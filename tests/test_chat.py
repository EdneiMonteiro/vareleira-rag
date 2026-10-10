import ast
import base64
import contextlib
import io
import json
import logging
import os
import re
import shlex
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from unittest import mock

import support  # noqa: F401  (configura o caminho dos scripts)
import chat_web
import lab_chat as lc
import lab_comum
import lab_geracao as lg
import lab_indexacao as li
import lab_politica as lp
from support import IndiceFalso, OpenAIFalso, OpenAIGeracaoFalso, RAIZ, copiar_pacote, erro_openai, indexar_pacote

try:
    from fastapi.testclient import TestClient
except ImportError:  # requirements/l200.txt não instalado: só os testes da interface HTTP deixam de rodar
    TestClient = None

PRECISA_DO_HTTP = unittest.skipIf(
    TestClient is None or chat_web.FastAPI is None or chat_web.uvicorn is None,
    "Instale requirements/l200.txt para testar a interface HTTP.")

BUSCA, MODELOS = "srch-vlr-exemplo", "ais-vlr-exemplo"
DIMENSOES = 8
ORIGEM_LOCAL = "http://127.0.0.1:8000"
TIPO_TENANT = "http://schemas.microsoft.com/identity/claims/tenantid"
TIPO_OBJETO = "http://schemas.microsoft.com/identity/claims/objectidentifier"
SUJEITO = "sujeito-sintetico"
PERGUNTA_INDIVIDUAL = "O meu seguro cobre este caso do meu imóvel?"
PERGUNTA_GERAL = "Qual é a regra geral para avisar a seguradora?"


def guid(numero):
    """GUIDs sintéticos montados na execução: nenhum identificador de ambiente fica escrito neste arquivo."""
    return str(uuid.UUID(int=numero))


TENANT, OUTRO_TENANT = guid(0xA1), guid(0xB2)


class Fixture:
    """Índice falso com os documentos sintéticos do L100, criado uma vez e só lido pelos testes."""

    pasta = indice = embeddings = None


def setUpModule():
    Fixture.pasta, inventario = copiar_pacote()
    Fixture.indice, Fixture.embeddings = indexar_pacote(inventario, BUSCA, MODELOS, DIMENSOES)


def tearDownModule():
    Fixture.pasta.cleanup()


def primeiro_trecho(entrada):
    """Id e texto do primeiro bloco <trecho> do pedido: o que a busca colocou em primeiro lugar."""
    achado = re.search(r'<trecho id="([^"]+)"[^>]*>\n(.*?)\n</trecho>', entrada, re.DOTALL)
    return achado.group(1), achado.group(2)


def responder(tipo, resposta="Resposta de teste.", evidencias=True, citacao=None, extras=None):
    def montar(argumentos):
        lista = []
        if evidencias:
            identificador, texto = primeiro_trecho(argumentos["input"])
            lista = [{"fonte": identificador, "citacao": citacao or texto.strip()[-60:]}]
        return {"tipo": tipo, "resposta": resposta, "evidencias": lista, **(extras or {})}

    return montar


def servico_rag(geracao, indice=None, embeddings=None, modo="vetorial", k=5):
    """O serviço real do chat (ajudantes do L100 e política) sobre o índice falso e os dublês da OpenAI."""
    recuperador = lg.Recuperador(indice or Fixture.indice,
                                 li.ClienteEmbeddings(embeddings or Fixture.embeddings, "embeddings", DIMENSOES))
    return lc.ServicoRag(recuperador, lg.ClienteGeracao(geracao, "geracao", MODELOS), modo, k)


def principal(tenant=TENANT, sujeito=SUJEITO, longos=False, claims=None):
    if claims is None:
        claims = [{"typ": "iss", "val": "https://emissor.exemplo.invalido/"},
                  {"typ": TIPO_TENANT if longos else "tid", "val": tenant},
                  {"typ": TIPO_OBJETO if longos else "oid", "val": sujeito}]
    return {"auth_typ": "aad", "name_typ": "name", "role_typ": "roles", "claims": claims}


def codificar(dados):
    return base64.b64encode(json.dumps(dados).encode("utf-8")).decode("ascii")


def autenticado(tenant=TENANT):
    return {lc.CABECALHO_PRINCIPAL: codificar(principal(tenant))}


def ambiente(mudancas=None, sem=()):
    base = {lc.VAR_EXIGIR_AUTENTICACAO: "true", lc.VAR_TENANT_AUTORIZADO: TENANT, lc.VAR_BUSCA: BUSCA, lc.VAR_MODELOS: MODELOS}
    base.update(mudancas or {})
    return {nome: valor for nome, valor in base.items() if nome not in sem}


def config(**mudancas):
    base = lc.ConfiguracaoChat(modo=lc.MODO_NUVEM, host="0.0.0.0", exigir_autenticacao=True,
                               tenants_autorizados=frozenset({TENANT}), busca=BUSCA, modelos=MODELOS)
    return replace(base, **mudancas)


def config_demo(**mudancas):
    return replace(lc.carregar_configuracao({}, modo=lc.MODO_DEMO), **mudancas)


def resposta_de(pergunta):
    evidencia = lc.EvidenciaChat("VLAR-CG-1_0-004", "as coberturas adicionais são contratadas à parte",
                                 "vareleira-lar/condicoes-gerais-v1.0.md", "1.0", "Vareleira Lar — Condições Gerais",
                                 "3. Coberturas adicionais", "3.1")
    return lc.RespostaChat(lp.DOCUMENTADA, lp.RESPONDIDA, f"Resposta para: {pergunta}", "", (evidencia,),
                           lc.UsoChat(1, 2, 3, 4))


class ServicoFalso:
    """Serviço de teste: registra cada pergunta e a thread que a atendeu, e pode esperar ou falhar."""

    def __init__(self, resposta=resposta_de, erro=None, esperar=None):
        self.resposta, self.erro, self.esperar = resposta, erro, esperar
        self.perguntas, self.threads = [], []

    def perguntar(self, pergunta):
        self.perguntas.append(pergunta)
        self.threads.append(threading.current_thread().name)
        if self.esperar is not None:
            self.esperar(pergunta)
        if self.erro is not None:
            raise self.erro
        return self.resposta(pergunta)


@contextlib.contextmanager
def servidor(servico, configuracao=None):
    app = chat_web.create_app(configuracao or config(), lambda _: servico)
    with TestClient(app, base_url=ORIGEM_LOCAL) as cliente:
        yield cliente


def perguntar_pela_api(cliente, corpo=None, cabecalhos=None, **opcoes):
    return cliente.post("/api/perguntar", json={"pergunta": PERGUNTA_GERAL} if corpo is None else corpo,
                        headers=autenticado() if cabecalhos is None else cabecalhos, **opcoes)


# --------------------------------------------------------------------------------------
# Configuração
# --------------------------------------------------------------------------------------

