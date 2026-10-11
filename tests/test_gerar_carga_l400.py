"""Testes do gerador de carga do L400 (scripts/gerar_carga_l400.py), todos locais: transporte injetado, sem Azure e sem rede.

Nada aqui abre um soquete: o transporte real é exercitado com um abridor falso, e a identidade gerenciada, com uma credencial falsa.
Endereço, token, perguntas, texto de resposta e identificadores são sentinelas que não podem aparecer no console nem nos relatórios.
"""

import ast
import contextlib
import http.client
import io
import json
import os
import re
import socket
import ssl
import stat
import sys
import tempfile
import threading
import time
import unicodedata
import unittest
import urllib.error
import urllib.request
import uuid
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import support  # noqa: F401  (configura o caminho dos scripts)
import avaliar_chat as ac
import chat_web
import gerar_carga_l400 as gc
import lab_chat as lc
import lab_comum
import lab_ingestao_l300
import lab_politica as lp
from support import RAIZ

HOST = "sentinela-do-destino.ambiente-ficticio.regiao-ficticia.azurecontainerapps.io"
HOST_INTERNO = "sentinela-do-destino.internal.ambiente-ficticio.regiao-ficticia.azurecontainerapps.io"
URL = f"https://{HOST}"
TOKEN = "token." + "a" * 30 + ".sintetico"
TEXTO_DA_RESPOSTA = "Texto sentinela da resposta, que nunca deve aparecer em saída alguma."
CITACAO = "Citação sentinela do trecho, que nunca deve aparecer em saída alguma."
PERGUNTA_DO_ARQUIVO = "Pergunta sentinela do arquivo sobre um tema sintético que nunca deve aparecer em saída alguma?"
OUTRA_PERGUNTA = "Segunda pergunta sentinela do arquivo, também sintética, que nunca deve aparecer em saída alguma?"
SENTINELAS = (TOKEN, HOST, URL, "sentinela-do-destino", TEXTO_DA_RESPOSTA, CITACAO, PERGUNTA_DO_ARQUIVO, OUTRA_PERGUNTA, *gc.PERGUNTAS_EMBUTIDAS)
ATACANTE = "atacante-ficticio.example"
# Destinos que um revisor mostrou aceitos antes da regra fechada de host (e variações): todos devem ser recusados antes de qualquer rede.
URLS_DE_ATAQUE = {
    "sufixo falso no meio do nome": f"https://chat.azurecontainerapps.io.{ATACANTE}",
    "sufixo falso colado por hífen": f"https://chat.azurecontainerapps.io-{ATACANTE}",
    "localhost": "https://localhost",
    "subdomínio de localhost": "https://x.localhost",
    "metadados de nuvem por nome": "https://metadata.google.internal",
    "metadados de nuvem por IP": "https://169.254.169.254",
    "IP v4 privado": "https://10.0.0.5",
    "IP v6": "https://[::1]",
    "IP em decimal": "https://2130706433",
    "domínio parecido sem o ponto": "https://chat-azurecontainerapps.io",
    "domínio parecido com letra a menos": "https://chat.azurecontainerapp.io",
    "domínio parecido com outro TLD": "https://chat.azurecontainerapps.com",
    "só o domínio, sem rótulo na frente": "https://azurecontainerapps.io",
    "domínio padrão com ponto final": f"https://{HOST}.",
    "maiúsculas com sufixo falso": f"HTTPS://CHAT.AZURECONTAINERAPPS.IO.{ATACANTE.upper()}",
    "IDN com ponto ideográfico": f"https://chat.azurecontainerapps.io\u3002{ATACANTE}",
    "IDN com i sem ponto": "https://chat.azurecontainerapps.\u0131o",
    "IDN com ponto de largura total": "https://chat\uff0eazurecontainerapps\uff0eio",
    "porta estranha no domínio padrão": f"{URL}:8443",
    "porta 80 no domínio padrão": f"{URL}:80",
    "porta estranha em host de ataque": f"https://{ATACANTE}:8443",
    "usuário com o domínio padrão": f"https://{HOST}@{ATACANTE}",
    "usuário com o domínio padrão e porta": f"https://{HOST}:443@{ATACANTE}",
    "fragmento com o sufixo": f"https://{ATACANTE}#.azurecontainerapps.io",
    "consulta com o sufixo": f"https://{ATACANTE}?.azurecontainerapps.io",
    "caminho com o sufixo": f"https://{ATACANTE}/.azurecontainerapps.io",
    "barra invertida antes do sufixo": f"https://{ATACANTE}\\.azurecontainerapps.io",
    "rótulo vazio na frente": "https://.azurecontainerapps.io",
    "rótulo vazio no meio": "https://a..azurecontainerapps.io",
    "sublinhado no rótulo": "https://a_b.azurecontainerapps.io",
    "rótulo com mais de 63 caracteres": "https://" + "a" * 64 + ".azurecontainerapps.io",
    "nome com mais de 253 caracteres": "https://" + ".".join(["a" * 60] * 5) + ".azurecontainerapps.io",
    "domínio personalizado": "https://chat.contoso.com",
    "outro serviço Azure": "https://conta.blob.core.windows.net",
    "exemplo do guia antigo": "https://exemplo.com",
}
FRAGMENTOS_DE_ATAQUE = (ATACANTE, "metadata.google", "169.254", "x.localhost", "contoso", "core.windows.net", "10.0.0.5", "2130706433",
                        "azurecontainerapp.io", "azurecontainerapps.com", "chat.exemplo")


def corpo_200(tipo=lp.DOCUMENTADA, evidencias=1, uso=(10, 20, 30, 0), simulada=False):
    """O corpo público de uma resposta 200, montado com as classes de produção: o gerador confere contra o mesmo formato."""
    itens = tuple(lc.EvidenciaChat(f"VLAR-T-1_0-00{numero}", CITACAO, "arquivo-ficticio.md", "1.0", "Documento fictício", "Seção fictícia", "1.1")
                  for numero in range(evidencias))
    resposta = lc.RespostaChat(tipo, lp.RESPONDIDA, TEXTO_DA_RESPOSTA, "", itens, lc.UsoChat(*uso) if uso else None, simulada)
    return json.dumps({"id": None, "id_requisicao": "a" * 32, **resposta.a_dict()}, ensure_ascii=False).encode("utf-8")


def resposta_ok(com_id=True, **opcoes):
    return gc.RespostaHttp(200, corpo_200(**opcoes), "application/json", com_id)


def resposta_erro(codigo, status, com_id=True):
    corpo = json.dumps({"erro": codigo, "mensagem": lc.MENSAGENS[codigo], "id_requisicao": "b" * 32}).encode("utf-8")
    return gc.RespostaHttp(status, corpo, "application/json", com_id)


def resposta_crua(status, corpo=b"", tipo="text/plain", com_id=False):
    return gc.RespostaHttp(status, corpo, tipo, com_id)


class Transporte:
    """Dublê de `enviar_http`: registra cada chamada, conta os pedidos simultâneos e responde conforme uma função (número, pergunta)."""

    def __init__(self, responder=None, duracao=0.0):
        self.responder = responder or (lambda numero, pergunta: resposta_ok())
        self.duracao = duracao
        self.durante = None
        self.chamadas = []
        self.atual = self.maximo = 0
        self._trava = threading.Lock()

    def __call__(self, url, corpo, cabecalhos, timeout):
        dados = json.loads(corpo.decode("utf-8"))
        with self._trava:
            self.chamadas.append({"url": url, "dados": dados, "cabecalhos": dict(cabecalhos), "timeout": timeout})
            numero = len(self.chamadas)
            self.atual += 1
            self.maximo = max(self.maximo, self.atual)
        try:
            if self.durante is not None:
                self.durante(numero)
            if self.duracao:
                time.sleep(self.duracao)
            resposta = self.responder(numero, dados["pergunta"])
        finally:
            with self._trava:
                self.atual -= 1
        if isinstance(resposta, BaseException):
            raise resposta
        return resposta

    @property
    def perguntas(self):
        return [chamada["dados"]["pergunta"] for chamada in self.chamadas]


class Relogio:
    """Relógio falso e seguro para threads: só avança quando o teste manda."""

    def __init__(self, inicio=0.0):
        self.agora, self._trava = inicio, threading.Lock()

    def __call__(self):
        with self._trava:
            return self.agora

    def avancar(self, segundos):
        with self._trava:
            self.agora += segundos


class CredencialFalsa:
    """Dublê da credencial gerenciada: nada sai da máquina."""

    instancias = []
    falha = None

    def __init__(self, client_id):
        self.client_id, self.escopos, self.fechada = client_id, [], False
        type(self).instancias.append(self)

    def get_token(self, *escopos, **opcoes):
        self.escopos.append(escopos)
        if type(self).falha is not None:
            raise type(self).falha
        return SimpleNamespace(token=TOKEN, expires_on=0)

    def close(self):
        self.fechada = True


@contextlib.contextmanager
def identidade_falsa(falha=None):
    CredencialFalsa.instancias, CredencialFalsa.falha = [], falha
    with mock.patch.object(lab_ingestao_l300, "criar_credencial_gerenciada", side_effect=CredencialFalsa):
        yield CredencialFalsa


def linha_do_resultado(texto):
    linhas = [linha for linha in texto.splitlines() if linha.startswith(gc.PREFIXO_DO_RESULTADO)]
    if len(linhas) != 1:
        raise AssertionError(f"era esperada uma linha de resultado, e há {len(linhas)}:\n{texto}")
    return json.loads(linhas[0][len(gc.PREFIXO_DO_RESULTADO):])


class FluxoRegistrado(io.StringIO):
    """Um fluxo de texto que também anota o que recebe em outro, compartilhado: assim se confere a ORDEM entre o stdout e o stderr."""

    def __init__(self, ordem):
        super().__init__()
        self.ordem = ordem

    def write(self, texto):
        self.ordem.write(texto)
        return super().write(texto)


class BaseDoGerador(unittest.TestCase):
    def setUp(self):
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        self.pasta = Path(pasta.name)
        self.relatorio = self.pasta / "relatorio.json"

    def rodar(self, *extras, url=URL, env=None, transporte=None, relogio=None):
        """Roda `principal` com a rede trocada por um dublê. Devolve (código, texto impresso, transporte)."""
        transporte = transporte or Transporte()
        argumentos = [*(["--url", url] if url is not None else []), *extras]
        saida = io.StringIO()
        with contextlib.redirect_stdout(saida), contextlib.redirect_stderr(saida):
            try:
                codigo = gc.principal(argumentos, env={gc.VAR_TOKEN: TOKEN} if env is None else env, transporte=transporte, relogio=relogio)
            except SystemExit as erro:
                codigo = erro.code
        return codigo, saida.getvalue(), transporte

    def rodar_separado(self, *extras, url=URL, env=None, transporte=None, relogio=None):
        """Como `rodar`, com stdout e stderr em fluxos distintos. Devolve (código, stdout, stderr, os dois na ordem em que foram escritos)."""
        transporte = transporte or Transporte()
        ordem = io.StringIO()
        saida, erro = FluxoRegistrado(ordem), FluxoRegistrado(ordem)
        with contextlib.redirect_stdout(saida), contextlib.redirect_stderr(erro):
            codigo = gc.principal([*(["--url", url] if url is not None else []), *extras],
                                  env={gc.VAR_TOKEN: TOKEN} if env is None else env, transporte=transporte, relogio=relogio)
        return codigo, saida.getvalue(), erro.getvalue(), ordem.getvalue()

    def executar(self, *extras, **opcoes):
        return self.rodar("--executar", "--confirmo-consumo", *extras, **opcoes)

    def ler_relatorio(self, caminho=None):
        return json.loads((caminho or self.relatorio).read_text(encoding="utf-8"))

    def sem_sentinelas(self, texto, *mais):
        for sentinela in (*SENTINELAS, *mais):
            self.assertNotIn(sentinela, texto)

    def escrever_perguntas(self, dados, nome="perguntas.json"):
        caminho = self.pasta / nome
        caminho.write_bytes(dados if isinstance(dados, bytes) else json.dumps(dados, ensure_ascii=False).encode("utf-8"))
        return caminho


# --------------------------------------------------------------------------------------
# Seguro por padrão: sem --executar nada sai
# --------------------------------------------------------------------------------------

class SeguroPorPadraoTests(BaseDoGerador):
    def test_sem_executar_nada_sai_por_rede_e_o_plano_mostra_os_limites_o_destino_mascarado_e_os_avisos(self):
        def proibido(*_, **__):
            raise AssertionError("o plano não pode usar a rede")

        transporte = Transporte(proibido)
        with contextlib.ExitStack() as pilha:
            for alvo, nome in ((socket.socket, "connect"), (socket, "create_connection"), (urllib.request.OpenerDirector, "open"),
                               (urllib.request, "build_opener"), (lab_ingestao_l300, "criar_credencial_gerenciada")):
                pilha.enter_context(mock.patch.object(alvo, nome, side_effect=proibido))
            codigo, saida, _ = self.rodar("--relatorio", str(self.relatorio), transporte=transporte)
        self.assertEqual(codigo, 0, saida)
        self.assertEqual(transporte.chamadas, [])
        self.assertFalse(self.relatorio.exists(), "o plano não cria relatório")
        self.assertNotIn(gc.PREFIXO_DO_RESULTADO, saida)
        self.sem_sentinelas(saida)
        for trecho in ("https://*.azurecontainerapps.io", "Pedidos: 6", "concorrência: 3",
                       f"pedidos novos só saem durante {gc.TEMPO_TOTAL_PADRAO:g} s (teto {gc.TEMPO_TOTAL_MAXIMO:g} s)",
                       f"até mais {gc.FOLGA_DE_ENCERRAMENTO:g} s para terminar",
                       f"o processo dura até {gc.TEMPO_TOTAL_PADRAO + gc.FOLGA_DE_ENCERRAMENTO:g} s depois do primeiro envio",
                       "o tempo de obter o token da identidade gerenciada fica fora dessa conta",
                       f"Por pedido: {gc.TEMPO_POR_PEDIDO_PADRAO:g} s (teto {gc.TEMPO_POR_PEDIDO_MAXIMO:g} s)",
                       "3 resultado(s) seguido(s)", "nenhum retry", "consome tokens", "não interrompe um pedido já enviado",
                       "não estabelece capacidade máxima", "garantia de disponibilidade", "[SIMULAÇÃO]", "--executar --confirmo-consumo",
                       "embutidas", gc.VAR_TOKEN, "os proxies do ambiente são ignorados de propósito"):
            self.assertIn(trecho, saida)
        self.assertNotIn("no total", saida, "o plano não promete um tempo total que o processo pode ultrapassar")

    def test_executar_exige_a_confirmacao_de_consumo_e_a_confirmacao_sozinha_continua_sendo_so_o_plano(self):
        sem_confirmar, so_confirmar = Transporte(), Transporte()
        codigo, saida, _ = self.rodar("--executar", "--relatorio", str(self.relatorio), transporte=sem_confirmar)
        self.assertEqual(codigo, 1, saida)
        self.assertIn("--confirmo-consumo", saida)
        self.assertEqual(sem_confirmar.chamadas, [])
        self.assertFalse(self.relatorio.exists())
        codigo, saida, _ = self.rodar("--confirmo-consumo", transporte=so_confirmar)
        self.assertEqual(codigo, 0, saida)
        self.assertEqual(so_confirmar.chamadas, [])
        self.assertIn("[SIMULAÇÃO]", saida)

    def test_plano_com_identidade_gerenciada_nao_pede_token_nem_cria_credencial(self):
        cliente, aplicativo = str(uuid.uuid4()), str(uuid.uuid4())
        with identidade_falsa() as credencial:
            codigo, saida, transporte = self.rodar("--identidade-gerenciada", "--client-id", cliente, "--audiencia",
                                                   f"api://{aplicativo}/.default", env={})
        self.assertEqual(codigo, 0, saida)
        self.assertEqual((credencial.instancias, transporte.chamadas), ([], []))
        self.assertIn("identidade gerenciada", saida)
        self.sem_sentinelas(saida, cliente, aplicativo)

    def test_plano_avisa_quando_o_prazo_por_pedido_e_menor_que_o_do_chat(self):
        codigo, saida, _ = self.rodar("--tempo-por-pedido", "30")
        self.assertEqual(codigo, 0, saida)
        self.assertIn("menor que o padrão do chat", saida)
        self.assertNotIn("menor que o padrão do chat", self.rodar()[1])

    def test_o_plano_nunca_mostra_o_host_so_o_dominio_padrao_mascarado_e_nao_tem_aviso_de_outro_host(self):
        sufixo = gc.DOMINIO_DO_CONTAINER_APPS
        for host in (HOST, f"rotulo-do-aplicativo.rotulo-do-ambiente.rotulo-da-regiao{sufixo}",
                     f"rotulo-do-aplicativo.internal.rotulo-do-ambiente.rotulo-da-regiao{sufixo}"):
            with self.subTest(host=host[:20]):
                codigo, saida, transporte = self.rodar(url=f"https://{host}")
                self.assertEqual((codigo, transporte.chamadas), (0, []), saida)
                self.assertIn("Destino: https://*.azurecontainerapps.io (mascarado", saida)
                for rotulo in host.split(".")[:-2]:
                    self.assertNotIn(rotulo, saida, "nenhum rótulo do host aparece")
                self.assertNotIn("o token será enviado a ele", saida, "um host fora do padrão não é mais aceito com aviso: é recusado")


