"""Avalia o contrato HTTP do chat do L200 (Desafio 06): uma pergunta por caso, em sequência, sem repetir e sem guardar texto.

Cada caso do arquivo vira um POST em /api/perguntar com o JSON {"pergunta": ...}. O avaliador confere, literalmente, o tipo e a
situação esperados e os invariantes da apresentação: em contratação individual, o texto e o aviso fixos da política e ao menos
uma citação; em resposta documentada, ao menos uma citação; em recusa, nenhuma. Falha de HTTP, de transporte ou de formato é
uma falha registrada, nunca uma resposta aprovada. Ele avalia o contrato e a apresentação do chat, não a fidelidade das respostas.

Sem --executar, só valida o arquivo de casos, o endereço, a presença das credenciais e o caminho do relatório, e mostra o plano:
nada é enviado e nenhum relatório é criado. Com --executar, o relatório é criado antes de qualquer acesso à rede, nunca
sobrescreve um arquivo e não guarda perguntas, textos, citações, o endereço do destino nem identificadores. Do servidor, só
entram no relatório valores de vocabulários fechados (tipo, situação, códigos de erro) e contagens. O uso de tokens só aparece
quando o chat o informa: respostas de erro não informam, então o consumo delas é desconhecido (não zero) e a soma é parcial.
O arquivo de casos, o avaliador e os módulos têm dois SHA-256, sempre com o nome do que medem: o dos bytes exatos do disco e o
do texto com CRLF trocado por LF, que não muda entre o Windows e o Git. Os metadados do arquivo de casos (nome, origem e
configuracao_avaliada) são gravados como vieram: a configuração não é conferida com o serviço, e um marcador como "a congelar
antes da execução" é aceito (o congelamento efetivo fica em um registro separado).

Destino: HTTPS só para o endereço padrão do Azure Container Apps (*.azurecontainerapps.io; domínios personalizados ficam fora
desta versão), com a identidade de teste (ClientSecretCredential, não um login de pessoa) lida de VARELEIRA_AVALIACAO_TENANT,
VARELEIRA_AVALIACAO_CLIENT_ID e VARELEIRA_AVALIACAO_SEGREDO; o token é para api://<ID do aplicativo>/.default e só é pedido
depois que o endereço é aceito. HTTP só em 127.0.0.1, localhost ou ::1, sem autenticação: é uma demonstração ou um uso local,
marcado assim no relatório. O endereço não pode ter usuário, senha, caminho, parâmetros nem fragmento, e redirecionamentos
nunca são seguidos.

Limites: 100 casos, 120 s por chamada, 128 KiB por resposta, 25 minutos no total e 3 falhas de transporte seguidas; os casos
que sobram ficam como não avaliados. O avaliador não repete chamadas e não altera o TLS nem as tentativas do chat. Uma resposta
503 (inclusive a de resposta descartada pela política) é o resultado daquele caso: ele falha, a execução segue.

Códigos de saída: 0 todos os casos passaram (ou a simulação foi válida); 1 uso ou entrada inválida; 2 token ou autenticação
recusados; 3 divergência, falha de HTTP ou de transporte, ou casos não avaliados; 4 defeito do avaliador.

Exemplos:
    python scripts\\avaliar_chat.py --casos <casos.json> --url http://127.0.0.1:8000 --relatorio <novo.json>
    python scripts\\avaliar_chat.py --casos <casos.json> --url https://<app>.<ambiente>.<regiao>.azurecontainerapps.io --relatorio <novo.json> --executar
"""

from __future__ import annotations

import argparse
import datetime as dt
import http.client
import json
import logging
import os
import re
import ssl
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping

import lab_chat
import lab_comum
import lab_politica
from lab_comum import ErroLab

VERSAO_DO_ESQUEMA = 1
VERSAO_DO_AVALIADOR = 1
CAMINHO_DA_API = "/api/perguntar"
USER_AGENT = f"vareleira-avaliar-chat/{VERSAO_DO_AVALIADOR}"

MAXIMO_DE_CASOS = 100
LIMITE_DO_ARQUIVO = 1024 * 1024  # bytes
LIMITE_DA_RESPOSTA = 128 * 1024  # bytes
TIMEOUT_DA_CHAMADA = 120.0  # segundos
TEMPO_MAXIMO = 25 * 60.0  # segundos, do primeiro ao último caso
FALHAS_DE_TRANSPORTE_SEGUIDAS = 3
MAXIMO_DE_PROBLEMAS_MOSTRADOS = 25

VAR_TENANT = "VARELEIRA_AVALIACAO_TENANT"
VAR_CLIENT_ID = "VARELEIRA_AVALIACAO_CLIENT_ID"
VAR_SEGREDO = "VARELEIRA_AVALIACAO_SEGREDO"
HOSTS_LOCAIS = frozenset({"127.0.0.1", "localhost", "::1"})
DOMINIO_DO_CONTAINER_APPS = ".azurecontainerapps.io"  # o endereço padrão do L200; domínios personalizados ficam fora desta versão
MAXIMO_DE_TOKENS = 10**9  # por contagem e por resposta: acima disso o valor não é plausível e a resposta é recusada
ARQUIVOS_DO_CODIGO = ("lab_comum.py", "lab_acesso.py", "lab_indexacao.py", "lab_geracao.py", "lab_politica.py", "lab_chat.py",
                      "lab_orquestracao.py", "chat_web.py")  # os módulos que o contêiner copia: o chat importa o lab_acesso mesmo sem o acesso documental, e o lab_orquestracao (L400) mesmo sem a coordenação

SITUACOES = (lab_politica.RESPONDIDA, lab_politica.RECUSADA, lab_politica.ESCLARECIMENTO)
SITUACAO_POR_TIPO = {
    lab_politica.DOCUMENTADA: lab_politica.RESPONDIDA,
    lab_politica.CONTRATACAO_INDIVIDUAL: lab_politica.RESPONDIDA,
    lab_politica.AMBIGUA: lab_politica.ESCLARECIMENTO,
    lab_politica.SEM_EVIDENCIA: lab_politica.RECUSADA,
    lab_politica.FORA_DE_ESCOPO: lab_politica.RECUSADA,
}

APROVADO, DIVERGENTE, FALHA_HTTP, ERRO, NAO_AVALIADO = "aprovado", "divergente", "falha_http", "erro", "nao_avaliado"
TEMPO_MAXIMO_EXCEDIDO = "tempo_maximo"
FALHAS_DE_TRANSPORTE = "falhas_de_transporte"
FALHA_DE_AUTENTICACAO = "falha_de_autenticacao"
CANCELADO = "cancelado"
DEFEITO_DO_AVALIADOR = "defeito_do_avaliador"
ESCOPO_DA_CONTAGEM = ("só as chamadas HTTP do avaliador ao chat; as tentativas internas do chat aos modelos e à busca "
                      "não são visíveis aqui")
