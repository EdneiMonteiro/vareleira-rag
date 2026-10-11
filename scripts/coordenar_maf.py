"""Responde a uma pergunta com a coordenação limitada do Microsoft Agent Framework (L400, Desafio 02).

Um agente de planejamento sugere até 2 consultas curtas, o programa busca cada uma com o filtro documental do perfil, confere versões e
trechos, e um agente de redação responde com referências curtas. O programa monta as citações e aplica a política do L100. Cada pergunta
tem limites finitos (chamadas, buscas, tokens, tempo), e toda tentativa conta, inclusive as que falham. Não altera nada no Azure.

--mostrar-plano exibe o fluxo, as instruções, os esquemas e os limites sem rede, sem credenciais e sem Azure.

Perfil: --perfil é a escolha de quem opera o comando, em uma máquina de confiança; ele não é uma autenticação do Microsoft Entra ID. Na API
HTTP do chat, o perfil vem dos papéis da identidade validada pela plataforma e nunca do JSON enviado pelo navegador.

Identidade: o Azure CLI (az login) por padrão, ou a identidade gerenciada com --identidade-gerenciada (e --client-id, se for a atribuída
ao usuário). Nenhuma chave é usada.

Ctrl+C cancela só esta consulta: as próximas etapas não executam. Um pedido ao modelo já enviado pode terminar e consumir tokens.

Exemplos:
    python scripts\\coordenar_maf.py --mostrar-plano
    python scripts\\coordenar_maf.py --busca <busca> --modelos <modelos> --perfil atendimento --pergunta "O seguro cobre danos elétricos e qual é a franquia?"
    python scripts\\coordenar_maf.py --busca <busca> --modelos <modelos> --perfil corretor --deployment-contingencia geracao-contingencia --pergunta "..."
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import textwrap
import threading
from typing import Any, Callable

import lab_acesso
import lab_chat
import lab_comum
import lab_geracao
import lab_indexacao
import lab_orquestracao
import lab_politica
from lab_comum import ErroLab

LARGURA = 100
LARGURA_DA_CITACAO = 160
CODIGO_CANCELADO = 130  # o de um programa interrompido por Ctrl+C
ESPERA_DO_CANCELAMENTO = 30.0  # segundos: o serviço termina antes disso, mesmo com uma busca em andamento (limite de 20 s)
PERFIS = {
    "atendimento": (lab_acesso.PAPEL_ATENDIMENTO,),
    "corretor": (lab_acesso.PAPEL_CORRETOR,),
    "ambos": (lab_acesso.PAPEL_ATENDIMENTO, lab_acesso.PAPEL_CORRETOR),
}
CODIGOS_DE_SAIDA = {
    lab_chat.NAO_AUTORIZADO: lab_comum.CODIGO_ACESSO,
    lab_chat.INDISPONIVEL: lab_comum.CODIGO_ACESSO,
    lab_chat.RESPOSTA_NAO_VERIFICADA: lab_comum.CODIGO_DIVERGENCIA,
    lab_chat.PERGUNTA_BLOQUEADA: lab_comum.CODIGO_USO,
    lab_chat.CANCELADO: CODIGO_CANCELADO,
}
_PADRAO_GUID = re.compile(r"[0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}")


def _inteiro(minimo: int, maximo: int, descricao: str) -> Callable[[str], int]:
    def validar(valor: str) -> int:
        try:
            numero = int(valor)
        except ValueError:
            numero = minimo - 1
        if not minimo <= numero <= maximo:
            raise argparse.ArgumentTypeError(f"{descricao}: um número inteiro de {minimo} a {maximo} (recebido: {valor!r}).")
        return numero

    return validar


def _decimal(minimo: float, maximo: float, descricao: str) -> Callable[[str], float]:
    def validar(valor: str) -> float:
        try:
            numero = float(valor)
        except ValueError:
            numero = math.nan
        if not math.isfinite(numero) or not minimo <= numero <= maximo:
            raise argparse.ArgumentTypeError(f"{descricao}: um número de {minimo:g} a {maximo:g} (recebido: {valor!r}).")
        return numero

    return validar


def _guid(valor: str) -> str:
    if not _PADRAO_GUID.fullmatch(valor):
        raise argparse.ArgumentTypeError("O --client-id deve ser um GUID.")
    return valor.lower()


def adicionar_argumentos(parser: lab_comum.ParserLab) -> None:
    padrao = lab_orquestracao.LimitesCoordenacao()
    faixas = lab_orquestracao.FAIXAS_DOS_LIMITES
    parser.add_argument("--mostrar-plano", action="store_true",
                        help="Mostra o fluxo, as instruções, os esquemas e os limites, sem rede, sem credenciais e sem Azure.")
    parser.add_argument("--pergunta", default=None, help="A pergunta, entre aspas. Obrigatória, exceto com --mostrar-plano.")
    parser.add_argument("--perfil", choices=tuple(PERFIS), default=None,
                        help="Perfil documental, escolhido por quem opera o comando (não é autenticação do Entra ID). "
                             "Obrigatório na consulta; define as classes de documento do filtro.")
    parser.add_argument("--busca", default=None, type=lab_indexacao.validar_busca,
                        help="Nome do serviço de busca (saída nomeBusca da implantação). Obrigatório na consulta.")
    parser.add_argument("--modelos", default=None, type=lab_indexacao.validar_modelos,
                        help="Nome do recurso de modelos (saída nomeModelos da implantação). Obrigatório na consulta.")
    parser.add_argument("--indice", default=lab_acesso.INDICE_PADRAO, type=lab_indexacao.validar_indice,
                        help=f"Índice no formato do L300, com o campo de acesso (padrão: {lab_acesso.INDICE_PADRAO}).")
    parser.add_argument("--deployment", default=lab_indexacao.DEPLOYMENT_PADRAO, type=lab_indexacao.validar_deployment,
                        help=f"Deployment de embeddings, não o modelo (padrão: {lab_indexacao.DEPLOYMENT_PADRAO}).")
    parser.add_argument("--dimensoes", default=lab_indexacao.DIMENSOES_PADRAO, type=lab_indexacao.validar_dimensoes,
                        help=f"Dimensões dos vetores, iguais às do índice (padrão: {lab_indexacao.DIMENSOES_PADRAO}).")
    lab_geracao.adicionar_argumentos_geracao(parser)
    parser.add_argument("--deployment-contingencia", default=None, type=lab_indexacao.validar_deployment,
                        help="Outro deployment de geração, do mesmo modelo e da mesma versão, usado só em falha transitória "
                             f"(ex.: {lab_orquestracao.DEPLOYMENT_DE_CONTINGENCIA_SUGERIDO}). Um segundo deployment não garante "
                             "cota adicional. Sem esta opção, não há contingência.")
    parser.add_argument("--identidade-gerenciada", action="store_true",
                        help="Usa a identidade gerenciada em vez do Azure CLI (para quando o comando roda dentro do Azure).")
    parser.add_argument("--client-id", default=None, type=_guid,
                        help="Com --identidade-gerenciada, o client id da identidade atribuída ao usuário.")
    parser.add_argument("--tempo", default=lab_chat.TEMPO_PADRAO,
                        type=_decimal(lab_chat.TEMPO_MINIMO_COORDENACAO, lab_chat.TEMPO_MAXIMO, "O tempo, em segundos"),
                        help=f"Tempo da consulta, como VARELEIRA_TIMEOUT_SEGUNDOS (padrão: {lab_chat.TEMPO_PADRAO:g}). "
                             "O serviço usa 2 s a menos.")
    parser.add_argument("--max-chamadas", default=padrao.max_chamadas,
                        type=_inteiro(*faixas["max_chamadas"], "O máximo de chamadas"),
                        help=f"Tentativas ao modelo, aos embeddings e à busca juntas (padrão: {padrao.max_chamadas}).")
    parser.add_argument("--max-buscas", default=padrao.max_buscas,
                        type=_inteiro(*faixas["max_buscas"], "O máximo de buscas"),
                        help=f"Buscas por pergunta (padrão: {padrao.max_buscas}).")
    parser.add_argument("--max-tokens", default=padrao.max_tokens,
                        type=_inteiro(*faixas["max_tokens"], "O máximo de tokens"),
                        help=f"Tokens de entrada e saída da geração, com reserva conservadora (padrão: {padrao.max_tokens}).")
    parser.add_argument("--tarifa-entrada", default=None, type=_decimal(0, 1e9, "A tarifa"),
                        help="Preço por milhão de tokens de entrada, na moeda que você escolher. Com --tarifa-saida, o programa "
                             "mostra uma estimativa de valor; sem tarifa, não mostra valor.")
    parser.add_argument("--tarifa-saida", default=None, type=_decimal(0, 1e9, "A tarifa"),
                        help="Preço por milhão de tokens de saída (já inclui o raciocínio).")
    parser.add_argument("--tarifa-embeddings", default=0.0, type=_decimal(0, 1e9, "A tarifa"),
                        help="Preço por milhão de tokens de embeddings (padrão: 0).")


def escrever(texto: str, recuo: str = "  ") -> None:
    print(textwrap.fill(texto, width=LARGURA, initial_indent=recuo, subsequent_indent=recuo))


def montar_parametros(args: argparse.Namespace, *, para_o_plano: bool = False) -> lab_orquestracao.ParametrosCoordenacao:
    """Os parâmetros do serviço a partir das opções. Para o plano, os nomes dos recursos podem faltar: nada é acessado."""
    limites = lab_orquestracao.LimitesCoordenacao(max_chamadas=args.max_chamadas, max_buscas=args.max_buscas, max_tokens=args.max_tokens)
    parametros = lab_orquestracao.ParametrosCoordenacao(
        modelos=args.modelos or ("modelos-exemplo" if para_o_plano else ""), busca=args.busca or ("busca-exemplo" if para_o_plano else ""),
        indice=args.indice, deployment_embeddings=args.deployment, dimensoes=args.dimensoes,
        deployment_geracao=args.deployment_geracao, deployment_contingencia=args.deployment_contingencia,
        esforco=args.esforco, modo_busca=args.modo, k=args.k, timeout_segundos=args.tempo, tenant_id=args.tenant_id,
        limites=limites)
    parametros.validar()
    return parametros


def exigir_opcoes_da_consulta(args: argparse.Namespace) -> None:
    faltam = [opcao for opcao, valor in (("--busca", args.busca), ("--modelos", args.modelos), ("--perfil", args.perfil),
                                         ("--pergunta", args.pergunta)) if not valor]
    if faltam:
        raise ErroLab(f"Para consultar, informe {', '.join(faltam)}. Para só examinar o fluxo, use --mostrar-plano.")
    if args.client_id and not args.identidade_gerenciada:
        raise ErroLab("--client-id só vale com --identidade-gerenciada.")
    if (args.tarifa_entrada is None) != (args.tarifa_saida is None):
        raise ErroLab("Informe --tarifa-entrada e --tarifa-saida juntas, ou nenhuma delas.")


def mostrar_plano(args: argparse.Namespace) -> None:
    parametros = montar_parametros(args, para_o_plano=True)
    acesso = lab_acesso.autorizar(PERFIS[args.perfil]) if args.perfil else None
    print("Plano da coordenação (sem rede, sem credenciais e sem Azure)")
    for linha in lab_orquestracao.descrever_plano(parametros, acesso):
        print(linha)
    print("\nPerfil: na consulta, --perfil é a escolha de quem opera o comando e não uma autenticação do Entra ID;"
          " na API HTTP, o perfil vem dos papéis da identidade validada, nunca do JSON.")
    if acesso is not None:
        print(f"  --perfil {args.perfil}: classes {', '.join(acesso.classes)} · filtro: {acesso.filtro}")
    print("\n--- Instruções do agente de planejamento ---")
    print(lab_orquestracao.INSTRUCOES_DO_PLANEJADOR.rstrip())
    print("\n--- Esquema fechado do plano (o que o agente de planejamento devolve) ---")
    print(json.dumps(lab_orquestracao.CONTRATO_DO_PLANO.esquema["schema"], ensure_ascii=False, indent=2))
    print("\n--- Instruções do agente de redação (as mesmas do chat convencional) ---")
    print(lab_chat.INSTRUCOES_L200.rstrip())
    print("\n--- Fim do plano ---")


def criar_credencial(args: argparse.Namespace) -> Any:
    """A identidade do comando, sem chaves: identidade gerenciada, se pedida, ou o Azure CLI (az login)."""
    try:
        from azure.identity import AzureCliCredential, ManagedIdentityCredential
    except ImportError:
        raise ErroLab(lab_orquestracao.MENSAGEM_SEM_MAF) from None
    if args.identidade_gerenciada:
        return ManagedIdentityCredential(client_id=args.client_id)
    return AzureCliCredential(tenant_id=args.tenant_id, process_timeout=30)


def imprimir_evento(evento: lab_orquestracao.EventoProgresso) -> None:
    """Uma linha por evento, só com vocabulário fechado e contagens, na hora em que o evento acontece."""
    dados = evento.dados
    if evento.tipo == lab_orquestracao.EVENTO_ETAPA:
        detalhes = ", ".join(f"{nome}={valor}" for nome, valor in dados.items() if nome != "ms")
        print(f"  [etapa] {evento.etapa}: {evento.estado}" + (f" ({detalhes})" if detalhes else ""), flush=True)
    elif evento.tipo == lab_orquestracao.EVENTO_TENTATIVA:
        causa = f", causa {dados['causa']}" if "causa" in dados else ""
        print(f"  [tentativa {dados.get('numero', '?')}] {evento.etapa}, deployment {dados.get('deployment', '?')}: "
              f"{evento.estado}{causa}", flush=True)


def consultar(servico: Any, pergunta: str, acesso: lab_acesso.ContextoAcesso,
              progresso: Callable[[lab_orquestracao.EventoProgresso], None]) -> lab_chat.RespostaChat:
    """Roda a consulta em uma thread: Ctrl+C dá o sinal de cancelamento desta consulta e espera o serviço terminar."""
    cancelar = threading.Event()
    resultado: dict[str, Any] = {}

    def trabalho() -> None:
        try:
            resultado["resposta"] = servico.perguntar(pergunta, acesso, progresso=progresso, cancelar=cancelar)
        except BaseException as erro:  # noqa: BLE001 - o erro é tratado na thread principal
            resultado["erro"] = erro

    thread = threading.Thread(target=trabalho, name="coordenacao-cli", daemon=True)  # o Ctrl+C nunca prende o processo a uma chamada remota
    thread.start()
    try:
        while thread.is_alive():
            thread.join(0.2)
    except KeyboardInterrupt:
        cancelar.set()
        print("\nCancelando: as próximas etapas não serão executadas. Um pedido ao modelo já enviado pode terminar e consumir tokens.",
              flush=True)
        thread.join(ESPERA_DO_CANCELAMENTO)
    if "erro" in resultado:
        raise resultado["erro"]
    if "resposta" not in resultado:
        raise lab_chat.ErroChat(lab_chat.CANCELADO, lab_orquestracao.CAUSA_CANCELADO)
    return resultado["resposta"]


def mostrar_resposta(resposta: lab_chat.RespostaChat) -> None:
    print(f"\nTipo da pergunta: {lab_politica.ROTULOS[resposta.tipo]}")
    titulo = {lab_politica.RESPONDIDA: "Resposta", lab_politica.RECUSADA: "Recusa",
              lab_politica.ESCLARECIMENTO: "Pergunta de esclarecimento"}[resposta.situacao]
    print(f"\n{titulo}:")
    escrever(resposta.texto)
    if resposta.evidencias:
        print("\nEvidências (cada citação é o texto do trecho recuperado, montado pelo programa):")
        for evidencia in resposta.evidencias:
            citacao = textwrap.shorten(evidencia.citacao, width=LARGURA_DA_CITACAO, placeholder="…")
            print(f"  [{evidencia.id}] \"{citacao}\"")
            clausulas = f" (cláusulas {evidencia.clausulas})" if evidencia.clausulas else ""
            print(f"      {evidencia.documento} · {evidencia.secao}{clausulas} · versão {evidencia.versao} · {evidencia.fonte}")
    if resposta.aviso:
        print("\nAviso:")
        escrever(resposta.aviso)


def mostrar_uso(resumo: dict[str, Any], limites: lab_orquestracao.LimitesCoordenacao, tarifa: lab_orquestracao.Tarifa | None) -> None:
    """Chamadas, tokens e incerteza da execução, inclusive quando ela falhou ou foi cancelada."""
    if not resumo:
        print("\nUso: a execução terminou antes de informar o resumo.")
        return
    print("\nLimites e uso desta execução:")
    print(f"  chamadas: {resumo['chamadas_total']} de {limites.max_chamadas} (modelo {resumo['chamadas_modelo']} de "
          f"{limites.max_chamadas_modelo}, com {resumo['tentativas_falhas']} falha(s); embeddings {resumo['chamadas_embeddings']}; "
          f"buscas {resumo['buscas']} de {limites.max_buscas}) · contingência usada: {'sim' if resumo['contingencia'] else 'não'}")
    print(f"  tokens conhecidos: entrada {resumo['tokens_entrada']}, saída {resumo['tokens_saida']} "
          f"(incluem {resumo['tokens_raciocinio']} de raciocínio, que não são somados de novo), embeddings {resumo['tokens_embeddings']}")
    if resumo["uso_incerto"]:
        print(f"  [AVISO] Uso incerto: uma tentativa falhou, foi cancelada ou não informou o consumo. Os tokens acima são só o mínimo "
              f"conhecido; o programa reservou {resumo['tokens_comprometidos']} de {limites.max_tokens} no pior caso.")
    print(f"  tempo: {resumo['ms'] / 1000:.1f} s")
    valor = lab_orquestracao.estimar_valor(resumo, tarifa)
    if valor is not None:
        print(f"  valor estimado: {valor:.6f} na moeda da tarifa que você informou. É uma estimativa, não a fatura.")
    else:
        motivo = "o uso é incerto" if tarifa is not None else "nenhuma tarifa foi informada"
        print(f"  valor: não calculado ({motivo}). Tokens não são fatura.")


def executar(args: argparse.Namespace) -> int:
    if args.mostrar_plano:
        mostrar_plano(args)
        return lab_comum.CODIGO_OK
    exigir_opcoes_da_consulta(args)
    pergunta = args.pergunta.strip()
    if not pergunta:
        raise ErroLab("Informe uma pergunta não vazia em --pergunta.")
    if len(pergunta) > lab_geracao.LIMITE_DA_PERGUNTA:
        raise ErroLab(f"A pergunta tem mais de {lab_geracao.LIMITE_DA_PERGUNTA} caracteres. Resuma-a.")
    parametros = montar_parametros(args)
    acesso = lab_acesso.autorizar(PERFIS[args.perfil])
    tarifa = (lab_orquestracao.Tarifa(args.tarifa_entrada, args.tarifa_saida, args.tarifa_embeddings)
              if args.tarifa_entrada is not None else None)
    print(f"Pergunta: {pergunta}")
    print(f"Perfil do operador: {args.perfil} (escolhido em --perfil, não é autenticação do Entra ID) · classes: "
          f"{', '.join(acesso.classes)} · filtro: {acesso.filtro}")
    identidade = "identidade gerenciada" if args.identidade_gerenciada else "Azure CLI (az login)"
    print(f"Identidade: {identidade} · serviço de busca '{args.busca}', índice '{args.indice}' · deployments: geração "
          f"'{args.deployment_geracao}', contingência '{args.deployment_contingencia or 'não configurada'}', embeddings '{args.deployment}'")
    print("\nProgresso (só etapas e contagens; o texto do modelo só aparece depois da política):")
    servico = lab_orquestracao.criar_servico_coordenado(parametros, criar_credencial(args))
    resumo: dict[str, Any] = {}

    def progresso(evento: lab_orquestracao.EventoProgresso) -> None:
        if evento.tipo == lab_orquestracao.EVENTO_RESUMO:
            resumo.update(evento.dados)
        else:
            imprimir_evento(evento)

    try:
        resposta = consultar(servico, pergunta, acesso, progresso)
    except lab_chat.ErroChat as erro:
        print(f"\n[ERRO] {erro.mensagem} (código: {erro.codigo}; causa: {erro.causa})", file=sys.stderr)
        print("Nenhuma resposta foi apresentada.")
        mostrar_uso(resumo, parametros.limites, tarifa)
        return CODIGOS_DE_SAIDA.get(erro.codigo, lab_comum.CODIGO_INESPERADO)
    mostrar_resposta(resposta)
    mostrar_uso(resumo, parametros.limites, tarifa)
    print("\nLembrete: a resposta explica regras do produto; ela não confirma as coberturas de uma contratação.")
    return lab_comum.CODIGO_OK


def principal(argv: list[str] | None = None) -> int:
    lab_comum.configurar_saida()
    parser = lab_comum.criar_parser(__doc__, armazenamento=False, inventario=False)
    adicionar_argumentos(parser)
    args = parser.parse_args(argv)
    return lab_comum.executar_com_tratamento(executar, args, tradutor=lab_indexacao.traduzir_erro_indexacao)


if __name__ == "__main__":
    sys.exit(principal())
