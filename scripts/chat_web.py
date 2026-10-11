"""Servidor HTTP do chat do L200: a interface web e a API de uma pergunta por requisição, sem memória entre elas.

Rotas: GET /healthz (vivo, sem Azure), GET /readyz (configuração e serviço prontos, sem chamar o Azure), GET / e
GET /static/<arquivo> (interface) e POST /api/perguntar (JSON com a pergunta atual). Tudo, exceto /healthz e /readyz, exige
a identidade entregue pela autenticação integrada do Azure Container Apps quando VARELEIRA_EXIGIR_AUTENTICACAO=true. Essa
identidade vem em um cabeçalho sem assinatura: ela só vale se todo o tráfego chega pelo ingresso com a autenticação exigida.

O modo padrão é o da nuvem: a configuração vem de variáveis de ambiente (veja lab_chat.py), a autenticação é obrigatória e
a falta de qualquer valor impede a partida. --demo (respostas simuladas, sem Azure) e --local-sem-autenticacao (Azure com a
sua sessão do Azure CLI) só aceitam 127.0.0.1, ::1 ou localhost.

Exemplos:
    python scripts\\chat_web.py --host 127.0.0.1 --port 8000 --demo
    python scripts\\chat_web.py --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import lab_chat
import lab_comum
from lab_comum import ErroLab

try:
    import uvicorn
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse, Response
    from starlette.exceptions import HTTPException as ErroHttp
except ImportError:  # requirements/l200.txt ainda não foi instalado: create_app e principal explicam
    uvicorn = FastAPI = Request = JSONResponse = Response = ErroHttp = None  # type: ignore[assignment,misc]

PASTA_WEB = lab_comum.RAIZ / "web"
ARQUIVOS_DA_INTERFACE = ("index.html", "app.js", "style.css")
ARQUIVOS_ESTATICOS = {"app.js": "text/javascript; charset=utf-8", "style.css": "text/css; charset=utf-8"}
ROTAS_ISENTAS = frozenset({"/healthz", "/readyz"})  # as únicas sem autenticação: não leem nem devolvem dados
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


@dataclass
class Estado:
    """O que existe depois da partida. Não há dados de usuário aqui: só a configuração, o serviço e o controle de carga."""

    configuracao: lab_chat.ConfiguracaoChat
    servico: lab_chat.ServicoChat
    executor: ThreadPoolExecutor
    capacidade: threading.BoundedSemaphore
    arquivos: dict[str, bytes]


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


async def consultar(estado: Estado, pergunta: str) -> lab_chat.RespostaChat:
    """Executa a consulta (síncrona) em uma thread, com concorrência limitada e tempo máximo.

    Sem vaga, responde logo com 429 em vez de enfileirar. A vaga só volta quando a thread termina, mesmo que a requisição
    já tenha expirado: assim o número de consultas em andamento nunca passa do limite.
    """
    if not estado.capacidade.acquire(blocking=False):
        raise lab_chat.ErroChat(lab_chat.OCUPADO)

    def trabalho() -> lab_chat.RespostaChat:
        try:
            return estado.servico.perguntar(pergunta)
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
        raise lab_chat.ErroChat(lab_chat.INDISPONIVEL, "tempo_esgotado") from None


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
        executor = ThreadPoolExecutor(max_workers=configuracao.max_concorrencia, thread_name_prefix="chat")
        app.state.chat = Estado(configuracao, servico, executor, threading.BoundedSemaphore(configuracao.max_concorrencia), arquivos)
        LOG.info("assistente pronto %s", lab_chat.resumo_publico(configuracao))
        try:
            yield
        finally:
            app.state.chat = None
            executor.shutdown(wait=False, cancel_futures=True)

    app = FastAPI(title="Assistente do Vareleira Lar", lifespan=ciclo_de_vida, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.chat = None

    @app.middleware("http")
    async def proteger_e_registrar(request: Request, call_next):
        inicio = time.perf_counter()
        id_requisicao = uuid.uuid4().hex
        request.state.id_requisicao = id_requisicao
        request.state.causa = None
        try:
            erro_de_acesso = None
            if not lab_chat.host_permitido(configuracao.modo, request.headers.get("host")):
                erro_de_acesso = lab_chat.ErroChat(lab_chat.HOST_INVALIDO)
            elif configuracao.exigir_autenticacao and request.url.path not in ROTAS_ISENTAS:
                try:
                    lab_chat.validar_principal(request.headers.get(lab_chat.CABECALHO_PRINCIPAL), configuracao.tenants_autorizados)
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

    @app.post("/api/perguntar")
    async def perguntar(request: Request):
        try:
            estado = request.app.state.chat
            if estado is None:
                raise lab_chat.ErroChat(lab_chat.NAO_PRONTO)
            if request.url.query:
                raise lab_chat.ErroChat(lab_chat.CAMPOS_NAO_PERMITIDOS)
            corpo = await ler_corpo(request, lab_chat.LIMITE_DO_CORPO)
            pedido = lab_chat.ler_pedido(corpo, request.headers.get("content-type"))
            resposta = await consultar(estado, pedido.pergunta)
        except Exception as erro:  # noqa: BLE001 - toda falha vira um código público; o texto da exceção não sai daqui
            return responder_erro(request, lab_chat.classificar_erro(erro))
        return JSONResponse({"id": pedido.id_cliente, "id_requisicao": request.state.id_requisicao, **resposta.a_dict()})

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
