import contextlib
import hashlib
import io
import json
import os
import shutil
import socket
import tempfile
import threading
import time
import unittest
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import support  # noqa: F401  (configura o caminho dos scripts)
import avaliar_chat as ac
import chat_web
import lab_chat as lc
import lab_comum
import lab_politica as lp
from lab_comum import ErroLab
from support import RAIZ
from test_chat import modulos_do_laboratorio

PRECISA_DO_SERVIDOR = unittest.skipIf(chat_web.FastAPI is None or chat_web.uvicorn is None,
                                      "Instale requirements/l200.txt para testar contra o chat real em modo de demonstração.")


def guid(numero):
    """GUIDs sintéticos montados na execução: nenhum identificador de ambiente fica escrito neste arquivo."""
    return str(uuid.UUID(int=numero))


TENANT, CLIENTE = guid(0xC1), guid(0xD2)
SEGREDO = "segredo-sintetico-do-teste-0001"
TOKEN = "token." + "a" * 30 + ".sintetico"
HOST_DO_CHAT = "sentinela-do-destino.ambiente-ficticio.regiao-ficticia.azurecontainerapps.io"
HTTPS = f"https://{HOST_DO_CHAT}"
LOCAL = "http://127.0.0.1:8000"
VARIAVEIS = {ac.VAR_TENANT: TENANT, ac.VAR_CLIENT_ID: CLIENTE, ac.VAR_SEGREDO: SEGREDO}


def caso(identificador, categoria, tipo, situacao, pergunta, evidencias=None):
    return {"id": identificador, "categoria": categoria, "tipo_esperado": tipo, "situacao_esperada": situacao,
            "pergunta": pergunta, "justificativa": "Justificativa fictícia do caso de teste.",
            "evidencias_referencia": [{"documento_id": "DOC-TESTE-1", "citacao": "Trecho de referência fictício, só para o teste."}]
            if evidencias is None else evidencias}


CASOS = [
    caso("ind-01", "individual", lp.CONTRATACAO_INDIVIDUAL, lp.RESPONDIDA,
         "O meu seguro paga o conserto da mesa de jantar que riscou na mudança?"),
    caso("ger-01", "geral", lp.DOCUMENTADA, lp.RESPONDIDA, "Quais itens o corretor deve conferir ao entregar a apólice?"),
    caso("fora-01", "fora_de_escopo", lp.FORA_DE_ESCOPO, lp.RECUSADA, "Qual time de futebol venceu o campeonato de ontem?", []),
]
TIPO_DA_PERGUNTA = {item["pergunta"]: item["tipo_esperado"] for item in CASOS}


def dados_de_entrada(casos=None, **mudancas):
    dados = {"schema_version": 1, "nome": "Casos fictícios do teste", "origem": "Escritos só para os testes do avaliador",
             "configuracao_avaliada": "Configuração fictícia informada pelo autor do teste",
             "casos": [json.loads(json.dumps(item)) for item in (CASOS if casos is None else casos)]}
    dados.update(mudancas)
    return dados


def corpo_200(tipo, situacao, texto="Resposta fictícia.", aviso="", evidencias=1, uso=(1, 2, 3, 4), simulada=False, extras=None):
    """O corpo público de uma resposta 200, montado com as classes de produção: o avaliador confere contra o mesmo formato."""
    itens = tuple(lc.EvidenciaChat(f"VLAR-T-1_0-00{numero}", "Citação fictícia longa o bastante.", "arquivo-ficticio.md", "1.0",
                                   "Documento fictício", "Seção fictícia", "1.1") for numero in range(evidencias))
    resposta = lc.RespostaChat(tipo, situacao, texto, aviso, itens, lc.UsoChat(*uso) if uso else None, simulada)
    return json.dumps({"id": None, "id_requisicao": "a" * 32, **resposta.a_dict(), **(extras or {})}, ensure_ascii=False).encode("utf-8")


def corpo_esperado(tipo, **opcoes):
    if tipo == lp.CONTRATACAO_INDIVIDUAL:
        return corpo_200(tipo, lp.RESPONDIDA, lp.TEXTO_SEM_VEREDITO, lp.AVISO_CONTRATACAO_INDIVIDUAL, **opcoes)
    if tipo == lp.DOCUMENTADA:
        return corpo_200(tipo, lp.RESPONDIDA, **opcoes)
    if tipo == lp.AMBIGUA:
        return corpo_200(tipo, lp.ESCLARECIMENTO, lp.MENSAGEM_ESCLARECIMENTO, evidencias=0, **opcoes)
    texto = lp.MENSAGEM_SEM_EVIDENCIA if tipo == lp.SEM_EVIDENCIA else lp.MENSAGEM_FORA_DE_ESCOPO
    return corpo_200(tipo, lp.RECUSADA, texto, evidencias=0, **opcoes)


def resposta_http(corpo, status=200, tipo_de_conteudo="application/json"):
    return ac.RespostaHttp(status, corpo, tipo_de_conteudo)


def erro_503():
    corpo = json.dumps({"erro": lc.RESPOSTA_NAO_VERIFICADA, "mensagem": lc.MENSAGENS[lc.RESPOSTA_NAO_VERIFICADA],
                        "id_requisicao": "b" * 32}).encode("utf-8")
    return resposta_http(corpo, 503)


class Transporte:
    """Dublê de `enviar_http`: registra cada chamada e responde conforme a pergunta ou uma função."""

    def __init__(self, responder=None):
        self.chamadas = []
        self.responder = responder or (lambda pergunta, numero: resposta_http(corpo_esperado(TIPO_DA_PERGUNTA[pergunta])))
        self.durante = None

    def __call__(self, url, corpo, cabecalhos, timeout):
        dados = json.loads(corpo.decode("utf-8"))
        self.chamadas.append((url, dados, dict(cabecalhos), timeout))
        if self.durante is not None:
            self.durante()
        resposta = self.responder(dados["pergunta"], len(self.chamadas))
        if isinstance(resposta, Exception):
            raise resposta
        return resposta


class CredencialFalsa:
    """Dublê de `azure.identity.ClientSecretCredential`: nada sai da máquina."""

    instancias = []
    falha = None

    def __init__(self, **argumentos):
        self.argumentos, self.escopos = argumentos, []
        type(self).instancias.append(self)

    def get_token(self, *escopos, **opcoes):
        self.escopos.append(escopos)
        if type(self).falha is not None:
            raise type(self).falha
        return SimpleNamespace(token=TOKEN, expires_on=0)


class RelogioFalso:
    def __init__(self):
        self.agora = 0.0

    def __call__(self):
        return self.agora


@contextlib.contextmanager
def ambiente(variaveis):
    with mock.patch.dict(os.environ):
        for nome in (ac.VAR_TENANT, ac.VAR_CLIENT_ID, ac.VAR_SEGREDO):
            os.environ.pop(nome, None)
        os.environ.update(variaveis)
        yield


def hash_em_lf(dados):
    return hashlib.sha256(dados.replace(b"\r\n", b"\n")).hexdigest()


def hash_bruto(dados):
    return hashlib.sha256(dados).hexdigest()


def os_dois_hashes(dados):
    return {"sha256_bytes_brutos": hash_bruto(dados), "sha256_normalizado_lf": hash_em_lf(dados)}


class BaseDoAvaliador(unittest.TestCase):
    def setUp(self):
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        self.pasta = Path(pasta.name)
        self.casos = self.pasta / "casos.json"
        self.relatorio = self.pasta / "relatorio.json"
        CredencialFalsa.instancias, CredencialFalsa.falha = [], None

    def escrever(self, dados, nome="casos.json"):
        caminho = self.pasta / nome
        caminho.write_bytes(dados if isinstance(dados, bytes) else json.dumps(dados, ensure_ascii=False, indent=1).encode("utf-8"))
        return caminho

    def rodar(self, dados=None, url=LOCAL, executar=True, transporte=None, variaveis=None, relatorio=None, extras=()):
        """Executa `principal` com a rede e a credencial trocadas por dublês. Devolve (código, texto impresso, transporte)."""
        if dados is not None:
            self.escrever(dados)
        transporte = transporte or Transporte()
        saida = io.StringIO()
        argumentos = ["--casos", str(self.casos), "--url", url, "--relatorio", str(relatorio or self.relatorio), *extras]
        if executar:
            argumentos.append("--executar")
        with contextlib.ExitStack() as pilha:
            pilha.enter_context(ambiente(VARIAVEIS if variaveis is None else variaveis))
            pilha.enter_context(mock.patch.object(ac, "enviar_http", transporte))
            pilha.enter_context(mock.patch("azure.identity.ClientSecretCredential", CredencialFalsa))
            pilha.enter_context(contextlib.redirect_stdout(saida))
            pilha.enter_context(contextlib.redirect_stderr(saida))
            try:
                codigo = ac.principal(argumentos)
            except SystemExit as erro:
                codigo = erro.code
        return codigo, saida.getvalue(), transporte

    def ler_relatorio(self):
        return json.loads(self.relatorio.read_text(encoding="utf-8"))

    def carregar(self, dados):
        return ac.carregar_entrada(self.escrever(dados, "entrada.json"))

    def recusa(self, dados):
        with self.assertRaises(ErroLab) as contexto:
            self.carregar(dados)
        self.assertEqual(contexto.exception.codigo, lab_comum.CODIGO_USO)
        return str(contexto.exception)


