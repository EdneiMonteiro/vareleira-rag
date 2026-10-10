import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import support  # noqa: F401  (configura o caminho dos scripts)
import buscar_trechos
import indexar_documentos
import lab_comum
import lab_indexacao as li
import verificar_indice
import visualizar_trechos
from azure.core.exceptions import ClientAuthenticationError, HttpResponseError, ServiceRequestError
from azure.identity import CredentialUnavailableError
from support import IndiceFalso, OpenAIFalso, container_com_documentos, copiar_pacote, rodar_script

CONTA, BUSCA, MODELOS = "stvlrag1234567890", "srch-vlr-exemplo", "ais-vlr-exemplo"
DIMENSOES = 8


class BaseComIndice(unittest.TestCase):
    """Índice falso já preenchido pelo próprio script de indexação, como depois do passo anterior."""

    def setUp(self):
        self.pasta, self.inventario = copiar_pacote()
        self.addCleanup(self.pasta.cleanup)
        self.indice = IndiceFalso()
        self.openai = OpenAIFalso(dimensoes=DIMENSOES)
        container = container_com_documentos(self.inventario)
        codigo, saida = rodar_script(
            indexar_documentos,
            ["--conta", CONTA, "--busca", BUSCA, "--modelos", MODELOS, "--dimensoes", str(DIMENSOES),
             "--inventario", str(self.inventario), "--executar"],
            container=container, abrir_indice=lambda *a, **k: self.indice, openai=self.openai)
        self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)
        self.documentos = lab_comum.carregar_inventario(self.inventario).documentos
        self.trechos = [t for d in self.documentos for t in li.dividir_documento(d, lab_comum.ler_conteudo(d).decode("utf-8"))]
        self.operacoes = list(self.indice.operacoes)
        self.chamadas = len(self.openai.chamadas)

    def arquivo_de_perguntas(self, perguntas):
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        caminho = Path(pasta.name) / "perguntas.json"
        caminho.write_text(json.dumps({"schema_version": 1, "sintetico": True, "perguntas": perguntas}), encoding="utf-8")
        return caminho

    def pergunta_que_acha_o_trecho(self, identificador, trecho):
        """A pergunta é o próprio texto do trecho: o vetor falso é idêntico e o trecho vem em primeiro lugar."""
        return {"id": identificador, "pergunta": trecho.texto_para_embedding,
                "esperado": [{"documento_id": trecho.documento.id, "texto_contem": trecho.conteudo[:30]}]}


