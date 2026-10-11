"""Testes do acesso documental do L300 (sem Azure): papéis, filtro, busca, serviço e API do chat.

O que se prova aqui: o filtro nasce só de papéis da identidade validada e de classes fixas; ele vai na própria consulta (texto,
vetorial e híbrida, com preFilter quando há vetor) antes de qualquer trecho chegar ao modelo; identidade sem papel conhecido recebe
403 antes de buscar, calcular embeddings ou chamar o modelo; o JSON e a query não definem permissões; duas pessoas ao mesmo tempo
não se misturam; e, com a opção desligada, o L200 funciona como sempre.
"""

import threading
import unittest
from concurrent.futures import ThreadPoolExecutor

import support  # noqa: F401  (configura o caminho dos scripts)
import lab_acesso as la
import lab_chat as lc
import lab_comum
import lab_geracao as lg
import lab_indexacao as li
import lab_politica as lp
from support import OpenAIFalso, OpenAIGeracaoFalso
from test_chat import (BUSCA, DIMENSOES, MODELOS, PERGUNTA_GERAL, PRECISA_DO_HTTP, SUJEITO, TENANT, ServicoFalso, ambiente,
                       codificar, config, perguntar_pela_api, principal, responder, rodar_chat, servidor)

PERGUNTA = "Qual é a regra fictícia de teste para este documento?"
MARCADORES = {"compartilhado": "MARCADOR-COMPARTILHADO-L300", "atendimento": "MARCADOR-ATENDIMENTO-L300",
              "corretor": "MARCADOR-CORRETOR-L300", None: "MARCADOR-SEM-CLASSE-L300", "": "MARCADOR-CLASSE-VAZIA-L300",
              "interno-desconhecido": "MARCADOR-CLASSE-DESCONHECIDA-L300"}
PERMITIDOS = {  # papéis -> marcadores que o modelo pode receber
    "atendimento": ((la.PAPEL_ATENDIMENTO,), {"compartilhado", "atendimento"}),
    "corretor": ((la.PAPEL_CORRETOR,), {"compartilhado", "corretor"}),
    "os dois papéis": ((la.PAPEL_ATENDIMENTO, la.PAPEL_CORRETOR), {"compartilhado", "atendimento", "corretor"}),
}


def trecho(classe, indice):
    identificador = f"TRECHO-{indice}"
    return {"id": identificador, "documento_id": f"DOC-{indice}", "titulo_documento": "Documento sintético", "secao": "Seção",
            "clausulas": "", "fonte": f"vareleira-lar-l300/documento-{indice}.md", "versao": "1.0", "acesso": classe,
            "conteudo": f"Regra fictícia de teste do trecho {indice}: {MARCADORES[classe]} vale só para quem pode consultar este documento."}


TRECHOS = [trecho(classe, indice) for indice, classe in enumerate(MARCADORES, start=1)]


class IndiceAcessoFalso:
    """Aplica o filtro como o serviço: só trechos de classes permitidas entram no ranking e no top-k (filtro antes da escolha)."""

    def __init__(self, trechos=TRECHOS, eventos=None, ao_consultar=None):
        self.trechos, self.eventos, self.ao_consultar = trechos, [] if eventos is None else eventos, ao_consultar
        self.consultas = []

    def consultar(self, texto, vetor, k, filtro=None):
        self.eventos.append("busca")
        self.consultas.append({"texto": texto, "vetor": vetor is not None, "k": k, "filtro": filtro})
        if filtro is None:
            raise AssertionError("consulta ao índice sem filtro de acesso")
        classes = la.classes_do_filtro(filtro)
        if self.ao_consultar:
            self.ao_consultar(classes)
        return [dict(item) for item in self.trechos if item["acesso"] in classes][:k]


class IndiceQueIgnoraOFiltro(IndiceAcessoFalso):
    """Um índice defeituoso: devolve tudo, como se o filtro não existisse."""

    def consultar(self, texto, vetor, k, filtro=None):
        self.eventos.append("busca")
        return [dict(item) for item in self.trechos][:k]


