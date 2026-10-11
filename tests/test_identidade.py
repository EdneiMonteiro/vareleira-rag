import argparse
import contextlib
import datetime as dt
import io
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

import support  # noqa: F401  (configura o caminho dos scripts)
import guardar_segredo
import lab_comum
import lab_geracao
import lab_identidade as lid
import lab_indexacao
import perguntar
import verificar_identidade
from azure.core.exceptions import ResourceNotFoundError
from support import OpenAIGeracaoFalso, copiar_pacote, indexar_pacote

COFRE, BUSCA, MODELOS, CONTA = "kv-vlr-exemplo", "srch-vlr-exemplo", "ais-vlr-exemplo", "stvlrag1234567890"
TENANT = "contoso.example"
APLICACAO = "00000000-0000-0000-0000-000000000000"
SEGREDO = "valor-secreto-de-teste-123"
AGORA = dt.datetime(2026, 10, 9, 12, 0, tzinfo=dt.timezone.utc)
DIMENSOES = 8


def erro_azure(nome, status=None, url="", mensagem=None):
    """Erro com o nome, o módulo e o código HTTP de um erro do SDK do Azure, sem depender dele."""
    classe = type(nome, (Exception,), {"status_code": status, "__module__": "azure.core.exceptions"})
    erro = classe(mensagem or f"{nome} de teste")
    if url:
        erro.response = SimpleNamespace(request=SimpleNamespace(url=url))
    return erro


class SegredosFalso:
    """Imita só o que o laboratório usa do cliente de segredos. Nunca devolve o valor em texto de erro."""

    def __init__(self, valor=SEGREDO, enabled=True, expires_on=None, erro=None):
        self.valor, self.enabled, self.expires_on, self.erro = valor, enabled, expires_on, erro
        self.gravados = []

    def get_secret(self, nome, version=None):
        if self.erro:
            raise self.erro
        if self.valor is None:
            raise ResourceNotFoundError("segredo inexistente")
        return SimpleNamespace(value=self.valor, properties=SimpleNamespace(enabled=self.enabled, expires_on=self.expires_on))

    def set_secret(self, nome, valor, **opcoes):
        if self.erro:
            raise self.erro
        self.gravados.append((nome, valor, opcoes))
        return SimpleNamespace(properties=SimpleNamespace(version="versao-abc"))


class ValidadoresTests(unittest.TestCase):
    def test_nome_do_cofre_forma_o_endereco_e_so_aceita_o_formato_do_azure(self):
        for valido in ("kv-vlr-abc123", "cofre", "A1b"):
            self.assertEqual(lid.validar_cofre(valido), valido)
        for invalido in ("ab", "1cofre", "cofre--duplo", "cofre-", "meu.cofre/x", "a" * 25, ""):
            with self.subTest(invalido=invalido), self.assertRaises(argparse.ArgumentTypeError):
                lid.validar_cofre(invalido)

    def test_nome_do_segredo_e_id_da_aplicacao(self):
        self.assertEqual(lid.validar_nome_do_segredo("segredo-da-aplicacao"), "segredo-da-aplicacao")
        for invalido in ("com_sublinhado", "com espaco", "a/b", ""):
            with self.subTest(invalido=invalido), self.assertRaises(argparse.ArgumentTypeError):
                lid.validar_nome_do_segredo(invalido)
        self.assertEqual(lid.validar_id_da_aplicacao(APLICACAO), APLICACAO)
        with self.assertRaises(argparse.ArgumentTypeError):
            lid.validar_id_da_aplicacao("nao-e-um-guid")

    def test_validade_em_dias(self):
        self.assertEqual(lid.validar_validade("7"), 7)
        for invalido in ("0", "91", "x", "-1"):
            with self.subTest(invalido=invalido), self.assertRaises(argparse.ArgumentTypeError):
                lid.validar_validade(invalido)