OBSERVACAO_DO_USO = ("Soma só do uso que o chat informou em respostas 200. Respostas de erro (inclusive o 503 de resposta descartada), "
                     "falhas de transporte e respostas sem o campo de uso não informam o consumo: ele é desconhecido, não zero. "
                     "Não é o total consumido nem o custo.")
SIGNIFICADO_DOS_HASHES = {
    "sha256_bytes_brutos": "SHA-256 dos bytes exatos do arquivo, como estão no disco (com CRLF ou LF)",
    "sha256_normalizado_lf": "SHA-256 do mesmo arquivo com CRLF trocado por LF: não muda entre o Windows e o Git",
}
NOTA_DA_CONFIGURACAO = ("Texto informado pelo autor do arquivo de casos e gravado como veio; o avaliador não o confere com o serviço. "
                        "Se for um marcador de configuração ainda por congelar, o congelamento efetivo fica em um registro separado, "
                        "fora deste relatório.")
DESCRICAO_DA_INTERRUPCAO = {
    TEMPO_MAXIMO_EXCEDIDO: "o tempo máximo de 25 minutos acabou",
    FALHAS_DE_TRANSPORTE: f"{FALHAS_DE_TRANSPORTE_SEGUIDAS} falhas de transporte seguidas",
    FALHA_DE_AUTENTICACAO: "não foi possível obter o token da identidade de teste",
    CANCELADO: "a execução foi cancelada",
    DEFEITO_DO_AVALIADOR: "defeito do avaliador",
}

# O chat acrescenta o id do navegador e o id da requisição ao que a política devolve: os nomes vêm da própria resposta pública.
_CAMPOS_DO_TRANSPORTE = frozenset({"id", "id_requisicao"})
_RESPOSTA_PUBLICA = lab_chat.RespostaChat(lab_politica.DOCUMENTADA, lab_politica.RESPONDIDA, "x", "").a_dict()
CAMPOS_DA_RESPOSTA = frozenset(_RESPOSTA_PUBLICA) | _CAMPOS_DO_TRANSPORTE
CAMPOS_DA_EVIDENCIA = frozenset(lab_chat.EvidenciaChat("a", "b", "c", "d", "e", "f", "g").a_dict())
CAMPOS_DO_USO = frozenset(lab_chat.UsoChat().a_dict())
TEXTO_INDIVIDUAL = lab_chat.limpar_texto(lab_politica.TEXTO_SEM_VEREDITO, lab_chat.LIMITE_DO_TEXTO)
AVISO_INDIVIDUAL = lab_chat.limpar_texto(lab_politica.AVISO_CONTRATACAO_INDIVIDUAL, lab_chat.LIMITE_DO_AVISO)

_CAMPOS_DA_ENTRADA = ("schema_version", "nome", "origem", "configuracao_avaliada", "casos")
_CAMPOS_DO_CASO = ("id", "categoria", "tipo_esperado", "situacao_esperada", "pergunta", "justificativa", "evidencias_referencia")
_CAMPOS_DA_REFERENCIA = ("documento_id", "citacao")
_PADRAO_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,59}")
_PADRAO_DOCUMENTO = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,59}")
_PADRAO_NOME_DE_CAMPO = re.compile(r"[A-Za-z0-9_$.-]{1,40}")
_PADRAO_ESQUEMA_DE_URL = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://")
_PADRAO_GUID = re.compile(r"[0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}")
_PADRAO_HOST = re.compile(r"(?=.{1,253}$)[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*")
_PADRAO_TOKEN = re.compile(r"[A-Za-z0-9._~+/=-]{20,8192}")
_PADRAO_CODIGO_ENTRA = re.compile(r"AADSTS(\d{4,7})")
_CATEGORIAS_DE_CONTROLE = frozenset({"Cc", "Cs", "Co", "Cn", "Zl", "Zp"})


# --------------------------------------------------------------------------------------
# Entrada
# --------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Caso:
    id: str
    categoria: str
    tipo_esperado: str
    situacao_esperada: str
    pergunta: str


@dataclass(frozen=True)
class Entrada:
    nome: str
    origem: str
    configuracao_avaliada: str
    casos: tuple[Caso, ...]
    sha256_bytes_brutos: str
    sha256_normalizado_lf: str
    campos_ignorados: tuple[str, ...] = ()


def hash_normalizado(dados: bytes) -> str:
    """SHA-256 com quebras de linha LF: o mesmo valor no Windows e no Git."""
    return lab_comum.calcular_sha256(lab_comum.normalizar_texto(dados))


def hashes_do_conteudo(dados: bytes) -> dict[str, str]:
    """Os dois SHA-256 do mesmo arquivo, cada um com o nome do que mede: os bytes exatos do disco e o texto com CRLF trocado por LF."""
    return {"sha256_bytes_brutos": lab_comum.calcular_sha256(dados), "sha256_normalizado_lf": hash_normalizado(dados)}


def _sem_repeticoes(pares: list[tuple[str, Any]]) -> dict[str, Any]:
    dados: dict[str, Any] = {}
    for chave, valor in pares:
        if chave in dados:
            raise ValueError("chave repetida")
        dados[chave] = valor
    return dados


def _texto_valido(valor: Any, maximo: int, quebras: bool = False) -> bool:
    if not isinstance(valor, str) or not 1 <= len(valor.strip()) <= maximo:
        return False
    return all((quebras and letra in "\n\t\r") or unicodedata.category(letra) not in _CATEGORIAS_DE_CONTROLE for letra in valor)


def _sem_endereco_nem_identificador(valor: str) -> bool:
    return not _PADRAO_ESQUEMA_DE_URL.search(valor) and not _PADRAO_GUID.search(valor)


def _validar_referencias(referencias: Any, onde: str, problemas: list[str]) -> None:
    if not isinstance(referencias, list) or len(referencias) > 20:
        problemas.append(f"{onde}: evidencias_referencia deve ser uma lista de até 20 itens.")
        return
    for posicao, item in enumerate(referencias):
        if not isinstance(item, dict) or any(chave not in item for chave in _CAMPOS_DA_REFERENCIA):
            problemas.append(f"{onde}: evidencias_referencia[{posicao}] precisa de documento_id e citacao.")
        elif not (isinstance(item["documento_id"], str) and _PADRAO_DOCUMENTO.fullmatch(item["documento_id"])
                  and _texto_valido(item["citacao"], 2000, quebras=True)):
            problemas.append(f"{onde}: evidencias_referencia[{posicao}] tem documento_id ou citacao inválidos.")


