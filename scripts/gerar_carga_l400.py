"""Gerador de carga HTTP finito e concorrente para o chat do L400 (Desafio 06): POST /api/perguntar, com tetos rígidos e sem guardar texto.

Envia poucos pedidos concorrentes para observar, em uma rodada pequena, como a admissão, os prazos e as falhas do chat se comportam:
pedidos aceitos, recusa explícita de "ocupado", erros públicos, tempo esgotado e falhas de rede. Cada trabalhador envia o próximo pedido
assim que recebe a resposta do anterior: a concorrência é o número de pedidos em andamento ao mesmo tempo, não uma taxa de chegada.
Não é um teste de capacidade: o resultado não estabelece capacidade máxima, percentil de produção, objetivo de nível de serviço nem
garantia de disponibilidade.

CONSUMO: cada pedido enviado chama a busca e os modelos do serviço e consome tokens, com custo; o gerador não sabe de antemão quanto cada
pedido gasta. Cancelar localmente (Ctrl+C, o limite de tempo ou a parada por falhas) NÃO interrompe um pedido já enviado: o serviço pode
continuar até concluir ou atingir o próprio prazo. Por isso a execução real exige --executar e --confirmo-consumo juntos.

Seguro por padrão: sem --executar, o programa só confere as opções, o endereço, as perguntas e o relatório e mostra o plano; nenhuma rede
é usada, nenhum token é pedido e nenhum arquivo é criado. Todos os limites são conferidos antes de qualquer rede.

Tetos fixos no código (nenhuma opção passa deles): 50 pedidos; concorrência 8, nunca maior que os pedidos; 600 s para enviar pedidos; 300 s
por pedido; 128 KiB por resposta; parada depois de, no máximo, 10 resultados seguidos fora do esperado. Não há tentativa automática: um
pedido que falha não é repetido. A execução sempre termina: ao enviar todos os pedidos, no limite de tempo, na parada por falhas ou em Ctrl+C.

Tempo: --tempo-maximo é o tempo para ENVIAR pedidos, contado a partir do primeiro envio. Passado esse tempo, nenhum pedido novo sai, e os
já enviados têm até mais 10 s para terminar; só então o programa desiste de quem ficou preso. O processo pode, portanto, durar até o tempo
máximo mais 10 s. O tempo de obter o token da identidade gerenciada, que tem prazo próprio do Azure, fica fora dessa conta.

Destino: --url https://<aplicativo>.<ambiente>.<região>.azurecontainerapps.io, o endereço padrão do chat hospedado (o formato interno,
<aplicativo>.internal.<ambiente>.<região>.azurecontainerapps.io, também vale). Padrão fechado, conferido antes de qualquer rede: só HTTPS na
porta 443, sem usuário, senha, parâmetros nem fragmento, e o host precisa terminar em .azurecontainerapps.io, comparado por rótulo (um nome
com o sufixo no meio não passa). Domínio personalizado, localhost, endereço IP e qualquer outro domínio são recusados: não há opção para
isso, e o token nunca é enviado a eles. O caminho é sempre /api/perguntar. Redirecionamentos nunca são seguidos: um 3xx é o resultado
"redirecionamento". O endereço nunca é impresso nem gravado: o plano mostra sempre https://*.azurecontainerapps.io. Os proxies do ambiente
(https_proxy, http_proxy, all_proxy e o registro do Windows) são ignorados de propósito, para o token não passar por um intermediário
implícito: o gerador se conecta direto ao destino, e quem só alcança o endereço por proxy não consegue usar esta versão.

Autenticação (Microsoft Entra ID): o token de acesso (Bearer) para api://<ID do aplicativo de login>/.default vem de uma variável de
ambiente, nunca de um argumento: VARELEIRA_CARGA_TOKEN ou o NOME de outra variável em --token-env. O valor nunca é impresso, gravado nem
repetido em mensagens. Dentro de um Job da rede, --identidade-gerenciada com --client-id e --audiencia pede o token à identidade gerenciada
(precisa do pacote azure-identity, de requirements/l400.txt, e dos módulos lab_ingestao_l300.py e lab_ingestao.py); fora do Azure, use a variável.

Perguntas: por padrão, 4 perguntas sintéticas de desenvolvimento sobre o laboratório, embutidas e usadas em rodízio. --perguntas-arquivo
aceita um JSON local com uma lista de 1 a 20 textos. NÃO use as perguntas dos conjuntos de avaliação (L100, L200 e L400), sobretudo as
finais: o conjunto final não serve para carga. A proteção do programa é de MELHOR ESFORÇO e falha fechada: recusa um arquivo dentro de uma
pasta de avaliação de dados/ (pelo caminho real, com links simbólicos e junções resolvidos; um caminho com prefixo especial do Windows ou
que não possa ser resolvido também é recusado) e, quando a pasta dados/ do projeto existe, recusa qualquer pergunta igual a uma de
dados/**/*.json (sem diferença de maiúsculas, acentos e pontuação), mesmo copiada para outra pasta. Em um Job, cuja imagem não tem dados/,
a conferência por conteúdo é impossível e fica indisponível (o plano avisa): quem opera é responsável por não usar o conjunto final.
Perguntas reescritas com outras palavras não são detectadas. Os textos das perguntas nunca são impressos nem gravados.

Resultado: o conteúdo das respostas é descartado. Só entram na análise o status HTTP, o tipo público da resposta, o código público de erro
(vocabulário fechado do chat), a presença do cabeçalho X-Request-Id (o valor não é guardado) e o uso informado em tokens. A última linha
da saída padrão (stdout) é L400_CARGA_RESULTADO=<JSON em uma linha>, com pedidos planejados e enviados, concorrência, tempo decorrido,
contagem por classe (ok, ocupado, erro_publico, http, timeout, falha_de_rede, redirecionamento, formato_invalido, resposta_simulada),
latências em ms, uso conhecido e o limite "carga_pequena_nao_capacidade_producao". Com poucos pedidos, mediana e p95 não são percentis de
produção. As mensagens [ERRO] vão para o stderr, um fluxo separado, e saem antes da linha de resultado.
--relatorio grava o mesmo resultado, com o detalhe de cada pedido, em um arquivo NOVO (nunca sobrescreve; permissão 0600 em POSIX).
--esperar diz quais classes não contam como divergência (padrão: ok); para exercitar a admissão, use --esperar ok,ocupado.

Códigos de saída: 0 todos os pedidos planejados foram enviados e cada resultado estava entre os esperados (ou foi só o plano);
1 uso: opção, endereço, pergunta, relatório ou token inválidos ou ausentes, ou confirmação de consumo ausente (nada foi enviado);
2 acesso: token da identidade gerenciada indisponível, autenticação recusada (HTTP 401 ou 403) ou nenhuma resposta HTTP recebida (rede,
DNS, TLS ou prazo em todos os pedidos); 3 divergência: resultado fora do esperado, execução interrompida (tempo, falhas seguidas ou
Ctrl+C) ou pedidos não enviados; 4 defeito do gerador.

Exemplos (PowerShell, a partir da raiz do projeto, com a .venv ativa; $urlChat é o endereço do chat, definido por você):
    # 1. Plano, sem enviar nada (o padrão). O token entra por variável, lido sem eco:
    $protegido = Read-Host "Token de acesso (Bearer) do chat" -AsSecureString
    $env:VARELEIRA_CARGA_TOKEN = [Net.NetworkCredential]::new("", $protegido).Password
    python scripts\\gerar_carga_l400.py --url $urlChat

    # 2. Carga real e pequena (6 pedidos, concorrência 3): consome tokens e exige as duas confirmações
    python scripts\\gerar_carga_l400.py --url $urlChat --pedidos 6 --concorrencia 3 --relatorio outputs\\carga-001.json --executar --confirmo-consumo

    # 3. Exercitar a admissão: 12 pedidos, concorrência 8, aceitando a recusa "ocupado"
    python scripts\\gerar_carga_l400.py --url $urlChat --pedidos 12 --concorrencia 8 --esperar ok,ocupado --executar --confirmo-consumo

    # 4. Dentro do Job da rede, com a identidade gerenciada (sem variável de token)
    python scripts/gerar_carga_l400.py --url $urlChat --identidade-gerenciada --client-id $idIdentidade --audiencia "api://$idLogin/.default" --executar --confirmo-consumo

    # Ao terminar, tire o token da sessão:
    Remove-Item Env:\\VARELEIRA_CARGA_TOKEN -ErrorAction SilentlyContinue
"""

from __future__ import annotations

import argparse
import datetime as dt
import http.client
import json
import logging
import math
import os
import re
import socket
import ssl
import sys
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Sequence

import lab_chat
import lab_comum
import lab_politica
from lab_comum import ErroLab

VERSAO_DO_ESQUEMA = 1
VERSAO_DO_GERADOR = 1
NOME_DO_RELATORIO = "carga_l400"
PREFIXO_DO_RESULTADO = "L400_CARGA_RESULTADO="
LIMITE_DA_CARGA = "carga_pequena_nao_capacidade_producao"
CAMINHO_DA_API = "/api/perguntar"  # a mesma rota do chat (chat_web.ROTA_PERGUNTAR): é a única que o gerador usa
DOMINIO_DO_CONTAINER_APPS = ".azurecontainerapps.io"  # o único domínio aceito: o endereço padrão do chat hospedado (como no avaliar_chat.py)
USER_AGENT = f"vareleira-gerar-carga-l400/{VERSAO_DO_GERADOR}"
VAR_TOKEN = "VARELEIRA_CARGA_TOKEN"

# Tetos rígidos: nenhuma opção passa deles.
PEDIDOS_MAXIMOS, PEDIDOS_PADRAO = 50, 6
CONCORRENCIA_MAXIMA, CONCORRENCIA_PADRAO = 8, 3
TEMPO_TOTAL_MINIMO, TEMPO_TOTAL_PADRAO, TEMPO_TOTAL_MAXIMO = 10.0, 300.0, 600.0
TEMPO_POR_PEDIDO_MINIMO, TEMPO_POR_PEDIDO_PADRAO, TEMPO_POR_PEDIDO_MAXIMO = 1.0, 120.0, 300.0
FALHAS_SEGUIDAS_PADRAO, FALHAS_SEGUIDAS_MAXIMAS = 3, 10
LIMITE_DA_RESPOSTA = 128 * 1024  # bytes lidos de cada resposta; acima disso o corpo é recusado
MAXIMO_DE_TOKENS = 10**9  # por contagem de uso: acima disso o valor não é plausível e a resposta é recusada
PERGUNTAS_NO_ARQUIVO_MAXIMAS = 20
LIMITE_DO_ARQUIVO_DE_PERGUNTAS = 64 * 1024  # bytes
RESTANTE_MINIMO = 1.0  # segundos: com menos que isso restando do tempo para enviar pedidos, nenhum pedido novo é enviado
FOLGA_DE_ENCERRAMENTO = 10.0  # segundos além do tempo máximo em que ainda se espera por pedidos já enviados
PASSO_DA_ESPERA = 0.1
MENOR_VALOR_REDIGIDO = 6
MENOR_PERGUNTA_REDIGIDA = 20  # uma pergunta curta ("documentada") seria igual a palavras da própria saída e a estragaria

