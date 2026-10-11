"""Testes da ingestão gerenciada do L200: definições, cliente REST, etapas do script e comparação com o L100 (sem Azure).

O serviço de busca é um dublê no nível HTTP: o cliente real monta os pedidos (endereço, cabeçalhos, condições de ETag, versão da
API) e o dublê guarda objetos, aplica as condições e devolve respostas parecidas com as do serviço, com os valores padrão que ele
acrescenta. Cada pedido fica registrado para provar o que o script leu e o que alterou.
"""

import contextlib
import copy
import http.server
import io
import json
import re
import threading
import unittest
import urllib.parse
from types import SimpleNamespace
from unittest import mock

import support  # noqa: F401  (configura o caminho dos scripts)
import gerenciar_ingestao
import lab_comum
import lab_indexacao
import lab_ingestao as li
from support import IndiceFalso, copiar_pacote, indexar_pacote, vetor_falso

BUSCA, MODELOS, CONTA = "srch-vlr-exemplo", "ais-vlr-exemplo", "stvlrag1234567890"
ASSINATURA, GRUPO = "00000000-0000-0000-0000-000000000000", "rg-vlr-exemplo"
TOKEN = "token-secreto-de-teste-0123456789"
INDICE, INDICE_L100 = "vareleira-lar-l200", "vareleira-lar-l100"
FONTE, SKILLSET, INDEXADOR = f"{INDICE}-fonte", f"{INDICE}-skillset", f"{INDICE}-indexador"
OBJETOS = [(li.INDICE, INDICE), (li.FONTE, FONTE), (li.SKILLSET, SKILLSET), (li.INDEXADOR, INDEXADOR)]
CRIAR = ["--assinatura", ASSINATURA, "--grupo", GRUPO, "--conta", CONTA, "--modelos", MODELOS]
DIMENSOES = 8


class CredencialFalsa:
    def __init__(self):
        self.escopos = []

    def get_token(self, escopo, **_):
        self.escopos.append(escopo)
        return SimpleNamespace(token=TOKEN, expires_on=4102444800)


class RelogioFalso:
    def __init__(self):
        self.t, self.dormidas = 0.0, []

    def agora(self):
        return self.t

    def dormir(self, segundos):
        self.dormidas.append(segundos)
        self.t += segundos


def paginas(texto, tamanho=1200, sobreposicao=100):
    """Divisão por janelas fixas: imita, sem as regras de frase do serviço, o que o Text Split devolve."""
    return [texto[i:i + tamanho] for i in range(0, len(texto), tamanho - sobreposicao) if texto[i:i + tamanho].strip()]


def documentos_do_l200(inventario, dimensoes=DIMENSOES):
    """Trechos como o indexador os gravaria: metadados do blob, endereço do blob em fonte, sem seção nem cláusulas."""
    docs = []
    for documento in lab_comum.carregar_inventario(inventario).documentos:
        for ordem, pagina in enumerate(paginas(lab_comum.ler_conteudo(documento).decode("utf-8"))):
            docs.append({
                "id": f"{documento.id.lower()}_pages_{ordem}", "id_pai": documento.id.lower(), "documento_id": documento.id,
                "titulo_documento": documento.blob.rsplit("/", 1)[-1], "produto": documento.produto, "versao": documento.versao,
                "secao": None, "clausulas": None, "conteudo": pagina,
                "fonte": f"https://{CONTA}.blob.core.windows.net/base-documental/{documento.blob}",
                "sha256": documento.sha256, "sintetico": "true", "vetor": vetor_falso(pagina, dimensoes)})
    return docs


def com_padroes_do_servico(tipo, objeto, devolve_credenciais):
    """O que o GET devolve além do enviado: valores padrão, nulos e a cadeia de conexão oculta."""
    copia = copy.deepcopy(objeto)
    copia["@odata.context"] = "https://exemplo/$metadata#objeto"
    if tipo == li.FONTE:
        copia["identity"], copia["encryptionKey"], copia["dataChangeDetectionPolicy"] = None, None, None
        if not devolve_credenciais:
            copia["credentials"] = {"connectionString": None}
    elif tipo == li.INDICE:
        for campo in copia["fields"]:
            campo.setdefault("synonymMaps", [])
            campo.setdefault("normalizer", None)
        for algoritmo in copia["vectorSearch"]["algorithms"]:
            algoritmo["hnswParameters"].update({"m": 4, "efConstruction": 400, "efSearch": 500})
        for perfil in copia["vectorSearch"]["profiles"]:
            perfil.setdefault("vectorizer", None)
        copia["scoringProfiles"], copia["encryptionKey"] = [], None
    elif tipo == li.SKILLSET:
        copia["cognitiveServices"], copia["knowledgeStore"] = None, None
        for habilidade in copia["skills"]:
            habilidade.setdefault("batchSize", None)
            for entrada in habilidade["inputs"]:
                entrada.setdefault("inputs", [])
        copia["skills"][0].update({"unit": "characters", "maximumPagesToTake": 0})
        for seletor in copia["indexProjections"]["selectors"]:
            for mapeamento in seletor["mappings"]:
                mapeamento.setdefault("sourceContext", None)
                mapeamento.setdefault("inputs", [])
    else:
        copia.update({"schedule": None, "fieldMappings": [], "outputFieldMappings": [], "cache": None, "encryptionKey": None})
        copia["parameters"].setdefault("batchSize", None)
    return copia


class ServicoBuscaFalso:
    """Imita o plano de dados do Azure AI Search no nível HTTP. Violações do contrato ficam em `violacoes`."""

    def __init__(self):
        self.objetos, self.documentos, self.requisicoes, self.violacoes = {}, {}, [], []
        self.falhas = {}  # (método, trecho do caminho) -> (status, código, mensagem, cabeçalhos)
        self.execucoes, self.em_andamento, self.ultimo = [], {}, {}
        self.polls_em_andamento = 0
        self.em_execucao = False
        self.resultado_final = {"status": "success", "itemsProcessed": 3, "itemsFailed": 0, "errors": [], "warnings": []}
        self.devolve_credenciais = False
        self.contador = 0
        self.versao_api = li.VERSAO_API

    def guardar(self, tipo, nome, definicao):
        self.contador += 1
        self.objetos[(tipo, nome)] = {**copy.deepcopy(definicao), "@odata.etag": f'"0x{self.contador}"'}

    def escritas(self):
        return [r for r in self.requisicoes if r.metodo in ("PUT", "DELETE")
                or (r.metodo == "POST" and "search.post.search" not in r.caminho)]

    def concluir_execucoes(self):
        """Termina as execuções em andamento, como se o indexador tivesse acabado entre dois comandos."""
        for nome in list(self.em_andamento):
            self.em_andamento[nome]["polls"] = 0
            self._status(nome)

    def __call__(self, metodo, url, cabecalhos, corpo):
        partes = urllib.parse.urlsplit(url)
        dados = json.loads(corpo) if corpo else None
        caminho = urllib.parse.unquote(partes.path).lstrip("/")
        self.requisicoes.append(SimpleNamespace(metodo=metodo, caminho=caminho, cabecalhos=dict(cabecalhos), corpo=dados))
        if partes.scheme != "https" or partes.netloc != f"{BUSCA}.search.windows.net":
            self.violacoes.append(f"endereço inesperado: {partes.netloc}")
            return self._erro(400, "BadRequest", "endereço inesperado")
        if cabecalhos.get("Authorization") != f"Bearer {TOKEN}":
            return self._erro(401, "Unauthorized", "token ausente ou inválido")
        if urllib.parse.parse_qs(partes.query).get("api-version") != [self.versao_api]:
            self.violacoes.append(f"api-version inesperada: {partes.query}")
            return self._erro(400, "BadRequest", "api-version")
        for (metodo_da_falha, trecho), (status, codigo, mensagem, extras) in self.falhas.items():
            if metodo_da_falha == metodo and trecho in caminho:
                return self._erro(status, codigo, mensagem, extras)
        return self._rotear(metodo, caminho, cabecalhos, dados)

    @staticmethod
    def _erro(status, codigo, mensagem, extras=None):
        corpo = json.dumps({"error": {"code": codigo, "message": mensagem}}).encode("utf-8")
        return li.RespostaHttp(status, corpo, dict(extras or {}))

    @staticmethod
    def _json(status, valor):
        return li.RespostaHttp(status, json.dumps(valor).encode("utf-8"), {})

    def _rotear(self, metodo, caminho, cabecalhos, dados):
        objeto = re.fullmatch(r"(indexes|datasources|skillsets|indexers)\('([^']+)'\)", caminho)
        acao = re.fullmatch(r"indexers\('([^']+)'\)/search\.(run|reset|status)", caminho)
        busca = re.fullmatch(r"indexes\('([^']+)'\)/docs/search\.post\.search", caminho)
        if objeto:
            return self._objeto(metodo, (objeto.group(1), objeto.group(2)), cabecalhos, dados)
        if acao:
            return self._acao(metodo, acao.group(1), acao.group(2))
        if busca and metodo == "POST":
            return self._buscar(busca.group(1), dados)
        self.violacoes.append(f"rota inesperada: {metodo} {caminho}")
        return self._erro(400, "BadRequest", "rota inesperada")

    def _objeto(self, metodo, chave, cabecalhos, dados):
        existente = self.objetos.get(chave)
        if metodo == "GET":
            if existente is None:
                return self._erro(404, "ResourceNotFound", "não existe")
            return self._json(200, com_padroes_do_servico(chave[0], existente, self.devolve_credenciais))
        if metodo == "PUT":
            if cabecalhos.get("Prefer") != "return=representation":
                self.violacoes.append("PUT sem Prefer: return=representation")
            if "If-None-Match" not in cabecalhos and "If-Match" not in cabecalhos:
                self.violacoes.append(f"PUT incondicional em {chave}")
            if cabecalhos.get("If-None-Match") == "*" and existente is not None:
                return self._erro(412, "PreconditionFailed", "já existe")
            if "If-Match" in cabecalhos and (existente is None or existente["@odata.etag"] != cabecalhos["If-Match"]):
                return self._erro(412, "PreconditionFailed", "o objeto mudou")
            self.guardar(chave[0], chave[1], dados)
            if chave[0] == li.INDEXADOR and not dados.get("disabled"):
                self.execucoes.append(chave[1])
                self.em_andamento[chave[1]] = {"polls": self.polls_em_andamento, "inicio": f"2026-10-10T10:00:0{len(self.execucoes)}Z"}
            return self._json(200 if existente else 201, com_padroes_do_servico(chave[0], self.objetos[chave], False))
        if metodo == "DELETE":
            if existente is None:
                return self._erro(404, "ResourceNotFound", "não existe")
            if "If-Match" in cabecalhos and existente["@odata.etag"] != cabecalhos["If-Match"]:
                return self._erro(412, "PreconditionFailed", "o objeto mudou")
            del self.objetos[chave]
            return li.RespostaHttp(204)
        self.violacoes.append(f"método inesperado: {metodo}")
        return self._erro(405, "MethodNotAllowed", "método")

    def _acao(self, metodo, nome, acao):
        indexador = self.objetos.get((li.INDEXADOR, nome))
        if indexador is None:
            return self._erro(404, "ResourceNotFound", "não existe")
        if acao == "status" and metodo == "GET":
            return self._json(200, self._status(nome))
        if acao == "reset" and metodo == "POST":
            self.ultimo.pop(nome, None)
            return li.RespostaHttp(204)
        if acao == "run" and metodo == "POST":
            if indexador.get("disabled"):
                self.violacoes.append("run em indexador desabilitado")
                return self._erro(409, "Conflict", "indexador desabilitado")
            if self.em_execucao:
                return self._erro(409, "Conflict", "Another indexer invocation is currently in progress; concurrent invocations are not allowed.")
            self.execucoes.append(nome)
            self.em_andamento[nome] = {"polls": self.polls_em_andamento, "inicio": f"2026-10-10T10:00:0{len(self.execucoes)}Z"}
            return li.RespostaHttp(202)
        self.violacoes.append(f"ação inesperada: {metodo} {acao}")
        return self._erro(400, "BadRequest", "ação")

    def _status(self, nome):
        execucao = self.em_andamento.get(nome)
        if execucao and execucao["polls"] > 0:
            execucao["polls"] -= 1
            ultimo = {"status": "inProgress", "startTime": execucao["inicio"], "itemsProcessed": 0, "itemsFailed": 0,
                      "errors": [], "warnings": []}
        elif execucao:
            ultimo = {**self.resultado_final, "startTime": execucao["inicio"], "endTime": "2026-10-10T10:05:00Z"}
            self.ultimo[nome] = ultimo
            del self.em_andamento[nome]
        else:
            ultimo = self.ultimo.get(nome)
        return {"name": nome, "status": "running", "lastResult": ultimo, "executionHistory": [ultimo] if ultimo else [],
                "limits": {"maxRunTime": "PT22H"}}

    def _buscar(self, indice, dados):
        definicao = self.objetos.get((li.INDICE, indice))
        if definicao is None:
            return self._erro(404, "ResourceNotFound", "o índice não existe")
        campos = [campo for campo in dados["select"].split(",")]
        existentes = {campo["name"] for campo in definicao["fields"]}
        if set(campos) - existentes:
            return self._erro(400, "InvalidRequest", f"campo desconhecido: {sorted(set(campos) - existentes)}")
        docs = self.documentos.get(indice, [])
        limite = dados.get("top", 50)  # sem top, o serviço devolve só uma página de 50 e uma continuação
        if limite > 1000:
            return self._erro(400, "InvalidRequestParameter", "top acima de 1000")
        resposta = {"value": [{campo: doc.get(campo) for campo in campos} | {"@search.score": 1.0} for doc in docs[:limite]]}
        if len(docs) > limite:
            resposta["@odata.nextPageParameters"] = {"search": dados.get("search"), "top": limite, "skip": limite}
        if dados.get("count"):
            resposta["@odata.count"] = len(docs)
        return self._json(200, resposta)