class VerificacaoDoIndiceTests(BaseComIndice):
    def verificar(self, *opcoes, perguntas=None, status_sem_credencial=401):
        perguntas = perguntas or [self.pergunta_que_acha_o_trecho("R1", self.trechos[3]),
                                  self.pergunta_que_acha_o_trecho("R2", self.trechos[20])]
        argumentos = ["--busca", BUSCA, "--modelos", MODELOS, "--dimensoes", str(DIMENSOES), "--inventario",
                      str(self.inventario), "--perguntas", str(self.arquivo_de_perguntas(perguntas)), *opcoes]
        with mock.patch.object(verificar_indice, "ESPERA_PADRAO_SEGUNDOS", 0), \
                mock.patch.object(li, "_status_anonimo", return_value=status_sem_credencial):
            return rodar_script(verificar_indice, argumentos, abrir_indice=lambda *a, **k: self.indice,
                                openai=self.openai)

    def test_indice_correto_e_aprovado_sem_alterar_nada(self):
        codigo, saida = self.verificar()
        self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)
        self.assertIn("Verificação aprovada", saida)
        self.assertNotIn("FALHA", saida)
        for trecho_da_saida in ("Definição do índice", "Trechos do índice", "Modelo dos vetores", "Busca vetorial",
                                "Acesso sem credenciais negado", "R1: esperado na posição 1"):
            self.assertIn(trecho_da_saida, saida)
        self.assertEqual(self.indice.operacoes, self.operacoes, "o verificador só lê")
        self.assertEqual(len(self.openai.chamadas), self.chamadas + 1, "uma chamada só, para todas as perguntas")

    def test_indice_inexistente_reprova_e_nem_chama_o_modelo(self):
        self.indice.definicao = None
        codigo, saida = self.verificar()
        self.assertEqual(codigo, lab_comum.CODIGO_DIVERGENCIA)
        self.assertIn("não existe", saida)
        self.assertEqual(len(self.openai.chamadas), self.chamadas)

    def test_trecho_faltando_sobrando_ou_alterado_reprova_e_aponta_os_ids(self):
        faltando = self.trechos[0].id
        del self.indice.documentos[faltando]
        alterado = self.trechos[1].id
        self.indice.documentos[alterado]["impressao"] = "outra"
        self.indice.documentos["VLAR-CG-1_0-099"] = {**self.indice.documentos[self.trechos[2].id], "id": "VLAR-CG-1_0-099"}
        codigo, saida = self.verificar()
        self.assertEqual(codigo, lab_comum.CODIGO_DIVERGENCIA, saida)
        self.assertIn(f"faltam 1 ({faltando})", saida)
        self.assertIn(f"1 com conteúdo diferente ({alterado})", saida)
        self.assertIn("1 sobrando (VLAR-CG-1_0-099)", saida)

    def test_espera_o_indice_refletir_as_gravacoes_antes_de_reprovar(self):
        completo = self.indice.trechos_gravados()
        respostas = iter([{}, dict(list(completo.items())[:5]), completo])
        with mock.patch.object(self.indice, "trechos_gravados", side_effect=lambda: next(respostas, completo)), \
                mock.patch.object(verificar_indice, "ESPERA_PADRAO_SEGUNDOS", 60), \
                mock.patch.object(verificar_indice.time, "sleep") as dormir:
            resultado, _ = verificar_indice.verificar_trechos(
                self.indice, self.trechos, li.EspecificacaoEmbedding("embeddings", DIMENSOES))
        self.assertTrue(resultado.ok, resultado.detalhe)
        self.assertEqual(dormir.call_count, 2)

    def test_vetores_de_outro_modelo_reprovam_e_orientam_a_recriar_o_indice(self):
        for registro in self.indice.documentos.values():
            registro["modelo_embeddings"] = "text-embedding-ada-002"
        codigo, saida = self.verificar()
        self.assertEqual(codigo, lab_comum.CODIGO_DIVERGENCIA)
        self.assertIn("text-embedding-ada-002", saida)
        self.assertIn("--recriar-indice", saida)

    def test_pergunta_sem_o_trecho_esperado_entre_os_primeiros_reprova(self):
        ruim = {"id": "R9", "pergunta": "qualquer coisa", "esperado": [{"documento_id": "VLAR-CG-1.0", "texto_contem": "texto que não existe"}]}
        codigo, saida = self.verificar(perguntas=[self.pergunta_que_acha_o_trecho("R1", self.trechos[3]), ruim])
        self.assertEqual(codigo, lab_comum.CODIGO_DIVERGENCIA)
        self.assertIn("em 1 de 2 perguntas", saida)
        self.assertIn("R9: esperado ausente dos 3 primeiros", saida)

    def test_k_define_quantos_resultados_sao_examinados(self):
        pergunta = self.pergunta_que_acha_o_trecho("R1", self.trechos[3])
        ranking = self.indice.consultar(None, support.vetor_falso(pergunta["pergunta"], DIMENSOES), 10)
        quinto = ranking[4]
        pergunta["esperado"] = [{"documento_id": quinto["documento_id"], "texto_contem": quinto["conteudo"][:30]}]
        codigo_curto, saida = self.verificar("--k", "4", perguntas=[pergunta])
        codigo_longo, _ = self.verificar("--k", "5", perguntas=[pergunta])
        self.assertEqual(codigo_curto, lab_comum.CODIGO_DIVERGENCIA)
        self.assertIn("ausente dos 4 primeiros", saida)
        self.assertEqual(codigo_longo, lab_comum.CODIGO_OK)

    def test_acesso_sem_credencial_permitido_reprova(self):
        codigo, saida = self.verificar(status_sem_credencial=200)
        self.assertEqual(codigo, lab_comum.CODIGO_DIVERGENCIA)
        self.assertIn("ACESSO SEM CREDENCIAL PERMITIDO", saida)

    def test_resultados_ja_prontos_aparecem_mesmo_se_uma_etapa_seguinte_falha(self):
        erro = HttpResponseError("sem permissão nos modelos")
        erro.status_code = 403
        self.openai.erro = erro
        codigo, saida = self.verificar()
        self.assertEqual(codigo, lab_comum.CODIGO_ACESSO)
        self.assertIn("[OK   ] Definição do índice", saida)
        self.assertIn("[OK   ] Trechos do índice", saida)
        self.assertNotIn("Verificação aprovada", saida)

    def test_acesso_sem_credenciais_conclusivo_so_com_401_ou_403(self):
        for status in (401, 403):
            with self.subTest(status=status):
                resultado = li.verificar_acesso_sem_credenciais(BUSCA, "indice", MODELOS, consultar=lambda url, s=status: s)
                self.assertTrue(resultado.ok, resultado.detalhe)
        for status in (200, 204):
            resultado = li.verificar_acesso_sem_credenciais(BUSCA, "indice", MODELOS, consultar=lambda url, s=status: s)
            self.assertFalse(resultado.ok)
            self.assertIn("PERMITIDO", resultado.detalhe)

    def test_resposta_inesperada_ou_falha_de_rede_nao_conta_como_negado(self):
        def sem_rede(url):
            raise TimeoutError("sem resposta")

        for consultar in (sem_rede, lambda url: 404, lambda url: 500):
            with self.subTest(consultar=getattr(consultar, "__name__", "http")):
                resultado = li.verificar_acesso_sem_credenciais(BUSCA, "indice", MODELOS, consultar=consultar)
                self.assertFalse(resultado.ok)
                self.assertIn("não foi possível confirmar", resultado.detalhe)

    def test_sonda_sem_credenciais_so_fala_com_os_enderecos_do_laboratorio(self):
        pedidos = []
        li.verificar_acesso_sem_credenciais(BUSCA, "meu-indice", MODELOS, consultar=lambda url: pedidos.append(url) or 401)
        self.assertEqual(len(pedidos), 2)
        self.assertTrue(pedidos[0].startswith(f"https://{BUSCA}.search.windows.net/indexes('meu-indice')/docs/$count?api-version="))
        self.assertEqual(pedidos[1], f"https://{MODELOS}.openai.azure.com/openai/v1/models")