# Classes de resultado (vocabulário fechado) e rótulos das falhas.
OK, OCUPADO, ERRO_PUBLICO, HTTP, TIMEOUT = "ok", "ocupado", "erro_publico", "http", "timeout"
FALHA_DE_REDE, REDIRECIONAMENTO, FORMATO_INVALIDO, SIMULADA = "falha_de_rede", "redirecionamento", "formato_invalido", "resposta_simulada"
CLASSES = (OK, OCUPADO, ERRO_PUBLICO, HTTP, TIMEOUT, FALHA_DE_REDE, REDIRECIONAMENTO, FORMATO_INVALIDO, SIMULADA)
CAUSAS_DE_REDE = ("dns", "conexao", "tls")

# Conferência do arquivo de perguntas contra os conjuntos de avaliação de dados/: feita, indisponível (sem conjuntos para comparar) ou não se aplica.
CONFERENCIA_FEITA, CONFERENCIA_INDISPONIVEL, CONFERENCIA_NAO_SE_APLICA = "feita", "indisponivel", "nao_se_aplica"

MOTIVO_TEMPO, MOTIVO_FALHAS, MOTIVO_CANCELADO = "tempo_maximo", "falhas_seguidas", "cancelado"
MOTIVO_DEFEITO, MOTIVO_TOKEN = "defeito_do_gerador", "falha_de_token"
DESCRICAO_DA_INTERRUPCAO = {
    MOTIVO_TEMPO: "o tempo máximo total acabou",
    MOTIVO_FALHAS: "houve resultados seguidos fora do esperado",
    MOTIVO_CANCELADO: "a execução foi cancelada (Ctrl+C)",
    MOTIVO_DEFEITO: "defeito do gerador",
    MOTIVO_TOKEN: "não foi possível obter o token da identidade gerenciada",
}

AVISO_DE_CONSUMO = ("Cada pedido enviado chama a busca e os modelos do serviço e consome tokens, com custo; o gerador não sabe de "
                    "antemão quanto cada pedido gasta.")
AVISO_DE_CANCELAMENTO = ("Cancelar localmente (Ctrl+C, parada por falhas ou limite de tempo) não interrompe um pedido já enviado: o "
                         "serviço pode continuar processando e consumindo até concluir ou atingir o próprio prazo.")
AVISO_DE_CAPACIDADE = ("Uma carga pequena e finita exercita limites, prazos e falhas daquela rodada: não estabelece capacidade máxima, "
                       "percentil de produção nem garantia de disponibilidade.")
AVISO_DA_LATENCIA = "Amostra pequena: mínima, mediana e p95 descrevem só esta rodada e não são percentis de produção."
OBSERVACAO_DO_USO = ("Soma só do uso que o chat informou em respostas 200; pedidos sem uso informado (erros, falhas, sem resposta ou "
                     "uso incerto) têm consumo desconhecido, não zero. Não é o total consumido nem o custo.")

# Perguntas sintéticas de desenvolvimento sobre os documentos públicos do laboratório. Não vêm nem derivam de nenhum conjunto de avaliação.
PERGUNTAS_EMBUTIDAS = (
    "Quantos acionamentos da assistência 24 horas cada tipo de serviço permite por vigência e até quanto a Vareleira paga de mão de obra?",
    "Como a franquia de danos elétricos é calculada quando o prejuízo é pequeno?",
    "Quando a cobertura de roubo e furto qualificado fica suspensa por desocupação do imóvel?",
    "O que é endosso no glossário do Vareleira Lar e quando ele é exigido?",
)

_GUID = r"[0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}"
_PADRAO_GUID = re.compile(_GUID)
_PADRAO_AUDIENCIA = re.compile(rf"api://{_GUID}/\.default")
_PADRAO_HOST = re.compile(r"(?=.{1,253}$)[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*")  # o mesmo do avaliar_chat.py
_PADRAO_NOME_DE_VARIAVEL = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}")
_PADRAO_TOKEN = re.compile(r"[A-Za-z0-9._~+/=-]{20,8192}")
_PADRAO_CODIGO_ENTRA = re.compile(r"AADSTS(\d{4,7})")
_PADRAO_ID_DA_REQUISICAO = re.compile(r"[0-9a-f]{32}")
_PADRAO_DECIMAL = re.compile(r"[0-9]{1,6}(?:\.[0-9]{1,3})?")

# O formato público da resposta 200 do chat, derivado das próprias classes de produção: um campo novo lá aparece aqui sem edição.
SITUACOES = (lab_politica.RESPONDIDA, lab_politica.RECUSADA, lab_politica.ESCLARECIMENTO)
CAMPOS_DA_RESPOSTA = frozenset(lab_chat.RespostaChat(lab_politica.DOCUMENTADA, lab_politica.RESPONDIDA, "x", "").a_dict()) | {"id", "id_requisicao"}
CAMPOS_DA_EVIDENCIA = frozenset(lab_chat.EvidenciaChat("a", "b", "c", "d", "e", "f", "g").a_dict())
CAMPOS_DO_USO = frozenset(lab_chat.UsoChat().a_dict())


# --------------------------------------------------------------------------------------
# Entradas: opções, destino, token, perguntas e relatório
# --------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Destino:
    """Endereço base validado. Nunca é impresso nem gravado: só a versão mascarada aparece no plano."""

    base: str = field(repr=False)
    host: str = field(repr=False)

    @property
    def url_do_pedido(self) -> str:
        return self.base + CAMINHO_DA_API

    @property
    def mascarado(self) -> str:
        """Sempre o mesmo texto: o host validado termina no domínio padrão, e nenhum rótulo dele (aplicativo, ambiente, região) é mostrado."""
        return f"https://*{DOMINIO_DO_CONTAINER_APPS}"


@dataclass(frozen=True)
class Plano:
    pedidos: int
    concorrencia: int
    tempo_maximo: float
    tempo_por_pedido: float
    falhas_seguidas: int
    esperar: frozenset[str]
    perguntas: tuple[str, ...] = field(repr=False)
    origem_das_perguntas: str
    conferencia_das_perguntas: str = CONFERENCIA_NAO_SE_APLICA  # só vale com --perguntas-arquivo
    perguntas_comparadas: int = 0  # quantas perguntas de dados/ o arquivo foi comparado


@dataclass(frozen=True)
class Identidade:
    client_id: str = field(repr=False)
    audiencia: str = field(repr=False)


@dataclass(frozen=True)
class Configuracao:
    plano: Plano
    destino: Destino
    nome_da_variavel: str | None  # None com a identidade gerenciada
    token: str | None = field(default=None, repr=False)
    identidade: Identidade | None = None
    relatorio: Path | None = None
    executar: bool = False


class _Problemas:
    """Junta todos os problemas das opções para listá-los de uma vez, sem repetir os valores recebidos."""

    def __init__(self) -> None:
        self.itens: list[str] = []

    def adicionar(self, texto: str) -> None:
        self.itens.append(texto)

    def tentar(self, funcao: Callable[..., Any], *argumentos: Any) -> Any:
        try:
            return funcao(*argumentos)
        except ErroLab as erro:
            self.itens.append(str(erro))
            return None

    def exigir(self) -> None:
        if self.itens:
            raise ErroLab("Opções inválidas; nada foi enviado:\n" + "\n".join(f"  - {item}" for item in self.itens)
                          + "\nOs valores recebidos não são repetidos aqui.")


def _inteiro(opcao: str, bruto: str | None, padrao: int, minimo: int, maximo: int) -> int:
    if bruto is None:
        return padrao
    texto = bruto.strip()
    if not (texto.isascii() and texto.isdigit() and len(texto) <= 9) or not minimo <= int(texto) <= maximo:
        raise ErroLab(f"{opcao}: informe um número inteiro de {minimo} a {maximo}.")
    return int(texto)


def _segundos(opcao: str, bruto: str | None, padrao: float, minimo: float, maximo: float) -> float:
    if bruto is None:
        return padrao
    texto = bruto.strip()
    if not _PADRAO_DECIMAL.fullmatch(texto) or not minimo <= float(texto) <= maximo:
        raise ErroLab(f"{opcao}: informe de {minimo:g} a {maximo:g} segundos, com ponto decimal (sem vírgula nem expoente).")
    return float(texto)


def validar_esperar(bruto: str | None) -> frozenset[str]:
    if bruto is None:
        return frozenset({OK})
    itens = [item for item in re.split(r"[,;\s]+", bruto.strip()) if item]
    if not itens or any(item not in CLASSES for item in itens):
        raise ErroLab(f"--esperar: informe uma ou mais classes separadas por vírgula, entre: {', '.join(CLASSES)}.")
    return frozenset(itens)


def validar_url(url: str) -> Destino:
    """Padrão fechado, conferido ANTES de montar a URL para o token só ir ao endereço esperado: HTTPS, sem usuário, parâmetros nem fragmento,
    caminho fixo da API, porta 443 e um host que termina em .azurecontainerapps.io (o endereço padrão do Azure Container Apps).

    A regra do host é a do `avaliar_chat.validar_destino`: o sufixo vale por rótulo (o ponto antes dele é obrigatório e o host inteiro precisa
    casar com o padrão DNS), então um nome com o sufixo no meio, como chat.azurecontainerapps.io.outro-dominio.example, não passa.
    Domínio personalizado, localhost, endereço IP e qualquer outro domínio são recusados, sem repetir o que foi digitado.
    """
    invalida = ErroLab("--url: endereço inválido. Use https://<aplicativo>.<ambiente>.<região>.azurecontainerapps.io, opcionalmente "
                       f"terminando em {CAMINHO_DA_API}, sem usuário, senha, parâmetros nem fragmento.")
    if not url or len(url) > 2048 or not url.isascii() or any(ord(letra) <= 32 or ord(letra) == 127 or letra == "\\" for letra in url):
        raise invalida
    try:
        partes = urllib.parse.urlsplit(url)
        porta = partes.port
    except ValueError:
        raise invalida from None
    if partes.scheme.lower() == "http":
        raise ErroLab("--url: HTTPS é obrigatório; o token nunca segue por HTTP.")
    host = (partes.hostname or "").lower()
    if (partes.scheme.lower() != "https" or not host or "@" in partes.netloc or partes.query or "?" in url or partes.fragment
            or "#" in url or ";" in url or partes.path not in ("", "/", CAMINHO_DA_API, CAMINHO_DA_API + "/")):
        raise invalida
    if not (host.endswith(DOMINIO_DO_CONTAINER_APPS) and _PADRAO_HOST.fullmatch(host)):
        raise ErroLab(f"--url: o host precisa ser o endereço padrão do Azure Container Apps, que termina em {DOMINIO_DO_CONTAINER_APPS} "
                      "(inclusive o formato interno <aplicativo>.internal.<ambiente>.<região>.azurecontainerapps.io). Domínio personalizado, "
                      "localhost, endereço IP e outros domínios não são aceitos. Nenhum token foi enviado.")
    if porta not in (None, 443):
        raise ErroLab("--url: só a porta 443, a padrão do HTTPS, é aceita para o endereço padrão do Azure Container Apps.")
    return Destino(f"https://{host}", host)


