"""Apoio dos testes: caminhos, cópia do pacote de dados e dublês do Blob Storage, do Search e da OpenAI (sem Azure)."""

from __future__ import annotations

import copy
import hashlib
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "scripts"))

from azure.core.exceptions import ResourceExistsError, ResourceModifiedError, ResourceNotFoundError  # noqa: E402


def copiar_pacote() -> tuple[tempfile.TemporaryDirectory, Path]:
    """Copia dados/l100 para uma pasta temporária, para os testes alterarem sem risco."""
    pasta = tempfile.TemporaryDirectory()
    destino = Path(pasta.name) / "l100"
    shutil.copytree(RAIZ / "dados" / "l100", destino)
    return pasta, destino / "inventario.json"


def erro_404(codigo: str) -> ResourceNotFoundError:
    erro = ResourceNotFoundError("não encontrado")
    erro.status_code = 404
    erro.error_code = codigo
    return erro


class BlobFalso:
    def __init__(self, dados: bytes, etag: str, metadata: dict[str, str], content_type: str):
        self.dados, self.etag, self.metadata, self.content_type = dados, etag, metadata, content_type


class ClienteBlobFalso:
    def __init__(self, container: "ContainerFalso", nome: str):
        self.container, self.nome = container, nome

    def _blob(self) -> BlobFalso:
        if not self.container.existe:
            raise erro_404("ContainerNotFound")
        if self.nome not in self.container.blobs:
            raise erro_404("BlobNotFound")
        return self.container.blobs[self.nome]

    def get_blob_properties(self) -> SimpleNamespace:
        blob = self._blob()
        return SimpleNamespace(size=len(blob.dados), etag=blob.etag, metadata=blob.metadata)

    def download_blob(self) -> SimpleNamespace:
        blob = self._blob()
        return SimpleNamespace(readall=lambda: blob.dados, properties=SimpleNamespace(etag=blob.etag))

    def upload_blob(self, dados: bytes, **opcoes) -> None:
        self.container.antes_de_enviar(self.nome)
        atual = self.container.blobs.get(self.nome)
        if not opcoes.get("overwrite", False) and atual is not None:
            raise ResourceExistsError("o blob já existe")
        if opcoes.get("etag") and atual is not None and atual.etag != opcoes["etag"]:
            raise ResourceModifiedError("o blob mudou")
        self.container.contador += 1
        self.container.blobs[self.nome] = BlobFalso(
            dados, f"etag-{self.container.contador}", dict(opcoes["metadata"]), opcoes["content_settings"].content_type
        )
        self.container.envios.append(self.nome)


class ContainerFalso:
    """Imita só o que os scripts usam do contêiner. Registra cada envio em `envios`."""

    def __init__(self, existe: bool = True):
        self.existe = existe
        self.blobs: dict[str, BlobFalso] = {}
        self.envios: list[str] = []
        self.contador = 0
        self.antes_de_enviar = lambda nome: None

    def get_blob_client(self, nome: str) -> ClienteBlobFalso:
        return ClienteBlobFalso(self, nome)

    def list_blobs(self, include=None):
        for nome, blob in self.blobs.items():
            yield SimpleNamespace(
                name=nome, size=len(blob.dados), metadata=blob.metadata,
                content_settings=SimpleNamespace(content_type=blob.content_type),
            )

    def colocar(self, nome: str, dados: bytes, metadata: dict[str, str] | None = None,
                content_type: str = "text/markdown; charset=utf-8") -> None:
        self.contador += 1
        self.blobs[nome] = BlobFalso(dados, f"etag-{self.contador}", metadata or {}, content_type)


def container_com_documentos(inventario: Path) -> ContainerFalso:
    """Contêiner falso já com os documentos do inventário, como depois do Desafio 01."""
    import lab_comum

    container = ContainerFalso()
    for documento in lab_comum.carregar_inventario(inventario).documentos:
        container.colocar(documento.blob, lab_comum.ler_conteudo(documento),
                          documento.metadados_blob, documento.tipo_conteudo)
    return container


def vetor_falso(texto: str, dimensoes: int) -> list[float]:
    """Vetor determinístico (de 1 a 32 dimensões) derivado do texto: o mesmo texto dá sempre o mesmo vetor."""
    resumo = hashlib.sha256(texto.encode("utf-8")).digest()
    return [resumo[i] / 255 * 2 - 1 for i in range(dimensoes)]