class EmbeddingsRegistrados(OpenAIFalso):
    def __init__(self, eventos):
        super().__init__(dimensoes=DIMENSOES)
        self.eventos = eventos

    def _criar(self, model, input):  # noqa: A002 - nome da API real
        self.eventos.append("embeddings")
        return super()._criar(model, input)


class GeracaoRegistrada(OpenAIGeracaoFalso):
    def __init__(self, eventos):
        super().__init__()
        self.eventos = eventos
        self.responder = responder(lp.DOCUMENTADA)

    def _criar(self, **argumentos):
        self.eventos.append("modelo")
        return super()._criar(**argumentos)


class Pilha:
    """O serviço real do chat no modo L300 sobre dublês que registram a ordem do que aconteceu."""

    def __init__(self, indice=None, modo="hibrida", k=6):
        self.eventos = []
        self.indice = indice if indice is not None else IndiceAcessoFalso(eventos=self.eventos)
        if getattr(self.indice, "eventos", None) is not self.eventos:
            self.indice.eventos = self.eventos
        self.embeddings, self.geracao = EmbeddingsRegistrados(self.eventos), GeracaoRegistrada(self.eventos)
        recuperador = lg.Recuperador(self.indice, li.ClienteEmbeddings(self.embeddings, "embeddings", DIMENSOES), exigir_filtro=True)
        self.servico = lc.ServicoRag(recuperador, lg.ClienteGeracao(self.geracao, "geracao", MODELOS), modo, k, exigir_acesso=True)

    def entrada_do_modelo(self):
        return self.geracao.chamadas[-1]["input"]


def cabecalhos(*papeis, tipo="roles", tenant=TENANT, extras=None):
    claims = [{"typ": "iss", "val": "https://emissor.exemplo.invalido/"}, {"typ": "tid", "val": tenant},
              {"typ": "oid", "val": SUJEITO}, *({"typ": tipo, "val": papel} for papel in papeis)]
    return {lc.CABECALHO_PRINCIPAL: codificar(principal(claims=claims)), **(extras or {})}


def config_l300(**mudancas):
    return config(exigir_acesso_documental=True, indice=la.INDICE_PADRAO, **mudancas)


# --------------------------------------------------------------------------------------
# Papéis, classes e filtro
# --------------------------------------------------------------------------------------