def validar_nome_da_variavel(nome: str | None) -> str:
    if nome is None:
        return VAR_TOKEN
    if not _PADRAO_NOME_DE_VARIAVEL.fullmatch(nome):
        raise ErroLab("--token-env: informe o NOME de uma variável de ambiente (letras, números e sublinhado), não o token.")
    return nome


def nome_visivel(nome: str) -> str:
    """O nome padrão aparece nas mensagens; um nome informado não, para um token digitado no lugar do nome não ser repetido."""
    return nome if nome == VAR_TOKEN else "indicada em --token-env"


def ler_token(ambiente: Mapping[str, str], nome: str) -> str | None:
    """O token da variável, ou None se ela não existe ou está vazia. Um valor sem a forma de um token é recusado, sem repeti-lo."""
    bruto = (ambiente.get(nome) or "").strip()
    if not bruto:
        return None
    if not _PADRAO_TOKEN.fullmatch(bruto):
        raise ErroLab(f"A variável do token ({nome_visivel(nome)}) não tem a forma de um token de acesso (Bearer); o valor não é repetido aqui.")
    return bruto


def validar_identidade(client_id: str | None, audiencia: str | None) -> Identidade:
    problemas = []
    if client_id is None or not _PADRAO_GUID.fullmatch(client_id):
        problemas.append("--client-id: informe o ID (GUID) do cliente da identidade gerenciada atribuída ao Job.")
    if audiencia is None or not _PADRAO_AUDIENCIA.fullmatch(audiencia):
        problemas.append("--audiencia: informe api://<ID do aplicativo de login>/.default, com o ID em formato de GUID.")
    if problemas:
        raise ErroLab(" ".join(problemas))
    return Identidade(client_id.lower(), audiencia)


def pasta_de_dados() -> Path:
    """A pasta dados/ do projeto, onde estão os conjuntos de avaliação. Em uma imagem de Job ela pode faltar ou não ter conjuntos."""
    return lab_comum.RAIZ / "dados"


_PREFIXOS_ESPECIAIS_DO_WINDOWS = ("\\\\?\\", "\\\\.\\", "//?/", "//./")


def _caminho_canonico(caminho: str | Path) -> str:
    """O caminho REAL (links simbólicos e junções resolvidos), sem prefixo `\\\\?\\` e em minúsculas no Windows. Qualquer falha recusa."""
    try:
        real = os.path.realpath(os.fspath(caminho))
    except (OSError, RuntimeError, ValueError):
        raise ErroLab("--perguntas-arquivo: não foi possível resolver o caminho com segurança; use um caminho comum do seu computador.") from None
    for prefixo, troca in (("\\\\?\\UNC\\", "\\\\"), ("\\\\?\\", ""), ("\\\\.\\", "")):  # o realpath mantém o prefixo que veio na entrada
        if real.startswith(prefixo):
            real = troca + real[len(prefixo):]
            break
    return os.path.normcase(real)


def _recusar_conjuntos_de_avaliacao(caminho: str) -> None:
    """Recusa um arquivo dentro de uma pasta de avaliação de dados/, pelo caminho real. Falha fechada: o que não puder ser resolvido é recusado."""
    if caminho.startswith(_PREFIXOS_ESPECIAIS_DO_WINDOWS):
        raise ErroLab("--perguntas-arquivo: caminhos com prefixo especial do Windows (\\\\?\\ ou \\\\.\\) não são aceitos; use um caminho comum.")
    alvo, dados = _caminho_canonico(caminho), _caminho_canonico(pasta_de_dados())
    if alvo != dados and not alvo.startswith(dados + os.sep):
        return
    if any(parte.startswith("avaliacao") for parte in alvo[len(dados):].casefold().split(os.sep)):
        raise ErroLab("--perguntas-arquivo: os conjuntos de avaliação de dados/ (inclusive o final do L400) não servem para carga; "
                      "use perguntas de desenvolvimento, em outra pasta.")


def _forma_simples(texto: str) -> str:
    """A pergunta sem diferença de maiúsculas, acentos, pontuação e espaços: copiar um conjunto com pequenos ajustes continua sendo copiar."""
    sem_acentos = "".join(letra for letra in unicodedata.normalize("NFD", texto.casefold()) if unicodedata.category(letra) != "Mn")
    return " ".join(re.findall(r"[a-z0-9]+", sem_acentos))


def perguntas_de_avaliacao(pasta: Path) -> list[str]:
    """Toda pergunta de todo JSON de `pasta` (avaliações finais, conjuntos de ajuste e de conferência). Falha fechada: arquivo ilegível recusa."""
    encontradas: list[str] = []

    def coletar(no: Any) -> None:
        if isinstance(no, dict):
            for chave, valor in no.items():
                if chave == "pergunta" and isinstance(valor, str):
                    encontradas.append(valor)
                else:
                    coletar(valor)
        elif isinstance(no, list):
            for item in no:
                coletar(item)

    try:
        for arquivo in sorted(pasta.rglob("*.json")):
            coletar(json.loads(arquivo.read_text(encoding="utf-8-sig")))
    except (OSError, ValueError, RecursionError):
        raise ErroLab("--perguntas-arquivo: não foi possível ler os conjuntos de avaliação de dados/ para conferir as perguntas; "
                      "corrija ou remova o arquivo ilegível.") from None
    return encontradas


def conferir_com_os_conjuntos(perguntas: Sequence[str]) -> tuple[str, int]:
    """Recusa a pergunta igual a alguma de dados/**/*.json. Devolve a situação da conferência e quantas perguntas de dados/ foram comparadas.

    Sem a pasta dados/ ou sem conjuntos nela (uma imagem de Job) a conferência por conteúdo é impossível: é de melhor esforço, e quem opera
    é responsável por não usar o conjunto final.
    """
    pasta = pasta_de_dados()
    try:
        existe = pasta.is_dir()
    except (OSError, ValueError):
        raise ErroLab("--perguntas-arquivo: não foi possível consultar a pasta dados/ para conferir as perguntas.") from None
    conhecidas = perguntas_de_avaliacao(pasta) if existe else []
    if not conhecidas:
        return CONFERENCIA_INDISPONIVEL, 0
    normalizadas = {lab_politica.normalizar(texto) for texto in conhecidas}
    simples = {forma for forma in map(_forma_simples, conhecidas) if forma}
    iguais = [posicao for posicao, texto in enumerate(perguntas, start=1)
              if lab_politica.normalizar(texto) in normalizadas or _forma_simples(texto) in simples]
    if iguais:
        raise ErroLab("--perguntas-arquivo: " + ", ".join(f"o item {posicao}" for posicao in iguais[:10]) + " é igual a uma pergunta de um "
                      "conjunto de avaliação de dados/ (final, de ajuste ou de conferência). Use perguntas de desenvolvimento.")
    return CONFERENCIA_FEITA, len(conhecidas)


@dataclass(frozen=True)
class PerguntasCarregadas:
    textos: tuple[str, ...] = field(repr=False)
    origem: str
    conferencia: str
    comparadas: int


def carregar_perguntas(caminho: str | None) -> PerguntasCarregadas:
    """As perguntas embutidas ou as de um JSON local (lista de textos), validadas com as regras do próprio chat; nunca são impressas."""
    if caminho is None:
        return PerguntasCarregadas(PERGUNTAS_EMBUTIDAS, "embutidas", CONFERENCIA_NAO_SE_APLICA, 0)
    _recusar_conjuntos_de_avaliacao(caminho)  # antes de abrir o arquivo
    arquivo = Path(caminho)
    try:
        if not arquivo.is_file():
            raise ErroLab("--perguntas-arquivo: arquivo não encontrado.")
        if arquivo.stat().st_size > LIMITE_DO_ARQUIVO_DE_PERGUNTAS:
            raise ErroLab(f"--perguntas-arquivo: o arquivo passa de {LIMITE_DO_ARQUIVO_DE_PERGUNTAS // 1024} KiB.")
        bruto = arquivo.read_bytes()
    except OSError:
        raise ErroLab("--perguntas-arquivo: não foi possível ler o arquivo.") from None
    try:  # o PowerShell 5 grava redirecionamentos em UTF-16; os demais editores, em UTF-8, às vezes com marca de ordem (BOM)
        texto = bruto.decode("utf-16") if bruto.startswith((b"\xff\xfe", b"\xfe\xff")) else bruto.decode("utf-8-sig")
        dados = json.loads(texto)
    except (ValueError, RecursionError):
        raise ErroLab("--perguntas-arquivo: o arquivo não é um JSON válido (UTF-8 ou UTF-16 com marca de ordem).") from None
    if not isinstance(dados, list) or not 1 <= len(dados) <= PERGUNTAS_NO_ARQUIVO_MAXIMAS:
        raise ErroLab(f"--perguntas-arquivo: o JSON deve ser uma lista de 1 a {PERGUNTAS_NO_ARQUIVO_MAXIMAS} textos.")
    problemas = []
    for posicao, item in enumerate(dados, start=1):
        if not isinstance(item, str):
            problemas.append(f"o item {posicao} não é um texto")
            continue
        try:  # o mesmo critério do chat: texto vazio, longo demais ou com caracteres de controle
            lab_chat.ler_pedido(json.dumps({"pergunta": item}).encode("utf-8"), "application/json")
        except lab_chat.ErroChat as erro:
            problemas.append(f"o item {posicao} foi recusado pelo chat ({erro.codigo})")
    if problemas:
        raise ErroLab("--perguntas-arquivo: " + "; ".join(problemas[:10]) + ".")
    conferencia, comparadas = conferir_com_os_conjuntos(dados)
    return PerguntasCarregadas(tuple(dados), "arquivo", conferencia, comparadas)


def validar_caminho_do_relatorio(caminho: str) -> Path:
    try:
        absoluto = Path(caminho).expanduser().resolve(strict=False)
        existe = os.path.lexists(absoluto)
        pasta_existe = absoluto.parent.is_dir()
    except (OSError, RuntimeError, ValueError):
        raise ErroLab("--relatorio: caminho inválido.") from None
    if existe:
        raise ErroLab("--relatorio: o arquivo já existe. O gerador nunca sobrescreve: escolha um caminho novo.")
    if not pasta_existe:
        raise ErroLab("--relatorio: a pasta não existe. Crie a pasta antes.")
    return absoluto


