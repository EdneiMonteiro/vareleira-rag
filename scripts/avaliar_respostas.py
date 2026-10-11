"""Mede a recuperação e as respostas do laboratório com conjuntos de ajuste e de teste (L100, Desafio 06).

Etapas:
    validar      confere os dois conjuntos contra os documentos locais; não acessa o Azure.
    recuperacao  mede, nos três modos de busca, se os trechos pertinentes aparecem entre os k primeiros (acerto@k) e a
                 posição do primeiro (MRR). Só lê o índice.
    respostas    responde a cada pergunta com o fluxo escolhido (--recuperacao obrigatoria ou ferramenta), aplica a política
                 do Desafio 04 e conta tipos, recusas, respostas descartadas e fatos esperados. Consome tokens.

Use o conjunto de ajuste para comparar configurações e escolher uma. Use o conjunto de teste uma vez, depois da escolha:
ele mostra só os números, e olhar as perguntas que falharam para mudar a configuração o transforma em outro conjunto de
ajuste. Não altera nada no Azure. Usa a identidade do Azure CLI (az login); não usa chaves.

Exemplos:
    python scripts\\avaliar_respostas.py --etapa validar
    python scripts\\avaliar_respostas.py --etapa recuperacao --conjunto ajuste --busca <busca> --modelos <modelos>
    python scripts\\avaliar_respostas.py --etapa respostas --conjunto ajuste --busca <busca> --modelos <modelos> --k 5
"""

from __future__ import annotations

import argparse
import sys
from typing import Sequence

import lab_agente
import lab_avaliacao
import lab_comum
import lab_geracao
import lab_indexacao
from lab_avaliacao import Avaliada, PerguntaAvaliada, ResumoDeBusca, ResumoDeRespostas
from lab_comum import ErroLab

LARGURA_DO_ROTULO = 34
TEXTO_NAS_FALHAS, TEXTO_SEMPRE = "falhas", "sempre"


def validar_repeticoes(valor: str) -> int:
    try:
        numero = int(valor)
    except ValueError:
        numero = 0
    if not 1 <= numero <= lab_avaliacao.REPETICOES_MAXIMAS:
        raise argparse.ArgumentTypeError(
            f"As repetições devem ser um número de 1 a {lab_avaliacao.REPETICOES_MAXIMAS} (recebido: {valor!r}).")
    return numero


def decimal(valor: float, casas: int = 1) -> str:
    return f"{valor:.{casas}f}".replace(".", ",")


def linha(rotulo: str, valor: str) -> None:
    print(f"  {rotulo} {'.' * max(2, LARGURA_DO_ROTULO - len(rotulo))} {valor}")


def descrever_categorias(perguntas: Sequence[PerguntaAvaliada]) -> str:
    return " · ".join(f"{categoria} {sum(1 for p in perguntas if p.categoria == categoria)}"
                      for categoria in lab_avaliacao.CATEGORIAS if any(p.categoria == categoria for p in perguntas))


def aviso_do_teste() -> None:
    print("Conjunto de teste: meça uma vez, com a configuração que você escolheu no conjunto de ajuste. Mudar a configuração "
          "depois de ver estes números transforma o teste em ajuste. Só os números aparecem; --mostrar-perguntas mostra o resto.")


# --------------------------------------------------------------------------------------
# Etapa validar
# --------------------------------------------------------------------------------------

def validar(args: argparse.Namespace) -> int:
    conjuntos = {nome: lab_avaliacao.carregar_conjunto(nome) for nome in lab_avaliacao.CONJUNTOS}
    inventario = lab_comum.carregar_e_validar(args.inventario)
    documentos = [(documento, lab_comum.ler_conteudo(documento).decode("utf-8")) for documento in inventario.documentos]
    trechos = lab_indexacao.dividir_documentos(documentos)
    for nome, perguntas in conjuntos.items():
        print(f"Conjunto {nome}: {len(perguntas)} pergunta(s)")
        print(f"  {descrever_categorias(perguntas)}")
    problemas = lab_avaliacao.verificar_conjuntos(conjuntos, trechos, [texto for _, texto in documentos])
    if problemas:
        print("\n[FALHA] Os conjuntos não conferem com os documentos locais:")
        for problema in problemas:
            print(f"  - {problema}")
        return lab_comum.CODIGO_DIVERGENCIA
    print(f"\nConferência: toda evidência esperada aparece em um dos {len(trechos)} trechos dos documentos locais, nenhuma "
          "pergunta foi copiada dos documentos e os dois conjuntos não repetem ids nem perguntas.")
    return lab_comum.CODIGO_OK


