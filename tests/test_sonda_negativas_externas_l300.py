"""Testes das negativas externas do L300 (scripts/sonda_negativas_externas_l300.py): sem rede, sem Azure e sem az.

As exportações do aluno (az resource show e az role assignment list) são arquivos criados na hora, com GUIDs sorteados. A credencial do
Azure CLI e as requisições HTTP são dublês; o acesso a sockets é proibido, o que prova que o modo simulado e as recusas de entrada não
tocam a rede. O que importa: aprovação só com as três recusas esperadas e a causa identificada, nenhuma mensagem bruta, token, URL ou
ID na saída nem no relatório, e nenhum token enviado a um endereço fora do esperado.
"""

import contextlib
import email.message
import io
import json
import os
import re
import socket
import stat
import subprocess
import sys
import tempfile
import unittest
import urllib.error
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import support  # noqa: F401  (configura o caminho dos scripts)
import sonda_l300 as sonda
import sonda_negativas_externas_l300 as negativas
from support import RAIZ
from test_sonda_l300 import criar_link_simbolico, segmento

CONTA, BUSCA, MODELOS = "contafake01", "buscafake01", "modelosfake01"
CONTAINER, INDICE = "base-documental-l300", "vareleira-lar-l300"
SUBSCRICAO, GRUPO = str(uuid.uuid4()), "rg-fake-l300"
TENANT, OPERADOR, OUTRA_PESSOA = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
ID_DA_REQUISICAO = str(uuid.uuid4())  # aparece nas mensagens dos serviços e nunca pode sair

ESCOPO_GRUPO = f"/subscriptions/{SUBSCRICAO}/resourceGroups/{GRUPO}"
ID_CONTA = f"{ESCOPO_GRUPO}/providers/Microsoft.Storage/storageAccounts/{CONTA}"
ID_BUSCA = f"{ESCOPO_GRUPO}/providers/Microsoft.Search/searchServices/{BUSCA}"
ID_MODELOS = f"{ESCOPO_GRUPO}/providers/Microsoft.CognitiveServices/accounts/{MODELOS}"
ESCOPO_DO_CONTEINER = f"{ID_CONTA}/blobServices/default/containers/{CONTAINER}"

BLOB_XML = (f'<?xml version="1.0" encoding="utf-8"?><Error><Code>AuthorizationFailure</Code><Message>This request is not authorized to '
            f"perform this operation.\nRequestId:{ID_DA_REQUISICAO}\nTime:2026-10-11T12:00:00Z</Message></Error>").encode()
BUSCA_JSON = json.dumps({"error": {"code": "", "message": f"Forbidden. publicNetworkAccess: Disabled. Request {ID_DA_REQUISICAO}"}}).encode()
MODELOS_JSON = json.dumps({"error": {"code": "403", "message": f"Public access is disabled. Please configure private endpoint. "
                                                              f"{ID_DA_REQUISICAO}"}}).encode()
RESPOSTAS_ESPERADAS = {"blob": (403, BLOB_XML, "AuthorizationFailure"), "busca": (403, BUSCA_JSON, None), "modelos": (403, MODELOS_JSON, None)}


def recurso(tipo, nome, publico="Disabled", **extras):
    return {"id": f"{ESCOPO_GRUPO}/providers/{tipo}/{nome}", "name": nome, "type": tipo, "location": "regiao-x",
            "properties": {"publicNetworkAccess": publico, "outro": {"campo": 1}}, "tags": {"a": "b"}, **extras}


def servicos(conta="Disabled", busca="Disabled", modelos="Disabled"):
    return [recurso("Microsoft.Storage/storageAccounts", CONTA, conta), recurso("Microsoft.Search/searchServices", BUSCA, busca),
            recurso("Microsoft.CognitiveServices/accounts", MODELOS, modelos)]


def atribuicao(papel, escopo, principal=OPERADOR, **extras):
    return {"principalId": principal, "principalType": "User", "roleDefinitionName": papel, "scope": escopo, "condition": None, **extras}


def papeis_do_operador():
    return [atribuicao("Storage Blob Data Contributor", ESCOPO_DO_CONTEINER), atribuicao("Search Index Data Contributor", ID_BUSCA),
            atribuicao("Cognitive Services OpenAI User", ESCOPO_GRUPO)]


class CredencialDoCli:
    """O que o AzureCliCredential devolve: um token com as claims do operador. Registra os escopos pedidos."""

    def __init__(self, oid=OPERADOR, tid=TENANT, sem_token=()):
        self.oid, self.tid, self.sem_token, self.escopos, self.fechada = oid, tid, tuple(sem_token), [], False

    def get_token(self, escopo, **_):
        self.escopos.append(escopo)
        if escopo in self.sem_token:
            raise RuntimeError(f"sem token {ID_DA_REQUISICAO}")
        return SimpleNamespace(token=f"{segmento({'alg': 'none'})}.{segmento({'oid': self.oid, 'tid': self.tid})}.sig", expires_on=1)

    def close(self):
        self.fechada = True


class BaseNegativas(unittest.TestCase):
    def setUp(self):
        def proibido(*_args, **_kwargs):
            raise AssertionError("o teste tentou usar a rede")

        for alvo, nome in ((socket, "getaddrinfo"), (socket, "create_connection"), (socket.socket, "connect"), (socket.socket, "connect_ex")):
            patch = mock.patch.object(alvo, nome, proibido)
            patch.start()
            self.addCleanup(patch.stop)
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        self.pasta = Path(pasta.name)
        self.servicos, self.papeis = self.escrever("servicos.json", servicos()), self.escrever("papeis.json", papeis_do_operador())

    def escrever(self, nome, dados, codificacao="utf-8"):
        caminho = self.pasta / nome
        caminho.write_text(json.dumps(dados), encoding=codificacao)
        return caminho

    def argv(self, *extras, servicos=None, papeis=None):
        return ["--tenant-id", TENANT, "--conta", CONTA, "--busca", BUSCA, "--modelos", MODELOS,
                "--servicos", str(servicos or self.servicos), "--papeis", str(papeis or self.papeis), *extras]

    def rodar(self, argv, respostas=None, credencial=None, requisitar=None):
        """Executa `principal` com a credencial e o HTTP dublados. Devolve (código, texto impresso, resultado, requisições, credencial)."""
        saida, erro, requisicoes = io.StringIO(), io.StringIO(), []
        credencial = credencial or CredencialDoCli()
        respostas = RESPOSTAS_ESPERADAS if respostas is None else respostas

        def falso(metodo, url, cabecalhos, corpo, tempo=negativas.TEMPO_HTTP):
            servico = "blob" if ".blob." in url else "busca" if ".search." in url else "modelos"
            requisicoes.append((servico, metodo, url, dict(cabecalhos), corpo))
            resposta = respostas[servico]
            if isinstance(resposta, Exception):
                raise resposta
            return resposta

        with mock.patch.object(negativas, "criar_credencial", return_value=credencial), \
                mock.patch.object(negativas, "requisitar", requisitar or falso), contextlib.redirect_stderr(erro):
            codigo = negativas.principal(argv, saida)
        self.assertEqual(erro.getvalue(), "")
        texto = saida.getvalue()
        linhas = texto.splitlines()
        self.assertTrue(linhas[-1].startswith(sonda.SENTINELA), "a linha de resultado é a última")
        self.assertEqual(sum(linha.startswith(sonda.SENTINELA) for linha in linhas), 1, "exatamente uma linha de resultado")
        resultado = json.loads(linhas[-1][len(sonda.SENTINELA):])
        self.assertEqual((resultado["codigo"], resultado["sonda"], resultado["etapa"]), (codigo, "l300", "negativas-externas"))
        self.verificar_vazamento(texto)
        return codigo, texto, resultado, requisicoes, credencial

    def verificar_vazamento(self, texto):
        for fragmento in (CONTA, BUSCA, MODELOS, SUBSCRICAO, GRUPO, TENANT, OPERADOR, OUTRA_PESSOA, ID_DA_REQUISICAO, "https://", "Bearer",
                          "eyJ", ".windows.net", ".openai.azure.com", "This request is not authorized", "private endpoint",
                          "RequestId", "regiao-x"):
            self.assertNotIn(fragmento, texto)


