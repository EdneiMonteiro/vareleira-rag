"""Testes da ingestão do L300 (sem Azure): manifesto de permissões, cópias classificadas, exclusão reversível e pipeline com acesso.

A validação do manifesto roda só no computador, com os arquivos reais, e a rede é bloqueada nesses testes. O Blob Storage é um dublê
em memória (com ETag, exclusão reversível e restauração) e o serviço de busca é o dublê HTTP do teste do L200, que confere cabeçalhos,
condições de ETag e rotas: cada pedido fica registrado para provar o que a ferramenta leu e o que alterou.
"""

import contextlib
import copy
import io
import json
import shutil
import socket
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import support  # noqa: F401  (configura o caminho dos scripts)
import gerenciar_ingestao_l300 as cli
import lab_acesso as la
import lab_comum
import lab_indexacao
import lab_ingestao as li
import lab_ingestao_l300 as l300
from azure.core import MatchConditions
from azure.core.exceptions import ResourceModifiedError
from support import RAIZ, ClienteBlobFalso, ContainerFalso, erro_404
from test_ingestao import (ASSINATURA, BUSCA, CONTA, GRUPO, MODELOS, TOKEN, CredencialFalsa, RelogioFalso, ServicoBuscaFalso)

INDICE = "vareleira-lar-l300"
FONTE, SKILLSET, INDEXADOR = f"{INDICE}-fonte", f"{INDICE}-skillset", f"{INDICE}-indexador"
OBJETOS = [(li.INDICE, INDICE), (li.FONTE, FONTE), (li.SKILLSET, SKILLSET), (li.INDEXADOR, INDEXADOR)]
CRIAR = ["--busca", BUSCA, "--assinatura", ASSINATURA, "--grupo", GRUPO, "--conta", CONTA, "--modelos", MODELOS]
OPERACIONAL, COMPARTILHADOS = "VLAR-OP-ATD-1.0", ("VLAR-CG-1.0", "VLAR-GL-1.0", "VLAR-FAQ-1.0")
MARCADOR_DO_ROTEIRO = "ATD-L300-ROTEIRO-7Q4K"
BLOB_OPERACIONAL = "vareleira-lar-l300/roteiro-interno-atendimento-v1.0.md"
ARQUIVO_OPERACIONAL = "dados/l300/documentos/roteiro-interno-atendimento-v1.0.md"


def copiar_raiz():
    """Cópia do que o L300 lê (inventário e documentos do L100, manifesto e documentos do L300), sem os conjuntos de avaliação."""
    pasta = tempfile.TemporaryDirectory()
    raiz = Path(pasta.name)
    (raiz / "dados" / "l100").mkdir(parents=True)
    shutil.copy2(RAIZ / "dados" / "l100" / "inventario.json", raiz / "dados" / "l100" / "inventario.json")
    shutil.copytree(RAIZ / "dados" / "l100" / "documentos", raiz / "dados" / "l100" / "documentos")
    shutil.copytree(RAIZ / "dados" / "l300", raiz / "dados" / "l300")
    return pasta, raiz


class ClienteBlobL300(ClienteBlobFalso):
    def _conferir_etag(self, atual, opcoes):
        if opcoes.get("etag") and atual.etag != opcoes["etag"]:
            raise ResourceModifiedError("o blob mudou")

    def set_blob_metadata(self, metadata, **opcoes):
        atual = self._blob()
        self._conferir_etag(atual, opcoes)
        self.container.contador += 1
        atual.etag, atual.metadata = f"etag-{self.container.contador}", dict(metadata)
        self.container.metadados.append(self.nome)
        self.container.opcoes_de_metadados.append(dict(opcoes))

    def delete_blob(self, delete_snapshots=None, **opcoes):
        atual = self._blob()
        self.container.antes_de_excluir(self.nome)
        self._conferir_etag(atual, opcoes)
        self.container.deletados[self.nome] = self.container.blobs.pop(self.nome)
        self.container.exclusoes.append(self.nome)

    def undelete_blob(self):
        if self.nome not in self.container.deletados:
            raise erro_404("BlobNotFound")
        self.container.blobs[self.nome] = self.container.deletados.pop(self.nome)
        self.container.restauracoes.append(self.nome)


class ContainerL300(ContainerFalso):
    """Contêiner em memória com exclusão reversível: o blob excluído sai da listagem comum e volta com `undelete_blob`."""

    def __init__(self):
        super().__init__()
        self.deletados, self.exclusoes, self.restauracoes, self.metadados = {}, [], [], []
        self.opcoes_de_metadados = []  # as condições (etag, match_condition) de cada set_blob_metadata
        self.antes_de_excluir = lambda nome: None

    def get_blob_client(self, nome):
        return ClienteBlobL300(self, nome)

    def list_blobs(self, name_starts_with=None, include=None):
        itens = [(nome, blob, False) for nome, blob in self.blobs.items()]
        if include and "deleted" in include:
            itens += [(nome, blob, True) for nome, blob in self.deletados.items()]
        for nome, blob, excluido in itens:
            if name_starts_with is None or nome.startswith(name_starts_with):
                yield SimpleNamespace(name=nome, size=len(blob.dados), metadata=blob.metadata, deleted=excluido)