class SegredoTests(unittest.TestCase):
    def test_le_o_valor_de_um_segredo_valido(self):
        self.assertEqual(lid.ler_segredo(COFRE, "s", cliente=SegredosFalso(), agora=lambda: AGORA), SEGREDO)

    def test_segredo_inexistente_orienta_com_o_nome_do_cofre(self):
        with self.assertRaises(lab_comum.ErroLab) as contexto:
            lid.ler_segredo(COFRE, "s", cliente=SegredosFalso(valor=None), agora=lambda: AGORA)
        self.assertIn(COFRE, str(contexto.exception))
        self.assertIn("guardar_segredo.py", str(contexto.exception))
        self.assertEqual(contexto.exception.codigo, lab_comum.CODIGO_ACESSO)

    def test_recusa_segredo_desativado_expirado_ou_vazio(self):
        ontem = AGORA - dt.timedelta(days=1)
        for cliente, trecho in ((SegredosFalso(enabled=False), "desativado"), (SegredosFalso(expires_on=ontem), "expirou em 2026-10-08"),
                                (SegredosFalso(valor=""), "vazio")):
            with self.subTest(trecho=trecho), self.assertRaises(lab_comum.ErroLab) as contexto:
                lid.ler_segredo(COFRE, "s", cliente=cliente, agora=lambda: AGORA)
            self.assertIn(trecho, str(contexto.exception))

    def test_guarda_com_validade_etiquetas_e_tipo_de_conteudo(self):
        cliente = SegredosFalso()
        versao, expira = lid.guardar_segredo(COFRE, "s", SEGREDO, validade_dias=3, cliente=cliente, agora=lambda: AGORA)
        nome, valor, opcoes = cliente.gravados[0]
        self.assertEqual((nome, valor, versao), ("s", SEGREDO, "versao-abc"))
        self.assertEqual(expira, AGORA + dt.timedelta(days=3))
        self.assertEqual(opcoes["expires_on"], expira)
        self.assertEqual(opcoes["content_type"], "text/plain")
        self.assertEqual(opcoes["tags"], lid.ETIQUETAS_DO_SEGREDO)

    def test_nao_guarda_valor_vazio_de_varias_linhas_ou_grande_demais(self):
        for valor in ("", "linha 1\nlinha 2", "a\rb", "x" * (lid.TAMANHO_MAXIMO_DO_SEGREDO + 1)):
            cliente = SegredosFalso()
            with self.subTest(tamanho=len(valor)), self.assertRaises(lab_comum.ErroLab) as contexto:
                lid.guardar_segredo(COFRE, "s", valor, cliente=cliente, agora=lambda: AGORA)
            self.assertEqual(cliente.gravados, [], "nada é gravado")
            if len(valor) > 20:
                self.assertNotIn(valor, str(contexto.exception), "a mensagem não repete o valor")


class CredencialTests(unittest.TestCase):
    def args(self, **mudancas):
        base = dict(identidade="aplicacao", cofre=COFRE, nome_do_segredo="s", id_da_aplicacao=APLICACAO, tenant_id=TENANT)
        return argparse.Namespace(**{**base, **mudancas})

    def test_operador_nao_cria_credencial_nem_le_o_cofre(self):
        ler = mock.Mock()
        self.assertIsNone(lid.resolver_credencial(self.args(identidade="operador"), ler=ler))
        self.assertIsNone(lid.resolver_credencial(argparse.Namespace(), ler=ler), "sem a opção, vale o operador")
        ler.assert_not_called()

    def test_aplicacao_sem_dados_lista_o_que_falta_antes_de_acessar_o_cofre(self):
        ler = mock.Mock()
        with self.assertRaises(lab_comum.ErroLab) as contexto:
            lid.resolver_credencial(self.args(cofre=None, tenant_id=None), ler=ler)
        self.assertIn("--cofre", str(contexto.exception))
        self.assertIn("--tenant-id", str(contexto.exception))
        self.assertNotIn("--id-da-aplicacao", str(contexto.exception))
        ler.assert_not_called()

    def test_aplicacao_le_o_segredo_com_a_conta_do_operador_e_cria_a_credencial(self):
        ler = mock.Mock(return_value=SEGREDO)
        criar = mock.Mock(return_value="credencial")
        self.assertEqual(lid.resolver_credencial(self.args(), ler=ler, criar=criar), "credencial")
        ler.assert_called_once_with(COFRE, "s", TENANT)
        criar.assert_called_once_with(TENANT, APLICACAO, SEGREDO)

    def test_descricao_da_identidade_nao_traz_o_id_da_aplicacao(self):
        self.assertEqual(lid.descrever_identidade(self.args(identidade="operador")), "operador (sessão do Azure CLI)")
        descricao = lid.descrever_identidade(self.args())
        self.assertIn(COFRE, descricao)
        self.assertNotIn(APLICACAO, descricao)

    def test_credencial_da_aplicacao_usa_tenant_id_da_aplicacao_e_segredo(self):
        credencial = lid.criar_credencial_da_aplicacao(TENANT, APLICACAO, SEGREDO)
        self.assertEqual(type(credencial).__name__, "ClientSecretCredential")