# --------------------------------------------------------------------------------------
# Limites: valores fixos no código, conferidos antes de qualquer rede
# --------------------------------------------------------------------------------------

class LimitesTests(BaseDoGerador):
    def test_limites_invalidos_sao_recusados_antes_da_rede_sem_repetir_o_valor(self):
        invalidos = (
            ("--pedidos", "0"), ("--pedidos", "51"), ("--pedidos", "-1"), ("--pedidos", "1e1"), ("--pedidos", "5.5"), ("--pedidos", "valor-sentinela"),
            ("--pedidos", "9" * 40), ("--concorrencia", "0"), ("--concorrencia", "9"), ("--concorrencia", "valor-sentinela"),
            ("--tempo-maximo", "601"), ("--tempo-maximo", "9.9"), ("--tempo-maximo", "nan"), ("--tempo-maximo", "inf"),
            ("--tempo-maximo", "1e3"), ("--tempo-maximo", "300,5"), ("--tempo-maximo", "valor-sentinela"),
            ("--tempo-por-pedido", "0.9"), ("--tempo-por-pedido", "300.1"), ("--tempo-por-pedido", "valor-sentinela"),
            ("--falhas-seguidas", "0"), ("--falhas-seguidas", "11"), ("--falhas-seguidas", "valor-sentinela"),
        )
        for opcao, valor in invalidos:
            with self.subTest(opcao=opcao, valor=valor):
                transporte = Transporte()
                codigo, saida, _ = self.executar(opcao, valor, transporte=transporte)
                self.assertEqual(codigo, 1, saida)
                self.assertEqual(transporte.chamadas, [], "nada é enviado")
                self.assertIn(opcao, saida)
                self.assertNotIn("valor-sentinela", saida)
                self.assertNotIn("Traceback", saida)

    def test_concorrencia_nunca_passa_dos_pedidos_e_o_padrao_se_ajusta_a_eles(self):
        transporte = Transporte()
        codigo, saida, _ = self.executar("--pedidos", "2", "--concorrencia", "3", transporte=transporte)
        self.assertEqual((codigo, transporte.chamadas), (1, []), saida)
        self.assertIn("não pode ser maior que --pedidos", saida)
        codigo, saida, transporte = self.executar("--pedidos", "2", transporte=Transporte(duracao=0.01))
        self.assertEqual(codigo, 0, saida)
        resultado = linha_do_resultado(saida)
        self.assertEqual((resultado["concorrencia"], resultado["pedidos"]["enviados"], transporte.maximo <= 2), (2, 2, True))

    def test_os_limites_de_cada_borda_sao_aceitos_e_os_tetos_aparecem_no_plano(self):
        maximos = ("--pedidos", "50", "--concorrencia", "8", "--tempo-maximo", "600", "--tempo-por-pedido", "300", "--falhas-seguidas", "10")
        minimos = ("--pedidos", "1", "--concorrencia", "1", "--tempo-maximo", "10", "--tempo-por-pedido", "1", "--falhas-seguidas", "1")
        codigo, saida, _ = self.rodar(*maximos)
        self.assertEqual(codigo, 0, saida)
        for trecho in ("Pedidos: 50 (teto 50)", "concorrência: 8 (teto 8", "durante 600 s (teto 600 s)", "o processo dura até 610 s",
                       "Por pedido: 300 s (teto 300 s)", "10 resultado(s) seguido(s)"):
            self.assertIn(trecho, saida)
        codigo, saida, _ = self.rodar(*minimos)
        self.assertEqual(codigo, 0, saida)
        self.assertIn("Pedidos: 1 (teto 50)", saida)

    def test_todos_os_problemas_das_opcoes_sao_listados_de_uma_vez(self):
        codigo, saida, _ = self.rodar("--pedidos", "99", "--tempo-maximo", "9999", "--esperar", "inventada", "--executar")
        self.assertEqual(codigo, 1, saida)
        for opcao in ("--pedidos", "--tempo-maximo", "--esperar", "--confirmo-consumo"):
            self.assertIn(opcao, saida)
        self.assertNotIn("inventada", saida)

    def test_esperar_aceita_so_classes_conhecidas(self):
        self.assertEqual(gc.validar_esperar(None), frozenset({gc.OK}))
        self.assertEqual(gc.validar_esperar("ok, ocupado;ok"), frozenset({gc.OK, gc.OCUPADO}))
        for invalido in ("", "  ", "ok,inventada", "OK"):
            with self.assertRaises(lab_comum.ErroLab, msg=invalido):
                gc.validar_esperar(invalido)

    def test_argumentos_desconhecidos_e_abreviados_nao_repetem_o_valor_digitado(self):
        for argumentos in (["--token", TOKEN], [f"--token={TOKEN}"], ["--ped", "3"], [f"--executar={TOKEN}"], ["--confirmo-consumo", TOKEN]):
            with self.subTest(argumentos=argumentos[:1]):
                transporte = Transporte()
                codigo, saida, _ = self.rodar(*argumentos, transporte=transporte)
                self.assertEqual((codigo, transporte.chamadas), (1, []), saida)
                self.assertNotIn(TOKEN, saida)
                self.assertNotIn(HOST, saida)

    def test_nenhum_valor_de_opcao_malformada_ou_desconhecida_e_repetido_com_qualquer_estilo_de_aspas(self):
        valores = {"aspa simples": f"'{TOKEN}", "aspa dupla": f'"{TOKEN}', "sem aspas": TOKEN, "aspas dos dois tipos": f"""'"{TOKEN}"'""",
                   "valor vazio": ""}
        for nome, valor in valores.items():
            for opcao in ("--executar", "--confirmo-consumo", "--identidade-gerenciada", "--token-sentinela", "--help", "-h"):
                if opcao == "-h" and not valor:
                    continue  # "-h" sozinho é o pedido de ajuda, não um valor
                argumento = f"{opcao}={valor}" if opcao.startswith("--") else f"{opcao}{valor}"
                with self.subTest(estilo=nome, opcao=opcao):
                    transporte = Transporte()
                    codigo, saida, _ = self.rodar(argumento, transporte=transporte)
                    self.assertEqual(transporte.chamadas, [], saida)
                    self.assertNotIn(TOKEN, saida)
                    self.assertNotIn(HOST, saida)
                    if valor:
                        self.assertNotIn(valor, saida)
                    if opcao == "-h":
                        self.assertIn(codigo, (0, 1), "conforme a versão do Python, -hXYZ mostra a ajuda ou acusa o argumento ignorado")
                    else:
                        self.assertEqual(codigo, 1, saida)
                        self.assertRegex(saida, r"erro: argumentos? ")
        codigo, saida, _ = self.rodar(f"--executar='{TOKEN}")
        self.assertIn("argumento --executar: a opção não aceita valor", saida, "o nome da opção ajuda; o valor, nunca")
        codigo, saida, _ = self.rodar(f"--chave-desconhecida={TOKEN}", TOKEN, f"--{TOKEN}")
        self.assertIn("--chave-desconhecida", saida, "só o nome da opção, antes do =")
        self.assertIn("2 item(ns) sem nome de opção reconhecível", saida, "um valor solto ou um nome estranho vira só uma contagem")
        self.assertNotIn(TOKEN, saida)

    def test_erros_de_uso_que_citam_so_nomes_de_opcoes_continuam_claros(self):
        codigo, saida, _ = self.rodar("--pedidos")
        self.assertEqual(codigo, 1, saida)
        self.assertIn("argumento --pedidos: falta informar o valor", saida)
        codigo, saida, _ = self.rodar(url=None)
        self.assertIn("faltam argumentos obrigatórios: --url", saida)

    def test_sem_url_e_erro_de_uso(self):
        codigo, saida, _ = self.rodar(url=None)
        self.assertEqual(codigo, 1, saida)
        self.assertIn("--url", saida)


# --------------------------------------------------------------------------------------
# Destino: HTTPS, formato fechado, sem redirecionamento
# --------------------------------------------------------------------------------------

class DestinoTests(BaseDoGerador):
    def test_so_https_sem_usuario_parametros_fragmento_ip_ou_caminho_alheio_e_com_host_dns_valido(self):
        validas = {URL: URL, URL + "/": URL, URL + gc.CAMINHO_DA_API: URL, URL + gc.CAMINHO_DA_API + "/": URL, f"https://{HOST.upper()}": URL,
                   f"{URL}:443": URL, f"{URL}:443{gc.CAMINHO_DA_API}": URL, f"HTTPS://{HOST}": URL, f"https://{HOST_INTERNO}": f"https://{HOST_INTERNO}",
                   "https://a.azurecontainerapps.io": "https://a.azurecontainerapps.io"}
        for entrada, base in validas.items():
            with self.subTest(entrada=entrada):
                destino = gc.validar_url(entrada)
                self.assertEqual((destino.base, destino.url_do_pedido), (base, base + "/api/perguntar"))
                self.assertNotIn(destino.host, repr(destino))
        invalidas = (
            f"http://{HOST}", f"HTTP://{HOST}", f"ftp://{HOST}", f"https://usuario@{HOST}", f"https://usuario:senha@{HOST}",
            f"{URL}?x=1", f"{URL}/?x=1", f"{URL}#fragmento", f"{URL}/api/perguntar/progresso", f"{URL}/api/perguntar/cancelar", f"{URL}/outro",
            f"{URL}/api/perguntar?x", f"{URL}:0", f"{URL}:65536", f"{URL}:abc", f"{URL};x", f"{URL} ", f"{URL}\n", "https://localhost",
            "https://intranet", "https://10.0.0.5", "https://[::1]", "https://exemplo_.com", "https://-exemplo.com", "https://exemplo..com",
            f"https://{HOST}.", "https://exemplo.com\\@outro.com", "https://exémplo.com", "", "   ", "https://", "//host.example.com",
            "host.example.com", "https://" + "a" * 64 + ".com", "https://" + "a." * 130 + "com")
        for entrada in invalidas:
            with self.subTest(entrada=entrada[:40]):
                with self.assertRaises(lab_comum.ErroLab) as contexto:
                    gc.validar_url(entrada)
                self.assertEqual(contexto.exception.codigo, lab_comum.CODIGO_USO)
                if len(entrada.strip()) > 8:
                    self.assertNotIn(entrada.strip(), str(contexto.exception), "o endereço recusado não é repetido")

    def test_endereco_invalido_para_antes_de_qualquer_rede_e_o_destino_so_aparece_mascarado(self):
        for url in (f"http://{HOST}", f"{URL}/api/perguntar/progresso", f"https://usuario@{HOST}"):
            transporte = Transporte()
            codigo, saida, _ = self.executar(url=url, transporte=transporte)
            self.assertEqual((codigo, transporte.chamadas), (1, []), saida)
            self.assertNotIn(HOST, saida)
            self.assertNotIn("usuario", saida)
        for host in (HOST, HOST_INTERNO, "a.azurecontainerapps.io"):
            destino = gc.validar_url(f"https://{host}")
            self.assertEqual(destino.mascarado, "https://*.azurecontainerapps.io", "sempre o mesmo texto, qualquer que seja o host")

    def test_so_hosts_que_terminam_em_azurecontainerapps_io_por_rotulo_sao_aceitos_e_a_mensagem_e_clara(self):
        for url in ("https://chat.exemplo.com", "https://exemplo.com", f"{URL}:8443", "https://chat.contoso.com/api/perguntar"):
            with self.subTest(url=url[:30]):
                with self.assertRaises(lab_comum.ErroLab) as contexto:
                    gc.validar_url(url)
                self.assertEqual(contexto.exception.codigo, lab_comum.CODIGO_USO)
                self.assertNotIn(url, str(contexto.exception))
        with self.assertRaises(lab_comum.ErroLab) as contexto:
            gc.validar_url("https://chat.exemplo.com")
        mensagem = str(contexto.exception)
        for trecho in ("--url", "endereço padrão do Azure Container Apps", ".azurecontainerapps.io", "<aplicativo>.internal.<ambiente>.<região>",
                       "Domínio personalizado", "Nenhum token foi enviado"):
            self.assertIn(trecho, mensagem)
        with self.assertRaises(lab_comum.ErroLab) as contexto:
            gc.validar_url(f"{URL}:8443")
        self.assertIn("porta 443", str(contexto.exception))
        parser = gc.criar_parser()
        self.assertFalse([opcao for acao in parser._actions for opcao in acao.option_strings if opcao in ("--dominio", "--host", "--permitir-host")],
                         "não há opção para aceitar outro domínio")

    def test_hosts_de_ataque_sao_recusados_antes_de_qualquer_rede_sem_repetir_o_que_foi_digitado(self):
        self.assertGreaterEqual(len(URLS_DE_ATAQUE), 30)
        with contextlib.ExitStack() as pilha:
            for alvo, nome in ((socket, "create_connection"), (socket.socket, "connect"), (urllib.request, "build_opener"),
                               (urllib.request.OpenerDirector, "open"), (lab_ingestao_l300, "criar_credencial_gerenciada")):
                pilha.enter_context(mock.patch.object(alvo, nome, side_effect=AssertionError("nenhuma rede antes da validação do destino")))
            for nome, url in URLS_DE_ATAQUE.items():
                with self.subTest(nome):
                    with self.assertRaises(lab_comum.ErroLab) as contexto:
                        gc.validar_url(url)
                    self.assertEqual(contexto.exception.codigo, lab_comum.CODIGO_USO)
                    transporte = Transporte()
                    codigo, saida, _ = self.executar("--relatorio", str(self.pasta / f"{uuid.uuid4().hex}.json"), url=url, transporte=transporte)
                    self.assertEqual((codigo, transporte.chamadas), (1, []), saida)
                    self.assertIn("--url", saida)
                    self.assertNotIn(url, saida)
                    self.assertNotIn(TOKEN, saida)
                    for fragmento in FRAGMENTOS_DE_ATAQUE:
                        self.assertNotIn(fragmento, saida, "o host recusado não é repetido")
                    self.assertEqual(list(self.pasta.glob("*.json")), [], "nenhum relatório é criado para um destino recusado")

    def test_so_o_apice_do_dominio_digitado_por_engano_nao_e_confundido_com_um_segredo_no_console(self):
        codigo, saida, _ = self.rodar(url="https://azurecontainerapps.io")
        self.assertEqual(codigo, 1, saida)
        self.assertIn("termina em .azurecontainerapps.io", saida)
        codigo, saida, _ = self.rodar(url="https://localhost")
        self.assertEqual(codigo, 1, saida)
        self.assertIn("localhost", saida, "a mensagem cita localhost como caso não aceito, e o console não o troca por asteriscos")
        self.assertNotIn("***", saida)

    def test_a_regra_do_host_e_a_mesma_do_avaliador_de_chat_irmao(self):
        self.assertEqual((gc.DOMINIO_DO_CONTAINER_APPS, gc._PADRAO_HOST.pattern), (ac.DOMINIO_DO_CONTAINER_APPS, ac._PADRAO_HOST.pattern))
        aceitas = (URL, URL + "/", f"https://{HOST.upper()}", f"https://{HOST_INTERNO}", "https://a.azurecontainerapps.io",
                   "https://xn--chat-fqa.azurecontainerapps.io")
        for url in (*aceitas, *(url for nome, url in URLS_DE_ATAQUE.items() if "porta" not in nome)):
            with self.subTest(url=url[:40]):
                resultados = []
                for validar in (gc.validar_url, ac.validar_destino):
                    try:
                        resultados.append(validar(url).base)
                    except lab_comum.ErroLab:
                        resultados.append(None)
                self.assertEqual(resultados[0], resultados[1], "o gerador e o avaliador aceitam e recusam os mesmos hosts")
                self.assertEqual(resultados[0] is not None, url in aceitas)

    def test_o_token_so_vai_ao_destino_validado_na_rota_fixa_com_o_corpo_so_da_pergunta(self):
        codigo, saida, transporte = self.executar("--pedidos", "3", url=f"{URL}/api/perguntar/")
        self.assertEqual(codigo, 0, saida)
        self.assertEqual(len(transporte.chamadas), 3)
        for chamada in transporte.chamadas:
            self.assertEqual(chamada["url"], f"{URL}/api/perguntar")
            self.assertEqual(set(chamada["dados"]), {"pergunta"})
            self.assertEqual(chamada["cabecalhos"]["Authorization"], f"Bearer {TOKEN}")
            self.assertEqual(chamada["cabecalhos"]["Content-Type"], "application/json")
            self.assertLessEqual(chamada["timeout"], 120)

    def test_redirecionamento_nao_e_seguido_e_vira_uma_classe_propria(self):
        transporte = Transporte(lambda numero, pergunta: resposta_crua(302, b"", "text/html", com_id=False))
        codigo, saida, _ = self.executar("--falhas-seguidas", "10", transporte=transporte)
        self.assertEqual(codigo, 3, saida)
        self.assertEqual(len(transporte.chamadas), 6, "o 3xx é o resultado: nenhuma chamada extra para segui-lo")
        resultado = linha_do_resultado(saida)
        self.assertEqual((resultado["classes"]["redirecionamento"], resultado["codigos_http"]), (6, {"302": 6}))

