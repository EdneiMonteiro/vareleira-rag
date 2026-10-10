"""Gerencia a ingestão do L200 no Azure AI Search e a compara com a do L100 (Desafios 02 e 03).

No L200, o serviço de busca faz o que os scripts do L100 faziam: um indexador lê os blobs do contêiner, um skillset divide o
texto (Text Split) e gera os embeddings, e uma projeção grava cada trecho em um índice separado. Este script cria, executa,
confere, compara e remove esses quatro objetos pela API REST do plano de dados, com a identidade do Azure CLI (az login) e
sem chaves. O índice do L100 nunca é alterado.

Cada etapa faz uma coisa. Por padrão, tudo SIMULA (só lê): nada é criado, executado nem apagado sem --executar.
    criar      índice, data source, skillset e indexador (o indexador nasce desabilitado: criar não executa nada)
    executar   executa o indexador (consome o modelo de embeddings); --aguardar espera o fim, com tempo limite
    conferir   estado dos objetos, execução (itens, falhas, erros) e campos preenchidos; somente leitura
    comparar   compara o índice do L200 com o do L100 nas seis perguntas de conferência; somente leitura
    remover    apaga só os quatro objetos do L200, nesta ordem: indexador, skillset, data source, índice

Um objeto que já existe com outra definição nunca é sobrescrito em silêncio: o plano mostra a diferença exata, e só
--substituir permite trocá-lo. A assinatura e o grupo de recursos nunca aparecem na tela: o ResourceId das definições
mostradas é redigido, e mensagens do serviço passam por uma redação de tokens, chaves e identificadores.

Exemplos:
    python scripts\\gerenciar_ingestao.py --etapa criar --busca <busca> --assinatura <assinatura> --grupo <grupo> --conta <conta> --modelos <modelos>
    python scripts\\gerenciar_ingestao.py --etapa criar --busca <busca> --assinatura <assinatura> --grupo <grupo> --conta <conta> --modelos <modelos> --executar
    python scripts\\gerenciar_ingestao.py --etapa executar --busca <busca> --executar --aguardar
    python scripts\\gerenciar_ingestao.py --etapa conferir --busca <busca>
    python scripts\\gerenciar_ingestao.py --etapa comparar --busca <busca> --modelos <modelos> --indice-referencia vareleira-lar-l100
    python scripts\\gerenciar_ingestao.py --etapa remover --busca <busca> --executar
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Mapping, Sequence

import lab_comum
import lab_indexacao
import lab_ingestao
from lab_comum import ErroLab, Verificacao
from lab_indexacao import DIVERGENTE, IGUAL, CRIAR
from lab_ingestao import AUSENTE, ALHEIO, FONTE, INDEXADOR, INDICE, REMOVER, ROTULOS, SKILLSET

LINHAS_DE_DIFERENCA = 8
LINHAS_DE_PROBLEMA = 5

_LINHAS_DE_QUALIDADE = (
    ("documento_id preenchido", "documento_id"),
    ("titulo_documento preenchido", "titulo_documento"),
    ("versao preenchida", "versao"),
    ("fonte preenchida", "fonte"),
    ("secao preenchida", "secao"),
    ("clausulas preenchidas", "clausulas"),
)


# --------------------------------------------------------------------------------------
# Utilitários de saída
# --------------------------------------------------------------------------------------

def _cliente(args: argparse.Namespace) -> lab_ingestao.ClienteBusca:
    return lab_ingestao.abrir_cliente(args.busca, args.tenant_id, args.versao_api)


def _cabecalho(args: argparse.Namespace, simula: bool, somente_leitura: bool = False) -> None:
    if somente_leitura:
        print("Modo: SOMENTE LEITURA (nenhuma alteração será feita)")
    else:
        print("Modo: " + ("SIMULAÇÃO (nenhuma alteração será feita)" if simula else "EXECUÇÃO"))
    print(f"Destino: serviço de busca '{args.busca}' (API REST {args.versao_api}), índice '{args.indice}'; "
          f"o índice de referência '{args.indice_referencia}' não é alterado")


def _avisar_executar_sem_efeito(args: argparse.Namespace) -> None:
    if args.executar:
        print(f"[AVISO] --executar não se aplica à etapa '{args.etapa}': ela só lê.")


def _percentual(valor: float | None) -> str:
    return "n/d" if valor is None else f"{valor:.0f}%"


def _mostrar_diferencas(diferencas: Sequence[str]) -> None:
    for diferenca in diferencas[:LINHAS_DE_DIFERENCA]:
        print(f"                 - {diferenca}")
    if len(diferencas) > LINHAS_DE_DIFERENCA:
        print(f"                 - ... e mais {len(diferencas) - LINHAS_DE_DIFERENCA} diferença(s)")


def _atuais(cliente: lab_ingestao.ClienteBusca, pares: Sequence[tuple[str, str]]) -> dict[tuple[str, str], dict[str, Any] | None]:
    return {(tipo, nome): cliente.obter(tipo, nome) for tipo, nome in pares}


# --------------------------------------------------------------------------------------
# Etapa criar
# --------------------------------------------------------------------------------------

def _resumo_do_objeto(acao: lab_ingestao.AcaoObjeto, p: lab_ingestao.Parametros) -> str:
    if acao.tipo == INDICE:
        campos = acao.definicao["fields"]
        return (f"{len(campos)} campos; chave com analisador keyword; busca vetorial (HNSW, cosseno, {p.dimensoes} dimensões)")
    if acao.tipo == FONTE:
        return (f"Blob Storage, contêiner '{p.container}', pasta '{p.prefixo}'; identidade gerenciada (ResourceId, sem chaves); "
                "exclusões: soft delete nativo do Blob")
    if acao.tipo == SKILLSET:
        return (f"Text Split (até {p.tamanho_maximo} caracteres, sobreposição de {p.sobreposicao}) + Azure OpenAI Embedding "
                f"('{p.deployment}', {p.modelo_embeddings}, {p.dimensoes} dimensões); projeção de índice: um documento por trecho")
    return "texto simples (.md); criado DESABILITADO: só executa pela etapa executar"


def _mostrar_plano_de_criacao(acoes: Sequence[lab_ingestao.AcaoObjeto], p: lab_ingestao.Parametros, args: argparse.Namespace) -> None:
    print("Plano:")
    for acao in acoes:
        rotulo = "substituir" if acao.estado == DIVERGENTE and args.substituir else acao.estado
        print(f"  [{rotulo:<10}] {ROTULOS[acao.tipo]} '{acao.nome}': {_resumo_do_objeto(acao, p)}")
        if acao.estado == DIVERGENTE:
            _mostrar_diferencas(acao.diferencas)
            print("                 " + ("<- será substituído (--substituir)" if args.substituir
                                          else "<- só será substituído com --substituir"))
    contagem = {estado: sum(1 for acao in acoes if acao.estado == estado) for estado in (CRIAR, IGUAL, DIVERGENTE)}
    print(f"  Total: {len(acoes)} objeto(s): {contagem[CRIAR]} a criar, {contagem[IGUAL]} iguais, {contagem[DIVERGENTE]} divergentes.")
    if args.mostrar_definicoes:
        print("Definições (redigidas) dos objetos que serão enviados:")
        for acao in acoes:
            if acao.estado != IGUAL:
                print(f"--- {ROTULOS[acao.tipo]} '{acao.nome}' ---")
                print(json.dumps(lab_ingestao.redigir_definicao(acao.definicao), ensure_ascii=False, indent=2))


def etapa_criar(args: argparse.Namespace) -> int:
    inventario = lab_comum.carregar_inventario(args.inventario)
    prefixo = args.prefixo or lab_ingestao.prefixo_do_inventario(inventario)
    parametros = lab_ingestao.Parametros(
        lab_ingestao.nomes_dos_objetos(args.indice), args.assinatura, args.grupo, args.conta, args.container, prefixo,
        args.modelos, args.deployment, args.modelo_embeddings, args.dimensoes, args.tamanho_maximo, args.sobreposicao)
    lab_ingestao.validar_parametros(parametros)
    _cabecalho(args, not args.executar)
    print(f"Origem: conta '{args.conta}', contêiner '{args.container}', pasta '{prefixo}' ({len(inventario.documentos)} "
          "documento(s) no inventário), lida pela identidade gerenciada do serviço de busca")
    print(f"Embeddings: deployment '{args.deployment}' ({args.modelo_embeddings}, {args.dimensoes} dimensões) do recurso "
          f"'{args.modelos}', chamado pela identidade gerenciada do serviço de busca")
    aviso = lab_comum.aviso_de_revisao(inventario)
    if aviso:
        print(f"[AVISO] {aviso}")

    cliente = _cliente(args)
    acoes = lab_ingestao.planejar_objetos(parametros, _atuais(cliente, parametros.nomes.em_ordem_de_criacao()))
    _mostrar_plano_de_criacao(acoes, parametros, args)

    if any(acao.estado == DIVERGENTE for acao in acoes) and not args.substituir:
        print("[PARADA] Há objeto(s) no serviço diferente(s) do definido. Nada foi alterado.")
        print("         Confira as diferenças acima. Para trocá-los de propósito: --executar --substituir.")
        return lab_comum.CODIGO_DIVERGENCIA
    if not args.executar:
        print("Antes de executar o indexador, confira (este script não altera permissões nem a conta de armazenamento):")
        print("  - a identidade gerenciada do serviço de busca (system-assigned) está habilitada;")
        print("  - ela tem 'Storage Blob Data Reader' no contêiner e 'Cognitive Services OpenAI User' no recurso de modelos;")
        print("  - a conta tem soft delete de blobs ativo e o versionamento de blobs desativado, que a detecção nativa de exclusão exige.")
        print("Simulação concluída. Para criar, repita o comando com --executar.")
        return lab_comum.CODIGO_OK

    criados = substituidos = 0
    for acao in acoes:
        if acao.estado == IGUAL:
            continue
        substituir = acao.estado == DIVERGENTE
        if substituir and not acao.proprio:
            print(f"[AVISO] {ROTULOS[acao.tipo]} '{acao.nome}' não traz o marcador do laboratório; está sendo substituído (--substituir).")
        cliente.gravar(acao.tipo, acao.nome, acao.definicao, etag=acao.etag if substituir else None)
        criados += not substituir
        substituidos += substituir
        print(f"[{'SUBSTITUÍDO' if substituir else 'CRIADO'}] {ROTULOS[acao.tipo]} '{acao.nome}'"
              + (" (desabilitado: não executa até a etapa executar)" if acao.tipo == INDEXADOR else "") + ".")
    if not criados and not substituidos:
        print("[IGUAL] Os quatro objetos já estão como o plano pede; nada a fazer.")
    else:
        print(f"Concluído: {criados} criado(s), {substituidos} substituído(s), "
              f"{len(acoes) - criados - substituidos} já igual(is). O indexador não foi executado.")
    if substituidos:
        print("Depois de substituir o skillset, a fonte ou o índice, reprocesse os blobs com --etapa executar --executar --reiniciar.")
    print(f"Próximo passo: python scripts\\gerenciar_ingestao.py --etapa executar --busca {args.busca} --indice {args.indice} "
          "--executar --aguardar")
    return lab_comum.CODIGO_OK


# --------------------------------------------------------------------------------------
# Etapa executar
# --------------------------------------------------------------------------------------

def mostrar_resumo(resumo: lab_ingestao.ResumoExecucao) -> None:
    print(f"Indexador: estado geral '{resumo.geral}'; última execução '{resumo.resultado or 'nenhuma'}'")
    if resumo.inicio:
        print(f"  Início: {resumo.inicio} · fim: {resumo.fim or 'em andamento'}")
    print(f"  Itens processados: {resumo.processados} · com falha: {resumo.falhas}")
    print(f"  Erros: {len(resumo.erros)} · avisos: {len(resumo.avisos)} · execuções no histórico: {resumo.historico}")
    if resumo.mensagem:
        print(f"  Mensagem do serviço: {resumo.mensagem[:240]}")
    for rotulo, itens in (("erro", resumo.erros), ("aviso", resumo.avisos)):
        for item in itens[:LINHAS_DE_PROBLEMA]:
            print(f"  - {rotulo}: {lab_ingestao.descrever_problema(item)}")
        if len(itens) > LINHAS_DE_PROBLEMA:
            print(f"  - ... e mais {len(itens) - LINHAS_DE_PROBLEMA} {rotulo}(s)")


def etapa_executar(args: argparse.Namespace) -> int:
    nomes = lab_ingestao.nomes_dos_objetos(args.indice)
    cliente = _cliente(args)
    _cabecalho(args, not args.executar)
    indexador = cliente.obter(INDEXADOR, nomes.indexador)
    if indexador is None:
        raise ErroLab(f"O indexador '{nomes.indexador}' não existe no serviço '{args.busca}'. Crie os objetos com "
                      "--etapa criar --executar.", lab_comum.CODIGO_DIVERGENCIA)
    if not lab_ingestao.objeto_do_laboratorio(indexador):
        raise ErroLab(f"O indexador '{nomes.indexador}' não traz o marcador do laboratório: este script não o executa.",
                      lab_comum.CODIGO_DIVERGENCIA)
    anterior = lab_ingestao.resumir_status(cliente.status_indexador(nomes.indexador))
    desabilitado = bool(indexador.get("disabled"))
    print("Plano:")
    if args.reiniciar:
        print(f"  [reiniciar ] indexador '{nomes.indexador}': apaga o rastreamento de mudanças; todos os blobs serão "
              "reprocessados e os embeddings, calculados de novo")
    if desabilitado:
        print(f"  [habilitar ] indexador '{nomes.indexador}' está desabilitado, como a etapa criar o deixa: atualizá-lo como "
              "habilitado inicia a execução (comportamento documentado do serviço)")
    else:
        print(f"  [executar  ] indexador '{nomes.indexador}': execução sob demanda")
    print("  Cada execução chama o deployment de embeddings para cada trecho novo ou alterado (consumo de tokens).")
    print(f"Última execução conhecida: {anterior.resultado or 'nenhuma'}"
          + (f", {anterior.processados} item(ns) processado(s)" if anterior.resultado else "") + ".")
    if not args.executar:
        print("Simulação concluída. Para executar, repita o comando com --executar.")
        return lab_comum.CODIGO_OK

    if args.reiniciar:
        cliente.reiniciar_indexador(nomes.indexador)
        print(f"[REINICIADO] Rastreamento do indexador '{nomes.indexador}' apagado.")
    if desabilitado:
        definicao = {nome: valor for nome, valor in indexador.items() if not nome.startswith("@odata")}
        definicao["disabled"] = False
        cliente.gravar(INDEXADOR, nomes.indexador, definicao, etag=indexador.get("@odata.etag"))
        print(f"[HABILITADO] Indexador '{nomes.indexador}' habilitado; a execução foi iniciada pelo serviço.")
    else:
        try:
            cliente.executar_indexador(nomes.indexador)
            print(f"[EXECUTANDO] Execução do indexador '{nomes.indexador}' iniciada.")
        except lab_ingestao.ErroServicoBusca as erro:
            if erro.status != 409:
                raise
            print(f"[EM EXECUÇÃO] O indexador '{nomes.indexador}' já estava em execução; a execução em andamento será acompanhada.")

    if args.aguardar is None:
        print("Acompanhe o resultado com --etapa conferir (ou repita este comando com --aguardar).")
        return lab_comum.CODIGO_OK
    print(f"Aguardando o fim da execução por até {args.aguardar} s (consulta a cada {lab_ingestao.INTERVALO_SEGUNDOS} s)...")
    resumo = lab_ingestao.aguardar_execucao(cliente, nomes.indexador, anterior.inicio, args.aguardar)
    if resumo is None:
        print(f"[TEMPO ESGOTADO] A execução não terminou em {args.aguardar} s. Ela continua no serviço: acompanhe com --etapa conferir.")
        return lab_comum.CODIGO_ACESSO
    mostrar_resumo(resumo)
    if resumo.ok and not resumo.processados and anterior.resultado is None:
        print("[ATENÇÃO] A primeira execução terminou sem processar nenhum blob. Confira a pasta lida (--prefixo ou a do "
              "inventário), o contêiner e se os documentos foram enviados pelo Desafio 01.")
        return lab_comum.CODIGO_DIVERGENCIA
    if resumo.ok:
        print("Execução concluída sem falhas. Confira o índice com --etapa conferir.")
        return lab_comum.CODIGO_OK
    print("Execução concluída com falhas ou erros. Nada foi desfeito: corrija a causa e repita (o indexador retoma o que falta).")
    return lab_comum.CODIGO_DIVERGENCIA


# --------------------------------------------------------------------------------------
# Etapa conferir
# --------------------------------------------------------------------------------------

def etapa_conferir(args: argparse.Namespace) -> int:
    nomes = lab_ingestao.nomes_dos_objetos(args.indice)
    inventario = lab_comum.carregar_inventario(args.inventario)
    cliente = _cliente(args)
    _cabecalho(args, False, somente_leitura=True)
    _avisar_executar_sem_efeito(args)
    resultados: list[Verificacao] = []

    def registrar(resultado: Verificacao) -> Verificacao:
        resultados.append(resultado)
        print(f"[{'OK' if resultado.ok else 'FALHA':<5}] {resultado.nome}: {resultado.detalhe}")
        return resultado

    atuais = _atuais(cliente, nomes.em_ordem_de_criacao())
    estados = []
    for tipo, nome in nomes.em_ordem_de_criacao():
        atual = atuais[(tipo, nome)]
        estados.append(f"{ROTULOS[tipo]} {'ausente' if atual is None else 'presente' if lab_ingestao.objeto_do_laboratorio(atual) else 'sem o marcador do laboratório'}")
    existem = all(atual is not None and lab_ingestao.objeto_do_laboratorio(atual) for atual in atuais.values())
    registrar(Verificacao("Objetos do pipeline", existem, "; ".join(estados)))
    fonte = atuais[(FONTE, nomes.fonte)]
    if fonte is not None:
        politica = (fonte.get("dataDeletionDetectionPolicy") or {}).get("@odata.type")
        registrar(Verificacao(
            "Detecção de exclusão", politica == lab_ingestao.POLITICA_DE_EXCLUSAO,
            "soft delete nativo do Blob ativo no data source (blobs apagados saem do índice na execução seguinte)"
            if politica == lab_ingestao.POLITICA_DE_EXCLUSAO else
            "o data source não tem a política de exclusão nativa: trechos de blobs apagados ficariam órfãos no índice. "
            "Ela precisa existir desde a primeira execução; se não, crie os objetos de novo (--etapa remover e --etapa criar)"))

    if all(getattr(args, opcao) for opcao in ("assinatura", "grupo", "conta", "modelos")) and existem:
        prefixo = args.prefixo or lab_ingestao.prefixo_do_inventario(inventario)
        parametros = lab_ingestao.Parametros(
            nomes, args.assinatura, args.grupo, args.conta, args.container, prefixo, args.modelos, args.deployment,
            args.modelo_embeddings, args.dimensoes, args.tamanho_maximo, args.sobreposicao)
        lab_ingestao.validar_parametros(parametros)
        diferentes = [acao for acao in lab_ingestao.planejar_objetos(parametros, atuais) if acao.estado != IGUAL]
        if diferentes:
            registrar(Verificacao("Definições dos objetos", False, f"{len(diferentes)} objeto(s) diferente(s) do definido"))
            for acao in diferentes:
                print(f"         {ROTULOS[acao.tipo]} '{acao.nome}':")
                _mostrar_diferencas(acao.diferencas)
        else:
            registrar(Verificacao("Definições dos objetos", True, "os quatro objetos são os definidos por este script"))
    else:
        print("[INFO ] Definições não comparadas: informe também --assinatura, --grupo, --conta e --modelos "
              "(com os quatro objetos presentes).")

    indexador = atuais[(INDEXADOR, nomes.indexador)]
    if indexador is not None:
        resumo = lab_ingestao.resumir_status(cliente.status_indexador(nomes.indexador))
        detalhe = (f"resultado '{resumo.resultado or 'nenhuma execução'}'; itens processados {resumo.processados}; itens com falha "
                   f"{resumo.falhas}; erros {len(resumo.erros)}; avisos {len(resumo.avisos)}; estado geral '{resumo.geral}'; "
                   f"indexador {'desabilitado' if indexador.get('disabled') else 'habilitado'}")
        registrar(Verificacao("Indexador: última execução", resumo.ok, detalhe))
        if resumo.resultado is None:
            print("         Nenhuma execução registrada: rode --etapa executar --executar.")
        elif resumo.ok and not resumo.processados:
            print("         Nenhum item processado nesta execução: sem mudanças desde a anterior (o que vale é o índice, conferido abaixo).")
        for rotulo, itens in (("erro", resumo.erros), ("aviso", resumo.avisos)):
            for item in itens[:LINHAS_DE_PROBLEMA]:
                print(f"         {rotulo}: {lab_ingestao.descrever_problema(item)}")
        if resumo.mensagem:
            print(f"         mensagem do serviço: {resumo.mensagem[:240]}")

    definicao_do_indice = atuais[(INDICE, nomes.indice)]
    if definicao_do_indice is None:
        registrar(Verificacao("Trechos do índice", False, f"o índice '{nomes.indice}' não existe"))
    else:
        incompativeis = lab_ingestao.diferencas_de_compatibilidade(definicao_do_indice, args.dimensoes)
        registrar(Verificacao("Compatibilidade com o recuperador do L100", not incompativeis,
                              "; ".join(incompativeis) or "campos de resultado e campo vetorial 'vetor' presentes"))
        presentes = {campo["name"] for campo in definicao_do_indice.get("fields", [])}
        campos = [campo for campo in (*lab_ingestao.CAMPOS_DA_LISTAGEM, *lab_ingestao.CAMPOS_EXTRAS_DO_L200) if campo in presentes]
        qualidade = lab_ingestao.analisar_trechos(lab_ingestao.listar_trechos(cliente, nomes.indice, campos), inventario, args.container)
        problemas = lab_ingestao.problemas_de_completude(qualidade)
        por_documento = ", ".join(f"{documento} {quantidade}" for documento, quantidade in sorted(qualidade.por_documento.items()))
        registrar(Verificacao("Trechos do índice", not problemas,
                              f"{qualidade.trechos} trecho(s) em {len(qualidade.por_documento)} de {len(inventario.documentos)} "
                              f"documento(s) do inventário ({por_documento or 'nenhum'})"
                              + ("; " + "; ".join(problemas) if problemas else "")))
        preenchidos = ", ".join(f"{campo} {_percentual(qualidade.percentual(campo))}" for campo in lab_ingestao.CAMPOS_PREENCHIDOS
                                if qualidade.percentual(campo) is not None)
        print(f"[INFO ] Campos preenchidos pelo pipeline (parte dos trechos): {preenchidos or 'nenhum'}.")
        if qualidade.trechos and qualidade.vazios.get("documento_id") == qualidade.trechos:
            print("[DICA ] Nenhum trecho trouxe os metadados do blob (documento_id, versao, produto, sha256, sintetico). Confira se "
                  "os blobs têm esses metadados (verificar_documentos.py, Desafio 01): a projeção os lê em /document/<nome do metadado>.")
        print(f"[INFO ] secao {_percentual(qualidade.percentual('secao'))} e clausulas {_percentual(qualidade.percentual('clausulas'))}: "
              "o Text Split não gera seções nem cláusulas; o campo vetorial 'vetor' não é recuperável, então a etapa comparar é "
              "que exercita a busca vetorial.")

    if all(resultado.ok for resultado in resultados):
        print("Conferência aprovada.")
        return lab_comum.CODIGO_OK
    print("Conferência reprovada. Corrija as falhas e repita. Nada foi alterado por este script.")
    return lab_comum.CODIGO_DIVERGENCIA


# --------------------------------------------------------------------------------------
# Etapa comparar
# --------------------------------------------------------------------------------------

def _resultados_do_indice(args: argparse.Namespace, indice: Any, pergunta: str, vetor: Sequence[float] | None) -> list[dict[str, Any]]:
    return indice.consultar(pergunta if args.modo != "vetorial" else None, vetor if args.modo != "texto" else None, args.k)


def _linha_de_quantidade(rotulo: str, valores: Sequence[str]) -> None:
    print(f"  {rotulo:<36}" + "".join(f"{valor:>10}" for valor in valores))


def _mostrar_pergunta(pergunta: lab_indexacao.PerguntaDeConferencia, por_indice: Mapping[str, list[dict[str, Any]]],
                      nomes: Mapping[str, str], inventario: lab_comum.Inventario, container: str, k: int) -> dict[str, int | None]:
    print(f"\n{pergunta.id}. {pergunta.pergunta}")
    posicoes: dict[str, int | None] = {}
    fontes: dict[str, set[str]] = {}
    for rotulo, resultados in por_indice.items():
        posicao = lab_indexacao.posicao_do_esperado(pergunta, resultados)
        posicoes[rotulo] = posicao
        rotulos_das_fontes = [lab_ingestao.rotulo_da_fonte(item.get("fonte"), inventario, container) for item in resultados]
        fontes[rotulo] = set(rotulos_das_fontes)
        situacao = f"fato esperado na posição {posicao}" if posicao else f"fato esperado ausente dos {k} primeiros"
        print(f"  {rotulo} ({nomes[rotulo]}): {situacao}")
        for ordem, (item, fonte) in enumerate(zip(resultados, rotulos_das_fontes), start=1):
            print(f"    {ordem}. [{item.get('id', '?')}] {fonte} · {lab_ingestao.resumir_trecho(item.get('conteudo'))}")
    comuns = sorted((fontes["L100"] & fontes["L200"]) - {lab_ingestao.FONTE_FORA_DO_INVENTARIO})
    print(f"  Fontes em comum entre os {k} primeiros: {len(comuns)} ({', '.join(comuns) or 'nenhuma'})")
    return posicoes


def etapa_comparar(args: argparse.Namespace) -> int:
    inventario = lab_comum.carregar_e_validar(args.inventario)
    perguntas = lab_indexacao.carregar_perguntas(lab_indexacao.PERGUNTAS_PADRAO)
    lab_ingestao.validar_perguntas_fixas(perguntas, inventario)
    cliente = _cliente(args)
    _cabecalho(args, False, somente_leitura=True)
    _avisar_executar_sem_efeito(args)
    nomes = {"L100": args.indice_referencia, "L200": args.indice}
    print(f"Perguntas: as {len(perguntas)} de conferência do L100 ({', '.join(lab_ingestao.PERGUNTAS_FIXAS)}), modo '{args.modo}', "
          f"{args.k} resultado(s) por pergunta. Não são o conjunto de avaliação do Desafio 06.")
    print("Consumo: " + ("nenhum embedding (modo texto)." if args.modo == "texto" else
                         f"um pedido de embeddings com as {len(perguntas)} perguntas, no deployment '{args.deployment}' (poucos tokens)."))

    qualidades: dict[str, lab_ingestao.Qualidade] = {}
    for rotulo, nome in nomes.items():
        definicao = cliente.obter(INDICE, nome)
        if definicao is None:
            raise ErroLab(f"O índice {rotulo} '{nome}' não existe no serviço '{args.busca}'. "
                          + ("Crie-o e execute o indexador (--etapa criar e --etapa executar)." if rotulo == "L200"
                             else "Reindexe o L100 com indexar_documentos.py --executar."), lab_comum.CODIGO_DIVERGENCIA)
        incompativeis = lab_ingestao.diferencas_de_compatibilidade(definicao, args.dimensoes)
        if incompativeis:
            print(f"[PARADA] O índice {rotulo} '{nome}' não é compatível com o recuperador do L100: {'; '.join(incompativeis)}.")
            return lab_comum.CODIGO_DIVERGENCIA
        presentes = {campo["name"] for campo in definicao.get("fields", [])}
        campos = [campo for campo in (*lab_ingestao.CAMPOS_DA_LISTAGEM, *lab_ingestao.CAMPOS_EXTRAS_DO_L200) if campo in presentes]
        qualidades[rotulo] = lab_ingestao.analisar_trechos(lab_ingestao.listar_trechos(cliente, nome, campos), inventario, args.container)
    if not qualidades["L200"].trechos:
        print(f"[PARADA] O índice L200 '{args.indice}' está vazio. Execute o indexador (--etapa executar --executar --aguardar).")
        return lab_comum.CODIGO_DIVERGENCIA

    l100, l200 = qualidades["L100"], qualidades["L200"]
    print("\nTamanho (o que cada caminho produziu)")
    _linha_de_quantidade("", ["L100", "L200"])
    _linha_de_quantidade("trechos", [str(l100.trechos), str(l200.trechos)])
    _linha_de_quantidade("documentos com trechos", [str(len(l100.por_documento)), str(len(l200.por_documento))])
    _linha_de_quantidade("tamanho médio do trecho (caracteres)", [str(l100.tamanho_medio), str(l200.tamanho_medio)])
    _linha_de_quantidade("maior trecho (caracteres)", [str(l100.tamanho_maximo), str(l200.tamanho_maximo)])
    so_l100, so_l200 = sorted(set(l100.por_documento) - set(l200.por_documento)), sorted(set(l200.por_documento) - set(l100.por_documento))
    print(f"  Documentos só no L100: {', '.join(so_l100) or 'nenhum'} · só no L200: {', '.join(so_l200) or 'nenhum'}")
    comuns = sorted(set(l100.fontes) & set(l200.fontes))
    print(f"  Fontes em comum: {len(comuns)} de {len(set(l100.fontes) | set(l200.fontes))} ({', '.join(comuns) or 'nenhuma'}); "
          "só as do inventário são mostradas")

    print("\nQualidade dos metadados e do texto (parte dos trechos)")
    _linha_de_quantidade("", ["L100", "L200"])
    for rotulo, campo in _LINHAS_DE_QUALIDADE:
        _linha_de_quantidade(rotulo, [_percentual(l100.percentual(campo)), _percentual(l200.percentual(campo))])
    for rotulo, atributo in (("trecho começa com cabeçalho Markdown", "iniciam_com_cabecalho"), ("trecho contém cabeçalho Markdown", "contem_cabecalho")):
        _linha_de_quantidade(rotulo, [_percentual(100.0 * getattr(q, atributo) / q.trechos) for q in (l100, l200)])
    print("  O L200 identifica o documento por metadados do blob e a fonte pelo endereço do blob (mostrada só como caminho no inventário); "
          "o título é o nome do arquivo.")

    vetores: list[Sequence[float]] | list[None] = [None] * len(perguntas)
    if args.modo != "texto":
        cliente_embeddings = lab_indexacao.criar_cliente_embeddings(args.modelos, args.deployment, args.dimensoes, args.tenant_id)
        vetores = cliente_embeddings.gerar([pergunta.pergunta for pergunta in perguntas]).vetores
    print(f"\nPerguntas de conferência (os {args.k} primeiros trechos de cada índice)")
    indices = {rotulo: lab_indexacao.abrir_indice(args.busca, nome, args.tenant_id) for rotulo, nome in nomes.items()}
    acertos = {"L100": 0, "L200": 0}
    for pergunta, vetor in zip(perguntas, vetores):
        por_indice = {rotulo: _resultados_do_indice(args, indice, pergunta.pergunta, vetor) for rotulo, indice in indices.items()}
        for rotulo, posicao in _mostrar_pergunta(pergunta, por_indice, nomes, inventario, args.container, args.k).items():
            acertos[rotulo] += posicao is not None
    print(f"\nResumo: o fato esperado apareceu entre os {args.k} primeiros em {acertos['L100']} de {len(perguntas)} perguntas no L100 "
          f"e em {acertos['L200']} no L200.")
    print("Esta comparação descreve diferenças e não aprova nem reprova o L200: o resultado do L100 não é meta, e trechos de "
          "tamanho, início e metadados diferentes são esperados. A decisão cabe a quem avalia o custo, a operação e a recuperação.")
    return lab_comum.CODIGO_OK


# --------------------------------------------------------------------------------------
# Etapa remover
# --------------------------------------------------------------------------------------

def etapa_remover(args: argparse.Namespace) -> int:
    nomes = lab_ingestao.nomes_dos_objetos(args.indice)
    cliente = _cliente(args)
    _cabecalho(args, not args.executar)
    acoes = lab_ingestao.planejar_remocao(nomes, _atuais(cliente, nomes.em_ordem_de_remocao()))
    print("Plano (nesta ordem: quem depende de outro objeto sai primeiro):")
    for acao in acoes:
        rotulo = {REMOVER: "remover", AUSENTE: "ausente", ALHEIO: "alheio"}[acao.estado]
        dica = {REMOVER: "", AUSENTE: " (não existe; nada a fazer)",
                ALHEIO: " (não traz o marcador do laboratório; não será apagado)"}[acao.estado]
        print(f"  [{rotulo:<10}] {ROTULOS[acao.tipo]} '{acao.nome}'{dica}")
    print(f"Só estes quatro objetos são considerados. O índice '{args.indice_referencia}', a conta de armazenamento, o recurso de "
          "modelos, o serviço de busca e as permissões não são alterados.")
    if any(acao.estado == ALHEIO for acao in acoes):
        print("[PARADA] Há objeto(s) com estes nomes que o laboratório não criou. Nada foi apagado: confira no portal do Azure.")
        return lab_comum.CODIGO_DIVERGENCIA
    a_remover = [acao for acao in acoes if acao.estado == REMOVER]
    if not a_remover:
        print("[IGUAL] Nenhum dos objetos existe; nada a remover.")
        return lab_comum.CODIGO_OK
    if not args.executar:
        print("Efeito: remover o índice apaga os trechos; recriá-los exige executar o indexador de novo (consumo de embeddings).")
        print("Simulação concluída. Para remover, repita o comando com --executar.")
        return lab_comum.CODIGO_OK
    for acao in a_remover:
        cliente.apagar(acao.tipo, acao.nome, acao.etag)
        print(f"[REMOVIDO] {ROTULOS[acao.tipo]} '{acao.nome}'.")
    print(f"Concluído: {len(a_remover)} objeto(s) removido(s).")
    return lab_comum.CODIGO_OK


# --------------------------------------------------------------------------------------
# Entrada
# --------------------------------------------------------------------------------------

_ETAPAS = {"criar": etapa_criar, "executar": etapa_executar, "conferir": etapa_conferir, "comparar": etapa_comparar,
           "remover": etapa_remover}


def executar(args: argparse.Namespace) -> int:
    lab_ingestao.exigir_opcoes(args)
    lab_ingestao.validar_combinacoes(args)
    return _ETAPAS[args.etapa](args)


def criar_parser() -> lab_comum.ParserLab:
    parser = lab_comum.criar_parser(__doc__, armazenamento=False)
    parser.add_argument("--etapa", required=True, choices=lab_ingestao.ETAPAS,
                        help="criar, executar, conferir, comparar ou remover (veja a descrição acima).")
    parser.add_argument("--busca", required=True, type=lab_indexacao.validar_busca,
                        help="Nome do serviço de busca (saída nomeBusca da implantação).")
    parser.add_argument("--indice", default=lab_ingestao.INDICE_PADRAO, type=lab_ingestao.validar_indice_l200,
                        help=f"Índice do L200; dele derivam o data source, o skillset e o indexador (padrão: {lab_ingestao.INDICE_PADRAO}).")
    parser.add_argument("--indice-referencia", default=lab_ingestao.INDICE_REFERENCIA_PADRAO, type=lab_indexacao.validar_indice,
                        help=f"Índice do L100 usado só na comparação, nunca alterado (padrão: {lab_ingestao.INDICE_REFERENCIA_PADRAO}).")
    parser.add_argument("--assinatura", default=None, type=lab_ingestao.validar_assinatura,
                        help="ID da assinatura Azure da conta de armazenamento (etapa criar). Forma o ResourceId; não é gravado em arquivo.")
    parser.add_argument("--grupo", default=None, type=lab_ingestao.validar_grupo,
                        help="Grupo de recursos da conta de armazenamento (etapa criar).")
    parser.add_argument("--conta", default=None, type=lab_comum.validar_conta,
                        help="Conta de armazenamento com os documentos (saída nomeConta da implantação; etapa criar).")
    parser.add_argument("--container", default=lab_comum.CONTAINER_PADRAO, type=lab_comum.validar_container,
                        help=f"Contêiner de blobs (padrão: {lab_comum.CONTAINER_PADRAO}).")
    parser.add_argument("--prefixo", default=None, type=lab_ingestao.validar_prefixo_blob,
                        help="Pasta do contêiner que o indexador lê (padrão: a pasta comum dos blobs do inventário).")
    parser.add_argument("--modelos", default=None, type=lab_indexacao.validar_modelos,
                        help="Recurso de modelos (saída nomeModelos da implantação; etapas criar e comparar).")
    parser.add_argument("--deployment", default=lab_indexacao.DEPLOYMENT_PADRAO, type=lab_indexacao.validar_deployment,
                        help=f"Deployment de embeddings, não o modelo (padrão: {lab_indexacao.DEPLOYMENT_PADRAO}).")
    parser.add_argument("--modelo-embeddings", default=lab_ingestao.MODELO_EMBEDDINGS_PADRAO, type=lab_ingestao.validar_modelo_embeddings,
                        help=f"Modelo do deployment, exigido pela habilidade (padrão: {lab_ingestao.MODELO_EMBEDDINGS_PADRAO}).")
    parser.add_argument("--dimensoes", default=lab_indexacao.DIMENSOES_PADRAO, type=lab_indexacao.validar_dimensoes,
                        help=f"Dimensões dos vetores (padrão: {lab_indexacao.DIMENSOES_PADRAO}).")
    lab_indexacao.adicionar_argumento_tamanho(parser)
    parser.add_argument("--sobreposicao", default=lab_ingestao.SOBREPOSICAO_PADRAO, type=lab_ingestao.validar_sobreposicao,
                        help=f"Caracteres repetidos entre trechos seguidos (padrão: {lab_ingestao.SOBREPOSICAO_PADRAO}).")
    parser.add_argument("--executar", action="store_true",
                        help="Faz a alteração (criar, executar o indexador ou remover). Sem esta opção, o script só simula.")
    parser.add_argument("--substituir", action="store_true",
                        help="Permite trocar um objeto existente que difere da definição (etapa criar).")
    parser.add_argument("--reiniciar", action="store_true",
                        help="Apaga o rastreamento do indexador antes de executar: reprocessa todos os blobs (etapa executar).")
    parser.add_argument("--aguardar", nargs="?", const=lab_ingestao.ESPERA_PADRAO_SEGUNDOS, default=None, type=lab_ingestao.validar_espera,
                        help=f"Espera o fim da execução do indexador, por até N segundos (padrão sem valor: "
                             f"{lab_ingestao.ESPERA_PADRAO_SEGUNDOS}; máximo {lab_ingestao.ESPERA_MAXIMA_SEGUNDOS}).")
    parser.add_argument("--modo", choices=lab_indexacao.MODOS_DE_BUSCA, default="vetorial",
                        help="Busca usada na comparação: vetorial (padrão), texto ou hibrida.")
    parser.add_argument("--k", default=3, type=lab_indexacao.validar_k,
                        help="Quantos trechos examinar por pergunta na comparação (padrão: 3).")
    parser.add_argument("--mostrar-definicoes", action="store_true",
                        help="Mostra, redigidas, as definições JSON dos objetos que a etapa criar enviaria.")
    parser.add_argument("--versao-api", choices=lab_ingestao.VERSOES_API, default=lab_ingestao.VERSAO_API,
                        help=f"Versão estável da API REST do serviço de busca (padrão: {lab_ingestao.VERSAO_API}, que documenta a "
                             "exclusão nativa do Blob).")
    return parser


def principal(argv: list[str] | None = None) -> int:
    lab_comum.configurar_saida()
    args = criar_parser().parse_args(argv)
    return lab_comum.executar_com_tratamento(executar, args, tradutor=lab_ingestao.traduzir_erro_ingestao)


if __name__ == "__main__":
    sys.exit(principal())
