"""Responde a uma pergunta com base nos documentos indexados e mostra as fontes (L100, Desafios 03 e 04).

Fluxo: a pergunta vira um embedding, a busca devolve os trechos mais pertinentes, o modelo de geração
recebe só esses trechos como contexto e responde, e o programa confere o que o modelo devolveu antes de
mostrar. Não altera nada no Azure. Usa a identidade do Azure CLI (az login); não usa chaves.

A política básica (padrão) confere que cada fonte citada foi recuperada. A política completa
(--politica completa) também classifica a pergunta, exige citações literais dos trechos e recusa o que os
documentos não autorizam. A resposta explica regras do produto: ela não confirma as coberturas de uma
contratação específica.

Exemplos:
    python scripts\\perguntar.py --busca <busca> --modelos <modelos> --pergunta "O seguro cobre danos elétricos?"
    python scripts\\perguntar.py --busca <busca> --modelos <modelos> --pergunta "Quanto custa o seguro?" --politica completa
"""

from __future__ import annotations

import argparse
import sys
import textwrap
from typing import Any, Mapping, Sequence

import lab_comum
import lab_geracao
import lab_identidade
import lab_indexacao
import lab_politica
from lab_comum import ErroLab

LARGURA = 100
POLITICAS = ("basica", "completa")
POLITICA_PADRAO = "basica"
LARGURA_DA_CITACAO = 160


def escrever(texto: str, recuo: str = "  ") -> None:
    print(textwrap.fill(texto, width=LARGURA, initial_indent=recuo, subsequent_indent=recuo))


def mostrar_trechos(resultados: Sequence[Mapping[str, Any]]) -> None:
    if not resultados:
        print("Nenhum trecho recuperado.")
        return
    print(f"Trechos recuperados ({len(resultados)}):")
    for posicao, item in enumerate(resultados, start=1):
        print(f"  {posicao}. [{item.get('id', '?')}] pontuação {item.get('@search.score', 0):.3f} · {item.get('secao', '?')}")


def mostrar_pedido(pedido: lab_geracao.Pedido) -> None:
    print("\n--- Instruções enviadas ao modelo ---")
    print(pedido.instrucoes.rstrip())
    print("\n--- Entrada enviada ao modelo ---")
    print(pedido.entrada)
    print("--- Fim do pedido ---")


def mostrar_resposta(saida: Mapping[str, Any], resultados: Sequence[Mapping[str, Any]]) -> list[str]:
    """Mostra a resposta e as fontes, e devolve os ids citados na ordem de citação."""
    print("\nResposta:")
    escrever(str(saida["resposta"]))
    citadas = list(dict.fromkeys(saida["fontes"]))
    por_id = {str(item["id"]): item for item in resultados}
    if citadas:
        print("\nFontes citadas:")
        for identificador in citadas:
            print(f"  {lab_geracao.descrever_fonte(por_id[identificador])}")
    else:
        print("\n[AVISO] A resposta não cita nenhuma fonte: não a use como regra do produto.")
    return citadas


def mostrar_origem(args: argparse.Namespace, recuperacao: lab_geracao.Recuperacao) -> None:
    """Passos 1 e 2 do percurso: do texto da pergunta aos trechos recuperados."""
    ids = ", ".join(str(item["id"]) for item in recuperacao.resultados)
    print("\nComo esta resposta foi produzida:")
    if args.modo == "texto":
        print("  1. A busca por palavras usou o texto da pergunta, sem embeddings.")
    else:
        print(f"  1. A pergunta virou um vetor ({recuperacao.tokens_embeddings} tokens de embeddings).")
    print(f"  2. A busca '{args.modo}' devolveu {len(recuperacao.resultados)} trecho(s): {ids}.")


def mostrar_uso(resultado: lab_geracao.ResultadoGeracao) -> None:
    print(f"  Uso na geração: {resultado.tokens_entrada} tokens de entrada e {resultado.tokens_saida} de saída "
          f"({resultado.tokens_raciocinio} de raciocínio).")


