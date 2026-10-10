"""Mostra como os documentos sintéticos são divididos em trechos (L100, Desafio 02). Não usa o Azure.

Lê os arquivos locais, confere o inventário (tamanho e hash) e lista cada trecho que seria enviado ao
índice: ordem, tamanho, seção e cláusulas. Nada é enviado, gravado ou calculado em serviço algum:
não exige login, assinatura nem permissões.

Exemplos:
    python scripts\\visualizar_trechos.py
    python scripts\\visualizar_trechos.py --documento VLAR-CG-1.0 --completo
    python scripts\\visualizar_trechos.py --tamanho-maximo 600
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import lab_comum
import lab_indexacao


def _encurtar(texto: str, largura: int) -> str:
    return texto if len(texto) <= largura else texto[: largura - 1] + "…"


def executar(args: argparse.Namespace) -> int:
    inventario = lab_comum.carregar_e_validar(args.inventario)
    documentos = [documento for documento in inventario.documentos if args.documento in (None, documento.id)]
    if not documentos:
        ids = ", ".join(documento.id for documento in inventario.documentos)
        raise lab_comum.ErroLab(f"Documento '{args.documento}' não está no inventário. Use um destes: {ids}.")
    print(f"Divisão local, sem Azure: no máximo {args.tamanho_maximo} caracteres por trecho.")
    print(f"Inventário: {len(inventario.documentos)} documento(s) conferidos por tamanho e hash.")

    total = caracteres = para_o_modelo = 0
    for documento in documentos:
        texto = lab_comum.ler_conteudo(documento).decode("utf-8")
        trechos = lab_indexacao.dividir_documento(documento, texto, args.tamanho_maximo)
        print(f"\n{documento.id} — {documento.titulo}: {len(trechos)} trecho(s)")
        print(f"  {'ordem':>5}  {'caracteres':>10}  {'seção':<40}  cláusulas")
        for trecho in trechos:
            print(f"  {trecho.ordem:>5}  {len(trecho.conteudo):>10}  {_encurtar(trecho.secao, 40):<40}  {trecho.clausulas}".rstrip())
            if args.completo:
                for linha in trecho.conteudo.split("\n"):
                    print(f"         | {linha}".rstrip())
                print()
        total += len(trechos)
        caracteres += sum(len(trecho.conteudo) for trecho in trechos)
        para_o_modelo += sum(len(trecho.texto_para_embedding) for trecho in trechos)
    media = caracteres // total if total else 0
    tokens = lab_indexacao.estimar_tokens(para_o_modelo)
    print(f"\nResumo: {total} trecho(s) em {len(documentos)} documento(s), em média {media} caracteres. "
          f"Estimativa grosseira: {tokens} tokens para gerar os embeddings (o serviço informa o uso real).")
    print("Nenhum arquivo foi alterado e nada foi enviado ao Azure.")
    return lab_comum.CODIGO_OK


def principal(argv: list[str] | None = None) -> int:
    lab_comum.configurar_saida()
    parser = lab_comum.ParserLab(description=__doc__)
    parser.add_argument("--inventario", type=Path, default=lab_comum.INVENTARIO_PADRAO,
                        help="Caminho do inventário (padrão: dados/l100/inventario.json).")
    parser.add_argument("--documento", default=None, help="Mostra só este documento (por exemplo, VLAR-CG-1.0).")
    parser.add_argument("--completo", action="store_true", help="Mostra também o texto de cada trecho.")
    lab_indexacao.adicionar_argumento_tamanho(parser)
    parser.add_argument("--detalhes", action="store_true", help="Mostra o erro técnico, se houver.")
    args = parser.parse_args(argv)
    return lab_comum.executar_com_tratamento(executar, args)


if __name__ == "__main__":
    sys.exit(principal())
