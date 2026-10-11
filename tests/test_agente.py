import asyncio
import contextlib
import io
import json
import logging
import unittest
from unittest import mock

import support  # noqa: F401  (configura o caminho dos scripts)
import agente_maf
import lab_agente as la
import lab_comum
import lab_geracao as lg
import lab_indexacao as li
import lab_politica as lp
from support import ServicoRespostasFalso, copiar_pacote, erro_openai, indexar_pacote, rodar_script

BUSCA, MODELOS = "srch-vlr-exemplo", "ais-vlr-exemplo"
DIMENSOES = 8


def trecho(identificador="A-1", conteudo="Texto do trecho A, com mais de vinte caracteres."):
    return {"id": identificador, "documento_id": "VLAR-CG-1.0", "titulo_documento": "Vareleira Lar — Condições Gerais",
            "secao": "3. Coberturas adicionais", "clausulas": "3.1", "conteudo": conteudo,
            "fonte": "vareleira-lar/condicoes-gerais-v1.0.md", "versao": "1.0", "@search.score": 0.03}


class RecuperadorFalso:
    def __init__(self, resultados=None):
        self.resultados = resultados if resultados is not None else [trecho("A-1"), trecho("B-2", "Texto do trecho B.")]
        self.chamadas: list[tuple[str, str, int]] = []
        self.erro: Exception | None = None

    def recuperar(self, pergunta, modo, k):
        self.chamadas.append((pergunta, modo, k))
        if self.erro:
            raise self.erro
        return lg.Recuperacao([dict(item) for item in self.resultados][:k], 3)


class FerramentaBuscaTests(unittest.TestCase):
    def ferramenta(self, maximo=2, **opcoes):
        self.recuperador = RecuperadorFalso(**opcoes)
        return la.FerramentaBusca(self.recuperador, "hibrida", 5, maximo)

    def test_devolve_os_trechos_em_blocos_e_registra_a_busca(self):
        busca = self.ferramenta()
        devolvido = busca.buscar("  franquia  ")
        self.assertEqual(devolvido, lg.montar_contexto(self.recuperador.resultados))
        self.assertEqual(self.recuperador.chamadas, [("franquia", "hibrida", 5)], "modo e k vêm do programa, não do modelo")
        self.assertEqual(busca.registros, [la.RegistroDeBusca("franquia", la.BUSCA_FEITA, ("A-1", "B-2"))])
        self.assertEqual(list(busca.trechos), ["A-1", "B-2"])
        self.assertEqual(busca.tokens_embeddings, 3)

    def test_trechos_repetidos_ficam_uma_vez_na_ordem_da_primeira_aparicao(self):
        busca = self.ferramenta(resultados=[trecho("B-2"), trecho("A-1")])
        busca.buscar("primeira")
        self.recuperador.resultados = [trecho("C-3"), trecho("A-1")]
        busca.buscar("segunda")
        self.assertEqual(list(busca.trechos), ["B-2", "A-1", "C-3"])
        self.assertEqual(busca.tokens_embeddings, 6)

    def test_consulta_vazia_ou_longa_demais_e_recusada_sem_buscar_e_sem_gastar_o_limite(self):
        busca = self.ferramenta(maximo=1)
        for consulta in ("   ", "x" * (la.LIMITE_DA_CONSULTA + 1), None):
            with self.subTest(consulta=str(consulta)[:5]):
                self.assertIn("Consulta inválida", busca.buscar(consulta))
        self.assertEqual(self.recuperador.chamadas, [])
        self.assertEqual({registro.situacao for registro in busca.registros}, {la.BUSCA_INVALIDA})
        busca.buscar("franquia")
        self.assertEqual(busca.feitas, 1)

    def test_depois_do_limite_a_busca_e_recusada_sem_chamar_o_indice(self):
        busca = self.ferramenta(maximo=1)
        busca.buscar("primeira")
        devolvido = busca.buscar("segunda")
        self.assertIn("Limite de 1 busca(s) atingido", devolvido)
        self.assertNotIn("<trecho", devolvido)
        self.assertEqual(len(self.recuperador.chamadas), 1)
        self.assertEqual([registro.situacao for registro in busca.registros], [la.BUSCA_FEITA, la.BUSCA_RECUSADA])

    def test_falha_da_busca_fica_guardada_e_o_erro_segue_para_o_agente(self):
        busca = self.ferramenta()
        falha = RuntimeError("falha de teste")
        self.recuperador.erro = falha
        with self.assertRaises(RuntimeError):
            busca.buscar("franquia")
        self.assertIs(busca.erro, falha)
        self.assertEqual(busca.registros[-1].situacao, la.BUSCA_COM_ERRO)


