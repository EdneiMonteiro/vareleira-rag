import contextlib
import io
import json
import unittest
from unittest import mock

import support  # noqa: F401  (configura o caminho dos scripts)
import atualizar_hashes_inventario
import lab_comum
from support import copiar_pacote


class InventarioTests(unittest.TestCase):
    def setUp(self):
        self.pasta, self.inventario = copiar_pacote()
        self.addCleanup(self.pasta.cleanup)
        self.documentos = self.inventario.parent / "documentos"

    def _alterar_inventario(self, funcao):
        bruto = json.loads(self.inventario.read_text(encoding="utf-8"))
        funcao(bruto)
        self.inventario.write_text(json.dumps(bruto, ensure_ascii=False), encoding="utf-8")

    def test_pacote_publicado_confere_com_o_inventario(self):
        inventario = lab_comum.carregar_e_validar()
        self.assertEqual(len(inventario.documentos), 3)
        self.assertEqual(len({d.blob for d in inventario.documentos}), 3)

    def test_cada_documento_se_identifica_como_sintetico_e_confere_id_e_versao(self):
        for documento in lab_comum.carregar_inventario().documentos:
            texto = documento.arquivo.read_text(encoding="utf-8")
            self.assertIn("Documento sintético", texto, documento.id)
            self.assertIn(f"| Identificador | {documento.id} |", texto)
            self.assertIn(f"| Versão | {documento.versao} |", texto)

    def test_conteudo_alterado_e_recusado(self):
        arquivo = self.documentos / "vareleira-lar-faq-v1.0.md"
        arquivo.write_text(arquivo.read_text(encoding="utf-8") + "\nLinha nova.\n", encoding="utf-8")
        with self.assertRaisesRegex(lab_comum.ErroLab, "hash não confere"):
            lab_comum.carregar_e_validar(self.inventario)

    def test_final_de_linha_do_windows_nao_altera_o_hash(self):
        arquivo = self.documentos / "vareleira-lar-glossario-v1.0.md"
        arquivo.write_bytes(arquivo.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
        lab_comum.carregar_e_validar(self.inventario)

    def test_arquivo_fora_do_inventario_e_recusado(self):
        (self.documentos / "rascunho.md").write_text("# Rascunho\n", encoding="utf-8")
        with self.assertRaisesRegex(lab_comum.ErroLab, "fora do inventário: rascunho.md"):
            lab_comum.carregar_e_validar(self.inventario)

    def test_arquivos_do_sistema_sao_ignorados(self):
        (self.documentos / "Thumbs.db").write_bytes(b"\x00")
        (self.documentos / ".DS_Store").write_bytes(b"\x00")
        lab_comum.carregar_e_validar(self.inventario)

    def test_documento_ausente_e_recusado(self):
        (self.documentos / "vareleira-lar-faq-v1.0.md").unlink()
        with self.assertRaisesRegex(lab_comum.ErroLab, "arquivo não encontrado"):
            lab_comum.carregar_e_validar(self.inventario)

    def test_documento_fora_de_utf8_e_recusado(self):
        (self.documentos / "vareleira-lar-faq-v1.0.md").write_bytes("residência".encode("latin-1"))
        with self.assertRaisesRegex(lab_comum.ErroLab, "codificado em UTF-8"):
            lab_comum.carregar_e_validar(self.inventario)
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaisesRegex(lab_comum.ErroLab, "codificado em UTF-8"):
            atualizar_hashes_inventario.atualizar(self.inventario, gravar=True)

    def test_entradas_perigosas_ou_inconsistentes_sao_recusadas(self):
        casos = {
            "fora da pasta documentos": (lambda b: b["documentos"][0].update(arquivo="../inventario.json"), "formato inválido"),
            "caminho absoluto": (lambda b: b["documentos"][0].update(arquivo="C:/Windows/win.ini"), "formato inválido"),
            "blob com ..": (lambda b: b["documentos"][0].update(blob="vareleira-lar/../x.md"), "não pode conter"),
            "id repetido": (lambda b: b["documentos"][1].update(id=b["documentos"][0]["id"]), "repetido no campo 'id'"),
            "blob repetido": (lambda b: b["documentos"][1].update(blob=b["documentos"][0]["blob"]), "repetido no campo 'blob'"),
            "não sintético": (lambda b: b.update(sintetico=False), "sintetico"),
            "hash inválido": (lambda b: b["documentos"][0].update(sha256="abc"), "formato inválido"),
            "revisão desconhecida": (lambda b: b["documentos"][0]["revisao_real"].update(status="talvez"), "revisao_real.status"),
        }
        for nome, (alteracao, esperado) in casos.items():
            with self.subTest(nome):
                self._alterar_inventario(alteracao)
                with self.assertRaisesRegex(lab_comum.ErroLab, esperado):
                    lab_comum.carregar_inventario(self.inventario)
                pasta, self.inventario = copiar_pacote()
                self.addCleanup(pasta.cleanup)

    def test_aviso_de_revisao_aparece_enquanto_houver_revisao_pendente(self):
        def aviso():
            return lab_comum.aviso_de_revisao(lab_comum.carregar_inventario(self.inventario))

        def aprovar_todos(bruto):
            for documento in bruto["documentos"]:
                documento["revisao_real"]["status"] = "aprovada"

        self._alterar_inventario(aprovar_todos)
        self.assertIsNone(aviso())
        self._alterar_inventario(lambda b: b["documentos"][0]["revisao_real"].update(status="pendente"))
        self.assertIn("revisão de conteúdo pendente", aviso())

    def test_atualizador_so_grava_com_pedido_explicito(self):
        arquivo = self.documentos / "vareleira-lar-faq-v1.0.md"
        arquivo.write_text(arquivo.read_text(encoding="utf-8") + "\nLinha nova.\n", encoding="utf-8")
        antes = self.inventario.read_text(encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(atualizar_hashes_inventario.atualizar(self.inventario, gravar=False), lab_comum.CODIGO_DIVERGENCIA)
            self.assertEqual(self.inventario.read_text(encoding="utf-8"), antes)
            self.assertEqual(atualizar_hashes_inventario.atualizar(self.inventario, gravar=True), lab_comum.CODIGO_OK)
        lab_comum.carregar_e_validar(self.inventario)

    def test_atualizador_pela_linha_de_comando(self):
        argumentos = ["--inventario", str(self.inventario)]
        with contextlib.redirect_stdout(io.StringIO()) as saida:
            self.assertEqual(atualizar_hashes_inventario.principal(argumentos), lab_comum.CODIGO_OK)
        self.assertIn("já está atualizado", saida.getvalue())
        (self.documentos / "vareleira-lar-faq-v1.0.md").unlink()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()) as erro:
            self.assertEqual(atualizar_hashes_inventario.principal(argumentos), lab_comum.CODIGO_USO)
        self.assertIn("arquivo não encontrado", erro.getvalue())


class ArgumentosTests(unittest.TestCase):
    def test_nome_de_conta_que_poderia_redirecionar_o_token_e_recusado(self):
        parser = lab_comum.criar_parser("teste")
        for conta in ("meu-site.exemplo/x", "UPPER", "ab", "a" * 25, "conta.com", "conta#x"):
            with self.subTest(conta=conta), self.assertRaises(SystemExit) as saida:
                with mock.patch("sys.stderr"):
                    parser.parse_args(["--conta", conta])
            self.assertEqual(saida.exception.code, lab_comum.CODIGO_USO)
        self.assertEqual(parser.parse_args(["--conta", "stvlrag1234567890"]).container, lab_comum.CONTAINER_PADRAO)

    def test_conta_ausente_ou_sem_valor_orienta_em_portugues(self):
        parser = lab_comum.criar_parser("teste")
        for argumentos in ([], ["--conta"]):
            with self.subTest(argumentos=argumentos), self.assertRaises(SystemExit) as saida:
                with contextlib.redirect_stderr(io.StringIO()) as erro:
                    parser.parse_args(argumentos)
            self.assertEqual(saida.exception.code, lab_comum.CODIGO_USO)
            self.assertNotIn("expected one argument", erro.getvalue())
            self.assertIn("nomeConta", erro.getvalue())


if __name__ == "__main__":
    unittest.main()