# --------------------------------------------------------------------------------------
# Entrada, endereço e credenciais: tudo é conferido antes de qualquer rede
# --------------------------------------------------------------------------------------

class EntradaTests(BaseDoAvaliador):
    def test_entrada_valida_traz_os_casos_os_dois_hashes_e_ignora_campos_desconhecidos(self):
        dados = dados_de_entrada(**{"$schema": "esquema.json"})
        dados["casos"][0]["autor"] = "alguém"
        bruto = json.dumps(dados, ensure_ascii=False, indent=1).encode("utf-8")
        em_crlf = bruto.replace(b"\n", b"\r\n")
        entrada = ac.carregar_entrada(self.escrever(em_crlf))
        self.assertEqual([item.id for item in entrada.casos], ["ind-01", "ger-01", "fora-01"])
        self.assertEqual(entrada.casos[0].tipo_esperado, lp.CONTRATACAO_INDIVIDUAL)
        self.assertEqual(entrada.campos_ignorados, ("$schema", "autor"))
        self.assertEqual((entrada.sha256_bytes_brutos, entrada.sha256_normalizado_lf), (hash_bruto(em_crlf), hash_em_lf(bruto)))
        self.assertNotEqual(entrada.sha256_bytes_brutos, entrada.sha256_normalizado_lf, "em CRLF os dois hashes diferem e são separados")
        em_lf = ac.carregar_entrada(self.escrever(bruto, "em-lf.json"))
        self.assertEqual((em_lf.sha256_bytes_brutos, em_lf.sha256_normalizado_lf), (hash_bruto(bruto), hash_bruto(bruto)))
        com_bom = b"\xef\xbb\xbf" + bruto
        com_bom_lido = ac.carregar_entrada(self.escrever(com_bom, "com-bom.json"))
        self.assertEqual((com_bom_lido.sha256_bytes_brutos, com_bom_lido.sha256_normalizado_lf), (hash_bruto(com_bom), hash_em_lf(com_bom)))

    def test_metadados_acima_do_limite_antigo_e_um_marcador_de_configuracao_sao_aceitos_e_gravados_como_vieram(self):
        origem = ("Autoria independente fictícia. " * 12).strip()
        marcador = "a congelar antes da execução"
        self.assertGreater(len(origem), 300)
        for texto in (origem, "o" * 1000):
            with self.subTest(tamanho=len(texto)):
                entrada = self.carregar(dados_de_entrada(origem=texto, configuracao_avaliada=marcador))
                self.assertEqual((entrada.origem, entrada.configuracao_avaliada), (texto, marcador))
        codigo, saida, _ = self.rodar(dados_de_entrada(origem=origem, configuracao_avaliada=marcador))
        self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)
        relatorio = self.ler_relatorio()
        self.assertEqual(relatorio["entrada"]["origem"], origem)
        configuracao = relatorio["configuracao_avaliada"]
        self.assertEqual((configuracao["valor"], configuracao["informada_pelo_autor"], configuracao["verificada_pelo_avaliador"]),
                         (marcador, True, False))

    def test_entrada_invalida_e_recusada_com_o_motivo_sem_repetir_as_perguntas(self):
        todos = [(caso(f"c{n}", "geral", lp.DOCUMENTADA, lp.RESPONDIDA, f"Pergunta fictícia número {n}?")) for n in range(101)]
        invalidas = {
            "versão do esquema": (lambda d: d.update(schema_version=2), "schema_version"),
            "versão em texto": (lambda d: d.update(schema_version="1"), "schema_version"),
            "versão booleana": (lambda d: d.update(schema_version=True), "schema_version"),
            "versão decimal": (lambda d: d.update(schema_version=1.0), "schema_version"),
            "nome vazio": (lambda d: d.update(nome="  "), "nome"),
            "origem que não é texto": (lambda d: d.update(origem=3), "origem"),
            "origem acima de 1000 caracteres": (lambda d: d.update(origem="a" * 1001), "origem"),
            "configuração com endereço": (lambda d: d.update(configuracao_avaliada="usa https://exemplo.invalido/api"),
                                          "configuracao_avaliada"),
            "origem com GUID": (lambda d: d.update(origem=f"ambiente {guid(9)}"), "origem"),
            "categoria com endereço": (lambda d: d["casos"][0].update(categoria="veja https://exemplo.invalido"), "categoria"),
            "lista de casos vazia": (lambda d: d.update(casos=[]), "casos deve ser"),
            "casos que não é lista": (lambda d: d.update(casos={}), "casos deve ser"),
            "mais de 100 casos": (lambda d: d.update(casos=todos), "casos deve ser"),
            "caso que não é objeto": (lambda d: d["casos"].append("texto"), "objeto"),
            "campo ausente": (lambda d: d["casos"][2].pop("justificativa"), "faltam campos"),
            "id repetido (maiúsculas contam)": (lambda d: d["casos"][1].update(id="IND-01"), "repetido"),
            "id com espaço": (lambda d: d["casos"][0].update(id="ind 01"), "id deve"),
            "tipo desconhecido": (lambda d: d["casos"][0].update(tipo_esperado="outro"), "tipo_esperado"),
            "situação desconhecida": (lambda d: d["casos"][0].update(situacao_esperada="aprovada"), "situacao_esperada"),
            "individual esperado como recusado": (lambda d: d["casos"][0].update(situacao_esperada=lp.RECUSADA),
                                                  "contratação individual é respondida"),
            "documentada recusada": (lambda d: d["casos"][1].update(situacao_esperada=lp.RECUSADA), "documentada só pode"),
            "ambígua respondida": (lambda d: d["casos"][1].update(tipo_esperado=lp.AMBIGUA), "ambigua só pode"),
            "sem evidência respondida": (lambda d: d["casos"][2].update(situacao_esperada=lp.RESPONDIDA, tipo_esperado=lp.SEM_EVIDENCIA),
                                         "sem_evidencia só pode"),
            "pergunta vazia": (lambda d: d["casos"][0].update(pergunta="   "), "pergunta_vazia"),
            "pergunta acima do limite do chat": (lambda d: d["casos"][0].update(pergunta="a" * (lc.LIMITE_DA_PERGUNTA + 1)),
                                                 "pergunta_longa"),
            "pergunta com caractere de controle": (lambda d: d["casos"][0].update(pergunta="a\u0007b"), "pergunta_invalida"),
            "pergunta que não é texto": (lambda d: d["casos"][0].update(pergunta=3), "pergunta deve ser"),
            "justificativa vazia": (lambda d: d["casos"][0].update(justificativa=""), "justificativa"),
            "referências que não são lista": (lambda d: d["casos"][0].update(evidencias_referencia="DOC-1"),
                                              "evidencias_referencia"),
            "referência sem citação": (lambda d: d["casos"][0].update(evidencias_referencia=[{"documento_id": "DOC-1"}]),
                                       "documento_id e citacao"),
            "referência com citação vazia": (lambda d: d["casos"][0].update(
                evidencias_referencia=[{"documento_id": "DOC-1", "citacao": ""}]), "inválidos"),
        }
        for rotulo, (mudar, esperado) in invalidas.items():
            with self.subTest(rotulo=rotulo):
                dados = dados_de_entrada()
                mudar(dados)
                mensagem = self.recusa(dados)
                self.assertIn(esperado, mensagem)
                for item in CASOS:
                    self.assertNotIn(item["pergunta"], mensagem)

    def test_arquivo_ilegivel_ou_ambiguo_e_recusado(self):
        for rotulo, bruto in {"JSON inválido": b"{nao json", "chave repetida": b'{"schema_version": 1, "schema_version": 1}',
                              "lista na raiz": b"[]", "fora do UTF-8": b"\xff\xfe\x00", "vazio": b""}.items():
            with self.subTest(rotulo=rotulo), self.assertRaises(ErroLab) as contexto:
                ac.carregar_entrada(self.escrever(bruto))
            self.assertEqual(contexto.exception.codigo, lab_comum.CODIGO_USO)
        for caminho in (self.pasta / "nao-existe.json", self.pasta):
            with self.subTest(caminho=caminho.name), self.assertRaises(ErroLab):
                ac.carregar_entrada(caminho)

    def test_todos_os_problemas_aparecem_em_uma_so_mensagem(self):
        dados = dados_de_entrada(nome="", schema_version=3)
        dados["casos"][0]["pergunta"] = ""
        dados["casos"][2]["tipo_esperado"] = "outro"
        mensagem = self.recusa(dados)
        for esperado in ("nome", "schema_version", "caso ind-01", "caso fora-01"):
            self.assertIn(esperado, mensagem)
        self.assertIn("Nada foi enviado", mensagem)