class TransporteRealTests(unittest.TestCase):
    """O transporte de verdade (`enviar_http`) sobre o `urllib` real, com a conexão trocada por bytes crus: nenhum soquete, nenhuma rede.

    O ambiente da máquina não pode mudar o resultado: as variáveis de proxy são removidas (um proxy definido no ambiente já fez estes
    testes falharem) e `getproxies`, que também lê o registro do Windows, devolve vazio.
    """

    def setUp(self):
        ambiente = mock.patch.dict(os.environ)
        ambiente.start()
        self.addCleanup(ambiente.stop)
        for nome in [nome for nome in os.environ if nome.lower().endswith("_proxy")]:
            del os.environ[nome]
        proxies = mock.patch.object(urllib.request, "getproxies", return_value={})
        proxies.start()
        self.addCleanup(proxies.stop)
        ConexaoFalsa.respostas, ConexaoFalsa.pedidos, ConexaoFalsa.conexoes = [], [], []

    def test_o_transporte_real_atravessa_o_urllib_sem_soquete_nao_segue_redirecionamento_e_guarda_so_a_presenca_do_id(self):
        identificador = uuid.uuid4().hex
        corpo = corpo_200()
        ConexaoFalsa.respostas = [
            http_cru(200, "OK", {"Content-Type": "application/json; charset=utf-8", "X-Request-Id": identificador}, corpo),
            http_cru(302, "Found", {"Location": "https://outro.example.com/", "X-Request-Id": identificador}),
            http_cru(429, "Too Many Requests", {"Content-Type": "application/json", "Retry-After": "2", "X-Request-Id": identificador},
                     json.dumps({"erro": lc.OCUPADO, "mensagem": lc.MENSAGENS[lc.OCUPADO], "id_requisicao": "b" * 32}).encode("utf-8")),
            http_cru(502, "Bad Gateway", {"Content-Type": "text/html"}, b"<html>falha da borda</html>"),
            http_cru(200, "OK", {"Content-Type": "application/json", "X-Request-Id": "não é um identificador"}, b"{}"),
        ]
        ConexaoFalsa.pedidos = []
        cabecalhos = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
        with mock.patch.object(http.client, "HTTPSConnection", ConexaoFalsa):
            respostas = [gc.enviar_http(f"{URL}/api/perguntar", b'{"pergunta":"x"}', cabecalhos, 7.0) for _ in range(5)]
        self.assertEqual(ConexaoFalsa.respostas, [], "uma conexão por pedido, e o 302 não abriu uma segunda para segui-lo")
        self.assertEqual([resposta.status for resposta in respostas], [200, 302, 429, 502, 200])
        self.assertEqual([resposta.id_requisicao_presente for resposta in respostas], [True, True, True, False, False])
        self.assertEqual((respostas[0].corpo, respostas[0].tipo_de_conteudo), (corpo, "application/json; charset=utf-8"))
        self.assertEqual([gc.classificar(1, resposta, 5).classe for resposta in respostas],
                         [gc.OK, gc.REDIRECIONAMENTO, gc.OCUPADO, gc.HTTP, gc.FORMATO_INVALIDO])
        for resposta in respostas:
            self.assertNotIn(identificador, repr(resposta) + json.dumps(asdict(resposta), default=repr))
        self.assertEqual(len(ConexaoFalsa.pedidos), 5)
        for servidor, timeout, metodo, seletor, enviado, enviados in ConexaoFalsa.pedidos:
            self.assertEqual((servidor, timeout, metodo, seletor, enviado), (HOST, 7.0, "POST", "/api/perguntar", b'{"pergunta":"x"}'))
            self.assertEqual((enviados["Authorization"], enviados["Connection"]), (f"Bearer {TOKEN}", "close"))

    def test_o_transporte_real_le_so_o_limite_de_bytes_com_ou_sem_content_length(self):
        grande = b"x" * (gc.LIMITE_DA_RESPOSTA + 1)
        sem_tamanho = "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\n\r\n".encode("latin-1") + grande
        for nome, bruto in (("tamanho declarado", http_cru(200, "OK", {"Content-Type": "application/json"}, grande)),
                            ("sem tamanho", sem_tamanho)):
            with self.subTest(nome):
                ConexaoFalsa.respostas, ConexaoFalsa.pedidos = [bruto], []
                with mock.patch.object(http.client, "HTTPSConnection", ConexaoFalsa):
                    with self.assertRaises(gc.FalhaDeTransporte) as contexto:
                        gc.enviar_http(URL, b"{}", {}, 5.0)
                self.assertEqual(contexto.exception.rotulo, "corpo_grande")
        ConexaoFalsa.respostas = [http_cru(200, "OK", {"Content-Type": "application/json"}, b"y" * gc.LIMITE_DA_RESPOSTA)]
        with mock.patch.object(http.client, "HTTPSConnection", ConexaoFalsa):
            self.assertEqual(len(gc.enviar_http(URL, b"{}", {}, 5.0).corpo), gc.LIMITE_DA_RESPOSTA, "exatamente no limite ainda é lido")

    def test_o_transporte_real_rotula_as_falhas_sem_o_texto_do_erro(self):
        casos = {
            "dns": [urllib.error.URLError(socket.gaierror(11001, "texto interno sentinela")), socket.gaierror(11001, "texto interno sentinela")],
            "conexao": [urllib.error.URLError(ConnectionRefusedError()), http.client.RemoteDisconnected("texto interno sentinela"), OSError("x")],
            "tls": [urllib.error.URLError(ssl.SSLCertVerificationError("texto interno sentinela")), ssl.SSLError("x")],
            "tempo_esgotado": [urllib.error.URLError(TimeoutError()), TimeoutError()],
        }
        for rotulo, acoes in casos.items():
            for acao in acoes:
                with self.subTest(rotulo=rotulo, acao=type(acao).__name__):
                    with mock.patch.object(urllib.request, "build_opener", return_value=AbridorFalso(acao)):
                        with self.assertRaises(gc.FalhaDeTransporte) as contexto:
                            gc.enviar_http(URL, b"{}", {}, 5.0)
                    self.assertEqual(contexto.exception.rotulo, rotulo)
                    self.assertNotIn("sentinela", str(contexto.exception))

    def test_falhas_ao_abrir_a_conexao_passam_pelo_urllib_e_viram_rotulos(self):
        for erro, rotulo in ((socket.gaierror(11001, "x"), "dns"), (ConnectionRefusedError(), "conexao"),
                             (ssl.SSLCertVerificationError("x"), "tls"), (TimeoutError(), "tempo_esgotado")):
            with self.subTest(rotulo):
                ConexaoFalsa.respostas, ConexaoFalsa.pedidos = [], []
                with mock.patch.object(http.client, "HTTPSConnection", ConexaoFalsa), mock.patch.object(ConexaoFalsa, "falha", erro):
                    with self.assertRaises(gc.FalhaDeTransporte) as contexto:
                        gc.enviar_http(URL, b"{}", {}, 5.0)
                self.assertEqual(contexto.exception.rotulo, rotulo)

    def test_a_verificacao_tls_padrao_e_preservada_o_gerador_nao_injeta_contexto_proprio(self):
        ConexaoFalsa.respostas = [http_cru(200, "OK", {"Content-Type": "application/json"}, corpo_200())]
        with mock.patch.object(http.client, "HTTPSConnection", ConexaoFalsa), \
                mock.patch.object(urllib.request, "build_opener", wraps=urllib.request.build_opener) as construir:
            gc.enviar_http(f"{URL}/api/perguntar", b"{}", {}, 5.0)
        (conexao,) = ConexaoFalsa.conexoes
        contexto = conexao.opcoes["context"]
        self.assertIsInstance(contexto, ssl.SSLContext)
        self.assertEqual((contexto.verify_mode, contexto.check_hostname), (ssl.CERT_REQUIRED, True), "certificado e nome do host verificados")
        padrao = ssl.create_default_context()
        self.assertEqual((contexto.minimum_version, contexto.verify_flags), (padrao.minimum_version, padrao.verify_flags))
        self.assertEqual([type(item) for item in construir.call_args.args], [urllib.request.ProxyHandler, gc._SemRedirecionamento],
                         "nenhum HTTPSHandler com contexto próprio: o urllib cria o dele, com a verificação padrão")

    def test_proxies_do_ambiente_sao_ignorados_e_o_token_nao_passa_por_um_intermediario_implicito(self):
        proxy = "http://proxy-ficticio.invalid:3128"
        variaveis = {nome: proxy for nome in ("https_proxy", "HTTPS_PROXY", "http_proxy", "HTTP_PROXY", "all_proxy", "ALL_PROXY")}
        with mock.patch.dict(os.environ, variaveis), mock.patch.object(urllib.request, "getproxies", urllib.request.getproxies_environment):
            self.assertEqual(urllib.request.getproxies().get("https"), proxy, "a premissa: o urllib padrão usaria este proxy")
            ConexaoFalsa.respostas = [http_cru(200, "OK", {"Content-Type": "application/json"}, corpo_200())]
            with mock.patch.object(http.client, "HTTPSConnection", ConexaoFalsa):
                resposta = gc.enviar_http(f"{URL}/api/perguntar", b"{}", {"Content-Type": "application/json"}, 5.0)
        self.assertEqual(resposta.status, 200)
        (conexao,) = ConexaoFalsa.conexoes
        self.assertEqual((conexao.host, conexao.tuneis), (HOST, []), "a conexão vai direto ao destino, sem túnel por proxy")
        self.assertEqual([pedido[0] for pedido in ConexaoFalsa.pedidos], [HOST])


def http_cru(status, razao, cabecalhos, corpo=b""):
    """Uma resposta HTTP/1.1 em bytes, como viria do servidor: quem a interpreta é o `http.client` de verdade."""
    linhas = [f"HTTP/1.1 {status} {razao}", *(f"{nome}: {valor}" for nome, valor in cabecalhos.items())]
    if "Content-Length" not in cabecalhos:
        linhas.append(f"Content-Length: {len(corpo)}")
    return ("\r\n".join(linhas) + "\r\n\r\n").encode("latin-1") + corpo


class SoqueteFalso:
    """Só o que `http.client.HTTPResponse` pede de um soquete: `makefile`. Não há rede."""

    def __init__(self, bruto):
        self.bruto = bruto

    def makefile(self, modo="rb", *_, **__):
        return io.BytesIO(self.bruto)

    def close(self):
        pass


class ConexaoFalsa(http.client.HTTPSConnection):
    """Dublê de `http.client.HTTPSConnection`: o `urllib` real (redirecionamento, HTTPError, cabeçalhos) roda sobre bytes crus, sem soquete."""

    respostas, pedidos, conexoes, falha = [], [], [], None

    def __init__(self, host, port=None, timeout=None, **opcoes):  # sem super(): nenhum soquete
        self.host, self.timeout, self.sock, self.opcoes, self.tuneis = host, timeout, None, opcoes, []
        type(self).conexoes.append(self)

    def set_tunnel(self, host, port=None, headers=None):
        self.tuneis.append(host)  # só um proxy faria o urllib pedir um túnel

    def set_debuglevel(self, nivel):
        pass

    def request(self, metodo, seletor, corpo=None, cabecalhos=None, **opcoes):
        if type(self).falha is not None:
            raise type(self).falha
        type(self).pedidos.append((self.host, self.timeout, metodo, seletor, corpo, dict(cabecalhos or {})))

    def getresponse(self):
        resposta = http.client.HTTPResponse(SoqueteFalso(type(self).respostas.pop(0)), method="POST")
        resposta.begin()
        return resposta

    def close(self):
        pass


class AbridorFalso:
    """Dublê do abridor de `urllib`: levanta o que lhe foi entregue. Nada abre um soquete."""

    def __init__(self, acao):
        self.acao, self.chamadas = acao, []

    def open(self, requisicao, timeout=None):
        self.chamadas.append((requisicao, timeout))
        raise self.acao


# --------------------------------------------------------------------------------------
# Token: só de variável de ambiente ou da identidade gerenciada, nunca impresso
# --------------------------------------------------------------------------------------

