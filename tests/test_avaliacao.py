import contextlib
import io
import json
import logging
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import support  # noqa: F401  (configura o caminho dos scripts)
import avaliar_respostas
import lab_agente
import lab_avaliacao as lv
import lab_comum
import lab_geracao as lg
import lab_indexacao as li
import lab_politica as lp
from support import OpenAIGeracaoFalso, RAIZ, ServicoRespostasFalso, copiar_pacote, erro_openai, indexar_pacote, rodar_script

BUSCA, MODELOS = "srch-vlr-exemplo", "ais-vlr-exemplo"
DIMENSOES = 8


def alternativa(documento="VLAR-CG-1.0", texto="dez dias corridos"):
    return {"documento_id": documento, "texto_contem": texto}


def pergunta_json(**campos):
    base = {"id": "X-01", "pergunta": "Qual é o prazo de pagamento?", "tipo_esperado": "documentada",
            "assuntos": [{"nome": "prazo", "alternativas": [alternativa()]}], "fatos": ["10 dias"]}
    base.update(campos)
    return base


def pergunta(identificador="X-01", tipo=lp.DOCUMENTADA, assuntos=None, fatos=("10 dias",), texto="Qual é o prazo?"):
    if assuntos is None:
        assuntos = (lv.Assunto("prazo", (lv.Alternativa("VLAR-CG-1.0", "dez dias corridos"),)),) if tipo in lv.RESPONDIVEIS else ()
    return lv.PerguntaAvaliada(identificador, texto, tipo, tuple(assuntos), tuple(fatos) if tipo in lv.RESPONDIVEIS else ())


def resultado(documento="VLAR-CG-1.0", conteudo="Paga em dez dias corridos."):
    return {"id": "T-1", "documento_id": documento, "conteudo": conteudo}


def decisao(situacao=lp.RESPONDIDA, tipo=lp.DOCUMENTADA, texto="Em 10 dias.", problemas=()):
    return lp.Decisao(situacao, tipo, tipo, texto, "", (), tuple(problemas))


def avaliada(item, decisao_obtida, entrada=100, saida=20, buscas=1, segundos=2.0):
    return lv.Avaliada(item, lv.Resposta(decisao_obtida, entrada, saida, buscas, segundos))


class ConjuntosReaisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.conjuntos = {nome: lv.carregar_conjunto(nome) for nome in lv.CONJUNTOS}

    def test_os_dois_conjuntos_tem_a_mesma_composicao(self):
        def composicao(nome):
            return sorted((item.categoria, item.tipo_esperado) for item in self.conjuntos[nome])

        self.assertEqual(composicao("ajuste"), composicao("teste"))
        self.assertEqual({len(itens) for itens in self.conjuntos.values()}, {12})
        categorias = {item.categoria for itens in self.conjuntos.values() for item in itens}
        self.assertEqual(categorias, set(lv.CATEGORIAS), "todas as categorias têm pelo menos uma pergunta")

    def test_ids_e_perguntas_nao_se_repetem_entre_os_conjuntos(self):
        todas = [item for itens in self.conjuntos.values() for item in itens]
        self.assertEqual(len({item.id for item in todas}), len(todas))
        self.assertEqual(len({lp.normalizar(item.pergunta) for item in todas}), len(todas))
        self.assertTrue(all(item.id.startswith("AJ-") for item in self.conjuntos["ajuste"]))
        self.assertTrue(all(item.id.startswith("TE-") for item in self.conjuntos["teste"]))

    def test_toda_evidencia_esperada_existe_nos_trechos_dos_documentos_locais(self):
        inventario = lab_comum.carregar_e_validar()
        documentos = [(documento, lab_comum.ler_conteudo(documento).decode("utf-8")) for documento in inventario.documentos]
        trechos = li.dividir_documentos(documentos)
        problemas = lv.verificar_conjuntos(self.conjuntos, trechos, [texto for _, texto in documentos])
        self.assertEqual(problemas, [])

    def test_as_perguntas_de_teste_nao_aparecem_em_guias_registros_nem_instrucoes(self):
        textos = [lp.INSTRUCOES_COMPLETAS, lg.INSTRUCOES, lab_agente.INSTRUCOES_DE_BUSCA]
        for pasta in ("desafios", "docs", ".github"):
            textos.extend(caminho.read_text(encoding="utf-8") for caminho in (RAIZ / pasta).rglob("*.md"))
        textos.extend((RAIZ / nome).read_text(encoding="utf-8") for nome in ("README.md", "CONTRIBUTING.md"))
        base = lp.normalizar("\n".join(textos))
        for item in self.conjuntos["teste"]:
            self.assertNotIn(lp.normalizar(item.pergunta), base, f"{item.id} vazou para um texto público")

    def test_as_perguntas_dos_conjuntos_nao_repetem_as_de_conferencia_do_desafio_02(self):
        conferencia = {lp.normalizar(item.pergunta) for item in li.carregar_perguntas()}
        for itens in self.conjuntos.values():
            for item in itens:
                self.assertNotIn(lp.normalizar(item.pergunta), conferencia, item.id)

    def test_perguntas_individuais_tem_possessivo_e_assunto_de_seguro_e_as_documentadas_nao(self):
        for itens in self.conjuntos.values():
            for item in itens:
                if item.tipo_esperado == lp.CONTRATACAO_INDIVIDUAL:
                    self.assertTrue(lp.parece_contratacao_individual(item.pergunta), item.id)
                elif item.tipo_esperado == lp.DOCUMENTADA:
                    self.assertFalse(lp.parece_contratacao_individual(item.pergunta), item.id)