def _validar_caso(bruto: Any, posicao: int, problemas: list[str], ignorados: set[str]) -> Caso | None:
    onde = f"casos[{posicao}]"
    if not isinstance(bruto, dict):
        problemas.append(f"{onde}: cada caso deve ser um objeto.")
        return None
    faltam = [campo for campo in _CAMPOS_DO_CASO if campo not in bruto]
    if faltam:
        problemas.append(f"{onde}: faltam campos: {', '.join(faltam)}.")
        return None
    ignorados.update(campo for campo in bruto if campo not in _CAMPOS_DO_CASO)
    antes = len(problemas)
    identificador = bruto["id"]
    if not (isinstance(identificador, str) and _PADRAO_ID.fullmatch(identificador)):
        problemas.append(f"{onde}: id deve ter de 1 a 60 caracteres: letras, números, ponto, hífen e sublinhado.")
    else:
        onde = f"caso {identificador}"
    if not _texto_valido(bruto["categoria"], 40):
        problemas.append(f"{onde}: categoria deve ser um texto de até 40 caracteres.")
    elif not _sem_endereco_nem_identificador(bruto["categoria"]):
        problemas.append(f"{onde}: categoria não pode ter endereços nem identificadores do ambiente: o relatório guarda este texto.")
    tipo, situacao = bruto["tipo_esperado"], bruto["situacao_esperada"]
    if tipo not in lab_politica.TIPOS:
        problemas.append(f"{onde}: tipo_esperado deve ser um de: {', '.join(lab_politica.TIPOS)}.")
    if situacao not in SITUACOES:
        problemas.append(f"{onde}: situacao_esperada deve ser uma de: {', '.join(SITUACOES)}.")
    if (isinstance(tipo, str) and isinstance(situacao, str) and tipo in SITUACAO_POR_TIPO and situacao in SITUACOES
            and situacao != SITUACAO_POR_TIPO[tipo]):
        problemas.append(f"{onde}: o tipo {tipo} só pode terminar em {SITUACAO_POR_TIPO[tipo]} "
                         "(contratação individual é respondida, não recusada).")
    pergunta = bruto["pergunta"]
    if not isinstance(pergunta, str):
        problemas.append(f"{onde}: pergunta deve ser um texto.")
    else:
        try:  # o mesmo critério do chat: limite, caracteres de controle e texto vazio
            lab_chat.ler_pedido(json.dumps({"pergunta": pergunta}).encode("utf-8"), "application/json")
        except lab_chat.ErroChat as erro:
            problemas.append(f"{onde}: pergunta recusada pelo chat ({erro.codigo}).")
    if not _texto_valido(bruto["justificativa"], 1000, quebras=True):
        problemas.append(f"{onde}: justificativa deve ser um texto de até 1000 caracteres.")
    _validar_referencias(bruto["evidencias_referencia"], onde, problemas)
    if len(problemas) > antes:
        return None
    return Caso(identificador, bruto["categoria"].strip(), tipo, situacao, pergunta)


def _validar_entrada(dados: Any, bruto: bytes) -> Entrada:
    problemas: list[str] = []
    ignorados: set[str] = set()
    if not isinstance(dados, dict):
        raise ErroLab("O arquivo de casos deve conter um objeto JSON.")
    faltam = [campo for campo in _CAMPOS_DA_ENTRADA if campo not in dados]
    if faltam:
        raise ErroLab(f"O arquivo de casos não tem os campos: {', '.join(faltam)}.")
    ignorados.update(campo for campo in dados if campo not in _CAMPOS_DA_ENTRADA)
    versao = dados["schema_version"]
    if isinstance(versao, bool) or versao != VERSAO_DO_ESQUEMA or not isinstance(versao, int):
        problemas.append(f"schema_version deve ser o número inteiro {VERSAO_DO_ESQUEMA}.")
    for campo, maximo in (("nome", 120), ("origem", 1000), ("configuracao_avaliada", 500)):
        if not _texto_valido(dados[campo], maximo):
            problemas.append(f"{campo} deve ser um texto de até {maximo} caracteres.")
        elif not _sem_endereco_nem_identificador(dados[campo]):
            problemas.append(f"{campo} não pode ter endereços nem identificadores do ambiente: o relatório guarda este texto.")
    brutos = dados["casos"]
    casos: list[Caso] = []
    if not isinstance(brutos, list) or not 1 <= len(brutos) <= MAXIMO_DE_CASOS:
        problemas.append(f"casos deve ser uma lista de 1 a {MAXIMO_DE_CASOS} itens.")
    else:
        vistos: dict[str, int] = {}
        for posicao, caso_bruto in enumerate(brutos):
            caso = _validar_caso(caso_bruto, posicao, problemas, ignorados)
            if caso is None:
                continue
            if caso.id.casefold() in vistos:
                problemas.append(f"caso {caso.id}: id repetido (também em casos[{vistos[caso.id.casefold()]}]; maiúsculas "
                                 "e minúsculas contam como iguais).")
            vistos.setdefault(caso.id.casefold(), posicao)
            casos.append(caso)
    if problemas:
        mostrados = "\n".join(f"  - {problema}" for problema in problemas[:MAXIMO_DE_PROBLEMAS_MOSTRADOS])
        resto = len(problemas) - MAXIMO_DE_PROBLEMAS_MOSTRADOS
        mais = f"\n  ... e mais {resto} problema(s)." if resto > 0 else ""
        raise ErroLab(f"O arquivo de casos não passou na validação ({len(problemas)} problema(s)). Nada foi enviado.\n"
                      f"{mostrados}{mais}")
    nomes = tuple(sorted(campo if _PADRAO_NOME_DE_CAMPO.fullmatch(campo) else "(nome fora do padrão)" for campo in ignorados))
    hashes = hashes_do_conteudo(bruto)
    return Entrada(dados["nome"].strip(), dados["origem"].strip(), dados["configuracao_avaliada"].strip(), tuple(casos),
                   hashes["sha256_bytes_brutos"], hashes["sha256_normalizado_lf"], nomes)


def carregar_entrada(caminho: Path) -> Entrada:
    """Lê e valida o arquivo de casos antes de qualquer acesso à rede. Os campos desconhecidos são ignorados, com aviso."""
    try:
        if not caminho.is_file():
            raise ErroLab("O arquivo de casos (--casos) não foi encontrado.")
        if caminho.stat().st_size > LIMITE_DO_ARQUIVO:
            raise ErroLab(f"O arquivo de casos tem mais de {LIMITE_DO_ARQUIVO // 1024} KiB.")
        bruto = caminho.read_bytes()
    except OSError:
        raise ErroLab("Não foi possível ler o arquivo de casos (--casos).") from None
    try:
        dados = json.loads(bruto.decode("utf-8-sig"), object_pairs_hook=_sem_repeticoes)
    except (ValueError, RecursionError):
        raise ErroLab("O arquivo de casos não é um JSON válido: use UTF-8 e não repita chaves.") from None
    return _validar_entrada(dados, bruto)


# --------------------------------------------------------------------------------------
# Destino, credenciais e relatório
# --------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Destino:
    """Endereço base. Nunca é impresso nem gravado: só o tipo (HTTPS ou loopback) aparece nas saídas."""

    base: str = field(repr=False)
    https: bool