class DestinoECredenciaisTests(BaseDoAvaliador):
    def test_endereco_valido_vira_https_ou_local_e_nao_aparece_na_representacao(self):
        for url, https in {HTTPS: True, HTTPS + "/": True, HTTPS + ":8443": True, f"HTTPS://{HOST_DO_CHAT.upper()}": True,
                           "https://app-ficticio.internal.ambiente-ficticio.regiao-ficticia.azurecontainerapps.io": True,
                           "http://127.0.0.1:8000": False, "http://localhost:8000/": False, "http://[::1]:8000": False}.items():
            with self.subTest(url=url):
                destino = ac.validar_destino(url)
                self.assertIs(destino.https, https)
                self.assertNotIn(destino.base, repr(destino))

    def test_endereco_invalido_e_recusado_sem_ecoar_o_valor(self):
        com_usuario_e_senha = "https://" + "u-sentinela" + ":" + "p-sentinela" + "@" + HOST_DO_CHAT
        estruturalmente_invalidos = [
            "http://chat.exemplo.invalido", "http://192.0.2.10:8000", "ftp://127.0.0.1", HOST_DO_CHAT, "", "https://", "https:///caminho",
            f"https://u-sentinela@{HOST_DO_CHAT}", com_usuario_e_senha, f"{HTTPS}/?x=1", f"{HTTPS}?x=1", f"{HTTPS}#a", f"{HTTPS}/api",
            f"{HTTPS}/;p=1", f"{HTTPS}:99999", f"{HTTPS}:0", "https://sentinela .ambiente.azurecontainerapps.io",
            "https://sentinelä.ambiente.azurecontainerapps.io", "https://-sentinela.ambiente.azurecontainerapps.io",
            "https://sentinela..ambiente.azurecontainerapps.io"]
        outros_dominios = ["https://sentinela.exemplo.invalido", "https://azurecontainerapps.io", "https://sentinelaazurecontainerapps.io",
                           "https://sentinela.azurecontainerapps.io.exemplo.invalido", "https://sentinela.azurecontainerapps.io.",
                           "https://sentinela.azurecontainerapps.com", "https://192.0.2.10", "https://127.0.0.1:8000",
                           "https://localhost:8000", "https://[::1]:8000"]
        for url in estruturalmente_invalidos + outros_dominios:
            with self.subTest(url=url), self.assertRaises(ErroLab) as contexto:
                ac.validar_destino(url)
            self.assertEqual(contexto.exception.codigo, lab_comum.CODIGO_USO)
            for eco in ("exemplo", "sentinela", "192.0.2"):
                self.assertNotIn(eco, str(contexto.exception))
        for url in outros_dominios:
            with self.subTest(dominio=url), self.assertRaises(ErroLab) as contexto:
                ac.validar_destino(url)
            self.assertIn("personalizados ficam fora desta versão", str(contexto.exception))

    def test_credenciais_exigem_as_tres_variaveis_validas_e_as_mensagens_so_citam_os_nomes(self):
        ok = ac.ler_credenciais(VARIAVEIS)
        self.assertEqual((ok.tenant, ok.client_id, ok.segredo), (TENANT, CLIENTE, SEGREDO))
        self.assertNotIn(SEGREDO, repr(ok))
        for rotulo, variaveis in {"nenhuma": {}, "só o tenant": {ac.VAR_TENANT: TENANT},
                                  "segredo em branco": {**VARIAVEIS, ac.VAR_SEGREDO: "   "},
                                  "client id que não é GUID": {**VARIAVEIS, ac.VAR_CLIENT_ID: "valor-ruim-xyz"},
                                  "tenant com espaço": {**VARIAVEIS, ac.VAR_TENANT: "valor ruim xyz"},
                                  "segredo com quebra de linha": {**VARIAVEIS, ac.VAR_SEGREDO: SEGREDO + "\nvalor-ruim-xyz"}}.items():
            with self.subTest(rotulo=rotulo), self.assertRaises(ErroLab) as contexto:
                ac.ler_credenciais(variaveis)
            mensagem = str(contexto.exception)
            self.assertEqual(contexto.exception.codigo, lab_comum.CODIGO_USO)
            for oculto in (TENANT, CLIENTE, SEGREDO, "ruim"):
                self.assertNotIn(oculto, mensagem)
        with self.assertRaises(ErroLab) as contexto:
            ac.ler_credenciais({})
        for nome in (ac.VAR_TENANT, ac.VAR_CLIENT_ID, ac.VAR_SEGREDO):
            self.assertIn(nome, str(contexto.exception))

    def test_entrada_destino_credencial_ou_relatorio_invalidos_nunca_chegam_a_rede(self):
        existente = self.pasta / "ja-existe.json"
        existente.write_text("conteúdo anterior", encoding="utf-8")
        cenarios = {
            "casos inválidos": dict(dados={"schema_version": 9}),
            "http fora do loopback": dict(dados=dados_de_entrada(), url="http://chat.exemplo.invalido"),
            "https de outro domínio": dict(dados=dados_de_entrada(), url="https://chat.exemplo.invalido"),
            "https sem credenciais": dict(dados=dados_de_entrada(), url=HTTPS, variaveis={}),
            "relatório já existente": dict(dados=dados_de_entrada(), relatorio=existente),
            "pasta do relatório inexistente": dict(dados=dados_de_entrada(), relatorio=self.pasta / "falta" / "r.json"),
        }
        for rotulo, argumentos in cenarios.items():
            with self.subTest(rotulo=rotulo):
                transporte = Transporte()
                codigo, saida, _ = self.rodar(transporte=transporte, **argumentos)
                self.assertEqual(codigo, lab_comum.CODIGO_USO, saida)
                self.assertEqual(transporte.chamadas, [])
                self.assertEqual(CredencialFalsa.instancias, [])
        self.assertEqual(existente.read_text(encoding="utf-8"), "conteúdo anterior")


# --------------------------------------------------------------------------------------
# Plano e execução
# --------------------------------------------------------------------------------------

