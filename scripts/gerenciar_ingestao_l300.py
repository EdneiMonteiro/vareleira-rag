"""Gerencia a ingestão do L300 (Desafio 02): manifesto de permissões, cópias classificadas e pipeline com o campo de acesso.

Esta ferramenta valida o manifesto de permissões documentais, envia as cópias classificadas ao Blob Storage e cria, executa, confere
e remove o pipeline gerenciado do Azure AI Search do L300, com a classe de acesso (campo `acesso`) em cada trecho. Tudo é separado do
L100 e do L200: contêiner 'base-documental-l300', pasta 'vareleira-lar-l300', índice 'vareleira-lar-l300' e objetos de busca com o
marcador 'vareleira-rag:l300'. Ela nunca lê nem altera o contêiner ou os índices dos níveis anteriores. O manifesto é
dados\\l300\\permissoes-documentais.json e rege só o que esta ferramenta envia: sem classe de acesso, um documento é negado, e tudo é
conferido antes de qualquer acesso ao Azure. O indexador lê a pasta inteira do L300 e o filtro do chat autoriza classes (o campo
`acesso`), não IDs do manifesto: por isso carregar avisa sobre blobs fora do manifesto e conferir reprova os trechos deles.

Por padrão, tudo SIMULA (só lê): nada é enviado, excluído, criado, executado nem apagado sem --executar.
    validar    confere o manifesto e os arquivos, só no seu computador (sem rede e sem Azure)
    carregar   envia ao contêiner do L300 as cópias do manifesto, com os metadados de acesso (--documento escolhe quais)
    excluir    exclusão reversível (soft delete) de um documento operacional do L300 (--documento obrigatório)
    restaurar  restaura um documento excluído e, se o conteúdo confere com o manifesto, reaplica os metadados (--documento obrigatório)
    criar      índice, data source, skillset e indexador do L300 (indexador DESABILITADO, em ambiente privado e sem agenda)
    executar   executa o indexador (consome o modelo de embeddings); --aguardar espera o fim, com tempo limite
    conferir   estado dos objetos, da execução e da classe de acesso de cada trecho; somente leitura
    remover    apaga só os quatro objetos de busca do L300 (os blobs não são apagados)

Só os documentos de origem L300 (o material operacional) podem ser excluídos e restaurados; as cópias dos documentos do L100 ficam
protegidas. Um objeto de busca que já existe sem o marcador do L300 nunca é substituído nem apagado, nem com --substituir. Com
--identidade-gerenciada, a ferramenta usa a identidade gerenciada do ambiente onde roda (para operar dentro da rede privada); sem
ela, usa a sessão do Azure CLI (az login). Nenhuma chave é usada.

Exemplos:
    python scripts\\gerenciar_ingestao_l300.py --etapa validar
    python scripts\\gerenciar_ingestao_l300.py --etapa carregar --conta <conta>
    python scripts\\gerenciar_ingestao_l300.py --etapa carregar --conta <conta> --executar
    python scripts\\gerenciar_ingestao_l300.py --etapa criar --busca <busca> --assinatura <assinatura> --grupo <grupo> --conta <conta> --modelos <modelos> --executar
    python scripts\\gerenciar_ingestao_l300.py --etapa executar --busca <busca> --executar --aguardar
    python scripts\\gerenciar_ingestao_l300.py --etapa conferir --busca <busca>
    python scripts\\gerenciar_ingestao_l300.py --etapa excluir --conta <conta> --documento VLAR-OP-ATD-1.0 --executar
    python scripts\\gerenciar_ingestao_l300.py --etapa restaurar --conta <conta> --documento VLAR-OP-ATD-1.0 --executar
    python scripts\\gerenciar_ingestao_l300.py --etapa remover --busca <busca> --executar
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

import gerenciar_ingestao as ingestao_l200
import lab_acesso
import lab_comum
import lab_indexacao
import lab_ingestao
import lab_ingestao_l300 as l300
from lab_comum import ErroLab, Verificacao

ETAPAS = ("validar", "carregar", "excluir", "restaurar", "criar", "executar", "conferir", "remover")
LINHAS_DE_DIFERENCA = 8
LINHAS_DE_PROBLEMA = 5

# O que cada etapa exige informar (--opcao). `remover`, por exemplo, não precisa saber de conta, assinatura nem modelos.
_OPCOES_DAS_ETAPAS = {
    "validar": (),
    "carregar": ("conta",),
    "excluir": ("conta", "documentos"),
    "restaurar": ("conta", "documentos"),
    "criar": ("busca", "assinatura", "grupo", "conta", "modelos"),
    "executar": ("busca",),
    "conferir": ("busca",),
    "remover": ("busca",),
}
_AJUDA_DAS_OPCOES = {
    "busca": "nome do serviço de busca (saída nomeBusca da implantação)",
    "assinatura": "ID da assinatura Azure, um GUID ('az account show --query id -o tsv')",
    "grupo": "nome do grupo de recursos da conta de armazenamento",
    "conta": "nome da conta de armazenamento do L300",
    "modelos": "nome do recurso de modelos (saída nomeModelos da implantação)",
    "documentos": "ID de um documento do manifesto, como VLAR-OP-ATD-1.0",
}
# Opções que só valem em certas etapas: usá-las em outra seria um engano, e o engano é recusado antes de qualquer acesso.
_OPCOES_POR_ETAPA = {
    "documentos": ("carregar", "excluir", "restaurar"),
    "substituir_divergentes": ("carregar",),
    "substituir": ("criar",),
    "mostrar_definicoes": ("criar",),
    "intervalo": ("criar",),
    "reiniciar": ("executar",),
    "aguardar": ("executar",),
    "ausentes": ("conferir",),
    "privado": ("criar", "conferir"),
    "identidade_gerenciada": ("carregar", "excluir", "restaurar", "criar", "executar", "conferir", "remover"),
    "client_id": ("carregar", "excluir", "restaurar", "criar", "executar", "conferir", "remover"),
}
_ROTULOS_DO_PLANO = {
    l300.CRIAR: "criar", l300.IGUAL: "igual", l300.DIVERGENTE: "divergente", l300.METADADOS: "metadados",
    l300.EXCLUIR: "excluir", l300.JA_EXCLUIDO: "excluído", l300.RESTAURAR: "restaurar", l300.ATIVO: "ativo",
    l300.AUSENTE: "ausente",
}


# --------------------------------------------------------------------------------------
# Opções
# --------------------------------------------------------------------------------------

def exigir_opcoes(args: argparse.Namespace) -> None:
    faltam = [opcao for opcao in _OPCOES_DAS_ETAPAS[args.etapa] if not getattr(args, opcao, None)]
    if faltam:
        nomes = [("--documento" if opcao == "documentos" else "--" + opcao) for opcao in faltam]
        detalhes = "; ".join(f"{nome}: {_AJUDA_DAS_OPCOES[opcao]}" for nome, opcao in zip(nomes, faltam))
        raise ErroLab(f"A etapa '{args.etapa}' exige informar {', '.join(nomes)} ({detalhes}).")


def validar_combinacoes(args: argparse.Namespace) -> None:
    """Confere o que depende de mais de uma opção. Roda antes de qualquer acesso ao Azure."""
    for opcao, etapas in _OPCOES_POR_ETAPA.items():
        if getattr(args, opcao, None) not in (None, False) and args.etapa not in etapas:
            nome = "--documento" if opcao == "documentos" else "--ausente" if opcao == "ausentes" else "--" + opcao.replace("_", "-")
            raise ErroLab(f"A opção {nome} só vale na etapa {' ou '.join(etapas)}, não na etapa '{args.etapa}'.")
    if args.client_id and not args.identidade_gerenciada:
        raise ErroLab("--client-id só vale com --identidade-gerenciada.")
    if args.identidade_gerenciada and args.tenant_id:
        raise ErroLab("--tenant-id vale só para a sessão do Azure CLI: com --identidade-gerenciada, o tenant é o do ambiente.")
    if args.etapa == "criar":
        minimo, maximo = lab_ingestao.DIMENSOES_DOS_MODELOS[args.modelo_embeddings]
        if not minimo <= args.dimensoes <= maximo:
            raise ErroLab(f"O modelo '{args.modelo_embeddings}' aceita de {minimo} a {maximo} dimensões; recebido: {args.dimensoes}.")
        if args.sobreposicao >= args.tamanho_maximo:
            raise ErroLab("A sobreposição precisa ser menor que o tamanho máximo do trecho.")


# --------------------------------------------------------------------------------------
# Saída
# --------------------------------------------------------------------------------------

def _credencial(args: argparse.Namespace) -> Any:
    return l300.criar_credencial_gerenciada(args.client_id) if args.identidade_gerenciada else None


def _cliente(args: argparse.Namespace) -> lab_ingestao.ClienteBusca:
    return l300.abrir_cliente(args.busca, args.tenant_id, args.versao_api, _credencial(args))


def _container(args: argparse.Namespace) -> Any:
    return l300.abrir_container(args.conta, args.container, args.tenant_id, _credencial(args))


def _modo(simula: bool, somente_leitura: bool = False) -> None:
    if somente_leitura:
        print("Modo: SOMENTE LEITURA (nenhuma alteração será feita)")
    else:
        print("Modo: " + ("SIMULAÇÃO (nenhuma alteração será feita)" if simula else "EXECUÇÃO"))


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


def _destino_dos_blobs(args: argparse.Namespace, manifesto: l300.Manifesto) -> None:
    print(f"Destino: conta '{args.conta}', contêiner '{args.container}', pasta '{manifesto.prefixo}'; os documentos do L100 e do "
          "L200 (contêiner 'base-documental') não são lidos nem alterados")


def _mostrar_plano_de_blobs(acoes: Sequence[l300.AcaoBlob]) -> None:
    print("Plano:")
    for acao in acoes:
        documento = acao.documento
        nota = f"  <- {acao.detalhe}" if acao.detalhe else ""
        print(f"  [{_ROTULOS_DO_PLANO[acao.estado]:<10}] {documento.id:<16} {documento.acesso:<13} {documento.blob}{nota}")


def _comando(etapa: str, *opcoes: str) -> str:
    return "python scripts\\gerenciar_ingestao_l300.py --etapa " + " ".join((etapa, *opcoes))


# --------------------------------------------------------------------------------------
# Etapa validar
# --------------------------------------------------------------------------------------

def etapa_validar(args: argparse.Namespace) -> int:
    manifesto = l300.carregar_e_validar(args.manifesto)
    print("Modo: LOCAL, SEM REDE (nenhum acesso ao Azure)")
    _avisar_executar_sem_efeito(args)
    print(f"Manifesto: {lab_comum._mostrar_caminho(manifesto.caminho)} (schema 1, sintético, {len(manifesto.documentos)} documento(s))")
    print("Classes de acesso permitidas: " + ", ".join(lab_acesso.CLASSES))
    for papel, classes in lab_acesso.CLASSES_POR_PAPEL.items():
        print(f"  Papel de aplicação {papel}: pode recuperar {', '.join(classes)}")
    print(f"Destino do L300, separado do L100 e do L200: contêiner '{l300.CONTAINER_PADRAO}', pasta '{manifesto.prefixo}', "
          f"índice '{l300.INDICE_PADRAO}'")
    print("Documentos:")
    for documento in manifesto.documentos:
        print(f"  [OK] {documento.id:<16} {documento.acesso:<13} {documento.origem.upper():<4} {documento.tamanho_bytes:>6} bytes  "
              f"sha256 {documento.sha256[:12]}  {documento.blob}")
    print("Conferido: caminhos dentro de dados\\, tamanho e hash do conteúdo normalizado (LF), declaração de sintético, "
          "classe de acesso presente e permitida, documentos do L100 idênticos ao inventário do L100 e nenhum arquivo sem "
          "permissão declarada.")
    aviso = lab_comum.aviso_de_revisao(manifesto.inventario())
    if aviso:
        print(f"[AVISO] {aviso}")
    operacionais = [documento.id for documento in manifesto.documentos if documento.origem == l300.ORIGEM_L300]
    print(f"Documentos que as etapas excluir e restaurar aceitam (origem L300): {', '.join(operacionais) or 'nenhum'}.")
    print("Validação concluída. Nenhuma chamada de rede foi feita e nada foi enviado.")
    print("Próximo passo: " + _comando("carregar", "--conta", "<conta>"))
    return lab_comum.CODIGO_OK


# --------------------------------------------------------------------------------------
# Etapas carregar, excluir e restaurar
# --------------------------------------------------------------------------------------

def etapa_carregar(args: argparse.Namespace) -> int:
    manifesto = l300.carregar_e_validar(args.manifesto)
    documentos = l300.selecionar_documentos(manifesto, args.documentos)
    _modo(not args.executar)
    _destino_dos_blobs(args, manifesto)
    print(f"Manifesto: {len(documentos)} de {len(manifesto.documentos)} documento(s) selecionado(s), conferidos por tamanho e hash; "
          "cada cópia leva os metadados 'acesso' (a classe) e 'sha256' (o hash do conteúdo de origem).")
    aviso = lab_comum.aviso_de_revisao(manifesto.inventario())
    if aviso:
        print(f"[AVISO] {aviso}")

    container = _container(args)
    acoes = l300.planejar_carga(container, documentos)
    _mostrar_plano_de_blobs(acoes)
    orfaos = l300.listar_orfaos(container, manifesto)
    if orfaos:
        print(f"[AVISO] {len(orfaos)} blob(s) na pasta '{manifesto.prefixo}' sem permissão declarada no manifesto: {', '.join(orfaos[:5])}"
              + (" ..." if len(orfaos) > 5 else "") + ". Esta ferramenta não os apaga. O indexador lê a pasta inteira e o filtro do chat "
              "autoriza classes, não IDs do manifesto: com uma classe permitida no metadado 'acesso', eles seriam recuperáveis. "
              "A etapa conferir reprova os trechos desses documentos.")

    if any(acao.estado in (l300.DIVERGENTE, l300.METADADOS) for acao in acoes) and not args.substituir_divergentes:
        print("[PARADA] Há blob(s) diferentes do manifesto (conteúdo ou metadados de acesso). Nada foi alterado.")
        print("         Investigue a diferença. Para aplicar o manifesto de propósito: --executar --substituir-divergentes.")
        return lab_comum.CODIGO_DIVERGENCIA
    if not args.executar:
        print("Simulação concluída. Para enviar, repita o comando com --executar.")
        return lab_comum.CODIGO_OK

    resultado = l300.aplicar_carga(container, acoes)
    print(f"Concluído: {resultado['criados']} criado(s), {resultado['substituidos']} trocado(s), {resultado['metadados']} com metadados "
          f"atualizados, {resultado['iguais']} já igual(is).")
    print("Próximo passo (cria os objetos de busca, uma vez): "
          + _comando("criar", "--busca", "<busca>", "--assinatura", "<assinatura>", "--grupo", "<grupo>", "--conta", args.conta,
                     "--modelos", "<modelos>"))
    print("Para reprocessar depois de uma carga: " + _comando("executar", "--busca", "<busca>", "--executar", "--aguardar"))
    return lab_comum.CODIGO_OK


def etapa_excluir(args: argparse.Namespace) -> int:
    manifesto = l300.carregar_manifesto(args.manifesto)
    documentos = l300.selecionar_documentos(manifesto, args.documentos, somente_origem=l300.ORIGEM_L300)
    _modo(not args.executar)
    _destino_dos_blobs(args, manifesto)
    container = _container(args)
    acoes = l300.planejar_exclusao(container, documentos)
    _mostrar_plano_de_blobs(acoes)
    if not any(acao.estado == l300.EXCLUIR for acao in acoes):
        print("[IGUAL] Nenhum blob ativo para excluir.")
        return lab_comum.CODIGO_OK
    print("Efeito: a exclusão é reversível (soft delete da conta). Os trechos só saem do índice na próxima execução do indexador "
          "(detecção nativa de exclusão), e a restauração desfaz a exclusão dentro do prazo de retenção da conta.")
    if not args.executar:
        print("Simulação concluída. Para excluir, repita o comando com --executar.")
        return lab_comum.CODIGO_OK
    excluidos = l300.aplicar_exclusao(container, acoes)
    print(f"Concluído: {excluidos} blob(s) excluído(s) de forma reversível.")
    desfazer = [opcao for acao in acoes if acao.estado == l300.EXCLUIR for opcao in ("--documento", acao.documento.id)]
    print("Próximo passo: " + _comando("executar", "--busca", "<busca>", "--executar", "--aguardar")
          + "; para desfazer: " + _comando("restaurar", "--conta", args.conta, *desfazer, "--executar"))
    return lab_comum.CODIGO_OK


def etapa_restaurar(args: argparse.Namespace) -> int:
    manifesto = l300.carregar_manifesto(args.manifesto)
    documentos = l300.selecionar_documentos(manifesto, args.documentos, somente_origem=l300.ORIGEM_L300)
    _modo(not args.executar)
    _destino_dos_blobs(args, manifesto)
    container = _container(args)
    acoes = l300.planejar_restauracao(container, documentos)
    _mostrar_plano_de_blobs(acoes)
    if not any(acao.estado == l300.RESTAURAR for acao in acoes):
        print("[IGUAL] Nenhum blob excluído de forma reversível para restaurar. Se o blob não existe, use --etapa carregar.")
        return lab_comum.CODIGO_OK
    print("Efeito: o blob volta como estava antes da exclusão. Se o conteúdo restaurado confere com o manifesto, os metadados do "
          "manifesto (classe de acesso) são reaplicados, o que faz o indexador reprocessá-lo na próxima execução. Se diverge, nada é "
          "reaplicado e a etapa termina com divergência (código 3): o blob fica restaurado, e a reposição exige --etapa carregar "
          "--substituir-divergentes antes de indexar.")
    if not args.executar:
        print("Simulação concluída. Para restaurar, repita o comando com --executar.")
        return lab_comum.CODIGO_OK
    restaurados = l300.aplicar_restauracao(container, acoes)
    print(f"Concluído: {restaurados} blob(s) restaurado(s).")
    print("Próximo passo: " + _comando("executar", "--busca", "<busca>", "--executar", "--aguardar"))
    return lab_comum.CODIGO_OK


# --------------------------------------------------------------------------------------
# Etapa criar
# --------------------------------------------------------------------------------------

def _resumo_do_objeto(acao: lab_ingestao.AcaoObjeto, p: lab_ingestao.Parametros) -> str:
    if acao.tipo == lab_ingestao.INDICE:
        return (f"{len(acao.definicao['fields'])} campos, com 'acesso' (texto filtrável, projetado do metadado do blob); "
                f"busca vetorial (HNSW, cosseno, {p.dimensoes} dimensões)")
    if acao.tipo == lab_ingestao.FONTE:
        return (f"Blob Storage, contêiner '{p.container}', pasta '{p.prefixo}'; identidade gerenciada (ResourceId, sem chaves); "
                "exclusões: soft delete nativo do Blob")
    if acao.tipo == lab_ingestao.SKILLSET:
        return (f"Text Split (até {p.tamanho_maximo} caracteres, sobreposição de {p.sobreposicao}) + Azure OpenAI Embedding "
                f"('{p.deployment}', {p.modelo_embeddings}, {p.dimensoes} dimensões); projeção de índice: um documento por trecho, "
                "com a classe de acesso do blob")
    ambiente = "privado (executionEnvironment=private)" if p.privado else "padrão (executionEnvironment=standard)"
    agenda = f"agenda {p.intervalo}" if p.intervalo else "sem agenda"
    return f"texto simples (.md); criado DESABILITADO; ambiente de execução {ambiente}; {agenda}"


def _mostrar_plano_de_criacao(acoes: Sequence[lab_ingestao.AcaoObjeto], p: lab_ingestao.Parametros, args: argparse.Namespace) -> None:
    print("Plano:")
    for acao in acoes:
        rotulo = "substituir" if acao.estado == lab_indexacao.DIVERGENTE and args.substituir and acao.proprio else acao.estado
        print(f"  [{rotulo:<10}] {lab_ingestao.ROTULOS[acao.tipo]} '{acao.nome}': {_resumo_do_objeto(acao, p)}")
        if acao.estado == lab_indexacao.DIVERGENTE:
            _mostrar_diferencas(acao.diferencas)
            if not acao.proprio:
                print("                 <- de outro dono: nunca é substituído por esta ferramenta, nem com --substituir")
            else:
                print("                 " + ("<- será substituído (--substituir)" if args.substituir
                                              else "<- só será substituído com --substituir"))
    contagem = {estado: sum(1 for acao in acoes if acao.estado == estado)
                for estado in (lab_indexacao.CRIAR, lab_indexacao.IGUAL, lab_indexacao.DIVERGENTE)}
    print(f"  Total: {len(acoes)} objeto(s): {contagem[lab_indexacao.CRIAR]} a criar, {contagem[lab_indexacao.IGUAL]} iguais, "
          f"{contagem[lab_indexacao.DIVERGENTE]} divergentes.")
    if args.mostrar_definicoes:
        print("Definições (redigidas) dos objetos que serão enviados:")
        for acao in acoes:
            if acao.estado != lab_indexacao.IGUAL:
                print(f"--- {lab_ingestao.ROTULOS[acao.tipo]} '{acao.nome}' ---")
                print(json.dumps(lab_ingestao.redigir_definicao(acao.definicao), ensure_ascii=False, indent=2))


def etapa_criar(args: argparse.Namespace) -> int:
    manifesto = l300.carregar_manifesto(args.manifesto)
    parametros = l300.parametros_do_pipeline(manifesto, args)
    lab_ingestao.validar_parametros(parametros)
    _modo(not args.executar)
    print(f"Destino: serviço de busca '{args.busca}' (API REST {args.versao_api}), índice '{args.indice}'; os índices do L100 e do "
          "L200 não são lidos nem alterados")
    print(f"Origem: conta '{args.conta}', contêiner '{args.container}', pasta '{parametros.prefixo}' ({len(manifesto.documentos)} "
          "documento(s) no manifesto), lida pela identidade gerenciada do serviço de busca")
    print(f"Embeddings: deployment '{args.deployment}' ({args.modelo_embeddings}, {args.dimensoes} dimensões) do recurso "
          f"'{args.modelos}', chamado pela identidade gerenciada do serviço de busca")
    aviso = lab_comum.aviso_de_revisao(manifesto.inventario())
    if aviso:
        print(f"[AVISO] {aviso}")

    cliente = _cliente(args)
    acoes = lab_ingestao.planejar_objetos(parametros, _atuais(cliente, parametros.nomes.em_ordem_de_criacao()))
    _mostrar_plano_de_criacao(acoes, parametros, args)

    alheios = [acao for acao in acoes if acao.estado != lab_indexacao.CRIAR and not acao.proprio]
    if alheios:
        print("[PARADA] Há objeto(s) com estes nomes sem o marcador do L300: " + ", ".join(
            f"{lab_ingestao.ROTULOS[acao.tipo]} '{acao.nome}'" for acao in alheios) + ". Nada foi alterado.")
        print("         Eles não foram criados por esta ferramenta e nunca são substituídos, nem com --substituir: confira no portal do Azure.")
        return lab_comum.CODIGO_DIVERGENCIA
    if any(acao.estado == lab_indexacao.DIVERGENTE for acao in acoes) and not args.substituir:
        print("[PARADA] Há objeto(s) do L300 no serviço diferente(s) do definido. Nada foi alterado.")
        print("         Confira as diferenças acima. Para trocá-los de propósito: --executar --substituir.")
        return lab_comum.CODIGO_DIVERGENCIA
    if not args.executar:
        print("Antes de executar o indexador, confira (esta ferramenta não altera permissões, redes nem a conta de armazenamento):")
        print("  - a identidade gerenciada do serviço de busca (system-assigned) está habilitada;")
        print(f"  - ela tem 'Storage Blob Data Reader' no contêiner '{args.container}' e 'Cognitive Services OpenAI User' no recurso de modelos;")
        if parametros.privado:
            print("  - ambiente privado: as conexões privadas compartilhadas (shared private links) da busca para o Blob Storage e para os "
                  "modelos existem e foram aprovadas nos recursos de destino;")
        print("  - a conta tem soft delete de blobs ativo e o versionamento de blobs desativado, que a detecção nativa de exclusão exige.")
        print("Simulação concluída. Para criar, repita o comando com --executar.")
        return lab_comum.CODIGO_OK

    criados = substituidos = 0
    for acao in acoes:
        if acao.estado == lab_indexacao.IGUAL:
            continue
        substituir = acao.estado == lab_indexacao.DIVERGENTE
        cliente.gravar(acao.tipo, acao.nome, acao.definicao, etag=acao.etag if substituir else None)
        criados += not substituir
        substituidos += substituir
        print(f"[{'SUBSTITUÍDO' if substituir else 'CRIADO'}] {lab_ingestao.ROTULOS[acao.tipo]} '{acao.nome}'"
              + (" (desabilitado: não executa até a etapa executar)" if acao.tipo == lab_ingestao.INDEXADOR else "") + ".")
    if not criados and not substituidos:
        print("[IGUAL] Os quatro objetos já estão como o plano pede; nada a fazer.")
    else:
        print(f"Concluído: {criados} criado(s), {substituidos} substituído(s), {len(acoes) - criados - substituidos} já igual(is). "
              "O indexador não foi executado.")
    if substituidos:
        print("Depois de substituir o skillset, a fonte ou o índice, reprocesse os blobs com --etapa executar --executar --reiniciar.")
    print("Próximo passo: " + _comando("executar", "--busca", args.busca, "--indice", args.indice, "--executar", "--aguardar"))
    return lab_comum.CODIGO_OK


# --------------------------------------------------------------------------------------
# Etapa executar
# --------------------------------------------------------------------------------------

def etapa_executar(args: argparse.Namespace) -> int:
    nomes = l300.nomes_dos_objetos(args.indice)
    cliente = _cliente(args)
    _modo(not args.executar)
    print(f"Destino: serviço de busca '{args.busca}' (API REST {args.versao_api}), índice '{args.indice}'")
    indexador = cliente.obter(lab_ingestao.INDEXADOR, nomes.indexador)
    if indexador is None:
        raise ErroLab(f"O indexador '{nomes.indexador}' não existe no serviço '{args.busca}'. Crie os objetos com "
                      "--etapa criar --executar.", lab_comum.CODIGO_DIVERGENCIA)
    if not lab_ingestao.objeto_do_laboratorio(indexador, l300.MARCADOR):
        raise ErroLab(f"O indexador '{nomes.indexador}' não traz o marcador do L300: esta ferramenta não o executa.",
                      lab_comum.CODIGO_DIVERGENCIA)
    anterior = lab_ingestao.resumir_status(cliente.status_indexador(nomes.indexador))
    desabilitado = bool(indexador.get("disabled"))
    ambiente = ((indexador.get("parameters") or {}).get("configuration") or {}).get("executionEnvironment") or "não definido"
    print("Plano:")
    if args.reiniciar:
        print(f"  [reiniciar ] indexador '{nomes.indexador}': apaga o rastreamento de mudanças; todos os blobs serão "
              "reprocessados e os embeddings, calculados de novo")
    if desabilitado:
        print(f"  [habilitar ] indexador '{nomes.indexador}' está desabilitado, como a etapa criar o deixa: atualizá-lo como "
              "habilitado inicia a execução (comportamento documentado do serviço)")
    else:
        print(f"  [executar  ] indexador '{nomes.indexador}': execução sob demanda")
    print(f"  Ambiente de execução do indexador: {ambiente}. Cada execução chama o deployment de embeddings para cada trecho novo ou "
          "alterado (consumo de tokens).")
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
        cliente.gravar(lab_ingestao.INDEXADOR, nomes.indexador, definicao, etag=indexador.get("@odata.etag"))
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
    ingestao_l200.mostrar_resumo(resumo)
    if resumo.ok and not resumo.processados and anterior.resultado is None:
        print("[ATENÇÃO] A primeira execução terminou sem processar nenhum blob. Confira a pasta lida, o contêiner e se as cópias "
              "foram enviadas com --etapa carregar --executar.")
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
    nomes = l300.nomes_dos_objetos(args.indice)
    manifesto = l300.carregar_manifesto(args.manifesto)
    ausentes = list(dict.fromkeys(args.ausentes or ()))
    desconhecidos = [identificador for identificador in ausentes if identificador not in manifesto.por_id()]
    if desconhecidos:
        raise ErroLab(f"Documento(s) fora do manifesto em --ausente: {', '.join(desconhecidos)}.")
    cliente = _cliente(args)
    _modo(False, somente_leitura=True)
    _avisar_executar_sem_efeito(args)
    print(f"Destino: serviço de busca '{args.busca}' (API REST {args.versao_api}), índice '{args.indice}'; os índices do L100 e do "
          "L200 não são lidos nem alterados")
    resultados: list[Verificacao] = []

    def registrar(resultado: Verificacao) -> Verificacao:
        resultados.append(resultado)
        print(f"[{'OK' if resultado.ok else 'FALHA':<5}] {resultado.nome}: {resultado.detalhe}")
        return resultado

    atuais = _atuais(cliente, nomes.em_ordem_de_criacao())
    estados = []
    for tipo, nome in nomes.em_ordem_de_criacao():
        atual = atuais[(tipo, nome)]
        estados.append(f"{lab_ingestao.ROTULOS[tipo]} " + (
            "ausente" if atual is None else "presente" if lab_ingestao.objeto_do_laboratorio(atual, l300.MARCADOR)
            else "sem o marcador do L300"))
    existem = all(atual is not None and lab_ingestao.objeto_do_laboratorio(atual, l300.MARCADOR) for atual in atuais.values())
    registrar(Verificacao("Objetos do pipeline do L300", existem, "; ".join(estados)))
    fonte = atuais[(lab_ingestao.FONTE, nomes.fonte)]
    if fonte is not None:
        politica = (fonte.get("dataDeletionDetectionPolicy") or {}).get("@odata.type")
        registrar(Verificacao(
            "Detecção de exclusão", politica == lab_ingestao.POLITICA_DE_EXCLUSAO,
            "soft delete nativo do Blob ativo no data source (blobs excluídos saem do índice na execução seguinte)"
            if politica == lab_ingestao.POLITICA_DE_EXCLUSAO else
            "o data source não tem a política de exclusão nativa: trechos de blobs excluídos ficariam órfãos no índice. "
            "Crie os objetos de novo (--etapa remover e --etapa criar)"))

    if all(getattr(args, opcao) for opcao in ("assinatura", "grupo", "conta", "modelos")) and existem:
        parametros = l300.parametros_do_pipeline(manifesto, args)
        lab_ingestao.validar_parametros(parametros)
        diferentes = [acao for acao in lab_ingestao.planejar_objetos(parametros, atuais) if acao.estado != lab_indexacao.IGUAL]
        if diferentes:
            registrar(Verificacao("Definições dos objetos", False, f"{len(diferentes)} objeto(s) diferente(s) do definido"))
            for acao in diferentes:
                print(f"         {lab_ingestao.ROTULOS[acao.tipo]} '{acao.nome}':")
                _mostrar_diferencas(acao.diferencas)
        else:
            registrar(Verificacao("Definições dos objetos", True, "os quatro objetos são os definidos por esta ferramenta"))
    else:
        print("[INFO ] Definições não comparadas: informe também --assinatura, --grupo, --conta e --modelos "
              "(com os quatro objetos presentes).")

    indexador = atuais[(lab_ingestao.INDEXADOR, nomes.indexador)]
    if indexador is not None:
        configuracao = (indexador.get("parameters") or {}).get("configuration") or {}
        esperado = "standard" if args.privado is False else "private"
        atual = configuracao.get("executionEnvironment")
        registrar(Verificacao("Ambiente de execução do indexador", atual == esperado,
                              f"'{atual or 'não definido'}' (esperado '{esperado}')"))
        agenda = (indexador.get("schedule") or {}).get("interval")
        print(f"[INFO ] Agenda do indexador: {agenda or 'nenhuma (só executa sob demanda)'}.")
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

    definicao_do_indice = atuais[(lab_ingestao.INDICE, nomes.indice)]
    if definicao_do_indice is None:
        registrar(Verificacao("Trechos do índice", False, f"o índice '{nomes.indice}' não existe"))
    else:
        incompativeis = lab_ingestao.diferencas_de_compatibilidade(definicao_do_indice, args.dimensoes)
        registrar(Verificacao("Compatibilidade com o recuperador do L100", not incompativeis,
                              "; ".join(incompativeis) or "campos de resultado e campo vetorial 'vetor' presentes"))
        presentes = {campo["name"]: campo for campo in definicao_do_indice.get("fields", [])}
        campo_de_acesso = presentes.get(lab_acesso.CAMPO_ACESSO)
        acesso_ok = bool(campo_de_acesso) and campo_de_acesso.get("type") == "Edm.String" and bool(campo_de_acesso.get("filterable"))
        registrar(Verificacao("Campo de acesso do índice", acesso_ok,
                              "'acesso' é texto filtrável (Edm.String)" if acesso_ok else
                              "falta o campo 'acesso' como texto filtrável: sem ele o filtro de segurança do chat não funciona"))
        campos = [campo for campo in (*lab_ingestao.CAMPOS_DA_LISTAGEM, *lab_ingestao.CAMPOS_EXTRAS_DO_L200, lab_acesso.CAMPO_ACESSO)
                  if campo in presentes]
        trechos = lab_ingestao.listar_trechos(cliente, nomes.indice, campos)
        qualidade = lab_ingestao.analisar_trechos(trechos, manifesto.inventario(sem=ausentes), args.container)
        problemas = lab_ingestao.problemas_de_completude(qualidade)
        por_documento = ", ".join(f"{documento} {quantidade}" for documento, quantidade in sorted(qualidade.por_documento.items()))
        esperados = len(manifesto.documentos) - len(ausentes)
        registrar(Verificacao("Trechos do índice", not problemas,
                              f"{qualidade.trechos} trecho(s) em {len(qualidade.por_documento)} de {esperados} "
                              f"documento(s) esperado(s) do manifesto ({por_documento or 'nenhum'})"
                              + ("; " + "; ".join(problemas) if problemas else "")))
        acesso = l300.analisar_acesso(trechos, manifesto)
        problemas_de_acesso = l300.problemas_de_acesso(acesso) if campo_de_acesso else ["o índice não tem o campo 'acesso'"]
        por_classe = ", ".join(f"{classe} {quantidade}" for classe, quantidade in sorted(acesso.por_classe.items()))
        registrar(Verificacao("Classe de acesso dos trechos", not problemas_de_acesso,
                              f"{por_classe or 'nenhuma classe'}" + ("; " + "; ".join(problemas_de_acesso) if problemas_de_acesso else
                                                                    "; cada trecho tem a classe do manifesto")))
        for identificador in ausentes:
            presentes_do_documento = acesso.por_documento.get(identificador, 0)
            registrar(Verificacao(f"Documento {identificador} ausente do índice", presentes_do_documento == 0,
                                  "nenhum trecho (como esperado)" if not presentes_do_documento else
                                  f"ainda há {presentes_do_documento} trecho(s): execute o indexador depois de excluir o blob"))
        preenchidos = ", ".join(f"{campo} {_percentual(qualidade.percentual(campo))}" for campo in lab_ingestao.CAMPOS_PREENCHIDOS
                                if qualidade.percentual(campo) is not None)
        print(f"[INFO ] Campos preenchidos pelo pipeline (parte dos trechos): {preenchidos or 'nenhum'}.")
        if qualidade.trechos and qualidade.vazios.get("documento_id") == qualidade.trechos:
            print("[DICA ] Nenhum trecho trouxe os metadados do blob (documento_id, versao, produto, sha256, sintetico, acesso). Confira "
                  "se os blobs têm esses metadados (--etapa carregar): a projeção os lê em /document/<nome do metadado>.")

    if all(resultado.ok for resultado in resultados):
        print("Conferência aprovada.")
        return lab_comum.CODIGO_OK
    print("Conferência reprovada. Corrija as falhas e repita. Nada foi alterado por esta ferramenta.")
    return lab_comum.CODIGO_DIVERGENCIA


# --------------------------------------------------------------------------------------
# Etapa remover
# --------------------------------------------------------------------------------------

def etapa_remover(args: argparse.Namespace) -> int:
    nomes = l300.nomes_dos_objetos(args.indice)
    cliente = _cliente(args)
    _modo(not args.executar)
    print(f"Destino: serviço de busca '{args.busca}' (API REST {args.versao_api}), índice '{args.indice}'; os índices do L100 e do "
          "L200 não são lidos nem alterados")
    acoes = lab_ingestao.planejar_remocao(nomes, _atuais(cliente, nomes.em_ordem_de_remocao()), l300.MARCADOR)
    print("Plano (nesta ordem: quem depende de outro objeto sai primeiro):")
    for acao in acoes:
        rotulo = {lab_ingestao.REMOVER: "remover", lab_ingestao.AUSENTE: "ausente", lab_ingestao.ALHEIO: "alheio"}[acao.estado]
        dica = {lab_ingestao.REMOVER: "", lab_ingestao.AUSENTE: " (não existe; nada a fazer)",
                lab_ingestao.ALHEIO: " (não traz o marcador do L300; não será apagado)"}[acao.estado]
        print(f"  [{rotulo:<10}] {lab_ingestao.ROTULOS[acao.tipo]} '{acao.nome}'{dica}")
    print("Só estes quatro objetos são considerados. Os blobs, a conta de armazenamento, o recurso de modelos, o serviço de busca, "
          "os índices do L100 e do L200 e as permissões não são alterados.")
    if any(acao.estado == lab_ingestao.ALHEIO for acao in acoes):
        print("[PARADA] Há objeto(s) com estes nomes que o L300 não criou. Nada foi apagado: confira no portal do Azure.")
        return lab_comum.CODIGO_DIVERGENCIA
    a_remover = [acao for acao in acoes if acao.estado == lab_ingestao.REMOVER]
    if not a_remover:
        print("[IGUAL] Nenhum dos objetos existe; nada a remover.")
        return lab_comum.CODIGO_OK
    if not args.executar:
        print("Efeito: remover o índice apaga os trechos; recriá-los exige executar o indexador de novo (consumo de embeddings).")
        print("Simulação concluída. Para remover, repita o comando com --executar.")
        return lab_comum.CODIGO_OK
    for acao in a_remover:
        cliente.apagar(acao.tipo, acao.nome, acao.etag)
        print(f"[REMOVIDO] {lab_ingestao.ROTULOS[acao.tipo]} '{acao.nome}'.")
    print(f"Concluído: {len(a_remover)} objeto(s) removido(s).")
    return lab_comum.CODIGO_OK


# --------------------------------------------------------------------------------------
# Entrada
# --------------------------------------------------------------------------------------

_ETAPAS = {"validar": etapa_validar, "carregar": etapa_carregar, "excluir": etapa_excluir, "restaurar": etapa_restaurar,
           "criar": etapa_criar, "executar": etapa_executar, "conferir": etapa_conferir, "remover": etapa_remover}


def executar(args: argparse.Namespace) -> int:
    exigir_opcoes(args)
    validar_combinacoes(args)
    return _ETAPAS[args.etapa](args)


def criar_parser() -> lab_comum.ParserLab:
    parser = lab_comum.criar_parser(__doc__, armazenamento=False, inventario=False)
    parser.add_argument("--ajuda", action="help", help="O mesmo que --help.")
    parser.add_argument("--etapa", required=True, choices=ETAPAS,
                        help="validar, carregar, excluir, restaurar, criar, executar, conferir ou remover (veja a descrição acima).")
    parser.add_argument("--manifesto", type=Path, default=l300.MANIFESTO_PADRAO,
                        help="Manifesto de permissões documentais (padrão: dados\\l300\\permissoes-documentais.json).")
    parser.add_argument("--conta", default=None, type=lab_comum.validar_conta,
                        help="Conta de armazenamento do L300 (saída nomeConta da implantação; etapas carregar, excluir, restaurar e criar).")
    parser.add_argument("--container", default=l300.CONTAINER_PADRAO, type=l300.validar_container_l300,
                        help=f"Contêiner de blobs do L300; o do L100 é recusado (padrão: {l300.CONTAINER_PADRAO}).")
    parser.add_argument("--documento", dest="documentos", action="append", default=None, type=l300.validar_id_do_documento, metavar="ID",
                        help="Documento do manifesto, como VLAR-OP-ATD-1.0; pode se repetir. Obrigatório em excluir e restaurar "
                             "(só documentos de origem L300); em carregar, limita o envio a estes documentos.")
    parser.add_argument("--substituir-divergentes", action="store_true",
                        help="Permite trocar blobs do L300 com conteúdo ou metadados diferentes do manifesto (etapa carregar).")
    parser.add_argument("--busca", default=None, type=lab_indexacao.validar_busca,
                        help="Nome do serviço de busca (saída nomeBusca da implantação).")
    parser.add_argument("--indice", default=l300.INDICE_PADRAO, type=l300.validar_indice_l300,
                        help=f"Índice do L300; dele derivam o data source, o skillset e o indexador (padrão: {l300.INDICE_PADRAO}).")
    parser.add_argument("--assinatura", default=None, type=lab_ingestao.validar_assinatura,
                        help="ID da assinatura Azure da conta de armazenamento (etapa criar). Forma o ResourceId; não é gravado em arquivo.")
    parser.add_argument("--grupo", default=None, type=lab_ingestao.validar_grupo,
                        help="Grupo de recursos da conta de armazenamento (etapa criar).")
    parser.add_argument("--modelos", default=None, type=lab_indexacao.validar_modelos,
                        help="Recurso de modelos (saída nomeModelos da implantação; etapa criar).")
    parser.add_argument("--deployment", default=lab_indexacao.DEPLOYMENT_PADRAO, type=lab_indexacao.validar_deployment,
                        help=f"Deployment de embeddings, não o modelo (padrão: {lab_indexacao.DEPLOYMENT_PADRAO}).")
    parser.add_argument("--modelo-embeddings", default=lab_ingestao.MODELO_EMBEDDINGS_PADRAO, type=lab_ingestao.validar_modelo_embeddings,
                        help=f"Modelo do deployment, exigido pela habilidade (padrão: {lab_ingestao.MODELO_EMBEDDINGS_PADRAO}).")
    parser.add_argument("--dimensoes", default=lab_indexacao.DIMENSOES_PADRAO, type=lab_indexacao.validar_dimensoes,
                        help=f"Dimensões dos vetores (padrão: {lab_indexacao.DIMENSOES_PADRAO}).")
    lab_indexacao.adicionar_argumento_tamanho(parser)
    parser.add_argument("--sobreposicao", default=lab_ingestao.SOBREPOSICAO_PADRAO, type=lab_ingestao.validar_sobreposicao,
                        help=f"Caracteres repetidos entre trechos seguidos (padrão: {lab_ingestao.SOBREPOSICAO_PADRAO}).")
    grupo_privado = parser._grupo_opcoes.add_mutually_exclusive_group()
    grupo_privado.add_argument("--privado", dest="privado", action="store_const", const=True, default=None,
                               help="Indexador no ambiente de execução privado (executionEnvironment=private), que sai pelas conexões "
                                    "privadas compartilhadas da busca. É o padrão do L300 (etapas criar e conferir).")
    grupo_privado.add_argument("--nao-privado", dest="privado", action="store_const", const=False,
                               help="Indexador no ambiente de execução padrão (standard), para um serviço sem conexões privadas "
                                    "(etapas criar e conferir).")
    parser.add_argument("--intervalo", default=None, type=l300.validar_intervalo, metavar="MINUTOS",
                        help=f"Agenda opcional do indexador, em minutos ({l300.INTERVALO_MINIMO} a {l300.INTERVALO_MAXIMO}). Sem ela, o "
                             "indexador não tem agenda e só executa sob demanda (etapa criar).")
    parser.add_argument("--executar", action="store_true",
                        help="Faz a alteração (carregar, excluir, restaurar, criar, executar o indexador ou remover). "
                             "Sem esta opção, a ferramenta só simula.")
    parser.add_argument("--substituir", action="store_true",
                        help="Permite trocar um objeto de busca do L300 que difere da definição (etapa criar). "
                             "Nunca troca um objeto sem o marcador do L300.")
    parser.add_argument("--reiniciar", action="store_true",
                        help="Apaga o rastreamento do indexador antes de executar: reprocessa todos os blobs (etapa executar).")
    parser.add_argument("--aguardar", nargs="?", const=lab_ingestao.ESPERA_PADRAO_SEGUNDOS, default=None, type=lab_ingestao.validar_espera,
                        help=f"Espera o fim da execução do indexador, por até N segundos (padrão sem valor: "
                             f"{lab_ingestao.ESPERA_PADRAO_SEGUNDOS}; máximo {lab_ingestao.ESPERA_MAXIMA_SEGUNDOS}).")
    parser.add_argument("--ausente", dest="ausentes", action="append", default=None, type=l300.validar_id_do_documento, metavar="ID",
                        help="Documento que deve estar AUSENTE do índice, como depois de excluir o blob e executar o indexador; "
                             "pode se repetir (etapa conferir).")
    parser.add_argument("--mostrar-definicoes", action="store_true",
                        help="Mostra, redigidas, as definições JSON dos objetos que a etapa criar enviaria.")
    parser.add_argument("--versao-api", choices=lab_ingestao.VERSOES_API, default=lab_ingestao.VERSAO_API,
                        help=f"Versão estável da API REST do serviço de busca (padrão: {lab_ingestao.VERSAO_API}, que documenta a "
                             "exclusão nativa do Blob).")
    parser.add_argument("--identidade-gerenciada", action="store_true",
                        help="Usa a identidade gerenciada do ambiente onde a ferramenta roda, em vez da sessão do Azure CLI (az login).")
    parser.add_argument("--client-id", default=None, type=l300.validar_client_id,
                        help="Client ID de uma identidade gerenciada atribuída pelo usuário (com --identidade-gerenciada).")
    return parser


def principal(argv: list[str] | None = None) -> int:
    lab_comum.configurar_saida()
    args = criar_parser().parse_args(argv)
    return lab_comum.executar_com_tratamento(executar, args, tradutor=lab_ingestao.traduzir_erro_ingestao)


if __name__ == "__main__":
    sys.exit(principal())
