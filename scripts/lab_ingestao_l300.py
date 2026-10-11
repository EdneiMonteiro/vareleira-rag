"""Regras do L300 (Desafio 02): manifesto de permissões documentais, cópias classificadas no Blob Storage e pipeline com campo de acesso.

O manifesto (dados/l300/permissoes-documentais.json) é a lista de permissão do que ESTA ferramenta envia: só o que ele declara, com
classe de acesso, é validado, enviado, excluído ou restaurado por ela. Ele não limita o que o indexador lê nem o que o chat
recupera: o indexador lê a pasta inteira do L300 no contêiner, e o filtro do chat autoriza CLASSES (o campo `acesso` de cada
trecho, veja lab_acesso), não IDs de documentos. Um blob ou trecho fora do manifesto, com uma classe permitida, continuaria
recuperável; por isso `carregar` avisa sobre blobs fora do manifesto e `conferir` reprova trechos de documentos que ele não declara
ou com classe diferente da declarada. Cada documento tem o caminho real do arquivo (dentro de dados/), o tamanho e o hash do
conteúdo normalizado (LF, como no L100) e uma classe da lista fixa de lab_acesso. Os três documentos do L100 são lidos no lugar,
sem alteração, e conferidos contra o inventário do L100; o material operacional novo fica em dados/l300/documentos. Um documento
sem classe, com classe desconhecida, fora de dados/ ou com conteúdo diferente do declarado faz a validação falhar, sempre antes
de qualquer acesso ao Azure.

As cópias vão para um contêiner e uma pasta próprios do L300, separados dos do L100, com o metadado `acesso` (a classe) e o `sha256`
do conteúdo de origem. O pipeline gerenciado reutiliza as definições do L200 (lab_ingestao) com objetos novos, o marcador
`vareleira-rag:l300`, o campo `acesso` projetado desse metadado e, por padrão, o indexador no ambiente de execução privado, criado
desabilitado e sem agenda. Nada aqui grava, executa ou apaga sem que quem chama peça; as funções de plano e de definição são puras ou
recebem o contêiner e o transporte por parâmetro, e podem ser testadas sem Azure.
"""

from __future__ import annotations

import argparse
import json
import posixpath
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Collection, Mapping, Sequence

import lab_acesso
import lab_comum
import lab_ingestao
from lab_comum import Documento, ErroLab, Inventario

RAIZ = lab_comum.RAIZ
MANIFESTO_PADRAO = RAIZ / "dados" / "l300" / "permissoes-documentais.json"
CONTAINER_PADRAO = "base-documental-l300"
PREFIXO_PADRAO = "vareleira-lar-l300"
INDICE_PADRAO = lab_acesso.INDICE_PADRAO
MARCADOR = "vareleira-rag:l300"  # na descrição de cada objeto: prova de que o L300 o criou
NIVEL = "L300"

ORIGEM_L100, ORIGEM_L300 = "l100", "l300"
ORIGENS = (ORIGEM_L100, ORIGEM_L300)
STATUS_REVISAO = ("pendente", "aprovada")
FRASE_SINTETICA = "Documento sintético"
INTERVALO_MINIMO, INTERVALO_MAXIMO = 5, 1440  # minutos: os limites de agenda do indexador (5 minutos a 24 horas)

# Estados do plano de blobs.
CRIAR, IGUAL, DIVERGENTE, METADADOS = "criar", "igual", "divergente", "metadados"
EXCLUIR, JA_EXCLUIDO, RESTAURAR, ATIVO, AUSENTE = "excluir", "ja-excluido", "restaurar", "ativo", "ausente"

_PADRAO_CONTAINER = re.compile(re.escape(CONTAINER_PADRAO) + r"(?:-[a-z0-9]{1,20}){0,3}")
_PADRAO_GUID = re.compile(r"[0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}")
# Mesmos formatos do inventário do L100, com os caminhos e os blobs restritos ao que o L300 permite.
_PADRAO_ID = re.compile(r"[A-Z0-9][A-Z0-9.-]{2,39}")
_PADRAO_SLUG = re.compile(r"[a-z0-9][a-z0-9-]{0,39}")
_PADRAO_VERSAO = re.compile(r"[0-9A-Za-z.-]{1,20}")
_PADRAO_SHA256 = re.compile(r"[0-9a-f]{64}")
_PADRAO_TIPO_CONTEUDO = re.compile(r"[a-z]+/[a-z0-9.+-]+(?:; charset=[A-Za-z0-9-]+)?")
_PADRAO_ARQUIVO = re.compile(r"dados/(l100|l300)/documentos/[a-z0-9][a-z0-9._-]{0,99}\.md")
_PADRAO_BLOB = re.compile(re.escape(PREFIXO_PADRAO) + r"/[a-z0-9][a-z0-9._-]{0,99}\.md")


