"""Identidade da aplicação e segredo no Azure Key Vault (L100, Desafio 07).

O operador (quem executou `az login`) guarda e lê o segredo do cofre. A aplicação usa esse segredo para se autenticar como
service principal e só faz o que os papéis dela permitem. O valor do segredo nunca é impresso nem gravado em arquivo.
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
from typing import Any, Callable

import lab_comum
import lab_indexacao
from lab_comum import ErroLab

IDENTIDADES = ("operador", "aplicacao")
IDENTIDADE_PADRAO = "operador"
SEGREDO_PADRAO = "segredo-da-aplicacao"
SUFIXO_COFRE = "vault.azure.net"
VALIDADE_PADRAO_DIAS = 7
VALIDADE_MAXIMA_DIAS = 90
TAMANHO_MAXIMO_DO_SEGREDO = 4096
ETIQUETAS_DO_SEGREDO = {"laboratorio": "vareleira-rag", "uso": "identidade-da-aplicacao"}

_PADRAO_COFRE = re.compile(r"(?!.*--)[A-Za-z][A-Za-z0-9-]{1,22}[A-Za-z0-9]")
_PADRAO_SEGREDO = re.compile(r"[A-Za-z0-9-]{1,127}")
_PADRAO_GUID = re.compile(r"[0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}")
_PADRAO_CODIGO_ENTRA = re.compile(r"AADSTS(\d{4,7})")

# O nome do cofre forma o endereço que receberá o token: só o formato do Azure é aceito.
validar_cofre = lab_comum.criar_validador(
    _PADRAO_COFRE, "O cofre deve ter de 3 a 24 caracteres: letras, números e hífens, começando por letra e sem hífens seguidos")
validar_nome_do_segredo = lab_comum.criar_validador(
    _PADRAO_SEGREDO, "O nome do segredo deve ter de 1 a 127 caracteres: letras, números e hífens")
validar_id_da_aplicacao = lab_comum.criar_validador(
    _PADRAO_GUID, "O ID da aplicação deve ser um GUID (o appId do service principal, não o ID de objeto)")


def validar_validade(valor: str) -> int:
    try:
        dias = int(valor)
    except ValueError:
        dias = 0
    if not 1 <= dias <= VALIDADE_MAXIMA_DIAS:
        raise argparse.ArgumentTypeError(
            f"A validade deve ser um número de dias de 1 a {VALIDADE_MAXIMA_DIAS} (recebido: {valor!r}).")
    return dias


def adicionar_argumentos_identidade(parser: lab_comum.ParserLab, *, escolha: bool = True) -> None:
    """Opções da identidade usada nos acessos ao Azure: a do operador (padrão) ou a da aplicação."""
    if escolha:
        parser.add_argument("--identidade", choices=IDENTIDADES, default=IDENTIDADE_PADRAO,
                            help="operador (padrão): a sua sessão do Azure CLI; aplicacao: o service principal, com o segredo "
                                 "lido do cofre (exige --cofre, --id-da-aplicacao e --tenant-id).")
    parser.add_argument("--cofre", default=None, type=validar_cofre,
                        help="Nome do Azure Key Vault que guarda o segredo da aplicação (saída nomeCofre da implantação).")
    parser.add_argument("--nome-do-segredo", default=SEGREDO_PADRAO, type=validar_nome_do_segredo,
                        help=f"Nome do segredo no cofre (padrão: {SEGREDO_PADRAO}).")
    parser.add_argument("--id-da-aplicacao", default=None, type=validar_id_da_aplicacao,
                        help="ID da aplicação (appId) do service principal. Não é um segredo.")


def exigir_dados_da_aplicacao(args: argparse.Namespace) -> None:
    faltam = [opcao for opcao, valor in (("--cofre", getattr(args, "cofre", None)),
                                         ("--id-da-aplicacao", getattr(args, "id_da_aplicacao", None)),
                                         ("--tenant-id", getattr(args, "tenant_id", None))) if not valor]
    if faltam:
        raise ErroLab("Para usar a identidade da aplicação, informe também " + ", ".join(faltam) + ". O segredo é lido do "
                      "cofre com a sua conta (az login); o ID do tenant e o ID da aplicação não são segredos.")


# --------------------------------------------------------------------------------------
# Segredo no Key Vault
# --------------------------------------------------------------------------------------

def _agora() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _cliente_de_segredos(cofre: str, credencial: Any) -> Any:
    try:
        from azure.keyvault.secrets import SecretClient
    except ImportError:
        raise ErroLab(
            "Biblioteca do Azure Key Vault não encontrada. Ative o ambiente virtual e execute: "
            "python -m pip install -r requirements/l100.txt"
        ) from None
    return SecretClient(vault_url=f"https://{cofre}.{SUFIXO_COFRE}", credential=credencial)


def criar_cliente_de_segredos(cofre: str, tenant_id: str | None = None, credencial: Any = None) -> Any:
    """Cliente do cofre, sem chaves, com a sua sessão do Azure CLI ou com a `credencial` informada."""
    if credencial is None:
        try:
            from azure.identity import AzureCliCredential
        except ImportError:
            raise ErroLab(
                "Biblioteca do Azure não encontrada. Ative o ambiente virtual e execute: "
                "python -m pip install -r requirements/l100.txt"
            ) from None
        credencial = AzureCliCredential(tenant_id=tenant_id, process_timeout=30)
    return _cliente_de_segredos(cofre, credencial)


def ler_segredo(cofre: str, nome: str, tenant_id: str | None = None, cliente: Any = None,
                agora: Callable[[], dt.datetime] = _agora) -> str:
    """Lê o valor do segredo com a sua sessão do Azure CLI. O valor só vai para quem chamou, nunca para a tela."""
    from azure.core.exceptions import ResourceNotFoundError
    cliente = cliente or criar_cliente_de_segredos(cofre, tenant_id)
    try:
        segredo = cliente.get_secret(nome)
    except ResourceNotFoundError:
        raise ErroLab(f"O segredo '{nome}' não existe no cofre '{cofre}'. Guarde-o com guardar_segredo.py ou confira o nome "
                      "(--nome-do-segredo).", lab_comum.CODIGO_ACESSO) from None
    propriedades = segredo.properties
    if propriedades.enabled is False:
        raise ErroLab(f"O segredo '{nome}' está desativado no cofre '{cofre}'.", lab_comum.CODIGO_ACESSO)
    if propriedades.expires_on is not None and propriedades.expires_on <= agora():
        raise ErroLab(f"O segredo '{nome}' expirou em {propriedades.expires_on:%Y-%m-%d}. Gere uma nova credencial para a "
                      "aplicação e guarde-a de novo.", lab_comum.CODIGO_ACESSO)
    if not segredo.value:
        raise ErroLab(f"O segredo '{nome}' está vazio no cofre '{cofre}'.", lab_comum.CODIGO_ACESSO)
    return str(segredo.value)


def guardar_segredo(cofre: str, nome: str, valor: str, tenant_id: str | None = None, validade_dias: int = VALIDADE_PADRAO_DIAS,
                    cliente: Any = None, agora: Callable[[], dt.datetime] = _agora) -> tuple[str, dt.datetime]:
    """Grava uma nova versão do segredo, com data de validade. Devolve a versão e a data de expiração."""
    if not valor:
        raise ErroLab("O valor do segredo está vazio. Nada foi gravado.")
    if len(valor) > TAMANHO_MAXIMO_DO_SEGREDO or "\n" in valor or "\r" in valor:
        raise ErroLab(f"O valor do segredo deve ter uma só linha e até {TAMANHO_MAXIMO_DO_SEGREDO} caracteres. Nada foi gravado.")
    cliente = cliente or criar_cliente_de_segredos(cofre, tenant_id)
    expira = agora() + dt.timedelta(days=validade_dias)
    criado = cliente.set_secret(nome, valor, expires_on=expira, content_type="text/plain", tags=dict(ETIQUETAS_DO_SEGREDO))
    return str(criado.properties.version), expira


# --------------------------------------------------------------------------------------
# Credencial da aplicação
# --------------------------------------------------------------------------------------

def criar_credencial_da_aplicacao(tenant_id: str, id_da_aplicacao: str, segredo: str) -> Any:
    try:
        from azure.identity import ClientSecretCredential
    except ImportError:
        raise ErroLab(
            "Biblioteca do Azure não encontrada. Ative o ambiente virtual e execute: "
            "python -m pip install -r requirements/l100.txt"
        ) from None
    return ClientSecretCredential(tenant_id=tenant_id, client_id=id_da_aplicacao, client_secret=segredo)


def resolver_credencial(args: argparse.Namespace, ler: Callable[..., str] = ler_segredo,
                        criar: Callable[..., Any] = criar_credencial_da_aplicacao) -> Any:
    """None para o operador (os clientes usam o Azure CLI); a credencial do service principal para a aplicação."""
    if getattr(args, "identidade", IDENTIDADE_PADRAO) != "aplicacao":
        return None
    exigir_dados_da_aplicacao(args)
    segredo = ler(args.cofre, args.nome_do_segredo, args.tenant_id)
    return criar(args.tenant_id, args.id_da_aplicacao, segredo)


def descrever_identidade(args: argparse.Namespace) -> str:
    if getattr(args, "identidade", IDENTIDADE_PADRAO) == "aplicacao":
        return f"aplicação (service principal), com o segredo lido do cofre '{args.cofre}'"
    return "operador (sessão do Azure CLI)"


# --------------------------------------------------------------------------------------
# Tradução de erros
# --------------------------------------------------------------------------------------

def _host_do_erro(erro: Exception) -> str:
    resposta = getattr(erro, "response", None)
    pedido = getattr(resposta, "request", None)
    return str(getattr(pedido, "url", "") or "") or str(erro)


def mensagem_do_entra(erro: Exception) -> str | None:
    """Orientação para as recusas do Microsoft Entra ID à autenticação da aplicação; None se não houver código AADSTS."""
    achado = _PADRAO_CODIGO_ENTRA.search(str(erro))
    if not achado:
        return None
    codigo = achado.group(1)
    conhecidas = {
        "7000215": "O Microsoft Entra ID recusou o segredo da aplicação (AADSTS7000215, segredo inválido). Confira se o cofre "
                   "guarda o valor do segredo, e não o ID dele, e se a credencial não foi trocada depois de guardada.",
        "7000222": "O segredo da aplicação expirou no Microsoft Entra ID (AADSTS7000222). Gere uma nova credencial e guarde-a "
                   "de novo no cofre.",
        "700016": "O Microsoft Entra ID não encontrou a aplicação neste tenant (AADSTS700016). Confira --id-da-aplicacao (o "
                  "appId, não o ID de objeto) e --tenant-id.",
        "90002": "O Microsoft Entra ID não encontrou o tenant informado (AADSTS90002). Confira --tenant-id.",
    }
    return conhecidas.get(codigo, f"O Microsoft Entra ID recusou a autenticação da aplicação (AADSTS{codigo}). Use --detalhes "
                                  "para ver o erro técnico; ele pode conter identificadores do seu ambiente.")


def _traduzir_erro_do_cofre(nome: str, status: int | None, cofre: str) -> str:
    if status == 403:
        return (f"A identidade usada não tem permissão de dados no cofre '{cofre}'. Ler segredos exige o papel 'Key Vault "
                "Secrets User' (ou 'Key Vault Secrets Officer'), e guardar exige 'Key Vault Secrets Officer'. Ter acesso para "
                "criar o cofre, como o Owner, não dá acesso aos segredos, e um papel novo pode levar alguns minutos para "
                "valer. Confira também regras de rede que bloqueiem o seu acesso.")
    if status == 401:
        return ("O cofre recusou a credencial. Execute 'az login' (com vários tenants, use --tenant-id) e confira o nome "
                f"do cofre '{cofre}'.")
    if status == 404:
        return f"O cofre '{cofre}' ou o segredo não foi encontrado. Confira o nome do cofre (saída nomeCofre) e do segredo."
    if status == 429:
        return f"O cofre '{cofre}' está limitando os pedidos (HTTP 429). Aguarde um minuto e repita."
    if nome == "ServiceRequestError":
        return (f"Não foi possível conectar ao cofre '{cofre}'. Confira o nome, a conexão de rede e se o endereço público "
                "do cofre está habilitado. Um cofre excluído continua reservando o nome até ser expurgado.")
    detalhe = f"HTTP {status}" if status else nome
    return f"Erro do cofre de segredos ({detalhe}). Use --detalhes para mais informações."


def traduzir_erro_identidade(erro: Exception, args: argparse.Namespace) -> tuple[str, int]:
    """Erros do Key Vault e da autenticação da aplicação; os demais seguem para o tradutor do Desafio 02."""
    nome = type(erro).__name__
    status = getattr(erro, "status_code", None)
    if nome == "ClientAuthenticationError":
        mensagem = mensagem_do_entra(erro)
        if mensagem:
            return mensagem, lab_comum.CODIGO_ACESSO
    if f".{SUFIXO_COFRE}" in _host_do_erro(erro) and (status is not None or nome == "ServiceRequestError"):
        return _traduzir_erro_do_cofre(nome, status, getattr(args, "cofre", None) or "?"), lab_comum.CODIGO_ACESSO
    return lab_indexacao.traduzir_erro_indexacao(erro, args)