class BaseL300(unittest.TestCase):
    def setUp(self):
        self.pasta, self.raiz = copiar_raiz()
        self.addCleanup(self.pasta.cleanup)
        self.manifesto = self.raiz / "dados" / "l300" / "permissoes-documentais.json"
        self.servico, self.credencial, self.relogio, self.container = ServicoBuscaFalso(), CredencialFalsa(), RelogioFalso(), ContainerL300()
        self.abertos = []  # (conta, contêiner, credencial) de cada contêiner aberto
        self.addCleanup(lambda: self.assertEqual(self.servico.violacoes, []))
        for alvo, nome, valor in ((l300, "RAIZ", self.raiz), (l300, "MANIFESTO_PADRAO", self.manifesto), (li, "_relogio", self.relogio.agora),
                                  (li, "_dormir", self.relogio.dormir)):
            patch = mock.patch.object(alvo, nome, valor)
            patch.start()
            self.addCleanup(patch.stop)
        for nome, falso in (("abrir_cliente", self._abrir_cliente), ("abrir_container", self._abrir_container)):
            patch = mock.patch.object(l300, nome, side_effect=falso)
            patch.start()
            self.addCleanup(patch.stop)

    def _abrir_cliente(self, busca, tenant_id=None, versao_api=li.VERSAO_API, credencial=None):
        self.servico.versao_api = versao_api
        return li.ClienteBusca(busca, tenant_id, credencial=credencial or self.credencial, transporte=self.servico, versao_api=versao_api)

    def _abrir_container(self, conta, container, tenant_id=None, credencial=None):
        self.abertos.append((conta, container, credencial))
        return self.container

    def rodar(self, etapa, *opcoes):
        saida = io.StringIO()
        with contextlib.redirect_stdout(saida), contextlib.redirect_stderr(saida):
            try:
                codigo = cli.principal(["--etapa", etapa, "--manifesto", str(self.manifesto), *opcoes])
            except SystemExit as erro:  # erro de argumentos do argparse
                codigo = erro.code
        self.assertNotIn(TOKEN, saida.getvalue(), "o token nunca pode aparecer na saída")
        return codigo, saida.getvalue()

    def ler_manifesto(self):
        return json.loads(self.manifesto.read_text(encoding="utf-8"))

    def gravar_manifesto(self, bruto):
        self.manifesto.write_text(json.dumps(bruto, ensure_ascii=False, indent=2), encoding="utf-8")

    def alterar_manifesto(self, funcao):
        bruto = self.ler_manifesto()
        funcao(bruto)
        self.gravar_manifesto(bruto)

    def documento(self, bruto, identificador=OPERACIONAL):
        return next(item for item in bruto["documentos"] if item["id"] == identificador)

    def carregar_blobs(self):
        codigo, saida = self.rodar("carregar", "--conta", CONTA, "--executar")
        self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)

    def criar_objetos(self, *opcoes):
        codigo, saida = self.rodar("criar", *CRIAR, "--executar", *opcoes)
        self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)
        self.servico.requisicoes.clear()

    def escritas(self):
        return [(r.metodo, r.caminho) for r in self.servico.escritas()]

    def parametros(self, **ajustes):
        args = SimpleNamespace(indice=INDICE, assinatura=ASSINATURA, grupo=GRUPO, conta=CONTA, container=l300.CONTAINER_PADRAO, modelos=MODELOS,
                               deployment="embeddings", modelo_embeddings="text-embedding-3-small", dimensoes=1536, tamanho_maximo=1200,
                               sobreposicao=100, privado=None, intervalo=None, **ajustes)
        return l300.parametros_do_pipeline(l300.carregar_manifesto(self.manifesto, self.raiz), args)


def sem_rede():
    """Qualquer tentativa de conexão ou de abrir o Azure durante a validação local é um defeito."""
    pilha = contextlib.ExitStack()
    pilha.enter_context(mock.patch.object(socket.socket, "connect", side_effect=AssertionError("conexão de rede na validação local")))
    for nome in ("abrir_cliente", "abrir_container", "criar_credencial_gerenciada"):
        pilha.enter_context(mock.patch.object(l300, nome, side_effect=AssertionError(f"{nome} chamado na validação local")))
    return pilha


# --------------------------------------------------------------------------------------
# Manifesto: validação local, sem rede
# --------------------------------------------------------------------------------------

