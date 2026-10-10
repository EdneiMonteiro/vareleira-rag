"""Indexa no Azure AI Search os documentos sintéticos do Blob Storage (L100, Desafio 02).

Percorre o caminho Blob -> leitura -> divisão em trechos -> embeddings -> índice. Por padrão, apenas SIMULA:
lê o contêiner e o índice, calcula os trechos e mostra o plano. Nada é criado, calculado nem gravado sem
--executar. Um trecho já indexado com conteúdo diferente nunca é trocado em silêncio, e trechos que o
documento não produz mais nunca são removidos em silêncio. Usa a identidade do Azure CLI (az login);
não usa chaves.

Exemplo:
    python scripts\\indexar_documentos.py --conta <conta> --busca <busca> --modelos <modelos>
    python scripts\\indexar_documentos.py --conta <conta> --busca <busca> --modelos <modelos> --executar
"""

from __future__ import annotations

import argparse
import sys
from typing import Any, Iterator, Sequence

import lab_comum
import lab_indexacao
from lab_comum import Documento, ErroLab
from lab_indexacao import CRIAR, DIVERGENTE, IGUAL, Plano

MODELO_DESCONHECIDO = "desconhecido"
LINHAS_DE_PROBLEMAS = 8


def ler_documentos_do_blob(container: Any, inventario: lab_comum.Inventario) -> list[tuple[Documento, str]]:
    """Lê do contêiner o texto de cada documento do inventário e confere tamanho e hash. Somente leitura."""
    from azure.core.exceptions import ResourceNotFoundError

    lidos: list[tuple[Documento, str]] = []
    problemas: list[str] = []
    for documento in inventario.documentos:
        cliente = container.get_blob_client(documento.blob)
        try:
            propriedades = cliente.get_blob_properties()
        except ResourceNotFoundError as erro:
            if lab_comum.codigo_do_erro(erro) == "ContainerNotFound":
                raise
            problemas.append(f"{documento.id}: não está no contêiner ({documento.blob})")
            continue
        # Só baixa quando o tamanho coincide: evita ler um blob inesperadamente grande.
        if propriedades.size != documento.tamanho_bytes:
            problemas.append(f"{documento.id}: o blob tem tamanho diferente do inventário")
            continue
        dados = cliente.download_blob().readall()
        if lab_comum.calcular_sha256(dados) != documento.sha256:
            problemas.append(f"{documento.id}: o conteúdo do blob é diferente do inventário (o hash não confere)")
            continue
        lidos.append((documento, dados.decode("utf-8")))
    if problemas:
        raise ErroLab(
            "A base documental no contêiner não confere com o inventário:\n  - " + "\n  - ".join(problemas)
            + "\nCorrija pelo Desafio 01 (carregar_documentos.py e verificar_documentos.py) antes de indexar.",
            lab_comum.CODIGO_DIVERGENCIA,
        )
    return lidos


def lotes(itens: Sequence[Any], tamanho: int) -> Iterator[Sequence[Any]]:
    for inicio in range(0, len(itens), tamanho):
        yield itens[inicio:inicio + tamanho]