def validar_argumentos(args: argparse.Namespace, ambiente: Mapping[str, str]) -> Configuracao:
    """Confere tudo antes de qualquer rede e lista todos os problemas de uma vez, sem repetir os valores recebidos."""
    problemas = _Problemas()
    pedidos = problemas.tentar(_inteiro, "--pedidos", args.pedidos, PEDIDOS_PADRAO, 1, PEDIDOS_MAXIMOS)
    concorrencia = problemas.tentar(_inteiro, "--concorrencia", args.concorrencia, CONCORRENCIA_PADRAO, 1, CONCORRENCIA_MAXIMA)
    if pedidos is not None and concorrencia is not None:
        if args.concorrencia is None:
            concorrencia = min(concorrencia, pedidos)  # o padrão se ajusta a poucos pedidos; um valor informado nunca passa deles
        elif concorrencia > pedidos:
            problemas.adicionar("--concorrencia: não pode ser maior que --pedidos.")
    tempo_maximo = problemas.tentar(_segundos, "--tempo-maximo", args.tempo_maximo, TEMPO_TOTAL_PADRAO, TEMPO_TOTAL_MINIMO,
                                    TEMPO_TOTAL_MAXIMO)
    tempo_por_pedido = problemas.tentar(_segundos, "--tempo-por-pedido", args.tempo_por_pedido, TEMPO_POR_PEDIDO_PADRAO,
                                        TEMPO_POR_PEDIDO_MINIMO, TEMPO_POR_PEDIDO_MAXIMO)
    falhas = problemas.tentar(_inteiro, "--falhas-seguidas", args.falhas_seguidas, FALHAS_SEGUIDAS_PADRAO, 1, FALHAS_SEGUIDAS_MAXIMAS)
    esperar = problemas.tentar(validar_esperar, args.esperar)
    destino = problemas.tentar(validar_url, args.url)
    perguntas = problemas.tentar(carregar_perguntas, args.perguntas_arquivo)
    relatorio = problemas.tentar(validar_caminho_do_relatorio, args.relatorio) if args.relatorio is not None else None
    if args.executar and not args.confirmo_consumo:
        problemas.adicionar("A execução real consome tokens e gera custo, e cancelar localmente não interrompe um pedido já enviado: "
                            "confirme com --confirmo-consumo, junto de --executar. Nada foi enviado.")
    nome = token = identidade = None
    if args.identidade_gerenciada:
        if args.token_env is not None:
            problemas.adicionar("--token-env não combina com --identidade-gerenciada: escolha uma das duas fontes de token.")
        identidade = problemas.tentar(validar_identidade, args.client_id, args.audiencia)
    else:
        if args.client_id is not None or args.audiencia is not None:
            problemas.adicionar("--client-id e --audiencia só valem com --identidade-gerenciada.")
        nome = problemas.tentar(validar_nome_da_variavel, args.token_env)
        if nome is not None:
            try:
                token = ler_token(ambiente, nome)
            except ErroLab as erro:
                problemas.adicionar(str(erro))
            else:
                if token is None and args.executar:
                    problemas.adicionar(f"Defina a variável de ambiente do token ({nome_visivel(nome)}) na sua sessão antes de executar; "
                                        "o valor nunca é impresso nem gravado.")
    problemas.exigir()
    plano = Plano(pedidos, concorrencia, tempo_maximo, tempo_por_pedido, falhas, esperar, perguntas.textos, perguntas.origem,
                  perguntas.conferencia, perguntas.comparadas)
    return Configuracao(plano, destino, nome, token, identidade, relatorio, args.executar)


# --------------------------------------------------------------------------------------
# Segredos: o programa não os imprime; o redator garante isso mesmo se algum caminho um dia o fizer
# --------------------------------------------------------------------------------------

class Redator:
    """Troca por *** os valores sensíveis conhecidos (token, endereço, IDs e perguntas) que chegarem ao console."""

    def __init__(self, valores: Sequence[str | None] = ()) -> None:
        self._trava = threading.Lock()
        self._formas: list[str] = []
        for valor in valores:
            self.adicionar(valor)

    def adicionar(self, valor: str | None) -> None:
        if not valor or len(valor) < MENOR_VALOR_REDIGIDO:
            return
        novas = {valor, json.dumps(valor)[1:-1], json.dumps(valor, ensure_ascii=False)[1:-1]}
        with self._trava:
            self._formas = sorted({*self._formas, *novas}, key=len, reverse=True)

    def aplicar(self, texto: str) -> str:
        with self._trava:
            formas = tuple(self._formas)
        for forma in formas:
            texto = "***".join(texto.split(forma))
        return texto

    def contem(self, texto: str) -> bool:
        with self._trava:
            return any(forma in texto for forma in self._formas)


class _SaidaRedigida:
    def __init__(self, destino: Any, redator: Redator) -> None:
        self._destino, self._redator = destino, redator

    def write(self, texto: str) -> int:
        return self._destino.write(self._redator.aplicar(texto))

    def __getattr__(self, nome: str) -> Any:
        return getattr(self._destino, nome)


@contextmanager
def proteger_saida(redator: Redator) -> Iterator[None]:
    saida, erro = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = _SaidaRedigida(saida, redator), _SaidaRedigida(erro, redator)
    try:
        yield
    finally:
        sys.stdout, sys.stderr = saida, erro


def valores_sensiveis(args: argparse.Namespace, ambiente: Mapping[str, str]) -> list[str | None]:
    """O que deve ser redigido desde o início: o token da variável e o que veio das opções (endereço, host e IDs).

    O host só entra se for um destino aceito, com rótulos próprios na frente do domínio padrão: o domínio sozinho, localhost e os demais
    hosts recusados nunca são impressos, e redigi-los trocaria por asteriscos as palavras das mensagens de erro.
    """
    valores: list[str | None] = [args.url, args.client_id, args.audiencia]
    nome = args.token_env if args.token_env and _PADRAO_NOME_DE_VARIAVEL.fullmatch(args.token_env) else VAR_TOKEN
    bruto = ambiente.get(nome) or ""
    valores += [bruto, bruto.strip()]
    try:
        host = urllib.parse.urlsplit(args.url or "").hostname or ""
    except ValueError:
        host = ""
    if host.endswith(DOMINIO_DO_CONTAINER_APPS) and len(host) > len(DOMINIO_DO_CONTAINER_APPS):
        valores.append(host)
    return valores


# --------------------------------------------------------------------------------------
# Token da identidade gerenciada (só no Job da rede; o modo local não importa o Azure)
# --------------------------------------------------------------------------------------

class ErroDeToken(Exception):
    """Não foi possível obter o token. Guarda só o código AADSTS, que não identifica nada: o texto do erro é descartado."""

    def __init__(self, codigo_entra: str | None = None):
        super().__init__("token indisponível")
        self.codigo_entra = codigo_entra


class FonteGerenciada:
    """O token da identidade gerenciada do Job. Criar a fonte não usa a rede (e falha antes de qualquer relatório); só `obter` pede o token."""

    def __init__(self, identidade: Identidade) -> None:
        try:
            import lab_ingestao_l300  # só aqui: o modo com o token em variável de ambiente não precisa do Azure
        except ImportError:
            raise ErroLab("Não foi possível carregar a identidade gerenciada (módulos lab_ingestao_l300 e lab_ingestao e pacote "
                          "azure-identity). Ative o ambiente virtual e execute: python -m pip install -r requirements/l400.txt") from None
        self._audiencia = identidade.audiencia
        self._credencial = lab_ingestao_l300.criar_credencial_gerenciada(identidade.client_id)

    def obter(self) -> str:
        """Pede o token. O texto do erro é descartado: o texto pode ter IDs do ambiente, e só o código AADSTS é guardado."""
        try:
            acesso = self._credencial.get_token(self._audiencia)
        except Exception as erro:  # noqa: BLE001
            achado = _PADRAO_CODIGO_ENTRA.search(str(erro))
            raise ErroDeToken(f"AADSTS{achado.group(1)}" if achado else None) from None
        token = getattr(acesso, "token", None)
        if not isinstance(token, str) or not _PADRAO_TOKEN.fullmatch(token):
            raise ErroDeToken()
        return token

    def fechar(self) -> None:
        fechar = getattr(self._credencial, "close", None)
        if callable(fechar):
            fechar()


# --------------------------------------------------------------------------------------
# Transporte: um POST, sem repetir e sem seguir redirecionamentos
# --------------------------------------------------------------------------------------

class FalhaDeTransporte(Exception):
    """Nenhuma resposta HTTP utilizável. O rótulo é de um vocabulário fechado, nunca o texto de uma exceção."""

    def __init__(self, rotulo: str):
        super().__init__(rotulo)
        self.rotulo = rotulo


@dataclass(frozen=True)
class RespostaHttp:
    status: int
    corpo: bytes = field(repr=False)
    tipo_de_conteudo: str = "application/json"
    id_requisicao_presente: bool = False  # só a presença do X-Request-Id; o valor não é guardado


Transporte = Callable[[str, bytes, Mapping[str, str], float], RespostaHttp]


class _SemRedirecionamento(urllib.request.HTTPRedirectHandler):
    """Nenhum redirecionamento é seguido: o token e a pergunta só vão ao destino informado."""

    def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> None:
        return None


def _ler_corpo(resposta: Any, prazo: float) -> bytes:
    """Lê no máximo `LIMITE_DA_RESPOSTA` bytes, mesmo sem Content-Length ou com um valor falso, e para no prazo."""
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


def _causa_da_falha(motivo: Any) -> str:
    if isinstance(motivo, TimeoutError):
        return "tempo_esgotado"
    if isinstance(motivo, ssl.SSLError):
        return "tls"
    return "dns" if isinstance(motivo, socket.gaierror) else "conexao"


def _resposta(status: int, corpo: bytes, cabecalhos: Any) -> RespostaHttp:
    identificador = cabecalhos.get("X-Request-Id", "") or ""
    return RespostaHttp(status, corpo, cabecalhos.get("Content-Type", "") or "", bool(_PADRAO_ID_DA_REQUISICAO.fullmatch(identificador)))