class TokenTests(BaseDoGerador):
    def test_o_token_so_vem_da_variavel_padrao_ou_da_indicada_e_nao_existe_opcao_para_informa_lo(self):
        opcoes = [opcao for acao in gc.criar_parser()._actions for opcao in acao.option_strings if "token" in opcao]
        self.assertEqual(opcoes, ["--token-env"], "só o NOME da variável é recebido, nunca o token")
        outro = TOKEN + "-outro"
        codigo, saida, transporte = self.executar("--pedidos", "2", "--token-env", "MINHA_VARIAVEL_DE_TOKEN",
                                                  env={gc.VAR_TOKEN: TOKEN, "MINHA_VARIAVEL_DE_TOKEN": outro})
        self.assertEqual(codigo, 0, saida)
        self.assertEqual({chamada["cabecalhos"]["Authorization"] for chamada in transporte.chamadas}, {f"Bearer {outro}"})
        self.assertNotIn("MINHA_VARIAVEL_DE_TOKEN", saida, "um nome informado não é repetido: poderia ser um token digitado no lugar")
        self.sem_sentinelas(saida, outro)

    def test_token_ausente_ou_malformado_impede_a_execucao_sem_repetir_o_valor(self):
        for variaveis in ({}, {gc.VAR_TOKEN: "   "}, {gc.VAR_TOKEN: "curto demais"}, {gc.VAR_TOKEN: "x" * 9000}):
            with self.subTest(tamanho=len(variaveis.get(gc.VAR_TOKEN, ""))):
                transporte = Transporte()
                codigo, saida, _ = self.executar("--relatorio", str(self.relatorio), env=variaveis, transporte=transporte)
                self.assertEqual((codigo, transporte.chamadas), (1, []), saida)
                self.assertFalse(self.relatorio.exists())
                self.assertNotIn("curto demais", saida)
        codigo, saida, _ = self.rodar(env={gc.VAR_TOKEN: "curto demais"})
        self.assertEqual(codigo, 1, "um valor malformado já aparece no plano")
        codigo, saida, _ = self.rodar(env={})
        self.assertEqual(codigo, 0, "no plano a falta do token só é avisada")
        self.assertIn("NÃO definida", saida)

    def test_nome_de_variavel_invalido_nao_e_repetido(self):
        for nome in (TOKEN, "com espaco", "1COMECA_COM_NUMERO", "a" * 65, "tem-hifen"):
            with self.subTest(nome=nome[:12]):
                transporte = Transporte()
                codigo, saida, _ = self.executar("--token-env", nome, transporte=transporte)
                self.assertEqual((codigo, transporte.chamadas), (1, []), saida)
                self.assertNotIn(nome, saida)

    def test_identidade_gerenciada_usa_a_credencial_do_repositorio_pede_o_escopo_e_nao_imprime_o_token(self):
        cliente, aplicativo = str(uuid.uuid4()).upper(), str(uuid.uuid4())
        audiencia = f"api://{aplicativo}/.default"
        with identidade_falsa() as credencial:
            codigo, saida, transporte = self.executar("--pedidos", "3", "--relatorio", str(self.relatorio), "--identidade-gerenciada",
                                                      "--client-id", cliente, "--audiencia", audiencia, env={})
        self.assertEqual(codigo, 0, saida)
        (instancia,) = credencial.instancias
        self.assertEqual((instancia.client_id, instancia.escopos, instancia.fechada), (cliente.lower(), [(audiencia,)], True))
        self.assertEqual({chamada["cabecalhos"]["Authorization"] for chamada in transporte.chamadas}, {f"Bearer {TOKEN}"})
        self.sem_sentinelas(saida + self.relatorio.read_text(encoding="utf-8"), cliente, cliente.lower(), aplicativo, audiencia)
        self.assertEqual(self.ler_relatorio()["identidade"], {"tipo": "identidade_gerenciada"})

    def test_a_variavel_de_token_nao_e_usada_nem_pedida_com_a_identidade_gerenciada(self):
        with identidade_falsa() as credencial:
            codigo, saida, transporte = self.executar("--identidade-gerenciada", "--client-id", str(uuid.uuid4()), "--audiencia",
                                                      f"api://{uuid.uuid4()}/.default", env={gc.VAR_TOKEN: "ignorado-e-de-outra-origem-123456"})
        self.assertEqual(codigo, 0, saida)
        self.assertEqual({chamada["cabecalhos"]["Authorization"] for chamada in transporte.chamadas}, {f"Bearer {TOKEN}"})
        self.assertEqual(len(credencial.instancias), 1)

    def test_identidade_gerenciada_exige_client_id_e_audiencia_validos_e_nao_combina_com_token_env(self):
        cliente, audiencia = str(uuid.uuid4()), f"api://{uuid.uuid4()}/.default"
        invalidas = {
            "sem nada": ["--identidade-gerenciada"],
            "sem audiência": ["--identidade-gerenciada", "--client-id", cliente],
            "sem client-id": ["--identidade-gerenciada", "--audiencia", audiencia],
            "client-id inválido": ["--identidade-gerenciada", "--client-id", "nao-e-guid", "--audiencia", audiencia],
            "audiência inválida": ["--identidade-gerenciada", "--client-id", cliente, "--audiencia", "https://exemplo.com/.default"],
            "audiência sem o escopo": ["--identidade-gerenciada", "--client-id", cliente, "--audiencia", f"api://{uuid.uuid4()}"],
            "com --token-env": ["--identidade-gerenciada", "--client-id", cliente, "--audiencia", audiencia, "--token-env", "OUTRA"],
            "client-id sem a identidade": ["--client-id", cliente],
            "audiência sem a identidade": ["--audiencia", audiencia],
        }
        for nome, argumentos in invalidas.items():
            with self.subTest(nome):
                with identidade_falsa() as credencial:
                    transporte = Transporte()
                    codigo, saida, _ = self.executar(*argumentos, transporte=transporte)
                self.assertEqual((codigo, transporte.chamadas, credencial.instancias), (1, [], []), saida)
                self.assertNotIn(cliente, saida)
                self.assertNotIn("nao-e-guid", saida)

    def test_falha_ao_obter_o_token_gerenciado_sai_com_2_sem_enviar_pedidos_e_so_mostra_o_codigo_aadsts(self):
        cliente, intruso = str(uuid.uuid4()), str(uuid.uuid4())
        falha = Exception(f"AADSTS70011: o escopo é inválido para o recurso {intruso}")
        with identidade_falsa(falha) as credencial:
            codigo, saida, transporte = self.executar("--relatorio", str(self.relatorio), "--identidade-gerenciada", "--client-id", cliente,
                                                      "--audiencia", f"api://{uuid.uuid4()}/.default")
        self.assertEqual((codigo, transporte.chamadas), (2, []), saida)
        self.assertIn("AADSTS70011", saida)
        self.assertNotIn(intruso, saida + self.relatorio.read_text(encoding="utf-8"))
        self.assertTrue(credencial.instancias[0].fechada, "a credencial é fechada mesmo com a falha")
        resultado = linha_do_resultado(saida)
        self.assertEqual((resultado["interrupcao"], resultado["pedidos"]["enviados"], resultado["codigo_de_saida"]), ("falha_de_token", 0, 2))
        self.assertEqual(self.ler_relatorio()["status"], "interrompido")

    def test_a_credencial_gerenciada_e_o_azure_so_sao_importados_sob_demanda_e_o_gerador_cabe_na_imagem_do_chat(self):
        arvore = ast.parse((RAIZ / "scripts" / "gerar_carga_l400.py").read_text(encoding="utf-8"))
        no_modulo, dentro_de_funcoes = set(), set()

        def visitar(no, em_funcao):
            alvo = dentro_de_funcoes if em_funcao else no_modulo
            if isinstance(no, ast.Import):
                alvo.update(item.name.split(".")[0] for item in no.names)
            elif isinstance(no, ast.ImportFrom) and no.module:
                alvo.add(no.module.split(".")[0])
            for filho in ast.iter_child_nodes(no):
                visitar(filho, em_funcao or isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)))

        visitar(arvore, False)
        for modulo in ("lab_ingestao_l300", "azure"):
            self.assertNotIn(modulo, no_modulo, "o modo local, com o token em variável, não exige o Azure")
        fora_da_biblioteca_padrao = {modulo for modulo in no_modulo if modulo not in sys.stdlib_module_names}
        self.assertEqual(fora_da_biblioteca_padrao, {"lab_chat", "lab_comum", "lab_politica"},
                         "só módulos que a imagem do chat já tem: o gerador entra em um Job acrescentando um único arquivo")
        self.assertEqual({modulo for modulo in dentro_de_funcoes if modulo not in sys.stdlib_module_names}, {"lab_ingestao_l300"})
        with identidade_falsa() as credencial:
            self.executar("--pedidos", "2")
        self.assertEqual(credencial.instancias, [], "com o token em variável a credencial gerenciada nem é criada")

    def test_sem_o_modulo_da_identidade_o_erro_orienta_sem_traceback(self):
        argumentos = ["--identidade-gerenciada", "--client-id", str(uuid.uuid4()), "--audiencia", f"api://{uuid.uuid4()}/.default"]
        with mock.patch.dict("sys.modules", {"lab_ingestao_l300": None}):
            codigo, saida, transporte = self.executar(*argumentos, env={})
        self.assertEqual((codigo, transporte.chamadas), (1, []), saida)
        self.assertIn("requirements/l400.txt", saida)
        self.assertNotIn("Traceback", saida)

    def test_se_algum_caminho_imprimir_o_token_o_console_o_troca_por_asteriscos(self):
        def imprime_por_engano(numero):
            print(f"depuração esquecida: {TOKEN} em {URL}")

        transporte = Transporte()
        transporte.durante = imprime_por_engano
        codigo, saida, _ = self.executar("--pedidos", "2", transporte=transporte)
        self.assertEqual(codigo, 0, saida)
        self.assertIn("***", saida)
        self.sem_sentinelas(saida)

    def test_resultado_com_valor_sensivel_nao_e_impresso_nem_gravado(self):
        original = gc.montar_resultado
        with mock.patch.object(gc, "montar_resultado", side_effect=lambda execucao: {**original(execucao), "vazou": TOKEN}):
            codigo, saida, _ = self.executar("--relatorio", str(self.relatorio))
        self.assertEqual(codigo, 4, saida)
        self.assertNotIn(gc.PREFIXO_DO_RESULTADO, saida)
        self.assertNotIn(TOKEN, saida + self.relatorio.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------------------
# Perguntas
# --------------------------------------------------------------------------------------

def _palavras(texto):
    sem_acentos = "".join(letra for letra in unicodedata.normalize("NFD", texto.casefold()) if unicodedata.category(letra) != "Mn")
    return set(re.findall(r"[a-z0-9]+", sem_acentos))


def perguntas_dos_conjuntos():
    """Toda pergunta de todo arquivo JSON de dados/: avaliações finais, conjuntos de ajuste e de conferência."""
    encontradas = []

    def coletar(no):
        if isinstance(no, dict):
            for chave, valor in no.items():
                if chave == "pergunta" and isinstance(valor, str):
                    encontradas.append(valor)
                else:
                    coletar(valor)
        elif isinstance(no, list):
            for item in no:
                coletar(item)

    for caminho in sorted((RAIZ / "dados").rglob("*.json")):
        coletar(json.loads(caminho.read_text(encoding="utf-8-sig")))
    return encontradas


class PerguntasTests(BaseDoGerador):
    def test_perguntas_embutidas_sao_poucas_validas_para_o_chat_e_diferentes_de_todo_conjunto_de_avaliacao(self):
        embutidas = gc.PERGUNTAS_EMBUTIDAS
        self.assertTrue(3 <= len(embutidas) <= 5)
        self.assertEqual(len(set(embutidas)), len(embutidas))
        for pergunta in embutidas:
            lc.ler_pedido(json.dumps({"pergunta": pergunta}).encode("utf-8"), "application/json")  # o chat as aceitaria
            self.assertFalse(lp.parece_contratacao_individual(pergunta), "são perguntas gerais sobre regras, não casos individuais")
        existentes = perguntas_dos_conjuntos()
        self.assertGreater(len(existentes), 50, "o teste precisa ver os conjuntos existentes para valer")
        for pergunta in embutidas:
            palavras = _palavras(pergunta)
            for outra in existentes:
                parecidas = _palavras(outra)
                self.assertNotEqual(lp.normalizar(pergunta), lp.normalizar(outra), "não pode ser uma pergunta de um conjunto")
                self.assertLess(len(palavras & parecidas) / len(palavras | parecidas), 0.7, "não pode ser derivada de uma pergunta de um conjunto")

    def test_arquivo_de_perguntas_vale_em_rodizio_e_os_textos_nunca_saem(self):
        caminho = self.escrever_perguntas([PERGUNTA_DO_ARQUIVO, OUTRA_PERGUNTA])
        codigo, saida, transporte = self.executar("--perguntas-arquivo", str(caminho), "--pedidos", "5", "--concorrencia", "1",
                                                  "--relatorio", str(self.relatorio))
        self.assertEqual(codigo, 0, saida)
        self.assertEqual(transporte.perguntas, [PERGUNTA_DO_ARQUIVO, OUTRA_PERGUNTA, PERGUNTA_DO_ARQUIVO, OUTRA_PERGUNTA, PERGUNTA_DO_ARQUIVO])
        self.sem_sentinelas(saida + self.relatorio.read_text(encoding="utf-8"))
        self.assertEqual(self.ler_relatorio()["perguntas"], {"origem": "arquivo", "quantidade": 2, "conferencia_com_avaliacoes": "feita",
                                                             "comparadas_com_avaliacoes": len(perguntas_dos_conjuntos())})

    def test_pergunta_curta_igual_a_uma_palavra_da_saida_nao_estraga_o_resultado(self):
        caminho = self.escrever_perguntas(["documentada", "ocupado"])
        codigo, saida, _ = self.executar("--perguntas-arquivo", str(caminho), "--pedidos", "4", "--relatorio", str(self.relatorio))
        self.assertEqual(codigo, 0, saida)
        self.assertEqual(linha_do_resultado(saida)["tipos"], {"documentada": 4})
        self.assertEqual(self.ler_relatorio()["perguntas"]["quantidade"], 2)

    def test_arquivo_de_perguntas_aceita_utf8_com_ou_sem_bom_e_utf16_do_powershell(self):
        dados = json.dumps([PERGUNTA_DO_ARQUIVO, OUTRA_PERGUNTA], ensure_ascii=False)
        for nome, bruto in (("utf-8", dados.encode("utf-8")), ("utf-8 com bom", b"\xef\xbb\xbf" + dados.encode("utf-8")),
                            ("utf-16", dados.encode("utf-16")), ("utf-16 be", b"\xfe\xff" + dados.encode("utf-16-be"))):
            with self.subTest(nome):
                carregadas = gc.carregar_perguntas(str(self.escrever_perguntas(bruto, f"{nome}.json")))
                self.assertEqual((carregadas.textos, carregadas.origem), ((PERGUNTA_DO_ARQUIVO, OUTRA_PERGUNTA), "arquivo"))
        with self.assertRaises(lab_comum.ErroLab):
            gc.carregar_perguntas(str(self.escrever_perguntas(b"\xff\xfe\x00", "truncado.json")))

    def test_perguntas_embutidas_giram_em_rodizio_e_com_concorrencia_cada_uma_e_usada_por_igual(self):
        codigo, saida, transporte = self.executar("--pedidos", "8", "--concorrencia", "4")
        self.assertEqual(codigo, 0, saida)
        contagem = {pergunta: transporte.perguntas.count(pergunta) for pergunta in gc.PERGUNTAS_EMBUTIDAS}
        self.assertEqual(set(contagem.values()), {8 // len(gc.PERGUNTAS_EMBUTIDAS)})
        self.assertEqual(sum(contagem.values()), 8)

    def test_arquivo_de_perguntas_invalido_e_recusado_sem_repetir_os_textos(self):
        grande = [f"Pergunta sintética de desenvolvimento número {numero}?" for numero in range(gc.PERGUNTAS_NO_ARQUIVO_MAXIMAS + 1)]
        invalidos = {
            "não é lista": {"perguntas": [PERGUNTA_DO_ARQUIVO]},
            "lista vazia": [],
            "mais que o limite": grande,
            "item que não é texto": [PERGUNTA_DO_ARQUIVO, 3],
            "item vazio": [PERGUNTA_DO_ARQUIVO, "   "],
            "item acima do limite do chat": [PERGUNTA_DO_ARQUIVO, "a" * (lc.LIMITE_DA_PERGUNTA + 1)],
            "item com caractere de controle": json.dumps([PERGUNTA_DO_ARQUIVO, "texto com \u0007 controle"]).encode("utf-8"),
            "json inválido": b"[ isto nao e json",
            "arquivo acima do limite": b" " * (gc.LIMITE_DO_ARQUIVO_DE_PERGUNTAS + 1),
        }
        for nome, dados in invalidos.items():
            with self.subTest(nome):
                transporte = Transporte()
                codigo, saida, _ = self.executar("--perguntas-arquivo", str(self.escrever_perguntas(dados)), transporte=transporte)
                self.assertEqual((codigo, transporte.chamadas), (1, []), saida)
                self.assertIn("--perguntas-arquivo", saida)
                self.assertNotIn(PERGUNTA_DO_ARQUIVO, saida)
        codigo, saida, _ = self.rodar("--perguntas-arquivo", str(self.pasta / "nao-existe.json"))
        self.assertEqual(codigo, 1, saida)
        self.assertIn("não encontrado", saida)

    def test_conjuntos_de_avaliacao_de_dados_nao_servem_como_perguntas_de_carga(self):
        for relativo in ("l100/avaliacao/teste.json", "l100/avaliacao-independente/x.json", "l200/avaliacao/chat-teste-v2.json",
                         "l400/avaliacao/comparacao-final-v1.json", "l400/avaliacao/qualquer.json"):
            with self.subTest(relativo):
                transporte = Transporte()
                codigo, saida, _ = self.rodar("--perguntas-arquivo", str(RAIZ / "dados" / relativo), transporte=transporte)
                self.assertEqual((codigo, transporte.chamadas), (1, []), saida)
                self.assertIn("conjuntos de avaliação", saida)
        codigo, saida, _ = self.rodar("--perguntas-arquivo", str(RAIZ / "dados" / "l400" / "carga" / "perguntas.json"))
        self.assertEqual(codigo, 1)
        self.assertIn("não encontrado", saida, "uma pasta de desenvolvimento em dados/ não é recusada por engano")

    def test_a_varredura_de_conteudo_ve_os_mesmos_conjuntos_que_o_teste_do_projeto_e_as_embutidas_passam(self):
        self.assertEqual(gc.pasta_de_dados(), RAIZ / "dados")
        existentes = perguntas_dos_conjuntos()
        self.assertEqual(sorted(gc.perguntas_de_avaliacao(gc.pasta_de_dados())), sorted(existentes))
        self.assertEqual(gc.conferir_com_os_conjuntos(gc.PERGUNTAS_EMBUTIDAS), (gc.CONFERENCIA_FEITA, len(existentes)))


class BloqueioDeConjuntosTests(BaseDoGerador):
    """Os conjuntos de avaliação de dados/ não servem para carga: recusa pelo caminho real (falha fechada) e pelo conteúdo.

    Tudo aqui usa uma pasta dados/ falsa, com perguntas sintéticas de TESTE criadas pelo próprio teste: nenhuma pergunta real de avaliação
    é copiada para o repositório.
    """

    FINAL_1 = "Pergunta sintética A do conjunto final de teste: qual é o prazo fictício para comunicar o evento ao produto de exemplo?"
    FINAL_2 = "Pergunta sintética B do conjunto final de teste: quem aciona a assistência fictícia depois do horário comercial?"
    AJUSTE = "Pergunta sintética C do conjunto de ajuste de teste: o que muda na franquia fictícia quando o prejuízo é pequeno?"
    LIVRE = "Pergunta sintética D de desenvolvimento, sem relação com os conjuntos de teste: como se descreve o produto de exemplo?"
    PASTA_RECUSADA = "conjuntos de avaliação de dados/ (inclusive o final do L400)"
    CONTEUDO_RECUSADO = "é igual a uma pergunta de um conjunto de avaliação"

    def setUp(self):
        super().setUp()
        self.dados = self.pasta / "dados"
        self.avaliacao = self.dados / "l400" / "avaliacao"
        self.desenvolvimento = self.dados / "l400" / "carga"
        for pasta in (self.avaliacao, self.desenvolvimento, self.dados / "l100"):
            pasta.mkdir(parents=True)
        (self.avaliacao / "final-sintetico.json").write_text(
            json.dumps({"perguntas": [{"id": "T1", "pergunta": self.FINAL_1}, {"id": "T2", "pergunta": self.FINAL_2}]}), encoding="utf-8")
        (self.dados / "l100" / "ajuste-sintetico.json").write_text(
            json.dumps({"conjunto": "ajuste", "itens": [{"pergunta": self.AJUSTE}]}), encoding="utf-8")
        self.lista_na_avaliacao = self.avaliacao / "lista-de-perguntas.json"  # uma lista comum, mas dentro de uma pasta de avaliação
        self.lista_na_avaliacao.write_text(json.dumps([self.LIVRE]), encoding="utf-8")
        self.fora = self.pasta / "fora"
        self.fora.mkdir()
        patcher = mock.patch.object(gc, "pasta_de_dados", return_value=self.dados)
        patcher.start()
        self.addCleanup(patcher.stop)

    def recusado(self, caminho, trecho):
        """Roda a CLI com o arquivo e confere: uso inválido, nenhum pedido, a mensagem esperada e nenhuma pergunta repetida."""
        transporte = Transporte()
        codigo, saida, _ = self.executar("--perguntas-arquivo", str(caminho), transporte=transporte)
        self.assertEqual((codigo, transporte.chamadas), (1, []), saida)
        self.assertIn(trecho, saida)
        self.assertNotIn("sentinela", saida)
        for texto in (self.FINAL_1, self.FINAL_2, self.AJUSTE, self.LIVRE):
            self.assertNotIn(texto, saida)
        return saida

    def test_arquivo_em_pasta_de_avaliacao_e_recusado_pelo_caminho_e_o_mesmo_conteudo_fora_dela_e_aceito(self):
        self.recusado(self.lista_na_avaliacao, self.PASTA_RECUSADA)
        livre = self.escrever_perguntas([self.LIVRE], "livre.json")
        codigo, saida, transporte = self.executar("--perguntas-arquivo", str(livre), "--pedidos", "2")
        self.assertEqual((codigo, len(transporte.chamadas)), (0, 2), saida)

    def test_copia_das_perguntas_de_avaliacao_em_outra_pasta_e_recusada_por_conteudo(self):
        for nome, pasta in (("fora de dados", self.pasta), ("em dados, fora das pastas de avaliação", self.desenvolvimento)):
            with self.subTest(nome):
                copia = pasta / f"{uuid.uuid4().hex}.json"
                copia.write_text(json.dumps([self.LIVRE, self.FINAL_2], ensure_ascii=False), encoding="utf-8")
                saida = self.recusado(copia, self.CONTEUDO_RECUSADO)
                self.assertIn("o item 2", saida)
                self.assertNotIn("o item 1", saida, "só as posições coincidentes são citadas, nunca os textos")
        ajuste = self.escrever_perguntas([self.AJUSTE], "ajuste.json")
        self.recusado(ajuste, self.CONTEUDO_RECUSADO)

    def test_a_copia_com_pequenos_ajustes_de_forma_continua_sendo_copia(self):
        sem_acentos = "".join(letra for letra in unicodedata.normalize("NFD", self.FINAL_1) if unicodedata.category(letra) != "Mn")
        variantes = {
            "caixa alta": self.FINAL_1.upper(),
            "sem acentos": sem_acentos,
            "sem pontuação": re.sub(r"[^\w\s]", "", self.FINAL_1),
            "espaços extras": "  " + self.FINAL_1.replace(" ", "   ") + "  ",
            "com ênfase de markdown": f"**{self.FINAL_1}**",
        }
        for nome, texto in variantes.items():
            with self.subTest(nome):
                self.recusado(self.escrever_perguntas([texto], f"{uuid.uuid4().hex}.json"), self.CONTEUDO_RECUSADO)

    def test_pergunta_parecida_mas_diferente_passa_e_o_plano_e_o_relatorio_dizem_que_a_conferencia_foi_feita(self):
        diferentes = self.escrever_perguntas([self.LIVRE, self.FINAL_1.replace("prazo", "limite"), self.FINAL_1[:50]], "diferentes.json")
        codigo, saida, _ = self.rodar("--perguntas-arquivo", str(diferentes))
        self.assertEqual(codigo, 0, saida)
        self.assertIn("Perguntas conferidas com as 3 de avaliação de dados/: nenhuma é igual", saida)
        self.assertNotIn("[AVISO] Sem a pasta dados/", saida)
        codigo, saida, _ = self.executar("--perguntas-arquivo", str(diferentes), "--pedidos", "3", "--relatorio", str(self.relatorio))
        self.assertEqual(codigo, 0, saida)
        self.assertEqual(self.ler_relatorio()["perguntas"], {"origem": "arquivo", "quantidade": 3, "conferencia_com_avaliacoes": "feita",
                                                             "comparadas_com_avaliacoes": 3})
        self.sem_sentinelas(saida + self.relatorio.read_text(encoding="utf-8"), self.LIVRE, self.FINAL_1, self.FINAL_2, self.AJUSTE)

    def test_caminho_com_prefixo_especial_do_windows_e_recusado_em_qualquer_sistema(self):
        for prefixo in ("\\\\?\\", "\\\\.\\", "//?/", "//./", "\\\\?\\UNC\\"):
            with self.subTest(prefixo=prefixo):
                caminho = prefixo + str(self.lista_na_avaliacao)
                self.recusado(caminho, "prefixo especial do Windows")
                with self.assertRaises(lab_comum.ErroLab):
                    gc.carregar_perguntas(caminho)
        self.recusado(self.lista_na_avaliacao, self.PASTA_RECUSADA)

    def test_o_prefixo_especial_que_o_sistema_devolver_ao_resolver_nao_esconde_a_pasta_de_avaliacao(self):
        real = os.path.realpath
        pasta_de_dados = os.path.normcase(real(self.dados))

        def prefixo_so_no_arquivo(caminho, *argumentos, **opcoes):
            resolvido = real(caminho, *argumentos, **opcoes)
            return resolvido if os.path.normcase(resolvido) == pasta_de_dados else "\\\\?\\" + resolvido

        with mock.patch.object(os.path, "realpath", side_effect=prefixo_so_no_arquivo):
            with self.assertRaises(lab_comum.ErroLab) as contexto:
                gc.carregar_perguntas(str(self.lista_na_avaliacao))
        self.assertIn(self.PASTA_RECUSADA, str(contexto.exception))

    @unittest.skipUnless(os.name == "nt", "só o Windows trata maiúsculas e minúsculas dos nomes de pasta como iguais")
    def test_a_comparacao_do_caminho_ignora_a_caixa_no_windows(self):
        real = os.path.realpath
        pasta_de_dados = os.path.normcase(real(self.dados))

        def em_caixa_alta_so_no_arquivo(caminho, *argumentos, **opcoes):
            resolvido = real(caminho, *argumentos, **opcoes)
            return resolvido if os.path.normcase(resolvido) == pasta_de_dados else resolvido.upper()

        with mock.patch.object(os.path, "realpath", side_effect=em_caixa_alta_so_no_arquivo):
            with self.assertRaises(lab_comum.ErroLab) as contexto:
                gc.carregar_perguntas(str(self.lista_na_avaliacao))
        self.assertIn(self.PASTA_RECUSADA, str(contexto.exception))

    def test_link_simbolico_para_a_pasta_ou_o_arquivo_de_avaliacao_e_recusado_pelo_caminho_real(self):
        elo_da_pasta, elo_do_arquivo = self.fora / "elo-da-pasta", self.fora / "elo-do-arquivo.json"
        try:
            os.symlink(self.avaliacao, elo_da_pasta, target_is_directory=True)
            os.symlink(self.lista_na_avaliacao, elo_do_arquivo)
        except (OSError, NotImplementedError, AttributeError) as erro:
            self.skipTest(f"este sistema não permite criar links simbólicos sem privilégio ({type(erro).__name__})")
        self.recusado(elo_da_pasta / "lista-de-perguntas.json", self.PASTA_RECUSADA)
        self.recusado(elo_do_arquivo, self.PASTA_RECUSADA)

    @unittest.skipUnless(sys.platform == "win32", "junções são um recurso do Windows")
    def test_juncao_do_windows_para_a_pasta_de_avaliacao_e_recusada_pelo_caminho_real(self):
        juncao = self.fora / "juncao"
        try:
            import _winapi
            _winapi.CreateJunction(str(self.avaliacao), str(juncao))
        except (ImportError, AttributeError, OSError) as erro:
            self.skipTest(f"não foi possível criar a junção ({type(erro).__name__})")
        self.addCleanup(os.rmdir, juncao)  # remove só a junção, nunca o que ela aponta
        self.recusado(juncao / "lista-de-perguntas.json", self.PASTA_RECUSADA)

    def test_erro_ao_resolver_o_caminho_recusa_em_vez_de_deixar_passar(self):
        arquivo = self.escrever_perguntas([self.LIVRE], "controle.json")
        for erro in (OSError("falha sentinela"), RuntimeError("laço sentinela"), ValueError("embedded null byte sentinela")):
            with self.subTest(tipo=type(erro).__name__):
                with mock.patch.object(os.path, "realpath", side_effect=erro):
                    self.recusado(arquivo, "não foi possível resolver o caminho")
                    with self.assertRaises(lab_comum.ErroLab):
                        gc.carregar_perguntas(str(arquivo))
        with self.assertRaises(lab_comum.ErroLab):
            gc.carregar_perguntas("a\x00b.json")
        codigo, saida, _ = self.rodar("--perguntas-arquivo", str(arquivo))
        self.assertEqual(codigo, 0, "o mesmo arquivo passa quando o caminho se resolve")

    def test_json_ilegivel_em_dados_recusa_em_vez_de_ignorar_a_conferencia(self):
        (self.dados / "l200").mkdir()
        (self.dados / "l200" / "quebrado.json").write_bytes(b"{ isto nao e json")
        arquivo = self.escrever_perguntas([self.LIVRE], "controle.json")
        self.recusado(arquivo, "não foi possível ler os conjuntos de avaliação de dados/")

    def test_sem_a_pasta_dados_ou_sem_conjuntos_a_conferencia_por_conteudo_e_indisponivel_e_o_plano_avisa(self):
        arquivo = self.escrever_perguntas([self.FINAL_1], "sem-como-saber.json")
        vazia = self.pasta / "vazia"
        vazia.mkdir()
        for nome, pasta in (("pasta ausente", self.pasta / "nao-existe"), ("pasta sem conjuntos", vazia)):
            with self.subTest(nome), mock.patch.object(gc, "pasta_de_dados", return_value=pasta):
                codigo, saida, _ = self.rodar("--perguntas-arquivo", str(arquivo))
                self.assertEqual(codigo, 0, saida)
                self.assertIn("[AVISO] Sem a pasta dados/", saida)
                self.assertIn("quem opera é responsável por não usar o conjunto final", saida)
                relatorio = self.pasta / f"{uuid.uuid4().hex}.json"
                codigo, saida, _ = self.executar("--perguntas-arquivo", str(arquivo), "--pedidos", "2", "--relatorio", str(relatorio))
                self.assertEqual(codigo, 0, saida)
                self.assertEqual(self.ler_relatorio(relatorio)["perguntas"], {"origem": "arquivo", "quantidade": 1,
                                                                              "conferencia_com_avaliacoes": "indisponivel",
                                                                              "comparadas_com_avaliacoes": 0})

    def test_as_perguntas_embutidas_nao_precisam_da_conferencia(self):
        with mock.patch.object(gc, "pasta_de_dados", side_effect=AssertionError("as embutidas não consultam dados/")):
            codigo, saida, _ = self.rodar()
        self.assertEqual(codigo, 0, saida)
        self.assertNotIn("Perguntas conferidas", saida)
        self.assertNotIn("[AVISO] Sem a pasta dados/", saida)


# --------------------------------------------------------------------------------------
# Classes de resultado e o que é analisado
# --------------------------------------------------------------------------------------

class ClassificacaoTests(BaseDoGerador):
    def test_cada_resposta_cai_em_uma_classe_do_vocabulario_fechado(self):
        invalido = json.dumps({"tipo": lp.DOCUMENTADA}).encode("utf-8")
        casos = (
            (resposta_ok(), gc.OK), (resposta_ok(tipo=lp.SEM_EVIDENCIA, evidencias=0), gc.OK), (resposta_ok(uso=None), gc.OK),
            (resposta_ok(simulada=True), gc.SIMULADA),
            (resposta_erro(lc.OCUPADO, 429), gc.OCUPADO),
            (resposta_erro(lc.OCUPADO, 503), gc.ERRO_PUBLICO),
            (resposta_erro(lc.INDISPONIVEL, 503), gc.ERRO_PUBLICO), (resposta_erro(lc.NAO_AUTORIZADO, 403), gc.ERRO_PUBLICO),
            (resposta_erro(lc.PERGUNTA_BLOQUEADA, 422), gc.ERRO_PUBLICO),
            (resposta_crua(429, b"<html>Too Many Requests</html>", "text/html"), gc.HTTP), (resposta_crua(502), gc.HTTP), (resposta_crua(401), gc.HTTP),
            (resposta_crua(204), gc.HTTP),
            (resposta_crua(302, b"", "text/html"), gc.REDIRECIONAMENTO), (resposta_crua(301), gc.REDIRECIONAMENTO),
            (gc.RespostaHttp(200, b"isto nao e json", "application/json"), gc.FORMATO_INVALIDO),
            (gc.RespostaHttp(200, corpo_200(), "text/html"), gc.FORMATO_INVALIDO),
            (gc.RespostaHttp(200, invalido, "application/json"), gc.FORMATO_INVALIDO),
            (gc.RespostaHttp(200, b"[]", "application/json"), gc.FORMATO_INVALIDO),
            (resposta_crua(999), gc.FORMATO_INVALIDO),
        )
        for resposta, esperada in casos:
            with self.subTest(status=resposta.status, esperada=esperada):
                resultado = gc.classificar(1, resposta, 12)
                self.assertEqual(resultado.classe, esperada)
                self.assertIn(resultado.classe, gc.CLASSES)
        ok = gc.classificar(1, resposta_ok(tipo=lp.DOCUMENTADA, evidencias=2, uso=(1, 2, 3, 4)), 12)
        self.assertEqual((ok.tipo, ok.evidencias, ok.http, ok.ms, ok.com_id_requisicao), ("documentada", 2, 200, 12, True))
        self.assertEqual(dict(ok.uso), {"tokens_embeddings": 1, "tokens_entrada": 2, "tokens_saida": 3, "tokens_raciocinio": 4})
        erro = gc.classificar(1, resposta_erro(lc.INDISPONIVEL, 503), 5)
        self.assertEqual((erro.erro_publico, erro.http, erro.tipo, erro.uso), ("indisponivel", 503, None, None))

    def test_falhas_de_transporte_viram_timeout_falha_de_rede_com_causa_ou_formato_invalido(self):
        esperadas = {"tempo_esgotado": (gc.TIMEOUT, None), "corpo_grande": (gc.FORMATO_INVALIDO, None), "dns": (gc.FALHA_DE_REDE, "dns"),
                     "conexao": (gc.FALHA_DE_REDE, "conexao"), "tls": (gc.FALHA_DE_REDE, "tls"),
                     "rotulo-desconhecido": (gc.FALHA_DE_REDE, "conexao")}
        for rotulo, (classe, causa) in esperadas.items():
            resultado = gc.resultado_de_falha(2, rotulo)
            self.assertEqual((resultado.classe, resultado.causa_de_rede, resultado.http, resultado.ms), (classe, causa, None, None), rotulo)

    def test_o_formato_publico_aceito_e_o_do_avaliador_de_chat_e_as_constantes_acompanham_o_chat(self):
        self.assertEqual((gc.CAMINHO_DA_API, gc.LIMITE_DA_RESPOSTA), (chat_web.ROTA_PERGUNTAR, ac.LIMITE_DA_RESPOSTA))
        self.assertEqual((gc.CAMPOS_DA_RESPOSTA, gc.CAMPOS_DA_EVIDENCIA, gc.CAMPOS_DO_USO),
                         (ac.CAMPOS_DA_RESPOSTA, ac.CAMPOS_DA_EVIDENCIA, ac.CAMPOS_DO_USO))
        base = json.loads(corpo_200(evidencias=1))
        uso, evidencia = base["uso"], base["evidencias"][0]

        def variante(**mudancas):
            return json.dumps({**base, **mudancas}).encode("utf-8")

        json_ = "application/json"
        validos = [(corpo_200(tipo=tipo, evidencias=quantidade, uso=consumo, simulada=simulada), json_)
                   for tipo in lp.TIPOS for quantidade in (0, 2) for consumo in (None, (1, 2, 3, 4)) for simulada in (False, True)]
        validos += [(corpo_200(), "application/json; charset=utf-8"), (corpo_200(), "APPLICATION/JSON")]
        invalidos = [
            (corpo_200(), "text/html"), (corpo_200(), ""), (b"nao e json", json_), (b"[]", json_), (b"\xff\xfe", json_),
            (json.dumps({chave: valor for chave, valor in base.items() if chave != "uso"}).encode("utf-8"), json_),
            (variante(extra="x"), json_), (variante(tipo="inventado"), json_), (variante(situacao="inventada"), json_),
            (variante(texto=3), json_), (variante(aviso=None), json_), (variante(simulada="sim"), json_), (variante(id=7), json_),
            (variante(id_requisicao=None), json_), (variante(aviso_simulacao=1), json_), (variante(evidencias="x"), json_),
            (variante(evidencias=[3]), json_), (variante(evidencias=[{"id": "x"}]), json_), (variante(evidencias=[{**evidencia, "id": 3}]), json_),
            (variante(uso=[1, 2, 3, 4]), json_), (variante(uso={"tokens_embeddings": 1}), json_),
            *((variante(uso={**uso, "tokens_saida": valor}), json_) for valor in (-1, True, 1.5, "7", 10**9 + 1, None)),
        ]
        for corpo, tipo in (*validos, *invalidos):
            with self.subTest(corpo=corpo[:60], tipo=tipo):
                try:
                    esperado = ac.interpretar_resposta(corpo, tipo)
                except ac.PayloadInvalido:
                    esperado = None
                try:
                    obtido = gc.interpretar_resposta(corpo, tipo)
                except gc.PayloadInvalido:
                    obtido = None
                self.assertEqual(obtido is None, esperado is None)
                if esperado is not None:
                    self.assertEqual((obtido.tipo, obtido.evidencias, obtido.uso, obtido.simulada),
                                     (esperado.tipo, esperado.citacoes, esperado.tokens, esperado.simulada))
        self.assertEqual(sum(1 for corpo, tipo in validos if gc.interpretar_resposta(corpo, tipo)), len(validos), "os válidos são aceitos")
        for corpo in (json.dumps({"erro": lc.OCUPADO}), json.dumps({"erro": "inventado"}), json.dumps({"erro": 3}), "[]", "{}", "nao e json",
                      json.dumps({"erro": lc.INDISPONIVEL, "mensagem": "x"})):
            self.assertEqual(gc.codigo_publico(corpo.encode("utf-8")), ac._codigo_do_chat(corpo.encode("utf-8")), corpo)

    def test_a_linha_de_resultado_conta_cada_classe_status_e_codigo_publico(self):
        respostas = {1: resposta_ok(), 2: resposta_erro(lc.OCUPADO, 429), 3: resposta_erro(lc.INDISPONIVEL, 503), 4: resposta_crua(502),
                     5: gc.FalhaDeTransporte("tempo_esgotado"), 6: gc.FalhaDeTransporte("dns"), 7: resposta_crua(302),
                     8: gc.RespostaHttp(200, b"nao e json", "application/json"), 9: resposta_ok(simulada=True)}
        transporte = Transporte(lambda numero, pergunta: respostas[numero])
        codigo, saida, _ = self.executar("--pedidos", "9", "--concorrencia", "1", "--falhas-seguidas", "10", transporte=transporte)
        self.assertEqual(codigo, 3, saida)
        resultado = linha_do_resultado(saida)
        self.assertEqual(resultado["classes"], dict.fromkeys(gc.CLASSES, 1))
        self.assertEqual(resultado["erros_publicos"], {"indisponivel": 1})
        self.assertEqual(resultado["codigos_http"], {"200": 3, "302": 1, "429": 1, "502": 1, "503": 1})
        self.assertEqual(resultado["causas_de_rede"], {"dns": 1})
        self.assertEqual((resultado["divergentes"], resultado["esperado"]), (8, ["ok"]))
        self.assertEqual((resultado["status"], resultado["interrupcao"]), ("concluido", None))

    def test_admissao_ocupado_e_divergencia_por_padrao_e_aceito_com_esperar(self):
        def responder(numero, pergunta):
            return resposta_erro(lc.OCUPADO, 429) if numero in (2, 4) else resposta_ok()

        codigo, saida, _ = self.executar("--concorrencia", "1", transporte=Transporte(responder))
        resultado = linha_do_resultado(saida)
        self.assertEqual((codigo, resultado["divergentes"], resultado["classes"]["ocupado"]), (3, 2, 2), saida)
        self.assertEqual(resultado["pedidos"]["enviados"], 6, "dois ocupados não seguidos não param a carga")
        codigo, saida, _ = self.executar("--concorrencia", "1", "--esperar", "ok,ocupado", transporte=Transporte(responder))
        resultado = linha_do_resultado(saida)
        self.assertEqual((codigo, resultado["divergentes"], resultado["classes"]["ocupado"], resultado["codigos_http"]), (0, 0, 2, {"200": 4, "429": 2}), saida)
        self.assertIn("[ESPERADO] pedido 2/6: ocupado (HTTP 429", saida, "uma recusa esperada não é rotulada como falha")
        self.assertIn("[OK] pedido 1/6: ok (HTTP 200", saida)

    def test_conteudo_da_resposta_e_descartado_so_tipo_fontes_e_uso_entram_na_analise(self):
        respostas = {1: resposta_ok(tipo=lp.DOCUMENTADA, evidencias=2), 2: resposta_ok(tipo=lp.DOCUMENTADA, evidencias=1),
                     3: resposta_ok(tipo=lp.SEM_EVIDENCIA, evidencias=0), 4: resposta_ok(tipo=lp.DOCUMENTADA, evidencias=1)}
        codigo, saida, _ = self.executar("--pedidos", "4", "--relatorio", str(self.relatorio), transporte=Transporte(lambda n, p: respostas[n]))
        self.assertEqual(codigo, 0, saida)
        resultado = linha_do_resultado(saida)
        self.assertEqual(resultado["tipos"], {"documentada": 3, "sem_evidencia": 1})
        self.assertEqual(resultado["respostas_ok_com_evidencia"], 3)
        self.sem_sentinelas(saida + self.relatorio.read_text(encoding="utf-8"))

    def test_so_a_presenca_do_id_da_requisicao_e_contada(self):
        transporte = Transporte(lambda numero, pergunta: resposta_ok(com_id=numero % 2 == 0))
        codigo, saida, _ = self.executar("--pedidos", "6", "--relatorio", str(self.relatorio), transporte=transporte)
        self.assertEqual(codigo, 0, saida)
        self.assertEqual(linha_do_resultado(saida)["respostas_com_id_requisicao"], 3)
        self.assertEqual(sorted(item["com_id_requisicao"] for item in self.ler_relatorio()["pedidos_detalhe"]), [False] * 3 + [True] * 3)

    def test_uso_conhecido_soma_so_o_informado_e_o_resto_fica_desconhecido_nunca_zero(self):
        respostas = {1: resposta_ok(uso=(1, 10, 100, 1000)), 2: resposta_ok(uso=None), 3: resposta_ok(uso=(2, 20, 200, 2000)),
                     4: resposta_erro(lc.INDISPONIVEL, 503)}
        codigo, saida, _ = self.executar("--pedidos", "4", "--concorrencia", "1", "--falhas-seguidas", "10",
                                         transporte=Transporte(lambda n, p: respostas[n]))
        self.assertEqual(codigo, 3, saida)
        uso = linha_do_resultado(saida)["uso"]
        self.assertEqual(uso["soma_do_uso_informado"], {"tokens_embeddings": 3, "tokens_entrada": 30, "tokens_raciocinio": 3000, "tokens_saida": 300})
        self.assertEqual((uso["pedidos_com_uso_informado"], uso["pedidos_sem_uso_informado"]), (2, 2))
        self.assertIn("desconhecido", uso["observacao"])
        codigo, saida, _ = self.executar("--pedidos", "2", transporte=Transporte(lambda n, p: resposta_ok(uso=None)))
        self.assertIsNone(linha_do_resultado(saida)["uso"]["soma_do_uso_informado"], "sem uso informado a soma é desconhecida, não zero")

    def test_latencias_minima_mediana_p95_e_maxima_em_ms_com_o_aviso_de_amostra_pequena(self):
        relogio, duracoes = Relogio(), [0.5, 0.1, 0.3, 0.2, 0.6, 0.4]
        transporte = Transporte()
        transporte.durante = lambda numero: relogio.avancar(duracoes[numero - 1])
        codigo, saida, _ = self.executar("--concorrencia", "1", transporte=transporte, relogio=relogio)
        self.assertEqual(codigo, 0, saida)
        resultado = linha_do_resultado(saida)
        esperada = {"n": 6, "minima": 100, "mediana": 300, "p95": 600, "maxima": 600}
        self.assertEqual((resultado["latencia_ms_ok"], resultado["latencia_ms_respostas_http"]), (esperada, esperada))
        self.assertIn("não são percentis de produção", resultado["aviso_latencia"])
        self.assertEqual(resultado["tempo_decorrido_s"], 2.1)
        self.assertEqual(gc.resumir_latencia([]), {"n": 0, "minima": None, "mediana": None, "p95": None, "maxima": None})
        self.assertEqual(gc.resumir_latencia([7]), {"n": 1, "minima": 7, "mediana": 7, "p95": 7, "maxima": 7})
        self.assertEqual(gc.resumir_latencia(list(range(1, 101)))["p95"], 95)

    def test_latencia_de_ok_nao_mistura_com_a_resposta_imediata_de_ocupado(self):
        relogio = Relogio()
        duracoes = {1: 2.0, 2: 0.01, 3: 3.0, 4: 0.02}
        transporte = Transporte(lambda numero, pergunta: resposta_erro(lc.OCUPADO, 429) if numero in (2, 4) else resposta_ok())
        transporte.durante = lambda numero: relogio.avancar(duracoes[numero])
        codigo, saida, _ = self.executar("--pedidos", "4", "--concorrencia", "1", "--esperar", "ok,ocupado", transporte=transporte, relogio=relogio)
        self.assertEqual(codigo, 0, saida)
        resultado = linha_do_resultado(saida)
        self.assertEqual((resultado["latencia_ms_ok"]["minima"], resultado["latencia_ms_ok"]["maxima"]), (2000, 3000))
        self.assertEqual((resultado["latencia_ms_respostas_http"]["minima"], resultado["latencia_ms_respostas_http"]["n"]), (10, 4))


# --------------------------------------------------------------------------------------
# Execução concorrente: teto, parada, tempo, sem retry e defeitos
# --------------------------------------------------------------------------------------

class ExecucaoTests(BaseDoGerador):
    def test_pedidos_simultaneos_nunca_passam_do_teto_de_concorrencia_mas_chegam_a_ele(self):
        barreira = threading.Barrier(4, timeout=5)

        def durante(numero):
            if numero <= 4:
                barreira.wait()  # os quatro primeiros só seguem juntos: prova que há quatro em andamento
            else:
                time.sleep(0.002)

        transporte = Transporte()
        transporte.durante = durante
        codigo, saida, _ = self.executar("--pedidos", "20", "--concorrencia", "4", transporte=transporte)
        self.assertEqual(codigo, 0, saida)
        self.assertEqual((transporte.maximo, len(transporte.chamadas)), (4, 20))
        self.assertEqual(linha_do_resultado(saida)["pedidos"], {"planejados": 20, "enviados": 20, "com_resultado": 20, "sem_resultado": 0,
                                                                "nao_enviados": 0})

    def test_no_teto_de_8_e_com_concorrencia_1_o_maximo_observado_e_respeitado(self):
        for concorrencia in (1, 8):
            with self.subTest(concorrencia=concorrencia):
                transporte = Transporte(duracao=0.003)
                codigo, saida, _ = self.executar("--pedidos", "24", "--concorrencia", str(concorrencia), transporte=transporte)
                self.assertEqual(codigo, 0, saida)
                self.assertLessEqual(transporte.maximo, concorrencia)
                self.assertEqual(len(transporte.chamadas), 24)

    def test_parada_apos_falhas_seguidas_nao_envia_o_resto_e_nunca_repete_um_pedido(self):
        for seguidas, esperados in (("3", 3), ("1", 1), ("5", 5)):
            with self.subTest(seguidas=seguidas):
                transporte = Transporte(lambda numero, pergunta: resposta_erro(lc.INDISPONIVEL, 503))
                codigo, saida, _ = self.executar("--pedidos", "20", "--concorrencia", "1", "--falhas-seguidas", seguidas, transporte=transporte)
                self.assertEqual(codigo, 3, saida)
                self.assertEqual(len(transporte.chamadas), esperados, "cada pedido é enviado uma vez só: nenhum retry")
                resultado = linha_do_resultado(saida)
                self.assertEqual((resultado["interrupcao"], resultado["status"]), ("falhas_seguidas", "interrompido"))
                self.assertEqual((resultado["pedidos"]["enviados"], resultado["pedidos"]["nao_enviados"]), (esperados, 20 - esperados))

    def test_com_concorrencia_a_parada_deixa_terminar_so_o_que_ja_estava_em_andamento(self):
        transporte = Transporte(lambda numero, pergunta: resposta_erro(lc.INDISPONIVEL, 503), duracao=0.01)
        codigo, saida, _ = self.executar("--pedidos", "40", "--concorrencia", "4", "--falhas-seguidas", "3", transporte=transporte)
        self.assertEqual(codigo, 3, saida)
        self.assertGreaterEqual(len(transporte.chamadas), 3)
        self.assertLessEqual(len(transporte.chamadas), 3 + 4 - 1, "três falhas e, no máximo, os outros três já em andamento")
        resultado = linha_do_resultado(saida)
        self.assertEqual(resultado["interrupcao"], "falhas_seguidas")
        self.assertEqual(resultado["pedidos"]["enviados"], len(transporte.chamadas))

    def test_uma_resposta_esperada_zera_a_contagem_de_falhas_seguidas(self):
        transporte = Transporte(lambda numero, pergunta: resposta_ok() if numero % 3 == 0 else resposta_erro(lc.INDISPONIVEL, 503))
        codigo, saida, _ = self.executar("--pedidos", "9", "--concorrencia", "1", transporte=transporte)
        self.assertEqual(codigo, 3, saida)
        resultado = linha_do_resultado(saida)
        self.assertEqual((resultado["pedidos"]["enviados"], resultado["status"], resultado["divergentes"]), (9, "concluido", 6))

    def test_so_o_que_esta_fora_do_esperado_conta_para_a_parada(self):
        transporte = Transporte(lambda numero, pergunta: resposta_erro(lc.OCUPADO, 429))
        codigo, saida, _ = self.executar("--pedidos", "10", "--concorrencia", "1", "--esperar", "ok,ocupado", transporte=transporte)
        self.assertEqual((codigo, len(transporte.chamadas)), (0, 10), saida)

    def test_so_falhas_de_rede_sem_nenhuma_resposta_http_saem_com_2_e_orientam(self):
        transporte = Transporte(lambda numero, pergunta: gc.FalhaDeTransporte("dns"))
        codigo, saida, _ = self.executar("--pedidos", "10", "--concorrencia", "1", transporte=transporte)
        self.assertEqual((codigo, len(transporte.chamadas)), (2, 3), saida)
        self.assertIn("Nenhuma resposta HTTP", saida)
        resultado = linha_do_resultado(saida)
        self.assertEqual((resultado["classes"]["falha_de_rede"], resultado["causas_de_rede"], resultado["interrupcao"]), (3, {"dns": 3}, "falhas_seguidas"))
        codigo, saida, _ = self.executar("--pedidos", "2", "--concorrencia", "1", transporte=Transporte(lambda n, p: gc.FalhaDeTransporte("tempo_esgotado")))
        self.assertEqual(codigo, 2, "dois pedidos, todos sem resposta, mesmo abaixo do limite de falhas seguidas")

    def test_falhas_de_rede_depois_de_respostas_http_sao_divergencia_e_nao_falta_de_acesso(self):
        transporte = Transporte(lambda numero, pergunta: resposta_ok() if numero == 1 else gc.FalhaDeTransporte("conexao"))
        codigo, saida, _ = self.executar("--pedidos", "6", "--concorrencia", "1", transporte=transporte)
        self.assertEqual(codigo, 3, saida)

    def test_autenticacao_recusada_sai_com_2_inclusive_sem_corpo_publico(self):
        for resposta in (resposta_crua(401), resposta_erro(lc.NAO_AUTORIZADO, 403), resposta_erro(lc.NAO_AUTENTICADO, 401)):
            with self.subTest(status=resposta.status):
                transporte = Transporte(lambda numero, pergunta, resposta=resposta: resposta)
                codigo, saida, _ = self.executar("--pedidos", "6", "--concorrencia", "1", transporte=transporte)
                self.assertEqual((codigo, len(transporte.chamadas)), (2, 3), saida)
                self.assertEqual(linha_do_resultado(saida)["acessos_recusados"], 3)
                self.assertIn("recusou a autenticação", saida)

    def test_limite_de_tempo_total_para_de_enviar_e_limita_o_prazo_do_ultimo_pedido(self):
        relogio, prazos = Relogio(), []

        def transporte(url, corpo, cabecalhos, timeout):
            """Cada pedido leva 60 s, mas nunca passa do prazo que recebeu, como um transporte de verdade."""
            prazos.append(timeout)
            relogio.avancar(min(60, timeout))
            if timeout <= 60:
                raise gc.FalhaDeTransporte("tempo_esgotado")
            return resposta_ok()

        codigo, saida, _ = self.executar("--pedidos", "6", "--concorrencia", "1", "--tempo-maximo", "100", "--tempo-por-pedido", "120",
                                         "--falhas-seguidas", "10", transporte=transporte, relogio=relogio)
        self.assertEqual(codigo, 3, saida)
        self.assertEqual(prazos, [100, 40], "o prazo de cada pedido nunca passa do tempo que resta")
        resultado = linha_do_resultado(saida)
        self.assertEqual(resultado["interrupcao"], "tempo_maximo")
        self.assertEqual((resultado["pedidos"]["enviados"], resultado["pedidos"]["nao_enviados"]), (2, 4))
        self.assertEqual((resultado["classes"]["ok"], resultado["classes"]["timeout"]), (1, 1))
        self.assertEqual(resultado["tempo_decorrido_s"], 100.0)
        self.assertIn("[INTERROMPIDA]", saida)

    def test_prazo_de_cada_pedido_e_o_da_opcao_enquanto_ha_tempo(self):
        codigo, saida, transporte = self.executar("--pedidos", "3", "--tempo-por-pedido", "45.5")
        self.assertEqual(codigo, 0, saida)
        self.assertEqual({chamada["timeout"] for chamada in transporte.chamadas}, {45.5})

    def test_um_pedido_preso_alem_do_teto_nao_segura_o_programa(self):
        relogio, liberar = Relogio(), threading.Event()
        self.addCleanup(liberar.set)

        def durante(numero):
            relogio.avancar(1000)  # o relógio passa do tempo máximo e da folga enquanto o pedido está preso
            liberar.wait(5)

        transporte = Transporte()
        transporte.durante = durante
        inicio = time.monotonic()
        codigo, saida, _ = self.executar("--pedidos", "3", "--concorrencia", "1", "--tempo-maximo", "10", transporte=transporte, relogio=relogio)
        self.assertLess(time.monotonic() - inicio, 3, "o programa não espera um pedido além do teto")
        self.assertEqual(codigo, 3, saida)
        resultado = linha_do_resultado(saida)
        self.assertEqual(resultado["interrupcao"], "tempo_maximo")
        self.assertEqual((resultado["pedidos"]["enviados"], resultado["pedidos"]["com_resultado"], resultado["pedidos"]["sem_resultado"]), (1, 0, 1))
        self.assertIn("ainda podem consumir tokens", saida)

    def executar_direto(self, transporte, relogio, **mudancas):
        """A `Execucao` sem a CLI, para olhar o estado depois de `executar` devolver e depois de os pedidos abandonados terminarem."""
        plano = {"pedidos": 3, "concorrencia": 1, "tempo_maximo": 10.0, "tempo_por_pedido": 5.0, "falhas_seguidas": 3, "esperar": frozenset({gc.OK}),
                 "perguntas": ("Pergunta sintética de teste?",), "origem_das_perguntas": "embutidas", **mudancas}
        antes, registrados = set(threading.enumerate()), []
        execucao = gc.Execucao(gc.Plano(**plano), gc.validar_url(URL), transporte, relogio, registrar=registrados.append)
        execucao.executar(TOKEN)
        return execucao, registrados, set(threading.enumerate()) - antes

    def test_pedido_ja_enviado_ganha_a_folga_de_encerramento_depois_do_tempo_maximo_e_nem_um_segundo_a_mais(self):
        for sobra, termina in ((-1, True), (1, False)):
            with self.subTest(sobra_sobre_a_folga_s=sobra):
                relogio = Relogio()

                def transporte(url, corpo, cabecalhos, timeout):
                    relogio.avancar(10 + gc.FOLGA_DE_ENCERRAMENTO + sobra)  # o relógio salta; o pedido leva 0,3 s de verdade
                    time.sleep(0.3)
                    return resposta_ok()

                execucao, _, trabalhadores = self.executar_direto(transporte, relogio, tempo_maximo=10.0)
                self.assertEqual(len(execucao.resultados), 1 if termina else 0,
                                 "dentro da folga o pedido enviado termina e é contado; passada a folga o gerador desiste dele")
                self.assertEqual(execucao.interrupcao, gc.MOTIVO_TEMPO)
                for trabalhador in trabalhadores:
                    trabalhador.join(5)

    def test_resultado_tardio_de_um_pedido_abandonado_nao_muda_nada_depois_do_encerramento(self):
        relogio, solto = Relogio(), threading.Event()
        self.addCleanup(solto.set)

        def transporte(url, corpo, cabecalhos, timeout):
            relogio.avancar(1000)  # passa do tempo máximo e da folga: o gerador desiste deste pedido
            solto.wait(5)
            return resposta_erro(lc.INDISPONIVEL, 503)  # fora do esperado: contaria para a parada se entrasse

        execucao, registrados, trabalhadores = self.executar_direto(transporte, relogio)
        self.assertTrue(execucao.encerrada)
        self.assertEqual((execucao.resultados, execucao.interrupcao), ([], gc.MOTIVO_TEMPO))
        self.assertTrue(trabalhadores, "o pedido abandonado ainda está em andamento quando a execução termina")
        solto.set()
        for trabalhador in trabalhadores:
            trabalhador.join(5)
            self.assertFalse(trabalhador.is_alive())
        self.assertEqual((execucao.resultados, registrados, execucao.seguidas), ([], [], 0), "o resultado tardio é descartado")
        self.assertEqual(execucao.proximo, 1, "o pedido abandonado continua contado como enviado")

    def test_defeito_do_gerador_sai_com_4_grava_o_relatorio_e_so_mostra_o_nome_do_tipo(self):
        transporte = Transporte(lambda numero, pergunta: RuntimeError("detalhe interno sentinela"))
        codigo, saida, _ = self.executar("--pedidos", "10", "--concorrencia", "1", "--relatorio", str(self.relatorio), transporte=transporte)
        self.assertEqual((codigo, len(transporte.chamadas)), (4, 1), saida)
        self.assertIn("RuntimeError", saida)
        self.assertNotIn("sentinela", saida)
        resultado = linha_do_resultado(saida)
        self.assertEqual((resultado["interrupcao"], resultado["codigo_de_saida"]), ("defeito_do_gerador", 4))
        self.assertEqual(self.ler_relatorio()["status"], "interrompido")

    def test_ctrl_c_para_os_pedidos_novos_espera_os_enviados_e_sai_com_3(self):
        iniciado = threading.Event()
        transporte = Transporte(duracao=0.05)
        transporte.durante = lambda numero: iniciado.set()
        original, chamadas = gc.Execucao._aguardar, []

        def aguardar(execucao):
            chamadas.append(1)
            if len(chamadas) == 1:
                iniciado.wait(5)
                raise KeyboardInterrupt
            return original(execucao)

        with mock.patch.object(gc.Execucao, "_aguardar", aguardar):
            codigo, saida, _ = self.executar("--pedidos", "30", "--concorrencia", "2", "--relatorio", str(self.relatorio), transporte=transporte)
        self.assertEqual(codigo, 3, saida)
        resultado = linha_do_resultado(saida)
        self.assertEqual(resultado["interrupcao"], "cancelado")
        self.assertLess(resultado["pedidos"]["enviados"], 30)
        self.assertEqual(resultado["pedidos"]["com_resultado"], resultado["pedidos"]["enviados"], "os já enviados terminam e são contados")
        self.assertIn("Aguardando os já enviados", saida)
        self.assertEqual(self.ler_relatorio()["interrupcao"], "cancelado")

    def test_ctrl_c_fora_da_execucao_sai_com_3_sem_traceback(self):
        with mock.patch.object(gc, "validar_argumentos", side_effect=KeyboardInterrupt):
            codigo, saida, _ = self.executar()
        self.assertEqual(codigo, 3, saida)
        self.assertIn("[INTERROMPIDA]", saida)
        self.assertNotIn("Traceback", saida)

    def test_cada_pedido_e_um_unico_envio_mesmo_com_falhas_de_todo_tipo(self):
        respostas = [resposta_erro(lc.INDISPONIVEL, 503), gc.FalhaDeTransporte("tempo_esgotado"), resposta_crua(502), resposta_ok(),
                     resposta_erro(lc.OCUPADO, 429), gc.FalhaDeTransporte("tls")]
        transporte = Transporte(lambda numero, pergunta: respostas[numero - 1])
        codigo, saida, _ = self.executar("--pedidos", "6", "--concorrencia", "1", "--falhas-seguidas", "10", transporte=transporte)
        self.assertEqual((codigo, len(transporte.chamadas)), (3, 6), saida)


# --------------------------------------------------------------------------------------
# Resultado, relatório e ajuda
# --------------------------------------------------------------------------------------

class ResultadoERelatorioTests(BaseDoGerador):
    def test_a_ultima_linha_e_o_resultado_em_json_ascii_com_os_campos_e_o_limite_de_carga_pequena(self):
        relogio = Relogio()
        transporte = Transporte()
        transporte.durante = lambda numero: relogio.avancar(0.25)
        codigo, saida, _ = self.executar("--concorrencia", "1", transporte=transporte, relogio=relogio)
        self.assertEqual(codigo, 0, saida)
        ultima = saida.rstrip().splitlines()[-1]
        self.assertTrue(ultima.startswith("L400_CARGA_RESULTADO="))
        self.assertTrue(ultima.isascii(), "uma linha de log sem problemas de codificação")
        resultado = linha_do_resultado(saida)
        self.assertEqual(resultado["pedidos"], {"planejados": 6, "enviados": 6, "com_resultado": 6, "sem_resultado": 0, "nao_enviados": 0})
        self.assertEqual((resultado["concorrencia"], resultado["status"], resultado["interrupcao"], resultado["codigo_de_saida"]), (1, "concluido", None, 0))
        self.assertEqual(resultado["classes"]["ok"], 6)
        self.assertEqual(set(resultado["classes"]), set(gc.CLASSES))
        self.assertEqual(resultado["limite"], "carga_pequena_nao_capacidade_producao")
        self.assertEqual(resultado["limites"], {"tempo_maximo_s": 300.0, "folga_de_encerramento_s": gc.FOLGA_DE_ENCERRAMENTO, "tempo_por_pedido_s": 120.0,
                                                "falhas_seguidas": 3, "resposta_maxima_bytes": gc.LIMITE_DA_RESPOSTA, "tentativas_automaticas": 0})
        self.assertEqual(resultado["tempo_decorrido_s"], 1.5, "seis pedidos de 0,25 s em sequência")
        for chave in ("latencia_ms_ok", "latencia_ms_respostas_http", "aviso_latencia", "uso", "erros_publicos", "codigos_http", "esperado"):
            self.assertIn(chave, resultado)
        self.assertIn("[OK] pedido 1/6: ok (HTTP 200", saida)
        self.assertLess(len(ultima), 4000, "cabe em uma linha de log")

    def test_o_relogio_padrao_mede_com_resolucao_de_submilissegundo_tambem_no_windows(self):
        with mock.patch.object(gc, "executar_carga", return_value=0) as executar_carga:
            codigo, saida, _ = self.executar()
        self.assertEqual(codigo, 0, saida)
        self.assertIs(executar_carga.call_args.args[3], time.perf_counter, "time.monotonic do Windows só avança de 15 em 15 ms")

    def test_relatorio_e_reservado_antes_da_rede_e_traz_o_detalhe_de_cada_pedido_sem_texto(self):
        existia = []
        transporte = Transporte(lambda numero, pergunta: resposta_ok())
        transporte.durante = lambda numero: existia.append(json.loads(self.relatorio.read_text(encoding="utf-8")).get("status"))
        codigo, saida, _ = self.executar("--pedidos", "3", "--relatorio", str(self.relatorio), transporte=transporte)
        self.assertEqual(codigo, 0, saida)
        self.assertEqual(existia, ["em_andamento"] * 3, "o arquivo existe, com um marcador, antes do primeiro pedido")
        relatorio = self.ler_relatorio()
        self.assertEqual((relatorio["status"], relatorio["relatorio"], relatorio["esquema"]), ("concluido", "carga_l400", 1))
        self.assertEqual([item["posicao"] for item in relatorio["pedidos_detalhe"]], [1, 2, 3])
        detalhe = relatorio["pedidos_detalhe"][0]
        self.assertEqual(set(detalhe), {"posicao", "classe", "esperado", "http", "ms", "erro_publico", "causa_de_rede", "tipo", "evidencias", "uso",
                                        "com_id_requisicao"})
        self.assertEqual((detalhe["classe"], detalhe["esperado"], detalhe["http"], detalhe["tipo"]), ("ok", True, 200, "documentada"))
        self.assertEqual(relatorio["destino"], {"esquema": "https", "caminho": "/api/perguntar"})
        self.assertEqual(relatorio["perguntas"], {"origem": "embutidas", "quantidade": len(gc.PERGUNTAS_EMBUTIDAS),
                                                  "conferencia_com_avaliacoes": "nao_se_aplica", "comparadas_com_avaliacoes": 0})
        self.assertEqual(relatorio["tetos"], {"pedidos": 50, "concorrencia": 8, "tempo_maximo_s": 600.0, "tempo_por_pedido_s": 300.0, "falhas_seguidas": 10})
        arquivo = Path(gc.__file__).resolve().read_bytes()
        self.assertEqual(relatorio["gerador"]["sha256_bytes_brutos"], gc.hashes_do_conteudo(arquivo)["sha256_bytes_brutos"])
        self.assertTrue(relatorio["inicio_utc"] and relatorio["fim_utc"])
        self.assertEqual(len(relatorio["avisos"]), 3)
        self.sem_sentinelas(saida + self.relatorio.read_text(encoding="utf-8"))

    def test_relatorio_existente_ou_em_pasta_ausente_para_antes_da_rede_e_nunca_e_sobrescrito(self):
        self.relatorio.write_text("medição anterior", encoding="utf-8")
        transporte = Transporte()
        codigo, saida, _ = self.executar("--relatorio", str(self.relatorio), transporte=transporte)
        self.assertEqual((codigo, transporte.chamadas), (1, []), saida)
        self.assertEqual(self.relatorio.read_text(encoding="utf-8"), "medição anterior")
        self.assertIn("nunca sobrescreve", saida)
        codigo, saida, _ = self.executar("--relatorio", str(self.pasta / "ausente" / "r.json"), transporte=transporte)
        self.assertEqual((codigo, transporte.chamadas), (1, []), saida)
        self.assertIn("pasta não existe", saida)
        with self.assertRaises(lab_comum.ErroLab):
            gc.reservar_relatorio(self.relatorio)
        self.assertEqual(self.relatorio.read_text(encoding="utf-8"), "medição anterior", "criar em modo exclusivo não trunca o que existe")

    @unittest.skipIf(os.name == "nt", "o Windows não aplica permissões POSIX")
    def test_relatorio_novo_e_legivel_so_pelo_dono_em_sistemas_posix(self):
        codigo, saida, _ = self.executar("--relatorio", str(self.relatorio))
        self.assertEqual(codigo, 0, saida)
        self.assertEqual(stat.S_IMODE(self.relatorio.stat().st_mode), 0o600)

    def test_falha_ao_gravar_o_relatorio_final_ainda_mostra_o_resultado_e_sai_com_4(self):
        with mock.patch.object(gc, "gravar_relatorio", side_effect=[None, OSError("disco cheio sentinela")]):
            codigo, saida, _ = self.executar("--relatorio", str(self.relatorio))
        self.assertEqual(codigo, 4, saida)
        self.assertEqual(linha_do_resultado(saida)["codigo_de_saida"], 0, "o resultado já foi impresso")
        self.assertIn("não foi possível gravar o relatório final", saida)
        self.assertNotIn("sentinela", saida)

    def conferir_que_o_resultado_e_a_ultima_linha(self, saida, erro, ordem, trecho_do_erro):
        linhas = saida.splitlines()
        self.assertTrue(linhas[-1].startswith(gc.PREFIXO_DO_RESULTADO), "a última linha do stdout é a do resultado")
        self.assertEqual(sum(linha.startswith(gc.PREFIXO_DO_RESULTADO) for linha in linhas), 1)
        self.assertNotIn("[ERRO]", saida, "os erros vão para o stderr, que é outro fluxo")
        self.assertIn("[ERRO]", erro)
        self.assertIn(trecho_do_erro, erro)
        juntas = ordem.splitlines()
        self.assertTrue(juntas[-1].startswith(gc.PREFIXO_DO_RESULTADO), "com os dois fluxos no mesmo destino, o resultado continua por último")
        self.assertTrue(any("[ERRO]" in linha for linha in juntas[:-1]), "e os erros saem antes dele")
        self.assertNotIn("sentinela", ordem)

    def test_com_falha_ao_gravar_o_relatorio_a_linha_de_resultado_e_a_ultima_do_stdout_e_o_erro_sai_antes_no_stderr(self):
        with mock.patch.object(gc, "gravar_relatorio", side_effect=[None, OSError("disco cheio sentinela")]):
            codigo, saida, erro, ordem = self.rodar_separado("--executar", "--confirmo-consumo", "--relatorio", str(self.relatorio))
        self.assertEqual(codigo, 4, ordem)
        self.conferir_que_o_resultado_e_a_ultima_linha(saida, erro, ordem, "não foi possível gravar o relatório final")

    def test_com_defeito_do_gerador_a_linha_de_resultado_e_a_ultima_do_stdout_e_o_erro_sai_antes_no_stderr(self):
        transporte = Transporte(lambda numero, pergunta: RuntimeError("detalhe interno sentinela"))
        codigo, saida, erro, ordem = self.rodar_separado("--executar", "--confirmo-consumo", "--concorrencia", "1", transporte=transporte)
        self.assertEqual(codigo, 4, ordem)
        self.conferir_que_o_resultado_e_a_ultima_linha(saida, erro, ordem, "Defeito do gerador (RuntimeError)")

    def test_com_defeito_e_falha_ao_gravar_juntos_os_dois_erros_saem_antes_da_linha_de_resultado(self):
        transporte = Transporte(lambda numero, pergunta: RuntimeError("detalhe interno sentinela"))
        with mock.patch.object(gc, "gravar_relatorio", side_effect=[None, OSError("disco cheio sentinela")]):
            codigo, saida, erro, ordem = self.rodar_separado("--executar", "--confirmo-consumo", "--concorrencia", "1", "--relatorio",
                                                             str(self.relatorio), transporte=transporte)
        self.assertEqual(codigo, 4, ordem)
        self.conferir_que_o_resultado_e_a_ultima_linha(saida, erro, ordem, "Defeito do gerador (RuntimeError)")
        self.assertIn("não foi possível gravar o relatório final", erro)

    def test_sem_erro_o_stderr_fica_vazio_e_a_linha_de_resultado_continua_por_ultimo(self):
        codigo, saida, erro, ordem = self.rodar_separado("--executar", "--confirmo-consumo", "--relatorio", str(self.relatorio))
        self.assertEqual((codigo, erro), (0, ""), ordem)
        self.assertTrue(saida.splitlines()[-1].startswith(gc.PREFIXO_DO_RESULTADO))

    def test_nem_token_nem_endereco_nem_perguntas_nem_textos_aparecem_em_nenhum_cenario(self):
        arquivo = self.escrever_perguntas([PERGUNTA_DO_ARQUIVO, OUTRA_PERGUNTA])
        cenarios = {
            "tudo certo": lambda numero, pergunta: resposta_ok(),
            "erros públicos e http": lambda numero, pergunta: resposta_erro(lc.INDISPONIVEL, 503) if numero % 2 else resposta_crua(502, TOKEN.encode()),
            "falhas de rede": lambda numero, pergunta: gc.FalhaDeTransporte("tls"),
            "corpo com o token": lambda numero, pergunta: gc.RespostaHttp(200, f'{{"texto": "{TOKEN} {URL}"}}'.encode(), "application/json"),
        }
        for nome, responder in cenarios.items():
            with self.subTest(nome):
                relatorio = self.pasta / f"{uuid.uuid4().hex}.json"
                codigo, saida, _ = self.executar("--perguntas-arquivo", str(arquivo), "--relatorio", str(relatorio), "--falhas-seguidas", "10",
                                                 transporte=Transporte(responder))
                self.assertIn(codigo, (0, 2, 3), saida)
                texto = saida + relatorio.read_text(encoding="utf-8")
                self.sem_sentinelas(texto)
                self.assertNotIn(f"Bearer {TOKEN}", texto)
                self.assertTrue(linha_do_resultado(saida))

    def test_ajuda_completa_em_portugues_com_exemplos_powershell_e_os_avisos(self):
        saida = io.StringIO()
        with contextlib.redirect_stdout(saida):
            with self.assertRaises(SystemExit) as contexto:
                gc.principal(["--help"])
        self.assertEqual(contexto.exception.code, 0)
        ajuda = " ".join(saida.getvalue().split()).casefold()  # sem as quebras de linha: uma frase pode ocupar duas linhas
        for trecho in ("PowerShell", "$env:VARELEIRA_CARGA_TOKEN", "Read-Host", "-AsSecureString", "Remove-Item Env:", "--executar", "--confirmo-consumo",
                       "consome tokens", "não interrompe um pedido já enviado", "não estabelece capacidade máxima", "garantia de disponibilidade",
                       "L400_CARGA_RESULTADO=", "--perguntas-arquivo", "NÃO use as perguntas dos conjuntos de avaliação", "Códigos de saída",
                       "Ctrl+C", "identidade gerenciada", "nunca de um argumento", "carga_pequena_nao_capacidade_producao", "--relatorio",
                       "--esperar ok,ocupado", "melhor esforço", "dados/", "imagem não tem dados/", "indisponível",
                       "terminar em .azurecontainerapps.io", "domínio personalizado", "localhost, endereço IP e qualquer outro domínio são recusados",
                       "proxies do ambiente", "são ignorados de propósito", "só HTTPS na porta 443",
                       "A última linha da saída padrão (stdout) é L400_CARGA_RESULTADO=", "as mensagens [ERRO] vão para o stderr", "saem antes da linha de resultado",
                       f"nenhum pedido novo sai, e os já enviados têm até mais {gc.FOLGA_DE_ENCERRAMENTO:g} s para terminar",
                       f"durar até o tempo máximo mais {gc.FOLGA_DE_ENCERRAMENTO:g} s", "obter o token da identidade gerenciada",
                       "fica fora dessa conta"):
            self.assertIn(" ".join(trecho.split()).casefold(), ajuda)
        self.assertNotIn("no total", ajuda, "nenhum texto promete um tempo total que o processo possa ultrapassar")
        for acao in gc.criar_parser()._actions:
            self.assertTrue(acao.help, f"{acao.option_strings} sem texto de ajuda")

    def test_os_numeros_da_ajuda_sao_os_dos_tetos_do_codigo(self):
        documentacao = " ".join(gc.__doc__.split())
        for trecho in (f"{gc.PEDIDOS_MAXIMOS} pedidos", f"concorrência {gc.CONCORRENCIA_MAXIMA}", f"{gc.TEMPO_TOTAL_MAXIMO:g} s para enviar pedidos",
                       f"{gc.TEMPO_POR_PEDIDO_MAXIMO:g} s por pedido", f"{gc.LIMITE_DA_RESPOSTA // 1024} KiB",
                       f"{gc.FALHAS_SEGUIDAS_MAXIMAS} resultados seguidos", f"{len(gc.PERGUNTAS_EMBUTIDAS)} perguntas sintéticas",
                       f"1 a {gc.PERGUNTAS_NO_ARQUIVO_MAXIMAS} textos", f"até mais {gc.FOLGA_DE_ENCERRAMENTO:g} s para terminar",
                       f"o tempo máximo mais {gc.FOLGA_DE_ENCERRAMENTO:g} s"):
            self.assertIn(trecho, documentacao)
        ajuda_do_tempo = next(acao.help for acao in gc.criar_parser()._actions if "--tempo-maximo" in acao.option_strings)
        for trecho in (f"{gc.TEMPO_TOTAL_MINIMO:g} a {gc.TEMPO_TOTAL_MAXIMO:g} s", f"padrão: {gc.TEMPO_TOTAL_PADRAO:g}",
                       f"até mais {gc.FOLGA_DE_ENCERRAMENTO:g} s para terminar", "ENVIAR pedidos"):
            self.assertIn(trecho, ajuda_do_tempo)


if __name__ == "__main__":
    unittest.main()