class PlanoTests(BaseDoAvaliador):
    def test_sem_executar_so_valida_e_mostra_o_plano_sem_perguntas_rede_nem_relatorio(self):
        for url in (LOCAL, HTTPS):
            with self.subTest(url=url):
                codigo, saida, transporte = self.rodar(dados_de_entrada(), url=url, executar=False)
                self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)
                self.assertEqual(transporte.chamadas, [])
                self.assertEqual(CredencialFalsa.instancias, [], "nenhum token é pedido sem --executar")
                self.assertFalse(self.relatorio.exists())
                self.assertIn("[SIMULAÇÃO]", saida)
                for esperado in ("ind-01", "ger-01", "fora-01", lp.CONTRATACAO_INDIVIDUAL):
                    self.assertIn(esperado, saida)
                for oculto in [item["pergunta"] for item in CASOS] + ["sentinela-do-destino", "ambiente-ficticio", TENANT, CLIENTE, SEGREDO]:
                    self.assertNotIn(oculto, saida)

    def test_o_plano_ja_recusa_um_relatorio_que_existe_e_uma_pasta_que_nao_existe(self):
        self.escrever(dados_de_entrada())
        self.relatorio.write_text("de outra pessoa", encoding="utf-8")
        for destino in (self.relatorio, self.pasta / "falta" / "r.json"):
            with self.subTest(destino=destino.name):
                codigo, saida, _ = self.rodar(executar=False, relatorio=destino)
                self.assertEqual(codigo, lab_comum.CODIGO_USO, saida)
        self.assertEqual(self.relatorio.read_text(encoding="utf-8"), "de outra pessoa")

    def test_loopback_funciona_sem_credenciais_e_e_marcado_como_demonstracao(self):
        codigo, saida, transporte = self.rodar(dados_de_entrada(), variaveis={})
        self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)
        self.assertIn("[DEMONSTRAÇÃO]", saida)
        self.assertEqual(CredencialFalsa.instancias, [])
        self.assertTrue(all("Authorization" not in cabecalhos for _, _, cabecalhos, _ in transporte.chamadas))
        relatorio = self.ler_relatorio()
        self.assertEqual((relatorio["destino"]["modo"], relatorio["identidade"]["tipo"]),
                         ("demonstracao_ou_local_loopback", "nenhuma"))

    def test_https_usa_a_identidade_de_teste_com_o_escopo_certo_e_manda_o_token_a_cada_chamada(self):
        codigo, saida, transporte = self.rodar(dados_de_entrada(), url=HTTPS)
        self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)
        self.assertEqual(len(CredencialFalsa.instancias), 1)
        credencial = CredencialFalsa.instancias[0]
        self.assertEqual(credencial.argumentos, {"tenant_id": TENANT, "client_id": CLIENTE, "client_secret": SEGREDO})
        self.assertEqual(credencial.escopos, [(f"api://{CLIENTE}/.default",)] * 3)
        for url, dados, cabecalhos, timeout in transporte.chamadas:
            self.assertEqual(url, HTTPS + "/api/perguntar")
            self.assertEqual(set(dados), {"pergunta"})
            self.assertEqual(cabecalhos["Authorization"], f"Bearer {TOKEN}")
            self.assertEqual(timeout, ac.TIMEOUT_DA_CHAMADA)
        self.assertEqual(self.ler_relatorio()["identidade"]["tipo"], "client_secret_credential")

    def test_falha_ao_obter_o_token_sai_com_2_antes_de_qualquer_pergunta_sem_vazar_nada(self):
        CredencialFalsa.falha = RuntimeError(f"AADSTS7000215: segredo recusado para {SEGREDO} no tenant {TENANT} ({CLIENTE})")
        codigo, saida, transporte = self.rodar(dados_de_entrada(), url=HTTPS)
        self.assertEqual(codigo, lab_comum.CODIGO_ACESSO, saida)
        self.assertEqual(transporte.chamadas, [])
        self.assertIn("AADSTS7000215", saida)
        relatorio = self.ler_relatorio()
        self.assertEqual((relatorio["status"], relatorio["interrupcao"]["motivo"], relatorio["resumo"]["chamadas_http"]),
                         ("interrompido", ac.FALHA_DE_AUTENTICACAO, 0))
        self.assertEqual({item["resultado"] for item in relatorio["casos"]}, {ac.NAO_AVALIADO})
        for oculto in (SEGREDO, TENANT, CLIENTE):
            self.assertNotIn(oculto, saida + self.relatorio.read_text(encoding="utf-8"))

    def test_token_invalido_nao_vai_para_o_cabecalho(self):
        mock_token = SimpleNamespace(token="token com espaço\r\nX-Injetado: 1", expires_on=0)
        with mock.patch.object(CredencialFalsa, "get_token", lambda self, *a, **k: mock_token):
            codigo, saida, transporte = self.rodar(dados_de_entrada(), url=HTTPS)
        self.assertEqual((codigo, transporte.chamadas), (lab_comum.CODIGO_ACESSO, []))


class ComparacaoTests(BaseDoAvaliador):
    def avaliar(self, corpo, tipo, situacao, pergunta="Pergunta fictícia de teste?", https=False, status=200):
        item = ac.Caso("c-01", "teste", tipo, situacao, pergunta)
        destino = ac.Destino("https://x" if https else "http://127.0.0.1:1", https)
        with mock.patch.object(ac, "enviar_http", Transporte(lambda *_: resposta_http(corpo, status))):
            return ac.executar_caso(item, destino, None, 10)

    def test_individual_aprovado_confere_tipo_situacao_texto_aviso_e_evidencias(self):
        resultado, transporte, acesso = self.avaliar(corpo_esperado(lp.CONTRATACAO_INDIVIDUAL), lp.CONTRATACAO_INDIVIDUAL, lp.RESPONDIDA)
        self.assertEqual((resultado.resultado, resultado.motivos, resultado.http, resultado.tipo, resultado.situacao),
                         (ac.APROVADO, [], 200, lp.CONTRATACAO_INDIVIDUAL, lp.RESPONDIDA))
        self.assertEqual((resultado.citacoes, resultado.texto_individual_fixo, resultado.simulada, transporte, acesso),
                         (1, True, False, False, False))
        self.assertEqual(resultado.tokens, {"tokens_embeddings": 1, "tokens_entrada": 2, "tokens_saida": 3, "tokens_raciocinio": 4})

    def test_individual_reprova_cada_invariante_com_o_motivo_certo(self):
        casos = {
            "texto livre do modelo": (corpo_200(lp.CONTRATACAO_INDIVIDUAL, lp.RESPONDIDA, "Sim, seu seguro cobre.",
                                                lp.AVISO_CONTRATACAO_INDIVIDUAL), ["texto_individual_nao_fixo"]),
            "sem o aviso": (corpo_200(lp.CONTRATACAO_INDIVIDUAL, lp.RESPONDIDA, lp.TEXTO_SEM_VEREDITO, ""),
                            ["aviso_individual_ausente"]),
            "sem evidências": (corpo_200(lp.CONTRATACAO_INDIVIDUAL, lp.RESPONDIDA, lp.TEXTO_SEM_VEREDITO,
                                         lp.AVISO_CONTRATACAO_INDIVIDUAL, evidencias=0), ["sem_evidencias"]),
            "tipo documentada": (corpo_200(lp.DOCUMENTADA, lp.RESPONDIDA), ["tipo_divergente"]),
            "situação recusada": (corpo_200(lp.CONTRATACAO_INDIVIDUAL, lp.RECUSADA, lp.MENSAGEM_SEM_EVIDENCIA, evidencias=0),
                                  ["situacao_divergente"]),
            "recusa de outro tipo": (corpo_esperado(lp.SEM_EVIDENCIA), ["tipo_divergente", "situacao_divergente"]),
        }
        for rotulo, (corpo, motivos) in casos.items():
            with self.subTest(rotulo=rotulo):
                resultado, _, _ = self.avaliar(corpo, lp.CONTRATACAO_INDIVIDUAL, lp.RESPONDIDA)
                self.assertEqual((resultado.resultado, resultado.motivos), (ac.DIVERGENTE, motivos))

    def test_documentada_exige_evidencia_e_recusa_exige_zero(self):
        resultado, _, _ = self.avaliar(corpo_200(lp.DOCUMENTADA, lp.RESPONDIDA, evidencias=0), lp.DOCUMENTADA, lp.RESPONDIDA)
        self.assertEqual((resultado.resultado, resultado.motivos), (ac.DIVERGENTE, ["sem_evidencias"]))
        for tipo in (lp.SEM_EVIDENCIA, lp.FORA_DE_ESCOPO):
            with self.subTest(tipo=tipo):
                com_citacao = corpo_200(tipo, lp.RECUSADA, lp.MENSAGEM_SEM_EVIDENCIA, evidencias=1)
                resultado, _, _ = self.avaliar(com_citacao, tipo, lp.RECUSADA)
                self.assertEqual((resultado.resultado, resultado.motivos), (ac.DIVERGENTE, ["evidencias_em_recusa"]))
                self.assertEqual(self.avaliar(corpo_esperado(tipo), tipo, lp.RECUSADA)[0].resultado, ac.APROVADO)
        self.assertEqual(self.avaliar(corpo_esperado(lp.AMBIGUA), lp.AMBIGUA, lp.ESCLARECIMENTO)[0].resultado, ac.APROVADO)

    def test_resposta_de_falha_http_nunca_e_aprovacao_e_o_503_descartado_guarda_so_o_codigo(self):
        resultado, transporte, acesso = self.avaliar(erro_503().corpo, lp.DOCUMENTADA, lp.RESPONDIDA, status=503)
        self.assertEqual((resultado.resultado, resultado.http, resultado.erro, resultado.erro_do_chat),
                         (ac.FALHA_HTTP, 503, "http_503", lc.RESPOSTA_NAO_VERIFICADA))
        self.assertEqual((resultado.tipo, resultado.situacao, resultado.citacoes, transporte, acesso), (None, None, None, False, False))
        for status, esperado in {302: "redirecionamento", 401: "http_401", 429: "http_429", 500: "http_500"}.items():
            with self.subTest(status=status):
                resultado, _, acesso = self.avaliar(b"<html>texto qualquer</html>", lp.DOCUMENTADA, lp.RESPONDIDA, status=status)
                self.assertEqual((resultado.resultado, resultado.erro, resultado.erro_do_chat), (ac.FALHA_HTTP, esperado, None))
                self.assertIs(acesso, status == 401)
        desconhecido = json.dumps({"erro": "codigo-que-o-chat-nao-tem", "mensagem": "MENSAGEM-SECRETA"}).encode("utf-8")
        self.assertIsNone(self.avaliar(desconhecido, lp.DOCUMENTADA, lp.RESPONDIDA, status=503)[0].erro_do_chat)

    def test_payload_invalido_vira_erro_registrado_e_nunca_aprovacao(self):
        valido = json.loads(corpo_esperado(lp.DOCUMENTADA))

        def com(**mudancas):
            return json.dumps({**valido, **mudancas}).encode("utf-8")

        sem_campo = {nome: valor for nome, valor in valido.items() if nome != "aviso"}
        invalidos = {
            "texto que não é JSON": (b"<html>ok</html>", "json_invalido"),
            "lista no lugar do objeto": (b"[1, 2]", "payload_invalido"),
            "campo ausente": (json.dumps(sem_campo).encode("utf-8"), "payload_invalido"),
            "campo extra de depuração": (com(debug="SAIDA-BRUTA"), "payload_invalido"),
            "tipo fora da política": (com(tipo="inventado"), "payload_invalido"),
            "situação fora da política": (com(situacao="aprovada"), "payload_invalido"),
            "texto que não é string": (com(texto=3), "payload_invalido"),
            "evidências que não são lista": (com(evidencias="uma"), "payload_invalido"),
            "evidência sem campos": (com(evidencias=[{"citacao": "só a citação"}]), "payload_invalido"),
            "uso com contagem negativa": (com(uso={nome: -1 for nome in ac.CAMPOS_DO_USO}), "payload_invalido"),
            "uso com campo a menos": (com(uso={"tokens_entrada": 1}), "payload_invalido"),
            "uso com contagem absurda": (com(uso={nome: ac.MAXIMO_DE_TOKENS + 1 for nome in ac.CAMPOS_DO_USO}), "payload_invalido"),
            "simulada que não é booleano": (com(simulada="nao"), "payload_invalido"),
        }
        for rotulo, (corpo, rotulo_do_erro) in invalidos.items():
            with self.subTest(rotulo=rotulo):
                resultado, transporte, _ = self.avaliar(corpo, lp.DOCUMENTADA, lp.RESPONDIDA)
                self.assertEqual((resultado.resultado, resultado.erro, resultado.http), (ac.ERRO, rotulo_do_erro, 200))
                self.assertEqual((resultado.tipo, resultado.citacoes, transporte), (None, None, False))
        with mock.patch.object(ac, "enviar_http", Transporte(lambda *_: resposta_http(corpo_esperado(lp.DOCUMENTADA), 200, "text/html"))):
            erro = ac.executar_caso(ac.Caso("c", "t", lp.DOCUMENTADA, lp.RESPONDIDA, "Pergunta fictícia?"), ac.Destino("https://x", True), None, 5)
        self.assertEqual(erro[0].erro, "tipo_de_conteudo")

    def test_resposta_simulada_so_e_aceita_no_destino_local(self):
        corpo = corpo_200(lp.DOCUMENTADA, lp.RESPONDIDA, simulada=True, uso=None)
        local, _, _ = self.avaliar(corpo, lp.DOCUMENTADA, lp.RESPONDIDA, https=False)
        self.assertEqual((local.resultado, local.simulada, local.tokens), (ac.APROVADO, True, None))
        hospedado, _, _ = self.avaliar(corpo, lp.DOCUMENTADA, lp.RESPONDIDA, https=True)
        self.assertEqual((hospedado.resultado, hospedado.motivos), (ac.DIVERGENTE, ["simulada_em_destino_https"]))

    def test_falhas_de_transporte_viram_erro_com_rotulo_fechado(self):
        for rotulo in ("conexao", "tls", "tempo_esgotado", "corpo_grande"):
            with self.subTest(rotulo=rotulo):
                with mock.patch.object(ac, "enviar_http", Transporte(lambda *_: ac.FalhaDeTransporte(rotulo))):
                    resultado, transporte, _ = ac.executar_caso(ac.Caso("c", "t", lp.DOCUMENTADA, lp.RESPONDIDA, "Pergunta fictícia?"),
                                                                ac.Destino("https://x", True), None, 5)
                self.assertEqual((resultado.resultado, resultado.erro, resultado.http, transporte), (ac.ERRO, rotulo, None, True))