class ConfiguracaoTests(unittest.TestCase):
    def test_na_nuvem_nada_e_assumido_quando_faltam_as_variaveis(self):
        with self.assertRaises(lc.ErroConfiguracao) as contexto:
            lc.carregar_configuracao({})
        for variavel in (lc.VAR_EXIGIR_AUTENTICACAO, lc.VAR_BUSCA, lc.VAR_MODELOS):
            self.assertIn(variavel, str(contexto.exception))
        self.assertEqual(contexto.exception.codigo, lab_comum.CODIGO_USO)

    def test_variavel_em_branco_vale_como_ausente(self):
        with self.assertRaises(lc.ErroConfiguracao) as contexto:
            lc.carregar_configuracao(ambiente({lc.VAR_BUSCA: "   "}))
        self.assertIn(lc.VAR_BUSCA, str(contexto.exception))

    def test_configuracao_completa_usa_os_padroes_do_l200(self):
        configuracao = lc.carregar_configuracao(ambiente(), host="0.0.0.0")
        self.assertEqual((configuracao.modo, configuracao.host, configuracao.exigir_autenticacao),
                         (lc.MODO_NUVEM, "0.0.0.0", True))
        self.assertEqual(configuracao.tenants_autorizados, frozenset({TENANT}))
        self.assertEqual((configuracao.busca, configuracao.modelos), (BUSCA, MODELOS))
        self.assertEqual(lc.INDICE_PADRAO, "vareleira-lar-l200")
        self.assertEqual((configuracao.indice, configuracao.deployment_embeddings, configuracao.dimensoes),
                         ("vareleira-lar-l200", li.DEPLOYMENT_PADRAO, 1536))
        self.assertEqual((configuracao.deployment_geracao, configuracao.esforco, configuracao.modo_busca, configuracao.k),
                         (lg.DEPLOYMENT_GERACAO_PADRAO, "low", "hibrida", 5))
        self.assertEqual((configuracao.max_concorrencia, configuracao.timeout_segundos), (4, 90.0))
        self.assertEqual((configuracao.tenant_id, configuracao.client_id), (None, None))

    def test_indice_padrao_e_o_da_ingestao_e_nao_o_de_referencia_do_l100(self):
        if not (RAIZ / "scripts" / "lab_ingestao.py").is_file():
            self.skipTest("lab_ingestao.py não encontrado: o índice padrão não foi comparado com o da ingestão.")
        import lab_ingestao

        self.assertEqual(lc.INDICE_PADRAO, lab_ingestao.INDICE_PADRAO)
        self.assertNotEqual(lc.INDICE_PADRAO, li.INDICE_PADRAO, "o chat não consulta por padrão o índice do L100")

    def test_valores_explicitos_substituem_os_padroes(self):
        configuracao = lc.carregar_configuracao(ambiente({
            lc.VAR_TENANT_AUTORIZADO: f"{TENANT.upper()}, {OUTRO_TENANT}", lc.VAR_TENANT_ID: OUTRO_TENANT,
            lc.VAR_CLIENT_ID: guid(7).upper(), lc.VAR_INDICE: "index-outro", lc.VAR_DEPLOYMENT_EMBEDDINGS: "emb.v2",
            lc.VAR_DIMENSOES: "3072", lc.VAR_DEPLOYMENT_GERACAO: "ger-v2", lc.VAR_ESFORCO: "none",
            lc.VAR_MODO_BUSCA: "texto", lc.VAR_K: "3", lc.VAR_MAX_CONCORRENCIA: "2", lc.VAR_TIMEOUT: "30.5"}))
        self.assertEqual(configuracao.tenants_autorizados, frozenset({TENANT, OUTRO_TENANT}))
        self.assertEqual((configuracao.tenant_id, configuracao.client_id), (OUTRO_TENANT, guid(7)))
        self.assertEqual((configuracao.indice, configuracao.deployment_embeddings, configuracao.dimensoes),
                         ("index-outro", "emb.v2", 3072))
        self.assertEqual((configuracao.deployment_geracao, configuracao.esforco, configuracao.modo_busca, configuracao.k),
                         ("ger-v2", "none", "texto", 3))
        self.assertEqual((configuracao.max_concorrencia, configuracao.timeout_segundos), (2, 30.5))

    def test_valor_invalido_e_recusado_sem_repetir_o_valor(self):
        invalidos = (lc.VAR_BUSCA, lc.VAR_MODELOS, lc.VAR_INDICE, lc.VAR_DEPLOYMENT_EMBEDDINGS, lc.VAR_DIMENSOES,
                     lc.VAR_DEPLOYMENT_GERACAO, lc.VAR_ESFORCO, lc.VAR_MODO_BUSCA, lc.VAR_K, lc.VAR_MAX_CONCORRENCIA,
                     lc.VAR_TIMEOUT, lc.VAR_TENANT_ID, lc.VAR_CLIENT_ID, lc.VAR_TENANT_AUTORIZADO,
                     lc.VAR_EXIGIR_AUTENTICACAO)
        for nome in invalidos:
            with self.subTest(variavel=nome):
                with self.assertRaises(lc.ErroConfiguracao) as contexto:
                    lc.carregar_configuracao(ambiente({nome: "Valor/ruim xyz"}))
                self.assertIn(nome, str(contexto.exception))
                self.assertNotIn("ruim xyz", str(contexto.exception))

    def test_nomes_que_formam_enderecos_aceitam_so_o_formato_do_azure(self):
        for busca in ("meu-site.exemplo/", "srch.exemplo", "https://srch.search.windows.net", "A"):
            with self.subTest(busca=busca), self.assertRaises(lc.ErroConfiguracao):
                lc.carregar_configuracao(ambiente({lc.VAR_BUSCA: busca}))

    def test_todos_os_problemas_aparecem_de_uma_vez(self):
        with self.assertRaises(lc.ErroConfiguracao) as contexto:
            lc.carregar_configuracao(ambiente({lc.VAR_K: "999", lc.VAR_ESFORCO: "extremo"}, sem=(lc.VAR_MODELOS,)))
        for variavel in (lc.VAR_K, lc.VAR_ESFORCO, lc.VAR_MODELOS):
            self.assertIn(variavel, str(contexto.exception))

    def test_na_nuvem_a_autenticacao_precisa_ser_true_e_explicita(self):
        for mudancas, sem in (({}, (lc.VAR_EXIGIR_AUTENTICACAO,)), ({lc.VAR_EXIGIR_AUTENTICACAO: "false"}, ())):
            with self.subTest(mudancas=mudancas, sem=sem), self.assertRaises(lc.ErroConfiguracao) as contexto:
                lc.carregar_configuracao(ambiente(mudancas, sem))
            self.assertIn(lc.VAR_EXIGIR_AUTENTICACAO, str(contexto.exception))

    def test_com_autenticacao_o_tenant_autorizado_e_obrigatorio(self):
        with self.assertRaises(lc.ErroConfiguracao) as contexto:
            lc.carregar_configuracao(ambiente(sem=(lc.VAR_TENANT_AUTORIZADO,)))
        self.assertIn(lc.VAR_TENANT_AUTORIZADO, str(contexto.exception))

    def test_demonstracao_nao_precisa_de_azure_nem_de_autenticacao(self):
        configuracao = lc.carregar_configuracao({}, modo=lc.MODO_DEMO)
        self.assertEqual((configuracao.modo, configuracao.exigir_autenticacao, configuracao.busca), (lc.MODO_DEMO, False, None))

    def test_modo_local_ainda_exige_os_recursos_do_azure(self):
        with self.assertRaises(lc.ErroConfiguracao) as contexto:
            lc.carregar_configuracao({}, modo=lc.MODO_LOCAL)
        self.assertIn(lc.VAR_BUSCA, str(contexto.exception))
        self.assertNotIn(lc.VAR_EXIGIR_AUTENTICACAO, str(contexto.exception))
        local = lc.carregar_configuracao({lc.VAR_BUSCA: BUSCA, lc.VAR_MODELOS: MODELOS}, modo=lc.MODO_LOCAL)
        self.assertFalse(local.exigir_autenticacao)

    def test_modos_sem_autenticacao_so_aceitam_loopback(self):
        for modo in (lc.MODO_DEMO, lc.MODO_LOCAL):
            for host in ("127.0.0.1", "localhost", "::1", "[::1]", "127.0.0.2"):
                with self.subTest(modo=modo, host=host):
                    lc.carregar_configuracao(ambiente(), modo=modo, host=host)
            for host in ("0.0.0.0", "::", "192.0.2.10", "exemplo.invalido", ""):
                with self.subTest(modo=modo, host=host), self.assertRaises(lc.ErroConfiguracao) as contexto:
                    lc.carregar_configuracao(ambiente(), modo=modo, host=host)
                self.assertIn("--host", str(contexto.exception))

    def test_a_nuvem_aceita_qualquer_endereco_de_escuta(self):
        self.assertEqual(lc.carregar_configuracao(ambiente(), host="0.0.0.0").host, "0.0.0.0")

    def test_destino_da_requisicao_so_e_conferido_nos_modos_locais(self):
        esperados = {"localhost": True, "localhost:8000": True, "127.0.0.1": True, "127.0.0.1:8000": True, "[::1]:8000": True,
                     "[::1]": True, "": False, None: False, "exemplo.invalido:80": False, "0.0.0.0": False,
                     "localhost.exemplo.invalido": False, "127.0.0.1.exemplo.invalido": False, "[::]:8000": False}
        for modo in (lc.MODO_LOCAL, lc.MODO_DEMO):
            for host, esperado in esperados.items():
                with self.subTest(modo=modo, host=host):
                    self.assertIs(lc.host_permitido(modo, host), esperado)
        self.assertTrue(lc.host_permitido(lc.MODO_NUVEM, "qualquer.exemplo.invalido"))
        self.assertTrue(lc.host_permitido(lc.MODO_NUVEM, None))

    def test_o_modo_vem_da_linha_de_comando_e_nunca_do_ambiente(self):
        with self.assertRaises(lc.ErroConfiguracao):
            lc.carregar_configuracao({"VARELEIRA_MODO": "demonstracao", "VARELEIRA_DEMO": "true", "VARELEIRA_LOCAL": "true"})

    def test_configuracao_montada_a_mao_tambem_e_validada(self):
        lc.validar_configuracao(config())
        for rotulo, configuracao in {
            "padrão sem nada": lc.ConfiguracaoChat(),
            "nuvem sem autenticação": config(exigir_autenticacao=False),
            "autenticação sem tenant": config(tenants_autorizados=frozenset()),
            "sem busca": config(busca=None),
            "sem modelos": config(modelos=""),
            "concorrência zero": config(max_concorrencia=0),
            "tempo curto demais": config(timeout_segundos=0.1),
            "modo desconhecido": config(modo="outro"),
            "demonstração fora do loopback": config(modo=lc.MODO_DEMO, host="0.0.0.0"),
        }.items():
            with self.subTest(rotulo=rotulo), self.assertRaises(lc.ErroConfiguracao):
                lc.validar_configuracao(configuracao)

    def test_o_resumo_do_registro_nao_traz_recursos_tenant_nem_identidade(self):
        resumo = lc.resumo_publico(config(tenant_id=OUTRO_TENANT, client_id=guid(7)))
        for oculto in (BUSCA, MODELOS, TENANT, OUTRO_TENANT, guid(7)):
            self.assertNotIn(oculto, resumo)
        for visivel in ("indice=vareleira-lar-l200", "dimensoes=1536", "esforco=low", "concorrencia=4"):
            self.assertIn(visivel, resumo)


# --------------------------------------------------------------------------------------
# Identidade de quem usa o chat
# --------------------------------------------------------------------------------------

class PrincipalTests(unittest.TestCase):
    def validar(self, cabecalho, tenants=(TENANT,)):
        return lc.validar_principal(cabecalho, tenants)

    def test_identidade_valida_aceita_nomes_curtos_e_uris_longas_de_claims(self):
        for longos in (False, True):
            with self.subTest(longos=longos):
                resultado = self.validar(codificar(principal(longos=longos)))
                self.assertEqual((resultado.tenant, resultado.sujeito), (TENANT, SUJEITO))

    def test_sub_basta_como_sujeito_e_a_comparacao_do_tenant_ignora_a_caixa(self):
        claims = [{"typ": "tid", "val": TENANT.upper()}, {"typ": "sub", "val": "assunto"}, {"typ": TIPO_TENANT, "val": TENANT}]
        self.assertEqual(self.validar(codificar(principal(claims=claims))).sujeito, "assunto")

    def test_base64_sem_preenchimento_e_espacos_nas_pontas_sao_aceitos(self):
        cabecalho = codificar(principal())
        self.assertEqual(self.validar(f" {cabecalho.rstrip('=')} ").tenant, TENANT)

    def test_ausente_ou_ilegivel_e_401(self):
        invalidos = {
            "ausente": None,
            "vazio": "   ",
            "texto que não é base64": "isto nao e base64!",
            "base64 de um texto qualquer": base64.b64encode(b"ola").decode("ascii"),
            "bytes que não são UTF-8": base64.b64encode(b'{"claims": "\xff"}').decode("ascii"),
            "JSON que não é objeto": codificar([1, 2, 3]),
            "sem claims": codificar({"auth_typ": "aad"}),
            "claims vazia": codificar({"claims": []}),
            "claims que não é lista": codificar({"claims": "tid"}),
            "claim que não é objeto": codificar({"claims": ["tid"]}),
            "claim sem valor": codificar({"claims": [{"typ": "tid"}]}),
            "claim com valor numérico": codificar({"claims": [{"typ": "tid", "val": 1}]}),
            "sem tenant": codificar(principal(claims=[{"typ": "oid", "val": SUJEITO}])),
            "tenant vazio": codificar(principal(tenant="")),
            "tenant que não é GUID": codificar(principal(tenant="contoso.exemplo")),
            "dois tenants diferentes": codificar(principal(claims=[
                {"typ": "tid", "val": TENANT}, {"typ": TIPO_TENANT, "val": OUTRO_TENANT}, {"typ": "oid", "val": SUJEITO}])),
            "sem sujeito": codificar(principal(claims=[{"typ": "tid", "val": TENANT}])),
            "sujeito vazio": codificar(principal(sujeito="  ")),
            "cabeçalho enorme": "A" * (lc.LIMITE_DO_CABECALHO + 1),
        }
        for rotulo, cabecalho in invalidos.items():
            with self.subTest(rotulo=rotulo), self.assertRaises(lc.ErroChat) as contexto:
                self.validar(cabecalho)
            self.assertEqual(contexto.exception.codigo, lc.NAO_AUTENTICADO)

    def test_tenant_nao_autorizado_e_403_e_sem_lista_nada_e_autorizado(self):
        for tenants in ((OUTRO_TENANT,), (), ("",)):
            with self.subTest(tenants=tenants), self.assertRaises(lc.ErroChat) as contexto:
                self.validar(codificar(principal()), tenants)
            self.assertEqual(contexto.exception.codigo, lc.NAO_AUTORIZADO)


# --------------------------------------------------------------------------------------
# Pedido
# --------------------------------------------------------------------------------------

class PedidoTests(unittest.TestCase):
    @staticmethod
    def ler(dados, tipo="application/json"):
        corpo = dados if isinstance(dados, bytes) else json.dumps(dados).encode("utf-8")
        return lc.ler_pedido(corpo, tipo)

    def codigo(self, dados, tipo="application/json"):
        with self.assertRaises(lc.ErroChat) as contexto:
            self.ler(dados, tipo)
        return contexto.exception.codigo

    def test_pedido_valido_leva_uma_pergunta_limpa_e_um_id_opcional(self):
        pedido = self.ler({"pergunta": "  Qual é o prazo?\n", "id": "navegador-0001"}, "application/json; charset=utf-8")
        self.assertEqual((pedido.pergunta, pedido.id_cliente), ("Qual é o prazo?", "navegador-0001"))
        self.assertIsNone(self.ler({"pergunta": "Qual é o prazo?"}).id_cliente)

    def test_so_aceita_json_e_um_objeto(self):
        self.assertEqual(self.codigo({"pergunta": "oi tudo"}, "text/plain"), lc.TIPO_DE_CONTEUDO_INVALIDO)
        self.assertEqual(self.codigo({"pergunta": "oi tudo"}, None), lc.TIPO_DE_CONTEUDO_INVALIDO)
        for corpo in (b"", b"{nao json", b"\xff\xfe", b'["pergunta"]', b'"pergunta"', b"3", b"null"):
            with self.subTest(corpo=corpo):
                self.assertEqual(self.codigo(corpo), lc.JSON_INVALIDO)

    def test_uma_pergunta_por_pedido_sem_historico_nem_opcoes_de_depuracao(self):
        for extra in ({"debug": True}, {"historico": [{"papel": "pessoa", "texto": "antes"}]}, {"mensagens": []},
                      {"modelo": "outro"}, {"stream": True}, {"contexto": "texto"}):
            with self.subTest(extra=extra):
                self.assertEqual(self.codigo({"pergunta": "Qual é o prazo?", **extra}), lc.CAMPOS_NAO_PERMITIDOS)

    def test_pergunta_ausente_vazia_ou_de_outro_tipo(self):
        self.assertEqual(self.codigo({}), lc.PERGUNTA_VAZIA)
        self.assertEqual(self.codigo({"pergunta": " \n\t "}), lc.PERGUNTA_VAZIA)
        for valor in (None, 3, ["oi"], {"texto": "oi"}, True):
            with self.subTest(valor=valor):
                self.assertEqual(self.codigo({"pergunta": valor}), lc.PERGUNTA_INVALIDA)

    def test_caracteres_de_controle_sao_recusados_e_os_de_formatacao_removidos(self):
        for texto in ("a\u0000b", "a\u0007b", "a\u009fb", "a\ud800b"):
            with self.subTest(texto=texto):
                self.assertEqual(self.codigo({"pergunta": texto}), lc.PERGUNTA_INVALIDA)
        self.assertEqual(self.ler({"pergunta": "Qual é\u202e o\u200b prazo?\nE a franquia?"}).pergunta,
                         "Qual é o prazo?\nE a franquia?")

    def test_limite_da_pergunta_e_o_do_console(self):
        self.assertEqual(lc.LIMITE_DA_PERGUNTA, lg.LIMITE_DA_PERGUNTA)
        limite = lc.LIMITE_DA_PERGUNTA
        self.assertEqual(len(self.ler({"pergunta": f"  {'a' * limite}  "}).pergunta), limite)
        self.assertEqual(self.codigo({"pergunta": "a" * (limite + 1)}), lc.PERGUNTA_LONGA)

    def test_id_do_navegador_tem_formato_fixo(self):
        for valor in ("curto", "com espaço no meio", "a" * 65, "id/com/barra", 12345678, ["abcdefgh"]):
            with self.subTest(valor=valor):
                self.assertEqual(self.codigo({"pergunta": "Qual é o prazo?", "id": valor}), lc.ID_INVALIDO)
        self.assertEqual(self.ler({"pergunta": "Qual é o prazo?", "id": str(uuid.UUID(int=5))}).id_cliente, guid(5))