class IndiceRoteirizado:
    """Índice de consulta com respostas combinadas por texto da pergunta (modo texto): o resultado de cada pergunta é conhecido."""

    def __init__(self, respostas):
        self.respostas, self.consultas = respostas, []

    def consultar(self, texto, vetor, k):
        self.consultas.append((texto, vetor, k))
        return [dict(item) for item in self.respostas.get(texto, [])][:k]


class BaseDeTeste(unittest.TestCase):
    def setUp(self):
        self.pasta, self.inventario = copiar_pacote()
        self.addCleanup(self.pasta.cleanup)
        self.servico, self.credencial, self.relogio = ServicoBuscaFalso(), CredencialFalsa(), RelogioFalso()
        self.addCleanup(lambda: self.assertEqual(self.servico.violacoes, []))
        for alvo, nome, valor in ((li, "abrir_cliente", None), (li, "_relogio", self.relogio.agora), (li, "_dormir", self.relogio.dormir)):
            parar = (mock.patch.object(alvo, nome, side_effect=self._abrir_cliente) if valor is None
                     else mock.patch.object(alvo, nome, valor))
            parar.start()
            self.addCleanup(parar.stop)
        self.documentos = lab_comum.carregar_inventario(self.inventario).documentos

    def _abrir_cliente(self, busca, tenant_id=None, versao_api=li.VERSAO_API):
        self.servico.versao_api = versao_api
        return li.ClienteBusca(busca, tenant_id, credencial=self.credencial, transporte=self.servico, versao_api=versao_api)

    def rodar(self, etapa, *opcoes, abrir_indice=None, openai=None):
        argumentos = ["--etapa", etapa, "--busca", BUSCA, "--inventario", str(self.inventario), *opcoes]
        saida = io.StringIO()
        with contextlib.ExitStack() as pilha:
            if abrir_indice is not None:
                pilha.enter_context(mock.patch.object(lab_indexacao, "abrir_indice", abrir_indice))
            if openai is not None:
                pilha.enter_context(mock.patch.object(
                    lab_indexacao, "criar_cliente_embeddings",
                    side_effect=lambda modelos, deployment, dimensoes, tenant=None, credencial=None:
                    lab_indexacao.ClienteEmbeddings(openai, deployment, dimensoes)))
            pilha.enter_context(contextlib.redirect_stdout(saida))
            pilha.enter_context(contextlib.redirect_stderr(saida))
            try:
                codigo = gerenciar_ingestao.principal(argumentos)
            except SystemExit as erro:  # erro de argumentos do argparse
                codigo = erro.code
        self.assertNotIn(TOKEN, saida.getvalue(), "o token nunca pode aparecer na saída")
        return codigo, saida.getvalue()

    def criar_objetos(self, *opcoes):
        codigo, saida = self.rodar("criar", *CRIAR, "--executar", *opcoes)
        self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)
        self.servico.requisicoes.clear()

    def metodos(self):
        return [(r.metodo, r.caminho.split("/")[0] if r.metodo != "POST" else r.caminho) for r in self.servico.requisicoes]

    def parametros(self, dimensoes=1536, **ajustes):
        base = dict(nomes=li.nomes_dos_objetos(INDICE), assinatura=ASSINATURA, grupo=GRUPO, conta=CONTA, container="base-documental",
                    prefixo="vareleira-lar", modelos=MODELOS, deployment="embeddings", modelo_embeddings="text-embedding-3-small",
                    dimensoes=dimensoes, tamanho_maximo=1200, sobreposicao=100)
        return li.Parametros(**{**base, **ajustes})


