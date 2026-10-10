import contextlib
import io
import unittest
from unittest import mock

import support  # noqa: F401  (configura o caminho dos scripts)
import lab_comum
import verificar_documentos
from support import ContainerFalso, copiar_pacote

CONTA = "stvlrag1234567890"


class VerificacaoTests(unittest.TestCase):
    def setUp(self):
        self.pasta, self.inventario = copiar_pacote()
        self.addCleanup(self.pasta.cleanup)
        self.documentos = lab_comum.carregar_inventario(self.inventario).documentos
        self.container = ContainerFalso()
        for documento in self.documentos:
            self.container.colocar(documento.blob, lab_comum.ler_conteudo(documento),
                                   documento.metadados_blob, documento.tipo_conteudo)
        self.primeiro = self.documentos[0]

    def rodar(self, status_anonimo=409):
        saida = io.StringIO()
        argumentos = ["--conta", CONTA, "--inventario", str(self.inventario)]
        with mock.patch.object(lab_comum, "criar_container", return_value=self.container), \
                mock.patch.object(verificar_documentos, "_status_anonimo", return_value=status_anonimo), \
                contextlib.redirect_stdout(saida), contextlib.redirect_stderr(saida):
            codigo = verificar_documentos.principal(argumentos)
        return codigo, saida.getvalue()

    def test_base_conforme_e_aprovada(self):
        codigo, saida = self.rodar()
        self.assertEqual(codigo, lab_comum.CODIGO_OK)
        self.assertIn("Verificação aprovada", saida)
        self.assertNotIn("FALHA", saida)

    def test_documento_ausente_reprova(self):
        del self.container.blobs[self.primeiro.blob]
        codigo, saida = self.rodar()
        self.assertEqual(codigo, lab_comum.CODIGO_DIVERGENCIA)
        self.assertIn("Documentos ausentes", saida)

    def test_blob_fora_do_inventario_reprova(self):
        self.container.colocar("vareleira-lar/rascunho.md", b"x")
        codigo, saida = self.rodar()
        self.assertEqual(codigo, lab_comum.CODIGO_DIVERGENCIA)
        self.assertIn("Blobs fora do inventário", saida)

    def test_conteudo_alterado_com_mesmo_tamanho_reprova_pelo_hash(self):
        blob = self.container.blobs[self.primeiro.blob]
        blob.dados = blob.dados[::-1]
        codigo, saida = self.rodar()
        self.assertEqual(codigo, lab_comum.CODIGO_DIVERGENCIA)
        self.assertIn("hash diferente", saida)

    def test_metadado_ou_tipo_incorreto_reprova(self):
        blob = self.container.blobs[self.primeiro.blob]
        blob.metadata = {}
        blob.content_type = "application/octet-stream"
        codigo, saida = self.rodar()
        self.assertEqual(codigo, lab_comum.CODIGO_DIVERGENCIA)
        self.assertIn("metadados ausentes ou diferentes: documento_id", saida)
        self.assertIn("tipo de conteúdo", saida)

    def test_leitura_anonima_permitida_reprova_e_aponta_o_endereco(self):
        codigo, saida = self.rodar(status_anonimo=200)
        self.assertEqual(codigo, lab_comum.CODIGO_DIVERGENCIA)
        self.assertIn("LEITURA ANÔNIMA PERMITIDA", saida)

    def test_respostas_que_negam_o_acesso_anonimo_aprovam(self):
        for status in (401, 403, 404, 409):
            with self.subTest(status=status):
                resultado = verificar_documentos.verificar_acesso_anonimo(
                    CONTA, "base-documental", ["a/b.md"], consultar=lambda url, s=status: s)
                self.assertTrue(resultado.ok, resultado.detalhe)

    def test_falha_de_rede_ou_resposta_inesperada_nao_conta_como_negado(self):
        def sem_rede(url):
            raise TimeoutError("sem resposta")

        for consultar in (sem_rede, lambda url: 500):
            with self.subTest(consultar=getattr(consultar, "__name__", "http500")):
                resultado = verificar_documentos.verificar_acesso_anonimo(
                    CONTA, "base-documental", ["a/b.md"], consultar=consultar)
                self.assertFalse(resultado.ok)
                self.assertIn("não foi possível confirmar", resultado.detalhe)

    def test_teste_anonimo_pede_listagem_e_cada_blob_so_no_endereco_da_conta(self):
        pedidos = []
        verificar_documentos.verificar_acesso_anonimo(
            CONTA, "base-documental", ["vareleira-lar/faq-v1.0.md"], consultar=lambda url: pedidos.append(url) or 409)
        self.assertEqual(pedidos, [
            f"https://{CONTA}.blob.core.windows.net/base-documental?restype=container&comp=list",
            f"https://{CONTA}.blob.core.windows.net/base-documental/vareleira-lar/faq-v1.0.md",
        ])


if __name__ == "__main__":
    unittest.main()
