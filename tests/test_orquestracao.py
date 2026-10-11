"""Testes da coordenação limitada do L400 (sem Azure): fluxo do MAF com dublês de transporte, limites, contingência, cancelamento e HTTP.

O que se prova aqui: o fluxo do Microsoft Agent Framework instalado roda de verdade (executores tipados, agentes de planejamento e redação)
sobre transportes falsos; cada uma das 2 consultas usa o filtro do perfil (e preFilter no vetorial); sem contexto de acesso nada é chamado;
duas requisições ao mesmo tempo não se misturam; referências inventadas, trecho fora do perfil e conflito de versões falham antes da resposta;
as tentativas contadas são as que o transporte realmente recebeu (SDK com max_retries=0), inclusive falhas e contingência; 429/5xx/rede/tempo
trocam de deployment e 401/403/404/formato/pedido recusado não; orçamento de tokens, tentativas, buscas e prazo impedem as próximas chamadas;
o cancelamento de uma execução interrompe as próximas etapas e não toca nas outras; o progresso só tem vocabulário fechado e contagens;
e, sem a opção, o chat L200/L300 não muda e nem carrega o módulo da coordenação.
"""

import asyncio
import contextlib
import faulthandler
import io
import json
import re
import socket
import subprocess
import sys
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from types import MappingProxyType, SimpleNamespace
from unittest import mock

import support  # noqa: F401  (configura o caminho dos scripts)
import chat_web
import coordenar_maf
import lab_acesso as la
import lab_chat as lc
import lab_comum
import lab_geracao as lg
import lab_indexacao as li
import lab_orquestracao as lo
import lab_politica as lp
from support import OpenAIFalso, OpenAIGeracaoFalso, RAIZ, ServicoRespostasFalso, vetor_falso
from test_acesso import ClienteBuscaFalso, CredencialFalsa, IndiceAcessoFalso, IndiceQueIgnoraOFiltro, MARCADORES, TRECHOS, cabecalhos
from test_chat import (BUSCA, DIMENSOES, MODELOS, OUTRO_TENANT, PERGUNTA_INDIVIDUAL, PRECISA_DO_HTTP, SUJEITO, TENANT, ambiente,
                       codificar, config, guid, servidor)
from test_chat import principal as principal_sintetico

PERGUNTA = "Qual é a regra fictícia de teste para este documento?"
PLANO = {"consulta_principal": "regra fictícia aviso", "consulta_complementar": "franquia"}
CONTINGENCIA = "geracao-contingencia"
SEGREDO = "SEGREDO-NA-RESPOSTA-DO-SERVICO"
ATENDIMENTO = (la.PAPEL_ATENDIMENTO,)


# --------------------------------------------------------------------------------------
# Dublês
# --------------------------------------------------------------------------------------

class Relogio:
    """Relógio falso: o teste decide quanto tempo passou, sem esperar."""

    def __init__(self):
        self.agora = 1000.0

    def __call__(self):
        return self.agora

    def avancar(self, segundos):
        self.agora += segundos


def corpo_200(pedido, saida, com_uso=True, incompleto=False):
    texto = saida if isinstance(saida, str) else json.dumps(saida, ensure_ascii=False)
    entrada = len(json.dumps(pedido["input"], ensure_ascii=False)) // 3
    corpo = {"id": "resp_1", "object": "response", "created_at": 1, "status": "incomplete" if incompleto else "completed",
             "model": pedido["model"], "incomplete_details": {"reason": "max_output_tokens"} if incompleto else None,
             "output": [] if incompleto else [{"id": "msg_1", "type": "message", "status": "completed", "role": "assistant",
                                               "content": [{"type": "output_text", "annotations": [], "text": texto}]}],
             "parallel_tool_calls": False, "tool_choice": "auto", "tools": []}
    if com_uso:
        corpo["usage"] = {"input_tokens": entrada, "input_tokens_details": {"cached_tokens": 0}, "output_tokens": 40,
                          "output_tokens_details": {"reasoning_tokens": 10}, "total_tokens": entrada + 40}
    return corpo


class Transporte(ServicoRespostasFalso):
    """O serviço de modelos falso (API Responses, no nível HTTP), com falhas por tentativa.

    `roteiro` diz o que acontece a cada pedido recebido, em ordem; `responder(pedido)` decide por pedido (para requisições ao mesmo tempo).
    Um passo é um dicionário ou texto (a saída do modelo), uma função do pedido, ou ("http", status[, código]), ("rede",), ("tempo",),
    ("lento", segundos[, saída]), ("sem_uso", saída) e ("incompleto",). Cada pedido recebido fica em `pedidos`: é a contagem real.
    """

    def __init__(self, roteiro=(), responder=None):
        super().__init__(roteiro)
        self.responder = responder

    async def _atender(self, requisicao):
        import httpx2

        pedido = json.loads(requisicao.content)
        self.pedidos.append(pedido)
        if self.responder is not None:
            passo = self.responder(pedido)
        elif self.roteiro:
            passo = self.roteiro.pop(0)
        else:
            raise AssertionError("o serviço recebeu mais pedidos do que o roteiro previu")
        if callable(passo):
            passo = passo(pedido)
        if isinstance(passo, tuple):
            tipo = passo[0]
            if tipo == "http":
                return httpx2.Response(passo[1], json={"error": {"code": passo[2] if len(passo) > 2 else "falha", "message": SEGREDO}})
            if tipo == "rede":
                raise httpx2.ConnectError(SEGREDO, request=requisicao)
            if tipo == "tempo":
                raise httpx2.ReadTimeout(SEGREDO, request=requisicao)
            if tipo == "lento":
                await asyncio.sleep(passo[1])
                passo = passo[2] if len(passo) > 2 else {}
            elif tipo == "sem_uso":
                return httpx2.Response(200, json=corpo_200(pedido, passo[1], com_uso=False))
            elif tipo == "incompleto":
                return httpx2.Response(200, json=corpo_200(pedido, "", incompleto=True))
        return httpx2.Response(200, json=corpo_200(pedido, passo))

    def de_planejamento(self):
        return [pedido for pedido in self.pedidos if pedido["text"]["format"]["name"] == "plano_de_consultas"]

    def de_redacao(self):
        return [pedido for pedido in self.pedidos if pedido["text"]["format"]["name"] == "resposta_com_referencias"]


def redator(tipo=lp.DOCUMENTADA, resposta="Resposta de teste.", referencias=True):
    """A saída do redator no contrato de referências curtas: por padrão cita o primeiro trecho recebido."""
    def montar(pedido):
        identificador, _ = ServicoRespostasFalso.primeiro_trecho(pedido)
        lista = [identificador] if referencias is True else list(referencias or [])
        return {"tipo": tipo, "resposta": resposta, "referencias": lista}

    return montar


def responder_padrao(plano=PLANO, saida_do_redator=None):
    """Para requisições simultâneas: o passo depende de quem pede (planejador ou redator), não da ordem de chegada."""
    escrever = saida_do_redator or redator()

    def responder(pedido):
        return plano if pedido["text"]["format"]["name"] == "plano_de_consultas" else escrever(pedido)

    return responder


def trecho_de(identificador, documento_id, versao, classe="compartilhado", conteudo=None):
    return {"id": identificador, "documento_id": documento_id, "titulo_documento": "Documento sintético", "secao": "Seção",
            "clausulas": "", "fonte": f"vareleira-lar-l300/{identificador}.md", "versao": versao, "acesso": classe,
            "conteudo": conteudo or f"Regra fictícia de teste do trecho {identificador}: vale só para este exercício documental."}


