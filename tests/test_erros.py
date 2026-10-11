import argparse
import contextlib
import io
import logging
import os
import sys
import unittest
from unittest import mock

import support  # noqa: F401  (configura o caminho dos scripts)
import lab_comum
from azure.core.exceptions import ClientAuthenticationError, HttpResponseError, ServiceRequestError
from azure.identity import CredentialUnavailableError


def com_status(erro, status=None, codigo=None):
    erro.status_code = status
    erro.error_code = codigo
    return erro


class TraducaoDeErrosTests(unittest.TestCase):
    def traduzir(self, erro):
        return lab_comum.traduzir_erro(erro, "stvlrag1234567890", "base-documental")

    def test_falta_de_permissao_de_dados_explica_o_papel_necessario(self):
        mensagem, codigo = self.traduzir(
            com_status(HttpResponseError("x"), 403, "AuthorizationPermissionMismatch"))
        self.assertEqual(codigo, lab_comum.CODIGO_ACESSO)
        self.assertIn("Storage Blob Data Contributor", mensagem)
        self.assertIn("alguns minutos", mensagem)

    def test_sem_login_orienta_az_login(self):
        for classe in (CredentialUnavailableError, ClientAuthenticationError):
            with self.subTest(classe=classe.__name__):
                mensagem, codigo = self.traduzir(com_status(classe("x")))
                self.assertEqual(codigo, lab_comum.CODIGO_ACESSO)
                self.assertIn("az login", mensagem)
                self.assertIn("az --version", mensagem)

    def test_token_recusado_orienta_sobre_tenant(self):
        mensagem, _ = self.traduzir(com_status(ClientAuthenticationError("x"), 401, "AuthenticationFailed"))
        self.assertIn("--tenant-id", mensagem)

    def test_falha_de_rede_orienta_sobre_o_nome_da_conta(self):
        mensagem, codigo = self.traduzir(ServiceRequestError("dns"))
        self.assertEqual(codigo, lab_comum.CODIGO_ACESSO)
        self.assertIn("stvlrag1234567890", mensagem)

    def test_mensagem_tecnica_do_servico_nao_vai_para_a_saida(self):
        segredo = "SEGREDO-FICTICIO-QUE-NAO-DEVE-APARECER"
        mensagem, _ = self.traduzir(com_status(HttpResponseError(segredo), 500, "InternalError"))
        self.assertNotIn(segredo, mensagem)
        self.assertIn("--detalhes", mensagem)

    def test_defeito_do_script_tem_codigo_proprio(self):
        _, codigo = self.traduzir(KeyError("campo"))
        self.assertEqual(codigo, lab_comum.CODIGO_INESPERADO)


class RegistroDoSdkTests(unittest.TestCase):
    def setUp(self):
        self.registro = logging.getLogger("azure")
        self.addCleanup(self.registro.setLevel, self.registro.level)
        self.registro.setLevel(logging.NOTSET)

    def executar(self, detalhes):
        argumentos = argparse.Namespace(conta="stvlrag1234567890", container="base-documental", detalhes=detalhes)
        with contextlib.redirect_stderr(io.StringIO()):
            return lab_comum.executar_com_tratamento(lambda _: lab_comum.CODIGO_OK, argumentos)

    def test_erro_bruto_do_sdk_so_aparece_com_detalhes(self):
        self.executar(detalhes=False)
        self.assertEqual(self.registro.level, logging.CRITICAL)
        self.registro.setLevel(logging.NOTSET)
        self.executar(detalhes=True)
        self.assertEqual(self.registro.level, logging.NOTSET)


class _Terminal(io.TextIOWrapper):
    def isatty(self):
        return True


class SaidaRedirecionadaTests(unittest.TestCase):
    def gravar(self, fluxo, pythonioencoding=None):
        """Configura a saída como os scripts fazem e devolve os bytes gravados para 'Título'."""
        ambiente = {chave: valor for chave, valor in os.environ.items() if chave != "PYTHONIOENCODING"}
        if pythonioencoding:
            ambiente["PYTHONIOENCODING"] = pythonioencoding
        with mock.patch.dict(os.environ, ambiente, clear=True), \
                mock.patch.object(sys, "stdout", fluxo), mock.patch.object(sys, "stderr", io.StringIO()):
            lab_comum.configurar_saida()
            fluxo.write("Título")
            fluxo.flush()
        return fluxo.buffer.getvalue()

    def test_saida_redirecionada_sai_em_utf8(self):
        fluxo = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
        self.assertEqual(self.gravar(fluxo), "Título".encode("utf-8"))

    def test_codificacao_escolhida_pelo_usuario_e_respeitada_sem_travar(self):
        fluxo = io.TextIOWrapper(io.BytesIO(), encoding="ascii")
        self.assertEqual(self.gravar(fluxo, "ascii"), b"T?tulo")

    def test_terminal_real_nao_e_alterado(self):
        fluxo = _Terminal(io.BytesIO(), encoding="cp1252")
        self.assertEqual(self.gravar(fluxo), "Título".encode("cp1252"))


if __name__ == "__main__":
    unittest.main()
