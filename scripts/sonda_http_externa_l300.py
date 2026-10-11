"""Provas HTTP EXTERNAS do chat do L300, feitas do computador de quem coordena (fora da imagem da sonda e fora da rede privada).

O chat tem ingresso externo, protegido pelo login da plataforma. Este helper confere, de fora, o que a sonda confere por dentro
(etapa http-interno de scripts/sonda_l300.py): quem não passou pelo login não entra, e quem entra recebe só o que o perfil permite.
Roda no mesmo processo que guarda o segredo efêmero. Tudo entra por variáveis de ambiente (ou por um mapeamento passado a
`principal`), nunca por arquivo nem por argumento de linha de comando. O segredo só existe em memória: não é gravado, registrado nem
emitido, e uma barreira final bloqueia a linha de resultado se ele (ou a URL, o tenant, um GUID, um IP ou um token) aparecer nela.
Reaproveita o formato, as barreiras e a lógica de conferência da sonda (scripts/sonda_l300.py).

Etapas (--etapa ou VARELEIRA_HTTP_ETAPA):
    sem-credenciais  só a URL (e, se houver, o tenant, para forjar o cabeçalho): /healthz e /readyz devem dar 200; a API sem token,
                     401; a API com um X-MS-CLIENT-PRINCIPAL inventado (papel de Atendimento), 401.
    perfil           token de ClientSecretCredential com escopo api://<loginAppId>/.default e UMA pergunta autenticada por execução,
                     conferida contra o perfil: atendimento, corretor e ambos, 200; sem-acesso, 403. O corretor não pode trazer o
                     documento operacional (VLAR-OP-ATD-1.0) nem o marcador interno; atendimento e ambos devem trazer o documento
                     operacional. Se a classificação do chat divergir, a divergência é reportada: nada é repetido nem ajustado.

Variáveis: VARELEIRA_HTTP_URL (https://<app>.<ambiente>.<região>.azurecontainerapps.io), VARELEIRA_HTTP_TENANT_ID,
VARELEIRA_HTTP_CLIENT_ID, VARELEIRA_HTTP_CLIENT_SECRET, VARELEIRA_HTTP_LOGIN_APP_ID, VARELEIRA_HTTP_PERFIL e VARELEIRA_HTTP_ETAPA.
O cliente (CLIENT_ID e CLIENT_SECRET) é um registro de aplicativo de teste, com o papel do perfil que se quer conferir; o
LOGIN_APP_ID é o registro de login do chat. São coisas diferentes, e nenhum valor fica no repositório.

Resultado: UMA linha `L300_SONDA_RESULTADO=<JSON>` no stdout (o mesmo formato da sonda, com etapa http-externo-sem-credenciais ou
http-externo-perfil) e o código de saída, que é sempre o da linha realmente emitida: 0 aprovado; 1 uso, configuração ou papéis do token
diferentes do perfil; 2 rede ou token (token_indisponivel traz o tipo do erro e codigo_entra: AADSTS#### achado na mensagem, em
memória, ou nao_identificado); 3 reprovado; 4 defeito (inclusive a linha `saida_bloqueada`, quando a barreira recusa a saída). Só HTTP,
tipo e situação do chat, contagens e presença do documento operacional e do marcador: nunca texto, IDs de pessoas, token ou URL.

Efeitos, custo e limpeza: sem-credenciais faz quatro requisições sem identidade, duas delas com uma pergunta que a plataforma deve
recusar com 401 (se não recusar, o chat pode processá-la, com consumo de embeddings e geração, e a etapa reprova). perfil faz UMA
pergunta autenticada por execução ao chat, que consome embeddings e uma geração. Nenhum recurso do Azure é criado, alterado nem removido. O segredo do
cliente de teste é seu: depois da prova, remova a variável da sessão (Remove-Item Env:VARELEIRA_HTTP_CLIENT_SECRET) e revogue a
credencial temporária, como o roteiro pede.

Exemplos (PowerShell, com o segredo só em memória, nunca em arquivo nem em argumento):
    $env:VARELEIRA_HTTP_URL = $url; $env:VARELEIRA_HTTP_ETAPA = 'sem-credenciais'; python scripts\\sonda_http_externa_l300.py
    $segredo = Read-Host -AsSecureString 'Segredo do cliente de teste'
    $env:VARELEIRA_HTTP_CLIENT_SECRET = [System.Net.NetworkCredential]::new('', $segredo).Password
    $env:VARELEIRA_HTTP_ETAPA = 'perfil'; python scripts\\sonda_http_externa_l300.py
    Remove-Item Env:VARELEIRA_HTTP_CLIENT_SECRET
Em Python: sonda_http_externa_l300.principal(["--etapa", "perfil"], ambiente={"VARELEIRA_HTTP_CLIENT_SECRET": segredo, ...}).
"""