class BuscaDeTrechosTests(BaseComIndice):
    def buscar(self, *opcoes, pergunta=None):
        argumentos = ["--busca", BUSCA, "--modelos", MODELOS, "--dimensoes", str(DIMENSOES),
                      "--pergunta", self.trechos[3].texto_para_embedding if pergunta is None else pergunta, *opcoes]
        return rodar_script(buscar_trechos, argumentos, abrir_indice=lambda *a, **k: self.indice, openai=self.openai)

    def test_busca_vetorial_calcula_o_embedding_e_mostra_fonte_e_pontuacao_sem_gerar_resposta(self):
        codigo, saida = self.buscar()
        self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)
        self.assertEqual(len(self.openai.chamadas), self.chamadas + 1)
        self.assertIn("1. [pontuação 1.000]", saida)
        self.assertIn(f"trecho {self.trechos[3].id}", saida)
        self.assertIn(f"fonte: {self.trechos[3].documento.blob}", saida)
        self.assertIn("nenhuma resposta é gerada", saida)
        self.assertEqual(saida.count("fonte:"), 3)
        self.assertEqual(self.indice.operacoes, self.operacoes)

    def test_cada_modo_envia_ao_indice_o_que_deve(self):
        pedidos = []
        original = self.indice.consultar
        self.indice.consultar = lambda texto, vetor, k: pedidos.append((texto, vetor is not None, k)) or original(texto, vetor, k)
        self.buscar("--modo", "vetorial", "--k", "2", pergunta="frase de teste")
        self.buscar("--modo", "texto", pergunta="frase de teste")
        self.buscar("--modo", "hibrida", "--k", "5", pergunta="frase de teste")
        self.assertEqual(pedidos, [(None, True, 2), ("frase de teste", False, 3), ("frase de teste", True, 5)])

    def test_busca_por_texto_nao_chama_o_servico_de_modelos(self):
        codigo, saida = self.buscar("--modo", "texto", pergunta="franquia")
        self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)
        self.assertEqual(len(self.openai.chamadas), self.chamadas)

    def test_pergunta_vazia_e_recusada_antes_de_acessar_o_azure(self):
        codigo, saida = self.buscar(pergunta="   ")
        self.assertEqual(codigo, lab_comum.CODIGO_USO)
        self.assertIn("pergunta", saida)
        self.assertEqual(len(self.openai.chamadas), self.chamadas)

    def test_indice_vazio_avisa_que_nada_foi_encontrado(self):
        self.indice.documentos.clear()
        codigo, saida = self.buscar(pergunta="qualquer")
        self.assertEqual(codigo, lab_comum.CODIGO_OK)
        self.assertIn("Nenhum trecho encontrado", saida)

    def test_resumo_do_trecho_fica_em_uma_linha_sem_marcacao_de_titulo(self):
        texto = "## Título\n\nPrimeiro   parágrafo.\n\n- item\n" + "palavra " * 100
        resumo = buscar_trechos.resumir(texto, 60)
        self.assertNotIn("\n", resumo)
        self.assertTrue(resumo.startswith("Título Primeiro parágrafo."))
        self.assertTrue(resumo.endswith("…"))
        self.assertLessEqual(len(resumo), 60)