class CarregadorTests(unittest.TestCase):
    def setUp(self):
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)

    def carregar(self, perguntas, **cabecalho):
        dados = {"schema_version": 1, "sintetico": True, "conjunto": "ajuste", "perguntas": perguntas}
        dados.update(cabecalho)
        (Path(self.pasta.name) / "ajuste.json").write_text(json.dumps(dados), encoding="utf-8")
        return lv.carregar_conjunto("ajuste", self.pasta.name)

    def recusa(self, perguntas, trecho, **cabecalho):
        with self.assertRaises(lab_comum.ErroLab) as contexto:
            self.carregar(perguntas, **cabecalho)
        self.assertIn(trecho, str(contexto.exception))

    def test_conjunto_valido_vira_perguntas_com_categoria_e_situacao_esperada(self):
        itens = self.carregar([
            pergunta_json(id="A-1"),
            pergunta_json(id="A-2", assuntos=[{"nome": "a", "alternativas": [alternativa()]},
                                              {"nome": "b", "alternativas": [alternativa()]}]),
            pergunta_json(id="A-3", tipo_esperado="contratacao_individual"),
            pergunta_json(id="A-4", tipo_esperado="sem_evidencia", assuntos=[], fatos=[]),
            pergunta_json(id="A-5", tipo_esperado="fora_de_escopo", assuntos=[], fatos=[]),
            pergunta_json(id="A-6", tipo_esperado="ambigua", assuntos=[], fatos=[]),
        ])
        self.assertEqual([item.categoria for item in itens],
                         ["simples", "composta", "individual", "sem evidência", "fora de escopo", "ambígua"])
        self.assertEqual([item.situacao_esperada for item in itens],
                         [lp.RESPONDIDA, lp.RESPONDIDA, lp.RESPONDIDA, lp.RECUSADA, lp.RECUSADA, lp.ESCLARECIMENTO])
        self.assertEqual([item.tem_resposta for item in itens], [True, True, True, False, False, False])

    def test_arquivo_ausente_e_json_invalido(self):
        with self.assertRaisesRegex(lab_comum.ErroLab, "não encontrado"):
            lv.carregar_conjunto("ajuste", self.pasta.name)
        (Path(self.pasta.name) / "ajuste.json").write_text("{ não é json", encoding="utf-8")
        with self.assertRaisesRegex(lab_comum.ErroLab, "JSON inválido"):
            lv.carregar_conjunto("ajuste", self.pasta.name)

    def test_cabecalho_e_estrutura_invalidos(self):
        self.recusa([pergunta_json()], "schema_version", schema_version=2)
        self.recusa([pergunta_json()], "sintetico", sintetico=False)
        self.recusa([pergunta_json()], "\"conjunto\": \"ajuste\"", conjunto="teste")
        self.recusa([], "pelo menos um item")

    def test_regras_de_cada_pergunta(self):
        casos = {
            "repetido": ([pergunta_json(), pergunta_json()], "ausente, fora do formato ou repetido"),
            "id invalido": ([pergunta_json(id="a b")], "fora do formato"),
            "pergunta vazia": ([pergunta_json(pergunta="  ")], "'pergunta' ausente"),
            "tipo": ([pergunta_json(tipo_esperado="outro")], "'tipo_esperado' deve ser"),
            "sem assuntos": ([pergunta_json(assuntos=[])], "precisa de pelo menos um assunto"),
            "recusa com assuntos": ([pergunta_json(tipo_esperado="sem_evidencia", fatos=[])], "não tem evidência esperada"),
            "sem fatos": ([pergunta_json(fatos=[])], "precisa de pelo menos um fato"),
            "recusa com fatos": ([pergunta_json(tipo_esperado="fora_de_escopo", assuntos=[])], "não tem fatos esperados"),
            "fato vazio": ([pergunta_json(fatos=[""])], "lista de textos não vazios"),
            "assunto sem alternativas": ([pergunta_json(assuntos=[{"nome": "a", "alternativas": []}])], "precisa de 'nome'"),
            "alternativa incompleta": ([pergunta_json(assuntos=[{"nome": "a", "alternativas": [{"documento_id": "X"}]}])],
                                       "precisa de 'documento_id' e 'texto_contem'"),
            "assunto repetido": ([pergunta_json(assuntos=[{"nome": "a", "alternativas": [alternativa()]},
                                                          {"nome": "a", "alternativas": [alternativa()]}])], "está repetido"),
        }
        for rotulo, (perguntas, trecho) in casos.items():
            with self.subTest(rotulo):
                self.recusa(perguntas, trecho)

    def test_selecionar_filtra_por_id_na_ordem_do_conjunto_e_recusa_id_desconhecido(self):
        itens = self.carregar([pergunta_json(id="A-1"), pergunta_json(id="A-2", pergunta="Outra?"),
                               pergunta_json(id="A-3", pergunta="Mais uma?")])
        self.assertEqual([item.id for item in lv.selecionar(itens, "A-3, A-1")], ["A-1", "A-3"])
        self.assertEqual(len(lv.selecionar(itens, None)), 3)
        with self.assertRaisesRegex(lab_comum.ErroLab, "Ids fora do conjunto: A-9"):
            lv.selecionar(itens, "A-1,A-9")
        with self.assertRaises(lab_comum.ErroLab):
            lv.selecionar(itens, " , ")


