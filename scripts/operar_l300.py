"""Operação protegida do L300: valida, planeja, sanitiza e confere SEM acessar a nuvem.

Este script lê só arquivos locais e variáveis de ambiente. Ele não usa rede, não chama o Azure nem o GitHub e não
executa nada na nuvem: quem executa, depois da aprovação humana de um ambiente protegido do GitHub, é o workflow manual
`l300-implantar.yml`. Não existe opção --executar nem etapa que apague recursos (o "limpar" do L300 fica fora daqui).
A única coisa que o script grava é um relatório novo e sanitizado, e nunca sobrescreve um arquivo que já existe.

Configuração privada × credenciais: coisas DIFERENTES, que o script nunca mistura:
    configuração privada   identificadores e nomes que sozinhos não dão acesso a nada, mas não devem aparecer nos registros: os IDs da
                           identidade de implantação (AZURE_CLIENT_ID, AZURE_TENANT_ID e AZURE_SUBSCRIPTION_ID), o grupo de recursos, os
                           nomes dos recursos existentes, o ID de objeto de quem carrega os documentos e os IDs do registro de login da
                           aplicação. No workflow cada um vem de um SECRET individual do ambiente protegido, que o runner mascara desde o
                           primeiro uso; nunca de vars (nem do contexto vars serializado), que o runner imprimiria em claro antes de
                           qualquer máscara. NÃO são credenciais. O que não é privado (SKUs, réplicas, partições, regiões e a ação sem
                           login) vem de vars, uma variável por vez.
    implantação (OIDC)     a identidade de quem executa o Azure: a identidade federada do GitHub Actions. Não existe segredo: o GitHub
                           emite um token de vida curta. AZURE_CLIENT_SECRET e as demais credenciais do Azure são recusados.
    login da aplicação     quem usa o chat: o registro de aplicativo do Microsoft Entra ID do chat, outro objeto. Só na fase aplicacao
                           há credencial: o segredo de cliente em secrets.VARELEIRA_SEGREDO_LOGIN do ambiente protegido, o ÚNICO segredo
                           aceito. Ele é uma variável efêmera dos passos que validam, simulam e aplicam (vira o parâmetro @secure do
                           Bicep e o secret do Azure Container Apps) e nunca vai para vars, GITHUB_ENV, argumentos, console nem relatórios.

Etapas (--etapa):
    validar             confere a fase, os portões da aplicação (confirmação, tag da imagem, conectividade privada), o
                        contexto do GitHub Actions e as variáveis, sem rede; --exigir-azure confere TODOS os destinos do Bicep e os
                        parâmetros da fase; --exportar-github-env repassa só valores validados (nunca o segredo do login)
    plano               mostra o plano declarativo da fase (o que cria, reutiliza e altera, e o efeito na migração);
                        --validar-bicep compila infra/l300.bicep no seu computador (sem Azure) e exige lint SEM avisos, como o CI
    sanitizar-whatif    reduz o JSON do what-if do ARM a contagens, tipos de recurso e caminhos de propriedades; descarta
                        valores, identificadores, endereços e principais; código 3 se houver exclusão, item não suportado
                        sem qualificação explícita, mudança potencial não resolvida ou plano diferente do revisado
    verificar-ambiente  avalia, offline, as evidências que o workflow baixou do GitHub sobre a proteção do ambiente: o login só é
                        liberado com revisores obrigatórios, restrição de branches E aprovação registrada desta execução, todos lidos
                        da API; qualquer lacuna (ausente, 403, JSON ilegível ou incompleto) bloqueia com código 3 e nenhuma atestação
                        substitui a prova
    conferir            confere um descritor de evidências que VOCÊ preencheu (DNS, SPL, aplicação, ingestão e provas
                        positiva e negativa); não prova segurança: só confere se os campos estão completos e coerentes
    resumir-logs        conta status HTTP, rotas, latência e causas em logs sanitizados do chat (somente leitura)

Códigos de saída: 0 concluído; 1 uso ou entrada inválida (inclui portão bloqueado); 3 a conferência não aceitou o que leu
(divergência); 4 defeito do script. Mensagens e relatórios nunca trazem valores antes/depois, identificadores, endereços,
tokens, perguntas ou respostas.

Exemplos (todos locais, sem rede):
    python scripts\\operar_l300.py --etapa plano --fase todas
    python scripts\\operar_l300.py --etapa plano --fase rede --validar-bicep
    python scripts\\operar_l300.py --etapa validar --fase aplicacao --aplicar --tag-imagem <tag> --confirmacao APLICAR-L300-APLICACAO
    python scripts\\operar_l300.py --etapa validar --fase isolar --conectividade-privada-validada --aplicar --confirmacao APLICAR-L300-ISOLAR
    python scripts\\operar_l300.py --etapa sanitizar-whatif --arquivo <whatif.json> --relatorio <novo-relatorio.json> --rotulo rede
    python scripts\\operar_l300.py --etapa sanitizar-whatif --arquivo <whatif.json> --relatorio <novo.json> --qualificar-nao-suportado Microsoft.Authorization/roleAssignments=3
    python scripts\\operar_l300.py --etapa verificar-ambiente --aprovacoes <aprovacoes.json> --ambiente <ambiente.json>
    python scripts\\operar_l300.py --etapa conferir --descritor <evidencias.json> --momento antes-de-isolar
    python scripts\\operar_l300.py --etapa resumir-logs --logs <logs-sanitizados.txt> --relatorio <novo-resumo.json>
"""

from __future__ import annotations

import argparse
import contextlib
import copy
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Mapping, Sequence

import lab_comum
from lab_comum import CODIGO_DIVERGENCIA, CODIGO_INESPERADO, CODIGO_OK, CODIGO_USO, ErroLab

# --------------------------------------------------------------------------------------
# Contrato com os workflows e com o Bicep do L300
# --------------------------------------------------------------------------------------

FASES = ("rede", "aplicacao", "isolar")
FASE_PADRAO = "rede"
AMBIENTE_GITHUB = "vareleira-l300"
RUNNER_ROTULOS = ("self-hosted", "linux", "vareleira-l300")
ARQUIVO_DO_WORKFLOW = "l300-implantar.yml"
REF_PERMITIDA = "refs/heads/main"
INDICE_L300 = "vareleira-lar-l300"
PREFIXO_DA_CONFIRMACAO = "APLICAR-L300-"
BICEP_L300 = lab_comum.RAIZ / "infra" / "l300.bicep"
DEPENDENCIAS_DE_DADOS = ("armazenamento", "busca", "modelos")

VAR_FASE = "VARELEIRA_L300_FASE"  # o bicepparam do L300 lê esta variável
VAR_APLICAR = "VARELEIRA_APLICAR"
VAR_CONECTIVIDADE = "VARELEIRA_L300_CONECTIVIDADE_PRIVADA_VALIDADA"  # portão do Bicep: autoriza a fase isolar
VAR_INGRESSO_EXTERNO = "VARELEIRA_L300_INGRESSO_EXTERNO"  # portão do Bicep: abre o endereço público da aplicação
VAR_TAG = "VARELEIRA_TAG_IMAGEM"
VAR_CONFIRMACAO = "VARELEIRA_CONFIRMACAO"
VAR_QUALIFICAR_NAO_SUPORTADO = "VARELEIRA_QUALIFICAR_NAO_SUPORTADO"
VAR_QUALIFICAR_REMOVIDAS = "VARELEIRA_QUALIFICAR_PROPRIEDADES_REMOVIDAS"
VAR_PLANO_SHA256 = "VARELEIRA_PLANO_SHA256"
VAR_VARIAVEIS_JSON = "VARELEIRA_VARS_JSON"  # só para testes e uso locais: o workflow NÃO a usa (vars serializado seria impresso em claro)
VAR_GRUPO = "VARELEIRA_GRUPO_RECURSOS"
VAR_ACESSO_DOCUMENTAL = "VARELEIRA_EXIGIR_ACESSO_DOCUMENTAL"
# Login DA APLICAÇÃO (registro de aplicativo do Microsoft Entra ID do chat): outro objeto, que não é a identidade de implantação.
VAR_ID_APLICACAO_LOGIN = "VARELEIRA_ID_APLICACAO_LOGIN"
VAR_ID_TENANT_LOGIN = "VARELEIRA_ID_TENANT_LOGIN"
VAR_ACAO_SEM_LOGIN = "VARELEIRA_ACAO_SEM_LOGIN"
VAR_SEGREDO_LOGIN = "VARELEIRA_SEGREDO_LOGIN"  # o ÚNICO segredo aceito: variável efêmera da fase aplicacao, só de secrets do GitHub
VAR_ID_OBJETO_CARGA = "VARELEIRA_ID_OBJETO_CARGA"
VAR_SKU_ARMAZENAMENTO = "VARELEIRA_SKU_ARMAZENAMENTO"
VAR_SKU_BUSCA = "VARELEIRA_SKU_BUSCA"
VAR_REPLICAS_BUSCA = "VARELEIRA_REPLICAS_BUSCA"
VAR_PARTICOES_BUSCA = "VARELEIRA_PARTICOES_BUSCA"
VARS_DE_REGIAO = ("VARELEIRA_LOCALIZACAO_ARMAZENAMENTO", "VARELEIRA_LOCALIZACAO_BUSCA", "VARELEIRA_LOCALIZACAO_MODELOS")
# Identidade de IMPLANTAÇÃO (OIDC): sem segredo de cliente. Os IDs são configuração privada (não credenciais) e a identidade não é
# o registro de login da aplicação.
VARS_DE_IDENTIDADE = ("AZURE_CLIENT_ID", "AZURE_TENANT_ID", "AZURE_SUBSCRIPTION_ID")
# Destinos que o infra/levels/l300.bicepparam exige em TODAS as fases (o Bicep recusa nomes vazios), sem valores padrão.
VARS_DE_DESTINO = ("VARELEIRA_NOME_CONTA", "VARELEIRA_NOME_BUSCA", "VARELEIRA_NOME_MODELOS", "VARELEIRA_NOME_REGISTRO",
                   "VARELEIRA_NOME_IDENTIDADE_APLICACAO", "VARELEIRA_NOME_WORKSPACE_LOGS", VAR_ID_OBJETO_CARGA)
VARS_DE_RECURSOS = (VAR_GRUPO, *VARS_DE_DESTINO)  # o grupo vai para o az; o resto, para o bicepparam
# Parâmetros obrigatórios só na fase (a tag da imagem, em aplicacao, vem do campo tag_imagem e é conferida à parte).
VARS_POR_FASE = {
    "rede": (),
    "aplicacao": (VAR_ID_APLICACAO_LOGIN, VAR_ID_TENANT_LOGIN),
    "isolar": (VAR_SKU_ARMAZENAMENTO, VAR_SKU_BUSCA, VAR_REPLICAS_BUSCA, VAR_PARTICOES_BUSCA),
}
VARS_OPCIONAIS_DO_BICEP = (VAR_ACAO_SEM_LOGIN, *VARS_DE_REGIAO)
# Configuração PRIVADA: identificadores e nomes que sozinhos não dão acesso a nada, mas não devem aparecer nos registros. No
# workflow cada uma vem de um SECRET individual do ambiente protegido (o runner o mascara desde o primeiro uso) e nunca de vars,
# que ele imprimiria em claro antes de qualquer máscara. Não são credenciais.
VARS_PRIVADAS = (*VARS_DE_IDENTIDADE, *VARS_DE_RECURSOS, *VARS_POR_FASE["aplicacao"])
# Configuração NÃO privada: vem de vars do ambiente, mapeadas uma a uma no workflow (nunca o contexto vars inteiro).
VARS_NAO_PRIVADAS = (*VARS_POR_FASE["isolar"], *VARS_DE_REGIAO, VAR_ACAO_SEM_LOGIN)
# Toda variável que o bicepparam lê precisa estar aqui: o teste de contrato falha se o Bicep ganhar uma que o script desconhece.
VARIAVEIS_DO_BICEPPARAM = frozenset({VAR_FASE, VAR_INGRESSO_EXTERNO, VAR_CONECTIVIDADE, VAR_TAG, VAR_SEGREDO_LOGIN, *VARS_DE_DESTINO,
                                     *(nome for nomes in VARS_POR_FASE.values() for nome in nomes), *VARS_OPCIONAIS_DO_BICEP})
# Credenciais do SDK do Azure que a implantação por OIDC nunca usa: se aparecerem no ambiente, a validação recusa.
CREDENCIAIS_DO_AZURE_RECUSADAS = frozenset({"AZURE_CLIENT_SECRET", "AZURE_CLIENT_CERTIFICATE_PATH", "AZURE_CLIENT_CERTIFICATE_PASSWORD",
                                            "AZURE_USERNAME", "AZURE_PASSWORD"})
NAO_EXPORTAR = frozenset({VAR_VARIAVEIS_JSON})

LIMITE_ARQUIVO_BYTES = 16 * 1024 * 1024
LIMITE_LOGS_BYTES = 64 * 1024 * 1024
LIMITE_LINHA_DE_LOG = 8192
LIMITE_DE_NOS_DO_DELTA = 20_000
LIMITE_DE_NIVEIS_DO_DELTA = 24
LIMITE_DE_CAMINHOS_POR_TIPO = 100
LIMITE_DE_CARACTERES_DO_TIPO = 160

_GUID = re.compile(r"[0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}")
_GRUPO = re.compile(r"(?=.{1,90}\Z)[A-Za-z0-9_().-]*[A-Za-z0-9_()-]")
_CONTA = re.compile(r"[a-z0-9]{3,24}")
_BUSCA = re.compile(r"(?!.*--)[a-z0-9][a-z0-9-]{0,58}[a-z0-9]")
_MODELOS = re.compile(r"[a-z0-9][a-z0-9-]{0,62}[a-z0-9]")
_REGIAO = re.compile(r"[a-z0-9]{3,32}")
_REGISTRO = re.compile(r"[A-Za-z0-9]{5,50}")
_IDENTIDADE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{2,127}")
_WORKSPACE = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{2,61}[A-Za-z0-9]")
_ACAO_SEM_LOGIN = re.compile(r"Return401|RedirectToLoginPage")
_NUMERO = re.compile(r"[0-9]{1,3}")
_TEXTO_CURTO = re.compile(r"[A-Za-z_]{1,32}")
_SKU_ARMAZENAMENTO = re.compile(r"Standard_(?:LRS|ZRS|GRS)")
_SKU_BUSCA = re.compile(r"basic|standard")
_REPLICAS = re.compile(r"[1-9]|1[0-2]")
_PARTICOES = re.compile(r"[1-4]|6|12")
# Segredo do login da aplicação: ASCII imprimível sem espaço nem quebra de linha (o que o Entra ID gera, com margem).
_SEGREDO_DO_LOGIN = re.compile(r"[\x21-\x7e]{16,256}")
_NOME_DE_CREDENCIAL = re.compile(r"(?:AZURE|VARELEIRA)_[A-Z0-9_]{1,64}")
_TAG = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}")
_NOME_DE_VARIAVEL = re.compile(r"VARELEIRA_[A-Z0-9_]{1,64}")
_VALOR_DE_VARIAVEL = re.compile(r"[A-Za-z0-9._:/=,@-]{1,512}")
_WORKFLOW_REF = re.compile(
    r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/\.github/workflows/" + re.escape(ARQUIVO_DO_WORKFLOW) + "@" + re.escape(REF_PERMITIDA))
_SHA256 = re.compile(r"[0-9a-f]{64}")
_ROTULO = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
_NOME_DE_RELATORIO = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,95}\.json")
_NOME_DE_AMBIENTE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
_TIPO_DE_RECURSO = re.compile(r"[A-Za-z][A-Za-z0-9]*(?:\.[A-Za-z0-9]+)+(?:/[A-Za-z][A-Za-z0-9]*)+")
_QUALIFICACAO = re.compile("(" + _TIPO_DE_RECURSO.pattern + r")=(\d{1,4})")
_SEGMENTO = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}")
_PARECE_HEX = re.compile(r"[0-9A-Fa-f]{16,}")
_CODIGO_CURTO = re.compile(r"[A-Za-z0-9_.-]{1,64}")
_PALAVRA = re.compile(r"[A-Za-z]{1,32}")
# Nomes que indicam segredo. O único aceito é VARELEIRA_SEGREDO_LOGIN, e só como variável efêmera da fase aplicacao.
_NOME_SENSIVEL = re.compile(r"(?:^|_)(?:SEGREDO|SECRET|SENHA|PASSWORD|TOKEN|CHAVE|KEY|CREDENCIAL|CREDENTIAL)(?:_|$)")