class FerramentaNoMafTests(unittest.TestCase):
    def test_o_modelo_recebe_nome_descricao_e_um_parametro_de_texto(self):
        ferramenta = la.criar_ferramenta_maf(la.FerramentaBusca(RecuperadorFalso(), "hibrida", 5))
        esquema = ferramenta.parameters()
        self.assertEqual(ferramenta.name, la.NOME_DA_FERRAMENTA)
        self.assertEqual(ferramenta.approval_mode, "never_require", "a busca só lê")
        self.assertEqual(esquema["required"], ["consulta"])
        self.assertEqual(esquema["properties"]["consulta"]["type"], "string")
        self.assertIn(str(la.LIMITE_DA_CONSULTA), esquema["properties"]["consulta"]["description"])
        self.assertEqual(set(esquema["properties"]), {"consulta"}, "o modelo não escolhe modo nem quantidade de trechos")

    def test_chamar_a_ferramenta_do_maf_aciona_a_busca_do_programa(self):
        busca = la.FerramentaBusca(RecuperadorFalso(), "texto", 2)
        ferramenta = la.criar_ferramenta_maf(busca)
        asyncio.run(ferramenta.invoke(consulta="franquia"))
        self.assertEqual(busca.registros[0].consulta, "franquia")
        self.assertEqual(busca.registros[0].situacao, la.BUSCA_FEITA)


class InstrucoesEDecisaoTests(unittest.TestCase):
    def saida(self, tipo, resposta="Resposta de teste.", evidencias=None):
        if evidencias is None:
            evidencias = [{"fonte": "A-1", "citacao": "Texto do trecho A, com mais de vinte caracteres."}]
        return {"tipo": tipo, "resposta": resposta, "evidencias": evidencias}

    def test_instrucoes_somam_a_busca_as_do_desafio_04(self):
        instrucoes = la.instrucoes_do_agente(3)
        self.assertTrue(instrucoes.startswith(lp.INSTRUCOES_COMPLETAS))
        for esperado in (la.NOME_DA_FERRAMENTA, "no máximo 3 chamada(s)", "sem_evidencia depois de buscar pelo menos uma vez"):
            self.assertIn(esperado, instrucoes)

    def test_tipos_que_dependem_dos_documentos_exigem_uma_busca_do_agente(self):
        for tipo in la.TIPOS_QUE_EXIGEM_BUSCA:
            with self.subTest(tipo=tipo):
                decisao = la.decidir(self.saida(tipo), [trecho()], "Qual é a regra?", buscas_feitas=0, exige_busca=True)
                self.assertEqual(decisao.situacao, lp.DESCARTADA)
                self.assertIn("nenhuma busca foi feita", decisao.problemas[0])

    def test_sem_necessidade_de_busca_o_agente_pode_recusar_ou_pedir_esclarecimento(self):
        casos = {lp.FORA_DE_ESCOPO: lp.RECUSADA, lp.AMBIGUA: lp.ESCLARECIMENTO}
        for tipo, situacao in casos.items():
            with self.subTest(tipo=tipo):
                decisao = la.decidir(self.saida(tipo, "Qual cobertura?", []), [], "Qual é o prazo?", 0, exige_busca=True)
                self.assertEqual(decisao.situacao, situacao)

    def test_com_busca_ou_com_recuperacao_obrigatoria_vale_a_politica_do_desafio_04(self):
        resultados = [trecho()]
        pergunta = "Qual é a regra?"
        com_busca = la.decidir(self.saida(lp.DOCUMENTADA), resultados, pergunta, buscas_feitas=1, exige_busca=True)
        self.assertEqual(com_busca.situacao, lp.RESPONDIDA)
        self.assertEqual(com_busca, lp.aplicar_politica(self.saida(lp.DOCUMENTADA), resultados, pergunta))
        sem_busca_do_agente = la.decidir(self.saida(lp.SEM_EVIDENCIA, "", []), resultados, pergunta, 0, exige_busca=False)
        self.assertEqual(sem_busca_do_agente.situacao, lp.RECUSADA)

    def test_citacao_de_um_trecho_que_o_agente_nunca_recebeu_descarta_a_resposta(self):
        saida = self.saida(lp.DOCUMENTADA, evidencias=[{"fonte": "Z-9", "citacao": "Texto do trecho A, com mais de vinte caracteres."}])
        decisao = la.decidir(saida, [trecho()], "Qual é a regra?", buscas_feitas=1, exige_busca=True)
        self.assertEqual(decisao.situacao, lp.DESCARTADA)
        self.assertIn("Z-9", decisao.problemas[0])