class VerificacaoDosConjuntosTests(unittest.TestCase):
    def trecho(self, documento_id="VLAR-CG-1.0", conteudo="O pagamento ocorre em dez dias corridos."):
        documento = lab_comum.Documento(
            id=documento_id, titulo="T", tipo="faq", produto="p", versao="1.0", arquivo=Path("a.md"), blob="a.md",
            tipo_conteudo="text/markdown", tamanho_bytes=1, sha256="0" * 64, revisao_status="pendente",
            vigencia_inicio="2025-01-01", vigencia_fim=None)
        return li.Trecho("T-1", documento, 1, "S", "", conteudo)

    def verificar(self, conjuntos, trechos=None, textos=("O pagamento ocorre em dez dias corridos.",)):
        return lv.verificar_conjuntos(conjuntos, trechos or [self.trecho()], list(textos))

    def test_conjuntos_coerentes_nao_tem_problemas(self):
        self.assertEqual(self.verificar({"ajuste": [pergunta()]}), [])

    def test_alternativa_inalcancavel_e_assunto_sem_nenhuma_alternativa_alcancavel(self):
        inalcancavel = pergunta(assuntos=(lv.Assunto("prazo", (lv.Alternativa("VLAR-CG-1.0", "quinze dias"),)),))
        problemas = self.verificar({"ajuste": [inalcancavel]})
        self.assertTrue(any("não aparece em nenhum trecho" in problema for problema in problemas))
        self.assertTrue(any("nenhuma alternativa do assunto 'prazo'" in problema for problema in problemas))

    def test_documento_inexistente(self):
        outro = pergunta(assuntos=(lv.Assunto("prazo", (lv.Alternativa("VLAR-XX-9.9", "dez dias"),)),))
        self.assertTrue(any("não existe no inventário" in problema for problema in self.verificar({"ajuste": [outro]})))

    def test_pergunta_copiada_dos_documentos_e_repeticoes_entre_conjuntos(self):
        copiada = pergunta(texto="O pagamento ocorre em dez dias corridos.")
        self.assertTrue(any("aparece nos documentos" in problema for problema in self.verificar({"ajuste": [copiada]})))
        repetida = {"ajuste": [pergunta(identificador="A-1", texto="Qual é o prazo?")],
                    "teste": [pergunta(identificador="A-1", texto="qual é o  PRAZO?")]}
        problemas = self.verificar(repetida)
        self.assertTrue(any("o id também existe em ajuste" in problema for problema in problemas))
        self.assertTrue(any("repete a de ajuste/A-1" in problema for problema in problemas))