class SimulacaoETests(BaseNegativas):
    def test_por_padrao_so_valida_as_entradas_e_imprime_o_plano_sem_rede_nem_token(self):
        def proibida(*_a, **_k):
            raise AssertionError("o modo simulado não pode obter token nem fazer requisições")

        codigo, texto, r, requisicoes, _ = self.rodar(self.argv(), requisitar=proibida)
        with mock.patch.object(negativas, "criar_credencial", proibida):
            self.assertEqual(negativas.principal(self.argv(), io.StringIO()), 0)
        self.assertEqual((codigo, r["veredicto"], r["causa"]), (0, "simulado", None))
        self.assertEqual(requisicoes, [])
        self.assertEqual((r["dados"]["modo"], r["dados"]["rede"], r["dados"]["identidade"], r["dados"]["aprovado"]),
                         ("simulado", "nao_usada", "nao_verificada", False))
        self.assertEqual(r["dados"]["precondicoes"], {
            "acesso_publico": {"blob": "desabilitado", "busca": "desabilitado", "modelos": "desabilitado"},
            "papeis_de_dados": {"blob": True, "busca": True, "modelos": True}, "operador": "unico_na_exportacao",
            "atribuicoes_condicionais_ignoradas": 0})
        self.assertIn("SIMULAÇÃO", texto)
        self.assertIn("Plano com --executar", texto)
        self.assertIn("NÃO é a prova da negativa", texto)
        self.assertEqual(texto.count("[ok]"), 3)

    def test_o_ponto_de_entrada_em_simulacao_roda_como_programa_sem_rede_e_emite_o_resultado_por_ultimo(self):
        ambiente = {nome: valor for nome, valor in os.environ.items() if not nome.startswith(("VARELEIRA_", "PYTHONPATH"))}
        ambiente["PYTHONDONTWRITEBYTECODE"] = "1"
        resultado = subprocess.run([sys.executable, str(RAIZ / "scripts" / "sonda_negativas_externas_l300.py"), *self.argv()],
                                   capture_output=True, text=True, encoding="utf-8", timeout=180, env=ambiente, cwd=RAIZ)
        self.assertEqual((resultado.returncode, resultado.stderr), (0, ""))
        linhas = resultado.stdout.splitlines()
        self.assertTrue(linhas[-1].startswith(sonda.SENTINELA))
        self.assertEqual(json.loads(linhas[-1][len(sonda.SENTINELA):])["veredicto"], "simulado")
        self.assertIn("SIMULAÇÃO", resultado.stdout)
        self.verificar_vazamento(resultado.stdout)

    def test_a_execucao_real_exige_o_sinalizador(self):
        codigo, _, r, requisicoes, _ = self.rodar(self.argv(), requisitar=mock.Mock(side_effect=AssertionError("sem --executar não há requisição")))
        self.assertEqual((codigo, r["veredicto"], requisicoes), (0, "simulado", []))
        codigo, texto, r, requisicoes, credencial = self.rodar(self.argv("--executar"))
        self.assertEqual((codigo, r["dados"]["modo"], r["dados"]["rede"], len(requisicoes)), (0, "executado", "usada", 3))
        self.assertTrue(credencial.fechada)

    def test_precondicoes_nao_atendidas_impedem_qualquer_tentativa_mesmo_com_executar(self):
        casos = {
            "busca com acesso público habilitado": (servicos(busca="Enabled"), papeis_do_operador(), ("busca", "habilitado", None)),
            "modelos sem a propriedade": ([{**s, "properties": {}} if s["name"] == MODELOS else s for s in servicos()], papeis_do_operador(),
                                          ("modelos", "ausente", None)),
            "sem papel no Blob": (servicos(), papeis_do_operador()[1:], ("blob", "desabilitado", False)),
            "papel só de gestão no Blob": (servicos(), [atribuicao("Contributor", ID_CONTA), *papeis_do_operador()[1:]],
                                           ("blob", "desabilitado", False)),
            "papel em outro contêiner": (servicos(), [atribuicao("Storage Blob Data Contributor", f"{ID_CONTA}/blobServices/default/"
                                                                                                    "containers/base-documental"),
                                                      *papeis_do_operador()[1:]], ("blob", "desabilitado", False)),
            "papel em outra conta": (servicos(), [atribuicao("Storage Blob Data Contributor", ID_CONTA.replace(CONTA, "outraconta99")),
                                                  *papeis_do_operador()[1:]], ("blob", "desabilitado", False)),
            "papel com condição": (servicos(), [atribuicao("Search Index Data Contributor", ID_BUSCA, condition="@Resource[x] == 1"),
                                                *papeis_do_operador()[0::2]], ("busca", "desabilitado", False)),
            "papel de outra pessoa": (servicos(), [*papeis_do_operador()[:2], atribuicao("Cognitive Services OpenAI User", ESCOPO_GRUPO,
                                                                                         principal=OUTRA_PESSOA)],
                                      ("modelos", "desabilitado", False)),
        }
        for nome, (recursos, atribuicoes, (servico, publico, papel)) in casos.items():
            with self.subTest(nome):
                argv = self.argv("--executar", "--operador-id", OPERADOR, servicos=self.escrever("s.json", recursos),
                                 papeis=self.escrever("p.json", atribuicoes))
                codigo, texto, r, requisicoes, credencial = self.rodar(argv, requisitar=mock.Mock(side_effect=AssertionError("sem rede")))
                self.assertEqual((codigo, r["veredicto"], r["causa"]), (3, "pendente", "precondicao_nao_atendida"))
                self.assertEqual((requisicoes, credencial.escopos, r["dados"]["rede"]), ([], [], "nao_usada"))
                self.assertEqual(r["dados"]["precondicoes"]["acesso_publico"][servico], publico)
                if papel is not None:
                    self.assertEqual(r["dados"]["precondicoes"]["papeis_de_dados"][servico], papel)
                self.assertIn("PENDENTE", texto)
                self.assertIn("nenhuma tentativa foi feita", texto)

    def test_papeis_em_qualquer_escopo_ancestral_ou_so_de_leitura_no_blob_contam(self):
        variantes = {
            "grupo de recursos": [atribuicao("Storage Blob Data Owner", ESCOPO_GRUPO), atribuicao("Search Index Data Reader", ESCOPO_GRUPO),
                                  atribuicao("Cognitive Services OpenAI Contributor", f"/subscriptions/{SUBSCRICAO}")],
            "recurso e índice": [atribuicao("Storage Blob Data Reader", ID_CONTA.lower() + "/"),
                                 atribuicao("Search Index Data Reader", f"{ID_BUSCA}/indexes/{INDICE}"),
                                 atribuicao("cognitive services openai user", ID_MODELOS)],
            "raiz": [atribuicao("Storage Blob Data Reader", "/"), atribuicao("Search Index Data Reader", "/"),
                     atribuicao("Cognitive Services OpenAI User", "/")],
        }
        for nome, atribuicoes in variantes.items():
            with self.subTest(nome):
                codigo, _, r, _, _ = self.rodar(self.argv(papeis=self.escrever("p.json", atribuicoes)))
                self.assertEqual((codigo, r["dados"]["precondicoes"]["papeis_de_dados"]), (0, {"blob": True, "busca": True, "modelos": True}))
        self.assertTrue(negativas.escopo_cobre("/subscriptions/ABC/", "/subscriptions/abc/resourcegroups/g"))
        self.assertFalse(negativas.escopo_cobre("/subscriptions/abc", "/subscriptions/abcd/resourcegroups/g"))
        self.assertFalse(negativas.escopo_cobre("/providers/Microsoft.Management/managementGroups/mg", ID_CONTA))

    def test_operador_unico_na_exportacao_ou_informado(self):
        misto = papeis_do_operador() + [atribuicao("Reader", ESCOPO_GRUPO, principal=OUTRA_PESSOA)]
        codigo, _, r, _, _ = self.rodar(self.argv(papeis=self.escrever("p.json", misto)))
        self.assertEqual((codigo, r["causa"], r["dados"]["motivo"], r["dados"]["principais"]), (1, "exportacao_invalida", "mais_de_um_principal", 2))
        codigo, _, r, _, _ = self.rodar(self.argv("--operador-id", OPERADOR.upper(), papeis=self.escrever("p.json", misto)))
        self.assertEqual((codigo, r["dados"]["precondicoes"]["operador"]), (0, "informado"))
        codigo, _, r, _, _ = self.rodar(self.argv(papeis=self.escrever("vazio.json", [])))
        self.assertEqual((codigo, r["dados"]["motivo"]), (1, "sem_atribuicoes"))