# --------------------------------------------------------------------------------------
# Argumentos da linha de comando
# --------------------------------------------------------------------------------------

# Estes nomes entram em endereços que recebem o token e em objetos que o script pode apagar: só o formato do L300 é aceito.
validar_container_l300 = lab_comum.criar_validador(
    _PADRAO_CONTAINER,
    f"O contêiner do L300 deve ser '{CONTAINER_PADRAO}', com no máximo 3 sufixos de letras minúsculas e números ligados por hífen. "
    "O contêiner do L100 nunca é usado por esta ferramenta")
validar_indice_l300 = lab_comum.criar_validador(
    lab_acesso.PADRAO_INDICE_L300,
    f"O índice do L300 deve ser '{INDICE_PADRAO}', com no máximo 3 sufixos de letras minúsculas e números ligados por hífen. "
    "Os índices do L100 e do L200 nunca são usados por esta ferramenta")
validar_id_do_documento = lab_comum.criar_validador(_PADRAO_ID, "O ID do documento deve ser o de um documento do manifesto, como VLAR-OP-ATD-1.0")
validar_client_id = lab_comum.criar_validador(_PADRAO_GUID, "O client ID da identidade gerenciada deve ser um GUID")


def validar_intervalo(valor: str) -> int:
    try:
        minutos = int(valor)
    except ValueError:
        minutos = 0
    if not INTERVALO_MINIMO <= minutos <= INTERVALO_MAXIMO:
        raise argparse.ArgumentTypeError(
            f"O intervalo da agenda deve ser um número de minutos de {INTERVALO_MINIMO} a {INTERVALO_MAXIMO} (recebido: {valor!r}).")
    return minutos


def intervalo_iso(minutos: int | None) -> str | None:
    """Agenda do indexador em ISO 8601 (PT30M, PT2H, P1D); sem intervalo, o indexador não tem agenda."""
    if minutos is None:
        return None
    if minutos == INTERVALO_MAXIMO:
        return "P1D"
    return f"PT{minutos // 60}H" if minutos % 60 == 0 else f"PT{minutos}M"


# --------------------------------------------------------------------------------------
# Manifesto de permissões
# --------------------------------------------------------------------------------------

@dataclass(frozen=True)
class DocumentoL300:
    id: str
    titulo: str
    tipo: str
    produto: str
    versao: str
    origem: str
    arquivo: Path
    arquivo_relativo: str
    blob: str
    tipo_conteudo: str
    tamanho_bytes: int
    sha256: str
    acesso: str
    revisao_status: str

    @property
    def metadados_blob(self) -> dict[str, str]:
        """Metadados gravados no blob (só ASCII, pois viram cabeçalhos HTTP): a classe de acesso e o hash do conteúdo de origem."""
        return {
            "documento_id": self.id,
            "versao": self.versao,
            "produto": self.produto,
            "sha256": self.sha256,
            "sintetico": "true",
            lab_acesso.CAMPO_ACESSO: self.acesso,
        }

    def como_documento(self) -> Documento:
        """O mesmo documento no formato do inventário do L100, para reutilizar a análise de trechos do L200."""
        return Documento(
            id=self.id, titulo=self.titulo, tipo=self.tipo, produto=self.produto, versao=self.versao, arquivo=self.arquivo,
            blob=self.blob, tipo_conteudo=self.tipo_conteudo, tamanho_bytes=self.tamanho_bytes, sha256=self.sha256,
            revisao_status=self.revisao_status)


@dataclass(frozen=True)
class Manifesto:
    caminho: Path
    raiz: Path
    documentos: tuple[DocumentoL300, ...]

    @property
    def prefixo(self) -> str:
        return PREFIXO_PADRAO

    def por_id(self) -> dict[str, DocumentoL300]:
        return {documento.id: documento for documento in self.documentos}

    def inventario(self, sem: Collection[str] = ()) -> Inventario:
        """O manifesto no formato do inventário, para a análise de trechos e o aviso de revisão (`sem` exclui documentos por ID)."""
        documentos = tuple(documento.como_documento() for documento in self.documentos if documento.id not in sem)
        return Inventario(caminho=self.caminho, pasta_documentos=self.raiz / "dados" / "l300" / "documentos", documentos=documentos)