class FiltroTests(unittest.TestCase):
    def test_cada_perfil_gera_o_filtro_so_com_classes_fixas(self):
        esperado = {"atendimento": "search.in(acesso,'compartilhado,atendimento',',')",
                    "corretor": "search.in(acesso,'compartilhado,corretor',',')",
                    "os dois papéis": "search.in(acesso,'compartilhado,atendimento,corretor',',')"}
        for rotulo, (papeis, _) in PERMITIDOS.items():
            with self.subTest(perfil=rotulo):
                contexto = la.autorizar(reversed(papeis))
                self.assertEqual(contexto.filtro, esperado[rotulo])
                self.assertEqual(la.classes_do_filtro(contexto.filtro), contexto.classes)

    def test_classe_fora_da_lista_ou_lista_vazia_nunca_vira_filtro(self):
        for rotulo, classes in {"vazia": [], "desconhecida": ["segredo"], "mistura": ["compartilhado", "segredo"],
                                "injeção": ["compartilhado') or true or search.in(acesso, 'x"], "caixa": ["Atendimento"],
                                "espaço": ["atendimento "], "nula": [None], "número": [1], "lista dentro da lista": [["corretor"]]}.items():
            with self.subTest(rotulo=rotulo), self.assertRaises(la.ErroAcesso):
                la.construir_filtro(classes)

    def test_so_o_filtro_gerado_pelo_programa_chega_a_busca(self):
        for rotulo, filtro in {"vazio": "", "nulo": None, "tautologia": "search.in(acesso,'compartilhado',',') or true",
                               "outro campo": "search.in(id,'compartilhado',',')", "igualdade": "acesso eq 'corretor'",
                               "classe fora da lista": "search.in(acesso,'segredo',',')",
                               "ordem diferente": "search.in(acesso,'atendimento,compartilhado',',')",
                               "classe repetida": "search.in(acesso,'compartilhado,compartilhado',',')",
                               "espaço sobrando": "search.in(acesso,'compartilhado',',') ", "quebra de linha": "search.in(acesso,'corretor',',')\n"
                               }.items():
            with self.subTest(rotulo=rotulo), self.assertRaises(la.ErroAcesso):
                la.validar_filtro(filtro)

    def test_papel_ausente_desconhecido_ou_com_outra_grafia_vale_como_nenhum(self):
        for papeis in ([], ["Vareleira.Admin"], ["vareleira.atendimento"], ["Vareleira.Atendimento "], ["Vareleira.Atendimento'"],
                       ["Contributor", "Owner"], [None, 3, ["Vareleira.Corretor"]], ["VARELEIRA.CORRETOR"]):
            with self.subTest(papeis=papeis), self.assertRaises(la.ErroSemPapel):
                la.autorizar(papeis)

    def test_papeis_vem_so_das_claims_roles_ou_da_uri_de_papel(self):
        uri = "http://schemas.microsoft.com/ws/2008/06/identity/claims/role"
        claims = [{"typ": "roles", "val": la.PAPEL_CORRETOR}, {"typ": uri, "val": la.PAPEL_ATENDIMENTO},
                  {"typ": "groups", "val": "Vareleira.Atendimento"}, {"typ": "role", "val": "Vareleira.Atendimento"},
                  {"typ": "scp", "val": "Vareleira.Corretor"}, {"typ": "roles", "val": "Vareleira.Outro"}, "lixo", {"typ": "roles"}]
        self.assertEqual(la.papeis_dos_claims(claims), (la.PAPEL_ATENDIMENTO, la.PAPEL_CORRETOR))
        so_outros_tipos = [claim for claim in claims if isinstance(claim, dict) and claim.get("typ") in {"groups", "role", "scp"}]
        self.assertEqual((len(so_outros_tipos), la.papeis_dos_claims(so_outros_tipos)), (3, ()))
        decodificado = lc.decodificar_principal(codificar(principal(claims=[
            {"typ": "tid", "val": TENANT}, {"typ": "oid", "val": SUJEITO}, {"typ": uri, "val": la.PAPEL_CORRETOR}])))
        self.assertEqual(decodificado.papeis, (la.PAPEL_CORRETOR,))

    def test_um_contexto_inconsistente_nao_existe(self):
        for argumentos in ((("Vareleira.Admin",), ("compartilhado",), "search.in(acesso,'compartilhado',',')"),
                           ((la.PAPEL_CORRETOR,), ("compartilhado", "atendimento"), "search.in(acesso,'compartilhado,atendimento',',')"),
                           ((la.PAPEL_CORRETOR,), ("compartilhado", "corretor"), "acesso ne null"), ((), (), "")):
            with self.subTest(argumentos=argumentos), self.assertRaises(la.ErroAcesso):
                la.ContextoAcesso(*argumentos)

    def test_classe_ausente_vazia_ou_desconhecida_nunca_passa(self):
        contexto = la.autorizar([la.PAPEL_ATENDIMENTO])
        self.assertTrue(contexto.permite({"acesso": "atendimento"}))
        for item in ({}, {"acesso": None}, {"acesso": ""}, {"acesso": "corretor"}, {"acesso": "interno"}, {"acesso": ["atendimento"]}):
            with self.subTest(item=item):
                self.assertFalse(contexto.permite(item))

    def test_indice_do_acesso_documental_e_so_o_do_l300(self):
        for nome in ("vareleira-lar-l300", "vareleira-lar-l300-teste", "vareleira-lar-l300-a-b-c"):
            self.assertTrue(la.indice_l300(nome), nome)
        for nome in ("vareleira-lar-l100", "vareleira-lar-l200", "vareleira-lar-l3000", "vareleira-lar-l300-a-b-c-d",
                     "outro-vareleira-lar-l300", "vareleira-lar-l300\n", "", None):
            self.assertFalse(la.indice_l300(nome), repr(nome))


# --------------------------------------------------------------------------------------
# Busca no Azure AI Search (cliente real do SDK, sem rede)
# --------------------------------------------------------------------------------------

class CredencialFalsa:
    def get_token(self, *escopos, **opcoes):
        raise AssertionError("nenhum token deve ser pedido")