def enviar_http(url: str, corpo: bytes, cabecalhos: Mapping[str, str], timeout: float) -> RespostaHttp:
    """Um POST direto ao destino, sem repetir e sem seguir redirecionamentos, com o certificado verificado e a resposta limitada em bytes.

    Os proxies do ambiente (https_proxy, http_proxy, all_proxy e o registro do Windows) são ignorados de propósito: o token não pode passar
    por um intermediário implícito. Quem precisar de proxy terá de pedir essa decisão explicitamente; hoje não há opção para isso.
    """
    abridor = urllib.request.build_opener(urllib.request.ProxyHandler({}), _SemRedirecionamento())  # o ProxyHandler vazio substitui o do ambiente
    requisicao = urllib.request.Request(url, data=corpo, headers=dict(cabecalhos), method="POST")
    prazo = time.monotonic() + timeout
    try:
        with abridor.open(requisicao, timeout=timeout) as resposta:
            return _resposta(resposta.status, _ler_corpo(resposta, prazo), resposta.headers)
    except urllib.error.HTTPError as erro:
        try:
            return _resposta(erro.code, _ler_corpo(erro, prazo), erro.headers)
        finally:
            erro.close()
    except urllib.error.URLError as erro:
        raise FalhaDeTransporte(_causa_da_falha(erro.reason)) from None
    except TimeoutError:
        raise FalhaDeTransporte("tempo_esgotado") from None
    except ssl.SSLError:
        raise FalhaDeTransporte("tls") from None
    except socket.gaierror:
        raise FalhaDeTransporte("dns") from None
    except (http.client.HTTPException, OSError, ValueError):
        raise FalhaDeTransporte("conexao") from None


# --------------------------------------------------------------------------------------
# O formato público da resposta: só o necessário é lido, o resto é descartado
# --------------------------------------------------------------------------------------

class PayloadInvalido(Exception):
    """A resposta 200 não tem o formato público do chat."""


@dataclass(frozen=True)
class RespostaPublica:
    tipo: str
    evidencias: int
    uso: Mapping[str, int] | None
    simulada: bool


def _contagem_valida(valor: Any) -> bool:
    return isinstance(valor, int) and not isinstance(valor, bool) and 0 <= valor <= MAXIMO_DE_TOKENS


def interpretar_resposta(corpo: bytes, tipo_de_conteudo: str) -> RespostaPublica:
    """Confere o formato público da resposta 200 e guarda só o tipo, a quantidade de fontes e o uso: o texto e as citações são descartados."""
    if tipo_de_conteudo.split(";")[0].strip().lower() != "application/json":
        raise PayloadInvalido
    try:
        dados = json.loads(corpo.decode("utf-8"))
    except (ValueError, RecursionError):
        raise PayloadInvalido from None
    if not isinstance(dados, dict) or set(dados) != CAMPOS_DA_RESPOSTA:
        raise PayloadInvalido
    evidencias, uso = dados["evidencias"], dados["uso"]
    estrutura_ok = (
        dados["tipo"] in lab_politica.TIPOS and dados["situacao"] in SITUACOES
        and isinstance(dados["texto"], str) and isinstance(dados["aviso"], str) and isinstance(dados["aviso_simulacao"], str)
        and isinstance(dados["simulada"], bool) and isinstance(dados["id_requisicao"], str)
        and (dados["id"] is None or isinstance(dados["id"], str))
        and isinstance(evidencias, list)
        and all(isinstance(item, dict) and set(item) == CAMPOS_DA_EVIDENCIA and all(isinstance(valor, str) for valor in item.values())
                for item in evidencias)
        and (uso is None or (isinstance(uso, dict) and set(uso) == CAMPOS_DO_USO and all(_contagem_valida(valor) for valor in uso.values()))))
    if not estrutura_ok:
        raise PayloadInvalido
    return RespostaPublica(dados["tipo"], len(evidencias), dict(uso) if uso is not None else None, dados["simulada"])


def codigo_publico(corpo: bytes) -> str | None:
    """O código público do erro (vocabulário fechado do chat), se a resposta de erro o traz; a mensagem é descartada."""
    try:
        dados = json.loads(corpo.decode("utf-8"))
    except (ValueError, RecursionError):
        return None
    codigo = dados.get("erro") if isinstance(dados, dict) else None
    return codigo if isinstance(codigo, str) and codigo in lab_chat.MENSAGENS else None


def agora_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def hashes_do_conteudo(dados: bytes) -> dict[str, str]:
    """Os dois SHA-256 do mesmo arquivo, cada um com o nome do que mede: os bytes do disco e o texto com CRLF trocado por LF."""
    return {"sha256_bytes_brutos": lab_comum.calcular_sha256(dados),
            "sha256_normalizado_lf": lab_comum.calcular_sha256(lab_comum.normalizar_texto(dados))}


# --------------------------------------------------------------------------------------
# Um pedido: do envio à classe do resultado
# --------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Resultado:
    """Só o que não identifica a pergunta, o texto, o destino nem a requisição: classe, status, tempo e contagens."""

    posicao: int
    classe: str
    ms: int | None = None
    http: int | None = None
    erro_publico: str | None = None
    causa_de_rede: str | None = None
    tipo: str | None = None
    evidencias: int | None = None
    uso: Mapping[str, int] | None = None
    com_id_requisicao: bool = False


def resultado_de_falha(posicao: int, rotulo: str) -> Resultado:
    if rotulo == "tempo_esgotado":
        return Resultado(posicao, TIMEOUT)
    if rotulo == "corpo_grande":
        return Resultado(posicao, FORMATO_INVALIDO)
    return Resultado(posicao, FALHA_DE_REDE, causa_de_rede=rotulo if rotulo in CAUSAS_DE_REDE else "conexao")


def classificar(posicao: int, resposta: RespostaHttp, ms: int) -> Resultado:
    """A classe de uma resposta HTTP. O corpo é lido só para conferir o formato público; o texto é descartado."""
    status = resposta.status
    base = {"posicao": posicao, "ms": ms, "http": status, "com_id_requisicao": resposta.id_requisicao_presente}
    if not 100 <= status <= 599:
        return Resultado(classe=FORMATO_INVALIDO, **{**base, "http": None})
    if 300 <= status < 400:
        return Resultado(classe=REDIRECIONAMENTO, **base)
    if status == 200:
        try:
            lida = interpretar_resposta(resposta.corpo, resposta.tipo_de_conteudo)
        except PayloadInvalido:
            return Resultado(classe=FORMATO_INVALIDO, **base)
        if lida.simulada:
            return Resultado(classe=SIMULADA, **base)
        return Resultado(classe=OK, tipo=lida.tipo, evidencias=lida.evidencias, uso=lida.uso, **base)
    codigo = codigo_publico(resposta.corpo)
    if codigo == lab_chat.OCUPADO and status == 429:
        return Resultado(classe=OCUPADO, **base)
    if codigo is not None:
        return Resultado(classe=ERRO_PUBLICO, erro_publico=codigo, **base)
    return Resultado(classe=HTTP, **base)


def executar_pedido(posicao: int, pergunta: str, destino: Destino, token: str, limite: float, transporte: Transporte,
                    relogio: Callable[[], float]) -> Resultado:
    """Um único POST, sem repetir. O token só vai ao destino validado e a pergunta só vai no corpo."""
    cabecalhos = {"Content-Type": "application/json", "Accept": "application/json", "User-Agent": USER_AGENT,
                  "Authorization": f"Bearer {token}"}
    corpo = json.dumps({"pergunta": pergunta}, ensure_ascii=False).encode("utf-8")
    inicio = relogio()
    try:
        resposta = transporte(destino.url_do_pedido, corpo, cabecalhos, limite)
    except FalhaDeTransporte as falha:
        return resultado_de_falha(posicao, falha.rotulo)
    return classificar(posicao, resposta, round((relogio() - inicio) * 1000))


def descrever(resultado: Resultado, total: int, esperado: bool) -> str:
    etiqueta = ("[OK]" if resultado.classe == OK else "[ESPERADO]") if esperado else "[FALHA]"
    classe = resultado.classe + (f":{resultado.erro_publico}" if resultado.erro_publico else "")
    classe += f":{resultado.causa_de_rede}" if resultado.causa_de_rede else ""
    detalhes = []
    if resultado.http is not None:
        detalhes.append(f"HTTP {resultado.http}")
    if resultado.ms is not None:
        detalhes.append(f"{resultado.ms} ms")
    if resultado.classe == OK:
        detalhes += [str(resultado.tipo), f"{resultado.evidencias} fonte(s)", "uso informado" if resultado.uso else "uso desconhecido"]
    return f"  {etiqueta} pedido {resultado.posicao}/{total}: {classe}" + (f" ({', '.join(detalhes)})" if detalhes else "")


# --------------------------------------------------------------------------------------
# Execução concorrente
# --------------------------------------------------------------------------------------