class TraducaoDeErrosTests(unittest.TestCase):
    ARGS = argparse.Namespace(cofre=COFRE, busca=BUSCA, indice="indice", modelos=MODELOS, deployment="d")

    def test_codigos_do_entra_viram_orientacao(self):
        casos = {"7000215": "segredo inválido", "7000222": "expirou", "700016": "não encontrou a aplicação", "90002": "tenant",
                 "50126": "AADSTS50126"}
        for codigo, trecho in casos.items():
            with self.subTest(codigo=codigo):
                mensagem = lid.mensagem_do_entra(RuntimeError(f"AADSTS{codigo}: erro. Detalhe do tenant"))
                self.assertIn(trecho, mensagem)
        self.assertIsNone(lid.mensagem_do_entra(RuntimeError("sem código")))

    def test_recusa_do_entra_nao_repete_o_texto_bruto_do_erro(self):
        erro = erro_azure("ClientAuthenticationError", mensagem=f"AADSTS7000215: Invalid client secret {SEGREDO}")
        mensagem, codigo = lid.traduzir_erro_identidade(erro, self.ARGS)
        self.assertEqual(codigo, lab_comum.CODIGO_ACESSO)
        self.assertNotIn(SEGREDO, mensagem)

    def test_erros_do_cofre_por_status(self):
        url = f"https://{COFRE}.vault.azure.net/secrets/s"
        casos = {403: "Key Vault Secrets User", 401: "az login", 404: "não foi encontrado", 429: "limitando"}
        for status, trecho in casos.items():
            with self.subTest(status=status):
                mensagem, codigo = lid.traduzir_erro_identidade(erro_azure("HttpResponseError", status, url), self.ARGS)
                self.assertIn(trecho, mensagem)
                self.assertIn(COFRE, mensagem)
                self.assertEqual(codigo, lab_comum.CODIGO_ACESSO)

    def test_falha_de_conexao_com_o_cofre_lembra_do_nome_reservado(self):
        erro = erro_azure("ServiceRequestError", None, f"https://{COFRE}.vault.azure.net/secrets/s")
        mensagem, _ = lid.traduzir_erro_identidade(erro, self.ARGS)
        self.assertIn("reservando o nome", mensagem)

    def test_demais_erros_seguem_para_o_tradutor_dos_desafios_anteriores(self):
        erro = erro_azure("HttpResponseError", 403, f"https://{BUSCA}.search.windows.net/indexes('i')")
        mensagem, _ = lid.traduzir_erro_identidade(erro, self.ARGS)
        self.assertIn("Search Index Data Reader", mensagem)