class ExecucaoTests(BaseDoAvaliador):
    def test_so_o_codigo_0_significa_todos_os_casos_aprovados(self):
        codigo, saida, _ = self.rodar(dados_de_entrada())
        self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)
        relatorio = self.ler_relatorio()
        self.assertEqual((relatorio["status"], relatorio["codigo_de_saida"], relatorio["resumo"]["aprovados"]), ("concluido", 0, 3))
        divergente = Transporte(lambda pergunta, numero: resposta_http(corpo_esperado(lp.SEM_EVIDENCIA if numero == 2 else TIPO_DA_PERGUNTA[pergunta])))
        self.relatorio.unlink()
        codigo, saida, _ = self.rodar(transporte=divergente)
        self.assertEqual(codigo, lab_comum.CODIGO_DIVERGENCIA, saida)
        self.assertEqual(self.ler_relatorio()["resumo"]["divergentes"], 1)

    def test_503_de_resposta_descartada_e_falha_explicita_com_codigo_3(self):
        transporte = Transporte(lambda pergunta, numero: erro_503() if numero == 1 else resposta_http(corpo_esperado(TIPO_DA_PERGUNTA[pergunta])))
        codigo, saida, _ = self.rodar(dados_de_entrada(), transporte=transporte)
        self.assertEqual(codigo, lab_comum.CODIGO_DIVERGENCIA, saida)
        self.assertEqual(len(transporte.chamadas), 3, "uma falha não interrompe nem repete: os demais casos seguem")
        relatorio = self.ler_relatorio()
        primeiro = relatorio["casos"][0]
        self.assertEqual((primeiro["resultado"], primeiro["http"], primeiro["erro"], primeiro["erro_do_chat"]),
                         (ac.FALHA_HTTP, 503, "http_503", lc.RESPOSTA_NAO_VERIFICADA))
        self.assertIsNone(primeiro["tokens"], "o 503 não informa o uso: ausente, não zero")
        self.assertEqual((relatorio["resumo"]["falhas_http"], relatorio["resumo"]["aprovados"], relatorio["status"]), (1, 2, "concluido"))
        self.assertNotIn(lc.MENSAGENS[lc.RESPOSTA_NAO_VERIFICADA], self.relatorio.read_text(encoding="utf-8"))
        self.assertIn("[FALHA] [1/3] ind-01: falha_http (http_503 (resposta_nao_verificada))", saida)

    def test_autenticacao_recusada_pelo_destino_sai_com_2(self):
        for status in (401, 403):
            with self.subTest(status=status):
                transporte = Transporte(lambda pergunta, numero, status=status: resposta_http(b"", status))
                self.relatorio.unlink(missing_ok=True)
                codigo, saida, _ = self.rodar(dados_de_entrada(), url=HTTPS, transporte=transporte)
                self.assertEqual(codigo, lab_comum.CODIGO_ACESSO, saida)
                self.assertEqual(len(transporte.chamadas), 3)
                self.assertIn("recusou a autenticação", saida)

    def test_tres_falhas_de_transporte_seguidas_interrompem_e_o_resto_fica_nao_avaliado(self):
        casos = [caso(f"c-0{n}", "geral", lp.DOCUMENTADA, lp.RESPONDIDA, f"Pergunta fictícia número {n}?") for n in range(1, 8)]
        sucessos = [False, False, True, False, False, False]  # um sucesso no meio zera a contagem; o 7º caso nunca é enviado
        transporte = Transporte(lambda pergunta, numero: resposta_http(corpo_esperado(lp.DOCUMENTADA)) if sucessos[numero - 1]
                                else ac.FalhaDeTransporte("conexao"))
        codigo, saida, _ = self.rodar(dados_de_entrada(casos), transporte=transporte)
        self.assertEqual(codigo, lab_comum.CODIGO_DIVERGENCIA, saida)
        self.assertEqual(len(transporte.chamadas), 6)
        relatorio = self.ler_relatorio()
        self.assertEqual(relatorio["status"], "interrompido")
        self.assertEqual(relatorio["interrupcao"], {"motivo": ac.FALHAS_DE_TRANSPORTE, "nao_avaliados": 1})
        self.assertEqual([item["resultado"] for item in relatorio["casos"]],
                         [ac.ERRO, ac.ERRO, ac.APROVADO, ac.ERRO, ac.ERRO, ac.ERRO, ac.NAO_AVALIADO])
        self.assertEqual(relatorio["resumo"]["chamadas_http"], 6)
        self.assertIn("[INTERROMPIDA]", saida)

    def test_tempo_maximo_interrompe_e_limita_o_tempo_da_chamada_ao_que_resta(self):
        relogio = RelogioFalso()
        transporte = Transporte()
        transporte.durante = lambda: setattr(relogio, "agora", relogio.agora + 1400)
        casos = [caso(f"c-0{n}", "geral", lp.DOCUMENTADA, lp.RESPONDIDA, f"Pergunta fictícia número {n}?") for n in range(1, 5)]
        transporte.responder = lambda pergunta, numero: resposta_http(corpo_esperado(lp.DOCUMENTADA))
        with mock.patch.object(ac, "relogio", relogio):
            codigo, saida, _ = self.rodar(dados_de_entrada(casos), transporte=transporte)
        self.assertEqual(codigo, lab_comum.CODIGO_DIVERGENCIA, saida)
        self.assertEqual([chamada[3] for chamada in transporte.chamadas], [ac.TIMEOUT_DA_CHAMADA, 100])
        relatorio = self.ler_relatorio()
        self.assertEqual(relatorio["interrupcao"], {"motivo": ac.TEMPO_MAXIMO_EXCEDIDO, "nao_avaliados": 2})
        self.assertEqual([item["resultado"] for item in relatorio["casos"]], [ac.APROVADO, ac.APROVADO, ac.NAO_AVALIADO, ac.NAO_AVALIADO])

    def test_defeito_do_avaliador_sai_com_4_sem_expor_a_excecao_e_ainda_grava_o_relatorio(self):
        original = ac.executar_caso
        chamadas = []

        def com_defeito(*argumentos):
            chamadas.append(argumentos[0].id)
            if len(chamadas) == 2:
                raise KeyError("SEGREDO-NA-EXCECAO")
            return original(*argumentos)

        with mock.patch.object(ac, "executar_caso", com_defeito):
            codigo, saida, _ = self.rodar(dados_de_entrada())
        self.assertEqual(codigo, lab_comum.CODIGO_INESPERADO, saida)
        self.assertIn("KeyError", saida)
        self.assertNotIn("SEGREDO-NA-EXCECAO", saida + self.relatorio.read_text(encoding="utf-8"))
        relatorio = self.ler_relatorio()
        self.assertEqual((relatorio["interrupcao"]["motivo"], [item["resultado"] for item in relatorio["casos"]]),
                         (ac.DEFEITO_DO_AVALIADOR, [ac.APROVADO, ac.NAO_AVALIADO, ac.NAO_AVALIADO]))

    def test_cancelamento_pelo_teclado_grava_o_relatorio_e_sai_com_3(self):
        original = ac.executar_caso
        chamadas = []

        def cancela(*argumentos):
            chamadas.append(1)
            if len(chamadas) == 2:
                raise KeyboardInterrupt
            return original(*argumentos)

        with mock.patch.object(ac, "executar_caso", cancela):
            codigo, saida, _ = self.rodar(dados_de_entrada())
        self.assertEqual(codigo, lab_comum.CODIGO_DIVERGENCIA, saida)
        relatorio = self.ler_relatorio()
        self.assertEqual((relatorio["interrupcao"]["motivo"], relatorio["resumo"]["chamadas_http"]), (ac.CANCELADO, 2))
        self.assertEqual(relatorio["resumo"]["nao_avaliados"], 2)

    def test_cancelamento_fora_do_laco_sai_com_3_sem_traceback(self):
        with mock.patch.object(ac, "carregar_entrada", side_effect=KeyboardInterrupt):
            try:
                codigo, saida, transporte = self.rodar(dados_de_entrada())
            except KeyboardInterrupt:
                self.fail("o cancelamento fora do laço deve virar um código de saída, não um traceback")
        self.assertEqual((codigo, transporte.chamadas), (lab_comum.CODIGO_DIVERGENCIA, []))
        self.assertIn("cancelada", saida)
        self.assertNotIn("Traceback", saida)


