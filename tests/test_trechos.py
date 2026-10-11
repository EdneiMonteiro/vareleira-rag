import contextlib
import io
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import support  # noqa: F401  (configura o caminho dos scripts)
import lab_comum
import lab_indexacao as li
from lab_comum import ErroLab
from support import OpenAIFalso, erro_openai

ESPECIFICACAO = li.EspecificacaoEmbedding("embeddings", 8)


def documento_de_teste(**campos):
    padrao = dict(
        id="TESTE-1.0", titulo="Documento de teste", tipo="faq", produto="produto-teste", versao="1.0",
        arquivo=Path("teste.md"), blob="pasta/teste.md", tipo_conteudo="text/markdown; charset=utf-8",
        tamanho_bytes=1, sha256="0" * 64, revisao_status="pendente", vigencia_inicio="2025-01-01", vigencia_fim=None,
    )
    padrao.update(campos)
    return lab_comum.Documento(**padrao)


def dividir(texto, tamanho=1200, **campos):
    return li.dividir_documento(documento_de_teste(**campos), texto, tamanho)


def documentos_reais():
    inventario = lab_comum.carregar_e_validar()
    return [(documento, lab_comum.ler_conteudo(documento).decode("utf-8")) for documento in inventario.documentos]


class DivisaoEmTrechosTests(unittest.TestCase):
    def test_cada_titulo_abre_um_trecho_novo_com_a_linha_do_titulo(self):
        trechos = dividir("# Título\n\nIntrodução.\n\n## Seção A\n\nTexto A.\n\n## Seção B\n\nTexto B.")
        self.assertEqual([t.secao for t in trechos], [li.SECAO_APRESENTACAO, "Seção A", "Seção B"])
        self.assertEqual([t.ordem for t in trechos], [1, 2, 3])
        self.assertTrue(trechos[0].conteudo.startswith("# Título"))
        self.assertTrue(trechos[1].conteudo.startswith("## Seção A\n\nTexto A."))

    def test_subtitulos_formam_o_caminho_da_secao(self):
        trechos = dividir("## Pai\n\nTexto.\n\n### Filho\n\nOutro texto.\n\n## Irmão\n\nMais texto.")
        self.assertEqual([t.secao for t in trechos], ["Pai", "Pai > Filho", "Irmão"])

    def test_lista_e_tabela_ficam_com_o_paragrafo_que_as_introduz(self):
        texto = ("## S\n\n1.1. Regra:\n\n- a) um\n- b) dois\n\n1.2. Valores:\n\n| A | B |\n| --- | --- |\n| 1 | 2 |\n\n"
                 "1.3. Fim.")
        trechos = dividir(texto, tamanho=80)
        com_lista = next(t for t in trechos if "1.1. Regra:" in t.conteudo)
        com_tabela = next(t for t in trechos if "1.2. Valores:" in t.conteudo)
        self.assertIn("- b) dois", com_lista.conteudo)
        self.assertIn("| 1 | 2 |", com_tabela.conteudo)

    def test_unidades_pequenas_sao_agrupadas_ate_o_limite_sem_cruzar_secoes(self):
        texto = "## A\n\nUm.\n\nDois.\n\nTrês.\n\n## B\n\nQuatro.\n\nCinco."
        trechos = dividir(texto, tamanho=1000)
        self.assertEqual([t.secao for t in trechos], ["A", "B"])
        self.assertIn("Três.", trechos[0].conteudo)
        self.assertNotIn("Quatro.", trechos[0].conteudo)
        mais_finos = dividir(texto, tamanho=20)
        self.assertGreater(len(mais_finos), len(trechos))

    def test_paragrafo_maior_que_o_limite_e_dividido_em_frases_sem_cortar_nenhuma(self):
        frases = [f"Frase número {numero} termina aqui." for numero in range(1, 21)]
        trechos = dividir("## S\n\n" + " ".join(frases), tamanho=200)
        self.assertGreater(len(trechos), 3)
        for trecho in trechos:
            self.assertLessEqual(len(trecho.conteudo), 200)
        todo = "\n".join(t.conteudo for t in trechos)
        for frase in frases:
            self.assertIn(frase, todo)

    def test_palavra_gigante_e_quebrada_para_respeitar_o_limite(self):
        trechos = dividir("## S\n\n" + "x" * 500, tamanho=100)
        self.assertTrue(all(len(t.conteudo) <= 100 for t in trechos))
        self.assertEqual(sum(t.conteudo.count("x") for t in trechos), 500)

    def test_numero_de_clausula_nao_se_separa_da_frase_ao_dividir_um_paragrafo_grande(self):
        frase = "Indeniza danos causados por curto-circuito, sobrecarga ou variação anormal de tensão."
        trechos = dividir(f"## 3. Coberturas\n\n3.2. **Danos elétricos.** {frase} {frase} {frase}", tamanho=150)
        self.assertGreater(len(trechos), 1)
        self.assertIn("3.2. **Danos elétricos.** Indeniza", trechos[0].conteudo)
        self.assertEqual(trechos[0].clausulas, "3.2")
        self.assertFalse(any(linha.strip() in {"3.2.", "2025."} for t in trechos for linha in t.conteudo.split("\n")))

    def test_codigo_em_cerca_nao_cria_secoes_nem_e_separado_por_linha_em_branco(self):
        texto = "## S\n\nAntes.\n\n```\n# comentário\n\nlinha após vazio\n```\n\nDepois."
        trechos = dividir(texto)
        self.assertEqual([t.secao for t in trechos], ["S"])
        self.assertIn("# comentário\n\nlinha após vazio", trechos[0].conteudo)

    def test_secao_sem_texto_nao_vira_trecho_e_documento_vazio_nao_gera_nada(self):
        self.assertEqual([t.secao for t in dividir("## Vazia\n\n## Com texto\n\nOlá.")], ["Com texto"])
        self.assertEqual(dividir(""), [])

    def test_texto_com_crlf_gera_os_mesmos_trechos(self):
        texto = "# T\n\nIntro.\n\n## A\n\n1.1. Regra.\n\n- a) item"
        self.assertEqual(dividir(texto), dividir(texto.replace("\n", "\r\n")))

    def test_resultado_e_deterministico(self):
        for documento, texto in documentos_reais():
            self.assertEqual(li.dividir_documento(documento, texto), li.dividir_documento(documento, texto))

    def test_clausulas_vem_do_inicio_dos_paragrafos(self):
        conteudo = "## 3. X\n\n3.1. a\n\n3.2. b, como na cláusula 4.1. do texto\n\n- a) item\n\n3.1. repetida"
        self.assertEqual(li.extrair_clausulas(conteudo), "3.1, 3.2")
        self.assertEqual(li.extrair_clausulas("## Pergunta?\n\nResposta sem numeração."), "")

    def test_identificadores_sao_estaveis_e_validos_como_chave_do_search(self):
        self.assertEqual(li.identificador_do_trecho("VLAR-CG-1.0", 7), "VLAR-CG-1_0-007")
        for documento, texto in documentos_reais():
            ids = [t.id for t in li.dividir_documento(documento, texto)]
            self.assertEqual(len(ids), len(set(ids)))
            for chave in ids:
                self.assertRegex(chave, r"^[A-Za-z0-9_=-]+$")

    def test_documentos_reais_respeitam_o_limite_e_nao_perdem_texto(self):
        for tamanho in (300, 600, 1200, 2500, 6000):
            for documento, texto in documentos_reais():
                with self.subTest(documento=documento.id, tamanho=tamanho):
                    trechos = li.dividir_documento(documento, texto, tamanho)
                    self.assertEqual([t.ordem for t in trechos], list(range(1, len(trechos) + 1)))
                    for trecho in trechos:
                        self.assertLessEqual(len(trecho.conteudo), tamanho)
                    reunido = "\n".join(t.conteudo for t in trechos)
                    palavras_perdidas = set(texto.split()) - set(reunido.split())
                    self.assertEqual(palavras_perdidas, set())
                    if tamanho >= 1200:
                        linhas_perdidas = [l for l in texto.split("\n") if l.strip() and l.strip() not in reunido]
                        self.assertEqual(linhas_perdidas, [])

    def test_documentos_reais_geram_um_trecho_por_pergunta_e_por_termo(self):
        por_tipo = {documento.tipo: li.dividir_documento(documento, texto) for documento, texto in documentos_reais()}
        perguntas = sum(1 for _, texto in documentos_reais() for linha in texto.split("\n")
                        if linha.startswith("## ") and linha.endswith("?"))
        self.assertEqual(len(por_tipo["faq"]), perguntas + 1)  # + apresentação do documento
        termos = [t for t in por_tipo["glossario"] if t.secao != li.SECAO_APRESENTACAO]
        self.assertTrue(all(t.conteudo.startswith("## ") for t in termos))
        self.assertTrue(all(t.clausulas for t in por_tipo["condicoes-gerais"] if t.secao[0].isdigit()))

    def test_trecho_leva_o_titulo_do_documento_para_o_embedding_e_os_metadados_para_o_indice(self):
        trecho = dividir("## S\n\nTexto.", titulo="Meu documento")[0]
        self.assertTrue(trecho.texto_para_embedding.startswith("Meu documento\n\n## S"))
        campos = trecho.campos()
        self.assertEqual(campos["documento_id"], "TESTE-1.0")
        self.assertEqual(campos["fonte"], "pasta/teste.md")
        self.assertEqual(campos["vigencia_inicio"], "2025-01-01")
        self.assertIsNone(campos["vigencia_fim"])
        self.assertNotIn("vetor", campos)