class ClienteBuscaFalso:
    def __init__(self):
        self.chamadas = []

    def search(self, **argumentos):
        self.chamadas.append(argumentos)
        return iter([{"id": "a", "acesso": "compartilhado"}])


class BuscaDoAzureTests(unittest.TestCase):
    def indice(self, **opcoes):
        indice = li.IndiceBusca(BUSCA, la.INDICE_PADRAO, credencial=CredencialFalsa(), **opcoes)
        indice._documentos = ClienteBuscaFalso()
        return indice

    def test_filtro_vale_nos_tres_modos_e_o_vetor_usa_prefiltro(self):
        filtro = la.construir_filtro(["compartilhado", "atendimento"])
        vetor = [0.1] * DIMENSOES
        for modo, texto, com_vetor in (("texto", "pergunta", None), ("vetorial", None, vetor), ("hibrida", "pergunta", vetor)):
            with self.subTest(modo=modo):
                indice = self.indice(exigir_filtro=True)
                indice.consultar(texto, com_vetor, 3, filtro)
                (chamada,) = indice._documentos.chamadas
                self.assertEqual(chamada["filter"], "search.in(acesso,'compartilhado,atendimento',',')")
                self.assertEqual(chamada["search_text"], texto)
                self.assertEqual(chamada["select"], [*li.IndiceBusca.CAMPOS_DO_RESULTADO, "acesso"])
                if com_vetor is None:
                    self.assertNotIn("vector_queries", chamada)
                    self.assertNotIn("vector_filter_mode", chamada)
                else:
                    self.assertEqual(chamada["vector_filter_mode"], "preFilter")
                    self.assertEqual(len(chamada["vector_queries"]), 1)

    def test_sem_filtro_a_consulta_e_a_do_l100_e_com_a_exigencia_ligada_e_erro_sem_chamar_o_servico(self):
        legado = self.indice()
        legado.consultar("pergunta", [0.1] * DIMENSOES, 3)
        (chamada,) = legado._documentos.chamadas
        for ausente in ("filter", "vector_filter_mode"):
            self.assertNotIn(ausente, chamada)
        self.assertEqual(chamada["select"], li.IndiceBusca.CAMPOS_DO_RESULTADO)
        exigente = self.indice(exigir_filtro=True)
        with self.assertRaises(la.ErroAcesso) as contexto:
            exigente.consultar("pergunta", None, 3)
        self.assertEqual(contexto.exception.causa, "filtro_ausente")
        for filtro in ("", "acesso eq 'corretor'", "search.in(acesso,'compartilhado',',') or true"):
            with self.subTest(filtro=filtro), self.assertRaises(la.ErroAcesso):
                exigente.consultar("pergunta", None, 3, filtro)
        self.assertEqual(exigente._documentos.chamadas, [], "o serviço de busca nunca foi chamado")


# --------------------------------------------------------------------------------------
# Recuperação e serviço: o filtro age antes de qualquer trecho chegar ao modelo
# --------------------------------------------------------------------------------------