class ManifestoTests(BaseL300):
    def test_o_manifesto_publicado_confere_com_os_arquivos_e_com_o_inventario_do_l100(self):
        manifesto = l300.carregar_e_validar(RAIZ / "dados" / "l300" / "permissoes-documentais.json", RAIZ)
        self.assertEqual([documento.id for documento in manifesto.documentos], [*COMPARTILHADOS, OPERACIONAL])
        self.assertEqual({documento.id: documento.acesso for documento in manifesto.documentos},
                         {**dict.fromkeys(COMPARTILHADOS, la.CLASSE_COMPARTILHADO), OPERACIONAL: la.CLASSE_ATENDIMENTO})
        l100 = {documento.id: documento for documento in lab_comum.carregar_e_validar().documentos}
        for documento in manifesto.documentos[:3]:
            self.assertEqual((documento.origem, documento.sha256, documento.tamanho_bytes, documento.arquivo),
                             (l300.ORIGEM_L100, l100[documento.id].sha256, l100[documento.id].tamanho_bytes, l100[documento.id].arquivo))
        self.assertTrue(all(documento.blob.startswith("vareleira-lar-l300/") for documento in manifesto.documentos))
        self.assertTrue(all(documento.metadados_blob["acesso"] == documento.acesso and documento.metadados_blob["sha256"] == documento.sha256
                            for documento in manifesto.documentos))
        # contêiner, pasta e índice do L300 são outros: nada é compartilhado com o L100 nem com o L200
        self.assertNotEqual((l300.CONTAINER_PADRAO, l300.PREFIXO_PADRAO, l300.INDICE_PADRAO),
                            (lab_comum.CONTAINER_PADRAO, "vareleira-lar", lab_indexacao.INDICE_PADRAO))
        self.assertFalse(l300.CONTAINER_PADRAO.startswith(lab_comum.CONTAINER_PADRAO + "/"))
        operacional = (RAIZ / ARQUIVO_OPERACIONAL).read_text(encoding="utf-8")
        self.assertEqual(operacional.count(MARCADOR_DO_ROTEIRO), 1, "um marcador único, só no material operacional")
        for documento in l100.values():
            self.assertNotIn(MARCADOR_DO_ROTEIRO, documento.arquivo.read_text(encoding="utf-8"))

    def test_validar_roda_sem_rede_com_os_arquivos_reais_e_a_saida_e_objetiva(self):
        saida = io.StringIO()
        with sem_rede(), contextlib.redirect_stdout(saida), contextlib.redirect_stderr(saida):
            with mock.patch.object(l300, "RAIZ", RAIZ), mock.patch.object(l300, "MANIFESTO_PADRAO", RAIZ / "dados" / "l300" / "permissoes-documentais.json"):
                codigo = cli.principal(["--etapa", "validar"])
        texto = saida.getvalue()
        self.assertEqual(codigo, lab_comum.CODIGO_OK, texto)
        for esperado in (*COMPARTILHADOS, OPERACIONAL, "compartilhado", "atendimento", "Nenhuma chamada de rede foi feita",
                         la.PAPEL_ATENDIMENTO, la.PAPEL_CORRETOR, "base-documental-l300", "vareleira-lar-l300"):
            self.assertIn(esperado, texto)
        manifesto = l300.carregar_manifesto(RAIZ / "dados" / "l300" / "permissoes-documentais.json", RAIZ)
        self.assertEqual("revisão de conteúdo pendente" in texto,
                         any(documento.revisao_status != "aprovada" for documento in manifesto.documentos))

    def test_manifesto_invalido_falha_fechada_antes_de_qualquer_acesso(self):
        def op(bruto):
            return self.documento(bruto)

        casos = {
            "sem classe de acesso": (lambda b: op(b).pop("acesso"), "'acesso' ausente"),
            "classe vazia": (lambda b: op(b).update(acesso=""), "'acesso' ausente"),
            "classe nula": (lambda b: op(b).update(acesso=None), "'acesso' ausente"),
            "classe desconhecida": (lambda b: op(b).update(acesso="publico"), "fora da lista de classes"),
            "classe com outra caixa": (lambda b: op(b).update(acesso="Atendimento"), "fora da lista de classes"),
            "classe em lista": (lambda b: op(b).update(acesso=["atendimento"]), "fora da lista de classes"),
            "lista de classes sem corretor": (lambda b: b.update(classes=["compartilhado", "atendimento"]), "classes"),
            "lista de classes com extra": (lambda b: b["classes"].append("gerencia"), "classes"),
            "origem desconhecida": (lambda b: op(b).update(origem="l200"), "'origem'"),
            "blob no prefixo do L100": (lambda b: op(b).update(blob="vareleira-lar/roteiro.md"), "'blob'"),
            "blob com subida de pasta": (lambda b: op(b).update(blob="vareleira-lar-l300/../x.md"), "'blob'"),
            "arquivo fora de dados": (lambda b: op(b).update(arquivo="../README.md"), "'arquivo'"),
            "arquivo na pasta do L200": (lambda b: op(b).update(arquivo="dados/l200/documentos/x.md"), "'arquivo'"),
            "origem diferente da pasta": (lambda b: op(b).update(origem="l100"), "precisa estar em dados/l100"),
            "não declarado sintético": (lambda b: b.update(sintetico=False), "sintetico"),
            "sem documentos": (lambda b: b.update(documentos=[]), "'documentos'"),
            "documento do L100 com hash diferente": (lambda b: b["documentos"][0].update(sha256="0" * 64), "difere do inventário do L100"),
            "documento do L100 que o inventário não tem": (lambda b: b["documentos"][0].update(id="VLAR-XX-9.9"), "não existe no inventário do L100"),
            "id repetido": (lambda b: op(b).update(id="VLAR-CG-1.0"), "repetido"),
        }
        for rotulo, (alterar, trecho_da_mensagem) in casos.items():
            with self.subTest(rotulo=rotulo):
                self.gravar_manifesto(json.loads((RAIZ / "dados" / "l300" / "permissoes-documentais.json").read_text(encoding="utf-8")))
                self.alterar_manifesto(alterar)
                with sem_rede():
                    codigo, saida = self.rodar("validar")
                    codigo_carga, _ = self.rodar("carregar", "--conta", CONTA, "--executar")
                self.assertEqual((codigo, codigo_carga), (lab_comum.CODIGO_USO, lab_comum.CODIGO_USO), saida)
                self.assertIn(trecho_da_mensagem, saida)
                self.assertIn("nada foi enviado", saida)
        self.assertEqual(self.abertos, [])

    def test_arquivo_que_nao_confere_ou_sem_permissao_declarada_e_negado(self):
        pasta = self.raiz / "dados" / "l300" / "documentos"
        original = (self.raiz / ARQUIVO_OPERACIONAL).read_bytes()
        casos = {
            "conteúdo alterado": (lambda: (self.raiz / ARQUIVO_OPERACIONAL).write_bytes(original + b"\nLinha nova.\n"), "hash não confere"),
            "arquivo sem permissão no manifesto": (lambda: (pasta / "rascunho.md").write_text("# Rascunho\n", encoding="utf-8"),
                                                    "sem permissão declarada: rascunho.md"),
            "arquivo ausente": (lambda: (self.raiz / ARQUIVO_OPERACIONAL).unlink(), "arquivo não encontrado"),
            "sem declaração de sintético": (lambda: (self.raiz / ARQUIVO_OPERACIONAL).write_bytes(original.replace(b"Documento sint\xc3\xa9tico", b"Documento")),
                                            "precisa se declarar sintético"),
        }
        for rotulo, (preparar, trecho_da_mensagem) in casos.items():
            with self.subTest(rotulo=rotulo):
                shutil.rmtree(self.raiz / "dados" / "l300")
                shutil.copytree(RAIZ / "dados" / "l300", self.raiz / "dados" / "l300")
                preparar()
                with sem_rede():
                    codigo, saida = self.rodar("validar")
                self.assertEqual(codigo, lab_comum.CODIGO_USO, saida)
                self.assertIn(trecho_da_mensagem, saida)

    def test_final_de_linha_do_windows_nao_altera_o_hash_e_ignora_arquivos_do_sistema(self):
        arquivo = self.raiz / ARQUIVO_OPERACIONAL
        arquivo.write_bytes(arquivo.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
        (arquivo.parent / "Thumbs.db").write_bytes(b"\x00")
        with sem_rede():
            codigo, saida = self.rodar("validar")
        self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)


# --------------------------------------------------------------------------------------
# Definições do pipeline
# --------------------------------------------------------------------------------------

