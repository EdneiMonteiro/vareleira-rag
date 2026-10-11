"""Negativas EXTERNAS do L300: confere, de FORA da rede, que o Blob, a busca e os modelos recusam o acesso pela internet.

Depois do isolamento (Desafio 04, fase `isolar`), os três serviços ficam com `publicNetworkAccess = Disabled`. A prova positiva (o
que funciona de DENTRO da rede) é da sonda (scripts/sonda_l300.py). Esta é a prova negativa: do SEU computador, fora da rede, com a
identidade do Azure CLI de quem opera e PAPÉIS DE DADOS nos três alvos, uma tentativa em cada serviço (leitura no Blob e na busca; nos
modelos, um pedido de embeddings, que não grava nada) deve ser recusada (HTTP 403) e a causa da recusa precisa ser o acesso público
desabilitado. Sem os papéis, um 403 poderia ser só falta de permissão e não provaria nada sobre a rede; por isso o script confere os
papéis e o estado dos serviços antes de qualquer tentativa.

Por padrão NÃO FAZ REDE: o modo simulado só valida as entradas, confere as pré-condições nas suas exportações e imprime o plano. A
execução real exige --executar. Ela não altera nada no Azure: faz um GET de leitura no Blob (lista 1 blob do contêiner do L300) e na
busca (conta os documentos do índice do L300) e um POST de embeddings com um texto sintético fixo nos modelos (não grava nada; se o
acesso público não estivesse bloqueado, consumiria poucos tokens). O token do Azure CLI só vai para o endereço exato de cada serviço,
montado a partir dos nomes validados (*.blob.core.windows.net, *.search.windows.net, *.openai.azure.com), sem redirecionamento.

Entradas (nenhum ID do ambiente fica no código; tudo vem de você):
    --tenant-id, --conta, --busca, --modelos   o tenant e os nomes dos três serviços (formatos validados antes de montar qualquer URL)
    --container, --indice, --deployment        padrões do L300: base-documental-l300, vareleira-lar-l300 e embeddings
    --servicos ARQUIVO...                      exportações de `az resource show --ids <id-do-recurso> -o json` dos três serviços
    --papeis ARQUIVO...                        exportação de `az role assignment list --assignee <operador> --all -o json`
    --operador-id GUID                         (opcional) o principal do operador, se a exportação de papéis tiver mais de um
    --relatorio ARQUIVO.json                   (opcional) relatório NOVO: nunca sobrescreve; permissão só do dono em sistemas POSIX
    --executar                                 faz as três tentativas; sem ele, é só simulação

Formato mínimo aceito das exportações (JSON, em UTF-8 ou no UTF-16 do PowerShell 5; até 8 MiB por arquivo). Campos a mais são
ignorados e nunca repetidos na saída:
    --servicos   um objeto, ou uma lista de objetos, cada um com `id` (ID do recurso no ARM), `name`, `type` e
                 `properties.publicNetworkAccess` (texto). Os três serviços precisam aparecer, identificados por `type` e `name`:
                 Microsoft.Storage/storageAccounts (--conta), Microsoft.Search/searchServices (--busca) e
                 Microsoft.CognitiveServices/accounts (--modelos). O `id` precisa ser o do próprio recurso, não o de um sub-recurso.
                 Condição: `publicNetworkAccess` igual a Disabled nos três.
    --papeis     uma lista de objetos, cada um com `principalId` (GUID), `roleDefinitionName` e `scope`. O operador é o principal da
                 exportação (ou o de --operador-id). Só valem atribuições DIRETAS a ele: as com `condition` preenchida, as recebidas por
                 grupo e as de grupo de gerenciamento não são avaliadas. Condição: um destes papéis, no escopo do alvo ou em um escopo
                 que o contém (assinatura, grupo de recursos ou o próprio recurso):
                   Blob, no contêiner do L300: Storage Blob Data Reader, Storage Blob Data Contributor ou Storage Blob Data Owner
                   busca, no índice do L300: Search Index Data Reader ou Search Index Data Contributor
                   modelos: Cognitive Services OpenAI User ou Cognitive Services OpenAI Contributor

Resultado: texto em português e, por último, UMA linha `L300_SONDA_RESULTADO=<JSON>` de vocabulário fechado (etapa
negativas-externas): HTTP, código curto do serviço, causa e evidência de cada serviço; nunca token, URL, ID, nome de recurso nem a
mensagem bruta do serviço. Não existe --detalhes: a mensagem bruta nunca é exibida nem gravada. Causas: acesso_publico_desabilitado
(a esperada), autorizacao_de_dados, autenticacao, dns, conexao e nao_identificada. Para o Blob, o código AuthorizationFailure sozinho
não identifica o mecanismo: a causa é atribuída pela combinação dele com o acesso público desabilitado, o papel de dados e a identidade
do token conferidos. Busca e modelos têm a causa identificada pela mensagem do serviço (marcadores fixos, lidos só em memória).

Código de saída (sempre o da linha realmente emitida, a mesma do relatório): 0 aprovado (ou simulação válida); 1 uso, argumentos ou
exportações inválidos; 2 sem token ou nenhum serviço respondeu (rede); 3 não aprovado: pré-condição não atendida, serviço que aceitou
a operação (reprovado) ou recusa sem a causa esperada (pendente: causa não identificada NÃO é aprovação); 4 defeito (inclusive
`saida_bloqueada`: se a barreira recusar a linha, por trazer algo que pareça token, URL, ID ou o nome de um dos seus recursos, o código
é 4 e o relatório registra essa mesma linha; escolha nomes que não coincidam com palavras do vocabulário, como `busca` ou `blob`).

Efeitos, custo e limpeza: não altera nada no Azure; o custo é o de três requisições (e, só se a recusa falhasse, de alguns tokens de
embeddings). O relatório, se pedido, é um arquivo local seu, em pasta privada: apague-o quando não precisar mais. As exportações
também ficam em pasta privada (trazem IDs do seu ambiente) e não vão ao repositório.

Exemplos (PowerShell; as exportações são SUAS e ficam em pasta privada, fora do repositório):
    az resource show --ids $idConta -o json > servico-conta.json     (repita para a busca e para os modelos)
    az role assignment list --assignee $operador --all -o json > papeis.json
    python scripts\\sonda_negativas_externas_l300.py --tenant-id $tenant --conta $conta --busca $busca --modelos $modelos `
        --servicos servico-conta.json servico-busca.json servico-modelos.json --papeis papeis.json
    python scripts\\sonda_negativas_externas_l300.py --tenant-id $tenant --conta $conta --busca $busca --modelos $modelos `
        --servicos servico-conta.json servico-busca.json servico-modelos.json --papeis papeis.json --executar --relatorio negativas.json
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import json
import logging
import os
import re
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import sonda_l300 as sonda

ETAPA = "negativas-externas"
SERVICOS = ("blob", "busca", "modelos")
ROTULOS = {"blob": "armazenamento (Blob)", "busca": "busca", "modelos": "modelos"}
TIPOS_NO_ARM = {"blob": "microsoft.storage/storageaccounts", "busca": "microsoft.search/searchservices",
                "modelos": "microsoft.cognitiveservices/accounts"}
PAPEIS_DE_DADOS = {
    "blob": ("Storage Blob Data Reader", "Storage Blob Data Contributor", "Storage Blob Data Owner"),
    "busca": ("Search Index Data Reader", "Search Index Data Contributor"),
    "modelos": ("Cognitive Services OpenAI User", "Cognitive Services OpenAI Contributor"),
}
CAUSAS = ("acesso_publico_desabilitado", "autorizacao_de_dados", "autenticacao", "dns", "conexao", "nao_identificada")
CODIGOS_CONHECIDOS = frozenset({"AuthorizationFailure", "AuthorizationPermissionMismatch", "AuthenticationFailed", "InvalidAuthenticationInfo",
                                "PublicAccessNotPermitted", "PermissionDenied", "Forbidden", "AccessDenied", "ContainerNotFound",
                                "ResourceNotFound", "401", "403", "404"})

TEMPO_HTTP, LIMITE_DO_CORPO, LIMITE_DO_ARQUIVO = 30, 65536, 8 * 1024 * 1024
VERSAO_DO_BLOB, VERSAO_DA_API_DOS_MODELOS = "2024-11-04", "2024-10-21"
ESCOPO_BLOB = "https://storage.azure.com/.default"
TEXTO_DE_CONFERENCIA = "Texto sintetico de conferencia de acesso."
LIMITE_DA_PROVA = ("Esta prova mostra a recusa vinda do acesso público desabilitado a partir da SUA rede, com a identidade do Azure CLI "
                   "informada. Ela não prova o bloqueio de outros caminhos (como uma VPN) nem substitui a prova positiva de dentro da rede.")

_PADRAO_GUID = re.compile(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}")
_PADRAO_RELATORIO = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}\.json")
_PADRAO_ID_NO_ARM = re.compile(r"/subscriptions/[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}/resourcegroups/[^/\s]{1,90}"
                               r"/providers/([^/\s]{1,64}/[^/\s]{1,64})/([^/\s]{1,64})", re.IGNORECASE)
_PADRAO_CODIGO = re.compile(r"[A-Za-z0-9_.-]{1,60}")
_CODIGO_NO_XML = re.compile(r"<Code>\s*([A-Za-z0-9_.-]{1,60})\s*</Code>")
# Marcadores lidos só em memória: nenhum trecho da mensagem do serviço é guardado, impresso ou gravado.
_ACESSO_PUBLICO_DESABILITADO = re.compile(
    r"public\s+(?:network\s+)?access\b.{0,80}?\bdisabled|publicNetworkAccess\b.{0,30}?\bdisabled"
    r"|(?:configure|use|through|via)\s+(?:a\s+)?private\s+(?:endpoint|link)", re.IGNORECASE | re.DOTALL)
_SEM_PERMISSAO_DE_DADOS = re.compile(r"using this permission|required data action", re.IGNORECASE)
_AUTENTICACAO = frozenset({"AuthenticationFailed", "InvalidAuthenticationInfo"})
_AUTORIZACAO = frozenset({"AuthorizationPermissionMismatch", "PermissionDenied"})


# --------------------------------------------------------------------------------------
# Argumentos: só nomes de chaves vão para o resultado, nunca os valores recebidos
# --------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Entradas:
    tenant: str
    conta: str
    busca: str
    modelos: str
    container: str
    indice: str
    deployment: str
    operador: str | None
    servicos: tuple[Path, ...]
    papeis: tuple[Path, ...]
    relatorio: Path | None
    executar: bool

    def privados(self) -> tuple[str, ...]:
        return tuple(valor for valor in (self.conta, self.busca, self.modelos, self.tenant, self.operador) if valor)


def _guid(valor: str) -> str:
    if not _PADRAO_GUID.fullmatch(valor):
        raise ValueError
    return valor.lower()


def _validadores() -> dict[str, Any]:
    comum, indexacao, l300 = sonda.mod.lab_comum, sonda.mod.lab_indexacao, sonda.mod.lab_ingestao_l300
    return {"tenant_id": comum.validar_tenant, "conta": comum.validar_conta, "busca": indexacao.validar_busca,
            "modelos": indexacao.validar_modelos, "container": l300.validar_container_l300, "indice": l300.validar_indice_l300,
            "deployment": indexacao.validar_deployment, "operador_id": _guid}


def ler_argumentos(argv: Sequence[str] | None) -> Entradas:
    parser = sonda.ParserDaSonda(add_help=False, allow_abbrev=False)
    for opcao in ("--tenant-id", "--conta", "--busca", "--modelos", "--container", "--indice", "--deployment", "--operador-id",
                  "--relatorio"):
        parser.add_argument(opcao, default=None)
    parser.add_argument("--servicos", nargs="+", action="extend", default=None)
    parser.add_argument("--papeis", nargs="+", action="extend", default=None)
    parser.add_argument("--executar", action="store_true")
    args = parser.parse_args(None if argv is None else list(argv))

    obrigatorias = ("tenant_id", "conta", "busca", "modelos", "servicos", "papeis")
    ausentes = [chave for chave in obrigatorias if not getattr(args, chave)]
    if ausentes:
        raise sonda.ErroSonda("argumentos_ausentes", sonda.USO, ausentes=ausentes)
    l300 = sonda.mod.lab_ingestao_l300
    padroes = {"container": l300.CONTAINER_PADRAO, "indice": l300.INDICE_PADRAO, "deployment": sonda.mod.lab_indexacao.DEPLOYMENT_PADRAO}
    validados: dict[str, Any] = {}
    invalidos: list[str] = []
    for chave, validar in _validadores().items():
        bruto = getattr(args, chave)
        if bruto is None:
            validados[chave] = padroes.get(chave)
            continue
        try:
            validados[chave] = validar(bruto)
        except (ValueError, argparse.ArgumentTypeError):
            invalidos.append(chave)
    if invalidos:
        raise sonda.ErroSonda("argumentos_invalidos", sonda.USO, invalidos=invalidos)
    return Entradas(
        tenant=validados["tenant_id"], conta=validados["conta"], busca=validados["busca"], modelos=validados["modelos"],
        container=validados["container"], indice=validados["indice"], deployment=validados["deployment"],
        operador=validados["operador_id"], servicos=tuple(Path(item) for item in args.servicos),
        papeis=tuple(Path(item) for item in args.papeis), relatorio=Path(args.relatorio) if args.relatorio else None,
        executar=args.executar)


def exigir_relatorio_novo(caminho: Path | None) -> None:
    """Confere o destino do relatório ANTES de qualquer trabalho: nome limitado, pasta existente e arquivo inexistente."""
    if caminho is None:
        return
    if not _PADRAO_RELATORIO.fullmatch(caminho.name):
        raise sonda.ErroSonda("relatorio_invalido", sonda.USO, motivo="nome")
    if not caminho.parent.is_dir():
        raise sonda.ErroSonda("relatorio_invalido", sonda.USO, motivo="pasta_inexistente")
    if caminho.exists() or caminho.is_symlink():
        raise sonda.ErroSonda("relatorio_invalido", sonda.USO, motivo="ja_existe")


def gravar_relatorio(caminho: Path, linha: str) -> None:
    """Cria o relatório em um arquivo NOVO (O_EXCL: nunca sobrescreve) e, em sistemas POSIX, legível só pelo dono."""
    corpo = json.loads(linha[len(sonda.SENTINELA):] if linha.startswith(sonda.SENTINELA) else linha)
    texto = json.dumps({"versao_relatorio": 1, "tipo": ETAPA, "resultado": corpo, "limite": LIMITE_DA_PROVA}, ensure_ascii=False,
                       indent=2) + "\n"
    descritor = os.open(caminho, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descritor, "w", encoding="utf-8", newline="\n") as arquivo:
        arquivo.write(texto)


# --------------------------------------------------------------------------------------
# Exportações do aluno: formato mínimo, pré-condições e papéis do operador
# --------------------------------------------------------------------------------------

def _decodificar(bruto: bytes) -> str:
    # O PowerShell 5 grava redirecionamentos em UTF-16; os demais, em UTF-8 (às vezes com BOM).
    return bruto.decode("utf-16") if bruto.startswith((b"\xff\xfe", b"\xfe\xff")) else bruto.decode("utf-8-sig")


def ler_exportacao(caminho: Path, arquivo: str) -> Any:
    try:
        if not caminho.is_file():
            raise sonda.ErroSonda("exportacao_invalida", sonda.USO, arquivo=arquivo, motivo="nao_encontrado")
        if caminho.stat().st_size > LIMITE_DO_ARQUIVO:
            raise sonda.ErroSonda("exportacao_invalida", sonda.USO, arquivo=arquivo, motivo="grande")
        bruto = caminho.read_bytes()
    except OSError:
        raise sonda.ErroSonda("exportacao_invalida", sonda.USO, arquivo=arquivo, motivo="ilegivel") from None
    try:
        return json.loads(_decodificar(bruto))
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise sonda.ErroSonda("exportacao_invalida", sonda.USO, arquivo=arquivo, motivo="json_invalido") from None


def _itens(caminhos: Sequence[Path], arquivo: str, aceita_objeto: bool) -> list[dict[str, Any]]:
    itens: list[dict[str, Any]] = []
    for caminho in caminhos:
        dados = ler_exportacao(caminho, arquivo)
        if isinstance(dados, dict) and aceita_objeto:
            dados = [dados]
        if not isinstance(dados, list) or not all(isinstance(item, dict) for item in dados):
            raise sonda.ErroSonda("exportacao_invalida", sonda.USO, arquivo=arquivo, motivo="formato")
        itens.extend(dados)
    return itens


@dataclass(frozen=True)
class Servico:
    id: str  # minúsculo, só em memória
    publico: str  # desabilitado, habilitado, outro ou ausente


def carregar_servicos(caminhos: Sequence[Path], entradas: Entradas) -> dict[str, Servico]:
    esperados = {(TIPOS_NO_ARM["blob"], entradas.conta): "blob", (TIPOS_NO_ARM["busca"], entradas.busca): "busca",
                 (TIPOS_NO_ARM["modelos"], entradas.modelos): "modelos"}
    achados: dict[str, Servico] = {}
    for item in _itens(caminhos, "servicos", aceita_objeto=True):
        tipo, nome, identificador = item.get("type"), item.get("name"), item.get("id")
        if not all(isinstance(valor, str) for valor in (tipo, nome, identificador)):
            continue
        servico = esperados.get((tipo.lower(), nome.lower()))
        if servico is None:
            continue
        partes = _PADRAO_ID_NO_ARM.fullmatch(identificador)
        if partes is None or partes.group(1).lower() != tipo.lower() or partes.group(2).lower() != nome.lower():
            raise sonda.ErroSonda("exportacao_invalida", sonda.USO, arquivo="servicos", motivo="id_do_recurso", servico=servico)
        propriedades = item.get("properties")
        acesso = propriedades.get("publicNetworkAccess") if isinstance(propriedades, dict) else None
        publico = ("ausente" if not isinstance(acesso, str) else "desabilitado" if acesso.lower() == "disabled"
                   else "habilitado" if acesso.lower() == "enabled" else "outro")
        novo = Servico(identificador.lower(), publico)
        if servico in achados and achados[servico] != novo:
            raise sonda.ErroSonda("exportacao_invalida", sonda.USO, arquivo="servicos", motivo="recurso_repetido", servico=servico)
        achados[servico] = novo
    faltam = [servico for servico in SERVICOS if servico not in achados]
    if faltam:
        raise sonda.ErroSonda("exportacao_invalida", sonda.USO, arquivo="servicos", motivo="servico_ausente", servicos=faltam)
    return achados


@dataclass(frozen=True)
class Atribuicao:
    principal: str
    papel: str
    escopo: str
    condicional: bool


def carregar_papeis(caminhos: Sequence[Path]) -> list[Atribuicao]:
    atribuicoes: list[Atribuicao] = []
    for item in _itens(caminhos, "papeis", aceita_objeto=False):
        principal, papel, escopo = item.get("principalId"), item.get("roleDefinitionName"), item.get("scope")
        if not (isinstance(principal, str) and _PADRAO_GUID.fullmatch(principal) and isinstance(papel, str) and 0 < len(papel) <= 200
                and isinstance(escopo, str) and escopo.startswith("/") and len(escopo) <= 500):
            raise sonda.ErroSonda("exportacao_invalida", sonda.USO, arquivo="papeis", motivo="formato")
        condicao = item.get("condition")
        atribuicoes.append(Atribuicao(principal.lower(), papel, escopo, isinstance(condicao, str) and bool(condicao.strip())))
    return atribuicoes


def _normalizar_escopo(escopo: str) -> str:
    return escopo.strip().lower().rstrip("/")


def escopo_cobre(escopo: str, alvo: str) -> bool:
    """O escopo da atribuição é o alvo ou um ancestral dele (a raiz `/` cobre tudo)."""
    escopo, alvo = _normalizar_escopo(escopo), _normalizar_escopo(alvo)
    return escopo == "" or alvo == escopo or alvo.startswith(escopo + "/")


def alvos_dos_papeis(servicos: Mapping[str, Servico], entradas: Entradas) -> dict[str, str]:
    """O recurso que cada operação toca: o contêiner do L300, o índice do L300 e a conta de modelos."""
    return {"blob": f"{servicos['blob'].id}/blobservices/default/containers/{entradas.container}".lower(),
            "busca": f"{servicos['busca'].id}/indexes/{entradas.indice}".lower(), "modelos": servicos["modelos"].id}


@dataclass(frozen=True)
class Precondicoes:
    publico: dict[str, str]
    papeis: dict[str, bool]
    operador: str  # só em memória
    origem_do_operador: str
    condicionais_ignoradas: int

    @property
    def ok(self) -> bool:
        return all(self.publico[s] == "desabilitado" and self.papeis[s] for s in SERVICOS)

    def a_dict(self) -> dict[str, Any]:
        return {"acesso_publico": dict(self.publico), "papeis_de_dados": dict(self.papeis), "operador": self.origem_do_operador,
                "atribuicoes_condicionais_ignoradas": self.condicionais_ignoradas}


def avaliar_precondicoes(servicos: Mapping[str, Servico], atribuicoes: Sequence[Atribuicao], entradas: Entradas) -> Precondicoes:
    if entradas.operador:
        operador, origem = entradas.operador, "informado"
    else:
        principais = {atribuicao.principal for atribuicao in atribuicoes}
        if len(principais) != 1:
            raise sonda.ErroSonda("exportacao_invalida", sonda.USO, arquivo="papeis",
                                  motivo="mais_de_um_principal" if principais else "sem_atribuicoes", principais=len(principais))
        operador, origem = next(iter(principais)), "unico_na_exportacao"
    do_operador = [atribuicao for atribuicao in atribuicoes if atribuicao.principal == operador]
    alvos = alvos_dos_papeis(servicos, entradas)
    papeis = {servico: any(not atribuicao.condicional and atribuicao.papel.casefold() in {p.casefold() for p in PAPEIS_DE_DADOS[servico]}
                           and escopo_cobre(atribuicao.escopo, alvos[servico]) for atribuicao in do_operador)
              for servico in SERVICOS}
    return Precondicoes({servico: servicos[servico].publico for servico in SERVICOS}, papeis, operador, origem,
                        sum(atribuicao.condicional for atribuicao in do_operador))


# --------------------------------------------------------------------------------------
# Destinos: o token só vai ao endereço exato de cada serviço
# --------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Destino:
    servico: str
    escopo: str
    metodo: str
    host: str
    caminho: str
    cabecalhos: Mapping[str, str]
    corpo: bytes | None

    @property
    def url(self) -> str:
        return f"https://{self.host}{self.caminho}"


def montar_destinos(entradas: Entradas) -> list[Destino]:
    comum, indexacao, ingestao = sonda.mod.lab_comum, sonda.mod.lab_indexacao, sonda.mod.lab_ingestao
    destinos = [
        Destino("blob", ESCOPO_BLOB, "GET", f"{entradas.conta}.{comum.SUFIXO_BLOB}",
                f"/{entradas.container}?restype=container&comp=list&maxresults=1", {"x-ms-version": VERSAO_DO_BLOB}, None),
        Destino("busca", ingestao.ESCOPO_BUSCA, "GET", f"{entradas.busca}.{indexacao.SUFIXO_BUSCA}",
                f"/indexes/{entradas.indice}/docs/$count?api-version={ingestao.VERSAO_API}", {}, None),
        Destino("modelos", indexacao.ESCOPO_MODELOS, "POST", f"{entradas.modelos}.{indexacao.SUFIXO_MODELOS}",
                f"/openai/deployments/{entradas.deployment}/embeddings?api-version={VERSAO_DA_API_DOS_MODELOS}",
                {"Content-Type": "application/json"}, json.dumps({"input": [TEXTO_DE_CONFERENCIA]}).encode("utf-8")),
    ]
    for destino in destinos:
        exigir_destino_exato(destino)
    return destinos


def exigir_destino_exato(destino: Destino) -> None:
    """Antes de qualquer token: HTTPS, sem usuário nem porta, e o host IGUAL ao montado dos nomes validados."""
    partes = urllib.parse.urlsplit(destino.url)
    try:
        porta = partes.port
    except ValueError:
        porta = -1
    sufixo = {"blob": ".blob.core.windows.net", "busca": ".search.windows.net", "modelos": ".openai.azure.com"}[destino.servico]
    if (partes.scheme != "https" or partes.username is not None or partes.password is not None or porta is not None
            or partes.hostname != destino.host or not destino.host.endswith(sufixo) or partes.fragment):
        raise sonda.ErroSonda("destino_inesperado", sonda.USO, servico=destino.servico)


def _claims(token: str) -> dict[str, Any] | None:
    try:
        carga = token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(carga + "=" * (-len(carga) % 4)))
    except (IndexError, ValueError):
        return None
    return claims if isinstance(claims, dict) else None


def identidade_do_token(token: str, tenant: str, operador: str) -> str:
    """Confere, só em memória, se o token é do operador (claim oid) e do tenant (claim tid, se o tenant foi dado como GUID)."""
    claims = _claims(token)
    dono, locatario = (claims.get("oid"), claims.get("tid")) if claims else (None, None)
    if not isinstance(dono, str):
        return "indeterminada"
    tenant_confere = not _PADRAO_GUID.fullmatch(tenant) or (isinstance(locatario, str) and locatario.lower() == tenant.lower())
    return "confere" if dono.lower() == operador.lower() and tenant_confere else "diferente"


# --------------------------------------------------------------------------------------
# Requisição e classificação da recusa (nunca guardam a mensagem do serviço)
# --------------------------------------------------------------------------------------

class FalhaDeRede(Exception):
    """A requisição não chegou a receber uma resposta HTTP. `tipo` é `dns` ou `conexao`."""

    def __init__(self, tipo: str):
        super().__init__(tipo)
        self.tipo = tipo


_ABRIDOR = urllib.request.build_opener(sonda.SemRedirecionamento)


def _tipo_de_falha(erro: BaseException) -> str:
    return "dns" if isinstance(erro, socket.gaierror) else "conexao"


def requisitar(metodo: str, url: str, cabecalhos: Mapping[str, str], corpo: bytes | None,
               tempo: float = TEMPO_HTTP) -> tuple[int, bytes, str | None]:
    """(status, até 64 KiB do corpo, cabeçalho x-ms-error-code). Sem redirecionamento; sem resposta, FalhaDeRede."""
    pedido = urllib.request.Request(url, data=corpo, method=metodo, headers=dict(cabecalhos))
    try:
        with _ABRIDOR.open(pedido, timeout=tempo) as resposta:
            return resposta.status, resposta.read(LIMITE_DO_CORPO), resposta.headers.get("x-ms-error-code")
    except urllib.error.HTTPError as erro:
        try:
            return erro.code, erro.read(LIMITE_DO_CORPO), (erro.headers.get("x-ms-error-code") if erro.headers is not None else None)
        finally:
            erro.close()
    except urllib.error.URLError as erro:
        raise FalhaDeRede(_tipo_de_falha(erro.reason)) from None
    except OSError as erro:  # inclui tempo esgotado, conexão recusada e falhas de TLS
        raise FalhaDeRede(_tipo_de_falha(erro)) from None


def _codigo_do_servico(texto: str, do_cabecalho: str | None) -> str | None:
    """O código curto do erro (JSON, XML ou cabeçalho), só se tiver o formato esperado; o resto da mensagem é descartado."""
    candidato = do_cabecalho
    if not candidato:
        try:
            dados = json.loads(texto)
            detalhe = dados.get("error", dados) if isinstance(dados, dict) else None
            candidato = detalhe.get("code") if isinstance(detalhe, dict) else None
        except ValueError:
            achado = _CODIGO_NO_XML.search(texto)
            candidato = achado.group(1) if achado else None
    candidato = None if candidato is None else str(candidato)
    return candidato if candidato and _PADRAO_CODIGO.fullmatch(candidato) else None


def classificar_recusa(servico: str, status: int, bruto: bytes, do_cabecalho: str | None, precondicoes_ok: bool) -> dict[str, Any]:
    """O registro fechado de UMA tentativa que recebeu resposta: HTTP, código curto, causa, evidência e resultado."""
    texto = bruto.decode("utf-8", errors="replace")
    codigo = _codigo_do_servico(texto, do_cabecalho)
    registro: dict[str, Any] = {"dependencia": servico, "http": status,
                                "codigo_servico": None if codigo is None else codigo if codigo in CODIGOS_CONHECIDOS else "outro"}
    if 200 <= status < 300:
        return {**registro, "causa": None, "evidencia": "operacao_aceita", "resultado": "permitida"}
    if status == 403 and _ACESSO_PUBLICO_DESABILITADO.search(texto):
        causa, evidencia = "acesso_publico_desabilitado", "mensagem_do_servico"
    elif status == 403 and servico == "blob" and codigo == "AuthorizationFailure" and precondicoes_ok:
        causa, evidencia = "acesso_publico_desabilitado", "codigo_do_servico_e_precondicoes"
    elif status == 401 or codigo in _AUTENTICACAO:
        causa, evidencia = "autenticacao", "codigo_do_servico" if codigo in _AUTENTICACAO else "status_http"
    elif codigo in _AUTORIZACAO or _SEM_PERMISSAO_DE_DADOS.search(texto):
        causa, evidencia = "autorizacao_de_dados", "codigo_do_servico" if codigo in _AUTORIZACAO else "mensagem_do_servico"
    else:
        causa, evidencia = "nao_identificada", "nenhuma"
    esperado = status == 403 and causa == "acesso_publico_desabilitado"
    return {**registro, "causa": causa, "evidencia": evidencia, "resultado": "recusa_esperada" if esperado else "pendente"}


def registro_sem_resposta(servico: str, causa: str, evidencia: str) -> dict[str, Any]:
    return {"dependencia": servico, "http": None, "codigo_servico": None, "causa": causa, "evidencia": evidencia, "resultado": "pendente"}


def decidir(resultados: Sequence[Mapping[str, Any]]) -> tuple[str, str | None, int]:
    """(veredicto, causa, código de saída). Só a recusa esperada nos três serviços aprova; causa não identificada é pendência."""
    if sorted(item["dependencia"] for item in resultados) != sorted(SERVICOS):
        raise sonda.ErroSonda("resultados_incompletos", sonda.INESPERADO)
    if any(item["resultado"] == "permitida" for item in resultados):
        return "reprovado", "acesso_permitido", sonda.DIVERGENCIA
    if all(item["resultado"] == "recusa_esperada" for item in resultados):
        return "aprovado", None, sonda.OK
    if all(item["http"] is None for item in resultados):
        return "erro", "sem_resposta_dos_servicos", sonda.ACESSO
    if any(item["causa"] == "nao_identificada" for item in resultados):
        return "pendente", "causa_nao_identificada", sonda.DIVERGENCIA
    return "pendente", "recusa_por_outro_mecanismo", sonda.DIVERGENCIA


def criar_credencial(tenant: str) -> Any:
    """A identidade do Azure CLI do operador (az login). Nenhuma chave nem segredo."""
    return sonda.importar("azure.identity").AzureCliCredential(tenant_id=tenant, process_timeout=30)


def executar_tentativas(entradas: Entradas, precondicoes: Precondicoes) -> tuple[list[dict[str, Any]], str]:
    """Obtém os tokens, confere a identidade de TODOS antes da primeira requisição e faz uma tentativa por serviço."""
    destinos = montar_destinos(entradas)
    credencial = criar_credencial(entradas.tenant)
    tokens: dict[str, str | None] = {}
    try:
        for destino in destinos:
            try:
                tokens[destino.servico] = credencial.get_token(destino.escopo).token
            except Exception:  # noqa: BLE001 - só o fato de o token não ter sido emitido interessa, nunca o texto do erro
                tokens[destino.servico] = None
        emitidos = [token for token in tokens.values() if token]
        if not emitidos:
            raise sonda.ErroSonda("token_indisponivel", sonda.ACESSO, servicos=list(SERVICOS))
        estados = {identidade_do_token(token, entradas.tenant, precondicoes.operador) for token in emitidos}
        identidade = "diferente" if "diferente" in estados else "indeterminada" if "indeterminada" in estados else "confere"
        if identidade != "confere":
            raise sonda.ErroSonda("identidade_diferente" if identidade == "diferente" else "identidade_indeterminada",
                                  sonda.DIVERGENCIA if identidade == "diferente" else sonda.ACESSO, identidade=identidade)
        resultados: list[dict[str, Any]] = []
        for destino in destinos:
            token = tokens[destino.servico]
            if not token:
                resultados.append(registro_sem_resposta(destino.servico, "autenticacao", "token_nao_emitido"))
                continue
            cabecalhos = {**destino.cabecalhos, "Authorization": f"Bearer {token}"}
            try:
                status, bruto, codigo = requisitar(destino.metodo, destino.url, cabecalhos, destino.corpo)
            except FalhaDeRede as falha:
                resultados.append(registro_sem_resposta(destino.servico, falha.tipo, "excecao_de_rede"))
            else:
                resultados.append(classificar_recusa(destino.servico, status, bruto, codigo, precondicoes.ok))
            finally:
                del cabecalhos, token
        return resultados, identidade
    finally:
        tokens.clear()
        fechar = getattr(credencial, "close", None)
        if callable(fechar):
            try:
                fechar()
            except Exception:  # noqa: BLE001 - encerrar a credencial nunca muda o veredicto
                pass


# --------------------------------------------------------------------------------------
# Texto para quem opera (só rótulos e códigos fechados) e fluxo principal
# --------------------------------------------------------------------------------------

_TEXTO_PUBLICO = {"desabilitado": "acesso público desabilitado", "habilitado": "acesso público HABILITADO",
                  "outro": "acesso público com valor diferente de Disabled", "ausente": "acesso público ausente na exportação"}


def mostrar_precondicoes(saida: Any, precondicoes: Precondicoes) -> None:
    print("Pré-condições lidas das suas exportações (nada foi consultado no Azure):", file=saida)
    for servico in SERVICOS:
        publico_ok = precondicoes.publico[servico] == "desabilitado"
        papel = ("papel de dados do operador no alvo confere" if precondicoes.papeis[servico]
                 else "FALTA papel de dados do operador no alvo (ou ele tem condição)")
        marca = "ok" if publico_ok and precondicoes.papeis[servico] else "PENDENTE"
        print(f"  [{marca}] {ROTULOS[servico]}: {_TEXTO_PUBLICO[precondicoes.publico[servico]]}; {papel}", file=saida)
    if precondicoes.condicionais_ignoradas:
        print(f"  [aviso] {precondicoes.condicionais_ignoradas} atribuição(ões) com condição do operador foram ignoradas.", file=saida)


def mostrar_plano(saida: Any) -> None:
    print("Plano com --executar (uma tentativa por serviço, de fora da rede, com a identidade do Azure CLI do operador):", file=saida)
    print("  armazenamento (Blob): listar 1 blob do contêiner do L300 (GET)", file=saida)
    print("  busca: contar os documentos do índice do L300 (GET)", file=saida)
    print("  modelos: pedir o embedding de um texto sintético fixo (POST; não grava nada, mas consome poucos tokens se o serviço "
          "aceitar o pedido)", file=saida)
    print("Aprovação: as três recusas com HTTP 403 e a causa identificada como acesso público desabilitado. Causa não identificada "
          "é pendência, não aprovação.", file=saida)


def mostrar_resultados(saida: Any, resultados: Sequence[Mapping[str, Any]]) -> None:
    print("Resultado por serviço (só códigos e causas; a mensagem do serviço nunca é exibida nem gravada):", file=saida)
    for item in resultados:
        http = "sem resposta" if item["http"] is None else f"HTTP {item['http']}"
        print(f"  {ROTULOS[item['dependencia']]}: {http}; causa: {item['causa'] or 'nenhuma (a operação foi aceita)'}; {item['resultado']}",
              file=saida)


_ORIENTACAO = {
    "aprovado": "APROVADO: as três recusas vieram do acesso público desabilitado. Registre acesso_privado.<dependência>.negativa = true.",
    "pendente": ("PENDENTE: nem toda recusa foi atribuída ao acesso público desabilitado. Mantenha a prova negativa como pendente (null) "
                 "nos serviços marcados acima e investigue DNS, conexão, autenticação, autorização ou a mensagem do serviço."),
    "reprovado": ("REPROVADO: um serviço aceitou a operação de fora da rede. O acesso público NÃO está bloqueado para ele: registre "
                  "false e revise o isolamento."),
    "erro": "SEM CONCLUSÃO: nenhum serviço respondeu. Confira a sua conexão e o DNS e repita; isto não aprova nem reprova o isolamento.",
}


def avaliar(entradas: Entradas, saida: Any) -> sonda.Resultado:
    exigir_relatorio_novo(entradas.relatorio)
    servicos = carregar_servicos(entradas.servicos, entradas)
    precondicoes = avaliar_precondicoes(servicos, carregar_papeis(entradas.papeis), entradas)
    modo = "executado" if entradas.executar else "simulado"
    print(f"Negativas externas do L300: {'EXECUÇÃO' if entradas.executar else 'SIMULAÇÃO (nenhuma rede, nenhum token)'}.", file=saida)
    mostrar_precondicoes(saida, precondicoes)
    dados: dict[str, Any] = {"modo": modo, "origem": "fora_da_rede", "rede": "nao_usada", "precondicoes": precondicoes.a_dict(),
                             "identidade": "nao_verificada", "resultados": [], "aprovado": False}
    if not precondicoes.ok:
        print("Pré-condição não atendida: nenhuma tentativa foi feita. Corrija o isolamento ou os papéis, exporte de novo e repita.",
              file=saida)
        return sonda.Resultado(ETAPA, sonda.DIVERGENCIA, "pendente", "precondicao_nao_atendida", dados)
    if not entradas.executar:
        mostrar_plano(saida)
        print("Nada foi enviado. Isto NÃO é a prova da negativa: repita com --executar para fazer as três tentativas.", file=saida)
        return sonda.Resultado(ETAPA, sonda.OK, "simulado", None, dados)
    resultados, identidade = executar_tentativas(entradas, precondicoes)
    veredicto, causa, codigo = decidir(resultados)
    dados.update(rede="usada", identidade=identidade, resultados=resultados, aprovado=veredicto == "aprovado")
    mostrar_resultados(saida, resultados)
    print(_ORIENTACAO[veredicto], file=saida)
    return sonda.Resultado(ETAPA, codigo, veredicto, causa, dados)


def principal(argv: Sequence[str] | None = None, saida: Any = None) -> int:
    saida = sys.stdout if saida is None else saida
    emissor = sonda.Emissor(saida)
    inicio = time.monotonic()
    privados: tuple[str, ...] = ()
    relatorio: Path | None = None
    logging.disable(logging.CRITICAL)
    try:
        try:
            entradas = ler_argumentos(argv)
            privados, relatorio = entradas.privados(), entradas.relatorio
            resultado = avaliar(entradas, saida)
        except Exception as erro:  # noqa: BLE001 - qualquer falha vira uma linha sentinela; Ctrl+C continua valendo
            falha = sonda.classificar_excecao(erro)
            resultado = sonda.Resultado(ETAPA, falha.codigo, falha.veredicto, falha.causa, falha.dados)
    finally:
        logging.disable(logging.NOTSET)
    resultado.duracao_s = round(time.monotonic() - inicio, 1)
    linha, codigo = sonda.linha_do_resultado(resultado, privados)  # a MESMA linha vai ao relatório e à saída, com o código dela
    if relatorio is not None and "modo" in resultado.dados:  # só um resultado avaliado vira relatório; erro de uso não
        try:
            gravar_relatorio(relatorio, linha)
        except OSError:
            print("[ERRO] Não foi possível criar o relatório (ele não é sobrescrito). O resultado abaixo continua valendo.", file=sys.stderr)
    emissor.emitir_linha(linha, codigo)
    return emissor.codigo


def _configurar_saida() -> None:
    with contextlib.suppress(Exception):
        sonda.mod.lab_comum.configurar_saida()  # acentos corretos em consoles e redirecionamentos do Windows


if __name__ == "__main__":
    _configurar_saida()
    sys.exit(principal())
