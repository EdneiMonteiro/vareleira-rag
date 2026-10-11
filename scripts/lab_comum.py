"""Regras compartilhadas pelos scripts do laboratório Vareleira RAG (L100).

O inventário é a lista de permissão: só o que estiver nele pode ser enviado. O hash
confere o conteúdo, e os nomes recebidos pela linha de comando são validados antes de
qualquer acesso ao Azure. Este módulo usa apenas a biblioteca padrão; os pacotes do
Azure são importados quando necessários, para exibir uma mensagem clara se faltarem.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

RAIZ = Path(__file__).resolve().parents[1]
INVENTARIO_PADRAO = RAIZ / "dados" / "l100" / "inventario.json"
CONTAINER_PADRAO = "base-documental"
LIMITE_TAMANHO_BYTES = 1_048_576
SUFIXO_BLOB = "blob.core.windows.net"
ARQUIVOS_IGNORADOS = {"desktop.ini", "thumbs.db"}

CODIGO_OK = 0
CODIGO_USO = 1  # argumentos, inventário ou arquivos locais inválidos
CODIGO_ACESSO = 2  # autenticação, permissão, rede ou serviço do Azure
CODIGO_DIVERGENCIA = 3  # conteúdo diferente do inventário
CODIGO_INESPERADO = 4  # defeito do script: use --detalhes e abra uma issue

_PADRAO_CONTA = re.compile(r"[a-z0-9]{3,24}")
_PADRAO_CONTAINER = re.compile(r"(?!.*--)[a-z0-9][a-z0-9-]{1,61}[a-z0-9]")
_PADRAO_TENANT = re.compile(r"[0-9A-Za-z.-]{1,255}")
_PADRAO_ID = re.compile(r"[A-Z0-9][A-Z0-9.-]{2,39}")
_PADRAO_SLUG = re.compile(r"[a-z0-9][a-z0-9-]{0,39}")
_PADRAO_VERSAO = re.compile(r"[0-9A-Za-z.-]{1,20}")
_PADRAO_ARQUIVO = re.compile(r"documentos/[a-z0-9][a-z0-9._-]{0,99}")
_PADRAO_BLOB = re.compile(r"[a-z0-9][a-z0-9._/-]{0,254}")
_PADRAO_SHA256 = re.compile(r"[0-9a-f]{64}")
_PADRAO_TIPO_CONTEUDO = re.compile(r"[a-z]+/[a-z0-9.+-]+(?:; charset=[A-Za-z0-9-]+)?")
_PADRAO_DATA = re.compile(r"\d{4}-\d{2}-\d{2}")
_STATUS_REVISAO = {"pendente", "aprovada"}


class ErroLab(Exception):
    """Erro esperado, com a mensagem já escrita para quem executa o laboratório."""

    def __init__(self, mensagem: str, codigo: int = CODIGO_USO):
        super().__init__(mensagem)
        self.codigo = codigo


@dataclass(frozen=True)
class Documento:
    id: str
    titulo: str
    tipo: str
    produto: str
    versao: str
    arquivo: Path
    blob: str
    tipo_conteudo: str
    tamanho_bytes: int
    sha256: str
    revisao_status: str
    vigencia_inicio: str = ""
    vigencia_fim: str | None = None

    @property
    def metadados_blob(self) -> dict[str, str]:
        """Metadados gravados no blob. Só ASCII, pois viram cabeçalhos HTTP."""
        return {
            "documento_id": self.id,
            "versao": self.versao,
            "produto": self.produto,
            "sha256": self.sha256,
            "sintetico": "true",
        }


@dataclass(frozen=True)
class Inventario:
    caminho: Path
    pasta_documentos: Path
    documentos: tuple[Documento, ...]


@dataclass(frozen=True)
class Verificacao:
    """Resultado de uma conferência: o que foi checado, se passou e o detalhe mostrado a quem executa."""

    nome: str
    ok: bool
    detalhe: str = ""


def normalizar_texto(dados: bytes) -> bytes:
    """Troca CRLF por LF: o mesmo texto gera o mesmo hash em qualquer sistema."""
    return dados.replace(b"\r\n", b"\n")


def calcular_sha256(dados: bytes) -> str:
    return hashlib.sha256(dados).hexdigest()


def ler_conteudo(documento: Documento) -> bytes:
    """Lê o arquivo local e devolve o conteúdo normalizado, que é o enviado ao Azure."""
    return normalizar_texto(documento.arquivo.read_bytes())


def _mostrar_caminho(caminho: Path) -> str:
    try:
        return str(caminho.resolve().relative_to(RAIZ))
    except ValueError:
        return str(caminho)


def _validar_entrada(entrada: Any, indice: int, pasta_documentos: Path, problemas: list[str]) -> Documento | None:
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
    titulo = texto("titulo")
    tipo = texto("tipo")
    produto = texto("produto", _PADRAO_SLUG)
    versao = texto("versao", _PADRAO_VERSAO)
    texto("autoridade_narrativa")
    texto("origem")
    texto("licenca")
    arquivo_relativo = texto("arquivo", _PADRAO_ARQUIVO)
    blob = texto("blob", _PADRAO_BLOB)
    tipo_conteudo = texto("tipo_conteudo", _PADRAO_TIPO_CONTEUDO)
    sha256 = texto("sha256", _PADRAO_SHA256)

    if blob and (".." in blob or "//" in blob or blob.endswith("/")):
        problemas.append(f"{rotulo}: campo 'blob' não pode conter '..', '//' ou terminar em '/'.")

    tamanho = entrada.get("tamanho_bytes")
    if isinstance(tamanho, bool) or not isinstance(tamanho, int) or not 0 <= tamanho <= LIMITE_TAMANHO_BYTES:
        problemas.append(f"{rotulo}: 'tamanho_bytes' deve ser um inteiro entre 0 e {LIMITE_TAMANHO_BYTES}.")

    vigencia = entrada.get("vigencia_ficticia")
    if not isinstance(vigencia, dict) or not _PADRAO_DATA.fullmatch(str(vigencia.get("inicio", ""))):
        problemas.append(f"{rotulo}: 'vigencia_ficticia.inicio' deve ter o formato AAAA-MM-DD.")
    elif vigencia.get("fim") is not None and not _PADRAO_DATA.fullmatch(str(vigencia["fim"])):
        problemas.append(f"{rotulo}: 'vigencia_ficticia.fim' deve ser nulo ou ter o formato AAAA-MM-DD.")

    acesso = entrada.get("classificacao_acesso")
    if not isinstance(acesso, dict) or not isinstance(acesso.get("nivel"), str) or not acesso["nivel"].strip():
        problemas.append(f"{rotulo}: 'classificacao_acesso.nivel' ausente ou vazio.")

    revisao = entrada.get("revisao_real")
    status_revisao = revisao.get("status") if isinstance(revisao, dict) else None
    if status_revisao not in _STATUS_REVISAO:
        problemas.append(f"{rotulo}: 'revisao_real.status' deve ser um destes valores: {sorted(_STATUS_REVISAO)}.")

    alvo = None
    if arquivo_relativo:
        alvo = (pasta_documentos.parent / arquivo_relativo).resolve()
        if not alvo.is_relative_to(pasta_documentos.resolve()):
            problemas.append(f"{rotulo}: o arquivo precisa ficar dentro da pasta 'documentos'.")

    if len(problemas) > inicio or alvo is None:
        return None
    return Documento(
        id=identificador, titulo=titulo, tipo=tipo, produto=produto, versao=versao,
        arquivo=alvo, blob=blob, tipo_conteudo=tipo_conteudo, tamanho_bytes=tamanho,
        sha256=sha256, revisao_status=status_revisao,
        vigencia_inicio=vigencia["inicio"], vigencia_fim=vigencia.get("fim"),
    )


def carregar_inventario(caminho: Path = INVENTARIO_PADRAO) -> Inventario:
    """Lê e valida a estrutura do inventário. Não confere os arquivos locais."""
    caminho = Path(caminho)
    try:
        bruto = json.loads(caminho.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ErroLab(f"Inventário não encontrado: {_mostrar_caminho(caminho)}") from None
    except json.JSONDecodeError as erro:
        raise ErroLab(f"Inventário com JSON inválido (linha {erro.lineno}, coluna {erro.colno}).") from None
    except (OSError, UnicodeDecodeError) as erro:
        raise ErroLab(f"Não foi possível ler o inventário: {type(erro).__name__}.") from None
    if not isinstance(bruto, dict):
        raise ErroLab("O inventário precisa ser um objeto JSON.")

    problemas: list[str] = []
    if bruto.get("schema_version") != 1:
        problemas.append("'schema_version' deve ser 1.")
    if bruto.get("sintetico") is not True:
        problemas.append("O inventário precisa declarar \"sintetico\": true. Use apenas documentos sintéticos.")
    entradas = bruto.get("documentos")
    pasta_documentos = caminho.parent / "documentos"
    documentos: list[Documento] = []
    if not isinstance(entradas, list) or not entradas:
        problemas.append("'documentos' deve ser uma lista com pelo menos um item.")
    else:
        for indice, entrada in enumerate(entradas):
            documento = _validar_entrada(entrada, indice, pasta_documentos, problemas)
            if documento:
                documentos.append(documento)
        for campo in ("id", "blob", "arquivo"):
            vistos: set[Any] = set()
            for documento in documentos:
                valor = getattr(documento, campo)
                if valor in vistos:
                    problemas.append(f"Valor repetido no campo '{campo}': {valor}.")
                vistos.add(valor)
    if problemas:
        raise ErroLab("Inventário inválido:\n  - " + "\n  - ".join(problemas))
    return Inventario(caminho=caminho, pasta_documentos=pasta_documentos, documentos=tuple(documentos))


def validar_arquivos_locais(inventario: Inventario) -> None:
    """Confere tamanho e hash de cada arquivo e recusa arquivos fora do inventário."""
    problemas: list[str] = []
    for documento in inventario.documentos:
        if not documento.arquivo.is_file():
            problemas.append(f"{documento.id}: arquivo não encontrado ({_mostrar_caminho(documento.arquivo)}).")
            continue
        dados = ler_conteudo(documento)
        try:
            dados.decode("utf-8")
        except UnicodeDecodeError:
            problemas.append(f"{documento.id}: o arquivo precisa estar codificado em UTF-8.")
            continue
        if len(dados) != documento.tamanho_bytes:
            problemas.append(
                f"{documento.id}: tamanho diferente do inventário ({len(dados)} bytes em vez de {documento.tamanho_bytes})."
            )
        if calcular_sha256(dados) != documento.sha256:
            problemas.append(f"{documento.id}: o conteúdo é diferente do inventário revisado (o hash não confere).")
    if not inventario.pasta_documentos.is_dir():
        problemas.append("A pasta 'documentos' não foi encontrada ao lado do inventário.")
    else:
        listados = {documento.arquivo.resolve() for documento in inventario.documentos}
        for caminho in sorted(inventario.pasta_documentos.iterdir()):
            ignorado = caminho.name.startswith(".") or caminho.name.lower() in ARQUIVOS_IGNORADOS
            if caminho.is_file() and not ignorado and caminho.resolve() not in listados:
                problemas.append(
                    f"Arquivo fora do inventário: {caminho.name}. Inclua-o no inventário ou remova-o da pasta."
                )
    if problemas:
        raise ErroLab("Arquivos locais não conferem com o inventário:\n  - " + "\n  - ".join(problemas))


def carregar_e_validar(caminho: Path = INVENTARIO_PADRAO) -> Inventario:
    inventario = carregar_inventario(caminho)
    validar_arquivos_locais(inventario)
    return inventario


def aviso_de_revisao(inventario: Inventario) -> str | None:
    pendentes = sum(1 for documento in inventario.documentos if documento.revisao_status != "aprovada")
    if not pendentes:
        return None
    return (
        f"{pendentes} de {len(inventario.documentos)} documento(s) com revisão de conteúdo pendente "
        "(campo revisao_real). Os textos são sintéticos e novos: revise-os antes de usar com uma turma."
    )


def criar_validador(padrao: re.Pattern[str], descricao: str) -> Callable[[str], str]:
    """Cria um tipo de argumento que só aceita valores no formato esperado."""

    def validar(valor: str) -> str:
        if not padrao.fullmatch(valor):
            raise argparse.ArgumentTypeError(f"{descricao} (recebido: {valor!r}).")
        return valor

    return validar


# O nome da conta forma o endereço que receberá o token. Aceitar só o formato do Azure
# impede que um valor como "meu-site.exemplo/" envie credenciais a outro destino.
validar_conta = criar_validador(_PADRAO_CONTA, "A conta deve ter de 3 a 24 caracteres, só letras minúsculas e números")
validar_container = criar_validador(
    _PADRAO_CONTAINER,
    "O contêiner deve ter de 3 a 63 caracteres: letras minúsculas, números e hífens, sem hífens seguidos",
)
validar_tenant = criar_validador(_PADRAO_TENANT, "O tenant deve ser um GUID ou um domínio, sem espaços")


class ParserLab(argparse.ArgumentParser):
    """Parser com mensagens em português e código de saída 1 (uso) para erros de argumentos."""

    _TRADUCOES = (
        ("the following arguments are required: ", "faltam argumentos obrigatórios: "),
        ("unrecognized arguments: ", "argumentos não reconhecidos: "),
        ("expected one argument", "falta informar o valor"),
        ("argument ", "argumento "),
    )
    # Dica extra quando falta o valor de uma opção que vem das saídas da implantação.
    _DICAS = (
        ("--conta", "Informe o nome da conta (saída nomeConta da implantação). Se você usou uma variável "
                    "como $conta, ela está vazia: repita a consulta do nome da conta da Etapa 4"),
        ("--busca", "Informe o nome do serviço de busca (saída nomeBusca da implantação do Desafio 02). "
                    "Se você usou uma variável como $busca, ela está vazia: repita a consulta da Etapa 2"),
        ("--modelos", "Informe o nome do recurso de modelos (saída nomeModelos da implantação do Desafio 02). "
                      "Se você usou uma variável como $modelos, ela está vazia: repita a consulta da Etapa 2"),
    )

    def __init__(self, *args: Any, **kwargs: Any):
        kwargs.setdefault("add_help", False)
        kwargs.setdefault("formatter_class", argparse.RawDescriptionHelpFormatter)
        super().__init__(*args, **kwargs)
        self._grupo_opcoes = self.add_argument_group("opções")
        self._grupo_opcoes.add_argument("-h", "--help", action="help", help="Mostra esta ajuda e sai.")

    def add_argument(self, *args: Any, **kwargs: Any) -> argparse.Action:
        return self._grupo_opcoes.add_argument(*args, **kwargs)

    def error(self, message: str) -> None:  # type: ignore[override]
        for original, traducao in self._TRADUCOES:
            message = message.replace(original, traducao)
        if "falta informar" in message or "obrigatórios" in message:
            for opcao, dica in self._DICAS:
                if opcao in message:
                    message += f". {dica}"
        self.print_usage(sys.stderr)
        self.exit(CODIGO_USO, f"{self.prog}: erro: {message}\n")


def criar_parser(descricao: str, *, armazenamento: bool = True, inventario: bool = True) -> ParserLab:
    """Cria o parser com as opções comuns.

    Sem `armazenamento`, omite as opções do Blob Storage; sem `inventario`, a do inventário.
    """
    parser = ParserLab(description=descricao)
    if armazenamento:
        parser.add_argument("--conta", required=True, type=validar_conta,
                            help="Nome da conta de armazenamento (saída nomeConta da implantação).")
        parser.add_argument("--container", default=CONTAINER_PADRAO, type=validar_container,
                            help=f"Nome do contêiner de blobs (padrão: {CONTAINER_PADRAO}).")
    if inventario:
        parser.add_argument("--inventario", type=Path, default=INVENTARIO_PADRAO,
                            help="Caminho do inventário (padrão: dados/l100/inventario.json).")
    parser.add_argument("--tenant-id", default=None, type=validar_tenant,
                        help="Tenant do Microsoft Entra ID, se a sua sessão do Azure CLI usa outro por padrão.")
    parser.add_argument("--detalhes", action="store_true",
                        help="Mostra o erro técnico. Pode conter identificadores do seu ambiente: não publique.")
    return parser


def configurar_saida() -> None:
    """Evita que um console com codificação limitada interrompa o script.

    No Windows, a saída redirecionada (por exemplo, capturada pelo agente do VS Code)
    sairia na página de código ANSI e os acentos chegariam quebrados a quem lê em UTF-8.
    Por isso ela usa UTF-8, a menos que PYTHONIOENCODING já defina a codificação.
    """
    codificacao_escolhida = bool(os.environ.get("PYTHONIOENCODING"))
    for fluxo in (sys.stdout, sys.stderr):
        try:
            if codificacao_escolhida or fluxo.isatty():
                fluxo.reconfigure(errors="replace")
            else:
                fluxo.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def criar_container(conta: str, container: str, tenant_id: str | None = None, credencial: Any = None) -> Any:
    """Cria o cliente do contêiner, sem chaves, com a identidade do Azure CLI (az login) ou com a `credencial` informada."""
    try:
        from azure.identity import AzureCliCredential
        from azure.storage.blob import BlobServiceClient
    except ImportError:
        raise ErroLab(
            "Bibliotecas do Azure não encontradas. Ative o ambiente virtual e execute: "
            "python -m pip install -r requirements/l100.txt"
        ) from None
    if credencial is None:
        credencial = AzureCliCredential(tenant_id=tenant_id, process_timeout=30)
    servico = BlobServiceClient(account_url=f"https://{conta}.{SUFIXO_BLOB}", credential=credencial)
    return servico.get_container_client(container)


def codigo_do_erro(erro: Exception) -> str | None:
    codigo = getattr(erro, "error_code", None)
    codigo = getattr(codigo, "value", codigo)
    return str(codigo) if codigo else None


def traduzir_erro(erro: Exception, conta: str, container: str) -> tuple[str, int]:
    """Transforma erros do Azure em orientação clara, sem expor tokens."""
    nome = type(erro).__name__
    status = getattr(erro, "status_code", None)
    codigo = codigo_do_erro(erro)
    if nome in {"CredentialUnavailableError", "ClientAuthenticationError"} and status is None:
        return ("Não foi possível obter credenciais do Azure CLI. Confirme que o Azure CLI está instalado ('az --version') "
                "e execute 'az login' (com vários tenants, use 'az login --tenant <ID>' e o parâmetro --tenant-id "
                "deste script), confirme com 'az account show' e tente de novo."), CODIGO_ACESSO
    if status == 403 and codigo == "AuthorizationPermissionMismatch":
        return (f"A sua identidade não tem permissão de dados no contêiner '{container}'. É preciso o papel "
                "'Storage Blob Data Contributor' (envio) ou 'Storage Blob Data Reader' (leitura) no contêiner ou na conta. "
                "Ter acesso para criar a conta não basta, e um papel novo pode levar alguns minutos para valer. "
                "Confira também o nome do contêiner: para um contêiner inexistente o Azure responde da mesma forma."), CODIGO_ACESSO
    if status in {401, 403}:
        return ("O Azure recusou a autenticação ou a autorização"
                f"{f' ({codigo})' if codigo else ''}. Confirme o tenant da assinatura (--tenant-id), execute 'az login' "
                "e verifique se há regras de rede bloqueando o seu acesso."), CODIGO_ACESSO
    if codigo == "ContainerNotFound":
        return (f"O contêiner '{container}' não existe na conta '{conta}'. Confirme os nomes "
                "e se a implantação do Bicep terminou."), CODIGO_ACESSO
    if status == 404:
        return f"Conta '{conta}' ou contêiner '{container}' não encontrado. Confirme os nomes informados.", CODIGO_ACESSO
    if nome == "ServiceRequestError":
        return (f"Não foi possível conectar à conta '{conta}'. Confira o nome, a conexão de rede "
                "e se o endereço público da conta está habilitado."), CODIGO_ACESSO
    if type(erro).__module__.split(".")[0] in {"azure", "requests", "urllib3"}:
        detalhe = ", ".join(parte for parte in (f"HTTP {status}" if status else "", codigo or "") if parte)
        return f"Erro do Azure ({nome}{f': {detalhe}' if detalhe else ''}). Use --detalhes para mais informações.", CODIGO_ACESSO
    return f"Erro inesperado do script ({nome}). Use --detalhes e, se persistir, abra uma issue sem dados do seu ambiente.", CODIGO_INESPERADO


def executar_com_tratamento(
    acao: Callable[[argparse.Namespace], int],
    args: argparse.Namespace,
    tradutor: Callable[[Exception, argparse.Namespace], tuple[str, int]] | None = None,
) -> int:
    """Executa a ação e converte erros esperados em mensagens e códigos de saída.

    O tradutor padrão cuida do Blob Storage; os scripts do Desafio 02 passam o deles.
    """
    if not getattr(args, "detalhes", False):
        # Sem --detalhes, nem o SDK do Azure nem o MAF despejam o erro bruto (inclusive tracebacks) antes da nossa mensagem.
        for nome in ("azure", "agent_framework"):
            logging.getLogger(nome).setLevel(logging.CRITICAL)
    try:
        return acao(args)
    except ErroLab as erro:
        if getattr(args, "detalhes", False) and erro.__cause__ is not None:
            traceback.print_exception(erro.__cause__)
        print(f"[ERRO] {erro}", file=sys.stderr)
        return erro.codigo
    except Exception as erro:  # noqa: BLE001 - erros do SDK variam; todos viram orientação
        if getattr(args, "detalhes", False):
            traceback.print_exc()
        if tradutor is not None:
            mensagem, codigo = tradutor(erro, args)
        else:
            mensagem, codigo = traduzir_erro(erro, getattr(args, "conta", "-"), getattr(args, "container", "-"))
        print(f"[ERRO] {mensagem}", file=sys.stderr)
        return codigo
