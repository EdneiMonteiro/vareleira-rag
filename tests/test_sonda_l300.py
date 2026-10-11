"""Testes offline da sonda do L300 (scripts/sonda_l300.py): nenhuma rede e nenhum Azure. A CLI de ingestão, a busca, os modelos, as
identidades e o DNS são dublês.

Cada teste roda a sonda pelo mesmo ponto de entrada do Job (`principal`) e confere o contrato: UMA linha sentinela no stdout, nada no
stderr, código de saída coerente, vocabulário fechado e nenhum nome de recurso, GUID, URL, host, IP ou token no resultado. O acesso a
sockets é proibido durante todos os testes, o que prova que nenhuma etapa dublada tentou usar a rede. Os GUIDs são sorteados a cada
execução (nunca valores fixos), e os tokens de teste são montados em tempo de execução.

Os dublês e as constantes daqui são reaproveitados pelos testes dos helpers do computador de quem coordena.
"""

import base64
import contextlib
import io
import json
import os
import re
import socket
import subprocess
import sys
import threading
import unittest
import uuid
from types import SimpleNamespace
from unittest import mock

import support  # noqa: F401  (configura o caminho dos scripts)
import lab_acesso
import lab_chat
import lab_comum
import lab_geracao
import lab_indexacao
import lab_ingestao as li
import sonda_l300 as sonda
from support import RAIZ

CONTA, BUSCA, MODELOS = "contafake01", "buscafake01", "modelosfake01"
ASSINATURA, GRUPO = str(uuid.uuid4()), "rg-fake-l300"
CLIENT_ID, APP_ID = str(uuid.uuid4()), str(uuid.uuid4())
URL = "https://chat.ambiente-fake123.regiao-x.azurecontainerapps.io"
AMBIENTE = {"VARELEIRA_PROBE_CONTA": CONTA, "VARELEIRA_PROBE_BUSCA": BUSCA, "VARELEIRA_PROBE_MODELOS": MODELOS,
            "VARELEIRA_PROBE_ASSINATURA": ASSINATURA, "VARELEIRA_PROBE_GRUPO": GRUPO, "VARELEIRA_PROBE_CLIENT_ID": CLIENT_ID}
PROIBIDOS = (CONTA, BUSCA, MODELOS, ASSINATURA, GRUPO, CLIENT_ID, APP_ID, "ambiente-fake123", "https://", "Bearer", "eyJ",
             ".windows.net", ".openai.azure.com", "azurecontainerapps")
OPERACIONAL, MARCADOR = "VLAR-OP-ATD-1.0", "ATD-L300-ROTEIRO-7Q4K"
CONTAINER_L300, INDICE_L300 = "base-documental-l300", "vareleira-lar-l300"
IDENTIDADE = ["--identidade-gerenciada", "--client-id", CLIENT_ID]

CONFERENCIA = """\
[OK   ] Objetos do pipeline do L300: índice presente; data source presente; skillset presente; indexador presente
[OK   ] Detecção de exclusão: soft delete nativo do Blob ativo no data source (blobs excluídos saem do índice na execução seguinte)
[OK   ] Definições dos objetos: os quatro objetos são os definidos por esta ferramenta
[OK   ] Ambiente de execução do indexador: 'private' (esperado 'private')
[INFO ] Agenda do indexador: nenhuma (só executa sob demanda).
[OK   ] Indexador: última execução: resultado 'success'; itens processados 4; itens com falha 0; erros 0; avisos 0
[OK   ] Compatibilidade com o recuperador do L100: campos de resultado e campo vetorial 'vetor' presentes
[OK   ] Campo de acesso do índice: 'acesso' é texto filtrável (Edm.String)
[OK   ] Trechos do índice: 9 trecho(s) em 4 de 4 documento(s) esperado(s) do manifesto (VLAR-CG-1.0 3, VLAR-FAQ-1.0 2)
[OK   ] Classe de acesso dos trechos: atendimento 2, compartilhado 7; cada trecho tem a classe do manifesto
"""
AUSENTE_OK = "[OK   ] Documento VLAR-OP-ATD-1.0 ausente do índice: nenhum trecho (como esperado)\n"
STATUS_DO_INDEXADOR = {"status": "running", "executionHistory": [{}], "lastResult": {
    "status": "success", "startTime": "2026-10-10T20:00:00Z", "endTime": "2026-10-10T20:03:00Z", "itemsProcessed": 4,
    "itemsFailed": 0, "errors": [], "warnings": []}}
EVIDENCIA_DO_ROTEIRO = {"id": "op-0001", "citacao": f"O código educativo deste roteiro é {MARCADOR}.", "documento": "Roteiro interno",
                        "fonte": "vareleira-lar-l300/roteiro-interno-atendimento-v1.0.md", "versao": "1.0", "secao": "Código",
                        "clausulas": ""}
EVIDENCIA_COMPARTILHADA = {"id": "cg-0001", "citacao": "A cobertura básica protege o imóvel contra incêndio.", "documento": "Condições Gerais",
                           "fonte": "vareleira-lar-l300/condicoes-gerais-v1.0.md", "versao": "1.0", "secao": "Cobertura", "clausulas": "2.1"}


def resposta_do_chat(tipo="documentada", situacao="respondida", evidencias=(EVIDENCIA_DO_ROTEIRO,)):
    """O corpo JSON de uma resposta 200 do chat (o formato de RespostaChat.a_dict), com texto do modelo que nunca pode sair."""
    return json.dumps({"id": None, "id_requisicao": "abc", "tipo": tipo, "situacao": situacao, "texto": "Texto do modelo.", "aviso": "",
                       "evidencias": list(evidencias), "uso": None, "simulada": False, "aviso_simulacao": ""}).encode()


def segmento(dados) -> str:
    return base64.urlsafe_b64encode(json.dumps(dados).encode()).rstrip(b"=").decode()


def jwt(appid, **claims):
    """Um token com a forma de um JWT, montado na hora: nunca existe um valor de token fixo neste arquivo."""
    return f"{segmento({'alg': 'none'})}.{segmento({'appid': appid, **claims})}.sig"


def criar_link_simbolico(link, alvo, pasta=False):
    """Um link simbólico de verdade. O teste é pulado só se o sistema ou o usuário não puderem criá-lo (como no Windows sem privilégio)."""
    try:
        os.symlink(alvo, link, target_is_directory=pasta)
    except (OSError, NotImplementedError) as erro:
        raise unittest.SkipTest(f"o sistema não permite criar links simbólicos ({type(erro).__name__})") from None


def trechos_do_indice(*extras):
    por_documento = (("VLAR-CG-1.0", "compartilhado", 3), ("VLAR-GL-1.0", "compartilhado", 2), ("VLAR-FAQ-1.0", "compartilhado", 2),
                     (OPERACIONAL, "atendimento", 2))
    return [{"documento_id": documento, "acesso": classe} for documento, classe, quantidade in por_documento
            for _ in range(quantidade)] + list(extras)


