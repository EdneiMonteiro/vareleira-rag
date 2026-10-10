"""Guarda um segredo no Azure Key Vault sem mostrá-lo (L100, Desafio 07).

O valor chega pela entrada padrão (um pipe do PowerShell) ou por uma variável de ambiente. Ele nunca é impresso, gravado em
arquivo nem passado como argumento de comando, que ficaria no histórico e na lista de processos. Cada execução grava uma nova
versão do segredo, com data de validade. Usa a sua sessão do Azure CLI (az login); exige o papel 'Key Vault Secrets Officer'
no cofre.

Exemplos:
    $segredo | python scripts\\guardar_segredo.py --cofre <cofre>
    python scripts\\guardar_segredo.py --cofre <cofre> --origem variavel
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Mapping, TextIO

import lab_comum
import lab_identidade
from lab_comum import ErroLab

ORIGENS = ("entrada", "variavel")
VARIAVEL_PADRAO = "VARELEIRA_SEGREDO"


def ler_valor(args: argparse.Namespace, entrada: TextIO | None = None, ambiente: Mapping[str, str] | None = None) -> str:
    """O valor do segredo, da entrada padrão ou da variável de ambiente. Nunca vem de um argumento de comando."""
    if args.origem == "variavel":
        valor = (os.environ if ambiente is None else ambiente).get(args.variavel, "")
        if not valor.strip():
            raise ErroLab(f"A variável de ambiente {args.variavel} está vazia ou não existe nesta sessão do terminal.")
        return valor.strip()
    entrada = entrada or sys.stdin
    if entrada.isatty():
        raise ErroLab("Envie o segredo pela entrada padrão, por exemplo: $segredo | python scripts\\guardar_segredo.py --cofre "
                      "<cofre>. Digitá-lo no terminal o deixaria visível e no histórico da sessão.")
    return entrada.read().strip()


def executar(args: argparse.Namespace) -> int:
    valor = ler_valor(args)
    versao, expira = lab_identidade.guardar_segredo(args.cofre, args.nome_do_segredo, valor, args.tenant_id, args.validade_dias)
    print(f"Segredo '{args.nome_do_segredo}' gravado no cofre '{args.cofre}' (versão {versao}), válido até {expira:%Y-%m-%d}.")
    print("O valor não foi mostrado nem gravado em arquivo. Apague-o da sessão do terminal quando terminar "
          "(por exemplo, Remove-Variable segredo).")
    return lab_comum.CODIGO_OK


def principal(argv: list[str] | None = None) -> int:
    lab_comum.configurar_saida()
    parser = lab_comum.criar_parser(__doc__, armazenamento=False, inventario=False)
    parser.add_argument("--cofre", required=True, type=lab_identidade.validar_cofre,
                        help="Nome do Azure Key Vault (saída nomeCofre da implantação).")
    parser.add_argument("--nome-do-segredo", default=lab_identidade.SEGREDO_PADRAO, type=lab_identidade.validar_nome_do_segredo,
                        help=f"Nome do segredo no cofre (padrão: {lab_identidade.SEGREDO_PADRAO}).")
    parser.add_argument("--origem", choices=ORIGENS, default="entrada",
                        help="entrada (padrão): lê o valor da entrada padrão (pipe); variavel: lê de uma variável de ambiente.")
    parser.add_argument("--variavel", default=VARIAVEL_PADRAO,
                        help=f"Nome da variável de ambiente usada com --origem variavel (padrão: {VARIAVEL_PADRAO}).")
    parser.add_argument("--validade-dias", default=lab_identidade.VALIDADE_PADRAO_DIAS, type=lab_identidade.validar_validade,
                        help=f"Dias até a data de validade do segredo, de 1 a {lab_identidade.VALIDADE_MAXIMA_DIAS} "
                             f"(padrão: {lab_identidade.VALIDADE_PADRAO_DIAS}).")
    args = parser.parse_args(argv)
    return lab_comum.executar_com_tratamento(executar, args, tradutor=lab_identidade.traduzir_erro_identidade)


if __name__ == "__main__":
    sys.exit(principal())
