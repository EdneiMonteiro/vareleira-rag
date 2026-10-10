"""Confere o índice do Azure AI Search sem alterar nada (L100, Desafio 02).

Verifica se a definição do índice é a esperada; se os trechos nele correspondem exatamente aos que os
documentos do inventário produzem (sem faltas, sobras nem conteúdo diferente); se os vetores vêm do
mesmo modelo que o deployment usa hoje; se perguntas de exemplo recuperam o trecho esperado entre os
primeiros resultados; e se pedidos sem credencial são recusados. A conferência das perguntas calcula
embeddings (poucos tokens). Usa a identidade do Azure CLI (az login); não usa chaves.

Exemplo:
    python scripts\\verificar_indice.py --busca <busca> --modelos <modelos>
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any, Sequence

import lab_comum
import lab_indexacao
from lab_comum import Verificacao
from lab_indexacao import CRIAR, DIVERGENTE, PerguntaDeConferencia

ESPERA_PADRAO_SEGUNDOS = 30
INTERVALO_SEGUNDOS = 5


def verificar_definicao(atual: dict[str, Any] | None, definicao: dict[str, Any]) -> Verificacao:
    nome = "Definição do índice"
    if atual is None:
        return Verificacao(nome, False, f"o índice '{definicao['name']}' não existe. Rode indexar_documentos.py --executar")
    diferencas = lab_indexacao.diferencas_do_esquema(definicao, atual)
    if diferencas:
        return Verificacao(nome, False, "; ".join(diferencas[:5]))
    dimensoes = next(campo["dimensions"] for campo in definicao["fields"] if campo["name"] == lab_indexacao.CAMPO_VETOR)
    return Verificacao(nome, True, f"{len(definicao['fields'])} campo(s); vetor de {dimensoes} dimensões (HNSW, cosseno)")


def verificar_trechos(
    indice: Any, trechos: Sequence[lab_indexacao.Trecho], especificacao: lab_indexacao.EspecificacaoEmbedding,
    espera_segundos: float | None = None,
) -> tuple[Verificacao, dict[str, dict[str, Any]]]:
    """Compara o índice com o que os documentos produzem. Espera um pouco: o índice atualiza em segundos."""
    nome = "Trechos do índice"
    espera = ESPERA_PADRAO_SEGUNDOS if espera_segundos is None else espera_segundos
    limite = time.monotonic() + espera
    while True:
        gravados = indice.trechos_gravados()
        plano = lab_indexacao.planejar(trechos, {chave: valores["impressao"] for chave, valores in gravados.items()},
                                       especificacao)
        iguais = len(trechos) - plano.contar(CRIAR) - plano.contar(DIVERGENTE)
        if iguais == len(trechos) and not plano.orfaos:
            return Verificacao(nome, True, f"{len(gravados)} trecho(s) no índice e {len(trechos)} esperados, "
                                           "todos com a impressão digital esperada"), gravados
        if time.monotonic() >= limite:
            break
        time.sleep(INTERVALO_SEGUNDOS)
    problemas = []
    faltando = [acao.trecho.id for acao in plano.acoes if acao.estado == CRIAR]
    diferentes = [acao.trecho.id for acao in plano.acoes if acao.estado == DIVERGENTE]
    if faltando:
        problemas.append(f"faltam {len(faltando)} ({', '.join(faltando[:3])}{'...' if len(faltando) > 3 else ''})")
    if diferentes:
        problemas.append(f"{len(diferentes)} com conteúdo diferente ({', '.join(diferentes[:3])}{'...' if len(diferentes) > 3 else ''})")
    if plano.orfaos:
        problemas.append(f"{len(plano.orfaos)} sobrando ({', '.join(plano.orfaos[:3])}{'...' if len(plano.orfaos) > 3 else ''})")
    return Verificacao(nome, False, f"{len(gravados)} no índice para {len(trechos)} esperados: " + "; ".join(problemas)), gravados


def verificar_modelo(gravados: dict[str, dict[str, Any]], modelo_atual: str) -> Verificacao:
    nome = "Modelo dos vetores"
    modelos_do_indice = sorted({str(valores.get("modelo_embeddings") or "") for valores in gravados.values()})
    if modelos_do_indice == [modelo_atual]:
        return Verificacao(nome, True, f"o índice e o deployment usam o modelo '{modelo_atual}'")
    return Verificacao(
        nome, False,
        f"o índice foi gerado com {modelos_do_indice or 'nenhum modelo'}, mas o deployment responde com '{modelo_atual}'. "
        "Vetores de modelos diferentes não são comparáveis: recrie o índice com --recriar-indice.",
    )


def verificar_recuperacao(
    indice: Any, perguntas: Sequence[PerguntaDeConferencia], vetores: Sequence[Sequence[float]], k: int,
) -> Verificacao:
    nome = f"Busca vetorial ({len(perguntas)} perguntas)"
    linhas = []
    acertos = 0
    for pergunta, vetor in zip(perguntas, vetores):
        resultados = indice.consultar(None, vetor, k)
        posicao = lab_indexacao.posicao_do_esperado(pergunta, resultados)
        acertos += posicao is not None
        primeiro = resultados[0]["id"] if resultados else "nenhum resultado"
        situacao = f"esperado na posição {posicao}" if posicao else f"esperado ausente dos {k} primeiros"
        linhas.append(f"    {pergunta.id}: {situacao}; primeiro resultado {primeiro}")
    resumo = f"o trecho esperado apareceu entre os {k} primeiros em {acertos} de {len(perguntas)} perguntas"
    return Verificacao(nome, acertos == len(perguntas), resumo + "\n" + "\n".join(linhas))


def executar(args: argparse.Namespace) -> int:
    inventario = lab_comum.carregar_e_validar(args.inventario)
    perguntas = lab_indexacao.carregar_perguntas(args.perguntas)
    print(f"Verificação somente leitura: serviço de busca '{args.busca}', índice '{args.indice}'")
    print(f"Inventário: {len(inventario.documentos)} documento(s) conferidos por tamanho e hash; "
          f"{len(perguntas)} pergunta(s) de conferência.")

    documentos = [(documento, lab_comum.ler_conteudo(documento).decode("utf-8")) for documento in inventario.documentos]
    trechos = lab_indexacao.dividir_documentos(documentos, args.tamanho_maximo)
    especificacao = lab_indexacao.EspecificacaoEmbedding(args.deployment, args.dimensoes)
    definicao = lab_indexacao.definicao_do_indice(args.indice, args.dimensoes)
    indice = lab_indexacao.abrir_indice(args.busca, args.indice, args.tenant_id)

    resultados: list[Verificacao] = []

    def registrar(resultado: Verificacao) -> Verificacao:
        # Cada resultado é mostrado assim que fica pronto: se uma etapa seguinte falhar, o que passou já foi visto.
        resultados.append(resultado)
        print(f"[{'OK' if resultado.ok else 'FALHA':<5}] {resultado.nome}: {resultado.detalhe}")
        return resultado

    if registrar(verificar_definicao(indice.definicao_atual(), definicao)).ok:
        trechos_ok, gravados = verificar_trechos(indice, trechos, especificacao)
        registrar(trechos_ok)
        cliente = lab_indexacao.criar_cliente_embeddings(args.modelos, args.deployment, args.dimensoes, args.tenant_id)
        embeddings = cliente.gerar([pergunta.pergunta for pergunta in perguntas])
        registrar(verificar_modelo(gravados, embeddings.modelo))
        registrar(verificar_recuperacao(indice, perguntas, embeddings.vetores, args.k))
    registrar(lab_indexacao.verificar_acesso_sem_credenciais(args.busca, args.indice, args.modelos))

    if all(resultado.ok for resultado in resultados):
        print("Verificação aprovada.")
        return lab_comum.CODIGO_OK
    print("Verificação reprovada. Corrija as falhas e repita. Nada foi alterado por este script.")
    return lab_comum.CODIGO_DIVERGENCIA


def principal(argv: list[str] | None = None) -> int:
    lab_comum.configurar_saida()
    parser = lab_comum.criar_parser(__doc__, armazenamento=False)
    lab_indexacao.adicionar_argumentos_indice(parser)
    lab_indexacao.adicionar_argumento_tamanho(parser)
    parser.add_argument("--perguntas", type=Path, default=lab_indexacao.PERGUNTAS_PADRAO,
                        help="Perguntas de conferência (padrão: dados/l100/conferencia-recuperacao.json).")
    parser.add_argument("--k", default=3, type=lab_indexacao.validar_k,
                        help="Quantos resultados examinar por pergunta (padrão: 3).")
    args = parser.parse_args(argv)
    return lab_comum.executar_com_tratamento(executar, args, tradutor=lab_indexacao.traduzir_erro_indexacao)


if __name__ == "__main__":
    sys.exit(principal())