# --------------------------------------------------------------------------------------
# Resposta pública
# --------------------------------------------------------------------------------------

class RespostaPublicaTests(unittest.TestCase):
    def test_limpar_texto_remove_controles_normaliza_e_limita(self):
        self.assertEqual(lc.limpar_texto("  a\t\tb \u0000 c\u202e\r\n\r\n\r\n\r\nd ", 100), "a b c\n\nd")
        self.assertEqual(lc.limpar_texto("a" * 50, 10), "a" * 9 + "…")
        self.assertEqual(lc.limpar_texto(None, 10), "")

    def test_evidencias_saem_so_com_os_campos_publicos_e_higienizados(self):
        trecho = {"id": "VLAR-X-1<b>", "fonte": "vareleira-lar/arquivo.md\u0007", "versao": "1.0<script>",
                  "titulo_documento": "Título\u202e do documento", "secao": "3. Seção\n\n\n\nfinal", "clausulas": "3.1",
                  "conteudo": "texto do trecho", "vetor": [0.1], "@search.score": 9.9}
        decisao = lp.Decisao(lp.RESPONDIDA, lp.DOCUMENTADA, lp.DOCUMENTADA, "ok\u0000 texto", "", (
            lp.Evidencia("VLAR-X-1<b>", "citação \u0007 literal"),), ())
        resposta = lc.montar_resposta(decisao, [trecho]).a_dict()
        self.assertEqual(resposta["texto"], "ok texto")
        self.assertEqual(resposta["evidencias"], [{
            "id": "VLAR-X-1b", "citacao": "citação literal", "fonte": "vareleira-lar/arquivo.md", "versao": "1.0script",
            "documento": "Título do documento", "secao": "3. Seção\n\nfinal", "clausulas": "3.1"}])

    def test_ids_longos_de_projecao_com_o_mesmo_prefixo_chegam_inteiros_distintos_e_localizaveis(self):
        prefixo = "VLAR-L200-" + "-".join(f"SECAO{n:03d}" for n in range(1, 20))
        ids = [f"{prefixo}-CLAUSULA-{letra}" for letra in "AB"]
        self.assertEqual(ids[0][:128], ids[1][:128], "o prefixo passa de 128 caracteres: um corte em 128 igualaria os dois")
        resultados = [{"id": id_, "fonte": f"arquivo-{n}.md", "versao": "1.0", "titulo_documento": f"Documento {n}",
                       "secao": f"Seção {n}", "clausulas": f"{n}.1"} for n, id_ in enumerate(ids, 1)]
        decisao = lp.Decisao(lp.RESPONDIDA, lp.DOCUMENTADA, lp.DOCUMENTADA, "ok", "", tuple(
            lp.Evidencia(id_, f"citação literal {n}") for n, id_ in enumerate(ids, 1)), ())
        evidencias = lc.montar_resposta(decisao, resultados).a_dict()["evidencias"]
        self.assertEqual([item["id"] for item in evidencias], ids)
        por_id = {item["id"]: item for item in resultados}
        self.assertEqual([por_id[item["id"]]["titulo_documento"] for item in evidencias], ["Documento 1", "Documento 2"])
        self.assertEqual([item["documento"] for item in evidencias], ["Documento 1", "Documento 2"])
        enorme = lp.Decisao(lp.RESPONDIDA, lp.DOCUMENTADA, lp.DOCUMENTADA, "ok", "", (lp.Evidencia("A" * 1030, "citação literal"),), ())
        self.assertEqual(len(lc.montar_resposta(enorme, []).a_dict()["evidencias"][0]["id"]), 1024,
                         "o limite oficial da chave de documento do Azure AI Search continua valendo")

    def test_resposta_descartada_ou_fora_do_vocabulario_nunca_vira_resposta(self):
        for decisao in (lp.Decisao(lp.DESCARTADA, lp.DOCUMENTADA, lp.DOCUMENTADA, "", "", (), ("a citação é falsa",)),
                        lp.Decisao("inventada", lp.DOCUMENTADA, lp.DOCUMENTADA, "texto", "", (), ()),
                        lp.Decisao(lp.RESPONDIDA, "tipo-novo", "tipo-novo", "texto", "", (), ()),
                        lp.Decisao(lp.RESPONDIDA, lp.DOCUMENTADA, lp.DOCUMENTADA, "\u0000\u200b", "", (), ())):
            with self.subTest(situacao=decisao.situacao), self.assertRaises(lc.ErroChat) as contexto:
                lc.montar_resposta(decisao, [])
            self.assertEqual(contexto.exception.codigo, lc.RESPOSTA_NAO_VERIFICADA)

    def test_uso_so_tem_contagens_inteiras_nao_negativas(self):
        self.assertEqual(lc.UsoChat(3, "4", None, -1).a_dict(),
                         {"tokens_embeddings": 3, "tokens_entrada": 4, "tokens_saida": 0, "tokens_raciocinio": 0})

    def test_causa_do_registro_so_aceita_vocabulario_fechado(self):
        self.assertEqual(lc.ErroChat(lc.INDISPONIVEL, "rede").causa, "rede")
        self.assertEqual(lc.ErroChat(lc.INDISPONIVEL, "Texto livre: da exceção").causa, lc.INDISPONIVEL)
        self.assertEqual(lc.ErroChat(lc.OCUPADO).mensagem, lc.MENSAGENS[lc.OCUPADO])

    def test_todo_codigo_publico_tem_mensagem_e_status_http(self):
        self.assertEqual(set(chat_web.STATUS_HTTP), set(lc.MENSAGENS))
        for codigo, mensagem in lc.MENSAGENS.items():
            self.assertTrue(mensagem.strip(), codigo)


# --------------------------------------------------------------------------------------
# Consulta com os ajudantes do L100 e a política
# --------------------------------------------------------------------------------------

class ServicoRagTests(unittest.TestCase):
    def setUp(self):
        self.geracao = OpenAIGeracaoFalso()
        self.geracao.responder = responder(lp.DOCUMENTADA)
        self.servico = servico_rag(self.geracao)

    def test_pergunta_documentada_usa_a_busca_o_pedido_e_a_politica_do_l100(self):
        resposta = self.servico.perguntar(PERGUNTA_GERAL)
        self.assertEqual((resposta.tipo, resposta.situacao, resposta.texto, resposta.aviso),
                         (lp.DOCUMENTADA, lp.RESPONDIDA, "Resposta de teste.", ""))
        self.assertEqual(len(resposta.evidencias), 1)
        evidencia = resposta.evidencias[0].a_dict()
        self.assertRegex(evidencia["id"], r"^VLAR-[A-Z]+-1_0-\d+$")
        self.assertTrue(evidencia["citacao"])
        self.assertEqual((evidencia["versao"], evidencia["fonte"].endswith(".md")), ("1.0", True))
        self.assertEqual(resposta.uso.a_dict()["tokens_saida"], 40)
        self.assertEqual(resposta.uso.a_dict()["tokens_raciocinio"], 10)
        self.assertGreater(resposta.uso.tokens_embeddings, 0)
        chamada = self.geracao.chamadas[0]
        self.assertEqual(chamada["instructions"], lp.INSTRUCOES_COMPLETAS)
        self.assertEqual(chamada["text"], {"format": lp.CONTRATO_COMPLETO.esquema})
        self.assertTrue(chamada["input"].endswith(f"Pergunta: {PERGUNTA_GERAL}"))
        self.assertIs(chamada["store"], False)

    def test_cada_pergunta_e_independente_e_o_modelo_so_recebe_a_atual(self):
        self.servico.perguntar("MARCADOR-ALFA primeira pergunta de teste")
        self.servico.perguntar("MARCADOR-BETA segunda pergunta de teste")
        primeira, segunda = (chamada["input"] for chamada in self.geracao.chamadas)
        self.assertIn("MARCADOR-ALFA", primeira)
        self.assertNotIn("MARCADOR-BETA", primeira)
        self.assertIn("MARCADOR-BETA", segunda)
        self.assertNotIn("MARCADOR-ALFA", segunda, "nada da pergunta anterior chega ao modelo")
        for chamada in self.geracao.chamadas:
            self.assertEqual(chamada["instructions"], lp.INSTRUCOES_COMPLETAS)

    def test_contratacao_individual_mostra_so_o_texto_fixo_da_politica(self):
        for rotulo, pergunta, tipo_do_modelo in (("regra por palavras", PERGUNTA_INDIVIDUAL, lp.DOCUMENTADA),
                                                 ("classificação do modelo", PERGUNTA_GERAL, lp.CONTRATACAO_INDIVIDUAL)):
            with self.subTest(rotulo=rotulo):
                self.geracao.responder = responder(tipo_do_modelo, resposta="Sim, o seu seguro cobre isso e será pago.")
                resposta = self.servico.perguntar(pergunta)
                self.assertEqual((resposta.tipo, resposta.situacao), (lp.CONTRATACAO_INDIVIDUAL, lp.RESPONDIDA))
                self.assertEqual((resposta.texto, resposta.aviso), (lp.TEXTO_SEM_VEREDITO, lp.AVISO_CONTRATACAO_INDIVIDUAL))
                self.assertTrue(resposta.evidencias)
                self.assertNotIn("será pago", json.dumps(resposta.a_dict(), ensure_ascii=False))

    def test_recusas_e_esclarecimento_usam_os_textos_da_politica(self):
        for tipo, situacao, texto in ((lp.SEM_EVIDENCIA, lp.RECUSADA, lp.MENSAGEM_SEM_EVIDENCIA),
                                      (lp.FORA_DE_ESCOPO, lp.RECUSADA, lp.MENSAGEM_FORA_DE_ESCOPO),
                                      (lp.AMBIGUA, lp.ESCLARECIMENTO, lp.MENSAGEM_ESCLARECIMENTO)):
            with self.subTest(tipo=tipo):
                self.geracao.responder = responder(tipo, resposta="Sim, cobre tudo!" if tipo != lp.AMBIGUA else "",
                                                   evidencias=False)
                resposta = self.servico.perguntar(PERGUNTA_GERAL)
                self.assertEqual((resposta.tipo, resposta.situacao, resposta.texto, resposta.evidencias),
                                 (tipo, situacao, texto, ()))
                self.assertNotIn("cobre tudo", json.dumps(resposta.a_dict(), ensure_ascii=False))

    def test_nada_alem_da_decisao_da_politica_chega_a_resposta(self):
        self.geracao.responder = responder(lp.DOCUMENTADA, extras={"debug": "SAIDA-BRUTA-DO-MODELO", "raciocinio": "PENSAMENTO-INTERNO"})
        resposta = json.dumps(self.servico.perguntar(PERGUNTA_GERAL).a_dict(), ensure_ascii=False)
        for oculto in ("SAIDA-BRUTA-DO-MODELO", "PENSAMENTO-INTERNO", '"debug"', "gpt-5", "<trecho"):
            self.assertNotIn(oculto, resposta)

    def test_resposta_sem_prova_e_descartada_e_o_texto_do_modelo_nao_aparece(self):
        self.geracao.responder = responder(lp.DOCUMENTADA, resposta="Resposta inventada.",
                                           citacao="Esta frase não existe em nenhum trecho recuperado.")
        with self.assertRaises(lc.ErroChat) as contexto:
            self.servico.perguntar(PERGUNTA_GERAL)
        self.assertEqual(contexto.exception.codigo, lc.RESPOSTA_NAO_VERIFICADA)
        self.assertNotIn("inventada", f"{contexto.exception} {contexto.exception.mensagem}")

    def test_sem_trechos_o_modelo_nao_e_chamado(self):
        servico = servico_rag(self.geracao, indice=IndiceFalso(), embeddings=OpenAIFalso(dimensoes=DIMENSOES))
        resposta = servico.perguntar(PERGUNTA_GERAL)
        self.assertEqual((resposta.tipo, resposta.situacao, resposta.texto), (lp.SEM_EVIDENCIA, lp.RECUSADA, lp.MENSAGEM_SEM_EVIDENCIA))
        self.assertEqual(self.geracao.chamadas, [])
        self.assertGreater(resposta.uso.tokens_embeddings, 0)
        self.assertEqual(resposta.uso.tokens_entrada, 0)

    def test_falhas_da_busca_e_do_modelo_chegam_inalteradas_a_quem_chamou(self):
        class IndiceQuebrado(IndiceFalso):
            def consultar(self, texto, vetor, k):
                raise RuntimeError("falha da busca")

        with self.assertRaises(RuntimeError):
            servico_rag(self.geracao, indice=IndiceQuebrado()).perguntar(PERGUNTA_GERAL)
        self.geracao.erro = erro_openai("RateLimitError", 429)
        with self.assertRaises(lab_comum.ErroLab) as contexto:
            self.servico.perguntar(PERGUNTA_GERAL)
        self.assertEqual(lc.classificar_erro(contexto.exception).causa, "limite_do_servico")

    def test_modos_de_busca_e_quantidade_de_trechos_vem_da_configuracao(self):
        servico = servico_rag(self.geracao, modo="texto", k=2)
        servico.perguntar("coberturas adicionais")
        self.assertEqual(len(re.findall(r"<trecho ", self.geracao.chamadas[0]["input"])), 2)