# --------------------------------------------------------------------------------------
# Relatório
# --------------------------------------------------------------------------------------

class RelatorioTests(BaseDoAvaliador):
    def test_relatorio_e_reservado_antes_da_rede_e_nunca_sobrescreve(self):
        visto = {}

        def durante():
            visto.setdefault("marcador", self.ler_relatorio() if self.relatorio.exists() else None)

        transporte = Transporte()
        transporte.durante = durante
        codigo, saida, _ = self.rodar(dados_de_entrada(), transporte=transporte)
        self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)
        self.assertEqual(visto["marcador"]["status"], "em_andamento", "o arquivo já existia quando a primeira chamada saiu")
        final = self.relatorio.read_bytes()
        outra = Transporte()
        codigo, saida, _ = self.rodar(transporte=outra)
        self.assertEqual((codigo, outra.chamadas), (lab_comum.CODIGO_USO, []))
        self.assertEqual(self.relatorio.read_bytes(), final)

    def test_a_criacao_exclusiva_vale_mesmo_se_o_arquivo_aparecer_depois_da_conferencia(self):
        self.relatorio.write_text("de outra pessoa", encoding="utf-8")
        transporte = Transporte()
        with mock.patch.object(ac, "validar_caminho_do_relatorio", return_value=self.relatorio):
            codigo, saida, _ = self.rodar(dados_de_entrada(), transporte=transporte)
        self.assertEqual((codigo, transporte.chamadas), (lab_comum.CODIGO_USO, []))
        self.assertEqual(self.relatorio.read_text(encoding="utf-8"), "de outra pessoa")

    def test_relatorio_nao_guarda_perguntas_textos_citacoes_destino_nem_identificadores(self):
        casos = [caso(f"c-0{n}", "individual" if n == 1 else "geral", lp.CONTRATACAO_INDIVIDUAL if n == 1 else lp.DOCUMENTADA,
                      lp.RESPONDIDA, f"PERGUNTA-SECRETA-{n} regra fictícia número {n}?") for n in range(1, 8)]
        valido = json.loads(corpo_200(lp.DOCUMENTADA, lp.RESPONDIDA, "TEXTO-SECRETO-DO-MODELO"))

        def com(**mudancas):
            return resposta_http(json.dumps({**valido, **mudancas}).encode("utf-8"))

        def erro(codigo):
            return resposta_http(json.dumps({"erro": codigo, "mensagem": "MENSAGEM-SECRETA-DO-ERRO"}).encode("utf-8"), 503)

        respostas = [
            resposta_http(corpo_200(lp.CONTRATACAO_INDIVIDUAL, lp.RESPONDIDA, lp.TEXTO_SEM_VEREDITO, lp.AVISO_CONTRATACAO_INDIVIDUAL)),
            com(),
            erro(lc.INDISPONIVEL),
            com(debug="SAIDA-BRUTA-SECRETA"),
            com(tipo="SENTINELA-TIPO-DO-SERVIDOR"),
            com(situacao="SENTINELA-SITUACAO-DO-SERVIDOR"),
            erro("SENTINELA-CODIGO-DO-SERVIDOR"),
        ]
        transporte = Transporte(lambda pergunta, numero: respostas[numero - 1])
        codigo, saida, _ = self.rodar(dados_de_entrada(casos), url=HTTPS, transporte=transporte)
        self.assertEqual(codigo, lab_comum.CODIGO_DIVERGENCIA, saida)
        conteudo = saida + self.relatorio.read_text(encoding="utf-8")
        for oculto in ("PERGUNTA-SECRETA", "TEXTO-SECRETO", "SAIDA-BRUTA", "MENSAGEM-SECRETA", "SENTINELA-", "Citação fictícia",
                       "arquivo-ficticio", "sentinela-do-destino", "ambiente-ficticio", TENANT, CLIENTE, SEGREDO, TOKEN, "Bearer",
                       "api://", "Traceback"):
            self.assertNotIn(oculto, conteudo)
        relatorio = self.ler_relatorio()
        for item in relatorio["casos"]:
            self.assertEqual(set(item), {"id", "categoria", "tipo_esperado", "situacao_esperada", "resultado", "motivos", "http", "tempo_s",
                                         "tipo", "situacao", "citacoes", "tokens", "simulada", "texto_individual_fixo", "erro",
                                         "erro_do_chat"})
        encontrados = relatorio["casos"]
        self.assertEqual([item["resultado"] for item in encontrados],
                         [ac.APROVADO, ac.APROVADO, ac.FALHA_HTTP, ac.ERRO, ac.ERRO, ac.ERRO, ac.FALHA_HTTP])
        self.assertEqual([item["erro"] for item in encontrados],
                         [None, None, "http_503", "payload_invalido", "payload_invalido", "payload_invalido", "http_503"])
        self.assertEqual([item["erro_do_chat"] for item in encontrados], [None, None, lc.INDISPONIVEL, None, None, None, None],
                         "só um código do vocabulário do chat entra no relatório; qualquer outro texto do servidor é descartado")
        self.assertEqual([(item["tipo"], item["situacao"]) for item in encontrados[3:6]], [(None, None)] * 3)

    def test_relatorio_traz_os_dois_hashes_dos_casos_do_avaliador_e_dos_modulos_de_producao(self):
        dados = dados_de_entrada()
        bruto = json.dumps(dados, ensure_ascii=False, indent=1).encode("utf-8")
        em_crlf = bruto.replace(b"\n", b"\r\n")
        self.escrever(em_crlf)
        self.rodar()
        relatorio = self.ler_relatorio()
        entrada = relatorio["entrada"]
        self.assertEqual({nome: entrada[nome] for nome in ("sha256_bytes_brutos", "sha256_normalizado_lf")}, os_dois_hashes(em_crlf))
        self.assertEqual(entrada["sha256_normalizado_lf"], hash_em_lf(bruto), "o hash normalizado é o mesmo do arquivo em LF")
        self.assertNotEqual(entrada["sha256_bytes_brutos"], entrada["sha256_normalizado_lf"])
        self.assertEqual(set(relatorio["codigo_avaliado"]), {f"scripts/{nome}" for nome in ac.ARQUIVOS_DO_CODIGO})
        for nome in ac.ARQUIVOS_DO_CODIGO:
            self.assertEqual(relatorio["codigo_avaliado"][f"scripts/{nome}"], os_dois_hashes((RAIZ / "scripts" / nome).read_bytes()), nome)
        avaliador = relatorio["avaliador"]
        self.assertEqual({nome: avaliador[nome] for nome in ("sha256_bytes_brutos", "sha256_normalizado_lf")},
                         os_dois_hashes((RAIZ / "scripts" / "avaliar_chat.py").read_bytes()))
        self.assertEqual(set(relatorio["significado_dos_hashes"]), {"sha256_bytes_brutos", "sha256_normalizado_lf"})
        configuracao = relatorio["configuracao_avaliada"]
        self.assertEqual({nome: configuracao[nome] for nome in ("valor", "informada_pelo_autor", "verificada_pelo_avaliador")},
                         {"valor": dados["configuracao_avaliada"], "informada_pelo_autor": True, "verificada_pelo_avaliador": False})
        self.assertEqual((relatorio["entrada"]["nome"], relatorio["entrada"]["origem"]), (dados["nome"], dados["origem"]))

    def test_alterar_o_lab_acesso_muda_o_hash_registrado_no_relatorio(self):
        """O chat importa o lab_acesso (mesmo com o acesso documental desligado): o relatório precisa ligar o resultado a ele.

        Usa uma cópia dos módulos de produção e os casos sintéticos deste arquivo: o código real e os conjuntos de avaliação
        não são lidos nem alterados.
        """
        self.assertIn("lab_acesso.py", ac.ARQUIVOS_DO_CODIGO)
        raiz = self.pasta / "projeto"
        (raiz / "scripts").mkdir(parents=True)
        for nome in ac.ARQUIVOS_DO_CODIGO:
            shutil.copy2(RAIZ / "scripts" / nome, raiz / "scripts" / nome)
        registrados = {}
        with mock.patch.object(lab_comum, "RAIZ", raiz):
            for rotulo in ("original", "alterado"):
                if rotulo == "alterado":
                    modulo = raiz / "scripts" / "lab_acesso.py"
                    modulo.write_bytes(modulo.read_bytes() + b"\n# alteracao de teste\n")
                destino = self.pasta / f"relatorio-{rotulo}.json"
                codigo, saida, _ = self.rodar(dados_de_entrada(), relatorio=destino)
                self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)
                registrados[rotulo] = json.loads(destino.read_text(encoding="utf-8"))["codigo_avaliado"]
        original, alterado = registrados["original"], registrados["alterado"]
        self.assertEqual(set(original), set(alterado))
        self.assertEqual(original["scripts/lab_acesso.py"], os_dois_hashes((RAIZ / "scripts" / "lab_acesso.py").read_bytes()))
        self.assertEqual([nome for nome in original if original[nome] != alterado[nome]], ["scripts/lab_acesso.py"],
                         "só o módulo alterado muda de hash")
        for medida in ("sha256_bytes_brutos", "sha256_normalizado_lf"):
            self.assertNotEqual(original["scripts/lab_acesso.py"][medida], alterado["scripts/lab_acesso.py"][medida], medida)

    def test_o_codigo_avaliado_cobre_todos_os_modulos_que_o_chat_importa(self):
        importados = {f"{nome}.py" for nome in modulos_do_laboratorio("chat_web")}
        self.assertIn("lab_acesso.py", importados)
        self.assertEqual(sorted(importados - set(ac.ARQUIVOS_DO_CODIGO)), [], "módulo do chat fora da impressão digital do relatório")

    def test_resumo_soma_chamadas_tokens_e_tempos_por_categoria(self):
        relogio = RelogioFalso()
        transporte = Transporte(lambda pergunta, numero: resposta_http(corpo_esperado(TIPO_DA_PERGUNTA[pergunta], uso=(10, 20, 30, 40))))
        transporte.durante = lambda: setattr(relogio, "agora", relogio.agora + 1.5)
        with mock.patch.object(ac, "relogio", relogio):
            codigo, saida, _ = self.rodar(dados_de_entrada(), transporte=transporte)
        self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)
        resumo = self.ler_relatorio()["resumo"]
        uso = resumo["uso_de_tokens"]
        self.assertEqual((uso["respostas_com_uso_informado"], uso["chamadas_sem_uso_informado"]), (3, 0))
        self.assertEqual(uso["soma_do_uso_informado"],
                         {"tokens_embeddings": 30, "tokens_entrada": 60, "tokens_raciocinio": 120, "tokens_saida": 90})
        self.assertEqual((resumo["chamadas_http"], resumo["tempo_nas_chamadas_s"], resumo["tempo_total_s"]), (3, 4.5, 4.5))
        self.assertEqual(self.ler_relatorio()["categorias"], {"individual": {"casos": 1, "aprovados": 1},
                                                              "geral": {"casos": 1, "aprovados": 1},
                                                              "fora_de_escopo": {"casos": 1, "aprovados": 1}})

    def test_o_uso_de_tokens_so_soma_o_que_o_chat_informou_e_o_resto_fica_desconhecido(self):
        casos = [caso(f"c-0{n}", "geral", lp.DOCUMENTADA, lp.RESPONDIDA, f"Pergunta fictícia número {n}?") for n in range(1, 5)]
        respostas = [resposta_http(corpo_esperado(lp.DOCUMENTADA, uso=(1, 2, 3, 4))), erro_503(),
                     resposta_http(corpo_esperado(lp.DOCUMENTADA, uso=None)), ac.FalhaDeTransporte("tempo_esgotado")]
        codigo, saida, _ = self.rodar(dados_de_entrada(casos), transporte=Transporte(lambda pergunta, numero: respostas[numero - 1]))
        self.assertEqual(codigo, lab_comum.CODIGO_DIVERGENCIA, saida)
        relatorio = self.ler_relatorio()
        uso = relatorio["resumo"]["uso_de_tokens"]
        self.assertEqual((uso["respostas_com_uso_informado"], uso["chamadas_sem_uso_informado"]), (1, 3))
        self.assertEqual(uso["soma_do_uso_informado"],
                         {"tokens_embeddings": 1, "tokens_entrada": 2, "tokens_raciocinio": 4, "tokens_saida": 3})
        self.assertEqual([item["tokens"] is None for item in relatorio["casos"]], [False, True, True, True],
                         "erro, falha de transporte e resposta sem uso ficam como ausentes, nunca como zero")
        self.assertIn("uso informado em 1 de 4 chamada(s)", saida)
        self.assertIn("não zero", saida)
        self.relatorio.unlink()
        codigo, saida, _ = self.rodar(dados_de_entrada(), transporte=Transporte(lambda pergunta, numero: erro_503()))
        uso = self.ler_relatorio()["resumo"]["uso_de_tokens"]
        self.assertEqual((uso["respostas_com_uso_informado"], uso["chamadas_sem_uso_informado"], uso["soma_do_uso_informado"]), (0, 3, None))
        self.assertIn("o chat não informou o uso em nenhuma resposta (desconhecido, não zero)", saida)