class ExecucaoTests(BaseNegativas):
    def test_aprovacao_exige_as_tres_recusas_com_a_causa_identificada_e_nada_vaza(self):
        relatorio = self.pasta / "negativas.json"
        codigo, texto, r, requisicoes, credencial = self.rodar(self.argv("--executar", "--relatorio", str(relatorio)))
        self.assertEqual((codigo, r["veredicto"], r["causa"]), (0, "aprovado", None))
        self.assertEqual(r["dados"]["resultados"], [
            {"dependencia": "blob", "http": 403, "codigo_servico": "AuthorizationFailure", "causa": "acesso_publico_desabilitado",
             "evidencia": "codigo_do_servico_e_precondicoes", "resultado": "recusa_esperada"},
            {"dependencia": "busca", "http": 403, "codigo_servico": None, "causa": "acesso_publico_desabilitado",
             "evidencia": "mensagem_do_servico", "resultado": "recusa_esperada"},
            {"dependencia": "modelos", "http": 403, "codigo_servico": "403", "causa": "acesso_publico_desabilitado",
             "evidencia": "mensagem_do_servico", "resultado": "recusa_esperada"}])
        self.assertEqual((r["dados"]["aprovado"], r["dados"]["identidade"], r["dados"]["origem"]), (True, "confere", "fora_da_rede"))
        self.assertIn("APROVADO", texto)
        # O token só vai ao endereço exato de cada serviço, com o escopo do serviço, em uma tentativa de leitura por serviço.
        self.assertEqual([(s, m, u) for s, m, u, _, _ in requisicoes], [
            ("blob", "GET", f"https://{CONTA}.blob.core.windows.net/{CONTAINER}?restype=container&comp=list&maxresults=1"),
            ("busca", "GET", f"https://{BUSCA}.search.windows.net/indexes/{INDICE}/docs/$count?api-version=2026-04-01"),
            ("modelos", "POST", f"https://{MODELOS}.openai.azure.com/openai/deployments/embeddings/embeddings?api-version=2024-10-21")])
        self.assertEqual(credencial.escopos, ["https://storage.azure.com/.default", "https://search.azure.com/.default",
                                              "https://cognitiveservices.azure.com/.default"])
        for _, _, _, cabecalhos, _ in requisicoes:
            self.assertTrue(cabecalhos["Authorization"].startswith("Bearer "))
        self.assertEqual(requisicoes[0][3]["x-ms-version"], "2024-11-04")
        self.assertEqual(json.loads(requisicoes[2][4]), {"input": [negativas.TEXTO_DE_CONFERENCIA]})
        self.assertEqual((requisicoes[0][4], requisicoes[1][4]), (None, None))
        # O relatório é novo, só tem o resultado fechado e, em sistemas POSIX, é legível só pelo dono.
        conteudo = relatorio.read_text(encoding="utf-8")
        self.verificar_vazamento(conteudo)
        relatado = json.loads(conteudo)
        self.assertEqual((relatado["versao_relatorio"], relatado["tipo"], relatado["resultado"]["veredicto"]), (1, "negativas-externas", "aprovado"))
        self.assertIn("VPN", relatado["limite"])
        if os.name == "posix":
            self.assertEqual(stat.S_IMODE(relatorio.stat().st_mode), 0o600)

    def test_causa_nao_identificada_e_pendencia_e_nunca_aprovacao(self):
        respostas = {**RESPOSTAS_ESPERADAS, "busca": (403, b'{"error": {"code": "", "message": "Forbidden"}}', None)}
        codigo, texto, r, _, _ = self.rodar(self.argv("--executar"), respostas=respostas)
        self.assertEqual((codigo, r["veredicto"], r["causa"], r["dados"]["aprovado"]), (3, "pendente", "causa_nao_identificada", False))
        busca = r["dados"]["resultados"][1]
        self.assertEqual((busca["causa"], busca["evidencia"], busca["resultado"]), ("nao_identificada", "nenhuma", "pendente"))
        self.assertIn("PENDENTE", texto)
        # O Blob com AuthorizationFailure só vale com as pré-condições conferidas; sem elas, o código sozinho não identifica o mecanismo.
        self.assertEqual(negativas.classificar_recusa("blob", 403, BLOB_XML, "AuthorizationFailure", False)["causa"], "nao_identificada")
        # Outras recusas do Blob (404, 5xx) e respostas sem corpo também ficam pendentes.
        for status in (404, 500, 302):
            respostas = {**RESPOSTAS_ESPERADAS, "blob": (status, b"", None)}
            codigo, _, r, _, _ = self.rodar(self.argv("--executar"), respostas=respostas)
            self.assertEqual((codigo, r["causa"], r["dados"]["resultados"][0]["http"]), (3, "causa_nao_identificada", status))

    def test_servico_que_aceita_a_operacao_reprova(self):
        for servico in negativas.SERVICOS:
            respostas = {**RESPOSTAS_ESPERADAS, servico: (200, b'{"value": []}', None)}
            with self.subTest(servico=servico):
                codigo, texto, r, _, _ = self.rodar(self.argv("--executar"), respostas=respostas)
                self.assertEqual((codigo, r["veredicto"], r["causa"], r["dados"]["aprovado"]), (3, "reprovado", "acesso_permitido", False))
                item = next(i for i in r["dados"]["resultados"] if i["dependencia"] == servico)
                self.assertEqual((item["resultado"], item["causa"], item["http"]), ("permitida", None, 200))
                self.assertIn("REPROVADO", texto)

    def test_dns_conexao_autenticacao_e_autorizacao_sao_causas_identificadas_mas_nao_aprovam(self):
        casos = (
            (urllib.error.URLError(socket.gaierror("sem nome")), "dns", "excecao_de_rede"),
            (urllib.error.URLError(ConnectionRefusedError()), "conexao", "excecao_de_rede"),
            ((401, b'{"error": {"code": "Unauthorized"}}', None), "autenticacao", "status_http"),
            ((403, b"<Error><Code>AuthenticationFailed</Code></Error>", "AuthenticationFailed"), "autenticacao", "codigo_do_servico"),
            ((403, b"<Error><Code>AuthorizationPermissionMismatch</Code></Error>", "AuthorizationPermissionMismatch"),
             "autorizacao_de_dados", "codigo_do_servico"),
            ((403, b'{"error": {"code": "PermissionDenied", "message": "lacks the required data action"}}', None),
             "autorizacao_de_dados", "codigo_do_servico"),
        )
        for resposta, causa, evidencia in casos:
            with self.subTest(causa=causa, evidencia=evidencia):
                if isinstance(resposta, Exception):
                    def requisitar(metodo, url, cabecalhos, corpo, tempo=30, falha=resposta, ok=RESPOSTAS_ESPERADAS):
                        if ".search." in url:
                            raise negativas.FalhaDeRede(negativas._tipo_de_falha(falha.reason))
                        return ok["blob" if ".blob." in url else "modelos"]

                    codigo, texto, r, _, _ = self.rodar(self.argv("--executar"), requisitar=requisitar)
                    item = r["dados"]["resultados"][1]
                    self.assertEqual((item["http"], item["codigo_servico"]), (None, None))
                else:
                    codigo, texto, r, _, _ = self.rodar(self.argv("--executar"), respostas={**RESPOSTAS_ESPERADAS, "busca": resposta})
                    item = r["dados"]["resultados"][1]
                self.assertEqual((codigo, r["veredicto"], r["causa"]), (3, "pendente", "recusa_por_outro_mecanismo"))
                self.assertEqual((item["causa"], item["evidencia"], item["resultado"]), (causa, evidencia, "pendente"))
                self.assertIn(item["causa"], negativas.CAUSAS)
                self.assertIn(causa, texto)

    def test_sem_resposta_de_nenhum_servico_nao_aprova_nem_reprova(self):
        falha = {servico: urllib.error.URLError(socket.gaierror("x")) for servico in negativas.SERVICOS}

        def requisitar(*_a, **_k):
            raise negativas.FalhaDeRede("dns")

        codigo, texto, r, _, _ = self.rodar(self.argv("--executar"), requisitar=requisitar)
        self.assertEqual((codigo, r["veredicto"], r["causa"], r["dados"]["aprovado"]), (2, "erro", "sem_resposta_dos_servicos", False))
        self.assertEqual([item["causa"] for item in r["dados"]["resultados"]], ["dns", "dns", "dns"])
        self.assertIn("SEM CONCLUSÃO", texto)

    def test_identidade_diferente_ou_indeterminada_nao_envia_nenhuma_requisicao(self):
        for credencial, causa, codigo_esperado in (
                (CredencialDoCli(oid=OUTRA_PESSOA), "identidade_diferente", 3),
                (CredencialDoCli(tid=str(uuid.uuid4())), "identidade_diferente", 3)):
            with self.subTest(causa=causa):
                codigo, _, r, requisicoes, _ = self.rodar(self.argv("--executar"), credencial=credencial)
                self.assertEqual((codigo, r["causa"], requisicoes), (codigo_esperado, causa, []))
                self.assertEqual(r["dados"]["identidade"], "diferente")

        class SemClaims(CredencialDoCli):
            def get_token(self, escopo, **_):
                return SimpleNamespace(token="token-sem-formato", expires_on=1)

        codigo, _, r, requisicoes, _ = self.rodar(self.argv("--executar"), credencial=SemClaims())
        self.assertEqual((codigo, r["causa"], requisicoes), (2, "identidade_indeterminada", []))

    def test_tenant_em_dominio_confere_so_o_operador(self):
        argv = self.argv("--executar")
        argv[argv.index("--tenant-id") + 1] = "exemplo.onmicrosoft.com"
        codigo, _, r, requisicoes, _ = self.rodar(argv, credencial=CredencialDoCli(tid=str(uuid.uuid4())))
        self.assertEqual((codigo, len(requisicoes)), (0, 3))

    def test_sem_token_nada_e_enviado_e_um_token_a_menos_deixa_so_aquele_servico_pendente(self):
        todos = CredencialDoCli(sem_token=("https://storage.azure.com/.default", "https://search.azure.com/.default",
                                           "https://cognitiveservices.azure.com/.default"))
        codigo, _, r, requisicoes, _ = self.rodar(self.argv("--executar"), credencial=todos)
        self.assertEqual((codigo, r["causa"], r["veredicto"], requisicoes), (2, "token_indisponivel", "erro", []))
        um = CredencialDoCli(sem_token=("https://search.azure.com/.default",))
        codigo, _, r, requisicoes, _ = self.rodar(self.argv("--executar"), credencial=um)
        self.assertEqual((codigo, r["causa"], [s for s, *_ in requisicoes]), (3, "recusa_por_outro_mecanismo", ["blob", "modelos"]))
        busca = r["dados"]["resultados"][1]
        self.assertEqual((busca["http"], busca["causa"], busca["evidencia"]), (None, "autenticacao", "token_nao_emitido"))

    def test_decidir_so_aprova_com_os_tres_servicos_e_as_tres_recusas_esperadas(self):
        def item(servico, resultado, causa="acesso_publico_desabilitado", http=403):
            return {"dependencia": servico, "http": http, "resultado": resultado, "causa": causa}

        esperados = [item(s, "recusa_esperada") for s in negativas.SERVICOS]
        self.assertEqual(negativas.decidir(esperados), ("aprovado", None, 0))
        with self.assertRaises(sonda.ErroSonda):
            negativas.decidir([])
        with self.assertRaises(sonda.ErroSonda):
            negativas.decidir(esperados[:2])
        self.assertEqual(negativas.decidir([*esperados[:2], item("modelos", "permitida", None, 200)])[:2], ("reprovado", "acesso_permitido"))