class DefinicoesTests(BaseDeTeste):
    def test_indice_tem_os_campos_do_recuperador_do_l100_e_o_perfil_vetorial(self):
        indice = li.definicao_do_indice(self.parametros())
        campos = {campo["name"]: campo for campo in indice["fields"]}
        for nome in ("id", "documento_id", "titulo_documento", "secao", "clausulas", "conteudo", "fonte", "versao", "vetor"):
            self.assertIn(nome, campos)
        self.assertEqual(li.CAMPOS_COMPATIVEIS, (*lab_indexacao.IndiceBusca.CAMPOS_DO_RESULTADO, "vetor"))
        self.assertEqual((campos["id"]["key"], campos["id"]["analyzer"], campos["id"]["searchable"]), (True, "keyword", True))
        self.assertEqual((campos["id_pai"]["filterable"], campos["id_pai"]["key"]), (True, False))
        vetor = campos["vetor"]
        self.assertEqual((vetor["type"], vetor["dimensions"], vetor["retrievable"], vetor["stored"], vetor["vectorSearchProfile"]),
                         ("Collection(Edm.Single)", 1536, False, False, "perfil-hnsw"))
        busca_vetorial = indice["vectorSearch"]
        self.assertEqual(busca_vetorial["algorithms"], [{"name": "hnsw-cosseno", "kind": "hnsw", "hnswParameters": {"metric": "cosine"}}])
        self.assertEqual(busca_vetorial["profiles"], [{"name": "perfil-hnsw", "algorithm": "hnsw-cosseno"}])
        self.assertEqual(campos["conteudo"]["analyzer"], "pt-BR.microsoft")
        self.assertIn(li.MARCADOR, indice["description"])

    def test_skillset_divide_em_paginas_de_1200_com_100_e_gera_embeddings_sem_chave(self):
        skillset = li.definicao_do_skillset(self.parametros())
        divisao, embeddings = skillset["skills"]
        self.assertEqual(divisao["@odata.type"], "#Microsoft.Skills.Text.SplitSkill")
        self.assertEqual((divisao["textSplitMode"], divisao["maximumPageLength"], divisao["pageOverlapLength"]), ("pages", 1200, 100))
        self.assertNotIn("unit", divisao, "a unidade é um recurso em preview; o padrão já é caracteres")
        self.assertEqual(embeddings["@odata.type"], "#Microsoft.Skills.Text.AzureOpenAIEmbeddingSkill")
        self.assertEqual((embeddings["resourceUri"], embeddings["deploymentId"], embeddings["modelName"], embeddings["dimensions"]),
                         (f"https://{MODELOS}.openai.azure.com", "embeddings", "text-embedding-3-small", 1536))
        for chave in ("apiKey", "authIdentity"):
            self.assertNotIn(chave, embeddings, "sem chave nem identidade explícita: vale a identidade do serviço de busca")
        self.assertEqual(embeddings["context"], "/document/pages/*")
        self.assertEqual(skillset["indexProjections"]["parameters"], {"projectionMode": "skipIndexingParentDocuments"})

    def test_projecao_mapeia_cada_campo_do_indice_menos_a_chave_e_o_pai(self):
        p = self.parametros()
        seletor = li.definicao_do_skillset(p)["indexProjections"]["selectors"][0]
        mapeados = {m["name"]: m["source"] for m in seletor["mappings"]}
        campos = {c["name"] for c in li.definicao_do_indice(p)["fields"]}
        self.assertEqual(set(mapeados), campos - {"id", "id_pai", "secao", "clausulas"})
        self.assertEqual((seletor["targetIndexName"], seletor["parentKeyFieldName"], seletor["sourceContext"]),
                         (INDICE, "id_pai", "/document/pages/*"))
        self.assertEqual(mapeados["documento_id"], "/document/documento_id")
        self.assertEqual(mapeados["versao"], "/document/versao")
        self.assertEqual(mapeados["fonte"], "/document/metadata_storage_path")
        self.assertEqual(mapeados["vetor"], "/document/pages/*/vetor")

    def test_fonte_usa_resourceid_sem_chave_pasta_do_inventario_e_exclusao_nativa(self):
        fonte = li.definicao_da_fonte(self.parametros())
        self.assertEqual(fonte["type"], "azureblob")
        self.assertEqual(fonte["credentials"]["connectionString"],
                         f"ResourceId=/subscriptions/{ASSINATURA}/resourceGroups/{GRUPO}/providers/Microsoft.Storage/storageAccounts/{CONTA}/;")
        for proibido in ("AccountKey", "SharedAccessSignature", "DefaultEndpointsProtocol", "SharedAccessKey"):
            self.assertNotIn(proibido, fonte["credentials"]["connectionString"])
        self.assertEqual(fonte["container"], {"name": "base-documental", "query": "vareleira-lar"})
        self.assertEqual(fonte["dataDeletionDetectionPolicy"],
                         {"@odata.type": "#Microsoft.Azure.Search.NativeBlobSoftDeleteDeletionDetectionPolicy"})
        self.assertRegex(fonte["description"], rf"\[{li.MARCADOR} destino=[0-9a-f]{{12}}\]")
        self.assertNotIn(CONTA, fonte["description"], "a descrição guarda só o hash do destino")

    def test_o_sdk_estavel_reconhece_as_quatro_definicoes_com_os_tipos_e_valores_esperados(self):
        from azure.search.documents.indexes import models as sdk

        p = self.parametros()
        indice = sdk.SearchIndex(li.definicao_do_indice(p))
        campos = {campo.name: campo for campo in indice.fields}
        self.assertEqual((campos["vetor"].vector_search_dimensions, campos["vetor"].vector_search_profile_name, campos["vetor"].stored),
                         (1536, "perfil-hnsw", False))
        self.assertEqual(campos["id"].analyzer_name.value, "keyword")
        self.assertEqual(indice.vector_search.algorithms[0].parameters.metric.value, "cosine")
        skillset = sdk.SearchIndexerSkillset(li.definicao_do_skillset(p))
        divisao, embeddings = skillset.skills
        self.assertIsInstance(divisao, sdk.SplitSkill)
        self.assertEqual((divisao.maximum_page_length, divisao.page_overlap_length, divisao.default_language_code), (1200, 100, "pt-BR"))
        self.assertIsInstance(embeddings, sdk.AzureOpenAIEmbeddingSkill)
        self.assertEqual((embeddings.resource_url, embeddings.deployment_name, embeddings.dimensions),
                         (f"https://{MODELOS}.openai.azure.com", "embeddings", 1536))
        seletor = skillset.index_projection.selectors[0]
        self.assertEqual((seletor.parent_key_field_name, seletor.target_index_name), ("id_pai", INDICE))
        self.assertEqual(skillset.index_projection.parameters.projection_mode.value, "skipIndexingParentDocuments")
        fonte = sdk.SearchIndexerDataSourceConnection(li.definicao_da_fonte(p))
        self.assertIsInstance(fonte.data_deletion_detection_policy, sdk.NativeBlobSoftDeleteDeletionDetectionPolicy)
        self.assertEqual((fonte.container.name, fonte.container.query), ("base-documental", "vareleira-lar"))
        indexador = sdk.SearchIndexer(li.definicao_do_indexador(p))
        self.assertEqual((indexador.is_disabled, indexador.target_index_name), (True, INDICE))

    def test_indexador_nasce_desabilitado_e_le_texto_simples_de_arquivos_md(self):
        indexador = li.definicao_do_indexador(self.parametros())
        self.assertIs(indexador["disabled"], True)
        self.assertEqual((indexador["dataSourceName"], indexador["skillsetName"], indexador["targetIndexName"]), (FONTE, SKILLSET, INDICE))
        self.assertEqual(indexador["parameters"]["configuration"],
                         {"dataToExtract": "contentAndMetadata", "parsingMode": "text", "indexedFileNameExtensions": ".md"})
        self.assertNotIn("fieldMappings", indexador, "a projeção cuida dos campos; mapear a chave do pai atrapalharia o rastreamento")
        self.assertNotIn("schedule", indexador)

    def test_definicoes_sao_consistentes_e_a_ordem_de_criacao_respeita_as_dependencias(self):
        p = self.parametros()
        li.validar_parametros(p)
        self.assertEqual([tipo for tipo, _, _ in li.definicoes_em_ordem(p)], [li.INDICE, li.FONTE, li.SKILLSET, li.INDEXADOR])
        self.assertEqual([tipo for tipo, _ in p.nomes.em_ordem_de_remocao()], [li.INDEXADOR, li.SKILLSET, li.FONTE, li.INDICE])
        with self.assertRaises(lab_comum.ErroLab):
            li.validar_parametros(self.parametros(dimensoes=3000))
        with self.assertRaises(lab_comum.ErroLab):
            li.validar_parametros(self.parametros(sobreposicao=1200))
        with mock.patch.object(li, "CAMPOS_SEM_ORIGEM", ()):
            with self.assertRaisesRegex(lab_comum.ErroLab, "sem mapeamento"):
                li.validar_consistencia(p)

    def test_nomes_derivam_do_indice_e_recusam_o_indice_do_l100_e_nomes_de_fora(self):
        nomes = li.nomes_dos_objetos(f"{INDICE}-teste")
        self.assertEqual((nomes.fonte, nomes.skillset, nomes.indexador),
                         (f"{INDICE}-teste-fonte", f"{INDICE}-teste-skillset", f"{INDICE}-teste-indexador"))
        for nome in (INDICE_L100, "vareleira-lar-l2000", "outro-indice", f"{INDICE}--x", f"{INDICE}-A", "", f"{INDICE}/../x"):
            with self.assertRaises(lab_comum.ErroLab, msg=nome):
                li.nomes_dos_objetos(nome)

    def test_validadores_recusam_assinatura_grupo_prefixo_e_resourceid_invalidos(self):
        self.assertEqual(li.validar_prefixo_blob("vareleira-lar/"), "vareleira-lar")
        for validar, valor in ((li.validar_assinatura, "nao-e-guid"), (li.validar_assinatura, ASSINATURA + "/x"),
                               (li.validar_grupo, "rg/x"), (li.validar_grupo, "rg;x"), (li.validar_grupo, "rg."),
                               (li.validar_prefixo_blob, "../x"), (li.validar_prefixo_blob, "A/b"), (li.validar_prefixo_blob, "a//b"),
                               (li.validar_modelo_embeddings, "gpt-5"), (li.validar_espera, "5"), (li.validar_espera, "99999")):
            with self.assertRaises(Exception, msg=valor):
                validar(valor)
        for assinatura, grupo, conta in (("x", GRUPO, CONTA), (ASSINATURA, "a/b", CONTA), (ASSINATURA, GRUPO, "Conta;Key=1")):
            with self.assertRaises(lab_comum.ErroLab):
                li.construir_resource_id(assinatura, grupo, conta)

    def test_prefixo_do_inventario_e_a_pasta_comum_dos_blobs(self):
        inventario = lab_comum.carregar_inventario(self.inventario)
        self.assertEqual(li.prefixo_do_inventario(inventario), "vareleira-lar")
        outro = SimpleNamespace(documentos=[SimpleNamespace(blob="a/x.md"), SimpleNamespace(blob="b/y.md")])
        with self.assertRaisesRegex(lab_comum.ErroLab, "--prefixo"):
            li.prefixo_do_inventario(outro)

    def test_redacao_remove_tokens_chaves_e_identificadores_do_ambiente(self):
        jwt = "eyJhbGciOiJSUzI1NiJ9.eyJhdWQiOiJ4In0.assinaturaDoToken"
        texto = (f"Bearer {jwt} AccountKey=abc123== sig=zzz https://{CONTA}.blob.core.windows.net/c/a.md "
                 f"/subscriptions/{ASSINATURA}/resourceGroups/{GRUPO}/providers/x")
        redigido = li.redigir_texto(texto)
        for segredo in (jwt, "abc123", "zzz", CONTA, ASSINATURA, GRUPO):
            self.assertNotIn(segredo, redigido)
        definicao = li.redigir_definicao({**li.definicao_da_fonte(self.parametros()), "skills": [{"resourceUri": f"https://{MODELOS}.openai.azure.com"}]})
        self.assertEqual(definicao["credentials"]["connectionString"], li.RESOURCE_ID_REDIGIDO)
        self.assertNotIn(MODELOS, json.dumps(definicao))