class ImpressaoEPlanoTests(unittest.TestCase):
    def setUp(self):
        self.trechos = dividir("## A\n\nUm.\n\n## B\n\nDois.\n\n## C\n\nTrês.")

    def test_impressao_muda_com_texto_metadado_deployment_e_dimensoes(self):
        base = li.calcular_impressao(self.trechos[0], ESPECIFICACAO)
        self.assertRegex(base, r"^[0-9a-f]{64}$")
        self.assertEqual(base, li.calcular_impressao(dividir("## A\n\nUm.")[0], ESPECIFICACAO))
        variacoes = {
            "texto": li.calcular_impressao(dividir("## A\n\nUm!")[0], ESPECIFICACAO),
            "versão": li.calcular_impressao(dividir("## A\n\nUm.", versao="2.0")[0], ESPECIFICACAO),
            "título": li.calcular_impressao(dividir("## A\n\nUm.", titulo="Outro")[0], ESPECIFICACAO),
            "deployment": li.calcular_impressao(self.trechos[0], li.EspecificacaoEmbedding("outro", 8)),
            "dimensões": li.calcular_impressao(self.trechos[0], li.EspecificacaoEmbedding("embeddings", 16)),
        }
        for rotulo, valor in variacoes.items():
            with self.subTest(rotulo):
                self.assertNotEqual(valor, base)

    def test_plano_separa_criar_igual_divergente_e_orfao(self):
        a, b, c = self.trechos
        existentes = {
            a.id: li.calcular_impressao(a, ESPECIFICACAO),
            b.id: "impressao-antiga",
            "TESTE-1_0-099": "x",
            "TESTE-1_0-050": "y",
        }
        plano = li.planejar(self.trechos, existentes, ESPECIFICACAO)
        self.assertEqual([acao.estado for acao in plano.acoes], [li.IGUAL, li.DIVERGENTE, li.CRIAR])
        self.assertEqual(plano.orfaos, ("TESTE-1_0-050", "TESTE-1_0-099"))
        self.assertEqual([acao.trecho.id for acao in plano.a_gravar], [b.id, c.id])
        self.assertEqual((plano.contar(li.CRIAR), plano.contar(li.IGUAL), plano.contar(li.DIVERGENTE)), (1, 1, 1))

    def test_indice_vazio_cria_tudo_e_indice_em_dia_nao_tem_nada_a_gravar(self):
        self.assertEqual(li.planejar(self.trechos, {}, ESPECIFICACAO).contar(li.CRIAR), 3)
        em_dia = {t.id: li.calcular_impressao(t, ESPECIFICACAO) for t in self.trechos}
        plano = li.planejar(self.trechos, em_dia, ESPECIFICACAO)
        self.assertEqual((plano.a_gravar, plano.orfaos), ((), ()))