def validar_destino(url: str) -> Destino:
    invalido = ErroLab("O endereço (--url) é inválido. Use o endereço padrão do chat hospedado (https://<aplicativo>...azurecontainerapps.io) "
                       "ou, só para um chat local, http://127.0.0.1:<porta>, sem usuário, senha, caminho, parâmetros nem fragmento.")
    if not url or not url.isascii() or any(ord(letra) <= 32 or ord(letra) == 127 for letra in url):
        raise invalido
    try:
        partes = urllib.parse.urlsplit(url)
        porta = partes.port
    except ValueError:
        raise invalido from None
    host = (partes.hostname or "").lower()
    if partes.scheme not in ("https", "http") or not host or "@" in partes.netloc or partes.query or "?" in url or partes.fragment \
            or "#" in url or ";" in url or partes.path not in ("", "/") or (porta is not None and not 1 <= porta <= 65535):
        raise invalido
    if partes.scheme == "http":
        if host not in HOSTS_LOCAIS:
            raise ErroLab("HTTP só é aceito em 127.0.0.1, localhost ou ::1 (demonstração ou uso local). Use HTTPS para o chat hospedado.")
    elif not (host.endswith(DOMINIO_DO_CONTAINER_APPS) and _PADRAO_HOST.fullmatch(host)):
        raise ErroLab("HTTPS só é aceito para o endereço padrão do Azure Container Apps (*.azurecontainerapps.io); domínios "
                      "personalizados ficam fora desta versão. Nenhum token foi pedido. Para um chat local, use http://127.0.0.1:<porta>.")
    return Destino(f"{partes.scheme}://{partes.netloc.lower()}", partes.scheme == "https")


@dataclass(frozen=True)
class Credenciais:
    """A identidade de teste. Só existe em memória e nunca aparece em uma saída."""

    tenant: str = field(repr=False)
    client_id: str = field(repr=False)
    segredo: str = field(repr=False)


def ler_credenciais(ambiente: Mapping[str, str]) -> Credenciais:
    """Confere a presença e o formato das três variáveis. As mensagens citam só os nomes, nunca os valores."""
    problemas: list[str] = []
    valores = {nome: (ambiente.get(nome) or "") for nome in (VAR_TENANT, VAR_CLIENT_ID, VAR_SEGREDO)}
    for nome, valor in valores.items():
        if not valor.strip():
            problemas.append(f"{nome}: obrigatória com HTTPS.")
    if valores[VAR_TENANT].strip():
        try:
            lab_comum.validar_tenant(valores[VAR_TENANT].strip())
        except argparse.ArgumentTypeError:
            problemas.append(f"{VAR_TENANT}: deve ser um GUID ou um domínio, sem espaços.")
    if valores[VAR_CLIENT_ID].strip() and not _PADRAO_GUID.fullmatch(valores[VAR_CLIENT_ID].strip()):
        problemas.append(f"{VAR_CLIENT_ID}: deve ser um GUID.")
    segredo = valores[VAR_SEGREDO]
    if segredo.strip() and (len(segredo) > 4096 or any(letra.isspace() or ord(letra) < 32 for letra in segredo)):
        problemas.append(f"{VAR_SEGREDO}: deve ter até 4096 caracteres, sem espaços nem quebras de linha.")
    if problemas:
        raise ErroLab("A identidade de teste (ClientSecretCredential, não um login de pessoa) está incompleta ou inválida:\n"
                      + "\n".join(f"  - {problema}" for problema in problemas)
                      + "\nDefina as variáveis de ambiente; os valores nunca são impressos nem gravados.")
    return Credenciais(valores[VAR_TENANT].strip(), valores[VAR_CLIENT_ID].strip().lower(), segredo)


def validar_caminho_do_relatorio(caminho: Path) -> Path:
    try:
        absoluto = caminho.expanduser().resolve(strict=False)
        existe = os.path.lexists(absoluto)
        pasta_existe = absoluto.parent.is_dir()
    except (OSError, RuntimeError, ValueError):
        raise ErroLab("O caminho do relatório (--relatorio) é inválido.") from None
    if existe:
        raise ErroLab("O relatório (--relatorio) já existe. O avaliador nunca sobrescreve: escolha um caminho novo.")
    if not pasta_existe:
        raise ErroLab("A pasta do relatório (--relatorio) não existe. Crie a pasta antes.")
    return absoluto


def reservar_relatorio(caminho: Path) -> Any:
    """Cria o arquivo antes da rede, em modo exclusivo, e deixa nele um marcador de execução em andamento."""
    try:
        arquivo = open(caminho, "x", encoding="utf-8", newline="\n")
    except FileExistsError:
        raise ErroLab("O relatório (--relatorio) já existe. O avaliador nunca sobrescreve: escolha um caminho novo.") from None
    except OSError:
        raise ErroLab("Não foi possível criar o relatório (--relatorio). Confira a pasta e as permissões.") from None
    try:
        gravar_relatorio(arquivo, {"schema_version": VERSAO_DO_ESQUEMA, "relatorio": "avaliacao_http_do_chat",
                                   "status": "em_andamento"})
    except OSError:
        arquivo.close()
        raise ErroLab("Não foi possível gravar no relatório (--relatorio). Confira a pasta e o espaço em disco.") from None
    return arquivo


def gravar_relatorio(arquivo: Any, relatorio: Mapping[str, Any]) -> None:
    arquivo.seek(0)
    arquivo.truncate()
    arquivo.write(json.dumps(relatorio, ensure_ascii=False, indent=2) + "\n")
    arquivo.flush()
    os.fsync(arquivo.fileno())


def hashes_do_codigo() -> dict[str, dict[str, str]]:
    """Os dois SHA-256 dos módulos de produção que o contêiner copia: ligam o resultado à versão do código que o gerou."""
    hashes = {}
    for nome in ARQUIVOS_DO_CODIGO:
        try:
            hashes[f"scripts/{nome}"] = hashes_do_conteudo((lab_comum.RAIZ / "scripts" / nome).read_bytes())
        except OSError:
            raise ErroLab(f"O módulo scripts/{nome} não foi encontrado: use uma cópia completa do projeto.") from None
    return hashes


# --------------------------------------------------------------------------------------
# Token da identidade de teste
# --------------------------------------------------------------------------------------

class ErroDeToken(Exception):
    """Não foi possível obter o token. Guarda só o código AADSTS, que não identifica nada: o texto do erro é descartado."""

    def __init__(self, codigo_entra: str | None = None):
        super().__init__("token indisponível")
        self.codigo_entra = codigo_entra