class GuardarSegredoTests(unittest.TestCase):
    def rodar(self, *opcoes, entrada=SEGREDO + "\r\n", cliente=None, ambiente=None):
        cliente = cliente or SegredosFalso()
        saida = io.StringIO()
        original = lid.guardar_segredo
        with contextlib.ExitStack() as pilha:
            pilha.enter_context(mock.patch.object(lid, "criar_cliente_de_segredos", return_value=cliente))
            # O valor padrão `agora=_agora` é fixado ao definir a função: trocar `lid._agora` não congela o relógio.
            # Por isso ele é injetado na chamada.
            pilha.enter_context(mock.patch.object(
                lid, "guardar_segredo", side_effect=lambda *a, **k: original(*a, agora=lambda: AGORA, **k)))
            pilha.enter_context(mock.patch.object(sys, "stdin", io.StringIO(entrada)))
            if ambiente is not None:
                pilha.enter_context(mock.patch.dict("os.environ", ambiente, clear=False))
            pilha.enter_context(contextlib.redirect_stdout(saida))
            pilha.enter_context(contextlib.redirect_stderr(saida))
            codigo = guardar_segredo.principal(["--cofre", COFRE, *opcoes])
        return codigo, saida.getvalue(), cliente

    def test_grava_a_entrada_padrao_sem_mostrar_o_valor(self):
        codigo, saida, cliente = self.rodar("--validade-dias", "5")
        self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)
        self.assertEqual(cliente.gravados[0][:2], (lid.SEGREDO_PADRAO, SEGREDO), "sem o fim de linha do PowerShell")
        self.assertIn("válido até 2026-10-14", saida)
        self.assertNotIn(SEGREDO, saida)

    def test_grava_a_variavel_de_ambiente_sem_mostrar_o_valor(self):
        codigo, saida, cliente = self.rodar("--origem", "variavel", ambiente={guardar_segredo.VARIAVEL_PADRAO: SEGREDO})
        self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)
        self.assertEqual(cliente.gravados[0][1], SEGREDO)
        self.assertNotIn(SEGREDO, saida)

    def test_variavel_ausente_ou_vazia_e_recusada(self):
        codigo, saida, cliente = self.rodar("--origem", "variavel", "--variavel", "VARELEIRA_AUSENTE_DE_TESTE")
        self.assertEqual(codigo, lab_comum.CODIGO_USO)
        self.assertIn("VARELEIRA_AUSENTE_DE_TESTE", saida)
        self.assertEqual(cliente.gravados, [])

    def test_entrada_vazia_nao_grava(self):
        codigo, saida, cliente = self.rodar(entrada="\r\n")
        self.assertEqual(codigo, lab_comum.CODIGO_USO)
        self.assertEqual(cliente.gravados, [])

    def test_terminal_interativo_e_recusado_para_nao_expor_o_valor(self):
        class Terminal(io.StringIO):
            def isatty(self):
                return True
        with self.assertRaises(lab_comum.ErroLab) as contexto:
            guardar_segredo.ler_valor(argparse.Namespace(origem="entrada", variavel="V"), entrada=Terminal(SEGREDO))
        self.assertIn("entrada padrão", str(contexto.exception))

    def test_erro_do_cofre_vira_orientacao_sem_o_valor(self):
        erro = erro_azure("HttpResponseError", 403, f"https://{COFRE}.vault.azure.net/secrets/s", mensagem=SEGREDO)
        codigo, saida, _ = self.rodar(cliente=SegredosFalso(erro=erro))
        self.assertEqual(codigo, lab_comum.CODIGO_ACESSO)
        self.assertIn("Key Vault Secrets Officer", saida)
        self.assertNotIn(SEGREDO, saida)

    def test_cofre_invalido_para_antes_de_qualquer_acesso(self):
        with mock.patch.object(lid, "criar_cliente_de_segredos") as criar, contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as contexto:
                guardar_segredo.principal(["--cofre", "meu.cofre/x"])
        self.assertEqual(contexto.exception.code, lab_comum.CODIGO_USO)
        criar.assert_not_called()


