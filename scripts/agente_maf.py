"""Responde a uma pergunta com um agente do Microsoft Agent Framework (L100, Desafio 05).

O agente recebe instruções e consulta os documentos por uma ferramenta de busca (--recuperacao ferramenta) ou
recebe os trechos que o programa buscou antes (--recuperacao obrigatoria). Nos dois casos, o programa confere o tipo
da pergunta e as citações com a política do Desafio 04 antes de mostrar a resposta, e mostra o rastro do agente:
as buscas que ele fez, os trechos que recebeu e os tokens usados. Não altera nada no Azure. Usa a identidade do
Azure CLI (az login); não usa chaves.

A resposta explica regras do produto: ela não confirma as coberturas de uma contratação específica.

Exemplos:
    python scripts\\agente_maf.py --busca <busca> --modelos <modelos> --pergunta "O seguro cobre danos elétricos e qual é a franquia?"
    python scripts\\agente_maf.py --busca <busca> --modelos <modelos> --pergunta "Qual é a franquia?" --recuperacao obrigatoria
    python scripts\\agente_maf.py --busca <busca> --modelos <modelos> --pergunta "Qual é a franquia?" --mostrar-agente
"""

from __future__ import annotations

import argparse
import json
import sys
import textwrap

import lab_agente
import lab_comum
import lab_geracao
import lab_indexacao
import lab_politica
import perguntar
from lab_comum import ErroLab

LARGURA_DA_CONSULTA = 90


def mostrar_agente(args: argparse.Namespace) -> None:
    """Mostra o que o agente recebe (instruções e ferramenta) sem chamar o Azure."""
    por_ferramenta = args.recuperacao == "ferramenta"
    print("\n--- Instruções do agente ---")
    print((lab_agente.instrucoes_do_agente(args.maximo_de_buscas) if por_ferramenta
           else lab_politica.INSTRUCOES_COMPLETAS).rstrip())
    if por_ferramenta:
        ferramenta = lab_agente.criar_ferramenta_maf(
            lab_agente.FerramentaBusca(lab_geracao.Recuperador(None, None), args.modo, args.k, args.maximo_de_buscas))
        print("\n--- Ferramenta que o agente pode chamar ---")
        print(f"Nome: {ferramenta.name}")
        print(f"Descrição: {ferramenta.description}")
        print("Parâmetros (esquema JSON que o modelo recebe):")
        print(json.dumps(ferramenta.parameters(), ensure_ascii=False, indent=2))
        limites = lab_agente.configuracao_de_limites(args.maximo_de_buscas)
        print("\n--- Limites ---")
        print(f"Chamadas da ferramenta: até {limites['max_function_calls']} · idas ao modelo: até {limites['max_iterations']} "
              f"· tempo do laço: {limites['max_duration_seconds']:.0f} s · tempo total: {lab_agente.TEMPO_MAXIMO:.0f} s")
        print(f"A ferramenta fixa o modo ({args.modo}) e a quantidade de trechos ({args.k}); o modelo escolhe só o texto da consulta.")
    else:
        print("\nSem ferramentas: o programa busca os trechos antes e os entrega junto da pergunta.")
    print("--- Fim da configuração ---")


def mostrar_rastro(args: argparse.Namespace, resultado: lab_agente.ResultadoAgente, conferidas: int | None) -> None:
    """O caminho percorrido: quem buscou, o que foi buscado e o que o programa conferiu."""
    print("\nComo esta resposta foi produzida:")
    if args.recuperacao == "ferramenta":
        print("  1. O agente recebeu a pergunta e as instruções, sem trechos.")
        if not resultado.buscas:
            print("  2. O agente não chamou a ferramenta: respondeu sem buscar.")
        else:
            print(f"  2. O agente chamou a ferramenta {lab_agente.NOME_DA_FERRAMENTA} {len(resultado.buscas)} vez(es):")
            for numero, busca in enumerate(resultado.buscas, start=1):
                consulta = textwrap.shorten(busca.consulta, width=LARGURA_DA_CONSULTA, placeholder="…")
                destino = {
                    lab_agente.BUSCA_FEITA: f"{len(busca.ids)} trecho(s): {', '.join(busca.ids) or '-'}",
                    lab_agente.BUSCA_INVALIDA: "consulta inválida, recusada pela ferramenta",
                    lab_agente.BUSCA_RECUSADA: "recusada pela ferramenta: limite de buscas",
                    lab_agente.BUSCA_COM_ERRO: "a busca falhou",
                }[busca.situacao]
                print(f"       busca {numero}: \"{consulta}\" → {destino}")
    else:
        ids = ", ".join(str(item["id"]) for item in resultado.trechos)
        print(f"  1. O programa buscou antes ('{args.modo}'): {len(resultado.trechos)} trecho(s): {ids}.")
        print("  2. O agente recebeu os trechos e a pergunta, sem ferramentas.")
    if conferidas is not None:
        print(f"  3. O programa conferiu o tipo e as evidências ({conferidas} citação(ões) literais) e escolheu o texto mostrado.")
    print(f"  Uso (todas as idas ao modelo): {resultado.tokens_entrada} tokens de entrada e {resultado.tokens_saida} de saída "
          f"({resultado.tokens_raciocinio} de raciocínio); busca: {resultado.tokens_embeddings} tokens de embeddings.")