class ClienteBuscaTests(BaseDeTeste):
    def cliente(self):
        return self._abrir_cliente(BUSCA, "tenant-exemplo")

    def test_criar_envia_token_so_ao_servico_com_versao_da_api_prefer_e_condicao_de_criacao(self):
        definicao = li.definicao_do_indice(self.parametros())
        self.cliente().gravar(li.INDICE, INDICE, definicao)
        pedido = self.servico.requisicoes[0]
        self.assertEqual((pedido.metodo, pedido.caminho), ("PUT", f"indexes('{INDICE}')"))
        self.assertEqual(pedido.cabecalhos["Authorization"], f"Bearer {TOKEN}")
        self.assertEqual((pedido.cabecalhos["Prefer"], pedido.cabecalhos["If-None-Match"]), ("return=representation", "*"))
        self.assertNotIn("If-Match", pedido.cabecalhos)
        self.assertEqual(pedido.cabecalhos["Content-Type"], "application/json")
        self.assertRegex(pedido.cabecalhos["x-ms-client-request-id"], r"^[0-9a-f-]{36}$")
        self.assertEqual(self.credencial.escopos, ["https://search.azure.com/.default"])
        self.assertEqual(pedido.corpo, definicao)

    def test_substituir_usa_o_etag_conferido_e_um_etag_velho_nao_sobrescreve(self):
        cliente = self.cliente()
        cliente.gravar(li.INDICE, INDICE, li.definicao_do_indice(self.parametros()))
        etag = cliente.obter(li.INDICE, INDICE)["@odata.etag"]
        cliente.gravar(li.INDICE, INDICE, li.definicao_do_indice(self.parametros()), etag=etag)
        self.assertEqual(self.servico.requisicoes[-1].cabecalhos["If-Match"], etag)
        with self.assertRaises(li.ErroServicoBusca) as contexto:
            cliente.gravar(li.INDICE, INDICE, li.definicao_do_indice(self.parametros()), etag=etag)
        self.assertEqual(contexto.exception.status, 412)
        with self.assertRaises(li.ErroServicoBusca) as contexto:
            cliente.gravar(li.INDICE, INDICE, li.definicao_do_indice(self.parametros()))
        self.assertEqual(contexto.exception.status, 412, "criar sobre um objeto existente também é recusado")

    def test_get_de_objeto_ausente_devolve_none_e_outros_erros_viram_erro_do_servico(self):
        cliente = self.cliente()
        self.assertIsNone(cliente.obter(li.FONTE, FONTE))
        self.servico.falhas[("GET", "datasources")] = (403, "Forbidden", "sem permissão", {})
        with self.assertRaises(li.ErroServicoBusca) as contexto:
            cliente.obter(li.FONTE, FONTE)
        self.assertEqual((contexto.exception.status, contexto.exception.codigo), (403, "Forbidden"))

    def test_nome_do_servico_e_de_objeto_so_aceitam_o_formato_esperado(self):
        for busca in ("meu-site.exemplo/", "a_b", "srch.evil.example", ""):
            with self.assertRaises(lab_comum.ErroLab, msg=busca):
                li.ClienteBusca(busca, transporte=self.servico, credencial=self.credencial)
        with self.assertRaises(lab_comum.ErroLab):
            li.ClienteBusca(BUSCA, transporte=self.servico, credencial=self.credencial, versao_api="2024-11-01-preview")
        with self.assertRaises(lab_comum.ErroLab):
            self.cliente().obter(li.INDICE, "nome')/../x")
        self.assertEqual(self.servico.requisicoes, [])

    def test_erros_http_viram_orientacao_em_portugues_com_codigo_de_saida(self):
        casos = [
            (401, {}, "recusou a credencial", lab_comum.CODIGO_ACESSO), (403, {}, "Search Service Contributor", lab_comum.CODIGO_ACESSO),
            (404, {}, "não foi encontrado", lab_comum.CODIGO_ACESSO), (409, {}, "outra execução", lab_comum.CODIGO_DIVERGENCIA),
            (412, {}, "Nada foi sobrescrito", lab_comum.CODIGO_DIVERGENCIA), (429, {"retry-after": "17"}, "Tente de novo em 17 s", lab_comum.CODIGO_ACESSO),
            (503, {}, "indisponível ou ocupado", lab_comum.CODIGO_ACESSO), (504, {}, "pode ter sido concluída", lab_comum.CODIGO_ACESSO),
            (400, {}, "recusou a definição", lab_comum.CODIGO_ACESSO), (418, {}, "Erro do serviço de busca (HTTP 418", lab_comum.CODIGO_ACESSO),
        ]
        args = SimpleNamespace(busca=BUSCA, versao_api=li.VERSAO_API)
        for status, cabecalhos, trecho, codigo in casos:
            erro = li.ErroServicoBusca(status, "Codigo", f"mensagem com {TOKEN}", "PUT", f"indexes('{INDICE}')", li.INDICE, INDICE,
                                       cabecalhos.get("retry-after"))
            mensagem, codigo_de_saida = li.traduzir_erro_ingestao(erro, args)
            self.assertIn(trecho, mensagem, status)
            self.assertEqual(codigo_de_saida, codigo, status)
            self.assertNotIn("mensagem com", mensagem, "a mensagem bruta do serviço só aparece com --detalhes")

    def test_erro_400_orienta_sobre_a_politica_de_exclusao_e_a_mensagem_so_vai_ao_traceback(self):
        erro = li.ErroServicoBusca(400, "InvalidRequestParameter", f"dataDeletionDetectionPolicy inválida; Bearer {TOKEN}00 /subscriptions/{ASSINATURA}/x",
                                   "PUT", f"datasources('{FONTE}')", li.FONTE, FONTE)
        mensagem, _ = li.traduzir_erro_ingestao(erro, SimpleNamespace(busca=BUSCA, versao_api="2025-09-01"))
        self.assertIn("2026-04-01", mensagem)
        self.assertIn("soft delete", mensagem)
        self.assertIn("em uso: 2025-09-01", mensagem)
        for segredo in (TOKEN, ASSINATURA):
            self.assertNotIn(segredo, mensagem + str(erro), "nem a mensagem nem o traceback (--detalhes) guardam segredo")
        self.assertIn("InvalidRequestParameter", str(erro))
        indice = li.ErroServicoBusca(400, "", "x", "PUT", f"indexes('{INDICE}')", li.INDICE, INDICE)
        self.assertIn("--etapa remover", li.traduzir_erro_ingestao(indice, SimpleNamespace(busca=BUSCA))[0])

    def test_falha_de_rede_vira_orientacao_de_conexao_e_erros_de_outros_modulos_seguem_o_l100(self):
        def sem_rede(*_):
            raise OSError("sem rede")

        cliente = li.ClienteBusca(BUSCA, credencial=self.credencial, transporte=sem_rede)
        with self.assertRaisesRegex(lab_comum.ErroLab, "Não foi possível conectar ao serviço de busca"):
            cliente.obter(li.INDICE, INDICE)
        mensagem, codigo = li.traduzir_erro_ingestao(RuntimeError("x"), SimpleNamespace(busca=BUSCA, conta="c", container="c"))
        self.assertEqual(codigo, lab_comum.CODIGO_INESPERADO)
        self.assertIn("Erro inesperado do script", mensagem)

    def test_a_credencial_do_azure_cli_recebe_o_tenant_informado_e_nenhuma_chave_e_usada(self):
        criadas = []

        def espiao(**opcoes):
            criadas.append(opcoes)
            return CredencialFalsa()

        with mock.patch("azure.identity.AzureCliCredential", side_effect=espiao):
            li.ClienteBusca(BUSCA, "tenant-exemplo", transporte=self.servico).obter(li.INDICE, INDICE)
        self.assertEqual(criadas, [{"tenant_id": "tenant-exemplo", "process_timeout": 30}])
        self.assertNotIn("api-key", {nome.lower() for nome in self.servico.requisicoes[0].cabecalhos})

    def test_sem_az_login_a_credencial_indisponivel_vira_orientacao_de_login_sem_nenhum_pedido(self):
        class CredencialIndisponivel:
            def get_token(self, *_, **__):
                raise type("CredentialUnavailableError", (Exception,), {"__module__": "azure.identity"})("sem sessão")

        with mock.patch.object(li, "abrir_cliente", side_effect=lambda busca, tenant=None, versao=li.VERSAO_API:
                               li.ClienteBusca(busca, credencial=CredencialIndisponivel(), transporte=self.servico, versao_api=versao)):
            codigo, saida = self.rodar("conferir")
        self.assertEqual(codigo, lab_comum.CODIGO_ACESSO)
        self.assertIn("az login", saida)
        self.assertEqual(self.servico.requisicoes, [])

    def test_resposta_que_nao_e_json_e_recusada_com_orientacao(self):
        cliente = li.ClienteBusca(BUSCA, credencial=self.credencial, transporte=lambda *_: li.RespostaHttp(200, b"<html>"))
        with self.assertRaisesRegex(lab_comum.ErroLab, "não é JSON"):
            cliente.obter(li.INDICE, INDICE)

    def test_o_token_e_pedido_uma_vez_e_renovado_perto_de_expirar(self):
        agora = [1000.0]
        emitidos = []

        class Credencial:
            def get_token(self, escopo, **_):
                emitidos.append(escopo)
                return SimpleNamespace(token=TOKEN, expires_on=agora[0] + 600)

        cliente = li.ClienteBusca(BUSCA, credencial=Credencial(), transporte=self.servico, agora=lambda: agora[0])
        cliente.obter(li.INDICE, INDICE)
        cliente.obter(li.INDICE, INDICE)
        self.assertEqual(len(emitidos), 1)
        agora[0] += 500  # restam 100 s, menos que a margem
        cliente.obter(li.INDICE, INDICE)
        self.assertEqual(len(emitidos), 2)

    def test_listagem_pede_top_explicito_e_traz_os_54_trechos_do_l100_sem_paginar(self):
        self.servico.guardar(li.INDICE, INDICE, li.definicao_do_indice(self.parametros()))
        self.servico.documentos[INDICE] = [{"id": f"t{n}", "conteudo": "x"} for n in range(54)]
        cliente = self.cliente()
        itens = li.listar_trechos(cliente, INDICE, ("id", "conteudo"))
        self.assertEqual(len(itens), 54, "mais que a página padrão de 50: sem top explícito, 4 trechos ficariam de fora")
        self.assertEqual(self.servico.requisicoes[-1].corpo["top"], li.LIMITE_LISTAGEM)
        sem_top = cliente.buscar(INDICE, {"search": "*", "select": "id"})
        self.assertEqual((len(sem_top["value"]), "@odata.nextPageParameters" in sem_top), (50, True), "o dublê reproduz a página padrão")

    def test_listagem_pede_os_campos_e_recusa_indices_maiores_que_o_laboratorio(self):
        self.servico.guardar(li.INDICE, INDICE, li.definicao_do_indice(self.parametros()))
        self.servico.documentos[INDICE] = [{"id": "a", "conteudo": "x", "@ignorado": 1}]
        self.assertEqual(li.listar_trechos(self.cliente(), INDICE, ("id", "conteudo")), [{"id": "a", "conteudo": "x"}])
        self.servico.documentos[INDICE] = [{"id": str(n)} for n in range(li.LIMITE_LISTAGEM + 1)]
        with self.assertRaisesRegex(lab_comum.ErroLab, "ou mais"):
            li.listar_trechos(self.cliente(), INDICE, ("id",))
        paginado = li.ClienteBusca(BUSCA, credencial=self.credencial, transporte=lambda *_: li.RespostaHttp(
            200, json.dumps({"value": [{"id": "a"}], "@odata.nextPageParameters": {"top": 1}}).encode("utf-8")))
        with self.assertRaisesRegex(lab_comum.ErroLab, "ou mais"):
            li.listar_trechos(paginado, INDICE, ("id",))

    def test_o_transporte_real_nao_segue_redirecionamentos_nem_reenvia_a_autorizacao(self):
        recebidos = []

        class Manipulador(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                recebidos.append((self.path, self.headers.get("Content-Length"), self.headers.get("Content-Type")))
                self.send_response(202)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def do_GET(self):
                recebidos.append((self.path, self.headers.get("Authorization")))
                if self.path == "/redireciona":
                    self.send_response(302)
                    self.send_header("Location", "/destino")
                    self.end_headers()
                    return
                corpo = b'{"error": {"code": "X", "message": "nao existe"}}'
                self.send_response(404)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(corpo)))
                self.end_headers()
                self.wfile.write(corpo)

            def log_message(self, *_):
                pass

        servidor = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Manipulador)
        threading.Thread(target=servidor.serve_forever, daemon=True).start()
        self.addCleanup(servidor.server_close)
        self.addCleanup(servidor.shutdown)
        base = f"http://127.0.0.1:{servidor.server_address[1]}"
        redirecionada = li.transporte_urllib("GET", f"{base}/redireciona", {"Authorization": "Bearer x"}, None)
        self.assertEqual(redirecionada.status, 302)
        self.assertEqual([caminho for caminho, _ in recebidos], ["/redireciona"], "o destino do redirecionamento não foi consultado")
        ausente = li.transporte_urllib("GET", f"{base}/outro", {"Authorization": "Bearer x", "Accept": "application/json"}, None)
        self.assertEqual((ausente.status, li._ler_erro(ausente.corpo)), (404, ("X", "nao existe")))
        self.assertEqual(ausente.cabecalhos["content-type"], "application/json")
        sem_corpo = li.transporte_urllib("POST", f"{base}/run", {"Authorization": "Bearer x"}, None)
        self.assertEqual(sem_corpo.status, 202)
        self.assertEqual(recebidos[-1], ("/run", "0", None), "POST sem corpo: Content-Length 0 e nenhum Content-Type inventado")


