"""Sonda do L300: confere o laboratório de DENTRO da rede privada, como um Azure Container Apps Job de execução manual.

Depois que o Blob, a busca e os modelos deixam de aceitar a internet (Desafio 04), o seu computador não alcança mais os dados: só o
que roda dentro da rede do ambiente alcança. Esta sonda é esse executor. Ela vai em uma imagem derivada da imagem do chat (monte o
contexto de build com scripts/montar_contexto_sonda_l300.py), usa uma identidade gerenciada atribuída ao usuário e reutiliza os
módulos reais do chat: Recuperador e ServicoRag são os mesmos bytes da aplicação.

Cada execução cumpre UMA etapa (--etapa ou VARELEIRA_PROBE_ETAPA) e termina: não há servidor nem espera aberta. A saída privada da
ferramenta de ingestão (nomes de recursos, URLs, mensagens do serviço) é capturada em memória e descartada. O único texto emitido é
UMA linha `L300_SONDA_RESULTADO=<JSON>`, de vocabulário fechado (números, booleanos e códigos curtos), e o código de saída dá o
veredicto:
    0 aprovado; 1 uso ou configuração; 2 acesso, rede, serviço ou tempo; 3 reprovado (divergência); 4 defeito.
Uma barreira final troca a linha por um defeito (`saida_bloqueada`) se ela trouxer algo que pareça token, URL, host, IP, GUID ou um
valor da configuração informada, e o código de saída é sempre o da linha realmente emitida (então 4, nunca o da linha recusada). Por
isso, não dê a um recurso um nome igual a uma palavra do vocabulário da linha (como `l300`).

Etapas:
    validar      local, sem rede: manifesto, documentos, módulos da imagem e configuração informada
    dns          os nomes oficiais do Blob, da busca e dos modelos resolvem só para endereços RFC 1918 (redes privadas)
    carregar, criar, executar, conferir, excluir, restaurar
                 chamam scripts/gerenciar_ingestao_l300.py com --identidade-gerenciada (excluir e restaurar só do VLAR-OP-ATD-1.0)
    resumo       contagens do índice por documento e por classe de acesso, e a última execução do indexador
    acesso       Recuperador e ServicoRag reais, com os papéis estáticos de lab_acesso (filtro e preFilter), no máximo uma geração
    http-interno (opcional) chamadas ao chat pelo endereço do Azure Container Apps, com o token da identidade gerenciada: verificações
                 de saúde e prontidão, API anônima e com cabeçalho inventado (401) e UMA pergunta autenticada, conferida contra o
                 perfil (consome embeddings e uma geração)
    negativas-mi três GETs que a identidade do chat NÃO pode fazer (Blob original, índices da busca, conta no ARM) e que devem dar 403,
                 feitos de dentro da rede para que a negativa seja de papel, não de rede (a sonda reprova se vier 2xx)

Configuração, só não secreta (variáveis de ambiente do Job): VARELEIRA_PROBE_CONTA, _BUSCA, _MODELOS, _ASSINATURA, _GRUPO e _CLIENT_ID.
O _CLIENT_ID escolhe a identidade gerenciada atribuída ao usuário que a execução usa (a da sonda; a do chat em negativas-mi).
Opcionais: _DOCUMENTO_AUSENTE (conferir --ausente), _ESPERA_SEGUNDOS (executar --aguardar; padrão 900), _LIMITE_SEGUNDOS (vigia da
sonda), _GERACAO (sim ou nao; padrão sim), _DEPLOYMENT_EMBEDDINGS, _DEPLOYMENT_GERACAO, _DIMENSOES, _ESFORCO, _EXIGIR_CONFIGURACAO
(validar), e, em http-interno, _URL, _APP_ID e _PERFIL (atendimento, corretor, ambos ou sem-acesso). Índice e contêiner são os do L300.
Os valores são configuração privada (nomes e IDs do seu ambiente): não os publique. Não há segredo: a identidade gerenciada não tem.

Efeitos, custo e limpeza (quem decide o que a identidade do Job pode fazer é você, pelos papéis que atribui a ela): validar, dns,
resumo, conferir e negativas-mi só leem (negativas-mi faz GETs que devem ser recusados). carregar, excluir e restaurar gravam só os
blobs do manifesto no contêiner do L300 (a exclusão é reversível e só do VLAR-OP-ATD-1.0; restaurar a desfaz). criar e executar mexem
só nos quatro objetos de busca do L300, e o indexador consome o modelo de embeddings. acesso consome embeddings e, no máximo, UMA
geração. http-interno não grava nada, mas CONSOME TOKENS: a pergunta autenticada ao chat passa por embeddings e por UMA geração. As
duas requisições sem identidade que também levam a pergunta devem ser recusadas com 401; se a plataforma não as recusar, o chat pode
processá-las (mais consumo) e a etapa reprova. O Job cobra o tempo de cada execução. A sonda não retira o Job, a imagem, as
identidades nem os papéis: a limpeza é a do roteiro do desafio, e cada uma dessas operações precisa da sua autorização.

Exemplos:
    python scripts\\sonda_l300.py --etapa validar            (no seu computador ou no build da imagem: local, sem rede e sem Azure)
    $env:VARELEIRA_PROBE_ETAPA = 'validar'; python scripts\\sonda_l300.py
    python scripts/sonda_l300.py --etapa dns                 (dentro do Job, com as variáveis VARELEIRA_PROBE_* da definição do Job)
    VARELEIRA_PROBE_ETAPA=conferir python scripts/sonda_l300.py
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import importlib
import inspect
import io
import ipaddress
import json
import logging
import math
import os
import re
import socket
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field, fields
from typing import Any, Callable, Iterator, Mapping, Sequence

SENTINELA = "L300_SONDA_RESULTADO="
FORMATO = 1
NOME_DA_SONDA = "l300"

# Os mesmos códigos de saída de lab_comum.
OK, USO, ACESSO, DIVERGENCIA, INESPERADO = 0, 1, 2, 3, 4

ETAPAS = ("validar", "dns", "carregar", "criar", "executar", "conferir", "excluir", "restaurar", "resumo", "acesso", "http-interno",
          "negativas-mi")
INDICE = "vareleira-lar-l300"
CONTAINER = "base-documental-l300"
DOCUMENTO_OPERACIONAL = "VLAR-OP-ATD-1.0"
MARCADOR = "ATD-L300-ROTEIRO-7Q4K"
PERGUNTA = "No roteiro interno de atendimento do Vareleira Lar, qual é o código de verificação do exercício, ATD-L300-ROTEIRO-7Q4K?"
# Para o HTTP: sem o código nem o ID do roteiro, para que a presença deles na resposta prove recuperação, e não eco da pergunta.
PERGUNTA_DO_CHAT = "Qual é o código educativo de verificação do exercício descrito no roteiro interno de atendimento do Vareleira Lar?"
GUID_ZERO = "00000000-0000-0000-0000-000000000000"

ESPERA_MINIMA, ESPERA_PADRAO, ESPERA_MAXIMA = 10, 900, 1500  # o limite máximo da ferramenta é 1800 s; a sonda para antes
LIMITE_MINIMO, LIMITE_MAXIMO = 30, 1750  # o tempo limite da réplica do Job é 1800 s
LIMITE_PADRAO, MARGEM_DO_INDEXADOR = 600, 300
LIMITES_POR_ETAPA = {"acesso": 900, "http-interno": 600, "negativas-mi": 300}
TEMPO_HTTP, TEMPO_DO_CHAT, LIMITE_DO_CORPO_HTTP = 30, 120, 65536  # o chat pode partir de zero réplicas: a primeira resposta demora
ESCOPO_BLOB, ESCOPO_ARM = "https://storage.azure.com/.default", "https://management.azure.com/.default"
VERSAO_DO_BLOB, VERSAO_DA_API_DO_ARM = "2023-11-03", "2024-01-01"

_REDES_RFC1918 = tuple(ipaddress.ip_network(rede) for rede in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))
_CRITICAS_DA_CONFERENCIA = frozenset({"objetos", "exclusao_nativa", "definicoes", "ambiente_privado", "indexador", "trechos",
                                      "compatibilidade", "campo_acesso", "classe_de_acesso"})


class ErroSonda(Exception):
    """Falha prevista, com causa de vocabulário fechado. Nenhum texto livre (mensagem de serviço, nome de recurso) entra aqui."""

    def __init__(self, causa: str, codigo: int = ACESSO, **dados: Any):
        super().__init__(causa)
        self.causa, self.codigo, self.dados = causa, codigo, dados

    @property
    def veredicto(self) -> str:
        return "reprovado" if self.codigo == DIVERGENCIA else "erro"


@dataclass
class Resultado:
    etapa: str | None
    codigo: int
    veredicto: str
    causa: str | None = None
    dados: dict[str, Any] = field(default_factory=dict)
    duracao_s: float = 0.0


# --------------------------------------------------------------------------------------
# Módulos do laboratório, importados sob demanda
# --------------------------------------------------------------------------------------

def nome_fechado(valor: Any, limite: int = 60) -> str:
    return re.sub(r"[^A-Za-z0-9_.]", "", str(valor or ""))[:limite] or "desconhecido"


def importar(nome: str) -> Any:
    try:
        return importlib.import_module(nome)
    except ImportError as erro:
        raise ErroSonda("dependencia_ausente", USO, modulo=nome_fechado(erro.name or nome)) from None


class _Modulos:
    """Acesso por atributo (`mod.lab_comum`) que importa na primeira vez: a falta de um módulo vira resultado fechado, não traceback."""

    def __getattr__(self, nome: str) -> Any:
        if nome.startswith("__"):
            raise AttributeError(nome)
        modulo = importar(nome)
        setattr(self, nome, modulo)
        return modulo


mod = _Modulos()


# --------------------------------------------------------------------------------------
# Resultado: vocabulário fechado, proteção da saída e emissão única
# --------------------------------------------------------------------------------------

_TEXTO_FECHADO = re.compile(r"[A-Za-z0-9_.:+-]{0,80}")
_PADROES_PROIBIDOS = (
    ("url", re.compile(r"(?i)https?://|\bwww\.")),
    ("guid", re.compile(r"(?i)\b[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}\b")),
    ("token", re.compile(r"eyJ[A-Za-z0-9_-]{8,}|(?i:bearer)\s+\S{8,}")),
    ("ip", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")),
    ("host", re.compile(r"(?i)[a-z0-9-]+\.(?:blob\.core\.windows\.net|search\.windows\.net|openai\.azure\.com|azurecontainerapps\.io"
                        r"|azurecr\.io|vault\.azure\.net)")),
    ("segredo", re.compile(r"[A-Za-z0-9+/_=-]{48,}")),
)


def _fechar(valor: Any) -> Any:
    """Só números, booleanos, None e textos curtos do vocabulário fechado passam; o resto vira um marcador inofensivo."""
    if valor is None or isinstance(valor, (bool, int)):
        return valor
    if isinstance(valor, float):
        return round(valor, 2) if math.isfinite(valor) else None
    if isinstance(valor, str):
        return valor if _TEXTO_FECHADO.fullmatch(valor) else "<fora_do_vocabulario>"
    if isinstance(valor, Mapping):
        return {(chave if isinstance(chave, str) and _TEXTO_FECHADO.fullmatch(chave) else "<chave>"): _fechar(item)
                for chave, item in valor.items()}
    if isinstance(valor, (set, frozenset)):
        valor = sorted(valor, key=str)
    if isinstance(valor, (list, tuple)):
        return [_fechar(item) for item in valor]
    return "<tipo_nao_suportado>"


def _serializar(resultado: Resultado) -> str:
    corpo = {"v": FORMATO, "sonda": NOME_DA_SONDA, "etapa": resultado.etapa, "codigo": int(resultado.codigo),
             "veredicto": resultado.veredicto, "causa": resultado.causa, "duracao_s": resultado.duracao_s,
             "dados": resultado.dados}
    return json.dumps(_fechar(corpo), ensure_ascii=True, separators=(",", ":"), sort_keys=True)


def proteger_com_codigo(resultado: Resultado, privados: Sequence[str] = ()) -> tuple[str, int]:
    """A linha JSON do resultado e o código de saída que ela declara.

    Se a linha trouxer algo que pareça token, URL, host, IP, GUID ou valor configurado, ela é trocada pela de um defeito
    (`saida_bloqueada`) e o código passa a ser INESPERADO: o código de saída do processo é sempre o da linha realmente emitida.
    """
    texto = _serializar(resultado)
    achados = {nome for nome, padrao in _PADROES_PROIBIDOS if padrao.search(texto)}
    for valor in privados:
        if len(valor) >= 3 and re.search(r"(?<![A-Za-z0-9])" + re.escape(valor) + r"(?![A-Za-z0-9])", texto, re.IGNORECASE):
            achados.add("valor_de_configuracao")
    if not achados:
        return texto, int(resultado.codigo)
    return _serializar(Resultado(resultado.etapa, INESPERADO, "erro", "saida_bloqueada", {"padroes": sorted(achados)},
                                 resultado.duracao_s)), INESPERADO


def proteger(resultado: Resultado, privados: Sequence[str] = ()) -> str:
    """A linha JSON do resultado, ou a de um defeito se ela trouxer algo que pareça token, URL, host, IP, GUID ou valor configurado."""
    return proteger_com_codigo(resultado, privados)[0]


def linha_do_resultado(resultado: Resultado, privados: Sequence[str] = ()) -> tuple[str, int]:
    """(linha, código de saída) que serão emitidos. Se a própria proteção falhar, vale a linha de último recurso (`saida_invalida`, 4)."""
    try:
        return proteger_com_codigo(resultado, privados)
    except Exception:  # noqa: BLE001 - a linha de último recurso não depende de nada do resultado
        return json.dumps({"v": FORMATO, "sonda": NOME_DA_SONDA, "etapa": None, "codigo": INESPERADO, "veredicto": "erro",
                           "causa": "saida_invalida", "duracao_s": 0, "dados": {}}, separators=(",", ":"), sort_keys=True), INESPERADO


class Emissor:
    """Escreve no máximo uma linha sentinela, mesmo que o vigia e a etapa terminem juntos, e guarda o código que essa linha declara.

    `codigo` é o código de saída do processo: o da linha realmente emitida (a de um defeito, se a barreira a trocou ou se nenhuma saiu).
    """

    def __init__(self, destino: Any):
        self._destino, self._trava, self._emitido = destino, threading.Lock(), False
        self.codigo = INESPERADO

    def emitir(self, resultado: Resultado, privados: Sequence[str] = ()) -> bool:
        linha, codigo = linha_do_resultado(resultado, privados)
        return self.emitir_linha(linha, codigo)

    def emitir_linha(self, linha: str, codigo: int) -> bool:
        """Escreve uma linha JÁ protegida (veja `linha_do_resultado`), para quem também a grava em outro lugar com o mesmo conteúdo."""
        with self._trava:
            if self._emitido:
                return False
            self._emitido = True
            self.codigo = codigo
            self._destino.write(SENTINELA + linha + "\n")
            self._destino.flush()
        return True


# --------------------------------------------------------------------------------------
# Configuração (não secreta) por variáveis de ambiente
# --------------------------------------------------------------------------------------

def _inteiro_entre(minimo: int, maximo: int) -> Callable[[str], int]:
    def validar(valor: str) -> int:
        if not re.fullmatch(r"[0-9]{1,6}", valor) or not minimo <= int(valor) <= maximo:
            raise ValueError
        return int(valor)

    return validar


def escolha(opcoes: Callable[[], Sequence[str]]) -> Callable[[str], str]:
    def validar(valor: str) -> str:
        if valor not in opcoes():
            raise ValueError
        return valor

    return validar


def _sim_ou_nao(valor: str) -> bool:
    if valor.lower() in ("sim", "true"):
        return True
    if valor.lower() in ("nao", "false"):
        return False
    raise ValueError


def _documento_operacional(valor: str) -> str:
    if valor != DOCUMENTO_OPERACIONAL:
        raise ValueError
    return valor


_PADRAO_URL = re.compile(r"https://[a-z0-9](?:[a-z0-9-]{0,60}[a-z0-9])?(?:\.internal)?(?:\.[a-z0-9](?:[a-z0-9-]{0,60}[a-z0-9])?){2}"
                         r"\.azurecontainerapps\.io/?")


def url_do_aplicativo(valor: str) -> str:
    """O endereço do chat no Azure Container Apps (só HTTPS e só `*.azurecontainerapps.io`), sem a barra final."""
    if not _PADRAO_URL.fullmatch(valor):
        raise ValueError
    return valor.rstrip("/")


# (chave, variável de ambiente, validador, padrão). Os validadores são os da própria ferramenta: o formato dos nomes e dos GUIDs
# é conferido antes de qualquer endereço ser montado.
_VARIAVEIS = (
    ("conta", "VARELEIRA_PROBE_CONTA", lambda v: mod.lab_comum.validar_conta(v), None),
    ("busca", "VARELEIRA_PROBE_BUSCA", lambda v: mod.lab_indexacao.validar_busca(v), None),
    ("modelos", "VARELEIRA_PROBE_MODELOS", lambda v: mod.lab_indexacao.validar_modelos(v), None),
    ("assinatura", "VARELEIRA_PROBE_ASSINATURA", lambda v: mod.lab_ingestao.validar_assinatura(v), None),
    ("grupo", "VARELEIRA_PROBE_GRUPO", lambda v: mod.lab_ingestao.validar_grupo(v), None),
    ("client_id", "VARELEIRA_PROBE_CLIENT_ID", lambda v: mod.lab_ingestao_l300.validar_client_id(v), None),
    ("documento_ausente", "VARELEIRA_PROBE_DOCUMENTO_AUSENTE", _documento_operacional, None),
    ("espera", "VARELEIRA_PROBE_ESPERA_SEGUNDOS", _inteiro_entre(ESPERA_MINIMA, ESPERA_MAXIMA), lambda: ESPERA_PADRAO),
    ("limite", "VARELEIRA_PROBE_LIMITE_SEGUNDOS", _inteiro_entre(LIMITE_MINIMO, LIMITE_MAXIMO), None),
    ("geracao", "VARELEIRA_PROBE_GERACAO", _sim_ou_nao, lambda: True),
    ("deployment_embeddings", "VARELEIRA_PROBE_DEPLOYMENT_EMBEDDINGS", lambda v: mod.lab_indexacao.validar_deployment(v),
     lambda: mod.lab_indexacao.DEPLOYMENT_PADRAO),
    ("deployment_geracao", "VARELEIRA_PROBE_DEPLOYMENT_GERACAO", lambda v: mod.lab_indexacao.validar_deployment(v),
     lambda: mod.lab_geracao.DEPLOYMENT_GERACAO_PADRAO),
    ("dimensoes", "VARELEIRA_PROBE_DIMENSOES", lambda v: mod.lab_indexacao.validar_dimensoes(v),
     lambda: mod.lab_indexacao.DIMENSOES_PADRAO),
    ("esforco", "VARELEIRA_PROBE_ESFORCO", escolha(lambda: mod.lab_geracao.ESFORCOS), lambda: mod.lab_geracao.ESFORCO_PADRAO),
    ("exigir_configuracao", "VARELEIRA_PROBE_EXIGIR_CONFIGURACAO", _sim_ou_nao, lambda: False),
    ("url", "VARELEIRA_PROBE_URL", url_do_aplicativo, None),
    ("app_id", "VARELEIRA_PROBE_APP_ID", lambda v: mod.lab_ingestao_l300.validar_client_id(v), None),
    ("perfil", "VARELEIRA_PROBE_PERFIL", escolha(lambda: tuple(ESPERADO_POR_PERFIL)), lambda: "atendimento"),
)
_CHAVES_DO_AZURE = ("conta", "busca", "modelos", "assinatura", "grupo", "client_id")
_CHAVES_PRIVADAS = _CHAVES_DO_AZURE + ("url", "app_id")

# etapa -> (chaves obrigatórias, chaves opcionais que, se informadas, precisam ser válidas)
_EXIGENCIAS = {
    "dns": (("conta", "busca", "modelos"), ()),
    "carregar": (("conta", "client_id"), ()),
    "excluir": (("conta", "client_id"), ()),
    "restaurar": (("conta", "client_id"), ()),
    "criar": (("conta", "busca", "assinatura", "grupo", "modelos", "client_id"), ("deployment_embeddings", "dimensoes")),
    "executar": (("busca", "client_id"), ("espera",)),
    "conferir": (("conta", "busca", "assinatura", "grupo", "modelos", "client_id"),
                 ("deployment_embeddings", "dimensoes", "documento_ausente")),
    "resumo": (("busca", "client_id"), ()),
    "acesso": (("busca", "modelos", "client_id"),
               ("deployment_embeddings", "deployment_geracao", "dimensoes", "esforco", "geracao")),
    "http-interno": (("url", "app_id", "client_id"), ("perfil",)),
    "negativas-mi": (("assinatura", "grupo", "conta", "busca", "client_id"), ()),
}


class Configuracao:
    def __init__(self, ambiente: Mapping[str, str], variaveis: Sequence[Any] = _VARIAVEIS, privadas: Sequence[str] = _CHAVES_PRIVADAS):
        self.valores: dict[str, Any] = {}
        self.ausentes: list[str] = []
        self.invalidas: list[str] = []
        self._brutos: list[str] = []
        self._padroes = {chave: padrao for chave, _, _, padrao in variaveis if padrao is not None}
        for chave, variavel, validar, _ in variaveis:
            bruto = (ambiente.get(variavel) or "").strip()
            if not bruto:
                self.ausentes.append(chave)
                continue
            if chave in privadas:
                self._brutos.append(bruto)
            try:
                self.valores[chave] = validar(bruto)
            except (argparse.ArgumentTypeError, ValueError):
                self.invalidas.append(chave)

    def obter(self, chave: str) -> Any:
        if chave in self.valores:
            return self.valores[chave]
        padrao = self._padroes.get(chave)
        return padrao() if padrao is not None else None

    def privados(self) -> tuple[str, ...]:
        return tuple(self._brutos)

    def exigir(self, *obrigatorias: str, opcionais: Sequence[str] = ()) -> None:
        invalidas = [chave for chave in (*obrigatorias, *opcionais) if chave in self.invalidas]
        ausentes = [chave for chave in obrigatorias if chave in self.ausentes]
        if invalidas:
            raise ErroSonda("configuracao_invalida", USO, invalidas=invalidas, ausentes=ausentes)
        if ausentes:
            raise ErroSonda("configuracao_ausente", USO, ausentes=ausentes)


# --------------------------------------------------------------------------------------
# Classificação de exceções (sem nunca usar o texto delas)
# --------------------------------------------------------------------------------------

def classificar_excecao(erro: BaseException) -> ErroSonda:
    if isinstance(erro, ErroSonda):
        return erro
    nome = nome_fechado(type(erro).__name__)
    raiz = type(erro).__module__.split(".")[0]
    try:
        busca = mod.lab_ingestao.ErroServicoBusca
        laboratorio = mod.lab_comum.ErroLab
    except ErroSonda:
        busca = laboratorio = ()
    if busca and isinstance(erro, busca):
        return ErroSonda("servico_de_busca", ACESSO, status=erro.status)
    if laboratorio and isinstance(erro, laboratorio):
        return ErroSonda("erro_do_laboratorio", erro.codigo if erro.codigo in (USO, ACESSO, DIVERGENCIA, INESPERADO) else INESPERADO,
                         tipo=nome)
    if raiz in {"azure", "openai"}:
        status = getattr(erro, "status_code", None)
        return ErroSonda("erro_do_sdk", ACESSO, tipo=nome, status=status if isinstance(status, int) else None)
    if isinstance(erro, (OSError, TimeoutError)):
        return ErroSonda("rede", ACESSO, tipo=nome)
    return ErroSonda("defeito_da_sonda", INESPERADO, excecao=nome)


# --------------------------------------------------------------------------------------
# Ferramenta de ingestão do L300 (saída privada capturada e interpretada só por marcadores fechados)
# --------------------------------------------------------------------------------------

@dataclass(frozen=True)
class SaidaDaCli:
    codigo: int
    texto: str


def executar_cli(argv: Sequence[str]) -> SaidaDaCli:
    cli = mod.gerenciar_ingestao_l300
    captura = io.StringIO()
    with contextlib.redirect_stdout(captura), contextlib.redirect_stderr(captura):
        try:
            codigo = cli.principal(list(argv))
        except SystemExit as erro:
            codigo = erro.code if isinstance(erro.code, int) else USO
    return SaidaDaCli(int(codigo), captura.getvalue())


def argumentos_da_cli(etapa: str, cfg: Configuracao) -> list[str]:
    identidade = ["--identidade-gerenciada", "--client-id", cfg.obter("client_id")]
    conta = ["--conta", cfg.obter("conta"), "--container", CONTAINER]
    busca = ["--busca", cfg.obter("busca"), "--indice", INDICE]
    modelos = ["--deployment", cfg.obter("deployment_embeddings"), "--dimensoes", str(cfg.obter("dimensoes"))]
    destino_do_azure = ["--assinatura", cfg.obter("assinatura"), "--grupo", cfg.obter("grupo"), "--modelos", cfg.obter("modelos")]
    if etapa == "carregar":
        return ["--etapa", "carregar", *conta, "--executar", *identidade]
    if etapa in ("excluir", "restaurar"):
        return ["--etapa", etapa, *conta, "--documento", DOCUMENTO_OPERACIONAL, "--executar", *identidade]
    if etapa == "criar":
        return ["--etapa", "criar", *busca, *conta, *destino_do_azure, *modelos, "--executar", *identidade]
    if etapa == "executar":
        return ["--etapa", "executar", *busca, "--executar", "--aguardar", str(cfg.obter("espera")), *identidade]
    if etapa == "conferir":
        ausente = ["--ausente", cfg.obter("documento_ausente")] if cfg.obter("documento_ausente") else []
        return ["--etapa", "conferir", *busca, *conta, *destino_do_azure, *modelos, *ausente, *identidade]
    raise ErroSonda("etapa_sem_cli", USO)


_CARGA = re.compile(r"Concluído: (\d+) criado\(s\), (\d+) trocado\(s\), (\d+) com metadados atualizados, (\d+) já igual\(is\)\.")
_CRIACAO = re.compile(r"Concluído: (\d+) criado\(s\), (\d+) substituído\(s\), (\d+) já igual\(is\)\.")
_CRIACAO_IGUAL = re.compile(r"\[IGUAL\] Os quatro objetos já estão como o plano pede")
_ORFAOS = re.compile(r"\[AVISO\] (\d+) blob\(s\) na pasta '[^']*' sem permissão declarada")
_EXCLUSAO = re.compile(r"Concluído: (\d+) blob\(s\) excluído\(s\) de forma reversível\.")
_RESTAURACAO = re.compile(r"Concluído: (\d+) blob\(s\) restaurado\(s\)\.")
_EXECUCAO_OK = re.compile(r"Execução concluída sem falhas\.")
_VALIDACAO_OK = re.compile(r"Validação concluída\.")
_CONFERENCIA_OK = re.compile(r"Conferência aprovada\.")
_VERIFICACAO = re.compile(r"^\[(OK|FALHA)\s*\] (.*)$", re.MULTILINE)
_AUSENTE_DO_INDICE = re.compile(r"Documento ([A-Z0-9][A-Z0-9.-]{2,39}) ausente do índice:")
_NOMES_DAS_VERIFICACOES = (
    ("Objetos do pipeline do L300", "objetos"), ("Detecção de exclusão", "exclusao_nativa"),
    ("Definições dos objetos", "definicoes"), ("Ambiente de execução do indexador", "ambiente_privado"),
    ("Indexador: última execução", "indexador"), ("Trechos do índice", "trechos"),
    ("Compatibilidade com o recuperador do L100", "compatibilidade"), ("Campo de acesso do índice", "campo_acesso"),
    ("Classe de acesso dos trechos", "classe_de_acesso"),
)
_MARCADORES = (
    ("parada", "[PARADA]"), ("tempo_esgotado", "[TEMPO ESGOTADO]"), ("atencao", "[ATENÇÃO]"), ("simulacao", "Simulação concluída"),
    ("conferencia_reprovada", "Conferência reprovada"), ("execucao_com_falhas", "Execução concluída com falhas ou erros"),
    ("restauracao_divergente", "o conteúdo restaurado difere do manifesto"), ("blob_mudou", "o blob mudou"),
    ("nada_a_excluir", "[IGUAL] Nenhum blob ativo para excluir"),
    ("nada_a_restaurar", "[IGUAL] Nenhum blob excluído de forma reversível para restaurar"),
)
_SERVICOS = (
    ("blob_sem_permissao", re.compile(r"permissão de dados no contêiner")),
    ("busca_sem_permissao", re.compile(r"não tem permissão para esta operação no serviço de busca|Search Service Contributor")),
    ("modelos_sem_permissao", re.compile(r"serviço de modelos recusou o pedido \(HTTP (?:401|403)")),
    ("http_401", re.compile(r"HTTP 401|recusou a credencial")),
    ("http_403", re.compile(r"HTTP 403|não tem permissão")),
    ("http_404", re.compile(r"HTTP 404|não foi encontrad|não encontrado|não existe na conta")),
    ("http_409", re.compile(r"HTTP 409|Conflito no serviço de busca")),
    ("http_412", re.compile(r"HTTP 412")),
    ("http_429", re.compile(r"HTTP 429|limitando")),
    ("http_5xx", re.compile(r"HTTP 5\d\d|indisponível ou ocupado|demorou demais")),
    ("rede", re.compile(r"Não foi possível conectar")),
    ("credencial", re.compile(r"credenciais do Azure CLI|CredentialUnavailable")),
    ("erro_do_azure", re.compile(r"Erro do Azure \(")),
    ("defeito_da_cli", re.compile(r"Erro inesperado do script")),
)


def marcadores_de(texto: str) -> list[str]:
    return [nome for nome, trecho in _MARCADORES if trecho in texto]


def servico_de(texto: str) -> str:
    return next((codigo for codigo, padrao in _SERVICOS if padrao.search(texto)), "desconhecido")


def verificacoes_de(texto: str) -> dict[str, Any]:
    aprovadas: list[str] = []
    falhas: list[str] = []
    for situacao, resto in _VERIFICACAO.findall(texto):
        codigo = next((fechado for nome, fechado in _NOMES_DAS_VERIFICACOES if resto.startswith(nome + ":")), None)
        if codigo is None:
            ausente = _AUSENTE_DO_INDICE.match(resto)
            codigo = f"ausente_{ausente.group(1)}" if ausente else "outra"
        (aprovadas if situacao == "OK" else falhas).append(codigo)
    return {"verificacoes_ok": len(aprovadas), "verificacoes_falha": len(falhas), "falhas": falhas, "aprovadas": aprovadas}


def extrair(etapa: str, texto: str) -> dict[str, Any]:
    """Só contagens e códigos fechados do que a ferramenta contou; nada do texto original é repassado."""
    dados: dict[str, Any] = {}
    if etapa == "carregar":
        achado = _CARGA.search(texto)
        if achado:
            dados.update(zip(("criados", "substituidos", "metadados", "iguais"), map(int, achado.groups())))
        orfaos = _ORFAOS.search(texto)
        dados["orfaos"] = int(orfaos.group(1)) if orfaos else 0
    elif etapa == "criar":
        achado = _CRIACAO.search(texto)
        if achado:
            dados.update(zip(("criados", "substituidos", "iguais"), map(int, achado.groups())))
        elif _CRIACAO_IGUAL.search(texto):
            dados.update(criados=0, substituidos=0, iguais=4)
    elif etapa == "executar":
        dados["concluida_sem_falhas"] = bool(_EXECUCAO_OK.search(texto))
    elif etapa == "conferir":
        dados.update(verificacoes_de(texto))
    elif etapa == "excluir":
        achado = _EXCLUSAO.search(texto)
        if achado:
            dados["excluidos"] = int(achado.group(1))
    elif etapa == "restaurar":
        achado = _RESTAURACAO.search(texto)
        if achado:
            dados["restaurados"] = int(achado.group(1))
    return dados


def _causa_da_cli(codigo: int, marcadores: Sequence[str]) -> str:
    for marcador, causa in (("tempo_esgotado", "indexador_nao_terminou"), ("execucao_com_falhas", "indexador_com_falhas"),
                            ("conferencia_reprovada", "conferencia_reprovada"), ("restauracao_divergente", "restauracao_divergente"),
                            ("parada", "parada_por_divergencia"), ("atencao", "primeira_execucao_sem_itens")):
        if marcador in marcadores:
            return causa
    return {USO: "uso_ou_manifesto_da_cli", ACESSO: "acesso_ou_servico", DIVERGENCIA: "divergencia",
            INESPERADO: "defeito_da_cli"}.get(codigo, "codigo_inesperado_da_cli")


def _conferir_o_sucesso(etapa: str, dados: dict[str, Any], texto: str, cfg: Configuracao) -> None:
    """O código 0 não basta: a linha de conclusão e as contagens esperadas precisam estar na saída (uma simulação também sai com 0)."""
    inesperada = ErroSonda("saida_inesperada_da_cli", DIVERGENCIA, **dados)
    if etapa == "carregar":
        if "criados" not in dados:
            raise inesperada
        if dados["orfaos"]:
            raise ErroSonda("blobs_fora_do_manifesto", DIVERGENCIA, **dados)
    elif etapa == "criar":
        if "iguais" not in dados:
            raise inesperada
    elif etapa == "executar":
        if not dados["concluida_sem_falhas"]:
            raise inesperada
    elif etapa == "conferir":
        if not _CONFERENCIA_OK.search(texto):
            raise inesperada
        exigidas = set(_CRITICAS_DA_CONFERENCIA)
        if cfg.obter("documento_ausente"):
            exigidas.add(f"ausente_{cfg.obter('documento_ausente')}")
        faltam = sorted(exigidas - set(dados["aprovadas"]))
        if faltam:
            raise ErroSonda("conferencia_incompleta", DIVERGENCIA, faltam=faltam, **dados)
    elif etapa in ("excluir", "restaurar"):
        chave, vazio, causa = (("excluidos", "nada_a_excluir", "nada_excluido") if etapa == "excluir"
                               else ("restaurados", "nada_a_restaurar", "nada_restaurado"))
        if vazio in marcadores_de(texto):
            raise ErroSonda(causa, DIVERGENCIA, **dados)
        if chave not in dados:
            raise inesperada
        if dados[chave] != 1:
            raise ErroSonda("quantidade_inesperada", DIVERGENCIA, **dados)


# --------------------------------------------------------------------------------------
# Resumo do índice e do indexador (por documento e por classe, sem nomes de recursos)
# --------------------------------------------------------------------------------------

_RESULTADOS_DO_INDEXADOR = ("success", "transientFailure", "persistentFailure", "inProgress", "reset")
_ESTADOS_DO_INDEXADOR = ("running", "error", "unknown")


def _cliente_de_busca(cfg: Configuracao) -> Any:
    l300 = mod.lab_ingestao_l300
    return l300.abrir_cliente(cfg.obter("busca"), None, mod.lab_ingestao.VERSAO_API, l300.criar_credencial_gerenciada(cfg.obter("client_id")))


def resumir_indice(cliente: Any) -> dict[str, Any]:
    l300, acesso = mod.lab_ingestao_l300, mod.lab_acesso
    manifesto = l300.carregar_manifesto()
    trechos = mod.lab_ingestao.listar_trechos(cliente, INDICE, ("documento_id", acesso.CAMPO_ACESSO))
    analise = l300.analisar_acesso(trechos, manifesto)
    ids = [documento.id for documento in manifesto.documentos]
    por_documento = {identificador: analise.por_documento.get(identificador, 0) for identificador in ids}
    return {"disponivel": True, "trechos": analise.trechos, "por_documento": por_documento,
            "por_classe": {classe: analise.por_classe.get(classe, 0) for classe in acesso.CLASSES},
            "sem_classe": analise.sem_classe, "classe_desconhecida": analise.classe_desconhecida,
            "classe_diferente": analise.classe_diferente, "fora_do_manifesto": analise.fora_do_manifesto,
            "sem_trechos": [identificador for identificador, quantidade in por_documento.items() if not quantidade]}


def resumir_indexador(cliente: Any) -> dict[str, Any]:
    nomes = mod.lab_ingestao_l300.nomes_dos_objetos(INDICE)
    resumo = mod.lab_ingestao.resumir_status(cliente.status_indexador(nomes.indexador))
    return {"resultado": resumo.resultado if resumo.resultado in _RESULTADOS_DO_INDEXADOR else "nenhuma" if resumo.resultado is None
            else "outro", "estado": resumo.geral if resumo.geral in _ESTADOS_DO_INDEXADOR else "outro",
            "processados": resumo.processados, "falhas": resumo.falhas, "erros": len(resumo.erros), "avisos": len(resumo.avisos)}


def anexar_o_indice(dados: dict[str, Any], cfg: Configuracao, com_indexador: bool = False) -> None:
    """Complemento de diagnóstico: se não puder ser obtido, isso fica explícito no resultado, sem mudar o veredicto da etapa."""
    try:
        cliente = _cliente_de_busca(cfg)
        dados["indice"] = resumir_indice(cliente)
        if com_indexador:
            dados["indexador"] = resumir_indexador(cliente)
    except Exception as erro:  # noqa: BLE001 - classificada por tipo e status, nunca pelo texto
        falha = classificar_excecao(erro)
        dados["indice"] = {"disponivel": False, "causa": falha.causa, **falha.dados}


def _inconsistencias_do_indice(indice: Mapping[str, Any]) -> list[str]:
    return [nome for nome in ("sem_classe", "classe_desconhecida", "classe_diferente", "fora_do_manifesto") if indice.get(nome)]


# --------------------------------------------------------------------------------------
# Etapas
# --------------------------------------------------------------------------------------

def verificar_modulos() -> None:
    """Os módulos da imagem e as peças do chat (base) de que a sonda depende; uma base desatualizada é recusada aqui, com o nome da peça."""
    for nome in ("lab_comum", "lab_acesso", "lab_indexacao", "lab_ingestao", "lab_ingestao_l300", "gerenciar_ingestao",
                 "gerenciar_ingestao_l300", "lab_geracao", "lab_politica", "lab_chat",
                 "azure.core", "azure.identity", "azure.storage.blob", "azure.search.documents", "openai"):
        importar(nome)
    chat, geracao, acesso, indexacao, l300 = mod.lab_chat, mod.lab_geracao, mod.lab_acesso, mod.lab_indexacao, mod.lab_ingestao_l300
    verificacoes = (
        ("lab_chat.criar_servico_azure", hasattr(chat, "criar_servico_azure") and hasattr(chat, "ErroChat")),
        ("lab_chat.classificar_erro", all(hasattr(chat, nome) for nome in ("classificar_erro", "MENSAGENS", "RESPOSTA_NAO_VERIFICADA",
                                                                           "MODO_NUVEM"))),
        ("lab_chat.ConfiguracaoChat.exigir_acesso_documental",
         "exigir_acesso_documental" in {campo.name for campo in fields(chat.ConfiguracaoChat)}),
        ("lab_chat.ServicoRag.exigir_acesso", "exigir_acesso" in inspect.signature(chat.ServicoRag.__init__).parameters),
        ("lab_geracao.Recuperador.exigir_filtro", "exigir_filtro" in inspect.signature(geracao.Recuperador.__init__).parameters),
        ("lab_indexacao.IndiceBusca.consultar.filtro", "filtro" in inspect.signature(indexacao.IndiceBusca.consultar).parameters),
        ("lab_acesso.autorizar", hasattr(acesso, "autorizar") and hasattr(acesso, "PAPEL_CORRETOR")),
        ("lab_ingestao_l300.analisar_acesso", all(hasattr(l300, nome) for nome in ("analisar_acesso", "abrir_cliente",
                                                                                   "criar_credencial_gerenciada"))),
        ("l300.indice_e_container", l300.INDICE_PADRAO == INDICE and l300.CONTAINER_PADRAO == CONTAINER),
    )
    faltam = [nome for nome, presente in verificacoes if not presente]
    if faltam:
        raise ErroSonda("base_incompativel", USO, itens=faltam)


@contextlib.contextmanager
def sem_rede() -> Iterator[dict[str, int]]:
    """Qualquer tentativa de conexão ou de resolução de nome vira falha da etapa, mesmo que um tratamento de erro a esconda."""
    tentativas = {"n": 0}
    originais = {nome: getattr(socket, nome) for nome in ("getaddrinfo", "create_connection")}
    conectar = socket.socket.connect, socket.socket.connect_ex

    def negado(*_: Any, **__: Any) -> Any:
        tentativas["n"] += 1
        raise OSError("rede bloqueada")

    for nome in originais:
        setattr(socket, nome, negado)
    socket.socket.connect = socket.socket.connect_ex = negado  # type: ignore[method-assign, assignment]
    try:
        yield tentativas
    finally:
        for nome, original in originais.items():
            setattr(socket, nome, original)
        socket.socket.connect, socket.socket.connect_ex = conectar  # type: ignore[method-assign]


def etapa_validar(cfg: Configuracao, args: argparse.Namespace) -> Resultado:
    if cfg.invalidas:
        raise ErroSonda("configuracao_invalida", USO, invalidas=list(cfg.invalidas))
    if args.exigir_configuracao or cfg.obter("exigir_configuracao"):
        cfg.exigir(*_CHAVES_DO_AZURE)
    verificar_modulos()
    with sem_rede() as rede:
        saida = executar_cli(["--etapa", "validar"])
        aprovada, manifesto = saida.codigo == OK and bool(_VALIDACAO_OK.search(saida.texto)), None
        if aprovada:
            try:
                manifesto = mod.lab_ingestao_l300.carregar_e_validar()
            except mod.lab_comum.ErroLab:
                aprovada = False
    if rede["n"]:
        raise ErroSonda("rede_usada_no_validar", DIVERGENCIA, tentativas=rede["n"])
    if not aprovada:
        raise ErroSonda("manifesto_invalido", saida.codigo if saida.codigo in (USO, ACESSO, DIVERGENCIA, INESPERADO) else USO,
                        cli_codigo=saida.codigo)
    documentos = manifesto.documentos
    operacional = next((d for d in documentos if d.id == DOCUMENTO_OPERACIONAL and d.origem == mod.lab_ingestao_l300.ORIGEM_L300), None)
    if operacional is None:
        raise ErroSonda("documento_operacional_ausente", DIVERGENCIA)
    classes = mod.lab_acesso.CLASSES
    return Resultado("validar", OK, "aprovado", None, {
        "modulos": "ok", "rede": "bloqueada", "cli_codigo": saida.codigo,
        "documentos": {"total": len(documentos), "l100": sum(d.origem == "l100" for d in documentos),
                       "l300": sum(d.origem == "l300" for d in documentos),
                       "por_classe": {classe: sum(d.acesso == classe for d in documentos) for classe in classes}},
        "ids": [d.id for d in documentos], "operacional": operacional.id,
        "configuracao": {chave: "invalida" if chave in cfg.invalidas else "ausente" if chave in cfg.ausentes else "ok"
                         for chave in _CHAVES_DO_AZURE}})


def _rfc1918(texto: str) -> bool:
    try:
        endereco = ipaddress.ip_address(texto.split("%", 1)[0])
    except ValueError:
        return False
    if isinstance(endereco, ipaddress.IPv6Address) and endereco.ipv4_mapped is not None:
        endereco = endereco.ipv4_mapped
    return isinstance(endereco, ipaddress.IPv4Address) and any(endereco in rede for rede in _REDES_RFC1918)


def etapa_dns(cfg: Configuracao, args: argparse.Namespace) -> Resultado:
    cfg.exigir(*_EXIGENCIAS["dns"][0])
    nomes = {"blob": f"{cfg.obter('conta')}.{mod.lab_comum.SUFIXO_BLOB}",
             "busca": f"{cfg.obter('busca')}.{mod.lab_indexacao.SUFIXO_BUSCA}",
             "modelos": f"{cfg.obter('modelos')}.{mod.lab_indexacao.SUFIXO_MODELOS}"}
    relatorio: dict[str, Any] = {}
    sem_resolucao: list[str] = []
    fora_da_faixa: list[str] = []
    for rotulo, nome in nomes.items():
        try:
            enderecos = {info[4][0] for info in socket.getaddrinfo(nome, 443, type=socket.SOCK_STREAM)}
        except OSError:
            enderecos = set()
        privados = sum(_rfc1918(endereco) for endereco in enderecos)
        todos = bool(enderecos) and privados == len(enderecos)
        relatorio[rotulo] = {"resolvido": bool(enderecos), "enderecos": len(enderecos), "rfc1918": privados, "todos_rfc1918": todos}
        if not enderecos:
            sem_resolucao.append(rotulo)
        elif not todos:
            fora_da_faixa.append(rotulo)
    if sem_resolucao:
        raise ErroSonda("nome_nao_resolvido", ACESSO, dns=relatorio, rotulos=sem_resolucao)
    if fora_da_faixa:
        raise ErroSonda("endereco_fora_de_rfc1918", DIVERGENCIA, dns=relatorio, rotulos=fora_da_faixa)
    return Resultado("dns", OK, "aprovado", None, {"dns": relatorio, "todos_rfc1918": True})


def etapa_da_cli(etapa: str, cfg: Configuracao, args: argparse.Namespace) -> Resultado:
    obrigatorias, opcionais = _EXIGENCIAS[etapa]
    cfg.exigir(*obrigatorias, opcionais=opcionais)
    saida = executar_cli(argumentos_da_cli(etapa, cfg))
    dados: dict[str, Any] = {"cli_codigo": saida.codigo, **extrair(etapa, saida.texto)}
    com_indice = etapa in ("executar", "conferir")
    if saida.codigo != OK:
        marcadores = marcadores_de(saida.texto)
        codigo = saida.codigo if saida.codigo in (USO, ACESSO, DIVERGENCIA, INESPERADO) else INESPERADO
        if codigo == ACESSO:
            dados["servico"] = servico_de(saida.texto)
        if com_indice:
            anexar_o_indice(dados, cfg, com_indexador=etapa == "executar")
        raise ErroSonda(_causa_da_cli(saida.codigo, marcadores), codigo, marcadores=marcadores, **dados)
    if com_indice:
        anexar_o_indice(dados, cfg, com_indexador=etapa == "executar")
    try:
        _conferir_o_sucesso(etapa, dados, saida.texto, cfg)
    except ErroSonda as erro:
        erro.dados = {**dados, **erro.dados}
        raise
    return Resultado(etapa, OK, "aprovado", None, dados)


def etapa_resumo(cfg: Configuracao, args: argparse.Namespace) -> Resultado:
    cfg.exigir(*_EXIGENCIAS["resumo"][0])
    cliente = _cliente_de_busca(cfg)
    indice, indexador = resumir_indice(cliente), resumir_indexador(cliente)
    problemas = _inconsistencias_do_indice(indice)
    if problemas:
        raise ErroSonda("classes_inconsistentes", DIVERGENCIA, indice=indice, indexador=indexador, problemas=problemas)
    return Resultado("resumo", OK, "aprovado", None, {"indice": indice, "indexador": indexador})


# --------------------------------------------------------------------------------------
# Etapa acesso: Recuperador e ServicoRag reais, papéis estáticos, filtro e preFilter
# --------------------------------------------------------------------------------------

_FORA_DO_ID_DE_TRECHO = re.compile(r"[^A-Za-z0-9_=-]")  # o chat remove estes caracteres do id da evidência
_CONSULTAS = (("texto", "codigo", MARCADOR), ("texto", "pergunta", PERGUNTA), ("vetorial", "pergunta", PERGUNTA),
              ("hibrida", "pergunta", PERGUNTA))


def _instrumentar(objeto: Any, nome: str, ao_chamar: Callable[..., None], ao_voltar: Callable[[Any], None] | None = None) -> None:
    original = getattr(objeto, nome)

    def envolvida(*args: Any, **kwargs: Any) -> Any:
        ao_chamar(*args, **kwargs)
        resultado = original(*args, **kwargs)
        if ao_voltar is not None:
            ao_voltar(resultado)
        return resultado

    setattr(objeto, nome, envolvida)


def _resumo_da_consulta(resultados: Sequence[Mapping[str, Any]], contexto: Any, ids: Sequence[str]) -> dict[str, Any]:
    classes: dict[str, int] = {}
    documentos: dict[str, int] = {}
    for item in resultados:
        classe = item.get(mod.lab_acesso.CAMPO_ACESSO)
        if isinstance(classe, str) and classe in mod.lab_acesso.CLASSES:
            classes[classe] = classes.get(classe, 0) + 1
        documento = str(item.get("documento_id") or "")
        if documento in ids:
            documentos[documento] = documentos.get(documento, 0) + 1
    return {"resultados": len(resultados), "fora_do_perfil": sum(not contexto.permite(item) for item in resultados),
            "classes": classes, "documentos": documentos,
            "marcador": sum(MARCADOR.casefold() in str(item.get("conteudo") or "").casefold() for item in resultados),
            "operacional": sum(item.get("documento_id") == DOCUMENTO_OPERACIONAL for item in resultados)}


def _perguntar_ao_servico(servico: Any, contexto: Any) -> Any:
    chat, acesso = mod.lab_chat, mod.lab_acesso
    try:
        return servico.perguntar(PERGUNTA, contexto)
    except acesso.ErroAcesso as erro:
        raise ErroSonda("acesso_documental_violado", DIVERGENCIA, motivo=erro.causa) from None
    except ErroSonda:
        raise
    except Exception as erro:  # noqa: BLE001 - só o código público e a causa curta do chat são usados
        publico = chat.classificar_erro(erro)
        codigo = DIVERGENCIA if publico.codigo == chat.RESPOSTA_NAO_VERIFICADA else ACESSO
        raise ErroSonda("geracao_falhou", codigo, codigo_chat=publico.codigo, motivo=publico.causa) from None


def etapa_acesso(cfg: Configuracao, args: argparse.Namespace) -> Resultado:
    obrigatorias, opcionais = _EXIGENCIAS["acesso"]
    cfg.exigir(*obrigatorias, opcionais=opcionais)
    acesso, chat, geracao, politica = mod.lab_acesso, mod.lab_chat, mod.lab_geracao, mod.lab_politica
    config = chat.ConfiguracaoChat(
        modo=chat.MODO_NUVEM, exigir_autenticacao=True, client_id=cfg.obter("client_id"), busca=cfg.obter("busca"),
        modelos=cfg.obter("modelos"), indice=INDICE, deployment_embeddings=cfg.obter("deployment_embeddings"),
        dimensoes=cfg.obter("dimensoes"), deployment_geracao=cfg.obter("deployment_geracao"), esforco=cfg.obter("esforco"),
        modo_busca=geracao.MODO_PADRAO, k=geracao.K_PADRAO, exigir_acesso_documental=True)
    servico = chat.criar_servico_azure(config)
    recuperador = servico.recuperador
    documentos_busca = getattr(recuperador.indice, "_documentos", None)
    if documentos_busca is None:
        raise ErroSonda("base_incompativel", USO, itens=["lab_indexacao.IndiceBusca._documentos"])

    chamadas = {"embeddings": 0, "busca": 0, "geracao": 0}
    pedidos: list[dict[str, Any]] = []
    ultimos: dict[str, Any] = {"resultados": []}
    limite_de_geracao = {"valor": 0}  # só o passo 3 libera a única geração; antes disso, qualquer chamada ao modelo é barrada

    def contar(chave: str) -> Callable[..., None]:
        def conta(*_: Any, **__: Any) -> None:
            chamadas[chave] += 1

        return conta

    def contar_geracao(*_: Any, **__: Any) -> None:
        chamadas["geracao"] += 1
        if chamadas["geracao"] > limite_de_geracao["valor"]:
            raise ErroSonda("geracao_alem_do_limite", DIVERGENCIA, chamadas=dict(chamadas))

    def registrar_busca(*_: Any, **kwargs: Any) -> None:
        chamadas["busca"] += 1
        pedidos.append({"filtro": kwargs.get("filter"), "vetorial": bool(kwargs.get("vector_queries")),
                        "modo_do_filtro": kwargs.get("vector_filter_mode")})

    _instrumentar(recuperador.embeddings, "gerar", contar("embeddings"))
    _instrumentar(documentos_busca, "search", registrar_busca)
    _instrumentar(recuperador.indice, "consultar", lambda *a, **k: None, lambda resultados: ultimos.update(resultados=resultados))
    _instrumentar(servico.gerador, "gerar", contar_geracao)

    falhas: list[str] = []
    dados: dict[str, Any] = {}

    # 1. Sem contexto, sem filtro, com filtro inventado ou sem papel: a recusa vem antes de embeddings, busca e geração.
    def recusado(chamada: Callable[[], Any], tipo: type, motivo: str) -> bool:
        antes = dict(chamadas)
        try:
            chamada()
        except tipo as erro:
            return getattr(erro, "causa", None) == motivo and chamadas == antes
        except ErroSonda:  # a trava de geração disparou: a recusa não aconteceu antes do modelo
            return False
        return False

    recusas = {
        "sem_contexto": recusado(lambda: servico.perguntar(PERGUNTA, None), chat.ErroChat, "sem_contexto_de_acesso"),
        "sem_filtro": recusado(lambda: recuperador.recuperar(PERGUNTA, geracao.MODO_PADRAO, geracao.K_PADRAO),
                               acesso.ErroAcesso, "filtro_ausente"),
        "filtro_invalido": recusado(lambda: recuperador.recuperar(PERGUNTA, geracao.MODO_PADRAO, geracao.K_PADRAO,
                                                                  filtro="acesso eq 'atendimento'"),
                                    acesso.ErroAcesso, "filtro_invalido"),
        "sem_papel": recusado(lambda: acesso.autorizar(["Vareleira.Outro"]), acesso.ErroSemPapel, "sem_papel_conhecido"),
    }
    dados["recusa"] = {**recusas, "chamadas": dict(chamadas)}
    if not all(recusas.values()) or any(chamadas.values()):
        raise ErroSonda("recusa_nao_aplicada", DIVERGENCIA, **dados)

    # 2. Cada perfil, em cada modo de busca, só recebe as classes que os papéis estáticos permitem.
    atendimento, corretor = acesso.autorizar([acesso.PAPEL_ATENDIMENTO]), acesso.autorizar([acesso.PAPEL_CORRETOR])
    if not ("compartilhado" in atendimento.classes and "compartilhado" in corretor.classes
            and "corretor" not in atendimento.classes and "atendimento" not in corretor.classes):
        falhas.append("papeis_estaticos_inesperados")
    ids = [documento.id for documento in mod.lab_ingestao_l300.carregar_manifesto().documentos]
    perfis: dict[str, Any] = {}
    for rotulo, contexto in (("atendimento", atendimento), ("corretor", corretor)):
        consultas = []
        for modo, consulta, texto in _CONSULTAS:
            antes = len(pedidos)
            resultados = recuperador.recuperar(texto, modo, geracao.K_PADRAO, filtro=contexto.filtro).resultados
            enviados = pedidos[antes:]
            resumo = _resumo_da_consulta(resultados, contexto, ids)
            resumo.update(modo=modo, consulta=consulta, filtro=len(enviados) == 1 and enviados[0]["filtro"] == contexto.filtro,
                          pre_filtro=None if modo == "texto" else
                          len(enviados) == 1 and enviados[0]["modo_do_filtro"] == acesso.MODO_PRE_FILTRO)
            consultas.append(resumo)
            if len(enviados) != 1 or not resumo["filtro"]:
                falhas.append("filtro_nao_enviado")
            if resumo["pre_filtro"] is False:
                falhas.append("pre_filtro_ausente")
            if resumo["fora_do_perfil"]:
                falhas.append("resultado_fora_do_perfil")
            if modo != "texto" and not resumo["resultados"]:
                falhas.append("busca_vetorial_sem_resultados")
            if rotulo == "corretor" and (resumo["marcador"] or resumo["operacional"] or resumo["classes"].get("atendimento")):
                falhas.append("conteudo_interno_no_perfil_corretor")
            if rotulo == "atendimento" and modo == "texto" and consulta == "codigo" and not resumo["marcador"]:
                falhas.append("marcador_nao_recuperado")
        perfis[rotulo] = {"classes": list(contexto.classes), "consultas": consultas}
    dados["perfis"] = perfis

    # 3. No máximo uma geração real, no perfil Atendimento, e só se nada acima falhou: só invariantes, nunca o texto.
    if not cfg.obter("geracao"):
        dados["geracao"] = {"executada": False, "motivo": "desativada"}
    elif falhas:
        dados["geracao"] = {"executada": False, "motivo": "invariantes_anteriores_falharam"}
    else:
        limite_de_geracao["valor"] = 1
        resposta = _perguntar_ao_servico(servico, atendimento)
        por_id = {_FORA_DO_ID_DE_TRECHO.sub("", str(item.get("id"))): item for item in ultimos["resultados"]}
        evidencias = [por_id.get(evidencia.id) for evidencia in resposta.evidencias]

        def rastreavel(evidencia: Any, item: Mapping[str, Any] | None) -> bool:
            return (item is not None and bool(evidencia.citacao)
                    and politica.normalizar(evidencia.citacao) in politica.normalizar(str(item.get("conteudo") or "")))

        permitidas = all(item is not None and atendimento.permite(item) for item in evidencias)
        rastreaveis = all(rastreavel(evidencia, item) for evidencia, item in zip(resposta.evidencias, evidencias))
        dados["geracao"] = {
            "executada": True, "perfil": "atendimento", "tipo": resposta.tipo, "situacao": resposta.situacao,
            "evidencias": len(resposta.evidencias), "fontes_permitidas": permitidas, "citacoes_rastreaveis": rastreaveis,
            "cita_o_roteiro": any(item is not None and item.get("documento_id") == DOCUMENTO_OPERACIONAL for item in evidencias),
            "marcador_na_citacao": any(MARCADOR.casefold() in evidencia.citacao.casefold() for evidencia in resposta.evidencias),
            "tokens": resposta.uso.a_dict() if resposta.uso is not None else None}
        if resposta.situacao != politica.RESPONDIDA or not resposta.evidencias:
            falhas.append("geracao_sem_resposta_documentada")
        if not permitidas:
            falhas.append("fonte_fora_do_perfil")
        if not rastreaveis:
            falhas.append("citacao_nao_rastreavel")
        if chamadas["geracao"] != 1:
            falhas.append("geracao_chamadas_inesperadas")
    dados["chamadas"] = dict(chamadas)
    if falhas:
        raise ErroSonda(falhas[0], DIVERGENCIA, falhas=list(dict.fromkeys(falhas)), **dados)
    return Resultado("acesso", OK, "aprovado", None, dados)


# --------------------------------------------------------------------------------------
# Transporte HTTP: só HTTPS, só os destinos esperados, sem redirecionamento
# --------------------------------------------------------------------------------------

class SemRedirecionamento(urllib.request.HTTPRedirectHandler):
    """Um redirecionamento reenviaria o token ao novo endereço: nunca é seguido."""

    def redirect_request(self, *_: Any, **__: Any) -> None:
        return None


_ABRIDOR = urllib.request.build_opener(SemRedirecionamento)

# Os únicos hosts aos quais a sonda manda uma requisição (e, nas etapas autenticadas, um token): o chat, o Blob, a busca e o ARM.
_HOSTS_ESPERADOS = re.compile(
    r"[a-z0-9](?:[a-z0-9.-]{0,200}[a-z0-9])?\.azurecontainerapps\.io"
    r"|[a-z0-9]{3,24}\.blob\.core\.windows\.net"
    r"|[a-z0-9][a-z0-9-]{0,58}[a-z0-9]\.search\.windows\.net"
    r"|management\.azure\.com")


def exigir_destino_esperado(url: str) -> None:
    """Recusa, antes de qualquer conexão, o que não for HTTPS, tiver usuário, porta ou um host fora dos esperados."""
    partes = urllib.parse.urlsplit(url)
    try:
        porta = partes.port
    except ValueError:
        porta = -1
    if (partes.scheme != "https" or partes.username is not None or partes.password is not None or porta is not None
            or not partes.hostname or not _HOSTS_ESPERADOS.fullmatch(partes.hostname)):
        raise ErroSonda("destino_inesperado", USO)


def transporte_http(metodo: str, url: str, cabecalhos: Mapping[str, str], corpo: bytes | None,
                    tempo: float = TEMPO_DO_CHAT) -> tuple[int, bytes]:
    exigir_destino_esperado(url)
    pedido = urllib.request.Request(url, data=corpo, method=metodo, headers=dict(cabecalhos))
    try:
        with _ABRIDOR.open(pedido, timeout=tempo) as resposta:
            return resposta.status, resposta.read(LIMITE_DO_CORPO_HTTP)
    except urllib.error.HTTPError as erro:
        try:
            return erro.code, erro.read(LIMITE_DO_CORPO_HTTP)
        finally:
            erro.close()


# --------------------------------------------------------------------------------------
# Etapa http-interno (opcional): o chat pelo endereço do Azure Container Apps
# --------------------------------------------------------------------------------------

def principal_forjado(tenant: str | None = None) -> str:
    """Um X-MS-CLIENT-PRINCIPAL inventado, com o papel de Atendimento: quem não passou pela autenticação não pode usá-lo."""
    alvo = tenant if tenant and re.fullmatch(r"[0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}", tenant) else GUID_ZERO
    claims = [{"typ": "tid", "val": alvo}, {"typ": "oid", "val": GUID_ZERO}, {"typ": "roles", "val": mod.lab_acesso.PAPEL_ATENDIMENTO}]
    bruto = json.dumps({"auth_typ": "aad", "claims": claims, "name_typ": "name", "role_typ": "roles"})
    return base64.b64encode(bruto.encode("utf-8")).decode("ascii")


ESPERADO_SEM_CREDENCIAIS = {"principal_forjado": 401, "anonimo": 401, "healthz": 200, "readyz": 200}


def sondar_sem_credenciais(base: str, tenant: str | None = None) -> dict[str, int]:
    """Os quatro pedidos sem identidade: verificações de saúde e de prontidão (200), API anônima (401) e cabeçalho inventado (401).

    Os dois POSTs levam uma pergunta de verdade: se a plataforma não os recusar, o chat pode processá-los (embeddings e geração).
    """
    cabecalhos = {"Content-Type": "application/json", "Accept": "application/json"}
    corpo = json.dumps({"pergunta": PERGUNTA_DO_CHAT}).encode("utf-8")
    return {"healthz": transporte_http("GET", f"{base}/healthz", {}, None)[0],
            "readyz": transporte_http("GET", f"{base}/readyz", {}, None)[0],
            "anonimo": transporte_http("POST", f"{base}/api/perguntar", cabecalhos, corpo)[0],
            "principal_forjado": transporte_http("POST", f"{base}/api/perguntar",
                                                 {**cabecalhos, "X-MS-CLIENT-PRINCIPAL": principal_forjado(tenant)}, corpo)[0]}


def falhas_sem_credenciais(estados: Mapping[str, int]) -> list[str]:
    causas = {"principal_forjado": "principal_forjado_nao_negado", "anonimo": "anonimo_nao_negado",
              "healthz": "healthz_indisponivel", "readyz": "readyz_indisponivel"}
    return [causas[chave] for chave, esperado in ESPERADO_SEM_CREDENCIAIS.items() if estados.get(chave) != esperado]


ESPERADO_POR_PERFIL = {"atendimento": 200, "corretor": 200, "ambos": 200, "sem-acesso": 403}


def codigo_de_erro_do_chat(bruto: bytes) -> str | None:
    """O código público de um erro do chat ({"erro": <código>}), só se for do vocabulário dele; None para qualquer outra resposta."""
    try:
        dados = json.loads(bruto.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None
    codigo = dados.get("erro") if isinstance(dados, dict) else None
    return codigo if isinstance(codigo, str) and codigo in mod.lab_chat.MENSAGENS else None


def analisar_resposta_do_chat(bruto: bytes) -> dict[str, Any] | None:
    """Fatos fechados de uma resposta 200 do chat, ou None se ela não tem o formato esperado. O texto nunca é guardado.

    A pergunta usada (PERGUNTA_DO_CHAT) não traz o código nem o ID do roteiro: se um deles aparece na resposta, veio da recuperação,
    não de um eco da pergunta.
    """
    try:
        resposta = json.loads(bruto.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None
    tipos = {"tipo": str, "situacao": str, "texto": str, "evidencias": list}
    if not isinstance(resposta, dict) or not all(isinstance(resposta.get(nome), tipo) for nome, tipo in tipos.items()):
        return None
    politica = mod.lab_politica
    corpo = bruto.decode("utf-8", errors="replace").casefold()
    evidencias = [item for item in resposta["evidencias"] if isinstance(item, dict)]
    nomeia_o_roteiro = any("roteiro" in str(item.get(campo) or "").casefold() for item in evidencias
                           for campo in ("id", "fonte", "documento"))
    marcador = MARCADOR.casefold() in corpo
    situacoes = (politica.RESPONDIDA, politica.RECUSADA, politica.ESCLARECIMENTO)
    return {"tipo": resposta["tipo"] if resposta["tipo"] in politica.TIPOS else "desconhecido",
            "situacao": resposta["situacao"] if resposta["situacao"] in situacoes else "desconhecido",
            "evidencias": len(resposta["evidencias"]), "marcador": marcador,
            "operacional": marcador or DOCUMENTO_OPERACIONAL.casefold() in corpo or nomeia_o_roteiro}


def avaliar_resposta_do_perfil(perfil: str, estado: int, bruto: bytes) -> tuple[dict[str, Any], list[str]]:
    """O veredicto de UMA resposta do chat para o perfil da identidade. Não repete a pergunta nem ajusta nada para passar."""
    dados: dict[str, Any] = {}
    esperado = ESPERADO_POR_PERFIL[perfil]
    if estado != esperado:
        return dados, ["acesso_indevido" if esperado == 403 and estado == 200 else "http_inesperado"]
    if estado != 200:
        dados["chat"] = codigo_de_erro_do_chat(bruto)  # distingue a recusa do chat da recusa da plataforma
        return dados, []
    fatos = analisar_resposta_do_chat(bruto)
    if fatos is None:
        return dados, ["resposta_fora_do_formato"]
    dados["resposta"] = fatos
    falhas: list[str] = []
    if "desconhecido" in (fatos["tipo"], fatos["situacao"]):
        falhas.append("resposta_fora_do_vocabulario")
    if perfil == "corretor" and fatos["operacional"]:
        falhas.append("conteudo_interno_no_perfil_corretor")
    if perfil in ("atendimento", "ambos"):
        if (fatos["tipo"], fatos["situacao"]) != ("documentada", mod.lab_politica.RESPONDIDA):
            falhas.append("classificacao_divergente")
        elif not fatos["operacional"]:
            falhas.append("fonte_operacional_ausente")
    return dados, falhas


def etapa_http_interno(cfg: Configuracao, args: argparse.Namespace) -> Resultado:
    obrigatorias, opcionais = _EXIGENCIAS["http-interno"]
    cfg.exigir(*obrigatorias, opcionais=opcionais)
    base, perfil = cfg.obter("url"), cfg.obter("perfil")
    estados: dict[str, Any] = dict(sondar_sem_credenciais(base))
    credencial = mod.lab_ingestao_l300.criar_credencial_gerenciada(cfg.obter("client_id"))
    token = credencial.get_token(f"api://{cfg.obter('app_id')}/.default").token
    cabecalhos = {"Content-Type": "application/json", "Accept": "application/json", "Authorization": f"Bearer {token}"}
    del token
    estados["autenticado"], bruto = transporte_http("POST", f"{base}/api/perguntar", cabecalhos,
                                                    json.dumps({"pergunta": PERGUNTA_DO_CHAT}).encode("utf-8"))
    del cabecalhos
    do_perfil, falhas_do_perfil = avaliar_resposta_do_perfil(perfil, estados["autenticado"], bruto)
    dados: dict[str, Any] = {"perfil": perfil, "estados": estados, **do_perfil}
    falhas = [*falhas_sem_credenciais(estados), *falhas_do_perfil]
    if falhas:
        raise ErroSonda(falhas[0], DIVERGENCIA, falhas=falhas, **dados)
    return Resultado("http-interno", OK, "aprovado", None, dados)


# --------------------------------------------------------------------------------------
# Etapa negativas-mi: o que a identidade do chat NÃO pode fazer, visto de dentro da rede
# --------------------------------------------------------------------------------------

def estado_http(url: str, cabecalhos: Mapping[str, str]) -> int:
    """Só o código HTTP de um GET: o corpo da resposta (que pode trazer identificadores do ambiente) nunca é lido nem guardado."""
    exigir_destino_esperado(url)
    pedido = urllib.request.Request(url, method="GET", headers=dict(cabecalhos))
    try:
        with _ABRIDOR.open(pedido, timeout=TEMPO_HTTP) as resposta:
            return resposta.status
    except urllib.error.HTTPError as erro:
        erro.close()
        return erro.code


def _identidade_do_token(token: str, client_id: str) -> str:
    """Confere, só em memória, se o token é da identidade escolhida (claim appid ou azp). Nenhum conteúdo do token sai daqui."""
    try:
        carga = token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(carga + "=" * (-len(carga) % 4)))
    except (IndexError, ValueError):
        return "indeterminada"
    dono = claims.get("appid") or claims.get("azp") if isinstance(claims, dict) else None
    if not isinstance(dono, str):
        return "indeterminada"
    return "confere" if dono.lower() == client_id.lower() else "diferente"


def etapa_negativas_mi(cfg: Configuracao, args: argparse.Namespace) -> Resultado:
    """Com a identidade do chat (escolhida por VARELEIRA_PROBE_CLIENT_ID), cada chamada abaixo deve devolver exatamente 403.

    Os três pedidos saem da própria rede do ambiente: um 403 prova que o papel falta, e não que a rede bloqueou. Com a identidade
    da sonda (que tem papéis de carga e administração) eles seriam 2xx, e a sonda reprova com `permissao_excessiva`.
    """
    obrigatorias, opcionais = _EXIGENCIAS["negativas-mi"]
    cfg.exigir(*obrigatorias, opcionais=opcionais)
    conta, busca, client_id = cfg.obter("conta"), cfg.obter("busca"), cfg.obter("client_id")
    recurso = (f"/subscriptions/{cfg.obter('assinatura')}/resourceGroups/{cfg.obter('grupo')}"
               f"/providers/Microsoft.Storage/storageAccounts/{conta}")
    pedidos = (
        ("blob", ESCOPO_BLOB, {"x-ms-version": VERSAO_DO_BLOB},
         f"https://{conta}.{mod.lab_comum.SUFIXO_BLOB}/{mod.lab_comum.CONTAINER_PADRAO}?restype=container&comp=list&maxresults=1"),
        ("busca", mod.lab_ingestao.ESCOPO_BUSCA, {},
         f"https://{busca}.{mod.lab_indexacao.SUFIXO_BUSCA}/indexes?api-version={mod.lab_ingestao.VERSAO_API}"),
        ("arm", ESCOPO_ARM, {}, f"https://management.azure.com{recurso}?api-version={VERSAO_DA_API_DO_ARM}"),
    )
    credencial = mod.lab_ingestao_l300.criar_credencial_gerenciada(client_id)
    estados: dict[str, Any] = {}
    identidades: list[str] = []
    for rotulo, escopo, extras, url in pedidos:
        try:
            token = credencial.get_token(escopo).token
        except Exception:  # noqa: BLE001 - só o fato de o token não ter sido emitido interessa, nunca o texto do erro
            estados[rotulo] = "erro_de_token"
            continue
        identidades.append(_identidade_do_token(token, client_id))
        try:
            estados[rotulo] = estado_http(url, {"Authorization": f"Bearer {token}", "Accept": "application/json", **extras})
        except OSError:
            estados[rotulo] = "erro_de_rede"
        finally:
            del token
    identidade = "diferente" if "diferente" in identidades else "confere" if "confere" in identidades else "indeterminada"
    dados: dict[str, Any] = {"esperado": 403, "estados": estados, "identidade": identidade}

    def em(selecao: Callable[[Any], bool]) -> list[str]:
        return [rotulo for rotulo, estado in estados.items() if selecao(estado)]

    liberadas = em(lambda estado: isinstance(estado, int) and 200 <= estado < 300)
    if identidade == "diferente":
        raise ErroSonda("identidade_diferente", DIVERGENCIA, **dados)
    if liberadas:
        raise ErroSonda("permissao_excessiva", DIVERGENCIA, rotulos=liberadas, **dados)
    if em(lambda estado: estado == "erro_de_token"):
        raise ErroSonda("token_indisponivel", ACESSO, rotulos=em(lambda estado: estado == "erro_de_token"), **dados)
    if em(lambda estado: estado == "erro_de_rede"):
        raise ErroSonda("rede", ACESSO, rotulos=em(lambda estado: estado == "erro_de_rede"), **dados)
    inesperados = em(lambda estado: estado != 403)
    if inesperados:
        raise ErroSonda("negativa_inconclusiva", DIVERGENCIA, rotulos=inesperados, **dados)
    return Resultado("negativas-mi", OK, "aprovado", None, dados)


ETAPAS_DA_SONDA: dict[str, Callable[[Configuracao, argparse.Namespace], Resultado]] = {
    "validar": etapa_validar, "dns": etapa_dns, "resumo": etapa_resumo, "acesso": etapa_acesso, "http-interno": etapa_http_interno,
    "negativas-mi": etapa_negativas_mi,
    **{nome: (lambda cfg, args, nome=nome: etapa_da_cli(nome, cfg, args))
       for nome in ("carregar", "criar", "executar", "conferir", "excluir", "restaurar")},
}


# --------------------------------------------------------------------------------------
# Entrada
# --------------------------------------------------------------------------------------

_sair: Callable[[int], Any] = os._exit


class ParserDaSonda(argparse.ArgumentParser):
    """Um erro de uso vira uma linha sentinela (`uso_invalido`), sem ecoar o argumento recebido nem imprimir a ajuda do argparse."""

    def error(self, mensagem: str) -> Any:  # type: ignore[override]
        raise ErroSonda("uso_invalido", USO)


def _ler_argumentos(argv: Sequence[str] | None, ambiente: Mapping[str, str]) -> argparse.Namespace:
    parser = ParserDaSonda(add_help=False, allow_abbrev=False)
    parser.add_argument("--etapa", choices=ETAPAS)
    parser.add_argument("--exigir-configuracao", action="store_true")
    args = parser.parse_args(None if argv is None else list(argv))
    da_variavel = (ambiente.get("VARELEIRA_PROBE_ETAPA") or "").strip() or None
    if da_variavel is not None and da_variavel not in ETAPAS:
        raise ErroSonda("etapa_desconhecida", USO)
    if args.etapa and da_variavel and args.etapa != da_variavel:
        raise ErroSonda("etapa_conflitante", USO)
    args.etapa = args.etapa or da_variavel
    if not args.etapa:
        raise ErroSonda("etapa_ausente", USO)
    return args


def _limite_da_etapa(etapa: str, cfg: Configuracao) -> int:
    if cfg.obter("limite"):
        return cfg.obter("limite")
    if etapa == "executar":
        return min(LIMITE_MAXIMO, cfg.obter("espera") + MARGEM_DO_INDEXADOR)
    return LIMITES_POR_ETAPA.get(etapa, LIMITE_PADRAO)


def principal(argv: Sequence[str] | None = None, ambiente: Mapping[str, str] | None = None, saida: Any = None) -> int:
    ambiente = os.environ if ambiente is None else ambiente
    emissor = Emissor(saida if saida is not None else sys.stdout)
    inicio = time.monotonic()
    etapa: str | None = None
    privados: tuple[str, ...] = ()
    vigia: threading.Timer | None = None
    logging.disable(logging.CRITICAL)
    try:
        # Nada além da linha sentinela chega ao stdout ou ao stderr, nem por bibliotecas.
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            try:
                args = _ler_argumentos(argv, ambiente)
                etapa = args.etapa
                cfg = Configuracao(ambiente)
                privados = cfg.privados()
                limite = _limite_da_etapa(etapa, cfg)

                def estourou() -> None:
                    emissor.emitir(Resultado(etapa, ACESSO, "erro", "tempo_da_sonda_esgotado", {"limite_s": limite},
                                             round(time.monotonic() - inicio, 1)), privados)
                    _sair(emissor.codigo)

                vigia = threading.Timer(limite, estourou)
                vigia.daemon = True
                vigia.start()
                resultado = ETAPAS_DA_SONDA[etapa](cfg, args)
            except BaseException as erro:  # noqa: BLE001 - qualquer saída precisa virar uma linha sentinela
                falha = classificar_excecao(erro)
                resultado = Resultado(etapa, falha.codigo, falha.veredicto, falha.causa, falha.dados)
    finally:
        if vigia is not None:
            vigia.cancel()
        logging.disable(logging.NOTSET)
    resultado.duracao_s = round(time.monotonic() - inicio, 1)
    emissor.emitir(resultado, privados)
    return emissor.codigo  # o da linha realmente emitida: se a barreira a trocou, 4


if __name__ == "__main__":
    sys.exit(principal())