def apresentar(args: argparse.Namespace, pergunta: str, resultado: lab_agente.ResultadoAgente) -> int:
    por_ferramenta = args.recuperacao == "ferramenta"
    decisao = lab_agente.decidir(resultado.saida, resultado.trechos, pergunta, resultado.buscas_feitas, por_ferramenta)
    if por_ferramenta and resultado.trechos:
        print()
        perguntar.mostrar_trechos(resultado.trechos)
    if decisao.situacao == lab_politica.DESCARTADA:
        print("\n[FALHA] A resposta do agente foi descartada porque não passou na verificação do programa:")
        for problema in decisao.problemas:
            print(f"  - {problema}")
        print("Nenhuma resposta foi apresentada. Repita o comando; se persistir, use --mostrar-agente para examinar "
              "as instruções e a ferramenta.")
        mostrar_rastro(args, resultado, None)
        return lab_comum.CODIGO_DIVERGENCIA
    perguntar.mostrar_decisao(decisao, resultado.trechos)
    mostrar_rastro(args, resultado, len(decisao.evidencias))
    print("\nLembrete: a resposta explica regras do produto; ela não confirma as coberturas de uma contratação.")
    return lab_comum.CODIGO_OK


def executar(args: argparse.Namespace) -> int:
    pergunta = args.pergunta.strip()
    if not pergunta:
        raise ErroLab("Informe uma pergunta não vazia em --pergunta.")
    if len(pergunta) > lab_geracao.LIMITE_DA_PERGUNTA:
        raise ErroLab(f"A pergunta tem mais de {lab_geracao.LIMITE_DA_PERGUNTA} caracteres. Resuma-a.")
    print(f"Pergunta: {pergunta}")
    if args.mostrar_agente:
        mostrar_agente(args)
        return lab_comum.CODIGO_OK
    por_ferramenta = args.recuperacao == "ferramenta"
    print(f"Agente: deployment '{args.deployment_geracao}' · esforço de raciocínio {args.esforco} · "
          f"recuperação {'por ferramenta' if por_ferramenta else 'obrigatória'}")
    destino = f"modo {args.modo} · {args.k} trecho(s) por busca · serviço de busca '{args.busca}', índice '{args.indice}'"
    recuperador = lab_geracao.criar_recuperador(args)
    if por_ferramenta:
        print(f"Busca: até {args.maximo_de_buscas} chamada(s) da ferramenta · {destino}")
        resultado = lab_agente.consultar_com_ferramenta(args, pergunta, recuperador)
    else:
        print(f"Busca: feita pelo programa antes do agente · {destino}")
        recuperacao = recuperador.recuperar(pergunta, args.modo, args.k)
        perguntar.mostrar_trechos(recuperacao.resultados)
        if not recuperacao.resultados:
            print("\nNenhum trecho foi recuperado, por isso o agente não foi chamado.")
            return lab_comum.CODIGO_OK
        resultado = lab_agente.consultar_com_trechos(args, pergunta, recuperacao)
    return apresentar(args, pergunta, resultado)


def principal(argv: list[str] | None = None) -> int:
    lab_comum.configurar_saida()
    parser = lab_comum.criar_parser(__doc__, armazenamento=False, inventario=False)
    lab_indexacao.adicionar_argumentos_indice(parser)
    lab_geracao.adicionar_argumentos_geracao(parser)
    lab_agente.adicionar_argumentos_agente(parser)
    parser.add_argument("--pergunta", required=True, help="A pergunta, entre aspas.")
    args = parser.parse_args(argv)
    return lab_comum.executar_com_tratamento(executar, args, tradutor=lab_indexacao.traduzir_erro_indexacao)


if __name__ == "__main__":
    sys.exit(principal())