# --------------------------------------------------------------------------------------
# Etapa recuperacao
# --------------------------------------------------------------------------------------

def mostrar_busca(resumos: Sequence[ResumoDeBusca]) -> None:
    ks = list(resumos[0].acertos)
    total = resumos[0].perguntas
    print("\nPerguntas com todos os assuntos entre os k primeiros trechos (acerto@k) e MRR (média de 1 sobre a posição do primeiro trecho pertinente):")
    print("  modo        " + "".join(f"acerto@{k}".ljust(11) for k in ks) + " MRR")
    for resumo in resumos:
        print(f"  {resumo.modo:<10}  " + "".join(f"{resumo.acertos[k]} de {total}".ljust(11) for k in ks) + f" {decimal(resumo.mrr, 2)}")


def mostrar_posicoes(resumos: Sequence[ResumoDeBusca], perguntas: Sequence[PerguntaAvaliada]) -> None:
    por_id = {pergunta.id: pergunta for pergunta in perguntas}
    k_maximo = max(resumos[0].acertos)
    print(f"\nPosição do primeiro trecho pertinente (- = nenhum nos {k_maximo} primeiros; * = faltam assuntos nos {k_maximo} primeiros):")
    print("  id      categoria       " + "".join(f"{resumo.modo:<10}" for resumo in resumos))
    for posicao in resumos[0].posicoes:
        celulas = ""
        for resumo in resumos:
            medida = next(item for item in resumo.posicoes if item.id == posicao.id)
            texto = str(medida.primeira) if medida.primeira else "-"
            celulas += f"{texto + ('*' if medida.cobertos < medida.total else ''):<10}"
        print(f"  {posicao.id:<6}  {por_id[posicao.id].categoria:<14}  {celulas}")


def executar_recuperacao(args: argparse.Namespace, perguntas: Sequence[PerguntaAvaliada], mostrar_detalhes: bool) -> int:
    respondiveis = [pergunta for pergunta in perguntas if pergunta.tem_resposta]
    if not respondiveis:
        raise ErroLab("Nenhuma das perguntas escolhidas tem resposta nos documentos; a medição da recuperação só usa "
                      "perguntas com resposta.")
    print(f"Recuperação · conjunto {args.conjunto} · {len(respondiveis)} de {len(perguntas)} pergunta(s) têm resposta nos "
          f"documentos e entram · acerto até k={max(lab_avaliacao.K_MEDIDOS)} · serviço de busca '{args.busca}', índice '{args.indice}'")
    if args.conjunto == "teste":
        aviso_do_teste()
    recuperador = lab_geracao.Recuperador(
        lab_indexacao.abrir_indice(args.busca, args.indice, args.tenant_id),
        lab_indexacao.criar_cliente_embeddings(args.modelos, args.deployment, args.dimensoes, args.tenant_id))
    ultimo: list[str] = []

    def ao_medir(modo: str, _pergunta: PerguntaAvaliada) -> None:
        if not ultimo or ultimo[-1] != modo:
            ultimo.append(modo)
            print(f"  medindo o modo {modo}...", flush=True)

    resumos = lab_avaliacao.avaliar_recuperacao(perguntas, recuperador, ao_medir=ao_medir)
    mostrar_busca(resumos)
    if mostrar_detalhes:
        mostrar_posicoes(resumos, respondiveis)
    print("\nUm trecho é pertinente quando contém uma das frases esperadas do conjunto. As perguntas sem resposta nos "
          "documentos ficam de fora, e a posição só vale dentro do mesmo modo.")
    return lab_comum.CODIGO_OK


# --------------------------------------------------------------------------------------
# Etapa respostas
# --------------------------------------------------------------------------------------