def mostrar_plano(plano: Plano, args: argparse.Namespace, estado_do_indice: str, ordem_dos_documentos: list[str]) -> None:
    print("Plano:")
    print(f"  [{estado_do_indice:<10}] índice '{args.indice}': definição com busca vetorial "
          f"(HNSW, cosseno, {args.dimensoes} dimensões)")
    for documento_id in ordem_dos_documentos:
        acoes = [acao for acao in plano.acoes if acao.trecho.documento.id == documento_id]
        contagens = ", ".join(f"{sum(1 for a in acoes if a.estado == estado)} {rotulo}"
                              for estado, rotulo in ((CRIAR, "a criar"), (IGUAL, "iguais"), (DIVERGENTE, "divergentes")))
        print(f"  {documento_id:<14} {len(acoes):>3} trecho(s): {contagens}")
    divergentes = [acao for acao in plano.acoes if acao.estado == DIVERGENTE]
    dica_divergente = ("será trocado (--substituir-divergentes)" if args.substituir_divergentes
                       else "só será trocado com --substituir-divergentes")
    dica_orfao = ("não vem mais dos documentos; será removido (--remover-orfaos)" if args.remover_orfaos
                  else "não vem mais dos documentos; só será removido com --remover-orfaos")
    for acao in divergentes[:LINHAS_DE_PROBLEMAS]:
        print(f"  [divergente ] {acao.trecho.id}  {acao.trecho.secao}  <- {dica_divergente}")
    if len(divergentes) > LINHAS_DE_PROBLEMAS:
        print(f"  [divergente ] ... e mais {len(divergentes) - LINHAS_DE_PROBLEMAS} trecho(s)")
    for chave in plano.orfaos[:LINHAS_DE_PROBLEMAS]:
        print(f"  [órfão      ] {chave}  <- {dica_orfao}")
    if len(plano.orfaos) > LINHAS_DE_PROBLEMAS:
        print(f"  [órfão      ] ... e mais {len(plano.orfaos) - LINHAS_DE_PROBLEMAS} trecho(s)")
    print(f"  Total: {len(plano.acoes)} trecho(s): {plano.contar(CRIAR)} a criar, {plano.contar(IGUAL)} iguais, "
          f"{plano.contar(DIVERGENTE)} divergentes; {len(plano.orfaos)} órfão(s).")
    a_gravar = plano.a_gravar
    if a_gravar:
        caracteres = sum(len(acao.trecho.texto_para_embedding) for acao in a_gravar)
        print(f"  Embeddings a gerar: {len(a_gravar)} trecho(s), cerca de {lab_indexacao.estimar_tokens(caracteres)} tokens "
              "(estimativa; o serviço informa o uso real).")
    else:
        print("  Embeddings a gerar: nenhum.")


