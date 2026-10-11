"""Regras do L200 (Desafios 02 e 03): ingestão gerenciada pelo Azure AI Search e comparação com o índice do L100.

No L100, os scripts leem os documentos, dividem em trechos, calculam os embeddings e gravam no índice. No L200, quem faz esse
caminho é o próprio serviço de busca: um indexador lê os blobs, um skillset (conjunto de etapas de processamento) divide o
texto e chama o modelo de embeddings, e uma projeção de índice grava cada trecho (filho) com os dados do documento (pai) em um
índice separado. Este módulo define os quatro objetos, calcula a diferença para o que já existe e fala com a API REST do plano de
dados do serviço de busca, usando só a biblioteca padrão e a identidade do Azure CLI (az login). Nenhuma chave é usada, e nada é
criado, alterado, executado ou apagado sem que quem chama peça.

As definições, o plano, a análise dos trechos e a tradução de erros são funções puras ou recebem o transporte HTTP por
parâmetro: podem ser testadas sem Azure.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import posixpath
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

import lab_acesso
import lab_comum
import lab_indexacao
from lab_comum import ErroLab, Inventario
from lab_indexacao import CRIAR, DIVERGENTE, IGUAL

# --------------------------------------------------------------------------------------
# Constantes
# --------------------------------------------------------------------------------------

# A política de exclusão nativa do Blob só consta na referência estável 2026-04-01; a 2025-09-01 lista apenas a política por
# coluna. Por isso o padrão é a 2026-04-01; a 2025-09-01 fica disponível (--versao-api) para quem quiser testá-la.
VERSAO_API = "2026-04-01"
VERSOES_API = ("2026-04-01", "2025-09-01")
ESCOPO_BUSCA = "https://search.azure.com/.default"
SUFIXO_BUSCA = lab_indexacao.SUFIXO_BUSCA
SUFIXO_MODELOS = lab_indexacao.SUFIXO_MODELOS
TEMPO_LIMITE_HTTP = 60  # segundos por requisição
MARGEM_DO_TOKEN = 120  # segundos antes de o token expirar em que ele é renovado

PREFIXO_L200 = "vareleira-lar-l200"
INDICE_PADRAO = PREFIXO_L200
INDICE_REFERENCIA_PADRAO = lab_indexacao.INDICE_PADRAO
MARCADOR = "vareleira-rag:l200"  # na descrição de cada objeto: prova que o laboratório o criou

MODELO_EMBEDDINGS_PADRAO = "text-embedding-3-small"
DIMENSOES_DOS_MODELOS = {  # (mínimo, máximo) aceitos pela habilidade de embeddings
    "text-embedding-ada-002": (1536, 1536),
    "text-embedding-3-small": (2, 1536),
    "text-embedding-3-large": (2, 3072),
}
SOBREPOSICAO_PADRAO = 100
SOBREPOSICAO_MAXIMA = 1000
IDIOMA_PADRAO = "pt-BR"
POLITICA_DE_EXCLUSAO = "#Microsoft.Azure.Search.NativeBlobSoftDeleteDeletionDetectionPolicy"

# Tipos de objeto: o valor é o nome da coleção na API REST.
INDICE, FONTE, SKILLSET, INDEXADOR = "indexes", "datasources", "skillsets", "indexers"
ROTULOS = {INDICE: "índice", FONTE: "data source", SKILLSET: "skillset", INDEXADOR: "indexador"}

ETAPAS = ("criar", "executar", "conferir", "comparar", "remover")
REMOVER, AUSENTE, ALHEIO = "remover", "ausente", "alheio"

PERGUNTAS_FIXAS = ("R1", "R2", "R3", "R4", "R5", "R6")
CAMPOS_COMPATIVEIS = (*lab_indexacao.IndiceBusca.CAMPOS_DO_RESULTADO, lab_indexacao.CAMPO_VETOR)
CAMPOS_PREENCHIDOS = ("documento_id", "titulo_documento", "conteudo", "fonte", "versao", "produto", "sha256", "sintetico")
CAMPOS_SEM_ORIGEM = ("secao", "clausulas")  # o Text Split não gera seções nem cláusulas
CAMPOS_DA_LISTAGEM = tuple(campo for campo in CAMPOS_COMPATIVEIS if campo != lab_indexacao.CAMPO_VETOR)
CAMPOS_EXTRAS_DO_L200 = ("id_pai", "produto", "sha256", "sintetico")
FONTE_FORA_DO_INVENTARIO = "[fora do inventário]"

INTERVALO_SEGUNDOS = 10
ESPERA_PADRAO_SEGUNDOS = 300
ESPERA_MAXIMA_SEGUNDOS = 1800
LIMITE_LISTAGEM = lab_indexacao.LIMITE_LISTAGEM

_dormir: Callable[[float], None] = time.sleep
_relogio: Callable[[], float] = time.monotonic

_PADRAO_GUID = re.compile(r"[0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}")
_PADRAO_GRUPO = re.compile(r"(?=.{1,90}$)[A-Za-z0-9_().-]*[A-Za-z0-9_()-]")
_PADRAO_INDICE_L200 = re.compile(re.escape(PREFIXO_L200) + r"(?:-[a-z0-9]{1,20}){0,3}")
_PADRAO_NOME_DE_OBJETO = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,126}[a-z0-9])?")
_PADRAO_PREFIXO_BLOB = re.compile(r"[a-z0-9][a-z0-9._-]{0,62}(?:/[a-z0-9][a-z0-9._-]{0,62}){0,3}/?")
_PADRAO_CABECALHO = re.compile(r"^\s{0,3}#{1,6}\s+\S", re.MULTILINE)
_PADRAO_ESPACOS = re.compile(r"\s+")
_PADROES_DE_SEGREDO = (
    (re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]*"), "<token>"),
    (re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]{8,}"), "Bearer <token>"),
    (re.compile(r"(?i)\b(AccountKey|SharedAccessKey|api-key|sig)=[^;&\s\"']+"), r"\1=<segredo>"),
    (_PADRAO_GUID, "<guid>"),
    (re.compile(r"(?i)/resourceGroups/[^/\s;\"']+"), "/resourceGroups/<grupo>"),
    (re.compile(r"(?i)https://[a-z0-9-]+\.blob\.core\.windows\.net"), "https://<conta>.blob.core.windows.net"),
)


# --------------------------------------------------------------------------------------
# Argumentos da linha de comando
# --------------------------------------------------------------------------------------

def _inteiro_entre(minimo: int, maximo: int, descricao: str) -> Callable[[str], int]:
    def validar(valor: str) -> int:
        try:
            numero = int(valor)
        except ValueError:
            numero = None
        if numero is None or not minimo <= numero <= maximo:
            raise argparse.ArgumentTypeError(f"{descricao} (recebido: {valor!r}).")
        return numero

    return validar


def validar_prefixo_blob(valor: str) -> str:
    """Pasta virtual do contêiner, sem a barra final: é o que o data source recebe em `container.query`."""
    if not _PADRAO_PREFIXO_BLOB.fullmatch(valor):
        raise argparse.ArgumentTypeError(
            "A pasta do contêiner deve ter até 4 níveis de letras minúsculas, números, '.', '_' e '-', separados por '/' "
            f"(recebido: {valor!r}).")
    return valor.rstrip("/")


# Os nomes entram em endereços que recebem o token e em objetos que o script pode apagar: só o formato esperado é aceito.
validar_assinatura = lab_comum.criar_validador(
    _PADRAO_GUID, "A assinatura deve ser um GUID, como o que 'az account show --query id -o tsv' mostra")
validar_grupo = lab_comum.criar_validador(
    _PADRAO_GRUPO, "O grupo de recursos deve ter até 90 caracteres: letras, números, '_', '(', ')', '-' e '.', sem terminar em '.'")
validar_indice_l200 = lab_comum.criar_validador(
    _PADRAO_INDICE_L200,
    f"O índice do L200 deve ser '{PREFIXO_L200}', com no máximo 3 sufixos de letras minúsculas e números ligados por hífen "
    f"(como '{PREFIXO_L200}-teste'). O índice do L100 nunca é alterado por este script")
validar_modelo_embeddings = lab_comum.criar_validador(
    re.compile("|".join(re.escape(nome) for nome in DIMENSOES_DOS_MODELOS)),
    "O modelo deve ser um destes: " + ", ".join(DIMENSOES_DOS_MODELOS))
validar_sobreposicao = _inteiro_entre(0, SOBREPOSICAO_MAXIMA, f"A sobreposição deve ser um número de 0 a {SOBREPOSICAO_MAXIMA} caracteres")
validar_espera = _inteiro_entre(
    INTERVALO_SEGUNDOS, ESPERA_MAXIMA_SEGUNDOS, f"A espera deve ser um número de {INTERVALO_SEGUNDOS} a {ESPERA_MAXIMA_SEGUNDOS} segundos")

_OPCOES_DAS_ETAPAS = {
    "criar": ("busca", "assinatura", "grupo", "conta", "modelos"),
    "executar": ("busca",),
    "conferir": ("busca",),
    "comparar": ("busca", "modelos"),
    "remover": ("busca",),
}
_AJUDA_DAS_OPCOES = {
    "busca": "nome do serviço de busca (saída nomeBusca da implantação)",
    "assinatura": "ID da assinatura Azure, um GUID ('az account show --query id -o tsv')",
    "grupo": "nome do grupo de recursos da conta de armazenamento",
    "conta": "nome da conta de armazenamento (saída nomeConta da implantação)",
    "modelos": "nome do recurso de modelos (saída nomeModelos da implantação)",
}


def exigir_opcoes(args: argparse.Namespace) -> None:
    """Cada etapa exige só o que usa: `remover`, por exemplo, não precisa saber de conta, assinatura nem modelos."""
    faltam = [opcao for opcao in _OPCOES_DAS_ETAPAS[args.etapa] if not getattr(args, opcao, None)]
    if faltam:
        detalhes = "; ".join(f"--{opcao}: {_AJUDA_DAS_OPCOES[opcao]}" for opcao in faltam)
        raise ErroLab(f"A etapa '{args.etapa}' exige informar {', '.join('--' + opcao for opcao in faltam)} ({detalhes}).")


_OPCOES_POR_ETAPA = {
    "substituir": ("criar",), "mostrar_definicoes": ("criar",), "reiniciar": ("executar",), "aguardar": ("executar",),
}


def validar_combinacoes(args: argparse.Namespace) -> None:
    """Confere o que depende de mais de uma opção. Roda antes de qualquer acesso ao Azure."""
    for opcao, etapas in _OPCOES_POR_ETAPA.items():
        if getattr(args, opcao, None) not in (None, False) and args.etapa not in etapas:
            raise ErroLab(f"A opção --{opcao.replace('_', '-')} só vale na etapa {' ou '.join(etapas)}, não na etapa '{args.etapa}'.")
    if args.indice == args.indice_referencia:
        raise ErroLab("O índice do L200 e o de referência precisam ser diferentes: o índice do L100 nunca é alterado.")
    minimo, maximo = DIMENSOES_DOS_MODELOS[args.modelo_embeddings]
    if not minimo <= args.dimensoes <= maximo:
        raise ErroLab(f"O modelo '{args.modelo_embeddings}' aceita de {minimo} a {maximo} dimensões; recebido: {args.dimensoes}.")
    if args.sobreposicao >= args.tamanho_maximo:
        raise ErroLab("A sobreposição precisa ser menor que o tamanho máximo do trecho.")


# --------------------------------------------------------------------------------------
# Nomes e parâmetros
# --------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Nomes:
    """Os quatro objetos do laboratório. Todos derivam do nome do índice, que precisa ter o prefixo do L200."""

    indice: str
    fonte: str
    skillset: str
    indexador: str

    def em_ordem_de_criacao(self) -> tuple[tuple[str, str], ...]:
        return ((INDICE, self.indice), (FONTE, self.fonte), (SKILLSET, self.skillset), (INDEXADOR, self.indexador))

    def em_ordem_de_remocao(self) -> tuple[tuple[str, str], ...]:
        """Quem depende sai primeiro: o indexador usa a fonte, o skillset e o índice."""
        return ((INDEXADOR, self.indexador), (SKILLSET, self.skillset), (FONTE, self.fonte), (INDICE, self.indice))


def nomes_dos_objetos(indice: str) -> Nomes:
    if not _PADRAO_INDICE_L200.fullmatch(indice):
        raise ErroLab(f"O nome '{indice}' não é um índice do L200 (prefixo '{PREFIXO_L200}'): nada será criado nem apagado com ele.")
    return Nomes(indice, f"{indice}-fonte", f"{indice}-skillset", f"{indice}-indexador")


def _formatar_resource_id(assinatura: str, grupo: str, conta: str) -> str:
    return f"ResourceId=/subscriptions/{assinatura}/resourceGroups/{grupo}/providers/Microsoft.Storage/storageAccounts/{conta}/;"


RESOURCE_ID_REDIGIDO = _formatar_resource_id("<assinatura>", "<grupo>", "<conta>")


def construir_resource_id(assinatura: str, grupo: str, conta: str) -> str:
    """Cadeia de conexão do data source por identidade gerenciada: identifica a conta e não contém chave nenhuma."""
    for valor, padrao, rotulo in ((assinatura, _PADRAO_GUID, "assinatura"), (grupo, _PADRAO_GRUPO, "grupo"),
                                  (conta, re.compile(r"[a-z0-9]{3,24}"), "conta")):
        if not padrao.fullmatch(valor or ""):
            raise ErroLab(f"Valor inválido para {rotulo}: o ResourceId do Blob Storage não pode ser montado.")
    return _formatar_resource_id(assinatura, grupo, conta)


@dataclass(frozen=True)
class Parametros:
    nomes: Nomes
    assinatura: str
    grupo: str
    conta: str
    container: str
    prefixo: str
    modelos: str
    deployment: str
    modelo_embeddings: str
    dimensoes: int
    tamanho_maximo: int
    sobreposicao: int
    # Variações do L300 (acesso documental e execução privada). Os padrões mantêm as definições do L200 como sempre foram.
    marcador: str = MARCADOR  # na descrição de cada objeto: prova de quem o criou
    nivel: str = "L200"
    acesso: bool = False  # acrescenta o campo `acesso` ao índice e o projeta do metadado `acesso` do blob
    privado: bool | None = None  # None: não define o ambiente de execução; True: "private"; False: "standard"
    intervalo: str | None = None  # agenda do indexador (ISO 8601, como PT2H); None: sem agenda

    @property
    def resource_id(self) -> str:
        return construir_resource_id(self.assinatura, self.grupo, self.conta)

    @property
    def destino(self) -> str:
        """Impressão curta do ResourceId. O serviço não devolve a cadeia de conexão, então ela fica na descrição só como hash."""
        return hashlib.sha256(self.resource_id.lower().encode("utf-8")).hexdigest()[:12]


def prefixo_do_inventario(inventario: Inventario) -> str:
    """Pasta comum dos blobs do inventário: limita o indexador aos documentos que o laboratório conhece."""
    pastas = [posixpath.dirname(documento.blob) for documento in inventario.documentos]
    comum = posixpath.commonpath(pastas) if all(pastas) else ""
    if not comum:
        raise ErroLab("Os blobs do inventário não estão em uma pasta comum do contêiner. Informe a pasta com --prefixo.")
    return comum


# --------------------------------------------------------------------------------------
# Definição dos objetos (API REST do plano de dados)
# --------------------------------------------------------------------------------------

def _descricao(p: Parametros, texto: str, extra: str = "") -> str:
    return f"{texto} [{p.marcador}{extra}]"


def definicao_do_indice(p: Parametros) -> dict[str, Any]:
    """Índice de trechos compatível com o recuperador do L100: mesmos campos de resultado e mesmo perfil vetorial."""

    def campo(nome: str, *, chave: bool = False, pesquisavel: bool = False, filtravel: bool = False,
              analisador: str | None = None) -> dict[str, Any]:
        definicao: dict[str, Any] = {
            "name": nome, "type": "Edm.String", "key": chave, "searchable": pesquisavel, "filterable": filtravel,
            "sortable": False, "facetable": False, "retrievable": True,
        }
        if analisador:
            definicao["analyzer"] = analisador
        return definicao

    return {
        "name": p.nomes.indice,
        "description": _descricao(p, f"Laboratorio Vareleira RAG ({p.nivel}): trechos gerados pelo indexador do Azure AI Search"),
        "fields": [
            # A chave de um índice com projeção precisa ser texto com o analisador keyword.
            campo("id", chave=True, pesquisavel=True, filtravel=True, analisador="keyword"),
            campo("id_pai", filtravel=True),
            campo("documento_id", filtravel=True),
            campo("titulo_documento", pesquisavel=True, analisador=lab_indexacao.ANALISADOR),
            campo("produto", filtravel=True),
            campo("versao", filtravel=True),
            campo("secao", pesquisavel=True, analisador=lab_indexacao.ANALISADOR),
            campo("clausulas"),
            campo("conteudo", pesquisavel=True, analisador=lab_indexacao.ANALISADOR),
            campo("fonte", filtravel=True),
            campo("sha256"),
            campo("sintetico", filtravel=True),
            # L300: classe de acesso do documento (texto filtrável), projetada do metadado `acesso` do blob. Sem coleção nem delimitador.
            *([campo(lab_acesso.CAMPO_ACESSO, filtravel=True)] if p.acesso else []),
            {
                "name": lab_indexacao.CAMPO_VETOR, "type": "Collection(Edm.Single)", "key": False, "searchable": True,
                "filterable": False, "sortable": False, "facetable": False, "retrievable": False, "stored": False,
                "dimensions": p.dimensoes, "vectorSearchProfile": lab_indexacao.PERFIL_VETORIAL,
            },
        ],
        "vectorSearch": {
            "algorithms": [{"name": lab_indexacao.ALGORITMO_VETORIAL, "kind": "hnsw", "hnswParameters": {"metric": "cosine"}}],
            "profiles": [{"name": lab_indexacao.PERFIL_VETORIAL, "algorithm": lab_indexacao.ALGORITMO_VETORIAL}],
        },
    }


def definicao_da_fonte(p: Parametros) -> dict[str, Any]:
    """Data source do Blob Storage por identidade gerenciada (ResourceId, sem chave), restrito à pasta do inventário."""
    return {
        "name": p.nomes.fonte,
        "description": _descricao(p, f"Laboratorio Vareleira RAG ({p.nivel}): documentos sinteticos no Blob Storage", f" destino={p.destino}"),
        "type": "azureblob",
        "credentials": {"connectionString": p.resource_id},
        "container": {"name": p.container, "query": p.prefixo},
        # Precisa valer desde a primeira execução: sem ela, excluir um blob deixa trechos órfãos no índice.
        "dataDeletionDetectionPolicy": {"@odata.type": POLITICA_DE_EXCLUSAO},
    }


def definicao_do_skillset(p: Parametros) -> dict[str, Any]:
    """Skillset que divide o texto (Text Split) e gera os embeddings; a projeção grava cada trecho como documento do índice."""
    nomes_dos_metadados = ("documento_id", "versao", "produto", "sha256", "sintetico", *((lab_acesso.CAMPO_ACESSO,) if p.acesso else ()))
    campos_dos_documentos = [(nome, f"/document/{nome}") for nome in nomes_dos_metadados]
    return {
        "name": p.nomes.skillset,
        "description": _descricao(p, f"Laboratorio Vareleira RAG ({p.nivel}): divide o texto e gera embeddings"),
        "skills": [
            {
                "@odata.type": "#Microsoft.Skills.Text.SplitSkill",
                "name": "dividir-em-trechos",
                "description": f"Paginas de ate {p.tamanho_maximo} caracteres, com sobreposicao de {p.sobreposicao}.",
                "context": "/document",
                "defaultLanguageCode": IDIOMA_PADRAO,
                "textSplitMode": "pages",
                "maximumPageLength": p.tamanho_maximo,
                "pageOverlapLength": p.sobreposicao,
                "inputs": [{"name": "text", "source": "/document/content"}],
                "outputs": [{"name": "textItems", "targetName": "pages"}],
            },
            {
                "@odata.type": "#Microsoft.Skills.Text.AzureOpenAIEmbeddingSkill",
                "name": "gerar-embeddings",
                "description": "Chama o deployment de embeddings com a identidade gerenciada do servico de busca (sem chave).",
                "context": "/document/pages/*",
                "resourceUri": f"https://{p.modelos}.{SUFIXO_MODELOS}",
                "deploymentId": p.deployment,
                "modelName": p.modelo_embeddings,
                "dimensions": p.dimensoes,
                "inputs": [{"name": "text", "source": "/document/pages/*"}],
                "outputs": [{"name": "embedding", "targetName": lab_indexacao.CAMPO_VETOR}],
            },
        ],
        "indexProjections": {
            "selectors": [{
                "targetIndexName": p.nomes.indice,
                "parentKeyFieldName": "id_pai",
                "sourceContext": "/document/pages/*",
                # Cada campo do índice precisa de um mapeamento explícito, menos a chave e o campo do pai.
                "mappings": [
                    {"name": "conteudo", "source": "/document/pages/*"},
                    {"name": lab_indexacao.CAMPO_VETOR, "source": f"/document/pages/*/{lab_indexacao.CAMPO_VETOR}"},
                    *({"name": nome, "source": origem} for nome, origem in campos_dos_documentos),
                    {"name": "titulo_documento", "source": "/document/metadata_storage_name"},
                    {"name": "fonte", "source": "/document/metadata_storage_path"},
                ],
            }],
            "parameters": {"projectionMode": "skipIndexingParentDocuments"},
        },
    }


def definicao_do_indexador(p: Parametros) -> dict[str, Any]:
    """Indexador criado desabilitado: criar ou atualizar um indexador o executa na hora, e a execução é uma etapa à parte.

    No L300, `privado` define o ambiente de execução ("private" para sair pelas conexões privadas compartilhadas da busca) e
    `intervalo` acrescenta uma agenda; sem ele, o indexador não tem agenda e só roda sob demanda.
    """
    configuracao: dict[str, Any] = {"dataToExtract": "contentAndMetadata", "parsingMode": "text", "indexedFileNameExtensions": ".md"}
    if p.privado is not None:
        configuracao["executionEnvironment"] = "private" if p.privado else "standard"
    definicao: dict[str, Any] = {
        "name": p.nomes.indexador,
        "description": _descricao(p, f"Laboratorio Vareleira RAG ({p.nivel}): le os blobs e grava os trechos no indice"),
        "dataSourceName": p.nomes.fonte,
        "skillsetName": p.nomes.skillset,
        "targetIndexName": p.nomes.indice,
        "disabled": True,
        "parameters": {
            "maxFailedItems": 0,
            "maxFailedItemsPerBatch": 0,
            "configuration": configuracao,
        },
    }
    if p.intervalo:
        definicao["schedule"] = {"interval": p.intervalo}
    return definicao


def definicoes_em_ordem(p: Parametros) -> list[tuple[str, str, dict[str, Any]]]:
    """(tipo, nome, definição) na ordem de criação: o índice e a fonte existem antes do skillset e do indexador que os usam."""
    return [
        (INDICE, p.nomes.indice, definicao_do_indice(p)),
        (FONTE, p.nomes.fonte, definicao_da_fonte(p)),
        (SKILLSET, p.nomes.skillset, definicao_do_skillset(p)),
        (INDEXADOR, p.nomes.indexador, definicao_do_indexador(p)),
    ]


def validar_consistencia(p: Parametros) -> None:
    """Confere que as quatro definições combinam entre si. Falha aqui é defeito do script, não do ambiente."""
    indice, skillset, indexador = definicao_do_indice(p), definicao_do_skillset(p), definicao_do_indexador(p)
    campos = {campo["name"]: campo for campo in indice["fields"]}
    problemas: list[str] = []
    chaves = [campo for campo in indice["fields"] if campo["key"]]
    if len(chaves) != 1 or chaves[0].get("analyzer") != "keyword":
        problemas.append("a chave do índice deve ser única e usar o analisador keyword")
    seletor = skillset["indexProjections"]["selectors"][0]
    pai = campos.get(seletor["parentKeyFieldName"])
    if pai is None or pai["type"] != "Edm.String" or not pai["filterable"] or pai["key"]:
        problemas.append("o campo do pai deve ser texto, filtrável e diferente da chave")
    if seletor["targetIndexName"] != indice["name"] or indexador["targetIndexName"] != indice["name"]:
        problemas.append("a projeção e o indexador devem apontar para o mesmo índice")
    mapeados = {mapeamento["name"] for mapeamento in seletor["mappings"]}
    if mapeados - set(campos):
        problemas.append("a projeção mapeia campos que o índice não tem: " + ", ".join(sorted(mapeados - set(campos))))
    sem_mapeamento = set(campos) - mapeados - {chaves[0]["name"] if chaves else "", seletor["parentKeyFieldName"], *CAMPOS_SEM_ORIGEM}
    if sem_mapeamento:
        problemas.append("campos do índice sem mapeamento na projeção: " + ", ".join(sorted(sem_mapeamento)))
    faltam = [campo for campo in CAMPOS_COMPATIVEIS if campo not in campos]
    if faltam:
        problemas.append("faltam campos do recuperador do L100: " + ", ".join(faltam))
    vetor = campos[lab_indexacao.CAMPO_VETOR]
    embedding = next(habilidade for habilidade in skillset["skills"] if "Embedding" in habilidade["@odata.type"])
    if vetor["dimensions"] != embedding["dimensions"]:
        problemas.append("as dimensões do campo vetorial e as da habilidade de embeddings devem ser iguais")
    nomes = (indexador["dataSourceName"], indexador["skillsetName"], indexador["targetIndexName"])
    if nomes != (p.nomes.fonte, p.nomes.skillset, p.nomes.indice):
        problemas.append("o indexador deve apontar para a fonte, o skillset e o índice do laboratório")
    if p.acesso:
        acesso = campos.get(lab_acesso.CAMPO_ACESSO)
        if acesso is None or acesso["type"] != "Edm.String" or not acesso["filterable"] or acesso["searchable"] or acesso["key"]:
            problemas.append("o campo de acesso deve ser texto, filtrável, não pesquisável e diferente da chave")
        origem = next((mapeamento["source"] for mapeamento in seletor["mappings"] if mapeamento["name"] == lab_acesso.CAMPO_ACESSO), None)
        if origem != f"/document/{lab_acesso.CAMPO_ACESSO}":
            problemas.append("o campo de acesso deve ser projetado do metadado 'acesso' do blob")
    if problemas:
        raise ErroLab(f"Definições do {p.nivel} inconsistentes (defeito do script; use --detalhes e abra uma issue):\n  - "
                      + "\n  - ".join(problemas), lab_comum.CODIGO_INESPERADO)


def validar_parametros(p: Parametros) -> None:
    """Valores de linha de comando já validados individualmente; aqui, o que depende de mais de um deles."""
    minimo, maximo = DIMENSOES_DOS_MODELOS[p.modelo_embeddings]
    if not minimo <= p.dimensoes <= maximo:
        raise ErroLab(f"O modelo '{p.modelo_embeddings}' aceita de {minimo} a {maximo} dimensões; recebido: {p.dimensoes}.")
    if p.sobreposicao >= p.tamanho_maximo:
        raise ErroLab("A sobreposição precisa ser menor que o tamanho máximo do trecho.")
    validar_consistencia(p)


# --------------------------------------------------------------------------------------
# Redação: nada do ambiente em tela, em plano ou em mensagem
# --------------------------------------------------------------------------------------

def redigir_texto(texto: Any) -> str:
    """Troca tokens, chaves, GUIDs, grupos de recursos e endereços de conta por marcadores."""
    resultado = str(texto or "")
    for padrao, substituto in _PADROES_DE_SEGREDO:
        resultado = padrao.sub(substituto, resultado)
    return resultado


def redigir_definicao(definicao: Mapping[str, Any]) -> dict[str, Any]:
    """Cópia da definição para mostrar em tela: sem assinatura, grupo, conta nem recurso de modelos."""
    copia = copy.deepcopy(dict(definicao))
    credenciais = copia.get("credentials")
    if isinstance(credenciais, dict) and credenciais.get("connectionString"):
        credenciais["connectionString"] = RESOURCE_ID_REDIGIDO
    for habilidade in copia.get("skills") or ():
        if "resourceUri" in habilidade:
            habilidade["resourceUri"] = f"https://<modelos>.{SUFIXO_MODELOS}"
    return copia


# --------------------------------------------------------------------------------------
# Plano: o que existe, o que falta e o que diverge
# --------------------------------------------------------------------------------------

_IGNORADAS = ("@odata.etag", "@odata.context")
_LISTAS_EXATAS = ("fields", "skills", "mappings", "algorithms", "profiles")
ROTULO_DO_DESTINO = "destino (hash do ResourceId)"


def _mostrar(valor: Any, limite: int = 90) -> str:
    texto = json.dumps(valor, ensure_ascii=False)
    return texto if len(texto) <= limite else texto[: limite - 1] + "…"


def _normalizar(tipo: str, definicao: Mapping[str, Any]) -> dict[str, Any]:
    copia = {chave: copy.deepcopy(valor) for chave, valor in definicao.items() if chave not in _IGNORADAS}
    if tipo == FONTE:
        copia.pop("credentials", None)  # o serviço não devolve a cadeia de conexão: o destino é conferido pelo hash da descrição
        descricao = str(copia.get("description") or "")
        destino = re.search(r" destino=([0-9a-f]{12})", descricao)
        copia["description"] = re.sub(r" destino=[0-9a-f]{12}", "", descricao)
        copia[ROTULO_DO_DESTINO] = destino.group(1) if destino else None
        container = copia.get("container")
        if isinstance(container, dict) and isinstance(container.get("query"), str):
            container["query"] = container["query"].strip("/")
    if tipo == SKILLSET:
        for habilidade in copia.get("skills") or ():
            if isinstance(habilidade, dict) and isinstance(habilidade.get("resourceUri"), str):
                habilidade["resourceUri"] = habilidade["resourceUri"].rstrip("/")
    if tipo == INDEXADOR:
        copia.pop("disabled", None)  # habilitar é a etapa executar; depois dela o valor deixa de ser o do modelo
    return copia


def _comparar(esperado: Any, atual: Any, caminho: str, saida: list[str], chave: str = "") -> None:
    """Compara só o que a definição esperada declara: o que o serviço acrescenta (valores padrão) não conta como diferença."""
    if isinstance(esperado, dict):
        if not isinstance(atual, dict):
            saida.append(f"{caminho or '/'}: o serviço tem {_mostrar(atual)} em vez de um objeto")
            return
        for nome, valor in esperado.items():
            local = f"{caminho}.{nome}" if caminho else nome
            if nome not in atual or (atual[nome] is None and valor is not None):
                saida.append(f"{local}: ausente no serviço (esperado {_mostrar(valor)})")
                continue
            _comparar(valor, atual[nome], local, saida, nome)
    elif isinstance(esperado, list):
        if not isinstance(atual, list):
            saida.append(f"{caminho}: o serviço tem {_mostrar(atual)} em vez de uma lista")
        elif esperado and all(isinstance(item, dict) and "name" in item for item in (*esperado, *atual)):
            por_nome = {item["name"]: item for item in atual}
            for item in esperado:
                local = f"{caminho}[{item['name']}]"
                if item["name"] not in por_nome:
                    saida.append(f"{local}: ausente no serviço")
                else:
                    _comparar(item, por_nome[item["name"]], local, saida)
            if chave in _LISTAS_EXATAS:
                previstos = {item["name"] for item in esperado}
                saida.extend(f"{caminho}[{nome}]: existe no serviço, mas a definição não o prevê" for nome in por_nome if nome not in previstos)
        else:
            if len(esperado) != len(atual):
                saida.append(f"{caminho}: {len(atual)} item(ns) no serviço em vez de {len(esperado)}")
            for posicao, (item_esperado, item_atual) in enumerate(zip(esperado, atual)):
                _comparar(item_esperado, item_atual, f"{caminho}[{posicao}]", saida)
    elif esperado != atual:
        saida.append(f"{caminho}: é {_mostrar(atual)} no serviço em vez de {_mostrar(esperado)}")


def diferencas_de_definicao(tipo: str, esperado: Mapping[str, Any], atual: Mapping[str, Any]) -> list[str]:
    """Lista exata do que o objeto existente tem de diferente da definição. Lista vazia: o objeto é o esperado."""
    saida: list[str] = []
    _comparar(_normalizar(tipo, esperado), _normalizar(tipo, atual), "", saida)
    return saida


def objeto_do_laboratorio(atual: Mapping[str, Any], marcador: str = MARCADOR) -> bool:
    return marcador in str(atual.get("description") or "")


@dataclass(frozen=True)
class AcaoObjeto:
    tipo: str
    nome: str
    definicao: dict[str, Any]
    estado: str
    diferencas: tuple[str, ...] = ()
    etag: str | None = None
    proprio: bool = True


def planejar_objetos(parametros: Parametros, atuais: Mapping[tuple[str, str], Mapping[str, Any] | None]) -> list[AcaoObjeto]:
    """Compara as definições com o que o serviço tem (tipo, nome -> objeto ou None). Somente leitura."""
    acoes = []
    for tipo, nome, definicao in definicoes_em_ordem(parametros):
        atual = atuais.get((tipo, nome))
        if atual is None:
            acoes.append(AcaoObjeto(tipo, nome, definicao, CRIAR))
            continue
        proprio = objeto_do_laboratorio(atual, parametros.marcador)
        diferencas = diferencas_de_definicao(tipo, definicao, atual)
        if not proprio:
            diferencas.insert(0, "o objeto existente não traz o marcador do laboratório na descrição: não foi criado por este script")
        acoes.append(AcaoObjeto(tipo, nome, definicao, DIVERGENTE if diferencas else IGUAL, tuple(diferencas),
                                atual.get("@odata.etag"), proprio))
    return acoes


@dataclass(frozen=True)
class AcaoRemocao:
    tipo: str
    nome: str
    estado: str  # REMOVER, AUSENTE ou ALHEIO
    etag: str | None = None


def planejar_remocao(nomes: Nomes, atuais: Mapping[tuple[str, str], Mapping[str, Any] | None],
                     marcador: str = MARCADOR) -> list[AcaoRemocao]:
    """Só entram na remoção os quatro objetos derivados do índice; os que não trazem o marcador do laboratório são recusados."""
    acoes = []
    for tipo, nome in nomes.em_ordem_de_remocao():
        atual = atuais.get((tipo, nome))
        if atual is None:
            acoes.append(AcaoRemocao(tipo, nome, AUSENTE))
        elif not objeto_do_laboratorio(atual, marcador):
            acoes.append(AcaoRemocao(tipo, nome, ALHEIO))
        else:
            acoes.append(AcaoRemocao(tipo, nome, REMOVER, atual.get("@odata.etag")))
    return acoes


# --------------------------------------------------------------------------------------
# Cliente REST do serviço de busca
# --------------------------------------------------------------------------------------

@dataclass(frozen=True)
class RespostaHttp:
    status: int
    corpo: bytes = b""
    cabecalhos: Mapping[str, str] = field(default_factory=dict)  # nomes em minúsculas


Transporte = Callable[[str, str, Mapping[str, str], bytes | None], RespostaHttp]


class _SemRedirecionamento(urllib.request.HTTPRedirectHandler):
    """Um redirecionamento reenviaria o cabeçalho de autorização ao novo endereço: por segurança, nunca é seguido."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001 - assinatura da biblioteca padrão
        return None


