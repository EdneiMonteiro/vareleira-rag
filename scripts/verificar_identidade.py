"""Confere o privilégio mínimo de uma identidade (L100, Desafio 07).

Com a identidade da aplicação (service principal), o script tenta duas operações que ela precisa fazer (consultar o índice e
gerar embeddings) e três que ela não deve poder fazer: alterar o serviço de busca, ler o segredo do cofre e listar os documentos do
armazenamento. As tentativas proibidas usam alvos que não existem ou resultados descartados. A de busca tenta apagar um índice
de nome aleatório, novo a cada execução: como esse índice não existe, ela não atinge nenhum índice real, mesmo que a permissão
esteja errada. O resultado "permitido" nelas significa privilégio demais; "negado" nas duas primeiras, privilégio de menos.
O resultado vale só para essas cinco tentativas: não prova que a identidade não tenha outros acessos. O segredo da aplicação é
lido do cofre com a sua conta (az login). Com --identidade operador, as mesmas tentativas usam a sua conta, que costuma ter
papéis amplos, para mostrar o contraste. Não cria, altera nem apaga recursos existentes.

Exemplos:
    python scripts\\verificar_identidade.py --busca <busca> --modelos <modelos> --conta <conta> --cofre <cofre> --id-da-aplicacao <appId> --tenant-id <tenant>
    python scripts\\verificar_identidade.py --busca <busca> --modelos <modelos> --conta <conta> --cofre <cofre> --identidade operador
"""

from __future__ import annotations

import argparse
import secrets
import sys
from dataclasses import dataclass
from typing import Any, Callable

import lab_comum
import lab_identidade
import lab_indexacao
from lab_comum import Verificacao

PERMITIDO, NEGADO, INCONCLUSIVO = "permitido", "negado", "inconclusivo"
PREFIXO_INDICE_DESCARTAVEL = "vlr-verificacao-"
TEXTO_DE_TESTE = "teste da identidade da aplicação"


def nome_de_indice_descartavel() -> str:
    """Nome novo e aleatório (64 bits) a cada chamada. Um nome fixo poderia coincidir com um índice real do serviço."""
    return PREFIXO_INDICE_DESCARTAVEL + secrets.token_hex(8)


@dataclass(frozen=True)
class Tentativa:
    nome: str
    esperado: str
    operacao: Callable[[], Any]
    # Em alvos que não existem, o 404 só chega depois da autorização: a operação foi permitida.
    autorizado_se_nao_existe: bool = False


def classificar(operacao: Callable[[], Any], autorizado_se_nao_existe: bool = False) -> tuple[str, str]:
    """Executa a operação e diz se o Azure a permitiu, a negou (HTTP 403) ou se o resultado não permite concluir."""
    try:
        operacao()
    except Exception as erro:  # noqa: BLE001 - qualquer recusa do serviço vira uma linha da conferência
        status = getattr(erro, "status_code", None)
        nome = type(erro).__name__
        if status == 403:
            return NEGADO, "HTTP 403"
        if status == 404 and autorizado_se_nao_existe:
            return PERMITIDO, "HTTP 404 depois da autorização: o alvo não existe, como esperado"
        if nome == "ClientAuthenticationError" or status == 401:
            return INCONCLUSIVO, "a autenticação da aplicação falhou"
        return INCONCLUSIVO, nome + (f", HTTP {status}" if status else "")
    return PERMITIDO, "operação aceita"


def conferir(tentativa: Tentativa) -> Verificacao:
    observado, detalhe = classificar(tentativa.operacao, tentativa.autorizado_se_nao_existe)
    if observado == tentativa.esperado:
        return Verificacao(tentativa.nome, True, f"{observado}, como esperado ({detalhe})")
    if observado == PERMITIDO:
        explicacao = "PRIVILÉGIO DEMAIS: a identidade não deveria poder fazer isto. Revise os papéis dela"
    elif observado == NEGADO:
        explicacao = "PRIVILÉGIO DE MENOS: a identidade precisa fazer isto. Revise os papéis dela (um papel novo pode levar alguns minutos)"
    else:
        explicacao = "não foi possível concluir"
    return Verificacao(tentativa.nome, False, f"esperado {tentativa.esperado}, obtido {observado} ({detalhe}). {explicacao}")