class FonteDeToken:
    """Token de acesso da identidade de teste para api://<ID do aplicativo>/.default, sempre só em memória."""

    def __init__(self, credenciais: Credenciais):
        try:
            from azure.identity import ClientSecretCredential
        except ImportError:
            raise ErroLab("Biblioteca do Azure não encontrada. Ative o ambiente virtual e execute: "
                          "python -m pip install -r requirements/l100.txt") from None
        self._escopo = f"api://{credenciais.client_id}/.default"
        self._credencial = ClientSecretCredential(
            tenant_id=credenciais.tenant, client_id=credenciais.client_id, client_secret=credenciais.segredo)

    def obter(self) -> str:
        try:
            acesso = self._credencial.get_token(self._escopo)
        except Exception as erro:  # noqa: BLE001 - o texto pode ter IDs do ambiente: só o código AADSTS é guardado
            achado = _PADRAO_CODIGO_ENTRA.search(str(erro))
            raise ErroDeToken(f"AADSTS{achado.group(1)}" if achado else None) from None
        token = getattr(acesso, "token", None)
        if not isinstance(token, str) or not _PADRAO_TOKEN.fullmatch(token):
            raise ErroDeToken() from None
        return token


def criar_fonte_de_token(credenciais: Credenciais) -> FonteDeToken:
    return FonteDeToken(credenciais)


# --------------------------------------------------------------------------------------
# Transporte
# --------------------------------------------------------------------------------------

class FalhaDeTransporte(Exception):
    """Nenhuma resposta HTTP utilizável. O rótulo é de um vocabulário fechado, nunca o texto de uma exceção."""

    def __init__(self, rotulo: str):
        super().__init__(rotulo)
        self.rotulo = rotulo


@dataclass(frozen=True)
class RespostaHttp:
    status: int
    corpo: bytes
    tipo_de_conteudo: str = "application/json"


class _SemRedirecionamento(urllib.request.HTTPRedirectHandler):
    """Nenhum redirecionamento é seguido: o token e a pergunta só vão ao destino informado."""

    def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> None:
        return None


def _ler_corpo(resposta: Any, prazo: float) -> bytes:
    declarado = resposta.headers.get("Content-Length", "")
    if declarado.isascii() and declarado.isdigit() and int(declarado) > LIMITE_DA_RESPOSTA:
        raise FalhaDeTransporte("corpo_grande")
    partes: list[bytes] = []
    total = 0
    while True:
        if time.monotonic() > prazo:
            raise FalhaDeTransporte("tempo_esgotado")
        parte = resposta.read(min(8192, LIMITE_DA_RESPOSTA + 1 - total))
        if not parte:
            return b"".join(partes)
        total += len(parte)
        if total > LIMITE_DA_RESPOSTA:
            raise FalhaDeTransporte("corpo_grande")
        partes.append(parte)


def _rotulo_de_transporte(motivo: Any) -> str:
    if isinstance(motivo, TimeoutError):
        return "tempo_esgotado"
    return "tls" if isinstance(motivo, ssl.SSLError) else "conexao"


def enviar_http(url: str, corpo: bytes, cabecalhos: Mapping[str, str], timeout: float) -> RespostaHttp:
    """Um POST, sem repetir e sem seguir redirecionamentos, com o certificado verificado e a resposta limitada a 128 KiB."""
    manipuladores: list[Any] = [_SemRedirecionamento()]
    if (urllib.parse.urlsplit(url).hostname or "") in HOSTS_LOCAIS:
        manipuladores.append(urllib.request.ProxyHandler({}))  # um chat local nunca passa por um proxy
    abridor = urllib.request.build_opener(*manipuladores)
    requisicao = urllib.request.Request(url, data=corpo, headers=dict(cabecalhos), method="POST")
    prazo = time.monotonic() + timeout
    try:
        with abridor.open(requisicao, timeout=timeout) as resposta:
            return RespostaHttp(resposta.status, _ler_corpo(resposta, prazo), resposta.headers.get("Content-Type", ""))
    except urllib.error.HTTPError as erro:
        try:
            return RespostaHttp(erro.code, _ler_corpo(erro, prazo), erro.headers.get("Content-Type", ""))
        finally:
            erro.close()
    except urllib.error.URLError as erro:
        raise FalhaDeTransporte(_rotulo_de_transporte(erro.reason)) from None
    except TimeoutError:
        raise FalhaDeTransporte("tempo_esgotado") from None
    except ssl.SSLError:
        raise FalhaDeTransporte("tls") from None
    except (http.client.HTTPException, OSError, ValueError):
        raise FalhaDeTransporte("conexao") from None


def relogio() -> float:
    return time.monotonic()


def agora_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


# --------------------------------------------------------------------------------------
# Um caso
# --------------------------------------------------------------------------------------

@dataclass
class ResultadoDoCaso:
    """Só o que não identifica a pergunta, o texto nem o destino: contagens, rótulos e tempos."""

    id: str
    categoria: str
    tipo_esperado: str
    situacao_esperada: str
    resultado: str
    motivos: list[str] = field(default_factory=list)
    http: int | None = None
    tempo_s: float | None = None
    tipo: str | None = None
    situacao: str | None = None
    citacoes: int | None = None
    tokens: dict[str, int] | None = None
    simulada: bool | None = None
    texto_individual_fixo: bool | None = None
    erro: str | None = None
    erro_do_chat: str | None = None


@dataclass(frozen=True)
class Resposta:
    tipo: str
    situacao: str
    citacoes: int
    tokens: dict[str, int] | None
    simulada: bool
    texto_fixo: bool
    aviso_fixo: bool


class PayloadInvalido(Exception):
    def __init__(self, rotulo: str):
        super().__init__(rotulo)
        self.rotulo = rotulo


def _contagem_valida(valor: Any) -> bool:
    return isinstance(valor, int) and not isinstance(valor, bool) and 0 <= valor <= MAXIMO_DE_TOKENS


def interpretar_resposta(corpo: bytes, tipo_de_conteudo: str) -> Resposta:
    """Confere o formato público da resposta 200 e guarda só contagens e comparações: o texto e as citações são descartados."""
    if tipo_de_conteudo.split(";")[0].strip().lower() != "application/json":
        raise PayloadInvalido("tipo_de_conteudo")
    try:
        dados = json.loads(corpo.decode("utf-8"))
    except (ValueError, RecursionError):
        raise PayloadInvalido("json_invalido") from None
    if not isinstance(dados, dict) or set(dados) != CAMPOS_DA_RESPOSTA:
        raise PayloadInvalido("payload_invalido")
    evidencias, uso = dados["evidencias"], dados["uso"]
    estrutura_ok = (
        dados["tipo"] in lab_politica.TIPOS and dados["situacao"] in SITUACOES
        and isinstance(dados["texto"], str) and isinstance(dados["aviso"], str) and isinstance(dados["aviso_simulacao"], str)
        and isinstance(dados["simulada"], bool) and isinstance(dados["id_requisicao"], str)
        and (dados["id"] is None or isinstance(dados["id"], str))
        and isinstance(evidencias, list)
        and all(isinstance(item, dict) and set(item) == CAMPOS_DA_EVIDENCIA and all(isinstance(valor, str) for valor in item.values())
                for item in evidencias)
        and (uso is None or (isinstance(uso, dict) and set(uso) == CAMPOS_DO_USO and all(_contagem_valida(v) for v in uso.values()))))
    if not estrutura_ok:
        raise PayloadInvalido("payload_invalido")
    return Resposta(dados["tipo"], dados["situacao"], len(evidencias), dict(uso) if uso is not None else None, dados["simulada"],
                    dados["texto"] == TEXTO_INDIVIDUAL, dados["aviso"] == AVISO_INDIVIDUAL)


