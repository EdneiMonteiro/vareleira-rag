"""Regras do Desafio 06 (L100): medir a recuperação e as respostas com conjuntos de perguntas de ajuste e de teste.

Os conjuntos são arquivos JSON em dados/l100/avaliacao. Cada pergunta diz o tipo esperado, os assuntos que a evidência
precisa cobrir e os fatos que uma boa resposta menciona. As métricas são funções puras: podem ser testadas sem Azure.
O acesso ao Azure (busca, embeddings e modelo de geração) entra por objetos recebidos como parâmetro e usa a
identidade do Azure CLI (az login); nenhuma chave é usada.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import lab_agente
import lab_comum
import lab_geracao
import lab_indexacao
import lab_politica
from lab_comum import ErroLab

CONJUNTOS = ("ajuste", "teste")
ETAPAS = ("validar", "recuperacao", "respostas")
PASTA_DOS_CONJUNTOS = lab_comum.RAIZ / "dados" / "l100" / "avaliacao"
K_MEDIDOS = (1, 3, 5, 10)
REPETICOES_MAXIMAS = 5
RESPONDIVEIS = (lab_politica.DOCUMENTADA, lab_politica.CONTRATACAO_INDIVIDUAL)
ERRO = "erro"

CATEGORIAS = ("simples", "composta", "individual", "sem evidência", "fora de escopo", "ambígua")
_CATEGORIA_DO_TIPO = {
    lab_politica.CONTRATACAO_INDIVIDUAL: "individual",
    lab_politica.SEM_EVIDENCIA: "sem evidência",
    lab_politica.FORA_DE_ESCOPO: "fora de escopo",
    lab_politica.AMBIGUA: "ambígua",
}
_SITUACAO_ESPERADA = {
    lab_politica.DOCUMENTADA: lab_politica.RESPONDIDA,
    lab_politica.CONTRATACAO_INDIVIDUAL: lab_politica.RESPONDIDA,
    lab_politica.SEM_EVIDENCIA: lab_politica.RECUSADA,
    lab_politica.FORA_DE_ESCOPO: lab_politica.RECUSADA,
    lab_politica.AMBIGUA: lab_politica.ESCLARECIMENTO,
}
_PADRAO_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,19}")


# --------------------------------------------------------------------------------------
# Conjuntos de perguntas
# --------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Alternativa:
    documento_id: str
    texto_contem: str


@dataclass(frozen=True)
class Assunto:
    """Um assunto que a evidência precisa cobrir. Basta uma das alternativas aparecer em um trecho."""

    nome: str
    alternativas: tuple[Alternativa, ...]


@dataclass(frozen=True)
class PerguntaAvaliada:
    id: str
    pergunta: str
    tipo_esperado: str
    assuntos: tuple[Assunto, ...]
    fatos: tuple[str, ...]

    @property
    def tem_resposta(self) -> bool:
        return self.tipo_esperado in RESPONDIVEIS

    @property
    def situacao_esperada(self) -> str:
        return _SITUACAO_ESPERADA[self.tipo_esperado]

    @property
    def categoria(self) -> str:
        if self.tipo_esperado == lab_politica.DOCUMENTADA:
            return "composta" if len(self.assuntos) > 1 else "simples"
        return _CATEGORIA_DO_TIPO[self.tipo_esperado]


def _texto(valor: Any) -> bool:
    return isinstance(valor, str) and bool(valor.strip())


def _ler_assuntos(entrada: Mapping[str, Any], rotulo: str, problemas: list[str]) -> list[Assunto]:
    tipo = entrada.get("tipo_esperado")
    brutos = entrada.get("assuntos")
    if not isinstance(brutos, list):
        problemas.append(f"{rotulo}: 'assuntos' deve ser uma lista")
        return []
    if tipo in RESPONDIVEIS and not brutos:
        problemas.append(f"{rotulo}: uma pergunta {tipo} precisa de pelo menos um assunto")
    if tipo in _SITUACAO_ESPERADA and tipo not in RESPONDIVEIS and brutos:
        problemas.append(f"{rotulo}: uma pergunta {tipo} não tem evidência esperada: 'assuntos' deve ficar vazia")
    assuntos: list[Assunto] = []
    nomes: set[str] = set()
    for posicao, bruto in enumerate(brutos, start=1):
        alternativas_brutas = bruto.get("alternativas") if isinstance(bruto, dict) else None
        if not isinstance(bruto, dict) or not _texto(bruto.get("nome")) or not isinstance(alternativas_brutas, list) \
                or not alternativas_brutas:
            problemas.append(f"{rotulo}: o assunto {posicao} precisa de 'nome' e de uma lista 'alternativas' com itens")
            continue
        if bruto["nome"] in nomes:
            problemas.append(f"{rotulo}: o assunto '{bruto['nome']}' está repetido")
            continue
        nomes.add(bruto["nome"])
        alternativas = []
        for alternativa in alternativas_brutas:
            if isinstance(alternativa, dict) and _texto(alternativa.get("documento_id")) and _texto(alternativa.get("texto_contem")):
                alternativas.append(Alternativa(alternativa["documento_id"], alternativa["texto_contem"]))
            else:
                problemas.append(f"{rotulo}: cada alternativa de '{bruto['nome']}' precisa de 'documento_id' e 'texto_contem'")
                break
        else:
            assuntos.append(Assunto(bruto["nome"], tuple(alternativas)))
    return assuntos


def carregar_conjunto(nome: str, pasta: Path | str | None = None) -> list[PerguntaAvaliada]:
    """Lê um conjunto de perguntas. Os arquivos ficam fora da pasta de documentos: não são conteúdo recuperável."""
    caminho = Path(pasta or PASTA_DOS_CONJUNTOS) / f"{nome}.json"
    mostrado = lab_comum._mostrar_caminho(caminho)
    try:
        bruto = json.loads(caminho.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ErroLab(f"Conjunto de perguntas não encontrado: {mostrado}") from None
    except json.JSONDecodeError as erro:
        raise ErroLab(f"Conjunto '{nome}' com JSON inválido (linha {erro.lineno}, coluna {erro.colno}).") from None
    except (OSError, UnicodeDecodeError) as erro:
        raise ErroLab(f"Não foi possível ler o conjunto '{nome}': {type(erro).__name__}.") from None
    problemas: list[str] = []
    if not isinstance(bruto, dict) or bruto.get("schema_version") != 1 or bruto.get("sintetico") is not True \
            or bruto.get("conjunto") != nome:
        problemas.append(f"o arquivo precisa ser um objeto com \"schema_version\": 1, \"sintetico\": true e \"conjunto\": \"{nome}\"")
    entradas = bruto.get("perguntas") if isinstance(bruto, dict) else None
    perguntas: list[PerguntaAvaliada] = []
    if not isinstance(entradas, list) or not entradas:
        problemas.append("'perguntas' deve ser uma lista com pelo menos um item")
        entradas = []
    vistos: set[str] = set()
    for indice, entrada in enumerate(entradas):
        rotulo = f"perguntas[{indice}]"
        if not isinstance(entrada, dict):
            problemas.append(f"{rotulo}: deve ser um objeto")
            continue
        identificador = entrada.get("id")
        if not isinstance(identificador, str) or not _PADRAO_ID.fullmatch(identificador) or identificador in vistos:
            problemas.append(f"{rotulo}: 'id' ausente, fora do formato ou repetido")
            continue
        vistos.add(identificador)
        rotulo = identificador
        pergunta, tipo, fatos = entrada.get("pergunta"), entrada.get("tipo_esperado"), entrada.get("fatos")
        ok = True
        if not _texto(pergunta) or len(pergunta.strip()) > lab_geracao.LIMITE_DA_PERGUNTA:
            problemas.append(f"{rotulo}: 'pergunta' ausente, vazia ou longa demais")
            ok = False
        if tipo not in lab_politica.TIPOS:
            problemas.append(f"{rotulo}: 'tipo_esperado' deve ser um destes: {', '.join(lab_politica.TIPOS)}")
            ok = False
        if not isinstance(fatos, list) or not all(_texto(fato) for fato in fatos):
            problemas.append(f"{rotulo}: 'fatos' deve ser uma lista de textos não vazios")
            ok = False
        elif tipo in RESPONDIVEIS and not fatos:
            problemas.append(f"{rotulo}: uma pergunta {tipo} precisa de pelo menos um fato esperado")
            ok = False
        elif tipo in _SITUACAO_ESPERADA and tipo not in RESPONDIVEIS and fatos:
            problemas.append(f"{rotulo}: uma pergunta {tipo} não tem fatos esperados: 'fatos' deve ficar vazia")
            ok = False
        assuntos = _ler_assuntos(entrada, rotulo, problemas)
        if ok and len(assuntos) == len(entrada.get("assuntos") or []):
            perguntas.append(PerguntaAvaliada(identificador, pergunta.strip(), tipo, tuple(assuntos), tuple(fatos)))
    if problemas:
        raise ErroLab(f"Conjunto '{nome}' inválido:\n  - " + "\n  - ".join(problemas))
    return perguntas


def selecionar(perguntas: Sequence[PerguntaAvaliada], ids: str | None) -> list[PerguntaAvaliada]:
    """Filtra as perguntas pelos ids pedidos (separados por vírgula), na ordem do conjunto."""
    if not ids:
        return list(perguntas)
    pedidos = [item.strip() for item in ids.split(",") if item.strip()]
    existentes = {pergunta.id for pergunta in perguntas}
    desconhecidos = [item for item in pedidos if item not in existentes]
    if desconhecidos or not pedidos:
        raise ErroLab(f"Ids fora do conjunto: {', '.join(desconhecidos) or '(nenhum informado)'}. "
                      f"Ids disponíveis: {', '.join(pergunta.id for pergunta in perguntas)}.")
    return [pergunta for pergunta in perguntas if pergunta.id in pedidos]


# --------------------------------------------------------------------------------------
# Conferência dos conjuntos contra os documentos (sem Azure)
# --------------------------------------------------------------------------------------

def verificar_conjuntos(conjuntos: Mapping[str, Sequence[PerguntaAvaliada]],
                        trechos: Sequence[lab_indexacao.Trecho], textos_dos_documentos: Sequence[str]) -> list[str]:
    """Problemas que tornariam a medição enganosa: evidência inalcançável, pergunta copiada e conjuntos misturados."""
    problemas: list[str] = []
    por_documento: dict[str, list[str]] = {}
    for trecho in trechos:
        por_documento.setdefault(trecho.documento.id, []).append(trecho.conteudo.lower())
    documentos = "\n".join(lab_politica.normalizar(texto) for texto in textos_dos_documentos)
    ids: dict[str, str] = {}
    textos: dict[str, str] = {}
    for conjunto, perguntas in conjuntos.items():
        for pergunta in perguntas:
            rotulo = f"{conjunto}/{pergunta.id}"
            if pergunta.id in ids:
                problemas.append(f"{rotulo}: o id também existe em {ids[pergunta.id]}")
            ids[pergunta.id] = conjunto
            normalizada = lab_politica.normalizar(pergunta.pergunta)
            if normalizada in textos:
                problemas.append(f"{rotulo}: a pergunta repete a de {textos[normalizada]}")
            textos[normalizada] = rotulo
            if normalizada in documentos:
                problemas.append(f"{rotulo}: o texto da pergunta aparece nos documentos")
            for assunto in pergunta.assuntos:
                presentes = 0
                for alternativa in assunto.alternativas:
                    if alternativa.documento_id not in por_documento:
                        problemas.append(f"{rotulo}: o documento '{alternativa.documento_id}' não existe no inventário")
                    elif any(alternativa.texto_contem.lower() in conteudo for conteudo in por_documento[alternativa.documento_id]):
                        presentes += 1
                    else:
                        problemas.append(f"{rotulo}: '{alternativa.texto_contem}' não aparece em nenhum trecho de {alternativa.documento_id}")
                if not presentes:
                    problemas.append(f"{rotulo}: nenhuma alternativa do assunto '{assunto.nome}' é alcançável nos trechos")
    return problemas


# --------------------------------------------------------------------------------------
# Métricas de recuperação
# --------------------------------------------------------------------------------------

def _cobre(assunto: Assunto, resultado: Mapping[str, Any]) -> bool:
    conteudo = str(resultado.get("conteudo") or "").lower()
    return any(alternativa.documento_id == resultado.get("documento_id") and alternativa.texto_contem.lower() in conteudo
               for alternativa in assunto.alternativas)


def assuntos_cobertos(pergunta: PerguntaAvaliada, resultados: Sequence[Mapping[str, Any]]) -> set[str]:
    """Nomes dos assuntos que algum dos resultados cobre."""
    return {assunto.nome for assunto in pergunta.assuntos if any(_cobre(assunto, resultado) for resultado in resultados)}


def primeira_posicao(pergunta: PerguntaAvaliada, resultados: Sequence[Mapping[str, Any]]) -> int | None:
    """Posição (1 é a primeira) do primeiro resultado que cobre algum assunto; None se nenhum cobre."""
    for posicao, resultado in enumerate(resultados, start=1):
        if any(_cobre(assunto, resultado) for assunto in pergunta.assuntos):
            return posicao
    return None


def acertou(pergunta: PerguntaAvaliada, resultados: Sequence[Mapping[str, Any]], k: int) -> bool:
    """Todos os assuntos da pergunta estão cobertos pelos k primeiros resultados."""
    return len(assuntos_cobertos(pergunta, resultados[:k])) == len(pergunta.assuntos)


@dataclass(frozen=True)
class PosicaoNaBusca:
    id: str
    primeira: int | None
    cobertos: int
    total: int
    acerto: Mapping[int, bool]


def medir_posicao(pergunta: PerguntaAvaliada, resultados: Sequence[Mapping[str, Any]],
                  ks: Sequence[int] = K_MEDIDOS) -> PosicaoNaBusca:
    return PosicaoNaBusca(pergunta.id, primeira_posicao(pergunta, resultados), len(assuntos_cobertos(pergunta, resultados)),
                          len(pergunta.assuntos), {k: acertou(pergunta, resultados, k) for k in ks})


@dataclass(frozen=True)
class ResumoDeBusca:
    modo: str
    perguntas: int
    acertos: Mapping[int, int]
    mrr: float
    posicoes: tuple[PosicaoNaBusca, ...]


def resumir_busca(modo: str, posicoes: Sequence[PosicaoNaBusca], ks: Sequence[int] = K_MEDIDOS) -> ResumoDeBusca:
    """acerto@k conta as perguntas com todos os assuntos nos k primeiros; MRR é a média de 1 sobre a primeira posição."""
    total = len(posicoes)
    mrr = sum(1 / posicao.primeira for posicao in posicoes if posicao.primeira) / total if total else 0.0
    return ResumoDeBusca(modo, total, {k: sum(1 for posicao in posicoes if posicao.acerto[k]) for k in ks}, mrr, tuple(posicoes))


def avaliar_recuperacao(perguntas: Sequence[PerguntaAvaliada], recuperador: lab_geracao.Recuperador,
                        modos: Sequence[str] = lab_indexacao.MODOS_DE_BUSCA, ks: Sequence[int] = K_MEDIDOS,
                        ao_medir: Callable[[str, PerguntaAvaliada], None] | None = None) -> list[ResumoDeBusca]:
    """Faz uma busca de k máximo por pergunta e por modo; só as perguntas com resposta nos documentos entram."""
    respondiveis = [pergunta for pergunta in perguntas if pergunta.tem_resposta]
    k_maximo = max(ks)
    resumos = []
    for modo in modos:
        posicoes = []
        for pergunta in respondiveis:
            if ao_medir:
                ao_medir(modo, pergunta)
            posicoes.append(medir_posicao(pergunta, recuperador.recuperar(pergunta.pergunta, modo, k_maximo).resultados, ks))
        resumos.append(resumir_busca(modo, posicoes, ks))
    return resumos


# --------------------------------------------------------------------------------------
# Respostas
# --------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Resposta:
    """O que o fluxo devolveu para uma pergunta; `decisao` é None quando o modelo respondeu fora do formato."""

    decisao: lab_politica.Decisao | None
    tokens_entrada: int
    tokens_saida: int
    buscas: int
    segundos: float


@dataclass(frozen=True)
class Avaliada:
    pergunta: PerguntaAvaliada
    resposta: Resposta

    @property
    def tipo(self) -> str:
        return self.resposta.decisao.tipo if self.resposta.decisao else ERRO

    @property
    def situacao(self) -> str:
        return self.resposta.decisao.situacao if self.resposta.decisao else ERRO

    @property
    def tipo_certo(self) -> bool:
        return self.tipo == self.pergunta.tipo_esperado

    @property
    def situacao_certa(self) -> bool:
        return self.situacao == self.pergunta.situacao_esperada

    @property
    def fatos_esperados(self) -> int:
        """Só as respostas mostradas à pessoa contam fatos."""
        return len(self.pergunta.fatos) if self.situacao == lab_politica.RESPONDIDA and self.pergunta.tem_resposta else 0

    @property
    def fatos_presentes(self) -> int:
        if not self.fatos_esperados:
            return 0
        texto = lab_politica.normalizar(self.resposta.decisao.texto)  # type: ignore[union-attr]
        return sum(1 for fato in self.pergunta.fatos if lab_politica.normalizar(fato) in texto)

    @property
    def falsa_recusa(self) -> bool:
        """A pergunta tem resposta nos documentos e o sistema recusou ou pediu esclarecimento."""
        return self.pergunta.tem_resposta and self.situacao in (lab_politica.RECUSADA, lab_politica.ESCLARECIMENTO)

    @property
    def falsa_resposta(self) -> bool:
        """A pergunta não tem resposta nos documentos e o sistema respondeu."""
        return not self.pergunta.tem_resposta and self.situacao == lab_politica.RESPONDIDA

    @property
    def motivo(self) -> str:
        """Por que a pergunta não está totalmente certa; vazio quando está."""
        decisao = self.resposta.decisao
        if decisao is None:
            return "o modelo respondeu fora do formato"
        if decisao.situacao == lab_politica.DESCARTADA:
            return "resposta descartada: " + (decisao.problemas[0] if decisao.problemas else "sem motivo registrado")
        if not self.situacao_certa:
            return f"{decisao.situacao}, esperada {self.pergunta.situacao_esperada}"
        if not self.tipo_certo:
            return f"tipo {decisao.tipo}, esperado {self.pergunta.tipo_esperado}"
        if self.fatos_presentes < self.fatos_esperados:
            return f"fatos {self.fatos_presentes} de {self.fatos_esperados}"
        return ""


@dataclass(frozen=True)
class ResumoDeRespostas:
    total: int
    tipo_certo: int
    situacao_certa: int
    descartadas: int
    erros: int
    falsas_recusas: int
    falsas_respostas: int
    fatos_presentes: int
    fatos_esperados: int
    tokens_entrada: float
    tokens_saida: float
    buscas: float
    segundos: float


def resumir(avaliadas: Sequence[Avaliada]) -> ResumoDeRespostas:
    total = len(avaliadas)

    def media(valores: Sequence[float]) -> float:
        return sum(valores) / total if total else 0.0

    return ResumoDeRespostas(
        total=total,
        tipo_certo=sum(1 for item in avaliadas if item.tipo_certo),
        situacao_certa=sum(1 for item in avaliadas if item.situacao_certa),
        descartadas=sum(1 for item in avaliadas if item.situacao == lab_politica.DESCARTADA),
        erros=sum(1 for item in avaliadas if item.situacao == ERRO),
        falsas_recusas=sum(1 for item in avaliadas if item.falsa_recusa),
        falsas_respostas=sum(1 for item in avaliadas if item.falsa_resposta),
        fatos_presentes=sum(item.fatos_presentes for item in avaliadas),
        fatos_esperados=sum(item.fatos_esperados for item in avaliadas),
        tokens_entrada=media([item.resposta.tokens_entrada for item in avaliadas]),
        tokens_saida=media([item.resposta.tokens_saida for item in avaliadas]),
        buscas=media([item.resposta.buscas for item in avaliadas]),
        segundos=media([item.resposta.segundos for item in avaliadas]),
    )


def resumir_por_categoria(avaliadas: Sequence[Avaliada]) -> dict[str, ResumoDeRespostas]:
    return {categoria: resumir([item for item in avaliadas if item.pergunta.categoria == categoria])
            for categoria in CATEGORIAS if any(item.pergunta.categoria == categoria for item in avaliadas)}


def avaliar_respostas(perguntas: Sequence[PerguntaAvaliada], responder: Callable[[PerguntaAvaliada], Resposta],
                      ao_concluir: Callable[[Avaliada], None] | None = None) -> list[Avaliada]:
    avaliadas = []
    for pergunta in perguntas:
        avaliada = Avaliada(pergunta, responder(pergunta))
        avaliadas.append(avaliada)
        if ao_concluir:
            ao_concluir(avaliada)
    return avaliadas


def criar_respondedor_fixo(recuperador: lab_geracao.Recuperador, cliente: lab_geracao.ClienteGeracao,
                           modo: str, k: int) -> Callable[[PerguntaAvaliada], Resposta]:
    """Recuperação obrigatória: o programa busca uma vez com a pergunta inteira e entrega os trechos ao modelo."""

    def responder(pergunta: PerguntaAvaliada) -> Resposta:
        inicio = time.monotonic()
        recuperacao = recuperador.recuperar(pergunta.pergunta, modo, k)
        if not recuperacao.resultados:  # sem trechos o fluxo não chama o modelo: equivale a "sem evidência"
            decisao = lab_politica.Decisao(lab_politica.RECUSADA, lab_politica.SEM_EVIDENCIA, lab_politica.SEM_EVIDENCIA,
                                           lab_politica.MENSAGEM_SEM_EVIDENCIA, "", (), ())
            return Resposta(decisao, 0, 0, 1, time.monotonic() - inicio)
        pedido = lab_geracao.montar_pedido(pergunta.pergunta, recuperacao.resultados, lab_politica.INSTRUCOES_COMPLETAS)
        try:
            resultado = cliente.gerar(pedido, lab_politica.CONTRATO_COMPLETO)
        except lab_geracao.ErroDeFormato:
            return Resposta(None, 0, 0, 1, time.monotonic() - inicio)
        decisao = lab_politica.aplicar_politica(resultado.saida, recuperacao.resultados, pergunta.pergunta)
        return Resposta(decisao, resultado.tokens_entrada, resultado.tokens_saida, 1, time.monotonic() - inicio)

    return responder


def criar_respondedor_agente(args: Any, recuperador: lab_geracao.Recuperador) -> Callable[[PerguntaAvaliada], Resposta]:
    """Recuperação por ferramenta: o agente do MAF decide quando e o que buscar, dentro dos limites de `args`."""

    def responder(pergunta: PerguntaAvaliada) -> Resposta:
        inicio = time.monotonic()
        try:
            resultado = lab_agente.consultar_com_ferramenta(args, pergunta.pergunta, recuperador)
        except lab_geracao.ErroDeFormato:
            return Resposta(None, 0, 0, 0, time.monotonic() - inicio)
        decisao = lab_agente.decidir(resultado.saida, resultado.trechos, pergunta.pergunta, resultado.buscas_feitas, True)
        return Resposta(decisao, resultado.tokens_entrada, resultado.tokens_saida, resultado.buscas_feitas,
                        time.monotonic() - inicio)

    return responder