# --------------------------------------------------------------------------------------
# Erros
# --------------------------------------------------------------------------------------

class ClassificacaoDeErrosTests(unittest.TestCase):
    def test_cada_falha_vira_um_codigo_publico_e_uma_causa_curta(self):
        segredo = "SEGREDO-NA-EXCECAO"
        envolvido = lab_comum.ErroLab(segredo, 2)
        envolvido.__cause__ = erro_openai("AuthenticationError", 401, segredo)
        casos = {
            "autenticação da OpenAI": (erro_openai("AuthenticationError", 401, segredo), lc.INDISPONIVEL, "acesso_negado"),
            "permissão (403)": (erro_openai("PermissionDeniedError", 403, segredo), lc.INDISPONIVEL, "acesso_negado"),
            "credencial do Azure": (erro_openai("ClientAuthenticationError", None, segredo), lc.INDISPONIVEL, "acesso_negado"),
            "limite de uso": (erro_openai("RateLimitError", 429, segredo), lc.INDISPONIVEL, "limite_do_servico"),
            "deployment ausente": (erro_openai("NotFoundError", 404, segredo), lc.INDISPONIVEL, "nao_encontrado"),
            "rede": (erro_openai("APIConnectionError", None, segredo), lc.INDISPONIVEL, "rede"),
            "tempo da rede": (TimeoutError(segredo), lc.INDISPONIVEL, "rede"),
            "erro 500 do serviço": (erro_openai("InternalServerError", 500, segredo), lc.INDISPONIVEL, "servico"),
            "ErroLab com causa da OpenAI": (envolvido, lc.INDISPONIVEL, "acesso_negado"),
            "ErroLab sem causa": (lab_comum.ErroLab(segredo, 2), lc.INDISPONIVEL, "ajudante"),
            "formato do modelo": (lg.ErroDeFormato(segredo, 2), lc.RESPOSTA_NAO_VERIFICADA, "formato_do_modelo"),
            "filtro de conteúdo": (erro_openai("BadRequestError", 400, segredo, code="content_filter"),
                                   lc.PERGUNTA_BLOQUEADA, "filtro_de_conteudo"),
            "defeito do programa": (KeyError(segredo), lc.ERRO_INTERNO, "inesperado"),
        }
        for rotulo, (erro, codigo, causa) in casos.items():
            with self.subTest(rotulo=rotulo):
                classificado = lc.classificar_erro(erro)
                self.assertEqual((classificado.codigo, classificado.causa), (codigo, causa))
                self.assertNotIn(segredo, f"{classificado} {classificado.mensagem}")

    def test_erro_ja_classificado_passa_como_esta(self):
        erro = lc.ErroChat(lc.OCUPADO)
        self.assertIs(lc.classificar_erro(erro), erro)


# --------------------------------------------------------------------------------------
# Demonstração e fábrica do Azure
# --------------------------------------------------------------------------------------

class DemonstracaoTests(unittest.TestCase):
    def test_toda_resposta_simulada_traz_o_aviso_e_passa_pela_politica(self):
        servico = lc.ServicoDemo()
        esperados = {
            "Qual é a regra geral para o aviso de um sinistro?": (lp.DOCUMENTADA, lp.RESPONDIDA),
            PERGUNTA_INDIVIDUAL: (lp.CONTRATACAO_INDIVIDUAL, lp.RESPONDIDA),
            "Quem ganhou o jogo de futebol de ontem?": (lp.FORA_DE_ESCOPO, lp.RECUSADA),
            "Qual é o preço do seguro?": (lp.SEM_EVIDENCIA, lp.RECUSADA),
            "Limite?": (lp.AMBIGUA, lp.ESCLARECIMENTO),
        }
        for pergunta, (tipo, situacao) in esperados.items():
            with self.subTest(pergunta=pergunta):
                resposta = servico.perguntar(pergunta)
                dados = resposta.a_dict()
                self.assertEqual((resposta.tipo, resposta.situacao), (tipo, situacao))
                self.assertIs(dados["simulada"], True)
                self.assertEqual(dados["aviso_simulacao"], lc.AVISO_SIMULACAO)
                self.assertIn("SIMULAÇÃO", dados["aviso_simulacao"])
                self.assertIsNone(dados["uso"])
                self.assertEqual(dados, servico.perguntar(pergunta).a_dict(), "determinística")
        individual = servico.perguntar(PERGUNTA_INDIVIDUAL)
        self.assertEqual((individual.texto, individual.aviso), (lp.TEXTO_SEM_VEREDITO, lp.AVISO_CONTRATACAO_INDIVIDUAL))

    def test_a_demonstracao_nao_toca_no_azure(self):
        with mock.patch.object(lc, "criar_credencial", side_effect=AssertionError("Azure")), \
                mock.patch.object(lg, "criar_cliente_geracao", side_effect=AssertionError("Azure")), \
                mock.patch.object(lg, "criar_recuperador", side_effect=AssertionError("Azure")):
            servico = lc.criar_servico(config_demo())
            self.assertIsInstance(servico, lc.ServicoDemo)
            servico.perguntar(PERGUNTA_GERAL)

    def test_o_modo_da_nuvem_nunca_cria_o_servico_de_demonstracao(self):
        with mock.patch.object(lc, "criar_servico_azure", return_value="servico-real") as criar:
            self.assertEqual(lc.criar_servico(config()), "servico-real")
        criar.assert_called_once()
        with self.assertRaises(lc.ErroConfiguracao):
            lc.criar_servico(lc.ConfiguracaoChat())


class FabricaDoAzureTests(unittest.TestCase):
    def test_a_fabrica_usa_os_ajudantes_e_entrega_a_mesma_credencial_ao_recuperador_e_ao_gerador(self):
        credencial, recuperador, gerador = object(), object(), object()
        configuracao = config(client_id=guid(5), tenant_id=OUTRO_TENANT, indice="index-teste", dimensoes=64, k=3,
                              modo_busca="texto", deployment_embeddings="emb-teste", deployment_geracao="ger-teste",
                              esforco="medium")
        with mock.patch.object(lc, "criar_credencial", return_value=credencial) as criar_credencial, \
                mock.patch.object(lg, "criar_recuperador", return_value=recuperador) as criar_recuperador, \
                mock.patch.object(lg, "criar_cliente_geracao", return_value=gerador) as criar_gerador:
            servico = lc.criar_servico_azure(configuracao)
        criar_credencial.assert_called_once_with(configuracao)
        argumentos = criar_recuperador.call_args.args[0]
        self.assertIs(argumentos.credencial, credencial)
        self.assertEqual((argumentos.busca, argumentos.modelos, argumentos.indice, argumentos.deployment, argumentos.dimensoes,
                          argumentos.modo, argumentos.tenant_id),
                         (BUSCA, MODELOS, "index-teste", "emb-teste", 64, "texto", OUTRO_TENANT))
        self.assertEqual(criar_gerador.call_args.args, (MODELOS, "ger-teste", "medium", OUTRO_TENANT, credencial))
        self.assertEqual((servico.recuperador, servico.gerador, servico.modo_busca, servico.k), (recuperador, gerador, "texto", 3))

    def test_na_nuvem_a_credencial_e_a_identidade_gerenciada_com_o_client_id_opcional(self):
        with mock.patch("azure.identity.ManagedIdentityCredential") as gerenciada, \
                mock.patch("azure.identity.AzureCliCredential") as cli:
            lc.criar_credencial(config(client_id=guid(5)))
            lc.criar_credencial(config())
        self.assertEqual([chamada.kwargs for chamada in gerenciada.call_args_list], [{"client_id": guid(5)}, {"client_id": None}])
        cli.assert_not_called()

    def test_no_uso_local_a_credencial_e_a_sessao_do_azure_cli_do_tenant_informado(self):
        with mock.patch("azure.identity.ManagedIdentityCredential") as gerenciada, \
                mock.patch("azure.identity.AzureCliCredential") as cli:
            lc.criar_credencial(config(modo=lc.MODO_LOCAL, host="127.0.0.1", exigir_autenticacao=False,
                                       tenant_id=OUTRO_TENANT))
        cli.assert_called_once_with(tenant_id=OUTRO_TENANT, process_timeout=30)
        gerenciada.assert_not_called()

    def test_clientes_e_credenciais_reais_sao_montados_na_partida_sem_rede_nem_token(self):
        from azure.identity import AzureCliCredential, ManagedIdentityCredential

        class CredencialQueNaoPodeSerUsada:
            def get_token(self, *escopos, **opcoes):
                raise AssertionError("nenhum token deve ser pedido na partida")

        local = config(modo=lc.MODO_LOCAL, host="127.0.0.1", exigir_autenticacao=False)
        with mock.patch.object(socket.socket, "connect", side_effect=AssertionError("conexão de rede na partida")):
            self.assertIsInstance(lc.criar_credencial(config(client_id=guid(5))), ManagedIdentityCredential)
            self.assertIsInstance(lc.criar_credencial(local), AzureCliCredential)
            with mock.patch.object(lc, "criar_credencial", return_value=CredencialQueNaoPodeSerUsada()):
                servico = lc.criar_servico_azure(config(indice="index-teste"))
        self.assertIsInstance(servico.recuperador, lg.Recuperador)
        self.assertIsInstance(servico.gerador, lg.ClienteGeracao)
        self.assertEqual((servico.recuperador.indice.nome, servico.recuperador.embeddings.dimensoes, servico.gerador.deployment),
                         ("index-teste", 1536, lg.DEPLOYMENT_GERACAO_PADRAO))


# --------------------------------------------------------------------------------------
# Interface HTTP
# --------------------------------------------------------------------------------------

