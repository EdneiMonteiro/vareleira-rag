"""Confere a base documental no Azure Blob Storage (L100, Desafio 01) sem alterar nada.

Verifica se os documentos do inventário estão no contêiner, sem blobs a mais; se conteúdo (SHA-256),
tipo e metadados conferem com o inventário; e se a leitura anônima é negada.
Usa a identidade do Azure CLI (az login); não usa chaves de conta.

Exemplo:
    python scripts\\verificar_documentos.py --conta <nome-da-conta>
"""

from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.request
from typing import Any, Callable
from urllib.parse import quote

import lab_comum
from lab_comum import Documento, Verificacao

# Respostas que indicam acesso negado: não autenticado, proibido, inexistente para anônimos
# ou acesso público desativado na conta (409). Uma resposta 2xx significaria leitura anônima.
STATUS_NEGADO = {401, 403, 404, 409}


def _verificar_documento(container: Any, documento: Documento, blob: Any) -> Verificacao:
    problemas: list[str] = []
    if blob.size != documento.tamanho_bytes:
        problemas.append(f"tamanho {blob.size} em vez de {documento.tamanho_bytes} bytes")
    else:
        conteudo = container.get_blob_client(documento.blob).download_blob().readall()
        if lab_comum.calcular_sha256(conteudo) != documento.sha256:
            problemas.append("hash diferente do inventário")
    tipo = getattr(getattr(blob, "content_settings", None), "content_type", None)
    if tipo != documento.tipo_conteudo:
        problemas.append(f"tipo de conteúdo {tipo!r} em vez de {documento.tipo_conteudo!r}")
    metadados = blob.metadata or {}
    divergentes = [chave for chave, esperado in documento.metadados_blob.items() if metadados.get(chave) != esperado]
    if divergentes:
        problemas.append(f"metadados ausentes ou diferentes: {', '.join(divergentes)}")
    if problemas:
        return Verificacao(documento.id, False, "; ".join(problemas))
    return Verificacao(documento.id, True, "conteúdo, tipo e metadados conferem com o inventário")


def verificar_conteudo(container: Any, inventario: lab_comum.Inventario) -> list[Verificacao]:
    esperados = {documento.blob: documento for documento in inventario.documentos}
    encontrados = {blob.name: blob for blob in container.list_blobs(include=["metadata"])}
    ausentes = sorted(set(esperados) - set(encontrados))
    extras = sorted(set(encontrados) - set(esperados))
    resultados = [Verificacao(
        "Quantidade e identificadores",
        not ausentes and not extras,
        f"{len(encontrados)} blob(s) no contêiner e {len(esperados)} no inventário",
    )]
    if ausentes:
        resultados.append(Verificacao("Documentos ausentes", False, ", ".join(ausentes)))
    if extras:
        resultados.append(Verificacao("Blobs fora do inventário", False, ", ".join(extras)))
    for nome, documento in esperados.items():
        if nome in encontrados:
            resultados.append(_verificar_documento(container, documento, encontrados[nome]))
    return resultados


def _status_anonimo(url: str) -> int:
    """Pede a URL sem nenhuma credencial e devolve só o código HTTP."""
    pedido = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(pedido, timeout=20) as resposta:
            return resposta.status
    except urllib.error.HTTPError as erro:
        return erro.code


def verificar_acesso_anonimo(
    conta: str, container: str, nomes_blobs: list[str],
    consultar: Callable[[str], int] | None = None,
) -> Verificacao:
    consultar = consultar or _status_anonimo
    base = f"https://{conta}.{lab_comum.SUFIXO_BLOB}/{container}"
    alvos = [("listagem do contêiner", f"{base}?restype=container&comp=list")]
    alvos += [(nome, f"{base}/{quote(nome)}") for nome in nomes_blobs]
    permitidos: list[str] = []
    inconclusivos: list[str] = []
    codigos: set[int] = set()
    for rotulo, url in alvos:
        try:
            status = consultar(url)
        except OSError as erro:
            inconclusivos.append(f"{rotulo} ({type(erro).__name__})")
            continue
        codigos.add(status)
        if 200 <= status < 300:
            permitidos.append(f"{rotulo} (HTTP {status})")
        elif status not in STATUS_NEGADO:
            inconclusivos.append(f"{rotulo} (HTTP {status})")
    if permitidos:
        return Verificacao("Leitura anônima negada", False, "LEITURA ANÔNIMA PERMITIDA em: " + "; ".join(permitidos))
    if inconclusivos:
        return Verificacao("Leitura anônima negada", False,
                           "não foi possível confirmar em: " + "; ".join(inconclusivos))
    resumo = ", ".join(f"HTTP {codigo}" for codigo in sorted(codigos))
    return Verificacao("Leitura anônima negada", True, f"{len(alvos)} endereço(s) testados sem credenciais; resposta: {resumo}")


def executar(args: argparse.Namespace) -> int:
    inventario = lab_comum.carregar_e_validar(args.inventario)
    print(f"Verificação somente leitura: conta '{args.conta}', contêiner '{args.container}'")
    print(f"Inventário: {len(inventario.documentos)} documento(s) conferidos por tamanho e hash.")
    container = lab_comum.criar_container(args.conta, args.container, args.tenant_id)
    resultados = verificar_conteudo(container, inventario)
    resultados.append(verificar_acesso_anonimo(
        args.conta, args.container, [documento.blob for documento in inventario.documentos]
    ))
    for resultado in resultados:
        print(f"[{'OK' if resultado.ok else 'FALHA':<5}] {resultado.nome}: {resultado.detalhe}")
    if all(resultado.ok for resultado in resultados):
        print("Verificação aprovada.")
        return lab_comum.CODIGO_OK
    print("Verificação reprovada. Corrija as falhas e repita. Nada foi alterado por este script.")
    return lab_comum.CODIGO_DIVERGENCIA


def principal(argv: list[str] | None = None) -> int:
    lab_comum.configurar_saida()
    parser = lab_comum.criar_parser(__doc__)
    args = parser.parse_args(argv)
    return lab_comum.executar_com_tratamento(executar, args)


if __name__ == "__main__":
    sys.exit(principal())