class ErroFormato(Exception):
    """O JSON existe, mas não tem a forma esperada. A mensagem descreve o campo, nunca o conteúdo."""


# --------------------------------------------------------------------------------------
# Segredos: o único é o do login da aplicação, e o valor nunca chega ao console, a relatórios, a vars nem ao GITHUB_ENV
# --------------------------------------------------------------------------------------

MENOR_SEGREDO_REDIGIDO = 6
_SEGREDOS_ATIVOS: tuple[str, ...] = ()  # preenchido por principal() enquanto a linha de comando roda


def nome_de_segredo(nome: str) -> bool:
    """Credencial do Azure ou do próprio L300 (sem distinguir maiúsculas): nunca vai para vars nem para o GITHUB_ENV."""
    maiusculo = nome.upper()
    return maiusculo in CREDENCIAIS_DO_AZURE_RECUSADAS or (
        maiusculo.startswith(("AZURE_", "VARELEIRA_")) and _NOME_SENSIVEL.search(maiusculo) is not None)


def segredos_para_redigir(env: Mapping[str, str]) -> tuple[str, ...]:
    """O segredo do login da aplicação, se estiver no ambiente, em todas as formas em que poderia aparecer em um texto."""
    bruto = env.get(VAR_SEGREDO_LOGIN, "")
    formas = {forma for valor in (bruto, bruto.strip()) if len(valor) >= MENOR_SEGREDO_REDIGIDO
              for forma in (valor, json.dumps(valor)[1:-1])}
    return tuple(sorted(formas, key=len, reverse=True))


def redigir(texto: str, segredos: Sequence[str]) -> str:
    for segredo in segredos:
        texto = "***".join(texto.split(segredo))
    return texto


class _SaidaRedigida:
    """Envolve stdout/stderr e troca qualquer segredo conhecido por '***' na hora de escrever (defesa em profundidade)."""

    def __init__(self, destino: Any, segredos: Sequence[str]) -> None:
        self._destino, self._segredos = destino, tuple(segredos)

    def write(self, texto: str) -> int:
        return self._destino.write(redigir(texto, self._segredos))

    def __getattr__(self, nome: str) -> Any:
        return getattr(self._destino, nome)


@contextlib.contextmanager
def _proteger_segredos(segredos: Sequence[str]) -> Iterator[None]:
    """Enquanto a etapa roda: redige o console e deixa o segredo à disposição da conferência dos relatórios."""
    global _SEGREDOS_ATIVOS
    if not segredos:
        yield
        return
    anterior, saida, erro = _SEGREDOS_ATIVOS, sys.stdout, sys.stderr
    _SEGREDOS_ATIVOS = tuple(segredos)
    sys.stdout, sys.stderr = _SaidaRedigida(saida, segredos), _SaidaRedigida(erro, segredos)
    try:
        yield
    finally:
        sys.stdout, sys.stderr = saida, erro
        _SEGREDOS_ATIVOS = anterior


def contem_segredo(texto: str) -> bool:
    return any(segredo in texto for segredo in _SEGREDOS_ATIVOS)


def ambiente_sem_credenciais() -> dict[str, str]:
    """Cópia do ambiente SEM credenciais, para os programas que o script executa (o Bicep só compila o template)."""
    return {nome: valor for nome, valor in os.environ.items()
            if _NOME_SENSIVEL.search(nome.upper()) is None and nome.upper() not in CREDENCIAIS_DO_AZURE_RECUSADAS}


# --------------------------------------------------------------------------------------
# Entradas: variáveis de ambiente, flags e arquivos
# --------------------------------------------------------------------------------------