from __future__ import annotations

import base64
import contextlib
import io
import json
import logging
import os
import re
import sys
import time
from typing import Any, Mapping, Sequence

import sonda_l300 as sonda

ETAPAS = ("sem-credenciais", "perfil")
_PADRAO_SEGREDO = re.compile(r"[\x21-\x7e]{8,256}")


def _segredo(valor: str) -> str:
    if not _PADRAO_SEGREDO.fullmatch(valor):
        raise ValueError
    return valor


_VARIAVEIS = (
    ("url", "VARELEIRA_HTTP_URL", sonda.url_do_aplicativo, None),
    ("tenant", "VARELEIRA_HTTP_TENANT_ID", lambda v: sonda.mod.lab_comum.validar_tenant(v), None),
    ("client_id", "VARELEIRA_HTTP_CLIENT_ID", lambda v: sonda.mod.lab_ingestao_l300.validar_client_id(v), None),
    ("segredo", "VARELEIRA_HTTP_CLIENT_SECRET", _segredo, None),
    ("login_app_id", "VARELEIRA_HTTP_LOGIN_APP_ID", lambda v: sonda.mod.lab_ingestao_l300.validar_client_id(v), None),
    ("perfil", "VARELEIRA_HTTP_PERFIL", sonda.escolha(lambda: tuple(sonda.ESPERADO_POR_PERFIL)), None),
    ("etapa", "VARELEIRA_HTTP_ETAPA", sonda.escolha(lambda: ETAPAS), None),
)
_CHAVES_PRIVADAS = ("url", "tenant", "client_id", "segredo", "login_app_id")


def criar_credencial(tenant: str, client_id: str, segredo: str) -> Any:
    """ClientSecretCredential do azure-identity. O segredo só passa por aqui, em memória."""
    return sonda.importar("azure.identity").ClientSecretCredential(tenant_id=tenant, client_id=client_id, client_secret=segredo)


_PADRAO_AADSTS = re.compile(r"AADSTS[0-9]{4,8}")


def codigo_entra(erro: BaseException) -> str:
    """O código AADSTS do Entra ID, achado em memória na mensagem do erro (e na das suas causas); senão, 'nao_identificado'.

    A mensagem em si (que traz GUIDs, IDs de rastreio e às vezes o nome do cliente) nunca é guardada, impressa nem emitida.
    """
    atual: BaseException | None = erro
    for _ in range(5):
        if atual is None:
            break
        try:
            achado = _PADRAO_AADSTS.search(str(atual))
        except Exception:  # noqa: BLE001 - um __str__ defeituoso não pode esconder a falha original
            achado = None
        if achado:
            return achado.group(0)
        atual = atual.__cause__ or atual.__context__
    return "nao_identificado"


def papeis_do_token(token: str) -> list[str] | None:
    """Os papéis do exercício na claim `roles`, lidos só em memória (a assinatura não é verificada aqui); None se não der para ler."""
    try:
        carga = token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(carga + "=" * (-len(carga) % 4)))
    except (IndexError, ValueError):
        return None
    papeis = claims.get("roles", []) if isinstance(claims, dict) else None
    if not isinstance(papeis, list):
        return None
    return [papel for papel in sonda.mod.lab_acesso.PAPEIS if papel in papeis]


def papeis_esperados(perfil: str) -> list[str]:
    acesso = sonda.mod.lab_acesso
    return {"atendimento": [acesso.PAPEL_ATENDIMENTO], "corretor": [acesso.PAPEL_CORRETOR],
            "ambos": [acesso.PAPEL_ATENDIMENTO, acesso.PAPEL_CORRETOR], "sem-acesso": []}[perfil]


def etapa_sem_credenciais(cfg: Any) -> Any:
    cfg.exigir("url", opcionais=("tenant",))
    estados = sonda.sondar_sem_credenciais(cfg.obter("url"), cfg.obter("tenant"))
    dados = {"estados": estados, "esperado": sonda.ESPERADO_SEM_CREDENCIAIS}
    falhas = sonda.falhas_sem_credenciais(estados)
    if falhas:
        raise sonda.ErroSonda(falhas[0], sonda.DIVERGENCIA, falhas=falhas, **dados)
    return sonda.Resultado("http-externo-sem-credenciais", sonda.OK, "aprovado", None, dados)