class DefinicoesTests(BaseL300):
    def test_dados_privados_do_l300_campo_de_acesso_marcador_proprio_e_indexador_desabilitado_sem_agenda(self):
        p = self.parametros()
        li.validar_parametros(p)
        indice, fonte, skillset, indexador = (definicao for _, _, definicao in li.definicoes_em_ordem(p))
        campos = {campo["name"]: campo for campo in indice["fields"]}
        self.assertEqual({chave: campos["acesso"][chave] for chave in ("type", "filterable", "searchable", "retrievable", "key", "sortable", "facetable")},
                         {"type": "Edm.String", "filterable": True, "searchable": False, "retrievable": True, "key": False,
                          "sortable": False, "facetable": False})
        self.assertTrue(set(li.CAMPOS_COMPATIVEIS) <= set(campos), "o recuperador do L100 continua compatível")
        mapeamentos = {m["name"]: m["source"] for m in skillset["indexProjections"]["selectors"][0]["mappings"]}
        self.assertEqual(mapeamentos["acesso"], "/document/acesso", "a classe vem do metadado do blob, sem coleção nem delimitador")
        self.assertEqual(fonte["container"], {"name": "base-documental-l300", "query": "vareleira-lar-l300"})
        self.assertEqual(fonte["dataDeletionDetectionPolicy"], {"@odata.type": li.POLITICA_DE_EXCLUSAO})
        self.assertIs(indexador["disabled"], True)
        self.assertEqual(indexador["parameters"]["configuration"]["executionEnvironment"], "private")
        self.assertNotIn("schedule", indexador, "sem agenda inicial automática")
        self.assertEqual([definicao["name"] for definicao in (indice, fonte, skillset, indexador)], [nome for _, nome in OBJETOS])
        for definicao in (indice, fonte, skillset, indexador):
            self.assertIn("vareleira-rag:l300", definicao["description"])
            self.assertNotIn("l200", definicao["description"].lower())

    def test_o_sdk_estavel_reconhece_as_definicoes_do_l300_com_agenda_opcional(self):
        from azure.search.documents.indexes import models as sdk

        p = self.parametros()
        campos = {campo.name: campo for campo in sdk.SearchIndex(li.definicao_do_indice(p)).fields}
        self.assertEqual((campos["acesso"].filterable, campos["acesso"].searchable, campos["acesso"].type.value), (True, False, "Edm.String"))
        self.assertIsNone(sdk.SearchIndexer(li.definicao_do_indexador(p)).schedule)
        com_agenda = self.parametros()
        com_agenda = li.Parametros(**{**com_agenda.__dict__, "intervalo": l300.intervalo_iso(120)})
        indexador = sdk.SearchIndexer(li.definicao_do_indexador(com_agenda))
        self.assertEqual((indexador.is_disabled, indexador.schedule.interval), (True, timedelta(hours=2)))
        self.assertEqual(indexador.parameters.configuration["executionEnvironment"], "private")

    def test_ambiente_privado_e_o_padrao_e_a_agenda_so_existe_quando_pedida(self):
        self.assertEqual(self.parametros().privado, True)
        for privado, esperado in ((True, "private"), (False, "standard")):
            p = li.Parametros(**{**self.parametros().__dict__, "privado": privado})
            self.assertEqual(li.definicao_do_indexador(p)["parameters"]["configuration"]["executionEnvironment"], esperado)
        self.assertEqual([l300.intervalo_iso(minutos) for minutos in (None, 5, 30, 60, 90, 120, 1440)],
                         [None, "PT5M", "PT30M", "PT1H", "PT90M", "PT2H", "P1D"])
        for invalido in ("4", "1441", "0", "-5", "umahora", ""):
            with self.assertRaises(Exception, msg=invalido):
                l300.validar_intervalo(invalido)

    def test_nomes_e_conteiner_do_l100_e_do_l200_sao_recusados(self):
        self.assertEqual(l300.nomes_dos_objetos(f"{INDICE}-teste").indexador, f"{INDICE}-teste-indexador")
        for nome in ("vareleira-lar-l100", "vareleira-lar-l200", "vareleira-lar-l200-teste", "vareleira-lar-l3000", ""):
            with self.assertRaises(lab_comum.ErroLab, msg=nome):
                l300.nomes_dos_objetos(nome)
        for container in ("base-documental", "base-documental-l200", "outro-base-documental-l300", "base-documental-l300x"):
            with self.assertRaises(Exception, msg=container):
                l300.validar_container_l300(container)

    def test_as_definicoes_do_l200_seguem_como_eram(self):
        p = li.Parametros(li.nomes_dos_objetos("vareleira-lar-l200"), ASSINATURA, GRUPO, CONTA, "base-documental", "vareleira-lar", MODELOS,
                          "embeddings", "text-embedding-3-small", 1536, 1200, 100)
        indice, indexador = li.definicao_do_indice(p), li.definicao_do_indexador(p)
        self.assertNotIn("acesso", {campo["name"] for campo in indice["fields"]})
        self.assertEqual(indexador["parameters"]["configuration"], {"dataToExtract": "contentAndMetadata", "parsingMode": "text",
                                                                    "indexedFileNameExtensions": ".md"})
        self.assertTrue(indice["description"].endswith("[vareleira-rag:l200]") and "(L200)" in indice["description"])


# --------------------------------------------------------------------------------------
# Objetos de busca (índice, data source, skillset, indexador)
# --------------------------------------------------------------------------------------

def trechos_do_indice(manifesto):
    """Trechos como o indexador os gravaria no L300: metadados do blob, endereço do blob em `fonte` e a classe de acesso."""
    trechos = []
    for documento in manifesto.documentos:
        for ordem in range(2):
            trechos.append({
                "id": f"{documento.id.lower()}_pages_{ordem}", "id_pai": documento.id.lower(), "documento_id": documento.id,
                "titulo_documento": documento.blob.rsplit("/", 1)[-1], "produto": documento.produto, "versao": documento.versao,
                "secao": None, "clausulas": None, "conteudo": f"Trecho {ordem} do documento {documento.id}.",
                "fonte": f"https://{CONTA}.blob.core.windows.net/base-documental-l300/{documento.blob}",
                "sha256": documento.sha256, "sintetico": "true", "acesso": documento.acesso})
    return trechos


