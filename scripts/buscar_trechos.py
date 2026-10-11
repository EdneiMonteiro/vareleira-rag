"""Busca no índice os trechos mais parecidos com uma pergunta (L100, Desafio 02). Não gera resposta.

Calcula o embedding da pergunta (busca vetorial) ou usa as palavras dela (busca por texto), ou os dois
(híbrida), e mostra os trechos mais pertinentes com a pontuação e a fonte. Só lê o índice: não altera
nada. Os trechos são evidência bruta, não uma resposta: um trecho encontrado não confirma a cobertura
de uma contratação específica. Usa a identidade do Azure CLI (az login); não usa chaves.

Exemplo:
    python scripts\\buscar_trechos.py --busca <busca> --modelos <modelos> --pergunta "O seguro cobre danos elétricos?"
"""

from __future__ import annotations

import argparse
import re
import sys
from typing import Any

import lab_comum
import lab_indexacao
from lab_comum import ErroLab

LARGURA_DO_TRECHO = 240


def resumir(conteudo: str, limite: int = LARGURA_DO_TRECHO) -> str:
    """Primeiras palavras do trecho, em uma linha, sem a marcação de título."""
    plano = re.sub(r"\s+", " ", re.sub(r"^#{1,6}\s+", "", conteudo.strip()))
    return plano if len(plano) <= limite else plano[: limite - 1].rstrip() + "…"


def mostrar(resultados: list[dict[str, Any]]) -> None:
    if not resultados:
        print("Nenhum trecho encontrado.")
        return
    for posicao, item in enumerate(resultados, start=1):
        clausulas = f" (cláusulas {item['clausulas']})" if item.get("clausulas") else ""
        print(f"\n{posicao}. [pontuação {item.get('@search.score', 0):.3f}] {item.get('titulo_documento', '?')} · "
              f"{item.get('secao', '?')}{clausulas}")
        print(f"   fonte: {item.get('fonte', '?')} · versão {item.get('versao', '?')} · trecho {item.get('id', '?')}")
        print(f"   {resumir(str(item.get('conteudo', '')))}")


def executar(args: argparse.Namespace) -> int:
    pergunta = args.pergunta.strip()
    if not pergunta:
        raise ErroLab("Informe uma pergunta não vazia em --pergunta.")
    print(f"Pergunta: {pergunta}")
    print(f"Modo: {args.modo} · {args.k} resultado(s) · serviço de busca '{args.busca}', índice '{args.indice}'")
    print("Só são mostrados os trechos mais parecidos com a pergunta; nenhuma resposta é gerada.")
    vetor = None
    if args.modo != "texto":
        cliente = lab_indexacao.criar_cliente_embeddings(args.modelos, args.deployment, args.dimensoes, args.tenant_id)
        vetor = cliente.gerar([pergunta]).vetores[0]
    indice = lab_indexacao.abrir_indice(args.busca, args.indice, args.tenant_id)
    mostrar(indice.consultar(pergunta if args.modo != "vetorial" else None, vetor, args.k))
    print("\nLembrete: trechos recuperados explicam regras do produto; não confirmam as coberturas de uma contratação.")
    return lab_comum.CODIGO_OK


def principal(argv: list[str] | None = None) -> int:
    lab_comum.configurar_saida()
    parser = lab_comum.criar_parser(__doc__, armazenamento=False, inventario=False)
    lab_indexacao.adicionar_argumentos_indice(parser)
    parser.add_argument("--pergunta", required=True, help="A pergunta, entre aspas.")
    parser.add_argument("--modo", choices=lab_indexacao.MODOS_DE_BUSCA, default="vetorial",
                        help="vetorial (padrão), texto (palavras) ou hibrida (os dois).")
    parser.add_argument("--k", default=3, type=lab_indexacao.validar_k,
                        help="Quantos trechos mostrar (padrão: 3).")
    args = parser.parse_args(argv)
    return lab_comum.executar_com_tratamento(executar, args, tradutor=lab_indexacao.traduzir_erro_indexacao)


if __name__ == "__main__":
    sys.exit(principal())