def _validar_documento(entrada: Any, indice: int, raiz: Path, problemas: list[str]) -> DocumentoL300 | None:
    rotulo = f"documentos[{indice}]"
    if not isinstance(entrada, dict):
        problemas.append(f"{rotulo}: deve ser um objeto.")
        return None
    inicio = len(problemas)

    def texto(chave: str, padrao: re.Pattern[str] | None = None) -> str | None:
        valor = entrada.get(chave)
        if not isinstance(valor, str) or not valor.strip():
            problemas.append(f"{rotulo}: campo '{chave}' ausente ou vazio.")
            return None
        if padrao is not None and not padrao.fullmatch(valor):
            problemas.append(f"{rotulo}: campo '{chave}' com formato inválido ({valor!r}).")
            return None
        return valor

    identificador = texto("id", _PADRAO_ID)
    if identificador:
        rotulo = identificador
    titulo, tipo = texto("titulo"), texto("tipo")
    produto, versao = texto("produto", _PADRAO_SLUG), texto("versao", _PADRAO_VERSAO)
    arquivo_relativo, blob = texto("arquivo", _PADRAO_ARQUIVO), texto("blob", _PADRAO_BLOB)
    tipo_conteudo, sha256 = texto("tipo_conteudo", _PADRAO_TIPO_CONTEUDO), texto("sha256", _PADRAO_SHA256)

    origem = entrada.get("origem")
    if origem not in ORIGENS:
        problemas.append(f"{rotulo}: 'origem' deve ser um destes valores: {', '.join(ORIGENS)}.")
    acesso = entrada.get("acesso")
    if not isinstance(acesso, str) or acesso not in lab_acesso.CLASSES:
        problemas.append(f"{rotulo}: 'acesso' ausente, vazio ou fora da lista de classes ({', '.join(lab_acesso.CLASSES)}). "
                         "Sem classe de acesso o documento é negado.")
    tamanho = entrada.get("tamanho_bytes")
    if isinstance(tamanho, bool) or not isinstance(tamanho, int) or not 0 <= tamanho <= lab_comum.LIMITE_TAMANHO_BYTES:
        problemas.append(f"{rotulo}: 'tamanho_bytes' deve ser um inteiro entre 0 e {lab_comum.LIMITE_TAMANHO_BYTES}.")
    revisao = entrada.get("revisao_real")
    status = revisao.get("status") if isinstance(revisao, dict) else None
    if status not in STATUS_REVISAO:
        problemas.append(f"{rotulo}: 'revisao_real.status' deve ser um destes valores: {list(STATUS_REVISAO)}.")

    alvo = None
    if arquivo_relativo:
        alvo = (raiz / arquivo_relativo).resolve()
        pasta_do_arquivo = _PADRAO_ARQUIVO.fullmatch(arquivo_relativo).group(1)  # type: ignore[union-attr]
        if not alvo.is_relative_to((raiz / "dados").resolve()):
            problemas.append(f"{rotulo}: o arquivo precisa ficar dentro da pasta 'dados' do projeto.")
        elif origem in ORIGENS and pasta_do_arquivo != origem:
            problemas.append(f"{rotulo}: um documento de origem {origem} precisa estar em dados/{origem}/documentos.")

    if len(problemas) > inicio or alvo is None:
        return None
    return DocumentoL300(
        id=identificador, titulo=titulo, tipo=tipo, produto=produto, versao=versao, origem=origem,  # type: ignore[arg-type]
        arquivo=alvo, arquivo_relativo=arquivo_relativo, blob=blob, tipo_conteudo=tipo_conteudo,  # type: ignore[arg-type]
        tamanho_bytes=tamanho, sha256=sha256, acesso=acesso, revisao_status=status)  # type: ignore[arg-type]


def _conferir_com_o_inventario_do_l100(documentos: Sequence[DocumentoL300], raiz: Path, problemas: list[str]) -> None:
    """Os documentos de origem L100 são os do inventário do L100, byte a byte: o manifesto só os classifica."""
    do_l100 = [documento for documento in documentos if documento.origem == ORIGEM_L100]
    if not do_l100:
        return
    try:
        inventario = lab_comum.carregar_inventario(raiz / "dados" / "l100" / "inventario.json")
    except ErroLab as erro:
        problemas.append("Não foi possível conferir os documentos do L100 com o inventário do L100: " + str(erro).splitlines()[0])
        return
    referencias = {documento.id: documento for documento in inventario.documentos}
    for documento in do_l100:
        referencia = referencias.get(documento.id)
        if referencia is None:
            problemas.append(f"{documento.id}: não existe no inventário do L100, mas o manifesto o declara de origem {ORIGEM_L100}.")
            continue
        diferentes = [campo for campo, no_manifesto, no_inventario in (
            ("titulo", documento.titulo, referencia.titulo), ("tipo", documento.tipo, referencia.tipo),
            ("produto", documento.produto, referencia.produto), ("versao", documento.versao, referencia.versao),
            ("tipo_conteudo", documento.tipo_conteudo, referencia.tipo_conteudo),
            ("tamanho_bytes", documento.tamanho_bytes, referencia.tamanho_bytes), ("sha256", documento.sha256, referencia.sha256),
            ("revisao_real.status", documento.revisao_status, referencia.revisao_status),
            ("arquivo", documento.arquivo, referencia.arquivo.resolve())) if no_manifesto != no_inventario]
        if diferentes:
            problemas.append(f"{documento.id}: o manifesto difere do inventário do L100 em {', '.join(diferentes)}. "
                             "Os documentos do L100 não mudam no L300.")