def _codigo_do_chat(corpo: bytes) -> str | None:
    """O código público do erro (vocabulário fechado do chat), se a resposta de erro o traz; a mensagem é descartada."""
    try:
        dados = json.loads(corpo.decode("utf-8"))
    except (ValueError, RecursionError):
        return None
    codigo = dados.get("erro") if isinstance(dados, dict) else None
    return codigo if isinstance(codigo, str) and codigo in lab_chat.MENSAGENS else None


def comparar(caso: Caso, resposta: Resposta, destino: Destino) -> list[str]:
    """Motivos da divergência: tipo e situação literais e os invariantes de apresentação. Vazio quando o caso passa."""
    motivos = []
    if resposta.tipo != caso.tipo_esperado:
        motivos.append("tipo_divergente")
    if resposta.situacao != caso.situacao_esperada:
        motivos.append("situacao_divergente")
    if resposta.simulada and destino.https:
        motivos.append("simulada_em_destino_https")
    if motivos:
        return motivos
    if caso.tipo_esperado == lab_politica.CONTRATACAO_INDIVIDUAL:
        if not resposta.texto_fixo:
            motivos.append("texto_individual_nao_fixo")
        if not resposta.aviso_fixo:
            motivos.append("aviso_individual_ausente")
        if resposta.citacoes < 1:
            motivos.append("sem_evidencias")
    elif caso.tipo_esperado == lab_politica.DOCUMENTADA:
        if resposta.citacoes < 1:
            motivos.append("sem_evidencias")
    elif caso.situacao_esperada == lab_politica.RECUSADA and resposta.citacoes != 0:
        motivos.append("evidencias_em_recusa")
    return motivos


def executar_caso(caso: Caso, destino: Destino, token: str | None, timeout: float) -> tuple[ResultadoDoCaso, bool, bool]:
    """Uma chamada. Devolve o resultado, se foi falha de transporte e se o destino recusou a autenticação (401 ou 403)."""
    resultado = ResultadoDoCaso(caso.id, caso.categoria, caso.tipo_esperado, caso.situacao_esperada, ERRO)
    cabecalhos = {"Content-Type": "application/json", "Accept": "application/json", "User-Agent": USER_AGENT}
    if token and destino.https:
        cabecalhos["Authorization"] = f"Bearer {token}"
    corpo = json.dumps({"pergunta": caso.pergunta}, ensure_ascii=False).encode("utf-8")
    inicio = relogio()
    try:
        resposta = enviar_http(destino.base + CAMINHO_DA_API, corpo, cabecalhos, timeout)
    except FalhaDeTransporte as falha:
        resultado.tempo_s = round(relogio() - inicio, 3)
        resultado.erro = falha.rotulo
        return resultado, True, False
    resultado.tempo_s = round(relogio() - inicio, 3)
    resultado.http = resposta.status
    if resposta.status != 200:
        resultado.resultado = FALHA_HTTP
        resultado.erro = "redirecionamento" if 300 <= resposta.status < 400 else f"http_{resposta.status}"
        resultado.erro_do_chat = _codigo_do_chat(resposta.corpo)
        return resultado, False, resposta.status in (401, 403)
    try:
        interpretada = interpretar_resposta(resposta.corpo, resposta.tipo_de_conteudo)
    except PayloadInvalido as invalido:
        resultado.erro = invalido.rotulo
        return resultado, False, False
    resultado.tipo, resultado.situacao, resultado.citacoes = interpretada.tipo, interpretada.situacao, interpretada.citacoes
    resultado.tokens, resultado.simulada = interpretada.tokens, interpretada.simulada
    resultado.texto_individual_fixo = interpretada.texto_fixo and interpretada.aviso_fixo
    resultado.motivos = comparar(caso, interpretada, destino)
    resultado.resultado = DIVERGENTE if resultado.motivos else APROVADO
    return resultado, False, False


# --------------------------------------------------------------------------------------
# Execução e relatório
# --------------------------------------------------------------------------------------

@dataclass
class Execucao:
    entrada: Entrada
    destino: Destino
    inicio_utc: str = ""
    fim_utc: str = ""
    duracao: float = 0.0
    resultados: list[ResultadoDoCaso] = field(default_factory=list)
    interrupcao: str | None = None
    codigo_entra: str | None = None
    chamadas: int = 0
    acessos_recusados: int = 0

    def interromper(self, motivo: str) -> None:
        self.interrupcao = self.interrupcao or motivo

    def finalizar(self) -> None:
        """Os casos que não chegaram a ser enviados ficam registrados como não avaliados, nunca como aprovados."""
        for caso in self.entrada.casos[len(self.resultados):]:
            self.resultados.append(ResultadoDoCaso(caso.id, caso.categoria, caso.tipo_esperado, caso.situacao_esperada,
                                                   NAO_AVALIADO, [self.interrupcao or "nao_enviado"]))

    def contar(self, resultado: str) -> int:
        return sum(1 for item in self.resultados if item.resultado == resultado)


def decimal(valor: float, casas: int = 1) -> str:
    return f"{valor:.{casas}f}".replace(".", ",")


def _descrever(posicao: int, total: int, item: ResultadoDoCaso) -> str:
    base = f"[{posicao}/{total}] {item.id}"
    if item.resultado == APROVADO:
        return f"  [OK] {base}: aprovado (HTTP {item.http}, {decimal(item.tempo_s or 0)} s)"
    if item.resultado == DIVERGENTE:
        detalhe = (f"esperado {item.tipo_esperado}/{item.situacao_esperada}, obtido {item.tipo}/{item.situacao}; "
                   f"{', '.join(item.motivos)}")
    elif item.resultado == FALHA_HTTP:
        detalhe = f"{item.erro}" + (f" ({item.erro_do_chat})" if item.erro_do_chat else "")
    else:
        detalhe = f"{item.erro}"
    return f"  [FALHA] {base}: {item.resultado} ({detalhe})"