# --------------------------------------------------------------------------------------
# Transporte real, contra um servidor local
# --------------------------------------------------------------------------------------

class SilenciosoNosErros(ThreadingHTTPServer):
    """O cliente do teste fecha a conexão de propósito (por exemplo, ao passar do limite): isso não é um erro a mostrar."""

    def handle_error(self, request, client_address):
        pass


@contextlib.contextmanager
def servidor_local(tratar):
    """Servidor HTTP em 127.0.0.1, só para os testes. `tratar(manipulador)` escreve a resposta; `pedidos` registra o que chegou."""
    pedidos = []

    class Manipulador(BaseHTTPRequestHandler):
        def do_POST(self):
            corpo = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            pedidos.append((self.path, dict(self.headers.items()), corpo))
            tratar(self)

        def log_message(self, *argumentos):
            pass

    servidor = SilenciosoNosErros(("127.0.0.1", 0), Manipulador)
    fio = threading.Thread(target=servidor.serve_forever, daemon=True)
    fio.start()
    try:
        yield f"http://127.0.0.1:{servidor.server_address[1]}", pedidos
    finally:
        servidor.shutdown()
        servidor.server_close()
        fio.join(5)


def responder_com(manipulador, status, corpo, tipo="application/json", cabecalhos=()):
    manipulador.send_response(status)
    manipulador.send_header("Content-Type", tipo)
    manipulador.send_header("Content-Length", str(len(corpo)))
    for nome, valor in cabecalhos:
        manipulador.send_header(nome, valor)
    manipulador.end_headers()
    manipulador.wfile.write(corpo)


