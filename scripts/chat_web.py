"""Servidor HTTP do chat do L200: a interface web e a API de uma pergunta por requisição, sem memória entre elas.

Rotas: GET /healthz (vivo, sem Azure), GET /readyz (configuração e serviço prontos, sem chamar o Azure), GET / e
GET /static/<arquivo> (interface) e POST /api/perguntar (JSON com a pergunta atual). Tudo, exceto /healthz e /readyz, exige
a identidade entregue pela autenticação integrada do Azure Container Apps quando VARELEIRA_EXIGIR_AUTENTICACAO=true. Essa
identidade vem em um cabeçalho sem assinatura: ela só vale se todo o tráfego chega pelo ingresso com a autenticação exigida.

O modo padrão é o da nuvem: a configuração vem de variáveis de ambiente (veja lab_chat.py), a autenticação é obrigatória e
a falta de qualquer valor impede a partida. --demo (respostas simuladas, sem Azure) e --local-sem-autenticacao (Azure com a
sua sessão do Azure CLI) só aceitam 127.0.0.1, ::1 ou localhost.

Acesso documental (L300): com VARELEIRA_EXIGIR_ACESSO_DOCUMENTAL=true, os papéis de aplicação da identidade autenticada (claims
`roles` do X-MS-CLIENT-PRINCIPAL) definem, por requisição, quais classes de documento a busca pode devolver. Uma identidade sem
papel reconhecido recebe 403 antes de qualquer busca, embedding ou chamada ao modelo, e o JSON e a query da pergunta não aceitam
papéis, filtro, índice, tenant nem usuário. A opção não combina com --demo nem com --local-sem-autenticacao.

Coordenação (L400): com VARELEIRA_EXIGIR_COORDENACAO=true, POST /api/perguntar usa o serviço coordenado (mesmo JSON de resposta) e existe
POST /api/perguntar/progresso, com a mesma validação e autenticação, que devolve eventos de etapa (text/event-stream) e, só depois da
política, a resposta. Cada requisição tem o próprio sinal de cancelamento: o navegador que aborta ou desconecta impede as próximas etapas
daquela consulta, e só dela. Um pedido ao modelo já enviado pode terminar e consumir tokens. Sem a opção, as rotas não existem (404).

A desconexão pode não chegar ao servidor a tempo pela borda da plataforma (o ingresso do Azure Container Apps pode manter aberta a conexão
com o servidor). Por isso existe também POST /api/perguntar/cancelar, com {"id_requisicao": "<X-Request-Id da resposta do fluxo>"}: a
mesma identidade autenticada, com papel reconhecido, cancela a própria consulta em andamento (a resposta é 202; o fluxo termina com o
evento `erro` `cancelado`). Outra identidade, uma consulta que já terminou e um identificador desconhecido recebem o mesmo 404, e
identificador ausente ou malformado recebe 422. O registro dessas consultas fica na memória do processo, só enquanto rodam, e guarda
apenas o sinal de cancelamento, uma chave (HMAC) de quem as iniciou e a validade: nunca pergunta, resposta, tenant nem OID. Com mais de
uma réplica, o cancelamento só chega se o pedido cair na réplica da consulta. Antes de o navegador receber o X-Request-Id (a resposta
do fluxo), só é possível abortar a conexão no próprio navegador, sem avisar o servidor.

Exemplos:
    python scripts\\chat_web.py --host 127.0.0.1 --port 8000 --demo
    python scripts\\chat_web.py --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import hmac
import json
import logging
import os
import secrets
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Mapping

import lab_acesso
import lab_chat
import lab_comum
from lab_comum import ErroLab

try:
    import uvicorn
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse, Response, StreamingResponse
    from starlette.exceptions import HTTPException as ErroHttp
except ImportError:  # requirements/l200.txt ainda não foi instalado: create_app e principal explicam
    uvicorn = FastAPI = Request = JSONResponse = Response = StreamingResponse = ErroHttp = None  # type: ignore[assignment,misc]

PASTA_WEB = lab_comum.RAIZ / "web"
ARQUIVOS_DA_INTERFACE = ("index.html", "app.js", "style.css")
ARQUIVOS_ESTATICOS = {"app.js": "text/javascript; charset=utf-8", "style.css": "text/css; charset=utf-8"}
ROTAS_ISENTAS = frozenset({"/healthz", "/readyz"})  # as únicas sem autenticação: não leem nem devolvem dados
ROTA_PERGUNTAR = "/api/perguntar"
ROTA_PROGRESSO = "/api/perguntar/progresso"  # só com a coordenação (L400)
ROTA_CANCELAR = "/api/perguntar/cancelar"  # só com a coordenação (L400): cancelamento explícito de uma consulta em andamento
LIMITE_DO_CORPO_DO_CANCELAMENTO = 1024  # bytes: só o identificador da consulta
VALIDADE_EXTRA_DO_REGISTRO = 5.0  # segundos além do tempo máximo de uma consulta, só uma rede de proteção
PORTA_PADRAO = 8000
LIMITE_DE_CONEXOES = 64
TEMPO_DE_ESPERA_AO_ENCERRAR = 20  # segundos
TAMANHO_DOS_CABECALHOS = 64 * 1024  # o cabeçalho de identidade pode listar muitos grupos
ESPERA_SUGERIDA = 2  # segundos, na resposta 429
BIBLIOTECAS_QUE_NAO_REGISTRAM = ("azure", "openai", "httpx", "httpx2", "httpcore", "httpcore2", "msal", "agent_framework")

MENSAGEM_SEM_WEB = ("Bibliotecas do chat não encontradas. Ative o ambiente virtual e execute: "
                    "python -m pip install -r requirements/l200.txt")

STATUS_HTTP = {
    lab_chat.NAO_AUTENTICADO: 401,
    lab_chat.NAO_AUTORIZADO: 403,
    lab_chat.HOST_INVALIDO: 400,
    lab_chat.NAO_ENCONTRADO: 404,
    lab_chat.METODO_NAO_PERMITIDO: 405,
    lab_chat.PEDIDO_GRANDE: 413,
    lab_chat.TIPO_DE_CONTEUDO_INVALIDO: 422,
    lab_chat.JSON_INVALIDO: 422,
    lab_chat.CAMPOS_NAO_PERMITIDOS: 422,
    lab_chat.PERGUNTA_INVALIDA: 422,
    lab_chat.PERGUNTA_VAZIA: 422,
    lab_chat.PERGUNTA_LONGA: 422,
    lab_chat.PERGUNTA_BLOQUEADA: 422,
    lab_chat.ID_INVALIDO: 422,
    lab_chat.OCUPADO: 429,
    lab_chat.ERRO_INTERNO: 500,
    lab_chat.INDISPONIVEL: 503,
    lab_chat.RESPOSTA_NAO_VERIFICADA: 503,
    lab_chat.NAO_PRONTO: 503,
    lab_chat.CANCELADO: 499,  # L400: o cliente cancelou; quase nunca há quem leia a resposta
    lab_chat.EXECUCAO_NAO_ENCONTRADA: 404,  # L400: cancelamento explícito sem consulta em andamento desta conta
    lab_chat.ID_DA_EXECUCAO_INVALIDO: 422,
}

# A página só carrega scripts e estilos do próprio servidor, só conversa com ele e não pode ser colocada em um quadro.
CABECALHOS_DE_SEGURANCA = {
    "Content-Security-Policy": ("default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; "
                                "base-uri 'none'; form-action 'none'; frame-ancestors 'none'"),
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}

LOG = logging.getLogger("vareleira.chat")
LOG.addHandler(logging.NullHandler())  # a biblioteca não imprime sozinha: quem inicia o servidor configura o registro


class ExecucoesAtivas:
    """As consultas coordenadas em andamento (L400), só para o cancelamento explícito por quem as iniciou.

    O cancelamento por desconexão pode não chegar ao servidor pela borda da plataforma, então o navegador pede o cancelamento por uma
    rota autenticada, com o X-Request-Id da consulta. Cada item guarda só o sinal de cancelamento, a chave de quem iniciou a consulta
    (um HMAC com um segredo que só existe neste processo: nunca o tenant nem o OID) e a validade; nada da pergunta, da resposta nem dos
    documentos. O item sai quando a consulta termina, é cancelada ou vence a validade, e o registro nunca passa do número de vagas de
    concorrência: só entra quem já passou pela admissão. Fica na memória deste processo, sem Redis nem banco: com mais de uma réplica,
    o cancelamento só chega se o pedido cair na réplica da consulta.
    """

    def __init__(self, limite: int, validade_s: float, relogio: Callable[[], float] = time.monotonic):
        self._trava = threading.Lock()
        self._itens: dict[str, tuple[bytes, threading.Event, float]] = {}
        self._limite, self._validade_s, self._relogio = limite, validade_s, relogio

    def _expurgar(self) -> None:  # quem chama já tem a trava
        agora = self._relogio()
        for id_requisicao in [chave for chave, (_, _, vence) in self._itens.items() if vence <= agora]:
            del self._itens[id_requisicao]

    def abrir(self, id_requisicao: str, ator: bytes, cancelar: threading.Event) -> None:
        with self._trava:
            self._expurgar()
            if id_requisicao in self._itens:
                raise lab_chat.ErroChat(lab_chat.ERRO_INTERNO, "id_duplicado")
            if len(self._itens) >= self._limite:
                raise lab_chat.ErroChat(lab_chat.OCUPADO, "registro_cheio")
            self._itens[id_requisicao] = (ator, cancelar, self._relogio() + self._validade_s)

    def cancelar(self, id_requisicao: str, ator: bytes) -> bool:
        """Dá o sinal de cancelamento se a consulta existe e é de quem pede. Quem não é o dono recebe o mesmo `False` de uma consulta
        que não existe: o identificador não revela de quem é nem se existe."""
        with self._trava:
            self._expurgar()
            item = self._itens.get(id_requisicao)
            if item is None or not hmac.compare_digest(item[0], ator):
                return False
            del self._itens[id_requisicao]
            item[1].set()
            return True

    def fechar(self, id_requisicao: str) -> None:
        with self._trava:
            self._itens.pop(id_requisicao, None)

    def __len__(self) -> int:
        with self._trava:
            return len(self._itens)


def chave_do_ator(segredo: bytes, principal: lab_chat.Principal) -> bytes:
    """Quem fez a requisição, sem guardar o tenant nem o OID: um HMAC (tenant e sujeito já validados pela autenticação integrada)."""
    return hmac.new(segredo, f"{principal.tenant}\x1f{principal.sujeito}".encode("utf-8"), hashlib.sha256).digest()


@dataclass
class Estado:
    """O que existe depois da partida. Não há dados de usuário aqui: só a configuração, o serviço e o controle de carga."""

    configuracao: lab_chat.ConfiguracaoChat
    servico: lab_chat.ServicoChat
    executor: ThreadPoolExecutor
    capacidade: threading.BoundedSemaphore
    arquivos: dict[str, bytes]
    execucoes: ExecucoesAtivas | None = None  # só com a coordenação (L400)


def exigir_web() -> None:
    if FastAPI is None:
        raise ErroLab(MENSAGEM_SEM_WEB)


def rotular_rota(caminho: str) -> str:
    """Rótulo de um vocabulário fechado para o registro: o endereço pedido nunca é gravado."""
    if caminho == "/healthz":
        return "saude"
    if caminho == "/readyz":
        return "prontidao"
    if caminho == "/api/perguntar":
        return "perguntar"
    if caminho == ROTA_PROGRESSO:
        return "progresso"
    if caminho == ROTA_CANCELAR:
        return "cancelar"
    if caminho == "/":
        return "interface"
    return "estatico" if caminho.startswith("/static/") else "outra"


def carregar_arquivos(pasta: Path, configuracao: lab_chat.ConfiguracaoChat) -> dict[str, bytes]:
    """Lê a interface na partida: uma instalação incompleta falha cedo, e a página já recebe o modo e o limite da pergunta."""
    arquivos: dict[str, bytes] = {}
    for nome in ARQUIVOS_DA_INTERFACE:
        try:
            arquivos[nome] = (pasta / nome).read_bytes()
        except OSError:
            raise ErroLab(f"Arquivo da interface não encontrado: web/{nome}. Use uma cópia completa do projeto.") from None
    pagina = arquivos["index.html"].decode("utf-8")
    pagina = pagina.replace("{{MODO}}", configuracao.modo).replace("{{LIMITE_PERGUNTA}}", str(lab_chat.LIMITE_DA_PERGUNTA))
    pagina = pagina.replace("{{COORDENACAO}}", "sim" if configuracao.exigir_coordenacao else "nao")
    arquivos["index.html"] = pagina.encode("utf-8")
    return arquivos


def resposta_de_erro(codigo: str, id_requisicao: str, cabecalhos: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse({"erro": codigo, "mensagem": lab_chat.MENSAGENS[codigo], "id_requisicao": id_requisicao},
                        status_code=STATUS_HTTP[codigo], headers=cabecalhos)


def responder_erro(request: Request, erro: lab_chat.ErroChat) -> JSONResponse:
    request.state.causa = erro.causa
    espera = {"Retry-After": str(ESPERA_SUGERIDA)} if erro.codigo == lab_chat.OCUPADO else None
    return resposta_de_erro(erro.codigo, request.state.id_requisicao, espera)


async def ler_corpo(request: Request, limite: int) -> bytes:
    """Lê no máximo `limite` bytes, mesmo sem Content-Length ou com um valor falso."""
    declarado = request.headers.get("content-length", "")
    if declarado.isascii() and declarado.isdigit() and int(declarado) > limite:
        raise lab_chat.ErroChat(lab_chat.PEDIDO_GRANDE)
    corpo = bytearray()
    async for parte in request.stream():
        corpo.extend(parte)
        if len(corpo) > limite:
            raise lab_chat.ErroChat(lab_chat.PEDIDO_GRANDE)
    return bytes(corpo)


async def consultar(estado: Estado, pergunta: str, acesso: lab_acesso.ContextoAcesso | None = None, *,
                    cancelar: threading.Event | None = None,
                    progresso: Callable[[Any], None] | None = None) -> lab_chat.RespostaChat:
    """Executa a consulta (síncrona) em uma thread, com concorrência limitada e tempo máximo.

    Sem vaga, responde logo com 429 em vez de enfileirar. A vaga só volta quando a thread termina, mesmo que a requisição
    já tenha expirado: assim o número de consultas em andamento nunca passa do limite. O contexto de acesso (L300) pertence a
    esta requisição e só chega ao serviço como argumento da chamada: nada dele fica no estado compartilhado.

    Com a coordenação (L400), `cancelar` (um sinal por requisição) e `progresso` seguem para o serviço coordenado, que não começa
    uma etapa nova depois do sinal. Quando o tempo acaba ou a requisição é cancelada aqui, o sinal é dado: a thread termina na
    próxima conferência do serviço, não fica rodando por conta própria.
    """
    if not estado.capacidade.acquire(blocking=False):
        raise lab_chat.ErroChat(lab_chat.OCUPADO)

    def trabalho() -> lab_chat.RespostaChat:
        try:
            if cancelar is not None or progresso is not None:  # só o serviço coordenado aceita os dois
                return estado.servico.perguntar(pergunta, acesso, cancelar=cancelar, progresso=progresso)
            if acesso is None:
                return estado.servico.perguntar(pergunta)
            return estado.servico.perguntar(pergunta, acesso)
        finally:
            estado.capacidade.release()

    try:
        futuro = asyncio.get_running_loop().run_in_executor(estado.executor, trabalho)
    except BaseException:
        estado.capacidade.release()
        raise
    try:
        return await asyncio.wait_for(futuro, timeout=estado.configuracao.timeout_segundos)
    except TimeoutError:
        if cancelar is not None:
            cancelar.set()
        raise lab_chat.ErroChat(lab_chat.INDISPONIVEL, "tempo_esgotado") from None
    except asyncio.CancelledError:  # o servidor desistiu desta requisição (cliente desconectado)
        if cancelar is not None:
            cancelar.set()
        raise


async def vigiar_conexao(request: Request, cancelar: threading.Event, encerrada: asyncio.Event) -> None:
    """Dá o sinal de cancelamento desta requisição se o cliente desconectar. Não toca nas consultas de outras pessoas.

    Depois do corpo, a próxima mensagem do servidor para esta requisição é a desconexão: a vigia só espera por ela (sem consultar
    de tempos em tempos) e termina quando `encerrada` é acionado. `Request.is_disconnected()` não serve aqui: por trás do
    middleware HTTP do Starlette ele não enxerga a desconexão, e cancelar a tarefa por fora dele pode ser engolido pelo AnyIO.
    """
    espera = asyncio.ensure_future(request.receive())
    fim = asyncio.ensure_future(encerrada.wait())
    try:
        await asyncio.wait({espera, fim}, return_when=asyncio.FIRST_COMPLETED)
        if espera.done() and not espera.cancelled() and espera.exception() is None and not encerrada.is_set():
            if espera.result().get("type") == "http.disconnect":
                cancelar.set()
    except Exception:  # noqa: BLE001 - a vigia é complementar: sem ela, o prazo da consulta continua valendo
        return
    finally:
        for tarefa in (espera, fim):
            tarefa.cancel()
        await asyncio.wait({espera, fim}, timeout=1.0)


def guardar_resumo(destino: dict[str, Any]) -> Callable[[Any], None]:
    """Um acompanhante que só guarda o resumo (contagens) que o serviço coordenado informa no fim da execução."""
    def guardar(evento: Any) -> None:
        if getattr(evento, "tipo", None) == "resumo":
            destino.update(evento.a_dict()["dados"])

    return guardar


def registrar_coordenacao(id_requisicao: str, resultado: str, resumo: Mapping[str, Any]) -> None:
    """Uma linha por consulta coordenada, só com vocabulário fechado e contagens (sem pergunta, trecho, resposta ou identidade)."""
    LOG.info("coordenacao id=%s resultado=%s chamadas=%d buscas=%d contingencia=%s uso_incerto=%s", id_requisicao, resultado,
             int(resumo.get("chamadas_total", 0)), int(resumo.get("buscas", 0)), "sim" if resumo.get("contingencia") else "nao",
             "nao" if resumo.get("uso_incerto") is False else "sim")


def evento_sse(nome: str, dados: Mapping[str, Any]) -> bytes:
    """Um evento do fluxo de progresso. O nome vem de um vocabulário fechado e o JSON nunca tem quebra de linha."""
    return f"event: {nome}\ndata: {json.dumps(dados, ensure_ascii=False, separators=(',', ':'))}\n\n".encode("utf-8")


def envelope_de_erro(erro: lab_chat.ErroChat, id_requisicao: str) -> dict[str, str]:
    return {"erro": erro.codigo, "mensagem": lab_chat.MENSAGENS[erro.codigo], "id_requisicao": id_requisicao}


def abrir_fluxo(estado: Estado, pedido: lab_chat.PedidoChat, acesso: lab_acesso.ContextoAcesso, id_requisicao: str,
                ator: bytes) -> AsyncIterator[bytes]:
    """O fluxo de eventos de uma consulta coordenada. Sem vaga, levanta OCUPADO antes de a resposta começar (429).

    A consulta roda em uma thread do executor e entrega os eventos por uma fila desta requisição. O texto da resposta só sai no
    evento `resposta`, depois da política; antes dele só há eventos de etapa e de tentativa com contagens. Se o navegador
    desconecta ou o tempo acaba, o sinal de cancelamento desta requisição é dado e nenhuma etapa nova começa.

    Enquanto a consulta roda, ela fica em `estado.execucoes` com a chave de quem a iniciou: é isso que deixa a mesma identidade
    cancelá-la por ROTA_CANCELAR, já que a desconexão pode não chegar até aqui pela borda da plataforma.
    """
    execucoes = estado.execucoes
    if execucoes is None:
        raise lab_chat.ErroChat(lab_chat.NAO_PRONTO)
    if not estado.capacidade.acquire(blocking=False):
        raise lab_chat.ErroChat(lab_chat.OCUPADO)
    laco = asyncio.get_running_loop()
    fila: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()
    cancelar = threading.Event()
    try:
        execucoes.abrir(id_requisicao, ator, cancelar)
    except BaseException:
        estado.capacidade.release()
        raise

    def entregar(item: tuple[str, Any]) -> None:
        try:
            laco.call_soon_threadsafe(fila.put_nowait, item)
        except RuntimeError:  # o servidor já encerrou o laço de eventos
            pass

    def trabalho() -> None:
        try:
            resultado: tuple[str, Any] = ("resposta", estado.servico.perguntar(
                pedido.pergunta, acesso, cancelar=cancelar, progresso=lambda evento: entregar(("evento", evento))))
        except BaseException as erro:  # noqa: BLE001 - toda falha vira um evento `erro` com código público
            resultado = ("falha", erro)
        finally:
            execucoes.fechar(id_requisicao)  # a consulta terminou: não há mais o que cancelar
            estado.capacidade.release()
        entregar(resultado)

    try:
        laco.run_in_executor(estado.executor, trabalho)
    except BaseException:
        execucoes.fechar(id_requisicao)
        estado.capacidade.release()
        raise

    async def corpo() -> AsyncIterator[bytes]:
        resultado, resumo = "cancelado", {}
        prazo = time.monotonic() + estado.configuracao.timeout_segundos
        try:
            while True:
                try:
                    tipo, valor = await asyncio.wait_for(fila.get(), timeout=max(prazo - time.monotonic(), 0.0))
                except TimeoutError:
                    tipo, valor = "falha", lab_chat.ErroChat(lab_chat.INDISPONIVEL, "tempo_esgotado")
                if tipo == "evento":
                    dados = valor.a_dict()
                    if dados.get("tipo") == "resumo":
                        resumo = dados["dados"]
                    yield evento_sse(dados["tipo"], dados)
                elif tipo == "resposta":
                    resultado = "concluido"
                    yield evento_sse("resposta", {"id": pedido.id_cliente, "id_requisicao": id_requisicao, **valor.a_dict()})
                    yield evento_sse("fim", {"estado": "concluida"})
                    return
                else:
                    erro = lab_chat.classificar_erro(valor)
                    resultado = "cancelado" if erro.codigo == lab_chat.CANCELADO else "erro"
                    yield evento_sse("erro", envelope_de_erro(erro, id_requisicao))
                    yield evento_sse("fim", {"estado": "cancelada" if resultado == "cancelado" else "falhou"})
                    return
        finally:
            cancelar.set()  # desconexão, tempo ou fim: nenhuma etapa nova começa para esta requisição (e só para ela)
            execucoes.fechar(id_requisicao)
            registrar_coordenacao(id_requisicao, resultado, resumo)

    return corpo()


def create_app(configuracao: lab_chat.ConfiguracaoChat,
               fabrica_servico: Callable[[lab_chat.ConfiguracaoChat], lab_chat.ServicoChat] | None = None,
               pasta_web: Path = PASTA_WEB) -> FastAPI:
    """Monta a aplicação sem ler o ambiente nem acessar o Azure: a validação e a criação do serviço ocorrem na partida.

    `fabrica_servico` cria o serviço na partida (por padrão, o do modo da configuração); os testes entregam uma fábrica
    com dublês. Nada é compartilhado entre pessoas além da configuração e dos clientes do Azure, que não guardam estado de usuário.
    """
    exigir_web()
    fabrica = fabrica_servico or lab_chat.criar_servico

    @asynccontextmanager
    async def ciclo_de_vida(app: FastAPI):
        lab_chat.validar_configuracao(configuracao)
        arquivos = carregar_arquivos(pasta_web, configuracao)
        servico = fabrica(configuracao)
        if configuracao.exigir_acesso_documental and getattr(servico, "exige_acesso", False) is not True:
            raise ErroLab("O serviço do chat não aplica o filtro de acesso documental: com a opção ativa, o chat não inicia assim.",
                          lab_comum.CODIGO_USO)
        if configuracao.exigir_coordenacao and getattr(servico, "coordenado", False) is not True:
            raise ErroLab("O serviço do chat não é o coordenado (L400): com a opção ativa, o chat não inicia assim.",
                          lab_comum.CODIGO_USO)
        executor = ThreadPoolExecutor(max_workers=configuracao.max_concorrencia, thread_name_prefix="chat")
        execucoes = (ExecucoesAtivas(configuracao.max_concorrencia, configuracao.timeout_segundos + VALIDADE_EXTRA_DO_REGISTRO)
                     if configuracao.exigir_coordenacao else None)
        app.state.chat = Estado(configuracao, servico, executor, threading.BoundedSemaphore(configuracao.max_concorrencia), arquivos,
                                execucoes)
        LOG.info("assistente pronto %s", lab_chat.resumo_publico(configuracao))
        try:
            yield
        finally:
            app.state.chat = None
            executor.shutdown(wait=False, cancel_futures=True)

    app = FastAPI(title="Assistente do Vareleira Lar", lifespan=ciclo_de_vida, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.chat = None
    segredo_dos_atores = secrets.token_bytes(32)  # só existe neste processo: a chave de quem inicia uma consulta não se repete fora dele

    @app.middleware("http")
    async def proteger_e_registrar(request: Request, call_next):
        inicio = time.perf_counter()
        id_requisicao = uuid.uuid4().hex
        request.state.id_requisicao = id_requisicao
        request.state.causa = None
        request.state.acesso = None
        request.state.ator = None
        try:
            erro_de_acesso = None
            if not lab_chat.host_permitido(configuracao.modo, request.headers.get("host")):
                erro_de_acesso = lab_chat.ErroChat(lab_chat.HOST_INVALIDO)
            elif configuracao.exigir_autenticacao and request.url.path not in ROTAS_ISENTAS:
                try:
                    principal = lab_chat.validar_principal(request.headers.get(lab_chat.CABECALHO_PRINCIPAL),
                                                           configuracao.tenants_autorizados)
                    if configuracao.exigir_acesso_documental:
                        request.state.acesso = lab_chat.contexto_de_acesso(principal)  # sem papel reconhecido: 403 aqui
                    if configuracao.exigir_coordenacao:
                        request.state.ator = chave_do_ator(segredo_dos_atores, principal)
                except lab_chat.ErroChat as erro:
                    erro_de_acesso = erro
            resposta = responder_erro(request, erro_de_acesso) if erro_de_acesso else await call_next(request)
        except Exception:  # noqa: BLE001 - o texto do erro pode ter dados internos: só a causa curta vai para o registro
            resposta = responder_erro(request, lab_chat.ErroChat(lab_chat.ERRO_INTERNO, "inesperado"))
        resposta.headers["X-Request-Id"] = id_requisicao
        for nome, valor in CABECALHOS_DE_SEGURANCA.items():
            resposta.headers[nome] = valor
        causa = f" causa={request.state.causa}" if request.state.causa else ""
        LOG.log(logging.WARNING if resposta.status_code >= 500 else logging.INFO, "requisicao id=%s rota=%s status=%d ms=%d%s",
                id_requisicao, rotular_rota(request.url.path), resposta.status_code,
                round((time.perf_counter() - inicio) * 1000), causa)
        return resposta

    @app.exception_handler(ErroHttp)
    async def erro_http(request: Request, erro: ErroHttp):
        codigos = {404: lab_chat.NAO_ENCONTRADO, 405: lab_chat.METODO_NAO_PERMITIDO}
        codigo = codigos.get(erro.status_code, lab_chat.JSON_INVALIDO if erro.status_code < 500 else lab_chat.ERRO_INTERNO)
        request.state.causa = codigo
        return resposta_de_erro(codigo, request.state.id_requisicao, dict(erro.headers or {}))

    @app.get("/healthz")
    async def vivo():
        return JSONResponse({"situacao": "ok"})

    @app.get("/readyz")
    async def pronto(request: Request):
        estado = request.app.state.chat
        if estado is None:
            return responder_erro(request, lab_chat.ErroChat(lab_chat.NAO_PRONTO))
        return JSONResponse({"situacao": "pronto", "modo": estado.configuracao.modo})

    @app.get("/")
    async def interface(request: Request):
        estado = request.app.state.chat
        if estado is None:
            return responder_erro(request, lab_chat.ErroChat(lab_chat.NAO_PRONTO))
        return Response(estado.arquivos["index.html"], media_type="text/html; charset=utf-8")

    @app.get("/static/{nome}")
    async def estatico(nome: str, request: Request):
        estado = request.app.state.chat
        if estado is None:
            return responder_erro(request, lab_chat.ErroChat(lab_chat.NAO_PRONTO))
        if nome not in ARQUIVOS_ESTATICOS:
            return responder_erro(request, lab_chat.ErroChat(lab_chat.NAO_ENCONTRADO))
        return Response(estado.arquivos[nome], media_type=ARQUIVOS_ESTATICOS[nome])

    @app.post(ROTA_PERGUNTAR)
    async def perguntar(request: Request):
        coordenado, resumo, resultado = False, {}, "erro"
        try:
            estado = request.app.state.chat
            if estado is None:
                raise lab_chat.ErroChat(lab_chat.NAO_PRONTO)
            if request.url.query:
                raise lab_chat.ErroChat(lab_chat.CAMPOS_NAO_PERMITIDOS)
            acesso = request.state.acesso if estado.configuracao.exigir_acesso_documental else None
            if estado.configuracao.exigir_acesso_documental and acesso is None:
                raise lab_chat.ErroChat(lab_chat.NAO_AUTORIZADO, "sem_papel_conhecido")
            corpo = await ler_corpo(request, lab_chat.LIMITE_DO_CORPO)
            pedido = lab_chat.ler_pedido(corpo, request.headers.get("content-type"))
            coordenado = estado.configuracao.exigir_coordenacao
            if coordenado:  # L400: um sinal de cancelamento por requisição, dado se o cliente desconectar
                cancelar, encerrada = threading.Event(), asyncio.Event()
                vigia = asyncio.ensure_future(vigiar_conexao(request, cancelar, encerrada))
                try:
                    resposta = await consultar(estado, pedido.pergunta, acesso, cancelar=cancelar, progresso=guardar_resumo(resumo))
                finally:
                    encerrada.set()
                    await asyncio.wait({vigia}, timeout=2.0)
                    if not vigia.done():  # não deveria acontecer: a vigia sai assim que `encerrada` é acionado
                        vigia.cancel()
            else:
                resposta = await consultar(estado, pedido.pergunta, acesso)
            resultado = "concluido"
        except asyncio.CancelledError:  # o servidor desistiu da requisição: o sinal de cancelamento já foi dado em `consultar`
            resultado = "cancelado"
            raise
        except Exception as erro:  # noqa: BLE001 - toda falha vira um código público; o texto da exceção não sai daqui
            publico = lab_chat.classificar_erro(erro)
            resultado = "cancelado" if publico.codigo == lab_chat.CANCELADO else "erro"
            return responder_erro(request, publico)
        finally:
            if coordenado:
                registrar_coordenacao(request.state.id_requisicao, resultado, resumo)
        return JSONResponse({"id": pedido.id_cliente, "id_requisicao": request.state.id_requisicao, **resposta.a_dict()})

    if configuracao.exigir_coordenacao:
        @app.post(ROTA_PROGRESSO)
        async def perguntar_com_progresso(request: Request):
            try:
                estado = request.app.state.chat
                if estado is None:
                    raise lab_chat.ErroChat(lab_chat.NAO_PRONTO)
                if request.url.query:
                    raise lab_chat.ErroChat(lab_chat.CAMPOS_NAO_PERMITIDOS)
                acesso, ator = request.state.acesso, request.state.ator
                if acesso is None or ator is None:
                    raise lab_chat.ErroChat(lab_chat.NAO_AUTORIZADO, "sem_papel_conhecido")
                corpo = await ler_corpo(request, lab_chat.LIMITE_DO_CORPO)
                pedido = lab_chat.ler_pedido(corpo, request.headers.get("content-type"))
                fluxo = abrir_fluxo(estado, pedido, acesso, request.state.id_requisicao, ator)
            except Exception as erro:  # noqa: BLE001 - antes do fluxo, uma falha ainda é uma resposta JSON comum
                return responder_erro(request, lab_chat.classificar_erro(erro))
            return StreamingResponse(fluxo, media_type="text/event-stream", headers={"X-Accel-Buffering": "no"})

        @app.post(ROTA_CANCELAR)
        async def cancelar_execucao(request: Request):
            """Cancela uma consulta em andamento da própria identidade. A mesma autenticação e o mesmo papel das outras rotas valem
            (sem papel, 403 antes de qualquer consulta); o JSON só traz o X-Request-Id, e quem pede é sempre a identidade da requisição."""
            try:
                estado = request.app.state.chat
                if estado is None or estado.execucoes is None:
                    raise lab_chat.ErroChat(lab_chat.NAO_PRONTO)
                if request.url.query:
                    raise lab_chat.ErroChat(lab_chat.CAMPOS_NAO_PERMITIDOS)
                if request.state.acesso is None or request.state.ator is None:
                    raise lab_chat.ErroChat(lab_chat.NAO_AUTORIZADO, "sem_papel_conhecido")
                corpo = await ler_corpo(request, LIMITE_DO_CORPO_DO_CANCELAMENTO)
                alvo = lab_chat.ler_pedido_de_cancelamento(corpo, request.headers.get("content-type"))
                if not estado.execucoes.cancelar(alvo, request.state.ator):
                    raise lab_chat.ErroChat(lab_chat.EXECUCAO_NAO_ENCONTRADA)
            except Exception as erro:  # noqa: BLE001 - só o código público e a causa curta saem daqui
                return responder_erro(request, lab_chat.classificar_erro(erro))
            return JSONResponse({"estado": "cancelamento_solicitado", "alvo": alvo}, status_code=202)

    return app


# --------------------------------------------------------------------------------------
# Linha de comando
# --------------------------------------------------------------------------------------

def validar_porta(valor: str) -> int:
    try:
        porta = int(valor)
    except ValueError:
        porta = 0
    if not 1 <= porta <= 65535:
        raise argparse.ArgumentTypeError(f"A porta deve ser um número de 1 a 65535 (recebido: {valor!r}).")
    return porta


def configurar_registro() -> None:
    """Registro só com id, rota, status e tempo. As bibliotecas do Azure ficam em silêncio: seus avisos trazem endereços."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s", stream=sys.stderr)
    for nome in BIBLIOTECAS_QUE_NAO_REGISTRAM:
        logging.getLogger(nome).setLevel(logging.CRITICAL)