class CriarTests(BaseDeTeste):
    def test_simulacao_so_le_mostra_o_plano_sem_dados_do_ambiente_e_nao_grava(self):
        codigo, saida = self.rodar("criar", *CRIAR)
        self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)
        self.assertEqual([r.metodo for r in self.servico.requisicoes], ["GET"] * 4)
        self.assertEqual(self.servico.objetos, {})
        self.assertIn("SIMULAÇÃO", saida)
        for tipo, nome in OBJETOS:
            self.assertIn(f"[criar     ] {li.ROTULOS[tipo]} '{nome}'", saida)
        self.assertIn("Total: 4 objeto(s): 4 a criar, 0 iguais, 0 divergentes.", saida)
        self.assertIn("exclusões: soft delete nativo do Blob", saida)
        self.assertIn("criado DESABILITADO", saida)
        self.assertIn("Simulação concluída", saida)
        for ambiente in (ASSINATURA, GRUPO, "ResourceId=/subscriptions"):
            self.assertNotIn(ambiente, saida)

    def test_execucao_cria_na_ordem_com_o_indexador_desabilitado_e_sem_executar_nada(self):
        codigo, saida = self.rodar("criar", *CRIAR, "--executar")
        self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)
        escritas = [(r.metodo, r.caminho) for r in self.servico.requisicoes if r.metodo != "GET"]
        self.assertEqual(escritas, [("PUT", f"indexes('{INDICE}')"), ("PUT", f"datasources('{FONTE}')"),
                                    ("PUT", f"skillsets('{SKILLSET}')"), ("PUT", f"indexers('{INDEXADOR}')")])
        for pedido in self.servico.requisicoes:
            if pedido.metodo == "PUT":
                self.assertEqual(pedido.cabecalhos["If-None-Match"], "*", "criar nunca sobrescreve")
        self.assertIs(self.servico.objetos[(li.INDEXADOR, INDEXADOR)]["disabled"], True)
        self.assertEqual(self.servico.execucoes, [], "criar o indexador não pode executá-lo")
        self.assertEqual(saida.count("[CRIADO"), 4)
        self.assertIn("O indexador não foi executado", saida)
        self.assertIn("--etapa executar", saida)
        esperado = li.definicoes_em_ordem(self.parametros())
        for (tipo, nome, definicao), (tipo_guardado, nome_guardado) in zip(esperado, OBJETOS):
            guardado = {k: v for k, v in self.servico.objetos[(tipo_guardado, nome_guardado)].items() if k != "@odata.etag"}
            self.assertEqual(guardado, definicao)

    def test_reexecucao_nao_grava_de_novo_mesmo_com_os_valores_padrao_que_o_servico_acrescenta(self):
        self.criar_objetos()
        codigo, saida = self.rodar("criar", *CRIAR, "--executar")
        self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)
        self.assertEqual([r.metodo for r in self.servico.requisicoes], ["GET"] * 4)
        self.assertIn("4 iguais", saida)
        self.assertIn("nada a fazer", saida)

    def test_depois_de_habilitar_o_indexador_o_plano_continua_igual(self):
        self.criar_objetos()
        self.servico.objetos[(li.INDEXADOR, INDEXADOR)]["disabled"] = False
        codigo, saida = self.rodar("criar", *CRIAR)
        self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)
        self.assertIn("4 iguais", saida)

    def test_barra_final_na_pasta_e_no_endereco_do_modelo_nao_viram_diferenca(self):
        self.criar_objetos()
        self.servico.objetos[(li.FONTE, FONTE)]["container"]["query"] = "vareleira-lar/"
        self.servico.objetos[(li.SKILLSET, SKILLSET)]["skills"][1]["resourceUri"] += "/"
        codigo, saida = self.rodar("criar", *CRIAR)
        self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)
        self.assertIn("4 iguais", saida)

    def test_objeto_divergente_para_mostra_a_diferenca_exata_e_so_troca_com_substituir(self):
        self.criar_objetos()
        self.servico.objetos[(li.SKILLSET, SKILLSET)]["skills"][0]["maximumPageLength"] = 2000
        for opcoes in ((), ("--executar",)):
            codigo, saida = self.rodar("criar", *CRIAR, *opcoes)
            self.assertEqual(codigo, lab_comum.CODIGO_DIVERGENCIA, saida)
            self.assertIn("[divergente] skillset", saida)
            self.assertIn("skills[dividir-em-trechos].maximumPageLength: é 2000 no serviço em vez de 1200", saida)
            self.assertIn("só será substituído com --substituir", saida)
            self.assertIn("[PARADA]", saida)
            self.assertEqual(self.servico.escritas(), [], "sem --substituir nada é alterado")
        self.assertEqual(self.servico.objetos[(li.SKILLSET, SKILLSET)]["skills"][0]["maximumPageLength"], 2000)

    def test_substituir_troca_so_o_divergente_com_o_etag_conferido_e_mantem_o_indexador_desabilitado(self):
        self.criar_objetos()
        self.servico.objetos[(li.SKILLSET, SKILLSET)]["skills"][0]["maximumPageLength"] = 2000
        etag = self.servico.objetos[(li.SKILLSET, SKILLSET)]["@odata.etag"]
        codigo, saida = self.rodar("criar", *CRIAR, "--substituir")
        self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)
        self.assertIn("[substituir] skillset", saida)
        self.assertIn("será substituído (--substituir)", saida)
        self.assertEqual(self.servico.escritas(), [], "a simulação não altera, mesmo com --substituir")
        codigo, saida = self.rodar("criar", *CRIAR, "--substituir", "--executar")
        self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)
        puts = [r for r in self.servico.requisicoes if r.metodo == "PUT"]
        self.assertEqual([r.caminho for r in puts], [f"skillsets('{SKILLSET}')"])
        self.assertEqual(puts[0].cabecalhos["If-Match"], etag)
        self.assertNotIn("If-None-Match", puts[0].cabecalhos)
        self.assertEqual(self.servico.objetos[(li.SKILLSET, SKILLSET)]["skills"][0]["maximumPageLength"], 1200)
        self.assertIn("[SUBSTITUÍDO", saida)
        self.assertIn("--reiniciar", saida, "depois de trocar o skillset, os blobs precisam ser reprocessados")
        self.assertEqual(self.servico.execucoes, [])

    def test_objeto_sem_o_marcador_do_laboratorio_e_divergente_e_o_destino_diferente_tambem(self):
        self.criar_objetos()
        self.servico.objetos[(li.INDICE, INDICE)]["description"] = "criado por outra pessoa"
        codigo, saida = self.rodar("criar", *CRIAR)
        self.assertEqual(codigo, lab_comum.CODIGO_DIVERGENCIA)
        self.assertIn("não traz o marcador do laboratório", saida)
        self.servico.guardar(li.INDICE, INDICE, li.definicao_do_indice(self.parametros()))
        codigo, saida = self.rodar("criar", "--assinatura", ASSINATURA, "--grupo", GRUPO, "--conta", "outraconta123", "--modelos", MODELOS)
        self.assertEqual(codigo, lab_comum.CODIGO_DIVERGENCIA)
        self.assertIn("[divergente] data source", saida)
        self.assertRegex(saida, r'destino \(hash do ResourceId\): é "[0-9a-f]{12}" no serviço em vez de "[0-9a-f]{12}"')
        for ambiente in (ASSINATURA, GRUPO):
            self.assertNotIn(ambiente, saida)

    def test_opcoes_de_uma_etapa_nao_valem_em_outra_e_o_executar_inutil_so_avisa(self):
        for etapa, opcao, valor in (("conferir", "--substituir", None), ("remover", "--reiniciar", None), ("criar", "--reiniciar", None),
                                    ("conferir", "--aguardar", "30"), ("executar", "--substituir", None), ("remover", "--mostrar-definicoes", None)):
            argumentos = [opcao] + ([valor] if valor else [])
            codigo, saida = self.rodar(etapa, *CRIAR, *argumentos)
            self.assertEqual(codigo, lab_comum.CODIGO_USO, (etapa, opcao))
            self.assertIn(f"A opção {opcao} só vale na etapa", saida)
        self.assertEqual(self.servico.requisicoes, [], "o erro de uso vem antes de qualquer acesso")
        codigo, saida = self.rodar("remover", "--executar", "--indice", f"{INDICE}-zzz")
        self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)

    def test_cada_etapa_exige_so_o_que_usa(self):
        codigo, saida = self.rodar("criar")
        self.assertEqual(codigo, lab_comum.CODIGO_USO)
        self.assertIn("A etapa 'criar' exige informar --assinatura, --grupo, --conta, --modelos", saida)
        self.assertEqual(self.servico.requisicoes, [], "o erro de uso vem antes de qualquer acesso")
        codigo, saida = self.rodar("comparar")
        self.assertEqual((codigo, "--modelos" in saida), (lab_comum.CODIGO_USO, True))
        codigo, _ = self.rodar("remover")
        self.assertEqual(codigo, lab_comum.CODIGO_OK, "remover não precisa de assinatura, grupo, conta nem modelos")

    def test_indice_do_l100_e_nomes_de_fora_do_prefixo_sao_recusados_como_destino(self):
        for opcoes in (["--indice", INDICE_L100], ["--indice", "outro-indice"], ["--indice-referencia", INDICE]):
            codigo, saida = self.rodar("criar", *CRIAR, "--executar", *opcoes)
            self.assertEqual(codigo, lab_comum.CODIGO_USO, opcoes)
            self.assertTrue("L200" in saida or "diferentes" in saida, saida)
        self.assertEqual(self.servico.requisicoes, [])

    def test_modelo_e_dimensoes_combinam_e_a_sobreposicao_e_menor_que_o_trecho(self):
        for opcoes in (["--modelo-embeddings", "text-embedding-ada-002", "--dimensoes", "256"], ["--dimensoes", "3000"],
                       ["--sobreposicao", "1200"], ["--tamanho-maximo", "300", "--sobreposicao", "300"]):
            codigo, _ = self.rodar("criar", *CRIAR, *opcoes)
            self.assertEqual(codigo, lab_comum.CODIGO_USO, opcoes)
        self.assertEqual(self.servico.requisicoes, [])

    def test_erro_403_vira_orientacao_sem_vazar_o_token_e_o_servico_nao_e_alterado(self):
        self.servico.falhas[("GET", "datasources")] = (403, "Forbidden", f"sem permissão Bearer {TOKEN}", {})
        codigo, saida = self.rodar("criar", *CRIAR, "--executar")
        self.assertEqual(codigo, lab_comum.CODIGO_ACESSO)
        self.assertIn("Search Service Contributor", saida)
        self.assertEqual(self.servico.escritas(), [])

    def test_erro_do_servico_com_detalhes_mostra_a_mensagem_redigida(self):
        self.servico.falhas[("GET", "datasources")] = (
            400, "InvalidRequest", f"falha em /subscriptions/{ASSINATURA}/resourceGroups/{GRUPO} Bearer {TOKEN}", {})
        codigo, saida = self.rodar("criar", *CRIAR, "--detalhes")
        self.assertEqual(codigo, lab_comum.CODIGO_ACESSO)
        self.assertIn("InvalidRequest", saida)
        for segredo in (ASSINATURA, GRUPO):
            self.assertNotIn(segredo, saida)

    def test_mostrar_definicoes_redige_assinatura_grupo_conta_e_modelos(self):
        codigo, saida = self.rodar("criar", *CRIAR, "--mostrar-definicoes")
        self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)
        self.assertIn(li.RESOURCE_ID_REDIGIDO, saida)
        self.assertIn('"@odata.type": "#Microsoft.Azure.Search.NativeBlobSoftDeleteDeletionDetectionPolicy"', saida)
        self.assertIn('"maximumPageLength": 1200', saida)
        for ambiente in (ASSINATURA, GRUPO, f"https://{MODELOS}"):
            self.assertNotIn(ambiente, saida)

    def test_pasta_vem_do_inventario_e_pode_ser_informada(self):
        self.rodar("criar", *CRIAR, "--executar")
        self.assertEqual(self.servico.objetos[(li.FONTE, FONTE)]["container"], {"name": "base-documental", "query": "vareleira-lar"})
        self.rodar("criar", *CRIAR, "--executar", "--indice", f"{INDICE}-b", "--prefixo", "vareleira-lar/documentos/")
        self.assertEqual(self.servico.objetos[(li.FONTE, f"{INDICE}-b-fonte")]["container"]["query"], "vareleira-lar/documentos")

    def test_a_versao_da_api_vai_em_todos_os_pedidos_e_a_outra_versao_estavel_e_aceita(self):
        self.criar_objetos()
        self.rodar("conferir")
        self.assertEqual(self.servico.violacoes, [])
        self.servico.versao_api = "2025-09-01"
        codigo, saida = self.rodar("criar", *CRIAR, "--versao-api", "2025-09-01")
        self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)
        self.assertIn("API REST 2025-09-01", saida)
        codigo, _ = self.rodar("criar", *CRIAR, "--versao-api", "2024-11-01-preview")
        self.assertEqual(codigo, lab_comum.CODIGO_USO)

    def test_alteracao_concorrente_durante_a_substituicao_para_sem_sobrescrever(self):
        self.criar_objetos()
        self.servico.objetos[(li.FONTE, FONTE)]["container"]["query"] = "outra-pasta"
        original = self.servico.__call__

        def muda_antes_do_put(metodo, url, cabecalhos, corpo):
            if metodo == "PUT":
                self.servico.guardar(li.FONTE, FONTE, {**self.servico.objetos[(li.FONTE, FONTE)], "description": "alterado por outra pessoa"})
            return original(metodo, url, cabecalhos, corpo)

        with mock.patch.object(li, "abrir_cliente", side_effect=lambda busca, tenant=None, versao=li.VERSAO_API:
                               li.ClienteBusca(busca, credencial=self.credencial, transporte=muda_antes_do_put, versao_api=versao)):
            codigo, saida = self.rodar("criar", *CRIAR, "--executar", "--substituir")
        self.assertEqual(codigo, lab_comum.CODIGO_DIVERGENCIA, saida)
        self.assertIn("Nada foi sobrescrito", saida)
        self.assertEqual(self.servico.objetos[(li.FONTE, FONTE)]["description"], "alterado por outra pessoa")