class PipelineTests(BaseL300):
    def test_criar_simula_por_padrao_e_so_le(self):
        codigo, saida = self.rodar("criar", *CRIAR)
        self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)
        self.assertEqual(self.escritas(), [])
        self.assertEqual(saida.count("[criar     ]"), 4)
        for esperado in ("SIMULAÇÃO", "DESABILITADO", "executionEnvironment=private", "'acesso'", "sem agenda", "shared private links"):
            self.assertIn(esperado, saida)

    def test_criar_executar_cria_so_os_quatro_objetos_do_l300_e_uma_segunda_vez_nao_altera_nada(self):
        codigo, saida = self.rodar("criar", *CRIAR, "--executar")
        self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)
        self.assertEqual(sorted(chave[1] for chave in self.servico.objetos), sorted(nome for _, nome in OBJETOS))
        self.assertEqual([metodo for metodo, _ in self.escritas()], ["PUT"] * 4)
        for requisicao in self.servico.requisicoes:
            if requisicao.metodo == "PUT":
                self.assertEqual(requisicao.cabecalhos["If-None-Match"], "*", "criação nunca sobrescreve")
        indexador = self.servico.objetos[(li.INDEXADOR, INDEXADOR)]
        self.assertTrue(indexador["disabled"])
        self.assertEqual(indexador["parameters"]["configuration"]["executionEnvironment"], "private")
        self.assertEqual(self.servico.execucoes, [], "criar não executa o indexador")
        self.servico.requisicoes.clear()
        codigo, saida = self.rodar("criar", *CRIAR, "--executar")
        self.assertEqual((codigo, self.escritas()), (lab_comum.CODIGO_OK, []), saida)
        self.assertIn("já estão como o plano pede", saida)

    def test_objeto_de_outro_dono_nunca_e_substituido_nem_com_substituir_e_o_etag_e_preservado(self):
        def alheio(marcador):
            """O índice do L300 como seria, mas criado por outra pessoa: a descrição não traz o marcador do L300."""
            return {**li.definicao_do_indice(self.parametros()), "description": f"Criado por outra pessoa {marcador}".strip()}

        for rotulo, definicao in {"sem marcador": alheio(""), "com o marcador do L200": alheio("[vareleira-rag:l200]")}.items():
            with self.subTest(rotulo=rotulo):
                self.servico.objetos.clear()
                self.servico.guardar(li.INDICE, INDICE, definicao)
                etag = self.servico.objetos[(li.INDICE, INDICE)]["@odata.etag"]
                self.servico.requisicoes.clear()
                for opcoes in ((), ("--executar",), ("--executar", "--substituir")):
                    codigo, saida = self.rodar("criar", *CRIAR, *opcoes)
                    self.assertEqual(codigo, lab_comum.CODIGO_DIVERGENCIA, saida)
                    self.assertIn("outro dono", saida)
                    self.assertIn("nunca são substituídos, nem com --substituir", saida)
                self.assertEqual(self.escritas(), [], "nada foi gravado nem apagado")
                self.assertEqual(self.servico.objetos[(li.INDICE, INDICE)]["@odata.etag"], etag)

    def test_objeto_do_l300_diferente_so_e_substituido_com_substituir_e_com_o_etag_planejado(self):
        self.criar_objetos()
        self.servico.objetos[(li.SKILLSET, SKILLSET)]["skills"][0]["maximumPageLength"] = 800
        etag = self.servico.objetos[(li.SKILLSET, SKILLSET)]["@odata.etag"]
        for opcoes in ((), ("--executar",)):
            codigo, saida = self.rodar("criar", *CRIAR, *opcoes)
            self.assertEqual(codigo, lab_comum.CODIGO_DIVERGENCIA, saida)
            self.assertIn("maximumPageLength", saida)
        self.assertEqual(self.escritas(), [])
        codigo, saida = self.rodar("criar", *CRIAR, "--executar", "--substituir")
        self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)
        (escrita,) = [r for r in self.servico.requisicoes if r.metodo == "PUT"]
        self.assertEqual((escrita.cabecalhos["If-Match"], escrita.caminho), (etag, f"skillsets('{SKILLSET}')"))
        self.assertIn("--reiniciar", saida)

    def test_executar_habilita_o_indexador_uma_vez_e_acompanha_a_execucao(self):
        self.criar_objetos()
        codigo, saida = self.rodar("executar", "--busca", BUSCA)
        self.assertEqual((codigo, self.escritas()), (lab_comum.CODIGO_OK, []), saida)
        self.assertIn("SIMULAÇÃO", saida)
        self.assertIn("private", saida)
        self.servico.polls_em_andamento = 1
        codigo, saida = self.rodar("executar", "--busca", BUSCA, "--executar", "--aguardar")
        self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)
        self.assertFalse(self.servico.objetos[(li.INDEXADOR, INDEXADOR)]["disabled"])
        self.assertEqual(self.servico.execucoes, [INDEXADOR])
        self.assertIn("Execução concluída sem falhas", saida)

    def test_remover_apaga_so_os_quatro_objetos_do_l300_e_preserva_o_l100_e_o_l200(self):
        self.criar_objetos()
        for tipo, nome in (("indexes", "vareleira-lar-l200"), ("indexes", "vareleira-lar-l100"), ("datasources", "vareleira-lar-l200-fonte"),
                           ("indexers", "vareleira-lar-l200-indexador")):
            self.servico.guardar(tipo, nome, {"name": nome, "description": "Laboratorio (L200) [vareleira-rag:l200]"})
        codigo, saida = self.rodar("remover", "--busca", BUSCA)
        self.assertEqual((codigo, self.escritas()), (lab_comum.CODIGO_OK, []), saida)
        codigo, saida = self.rodar("remover", "--busca", BUSCA, "--executar")
        self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)
        self.assertEqual(sorted(caminho for metodo, caminho in self.escritas() if metodo == "DELETE"),
                         sorted(f"{tipo}('{nome}')" for tipo, nome in OBJETOS))
        self.assertEqual(sorted(chave[1] for chave in self.servico.objetos),
                         ["vareleira-lar-l100", "vareleira-lar-l200", "vareleira-lar-l200-fonte", "vareleira-lar-l200-indexador"])

    def test_remover_para_se_um_dos_nomes_do_l300_e_de_outro_dono(self):
        self.criar_objetos()
        self.servico.objetos[(li.SKILLSET, SKILLSET)]["description"] = "de outra pessoa"
        codigo, saida = self.rodar("remover", "--busca", BUSCA, "--executar")
        self.assertEqual(codigo, lab_comum.CODIGO_DIVERGENCIA, saida)
        self.assertEqual([metodo for metodo, _ in self.escritas()], [], "nada foi apagado")
        self.assertEqual(len(self.servico.objetos), 4)

    def test_conferir_compara_a_classe_de_acesso_de_cada_trecho_com_o_manifesto(self):
        self.criar_objetos()
        self.assertEqual(self.rodar("executar", "--busca", BUSCA, "--executar", "--aguardar")[0], lab_comum.CODIGO_OK)
        manifesto = l300.carregar_manifesto(self.manifesto, self.raiz)
        completo = trechos_do_indice(manifesto)
        self.servico.documentos[INDICE] = completo
        self.servico.requisicoes.clear()
        codigo, saida = self.rodar("conferir", *CRIAR)
        self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)
        for esperado in ("Conferência aprovada", "atendimento 2", "compartilhado 6", "Ambiente de execução do indexador", "'private'"):
            self.assertIn(esperado, saida)
        casos = {
            "trecho sem classe": (lambda t: t[-1].update(acesso=None), "sem classe de acesso"),
            "classe vazia": (lambda t: t[-1].update(acesso=""), "sem classe de acesso"),
            "classe desconhecida": (lambda t: t[-1].update(acesso="interno"), "fora da lista"),
            "classe diferente da do manifesto": (lambda t: t[-1].update(acesso="compartilhado"), "classe diferente da do manifesto"),
            "documento fora do manifesto": (lambda t: t[0].update(documento_id="VLAR-XX-9.9"), "não declara"),
            "documento sem trechos": (lambda t: t.__delitem__(slice(-2, None)), "sem trechos"),
        }
        for rotulo, (alterar, trecho_da_mensagem) in casos.items():
            with self.subTest(rotulo=rotulo):
                trechos = copy.deepcopy(completo)
                alterar(trechos)
                self.servico.documentos[INDICE] = trechos
                codigo, saida = self.rodar("conferir", "--busca", BUSCA)
                self.assertEqual(codigo, lab_comum.CODIGO_DIVERGENCIA, saida)
                self.assertIn(trecho_da_mensagem, saida)
        self.assertEqual(self.escritas(), [], "conferir só lê")

    def test_conferir_ausente_aprova_a_exclusao_so_quando_o_documento_saiu_do_indice(self):
        self.criar_objetos()
        self.assertEqual(self.rodar("executar", "--busca", BUSCA, "--executar", "--aguardar")[0], lab_comum.CODIGO_OK)
        completo = trechos_do_indice(l300.carregar_manifesto(self.manifesto, self.raiz))
        self.servico.documentos[INDICE] = completo
        codigo, saida = self.rodar("conferir", "--busca", BUSCA, "--ausente", OPERACIONAL)
        self.assertEqual(codigo, lab_comum.CODIGO_DIVERGENCIA, saida)
        self.assertIn("ainda há 2 trecho(s)", saida)
        self.servico.documentos[INDICE] = [trecho for trecho in completo if trecho["documento_id"] != OPERACIONAL]
        codigo, saida = self.rodar("conferir", "--busca", BUSCA, "--ausente", OPERACIONAL)
        self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)
        self.assertEqual(self.rodar("conferir", "--busca", BUSCA)[0], lab_comum.CODIGO_DIVERGENCIA, "sem --ausente, a falta do documento reprova")