def mostrar_avaliada(avaliada: Avaliada, texto: str) -> None:
    """Uma linha por pergunta; o texto da pergunta aparece sempre, só nas falhas ou nunca, conforme `texto`."""
    pergunta, resposta = avaliada.pergunta, avaliada.resposta
    marca = "[ok]   " if not avaliada.motivo else "[falha]"
    fatos = f"fatos {avaliada.fatos_presentes}/{avaliada.fatos_esperados}" if avaliada.fatos_esperados else "fatos -"
    print(f"  {marca} {pergunta.id:<6} {pergunta.categoria:<14} tipo {avaliada.tipo:<22} {avaliada.situacao:<14} {fatos:<10} "
          f"{resposta.tokens_entrada:>5} tokens {decimal(resposta.segundos):>5} s" + (f"  {avaliada.motivo}" if avaliada.motivo else ""),
          flush=True)
    if texto == TEXTO_SEMPRE or (texto == TEXTO_NAS_FALHAS and avaliada.motivo):
        print(f"           \"{pergunta.pergunta}\"")


def mostrar_resumo(resumo: ResumoDeRespostas, por_categoria: dict[str, ResumoDeRespostas], titulo: str) -> None:
    print(f"\n{titulo}")
    linha("Tipo da pergunta correto", f"{resumo.tipo_certo} de {resumo.total}")
    linha("Situação correta", f"{resumo.situacao_certa} de {resumo.total} (respondeu, recusou ou pediu esclarecimento como devia)")
    linha("Respostas descartadas pela verificação", str(resumo.descartadas))
    linha("Erros de formato do modelo", str(resumo.erros))
    linha("Falsas recusas", f"{resumo.falsas_recusas} (pergunta com resposta nos documentos que não foi respondida)")
    linha("Falsas respostas", f"{resumo.falsas_respostas} (pergunta sem resposta nos documentos que foi respondida)")
    linha("Fatos esperados presentes", f"{resumo.fatos_presentes} de {resumo.fatos_esperados} (nas respostas mostradas)")
    linha("Tokens de entrada (média)", str(round(resumo.tokens_entrada)))
    linha("Tokens de saída (média)", str(round(resumo.tokens_saida)))
    linha("Buscas por pergunta (média)", decimal(resumo.buscas))
    linha("Tempo por pergunta (média)", f"{decimal(resumo.segundos)} s")
    print("\n  categoria       perguntas  tipo certo  situação certa  fatos")
    for categoria, parte in por_categoria.items():
        fatos = f"{parte.fatos_presentes}/{parte.fatos_esperados}" if parte.fatos_esperados else "-"
        print(f"  {categoria:<14}  {parte.total:>9}  {parte.tipo_certo:>10}  {parte.situacao_certa:>14}  {fatos}")


def faixa(valores: Sequence[int]) -> str:
    return str(valores[0]) if min(valores) == max(valores) else f"de {min(valores)} a {max(valores)}"


def mostrar_variacao(resumos: Sequence[ResumoDeRespostas]) -> None:
    total = resumos[0].total
    print(f"\nVariação entre as {len(resumos)} execuções (o modelo não responde igual a cada vez)")
    linha("Tipo da pergunta correto", f"{faixa([r.tipo_certo for r in resumos])} de {total}")
    linha("Situação correta", f"{faixa([r.situacao_certa for r in resumos])} de {total}")
    linha("Respostas descartadas", faixa([r.descartadas for r in resumos]))
    linha("Fatos esperados presentes", f"{faixa([r.fatos_presentes for r in resumos])} de {resumos[0].fatos_esperados}"
          if len({r.fatos_esperados for r in resumos}) == 1 else faixa([r.fatos_presentes for r in resumos]))