class ExecutarTests(BaseDeTeste):
    def setUp(self):
        super().setUp()
        self.criar_objetos()

    def test_simulacao_nao_habilita_nem_executa(self):
        codigo, saida = self.rodar("executar")
        self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)
        self.assertIn("SIMULAÇÃO", saida)
        self.assertIn("[habilitar ]", saida)
        self.assertEqual(self.servico.escritas(), [])
        self.assertEqual(self.servico.execucoes, [])

    def test_indexador_desabilitado_e_habilitado_e_o_servico_inicia_a_execucao_sem_chamar_run(self):
        codigo, saida = self.rodar("executar", "--executar")
        self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)
        escritas = [(r.metodo, r.caminho) for r in self.servico.escritas()]
        self.assertEqual(escritas, [("PUT", f"indexers('{INDEXADOR}')")], "habilitar é a única escrita; run em indexador desabilitado seria recusado")
        put = next(r for r in self.servico.requisicoes if r.metodo == "PUT")
        self.assertIs(put.corpo["disabled"], False)
        self.assertEqual(put.corpo["dataSourceName"], FONTE, "a definição existente é mantida; só o estado muda")
        self.assertNotIn("@odata.etag", put.corpo)
        self.assertIn("If-Match", put.cabecalhos)
        self.assertEqual(self.servico.execucoes, [INDEXADOR])
        self.assertIn("[HABILITADO]", saida)
        self.assertIn("--etapa conferir", saida)

    def test_indexador_habilitado_e_executado_sob_demanda_e_aguardar_espera_o_fim(self):
        self.assertEqual(self.rodar("executar", "--executar")[0], lab_comum.CODIGO_OK)
        self.servico.concluir_execucoes()
        self.servico.requisicoes.clear()
        self.servico.polls_em_andamento = 2
        codigo, saida = self.rodar("executar", "--executar", "--aguardar", "60")
        self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)
        self.assertEqual([(r.metodo, r.caminho) for r in self.servico.escritas()], [("POST", f"indexers('{INDEXADOR}')/search.run")])
        self.assertEqual(self.relogio.dormidas, [10, 10])
        self.assertIn("Itens processados: 3 · com falha: 0", saida)
        self.assertIn("Execução concluída sem falhas", saida)

    def test_aguardar_sem_valor_usa_o_tempo_padrao_e_so_aceita_valores_limitados(self):
        self.servico.polls_em_andamento = 10 ** 6
        codigo, saida = self.rodar("executar", "--executar", "--aguardar")
        self.assertEqual(codigo, lab_comum.CODIGO_ACESSO)
        self.assertIn(f"por até {li.ESPERA_PADRAO_SEGUNDOS} s", saida)
        self.assertGreaterEqual(sum(self.relogio.dormidas), li.ESPERA_PADRAO_SEGUNDOS - 1)
        for valor in ("5", "1801", "x"):
            self.assertEqual(self.rodar("executar", "--executar", "--aguardar", valor)[0], lab_comum.CODIGO_USO, valor)

    def test_aguardar_tem_tempo_limite_e_diz_que_a_execucao_continua_no_servico(self):
        self.servico.polls_em_andamento = 10 ** 6
        codigo, saida = self.rodar("executar", "--executar", "--aguardar", "30")
        self.assertEqual(codigo, lab_comum.CODIGO_ACESSO)
        self.assertIn("[TEMPO ESGOTADO]", saida)
        self.assertIn("continua no serviço", saida)
        self.assertEqual(self.relogio.t, 30)

    def test_execucao_com_falhas_devolve_divergencia_e_mostra_erros_sem_a_chave_do_documento_nem_ids(self):
        self.servico.resultado_final = {
            "status": "transientFailure", "itemsProcessed": 3, "itemsFailed": 1,
            "errorMessage": f"falha em /subscriptions/{ASSINATURA}/resourceGroups/{GRUPO}",
            "errors": [{"key": "aHR0cHM6Ly9jaGF2ZS1kby1kb2N1bWVudG8=", "name": "Enrichment.AzureOpenAIEmbeddingSkill.#2", "statusCode": 403,
                        "errorMessage": f"Acesso negado a https://{CONTA}.blob.core.windows.net/base-documental/x.md"}],
            "warnings": [{"message": "aviso de teste"}]}
        codigo, saida = self.rodar("executar", "--executar", "--aguardar", "30")
        self.assertEqual(codigo, lab_comum.CODIGO_DIVERGENCIA, saida)
        self.assertIn("Itens processados: 3 · com falha: 1", saida)
        self.assertIn("- erro: Enrichment.AzureOpenAIEmbeddingSkill.#2: HTTP 403 Acesso negado", saida)
        self.assertIn("- aviso: aviso de teste", saida)
        self.assertIn("Execução concluída com falhas", saida)
        for oculto in ("aHR0cHM6", ASSINATURA, GRUPO, CONTA):
            self.assertNotIn(oculto, saida)

    def test_reiniciar_apaga_o_rastreamento_antes_de_habilitar_ou_executar(self):
        codigo, saida = self.rodar("executar", "--executar", "--reiniciar")
        self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)
        escritas = [(r.metodo, r.caminho) for r in self.servico.escritas()]
        self.assertEqual(escritas, [("POST", f"indexers('{INDEXADOR}')/search.reset"), ("PUT", f"indexers('{INDEXADOR}')")])
        self.assertIn("[REINICIADO]", saida)
        simulacao = self.rodar("executar", "--reiniciar")[1]
        self.assertIn("[reiniciar ]", simulacao)

    def test_primeira_execucao_sem_nenhum_item_processado_e_um_alerta_mas_uma_nova_sem_mudancas_e_aceita(self):
        self.servico.resultado_final = {"status": "success", "itemsProcessed": 0, "itemsFailed": 0, "errors": [], "warnings": []}
        codigo, saida = self.rodar("executar", "--executar", "--aguardar", "30")
        self.assertEqual(codigo, lab_comum.CODIGO_DIVERGENCIA, saida)
        self.assertIn("[ATENÇÃO] A primeira execução terminou sem processar nenhum blob", saida)
        self.servico.resultado_final = {"status": "success", "itemsProcessed": 3, "itemsFailed": 0, "errors": [], "warnings": []}
        self.servico.objetos[(li.INDEXADOR, INDEXADOR)]["disabled"] = False
        self.assertEqual(self.rodar("executar", "--executar", "--aguardar", "30")[0], lab_comum.CODIGO_OK)
        self.servico.resultado_final = {"status": "success", "itemsProcessed": 0, "itemsFailed": 0, "errors": [], "warnings": []}
        codigo, saida = self.rodar("executar", "--executar", "--aguardar", "30")
        self.assertEqual(codigo, lab_comum.CODIGO_OK, "depois de uma execução anterior, zero itens significa só que nada mudou")

    def test_execucao_em_andamento_409_e_acompanhada_sem_nova_execucao(self):
        self.assertEqual(self.rodar("executar", "--executar")[0], lab_comum.CODIGO_OK)
        self.servico.em_execucao = True
        self.servico.requisicoes.clear()
        codigo, saida = self.rodar("executar", "--executar")
        self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)
        self.assertIn("[EM EXECUÇÃO]", saida)
        self.servico.falhas[("POST", "search.run")] = (500, "Erro", "interno", {})
        self.assertEqual(self.rodar("executar", "--executar")[0], lab_comum.CODIGO_ACESSO, "só o 409 de execução em andamento é tolerado")

    def test_sem_indexador_ou_sem_o_marcador_do_laboratorio_nao_executa_nada(self):
        self.servico.objetos[(li.INDEXADOR, INDEXADOR)]["description"] = "de outra pessoa"
        codigo, saida = self.rodar("executar", "--executar")
        self.assertEqual(codigo, lab_comum.CODIGO_DIVERGENCIA)
        self.assertIn("marcador do laboratório", saida)
        del self.servico.objetos[(li.INDEXADOR, INDEXADOR)]
        codigo, saida = self.rodar("executar", "--executar")
        self.assertEqual(codigo, lab_comum.CODIGO_DIVERGENCIA)
        self.assertIn("não existe", saida)
        self.assertEqual(self.servico.escritas(), [])
        self.assertEqual(self.servico.execucoes, [])