@PRECISA_DO_HTTP
class SaudeEPartidaTests(unittest.TestCase):
    def test_saude_e_prontidao_nao_pedem_identidade_nem_chamam_o_servico(self):
        servico, criados = ServicoFalso(), []
        app = chat_web.create_app(config(), lambda cfg: criados.append(cfg) or servico)
        self.assertEqual(criados, [], "criar a aplicação não cria o serviço nem lê o ambiente")
        with TestClient(app) as cliente:
            self.assertEqual(len(criados), 1)
            saude, prontidao = cliente.get("/healthz"), cliente.get("/readyz")
        self.assertEqual((saude.status_code, saude.json()), (200, {"situacao": "ok"}))
        self.assertEqual((prontidao.status_code, prontidao.json()), (200, {"situacao": "pronto", "modo": lc.MODO_NUVEM}))
        self.assertEqual(servico.perguntas, [])

    def test_antes_da_partida_a_aplicacao_esta_viva_mas_nao_pronta(self):
        app = chat_web.create_app(config(), lambda cfg: ServicoFalso())
        cliente = TestClient(app)
        self.assertEqual(cliente.get("/healthz").status_code, 200)
        pronta = cliente.get("/readyz")
        self.assertEqual((pronta.status_code, pronta.json()["erro"]), (503, lc.NAO_PRONTO))

    def test_configuracao_invalida_impede_a_partida_e_o_servico_nao_e_criado(self):
        criados = []
        app = chat_web.create_app(lc.ConfiguracaoChat(), lambda cfg: criados.append(cfg))
        with self.assertRaises(lc.ErroConfiguracao), TestClient(app):
            pass
        self.assertEqual(criados, [])

    def test_falha_ao_criar_o_servico_impede_a_partida_sem_cair_na_demonstracao(self):
        def fabrica(cfg):
            raise lab_comum.ErroLab("falha ao abrir o Azure")

        for configuracao in (config(), config(modo=lc.MODO_LOCAL, host="127.0.0.1", exigir_autenticacao=False)):
            with self.subTest(modo=configuracao.modo), self.assertRaises(lab_comum.ErroLab):
                with TestClient(chat_web.create_app(configuracao, fabrica)):
                    pass

    def test_instalacao_sem_a_interface_nao_inicia(self):
        with tempfile.TemporaryDirectory() as pasta, self.assertRaises(lab_comum.ErroLab) as contexto:
            with TestClient(chat_web.create_app(config(), lambda cfg: ServicoFalso(), pasta_web=Path(pasta))):
                pass
        self.assertIn("web/index.html", str(contexto.exception))

    def test_a_consulta_roda_fora_do_laco_de_eventos_e_a_saude_continua_respondendo(self):
        entrou, soltar = threading.Event(), threading.Event()

        def esperar(pergunta):
            entrou.set()
            soltar.wait(10)

        servico = ServicoFalso(esperar=esperar)
        with servidor(servico) as cliente, ThreadPoolExecutor(1) as pool:
            demorada = pool.submit(perguntar_pela_api, cliente)
            self.assertTrue(entrou.wait(10))
            self.assertEqual(cliente.get("/healthz").status_code, 200)
            soltar.set()
            self.assertEqual(demorada.result(timeout=10).status_code, 200)
        self.assertTrue(all(nome.startswith("chat") for nome in servico.threads), servico.threads)
        self.assertNotIn(threading.current_thread().name, servico.threads)


@PRECISA_DO_HTTP
class AcessoTests(unittest.TestCase):
    def test_sem_identidade_valida_nada_e_servido_exceto_a_saude(self):
        servico = ServicoFalso()
        with servidor(servico) as cliente:
            for caminho in ("/", "/static/app.js", "/static/style.css", "/qualquer-coisa", "/docs", "/openapi.json"):
                with self.subTest(caminho=caminho):
                    resposta = cliente.get(caminho)
                    self.assertEqual((resposta.status_code, resposta.json()["erro"]), (401, lc.NAO_AUTENTICADO))
            sem_identidade = cliente.post("/api/perguntar", json={"pergunta": PERGUNTA_GERAL})
            self.assertEqual(sem_identidade.status_code, 401)
            for caminho in ("/healthz", "/readyz"):
                self.assertEqual(cliente.get(caminho).status_code, 200)
        self.assertEqual(servico.perguntas, [])

    def test_cabecalho_ilegivel_e_401_e_tenant_nao_autorizado_e_403(self):
        servico = ServicoFalso()
        with servidor(servico) as cliente:
            for rotulo, cabecalho in {"texto solto": "isto nao e base64!", "JSON sem claims": codificar({"auth_typ": "aad"}),
                                      "sem sujeito": codificar(principal(claims=[{"typ": "tid", "val": TENANT}]))}.items():
                with self.subTest(rotulo=rotulo):
                    resposta = perguntar_pela_api(cliente, cabecalhos={lc.CABECALHO_PRINCIPAL: cabecalho})
                    self.assertEqual((resposta.status_code, resposta.json()["erro"]), (401, lc.NAO_AUTENTICADO))
            proibida = perguntar_pela_api(cliente, cabecalhos=autenticado(OUTRO_TENANT))
            self.assertEqual((proibida.status_code, proibida.json()["erro"]), (403, lc.NAO_AUTORIZADO))
            self.assertEqual(proibida.json()["mensagem"], lc.MENSAGENS[lc.NAO_AUTORIZADO])
        self.assertEqual(servico.perguntas, [])

    def test_identidade_valida_acessa_a_interface_e_a_api(self):
        with servidor(ServicoFalso()) as cliente:
            self.assertEqual(cliente.get("/", headers=autenticado()).status_code, 200)
            self.assertEqual(cliente.get("/static/app.js", headers=autenticado()).status_code, 200)
            self.assertEqual(perguntar_pela_api(cliente).status_code, 200)

    def test_no_modo_local_o_cabecalho_nao_e_lido_nem_confiado(self):
        local = config(modo=lc.MODO_LOCAL, host="127.0.0.1", exigir_autenticacao=False, tenants_autorizados=frozenset())
        servico = ServicoFalso()
        with servidor(servico, local) as cliente:
            for cabecalhos in ({}, {lc.CABECALHO_PRINCIPAL: "lixo!!"}, autenticado(OUTRO_TENANT)):
                with self.subTest(cabecalhos=bool(cabecalhos)):
                    self.assertEqual(perguntar_pela_api(cliente, cabecalhos=cabecalhos).status_code, 200)
        self.assertEqual(len(servico.perguntas), 3)

    def test_o_modo_exige_identidade_mesmo_na_demonstracao_quando_configurado(self):
        demo = config_demo(exigir_autenticacao=True, tenants_autorizados=frozenset({TENANT}))
        with TestClient(chat_web.create_app(demo), base_url=ORIGEM_LOCAL) as cliente:
            self.assertEqual(perguntar_pela_api(cliente, cabecalhos={}).status_code, 401)
            self.assertEqual(perguntar_pela_api(cliente).status_code, 200)

    def test_modos_locais_so_atendem_pelo_proprio_computador_e_a_nuvem_nao_restringe_o_endereco(self):
        local = config(modo=lc.MODO_LOCAL, host="127.0.0.1", exigir_autenticacao=False, tenants_autorizados=frozenset())
        servico = ServicoFalso()
        with servidor(servico, local) as cliente:
            for host in ("localhost:8000", "127.0.0.1:8000", "[::1]:8000", "localhost", "LOCALHOST:8000"):
                with self.subTest(host=host):
                    self.assertEqual(cliente.get("/healthz", headers={"host": host}).status_code, 200)
            for host in ("exemplo.invalido", "exemplo.invalido:8000", "localhost.exemplo.invalido",
                         "127.0.0.1.exemplo.invalido", "0.0.0.0:8000", "192.0.2.10"):
                with self.subTest(host=host):
                    for resposta in (cliente.get("/healthz", headers={"host": host}),
                                     perguntar_pela_api(cliente, cabecalhos={"host": host})):
                        self.assertEqual((resposta.status_code, resposta.json()["erro"]), (400, lc.HOST_INVALIDO))
        self.assertEqual(servico.perguntas, [])
        with servidor(ServicoFalso()) as nuvem:
            self.assertEqual(nuvem.get("/healthz", headers={"host": "app.exemplo.invalido"}).status_code, 200)