class DefinicaoDoIndiceTests(unittest.TestCase):
    def setUp(self):
        self.definicao = li.definicao_do_indice("meu-indice", 8)

    def campo(self, nome, definicao=None):
        return next(c for c in (definicao or self.definicao)["fields"] if c["name"] == nome)

    def test_vetor_tem_dimensoes_cosseno_e_nao_e_devolvido_nem_armazenado_duas_vezes(self):
        vetor = self.campo("vetor")
        self.assertEqual((vetor["type"], vetor["dimensions"], vetor["vectorSearchProfile"]),
                         ("Collection(Edm.Single)", 8, li.PERFIL_VETORIAL))
        self.assertFalse(vetor["retrievable"])
        self.assertFalse(vetor["stored"])
        algoritmo = self.definicao["vectorSearch"]["algorithms"][0]
        self.assertEqual((algoritmo["kind"], algoritmo["hnswParameters"]["metric"]), ("hnsw", "cosine"))

    def test_todos_os_atributos_sao_explicitos_porque_o_servico_assume_verdadeiro_em_texto(self):
        for campo in self.definicao["fields"]:
            with self.subTest(campo["name"]):
                self.assertTrue({"key", "searchable", "filterable", "sortable", "facetable", "retrievable"} <= set(campo))
        self.assertTrue(self.campo("id")["key"])
        self.assertEqual(self.campo("conteudo")["analyzer"], li.ANALISADOR)
        self.assertFalse(self.campo("impressao")["searchable"])

    def test_campos_cobrem_tudo_o_que_os_trechos_gravam(self):
        trecho = dividir("## S\n\nTexto.")[0]
        gravados = {*trecho.campos(), "modelo_embeddings", "impressao", "vetor"}
        self.assertEqual(gravados, {c["name"] for c in self.definicao["fields"]})

    def test_sdk_aceita_a_definicao_e_a_devolve_igual(self):
        from azure.search.documents.indexes.models import SearchIndex

        self.assertEqual(SearchIndex(self.definicao).as_dict(), self.definicao)

    def test_indice_igual_ao_esperado_nao_tem_diferencas(self):
        self.assertEqual(li.diferencas_do_esquema(self.definicao, self.definicao), [])

    def test_diferencas_sao_apontadas_em_portugues(self):
        casos = {
            "dimensões": (lambda d: self.campo("vetor", d).update(dimensions=16), "dimensions é 16 em vez de 8"),
            "campo ausente": (lambda d: d["fields"].remove(self.campo("secao", d)), "falta o campo 'secao'"),
            "campo extra": (lambda d: d["fields"].append({"name": "novo", "type": "Edm.String"}), "campos que não fazem parte"),
            "atributo": (lambda d: self.campo("id", d).update(searchable=True), "campo 'id': searchable é True em vez de False"),
            "tipo": (lambda d: self.campo("ordem", d).update(type="Edm.String"), "campo 'ordem': type é 'Edm.String'"),
            "métrica": (lambda d: d["vectorSearch"]["algorithms"][0]["hnswParameters"].update(metric="euclidean"),
                        "métrica é 'euclidean' em vez de 'cosine'"),
            "perfil": (lambda d: d["vectorSearch"]["profiles"].clear(), "falta o perfil vetorial"),
        }
        for rotulo, (alterar, esperado) in casos.items():
            with self.subTest(rotulo):
                alterado = json.loads(json.dumps(self.definicao))
                alterar(alterado)
                self.assertTrue(any(esperado in d for d in li.diferencas_do_esquema(self.definicao, alterado)),
                                li.diferencas_do_esquema(self.definicao, alterado))

    def test_parametros_adicionais_do_servico_nao_contam_como_diferenca(self):
        devolvido = json.loads(json.dumps(self.definicao))
        devolvido["vectorSearch"]["algorithms"][0]["hnswParameters"].update(m=4, efConstruction=400, efSearch=500)
        devolvido["@odata.etag"] = '"0x1"'
        self.assertEqual(li.diferencas_do_esquema(self.definicao, devolvido), [])