class ServicoL300Tests(unittest.TestCase):
    def test_o_modelo_recebe_so_trechos_das_classes_do_perfil_nos_tres_modos(self):
        for modo in ("texto", "vetorial", "hibrida"):
            for rotulo, (papeis, permitidas) in PERMITIDOS.items():
                with self.subTest(modo=modo, perfil=rotulo):
                    pilha = Pilha(modo=modo)
                    contexto = la.autorizar(papeis)
                    resposta = pilha.servico.perguntar(PERGUNTA, contexto)
                    entrada = pilha.entrada_do_modelo()
                    for classe, marcador in MARCADORES.items():
                        self.assertEqual(marcador in entrada, classe in permitidas, f"{classe!r} no pedido ao modelo")
                    (consulta,) = pilha.indice.consultas
                    self.assertEqual((consulta["filtro"], consulta["vetor"]), (contexto.filtro, modo != "texto"))
                    esperados = ["embeddings", "busca", "modelo"] if modo != "texto" else ["busca", "modelo"]
                    self.assertEqual(pilha.eventos, esperados, "a busca com filtro vem antes do modelo")
                    self.assertEqual(resposta.situacao, lp.RESPONDIDA)
                    ids_citados = {evidencia.id for evidencia in resposta.evidencias}
                    self.assertTrue(ids_citados <= {item["id"] for item in TRECHOS if item["acesso"] in permitidas})

    def test_sem_trecho_autorizado_a_resposta_e_generica_e_o_modelo_nao_e_chamado(self):
        so_do_atendimento = [item for item in TRECHOS if item["acesso"] == "atendimento"]
        pilha = Pilha(IndiceAcessoFalso(trechos=so_do_atendimento))
        resposta = pilha.servico.perguntar(PERGUNTA, la.autorizar([la.PAPEL_CORRETOR]))
        self.assertEqual((resposta.tipo, resposta.situacao, resposta.texto, resposta.evidencias),
                         (lp.SEM_EVIDENCIA, lp.RECUSADA, lp.MENSAGEM_SEM_EVIDENCIA, ()))
        self.assertEqual(pilha.geracao.chamadas, [], "nenhum conteúdo não autorizado chega ao modelo")
        publico = str(resposta.a_dict())
        for oculto in (so_do_atendimento[0]["id"], so_do_atendimento[0]["fonte"], MARCADORES["atendimento"]):
            self.assertNotIn(oculto, publico, "a resposta não revela que o documento existe")

    def test_sem_contexto_de_acesso_nada_e_buscado_nem_calculado_nem_enviado(self):
        pilha = Pilha()
        with self.assertRaises(lc.ErroChat) as contexto:
            pilha.servico.perguntar(PERGUNTA)
        self.assertEqual((contexto.exception.codigo, contexto.exception.causa), (lc.NAO_AUTORIZADO, "sem_contexto_de_acesso"))
        for ajudante in (pilha.servico.recuperador.recuperar, ):
            with self.assertRaises(la.ErroAcesso):
                ajudante(PERGUNTA, "hibrida", 3)
        self.assertEqual(pilha.eventos, [], "nem embeddings, nem busca, nem modelo")

    def test_trecho_fora_do_perfil_devolvido_pelo_indice_interrompe_a_requisicao_sem_chamar_o_modelo(self):
        pilha = Pilha(IndiceQueIgnoraOFiltro())
        with self.assertRaises(la.ErroAcesso) as contexto:
            pilha.servico.perguntar(PERGUNTA, la.autorizar([la.PAPEL_CORRETOR]))
        publico = lc.classificar_erro(contexto.exception)
        self.assertEqual((publico.codigo, publico.causa), (lc.INDISPONIVEL, "resultado_fora_do_perfil"))
        self.assertEqual(pilha.geracao.chamadas, [])

    def test_o_filtro_autoriza_classes_e_nao_limita_os_ids_ao_manifesto_da_ingestao(self):
        """O manifesto rege o que a ferramenta de ingestão envia; na consulta, só a classe do trecho decide."""
        fora_do_manifesto = {**trecho("compartilhado", 90), "documento_id": "VLAR-FORA-DO-MANIFESTO-9.9"}
        pilha = Pilha(IndiceAcessoFalso(trechos=[fora_do_manifesto]))
        pilha.servico.perguntar(PERGUNTA, la.autorizar([la.PAPEL_CORRETOR]))
        self.assertIn("VLAR-FORA-DO-MANIFESTO-9.9", pilha.entrada_do_modelo())

    def test_o_servico_nao_guarda_estado_de_quem_perguntou(self):
        pilha = Pilha()
        antes = dict(vars(pilha.servico))
        pilha.servico.perguntar(PERGUNTA, la.autorizar([la.PAPEL_ATENDIMENTO]))
        pilha.servico.perguntar(PERGUNTA, la.autorizar([la.PAPEL_CORRETOR]))
        self.assertEqual(vars(pilha.servico), antes)
        self.assertNotIn(MARCADORES["atendimento"], pilha.geracao.chamadas[1]["input"], "o perfil anterior não vaza para o seguinte")


# --------------------------------------------------------------------------------------
# Configuração
# --------------------------------------------------------------------------------------