def mostrar_inicio(configuracao: lab_chat.ConfiguracaoChat, porta: int) -> None:
    descricoes = {
        lab_chat.MODO_DEMO: "modo de demonstração: as respostas são simuladas e não consultam o Azure.",
        lab_chat.MODO_LOCAL: "modo local sem autenticação, acessível só neste computador, com a sua sessão do Azure CLI.",
        lab_chat.MODO_NUVEM: "autenticação exigida: a identidade do Azure Container Apps é conferida contra o tenant autorizado.",
    }
    print(f"Chat do Vareleira Lar, {descricoes[configuracao.modo]}")
    if configuracao.exigir_acesso_documental:
        print("Acesso documental ativo: os papéis de aplicação da identidade definem as classes de documento da busca, "
              "e quem não tem papel reconhecido recebe 403 antes de qualquer consulta.")
    if configuracao.exigir_coordenacao:
        print("Coordenação L400 ativa: planejamento, recuperação filtrada, verificação e redação com limites finitos; "
              f"contingência de geração {'configurada' if configuracao.deployment_contingencia else 'não configurada'}; "
              f"progresso por eventos em POST {ROTA_PROGRESSO}.")
    print(f"Endereço: http://{configuracao.host}:{porta}  (encerre com Ctrl+C)")


def traduzir_erro_do_chat(erro: Exception, args: argparse.Namespace) -> tuple[str, int]:
    return (f"Erro inesperado ao iniciar o chat ({type(erro).__name__}). Confira a configuração, as bibliotecas "
            "instaladas e se a porta está livre.", lab_comum.CODIGO_INESPERADO)


