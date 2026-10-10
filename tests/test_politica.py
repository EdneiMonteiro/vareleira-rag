import contextlib
import io
import json
import re
import unittest

import support  # noqa: F401  (configura o caminho dos scripts)
import lab_comum
import lab_geracao as lg
import lab_indexacao as li
import lab_politica as lp
import perguntar
from support import OpenAIGeracaoFalso, copiar_pacote, indexar_pacote, rodar_script

BUSCA, MODELOS = "srch-vlr-exemplo", "ais-vlr-exemplo"
DIMENSOES = 8
CONTEUDO = ("## 3. Coberturas adicionais\n\n3.1. As coberturas adicionais são contratadas à parte e "
            "**só valem se constarem como contratadas na apólice individual**.\n\n| Cobertura | Franquia |\n"
            "| --- | --- |\n| Danos elétricos | 10% do prejuízo, com mínimo de R$ 300,00 |")


def trecho(identificador="VLAR-CG-1_0-004", conteudo=CONTEUDO):
    return {"id": identificador, "documento_id": "VLAR-CG-1.0", "titulo_documento": "Vareleira Lar — Condições Gerais",
            "secao": "3. Coberturas adicionais", "clausulas": "3.1", "conteudo": conteudo,
            "fonte": "vareleira-lar/condicoes-gerais-v1.0.md", "versao": "1.0"}


def saida(tipo=lp.DOCUMENTADA, resposta="Resposta.", evidencias=None):
    if evidencias is None:
        evidencias = [{"fonte": "VLAR-CG-1_0-004", "citacao": "as coberturas adicionais são contratadas à parte"}]
    return {"tipo": tipo, "resposta": resposta, "evidencias": evidencias}


class NormalizacaoEDeteccaoTests(unittest.TestCase):
    def test_normalizar_ignora_marcas_de_markdown_caixa_e_espacos(self):
        self.assertEqual(lp.normalizar("**Danos  elétricos.**\n| a | b |"), "danos elétricos. a b")
        self.assertEqual(lp.normalizar("  Texto `com` _marcas_  "), "texto com marcas")

    def test_normalizar_nao_deixa_espaco_entre_a_marca_de_enfase_e_a_pontuacao(self):
        self.assertEqual(lp.normalizar("na **apólice individual**, no **prazo**: 7 dias (**30** no total)."),
                         lp.normalizar("na apólice individual, no prazo: 7 dias (30 no total)."))

    def test_regra_do_programa_reconhece_pergunta_sobre_o_caso_da_pessoa(self):
        sim = ["O meu seguro cobre danos elétricos?", "Roubaram meu notebook na rua. O seguro paga?",
               "Minha apólice cobre alagamento?", "A casa é nossa: o contrato vale para reforma?"]
        nao = ["O Vareleira Lar cobre alagamento ou enchente?", "Em quantos dias preciso avisar que houve um sinistro?",
               "Qual é a franquia da cobertura de danos elétricos?", "Meu cachorro come ração.", "O seguro cobre?"]
        for pergunta in sim:
            with self.subTest(pergunta=pergunta):
                self.assertTrue(lp.parece_contratacao_individual(pergunta))
        for pergunta in nao:
            with self.subTest(pergunta=pergunta):
                self.assertFalse(lp.parece_contratacao_individual(pergunta))

    def test_veredito_detecta_afirmar_ou_negar_a_cobertura_de_um_caso(self):
        sim = ["Sim, está coberto.", "Não. O seguro não indeniza bens portáteis.", "  \"Sim!\" Seu caso tem cobertura.",
               "Seu seguro cobre esse caso.", "Seu seguro não paga isso.", "O sinistro será indenizado.",
               "O imóvel não está coberto.", "Você tem direito à indenização."]
        nao = ["Não há carência nas coberturas do produto.", "A regra geral exclui bens portáteis levados para fora.",
               "Danos elétricos é uma cobertura adicional e só vale se estiver contratada.",
               "Existe uma cobertura adicional para danos elétricos."]
        for texto in sim:
            with self.subTest(texto=texto):
                self.assertTrue(lp.afirma_veredito(texto))
        for texto in nao:
            with self.subTest(texto=texto):
                self.assertFalse(lp.afirma_veredito(texto))


