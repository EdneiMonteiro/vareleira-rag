"""Planejador e verificador de encerramento do laboratório L300/L400, 100% offline.

Este módulo NUNCA acessa o Azure: não usa rede, não executa o `az`, não abre processos e não apaga nada. Ele só (1) lê um
inventário e instantâneos que VOCÊ exportou, (2) valida tudo, (3) monta o texto de um plano ordenado de comandos para VOCÊ
revisar e executar por conta própria e (4) compara os instantâneos de antes e de depois. O único arquivo que ele grava é um
relatório novo e sanitizado (só contagens e vocabulário fechado), criado sem sobrescrever nada.

Fluxo (a CLI é scripts/planejar_encerramento.py)
    modelo      imprime um modelo de inventário para preencher
    capturar    imprime os comandos que exportam a linha de base (ANTES de criar o grupo exclusivo) e o estado final (DEPOIS)
    plano       valida o inventário (e a linha de base) e imprime o plano; nada é executado
    conferir    compara antes e depois e decide: aprovado (código 0), reprovado ou pendente (código 3)

Inventário (JSON privado, esquema versão 1). Guarde-o em local privado: ele traz identificadores do seu ambiente.
    versao                  1
    assinatura              GUID da assinatura do laboratório
    tenant                  GUID do tenant. Opcional, mas OBRIGATÓRIO quando há identidades_entra ou principais_proprios
                            (sem ele, um "não encontrado" do Graph poderia significar que você está no diretório errado)
    regiao                  região dos recursos (ex.: letras minúsculas e números, como as do `az account list-locations`)
    grupo                   nome do grupo de recursos EXCLUSIVO do laboratório
    grupo_exclusivo         true: atesta que só o laboratório usa o grupo. Qualquer outro valor recusa o plano
    grupo_gerenciado        opcional. Grupo gerenciado pelo Container Apps. É só conferido como ausente, nunca manipulado
    principais_proprios     lista de GUIDs de OBJETO (o principalId) dos principais criados pelo laboratório (identidades
                            gerenciadas e principais de serviço). NUNCA o clientId nem o appId: com eles o Microsoft Graph
                            responde 404 e a "ausência" ficaria vazia (veja a nota sobre IDs abaixo). Só atribuições de papel
                            desses principais podem ser revogadas
    recursos_proprios       lista de {id, tipo}: recursos do grupo exclusivo. O tipo precisa combinar com o ID
    shared_private_links    lista de {id}: shared private links da busca (os filhos do serviço de busca)
    atribuicoes_proprias    lista de {id, escopo, principal_id, papel_id}: atribuições de papel criadas pelo laboratório.
                            O escopo fica dentro do grupo exclusivo e o ID é <escopo>/providers/Microsoft.Authorization/
                            roleAssignments/<GUID>. O principal_id precisa estar em principais_proprios
    identidades_entra       lista de {objeto_id, app_id, nome, principal_id, chaves}: aplicativos do Entra ID criados pelo
                            laboratório. objeto_id é o ID de OBJETO do aplicativo (o `id`); app_id, o ID do aplicativo (client
                            id, o `appId`): são GUIDs DIFERENTES; nome, o nome de exibição (sem espaços); principal_id
                            (opcional), o ID de OBJETO do principal de serviço (o `id` dele, não o appId), que também precisa
                            estar em principais_proprios; chaves (opcional), os IDs das credenciais criadas (nunca o valor
                            do segredo)
    expurgos                lista de itens com exclusão reversível, cada um com "tipo":
                            conta_de_modelos {nome, regiao, grupo} (o grupo é o exclusivo) e cofre_de_chaves {nome, regiao}
    Toda lista é obrigatória (use [] quando não houver itens): um item de um tipo ausente só omite o passo correspondente.
    Campos desconhecidos são recusados, para que um erro de digitação não faça um passo sumir em silêncio.
    Nota sobre IDs: `az ad app|sp show|delete --id <GUID>` resolve PRIMEIRO pelo appId, mas as provas de ausência (Microsoft
    Graph) usam o ID de OBJETO. Confundir os dois (ou usar o clientId de uma identidade gerenciada) faria o Graph responder
    404 para um objeto que ainda existe: uma "ausência" vazia. Por isso um GUID só pode ter UM papel no inventário (o mesmo GUID
    não pode ser, ao mesmo tempo, objeto_id, app_id e principal) e cada passo do Entra confere o `id` e o `appId` lidos antes
    de apagar. Um GUID errado, porém distinto e bem formado, não é detectável offline: confira os IDs com os comandos que
    '--etapa modelo' mostra.

Instantâneos (listas JSON no formato do Azure CLI; use os comandos impressos por --etapa capturar)
    grupos        az group list                           campos usados: id, name
    recursos      az resource list                        campos usados: id, type
    papeis        az role assignment list --all           campos usados: id, principalId, roleDefinitionId, scope
    Listas paginadas (com nextLink) são recusadas: complete a listagem. Todo item precisa ser da assinatura do inventário.
    Linha de base ("antes"): capture ANTES de criar o grupo exclusivo. Ela é o que existia antes do laboratório; por isso
    nenhum item do inventário (nem do grupo exclusivo ou do gerenciado) pode constar nela, e o plano recusa o contrário.
    Uma linha de base totalmente vazia não prova nada (pode ser a assinatura errada): o plano a trata como prévia e a
    conferência a deixa pendente.
    Estado final ("depois"): capture depois de executar o plano.
    Presença ("presenca-depois.json"): {identificador_logico: "ausente" | "presente" | "indeterminado"}, gerado pelo trecho
    impresso por --etapa capturar --momento depois. Um 404 é "ausente", um sucesso é "presente" e qualquer outro resultado é
    "indeterminado". Os identificadores lógicos são tipo + 8 caracteres de um hash: não trazem IDs.

Guardas (cada uma recusa o plano com orientação para corrigir)
    - todo ID de recurso começa pelo prefixo exato /subscriptions/<assinatura>/resourceGroups/<grupo>/ (sem diferenciar
      caixa) e não contém "?", "#", "\\", "/../", "/./", "%", espaços, aspas, ponto e vírgula, crase, "$", "*" nem curingas;
      GUIDs e nomes seguem padrões fechados;
    - o grupo precisa ser atestado como exclusivo e não pode constar na linha de base; nenhum ID do inventário pode constar
      nela; nenhum principal próprio pode já ter papéis na linha de base;
    - toda atribuição: ID de roleAssignment, escopo dentro do grupo exclusivo (igual ou subcaminho) e principal próprio;
    - um GUID só pode ter um papel (ID de objeto, ID do aplicativo, credencial, definição de papel, assinatura, tenant);
    - nenhum comando impresso usa curinga, --all, filtro por nome parcial ou ID deduzido: todo alvo vem literalmente do
      inventário (os dois nomes que o `az search` exige são extraídos do ID literal do link por uma expressão fechada);
    - todo bloco impresso é UM comando composto que se recusa a rodar, sem executar nada, fora do PowerShell 7 e enquanto a
      PREPARAÇÃO não tiver sido concluída na mesma janela (um `throw` solto não serviria: colado linha a linha no Windows
      PowerShell 5.1, ele não interromperia as linhas seguintes). Os blocos que leem listas JSON filtram em duas etapas e
      exigem EXATAMENTE um item, porque no 5.1 `ConvertFrom-Json | Where-Object` devolve a lista inteira.

Ordem do plano (obrigatória; fases sem itens são omitidas)
    1 consumidores (aplicativos e jobs do Container Apps)   2 shared private links da busca (antes do serviço de busca e
    dos destinos)   3 Entra ID: credenciais, principal de serviço, aplicativo e expurgo em deletedItems   4 atribuições de
    papel próprias, por ID exato   5 workspace do Log Analytics (exclusão permanente)   6 ambientes do Container Apps,
    pelo serviço, sem tocar o grupo gerenciado   7 grupo exclusivo   8 expurgo de itens com exclusão reversível.
    Cada passo traz título, efeito (reversível ou irreversível), o comando e a verificação de ausência por listagem ou por
    consulta direta. Um comando de espera (ou um código de saída 0) NÃO prova ausência.

Limites
    O plano e a conferência trabalham sobre os arquivos que você exportou; eles não provam o estado atual do Azure, não
    acham o que não está no inventário e não medem custo. Se os três arquivos de depois forem idênticos aos de antes, a
    conferência avisa (pode ser só o mesmo arquivo informado duas vezes). Mudanças legítimas de terceiros entre a linha de
    base e o encerramento aparecem como divergência: investigue, a ferramenta não decide por você. A ferramenta não imprime
    IDs nas mensagens de conferência nem nos relatórios; o plano em si precisa dos IDs, por isso é privado.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from lab_comum import CODIGO_DIVERGENCIA, CODIGO_INESPERADO, ErroLab

VERSAO_DO_INVENTARIO = 1
VERSAO_DO_RELATORIO = 1
LIMITE_DE_ARQUIVO_BYTES = 32 * 1024 * 1024
LIMITE_DE_ITENS = 500
LIMITE_DE_ITENS_DO_INSTANTANEO = 500_000
LIMITE_DE_PROBLEMAS = 25
LIMITE_DE_EXEMPLOS = 5

REVERSIVEL = "reversivel"
IRREVERSIVEL = "irreversivel"
ROTULO_DO_EFEITO = {REVERSIVEL: "reversível", IRREVERSIVEL: "irreversível"}

ESTADOS_DE_PRESENCA = ("ausente", "presente", "indeterminado")
MOMENTOS = ("antes", "depois")

# Tipos de passo (vocabulário fechado dos relatórios): tipo -> (fase, efeito)
PASSO_APLICATIVO = "aplicativo_container_app"
PASSO_JOB = "job_container_app"
PASSO_LINK = "link_privado_busca"
PASSO_CREDENCIAL = "credencial_entra"
PASSO_PRINCIPAL = "principal_servico_entra"
PASSO_EXPURGO_PRINCIPAL = "expurgo_principal_servico"
PASSO_APLICATIVO_ENTRA = "aplicativo_entra"
PASSO_EXPURGO_APLICATIVO = "expurgo_aplicativo"
PASSO_ATRIBUICAO = "atribuicao_papel"
PASSO_WORKSPACE = "workspace_logs"
PASSO_AMBIENTE = "ambiente_container_apps"
PASSO_GRUPO = "grupo_exclusivo"
PASSO_EXPURGO_MODELOS = "expurgo_conta_de_modelos"
PASSO_EXPURGO_COFRE = "expurgo_cofre_de_chaves"

TIPOS_DE_PASSO: dict[str, tuple[int, str]] = {
    PASSO_APLICATIVO: (1, IRREVERSIVEL),
    PASSO_JOB: (1, IRREVERSIVEL),
    PASSO_LINK: (2, IRREVERSIVEL),
    PASSO_CREDENCIAL: (3, IRREVERSIVEL),
    PASSO_PRINCIPAL: (3, REVERSIVEL),
    PASSO_EXPURGO_PRINCIPAL: (3, IRREVERSIVEL),
    PASSO_APLICATIVO_ENTRA: (3, REVERSIVEL),
    PASSO_EXPURGO_APLICATIVO: (3, IRREVERSIVEL),
    PASSO_ATRIBUICAO: (4, IRREVERSIVEL),
    PASSO_WORKSPACE: (5, IRREVERSIVEL),
    PASSO_AMBIENTE: (6, IRREVERSIVEL),
    PASSO_GRUPO: (7, IRREVERSIVEL),
    PASSO_EXPURGO_MODELOS: (8, IRREVERSIVEL),
    PASSO_EXPURGO_COFRE: (8, IRREVERSIVEL),
}
FASES = {
    1: "Consumidores: aplicativos e jobs do Container Apps",
    2: "Shared private links da busca (antes do serviço de busca e dos destinos)",
    3: "Microsoft Entra ID: credenciais, principal de serviço, aplicativo e expurgo em deletedItems",
    4: "Atribuições de papel próprias (por ID exato)",
    5: "Workspace do Log Analytics (exclusão permanente)",
    6: "Ambientes do Container Apps (pelo serviço; o grupo gerenciado não é tocado)",
    7: "Grupo exclusivo do laboratório",
    8: "Expurgo de itens com exclusão reversível",
}

TIPO_APLICATIVO = "microsoft.app/containerapps"
TIPO_JOB = "microsoft.app/jobs"
TIPO_AMBIENTE = "microsoft.app/managedenvironments"
TIPO_WORKSPACE = "microsoft.operationalinsights/workspaces"
TIPO_LINK = "microsoft.search/searchservices/sharedprivatelinkresources"
TIPO_ATRIBUICAO = "microsoft.authorization/roleassignments"
TIPOS_RESERVADOS = {TIPO_LINK: "shared_private_links", TIPO_ATRIBUICAO: "atribuicoes_proprias"}
TIPOS_COM_PASSO_PROPRIO = (TIPO_APLICATIVO, TIPO_JOB, TIPO_AMBIENTE, TIPO_WORKSPACE)

EXPURGO_CONTA_DE_MODELOS = "conta_de_modelos"
EXPURGO_COFRE_DE_CHAVES = "cofre_de_chaves"

# Categorias de presença = identificadores dos critérios da conferência que dependem do arquivo de presença.
ENTRA_APLICATIVOS = "entra_aplicativos_ausentes"
ENTRA_PRINCIPAIS = "entra_principais_ausentes"
ENTRA_EXCLUIDOS = "entra_itens_excluidos_expurgados"
EXPURGO_MODELOS = "expurgo_conta_de_modelos"
EXPURGO_COFRE = "expurgo_cofre_de_chaves"

CRITERIOS = {
    "linha_de_base_com_itens": "A linha de base tem ao menos um item (totalmente vazia, ela poderia ser a assinatura errada).",
    "grupo_proprio_ausente": "O grupo exclusivo do laboratório não aparece mais na listagem de grupos.",
    "grupo_gerenciado_ausente": "O grupo gerenciado do Container Apps não aparece mais na listagem de grupos.",
    "grupos_anteriores_preservados": "Todos os grupos da linha de base continuam presentes.",
    "recursos_anteriores_preservados": "Todos os recursos da linha de base continuam presentes, com o mesmo tipo.",
    "recursos_proprios_ausentes": "Nenhum recurso resta dentro do grupo exclusivo (nem do gerenciado).",
    "atribuicoes_anteriores_preservadas": "Todas as atribuições de papel da linha de base continuam iguais (principal, papel e escopo).",
    "atribuicoes_proprias_ausentes": "Nenhuma atribuição própria resta (escopo no grupo exclusivo ou ID do inventário).",
    ENTRA_APLICATIVOS: "Os aplicativos do Entra ID do inventário estão ausentes (404 no Graph).",
    ENTRA_PRINCIPAIS: "Os principais próprios (principais de serviço e identidades gerenciadas) estão ausentes (404 no Graph).",
    ENTRA_EXCLUIDOS: "Nenhum item do inventário permanece em directory/deletedItems (404 no Graph).",
    EXPURGO_MODELOS: "A conta de modelos própria não aparece mais entre as contas excluídas.",
    EXPURGO_COFRE: "O cofre de chaves próprio não aparece mais entre os cofres excluídos.",
}
ESTADOS_DE_CRITERIO = ("atendido", "reprovado", "pendente", "nao_aplicavel")

ARQUIVOS_DE_CAPTURA = {
    "antes": {"grupos": "grupos-antes.json", "recursos": "recursos-antes.json", "papeis": "papeis-antes.json"},
    "depois": {"grupos": "grupos-depois.json", "recursos": "recursos-depois.json", "papeis": "papeis-depois.json",
               "presenca": "presenca-depois.json"},
}

CAMPOS_DO_INVENTARIO = ("versao", "assinatura", "tenant", "regiao", "grupo", "grupo_exclusivo", "grupo_gerenciado",
                        "principais_proprios", "recursos_proprios", "shared_private_links", "atribuicoes_proprias",
                        "identidades_entra", "expurgos")
CAMPOS_OBRIGATORIOS = tuple(c for c in CAMPOS_DO_INVENTARIO if c not in ("tenant", "grupo_gerenciado"))

_SEGMENTO_DE_NOME = r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}"
_SEGMENTO_DE_TIPO = r"[A-Za-z][A-Za-z0-9]*"
_NAMESPACE = r"[A-Za-z][A-Za-z0-9]*(?:\.[A-Za-z0-9]+)+"
_GUID = re.compile(r"[0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}")
_NOME_DO_GRUPO = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,89}")
_NOME_DE_EXIBICAO = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,119}")
_NOME_DE_RECURSO = re.compile(_SEGMENTO_DE_NOME)
_NOME_DO_COFRE = re.compile(r"[A-Za-z][A-Za-z0-9-]{1,22}[A-Za-z0-9]")
_REGIAO = re.compile(r"[a-z0-9]{3,32}")
_TIPO_DE_RECURSO = re.compile(_NAMESPACE + r"(?:/" + _SEGMENTO_DE_TIPO + r")+")
_RESTO_DO_ID = re.compile(r"providers/" + _NAMESPACE + r"/" + _SEGMENTO_DE_TIPO + r"/" + _SEGMENTO_DE_NOME
                          + r"(?:/" + _SEGMENTO_DE_TIPO + r"/" + _SEGMENTO_DE_NOME + r")*")
_RESTO_DO_LINK = re.compile(r"providers/Microsoft\.Search/searchServices/(?P<servico>" + _SEGMENTO_DE_NOME
                            + r")/sharedPrivateLinkResources/(?P<nome>" + _SEGMENTO_DE_NOME + r")", re.IGNORECASE)
_PASTA = re.compile(r"[\w .\-\\/:()~]{1,240}")
_NOME_DE_RELATORIO = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,95}\.json")
_SEGURO_NO_POWERSHELL = re.compile(r"[A-Za-z0-9._/:-]+")
_CHAVE_DE_CAMPO = re.compile(r"[a-z_]{1,40}")

_PROIBIDOS_EM_IDS = (
    ("?", "o caractere '?'"), ("#", "o caractere '#'"), ("\\", "uma barra invertida"), ("//", "'//'"), ("/../", "'/../'"),
    ("/./", "'/./'"), ("%", "o caractere '%'"), (" ", "um espaço"), ("'", "aspas simples"), ('"', "aspas duplas"),
    (";", "ponto e vírgula"), ("`", "uma crase"), ("$", "o caractere '$'"), ("*", "o curinga '*'"),
)
_ESPECIAIS_EM_IDS = set("[]{}()|&<>!=+,@^~:")


# --------------------------------------------------------------------------------------
# Dados validados
# --------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Recurso:
    id: str
    tipo: str


@dataclass(frozen=True)
class Link:
    id: str
    servico: str
    nome: str


@dataclass(frozen=True)
class Atribuicao:
    id: str
    escopo: str
    principal_id: str
    papel_id: str


@dataclass(frozen=True)
class IdentidadeEntra:
    objeto_id: str
    app_id: str
    nome: str
    principal_id: str | None
    chaves: tuple[str, ...]


@dataclass(frozen=True)
class Expurgo:
    tipo: str
    nome: str
    regiao: str
    grupo: str | None


@dataclass(frozen=True)
class Inventario:
    assinatura: str
    tenant: str | None
    regiao: str
    grupo: str
    grupo_gerenciado: str | None
    principais_proprios: tuple[str, ...]
    recursos: tuple[Recurso, ...]
    links: tuple[Link, ...]
    atribuicoes: tuple[Atribuicao, ...]
    identidades: tuple[IdentidadeEntra, ...]
    expurgos: tuple[Expurgo, ...]
    sha256: str = ""

    @property
    def prefixo(self) -> str:
        return f"/subscriptions/{self.assinatura}/resourceGroups/{self.grupo}"

    @property
    def prefixo_gerenciado(self) -> str | None:
        if self.grupo_gerenciado is None:
            return None
        return f"/subscriptions/{self.assinatura}/resourceGroups/{self.grupo_gerenciado}"

    @property
    def prefixos_proprios(self) -> tuple[str, ...]:
        """Prefixos (minúsculos, com barra final) que pertencem ao laboratório: o grupo exclusivo e o gerenciado."""
        return tuple(p.lower() + "/" for p in (self.prefixo, self.prefixo_gerenciado) if p)

    @property
    def ids(self) -> frozenset[str]:
        """IDs (minúsculos) de recursos, links e atribuições do inventário."""
        return frozenset(i.lower() for i in (*(r.id for r in self.recursos), *(l.id for l in self.links),
                                              *(a.id for a in self.atribuicoes)))

    @property
    def usa_graph(self) -> bool:
        return bool(self.identidades or self.principais_proprios)


@dataclass(frozen=True)
class Instantaneo:
    """Estado exportado de uma assinatura: nomes de grupos, recursos (id -> tipo) e atribuições (id -> principal, papel, escopo).

    Tudo em minúsculas: o Azure não diferencia caixa em nomes e IDs.
    """

    grupos: frozenset[str]
    recursos: Mapping[str, str]
    atribuicoes: Mapping[str, tuple[str, str, str]]
    sha256: Mapping[str, str]

    @property
    def vazio(self) -> bool:
        return not (self.grupos or self.recursos or self.atribuicoes)


@dataclass(frozen=True)
class Passo:
    numero: int
    fase: int
    tipo: str
    titulo: str
    efeito: str
    comando: str
    verificacao: str
    nota: str = ""


@dataclass(frozen=True)
class ItemDeFechamento:
    texto: str
    comando: str = ""


@dataclass(frozen=True)
class Plano:
    precondicoes: tuple[str, ...]
    preparacao: str
    passos: tuple[Passo, ...]
    fechamento: tuple[ItemDeFechamento, ...]
    removidos_com_o_grupo: Mapping[str, int]
    fases_omitidas: tuple[int, ...]
    linha_de_base_conferida: bool
    inventario_sha256: str


@dataclass(frozen=True)
class ItemDePresenca:
    chave: str
    categoria: str
    metodo: str  # "graph", "conta_de_modelos" ou "cofre_de_chaves"
    alvo: str


@dataclass(frozen=True)
class Criterio:
    id: str
    estado: str
    conferidos: int
    divergentes: int
    pendentes: int
    detalhe: str


@dataclass(frozen=True)
class Conferencia:
    resultado: str  # aprovado, reprovado ou pendente
    criterios: tuple[Criterio, ...]
    avisos: tuple[str, ...]
    linha_de_base: Mapping[str, int]
    inventario: Mapping[str, int]
    sha256: Mapping[str, str]


# --------------------------------------------------------------------------------------
# Leitura de arquivos
# --------------------------------------------------------------------------------------

def _recusar_constante(_nome: str) -> Any:
    raise ValueError("constante JSON não padronizada")


def ler_json(caminho: Path, descricao: str) -> tuple[Any, str]:
    """Lê um JSON local (UTF-8, com ou sem BOM, ou UTF-16 do PowerShell 5) e devolve (dados, sha256 dos bytes).

    As mensagens citam só `descricao` (por exemplo, o nome da opção), nunca o caminho nem o conteúdo.
    """
    caminho = Path(caminho)
    try:
        if not caminho.is_file():
            raise ErroLab(f"Arquivo não encontrado ({descricao}). Confira o caminho informado.")
        if caminho.stat().st_size > LIMITE_DE_ARQUIVO_BYTES:
            raise ErroLab(f"O arquivo ({descricao}) passa de {LIMITE_DE_ARQUIVO_BYTES // (1024 * 1024)} MiB e não foi lido.")
        bruto = caminho.read_bytes()
    except OSError:
        raise ErroLab(f"Não foi possível ler o arquivo ({descricao}).") from None
    try:
        texto = bruto.decode("utf-16") if bruto.startswith((b"\xff\xfe", b"\xfe\xff")) else bruto.decode("utf-8-sig")
        return json.loads(texto, parse_constant=_recusar_constante), hashlib.sha256(bruto).hexdigest()
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise ErroLab(f"O arquivo ({descricao}) não contém JSON válido. Se ele veio de um comando que falhou, apague-o e repita a "
                      "exportação com os comandos de '--etapa capturar'.") from None


def exigir_relatorio_novo(caminho: Path | None) -> Path | None:
    """Confere o destino do relatório ANTES de qualquer trabalho: nome limitado, pasta existente, arquivo inexistente."""
    if caminho is None:
        return None
    caminho = Path(caminho)
    if not _NOME_DE_RELATORIO.fullmatch(caminho.name):
        raise ErroLab("O nome do relatório deve ter até 100 caracteres, começar por letra ou número, usar só letras, números, "
                      "'.', '_' e '-', e terminar em .json.")
    if not caminho.parent.is_dir():
        raise ErroLab("A pasta do relatório não existe. Crie a pasta e repita.")
    if caminho.exists():
        raise ErroLab("O relatório já existe e não é sobrescrito. Escolha outro nome.")
    return caminho


def gravar_relatorio(caminho: Path, dados: Mapping[str, Any]) -> None:
    """Cria o relatório em um arquivo NOVO (nunca sobrescreve) e, em sistemas POSIX, legível só pelo dono."""
    texto = json.dumps(dados, ensure_ascii=False, indent=2) + "\n"
    try:
        descritor = os.open(caminho, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raise ErroLab("O relatório já existe e não é sobrescrito. Escolha outro nome.") from None
    except OSError:
        raise ErroLab("Não foi possível criar o relatório.") from None
    with os.fdopen(descritor, "w", encoding="utf-8", newline="\n") as arquivo:
        arquivo.write(texto)


# --------------------------------------------------------------------------------------
# Validação do inventário
# --------------------------------------------------------------------------------------

class _Problemas:
    """Acumula os problemas para mostrar todos de uma vez. As mensagens citam o campo, nunca o valor."""

    def __init__(self) -> None:
        self.itens: list[str] = []

    def add(self, rotulo: str, mensagem: str) -> None:
        self.itens.append(f"{rotulo}: {mensagem}")

    def levantar(self, titulo: str, orientacao: str, codigo: int | None = None) -> None:
        if not self.itens:
            return
        itens = self.itens[:LIMITE_DE_PROBLEMAS]
        resto = len(self.itens) - len(itens)
        texto = titulo + "\n  - " + "\n  - ".join(itens)
        if resto > 0:
            texto += f"\n  - ... e mais {resto} problema(s)."
        if codigo is None:
            raise ErroLab(f"{texto}\n{orientacao}")
        raise ErroLab(f"{texto}\n{orientacao}", codigo)


def _chave_segura(chave: Any) -> str:
    return chave if isinstance(chave, str) and _CHAVE_DE_CAMPO.fullmatch(chave) else "<campo>"


def _guid(p: _Problemas, rotulo: str, valor: Any) -> str | None:
    if not isinstance(valor, str) or not _GUID.fullmatch(valor):
        p.add(rotulo, "deve ser um GUID (oito, quatro, quatro, quatro e doze caracteres hexadecimais separados por hífen).")
        return None
    return valor.lower()


def _texto(p: _Problemas, rotulo: str, valor: Any, padrao: re.Pattern[str], dica: str) -> str | None:
    if not isinstance(valor, str) or not padrao.fullmatch(valor):
        p.add(rotulo, dica)
        return None
    return valor


def _lista(p: _Problemas, rotulo: str, valor: Any) -> list[Any]:
    if not isinstance(valor, list):
        p.add(rotulo, "deve ser uma lista (use [] quando não houver itens).")
        return []
    if len(valor) > LIMITE_DE_ITENS:
        p.add(rotulo, f"tem itens demais (limite de {LIMITE_DE_ITENS}). Revise o inventário.")
        return []
    return valor


def _chaves_exatas(p: _Problemas, rotulo: str, item: dict[Any, Any], obrigatorias: Sequence[str],
                   opcionais: Sequence[str] = ()) -> None:
    for chave in item:
        if chave not in obrigatorias and chave not in opcionais:
            p.add(rotulo, f"campo desconhecido: {_chave_segura(chave)}.")
    for chave in obrigatorias:
        if chave not in item:
            p.add(rotulo, f"campo obrigatório ausente: {chave}.")


_PAPEIS_DE_GUID = {
    "assinatura": "o ID da assinatura",
    "tenant": "o ID do tenant",
    "principal": "o ID de OBJETO de um principal (principais_proprios, principal_id)",
    "objeto": "o ID de OBJETO de um aplicativo (objeto_id)",
    "app": "o ID de um aplicativo (app_id, o client id)",
    "chave": "o ID de uma credencial (chaves)",
    "papel": "o ID de uma definição de papel (papel_id)",
}


def _recusar_guid_em_dois_papeis(p: _Problemas, usos: Sequence[tuple[str, str, str]]) -> None:
    """Recusa o GUID que aparece com papéis diferentes. Repetir o mesmo papel é normal (um principal próprio aparece em
    principais_proprios, na identidade e nas atribuições). As mensagens citam só os campos, nunca o valor."""
    primeiro: dict[str, tuple[str, str]] = {}
    for guid, papel, rotulo in usos:
        anterior = primeiro.setdefault(guid, (papel, rotulo))
        if anterior[0] != papel:
            p.add(rotulo, f"este GUID também aparece como {_PAPEIS_DE_GUID[anterior[0]]} em {anterior[1]}: cada GUID tem um só papel. "
                          "O ID de objeto, o ID do aplicativo (client id) e o ID do principal de serviço são GUIDs diferentes: "
                          "releia-os com os comandos mostrados por '--etapa modelo'.")


def caractere_proibido_em_id(valor: str) -> str | None:
    """Descreve o primeiro caractere ou sequência que um ID de recurso nunca pode ter, ou None."""
    for sequencia, descricao in _PROIBIDOS_EM_IDS:
        if sequencia in valor:
            return descricao
    if not valor.isascii() or not valor.isprintable() or any(c in _ESPECIAIS_EM_IDS for c in valor):
        return "um caractere especial ou fora do conjunto permitido"
    return None


def _id_do_grupo(p: _Problemas, rotulo: str, valor: Any, prefixo: str) -> str | None:
    """Guarda do ID: prefixo exato do grupo exclusivo, sem caracteres de escape ou curingas e com estrutura de ID do ARM."""
    if not isinstance(valor, str) or not valor or len(valor) > 1024:
        p.add(rotulo, "o ID deve ser um texto de até 1024 caracteres.")
        return None
    proibido = caractere_proibido_em_id(valor)
    if proibido:
        p.add(rotulo, f"o ID contém {proibido}. Curingas, caracteres de escape, aspas e separadores são recusados.")
        return None
    if not valor.lower().startswith(prefixo.lower() + "/"):
        p.add(rotulo, "o ID não começa pelo prefixo /subscriptions/<assinatura>/resourceGroups/<grupo>/ do grupo exclusivo. "
                      "Esta ferramenta nunca planeja apagar algo fora dele: corrija o ID ou remova o item.")
        return None
    if not _RESTO_DO_ID.fullmatch(valor[len(prefixo) + 1:]):
        p.add(rotulo, "o ID não tem a forma .../providers/<namespace>/<tipo>/<nome>[/<tipo>/<nome>].")
        return None
    return valor


def _escopo_do_grupo(p: _Problemas, rotulo: str, valor: Any, prefixo: str) -> str | None:
    if isinstance(valor, str) and valor.lower() == prefixo.lower() and valor.isascii() and valor.isprintable():
        return valor
    return _id_do_grupo(p, rotulo, valor, prefixo)


def _tipo_do_id(valor: str, prefixo: str) -> str:
    partes = valor[len(prefixo) + 1:].split("/")
    return partes[1] + "/" + "/".join(partes[2::2])


def carregar_inventario(caminho: Path) -> Inventario:
    dados, sha256 = ler_json(caminho, "--inventario")
    return inventario_de_dados(dados, sha256)


def inventario_de_dados(dados: Any, sha256: str = "") -> Inventario:  # noqa: C901 - uma validação linear, campo a campo
    if not isinstance(dados, dict):
        raise ErroLab("O inventário precisa ser um objeto JSON. Use '--etapa modelo' para ver o formato.")
    p = _Problemas()
    for chave in dados:
        if chave not in CAMPOS_DO_INVENTARIO:
            p.add("inventario", f"campo desconhecido: {_chave_segura(chave)}.")
    for chave in CAMPOS_OBRIGATORIOS:
        if chave not in dados:
            p.add(chave, "campo obrigatório ausente.")
    versao = dados.get("versao")
    if isinstance(versao, bool) or versao != VERSAO_DO_INVENTARIO:
        p.add("versao", f"deve ser {VERSAO_DO_INVENTARIO}.")
    assinatura = _guid(p, "assinatura", dados.get("assinatura")) if "assinatura" in dados else None
    tenant = _guid(p, "tenant", dados["tenant"]) if dados.get("tenant") is not None else None
    usos: list[tuple[str, str, str]] = []  # (GUID, papel, campo): cada GUID só pode ter um papel

    def usar(papel: str, rotulo: str, guid: str | None) -> None:
        if guid:
            usos.append((guid, papel, rotulo))

    usar("assinatura", "assinatura", assinatura)
    usar("tenant", "tenant", tenant)
    regiao = _texto(p, "regiao", dados.get("regiao"), _REGIAO, "deve ter de 3 a 32 letras minúsculas e números (por exemplo, a "
                    "região mostrada por 'az account list-locations').") if "regiao" in dados else None
    grupo = _texto(p, "grupo", dados.get("grupo"), _NOME_DO_GRUPO, "deve ter até 90 caracteres: letras, números, '.', '_' e '-', "
                   "começando por letra ou número.") if "grupo" in dados else None
    if grupo is not None and grupo.endswith("."):
        p.add("grupo", "não pode terminar com ponto.")
        grupo = None
    if "grupo_exclusivo" in dados and dados["grupo_exclusivo"] is not True:
        p.add("grupo_exclusivo", "deve ser true. É a sua atestação de que SÓ o laboratório usa o grupo: se alguém mais o usa, "
                                 "ele não é exclusivo e esta ferramenta não planeja removê-lo.")
    gerenciado = None
    if dados.get("grupo_gerenciado") is not None:
        gerenciado = _texto(p, "grupo_gerenciado", dados["grupo_gerenciado"], _NOME_DO_GRUPO, "deve ser um nome de grupo válido.")
        if gerenciado is not None and grupo is not None and gerenciado.lower() == grupo.lower():
            p.add("grupo_gerenciado", "não pode ser o mesmo grupo exclusivo.")
            gerenciado = None
    if assinatura is None or grupo is None:
        p.levantar("Inventário inválido:", "Corrija o inventário e repita; nenhum comando foi gerado.")
        raise ErroLab("Inventário inválido: assinatura e grupo são obrigatórios.")
    prefixo = f"/subscriptions/{assinatura}/resourceGroups/{grupo}"

    def lista(chave: str) -> list[Any]:
        return _lista(p, chave, dados[chave]) if chave in dados else []

    principais: list[str] = []
    for i, item in enumerate(lista("principais_proprios")):
        guid = _guid(p, f"principais_proprios[{i}]", item)
        usar("principal", f"principais_proprios[{i}]", guid)
        if guid:
            principais.append(guid)
    if len(set(principais)) != len(principais):
        p.add("principais_proprios", "há GUIDs repetidos.")
    conhecidos = set(principais)

    recursos: list[Recurso] = []
    for i, item in enumerate(lista("recursos_proprios")):
        rotulo = f"recursos_proprios[{i}]"
        if not isinstance(item, dict):
            p.add(rotulo, "deve ser um objeto {id, tipo}.")
            continue
        _chaves_exatas(p, rotulo, item, ("id", "tipo"))
        id_ = _id_do_grupo(p, f"{rotulo}.id", item.get("id"), prefixo)
        tipo = _texto(p, f"{rotulo}.tipo", item.get("tipo"), _TIPO_DE_RECURSO, "deve ser um tipo do ARM, como Microsoft.App/containerApps.")
        if id_ is None or tipo is None:
            continue
        if tipo.lower() != _tipo_do_id(id_, prefixo).lower():
            p.add(rotulo, "o tipo não combina com o ID.")
        elif tipo.lower() in TIPOS_RESERVADOS:
            p.add(rotulo, f"este tipo tem lista própria: informe-o em {TIPOS_RESERVADOS[tipo.lower()]}.")
        else:
            recursos.append(Recurso(id_, tipo))

    links: list[Link] = []
    for i, item in enumerate(lista("shared_private_links")):
        rotulo = f"shared_private_links[{i}]"
        if not isinstance(item, dict):
            p.add(rotulo, "deve ser um objeto {id}.")
            continue
        _chaves_exatas(p, rotulo, item, ("id",))
        id_ = _id_do_grupo(p, f"{rotulo}.id", item.get("id"), prefixo)
        if id_ is None:
            continue
        achado = _RESTO_DO_LINK.fullmatch(id_[len(prefixo) + 1:])
        if achado is None:
            p.add(f"{rotulo}.id", "deve ser o ID de um link: .../providers/Microsoft.Search/searchServices/<serviço>/"
                                  "sharedPrivateLinkResources/<nome>.")
            continue
        links.append(Link(id_, achado.group("servico"), achado.group("nome")))

    atribuicoes: list[Atribuicao] = []
    for i, item in enumerate(lista("atribuicoes_proprias")):
        rotulo = f"atribuicoes_proprias[{i}]"
        if not isinstance(item, dict):
            p.add(rotulo, "deve ser um objeto {id, escopo, principal_id, papel_id}.")
            continue
        _chaves_exatas(p, rotulo, item, ("id", "escopo", "principal_id", "papel_id"))
        escopo = _escopo_do_grupo(p, f"{rotulo}.escopo", item.get("escopo"), prefixo)
        id_ = _id_do_grupo(p, f"{rotulo}.id", item.get("id"), prefixo)
        principal = _guid(p, f"{rotulo}.principal_id", item.get("principal_id"))
        papel = _guid(p, f"{rotulo}.papel_id", item.get("papel_id"))
        usar("principal", f"{rotulo}.principal_id", principal)
        usar("papel", f"{rotulo}.papel_id", papel)
        if escopo and id_:
            esperado = escopo.lower() + "/providers/microsoft.authorization/roleassignments/"
            if not (id_.lower().startswith(esperado) and _GUID.fullmatch(id_[len(esperado):])):
                p.add(rotulo, "o ID não é de uma atribuição desse escopo: use <escopo>/providers/Microsoft.Authorization/"
                              "roleAssignments/<GUID>.")
                continue
        if principal and principal not in conhecidos:
            p.add(rotulo, "o principal não está em principais_proprios. Esta ferramenta só revoga papéis de principais criados "
                          "pelo laboratório: preserve papéis herdados e de outros recursos.")
            continue
        if escopo and id_ and principal and papel:
            atribuicoes.append(Atribuicao(id_, escopo, principal, papel))

    identidades: list[IdentidadeEntra] = []
    for i, item in enumerate(lista("identidades_entra")):
        rotulo = f"identidades_entra[{i}]"
        if not isinstance(item, dict):
            p.add(rotulo, "deve ser um objeto {objeto_id, app_id, nome, principal_id, chaves}.")
            continue
        _chaves_exatas(p, rotulo, item, ("objeto_id", "app_id", "nome"), ("principal_id", "chaves"))
        objeto = _guid(p, f"{rotulo}.objeto_id", item.get("objeto_id"))
        app = _guid(p, f"{rotulo}.app_id", item.get("app_id"))
        nome = _texto(p, f"{rotulo}.nome", item.get("nome"), _NOME_DE_EXIBICAO,
                      "deve ser o nome de exibição do aplicativo: letras, números, '.', '_' e '-', sem espaços.")
        principal = _guid(p, f"{rotulo}.principal_id", item["principal_id"]) if item.get("principal_id") is not None else None
        usar("objeto", f"{rotulo}.objeto_id", objeto)
        usar("app", f"{rotulo}.app_id", app)
        usar("principal", f"{rotulo}.principal_id", principal)
        if principal and principal not in conhecidos:
            p.add(f"{rotulo}.principal_id", "o principal de serviço também precisa constar em principais_proprios.")
        chaves: list[str] = []
        for j, chave in enumerate(_lista(p, f"{rotulo}.chaves", item["chaves"]) if "chaves" in item else []):
            guid = _guid(p, f"{rotulo}.chaves[{j}]", chave)
            usar("chave", f"{rotulo}.chaves[{j}]", guid)
            if guid:
                chaves.append(guid)
        if len(set(chaves)) != len(chaves):
            p.add(f"{rotulo}.chaves", "há GUIDs repetidos.")
        if objeto and app and nome:
            identidades.append(IdentidadeEntra(objeto, app, nome, principal, tuple(chaves)))
    for campo in ("objeto_id", "app_id", "principal_id"):
        valores = [getattr(i, campo) for i in identidades if getattr(i, campo)]
        if len(set(valores)) != len(valores):
            p.add("identidades_entra", f"há {campo} repetido.")
    chaves_vistas: set[str] = set()
    for identidade in identidades:
        if chaves_vistas & set(identidade.chaves):
            p.add("identidades_entra", "há credenciais (chaves) repetidas entre identidades diferentes.")
            break
        chaves_vistas |= set(identidade.chaves)

    expurgos: list[Expurgo] = []
    for i, item in enumerate(lista("expurgos")):
        rotulo = f"expurgos[{i}]"
        if not isinstance(item, dict):
            p.add(rotulo, "deve ser um objeto com 'tipo'.")
            continue
        tipo = item.get("tipo")
        if tipo == EXPURGO_CONTA_DE_MODELOS:
            _chaves_exatas(p, rotulo, item, ("tipo", "nome", "regiao", "grupo"))
            nome = _texto(p, f"{rotulo}.nome", item.get("nome"), _NOME_DE_RECURSO, "deve ser o nome da conta de modelos.")
            area = _texto(p, f"{rotulo}.regiao", item.get("regiao"), _REGIAO, "deve ser uma região válida.")
            grupo_da_conta = _texto(p, f"{rotulo}.grupo", item.get("grupo"), _NOME_DO_GRUPO, "deve ser o grupo exclusivo.")
            if grupo_da_conta and grupo_da_conta.lower() != grupo.lower():
                p.add(f"{rotulo}.grupo", "deve ser o grupo exclusivo do laboratório: nunca se expurga uma conta de outro grupo.")
            elif nome and area and grupo_da_conta:
                expurgos.append(Expurgo(tipo, nome, area, grupo_da_conta))
        elif tipo == EXPURGO_COFRE_DE_CHAVES:
            _chaves_exatas(p, rotulo, item, ("tipo", "nome", "regiao"))
            nome = _texto(p, f"{rotulo}.nome", item.get("nome"), _NOME_DO_COFRE,
                          "deve ter de 3 a 24 caracteres: letras, números e hífens, começando por letra.")
            area = _texto(p, f"{rotulo}.regiao", item.get("regiao"), _REGIAO, "deve ser uma região válida.")
            if nome and area:
                expurgos.append(Expurgo(tipo, nome, area, None))
        else:
            p.add(rotulo, f"'tipo' deve ser {EXPURGO_CONTA_DE_MODELOS} ou {EXPURGO_COFRE_DE_CHAVES}.")

    todos = [*(r.id for r in recursos), *(l.id for l in links), *(a.id for a in atribuicoes)]
    if len({i.lower() for i in todos}) != len(todos):
        p.add("inventario", "há IDs repetidos entre recursos_proprios, shared_private_links e atribuicoes_proprias.")
    if (identidades or principais) and tenant is None:
        p.add("tenant", "é obrigatório quando há identidades_entra ou principais_proprios: sem ele, um 'não encontrado' do "
                        "Microsoft Graph poderia significar que você está no diretório errado.")
    _recusar_guid_em_dois_papeis(p, usos)
    p.levantar("Inventário inválido:", "Corrija o inventário e repita; nenhum comando foi gerado. Os valores não são repetidos nas "
                                       "mensagens de propósito.")
    return Inventario(assinatura=assinatura, tenant=tenant, regiao=regiao or "", grupo=grupo, grupo_gerenciado=gerenciado,
                      principais_proprios=tuple(principais), recursos=tuple(recursos), links=tuple(links),
                      atribuicoes=tuple(atribuicoes), identidades=tuple(identidades), expurgos=tuple(expurgos), sha256=sha256)


def modelo_de_inventario() -> dict[str, Any]:
    """Modelo para preencher. Os marcadores <...> não são valores válidos: o plano recusa o modelo até você preenchê-lo."""
    return {
        "versao": VERSAO_DO_INVENTARIO,
        "assinatura": "<GUID da assinatura do laboratório>",
        "tenant": "<GUID do tenant (obrigatório se houver objetos do Entra ID)>",
        "regiao": "<região, por exemplo a de 'az account list-locations'>",
        "grupo": "<nome do grupo de recursos EXCLUSIVO do laboratório>",
        "grupo_exclusivo": False,
        "grupo_gerenciado": "<grupo gerenciado do Container Apps, se houver; senão apague este campo>",
        "principais_proprios": ["<ID de OBJETO (principalId) de um principal criado pelo laboratório; nunca o clientId>"],
        "recursos_proprios": [{"id": "/subscriptions/<assinatura>/resourceGroups/<grupo>/providers/<namespace>/<tipo>/<nome>",
                               "tipo": "<namespace>/<tipo>"}],
        "shared_private_links": [{"id": "/subscriptions/<assinatura>/resourceGroups/<grupo>/providers/Microsoft.Search/"
                                        "searchServices/<busca>/sharedPrivateLinkResources/<link>"}],
        "atribuicoes_proprias": [{"id": "<escopo>/providers/Microsoft.Authorization/roleAssignments/<GUID>",
                                  "escopo": "/subscriptions/<assinatura>/resourceGroups/<grupo>",
                                  "principal_id": "<ID de OBJETO do principal próprio (o mesmo de principais_proprios)>",
                                  "papel_id": "<GUID da definição do papel>"}],
        "identidades_entra": [{"objeto_id": "<ID de OBJETO do aplicativo (o id)>",
                               "app_id": "<ID do aplicativo (o appId, o client id): outro GUID, diferente do ID de objeto>",
                               "nome": "<nome de exibição, sem espaços>",
                               "principal_id": "<ID de OBJETO do principal de serviço (o id dele, não o appId)>",
                               "chaves": ["<GUID de uma credencial criada>"]}],
        "expurgos": [{"tipo": EXPURGO_CONTA_DE_MODELOS, "nome": "<conta de modelos>", "regiao": "<região>", "grupo": "<grupo exclusivo>"},
                     {"tipo": EXPURGO_COFRE_DE_CHAVES, "nome": "<cofre de chaves>", "regiao": "<região>"}],
    }


# --------------------------------------------------------------------------------------
# Instantâneos e linha de base
# --------------------------------------------------------------------------------------

def _texto_livre(valor: Any, limite: int = 1024) -> bool:
    return isinstance(valor, str) and 0 < len(valor) <= limite and valor.isprintable()


def _lista_do_az(caminho: Path, descricao: str) -> tuple[list[Any], str]:
    dados, sha256 = ler_json(caminho, descricao)
    if isinstance(dados, dict):
        if "nextLink" in dados or "@odata.nextLink" in dados:
            raise ErroLab(f"O arquivo ({descricao}) é uma listagem paginada (tem nextLink): é preciso completar a listagem antes de continuar. "
                          "Use o comando de '--etapa capturar': o Azure CLI percorre todas as páginas por você.")
        raise ErroLab(f"O arquivo ({descricao}) deve ser uma lista JSON exportada por 'az ... list'. Use o comando de '--etapa "
                      "capturar'; o formato bruto da API (com 'value') não é aceito.")
    if not isinstance(dados, list):
        raise ErroLab(f"O arquivo ({descricao}) deve ser uma lista JSON exportada por 'az ... list'.")
    if len(dados) > LIMITE_DE_ITENS_DO_INSTANTANEO:
        raise ErroLab(f"O arquivo ({descricao}) tem itens demais e não foi lido.")
    return dados, sha256


def _da_assinatura(valor: str, assinatura: str) -> bool:
    base = f"/subscriptions/{assinatura}".lower()
    minusculo = valor.lower()
    return minusculo == base or minusculo.startswith(base + "/")


def carregar_instantaneo(grupos: Path, recursos: Path, papeis: Path, assinatura: str, momento: str) -> Instantaneo:
    """Lê e valida os três arquivos de um momento. Qualquer arquivo inválido interrompe com a orientação para exportar de novo."""
    sufixo = f"-{momento}"
    nomes: set[str] = set()
    mapa_recursos: dict[str, str] = {}
    mapa_papeis: dict[str, tuple[str, str, str]] = {}
    hashes: dict[str, str] = {}
    p = _Problemas()

    itens, hashes["grupos"] = _lista_do_az(grupos, f"--grupos{sufixo}")
    for i, item in enumerate(itens):
        rotulo = f"--grupos{sufixo}[{i}]"
        if not (isinstance(item, dict) and _texto_livre(item.get("id")) and _texto_livre(item.get("name"), 90)):
            p.add(rotulo, "cada item precisa ter 'id' e 'name' (use o comando de '--etapa capturar').")
            continue
        identificador = item["id"].lower()
        if not identificador.startswith(f"/subscriptions/{assinatura}/resourcegroups/".lower()) or \
                identificador.rsplit("/", 1)[-1] != item["name"].lower():
            p.add(rotulo, "o item não é um grupo da assinatura do inventário (ou 'id' e 'name' não combinam).")
            continue
        nomes.add(item["name"].lower())

    itens, hashes["recursos"] = _lista_do_az(recursos, f"--recursos{sufixo}")
    for i, item in enumerate(itens):
        rotulo = f"--recursos{sufixo}[{i}]"
        if not (isinstance(item, dict) and _texto_livre(item.get("id")) and _texto_livre(item.get("type"), 256)):
            p.add(rotulo, "cada item precisa ter 'id' e 'type' (use o comando de '--etapa capturar').")
            continue
        if not _da_assinatura(item["id"], assinatura):
            p.add(rotulo, "o item não é da assinatura do inventário.")
            continue
        anterior = mapa_recursos.setdefault(item["id"].lower(), item["type"].lower())
        if anterior != item["type"].lower():
            p.add(rotulo, "o mesmo ID aparece com tipos diferentes.")

    itens, hashes["papeis"] = _lista_do_az(papeis, f"--papeis{sufixo}")
    for i, item in enumerate(itens):
        rotulo = f"--papeis{sufixo}[{i}]"
        campos = ("id", "principalId", "roleDefinitionId", "scope")
        if not (isinstance(item, dict) and all(_texto_livre(item.get(c)) for c in campos)):
            p.add(rotulo, "cada item precisa ter id, principalId, roleDefinitionId e scope (use o comando de '--etapa capturar').")
            continue
        if not (_da_assinatura(item["id"], assinatura) and _da_assinatura(item["scope"], assinatura)):
            p.add(rotulo, "o item não é da assinatura do inventário (um escopo fora dela, como grupo de gerenciamento, não é aceito).")
            continue
        valor = (item["principalId"].lower(), item["roleDefinitionId"].lower(), item["scope"].lower())
        if mapa_papeis.setdefault(item["id"].lower(), valor) != valor:
            p.add(rotulo, "o mesmo ID aparece com valores diferentes.")
    p.levantar("Instantâneo inválido:", "Refaça a exportação com os comandos de '--etapa capturar' (um arquivo por listagem, sem "
                                        "editar à mão) e repita.")
    return Instantaneo(grupos=frozenset(nomes), recursos=mapa_recursos, atribuicoes=mapa_papeis, sha256=hashes)


def validar_linha_de_base(inv: Inventario, base: Instantaneo) -> None:
    """Recusa o plano se o inventário tocar algo que já existia antes do laboratório. Mensagens só com contagens."""
    p = _Problemas()
    if inv.grupo.lower() in base.grupos:
        p.add("grupo", "o grupo exclusivo já existia na linha de base: ele não é exclusivo do laboratório (ou a linha de base foi "
                       "capturada depois de criá-lo). Capture a linha de base ANTES de criar o grupo.")
    if inv.grupo_gerenciado and inv.grupo_gerenciado.lower() in base.grupos:
        p.add("grupo_gerenciado", "o grupo gerenciado já existia na linha de base: ele não pertence ao ambiente do laboratório.")
    dentro = sum(1 for i in base.recursos if i.startswith(inv.prefixos_proprios))
    if dentro:
        p.add("--recursos-antes", f"{dentro} recurso(s) da linha de base estão dentro do grupo exclusivo (ou do gerenciado): o grupo "
                                  "não é exclusivo ou a linha de base foi capturada tarde demais.")
    dentro = sum(1 for _, _, escopo in base.atribuicoes.values()
                 if (escopo + "/").startswith(inv.prefixos_proprios))
    if dentro:
        p.add("--papeis-antes", f"{dentro} atribuição(ões) da linha de base estão no escopo do grupo exclusivo (ou do gerenciado).")
    ids = inv.ids
    repetidos = sum(1 for i in base.recursos if i in ids) + sum(1 for i in base.atribuicoes if i in ids)
    if repetidos:
        p.add("inventario", f"{repetidos} ID(s) do inventário já constam na linha de base: nunca se planeja apagar o que já existia "
                            "antes do laboratório. Remova-os do inventário.")
    proprios = set(inv.principais_proprios)
    com_papel = sum(1 for principal, _, _ in base.atribuicoes.values() if principal in proprios)
    if com_papel:
        p.add("principais_proprios", f"{com_papel} atribuição(ões) da linha de base pertencem a principais listados como próprios: "
                                     "eles já existiam antes do laboratório e não podem ser tratados como criados por ele.")
    p.levantar("A linha de base não combina com o inventário:", "Corrija o inventário (ou capture a linha de base certa) e repita.")


# --------------------------------------------------------------------------------------
# Texto dos comandos (PowerShell 7)
# --------------------------------------------------------------------------------------

BASE_DO_GRAPH = "https://graph.microsoft.com/v1.0/"


def _aspas(valor: str) -> str:
    """Coloca o valor entre aspas simples. Os valores já foram validados; isto é a última barreira, não a primeira."""
    if not _SEGURO_NO_POWERSHELL.fullmatch(valor):
        raise ErroLab("Um valor fora do conjunto seguro chegou à montagem de um comando; nada foi impresso.", CODIGO_INESPERADO)
    return f"'{valor}'"


def _preencher(modelo: str, **valores: str) -> str:
    texto = modelo
    for chave, valor in valores.items():
        texto = texto.replace(f"@@{chave}@@", valor)
    if "@@" in texto:
        raise ErroLab("Um modelo de comando ficou com campo sem valor; nada foi impresso.", CODIGO_INESPERADO)
    return texto


_AVISO_DA_VERSAO = "Este bloco exige o PowerShell 7 (pwsh): abra o pwsh, faça az login, cole a PREPARAÇÃO e repita. Nada foi executado."
_AVISO_DA_PREPARACAO = "Cole antes a PREPARAÇÃO nesta mesma janela do PowerShell 7 (e use o mesmo inventário). Nada foi executado."
_AVISO_DA_VERSAO_NA_PREPARACAO = ("A PREPARAÇÃO exige o PowerShell 7 (pwsh): abra o pwsh, faça az login e cole-a de novo. "
                                  "Nada foi executado.")
_AVISO_DA_VERSAO_NA_CAPTURA = "Este bloco exige o PowerShell 7 (pwsh): abra o pwsh, faça az login e repita. Nada foi gravado."

# Todo bloco impresso é UM comando composto (as chaves de fechamento ficam na mesma linha do else/elseif, como o console exige):
# o console só o executa depois de recebê-lo inteiro, então nada do corpo roda fora do PowerShell 7 nem sem a PREPARAÇÃO.
_PROTEGIDO = """\
if ($PSVersionTable.PSVersion.Major -lt 7) {
    Write-Warning '@@AVISO_DA_VERSAO@@'@@RESPOSTA@@
} elseif ($script:EncerramentoPronto -ne @@MARCA@@) {
    Write-Warning '@@AVISO_DA_PREPARACAO@@'@@RESPOSTA@@
} else {
@@CORPO@@
}"""

_PREPARACAO = """\
$script:EncerramentoPronto = $null
if ($PSVersionTable.PSVersion.Major -lt 7) {
    Write-Warning '@@AVISO_DA_VERSAO@@'
} else {
@@CORPO@@
    $script:EncerramentoPronto = @@MARCA@@
    'Preparação concluída nesta janela: a conta ativa confere com o inventário.'
}"""

_CAPTURA = """\
if ($PSVersionTable.PSVersion.Major -lt 7) {
    Write-Warning '@@AVISO_DA_VERSAO@@'
} else {
@@CORPO@@
}"""

_VERIFICAR_POR_LISTAGEM = """\
$lista = @@LISTAGEM@@
if ($LASTEXITCODE -ne 0) { Write-Warning 'A listagem falhou: isto NÃO prova ausência.'; 'indeterminado' } elseif ($lista | Where-Object { $_ -ieq @@ALVO@@ }) { 'presente' } else { 'ausente' }"""

_VERIFICAR_GRUPO = """\
$existe = az group exists --name @@GRUPO@@ --subscription @@ASSINATURA@@
if ($LASTEXITCODE -ne 0) { Write-Warning 'A consulta falhou: isto NÃO prova ausência.'; 'indeterminado' } elseif ($existe -eq 'false') { 'ausente' } else { 'presente' }"""

_CONTA_ATIVA = """\
$conta = az account show --output json | ConvertFrom-Json
if (-not $conta -or $conta.id -ne @@ASSINATURA@@@@CONDICAO_TENANT@@) {
    throw 'A conta ativa do Azure CLI não é a do inventário. Use az account set --subscription com a assinatura do inventário (e az login --tenant com o tenant do inventário, se preciso) e repita.'
}"""

_GRAPH = """\
$script:TokenGraph = az account get-access-token --resource-type ms-graph --tenant @@TENANT@@ --query accessToken --output tsv
if ($LASTEXITCODE -ne 0 -or -not $script:TokenGraph) { throw 'Não foi possível obter o token do Microsoft Graph para o tenant do inventário. O token nunca é exibido.' }
function Get-EstadoGraph {
    param([Parameter(Mandatory)][string]$Caminho)
    try {
        $resposta = Invoke-WebRequest -Method Get -Uri ('@@BASE@@' + $Caminho) -Headers @{ Authorization = ('Bearer ' + $script:TokenGraph) } -SkipHttpErrorCheck -MaximumRedirection 0 -TimeoutSec 60
        switch ([int]$resposta.StatusCode) { 200 { 'presente' } 404 { 'ausente' } default { 'indeterminado' } }
    } catch {
        'indeterminado'
    }
}"""

_GUARDADO = """\
@@LIMPAR@@
@@LEITURA@@
if (@@CONDICAO@@) {
    @@COMANDO@@
} else {
    Write-Warning '@@AVISO@@'
}"""


def _verificar_por_listagem(listagem: str, alvo: str) -> str:
    return _preencher(_VERIFICAR_POR_LISTAGEM, LISTAGEM=listagem, ALVO=_aspas(alvo))


def _guardado(variaveis: Sequence[str], leitura: str, condicao: str, comando: str, aviso: str) -> str:
    """Lê o objeto, confere-o com o inventário e só então executa o comando. As variáveis são zeradas antes da leitura: se ela
    falhar no meio (por exemplo, um JSON inválido), um valor deixado por um bloco anterior não pode ser reaproveitado."""
    limpar = "; ".join(f"${nome} = $null" for nome in variaveis)
    return _preencher(_GUARDADO, LIMPAR=limpar, LEITURA=leitura, CONDICAO=condicao, COMANDO=comando, AVISO=aviso)


def _verificar_grafico(caminho: str) -> str:
    return f"Get-EstadoGraph {_aspas(caminho)}"


def _bloco_da_conta(inv: Inventario) -> str:
    condicao = f" -or $conta.tenantId -ne {_aspas(inv.tenant)}" if inv.tenant else ""
    return _preencher(_CONTA_ATIVA, ASSINATURA=_aspas(inv.assinatura), CONDICAO_TENANT=condicao)


def _bloco_do_graph(inv: Inventario) -> str:
    return _preencher(_GRAPH, TENANT=_aspas(inv.tenant or ""), BASE=BASE_DO_GRAPH)


def _consulta_de_ids() -> str:
    return "--query '[].id' --output tsv"


def _marca_da_preparacao(inv: Inventario) -> str:
    """O que a PREPARAÇÃO grava na sessão: amarra os blocos ao inventário (assinatura e grupo) para o qual ela foi executada."""
    return _aspas(f"{inv.assinatura}/{inv.grupo}")


def _proteger(corpo: str, inv: Inventario, resposta_de_recusa: str = "") -> str:
    """Envolve o corpo em UM comando composto que só o executa no PowerShell 7 e depois da PREPARAÇÃO desta janela.

    Um `throw` solto não serviria: colado linha a linha no Windows PowerShell 5.1, ele não interromperia as linhas seguintes.
    `resposta_de_recusa` é o que um bloco de verificação responde ao se recusar a rodar ('indeterminado', nunca 'ausente').
    """
    resposta = f"; {_aspas(resposta_de_recusa)}" if resposta_de_recusa else ""
    return _preencher(_PROTEGIDO, AVISO_DA_VERSAO=_AVISO_DA_VERSAO, AVISO_DA_PREPARACAO=_AVISO_DA_PREPARACAO, RESPOSTA=resposta,
                      MARCA=_marca_da_preparacao(inv), CORPO=_indentar(corpo, 4))


def _preparacao(inv: Inventario) -> str:
    partes = [_bloco_da_conta(inv)] + ([_bloco_do_graph(inv)] if inv.identidades else [])
    return _preencher(_PREPARACAO, AVISO_DA_VERSAO=_AVISO_DA_VERSAO_NA_PREPARACAO, MARCA=_marca_da_preparacao(inv),
                      CORPO=_indentar("\n".join(partes), 4))


# --------------------------------------------------------------------------------------
# Plano
# --------------------------------------------------------------------------------------

def _precondicoes(linha_de_base: bool) -> tuple[str, ...]:
    base = ("conferida contra os instantâneos informados: nenhum alvo do inventário constava neles." if linha_de_base else
            "NÃO conferida. Este plano é só uma PRÉVIA: não execute nada antes de repetir o comando com os três arquivos da "
            "linha de base (capturada ANTES de criar o grupo exclusivo).")
    return (
        "Autorização: quem responde pela assinatura autorizou, por escrito, o encerramento deste grupo e dos objetos do Microsoft "
        "Entra ID listados. Entrar no Azure (login) não comprova autorização.",
        "Alvos: cada ID deste plano veio do SEU inventário. Revise todos antes de executar; o que não está no inventário não é "
        "tocado e não deve ser apagado por improviso. Confira também que os principais (principais_proprios e principal_id) e o "
        "objeto_id são IDs de OBJETO, nunca o clientId nem o appId: com o ID errado o Microsoft Graph responde 404 e a "
        "\"ausência\" ficaria vazia.",
        f"Linha de base: {base}",
        "Custo e efeito: os recursos continuam sendo cobrados até serem excluídos, e quase todos os passos são irreversíveis (o "
        "efeito de cada um está indicado). Registre o que foi feito, quando e por quem.",
        "Bloqueios: nenhum bloqueio administrativo será removido por este plano. Se um passo falhar por causa de um bloqueio (por "
        "exemplo LockedSPLResourceFound), pare e consulte quem administra a assinatura; não remova o bloqueio nem recrie "
        "dependências para contornar.",
        "Sem curingas: nenhum passo usa curinga, --all, filtro por nome parcial ou ID deduzido; todo alvo vem literalmente do "
        "inventário. Não adapte os comandos para apagar tudo o que combina com um padrão.",
        "Grupo gerenciado do Container Apps: ele pertence à plataforma e some com o ambiente. Não edite nem exclua seus "
        "componentes manualmente.",
        "Papéis herdados: atribuições herdadas ou de outros recursos NÃO são revogadas. Cada atribuição própria é removida pelo "
        "ID exato, depois de conferir escopo, principal e papel contra o inventário.",
        "Execução: rode um passo por vez, na ordem, no PowerShell 7 (com az login feito), e leia o resultado da verificação antes "
        "de seguir. Cole a PREPARAÇÃO primeiro, na MESMA janela dos passos: cada bloco confere a versão do PowerShell e se a "
        "PREPARAÇÃO foi concluída nesta janela, e se recusa a rodar (sem executar nada) quando não foi. Um comando de espera (como "
        "az ... wait) ou um código de saída 0 NÃO prova ausência: só a verificação de cada passo prova.",
    )


def montar_plano(inv: Inventario, linha_de_base_conferida: bool) -> Plano:  # noqa: C901 - um construtor por tipo de passo
    passos: list[Passo] = []
    assinatura, grupo = _aspas(inv.assinatura), _aspas(inv.grupo)

    def adicionar(tipo: str, titulo: str, comando: str, verificacao: str, nota: str = "") -> None:
        fase, efeito = TIPOS_DE_PASSO[tipo]
        passos.append(Passo(len(passos) + 1, fase, tipo, titulo, efeito, _proteger(comando, inv),
                            _proteger(verificacao, inv, "indeterminado"), nota))

    def do_tipo(tipo: str) -> list[Recurso]:
        return [r for r in inv.recursos if r.tipo.lower() == tipo]

    def listagem_do_grupo(comando: str) -> str:
        return f"{comando} --resource-group {grupo} --subscription {assinatura} {_consulta_de_ids()}"

    # 1. Consumidores
    for rotulo, tipo, passo, apagar, listar in (
            ("aplicativo Container Apps", TIPO_APLICATIVO, PASSO_APLICATIVO, "az containerapp delete", "az containerapp list"),
            ("job do Container Apps", TIPO_JOB, PASSO_JOB, "az containerapp job delete", "az containerapp job list")):
        itens = do_tipo(tipo)
        for numero, recurso in enumerate(itens, 1):
            adicionar(passo, f"Excluir o {rotulo} ({numero} de {len(itens)})",
                      f"{apagar} --ids {_aspas(recurso.id)} --yes",
                      _verificar_por_listagem(listagem_do_grupo(listar), recurso.id),
                      "Retire os consumidores antes de qualquer dependência deles." if numero == 1 else "")

    # 2. Shared private links
    for numero, link in enumerate(inv.links, 1):
        adicionar(PASSO_LINK, f"Excluir o shared private link ({numero} de {len(inv.links)})",
                  f"az search shared-private-link-resource delete --resource-group {grupo} --service-name {_aspas(link.servico)} "
                  f"--name {_aspas(link.nome)} --subscription {assinatura} --yes",
                  _verificar_por_listagem(f"az search shared-private-link-resource list --resource-group {grupo} --service-name "
                                          f"{_aspas(link.servico)} --subscription {assinatura} {_consulta_de_ids()}", link.id),
                  "Faça isto ANTES de excluir o serviço de busca e os destinos dos links: um destino já ausente pode bloquear a "
                  "exclusão da busca (LockedSPLResourceFound). A exclusão é assíncrona: repita a verificação até 'ausente'. Ao "
                  "final, a listagem do serviço deve estar vazia; se ainda mostrar um link que não é do inventário, NÃO o apague: "
                  "confirme o proprietário e atualize o inventário.")

    # 3. Entra ID
    for numero, identidade in enumerate(inv.identidades, 1):
        rotulo = f"Aplicativo do Entra ID {numero} de {len(inv.identidades)}"
        objeto, app, nome = identidade.objeto_id, identidade.app_id, identidade.nome
        for ordem, chave in enumerate(identidade.chaves, 1):
            adicionar(PASSO_CREDENCIAL, f"{rotulo}: revogar a credencial {ordem} de {len(identidade.chaves)}",
                      f"az ad app credential delete --id {_aspas(objeto)} --key-id {_aspas(chave)}",
                      _verificar_por_listagem(f"az ad app credential list --id {_aspas(objeto)} --query '[].keyId' --output tsv", chave),
                      "Revogue o segredo antes de remover o aplicativo.")
        if identidade.principal_id:
            principal = identidade.principal_id
            adicionar(PASSO_PRINCIPAL, f"{rotulo}: remover o principal de serviço",
                      _guardado(("sp",),
                                f"$sp = az ad sp show --id {_aspas(principal)} --query '{{id:id,appId:appId}}' --output json | ConvertFrom-Json",
                                f"$LASTEXITCODE -eq 0 -and $sp -and $sp.id -eq {_aspas(principal)} -and $sp.appId -eq {_aspas(app)}",
                                f"az ad sp delete --id {_aspas(principal)}",
                                "O principal de serviço não confere com o inventário (ID de objeto e ID do aplicativo) ou já não existe; nada foi apagado."),
                      _verificar_grafico(f"servicePrincipals/{principal}"),
                      "O bloco só apaga se o ID de objeto e o appId lidos conferirem com o inventário (o az resolve --id primeiro pelo "
                      "appId). A remoção é recuperável em directory/deletedItems por até 30 dias, até o expurgo do passo seguinte.")
            adicionar(PASSO_EXPURGO_PRINCIPAL, f"{rotulo}: expurgar o principal de serviço excluído",
                      _expurgo_do_graph(principal, app), _verificar_grafico(f"directory/deletedItems/{principal}"),
                      "O expurgo é permanente: o item não pode mais ser restaurado.")
        adicionar(PASSO_APLICATIVO_ENTRA, f"{rotulo}: remover o aplicativo",
                  _guardado(("app",),
                            f"$app = az ad app show --id {_aspas(objeto)} --query '{{id:id,appId:appId,nome:displayName}}' --output json | ConvertFrom-Json",
                            f"$LASTEXITCODE -eq 0 -and $app -and $app.id -eq {_aspas(objeto)} -and $app.appId -eq {_aspas(app)} "
                            f"-and $app.nome -eq {_aspas(nome)}",
                            f"az ad app delete --id {_aspas(objeto)}",
                            "O aplicativo não confere com o inventário (ID de objeto, ID do aplicativo e nome) ou já não existe; nada foi apagado."),
                  _verificar_grafico(f"applications/{objeto}"),
                  "O bloco só apaga se o ID de objeto, o appId e o nome lidos conferirem com o inventário (o az resolve --id primeiro "
                  "pelo appId). A remoção é recuperável em directory/deletedItems por até 30 dias, até o expurgo do passo seguinte.")
        adicionar(PASSO_EXPURGO_APLICATIVO, f"{rotulo}: expurgar o aplicativo excluído",
                  _expurgo_do_graph(objeto, app), _verificar_grafico(f"directory/deletedItems/{objeto}"),
                  "O expurgo é permanente: o item não pode mais ser restaurado.")

    # 4. Atribuições de papel
    for numero, atribuicao in enumerate(inv.atribuicoes, 1):
        adicionar(PASSO_ATRIBUICAO, f"Revogar a atribuição de papel ({numero} de {len(inv.atribuicoes)})",
                  _revogacao(atribuicao, assinatura),
                  _verificar_por_listagem(f"az role assignment list --scope {_aspas(atribuicao.escopo)} --subscription {assinatura} "
                                          f"--fill-principal-name false --fill-role-definition-name false {_consulta_de_ids()}",
                                          atribuicao.id),
                  "Só este ID exato é revogado, e só se a listagem trouxer UMA atribuição com esse ID e ela conferir com o "
                  "inventário. Papéis herdados, de outros recursos ou de outros principais não são tocados. O principal do inventário "
                  "é o ID de OBJETO (principalId), nunca o clientId: com o ID errado nada confere e nada é revogado.")

    # 5. Workspace
    workspaces = do_tipo(TIPO_WORKSPACE)
    for numero, recurso in enumerate(workspaces, 1):
        adicionar(PASSO_WORKSPACE, f"Excluir o workspace do Log Analytics ({numero} de {len(workspaces)})",
                  f"az monitor log-analytics workspace delete --ids {_aspas(recurso.id)} --force true --yes",
                  _verificar_por_listagem(listagem_do_grupo("az monitor log-analytics workspace list"), recurso.id),
                  "--force exclui de forma permanente e libera o nome; sem ele o nome ficaria reservado por 14 dias.")

    # 6. Ambientes
    ambientes = do_tipo(TIPO_AMBIENTE)
    for numero, recurso in enumerate(ambientes, 1):
        adicionar(PASSO_AMBIENTE, f"Excluir o ambiente do Container Apps ({numero} de {len(ambientes)})",
                  f"az containerapp env delete --ids {_aspas(recurso.id)} --yes --no-wait",
                  _verificar_por_listagem(listagem_do_grupo("az containerapp env list"), recurso.id),
                  "A exclusão é assíncrona e pode levar vários minutos: repita a verificação até 'ausente'. O grupo gerenciado "
                  "pela plataforma some com o ambiente; não o edite nem exclua seus componentes.")

    # 7. Grupo exclusivo
    outros = Counter(r.tipo for r in inv.recursos if r.tipo.lower() not in TIPOS_COM_PASSO_PROPRIO)
    esperados = "\n".join(f"    {_aspas(r.id)}" for r in inv.recursos)
    leitura = (f"$esperados = @(\n{esperados}\n)\n" if esperados else "$esperados = @()\n") + \
        f"$presentes = az resource list --resource-group {grupo} --subscription {assinatura} {_consulta_de_ids()}"
    bloco = (
        f"{leitura}\n"
        "if ($LASTEXITCODE -ne 0) {\n"
        "    Write-Warning 'A listagem do grupo falhou; nada foi apagado.'\n"
        "} else {\n"
        "    $fora = @($presentes | Where-Object { $_ -and ($_ -notin $esperados) })\n"
        "    if ($fora.Count -gt 0) {\n"
        "        Write-Warning ('O grupo contém ' + $fora.Count + ' recurso(s) fora do inventário; nada foi apagado. Se forem do laboratório, "
        "acrescente-os ao inventário; se não forem, o grupo NÃO é exclusivo.')\n"
        "        $fora | ForEach-Object { '  fora do inventário: ' + $_ }\n"
        "    } else {\n"
        f"        az group delete --name {grupo} --subscription {assinatura} --yes\n"
        "    }\n"
        "}")
    adicionar(PASSO_GRUPO, "Excluir o grupo exclusivo do laboratório", bloco, _preencher(_VERIFICAR_GRUPO, GRUPO=grupo, ASSINATURA=assinatura),
              "Antes de excluir, o bloco confere que o grupo só contém recursos do inventário. A exclusão remove também os recursos "
              "que não têm passo próprio"
              + (": " + ", ".join(f"{quantidade} de {tipo}" for tipo, quantidade in sorted(outros.items())) if outros else " (nenhum no inventário)")
              + ". A exclusão é síncrona e pode levar vários minutos: não a interrompa e, se interromper, confira o estado antes de repetir. "
                "Se falhar (por exemplo LockedSPLResourceFound), pare, volte às fases 1 e 2 e confira por listagem antes de repetir; "
                "um comando de espera com código 0 NÃO prova que o grupo sumiu.")

    # 8. Expurgos
    for numero, expurgo in enumerate(inv.expurgos, 1):
        if expurgo.tipo == EXPURGO_CONTA_DE_MODELOS:
            adicionar(PASSO_EXPURGO_MODELOS, f"Expurgar a conta de modelos excluída ({numero} de {len(inv.expurgos)})",
                      f"az cognitiveservices account purge --location {_aspas(expurgo.regiao)} --resource-group {grupo} "
                      f"--name {_aspas(expurgo.nome)} --subscription {assinatura}",
                      _verificar_por_listagem(f"az cognitiveservices account list-deleted --subscription {assinatura} "
                                              "--query '[].name' --output tsv", expurgo.nome),
                      "A conta fica recuperável depois que o grupo é excluído; o expurgo libera o nome da conta. É permanente.")
        else:
            prefixo = _aspas(inv.prefixo + "/")
            adicionar(PASSO_EXPURGO_COFRE, f"Expurgar o cofre de chaves excluído ({numero} de {len(inv.expurgos)})",
                      _guardado(("cofre",),
                                f"$cofre = az keyvault show-deleted --name {_aspas(expurgo.nome)} --location {_aspas(expurgo.regiao)} "
                                f"--subscription {assinatura} --query 'properties.vaultId' --output tsv",
                                f"$LASTEXITCODE -eq 0 -and $cofre -is [string] -and "
                                f"$cofre.StartsWith({prefixo}, [System.StringComparison]::OrdinalIgnoreCase)",
                                f"az keyvault purge --name {_aspas(expurgo.nome)} --location {_aspas(expurgo.regiao)} --subscription {assinatura}",
                                "O cofre excluído não é do grupo exclusivo do inventário ou já não existe; nada foi expurgado."),
                      _verificar_por_listagem(f"az keyvault list-deleted --subscription {assinatura} --query '[].name' --output tsv",
                                              expurgo.nome),
                      "O expurgo é permanente. Se o cofre tem proteção contra expurgo, o comando falha e ele permanece recuperável "
                      "até o fim da retenção: não tente contornar.")

    preparacao = _preparacao(inv)
    fases_presentes = {p.fase for p in passos}
    return Plano(precondicoes=_precondicoes(linha_de_base_conferida), preparacao=preparacao, passos=tuple(passos),
                 fechamento=_fechamento(inv), removidos_com_o_grupo=dict(sorted(outros.items())),
                 fases_omitidas=tuple(f for f in FASES if f not in fases_presentes), linha_de_base_conferida=linha_de_base_conferida,
                 inventario_sha256=inv.sha256)


def _revogacao(atribuicao: Atribuicao, assinatura: str) -> str:
    """Revoga UMA atribuição pelo ID exato, depois de conferir que a listagem a traz uma única vez e que ela bate com o inventário.

    Lê e filtra em duas etapas: no Windows PowerShell 5.1, `ConvertFrom-Json | Where-Object` entrega a lista inteira ao filtro como
    um único objeto, e principal, escopo e papel passariam se QUALQUER item da lista coincidisse.
    """
    leitura = (f"$todas = az role assignment list --scope {_aspas(atribuicao.escopo)} --subscription {assinatura} "
               "--fill-principal-name false --fill-role-definition-name false "
               "--query '[].{id:id,principalId:principalId,roleDefinitionId:roleDefinitionId,scope:scope}' --output json "
               "| ConvertFrom-Json\n"
               f"$achadas = @(@($todas) | Where-Object {{ $_ -and $_.id -ieq {_aspas(atribuicao.id)} }})")
    condicao = (f"$LASTEXITCODE -eq 0 -and $achadas.Count -eq 1 -and $achadas[0].principalId -ieq {_aspas(atribuicao.principal_id)} "
                f"-and $achadas[0].scope -ieq {_aspas(atribuicao.escopo)} -and ([string]$achadas[0].roleDefinitionId).EndsWith("
                f"{_aspas('/' + atribuicao.papel_id)}, [System.StringComparison]::OrdinalIgnoreCase)")
    return _guardado(("todas", "achadas"), leitura, condicao, f"az role assignment delete --ids {_aspas(atribuicao.id)}",
                     "A atribuição não confere com o inventário (uma única atribuição com esse ID, o principal, o escopo e o papel) "
                     "ou já não existe; nada foi revogado.")


def _expurgo_do_graph(objeto: str, app: str) -> str:
    url = _aspas(BASE_DO_GRAPH + "directory/deletedItems/" + objeto)
    return _guardado(("item",),
                     f"$item = az rest --method get --url {url} --query '{{id:id,appId:appId}}' --output json | ConvertFrom-Json",
                     f"$LASTEXITCODE -eq 0 -and $item -and $item.id -eq {_aspas(objeto)} -and $item.appId -eq {_aspas(app)}",
                     f"az rest --method delete --url {url}",
                     "O item excluído não confere com o inventário (ID de objeto e ID do aplicativo) ou já foi expurgado; nada foi apagado.")


def _fechamento(inv: Inventario) -> tuple[ItemDeFechamento, ...]:
    assinatura, grupo = _aspas(inv.assinatura), _aspas(inv.grupo)
    python = r".\.venv\Scripts\python.exe scripts\planejar_encerramento.py"
    itens = [
        ItemDeFechamento("Capture o estado final (somente leitura): o comando abaixo IMPRIME o bloco PowerShell que você cola; guarde os "
                         "arquivos em local privado.",
                         f"{python} --etapa capturar --momento depois --assinatura {assinatura} --grupo {grupo} --pasta '<pasta>' "
                         "--inventario '<inventario.json>'"),
        ItemDeFechamento("Rode a conferência: ela retorna 0 só se TODOS os critérios forem atendidos (3 se algum for reprovado ou "
                         "ficar pendente).",
                         f"{python} --etapa conferir --inventario '<inventario.json>' --grupos-antes '<grupos-antes.json>' "
                         "--recursos-antes '<recursos-antes.json>' --papeis-antes '<papeis-antes.json>' --grupos-depois "
                         "'<grupos-depois.json>' --recursos-depois '<recursos-depois.json>' --papeis-depois '<papeis-depois.json>' "
                         "--presenca '<presenca-depois.json>' --relatorio '<relatorio-novo.json>'"),
        ItemDeFechamento("Custos: consulte o Cost Management (portal ou API) para o período e os grupos do laboratório. Atraso de "
                         "cobrança é comum: resposta vazia, sem linhas ou com erro de limite (429) NÃO significa custo zero nem "
                         "cumprimento do teto. Registre 'indisponível' em vez de zero."),
        ItemDeFechamento("Se a conferência terminar com código 3 (reprovado ou pendente), o encerramento NÃO está concluído: corrija "
                         "o que foi apontado e repita a captura e a conferência."),
    ]
    if inv.grupo_gerenciado:
        itens.append(ItemDeFechamento("Somente leitura: confirme que o grupo gerenciado também sumiu (esperado: ausente).",
                                      _proteger(_preencher(_VERIFICAR_GRUPO, GRUPO=_aspas(inv.grupo_gerenciado), ASSINATURA=assinatura),
                                                inv, "indeterminado")))
    return tuple(itens)


def _indentar(bloco: str, espacos: int = 8) -> str:
    return "\n".join((" " * espacos + linha) if linha else linha for linha in bloco.splitlines())


def plano_em_texto(plano: Plano) -> str:
    """O plano para ler e executar por conta própria. Contém IDs do seu ambiente: é privado."""
    linhas = [
        "PLANO DE ENCERRAMENTO DO LABORATÓRIO (somente texto: esta ferramenta não executa nada nem acessa o Azure)",
        f"Passos: {len(plano.passos)} ({sum(1 for p in plano.passos if p.efeito == IRREVERSIVEL)} irreversíveis, "
        f"{sum(1 for p in plano.passos if p.efeito == REVERSIVEL)} reversíveis)",
        "Linha de base: " + ("conferida" if plano.linha_de_base_conferida else "NÃO CONFERIDA: PRÉVIA, NÃO EXECUTE"),
    ]
    if plano.fases_omitidas:
        linhas.append("Fases sem itens no inventário (omitidas): " + ", ".join(str(f) for f in plano.fases_omitidas))
    linhas += ["", "ANTES DE COMEÇAR (confirme cada item)"]
    linhas += [f"  {numero}. {texto}" for numero, texto in enumerate(plano.precondicoes, 1)]
    linhas += ["", "PREPARAÇÃO (cole PRIMEIRO, na mesma janela do PowerShell 7 em que você fez az login e em que vai colar os passos; só "
                   "leitura, nada é apagado)",
               _indentar(plano.preparacao, 4)]
    fase_atual = 0
    for passo in plano.passos:
        if passo.fase != fase_atual:
            fase_atual = passo.fase
            linhas += ["", f"FASE {fase_atual} de {len(FASES)}: {FASES[fase_atual]}"]
        linhas += ["", f"  Passo {passo.numero} de {len(plano.passos)}: {passo.titulo} [{ROTULO_DO_EFEITO[passo.efeito]}]",
                   "    Executar (cole o bloco inteiro; ele se recusa a rodar sem o PowerShell 7 e sem a PREPARAÇÃO desta janela):",
                   _indentar(passo.comando),
                   "    Verificar a ausência (esperado: ausente; 'presente' é falha e 'indeterminado' NÃO prova nada):",
                   _indentar(passo.verificacao)]
        if passo.nota:
            linhas.append(f"    Observação: {passo.nota}")
    linhas += ["", "FECHAMENTO (obrigatório)"]
    for numero, item in enumerate(plano.fechamento, 1):
        linhas.append(f"  {numero}. {item.texto}")
        if item.comando:
            linhas.append(_indentar(item.comando, 6))
    return "\n".join(linhas)


def plano_em_dict(plano: Plano) -> dict[str, Any]:
    return {
        "versao_plano": 1,
        "somente_texto": True,
        "linha_de_base": "conferida" if plano.linha_de_base_conferida else "nao_conferida",
        "precondicoes": list(plano.precondicoes),
        "preparacao": plano.preparacao,
        "fases_omitidas": list(plano.fases_omitidas),
        "passos": [{"numero": p.numero, "fase": p.fase, "tipo": p.tipo, "titulo": p.titulo, "efeito": p.efeito,
                    "comando": p.comando, "verificacao": p.verificacao, "nota": p.nota} for p in plano.passos],
        "removidos_com_o_grupo": dict(plano.removidos_com_o_grupo),
        "fechamento": [{"texto": i.texto, "comando": i.comando} for i in plano.fechamento],
    }


def relatorio_do_plano(plano: Plano) -> dict[str, Any]:
    """Relatório sanitizado: só contagens e vocabulário fechado, sem IDs, nomes nem comandos."""
    por_tipo = Counter(p.tipo for p in plano.passos)
    por_efeito = Counter(p.efeito for p in plano.passos)
    return {
        "versao_relatorio": VERSAO_DO_RELATORIO,
        "tipo": "plano-de-encerramento",
        "linha_de_base": "conferida" if plano.linha_de_base_conferida else "nao_conferida",
        "total_de_passos": len(plano.passos),
        "passos_por_tipo": {tipo: por_tipo[tipo] for tipo in TIPOS_DE_PASSO if por_tipo[tipo]},
        "passos_por_efeito": {efeito: por_efeito[efeito] for efeito in (REVERSIVEL, IRREVERSIVEL)},
        "recursos_removidos_com_o_grupo": sum(plano.removidos_com_o_grupo.values()),
        "fases_omitidas": list(plano.fases_omitidas),
        "entradas_sha256": {"inventario": plano.inventario_sha256},
        "limite": "Este relatório descreve um plano em texto. Nada foi executado nem conferido no Azure.",
    }


# --------------------------------------------------------------------------------------
# Captura (comandos que exportam os instantâneos)
# --------------------------------------------------------------------------------------

def validar_pasta(valor: str) -> str:
    if valor != valor.strip() or not _PASTA.fullmatch(valor):
        raise ErroLab("A pasta deve ter até 240 caracteres e usar só letras, números, espaços, '.', '_', '-', '(', ')', '~', ':', "
                      "'\\' e '/'. Escolha uma pasta sem aspas nem outros caracteres especiais.")
    return valor


def eh_guid(valor: str) -> bool:
    return bool(_GUID.fullmatch(valor))


def eh_nome_de_grupo(valor: str) -> bool:
    return bool(_NOME_DO_GRUPO.fullmatch(valor)) and not valor.endswith(".")


def _aspas_de_caminho(valor: str) -> str:
    return "'" + validar_pasta(valor) + "'"


def chave_de_presenca(tipo: str, valor: str) -> str:
    """Identificador lógico estável e sem IDs: o tipo e 8 caracteres do hash do valor."""
    return f"{tipo}-{hashlib.sha256(valor.lower().encode('utf-8')).hexdigest()[:8]}"


def itens_de_presenca(inv: Inventario) -> tuple[ItemDePresenca, ...]:
    itens: list[ItemDePresenca] = []
    for identidade in inv.identidades:
        itens.append(ItemDePresenca(chave_de_presenca("aplicativo", identidade.objeto_id), ENTRA_APLICATIVOS, "graph",
                                    f"applications/{identidade.objeto_id}"))
    for principal in inv.principais_proprios:
        itens.append(ItemDePresenca(chave_de_presenca("principal", principal), ENTRA_PRINCIPAIS, "graph", f"servicePrincipals/{principal}"))
    for identidade in inv.identidades:
        itens.append(ItemDePresenca(chave_de_presenca("aplicativo-excluido", identidade.objeto_id), ENTRA_EXCLUIDOS, "graph",
                                    f"directory/deletedItems/{identidade.objeto_id}"))
        if identidade.principal_id:
            itens.append(ItemDePresenca(chave_de_presenca("principal-excluido", identidade.principal_id), ENTRA_EXCLUIDOS, "graph",
                                        f"directory/deletedItems/{identidade.principal_id}"))
    for expurgo in inv.expurgos:
        if expurgo.tipo == EXPURGO_CONTA_DE_MODELOS:
            itens.append(ItemDePresenca(chave_de_presenca("conta-de-modelos", f"{expurgo.regiao}|{expurgo.grupo}|{expurgo.nome}"),
                                        EXPURGO_MODELOS, EXPURGO_CONTA_DE_MODELOS, expurgo.nome))
        else:
            itens.append(ItemDePresenca(chave_de_presenca("cofre-de-chaves", f"{expurgo.regiao}|{expurgo.nome}"),
                                        EXPURGO_COFRE, EXPURGO_COFRE_DE_CHAVES, expurgo.nome))
    chaves = [i.chave for i in itens]
    if len(set(chaves)) != len(chaves):
        raise ErroLab("Dois itens do inventário geraram o mesmo identificador lógico de presença; revise o inventário.", CODIGO_INESPERADO)
    return tuple(itens)


def comandos_de_captura(assinatura: str, grupo: str, momento: str, pasta: str, inv: Inventario | None = None) -> str:
    """Texto PowerShell que exporta os instantâneos (somente leitura) sem sobrescrever arquivos. Nada é executado aqui."""
    if momento not in MOMENTOS:
        raise ErroLab(f"O momento deve ser {' ou '.join(MOMENTOS)}.")
    sub, nome_do_grupo, destino = _aspas(assinatura), _aspas(grupo), _aspas_de_caminho(pasta)
    arquivos = ARQUIVOS_DE_CAPTURA[momento]
    if momento == "depois" and inv is None:
        raise ErroLab("Para --momento depois, informe --inventario: o trecho de presença testa cada objeto dele.")
    if inv is not None and (inv.assinatura.lower() != assinatura.lower() or inv.grupo.lower() != grupo.lower()):
        raise ErroLab("--assinatura e --grupo não combinam com o inventário. Confira os dois valores antes de capturar.")
    cabecalho = [
        f"# {'Linha de base' if momento == 'antes' else 'Estado final'}: somente leitura (nada é criado nem apagado). Cole o bloco inteiro "
        "(ele é um único comando) no PowerShell 7, com az login feito.",
        ("# Execute ANTES de criar o grupo exclusivo do laboratório: a linha de base é o que existia antes dele."
         if momento == "antes" else
         "# Execute depois de rodar todos os passos do plano. Guarde os arquivos em local privado: eles trazem identificadores."),
    ]
    linhas = [
        f"$assinatura = {sub}",
        f"$grupo = {nome_do_grupo}",
        f"$pasta = {destino}",
    ]
    if momento == "depois" and inv is not None and inv.usa_graph:
        linhas += [_bloco_da_conta(inv), _bloco_do_graph(inv)]
    if momento == "antes":
        linhas += [
            "# A linha de base só vale se o grupo exclusivo ainda não existir.",
            "$existe = az group exists --name $grupo --subscription $assinatura",
            "if ($LASTEXITCODE -ne 0) { throw 'Não foi possível consultar o grupo: nada foi gravado.' }",
            "if ($existe -ne 'false') { throw 'O grupo já existe: a linha de base precisa ser capturada antes de criá-lo. Nada foi gravado.' }",
        ]
    linhas += [
        "# As três leituras acontecem antes de qualquer gravação; se uma falhar, nada é gravado.",
        "$grupos = az group list --subscription $assinatura --query '[].{id:id,name:name}' --output json",
        "if ($LASTEXITCODE -ne 0) { throw 'az group list falhou: nada foi gravado.' }",
        "$recursos = az resource list --subscription $assinatura --query '[].{id:id,type:type}' --output json",
        "if ($LASTEXITCODE -ne 0) { throw 'az resource list falhou: nada foi gravado.' }",
        "$papeis = az role assignment list --all --subscription $assinatura --fill-principal-name false --fill-role-definition-name "
        "false --query '[].{id:id,principalId:principalId,roleDefinitionId:roleDefinitionId,scope:scope}' --output json",
        "if ($LASTEXITCODE -ne 0) { throw 'az role assignment list falhou: nada foi gravado.' }",
    ]
    itens = itens_de_presenca(inv) if momento == "depois" and inv is not None else ()
    if itens:
        linhas += _trecho_de_presenca(itens)
    nomes = ", ".join(f"'{arquivos[c]}'" for c in ("grupos", "recursos", "papeis", *(("presenca",) if itens else ())))
    linhas += [
        "# Nada é sobrescrito: se algum arquivo já existir, nada é gravado.",
        f"$alvos = @({nomes}) | ForEach-Object {{ Join-Path $pasta $_ }}",
        "if (-not (Test-Path -LiteralPath $pasta -PathType Container)) { New-Item -ItemType Directory -Path $pasta | Out-Null }",
        "if ($alvos | Where-Object { Test-Path -LiteralPath $_ }) { throw 'Algum arquivo já existe: nada foi sobrescrito. Use outra pasta.' }",
        f"$grupos | Out-File -LiteralPath (Join-Path $pasta '{arquivos['grupos']}') -Encoding utf8 -NoClobber",
        f"$recursos | Out-File -LiteralPath (Join-Path $pasta '{arquivos['recursos']}') -Encoding utf8 -NoClobber",
        f"$papeis | Out-File -LiteralPath (Join-Path $pasta '{arquivos['papeis']}') -Encoding utf8 -NoClobber",
    ]
    if itens:
        linhas += [f"$estados | ConvertTo-Json | Out-File -LiteralPath (Join-Path $pasta '{arquivos['presenca']}') -Encoding utf8 -NoClobber",
                   "$estados.GetEnumerator() | Group-Object -Property Value | ForEach-Object { $_.Name + ': ' + $_.Count }"]
    linhas.append("'Instantâneos gravados.'")
    return "\n".join(cabecalho) + "\n" + _preencher(_CAPTURA, AVISO_DA_VERSAO=_AVISO_DA_VERSAO_NA_CAPTURA,
                                                    CORPO=_indentar("\n".join(linhas), 4))


def _trecho_de_presenca(itens: Sequence[ItemDePresenca]) -> list[str]:
    linhas = ["# Presença de cada objeto do inventário. 404 = ausente; sucesso = presente; qualquer outro resultado = indeterminado.",
              "# Um 404 só prova ausência se o inventário tem IDs de OBJETO (nunca o clientId nem o appId no lugar do ID de objeto).",
              "$estados = [ordered]@{}"]
    linhas += [f"$estados[{_aspas(i.chave)}] = Get-EstadoGraph {_aspas(i.alvo)}" for i in itens if i.metodo == "graph"]
    for metodo, variavel, listagem in (
            (EXPURGO_CONTA_DE_MODELOS, "$excluidas", "az cognitiveservices account list-deleted"),
            (EXPURGO_COFRE_DE_CHAVES, "$excluidos", "az keyvault list-deleted")):
        do_metodo = [i for i in itens if i.metodo == metodo]
        if do_metodo:
            linhas += [f"{variavel} = {listagem} --subscription $assinatura --query '[].name' --output tsv",
                       "$falhou = $LASTEXITCODE -ne 0"]
            linhas += [f"$estados[{_aspas(i.chave)}] = if ($falhou) {{ 'indeterminado' }} elseif ({variavel} | Where-Object {{ $_ -ieq "
                       f"{_aspas(i.alvo)} }}) {{ 'presente' }} else {{ 'ausente' }}" for i in do_metodo]
    return linhas


def carregar_presenca(caminho: Path, inv: Inventario) -> dict[str, str]:
    dados, _ = ler_json(caminho, "--presenca")
    if not isinstance(dados, dict):
        raise ErroLab("O arquivo de presença (--presenca) deve ser um objeto {identificador: estado}, gerado pelo trecho de "
                      "'--etapa capturar --momento depois'.")
    esperadas = {i.chave for i in itens_de_presenca(inv)}
    desconhecidas = sum(1 for chave in dados if chave not in esperadas)
    if desconhecidas:
        raise ErroLab(f"O arquivo de presença tem {desconhecidas} identificador(es) que não são deste inventário: ele foi gerado "
                      "para outro inventário ou foi alterado. Gere-o de novo com '--etapa capturar --momento depois'.")
    invalidos = sum(1 for estado in dados.values() if estado not in ESTADOS_DE_PRESENCA)
    if invalidos:
        raise ErroLab(f"O arquivo de presença tem {invalidos} estado(s) inválido(s): use somente {', '.join(ESTADOS_DE_PRESENCA)}.")
    return dict(dados)


# --------------------------------------------------------------------------------------
# Conferência
# --------------------------------------------------------------------------------------

def _folha(identificador: str) -> str:
    """Os 8 primeiros caracteres (seguros) do último segmento: o suficiente para reconhecer o item, nunca o ID inteiro."""
    ultimo = identificador.rstrip("/").rsplit("/", 1)[-1]
    return re.sub(r"[^A-Za-z0-9._-]", "?", ultimo)[:8] + "…"


def _exemplos(itens: Sequence[str]) -> str:
    if not itens:
        return ""
    mostrados = list(itens[:LIMITE_DE_EXEMPLOS])
    return " Exemplos (8 primeiros caracteres): " + ", ".join(mostrados) + ("…" if len(itens) > LIMITE_DE_EXEMPLOS else "") + "."


def _criterio(identificador: str, conferidos: int, divergentes: int, detalhe: str, pendentes: int = 0) -> Criterio:
    estado = "reprovado" if divergentes else "pendente" if pendentes else "atendido"
    return Criterio(identificador, estado, conferidos, divergentes, pendentes, detalhe)


def _nao_aplicavel(identificador: str, detalhe: str) -> Criterio:
    return Criterio(identificador, "nao_aplicavel", 0, 0, 0, detalhe)


def conferir_encerramento(inv: Inventario, antes: Instantaneo, depois: Instantaneo, presenca: Mapping[str, str] | None) -> Conferencia:
    criterios: list[Criterio] = []
    avisos: list[str] = []

    total_da_base = len(antes.grupos) + len(antes.recursos) + len(antes.atribuicoes)
    criterios.append(_criterio("linha_de_base_com_itens", total_da_base, 0,
                               "A linha de base está totalmente vazia: não dá para distinguir uma assinatura sem nada de uma exportação da "
                               "assinatura errada. Confira a assinatura e refaça a captura da linha de base." if antes.vazio else
                               f"A linha de base tem {total_da_base} item(ns).", pendentes=int(antes.vazio)))

    presente = inv.grupo.lower() in depois.grupos
    criterios.append(_criterio("grupo_proprio_ausente", 1, int(presente),
                               "O grupo exclusivo AINDA aparece na listagem: a exclusão não terminou (confira o histórico de atividade)."
                               if presente else "O grupo exclusivo não aparece na listagem."))
    if inv.grupo_gerenciado:
        presente = inv.grupo_gerenciado.lower() in depois.grupos
        criterios.append(_criterio("grupo_gerenciado_ausente", 1, int(presente),
                                   "O grupo gerenciado AINDA aparece: o ambiente do Container Apps ainda não foi removido (não o "
                                   "manipule; confira o ambiente)." if presente else "O grupo gerenciado não aparece na listagem."))
    else:
        criterios.append(_nao_aplicavel("grupo_gerenciado_ausente", "O inventário não informa grupo gerenciado."))

    ausentes = sorted(g for g in antes.grupos if g not in depois.grupos)
    criterios.append(_criterio("grupos_anteriores_preservados", len(antes.grupos), len(ausentes),
                               f"{len(ausentes)} de {len(antes.grupos)} grupo(s) da linha de base sumiram." + _exemplos([g[:8] + "…" for g in ausentes])
                               if ausentes else f"{len(antes.grupos)} grupo(s) da linha de base conferidos."))
    if not antes.grupos and not antes.vazio:
        avisos.append("linha_de_base_sem_grupos")

    divergentes = sorted((i, tipo) for i, tipo in antes.recursos.items() if depois.recursos.get(i) != tipo)
    criterios.append(_criterio("recursos_anteriores_preservados", len(antes.recursos), len(divergentes),
                               f"{len(divergentes)} de {len(antes.recursos)} recurso(s) da linha de base sumiram ou mudaram de tipo."
                               + _exemplos([f"{tipo}:{_folha(i)}" for i, tipo in divergentes])
                               if divergentes else f"{len(antes.recursos)} recurso(s) da linha de base conferidos."))
    if not antes.recursos and not antes.vazio:
        avisos.append("linha_de_base_sem_recursos")

    restantes = sorted((i, tipo) for i, tipo in depois.recursos.items() if i.startswith(inv.prefixos_proprios) or i in inv.ids)
    criterios.append(_criterio("recursos_proprios_ausentes", len(inv.recursos), len(restantes),
                               f"{len(restantes)} recurso(s) ainda aparecem dentro do grupo exclusivo (ou do gerenciado)."
                               + _exemplos([f"{tipo}:{_folha(i)}" for i, tipo in restantes])
                               if restantes else "Nenhum recurso resta no grupo exclusivo nem no gerenciado."))

    alterados = sorted(i for i, valor in antes.atribuicoes.items() if depois.atribuicoes.get(i) != valor)
    criterios.append(_criterio("atribuicoes_anteriores_preservadas", len(antes.atribuicoes), len(alterados),
                               f"{len(alterados)} de {len(antes.atribuicoes)} atribuição(ões) da linha de base sumiram ou mudaram."
                               + _exemplos([_folha(i) for i in alterados])
                               if alterados else f"{len(antes.atribuicoes)} atribuição(ões) da linha de base conferidas."))
    if not antes.atribuicoes and not antes.vazio:
        avisos.append("linha_de_base_sem_atribuicoes")

    proprias = sorted(i for i, (_, _, escopo) in depois.atribuicoes.items() if (escopo + "/").startswith(inv.prefixos_proprios) or i in inv.ids)
    criterios.append(_criterio("atribuicoes_proprias_ausentes", len(inv.atribuicoes), len(proprias),
                               f"{len(proprias)} atribuição(ões) própria(s) ainda aparecem (escopo no grupo exclusivo ou ID do inventário)."
                               + _exemplos([_folha(i) for i in proprias])
                               if proprias else "Nenhuma atribuição própria resta."))

    itens = itens_de_presenca(inv)
    for categoria in (ENTRA_APLICATIVOS, ENTRA_PRINCIPAIS, ENTRA_EXCLUIDOS, EXPURGO_MODELOS, EXPURGO_COFRE):
        da_categoria = [i for i in itens if i.categoria == categoria]
        if not da_categoria:
            criterios.append(_nao_aplicavel(categoria, "O inventário não tem itens desta categoria."))
            continue
        if presenca is None:
            criterios.append(_criterio(categoria, len(da_categoria), 0,
                                       f"Sem arquivo de presença (--presenca): {len(da_categoria)} item(ns) NÃO conferido(s).",
                                       pendentes=len(da_categoria)))
            continue
        estados = Counter(presenca.get(i.chave, "faltando") for i in da_categoria)
        reprovados, pendentes = estados["presente"], estados["indeterminado"] + estados["faltando"]
        if reprovados:
            detalhe = f"{reprovados} de {len(da_categoria)} item(ns) AINDA presente(s)."
        elif pendentes:
            detalhe = (f"{pendentes} de {len(da_categoria)} item(ns) sem prova de ausência (indeterminado ou ausente do arquivo): "
                       "repita o trecho de presença; indeterminado NUNCA vale como ausente.")
        else:
            detalhe = f"{len(da_categoria)} item(ns) ausente(s)."
        criterios.append(_criterio(categoria, len(da_categoria), reprovados, detalhe, pendentes=0 if reprovados else pendentes))

    estados_dos_criterios = Counter(c.estado for c in criterios)
    resultado = "reprovado" if estados_dos_criterios["reprovado"] else "pendente" if estados_dos_criterios["pendente"] else "aprovado"
    if all(antes.sha256.get(lista) == depois.sha256.get(lista) for lista in ("grupos", "recursos", "papeis")):
        avisos.append("instantaneos_identicos_aos_da_linha_de_base")
    return Conferencia(
        resultado=resultado, criterios=tuple(criterios), avisos=tuple(avisos),
        linha_de_base={"grupos": len(antes.grupos), "recursos": len(antes.recursos), "atribuicoes": len(antes.atribuicoes)},
        inventario={"recursos_proprios": len(inv.recursos), "shared_private_links": len(inv.links),
                    "atribuicoes_proprias": len(inv.atribuicoes), "identidades_entra": len(inv.identidades),
                    "principais_proprios": len(inv.principais_proprios), "expurgos": len(inv.expurgos)},
        sha256={"inventario": inv.sha256, **{f"{papel}_antes": h for papel, h in antes.sha256.items()},
                **{f"{papel}_depois": h for papel, h in depois.sha256.items()}})


LIMITE_DA_CONFERENCIA = ("Esta conferência compara os arquivos que você exportou; ela não consulta o Azure e não prova custo, a ausência "
                         "de objetos fora do inventário nem o estado atual do ambiente. Um 404 do Graph só prova ausência se o "
                         "inventário traz IDs de OBJETO corretos (nunca o clientId). Mudanças legítimas de terceiros entre a linha "
                         "de base e o encerramento aparecem como divergência: investigue.")


def conferencia_em_texto(conferencia: Conferencia) -> str:
    rotulos = {"atendido": "atendido", "reprovado": "REPROVADO", "pendente": "PENDENTE", "nao_aplicavel": "não se aplica"}
    linhas = ["Conferência do encerramento (somente os arquivos exportados; nenhum ID é repetido aqui)"]
    for criterio in conferencia.criterios:
        linhas.append(f"  [{rotulos[criterio.estado]}] {criterio.id}: {CRITERIOS[criterio.id]}")
        if criterio.estado not in ("atendido", "nao_aplicavel"):
            linhas.append(f"      {criterio.detalhe}")
    contagem = Counter(c.estado for c in conferencia.criterios)
    linhas.append(f"Resumo: {contagem['atendido']} atendido(s), {contagem['reprovado']} reprovado(s), {contagem['pendente']} "
                  f"pendente(s), {contagem['nao_aplicavel']} não aplicável(is).")
    for aviso in conferencia.avisos:
        linhas.append(f"[AVISO] {_AVISOS[aviso]}")
    linhas.append(LIMITE_DA_CONFERENCIA)
    return "\n".join(linhas)


_AVISOS = {
    "linha_de_base_sem_grupos": "A linha de base não tem grupos: nada foi comparado no critério de grupos anteriores.",
    "linha_de_base_sem_recursos": "A linha de base não tem recursos: nada foi comparado no critério de recursos anteriores.",
    "linha_de_base_sem_atribuicoes": "A linha de base não tem atribuições: nada foi comparado no critério de atribuições anteriores.",
    "instantaneos_identicos_aos_da_linha_de_base": "Os três arquivos de depois são idênticos, byte a byte, aos da linha de base. Isso é esperado se nada "
                                                   "mais mudou na assinatura, mas também é o que acontece se o mesmo arquivo foi informado nos dois lugares "
                                                   "ou se o estado final foi exportado de novo antes do encerramento: confirme que são exportações diferentes.",
}


def relatorio_da_conferencia(conferencia: Conferencia) -> dict[str, Any]:
    """Relatório sanitizado: só contagens, hashes dos arquivos e vocabulário fechado. Sem IDs, nomes nem textos livres."""
    contagem = Counter(c.estado for c in conferencia.criterios)
    return {
        "versao_relatorio": VERSAO_DO_RELATORIO,
        "tipo": "conferencia-de-encerramento",
        "resultado": conferencia.resultado,
        "contagem": {estado: contagem.get(estado, 0) for estado in ESTADOS_DE_CRITERIO},
        "verificacoes": [{"id": c.id, "estado": c.estado, "conferidos": c.conferidos, "divergentes": c.divergentes,
                          "pendentes": c.pendentes} for c in conferencia.criterios],
        "linha_de_base": dict(conferencia.linha_de_base),
        "inventario": dict(conferencia.inventario),
        "avisos": list(conferencia.avisos),
        "entradas_sha256": dict(conferencia.sha256),
        "limite": LIMITE_DA_CONFERENCIA,
    }


def exigir_aprovacao(conferencia: Conferencia) -> None:
    """Levanta o erro de divergência (código 3) se a conferência não estiver aprovada. Pendente NUNCA é aprovado."""
    if conferencia.resultado == "aprovado":
        return
    situacao = "REPROVADO" if conferencia.resultado == "reprovado" else "PENDENTE"
    raise ErroLab(f"Encerramento {situacao}: ele NÃO pode ser considerado concluído. Corrija ou complete os itens acima e repita a "
                  "captura e a conferência. Consulte também os custos sem interpretar resposta vazia como custo zero.",
                  CODIGO_DIVERGENCIA)
