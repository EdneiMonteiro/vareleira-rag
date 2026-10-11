r"""Planejador e verificador de encerramento do laboratório L300/L400: SOMENTE LEITURA, sem Azure.

Esta ferramenta nunca chama o Azure nem o `az` e nunca apaga nada. Ela lê um inventário e instantâneos que VOCÊ exportou com o
Azure CLI, valida tudo e imprime TEXTO: um plano ordenado de comandos para você revisar e executar por conta própria, os comandos
que capturam os instantâneos e o resultado da conferência. O único arquivo que ela grava é um relatório NOVO e sanitizado
(--relatorio): nunca sobrescreve outro arquivo e só traz contagens e vocabulário fechado.

Por que existe: o encerramento completo apaga recursos, identidades e papéis, e uma exclusão errada não tem volta. O roteiro
administrativo precisa de um inventário próprio e de uma ordem fixa (primeiro os consumidores, depois os shared private links
da busca, as identidades, os papéis, o grupo e os expurgos). Esta ferramenta recusa o que foge do inventário, imprime a ordem
validada e confere o resultado, sem nunca decidir por você.

Etapas (--etapa)
    modelo      imprime um modelo de inventário (JSON) para você preencher. O modelo é inválido de propósito: o plano o recusa
                até você trocar cada marcador <...> por um valor real
    capturar    imprime comandos PowerShell 7 que exportam grupos, recursos e atribuições de papel da assinatura (só leitura).
                --momento antes: a linha de base, capturada ANTES de criar o grupo exclusivo do laboratório.
                --momento depois: o estado final; imprime também o trecho que testa a presença de cada objeto do Entra ID e
                dos expurgos do inventário (404 = ausente, sucesso = presente, outro resultado = indeterminado)
    plano       valida o inventário (e a linha de base, se informada) e imprime o plano ordenado. Nada é executado.
                Sem a linha de base o plano é só uma PRÉVIA e diz isso. Cole a PREPARAÇÃO do plano primeiro, na mesma janela
                do PowerShell 7 em que colará os passos: cada bloco se recusa a rodar sem ela
    conferir    compara os instantâneos de antes e de depois e o arquivo de presença. Código 0 só se TODOS os critérios forem
                atendidos; reprovado ou pendente retorna 3. O que não pode ser conferido fica pendente, nunca aprovado
                (por exemplo, a presença não provada ou uma linha de base totalmente vazia, que poderia ser a assinatura errada)

Fluxo
    1. (antes de criar o grupo)  capturar --momento antes, e cole o bloco no PowerShell 7
    2. (depois de implantar)     modelo, preencha o inventário e guarde-o em local PRIVADO
    3.                           plano com os três arquivos da linha de base: revise TODOS os alvos
    4. (com autorização)         execute o plano você mesmo, um passo por vez, conferindo a verificação de cada passo
    5.                           capturar --momento depois, cole o bloco e rode conferir

Garantias
    - nenhum comando impresso usa curinga, --all (só nos comandos de captura, que leem), filtro por nome parcial ou ID deduzido;
      todo alvo vem literalmente do inventário, com valores validados entre aspas simples;
    - o grupo precisa ser atestado como exclusivo; nenhum item do inventário pode constar na linha de base; todo ID começa pelo
      prefixo exato do grupo exclusivo; toda atribuição de papel é do escopo do grupo e de um principal criado pelo laboratório;
    - um GUID só pode ter UM papel no inventário (objeto_id, app_id, principal, credencial, papel, assinatura, tenant): o
      `az ad ... --id` resolve primeiro pelo appId, e confundir o appId (ou o clientId de uma identidade gerenciada) com o ID de
      OBJETO faria o Microsoft Graph responder 404 para um objeto que ainda existe. principais_proprios e principal_id são IDs
      de OBJETO (principalId), nunca o clientId. Um GUID errado, porém distinto e bem formado, não é detectável offline;
    - os comandos impressos são blocos PowerShell COMPLETOS, cada um um único comando composto: ele se recusa a rodar, sem executar
      nada, fora do PowerShell 7 e enquanto a PREPARAÇÃO do plano não tiver sido colada e concluída na mesma janela;
    - o grupo gerenciado do Container Apps só é conferido como ausente: nunca é manipulado;
    - atribuições de papel HERDADAS de escopos acima da assinatura (a raiz do tenant e grupos de gerenciamento, que o
      `az role assignment list --all` inclui quando a assinatura fica sob um grupo de gerenciamento) são aceitas nos instantâneos,
      ignoradas e só contadas: o laboratório não as altera e a ferramenta não as compara. Item de OUTRA assinatura, com `id` e
      `scope` incoerentes ou de formato desconhecido continua recusado;
    - nenhum bloqueio administrativo é removido e nada é recriado para contornar uma falha;
    - mensagens de erro, de conferência e relatórios nunca repetem IDs, nomes ou segredos. O PLANO em si traz os IDs (ele é a
      lista do que apagar): trate-o como privado, igual ao inventário e aos instantâneos.

Códigos de saída: 0 concluído (conferir: aprovado); 1 uso ou entrada inválida (inclui toda guarda que recusa o inventário ou a
linha de base); 3 conferência reprovada ou pendente; 4 defeito do script (use --detalhes).

Exemplos (PowerShell 7, na raiz do projeto; <...> são os seus valores)
    # Linha de base: imprime os comandos; cole-os no PowerShell (ANTES de criar o grupo exclusivo)
    .\.venv\Scripts\python.exe scripts\planejar_encerramento.py --etapa capturar --momento antes --assinatura <GUID> --grupo <grupo> --pasta .\encerramento

    # Modelo de inventário (redirecione para um arquivo privado e preencha)
    .\.venv\Scripts\python.exe scripts\planejar_encerramento.py --etapa modelo > inventario.json

    # Plano, conferido contra a linha de base (--formato json imprime o plano em JSON, para ler por programa)
    .\.venv\Scripts\python.exe scripts\planejar_encerramento.py --etapa plano --inventario inventario.json --grupos-antes .\encerramento\grupos-antes.json --recursos-antes .\encerramento\recursos-antes.json --papeis-antes .\encerramento\papeis-antes.json

    # Relatório sanitizado do plano (só contagens); o arquivo precisa ser novo
    .\.venv\Scripts\python.exe scripts\planejar_encerramento.py --etapa plano --inventario inventario.json --grupos-antes .\encerramento\grupos-antes.json --recursos-antes .\encerramento\recursos-antes.json --papeis-antes .\encerramento\papeis-antes.json --relatorio .\encerramento\plano-relatorio.json

    # Depois de executar o plano: estado final e presença dos objetos
    .\.venv\Scripts\python.exe scripts\planejar_encerramento.py --etapa capturar --momento depois --assinatura <GUID> --grupo <grupo> --pasta .\encerramento --inventario inventario.json

    # Conferência final (0 = aprovado; 3 = reprovado ou pendente)
    .\.venv\Scripts\python.exe scripts\planejar_encerramento.py --etapa conferir --inventario inventario.json --grupos-antes .\encerramento\grupos-antes.json --recursos-antes .\encerramento\recursos-antes.json --papeis-antes .\encerramento\papeis-antes.json --grupos-depois .\encerramento\grupos-depois.json --recursos-depois .\encerramento\recursos-depois.json --papeis-depois .\encerramento\papeis-depois.json --presenca .\encerramento\presenca-depois.json --relatorio .\encerramento\conferencia.json

Depois da conferência, consulte os custos sem interpretar uma resposta vazia como custo zero: atraso de cobrança é comum.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Callable

import lab_comum
import lab_encerramento as enc
from lab_comum import CODIGO_INESPERADO, CODIGO_OK, CODIGO_USO, ErroLab

ETAPAS = ("modelo", "capturar", "plano", "conferir")

COMO_PREENCHER = """\
[AVISO] Este modelo NÃO é válido de propósito: troque cada <marcador> por um valor real e use "grupo_exclusivo": true SOMENTE se
ninguém mais usa o grupo. Apague os itens de exemplo que não se aplicam (use [] para uma lista sem itens). Guarde o inventário em
local PRIVADO: ele traz identificadores do seu ambiente.
ATENÇÃO aos IDs: principais_proprios, principal_id e objeto_id são IDs de OBJETO (o `id`/`principalId`), NUNCA o clientId nem o
appId; app_id é o appId (client id) do aplicativo. São GUIDs diferentes e um GUID só pode ter um papel no inventário. Com o ID
errado, o Microsoft Graph responde 404 para um objeto que ainda existe e a "ausência" fica vazia.
Onde achar os valores (comandos que só leem; troque <...> pelos seus valores):
  recursos             az resource list --resource-group <grupo> --query "[].{id:id,tipo:type}"
  shared private links az search shared-private-link-resource list --resource-group <grupo> --service-name <busca> --query "[].id"
  atribuições          az role assignment list --scope /subscriptions/<assinatura>/resourceGroups/<grupo> --fill-principal-name false --query "[].{id:id,escopo:scope,principal_id:principalId,papel:roleDefinitionId}"
  aplicativo do Entra  az ad app show --id <app_id> --query "{objeto_id:id,app_id:appId,nome:displayName}"
  credenciais          az ad app credential list --id <app_id> --query "[].keyId"
  principal de serviço az ad sp show --id <app_id> --query "{principal_id:id,app_id:appId}"   (principal_id é o `id`, não o appId)
  identidade gerenciada az identity show --ids <ID da identidade> --query "{principal_id:principalId,client_id:clientId}"   (use o principal_id; o client_id NÃO serve)