class EvidenciasTests(unittest.TestCase):
    def verificar(self, *evidencias, resultados=None):
        return lp.verificar_evidencias(list(evidencias), resultados or [trecho()])

    def test_citacao_literal_vale_mesmo_com_markdown_caixa_e_quebras_de_linha(self):
        validas, problemas, curtas = self.verificar(
            {"fonte": "VLAR-CG-1_0-004", "citacao": "só valem se constarem como contratadas na apólice individual"},
            {"fonte": "VLAR-CG-1_0-004", "citacao": "AS COBERTURAS ADICIONAIS são contratadas\n à parte"},
            {"fonte": "VLAR-CG-1_0-004", "citacao": "| Danos elétricos | 10% do prejuízo, com mínimo de R$ 300,00 |"})
        self.assertEqual((len(validas), problemas, curtas), (3, [], 0))

    def test_citacao_sem_as_marcas_vale_quando_a_pontuacao_vem_colada_na_marca_do_trecho(self):
        validas, problemas, _ = self.verificar(
            {"fonte": "VLAR-CG-1_0-004",
             "citacao": "As coberturas adicionais são contratadas à parte e só valem se constarem como contratadas na apólice individual."})
        self.assertEqual((len(validas), problemas), (1, []))

    def test_fonte_desconhecida_citacao_alterada_e_evidencia_malformada_sao_problemas(self):
        validas, problemas, curtas = self.verificar(
            {"fonte": "VLAR-XX-9_9-999", "citacao": "as coberturas adicionais são contratadas à parte"},
            {"fonte": "VLAR-CG-1_0-004", "citacao": "as coberturas adicionais são sempre incluídas na apólice"},
            {"fonte": "VLAR-CG-1_0-004"}, {"fonte": 3, "citacao": 4})
        self.assertEqual(validas, [])
        self.assertEqual(len(problemas), 4)
        self.assertIn("VLAR-XX-9_9-999 não está entre os trechos recuperados", problemas[0])
        self.assertIn("não aparece literalmente", problemas[1])
        self.assertIn("sem fonte ou sem citação", problemas[2])

    def test_citacao_curta_demais_e_ignorada_sem_virar_problema(self):
        validas, problemas, curtas = self.verificar(
            {"fonte": "VLAR-CG-1_0-004", "citacao": "Danos elétricos"},
            {"fonte": "VLAR-CG-1_0-004", "citacao": "contratadas à parte"},
            {"fonte": "VLAR-CG-1_0-004", "citacao": "as coberturas adicionais são contratadas à parte"})
        self.assertEqual(len(validas), 1)
        self.assertEqual((problemas, curtas), ([], 2))

    def test_citacao_so_vale_para_o_trecho_indicado(self):
        outro = trecho("VLAR-FAQ-1_0-002", "Texto totalmente diferente, sem a frase procurada em nenhum ponto.")
        _, problemas, _ = self.verificar(
            {"fonte": "VLAR-FAQ-1_0-002", "citacao": "as coberturas adicionais são contratadas à parte"},
            resultados=[trecho(), outro])
        self.assertIn("VLAR-FAQ-1_0-002 não aparece literalmente", problemas[0])