class TransporteRealTests(unittest.TestCase):
    CABECALHOS = {"Content-Type": "application/json", "Authorization": f"Bearer {TOKEN}"}

    def test_redirecionamento_nao_e_seguido_e_o_destino_dele_nao_recebe_a_pergunta_nem_o_token(self):
        with servidor_local(lambda m: responder_com(m, 200, b"{}")) as (url_b, pedidos_b), \
                servidor_local(lambda m: responder_com(m, 302, b"", cabecalhos=[("Location", url_b + "/api/perguntar")])) as (url_a, _):
            resposta = ac.enviar_http(url_a + "/api/perguntar", b'{"pergunta": "PERGUNTA-SECRETA"}', self.CABECALHOS, 5)
            resultado, transporte, acesso = ac.executar_caso(ac.Caso("c", "t", lp.DOCUMENTADA, lp.RESPONDIDA, "PERGUNTA-SECRETA?"),
                                                              ac.Destino(url_a, False), TOKEN, 5)
        self.assertEqual(resposta.status, 302)
        self.assertEqual(pedidos_b, [], "o destino do redirecionamento nunca foi contatado")
        self.assertEqual((resultado.resultado, resultado.erro, transporte, acesso), (ac.FALHA_HTTP, "redirecionamento", False, False))

    def test_resposta_de_erro_chega_com_status_e_corpo_e_o_pedido_leva_so_a_pergunta(self):
        with servidor_local(lambda m: responder_com(m, 503, erro_503().corpo)) as (url, pedidos):
            resposta = ac.enviar_http(url + "/api/perguntar", b'{"pergunta": "oi tudo bem"}', self.CABECALHOS, 5)
        self.assertEqual((resposta.status, ac._codigo_do_chat(resposta.corpo)), (503, lc.RESPOSTA_NAO_VERIFICADA))
        caminho, cabecalhos, corpo = pedidos[0]
        self.assertEqual((caminho, json.loads(corpo)), ("/api/perguntar", {"pergunta": "oi tudo bem"}))
        self.assertEqual({nome.lower(): valor for nome, valor in cabecalhos.items()}["content-type"], "application/json")

    def test_corpo_acima_de_128_kib_e_falha_de_transporte_com_ou_sem_content_length(self):
        def sem_tamanho(manipulador):
            manipulador.send_response(200)
            manipulador.send_header("Content-Type", "application/json")
            manipulador.end_headers()
            manipulador.wfile.write(b"x" * (ac.LIMITE_DA_RESPOSTA + 10))

        for rotulo, tratar in {"com Content-Length": lambda m: responder_com(m, 200, b"x" * (ac.LIMITE_DA_RESPOSTA + 1)),
                               "sem Content-Length": sem_tamanho}.items():
            with self.subTest(rotulo=rotulo), servidor_local(tratar) as (url, _):
                with self.assertRaises(ac.FalhaDeTransporte) as contexto:
                    ac.enviar_http(url + "/api/perguntar", b"{}", self.CABECALHOS, 5)
                self.assertEqual(contexto.exception.rotulo, "corpo_grande")

    def test_corpo_exatamente_no_limite_e_aceito(self):
        with servidor_local(lambda m: responder_com(m, 200, b"x" * ac.LIMITE_DA_RESPOSTA)) as (url, _):
            resposta = ac.enviar_http(url + "/api/perguntar", b"{}", self.CABECALHOS, 5)
        self.assertEqual(len(resposta.corpo), ac.LIMITE_DA_RESPOSTA)

    def test_timeout_e_conexao_recusada_sao_falhas_de_transporte_sem_repetir(self):
        def lento(manipulador):
            time.sleep(1.5)

        with servidor_local(lento) as (url, pedidos):
            with self.assertRaises(ac.FalhaDeTransporte) as contexto:
                ac.enviar_http(url + "/api/perguntar", b"{}", self.CABECALHOS, 0.3)
            self.assertEqual(contexto.exception.rotulo, "tempo_esgotado")
            self.assertEqual(len(pedidos), 1, "o avaliador não repete a chamada")
        with socket.socket() as livre:
            livre.bind(("127.0.0.1", 0))
            porta = livre.getsockname()[1]
        with self.assertRaises(ac.FalhaDeTransporte) as contexto:
            ac.enviar_http(f"http://127.0.0.1:{porta}/api/perguntar", b"{}", self.CABECALHOS, 5)
        self.assertEqual(contexto.exception.rotulo, "conexao")

    def test_o_certificado_e_sempre_verificado(self):
        codigo = (RAIZ / "scripts" / "avaliar_chat.py").read_text(encoding="utf-8")
        for proibido in ("_create_unverified_context", "CERT_NONE", "check_hostname = False", "verify=False", "install_opener"):
            self.assertNotIn(proibido, codigo)


# --------------------------------------------------------------------------------------
# Contra o chat real, em modo de demonstração (sem Azure)
# --------------------------------------------------------------------------------------

@contextlib.contextmanager
def chat_de_demonstracao():
    configuracao = lc.carregar_configuracao({}, modo=lc.MODO_DEMO)
    servidor = chat_web.uvicorn.Server(chat_web.uvicorn.Config(
        chat_web.create_app(configuracao), host="127.0.0.1", port=0, log_config=None, access_log=False, lifespan="on",
        http="h11", ws="none"))
    fio = threading.Thread(target=servidor.run, daemon=True)
    fio.start()
    limite = time.monotonic() + 30
    while not servidor.started and fio.is_alive() and time.monotonic() < limite:
        time.sleep(0.02)
    if not servidor.started:
        raise AssertionError("o chat local não iniciou")
    try:
        yield f"http://127.0.0.1:{servidor.servers[0].sockets[0].getsockname()[1]}"
    finally:
        servidor.should_exit = True
        fio.join(20)


@PRECISA_DO_SERVIDOR
class ContraOChatRealTests(BaseDoAvaliador):
    def test_a_demonstracao_real_passa_pelo_avaliador_com_os_cinco_tipos_e_fica_marcada(self):
        casos = CASOS[:2] + [
            caso("sem-01", "sem_evidencia", lp.SEM_EVIDENCIA, lp.RECUSADA, "Qual o preço mensal do seguro residencial?", []),
            CASOS[2],
            caso("amb-01", "ambigua", lp.AMBIGUA, lp.ESCLARECIMENTO, "Prazo?", []),
        ]
        with chat_de_demonstracao() as url:
            codigo, saida, _ = self.rodar(dados_de_entrada(casos), url=url, transporte=ac.enviar_http)
        self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)
        relatorio = self.ler_relatorio()
        self.assertEqual([item["resultado"] for item in relatorio["casos"]], [ac.APROVADO] * 5)
        self.assertEqual([item["tipo"] for item in relatorio["casos"]],
                         [lp.CONTRATACAO_INDIVIDUAL, lp.DOCUMENTADA, lp.SEM_EVIDENCIA, lp.FORA_DE_ESCOPO, lp.AMBIGUA])
        self.assertTrue(relatorio["casos"][0]["texto_individual_fixo"])
        self.assertEqual((relatorio["resumo"]["respostas_simuladas"], relatorio["destino"]["modo"], relatorio["identidade"]["tipo"]),
                         (5, "demonstracao_ou_local_loopback", "nenhuma"))
        self.assertIn("[DEMONSTRAÇÃO]", saida)
        conteudo = self.relatorio.read_text(encoding="utf-8")
        for oculto in ("127.0.0.1", "http://", "localhost"):
            self.assertNotIn(oculto, conteudo, "o endereço do destino não é gravado")


if __name__ == "__main__":
    unittest.main()