class VisualizacaoDosTrechosTests(unittest.TestCase):
    def rodar(self, *opcoes):
        # Sem dublê algum: se o script tentasse usar o Azure, o teste falharia.
        return rodar_script(visualizar_trechos, list(opcoes))

    def test_mostra_os_trechos_de_todos_os_documentos_sem_azure(self):
        codigo, saida = self.rodar()
        self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)
        for documento_id in ("VLAR-CG-1.0", "VLAR-GL-1.0", "VLAR-FAQ-1.0"):
            self.assertIn(documento_id, saida)
        self.assertIn("Nenhum arquivo foi alterado e nada foi enviado ao Azure.", saida)
        self.assertIn("1.1, 1.2", saida)

    def test_tamanho_menor_gera_mais_trechos(self):
        def total(*opcoes):
            _, saida = self.rodar(*opcoes)
            return int(saida.split("Resumo: ")[1].split(" trecho")[0])

        self.assertGreater(total("--tamanho-maximo", "400"), total())

    def test_documento_filtrado_e_texto_completo(self):
        codigo, saida = self.rodar("--documento", "VLAR-GL-1.0", "--completo")
        self.assertEqual(codigo, lab_comum.CODIGO_OK)
        self.assertIn("VLAR-GL-1.0 — ", saida)
        self.assertNotIn("VLAR-CG-1.0 — ", saida)
        self.assertIn("         | ## Franquia", saida)
        self.assertNotIn(" \n", saida, "linhas em branco do texto não deixam espaços sobrando")

    def test_documento_desconhecido_lista_os_validos(self):
        codigo, saida = self.rodar("--documento", "NAO-EXISTE")
        self.assertEqual(codigo, lab_comum.CODIGO_USO)
        self.assertIn("VLAR-CG-1.0", saida)

    def test_estimativa_de_tokens_conta_o_texto_que_vai_ao_modelo_como_a_indexacao(self):
        inventario = lab_comum.carregar_inventario()
        esperado = li.estimar_tokens(sum(
            len(trecho.texto_para_embedding)
            for documento in inventario.documentos
            for trecho in li.dividir_documento(documento, lab_comum.ler_conteudo(documento).decode("utf-8"))))
        _, saida = self.rodar()
        self.assertIn(f"Estimativa grosseira: {esperado} tokens", saida)


def erro_da_openai(nome, status, mensagem="MENSAGEM-SENSIVEL-DO-SERVICO"):
    classe = type(nome, (Exception,), {"status_code": status, "__module__": "openai"})
    return classe(mensagem)


def erro_do_azure(classe, status, url, codigo=None):
    erro = classe("MENSAGEM-SENSIVEL-DO-SERVICO")
    erro.status_code, erro.error_code = status, codigo
    erro.response = SimpleNamespace(request=SimpleNamespace(url=url))
    return erro