def executar_respostas(args: argparse.Namespace, perguntas: Sequence[PerguntaAvaliada], texto: str) -> int:
    por_ferramenta = args.recuperacao == "ferramenta"
    fluxo = f"recuperação por ferramenta (até {args.maximo_de_buscas} busca(s))" if por_ferramenta else "recuperação obrigatória"
    print(f"Respostas · conjunto {args.conjunto} · {len(perguntas)} pergunta(s) · {fluxo} · modo {args.modo} · k {args.k} "
          f"· esforço {args.esforco} · deployment '{args.deployment_geracao}'")
    if args.conjunto == "teste":
        aviso_do_teste()
    recuperador = lab_geracao.criar_recuperador(args)
    if por_ferramenta:
        responder = lab_avaliacao.criar_respondedor_agente(args, recuperador)
    else:
        cliente = lab_geracao.criar_cliente_geracao(args.modelos, args.deployment_geracao, args.esforco, args.tenant_id)
        responder = lab_avaliacao.criar_respondedor_fixo(recuperador, cliente, args.modo, args.k)
    mostrar_linhas = args.conjunto == "ajuste" or args.mostrar_perguntas
    resumos: list[ResumoDeRespostas] = []
    for numero in range(1, args.repeticoes + 1):
        if args.repeticoes > 1:
            print(f"\nExecução {numero} de {args.repeticoes}")
        avaliadas = lab_avaliacao.avaliar_respostas(
            perguntas, responder, (lambda item: mostrar_avaliada(item, texto)) if mostrar_linhas else None)
        resumo = lab_avaliacao.resumir(avaliadas)
        resumos.append(resumo)
        mostrar_resumo(resumo, lab_avaliacao.resumir_por_categoria(avaliadas),
                       "Resumo" if args.repeticoes == 1 else f"Resumo da execução {numero}")
    if len(resumos) > 1:
        mostrar_variacao(resumos)
    print("\nOs fatos esperados são frases curtas que a resposta deveria conter; uma boa resposta com outras palavras "
          "conta como ausente. A política confere as citações, não se a resposta cobre toda a pergunta.")
    return lab_comum.CODIGO_OK


# --------------------------------------------------------------------------------------
# Entrada
# --------------------------------------------------------------------------------------

def executar(args: argparse.Namespace) -> int:
    if args.etapa == "validar":
        return validar(args)
    if not args.conjunto:
        raise ErroLab("Informe o conjunto: --conjunto ajuste ou --conjunto teste.")
    perguntas = lab_avaliacao.selecionar(lab_avaliacao.carregar_conjunto(args.conjunto), args.ids)
    mostrar_texto = TEXTO_SEMPRE if args.mostrar_perguntas else TEXTO_NAS_FALHAS
    if args.etapa == "recuperacao":
        return executar_recuperacao(args, perguntas, args.conjunto == "ajuste" or args.mostrar_perguntas)
    return executar_respostas(args, perguntas, mostrar_texto)


def _etapa_pedida(argv: Sequence[str]) -> str | None:
    for posicao, argumento in enumerate(argv):
        if argumento == "--etapa" and posicao + 1 < len(argv):
            return argv[posicao + 1]
        if argumento.startswith("--etapa="):
            return argumento.split("=", 1)[1]
    return None


def principal(argv: list[str] | None = None) -> int:
    lab_comum.configurar_saida()
    argumentos = list(sys.argv[1:] if argv is None else argv)
    parser = lab_comum.criar_parser(__doc__, armazenamento=False, inventario=True)
    lab_indexacao.adicionar_argumentos_indice(parser, obrigatorios=_etapa_pedida(argumentos) != "validar")
    lab_geracao.adicionar_argumentos_geracao(parser)
    lab_agente.adicionar_argumentos_agente(parser, mostrar_agente=False, padrao="obrigatoria")
    parser.add_argument("--etapa", choices=lab_avaliacao.ETAPAS, default="recuperacao",
                        help="validar (sem Azure), recuperacao (padrão) ou respostas.")
    parser.add_argument("--conjunto", choices=lab_avaliacao.CONJUNTOS, default=None,
                        help="ajuste (para comparar configurações) ou teste (para medir uma vez). Obrigatório fora de --etapa validar.")
    parser.add_argument("--ids", default=None, help="Mede só estas perguntas, separadas por vírgula (por exemplo AJ-01,AJ-05).")
    parser.add_argument("--repeticoes", default=1, type=validar_repeticoes,
                        help=f"Repete a etapa respostas e mostra a variação, de 1 a {lab_avaliacao.REPETICOES_MAXIMAS} (padrão: 1).")
    parser.add_argument("--mostrar-perguntas", action="store_true",
                        help="Mostra o texto das perguntas e o resultado de cada uma, inclusive no conjunto de teste.")
    args = parser.parse_args(argumentos)
    return lab_comum.executar_com_tratamento(executar, args, tradutor=lab_indexacao.traduzir_erro_indexacao)


if __name__ == "__main__":
    sys.exit(principal())