class VerificarIdentidadeTests(unittest.TestCase):
    def test_classificar_distingue_negado_permitido_e_inconclusivo(self):
        def levanta(erro):
            def operacao():
                raise erro
            return operacao
        self.assertEqual(verificar_identidade.classificar(lambda: None)[0], verificar_identidade.PERMITIDO)
        self.assertEqual(verificar_identidade.classificar(levanta(erro_azure("HttpResponseError", 403)))[0], verificar_identidade.NEGADO)
        self.assertEqual(verificar_identidade.classificar(levanta(erro_azure("ResourceNotFoundError", 404)), True)[0],
                         verificar_identidade.PERMITIDO)
        self.assertEqual(verificar_identidade.classificar(levanta(erro_azure("ResourceNotFoundError", 404)))[0],
                         verificar_identidade.INCONCLUSIVO)
        self.assertEqual(verificar_identidade.classificar(levanta(erro_azure("ClientAuthenticationError", 401)))[0],
                         verificar_identidade.INCONCLUSIVO)

    def test_conferir_explica_privilegio_demais_e_de_menos(self):
        demais = verificar_identidade.conferir(verificar_identidade.Tentativa("ler", verificar_identidade.NEGADO, lambda: None))
        self.assertFalse(demais.ok)
        self.assertIn("PRIVILÉGIO DEMAIS", demais.detalhe)

        def recusa():
            raise erro_azure("HttpResponseError", 403)
        de_menos = verificar_identidade.conferir(verificar_identidade.Tentativa("ler", verificar_identidade.PERMITIDO, recusa))
        self.assertFalse(de_menos.ok)
        self.assertIn("PRIVILÉGIO DE MENOS", de_menos.detalhe)

    def rodar(self, *, leitura=None, embeddings=None, apagar=None, segredo=None, blobs=None, operador=False):
        """Executa o script com dublês. Cada parâmetro é uma exceção a levantar (ou None para a operação ser aceita)."""
        credencial = object()
        capturadas = []

        def levanta(erro, retorno=None):
            def operacao(*a, **k):
                if erro:
                    raise erro
                return retorno
            return operacao

        indice = SimpleNamespace(contar=levanta(leitura, 54))
        inexistente = SimpleNamespace(apagar=levanta(apagar))

        def abrir(busca, nome, tenant=None, credencial_usada=None):
            capturadas.append(credencial_usada)
            return inexistente if nome == verificar_identidade.INDICE_INEXISTENTE else indice

        def criar_embeddings(modelos, deployment, dimensoes, tenant=None, credencial_usada=None):
            capturadas.append(credencial_usada)
            return SimpleNamespace(gerar=levanta(embeddings))

        def criar_cofre(cofre, tenant=None, credencial_usada=None):
            capturadas.append(credencial_usada)
            return SimpleNamespace(get_secret=levanta(segredo, SimpleNamespace(value=SEGREDO)))

        def criar_container(conta, container, tenant=None, credencial_usada=None):
            capturadas.append(credencial_usada)
            return SimpleNamespace(list_blobs=levanta(blobs, iter(())))

        saida = io.StringIO()
        with contextlib.ExitStack() as pilha:
            if not operador:
                pilha.enter_context(mock.patch.object(lid, "resolver_credencial", return_value=credencial))
            pilha.enter_context(mock.patch.object(lab_indexacao, "abrir_indice", side_effect=abrir))
            pilha.enter_context(mock.patch.object(lab_indexacao, "criar_cliente_embeddings", side_effect=criar_embeddings))
            pilha.enter_context(mock.patch.object(lid, "criar_cliente_de_segredos", side_effect=criar_cofre))
            pilha.enter_context(mock.patch.object(lab_comum, "criar_container", side_effect=criar_container))
            pilha.enter_context(contextlib.redirect_stdout(saida))
            pilha.enter_context(contextlib.redirect_stderr(saida))
            identidade = ["--identidade", "operador"] if operador else ["--id-da-aplicacao", APLICACAO, "--tenant-id", TENANT]
            codigo = verificar_identidade.principal([
                "--busca", BUSCA, "--modelos", MODELOS, "--conta", CONTA, "--cofre", COFRE, *identidade])
        return codigo, saida.getvalue(), credencial, capturadas

    def test_privilegio_minimo_confirmado_quando_so_leitura_e_modelos_sao_permitidos(self):
        negado = erro_azure("HttpResponseError", 403)
        codigo, saida, credencial, capturadas = self.rodar(apagar=negado, segredo=negado, blobs=negado)
        self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)
        self.assertEqual(saida.count("[OK   ]"), 5)
        self.assertIn("Privilégio mínimo confirmado", saida)
        self.assertIn(f"cofre '{COFRE}'", saida)
        self.assertNotIn(APLICACAO, saida)
        self.assertNotIn(SEGREDO, saida)

    def test_leitura_do_segredo_permitida_e_privilegio_demais_sem_mostrar_o_valor(self):
        negado = erro_azure("HttpResponseError", 403)
        codigo, saida, _, _ = self.rodar(apagar=negado, blobs=negado)
        self.assertEqual(codigo, lab_comum.CODIGO_DIVERGENCIA)
        self.assertIn("PRIVILÉGIO DEMAIS", saida)
        self.assertEqual(saida.count("[FALHA]"), 1)
        self.assertNotIn(SEGREDO, saida)

    def test_apagar_indice_inexistente_com_404_prova_permissao_de_escrita(self):
        negado = erro_azure("HttpResponseError", 403)
        codigo, saida, _, _ = self.rodar(apagar=erro_azure("ResourceNotFoundError", 404), segredo=negado, blobs=negado)
        self.assertEqual(codigo, lab_comum.CODIGO_DIVERGENCIA)
        self.assertIn("PRIVILÉGIO DEMAIS", saida)

    def test_leitura_negada_e_privilegio_de_menos(self):
        negado = erro_azure("HttpResponseError", 403)
        codigo, saida, _, _ = self.rodar(leitura=negado, apagar=negado, segredo=negado, blobs=negado)
        self.assertEqual(codigo, lab_comum.CODIGO_DIVERGENCIA)
        self.assertIn("PRIVILÉGIO DE MENOS", saida)

    def test_com_a_conta_do_operador_as_falhas_por_privilegio_demais_sao_o_contraste_esperado(self):
        codigo, saida, _, capturadas = self.rodar(operador=True)
        self.assertEqual(codigo, lab_comum.CODIGO_DIVERGENCIA, saida)
        self.assertEqual(saida.count("PRIVILÉGIO DEMAIS"), 3)
        self.assertEqual(saida.count("[OK   ]"), 2)
        self.assertIn("identidade: operador (sessão do Azure CLI)", saida)
        self.assertIn("contraste esperado", saida)
        self.assertEqual(capturadas, [None] * 5, "nenhuma credencial própria: os clientes usam o Azure CLI")
        self.assertNotIn(SEGREDO, saida)

    def test_tudo_e_feito_com_a_credencial_da_aplicacao(self):
        negado = erro_azure("HttpResponseError", 403)
        codigo, saida, credencial, capturadas = self.rodar(apagar=negado, segredo=negado, blobs=negado)
        self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)
        self.assertEqual(len(capturadas), 5, "dois índices, embeddings, cofre e contêiner")
        self.assertTrue(all(c is credencial for c in capturadas), "nenhum cliente usa a sessão do operador")


