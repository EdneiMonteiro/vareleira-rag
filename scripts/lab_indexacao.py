"""Regras do Desafio 02 (L100): dividir os documentos em trechos, calcular embeddings e indexar no Azure AI Search.

A divisão em trechos, a impressão digital de cada trecho, o plano de alterações e a definição do
índice são funções puras: podem ser testadas sem Azure. Os pacotes do Azure e da OpenAI são
importados só quando necessários, para exibir uma mensagem clara se faltarem. Todo acesso usa a
identidade do Azure CLI (az login); nenhuma chave é usada.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import textwrap
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

import lab_comum
from lab_comum import Documento, ErroLab, Verificacao

SUFIXO_BUSCA = "search.windows.net"
SUFIXO_MODELOS = "openai.azure.com"
ESCOPO_MODELOS = "https://cognitiveservices.azure.com/.default"
# Versão estável da API do Azure AI Search usada pelo SDK instalado; serve à sonda sem credenciais.
VERSAO_API_BUSCA = "2026-04-01"

INDICE_PADRAO = "vareleira-lar-l100"
DEPLOYMENT_PADRAO = "embeddings"
DIMENSOES_PADRAO = 1536
TAMANHO_MAXIMO_PADRAO = 1200
PERGUNTAS_PADRAO = lab_comum.RAIZ / "dados" / "l100" / "conferencia-recuperacao.json"

LOTE_EMBEDDINGS = 16
LOTE_INDICE = 50
LIMITE_LISTAGEM = 1000
MODOS_DE_BUSCA = ("vetorial", "texto", "hibrida")

CAMPO_VETOR = "vetor"
PERFIL_VETORIAL = "perfil-hnsw"
ALGORITMO_VETORIAL = "hnsw-cosseno"
ANALISADOR = "pt-BR.microsoft"
SECAO_APRESENTACAO = "Apresentação do documento"
VERSAO_DA_IMPRESSAO = 1
CARACTERES_POR_TOKEN = 3  # estimativa grosseira para português; o serviço informa o uso real
# O serviço de modelos às vezes responde 404 "Subdomain does not map to a resource" de forma intermitente, também
# com o recurso e o deployment corretos. Só esse erro é repetido, com espera curta e crescente, antes de virar orientação.
TENTATIVAS_DO_SUBDOMINIO = 6
ESPERA_DO_SUBDOMINIO = 0.5  # segundos, multiplicados pelo número da tentativa

CRIAR = "criar"
IGUAL = "igual"
DIVERGENTE = "divergente"

_PADRAO_BUSCA = re.compile(r"(?!.*--)[a-z0-9][a-z0-9-]{0,58}[a-z0-9]")
_PADRAO_MODELOS = re.compile(r"[a-z0-9][a-z0-9-]{0,62}[a-z0-9]")
_PADRAO_INDICE = re.compile(r"(?!.*--)[a-z0-9][a-z0-9-]{0,126}[a-z0-9]")
_PADRAO_DEPLOYMENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
_PADRAO_TITULO = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_PADRAO_ITEM_DE_LISTA = re.compile(r"^\s{0,3}(?:[-*+]|\d{1,3}[.)])\s+")
_PADRAO_CLAUSULA = re.compile(r"^\s*(\d+(?:\.\d+)+)\.\s")
_PADRAO_CERCA = re.compile(r"^\s{0,3}(?:```|~~~)")
_PADRAO_FRASE = re.compile(r"(?<=[^\d\s][.!?;:])\s+")  # não separa depois de números como "3.2." ou "2025."
_PADRAO_ID_DE_TRECHO = re.compile(r"[^A-Za-z0-9_=-]")


# --------------------------------------------------------------------------------------
# Argumentos da linha de comando
# --------------------------------------------------------------------------------------

def _validador_inteiro(minimo: int, maximo: int, descricao: str) -> Callable[[str], int]:
    def validar(valor: str) -> int:
        try:
            numero = int(valor)
        except ValueError:
            raise argparse.ArgumentTypeError(f"{descricao} (recebido: {valor!r}).") from None
        if not minimo <= numero <= maximo:
            raise argparse.ArgumentTypeError(f"{descricao} (recebido: {valor!r}).")
        return numero

    return validar


# Os nomes formam os endereços que receberão o token. Aceitar só o formato do Azure impede que um
# valor como "meu-site.exemplo/" envie credenciais a outro destino.
validar_busca = lab_comum.criar_validador(
    _PADRAO_BUSCA, "O serviço de busca deve ter de 2 a 60 caracteres: letras minúsculas, números e hífens")
validar_modelos = lab_comum.criar_validador(
    _PADRAO_MODELOS, "O recurso de modelos deve ter de 2 a 64 caracteres: letras minúsculas, números e hífens")
validar_indice = lab_comum.criar_validador(
    _PADRAO_INDICE, "O índice deve ter de 2 a 128 caracteres: letras minúsculas, números e hífens, sem hífens seguidos")
validar_deployment = lab_comum.criar_validador(
    _PADRAO_DEPLOYMENT, "O deployment deve ter até 64 caracteres: letras, números, ponto, hífen e sublinhado")
validar_dimensoes = _validador_inteiro(1, 3072, "As dimensões devem ser um número de 1 a 3072")
validar_tamanho_maximo = _validador_inteiro(300, 6000, "O tamanho máximo deve ser um número de 300 a 6000 caracteres")
validar_k = _validador_inteiro(1, 10, "A quantidade de trechos deve ser um número de 1 a 10")


def adicionar_argumentos_indice(parser: lab_comum.ParserLab, obrigatorios: bool = True) -> None:
    """Opções que identificam o serviço de busca, o índice e o deployment de embeddings.

    Com `obrigatorios=False`, `--busca` e `--modelos` ficam opcionais (para etapas que não acessam o Azure).
    """
    parser.add_argument("--busca", required=obrigatorios, type=validar_busca,
                        help="Nome do serviço de busca (saída nomeBusca da implantação do Desafio 02).")
    parser.add_argument("--modelos", required=obrigatorios, type=validar_modelos,
                        help="Nome do recurso de modelos (saída nomeModelos da implantação do Desafio 02).")
    parser.add_argument("--indice", default=INDICE_PADRAO, type=validar_indice,
                        help=f"Nome do índice (padrão: {INDICE_PADRAO}).")
    parser.add_argument("--deployment", default=DEPLOYMENT_PADRAO, type=validar_deployment,
                        help=f"Nome do deployment de embeddings, não do modelo (padrão: {DEPLOYMENT_PADRAO}).")
    parser.add_argument("--dimensoes", default=DIMENSOES_PADRAO, type=validar_dimensoes,
                        help=f"Dimensões dos vetores, iguais às do modelo (padrão: {DIMENSOES_PADRAO}).")


def adicionar_argumento_tamanho(parser: lab_comum.ParserLab) -> None:
    parser.add_argument("--tamanho-maximo", default=TAMANHO_MAXIMO_PADRAO, type=validar_tamanho_maximo,
                        help=f"Tamanho máximo de cada trecho, em caracteres (padrão: {TAMANHO_MAXIMO_PADRAO}).")


# --------------------------------------------------------------------------------------
# Divisão em trechos
# --------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Trecho:
    id: str
    documento: Documento
    ordem: int
    secao: str
    clausulas: str
    conteudo: str

    def campos(self) -> dict[str, Any]:
        """Campos do índice que vêm do documento, sem o vetor e sem a impressão digital."""
        doc = self.documento
        return {
            "id": self.id,
            "documento_id": doc.id,
            "titulo_documento": doc.titulo,
            "tipo": doc.tipo,
            "produto": doc.produto,
            "versao": doc.versao,
            "vigencia_inicio": doc.vigencia_inicio,
            "vigencia_fim": doc.vigencia_fim,
            "secao": self.secao,
            "clausulas": self.clausulas,
            "ordem": self.ordem,
            "conteudo": self.conteudo,
            "fonte": doc.blob,
        }

    @property
    def texto_para_embedding(self) -> str:
        """O título do documento vai junto: dá contexto a trechos curtos, como um termo do glossário."""
        return f"{self.documento.titulo}\n\n{self.conteudo}"


@dataclass(frozen=True)
class _Secao:
    nome: str
    linha_titulo: str
    unidades: tuple[str, ...]


def identificador_do_trecho(documento_id: str, ordem: int) -> str:
    """Chave válida no Azure AI Search (só letras, números, '_', '-' e '='), estável para o mesmo documento."""
    return _PADRAO_ID_DE_TRECHO.sub("_", f"{documento_id}-{ordem:03d}")


def estimar_tokens(caracteres: int) -> int:
    return max(1, -(-caracteres // CARACTERES_POR_TOKEN))


def _agrupar_em_unidades(linhas: Sequence[str]) -> list[str]:
    """Junta linhas em parágrafos; listas e tabelas ficam com o parágrafo que as introduz."""
    blocos: list[str] = []
    atual: list[str] = []
    em_cerca = False
    for linha in [*linhas, ""]:
        if _PADRAO_CERCA.match(linha):
            em_cerca = not em_cerca
        if not linha.strip() and not em_cerca:
            if atual:
                blocos.append("\n".join(atual))
                atual = []
            continue
        atual.append(linha.rstrip())
    unidades: list[str] = []
    for bloco in blocos:
        primeira = bloco.split("\n", 1)[0]
        complementa = bool(_PADRAO_ITEM_DE_LISTA.match(primeira)) or primeira.lstrip().startswith("|")
        if complementa and unidades:
            unidades[-1] += "\n\n" + bloco
        else:
            unidades.append(bloco)
    return unidades


def _ler_secoes(texto: str) -> list[_Secao]:
    """Divide o Markdown em seções: cada título, de qualquer nível, abre uma seção nova."""
    brutas: list[tuple[str, str, list[str]]] = [(SECAO_APRESENTACAO, "", [])]
    pilha: list[tuple[int, str]] = []
    em_cerca = False
    for linha in texto.split("\n"):
        if _PADRAO_CERCA.match(linha):
            em_cerca = not em_cerca
        titulo = None if em_cerca else _PADRAO_TITULO.match(linha)
        if not titulo:
            brutas[-1][2].append(linha)
            continue
        nivel, nome = len(titulo.group(1)), titulo.group(2)
        while pilha and pilha[-1][0] >= nivel:
            pilha.pop()
        pilha.append((nivel, nome))
        caminho = SECAO_APRESENTACAO if nivel == 1 else " > ".join(item for nivel_item, item in pilha if nivel_item > 1)
        brutas.append((caminho, linha.strip(), []))
    secoes = []
    for nome, linha_titulo, linhas in brutas:
        unidades = _agrupar_em_unidades(linhas)
        if unidades:
            secoes.append(_Secao(nome, linha_titulo, tuple(unidades)))
    return secoes


def _dividir_unidade(unidade: str, limite: int) -> list[str]:
    """Divide uma unidade maior que o limite: por linhas, depois por frases e, por fim, por palavras."""
    if len(unidade) <= limite:
        return [unidade]
    partes: list[str] = []
    for linha in unidade.split("\n"):
        if len(linha) <= limite:
            partes.append(linha)
            continue
        for frase in _PADRAO_FRASE.split(linha):
            partes.extend(textwrap.wrap(frase, width=limite, break_long_words=True, break_on_hyphens=False) or [""])
    pedacos: list[str] = []
    atual = ""
    for parte in partes:
        candidata = f"{atual}\n{parte}" if atual else parte
        if atual and len(candidata) > limite:
            pedacos.append(atual)
            atual = parte
        else:
            atual = candidata
    if atual:
        pedacos.append(atual)
    return pedacos


def _montar(cabecalho: str, unidades: Sequence[str]) -> str:
    corpo = "\n\n".join(unidades)
    return f"{cabecalho}\n\n{corpo}" if cabecalho else corpo


def _empacotar(unidades: Sequence[str], cabecalho: str, tamanho_maximo: int) -> list[str]:
    """Junta unidades inteiras em trechos de até `tamanho_maximo` caracteres, com o título da seção no início."""
    folga = max(1, tamanho_maximo - len(cabecalho) - 2)
    pedacos = [pedaco for unidade in unidades for pedaco in _dividir_unidade(unidade, folga)]
    trechos: list[str] = []
    atual: list[str] = []
    for pedaco in pedacos:
        if atual and len(_montar(cabecalho, [*atual, pedaco])) > tamanho_maximo:
            trechos.append(_montar(cabecalho, atual))
            atual = []
        atual.append(pedaco)
    if atual:
        trechos.append(_montar(cabecalho, atual))
    return trechos


def extrair_clausulas(conteudo: str) -> str:
    """Números de cláusula que abrem parágrafos do trecho, como '3.1, 3.2'. Vazio se o texto não numera cláusulas."""
    encontradas: list[str] = []
    for linha in conteudo.split("\n"):
        if _PADRAO_TITULO.match(linha):
            continue
        achado = _PADRAO_CLAUSULA.match(linha)
        if achado and achado.group(1) not in encontradas:
            encontradas.append(achado.group(1))
    return ", ".join(encontradas)


def dividir_documento(documento: Documento, texto: str, tamanho_maximo: int = TAMANHO_MAXIMO_PADRAO) -> list[Trecho]:
    """Divide um documento Markdown em trechos que respeitam as seções, os parágrafos e as cláusulas."""
    trechos: list[Trecho] = []
    ordem = 0
    for secao in _ler_secoes(texto.replace("\r\n", "\n")):
        for conteudo in _empacotar(secao.unidades, secao.linha_titulo, tamanho_maximo):
            ordem += 1
            trechos.append(Trecho(
                id=identificador_do_trecho(documento.id, ordem), documento=documento, ordem=ordem,
                secao=secao.nome, clausulas=extrair_clausulas(conteudo), conteudo=conteudo,
            ))
    return trechos


def dividir_documentos(documentos: Iterable[tuple[Documento, str]], tamanho_maximo: int = TAMANHO_MAXIMO_PADRAO) -> list[Trecho]:
    return [trecho for documento, texto in documentos for trecho in dividir_documento(documento, texto, tamanho_maximo)]


# --------------------------------------------------------------------------------------
# Impressão digital e plano
# --------------------------------------------------------------------------------------

@dataclass(frozen=True)
class EspecificacaoEmbedding:
    """O que, além do texto, determina o vetor: o deployment e o tamanho do vetor."""

    deployment: str
    dimensoes: int


def calcular_impressao(trecho: Trecho, especificacao: EspecificacaoEmbedding) -> str:
    """Impressão digital (SHA-256) de tudo o que define o registro do trecho no índice.

    Se o texto, algum metadado, o deployment ou as dimensões mudarem, a impressão muda e o trecho
    deixa de ser considerado igual ao que já está no índice.
    """
    base = {
        "v": VERSAO_DA_IMPRESSAO,
        "deployment": especificacao.deployment,
        "dimensoes": especificacao.dimensoes,
        "campos": trecho.campos(),
    }
    bruto = json.dumps(base, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(bruto.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class AcaoTrecho:
    trecho: Trecho
    impressao: str
    estado: str


@dataclass(frozen=True)
class Plano:
    acoes: tuple[AcaoTrecho, ...]
    orfaos: tuple[str, ...]

    def contar(self, estado: str) -> int:
        return sum(1 for acao in self.acoes if acao.estado == estado)

    @property
    def a_gravar(self) -> tuple[AcaoTrecho, ...]:
        return tuple(acao for acao in self.acoes if acao.estado in (CRIAR, DIVERGENTE))


def planejar(trechos: Sequence[Trecho], existentes: Mapping[str, str | None], especificacao: EspecificacaoEmbedding) -> Plano:
    """Compara os trechos calculados com os que já estão no índice (id -> impressão). Somente leitura."""
    acoes = []
    for trecho in trechos:
        impressao = calcular_impressao(trecho, especificacao)
        if trecho.id not in existentes:
            estado = CRIAR
        elif existentes[trecho.id] == impressao:
            estado = IGUAL
        else:
            estado = DIVERGENTE
        acoes.append(AcaoTrecho(trecho, impressao, estado))
    produzidos = {trecho.id for trecho in trechos}
    return Plano(tuple(acoes), tuple(sorted(set(existentes) - produzidos)))


# --------------------------------------------------------------------------------------
# Definição do índice
# --------------------------------------------------------------------------------------

_PADRAO_DOS_ATRIBUTOS = {
    "key": False, "searchable": False, "filterable": False, "sortable": False, "facetable": False,
    "retrievable": True, "stored": True,
}


def definicao_do_indice(nome: str, dimensoes: int = DIMENSOES_PADRAO) -> dict[str, Any]:
    """Definição do índice no formato JSON da API REST do Azure AI Search.

    Todos os atributos são informados de forma explícita: o serviço trata como verdadeiros os que
    ficam em branco em campos de texto, o que aumentaria o índice sem necessidade.
    """

    def campo(nome_do_campo: str, tipo: str = "Edm.String", *, chave: bool = False, pesquisavel: bool = False,
              filtravel: bool = False, ordenavel: bool = False, analisador: str | None = None) -> dict[str, Any]:
        definicao_do_campo: dict[str, Any] = {
            "name": nome_do_campo, "type": tipo, "key": chave, "searchable": pesquisavel, "filterable": filtravel,
            "sortable": ordenavel, "facetable": False, "retrievable": True,
        }
        if analisador:
            definicao_do_campo["analyzer"] = analisador
        return definicao_do_campo

    return {
        "name": nome,
        "fields": [
            campo("id", chave=True, filtravel=True),
            campo("documento_id", filtravel=True),
            campo("titulo_documento", pesquisavel=True, analisador=ANALISADOR),
            campo("tipo", filtravel=True),
            campo("produto", filtravel=True),
            campo("versao", filtravel=True),
            campo("vigencia_inicio", filtravel=True),
            campo("vigencia_fim", filtravel=True),
            campo("secao", pesquisavel=True, analisador=ANALISADOR),
            campo("clausulas"),
            campo("ordem", "Edm.Int32", filtravel=True, ordenavel=True),
            campo("conteudo", pesquisavel=True, analisador=ANALISADOR),
            campo("fonte", filtravel=True),
            campo("modelo_embeddings", filtravel=True),
            campo("impressao"),
            {
                "name": CAMPO_VETOR, "type": "Collection(Edm.Single)", "key": False, "searchable": True,
                "filterable": False, "sortable": False, "facetable": False, "retrievable": False, "stored": False,
                "dimensions": dimensoes, "vectorSearchProfile": PERFIL_VETORIAL,
            },
        ],
        "vectorSearch": {
            "algorithms": [{"name": ALGORITMO_VETORIAL, "kind": "hnsw", "hnswParameters": {"metric": "cosine"}}],
            "profiles": [{"name": PERFIL_VETORIAL, "algorithm": ALGORITMO_VETORIAL}],
        },
    }


def diferencas_do_esquema(esperado: Mapping[str, Any], atual: Mapping[str, Any]) -> list[str]:
    """Lista o que o índice existente tem de diferente do esperado. Lista vazia: o índice é compatível."""
    problemas: list[str] = []
    campos_atuais = {campo["name"]: campo for campo in atual.get("fields", [])}
    nomes_esperados = set()
    for campo in esperado["fields"]:
        nome = campo["name"]
        nomes_esperados.add(nome)
        real = campos_atuais.get(nome)
        if real is None:
            problemas.append(f"falta o campo '{nome}'")
            continue
        for chave in ("type", "analyzer", "dimensions", "vectorSearchProfile"):
            if chave in campo and real.get(chave) != campo[chave]:
                problemas.append(f"campo '{nome}': {chave} é {real.get(chave)!r} em vez de {campo[chave]!r}")
        for chave, padrao in _PADRAO_DOS_ATRIBUTOS.items():
            esperado_valor = campo.get(chave, padrao)
            real_valor = real.get(chave, padrao)
            if real_valor is None:
                real_valor = padrao
            if real_valor != esperado_valor:
                problemas.append(f"campo '{nome}': {chave} é {real_valor!r} em vez de {esperado_valor!r}")
    extras = sorted(set(campos_atuais) - nomes_esperados)
    if extras:
        problemas.append(f"campos que não fazem parte da definição: {', '.join(extras)}")

    busca_vetorial = atual.get("vectorSearch") or {}
    algoritmos = {item["name"]: item for item in busca_vetorial.get("algorithms", [])}
    algoritmo = algoritmos.get(ALGORITMO_VETORIAL)
    if algoritmo is None:
        problemas.append(f"falta o algoritmo vetorial '{ALGORITMO_VETORIAL}'")
    else:
        if algoritmo.get("kind") != "hnsw":
            problemas.append(f"algoritmo '{ALGORITMO_VETORIAL}': tipo é {algoritmo.get('kind')!r} em vez de 'hnsw'")
        metrica = (algoritmo.get("hnswParameters") or {}).get("metric")
        if metrica != "cosine":
            problemas.append(f"algoritmo '{ALGORITMO_VETORIAL}': métrica é {metrica!r} em vez de 'cosine'")
    perfis = {item["name"]: item for item in busca_vetorial.get("profiles", [])}
    perfil = perfis.get(PERFIL_VETORIAL)
    if perfil is None:
        problemas.append(f"falta o perfil vetorial '{PERFIL_VETORIAL}'")
    elif perfil.get("algorithm") != ALGORITMO_VETORIAL:
        problemas.append(f"perfil '{PERFIL_VETORIAL}': algoritmo é {perfil.get('algorithm')!r} em vez de {ALGORITMO_VETORIAL!r}")
    return problemas


# --------------------------------------------------------------------------------------
# Perguntas de conferência
# --------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Esperado:
    documento_id: str
    texto_contem: str


@dataclass(frozen=True)
class PerguntaDeConferencia:
    id: str
    pergunta: str
    esperados: tuple[Esperado, ...]


def carregar_perguntas(caminho: Path = PERGUNTAS_PADRAO) -> list[PerguntaDeConferencia]:
    """Lê as perguntas de conferência. Ficam fora da pasta de documentos: não são conteúdo recuperável."""
    caminho = Path(caminho)
    try:
        bruto = json.loads(caminho.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ErroLab(f"Arquivo de perguntas não encontrado: {lab_comum._mostrar_caminho(caminho)}") from None
    except json.JSONDecodeError as erro:
        raise ErroLab(f"Arquivo de perguntas com JSON inválido (linha {erro.lineno}, coluna {erro.colno}).") from None
    except (OSError, UnicodeDecodeError) as erro:
        raise ErroLab(f"Não foi possível ler o arquivo de perguntas: {type(erro).__name__}.") from None
    problemas: list[str] = []
    if not isinstance(bruto, dict) or bruto.get("schema_version") != 1 or bruto.get("sintetico") is not True:
        problemas.append("o arquivo precisa ser um objeto com \"schema_version\": 1 e \"sintetico\": true")
    entradas = bruto.get("perguntas") if isinstance(bruto, dict) else None
    perguntas: list[PerguntaDeConferencia] = []
    if not isinstance(entradas, list) or not entradas:
        problemas.append("'perguntas' deve ser uma lista com pelo menos um item")
    else:
        vistos: set[str] = set()
        for indice, entrada in enumerate(entradas):
            rotulo = f"perguntas[{indice}]"
            if not isinstance(entrada, dict):
                problemas.append(f"{rotulo}: deve ser um objeto")
                continue
            identificador, pergunta = entrada.get("id"), entrada.get("pergunta")
            if not isinstance(identificador, str) or not identificador.strip() or identificador in vistos:
                problemas.append(f"{rotulo}: 'id' ausente, vazio ou repetido")
                continue
            vistos.add(identificador)
            rotulo = identificador
            esperados = []
            itens = entrada.get("esperado")
            if not isinstance(pergunta, str) or not pergunta.strip():
                problemas.append(f"{rotulo}: 'pergunta' ausente ou vazia")
            if not isinstance(itens, list) or not itens:
                problemas.append(f"{rotulo}: 'esperado' deve ser uma lista com pelo menos um item")
                continue
            for item in itens:
                documento, trecho = (item.get("documento_id"), item.get("texto_contem")) if isinstance(item, dict) else (None, None)
                if not isinstance(documento, str) or not documento or not isinstance(trecho, str) or not trecho:
                    problemas.append(f"{rotulo}: cada item de 'esperado' precisa de 'documento_id' e 'texto_contem'")
                    break
                esperados.append(Esperado(documento, trecho))
            else:
                if isinstance(pergunta, str) and pergunta.strip():
                    perguntas.append(PerguntaDeConferencia(identificador, pergunta, tuple(esperados)))
    if problemas:
        raise ErroLab("Arquivo de perguntas inválido:\n  - " + "\n  - ".join(problemas))
    return perguntas


def posicao_do_esperado(pergunta: PerguntaDeConferencia, resultados: Sequence[Mapping[str, Any]]) -> int | None:
    """Posição (1 é a primeira) do primeiro resultado que contém um dos trechos esperados; None se nenhum."""
    for posicao, resultado in enumerate(resultados, start=1):
        conteudo = str(resultado.get("conteudo") or "").lower()
        for esperado in pergunta.esperados:
            if resultado.get("documento_id") == esperado.documento_id and esperado.texto_contem.lower() in conteudo:
                return posicao
    return None


# --------------------------------------------------------------------------------------
# Modelo de embeddings
# --------------------------------------------------------------------------------------

@dataclass(frozen=True)
class ResultadoEmbeddings:
    vetores: list[list[float]]
    modelo: str
    tokens: int


class ClienteEmbeddings:
    """Gera embeddings em lotes por um cliente compatível com a API da OpenAI e confere cada resposta."""

    def __init__(self, cliente: Any, deployment: str, dimensoes: int, lote: int = LOTE_EMBEDDINGS):
        self.cliente, self.deployment, self.dimensoes, self.lote = cliente, deployment, dimensoes, lote

    def _criar(self, parte: list[str]) -> Any:
        tentativa = 1
        while True:
            try:
                return self.cliente.embeddings.create(model=self.deployment, input=parte)
            except Exception as erro:  # noqa: BLE001 - só o 404 intermitente do serviço de modelos é repetido
                intermitente = (type(erro).__module__.split(".")[0] == "openai" and getattr(erro, "status_code", None) == 404
                                and subdominio_sem_recurso(erro))
                if not intermitente or tentativa == TENTATIVAS_DO_SUBDOMINIO:
                    raise
                espera = ESPERA_DO_SUBDOMINIO * tentativa
                print(f"[AVISO] O serviço de modelos respondeu 404 intermitente (tentativa {tentativa} de "
                      f"{TENTATIVAS_DO_SUBDOMINIO}). Repetindo em {espera:g} s.", file=sys.stderr)
                time.sleep(espera)
                tentativa += 1

    def gerar(self, textos: Sequence[str]) -> ResultadoEmbeddings:
        vetores: list[list[float]] = []
        modelos: set[str] = set()
        tokens = 0
        for inicio in range(0, len(textos), self.lote):
            parte = list(textos[inicio:inicio + self.lote])
            resposta = self._criar(parte)
            itens = sorted(resposta.data, key=lambda item: item.index)
            if len(itens) != len(parte):
                raise ErroLab(
                    f"O serviço de modelos devolveu {len(itens)} vetor(es) para {len(parte)} texto(s). "
                    "Nada foi gravado no índice.", lab_comum.CODIGO_ACESSO)
            for item in itens:
                if len(item.embedding) != self.dimensoes:
                    raise ErroLab(
                        f"O deployment '{self.deployment}' devolveu vetores de {len(item.embedding)} dimensões, mas o "
                        f"índice espera {self.dimensoes}. Use --dimensoes {len(item.embedding)} com um índice novo "
                        "(--indice) ou confira o modelo do deployment. Nada foi gravado no índice.")
                vetores.append(list(item.embedding))
            modelos.add(str(getattr(resposta, "model", "") or ""))
            tokens += getattr(getattr(resposta, "usage", None), "total_tokens", 0) or 0
        if len(modelos) > 1:
            raise ErroLab("O deployment respondeu com modelos diferentes durante a execução. Repita o comando.",
                          lab_comum.CODIGO_DIVERGENCIA)
        return ResultadoEmbeddings(vetores, modelos.pop() if modelos else "", tokens)


def criar_cliente_embeddings(modelos: str, deployment: str, dimensoes: int, tenant_id: str | None = None,
                             credencial: Any = None) -> ClienteEmbeddings:
    """Cria o cliente, sem chaves, com a identidade do Azure CLI (az login) ou com a `credencial` informada."""
    try:
        from azure.identity import AzureCliCredential, get_bearer_token_provider
        from openai import OpenAI
    except ImportError:
        raise ErroLab(
            "Bibliotecas do Azure ou da OpenAI não encontradas. Ative o ambiente virtual e execute: "
            "python -m pip install -r requirements/l100.txt"
        ) from None
    if credencial is None:
        credencial = AzureCliCredential(tenant_id=tenant_id, process_timeout=30)
    cliente = OpenAI(
        base_url=f"https://{modelos}.{SUFIXO_MODELOS}/openai/v1/",
        api_key=get_bearer_token_provider(credencial, ESCOPO_MODELOS),
        # Uma conexão nova por pedido: na validação, as repetições pela mesma conexão falharam em sequência
        # (ver TENTATIVAS_DO_SUBDOMINIO), e com conexão nova os pedidos passaram.
        default_headers={"Connection": "close"},
        max_retries=4, timeout=60,
    )
    return ClienteEmbeddings(cliente, deployment, dimensoes)


# --------------------------------------------------------------------------------------
# Azure AI Search
# --------------------------------------------------------------------------------------

class IndiceBusca:
    """Operações do laboratório no Azure AI Search, sem chaves, com a identidade do Azure CLI ou a `credencial` informada."""

    CAMPOS_DO_RESULTADO = ["id", "documento_id", "titulo_documento", "secao", "clausulas", "conteudo", "fonte", "versao"]

    def __init__(self, busca: str, indice: str, tenant_id: str | None = None, credencial: Any = None):
        try:
            from azure.identity import AzureCliCredential
            from azure.search.documents import SearchClient
            from azure.search.documents.indexes import SearchIndexClient
        except ImportError:
            raise ErroLab(
                "Bibliotecas do Azure não encontradas. Ative o ambiente virtual e execute: "
                "python -m pip install -r requirements/l100.txt"
            ) from None
        self.nome = indice
        endereco = f"https://{busca}.{SUFIXO_BUSCA}"
        if credencial is None:
            credencial = AzureCliCredential(tenant_id=tenant_id, process_timeout=30)
        self._indices = SearchIndexClient(endpoint=endereco, credential=credencial)
        self._documentos = SearchClient(endpoint=endereco, index_name=indice, credential=credencial)

    def definicao_atual(self) -> dict[str, Any] | None:
        from azure.core.exceptions import ResourceNotFoundError
        try:
            return self._indices.get_index(self.nome).as_dict()
        except ResourceNotFoundError:
            return None

    def criar(self, definicao: Mapping[str, Any]) -> None:
        from azure.search.documents.indexes.models import SearchIndex
        self._indices.create_index(SearchIndex(dict(definicao)))

    def apagar(self) -> None:
        self._indices.delete_index(self.nome)

    def trechos_gravados(self) -> dict[str, dict[str, Any]]:
        """id -> {impressao, modelo_embeddings} de todos os documentos do índice."""
        resultados = self._documentos.search(search_text="*", select=["id", "impressao", "modelo_embeddings"],
                                             top=LIMITE_LISTAGEM)
        gravados = {item["id"]: {"impressao": item.get("impressao"), "modelo_embeddings": item.get("modelo_embeddings")}
                    for item in resultados}
        if len(gravados) >= LIMITE_LISTAGEM:
            raise ErroLab(f"O índice tem {LIMITE_LISTAGEM} documentos ou mais, mais do que este laboratório espera. "
                          "Use outro nome de índice (--indice).")
        return gravados

    def gravar(self, documentos: list[dict[str, Any]]) -> None:
        self._conferir(self._documentos.merge_or_upload_documents(documents=documentos), "gravar")

    def remover(self, ids: list[str]) -> None:
        self._conferir(self._documentos.delete_documents(documents=[{"id": chave} for chave in ids]), "remover")

    @staticmethod
    def _conferir(resultados: Iterable[Any], verbo: str) -> None:
        recusados = [resultado for resultado in resultados if not resultado.succeeded]
        if recusados:
            detalhe = "; ".join(f"{item.key}: {str(item.error_message or 'sem detalhe')[:120]}" for item in recusados[:3])
            raise ErroLab(f"O serviço de busca recusou {len(recusados)} documento(s) ao {verbo} ({detalhe}).",
                          lab_comum.CODIGO_ACESSO)

    def contar(self) -> int:
        return self._documentos.get_document_count()

    def consultar(self, texto: str, vetor: Sequence[float] | None, k: int) -> list[dict[str, Any]]:
        """Busca por palavras (texto), por vetor ou pelos dois (híbrida), conforme o que for informado."""
        from azure.search.documents.models import VectorizedQuery
        opcoes: dict[str, Any] = {"select": self.CAMPOS_DO_RESULTADO, "top": k}
        if vetor is not None:
            opcoes["vector_queries"] = [VectorizedQuery(vector=list(vetor), k_nearest_neighbors=k, fields=CAMPO_VETOR)]
        return [dict(item) for item in self._documentos.search(search_text=texto or None, **opcoes)]


def abrir_indice(busca: str, indice: str, tenant_id: str | None = None, credencial: Any = None) -> IndiceBusca:
    return IndiceBusca(busca, indice, tenant_id, credencial)


# --------------------------------------------------------------------------------------
# Acesso sem credenciais
# --------------------------------------------------------------------------------------

STATUS_SEM_CREDENCIAL = {401, 403}


def _status_anonimo(url: str) -> int:
    """Pede a URL sem nenhuma credencial e devolve só o código HTTP."""
    pedido = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(pedido, timeout=20) as resposta:
            return resposta.status
    except urllib.error.HTTPError as erro:
        return erro.code


def verificar_acesso_sem_credenciais(
    busca: str, indice: str, modelos: str, consultar: Callable[[str], int] | None = None,
) -> Verificacao:
    """Confere que a busca e os modelos recusam quem não apresenta credencial (chaves de API desativadas)."""
    nome = "Acesso sem credenciais negado"
    consultar = consultar or _status_anonimo
    alvos = [
        ("busca", f"https://{busca}.{SUFIXO_BUSCA}/indexes('{indice}')/docs/$count?api-version={VERSAO_API_BUSCA}"),
        ("modelos", f"https://{modelos}.{SUFIXO_MODELOS}/openai/v1/models"),
    ]
    abertos: list[str] = []
    inconclusivos: list[str] = []
    codigos: list[str] = []
    for rotulo, url in alvos:
        try:
            status = consultar(url)
        except OSError as erro:
            inconclusivos.append(f"{rotulo} ({type(erro).__name__})")
            continue
        codigos.append(f"{rotulo} HTTP {status}")
        if 200 <= status < 300:
            abertos.append(f"{rotulo} (HTTP {status})")
        elif status not in STATUS_SEM_CREDENCIAL:
            inconclusivos.append(f"{rotulo} (HTTP {status})")
    if abertos:
        return Verificacao(nome, False, "ACESSO SEM CREDENCIAL PERMITIDO em: " + "; ".join(abertos))
    if inconclusivos:
        return Verificacao(nome, False, "não foi possível confirmar em: " + "; ".join(inconclusivos))
    return Verificacao(nome, True, "pedidos sem credencial recusados: " + "; ".join(codigos))


# --------------------------------------------------------------------------------------
# Tradução de erros
# --------------------------------------------------------------------------------------

def _host_do_erro(erro: Exception) -> str:
    resposta = getattr(erro, "response", None)
    pedido = getattr(resposta, "request", None)
    return str(getattr(pedido, "url", "") or "") or str(erro)


def subdominio_sem_recurso(erro: Exception) -> bool:
    """O 404 que o Azure devolve quando o endereço do recurso não corresponde a nenhum recurso, certo ou não."""
    return "Subdomain does not map to a resource" in str(erro)


def mensagem_de_subdominio_sem_recurso(modelos: str) -> str:
    return (f"O Azure respondeu 404 ('Subdomain does not map to a resource') para o recurso de modelos '{modelos}'. "
            "Confira o nome do recurso (saída nomeModelos da implantação). Com o nome certo, o Azure pode responder "
            "assim de forma intermitente, sobretudo logo após criar ou alterar o recurso: aguarde alguns minutos e repita.")


def _traduzir_erro_modelos(nome: str, status: int | None, modelos: str, deployment: str,
                           sem_recurso: bool = False) -> tuple[str, int]:
    acesso = lab_comum.CODIGO_ACESSO
    if nome in {"AuthenticationError", "PermissionDeniedError"} or status in {401, 403}:
        return (f"O serviço de modelos recusou o pedido (HTTP {status or '401 ou 403'}). Confira se a sessão do Azure CLI é do "
                "tenant da assinatura ('az login', com --tenant-id se houver vários) e se a sua identidade tem o papel "
                f"'Cognitive Services OpenAI User' no recurso '{modelos}'. Um papel novo pode levar alguns minutos para "
                "valer. Confira também regras de rede que bloqueiem o seu acesso."), acesso
    if (nome == "NotFoundError" or status == 404) and sem_recurso:
        return mensagem_de_subdominio_sem_recurso(modelos), acesso
    if nome == "NotFoundError" or status == 404:
        return (f"O deployment '{deployment}' não foi encontrado no recurso '{modelos}'. Use o nome do deployment "
                "(saída nomeDeploymentEmbeddings da implantação), não o nome do modelo, e confira o nome do recurso."), acesso
    if nome == "RateLimitError" or status == 429:
        return ("O deployment atingiu o limite de requisições ou de tokens por minuto (HTTP 429). Aguarde um minuto e "
                "repita: o script retoma sem duplicar nada. Se persistir, aumente capacidadeEmbeddings no Bicep."), acesso
    if nome in {"APIConnectionError", "APITimeoutError"}:
        return (f"Não foi possível conectar ao recurso de modelos '{modelos}'. Confira o nome, a conexão de rede e se o "
                "endereço público do recurso está habilitado."), acesso
    detalhe = f"HTTP {status}" if status else nome
    return f"O serviço de modelos recusou ou não concluiu o pedido ({detalhe}). Use --detalhes para mais informações.", acesso


def _traduzir_erro_busca(nome: str, status: int | None, busca: str, indice: str) -> tuple[str, int]:
    acesso = lab_comum.CODIGO_ACESSO
    if status == 403:
        return (f"A sua identidade não tem permissão no serviço de busca '{busca}'. Gravar e consultar documentos exige o "
                "papel 'Search Index Data Contributor' (ou 'Search Index Data Reader', só para consultar), e criar ou "
                "alterar o índice, 'Search Service Contributor'. Ter acesso para criar o serviço, como o Owner, não dá "
                "acesso aos documentos, e um papel novo pode levar alguns minutos para valer."), acesso
    if status == 401:
        return ("O serviço de busca recusou a credencial. Execute 'az login' (com vários tenants, use --tenant-id) "
                f"e confira o nome do serviço '{busca}'."), acesso
    if status == 404:
        return (f"O serviço de busca '{busca}' ou o índice '{indice}' não foi encontrado. Confira os nomes (saída "
                "nomeBusca da implantação) e, para consultar, se o índice já foi criado por indexar_documentos.py "
                "--executar."), acesso
    if status == 409:
        return ("O índice mudou durante a execução. Nada foi gravado: rode a simulação de novo.",
                lab_comum.CODIGO_DIVERGENCIA)
    if status in {429, 502, 503, 504}:
        return (f"O serviço de busca está limitando ou indisponível (HTTP {status}). Aguarde alguns minutos e repita: "
                "o script é idempotente."), acesso
    if nome == "ServiceRequestError":
        return (f"Não foi possível conectar ao serviço de busca '{busca}'. Confira o nome, a conexão de rede e se o "
                "endereço público do serviço está habilitado."), acesso
    detalhe = f"HTTP {status}" if status else nome
    return f"Erro do serviço de busca ({detalhe}). Use --detalhes para mais informações.", acesso


def traduzir_erro_indexacao(erro: Exception, args: argparse.Namespace) -> tuple[str, int]:
    """Transforma erros do Search, dos modelos e do Storage em orientação clara, sem expor tokens."""
    nome = type(erro).__name__
    status = getattr(erro, "status_code", None)
    if type(erro).__module__.split(".")[0] == "openai":
        return _traduzir_erro_modelos(nome, status, getattr(args, "modelos", "?"), getattr(args, "deployment", "?"),
                                      subdominio_sem_recurso(erro))
    destino = _host_do_erro(erro)
    if f".{SUFIXO_BUSCA}" in destino and (status is not None or nome == "ServiceRequestError"):
        return _traduzir_erro_busca(nome, status, getattr(args, "busca", "?"), getattr(args, "indice", "?"))
    return lab_comum.traduzir_erro(erro, getattr(args, "conta", "?"), getattr(args, "container", "?"))