class EntradasTests(BaseNegativas):
    def test_argumentos_sao_validados_antes_de_montar_qualquer_url(self):
        def sem_requisicao(*_a, **_k):
            raise AssertionError("argumento inválido não chega à rede")

        casos = (
            (["--conta", "meu-site.exemplo/"], "argumentos_invalidos", {"invalidos": ["conta"]}),
            (["--busca", "Busca_Maiuscula"], "argumentos_invalidos", {"invalidos": ["busca"]}),
            (["--modelos", "x" * 70], "argumentos_invalidos", {"invalidos": ["modelos"]}),
            (["--tenant-id", "tenant com espaço"], "argumentos_invalidos", {"invalidos": ["tenant_id"]}),
            (["--container", "base-documental"], "argumentos_invalidos", {"invalidos": ["container"]}),
            (["--indice", "vareleira-lar-l100"], "argumentos_invalidos", {"invalidos": ["indice"]}),
            (["--deployment", "../x"], "argumentos_invalidos", {"invalidos": ["deployment"]}),
            (["--operador-id", "nao-e-guid"], "argumentos_invalidos", {"invalidos": ["operador_id"]}),
        )
        for substituicao, causa, extras in casos:
            with self.subTest(argumento=substituicao[0]):
                argv = self.argv("--executar")
                if substituicao[0] in argv:
                    argv[argv.index(substituicao[0]) + 1] = substituicao[1]
                else:
                    argv += substituicao
                codigo, texto, r, requisicoes, credencial = self.rodar(argv, requisitar=sem_requisicao)
                self.assertEqual((codigo, r["causa"], requisicoes, credencial.escopos), (1, causa, [], []))
                for chave, valor in extras.items():
                    self.assertEqual(r["dados"][chave], valor)
                self.assertNotIn(substituicao[1], texto)
        codigo, _, r, _, _ = self.rodar(["--executar"])
        self.assertEqual((codigo, r["causa"], r["dados"]["ausentes"]), (1, "argumentos_ausentes",
                                                                      ["tenant_id", "conta", "busca", "modelos", "servicos", "papeis"]))
        for argv in (["--ajuda"], self.argv("--detalhes"), self.argv("--token", "abc")):
            codigo, _, r, _, _ = self.rodar(argv)
            self.assertEqual((codigo, r["causa"]), (1, "uso_invalido"))

    def test_padroes_do_l300_e_valores_informados_formam_destinos_exatos(self):
        entradas = negativas.ler_argumentos(self.argv("--container", "base-documental-l300-b", "--indice", "vareleira-lar-l300-b",
                                                      "--deployment", "emb.v2"))
        urls = [destino.url for destino in negativas.montar_destinos(entradas)]
        self.assertEqual(urls, [
            f"https://{CONTA}.blob.core.windows.net/base-documental-l300-b?restype=container&comp=list&maxresults=1",
            f"https://{BUSCA}.search.windows.net/indexes/vareleira-lar-l300-b/docs/$count?api-version=2026-04-01",
            f"https://{MODELOS}.openai.azure.com/openai/deployments/emb.v2/embeddings?api-version=2024-10-21"])
        padrao = negativas.ler_argumentos(self.argv())
        self.assertEqual((padrao.container, padrao.indice, padrao.deployment), (CONTAINER, INDICE, "embeddings"))

    def test_o_token_nunca_vai_a_um_destino_diferente_do_montado_dos_nomes(self):
        destino = negativas.montar_destinos(negativas.ler_argumentos(self.argv()))[0]
        for alterado in (negativas.Destino(**{**destino.__dict__, "host": "exemplo.com"}),
                         negativas.Destino(**{**destino.__dict__, "host": f"{CONTA}.blob.core.windows.net.exemplo.com"}),
                         negativas.Destino(**{**destino.__dict__, "host": f"{CONTA}.blob.core.windows.net:8443"}),
                         negativas.Destino(**{**destino.__dict__, "host": f"usuario@{CONTA}.blob.core.windows.net"}),
                         negativas.Destino(**{**destino.__dict__, "servico": "busca"})):
            with self.subTest(host=alterado.host[:20]), self.assertRaises(sonda.ErroSonda) as erro:
                negativas.exigir_destino_exato(alterado)
            self.assertEqual(erro.exception.causa, "destino_inesperado")

    def test_exportacoes_invalidas_sao_recusadas_so_com_o_nome_do_arquivo_e_o_motivo(self):
        grande = self.pasta / "grande.json"
        grande.write_text(" " * 64, encoding="utf-8")
        ruim = self.pasta / "ruim.json"
        ruim.write_text("{nao e json", encoding="utf-8")
        casos = (
            (dict(servicos=self.pasta / "inexistente.json"), "servicos", "nao_encontrado"),
            (dict(servicos=ruim), "servicos", "json_invalido"),
            (dict(servicos=self.escrever("texto.json", "uma string")), "servicos", "formato"),
            (dict(servicos=self.escrever("lista.json", [1, 2])), "servicos", "formato"),
            (dict(servicos=self.escrever("dois.json", servicos()[:2])), "servicos", "servico_ausente"),
            (dict(servicos=self.escrever("sem-propriedades.json", [{"id": "x", "name": CONTA, "type": "Microsoft.Storage/storageAccounts"}])),
             "servicos", "id_do_recurso"),
            (dict(servicos=self.escrever("subrecurso.json", [{**recurso("Microsoft.Storage/storageAccounts", CONTA),
                                                             "id": ID_CONTA + "/blobServices/default"}, *servicos()[1:]])),
             "servicos", "id_do_recurso"),
            (dict(servicos=self.escrever("repetido.json", [*servicos(), recurso("Microsoft.Storage/storageAccounts", CONTA, "Enabled")])),
             "servicos", "recurso_repetido"),
            (dict(papeis=self.escrever("objeto.json", {"principalId": OPERADOR})), "papeis", "formato"),
            (dict(papeis=self.escrever("sem-campos.json", [{"principalId": OPERADOR, "scope": "/x"}])), "papeis", "formato"),
            (dict(papeis=self.escrever("principal-ruim.json", [atribuicao("Reader", "/x", principal="nao-guid")])), "papeis", "formato"),
            (dict(papeis=self.escrever("escopo-ruim.json", [atribuicao("Reader", "sem-barra")])), "papeis", "formato"),
        )
        for nomes, arquivo, motivo in casos:
            with self.subTest(arquivo=arquivo, motivo=motivo):
                codigo, texto, r, _, _ = self.rodar(self.argv(**nomes))
                self.assertEqual((codigo, r["causa"], r["dados"]["arquivo"], r["dados"]["motivo"]), (1, "exportacao_invalida", arquivo, motivo))
                self.assertNotIn("ruim.json", texto)
        with mock.patch.object(negativas, "LIMITE_DO_ARQUIVO", 10):
            codigo, _, r, _, _ = self.rodar(self.argv(servicos=grande))
        self.assertEqual((codigo, r["dados"]["motivo"]), (1, "grande"))

    def test_aceita_utf16_do_powershell_5_varios_arquivos_e_campos_a_mais(self):
        utf16 = self.escrever("utf16.json", servicos(), codificacao="utf-16")
        um_por_arquivo = [self.escrever(f"s{i}.json", item) for i, item in enumerate(servicos())]
        papeis_a, papeis_b = self.escrever("a.json", papeis_do_operador()[:1]), self.escrever("b.json", papeis_do_operador()[1:])
        for argv in (self.argv(servicos=utf16),
                     ["--tenant-id", TENANT, "--conta", CONTA, "--busca", BUSCA, "--modelos", MODELOS,
                      "--servicos", *map(str, um_por_arquivo), "--papeis", str(papeis_a), str(papeis_b)]):
            codigo, _, r, _, _ = self.rodar(argv)
            self.assertEqual((codigo, r["veredicto"]), (0, "simulado"))
        com_bom = self.pasta / "bom.json"
        com_bom.write_bytes(b"\xef\xbb\xbf" + json.dumps(papeis_do_operador()).encode("utf-8"))
        self.assertEqual(self.rodar(self.argv(papeis=com_bom))[0], 0)
        repetidas = ["--tenant-id", TENANT, "--conta", CONTA, "--busca", BUSCA, "--modelos", MODELOS, "--servicos", str(um_por_arquivo[0]),
                     "--servicos", str(um_por_arquivo[1]), str(um_por_arquivo[2]), "--papeis", str(papeis_a), "--papeis", str(papeis_b)]
        self.assertEqual(self.rodar(repetidas)[0], 0, "uma opção repetida acumula os arquivos em vez de descartar os anteriores")

    def test_relatorio_e_sempre_novo_e_o_destino_e_conferido_antes_de_tudo(self):
        existente = self.pasta / "existente.json"
        existente.write_text("conteudo anterior", encoding="utf-8")
        for destino, motivo in ((existente, "ja_existe"), (self.pasta / "nao-existe" / "r.json", "pasta_inexistente"),
                                (self.pasta / "r.txt", "nome"), (self.pasta / "..r.json", "nome")):
            with self.subTest(motivo=motivo):
                codigo, _, r, requisicoes, credencial = self.rodar(self.argv("--executar", "--relatorio", str(destino)))
                self.assertEqual((codigo, r["causa"], r["dados"]["motivo"], requisicoes, credencial.escopos), (1, "relatorio_invalido", motivo, [], []))
        self.assertEqual(existente.read_text(encoding="utf-8"), "conteudo anterior", "nunca sobrescreve")
        # O relatório de uma execução não aprovada também é gravado: pendências e falhas contam como registro.
        pendente = self.pasta / "pendente.json"
        respostas = {**RESPOSTAS_ESPERADAS, "busca": (403, b"{}", None)}
        self.rodar(self.argv("--executar", "--relatorio", str(pendente)), respostas=respostas)
        self.assertEqual(json.loads(pendente.read_text(encoding="utf-8"))["resultado"]["causa"], "causa_nao_identificada")