class ErroEmbrulhadoPeloMafTests(unittest.TestCase):
    ARGS = type("Args", (), {"modelos": MODELOS, "deployment_geracao": "geracao", "deployment": "embeddings",
                              "busca": BUSCA, "indice": "indice-x", "conta": "-", "container": "-"})()

    @staticmethod
    def embrulhar(causa):
        try:
            try:
                raise causa
            except Exception as erro:
                raise RuntimeError("service failed to complete the prompt") from erro
        except RuntimeError as embrulho:
            return embrulho

    def test_o_erro_original_da_openai_e_traduzido_pelo_tradutor_da_geracao(self):
        embrulho = self.embrulhar(erro_openai("PermissionDeniedError", 403))
        mensagem, codigo = la.traduzir_erro_do_agente(embrulho, self.ARGS)
        self.assertIn("Cognitive Services OpenAI User", mensagem)
        self.assertEqual(codigo, lab_comum.CODIGO_ACESSO)

    def test_erro_de_credencial_do_azure_vira_orientacao_de_login(self):
        from azure.identity import CredentialUnavailableError

        mensagem, _ = la.traduzir_erro_do_agente(self.embrulhar(CredentialUnavailableError("sem sessão")), self.ARGS)
        self.assertIn("az login", mensagem)

    def test_cadeia_sem_erro_conhecido_nao_e_traduzida(self):
        self.assertIsNone(la.traduzir_erro_do_agente(self.embrulhar(ValueError("defeito")), self.ARGS))


class AgenteMafTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(logging.getLogger("agent_framework").setLevel, logging.NOTSET)
        self.pasta, self.inventario = copiar_pacote()
        self.addCleanup(self.pasta.cleanup)
        self.indice, self.embeddings = indexar_pacote(self.inventario, BUSCA, MODELOS, DIMENSOES)
        self.chamadas_de_embeddings = len(self.embeddings.chamadas)
        documentos = lab_comum.carregar_inventario(self.inventario).documentos
        textos = [t for d in documentos for t in li.dividir_documento(d, lab_comum.ler_conteudo(d).decode("utf-8"))]
        # A consulta é o texto do próprio trecho (o vetor falso é idêntico): ele vem em primeiro lugar.
        self.alvo = min(textos, key=lambda item: len(item.texto_para_embedding))
        self.pergunta = self.alvo.texto_para_embedding
        self.servico: ServicoRespostasFalso | None = None

    def final(self, tipo=lp.DOCUMENTADA, resposta="Resposta de teste.", citacao=None):
        def montar(pedido):
            identificador, texto = ServicoRespostasFalso.primeiro_trecho(pedido)
            return {"tipo": tipo, "resposta": resposta,
                    "evidencias": [{"fonte": identificador, "citacao": citacao or texto.strip()[-60:]}]}
        return montar

    @staticmethod
    def sem_evidencias(tipo, resposta=""):
        return {"tipo": tipo, "resposta": resposta, "evidencias": []}

    def agente(self, roteiro, *opcoes, pergunta=None):
        self.servico = ServicoRespostasFalso(roteiro)
        argumentos = ["--busca", BUSCA, "--modelos", MODELOS, "--dimensoes", str(DIMENSOES), "--modo", "vetorial",
                      "--pergunta", pergunta if pergunta is not None else self.pergunta, *opcoes]
        return rodar_script(agente_maf, argumentos, abrir_indice=lambda *a, **k: self.indice,
                            openai=self.embeddings, agente=self.servico)

    def test_ferramenta_fluxo_completo_mostra_resposta_evidencias_rastro_e_uso(self):
        operacoes = list(self.indice.operacoes)
        codigo, saida = self.agente([("buscar", self.pergunta), self.final()])
        self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)
        for esperado in ("recuperação por ferramenta", "Trechos recuperados (", "Tipo da pergunta: documentada nos trechos",
                         "Resposta de teste.", "Evidências conferidas", "1. O agente recebeu a pergunta e as instruções, sem trechos.",
                         "2. O agente chamou a ferramenta buscar_trechos 1 vez(es):", "busca 1:", self.alvo.id,
                         "3. O programa conferiu o tipo e as evidências (1 citação(ões) literais)", "não confirma as coberturas"):
            self.assertIn(esperado, saida)
        self.assertEqual(self.indice.operacoes, operacoes, "o agente só lê")
        self.assertEqual(len(self.embeddings.chamadas), self.chamadas_de_embeddings + 1, "uma busca, um embedding")
        self.assertEqual(len(self.servico.pedidos), 2, "uma ida para pedir a busca e outra para responder")

    def test_texto_escrito_antes_da_ferramenta_nao_entra_na_resposta_final(self):
        codigo, saida = self.agente([("buscar", self.pergunta, "Vou buscar nos documentos."), self.final()])
        self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)
        self.assertIn("Tipo da pergunta: documentada nos trechos", saida)
        self.assertNotIn("Vou buscar", saida)

    def test_contratacao_individual_mostra_o_texto_do_programa_e_as_citacoes_conferidas(self):
        roteiro = [("buscar", self.pergunta), self.final(lp.CONTRATACAO_INDIVIDUAL, "Em regra, não.")]
        codigo, saida = self.agente(roteiro)
        self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)
        identificador, texto = ServicoRespostasFalso.primeiro_trecho(self.servico.pedidos[1])
        citacao = " ".join(texto.strip()[-60:].split())
        lido = " ".join(saida.split())  # o texto é quebrado em linhas ao imprimir
        for esperado in ("Tipo da pergunta: contratação individual", lp.TEXTO_SEM_VEREDITO, f'[{identificador}] "{citacao}"',
                         "cláusulas 1.3 e 11.1"):
            self.assertIn(esperado, lido)
        self.assertNotIn("Em regra, não.", saida, "o texto livre do modelo não chega à pessoa")

    def test_o_pedido_ao_modelo_leva_as_instrucoes_a_ferramenta_e_as_opcoes_de_privacidade_e_custo(self):
        self.agente([("buscar", self.pergunta), self.final()])
        primeiro, segundo = self.servico.pedidos
        self.assertEqual(primeiro["model"], "geracao")
        self.assertEqual(primeiro["instructions"], la.instrucoes_do_agente(la.BUSCAS_PADRAO))
        self.assertEqual(primeiro["store"], False, "nada fica guardado no serviço")
        self.assertEqual(primeiro["reasoning"], {"effort": "low"})
        self.assertEqual(primeiro["max_output_tokens"], lg.LIMITE_DE_SAIDA_TOKENS)
        self.assertEqual(primeiro["parallel_tool_calls"], False)
        self.assertEqual(primeiro["text"], {"format": lp.CONTRATO_COMPLETO.esquema})
        self.assertEqual([ferramenta["name"] for ferramenta in primeiro["tools"]], [la.NOME_DA_FERRAMENTA])
        self.assertNotIn("<trecho", ServicoRespostasFalso.texto_recebido(primeiro), "o agente começa sem trechos")
        self.assertIn(f'<trecho id="{self.alvo.id}"', ServicoRespostasFalso.texto_recebido(segundo),
                      "o resultado da ferramenta volta ao modelo")
        for pedido in (primeiro, segundo):
            self.assertNotIn(BUSCA, json.dumps(pedido))
            self.assertNotIn(MODELOS, json.dumps(pedido))

    def test_o_uso_somado_conta_todas_as_idas_ao_modelo(self):
        _, saida = self.agente([("buscar", self.pergunta), self.final()])
        entrada = sum(len(json.dumps(pedido["input"], ensure_ascii=False)) // 3 for pedido in self.servico.pedidos)
        self.assertIn(f"{entrada} tokens de entrada e 80 de saída (20 de raciocínio)", saida)

    def test_modo_k_e_esforco_chegam_a_busca_e_ao_modelo(self):
        self.agente([("buscar", self.pergunta), lambda pedido: self.final()(pedido)], "--k", "2", "--esforco", "none")
        self.assertEqual(self.servico.pedidos[0]["reasoning"], {"effort": "none"})
        resultado = next(item["output"] for item in self.servico.pedidos[1]["input"] if item.get("type") == "function_call_output")
        self.assertEqual(resultado.count("<trecho "), 2)

    def test_recuperacao_obrigatoria_entrega_os_trechos_sem_ferramentas(self):
        codigo, saida = self.agente([self.final()], "--recuperacao", "obrigatoria")
        self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)
        self.assertEqual(len(self.servico.pedidos), 1)
        pedido = self.servico.pedidos[0]
        self.assertNotIn("tools", pedido)
        self.assertEqual(pedido["instructions"], lp.INSTRUCOES_COMPLETAS)
        self.assertIn(f'<trecho id="{self.alvo.id}"', ServicoRespostasFalso.texto_recebido(pedido))
        for esperado in ("recuperação obrigatória", "1. O programa buscou antes ('vetorial')",
                         "2. O agente recebeu os trechos e a pergunta, sem ferramentas.", "3. O programa conferiu"):
            self.assertIn(esperado, saida)
        self.assertNotIn("chamou a ferramenta", saida)

    def test_citacao_inventada_descarta_a_resposta_e_mostra_o_rastro(self):
        codigo, saida = self.agente([("buscar", self.pergunta),
                                     self.final(resposta="Resposta inventada.", citacao="Esta frase não existe em nenhum trecho.")])
        self.assertEqual(codigo, lab_comum.CODIGO_DIVERGENCIA)
        for esperado in ("[FALHA] A resposta do agente foi descartada", "não aparece literalmente no trecho", "busca 1:"):
            self.assertIn(esperado, saida)
        self.assertNotIn("Resposta inventada.", saida)
        self.assertNotIn("3. O programa conferiu", saida)

    def test_agente_que_responde_sem_buscar_sobre_o_produto_e_descartado(self):
        for tipo in (lp.SEM_EVIDENCIA, lp.DOCUMENTADA):
            with self.subTest(tipo=tipo):
                codigo, saida = self.agente([self.sem_evidencias(tipo, "Resposta de cabeça.")])
                self.assertEqual(codigo, lab_comum.CODIGO_DIVERGENCIA)
                self.assertIn("nenhuma busca foi feita", saida)
                self.assertIn("2. O agente não chamou a ferramenta: respondeu sem buscar.", saida)
                self.assertNotIn("Resposta de cabeça.", saida)
                self.assertEqual(len(self.embeddings.chamadas), self.chamadas_de_embeddings)

    def test_pergunta_fora_de_escopo_pode_dispensar_a_busca(self):
        codigo, saida = self.agente([self.sem_evidencias(lp.FORA_DE_ESCOPO)], pergunta="Qual é a capital da França?")
        self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)
        self.assertIn("Tipo da pergunta: fora de escopo", saida)
        self.assertIn(lp.MENSAGEM_FORA_DE_ESCOPO, " ".join(saida.split()), "o texto é quebrado em linhas ao imprimir")
        self.assertEqual(len(self.servico.pedidos), 1)

    def test_depois_do_limite_o_maf_pede_a_resposta_final_sem_ferramentas(self):
        roteiro = [("buscar", self.pergunta), ("buscar", self.pergunta), self.final()]
        codigo, saida = self.agente(roteiro, "--maximo-de-buscas", "2")
        self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)
        self.assertEqual(len(self.servico.pedidos), 3)
        self.assertNotEqual(self.servico.pedidos[1].get("tool_choice"), "none")
        self.assertEqual(self.servico.pedidos[2].get("tool_choice"), "none", "no limite, o MAF desliga a ferramenta")
        self.assertIn("2. O agente chamou a ferramenta buscar_trechos 2 vez(es):", saida)

    def test_maximo_de_buscas_menor_para_antes(self):
        self.agente([("buscar", self.pergunta), self.final()], "--maximo-de-buscas", "1")
        self.assertEqual(self.servico.pedidos[1].get("tool_choice"), "none")

    def test_falha_da_busca_vira_orientacao_mesmo_que_o_agente_responda_depois(self):
        self.embeddings.erro = erro_openai("NotFoundError", 404)
        codigo, saida = self.agente([("buscar", self.pergunta), self.sem_evidencias(lp.SEM_EVIDENCIA)])
        self.assertEqual(codigo, lab_comum.CODIGO_ACESSO)
        self.assertIn("[ERRO]", saida)
        self.assertIn("nomeDeploymentEmbeddings", saida, "o erro da busca usa o tradutor dos embeddings")
        self.assertNotIn("Recusa", saida, "a recusa do agente não esconde a falha da busca")
        self.assertNotIn("Traceback", saida)
        self.assertNotIn("Function failed", saida, "o log bruto do MAF fica de fora sem --detalhes")

    def test_erro_do_laboratorio_levantado_pela_busca_chega_com_a_mensagem_e_o_codigo_originais(self):
        menor = DIMENSOES // 2
        self.embeddings.dimensoes = menor  # o deployment passa a devolver vetores incompatíveis com o índice
        codigo, saida = self.agente([("buscar", self.pergunta), self.sem_evidencias(lp.SEM_EVIDENCIA)])
        self.assertEqual(codigo, lab_comum.CODIGO_USO, "o código 1 do erro original não vira o 4 de defeito do script")
        lido = " ".join(saida.split())
        self.assertIn(f"devolveu vetores de {menor} dimensões, mas o índice espera {DIMENSOES}", lido)
        self.assertIn(f"Use --dimensoes {menor} com um índice novo", lido)
        self.assertNotIn("Erro inesperado do script", saida)
        self.assertNotIn("Recusa", saida, "a recusa do agente não esconde a falha da busca")
        self.assertNotIn("Traceback", saida)

    def test_detalhes_mostra_o_erro_bruto_da_ferramenta(self):
        self.embeddings.erro = erro_openai("NotFoundError", 404)
        logging.getLogger("agent_framework").setLevel(logging.NOTSET)
        codigo, saida = self.agente([("buscar", self.pergunta), self.sem_evidencias(lp.SEM_EVIDENCIA)], "--detalhes")
        self.assertEqual(codigo, lab_comum.CODIGO_ACESSO)
        self.assertIn("Function failed", saida)
        self.assertIn("Traceback", saida)

    def test_erros_do_servico_de_geracao_viram_orientacao_e_nao_expoem_o_erro_bruto(self):
        casos = {403: "Cognitive Services OpenAI User", 404: "nomeDeploymentGeracao", 429: "capacidadeGeracao"}
        for status, esperado in casos.items():
            with self.subTest(status=status):
                servico = ServicoRespostasFalso([])
                servico.erro_http = (status, {"error": {"code": "MENSAGEM-SENSIVEL", "message": "MENSAGEM-SENSIVEL"}})
                argumentos = ["--busca", BUSCA, "--modelos", MODELOS, "--dimensoes", str(DIMENSOES), "--pergunta", self.pergunta,
                              "--recuperacao", "obrigatoria", "--modo", "vetorial"]
                codigo, saida = rodar_script(agente_maf, argumentos, abrir_indice=lambda *a, **k: self.indice,
                                             openai=self.embeddings, agente=servico)
                self.assertEqual(codigo, lab_comum.CODIGO_ACESSO)
                self.assertIn(esperado, saida)
                self.assertNotIn("MENSAGEM-SENSIVEL", saida)
                self.assertNotIn("Traceback", saida)

    def test_resposta_truncada_pede_menos_raciocinio(self):
        codigo, saida = self.agente([("incompleto",)], "--recuperacao", "obrigatoria")
        self.assertEqual(codigo, lab_comum.CODIGO_ACESSO)
        self.assertIn("não terminou a resposta", saida)
        self.assertIn("--esforco", saida)

    def test_agente_que_passa_do_tempo_maximo_e_interrompido(self):
        self.servico = ServicoRespostasFalso([self.final()])
        self.servico.atraso = 5
        argumentos = ["--busca", BUSCA, "--modelos", MODELOS, "--dimensoes", str(DIMENSOES), "--pergunta", self.pergunta,
                      "--recuperacao", "obrigatoria", "--modo", "vetorial"]
        with mock.patch.object(la, "TEMPO_MAXIMO", 0.2):
            codigo, saida = rodar_script(agente_maf, argumentos, abrir_indice=lambda *a, **k: self.indice,
                                         openai=self.embeddings, agente=self.servico)
        self.assertEqual(codigo, lab_comum.CODIGO_ACESSO)
        self.assertIn("O agente não terminou em", saida)

    def test_mostrar_agente_exibe_instrucoes_ferramenta_e_limites_sem_acessar_o_azure(self):
        codigo, saida = self.agente([], "--mostrar-agente", "--maximo-de-buscas", "3")
        self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)
        for esperado in ("--- Instruções do agente ---", "no máximo 3 chamada(s)", "Nome: buscar_trechos", '"required": [',
                         "Chamadas da ferramenta: até 3 · idas ao modelo: até 5", "o modelo escolhe só o texto da consulta"):
            self.assertIn(esperado, saida)
        self.assertEqual(self.servico.pedidos, [])
        self.assertEqual(len(self.embeddings.chamadas), self.chamadas_de_embeddings)

    def test_mostrar_agente_com_recuperacao_obrigatoria_nao_tem_ferramenta(self):
        codigo, saida = self.agente([], "--mostrar-agente", "--recuperacao", "obrigatoria")
        self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)
        self.assertIn("Sem ferramentas", saida)
        self.assertNotIn("Nome: buscar_trechos", saida)

    def test_indice_vazio_com_recuperacao_obrigatoria_nao_chama_o_agente(self):
        self.indice.documentos.clear()
        codigo, saida = self.agente([], "--recuperacao", "obrigatoria")
        self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)
        self.assertIn("o agente não foi chamado", saida)
        self.assertEqual(self.servico.pedidos, [])

    def test_pergunta_vazia_ou_longa_demais_para_antes_de_acessar_o_azure(self):
        for pergunta, esperado in (("   ", "pergunta não vazia"), ("x" * (lg.LIMITE_DA_PERGUNTA + 1), "mais de")):
            with self.subTest(pergunta=pergunta[:5]):
                codigo, saida = self.agente([], pergunta=pergunta)
                self.assertEqual(codigo, lab_comum.CODIGO_USO)
                self.assertIn(esperado, saida)
        self.assertEqual(len(self.embeddings.chamadas), self.chamadas_de_embeddings)

    def test_argumentos_invalidos_sao_recusados_antes_de_chamar_o_azure(self):
        for opcoes in (["--maximo-de-buscas", "0"], ["--maximo-de-buscas", str(la.BUSCAS_MAXIMAS + 1)],
                       ["--maximo-de-buscas", "muitas"], ["--recuperacao", "outra"]):
            with self.subTest(opcoes=opcoes), self.assertRaises(SystemExit) as saida:
                with contextlib.redirect_stderr(io.StringIO()):
                    self.agente([], *opcoes)
            self.assertEqual(saida.exception.code, lab_comum.CODIGO_USO)
        self.assertEqual(self.servico.pedidos, [])


if __name__ == "__main__":
    unittest.main()