def apresentar_basica(args: argparse.Namespace, recuperacao: lab_geracao.Recuperacao,
                      resultado: lab_geracao.ResultadoGeracao) -> int:
    """Política básica (Desafio 03): a resposta só é mostrada se todas as fontes citadas foram recuperadas."""
    desconhecidas = lab_geracao.fontes_desconhecidas(resultado.saida["fontes"], recuperacao.resultados)
    if desconhecidas:
        print("\n[FALHA] O modelo citou fontes que não estão entre os trechos recuperados: "
              f"{', '.join(desconhecidas)}. A resposta não foi apresentada. Repita o comando; se persistir, "
              "use --mostrar-prompt para examinar o pedido.")
        return lab_comum.CODIGO_DIVERGENCIA
    citadas = mostrar_resposta(resultado.saida, recuperacao.resultados)
    mostrar_origem(args, recuperacao)
    print(f"  3. O deployment '{args.deployment_geracao}' recebeu esses trechos e a pergunta, e citou {len(citadas)}.")
    print("  4. O script conferiu que cada fonte citada está entre os trechos recuperados.")
    mostrar_uso(resultado)
    print("\nLembrete: a resposta explica regras do produto; ela não confirma as coberturas de uma contratação.")
    return lab_comum.CODIGO_OK


def mostrar_decisao(decisao: lab_politica.Decisao, resultados: Sequence[Mapping[str, Any]]) -> None:
    """Tipo, texto, evidências e aviso que a política manda mostrar à pessoa."""
    rotulo = lab_politica.ROTULOS[decisao.tipo]
    if decisao.tipo != decisao.tipo_do_modelo:
        rotulo += (f" (o modelo classificou como {lab_politica.ROTULOS[decisao.tipo_do_modelo]}; "
                   "uma regra do programa mudou o tipo)")
    print(f"\nTipo da pergunta: {rotulo}")
    titulo = {lab_politica.RESPONDIDA: "Resposta", lab_politica.RECUSADA: "Recusa",
              lab_politica.ESCLARECIMENTO: "Pergunta de esclarecimento"}[decisao.situacao]
    print(f"\n{titulo}:")
    escrever(decisao.texto)
    if decisao.evidencias:
        por_id = {str(item["id"]): item for item in resultados}
        print("\nEvidências conferidas (cada citação aparece literalmente no trecho):")
        for evidencia in decisao.evidencias:
            citacao = textwrap.shorten(evidencia.citacao, width=LARGURA_DA_CITACAO, placeholder="…")
            print(f"  [{evidencia.fonte}] \"{citacao}\"")
            print(f"      {lab_geracao.descrever_origem(por_id[evidencia.fonte])}")
        if decisao.citacoes_curtas_ignoradas:
            print(f"  ({decisao.citacoes_curtas_ignoradas} citação(ões) curtas demais foram ignoradas.)")
    if decisao.aviso:
        print("\nAviso:")
        escrever(decisao.aviso)


def apresentar_completa(args: argparse.Namespace, pergunta: str, recuperacao: lab_geracao.Recuperacao,
                        resultado: lab_geracao.ResultadoGeracao) -> int:
    """Política completa (Desafio 04): o programa decide o que a pessoa vê, conforme o tipo da pergunta."""
    decisao = lab_politica.aplicar_politica(resultado.saida, recuperacao.resultados, pergunta)
    if decisao.situacao == lab_politica.DESCARTADA:
        print("\n[FALHA] A resposta do modelo foi descartada porque não passou na verificação do programa:")
        for problema in decisao.problemas:
            print(f"  - {problema}")
        print("Nenhuma resposta foi apresentada. Repita o comando; se persistir, use --mostrar-prompt para examinar o pedido.")
        mostrar_uso(resultado)
        return lab_comum.CODIGO_DIVERGENCIA
    mostrar_decisao(decisao, recuperacao.resultados)
    mostrar_origem(args, recuperacao)
    print(f"  3. O deployment '{args.deployment_geracao}' classificou a pergunta e propôs a resposta.")
    print(f"  4. O programa conferiu o tipo e as evidências ({len(decisao.evidencias)} citação(ões) literais) "
          "e escolheu o texto mostrado.")
    mostrar_uso(resultado)
    print("\nLembrete: a resposta explica regras do produto; ela não confirma as coberturas de uma contratação.")
    return lab_comum.CODIGO_OK