Uma listagem do grupo exclusivo deve mostrar só recursos do laboratório: inclua TODOS em recursos_proprios (o passo do grupo recusa-se
a apagar se sobrar algo fora do inventário). Já a listagem de atribuições de um escopo pode trazer também papéis herdados ou de
outros principais: inclua em atribuicoes_proprias só os que o laboratório criou (principal em principais_proprios)."""


def _guid(valor: str) -> str:
    if not enc.eh_guid(valor):
        raise argparse.ArgumentTypeError("deve ser um GUID (por exemplo, o ID da assinatura).")
    return valor.lower()


def _nome_de_grupo(valor: str) -> str:
    if not enc.eh_nome_de_grupo(valor):
        raise argparse.ArgumentTypeError("deve ser um nome de grupo: até 90 caracteres, letras, números, '.', '_' e '-'.")
    return valor


def criar_parser() -> lab_comum.ParserLab:
    parser = lab_comum.ParserLab(description=__doc__)
    parser.add_argument("--etapa", required=True, choices=ETAPAS, help="modelo, capturar, plano ou conferir (veja a descrição acima).")
    parser.add_argument("--inventario", type=Path, default=None,
                        help="Inventário JSON privado (plano, conferir e capturar --momento depois). Use --etapa modelo para o formato.")
    parser.add_argument("--assinatura", type=_guid, default=None, help="capturar: GUID da assinatura do laboratório.")
    parser.add_argument("--grupo", type=_nome_de_grupo, default=None, help="capturar: nome do grupo exclusivo do laboratório.")
    parser.add_argument("--momento", choices=enc.MOMENTOS, default=None,
                        help="capturar: antes (linha de base, ANTES de criar o grupo) ou depois (estado final).")
    parser.add_argument("--pasta", default=None, help="capturar: pasta local onde os comandos impressos gravarão os instantâneos.")
    for momento in enc.MOMENTOS:
        for nome, descricao in (("grupos", "az group list"), ("recursos", "az resource list"), ("papeis", "az role assignment list --all")):
            parser.add_argument(f"--{nome}-{momento}", type=Path, default=None,
                                help=f"{'plano e ' if momento == 'antes' else ''}conferir: JSON exportado por '{descricao}' "
                                     f"({'linha de base' if momento == 'antes' else 'estado final'}).")
    parser.add_argument("--presenca", type=Path, default=None,
                        help="conferir: presenca-depois.json, gerado pelo trecho de 'capturar --momento depois'. Sem ele, os critérios "
                             "do Entra ID e dos expurgos ficam pendentes.")
    parser.add_argument("--formato", choices=("texto", "json"), default="texto", help="plano: texto (padrão) ou json.")
    parser.add_argument("--relatorio", type=Path, default=None,
                        help="plano e conferir: relatório JSON sanitizado a criar. Precisa ser um arquivo NOVO: nunca sobrescreve.")
    parser.add_argument("--detalhes", action="store_true",
                        help="Mostra o erro técnico de um defeito do script. Pode conter dados do seu ambiente: não publique.")
    return parser


def _exigir(valor: object, opcao: str, etapa: str) -> None:
    if valor is None:
        raise ErroLab(f"Na etapa {etapa}, informe {opcao}. Veja a ajuda com --help.")


def _arquivos_da_linha_de_base(args: argparse.Namespace) -> tuple[Path, Path, Path] | None:
    informados = [args.grupos_antes, args.recursos_antes, args.papeis_antes]
    if all(i is None for i in informados):
        return None
    if any(i is None for i in informados):
        raise ErroLab("Informe os TRÊS arquivos da linha de base (--grupos-antes, --recursos-antes e --papeis-antes) ou nenhum: "
                      "uma linha de base parcial não permite conferir o inventário.")
    return tuple(informados)  # type: ignore[return-value]


def etapa_modelo(args: argparse.Namespace) -> int:
    print(json.dumps(enc.modelo_de_inventario(), ensure_ascii=False, indent=2))
    print(COMO_PREENCHER, file=sys.stderr)
    return CODIGO_OK


def etapa_capturar(args: argparse.Namespace) -> int:
    for valor, opcao in ((args.assinatura, "--assinatura"), (args.grupo, "--grupo"), (args.momento, "--momento"), (args.pasta, "--pasta")):
        _exigir(valor, opcao, "capturar")
    inventario = enc.carregar_inventario(args.inventario) if args.inventario else None
    print(enc.comandos_de_captura(args.assinatura, args.grupo, args.momento, args.pasta, inventario))
    return CODIGO_OK


def etapa_plano(args: argparse.Namespace) -> int:
    _exigir(args.inventario, "--inventario", "plano")
    relatorio = enc.exigir_relatorio_novo(args.relatorio)
    inventario = enc.carregar_inventario(args.inventario)
    arquivos = _arquivos_da_linha_de_base(args)
    conferida = False
    herdadas = 0
    if arquivos is not None:
        base = enc.carregar_instantaneo(*arquivos, inventario.assinatura, "antes")
        enc.validar_linha_de_base(inventario, base)
        conferida = not base.vazio
        herdadas = base.atribuicoes_herdadas_ignoradas
        if not conferida:
            print("[AVISO] A linha de base está totalmente vazia: não dá para distinguir uma assinatura sem nada de uma exportação da "
                  "assinatura errada, então ela não conferiu nada. Este plano é só uma PRÉVIA.", file=sys.stderr)
    else:
        print("[AVISO] Sem a linha de base (--grupos-antes, --recursos-antes e --papeis-antes), não foi possível conferir que nenhum "
              "alvo já existia antes do laboratório: este plano é só uma PRÉVIA. Não execute nada antes de repetir o comando com os "
              "três arquivos.", file=sys.stderr)
    plano = enc.montar_plano(inventario, conferida, herdadas)
    print(json.dumps(enc.plano_em_dict(plano), ensure_ascii=False, indent=2) if args.formato == "json" else enc.plano_em_texto(plano))
    if relatorio is not None:
        enc.gravar_relatorio(relatorio, enc.relatorio_do_plano(plano))
        print("Relatório sanitizado do plano gravado (só contagens, sem IDs).", file=sys.stderr)
    return CODIGO_OK


def etapa_conferir(args: argparse.Namespace) -> int:
    _exigir(args.inventario, "--inventario", "conferir")
    faltando = [opcao for valor, opcao in (
        (args.grupos_antes, "--grupos-antes"), (args.recursos_antes, "--recursos-antes"), (args.papeis_antes, "--papeis-antes"),
        (args.grupos_depois, "--grupos-depois"), (args.recursos_depois, "--recursos-depois"), (args.papeis_depois, "--papeis-depois")) if valor is None]
    if faltando:
        raise ErroLab("Na etapa conferir, informe também: " + ", ".join(faltando) + ".")
    relatorio = enc.exigir_relatorio_novo(args.relatorio)
    inventario = enc.carregar_inventario(args.inventario)
    antes = enc.carregar_instantaneo(args.grupos_antes, args.recursos_antes, args.papeis_antes, inventario.assinatura, "antes")
    enc.validar_linha_de_base(inventario, antes)
    depois = enc.carregar_instantaneo(args.grupos_depois, args.recursos_depois, args.papeis_depois, inventario.assinatura, "depois")
    presenca = enc.carregar_presenca(args.presenca, inventario) if args.presenca else None
    conferencia = enc.conferir_encerramento(inventario, antes, depois, presenca)
    print(enc.conferencia_em_texto(conferencia))
    if relatorio is not None:
        enc.gravar_relatorio(relatorio, enc.relatorio_da_conferencia(conferencia))
        print("Relatório sanitizado da conferência gravado (só contagens, sem IDs).")
    enc.exigir_aprovacao(conferencia)
    print("Resultado: APROVADO. Todos os critérios foram atendidos nos arquivos conferidos. Consulte os custos sem interpretar resposta "
          "vazia como custo zero.")
    return CODIGO_OK


_ETAPAS: dict[str, Callable[[argparse.Namespace], int]] = {
    "modelo": etapa_modelo, "capturar": etapa_capturar, "plano": etapa_plano, "conferir": etapa_conferir,
}


def _traduzir_erro(erro: Exception, args: argparse.Namespace) -> tuple[str, int]:
    return (f"Erro inesperado do script ({type(erro).__name__}). Nada foi alterado; o texto técnico foi omitido de propósito, porque "
            "pode conter dados do seu ambiente. Use --detalhes e, se persistir, abra uma issue sem dados do seu ambiente.",
            CODIGO_INESPERADO)


def principal(argv: list[str] | None = None) -> int:
    lab_comum.configurar_saida()
    if sys.version_info < (3, 12):
        print("[ERRO] Este script exige Python 3.12 ou superior.", file=sys.stderr)
        return CODIGO_USO
    args = criar_parser().parse_args(argv)
    return lab_comum.executar_com_tratamento(lambda a: _ETAPAS[a.etapa](a), args, tradutor=_traduzir_erro)


if __name__ == "__main__":
    sys.exit(principal())