_ABRIDOR = urllib.request.build_opener(_SemRedirecionamento)


def transporte_urllib(metodo: str, url: str, cabecalhos: Mapping[str, str], corpo: bytes | None) -> RespostaHttp:
    pedido = urllib.request.Request(url, data=corpo, method=metodo, headers=dict(cabecalhos))
    try:
        with _ABRIDOR.open(pedido, timeout=TEMPO_LIMITE_HTTP) as resposta:
            return RespostaHttp(resposta.status, resposta.read(), {nome.lower(): valor for nome, valor in resposta.headers.items()})
    except urllib.error.HTTPError as erro:
        try:
            conteudo = erro.read()
        finally:
            erro.close()
        return RespostaHttp(erro.code, conteudo, {nome.lower(): valor for nome, valor in erro.headers.items()})


class ErroServicoBusca(Exception):
    """Resposta de erro do serviço de busca. A mensagem do serviço só aparece com --detalhes e sempre redigida."""

    def __init__(self, status: int, codigo: str, mensagem: str, metodo: str, rota: str, tipo: str = "", nome: str = "",
                 espera: str | None = None, id_requisicao: str = ""):
        self.status, self.codigo, self.mensagem = status, codigo, redigir_texto(mensagem)
        self.metodo, self.rota, self.tipo, self.nome, self.espera, self.id_requisicao = metodo, rota, tipo, nome, espera, id_requisicao
        super().__init__(f"HTTP {status} em {metodo} {rota}"
                         + (f" ({codigo})" if codigo else "") + (f": {self.mensagem}" if self.mensagem else "")
                         + (f" [x-ms-client-request-id {id_requisicao}]" if id_requisicao else ""))

    @property
    def alvo(self) -> str:
        return f"{ROTULOS[self.tipo]} '{self.nome}'" if self.tipo in ROTULOS and self.nome else f"{self.metodo} {self.rota}"