class ConferirTests(BaseDeTeste):
    def setUp(self):
        super().setUp()
        self.criar_objetos()
        self.servico.documentos[INDICE] = documentos_do_l200(self.inventario)
        self.servico.ultimo[INDEXADOR] = {"status": "success", "startTime": "2026-10-10T10:00:01Z", "endTime": "2026-10-10T10:05:00Z",
                                          "itemsProcessed": 3, "itemsFailed": 0, "errors": [], "warnings": []}
        self.completo = [*CRIAR]

    def test_conferencia_aprovada_reporta_status_itens_falhas_e_campos_preenchidos(self):
        codigo, saida = self.rodar("conferir", *self.completo)
        self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)
        self.assertEqual(self.servico.escritas(), [], "conferir só lê")
        self.assertIn("[OK   ] Objetos do pipeline", saida)
        self.assertIn("[OK   ] Definições dos objetos: os quatro objetos são os definidos por este script", saida)
        self.assertIn("resultado 'success'; itens processados 3; itens com falha 0; erros 0; avisos 0; estado geral 'running'; indexador desabilitado", saida)
        total = len(self.servico.documentos[INDICE])
        self.assertIn(f"{total} trecho(s) em 3 de 3 documento(s) do inventário", saida)
        self.assertIn("documento_id 100%", saida)
        self.assertIn("sintetico 100%", saida)
        self.assertIn("secao 0% e clausulas 0%", saida)
        self.assertIn("Conferência aprovada.", saida)

    def test_conferencia_sugere_verificar_os_metadados_dos_blobs_quando_nenhum_trecho_os_recebeu(self):
        for doc in self.servico.documentos[INDICE]:
            doc.update({"documento_id": None, "versao": None, "produto": None, "sha256": None, "sintetico": None})
        codigo, saida = self.rodar("conferir")
        self.assertEqual(codigo, lab_comum.CODIGO_DIVERGENCIA)
        self.assertIn("[DICA ] Nenhum trecho trouxe os metadados do blob", saida)
        self.assertIn("verificar_documentos.py", saida)

    def test_conferencia_exige_a_deteccao_de_exclusao_nativa_no_data_source(self):
        self.assertIn("[OK   ] Detecção de exclusão", self.rodar("conferir")[1])
        del self.servico.objetos[(li.FONTE, FONTE)]["dataDeletionDetectionPolicy"]
        codigo, saida = self.rodar("conferir")
        self.assertEqual(codigo, lab_comum.CODIGO_DIVERGENCIA)
        self.assertIn("[FALHA] Detecção de exclusão: o data source não tem a política de exclusão nativa", saida)
        self.assertIn("órfãos", saida)

    def test_ultima_execucao_sem_mudancas_com_zero_itens_nao_reprova_a_conferencia(self):
        self.servico.ultimo[INDEXADOR]["itemsProcessed"] = 0
        codigo, saida = self.rodar("conferir")
        self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)
        self.assertIn("Nenhum item processado nesta execução: sem mudanças desde a anterior", saida)

    def test_conferencia_so_com_a_busca_nao_compara_definicoes_mas_confere_o_resto(self):
        codigo, saida = self.rodar("conferir")
        self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)
        self.assertIn("[INFO ] Definições não comparadas", saida)
        self.assertNotIn("Definições dos objetos", saida.replace("Definições não comparadas", ""))

    def test_conferencia_aponta_campos_vazios_fonte_fora_do_inventario_versao_hash_e_conteudo_nao_sintetico(self):
        docs = self.servico.documentos[INDICE]
        docs[0]["documento_id"] = None
        docs[1]["fonte"] = f"https://{CONTA}.blob.core.windows.net/base-documental/segredo/real.md"
        docs[2]["sintetico"] = "false"
        docs[3]["versao"] = "9.9"
        docs[4]["sha256"] = "0" * 64
        docs[5]["conteudo"] = ""
        codigo, saida = self.rodar("conferir", *self.completo)
        self.assertEqual(codigo, lab_comum.CODIGO_DIVERGENCIA, saida)
        for esperado in ("1 trecho(s) sem 'documento_id'", "1 trecho(s) sem 'conteudo'", "fora do inventário", "não está marcado como sintético",
                         "com versão diferente", "sha256 diferente"):
            self.assertIn(esperado, saida)
        self.assertNotIn("segredo/real.md", saida, "fontes fora da lista de permissão não são mostradas")
        self.assertIn("Conferência reprovada", saida)

    def test_conferencia_aponta_documento_do_inventario_sem_trechos(self):
        self.servico.documentos[INDICE] = [d for d in self.servico.documentos[INDICE] if d["documento_id"] != "VLAR-FAQ-1.0"]
        codigo, saida = self.rodar("conferir")
        self.assertEqual(codigo, lab_comum.CODIGO_DIVERGENCIA)
        self.assertIn("documentos do inventário sem trechos: VLAR-FAQ-1.0", saida)
        self.servico.documentos[INDICE] = []
        self.assertIn("o índice não tem nenhum trecho", self.rodar("conferir")[1])

    def test_conferencia_reporta_erros_e_avisos_do_indexador_redigidos(self):
        self.servico.ultimo[INDEXADOR].update({
            "status": "transientFailure", "itemsFailed": 1, "errorMessage": f"erro em /subscriptions/{ASSINATURA}/resourceGroups/{GRUPO}",
            "errors": [{"key": "chave-base64", "name": "Skill.X", "statusCode": 429, "errorMessage": "limite de requisições"}],
            "warnings": [{"message": "aviso 1"}, {"message": "aviso 2"}]})
        codigo, saida = self.rodar("conferir")
        self.assertEqual(codigo, lab_comum.CODIGO_DIVERGENCIA)
        self.assertIn("resultado 'transientFailure'; itens processados 3; itens com falha 1; erros 1; avisos 2", saida)
        self.assertIn("erro: Skill.X: HTTP 429 limite de requisições", saida)
        self.assertIn("aviso: aviso 1", saida)
        for oculto in ("chave-base64", ASSINATURA, GRUPO):
            self.assertNotIn(oculto, saida)

    def test_sem_execucao_ou_sem_objetos_a_conferencia_reprova_com_orientacao(self):
        self.servico.ultimo.clear()
        codigo, saida = self.rodar("conferir")
        self.assertEqual(codigo, lab_comum.CODIGO_DIVERGENCIA)
        self.assertIn("Nenhuma execução registrada", saida)
        for chave in [(li.INDEXADOR, INDEXADOR), (li.SKILLSET, SKILLSET)]:
            del self.servico.objetos[chave]
        codigo, saida = self.rodar("conferir", *self.completo)
        self.assertEqual(codigo, lab_comum.CODIGO_DIVERGENCIA)
        self.assertIn("indexador ausente", saida)
        self.assertIn("[INFO ] Definições não comparadas", saida)
        del self.servico.objetos[(li.INDICE, INDICE)]
        self.assertIn("o índice 'vareleira-lar-l200' não existe", self.rodar("conferir")[1])

    def test_conferencia_detecta_definicao_diferente_e_destino_diferente(self):
        self.servico.objetos[(li.INDICE, INDICE)]["fields"][2]["type"] = "Edm.Int32"
        codigo, saida = self.rodar("conferir", *self.completo)
        self.assertEqual(codigo, lab_comum.CODIGO_DIVERGENCIA)
        self.assertIn("[FALHA] Definições dos objetos: 1 objeto(s) diferente(s) do definido", saida)
        self.assertIn("fields[documento_id].type: é \"Edm.Int32\" no serviço em vez de \"Edm.String\"", saida)

    def test_conferencia_so_seleciona_campos_que_o_indice_tem_e_avisa_do_executar_inutil(self):
        indice = self.servico.objetos[(li.INDICE, INDICE)]
        indice["fields"] = [c for c in indice["fields"] if c["name"] not in ("sha256", "sintetico")]
        codigo, saida = self.rodar("conferir", "--executar")
        self.assertIn("[AVISO] --executar não se aplica à etapa 'conferir'", saida)
        self.assertIn("Compatibilidade com o recuperador do L100", saida)
        self.assertEqual(self.servico.violacoes, [], "o dublê recusa select de campo que o índice não tem")
        self.assertNotEqual(codigo, lab_comum.CODIGO_USO)

    def test_conferencia_reprova_indice_sem_os_campos_do_recuperador(self):
        indice = self.servico.objetos[(li.INDICE, INDICE)]
        indice["fields"] = [c for c in indice["fields"] if c["name"] not in ("secao", "vetor")]
        codigo, saida = self.rodar("conferir")
        self.assertEqual(codigo, lab_comum.CODIGO_DIVERGENCIA)
        self.assertIn("falta o campo 'secao'", saida)
        self.assertIn("falta o campo 'vetor'", saida)


class CompararTests(BaseDeTeste):
    def setUp(self):
        super().setUp()
        self.servico.guardar(li.INDICE, INDICE, li.definicao_do_indice(self.parametros(DIMENSOES)))
        self.servico.guardar(li.INDICE, INDICE_L100, lab_indexacao.definicao_do_indice(INDICE_L100, DIMENSOES))
        self.l100, self.openai = indexar_pacote(self.inventario, BUSCA, MODELOS, DIMENSOES)
        self.l200 = IndiceFalso(INDICE)
        self.docs_l200 = documentos_do_l200(self.inventario)
        self.l200.documentos = {d["id"]: d for d in self.docs_l200}
        self.servico.documentos[INDICE_L100] = [dict(d) for d in self.l100.documentos.values()]
        self.servico.documentos[INDICE] = self.docs_l200
        self.indices = {INDICE_L100: self.l100, INDICE: self.l200}
        self.openai.chamadas.clear()

    def comparar(self, *opcoes, indices=None):
        indices = indices or self.indices
        return self.rodar("comparar", "--modelos", MODELOS, "--dimensoes", str(DIMENSOES), *opcoes,
                          abrir_indice=lambda busca, indice, tenant=None, credencial=None: indices[indice], openai=self.openai)

    def respostas_roteirizadas(self, sem_o_fato_no_l200=()):
        perguntas = lab_indexacao.carregar_perguntas()
        inventario = lab_comum.carregar_inventario(self.inventario)
        blobs = {d.id: d.blob for d in inventario.documentos}
        l100, l200 = {}, {}
        for pergunta in perguntas:
            esperado = pergunta.esperados[0]
            base = {"id": "x", "documento_id": esperado.documento_id, "titulo_documento": "t", "secao": "s", "clausulas": "",
                    "versao": "1.0", "fonte": blobs[esperado.documento_id]}
            l100[pergunta.pergunta] = [{**base, "id": f"L100-{pergunta.id}", "conteudo": f"## Seção\n{esperado.texto_contem}"}]
            texto = "sem o fato" if pergunta.id in sem_o_fato_no_l200 else esperado.texto_contem
            l200[pergunta.pergunta] = [
                {**base, "id": f"L200-{pergunta.id}-a", "conteudo": "outro assunto", "fonte": "https://externo.exemplo/real.md"},
                {**base, "id": f"L200-{pergunta.id}-b", "conteudo": texto,
                 "fonte": f"https://{CONTA}.blob.core.windows.net/base-documental/{blobs[esperado.documento_id]}"}]
        return {INDICE_L100: IndiceRoteirizado(l100), INDICE: IndiceRoteirizado(l200)}

    def test_comparacao_mostra_tamanho_qualidade_e_perguntas_sem_alterar_nada(self):
        codigo, saida = self.comparar()
        self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)
        self.assertEqual(self.servico.escritas(), [])
        self.assertIn("SOMENTE LEITURA", saida)
        self.assertIn(f"{len(self.l100.documentos)}", saida)
        self.assertIn(f"{len(self.docs_l200)}", saida)
        for pergunta in lab_indexacao.carregar_perguntas():
            self.assertIn(f"\n{pergunta.id}. {pergunta.pergunta}", saida)
        self.assertEqual(self.openai.textos_enviados, 6, "um embedding por pergunta de conferência, em um só pedido")
        self.assertEqual(len(self.openai.chamadas), 1)
        self.assertIn("Consumo: um pedido de embeddings com as 6 perguntas, no deployment 'embeddings'", saida)
        self.assertIn("Documentos só no L100: nenhum · só no L200: nenhum", saida)
        self.assertIn("Fontes em comum: 3 de 3", saida)
        self.assertRegex(saida, r"\n  trechos\s+54\s+\d+\n", "o L100 tem mais de 50 trechos: a listagem não pode parar na página padrão")
        self.assertIn("secao preenchida", saida)
        self.assertRegex(saida, r"secao preenchida\s+100%\s+0%")
        self.assertRegex(saida, r"clausulas preenchidas\s+\d+%\s+0%")
        self.assertIn("trecho começa com cabeçalho Markdown", saida)
        self.assertIn("não aprova nem reprova o L200", saida)
        self.assertNotIn(CONTA, saida, "o endereço da conta não é mostrado: as fontes aparecem como caminho do inventário")
        self.assertRegex(saida, r"vareleira-lar/[a-z-]+-v1\.0\.md")

    def test_comparacao_conta_o_fato_esperado_por_indice_e_as_fontes_em_comum(self):
        indices = self.respostas_roteirizadas(sem_o_fato_no_l200=("R3",))
        codigo, saida = self.comparar("--modo", "texto", indices=indices)
        self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)
        self.assertEqual(self.openai.chamadas, [], "no modo texto não há embeddings")
        self.assertIn("Consumo: nenhum embedding (modo texto).", saida)
        self.assertIn("L100 (vareleira-lar-l100): fato esperado na posição 1", saida)
        self.assertIn("L200 (vareleira-lar-l200): fato esperado na posição 2", saida)
        self.assertIn("L200 (vareleira-lar-l200): fato esperado ausente dos 3 primeiros", saida)
        self.assertIn("o fato esperado apareceu entre os 3 primeiros em 6 de 6 perguntas no L100 e em 5 no L200", saida)
        self.assertIn(li.FONTE_FORA_DO_INVENTARIO, saida)
        self.assertNotIn("externo.exemplo", saida, "fonte fora do inventário vira marcador")
        self.assertIn("Fontes em comum entre os 3 primeiros: 1 (vareleira-lar/", saida)
        for consulta in indices[INDICE].consultas:
            self.assertIsNone(consulta[1])
            self.assertEqual(consulta[2], 3)

    def test_modos_vetorial_e_hibrida_enviam_o_vetor_da_pergunta_ao_recuperador_existente(self):
        class Espiao(IndiceFalso):
            consultas = []

            def consultar(self, texto, vetor, k):
                self.consultas.append((texto, None if vetor is None else len(vetor), k))
                return super().consultar(texto, vetor, k)

        self.l200.__class__ = Espiao
        Espiao.consultas = []
        self.assertEqual(self.comparar("--k", "2")[0], lab_comum.CODIGO_OK)
        self.assertEqual({(texto, tamanho, k) for texto, tamanho, k in Espiao.consultas}, {(None, DIMENSOES, 2)})
        Espiao.consultas.clear()
        self.assertEqual(self.comparar("--modo", "hibrida")[0], lab_comum.CODIGO_OK)
        self.assertTrue(all(texto and tamanho == DIMENSOES for texto, tamanho, _ in Espiao.consultas))

    def test_comparacao_usa_so_as_seis_perguntas_de_conferencia_e_nunca_os_conjuntos_do_desafio_06(self):
        caminhos = []
        original = lab_indexacao.carregar_perguntas

        def espiao(caminho=lab_indexacao.PERGUNTAS_PADRAO):
            caminhos.append(caminho)
            return original(caminho)

        with mock.patch.object(lab_indexacao, "carregar_perguntas", espiao):
            self.assertEqual(self.comparar()[0], lab_comum.CODIGO_OK)
        self.assertEqual([str(c) for c in caminhos], [str(lab_indexacao.PERGUNTAS_PADRAO)])
        self.assertNotIn("avaliacao", str(caminhos[0]).replace("conferencia", ""))
        parser = gerenciar_ingestao.criar_parser()
        self.assertNotIn("--conjunto", parser.format_help())
        self.assertNotIn("--perguntas", parser.format_help(), "a lista de perguntas é fixa")

    def test_lista_de_perguntas_precisa_ter_as_seis_fixas_e_fatos_que_existem_nos_documentos(self):
        inventario = lab_comum.carregar_inventario(self.inventario)
        perguntas = lab_indexacao.carregar_perguntas()
        li.validar_perguntas_fixas(perguntas, inventario)
        with self.assertRaisesRegex(lab_comum.ErroLab, "R1, R2, R3, R4, R5, R6"):
            li.validar_perguntas_fixas(perguntas[:5], inventario)
        with self.assertRaisesRegex(lab_comum.ErroLab, "Desafio 06"):
            li.validar_perguntas_fixas([lab_indexacao.PerguntaDeConferencia(f"AJ-{n}", "?", perguntas[0].esperados) for n in range(6)], inventario)
        alterada = [lab_indexacao.PerguntaDeConferencia(p.id, p.pergunta, (lab_indexacao.Esperado(p.esperados[0].documento_id, "texto que não existe"),))
                    if p.id == "R2" else p for p in perguntas]
        with self.assertRaisesRegex(lab_comum.ErroLab, "R2: o texto esperado"):
            li.validar_perguntas_fixas(alterada, inventario)
        desconhecido = [lab_indexacao.PerguntaDeConferencia(p.id, p.pergunta, (lab_indexacao.Esperado("VLAR-XX-9.9", "x"),))
                        if p.id == "R1" else p for p in perguntas]
        with self.assertRaisesRegex(lab_comum.ErroLab, "R1: o documento VLAR-XX-9.9 não está no inventário"):
            li.validar_perguntas_fixas(desconhecido, inventario)

    def test_comparacao_para_quando_um_indice_nao_existe_esta_vazio_ou_nao_e_compativel(self):
        self.servico.documentos[INDICE] = []
        codigo, saida = self.comparar()
        self.assertEqual((codigo, "está vazio" in saida), (lab_comum.CODIGO_DIVERGENCIA, True))
        self.assertEqual(self.openai.chamadas, [], "nenhum embedding é calculado quando a comparação não pode acontecer")
        del self.servico.objetos[(li.INDICE, INDICE)]
        codigo, saida = self.comparar()
        self.assertEqual(codigo, lab_comum.CODIGO_DIVERGENCIA)
        self.assertIn("O índice L200 'vareleira-lar-l200' não existe", saida)
        self.servico.guardar(li.INDICE, INDICE, li.definicao_do_indice(self.parametros(DIMENSOES)))
        del self.servico.objetos[(li.INDICE, INDICE_L100)]
        self.assertIn("Reindexe o L100", self.comparar()[1])
        indice = li.definicao_do_indice(self.parametros(DIMENSOES))
        indice["fields"] = [c for c in indice["fields"] if c["name"] != "versao"]
        self.servico.guardar(li.INDICE, INDICE, indice)
        self.servico.guardar(li.INDICE, INDICE_L100, lab_indexacao.definicao_do_indice(INDICE_L100, DIMENSOES))
        codigo, saida = self.comparar()
        self.assertEqual(codigo, lab_comum.CODIGO_DIVERGENCIA)
        self.assertIn("não é compatível com o recuperador do L100: falta o campo 'versao'", saida)

    def test_dimensoes_diferentes_do_indice_impedem_a_comparacao(self):
        self.servico.guardar(li.INDICE, INDICE, li.definicao_do_indice(self.parametros(1536)))
        codigo, saida = self.comparar()
        self.assertEqual(codigo, lab_comum.CODIGO_DIVERGENCIA)
        self.assertIn(f"tem 1536 dimensões em vez de {DIMENSOES}", saida)