class ClienteBuscaFalso:
    """Faz as vezes do cliente REST da busca: lista os trechos e devolve o status do indexador, sem rede."""

    def __init__(self, trechos=None, status=None, erro=None):
        self.trechos, self.status, self.erro, self.pedidos = trechos or [], status or STATUS_DO_INDEXADOR, erro, []

    def buscar(self, indice, corpo):
        self.pedidos.append((indice, corpo))
        if self.erro:
            raise self.erro
        return {"value": list(self.trechos)}

    def status_indexador(self, nome):
        if self.erro:
            raise self.erro
        return self.status


class CliFalsa:
    """Dublê de scripts/gerenciar_ingestao_l300.py: registra os argumentos e imprime saída PRIVADA (nomes, URL, token), como a real."""

    def __init__(self, respostas):
        self.respostas, self.chamadas = respostas, []

    def __call__(self, argv):
        self.chamadas.append(list(argv))
        texto, codigo = self.respostas[argv[argv.index("--etapa") + 1]]
        print(f"Destino: conta '{CONTA}', busca '{BUSCA}', https://{CONTA}.blob.core.windows.net, Authorization: Bearer "
              f"{jwt(CLIENT_ID)}", file=sys.stderr)
        print(texto)
        return codigo


class CredencialFalsa:
    def __init__(self, appid=CLIENT_ID, falha_em=()):
        self.appid, self.falha_em, self.escopos = appid, tuple(falha_em), []

    def get_token(self, escopo, **_):
        self.escopos.append(escopo)
        if escopo in self.falha_em:
            raise RuntimeError(f"sem token para {CONTA}")
        return SimpleNamespace(token=jwt(self.appid), expires_on=4102444800)


class BaseSonda(unittest.TestCase):
    def setUp(self):
        def proibido(*_args, **_kwargs):
            raise AssertionError("o teste tentou usar a rede")

        for alvo, nome in ((socket, "getaddrinfo"), (socket, "create_connection"), (socket.socket, "connect"),
                           (socket.socket, "connect_ex")):
            patch = mock.patch.object(alvo, nome, proibido)
            patch.start()
            self.addCleanup(patch.stop)

    def rodar(self, argv, ambiente=None, principal=None, proibidos=(), conferir_codigo=True):
        saida, fora, erro = io.StringIO(), io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(fora), contextlib.redirect_stderr(erro):
            codigo = (principal or sonda.principal)(argv, AMBIENTE if ambiente is None else ambiente, saida)
        self.assertEqual((fora.getvalue(), erro.getvalue()), ("", ""), "nada além da sentinela pode ir ao stdout ou ao stderr")
        linhas = saida.getvalue().splitlines()
        self.assertEqual(len(linhas), 1, "exatamente uma linha")
        self.assertTrue(linhas[0].startswith(sonda.SENTINELA))
        resultado = json.loads(linhas[0][len(sonda.SENTINELA):])
        if conferir_codigo:  # o vigia real encerra o processo; no teste a etapa volta, e só a linha vale
            self.assertEqual(resultado["codigo"], codigo)
        self.assertEqual(resultado["v"], 1)
        for fragmento in (*PROIBIDOS, *proibidos):
            self.assertNotIn(fragmento, linhas[0])
        return codigo, resultado

    @contextlib.contextmanager
    def com_cli(self, respostas, cliente=None):
        cli = CliFalsa(respostas)
        with mock.patch.object(sonda.mod.gerenciar_ingestao_l300, "principal", cli), \
                mock.patch.object(sonda.mod.lab_ingestao_l300, "abrir_cliente", return_value=cliente or ClienteBuscaFalso(
                    trechos_do_indice())), \
                mock.patch.object(sonda.mod.lab_ingestao_l300, "criar_credencial_gerenciada", return_value=object()):
            yield cli