class TraducaoDeErrosDaIndexacaoTests(unittest.TestCase):
    ARGS = SimpleNamespace(busca=BUSCA, modelos=MODELOS, indice="indice-x", deployment="emb-x",
                           conta=CONTA, container="base-documental")
    URL_BUSCA = f"https://{BUSCA}.search.windows.net/indexes('indice-x')?api-version=2026-04-01"
    URL_BLOB = f"https://{CONTA}.blob.core.windows.net/base-documental/a.md"

    def traduzir(self, erro):
        return li.traduzir_erro_indexacao(erro, self.ARGS)

    def test_erros_do_servico_de_modelos(self):
        casos = {
            ("AuthenticationError", 401): "HTTP 401",
            ("PermissionDeniedError", 403): "HTTP 403",
            ("NotFoundError", 404): "deployment 'emb-x' não foi encontrado",
            ("RateLimitError", 429): "limite de requisições",
            ("APIConnectionError", None): f"conectar ao recurso de modelos '{MODELOS}'",
            ("APITimeoutError", None): f"conectar ao recurso de modelos '{MODELOS}'",
            ("InternalServerError", 500): "HTTP 500",
        }
        for (nome, status), esperado in casos.items():
            with self.subTest(nome):
                mensagem, codigo = self.traduzir(erro_da_openai(nome, status))
                self.assertIn(esperado, mensagem)
                self.assertEqual(codigo, lab_comum.CODIGO_ACESSO)
                self.assertNotIn("MENSAGEM-SENSIVEL", mensagem)

    def test_404_de_subdominio_sem_recurso_orienta_sobre_o_recurso_e_a_intermitencia(self):
        erro = erro_da_openai("NotFoundError", 404, "Error code: 404 - Subdomain does not map to a resource.")
        mensagem, codigo = self.traduzir(erro)
        self.assertIn("intermitente", mensagem)
        self.assertIn(f"'{MODELOS}'", mensagem)
        self.assertNotIn("deployment 'emb-x'", mensagem)
        self.assertEqual(codigo, lab_comum.CODIGO_ACESSO)

    def test_recusa_dos_modelos_cita_o_papel_e_a_sessao_porque_o_servico_responde_401_ou_403(self):
        for nome, status in (("AuthenticationError", 401), ("PermissionDeniedError", 403)):
            with self.subTest(nome):
                mensagem, _ = self.traduzir(erro_da_openai(nome, status))
                self.assertIn("Cognitive Services OpenAI User", mensagem)
                self.assertIn("az login", mensagem)

    def test_erros_do_servico_de_busca(self):
        casos = {
            403: ("Search Service Contributor", "Search Index Data Contributor", lab_comum.CODIGO_ACESSO),
            401: ("recusou a credencial", "az login", lab_comum.CODIGO_ACESSO),
            404: ("índice 'indice-x' não foi encontrado", "indexar_documentos.py", lab_comum.CODIGO_ACESSO),
            409: ("mudou durante a execução", "simulação", lab_comum.CODIGO_DIVERGENCIA),
            429: ("limitando ou indisponível", "idempotente", lab_comum.CODIGO_ACESSO),
            400: ("HTTP 400", "--detalhes", lab_comum.CODIGO_ACESSO),
        }
        for status, (um, dois, esperado) in casos.items():
            with self.subTest(status=status):
                mensagem, codigo = self.traduzir(erro_do_azure(HttpResponseError, status, self.URL_BUSCA))
                self.assertIn(um, mensagem)
                self.assertIn(dois, mensagem)
                self.assertEqual(codigo, esperado)
                self.assertNotIn("MENSAGEM-SENSIVEL", mensagem)

    def test_falha_de_rede_para_o_search_cita_o_nome_do_servico(self):
        erro = ServiceRequestError(f"Cannot connect to host {BUSCA}.search.windows.net:443")
        mensagem, codigo = self.traduzir(erro)
        self.assertIn(f"serviço de busca '{BUSCA}'", mensagem)
        self.assertEqual(codigo, lab_comum.CODIGO_ACESSO)

    def test_erros_do_storage_continuam_com_a_orientacao_do_desafio_01(self):
        erro = erro_do_azure(HttpResponseError, 403, self.URL_BLOB, "AuthorizationPermissionMismatch")
        mensagem, _ = self.traduzir(erro)
        self.assertIn("Storage Blob Data Contributor", mensagem)

    def test_sem_login_orienta_az_login_mesmo_vindo_do_search_ou_dos_modelos(self):
        for classe in (CredentialUnavailableError, ClientAuthenticationError):
            with self.subTest(classe=classe.__name__):
                mensagem, codigo = self.traduzir(classe("x"))
                self.assertIn("az login", mensagem)
                self.assertEqual(codigo, lab_comum.CODIGO_ACESSO)

    def test_defeito_do_script_tem_codigo_proprio(self):
        _, codigo = self.traduzir(KeyError("campo"))
        self.assertEqual(codigo, lab_comum.CODIGO_INESPERADO)


if __name__ == "__main__":
    unittest.main()