class ConfiguracaoL300Tests(unittest.TestCase):
    L300 = {lc.VAR_EXIGIR_ACESSO_DOCUMENTAL: "true"}

    def test_opcao_desligada_por_padrao_mantem_o_indice_e_o_comportamento_do_l200(self):
        padrao = lc.carregar_configuracao(ambiente())
        self.assertEqual((padrao.exigir_acesso_documental, padrao.indice), (False, "vareleira-lar-l200"))
        self.assertIn("acesso_documental=nao", lc.resumo_publico(padrao))
        explicita = lc.carregar_configuracao(ambiente({lc.VAR_EXIGIR_ACESSO_DOCUMENTAL: "false"}))
        self.assertEqual((explicita.exigir_acesso_documental, explicita.indice), (False, "vareleira-lar-l200"))

    def test_opcao_ligada_usa_o_indice_do_l300_e_so_aceita_indices_do_l300(self):
        ligada = lc.carregar_configuracao(ambiente(self.L300))
        self.assertEqual((ligada.exigir_acesso_documental, ligada.indice), (True, "vareleira-lar-l300"))
        self.assertIn("acesso_documental=sim", lc.resumo_publico(ligada))
        self.assertEqual(lc.carregar_configuracao(ambiente({**self.L300, lc.VAR_INDICE: "vareleira-lar-l300-teste"})).indice,
                         "vareleira-lar-l300-teste")
        for indice in ("vareleira-lar-l100", "vareleira-lar-l200", "vareleira-lar-l3000", "outro-indice"):
            with self.subTest(indice=indice), self.assertRaises(lc.ErroConfiguracao) as erro:
                lc.carregar_configuracao(ambiente({**self.L300, lc.VAR_INDICE: indice}))
            self.assertIn(lc.VAR_INDICE, str(erro.exception))
            self.assertNotIn(indice, str(erro.exception), "o valor recebido não é repetido")

    def test_opcao_ligada_exige_nuvem_autenticacao_e_tenant(self):
        for rotulo, variaveis, sem in (("sem autenticação", {**self.L300, lc.VAR_EXIGIR_AUTENTICACAO: "false"}, ()),
                                       ("sem tenant", self.L300, (lc.VAR_TENANT_AUTORIZADO,)),
                                       ("valor inválido", {lc.VAR_EXIGIR_ACESSO_DOCUMENTAL: "talvez"}, ())):
            with self.subTest(rotulo=rotulo), self.assertRaises(lc.ErroConfiguracao):
                lc.carregar_configuracao(ambiente(variaveis, sem))
        for modo in (lc.MODO_DEMO, lc.MODO_LOCAL):
            with self.subTest(modo=modo), self.assertRaises(lc.ErroConfiguracao) as erro:
                lc.carregar_configuracao(ambiente(self.L300), modo=modo, host="127.0.0.1")
            self.assertIn(lc.VAR_EXIGIR_ACESSO_DOCUMENTAL, str(erro.exception))
        for rotulo, configuracao in {"índice do L200": config(exigir_acesso_documental=True),
                                     "demonstração": config_l300(modo=lc.MODO_DEMO, host="127.0.0.1"),
                                     "local": config_l300(modo=lc.MODO_LOCAL, host="127.0.0.1", exigir_autenticacao=False),
                                     "sem tenant": config_l300(tenants_autorizados=frozenset())}.items():
            with self.subTest(rotulo=rotulo), self.assertRaises(lc.ErroConfiguracao):
                lc.validar_configuracao(configuracao)
        lc.validar_configuracao(config_l300())

    @PRECISA_DO_HTTP
    def test_na_linha_de_comando_a_opcao_nao_combina_com_demo_nem_com_local(self):
        for opcao in ("--demo", "--local-sem-autenticacao"):
            with self.subTest(opcao=opcao):
                codigo, texto, servidor_falso = rodar_chat([opcao], {**ambiente(self.L300)})
                self.assertEqual(codigo, lab_comum.CODIGO_USO, texto)
                self.assertIn(lc.VAR_EXIGIR_ACESSO_DOCUMENTAL, texto)
                servidor_falso.assert_not_called()


# --------------------------------------------------------------------------------------
# API do chat
# --------------------------------------------------------------------------------------