class Execucao:
    """O estado de uma execução. Toda alteração acontece sob a trava; cada trabalhador só reserva um pedido e registra o resultado.

    Há exatamente `concorrencia` trabalhadores, e cada um tem no máximo um pedido em andamento: os pedidos simultâneos nunca passam do
    teto. Os trabalhadores são daemon: um segundo Ctrl+C ou o teto de tempo encerram o programa sem esperar um pedido preso.
    """

    def __init__(self, plano: Plano, destino: Destino, transporte: Transporte, relogio: Callable[[], float],
                 registrar: Callable[[str], None] = print) -> None:
        self.plano, self.destino, self.transporte, self.relogio, self._registrar = plano, destino, transporte, relogio, registrar
        self._token = ""
        self._trava = threading.Lock()
        self._fim = threading.Event()
        self._ativos = 0
        self.parar = threading.Event()  # sinal compartilhado: nenhum pedido novo começa depois dele
        self.proximo = 0  # pedidos já reservados, isto é, enviados ou em envio
        self.resultados: list[Resultado] = []
        self.seguidas = 0
        self.interrupcao: str | None = None
        self.defeito: str | None = None
        self.codigo_entra: str | None = None
        self.token_de_variavel = True
        self.encerrada = False
        self.inicio: float | None = None
        self.fim: float | None = None
        self.inicio_utc = self.fim_utc = ""

    def _interromper(self, motivo: str) -> None:  # quem chama já tem a trava
        self.interrupcao = self.interrupcao or motivo
        self.parar.set()

    def interromper(self, motivo: str) -> None:
        with self._trava:
            self._interromper(motivo)

    def _reservar(self) -> tuple[int, str, float] | None:
        """O próximo pedido (posição, pergunta, prazo) ou None quando a execução deve parar: sinal, pedidos esgotados ou fim do tempo de envio."""
        with self._trava:
            if self.parar.is_set() or self.proximo >= self.plano.pedidos:
                return None
            restante = self.plano.tempo_maximo - (self.relogio() - self.inicio)
            if restante < RESTANTE_MINIMO:
                self._interromper(MOTIVO_TEMPO)
                return None
            posicao = self.proximo
            self.proximo += 1
            return (posicao + 1, self.plano.perguntas[posicao % len(self.plano.perguntas)],
                    min(self.plano.tempo_por_pedido, restante))

    def _concluir(self, resultado: Resultado) -> None:
        with self._trava:
            if self.encerrada:  # um pedido abandonado depois do encerramento não muda mais nada
                return
            self.resultados.append(resultado)
            esperado = resultado.classe in self.plano.esperar
            self.seguidas = 0 if esperado else self.seguidas + 1
            self._registrar(descrever(resultado, self.plano.pedidos, esperado))
            if self.seguidas >= self.plano.falhas_seguidas:
                self._interromper(MOTIVO_FALHAS)

    def _trabalhar(self) -> None:
        try:
            while (pedido := self._reservar()) is not None:
                posicao, pergunta, limite = pedido
                self._concluir(executar_pedido(posicao, pergunta, self.destino, self._token, limite, self.transporte, self.relogio))
        except BaseException as erro:  # noqa: BLE001 - um defeito interrompe toda a carga; só o nome do tipo é guardado
            with self._trava:
                self.defeito = self.defeito or type(erro).__name__
                self._interromper(MOTIVO_DEFEITO)
        finally:
            with self._trava:
                self._ativos -= 1
                if self._ativos == 0:
                    self._fim.set()

    def _aguardar(self) -> None:
        """Espera os trabalhadores em passos curtos (para Ctrl+C valer) e desiste de quem passar do teto de tempo mais a folga."""
        while not self._fim.wait(PASSO_DA_ESPERA):
            if self.relogio() - self.inicio > self.plano.tempo_maximo + FOLGA_DE_ENCERRAMENTO:
                self.interromper(MOTIVO_TEMPO)
                return  # os pedidos ainda em andamento ficam sem resultado e contam como enviados

    def executar(self, token: str) -> None:
        self._token = token
        self.inicio = self.relogio()
        trabalhadores = [threading.Thread(target=self._trabalhar, name=f"carga-{numero}", daemon=True)
                         for numero in range(1, self.plano.concorrencia + 1)]
        self._ativos = len(trabalhadores)
        for trabalhador in trabalhadores:
            trabalhador.start()
        try:
            self._aguardar()
        except KeyboardInterrupt:
            self.interromper(MOTIVO_CANCELADO)
            print("\n[INTERROMPIDA] Nenhum pedido novo será enviado. Aguardando os já enviados "
                  "(Ctrl+C de novo para sair sem esperar; eles podem continuar consumindo no serviço).")
            try:
                self._aguardar()
            except KeyboardInterrupt:
                pass
        self.encerrar()

    def encerrar(self, motivo: str | None = None) -> None:
        """Fecha a execução: depois dela nenhum resultado entra, e o que não foi enviado fica como não enviado."""
        with self._trava:
            if motivo:
                self._interromper(motivo)
            self.encerrada = True
            self.parar.set()
            agora = self.relogio()
            self.inicio = agora if self.inicio is None else self.inicio
            self.fim = agora if self.fim is None else self.fim


# --------------------------------------------------------------------------------------
# Resumo, resultado e relatório
# --------------------------------------------------------------------------------------

def _percentil(ordenados: Sequence[int], percentual: int) -> int:
    return ordenados[max(0, math.ceil(percentual / 100 * len(ordenados)) - 1)]


def resumir_latencia(tempos: Sequence[int]) -> dict[str, Any]:
    """Mínima, mediana (p50), p95 e máxima em ms pelo método do posto mais próximo, o mesmo dos avaliadores; sem amostra, null."""
    ordenados = sorted(tempos)
    if not ordenados:
        return {"n": 0, "minima": None, "mediana": None, "p95": None, "maxima": None}
    return {"n": len(ordenados), "minima": ordenados[0], "mediana": _percentil(ordenados, 50), "p95": _percentil(ordenados, 95),
            "maxima": ordenados[-1]}


def resumir_uso(resultados: Sequence[Resultado], enviados: int) -> dict[str, Any]:
    """Soma só o uso informado. Onde o chat não informa, o consumo é desconhecido: nunca vira zero nem um total completo."""
    informados = [item.uso for item in resultados if item.uso is not None]
    soma = None
    if informados:
        soma = dict.fromkeys(sorted(CAMPOS_DO_USO), 0)
        for uso in informados:
            for nome, valor in uso.items():
                soma[nome] += valor
    return {"pedidos_com_uso_informado": len(informados), "pedidos_sem_uso_informado": max(enviados - len(informados), 0),
            "soma_do_uso_informado": soma, "observacao": OBSERVACAO_DO_USO}


def codigo_de_saida(execucao: Execucao, resultados: Sequence[Resultado], nao_enviados: int) -> int:
    if execucao.defeito is not None:
        return lab_comum.CODIGO_INESPERADO
    recusados = sum(1 for item in resultados if item.http in (401, 403))
    sem_resposta_http = bool(resultados) and all(item.classe in (TIMEOUT, FALHA_DE_REDE) for item in resultados)
    if execucao.interrupcao == MOTIVO_TOKEN or recusados or sem_resposta_http:
        return lab_comum.CODIGO_ACESSO
    fora_do_esperado = any(item.classe not in execucao.plano.esperar for item in resultados)
    if fora_do_esperado or execucao.interrupcao or nao_enviados:
        return lab_comum.CODIGO_DIVERGENCIA
    return lab_comum.CODIGO_OK


def montar_resultado(execucao: Execucao) -> dict[str, Any]:
    """O resultado que vai para a linha L400_CARGA_RESULTADO e para o relatório: contagens e vocabulários fechados, nunca texto."""
    plano = execucao.plano
    resultados = sorted(execucao.resultados, key=lambda item: item.posicao)
    enviados = execucao.proximo
    nao_enviados = plano.pedidos - enviados
    classes = dict.fromkeys(CLASSES, 0)
    classes.update(Counter(item.classe for item in resultados))
    com_http = [item.ms for item in resultados if item.http is not None and item.ms is not None]
    return {
        "esquema": VERSAO_DO_ESQUEMA,
        "relatorio": NOME_DO_RELATORIO,
        "status": "interrompido" if execucao.interrupcao else "concluido",
        "interrupcao": execucao.interrupcao,
        "pedidos": {"planejados": plano.pedidos, "enviados": enviados, "com_resultado": len(resultados),
                    "sem_resultado": enviados - len(resultados), "nao_enviados": nao_enviados},
        "concorrencia": plano.concorrencia,
        "tempo_decorrido_s": round(max((execucao.fim or 0.0) - (execucao.inicio or 0.0), 0.0), 3),
        "classes": classes,
        "erros_publicos": dict(sorted(Counter(item.erro_publico for item in resultados if item.erro_publico).items())),
        "codigos_http": dict(sorted(Counter(str(item.http) for item in resultados if item.http is not None).items())),
        "causas_de_rede": dict(sorted(Counter(item.causa_de_rede for item in resultados if item.causa_de_rede).items())),
        "esperado": sorted(plano.esperar),
        "divergentes": sum(1 for item in resultados if item.classe not in plano.esperar),
        "acessos_recusados": sum(1 for item in resultados if item.http in (401, 403)),
        "respostas_com_id_requisicao": sum(1 for item in resultados if item.com_id_requisicao),
        "tipos": dict(sorted(Counter(item.tipo for item in resultados if item.tipo).items())),
        "respostas_ok_com_evidencia": sum(1 for item in resultados if item.classe == OK and (item.evidencias or 0) > 0),
        "latencia_ms_ok": resumir_latencia([item.ms for item in resultados if item.classe == OK and item.ms is not None]),
        "latencia_ms_respostas_http": resumir_latencia(com_http),
        "aviso_latencia": AVISO_DA_LATENCIA,
        "uso": resumir_uso(resultados, enviados),
        "limites": {"tempo_maximo_s": plano.tempo_maximo, "folga_de_encerramento_s": FOLGA_DE_ENCERRAMENTO,
                    "tempo_por_pedido_s": plano.tempo_por_pedido, "falhas_seguidas": plano.falhas_seguidas,
                    "resposta_maxima_bytes": LIMITE_DA_RESPOSTA, "tentativas_automaticas": 0},
        "limite": LIMITE_DA_CARGA,
        "codigo_de_saida": codigo_de_saida(execucao, resultados, nao_enviados),
    }


def montar_relatorio(execucao: Execucao, resultado: Mapping[str, Any]) -> dict[str, Any]:
    plano = execucao.plano
    arquivo = Path(__file__).resolve()
    return {
        **resultado,
        "inicio_utc": execucao.inicio_utc,
        "fim_utc": execucao.fim_utc,
        "destino": {"esquema": "https", "caminho": CAMINHO_DA_API},
        "identidade": {"tipo": "bearer_de_variavel_de_ambiente" if execucao.token_de_variavel else "identidade_gerenciada"},
        "perguntas": {"origem": plano.origem_das_perguntas, "quantidade": len(plano.perguntas),
                      "conferencia_com_avaliacoes": plano.conferencia_das_perguntas,
                      "comparadas_com_avaliacoes": plano.perguntas_comparadas},
        "tetos": {"pedidos": PEDIDOS_MAXIMOS, "concorrencia": CONCORRENCIA_MAXIMA, "tempo_maximo_s": TEMPO_TOTAL_MAXIMO,
                  "tempo_por_pedido_s": TEMPO_POR_PEDIDO_MAXIMO, "falhas_seguidas": FALHAS_SEGUIDAS_MAXIMAS},
        "gerador": {"arquivo": f"scripts/{arquivo.name}", "versao": VERSAO_DO_GERADOR, **hashes_do_conteudo(arquivo.read_bytes())},
        "avisos": [AVISO_DE_CONSUMO, AVISO_DE_CANCELAMENTO, AVISO_DE_CAPACIDADE],
        "pedidos_detalhe": [{"posicao": item.posicao, "classe": item.classe, "esperado": item.classe in plano.esperar, "http": item.http,
                             "ms": item.ms, "erro_publico": item.erro_publico, "causa_de_rede": item.causa_de_rede, "tipo": item.tipo,
                             "evidencias": item.evidencias, "uso": dict(item.uso) if item.uso is not None else None,
                             "com_id_requisicao": item.com_id_requisicao}
                            for item in sorted(execucao.resultados, key=lambda resultado_: resultado_.posicao)],
    }