class OpenAIFalso:
    """Imita só o que o laboratório usa do cliente da OpenAI: embeddings.create. Registra cada chamada."""

    def __init__(self, dimensoes: int = 8, modelo: str = "text-embedding-3-small"):
        self.dimensoes, self.modelo = dimensoes, modelo
        self.chamadas: list[tuple[str, list[str]]] = []
        self.erro: Exception | None = None
        self.embeddings = SimpleNamespace(create=self._criar)

    def _criar(self, model: str, input: list[str]) -> SimpleNamespace:  # noqa: A002 - nome da API real
        self.chamadas.append((model, list(input)))
        if self.erro:
            raise self.erro
        itens = [SimpleNamespace(index=posicao, embedding=vetor_falso(texto, self.dimensoes))
                 for posicao, texto in enumerate(input)]
        # Fora de ordem de propósito: o código precisa usar o campo index, não a ordem da lista.
        return SimpleNamespace(data=itens[::-1], model=self.modelo,
                               usage=SimpleNamespace(total_tokens=sum(len(texto) // 3 + 1 for texto in input)))

    @property
    def textos_enviados(self) -> int:
        return sum(len(textos) for _, textos in self.chamadas)


def erro_openai(nome: str, status: int | None = None, mensagem: str | None = None, **atributos) -> Exception:
    """Erro com o nome, o módulo e o código HTTP de um erro da biblioteca da OpenAI, sem depender dela."""
    classe = type(nome, (Exception,), {"status_code": status, "__module__": "openai", **atributos})
    return classe(mensagem or f"{nome} de teste")


class OpenAIGeracaoFalso:
    """Imita só o que o laboratório usa da OpenAI na geração: responses.create. Registra cada chamada.

    Por padrão, responde citando o primeiro trecho recebido. Os testes trocam `responder` para simular
    outras respostas e `erro`, `status` ou `texto` para simular falhas.
    """

    def __init__(self, modelo: str = "gpt-5.4-mini-2026-03-17"):
        self.modelo = modelo
        self.chamadas: list[dict] = []
        self.erro: Exception | None = None
        self.status = "completed"
        self.texto: str | None = None
        self.responder = self._responder_padrao
        self.responses = SimpleNamespace(create=self._criar)

    @staticmethod
    def ids_recebidos(entrada: str) -> list[str]:
        return re.findall(r'<trecho id="([^"]+)"', entrada)

    def _responder_padrao(self, argumentos: dict) -> dict:
        return {"resposta": "Resposta de teste.", "fontes": self.ids_recebidos(argumentos["input"])[:1]}

    def _criar(self, **argumentos) -> SimpleNamespace:
        self.chamadas.append(argumentos)
        if self.erro:
            raise self.erro
        texto = self.texto if self.texto is not None else json.dumps(self.responder(argumentos), ensure_ascii=False)
        incompleto = SimpleNamespace(reason="max_output_tokens") if self.status == "incomplete" else None
        return SimpleNamespace(
            status=self.status, output_text=texto, model=self.modelo, incomplete_details=incompleto,
            usage=SimpleNamespace(input_tokens=len(argumentos["input"]) // 3, output_tokens=40,
                                  output_tokens_details=SimpleNamespace(reasoning_tokens=10)))


class ServicoRespostasFalso:
    """Imita o serviço de modelos do Azure (API Responses) no nível HTTP, sem rede.

    O Microsoft Agent Framework e a biblioteca da OpenAI rodam de verdade; só o transporte é trocado por este dublê.
    `roteiro` diz o que o "modelo" faz a cada ida ao serviço: ("buscar", consulta) pede a ferramenta de busca; um
    dicionário ou um texto é a resposta final; uma função recebe o pedido (o corpo da requisição) e devolve um desses.
    Cada pedido recebido fica em `pedidos`. Com `erro_http`, todo pedido recebe esse erro.
    """

    def __init__(self, roteiro):
        self.roteiro = list(roteiro)
        self.pedidos: list[dict] = []
        self.erro_http: tuple[int, dict] | None = None
        self.atraso = 0.0  # segundos antes de cada resposta

    def cliente_assincrono(self):
        import httpx2  # vem junto da biblioteca da OpenAI
        from openai import AsyncAzureOpenAI

        return AsyncAzureOpenAI(
            azure_endpoint="https://modelos-teste.openai.azure.com", api_version="v1", api_key="chave-de-teste",
            max_retries=0, http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(self._atender)))

    @staticmethod
    def texto_recebido(pedido: dict) -> str:
        """Tudo o que o modelo leu neste pedido: mensagens e resultados de ferramentas."""
        partes = []
        for item in pedido["input"]:
            if item.get("type") == "function_call_output":
                partes.append(str(item["output"]))
            for conteudo in item.get("content") or []:
                partes.append(str(conteudo.get("text", "")))
        return "\n".join(partes)

    @classmethod
    def primeiro_trecho(cls, pedido: dict) -> tuple[str, str]:
        """Id e texto do primeiro bloco <trecho> que o modelo recebeu."""
        achado = re.search(r'<trecho id="([^"]+)"[^>]*>\n(.*?)\n</trecho>', cls.texto_recebido(pedido), re.DOTALL)
        return achado.group(1), achado.group(2)

    async def _atender(self, requisicao):
        import asyncio

        import httpx2

        pedido = json.loads(requisicao.content)
        self.pedidos.append(pedido)
        if self.atraso:
            await asyncio.sleep(self.atraso)
        if self.erro_http is not None:
            return httpx2.Response(self.erro_http[0], json=self.erro_http[1])
        if not self.roteiro:
            raise AssertionError("o agente fez mais idas ao modelo do que o roteiro previu")
        passo = self.roteiro.pop(0)
        if callable(passo):
            passo = passo(pedido)
        numero = len(self.pedidos)
        situacao, detalhes = "completed", None
        if isinstance(passo, tuple) and passo[0] == "buscar":
            saida = [{"id": f"fc_{numero}", "type": "function_call", "status": "completed", "call_id": f"call_{numero}",
                      "name": "buscar_trechos", "arguments": json.dumps({"consulta": passo[1]}, ensure_ascii=False)}]
            if len(passo) > 2:  # texto escrito pelo modelo antes de pedir a ferramenta
                saida.insert(0, {"id": f"msg_{numero}", "type": "message", "status": "completed", "role": "assistant",
                                 "content": [{"type": "output_text", "annotations": [], "text": passo[2]}]})
        elif isinstance(passo, tuple) and passo[0] == "incompleto":
            saida, situacao, detalhes = [], "incomplete", {"reason": "max_output_tokens"}
        else:
            texto = passo if isinstance(passo, str) else json.dumps(passo, ensure_ascii=False)
            saida = [{"id": f"msg_{numero}", "type": "message", "status": "completed", "role": "assistant",
                      "content": [{"type": "output_text", "annotations": [], "text": texto}]}]
        entrada = len(json.dumps(pedido["input"], ensure_ascii=False)) // 3
        return httpx2.Response(200, json={
            "id": f"resp_{numero}", "object": "response", "created_at": 1, "status": situacao, "model": pedido["model"],
            "incomplete_details": detalhes, "output": saida, "parallel_tool_calls": False, "tool_choice": "auto", "tools": [],
            "usage": {"input_tokens": entrada, "input_tokens_details": {"cached_tokens": 0}, "output_tokens": 40,
                      "output_tokens_details": {"reasoning_tokens": 10}, "total_tokens": entrada + 40}})


class IndiceFalso:
    """Imita o Azure AI Search nas operações do laboratório. Registra cada operação que altera algo."""

    def __init__(self, nome: str = "vareleira-lar-l100"):
        self.nome = nome
        self.definicao: dict | None = None
        self.documentos: dict[str, dict] = {}
        self.operacoes: list[tuple[str, int]] = []

    def definicao_atual(self):
        return copy.deepcopy(self.definicao)

    def criar(self, definicao) -> None:
        self.operacoes.append(("criar", 1))
        self.definicao = copy.deepcopy(dict(definicao))

    def apagar(self) -> None:
        self.operacoes.append(("apagar", 1))
        self.definicao, self.documentos = None, {}

    def trechos_gravados(self) -> dict[str, dict]:
        return {chave: {"impressao": d.get("impressao"), "modelo_embeddings": d.get("modelo_embeddings")}
                for chave, d in self.documentos.items()}

    def gravar(self, documentos) -> None:
        self.operacoes.append(("gravar", len(documentos)))
        for documento in documentos:
            self.documentos[documento["id"]] = copy.deepcopy(documento)

    def remover(self, ids) -> None:
        self.operacoes.append(("remover", len(ids)))
        for chave in ids:
            self.documentos.pop(chave, None)

    def contar(self) -> int:
        return len(self.documentos)

    def consultar(self, texto, vetor, k):
        pontuados = []
        for documento in self.documentos.values():
            if vetor is not None:
                produto = sum(a * b for a, b in zip(vetor, documento["vetor"]))
                norma = (sum(a * a for a in vetor) * sum(b * b for b in documento["vetor"])) ** 0.5
                pontos = produto / norma
            else:
                pontos = float(sum(documento["conteudo"].lower().count(p) for p in str(texto).lower().split()))
            pontuados.append((pontos, documento))
        pontuados.sort(key=lambda item: item[0], reverse=True)
        campos = ("id", "documento_id", "titulo_documento", "secao", "clausulas", "conteudo", "fonte", "versao")
        return [{**{campo: documento[campo] for campo in campos}, "@search.score": pontos}
                for pontos, documento in pontuados[:k]]


def rodar_script(modulo, argumentos, *, container=None, abrir_indice=None, openai=None, geracao=None,
                 agente=None) -> tuple[int, str]:
    """Executa `modulo.principal` com os dublês no lugar do Azure e devolve (código de saída, texto impresso)."""
    import contextlib
    import io
    from unittest import mock

    import lab_agente
    import lab_comum
    import lab_geracao
    import lab_indexacao

    saida = io.StringIO()
    with contextlib.ExitStack() as pilha:
        if container is not None:
            pilha.enter_context(mock.patch.object(lab_comum, "criar_container", return_value=container))
        if abrir_indice is not None:
            pilha.enter_context(mock.patch.object(lab_indexacao, "abrir_indice", abrir_indice))
        if openai is not None:
            pilha.enter_context(mock.patch.object(
                lab_indexacao, "criar_cliente_embeddings",
                side_effect=lambda modelos, deployment, dimensoes, tenant=None, credencial=None:
                lab_indexacao.ClienteEmbeddings(openai, deployment, dimensoes)))
        if geracao is not None:
            pilha.enter_context(mock.patch.object(
                lab_geracao, "criar_cliente_geracao",
                side_effect=lambda modelos, deployment, esforco=lab_geracao.ESFORCO_PADRAO, tenant_id=None, credencial=None:
                lab_geracao.ClienteGeracao(geracao, deployment, modelos, esforco)))
        if agente is not None:
            original = lab_agente.criar_cliente_maf
            pilha.enter_context(mock.patch.object(
                lab_agente, "criar_cliente_maf",
                side_effect=lambda modelos, deployment, maximo_de_buscas=lab_agente.BUSCAS_PADRAO, tenant_id=None:
                original(modelos, deployment, maximo_de_buscas, tenant_id, async_client=agente.cliente_assincrono())))
        pilha.enter_context(contextlib.redirect_stdout(saida))
        pilha.enter_context(contextlib.redirect_stderr(saida))
        codigo = modulo.principal(argumentos)
    return codigo, saida.getvalue()


def indexar_pacote(inventario: Path, busca: str, modelos: str, dimensoes: int) -> tuple["IndiceFalso", "OpenAIFalso"]:
    """Indexa os documentos do inventário em um índice falso, como depois do Desafio 02."""
    import indexar_documentos
    import lab_comum

    indice, openai = IndiceFalso(), OpenAIFalso(dimensoes=dimensoes)
    codigo, saida = rodar_script(
        indexar_documentos,
        ["--conta", "stvlrag1234567890", "--busca", busca, "--modelos", modelos, "--dimensoes", str(dimensoes),
         "--inventario", str(inventario), "--executar"],
        container=container_com_documentos(inventario), abrir_indice=lambda *a, **k: indice, openai=openai)
    if codigo != lab_comum.CODIGO_OK:
        raise AssertionError(f"a indexação de apoio falhou: {saida}")
    return indice, openai