def etapa_perfil(cfg: Any) -> Any:
    cfg.exigir("url", "tenant", "client_id", "segredo", "login_app_id", "perfil")
    perfil = cfg.obter("perfil")
    try:
        credencial = criar_credencial(cfg.obter("tenant"), cfg.obter("client_id"), cfg.obter("segredo"))
        token = credencial.get_token(f"api://{cfg.obter('login_app_id')}/.default").token
    except sonda.ErroSonda:
        raise
    except Exception as erro:  # noqa: BLE001 - só o tipo e o código AADSTS interessam: o texto pode trazer identificadores
        raise sonda.ErroSonda("token_indisponivel", sonda.ACESSO, tipo=sonda.nome_fechado(type(erro).__name__),
                              codigo_entra=codigo_entra(erro)) from None
    del credencial
    papeis, esperados = papeis_do_token(token), papeis_esperados(perfil)
    if papeis is not None and papeis != esperados:
        raise sonda.ErroSonda("papeis_do_token_inesperados", sonda.USO, perfil=perfil, esperados=esperados, encontrados=papeis)
    cabecalhos = {"Content-Type": "application/json", "Accept": "application/json", "Authorization": f"Bearer {token}"}
    del token
    corpo = json.dumps({"pergunta": sonda.PERGUNTA_DO_CHAT}).encode("utf-8")
    estado, bruto = sonda.transporte_http("POST", f"{cfg.obter('url')}/api/perguntar", cabecalhos, corpo)
    del cabecalhos
    do_perfil, falhas = sonda.avaliar_resposta_do_perfil(perfil, estado, bruto)
    dados = {"perfil": perfil, "http": estado, "esperado": sonda.ESPERADO_POR_PERFIL[perfil], "papeis_no_token": papeis, **do_perfil}
    if falhas:
        raise sonda.ErroSonda(falhas[0], sonda.DIVERGENCIA, falhas=falhas, **dados)
    return sonda.Resultado("http-externo-perfil", sonda.OK, "aprovado", None, dados)


_ETAPAS = {"sem-credenciais": etapa_sem_credenciais, "perfil": etapa_perfil}


def _ler_argumentos(argv: Sequence[str] | None, ambiente: Mapping[str, str]) -> str:
    parser = sonda.ParserDaSonda(add_help=False, allow_abbrev=False)
    parser.add_argument("--etapa", choices=ETAPAS)
    args = parser.parse_args(None if argv is None else list(argv))
    da_variavel = (ambiente.get("VARELEIRA_HTTP_ETAPA") or "").strip() or None
    if da_variavel is not None and da_variavel not in ETAPAS:
        raise sonda.ErroSonda("etapa_desconhecida", sonda.USO)
    if args.etapa and da_variavel and args.etapa != da_variavel:
        raise sonda.ErroSonda("etapa_conflitante", sonda.USO)
    etapa = args.etapa or da_variavel
    if not etapa:
        raise sonda.ErroSonda("etapa_ausente", sonda.USO)
    return etapa


def principal(argv: Sequence[str] | None = None, ambiente: Mapping[str, str] | None = None, saida: Any = None) -> int:
    ambiente = os.environ if ambiente is None else ambiente
    emissor = sonda.Emissor(saida if saida is not None else sys.stdout)
    inicio = time.monotonic()
    etapa: str | None = None
    privados: tuple[str, ...] = ()
    logging.disable(logging.CRITICAL)
    try:
        # Nada além da linha sentinela chega ao stdout ou ao stderr, nem por bibliotecas.
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            try:
                etapa = _ler_argumentos(argv, ambiente)
                cfg = sonda.Configuracao(ambiente, _VARIAVEIS, _CHAVES_PRIVADAS)
                privados = cfg.privados()
                resultado = _ETAPAS[etapa](cfg)
            except Exception as erro:  # noqa: BLE001 - qualquer falha vira uma linha sentinela; Ctrl+C continua valendo
                falha = sonda.classificar_excecao(erro)
                resultado = sonda.Resultado(f"http-externo-{etapa}" if etapa else None, falha.codigo, falha.veredicto,
                                            falha.causa, falha.dados)
    finally:
        logging.disable(logging.NOTSET)
    resultado.duracao_s = round(time.monotonic() - inicio, 1)
    emissor.emitir(resultado, privados)
    return emissor.codigo  # o da linha realmente emitida: se a barreira a trocou, 4


if __name__ == "__main__":
    sys.exit(principal())