class MetricasDeBuscaTests(unittest.TestCase):
    def composta(self):
        return pergunta(assuntos=(
            lv.Assunto("prazo", (lv.Alternativa("VLAR-CG-1.0", "dez dias corridos"), lv.Alternativa("VLAR-FAQ-1.0", "10 dias"))),
            lv.Assunto("valor", (lv.Alternativa("VLAR-CG-1.0", "R$ 400,00"),))))

    def test_assunto_coberto_por_qualquer_alternativa_ignorando_maiusculas(self):
        item = self.composta()
        self.assertEqual(lv.assuntos_cobertos(item, [resultado(conteudo="PAGA EM DEZ DIAS CORRIDOS")]), {"prazo"})
        self.assertEqual(lv.assuntos_cobertos(item, [resultado("VLAR-FAQ-1.0", "Em 10 dias.")]), {"prazo"})

    def test_o_documento_precisa_ser_o_esperado(self):
        self.assertEqual(lv.assuntos_cobertos(self.composta(), [resultado("VLAR-GL-1.0", "dez dias corridos")]), set())

    def test_pergunta_composta_so_acerta_com_todos_os_assuntos_dentro_do_k(self):
        item = self.composta()
        resultados = [resultado(conteudo="dez dias corridos"), resultado(conteudo="nada"), resultado(conteudo="R$ 400,00")]
        self.assertEqual(lv.primeira_posicao(item, resultados), 1)
        self.assertFalse(lv.acertou(item, resultados, 1))
        self.assertFalse(lv.acertou(item, resultados, 2))
        self.assertTrue(lv.acertou(item, resultados, 3))
        medida = lv.medir_posicao(item, resultados)
        self.assertEqual((medida.primeira, medida.cobertos, medida.total), (1, 2, 2))
        self.assertEqual(dict(medida.acerto), {1: False, 3: True, 5: True, 10: True})

    def test_sem_nenhum_trecho_pertinente(self):
        medida = lv.medir_posicao(self.composta(), [resultado(conteudo="nada")] * 3)
        self.assertEqual((medida.primeira, medida.cobertos), (None, 0))
        self.assertFalse(any(medida.acerto.values()))

    def test_resumo_conta_acertos_por_k_e_calcula_o_mrr(self):
        item = pergunta()
        posicoes = [lv.medir_posicao(item, r) for r in (
            [resultado()],
            [resultado(conteudo="nada"), resultado()],
            [resultado(conteudo="nada")] * 4)]
        resumo = lv.resumir_busca("hibrida", posicoes)
        self.assertEqual(resumo.perguntas, 3)
        self.assertEqual(dict(resumo.acertos), {1: 1, 3: 2, 5: 2, 10: 2})
        self.assertAlmostEqual(resumo.mrr, (1 + 0.5 + 0) / 3)
        self.assertEqual(lv.resumir_busca("texto", []).mrr, 0.0)

    def test_avaliar_recuperacao_usa_so_perguntas_com_resposta_e_o_maior_k_em_cada_modo(self):
        chamadas = []

        class Falso:
            def recuperar(self, texto, modo, k):
                chamadas.append((texto, modo, k))
                return lg.Recuperacao([resultado()], 0)

        itens = [pergunta("A-1", texto="Com resposta?"), pergunta("A-2", lp.SEM_EVIDENCIA, texto="Sem resposta?")]
        resumos = lv.avaliar_recuperacao(itens, Falso())
        self.assertEqual([resumo.modo for resumo in resumos], list(li.MODOS_DE_BUSCA))
        self.assertEqual(chamadas, [("Com resposta?", modo, 10) for modo in li.MODOS_DE_BUSCA])
        self.assertTrue(all(resumo.perguntas == 1 for resumo in resumos))


