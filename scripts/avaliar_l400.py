"""Compara a referência (aplicação do L300) com a coordenação (aplicação do L400) pelo contrato HTTP do chat, sem modelo como juiz.

Cada caso do arquivo de casos (o mesmo formato do avaliar_chat.py) vira UM POST em /api/perguntar para cada estratégia, com o mesmo
corpo e os mesmos cabeçalhos; quem escolhe a estratégia é a aplicação (cada uma tem a sua configuração), nunca o cliente. O avaliador
confere, literalmente, o tipo e a situação esperados e os invariantes da apresentação, como o avaliar_chat.py: ele mede o contrato
e a política do chat, não a fidelidade semântica das respostas. Nenhum modelo julga nada.

Antes de qualquer chamada, o plano é congelado: casos em ordem de id, uma chamada por estratégia e caso, com a estratégia que vai
primeiro alternando de caso em caso. O plano tem um SHA-256 (plano_sha256), assim como o conjunto de casos (conjunto_sha256) e o
código avaliado (codigo_sha256); --plano-esperado, --conjunto-esperado e --codigo-esperado recusam a execução se algum deles for
diferente do que foi congelado. Falha de HTTP (inclusive 429 e 503), tempo esgotado, JSON inválido e caso não avaliado contam como
falha: o denominador é sempre o total de casos planejado, e uma resposta sem o campo de uso fica com uso desconhecido (nunca zero).

Sem --executar nem --simular (o padrão, que também se pede com --plano), só valida o arquivo de casos, os destinos, as credenciais e o relatório
e mostra o plano: nada é enviado e nenhum relatório é criado. Com --executar, o relatório é criado antes de qualquer rede, nunca sobrescreve um
arquivo e não guarda
perguntas, corpos de resposta, textos, citações, endereços, tokens nem identificadores; só contagens, códigos, tempos, tokens e rótulos
de vocabulário fechado. Com --simular, nada sai do computador: um transporte simulado responde o que cada caso espera, para ensaiar o
fluxo e o relatório (que fica marcado como simulado e nunca vale como medição).

Destinos (--url-referencia e --url-coordenacao, um para cada aplicação, recebidos explicitamente): HTTPS só para o endereço padrão do
Azure Container Apps (*.azurecontainerapps.io) ou HTTP em 127.0.0.1, localhost ou ::1, sem usuário, caminho, parâmetros nem fragmento; os
redirecionamentos nunca são seguidos. Os tokens de acesso (Bearer) vêm só de variáveis de ambiente, VARELEIRA_L400_TOKEN_REFERENCIA e
VARELEIRA_L400_TOKEN_COORDENACAO, nunca de argumentos nem de arquivos; ficam em memória e nunca são impressos nem gravados. Com HTTPS,
sem token a execução nem começa: o avaliador não tem opção para contornar a fronteira de acesso. Cada artefato avaliado (a imagem de cada
aplicação) é declarado por --artefato-referencia e --artefato-coordenacao (um digest sha256:<64 hex> ou uma tag imutável); o avaliador
não o confere com o serviço.

Custo (opcional): os preços por 1 milhão de tokens são informados por quem opera (--preco-entrada-1m, --preco-saida-1m,
--preco-embeddings-1m e --moeda); nenhum preço existe neste programa. O custo estimado só usa o uso que o chat informou, e é parcial
quando alguma resposta não o informou.

Limites: 100 casos (200 chamadas), 120 s por chamada, 128 KiB por resposta, 50 minutos no total e 3 falhas seguidas de transporte, ou de
acesso recusado (401 ou 403), por estratégia; o que sobra fica como não avaliado, e as chamadas nunca são repetidas.

Códigos de saída: 0 todos os casos passaram nas duas estratégias (ou o ensaio terminou); 1 uso ou entrada inválida; 2 acesso recusado
pelo destino; 3 divergência, falha, interrupção ou casos não avaliados; 4 defeito do avaliador.

Exemplos (o plano primeiro, sem enviar nada; depois a execução):
    python scripts\\avaliar_l400.py --casos <casos.json> --url-referencia <url-l300> --url-coordenacao <url-l400> --artefato-referencia <tag-ou-digest> --artefato-coordenacao <tag-ou-digest> --relatorio <novo.json>
    python scripts\\avaliar_l400.py --casos <casos.json> --relatorio <novo.json> --simular
    python scripts\\avaliar_l400.py --casos <casos.json> --url-referencia <url-l300> --url-coordenacao <url-l400> --artefato-referencia <tag-ou-digest> --artefato-coordenacao <tag-ou-digest> --relatorio <novo.json> --plano-esperado <sha256> --codigo-esperado <sha256> --executar
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import os
import re
import sys
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import avaliar_chat as ac
import lab_chat
import lab_comum
import lab_politica
import operar_l300 as o3
from lab_comum import ErroLab

VERSAO_DO_ESQUEMA = 1
VERSAO_DO_AVALIADOR = 1
NOME_DO_RELATORIO = "comparacao_l400"
ESTRATEGIAS = ("referencia", "coordenacao")
BASE = ESTRATEGIAS[0]
ROTULOS = {"referencia": "referência (L300)", "coordenacao": "coordenação (L400)"}
VAR_TOKEN = {"referencia": "VARELEIRA_L400_TOKEN_REFERENCIA", "coordenacao": "VARELEIRA_L400_TOKEN_COORDENACAO"}
USER_AGENT = f"vareleira-avaliar-l400/{VERSAO_DO_AVALIADOR}"
ORDEM_DO_PLANO = "id_ascendente_com_estrategia_alternada"

MAXIMO_DE_CASOS = ac.MAXIMO_DE_CASOS
TIMEOUT_DA_CHAMADA = ac.TIMEOUT_DA_CHAMADA
TEMPO_MAXIMO = 50 * 60.0  # segundos: duas chamadas por caso
FALHAS_SEGUIDAS = ac.FALHAS_DE_TRANSPORTE_SEGUIDAS
DOCKERFILE = lab_comum.RAIZ / "Dockerfile"

TEMPO_MAXIMO_EXCEDIDO = ac.TEMPO_MAXIMO_EXCEDIDO
FALHAS_DE_TRANSPORTE = ac.FALHAS_DE_TRANSPORTE
ACESSO_RECUSADO = "acesso_recusado"
CANCELADO = ac.CANCELADO
DEFEITO_DO_AVALIADOR = ac.DEFEITO_DO_AVALIADOR
DESCRICAO_DA_INTERRUPCAO = {
    TEMPO_MAXIMO_EXCEDIDO: "o tempo máximo de 50 minutos acabou",
    FALHAS_DE_TRANSPORTE: f"{FALHAS_SEGUIDAS} falhas de transporte seguidas",
    ACESSO_RECUSADO: f"{FALHAS_SEGUIDAS} recusas de acesso (HTTP 401 ou 403) seguidas",
    CANCELADO: "a execução foi cancelada",
    DEFEITO_DO_AVALIADOR: "defeito do avaliador",
}

LEITURA_PERMITIDA = (
    "Comparação descritiva entre as duas estratégias sobre o MESMO conjunto de casos, com o plano congelado antes das chamadas e a "
    "configuração relativa declarada igual.",
    "Contagens, códigos HTTP, latências e tokens que o chat informou; falhas e casos não avaliados contam como falha, e o denominador "
    "é sempre o total de casos planejado.",
)
LEITURA_PROIBIDA = (
    "Comparar este relatório com o de outro conjunto de casos ou de outro plano (conjunto_sha256 ou plano_sha256 diferentes): não é uma "
    "comparação causal nem equivalente.",
    "Concluir fidelidade, correção semântica ou qualidade das respostas: o avaliador confere o contrato e a política do chat, sem "
    "modelo como juiz.",
    "Extrapolar latência, consumo ou custo para outro volume, concorrência ou horário, ou tratar a troca de um índice ou de uma "
    "configuração como prova de compatibilidade.",
)
OBSERVACAO_DO_USO = ("Soma só do uso que o chat informou em respostas 200. Respostas de erro, falhas de transporte e respostas sem o campo "
                     "de uso (null, quando alguma tentativa falhou ou não informou) deixam o consumo desconhecido, não zero. Não é o "
                     "total consumido nem o custo.")
OBSERVACAO_DO_CUSTO = ("Estimativa com os preços informados por quem opera e só com o uso informado; os tokens de raciocínio já estão "
                       "nos de saída e não são somados de novo. Parcial quando alguma chamada não informou o uso.")
ESCOPO_DA_CONTAGEM = "só as chamadas HTTP do avaliador ao chat; as tentativas internas do chat aos modelos e à busca não são visíveis aqui"

CHAVES_DO_RELATORIO = frozenset({
    "schema_version", "relatorio", "status", "simulado", "interrupcao", "codigo_de_saida", "inicio_utc", "fim_utc", "entrada", "plano",
    "configuracao_avaliada", "avaliador", "codigo_avaliado", "codigo_sha256", "significado_dos_hashes", "artefatos", "destinos",
    "identidade", "limites", "estrategias", "comparacao", "custos", "interpretacao", "avisos"})

_PADRAO_ARTEFATO = re.compile(r"sha256:[0-9a-f]{64}|[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}")
_PADRAO_PRECO = re.compile(r"[0-9]{1,9}(?:\.[0-9]{1,9})?")
_PADRAO_MOEDA = re.compile(r"[A-Z]{3}")
_PADRAO_SHA256 = re.compile(r"[0-9a-f]{64}")
PASTAS_FINAIS_PROTEGIDAS = ("dados/l100/avaliacao", "dados/l100/avaliacao-independente", "dados/l200/avaliacao")
PASTAS_DO_CONTEXTO_DA_IMAGEM = ("scripts", "web", "requirements")


# --------------------------------------------------------------------------------------
# Entradas: casos, destinos, tokens, artefatos, preços
# --------------------------------------------------------------------------------------

def validar_caminho_dos_casos(caminho: Path, raiz: Path = lab_comum.RAIZ) -> Path:
    """Recusa, antes de abrir o arquivo, as avaliações finais de outros níveis, os corpora e o contexto de build da imagem.

    Uma pergunta de teste nunca pode ficar onde o indexador ou o build da imagem a leriam, e um conjunto final do L100 ou do L200
    não é reinterpretado como conjunto do L400.
    """
    try:
        absoluto = caminho.expanduser().resolve(strict=False)
        raiz = raiz.resolve()
    except (OSError, RuntimeError, ValueError):
        raise ErroLab("O caminho dos casos (--casos) é inválido.") from None
    for pasta in PASTAS_FINAIS_PROTEGIDAS:
        if absoluto.is_relative_to(raiz / pasta):
            raise ErroLab("O arquivo de casos está em uma pasta de avaliações finais do L100 ou do L200, que não são abertas nem "
                          "reinterpretadas como conjunto do L400. Use um conjunto novo, criado para o L400.")
    corpora = list((raiz / "dados").glob("*/documentos")) if (raiz / "dados").is_dir() else []
    if any(absoluto.is_relative_to(pasta) for pasta in (*corpora, *(raiz / nome for nome in PASTAS_DO_CONTEXTO_DA_IMAGEM))):
        raise ErroLab("O arquivo de casos está em uma pasta que o indexador ou o build da imagem leem (documentos, scripts, web ou "
                      "requirements). Perguntas de teste não entram em corpus nem em imagem: guarde o arquivo em outra pasta.")
    return absoluto


def validar_artefato(valor: str | None, opcao: str) -> str:
    if valor is None or not _PADRAO_ARTEFATO.fullmatch(valor) or valor.lower() == "latest":
        raise ErroLab(f"{opcao}: informe o artefato avaliado, um digest sha256:<64 hexadecimais> ou uma tag imutável da imagem "
                      "(nunca 'latest', endereços ou caminhos). O avaliador o grava como foi declarado e não o confere com o serviço.")
    return valor


def ler_tokens(ambiente: Mapping[str, str], destinos: Mapping[str, ac.Destino]) -> dict[str, str | None]:
    """Os tokens Bearer das variáveis de ambiente. Com HTTPS, sem token válido a execução nem começa; nenhum valor é impresso."""
    tokens: dict[str, str | None] = {}
    problemas = []
    for estrategia in ESTRATEGIAS:
        nome = VAR_TOKEN[estrategia]
        bruto = (ambiente.get(nome) or "").strip()
        if not destinos[estrategia].https:
            tokens[estrategia] = None
        elif not bruto:
            problemas.append(f"{nome}: obrigatória com HTTPS.")
        elif not ac._PADRAO_TOKEN.fullmatch(bruto):
            problemas.append(f"{nome}: não tem a forma de um token de acesso.")
        else:
            tokens[estrategia] = bruto
    if problemas:
        raise ErroLab("Os tokens de acesso (Bearer) das duas aplicações vêm só de variáveis de ambiente, definidas na sua sessão:\n"
                      + "\n".join(f"  - {problema}" for problema in problemas)
                      + "\nOs valores nunca são impressos nem gravados, e o avaliador não tem opção para enviar chamadas sem eles.")
    return tokens


@dataclass(frozen=True)
class Precos:
    """Preços por 1 milhão de tokens, informados por quem opera. Não existe preço neste programa."""

    entrada: float
    saida: float
    embeddings: float
    moeda: str


def ler_precos(args: argparse.Namespace) -> Precos | None:
    brutos = {"entrada": args.preco_entrada_1m, "saida": args.preco_saida_1m, "embeddings": args.preco_embeddings_1m}
    if all(valor is None for valor in brutos.values()) and args.moeda is None:
        return None
    if any(valor is None for valor in brutos.values()) or args.moeda is None:
        raise ErroLab("Para estimar o custo, informe os três preços por 1 milhão de tokens (--preco-entrada-1m, --preco-saida-1m e "
                      "--preco-embeddings-1m) e a moeda (--moeda, três letras maiúsculas), ou nenhum deles. Nenhum preço é assumido.")
    valores = {}
    for nome, bruto in brutos.items():
        if not _PADRAO_PRECO.fullmatch(bruto.strip()) or not math.isfinite(float(bruto)) or float(bruto) < 0:
            raise ErroLab(f"--preco-{nome}-1m: informe um número decimal finito, maior ou igual a zero, como 1.25 (sem sinal, expoente "
                          "nem separador de milhar).")
        valores[nome] = float(bruto)
    if not _PADRAO_MOEDA.fullmatch(args.moeda):
        raise ErroLab("--moeda: use o código de três letras maiúsculas da moeda dos preços informados.")
    return Precos(valores["entrada"], valores["saida"], valores["embeddings"], args.moeda)


def segredos_para_redigir(ambiente: Mapping[str, str]) -> tuple[str, ...]:
    """Os tokens, em todas as formas em que poderiam aparecer em um texto, para redigir o console e conferir o relatório."""
    formas = set()
    for nome in VAR_TOKEN.values():
        bruto = ambiente.get(nome) or ""
        for valor in (bruto, bruto.strip()):
            if len(valor) >= o3.MENOR_SEGREDO_REDIGIDO:
                formas.update((valor, json.dumps(valor)[1:-1]))
    return tuple(sorted(formas, key=len, reverse=True))


# --------------------------------------------------------------------------------------
# Plano congelado
# --------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Passo:
    posicao: int
    caso: str
    estrategia: str


@dataclass(frozen=True)
class Plano:
    passos: tuple[Passo, ...]
    sha256: str
    conjunto_sha256: str


def _sha256_canonico(dados: Any) -> str:
    texto = json.dumps(dados, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(texto.encode("ascii")).hexdigest()


def casos_em_ordem(entrada: ac.Entrada) -> list[ac.Caso]:
    return sorted(entrada.casos, key=lambda caso: (caso.id.casefold(), caso.id))


def hash_do_conjunto(entrada: ac.Entrada) -> str:
    """SHA-256 do conteúdo dos casos (ids, categorias, tipos, situações e perguntas), na ordem do plano: o mesmo conjunto dá o mesmo valor
    em qualquer formatação do arquivo. As perguntas entram no hash e nunca no relatório."""
    return _sha256_canonico([[caso.id, caso.categoria, caso.tipo_esperado, caso.situacao_esperada, caso.pergunta]
                             for caso in casos_em_ordem(entrada)])


def construir_plano(entrada: ac.Entrada) -> Plano:
    """Uma chamada por estratégia e caso, casos em ordem de id e a estratégia que vai primeiro alternando de caso em caso."""
    passos: list[Passo] = []
    for indice, caso in enumerate(casos_em_ordem(entrada)):
        ordem = ESTRATEGIAS if indice % 2 == 0 else tuple(reversed(ESTRATEGIAS))
        anteriores = len(passos)
        passos.extend(Passo(anteriores + deslocamento + 1, caso.id, estrategia) for deslocamento, estrategia in enumerate(ordem))
    conjunto = hash_do_conjunto(entrada)
    sha256 = _sha256_canonico({"versao": VERSAO_DO_ESQUEMA, "ordem": ORDEM_DO_PLANO, "estrategias": list(ESTRATEGIAS),
                               "conjunto_sha256": conjunto, "passos": [[p.posicao, p.caso, p.estrategia] for p in passos]})
    return Plano(tuple(passos), sha256, conjunto)


def hashes_do_codigo() -> dict[str, dict[str, str]]:
    """Os dois SHA-256 de cada módulo que a imagem copia (avaliar_chat.ARQUIVOS_DO_CODIGO) e do Dockerfile."""
    hashes = ac.hashes_do_codigo()
    try:
        hashes["Dockerfile"] = ac.hashes_do_conteudo(DOCKERFILE.read_bytes())
    except OSError:
        raise ErroLab("O Dockerfile não foi encontrado: use uma cópia completa do projeto.") from None
    return hashes


def hash_do_codigo(hashes: Mapping[str, Mapping[str, str]]) -> str:
    """Um único SHA-256 do código avaliado (o de cada arquivo com quebras LF), para comparar com o valor congelado."""
    return _sha256_canonico({nome: hashes[nome]["sha256_normalizado_lf"] for nome in sorted(hashes)})


# --------------------------------------------------------------------------------------
# Transportes: o real é o do avaliar_chat; o simulado não usa rede
# --------------------------------------------------------------------------------------

Transporte = Callable[[str, bytes, Mapping[str, str], float], ac.RespostaHttp]


class TransporteSimulado:
    """Responde o que cada caso espera, com as classes de produção, sem rede. O uso é simulado e diferente em cada estratégia."""

    USO = {"referencia": lab_chat.UsoChat(20, 400, 80, 0), "coordenacao": lab_chat.UsoChat(40, 1200, 240, 0)}

    def __init__(self, entrada: ac.Entrada):
        self._por_pergunta = {caso.pergunta: caso for caso in entrada.casos}

    def __call__(self, url: str, corpo: bytes, cabecalhos: Mapping[str, str], timeout: float) -> ac.RespostaHttp:
        caso = self._por_pergunta[json.loads(corpo.decode("utf-8"))["pergunta"]]
        estrategia = next(nome for nome in ESTRATEGIAS if nome in url)
        tipo = caso.tipo_esperado
        texto, aviso, citacoes = {
            lab_politica.CONTRATACAO_INDIVIDUAL: (lab_politica.TEXTO_SEM_VEREDITO, lab_politica.AVISO_CONTRATACAO_INDIVIDUAL, 1),
            lab_politica.DOCUMENTADA: ("Resposta simulada, sem consultar documentos nem modelos.", "", 1),
            lab_politica.AMBIGUA: (lab_politica.MENSAGEM_ESCLARECIMENTO, "", 0),
            lab_politica.SEM_EVIDENCIA: (lab_politica.MENSAGEM_SEM_EVIDENCIA, "", 0),
            lab_politica.FORA_DE_ESCOPO: (lab_politica.MENSAGEM_FORA_DE_ESCOPO, "", 0),
        }[tipo]
        evidencias = tuple(lab_chat.EvidenciaChat(f"SIM-{numero:04d}", "Citação simulada.", "simulado.md", "0", "Documento simulado",
                                                  "Seção simulada", "0") for numero in range(citacoes))
        resposta = lab_chat.RespostaChat(tipo, caso.situacao_esperada, texto, aviso, evidencias, self.USO[estrategia], True)
        return ac.RespostaHttp(200, json.dumps({"id": None, "id_requisicao": "s" * 32, **resposta.a_dict()},
                                               ensure_ascii=False).encode("utf-8"))


# --------------------------------------------------------------------------------------
# Um passo do plano
# --------------------------------------------------------------------------------------

def executar_caso(caso: ac.Caso, destino: ac.Destino, token: str | None, timeout: float, transporte: Transporte,
                  relogio: Callable[[], float]) -> tuple[ac.ResultadoDoCaso, bool, bool]:
    """Uma chamada, sem repetir. Devolve o resultado, se foi falha de transporte e se o destino recusou o acesso (401 ou 403)."""
    resultado = ac.ResultadoDoCaso(caso.id, caso.categoria, caso.tipo_esperado, caso.situacao_esperada, ac.ERRO)
    cabecalhos = {"Content-Type": "application/json", "Accept": "application/json", "User-Agent": USER_AGENT}
    if destino.https:
        cabecalhos["Authorization"] = f"Bearer {token}"
    corpo = json.dumps({"pergunta": caso.pergunta}, ensure_ascii=False).encode("utf-8")
    inicio = relogio()
    try:
        resposta = transporte(destino.base + ac.CAMINHO_DA_API, corpo, cabecalhos, timeout)
    except ac.FalhaDeTransporte as falha:
        resultado.tempo_s = round(relogio() - inicio, 3)
        resultado.erro = falha.rotulo
        return resultado, True, False
    resultado.tempo_s = round(relogio() - inicio, 3)
    resultado.http = resposta.status
    if resposta.status != 200:
        resultado.resultado = ac.FALHA_HTTP
        resultado.erro = ("redirecionamento" if 300 <= resposta.status < 400 else
                          f"http_{resposta.status}" if 100 <= resposta.status <= 599 else "http_invalido")
        resultado.erro_do_chat = ac._codigo_do_chat(resposta.corpo)
        return resultado, False, resposta.status in (401, 403)
    try:
        interpretada = ac.interpretar_resposta(resposta.corpo, resposta.tipo_de_conteudo)
    except ac.PayloadInvalido as invalido:
        resultado.erro = invalido.rotulo
        return resultado, False, False
    resultado.tipo, resultado.situacao, resultado.citacoes = interpretada.tipo, interpretada.situacao, interpretada.citacoes
    resultado.tokens, resultado.simulada = interpretada.tokens, interpretada.simulada
    resultado.texto_individual_fixo = interpretada.texto_fixo and interpretada.aviso_fixo
    resultado.motivos = ac.comparar(caso, interpretada, destino)
    resultado.resultado = ac.DIVERGENTE if resultado.motivos else ac.APROVADO
    return resultado, False, False


# --------------------------------------------------------------------------------------
# Execução
# --------------------------------------------------------------------------------------

@dataclass
class Execucao:
    entrada: ac.Entrada
    plano: Plano
    destinos: dict[str, ac.Destino]
    artefatos: dict[str, str]
    codigo: dict[str, dict[str, str]] | None = None
    precos: Precos | None = None
    simulado: bool = False
    esperados: dict[str, bool] = field(default_factory=dict)
    avisos: list[str] = field(default_factory=list)
    inicio_utc: str = ""
    fim_utc: str = ""
    duracao: float = 0.0
    resultados: dict[str, dict[str, ac.ResultadoDoCaso]] = field(default_factory=lambda: {e: {} for e in ESTRATEGIAS})
    chamadas: dict[str, int] = field(default_factory=lambda: dict.fromkeys(ESTRATEGIAS, 0))
    acessos_recusados: dict[str, int] = field(default_factory=lambda: dict.fromkeys(ESTRATEGIAS, 0))
    interrupcao: str | None = None
    interrupcoes: dict[str, str] = field(default_factory=dict)

    def interromper(self, motivo: str) -> None:
        self.interrupcao = self.interrupcao or motivo

    def finalizar(self) -> None:
        """Os passos que não chegaram a ser enviados ficam registrados como não avaliados, nunca como aprovados."""
        por_id = {caso.id: caso for caso in self.entrada.casos}
        for passo in self.plano.passos:
            if passo.caso not in self.resultados[passo.estrategia]:
                caso = por_id[passo.caso]
                motivo = self.interrupcoes.get(passo.estrategia) or self.interrupcao or "nao_enviado"
                self.resultados[passo.estrategia][passo.caso] = ac.ResultadoDoCaso(
                    caso.id, caso.categoria, caso.tipo_esperado, caso.situacao_esperada, ac.NAO_AVALIADO, [motivo])

    def itens(self, estrategia: str) -> list[ac.ResultadoDoCaso]:
        return [self.resultados[estrategia][caso.id] for caso in casos_em_ordem(self.entrada)]

    def contar(self, estrategia: str, resultado: str) -> int:
        return sum(1 for item in self.resultados[estrategia].values() if item.resultado == resultado)

    @property
    def interrompida(self) -> bool:
        return bool(self.interrupcao or self.interrupcoes)


def descrever(passo: Passo, total: int, item: ac.ResultadoDoCaso) -> str:
    base = f"[{passo.posicao}/{total}] {passo.caso} · {passo.estrategia}"
    if item.resultado == ac.APROVADO:
        return f"  [OK] {base}: aprovado (HTTP {item.http}, {ac.decimal(item.tempo_s or 0)} s)"
    if item.resultado == ac.DIVERGENTE:
        return f"  [FALHA] {base}: divergente ({', '.join(item.motivos)})"
    detalhe = (item.erro or "?") + (f" ({item.erro_do_chat})" if item.erro_do_chat else "")
    return f"  [FALHA] {base}: {item.resultado} ({detalhe})"


def avaliar(execucao: Execucao, tokens: Mapping[str, str | None], transporte: Transporte, relogio: Callable[[], float],
            registrar: Callable[[str], None] = print) -> None:
    """Envia os passos do plano em sequência. Para no tempo máximo e, em cada estratégia, em 3 falhas seguidas de transporte ou de acesso."""
    inicio = relogio()
    por_id = {caso.id: caso for caso in execucao.entrada.casos}
    seguidas = {estrategia: {"transporte": 0, "acesso": 0} for estrategia in ESTRATEGIAS}
    total = len(execucao.plano.passos)
    for passo in execucao.plano.passos:
        estrategia = passo.estrategia
        if estrategia in execucao.interrupcoes:
            continue
        restante = TEMPO_MAXIMO - (relogio() - inicio)
        if restante < 1:
            execucao.interromper(TEMPO_MAXIMO_EXCEDIDO)
            break
        item, falha_de_transporte, acesso_recusado = executar_caso(
            por_id[passo.caso], execucao.destinos[estrategia], tokens.get(estrategia), min(TIMEOUT_DA_CHAMADA, restante), transporte, relogio)
        execucao.resultados[estrategia][passo.caso] = item
        execucao.chamadas[estrategia] += 1
        execucao.acessos_recusados[estrategia] += int(acesso_recusado)
        registrar(descrever(passo, total, item))
        contadores = seguidas[estrategia]
        contadores["transporte"] = contadores["transporte"] + 1 if falha_de_transporte else 0
        contadores["acesso"] = contadores["acesso"] + 1 if acesso_recusado else 0
        if contadores["transporte"] >= FALHAS_SEGUIDAS:
            execucao.interrupcoes[estrategia] = FALHAS_DE_TRANSPORTE
        elif contadores["acesso"] >= FALHAS_SEGUIDAS:
            execucao.interrupcoes[estrategia] = ACESSO_RECUSADO


# --------------------------------------------------------------------------------------
# Relatório
# --------------------------------------------------------------------------------------

def _percentil(ordenados: Sequence[float], percentual: int) -> float:
    return ordenados[max(0, math.ceil(percentual / 100 * len(ordenados)) - 1)]


def resumir_latencia(itens: Sequence[ac.ResultadoDoCaso]) -> dict[str, Any]:
    """Latência só das chamadas que receberam uma resposta HTTP; sem nenhuma, os valores são null (nunca zero)."""
    tempos = sorted(item.tempo_s for item in itens if item.http is not None and item.tempo_s is not None)
    if not tempos:
        return {"respostas_http": 0, "minimo": None, "p50": None, "p95": None, "maximo": None, "media": None}
    return {"respostas_http": len(tempos), "minimo": tempos[0], "p50": _percentil(tempos, 50), "p95": _percentil(tempos, 95),
            "maximo": tempos[-1], "media": round(sum(tempos) / len(tempos), 3)}


def resumir_uso(itens: Sequence[ac.ResultadoDoCaso], chamadas: int) -> dict[str, Any]:
    """Soma só o uso informado. Onde o chat não informa, o consumo é desconhecido: nunca vira zero nem um total completo."""
    informados = [item.tokens for item in itens if item.tokens is not None]
    soma = None
    if informados:
        soma = dict.fromkeys(sorted(ac.CAMPOS_DO_USO), 0)
        for uso in informados:
            for nome, valor in uso.items():
                soma[nome] += valor
    return {"respostas_com_uso_informado": len(informados), "chamadas_sem_uso_informado": max(chamadas - len(informados), 0),
            "soma_do_uso_informado": soma, "observacao": OBSERVACAO_DO_USO}


def estimar_custo(uso: Mapping[str, Any], precos: Precos | None) -> dict[str, Any] | None:
    if precos is None:
        return None
    soma = uso["soma_do_uso_informado"]
    estimado = None if soma is None else round(
        (soma["tokens_embeddings"] * precos.embeddings + soma["tokens_entrada"] * precos.entrada + soma["tokens_saida"] * precos.saida)
        / 1_000_000, 6)
    return {"estimado_com_o_uso_informado": estimado, "parcial": soma is None or uso["chamadas_sem_uso_informado"] > 0}


def resumir_estrategia(execucao: Execucao, estrategia: str) -> dict[str, Any]:
    itens = execucao.itens(estrategia)
    total = len(itens)
    contagem = Counter(item.resultado for item in itens)
    categorias: dict[str, dict[str, int]] = {}
    for item in itens:
        resumo = categorias.setdefault(item.categoria, {"casos": 0, "aprovados": 0})
        resumo["casos"] += 1
        resumo["aprovados"] += int(item.resultado == ac.APROVADO)
    uso = resumir_uso(itens, execucao.chamadas[estrategia])
    return {
        "casos_planejados": total, "chamadas_http": execucao.chamadas[estrategia], "aprovados": contagem[ac.APROVADO],
        "divergentes": contagem[ac.DIVERGENTE], "falhas_http": contagem[ac.FALHA_HTTP], "erros": contagem[ac.ERRO],
        "nao_avaliados": contagem[ac.NAO_AVALIADO],
        "taxa_de_aprovacao": round(contagem[ac.APROVADO] / total, 4) if total else None,
        "denominador": "casos_planejados: falhas, descartes (429, 503), tempo esgotado, JSON inválido e não avaliados contam como falha",
        "codigos_http": dict(sorted(Counter(str(item.http) for item in itens if item.http is not None).items())),
        "erros_por_rotulo": dict(sorted(Counter(item.erro for item in itens if item.erro).items())),
        "erros_do_chat": dict(sorted(Counter(item.erro_do_chat for item in itens if item.erro_do_chat).items())),
        "acessos_recusados": execucao.acessos_recusados[estrategia], "respostas_simuladas": sum(1 for item in itens if item.simulada),
        "latencia_s": resumir_latencia(itens), "uso_de_tokens": uso, "custo": estimar_custo(uso, execucao.precos),
        "categorias": categorias, "escopo_da_contagem": ESCOPO_DA_CONTAGEM,
    }


def comparar_estrategias(execucao: Execucao, resumos: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """Ganho e perda em relação à base (a referência): só com o resultado de cada caso, que é o mesmo conjunto nas duas estratégias."""
    ids = [caso.id for caso in casos_em_ordem(execucao.entrada)]
    aprovado = {estrategia: {i: execucao.resultados[estrategia][i].resultado == ac.APROVADO for i in ids} for estrategia in ESTRATEGIAS}
    ganhos = [i for i in ids if not aprovado[BASE][i] and aprovado["coordenacao"][i]]
    perdas = [i for i in ids if aprovado[BASE][i] and not aprovado["coordenacao"][i]]
    base, outra = resumos[BASE], resumos["coordenacao"]

    def diferenca(a: Any, b: Any) -> Any:
        return None if a is None or b is None else round(a - b, 6)

    usos = [resumos[estrategia]["uso_de_tokens"] for estrategia in ESTRATEGIAS]
    completos = all(uso["soma_do_uso_informado"] is not None and uso["chamadas_sem_uso_informado"] == 0 for uso in usos)
    custos = [resumos[estrategia]["custo"] for estrategia in ESTRATEGIAS]
    custos_completos = all(custo is not None and custo["estimado_com_o_uso_informado"] is not None and not custo["parcial"] for custo in custos)
    return {
        "base": BASE, "casos": len(ids), "ambos_aprovados": sum(1 for i in ids if aprovado[BASE][i] and aprovado["coordenacao"][i]),
        "ambos_reprovados": sum(1 for i in ids if not aprovado[BASE][i] and not aprovado["coordenacao"][i]),
        "ganhos": len(ganhos), "perdas": len(perdas), "saldo": len(ganhos) - len(perdas), "ids_dos_ganhos": ganhos,
        "ids_das_perdas": perdas, "delta_da_taxa_de_aprovacao": diferenca(outra["taxa_de_aprovacao"], base["taxa_de_aprovacao"]),
        "delta_da_latencia_p50_s": diferenca(outra["latencia_s"]["p50"], base["latencia_s"]["p50"]),
        "delta_da_latencia_p95_s": diferenca(outra["latencia_s"]["p95"], base["latencia_s"]["p95"]),
        "delta_dos_tokens": ({nome: outra["uso_de_tokens"]["soma_do_uso_informado"][nome] - base["uso_de_tokens"]["soma_do_uso_informado"][nome]
                              for nome in sorted(ac.CAMPOS_DO_USO)} if completos else None),
        "delta_do_custo_estimado": diferenca(custos[1]["estimado_com_o_uso_informado"], custos[0]["estimado_com_o_uso_informado"])
        if custos_completos else None,
        "nota_dos_deltas": "null quando algum dos lados tem valor desconhecido: o desconhecido nunca é tratado como zero",
    }


def codigo_de_saida(execucao: Execucao) -> int:
    if any(execucao.acessos_recusados.values()):
        return lab_comum.CODIGO_ACESSO
    aprovados = all(item.resultado == ac.APROVADO for estrategia in ESTRATEGIAS for item in execucao.resultados[estrategia].values())
    return lab_comum.CODIGO_OK if aprovados and not execucao.interrompida else lab_comum.CODIGO_DIVERGENCIA


def montar_relatorio(execucao: Execucao) -> dict[str, Any]:
    entrada, plano = execucao.entrada, execucao.plano
    resumos = {estrategia: resumir_estrategia(execucao, estrategia) for estrategia in ESTRATEGIAS}
    nao_avaliados = {estrategia: resumos[estrategia]["nao_avaliados"] for estrategia in ESTRATEGIAS}
    avisos = list(execucao.avisos)
    if execucao.simulado:
        avisos.append("ENSAIO: respostas simuladas, sem rede. Este relatório não mede nenhuma aplicação e não vale como evidência.")
    if any(item.simulada for estrategia in ESTRATEGIAS for item in execucao.resultados[estrategia].values()) and not execucao.simulado:
        avisos.append("Há respostas marcadas como simuladas pelo próprio chat (modo de demonstração): elas não medem o serviço real.")
    codigo = execucao.codigo or {}
    return {
        "schema_version": VERSAO_DO_ESQUEMA,
        "relatorio": NOME_DO_RELATORIO,
        "status": "interrompido" if execucao.interrompida else "concluido",
        "simulado": execucao.simulado,
        "interrupcao": ({"motivo_global": execucao.interrupcao, "motivo_por_estrategia": dict(execucao.interrupcoes),
                         "nao_avaliados": nao_avaliados} if execucao.interrompida else None),
        "codigo_de_saida": codigo_de_saida(execucao),
        "inicio_utc": execucao.inicio_utc,
        "fim_utc": execucao.fim_utc,
        "entrada": {"nome": entrada.nome, "origem": entrada.origem, "casos": len(entrada.casos),
                    "campos_ignorados": list(entrada.campos_ignorados), "sha256_bytes_brutos": entrada.sha256_bytes_brutos,
                    "sha256_normalizado_lf": entrada.sha256_normalizado_lf, "conjunto_sha256": plano.conjunto_sha256},
        "plano": {"sha256": plano.sha256, "ordem": ORDEM_DO_PLANO, "estrategias": list(ESTRATEGIAS),
                  "chamadas_planejadas": len(plano.passos), "congelado_antes_da_execucao": True,
                  "hashes_esperados_conferidos": dict(execucao.esperados)},
        "configuracao_avaliada": {"valor": entrada.configuracao_avaliada, "informada_pelo_autor": True, "verificada_pelo_avaliador": False,
                                  "nota": ac.NOTA_DA_CONFIGURACAO},
        "avaliador": {"arquivo": "scripts/avaliar_l400.py", "versao": VERSAO_DO_AVALIADOR,
                      **ac.hashes_do_conteudo(Path(__file__).resolve().read_bytes())},
        "codigo_avaliado": codigo,
        "codigo_sha256": hash_do_codigo(codigo) if codigo else None,
        "significado_dos_hashes": ac.SIGNIFICADO_DOS_HASHES,
        "artefatos": {estrategia: {"origem_declarada": execucao.artefatos[estrategia], "verificada_pelo_avaliador": False}
                      for estrategia in ESTRATEGIAS},
        "destinos": {estrategia: {"modo": ("simulado_sem_rede" if execucao.simulado else "hospedado_https" if execucao.destinos[estrategia].https
                                           else "demonstracao_ou_local_loopback")} for estrategia in ESTRATEGIAS},
        "identidade": {"tipo": "simulada" if execucao.simulado else "bearer_de_variavel_de_ambiente"},
        "limites": {"casos": MAXIMO_DE_CASOS, "chamadas_por_caso_e_estrategia": 1, "timeout_da_chamada_s": int(TIMEOUT_DA_CHAMADA),
                    "tempo_maximo_s": int(TEMPO_MAXIMO), "falhas_seguidas_por_estrategia": FALHAS_SEGUIDAS,
                    "resposta_maxima_bytes": ac.LIMITE_DA_RESPOSTA, "tentativas_automaticas_do_avaliador": 0},
        "estrategias": {estrategia: {"rotulo": ROTULOS[estrategia], "resumo": resumos[estrategia],
                                     "casos": [{**asdict(item), "posicao": passo.posicao}
                                               for caso in casos_em_ordem(entrada) for item in [execucao.resultados[estrategia][caso.id]]
                                               for passo in plano.passos if passo.caso == caso.id and passo.estrategia == estrategia]}
                        for estrategia in ESTRATEGIAS},
        "comparacao": comparar_estrategias(execucao, resumos),
        "custos": ({"regime": "precos_informados_pelo_operador", "moeda": execucao.precos.moeda,
                    "precos_por_1m_de_tokens": {"entrada": execucao.precos.entrada, "saida": execucao.precos.saida,
                                                "embeddings": execucao.precos.embeddings}, "observacao": OBSERVACAO_DO_CUSTO}
                   if execucao.precos is not None else {"regime": "nao_informado", "moeda": None, "precos_por_1m_de_tokens": None,
                                                         "observacao": "Nenhum preço foi informado: só tokens, sem custo."}),
        "interpretacao": {"permite": list(LEITURA_PERMITIDA), "nao_permite": list(LEITURA_PROIBIDA)},
        "avisos": avisos,
    }


# --------------------------------------------------------------------------------------
# Saída, relatório em arquivo e linha de comando
# --------------------------------------------------------------------------------------

def reservar_relatorio(caminho: Path) -> Any:
    """Cria o arquivo antes da rede, em modo exclusivo, e deixa nele um marcador de execução em andamento."""
    try:
        descritor = os.open(caminho, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raise ErroLab("O relatório (--relatorio) já existe. O avaliador nunca sobrescreve: escolha um caminho novo.") from None
    except OSError:
        raise ErroLab("Não foi possível criar o relatório (--relatorio). Confira a pasta e as permissões.") from None
    arquivo = os.fdopen(descritor, "w", encoding="utf-8", newline="\n")
    try:
        gravar_relatorio(arquivo, {"schema_version": VERSAO_DO_ESQUEMA, "relatorio": NOME_DO_RELATORIO, "status": "em_andamento"})
    except OSError:
        arquivo.close()
        raise ErroLab("Não foi possível gravar no relatório (--relatorio). Confira a pasta e o espaço em disco.") from None
    return arquivo


def gravar_relatorio(arquivo: Any, relatorio: Mapping[str, Any]) -> None:
    texto = json.dumps(relatorio, ensure_ascii=False, indent=2) + "\n"
    if o3.contem_segredo(texto):
        raise ErroLab("O relatório continha um token de acesso e NÃO foi gravado (o valor não é exibido).", lab_comum.CODIGO_INESPERADO)
    arquivo.seek(0)
    arquivo.truncate()
    arquivo.write(texto)
    arquivo.flush()
    os.fsync(arquivo.fileno())


def mostrar_plano(entrada: ac.Entrada, plano: Plano, destinos: Mapping[str, ac.Destino], artefatos: Mapping[str, str],
                  codigo_sha256: str | None, modo: str) -> None:
    print("Comparação L400: referência (L300) × coordenação (L400), pelo contrato HTTP do chat")
    categorias = Counter(caso.categoria for caso in entrada.casos)
    print(f"  Casos: {len(entrada.casos)} ({' · '.join(f'{nome} {total}' for nome, total in categorias.items())})")
    if entrada.campos_ignorados:
        print(f"  [AVISO] Campos desconhecidos ignorados: {', '.join(entrada.campos_ignorados)}.")
    print(f"  conjunto_sha256: {plano.conjunto_sha256}")
    print(f"  plano_sha256:    {plano.sha256}")
    print(f"  codigo_sha256:   {codigo_sha256 or 'não calculado (veja o aviso)'}")
    print(f"  Plano congelado: {len(plano.passos)} POST sequenciais ({len(entrada.casos)} casos × {len(ESTRATEGIAS)} estratégias), casos em "
          f"ordem de id e a estratégia que vai primeiro alternando de caso em caso; sem repetição automática; {int(TIMEOUT_DA_CHAMADA)} s "
          f"por chamada, {ac.LIMITE_DA_RESPOSTA // 1024} KiB por resposta; para em {int(TEMPO_MAXIMO // 60)} min ou em "
          f"{FALHAS_SEGUIDAS} falhas seguidas por estratégia.")
    for estrategia in ESTRATEGIAS:
        destino = ("simulado, sem rede" if modo == "simular" else "HTTPS, endereço padrão do Azure Container Apps (não impresso nem gravado)"
                   if destinos[estrategia].https else "HTTP local em loopback, sem autenticação (demonstração)")
        print(f"  {ROTULOS[estrategia]}: {destino}; artefato declarado: {artefatos[estrategia]}")
    if modo == "plano":
        print("\n[SIMULAÇÃO] Entrada, destinos, credenciais e relatório conferem; nenhuma pergunta foi enviada e nenhum relatório foi "
              "criado. Repita com --executar para enviar (guarde os três SHA-256 acima para --plano-esperado, --conjunto-esperado e "
              "--codigo-esperado) ou com --simular para um ensaio sem rede.")
    elif modo == "simular":
        print("\n[ENSAIO] Respostas simuladas, sem rede nem credenciais: o relatório não mede nenhuma aplicação.")


def _descrever_uso(uso: Mapping[str, Any]) -> str:
    soma = uso["soma_do_uso_informado"]
    if soma is None:
        return "tokens desconhecidos (nenhuma resposta informou o uso)"
    total = uso["respostas_com_uso_informado"] + uso["chamadas_sem_uso_informado"]
    return (f"tokens informados em {uso['respostas_com_uso_informado']} de {total} chamada(s) (soma parcial: "
            + " · ".join(f"{nome.removeprefix('tokens_')} {valor}" for nome, valor in soma.items()) + ")")


def mostrar_resumo(relatorio: Mapping[str, Any], caminho: Path) -> None:
    print("\nResultado (denominador = casos planejados; falhas e casos não avaliados contam como falha):")
    for estrategia in ESTRATEGIAS:
        resumo = relatorio["estrategias"][estrategia]["resumo"]
        latencia = resumo["latencia_s"]
        tempo = "latência desconhecida" if latencia["p50"] is None else f"latência p50 {ac.decimal(latencia['p50'], 2)} s, p95 {ac.decimal(latencia['p95'], 2)} s"
        print(f"  {ROTULOS[estrategia]}: {resumo['aprovados']} de {resumo['casos_planejados']} aprovados · divergentes {resumo['divergentes']} · "
              f"falhas de HTTP {resumo['falhas_http']} · erros {resumo['erros']} · não avaliados {resumo['nao_avaliados']} · {tempo}")
        print(f"      {_descrever_uso(resumo['uso_de_tokens'])}")
        custo = resumo["custo"]
        if custo is not None:
            valor = "desconhecido" if custo["estimado_com_o_uso_informado"] is None else (
                f"{custo['estimado_com_o_uso_informado']} {relatorio['custos']['moeda']}" + (" (parcial)" if custo["parcial"] else ""))
            print(f"      custo estimado com o uso informado: {valor}")
    comparacao = relatorio["comparacao"]
    print(f"  Em relação à referência: {comparacao['ganhos']} ganho(s), {comparacao['perdas']} perda(s), saldo {comparacao['saldo']}; "
          f"{comparacao['ambos_aprovados']} caso(s) aprovados nas duas e {comparacao['ambos_reprovados']} reprovados nas duas.")
    if relatorio["simulado"]:
        print("  [ENSAIO] Resultado simulado: não é medição.")
    interrupcao = relatorio["interrupcao"]
    if interrupcao:
        motivos = [interrupcao["motivo_global"], *interrupcao["motivo_por_estrategia"].values()]
        print("  [INTERROMPIDA] " + "; ".join(DESCRICAO_DA_INTERRUPCAO[motivo] for motivo in dict.fromkeys(m for m in motivos if m)) + ".")
    if sum(relatorio["estrategias"][e]["resumo"]["acessos_recusados"] for e in ESTRATEGIAS):
        print("  [ERRO] O destino recusou a autenticação (HTTP 401 ou 403). Confira o token de cada aplicação e a autorização documental.")
    print(f"  Relatório gravado em {caminho} (arquivo novo, sem endereços, perguntas, textos, tokens nem corpos de resposta).")


def executar_comparacao(execucao: Execucao, tokens: Mapping[str, str | None], transporte: Transporte, relogio: Callable[[], float],
                        caminho: Path) -> int:
    arquivo = reservar_relatorio(caminho)  # antes de qualquer acesso à rede
    defeito: Exception | None = None
    execucao.inicio_utc = ac.agora_utc()
    inicio = relogio()
    try:
        avaliar(execucao, tokens, transporte, relogio)
    except KeyboardInterrupt:
        execucao.interromper(CANCELADO)
    except Exception as erro:  # noqa: BLE001 - o relatório registra a interrupção; só o tipo do erro é mostrado
        execucao.interromper(DEFEITO_DO_AVALIADOR)
        defeito = erro
    execucao.duracao = relogio() - inicio
    execucao.fim_utc = ac.agora_utc()
    execucao.finalizar()
    relatorio = montar_relatorio(execucao)
    try:
        gravar_relatorio(arquivo, relatorio)
    except OSError:
        raise ErroLab("As perguntas foram enviadas, mas não foi possível gravar o relatório final. O resumo acima é o que existe.",
                      lab_comum.CODIGO_INESPERADO) from None
    finally:
        arquivo.close()
    if defeito is not None:
        raise defeito
    mostrar_resumo(relatorio, caminho)
    return relatorio["codigo_de_saida"]


def _conferir_esperado(nome: str, esperado: str | None, atual: str, o_que: str) -> bool:
    if esperado is None:
        return False
    if not _PADRAO_SHA256.fullmatch(esperado):
        raise ErroLab(f"--{nome}-esperado: informe os 64 caracteres hexadecimais minúsculos do SHA-256 congelado.")
    if esperado != atual:
        raise ErroLab(f"{o_que} não é o que foi congelado ({nome}_sha256 diferente): nada foi enviado. Se a mudança é de propósito, é um "
                      "novo experimento: congele de novo e não compare os resultados com os do anterior.")
    return True


def executar(args: argparse.Namespace, ambiente: Mapping[str, str], transporte: Transporte | None, relogio: Callable[[], float] | None) -> int:
    for nome in ("azure", "msal"):
        logging.getLogger(nome).setLevel(logging.CRITICAL)
    if sum(map(bool, (args.plano, args.executar, args.simular))) > 1:
        raise ErroLab("Use só um destes: --plano (o padrão: só valida e mostra o plano), --simular (ensaio sem rede) ou --executar (chamadas reais).")
    modo = "simular" if args.simular else "executar" if args.executar else "plano"
    entrada = ac.carregar_entrada(validar_caminho_dos_casos(Path(args.casos)))
    if modo == "simular":
        destinos = {estrategia: ac.Destino(f"simulado://{estrategia}", False) for estrategia in ESTRATEGIAS}
        artefatos = dict.fromkeys(ESTRATEGIAS, "simulado")
        tokens: dict[str, str | None] = dict.fromkeys(ESTRATEGIAS)
    else:
        urls = {"referencia": args.url_referencia, "coordenacao": args.url_coordenacao}
        if not all(urls.values()):
            raise ErroLab("Informe --url-referencia e --url-coordenacao: o endereço de cada aplicação é recebido explicitamente.")
        destinos = {estrategia: ac.validar_destino(url) for estrategia, url in urls.items()}
        if destinos["referencia"].base == destinos["coordenacao"].base:
            raise ErroLab("As duas aplicações têm o mesmo endereço: sem duas aplicações com estratégias diferentes não há comparação.")
        artefatos = {"referencia": validar_artefato(args.artefato_referencia, "--artefato-referencia"),
                     "coordenacao": validar_artefato(args.artefato_coordenacao, "--artefato-coordenacao")}
        tokens = ler_tokens(ambiente, destinos)
    precos = ler_precos(args)
    plano = construir_plano(entrada)
    avisos: list[str] = []
    codigo: dict[str, dict[str, str]] | None = None
    try:
        codigo = hashes_do_codigo()
    except ErroLab as erro:
        if modo != "plano":
            raise
        avisos.append(f"O código avaliado não pôde ser conferido agora: {erro}")
        print(f"[AVISO] {avisos[-1]}")
    esperados = {"conjunto": _conferir_esperado("conjunto", args.conjunto_esperado, plano.conjunto_sha256, "O conjunto de casos"),
                 "plano": _conferir_esperado("plano", args.plano_esperado, plano.sha256, "O plano"),
                 "codigo": codigo is not None and _conferir_esperado("codigo", args.codigo_esperado, hash_do_codigo(codigo), "O código avaliado")}
    if args.codigo_esperado is not None and codigo is None:
        raise ErroLab("--codigo-esperado exige calcular o código avaliado, o que não foi possível.")
    caminho = ac.validar_caminho_do_relatorio(Path(args.relatorio))
    mostrar_plano(entrada, plano, destinos, artefatos, hash_do_codigo(codigo) if codigo else None, modo)
    if modo == "plano":
        return lab_comum.CODIGO_OK
    print("\nExecutando (um POST por estratégia e caso, em sequência):" if modo == "executar" else "\nEnsaiando (sem rede):")
    execucao = Execucao(entrada, plano, destinos, artefatos, codigo, precos, modo == "simular", esperados, avisos)
    if modo == "simular":
        usar = TransporteSimulado(entrada)
    else:
        usar = transporte or ac.enviar_http
    return executar_comparacao(execucao, tokens, usar, relogio or ac.relogio, caminho)


def traduzir_erro(erro: Exception, args: argparse.Namespace) -> tuple[str, int]:
    return (f"Erro inesperado do avaliador ({type(erro).__name__}). Nenhum dado do ambiente foi impresso; se o relatório foi criado, ele "
            "registra a interrupção.", lab_comum.CODIGO_INESPERADO)


def criar_parser() -> lab_comum.ParserLab:
    parser = lab_comum.ParserLab(description=__doc__)
    parser.add_argument("--casos", required=True, help="Arquivo JSON dos casos (schema_version 1, o mesmo do avaliar_chat.py), fora do "
                        "corpus, do contexto da imagem e das avaliações finais do L100 e do L200.")
    parser.add_argument("--url-referencia", default=None, help="Endereço base da aplicação de referência (L300): HTTPS "
                        "*.azurecontainerapps.io ou http://127.0.0.1:<porta>. Nunca é impresso nem gravado.")
    parser.add_argument("--url-coordenacao", default=None, help="Endereço base da aplicação com coordenação (L400), no mesmo formato.")
    parser.add_argument("--artefato-referencia", default=None, help="Artefato avaliado na referência: digest sha256:<64 hex> ou tag imutável.")
    parser.add_argument("--artefato-coordenacao", default=None, help="Artefato avaliado na coordenação: digest sha256:<64 hex> ou tag imutável.")
    parser.add_argument("--relatorio", required=True, help="Relatório JSON a criar. O arquivo não pode existir: o avaliador nunca sobrescreve.")
    parser.add_argument("--plano", action="store_true", help="Só valida a entrada, os destinos e as credenciais e mostra o plano congelado com os três "
                        "SHA-256, sem enviar nada nem criar relatório. É o padrão: a opção só deixa o pedido explícito.")
    parser.add_argument("--executar", action="store_true", help="Envia as perguntas às duas aplicações. Sem esta opção, só valida e mostra o plano.")
    parser.add_argument("--simular", action="store_true", help="Ensaio sem rede nem credenciais, com respostas simuladas: o relatório é "
                        "marcado como simulado e nunca vale como medição.")
    parser.add_argument("--conjunto-esperado", default=None, metavar="SHA256", help="Recusa a execução se o conjunto_sha256 for outro.")
    parser.add_argument("--plano-esperado", default=None, metavar="SHA256", help="Recusa a execução se o plano_sha256 for outro.")
    parser.add_argument("--codigo-esperado", default=None, metavar="SHA256", help="Recusa a execução se o codigo_sha256 for outro.")
    parser.add_argument("--preco-entrada-1m", default=None, metavar="N", help="Preço por 1 milhão de tokens de entrada, informado por quem opera.")
    parser.add_argument("--preco-saida-1m", default=None, metavar="N", help="Preço por 1 milhão de tokens de saída (inclui os de raciocínio).")
    parser.add_argument("--preco-embeddings-1m", default=None, metavar="N", help="Preço por 1 milhão de tokens de embeddings.")
    parser.add_argument("--moeda", default=None, metavar="XXX", help="Moeda dos preços, em três letras maiúsculas.")
    return parser


def principal(argv: Sequence[str] | None = None, *, env: Mapping[str, str] | None = None, transporte: Transporte | None = None,
              relogio: Callable[[], float] | None = None) -> int:
    lab_comum.configurar_saida()
    ambiente = dict(os.environ if env is None else env)
    args = criar_parser().parse_args(argv)
    with o3._proteger_segredos(segredos_para_redigir(ambiente)):
        try:
            return lab_comum.executar_com_tratamento(lambda a: executar(a, ambiente, transporte, relogio), args, tradutor=traduzir_erro)
        except KeyboardInterrupt:  # fora do laço dos passos; dentro dele, o relatório registra o cancelamento
            print("[INTERROMPIDA] A execução foi cancelada.", file=sys.stderr)
            return lab_comum.CODIGO_DIVERGENCIA


if __name__ == "__main__":
    sys.exit(principal())
