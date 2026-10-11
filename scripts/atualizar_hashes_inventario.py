"""Recalcula o tamanho e o SHA-256 dos documentos do inventário (para quem mantém os documentos).

Por padrão, apenas mostra o que mudaria. Use --gravar para atualizar o inventário e revise o
diff antes de publicar: mudar um documento muda o conteúdo que será enviado ao Azure.
Não acessa o Azure.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import lab_comum


def atualizar(caminho: Path, gravar: bool) -> int:
    inventario = lab_comum.carregar_inventario(caminho)
    bruto = json.loads(caminho.read_text(encoding="utf-8"))
    desatualizados = 0
    for documento, entrada in zip(inventario.documentos, bruto["documentos"]):
        if not documento.arquivo.is_file():
            raise lab_comum.ErroLab(f"{documento.id}: arquivo não encontrado ({documento.arquivo.name}).")
        dados = lab_comum.ler_conteudo(documento)
        try:
            dados.decode("utf-8")
        except UnicodeDecodeError:
            raise lab_comum.ErroLab(f"{documento.id}: o arquivo precisa estar codificado em UTF-8.") from None
        tamanho, sha256 = len(dados), lab_comum.calcular_sha256(dados)
        if (entrada["tamanho_bytes"], entrada["sha256"]) == (tamanho, sha256):
            print(f"[OK] {documento.id}: sem mudanças ({tamanho} bytes).")
            continue
        desatualizados += 1
        print(f"[MUDOU] {documento.id}: {entrada['tamanho_bytes']} -> {tamanho} bytes; hash {sha256[:12]}...")
        entrada["tamanho_bytes"], entrada["sha256"] = tamanho, sha256
    if not desatualizados:
        print("Inventário já está atualizado.")
        return lab_comum.CODIGO_OK
    if not gravar:
        print(f"{desatualizados} documento(s) desatualizado(s) no inventário. Use --gravar para atualizar.")
        return lab_comum.CODIGO_DIVERGENCIA
    texto = json.dumps(bruto, indent=2, ensure_ascii=False) + "\n"
    caminho.write_text(texto, encoding="utf-8", newline="\n")
    print(f"Inventário atualizado: {desatualizados} documento(s). Revise o diff antes de publicar.")
    return lab_comum.CODIGO_OK


def principal(argv: list[str] | None = None) -> int:
    lab_comum.configurar_saida()
    parser = lab_comum.ParserLab(description=__doc__)
    parser.add_argument("--inventario", type=Path, default=lab_comum.INVENTARIO_PADRAO,
                        help="Caminho do inventário (padrão: dados/l100/inventario.json).")
    parser.add_argument("--gravar", action="store_true", help="Grava as mudanças no inventário.")
    args = parser.parse_args(argv)
    try:
        return atualizar(args.inventario, args.gravar)
    except lab_comum.ErroLab as erro:
        print(f"[ERRO] {erro}", file=sys.stderr)
        return erro.codigo


if __name__ == "__main__":
    sys.exit(principal())