class OpenAIComDimensoes(OpenAIFalso):
    """Embeddings como o serviço real (modelos text-embedding-3): sem `dimensions` os vetores têm o tamanho nativo do modelo
    (1536 aqui); com `dimensions`, o tamanho pedido. `pedidas` guarda o `dimensions` de cada pedido (None se não foi enviado)."""

    NATIVO = 1536

    def __init__(self, dimensoes=DIMENSOES, nativo=NATIVO):
        super().__init__(dimensoes=dimensoes)
        self.nativo, self.pedidas = nativo, []

    def _criar(self, model, input, dimensions=None):  # noqa: A002 - nome da API real
        self.chamadas.append((model, list(input)))
        self.pedidas.append(dimensions)
        if self.erro:
            raise self.erro
        tamanho = self.nativo if dimensions is None else dimensions
        itens = [SimpleNamespace(index=posicao, embedding=(vetor_falso(texto, 32) * (tamanho // 32 + 1))[:tamanho])
                 for posicao, texto in enumerate(input)]
        return SimpleNamespace(data=itens[::-1], model=self.modelo,
                               usage=SimpleNamespace(total_tokens=sum(len(texto) // 3 + 1 for texto in input)))


class Pilha:
    """O serviço coordenado real (MAF, política, orçamento) sobre o transporte falso, o índice falso e o cliente de embeddings falso."""

    def __init__(self, roteiro=None, *, responder=None, trechos=None, indice=None, modo="hibrida", contingencia=CONTINGENCIA,
                 limites=None, disjuntor=None, relogio=None, k=6, timeout=lc.TEMPO_PADRAO, dimensoes=DIMENSOES, openai=None):
        self.transporte = Transporte(roteiro or [], responder)
        self.indice = indice if indice is not None else IndiceAcessoFalso(trechos=TRECHOS if trechos is None else trechos)
        self.openai = openai if openai is not None else OpenAIComDimensoes(dimensoes=dimensoes)
        self.clientes, self.eventos = [], []
        embeddings = None if modo == "texto" else lo.ClienteEmbeddingsDeUmaTentativa(self.openai, "embeddings", dimensoes)
        self.parametros = lo.ParametrosCoordenacao(
            modelos=MODELOS, busca=BUSCA, indice=la.INDICE_PADRAO, dimensoes=dimensoes, deployment_contingencia=contingencia,
            modo_busca=modo, k=k, timeout_segundos=timeout, limites=limites or lo.LimitesCoordenacao())
        extras = {} if relogio is None else {"relogio": relogio}
        self.servico = lo.ServicoCoordenado(self.parametros, indice=self.indice, embeddings=embeddings,
                                            fabrica_cliente=self.abrir_cliente, disjuntor=disjuntor, **extras)

    def abrir_cliente(self):
        cliente = self.transporte.cliente_assincrono()
        self.clientes.append(cliente)
        return cliente

    def perguntar(self, pergunta=PERGUNTA, papeis=ATENDIMENTO, **opcoes):
        return self.servico.perguntar(pergunta, la.autorizar(papeis), progresso=self.eventos.append, **opcoes)

    def modelos_usados(self):
        return [pedido["model"] for pedido in self.transporte.pedidos]

    def etapas(self):
        return [(evento.etapa, evento.estado) for evento in self.eventos if evento.tipo == lo.EVENTO_ETAPA]

    def resumo(self):
        return next(dict(evento.dados) for evento in self.eventos if evento.tipo == lo.EVENTO_RESUMO)

    def estado_final(self):
        return next(evento.estado for evento in self.eventos if evento.tipo == lo.EVENTO_RESUMO)

    def sem_chamadas(self):
        return not self.transporte.pedidos and not self.openai.chamadas and not self.indice.consultas


def erro_chat(teste, chamada, codigo, causa=None):
    with teste.assertRaises(lc.ErroChat) as contexto:
        chamada()
    teste.assertEqual(contexto.exception.codigo, codigo)
    if causa is not None:
        teste.assertEqual(contexto.exception.causa, causa)
    return contexto.exception


def esperar_ate(condicao, limite=15):
    fim = time.monotonic() + limite
    while not condicao() and time.monotonic() < fim:
        time.sleep(0.02)
    return condicao()


def threads_do_pool():
    """As threads de busca e embeddings das execuções (o pool de cada execução usa o prefixo 'coordenacao')."""
    return [thread for thread in threading.enumerate() if thread.name.startswith("coordenacao_") and thread.is_alive()]


class TesteComLimite(unittest.TestCase):
    """Se um teste com laço de eventos, servidor ou threads travar, o processo cai com as pilhas das threads em vez de travar a suíte."""

    LIMITE_DO_TESTE_S = 120

    def setUp(self):
        super().setUp()
        faulthandler.dump_traceback_later(self.LIMITE_DO_TESTE_S, exit=True, file=sys.__stderr__ or sys.stderr)
        self.addCleanup(faulthandler.cancel_dump_traceback_later)


# --------------------------------------------------------------------------------------
# Configuração, opt-in e padrões
# --------------------------------------------------------------------------------------

def ambiente_l400(mudancas=None, sem=()):
    base = {lc.VAR_EXIGIR_ACESSO_DOCUMENTAL: "true", lc.VAR_INDICE: "vareleira-lar-l300-l400-768", lc.VAR_DIMENSOES: "768",
            lc.VAR_EXIGIR_COORDENACAO: "true", lc.VAR_DEPLOYMENT_CONTINGENCIA: CONTINGENCIA}
    base.update(mudancas or {})
    return ambiente({nome: valor for nome, valor in base.items() if nome not in sem})


def config_l400(**mudancas):
    valores = {"exigir_acesso_documental": True, "indice": la.INDICE_PADRAO, "exigir_coordenacao": True,
               "deployment_contingencia": CONTINGENCIA, **mudancas}
    return config(**valores)


class ConfiguracaoL400Tests(TesteComLimite):
    def test_a_coordenacao_vem_desligada_e_o_resumo_dos_outros_modos_nao_muda(self):
        padrao = lc.carregar_configuracao(ambiente())
        for configuracao in (lc.ConfiguracaoChat(), padrao):
            self.assertEqual((configuracao.exigir_coordenacao, configuracao.deployment_contingencia), (False, None))
        self.assertNotIn("coordenacao", lc.resumo_publico(padrao))
        explicita = lc.carregar_configuracao(ambiente({lc.VAR_EXIGIR_COORDENACAO: "false"}))
        self.assertFalse(explicita.exigir_coordenacao)

    def test_variaveis_da_coordenacao_e_o_indice_candidato_de_768_dimensoes(self):
        configuracao = lc.carregar_configuracao(ambiente_l400())
        self.assertEqual((configuracao.exigir_coordenacao, configuracao.deployment_contingencia, configuracao.indice,
                          configuracao.dimensoes), (True, CONTINGENCIA, "vareleira-lar-l300-l400-768", 768))
        self.assertTrue(la.indice_l300(configuracao.indice), "o candidato conserva o prefixo do L300")
        resumo = lc.resumo_publico(configuracao)
        self.assertIn("coordenacao=sim contingencia=sim", resumo)
        self.assertNotIn(CONTINGENCIA, resumo)
        sem_contingencia = lc.carregar_configuracao(ambiente_l400(sem=(lc.VAR_DEPLOYMENT_CONTINGENCIA,)))
        self.assertIsNone(sem_contingencia.deployment_contingencia)
        self.assertIn("contingencia=nao", lc.resumo_publico(sem_contingencia))

    def test_configuracao_invalida_da_coordenacao_impede_a_partida_sem_repetir_valores(self):
        casos = {
            "sem acesso documental": (ambiente_l400({lc.VAR_EXIGIR_ACESSO_DOCUMENTAL: "false"}), lc.VAR_EXIGIR_ACESSO_DOCUMENTAL),
            "sem autenticação": (ambiente_l400({lc.VAR_EXIGIR_AUTENTICACAO: "false"}), lc.VAR_EXIGIR_AUTENTICACAO),
            "índice do L200": (ambiente_l400({lc.VAR_INDICE: "vareleira-lar-l200"}), lc.VAR_INDICE),
            "contingência igual à geração": (ambiente_l400({lc.VAR_DEPLOYMENT_CONTINGENCIA: "geracao"}), lc.VAR_DEPLOYMENT_CONTINGENCIA),
            "contingência sem coordenação": (ambiente_l400({lc.VAR_EXIGIR_COORDENACAO: "false"}), lc.VAR_DEPLOYMENT_CONTINGENCIA),
            "tempo curto demais": (ambiente_l400({lc.VAR_TIMEOUT: "10"}), lc.VAR_TIMEOUT),
            "valor que não é booleano": (ambiente_l400({lc.VAR_EXIGIR_COORDENACAO: "talvez"}), lc.VAR_EXIGIR_COORDENACAO),
            "nome de deployment inválido": (ambiente_l400({lc.VAR_DEPLOYMENT_CONTINGENCIA: "Valor/ruim xyz"}),
                                            lc.VAR_DEPLOYMENT_CONTINGENCIA),
        }
        for rotulo, (variaveis, nome) in casos.items():
            with self.subTest(rotulo=rotulo), self.assertRaises(lc.ErroConfiguracao) as erro:
                lc.carregar_configuracao(variaveis)
            self.assertIn(nome, str(erro.exception))
            self.assertNotIn("ruim xyz", str(erro.exception))
        for modo in (lc.MODO_LOCAL, lc.MODO_DEMO):
            with self.subTest(modo=modo), self.assertRaises(lc.ErroConfiguracao) as erro:
                lc.carregar_configuracao(ambiente_l400(), modo=modo, host="127.0.0.1")
            self.assertIn(lc.VAR_EXIGIR_COORDENACAO, str(erro.exception))
        with self.assertRaises(lc.ErroConfiguracao):
            lc.validar_configuracao(config_l400(modo=lc.MODO_DEMO, host="127.0.0.1"))
        lc.validar_configuracao(config_l400())

    def test_o_chat_sem_a_coordenacao_nao_carrega_o_modulo_nem_o_maf(self):
        codigo = ("import sys; sys.path.insert(0, 'scripts'); import chat_web, lab_chat; "
                  "assert 'lab_orquestracao' not in sys.modules and 'agent_framework' not in sys.modules")
        resultado = subprocess.run([sys.executable, "-c", codigo], cwd=RAIZ, capture_output=True, text=True, timeout=120)
        self.assertEqual(resultado.returncode, 0, resultado.stderr)

    def test_a_fabrica_cria_o_servico_coordenado_sem_rede_nem_token_e_sem_os_ajudantes_do_l200(self):
        class CredencialQueNaoPodeSerUsada:
            def get_token(self, *escopos, **opcoes):
                raise AssertionError("nenhum token deve ser pedido na partida")

        with mock.patch.object(socket.socket, "connect", side_effect=AssertionError("conexão de rede na partida")), \
                mock.patch.object(lc, "criar_credencial", return_value=CredencialQueNaoPodeSerUsada()), \
                mock.patch.object(lg, "criar_cliente_geracao", side_effect=AssertionError("cliente do L200")), \
                mock.patch.object(lg, "criar_recuperador", side_effect=AssertionError("recuperador do L200")):
            servico = lc.criar_servico_azure(config_l400(indice="vareleira-lar-l300-l400-768", dimensoes=768))
            cliente_de_modelos = servico.fabrica_cliente()
        self.assertIsInstance(servico, lo.ServicoCoordenado)
        self.assertTrue(servico.coordenado and servico.exige_acesso)
        self.assertEqual(servico.parametros.deployment_contingencia, CONTINGENCIA)
        self.assertEqual((servico.embeddings.cliente.max_retries, servico.embeddings.dimensoes), (0, 768))
        self.assertEqual((cliente_de_modelos.max_retries, str(cliente_de_modelos.base_url)),
                         (0, f"https://{MODELOS}.openai.azure.com/openai/v1/"))
        asyncio.run(cliente_de_modelos.close())
        politicas = servico.indice._documentos._client._pipeline._impl_policies
        repeticoes = [getattr(politica, "policy", politica) for politica in politicas]
        totais = [politica.total_retries for politica in repeticoes if type(politica).__name__ == "RetryPolicy"]
        self.assertEqual(totais, [0], "o cliente de busca não repete por conta própria: cada consulta é uma tentativa contada")

    def test_cliente_com_repeticoes_do_sdk_e_recusado_antes_de_qualquer_pedido(self):
        pilha = Pilha([PLANO, redator()])
        from openai import AsyncAzureOpenAI

        def com_repeticoes():
            return AsyncAzureOpenAI(azure_endpoint="https://modelos-teste.openai.azure.com", api_version="v1", api_key="chave-de-teste",
                                    max_retries=2)

        pilha.servico.fabrica_cliente = com_repeticoes
        erro_chat(self, pilha.perguntar, lc.ERRO_INTERNO, "cliente_com_repeticoes")
        self.assertTrue(pilha.sem_chamadas())

    def test_todo_limite_e_finito_e_zero_nunca_significa_ilimitado(self):
        self.assertEqual(lo.LimitesCoordenacao().problemas(), [])
        for nome, (minimo, maximo) in lo.FAIXAS_DOS_LIMITES.items():
            self.assertGreater(minimo, 0, f"{nome}: zero nunca é um limite válido")
            for invalido in (0, -1, minimo - 1, maximo + 1, float("nan"), float("inf"), True, None, "8"):
                with self.subTest(limite=nome, valor=invalido):
                    self.assertTrue(lo.LimitesCoordenacao(**{nome: invalido}).problemas(), f"{nome}={invalido!r} foi aceito")
            for valor in (minimo, maximo):
                self.assertEqual(lo.LimitesCoordenacao(**{nome: valor}).problemas(), [], f"{nome}={valor}")
        self.assertTrue(lo.LimitesCoordenacao(max_chamadas=4, max_chamadas_modelo=6).problemas(), "tentativas de geração acima do total")
        self.assertTrue(lo.LimitesCoordenacao(max_chamadas=4).problemas("hibrida") == [])
        self.assertEqual((lo.chamadas_minimas("texto"), lo.chamadas_minimas("hibrida")), (3, 4))
        self.assertTrue(lo.LimitesCoordenacao(max_chamadas=4).problemas("hibrida") == [] and lo.LimitesCoordenacao(max_chamadas=4).problemas("texto") == [])

    def test_parametros_e_servico_invalidos_nao_chegam_a_chamar_modelos(self):
        validos = dict(modelos=MODELOS, busca=BUSCA, dimensoes=DIMENSOES)
        invalidos = {"índice do L200": {"indice": "vareleira-lar-l200"}, "contingência igual à geração": {"deployment_contingencia": "geracao"},
                     "tempo curto": {"timeout_segundos": 10}, "k fora da faixa": {"k": 11}, "esforço desconhecido": {"esforco": "max"},
                     "modo desconhecido": {"modo_busca": "outro"}, "busca com formato de endereço": {"busca": "srch.exemplo/"}}
        for rotulo, mudanca in invalidos.items():
            with self.subTest(rotulo=rotulo):
                parametros = lo.ParametrosCoordenacao(**{**validos, **mudanca})
                self.assertTrue(parametros.problemas())
                with self.assertRaises(lc.ErroConfiguracao) as erro:
                    lo.ServicoCoordenado(parametros, indice=IndiceAcessoFalso(), embeddings=object(), fabrica_cliente=lambda: None)
                self.assertNotIn("srch.exemplo", str(erro.exception))
        with self.assertRaises(lc.ErroConfiguracao):
            lo.ServicoCoordenado(lo.ParametrosCoordenacao(**validos), indice=object(), embeddings=object(), fabrica_cliente=lambda: None)


class EmbeddingsDeUmaTentativaTests(TesteComLimite):
    """O candidato de 768 dimensões foi criado com `dimensions` (modelos text-embedding-3): a consulta precisa pedir o mesmo tamanho."""

    def test_o_indice_de_768_dimensoes_pede_768_ao_modelo_e_recebe_768(self):
        servico = OpenAIComDimensoes(dimensoes=768)
        resultado = lo.ClienteEmbeddingsDeUmaTentativa(servico, "embeddings", 768).gerar(["franquia danos elétricos"])
        self.assertEqual(servico.pedidas, [768], "o pedido leva `dimensions`")
        self.assertEqual([len(vetor) for vetor in resultado.vetores], [768])

    def test_o_indice_de_referencia_de_1536_dimensoes_continua_com_o_pedido_de_antes(self):
        servico = OpenAIComDimensoes(dimensoes=1536)
        resultado = lo.ClienteEmbeddingsDeUmaTentativa(servico, "embeddings", 1536).gerar(["franquia danos elétricos"])
        self.assertEqual(servico.pedidas, [None], "sem `dimensions`: o pedido validado no Azure e o do L100 ao L300 não mudam")
        self.assertEqual([len(vetor) for vetor in resultado.vetores], [1536])

    def test_o_servico_que_devolve_1536_para_um_indice_de_768_e_recusado_sem_consultar_o_indice(self):
        class IgnoraDimensions(OpenAIComDimensoes):
            def _criar(self, model, input, dimensions=None):  # noqa: A002 - descarta o parâmetro, como um modelo que não o aceita
                return super()._criar(model, input)

        with self.assertRaises(lab_comum.ErroLab) as erro:
            lo.ClienteEmbeddingsDeUmaTentativa(IgnoraDimensions(dimensoes=768), "embeddings", 768).gerar(["franquia danos elétricos"])
        self.assertIn("1536", str(erro.exception))
        self.assertIn("768", str(erro.exception))

    def test_a_coordenacao_inteira_funciona_com_o_indice_de_768_e_um_modelo_de_1536_nativos(self):
        servico = OpenAIComDimensoes(dimensoes=768)
        pilha = Pilha([PLANO, redator()], dimensoes=768, openai=servico)
        resposta = pilha.perguntar()
        self.assertEqual(resposta.situacao, lp.RESPONDIDA)
        self.assertEqual(servico.pedidas, [768, 768], "um pedido de embeddings por busca, cada um com `dimensions`")
        resumo = pilha.resumo()
        self.assertEqual((resumo["chamadas_embeddings"], resumo["buscas"], resumo["uso_incerto"]), (2, 2, False))

    def test_sem_o_parametro_a_coordenacao_falha_antes_da_busca_com_o_uso_incerto(self):
        """O sintoma visto no Azure com o candidato: planejamento ok, um pedido de embeddings recusado, nenhuma busca."""
        class IgnoraDimensions(OpenAIComDimensoes):
            def _criar(self, model, input, dimensions=None):  # noqa: A002
                return super()._criar(model, input)

        pilha = Pilha([PLANO, redator()], dimensoes=768, openai=IgnoraDimensions(dimensoes=768))
        erro_chat(self, pilha.perguntar, lc.INDISPONIVEL)
        resumo = pilha.resumo()
        self.assertEqual((resumo["chamadas_modelo"], resumo["chamadas_embeddings"], resumo["buscas"], resumo["uso_incerto"]), (1, 1, 0, True))
        self.assertEqual(pilha.transporte.de_redacao(), [])


# --------------------------------------------------------------------------------------
# O fluxo do MAF
# --------------------------------------------------------------------------------------

class FluxoTests(TesteComLimite):
    def test_o_fluxo_do_maf_planeja_busca_com_filtro_em_cada_consulta_verifica_redige_e_aplica_a_politica(self):
        pilha = Pilha([PLANO, redator()])
        contexto = la.autorizar(ATENDIMENTO)
        resposta = pilha.perguntar()
        self.assertEqual((resposta.tipo, resposta.situacao, resposta.texto), (lp.DOCUMENTADA, lp.RESPONDIDA, "Resposta de teste."))
        self.assertEqual([evidencia.id for evidencia in resposta.evidencias], ["TRECHO-1"])
        self.assertEqual(resposta.evidencias[0].citacao, lc.limpar_texto(TRECHOS[0]["conteudo"], None), "a citação é o trecho, montado pelo programa")
        # duas consultas, cada uma com o filtro do perfil e com o vetor (híbrida)
        self.assertEqual([(consulta["texto"], consulta["filtro"], consulta["vetor"], consulta["k"]) for consulta in pilha.indice.consultas],
                         [("regra fictícia aviso", contexto.filtro, True, 6), ("franquia", contexto.filtro, True, 6)])
        self.assertEqual(pilha.openai.textos_enviados, 2, "um embedding por consulta")
        # dois pedidos de modelo: planejamento e redação, no mesmo deployment, sem ferramentas e com saída limitada
        planejamento, redacao = pilha.transporte.pedidos
        self.assertEqual((planejamento["model"], redacao["model"]), ("geracao", "geracao"))
        self.assertEqual(planejamento["instructions"], lo.INSTRUCOES_DO_PLANEJADOR)
        self.assertEqual(redacao["instructions"], lc.INSTRUCOES_L200)
        for pedido, formato, saida_maxima in ((planejamento, "plano_de_consultas", 1000), (redacao, "resposta_com_referencias", 3000)):
            self.assertEqual(pedido["text"]["format"]["name"], formato)
            self.assertEqual((pedido["max_output_tokens"], pedido["store"], pedido["reasoning"]), (saida_maxima, False, {"effort": "low"}))
            self.assertNotIn("tools", pedido, "o agente não tem ferramentas")
            self.assertNotIn("tool_choice", pedido)
        self.assertIn("<pergunta>", ServicoRespostasFalso.texto_recebido(planejamento))
        self.assertNotIn("<trecho", ServicoRespostasFalso.texto_recebido(planejamento), "o planejador não vê os trechos")
        self.assertEqual(redacao["text"]["format"]["schema"]["properties"]["referencias"]["items"]["enum"], ["T1", "T2"])
        for oculto in (la.INDICE_PADRAO, BUSCA, MODELOS, contexto.filtro, "acesso", "compartilhado"):
            self.assertNotIn(oculto, json.dumps(redacao, ensure_ascii=False), "o modelo não recebe filtro, índice, recurso nem classe")
        # etapas, tentativas e contagens reais
        self.assertEqual(pilha.etapas(), [(etapa, estado) for etapa in lo.ETAPAS for estado in ("iniciada", "concluida")])
        self.assertEqual(pilha.estado_final(), "concluida")
        resumo = pilha.resumo()
        self.assertEqual((resumo["chamadas_modelo"], resumo["chamadas_embeddings"], resumo["buscas"], resumo["chamadas_total"]), (2, 2, 2, 6))
        self.assertEqual(resumo["chamadas_modelo"], len(pilha.transporte.pedidos), "o contado é o que o transporte recebeu")
        self.assertEqual((resumo["tentativas_falhas"], resumo["contingencia"], resumo["uso_incerto"]), (0, False, False))
        self.assertTrue(all(cliente.max_retries == 0 for cliente in pilha.clientes))

    def test_o_workflow_e_um_grafo_linear_tipado_do_maf_instalado(self):
        nucleo = lo.Nucleo("", None, lo.ParametrosCoordenacao(modelos=MODELOS, busca=BUSCA))
        fluxo = lo.construir_workflow(nucleo)
        self.assertEqual([executor.id for executor in fluxo.get_executors_list()], list(lo.ETAPAS))
        self.assertEqual((fluxo.max_iterations, fluxo.name), (len(lo.ETAPAS), lo.NOME_DO_FLUXO))
        tipos = {executor.id: ([t.__name__ for t in executor.input_types], [t.__name__ for t in executor.output_types])
                 for executor in fluxo.get_executors_list()}
        self.assertEqual(tipos["planejamento"], (["PedidoDaConsulta"], ["PlanoDeConsultas"]))
        self.assertEqual(tipos["recuperacao"], (["PlanoDeConsultas"], ["Recuperados"]))
        self.assertEqual(tipos["politica"], (["RedacaoPronta"], []))
        self.assertEqual([t.__name__ for t in fluxo.get_executors_list()[-1].workflow_output_types], ["RespostaChat"])
        outro = lo.construir_workflow(nucleo)
        self.assertIsNot(fluxo, outro)
        self.assertTrue(all(a is not b for a, b in zip(fluxo.get_executors_list(), outro.get_executors_list())))

    def test_preFilter_e_o_filtro_do_perfil_chegam_a_busca_do_azure_nos_tres_modos_em_todas_as_consultas(self):
        class BuscaComTrechos(ClienteBuscaFalso):
            def search(self, **argumentos):
                super().search(**argumentos)
                classes = la.classes_do_filtro(argumentos["filter"])
                return iter([dict(item) for item in TRECHOS if item["acesso"] in classes])

        for modo in ("texto", "vetorial", "hibrida"):
            with self.subTest(modo=modo):
                pilha = Pilha([PLANO, redator()], modo=modo)
                indice = lo.IndiceBuscaDeUmaTentativa(BUSCA, la.INDICE_PADRAO, credencial=CredencialFalsa(), exigir_filtro=True)
                indice._documentos = BuscaComTrechos()
                pilha.servico.indice = indice
                contexto = la.autorizar(ATENDIMENTO)
                self.assertEqual(pilha.perguntar().situacao, lp.RESPONDIDA)
                self.assertEqual(len(indice._documentos.chamadas), 2, "uma busca por consulta")
                for chamada, consulta in zip(indice._documentos.chamadas, ("regra fictícia aviso", "franquia")):
                    self.assertEqual((chamada["filter"], chamada["search_text"] == (None if modo == "vetorial" else consulta)),
                                     (contexto.filtro, True))
                    self.assertEqual(chamada["select"], [*li.IndiceBusca.CAMPOS_DO_RESULTADO, "acesso"])
                    if modo == "texto":
                        self.assertNotIn("vector_queries", chamada)
                        self.assertNotIn("vector_filter_mode", chamada)
                    else:
                        self.assertEqual((chamada["vector_filter_mode"], len(chamada["vector_queries"])), ("preFilter", 1))
                self.assertEqual(pilha.openai.textos_enviados, 0 if modo == "texto" else 2)

    def test_sem_contexto_de_acesso_nada_e_buscado_calculado_nem_enviado_aos_modelos(self):
        pilha = Pilha([PLANO, redator()])
        erro_chat(self, lambda: pilha.servico.perguntar(PERGUNTA), lc.NAO_AUTORIZADO, "sem_contexto_de_acesso")
        for falso in (object(), SimpleContexto(), "search.in(acesso,'corretor',',')", {"filtro": "x"}):
            with self.subTest(falso=type(falso).__name__):
                erro_chat(self, lambda falso=falso: pilha.servico.perguntar(PERGUNTA, falso), lc.NAO_AUTORIZADO, "contexto_invalido")
        for pergunta, codigo in (("   ", lc.PERGUNTA_VAZIA), (None, lc.PERGUNTA_VAZIA), ("a" * (lc.LIMITE_DA_PERGUNTA + 1), lc.PERGUNTA_LONGA)):
            erro_chat(self, lambda pergunta=pergunta: pilha.servico.perguntar(pergunta, la.autorizar(ATENDIMENTO)), codigo)
        self.assertTrue(pilha.sem_chamadas(), "nem modelos, nem embeddings, nem busca")
        self.assertEqual(pilha.clientes, [], "nem o cliente de modelos foi aberto")

    def test_o_planejador_so_escolhe_texto_de_busca_nunca_o_filtro_nem_o_destino(self):
        injecao = "regra') or true or search.in(acesso, 'corretor"
        pilha = Pilha([{"consulta_principal": injecao, "consulta_complementar": "  segundo   assunto  "}, redator()])
        contexto = la.autorizar(ATENDIMENTO)
        pilha.perguntar()
        self.assertEqual([(consulta["texto"], consulta["filtro"]) for consulta in pilha.indice.consultas],
                         [(injecao, contexto.filtro), ("segundo assunto", contexto.filtro)])
        self.assertNotIn(MARCADORES["corretor"], json.dumps(pilha.transporte.de_redacao()))

    def test_plano_invalido_e_recusado_antes_de_qualquer_busca(self):
        casos = {"sem consulta principal": {"consulta_principal": "   ", "consulta_complementar": "x"},
                 "consulta longa demais": {"consulta_principal": "a" * (lo.LIMITE_DA_CONSULTA + 1), "consulta_complementar": ""},
                 "campo ausente": {"consulta_principal": "regra"}, "campo que não é texto": {"consulta_principal": 3, "consulta_complementar": ""},
                 "texto solto": "isto não é JSON"}
        for rotulo, plano in casos.items():
            with self.subTest(rotulo=rotulo):
                pilha = Pilha([plano, redator()])
                erro_chat(self, pilha.perguntar, lc.RESPOSTA_NAO_VERIFICADA)
                self.assertEqual((len(pilha.transporte.pedidos), pilha.openai.chamadas, pilha.indice.consultas), (1, [], []))
        repetidas = Pilha([{"consulta_principal": "Regra  de AVISO", "consulta_complementar": "regra de aviso"}, redator()])
        repetidas.perguntar()
        self.assertEqual(len(repetidas.indice.consultas), 1, "consultas repetidas viram uma só")

    def test_referencia_inventada_descarta_a_resposta_inteira_sem_mostrar_o_texto_do_modelo(self):
        for rotulo, saida in {"id inventado": redator(resposta="Resposta inventada.", referencias=["T99"]),
                              "id do índice no lugar do curto": redator(resposta="Resposta inventada.", referencias=["TRECHO-1"]),
                              "um id válido e um inventado": redator(resposta="Resposta inventada.", referencias=["T1", "T9"])}.items():
            with self.subTest(rotulo=rotulo):
                pilha = Pilha([PLANO, saida])
                erro = erro_chat(self, pilha.perguntar, lc.RESPOSTA_NAO_VERIFICADA, "referencia_desconhecida")
                self.assertNotIn("inventada", f"{erro} {erro.mensagem} {erro.causa}")
                self.assertEqual(pilha.estado_final(), "falhou")
        pilha = Pilha([PLANO, redator(lp.DOCUMENTADA, "Resposta sem fonte.", referencias=[])])
        erro_chat(self, pilha.perguntar, lc.RESPOSTA_NAO_VERIFICADA)

    def test_trecho_fora_do_perfil_interrompe_a_execucao_antes_da_redacao(self):
        pilha = Pilha([PLANO, redator()], indice=IndiceQueIgnoraOFiltro())
        erro_chat(self, lambda: pilha.perguntar(papeis=(la.PAPEL_CORRETOR,)), lc.INDISPONIVEL, "resultado_fora_do_perfil")
        self.assertEqual(len(pilha.transporte.pedidos), 1, "só o planejamento chegou ao modelo")
        self.assertEqual(pilha.transporte.de_redacao(), [])
        enviado = json.dumps(pilha.transporte.pedidos)
        for classe in ("atendimento", "interno-desconhecido", None):
            self.assertNotIn(MARCADORES[classe], enviado)

    def test_conflito_de_versoes_e_trechos_incoerentes_falham_antes_da_redacao(self):
        casos = {
            "duas versões do mesmo documento": ([trecho_de("A-1", "VLAR-CG-1.0", "1.0"), trecho_de("A-2", "VLAR-CG-2.0", "2.0")],
                                                "conflito_de_versoes"),
            "versão que contradiz o documento": ([trecho_de("A-1", "VLAR-CG-1.0", "2.0")], "versao_incoerente"),
            "documento fora do formato": ([trecho_de("A-1", "documento minúsculo", "1.0")], "trecho_invalido"),
            "conteúdo vazio": ([trecho_de("A-1", "VLAR-CG-1.0", "1.0", conteudo="   ")], "trecho_invalido"),
            "trecho acima do limite": ([trecho_de("A-1", "VLAR-CG-1.0", "1.0", conteudo="palavra " * 1000)], "trecho_acima_do_limite"),
        }
        for rotulo, (trechos, causa) in casos.items():
            with self.subTest(rotulo=rotulo):
                pilha = Pilha([PLANO, redator()], trechos=trechos)
                erro_chat(self, pilha.perguntar, lc.RESPOSTA_NAO_VERIFICADA, causa)
                self.assertEqual(pilha.transporte.de_redacao(), [], "o redator não foi chamado")
                self.assertIn(("verificacao", "falhou"), pilha.etapas())
        versoes_iguais = Pilha([PLANO, redator()], trechos=[trecho_de("A-1", "VLAR-CG-1.0", "1.0"), trecho_de("A-2", "VLAR-GL-1.0", "1.0")])
        self.assertEqual(versoes_iguais.perguntar().situacao, lp.RESPONDIDA)

    def test_o_mesmo_trecho_com_conteudo_diferente_em_duas_consultas_e_divergencia(self):
        class IndiceInstavel(IndiceAcessoFalso):
            def consultar(self, texto, vetor, k, filtro=None):
                resultados = super().consultar(texto, vetor, k, filtro)
                if texto == "franquia":
                    resultados = [{**item, "conteudo": item["conteudo"] + " Texto diferente."} for item in resultados]
                return resultados

        pilha = Pilha([PLANO, redator()], indice=IndiceInstavel(trechos=TRECHOS))
        erro_chat(self, pilha.perguntar, lc.RESPOSTA_NAO_VERIFICADA, "trecho_divergente")
        self.assertEqual(pilha.transporte.de_redacao(), [])

    def test_a_mesclagem_intercala_as_consultas_sem_repetir_ids_e_respeita_o_limite(self):
        def t(numero, consulta):
            return lo.TrechoRecuperado.de_resultado(trecho_de(f"A-{numero}", f"DOC-{numero}", "1.0"), consulta)

        mesclados = lo.mesclar_resultados([[t(1, 1), t(2, 1), t(3, 1)], [t(1, 2), t(4, 2), t(5, 2)]], limite=4)
        self.assertEqual([trecho.id for trecho in mesclados], ["A-1", "A-2", "A-4", "A-3"])
        self.assertEqual(lo.mesclar_resultados([[], []]), ())

    def test_sem_trechos_o_redator_nao_e_chamado_e_vale_a_recusa_da_politica(self):
        pilha = Pilha([PLANO, redator()], trechos=[])
        resposta = pilha.perguntar()
        self.assertEqual((resposta.tipo, resposta.situacao, resposta.texto, resposta.evidencias),
                         (lp.SEM_EVIDENCIA, lp.RECUSADA, lp.MENSAGEM_SEM_EVIDENCIA, ()))
        self.assertEqual(len(pilha.transporte.pedidos), 1)
        self.assertEqual(pilha.transporte.de_redacao(), [])
        self.assertIsNotNone(resposta.uso, "o planejamento e a busca foram pagos e informaram o uso")
        self.assertGreater(resposta.uso.tokens_entrada, 0)
        self.assertEqual(pilha.etapas()[-2:], [("redacao", "ignorada"), ("politica", "ignorada")])

    def test_contratacao_individual_conserva_o_texto_e_o_aviso_fixos_da_politica(self):
        for tipo_do_modelo in (lp.DOCUMENTADA, lp.CONTRATACAO_INDIVIDUAL):
            with self.subTest(tipo_do_modelo=tipo_do_modelo):
                pilha = Pilha([PLANO, redator(tipo_do_modelo, "Sim, o seu seguro cobre e vai pagar tudo.")])
                resposta = pilha.perguntar(PERGUNTA_INDIVIDUAL)
                self.assertEqual((resposta.tipo, resposta.texto, resposta.aviso),
                                 (lp.CONTRATACAO_INDIVIDUAL, lp.TEXTO_SEM_VEREDITO, lp.AVISO_CONTRATACAO_INDIVIDUAL))
                self.assertTrue(resposta.evidencias)
                self.assertNotIn("vai pagar", json.dumps(resposta.a_dict(), ensure_ascii=False))

    def test_a_resposta_publica_e_a_do_chat_convencional_para_o_mesmo_contexto(self):
        geracao = OpenAIGeracaoFalso()
        geracao.responder = lambda argumentos: {"tipo": lp.DOCUMENTADA, "resposta": "Resposta de teste.",
                                                "referencias": OpenAIGeracaoFalso.ids_recebidos(argumentos["input"])[:1]}
        indice = IndiceAcessoFalso(trechos=TRECHOS)
        convencional = lc.ServicoRag(lg.Recuperador(indice, li.ClienteEmbeddings(OpenAIFalso(dimensoes=DIMENSOES), "embeddings", DIMENSOES),
                                                    exigir_filtro=True),
                                     lg.ClienteGeracao(geracao, "geracao", MODELOS), "hibrida", 6, exigir_acesso=True)
        esperada = convencional.perguntar(PERGUNTA, la.autorizar(ATENDIMENTO))
        pilha = Pilha([PLANO, redator()])
        obtida = pilha.perguntar()
        publica = lambda resposta: {campo: valor for campo, valor in resposta.a_dict().items() if campo != "uso"}  # noqa: E731
        self.assertEqual(publica(obtida), publica(esperada), "mesmo contrato público, mesmas citações, mesma política")
        self.assertEqual(set(obtida.a_dict()), set(esperada.a_dict()))
        pedido_do_redator = pilha.transporte.de_redacao()[0]
        self.assertEqual(pedido_do_redator["instructions"], geracao.chamadas[0]["instructions"])
        self.assertEqual(ServicoRespostasFalso.texto_recebido(pedido_do_redator), geracao.chamadas[0]["input"],
                         "o redator recebe o mesmo pedido que o gerador do chat convencional")

    def test_duas_execucoes_ao_mesmo_tempo_nao_misturam_perfis_agentes_nem_orcamentos(self):
        for rodada in range(3):
            with self.subTest(rodada=rodada):
                barreira = threading.Barrier(2, timeout=10)
                indice = IndiceAcessoFalso(ao_consultar=lambda classes: barreira.wait())
                pilha = Pilha(responder=responder_padrao(), indice=indice)
                fluxos = []
                original = lo.construir_workflow

                def espiar(nucleo):
                    fluxo = original(nucleo)
                    fluxos.append((fluxo, nucleo))
                    return fluxo

                with mock.patch.object(lo, "construir_workflow", espiar), ThreadPoolExecutor(2) as pool:
                    atendimento = pool.submit(pilha.perguntar, PERGUNTA, (la.PAPEL_ATENDIMENTO,))
                    corretor = pool.submit(pilha.perguntar, PERGUNTA, (la.PAPEL_CORRETOR,))
                    respostas = {"atendimento": atendimento.result(timeout=30), "corretor": corretor.result(timeout=30)}
                proibidas = {"atendimento": {"TRECHO-3"}, "corretor": {"TRECHO-2"}}
                permitidas = {"atendimento": {"TRECHO-1", "TRECHO-2"}, "corretor": {"TRECHO-1", "TRECHO-3"}}
                for perfil, resposta in respostas.items():
                    ids = {evidencia.id for evidencia in resposta.evidencias}
                    self.assertTrue(ids and ids <= permitidas[perfil] and not ids & proibidas[perfil], perfil)
                por_marcador = {}
                for pedido in pilha.transporte.de_redacao():
                    texto = ServicoRespostasFalso.texto_recebido(pedido)
                    visiveis = [classe for classe in ("atendimento", "corretor") if MARCADORES[classe] in texto]
                    self.assertEqual(len(visiveis), 1, "cada pedido ao modelo traz a classe restrita de uma só pessoa")
                    por_marcador[visiveis[0]] = texto
                self.assertEqual(set(por_marcador), {"atendimento", "corretor"})
                filtros = sorted({consulta["filtro"] for consulta in indice.consultas})
                self.assertEqual(filtros, sorted(la.autorizar(papeis).filtro for papeis in ((la.PAPEL_ATENDIMENTO,), (la.PAPEL_CORRETOR,))))
                self.assertEqual(len(fluxos), 2)
                (fluxo_a, nucleo_a), (fluxo_b, nucleo_b) = fluxos
                self.assertIsNot(fluxo_a, fluxo_b)
                self.assertIsNot(nucleo_a.orcamento, nucleo_b.orcamento)
                self.assertIsNot(nucleo_a.chamador, nucleo_b.chamador)
                self.assertNotEqual(nucleo_a.acesso.filtro, nucleo_b.acesso.filtro)
                self.assertEqual(len(pilha.clientes), 2, "um cliente de modelos por execução")
                self.assertEqual(vars(pilha.servico).keys(), {"parametros", "indice", "embeddings", "fabrica_cliente", "disjuntor", "relogio"},
                                 "o serviço só guarda clientes, parâmetros e disjuntor")

    def test_nada_do_que_a_pessoa_perguntou_fica_no_servico_depois_da_consulta(self):
        pilha = Pilha([PLANO, redator(), PLANO, redator()])
        pilha.perguntar("MARCADOR-ALFA pergunta anterior")
        pilha.perguntar("MARCADOR-BETA pergunta atual")
        segunda = ServicoRespostasFalso.texto_recebido(pilha.transporte.pedidos[2]) + ServicoRespostasFalso.texto_recebido(pilha.transporte.pedidos[3])
        self.assertNotIn("MARCADOR-ALFA", segunda)
        self.assertIn("MARCADOR-BETA", segunda)
        self.assertNotIn("ALFA", repr(vars(pilha.servico)) + repr(vars(pilha.servico.disjuntor)))


class SimpleContexto:
    """Parece um contexto de acesso (tem papéis, classes e filtro), mas não foi criado por `autorizar`."""

    papeis, classes, filtro = (la.PAPEL_ATENDIMENTO,), ("compartilhado", "atendimento"), la.autorizar(ATENDIMENTO).filtro


# --------------------------------------------------------------------------------------
# Limites, orçamento, contingência
# --------------------------------------------------------------------------------------

class ContingenciaELimitesTests(TesteComLimite):
    def test_429_e_503_usam_a_contingencia_e_toda_tentativa_que_falhou_e_contada(self):
        pilha = Pilha([("http", 429), PLANO, ("http", 503), redator()])
        resposta = pilha.perguntar()
        self.assertEqual(resposta.situacao, lp.RESPONDIDA)
        self.assertEqual(pilha.modelos_usados(), ["geracao", CONTINGENCIA, "geracao", CONTINGENCIA])
        resumo = pilha.resumo()
        self.assertEqual((resumo["chamadas_modelo"], resumo["tentativas_falhas"], resumo["contingencia"]), (4, 2, True))
        self.assertEqual(resumo["chamadas_modelo"], len(pilha.transporte.pedidos), "contadas = recebidas pelo transporte (sem repetições escondidas)")
        self.assertEqual(resumo["chamadas_total"], 4 + 2 + 2)
        tentativas = [(evento.etapa, evento.estado, evento.dados["deployment"], evento.dados.get("causa"))
                      for evento in pilha.eventos if evento.tipo == lo.EVENTO_TENTATIVA]
        self.assertEqual(tentativas, [("planejamento", "falha_transitoria", "primario", "limite_do_servico"),
                                      ("planejamento", "ok", "contingencia", None),
                                      ("redacao", "falha_transitoria", "primario", "servico"), ("redacao", "ok", "contingencia", None)])
        self.assertTrue(resumo["uso_incerto"])
        self.assertIsNone(resposta.uso, "uma tentativa falha pode ter consumido: o uso não vira zero nem total completo")
        self.assertGreater(resumo["tokens_comprometidos"], resumo["tokens_entrada"] + resumo["tokens_saida"], "a reserva das falhas fica comprometida")
        self.assertNotIn(SEGREDO, json.dumps([evento.a_dict() for evento in pilha.eventos]))

    def test_a_contingencia_so_troca_o_deployment_e_nao_muda_filtro_identidade_nem_pedido(self):
        pilha = Pilha([("http", 503), PLANO, redator()])
        pilha.perguntar()
        primario, contingencia = pilha.transporte.pedidos[:2]
        self.assertEqual((primario["model"], contingencia["model"]), ("geracao", CONTINGENCIA))
        self.assertEqual({**primario, "model": None}, {**contingencia, "model": None})
        self.assertEqual({consulta["filtro"] for consulta in pilha.indice.consultas}, {la.autorizar(ATENDIMENTO).filtro})

    def test_rede_e_tempo_esgotado_do_servico_tambem_sao_transitorios(self):
        for passo, causa in ((("rede",), "rede"), (("tempo",), "tempo_esgotado")):
            with self.subTest(passo=passo[0]):
                pilha = Pilha([passo, PLANO, redator()])
                self.assertEqual(pilha.perguntar().situacao, lp.RESPONDIDA)
                self.assertEqual(pilha.modelos_usados()[:2], ["geracao", CONTINGENCIA])
                falha = next(evento for evento in pilha.eventos if evento.estado == "falha_transitoria")
                self.assertEqual(falha.dados["causa"], causa)

    def test_o_tempo_por_chamada_acaba_a_espera_e_a_contingencia_assume(self):
        faixas = dict(lo.FAIXAS_DOS_LIMITES, tempo_por_chamada_s=(0.2, 120.0))
        with mock.patch.object(lo, "FAIXAS_DOS_LIMITES", MappingProxyType(faixas)):
            pilha = Pilha([("lento", 5), PLANO, redator()], limites=lo.LimitesCoordenacao(tempo_por_chamada_s=0.5))
            inicio = time.monotonic()
            resposta = pilha.perguntar()
        self.assertLess(time.monotonic() - inicio, 3, "o programa para de esperar no tempo da chamada, não no do serviço")
        self.assertEqual((resposta.situacao, pilha.modelos_usados()[:2]), (lp.RESPONDIDA, ["geracao", CONTINGENCIA]))
        self.assertEqual(next(e for e in pilha.eventos if e.estado == "falha_transitoria").dados["causa"], "tempo_esgotado")

    def test_acesso_negado_deployment_ausente_pedido_recusado_e_formato_nao_usam_a_contingencia(self):
        casos = {"401": (("http", 401), lc.INDISPONIVEL, "acesso_negado"), "403": (("http", 403), lc.INDISPONIVEL, "acesso_negado"),
                 "404": (("http", 404), lc.INDISPONIVEL, "nao_encontrado"), "400": (("http", 400), lc.INDISPONIVEL, "requisicao_recusada"),
                 "422": (("http", 422), lc.INDISPONIVEL, "requisicao_recusada"),
                 "filtro de conteúdo": (("http", 400, "content_filter"), lc.PERGUNTA_BLOQUEADA, "filtro_de_conteudo"),
                 "saída fora do formato": ("isto não é JSON", lc.RESPOSTA_NAO_VERIFICADA, "formato_do_modelo"),
                 "saída sem os campos": ({"consulta_principal": "x"}, lc.RESPOSTA_NAO_VERIFICADA, "formato_do_modelo"),
                 "saída truncada": (("incompleto",), lc.RESPOSTA_NAO_VERIFICADA, "saida_truncada")}
        for rotulo, (passo, codigo, causa) in casos.items():
            with self.subTest(rotulo=rotulo):
                pilha = Pilha([passo, PLANO, redator()])
                erro = erro_chat(self, pilha.perguntar, codigo, causa)
                self.assertEqual(pilha.modelos_usados(), ["geracao"], "um único pedido, no deployment principal: sem contingência")
                self.assertNotIn(SEGREDO, f"{erro} {erro.mensagem}")
                self.assertEqual(pilha.resumo()["contingencia"], False)
                self.assertEqual(pilha.indice.consultas, [])

    def test_sem_contingencia_configurada_a_falha_transitoria_termina_a_consulta(self):
        pilha = Pilha([("http", 503), PLANO], contingencia=None)
        erro_chat(self, pilha.perguntar, lc.INDISPONIVEL, "servico")
        self.assertEqual(pilha.modelos_usados(), ["geracao"])

    def test_se_a_contingencia_tambem_falha_o_erro_e_o_da_ultima_tentativa_e_ambas_contam(self):
        pilha = Pilha([("http", 429), ("http", 503)])
        erro_chat(self, pilha.perguntar, lc.INDISPONIVEL, "servico")
        self.assertEqual((pilha.resumo()["chamadas_modelo"], pilha.resumo()["tentativas_falhas"]), (2, 2))
        self.assertEqual(len(pilha.transporte.pedidos), 2)

    def test_o_limite_de_tentativas_de_geracao_inclui_falhas_e_contingencia(self):
        pilha = Pilha([("http", 429), PLANO, redator()], limites=lo.LimitesCoordenacao(max_chamadas_modelo=2))
        erro_chat(self, pilha.perguntar, lc.INDISPONIVEL, lo.CAUSA_LIMITE_DE_CHAMADAS)
        self.assertEqual(pilha.modelos_usados(), ["geracao", CONTINGENCIA], "a redação não saiu: as 2 tentativas já foram gastas")
        self.assertEqual(pilha.resumo()["chamadas_modelo"], 2)



    def test_o_limite_de_chamadas_totais_reduz_as_buscas_e_nunca_e_ultrapassado(self):
        pilha = Pilha([PLANO, redator()], limites=lo.LimitesCoordenacao(max_chamadas=4))
        resposta = pilha.perguntar()
        self.assertEqual(resposta.situacao, lp.RESPONDIDA)
        self.assertEqual(len(pilha.indice.consultas), 1, "só uma busca cabe: planejamento, embedding, busca e redação")
        resumo = pilha.resumo()
        self.assertEqual((resumo["chamadas_total"], resumo["buscas"]), (4, 1))
        recuperacao = next(evento for evento in pilha.eventos if evento.etapa == "recuperacao" and evento.estado == "concluida")
        self.assertEqual(recuperacao.dados["consultas_descartadas"], 1)

    def test_o_limite_de_buscas_vale_mesmo_com_um_plano_de_duas_consultas(self):
        pilha = Pilha([PLANO, redator()], limites=lo.LimitesCoordenacao(max_buscas=1))
        pilha.perguntar()
        self.assertEqual((len(pilha.indice.consultas), pilha.openai.textos_enviados), (1, 1))

    def test_o_orcamento_recusa_a_chamada_que_passaria_do_limite_antes_de_enviar(self):
        orcamento = lo.Orcamento(lo.LimitesCoordenacao(max_chamadas=4, max_buscas=1), prazo_s=60, modo_busca="hibrida")
        orcamento.autorizar_embeddings()
        orcamento.autorizar_busca()
        for chamada in (orcamento.autorizar_embeddings, orcamento.autorizar_busca):
            with self.assertRaises(lc.ErroChat) as erro:
                chamada()
            self.assertEqual(erro.exception.causa, lo.CAUSA_LIMITE_DE_BUSCAS, "o embedding só existe para a busca que vem depois")
        orcamento.autorizar_modelo(10, 10)
        orcamento.autorizar_modelo(10, 10)
        with self.assertRaises(lc.ErroChat) as erro:
            orcamento.autorizar_modelo(10, 10)
        self.assertEqual(erro.exception.causa, lo.CAUSA_LIMITE_DE_CHAMADAS)
        self.assertEqual((orcamento.chamadas_total, orcamento.chamadas_modelo), (4, 2), "a recusada não foi contada")

    def test_orcamento_de_tokens_insuficiente_impede_a_proxima_chamada(self):
        pilha = Pilha([PLANO, redator()], limites=lo.LimitesCoordenacao(max_tokens=lo.FAIXAS_DOS_LIMITES["max_tokens"][0]))
        erro_chat(self, pilha.perguntar, lc.INDISPONIVEL, lo.CAUSA_ORCAMENTO_DE_TOKENS)
        self.assertEqual(pilha.modelos_usados(), ["geracao"], "a redação não foi enviada")
        self.assertEqual(len(pilha.indice.consultas), 2, "a recuperação já tinha acontecido")
        self.assertEqual(pilha.estado_final(), "falhou")

    def test_uso_nao_informado_fica_incerto_reserva_o_pior_caso_e_bloqueia_chamadas_que_estourariam(self):
        incerto = Pilha([("sem_uso", PLANO), redator()])
        resposta = incerto.perguntar()
        resumo = incerto.resumo()
        self.assertEqual(resposta.situacao, lp.RESPONDIDA)
        self.assertTrue(resumo["uso_incerto"])
        self.assertIsNone(resposta.uso, "uso indisponível não vira zero nem sucesso")
        self.assertGreater(resumo["tokens_comprometidos"], resumo["tokens_entrada"] + resumo["tokens_saida"])
        self.assertGreater(resumo["tokens_entrada"], 0, "o que foi informado (só a redação) fica registrado como mínimo")
        # Um limite que cabe se o planejamento tivesse informado o uso, mas não com a reserva do pior caso: a redação não sai.
        planejamento = lo.estimar_tokens(lo.INSTRUCOES_DO_PLANEJADOR, lo.entrada_do_planejador(PERGUNTA),
                                         json.dumps(lo.CONTRATO_DO_PLANO.esquema, ensure_ascii=False)) + 1000
        pedido, contrato = lc.pedido_de_referencias(PERGUNTA, [TRECHOS[0], TRECHOS[1]])
        redacao = lo.estimar_tokens(pedido.instrucoes, pedido.entrada, json.dumps(contrato.esquema, ensure_ascii=False)) + 3000
        uso_do_planejamento = 300  # folga sobre o que o dublê informa (entrada pequena e 40 de saída)
        limite = uso_do_planejamento + redacao
        self.assertLess(limite, planejamento + redacao, "premissa: a reserva do planejamento é maior que o uso informado")
        informado = Pilha([PLANO, redator()], limites=lo.LimitesCoordenacao(max_tokens=limite))
        self.assertEqual(informado.perguntar().situacao, lp.RESPONDIDA)
        apertada = Pilha([("sem_uso", PLANO), redator()], limites=lo.LimitesCoordenacao(max_tokens=limite))
        erro_chat(self, apertada.perguntar, lc.INDISPONIVEL, lo.CAUSA_ORCAMENTO_DE_TOKENS)
        self.assertEqual(apertada.modelos_usados(), ["geracao"], "a redação não foi enviada: a reserva do pior caso a bloqueou")

    def test_tokens_de_raciocinio_ja_estao_na_saida_e_nao_sao_somados_duas_vezes(self):
        pilha = Pilha([PLANO, redator()])
        resposta = pilha.perguntar()
        resumo = pilha.resumo()
        self.assertEqual((resumo["tokens_saida"], resumo["tokens_raciocinio"]), (80, 20))
        self.assertEqual(resumo["tokens_comprometidos"], resumo["tokens_entrada"] + resumo["tokens_saida"])
        self.assertEqual((resposta.uso.tokens_saida, resposta.uso.tokens_raciocinio), (80, 20))
        for incoerente in ({"input_token_count": 5, "output_token_count": 3, "reasoning_output_token_count": 9},
                           {"input_token_count": -1, "output_token_count": 3}, {"input_token_count": 5}, {}, None,
                           {"input_token_count": True, "output_token_count": 3}):
            self.assertIsNone(lo.uso_do_modelo(mock.Mock(usage_details=incoerente)), incoerente)
        self.assertEqual(lo.uso_do_modelo(mock.Mock(usage_details={"input_token_count": 5, "output_token_count": 3})), lo.UsoModelo(5, 3, 0))

    def test_o_prazo_impede_as_proximas_etapas(self):
        relogio = Relogio()

        def planejar_e_gastar(tempo):
            def passo(pedido):
                relogio.avancar(tempo)
                return PLANO

            return passo

        gastou_tudo = Pilha([planejar_e_gastar(100), redator()], relogio=relogio)
        erro_chat(self, gastou_tudo.perguntar, lc.INDISPONIVEL, lo.CAUSA_TEMPO_ESGOTADO)
        self.assertEqual((len(gastou_tudo.transporte.pedidos), gastou_tudo.openai.chamadas, gastou_tudo.indice.consultas), (1, [], []))
        sobrou_pouco = Pilha([planejar_e_gastar(86.5), redator()], relogio=relogio)
        relogio.agora = 1000.0
        erro_chat(self, sobrou_pouco.perguntar, lc.INDISPONIVEL, lo.CAUSA_PRAZO_INSUFICIENTE)
        self.assertEqual((len(sobrou_pouco.transporte.pedidos), sobrou_pouco.openai.chamadas, sobrou_pouco.indice.consultas), (1, [], []))

    def test_o_prazo_impede_a_contingencia_depois_de_uma_falha(self):
        relogio = Relogio()

        def falhar_e_gastar(pedido):
            relogio.avancar(86.5)
            return ("http", 503)

        pilha = Pilha([falhar_e_gastar, PLANO], relogio=relogio)
        erro_chat(self, pilha.perguntar, lc.INDISPONIVEL, lo.CAUSA_PRAZO_INSUFICIENTE)
        self.assertEqual(pilha.modelos_usados(), ["geracao"], "sobraram menos de 3 s: a contingência não saiu")

    def test_o_disjuntor_pula_o_deployment_que_falhou_e_so_volta_depois_da_pausa(self):
        relogio = Relogio()
        disjuntor = lo.Disjuntor(limiar=2, pausa_s=30, relogio=relogio)
        self.assertTrue(disjuntor.permite("a"))
        disjuntor.falha("a")
        self.assertEqual(disjuntor.estado("a"), "fechado")
        disjuntor.falha("a")
        self.assertEqual((disjuntor.estado("a"), disjuntor.permite("a")), ("aberto", False))
        self.assertTrue(disjuntor.permite("b"), "um deployment não afeta o outro")
        relogio.avancar(31)
        self.assertEqual(disjuntor.estado("a"), "semiaberto")
        self.assertTrue(disjuntor.permite("a"), "uma única tentativa de teste")
        self.assertFalse(disjuntor.permite("a"))
        disjuntor.falha("a")
        self.assertEqual((disjuntor.estado("a"), disjuntor.permite("a")), ("aberto", False), "o teste falhou: a pausa recomeça")
        relogio.avancar(31)
        self.assertTrue(disjuntor.permite("a"))
        disjuntor.sucesso("a")
        self.assertEqual((disjuntor.estado("a"), disjuntor.permite("a")), ("fechado", True))
        for invalido in ((0, 30), (2, 0), (2, float("inf"))):
            with self.assertRaises(ValueError):
                lo.Disjuntor(*invalido)

    def test_com_o_disjuntor_aberto_o_principal_e_pulado_sem_gastar_tentativa(self):
        relogio = Relogio()
        disjuntor = lo.Disjuntor(limiar=2, pausa_s=30, relogio=relogio)
        primeira = Pilha([("http", 503), PLANO, ("http", 503), redator()], disjuntor=disjuntor, relogio=relogio)
        primeira.perguntar()
        self.assertEqual(disjuntor.estado("geracao"), "aberto")
        segunda = Pilha([PLANO, redator()], disjuntor=disjuntor, relogio=relogio)
        segunda.perguntar()
        self.assertEqual(segunda.modelos_usados(), [CONTINGENCIA, CONTINGENCIA], "o principal foi pulado: nenhum pedido a ele")
        self.assertEqual(segunda.resumo()["chamadas_modelo"], 2)
        puladas = [evento for evento in segunda.eventos if evento.estado == "pulada"]
        self.assertEqual([evento.dados["causa"] for evento in puladas], ["circuito_aberto", "circuito_aberto"])
        relogio.avancar(31)
        terceira = Pilha([PLANO, redator()], disjuntor=disjuntor, relogio=relogio)
        terceira.perguntar()
        self.assertEqual(terceira.modelos_usados(), ["geracao", "geracao"], "passada a pausa, o principal recebe a tentativa de teste")
        self.assertEqual(disjuntor.estado("geracao"), "fechado")

    def test_com_os_dois_disjuntores_abertos_nada_e_enviado(self):
        relogio = Relogio()
        disjuntor = lo.Disjuntor(limiar=1, pausa_s=30, relogio=relogio)
        disjuntor.falha("geracao")
        disjuntor.falha(CONTINGENCIA)
        pilha = Pilha([PLANO], disjuntor=disjuntor, relogio=relogio)
        erro_chat(self, pilha.perguntar, lc.INDISPONIVEL, lo.CAUSA_CIRCUITO_ABERTO)
        self.assertEqual(pilha.transporte.pedidos, [])
        self.assertEqual(pilha.resumo()["chamadas_modelo"], 0)

    def test_erro_de_acesso_nao_abre_o_disjuntor(self):
        disjuntor = lo.Disjuntor(limiar=1, pausa_s=30)
        for _ in range(3):
            pilha = Pilha([("http", 403)], disjuntor=disjuntor)
            erro_chat(self, pilha.perguntar, lc.INDISPONIVEL, "acesso_negado")
        self.assertEqual(disjuntor.estado("geracao"), "fechado")

    def test_a_falha_dos_embeddings_ou_da_busca_nao_tem_contingencia_e_vira_codigo_publico(self):
        pilha = Pilha([PLANO, redator()])
        pilha.openai.erro = support_erro("RateLimitError", 429)
        erro_chat(self, pilha.perguntar, lc.INDISPONIVEL, "limite_do_servico")
        self.assertEqual((len(pilha.transporte.pedidos), pilha.openai.textos_enviados), (1, 1), "uma tentativa de embedding, sem repetição")
        self.assertEqual(pilha.resumo()["chamadas_embeddings"], 1)

        class IndiceQuebrado(IndiceAcessoFalso):
            def consultar(self, texto, vetor, k, filtro=None):
                raise RuntimeError(SEGREDO)

        quebrado = Pilha([PLANO, redator()], indice=IndiceQuebrado())
        erro = erro_chat(self, quebrado.perguntar, lc.ERRO_INTERNO, "inesperado")
        self.assertNotIn(SEGREDO, f"{erro} {erro.mensagem}")
        self.assertEqual(quebrado.transporte.de_redacao(), [])


def support_erro(nome, status):
    return support.erro_openai(nome, status, SEGREDO)


# --------------------------------------------------------------------------------------
# Cancelamento e progresso
# --------------------------------------------------------------------------------------

class CancelamentoEProgressoTests(TesteComLimite):
    def test_cancelado_antes_de_comecar_nada_e_chamado(self):
        pilha = Pilha([PLANO, redator()])
        sinal = threading.Event()
        sinal.set()
        erro_chat(self, lambda: pilha.perguntar(cancelar=sinal), lc.CANCELADO, "cancelado")
        self.assertTrue(pilha.sem_chamadas())
        self.assertEqual(pilha.clientes, [])

    def test_cancelar_durante_o_planejamento_interrompe_a_espera_e_as_proximas_etapas(self):
        pilha = Pilha([("lento", 10, PLANO), redator()])
        sinal = threading.Event()
        threading.Timer(0.4, sinal.set).start()
        inicio = time.monotonic()
        erro_chat(self, lambda: pilha.perguntar(cancelar=sinal), lc.CANCELADO, "cancelado")
        self.assertLess(time.monotonic() - inicio, 5, "o programa deixa de esperar, não espera os 10 s do serviço")
        self.assertEqual(len(pilha.transporte.pedidos), 1, "o pedido já enviado saiu; nada depois dele")
        self.assertEqual((pilha.openai.chamadas, pilha.indice.consultas, pilha.transporte.de_redacao()), ([], [], []))
        self.assertEqual(pilha.estado_final(), "cancelada")
        self.assertEqual([etapa for etapa, estado in pilha.etapas() if estado == "iniciada"], ["planejamento"])
        resumo = pilha.resumo()
        self.assertEqual((resumo["chamadas_modelo"], resumo["tentativas_falhas"], resumo["uso_incerto"]), (1, 1, True),
                         "a tentativa enviada conta, e o consumo dela é incerto")

    def test_cancelar_durante_a_recuperacao_impede_a_redacao(self):
        sinal = threading.Event()

        def buscar_e_cancelar(classes):
            sinal.set()

        pilha = Pilha([PLANO, redator()], indice=IndiceAcessoFalso(ao_consultar=buscar_e_cancelar))
        erro_chat(self, lambda: pilha.perguntar(cancelar=sinal), lc.CANCELADO)
        self.assertEqual(len(pilha.transporte.pedidos), 1)
        self.assertEqual(len(pilha.indice.consultas), 1, "a segunda consulta não saiu")
        self.assertEqual(pilha.transporte.de_redacao(), [])
        self.assertNotIn(("politica", "iniciada"), pilha.etapas())

    def test_cancelar_com_o_pedido_de_embeddings_em_andamento_deixa_o_uso_incerto_e_nao_envia_a_busca(self):
        """O evento 'recuperacao iniciada' chega depois de o pedido de embeddings já ter saído: cancelar nele não impede esse pedido.
        O pedido abandonado pode ter consumido tokens, e o resumo tem de dizer isso mesmo antes de a resposta dele chegar."""
        saiu, liberar, sinal = threading.Event(), threading.Event(), threading.Event()
        self.addCleanup(liberar.set)  # mesmo se uma asserção falhar, o pedido abandonado termina

        class EmbeddingsQueEspera:
            def __init__(self, base):
                self.base = base

            def gerar(self, textos):
                saiu.set()
                liberar.wait(15)
                return self.base.gerar(textos)

        pilha = Pilha([PLANO, redator()])
        pilha.servico.embeddings = EmbeddingsQueEspera(pilha.servico.embeddings)
        threading.Thread(target=lambda: (saiu.wait(10), sinal.set()), daemon=True).start()
        inicio = time.monotonic()
        erro_chat(self, lambda: pilha.perguntar(cancelar=sinal), lc.CANCELADO, "cancelado")
        self.assertLess(time.monotonic() - inicio, 5, "o programa deixa de esperar o pedido abandonado")
        resumo = pilha.resumo()
        self.assertEqual((resumo["chamadas_modelo"], resumo["chamadas_embeddings"], resumo["buscas"]), (1, 1, 0))
        self.assertTrue(resumo["uso_incerto"], "o pedido de embeddings enviado e abandonado pode ter consumido tokens")
        self.assertEqual(pilha.estado_final(), "cancelada")
        liberar.set()  # o pedido abandonado termina sozinho, e nada é enviado depois do cancelamento
        self.assertTrue(esperar_ate(lambda: not threads_do_pool(), 10), "a thread do pedido abandonado terminou")
        self.assertEqual((pilha.indice.consultas, pilha.transporte.de_redacao()), ([], []))

    def test_cancelado_na_hora_de_responder_nenhuma_resposta_sai_mesmo_pronta(self):
        sinal = threading.Event()

        def redigir_e_cancelar(pedido):
            sinal.set()
            return redator()(pedido)

        pilha = Pilha([PLANO, redigir_e_cancelar])
        erro_chat(self, lambda: pilha.perguntar(cancelar=sinal), lc.CANCELADO)
        self.assertEqual(len(pilha.transporte.pedidos), 2)
        self.assertEqual(pilha.estado_final(), "cancelada")

    def test_cancelar_uma_execucao_nao_cancela_a_outra(self):
        def responder(pedido):
            lenta = "EXECUCAO-LENTA" in ServicoRespostasFalso.texto_recebido(pedido)
            passo = responder_padrao()(pedido)
            return ("lento", 10, passo) if lenta else passo

        pilha = Pilha(responder=responder)
        cancelada, normal = threading.Event(), threading.Event()
        threading.Timer(0.5, cancelada.set).start()
        with ThreadPoolExecutor(2) as pool:
            primeira = pool.submit(pilha.perguntar, "EXECUCAO-LENTA " + PERGUNTA, ATENDIMENTO, cancelar=cancelada)
            segunda = pool.submit(pilha.perguntar, "EXECUCAO-NORMAL " + PERGUNTA, ATENDIMENTO, cancelar=normal)
            self.assertEqual(segunda.result(timeout=30).situacao, lp.RESPONDIDA)
            with self.assertRaises(lc.ErroChat) as erro:
                primeira.result(timeout=30)
        self.assertEqual(erro.exception.codigo, lc.CANCELADO)
        self.assertFalse(normal.is_set())
        estados = sorted(evento.estado for evento in pilha.eventos if evento.tipo == lo.EVENTO_RESUMO)
        self.assertEqual(estados, ["cancelada", "concluida"])

    def test_o_progresso_so_tem_vocabulario_fechado_e_contagens_e_nunca_conteudo(self):
        pilha = Pilha([PLANO, redator(resposta="TEXTO-DO-MODELO-QUE-SO-APARECE-NA-RESPOSTA")])
        pergunta = "PERGUNTA-SECRETA-DA-PESSOA " + PERGUNTA
        resposta = pilha.perguntar(pergunta)
        serializado = json.dumps([evento.a_dict() for evento in pilha.eventos], ensure_ascii=False)
        proibidos = (pergunta, "PERGUNTA-SECRETA", "TEXTO-DO-MODELO", "regra fictícia aviso", "franquia", TRECHOS[0]["conteudo"][:30],
                     "MARCADOR-", "Você prepara buscas", la.autorizar(ATENDIMENTO).filtro, BUSCA, MODELOS, "geracao", "T1", "TRECHO-1")
        for proibido in proibidos:
            self.assertNotIn(proibido, serializado)
        for evento in pilha.eventos:
            dados = evento.a_dict()
            self.assertEqual(set(dados), {"tipo", "etapa", "estado", "dados"})
            self.assertIn(dados["tipo"], lo.ESTADOS_DOS_EVENTOS)
            self.assertIn(dados["estado"], lo.ESTADOS_DOS_EVENTOS[dados["tipo"]])
            self.assertTrue(dados["etapa"] in lo.ETAPAS or (dados["tipo"] == lo.EVENTO_RESUMO and dados["etapa"] == ""))
            for nome, valor in dados["dados"].items():
                self.assertTrue(isinstance(valor, (int, bool)) or nome in {"deployment", "causa", "papel"}, nome)
        self.assertEqual(resposta.texto, "TEXTO-DO-MODELO-QUE-SO-APARECE-NA-RESPOSTA")

    def test_um_evento_fora_do_vocabulario_nao_existe(self):
        validos = lo.EventoProgresso(lo.EVENTO_ETAPA, "iniciada", "planejamento", {"consultas": 2, "contingencia": True})
        self.assertEqual(validos.a_dict()["dados"], {"consultas": 2, "contingencia": True})
        invalidos = [dict(tipo="outro", estado="iniciada"), dict(tipo="etapa", estado="falou", etapa="planejamento"),
                     dict(tipo="etapa", estado="iniciada", etapa="pergunta secreta"), dict(tipo="resumo", estado="concluida", etapa="redacao"),
                     dict(tipo="etapa", estado="iniciada", etapa="redacao", dados={"texto": "resposta do modelo"}),
                     dict(tipo="etapa", estado="iniciada", etapa="redacao", dados={"consultas": "duas"}),
                     dict(tipo="etapa", estado="iniciada", etapa="redacao", dados={"consultas": True}),
                     dict(tipo="etapa", estado="iniciada", etapa="redacao", dados={"consultas": -1}),
                     dict(tipo="tentativa", estado="ok", etapa="redacao", dados={"deployment": "geracao"}),
                     dict(tipo="tentativa", estado="falha", etapa="redacao", dados={"causa": "Texto livre: do erro"})]
        for argumentos in invalidos:
            with self.subTest(argumentos=argumentos), self.assertRaises(ValueError):
                lo.EventoProgresso(**argumentos)

    def test_um_acompanhante_que_falha_nao_derruba_a_consulta(self):
        pilha = Pilha([PLANO, redator()])

        def quebrado(evento):
            raise RuntimeError(SEGREDO)

        resposta = pilha.servico.perguntar(PERGUNTA, la.autorizar(ATENDIMENTO), progresso=quebrado)
        self.assertEqual(resposta.situacao, lp.RESPONDIDA)

    def test_o_resumo_sai_tambem_quando_a_consulta_falha(self):
        pilha = Pilha([("http", 403)])
        erro_chat(self, pilha.perguntar, lc.INDISPONIVEL, "acesso_negado")
        self.assertEqual(pilha.estado_final(), "falhou")
        self.assertEqual((pilha.resumo()["chamadas_modelo"], pilha.resumo()["uso_incerto"]), (1, True))
        self.assertIn(("planejamento", "falhou"), pilha.etapas())


# --------------------------------------------------------------------------------------
# HTTP: JSON, eventos de progresso e desconexão
# --------------------------------------------------------------------------------------

class ServicoCoordenadoFalso:
    """Um serviço coordenado de teste: entrega eventos prontos, pode esperar o cancelamento ou falhar. Registra cada chamada."""

    exige_acesso = True
    coordenado = True

    def __init__(self, eventos=(), resposta=None, erro=None, esperar=None):
        self.eventos, self.resposta, self.erro, self.esperar = list(eventos), resposta, erro, esperar
        self.chamadas, self.cancelamentos = [], []

    def perguntar(self, pergunta, acesso=None, *, progresso=None, cancelar=None):
        self.chamadas.append((pergunta, acesso))
        for evento in self.eventos:
            if progresso is not None:
                progresso(evento)
        if self.esperar is not None:
            self.esperar(pergunta, cancelar)
        if cancelar is not None and cancelar.is_set():
            self.cancelamentos.append(pergunta)
            raise lc.ErroChat(lc.CANCELADO, "cancelado")
        if self.erro is not None:
            raise self.erro
        return self.resposta(pergunta) if self.resposta else resposta_publica(pergunta)


def resposta_publica(pergunta):
    evidencia = lc.EvidenciaChat("VLAR-CG-1_0-004", "as coberturas adicionais são contratadas à parte", "vareleira-lar/condicoes-gerais-v1.0.md",
                                 "1.0", "Vareleira Lar — Condições Gerais", "3. Coberturas adicionais", "3.1")
    return lc.RespostaChat(lp.DOCUMENTADA, lp.RESPONDIDA, "Resposta pública de teste.", "", (evidencia,), lc.UsoChat(1, 2, 3, 4))


def eventos_de_etapa():
    resumo = {"chamadas_modelo": 2, "chamadas_embeddings": 2, "buscas": 2, "chamadas_total": 6, "tentativas_falhas": 0,
              "contingencia": False, "uso_incerto": False, "tokens_embeddings": 3, "tokens_entrada": 100, "tokens_saida": 20,
              "tokens_raciocinio": 5, "tokens_comprometidos": 120, "ms": 50}
    return [lo.EventoProgresso(lo.EVENTO_ETAPA, "iniciada", "planejamento", {"ms": 1}),
            lo.EventoProgresso(lo.EVENTO_TENTATIVA, "ok", "planejamento", {"deployment": "primario", "numero": 1, "ms": 2}),
            lo.EventoProgresso(lo.EVENTO_ETAPA, "concluida", "planejamento", {"consultas": 2, "ms": 3}),
            lo.EventoProgresso(lo.EVENTO_RESUMO, "concluida", "", resumo)]


def ler_eventos(texto):
    eventos = []
    for bloco in texto.split("\n\n"):
        if bloco.strip():
            nome = dados = None
            for linha in bloco.split("\n"):
                if linha.startswith("event: "):
                    nome = linha[len("event: "):]
                elif linha.startswith("data: "):
                    dados = json.loads(linha[len("data: "):])
            eventos.append((nome, dados))
    return eventos


def pedir_progresso(cliente, corpo=None, papeis=ATENDIMENTO, **opcoes):
    return cliente.post(chat_web.ROTA_PROGRESSO, json={"pergunta": PERGUNTA} if corpo is None else corpo, headers=cabecalhos(*papeis), **opcoes)


def pedir_json(cliente, corpo=None, papeis=ATENDIMENTO, **opcoes):
    return cliente.post(chat_web.ROTA_PERGUNTAR, json={"pergunta": PERGUNTA} if corpo is None else corpo, headers=cabecalhos(*papeis), **opcoes)


def cabecalho_de(sujeito, *papeis, tenant=TENANT):
    """O X-MS-CLIENT-PRINCIPAL de outra pessoa (outro OID no mesmo tenant) ou do mesmo OID em outro tenant."""
    claims = [{"typ": "iss", "val": "https://emissor.exemplo.invalido/"}, {"typ": "tid", "val": tenant}, {"typ": "oid", "val": sujeito},
              *({"typ": "roles", "val": papel} for papel in papeis)]
    return codificar(principal_sintetico(claims=claims))


class ExecucoesAtivasTests(TesteComLimite):
    """O registro de consultas em andamento: só para o cancelamento explícito, limitado e sem conteúdo de ninguém."""

    @staticmethod
    def novo(limite=2, validade=30.0):
        relogio = Relogio()
        return chat_web.ExecucoesAtivas(limite, validade, relogio), relogio

    def test_so_o_dono_cancela_e_o_item_sai_com_o_cancelamento(self):
        registro, _ = self.novo()
        dono, outro, alvo, sinal = b"A" * 32, b"B" * 32, "a" * 32, threading.Event()
        registro.abrir(alvo, dono, sinal)
        self.assertFalse(registro.cancelar(alvo, outro))
        self.assertFalse(sinal.is_set())
        self.assertEqual(len(registro), 1, "uma tentativa de outra identidade não muda nada")
        self.assertFalse(registro.cancelar("b" * 32, dono), "um identificador desconhecido não cancela nada")
        self.assertTrue(registro.cancelar(alvo, dono))
        self.assertTrue(sinal.is_set())
        self.assertEqual(len(registro), 0)
        self.assertFalse(registro.cancelar(alvo, dono), "já cancelada: não há o que cancelar de novo")

    def test_fechar_tira_o_item_sem_dar_sinal_e_pode_ser_repetido(self):
        registro, _ = self.novo()
        sinal = threading.Event()
        registro.abrir("a" * 32, b"A" * 32, sinal)
        registro.fechar("a" * 32)
        registro.fechar("a" * 32)
        self.assertEqual(len(registro), 0)
        self.assertFalse(sinal.is_set())
        self.assertFalse(registro.cancelar("a" * 32, b"A" * 32))

    def test_o_item_vence_com_a_validade_sem_dar_sinal(self):
        registro, relogio = self.novo(validade=10)
        sinal = threading.Event()
        registro.abrir("a" * 32, b"A" * 32, sinal)
        relogio.avancar(10.1)
        self.assertFalse(registro.cancelar("a" * 32, b"A" * 32))
        self.assertFalse(sinal.is_set(), "vencido: a consulta já passou do tempo máximo e terminou sozinha")
        self.assertEqual(len(registro), 0)

    def test_o_registro_nunca_passa_do_limite_e_nao_repete_identificador(self):
        registro, relogio = self.novo(limite=2, validade=30)
        for letra in "ab":
            registro.abrir(letra * 32, b"A" * 32, threading.Event())
        with self.assertRaises(lc.ErroChat) as cheio:
            registro.abrir("c" * 32, b"A" * 32, threading.Event())
        self.assertEqual(cheio.exception.codigo, lc.OCUPADO)
        registro.fechar("a" * 32)
        registro.abrir("c" * 32, b"A" * 32, threading.Event())
        with self.assertRaises(lc.ErroChat) as repetido:
            registro.abrir("c" * 32, b"B" * 32, threading.Event())
        self.assertEqual(repetido.exception.codigo, lc.ERRO_INTERNO, "o mesmo identificador nunca vira o de outra pessoa")
        self.assertTrue(registro.cancelar("c" * 32, b"A" * 32), "o dono original continua dono")
        relogio.avancar(31)
        registro.abrir("d" * 32, b"A" * 32, threading.Event())
        self.assertEqual(len(registro), 1, "o que venceu libera a vaga")

    def test_a_chave_do_ator_nao_guarda_tenant_nem_oid_e_depende_do_segredo_do_processo(self):
        segredo, pessoa = b"S" * 32, lc.Principal(TENANT, SUJEITO, ())
        chave = chat_web.chave_do_ator(segredo, pessoa)
        self.assertEqual(len(chave), 32)
        for sensivel in (TENANT, SUJEITO):
            self.assertNotIn(sensivel.encode("utf-8"), chave)
        self.assertEqual(chave, chat_web.chave_do_ator(segredo, lc.Principal(TENANT, SUJEITO, ("Vareleira.Corretor",))),
                         "só o tenant e o sujeito identificam: os papéis não")
        self.assertNotEqual(chave, chat_web.chave_do_ator(segredo, lc.Principal(TENANT, "outro-sujeito", ())))
        self.assertNotEqual(chave, chat_web.chave_do_ator(segredo, lc.Principal(OUTRO_TENANT, SUJEITO, ())))
        self.assertNotEqual(chave, chat_web.chave_do_ator(b"T" * 32, pessoa), "a chave só vale dentro do processo que a gerou")


@PRECISA_DO_HTTP
class HttpTests(TesteComLimite):
    def test_sem_a_coordenacao_a_rota_de_progresso_nao_existe_e_o_json_nao_muda(self):
        servico = ServicoCoordenadoFalso()
        sem_coordenacao = config(exigir_acesso_documental=True, indice=la.INDICE_PADRAO)
        with servidor(servico, sem_coordenacao) as cliente:
            progresso = pedir_progresso(cliente)
            normal = pedir_json(cliente)
            self.assertEqual((progresso.status_code, progresso.json()["erro"]), (404, lc.NAO_ENCONTRADO))
            self.assertIn('data-coordenacao="nao"', cliente.get("/", headers=cabecalhos(*ATENDIMENTO)).text)
        self.assertEqual(normal.status_code, 200)
        self.assertEqual(set(normal.json()), {"id", "id_requisicao", "tipo", "situacao", "texto", "aviso", "evidencias", "uso", "simulada",
                                              "aviso_simulacao"})
        self.assertEqual(len(servico.chamadas), 1)
        self.assertEqual(servico.cancelamentos, [])

    def test_a_coordenacao_exige_um_servico_coordenado_na_partida(self):
        from test_chat import ServicoFalso

        class SoComAcesso(ServicoFalso):
            exige_acesso = True

        with self.assertRaises(lab_comum.ErroLab) as erro, servidor(SoComAcesso(), config_l400()):
            pass
        self.assertIn("coordenado", str(erro.exception))

    def test_o_json_normal_do_modo_coordenado_tem_o_mesmo_formato_e_o_cancelamento_e_um_sinal_por_requisicao(self):
        servico = ServicoCoordenadoFalso(eventos_de_etapa())
        with servidor(servico, config_l400()) as cliente:
            resposta = pedir_json(cliente, {"pergunta": PERGUNTA, "id": "id-do-navegador-1"})
            pagina = cliente.get("/", headers=cabecalhos(*ATENDIMENTO))
        self.assertEqual(resposta.status_code, 200, resposta.text)
        dados = resposta.json()
        self.assertEqual(set(dados), {"id", "id_requisicao", "tipo", "situacao", "texto", "aviso", "evidencias", "uso", "simulada",
                                      "aviso_simulacao"})
        self.assertEqual((dados["id"], dados["texto"]), ("id-do-navegador-1", "Resposta pública de teste."))
        self.assertIn('data-coordenacao="sim"', pagina.text)
        self.assertNotIn("{{", pagina.text)

    def test_o_json_de_uma_consulta_coordenada_com_uso_incerto_leva_uso_nulo_como_o_avaliador_espera(self):
        incerta = lc.RespostaChat(lp.DOCUMENTADA, lp.RESPONDIDA, "Resposta de teste.", "", (), None)
        with servidor(ServicoCoordenadoFalso(resposta=lambda pergunta: incerta), config_l400()) as cliente:
            self.assertIsNone(pedir_json(cliente).json()["uso"])

    def test_o_fluxo_de_progresso_entrega_etapas_e_so_depois_a_resposta_no_mesmo_formato_do_json(self):
        servico = ServicoCoordenadoFalso(eventos_de_etapa())
        with servidor(servico, config_l400()) as cliente:
            resposta = pedir_progresso(cliente, {"pergunta": PERGUNTA, "id": "id-do-navegador-2"})
        self.assertEqual(resposta.status_code, 200, resposta.text)
        self.assertTrue(resposta.headers["content-type"].startswith("text/event-stream"))
        self.assertEqual(resposta.headers["cache-control"], "no-store")
        self.assertRegex(resposta.headers["x-request-id"], r"^[0-9a-f]{32}$")
        self.assertIn("frame-ancestors 'none'", resposta.headers["content-security-policy"])
        eventos = ler_eventos(resposta.text)
        self.assertEqual([nome for nome, _ in eventos], ["etapa", "tentativa", "etapa", "resumo", "resposta", "fim"])
        self.assertEqual(eventos[0][1], {"tipo": "etapa", "etapa": "planejamento", "estado": "iniciada", "dados": {"ms": 1}})
        indice_da_resposta = [nome for nome, _ in eventos].index("resposta")
        antes = json.dumps(eventos[:indice_da_resposta], ensure_ascii=False)
        for texto_da_resposta in ("Resposta pública de teste.", "as coberturas adicionais", PERGUNTA):
            self.assertNotIn(texto_da_resposta, antes, "nenhum texto antes do evento final")
        final = eventos[indice_da_resposta][1]
        self.assertEqual(set(final), {"id", "id_requisicao", "tipo", "situacao", "texto", "aviso", "evidencias", "uso", "simulada",
                                      "aviso_simulacao"})
        self.assertEqual((final["id"], final["id_requisicao"], final["texto"]),
                         ("id-do-navegador-2", resposta.headers["x-request-id"], "Resposta pública de teste."))
        self.assertEqual(eventos[-1], ("fim", {"estado": "concluida"}))

    def test_falha_no_fluxo_vira_evento_de_erro_com_codigo_publico_e_nunca_texto_da_excecao(self):
        casos = {"limite": (lc.ErroChat(lc.INDISPONIVEL, lo.CAUSA_LIMITE_DE_CHAMADAS), lc.INDISPONIVEL, "falhou"),
                 "cancelado": (lc.ErroChat(lc.CANCELADO, "cancelado"), lc.CANCELADO, "cancelada"),
                 "inesperado": (RuntimeError(SEGREDO), lc.ERRO_INTERNO, "falhou")}
        for rotulo, (erro, codigo, estado) in casos.items():
            with self.subTest(rotulo=rotulo), self.assertLogs("vareleira.chat", "INFO") as registro:
                with servidor(ServicoCoordenadoFalso(erro=erro), config_l400()) as cliente:
                    resposta = pedir_progresso(cliente)
                self.assertEqual(resposta.status_code, 200, "o status já saiu com o início do fluxo")
                nome, dados = ler_eventos(resposta.text)[-2]
                self.assertEqual(nome, "erro")
                self.assertEqual(dados, {"erro": codigo, "mensagem": lc.MENSAGENS[codigo], "id_requisicao": resposta.headers["x-request-id"]})
                self.assertEqual(ler_eventos(resposta.text)[-1], ("fim", {"estado": estado}))
                self.assertNotIn(SEGREDO, resposta.text + "\n".join(registro.output))

    def test_a_rota_de_progresso_exige_identidade_e_papel_e_nao_aceita_perfil_filtro_nem_destino_do_cliente(self):
        servico = ServicoCoordenadoFalso()
        with servidor(servico, config_l400()) as cliente:
            for rotulo, cabecalho in {"sem identidade": {}, "sem papel": cabecalhos(), "papel desconhecido": cabecalhos("Vareleira.Admin")}.items():
                with self.subTest(rotulo=rotulo):
                    resposta = cliente.post(chat_web.ROTA_PROGRESSO, json={"pergunta": PERGUNTA}, headers=cabecalho)
                    self.assertIn(resposta.status_code, (401, 403))
                    self.assertTrue(resposta.headers["content-type"].startswith("application/json"))
            enviados = {"perfil": "corretor", "papeis": ["Vareleira.Corretor"], "filtro": "search.in(acesso,'corretor',',')", "indice": "x",
                        "deployment": "geracao-contingencia", "timeout": 600, "acesso": "corretor", "classes": ["corretor"],
                        "max_chamadas": 100}
            for campo, valor in enviados.items():
                with self.subTest(campo=campo):
                    for pedir in (pedir_progresso, pedir_json):
                        resposta = pedir(cliente, {"pergunta": PERGUNTA, campo: valor})
                        self.assertEqual((resposta.status_code, resposta.json()["erro"]), (422, lc.CAMPOS_NAO_PERMITIDOS))
            for consulta in ("?perfil=corretor", "?filtro=true", "?deployment=x"):
                resposta = cliente.post(chat_web.ROTA_PROGRESSO + consulta, json={"pergunta": PERGUNTA}, headers=cabecalhos(*ATENDIMENTO))
                self.assertEqual((resposta.status_code, resposta.json()["erro"]), (422, lc.CAMPOS_NAO_PERMITIDOS))
            self.assertEqual(servico.chamadas, [], "pedido sem identidade, sem papel ou que tenta definir permissões nunca chega ao serviço")

    def test_sem_vaga_o_fluxo_responde_429_antes_de_comecar(self):
        entrou, soltar = threading.Event(), threading.Event()

        def esperar(pergunta, cancelar):
            entrou.set()
            soltar.wait(10)

        with servidor(ServicoCoordenadoFalso(esperar=esperar), config_l400(max_concorrencia=1)) as cliente, ThreadPoolExecutor(1) as pool:
            primeira = pool.submit(pedir_progresso, cliente)
            self.assertTrue(entrou.wait(10))
            segunda = pedir_progresso(cliente)
            self.assertEqual((segunda.status_code, segunda.json()["erro"], segunda.headers["retry-after"]),
                             (429, lc.OCUPADO, str(chat_web.ESPERA_SUGERIDA)))
            soltar.set()
            self.assertEqual(primeira.result(timeout=20).status_code, 200)

    def test_o_registro_da_coordenacao_tem_formato_fechado_e_nenhum_conteudo(self):
        servico = ServicoCoordenadoFalso(eventos_de_etapa())
        with self.assertLogs("vareleira.chat", "INFO") as registro, servidor(servico, config_l400()) as cliente:
            pedir_json(cliente, {"pergunta": "PERGUNTA-SECRETA " + PERGUNTA})
            pedir_progresso(cliente, {"pergunta": "PERGUNTA-SECRETA " + PERGUNTA})
        linhas = [linha for linha in registro.output if "coordenacao id=" in linha]
        self.assertEqual(len(linhas), 2)
        for linha in linhas:
            self.assertRegex(linha.split(":", 2)[2],
                             r"^coordenacao id=[0-9a-f]{32} resultado=concluido chamadas=6 buscas=2 contingencia=nao uso_incerto=nao$")
        texto = "\n".join(registro.output)
        for proibido in ("PERGUNTA-SECRETA", "Resposta pública", TENANT, MODELOS, BUSCA):
            self.assertNotIn(proibido, texto)
        rotas = [linha.split("rota=")[1].split()[0] for linha in registro.output if "requisicao id=" in linha]
        self.assertEqual(rotas, ["perguntar", "progresso"])

    def test_todo_o_registro_da_coordenacao_cabe_em_tres_formatos_fechados_em_qualquer_resultado(self):
        formatos = (r"assistente pronto [a-z_]+=\S+( [a-z_]+=\S+)*",
                    r"requisicao id=[0-9a-f]{32} rota=(perguntar|progresso) status=[0-9]{3} ms=[0-9]+( causa=[a-z_]{1,40})?",
                    r"coordenacao id=[0-9a-f]{32} resultado=(concluido|erro|cancelado) chamadas=[0-9]+ buscas=[0-9]+ "
                    r"contingencia=(sim|nao) uso_incerto=(sim|nao)")
        casos = {"concluída": ServicoCoordenadoFalso(eventos_de_etapa()),
                 "limite": ServicoCoordenadoFalso(erro=lc.ErroChat(lc.INDISPONIVEL, lo.CAUSA_LIMITE_DE_CHAMADAS)),
                 "cancelada": ServicoCoordenadoFalso(erro=lc.ErroChat(lc.CANCELADO, lo.CAUSA_CANCELADO)),
                 "inesperada": ServicoCoordenadoFalso(erro=RuntimeError(SEGREDO))}
        for rotulo, servico in casos.items():
            with self.subTest(caso=rotulo), self.assertLogs("vareleira.chat", "INFO") as registro:
                with servidor(servico, config_l400()) as cliente:
                    pedir_json(cliente)
                    pedir_progresso(cliente)
            mensagens = [linha.split(":", 2)[2] for linha in registro.output]
            for mensagem in mensagens:
                self.assertTrue(any(re.fullmatch(formato, mensagem) for formato in formatos), f"formato desconhecido: {mensagem}")
            self.assertEqual(sum(m.startswith("coordenacao id=") for m in mensagens), 2, "uma linha por consulta, no JSON e no fluxo")

    def test_o_json_coordenado_com_falha_registra_a_causa_e_a_linha_da_coordenacao(self):
        erro = lc.ErroChat(lc.INDISPONIVEL, lo.CAUSA_ORCAMENTO_DE_TOKENS)
        with self.assertLogs("vareleira.chat", "INFO") as registro, servidor(ServicoCoordenadoFalso(erro=erro), config_l400()) as cliente:
            resposta = pedir_json(cliente)
        self.assertEqual((resposta.status_code, resposta.json()["erro"]), (503, lc.INDISPONIVEL))
        texto = "\n".join(registro.output)
        self.assertIn("causa=orcamento_de_tokens", texto)
        self.assertRegex(texto, r"coordenacao id=[0-9a-f]{32} resultado=erro chamadas=0 buscas=0 contingencia=nao uso_incerto=sim")

    def test_a_coordenacao_real_atras_do_http_entrega_o_mesmo_resultado_no_json_e_no_fluxo(self):
        pilha = Pilha([PLANO, redator(), PLANO, redator()])
        with servidor(pilha.servico, config_l400()) as cliente:
            json_normal = pedir_json(cliente)
            fluxo = pedir_progresso(cliente)
        self.assertEqual((json_normal.status_code, fluxo.status_code), (200, 200), json_normal.text)
        final = ler_eventos(fluxo.text)[-2][1]
        publico = lambda dados: {campo: valor for campo, valor in dados.items() if campo not in ("id", "id_requisicao")}  # noqa: E731
        self.assertEqual(publico(final), publico(json_normal.json()))
        self.assertEqual(json_normal.json()["tipo"], lp.DOCUMENTADA)
        self.assertEqual(json_normal.json()["uso"], {"tokens_embeddings": 10, "tokens_entrada": json_normal.json()["uso"]["tokens_entrada"],
                                                     "tokens_saida": 80, "tokens_raciocinio": 20})

    def test_o_fluxo_real_de_progresso_traz_as_etapas_na_ordem_e_so_depois_a_resposta(self):
        pilha = Pilha([PLANO, redator(resposta="TEXTO-DO-MODELO-SO-NA-RESPOSTA")])
        with servidor(pilha.servico, config_l400()) as cliente:
            fluxo = pedir_progresso(cliente)
        eventos = ler_eventos(fluxo.text)
        nomes = [nome for nome, _ in eventos]
        self.assertEqual(nomes[-3:], ["resumo", "resposta", "fim"])
        self.assertEqual([(dados["etapa"], dados["estado"]) for nome, dados in eventos if nome == "etapa"],
                         [(etapa, estado) for etapa in lo.ETAPAS for estado in ("iniciada", "concluida")])
        self.assertEqual(eventos[-2][1]["texto"], "TEXTO-DO-MODELO-SO-NA-RESPOSTA")
        self.assertNotIn("TEXTO-DO-MODELO", json.dumps(eventos[:-2], ensure_ascii=False))
        self.assertEqual(eventos[-3][1]["dados"]["chamadas_modelo"], 2)

    def test_a_rota_de_cancelamento_so_existe_com_a_coordenacao(self):
        sem_coordenacao = config(exigir_acesso_documental=True, indice=la.INDICE_PADRAO)
        with servidor(ServicoCoordenadoFalso(), sem_coordenacao) as cliente:
            resposta = cliente.post(chat_web.ROTA_CANCELAR, json={"id_requisicao": "a" * 32}, headers=cabecalhos(*ATENDIMENTO))
            self.assertEqual((resposta.status_code, resposta.json()["erro"]), (404, lc.NAO_ENCONTRADO))
            self.assertIsNone(cliente.app.state.chat.execucoes, "sem a coordenação não há registro de consultas")

    def test_o_cancelamento_exige_identidade_papel_e_um_identificador_valido_sem_chegar_ao_servico(self):
        servico, alvo = ServicoCoordenadoFalso(), "a" * 32
        with servidor(servico, config_l400()) as cliente:
            def cancelar(corpo=None, cabecalho=None, **opcoes):
                return cliente.post(chat_web.ROTA_CANCELAR, json=corpo, headers=cabecalhos(*ATENDIMENTO) if cabecalho is None else cabecalho,
                                    **opcoes)

            sem_acesso = {"sem identidade": ({}, 401, lc.NAO_AUTENTICADO), "sem papel": (cabecalhos(), 403, lc.NAO_AUTORIZADO),
                          "papel desconhecido": (cabecalhos("Vareleira.Admin"), 403, lc.NAO_AUTORIZADO),
                          "outro tenant": (cabecalhos(*ATENDIMENTO, tenant=OUTRO_TENANT), 403, lc.NAO_AUTORIZADO)}
            for rotulo, (cabecalho, status, codigo) in sem_acesso.items():
                with self.subTest(rotulo=rotulo):
                    resposta = cancelar({"id_requisicao": alvo}, cabecalho)
                    self.assertEqual((resposta.status_code, resposta.json()["erro"]), (status, codigo))
            invalidos = {"sem o campo": {}, "formato": {"id_requisicao": "não é um id"}, "maiúsculas": {"id_requisicao": "A" * 32},
                         "curto": {"id_requisicao": "a" * 31}, "longo": {"id_requisicao": "a" * 33}, "número": {"id_requisicao": 123},
                         "nulo": {"id_requisicao": None}}
            for rotulo, corpo in invalidos.items():
                with self.subTest(identificador=rotulo):
                    resposta = cancelar(corpo)
                    self.assertEqual((resposta.status_code, resposta.json()["erro"]), (422, lc.ID_DA_EXECUCAO_INVALIDO))
            for campo, valor in {"perfil": "corretor", "papeis": ["Vareleira.Corretor"], "filtro": "true", "tenant": TENANT,
                                 "oid": SUJEITO, "deployment": "x", "pergunta": PERGUNTA}.items():
                with self.subTest(campo=campo):
                    resposta = cancelar({"id_requisicao": alvo, campo: valor})
                    self.assertEqual((resposta.status_code, resposta.json()["erro"]), (422, lc.CAMPOS_NAO_PERMITIDOS))
            resposta = cliente.post(chat_web.ROTA_CANCELAR + "?perfil=corretor", json={"id_requisicao": alvo}, headers=cabecalhos(*ATENDIMENTO))
            self.assertEqual((resposta.status_code, resposta.json()["erro"]), (422, lc.CAMPOS_NAO_PERMITIDOS))
            for rotulo, argumentos, status, codigo in (
                    ("não é JSON", dict(content=b"nao e json", headers={"Content-Type": "application/json"}), 422, lc.JSON_INVALIDO),
                    ("lista", dict(content=b"[]", headers={"Content-Type": "application/json"}), 422, lc.JSON_INVALIDO),
                    ("tipo de conteúdo", dict(content=b'{"id_requisicao": "' + alvo.encode() + b'"}', headers={"Content-Type": "text/plain"}),
                     422, lc.TIPO_DE_CONTEUDO_INVALIDO),
                    ("corpo grande", dict(content=b"x" * 2000, headers={"Content-Type": "application/json"}), 413, lc.PEDIDO_GRANDE)):
                with self.subTest(corpo=rotulo):
                    argumentos["headers"] = {**cabecalhos(*ATENDIMENTO), **argumentos["headers"]}
                    resposta = cliente.post(chat_web.ROTA_CANCELAR, **argumentos)
                    self.assertEqual((resposta.status_code, resposta.json()["erro"]), (status, codigo))
            self.assertEqual(cliente.get(chat_web.ROTA_CANCELAR, headers=cabecalhos(*ATENDIMENTO)).status_code, 405)
            resposta = cancelar({"id_requisicao": alvo})
            self.assertEqual((resposta.status_code, resposta.json()["erro"]), (404, lc.EXECUCAO_NAO_ENCONTRADA),
                             "um identificador bem formado que ninguém tem em andamento")
        self.assertEqual(servico.chamadas, [], "nenhum desses pedidos chega ao serviço")

    def test_a_consulta_so_esta_no_registro_enquanto_roda_e_o_registro_nao_guarda_conteudo(self):
        visto = {"durante": [], "conteudo": ""}

        def esperar(pergunta, cancelar):
            registro = visto["registro"]
            visto["durante"].append(len(registro))
            visto["conteudo"] += repr(registro._itens)

        with servidor(ServicoCoordenadoFalso(esperar=esperar), config_l400()) as cliente:
            visto["registro"] = cliente.app.state.chat.execucoes
            pedir_progresso(cliente, {"pergunta": "PERGUNTA-SECRETA " + PERGUNTA})
            self.assertEqual(len(visto["registro"]), 0, "terminou: saiu do registro")
            pedir_json(cliente)
            self.assertEqual(len(visto["registro"]), 0)
        self.assertEqual(visto["durante"], [1, 0], "o fluxo de progresso se registra; o JSON não tem identificador a tempo de ser cancelado")
        for proibido in ("PERGUNTA-SECRETA", TENANT, SUJEITO, la.PAPEL_ATENDIMENTO):
            self.assertNotIn(proibido, visto["conteudo"])

    def test_o_registro_esvazia_em_qualquer_fim_da_consulta(self):
        casos = {"concluída": ServicoCoordenadoFalso(eventos_de_etapa()),
                 "falha prevista": ServicoCoordenadoFalso(erro=lc.ErroChat(lc.INDISPONIVEL, lo.CAUSA_LIMITE_DE_CHAMADAS)),
                 "cancelada pelo serviço": ServicoCoordenadoFalso(erro=lc.ErroChat(lc.CANCELADO, lo.CAUSA_CANCELADO)),
                 "falha inesperada": ServicoCoordenadoFalso(erro=RuntimeError(SEGREDO))}
        for rotulo, servico in casos.items():
            with self.subTest(caso=rotulo), servidor(servico, config_l400()) as cliente:
                registro = cliente.app.state.chat.execucoes
                self.assertEqual(pedir_progresso(cliente).status_code, 200)
                self.assertEqual(len(registro), 0)


class ServidorLocal:
    """Um servidor uvicorn de verdade em 127.0.0.1, em uma thread, para provar o que só acontece com uma conexão real: a desconexão."""

    def __init__(self, app):
        import uvicorn

        with socket.socket() as soquete:
            soquete.bind(("127.0.0.1", 0))
            self.porta = soquete.getsockname()[1]
        self.servidor = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=self.porta, log_config=None, lifespan="on", http="h11",
                                                      ws="none", access_log=False))
        self.thread = threading.Thread(target=self.servidor.run, daemon=True)

    def __enter__(self):
        self.thread.start()
        limite = time.monotonic() + 20
        while not self.servidor.started and time.monotonic() < limite:
            time.sleep(0.05)
        if not self.servidor.started:
            raise AssertionError("o servidor local não iniciou")
        return self

    def __exit__(self, *erro):
        self.servidor.should_exit = True
        self.thread.join(timeout=20)

    def abrir(self, rota, corpo=None, papeis=ATENDIMENTO, cabecalho=None):
        dados = json.dumps({"pergunta": PERGUNTA} if corpo is None else corpo).encode("utf-8")
        cabecalho = cabecalho or cabecalhos(*papeis)[lc.CABECALHO_PRINCIPAL]
        pedido = (f"POST {rota} HTTP/1.1\r\nHost: 127.0.0.1:{self.porta}\r\nContent-Type: application/json\r\n"
                  f"Content-Length: {len(dados)}\r\n{lc.CABECALHO_PRINCIPAL}: {cabecalho}\r\nConnection: close\r\n\r\n").encode("ascii") + dados
        soquete = socket.create_connection(("127.0.0.1", self.porta), timeout=20)
        soquete.sendall(pedido)
        return soquete

    def responder(self, rota, corpo=None, papeis=ATENDIMENTO, cabecalho=None):
        """Uma requisição completa (a resposta vai até o fim da conexão): devolve (status, JSON da resposta)."""
        with contextlib.closing(self.abrir(rota, corpo, papeis, cabecalho)) as soquete:
            bruto = ler_ate(soquete, b"\0")  # sem essa marca, lê até o servidor fechar a conexão
        cabeca, _, resto = bruto.partition(b"\r\n\r\n")
        return int(cabeca.split(b" ", 2)[1]), json.loads(resto.decode("utf-8")) if resto.strip() else None


def ler_ate(soquete, marca, limite=20):
    recebido = b""
    fim = time.monotonic() + limite
    while marca not in recebido and time.monotonic() < fim:
        try:
            parte = soquete.recv(65536)
        except socket.timeout:
            continue
        if not parte:
            break
        recebido += parte
    return recebido


class PedidoFalso:
    """Do `Request` do Starlette, só o que a vigia usa: a próxima mensagem do servidor para esta requisição."""

    def __init__(self, receber):
        self.receive = receber


class VigiaDaConexaoTests(TesteComLimite):
    def vigiar(self, receber, encerrada_antes=False):
        cancelar = threading.Event()

        async def principal():
            encerrada = asyncio.Event()
            if encerrada_antes:
                encerrada.set()
            vigia = asyncio.ensure_future(chat_web.vigiar_conexao(PedidoFalso(receber), cancelar, encerrada))
            await asyncio.sleep(0.05)
            encerrada.set()
            await asyncio.wait_for(vigia, 5)

        inicio = time.monotonic()
        asyncio.run(principal())
        return cancelar, time.monotonic() - inicio

    def test_a_desconexao_do_cliente_da_o_sinal_de_cancelamento_desta_requisicao(self):
        async def desconectou():
            return {"type": "http.disconnect"}

        cancelar, _ = self.vigiar(desconectou)
        self.assertTrue(cancelar.is_set())

    def test_sem_desconexao_a_vigia_acaba_com_a_consulta_e_a_espera_nao_fica_pendurada(self):
        canceladas = []

        async def espera_para_sempre():
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                canceladas.append(True)
                raise

        cancelar, demora = self.vigiar(espera_para_sempre)
        self.assertFalse(cancelar.is_set())
        self.assertEqual(canceladas, [True])
        self.assertLess(demora, 2, "a vigia não segura a requisição depois do fim da consulta")

    def test_a_desconexao_que_so_chega_com_o_fim_da_consulta_nao_cancela_nada(self):
        async def desconectou():
            return {"type": "http.disconnect"}

        cancelar, _ = self.vigiar(desconectou, encerrada_antes=True)
        self.assertFalse(cancelar.is_set(), "com a resposta enviada o servidor também avisa 'desconexão': a consulta já terminou")

    def test_uma_falha_da_vigia_nao_derruba_a_consulta_nem_da_sinal(self):
        async def quebrada():
            raise RuntimeError(SEGREDO)

        cancelar, _ = self.vigiar(quebrada)
        self.assertFalse(cancelar.is_set())

    def test_uma_mensagem_que_nao_e_desconexao_nao_cancela(self):
        async def corpo_extra():
            return {"type": "http.request", "body": b"", "more_body": False}

        cancelar, _ = self.vigiar(corpo_extra)
        self.assertFalse(cancelar.is_set())


@PRECISA_DO_HTTP
class DesconexaoTests(TesteComLimite):
    def esperar_ate(self, condicao, limite=15):
        fim = time.monotonic() + limite
        while not condicao() and time.monotonic() < fim:
            time.sleep(0.05)
        return condicao()

    def test_o_navegador_que_desconecta_do_fluxo_cancela_so_aquela_consulta(self):
        iniciou, soltar = threading.Event(), threading.Event()

        def esperar(pergunta, cancelar):
            if "A-CANCELAR" in pergunta:
                iniciou.set()
                cancelar.wait(15)

        servico = ServicoCoordenadoFalso(eventos_de_etapa(), esperar=esperar)
        with self.assertLogs("vareleira.chat", "INFO") as registro, ServidorLocal(chat_web.create_app(config_l400(), lambda _: servico)) as local:
            cancelada = local.abrir(chat_web.ROTA_PROGRESSO, {"pergunta": "A-CANCELAR " + PERGUNTA})
            inicial = ler_ate(cancelada, b"event: etapa")
            self.assertIn(b"200 OK", inicial)
            self.assertTrue(iniciou.wait(15))
            normal = local.abrir(chat_web.ROTA_PROGRESSO, {"pergunta": "NORMAL " + PERGUNTA})
            completa = ler_ate(normal, b"event: fim")
            normal.close()
            self.assertIn(b"event: resposta", completa, "a outra consulta termina normalmente")
            cancelada.close()  # o navegador abortou (AbortController): a conexão cai
            self.assertTrue(self.esperar_ate(lambda: servico.cancelamentos), "o servidor deu o sinal de cancelamento")
        self.assertEqual(servico.cancelamentos, ["A-CANCELAR " + PERGUNTA])
        self.assertTrue(any("resultado=cancelado" in linha for linha in registro.output))
        self.assertTrue(any("resultado=concluido" in linha for linha in registro.output))

    def test_o_cliente_do_json_que_desconecta_tambem_cancela_so_a_propria_requisicao(self):
        iniciou = threading.Event()

        def esperar(pergunta, cancelar):
            iniciou.set()
            cancelar.wait(15)

        servico = ServicoCoordenadoFalso(esperar=esperar)
        with ServidorLocal(chat_web.create_app(config_l400(), lambda _: servico)) as local:
            soquete = local.abrir(chat_web.ROTA_PERGUNTAR)
            self.assertTrue(iniciou.wait(15))
            soquete.close()
            self.assertTrue(self.esperar_ate(lambda: servico.cancelamentos), "a desconexão do cliente do JSON deu o sinal desta requisição")


@PRECISA_DO_HTTP
class CancelamentoExplicitoTests(TesteComLimite):
    """O cancelamento pela rota autenticada: vale mesmo quando a desconexão do navegador não chega ao servidor (a conexão fica aberta).
    A consulta é a real (MAF, orçamento, política), com o modelo falso lento, atrás do servidor uvicorn de verdade."""

    @staticmethod
    def abrir_fluxo(local, **opcoes):
        soquete = local.abrir(chat_web.ROTA_PROGRESSO, **opcoes)
        inicio = ler_ate(soquete, b"event: etapa")
        achado = re.search(rb"\r\nx-request-id: ([0-9a-f]{32})\r\n", inicio, re.IGNORECASE)
        return soquete, inicio, achado.group(1).decode("ascii") if achado else None

    def test_so_a_mesma_identidade_cancela_a_consulta_em_andamento_e_nenhuma_etapa_futura_roda(self):
        pilha = Pilha([("lento", 20, PLANO), redator()])
        app = chat_web.create_app(config_l400(tenants_autorizados=frozenset({TENANT, OUTRO_TENANT})), lambda _: pilha.servico)
        outra_pessoa = cabecalho_de("outro-sujeito", *ATENDIMENTO)
        mesmo_oid_em_outro_tenant = cabecalho_de(SUJEITO, *ATENDIMENTO, tenant=OUTRO_TENANT)
        with self.assertLogs("vareleira.chat", "INFO") as registro, ServidorLocal(app) as local:
            fluxo, inicio, alvo = self.abrir_fluxo(local)
            self.addCleanup(fluxo.close)
            self.assertIn(b" 200 ", inicio.split(b"\r\n", 1)[0])
            self.assertIsNotNone(alvo, "o identificador chega nos cabeçalhos, antes de qualquer evento")
            self.assertTrue(esperar_ate(lambda: len(pilha.transporte.pedidos) == 1), "o planejamento está em andamento no modelo")
            execucoes = app.state.chat.execucoes
            self.assertEqual(len(execucoes), 1)
            for rotulo, cabecalho in {"outra pessoa": outra_pessoa, "o mesmo OID em outro tenant": mesmo_oid_em_outro_tenant}.items():
                with self.subTest(quem=rotulo):
                    status, dados = local.responder(chat_web.ROTA_CANCELAR, {"id_requisicao": alvo}, cabecalho=cabecalho)
                    self.assertEqual((status, dados["erro"]), (404, lc.EXECUCAO_NAO_ENCONTRADA), "o mesmo erro de uma consulta que não existe")
            self.assertEqual(len(execucoes), 1, "a consulta de quem iniciou segue em andamento")
            inicio_do_cancelamento = time.monotonic()
            status, dados = local.responder(chat_web.ROTA_CANCELAR, {"id_requisicao": alvo})
            self.assertEqual((status, dados), (202, {"estado": "cancelamento_solicitado", "alvo": alvo}))
            final = ler_ate(fluxo, b"event: fim")
            self.assertLess(time.monotonic() - inicio_do_cancelamento, 8, "parou logo, sem esperar os 20 s do modelo")
            self.assertIn(b"event: erro", final)
            self.assertIn(b'"erro":"cancelado"', final)
            self.assertIn(b'"estado":"cancelada"', final)
            self.assertTrue(esperar_ate(lambda: len(execucoes) == 0), "o registro esvazia")
            status, dados = local.responder(chat_web.ROTA_CANCELAR, {"id_requisicao": alvo})
            self.assertEqual((status, dados["erro"]), (404, lc.EXECUCAO_NAO_ENCONTRADA), "uma consulta cancelada não é cancelada de novo")
        self.assertEqual(len(pilha.transporte.pedidos), 1, "só o planejamento chegou ao modelo: nenhuma etapa futura")
        self.assertEqual((pilha.openai.chamadas, pilha.indice.consultas, pilha.transporte.de_redacao()), ([], [], []))
        linhas = [linha.split(":", 2)[2] for linha in registro.output]
        self.assertTrue(any(m.startswith("coordenacao ") and "resultado=cancelado" in m for m in linhas))
        self.assertEqual(sum("rota=cancelar" in m for m in linhas), 4, "uma linha da requisição por pedido de cancelamento")
        texto = "\n".join(linhas)
        for proibido in (SUJEITO, "outro-sujeito", TENANT, OUTRO_TENANT, "PERGUNTA", PERGUNTA):
            self.assertNotIn(proibido, texto, "o registro não traz identidade nem pergunta")

    def test_o_registro_esvazia_quando_o_navegador_desconecta_e_nao_deixa_a_consulta_pendurada(self):
        pilha = Pilha([("lento", 20, PLANO), redator()])
        app = chat_web.create_app(config_l400(), lambda _: pilha.servico)
        with ServidorLocal(app) as local:
            fluxo, _, alvo = self.abrir_fluxo(local)
            self.assertIsNotNone(alvo)
            self.assertTrue(esperar_ate(lambda: len(pilha.transporte.pedidos) == 1))
            execucoes = app.state.chat.execucoes
            self.assertEqual(len(execucoes), 1)
            fluxo.close()
            self.assertTrue(esperar_ate(lambda: len(execucoes) == 0), "sem o navegador, a consulta sai do registro (e é cancelada)")
            self.assertEqual(local.responder(chat_web.ROTA_CANCELAR, {"id_requisicao": alvo})[0], 404)
        self.assertEqual(len(pilha.transporte.pedidos), 1)


# --------------------------------------------------------------------------------------
# Linha de comando
# --------------------------------------------------------------------------------------

def rodar_coordenar(argumentos, servico=None, credencial_ok=True):
    """Executa `coordenar_maf.principal` com o serviço e a credencial trocados por dublês. Devolve (código, texto impresso)."""
    saida = io.StringIO()
    with contextlib.ExitStack() as pilha:
        if servico is not None:
            pilha.enter_context(mock.patch.object(lo, "criar_servico_coordenado", return_value=servico))
        if credencial_ok:
            pilha.enter_context(mock.patch.object(coordenar_maf, "criar_credencial", return_value=CredencialFalsa()))
        pilha.enter_context(contextlib.redirect_stdout(saida))
        pilha.enter_context(contextlib.redirect_stderr(saida))
        try:
            codigo = coordenar_maf.principal(argumentos)
        except SystemExit as erro:
            codigo = erro.code
    return codigo, saida.getvalue()


ARGUMENTOS_DA_CONSULTA = ["--busca", BUSCA, "--modelos", MODELOS, "--perfil", "atendimento", "--pergunta", PERGUNTA,
                          "--dimensoes", str(DIMENSOES)]


class CliTests(TesteComLimite):
    def test_mostrar_plano_nao_usa_rede_nem_credencial_nem_servico(self):
        with mock.patch.object(socket.socket, "connect", side_effect=AssertionError("rede")), \
                mock.patch.object(lo, "criar_servico_coordenado", side_effect=AssertionError("serviço")):
            codigo, texto = rodar_coordenar(["--mostrar-plano", "--perfil", "corretor", "--deployment-contingencia", CONTINGENCIA],
                                            credencial_ok=False)
        self.assertEqual(codigo, lab_comum.CODIGO_OK, texto)
        plano = " ".join(texto.split())
        for esperado in ("sem rede, sem credenciais e sem Azure", "planejamento → recuperacao → verificacao → redacao → politica",
                         "search.in(acesso,'compartilhado,corretor',',')", f"contingência: {CONTINGENCIA}", "max_retries=0",
                         "Grafo montado com o MAF", "recuperacao: recebe PlanoDeConsultas; envia Recuperados",
                         "não uma autenticação do Entra ID", "chamadas no total (modelo, embeddings e busca): 8",
                         "tentativas de geração: 4 · buscas: 2", "tokens (reserva", "nunca trocam de deployment",
                         "não garante cota adicional", "Nenhuma resposta sai depois do cancelamento",
                         "--- Instruções do agente de planejamento ---", "Esquema fechado do plano"):
            self.assertIn(esperado, plano)
        self.assertNotIn(MODELOS, texto)

    def test_o_plano_sem_perfil_e_sem_contingencia_diz_isso_e_nao_inventa_padroes(self):
        codigo, texto = rodar_coordenar(["--mostrar-plano"], credencial_ok=False)
        self.assertEqual(codigo, lab_comum.CODIGO_OK)
        self.assertIn("contingência: não configurada", texto)
        self.assertIn("definido pelo contexto de acesso de cada requisição", texto)

    def test_a_consulta_exige_as_opcoes_explicitas_e_o_perfil_nunca_tem_padrao(self):
        casos = {"sem perfil": ([a for i, a in enumerate(ARGUMENTOS_DA_CONSULTA) if i not in (4, 5)], "--perfil"),
                 "sem busca": (ARGUMENTOS_DA_CONSULTA[2:], "--busca"),
                 "sem pergunta": (ARGUMENTOS_DA_CONSULTA[:6], "--pergunta"),
                 "client-id sem identidade gerenciada": ([*ARGUMENTOS_DA_CONSULTA, "--client-id", guid(5)], "--identidade-gerenciada"),
                 "tarifa incompleta": ([*ARGUMENTOS_DA_CONSULTA, "--tarifa-entrada", "1"], "--tarifa-saida")}
        for rotulo, (argumentos, esperado) in casos.items():
            with self.subTest(rotulo=rotulo):
                codigo, texto = rodar_coordenar(argumentos, servico=Pilha([PLANO, redator()]).servico)
                self.assertEqual(codigo, lab_comum.CODIGO_USO, texto)
                self.assertIn(esperado, texto)
        for invalido in (["--perfil", "administrador"], ["--max-chamadas", "0"], ["--max-chamadas", "99"], ["--max-tokens", "10"],
                         ["--max-buscas", "3"], ["--tempo", "5"], ["--tempo", "nan"]):
            with self.subTest(invalido=invalido):
                codigo, _ = rodar_coordenar([*ARGUMENTOS_DA_CONSULTA, *invalido])
                self.assertEqual(codigo, lab_comum.CODIGO_USO)

    def test_a_consulta_mostra_progresso_resposta_evidencias_uso_e_nao_inventa_valor(self):
        pilha = Pilha([PLANO, redator()])
        codigo, texto = rodar_coordenar(ARGUMENTOS_DA_CONSULTA, servico=pilha.servico)
        self.assertEqual(codigo, lab_comum.CODIGO_OK, texto)
        for esperado in ("Perfil do operador: atendimento (escolhido em --perfil, não é autenticação do Entra ID)", "[etapa] planejamento: iniciada",
                         "[tentativa 1] planejamento, deployment primario: ok", "[etapa] politica: concluida", "Tipo da pergunta: documentada nos trechos",
                         "Resposta de teste.", "[TRECHO-1]", "chamadas: 6 de 8", "buscas 2 de 2", "contingência usada: não",
                         "valor: não calculado (nenhuma tarifa foi informada). Tokens não são fatura.", "não confirma as coberturas"):
            self.assertIn(esperado, texto)
        self.assertNotIn("Uso incerto", texto)
        self.assertLess(texto.index("[etapa] planejamento: iniciada"), texto.index("Resposta:"), "o progresso vem antes do texto da resposta")
        codigo, com_tarifa = rodar_coordenar([*ARGUMENTOS_DA_CONSULTA, "--tarifa-entrada", "2", "--tarifa-saida", "8"],
                                             servico=Pilha([PLANO, redator()]).servico)
        self.assertEqual(codigo, lab_comum.CODIGO_OK)
        self.assertRegex(com_tarifa, r"valor estimado: \d+\.\d{6} na moeda da tarifa que você informou\. É uma estimativa, não a fatura\.")

    def test_a_consulta_com_falha_mostra_codigo_publico_uso_incerto_e_nenhum_texto_bruto(self):
        pilha = Pilha([("http", 403)])
        codigo, texto = rodar_coordenar([*ARGUMENTOS_DA_CONSULTA, "--tarifa-entrada", "2", "--tarifa-saida", "8"], servico=pilha.servico)
        self.assertEqual(codigo, lab_comum.CODIGO_ACESSO)
        for esperado in ("[ERRO]", "código: indisponivel; causa: acesso_negado", "Nenhuma resposta foi apresentada", "Uso incerto",
                         "valor: não calculado (o uso é incerto)"):
            self.assertIn(esperado, texto)
        self.assertNotIn(SEGREDO, texto)
        self.assertNotIn("Traceback", texto)
        sem_fonte = Pilha([PLANO, redator(referencias=["T99"])])
        codigo, texto = rodar_coordenar(ARGUMENTOS_DA_CONSULTA, servico=sem_fonte.servico)
        self.assertEqual(codigo, lab_comum.CODIGO_DIVERGENCIA)
        self.assertIn("referencia_desconhecida", texto)

    def test_ctrl_c_cancela_so_esta_consulta_e_as_proximas_etapas_nao_executam(self):
        pilha = Pilha([("lento", 10, PLANO), redator()])

        class ThreadQueInterrompe(threading.Thread):
            interrompida = False

            def join(self, timeout=None):
                if self.name == "coordenacao-cli" and not ThreadQueInterrompe.interrompida:
                    ThreadQueInterrompe.interrompida = True
                    fim = time.monotonic() + 10
                    while not pilha.transporte.pedidos and time.monotonic() < fim:  # o Ctrl+C chega com o planejamento em andamento
                        time.sleep(0.01)
                    raise KeyboardInterrupt
                return super().join(timeout)

        with mock.patch.object(coordenar_maf.threading, "Thread", ThreadQueInterrompe):
            inicio = time.monotonic()
            codigo, texto = rodar_coordenar(ARGUMENTOS_DA_CONSULTA, servico=pilha.servico)
        self.assertEqual(codigo, coordenar_maf.CODIGO_CANCELADO, texto)
        self.assertLess(time.monotonic() - inicio, 8)
        self.assertIn("Cancelando: as próximas etapas não serão executadas", texto)
        self.assertIn("pode terminar e consumir tokens", texto)
        self.assertEqual((len(pilha.transporte.pedidos), pilha.indice.consultas, pilha.openai.chamadas), (1, [], []))
        self.assertIn("Uso incerto", texto)


# --------------------------------------------------------------------------------------
# Código sem chaves nem repetições escondidas
# --------------------------------------------------------------------------------------

class CodigoTests(unittest.TestCase):
    def codigo(self, nome):
        return (RAIZ / "scripts" / nome).read_text(encoding="utf-8")

    def test_os_clientes_nascem_sem_repeticoes_automaticas_e_sem_chaves(self):
        for nome in ("lab_orquestracao.py", "coordenar_maf.py"):
            texto = self.codigo(nome)
            self.assertIsNone(re.search(r"max_retries\s*=\s*[1-9]", texto), nome)
            self.assertIsNone(re.search(r"api_key\s*=\s*[\"']", texto), nome)
            self.assertIsNone(re.search(r"AccountKey|client_secret|password|connection[_ ]string", texto, re.IGNORECASE), nome)
            self.assertIsNone(re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", texto), nome)
        fabrica = self.codigo("lab_orquestracao.py")
        self.assertEqual(len(re.findall(r"max_retries=0,\s+timeout=", fabrica)), 2, "os clientes de embeddings e de modelos")
        self.assertIn("retry_total=0", fabrica)

    def test_a_imagem_e_a_avaliacao_incluem_o_modulo_da_coordenacao(self):
        import avaliar_chat

        self.assertIn("lab_orquestracao.py", avaliar_chat.ARQUIVOS_DO_CODIGO)
        self.assertIn("scripts/lab_orquestracao.py", (RAIZ / "Dockerfile").read_text(encoding="utf-8"))
        self.assertIn("!scripts/lab_orquestracao.py", (RAIZ / ".dockerignore").read_text(encoding="utf-8"))
        linhas = [linha.strip() for linha in (RAIZ / "requirements" / "l400.txt").read_text(encoding="utf-8").splitlines()
                  if linha.strip() and not linha.startswith("#")]
        self.assertEqual(linhas, ["-r l300.txt"])

    def test_a_estimativa_de_valor_so_existe_com_tarifa_informada_e_uso_conhecido(self):
        resumo = {"uso_incerto": False, "tokens_entrada": 1_000_000, "tokens_saida": 500_000, "tokens_embeddings": 2_000_000}
        tarifa = lo.Tarifa(2.0, 8.0, 0.5)
        self.assertEqual(lo.estimar_valor(resumo, tarifa), 2.0 + 4.0 + 1.0)
        self.assertIsNone(lo.estimar_valor(resumo, None))
        self.assertIsNone(lo.estimar_valor({**resumo, "uso_incerto": True}, tarifa))
        self.assertIsNone(lo.estimar_valor({}, tarifa))


if __name__ == "__main__":
    unittest.main()