def executar(args: argparse.Namespace) -> int:
    exigir_web()
    if args.demo and args.local_sem_autenticacao:
        raise ErroLab("Use --demo ou --local-sem-autenticacao, não os dois.")
    modo = lab_chat.MODO_DEMO if args.demo else lab_chat.MODO_LOCAL if args.local_sem_autenticacao else lab_chat.MODO_NUVEM
    configuracao = lab_chat.carregar_configuracao(os.environ, modo=modo, host=args.host)
    app = create_app(configuracao)
    configurar_registro()
    mostrar_inicio(configuracao, args.port)
    # lifespan="on": uma falha na partida (configuração, arquivos, serviço) encerra o programa em vez de ser ignorada.
    uvicorn.run(app, host=configuracao.host, port=args.port, lifespan="on", http="h11", ws="none", log_config=None,
                access_log=False, server_header=False, proxy_headers=False, limit_concurrency=LIMITE_DE_CONEXOES,
                h11_max_incomplete_event_size=TAMANHO_DOS_CABECALHOS, timeout_graceful_shutdown=TEMPO_DE_ESPERA_AO_ENCERRAR)
    return lab_comum.CODIGO_OK


def principal(argv: list[str] | None = None) -> int:
    lab_comum.configurar_saida()
    parser = lab_comum.ParserLab(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1",
                        help="Endereço em que o servidor escuta (padrão: 127.0.0.1). 0.0.0.0 só com a autenticação exigida.")
    parser.add_argument("--port", type=validar_porta, default=PORTA_PADRAO, help=f"Porta (padrão: {PORTA_PADRAO}).")
    parser.add_argument("--demo", action="store_true",
                        help="Respostas simuladas, sem Azure e sem autenticação. Só em 127.0.0.1, ::1 ou localhost.")
    parser.add_argument("--local-sem-autenticacao", action="store_true",
                        help="Usa o Azure com a sua sessão do Azure CLI, sem autenticação de usuário. "
                             "Só em 127.0.0.1, ::1 ou localhost.")
    args = parser.parse_args(argv)
    return lab_comum.executar_com_tratamento(executar, args, tradutor=traduzir_erro_do_chat)


if __name__ == "__main__":
    sys.exit(principal())