def reservar_relatorio(caminho: Path) -> Any:
    """Cria o arquivo ANTES da rede, em modo exclusivo (nunca sobrescreve), legível só pelo dono em POSIX, com um marcador em andamento."""
    try:
        descritor = os.open(caminho, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raise ErroLab("--relatorio: o arquivo já existe. O gerador nunca sobrescreve: escolha um caminho novo.") from None
    except OSError:
        raise ErroLab("Não foi possível criar o relatório (--relatorio). Confira a pasta e as permissões.") from None
    arquivo = os.fdopen(descritor, "w", encoding="utf-8", newline="\n")
    try:
        gravar_relatorio(arquivo, json.dumps({"esquema": VERSAO_DO_ESQUEMA, "relatorio": NOME_DO_RELATORIO, "status": "em_andamento"}) + "\n")
    except OSError:
        arquivo.close()
        raise ErroLab("Não foi possível gravar no relatório (--relatorio). Confira a pasta e o espaço em disco.") from None
    return arquivo


def gravar_relatorio(arquivo: Any, texto: str) -> None:
    arquivo.seek(0)
    arquivo.truncate()
    arquivo.write(texto)
    arquivo.flush()
    os.fsync(arquivo.fileno())


def decimal(valor: float, casas: int = 1) -> str:
    return f"{valor:.{casas}f}".replace(".", ",")


def _descrever_latencia(nome: str, latencia: Mapping[str, Any]) -> str:
    if not latencia["n"]:
        return f"{nome}: sem amostra"
    return (f"{nome}: mínima {latencia['minima']} · mediana {latencia['mediana']} · p95 {latencia['p95']} · "
            f"máxima {latencia['maxima']} ms (n={latencia['n']})")


def mostrar_resumo(resultado: Mapping[str, Any], execucao: Execucao, caminho: Path | None) -> None:
    pedidos = resultado["pedidos"]
    print(f"\nResultado: {pedidos['enviados']} de {pedidos['planejados']} pedido(s) enviado(s), {pedidos['com_resultado']} com resultado, "
          f"{resultado['divergentes']} fora do esperado ({', '.join(resultado['esperado'])}) · tempo {decimal(resultado['tempo_decorrido_s'])} s")
    print("  Classes: " + (" · ".join(f"{nome} {total}" for nome, total in resultado["classes"].items() if total) or "nenhuma"))
    for rotulo, chave in (("Erros públicos", "erros_publicos"), ("Códigos HTTP", "codigos_http"), ("Falhas de rede", "causas_de_rede"),
                          ("Tipos de resposta", "tipos")):
        if resultado[chave]:
            print(f"  {rotulo}: " + " · ".join(f"{nome} {total}" for nome, total in resultado[chave].items()))
    print(f"  Respostas com X-Request-Id: {resultado['respostas_com_id_requisicao']} (o valor não é guardado)")
    print(f"  Latência {_descrever_latencia('das respostas ok', resultado['latencia_ms_ok'])}")
    print(f"  Latência {_descrever_latencia('de todas as respostas HTTP', resultado['latencia_ms_respostas_http'])}")
    print(f"  [AVISO] {AVISO_DA_LATENCIA}")
    uso = resultado["uso"]
    if uso["soma_do_uso_informado"] is None:
        print("  Tokens: o chat não informou o uso em nenhum pedido (desconhecido, não zero).")
    else:
        soma = " · ".join(f"{nome} {valor}" for nome, valor in uso["soma_do_uso_informado"].items())
        print(f"  Tokens: uso informado em {uso['pedidos_com_uso_informado']} pedido(s); em {uso['pedidos_sem_uso_informado']} o consumo é "
              f"desconhecido (não zero). Soma parcial: {soma}. Não é o total consumido nem o custo.")
    if pedidos["sem_resultado"]:
        print(f"  [AVISO] {pedidos['sem_resultado']} pedido(s) enviado(s) ficaram sem resultado: ainda podem consumir tokens no serviço.")
    if execucao.interrupcao:
        print(f"  [INTERROMPIDA] {DESCRICAO_DA_INTERRUPCAO[execucao.interrupcao]}; {pedidos['nao_enviados']} pedido(s) não foram enviados.")
    if execucao.interrupcao == MOTIVO_TOKEN:
        codigo = f" ({execucao.codigo_entra})" if execucao.codigo_entra else ""
        print(f"  [ERRO] Não foi possível obter o token da identidade gerenciada{codigo}. Confira a identidade atribuída ao Job, o "
              "--client-id e a audiência; nenhum pedido foi enviado.")
    if resultado["acessos_recusados"]:
        print(f"  [ERRO] O destino recusou a autenticação (HTTP 401 ou 403) em {resultado['acessos_recusados']} pedido(s). Confira o token, "
              "a audiência (api://<ID do aplicativo de login>/.default) e o papel da identidade.")
    elif resultado["codigo_de_saida"] == lab_comum.CODIGO_ACESSO and execucao.interrupcao != MOTIVO_TOKEN:
        print("  [ERRO] Nenhuma resposta HTTP foi recebida. Confira o endereço, o DNS e o TLS: um ambiente interno só resolve dentro da "
              "rede privada, e o gerador precisa rodar de onde o endereço é alcançável sem proxy (os proxies do ambiente são ignorados "
              "de propósito).")
    print(f"  [LIMITE] {AVISO_DE_CAPACIDADE}")
    if caminho is not None:
        print(f"  Relatório gravado em {caminho} (arquivo novo, sem endereço, perguntas, textos, tokens nem identificadores).")


def mostrar_plano(configuracao: Configuracao) -> None:
    plano, destino = configuracao.plano, configuracao.destino
    print("Gerador de carga L400: pedidos concorrentes e finitos em POST /api/perguntar")
    print(f"  Destino: {destino.mascarado} (mascarado; o endereço completo nunca é impresso nem gravado; caminho fixo {CAMINHO_DA_API})")
    print("  Rede: conexão direta ao destino, com o certificado verificado; os proxies do ambiente são ignorados de propósito")
    print(f"  Pedidos: {plano.pedidos} (teto {PEDIDOS_MAXIMOS}) · concorrência: {plano.concorrencia} (teto {CONCORRENCIA_MAXIMA}, "
          "nunca acima dos pedidos)")
    print(f"  Tempo: pedidos novos só saem durante {plano.tempo_maximo:g} s (teto {TEMPO_TOTAL_MAXIMO:g} s); os já enviados têm até mais "
          f"{FOLGA_DE_ENCERRAMENTO:g} s para terminar, então o processo dura até {plano.tempo_maximo + FOLGA_DE_ENCERRAMENTO:g} s depois do "
          "primeiro envio; o tempo de obter o token da identidade gerenciada fica fora dessa conta")
    print(f"  Por pedido: {plano.tempo_por_pedido:g} s (teto {TEMPO_POR_PEDIDO_MAXIMO:g} s); resposta de até {LIMITE_DA_RESPOSTA // 1024} KiB")
    print(f"  Parada: depois de {plano.falhas_seguidas} resultado(s) seguido(s) fora do esperado; nenhuma tentativa automática (nenhum retry)")
    print(f"  Esperado: {', '.join(sorted(plano.esperar))} (qualquer outra classe é divergência, sai com 3 e conta para a parada)")
    print(f"  Perguntas: {len(plano.perguntas)} {plano.origem_das_perguntas}, usadas em rodízio (os textos nunca são impressos nem gravados)")
    if plano.conferencia_das_perguntas == CONFERENCIA_FEITA:
        print(f"  Perguntas conferidas com as {plano.perguntas_comparadas} de avaliação de dados/: nenhuma é igual (melhor esforço: "
              "perguntas reescritas não são detectadas)")
    elif plano.conferencia_das_perguntas == CONFERENCIA_INDISPONIVEL:
        print("  [AVISO] Sem a pasta dados/ (ou sem conjuntos de avaliação nela), o arquivo de perguntas NÃO foi conferido contra eles: "
              "quem opera é responsável por não usar o conjunto final.")
    if configuracao.identidade is not None:
        print("  Autenticação: identidade gerenciada (client-id e audiência informados; o token só é pedido com --executar e nunca é impresso)")
    else:
        nome = configuracao.nome_da_variavel or VAR_TOKEN
        situacao = "definida" if configuracao.token else "NÃO definida: é obrigatória com --executar"
        print(f"  Autenticação: token Bearer da variável {nome_visivel(nome)} ({situacao}); o valor nunca é impresso")
    print("  Relatório: " + ("um arquivo novo será criado antes da rede (nunca sobrescreve)" if configuracao.relatorio is not None
                              else "nenhum (só a linha L400_CARGA_RESULTADO= no console)"))
    if plano.tempo_por_pedido < lab_chat.TEMPO_PADRAO:
        print(f"  [AVISO] O prazo por pedido ({plano.tempo_por_pedido:g} s) é menor que o padrão do chat ({lab_chat.TEMPO_PADRAO:g} s): "
              "um pedido lento pode ser abandonado aqui enquanto o serviço continua processando e consumindo.")
    print(f"  [CONSUMO] {AVISO_DE_CONSUMO}")
    print(f"  [CONSUMO] {AVISO_DE_CANCELAMENTO}")
    print(f"  [LIMITE] {AVISO_DE_CAPACIDADE}")


def executar_carga(configuracao: Configuracao, redator: Redator, transporte: Transporte, relogio: Callable[[], float]) -> int:
    fonte = FonteGerenciada(configuracao.identidade) if configuracao.identidade is not None else None  # sem rede; falha antes do relatório
    try:
        arquivo = reservar_relatorio(configuracao.relatorio) if configuracao.relatorio is not None else None  # antes de qualquer rede
        try:
            return _executar_e_registrar(configuracao, redator, transporte, relogio, fonte, arquivo)
        finally:
            if arquivo is not None:
                arquivo.close()
    finally:
        if fonte is not None:
            fonte.fechar()


def _executar_e_registrar(configuracao: Configuracao, redator: Redator, transporte: Transporte, relogio: Callable[[], float],
                          fonte: FonteGerenciada | None, arquivo: Any) -> int:
    plano = configuracao.plano
    execucao = Execucao(plano, configuracao.destino, transporte, relogio)
    execucao.token_de_variavel = fonte is None
    execucao.inicio_utc = agora_utc()
    try:
        token = configuracao.token
        if fonte is not None:
            print("\nPedindo o token à identidade gerenciada (nenhum pedido foi enviado ainda)...")
            token = fonte.obter()
            redator.adicionar(token)
        print(f"\nExecutando: até {plano.pedidos} pedido(s), {plano.concorrencia} ao mesmo tempo, em POST {CAMINHO_DA_API}:")
        execucao.executar(token or "")
    except ErroDeToken as erro:
        execucao.codigo_entra = erro.codigo_entra
        execucao.encerrar(MOTIVO_TOKEN)
    except KeyboardInterrupt:
        execucao.encerrar(MOTIVO_CANCELADO)
    except Exception as erro:  # noqa: BLE001 - o resultado registra a interrupção; só o nome do tipo do erro é guardado
        execucao.defeito = type(erro).__name__
        execucao.encerrar(MOTIVO_DEFEITO)
    execucao.encerrar()
    execucao.fim_utc = agora_utc()
    resultado = montar_resultado(execucao)
    linha = json.dumps(resultado, ensure_ascii=True, separators=(",", ":"))
    texto_do_relatorio = json.dumps(montar_relatorio(execucao, resultado), ensure_ascii=False, indent=2) + "\n"
    if redator.contem(linha) or redator.contem(texto_do_relatorio):
        raise ErroLab("O resultado continha um valor sensível (token, endereço, identificador ou pergunta) e NÃO foi impresso nem "
                      "gravado; o valor não é exibido.", lab_comum.CODIGO_INESPERADO)
    gravado = False
    if arquivo is not None:
        try:
            gravar_relatorio(arquivo, texto_do_relatorio)
            gravado = True
        except OSError:
            pass
    mostrar_resumo(resultado, execucao, configuracao.relatorio if gravado else None)
    erros = []
    if execucao.defeito is not None:
        erros.append(f"Defeito do gerador ({execucao.defeito}). Nenhum dado do ambiente foi impresso; o resultado registra a interrupção.")
    if arquivo is not None and not gravado:
        erros.append("Os pedidos foram enviados, mas não foi possível gravar o relatório final. O resumo e a linha de resultado no "
                     "console são o que existe.")
    sys.stdout.flush()  # com stdout e stderr no mesmo destino, a ordem é a das chamadas: os erros primeiro e a linha de resultado por último
    for erro in erros:
        print(f"[ERRO] {erro}", file=sys.stderr, flush=True)
    print(PREFIXO_DO_RESULTADO + linha, flush=True)
    return lab_comum.CODIGO_INESPERADO if erros else resultado["codigo_de_saida"]


# --------------------------------------------------------------------------------------
# Linha de comando
# --------------------------------------------------------------------------------------

def executar(args: argparse.Namespace, ambiente: Mapping[str, str], redator: Redator, transporte: Transporte | None,
             relogio: Callable[[], float] | None) -> int:
    for nome in ("azure", "msal"):
        logging.getLogger(nome).setLevel(logging.CRITICAL)
    configuracao = validar_argumentos(args, ambiente)
    for valor in (configuracao.token, *(pergunta for pergunta in configuracao.plano.perguntas if len(pergunta) >= MENOR_PERGUNTA_REDIGIDA)):
        redator.adicionar(valor)
    mostrar_plano(configuracao)
    if not configuracao.executar:
        print("\n[SIMULAÇÃO] Opções, endereço, perguntas e relatório conferem; nada foi enviado, nenhum token foi pedido e nenhum "
              "relatório foi criado. Para enviar de verdade, repita com --executar --confirmo-consumo.")
        return lab_comum.CODIGO_OK
    return executar_carga(configuracao, redator, transporte or enviar_http, relogio or time.perf_counter)  # perf_counter: no Windows, monotonic só mede de 15 em 15 ms


def traduzir_erro(erro: Exception, args: argparse.Namespace) -> tuple[str, int]:
    return (f"Erro inesperado do gerador ({type(erro).__name__}). Nenhum dado do ambiente foi impresso; se o relatório foi criado, "
            "ele registra a interrupção.", lab_comum.CODIGO_INESPERADO)


_PADRAO_NOME_DE_OPCAO = re.compile(r"--?[A-Za-z][A-Za-z0-9-]{0,39}")
_PADRAO_OPCAO_COM_VALOR_IGNORADO = re.compile(r"argument (--?[a-z][a-z-]*(?:/--?[a-z][a-z-]*)*): ignored explicit argument")
_PADRAO_ERRO_SEM_VALOR_DIGITADO = re.compile(r"the following arguments are required: --?[a-z][a-z-]*(?:, --?[a-z][a-z-]*)*"
                                             r"|argument --?[a-z][a-z-]*(?:/--?[a-z][a-z-]*)*: expected one argument")


class _ParserDaCarga(lab_comum.ParserLab):
    """O argparse repete o que foi digitado nos erros (inclusive com aspas desencontradas); aqui nenhum valor é repetido, no máximo o NOME
    de uma opção, para um token passado por engano não ir ao console. Só as mensagens que não carregam texto digitado passam como estão."""

    def parse_args(self, args: Sequence[str] | None = None,  # type: ignore[override]
                   namespace: argparse.Namespace | None = None) -> argparse.Namespace:
        conhecidos, extras = self.parse_known_args(args, namespace)
        if extras:
            nomes = [extra.split("=", 1)[0] for extra in extras if extra.startswith("-")]
            nomes = [nome for nome in nomes if _PADRAO_NOME_DE_OPCAO.fullmatch(nome)]
            partes = [f"opções desconhecidas: {', '.join(nomes[:10])}"] if nomes else []
            if len(extras) > len(nomes):
                partes.append(f"{len(extras) - len(nomes)} item(ns) sem nome de opção reconhecível")
            super().error(f"argumentos não reconhecidos ({'; '.join(partes)}). Só o nome de uma opção é mostrado, nunca o valor que vem "
                          "depois dela. Use --help")
        return conhecidos

    def error(self, message: str) -> None:  # type: ignore[override]
        ignorado = _PADRAO_OPCAO_COM_VALOR_IGNORADO.match(message)
        if ignorado:
            message = f"argument {ignorado.group(1)}: a opção não aceita valor (o valor informado não é repetido aqui)"
        elif not _PADRAO_ERRO_SEM_VALOR_DIGITADO.fullmatch(message):
            message = "argumentos inválidos (os valores informados não são repetidos aqui). Use --help"
        super().error(message)


def criar_parser() -> lab_comum.ParserLab:
    parser = _ParserDaCarga(description=__doc__, allow_abbrev=False)
    parser.add_argument("--url", required=True, metavar="URL",
                        help="Endereço do chat: https://<aplicativo>.<ambiente>.<região>.azurecontainerapps.io (o formato interno, com "
                             ".internal., também vale), opcionalmente terminando em /api/perguntar. Só HTTPS na porta 443, sem usuário, "
                             "senha, parâmetros nem fragmento; outros domínios (inclusive personalizados), localhost e IP são recusados. "
                             "Nunca é impresso nem gravado. Os proxies do ambiente são ignorados de propósito.")
    parser.add_argument("--pedidos", default=None, metavar="N",
                        help=f"Quantidade de pedidos de 1 a {PEDIDOS_MAXIMOS} (padrão: {PEDIDOS_PADRAO}). Cada um consome tokens.")
    parser.add_argument("--concorrencia", default=None, metavar="N",
                        help=f"Pedidos ao mesmo tempo, de 1 a {CONCORRENCIA_MAXIMA} e nunca mais que os pedidos (padrão: "
                             f"{CONCORRENCIA_PADRAO}, ou os pedidos, se forem menos).")
    parser.add_argument("--tempo-maximo", default=None, metavar="SEGUNDOS",
                        help=f"Tempo máximo para ENVIAR pedidos, de {TEMPO_TOTAL_MINIMO:g} a {TEMPO_TOTAL_MAXIMO:g} s (padrão: "
                             f"{TEMPO_TOTAL_PADRAO:g}). Depois dele, nenhum pedido novo sai; os já enviados têm até mais "
                             f"{FOLGA_DE_ENCERRAMENTO:g} s para terminar (o processo dura até o tempo máximo mais {FOLGA_DE_ENCERRAMENTO:g} s), "
                             "e o tempo de obter o token da identidade gerenciada fica fora dessa conta.")
    parser.add_argument("--tempo-por-pedido", default=None, metavar="SEGUNDOS",
                        help=f"Prazo de cada pedido, de {TEMPO_POR_PEDIDO_MINIMO:g} a {TEMPO_POR_PEDIDO_MAXIMO:g} s (padrão: "
                             f"{TEMPO_POR_PEDIDO_PADRAO:g}). Use mais que o prazo do chat ({lab_chat.TEMPO_PADRAO:g} s por padrão).")
    parser.add_argument("--falhas-seguidas", default=None, metavar="N",
                        help=f"Para depois de N resultados seguidos fora do esperado, de 1 a {FALHAS_SEGUIDAS_MAXIMAS} "
                             f"(padrão: {FALHAS_SEGUIDAS_PADRAO}).")
    parser.add_argument("--esperar", default=None, metavar="CLASSES",
                        help="Classes que não contam como divergência, separadas por vírgula, entre: " + ", ".join(CLASSES)
                             + f" (padrão: {OK}). Para exercitar a admissão, use ok,ocupado.")
    parser.add_argument("--perguntas-arquivo", default=None, metavar="ARQUIVO",
                        help=f"JSON local com uma lista de 1 a {PERGUNTAS_NO_ARQUIVO_MAXIMAS} perguntas (textos). NÃO use os conjuntos de "
                             "avaliação, sobretudo o final. A recusa é de melhor esforço: um arquivo em pastas de avaliação de dados/ ou "
                             "com perguntas iguais às de dados/**/*.json é recusado, e um caminho com prefixo especial do Windows ou que "
                             "não possa ser resolvido também; sem a pasta dados/ (imagem de Job) a conferência por conteúdo é "
                             "impossível e quem opera é responsável. Sem esta opção, valem as perguntas embutidas.")
    parser.add_argument("--token-env", default=None, metavar="NOME",
                        help=f"NOME da variável de ambiente com o token Bearer (padrão: {VAR_TOKEN}). O token nunca vem por argumento.")
    parser.add_argument("--identidade-gerenciada", action="store_true",
                        help="Pede o token à identidade gerenciada (para rodar dentro do Job da rede). Exige --client-id e --audiencia.")
    parser.add_argument("--client-id", default=None, metavar="GUID",
                        help="ID do cliente da identidade gerenciada atribuída ao Job (com --identidade-gerenciada).")
    parser.add_argument("--audiencia", default=None, metavar="ESCOPO",
                        help="api://<ID do aplicativo de login>/.default (com --identidade-gerenciada).")
    parser.add_argument("--relatorio", default=None, metavar="ARQUIVO",
                        help="Relatório JSON a criar, com o detalhe de cada pedido. O arquivo não pode existir: o gerador nunca sobrescreve.")
    parser.add_argument("--executar", action="store_true",
                        help="Envia os pedidos (consome tokens). Exige também --confirmo-consumo. Sem esta opção, só mostra o plano.")
    parser.add_argument("--confirmo-consumo", action="store_true",
                        help="Aceita, de forma explícita, que cada pedido enviado consome tokens e que cancelar localmente não "
                             "interrompe um pedido já enviado.")
    return parser


def principal(argv: Sequence[str] | None = None, *, env: Mapping[str, str] | None = None, transporte: Transporte | None = None,
              relogio: Callable[[], float] | None = None) -> int:
    lab_comum.configurar_saida()
    ambiente = dict(os.environ if env is None else env)
    args = criar_parser().parse_args(argv)
    redator = Redator(valores_sensiveis(args, ambiente))
    with proteger_saida(redator):
        try:
            return lab_comum.executar_com_tratamento(lambda a: executar(a, ambiente, redator, transporte, relogio), args,
                                                     tradutor=traduzir_erro)
        except KeyboardInterrupt:  # fora do laço dos pedidos; dentro dele, o resultado registra o cancelamento
            print("[INTERROMPIDA] A execução foi cancelada.", file=sys.stderr)
            return lab_comum.CODIGO_DIVERGENCIA


if __name__ == "__main__":
    sys.exit(principal())