class ControlesDeSegurancaTests(BaseNegativas):
    """Cada controle é exercitado com a função REAL: nenhum teste aqui substitui o código que ele protege."""

    def linha(self):
        return sonda.proteger(sonda.Resultado(negativas.ETAPA, 0, "simulado"), ())

    def test_o_relatorio_nunca_trunca_um_arquivo_existente(self):
        existente = self.pasta / "existente.json"
        existente.write_text("conteudo anterior", encoding="utf-8")
        with self.assertRaises(FileExistsError):
            negativas.gravar_relatorio(existente, self.linha())
        self.assertEqual(existente.read_text(encoding="utf-8"), "conteudo anterior")
        novo = self.pasta / "novo.json"
        negativas.gravar_relatorio(novo, self.linha())
        self.assertEqual(json.loads(novo.read_text(encoding="utf-8"))["resultado"]["veredicto"], "simulado")

    def test_uma_corrida_que_cria_o_arquivo_depois_da_conferencia_do_nome_nao_o_sobrescreve(self):
        corrida = self.pasta / "corrida.json"

        def requisitar(metodo, url, cabecalhos, corpo, tempo=negativas.TEMPO_HTTP):
            corrida.write_text("do intruso", encoding="utf-8")  # o nome estava livre na conferência; alguém o cria antes da gravação
            return RESPOSTAS_ESPERADAS["blob" if ".blob." in url else "busca" if ".search." in url else "modelos"]

        saida, erro = io.StringIO(), io.StringIO()
        with mock.patch.object(negativas, "criar_credencial", return_value=CredencialDoCli()), \
                mock.patch.object(negativas, "requisitar", requisitar), contextlib.redirect_stderr(erro):
            codigo = negativas.principal(self.argv("--executar", "--relatorio", str(corrida)), saida)
        self.assertEqual(corrida.read_text(encoding="utf-8"), "do intruso", "o arquivo criado por outra pessoa nunca é sobrescrito")
        self.assertEqual(codigo, 0, "o resultado continua valendo")
        self.assertIn("não foi possível criar o relatório", erro.getvalue().lower())
        self.assertEqual(json.loads(saida.getvalue().splitlines()[-1][len(sonda.SENTINELA):])["veredicto"], "aprovado")

    def test_um_link_simbolico_no_lugar_do_relatorio_nunca_e_seguido(self):
        existente, pendente = self.pasta / "existente.json", self.pasta / "alvo-pendente.json"
        existente.write_text("conteudo anterior", encoding="utf-8")
        para_existente, para_pendente = self.pasta / "link-existente.json", self.pasta / "link-pendente.json"
        criar_link_simbolico(para_existente, existente)
        criar_link_simbolico(para_pendente, pendente)  # pendente: exists() é falso, e só is_symlink() o enxerga
        for link in (para_existente, para_pendente):
            with self.subTest(link=link.name):
                codigo, _, r, requisicoes, _ = self.rodar(self.argv("--executar", "--relatorio", str(link)),
                                                          requisitar=mock.Mock(side_effect=AssertionError("sem rede")))
                self.assertEqual((codigo, r["causa"], r["dados"]["motivo"], requisicoes), (1, "relatorio_invalido", "ja_existe", []))
        self.assertFalse(pendente.exists())
        # Se um link surgisse depois da conferência, a criação exclusiva também não escreveria através dele em um arquivo existente.
        with self.assertRaises(FileExistsError):
            negativas.gravar_relatorio(para_existente, self.linha())
        self.assertEqual(existente.read_text(encoding="utf-8"), "conteudo anterior")

    @unittest.skipUnless(os.name == "posix", "no Windows o O_EXCL segue um link pendente e cria o alvo; lá vale a conferência prévia do nome")
    def test_em_posix_a_criacao_exclusiva_tambem_recusa_um_link_pendente(self):
        alvo, link = self.pasta / "alvo-pendente.json", self.pasta / "link-pendente.json"
        criar_link_simbolico(link, alvo)
        with self.assertRaises(FileExistsError):
            negativas.gravar_relatorio(link, self.linha())
        self.assertFalse(alvo.exists(), "o link pendente não é seguido para criar o arquivo")

    def test_a_barreira_por_valor_esta_ligada_ao_ponto_de_entrada_e_o_codigo_e_o_relatorio_sao_os_da_linha_emitida(self):
        # Um nome igual a uma palavra do vocabulário da linha ("blob", "busca", "modelos", "aprovado") é um valor de Entradas.privados():
        # a linha vira a do defeito, o código de saída é o dela (4, não o 0 da aprovação) e o relatório grava a MESMA linha.
        def executar_com(relatorio, conta=CONTA, busca=BUSCA, modelos=MODELOS, tenant=TENANT):
            exportacao = [recurso("Microsoft.Storage/storageAccounts", conta), recurso("Microsoft.Search/searchServices", busca),
                          recurso("Microsoft.CognitiveServices/accounts", modelos)]
            papeis = [atribuicao(papel, ESCOPO_GRUPO) for papel in ("Storage Blob Data Contributor", "Search Index Data Contributor",
                                                                    "Cognitive Services OpenAI User")]
            argv = ["--tenant-id", tenant, "--conta", conta, "--busca", busca, "--modelos", modelos,
                    "--servicos", str(self.escrever("s.json", exportacao)), "--papeis", str(self.escrever("p.json", papeis)),
                    "--executar", "--relatorio", str(relatorio)]
            return self.rodar(argv)

        codigo, _, r, _, _ = executar_com(self.pasta / "referencia.json")
        self.assertEqual((codigo, r["veredicto"]), (0, "aprovado"))
        for chave, valor in (("conta", "blob"), ("busca", "busca"), ("modelos", "modelos"), ("tenant", "aprovado")):
            with self.subTest(chave=chave):
                relatorio = self.pasta / f"bloqueado-{chave}.json"
                codigo, _, r, _, _ = executar_com(relatorio, **{chave: valor})
                self.assertEqual((codigo, r["codigo"], r["veredicto"], r["causa"]), (4, 4, "erro", "saida_bloqueada"))
                self.assertEqual(r["dados"], {"padroes": ["valor_de_configuracao"]})
                self.assertEqual(json.loads(relatorio.read_text(encoding="utf-8"))["resultado"], r)

    def test_se_a_propria_barreira_falhar_o_relatorio_e_a_linha_sao_os_de_ultimo_recurso_e_o_codigo_e_4(self):
        def avaliacao_com_defeito(entradas, saida):
            return sonda.Resultado(negativas.ETAPA, None, "aprovado", None, {"modo": "executado"})  # sem código, a serialização falha

        relatorio, saida = self.pasta / "defeito.json", io.StringIO()
        with mock.patch.object(negativas, "avaliar", avaliacao_com_defeito):
            codigo = negativas.principal(self.argv("--relatorio", str(relatorio)), saida)
        linha = json.loads(saida.getvalue().splitlines()[-1][len(sonda.SENTINELA):])
        self.assertEqual((codigo, linha["codigo"], linha["veredicto"], linha["causa"]), (4, 4, "erro", "saida_invalida"))
        self.assertEqual(json.loads(relatorio.read_text(encoding="utf-8"))["resultado"], linha)

    def test_um_destino_adulterado_e_recusado_antes_de_qualquer_token(self):
        comum, indexacao = sonda.mod.lab_comum, sonda.mod.lab_indexacao
        adulteracoes = ((comum, "SUFIXO_BLOB", "blob.core.windows.net.exemplo.com"), (comum, "SUFIXO_BLOB", "blob.core.windows.net:8443"),
                        (indexacao, "SUFIXO_BUSCA", "search.windows.net@exemplo.com"), (indexacao, "SUFIXO_MODELOS", "exemplo.com"))
        for modulo, nome, valor in adulteracoes:
            with self.subTest(nome=nome, valor=valor), mock.patch.object(modulo, nome, valor):
                with self.assertRaises(sonda.ErroSonda) as erro:
                    negativas.montar_destinos(negativas.ler_argumentos(self.argv()))
                self.assertEqual((erro.exception.causa, erro.exception.codigo), ("destino_inesperado", sonda.USO))
                codigo, _, r, requisicoes, credencial = self.rodar(self.argv("--executar"),
                                                                    requisitar=mock.Mock(side_effect=AssertionError("sem rede")))
                self.assertEqual((codigo, r["causa"], requisicoes, credencial.escopos), (1, "destino_inesperado", [], []))


