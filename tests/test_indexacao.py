import contextlib
import io
import unittest
from unittest import mock

import support  # noqa: F401  (configura o caminho dos scripts)
import indexar_documentos
import lab_comum
import lab_indexacao as li
from azure.core.exceptions import HttpResponseError
from support import IndiceFalso, OpenAIFalso, container_com_documentos, copiar_pacote, rodar_script

CONTA, BUSCA, MODELOS = "stvlrag1234567890", "srch-vlr-exemplo", "ais-vlr-exemplo"
DIMENSOES = 8


class IndexacaoTests(unittest.TestCase):
    def setUp(self):
        self.pasta, self.inventario = copiar_pacote()
        self.addCleanup(self.pasta.cleanup)
        self.container = container_com_documentos(self.inventario)
        self.indice = IndiceFalso()
        self.openai = OpenAIFalso(dimensoes=DIMENSOES)
        self.documentos = lab_comum.carregar_inventario(self.inventario).documentos
        self.abriu_indice = mock.Mock(return_value=self.indice)

    def rodar(self, *opcoes):
        argumentos = ["--conta", CONTA, "--busca", BUSCA, "--modelos", MODELOS, "--dimensoes", str(DIMENSOES),
                      "--inventario", str(self.inventario), *opcoes]
        return rodar_script(indexar_documentos, argumentos, container=self.container,
                            abrir_indice=self.abriu_indice, openai=self.openai)

    def total_de_trechos(self):
        return sum(len(li.dividir_documento(d, lab_comum.ler_conteudo(d).decode("utf-8"))) for d in self.documentos)

    def indexar(self):
        codigo, saida = self.rodar("--executar")
        self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)
        return saida

    def test_simulacao_mostra_o_plano_e_nao_altera_nem_calcula_nada(self):
        codigo, saida = self.rodar()
        self.assertEqual(codigo, lab_comum.CODIGO_OK)
        self.assertIn("SIMULAÇÃO", saida)
        self.assertIn(f"{self.total_de_trechos()} a criar", saida)
        self.assertIn("[criar     ] índice", saida)
        self.assertEqual((self.indice.operacoes, self.openai.chamadas), ([], []))

    def test_execucao_cria_o_indice_e_grava_cada_trecho_com_vetor_modelo_e_impressao(self):
        saida = self.indexar()
        total = self.total_de_trechos()
        self.assertEqual(len(self.indice.documentos), total)
        self.assertEqual(self.indice.definicao, li.definicao_do_indice("vareleira-lar-l100", DIMENSOES))
        self.assertEqual(self.openai.textos_enviados, total)
        self.assertGreater(len(self.openai.chamadas), 1, "os embeddings são pedidos em lotes")
        especificacao = li.EspecificacaoEmbedding("embeddings", DIMENSOES)
        for registro in self.indice.documentos.values():
            self.assertEqual(len(registro["vetor"]), DIMENSOES)
            self.assertEqual(registro["modelo_embeddings"], "text-embedding-3-small")
            self.assertRegex(registro["impressao"], r"^[0-9a-f]{64}$")
            self.assertTrue(registro["conteudo"].startswith("#"), "cada trecho começa pela linha do título")
        self.assertEqual(self.openai.chamadas[0][0], "embeddings")
        self.assertIn(f"{total} criado(s)", saida)
        self.assertEqual(
            li.planejar(
                [t for d in self.documentos for t in li.dividir_documento(d, lab_comum.ler_conteudo(d).decode("utf-8"))],
                {k: v["impressao"] for k, v in self.indice.documentos.items()}, especificacao,
            ).a_gravar, ())

    def test_reexecucao_nao_chama_o_modelo_nem_grava_de_novo(self):
        self.indexar()
        operacoes, chamadas = list(self.indice.operacoes), len(self.openai.chamadas)
        saida = self.indexar()
        self.assertEqual(self.indice.operacoes, operacoes)
        self.assertEqual(len(self.openai.chamadas), chamadas)
        self.assertIn("0 criado(s), 0 trocado(s)", saida)
        self.assertIn("nada a fazer", saida)

    def test_trecho_com_conteudo_diferente_para_e_so_troca_com_pedido_explicito(self):
        self.indexar()
        chave = sorted(self.indice.documentos)[3]
        self.indice.documentos[chave]["impressao"] = "impressao-de-outro-texto"
        antes, chamadas = dict(self.indice.documentos[chave]), len(self.openai.chamadas)
        codigo, saida = self.rodar("--executar")
        self.assertEqual(codigo, lab_comum.CODIGO_DIVERGENCIA)
        self.assertIn("PARADA", saida)
        self.assertIn("só será trocado com --substituir-divergentes", saida)
        self.assertEqual((self.indice.documentos[chave], len(self.openai.chamadas)), (antes, chamadas))
        codigo, saida = self.rodar("--executar", "--substituir-divergentes")
        self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)
        self.assertIn("será trocado (--substituir-divergentes)", saida)
        self.assertNotIn("só será trocado", saida, "com a opção informada, o plano não diz que falta a opção")
        self.assertNotEqual(self.indice.documentos[chave]["impressao"], "impressao-de-outro-texto")
        self.assertEqual(len(self.openai.chamadas[-1][1]), 1, "só o trecho divergente é calculado de novo")

    def test_trecho_orfao_para_e_so_e_removido_com_pedido_explicito(self):
        self.indexar()
        self.indice.documentos["VLAR-CG-1_0-099"] = {"id": "VLAR-CG-1_0-099", "impressao": "x", "vetor": [0] * DIMENSOES}
        codigo, saida = self.rodar("--executar")
        self.assertEqual(codigo, lab_comum.CODIGO_DIVERGENCIA)
        self.assertIn("VLAR-CG-1_0-099", saida)
        self.assertIn("só será removido com --remover-orfaos", saida)
        self.assertIn("VLAR-CG-1_0-099", self.indice.documentos)
        codigo, saida = self.rodar("--executar", "--remover-orfaos")
        self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)
        self.assertIn("será removido (--remover-orfaos)", saida)
        self.assertNotIn("só será removido", saida)
        self.assertNotIn("VLAR-CG-1_0-099", self.indice.documentos)
        self.assertEqual(len(self.indice.documentos), self.total_de_trechos())

    def test_simulacao_tambem_sinaliza_divergencia_e_orfao_sem_alterar(self):
        self.indexar()
        operacoes = list(self.indice.operacoes)
        self.indice.documentos["VLAR-CG-1_0-099"] = {"id": "VLAR-CG-1_0-099", "impressao": "x", "vetor": [0] * DIMENSOES}
        codigo, _ = self.rodar()
        self.assertEqual(codigo, lab_comum.CODIGO_DIVERGENCIA)
        self.assertEqual(self.indice.operacoes, operacoes)

    def test_indice_com_outra_definicao_para_sem_alterar_e_aponta_a_diferenca(self):
        self.indexar()
        operacoes = list(self.indice.operacoes)
        codigo, saida = self.rodar("--dimensoes", "16", "--executar")
        self.assertEqual(codigo, lab_comum.CODIGO_DIVERGENCIA)
        self.assertIn("dimensions é 8 em vez de 16", saida)
        self.assertIn("--recriar-indice", saida)
        self.assertEqual(self.indice.operacoes, operacoes)

    def test_recriar_indice_apaga_e_cria_de_novo_mas_so_depois_de_calcular_os_vetores(self):
        self.indexar()
        self.openai.dimensoes = 16
        codigo, _ = self.rodar("--dimensoes", "16", "--executar", "--recriar-indice")
        self.assertEqual(codigo, lab_comum.CODIGO_OK)
        self.assertEqual([op for op, _ in self.indice.operacoes if op in ("apagar", "criar")],
                         ["criar", "apagar", "criar"])
        self.assertTrue(all(len(r["vetor"]) == 16 for r in self.indice.documentos.values()))
        self.assertEqual(len(self.indice.documentos), self.total_de_trechos())

    def test_recriar_indice_na_simulacao_nao_apaga_nada(self):
        self.indexar()
        operacoes = list(self.indice.operacoes)
        codigo, saida = self.rodar("--recriar-indice")
        self.assertEqual(codigo, lab_comum.CODIGO_OK)
        self.assertIn("[recriar", saida)
        self.assertEqual(self.indice.operacoes, operacoes)

    def test_falha_do_servico_de_modelos_nao_cria_o_indice_nem_grava(self):
        erro = HttpResponseError("falha do serviço de modelos")
        erro.status_code = 500
        self.openai.erro = erro
        codigo, _ = self.rodar("--executar")
        self.assertNotEqual(codigo, lab_comum.CODIGO_OK)
        self.assertEqual((self.indice.operacoes, self.indice.definicao), ([], None))

    def test_vetores_com_dimensao_errada_nao_criam_o_indice(self):
        self.openai.dimensoes = 4
        codigo, saida = self.rodar("--executar")
        self.assertEqual(codigo, lab_comum.CODIGO_USO)
        self.assertIn("4 dimensões", saida)
        self.assertEqual(self.indice.operacoes, [])

    def test_base_documental_diferente_do_inventario_para_antes_de_tocar_no_indice(self):
        self.container.blobs[self.documentos[0].blob].dados += b" alterado"
        codigo, saida = self.rodar("--executar")
        self.assertEqual(codigo, lab_comum.CODIGO_DIVERGENCIA)
        self.assertIn("Desafio 01", saida)
        self.abriu_indice.assert_not_called()
        self.assertEqual(self.openai.chamadas, [])

    def test_documento_ausente_no_conteiner_para_antes_de_tocar_no_indice(self):
        del self.container.blobs[self.documentos[1].blob]
        codigo, saida = self.rodar()
        self.assertEqual(codigo, lab_comum.CODIGO_DIVERGENCIA)
        self.assertIn("não está no contêiner", saida)
        self.abriu_indice.assert_not_called()

    def test_conteiner_inexistente_gera_orientacao(self):
        self.container.existe = False
        codigo, saida = self.rodar()
        self.assertEqual(codigo, lab_comum.CODIGO_ACESSO)
        self.assertIn("não existe", saida)

    def test_o_tamanho_maximo_muda_os_trechos_e_o_plano_acusa_a_diferenca(self):
        self.indexar()
        codigo, saida = self.rodar("--tamanho-maximo", "300")
        self.assertEqual(codigo, lab_comum.CODIGO_DIVERGENCIA)
        self.assertIn("divergentes", saida)

    def test_nenhum_argumento_obrigatorio_ausente_passa(self):
        saida = io.StringIO()
        with contextlib.redirect_stderr(saida), self.assertRaises(SystemExit) as contexto:
            indexar_documentos.principal(["--conta", CONTA])
        self.assertEqual(contexto.exception.code, lab_comum.CODIGO_USO)
        self.assertIn("--busca", saida.getvalue())
        self.assertIn("saída nomeBusca", saida.getvalue())


class RegistroDoSearchTests(unittest.TestCase):
    def resultado(self, chave, ok, mensagem=None):
        from types import SimpleNamespace
        return SimpleNamespace(key=chave, succeeded=ok, error_message=mensagem)

    def test_documento_recusado_pelo_servico_interrompe_com_a_chave_e_sem_o_conteudo(self):
        with self.assertRaises(lab_comum.ErroLab) as contexto:
            li.IndiceBusca._conferir([self.resultado("a", True), self.resultado("b", False, "dimensão inválida")], "gravar")
        mensagem = str(contexto.exception)
        self.assertIn("b: dimensão inválida", mensagem)
        self.assertEqual(contexto.exception.codigo, lab_comum.CODIGO_ACESSO)

    def test_todos_aceitos_nao_gera_erro(self):
        li.IndiceBusca._conferir([self.resultado("a", True)], "gravar")


if __name__ == "__main__":
    unittest.main()