@PRECISA_DO_HTTP
class ApiL300Tests(unittest.TestCase):
    def pergunta(self, cliente, corpo=None, **opcoes):
        return perguntar_pela_api(cliente, corpo, **opcoes)

    def test_sem_papel_conhecido_e_403_antes_de_buscar_calcular_embeddings_ou_chamar_o_modelo(self):
        pilha = Pilha()
        invalidos = {"sem papéis": cabecalhos(), "papel desconhecido": cabecalhos("Vareleira.Admin"),
                     "outra caixa": cabecalhos("vareleira.atendimento"), "espaço no fim": cabecalhos("Vareleira.Corretor "),
                     "papel em claim de grupo": cabecalhos(la.PAPEL_ATENDIMENTO, tipo="groups"),
                     "papel em claim escopo": cabecalhos(la.PAPEL_CORRETOR, tipo="scp")}
        with servidor(pilha.servico, config_l300()) as cliente:
            for rotulo, cabecalho in invalidos.items():
                with self.subTest(rotulo=rotulo):
                    for resposta in (self.pergunta(cliente, cabecalhos=cabecalho), cliente.get("/", headers=cabecalho)):
                        self.assertEqual((resposta.status_code, resposta.json()["erro"]), (403, lc.NAO_AUTORIZADO))
                        self.assertEqual(resposta.json()["mensagem"], lc.MENSAGENS[lc.NAO_AUTORIZADO])
            self.assertEqual(pilha.eventos, [], "nada foi buscado, calculado nem enviado ao modelo")
            self.assertEqual(self.pergunta(cliente, cabecalhos=cabecalhos(la.PAPEL_ATENDIMENTO)).status_code, 200)
            self.assertEqual(pilha.eventos, ["embeddings", "busca", "modelo"])

    def test_perfis_distintos_recebem_so_o_que_o_perfil_permite(self):
        for rotulo, (papeis, permitidas) in PERMITIDOS.items():
            with self.subTest(perfil=rotulo):
                pilha = Pilha()
                with servidor(pilha.servico, config_l300()) as cliente:
                    resposta = self.pergunta(cliente, cabecalhos=cabecalhos(*papeis))
                self.assertEqual(resposta.status_code, 200, resposta.text)
                entrada = pilha.entrada_do_modelo()
                for classe, marcador in MARCADORES.items():
                    self.assertEqual(marcador in entrada, classe in permitidas, classe)
                self.assertNotIn("acesso", resposta.text.replace("acesso documental", ""), "a classe não é exposta ao navegador")

    def test_permissoes_nao_vem_do_json_nem_da_query_nem_de_outros_cabecalhos(self):
        pilha = Pilha()
        enviados = {"papeis": ["Vareleira.Corretor"], "roles": ["Vareleira.Corretor"], "acesso": "corretor", "perfil": "corretor",
                    "classes": ["corretor"], "tenant": TENANT, "usuario": "alguem", "indice": "vareleira-lar-l200",
                    "filtro": "search.in(acesso,'corretor',',')"}
        with servidor(pilha.servico, config_l300()) as cliente:
            atendimento = cabecalhos(la.PAPEL_ATENDIMENTO)
            for campo, valor in enviados.items():
                with self.subTest(campo=campo):
                    resposta = self.pergunta(cliente, {"pergunta": PERGUNTA_GERAL, campo: valor}, cabecalhos=atendimento)
                    self.assertEqual((resposta.status_code, resposta.json()["erro"]), (422, lc.CAMPOS_NAO_PERMITIDOS))
            for consulta in ("?acesso=corretor", "?papel=Vareleira.Corretor", "?filtro=true", "?indice=vareleira-lar-l200"):
                with self.subTest(consulta=consulta):
                    resposta = cliente.post("/api/perguntar" + consulta, json={"pergunta": PERGUNTA_GERAL}, headers=atendimento)
                    self.assertEqual((resposta.status_code, resposta.json()["erro"]), (422, lc.CAMPOS_NAO_PERMITIDOS))
            self.assertEqual(pilha.eventos, [], "pedido que tenta definir permissões nunca chega ao serviço")
            outros = {**atendimento, "x-roles": "Vareleira.Corretor", "x-acesso": "corretor", "x-ms-client-principal-roles": "Vareleira.Corretor"}
            self.assertEqual(self.pergunta(cliente, cabecalhos=outros).status_code, 200)
            self.assertNotIn(MARCADORES["corretor"], pilha.entrada_do_modelo())
            self.assertIn(MARCADORES["atendimento"], pilha.entrada_do_modelo())

    def test_dois_usuarios_ao_mesmo_tempo_ficam_isolados(self):
        for rodada in range(3):
            with self.subTest(rodada=rodada):
                barreira = threading.Barrier(2, timeout=10)
                pilha = Pilha(IndiceAcessoFalso(ao_consultar=lambda classes: barreira.wait()))
                with servidor(pilha.servico, config_l300()) as cliente, ThreadPoolExecutor(2) as pool:
                    atendimento = pool.submit(self.pergunta, cliente, cabecalhos=cabecalhos(la.PAPEL_ATENDIMENTO))
                    corretor = pool.submit(self.pergunta, cliente, cabecalhos=cabecalhos(la.PAPEL_CORRETOR))
                    respostas = {"atendimento": atendimento.result(timeout=20), "corretor": corretor.result(timeout=20)}
                self.assertEqual([resposta.status_code for resposta in respostas.values()], [200, 200])
                por_filtro = {}
                for chamada in pilha.geracao.chamadas:
                    classe_unica = [classe for classe in ("atendimento", "corretor") if MARCADORES[classe] in chamada["input"]]
                    self.assertEqual(len(classe_unica), 1, "cada pedido ao modelo traz a classe restrita de uma só pessoa")
                    por_filtro[classe_unica[0]] = chamada["input"]
                self.assertEqual(set(por_filtro), {"atendimento", "corretor"})
                self.assertNotIn(MARCADORES["corretor"], por_filtro["atendimento"])
                self.assertNotIn(MARCADORES["atendimento"], por_filtro["corretor"])
                for rotulo, resposta in respostas.items():
                    fontes = {evidencia["fonte"] for evidencia in resposta.json()["evidencias"]}
                    proibidas = {item["fonte"] for item in TRECHOS if item["acesso"] == ("corretor" if rotulo == "atendimento" else "atendimento")}
                    self.assertFalse(fontes & proibidas, rotulo)

    def test_indice_com_trecho_fora_do_perfil_vira_503_sem_chamar_o_modelo_nem_expor_o_trecho(self):
        pilha = Pilha(IndiceQueIgnoraOFiltro())
        with self.assertLogs("vareleira.chat", "INFO") as registro, servidor(pilha.servico, config_l300()) as cliente:
            resposta = self.pergunta(cliente, cabecalhos=cabecalhos(la.PAPEL_CORRETOR))
        self.assertEqual((resposta.status_code, resposta.json()["erro"]), (503, lc.INDISPONIVEL))
        self.assertEqual(pilha.geracao.chamadas, [])
        for oculto in MARCADORES.values():
            self.assertNotIn(oculto, resposta.text)
        self.assertIn("causa=resultado_fora_do_perfil", "\n".join(registro.output))

    def test_com_a_opcao_ligada_o_chat_nao_inicia_com_servico_que_nao_aplica_o_filtro(self):
        with self.assertRaises(lab_comum.ErroLab), servidor(ServicoFalso(), config_l300()):
            pass

    def test_com_a_opcao_desligada_o_l200_segue_igual_sem_exigir_papeis(self):
        servico = ServicoFalso()
        with servidor(servico, config()) as cliente:
            sem_papel = self.pergunta(cliente, cabecalhos=cabecalhos())
            com_papel_invalido = self.pergunta(cliente, cabecalhos=cabecalhos("Vareleira.Admin"))
            pronta = cliente.get("/readyz")
        self.assertEqual([sem_papel.status_code, com_papel_invalido.status_code], [200, 200])
        self.assertEqual(len(servico.perguntas), 2, "o serviço do L200 é chamado só com a pergunta, como antes")
        self.assertEqual(pronta.json(), {"situacao": "pronto", "modo": lc.MODO_NUVEM})


if __name__ == "__main__":
    unittest.main()