class ClassificacaoETransporteTests(unittest.TestCase):
    def test_classificacao_de_cada_servico_por_status_codigo_e_marcadores(self):
        classificar = negativas.classificar_recusa
        tabela = (
            ("blob", 403, BLOB_XML, "AuthorizationFailure", ("acesso_publico_desabilitado", "codigo_do_servico_e_precondicoes")),
            ("blob", 403, BLOB_XML, None, ("acesso_publico_desabilitado", "codigo_do_servico_e_precondicoes")),
            ("blob", 403, b"<Error><Code>AuthorizationPermissionMismatch</Code><Message>using this permission</Message></Error>", None,
             ("autorizacao_de_dados", "codigo_do_servico")),
            ("blob", 403, b"<Error><Code>Outro</Code></Error>", None, ("nao_identificada", "nenhuma")),
            ("busca", 403, b'{"error": {"message": "Public network access is disabled for this service"}}', None,
             ("acesso_publico_desabilitado", "mensagem_do_servico")),
            ("busca", 403, b'{"error": {"message": "publicNetworkAccess is set to Disabled"}}', None,
             ("acesso_publico_desabilitado", "mensagem_do_servico")),
            ("modelos", 403, b'{"error": {"code": "403", "message": "Public access is disabled. Please configure private endpoint."}}',
             None, ("acesso_publico_desabilitado", "mensagem_do_servico")),
            ("modelos", 403, b'{"error": {"message": "Access denied due to Virtual Network/Firewall rules."}}', None,
             ("nao_identificada", "nenhuma")),
            ("modelos", 401, b'{"error": {"code": "401", "message": "Access denied due to invalid subscription key."}}', None,
             ("autenticacao", "status_http")),
            ("busca", 403, b"nao e json", None, ("nao_identificada", "nenhuma")),
            ("busca", 403, b"", None, ("nao_identificada", "nenhuma")),
        )
        for servico, status, corpo, codigo, (causa, evidencia) in tabela:
            with self.subTest(servico=servico, causa=causa, corpo=corpo[:20]):
                registro = classificar(servico, status, corpo, codigo, True)
                self.assertEqual((registro["causa"], registro["evidencia"]), (causa, evidencia))
                self.assertIn(registro["causa"], negativas.CAUSAS)
                self.assertEqual(registro["resultado"], "recusa_esperada" if causa == "acesso_publico_desabilitado" else "pendente")
        # Um 403 com a mensagem de acesso público desabilitado só vale como recusa esperada com o status 403.
        self.assertEqual(classificar("modelos", 400, b"Public access is disabled", None, True)["resultado"], "pendente")
        # O código vem do vocabulário conhecido; qualquer outro vira "outro", e o texto da mensagem nunca aparece no registro.
        registro = classificar("blob", 403, b"<Error><Code>CodigoQualquer</Code><Message>segredo-123</Message></Error>", None, True)
        self.assertEqual(registro["codigo_servico"], "outro")
        self.assertNotIn("segredo-123", json.dumps(registro))
        self.assertEqual(classificar("blob", 403, b"\xff\xfe\x00", None, True)["causa"], "nao_identificada")

    def test_requisitar_devolve_status_e_corpo_limitado_e_classifica_falhas_sem_resposta(self):
        class Resposta:
            status = 200
            headers = email.message.Message()

            def __init__(self, corpo):
                self.corpo = corpo

            def read(self, limite):
                return self.corpo[:limite]

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

        with mock.patch.object(negativas._ABRIDOR, "open", return_value=Resposta(b"x" * 100000)) as abrir:
            status, corpo, codigo = negativas.requisitar("GET", "https://x/", {}, None)
        self.assertEqual((status, len(corpo), codigo), (200, negativas.LIMITE_DO_CORPO, None))
        self.assertEqual(abrir.call_args.kwargs["timeout"], negativas.TEMPO_HTTP)
        cabecalhos = email.message.Message()
        cabecalhos["x-ms-error-code"] = "AuthorizationFailure"
        erro = urllib.error.HTTPError("https://x/", 403, "Forbidden", cabecalhos, io.BytesIO(b"corpo"))
        with mock.patch.object(negativas._ABRIDOR, "open", side_effect=erro):
            self.assertEqual(negativas.requisitar("GET", "https://x/", {}, None), (403, b"corpo", "AuthorizationFailure"))
        for falha, tipo in ((urllib.error.URLError(socket.gaierror("x")), "dns"), (urllib.error.URLError(ConnectionResetError()), "conexao"),
                            (TimeoutError("x"), "conexao"), (socket.gaierror("x"), "dns"), (ConnectionRefusedError(), "conexao"),
                            (urllib.error.URLError("texto"), "conexao")):
            with self.subTest(tipo=tipo, falha=type(falha).__name__), mock.patch.object(negativas._ABRIDOR, "open", side_effect=falha):
                with self.assertRaises(negativas.FalhaDeRede) as capturada:
                    negativas.requisitar("GET", "https://x/", {}, None)
            self.assertEqual(capturada.exception.tipo, tipo)

    def test_o_abridor_nao_segue_redirecionamentos(self):
        self.assertTrue(any(isinstance(manipulador, sonda.SemRedirecionamento) for manipulador in negativas._ABRIDOR.handlers))

    def test_o_codigo_e_a_documentacao_publica_nao_fixam_valores_do_ambiente(self):
        codigo = (RAIZ / "scripts" / "sonda_negativas_externas_l300.py").read_text(encoding="utf-8")
        self.assertEqual(re.findall(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", codigo, re.IGNORECASE), [])
        for opcao in ("--tenant-id", "--conta", "--busca", "--modelos", "--container", "--indice", "--deployment", "--servicos", "--papeis",
                      "--operador-id", "--relatorio", "--executar"):
            self.assertIn(opcao, negativas.__doc__)
        for exigido in ("az resource show", "az role assignment list", "L300_SONDA_RESULTADO=", "AzureCli", "publicNetworkAccess"):
            self.assertIn(exigido, codigo)
        for papeis in negativas.PAPEIS_DE_DADOS.values():
            for nome in papeis:
                self.assertIn(nome, negativas.__doc__)
        self.assertIn("Não existe --detalhes", negativas.__doc__)


if __name__ == "__main__":
    unittest.main()