class PerguntasDeConferenciaTests(unittest.TestCase):
    def escrever(self, conteudo):
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        caminho = Path(pasta.name) / "perguntas.json"
        caminho.write_text(conteudo if isinstance(conteudo, str) else json.dumps(conteudo), encoding="utf-8")
        return caminho

    def valido(self, **mudancas):
        base = {"schema_version": 1, "sintetico": True, "perguntas": [
            {"id": "R1", "pergunta": "Pergunta?", "esperado": [{"documento_id": "D-1", "texto_contem": "trecho"}]}]}
        base.update(mudancas)
        return base

    def test_arquivo_do_repositorio_e_valido_e_cada_pergunta_tem_resposta_no_corpus(self):
        perguntas = li.carregar_perguntas()
        self.assertGreaterEqual(len(perguntas), 5)
        resultados = [{"documento_id": t.documento.id, "conteudo": t.conteudo}
                      for documento, texto in documentos_reais() for t in li.dividir_documento(documento, texto)]
        for pergunta in perguntas:
            with self.subTest(pergunta.id):
                self.assertIsNotNone(li.posicao_do_esperado(pergunta, resultados))

    def test_perguntas_ficam_fora_da_pasta_de_documentos_recuperaveis(self):
        self.assertNotIn("documentos", li.PERGUNTAS_PADRAO.parts)

    def test_posicao_do_esperado_ignora_caixa_e_devolve_a_primeira_posicao(self):
        pergunta = li.carregar_perguntas(self.escrever(self.valido()))[0]
        resultados = [{"documento_id": "D-1", "conteudo": "nada"}, {"documento_id": "D-2", "conteudo": "TRECHO"},
                      {"documento_id": "D-1", "conteudo": "um Trecho aqui"}]
        self.assertEqual(li.posicao_do_esperado(pergunta, resultados), 3)
        self.assertIsNone(li.posicao_do_esperado(pergunta, resultados[:2]))
        self.assertIsNone(li.posicao_do_esperado(pergunta, []))

    def test_arquivos_invalidos_geram_mensagens_claras(self):
        casos = {
            "JSON inválido": ("{", "JSON inválido"),
            "sem sintetico": (self.valido(sintetico=False), "sintetico"),
            "sem perguntas": (self.valido(perguntas=[]), "'perguntas'"),
            "sem esperado": (self.valido(perguntas=[{"id": "R1", "pergunta": "x", "esperado": []}]), "'esperado'"),
            "id repetido": (self.valido(perguntas=[
                {"id": "R1", "pergunta": "x", "esperado": [{"documento_id": "D", "texto_contem": "t"}]},
                {"id": "R1", "pergunta": "y", "esperado": [{"documento_id": "D", "texto_contem": "t"}]}]), "repetido"),
            "item incompleto": (self.valido(perguntas=[
                {"id": "R1", "pergunta": "x", "esperado": [{"documento_id": "D"}]}]), "documento_id"),
        }
        for rotulo, (conteudo, trecho_da_mensagem) in casos.items():
            with self.subTest(rotulo), self.assertRaises(ErroLab) as contexto:
                li.carregar_perguntas(self.escrever(conteudo))
            self.assertIn(trecho_da_mensagem, str(contexto.exception))
        with self.assertRaises(ErroLab):
            li.carregar_perguntas(Path(tempfile.gettempdir()) / "nao-existe-vlr.json")