def avaliar(execucao: Execucao, fonte: FonteDeToken | None, registrar: Callable[[str], None] = print) -> None:
    """Envia os casos em sequência. Para no limite de tempo, em 3 falhas de transporte seguidas ou sem token."""
    inicio = relogio()
    seguidas = 0
    total = len(execucao.entrada.casos)
    for posicao, caso in enumerate(execucao.entrada.casos, start=1):
        restante = TEMPO_MAXIMO - (relogio() - inicio)
        if restante < 1:
            execucao.interromper(TEMPO_MAXIMO_EXCEDIDO)
            break
        token = None
        if fonte is not None:
            try:
                token = fonte.obter()
            except ErroDeToken as erro:
                execucao.codigo_entra = erro.codigo_entra
                execucao.interromper(FALHA_DE_AUTENTICACAO)
                break
        execucao.chamadas += 1
        item, transporte, acesso_recusado = executar_caso(caso, execucao.destino, token, min(TIMEOUT_DA_CHAMADA, restante))
        execucao.resultados.append(item)
        execucao.acessos_recusados += int(acesso_recusado)
        registrar(_descrever(posicao, total, item))
        seguidas = seguidas + 1 if transporte else 0
        if seguidas >= FALHAS_DE_TRANSPORTE_SEGUIDAS:
            execucao.interromper(FALHAS_DE_TRANSPORTE)
            break


def resumir_uso(execucao: Execucao) -> dict[str, Any]:
    """Soma só o uso que o chat informou. Onde ele não informa, o consumo é desconhecido: nunca vira zero nem um total completo."""
    informados = [item.tokens for item in execucao.resultados if item.tokens is not None]
    soma = None
    if informados:
        soma = dict.fromkeys(sorted(CAMPOS_DO_USO), 0)
        for uso in informados:
            for nome, valor in uso.items():
                soma[nome] += valor
    return {"respostas_com_uso_informado": len(informados),
            "chamadas_sem_uso_informado": max(execucao.chamadas - len(informados), 0),
            "soma_do_uso_informado": soma,
            "observacao": OBSERVACAO_DO_USO}


def codigo_de_saida(execucao: Execucao) -> int:
    if execucao.interrupcao == FALHA_DE_AUTENTICACAO or execucao.acessos_recusados:
        return lab_comum.CODIGO_ACESSO
    if execucao.interrupcao is None and all(item.resultado == APROVADO for item in execucao.resultados):
        return lab_comum.CODIGO_OK
    return lab_comum.CODIGO_DIVERGENCIA


def montar_relatorio(execucao: Execucao) -> dict[str, Any]:
    entrada, resultados = execucao.entrada, execucao.resultados
    categorias: dict[str, dict[str, int]] = {}
    for item in resultados:
        resumo = categorias.setdefault(item.categoria, {"casos": 0, "aprovados": 0})
        resumo["casos"] += 1
        resumo["aprovados"] += int(item.resultado == APROVADO)
    return {
        "schema_version": VERSAO_DO_ESQUEMA,
        "relatorio": "avaliacao_http_do_chat",
        "status": "interrompido" if execucao.interrupcao else "concluido",
        "interrupcao": ({"motivo": execucao.interrupcao, "nao_avaliados": execucao.contar(NAO_AVALIADO)}
                        if execucao.interrupcao else None),
        "codigo_de_saida": codigo_de_saida(execucao),
        "inicio_utc": execucao.inicio_utc,
        "fim_utc": execucao.fim_utc,
        "entrada": {"nome": entrada.nome, "origem": entrada.origem, "casos": len(entrada.casos),
                    "campos_ignorados": list(entrada.campos_ignorados), "sha256_bytes_brutos": entrada.sha256_bytes_brutos,
                    "sha256_normalizado_lf": entrada.sha256_normalizado_lf},
        "configuracao_avaliada": {"valor": entrada.configuracao_avaliada, "informada_pelo_autor": True,
                                  "verificada_pelo_avaliador": False, "nota": NOTA_DA_CONFIGURACAO},
        "destino": {"modo": "hospedado_https" if execucao.destino.https else "demonstracao_ou_local_loopback"},
        "identidade": {"tipo": "client_secret_credential" if execucao.destino.https else "nenhuma"},
        "limites": {"casos": MAXIMO_DE_CASOS, "timeout_da_chamada_s": int(TIMEOUT_DA_CHAMADA), "tempo_maximo_s": int(TEMPO_MAXIMO),
                    "falhas_de_transporte_seguidas": FALHAS_DE_TRANSPORTE_SEGUIDAS, "resposta_maxima_bytes": LIMITE_DA_RESPOSTA,
                    "tentativas_automaticas_do_avaliador": 0},
        "avaliador": {"arquivo": "scripts/avaliar_chat.py", "versao": VERSAO_DO_AVALIADOR,
                      **hashes_do_conteudo(Path(__file__).resolve().read_bytes())},
        "codigo_avaliado": hashes_do_codigo(),
        "significado_dos_hashes": SIGNIFICADO_DOS_HASHES,
        "resumo": {
            "casos": len(resultados), "aprovados": execucao.contar(APROVADO), "divergentes": execucao.contar(DIVERGENTE),
            "falhas_http": execucao.contar(FALHA_HTTP), "erros": execucao.contar(ERRO), "nao_avaliados": execucao.contar(NAO_AVALIADO),
            "chamadas_http": execucao.chamadas,
            "escopo_da_contagem": ESCOPO_DA_CONTAGEM,
            "respostas_simuladas": sum(1 for item in resultados if item.simulada),
            "uso_de_tokens": resumir_uso(execucao),
            "tempo_nas_chamadas_s": round(sum(item.tempo_s or 0.0 for item in resultados), 3),
            "tempo_total_s": round(execucao.duracao, 3),
        },
        "categorias": categorias,
        "casos": [asdict(item) for item in resultados],
    }


# --------------------------------------------------------------------------------------
# Linha de comando
# --------------------------------------------------------------------------------------

def mostrar_plano(entrada: Entrada, destino: Destino, executar: bool) -> None:
    print("Avaliação do contrato HTTP do chat L200 (Desafio 06)")
    categorias: dict[str, int] = {}
    for caso in entrada.casos:
        categorias[caso.categoria] = categorias.get(caso.categoria, 0) + 1
    print(f"  Casos: {len(entrada.casos)} ({' · '.join(f'{nome} {total}' for nome, total in categorias.items())})")
    if entrada.campos_ignorados:
        print(f"  [AVISO] Campos desconhecidos ignorados: {', '.join(entrada.campos_ignorados)}.")
    for caso in entrada.casos:
        print(f"    {caso.id:<14} {caso.tipo_esperado} / {caso.situacao_esperada}")
    print(f"  Plano: {len(entrada.casos)} POST sequencial(is), sem repetição automática; {int(TIMEOUT_DA_CHAMADA)} s por chamada, "
          f"{LIMITE_DA_RESPOSTA // 1024} KiB por resposta; para em {int(TEMPO_MAXIMO // 60)} min ou "
          f"{FALHAS_DE_TRANSPORTE_SEGUIDAS} falhas de transporte seguidas.")
    if destino.https:
        print("  Destino: HTTPS, endereço padrão do Azure Container Apps (o endereço não é impresso nem gravado). Identidade de teste "
              "(ClientSecretCredential), sem login de pessoa: as três variáveis estão definidas e bem formadas, mas o token só é "
              "pedido com --executar.")
    else:
        print("  [DEMONSTRAÇÃO] Destino local em HTTP, sem autenticação: o resultado não avalia o chat hospedado.")
    if not executar:
        print("\n[SIMULAÇÃO] Entrada, destino e relatório conferem; nenhuma pergunta foi enviada e nenhum relatório foi criado. "
              "Repita com --executar para enviar.")