class RespostasAvaliadasTests(unittest.TestCase):
    def test_resposta_certa_com_todos_os_fatos(self):
        item = avaliada(pergunta(fatos=("10 dias",)), decisao(texto="O prazo é de **10 dias**."))
        self.assertTrue(item.tipo_certo and item.situacao_certa)
        self.assertEqual((item.fatos_presentes, item.fatos_esperados), (1, 1))
        self.assertEqual(item.motivo, "")

    def test_fatos_faltando_e_texto_trocado_pelo_programa_contam_como_ausentes(self):
        faltando = avaliada(pergunta(fatos=("10 dias", "R$ 400,00")), decisao(texto="O prazo é de 10 dias."))
        self.assertEqual((faltando.fatos_presentes, faltando.fatos_esperados, faltando.motivo), (1, 2, "fatos 1 de 2"))
        individual = pergunta("I-1", lp.CONTRATACAO_INDIVIDUAL, fatos=("contratad",))
        trocado = avaliada(individual, decisao(tipo=lp.CONTRATACAO_INDIVIDUAL, texto=lp.TEXTO_SEM_VEREDITO))
        self.assertEqual((trocado.fatos_presentes, trocado.fatos_esperados), (0, 1))

    def test_so_a_resposta_mostrada_conta_fatos(self):
        recusada = avaliada(pergunta(), decisao(lp.RECUSADA, lp.SEM_EVIDENCIA, lp.MENSAGEM_SEM_EVIDENCIA))
        self.assertEqual(recusada.fatos_esperados, 0)
        self.assertTrue(recusada.falsa_recusa)
        self.assertEqual(recusada.motivo, "recusada, esperada respondida")
        sem_resposta = avaliada(pergunta("S-1", lp.SEM_EVIDENCIA), decisao())
        self.assertEqual(sem_resposta.fatos_esperados, 0)

    def test_falsa_recusa_e_falsa_resposta(self):
        self.assertTrue(avaliada(pergunta(), decisao(lp.ESCLARECIMENTO, lp.AMBIGUA, "Qual?")).falsa_recusa)
        self.assertFalse(avaliada(pergunta("S-1", lp.SEM_EVIDENCIA), decisao(lp.RECUSADA, lp.SEM_EVIDENCIA)).falsa_resposta)
        resposta_indevida = avaliada(pergunta("S-1", lp.SEM_EVIDENCIA), decisao(texto="Inventou."))
        self.assertTrue(resposta_indevida.falsa_resposta)
        self.assertFalse(resposta_indevida.falsa_recusa)

    def test_tipo_certo_e_independente_da_situacao(self):
        descartada = avaliada(pergunta(), decisao(lp.DESCARTADA, texto="", problemas=["a citação não é literal"]))
        self.assertTrue(descartada.tipo_certo)
        self.assertFalse(descartada.situacao_certa)
        self.assertEqual(descartada.motivo, "resposta descartada: a citação não é literal")
        tipo_errado = avaliada(pergunta("S-1", lp.SEM_EVIDENCIA), decisao(lp.RECUSADA, lp.FORA_DE_ESCOPO))
        self.assertTrue(tipo_errado.situacao_certa)
        self.assertFalse(tipo_errado.tipo_certo)
        self.assertEqual(tipo_errado.motivo, "tipo fora_de_escopo, esperado sem_evidencia")

    def test_erro_de_formato_nao_tem_decisao(self):
        erro = avaliada(pergunta(), None)
        self.assertEqual((erro.tipo, erro.situacao, erro.tipo_certo, erro.situacao_certa), (lv.ERRO, lv.ERRO, False, False))
        self.assertEqual(erro.motivo, "o modelo respondeu fora do formato")

    def test_resumo_e_resumo_por_categoria(self):
        itens = [
            avaliada(pergunta("A-1", fatos=("10 dias",)), decisao(texto="10 dias"), entrada=100, saida=10, buscas=1, segundos=2),
            avaliada(pergunta("A-2", fatos=("10 dias",)), decisao(lp.RECUSADA, lp.SEM_EVIDENCIA), entrada=300, saida=30, buscas=2, segundos=4),
            avaliada(pergunta("A-3", lp.SEM_EVIDENCIA), decisao(texto="inventou"), entrada=200, saida=20, buscas=0, segundos=6),
            avaliada(pergunta("A-4", fatos=("10 dias",)), decisao(lp.DESCARTADA, texto="", problemas=["x"]), entrada=0, saida=0, buscas=1, segundos=0),
            avaliada(pergunta("A-5", lp.FORA_DE_ESCOPO), None, entrada=0, saida=0, buscas=1, segundos=0),
        ]
        resumo = lv.resumir(itens)
        self.assertEqual((resumo.total, resumo.tipo_certo, resumo.situacao_certa), (5, 2, 1))
        self.assertEqual((resumo.descartadas, resumo.erros, resumo.falsas_recusas, resumo.falsas_respostas), (1, 1, 1, 1))
        self.assertEqual((resumo.fatos_presentes, resumo.fatos_esperados), (1, 1))
        self.assertAlmostEqual(resumo.tokens_entrada, 120)
        self.assertAlmostEqual(resumo.buscas, 1.0)
        self.assertAlmostEqual(resumo.segundos, 2.4)
        por_categoria = lv.resumir_por_categoria(itens)
        self.assertEqual(list(por_categoria), ["simples", "sem evidência", "fora de escopo"])
        self.assertEqual(por_categoria["simples"].total, 3)
        self.assertEqual(lv.resumir([]).total, 0)

    def test_avaliar_respostas_chama_o_respondedor_na_ordem_e_avisa_cada_conclusao(self):
        avisadas = []
        itens = [pergunta("A-1"), pergunta("A-2", texto="Outra?")]
        resultado_final = lv.avaliar_respostas(
            itens, lambda item: lv.Resposta(decisao(), 1, 1, 1, 0.1), lambda item: avisadas.append(item.pergunta.id))
        self.assertEqual([item.pergunta.id for item in resultado_final], ["A-1", "A-2"])
        self.assertEqual(avisadas, ["A-1", "A-2"])


