import contextlib
import io
import unittest
from unittest import mock

import support  # noqa: F401  (configura o caminho dos scripts)
import carregar_documentos
import lab_comum
from support import ContainerFalso, copiar_pacote

CONTA = "stvlrag1234567890"


def rodar(container, inventario, *opcoes):
    """Executa o script com um contêiner falso e devolve (código de saída, texto impresso)."""
    saida = io.StringIO()
    argumentos = ["--conta", CONTA, "--inventario", str(inventario), *opcoes]
    with mock.patch.object(lab_comum, "criar_container", return_value=container), \
            contextlib.redirect_stdout(saida), contextlib.redirect_stderr(saida):
        codigo = carregar_documentos.principal(argumentos)
    return codigo, saida.getvalue()


class CargaTests(unittest.TestCase):
    def setUp(self):
        self.pasta, self.inventario = copiar_pacote()
        self.addCleanup(self.pasta.cleanup)
        self.container = ContainerFalso()
        self.documentos = lab_comum.carregar_inventario(self.inventario).documentos
        self.primeiro = self.documentos[0]

    def test_simulacao_nao_envia_nada(self):
        codigo, saida = rodar(self.container, self.inventario)
        self.assertEqual(codigo, lab_comum.CODIGO_OK)
        self.assertEqual(self.container.envios, [])
        self.assertIn("SIMULAÇÃO", saida)
        self.assertEqual(saida.count("[criar"), 3)

    def test_execucao_envia_conteudo_normalizado_com_metadados_e_tipo(self):
        arquivo = self.primeiro.arquivo
        arquivo.write_bytes(arquivo.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
        codigo, _ = rodar(self.container, self.inventario, "--executar")
        self.assertEqual(codigo, lab_comum.CODIGO_OK)
        self.assertEqual(sorted(self.container.envios), sorted(d.blob for d in self.documentos))
        for documento in self.documentos:
            blob = self.container.blobs[documento.blob]
            self.assertEqual(lab_comum.calcular_sha256(blob.dados), documento.sha256)
            self.assertNotIn(b"\r\n", blob.dados)
            self.assertEqual(blob.metadata, documento.metadados_blob)
            self.assertEqual(blob.content_type, documento.tipo_conteudo)

    def test_reexecucao_nao_reenvia_documentos_iguais(self):
        rodar(self.container, self.inventario, "--executar")
        envios = list(self.container.envios)
        codigo, saida = rodar(self.container, self.inventario, "--executar")
        self.assertEqual(codigo, lab_comum.CODIGO_OK)
        self.assertEqual(self.container.envios, envios)
        self.assertIn("3 já igual", saida)

    def test_divergencia_interrompe_sem_alterar_nada(self):
        self.container.colocar(self.primeiro.blob, b"conteudo diferente")
        codigo, saida = rodar(self.container, self.inventario, "--executar")
        self.assertEqual(codigo, lab_comum.CODIGO_DIVERGENCIA)
        self.assertEqual(self.container.envios, [])
        self.assertEqual(self.container.blobs[self.primeiro.blob].dados, b"conteudo diferente")
        self.assertEqual(len(self.container.blobs), 1, "nem os documentos ausentes devem ser criados")
        self.assertIn("PARADA", saida)

    def test_divergencia_na_simulacao_tambem_e_sinalizada(self):
        self.container.colocar(self.primeiro.blob, b"conteudo diferente")
        codigo, _ = rodar(self.container, self.inventario)
        self.assertEqual(codigo, lab_comum.CODIGO_DIVERGENCIA)

    def test_substituicao_exige_pedido_explicito(self):
        self.container.colocar(self.primeiro.blob, b"conteudo diferente")
        codigo, saida = rodar(self.container, self.inventario, "--executar", "--substituir-divergentes")
        self.assertEqual(codigo, lab_comum.CODIGO_OK)
        self.assertEqual(lab_comum.calcular_sha256(self.container.blobs[self.primeiro.blob].dados), self.primeiro.sha256)
        self.assertIn("TROCADO", saida)

    def test_blob_alterado_depois_da_simulacao_nao_e_sobrescrito(self):
        self.container.colocar(self.primeiro.blob, b"antigo")

        def outra_pessoa_altera(nome):
            if nome == self.primeiro.blob:
                self.container.colocar(nome, b"alguem mudou")

        self.container.antes_de_enviar = outra_pessoa_altera
        codigo, _ = rodar(self.container, self.inventario, "--executar", "--substituir-divergentes")
        self.assertEqual(codigo, lab_comum.CODIGO_DIVERGENCIA)
        self.assertEqual(self.container.blobs[self.primeiro.blob].dados, b"alguem mudou")
        self.assertEqual(self.container.envios, [])

    def test_blob_criado_por_outra_pessoa_durante_o_envio_nao_e_sobrescrito(self):
        def outra_pessoa_cria(nome):
            if nome == self.primeiro.blob and nome not in self.container.blobs:
                self.container.colocar(nome, b"criado por outra pessoa")

        self.container.antes_de_enviar = outra_pessoa_cria
        codigo, _ = rodar(self.container, self.inventario, "--executar")
        self.assertEqual(codigo, lab_comum.CODIGO_DIVERGENCIA)
        self.assertEqual(self.container.blobs[self.primeiro.blob].dados, b"criado por outra pessoa")

    def test_conteiner_inexistente_gera_orientacao(self):
        codigo, saida = rodar(ContainerFalso(existe=False), self.inventario)
        self.assertEqual(codigo, lab_comum.CODIGO_ACESSO)
        self.assertIn("não existe", saida)

    def test_arquivo_local_diferente_do_inventario_para_antes_de_acessar_o_azure(self):
        self.primeiro.arquivo.write_text("outro texto\n", encoding="utf-8")
        with mock.patch.object(lab_comum, "criar_container") as criar:
            saida = io.StringIO()
            with contextlib.redirect_stderr(saida):
                codigo = carregar_documentos.principal(["--conta", CONTA, "--inventario", str(self.inventario), "--executar"])
        self.assertEqual(codigo, lab_comum.CODIGO_USO)
        criar.assert_not_called()
        self.assertIn("hash não confere", saida.getvalue())


if __name__ == "__main__":
    unittest.main()