@PRECISA_DO_HTTP
class ApiPerguntarTests(unittest.TestCase):
    def test_pergunta_valida_devolve_so_os_campos_publicos(self):
        servico = ServicoFalso()
        with servidor(servico) as cliente:
            resposta = perguntar_pela_api(cliente, {"pergunta": "  Qual é o prazo?  ", "id": "navegador-0001"})
        self.assertEqual(resposta.status_code, 200)
        dados = resposta.json()
        self.assertEqual(set(dados), {"id", "id_requisicao", "tipo", "situacao", "texto", "aviso", "evidencias", "uso",
                                      "simulada", "aviso_simulacao"})
        self.assertEqual((dados["id"], dados["id_requisicao"]), ("navegador-0001", resposta.headers["x-request-id"]))
        self.assertEqual((dados["tipo"], dados["situacao"], dados["texto"]), (lp.DOCUMENTADA, lp.RESPONDIDA, "Resposta para: Qual é o prazo?"))
        self.assertEqual(set(dados["evidencias"][0]), {"id", "citacao", "fonte", "versao", "documento", "secao", "clausulas"})
        self.assertEqual(dados["uso"], {"tokens_embeddings": 1, "tokens_entrada": 2, "tokens_saida": 3, "tokens_raciocinio": 4})
        self.assertEqual((dados["simulada"], dados["aviso_simulacao"]), (False, ""))
        self.assertEqual(servico.perguntas, ["Qual é o prazo?"])
        for oculto in (TENANT, SUJEITO, lc.CABECALHO_PRINCIPAL, "emissor.exemplo"):
            self.assertNotIn(oculto, resposta.text)

    def test_toda_resposta_leva_cabecalhos_de_seguranca_e_nenhuma_e_guardada_em_cache(self):
        with servidor(ServicoFalso()) as cliente:
            respostas = [perguntar_pela_api(cliente), perguntar_pela_api(cliente, cabecalhos={}), cliente.get("/healthz"),
                         cliente.get("/", headers=autenticado()), cliente.get("/nao-existe", headers=autenticado())]
        for resposta in respostas:
            with self.subTest(status=resposta.status_code):
                self.assertEqual(resposta.headers["cache-control"], "no-store")
                self.assertEqual(resposta.headers["x-content-type-options"], "nosniff")
                self.assertEqual(resposta.headers["x-frame-options"], "DENY")
                self.assertEqual(resposta.headers["referrer-policy"], "no-referrer")
                politica = resposta.headers["content-security-policy"]
                for diretiva in ("default-src 'none'", "script-src 'self'", "style-src 'self'", "connect-src 'self'",
                                 "frame-ancestors 'none'"):
                    self.assertIn(diretiva, politica)
                self.assertRegex(resposta.headers["x-request-id"], r"^[0-9a-f]{32}$")

    def test_pedido_malformado_e_422_sem_ecoar_o_que_foi_enviado(self):
        servico = ServicoFalso()
        casos = {
            "sem pergunta": ({}, lc.PERGUNTA_VAZIA),
            "pergunta vazia": ({"pergunta": "  "}, lc.PERGUNTA_VAZIA),
            "pergunta numérica": ({"pergunta": 3}, lc.PERGUNTA_INVALIDA),
            "pergunta longa": ({"pergunta": "a" * (lc.LIMITE_DA_PERGUNTA + 1)}, lc.PERGUNTA_LONGA),
            "lista no lugar do objeto": (["ENVIADO-NO-CORPO"], lc.JSON_INVALIDO),
            "campo de depuração": ({"pergunta": "ENVIADO-NO-CORPO", "debug": True}, lc.CAMPOS_NAO_PERMITIDOS),
            "histórico": ({"pergunta": "ENVIADO-NO-CORPO", "historico": [{"texto": "ENVIADO-ANTES"}]}, lc.CAMPOS_NAO_PERMITIDOS),
            "mensagens": ({"mensagens": [{"texto": "ENVIADO-ANTES"}]}, lc.CAMPOS_NAO_PERMITIDOS),
            "id curto": ({"pergunta": "ENVIADO-NO-CORPO", "id": "1"}, lc.ID_INVALIDO),
        }
        with servidor(servico) as cliente:
            for rotulo, (corpo, codigo) in casos.items():
                with self.subTest(rotulo=rotulo):
                    resposta = perguntar_pela_api(cliente, corpo)
                    self.assertEqual((resposta.status_code, resposta.json()["erro"]), (422, codigo))
                    self.assertEqual(resposta.json()["mensagem"], lc.MENSAGENS[codigo])
                    self.assertNotIn("ENVIADO", resposta.text)
            texto_solto = cliente.post("/api/perguntar", content=b"{ENVIADO-NO-CORPO", headers={**autenticado(), "content-type": "application/json"})
            outro_tipo = cliente.post("/api/perguntar", content=b'{"pergunta": "ENVIADO-NO-CORPO"}', headers={**autenticado(), "content-type": "text/plain"})
            com_consulta = cliente.post("/api/perguntar?debug=1", json={"pergunta": PERGUNTA_GERAL}, headers=autenticado())
        self.assertEqual([(r.status_code, r.json()["erro"]) for r in (texto_solto, outro_tipo, com_consulta)],
                         [(422, lc.JSON_INVALIDO), (422, lc.TIPO_DE_CONTEUDO_INVALIDO), (422, lc.CAMPOS_NAO_PERMITIDOS)])
        self.assertNotIn("ENVIADO", texto_solto.text + outro_tipo.text)
        self.assertEqual(servico.perguntas, [], "pedido inválido nunca chega ao serviço")

    def test_corpo_grande_e_recusado_com_ou_sem_content_length(self):
        def partes():
            yield b'{"pergunta": "'
            for _ in range(3):
                yield b"a" * lc.LIMITE_DO_CORPO
            yield b'"}'

        servico = ServicoFalso()
        with servidor(servico) as cliente:
            declarado = cliente.post("/api/perguntar", content=b'{"pergunta": "' + b"a" * lc.LIMITE_DO_CORPO + b'"}',
                                     headers={**autenticado(), "content-type": "application/json"})
            em_partes = cliente.post("/api/perguntar", content=partes(), headers={**autenticado(), "content-type": "application/json"})
        self.assertEqual([r.status_code for r in (declarado, em_partes)], [413, 413])
        self.assertEqual(declarado.json()["erro"], lc.PEDIDO_GRANDE)
        self.assertEqual(servico.perguntas, [])

    def test_metodo_errado_e_endereco_desconhecido_tem_resposta_padronizada(self):
        with servidor(ServicoFalso()) as cliente:
            metodo = cliente.get("/api/perguntar", headers=autenticado())
            ausente = cliente.get("/nao-existe", headers=autenticado())
            estatico = cliente.get("/static/index.html", headers=autenticado())
            fora = cliente.get("/static/..%2Fscripts%2Flab_chat.py", headers=autenticado())
        self.assertEqual((metodo.status_code, metodo.headers["allow"], metodo.json()["erro"]), (405, "POST", lc.METODO_NAO_PERMITIDO))
        for resposta in (ausente, estatico, fora):
            self.assertEqual((resposta.status_code, resposta.json()["erro"]), (404, lc.NAO_ENCONTRADO))

    def test_falhas_viram_codigos_publicos_sem_texto_de_excecao_nem_dados_do_pedido(self):
        segredo = "SEGREDO-NA-EXCECAO"
        casos = {
            "acesso negado": (erro_openai("AuthenticationError", 401, segredo), 503, lc.INDISPONIVEL, "acesso_negado"),
            "limite do serviço": (erro_openai("RateLimitError", 429, segredo), 503, lc.INDISPONIVEL, "limite_do_servico"),
            "deployment ausente": (erro_openai("NotFoundError", 404, segredo), 503, lc.INDISPONIVEL, "nao_encontrado"),
            "rede": (erro_openai("APIConnectionError", None, segredo), 503, lc.INDISPONIVEL, "rede"),
            "formato do modelo": (lg.ErroDeFormato(segredo, 2), 503, lc.RESPOSTA_NAO_VERIFICADA, "formato_do_modelo"),
            "filtro de conteúdo": (erro_openai("BadRequestError", 400, segredo, code="content_filter"), 422,
                                   lc.PERGUNTA_BLOQUEADA, "filtro_de_conteudo"),
            "defeito inesperado": (RuntimeError(segredo), 500, lc.ERRO_INTERNO, "inesperado"),
        }
        for rotulo, (erro, status, codigo, causa) in casos.items():
            with self.subTest(rotulo=rotulo), self.assertLogs("vareleira.chat", "INFO") as registro:
                with servidor(ServicoFalso(erro=erro)) as cliente:
                    resposta = perguntar_pela_api(cliente, {"pergunta": "PERGUNTA-SECRETA"})
                dados = resposta.json()
                self.assertEqual((resposta.status_code, dados["erro"], dados["mensagem"]), (status, codigo, lc.MENSAGENS[codigo]))
                self.assertEqual(set(dados), {"erro", "mensagem", "id_requisicao"})
                self.assertEqual(dados["id_requisicao"], resposta.headers["x-request-id"])
                self.assertNotIn(segredo, resposta.text)
                saida = "\n".join(registro.output)
                for proibido in (segredo, "PERGUNTA-SECRETA", TENANT, SUJEITO, "Traceback"):
                    self.assertNotIn(proibido, saida)
                self.assertIn(f"status={status}", saida)
                self.assertIn(f"causa={causa}", saida)

    def test_resposta_de_falha_nunca_tem_formato_de_sucesso(self):
        with servidor(ServicoFalso(erro=RuntimeError("x"))) as cliente:
            dados = perguntar_pela_api(cliente).json()
        for campo in ("tipo", "situacao", "texto", "evidencias", "uso", "simulada"):
            self.assertNotIn(campo, dados)

    def test_registro_so_tem_id_rota_status_e_tempo(self):
        with self.assertLogs("vareleira.chat", "INFO") as registro:
            with servidor(ServicoFalso()) as cliente:
                perguntar_pela_api(cliente, {"pergunta": "PERGUNTA-SECRETA"})
                cliente.get("/static/app.js?token=SEGREDO-NA-CONSULTA", headers=autenticado())
                perguntar_pela_api(cliente, cabecalhos={lc.CABECALHO_PRINCIPAL: "cabecalho-ruim"})
                cliente.get("/healthz")
        linhas = [linha.split("requisicao ", 1)[1] for linha in registro.output if "requisicao " in linha]
        campos = [dict(par.split("=", 1) for par in linha.split()) for linha in linhas]
        for item in campos:
            self.assertLessEqual(set(item), {"id", "rota", "status", "ms", "causa"})
            self.assertRegex(item["id"], r"^[0-9a-f]{32}$")
            self.assertTrue(item["ms"].isdigit())
        self.assertEqual([(item["rota"], item["status"]) for item in campos],
                         [("perguntar", "200"), ("estatico", "200"), ("perguntar", "401"), ("saude", "200")])
        self.assertEqual([item.get("causa") for item in campos], [None, None, "principal_invalido", None])
        texto = "\n".join(registro.output)
        for proibido in ("PERGUNTA-SECRETA", "SEGREDO-NA-CONSULTA", "cabecalho-ruim", "/static/app.js", "/api/perguntar", TENANT):
            self.assertNotIn(proibido, texto)


@PRECISA_DO_HTTP
class ControleDeCargaTests(unittest.TestCase):
    def test_sem_vaga_responde_429_sem_enfileirar_e_libera_depois(self):
        entrou, soltar = threading.Event(), threading.Event()

        def esperar(pergunta):
            if pergunta == "primeira":
                entrou.set()
                soltar.wait(10)

        servico = ServicoFalso(esperar=esperar)
        with servidor(servico, config(max_concorrencia=1)) as cliente, ThreadPoolExecutor(1) as pool:
            primeira = pool.submit(perguntar_pela_api, cliente, {"pergunta": "primeira"})
            self.assertTrue(entrou.wait(10))
            segunda = perguntar_pela_api(cliente, {"pergunta": "segunda"})
            self.assertEqual((segunda.status_code, segunda.json()["erro"], segunda.headers["retry-after"]),
                             (429, lc.OCUPADO, str(chat_web.ESPERA_SUGERIDA)))
            soltar.set()
            self.assertEqual(primeira.result(timeout=10).status_code, 200)
            self.assertEqual(perguntar_pela_api(cliente, {"pergunta": "terceira"}).status_code, 200)
        self.assertEqual(servico.perguntas, ["primeira", "terceira"], "a segunda nunca chegou ao serviço")

    def test_tempo_esgotado_responde_503_e_a_vaga_so_volta_quando_o_trabalho_termina(self):
        soltar = threading.Event()
        servico = ServicoFalso(esperar=lambda pergunta: soltar.wait(10))
        with mock.patch.object(lc, "TEMPO_MINIMO", 0.05), \
                servidor(servico, config(max_concorrencia=1, timeout_segundos=0.2)) as cliente:
            lenta = perguntar_pela_api(cliente)
            self.assertEqual((lenta.status_code, lenta.json()["erro"]), (503, lc.INDISPONIVEL))
            ocupada = perguntar_pela_api(cliente)
            self.assertEqual(ocupada.status_code, 429, "o trabalho da primeira ainda ocupa a única vaga")
            soltar.set()
            for _ in range(100):
                livre = perguntar_pela_api(cliente)
                if livre.status_code != 429:
                    break
                time.sleep(0.05)
            self.assertEqual(livre.status_code, 200)

    def test_consultas_simultaneas_nao_misturam_perguntas_nem_respostas(self):
        quantidade = 4
        barreira = threading.Barrier(quantidade, timeout=10)
        servico = ServicoFalso(esperar=lambda pergunta: barreira.wait())
        with servidor(servico, config(max_concorrencia=quantidade)) as cliente, ThreadPoolExecutor(quantidade) as pool:
            futuros = [pool.submit(perguntar_pela_api, cliente, {"pergunta": f"pergunta-{numero}", "id": f"id-cliente-{numero}"})
                       for numero in range(quantidade)]
            respostas = [futuro.result(timeout=20) for futuro in futuros]
        for numero, resposta in enumerate(respostas):
            self.assertEqual(resposta.status_code, 200)
            self.assertEqual((resposta.json()["texto"], resposta.json()["id"]),
                             (f"Resposta para: pergunta-{numero}", f"id-cliente-{numero}"))
        self.assertEqual(len({resposta.json()["id_requisicao"] for resposta in respostas}), quantidade)

    def test_o_mesmo_id_do_navegador_em_duas_requisicoes_nao_e_reaproveitado_pelo_servidor(self):
        servico = ServicoFalso()
        with servidor(servico) as cliente:
            primeira = perguntar_pela_api(cliente, {"pergunta": "Primeira pergunta", "id": "mesmo-id-0001"})
            segunda = perguntar_pela_api(cliente, {"pergunta": "Segunda pergunta", "id": "mesmo-id-0001"})
        self.assertEqual((primeira.json()["texto"], segunda.json()["texto"]),
                         ("Resposta para: Primeira pergunta", "Resposta para: Segunda pergunta"))
        self.assertNotEqual(primeira.json()["id_requisicao"], segunda.json()["id_requisicao"])
        self.assertEqual(servico.perguntas, ["Primeira pergunta", "Segunda pergunta"])