class RespondedorFixoTests(unittest.TestCase):
    class RecuperadorFalso:
        def __init__(self, resultados):
            self.resultados, self.chamadas = resultados, []

        def recuperar(self, texto, modo, k):
            self.chamadas.append((texto, modo, k))
            return lg.Recuperacao(self.resultados, 3)

    def trechos(self):
        return [{"id": "VLAR-CG-1_0-001", "documento_id": "VLAR-CG-1.0", "titulo_documento": "T", "secao": "S",
                 "clausulas": "1", "conteudo": "O pagamento ocorre em até 10 dias corridos depois do acordo.",
                 "fonte": "a.md", "versao": "1.0"}]

    def respondedor(self, geracao, trechos=None):
        recuperador = self.RecuperadorFalso(self.trechos() if trechos is None else trechos)
        cliente = lg.ClienteGeracao(geracao, "geracao", MODELOS)
        return lv.criar_respondedor_fixo(recuperador, cliente, "hibrida", 4), recuperador

    def test_busca_uma_vez_com_a_pergunta_inteira_e_aplica_a_politica(self):
        geracao = OpenAIGeracaoFalso()
        geracao.responder = lambda argumentos: {
            "tipo": lp.DOCUMENTADA, "resposta": "Até 10 dias.",
            "evidencias": [{"fonte": "VLAR-CG-1_0-001", "citacao": "O pagamento ocorre em até 10 dias corridos"}]}
        responder, recuperador = self.respondedor(geracao)
        resposta = responder(pergunta(texto="Em quantos dias paga?"))
        self.assertEqual(recuperador.chamadas, [("Em quantos dias paga?", "hibrida", 4)])
        self.assertEqual(resposta.decisao.situacao, lp.RESPONDIDA)
        self.assertEqual(resposta.buscas, 1)
        self.assertGreater(resposta.tokens_entrada, 0)
        self.assertEqual(geracao.chamadas[0]["instructions"], lp.INSTRUCOES_COMPLETAS)

    def test_citacao_inventada_vira_resposta_descartada(self):
        geracao = OpenAIGeracaoFalso()
        geracao.responder = lambda argumentos: {
            "tipo": lp.DOCUMENTADA, "resposta": "Inventou.",
            "evidencias": [{"fonte": "VLAR-CG-1_0-001", "citacao": "Esta frase não existe em nenhum trecho."}]}
        resposta = self.respondedor(geracao)[0](pergunta())
        self.assertEqual(resposta.decisao.situacao, lp.DESCARTADA)

    def test_sem_trechos_nao_chama_o_modelo_e_conta_como_sem_evidencia(self):
        geracao = OpenAIGeracaoFalso()
        resposta = self.respondedor(geracao, trechos=[])[0](pergunta())
        self.assertEqual((resposta.decisao.situacao, resposta.decisao.tipo), (lp.RECUSADA, lp.SEM_EVIDENCIA))
        self.assertEqual((resposta.tokens_entrada, geracao.chamadas), (0, []))

    def test_formato_inesperado_vira_resposta_sem_decisao_e_a_medicao_continua(self):
        geracao = OpenAIGeracaoFalso()
        geracao.texto = "isto não é JSON"
        resposta = self.respondedor(geracao)[0](pergunta())
        self.assertIsNone(resposta.decisao)

    def test_erros_do_servico_interrompem_a_medicao(self):
        geracao = OpenAIGeracaoFalso()
        geracao.erro = erro_openai("RateLimitError", 429)
        with self.assertRaises(lab_comum.ErroLab) as contexto:
            self.respondedor(geracao)[0](pergunta())
        self.assertNotIsInstance(contexto.exception, lg.ErroDeFormato)

    def test_erro_de_formato_e_um_erro_do_laboratorio(self):
        with self.assertRaises(lg.ErroDeFormato) as contexto:
            lg.ler_saida("isto não é JSON", lg.CONTRATO_BASICO)
        self.assertIsInstance(contexto.exception, lab_comum.ErroLab)