def montar_tentativas(args: argparse.Namespace, credencial: Any) -> list[Tentativa]:
    indice = lab_indexacao.abrir_indice(args.busca, args.indice, args.tenant_id, credencial)
    descartavel = nome_de_indice_descartavel()
    while descartavel == args.indice:
        descartavel = nome_de_indice_descartavel()
    inexistente = lab_indexacao.abrir_indice(args.busca, descartavel, args.tenant_id, credencial)
    embeddings = lab_indexacao.criar_cliente_embeddings(args.modelos, args.deployment, args.dimensoes, args.tenant_id, credencial)
    cofre = lab_identidade.criar_cliente_de_segredos(args.cofre, args.tenant_id, credencial)
    container = lab_comum.criar_container(args.conta, args.container, args.tenant_id, credencial)
    return [
        Tentativa(f"Consultar o índice '{args.indice}' (leitura)", PERMITIDO, indice.contar),
        Tentativa(f"Gerar embeddings no recurso '{args.modelos}'", PERMITIDO, lambda: embeddings.gerar([TEXTO_DE_TESTE])),
        Tentativa("Alterar o serviço de busca (apagar um índice de nome aleatório que não existe)", NEGADO,
                  inexistente.apagar, True),
        Tentativa(f"Ler o segredo '{args.nome_do_segredo}' do cofre '{args.cofre}'", NEGADO,
                  lambda: cofre.get_secret(args.nome_do_segredo), True),
        Tentativa(f"Listar os documentos da conta '{args.conta}'", NEGADO,
                  lambda: next(iter(container.list_blobs()), None), True),
    ]


def executar(args: argparse.Namespace) -> int:
    if args.identidade == "operador" and not args.cofre:
        raise lab_comum.ErroLab("Informe --cofre: uma das tentativas lê um segredo do cofre.")
    credencial = lab_identidade.resolver_credencial(args)
    print(f"Verificação do privilégio mínimo, sem alterar recursos existentes · identidade: {lab_identidade.descrever_identidade(args)}")
    print(f"Alvos: busca '{args.busca}', modelos '{args.modelos}', conta '{args.conta}', cofre '{args.cofre}'.")
    resultados: list[Verificacao] = []
    for tentativa in montar_tentativas(args, credencial):
        resultado = conferir(tentativa)
        resultados.append(resultado)
        # Cada resultado é mostrado assim que fica pronto: se uma tentativa seguinte falhar, o que passou já foi visto.
        print(f"[{'OK' if resultado.ok else 'FALHA':<5}] {resultado.nome}: {resultado.detalhe}")
    if args.identidade == "operador":
        print("Esta conferência usou a sua conta, que costuma ter papéis amplos: as falhas por privilégio demais são o contraste "
              "esperado. Use --identidade aplicacao para conferir a aplicação.")
    alcance = ("Este resultado vale só para as cinco tentativas acima. Nenhum recurso existente foi alterado por este script: "
               "a exclusão testada usa o nome aleatório de um índice que não existe.")
    if all(resultado.ok for resultado in resultados):
        print("As duas operações necessárias funcionaram e as três proibidas foram recusadas. " + alcance + " Isso não prova que "
              "a identidade não tenha outros acessos: revise também as atribuições de papel dela no Azure.")
        return lab_comum.CODIGO_OK
    print("Privilégio divergente do esperado. Corrija os papéis e repita. " + alcance)
    return lab_comum.CODIGO_DIVERGENCIA


def principal(argv: list[str] | None = None) -> int:
    lab_comum.configurar_saida()
    parser = lab_comum.criar_parser(__doc__, inventario=False)
    lab_indexacao.adicionar_argumentos_indice(parser)
    lab_identidade.adicionar_argumentos_identidade(parser)
    parser.set_defaults(identidade="aplicacao")
    args = parser.parse_args(argv)
    return lab_comum.executar_com_tratamento(executar, args, tradutor=lab_identidade.traduzir_erro_identidade)


if __name__ == "__main__":
    sys.exit(principal())