class ContratoDaSondaTests(unittest.TestCase):
    def test_codigos_de_saida_sentinela_e_vocabulario_sao_os_do_laboratorio(self):
        self.assertEqual((sonda.OK, sonda.USO, sonda.ACESSO, sonda.DIVERGENCIA, sonda.INESPERADO),
                         (lab_comum.CODIGO_OK, lab_comum.CODIGO_USO, lab_comum.CODIGO_ACESSO, lab_comum.CODIGO_DIVERGENCIA,
                          lab_comum.CODIGO_INESPERADO))
        self.assertEqual(sonda.SENTINELA, "L300_SONDA_RESULTADO=")
        self.assertEqual((sonda.INDICE, sonda.CONTAINER, sonda.DOCUMENTO_OPERACIONAL),
                         ("vareleira-lar-l300", "base-documental-l300", "VLAR-OP-ATD-1.0"))
        self.assertEqual(sonda.ETAPAS, ("validar", "dns", "carregar", "criar", "executar", "conferir", "excluir", "restaurar", "resumo",
                                        "acesso", "http-interno", "negativas-mi"))
        self.assertEqual(set(sonda.ETAPAS), set(sonda.ETAPAS_DA_SONDA))

    def test_o_docstring_documenta_cada_etapa_e_cada_variavel_de_ambiente(self):
        doc = sonda.__doc__
        for etapa in sonda.ETAPAS:
            self.assertIn(etapa, doc, etapa)
        variaveis = {variavel for _, variavel, _, _ in sonda._VARIAVEIS} | {"VARELEIRA_PROBE_ETAPA"}
        for variavel in variaveis:
            self.assertTrue(variavel.startswith("VARELEIRA_PROBE_"), variavel)
            self.assertIn(variavel.removeprefix("VARELEIRA_PROBE"), doc, variavel)
        self.assertIn("L300_SONDA_RESULTADO=", doc)

    def test_o_docstring_nao_diz_que_http_interno_so_le_e_informa_o_consumo_e_o_codigo_da_linha_bloqueada(self):
        doc = " ".join(sonda.__doc__.split())
        somente_leitura = doc[doc.index("Efeitos, custo e limpeza"):doc.index("só leem")]
        self.assertNotIn("http-interno", somente_leitura)
        self.assertIn("http-interno não grava nada, mas CONSOME TOKENS", doc)
        self.assertIn("embeddings e por UMA geração", doc)
        self.assertIn("o código de saída é sempre o da linha realmente emitida (então 4", doc)

    def test_o_ponto_de_entrada_roda_como_no_job_e_emite_uma_unica_linha(self):
        ambiente = {nome: valor for nome, valor in os.environ.items() if not nome.startswith(("VARELEIRA_", "PYTHONPATH"))}
        ambiente["PYTHONDONTWRITEBYTECODE"] = "1"
        resultado = subprocess.run([sys.executable, str(RAIZ / "scripts" / "sonda_l300.py"), "--etapa", "validar"], capture_output=True,
                                   text=True, timeout=180, env=ambiente, cwd=RAIZ)
        self.assertEqual((resultado.returncode, resultado.stderr), (0, ""))
        linhas = resultado.stdout.splitlines()
        self.assertEqual(len(linhas), 1)
        corpo = json.loads(linhas[0].removeprefix(sonda.SENTINELA))
        self.assertEqual((corpo["etapa"], corpo["veredicto"], corpo["codigo"], corpo["dados"]["rede"]), ("validar", "aprovado", 0, "bloqueada"))
        ambiente["VARELEIRA_PROBE_ETAPA"] = "etapa-que-nao-existe"
        resultado = subprocess.run([sys.executable, str(RAIZ / "scripts" / "sonda_l300.py")], capture_output=True, text=True, timeout=120,
                                   env=ambiente, cwd=RAIZ)
        self.assertEqual((resultado.returncode, resultado.stderr), (1, ""))
        self.assertEqual(json.loads(resultado.stdout.removeprefix(sonda.SENTINELA))["causa"], "etapa_desconhecida")

    def test_o_codigo_publico_nao_fixa_valores_do_ambiente(self):
        codigo = (RAIZ / "scripts" / "sonda_l300.py").read_text(encoding="utf-8")
        self.assertEqual({achado.lower() for achado in re.findall(r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}", codigo, re.I)},
                         {sonda.GUID_ZERO})
        for proibido in ("brazilsouth", "eastus", "westeurope", "mango"):
            self.assertNotIn(proibido, codigo)
        # O prefixo "probe" só sobrevive nas variáveis de ambiente (contrato do Job); nomes e textos públicos usam "sonda".
        self.assertEqual([achado for achado in re.findall(r"\w*(?i:probe)\w*", codigo) if not achado.startswith("VARELEIRA_PROBE_")],
                         [])

    def test_o_transporte_so_fala_com_os_destinos_esperados(self):
        for url in ("https://chat.ambiente-fake123.regiao-x.azurecontainerapps.io/healthz",
                    "https://chat.internal.ambiente-fake123.regiao-x.azurecontainerapps.io/api/perguntar",
                    f"https://{CONTA}.blob.core.windows.net/base-documental?restype=container&comp=list",
                    f"https://{BUSCA}.search.windows.net/indexes?api-version=2026-04-01",
                    "https://management.azure.com/subscriptions/x?api-version=2024-01-01"):
            sonda.exigir_destino_esperado(url)
        for url in ("http://chat.ambiente-fake123.regiao-x.azurecontainerapps.io/healthz",
                    "https://usuario@chat.ambiente-fake123.regiao-x.azurecontainerapps.io/",
                    "https://chat.ambiente-fake123.regiao-x.azurecontainerapps.io:8443/",
                    "https://exemplo.com/", "https://exemplo.com/management.azure.com",
                    f"https://{CONTA}.blob.core.windows.net.exemplo.com/", f"https://{MODELOS}.openai.azure.com/",
                    "ftp://management.azure.com/", "file:///etc/passwd", "https:///sem-host", "https://x.azurecontainerapps.io@exemplo.com/"):
            with self.subTest(url=url[:30]), self.assertRaises(sonda.ErroSonda) as erro:
                sonda.exigir_destino_esperado(url)
            self.assertEqual((erro.exception.causa, erro.exception.codigo), ("destino_inesperado", sonda.USO))

    def test_nenhum_transporte_chega_a_rede_com_um_destino_inesperado_e_o_redirecionamento_nunca_e_seguido(self):
        def proibido(*_args, **_kwargs):
            raise AssertionError("o transporte tentou abrir uma conexão")

        with mock.patch.object(sonda._ABRIDOR, "open", proibido):
            with self.assertRaises(sonda.ErroSonda):
                sonda.transporte_http("GET", "https://exemplo.com/", {}, None)
            with self.assertRaises(sonda.ErroSonda):
                sonda.estado_http("http://management.azure.com/", {})
        self.assertIsNone(sonda.SemRedirecionamento().redirect_request(None, None, 302, "Found", {}, "https://exemplo.com/"))


class TestesDaSonda(BaseSonda):
    def test_validar_roda_local_com_os_quatro_documentos_e_valida_a_configuracao(self):
        codigo, r = self.rodar(["--etapa", "validar"], {})
        self.assertEqual((codigo, r["etapa"], r["veredicto"], r["causa"]), (0, "validar", "aprovado", None))
        dados = r["dados"]
        self.assertEqual(dados["documentos"], {"total": 4, "l100": 3, "l300": 1,
                                               "por_classe": {"compartilhado": 3, "atendimento": 1, "corretor": 0}})
        self.assertEqual(dados["ids"], ["VLAR-CG-1.0", "VLAR-GL-1.0", "VLAR-FAQ-1.0", OPERACIONAL])
        self.assertEqual((dados["modulos"], dados["rede"], dados["operacional"]), ("ok", "bloqueada", OPERACIONAL))
        self.assertEqual(set(dados["configuracao"].values()), {"ausente"})

        codigo, r = self.rodar(["--etapa", "validar", "--exigir-configuracao"])
        self.assertEqual((codigo, set(r["dados"]["configuracao"].values())), (0, {"ok"}))
        codigo, r = self.rodar(["--etapa", "validar", "--exigir-configuracao"], {})
        self.assertEqual((codigo, r["causa"], sorted(r["dados"]["ausentes"])),
                         (1, "configuracao_ausente", sorted(["conta", "busca", "modelos", "assinatura", "grupo", "client_id"])))
        codigo, r = self.rodar(["--etapa", "validar"], {**AMBIENTE, "VARELEIRA_PROBE_CONTA": "Conta_Invalida"})
        self.assertEqual((codigo, r["causa"], r["dados"]["invalidas"]), (1, "configuracao_invalida", ["conta"]))
        self.assertNotIn("Conta_Invalida", json.dumps(r))

        def cli_que_tenta_a_rede(_argv):
            with contextlib.suppress(OSError):  # um tratamento de erro não pode esconder a tentativa
                socket.getaddrinfo("nome.invalido", 443)
            print("Validação concluída.")
            return 0

        with mock.patch.object(sonda.mod.gerenciar_ingestao_l300, "principal", cli_que_tenta_a_rede):
            codigo, r = self.rodar(["--etapa", "validar"], {})
        self.assertEqual((codigo, r["causa"], r["dados"]["tentativas"]), (3, "rede_usada_no_validar", 1))

        # Uma base (a imagem do chat) sem uma peça de que a sonda depende é recusada no build, com o nome da peça e sem traceback.
        with mock.patch.dict(vars(lab_chat)):
            del vars(lab_chat)["classificar_erro"]
            codigo, r = self.rodar(["--etapa", "validar"], {})
        self.assertEqual((codigo, r["causa"], r["dados"]["itens"]), (1, "base_incompativel", ["lab_chat.classificar_erro"]))
        with mock.patch.object(sonda.mod.lab_ingestao_l300, "INDICE_PADRAO", "vareleira-lar-l300-outro"):
            codigo, r = self.rodar(["--etapa", "validar"], {})
        self.assertEqual((codigo, r["causa"], r["dados"]["itens"]), (1, "base_incompativel", ["l300.indice_e_container"]))

    def test_pipeline_chama_a_cli_com_identidade_gerenciada_e_resume_o_indice_sem_vazar(self):
        cli = self.enterContext(self.com_cli({
            "carregar": ("Plano:\n  [criar     ] VLAR-CG-1.0\nConcluído: 4 criado(s), 0 trocado(s), 0 com metadados atualizados, 0 já igual(is).", 0),
            "criar": ("Concluído: 4 criado(s), 0 substituído(s), 0 já igual(is). O indexador não foi executado.", 0),
            "executar": ("Aguardando o fim...\nExecução concluída sem falhas. Confira o índice com --etapa conferir.", 0),
            "conferir": (CONFERENCIA + "Conferência aprovada.", 0),
            "excluir": ("Concluído: 1 blob(s) excluído(s) de forma reversível.", 0),
            "restaurar": ("Concluído: 1 blob(s) restaurado(s).", 0),
        }))
        resultados = {}
        for etapa in ("carregar", "criar", "executar", "conferir", "excluir", "restaurar"):
            codigo, resultados[etapa] = self.rodar(["--etapa", etapa])
            self.assertEqual((codigo, resultados[etapa]["veredicto"], resultados[etapa]["causa"]), (0, "aprovado", None), etapa)
        conta = ["--conta", CONTA, "--container", CONTAINER_L300]
        busca = ["--busca", BUSCA, "--indice", INDICE_L300]
        destino = ["--assinatura", ASSINATURA, "--grupo", GRUPO, "--modelos", MODELOS, "--deployment", "embeddings", "--dimensoes", "1536"]
        self.assertEqual(cli.chamadas, [
            ["--etapa", "carregar", *conta, "--executar", *IDENTIDADE],
            ["--etapa", "criar", *busca, *conta, *destino, "--executar", *IDENTIDADE],
            ["--etapa", "executar", *busca, "--executar", "--aguardar", "900", *IDENTIDADE],
            ["--etapa", "conferir", *busca, *conta, *destino, *IDENTIDADE],
            ["--etapa", "excluir", *conta, "--documento", OPERACIONAL, "--executar", *IDENTIDADE],
            ["--etapa", "restaurar", *conta, "--documento", OPERACIONAL, "--executar", *IDENTIDADE],
        ])
        # Os argumentos montados são aceitos pelo analisador REAL da ferramenta (opções por etapa e combinações incluídas).
        for argv in cli.chamadas:
            real = sonda.mod.gerenciar_ingestao_l300
            args = real.criar_parser().parse_args(argv)
            real.exigir_opcoes(args)
            real.validar_combinacoes(args)
            self.assertTrue(args.identidade_gerenciada and args.executar is (args.etapa != "conferir"))
            self.assertEqual((args.client_id, args.container, args.indice), (CLIENT_ID, CONTAINER_L300, INDICE_L300))
        self.assertEqual(resultados["carregar"]["dados"], {"cli_codigo": 0, "criados": 4, "substituidos": 0, "metadados": 0, "iguais": 0,
                                                           "orfaos": 0})
        self.assertEqual(resultados["criar"]["dados"], {"cli_codigo": 0, "criados": 4, "substituidos": 0, "iguais": 0})
        self.assertEqual((resultados["excluir"]["dados"]["excluidos"], resultados["restaurar"]["dados"]["restaurados"]), (1, 1))
        indice = resultados["executar"]["dados"]["indice"]
        self.assertEqual(indice["por_documento"], {"VLAR-CG-1.0": 3, "VLAR-GL-1.0": 2, "VLAR-FAQ-1.0": 2, OPERACIONAL: 2})
        self.assertEqual(indice["por_classe"], {"compartilhado": 7, "atendimento": 2, "corretor": 0})
        self.assertEqual((indice["trechos"], indice["sem_trechos"], indice["fora_do_manifesto"]), (9, [], 0))
        self.assertEqual(resultados["executar"]["dados"]["indexador"],
                         {"resultado": "success", "estado": "running", "processados": 4, "falhas": 0, "erros": 0, "avisos": 0})
        self.assertEqual((resultados["conferir"]["dados"]["verificacoes_ok"], resultados["conferir"]["dados"]["verificacoes_falha"]), (9, 0))

        # Durante a exclusão, conferir recebe --ausente do documento operacional; a espera do indexador é finita e configurável.
        ambiente = {**AMBIENTE, "VARELEIRA_PROBE_DOCUMENTO_AUSENTE": OPERACIONAL, "VARELEIRA_PROBE_ESPERA_SEGUNDOS": "120"}
        cli.respostas["conferir"] = (CONFERENCIA + AUSENTE_OK + "Conferência aprovada.", 0)
        codigo, r = self.rodar(["--etapa", "conferir"], ambiente)
        self.assertEqual((codigo, cli.chamadas[-1][-5:-3]), (0, ["--ausente", OPERACIONAL]))
        self.assertIn(f"ausente_{OPERACIONAL}", r["dados"]["aprovadas"])
        self.rodar(["--etapa", "executar"], ambiente)
        self.assertEqual(cli.chamadas[-1][cli.chamadas[-1].index("--aguardar") + 1], "120")
        self.assertEqual(sonda._limite_da_etapa("executar", sonda.Configuracao(ambiente)), 120 + sonda.MARGEM_DO_INDEXADOR)
        codigo, r = self.rodar(["--etapa", "conferir"], {**AMBIENTE, "VARELEIRA_PROBE_DOCUMENTO_AUSENTE": "VLAR-CG-1.0"})
        self.assertEqual((codigo, r["causa"], r["dados"]["invalidas"]), (1, "configuracao_invalida", ["documento_ausente"]))

        # resumo: contagens por documento e por classe, zeradas quando o documento não tem trechos, sem nomes de recursos.
        sem_roteiro = ClienteBuscaFalso([t for t in trechos_do_indice() if t["documento_id"] != OPERACIONAL])
        with mock.patch.object(sonda.mod.lab_ingestao_l300, "abrir_cliente", return_value=sem_roteiro):
            codigo, r = self.rodar(["--etapa", "resumo"])
        self.assertEqual((codigo, r["dados"]["indice"]["sem_trechos"], r["dados"]["indice"]["por_documento"][OPERACIONAL]),
                         (0, [OPERACIONAL], 0))
        errado = ClienteBuscaFalso(trechos_do_indice({"documento_id": "OUTRO-DOC", "acesso": "corretor"}))
        with mock.patch.object(sonda.mod.lab_ingestao_l300, "abrir_cliente", return_value=errado):
            codigo, r = self.rodar(["--etapa", "resumo"])
        self.assertEqual((codigo, r["causa"], r["dados"]["problemas"], r["dados"]["indice"]["por_classe"]["corretor"]),
                         (3, "classes_inconsistentes", ["fora_do_manifesto"], 1))

    def test_falhas_terminam_com_codigo_nao_zero_causa_fechada_e_nenhum_vazamento(self):
        indisponivel = ClienteBuscaFalso(erro=li.ErroServicoBusca(403, "Forbidden", f"{BUSCA} negou", "GET", "indexes"))
        casos = [
            ("carregar", 0, "Modo: SIMULAÇÃO (nenhuma alteração será feita)\nSimulação concluída. Para enviar, repita o comando com --executar.",
             3, "saida_inesperada_da_cli", {}),
            ("carregar", 2, "[ERRO] A sua identidade não tem permissão de dados no contêiner 'base-documental-l300'.",
             2, "acesso_ou_servico", {"servico": "blob_sem_permissao"}),
            ("carregar", 0, "Concluído: 4 criado(s), 0 trocado(s), 0 com metadados atualizados, 0 já igual(is).\n[AVISO] 1 blob(s) na pasta "
                            "'vareleira-lar-l300' sem permissão declarada no manifesto: x.md.", 3, "blobs_fora_do_manifesto", {"orfaos": 1}),
            ("criar", 3, "[PARADA] Há objeto(s) do L300 no serviço diferente(s) do definido. Nada foi alterado.",
             3, "parada_por_divergencia", {}),
            ("criar", 4, "[ERRO] Erro inesperado do script (KeyError). Use --detalhes.", 4, "defeito_da_cli", {}),
            ("executar", 2, "[TEMPO ESGOTADO] A execução não terminou em 900 s.", 2, "indexador_nao_terminou",
             {"indice": {"disponivel": False, "causa": "servico_de_busca", "status": 403}}),
            ("conferir", 3, CONFERENCIA.replace("[OK   ] Classe de acesso dos trechos", "[FALHA] Classe de acesso dos trechos")
             + "Conferência reprovada.", 3, "conferencia_reprovada", {"falhas": ["classe_de_acesso"], "verificacoes_ok": 8}),
            ("conferir", 0, "Conferência aprovada.", 3, "conferencia_incompleta", {"verificacoes_ok": 0}),
            ("excluir", 0, "[IGUAL] Nenhum blob ativo para excluir.", 3, "nada_excluido", {}),
            ("restaurar", 0, "[IGUAL] Nenhum blob excluído de forma reversível para restaurar.", 3, "nada_restaurado", {}),
            ("restaurar", 3, "[ERRO] VLAR-OP-ATD-1.0: restaurado, mas o conteúdo restaurado difere do manifesto (o hash não confere).",
             3, "restauracao_divergente", {}),
        ]
        for etapa, saida_da_cli, texto, esperado, causa, extras in casos:
            with self.subTest(etapa=etapa, causa=causa), self.com_cli({etapa: (texto, saida_da_cli)}, indisponivel):
                codigo, r = self.rodar(["--etapa", etapa])
                self.assertEqual((codigo, r["causa"], r["veredicto"]), (esperado, causa, "reprovado" if esperado == 3 else "erro"))
                self.assertEqual(r["dados"]["cli_codigo"], saida_da_cli)
                for chave, valor in extras.items():
                    self.assertEqual(r["dados"][chave], valor)

        # Uso e configuração: código 1, só os nomes das chaves, nunca os valores.
        for argv, ambiente, causa, extras in (
                (["--etapa", "carregar"], {}, "configuracao_ausente", {"ausentes": ["conta", "client_id"]}),
                (["--etapa", "carregar"], {**AMBIENTE, "VARELEIRA_PROBE_CLIENT_ID": "nao-e-guid"}, "configuracao_invalida",
                 {"invalidas": ["client_id"]}),
                (["--etapa", "inexistente"], AMBIENTE, "uso_invalido", {}),
                (["--ajuda"], AMBIENTE, "uso_invalido", {}),
                ([], {}, "etapa_ausente", {}), ([], {"VARELEIRA_PROBE_ETAPA": "xpto"}, "etapa_desconhecida", {}),
                (["--etapa", "validar"], {"VARELEIRA_PROBE_ETAPA": "dns"}, "etapa_conflitante", {})):
            with self.subTest(causa=causa):
                codigo, r = self.rodar(argv, ambiente)
                self.assertEqual((codigo, r["causa"]), (1, causa))
                for chave, valor in extras.items():
                    self.assertEqual(r["dados"][chave], valor)
        self.assertEqual(self.rodar([], {"VARELEIRA_PROBE_ETAPA": "validar"})[0], 0)

        # Exceção inesperada: código 4, só o nome da classe, sem traceback no stderr e sem o texto da exceção.
        def cli_com_defeito(_argv):
            raise RuntimeError(f"falha com {CONTA} e {BUSCA}")

        with mock.patch.object(sonda.mod.gerenciar_ingestao_l300, "principal", cli_com_defeito):
            codigo, r = self.rodar(["--etapa", "validar"], {})
        self.assertEqual((codigo, r["causa"], r["dados"]["excecao"]), (4, "defeito_da_sonda", "RuntimeError"))

        # Barreira final: um valor configurado, um IP, um GUID ou um token curto que chegassem ao resultado bloqueiam a linha inteira.
        token_curto = f"{segmento({'alg': 'none'})}.abc.sig"
        for valor, padrao in ((CONTA, "valor_de_configuracao"), ("10.20.30.4", "ip"), (ASSINATURA, "guid"), (token_curto, "token"),
                              (f"{BUSCA}.search.windows.net", "host")):
            with self.subTest(padrao=padrao):
                linha = sonda.proteger(sonda.Resultado("dns", 0, "aprovado", None, {"x": valor}), (CONTA,))
                bloqueado = json.loads(linha)
                self.assertEqual((bloqueado["causa"], bloqueado["codigo"], bloqueado["veredicto"]), ("saida_bloqueada", 4, "erro"))
                self.assertIn(padrao, bloqueado["dados"]["padroes"])
                self.assertNotIn(valor, linha)
        # Texto fora do vocabulário fechado (um token longo, uma URL, uma frase) nunca passa: vira um marcador inofensivo.
        for valor in (jwt(CLIENT_ID), "https://a/b", "uma frase com espaços"):
            linha = sonda.proteger(sonda.Resultado("dns", 0, "aprovado", None, {"x": valor}), ())
            self.assertEqual(json.loads(linha)["dados"], {"x": "<fora_do_vocabulario>"})
        # Um valor configurado só bloqueia como palavra inteira: "contafake01" dentro de outra palavra não é o valor.
        self.assertEqual(json.loads(sonda.proteger(sonda.Resultado("dns", 0, "aprovado", None, {"x": "meucontafake01x"}), (CONTA,)))["causa"],
                         None)

    def test_a_barreira_por_valor_esta_ligada_ao_ponto_de_entrada_e_o_codigo_de_saida_e_o_da_linha_emitida(self):
        # Um nome de recurso igual a uma palavra do vocabulário da linha (aqui, o veredicto) é um valor da configuração que a linha
        # não pode trazer: Configuracao.privados() alimenta o emissor, a linha vira a do defeito e o código de saída é o dela (4),
        # não o 0 da etapa que foi aprovada.
        codigo, r = self.rodar(["--etapa", "validar"])
        self.assertEqual((codigo, r["veredicto"], r["causa"]), (0, "aprovado", None))
        for variavel, valor in (("CONTA", "aprovado"), ("BUSCA", "aprovado"), ("MODELOS", "aprovado"), ("GRUPO", "APROVADO")):
            with self.subTest(variavel=variavel):
                codigo, r = self.rodar(["--etapa", "validar"], {**AMBIENTE, f"VARELEIRA_PROBE_{variavel}": valor}, proibidos=("aprovado",))
                self.assertEqual((codigo, r["codigo"], r["veredicto"], r["causa"]), (4, 4, "erro", "saida_bloqueada"))
                self.assertEqual(r["dados"], {"padroes": ["valor_de_configuracao"]})
        # Uma etapa que terminou em 3 (reprovada) também sai com 4 se a linha foi trocada: vale o código da linha emitida.
        reprovada = CONFERENCIA.replace("[OK   ] Classe de acesso dos trechos", "[FALHA] Classe de acesso dos trechos") + "Conferência reprovada."
        with self.com_cli({"conferir": (reprovada, 3)}):
            codigo, r = self.rodar(["--etapa", "conferir"])
            self.assertEqual((codigo, r["veredicto"], r["causa"]), (3, "reprovado", "conferencia_reprovada"))
            codigo, r = self.rodar(["--etapa", "conferir"], {**AMBIENTE, "VARELEIRA_PROBE_GRUPO": "reprovado"}, proibidos=("reprovado",))
            self.assertEqual((codigo, r["codigo"], r["causa"]), (4, 4, "saida_bloqueada"))

    def test_a_configuracao_entrega_cada_valor_privado_para_a_barreira(self):
        cfg = sonda.Configuracao({**AMBIENTE, "VARELEIRA_PROBE_URL": URL, "VARELEIRA_PROBE_APP_ID": APP_ID, "VARELEIRA_PROBE_PERFIL": "ambos"})
        self.assertEqual(sorted(cfg.privados()), sorted([CONTA, BUSCA, MODELOS, ASSINATURA, GRUPO, CLIENT_ID, URL, APP_ID]))

    def test_se_a_propria_barreira_falhar_a_linha_e_a_de_ultimo_recurso_e_o_codigo_de_saida_e_4(self):
        def etapa_com_defeito(_cfg, _args):
            return sonda.Resultado("dns", None, "aprovado")  # o código precisa ser um inteiro: sem ele a serialização falha

        with mock.patch.dict(sonda.ETAPAS_DA_SONDA, {"dns": etapa_com_defeito}):
            codigo, r = self.rodar(["--etapa", "dns"])
        self.assertEqual((codigo, r["codigo"], r["veredicto"], r["causa"], r["etapa"]), (4, 4, "erro", "saida_invalida", None))

    def test_o_vigia_encerra_o_processo_com_o_codigo_da_linha_que_emitiu(self):
        # Se uma etapa travar, o vigia emite a linha e encerra com o código DELA (o de tempo esgotado, ou 4 se a barreira a trocou);
        # a etapa que volta depois não emite de novo.
        for grupo, esperado, causa in (("rg-fake-l300", 2, "tempo_da_sonda_esgotado"), ("erro", 4, "saida_bloqueada")):
            liberar, saidas = threading.Event(), []

            def etapa_travada(_cfg, _args, liberar=liberar):
                liberar.wait(5)
                return sonda.Resultado("dns", 0, "aprovado")

            def sair(codigo, liberar=liberar, saidas=saidas):
                saidas.append(codigo)
                liberar.set()

            with self.subTest(grupo=grupo), mock.patch.dict(sonda.ETAPAS_DA_SONDA, {"dns": etapa_travada}), \
                    mock.patch.object(sonda, "_limite_da_etapa", return_value=0.05), mock.patch.object(sonda, "_sair", sair):
                codigo, r = self.rodar(["--etapa", "dns"], {**AMBIENTE, "VARELEIRA_PROBE_GRUPO": grupo})
                self.assertEqual((saidas, codigo, r["codigo"], r["causa"]), ([esperado], esperado, esperado, causa))
                if esperado == 2:
                    self.assertEqual(r["dados"]["limite_s"], 0.05)

    def test_acesso_usa_recuperador_e_servico_reais_com_papeis_estaticos(self):
        servico, config = self.servico_com_indice_falso(), []
        with mock.patch.object(lab_chat, "criar_servico_azure", side_effect=lambda c: config.append(c) or servico):
            codigo, r = self.rodar(["--etapa", "acesso"])
        self.assertEqual((codigo, r["veredicto"], r["causa"]), (0, "aprovado", None))
        self.assertEqual((config[0].client_id, config[0].indice, config[0].exigir_acesso_documental, config[0].modo, config[0].exigir_coordenacao),
                         (CLIENT_ID, INDICE_L300, True, "nuvem", False))
        dados = r["dados"]
        self.assertEqual(dados["recusa"], {"sem_contexto": True, "sem_filtro": True, "filtro_invalido": True, "sem_papel": True,
                                           "chamadas": {"embeddings": 0, "busca": 0, "geracao": 0}})
        atendimento, corretor = dados["perfis"]["atendimento"], dados["perfis"]["corretor"]
        self.assertEqual((atendimento["classes"], corretor["classes"]), (["compartilhado", "atendimento"], ["compartilhado", "corretor"]))
        for perfil in (atendimento, corretor):
            self.assertEqual([(c["modo"], c["consulta"]) for c in perfil["consultas"]],
                             [("texto", "codigo"), ("texto", "pergunta"), ("vetorial", "pergunta"), ("hibrida", "pergunta")])
            self.assertTrue(all(c["fora_do_perfil"] == 0 and c["filtro"] is True for c in perfil["consultas"]))
            self.assertEqual([c["pre_filtro"] for c in perfil["consultas"]], [None, None, True, True])
        self.assertGreaterEqual(atendimento["consultas"][0]["marcador"], 1)  # texto, consulta específica: o marcador é recuperável
        self.assertTrue(all(c["marcador"] == 0 and c["operacional"] == 0 and "atendimento" not in c["classes"]
                            for c in corretor["consultas"]))
        self.assertEqual(dados["geracao"], {
            "executada": True, "perfil": "atendimento", "tipo": "documentada", "situacao": "respondida", "evidencias": 1,
            "fontes_permitidas": True, "citacoes_rastreaveis": True, "cita_o_roteiro": True, "marcador_na_citacao": True,
            "tokens": {"tokens_embeddings": 7, "tokens_entrada": 120, "tokens_saida": 30, "tokens_raciocinio": 0}})
        self.assertEqual(dados["chamadas"], {"embeddings": 5, "busca": 9, "geracao": 1})
        self.assertEqual(len(servico.gerador.pedidos), 1)
        for texto in (MARCADOR, "Resposta sintética", lab_acesso.PAPEL_ATENDIMENTO):
            self.assertNotIn(texto, json.dumps(r))

        # Um índice que ignora o filtro entrega o roteiro ao Corretor: a sonda reprova e NÃO gasta a geração.
        vazando = self.servico_com_indice_falso(vazar=True)
        with mock.patch.object(lab_chat, "criar_servico_azure", return_value=vazando):
            codigo, r = self.rodar(["--etapa", "acesso"])
        self.assertEqual((codigo, r["causa"]), (3, "resultado_fora_do_perfil"))
        self.assertIn("conteudo_interno_no_perfil_corretor", r["dados"]["falhas"])
        self.assertEqual(r["dados"]["geracao"], {"executada": False, "motivo": "invariantes_anteriores_falharam"})
        self.assertEqual(r["dados"]["chamadas"]["geracao"], 0)

        # Um serviço que não recusa a chamada sem contexto é reprovado antes de qualquer busca real, e o modelo nunca é chamado.
        sem_recusa = self.servico_com_indice_falso(exigir_acesso=False)
        with mock.patch.object(lab_chat, "criar_servico_azure", return_value=sem_recusa):
            codigo, r = self.rodar(["--etapa", "acesso"])
        self.assertEqual((codigo, r["causa"], r["dados"]["recusa"]["sem_contexto"], r["dados"]["recusa"]["filtro_invalido"]),
                         (3, "recusa_nao_aplicada", False, True))
        self.assertEqual(sem_recusa.gerador.pedidos, [])

        # A geração pode ser desligada: só as consultas, nenhuma chamada ao modelo.
        com_servico = self.servico_com_indice_falso()
        with mock.patch.object(lab_chat, "criar_servico_azure", return_value=com_servico):
            codigo, r = self.rodar(["--etapa", "acesso"], {**AMBIENTE, "VARELEIRA_PROBE_GERACAO": "nao"})
        self.assertEqual((codigo, r["dados"]["geracao"], r["dados"]["chamadas"]["geracao"]),
                         (0, {"executada": False, "motivo": "desativada"}, 0))

    def servico_com_indice_falso(self, vazar=False, exigir_acesso=True):
        """ServicoRag e Recuperador REAIS sobre o IndiceBusca real, com o cliente de busca, os embeddings e o modelo dublados."""
        trechos = [
            {"id": "cg-0001", "documento_id": "VLAR-CG-1.0", "titulo_documento": "Condições Gerais", "secao": "Cobertura", "clausulas": "2.1",
             "conteudo": "A cobertura básica do Vareleira Lar protege o imóvel contra incêndio e explosão.", "fonte": "x", "versao": "1.0",
             "acesso": "compartilhado"},
            {"id": "gl-0001", "documento_id": "VLAR-GL-1.0", "titulo_documento": "Glossário", "secao": "Termos", "clausulas": "",
             "conteudo": "Franquia é a parte do prejuízo que fica a cargo de quem contrata o seguro.", "fonte": "x", "versao": "1.0",
             "acesso": "compartilhado"},
            {"id": "faq-0001", "documento_id": "VLAR-FAQ-1.0", "titulo_documento": "Perguntas frequentes", "secao": "Geral", "clausulas": "",
             "conteudo": "Perguntas frequentes para o Atendimento e para corretores sobre o seguro residencial.", "fonte": "x",
             "versao": "1.0", "acesso": "compartilhado"},
            {"id": "op-0001", "documento_id": OPERACIONAL, "titulo_documento": "Roteiro interno", "secao": "Código", "clausulas": "",
             "conteudo": f"O código educativo deste roteiro interno de atendimento é {MARCADOR}. Ele existe apenas para os testes.",
             "fonte": "x", "versao": "1.0", "acesso": "atendimento"},
        ]

        class Busca:
            def __init__(self):
                self.pedidos = []

            def search(self, search_text=None, **opcoes):
                self.pedidos.append(opcoes)
                filtro = opcoes.get("filter")
                classes = None if vazar or filtro is None else lab_acesso.classes_do_filtro(filtro)
                candidatos = [dict(t) for t in trechos if classes is None or t["acesso"] in classes]
                termos = [t for t in re.split(r"[\s,?]+", (search_text or "").casefold()) if len(t) > 3]

                def pontos(trecho):
                    return sum(termo in trecho["conteudo"].casefold() for termo in termos)

                if search_text and not opcoes.get("vector_queries"):
                    candidatos = [t for t in candidatos if pontos(t)]
                return sorted(candidatos, key=lambda t: -pontos(t))[:opcoes.get("top", 5)]

        class Embeddings:
            def gerar(self, textos):
                return lab_indexacao.ResultadoEmbeddings([[0.0, 1.0] for _ in textos], "falso", 7 * len(textos))

        class Gerador:
            def __init__(self):
                self.pedidos = []

            def gerar(self, pedido, contrato):
                self.pedidos.append(pedido)
                blocos = re.findall(r'<trecho id="(T\d+)"[^>]*>\n(.*?)\n</trecho>', pedido.entrada, re.S)
                citar = [id_curto for id_curto, texto in blocos if MARCADOR in texto] or [blocos[0][0]]
                return lab_geracao.ResultadoGeracao({"tipo": "documentada", "resposta": "Resposta sintética de teste.",
                                                     "referencias": citar}, 120, 30, 0)

        indice = object.__new__(lab_indexacao.IndiceBusca)
        indice.nome, indice.exigir_filtro, indice._documentos = INDICE_L300, exigir_acesso, Busca()
        recuperador = lab_geracao.Recuperador(indice, Embeddings(), exigir_filtro=exigir_acesso)
        return lab_chat.ServicoRag(recuperador, Gerador(), "hibrida", 5, exigir_acesso)

    def test_etapa_dns_aceita_so_enderecos_rfc1918_e_nao_publica_nomes_nem_ips(self):
        consultados = []

        def resolver(tabela):
            def falso(host, porta, *_, **__):
                consultados.append(host)
                valor = tabela[host.split(".")[0]]
                if isinstance(valor, Exception):
                    raise valor
                return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, porta)) for ip in valor]

            return falso

        privado = ["10.10.0.4"]
        enderecos = ("10.10.0.4", "172.31.255.254", "192.168.1.9", "172.32.0.1", "172.16.0.1", "100.64.0.1")  # nenhum IP pode sair
        with mock.patch.object(socket, "getaddrinfo", resolver({CONTA: privado, BUSCA: ["172.31.255.254"], MODELOS: ["192.168.1.9"]})):
            codigo, r = self.rodar(["--etapa", "dns"], proibidos=enderecos)
        self.assertEqual((codigo, r["dados"]["todos_rfc1918"]), (0, True))
        self.assertEqual(consultados, [f"{CONTA}.blob.core.windows.net", f"{BUSCA}.search.windows.net", f"{MODELOS}.openai.azure.com"])
        self.assertEqual(r["dados"]["dns"]["blob"], {"resolvido": True, "enderecos": 1, "rfc1918": 1, "todos_rfc1918": True})
        misto = {CONTA: privado, BUSCA: ["172.32.0.1", "172.16.0.1"], MODELOS: ["100.64.0.1"]}  # 172.32/12 e 100.64/10 não são RFC 1918
        with mock.patch.object(socket, "getaddrinfo", resolver(misto)):
            codigo, r = self.rodar(["--etapa", "dns"], proibidos=enderecos)
        self.assertEqual((codigo, r["causa"], r["dados"]["rotulos"], r["dados"]["dns"]["busca"]["rfc1918"]),
                         (3, "endereco_fora_de_rfc1918", ["busca", "modelos"], 1))
        with mock.patch.object(socket, "getaddrinfo", resolver({CONTA: privado, BUSCA: privado, MODELOS: socket.gaierror("sem nome")})):
            codigo, r = self.rodar(["--etapa", "dns"], proibidos=enderecos)
        self.assertEqual((codigo, r["causa"], r["dados"]["rotulos"]), (2, "nome_nao_resolvido", ["modelos"]))

    def test_negativas_mi_exigem_403_da_identidade_do_chat_vista_de_dentro_da_rede(self):
        pedidos = []

        def estado(estados):
            def falso(url, cabecalhos):
                pedidos.append((url, dict(cabecalhos)))
                valor = estados["blob" if ".blob." in url else "arm" if "management" in url else "busca"]
                if isinstance(valor, Exception):
                    raise valor
                return valor

            return falso

        credencial = CredencialFalsa()
        with mock.patch.object(sonda, "estado_http", estado({"blob": 403, "busca": 403, "arm": 403})), \
                mock.patch.object(sonda.mod.lab_ingestao_l300, "criar_credencial_gerenciada", return_value=credencial) as criar:
            codigo, r = self.rodar(["--etapa", "negativas-mi"])
        self.assertEqual((codigo, r["dados"]), (0, {"esperado": 403, "estados": {"blob": 403, "busca": 403, "arm": 403},
                                                    "identidade": "confere"}))
        criar.assert_called_once_with(CLIENT_ID)
        self.assertEqual(credencial.escopos, ["https://storage.azure.com/.default", "https://search.azure.com/.default",
                                              "https://management.azure.com/.default"])
        self.assertEqual([url for url, _ in pedidos], [
            f"https://{CONTA}.blob.core.windows.net/base-documental?restype=container&comp=list&maxresults=1",
            f"https://{BUSCA}.search.windows.net/indexes?api-version=2026-04-01",
            f"https://management.azure.com/subscriptions/{ASSINATURA}/resourceGroups/{GRUPO}/providers/Microsoft.Storage/storageAccounts/"
            f"{CONTA}?api-version=2024-01-01"])
        self.assertTrue(all(cabecalhos["Authorization"] == f"Bearer {jwt(CLIENT_ID)}" for _, cabecalhos in pedidos))
        self.assertEqual(pedidos[0][1]["x-ms-version"], "2023-11-03")
        for estados, falsa, esperado, causa, extras in (
                ({"blob": 403, "busca": 200, "arm": 403}, CredencialFalsa(), 3, "permissao_excessiva", {"rotulos": ["busca"]}),
                ({"blob": 403, "busca": 403, "arm": OSError("rede")}, CredencialFalsa(), 2, "rede", {"rotulos": ["arm"]}),
                ({"blob": 403, "busca": 403, "arm": 403}, CredencialFalsa(falha_em=["https://management.azure.com/.default"]), 2,
                 "token_indisponivel", {"rotulos": ["arm"]}),
                ({"blob": 404, "busca": 403, "arm": 403}, CredencialFalsa(), 3, "negativa_inconclusiva", {"rotulos": ["blob"]}),
                ({"blob": 403, "busca": 403, "arm": 403}, CredencialFalsa(appid=sonda.GUID_ZERO), 3,
                 "identidade_diferente", {"identidade": "diferente"})):
            with self.subTest(causa=causa), mock.patch.object(sonda, "estado_http", estado(estados)), \
                    mock.patch.object(sonda.mod.lab_ingestao_l300, "criar_credencial_gerenciada", return_value=falsa):
                codigo, r = self.rodar(["--etapa", "negativas-mi"])
                self.assertEqual((codigo, r["causa"]), (esperado, causa))
                for chave, valor in extras.items():
                    self.assertEqual(r["dados"][chave], valor)
        codigo, r = self.rodar(["--etapa", "negativas-mi"], {k: v for k, v in AMBIENTE.items() if k != "VARELEIRA_PROBE_GRUPO"})
        self.assertEqual((codigo, r["causa"], r["dados"]["ausentes"]), (1, "configuracao_ausente", ["grupo"]))

    def test_http_interno_confere_saude_negativas_e_uma_pergunta_autenticada_por_perfil(self):
        enviados = []

        def http(autenticado):
            def falso(metodo, url, cabecalhos, corpo_enviado):
                enviados.append((metodo, url.removeprefix(URL), dict(cabecalhos), corpo_enviado))
                if "Authorization" in cabecalhos:
                    return autenticado
                return {"/healthz": (200, b"ok"), "/readyz": (200, b"ok")}.get(url.removeprefix(URL), (401, b""))

            return falso

        ambiente = {**AMBIENTE, "VARELEIRA_PROBE_URL": URL, "VARELEIRA_PROBE_APP_ID": APP_ID}
        credencial = CredencialFalsa()
        for perfil, autenticado, esperado, causa in (
                ("atendimento", (200, resposta_do_chat()), 0, None),
                ("corretor", (200, resposta_do_chat()), 3, "conteudo_interno_no_perfil_corretor"),
                ("sem-acesso", (403, b'{"erro": "nao_autorizado", "mensagem": "x"}'), 0, None)):
            with self.subTest(perfil=perfil, causa=causa), mock.patch.object(sonda, "transporte_http", http(autenticado)), \
                    mock.patch.object(sonda.mod.lab_ingestao_l300, "criar_credencial_gerenciada", return_value=credencial):
                enviados.clear()
                codigo, r = self.rodar(["--etapa", "http-interno"], {**ambiente, "VARELEIRA_PROBE_PERFIL": perfil})
                self.assertEqual((codigo, r["causa"]), (esperado, causa))
                self.assertEqual(r["dados"]["estados"], {"healthz": 200, "readyz": 200, "anonimo": 401, "principal_forjado": 401,
                                                         "autenticado": autenticado[0]})
                self.assertEqual([(m, u, "Authorization" in c, "X-MS-CLIENT-PRINCIPAL" in c) for m, u, c, _ in enviados],
                                 [("GET", "/healthz", False, False), ("GET", "/readyz", False, False),
                                  ("POST", "/api/perguntar", False, False), ("POST", "/api/perguntar", False, True),
                                  ("POST", "/api/perguntar", True, False)])
                forjado = json.loads(base64.b64decode(enviados[3][2]["X-MS-CLIENT-PRINCIPAL"]))
                self.assertIn({"typ": "roles", "val": "Vareleira.Atendimento"}, forjado["claims"])
                self.assertEqual(json.loads(enviados[-1][3]), {"pergunta": sonda.PERGUNTA_DO_CHAT})
                self.assertEqual(enviados[-1][2]["Authorization"], f"Bearer {jwt(CLIENT_ID)}")
        self.assertEqual(credencial.escopos[-1], f"api://{APP_ID}/.default")
        self.assertNotIn(MARCADOR, sonda.PERGUNTA_DO_CHAT)
        for estados_anonimos, causa in (({("POST", False): (200, b"")}, "anonimo_nao_negado"),
                                        ({("POST", True): (200, b"")}, "principal_forjado_nao_negado")):
            def aberto(metodo, url, cabecalhos, corpo_enviado, trocas=estados_anonimos):
                if "Authorization" in cabecalhos:
                    return 200, resposta_do_chat()
                return trocas.get((metodo, "X-MS-CLIENT-PRINCIPAL" in cabecalhos), (401, b"") if metodo == "POST" else (200, b"ok"))

            with self.subTest(causa=causa), mock.patch.object(sonda, "transporte_http", aberto), \
                    mock.patch.object(sonda.mod.lab_ingestao_l300, "criar_credencial_gerenciada", return_value=credencial):
                codigo, r = self.rodar(["--etapa", "http-interno"], ambiente)
                self.assertEqual((codigo, r["causa"]), (3, causa))
        for invalida in ("http://chat.x.regiao-x.azurecontainerapps.io", "https://exemplo.com", f"{URL}/api", f"{URL}:8443"):
            codigo, r = self.rodar(["--etapa", "http-interno"], {**ambiente, "VARELEIRA_PROBE_URL": invalida})
            self.assertEqual((codigo, r["dados"]["invalidas"]), (1, ["url"]))


if __name__ == "__main__":
    unittest.main()