# --------------------------------------------------------------------------------------
# Blobs: carregar, excluir e restaurar
# --------------------------------------------------------------------------------------

class BlobsTests(BaseL300):
    def test_carregar_simula_por_padrao_e_envia_so_o_manifesto_com_a_classe_de_acesso(self):
        codigo, saida = self.rodar("carregar", "--conta", CONTA)
        self.assertEqual((codigo, self.container.envios), (lab_comum.CODIGO_OK, []), saida)
        self.assertEqual(saida.count("[criar     ]"), 4)
        self.carregar_blobs()
        manifesto = l300.carregar_manifesto(self.manifesto, self.raiz)
        self.assertEqual(sorted(self.container.blobs), sorted(documento.blob for documento in manifesto.documentos))
        for documento in manifesto.documentos:
            blob = self.container.blobs[documento.blob]
            self.assertEqual(blob.metadata, documento.metadados_blob)
            self.assertEqual(lab_comum.calcular_sha256(blob.dados), documento.sha256, "o blob tem o conteúdo normalizado do manifesto")
        self.assertEqual(self.container.blobs[BLOB_OPERACIONAL].metadata["acesso"], "atendimento")
        self.assertEqual({(conta, container) for conta, container, _ in self.abertos}, {(CONTA, "base-documental-l300")},
                         "só o contêiner do L300 foi aberto: o do L100 nunca")
        self.container.envios.clear()
        codigo, saida = self.rodar("carregar", "--conta", CONTA, "--executar")
        self.assertEqual((codigo, self.container.envios), (lab_comum.CODIGO_OK, []), "a recarga não reenvia o que já está igual")

    def test_carregar_pode_limitar_o_envio_ao_documento_operacional(self):
        codigo, saida = self.rodar("carregar", "--conta", CONTA, "--documento", OPERACIONAL, "--executar")
        self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)
        self.assertEqual(list(self.container.blobs), [BLOB_OPERACIONAL])
        self.assertEqual(self.rodar("carregar", "--conta", CONTA, "--documento", "VLAR-XX-9.9")[0], lab_comum.CODIGO_USO)

    def test_mudanca_de_classe_atualiza_so_os_metadados_do_blob_do_l300_e_exige_confirmacao(self):
        self.carregar_blobs()
        antes = {nome: (blob.dados, blob.etag) for nome, blob in self.container.blobs.items()}
        self.container.envios.clear()
        self.alterar_manifesto(lambda b: self.documento(b).update(acesso="corretor"))
        for opcoes in ((), ("--executar",)):
            codigo, saida = self.rodar("carregar", "--conta", CONTA, *opcoes)
            self.assertEqual(codigo, lab_comum.CODIGO_DIVERGENCIA, saida)
            self.assertIn("metadados diferentes: acesso", saida)
        self.assertEqual(self.container.metadados, [], "sem --substituir-divergentes nada é alterado")
        codigo, saida = self.rodar("carregar", "--conta", CONTA, "--executar", "--substituir-divergentes")
        self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)
        self.assertEqual((self.container.metadados, self.container.envios), ([BLOB_OPERACIONAL], []), "só metadados, só do blob operacional")
        self.assertEqual(self.container.blobs[BLOB_OPERACIONAL].metadata["acesso"], "corretor")
        for nome, (dados, etag) in antes.items():
            self.assertEqual(self.container.blobs[nome].dados, dados)
            self.assertEqual(self.container.blobs[nome].etag != etag, nome == BLOB_OPERACIONAL)

    def test_conteudo_diferente_exige_confirmacao_e_blob_alterado_depois_do_plano_nao_e_sobrescrito(self):
        self.carregar_blobs()
        self.container.blobs[BLOB_OPERACIONAL].dados = b"conteudo de outra pessoa"
        self.container.envios.clear()
        codigo, saida = self.rodar("carregar", "--conta", CONTA, "--executar")
        self.assertEqual((codigo, self.container.envios), (lab_comum.CODIGO_DIVERGENCIA, []), saida)
        self.assertIn("conteúdo diferente do manifesto", saida)
        self.container.antes_de_enviar = lambda nome: setattr(self.container.blobs[nome], "etag", "etag-de-outra-pessoa")
        codigo, saida = self.rodar("carregar", "--conta", CONTA, "--executar", "--substituir-divergentes")
        self.assertEqual((codigo, self.container.envios), (lab_comum.CODIGO_DIVERGENCIA, []), saida)
        self.assertIn("mudou depois da simulação", saida)
        self.assertEqual(self.container.blobs[BLOB_OPERACIONAL].dados, b"conteudo de outra pessoa")
        self.container.antes_de_enviar = lambda nome: None
        self.assertEqual(self.rodar("carregar", "--conta", CONTA, "--executar", "--substituir-divergentes")[0], lab_comum.CODIGO_OK)
        self.assertEqual(self.container.envios, [BLOB_OPERACIONAL])

    def test_carregar_avisa_blob_sem_permissao_declarada_e_nunca_o_apaga(self):
        self.carregar_blobs()
        self.container.colocar("vareleira-lar-l300/escondido.md", b"# fora do manifesto\n", {"acesso": "compartilhado"})
        codigo, saida = self.rodar("carregar", "--conta", CONTA, "--executar")
        self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)
        self.assertIn("sem permissão declarada no manifesto: vareleira-lar-l300/escondido.md", saida)
        self.assertIn("o filtro do chat autoriza classes, não IDs do manifesto", saida, "o aviso não promete o que o filtro não faz")
        self.assertIn("vareleira-lar-l300/escondido.md", self.container.blobs)
        self.assertEqual(self.container.exclusoes, [])

    def test_excluir_e_restaurar_atuam_so_no_documento_operacional_e_a_exclusao_e_reversivel(self):
        self.carregar_blobs()
        originais = {nome: blob.etag for nome, blob in self.container.blobs.items()}
        codigo, saida = self.rodar("excluir", "--conta", CONTA, "--documento", OPERACIONAL)
        self.assertEqual((codigo, self.container.exclusoes), (lab_comum.CODIGO_OK, []), saida)
        self.assertIn("Simulação concluída", saida)
        for protegido in COMPARTILHADOS:
            codigo, saida = self.rodar("excluir", "--conta", CONTA, "--documento", protegido, "--executar")
            self.assertEqual((codigo, self.container.exclusoes), (lab_comum.CODIGO_USO, []), saida)
            self.assertIn("ficam protegidas", saida)
        codigo, saida = self.rodar("excluir", "--conta", CONTA, "--documento", OPERACIONAL, "--executar")
        self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)
        self.assertEqual((self.container.exclusoes, sorted(self.container.blobs)),
                         ([BLOB_OPERACIONAL], sorted(nome for nome in originais if nome != BLOB_OPERACIONAL)))
        self.assertIn(BLOB_OPERACIONAL, self.container.deletados, "excluído de forma reversível, não apagado")
        self.assertIn("--etapa restaurar", saida)
        self.assertIn("excluído", self.rodar("excluir", "--conta", CONTA, "--documento", OPERACIONAL, "--executar")[1], "a segunda exclusão não faz nada")
        self.assertEqual(self.container.exclusoes, [BLOB_OPERACIONAL])

        codigo, saida = self.rodar("restaurar", "--conta", CONTA, "--documento", OPERACIONAL)
        self.assertEqual((codigo, self.container.restauracoes), (lab_comum.CODIGO_OK, []), saida)
        self.assertIn("[restaurar ]", saida)
        codigo, saida = self.rodar("restaurar", "--conta", CONTA, "--documento", OPERACIONAL, "--executar")
        self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)
        self.assertEqual((self.container.restauracoes, self.container.metadados), ([BLOB_OPERACIONAL], [BLOB_OPERACIONAL]))
        restaurado = self.container.blobs[BLOB_OPERACIONAL]
        self.assertEqual(restaurado.metadata["acesso"], "atendimento")
        self.assertNotEqual(restaurado.etag, originais[BLOB_OPERACIONAL], "os metadados reaplicados atualizam o blob para o indexador reprocessá-lo")
        for nome, etag in originais.items():
            if nome != BLOB_OPERACIONAL:
                self.assertEqual(self.container.blobs[nome].etag, etag, "os blobs compartilhados não foram tocados")
        self.assertIn("Nenhum blob excluído", self.rodar("restaurar", "--conta", CONTA, "--documento", OPERACIONAL, "--executar")[1])

    def test_restaurar_com_conteudo_igual_reaplica_a_classe_do_manifesto_com_o_etag_conferido(self):
        self.carregar_blobs()
        self.assertEqual(self.rodar("excluir", "--conta", CONTA, "--documento", OPERACIONAL, "--executar")[0], lab_comum.CODIGO_OK)
        excluido = self.container.deletados[BLOB_OPERACIONAL]
        excluido.metadata = {**excluido.metadata, "acesso": "compartilhado"}
        etag_da_versao_excluida = excluido.etag
        codigo, saida = self.rodar("restaurar", "--conta", CONTA, "--documento", OPERACIONAL, "--executar")
        self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)
        self.assertEqual(self.container.blobs[BLOB_OPERACIONAL].metadata["acesso"], "atendimento", "a classe vem do manifesto, não da versão restaurada")
        (opcoes,) = self.container.opcoes_de_metadados
        self.assertEqual((opcoes["etag"], opcoes["match_condition"]), (etag_da_versao_excluida, MatchConditions.IfNotModified))

    def test_restaurar_com_conteudo_divergente_nao_reaplica_metadados_e_termina_com_divergencia(self):
        esperado = lab_comum.normalizar_texto((self.raiz / ARQUIVO_OPERACIONAL).read_bytes())
        variantes = {"tamanho diferente": b"versao antiga do roteiro", "mesmo tamanho e outro hash": bytes([esperado[0] ^ 1]) + esperado[1:]}
        self.assertEqual(len(variantes["mesmo tamanho e outro hash"]), len(esperado))
        for rotulo, divergente in variantes.items():
            with self.subTest(rotulo=rotulo):
                self.container = ContainerL300()
                self.carregar_blobs()
                self.assertEqual(self.rodar("excluir", "--conta", CONTA, "--documento", OPERACIONAL, "--executar")[0], lab_comum.CODIGO_OK)
                excluido = self.container.deletados[BLOB_OPERACIONAL]
                excluido.dados, excluido.metadata = divergente, {**excluido.metadata, "acesso": "compartilhado"}
                metadados_da_exclusao = dict(excluido.metadata)

                codigo, saida = self.rodar("restaurar", "--conta", CONTA, "--documento", OPERACIONAL, "--executar")
                self.assertEqual(codigo, lab_comum.CODIGO_DIVERGENCIA, saida)
                self.assertEqual((self.container.metadados, self.container.opcoes_de_metadados), ([], []),
                                 "nenhuma set_blob_metadata: a classe do manifesto não vai para bytes que ninguém autorizou")
                restaurado = self.container.blobs[BLOB_OPERACIONAL]
                self.assertEqual((self.container.restauracoes, restaurado.dados, restaurado.metadata),
                                 ([BLOB_OPERACIONAL], divergente, metadados_da_exclusao), "estado parcial: restaurado, sem reclassificação")
                for dito in (OPERACIONAL, "foi restaurado", "NÃO foram reaplicados", "reposição autorizada", "--substituir-divergentes",
                             "a indexação deve aguardar", "não execute o indexador"):
                    self.assertIn(dito, saida)
                for falso_sucesso in ("[RESTAURADO]", "Concluído", "Próximo passo"):
                    self.assertNotIn(falso_sucesso, saida)

                self.assertIn("Nenhum blob excluído", self.rodar("restaurar", "--conta", CONTA, "--documento", OPERACIONAL, "--executar")[1])
                self.assertEqual(self.container.metadados, [], "repetir a restauração não reclassifica nada")
                self.assertEqual(self.rodar("carregar", "--conta", CONTA, "--executar")[0], lab_comum.CODIGO_DIVERGENCIA)
                self.assertEqual(self.container.blobs[BLOB_OPERACIONAL].dados, divergente, "sem --substituir-divergentes nada é trocado")
                codigo, saida = self.rodar("carregar", "--conta", CONTA, "--executar", "--substituir-divergentes")
                self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)
                reposto = self.container.blobs[BLOB_OPERACIONAL]
                self.assertEqual((reposto.dados, reposto.metadata["acesso"]), (esperado, "atendimento"), "a reposição autorizada repõe conteúdo e classe")

    def test_restauracao_para_no_primeiro_divergente_e_diz_o_que_foi_feito_e_o_que_ficou_sem_processar(self):
        def documento(nome, conteudo):
            return l300.DocumentoL300(
                id=f"VLAR-OP-{nome.upper()}-1.0", titulo=nome, tipo="roteiro-operacional", produto="vareleira-lar", versao="1.0",
                origem=l300.ORIGEM_L300, arquivo=self.raiz / f"{nome}.md", arquivo_relativo=f"dados/l300/documentos/{nome}.md",
                blob=f"vareleira-lar-l300/{nome}.md", tipo_conteudo="text/markdown; charset=utf-8", tamanho_bytes=len(conteudo),
                sha256=lab_comum.calcular_sha256(conteudo), acesso="atendimento", revisao_status="pendente")

        conferido, divergente, nao_processado = documento("a", b"conteudo a"), documento("b", b"conteudo b"), documento("c", b"conteudo c")
        container = ContainerL300()
        for item, no_blob in ((conferido, b"conteudo a"), (divergente, b"outro conteudo"), (nao_processado, b"conteudo c")):
            container.colocar(item.blob, no_blob, {"acesso": "compartilhado"})
            container.deletados[item.blob] = container.blobs.pop(item.blob)
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(lab_comum.ErroLab) as contexto:
            l300.aplicar_restauracao(container, [l300.AcaoBlob(item, l300.RESTAURAR) for item in (conferido, divergente, nao_processado)])
        self.assertEqual(contexto.exception.codigo, lab_comum.CODIGO_DIVERGENCIA)
        self.assertEqual((container.restauracoes, container.metadados), ([conferido.blob, divergente.blob], [conferido.blob]))
        self.assertEqual(container.blobs[divergente.blob].metadata, {"acesso": "compartilhado"}, "o divergente não foi reclassificado")
        self.assertIn(nao_processado.blob, container.deletados, "o seguinte nem foi tentado")
        self.assertIn(f"nesta execução: {conferido.id}.", str(contexto.exception))
        self.assertIn(f"seguem excluídos de forma reversível): {nao_processado.id}.", str(contexto.exception))

    def test_restaurar_o_que_nunca_existiu_e_excluir_o_que_nao_existe_nao_fazem_nada(self):
        for etapa in ("excluir", "restaurar"):
            codigo, saida = self.rodar(etapa, "--conta", CONTA, "--documento", OPERACIONAL, "--executar")
            self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)
            self.assertIn("ausente", saida)
        self.assertEqual((self.container.exclusoes, self.container.restauracoes, self.container.envios), ([], [], []))

    def test_conteiner_do_l100_e_recusado_e_a_identidade_gerenciada_e_opcional(self):
        for opcoes in (("--container", "base-documental"), ("--container", "base-documental-l200")):
            codigo, saida = self.rodar("carregar", "--conta", CONTA, *opcoes)
            self.assertEqual(codigo, lab_comum.CODIGO_USO, saida)
        self.assertEqual(self.abertos, [], "o contêiner do L100 nunca é aberto")
        cliente = "00000000-0000-0000-0000-000000000000"
        with mock.patch.object(l300, "criar_credencial_gerenciada", return_value="credencial-gerenciada") as criar:
            codigo, saida = self.rodar("carregar", "--conta", CONTA, "--identidade-gerenciada", "--client-id", cliente)
        self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)
        criar.assert_called_once_with(cliente)
        self.assertEqual(self.abertos, [(CONTA, "base-documental-l300", "credencial-gerenciada")])
        self.abertos.clear()
        self.assertEqual(self.rodar("carregar", "--conta", CONTA)[0], lab_comum.CODIGO_OK)
        self.assertEqual(self.abertos, [(CONTA, "base-documental-l300", None)], "sem a opção, vale o Azure CLI")
        for opcoes in (("--client-id", cliente), ("--identidade-gerenciada", "--tenant-id", "contoso.exemplo")):
            self.assertEqual(self.rodar("carregar", "--conta", CONTA, *opcoes)[0], lab_comum.CODIGO_USO, opcoes)

    def test_opcoes_que_faltam_ou_de_outra_etapa_sao_recusadas_antes_de_qualquer_acesso(self):
        casos = (("carregar", ()), ("excluir", ("--conta", CONTA)), ("restaurar", ("--documento", OPERACIONAL)),
                 ("criar", ("--busca", BUSCA)), ("executar", ()), ("conferir", ()), ("remover", ()),
                 ("validar", ("--substituir",)), ("validar", ("--identidade-gerenciada",)), ("carregar", ("--conta", CONTA, "--aguardar")),
                 ("conferir", ("--busca", BUSCA, "--intervalo", "30")), ("remover", ("--busca", BUSCA, "--indice", "vareleira-lar-l200")),
                 ("criar", (*CRIAR, "--privado", "--nao-privado")), ("criar", (*CRIAR, "--intervalo", "4")))
        for etapa, opcoes in casos:
            with self.subTest(etapa=etapa, opcoes=opcoes):
                codigo, saida = self.rodar(etapa, *opcoes)
                self.assertEqual(codigo, lab_comum.CODIGO_USO, saida)
        self.assertEqual((self.abertos, self.servico.requisicoes), ([], []), "nenhum acesso ao Azure")

    def test_a_ajuda_lista_as_etapas_e_nao_precisa_de_nenhuma_opcao(self):
        saida = io.StringIO()
        with contextlib.redirect_stdout(saida), self.assertRaises(SystemExit) as saiu:
            cli.principal(["--ajuda"])
        self.assertEqual(saiu.exception.code, 0)
        for etapa in cli.ETAPAS:
            self.assertIn(etapa, saida.getvalue())
        for opcao in ("--manifesto", "--documento", "--substituir-divergentes", "--privado", "--nao-privado", "--intervalo", "--ausente",
                      "--identidade-gerenciada", "--executar"):
            self.assertIn(opcao, saida.getvalue())


if __name__ == "__main__":
    unittest.main()