class PoliticaTests(unittest.TestCase):
    def aplicar(self, dados, pergunta="Qual é a franquia de danos elétricos?", resultados=None):
        return lp.aplicar_politica(dados, resultados or [trecho()], pergunta)

    def test_pergunta_documentada_com_evidencia_conferida_e_respondida(self):
        decisao = self.aplicar(saida(resposta="A cobertura é adicional."))
        self.assertEqual((decisao.situacao, decisao.tipo, decisao.texto, decisao.aviso),
                         (lp.RESPONDIDA, lp.DOCUMENTADA, "A cobertura é adicional.", ""))
        self.assertEqual(len(decisao.evidencias), 1)

    def test_pergunta_sobre_o_caso_da_pessoa_ganha_o_aviso_mesmo_se_o_modelo_disse_documentada(self):
        decisao = self.aplicar(saida(), pergunta="O meu seguro cobre danos elétricos?")
        self.assertEqual((decisao.tipo, decisao.tipo_do_modelo), (lp.CONTRATACAO_INDIVIDUAL, lp.DOCUMENTADA))
        self.assertEqual(decisao.aviso, lp.AVISO_CONTRATACAO_INDIVIDUAL)
        self.assertEqual(decisao.situacao, lp.RESPONDIDA)

    def test_veredito_do_modelo_sobre_o_caso_e_trocado_pelo_texto_padrao_mantendo_as_evidencias(self):
        decisao = self.aplicar(saida(lp.CONTRATACAO_INDIVIDUAL, "Sim, seu seguro cobre isso."))
        self.assertEqual(decisao.texto, lp.TEXTO_SEM_VEREDITO)
        self.assertEqual(len(decisao.evidencias), 1)
        self.assertEqual(decisao.aviso, lp.AVISO_CONTRATACAO_INDIVIDUAL)

    def test_contratacao_individual_sem_veredito_mantem_o_texto_do_modelo(self):
        decisao = self.aplicar(saida(lp.CONTRATACAO_INDIVIDUAL, "A regra geral é a cláusula 3.1."))
        self.assertEqual(decisao.texto, "A regra geral é a cláusula 3.1.")

    def test_sem_evidencia_e_fora_de_escopo_usam_o_texto_do_programa_e_ignoram_o_do_modelo(self):
        for tipo, esperado in ((lp.SEM_EVIDENCIA, lp.MENSAGEM_SEM_EVIDENCIA), (lp.FORA_DE_ESCOPO, lp.MENSAGEM_FORA_DE_ESCOPO)):
            with self.subTest(tipo=tipo):
                decisao = self.aplicar(saida(tipo, "Sim, cobre tudo!"))
                self.assertEqual((decisao.situacao, decisao.texto, decisao.evidencias), (lp.RECUSADA, esperado, ()))

    def test_pergunta_ambigua_mostra_o_esclarecimento_do_modelo_ou_o_padrao(self):
        decisao = self.aplicar(saida(lp.AMBIGUA, "Prazo de quê?", []))
        self.assertEqual((decisao.situacao, decisao.texto), (lp.ESCLARECIMENTO, "Prazo de quê?"))
        self.assertEqual(self.aplicar(saida(lp.AMBIGUA, " ", [])).texto, lp.MENSAGEM_ESCLARECIMENTO)

    def test_resposta_sem_prova_e_descartada_e_nao_aparece(self):
        casos = {
            "sem evidências": saida(evidencias=[]),
            "só citações curtas": saida(evidencias=[{"fonte": "VLAR-CG-1_0-004", "citacao": "curta"}]),
            "fonte desconhecida": saida(evidencias=[{"fonte": "X-1", "citacao": "as coberturas adicionais são contratadas à parte"}]),
            "citação inventada": saida(evidencias=[{"fonte": "VLAR-CG-1_0-004", "citacao": "Todas as coberturas estão incluídas sempre."}]),
            "resposta vazia": saida(resposta="  "),
            "tipo inexistente": saida(tipo="outro"),
        }
        for rotulo, dados in casos.items():
            with self.subTest(rotulo=rotulo):
                decisao = self.aplicar(dados)
                self.assertEqual(decisao.situacao, lp.DESCARTADA)
                self.assertEqual((decisao.texto, decisao.evidencias), ("", ()))
                self.assertTrue(decisao.problemas)

    def test_uma_citacao_inventada_descarta_a_resposta_mesmo_com_outras_validas(self):
        decisao = self.aplicar(saida(evidencias=[
            {"fonte": "VLAR-CG-1_0-004", "citacao": "as coberturas adicionais são contratadas à parte"},
            {"fonte": "VLAR-CG-1_0-004", "citacao": "Todas as coberturas estão incluídas sempre."}]))
        self.assertEqual(decisao.situacao, lp.DESCARTADA)

    def test_citacoes_curtas_ignoradas_sao_contadas_quando_ha_evidencia_valida(self):
        decisao = self.aplicar(saida(evidencias=[
            {"fonte": "VLAR-CG-1_0-004", "citacao": "curta"},
            {"fonte": "VLAR-CG-1_0-004", "citacao": "as coberturas adicionais são contratadas à parte"}]))
        self.assertEqual((decisao.situacao, decisao.citacoes_curtas_ignoradas, len(decisao.evidencias)), (lp.RESPONDIDA, 1, 1))