@PRECISA_DO_HTTP
class InterfaceEDemonstracaoTests(unittest.TestCase):
    def test_a_demonstracao_funciona_offline_de_ponta_a_ponta_e_sempre_avisa(self):
        with mock.patch.object(lc, "criar_credencial", side_effect=AssertionError("Azure")), \
                TestClient(chat_web.create_app(config_demo()), base_url=ORIGEM_LOCAL) as cliente:
            self.assertEqual(cliente.get("/readyz").json(), {"situacao": "pronto", "modo": lc.MODO_DEMO})
            pagina = cliente.get("/")
            self.assertIn('data-modo="demonstracao"', pagina.text)
            for pergunta in (PERGUNTA_GERAL, PERGUNTA_INDIVIDUAL, "Qual é o preço?"):
                with self.subTest(pergunta=pergunta):
                    resposta = cliente.post("/api/perguntar", json={"pergunta": pergunta})
                    dados = resposta.json()
                    self.assertEqual(resposta.status_code, 200)
                    self.assertEqual((dados["simulada"], dados["aviso_simulacao"]), (True, lc.AVISO_SIMULACAO))

    def test_falha_do_servico_real_nunca_vira_resposta_simulada(self):
        with servidor(ServicoFalso(erro=erro_openai("AuthenticationError", 401))) as cliente:
            dados = perguntar_pela_api(cliente).json()
        self.assertEqual(dados["erro"], lc.INDISPONIVEL)
        self.assertNotIn("simulada", dados)
        self.assertNotIn("SIMULAÇÃO", json.dumps(dados, ensure_ascii=False))

    def test_a_pagina_recebe_o_modo_e_o_limite_e_os_arquivos_estaticos_sao_os_do_projeto(self):
        with servidor(ServicoFalso()) as cliente:
            pagina = cliente.get("/", headers=autenticado())
            script = cliente.get("/static/app.js", headers=autenticado())
            estilo = cliente.get("/static/style.css", headers=autenticado())
        self.assertEqual(pagina.headers["content-type"], "text/html; charset=utf-8")
        self.assertIn(f'data-modo="{lc.MODO_NUVEM}"', pagina.text)
        self.assertIn(f'data-limite-pergunta="{lc.LIMITE_DA_PERGUNTA}"', pagina.text)
        self.assertNotIn("{{", pagina.text)
        self.assertEqual(script.content, (RAIZ / "web" / "app.js").read_bytes())
        self.assertEqual(estilo.content, (RAIZ / "web" / "style.css").read_bytes())
        self.assertTrue(script.headers["content-type"].startswith("text/javascript"))
        self.assertTrue(estilo.headers["content-type"].startswith("text/css"))


@PRECISA_DO_HTTP
class PoliticaPeloHttpTests(unittest.TestCase):
    """O serviço real (ajudantes do L100 e política) atrás da API, com dublês no lugar da OpenAI e da busca."""

    def perguntar(self, geracao, pergunta=PERGUNTA_GERAL):
        with servidor(servico_rag(geracao)) as cliente:
            return perguntar_pela_api(cliente, {"pergunta": pergunta})

    def test_contratacao_individual_chega_ao_navegador_com_o_texto_fixo_e_nunca_o_do_modelo(self):
        for tipo_do_modelo in (lp.DOCUMENTADA, lp.CONTRATACAO_INDIVIDUAL):
            with self.subTest(tipo_do_modelo=tipo_do_modelo):
                geracao = OpenAIGeracaoFalso()
                geracao.responder = responder(tipo_do_modelo, resposta="Sim, o seu seguro cobre e vai pagar tudo.")
                resposta = self.perguntar(geracao, PERGUNTA_INDIVIDUAL)
                dados = resposta.json()
                self.assertEqual(resposta.status_code, 200)
                self.assertEqual((dados["tipo"], dados["texto"], dados["aviso"]),
                                 (lp.CONTRATACAO_INDIVIDUAL, lp.TEXTO_SEM_VEREDITO, lp.AVISO_CONTRATACAO_INDIVIDUAL))
                self.assertTrue(dados["evidencias"])
                self.assertNotIn("vai pagar", resposta.text)

    def test_nenhum_campo_bruto_do_modelo_chega_ao_navegador(self):
        geracao = OpenAIGeracaoFalso()
        geracao.responder = responder(lp.DOCUMENTADA, extras={"debug": "SAIDA-BRUTA-DO-MODELO"})
        resposta = self.perguntar(geracao)
        self.assertEqual(resposta.status_code, 200)
        for oculto in ("SAIDA-BRUTA-DO-MODELO", "debug", "gpt-5", "<trecho", "instructions"):
            self.assertNotIn(oculto, resposta.text)
        self.assertEqual(set(resposta.json()), {"id", "id_requisicao", "tipo", "situacao", "texto", "aviso", "evidencias",
                                                "uso", "simulada", "aviso_simulacao"})

    def test_resposta_com_citacao_inventada_vira_503_sem_o_texto_do_modelo(self):
        geracao = OpenAIGeracaoFalso()
        geracao.responder = responder(lp.DOCUMENTADA, resposta="Resposta inventada.", citacao="Frase que não existe em nenhum trecho.")
        resposta = self.perguntar(geracao)
        self.assertEqual((resposta.status_code, resposta.json()["erro"]), (503, lc.RESPOSTA_NAO_VERIFICADA))
        self.assertNotIn("inventada", resposta.text)

    def test_recusas_e_esclarecimento_chegam_com_os_textos_da_politica(self):
        for tipo, texto in ((lp.SEM_EVIDENCIA, lp.MENSAGEM_SEM_EVIDENCIA), (lp.FORA_DE_ESCOPO, lp.MENSAGEM_FORA_DE_ESCOPO)):
            with self.subTest(tipo=tipo):
                geracao = OpenAIGeracaoFalso()
                geracao.responder = responder(tipo, resposta="Cobre tudo!", evidencias=False)
                dados = self.perguntar(geracao).json()
                self.assertEqual((dados["tipo"], dados["situacao"], dados["texto"], dados["evidencias"]),
                                 (tipo, lp.RECUSADA, texto, []))

    def test_cada_requisicao_http_leva_so_a_pergunta_atual_ao_modelo(self):
        geracao = OpenAIGeracaoFalso()
        geracao.responder = responder(lp.DOCUMENTADA)
        with servidor(servico_rag(geracao)) as cliente:
            perguntar_pela_api(cliente, {"pergunta": "MARCADOR-ALFA pergunta anterior"})
            perguntar_pela_api(cliente, {"pergunta": "MARCADOR-BETA pergunta atual"})
        self.assertNotIn("MARCADOR-ALFA", geracao.chamadas[1]["input"])
        self.assertIn("MARCADOR-BETA", geracao.chamadas[1]["input"])


# --------------------------------------------------------------------------------------
# Linha de comando
# --------------------------------------------------------------------------------------

def rodar_chat(argumentos, variaveis=None):
    """Executa `chat_web.principal` com o servidor trocado por um dublê. Devolve (código, texto impresso, chamada ao servidor)."""
    saida = io.StringIO()
    with contextlib.ExitStack() as pilha:
        pilha.enter_context(mock.patch.dict(os.environ, variaveis or {}, clear=True))
        servidor_falso = pilha.enter_context(mock.patch.object(chat_web.uvicorn, "run"))
        pilha.enter_context(mock.patch.object(chat_web, "configurar_registro"))
        pilha.enter_context(contextlib.redirect_stdout(saida))
        pilha.enter_context(contextlib.redirect_stderr(saida))
        try:
            codigo = chat_web.principal(argumentos)
        except SystemExit as erro:
            codigo = erro.code
    return codigo, saida.getvalue(), servidor_falso


@PRECISA_DO_HTTP
class LinhaDeComandoTests(unittest.TestCase):
    def test_demo_inicia_so_em_loopback_com_as_opcoes_de_servidor_seguras(self):
        codigo, texto, servidor_falso = rodar_chat(["--host", "127.0.0.1", "--port", "8123", "--demo"])
        self.assertEqual(codigo, lab_comum.CODIGO_OK, texto)
        self.assertIn("modo de demonstração", texto)
        self.assertIn("http://127.0.0.1:8123", texto)
        servidor_falso.assert_called_once()
        self.assertIsInstance(servidor_falso.call_args.args[0], chat_web.FastAPI)
        opcoes = servidor_falso.call_args.kwargs
        self.assertEqual((opcoes["host"], opcoes["port"], opcoes["lifespan"]), ("127.0.0.1", 8123, "on"))
        self.assertEqual((opcoes["http"], opcoes["ws"]), ("h11", "none"))
        self.assertEqual((opcoes["access_log"], opcoes["server_header"], opcoes["proxy_headers"]), (False, False, False))
        self.assertEqual(opcoes["limit_concurrency"], chat_web.LIMITE_DE_CONEXOES)

    def test_sem_variaveis_a_nuvem_nao_inicia_e_lista_o_que_falta(self):
        codigo, texto, servidor_falso = rodar_chat(["--host", "0.0.0.0", "--port", "8000"])
        self.assertEqual(codigo, lab_comum.CODIGO_USO)
        for variavel in (lc.VAR_EXIGIR_AUTENTICACAO, lc.VAR_BUSCA, lc.VAR_MODELOS):
            self.assertIn(variavel, texto)
        servidor_falso.assert_not_called()

    def test_nuvem_com_a_configuracao_completa_escuta_no_endereco_pedido(self):
        codigo, texto, servidor_falso = rodar_chat(["--host", "0.0.0.0", "--port", "8000"], ambiente())
        self.assertEqual(codigo, lab_comum.CODIGO_OK, texto)
        self.assertEqual((servidor_falso.call_args.kwargs["host"], servidor_falso.call_args.kwargs["port"]), ("0.0.0.0", 8000))
        self.assertIn("autenticação exigida", texto)

    def test_nuvem_com_autenticacao_desligada_nao_inicia(self):
        codigo, texto, servidor_falso = rodar_chat([], ambiente({lc.VAR_EXIGIR_AUTENTICACAO: "false"}))
        self.assertEqual(codigo, lab_comum.CODIGO_USO)
        self.assertIn(lc.VAR_EXIGIR_AUTENTICACAO, texto)
        servidor_falso.assert_not_called()

    def test_modos_locais_recusam_enderecos_que_outras_maquinas_alcancam(self):
        for opcao in ("--demo", "--local-sem-autenticacao"):
            with self.subTest(opcao=opcao):
                codigo, texto, servidor_falso = rodar_chat([opcao, "--host", "0.0.0.0"], ambiente())
                self.assertEqual(codigo, lab_comum.CODIGO_USO)
                self.assertIn("--host", texto)
                servidor_falso.assert_not_called()

    def test_modo_local_usa_o_azure_com_a_sessao_do_cli_e_exige_os_recursos(self):
        codigo, texto, servidor_falso = rodar_chat(["--local-sem-autenticacao"])
        self.assertEqual(codigo, lab_comum.CODIGO_USO)
        self.assertIn(lc.VAR_BUSCA, texto)
        servidor_falso.assert_not_called()
        codigo, texto, servidor_falso = rodar_chat(["--local-sem-autenticacao"], {lc.VAR_BUSCA: BUSCA, lc.VAR_MODELOS: MODELOS})
        self.assertEqual(codigo, lab_comum.CODIGO_OK, texto)
        self.assertIn("sem autenticação", texto)
        servidor_falso.assert_called_once()

    def test_demo_e_modo_local_nao_se_combinam(self):
        codigo, texto, servidor_falso = rodar_chat(["--demo", "--local-sem-autenticacao"])
        self.assertEqual(codigo, lab_comum.CODIGO_USO)
        servidor_falso.assert_not_called()

    def test_porta_invalida_e_recusada_com_codigo_de_uso(self):
        for porta in ("0", "70000", "abc"):
            with self.subTest(porta=porta):
                codigo, texto, servidor_falso = rodar_chat(["--demo", "--port", porta])
                self.assertEqual(codigo, lab_comum.CODIGO_USO)
                servidor_falso.assert_not_called()

    def test_falha_inesperada_ao_iniciar_mostra_so_o_tipo_do_erro(self):
        saida = io.StringIO()
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(chat_web, "configurar_registro"), \
                mock.patch.object(chat_web.uvicorn, "run", side_effect=RuntimeError("SEGREDO-NA-EXCECAO")), \
                contextlib.redirect_stdout(saida), contextlib.redirect_stderr(saida):
            codigo = chat_web.principal(["--demo"])
        self.assertEqual(codigo, lab_comum.CODIGO_INESPERADO)
        self.assertIn("RuntimeError", saida.getvalue())
        self.assertNotIn("SEGREDO", saida.getvalue())

    def test_o_registro_silencia_as_bibliotecas_que_trazem_enderecos(self):
        niveis = {nome: logging.getLogger(nome).level for nome in chat_web.BIBLIOTECAS_QUE_NAO_REGISTRAM}
        self.addCleanup(lambda: [logging.getLogger(nome).setLevel(nivel) for nome, nivel in niveis.items()])
        with mock.patch.object(logging, "basicConfig") as basico:
            chat_web.configurar_registro()
        basico.assert_called_once()
        for nome in chat_web.BIBLIOTECAS_QUE_NAO_REGISTRAM:
            self.assertEqual(logging.getLogger(nome).level, logging.CRITICAL, nome)

    def test_rotulos_do_registro_vem_de_um_vocabulario_fechado(self):
        self.assertEqual([chat_web.rotular_rota(caminho) for caminho in ("/", "/healthz", "/readyz", "/api/perguntar",
                                                                          "/static/app.js", "/static/../x", "/outra?q=segredo")],
                         ["interface", "saude", "prontidao", "perguntar", "estatico", "estatico", "outra"])