def executar(args: argparse.Namespace) -> int:
    inventario = lab_comum.carregar_inventario(args.inventario)
    modo = "EXECUÇÃO" if args.executar else "SIMULAÇÃO (nenhuma alteração será feita)"
    print(f"Modo: {modo}")
    print(f"Origem: conta '{args.conta}', contêiner '{args.container}'")
    print(f"Destino: serviço de busca '{args.busca}', índice '{args.indice}'")
    print(f"Embeddings: deployment '{args.deployment}' do recurso '{args.modelos}' ({args.dimensoes} dimensões)")
    print(f"Inventário: {len(inventario.documentos)} documento(s).")
    aviso = lab_comum.aviso_de_revisao(inventario)
    if aviso:
        print(f"[AVISO] {aviso}")

    container = lab_comum.criar_container(args.conta, args.container, args.tenant_id)
    documentos = ler_documentos_do_blob(container, inventario)
    print(f"Contêiner: {len(documentos)} documento(s) conferidos por tamanho e hash.")
    trechos = lab_indexacao.dividir_documentos(documentos, args.tamanho_maximo)
    print(f"Divisão: {len(trechos)} trecho(s) de até {args.tamanho_maximo} caracteres.")

    indice = lab_indexacao.abrir_indice(args.busca, args.indice, args.tenant_id)
    definicao = lab_indexacao.definicao_do_indice(args.indice, args.dimensoes)
    atual = indice.definicao_atual()
    recriar = args.recriar_indice and atual is not None
    diferencas = [] if atual is None else lab_indexacao.diferencas_do_esquema(definicao, atual)
    if atual is None:
        estado_do_indice = "criar"
    elif recriar:
        estado_do_indice = "recriar"
    elif diferencas:
        estado_do_indice = "incompatível"
    else:
        estado_do_indice = "igual"
    existentes: dict[str, str | None] = {}
    if estado_do_indice == "incompatível":
        print("Plano:")
        print(f"  [incompatível] o índice '{args.indice}' já existe com outra definição.")
        print("[PARADA] Nada foi alterado. Diferenças encontradas:")
        for diferenca in diferencas[:8]:
            print(f"         - {diferenca}")
        print("         Use outro nome (--indice) ou apague este índice de propósito com --executar --recriar-indice.")
        return lab_comum.CODIGO_DIVERGENCIA
    if estado_do_indice == "igual":
        existentes = {chave: valores["impressao"] for chave, valores in indice.trechos_gravados().items()}

    especificacao = lab_indexacao.EspecificacaoEmbedding(args.deployment, args.dimensoes)
    plano = lab_indexacao.planejar(trechos, existentes, especificacao)
    mostrar_plano(plano, args, estado_do_indice, [documento.id for documento, _ in documentos])

    if plano.contar(DIVERGENTE) and not args.substituir_divergentes:
        print("[PARADA] Há trecho(s) indexado(s) com conteúdo diferente do calculado. Nada foi alterado.")
        print("         Investigue a diferença. Para trocar de propósito: --executar --substituir-divergentes.")
        return lab_comum.CODIGO_DIVERGENCIA
    if plano.orfaos and not args.remover_orfaos:
        print("[PARADA] Há trecho(s) no índice que os documentos não produzem mais. Nada foi alterado.")
        print("         Investigue a diferença. Para removê-los de propósito: --executar --remover-orfaos.")
        return lab_comum.CODIGO_DIVERGENCIA
    if not args.executar:
        print("Simulação concluída. Para indexar, repita o comando com --executar.")
        return lab_comum.CODIGO_OK

    resumo = {"criados": 0, "trocados": 0, "iguais": plano.contar(IGUAL), "removidos": 0}
    a_gravar = plano.a_gravar
    modelo = MODELO_DESCONHECIDO
    vetores: list[list[float]] = []
    if a_gravar:
        # Primeiro calcula tudo: se o serviço de modelos falhar, nada foi criado nem gravado.
        cliente = lab_indexacao.criar_cliente_embeddings(args.modelos, args.deployment, args.dimensoes, args.tenant_id)
        resultado = cliente.gerar([acao.trecho.texto_para_embedding for acao in a_gravar])
        vetores, modelo = resultado.vetores, resultado.modelo or MODELO_DESCONHECIDO
        print(f"[EMBEDDINGS] {len(vetores)} vetor(es) de {args.dimensoes} dimensões gerados com o modelo '{modelo}' "
              f"({resultado.tokens} tokens usados).")
    if recriar:
        indice.apagar()
        print(f"[APAGADO] O índice '{args.indice}' anterior foi apagado de propósito (--recriar-indice).")
    if atual is None or recriar:
        indice.criar(definicao)
        print(f"[CRIADO] Índice '{args.indice}'.")

    registros = [
        {**acao.trecho.campos(), "modelo_embeddings": modelo, "impressao": acao.impressao, "vetor": vetor}
        for acao, vetor in zip(a_gravar, vetores)
    ]
    for lote in lotes(registros, lab_indexacao.LOTE_INDICE):
        indice.gravar(list(lote))
    resumo["criados"] = sum(1 for acao in a_gravar if acao.estado == CRIAR)
    resumo["trocados"] = len(a_gravar) - resumo["criados"]
    if registros:
        print(f"[INDEXADO] {resumo['criados']} criado(s), {resumo['trocados']} trocado(s).")
    if plano.orfaos:
        indice.remover(list(plano.orfaos))
        resumo["removidos"] = len(plano.orfaos)
        print(f"[REMOVIDO] {len(plano.orfaos)} trecho(s) órfão(s) removido(s) de propósito (--remover-orfaos).")
    if not registros and not plano.orfaos:
        print("[IGUAL] O índice já está como o plano pede; nada a fazer.")
    print(f"Concluído: {resumo['criados']} criado(s), {resumo['trocados']} trocado(s), {resumo['iguais']} já igual(is), "
          f"{resumo['removidos']} removido(s).")
    print("O índice pode levar alguns segundos para refletir as gravações.")
    print(f"Próximo passo: python scripts\\verificar_indice.py --busca {args.busca} --modelos {args.modelos}")
    return lab_comum.CODIGO_OK


def principal(argv: list[str] | None = None) -> int:
    lab_comum.configurar_saida()
    parser = lab_comum.criar_parser(__doc__)
    lab_indexacao.adicionar_argumentos_indice(parser)
    lab_indexacao.adicionar_argumento_tamanho(parser)
    parser.add_argument("--executar", action="store_true",
                        help="Calcula os embeddings e grava no índice. Sem esta opção, o script só simula.")
    parser.add_argument("--substituir-divergentes", action="store_true",
                        help="Permite trocar trechos indexados com conteúdo diferente do calculado.")
    parser.add_argument("--remover-orfaos", action="store_true",
                        help="Permite remover do índice trechos que os documentos não produzem mais.")
    parser.add_argument("--recriar-indice", action="store_true",
                        help="Apaga o índice existente e o cria de novo (todos os trechos são calculados outra vez).")
    args = parser.parse_args(argv)
    return lab_comum.executar_com_tratamento(executar, args, tradutor=lab_indexacao.traduzir_erro_indexacao)


if __name__ == "__main__":
    sys.exit(principal())