@dataclass
class Validacao:
    problemas: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    portoes: list[str] = field(default_factory=list)
    fase: str = ""
    aplicar: bool = False
    exportar: dict[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.problemas


def _booleano(env: Mapping[str, str], nome: str, validacao: Validacao) -> bool:
    bruto = env.get(nome, "")
    if bruto in ("", "false"):
        return False
    if bruto == "true":
        return True
    validacao.problemas.append(f"{nome}: use exatamente 'true' ou 'false'.")
    return False


def interpretar_qualificacoes(texto: str) -> dict[str, int]:
    """Lê `Tipo=N,Tipo=N`. Cada par diz exatamente quantos itens daquele tipo de recurso você revisou e aceita."""
    if not texto:
        return {}
    qualificacoes: dict[str, int] = {}
    partes = texto.split(",")
    if len(partes) > 20:
        raise ErroLab("Informe no máximo 20 qualificações.")
    for parte in partes:
        achado = _QUALIFICACAO.fullmatch(parte)
        if not achado:
            raise ErroLab("formato inválido: use TIPO=N separados por vírgula, por exemplo "
                          "Microsoft.Authorization/roleAssignments=3 (o tipo de recurso, '=' e a quantidade revisada).")
        tipo, quantidade = achado.group(1), int(achado.group(2))
        if tipo in qualificacoes:
            raise ErroLab("o mesmo tipo de recurso aparece duas vezes.")
        qualificacoes[tipo] = quantidade
    return qualificacoes


def _variaveis_aceitas(env: Mapping[str, str], validacao: Validacao) -> dict[str, str]:
    """Variáveis que o script lê: identidade de implantação do Azure e VARELEIRA_*. Valores do ambiente vencem os de `vars`.

    O JSON de `vars` (VARELEIRA_VARS_JSON) serve só para testes e uso locais: o workflow entrega cada campo, enumerado, no
    ambiente do passo (privados vindos de secrets, não privados de vars), porque o runner imprime o `vars` serializado em claro.
    Nomes de segredo nunca entram aqui: em `vars` do GitHub são um erro (o valor nem é lido) e, no ambiente do passo, o do
    login da aplicação é tratado à parte, em _validar_segredos. Assim nenhum segredo chega a GITHUB_ENV ou a um relatório.
    """
    aceitas: dict[str, str] = {}
    bruto = env.get(VAR_VARIAVEIS_JSON, "")
    if bruto:
        try:
            dados = json.loads(bruto)
        except ValueError:
            dados = None
        if not isinstance(dados, dict):
            validacao.problemas.append(f"{VAR_VARIAVEIS_JSON}: não é um objeto JSON com as variáveis do GitHub (vars).")
            dados = {}
        for nome, valor in dados.items():
            maiusculo = nome.upper() if isinstance(nome, str) else ""
            if _NOME_DE_CREDENCIAL.fullmatch(maiusculo) and nome_de_segredo(maiusculo):
                if maiusculo == VAR_SEGREDO_LOGIN:
                    validacao.problemas.append(
                        f"{maiusculo}: o segredo do login da aplicação não pode ficar em vars: segredos nunca ficam em variáveis do "
                        "GitHub, que qualquer pessoa com acesso ao repositório lê. Remova a variável, gere um segredo novo no "
                        "registro do Microsoft Entra ID do chat (este foi exposto) e guarde-o só em secrets do ambiente "
                        "protegido. O valor não foi lido.")
                else:
                    validacao.problemas.append(f"{maiusculo}: o nome indica um segredo, e segredos nunca ficam em variáveis do GitHub "
                                               "(vars). Remova a variável; o valor não foi lido.")
                continue
            if not (maiusculo in VARS_DE_IDENTIDADE or _NOME_DE_VARIAVEL.fullmatch(maiusculo)) or not isinstance(valor, str):
                continue
            aceitas[maiusculo] = valor
    for nome, valor in env.items():
        if nome == VAR_VARIAVEIS_JSON or _NOME_SENSIVEL.search(nome):
            continue
        if nome in VARS_DE_IDENTIDADE or _NOME_DE_VARIAVEL.fullmatch(nome):
            aceitas[nome] = valor
    return aceitas


_VALIDADORES_POR_NOME: dict[str, tuple[re.Pattern[str], str]] = {
    VAR_GRUPO: (_GRUPO, "grupo de recursos: até 90 caracteres (letras, números, '_', '(', ')', '-' e '.', sem terminar em '.')"),
    "VARELEIRA_NOME_CONTA": (_CONTA, "conta de armazenamento: de 3 a 24 letras minúsculas e números"),
    "VARELEIRA_NOME_BUSCA": (_BUSCA, "serviço de busca: de 2 a 60 letras minúsculas, números e hífens, sem hífens seguidos"),
    "VARELEIRA_NOME_MODELOS": (_MODELOS, "recurso de modelos: de 2 a 64 letras minúsculas, números e hífens"),
    "VARELEIRA_NOME_REGISTRO": (_REGISTRO, "registro de imagens: de 5 a 50 letras e números"),
    "VARELEIRA_NOME_IDENTIDADE_APLICACAO": (_IDENTIDADE, "identidade gerenciada da aplicação: de 3 a 128 letras, números, '_' e '-', "
                                            "começando por letra ou número"),
    "VARELEIRA_NOME_WORKSPACE_LOGS": (_WORKSPACE, "workspace do Log Analytics: de 4 a 63 letras, números e hífens, sem hífen no "
                                      "início nem no fim"),
    VAR_ID_OBJETO_CARGA: (_GUID, "ID de objeto de quem carrega os documentos: um GUID de 36 caracteres"),
    VAR_ID_APLICACAO_LOGIN: (_GUID, "ID do aplicativo (cliente) do registro de login da aplicação: um GUID de 36 caracteres"),
    VAR_ID_TENANT_LOGIN: (_GUID, "ID do tenant do registro de login da aplicação: um GUID de 36 caracteres"),
    VAR_ACAO_SEM_LOGIN: (_ACAO_SEM_LOGIN, "ação para quem chega sem login: Return401 ou RedirectToLoginPage"),
    VAR_SKU_ARMAZENAMENTO: (_TEXTO_CURTO, "redundância atual da conta de armazenamento: um texto curto, como Standard_LRS"),
    VAR_SKU_BUSCA: (_TEXTO_CURTO, "camada atual do serviço de busca: um texto curto, como basic"),
    VAR_REPLICAS_BUSCA: (_NUMERO, "réplicas atuais da busca: um número inteiro (o bicepparam o converte com int())"),
    VAR_PARTICOES_BUSCA: (_NUMERO, "partições atuais da busca: um número inteiro (o bicepparam o converte com int())"),
    **{nome: (_REGIAO, "região: de 3 a 32 letras minúsculas e números") for nome in VARS_DE_REGIAO},
}
# Na fase isolar o módulo de isolamento recusa o que não for exatamente a configuração atual: aqui só confere a forma.
_VALIDADORES_DA_FASE_ISOLAR: dict[str, tuple[re.Pattern[str], str]] = {
    VAR_SKU_ARMAZENAMENTO: (_SKU_ARMAZENAMENTO, "redundância atual da conta de armazenamento: Standard_LRS, Standard_ZRS ou Standard_GRS"),
    VAR_SKU_BUSCA: (_SKU_BUSCA, "camada atual do serviço de busca: basic ou standard"),
    VAR_REPLICAS_BUSCA: (_REPLICAS, "réplicas atuais da busca: de 1 a 12"),
    VAR_PARTICOES_BUSCA: (_PARTICOES, "partições atuais da busca: 1, 2, 3, 4, 6 ou 12"),
}
_TITULO_DAS_VARIAVEIS_DA_FASE = {
    "aplicacao": "login da aplicação, o registro do Microsoft Entra ID do chat, que NÃO é a identidade de implantação (OIDC); "
                 "configuração privada: secrets individuais do ambiente protegido",
    "isolar": "configuração ATUAL dos serviços de dados, que o ARM reaplica inteiros; não é privada: variáveis (vars) do "
              "ambiente protegido, uma a uma",
}


def _validar_contexto_do_github(env: Mapping[str, str], v: Validacao) -> None:
    if env.get("GITHUB_ACTIONS") != "true":
        v.problemas.append("Contexto: esta conferência só vale dentro do GitHub Actions (GITHUB_ACTIONS=true). Fora dele, use "
                           "as etapas plano, sanitizar-whatif, conferir e resumir-logs.")
        return
    if env.get("GITHUB_EVENT_NAME") != "workflow_dispatch":
        v.problemas.append("Contexto: a operação só roda por disparo manual (workflow_dispatch).")
    elif env.get("GITHUB_REF") != REF_PERMITIDA:
        v.problemas.append(f"Contexto: a operação só roda na branch principal ({REF_PERMITIDA}); outras referências são recusadas.")
    elif not _WORKFLOW_REF.fullmatch(env.get("GITHUB_WORKFLOW_REF", "")):
        v.problemas.append(f"Contexto: o workflow em execução não é .github/workflows/{ARQUIVO_DO_WORKFLOW} na branch principal.")
    else:
        v.portoes.append(f"contexto do GitHub: workflow_dispatch de {ARQUIVO_DO_WORKFLOW} na branch principal")


def _validar_variaveis_do_azure(aceitas: Mapping[str, str], v: Validacao, fase: str) -> None:
    """Todos os destinos que o bicepparam exige, mais os parâmetros da fase, antes de qualquer chamada ao Azure."""
    exigidas = [("identidade de implantação (OIDC, sem segredo de cliente); configuração privada: secrets individuais do ambiente "
                 "protegido", VARS_DE_IDENTIDADE),
                ("destinos do Bicep, exigidos em todas as fases; configuração privada: secrets individuais do ambiente protegido",
                 VARS_DE_RECURSOS)]
    if VARS_POR_FASE.get(fase):
        exigidas.append((f"fase {fase}: {_TITULO_DAS_VARIAVEIS_DA_FASE[fase]}", VARS_POR_FASE[fase]))
    problemas_antes = len(v.problemas)
    for titulo, nomes in exigidas:
        ausentes = [nome for nome in nomes if not aceitas.get(nome)]
        if ausentes:
            v.problemas.append(f"Variáveis ausentes ({titulo}); sem valores padrão: " + ", ".join(ausentes) + ".")
    for nome in VARS_DE_IDENTIDADE:
        if aceitas.get(nome) and not _GUID.fullmatch(aceitas[nome]):
            v.problemas.append(f"{nome}: o valor não tem o formato de um GUID (o valor não é exibido).")
    for nome, valor in sorted(aceitas.items()):
        if not valor or not nome.startswith("VARELEIRA_") or nome in NAO_EXPORTAR or nome == VAR_CONFIRMACAO:
            continue
        padrao, descricao = _VALIDADORES_POR_NOME.get(nome, (None, ""))
        if fase == "isolar" and nome in _VALIDADORES_DA_FASE_ISOLAR:
            padrao, descricao = _VALIDADORES_DA_FASE_ISOLAR[nome]
        if padrao is not None:
            if not padrao.fullmatch(valor):
                v.problemas.append(f"{nome}: formato inválido ({descricao}). O valor não é exibido.")
        elif nome in (VAR_FASE, VAR_APLICAR, VAR_CONECTIVIDADE, VAR_INGRESSO_EXTERNO, VAR_TAG, VAR_QUALIFICAR_NAO_SUPORTADO,
                      VAR_QUALIFICAR_REMOVIDAS, VAR_PLANO_SHA256):
            continue  # validadas uma a uma em validar_operacao
        elif not _VALOR_DE_VARIAVEL.fullmatch(valor):
            v.problemas.append(f"{nome}: o valor usa caracteres não permitidos (aceitos: letras, números e . _ : / = , @ -).")
    if fase == "isolar" and not any(aceitas.get(nome) for nome in VARS_DE_REGIAO):
        v.avisos.append("Regiões dos serviços de dados não informadas: assume-se a região do grupo de recursos. Se algum deles estiver "
                        "em outra região, informe " + ", ".join(VARS_DE_REGIAO) + ": o ARM não move recursos.")
    if len(v.problemas) == problemas_antes:
        v.portoes.append("identidade de implantação (OIDC): AZURE_CLIENT_ID, AZURE_TENANT_ID e AZURE_SUBSCRIPTION_ID presentes, "
                         "com formato de GUID e sem segredo (valores não exibidos)")
        v.portoes.append("destinos do Bicep presentes, sem valores padrão e com formato válido (valores não exibidos)")
        if fase == "aplicacao":
            v.portoes.append("login da aplicação (registro do Entra ID do chat, distinto da identidade de implantação): ID do "
                             "aplicativo e do tenant presentes e válidos (valores não exibidos)")
        if fase == "isolar":
            v.portoes.append("configuração atual dos serviços de dados presente e com formato válido (valores não exibidos)")


def _validar_segredos(env: Mapping[str, str], v: Validacao, fase: str, exigir_login: bool) -> None:
    """O único segredo é o do login da aplicação, e só na fase aplicacao. Qualquer outra credencial é recusada.

    O valor nunca é repetido: as mensagens trazem só nomes de variáveis e regras de formato.
    """
    outros = sorted({nome.upper() for nome, valor in env.items()
                     if valor and nome != VAR_VARIAVEIS_JSON and nome != VAR_SEGREDO_LOGIN
                     and _NOME_DE_CREDENCIAL.fullmatch(nome.upper()) and nome_de_segredo(nome)})
    if outros:
        v.problemas.append("Credenciais não permitidas no ambiente deste passo: " + ", ".join(outros) + ". A implantação usa OIDC, "
                           "sem segredo (não use AZURE_CLIENT_SECRET nem outra credencial do Azure), e o único segredo aceito é "
                           f"{VAR_SEGREDO_LOGIN}, o do login da aplicação, só na fase aplicacao. Remova as variáveis do ambiente do "
                           "runner. Os valores não são exibidos.")
    segredo = env.get(VAR_SEGREDO_LOGIN, "")
    if fase == "aplicacao":
        if not segredo:
            if exigir_login:
                v.problemas.append(f"Login da aplicação: a fase aplicacao exige {VAR_SEGREDO_LOGIN}, o segredo de cliente do "
                                   "registro do Microsoft Entra ID do chat (não é a identidade de implantação por OIDC, que não tem "
                                   "segredo). Ele vem só de secrets do ambiente protegido, mapeado apenas nos passos desta fase: "
                                   "nunca de vars, argumentos nem arquivos. Peça a quem administra o repositório para criá-lo e repita.")
        elif not _SEGREDO_DO_LOGIN.fullmatch(segredo):
            v.problemas.append(f"{VAR_SEGREDO_LOGIN}: formato inválido (de 16 a 256 caracteres ASCII imprimíveis, sem espaços nem "
                               "quebras de linha, como o segredo de cliente do Entra ID). O valor não é exibido.")
        else:
            v.portoes.append("login da aplicação: segredo do registro do Entra ID presente e com formato válido (valor não exibido; "
                             "é outra credencial, distinta da identidade de implantação por OIDC)")
    elif segredo and fase:
        v.problemas.append(f"{VAR_SEGREDO_LOGIN}: o segredo do login da aplicação só existe na fase aplicacao; nas fases rede e "
                           "isolar ele não pode estar definido, para nunca chegar ao Azure sem necessidade. Remova-o do ambiente "
                           "do passo. O valor não é exibido.")


def validar_operacao(env: Mapping[str, str], *, exigir_github: bool = False, exigir_oidc: bool = False,
                     exigir_azure: bool = False, exigir_segredo_login: bool = False) -> Validacao:
    """Confere os portões de uma operação L300 sem rede. Nada é lido além de `env`, e nenhum valor é repetido na saída."""
    v = Validacao()
    fase = env.get(VAR_FASE, "")
    if not fase:
        if exigir_github or exigir_azure:
            v.problemas.append(f"Fase ausente: informe {VAR_FASE} com uma destas: {', '.join(FASES)}.")
        else:
            fase = FASE_PADRAO
            v.avisos.append(f"Fase não informada: usando o padrão '{FASE_PADRAO}'.")
    elif fase not in FASES:
        v.problemas.append(f"Fase inválida: use exatamente uma destas: {', '.join(FASES)}.")
        fase = ""
    v.fase = fase
    v.aplicar = _booleano(env, VAR_APLICAR, v)
    conectividade = _booleano(env, VAR_CONECTIVIDADE, v)
    ingresso_externo = _booleano(env, VAR_INGRESSO_EXTERNO, v)

    if fase:
        v.portoes.append(f"fase conhecida: {fase}")
        if v.aplicar:
            esperada = PREFIXO_DA_CONFIRMACAO + fase.upper()
            if env.get(VAR_CONFIRMACAO, "") != esperada:
                v.problemas.append(f"Confirmação: para aplicar, digite exatamente {esperada} (campo 'confirmacao'). "
                                   "O texto nomeia a fase, não um recurso.")
            else:
                v.portoes.append("confirmação digitada confere com a fase")
        if fase == "isolar":
            if not conectividade:
                v.problemas.append("Fase isolar: exige conectividade_privada_validada=true, isto é, a SUA atestação de que a "
                                   "conectividade privada foi validada com evidências (use --etapa conferir). O Bicep recusa "
                                   "a fase isolar sem ela e o workflow não consegue provar isso por você.")
            else:
                v.portoes.append("conectividade privada atestada por quem dispara (não verificada pelo workflow)")
        if ingresso_externo:
            if fase != "aplicacao":
                v.problemas.append("Ingresso externo: só existe na fase aplicacao.")
            else:
                v.avisos.append("Ingresso externo LIGADO: abre o endereço público da aplicação (com login). Faça isso só depois de "
                                "conferir o login e a autorização documental com o ingresso fechado.")
        tag = env.get(VAR_TAG, "")
        if tag:
            if not _TAG.fullmatch(tag) or tag.lower() == "latest":
                v.problemas.append("Tag da imagem inválida: use uma tag imutável (letras, números, '_', '.', '-', até 128 "
                                   "caracteres), nunca 'latest'.")
            elif fase == "aplicacao":
                v.portoes.append("tag da imagem imutável informada")
        elif fase == "aplicacao":
            v.problemas.append(f"Tag da imagem ausente: a fase aplicacao exige {VAR_TAG} (campo 'tag_imagem'), uma tag imutável "
                               "já publicada no registro.")

    for nome in (VAR_QUALIFICAR_NAO_SUPORTADO, VAR_QUALIFICAR_REMOVIDAS):
        try:
            interpretar_qualificacoes(env.get(nome, ""))
        except ErroLab as erro:
            v.problemas.append(f"{nome}: {erro}")
    plano = env.get(VAR_PLANO_SHA256, "")
    if plano and not _SHA256.fullmatch(plano):
        v.problemas.append(f"{VAR_PLANO_SHA256}: use os 64 caracteres hexadecimais minúsculos do plano_sha256 de uma simulação.")

    if exigir_github:
        _validar_contexto_do_github(env, v)
    if exigir_oidc:
        if env.get("ACTIONS_ID_TOKEN_REQUEST_URL") and env.get("ACTIONS_ID_TOKEN_REQUEST_TOKEN"):
            v.portoes.append("OIDC disponível neste job (nenhum token é lido nem exibido)")
        else:
            v.problemas.append("OIDC indisponível: o job precisa da permissão 'id-token: write' e do ambiente protegido. "
                               "Nenhum login será tentado.")
    aceitas = _variaveis_aceitas(env, v)
    if exigir_azure:
        _validar_variaveis_do_azure(aceitas, v, fase)
    _validar_segredos(env, v, fase, exigir_azure or exigir_segredo_login)
    login, implantacao = aceitas.get(VAR_ID_APLICACAO_LOGIN, ""), aceitas.get("AZURE_CLIENT_ID", "")
    if login and implantacao and login.casefold() == implantacao.casefold():
        v.problemas.append(f"{VAR_ID_APLICACAO_LOGIN}: é igual a AZURE_CLIENT_ID, mas são objetos diferentes: AZURE_CLIENT_ID é a "
                           f"identidade federada que IMPLANTA (OIDC, sem segredo) e {VAR_ID_APLICACAO_LOGIN} é o registro do "
                           "Microsoft Entra ID que autentica quem usa o chat. Informe o ID do registro de login (valores não exibidos).")
    if aceitas.get(VAR_ACESSO_DOCUMENTAL, "true") != "true":
        v.problemas.append(f"{VAR_ACESSO_DOCUMENTAL}: o L300 exige o controle de acesso por documento ligado (true).")

    if v.ok:
        v.exportar = {nome: valor for nome, valor in sorted(aceitas.items())
                      if nome.startswith("VARELEIRA_") and nome not in NAO_EXPORTAR and valor}
        if not v.aplicar:
            v.exportar.pop(VAR_CONFIRMACAO, None)  # a confirmação só vale (e só é repassada) quando se pede para aplicar
    return v


def escrever_github_env(caminho: str, exportar: Mapping[str, str]) -> int:
    """Acrescenta ao arquivo GITHUB_ENV só valores já validados: nome VARELEIRA_*, valor sem espaço nem quebra de linha."""
    linhas = []
    for nome, valor in exportar.items():
        if nome_de_segredo(nome):
            raise ErroLab("Recusado: segredos nunca são exportados para o GITHUB_ENV; o do login da aplicação só existe como "
                          "variável efêmera dos passos que o recebem de secrets (nada foi gravado).")
        if not _NOME_DE_VARIAVEL.fullmatch(nome) or not _VALOR_DE_VARIAVEL.fullmatch(valor):
            raise ErroLab("Recusado: um nome ou valor a exportar tem formato fora do permitido (nada foi gravado).")
        linhas.append(f"{nome}={valor}\n")
    if linhas:
        with open(caminho, "a", encoding="utf-8", newline="\n") as arquivo:
            arquivo.write("".join(linhas))
    return len(linhas)


def _exigir_relatorio_novo(caminho: Path | None) -> Path | None:
    """Confere o destino do relatório ANTES de qualquer trabalho: nome limitado, pasta existente, arquivo inexistente."""
    if caminho is None:
        return None
    if not _NOME_DE_RELATORIO.fullmatch(caminho.name):
        raise ErroLab("O nome do relatório deve ter até 100 caracteres, começar por letra ou número, usar só letras, números, "
                      "'.', '_' e '-', e terminar em .json.")
    if not caminho.parent.is_dir():
        raise ErroLab("A pasta do relatório não existe. Crie a pasta e repita.")
    if caminho.exists():
        raise ErroLab(f"O relatório {caminho.name} já existe e não é sobrescrito. Escolha outro nome.")
    return caminho


def _gravar_relatorio(caminho: Path, dados: Mapping[str, Any]) -> None:
    """Cria o relatório JSON em um arquivo NOVO (nunca sobrescreve) e, em sistemas POSIX, legível só pelo dono."""
    texto = json.dumps(dados, ensure_ascii=False, indent=2) + "\n"
    if contem_segredo(texto):
        raise ErroLab("O relatório continha o valor do segredo do login da aplicação e NÃO foi gravado (o valor não é exibido). "
                      "Nenhum relatório pode trazer segredos: confira o que foi informado nas opções e repita.", CODIGO_INESPERADO)
    try:
        descritor = os.open(caminho, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raise ErroLab(f"O relatório {caminho.name} já existe e não é sobrescrito. Escolha outro nome.") from None
    except OSError:
        raise ErroLab(f"Não foi possível criar o relatório {caminho.name}.") from None
    with os.fdopen(descritor, "w", encoding="utf-8", newline="\n") as arquivo:
        arquivo.write(texto)


def _ler_bytes(caminho: Path, limite: int) -> bytes:
    try:
        if not caminho.is_file():
            raise ErroLab(f"Arquivo não encontrado: {caminho.name}.")
        if caminho.stat().st_size > limite:
            raise ErroLab(f"O arquivo {caminho.name} passa do limite de {limite / (1024 * 1024):g} MiB e não foi lido.")
        return caminho.read_bytes()
    except OSError:
        raise ErroLab(f"Não foi possível ler o arquivo {caminho.name}.") from None


def _decodificar(bruto: bytes) -> str:
    # O PowerShell 5 grava redirecionamentos em UTF-16; os demais, em UTF-8 (às vezes com BOM).
    return bruto.decode("utf-16") if bruto.startswith((b"\xff\xfe", b"\xfe\xff")) else bruto.decode("utf-8-sig")


def _ler_json(caminho: Path, limite: int | None = None) -> tuple[bytes, Any]:
    bruto = _ler_bytes(caminho, limite or LIMITE_ARQUIVO_BYTES)
    try:
        return bruto, json.loads(_decodificar(bruto))
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise ErroLab(f"O arquivo {caminho.name} não contém JSON válido.") from None


def _ler_json_opcional(caminho: Path | None) -> tuple[Any, str]:
    """Para evidências que o workflow tenta baixar: arquivo ausente ou ilegível vira 'indisponível', nunca erro."""
    if caminho is None:
        return None, "ausente"
    try:
        _, dados = _ler_json(caminho, 4 * 1024 * 1024)
    except ErroLab:
        return None, "ilegivel"
    return dados, "ok"


# --------------------------------------------------------------------------------------
# Etapa validar
# --------------------------------------------------------------------------------------

def etapa_validar(args: argparse.Namespace, env: Mapping[str, str]) -> int:
    v = validar_operacao(env, exigir_github=args.exigir_github, exigir_oidc=args.exigir_oidc, exigir_azure=args.exigir_azure,
                         exigir_segredo_login=args.exigir_segredo_login)
    if not v.ok:
        raise ErroLab("Operação L300 bloqueada antes de qualquer chamada de rede ou de nuvem:\n"
                      + "\n".join(f"  - {problema}" for problema in v.problemas)
                      + "\nCorrija as entradas e repita. Nada foi alterado.", CODIGO_USO)
    print("Operação L300: validação local (sem rede, sem Azure, sem GitHub)")
    print(f"Fase: {v.fase}")
    print("Modo: " + ("APLICAÇÃO (altera a nuvem, só depois da aprovação do ambiente protegido)" if v.aplicar
                      else "SIMULAÇÃO (what-if: nada é alterado)"))
    print("Portões conferidos:")
    for portao in v.portoes:
        print(f"  [ok] {portao}")
    for aviso in v.avisos:
        print(f"[AVISO] {aviso}")
    print("Credenciais: a implantação usa a identidade federada (OIDC), sem segredo; o login da aplicação é OUTRA credencial "
          f"(registro do Entra ID do chat), com segredo só na fase aplicacao ({VAR_SEGREDO_LOGIN}, de secrets do ambiente protegido).")
    print("Configuração privada (IDs e nomes; NÃO são credenciais): vem de secrets individuais do ambiente protegido, que o runner "
          "mascara; a não privada (SKUs, réplicas, partições, regiões e ação sem login) vem de vars, uma a uma.")
    if args.exportar_github_env:
        caminho = env.get("GITHUB_ENV", "")
        if not caminho or env.get("GITHUB_ACTIONS") != "true":
            raise ErroLab("--exportar-github-env só funciona dentro do GitHub Actions (GITHUB_ENV ausente).")
        total = escrever_github_env(caminho, v.exportar)
        print(f"Exportadas para os próximos passos: {total} variável(is) VARELEIRA_* validadas (valores não exibidos; nunca o segredo "
              "do login da aplicação).")
    print("Resultado: entradas válidas. Isto NÃO prova autorização no Azure nem a proteção do ambiente do GitHub: "
          "esses itens são conferidos nas etapas seguintes do workflow.")
    return CODIGO_OK


# --------------------------------------------------------------------------------------
# Etapa plano
# --------------------------------------------------------------------------------------

_PORTOES_COMUNS = (
    "execução manual (workflow_dispatch) na branch principal, em ambiente protegido do GitHub com revisores obrigatórios",
    "a simulação (what-if) sanitizada roda sempre antes e não pode ter exclusões, itens não suportados sem qualificação "
    "nem mudanças potenciais",
    "para aplicar: aplicar=true e a confirmação APLICAR-L300-<FASE>",
)

PLANO_DAS_FASES: dict[str, dict[str, Any]] = {
    "rede": {
        "objetivo": "Preparar a rede privada e os recursos novos do L300. O acesso público dos dados continua aberto.",
        "cria": [
            "rede virtual com sub-redes para o ambiente do Container Apps e para os endpoints privados, e zonas de DNS privado "
            "ligadas a ela",
            "endpoints privados do armazenamento (Blob), da busca e dos modelos",
            "contêiner de documentos do L300 e os papéis de dados de quem carrega os documentos",
            "Shared Private Links (SPL) da busca para o Blob e para os modelos, pendentes de aprovação no destino",
            "novo ambiente do Azure Container Apps integrado à rede (o ambiente do L200 não pode ser movido para uma rede)",
        ],
        "reutiliza": [
            "armazenamento, busca e modelos que já existem (só referenciados ou reaplicados com a configuração atual)",
            "registro de imagens (ACR Basic): continua com endereço público, autenticado",
        ],
        "altera": ["os serviços de dados existentes ganham caminhos privados (endpoints e SPL); o acesso público deles continua habilitado"],
        "fora_do_bicep": [
            "aprovação das conexões das SPL nos recursos de destino (Blob e modelos)",
            "criação dos objetos do índice (índice, fonte de dados, skillset e indexador com executionEnvironment = private) pelo "
            "script de ingestão, de dentro da rede",
            "registro do aplicativo e papéis Vareleira.Atendimento e Vareleira.Corretor no Microsoft Entra ID",
        ],
        "efeito_na_migracao": [
            "O L300 nasce ao lado do L200: ambiente novo. O ambiente e a aplicação do L200 não são alterados.",
            "Nada é removido nesta fase.",
        ],
        "precondicoes": [
            "grupo de recursos, nomes dos recursos existentes (conta, busca, modelos, registro de imagens, identidade da aplicação e "
            "workspace de logs) e ID de objeto de quem carrega os documentos, informados por secrets individuais do ambiente "
            "protegido (configuração privada, mascarada pelo runner; não são credenciais)",
            "aplicar=true só depois de revisar o what-if sanitizado",
        ],
        "portoes": list(_PORTOES_COMUNS),
        "proxima_fase": "aplicacao",
    },
    "aplicacao": {
        "objetivo": "Publicar a aplicação L300 no novo ambiente, com login e controle de acesso por documento.",
        "cria": [
            "nova aplicação do chat L300 no ambiente integrado à rede, com a imagem da tag informada (publicada antes no registro) "
            "e o ingresso fechado, a menos que o ingresso externo seja ligado de propósito",
            "autenticação integrada do Microsoft Entra ID, com os perfis de aplicativo Vareleira.Atendimento e Vareleira.Corretor; "
            "usuário e perfis vêm só da plataforma",
            f"configuração da aplicação com {VAR_ACESSO_DOCUMENTAL}=true e o índice {INDICE_L300}",
        ],
        "reutiliza": [
            "rede, endpoints privados, SPL e ambiente da fase rede",
            "armazenamento, busca, modelos, registro de imagens, identidade da aplicação e logs já existentes (nomes por variáveis)",
        ],
        "altera": [],
        "fora_do_bicep": [
            f"carga e ingestão dos documentos no índice {INDICE_L300}: operação de dados, feita por um runner DENTRO da rede "
            "(nunca por runner hospedado pelo GitHub)",
            "publicação da imagem no registro, antes desta fase",
        ],
        "efeito_na_migracao": [
            "O L200 segue funcionando em paralelo; só migre os usuários depois de validar o L300.",
            "Com o ingresso externo ligado, o endereço do L300 fica público (com login): ligue só depois de conferir o login e a "
            "autorização documental.",
        ],
        "precondicoes": [
            "fase rede aplicada e conferida",
            "imagem com a tag informada já publicada no registro",
            f"registro de aplicativo do Entra ID do chat criado fora do Bicep: {VAR_ID_APLICACAO_LOGIN} e {VAR_ID_TENANT_LOGIN} em "
            "secrets individuais do ambiente protegido (configuração privada, não credenciais) e, à parte, o segredo de cliente "
            f"({VAR_SEGREDO_LOGIN}), também em secrets do ambiente protegido; esse segredo é outra credencial, que "
            "não se confunde com a identidade de implantação (OIDC)",
        ],
        "portoes": [*_PORTOES_COMUNS, "tag de imagem imutável (nunca 'latest')",
                    "ingresso_externo=true é um portão à parte, só nesta fase"],
        "proxima_fase": "isolar",
    },
    "isolar": {
        "objetivo": "Fechar o acesso público dos dados (armazenamento, busca e modelos) depois de provar o caminho privado.",
        "cria": [],
        "reutiliza": ["toda a rede privada, a aplicação L300 e o registro de imagens (continua público, com autenticação)"],
        "altera": [
            "armazenamento, busca e modelos passam a aceitar apenas o caminho privado; o ARM reaplica cada serviço inteiro, então "
            "a configuração ATUAL deles (camada, réplicas, partições e regiões) precisa ser informada por variáveis",
        ],
        "efeito_na_migracao": [
            "A aplicação do L200 e qualquer script executado fora da rede (inclusive os do L100 no seu computador) perdem o "
            "acesso aos dados. Migre os usuários para o L300 antes ou aceite a interrupção do L200.",
            f"Operações de dados (carga, ingestão, conferência) passam a exigir um runner dentro da rede, como o runner "
            f"confiável {list(RUNNER_ROTULOS)}.",
        ],
        "precondicoes": [
            "DNS privado resolvendo, de dentro da rede, o armazenamento, a busca e os modelos",
            "SPL da busca para o Blob e para os modelos APROVADAS no destino",
            f"aplicação L300 respondendo uma pergunta pelos endpoints privados e ingestão concluída no índice {INDICE_L300} "
            "com o indexador em executionEnvironment = private",
            "prova positiva (o caminho privado funciona) coletada por você antes; a prova negativa (o caminho público foi "
            "recusado) só existe depois de isolar: a conferência está em --etapa conferir",
            f"configuração ATUAL dos serviços de dados em variáveis do ambiente protegido ({VAR_SKU_ARMAZENAMENTO}, {VAR_SKU_BUSCA}, "
            f"{VAR_REPLICAS_BUSCA} e {VAR_PARTICOES_BUSCA}; as regiões só se algum serviço não estiver na do grupo de recursos)",
        ],
        "portoes": [*_PORTOES_COMUNS, "conectividade_privada_validada=true: atestação sua, que o workflow não consegue verificar "
                    "(vale também para a simulação: o Bicep recusa a fase sem ela)"],
        "proxima_fase": None,
    },
}

NAO_FAZ = (
    "não apaga recursos nem dados e não usa o modo Complete de implantação",
    "não troca modelos, deployments nem versões",
    "não concede papéis amplos (como Owner ou Contributor) nem cria credenciais com segredo",
    "não altera o L100 nem o L200 além do que o what-if mostrar e você aprovar",
)

# Duas credenciais DIFERENTES. Nunca use a de uma no lugar da outra. Os IDs delas são configuração privada, não credenciais.
CREDENCIAIS: dict[str, dict[str, Any]] = {
    "implantacao_oidc": {
        "quem": "identidade federada do GitHub Actions: executa a implantação no Azure (OIDC, token de vida curta)",
        "variaveis": list(VARS_DE_IDENTIDADE),
        "segredo": "nenhum: AZURE_CLIENT_SECRET e as demais credenciais do Azure são recusados",
    },
    "login_da_aplicacao": {
        "quem": "registro de aplicativo do Microsoft Entra ID do chat: autentica quem usa a aplicação (outro objeto, que não é a "
                "identidade de implantação)",
        "fase": "aplicacao",
        "variaveis": [VAR_ID_APLICACAO_LOGIN, VAR_ID_TENANT_LOGIN, f"{VAR_ACAO_SEM_LOGIN} (opcional)"],
        "segredo": f"{VAR_SEGREDO_LOGIN}: o único segredo aceito; só em secrets do ambiente protegido, como variável efêmera dos "
                   "passos que validam, simulam e aplicam; vira o parâmetro @secure do Bicep e o secret do Azure Container Apps; "
                   "nunca vai para vars, GITHUB_ENV, argumentos, console nem relatórios",
    },
}

# De onde vem cada variável que não é credencial: o runner imprime env e with ANTES do run, então o que é privado precisa ser
# secret (mascarado desde o primeiro uso) e o que não é pode ser var, mas sempre mapeado campo a campo.
CONFIGURACAO: dict[str, dict[str, Any]] = {
    "privada": {
        "o_que_e": "identificadores e nomes que sozinhos não dão acesso a nada, mas não devem aparecer nos registros; NÃO são "
                   "credenciais",
        "onde": "secrets individuais do ambiente protegido (o runner os mascara desde o primeiro uso); nunca vars nem vars serializado",
        "variaveis": list(VARS_PRIVADAS),
    },
    "nao_privada": {
        "o_que_e": "SKUs, réplicas, partições, regiões e a ação sem login",
        "onde": "variáveis (vars) do ambiente protegido, mapeadas uma a uma no workflow",
        "variaveis": list(VARS_NAO_PRIVADAS),
    },
}


def montar_plano(fase: str) -> dict[str, Any]:
    if fase != "todas" and fase not in FASES:
        raise ErroLab(f"Fase inválida: use uma destas: {', '.join((*FASES, 'todas'))}.")
    fases = FASES if fase == "todas" else (fase,)
    return {
        "versao": 1,
        "tipo": "plano-declarativo",
        "origem": "contrato de interface do L300; o what-if do ARM é a fonte da verdade e substitui esta descrição",
        "nuvem": {"chamadas": 0, "executa": False},
        "credenciais": copy.deepcopy(CREDENCIAIS),
        "configuracao": copy.deepcopy(CONFIGURACAO),
        "fases": [{"fase": nome, **PLANO_DAS_FASES[nome], "nao_faz": list(NAO_FAZ)} for nome in fases],
    }


def _imprimir_plano(plano: Mapping[str, Any]) -> None:
    print("Plano declarativo do L300 (local: nenhuma chamada de rede, nada é consultado nem alterado)")
    print(f"Origem: {plano['origem']}.")
    print("Credenciais (são duas, diferentes):")
    implantacao, login = plano["credenciais"]["implantacao_oidc"], plano["credenciais"]["login_da_aplicacao"]
    print(f"  - Implantação (OIDC): {implantacao['quem']}. Variáveis: {', '.join(implantacao['variaveis'])}. Segredo: "
          f"{implantacao['segredo']}.")
    print(f"  - Login da aplicação (fase {login['fase']}): {login['quem']}. Variáveis: {', '.join(login['variaveis'])}. "
          f"Segredo: {login['segredo']}.")
    privada, nao_privada = plano["configuracao"]["privada"], plano["configuracao"]["nao_privada"]
    print("Configuração (não é credencial):")
    print(f"  - Privada: {privada['o_que_e']}. Vem de {privada['onde']}: {', '.join(privada['variaveis'])}.")
    print(f"  - Não privada: {nao_privada['o_que_e']}. Vem de {nao_privada['onde']}: {', '.join(nao_privada['variaveis'])}.")
    rotulos = (("cria", "Cria (esperado)"), ("reutiliza", "Reutiliza"), ("altera", "Altera"), ("fora_do_bicep", "Fora do Bicep"),
               ("efeito_na_migracao", "Efeito na migração"), ("precondicoes", "Pré-condições"),
               ("portoes", "Portões para aplicar"), ("nao_faz", "Não faz"))
    for fase in plano["fases"]:
        print(f"\nFase '{fase['fase']}': {fase['objetivo']}")
        for chave, titulo in rotulos:
            itens = fase.get(chave) or []
            if itens:
                print(f"  {titulo}:")
                for item in itens:
                    print(f"    - {item}")
        if fase.get("proxima_fase"):
            print(f"  Próxima fase: {fase['proxima_fase']}")


def localizar_bicep() -> str | None:
    """O Bicep CLI mais novo entre AZURE_CONFIG_DIR/bin, ~/.azure/bin e o PATH."""
    nome = "bicep.exe" if os.name == "nt" else "bicep"
    pastas = [os.environ.get("AZURE_CONFIG_DIR"), str(Path.home() / ".azure")]
    candidatos = {str(Path(pasta) / "bin" / nome) for pasta in pastas if pasta}
    candidatos.add(shutil.which("bicep") or "")

    def versao(executavel: str) -> tuple[int, ...]:
        try:
            saida = subprocess.run([executavel, "--version"], capture_output=True, text=True, timeout=30, check=False,
                                   env=ambiente_sem_credenciais()).stdout
        except (OSError, subprocess.SubprocessError):
            return (0,)
        achado = re.search(r"(\d+)\.(\d+)\.(\d+)", saida)
        return tuple(int(parte) for parte in achado.groups()) if achado else (0,)

    return max((c for c in candidatos if c and Path(c).is_file()), key=versao, default=None)


def validar_bicep(arquivo: Path = BICEP_L300, *, binario: str | None = None, executar: Callable[..., Any] | None = None
                  ) -> dict[str, Any]:
    """Compila e roda o lint do TEMPLATE no seu computador, com o mesmo rigor do CI: lint SEM avisos. Não chama o Azure.

    Aviso, erro ou qualquer saída do lint é recusado; a mensagem só traz contagens e códigos de regra, nunca o texto do
    diagnóstico, caminhos nem valores. Compila somente infra/l300.bicep, nunca o arquivo de parâmetros: a compilação dos
    parâmetros leria o segredo do login da aplicação e a opção --stdout o exibiria. Por isso o programa roda com um ambiente
    sem nenhuma credencial.
    """
    if not arquivo.is_file():
        raise ErroLab("infra/l300.bicep ainda não existe neste checkout: a compilação NÃO foi conferida.")
    binario = binario or localizar_bicep()
    if not binario:
        raise ErroLab("Bicep CLI não encontrado (PATH, ~/.azure/bin ou AZURE_CONFIG_DIR): a compilação NÃO foi conferida. "
                      "Instale com 'az bicep install'.")
    executar = executar or subprocess.run
    opcoes = {"capture_output": True, "text": True, "encoding": "utf-8", "timeout": 180, "check": False,
              "env": ambiente_sem_credenciais()}
    versao = re.search(r"\d+\.\d+\.\d+", executar([binario, "--version"], **opcoes).stdout or "")
    compilacao = executar([binario, "build", str(arquivo), "--stdout"], **opcoes)
    lint = executar([binario, "lint", str(arquivo)], **opcoes)
    diagnosticos = ((lint.stdout or "") + (lint.stderr or "")).strip()
    resultado = {"arquivo": "infra/l300.bicep", "versao_do_bicep": versao.group(0) if versao else "desconhecida",
                 "compila": compilacao.returncode == 0, "avisos_do_lint": len(re.findall(r": Warning ", diagnosticos)),
                 "erros_do_lint": len(re.findall(r": Error ", diagnosticos))}
    if not resultado["compila"] or resultado["erros_do_lint"]:
        raise ErroLab(f"O Bicep não compilou ou o lint acusou erros ({resultado['erros_do_lint']} erro(s) no lint). "
                      "Rode 'bicep build infra/l300.bicep' para ver os detalhes.")
    if lint.returncode != 0 or diagnosticos:
        regras = Counter(re.findall(r": (?:Warning|Info|Error) ([A-Za-z0-9-]{1,40}):", diagnosticos))
        por_regra = ", ".join(f"{regra}={n}" for regra, n in sorted(regras.items())[:10]) or "sem código reconhecido"
        raise ErroLab(f"O lint do Bicep não está limpo ({resultado['avisos_do_lint']} aviso(s); regras: {por_regra}). O padrão do "
                      "projeto é lint SEM avisos, o mesmo do CI: corrija os avisos ou use o Bicep da versão que o CI fixa "
                      "(BICEP_VERSAO em .github/workflows/validar.yml). Rode 'bicep lint infra/l300.bicep' para ver os detalhes; "
                      "nenhum trecho do Bicep, caminho ou valor é repetido aqui.")
    return resultado


def etapa_plano(args: argparse.Namespace, env: Mapping[str, str]) -> int:
    relatorio = _exigir_relatorio_novo(Path(args.relatorio) if args.relatorio else None)
    plano = montar_plano(env.get(VAR_FASE) or FASE_PADRAO)
    if args.validar_bicep:
        plano["bicep"] = validar_bicep()
    if args.formato == "json":
        print(json.dumps(plano, ensure_ascii=False, indent=2))
    else:
        _imprimir_plano(plano)
        if args.validar_bicep:
            b = plano["bicep"]
            print(f"\nBicep (local, sem Azure): {b['arquivo']} compila com a versão {b['versao_do_bicep']} e o lint está limpo "
                  "(sem avisos, como no CI).")
    if relatorio is not None:
        _gravar_relatorio(relatorio, plano)
    return CODIGO_OK


# --------------------------------------------------------------------------------------
# Etapa sanitizar-whatif
# --------------------------------------------------------------------------------------

TIPOS_DE_MUDANCA = ("Create", "Delete", "Deploy", "Ignore", "Modify", "NoChange", "Unsupported")
TIPOS_DE_PROPRIEDADE = ("Array", "Create", "Delete", "Modify", "NoEffect")
TIPO_NAO_IDENTIFICADO = "<tipo-nao-identificado>"
GARANTIAS_DO_WHATIF = (
    "Só contagens, tipos de recurso e caminhos de propriedades: nenhum valor antes/depois, identificador de recurso, endereço, "
    "principal de acesso, segredo ou mensagem do serviço.",
    "O arquivo bruto não é copiado nem guardado; só o hash dele (bruto_sha256) é registrado.",
)


def _literais_da_expressao(expressao: str) -> list[str] | None:
    """Conteúdo dos literais entre aspas simples de uma expressão do ARM, na ordem em que aparecem.

    Duas aspas seguidas ('') dentro de um literal são uma aspa escapada. Não há limite de tamanho por literal: um literal
    longo (como o ID do escopo) precisa ser lido inteiro, senão as aspas dos seguintes desalinham. Devolve None se algum
    literal não fecha, porque nada de uma expressão malformada é confiável.
    """
    literais: list[str] = []
    abertura = expressao.find("'")
    while abertura >= 0:
        busca = abertura + 1
        while True:
            fechamento = expressao.find("'", busca)
            if fechamento < 0:
                return None
            if not expressao.startswith("'", fechamento + 1):
                break
            busca = fechamento + 2
        literais.append(expressao[abertura + 1:fechamento])
        abertura = expressao.find("'", fechamento + 1)
    return literais


def tipo_do_recurso(resource_id: Any) -> str | None:
    """Só o tipo (por exemplo Microsoft.Search/searchServices) de um resourceId; nome, grupo e assinatura são descartados."""
    if not isinstance(resource_id, str) or not resource_id:
        return None
    # Expressão que o ARM não resolveu (itens Unsupported): o tipo é o primeiro literal com a forma de um tipo. Os demais
    # literais, como o ID longo do escopo, são lidos inteiros, mas nunca viram tipo.
    if resource_id.startswith("["):
        for literal in _literais_da_expressao(resource_id) or ():
            if len(literal) <= LIMITE_DE_CARACTERES_DO_TIPO and _TIPO_DE_RECURSO.fullmatch(literal):
                return literal
        return None
    if "/providers/" in resource_id:
        resto = resource_id.rsplit("/providers/", 1)[1].split("/")
        if len(resto) < 3 or len(resto) % 2 == 0:
            return None
        tipo = "/".join([resto[0], *resto[1::2]])
        return tipo if _TIPO_DE_RECURSO.fullmatch(tipo) else None
    if re.fullmatch(r"/subscriptions/[^/]+/resourceGroups/[^/]+", resource_id):
        return "Microsoft.Resources/resourceGroups"
    return None


def _sanitizar_caminho(caminho: str) -> str:
    """Mantém só nomes de propriedade; índices viram '*' e qualquer chave que pareça nome, ID ou segredo vira '<chave>'."""
    segmentos = []
    for segmento in caminho.split(".")[:12]:
        if re.fullmatch(r"[0-9]+", segmento):
            segmentos.append("*")
        elif _SEGMENTO.fullmatch(segmento) and not _PARECE_HEX.fullmatch(segmento):
            segmentos.append(segmento)
        else:
            segmentos.append("<chave>")
    return ".".join(segmentos)[:200]


def _lista(valor: Any, nome: str) -> list[Any]:
    if valor is None:
        return []
    if not isinstance(valor, list):
        raise ErroFormato(f"o campo '{nome}' não é uma lista")
    return valor


def _percorrer_delta(delta: Any, destino: dict[str, Any]) -> None:
    pilha = [(no, "", 1) for no in reversed(_lista(delta, "delta"))]
    visitados = 0
    while pilha:
        no, prefixo, nivel = pilha.pop()
        visitados += 1
        if visitados > LIMITE_DE_NOS_DO_DELTA or nivel > LIMITE_DE_NIVEIS_DO_DELTA:
            raise ErroFormato("o 'delta' é grande ou profundo demais para ser conferido")
        if not isinstance(no, dict):
            raise ErroFormato("um item de 'delta' não é um objeto")
        caminho, mudanca = no.get("path"), no.get("propertyChangeType")
        if not isinstance(caminho, str) or mudanca not in TIPOS_DE_PROPRIEDADE:
            raise ErroFormato("um item de 'delta' não tem 'path' ou 'propertyChangeType' reconhecíveis")
        completo = f"{prefixo}.{caminho}" if prefixo else caminho
        destino["propriedades"][mudanca] += 1
        if mudanca != "NoEffect":
            destino["caminhos"].add((_sanitizar_caminho(completo), mudanca))
        for filho in reversed(_lista(no.get("children"), "children")):
            pilha.append((filho, completo, nivel + 1))


@dataclass
class AnaliseWhatIf:
    status: str
    codigo_do_erro: str | None
    mudancas: Counter
    por_tipo: dict[str, dict[str, Any]]
    nao_suportados: Counter
    motivos_nao_suportado: Counter
    removidas: Counter
    potenciais: int
    diagnosticos: Counter
    codigos_de_diagnostico: set[str]


def analisar_whatif(dados: Any) -> AnaliseWhatIf:
    """Lê o JSON do what-if e guarda só contagens, tipos e caminhos. Falha com ErroFormato se a forma for desconhecida."""
    if not isinstance(dados, dict):
        raise ErroFormato("a raiz do JSON não é um objeto (nulo, lista ou valor simples)")
    status = dados.get("status")
    if not isinstance(status, str) or not status:
        raise ErroFormato("falta o campo 'status' (texto)")
    status = status if _PALAVRA.fullmatch(status) else "Desconhecido"
    erro, codigo_do_erro = dados.get("error"), None
    if erro is not None:
        bruto = erro.get("code") if isinstance(erro, dict) else None
        codigo_do_erro = bruto if isinstance(bruto, str) and _CODIGO_CURTO.fullmatch(bruto) else "desconhecido"
    brutas = dados.get("changes")
    if brutas is None and (status != "Succeeded" or erro is not None):
        brutas = []
    if not isinstance(brutas, list):
        raise ErroFormato("o campo 'changes' não é uma lista")

    analise = AnaliseWhatIf(status, codigo_do_erro, Counter(), {}, Counter(), Counter(), Counter(), 0, Counter(), set())
    for indice, mudanca in enumerate(brutas):
        if not isinstance(mudanca, dict):
            raise ErroFormato(f"o item {indice} de 'changes' não é um objeto")
        tipo_da_mudanca = mudanca.get("changeType")
        if tipo_da_mudanca not in TIPOS_DE_MUDANCA:
            raise ErroFormato(f"o item {indice} de 'changes' tem um 'changeType' desconhecido")
        tipo = tipo_do_recurso(mudanca.get("resourceId"))
        if tipo is None:
            if tipo_da_mudanca != "Unsupported":
                raise ErroFormato(f"o item {indice} de 'changes' não tem um 'resourceId' reconhecível")
            tipo = TIPO_NAO_IDENTIFICADO
        entrada = analise.por_tipo.setdefault(
            tipo, {"mudancas": Counter(), "propriedades": Counter(), "caminhos": set()})
        entrada["mudancas"][tipo_da_mudanca] += 1
        analise.mudancas[tipo_da_mudanca] += 1
        _percorrer_delta(mudanca.get("delta"), entrada)
        if tipo_da_mudanca == "Unsupported":
            analise.nao_suportados[tipo] += 1
            motivo = mudanca.get("unsupportedReason")
            nao_calculavel = isinstance(motivo, str) and "resource ID or API version cannot be" in motivo
            analise.motivos_nao_suportado["id_ou_versao_nao_calculavel" if nao_calculavel else "outro"] += 1
    for tipo, entrada in analise.por_tipo.items():
        if entrada["propriedades"]["Delete"]:
            analise.removidas[tipo] = entrada["propriedades"]["Delete"]

    potenciais = dados.get("potentialChanges")
    if potenciais is not None and not isinstance(potenciais, list):
        raise ErroFormato("o campo 'potentialChanges' não é uma lista")
    analise.potenciais = len(potenciais or [])
    for diagnostico in _lista(dados.get("diagnostics"), "diagnostics"):
        nivel = diagnostico.get("level") if isinstance(diagnostico, dict) else None
        codigo = diagnostico.get("code") if isinstance(diagnostico, dict) else None
        analise.diagnosticos[nivel if isinstance(nivel, str) and _PALAVRA.fullmatch(nivel) else "Desconhecido"] += 1
        if isinstance(codigo, str) and _CODIGO_CURTO.fullmatch(codigo):
            analise.codigos_de_diagnostico.add(codigo)
    return analise


def _conteudo_sanitizado(analise: AnaliseWhatIf) -> dict[str, Any]:
    por_tipo = []
    for tipo in sorted(analise.por_tipo):
        entrada = analise.por_tipo[tipo]
        caminhos = sorted(entrada["caminhos"])
        por_tipo.append({
            "tipo": tipo,
            "mudancas": dict(sorted(entrada["mudancas"].items())),
            "propriedades": dict(sorted(entrada["propriedades"].items())),
            "caminhos": [{"caminho": caminho, "mudanca": mudanca} for caminho, mudanca in caminhos[:LIMITE_DE_CAMINHOS_POR_TIPO]],
            "caminhos_omitidos": max(0, len(caminhos) - LIMITE_DE_CAMINHOS_POR_TIPO),
        })
    return {
        "status_arm": analise.status,
        "codigo_do_erro_arm": analise.codigo_do_erro,
        "por_mudanca": {tipo: analise.mudancas.get(tipo, 0) for tipo in TIPOS_DE_MUDANCA},
        "por_tipo": por_tipo,
        "nao_suportados": dict(sorted(analise.nao_suportados.items())),
        "motivos_nao_suportado": dict(sorted(analise.motivos_nao_suportado.items())),
        "propriedades_removidas": dict(sorted(analise.removidas.items())),
        "mudancas_potenciais": analise.potenciais,
        "diagnosticos": dict(sorted(analise.diagnosticos.items())),
        "codigos_de_diagnostico": sorted(analise.codigos_de_diagnostico),
    }


def _sha256_do_conteudo(conteudo: Mapping[str, Any]) -> str:
    texto = json.dumps(conteudo, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(texto.encode("ascii")).hexdigest()


def _comparar_qualificacoes(codigo: str, descricao: str, ocorrencias: Mapping[str, int], qualificacoes: Mapping[str, int],
                            opcao: str) -> list[dict[str, str]]:
    """Cada tipo de recurso com itens precisa de uma qualificação com a quantidade EXATA; nada é aprovado automaticamente."""
    motivos = []
    for tipo in sorted(set(ocorrencias) | set(qualificacoes)):
        achados, qualificado = ocorrencias.get(tipo, 0), qualificacoes.get(tipo)
        if achados and qualificado is None:
            if _QUALIFICACAO.fullmatch(f"{tipo}={achados}"):
                orientacao = f"Se, depois de revisar, estiver correto, qualifique explicitamente com {opcao} {tipo}={achados}."
            else:
                orientacao = "Este item não pode ser qualificado: investigue a causa."
            motivos.append({"codigo": f"{codigo}_sem_qualificacao", "tipo": tipo, "quantidade": str(achados), "detalhe":
                            f"{achados} {descricao} do tipo {tipo} sem qualificação: o efeito não é previsto aqui e não é "
                            f"aprovado automaticamente. {orientacao}"})
        elif qualificado is not None and qualificado != achados:
            motivos.append({"codigo": f"{codigo}_qualificacao_diverge", "tipo": tipo, "quantidade": str(achados), "detalhe":
                            f"A qualificação de {tipo} diz {qualificado}, mas o plano tem {achados}: revise e atualize."})
    return motivos


def construir_relatorio_whatif(bruto: bytes, dados: Any, *, rotulo: str, nao_suportado: Mapping[str, int],
                               removidas: Mapping[str, int], plano_esperado: str = "",
                               eco_de_segredo: bool = False) -> dict[str, Any]:
    analise = analisar_whatif(dados)
    conteudo = _conteudo_sanitizado(analise)
    conteudo_sha256 = _sha256_do_conteudo(conteudo)
    motivos: list[dict[str, str]] = []
    if analise.status != "Succeeded":
        motivos.append({"codigo": "status_do_arm", "detalhe": f"O ARM terminou a simulação com o status '{analise.status}', "
                                                              "não 'Succeeded'."})
    if analise.codigo_do_erro:
        motivos.append({"codigo": "erro_do_arm", "detalhe": f"O ARM devolveu um erro na simulação (código {analise.codigo_do_erro}); "
                                                            "a mensagem foi descartada."})
    if analise.potenciais:
        motivos.append({"codigo": "mudancas_potenciais", "quantidade": str(analise.potenciais), "detalhe":
                        f"Há {analise.potenciais} mudança(s) potencial(is) que o ARM não resolveu: o plano não está concluído."})
    if analise.mudancas["Delete"]:
        tipos = sorted(tipo for tipo, entrada in analise.por_tipo.items() if entrada["mudancas"]["Delete"])
        motivos.append({"codigo": "exclusao_de_recurso", "quantidade": str(analise.mudancas["Delete"]), "detalhe":
                        f"O plano exclui {analise.mudancas['Delete']} recurso(s) existente(s) ({', '.join(tipos)}). Exclusões "
                        "nunca são esperadas aqui: revise o Bicep."})
    if analise.diagnosticos.get("Error"):
        motivos.append({"codigo": "diagnostico_de_erro", "quantidade": str(analise.diagnosticos["Error"]), "detalhe":
                        f"O ARM reportou {analise.diagnosticos['Error']} diagnóstico(s) de nível Error."})
    motivos += _comparar_qualificacoes("nao_suportado", "item(ns) não suportado(s) pelo what-if", analise.nao_suportados,
                                       nao_suportado, "--qualificar-nao-suportado")
    motivos += _comparar_qualificacoes("propriedade_removida", "propriedade(s) removida(s) em recurso existente", analise.removidas,
                                       removidas, "--qualificar-propriedades-removidas")
    if plano_esperado and plano_esperado != conteudo_sha256:
        motivos.append({"codigo": "plano_diferente_do_revisado", "detalhe": "O plano sanitizado não é o que você revisou "
                        "(plano_sha256 diferente): repita a simulação e revise de novo."})

    avisos = []
    if analise.removidas and not [m for m in motivos if m["codigo"].startswith("propriedade_removida")]:
        avisos.append(f"{sum(analise.removidas.values())} propriedade(s) removida(s) em recursos existentes foram qualificadas "
                      "por você: confira os caminhos no relatório.")
    if analise.diagnosticos.get("Warning"):
        avisos.append(f"O ARM reportou {analise.diagnosticos['Warning']} diagnóstico(s) de aviso (mensagens descartadas).")
    if not analise.mudancas:
        avisos.append("O what-if não listou nenhuma mudança.")
    if eco_de_segredo:
        avisos.append("O JSON bruto do what-if contém o valor do segredo do login da aplicação (o ARM o ecoou): trate o arquivo bruto "
                      "como segredo e apague-o ao terminar. Nada dele foi copiado para este relatório nem para o console.")
    codigo = CODIGO_DIVERGENCIA if motivos else CODIGO_OK
    return {
        "versao_relatorio": 1,
        "tipo": "whatif-sanitizado",
        "rotulo": rotulo,
        "bruto_sha256": hashlib.sha256(bruto).hexdigest(),
        "conteudo_sha256": conteudo_sha256,
        **conteudo,
        "qualificacoes": {"nao_suportado": dict(sorted(nao_suportado.items())),
                          "propriedades_removidas": dict(sorted(removidas.items()))},
        "avisos": avisos,
        "decisao": {"codigo": codigo, "resultado": "concluido" if not motivos else "bloqueado", "motivos": motivos},
        "garantias": list(GARANTIAS_DO_WHATIF),
    }


def _imprimir_resumo_do_whatif(relatorio: Mapping[str, Any]) -> None:
    print("What-if sanitizado (só contagens, tipos e caminhos; nenhum valor, identificador, endereço ou principal)")
    print(f"Rótulo: {relatorio['rotulo']}")
    print(f"Arquivo bruto: sha256 {relatorio['bruto_sha256']} (o arquivo bruto não é copiado nem enviado a lugar nenhum)")
    print(f"Status do ARM: {relatorio['status_arm']}")
    print("Mudanças por ação: " + ", ".join(f"{tipo}={n}" for tipo, n in relatorio["por_mudanca"].items()))
    if relatorio["por_tipo"]:
        print("Recursos por tipo:")
        for entrada in relatorio["por_tipo"]:
            acoes = ", ".join(f"{tipo}={n}" for tipo, n in entrada["mudancas"].items())
            propriedades = {tipo: n for tipo, n in entrada["propriedades"].items() if n and tipo != "NoEffect"}
            extra = f" | propriedades: {', '.join(f'{t}={n}' for t, n in sorted(propriedades.items()))}" if propriedades else ""
            print(f"  - {entrada['tipo']}: {acoes}{extra}")
    if relatorio["nao_suportados"]:
        print("Não suportados (o ARM não consegue prever o efeito): "
              + ", ".join(f"{tipo}={n}" for tipo, n in relatorio["nao_suportados"].items()))
    if relatorio["propriedades_removidas"]:
        print("Propriedades removidas em recursos existentes: "
              + ", ".join(f"{tipo}={n}" for tipo, n in relatorio["propriedades_removidas"].items()))
    if relatorio["mudancas_potenciais"]:
        print(f"Mudanças potenciais não resolvidas: {relatorio['mudancas_potenciais']}")
    print(f"Hash do conteúdo sanitizado (plano_sha256): {relatorio['conteudo_sha256']}")
    for aviso in relatorio["avisos"]:
        print(f"[AVISO] {aviso}")
    decisao = relatorio["decisao"]
    if decisao["motivos"]:
        print(f"Resultado: BLOQUEADO (código {decisao['codigo']}):")
        for motivo in decisao["motivos"]:
            print(f"  - {motivo['detalhe']}")
    else:
        print("Resultado: CONCLUÍDO, sem exclusões, sem itens não suportados sem qualificação e sem pendências.")


def etapa_sanitizar_whatif(args: argparse.Namespace, env: Mapping[str, str]) -> int:
    if not args.arquivo or not args.relatorio:
        raise ErroLab("Informe --arquivo (o JSON do what-if) e --relatorio (um arquivo NOVO para o relatório sanitizado).")
    relatorio = _exigir_relatorio_novo(Path(args.relatorio))
    rotulo = args.rotulo or env.get(VAR_FASE) or "sem-rotulo"
    if not _ROTULO.fullmatch(rotulo):
        raise ErroLab("O rótulo deve ter até 64 caracteres: letras, números, '.', '_' e '-', começando por letra ou número.")
    plano_esperado = args.plano_esperado or env.get(VAR_PLANO_SHA256, "")
    if plano_esperado and not _SHA256.fullmatch(plano_esperado):
        raise ErroLab("O plano esperado deve ter os 64 caracteres hexadecimais minúsculos do plano_sha256 de uma simulação.")
    try:
        nao_suportado = interpretar_qualificacoes(args.qualificar_nao_suportado or env.get(VAR_QUALIFICAR_NAO_SUPORTADO, ""))
        removidas = interpretar_qualificacoes(args.qualificar_propriedades_removidas or env.get(VAR_QUALIFICAR_REMOVIDAS, ""))
    except ErroLab as erro:
        raise ErroLab(f"Qualificação inválida: {erro}") from None
    bruto, dados = _ler_json(Path(args.arquivo))
    try:
        resultado = construir_relatorio_whatif(bruto, dados, rotulo=rotulo, nao_suportado=nao_suportado, removidas=removidas,
                                               plano_esperado=plano_esperado, eco_de_segredo=contem_segredo(_decodificar(bruto)))
    except ErroFormato as erro:
        raise ErroLab(f"O JSON não tem a forma de um what-if do ARM e não pôde ser interpretado ({erro}). Nada foi "
                      "gravado e nenhum conteúdo do arquivo é repetido aqui.", CODIGO_DIVERGENCIA) from None
    _gravar_relatorio(relatorio, resultado)
    _imprimir_resumo_do_whatif(resultado)
    print(f"Relatório sanitizado gravado: {relatorio.name}")
    return resultado["decisao"]["codigo"]


# --------------------------------------------------------------------------------------
# Etapa verificar-ambiente
# --------------------------------------------------------------------------------------

def _avaliar_aprovacoes(dados: Any, ambiente: str) -> tuple[str, int, set[str]]:
    """('aprovada' | 'sem_registro' | 'indisponivel', aprovações para o ambiente, logins distintos).

    'indisponivel' é tudo que não é uma lista de objetos: arquivo ausente ou ilegível, resposta de erro (403, 404) ou forma inesperada.
    """
    if not isinstance(dados, list) or any(not isinstance(item, dict) for item in dados):
        return "indisponivel", 0, set()
    aprovacoes, logins = 0, set()
    for item in dados:
        ambientes = item.get("environments")
        if item.get("state") != "approved" or not isinstance(ambientes, list):
            continue
        if any(isinstance(a, dict) and isinstance(a.get("name"), str) and a["name"].casefold() == ambiente.casefold()
               for a in ambientes):
            aprovacoes += 1
            usuario = item.get("user")
            if isinstance(usuario, dict) and isinstance(usuario.get("login"), str):
                logins.add(usuario["login"].casefold())
    return ("aprovada" if aprovacoes else "sem_registro"), aprovacoes, logins


def _avaliar_regras(dados: Any, ambiente: str) -> tuple[str, dict[str, Any]]:
    """('protegido' | 'sem_protecao' | 'indisponivel', detalhes) a partir de GET /repos/.../environments/<nome>.

    'indisponivel' é tudo que não é o objeto completo do ambiente pedido: ausente, ilegível, resposta de erro, outro ambiente
    ou sem a lista protection_rules.
    """
    if (not isinstance(dados, dict) or not isinstance(dados.get("name"), str)
            or dados["name"].casefold() != ambiente.casefold() or not isinstance(dados.get("protection_rules"), list)):
        return "indisponivel", {}
    revisores, impede_autoaprovacao = 0, None
    for regra in dados["protection_rules"]:
        if isinstance(regra, dict) and regra.get("type") == "required_reviewers":
            lista = regra.get("reviewers")
            revisores += len(lista) if isinstance(lista, list) else 0
            impede_autoaprovacao = bool(regra.get("prevent_self_review"))
    politica = dados.get("deployment_branch_policy")
    restringe = isinstance(politica, dict) and (politica.get("protected_branches") is True
                                                or politica.get("custom_branch_policies") is True)
    detalhes = {"revisores": revisores, "impede_autoaprovacao": impede_autoaprovacao, "restringe_branches": restringe,
                "administradores_podem_contornar": dados.get("can_admins_bypass") is True}
    return ("protegido" if revisores else "sem_protecao"), detalhes


def avaliar_ambiente(aprovacoes: Any, ambiente: Any, *, nome: str = AMBIENTE_GITHUB, ator: str = "") -> dict[str, Any]:
    """Decide se a proteção do ambiente foi COMPROVADA pelo GitHub ou REPROVADA. Não existe meio-termo nem atestação.

    O login só é liberado com TRÊS provas lidas da API do GitHub, todas juntas: revisores obrigatórios, restrição de branches e
    uma aprovação humana registrada para ESTA execução. Qualquer lacuna (arquivo ausente, 403 ou 404, JSON ilegível ou incompleto,
    outro ambiente, ambiente criado sem regras, evidência de só um dos dois endpoints) é um motivo explícito de bloqueio:
    nenhuma variável, flag ou atestação de quem dispara substitui a prova.
    """
    estado_aprovacoes, aprovadas, logins = _avaliar_aprovacoes(aprovacoes, nome)
    estado_regras, regras = _avaliar_regras(ambiente, nome)
    motivos, avisos = [], []
    if estado_aprovacoes == "indisponivel":
        motivos.append("as aprovações desta execução não puderam ser lidas (arquivo ausente, resposta de erro como 403 ou 404, JSON "
                       "ilegível ou incompleto): sem elas não há prova de aprovação humana")
    elif estado_aprovacoes == "sem_registro":
        motivos.append("nenhuma aprovação humana está registrada para o ambiente nesta execução (o ambiente não exigiu revisão)")
    if estado_regras == "indisponivel":
        motivos.append("as regras do ambiente não puderam ser lidas (arquivo ausente, resposta de erro como 403 ou 404, JSON "
                       "ilegível ou incompleto): sem elas não há prova de revisores obrigatórios nem de restrição de branches")
    elif estado_regras == "sem_protecao":
        motivos.append("o ambiente não tem revisores obrigatórios (um ambiente criado automaticamente nasce sem regras)")
    elif not regras["restringe_branches"]:
        motivos.append("o ambiente aceita qualquer branch: restrinja-o à branch principal")
    estado = "reprovado" if motivos else "comprovado"
    if estado == "comprovado":
        if regras["impede_autoaprovacao"] is False:
            avisos.append("o ambiente permite que quem dispara também aprove (prevent_self_review desligado)")
        if ator and logins and logins == {ator.casefold()}:
            avisos.append("a única aprovação registrada veio de quem disparou o workflow")
        if regras["administradores_podem_contornar"]:
            avisos.append("administradores podem contornar as regras do ambiente (can_admins_bypass)")
    return {"estado": estado, "aprovacoes": estado_aprovacoes, "aprovacoes_registradas": aprovadas, "regras": estado_regras,
            "detalhes_das_regras": regras, "motivos": motivos, "avisos": avisos}


def etapa_verificar_ambiente(args: argparse.Namespace, env: Mapping[str, str]) -> int:
    nome = args.nome_ambiente or AMBIENTE_GITHUB
    if not _NOME_DE_AMBIENTE.fullmatch(nome):
        raise ErroLab("O nome do ambiente deve ter até 64 caracteres: letras, números, '.', '_' e '-'.")
    aprovacoes, estado_a = _ler_json_opcional(Path(args.aprovacoes) if args.aprovacoes else None)
    ambiente, estado_e = _ler_json_opcional(Path(args.ambiente) if args.ambiente else None)
    resultado = avaliar_ambiente(aprovacoes, ambiente, nome=nome, ator=args.ator or "")
    print(f"Ambiente '{nome}': conferência da proteção, só com o que o GitHub devolveu (antes de qualquer login no Azure)")
    textos_a = {"aprovada": f"{resultado['aprovacoes_registradas']} aprovação(ões) registrada(s) para o ambiente nesta execução",
                "sem_registro": "nenhuma aprovação registrada para o ambiente nesta execução",
                "indisponivel": "indisponível (a API não devolveu uma lista utilizável)"}
    textos_r = {"protegido": f"revisores obrigatórios: {resultado['detalhes_das_regras'].get('revisores', 0)}; restrição de "
                             f"branches: {'sim' if resultado['detalhes_das_regras'].get('restringe_branches') else 'não'}",
                "sem_protecao": "sem revisores obrigatórios", "indisponivel": "indisponíveis (a API não devolveu as regras)"}
    print(f"  Aprovações da execução: {textos_a[resultado['aprovacoes']]}")
    print(f"  Regras do ambiente: {textos_r[resultado['regras']]}")
    if estado_a != "ok" or estado_e != "ok":
        print("  Arquivos de evidência: " + ", ".join(f"{rotulo} {estado}" for rotulo, estado in
                                                     (("aprovações", estado_a), ("ambiente", estado_e)) if estado != "ok"))
    for aviso in resultado["avisos"]:
        print(f"[AVISO] {aviso}")
    if resultado["estado"] != "comprovado":
        raise ErroLab("Proteção do ambiente NÃO comprovada: o login no Azure não será tentado. Só a leitura, pela API do GitHub, de "
                      "revisores obrigatórios, restrição de branches E aprovação registrada desta execução libera o login; "
                      "nenhuma atestação substitui essa prova.\n"
                      + "\n".join(f"  - {motivo}" for motivo in resultado["motivos"])
                      + f"\nConfigure revisores obrigatórios e a restrição à branch principal no ambiente '{nome}', aprove a execução "
                        "e confirme que o token do job lê as aprovações e as regras (permissão actions: read); depois repita.",
                      CODIGO_DIVERGENCIA)
    print("Resultado: PROTEÇÃO COMPROVADA pelo GitHub (regras, restrição de branches e aprovação desta execução).")
    return CODIGO_OK


# --------------------------------------------------------------------------------------
# Etapa conferir
# --------------------------------------------------------------------------------------

MOMENTOS = ("antes-de-isolar", "depois-de-isolar")
ESTADOS_DE_SPL = ("aprovado", "pendente", "rejeitado", "ausente")
_ROTULOS_DAS_DEPENDENCIAS = {"armazenamento": "armazenamento (Blob)", "busca": "busca", "modelos": "modelos"}
_SECOES = {
    "dns_privado": set(DEPENDENCIAS_DE_DADOS),
    "spl_busca": {"armazenamento", "modelos"},
    "aplicacao": {"prontidao_http", "revisao_ativa", "consulta_respondida", "login_publico_http"},
    "ingestao": {"indice", "ambiente_de_execucao", "ultima_execucao", "itens_processados", "itens_com_falha"},
    "acesso_privado": set(DEPENDENCIAS_DE_DADOS),
}


def _chave_segura(chave: Any) -> str:
    return chave if isinstance(chave, str) and re.fullmatch(r"[a-z_]{1,40}", chave) else "<campo>"


def conferir_descritor(dados: Any, momento: str) -> dict[str, Any]:
    """Confere um descritor de evidências preenchido por VOCÊ. Não prova nada: só aponta o que falta ou contradiz."""
    if momento not in MOMENTOS:
        raise ErroLab(f"Momento inválido: use {' ou '.join(MOMENTOS)}.")
    problemas: list[str] = []
    if not isinstance(dados, dict):
        raise ErroLab("O descritor precisa ser um objeto JSON.")
    if dados.get("versao") != 1 or isinstance(dados.get("versao"), bool):
        problemas.append("'versao' deve ser 1.")
    if dados.get("origem") not in ("operador", "simulado"):
        problemas.append("'origem' deve ser 'operador' (evidências reais, guardadas por você) ou 'simulado' (exemplo).")
    for chave in dados:
        if chave not in ("versao", "origem", *_SECOES):
            problemas.append(f"campo desconhecido na raiz: {_chave_segura(chave)}.")

    def secao(nome: str) -> dict[str, Any]:
        valor = dados.get(nome)
        if valor is None:
            return {}
        if not isinstance(valor, dict):
            problemas.append(f"'{nome}' deve ser um objeto.")
            return {}
        for chave in valor:
            if chave not in _SECOES[nome]:
                problemas.append(f"campo desconhecido em '{nome}': {_chave_segura(chave)}.")
        return valor

    def booleano(caminho: str, valor: Any) -> bool | None:
        if valor is not None and not isinstance(valor, bool):
            problemas.append(f"'{caminho}' deve ser true, false ou nulo (JSON booleano, não texto).")
            return None
        return valor

    def inteiro(caminho: str, valor: Any) -> int | None:
        if valor is not None and (isinstance(valor, bool) or not isinstance(valor, int) or valor < 0):
            problemas.append(f"'{caminho}' deve ser um inteiro maior ou igual a zero, ou nulo.")
            return None
        return valor

    verificacoes: list[dict[str, str]] = []

    def registrar(identificador: str, descricao: str, estado: str) -> None:
        verificacoes.append({"id": identificador, "descricao": descricao, "estado": estado, "origem": "descritor do operador"})

    dns, spl, app, ingestao, acesso = (secao(n) for n in ("dns_privado", "spl_busca", "aplicacao", "ingestao", "acesso_privado"))
    for dependencia in DEPENDENCIAS_DE_DADOS:
        rotulo = _ROTULOS_DAS_DEPENDENCIAS[dependencia]
        valor = booleano(f"dns_privado.{dependencia}", dns.get(dependencia))
        registrar(f"dns_privado.{dependencia}", f"{rotulo}: de dentro da rede, o nome resolve para endereço privado",
                  "pendente" if valor is None else "atendido" if valor else "reprovado")
    for destino in ("armazenamento", "modelos"):
        valor = spl.get(destino)
        if valor is not None and valor not in ESTADOS_DE_SPL:
            problemas.append(f"'spl_busca.{destino}' deve ser um destes: {', '.join(ESTADOS_DE_SPL)}.")
            valor = None
        registrar(f"spl_busca.{destino}", f"SPL da busca para {_ROTULOS_DAS_DEPENDENCIAS[destino]} aprovada no destino",
                  "pendente" if valor in (None, "pendente") else "atendido" if valor == "aprovado" else "reprovado")
    prontidao = inteiro("aplicacao.prontidao_http", app.get("prontidao_http"))
    revisao = booleano("aplicacao.revisao_ativa", app.get("revisao_ativa"))
    consulta = booleano("aplicacao.consulta_respondida", app.get("consulta_respondida"))
    registrar("aplicacao.prontidao_http", "a aplicação L300 responde 200 em /readyz (só mostra que ela está de pé, não que os "
              "dados chegam ao fim)", "pendente" if prontidao is None else "atendido" if prontidao == 200 else "reprovado")
    registrar("aplicacao.revisao_ativa", "a revisão ativa da aplicação L300 está em execução",
              "pendente" if revisao is None else "atendido" if revisao else "reprovado")
    registrar("aplicacao.consulta_respondida", "uma pergunta de teste foi respondida pela aplicação L300, usando os endpoints "
              "privados (de ponta a ponta, não só /readyz)", "pendente" if consulta is None else "atendido" if consulta else "reprovado")
    indice = ingestao.get("indice")
    if indice is not None and not isinstance(indice, str):
        problemas.append("'ingestao.indice' deve ser texto ou nulo.")
        indice = None
    ambiente_de_execucao = ingestao.get("ambiente_de_execucao")
    if ambiente_de_execucao is not None and not (isinstance(ambiente_de_execucao, str)
                                                 and re.fullmatch(r"[A-Za-z]{1,32}", ambiente_de_execucao)):
        problemas.append("'ingestao.ambiente_de_execucao' deve ser um texto curto, como private, ou nulo.")
        ambiente_de_execucao = None
    ultima = ingestao.get("ultima_execucao")
    if ultima is not None and not (isinstance(ultima, str) and re.fullmatch(r"[A-Za-z]{1,32}", ultima)):
        problemas.append("'ingestao.ultima_execucao' deve ser um texto curto, como success, ou nulo.")
        ultima = None
    itens = inteiro("ingestao.itens_processados", ingestao.get("itens_processados"))
    falhas = inteiro("ingestao.itens_com_falha", ingestao.get("itens_com_falha"))
    registrar("ingestao.indice", f"o índice conferido é o do L300 ({INDICE_L300})",
              "pendente" if indice is None else "atendido" if indice == INDICE_L300 else "reprovado")
    registrar("ingestao.ambiente_de_execucao", "o indexador roda no ambiente privado (executionEnvironment = private); no "
              "ambiente padrão a ingestão usaria o caminho público",
              "pendente" if ambiente_de_execucao is None else "atendido" if ambiente_de_execucao == "private" else "reprovado")
    registrar("ingestao.ultima_execucao", "a última execução do indexador terminou com sucesso",
              "pendente" if ultima is None else "atendido" if ultima == "success" else "reprovado")
    registrar("ingestao.itens_processados", "ao menos um item foi processado pelo caminho privado",
              "pendente" if itens is None else "atendido" if itens >= 1 else "reprovado")
    registrar("ingestao.itens_com_falha", "nenhum item falhou na ingestão",
              "pendente" if falhas is None else "atendido" if falhas == 0 else "reprovado")
    login = inteiro("aplicacao.login_publico_http", app.get("login_publico_http"))
    positivas = {d: acesso.get(d) for d in DEPENDENCIAS_DE_DADOS}
    for dependencia in DEPENDENCIAS_DE_DADOS:
        prova = positivas[dependencia]
        if prova is not None and not isinstance(prova, dict):
            problemas.append(f"'acesso_privado.{dependencia}' deve ser um objeto com 'positiva' e 'negativa'.")
            prova = None
        prova = prova or {}
        for chave in prova:
            if chave not in ("positiva", "negativa"):
                problemas.append(f"campo desconhecido em 'acesso_privado.{dependencia}': {_chave_segura(chave)}.")
        rotulo = _ROTULOS_DAS_DEPENDENCIAS[dependencia]
        positiva = booleano(f"acesso_privado.{dependencia}.positiva", prova.get("positiva"))
        negativa = booleano(f"acesso_privado.{dependencia}.negativa", prova.get("negativa"))
        registrar(f"acesso_privado.{dependencia}.positiva", f"prova positiva de {rotulo}: uma chamada de DENTRO da rede, pelo "
                  "caminho privado, funcionou", "pendente" if positiva is None else "atendido" if positiva else "reprovado")
        descricao = f"prova negativa de {rotulo}: uma chamada de FORA da rede (caminho público) foi recusada"
        if momento == "antes-de-isolar":
            registrar(f"acesso_privado.{dependencia}.negativa", descricao + " (só existe depois de isolar)", "nao_exigida_agora")
        else:
            registrar(f"acesso_privado.{dependencia}.negativa", descricao,
                      "pendente" if negativa is None else "atendido" if negativa else "reprovado")
    if problemas:
        raise ErroLab("O descritor tem problemas de forma (nenhum valor é repetido aqui):\n"
                      + "\n".join(f"  - {problema}" for problema in problemas))
    contagem = Counter(item["estado"] for item in verificacoes)
    if contagem["reprovado"]:
        resultado = "reprovado"
    elif contagem["pendente"]:
        resultado = "incompleto"
    else:
        resultado = "completo"
    avisos = []
    if login is not None:
        avisos.append("aplicacao.login_publico_http foi IGNORADO: a página de login pública responder 200 não prova nada sobre a "
                      "conectividade privada dos dados.")
    return {
        "versao_relatorio": 1, "tipo": "conferencia-de-evidencias", "momento": momento, "origem_do_descritor": dados["origem"],
        "resultado": resultado, "contagem": {estado: contagem.get(estado, 0) for estado in
                                              ("atendido", "pendente", "reprovado", "nao_exigida_agora")},
        "verificacoes": verificacoes, "avisos": avisos,
        "limite": ("Esta matriz só confere os campos do descritor que você preencheu. Ela NÃO é uma prova de segurança: a prova são "
                   "os comandos, saídas e capturas que você guarda em local privado."),
    }


def etapa_conferir(args: argparse.Namespace, env: Mapping[str, str]) -> int:
    if not args.descritor:
        raise ErroLab("Informe --descritor (o JSON de evidências que você preencheu).")
    relatorio = _exigir_relatorio_novo(Path(args.relatorio) if args.relatorio else None)
    _, dados = _ler_json(Path(args.descritor))
    resultado = conferir_descritor(dados, args.momento)
    print(f"Conferência de evidências ({resultado['momento']}; origem do descritor: {resultado['origem_do_descritor']})")
    for item in resultado["verificacoes"]:
        print(f"  [{item['estado']}] {item['id']}: {item['descricao']}")
    for aviso in resultado["avisos"]:
        print(f"[AVISO] {aviso}")
    contagem = resultado["contagem"]
    print(f"Resumo: {contagem['atendido']} atendido(s), {contagem['pendente']} pendente(s), {contagem['reprovado']} reprovado(s), "
          f"{contagem['nao_exigida_agora']} não exigido(s) neste momento.")
    if relatorio is not None:
        _gravar_relatorio(relatorio, resultado)
    if resultado["resultado"] != "completo":
        situacao = "reprovadas" if resultado["resultado"] == "reprovado" else "incompletas"
        raise ErroLab(f"Evidências {situacao}: a conectividade privada NÃO pode ser considerada validada. "
                      "Complete ou corrija os itens acima e repita. " + resultado["limite"], CODIGO_DIVERGENCIA)
    print("Resultado: descritor COMPLETO e coerente para este momento. " + resultado["limite"])
    return CODIGO_OK


# --------------------------------------------------------------------------------------
# Etapa resumir-logs (somente leitura)
# --------------------------------------------------------------------------------------

_TEMPO = r"(?:\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3} )?"
_REQUISICAO = re.compile(
    "^" + _TEMPO + r"(?:INFO|WARNING|ERROR) vareleira\.chat requisicao id=[0-9A-Za-z_-]{1,64} rota=([a-z_]{1,24}) "
    r"status=([1-5][0-9][0-9]) ms=([0-9]{1,8})(?: causa=([a-z_]{1,40}))?$")
_IGNORADAS = (
    ("partida", re.compile("^" + _TEMPO + r"INFO vareleira\.chat assistente pronto [A-Za-z0-9_=.:/ -]{0,400}$")),
    ("partida", re.compile(r"^Chat do Vareleira Lar, .{0,300}$")),
    ("partida", re.compile(r"^Endereço: http://\S{1,100}  \(encerre com Ctrl\+C\)$")),
    ("ciclo_do_servidor", re.compile(
        "^" + _TEMPO + r"(?:INFO|WARNING) uvicorn\.error (?:Started server process \[[0-9]+\]|Waiting for application startup\.|"
        r"Application startup complete\.|Uvicorn running on \S+ \(Press CTRL\+C to quit\)|Shutting down|"
        r"Waiting for application shutdown\.|Application shutdown complete\.|Finished server process \[[0-9]+\])$")),
    ("plataforma", re.compile(r"^Connecting to the container '[^']{1,64}'\.\.\.$")),
    ("plataforma", re.compile(
        r"^Successfully Connected to container: '[^']{1,64}' \[Revision: '[^']{1,128}', Replica: '[^']{1,160}'\]$")),
)
_PREFIXO_DE_TEMPO_ISO = re.compile(r"\d{4}-\d{2}-\d{2}T[0-9:.]+(?:Z|[+-]\d{2}:\d{2})\s+")
ROTAS_DE_SAUDE = ("saude", "prontidao")


def _mensagem_da_linha(linha: str) -> str | None:
    """A mensagem de uma linha do servidor: texto puro, ou o envelope JSON do Container Apps ({"TimeStamp", "Log"})."""
    texto = linha.strip()
    if texto.startswith("{"):
        try:
            dados = json.loads(texto)
        except ValueError:
            return None
        if not isinstance(dados, dict) or not isinstance(dados.get("Log"), str):
            return None
        texto = dados["Log"].strip()
    else:
        achado = _PREFIXO_DE_TEMPO_ISO.match(texto)
        texto = texto[achado.end():] if achado else texto
    if texto.startswith("P "):  # fragmento de uma linha longa: não dá para conferir
        return None
    return texto[2:] if texto.startswith("F ") else texto


def _percentil(ordenados: Sequence[int], percentual: int) -> int:
    return ordenados[max(0, math.ceil(percentual / 100 * len(ordenados)) - 1)]


def resumir_logs(linhas: Iterable[str]) -> dict[str, Any]:
    """Conta requisições, status, latência e causas. Falha FECHADA: linha desconhecida é contada e derruba o resultado."""
    total = vazias = 0
    ignoradas: Counter = Counter()
    desconhecidas: list[int] = []
    n_desconhecidas = 0
    por_rota: dict[str, dict[str, Any]] = {}
    status_geral: Counter = Counter()
    causas: dict[str, Counter] = {}
    for numero, linha in enumerate(linhas, start=1):
        total += 1
        if not linha.strip():
            vazias += 1
            continue
        mensagem = _mensagem_da_linha(linha) if len(linha) <= LIMITE_LINHA_DE_LOG else None
        achado = _REQUISICAO.match(mensagem) if mensagem is not None else None
        if achado:
            rota, status, ms, causa = achado.group(1), achado.group(2), int(achado.group(3)), achado.group(4)
            dados = por_rota.setdefault(rota, {"total": 0, "status": Counter(), "latencias": []})
            dados["total"] += 1
            dados["status"][status] += 1
            dados["latencias"].append(ms)
            status_geral[status] += 1
            if int(status) >= 400:
                causas.setdefault(status, Counter())[causa or "sem_causa"] += 1
            continue
        categoria = next((nome for nome, padrao in _IGNORADAS if mensagem is not None and padrao.match(mensagem)), None)
        if categoria:
            ignoradas[categoria] += 1
            continue
        n_desconhecidas += 1
        if len(desconhecidas) < 10:
            desconhecidas.append(numero)

    rotas = {}
    for rota in sorted(por_rota):
        dados = por_rota[rota]
        ordenados = sorted(dados["latencias"])
        rotas[rota] = {"total": dados["total"], "status": dict(sorted(dados["status"].items())),
                       "latencia_ms": {"minimo": ordenados[0], "p50": _percentil(ordenados, 50), "p95": _percentil(ordenados, 95),
                                       "maximo": ordenados[-1], "media": round(sum(ordenados) / len(ordenados))}}
    requisicoes = sum(dados["total"] for dados in por_rota.values())
    sondas = {rota: por_rota[rota]["total"] for rota in ROTAS_DE_SAUDE if rota in por_rota}
    de_usuario = requisicoes - sum(sondas.values())
    erros_5xx = sum(n for status, n in status_geral.items() if status.startswith("5"))
    erros_5xx_de_usuario = sum(n for rota, dados in por_rota.items() if rota not in ROTAS_DE_SAUDE
                               for status, n in dados["status"].items() if status.startswith("5"))
    classes: Counter = Counter()
    for status, n in status_geral.items():
        classes[f"{status[0]}xx"] += n
    codigo = CODIGO_DIVERGENCIA if n_desconhecidas else CODIGO_OK
    return {
        "versao_relatorio": 1, "tipo": "resumo-de-logs",
        "linhas": {"total": total, "vazias": vazias, "requisicoes": requisicoes, "ignoradas_conhecidas": dict(sorted(ignoradas.items())),
                   "desconhecidas": n_desconhecidas, "primeiras_desconhecidas": desconhecidas},
        "requisicoes": {"total": requisicoes, "sondas_de_saude": sondas, "de_usuario": de_usuario},
        "por_rota": rotas,
        "por_status": dict(sorted(status_geral.items())),
        "por_classe": dict(sorted(classes.items())),
        "causas_por_status": {status: dict(sorted(contagem.items())) for status, contagem in sorted(causas.items())},
        "taxa_5xx_de_usuario": round(erros_5xx_de_usuario / de_usuario, 4) if de_usuario else None,
        "erros_5xx_total": erros_5xx,
        "decisao": {"codigo": codigo, "resultado": "concluido" if not n_desconhecidas else
                    "falha_fechada: ha linhas que o resumo nao reconhece (nada delas foi copiado)"},
        "garantias": ["Só contagens de status, rotas, latência e causas curtas; nenhuma pergunta, resposta, token, URL ou "
                      "identificador é lido para a saída.",
                      "Linhas fora dos formatos conhecidos nunca são ignoradas em silêncio: são contadas e o resultado falha."],
    }


def etapa_resumir_logs(args: argparse.Namespace, env: Mapping[str, str]) -> int:
    if not args.logs:
        raise ErroLab("Informe --logs (um arquivo de logs sanitizados do chat).")
    relatorio = _exigir_relatorio_novo(Path(args.relatorio) if args.relatorio else None)
    caminho = Path(args.logs)
    try:
        texto = _decodificar(_ler_bytes(caminho, LIMITE_LOGS_BYTES))
    except UnicodeDecodeError:
        raise ErroLab(f"O arquivo {caminho.name} não está em UTF-8 nem em UTF-16 com marca de ordem.") from None
    resumo = resumir_logs(texto.splitlines())
    linhas, req = resumo["linhas"], resumo["requisicoes"]
    sondas = ", ".join(f"{rota}={n}" for rota, n in req["sondas_de_saude"].items()) or "nenhuma"
    print("Resumo de logs do chat (somente leitura; nenhuma pergunta, resposta, token ou URL é exibido)")
    print(f"Linhas: {linhas['total']} (vazias: {linhas['vazias']}); requisições: {req['total']}; sondas de saúde: {sondas}")
    if linhas["ignoradas_conhecidas"]:
        print("Linhas conhecidas ignoradas: " + ", ".join(f"{nome}={n}" for nome, n in linhas["ignoradas_conhecidas"].items()))
    print("Requisições de usuário (fora das sondas): " + str(req["de_usuario"]))
    print("Status: " + (", ".join(f"{status}={n}" for status, n in resumo["por_status"].items()) or "nenhum"))
    for rota, dados in resumo["por_rota"].items():
        lat = dados["latencia_ms"]
        print(f"  rota {rota}: {dados['total']} requisição(ões); latência ms p50={lat['p50']} p95={lat['p95']} máx={lat['maximo']}")
    for status, contagem in resumo["causas_por_status"].items():
        print(f"  causas de {status}: " + ", ".join(f"{causa}={n}" for causa, n in contagem.items()))
    if resumo["taxa_5xx_de_usuario"] is not None:
        print(f"Taxa de 5xx nas requisições de usuário: {resumo['taxa_5xx_de_usuario']:.2%}")
    if relatorio is not None:
        _gravar_relatorio(relatorio, resumo)
    if linhas["desconhecidas"]:
        raise ErroLab(f"{linhas['desconhecidas']} linha(s) não reconhecida(s) (primeiras: {linhas['primeiras_desconhecidas']}). "
                      "O resumo falha fechado: nada delas foi copiado. Sanitize o arquivo ou, se o formato do servidor mudou, "
                      "atualize o resumo.", CODIGO_DIVERGENCIA)
    print("Resultado: concluído; todas as linhas foram reconhecidas.")
    return CODIGO_OK


# --------------------------------------------------------------------------------------
# Linha de comando
# --------------------------------------------------------------------------------------

_ETAPAS: dict[str, Callable[[argparse.Namespace, Mapping[str, str]], int]] = {
    "validar": etapa_validar,
    "plano": etapa_plano,
    "sanitizar-whatif": etapa_sanitizar_whatif,
    "verificar-ambiente": etapa_verificar_ambiente,
    "conferir": etapa_conferir,
    "resumir-logs": etapa_resumir_logs,
}
ETAPAS = tuple(_ETAPAS)


def criar_parser() -> lab_comum.ParserLab:
    parser = lab_comum.ParserLab(description=__doc__)
    parser.add_argument("--etapa", required=True, choices=ETAPAS, help="validar, plano, sanitizar-whatif, verificar-ambiente, "
                        "conferir ou resumir-logs (veja a descrição acima).")
    parser.add_argument("--fase", default=None, help=f"Fase do L300: {', '.join(FASES)} (em plano, também 'todas'). "
                        f"Padrão local: {FASE_PADRAO}. No workflow vem de {VAR_FASE}.")
    parser.add_argument("--aplicar", action="store_true", help=f"Declara a intenção de APLICAR (equivale a {VAR_APLICAR}=true). "
                        "Este script nunca aplica nada: só confere os portões.")
    parser.add_argument("--conectividade-privada-validada", action="store_true",
                        help="Atestação sua de que a conectividade privada foi validada com evidências (obrigatória na fase isolar).")
    parser.add_argument("--ingresso-externo", action="store_true",
                        help="Fase aplicacao: abre o endereço público da aplicação (login obrigatório). Só depois de conferir o login "
                             "e a autorização documental com o ingresso fechado.")
    parser.add_argument("--confirmacao", default=None, help=f"Texto de confirmação para aplicar: {PREFIXO_DA_CONFIRMACAO}<FASE EM MAIÚSCULAS>.")
    parser.add_argument("--tag-imagem", default=None, help="Tag imutável da imagem já publicada no registro (obrigatória na fase aplicacao).")
    parser.add_argument("--exigir-github", action="store_true",
                        help="validar: exige o contexto do GitHub Actions (workflow_dispatch na branch principal).")
    parser.add_argument("--exigir-oidc", action="store_true",
                        help="validar: exige que o job tenha o token OIDC da identidade de implantação (sem segredo).")
    parser.add_argument("--exigir-azure", action="store_true",
                        help="validar: exige a identidade de implantação (OIDC), TODOS os destinos do infra/levels/l300.bicepparam e os "
                             "parâmetros da fase (login da aplicação em aplicacao; configuração atual dos serviços de dados em isolar), "
                             "com formato válido e sem valores padrão. A configuração privada (IDs e nomes; não são credenciais) vem "
                             "de secrets individuais do ambiente; a não privada, de vars. Em aplicacao, inclui o segredo do login da "
                             "aplicação, a única credencial com segredo.")
    parser.add_argument("--exigir-segredo-login", action="store_true",
                        help=f"validar: na fase aplicacao, exige o segredo do login da aplicação ({VAR_SEGREDO_LOGIN}, vindo de secrets do "
                             "ambiente protegido; nunca de argumento). Já incluído em --exigir-azure. Não existe opção para informar o valor.")
    parser.add_argument("--exportar-github-env", action="store_true",
                        help="validar: grava em GITHUB_ENV só as variáveis VARELEIRA_* validadas (dentro do GitHub Actions). Nunca "
                             "inclui o segredo do login da aplicação.")
    parser.add_argument("--validar-bicep", action="store_true",
                        help="plano: compila e roda o lint do TEMPLATE infra/l300.bicep localmente (sem Azure, sem credenciais, "
                             "sem compilar o arquivo de parâmetros). O lint precisa estar SEM avisos, como no CI.")
    parser.add_argument("--formato", choices=("texto", "json"), default="texto", help="plano: texto (padrão) ou json.")
    parser.add_argument("--arquivo", default=None, help="sanitizar-whatif: o JSON do what-if. Nunca é copiado nem exibido.")
    parser.add_argument("--relatorio", default=None, help="Relatório JSON a criar. Precisa ser um arquivo NOVO: nunca sobrescreve.")
    parser.add_argument("--rotulo", default=None, help="sanitizar-whatif: rótulo curto do relatório (padrão: a fase).")
    parser.add_argument("--qualificar-nao-suportado", default=None, metavar="TIPO=N,...",
                        help="sanitizar-whatif: aceita, explicitamente e pela quantidade exata, itens que o what-if não consegue prever.")
    parser.add_argument("--qualificar-propriedades-removidas", default=None, metavar="TIPO=N,...",
                        help="sanitizar-whatif: aceita, pela quantidade exata, propriedades removidas em recursos existentes.")
    parser.add_argument("--plano-esperado", default=None, metavar="SHA256",
                        help="sanitizar-whatif: exige que o conteúdo sanitizado tenha este plano_sha256 (o de uma simulação já revisada).")
    parser.add_argument("--aprovacoes", default=None,
                        help="verificar-ambiente: JSON de GET /actions/runs/<id>/approvals. Sem ele (ou ilegível, ou com erro 403), o login "
                             "não é liberado.")
    parser.add_argument("--ambiente", default=None,
                        help="verificar-ambiente: JSON de GET /environments/<nome>. Sem ele (ou ilegível, ou com erro 403), o login "
                             "não é liberado.")
    parser.add_argument("--nome-ambiente", default=None, help=f"verificar-ambiente: nome do ambiente (padrão: {AMBIENTE_GITHUB}).")
    parser.add_argument("--ator", default=None, help="verificar-ambiente: quem disparou o workflow (só para avisar sobre autoaprovação).")
    parser.add_argument("--descritor", default=None, help="conferir: o JSON de evidências que você preencheu.")
    parser.add_argument("--momento", choices=MOMENTOS, default="antes-de-isolar",
                        help="conferir: antes-de-isolar (padrão; exige as provas positivas) ou depois-de-isolar (exige também as negativas).")
    parser.add_argument("--logs", default=None, help="resumir-logs: arquivo de logs sanitizados do chat (texto ou JSON do Container Apps).")
    return parser


def _aplicar_opcoes(args: argparse.Namespace, ambiente: dict[str, str]) -> None:
    for valor, nome in ((args.fase, VAR_FASE), (args.confirmacao, VAR_CONFIRMACAO), (args.tag_imagem, VAR_TAG)):
        if valor is not None:
            ambiente[nome] = valor
    if args.aplicar:
        ambiente[VAR_APLICAR] = "true"
    if args.conectividade_privada_validada:
        ambiente[VAR_CONECTIVIDADE] = "true"
    if args.ingresso_externo:
        ambiente[VAR_INGRESSO_EXTERNO] = "true"


def _traduzir_erro(erro: Exception, args: argparse.Namespace) -> tuple[str, int]:
    return (f"Erro inesperado do script ({type(erro).__name__}). Nada foi alterado; o texto técnico foi omitido de propósito, "
            "porque pode conter dados do seu ambiente.", CODIGO_INESPERADO)


def principal(argv: list[str] | None = None, env: Mapping[str, str] | None = None) -> int:
    lab_comum.configurar_saida()
    if sys.version_info < (3, 12):
        print("[ERRO] Este script exige Python 3.12 ou superior.", file=sys.stderr)
        return CODIGO_USO
    ambiente = dict(os.environ if env is None else env)
    with _proteger_segredos(segredos_para_redigir(ambiente)):
        args = criar_parser().parse_args(argv)
        _aplicar_opcoes(args, ambiente)
        return lab_comum.executar_com_tratamento(lambda a: _ETAPAS[a.etapa](a, ambiente), args, tradutor=_traduzir_erro)


if __name__ == "__main__":
    sys.exit(principal())