class ClienteEmbeddingsTests(unittest.TestCase):
    def test_gera_em_lotes_preserva_a_ordem_e_soma_os_tokens(self):
        openai = OpenAIFalso(dimensoes=8)
        textos = [f"texto {numero}" for numero in range(40)]
        resultado = li.ClienteEmbeddings(openai, "embeddings", 8, lote=16).gerar(textos)
        self.assertEqual([len(chamada[1]) for chamada in openai.chamadas], [16, 16, 8])
        self.assertTrue(all(chamada[0] == "embeddings" for chamada in openai.chamadas))
        self.assertEqual(len(resultado.vetores), 40)
        self.assertEqual(resultado.vetores[5], support.vetor_falso("texto 5", 8))
        self.assertEqual(resultado.modelo, "text-embedding-3-small")
        self.assertGreater(resultado.tokens, 40)

    def test_nenhum_texto_nao_chama_o_servico(self):
        openai = OpenAIFalso()
        self.assertEqual(li.ClienteEmbeddings(openai, "embeddings", 8).gerar([]).vetores, [])
        self.assertEqual(openai.chamadas, [])

    def test_dimensao_diferente_da_esperada_para_com_orientacao(self):
        with self.assertRaises(ErroLab) as contexto:
            li.ClienteEmbeddings(OpenAIFalso(dimensoes=8), "embeddings", 16).gerar(["a"])
        mensagem = str(contexto.exception)
        self.assertIn("8 dimensões", mensagem)
        self.assertIn("--dimensoes 8", mensagem)
        self.assertEqual(contexto.exception.codigo, lab_comum.CODIGO_USO)

    def test_resposta_com_quantidade_errada_de_vetores_para(self):
        openai = OpenAIFalso()
        criar = openai._criar

        def sem_dados(model, input):  # noqa: A002
            resposta = criar(model, input)
            resposta.data = []
            return resposta

        openai.embeddings.create = sem_dados
        with self.assertRaises(ErroLab) as contexto:
            li.ClienteEmbeddings(openai, "embeddings", 8).gerar(["a", "b"])
        self.assertEqual(contexto.exception.codigo, lab_comum.CODIGO_ACESSO)

    def test_modelos_diferentes_entre_lotes_param_a_execucao(self):
        openai = OpenAIFalso()
        modelos = iter(["modelo-a", "modelo-b"])
        criar = openai._criar

        def alternando(model, input):  # noqa: A002
            resposta = criar(model, input)
            resposta.model = next(modelos)
            return resposta

        openai.embeddings.create = alternando
        with self.assertRaises(ErroLab) as contexto:
            li.ClienteEmbeddings(openai, "embeddings", 8, lote=2).gerar(["a", "b", "c"])
        self.assertEqual(contexto.exception.codigo, lab_comum.CODIGO_DIVERGENCIA)

    def test_estimativa_de_tokens_nunca_e_zero(self):
        self.assertEqual(li.estimar_tokens(0), 1)
        self.assertEqual(li.estimar_tokens(300), 100)
        self.assertEqual(li.estimar_tokens(301), 101)

    def test_404_intermitente_de_subdominio_e_repetido_ate_funcionar(self):
        openai = OpenAIFalso()
        falhas = [erro_openai("NotFoundError", 404, "Error code: 404 - Subdomain does not map to a resource.")] * 2
        criar = openai._criar

        def com_falhas(model, input):  # noqa: A002
            if falhas:
                raise falhas.pop()
            return criar(model, input)

        openai.embeddings.create = com_falhas
        saida = io.StringIO()
        with mock.patch.object(li.time, "sleep") as dormir, contextlib.redirect_stderr(saida):
            resultado = li.ClienteEmbeddings(openai, "embeddings", 8).gerar(["a"])
        self.assertEqual(len(resultado.vetores), 1)
        self.assertEqual([chamada.args[0] for chamada in dormir.call_args_list],
                         [li.ESPERA_DO_SUBDOMINIO, 2 * li.ESPERA_DO_SUBDOMINIO], "a espera cresce")
        self.assertIn(f"tentativa 1 de {li.TENTATIVAS_DO_SUBDOMINIO}", saida.getvalue())

    def test_404_intermitente_que_nao_passa_vira_o_erro_original_depois_das_tentativas(self):
        openai = OpenAIFalso()
        openai.erro = erro_openai("NotFoundError", 404, "Error code: 404 - Subdomain does not map to a resource.")
        with mock.patch.object(li.time, "sleep"), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(Exception) as contexto:
                li.ClienteEmbeddings(openai, "embeddings", 8).gerar(["a"])
        self.assertIs(contexto.exception, openai.erro)
        self.assertEqual(len(openai.chamadas), li.TENTATIVAS_DO_SUBDOMINIO)

    def test_outros_erros_nao_sao_repetidos(self):
        for erro in (erro_openai("NotFoundError", 404, "Error code: 404 - DeploymentNotFound"),
                     erro_openai("PermissionDeniedError", 403, "Subdomain does not map to a resource."),
                     RuntimeError("Subdomain does not map to a resource.")):
            with self.subTest(erro=type(erro).__name__):
                openai = OpenAIFalso()
                openai.erro = erro
                with mock.patch.object(li.time, "sleep") as dormir:
                    with self.assertRaises(Exception):
                        li.ClienteEmbeddings(openai, "embeddings", 8).gerar(["a"])
                self.assertEqual(len(openai.chamadas), 1)
                dormir.assert_not_called()