class ContratoETextosTests(unittest.TestCase):
    def test_esquema_aceita_exatamente_os_tipos_do_programa(self):
        esquema = lp.CONTRATO_COMPLETO.esquema
        propriedades = esquema["schema"]["properties"]
        self.assertTrue(esquema["strict"])
        self.assertEqual(propriedades["tipo"]["enum"], list(lp.TIPOS))
        self.assertEqual(sorted(esquema["schema"]["required"]), sorted(propriedades))
        item = propriedades["evidencias"]["items"]
        self.assertFalse(item["additionalProperties"])
        self.assertEqual(sorted(item["required"]), ["citacao", "fonte"])

    def test_instrucoes_descrevem_cada_tipo_e_exigem_citacao_literal(self):
        for tipo in lp.TIPOS:
            self.assertIn(tipo, lp.INSTRUCOES_COMPLETAS)
        for exigido in ("exatamente como está", f"{lp.MINIMO_DA_CITACAO} caracteres", "<trecho>", "conhecimento próprio",
                        "sem afirmar nem negar"):
            self.assertIn(exigido, lp.INSTRUCOES_COMPLETAS)

    def test_aviso_cita_clausulas_que_existem_nas_condicoes_gerais(self):
        documento = (support.RAIZ / "dados" / "l100" / "documentos" / "vareleira-lar-condicoes-gerais-v1.0.md").read_text(encoding="utf-8")
        for clausula in ("1.3.", "11.1."):
            self.assertIn(f"\n{clausula} ", documento)
        self.assertIn("cláusulas 1.3 e 11.1", lp.AVISO_CONTRATACAO_INDIVIDUAL)

    def test_leitor_aceita_a_saida_completa_e_recusa_evidencia_que_nao_e_objeto(self):
        bruto = json.dumps(saida())
        self.assertEqual(lg.ler_saida(bruto, lp.CONTRATO_COMPLETO)["tipo"], lp.DOCUMENTADA)
        with self.assertRaises(lab_comum.ErroLab):
            lg.ler_saida(json.dumps({**saida(), "evidencias": ["texto solto"]}), lp.CONTRATO_COMPLETO)