def _descrever_uso(uso: Mapping[str, Any]) -> str:
    soma = uso["soma_do_uso_informado"]
    if soma is None:
        return "Tokens: o chat não informou o uso em nenhuma resposta (desconhecido, não zero)."
    total = uso["respostas_com_uso_informado"] + uso["chamadas_sem_uso_informado"]
    partes = " · ".join(f"{nome} {valor}" for nome, valor in soma.items())
    return (f"Tokens: uso informado em {uso['respostas_com_uso_informado']} de {total} chamada(s); nas demais o consumo é desconhecido "
            f"(não zero). Soma parcial do que foi informado: {partes}. Não é o total consumido nem o custo.")


def mostrar_resumo(execucao: Execucao, caminho: Path) -> None:
    total = len(execucao.entrada.casos)
    print(f"\nResultado: {execucao.contar(APROVADO)} de {total} caso(s) aprovados")
    for rotulo, nome in (("divergentes", DIVERGENTE), ("falhas de HTTP", FALHA_HTTP), ("erros de transporte ou formato", ERRO),
                         ("não avaliados", NAO_AVALIADO)):
        print(f"  {rotulo}: {execucao.contar(nome)}")
    print(f"  Chamadas HTTP ao chat: {execucao.chamadas} · tempo total: {decimal(execucao.duracao)} s")
    print(f"  {_descrever_uso(resumir_uso(execucao))}")
    simuladas = sum(1 for item in execucao.resultados if item.simulada)
    if simuladas:
        print(f"  [DEMONSTRAÇÃO] {simuladas} resposta(s) simulada(s): este resultado não avalia o serviço real.")
    if execucao.interrupcao:
        print(f"  [INTERROMPIDA] {DESCRICAO_DA_INTERRUPCAO[execucao.interrupcao]}; "
              f"{execucao.contar(NAO_AVALIADO)} caso(s) não avaliado(s).")
    if execucao.interrupcao == FALHA_DE_AUTENTICACAO:
        codigo = f" ({execucao.codigo_entra})" if execucao.codigo_entra else ""
        print(f"  [ERRO] Não foi possível obter o token{codigo}. Confira o segredo, o tenant e a identidade de teste; nenhuma "
              "pergunta foi enviada.")
    elif execucao.acessos_recusados:
        print(f"  [ERRO] O destino recusou a autenticação (HTTP 401 ou 403) em {execucao.acessos_recusados} chamada(s). Confira a "
              "audiência do token (api://<ID do aplicativo>/.default) e a autorização da identidade de teste.")
    print(f"  Relatório gravado em {caminho} (arquivo novo, sem endereço do destino, perguntas, textos nem identificadores).")


def executar_avaliacao(entrada: Entrada, destino: Destino, credenciais: Credenciais | None, caminho: Path) -> int:
    fonte = criar_fonte_de_token(credenciais) if credenciais is not None else None
    execucao = Execucao(entrada, destino, inicio_utc=agora_utc())
    arquivo = reservar_relatorio(caminho)  # antes de qualquer acesso à rede
    defeito: Exception | None = None
    inicio = relogio()
    try:
        avaliar(execucao, fonte)
    except KeyboardInterrupt:
        execucao.interromper(CANCELADO)
    except Exception as erro:  # noqa: BLE001 - o relatório registra a interrupção; só o tipo do erro é mostrado
        execucao.interromper(DEFEITO_DO_AVALIADOR)
        defeito = erro
    execucao.duracao = relogio() - inicio
    execucao.fim_utc = agora_utc()
    execucao.finalizar()
    try:
        gravar_relatorio(arquivo, montar_relatorio(execucao))
    except OSError:
        raise ErroLab("Os casos foram enviados, mas não foi possível gravar o relatório final. O resumo acima é o que existe.",
                      lab_comum.CODIGO_INESPERADO) from None
    finally:
        arquivo.close()
    if defeito is not None:
        raise defeito
    mostrar_resumo(execucao, caminho)
    return codigo_de_saida(execucao)


def executar(args: argparse.Namespace) -> int:
    for nome in ("azure", "msal"):
        logging.getLogger(nome).setLevel(logging.CRITICAL)
    entrada = carregar_entrada(Path(args.casos))
    destino = validar_destino(args.url)
    credenciais = ler_credenciais(os.environ) if destino.https else None
    caminho = validar_caminho_do_relatorio(Path(args.relatorio))
    mostrar_plano(entrada, destino, args.executar)
    if not args.executar:
        return lab_comum.CODIGO_OK
    print("\nExecutando (um POST por caso, em sequência):")
    return executar_avaliacao(entrada, destino, credenciais, caminho)


def traduzir_erro_do_avaliador(erro: Exception, args: argparse.Namespace) -> tuple[str, int]:
    return (f"Erro inesperado do avaliador ({type(erro).__name__}). Nenhum dado do ambiente foi impresso; se o relatório foi "
            "criado, ele registra a interrupção.", lab_comum.CODIGO_INESPERADO)


def principal(argv: list[str] | None = None) -> int:
    lab_comum.configurar_saida()
    parser = lab_comum.ParserLab(description=__doc__)
    parser.add_argument("--casos", required=True, help="Arquivo JSON dos casos (schema_version 1).")
    parser.add_argument("--url", required=True,
                        help="Endereço base do chat: o endereço padrão https://<aplicativo>.<ambiente>.<regiao>.azurecontainerapps.io "
                             "(domínios personalizados não são aceitos) ou, só para demonstração ou uso local, "
                             "http://127.0.0.1:<porta>. Nunca é impresso nem gravado.")
    parser.add_argument("--relatorio", required=True,
                        help="Relatório JSON a criar. O arquivo não pode existir: o avaliador nunca sobrescreve.")
    parser.add_argument("--executar", action="store_true",
                        help="Envia as perguntas. Sem esta opção, só valida a entrada e o plano.")
    args = parser.parse_args(argv)
    try:
        return lab_comum.executar_com_tratamento(executar, args, tradutor=traduzir_erro_do_avaliador)
    except KeyboardInterrupt:  # fora do laço dos casos; dentro dele, o relatório registra o cancelamento
        print("[INTERROMPIDA] A execução foi cancelada.", file=sys.stderr)
        return lab_comum.CODIGO_DIVERGENCIA


if __name__ == "__main__":
    sys.exit(principal())