class ValidacaoDeArgumentosTests(unittest.TestCase):
    def test_nomes_que_formam_enderecos_so_aceitam_o_formato_do_azure(self):
        for validar, valido in ((li.validar_busca, "srch-vlr-abc123"), (li.validar_modelos, "ais-vlr-abc123"),
                                (li.validar_indice, "vareleira-lar-l100")):
            self.assertEqual(validar(valido), valido)
            for invalido in ("meu-site.exemplo/x", "UPPER", "a b", "-abc", "abc-", "x" * 130, "", "a..b"):
                with self.subTest(validar=validar, valor=invalido), self.assertRaises(Exception):
                    validar(invalido)

    def test_nomes_de_busca_e_indice_nao_aceitam_hifens_seguidos(self):
        for validar in (li.validar_busca, li.validar_indice):
            with self.assertRaises(Exception):
                validar("abc--def")

    def test_numeros_fora_do_intervalo_sao_recusados(self):
        self.assertEqual(li.validar_dimensoes("1536"), 1536)
        self.assertEqual(li.validar_k("3"), 3)
        for validar, valor in ((li.validar_dimensoes, "0"), (li.validar_dimensoes, "9999"), (li.validar_dimensoes, "x"),
                               (li.validar_k, "0"), (li.validar_k, "11"), (li.validar_tamanho_maximo, "100")):
            with self.subTest(valor=valor), self.assertRaises(Exception):
                validar(valor)

    def test_deployment_aceita_o_formato_do_azure(self):
        for valido in ("embeddings", "text-embedding-3-small", "emb_1.0"):
            self.assertEqual(li.validar_deployment(valido), valido)
        with self.assertRaises(Exception):
            li.validar_deployment("com espaço")


if __name__ == "__main__":
    unittest.main()