def carregar_manifesto(caminho: Path | None = None, raiz: Path | None = None) -> Manifesto:
    """Lê e valida a estrutura do manifesto e a identidade dos documentos do L100. Não lê os arquivos de conteúdo nem a rede.

    Os caminhos dos documentos são relativos à `raiz` do projeto (a do repositório, por padrão) e precisam ficar dentro de dados/.
    """
    raiz = Path(raiz or RAIZ)
    caminho = Path(caminho or MANIFESTO_PADRAO)
    try:
        bruto = json.loads(caminho.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ErroLab(f"Manifesto de permissões não encontrado: {lab_comum._mostrar_caminho(caminho)}") from None
    except json.JSONDecodeError as erro:
        raise ErroLab(f"Manifesto com JSON inválido (linha {erro.lineno}, coluna {erro.colno}).") from None
    except (OSError, UnicodeDecodeError) as erro:
        raise ErroLab(f"Não foi possível ler o manifesto: {type(erro).__name__}.") from None
    if not isinstance(bruto, dict):
        raise ErroLab("O manifesto precisa ser um objeto JSON.")

    problemas: list[str] = []
    if bruto.get("schema_version") != 1:
        problemas.append("'schema_version' deve ser 1.")
    if bruto.get("sintetico") is not True:
        problemas.append("O manifesto precisa declarar \"sintetico\": true. Use apenas documentos sintéticos.")
    classes = bruto.get("classes")
    if not (isinstance(classes, list) and all(isinstance(classe, str) for classe in classes) and len(classes) == len(set(classes))
            and set(classes) == set(lab_acesso.CLASSES)):
        problemas.append(f"'classes' deve listar exatamente as classes permitidas: {', '.join(lab_acesso.CLASSES)}.")
    entradas = bruto.get("documentos")
    documentos: list[DocumentoL300] = []
    if not isinstance(entradas, list) or not entradas:
        problemas.append("'documentos' deve ser uma lista com pelo menos um item.")
    else:
        for indice, entrada in enumerate(entradas):
            documento = _validar_documento(entrada, indice, raiz, problemas)
            if documento:
                documentos.append(documento)
        for campo in ("id", "blob", "arquivo"):
            vistos: set[Any] = set()
            for documento in documentos:
                valor = getattr(documento, campo)
                if valor in vistos:
                    problemas.append(f"Valor repetido no campo '{campo}': {valor}.")
                vistos.add(valor)
        _conferir_com_o_inventario_do_l100(documentos, raiz, problemas)
    if problemas:
        raise ErroLab("Manifesto de permissões inválido (nada foi enviado nem lido no Azure):\n  - " + "\n  - ".join(problemas))
    return Manifesto(caminho=caminho, raiz=raiz, documentos=tuple(documentos))


def validar_arquivos(manifesto: Manifesto) -> None:
    """Confere cada arquivo (tamanho, hash do conteúdo normalizado, declaração de sintético, ID e versão) e nega o que o manifesto não lista."""
    problemas: list[str] = []
    for documento in manifesto.documentos:
        if not documento.arquivo.is_file():
            problemas.append(f"{documento.id}: arquivo não encontrado ({documento.arquivo_relativo}).")
            continue
        dados = lab_comum.normalizar_texto(documento.arquivo.read_bytes())
        try:
            conteudo = dados.decode("utf-8")
        except UnicodeDecodeError:
            problemas.append(f"{documento.id}: o arquivo precisa estar codificado em UTF-8.")
            continue
        if len(dados) != documento.tamanho_bytes:
            problemas.append(f"{documento.id}: tamanho diferente do manifesto ({len(dados)} bytes em vez de {documento.tamanho_bytes}).")
        if lab_comum.calcular_sha256(dados) != documento.sha256:
            problemas.append(f"{documento.id}: o conteúdo é diferente do manifesto (o hash não confere).")
        if FRASE_SINTETICA not in conteudo:
            problemas.append(f"{documento.id}: o documento precisa se declarar sintético ('{FRASE_SINTETICA}').")
        if f"| Identificador | {documento.id} |" not in conteudo or f"| Versão | {documento.versao} |" not in conteudo:
            problemas.append(f"{documento.id}: o identificador e a versão do documento não combinam com o manifesto.")
    pasta = manifesto.raiz / "dados" / "l300" / "documentos"
    if not pasta.is_dir():
        problemas.append("A pasta dados/l300/documentos não foi encontrada.")
    else:
        listados = {documento.arquivo for documento in manifesto.documentos}
        for caminho in sorted(pasta.iterdir()):
            ignorado = caminho.name.startswith(".") or caminho.name.lower() in lab_comum.ARQUIVOS_IGNORADOS
            if caminho.is_file() and not ignorado and caminho.resolve() not in listados:
                problemas.append(f"Arquivo sem permissão declarada: {caminho.name}. Sem classe de acesso no manifesto, ele é negado: "
                                 "inclua-o no manifesto ou remova-o da pasta.")
    if problemas:
        raise ErroLab("Arquivos locais não conferem com o manifesto de permissões:\n  - " + "\n  - ".join(problemas))


def carregar_e_validar(caminho: Path | None = None, raiz: Path | None = None) -> Manifesto:
    manifesto = carregar_manifesto(caminho, raiz)
    validar_arquivos(manifesto)
    return manifesto


def selecionar_documentos(manifesto: Manifesto, ids: Sequence[str] | None, *, somente_origem: str | None = None) -> list[DocumentoL300]:
    """Os documentos pedidos (ou todos). Com `somente_origem`, qualquer outro é recusado: as cópias do L100 ficam protegidas."""
    por_id = manifesto.por_id()
    if not ids:
        escolhidos = list(manifesto.documentos)
    else:
        desconhecidos = [identificador for identificador in dict.fromkeys(ids) if identificador not in por_id]
        if desconhecidos:
            raise ErroLab(f"Documento(s) fora do manifesto: {', '.join(desconhecidos)}. Documentos do manifesto: {', '.join(por_id)}.")
        escolhidos = [por_id[identificador] for identificador in dict.fromkeys(ids)]
    if somente_origem:
        recusados = [documento.id for documento in escolhidos if documento.origem != somente_origem]
        if recusados:
            alvos = [documento.id for documento in manifesto.documentos if documento.origem == somente_origem]
            raise ErroLab(f"Esta etapa só atua em documentos de origem {somente_origem.upper()} ({', '.join(alvos) or 'nenhum'}); "
                          f"as cópias dos documentos do L100 ficam protegidas: {', '.join(recusados)}.")
    return escolhidos


# --------------------------------------------------------------------------------------
# Blobs: carregar, excluir e restaurar (só os blobs do manifesto, no contêiner e na pasta do L300)
# --------------------------------------------------------------------------------------

@dataclass(frozen=True)
class AcaoBlob:
    documento: DocumentoL300
    estado: str
    etag: str | None = None
    detalhe: str = ""


def _metadados_diferentes(esperados: Mapping[str, str], atuais: Mapping[str, str] | None) -> list[str]:
    atuais = atuais or {}
    return [chave for chave, valor in esperados.items() if atuais.get(chave) != valor]


def _blob_com_conteudo_igual(cliente: Any, documento: DocumentoL300, propriedades: Any) -> tuple[bool, str | None]:
    """(conteúdo igual ao do manifesto, ETag lido). Só baixa o blob quando o tamanho coincide, para não ler um blob inesperadamente grande."""
    if propriedades.size != documento.tamanho_bytes:
        return False, propriedades.etag
    baixado = cliente.download_blob()
    return lab_comum.calcular_sha256(baixado.readall()) == documento.sha256, baixado.properties.etag


def _excluido_reversivelmente(container: Any, blob: str) -> bool:
    return any(item.name == blob and getattr(item, "deleted", False)
               for item in container.list_blobs(name_starts_with=blob, include=["deleted"]))


def planejar_carga(container: Any, documentos: Sequence[DocumentoL300]) -> list[AcaoBlob]:
    """Compara cada cópia do manifesto com o contêiner do L300 (conteúdo e metadados). Somente leitura."""
    from azure.core.exceptions import ResourceNotFoundError

    acoes: list[AcaoBlob] = []
    for documento in documentos:
        cliente = container.get_blob_client(documento.blob)
        try:
            propriedades = cliente.get_blob_properties()
        except ResourceNotFoundError as erro:
            if lab_comum.codigo_do_erro(erro) == "ContainerNotFound":
                raise
            acoes.append(AcaoBlob(documento, CRIAR))
            continue
        igual, etag = _blob_com_conteudo_igual(cliente, documento, propriedades)
        if not igual:
            acoes.append(AcaoBlob(documento, DIVERGENTE, etag or propriedades.etag, "conteúdo diferente do manifesto"))
            continue
        diferentes = _metadados_diferentes(documento.metadados_blob, getattr(propriedades, "metadata", None))
        if diferentes:
            acoes.append(AcaoBlob(documento, METADADOS, etag or propriedades.etag, "metadados diferentes: " + ", ".join(diferentes)))
        else:
            acoes.append(AcaoBlob(documento, IGUAL, etag or propriedades.etag))
    return acoes


def aplicar_carga(container: Any, acoes: Sequence[AcaoBlob]) -> dict[str, int]:
    """Envia o que o plano indica. Criação só se o blob não existir; troca e metadados só com o ETag planejado."""
    from azure.core import MatchConditions
    from azure.core.exceptions import ResourceExistsError, ResourceModifiedError
    from azure.storage.blob import ContentSettings

    resultado = {"criados": 0, "substituidos": 0, "metadados": 0, "iguais": 0}
    for acao in acoes:
        documento = acao.documento
        if acao.estado == IGUAL:
            resultado["iguais"] += 1
            print(f"[IGUAL]    {documento.id}: já existe com o mesmo conteúdo e a mesma classe de acesso; nada a fazer.")
            continue
        cliente = container.get_blob_client(documento.blob)
        conteudo = lab_comum.normalizar_texto(documento.arquivo.read_bytes())
        if lab_comum.calcular_sha256(conteudo) != documento.sha256:
            raise ErroLab(f"{documento.id}: o arquivo mudou durante a execução. Rode a simulação de novo.")
        try:
            if acao.estado == METADADOS:
                cliente.set_blob_metadata(documento.metadados_blob, etag=acao.etag, match_condition=MatchConditions.IfNotModified)
                resultado["metadados"] += 1
                print(f"[METADADOS] {documento.id}: metadados atualizados no blob do L300 (classe de acesso: {documento.acesso}).")
                continue
            opcoes: dict[str, Any] = {
                "metadata": documento.metadados_blob,
                "content_settings": ContentSettings(content_type=documento.tipo_conteudo, content_language="pt-BR"),
            }
            if acao.estado == DIVERGENTE:
                opcoes.update(overwrite=True, etag=acao.etag, match_condition=MatchConditions.IfNotModified)
            else:
                opcoes["overwrite"] = False
            cliente.upload_blob(conteudo, **opcoes)
        except (ResourceExistsError, ResourceModifiedError):
            raise ErroLab(f"{documento.id}: o blob mudou depois da simulação. Nada foi sobrescrito; rode a simulação de novo.",
                          lab_comum.CODIGO_DIVERGENCIA) from None
        if acao.estado == DIVERGENTE:
            resultado["substituidos"] += 1
            print(f"[TROCADO]  {documento.id}: conteúdo anterior substituído (recuperável pela exclusão reversível).")
        else:
            resultado["criados"] += 1
            print(f"[CRIADO]   {documento.id}: enviado como {documento.blob} (classe de acesso: {documento.acesso}).")
    return resultado


def listar_orfaos(container: Any, manifesto: Manifesto) -> list[str]:
    """Blobs ativos na pasta do L300 que o manifesto não declara.

    O manifesto rege só o que a ferramenta envia: o indexador lê a pasta inteira e o filtro do chat autoriza classes, não IDs do
    manifesto. Um blob assim é indexado e, com uma classe permitida no metadado `acesso`, recuperável pelo chat; aqui ele é só
    apontado (aviso do carregar e reprovação do conferir), nunca apagado.
    """
    conhecidos = {documento.blob for documento in manifesto.documentos}
    return sorted(item.name for item in container.list_blobs(name_starts_with=f"{manifesto.prefixo}/") if item.name not in conhecidos)


def planejar_exclusao(container: Any, documentos: Sequence[DocumentoL300]) -> list[AcaoBlob]:
    """Para cada documento: existe (EXCLUIR), já foi excluído de forma reversível (JA_EXCLUIDO) ou não existe (AUSENTE). Somente leitura."""
    from azure.core.exceptions import ResourceNotFoundError

    acoes: list[AcaoBlob] = []
    for documento in documentos:
        try:
            propriedades = container.get_blob_client(documento.blob).get_blob_properties()
        except ResourceNotFoundError as erro:
            if lab_comum.codigo_do_erro(erro) == "ContainerNotFound":
                raise
            acoes.append(AcaoBlob(documento, JA_EXCLUIDO if _excluido_reversivelmente(container, documento.blob) else AUSENTE))
            continue
        acoes.append(AcaoBlob(documento, EXCLUIR, propriedades.etag))
    return acoes


def aplicar_exclusao(container: Any, acoes: Sequence[AcaoBlob]) -> int:
    """Exclusão reversível (soft delete): só do blob planejado, com o ETag lido, e só dos documentos de origem L300."""
    from azure.core import MatchConditions
    from azure.core.exceptions import ResourceModifiedError, ResourceNotFoundError

    excluidos = 0
    for acao in acoes:
        if acao.estado != EXCLUIR:
            continue
        try:
            container.get_blob_client(acao.documento.blob).delete_blob(
                delete_snapshots="include", etag=acao.etag, match_condition=MatchConditions.IfNotModified)
        except (ResourceModifiedError, ResourceNotFoundError):
            raise ErroLab(f"{acao.documento.id}: o blob mudou depois da simulação. Nada foi excluído; rode a simulação de novo.",
                          lab_comum.CODIGO_DIVERGENCIA) from None
        excluidos += 1
        print(f"[EXCLUIDO] {acao.documento.id}: {acao.documento.blob} excluído de forma reversível (soft delete); "
              "os trechos saem do índice na próxima execução do indexador.")
    return excluidos


def planejar_restauracao(container: Any, documentos: Sequence[DocumentoL300]) -> list[AcaoBlob]:
    """Para cada documento: já ativo (ATIVO), excluído de forma reversível (RESTAURAR) ou sem versão a restaurar (AUSENTE). Somente leitura."""
    from azure.core.exceptions import ResourceNotFoundError

    acoes: list[AcaoBlob] = []
    for documento in documentos:
        try:
            container.get_blob_client(documento.blob).get_blob_properties()
        except ResourceNotFoundError as erro:
            if lab_comum.codigo_do_erro(erro) == "ContainerNotFound":
                raise
            acoes.append(AcaoBlob(documento, RESTAURAR if _excluido_reversivelmente(container, documento.blob) else AUSENTE))
            continue
        acoes.append(AcaoBlob(documento, ATIVO))
    return acoes


def _mensagem_da_restauracao_divergente(documento: DocumentoL300, feitos: Sequence[str], nao_processados: Sequence[str]) -> str:
    mensagem = (
        f"{documento.id}: o blob {documento.blob} foi restaurado, mas o conteúdo restaurado difere do manifesto (o hash não confere). "
        "Os metadados do manifesto (classe de acesso) NÃO foram reaplicados: o blob segue com os metadados que tinha quando foi "
        "excluído, sem conferência. A divergência exige reposição autorizada (--etapa carregar --documento "
        f"{documento.id} --executar --substituir-divergentes), e a indexação deve aguardar essa conferência: não execute o indexador antes.")
    if feitos:
        mensagem += " Já restaurados, com os metadados do manifesto, nesta execução: " + ", ".join(feitos) + "."
    if nao_processados:
        mensagem += " Não processados (seguem excluídos de forma reversível): " + ", ".join(nao_processados) + "."
    return mensagem


def aplicar_restauracao(container: Any, acoes: Sequence[AcaoBlob]) -> int:
    """Restaura o blob excluído e, só se o conteúdo restaurado for o do manifesto, reaplica os metadados do manifesto.

    Reaplicar os metadados garante a classe de acesso do manifesto mesmo que a versão restaurada tivesse outra e atualiza a data de
    modificação do blob, que é o que faz o indexador reprocessá-lo. Mas a classe do manifesto vale para o conteúdo que o manifesto
    declara, não para bytes que ninguém autorizou: se o conteúdo restaurado diverge, nada é reaplicado e o erro de divergência para
    a etapa (sem seguir para os próximos documentos). O blob já está restaurado, com os metadados que tinha ao ser excluído; a
    reposição do conteúdo exige `carregar --substituir-divergentes`, e a indexação deve aguardar essa conferência.
    """
    from azure.core import MatchConditions
    from azure.core.exceptions import ResourceModifiedError, ResourceNotFoundError

    pendentes = [acao for acao in acoes if acao.estado == RESTAURAR]
    feitos: list[str] = []
    for posicao, acao in enumerate(pendentes):
        documento = acao.documento
        cliente = container.get_blob_client(documento.blob)
        try:
            cliente.undelete_blob()
            propriedades = cliente.get_blob_properties()
            igual, etag = _blob_com_conteudo_igual(cliente, documento, propriedades)
            if igual:
                cliente.set_blob_metadata(documento.metadados_blob, etag=etag or propriedades.etag,
                                          match_condition=MatchConditions.IfNotModified)
        except (ResourceModifiedError, ResourceNotFoundError):
            raise ErroLab(f"{documento.id}: o blob mudou durante a restauração e pode já ter sido restaurado, sem os metadados do "
                          "manifesto. Rode a simulação de novo e confira o resultado antes de executar o indexador.",
                          lab_comum.CODIGO_DIVERGENCIA) from None
        if not igual:
            raise ErroLab(_mensagem_da_restauracao_divergente(
                documento, feitos, [seguinte.documento.id for seguinte in pendentes[posicao + 1:]]), lab_comum.CODIGO_DIVERGENCIA)
        feitos.append(documento.id)
        print(f"[RESTAURADO] {documento.id}: {documento.blob} restaurado; metadados do manifesto reaplicados "
              f"(classe de acesso: {documento.acesso}).")
    return len(feitos)


# --------------------------------------------------------------------------------------
# Pipeline gerenciado do L300 (objetos novos, definições reutilizadas do L200)
# --------------------------------------------------------------------------------------

def nomes_dos_objetos(indice: str) -> lab_ingestao.Nomes:
    """Os quatro objetos do L300, derivados do índice, que precisa ter o prefixo do L300: nada do L100 ou do L200 entra aqui."""
    if not lab_acesso.indice_l300(indice):
        raise ErroLab(f"O nome '{indice}' não é um índice do L300 (prefixo '{INDICE_PADRAO}'): nada será criado nem apagado com ele.")
    return lab_ingestao.Nomes(indice, f"{indice}-fonte", f"{indice}-skillset", f"{indice}-indexador")


def parametros_do_pipeline(manifesto: Manifesto, args: argparse.Namespace) -> lab_ingestao.Parametros:
    """Parâmetros do pipeline: campo `acesso`, marcador do L300, execução privada (padrão) e agenda só se pedida."""
    if posixpath.commonpath([posixpath.dirname(documento.blob) for documento in manifesto.documentos]) != manifesto.prefixo:
        raise ErroLab(f"Os blobs do manifesto precisam estar na pasta '{manifesto.prefixo}' do contêiner do L300.")
    return lab_ingestao.Parametros(
        nomes_dos_objetos(args.indice), args.assinatura, args.grupo, args.conta, args.container, manifesto.prefixo, args.modelos,
        args.deployment, args.modelo_embeddings, args.dimensoes, args.tamanho_maximo, args.sobreposicao,
        marcador=MARCADOR, nivel=NIVEL, acesso=True, privado=args.privado is not False, intervalo=intervalo_iso(args.intervalo))


def abrir_cliente(busca: str, tenant_id: str | None = None, versao_api: str = lab_ingestao.VERSAO_API,
                  credencial: Any = None) -> lab_ingestao.ClienteBusca:
    """Cliente REST do serviço de busca, com a sessão do Azure CLI ou com a `credencial` informada (identidade gerenciada)."""
    return lab_ingestao.ClienteBusca(busca, tenant_id, credencial, versao_api=versao_api)


def abrir_container(conta: str, container: str, tenant_id: str | None = None, credencial: Any = None) -> Any:
    return lab_comum.criar_container(conta, container, tenant_id, credencial)


def criar_credencial_gerenciada(client_id: str | None) -> Any:
    """Identidade gerenciada do computador ou do serviço onde a ferramenta roda (o `client_id` escolhe a atribuída pelo usuário)."""
    try:
        from azure.identity import ManagedIdentityCredential
    except ImportError:
        raise ErroLab("Biblioteca do Azure não encontrada. Ative o ambiente virtual e execute: "
                      "python -m pip install -r requirements/l100.txt") from None
    return ManagedIdentityCredential(client_id=client_id)


# --------------------------------------------------------------------------------------
# Conferência dos trechos: classe de acesso de cada trecho contra o manifesto
# --------------------------------------------------------------------------------------

@dataclass(frozen=True)
class QualidadeAcesso:
    trechos: int
    por_documento: Mapping[str, int]
    por_classe: Mapping[str, int]
    sem_classe: int
    classe_desconhecida: int
    classe_diferente: int
    fora_do_manifesto: int


def analisar_acesso(trechos: Sequence[Mapping[str, Any]], manifesto: Manifesto) -> QualidadeAcesso:
    """Mede os trechos contra o manifesto: classe ausente, desconhecida ou diferente da declarada, e documentos que ele não conhece."""
    esperado = {documento.id: documento.acesso for documento in manifesto.documentos}
    por_documento: dict[str, int] = {}
    por_classe: dict[str, int] = {}
    sem_classe = desconhecida = diferente = fora = 0
    for trecho in trechos:
        identificador = str(trecho.get("documento_id") or "")
        por_documento[identificador] = por_documento.get(identificador, 0) + 1
        classe = trecho.get(lab_acesso.CAMPO_ACESSO)
        if not isinstance(classe, str) or not classe.strip():
            sem_classe += 1
        elif classe not in lab_acesso.CLASSES:
            desconhecida += 1
        else:
            por_classe[classe] = por_classe.get(classe, 0) + 1
            diferente += identificador in esperado and esperado[identificador] != classe
        fora += identificador not in esperado
    return QualidadeAcesso(len(trechos), por_documento, por_classe, sem_classe, desconhecida, diferente, fora)


def problemas_de_acesso(qualidade: QualidadeAcesso) -> list[str]:
    """O que impede de confiar na classe de acesso do índice: um trecho assim nunca poderia ser entregue ao perfil certo."""
    problemas = []
    if qualidade.sem_classe:
        problemas.append(f"{qualidade.sem_classe} trecho(s) sem classe de acesso (nunca são recuperados)")
    if qualidade.classe_desconhecida:
        problemas.append(f"{qualidade.classe_desconhecida} trecho(s) com classe de acesso fora da lista (nunca são recuperados)")
    if qualidade.classe_diferente:
        problemas.append(f"{qualidade.classe_diferente} trecho(s) com classe diferente da do manifesto")
    if qualidade.fora_do_manifesto:
        problemas.append(f"{qualidade.fora_do_manifesto} trecho(s) de documento que o manifesto não declara")
    return problemas