class RemoverTests(BaseDeTeste):
    def setUp(self):
        super().setUp()
        self.criar_objetos()
        self.servico.guardar(li.INDICE, INDICE_L100, lab_indexacao.definicao_do_indice(INDICE_L100, DIMENSOES))
        self.servico.documentos[INDICE_L100] = [{"id": "x"}]

    def test_simulacao_lista_os_quatro_objetos_em_ordem_de_dependencia_e_nao_apaga(self):
        codigo, saida = self.rodar("remover")
        self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)
        self.assertEqual([r.metodo for r in self.servico.requisicoes], ["GET"] * 4)
        self.assertIn("SIMULAÇÃO", saida)
        plano = saida.split("Plano")[1]
        ordem = [plano.index(f"'{nome}'") for nome in (INDEXADOR, SKILLSET, FONTE, INDICE)]
        self.assertEqual(ordem, sorted(ordem))
        self.assertIn("Simulação concluída. Para remover", saida)
        self.assertEqual(len(self.servico.objetos), 5)

    def test_remocao_apaga_so_os_quatro_na_ordem_de_dependencia_e_preserva_o_indice_do_l100(self):
        etags = {chave: valor["@odata.etag"] for chave, valor in self.servico.objetos.items()}
        codigo, saida = self.rodar("remover", "--executar")
        self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)
        apagados = [(r.caminho, r.cabecalhos["If-Match"]) for r in self.servico.requisicoes if r.metodo == "DELETE"]
        self.assertEqual(apagados, [(f"indexers('{INDEXADOR}')", etags[(li.INDEXADOR, INDEXADOR)]),
                                    (f"skillsets('{SKILLSET}')", etags[(li.SKILLSET, SKILLSET)]),
                                    (f"datasources('{FONTE}')", etags[(li.FONTE, FONTE)]),
                                    (f"indexes('{INDICE}')", etags[(li.INDICE, INDICE)])])
        self.assertEqual(list(self.servico.objetos), [(li.INDICE, INDICE_L100)], "o índice do L100 continua, e nada sobrou do L200")
        self.assertEqual(saida.count("[REMOVIDO]"), 4)
        self.assertNotIn(INDICE_L100 + "'", saida.split("Plano")[1].split("Só estes")[0])
        self.assertIn(f"O índice '{INDICE_L100}', a conta de armazenamento", saida)

    def test_remocao_com_sufixo_so_toca_nos_objetos_derivados_dele(self):
        self.rodar("criar", *CRIAR, "--executar", "--indice", f"{INDICE}-b")
        self.servico.requisicoes.clear()
        codigo, saida = self.rodar("remover", "--executar", "--indice", f"{INDICE}-b")
        self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)
        restantes = {nome for _, nome in self.servico.objetos}
        self.assertEqual(restantes, {INDICE, FONTE, SKILLSET, INDEXADOR, INDICE_L100})

    def test_objeto_sem_o_marcador_do_laboratorio_impede_a_remocao_de_todos(self):
        self.servico.objetos[(li.FONTE, FONTE)]["description"] = "de outra pessoa"
        for opcoes in ((), ("--executar",)):
            codigo, saida = self.rodar("remover", *opcoes)
            self.assertEqual(codigo, lab_comum.CODIGO_DIVERGENCIA, saida)
            self.assertIn("[alheio    ]", saida)
            self.assertIn("Nada foi apagado", saida)
        self.assertEqual(self.servico.escritas(), [])
        self.assertEqual(len(self.servico.objetos), 5)

    def test_indices_fora_do_prefixo_do_l200_sao_recusados_antes_de_qualquer_acesso(self):
        for indice in (INDICE_L100, "outro-indice", f"{INDICE}-x-y-z-w", "vareleira-lar-l200_x"):
            codigo, saida = self.rodar("remover", "--executar", "--indice", indice)
            self.assertEqual(codigo, lab_comum.CODIGO_USO, indice)
        self.assertEqual(self.servico.requisicoes, [])
        self.assertEqual(len(self.servico.objetos), 5)

    def test_remocao_e_idempotente_e_retoma_do_que_sobrou(self):
        del self.servico.objetos[(li.INDEXADOR, INDEXADOR)]
        del self.servico.objetos[(li.SKILLSET, SKILLSET)]
        codigo, saida = self.rodar("remover", "--executar")
        self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)
        self.assertEqual(saida.count("(não existe; nada a fazer)"), 2)
        self.assertEqual(saida.count("[REMOVIDO]"), 2)
        codigo, saida = self.rodar("remover", "--executar")
        self.assertEqual(codigo, lab_comum.CODIGO_OK)
        self.assertIn("Nenhum dos objetos existe", saida)

    def test_objeto_alterado_durante_a_remocao_para_sem_apagar_o_que_mudou(self):
        original = self.servico.__call__

        def muda_antes_de_apagar(metodo, url, cabecalhos, corpo):
            if metodo == "DELETE" and "skillsets" in url:
                self.servico.guardar(li.SKILLSET, SKILLSET, {**self.servico.objetos[(li.SKILLSET, SKILLSET)]})
            return original(metodo, url, cabecalhos, corpo)

        with mock.patch.object(li, "abrir_cliente", side_effect=lambda busca, tenant=None, versao=li.VERSAO_API:
                               li.ClienteBusca(busca, credencial=self.credencial, transporte=muda_antes_de_apagar, versao_api=versao)):
            codigo, saida = self.rodar("remover", "--executar")
        self.assertEqual(codigo, lab_comum.CODIGO_DIVERGENCIA, saida)
        self.assertIn("Nada foi apagado neste objeto", saida)
        self.assertIn((li.SKILLSET, SKILLSET), self.servico.objetos)
        self.assertIn((li.INDICE, INDICE), self.servico.objetos, "o índice só sai depois dos que dependem dele")

    def test_erro_403_ao_apagar_vira_orientacao_e_nada_mais_e_apagado(self):
        self.servico.falhas[("DELETE", "datasources")] = (403, "Forbidden", "sem permissão", {})
        codigo, saida = self.rodar("remover", "--executar")
        self.assertEqual(codigo, lab_comum.CODIGO_ACESSO)
        self.assertIn("Search Service Contributor", saida)
        self.assertIn((li.INDICE, INDICE), self.servico.objetos)
        self.assertIn((li.FONTE, FONTE), self.servico.objetos)


if __name__ == "__main__":
    unittest.main()