class AvaliarRespostasCLITests(unittest.TestCase):
    """O script completo, com os dublês do índice, dos embeddings e do modelo no lugar do Azure."""

    def setUp(self):
        self.pasta, self.inventario = copiar_pacote()
        self.addCleanup(self.pasta.cleanup)
        self.indice, self.embeddings = indexar_pacote(self.inventario, BUSCA, MODELOS, DIMENSOES)
        self.chamadas_de_embeddings = len(self.embeddings.chamadas)
        self.geracao = OpenAIGeracaoFalso()
        self.geracao.responder = self.modelo_perfeito
        self.servico: ServicoRespostasFalso | None = None
        self.conjuntos = {nome: {item.pergunta: item for item in lv.carregar_conjunto(nome)} for nome in lv.CONJUNTOS}
        self.addCleanup(logging.getLogger("agent_framework").setLevel, logging.NOTSET)

    def item_da_entrada(self, entrada):
        pergunta_pedida = entrada.rsplit("Pergunta: ", 1)[1].strip()
        return next(itens[pergunta_pedida] for itens in self.conjuntos.values() if pergunta_pedida in itens)

    def resposta_para(self, item, identificador, texto_do_trecho):
        if item.tipo_esperado in lv.RESPONDIVEIS:
            return {"tipo": item.tipo_esperado, "resposta": "Resposta com " + " e ".join(item.fatos) + ".",
                    "evidencias": [{"fonte": identificador, "citacao": texto_do_trecho.strip()[-60:]}]}
        return {"tipo": item.tipo_esperado, "resposta": "Qual assunto?" if item.tipo_esperado == lp.AMBIGUA else "",
                "evidencias": []}

    def modelo_perfeito(self, argumentos):
        item = self.item_da_entrada(argumentos["input"])
        identificador, texto = ServicoRespostasFalso.primeiro_trecho({"input": [{"content": [{"text": argumentos["input"]}]}]})
        return self.resposta_para(item, identificador, texto)

    def avaliar(self, *opcoes, etapa="respostas", conjunto="ajuste"):
        argumentos = ["--etapa", etapa, "--busca", BUSCA, "--modelos", MODELOS, "--dimensoes", str(DIMENSOES),
                      "--modo", "vetorial", "--k", "3", *opcoes]
        if conjunto:
            argumentos += ["--conjunto", conjunto]
        return rodar_script(avaliar_respostas, argumentos, abrir_indice=lambda *a, **k: self.indice,
                            openai=self.embeddings, geracao=self.geracao, agente=self.servico)

    def test_validar_nao_exige_busca_nem_modelos_e_nao_acessa_o_azure(self):
        codigo, saida = rodar_script(avaliar_respostas, ["--etapa", "validar"])
        self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)
        for esperado in ("Conjunto ajuste: 12 pergunta(s)", "Conjunto teste: 12 pergunta(s)", "simples 5 · composta 2",
                         "Conferência: toda evidência esperada aparece"):
            self.assertIn(esperado, saida)
        self.assertEqual(self.geracao.chamadas, [])

    def test_validar_aponta_conjuntos_que_nao_conferem_com_os_documentos(self):
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        for nome in lv.CONJUNTOS:
            dados = json.loads((lv.PASTA_DOS_CONJUNTOS / f"{nome}.json").read_text(encoding="utf-8"))
            if nome == "ajuste":
                dados["perguntas"][0]["assuntos"][0]["alternativas"] = [alternativa("VLAR-CG-1.0", "frase que não existe")]
            (Path(pasta.name) / f"{nome}.json").write_text(json.dumps(dados), encoding="utf-8")
        with mock.patch.object(lv, "PASTA_DOS_CONJUNTOS", Path(pasta.name)):
            codigo, saida = rodar_script(avaliar_respostas, ["--etapa", "validar"])
        self.assertEqual(codigo, lab_comum.CODIGO_DIVERGENCIA)
        self.assertIn("[FALHA]", saida)
        self.assertIn("frase que não existe", saida)

    def test_respostas_perfeitas_no_ajuste_dao_tudo_certo_e_mostram_o_texto_so_nas_falhas(self):
        codigo, saida = self.avaliar()
        self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)
        for esperado in ("Respostas · conjunto ajuste · 12 pergunta(s) · recuperação obrigatória · modo vetorial · k 3",
                         "Tipo da pergunta correto ........", "12 de 12", "Falsas recusas ..", "Falsas respostas ..",
                         "categoria       perguntas  tipo certo  situação certa  fatos", "composta"):
            self.assertIn(esperado, saida)
        self.assertEqual(saida.count("[ok]"), 12)
        self.assertNotIn("[falha]", saida)
        self.assertNotIn("Quanto tempo a Vareleira", saida, "sem falhas, o texto das perguntas não aparece")
        self.assertEqual(len(self.geracao.chamadas), 12)
        self.assertEqual(len(self.embeddings.chamadas) - self.chamadas_de_embeddings, 12, "uma busca vetorial por pergunta")

    def test_erros_do_modelo_aparecem_como_falhas_com_o_texto_da_pergunta_no_ajuste(self):
        def com_erros(argumentos):
            item = self.item_da_entrada(argumentos["input"])
            identificador, texto = ServicoRespostasFalso.primeiro_trecho({"input": [{"content": [{"text": argumentos["input"]}]}]})
            if item.id == "AJ-02":  # recusa o que tem resposta
                return {"tipo": lp.SEM_EVIDENCIA, "resposta": "", "evidencias": []}
            if item.id == "AJ-03":  # cita o que o trecho não diz
                return {"tipo": lp.DOCUMENTADA, "resposta": "boletim de ocorrência",
                        "evidencias": [{"fonte": identificador, "citacao": "Esta frase não existe em nenhum trecho."}]}
            if item.id == "AJ-11":  # responde o que devia recusar
                return {"tipo": lp.DOCUMENTADA, "resposta": "Inventou.",
                        "evidencias": [{"fonte": identificador, "citacao": texto.strip()[-60:]}]}
            if item.id == "AJ-05":  # formato fora do esquema
                return {"tipo": lp.DOCUMENTADA, "resposta": 5, "evidencias": []}
            return self.resposta_para(item, identificador, texto)

        self.geracao.responder = com_erros
        codigo, saida = self.avaliar()
        self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)
        for esperado in ("[falha] AJ-02", "recusada, esperada respondida", "[falha] AJ-03", "resposta descartada",
                         "[falha] AJ-11", "respondida, esperada recusada", "[falha] AJ-05", "o modelo respondeu fora do formato",
                         "Qual é a franquia da cobertura de vendaval e granizo?"):
            self.assertIn(esperado, saida)
        resumo = saida.split("Resumo", 1)[1]
        for rotulo, valor in (("Respostas descartadas pela verificação", "1"), ("Erros de formato do modelo", "1"),
                              ("Falsas recusas", "1 (pergunta com"), ("Falsas respostas", "1 (pergunta sem")):
            self.assertRegex(resumo, rf"{rotulo} \.+ {re.escape(valor)}")
        self.assertRegex(resumo, r"Situação correta \.+ 8 de 12")

    def test_conjunto_de_teste_mostra_so_os_numeros_ate_pedir_as_perguntas(self):
        codigo, saida = self.avaliar(conjunto="teste")
        self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)
        self.assertIn("Conjunto de teste: meça uma vez", saida)
        self.assertIn("12 de 12", saida)
        self.assertNotIn("[ok]", saida)
        for item in self.conjuntos["teste"].values():
            self.assertNotIn(item.pergunta, saida)
        self.assertNotIn("TE-01", saida)
        codigo, saida = self.avaliar("--mostrar-perguntas", "--ids", "TE-03,TE-04", conjunto="teste")
        self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)
        self.assertEqual(saida.count("[ok]"), 2)
        self.assertIn("A renovação do seguro é automática?", saida)

    def test_ids_limitam_a_medicao_e_id_desconhecido_para_antes_de_chamar_o_modelo(self):
        codigo, saida = self.avaliar("--ids", "AJ-01,AJ-05")
        self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)
        self.assertIn("2 pergunta(s)", saida)
        self.assertEqual(len(self.geracao.chamadas), 2)
        self.geracao.chamadas.clear()
        codigo, saida = self.avaliar("--ids", "AJ-99")
        self.assertEqual(codigo, lab_comum.CODIGO_USO)
        self.assertIn("Ids fora do conjunto: AJ-99", saida)
        self.assertEqual(self.geracao.chamadas, [])

    def test_repeticoes_mostram_a_variacao_entre_as_execucoes(self):
        codigo, saida = self.avaliar("--repeticoes", "2", "--ids", "AJ-01,AJ-02")
        self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)
        for esperado in ("Execução 1 de 2", "Execução 2 de 2", "Resumo da execução 2", "Variação entre as 2 execuções"):
            self.assertIn(esperado, saida)
        self.assertEqual(len(self.geracao.chamadas), 4)
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            self.avaliar("--repeticoes", "6")

    def test_respostas_e_recuperacao_exigem_o_conjunto(self):
        for etapa in ("respostas", "recuperacao"):
            with self.subTest(etapa):
                codigo, saida = self.avaliar(etapa=etapa, conjunto=None)
                self.assertEqual(codigo, lab_comum.CODIGO_USO)
                self.assertIn("Informe o conjunto", saida)

    def test_recuperacao_mede_os_tres_modos_e_mostra_posicoes_so_no_ajuste(self):
        codigo, saida = self.avaliar(etapa="recuperacao")
        self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)
        for esperado in ("9 de 12 pergunta(s) têm resposta nos documentos", "medindo o modo vetorial", "medindo o modo texto",
                         "medindo o modo hibrida", "acerto@1", "acerto@10", "MRR", "Posição do primeiro trecho pertinente"):
            self.assertIn(esperado, saida)
        self.assertRegex(saida, r"AJ-06\s+composta")
        self.assertEqual(self.geracao.chamadas, [], "a etapa de recuperação não chama o modelo de geração")
        codigo, saida = self.avaliar(etapa="recuperacao", conjunto="teste")
        self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)
        self.assertIn("Conjunto de teste: meça uma vez", saida)
        self.assertNotIn("Posição do primeiro trecho pertinente", saida)
        self.assertNotIn("TE-01", saida)

    def test_recuperacao_so_com_perguntas_sem_resposta_para(self):
        codigo, saida = self.avaliar("--ids", "AJ-10,AJ-11", etapa="recuperacao")
        self.assertEqual(codigo, lab_comum.CODIGO_USO)
        self.assertIn("Nenhuma das perguntas escolhidas tem resposta", saida)

    def test_agente_com_ferramenta_mede_as_buscas_por_pergunta(self):
        def final(pedido):
            identificador, texto = ServicoRespostasFalso.primeiro_trecho(pedido)
            return {"tipo": lp.DOCUMENTADA, "resposta": "Até 30 dias corridos.",
                    "evidencias": [{"fonte": identificador, "citacao": texto.strip()[-60:]}]}

        self.servico = ServicoRespostasFalso([("buscar", "prazo de análise de sinistro"), final])
        codigo, saida = self.avaliar("--recuperacao", "ferramenta", "--ids", "AJ-01")
        self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)
        self.assertIn("recuperação por ferramenta (até 2 busca(s))", saida)
        self.assertRegex(saida, r"Buscas por pergunta \(média\) \.+ 1,0")
        self.assertIn("[ok]", saida)
        self.assertEqual(len(self.servico.pedidos), 2)
        self.assertEqual(self.geracao.chamadas, [], "o fluxo do agente não usa o cliente de geração direto")

    def test_agente_que_responde_sem_buscar_aparece_como_resposta_descartada(self):
        self.servico = ServicoRespostasFalso([{"tipo": lp.DOCUMENTADA, "resposta": "De cabeça.", "evidencias": []}])
        codigo, saida = self.avaliar("--recuperacao", "ferramenta", "--ids", "AJ-01")
        self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)
        self.assertIn("[falha] AJ-01", saida)
        self.assertIn("resposta descartada: o agente respondeu sem buscar", saida)

    def test_erro_do_servico_de_geracao_interrompe_a_medicao_com_orientacao(self):
        self.geracao.erro = erro_openai("PermissionDeniedError", 403)
        codigo, saida = self.avaliar()
        self.assertEqual(codigo, lab_comum.CODIGO_ACESSO)
        self.assertIn("Cognitive Services OpenAI User", saida)
        self.assertNotIn("Resumo", saida, "não há resumo de uma medição interrompida")


if __name__ == "__main__":
    unittest.main()