class PerguntarComPoliticaTests(unittest.TestCase):
    def setUp(self):
        self.pasta, self.inventario = copiar_pacote()
        self.addCleanup(self.pasta.cleanup)
        self.indice, self.embeddings = indexar_pacote(self.inventario, BUSCA, MODELOS, DIMENSOES)
        self.geracao = OpenAIGeracaoFalso()
        documentos = lab_comum.carregar_inventario(self.inventario).documentos
        textos = [t for d in documentos for t in li.dividir_documento(d, lab_comum.ler_conteudo(d).decode("utf-8"))]
        self.alvo = min(textos, key=lambda item: len(item.texto_para_embedding))
        self.pergunta_padrao = self.alvo.texto_para_embedding
        self.geracao.responder = self.responder(lp.DOCUMENTADA)

    @staticmethod
    def primeiro_trecho(entrada):
        """Id e texto do primeiro bloco <trecho> do pedido: o que a busca colocou em primeiro lugar."""
        achado = re.search(r'<trecho id="([^"]+)"[^>]*>\n(.*?)\n</trecho>', entrada, re.DOTALL)
        return achado.group(1), achado.group(2)

    def responder(self, tipo, resposta="Resposta de teste.", evidencias=True, citacao=None):
        def montar(argumentos):
            lista = []
            if evidencias:
                identificador, texto = self.primeiro_trecho(argumentos["input"])
                lista = [{"fonte": identificador, "citacao": citacao or texto.strip()[-60:]}]
            return {"tipo": tipo, "resposta": resposta, "evidencias": lista}
        return montar

    def perguntar(self, *opcoes, pergunta=None):
        argumentos = ["--busca", BUSCA, "--modelos", MODELOS, "--dimensoes", str(DIMENSOES), "--modo", "vetorial",
                      "--politica", "completa", "--pergunta", pergunta or self.pergunta_padrao, *opcoes]
        return rodar_script(perguntar, argumentos, abrir_indice=lambda *a, **k: self.indice,
                            openai=self.embeddings, geracao=self.geracao)

    def test_resposta_documentada_mostra_tipo_resposta_evidencias_e_percurso(self):
        operacoes = list(self.indice.operacoes)
        codigo, texto = self.perguntar()
        self.assertEqual(codigo, lab_comum.CODIGO_OK, texto)
        for esperado in ("política completa", "Tipo da pergunta: documentada nos trechos", "Resposta:", "Resposta de teste.",
                         "Evidências conferidas (cada citação aparece literalmente no trecho):",
                         "O deployment 'geracao' classificou a pergunta e propôs a resposta.",
                         "1 citação(ões) literais", "Uso na geração:"):
            self.assertIn(esperado, texto)
        self.assertNotIn("Aviso:", texto)
        self.assertEqual(self.indice.operacoes, operacoes, "perguntar só lê")

    def test_o_pedido_usa_as_instrucoes_e_o_esquema_da_politica_completa(self):
        self.perguntar()
        chamada = self.geracao.chamadas[0]
        self.assertEqual(chamada["instructions"], lp.INSTRUCOES_COMPLETAS)
        self.assertEqual(chamada["text"], {"format": lp.CONTRATO_COMPLETO.esquema})

    def test_politica_basica_continua_sendo_o_padrao(self):
        argumentos = ["--busca", BUSCA, "--modelos", MODELOS, "--dimensoes", str(DIMENSOES), "--pergunta", self.pergunta_padrao]
        padrao = OpenAIGeracaoFalso()
        rodar_script(perguntar, argumentos, abrir_indice=lambda *a, **k: self.indice, openai=self.embeddings, geracao=padrao)
        self.assertEqual(padrao.chamadas[0]["instructions"], lg.INSTRUCOES)
        self.assertEqual(padrao.chamadas[0]["text"], {"format": lg.CONTRATO_BASICO.esquema})

    def test_pergunta_sobre_o_caso_da_pessoa_mostra_o_aviso_e_a_mudanca_de_tipo(self):
        codigo, texto = self.perguntar(pergunta="O meu seguro cobre " + self.pergunta_padrao)
        self.assertEqual(codigo, lab_comum.CODIGO_OK, texto)
        self.assertIn("Tipo da pergunta: contratação individual (o modelo classificou como documentada nos trechos; "
                      "uma regra do programa mudou o tipo)", texto)
        self.assertIn("Aviso:", texto)
        self.assertIn("cláusulas 1.3 e 11.1", texto)

    def test_sem_evidencia_e_fora_de_escopo_viram_recusas_com_o_texto_do_programa(self):
        for tipo, mensagem in ((lp.SEM_EVIDENCIA, lp.MENSAGEM_SEM_EVIDENCIA), (lp.FORA_DE_ESCOPO, lp.MENSAGEM_FORA_DE_ESCOPO)):
            with self.subTest(tipo=tipo):
                self.geracao.responder = self.responder(tipo, resposta="Sim, cobre tudo!", evidencias=False)
                codigo, texto = self.perguntar()
                self.assertEqual(codigo, lab_comum.CODIGO_OK, texto)
                self.assertIn("Recusa:", texto)
                self.assertIn(mensagem[:40], texto)
                self.assertNotIn("Sim, cobre tudo!", texto)
                self.assertNotIn("Evidências conferidas", texto)

    def test_pergunta_ambigua_mostra_a_pergunta_de_esclarecimento(self):
        self.geracao.responder = self.responder(lp.AMBIGUA, resposta="Prazo de quê?", evidencias=False)
        codigo, texto = self.perguntar()
        self.assertEqual(codigo, lab_comum.CODIGO_OK, texto)
        self.assertIn("Pergunta de esclarecimento:", texto)
        self.assertIn("Prazo de quê?", texto)

    def test_resposta_com_citacao_inventada_e_descartada_com_codigo_3(self):
        self.geracao.responder = self.responder(lp.DOCUMENTADA, resposta="Resposta inventada.",
                                                citacao="Esta frase não existe em nenhum trecho recuperado.")
        codigo, texto = self.perguntar()
        self.assertEqual(codigo, lab_comum.CODIGO_DIVERGENCIA)
        self.assertIn("[FALHA] A resposta do modelo foi descartada", texto)
        self.assertIn("não aparece literalmente no trecho", texto)
        self.assertNotIn("Resposta inventada.", texto)
        self.assertNotIn("Resposta:", texto)

    def test_citacoes_curtas_ignoradas_sao_informadas(self):
        base = self.responder(lp.DOCUMENTADA)

        def com_curta(argumentos):
            dados = base(argumentos)
            dados["evidencias"].append({"fonte": dados["evidencias"][0]["fonte"], "citacao": "curta"})
            return dados

        self.geracao.responder = com_curta
        codigo, texto = self.perguntar()
        self.assertEqual(codigo, lab_comum.CODIGO_OK, texto)
        self.assertIn("1 citação(ões) curtas demais foram ignoradas.", texto)

    def test_sem_geracao_mostra_as_instrucoes_da_politica_completa_sem_chamar_o_modelo(self):
        codigo, texto = self.perguntar("--sem-geracao")
        self.assertEqual(codigo, lab_comum.CODIGO_OK, texto)
        self.assertIn("Primeiro, classifique a pergunta", texto)
        self.assertEqual(self.geracao.chamadas, [])

    def test_politica_desconhecida_e_recusada_antes_de_acessar_o_azure(self):
        with self.assertRaises(SystemExit) as saida_do_programa, contextlib.redirect_stderr(io.StringIO()):
            self.perguntar("--politica", "livre")
        self.assertEqual(saida_do_programa.exception.code, lab_comum.CODIGO_USO)
        self.assertEqual(self.geracao.chamadas, [])


if __name__ == "__main__":
    unittest.main()
