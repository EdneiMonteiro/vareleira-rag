"""Envia ao Azure Blob Storage os documentos sintéticos do inventário (L100, Desafio 01).

Por padrão, apenas SIMULA: valida o inventário, compara com o contêiner e mostra o plano.
Nada é enviado sem --executar. Um blob existente com conteúdo diferente nunca é sobrescrito
em silêncio: o script para, a menos que você peça --substituir-divergentes.
Usa a identidade do Azure CLI (az login); não usa chaves de conta.

Exemplo:
    python scripts\\carregar_documentos.py --conta <nome-da-conta>
    python scripts\\carregar_documentos.py --conta <nome-da-conta> --executar
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from typing import Any

import lab_comum
from lab_comum import Documento, ErroLab

CRIAR = "criar"
IGUAL = "igual"
DIVERGENTE = "divergente"


@dataclass(frozen=True)
class Acao:
    documento: Documento
    estado: str
    etag: str | None = None


def planejar(container: Any, inventario: lab_comum.Inventario) -> list[Acao]:
    """Compara cada documento do inventário com o contêiner. Somente leitura."""
    from azure.core.exceptions import ResourceNotFoundError

    acoes: list[Acao] = []
    for documento in inventario.documentos:
        cliente = container.get_blob_client(documento.blob)
        try:
            propriedades = cliente.get_blob_properties()
        except ResourceNotFoundError as erro:
            if lab_comum.codigo_do_erro(erro) == "ContainerNotFound":
                raise
            acoes.append(Acao(documento, CRIAR))
            continue
        # Só baixa quando o tamanho coincide: evita ler um blob inesperadamente grande.
        if propriedades.size != documento.tamanho_bytes:
            acoes.append(Acao(documento, DIVERGENTE, propriedades.etag))
            continue
        baixado = cliente.download_blob()
        igual = lab_comum.calcular_sha256(baixado.readall()) == documento.sha256
        acoes.append(Acao(documento, IGUAL if igual else DIVERGENTE, baixado.properties.etag))
    return acoes


def enviar(container: Any, acoes: list[Acao]) -> dict[str, int]:
    """Envia o que o plano indica. Criação só se o blob não existir; troca só com o ETag planejado."""
    from azure.core import MatchConditions
    from azure.core.exceptions import ResourceExistsError, ResourceModifiedError
    from azure.storage.blob import ContentSettings

    resultado = {"criados": 0, "substituidos": 0, "iguais": 0}
    for acao in acoes:
        documento = acao.documento
        if acao.estado == IGUAL:
            resultado["iguais"] += 1
            print(f"[IGUAL]  {documento.id}: já existe com o mesmo conteúdo; nada a fazer.")
            continue
        conteudo = lab_comum.ler_conteudo(documento)
        if lab_comum.calcular_sha256(conteudo) != documento.sha256:
            raise ErroLab(f"{documento.id}: o arquivo mudou durante a execução. Rode a simulação de novo.")
        opcoes: dict[str, Any] = {
            "metadata": documento.metadados_blob,
            "content_settings": ContentSettings(content_type=documento.tipo_conteudo, content_language="pt-BR"),
        }
        if acao.estado == DIVERGENTE:
            opcoes.update(overwrite=True, etag=acao.etag, match_condition=MatchConditions.IfNotModified)
        else:
            opcoes["overwrite"] = False
        try:
            container.get_blob_client(documento.blob).upload_blob(conteudo, **opcoes)
        except (ResourceExistsError, ResourceModifiedError):
            raise ErroLab(
                f"{documento.id}: o blob mudou depois da simulação. Nada foi sobrescrito; rode a simulação de novo.",
                lab_comum.CODIGO_DIVERGENCIA,
            ) from None
        if acao.estado == DIVERGENTE:
            resultado["substituidos"] += 1
            print(f"[TROCADO] {documento.id}: conteúdo anterior substituído (recuperável pela exclusão reversível).")
        else:
            resultado["criados"] += 1
            print(f"[CRIADO] {documento.id}: enviado como {documento.blob}.")
    return resultado


def mostrar_plano(acoes: list[Acao]) -> None:
    print("Plano:")
    for acao in acoes:
        nota = "  <- só será trocado com --substituir-divergentes" if acao.estado == DIVERGENTE else ""
        print(f"  [{acao.estado:<10}] {acao.documento.id:<14} {acao.documento.blob}{nota}")


def executar(args: argparse.Namespace) -> int:
    inventario = lab_comum.carregar_e_validar(args.inventario)
    modo = "EXECUÇÃO" if args.executar else "SIMULAÇÃO (nenhuma alteração será feita)"
    print(f"Modo: {modo}")
    print(f"Destino: conta '{args.conta}', contêiner '{args.container}'")
    print(f"Inventário: {len(inventario.documentos)} documento(s) conferidos por tamanho e hash.")
    aviso = lab_comum.aviso_de_revisao(inventario)
    if aviso:
        print(f"[AVISO] {aviso}")

    container = lab_comum.criar_container(args.conta, args.container, args.tenant_id)
    acoes = planejar(container, inventario)
    mostrar_plano(acoes)

    if any(acao.estado == DIVERGENTE for acao in acoes) and not args.substituir_divergentes:
        print("[PARADA] Há blob(s) com conteúdo diferente do inventário. Nada foi alterado.")
        print("         Investigue a diferença. Para substituir de propósito: --executar --substituir-divergentes.")
        return lab_comum.CODIGO_DIVERGENCIA
    if not args.executar:
        print("Simulação concluída. Para enviar, repita o comando com --executar.")
        return lab_comum.CODIGO_OK

    resultado = enviar(container, acoes)
    print(f"Concluído: {resultado['criados']} criado(s), {resultado['substituidos']} trocado(s), "
          f"{resultado['iguais']} já igual(is).")
    print(f"Próximo passo: python scripts\\verificar_documentos.py --conta {args.conta}")
    return lab_comum.CODIGO_OK


def principal(argv: list[str] | None = None) -> int:
    lab_comum.configurar_saida()
    parser = lab_comum.criar_parser(__doc__)
    parser.add_argument("--executar", action="store_true",
                        help="Envia os documentos. Sem esta opção, o script só simula.")
    parser.add_argument("--substituir-divergentes", action="store_true",
                        help="Permite trocar blobs existentes com conteúdo diferente do inventário.")
    args = parser.parse_args(argv)
    return lab_comum.executar_com_tratamento(executar, args)


if __name__ == "__main__":
    sys.exit(principal())