class PerguntarComIdentidadeTests(unittest.TestCase):
    def setUp(self):
        self.pasta, self.inventario = copiar_pacote()
        self.addCleanup(self.pasta.cleanup)
        self.indice, self.embeddings = indexar_pacote(self.inventario, BUSCA, MODELOS, DIMENSOES)
        self.geracao = OpenAIGeracaoFalso()

    def perguntar(self, *opcoes, credencial=None):
        abrir = mock.Mock(return_value=self.indice)
        criar_embeddings = mock.Mock(side_effect=lambda m, d, dim, t=None, c=None: lab_indexacao.ClienteEmbeddings(self.embeddings, d, dim))
        criar_geracao = mock.Mock(side_effect=lambda m, d, e=lab_geracao.ESFORCO_PADRAO, t=None, c=None:
                                  lab_geracao.ClienteGeracao(self.geracao, d, m, e))
        saida = io.StringIO()
        with contextlib.ExitStack() as pilha:
            pilha.enter_context(mock.patch.object(lid, "resolver_credencial", return_value=credencial))
            pilha.enter_context(mock.patch.object(lab_indexacao, "abrir_indice", abrir))
            pilha.enter_context(mock.patch.object(lab_indexacao, "criar_cliente_embeddings", criar_embeddings))
            pilha.enter_context(mock.patch.object(lab_geracao, "criar_cliente_geracao", criar_geracao))
            pilha.enter_context(contextlib.redirect_stdout(saida))
            pilha.enter_context(contextlib.redirect_stderr(saida))
            codigo = perguntar.principal(["--busca", BUSCA, "--modelos", MODELOS, "--dimensoes", str(DIMENSOES),
                                          "--pergunta", "franquia", "--modo", "hibrida", *opcoes])
        return codigo, saida.getvalue(), abrir, criar_embeddings, criar_geracao

    def test_a_identidade_da_aplicacao_chega_ao_indice_aos_embeddings_e_a_geracao(self):
        credencial = object()
        codigo, saida, abrir, embeddings, geracao = self.perguntar(
            "--identidade", "aplicacao", "--cofre", COFRE, "--id-da-aplicacao", APLICACAO, "--tenant-id", TENANT,
            credencial=credencial)
        self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)
        self.assertIn(f"Identidade: aplicação (service principal), com o segredo lido do cofre '{COFRE}'", saida)
        self.assertIs(abrir.call_args.args[3], credencial)
        self.assertIs(embeddings.call_args.args[4], credencial)
        self.assertIs(geracao.call_args.args[4], credencial)

    def test_sem_a_opcao_nada_muda_e_nenhuma_credencial_e_passada(self):
        codigo, saida, abrir, embeddings, geracao = self.perguntar()
        self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)
        self.assertNotIn("Identidade:", saida)
        self.assertIsNone(abrir.call_args.args[3])
        self.assertIsNone(geracao.call_args.args[4])

    def test_aplicacao_sem_cofre_para_antes_de_acessar_o_azure(self):
        with mock.patch.object(lab_indexacao, "abrir_indice") as abrir, contextlib.redirect_stdout(io.StringIO()) as saida, \
                contextlib.redirect_stderr(saida):
            codigo = perguntar.principal(["--busca", BUSCA, "--modelos", MODELOS, "--pergunta", "franquia",
                                          "--identidade", "aplicacao"])
        self.assertEqual(codigo, lab_comum.CODIGO_USO)
        self.assertIn("--cofre", saida.getvalue())
        abrir.assert_not_called()


if __name__ == "__main__":
    unittest.main()