# --------------------------------------------------------------------------------------
# Páginas, imagem e dependências
# --------------------------------------------------------------------------------------

PASTA_WEB = RAIZ / "web"
ARQUIVOS_WEB = ("index.html", "app.js", "style.css")


def ler_web(nome):
    return (PASTA_WEB / nome).read_text(encoding="utf-8")


class InterfaceWebTests(unittest.TestCase):
    def test_os_tres_arquivos_existem_e_a_pagina_so_carrega_os_do_proprio_servidor(self):
        for nome in ARQUIVOS_WEB:
            self.assertTrue((PASTA_WEB / nome).is_file(), nome)
        pagina = ler_web("index.html")
        self.assertEqual(re.findall(r'(?:src|href)="([^"]+)"', pagina.replace('href="#pergunta"', "")),
                         ["/static/style.css", "/static/app.js"])
        for nome in ARQUIVOS_WEB:
            self.assertIsNone(re.search(r"https?://|//cdn|@import|url\(", ler_web(nome)), nome)

    def test_texto_do_servidor_entra_so_por_textcontent(self):
        proibidos = ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function",
                     "createContextualFragment", "srcdoc", "DOMParser", "setAttribute(\"on", "javascript:")
        for nome in ("app.js", "index.html"):
            for proibido in proibidos:
                self.assertNotIn(proibido, ler_web(nome), f"{nome}: {proibido}")
        self.assertIn("textContent", ler_web("app.js"))

    def test_nada_e_guardado_no_navegador(self):
        for proibido in ("localStorage", "sessionStorage", "indexedDB", "document.cookie", "caches.", "serviceWorker", "window.name"):
            self.assertNotIn(proibido, ler_web("app.js"), proibido)

    def test_cada_requisicao_leva_so_a_pergunta_atual_e_um_id_novo(self):
        script = ler_web("app.js")
        self.assertEqual(script.count("fetch("), 1)
        corpos = re.findall(r"JSON\.stringify\(([^;]*?)\)\s*,", script)
        self.assertEqual([re.sub(r"\s+", " ", corpo) for corpo in corpos], ["{ pergunta: pergunta, id: novoId() }"])
        self.assertNotIn("mensagens", corpos[0])

    def test_sem_credenciais_identificadores_nem_texto_dos_documentos_na_interface(self):
        conteudo = "\n".join(ler_web(nome) for nome in ARQUIVOS_WEB)
        for padrao in (r"Bearer\s", r"Authorization", r"x-ms-client-principal", r"api[-_]?key", r"client[_-]?secret", r"password",
                       r"access_token", r"id_token", r"eyJ[A-Za-z0-9_-]{10,}", r"AccountKey", r"[?&]sig=",
                       r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
                       r"\.(windows\.net|azure\.com|azurewebsites\.net|azurecontainerapps\.io)", r"login\.microsoftonline"):
            self.assertIsNone(re.search(padrao, conteudo, re.IGNORECASE), padrao)
        normalizado = lp.normalizar(conteudo)
        for caminho in sorted((RAIZ / "dados" / "l100" / "documentos").glob("*.md")):
            for linha in caminho.read_text(encoding="utf-8").splitlines():
                frase = lp.normalizar(linha)
                if len(frase) >= 50:
                    self.assertNotIn(frase, normalizado, f"{caminho.name}: {frase[:40]}")

    def test_pagina_acessivel_sem_codigo_embutido_e_com_o_limite_do_servidor(self):
        pagina = ler_web("index.html")
        self.assertIn('<html lang="pt-BR">', pagina)
        self.assertIn('<label for="pergunta">', pagina)
        self.assertIn('aria-live="polite"', pagina)
        self.assertIn(f'maxlength="{lc.LIMITE_DA_PERGUNTA}"', pagina)
        scripts = re.findall(r"<script([^>]*)>(.*?)</script>", pagina, re.DOTALL)
        self.assertEqual(len(scripts), 1)
        self.assertIn("src=", scripts[0][0])
        self.assertEqual(scripts[0][1].strip(), "", "nenhum código dentro da página")
        self.assertNotRegex(pagina, r"<style")
        self.assertNotRegex(pagina, r"\sstyle=")
        self.assertNotRegex(pagina, r"\son[a-z]+=")

    def test_a_pagina_explica_que_cada_pergunta_e_enviada_sozinha(self):
        pagina = " ".join(ler_web("index.html").split())
        self.assertIn("Cada pergunta é enviada sozinha", pagina)
        self.assertIn("não lembra das anteriores", pagina)

    def test_script_tem_sintaxe_valida(self):
        node = shutil.which("node")
        if node is None:
            self.skipTest("Node.js não encontrado: a sintaxe do script não foi conferida.")
        resultado = subprocess.run([node, "--check", str(PASTA_WEB / "app.js")], capture_output=True, text=True, timeout=60)
        self.assertEqual(resultado.returncode, 0, resultado.stderr)


def instrucoes_do_dockerfile():
    instrucoes, atual = [], ""
    for linha in (RAIZ / "Dockerfile").read_text(encoding="utf-8").splitlines():
        if not atual and (not linha.strip() or linha.lstrip().startswith("#")):
            continue
        continua = linha.rstrip().endswith("\\")
        atual += (linha.rstrip()[:-1] if continua else linha.rstrip()) + " "
        if not continua:
            instrucoes.append(atual.strip())
            atual = ""
    return [(texto.split(None, 1)[0].upper(), texto.split(None, 1)[1] if " " in texto else "") for texto in instrucoes]


def origens_copiadas():
    origens = []
    for nome, argumentos in instrucoes_do_dockerfile():
        if nome == "COPY":
            partes = [parte for parte in shlex.split(argumentos) if not parte.startswith("--")]
            origens.extend(partes[:-1])
    return origens


def modulos_do_laboratorio(nome, vistos=None):
    """Módulos de scripts/ que `nome` importa, direta ou indiretamente (inclusive imports dentro de funções)."""
    vistos = set() if vistos is None else vistos
    caminho = RAIZ / "scripts" / f"{nome}.py"
    if nome in vistos or not caminho.is_file():
        return vistos
    vistos.add(nome)
    for no in ast.walk(ast.parse(caminho.read_text(encoding="utf-8"))):
        if isinstance(no, ast.Import):
            importados = [alias.name.split(".")[0] for alias in no.names]
        elif isinstance(no, ast.ImportFrom) and no.module and no.level == 0:
            importados = [no.module.split(".")[0]]
        else:
            continue
        for importado in importados:
            modulos_do_laboratorio(importado, vistos)
    return vistos


class ConteinerEDependenciasTests(unittest.TestCase):
    def test_imagem_python_312_slim_sem_privilegios_e_sem_configuracao_embutida(self):
        instrucoes = instrucoes_do_dockerfile()
        self.assertEqual(instrucoes[0], ("FROM", "python:3.12-slim"))
        usuarios = [argumentos for nome, argumentos in instrucoes if nome == "USER"]
        self.assertEqual(len(usuarios), 1)
        uid = usuarios[0].split(":")[0]
        self.assertTrue(uid.isdigit() and int(uid) > 0, "o contêiner roda com um UID numérico diferente de root")
        self.assertEqual(instrucoes[-1][0], "ENTRYPOINT", "o usuário comum vale para o processo final")
        for nome, argumentos in instrucoes:
            if nome in {"ENV", "ARG"}:
                self.assertNotRegex(argumentos, r"(?i)secret|password|token|key|credential|connection", argumentos)
                self.assertNotRegex(argumentos, r"VARELEIRA_|AZURE_", "a configuração chega pelas variáveis do contêiner")
        dockerfile = (RAIZ / "Dockerfile").read_text(encoding="utf-8")
        for proibido in ("--demo", "--local-sem-autenticacao", "VARELEIRA_EXIGIR_AUTENTICACAO", "--trusted-host", ".env"):
            self.assertNotIn(proibido, dockerfile)
        self.assertNotRegex(dockerfile, r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")

    def test_entrypoint_inicia_o_chat_em_todas_as_interfaces_e_sem_modo_local(self):
        entrypoint = [argumentos for nome, argumentos in instrucoes_do_dockerfile() if nome == "ENTRYPOINT"]
        self.assertEqual(len(entrypoint), 1)
        self.assertEqual(json.loads(entrypoint[0]), ["python", "scripts/chat_web.py", "--host", "0.0.0.0", "--port", "8000"])

    def test_verificacao_de_saude_usa_so_a_biblioteca_padrao_na_rota_de_saude(self):
        saude = [argumentos for nome, argumentos in instrucoes_do_dockerfile() if nome == "HEALTHCHECK"]
        self.assertEqual(len(saude), 1)
        comando = json.loads(saude[0].split("CMD", 1)[1])
        self.assertEqual(comando[:2], ["python", "-c"])
        self.assertIn("urllib.request", comando[2])
        self.assertIn("/healthz", comando[2])
        self.assertNotRegex(saude[0], r"curl|wget")
        self.assertIn("8000", comando[2])

    def test_a_imagem_copia_so_o_que_o_chat_importa_e_a_interface(self):
        origens = set(origens_copiadas())
        modulos = modulos_do_laboratorio("chat_web")
        self.assertEqual({origem for origem in origens if origem.startswith("scripts/")},
                         {f"scripts/{modulo}.py" for modulo in modulos})
        self.assertEqual({origem for origem in origens if origem.startswith("web/")}, {f"web/{nome}" for nome in ARQUIVOS_WEB})
        self.assertEqual({origem for origem in origens if origem.startswith("requirements/")},
                         {"requirements/l100.txt", "requirements/l200.txt"})
        self.assertEqual(len(origens), len(origens_copiadas()), "nenhuma origem repetida")
        for origem in origens:
            self.assertTrue((RAIZ / origem).is_file(), origem)
        destinos = {argumentos.split()[-1] for nome, argumentos in instrucoes_do_dockerfile() if nome == "COPY"}
        self.assertEqual(destinos, {"./requirements/", "./scripts/", "./web/"})
        self.assertIn(("WORKDIR", "/app"), instrucoes_do_dockerfile())
        self.assertIn(("RUN", "python -m pip install -r requirements/l200.txt"), instrucoes_do_dockerfile())

    def test_dockerignore_e_uma_lista_de_permissao_com_exclusoes_finais_de_segredos(self):
        regras = [linha.strip() for linha in (RAIZ / ".dockerignore").read_text(encoding="utf-8").splitlines()
                  if linha.strip() and not linha.lstrip().startswith("#")]
        self.assertEqual(regras[0], "**")
        permissoes = [regra[1:] for regra in regras if regra.startswith("!")]
        self.assertEqual(set(permissoes), set(origens_copiadas()))
        ultima_permissao = max(posicao for posicao, regra in enumerate(regras) if regra.startswith("!"))
        finais = set(regras[ultima_permissao + 1:])
        for exigida in ("**/.env", "**/.env.*", "**/*.pem", "**/*.key", ".git", ".venv", ".playwright-mcp", "context.md",
                        "session-state"):
            self.assertIn(exigida, finais)
        self.assertFalse(any(regra.startswith("!") for regra in regras[ultima_permissao + 1:]))

    def test_dependencias_do_l200_incluem_as_do_l100_e_fixam_as_novas(self):
        linhas = [linha.strip() for linha in (RAIZ / "requirements" / "l200.txt").read_text(encoding="utf-8").splitlines()
                  if linha.strip() and not linha.startswith("#")]
        self.assertEqual(linhas[0], "-r l100.txt")
        fixadas = {linha.split("==")[0] for linha in linhas[1:] if re.fullmatch(r"[A-Za-z0-9_.-]+==[0-9][0-9A-Za-z.]*", linha)}
        self.assertEqual(fixadas, {"fastapi", "uvicorn"})
        self.assertEqual(len(linhas), 3)
        l100 = (RAIZ / "requirements" / "l100.txt").read_text(encoding="utf-8")
        for pacote in ("fastapi", "uvicorn"):
            self.assertNotIn(pacote, l100, "o L100 não ganha dependências do L200")


if __name__ == "__main__":
    unittest.main()