class _Token:
    """Token do Microsoft Entra ID para o serviço de busca, pedido só quando preciso e renovado perto de expirar."""

    def __init__(self, tenant_id: str | None, credencial: Any, agora: Callable[[], float]):
        self._tenant_id, self._credencial, self._agora = tenant_id, credencial, agora
        self._valor: str | None = None
        self._expira = 0.0

    def obter(self) -> str:
        if self._valor is None or self._expira - self._agora() < MARGEM_DO_TOKEN:
            if self._credencial is None:
                try:
                    from azure.identity import AzureCliCredential
                except ImportError:
                    raise ErroLab("Biblioteca do Azure não encontrada. Ative o ambiente virtual e execute: "
                                  "python -m pip install -r requirements/l100.txt") from None
                self._credencial = AzureCliCredential(tenant_id=self._tenant_id, process_timeout=30)
            acesso = self._credencial.get_token(ESCOPO_BUSCA)
            self._valor, self._expira = str(acesso.token), float(acesso.expires_on)
        return self._valor


def _nome_de_objeto(nome: str) -> str:
    if not _PADRAO_NOME_DE_OBJETO.fullmatch(nome or ""):
        raise ErroLab(f"Nome de objeto inválido para o serviço de busca: {nome!r}.")
    return nome


class ClienteBusca:
    """Cliente mínimo da API REST do plano de dados do Azure AI Search, sem chaves, com a identidade do Azure CLI.

    O token só é enviado a https://<busca>.search.windows.net, com o nome validado. O `transporte` e a `credencial` podem ser
    trocados, o que permite testar sem rede.
    """

    def __init__(self, busca: str, tenant_id: str | None = None, credencial: Any = None, transporte: Transporte | None = None,
                 versao_api: str = VERSAO_API, agora: Callable[[], float] = time.time):
        try:
            lab_indexacao.validar_busca(busca)
        except argparse.ArgumentTypeError as erro:
            raise ErroLab(str(erro)) from None
        if versao_api not in VERSOES_API:
            raise ErroLab(f"Versão da API não prevista: {versao_api!r}. Use uma destas: {', '.join(VERSOES_API)}.")
        self.busca, self.versao_api = busca, versao_api
        self.endereco = f"https://{busca}.{SUFIXO_BUSCA}"
        self._transporte = transporte or transporte_urllib
        self._token = _Token(tenant_id, credencial, agora)

    def _pedir(self, metodo: str, caminho: str, *, corpo: Any = None, cabecalhos: Mapping[str, str] | None = None,
               esperados: Sequence[int] = (200,), tipo: str = "", nome: str = "") -> dict[str, Any]:
        url = f"{self.endereco}/{caminho}?api-version={self.versao_api}"
        id_requisicao = str(uuid.uuid4())
        enviados = {
            "Authorization": f"Bearer {self._token.obter()}",
            "Accept": "application/json;odata.metadata=minimal",
            "x-ms-client-request-id": id_requisicao,
            **(cabecalhos or {}),
        }
        dados = None
        if corpo is not None:
            enviados["Content-Type"] = "application/json"
            dados = json.dumps(corpo, ensure_ascii=False).encode("utf-8")
        try:
            resposta = self._transporte(metodo, url, enviados, dados)
        except OSError as erro:
            raise ErroLab(
                f"Não foi possível conectar ao serviço de busca '{self.busca}'. Confira o nome (saída nomeBusca da implantação), "
                "a conexão de rede e se o endereço público do serviço está habilitado.", lab_comum.CODIGO_ACESSO) from erro
        if resposta.status not in esperados:
            codigo, mensagem = _ler_erro(resposta.corpo)
            raise ErroServicoBusca(resposta.status, codigo, mensagem, metodo, caminho, tipo, nome,
                                   resposta.cabecalhos.get("retry-after"), id_requisicao)
        if not resposta.corpo:
            return {}
        try:
            resultado = json.loads(resposta.corpo.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ErroLab(f"O serviço de busca devolveu uma resposta que não é JSON (HTTP {resposta.status}). "
                          "Repita; se persistir, use --detalhes.", lab_comum.CODIGO_ACESSO) from None
        return resultado if isinstance(resultado, dict) else {}

    def obter(self, tipo: str, nome: str) -> dict[str, Any] | None:
        """Definição do objeto no serviço, ou None se ele não existe."""
        try:
            return self._pedir("GET", f"{tipo}('{_nome_de_objeto(nome)}')", tipo=tipo, nome=nome)
        except ErroServicoBusca as erro:
            if erro.status == 404:
                return None
            raise

    def gravar(self, tipo: str, nome: str, definicao: Mapping[str, Any], etag: str | None = None) -> dict[str, Any]:
        """Cria (se o objeto não existe) ou substitui (só se o ETag ainda for o conferido). Nunca sobrescreve sem condição."""
        condicao = {"If-Match": etag} if etag else {"If-None-Match": "*"}
        return self._pedir("PUT", f"{tipo}('{_nome_de_objeto(nome)}')", corpo=dict(definicao), esperados=(200, 201),
                           cabecalhos={"Prefer": "return=representation", **condicao}, tipo=tipo, nome=nome)

    def apagar(self, tipo: str, nome: str, etag: str | None = None) -> None:
        self._pedir("DELETE", f"{tipo}('{_nome_de_objeto(nome)}')", esperados=(200, 204),
                    cabecalhos={"If-Match": etag} if etag else None, tipo=tipo, nome=nome)

    def executar_indexador(self, nome: str) -> None:
        self._pedir("POST", f"indexers('{_nome_de_objeto(nome)}')/search.run", esperados=(200, 202), tipo=INDEXADOR, nome=nome)

    def reiniciar_indexador(self, nome: str) -> None:
        self._pedir("POST", f"indexers('{_nome_de_objeto(nome)}')/search.reset", esperados=(200, 204), tipo=INDEXADOR, nome=nome)

    def status_indexador(self, nome: str) -> dict[str, Any]:
        return self._pedir("GET", f"indexers('{_nome_de_objeto(nome)}')/search.status", tipo=INDEXADOR, nome=nome)

    def buscar(self, indice: str, corpo: Mapping[str, Any]) -> dict[str, Any]:
        return self._pedir("POST", f"indexes('{_nome_de_objeto(indice)}')/docs/search.post.search", corpo=dict(corpo),
                           tipo=INDICE, nome=indice)


def abrir_cliente(busca: str, tenant_id: str | None = None, versao_api: str = VERSAO_API) -> ClienteBusca:
    return ClienteBusca(busca, tenant_id, versao_api=versao_api)


def _ler_erro(corpo: bytes) -> tuple[str, str]:
    try:
        erro = json.loads(corpo.decode("utf-8")).get("error") or {}
        return str(erro.get("code") or ""), str(erro.get("message") or "")
    except (UnicodeDecodeError, json.JSONDecodeError, AttributeError):
        return "", ""


def listar_trechos(cliente: ClienteBusca, indice: str, campos: Sequence[str] = CAMPOS_DA_LISTAGEM) -> list[dict[str, Any]]:
    """Todos os documentos do índice (só os campos pedidos). O laboratório tem dezenas; no limite, ou com mais páginas, para."""
    resposta = cliente.buscar(indice, {"search": "*", "select": ",".join(campos), "top": LIMITE_LISTAGEM})
    itens = resposta.get("value") or []
    if len(itens) >= LIMITE_LISTAGEM or resposta.get("@odata.nextPageParameters"):
        raise ErroLab(f"O índice '{indice}' tem {LIMITE_LISTAGEM} documentos ou mais, mais do que este laboratório espera. "
                      "Confira o nome do índice.")
    return [{nome: valor for nome, valor in item.items() if not nome.startswith("@")} for item in itens]


# --------------------------------------------------------------------------------------
# Execução do indexador
# --------------------------------------------------------------------------------------

@dataclass(frozen=True)
class ResumoExecucao:
    geral: str
    resultado: str | None
    inicio: str | None
    fim: str | None
    processados: int
    falhas: int
    mensagem: str | None
    erros: tuple[Mapping[str, Any], ...]
    avisos: tuple[Mapping[str, Any], ...]
    historico: int

    @property
    def concluida(self) -> bool:
        return self.resultado in ("success", "transientFailure")

    @property
    def ok(self) -> bool:
        return self.resultado == "success" and self.falhas == 0 and not self.erros and self.geral != "error"


def resumir_status(status: Mapping[str, Any]) -> ResumoExecucao:
    """Reduz a resposta de status do indexador ao que importa: resultado, itens processados e falhas, erros e avisos."""
    ultimo = status.get("lastResult") or {}
    return ResumoExecucao(
        geral=str(status.get("status") or "unknown"), resultado=ultimo.get("status"),
        inicio=ultimo.get("startTime"), fim=ultimo.get("endTime"),
        processados=int(ultimo.get("itemsProcessed") or 0), falhas=int(ultimo.get("itemsFailed") or 0),
        mensagem=redigir_texto(ultimo.get("errorMessage")) or None,
        erros=tuple(ultimo.get("errors") or ()), avisos=tuple(ultimo.get("warnings") or ()),
        historico=len(status.get("executionHistory") or ()))


def descrever_problema(item: Mapping[str, Any]) -> str:
    """Um erro ou aviso do indexador em uma linha, sem a chave do documento e sem identificadores do ambiente."""
    origem = f"{item['name']}: " if item.get("name") else ""
    codigo = f"HTTP {item['statusCode']} " if item.get("statusCode") else ""
    texto = redigir_texto(item.get("errorMessage") or item.get("message") or "sem detalhe")
    return f"{origem}{codigo}{_PADRAO_ESPACOS.sub(' ', texto)[:240]}"


def aguardar_execucao(cliente: ClienteBusca, nome: str, inicio_anterior: str | None, limite_segundos: int) -> ResumoExecucao | None:
    """Consulta o status até terminar uma execução nova (início diferente do anterior) ou até o tempo acabar (None)."""
    fim = _relogio() + limite_segundos
    while True:
        resumo = resumir_status(cliente.status_indexador(nome))
        if resumo.concluida and resumo.inicio != inicio_anterior:
            return resumo
        restante = fim - _relogio()
        if restante <= 0:
            return None
        _dormir(min(INTERVALO_SEGUNDOS, restante))


# --------------------------------------------------------------------------------------
# Fontes, qualidade dos trechos e perguntas de conferência
# --------------------------------------------------------------------------------------

def caminho_da_fonte(valor: Any, container: str) -> str:
    """Caminho do blob dentro do contêiner, sem endereço da conta, parâmetros nem SAS, como o L100 grava em `fonte`."""
    texto = str(valor or "").strip()
    if not texto:
        return ""
    partes = urllib.parse.urlsplit(texto)
    if not partes.scheme:
        return texto.split("?", 1)[0].split("#", 1)[0].lstrip("/")
    caminho = urllib.parse.unquote(partes.path).lstrip("/")
    return caminho[len(container) + 1:] if caminho.startswith(f"{container}/") else caminho


def rotulo_da_fonte(valor: Any, inventario: Inventario, container: str) -> str:
    """Só fontes do inventário aparecem; qualquer outra vira um marcador (nada fora da lista de permissão é mostrado)."""
    caminho = caminho_da_fonte(valor, container)
    return caminho if caminho in {documento.blob for documento in inventario.documentos} else FONTE_FORA_DO_INVENTARIO


def resumir_trecho(conteudo: Any, limite: int = 110) -> str:
    plano = _PADRAO_ESPACOS.sub(" ", re.sub(r"(?m)^\s{0,3}#{1,6}\s+", "", str(conteudo or ""))).strip()
    return plano if len(plano) <= limite else plano[: limite - 1].rstrip() + "…"


def _vazio(valor: Any) -> bool:
    return valor is None or not str(valor).strip()


@dataclass(frozen=True)
class Qualidade:
    """Retrato dos trechos de um índice: o que os campos trazem e como o texto começa."""

    trechos: int
    por_documento: Mapping[str, int]
    fontes: tuple[str, ...]
    vazios: Mapping[str, int]
    fora_do_inventario: int
    nao_sinteticos: int | None
    versao_diferente: int
    hash_diferente: int | None
    iniciam_com_cabecalho: int
    contem_cabecalho: int
    tamanho_medio: int
    tamanho_maximo: int
    ausentes: tuple[str, ...]

    def percentual(self, campo: str) -> float | None:
        """Parte dos trechos em que o campo vem preenchido; None se o índice não tem o campo ou não tem trechos."""
        if campo not in self.vazios or not self.trechos:
            return None
        return 100.0 * (self.trechos - self.vazios[campo]) / self.trechos


def analisar_trechos(trechos: Sequence[Mapping[str, Any]], inventario: Inventario, container: str) -> Qualidade:
    """Mede os trechos contra o inventário: documentos presentes, campos vazios, fontes permitidas, versão e hash."""
    por_id = {documento.id: documento for documento in inventario.documentos}
    permitidas = {documento.blob for documento in inventario.documentos}
    campos = [campo for campo in (*CAMPOS_DA_LISTAGEM, *CAMPOS_EXTRAS_DO_L200) if any(campo in trecho for trecho in trechos)]
    por_documento: dict[str, int] = {}
    fontes: set[str] = set()
    vazios = {campo: 0 for campo in campos}
    fora = versao_diferente = iniciam = contem = soma = maior = 0
    nao_sinteticos = hash_diferente = 0
    for trecho in trechos:
        for campo in campos:
            vazios[campo] += _vazio(trecho.get(campo))
        documento = por_id.get(str(trecho.get("documento_id") or ""))
        if documento is not None:
            por_documento[documento.id] = por_documento.get(documento.id, 0) + 1
            versao_diferente += not _vazio(trecho.get("versao")) and trecho.get("versao") != documento.versao
            hash_diferente += not _vazio(trecho.get("sha256")) and trecho.get("sha256") != documento.sha256
        caminho = caminho_da_fonte(trecho.get("fonte"), container)
        if caminho in permitidas:
            fontes.add(caminho)
        if documento is None or caminho not in permitidas:
            fora += 1
        nao_sinteticos += "sintetico" in trecho and str(trecho.get("sintetico")).lower() != "true"
        conteudo = str(trecho.get("conteudo") or "")
        iniciam += bool(_PADRAO_CABECALHO.match(conteudo))
        contem += bool(_PADRAO_CABECALHO.search(conteudo))
        soma, maior = soma + len(conteudo), max(maior, len(conteudo))
    return Qualidade(
        trechos=len(trechos), por_documento=por_documento, fontes=tuple(sorted(fontes)), vazios=vazios,
        fora_do_inventario=fora, nao_sinteticos=nao_sinteticos if "sintetico" in campos else None,
        versao_diferente=versao_diferente, hash_diferente=hash_diferente if "sha256" in campos else None,
        iniciam_com_cabecalho=iniciam, contem_cabecalho=contem, tamanho_medio=round(soma / len(trechos)) if trechos else 0,
        tamanho_maximo=maior, ausentes=tuple(documento.id for documento in inventario.documentos if documento.id not in por_documento))


def problemas_de_completude(qualidade: Qualidade) -> list[str]:
    """O que impede de considerar o índice completo: nada disso depende das métricas do L100."""
    problemas = []
    if not qualidade.trechos:
        return ["o índice não tem nenhum trecho"]
    if qualidade.ausentes:
        problemas.append("documentos do inventário sem trechos: " + ", ".join(qualidade.ausentes))
    for campo in CAMPOS_PREENCHIDOS:
        if qualidade.vazios.get(campo):
            problemas.append(f"{qualidade.vazios[campo]} trecho(s) sem '{campo}'")
    if qualidade.fora_do_inventario:
        problemas.append(f"{qualidade.fora_do_inventario} trecho(s) com documento ou fonte fora do inventário")
    if qualidade.nao_sinteticos:
        problemas.append(f"{qualidade.nao_sinteticos} trecho(s) cujo documento não está marcado como sintético")
    if qualidade.versao_diferente:
        problemas.append(f"{qualidade.versao_diferente} trecho(s) com versão diferente da do inventário")
    if qualidade.hash_diferente:
        problemas.append(f"{qualidade.hash_diferente} trecho(s) com sha256 diferente do inventário")
    return problemas


def validar_perguntas_fixas(perguntas: Sequence[lab_indexacao.PerguntaDeConferencia], inventario: Inventario) -> None:
    """A comparação usa só as seis perguntas de conferência do L100, e cada fato esperado precisa existir nos documentos locais."""
    ids = tuple(pergunta.id for pergunta in perguntas)
    if ids != PERGUNTAS_FIXAS:
        raise ErroLab(f"A comparação usa as perguntas de conferência {', '.join(PERGUNTAS_FIXAS)} (dados/l100/conferencia-recuperacao.json); "
                      f"encontrei: {', '.join(ids) or 'nenhuma'}. Os conjuntos de avaliação do Desafio 06 não fazem parte da comparação.")
    textos = {documento.id: lab_comum.ler_conteudo(documento).decode("utf-8").lower() for documento in inventario.documentos}
    problemas = []
    for pergunta in perguntas:
        for esperado in pergunta.esperados:
            if esperado.documento_id not in textos:
                problemas.append(f"{pergunta.id}: o documento {esperado.documento_id} não está no inventário")
            elif esperado.texto_contem.lower() not in textos[esperado.documento_id]:
                problemas.append(f"{pergunta.id}: o texto esperado de {esperado.documento_id} não existe mais no documento")
    if problemas:
        raise ErroLab("A lista de perguntas de conferência não combina com os documentos:\n  - " + "\n  - ".join(problemas))


def diferencas_de_compatibilidade(atual: Mapping[str, Any], dimensoes: int | None = None) -> list[str]:
    """O que impede o recuperador do L100 de consultar este índice: campos de resultado e campo vetorial."""
    campos = {campo["name"]: campo for campo in atual.get("fields", [])}
    problemas = [f"falta o campo '{nome}'" for nome in CAMPOS_COMPATIVEIS if nome not in campos]
    vetor = campos.get(lab_indexacao.CAMPO_VETOR)
    if vetor is not None:
        if vetor.get("type") != "Collection(Edm.Single)" or not vetor.get("vectorSearchProfile"):
            problemas.append(f"o campo '{lab_indexacao.CAMPO_VETOR}' não é um campo vetorial com perfil")
        if dimensoes is not None and vetor.get("dimensions") != dimensoes:
            problemas.append(f"o campo '{lab_indexacao.CAMPO_VETOR}' tem {vetor.get('dimensions')} dimensões em vez de {dimensoes}")
    return problemas


# --------------------------------------------------------------------------------------
# Tradução de erros
# --------------------------------------------------------------------------------------

def _traduzir_http(erro: ErroServicoBusca, args: argparse.Namespace) -> tuple[str, int]:
    acesso, divergencia = lab_comum.CODIGO_ACESSO, lab_comum.CODIGO_DIVERGENCIA
    busca, status, alvo = getattr(args, "busca", "?"), erro.status, erro.alvo
    minusculas = erro.mensagem.lower()
    if status == 401:
        return (f"O serviço de busca '{busca}' recusou a credencial (HTTP 401). Execute 'az login' (com vários tenants, use "
                "--tenant-id), confirme com 'az account show' e confira o nome do serviço. O serviço precisa aceitar a "
                "autenticação do Microsoft Entra ID."), acesso
    if status == 403:
        return (f"A sua identidade não tem permissão para esta operação no serviço de busca '{busca}' (HTTP 403, {alvo}). Criar, "
                "alterar, executar ou apagar índices, data sources, skillsets e indexadores exige o papel 'Search Service "
                "Contributor'; consultar documentos exige 'Search Index Data Reader'. Os papéis Owner e Contributor do Azure "
                "administram o serviço, mas não dão acesso aos objetos nem aos documentos, e um papel novo pode levar alguns "
                "minutos para valer. Confira também regras de rede que bloqueiem o seu acesso."), acesso
    if status == 404:
        return (f"O serviço de busca '{busca}' ou o objeto não foi encontrado ({alvo}). Confira o nome do serviço (saída nomeBusca "
                "da implantação) e se a etapa criar já foi executada."), acesso
    if status == 409:
        return (f"Conflito no serviço de busca ({alvo}, HTTP 409): outra execução do indexador pode estar em andamento, ou o objeto "
                "mudou. Aguarde, confira com --etapa conferir e repita."), divergencia
    if status == 412:
        if erro.metodo == "DELETE":
            return (f"O objeto mudou desde que o plano foi calculado ({alvo}, HTTP 412). Nada foi apagado neste objeto: rode a "
                    "simulação de novo para ver o plano atual."), divergencia
        return (f"O objeto mudou, ou já existia, quando o script tentou gravá-lo ({alvo}, HTTP 412). Nada foi sobrescrito: rode a "
                "simulação de novo para ver o plano atual."), divergencia
    if status == 429:
        espera = f" Tente de novo em {erro.espera} s." if erro.espera and erro.espera.isdigit() else ""
        return (f"O serviço de busca está limitando as requisições (HTTP 429).{espera} Aguarde e repita: o script é idempotente, "
                "e o que já foi criado continua válido."), acesso
    if status == 504:
        return (f"O serviço de busca demorou demais para responder (HTTP 504, {alvo}). A operação pode ter sido concluída mesmo "
                "assim: confira com --etapa conferir, ou rode a simulação, antes de repetir."), acesso
    if status in {500, 502, 503}:
        return (f"O serviço de busca está indisponível ou ocupado (HTTP {status}, {alvo}). Aguarde alguns minutos e repita; o "
                "script é idempotente."), acesso
    if status == 400:
        dicas = []
        if "dataDeletionDetectionPolicy".lower() in minusculas or "nativeblobsoftdelete" in minusculas:
            dicas.append(f"a política de exclusão nativa do Blob só está documentada na API 2026-04-01 (use --versao-api "
                         f"2026-04-01; em uso: {getattr(args, 'versao_api', VERSAO_API)}), e exige soft delete ativo na conta, "
                         "sem versionamento de blobs")
        if any(termo in minusculas for termo in ("managed identity", "resourceid", "authorization", "identity")):
            dicas.append("confirme a identidade gerenciada do serviço de busca (system-assigned) e os papéis dela: 'Storage Blob "
                         "Data Reader' no contêiner e 'Cognitive Services OpenAI User' no recurso de modelos")
        if erro.tipo == INDICE and erro.metodo == "PUT":
            dicas.append("o serviço só aceita alterações compatíveis em um índice existente: para outras, remova o índice com "
                         "--etapa remover --executar e crie de novo")
        orientacao = (" Possíveis causas: " + "; ".join(dicas) + ".") if dicas else ""
        return (f"O serviço de busca recusou a definição ({alvo}, HTTP 400{f', {erro.codigo}' if erro.codigo else ''}).{orientacao} "
                "Use --detalhes para ver a mensagem do serviço."), acesso
    detalhe = f"HTTP {status}{f', {erro.codigo}' if erro.codigo else ''}"
    return f"Erro do serviço de busca ({detalhe}, {alvo}). Use --detalhes para mais informações.", acesso


def traduzir_erro_ingestao(erro: Exception, args: argparse.Namespace) -> tuple[str, int]:
    """Erros do serviço de busca (REST) ficam aqui; os do Search SDK, dos modelos e do Storage seguem a tradução do L100."""
    if isinstance(erro, ErroServicoBusca):
        return _traduzir_http(erro, args)
    return lab_indexacao.traduzir_erro_indexacao(erro, args)
