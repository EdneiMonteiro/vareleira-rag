"""Operação offline do L400: plano, what-if sanitizado, conferência da migração de índice, resumo de logs e validação da comparação.

Este script lê só arquivos locais e variáveis de ambiente. Ele não usa rede, não chama o Azure nem o GitHub, não implanta, não carrega
dados, não atribui papéis e não apaga nada: quem executa as etapas na nuvem é quem opera, com autorização própria para cada uma. A
única coisa que o script grava é um relatório novo e sanitizado, e nunca sobrescreve um arquivo que já existe. Os relatórios têm
vocabulário fechado, contagens e hashes: nunca nomes de recursos, identificadores, endereços, tokens, perguntas ou respostas. Nada do
que ele produz é evidência do Azure: o que ele confere é o que VOCÊ declarou (origem "operador") ou um exemplo (origem "simulado").

Etapas (--etapa):
    planejar            mostra o plano declarativo, com um vocabulário fechado de passos (quem executa, o que cria, reutiliza e altera,
                        custo, variáveis, portões, comandos de referência e limpeza); --validar-bicep compila infra/l400.bicep e exige
                        lint SEM avisos, como o CI
    sanitizar-whatif    reduz o JSON do what-if do ARM a contagens, tipos de recurso e caminhos de propriedades (o mesmo critério do L300)
    conferir-migracao   confere o descritor de promoção ou de retorno do índice: nomes distintos no namespace do L300, modelo e dimensões
                        iguais ao manifesto de deployment, as mesmas quatro fontes e classes e as contagens de trechos antes e depois.
                        Trocar o índice na configuração da aplicação não prova compatibilidade: a prova é o que foi observado
    resumir-logs        conta status, rotas, latência e causas dos logs sanitizados do chat, os eventos da coordenação e as duas linhas de
                        partida do L400; qualquer outra linha derruba o resultado
    validar-comparacao  valida o relatório do avaliar_l400.py: tipo, hashes, mesmo conjunto e plano nas duas estratégias, denominador só
                        de casos planejados, uso desconhecido (nunca zero), ganhos e perdas, custos e ausência de conteúdo bruto

Códigos de saída: 0 concluído; 1 uso ou entrada inválida; 3 a conferência não aceitou o que leu (divergência, evidência incompleta ou
ensaio simulado); 4 defeito do script. Mensagens e relatórios nunca trazem valores privados.

Exemplos (todos locais, sem rede):
    python scripts\\operar_l400.py --etapa planejar
    python scripts\\operar_l400.py --etapa planejar --passo indice-candidato --formato json --validar-bicep
    python scripts\\operar_l400.py --etapa sanitizar-whatif --arquivo <whatif.json> --relatorio <novo-relatorio.json> --rotulo contingencia
    python scripts\\operar_l400.py --etapa conferir-migracao --descritor <descritor.json> --relatorio <novo-relatorio.json>
    python scripts\\operar_l400.py --etapa resumir-logs --logs <logs-sanitizados.txt> --relatorio <novo-resumo.json>
    python scripts\\operar_l400.py --etapa validar-comparacao --comparacao <relatorio-do-avaliador.json> --conjunto-esperado <sha256> --codigo-esperado <sha256>
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

import avaliar_l400 as al4
import lab_acesso
import lab_comum
import lab_ingestao
import lab_ingestao_l300 as l300
import operar_l300 as o3
from lab_comum import CODIGO_DIVERGENCIA, CODIGO_INESPERADO, CODIGO_OK, CODIGO_USO, ErroLab

# --------------------------------------------------------------------------------------
# Contrato com o Bicep, com a ingestão do L300 e com o avaliador
# --------------------------------------------------------------------------------------

BICEP_L400 = lab_comum.RAIZ / "infra" / "l400.bicep"
FASES = ("contingencia", "aplicacao")
PERFIS = ("referencia", "candidato")
INDICE_REFERENCIA = lab_acesso.INDICE_PADRAO
DIMENSOES_REFERENCIA = 1536
INDICE_CANDIDATO = "vareleira-lar-l300-l400-768"
DIMENSOES_CANDIDATA = 768
DEPLOYMENT_EMBEDDINGS = "embeddings"
DEPLOYMENT_GERACAO = "geracao"
DEPLOYMENT_CONTINGENCIA = "geracao-contingencia"
FONTES_APROVADAS = ("VLAR-CG-1.0", "VLAR-GL-1.0", "VLAR-FAQ-1.0", "VLAR-OP-ATD-1.0")
ORIGENS = ("operador", "simulado")
ACOES = ("promover", "retornar")
VERSAO_DO_RELATORIO = 1

VAR_FASE = "VARELEIRA_L400_FASE"  # o bicepparam do L400 lê estas variáveis
VAR_INGRESSO_EXTERNO = "VARELEIRA_L400_INGRESSO_EXTERNO"
VAR_PERFIL_INDICE = "VARELEIRA_L400_PERFIL_INDICE"
VAR_NOME_AMBIENTE = "VARELEIRA_L400_NOME_AMBIENTE"
VAR_TAG_IMAGEM = "VARELEIRA_L400_TAG_IMAGEM"
VARS_DOS_DESTINOS = ("VARELEIRA_NOME_MODELOS", "VARELEIRA_NOME_BUSCA", "VARELEIRA_NOME_REGISTRO", "VARELEIRA_NOME_IDENTIDADE_APLICACAO",
                     VAR_NOME_AMBIENTE)
VARS_DA_CONTINGENCIA = ("VARELEIRA_L400_MODELO_CONTINGENCIA", "VARELEIRA_L400_VERSAO_MODELO_CONTINGENCIA", "VARELEIRA_L400_SKU_CONTINGENCIA",
                        "VARELEIRA_L400_CAPACIDADE_CONTINGENCIA")
VARS_DA_APLICACAO = (VAR_TAG_IMAGEM, "VARELEIRA_ID_APLICACAO_LOGIN", "VARELEIRA_ID_TENANT_LOGIN", o3.VAR_SEGREDO_LOGIN)
VARS_OPCIONAIS = (VAR_FASE, VAR_INGRESSO_EXTERNO, VAR_PERFIL_INDICE, "VARELEIRA_ACAO_SEM_LOGIN")
# Toda variável que o bicepparam lê precisa estar aqui: o teste de contrato falha se o Bicep ganhar uma que o script desconhece.
VARIAVEIS_DO_BICEPPARAM = frozenset({*VARS_DOS_DESTINOS, *VARS_DA_CONTINGENCIA, *VARS_DA_APLICACAO, *VARS_OPCIONAIS})
VARS_PRIVADAS = (*VARS_DOS_DESTINOS, VAR_TAG_IMAGEM, "VARELEIRA_ID_APLICACAO_LOGIN", "VARELEIRA_ID_TENANT_LOGIN")

_PADRAO_DEPLOYMENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
_PADRAO_VERSAO = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,31}")
_PADRAO_INDICE = re.compile(r"[a-z0-9][a-z0-9-]{0,126}[a-z0-9]")
_PADRAO_DOCUMENTO = re.compile(r"[A-Z0-9][A-Z0-9.-]{2,39}")
_PADRAO_SHA256 = re.compile(r"[0-9a-f]{64}")
_LIMITE_DE_TRECHOS = 1_000_000

# --------------------------------------------------------------------------------------
# Plano declarativo
# --------------------------------------------------------------------------------------

EXECUTORES = {
    "bicep": "implantação incremental de infra/l400.bicep com infra/levels/l400.bicepparam, feita pelo coordenador (fora destes scripts)",
    "ingestao-l300": "scripts/gerenciar_ingestao_l300.py, pela sessão de quem opera (az login) ou por identidade gerenciada",
    "offline": "este script, sem rede",
    "avaliador": "scripts/avaliar_l400.py, por HTTP, com tokens em variáveis de ambiente",
    "coordenador": "operação de nuvem do coordenador, com autorização própria; nenhum script deste nível apaga recursos",
}
PRECONDICOES_GERAIS = (
    "base L100 ao L300 recriada no grupo de recursos exclusivo e conferida (rede privada, ambiente do Container Apps, registro, "
    "identidade, busca, modelos, índice de referência vareleira-lar-l300 e a aplicação do L300 como referência)",
    "só as quatro fontes sintéticas já aprovadas (VLAR-CG-1.0, VLAR-GL-1.0, VLAR-FAQ-1.0 e VLAR-OP-ATD-1.0): nenhuma regra nova de seguro",
    "destino, orçamento e limpeza autorizados por quem responde pela assinatura; nenhum ID real fica em arquivo do repositório",
)
_COMANDO_INGESTAO = "python scripts\\gerenciar_ingestao_l300.py --etapa "
_INDICE_E_DIMENSOES = f"--indice {INDICE_CANDIDATO} --dimensoes {DIMENSOES_CANDIDATA}"

PLANO_DOS_PASSOS: dict[str, dict[str, Any]] = {
    "contingencia": {
        "objetivo": "Criar o deployment de geração de contingência no recurso de modelos existente, com o mesmo modelo e versão do principal.",
        "executor": "bicep", "nuvem": True,
        "variaveis": [VAR_FASE, *VARS_DOS_DESTINOS, *VARS_DA_CONTINGENCIA],
        "cria": [f"deployment '{DEPLOYMENT_CONTINGENCIA}', filho do recurso de modelos existente, com modelo e versão fixos (NoAutoUpgrade), "
                 "tipo que cobra por uso e cota explícita"],
        "reutiliza": ["recurso de modelos e deployments principal e de embeddings (só lidos)",
                      "identidade e papéis do L300: o papel de uso dos modelos vale para todos os deployments do recurso"],
        "altera": [],
        "custo": ["sem custo fixo: cobra por uso", "reserva cota regional: o Bicep não a consulta nem infere cota nova pelo fato de existirem "
                  "dois deployments; a capacidade é um valor seu, conferido antes"],
        "efeito_na_migracao": ["nenhum: o deployment principal e a aplicação do L300 não são alterados"],
        "precondicoes": ["cota regional disponível conferida por você", "what-if revisado (--etapa sanitizar-whatif)"],
        "portoes": ["guardas do Bicep: nome diferente do principal e do de embeddings; mesmo modelo e versão do principal; dimensões do perfil "
                    "dentro do limite do modelo de embeddings"],
        "comandos": ["python scripts\\operar_l400.py --etapa sanitizar-whatif --arquivo <whatif.json> --relatorio <novo.json> --rotulo contingencia"],
        "limpeza": [f"excluir o deployment '{DEPLOYMENT_CONTINGENCIA}' (coordenador); o principal não é tocado"],
    },
    "indice-candidato": {
        "objetivo": f"Criar e carregar o índice candidato '{INDICE_CANDIDATO}' ({DIMENSOES_CANDIDATA} dimensões), separado da referência, com as mesmas "
                    "quatro fontes e o mesmo contêiner.",
        "executor": "ingestao-l300", "nuvem": True,
        "variaveis": [],
        "cria": [f"índice '{INDICE_CANDIDATO}' e os três objetos derivados (data source, skillset e indexador), com o marcador do L300",
                 "trechos reindexados das mesmas quatro fontes, com a classe de acesso de cada uma"],
        "reutiliza": ["contêiner base-documental-l300 e manifesto de permissões documentais", "serviço de busca, conexões privadas e deployment de embeddings"],
        "altera": [],
        "custo": ["tokens de embeddings na reindexação das quatro fontes", "o índice extra ocupa armazenamento do serviço de busca"],
        "efeito_na_migracao": [f"o índice de referência '{INDICE_REFERENCIA}' não é alterado; o candidato conserva o prefixo do L300 de propósito, "
                               "porque o filtro de acesso documental só vale nesse namespace"],
        "precondicoes": ["índice de referência criado e conferido", "indexador no ambiente privado funcionando (conexões compartilhadas aprovadas)"],
        "portoes": ["cada comando simula por padrão: só --executar altera o serviço"],
        "comandos": [_COMANDO_INGESTAO + f"criar --busca <busca> --assinatura <assinatura> --grupo <grupo> --conta <conta> --modelos <modelos> {_INDICE_E_DIMENSOES}",
                     _COMANDO_INGESTAO + f"executar --busca <busca> {_INDICE_E_DIMENSOES.split(' --dimensoes')[0]} --executar --aguardar",
                     _COMANDO_INGESTAO + f"conferir --busca <busca> {_INDICE_E_DIMENSOES}"],
        "limpeza": [_COMANDO_INGESTAO + f"remover --busca <busca> --indice {INDICE_CANDIDATO} --executar (só os quatro objetos de busca do candidato)"],
    },
    "conferir-migracao": {
        "objetivo": "Conferir, offline, o descritor de promoção (ou de retorno) do índice, preenchido por você com o que observou.",
        "executor": "offline", "nuvem": False,
        "variaveis": [],
        "cria": ["relatório JSON novo e sanitizado (opcional), que nunca sobrescreve arquivo"],
        "reutiliza": ["manifesto de permissões do L300 (as quatro fontes, as classes e os hashes)"],
        "altera": [],
        "custo": ["nenhum"],
        "efeito_na_migracao": ["nenhum: só lê"],
        "precondicoes": ["índice candidato criado, carregado e conferido pela ingestão do L300, com contagens antes e depois anotadas por você"],
        "portoes": ["aprovado (código 0) antes de promover e de novo antes de retornar; origem do descritor explícita (operador ou simulado)"],
        "comandos": ["python scripts\\operar_l400.py --etapa conferir-migracao --descritor <descritor.json> --relatorio <novo.json>"],
        "limpeza": ["apagar o descritor e o relatório privados ao fim"],
    },
    "aplicacao": {
        "objetivo": "Publicar a aplicação do L400, separada da do L300, no ambiente do L300, com login, acesso documental e coordenação exigidos.",
        "executor": "bicep", "nuvem": True,
        "variaveis": [VAR_FASE, VAR_PERFIL_INDICE, VAR_INGRESSO_EXTERNO, *VARS_DOS_DESTINOS, *VARS_DA_CONTINGENCIA, *VARS_DA_APLICACAO,
                      "VARELEIRA_ACAO_SEM_LOGIN"],
        "cria": ["aplicação do chat do L400 (Consumption, de 0 a 1 réplica) com a imagem da tag informada e o ingresso fechado",
                 "autenticação integrada do Microsoft Entra ID",
                 "variáveis VARELEIRA_EXIGIR_ACESSO_DOCUMENTAL=true, VARELEIRA_EXIGIR_COORDENACAO=true e VARELEIRA_DEPLOYMENT_CONTINGENCIA"],
        "reutiliza": ["ambiente do L300, registro, identidade e papéis do L300 (nenhum papel novo)", "deployments principal, de contingência e de embeddings"],
        "altera": [],
        "custo": ["Consumption: a computação da aplicação não tem custo fixo com zero réplica; sem perfil dedicado, GPU nem capacidade provisionada",
                  "isso vale só para a computação da aplicação: as dependências (registro, busca, modelos, rede privada, monitoramento) e o medidor "
                  "de gestão do ambiente do Container Apps podem cobrar, com ou sem réplicas"],
        "efeito_na_migracao": ["a aplicação do L300 continua como referência; com o perfil referencia, a do L400 consulta o mesmo índice do L300"],
        "precondicoes": ["fase contingencia aplicada", "imagem com a coordenação (lab_orquestracao) publicada com tag imutável",
                         "registro de aplicativo do Entra ID com o endereço de retorno da saída urlRetornoLogin, e os papéis de aplicação"],
        "portoes": [f"{VAR_INGRESSO_EXTERNO}=true é um portão à parte, só depois de conferir o login e a autorização documental",
                    "o segredo do login só existe na sessão: nunca em arquivo, argumento, prompt ou relatório"],
        "comandos": ["python scripts\\operar_l400.py --etapa sanitizar-whatif --arquivo <whatif.json> --relatorio <novo.json> --rotulo aplicacao"],
        "limpeza": ["excluir a aplicação do L400 (coordenador); a do L300 não é tocada"],
    },
    "comparar": {
        "objetivo": "Comparar a referência (L300) com a coordenação (L400), no mesmo conjunto NOVO de casos, com o plano congelado antes.",
        "executor": "avaliador", "nuvem": True,
        "variaveis": list(al4.VAR_TOKEN.values()),
        "cria": ["relatório JSON novo, sem perguntas, corpos, endereços nem tokens"],
        "reutiliza": ["as duas aplicações, pelo mesmo POST /api/perguntar e o mesmo corpo; a estratégia vem da aplicação, nunca do cliente"],
        "altera": [],
        "custo": ["uma chamada por estratégia e caso: tokens de modelo e de embeddings, sem repetição automática",
                  "preços por 1 milhão de tokens informados por você; nenhum preço existe nos scripts"],
        "efeito_na_migracao": ["nenhum"],
        "precondicoes": ["conjunto criado e congelado DEPOIS do código, fora do corpus, da imagem e das avaliações finais do L100 e do L200",
                         "as duas aplicações alcançáveis pelo endereço padrão do Container Apps, com login, durante a medição"],
        "portoes": ["sem --executar, só mostra o plano e os três SHA-256 (conjunto, plano e código) para congelar",
                    "token de cada aplicação em variável de ambiente; sem token, o avaliador nem começa"],
        "comandos": ["python scripts\\avaliar_l400.py --casos <casos.json> --url-referencia <url> --url-coordenacao <url> --artefato-referencia <tag> "
                     "--artefato-coordenacao <tag> --relatorio <novo.json>",
                     "python scripts\\operar_l400.py --etapa validar-comparacao --comparacao <relatorio.json> --conjunto-esperado <sha256> "
                     "--plano-avaliacao-esperado <sha256> --codigo-esperado <sha256>"],
        "limpeza": ["apagar o relatório bruto privado e os tokens da sessão (Remove-Item Env:\\NOME)"],
    },
    "promover-indice": {
        "objetivo": "Apontar a aplicação do L400 para o índice candidato, só depois de conferir a migração.",
        "executor": "bicep", "nuvem": True,
        "variaveis": [VAR_FASE, VAR_PERFIL_INDICE],
        "cria": [],
        "reutiliza": ["a aplicação do L400 e o índice candidato"],
        "altera": [f"VARELEIRA_INDICE e VARELEIRA_DIMENSOES da aplicação do L400 (perfil candidato: {INDICE_CANDIDATO}, {DIMENSOES_CANDIDATA})"],
        "custo": ["nova revisão da aplicação; sem custo fixo"],
        "efeito_na_migracao": ["a referência e o índice vareleira-lar-l300 não são alterados; o retorno é a mesma troca ao contrário"],
        "precondicoes": ["--etapa conferir-migracao aprovada com ação promover e origem operador"],
        "portoes": ["trocar o perfil troca só configuração e NÃO prova compatibilidade dos vetores: a prova é a conferência acima"],
        "comandos": [f"definir {VAR_PERFIL_INDICE}=candidato e repetir a fase aplicacao"],
        "limpeza": ["nenhuma além da limpeza da aplicação"],
    },
    "retornar-indice": {
        "objetivo": "Voltar a aplicação do L400 ao índice de referência.",
        "executor": "bicep", "nuvem": True,
        "variaveis": [VAR_FASE, VAR_PERFIL_INDICE],
        "cria": [],
        "reutiliza": ["a aplicação do L400 e o índice de referência, que nunca foi alterado"],
        "altera": [f"VARELEIRA_INDICE e VARELEIRA_DIMENSOES da aplicação do L400 (perfil referencia: {INDICE_REFERENCIA}, {DIMENSOES_REFERENCIA})"],
        "custo": ["nova revisão da aplicação; sem custo fixo"],
        "efeito_na_migracao": ["o índice candidato continua existindo até a limpeza"],
        "precondicoes": ["--etapa conferir-migracao aprovada com ação retornar (a referência intacta, com as mesmas contagens)"],
        "portoes": ["o retorno também é explícito: nenhuma troca automática"],
        "comandos": [f"definir {VAR_PERFIL_INDICE}=referencia e repetir a fase aplicacao"],
        "limpeza": ["nenhuma além da limpeza da aplicação"],
    },
    "carga-interrupcao": {
        "objetivo": "Ensaiar a parada do CLIENTE no avaliador serial (uma chamada por vez, poucos casos), com as falhas e o que ficou sem avaliar "
                    "contados como falha. Não é carga concorrente nem cancelamento no SERVIDOR.",
        "executor": "avaliador", "nuvem": True,
        "variaveis": list(al4.VAR_TOKEN.values()),
        "cria": ["relatório JSON novo, com os códigos HTTP e as falhas contadas como falha"],
        "reutiliza": ["o mesmo avaliador serial, sem paralelismo, com poucos casos; quem para é o cliente: o limite de tempo, as falhas seguidas e o "
                      "Ctrl+C interrompem as chamadas futuras"],
        "altera": [],
        "custo": ["tokens das poucas chamadas; sem repetição automática"],
        "efeito_na_migracao": ["nenhum"],
        "precondicoes": ["comparação normal concluída e validada"],
        "portoes": ["não é carga concorrente: o avaliador é serial e não mede vazão nem comportamento sob concorrência",
                    "não prova o cancelamento no SERVIDOR: o avaliador só usa o POST /api/perguntar em JSON e não avalia o fluxo de progresso (SSE), "
                    "e parar o cliente não mostra o que o servidor fez com um pedido já enviado; essa prova pede outro auxiliar e é dos testes do "
                    "runtime e de uma prova manual com o cliente web, registradas à parte"],
        "comandos": ["python scripts\\avaliar_l400.py ... --executar (com um conjunto pequeno), interrompendo com Ctrl+C quando for o caso"],
        "limpeza": ["apagar o relatório bruto privado"],
    },
    "limpeza": {
        "objetivo": "Remover os recursos temporários do L400 e conferir que nada próprio ficou, inclusive o que tem exclusão reversível.",
        "executor": "coordenador", "nuvem": True,
        "variaveis": [],
        "cria": [],
        "reutiliza": [],
        "altera": [],
        "custo": ["o que não for removido segue cobrando"],
        "efeito_na_migracao": ["fora do escopo dos scripts: nenhum script deste nível apaga recursos, índices ou dados"],
        "precondicoes": ["relatórios e provas guardados em local privado", "autorização de quem responde pela assinatura"],
        "portoes": ["só os recursos próprios e temporários; preservar o que já existia antes do L400"],
        "comandos": [_COMANDO_INGESTAO + f"remover --busca <busca> --indice {INDICE_CANDIDATO} --executar (índice candidato)"],
        "limpeza": ["aplicação do L400, deployment de contingência, índice candidato, base recriada e expurgos conferidos, pelo coordenador"],
    },
}
PASSOS = tuple(PLANO_DOS_PASSOS)

CREDENCIAIS = {
    "login_da_aplicacao": {"quem": "registro de aplicativo do Microsoft Entra ID do chat (EasyAuth), outro objeto que a identidade de implantação",
                           "segredo": f"{o3.VAR_SEGREDO_LOGIN}: só na sessão, parâmetro @secure do Bicep; nunca em arquivo, argumento, console ou relatório"},
    "avaliador": {"quem": "token Bearer de cada aplicação, obtido por quem opera",
                  "variaveis": list(al4.VAR_TOKEN.values()),
                  "segredo": "só em variáveis de ambiente, em memória; nunca em argumento, arquivo, console ou relatório"},
}
NAO_FAZ = (
    "não acessa a nuvem, o GitHub nem a rede, e não implanta, carrega, atribui papéis nem apaga nada",
    "não cria nem lê o conjunto final de avaliação, nem abre as avaliações finais do L100 e do L200",
    "não infere cota, preço nem orçamento novos e não troca modelos, versões nem deployments",
    "não trata a troca de um índice ou de uma configuração como prova de compatibilidade",
)


def montar_plano(passo: str) -> dict[str, Any]:
    if passo != "todos" and passo not in PASSOS:
        raise ErroLab(f"Passo inválido: use um destes: {', '.join((*PASSOS, 'todos'))}.")
    passos = PASSOS if passo == "todos" else (passo,)
    return {
        "versao": VERSAO_DO_RELATORIO,
        "tipo": "plano-declarativo-l400",
        "origem": "contrato de interface do L400; o what-if do ARM é a fonte da verdade e substitui esta descrição",
        "nuvem": {"chamadas": 0, "executa": False},
        "executores": copy.deepcopy(EXECUTORES),
        "precondicoes_gerais": list(PRECONDICOES_GERAIS),
        "credenciais": copy.deepcopy(CREDENCIAIS),
        "variaveis_do_bicepparam": {"obrigatorias_por_fase": {"contingencia": [*VARS_DOS_DESTINOS, *VARS_DA_CONTINGENCIA],
                                                              "aplicacao": [*VARS_DOS_DESTINOS, *VARS_DA_CONTINGENCIA, *VARS_DA_APLICACAO]},
                                    "opcionais": list(VARS_OPCIONAIS), "privadas": list(VARS_PRIVADAS)},
        "passos": [{"passo": nome, **copy.deepcopy(PLANO_DOS_PASSOS[nome])} for nome in passos],
        "nao_faz": list(NAO_FAZ),
    }


def imprimir_plano(plano: Mapping[str, Any]) -> None:
    print("Plano declarativo do L400 (local: nenhuma chamada de rede, nada é consultado nem alterado)")
    print(f"Origem: {plano['origem']}.")
    print("Pré-condições gerais:")
    for item in plano["precondicoes_gerais"]:
        print(f"  - {item}")
    variaveis = plano["variaveis_do_bicepparam"]
    print("Variáveis do infra/levels/l400.bicepparam (só os nomes; os valores ficam na sua sessão):")
    for fase, nomes in variaveis["obrigatorias_por_fase"].items():
        print(f"  - fase {fase}: {', '.join(nomes)}")
    print(f"  - opcionais: {', '.join(variaveis['opcionais'])}")
    rotulos = (("cria", "Cria"), ("reutiliza", "Reutiliza"), ("altera", "Altera"), ("custo", "Custo"), ("efeito_na_migracao", "Efeito na migração"),
               ("precondicoes", "Pré-condições"), ("portoes", "Portões"), ("variaveis", "Variáveis"), ("comandos", "Comandos de referência"),
               ("limpeza", "Limpeza"))
    for passo in plano["passos"]:
        print(f"\nPasso '{passo['passo']}': {passo['objetivo']}")
        print(f"  Quem executa: {plano['executores'][passo['executor']]}. Usa a nuvem: {'sim' if passo['nuvem'] else 'não'}.")
        for chave, titulo in rotulos:
            itens = passo.get(chave) or []
            if itens:
                print(f"  {titulo}:")
                for item in itens:
                    print(f"    - {item}")
    print("\nNão faz:")
    for item in plano["nao_faz"]:
        print(f"  - {item}")


def validar_bicep() -> dict[str, Any]:
    """Compila e roda o lint de infra/l400.bicep (e dos módulos que ele usa) no seu computador, sem Azure e sem credenciais."""
    try:
        resultado = o3.validar_bicep(BICEP_L400)
    except ErroLab as erro:
        raise ErroLab(str(erro).replace("infra/l300.bicep", "infra/l400.bicep"), erro.codigo) from None
    resultado["arquivo"] = "infra/l400.bicep"
    return resultado


def etapa_planejar(args: argparse.Namespace, env: Mapping[str, str]) -> int:
    relatorio = o3._exigir_relatorio_novo(Path(args.relatorio) if args.relatorio else None)
    plano = montar_plano(args.passo)
    if args.validar_bicep:
        plano["bicep"] = validar_bicep()
    if args.formato == "json":
        print(json.dumps(plano, ensure_ascii=False, indent=2))
    else:
        imprimir_plano(plano)
        if args.validar_bicep:
            b = plano["bicep"]
            print(f"\nBicep (local, sem Azure): {b['arquivo']} compila com a versão {b['versao_do_bicep']} e o lint está limpo (sem avisos, como no CI).")
    if relatorio is not None:
        o3._gravar_relatorio(relatorio, plano)
    return CODIGO_OK


# --------------------------------------------------------------------------------------
# Etapa sanitizar-whatif (o mesmo critério do L300)
# --------------------------------------------------------------------------------------

def etapa_sanitizar_whatif(args: argparse.Namespace, env: Mapping[str, str]) -> int:
    args.rotulo = args.rotulo or env.get(VAR_FASE) or "sem-rotulo"
    return o3.etapa_sanitizar_whatif(args, env)


# --------------------------------------------------------------------------------------
# Etapa conferir-migracao
# --------------------------------------------------------------------------------------

LIMITE_DA_MIGRACAO = ("Esta conferência só lê os campos do descritor que você preencheu: ela NÃO consulta o Azure, NÃO gera evidência de nuvem e "
                      "NÃO prova que os vetores são compatíveis. A prova são os comandos, saídas e contagens que você observou e guarda em "
                      "local privado; trocar o índice na configuração da aplicação não é essa prova.")
_CAMPOS_DA_RAIZ = ("versao", "origem", "acao", "manifesto_deployment", "configuracao_atual", "configuracao_alvo", "indices")
_CAMPOS_DO_MANIFESTO = ("embeddings", "geracao_principal", "geracao_contingencia")
_CAMPOS_DO_DEPLOYMENT = ("deployment", "modelo", "versao")
_CAMPOS_DA_CONFIGURACAO = ("indice", "dimensoes", "deployment_embeddings")
_CAMPOS_DO_INDICE = ("indice", "dimensoes", "modelo_embeddings", "versao_modelo_embeddings", "origem_observada", "fontes", "contagem_antes",
                     "contagem_depois")
_CAMPOS_DA_FONTE = ("documento_id", "classe", "sha256")


def _chave_segura(chave: Any) -> str:
    return chave if isinstance(chave, str) and re.fullmatch(r"[a-z_]{1,40}", chave) else "<campo>"


class _Forma:
    """Confere a forma do descritor e junta TODOS os problemas, sem repetir nenhum valor."""

    def __init__(self) -> None:
        self.problemas: list[str] = []

    def objeto(self, valor: Any, onde: str, campos: Sequence[str]) -> dict[str, Any]:
        if not isinstance(valor, dict):
            self.problemas.append(f"'{onde}' deve ser um objeto.")
            return {}
        for chave in valor:
            if chave not in campos:
                self.problemas.append(f"campo desconhecido em '{onde}': {_chave_segura(chave)}.")
        for chave in campos:
            if chave not in valor:
                self.problemas.append(f"falta o campo '{onde}.{chave}'.")
        return valor

    def texto(self, valor: Any, onde: str, padrao: re.Pattern[str]) -> str | None:
        if not isinstance(valor, str) or not padrao.fullmatch(valor):
            self.problemas.append(f"'{onde}' ausente ou com formato inválido.")
            return None
        return valor

    def inteiro(self, valor: Any, onde: str, minimo: int, maximo: int) -> int | None:
        if isinstance(valor, bool) or not isinstance(valor, int) or not minimo <= valor <= maximo:
            self.problemas.append(f"'{onde}' deve ser um inteiro de {minimo} a {maximo}.")
            return None
        return valor

    def escolha(self, valor: Any, onde: str, opcoes: Sequence[str]) -> str | None:
        if not isinstance(valor, str) or valor not in opcoes:
            self.problemas.append(f"'{onde}' deve ser um destes: {', '.join(opcoes)}.")
            return None
        return valor

    def deployment(self, valor: Any, onde: str) -> dict[str, Any]:
        item = self.objeto(valor, onde, _CAMPOS_DO_DEPLOYMENT)
        self.texto(item.get("deployment"), f"{onde}.deployment", _PADRAO_DEPLOYMENT)
        self.texto(item.get("modelo"), f"{onde}.modelo", _PADRAO_DEPLOYMENT)
        self.texto(item.get("versao"), f"{onde}.versao", _PADRAO_VERSAO)
        return item

    def configuracao(self, valor: Any, onde: str) -> dict[str, Any]:
        item = self.objeto(valor, onde, _CAMPOS_DA_CONFIGURACAO)
        self.texto(item.get("indice"), f"{onde}.indice", _PADRAO_INDICE)
        self.inteiro(item.get("dimensoes"), f"{onde}.dimensoes", 1, 3072)
        self.texto(item.get("deployment_embeddings"), f"{onde}.deployment_embeddings", _PADRAO_DEPLOYMENT)
        return item

    def contagem(self, valor: Any, onde: str) -> dict[str, int] | None:
        item = self.objeto(valor, onde, ("por_documento",))
        por_documento = item.get("por_documento")
        if not isinstance(por_documento, dict) or not por_documento:
            self.problemas.append(f"'{onde}.por_documento' deve ser um objeto com a contagem de trechos de cada documento.")
            return None
        resultado = {}
        for documento, quantidade in por_documento.items():
            if not isinstance(documento, str) or not _PADRAO_DOCUMENTO.fullmatch(documento):
                self.problemas.append(f"'{onde}.por_documento' tem um identificador de documento com formato inválido.")
            elif isinstance(quantidade, bool) or not isinstance(quantidade, int) or not 0 <= quantidade <= _LIMITE_DE_TRECHOS:
                self.problemas.append(f"'{onde}.por_documento' tem uma contagem que não é um inteiro de 0 a {_LIMITE_DE_TRECHOS}.")
            else:
                resultado[documento] = quantidade
        return resultado

    def indice(self, valor: Any, onde: str, antes_obrigatoria: bool) -> dict[str, Any]:
        item = self.objeto(valor, onde, _CAMPOS_DO_INDICE)
        self.texto(item.get("indice"), f"{onde}.indice", _PADRAO_INDICE)
        self.inteiro(item.get("dimensoes"), f"{onde}.dimensoes", 1, 3072)
        self.texto(item.get("modelo_embeddings"), f"{onde}.modelo_embeddings", _PADRAO_DEPLOYMENT)
        self.texto(item.get("versao_modelo_embeddings"), f"{onde}.versao_modelo_embeddings", _PADRAO_VERSAO)
        self.escolha(item.get("origem_observada"), f"{onde}.origem_observada", ORIGENS)
        fontes = item.get("fontes")
        if not isinstance(fontes, list) or not 1 <= len(fontes) <= 20:
            self.problemas.append(f"'{onde}.fontes' deve ser uma lista de 1 a 20 fontes.")
        else:
            vistos: set[str] = set()
            for posicao, fonte in enumerate(fontes):
                registro = self.objeto(fonte, f"{onde}.fontes[{posicao}]", _CAMPOS_DA_FONTE)
                identificador = self.texto(registro.get("documento_id"), f"{onde}.fontes[{posicao}].documento_id", _PADRAO_DOCUMENTO)
                self.escolha(registro.get("classe"), f"{onde}.fontes[{posicao}].classe", lab_acesso.CLASSES)
                self.texto(registro.get("sha256"), f"{onde}.fontes[{posicao}].sha256", _PADRAO_SHA256)
                if identificador in vistos:
                    self.problemas.append(f"'{onde}.fontes' repete um documento.")
                vistos.add(identificador or "")
        antes = item.get("contagem_antes")
        if antes is not None or antes_obrigatoria:
            self.contagem(antes, f"{onde}.contagem_antes")
        self.contagem(item.get("contagem_depois"), f"{onde}.contagem_depois")
        return item


def hash_das_fontes_e_classes(fontes: Iterable[Mapping[str, Any]]) -> str:
    """SHA-256 canônico da lista de fontes com a classe e o hash de conteúdo de cada uma, em ordem de documento."""
    return al4._sha256_canonico(sorted([fonte["documento_id"], fonte["classe"], fonte["sha256"]] for fonte in fontes))


def fontes_do_manifesto(caminho: Path = l300.MANIFESTO_PADRAO) -> list[dict[str, str]]:
    """As fontes aprovadas, lidas do manifesto do L300 (que confere os arquivos e os hashes). Só as quatro aprovadas são aceitas."""
    manifesto = l300.carregar_e_validar(caminho)
    fontes = [{"documento_id": documento.id, "classe": documento.acesso, "sha256": documento.sha256} for documento in manifesto.documentos]
    if sorted(fonte["documento_id"] for fonte in fontes) != sorted(FONTES_APROVADAS):
        raise ErroLab("O manifesto de permissões não declara exatamente as quatro fontes aprovadas do L400: nenhuma fonte entra ou sai "
                      "sem nova revisão.")
    return fontes


def conferir_migracao(dados: Any, fontes_esperadas: Sequence[Mapping[str, str]]) -> dict[str, Any]:
    """Confere o descritor de promoção ou de retorno. Dados ausentes ou incompletos são recusados; nada recebe valor padrão."""
    forma = _Forma()
    raiz = forma.objeto(dados, "descritor", _CAMPOS_DA_RAIZ)
    if raiz.get("versao") != 1 or isinstance(raiz.get("versao"), bool):
        forma.problemas.append("'versao' deve ser 1.")
    origem = forma.escolha(raiz.get("origem"), "origem", ORIGENS)
    acao = forma.escolha(raiz.get("acao"), "acao", ACOES)
    manifesto = forma.objeto(raiz.get("manifesto_deployment"), "manifesto_deployment", _CAMPOS_DO_MANIFESTO)
    embeddings = forma.deployment(manifesto.get("embeddings"), "manifesto_deployment.embeddings")
    principal = forma.deployment(manifesto.get("geracao_principal"), "manifesto_deployment.geracao_principal")
    contingencia = forma.deployment(manifesto.get("geracao_contingencia"), "manifesto_deployment.geracao_contingencia")
    atual = forma.configuracao(raiz.get("configuracao_atual"), "configuracao_atual")
    alvo = forma.configuracao(raiz.get("configuracao_alvo"), "configuracao_alvo")
    indices = forma.objeto(raiz.get("indices"), "indices", ("referencia", "candidato"))
    referencia = forma.indice(indices.get("referencia"), "indices.referencia", antes_obrigatoria=True)
    candidato = forma.indice(indices.get("candidato"), "indices.candidato", antes_obrigatoria=False)
    if forma.problemas:
        raise ErroLab("O descritor tem problemas de forma (nenhum valor é repetido aqui; nada foi inferido nem preenchido):\n"
                      + "\n".join(f"  - {problema}" for problema in forma.problemas[:40])
                      + (f"\n  - ... e mais {len(forma.problemas) - 40} problema(s)." if len(forma.problemas) > 40 else ""))

    verificacoes: list[dict[str, str]] = []

    def registrar(identificador: str, descricao: str, atendido: bool) -> None:
        verificacoes.append({"id": identificador, "descricao": descricao, "estado": "atendido" if atendido else "reprovado",
                             "origem": "descritor do operador"})

    observadas = {referencia["origem_observada"], candidato["origem_observada"]}
    registrar("origem.explicita", "a origem do descritor e a de cada observação são explícitas e coerentes (observação simulada só em descritor simulado)",
              origem == "simulado" or observadas == {"operador"})
    por_nome = {referencia["indice"]: referencia, candidato["indice"]: candidato}
    de, para = (atual, alvo)
    registrar("acao.coerente", "a ação combina com as configurações: promover vai da referência ao candidato; retornar, do candidato à referência",
              (atual["indice"], alvo["indice"]) == ((referencia["indice"], candidato["indice"]) if acao == "promover"
                                                    else (candidato["indice"], referencia["indice"])))
    registrar("indices.namespace_e_nomes_distintos",
              f"os dois índices estão no namespace do L300 e têm nomes diferentes; a referência é o índice '{INDICE_REFERENCIA}', que não é alterado",
              lab_acesso.indice_l300(referencia["indice"]) and lab_acesso.indice_l300(candidato["indice"])
              and referencia["indice"] != candidato["indice"] and referencia["indice"] == INDICE_REFERENCIA)
    registrar("manifesto.contingencia_distinta_com_mesmo_modelo",
              "o deployment de contingência tem nome diferente do principal e o mesmo modelo e versão",
              principal["deployment"] != contingencia["deployment"] and (principal["modelo"], principal["versao"]) == (contingencia["modelo"], contingencia["versao"]))
    registrar("manifesto.embeddings_iguais_nos_indices",
              "os dois índices foram construídos com o modelo, a versão e o deployment de embeddings do manifesto de deployment da vez",
              all((item["modelo_embeddings"], item["versao_modelo_embeddings"]) == (embeddings["modelo"], embeddings["versao"]) for item in por_nome.values())
              and atual["deployment_embeddings"] == embeddings["deployment"] == alvo["deployment_embeddings"])
    limites = lab_ingestao.DIMENSOES_DOS_MODELOS.get(embeddings["modelo"])
    registrar("dimensoes.cabem_no_modelo", "as dimensões observadas de cada índice cabem no modelo de embeddings do manifesto",
              limites is not None and all(limites[0] <= item["dimensoes"] <= limites[1] for item in por_nome.values()))
    registrar("configuracao.igual_ao_indice_observado",
              "a configuração atual e a alvo (nome do índice e dimensões) são iguais ao que foi observado em cada índice: trocar a configuração não é prova",
              all(configuracao["indice"] in por_nome and configuracao["dimensoes"] == por_nome[configuracao["indice"]]["dimensoes"]
                  for configuracao in (de, para)))
    esperado = hash_das_fontes_e_classes(fontes_esperadas)
    hashes = {nome: hash_das_fontes_e_classes(item["fontes"]) for nome, item in (("referencia", referencia), ("candidato", candidato))}
    registrar("fontes.mesmas_do_manifesto", "os dois índices têm exatamente as quatro fontes aprovadas, com a mesma classe e o mesmo hash de conteúdo "
              "do manifesto do L300", all(valor == esperado for valor in hashes.values()))
    documentos = {fonte["documento_id"] for fonte in fontes_esperadas}

    def cobre(contagem: Mapping[str, int]) -> bool:
        return set(contagem) == documentos and all(quantidade >= 1 for quantidade in contagem.values())

    antes, depois = referencia["contagem_antes"]["por_documento"], referencia["contagem_depois"]["por_documento"]
    candidatas = candidato["contagem_depois"]["por_documento"]
    registrar("contagens.referencia_preservada", "a referência tem trechos de cada fonte e as mesmas contagens antes e depois: a evolução do índice "
              "não a modifica", cobre(antes) and cobre(depois) and antes == depois)
    registrar("contagens.candidato_igual_a_referencia", "o candidato tem trechos de cada fonte e a mesma contagem por documento da referência (mesmo "
              "conteúdo, só outras dimensões)", cobre(candidatas) and candidatas == depois)
    totais = {"referencia_antes": sum(antes.values()), "referencia_depois": sum(depois.values()), "candidato_depois": sum(candidatas.values())}
    contagem = Counter(item["estado"] for item in verificacoes)
    avisos = []
    if origem == "simulado":
        avisos.append("Descritor SIMULADO (exemplo): serve para ensaiar o fluxo e nunca vale como evidência de uma migração real.")
    return {
        "versao_relatorio": VERSAO_DO_RELATORIO, "tipo": "conferencia-de-migracao", "acao": acao, "origem_do_descritor": origem,
        "resultado": "reprovado" if contagem["reprovado"] else "aprovado",
        "contagem": {estado: contagem.get(estado, 0) for estado in ("atendido", "reprovado")},
        "verificacoes": verificacoes,
        "hashes_das_fontes_e_classes": {"esperado": esperado, **hashes},
        "totais_de_trechos": totais,
        "evidencia_azure": False,
        "avisos": avisos,
        "limite": LIMITE_DA_MIGRACAO,
    }


def etapa_conferir_migracao(args: argparse.Namespace, env: Mapping[str, str]) -> int:
    if not args.descritor:
        raise ErroLab("Informe --descritor (o JSON de promoção ou de retorno que você preencheu).")
    relatorio = o3._exigir_relatorio_novo(Path(args.relatorio) if args.relatorio else None)
    _, dados = o3._ler_json(Path(args.descritor))
    resultado = conferir_migracao(dados, fontes_do_manifesto(Path(args.manifesto)))
    print(f"Conferência da migração de índice (ação: {resultado['acao']}; origem do descritor: {resultado['origem_do_descritor']})")
    for item in resultado["verificacoes"]:
        print(f"  [{item['estado']}] {item['id']}: {item['descricao']}")
    for aviso in resultado["avisos"]:
        print(f"[AVISO] {aviso}")
    contagem = resultado["contagem"]
    print(f"Resumo: {contagem['atendido']} atendido(s), {contagem['reprovado']} reprovado(s).")
    if relatorio is not None:
        o3._gravar_relatorio(relatorio, resultado)
    if resultado["resultado"] != "aprovado":
        raise ErroLab("Conferência reprovada: a troca NÃO está liberada. Corrija o que for observação errada ou refaça a indexação e repita. "
                      + resultado["limite"], CODIGO_DIVERGENCIA)
    print("Resultado: aprovado, segundo o que você declarou. " + resultado["limite"])
    return CODIGO_OK


# --------------------------------------------------------------------------------------
# Etapa resumir-logs (somente leitura): o resumo do L300 mais as linhas próprias do L400
# --------------------------------------------------------------------------------------

_COORDENACAO = re.compile(
    "^" + o3._TEMPO + r"(?:INFO|WARNING|ERROR) vareleira\.chat coordenacao id=[0-9A-Za-z_-]{1,64} resultado=(concluido|erro|cancelado) "
    r"chamadas=([0-9]{1,4}) buscas=([0-9]{1,4}) contingencia=(sim|nao) uso_incerto=(sim|nao)$")
# As duas linhas de partida do chat com acesso documental e coordenação, no texto exato dele: sem trecho livre, qualquer outra
# linha com esses começos continua desconhecida.
_PARTIDA = (
    re.compile(r"^Acesso documental ativo: os papéis de aplicação da identidade definem as classes de documento da busca, "
               r"e quem não tem papel reconhecido recebe 403 antes de qualquer consulta\.$"),
    re.compile(r"^Coordenação L400 ativa: planejamento, recuperação filtrada, verificação e redação com limites finitos; "
               r"contingência de geração (?:configurada|não configurada); progresso por eventos em POST /api/perguntar/progresso\.$"),
)


def resumir_logs(linhas: Iterable[str]) -> dict[str, Any]:
    """O resumo de logs do L300 (que falha fechado diante de linha desconhecida) mais a contagem dos eventos da coordenação e das duas
    linhas de partida do L400, ambos de vocabulário fechado."""
    todas = list(linhas)
    eventos: list[tuple[str, ...]] = []
    de_partida = 0
    restantes = []
    for linha in todas:
        mensagem = o3._mensagem_da_linha(linha) if len(linha) <= o3.LIMITE_LINHA_DE_LOG else None
        achado = _COORDENACAO.match(mensagem) if mensagem is not None else None
        if achado:
            eventos.append(achado.groups())
        elif mensagem is not None and any(padrao.match(mensagem) for padrao in _PARTIDA):
            de_partida += 1
        else:
            restantes.append(linha)
            continue
        restantes.append("")  # mantém a numeração das linhas; a linha em branco é descontada abaixo
    resumo = o3.resumir_logs(restantes)
    resumo["linhas"]["vazias"] -= len(eventos) + de_partida
    ignoradas = Counter(resumo["linhas"]["ignoradas_conhecidas"])
    ignoradas.update({"coordenacao": len(eventos), "partida": de_partida})
    resumo["linhas"]["ignoradas_conhecidas"] = dict(sorted((nome, n) for nome, n in ignoradas.items() if n))
    resumo["coordenacao"] = {
        "eventos": len(eventos),
        "por_resultado": {nome: sum(1 for e in eventos if e[0] == nome) for nome in ("concluido", "erro", "cancelado")},
        "com_contingencia": sum(1 for e in eventos if e[3] == "sim"),
        "com_uso_incerto": sum(1 for e in eventos if e[4] == "sim"),
        "chamadas_total": sum(int(e[1]) for e in eventos), "buscas_total": sum(int(e[2]) for e in eventos),
    }
    resumo["tipo"] = "resumo-de-logs"
    resumo["nivel"] = "L400"
    return resumo


def etapa_resumir_logs(args: argparse.Namespace, env: Mapping[str, str]) -> int:
    if not args.logs:
        raise ErroLab("Informe --logs (um arquivo de logs sanitizados do chat).")
    relatorio = o3._exigir_relatorio_novo(Path(args.relatorio) if args.relatorio else None)
    caminho = Path(args.logs)
    try:
        texto = o3._decodificar(o3._ler_bytes(caminho, o3.LIMITE_LOGS_BYTES))
    except UnicodeDecodeError:
        raise ErroLab(f"O arquivo {caminho.name} não está em UTF-8 nem em UTF-16 com marca de ordem.") from None
    resumo = resumir_logs(texto.splitlines())
    linhas, req, coordenacao = resumo["linhas"], resumo["requisicoes"], resumo["coordenacao"]
    sondas = ", ".join(f"{rota}={n}" for rota, n in req["sondas_de_saude"].items()) or "nenhuma"
    print("Resumo de logs do chat (somente leitura; nenhuma pergunta, resposta, token ou URL é exibido)")
    print(f"Linhas: {linhas['total']} (vazias: {linhas['vazias']}); requisições: {req['total']}; sondas de saúde: {sondas}")
    print("Status: " + (", ".join(f"{status}={n}" for status, n in resumo["por_status"].items()) or "nenhum"))
    for rota, dados in resumo["por_rota"].items():
        lat = dados["latencia_ms"]
        print(f"  rota {rota}: {dados['total']} requisição(ões); latência ms p50={lat['p50']} p95={lat['p95']} máx={lat['maximo']}")
    for status, causas in resumo["causas_por_status"].items():
        print(f"  causas de {status}: " + ", ".join(f"{causa}={n}" for causa, n in causas.items()))
    print(f"Coordenação: {coordenacao['eventos']} evento(s) (" + ", ".join(f"{n} {nome}" for nome, n in coordenacao["por_resultado"].items()) +
          f"); com contingência: {coordenacao['com_contingencia']}; com uso incerto: {coordenacao['com_uso_incerto']}; chamadas: "
          f"{coordenacao['chamadas_total']}; buscas: {coordenacao['buscas_total']}")
    if relatorio is not None:
        o3._gravar_relatorio(relatorio, resumo)
    if linhas["desconhecidas"]:
        raise ErroLab(f"{linhas['desconhecidas']} linha(s) não reconhecida(s) (primeiras: {linhas['primeiras_desconhecidas']}). O resumo falha "
                      "fechado: nada delas foi copiado. Sanitize o arquivo ou, se o formato do servidor mudou, atualize o resumo.", CODIGO_DIVERGENCIA)
    print("Resultado: concluído; todas as linhas foram reconhecidas.")
    return CODIGO_OK


# --------------------------------------------------------------------------------------
# Etapa validar-comparacao
# --------------------------------------------------------------------------------------

LIMITE_DA_VALIDACAO = ("Esta validação confere a coerência e a forma do relatório do avaliador, e os hashes que você informar. Ela NÃO refaz as chamadas, "
                       "NÃO consulta o Azure e NÃO julga a qualidade das respostas: o que o relatório mede é o contrato e a política do chat.")
_CHAVES_PROIBIDAS = frozenset({"pergunta", "perguntas", "texto", "corpo", "body", "url", "urls", "endereco", "token", "tokens_de_acesso",
                               "authorization", "cabecalhos", "headers", "citacao", "citacoes_texto", "evidencias", "resposta", "mensagem"})
_PARECE_URL = re.compile(r"(?i)\b[a-z][a-z0-9+.-]*://|\.azurecontainerapps\.io")
_PARECE_TOKEN = re.compile(r"(?i)\bbearer\s|eyJ[A-Za-z0-9_-]{8,}\.")
_ESTADOS_DE_CASO = (al4.ac.APROVADO, al4.ac.DIVERGENTE, al4.ac.FALHA_HTTP, al4.ac.ERRO, al4.ac.NAO_AVALIADO)
_MODOS_DE_DESTINO = ("hospedado_https", "demonstracao_ou_local_loopback", "simulado_sem_rede")
_CAMPOS_DO_USO = tuple(sorted(al4.ac.CAMPOS_DO_USO))


class _Falha(Exception):
    """A estrutura do relatório não é a esperada; a mensagem descreve o campo, nunca o conteúdo."""


def _exigir(condicao: bool, mensagem: str) -> None:
    if not condicao:
        raise _Falha(mensagem)


def _varrer_conteudo_bruto(valor: Any, caminho: str = "relatorio") -> list[str]:
    achados: list[str] = []
    pilha = [(valor, caminho)]
    while pilha and len(achados) < 10:
        atual, onde = pilha.pop()
        if isinstance(atual, dict):
            for chave, filho in atual.items():
                if isinstance(chave, str) and chave.casefold() in _CHAVES_PROIBIDAS:
                    achados.append(f"{onde}: campo '{_chave_segura(chave.casefold())}' não pode existir no relatório")
                pilha.append((filho, f"{onde}.{_chave_segura(chave)}"))
        elif isinstance(atual, list):
            pilha.extend((filho, f"{onde}[]") for filho in atual)
        elif isinstance(atual, str) and (_PARECE_URL.search(atual) or _PARECE_TOKEN.search(atual)):
            achados.append(f"{onde}: um texto parece um endereço ou um token")
    return achados


def _sha(valor: Any) -> bool:
    return isinstance(valor, str) and _PADRAO_SHA256.fullmatch(valor) is not None


def _numero_nao_negativo(valor: Any) -> bool:
    return isinstance(valor, (int, float)) and not isinstance(valor, bool) and math.isfinite(valor) and valor >= 0


def _verificar_tipo(r: Mapping[str, Any]) -> str:
    _exigir(isinstance(r, dict), "a raiz não é um objeto")
    if r.get("relatorio") == "avaliacao_http_do_chat":
        raise _Falha("é um relatório do avaliador do L200 (avaliacao_http_do_chat): não é reinterpretado como comparação do L400")
    _exigir(r.get("relatorio") == al4.NOME_DO_RELATORIO and r.get("schema_version") == al4.VERSAO_DO_ESQUEMA and not isinstance(r.get("schema_version"), bool),
            "o relatório não é uma comparação do L400 (relatorio e schema_version)")
    _exigir(set(r) == al4.CHAVES_DO_RELATORIO, "o conjunto de campos da raiz não é o do relatório do avaliador")
    return "relatório de comparação do L400, com os campos esperados"


def _verificar_hashes(r: Mapping[str, Any]) -> str:
    entrada, plano, avaliador, codigo = r["entrada"], r["plano"], r["avaliador"], r["codigo_avaliado"]
    _exigir(all(_sha(entrada.get(nome)) for nome in ("sha256_bytes_brutos", "sha256_normalizado_lf", "conjunto_sha256")), "hash do conjunto ausente ou inválido")
    _exigir(_sha(plano.get("sha256")), "hash do plano ausente ou inválido")
    _exigir(all(_sha(avaliador.get(nome)) for nome in ("sha256_bytes_brutos", "sha256_normalizado_lf")), "hash do avaliador ausente ou inválido")
    _exigir(isinstance(codigo, dict) and codigo and all(isinstance(item, dict) and _sha(item.get("sha256_bytes_brutos")) and _sha(item.get("sha256_normalizado_lf"))
                                                       for item in codigo.values()), "os hashes do código avaliado estão ausentes ou inválidos")
    _exigir(_sha(r["codigo_sha256"]) and r["codigo_sha256"] == al4.hash_do_codigo(codigo), "codigo_sha256 não corresponde aos hashes do código avaliado")
    return "hashes do conjunto, do plano, do avaliador e do código presentes e coerentes"


def _verificar_artefatos(r: Mapping[str, Any]) -> str:
    _exigir(set(r["artefatos"]) == set(al4.ESTRATEGIAS), "os artefatos não cobrem as duas estratégias")
    for item in r["artefatos"].values():
        valor = item.get("origem_declarada")
        _exigir(isinstance(valor, str) and (valor == "simulado" or al4._PADRAO_ARTEFATO.fullmatch(valor) is not None and valor.lower() != "latest"),
                "a origem declarada de um artefato é inválida")
        _exigir(item.get("verificada_pelo_avaliador") is False, "um artefato aparece como verificado pelo avaliador, que não o confere")
    return "origem do artefato declarada para cada estratégia (o avaliador não a confere com o serviço)"


def _casos(r: Mapping[str, Any], estrategia: str) -> list[dict[str, Any]]:
    casos = r["estrategias"][estrategia]["casos"]
    _exigir(isinstance(casos, list) and all(isinstance(caso, dict) for caso in casos), "a lista de casos está malformada")
    return casos


def _verificar_mesmo_conjunto_e_plano(r: Mapping[str, Any]) -> str:
    _exigir(set(r["estrategias"]) == set(al4.ESTRATEGIAS), "as estratégias não são a referência e a coordenação")
    ids = {estrategia: [caso["id"] for caso in _casos(r, estrategia)] for estrategia in al4.ESTRATEGIAS}
    total = r["entrada"]["casos"]
    _exigir(isinstance(total, int) and total >= 1, "o total de casos é inválido")
    _exigir(ids["referencia"] == ids["coordenacao"] and len(ids["referencia"]) == total and len(set(ids["referencia"])) == total,
            "as duas estratégias não têm o mesmo conjunto de casos, na mesma ordem")
    _exigir(r["plano"]["chamadas_planejadas"] == total * len(al4.ESTRATEGIAS), "as chamadas planejadas não são uma por estratégia e caso")
    posicoes = sorted(caso["posicao"] for estrategia in al4.ESTRATEGIAS for caso in _casos(r, estrategia))
    _exigir(posicoes == list(range(1, total * len(al4.ESTRATEGIAS) + 1)), "as posições do plano não são únicas e contínuas")
    _exigir(r["plano"]["congelado_antes_da_execucao"] is True and r["plano"]["estrategias"] == list(al4.ESTRATEGIAS), "o plano não está declarado como congelado")
    return "mesmo conjunto, mesma ordem e uma chamada planejada por estratégia e caso"


def _verificar_denominador(r: Mapping[str, Any]) -> str:
    for estrategia in al4.ESTRATEGIAS:
        resumo, casos = r["estrategias"][estrategia]["resumo"], _casos(r, estrategia)
        _exigir(all(caso.get("resultado") in _ESTADOS_DE_CASO for caso in casos), "um caso tem um resultado fora do vocabulário fechado")
        contagem = Counter(caso["resultado"] for caso in casos)
        total = len(casos)
        _exigir(resumo["casos_planejados"] == total, "casos_planejados não é o total de casos")
        _exigir(sum(contagem.values()) == total and all(resumo[nome] == contagem[estado] for nome, estado in (
            ("aprovados", al4.ac.APROVADO), ("divergentes", al4.ac.DIVERGENTE), ("falhas_http", al4.ac.FALHA_HTTP), ("erros", al4.ac.ERRO),
            ("nao_avaliados", al4.ac.NAO_AVALIADO))), "as contagens do resumo não batem com os casos")
        _exigir(resumo["taxa_de_aprovacao"] == round(contagem[al4.ac.APROVADO] / total, 4),
                "a taxa de aprovação não usa o total de casos planejados como denominador")
        _exigir(resumo["chamadas_http"] == total - contagem[al4.ac.NAO_AVALIADO], "chamadas_http não é o total menos os não avaliados")
    return "denominador = casos planejados: falhas, descartes e não avaliados contam como falha"


def _verificar_uso(r: Mapping[str, Any]) -> str:
    for estrategia in al4.ESTRATEGIAS:
        resumo, casos = r["estrategias"][estrategia]["resumo"], _casos(r, estrategia)
        uso = resumo["uso_de_tokens"]
        informados = [caso["tokens"] for caso in casos if caso.get("tokens") is not None]
        _exigir(all(isinstance(item, dict) and sorted(item) == list(_CAMPOS_DO_USO) and all(isinstance(v, int) and not isinstance(v, bool) and v >= 0 for v in item.values())
                    for item in informados), "um caso tem o uso de tokens malformado")
        _exigir(all(caso.get("tokens") is None for caso in casos if caso.get("http") != 200), "uma chamada sem resposta 200 informa tokens")
        _exigir(uso["respostas_com_uso_informado"] == len(informados) and uso["chamadas_sem_uso_informado"] == resumo["chamadas_http"] - len(informados),
                "as contagens de uso informado e desconhecido não batem com os casos")
        esperado = None if not informados else {nome: sum(item[nome] for item in informados) for nome in _CAMPOS_DO_USO}
        _exigir(uso["soma_do_uso_informado"] == esperado, "a soma do uso não é a dos casos (e sem uso informado ela deve ser null, nunca zero)")
    return "uso desconhecido fica null: nunca vira zero nem total completo"


def _verificar_comparacao(r: Mapping[str, Any]) -> str:
    comparacao = r["comparacao"]
    por_estrategia = {estrategia: {caso["id"]: caso["resultado"] == al4.ac.APROVADO for caso in _casos(r, estrategia)} for estrategia in al4.ESTRATEGIAS}
    ids = [caso["id"] for caso in _casos(r, al4.BASE)]
    ganhos = [i for i in ids if not por_estrategia["referencia"][i] and por_estrategia["coordenacao"][i]]
    perdas = [i for i in ids if por_estrategia["referencia"][i] and not por_estrategia["coordenacao"][i]]
    esperado = {"base": al4.BASE, "casos": len(ids), "ganhos": len(ganhos), "perdas": len(perdas), "saldo": len(ganhos) - len(perdas),
                "ids_dos_ganhos": ganhos, "ids_das_perdas": perdas,
                "ambos_aprovados": sum(1 for i in ids if por_estrategia["referencia"][i] and por_estrategia["coordenacao"][i]),
                "ambos_reprovados": sum(1 for i in ids if not por_estrategia["referencia"][i] and not por_estrategia["coordenacao"][i])}
    _exigir(all(comparacao.get(chave) == valor for chave, valor in esperado.items()), "ganhos, perdas e contagens não batem com os resultados por caso")
    return "ganhos e perdas em relação à referência recalculados e conferidos"


def _verificar_custos(r: Mapping[str, Any]) -> str:
    custos = r["custos"]
    resumos = {estrategia: r["estrategias"][estrategia]["resumo"] for estrategia in al4.ESTRATEGIAS}
    if custos["regime"] == "nao_informado":
        _exigir(custos["precos_por_1m_de_tokens"] is None and all(resumo["custo"] is None for resumo in resumos.values()), "há custo sem preço informado")
        return "nenhum preço informado: só tokens, sem custo"
    _exigir(custos["regime"] == "precos_informados_pelo_operador" and isinstance(custos["moeda"], str) and re.fullmatch(r"[A-Z]{3}", custos["moeda"]),
            "o regime ou a moeda de custos é inválido")
    precos = custos["precos_por_1m_de_tokens"]
    _exigir(isinstance(precos, dict) and set(precos) == {"entrada", "saida", "embeddings"} and all(_numero_nao_negativo(v) for v in precos.values()),
            "os preços informados não são números finitos maiores ou iguais a zero")
    for resumo in resumos.values():
        uso, custo = resumo["uso_de_tokens"], resumo["custo"]
        soma = uso["soma_do_uso_informado"]
        esperado = None if soma is None else round((soma["tokens_embeddings"] * precos["embeddings"] + soma["tokens_entrada"] * precos["entrada"]
                                                    + soma["tokens_saida"] * precos["saida"]) / 1_000_000, 6)
        _exigir(isinstance(custo, dict) and custo["estimado_com_o_uso_informado"] == esperado
                and custo["parcial"] == (soma is None or uso["chamadas_sem_uso_informado"] > 0), "o custo estimado não é o do uso informado")
    return "custo só dos preços informados e do uso informado; parcial quando há uso desconhecido"


def _verificar_interpretacao(r: Mapping[str, Any]) -> str:
    interpretacao = r["interpretacao"]
    _exigir(interpretacao == {"permite": list(al4.LEITURA_PERMITIDA), "nao_permite": list(al4.LEITURA_PROIBIDA)},
            "a leitura permitida e a proibida foram alteradas: nada induz tratar conjuntos distintos como comparação causal")
    return "a leitura permitida e a proibida são as do avaliador"


def _verificar_destinos(r: Mapping[str, Any]) -> str:
    modos = {estrategia: r["destinos"][estrategia]["modo"] for estrategia in al4.ESTRATEGIAS}
    _exigir(all(modo in _MODOS_DE_DESTINO for modo in modos.values()), "o modo de um destino está fora do vocabulário")
    _exigir(r["simulado"] is False or set(modos.values()) == {"simulado_sem_rede"}, "um relatório simulado precisa ter destinos simulados")
    _exigir(r["simulado"] is True or "simulado_sem_rede" not in modos.values(), "destino simulado em um relatório que não é simulado")
    return "modos de destino dentro do vocabulário fechado"


_VERIFICACOES: tuple[tuple[str, str, Callable[[Mapping[str, Any]], str]], ...] = (
    ("tipo_e_campos", "o relatório é uma comparação do L400 (e não uma avaliação do L200) e só tem os campos do avaliador", _verificar_tipo),
    ("hashes", "hashes do conjunto, do plano, do avaliador e do código avaliado presentes e coerentes", _verificar_hashes),
    ("artefatos", "a origem do artefato avaliado foi declarada para cada estratégia", _verificar_artefatos),
    ("mesmo_conjunto_e_plano", "as duas estratégias têm o mesmo conjunto e o mesmo plano congelado, com uma chamada por estratégia e caso",
     _verificar_mesmo_conjunto_e_plano),
    ("denominador", "falhas, descartes (429, 503), tempo esgotado, JSON inválido e não avaliados contam como falha", _verificar_denominador),
    ("uso_de_tokens", "uso desconhecido é null, nunca zero", _verificar_uso),
    ("ganho_e_perda", "ganho e perda em relação à referência conferem com os resultados por caso", _verificar_comparacao),
    ("custos", "custos só com preços informados e finitos", _verificar_custos),
    ("interpretacao", "nada induz a tratar conjuntos distintos como comparação causal", _verificar_interpretacao),
    ("destinos", "os modos de destino estão no vocabulário fechado", _verificar_destinos),
)


def validar_comparacao(dados: Any, *, conjunto_esperado: str | None = None, plano_esperado: str | None = None,
                       codigo_esperado: str | None = None) -> dict[str, Any]:
    """Valida o relatório do avaliar_l400.py. O relatório inválido nunca é aceito; o incompleto e o simulado não valem como evidência."""
    for nome, esperado in (("conjunto", conjunto_esperado), ("plano da avaliação", plano_esperado), ("código", codigo_esperado)):
        if esperado is not None and not _PADRAO_SHA256.fullmatch(esperado):
            raise ErroLab(f"O SHA-256 esperado do {nome} deve ter os 64 caracteres hexadecimais minúsculos.")
    verificacoes: list[dict[str, str]] = []
    falhou_no_tipo = False
    for identificador, descricao, funcao in _VERIFICACOES:
        if falhou_no_tipo:
            verificacoes.append({"id": identificador, "descricao": descricao, "estado": "nao_avaliado", "detalhe": "o relatório não tem a forma esperada"})
            continue
        try:
            detalhe, estado = funcao(dados), "atendido"
        except _Falha as falha:
            detalhe, estado = str(falha), "reprovado"
        except (KeyError, TypeError, ValueError, AttributeError, IndexError):
            detalhe, estado = "a estrutura do relatório não é a esperada", "reprovado"
        verificacoes.append({"id": identificador, "descricao": descricao, "estado": estado, "detalhe": detalhe})
        falhou_no_tipo = identificador == "tipo_e_campos" and estado == "reprovado"
    brutos = _varrer_conteudo_bruto(dados) if isinstance(dados, (dict, list)) else []
    verificacoes.append({"id": "sem_conteudo_bruto", "descricao": "o relatório não guarda pergunta, corpo de resposta, endereço, token nem cabeçalho",
                         "estado": "reprovado" if brutos else "atendido",
                         "detalhe": "; ".join(brutos) if brutos else "nenhum campo proibido e nenhum texto parecido com endereço ou token"})
    valido = isinstance(dados, dict) and not falhou_no_tipo
    hashes = {nome: (dados.get(bloco, {}).get(campo) if valido and isinstance(dados.get(bloco), dict) else None)
              for nome, bloco, campo in (("conjunto_sha256", "entrada", "conjunto_sha256"), ("plano_sha256", "plano", "sha256"))}
    hashes["codigo_sha256"] = dados.get("codigo_sha256") if valido else None
    conferidos = {}
    for nome, esperado, atual in (("conjunto", conjunto_esperado, hashes["conjunto_sha256"]), ("plano_da_avaliacao", plano_esperado, hashes["plano_sha256"]),
                                  ("codigo", codigo_esperado, hashes["codigo_sha256"])):
        if esperado is None:
            conferidos[nome] = "nao_informado"
        else:
            conferidos[nome] = "igual" if esperado == atual else "diferente"
            verificacoes.append({"id": f"{nome}_esperado", "descricao": f"o SHA-256 do {nome.replace('_', ' ')} é o congelado",
                                 "estado": "atendido" if esperado == atual else "reprovado",
                                 "detalhe": "igual ao informado" if esperado == atual else "diferente do informado: outro experimento, não comparável"})
    contagem = Counter(item["estado"] for item in verificacoes)
    avisos = []
    nao_informados = [nome for nome, estado in conferidos.items() if estado == "nao_informado"]
    if nao_informados and valido:
        confirmados = dados.get("plano", {}).get("hashes_esperados_conferidos", {}) if isinstance(dados.get("plano"), dict) else {}
        pendentes = [nome.replace("plano_da_avaliacao", "plano") for nome in nao_informados if not (isinstance(confirmados, dict) and confirmados.get(nome.replace("plano_da_avaliacao", "plano")) is True)]
        if pendentes:
            avisos.append("O congelamento não foi comprovado para: " + ", ".join(pendentes) + ". Informe os SHA-256 congelados antes da execução.")
    completo = valido and dados.get("status") == "concluido" and dados.get("interrupcao") is None and all(
        dados["estrategias"][e]["resumo"].get("nao_avaliados") == 0 for e in al4.ESTRATEGIAS if isinstance(dados.get("estrategias"), dict) and e in dados["estrategias"])
    hospedado = valido and isinstance(dados.get("destinos"), dict) and all(
        isinstance(dados["destinos"].get(e), dict) and dados["destinos"][e].get("modo") == "hospedado_https" for e in al4.ESTRATEGIAS)
    simulado = valido and dados.get("simulado") is True
    if contagem["reprovado"] or not valido:
        resultado = "invalido"
    elif simulado:
        resultado = "ensaio_simulado"
        avisos.append("Relatório SIMULADO (ensaio): a estrutura confere, mas ele não mede nenhuma aplicação e não vale como evidência.")
    elif not completo:
        resultado = "valido_incompleto"
        avisos.append("Execução interrompida ou com casos não avaliados: contam como falha, e a comparação não está completa.")
    elif not hospedado:
        resultado = "valido_incompleto"
        avisos.append("Pelo menos um destino é local (demonstração): o resultado não é evidência do serviço hospedado.")
    else:
        resultado = "valido_completo"
    return {
        "versao_relatorio": VERSAO_DO_RELATORIO, "tipo": "validacao-da-comparacao-l400", "resultado": resultado,
        "contagem": {estado: contagem.get(estado, 0) for estado in ("atendido", "reprovado", "nao_avaliado")},
        "verificacoes": verificacoes, "hashes": hashes, "hashes_esperados": conferidos, "evidencia_azure": False, "avisos": avisos,
        "limite": LIMITE_DA_VALIDACAO,
    }


def etapa_validar_comparacao(args: argparse.Namespace, env: Mapping[str, str]) -> int:
    if not args.comparacao:
        raise ErroLab("Informe --comparacao (o relatório JSON gerado por scripts/avaliar_l400.py).")
    relatorio = o3._exigir_relatorio_novo(Path(args.relatorio) if args.relatorio else None)
    _, dados = o3._ler_json(Path(args.comparacao))
    resultado = validar_comparacao(dados, conjunto_esperado=args.conjunto_esperado, plano_esperado=args.plano_avaliacao_esperado,
                                   codigo_esperado=args.codigo_esperado)
    print(f"Validação da comparação do L400: {resultado['resultado']}")
    for item in resultado["verificacoes"]:
        print(f"  [{item['estado']}] {item['id']}: {item['detalhe']}")
    for aviso in resultado["avisos"]:
        print(f"[AVISO] {aviso}")
    if relatorio is not None:
        o3._gravar_relatorio(relatorio, resultado)
    if resultado["resultado"] != "valido_completo":
        raise ErroLab(f"Relatório não aceito como comparação completa ({resultado['resultado']}). " + resultado["limite"], CODIGO_DIVERGENCIA)
    print("Resultado: relatório válido e completo, sem conteúdo bruto. " + resultado["limite"])
    return CODIGO_OK


# --------------------------------------------------------------------------------------
# Linha de comando
# --------------------------------------------------------------------------------------

_ETAPAS: dict[str, Callable[[argparse.Namespace, Mapping[str, str]], int]] = {
    "planejar": etapa_planejar,
    "sanitizar-whatif": etapa_sanitizar_whatif,
    "conferir-migracao": etapa_conferir_migracao,
    "resumir-logs": etapa_resumir_logs,
    "validar-comparacao": etapa_validar_comparacao,
}
ETAPAS = tuple(_ETAPAS)


def criar_parser() -> lab_comum.ParserLab:
    parser = lab_comum.ParserLab(description=__doc__)
    parser.add_argument("--etapa", required=True, choices=ETAPAS, help=", ".join(ETAPAS) + " (veja a descrição acima).")
    parser.add_argument("--passo", choices=(*PASSOS, "todos"), default="todos", help="planejar: um passo do plano ou todos (padrão).")
    parser.add_argument("--formato", choices=("texto", "json"), default="texto", help="planejar: texto (padrão) ou json.")
    parser.add_argument("--validar-bicep", action="store_true", help="planejar: compila e roda o lint de infra/l400.bicep localmente (sem Azure, "
                        "sem credenciais, sem compilar o arquivo de parâmetros). O lint precisa estar SEM avisos, como no CI.")
    parser.add_argument("--relatorio", default=None, help="Relatório JSON a criar. Precisa ser um arquivo NOVO: nunca sobrescreve.")
    parser.add_argument("--arquivo", default=None, help="sanitizar-whatif: o JSON do what-if. Nunca é copiado nem exibido.")
    parser.add_argument("--rotulo", default=None, help=f"sanitizar-whatif: rótulo curto do relatório (padrão: {VAR_FASE} ou sem-rotulo).")
    parser.add_argument("--qualificar-nao-suportado", default=None, metavar="TIPO=N,...",
                        help="sanitizar-whatif: aceita, explicitamente e pela quantidade exata, itens que o what-if não consegue prever.")
    parser.add_argument("--qualificar-propriedades-removidas", default=None, metavar="TIPO=N,...",
                        help="sanitizar-whatif: aceita, pela quantidade exata, propriedades removidas em recursos existentes.")
    parser.add_argument("--plano-esperado", default=None, metavar="SHA256",
                        help="sanitizar-whatif: exige que o conteúdo sanitizado tenha este plano_sha256 (o de uma simulação já revisada).")
    parser.add_argument("--descritor", default=None, help="conferir-migracao: o JSON de promoção ou de retorno que você preencheu.")
    parser.add_argument("--manifesto", default=str(l300.MANIFESTO_PADRAO), help="conferir-migracao: manifesto de permissões do L300 (padrão: o do repositório).")
    parser.add_argument("--logs", default=None, help="resumir-logs: arquivo de logs sanitizados do chat (texto ou JSON do Container Apps).")
    parser.add_argument("--comparacao", default=None, help="validar-comparacao: o relatório JSON do scripts/avaliar_l400.py.")
    parser.add_argument("--conjunto-esperado", default=None, metavar="SHA256", help="validar-comparacao: o conjunto_sha256 congelado.")
    parser.add_argument("--plano-avaliacao-esperado", default=None, metavar="SHA256", help="validar-comparacao: o plano_sha256 congelado do avaliador.")
    parser.add_argument("--codigo-esperado", default=None, metavar="SHA256", help="validar-comparacao: o codigo_sha256 congelado.")
    return parser


def _traduzir_erro(erro: Exception, args: argparse.Namespace) -> tuple[str, int]:
    return (f"Erro inesperado do script ({type(erro).__name__}). Nada foi alterado; o texto técnico foi omitido de propósito, porque pode conter dados "
            "do seu ambiente.", CODIGO_INESPERADO)


def principal(argv: list[str] | None = None, env: Mapping[str, str] | None = None) -> int:
    lab_comum.configurar_saida()
    if sys.version_info < (3, 12):
        print("[ERRO] Este script exige Python 3.12 ou superior.", file=sys.stderr)
        return CODIGO_USO
    import os

    ambiente = dict(os.environ if env is None else env)
    with o3._proteger_segredos(o3.segredos_para_redigir(ambiente)):
        args = criar_parser().parse_args(argv)
        return lab_comum.executar_com_tratamento(lambda a: _ETAPAS[a.etapa](a, ambiente), args, tradutor=_traduzir_erro)


if __name__ == "__main__":
    sys.exit(principal())