def executar(args: argparse.Namespace) -> int:
    pergunta = args.pergunta.strip()
    if not pergunta:
        raise ErroLab("Informe uma pergunta não vazia em --pergunta.")
    if len(pergunta) > lab_geracao.LIMITE_DA_PERGUNTA:
        raise ErroLab(f"A pergunta tem mais de {lab_geracao.LIMITE_DA_PERGUNTA} caracteres. Resuma-a.")
    print(f"Pergunta: {pergunta}")
    args.credencial = lab_identidade.resolver_credencial(args)
    if args.credencial is not None:
        print(f"Identidade: {lab_identidade.descrever_identidade(args)}")
    print(f"Recuperação: modo {args.modo} · {args.k} trecho(s) · serviço de busca '{args.busca}', índice '{args.indice}'")
    recuperacao = lab_geracao.criar_recuperador(args).recuperar(pergunta, args.modo, args.k)
    mostrar_trechos(recuperacao.resultados)
    completa = args.politica == "completa"
    pedido = lab_geracao.montar_pedido(
        pergunta, recuperacao.resultados, lab_politica.INSTRUCOES_COMPLETAS if completa else lab_geracao.INSTRUCOES)
    if args.mostrar_prompt or args.sem_geracao:
        mostrar_pedido(pedido)
    if args.sem_geracao:
        print("\nSimulação: o modelo de geração não foi chamado. Repita sem --sem-geracao para obter a resposta.")
        return lab_comum.CODIGO_OK
    if not recuperacao.resultados:
        print("\nNenhum trecho foi recuperado, por isso o modelo de geração não foi chamado.")
        return lab_comum.CODIGO_OK
    sufixo = " · política completa" if completa else ""
    print(f"Geração: deployment '{args.deployment_geracao}' · esforço de raciocínio {args.esforco}{sufixo}")
    cliente = lab_geracao.criar_cliente_geracao(
        args.modelos, args.deployment_geracao, args.esforco, args.tenant_id, args.credencial)
    resultado = cliente.gerar(pedido, lab_politica.CONTRATO_COMPLETO if completa else lab_geracao.CONTRATO_BASICO)
    if completa:
        return apresentar_completa(args, pergunta, recuperacao, resultado)
    return apresentar_basica(args, recuperacao, resultado)


def principal(argv: list[str] | None = None) -> int:
    lab_comum.configurar_saida()
    parser = lab_comum.criar_parser(__doc__, armazenamento=False, inventario=False)
    lab_indexacao.adicionar_argumentos_indice(parser)
    lab_geracao.adicionar_argumentos_geracao(parser)
    parser.add_argument("--pergunta", required=True, help="A pergunta, entre aspas.")
    parser.add_argument("--politica", choices=POLITICAS, default=POLITICA_PADRAO,
                        help="basica (padrão): confere as fontes citadas; completa: também classifica a pergunta, "
                             "exige citações literais e recusa o que os documentos não autorizam.")
    parser.add_argument("--mostrar-prompt", action="store_true",
                        help="Mostra as instruções e a entrada enviadas ao modelo de geração.")
    parser.add_argument("--sem-geracao", action="store_true",
                        help="Recupera os trechos e mostra o pedido, mas não chama o modelo de geração.")
    lab_identidade.adicionar_argumentos_identidade(parser)
    args = parser.parse_args(argv)
    return lab_comum.executar_com_tratamento(executar, args, tradutor=lab_identidade.traduzir_erro_identidade)


if __name__ == "__main__":
    sys.exit(principal())
