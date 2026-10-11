"""Testes do helper das provas HTTP externas do chat (scripts/sonda_http_externa_l300.py): sem rede e sem Azure.

O transporte HTTP e a credencial do Entra ID são dublês. O segredo, o tenant e os IDs são sorteados a cada execução: o que importa é
que nenhum deles, nem o texto do modelo, apareça na linha de resultado, no stdout ou no stderr, e que o segredo nunca seja argumento.
"""

import base64
import io
import json
import os
import re
import secrets
import subprocess
import sys
import unittest
import uuid
from types import SimpleNamespace
from unittest import mock

import support  # noqa: F401  (configura o caminho dos scripts)
import sonda_http_externa_l300 as externo
import sonda_l300 as sonda
from azure.core.exceptions import ClientAuthenticationError
from support import RAIZ
from test_sonda_l300 import (APP_ID, CLIENT_ID, EVIDENCIA_COMPARTILHADA, EVIDENCIA_DO_ROTEIRO, MARCADOR, URL, BaseSonda,
                             CredencialFalsa, jwt, resposta_do_chat, segmento)

TENANT, SEGREDO = str(uuid.uuid4()), "Q~" + secrets.token_urlsafe(30)
AMBIENTE_EXTERNO = {"VARELEIRA_HTTP_URL": URL, "VARELEIRA_HTTP_TENANT_ID": TENANT, "VARELEIRA_HTTP_CLIENT_ID": CLIENT_ID,
                    "VARELEIRA_HTTP_CLIENT_SECRET": SEGREDO, "VARELEIRA_HTTP_LOGIN_APP_ID": APP_ID}


class ContratoDoHelperTests(unittest.TestCase):
    def test_usa_a_sonda_publica_e_documenta_as_variaveis_sem_depender_de_pasta_privada(self):
        self.assertIs(externo.sonda, sonda)
        codigo = (RAIZ / "scripts" / "sonda_http_externa_l300.py").read_text(encoding="utf-8")
        self.assertNotIn("contexto", codigo.replace("contexto de build", ""))
        self.assertNotIn("probe_l300", codigo)
        self.assertNotIn("sys.path", codigo, "o helper importa a sonda como qualquer módulo de scripts/")
        for variavel in {variavel for _, variavel, _, _ in externo._VARIAVEIS}:
            self.assertTrue(variavel.startswith("VARELEIRA_HTTP_"), variavel)
            self.assertIn(variavel, externo.__doc__)
        self.assertEqual(externo.ETAPAS, ("sem-credenciais", "perfil"))
        self.assertIn("L300_SONDA_RESULTADO=", externo.__doc__)
        self.assertEqual({achado.lower() for achado in re.findall(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", codigo, re.I)}, set())


    def test_o_ponto_de_entrada_roda_como_programa_e_recusa_a_etapa_sem_configuracao(self):
        ambiente = {nome: valor for nome, valor in os.environ.items() if not nome.startswith(("VARELEIRA_", "PYTHONPATH"))}
        ambiente["PYTHONDONTWRITEBYTECODE"] = "1"
        resultado = subprocess.run([sys.executable, str(RAIZ / "scripts" / "sonda_http_externa_l300.py"), "--etapa", "perfil"],
                                   capture_output=True, text=True, timeout=120, env=ambiente, cwd=RAIZ)
        self.assertEqual((resultado.returncode, resultado.stderr), (1, ""))
        linhas = resultado.stdout.splitlines()
        self.assertEqual(len(linhas), 1)
        corpo = json.loads(linhas[0].removeprefix(sonda.SENTINELA))
        self.assertEqual((corpo["etapa"], corpo["causa"]), ("http-externo-perfil", "configuracao_ausente"))
        self.assertEqual(sorted(corpo["dados"]["ausentes"]), ["client_id", "login_app_id", "perfil", "segredo", "tenant", "url"])


class TestesDoHelperExterno(BaseSonda):
    """O helper do HOST (fora da imagem): HTTP externo sem credenciais e por perfil, com transporte e credencial dublados."""

    def externo(self, argv, ambiente):
        return self.rodar(argv, ambiente, principal=externo.principal, proibidos=(
            SEGREDO, TENANT, "Texto do modelo", MARCADOR, "roteiro-interno-atendimento", "alguem@exemplo", "ValidacaoSemAcesso"))

    def test_sem_credenciais_nega_anonimo_e_cabecalho_inventado_e_nao_precisa_de_segredo(self):
        enviados = []

        def http(respostas):
            def falso(metodo, url, cabecalhos, corpo):
                enviados.append((metodo, url.removeprefix(URL), dict(cabecalhos), corpo))
                return respostas.get(("principal" if "X-MS-CLIENT-PRINCIPAL" in cabecalhos else metodo, url.removeprefix(URL)), (401, b""))

            return falso

        sem_credencial = mock.patch.object(externo, "criar_credencial", side_effect=AssertionError("não usa credencial"))
        saudaveis = {("GET", "/healthz"): (200, b"ok"), ("GET", "/readyz"): (200, b"ok")}
        with sem_credencial, mock.patch.object(sonda, "transporte_http", http(saudaveis)):
            codigo, r = self.externo(["--etapa", "sem-credenciais"], {"VARELEIRA_HTTP_URL": URL, "VARELEIRA_HTTP_TENANT_ID": TENANT})
        self.assertEqual((codigo, r["etapa"], r["veredicto"], r["causa"]), (0, "http-externo-sem-credenciais", "aprovado", None))
        self.assertEqual(r["dados"]["estados"], {"healthz": 200, "readyz": 200, "anonimo": 401, "principal_forjado": 401})
        self.assertEqual([(m, u, "X-MS-CLIENT-PRINCIPAL" in c, "Authorization" in c) for m, u, c, _ in enviados],
                         [("GET", "/healthz", False, False), ("GET", "/readyz", False, False), ("POST", "/api/perguntar", False, False),
                          ("POST", "/api/perguntar", True, False)])
        forjado = json.loads(base64.b64decode(enviados[3][2]["X-MS-CLIENT-PRINCIPAL"]))
        self.assertIn({"typ": "tid", "val": TENANT}, forjado["claims"])
        self.assertIn({"typ": "roles", "val": "Vareleira.Atendimento"}, forjado["claims"])
        for estados, causa in (({("principal", "/api/perguntar"): (200, b"")}, "principal_forjado_nao_negado"),
                               ({("POST", "/api/perguntar"): (200, b"")}, "anonimo_nao_negado"),
                               ({("GET", "/healthz"): (503, b""), ("GET", "/readyz"): (200, b"")}, "healthz_indisponivel"),
                               ({("GET", "/healthz"): (200, b""), ("GET", "/readyz"): (503, b"")}, "readyz_indisponivel")):
            with self.subTest(causa=causa), mock.patch.object(sonda, "transporte_http", http({**saudaveis, **estados})):
                codigo, r = self.externo(["--etapa", "sem-credenciais"], {"VARELEIRA_HTTP_URL": URL})
                self.assertEqual((codigo, r["causa"], r["veredicto"]), (3, causa, "reprovado"))
        with mock.patch.object(sonda, "transporte_http", side_effect=OSError("sem rota")):
            codigo, r = self.externo(["--etapa", "sem-credenciais"], {"VARELEIRA_HTTP_URL": URL})
        self.assertEqual((codigo, r["causa"], r["dados"]["tipo"]), (2, "rede", "OSError"))
        for ambiente, causa, chave, valor in (
                ({}, "configuracao_ausente", "ausentes", ["url"]),
                ({"VARELEIRA_HTTP_URL": "http://chat.x.regiao-x.azurecontainerapps.io"}, "configuracao_invalida", "invalidas", ["url"]),
                ({"VARELEIRA_HTTP_URL": URL, "VARELEIRA_HTTP_TENANT_ID": "tenant com espaço"}, "configuracao_invalida", "invalidas",
                 ["tenant"])):
            codigo, r = self.externo(["--etapa", "sem-credenciais"], ambiente)
            self.assertEqual((codigo, r["causa"], r["dados"][chave]), (1, causa, valor))

    def test_a_barreira_por_valor_esta_ligada_ao_ponto_de_entrada_e_o_codigo_de_saida_e_o_da_linha_emitida(self):
        # Um valor privado (o tenant, o segredo) igual a uma palavra do vocabulário da linha bloqueia a linha pelo ponto de entrada
        # real, e o código de saída é o dela (4), não o 0 da etapa que foi aprovada.
        class CredencialDoAtendimento:
            def get_token(self, escopo, **_):
                return SimpleNamespace(token=jwt(CLIENT_ID, roles=["Vareleira.Atendimento"]), expires_on=4102444800)

        saudavel = mock.patch.object(sonda, "transporte_http", lambda metodo, url, cabecalhos, corpo: (200 if metodo == "GET" else 401, b""))
        with saudavel:
            codigo, r = self.externo(["--etapa", "sem-credenciais"], {"VARELEIRA_HTTP_URL": URL})
            self.assertEqual((codigo, r["veredicto"]), (0, "aprovado"))
            codigo, r = self.externo(["--etapa", "sem-credenciais"], {"VARELEIRA_HTTP_URL": URL, "VARELEIRA_HTTP_TENANT_ID": "aprovado"})
        self.assertEqual((codigo, r["codigo"], r["veredicto"], r["causa"]), (4, 4, "erro", "saida_bloqueada"))
        self.assertEqual(r["dados"], {"padroes": ["valor_de_configuracao"]})
        perfil = {**AMBIENTE_EXTERNO, "VARELEIRA_HTTP_PERFIL": "atendimento"}
        with mock.patch.object(externo, "criar_credencial", return_value=CredencialDoAtendimento()), \
                mock.patch.object(sonda, "transporte_http", return_value=(200, resposta_do_chat())):
            codigo, r = self.externo(["--etapa", "perfil"], perfil)
            self.assertEqual((codigo, r["veredicto"]), (0, "aprovado"))
            codigo, r = self.externo(["--etapa", "perfil"], {**perfil, "VARELEIRA_HTTP_CLIENT_SECRET": "aprovado"})
        self.assertEqual((codigo, r["codigo"], r["causa"]), (4, 4, "saida_bloqueada"))

    def test_sem_credenciais_so_conversa_com_o_endereco_do_chat_validado(self):
        # O transporte real recusa, antes de qualquer conexão, um destino fora de *.azurecontainerapps.io.
        with self.assertRaises(sonda.ErroSonda):
            sonda.sondar_sem_credenciais("https://exemplo.com")
        with mock.patch.dict(os.environ, {"VARELEIRA_HTTP_URL": URL}, clear=False), \
                mock.patch.object(sonda, "transporte_http", lambda metodo, url, cabecalhos, corpo: (200 if metodo == "GET" else 401, b"")):
            saida = io.StringIO()
            codigo = externo.principal(["--etapa", "sem-credenciais"], None, saida)
        self.assertEqual(codigo, 0)
        self.assertEqual(len(saida.getvalue().splitlines()), 1)

    def test_perfil_faz_uma_chamada_autenticada_e_confere_o_perfil_sem_repetir_nem_vazar(self):
        enviados, criadas = [], []

        def http(autenticado):
            def falso(metodo, url, cabecalhos, corpo):
                enviados.append((metodo, url.removeprefix(URL), cabecalhos.get("Authorization", ""), corpo))
                if isinstance(autenticado, Exception):
                    raise autenticado
                return autenticado

            return falso

        def credencial(papeis, falha=False):
            class Falsa(CredencialFalsa):
                def get_token(self, escopo, **_):
                    self.escopos.append(escopo)
                    if falha:
                        raise falha if isinstance(falha, Exception) else RuntimeError(f"AADSTS7000215: segredo {SEGREDO}")
                    carga = segmento({"roles": papeis, "oid": "pessoa", "upn": "alguem@exemplo"})
                    return SimpleNamespace(token=f"{segmento({'alg': 'none'})}.{carga}.sig", expires_on=4102444800)

            falsa = Falsa()
            return mock.patch.object(externo, "criar_credencial", side_effect=lambda *args: criadas.append(args) or falsa), falsa

        roteiro, compartilhada = EVIDENCIA_DO_ROTEIRO, EVIDENCIA_COMPARTILHADA
        atd, cor = ["Vareleira.Atendimento"], ["Vareleira.Corretor"]
        casos = (  # perfil, papéis no token, resposta HTTP, código, causa
            ("atendimento", atd, (200, resposta_do_chat()), 0, None),
            ("ambos", atd + cor, (200, resposta_do_chat()), 0, None),
            ("corretor", cor, (200, resposta_do_chat("sem_evidencia", "recusada", [])), 0, None),
            ("corretor", cor, (200, resposta_do_chat(evidencias=[compartilhada])), 0, None),
            ("corretor", cor, (200, resposta_do_chat(evidencias=[roteiro])), 3, "conteudo_interno_no_perfil_corretor"),
            ("corretor", cor, (200, resposta_do_chat(evidencias=[{**compartilhada, "fonte": "x/roteiro-interno-atendimento-v1.0.md"}])),
             3, "conteudo_interno_no_perfil_corretor"),
            ("sem-acesso", [], (403, b'{"erro": "nao_autorizado", "mensagem": "x", "id_requisicao": "y"}'), 0, None),
            ("sem-acesso", [], (200, resposta_do_chat()), 3, "acesso_indevido"),
            ("sem-acesso", [], (401, b""), 3, "http_inesperado"),
            ("atendimento", atd, (403, b""), 3, "http_inesperado"),
            ("atendimento", atd, (200, resposta_do_chat("sem_evidencia", "recusada", [])), 3, "classificacao_divergente"),
            ("atendimento", atd, (200, resposta_do_chat("fora_de_escopo", "recusada", [])), 3, "classificacao_divergente"),
            ("ambos", atd + cor, (200, resposta_do_chat(evidencias=[compartilhada])), 3, "fonte_operacional_ausente"),
            ("atendimento", atd, (200, b"<html>nao e json</html>"), 3, "resposta_fora_do_formato"),
        )
        for perfil, papeis, resposta, esperado, causa in casos:
            with self.subTest(perfil=perfil, causa=causa, http=resposta[0]):
                enviados.clear()
                criadas.clear()
                patch_credencial, falsa = credencial(papeis)
                with patch_credencial, mock.patch.object(sonda, "transporte_http", http(resposta)):
                    codigo, r = self.externo(["--etapa", "perfil"], {**AMBIENTE_EXTERNO, "VARELEIRA_HTTP_PERFIL": perfil})
                self.assertEqual((codigo, r["causa"], r["etapa"]), (esperado, causa, "http-externo-perfil"))
                # UMA chamada autenticada, sem repetição, com a pergunta que não traz o código nem o ID do roteiro.
                self.assertEqual([(m, u, a.startswith("Bearer ")) for m, u, a, _ in enviados], [("POST", "/api/perguntar", True)])
                self.assertEqual(json.loads(enviados[0][3]), {"pergunta": sonda.PERGUNTA_DO_CHAT})
                self.assertEqual(criadas, [(TENANT, CLIENT_ID, SEGREDO)])
                self.assertEqual(falsa.escopos, [f"api://{APP_ID}/.default"])
                self.assertEqual((r["dados"]["perfil"], r["dados"]["http"], r["dados"]["papeis_no_token"]), (perfil, resposta[0], papeis))

        # O que é registrado do caso aprovado: só HTTP, tipo e situação, contagens e presença do documento operacional e do marcador.
        patch_credencial, _ = credencial(atd)
        with patch_credencial, mock.patch.object(sonda, "transporte_http", http((200, resposta_do_chat()))):
            codigo, r = self.externo(["--etapa", "perfil"], {**AMBIENTE_EXTERNO, "VARELEIRA_HTTP_PERFIL": "atendimento"})
        self.assertEqual(r["dados"], {"perfil": "atendimento", "http": 200, "esperado": 200, "papeis_no_token": atd, "resposta": {
            "tipo": "documentada", "situacao": "respondida", "evidencias": 1, "marcador": True, "operacional": True}})
        patch_credencial, _ = credencial(["Vareleira.Atendimento"])
        with patch_credencial, mock.patch.object(sonda, "transporte_http", http((403, b'{"erro": "nao_autorizado"}'))):
            codigo, r = self.externo(["--etapa", "perfil"], {**AMBIENTE_EXTERNO, "VARELEIRA_HTTP_PERFIL": "sem-acesso"})
        self.assertEqual((codigo, r["causa"], r["dados"]["encontrados"], r["dados"]["esperados"]),
                         (1, "papeis_do_token_inesperados", atd, []))

        # Papel de aplicação desconhecido (o cliente de validação sem acesso): só os papéis reconhecidos pelo lab_acesso (Atendimento e
        # Corretor) contam. O desconhecido é ignorado, nunca sai no resultado, e a chamada segue; em sem-acesso o servidor deve dar 403.
        desconhecido = ["Vareleira.ValidacaoSemAcesso"]
        for perfil, papeis, resposta, esperado, causa, chamadas, encontrados in (
                ("sem-acesso", desconhecido, (403, b'{"erro": "nao_autorizado"}'), 0, None, 1, []),
                ("sem-acesso", desconhecido, (200, resposta_do_chat()), 3, "acesso_indevido", 1, []),
                ("sem-acesso", desconhecido + atd, (403, b""), 1, "papeis_do_token_inesperados", 0, atd),
                ("atendimento", desconhecido + atd, (200, resposta_do_chat()), 0, None, 1, atd)):
            with self.subTest(perfil=perfil, causa=causa, http=resposta[0]):
                enviados.clear()
                patch_credencial, _ = credencial(papeis)
                with patch_credencial, mock.patch.object(sonda, "transporte_http", http(resposta)):
                    codigo, r = self.externo(["--etapa", "perfil"], {**AMBIENTE_EXTERNO, "VARELEIRA_HTTP_PERFIL": perfil})
                self.assertEqual((codigo, r["causa"], len(enviados)), (esperado, causa, chamadas))
                chave = "encontrados" if causa == "papeis_do_token_inesperados" else "papeis_no_token"
                self.assertEqual(r["dados"][chave], encontrados)
                if perfil == "sem-acesso" and causa is None:
                    self.assertEqual((r["dados"]["http"], r["dados"]["chat"]), (403, "nao_autorizado"))

        # Token com papéis diferentes do perfil: configuração, sem nenhuma chamada HTTP. Token que não sai ou rede que falha: código 2.
        for papeis, falha, resposta, esperado, causa in ((cor, False, (200, b""), 1, "papeis_do_token_inesperados"),
                                                         (atd, True, (200, b""), 2, "token_indisponivel"),
                                                         (atd, False, OSError("sem rota"), 2, "rede")):
            with self.subTest(causa=causa):
                enviados.clear()
                patch_credencial, _ = credencial(papeis, falha)
                with patch_credencial, mock.patch.object(sonda, "transporte_http", http(resposta)):
                    codigo, r = self.externo(["--etapa", "perfil"], {**AMBIENTE_EXTERNO, "VARELEIRA_HTTP_PERFIL": "atendimento"})
                self.assertEqual((codigo, r["causa"]), (esperado, causa))
                self.assertEqual(len(enviados), 1 if causa == "rede" else 0)

        # Falha ao obter o token (cliente sem acesso, segredo errado...): só o tipo do erro e o código AADSTS, achado em memória. A
        # mensagem (GUIDs, ID de rastreio, segredo, token) nunca sai, e nenhuma chamada HTTP é feita.
        mensagem = (f"Authentication failed: AADSTS7000215: Invalid client secret provided. Trace ID: {TENANT} Correlation ID: "
                    f"{CLIENT_ID} Secret {SEGREDO} Bearer {segmento({'alg': 'none'})}")
        encadeado = RuntimeError("falha externa")
        encadeado.__cause__ = ValueError("AADSTS70011: The provided value for the input parameter 'scope' is not valid")
        for erro, tipo, esperado_entra in (
                (ClientAuthenticationError(mensagem), "ClientAuthenticationError", "AADSTS7000215"),
                (ClientAuthenticationError("Falha sem código do Entra para " + CLIENT_ID), "ClientAuthenticationError",
                 "nao_identificado"),
                (ClientAuthenticationError("AADSTS50126 depois AADSTS700016"), "ClientAuthenticationError", "AADSTS50126"),
                (ClientAuthenticationError("AADSTS12 tem menos de 4 dígitos e AADSTS não tem nenhum"), "ClientAuthenticationError",
                 "nao_identificado"),
                (encadeado, "RuntimeError", "AADSTS70011")):
            with self.subTest(tipo=tipo, entra=esperado_entra):
                enviados.clear()
                patch_credencial, _ = credencial(atd, erro)
                with patch_credencial, mock.patch.object(sonda, "transporte_http", http((200, b""))):
                    codigo, r = self.externo(["--etapa", "perfil"], {**AMBIENTE_EXTERNO, "VARELEIRA_HTTP_PERFIL": "sem-acesso"})
                self.assertEqual((codigo, r["causa"], r["veredicto"], len(enviados)), (2, "token_indisponivel", "erro", 0))
                self.assertEqual(r["dados"], {"tipo": tipo, "codigo_entra": esperado_entra})
                self.assertNotIn("Invalid client secret", json.dumps(r))

        # Configuração e uso: só os nomes das chaves; o segredo nunca é argumento.
        for retirar, valor_invalido, causa, chave, esperado in (
                ("VARELEIRA_HTTP_CLIENT_SECRET", None, "configuracao_ausente", "ausentes", ["segredo"]),
                ("VARELEIRA_HTTP_CLIENT_ID", "nao-e-guid", "configuracao_invalida", "invalidas", ["client_id"]),
                ("VARELEIRA_HTTP_LOGIN_APP_ID", None, "configuracao_ausente", "ausentes", ["login_app_id"]),
                ("VARELEIRA_HTTP_CLIENT_SECRET", "curto", "configuracao_invalida", "invalidas", ["segredo"])):
            ambiente = {**AMBIENTE_EXTERNO, "VARELEIRA_HTTP_PERFIL": "atendimento"}
            ambiente.pop(retirar) if valor_invalido is None else ambiente.update({retirar: valor_invalido})
            codigo, r = self.externo(["--etapa", "perfil"], ambiente)
            self.assertEqual((codigo, r["causa"], r["dados"][chave]), (1, causa, esperado))
            self.assertNotIn("nao-e-guid", json.dumps(r))
        codigo, r = self.externo(["--etapa", "perfil"], AMBIENTE_EXTERNO)
        self.assertEqual((codigo, r["causa"], r["dados"]["ausentes"]), (1, "configuracao_ausente", ["perfil"]))
        codigo, r = self.externo(["--etapa", "perfil", f"--segredo={SEGREDO}"], {**AMBIENTE_EXTERNO, "VARELEIRA_HTTP_PERFIL": "corretor"})
        self.assertEqual((codigo, r["causa"]), (1, "uso_invalido"))
        for argv in (["--etapa", "xpto"], [], ["--etapa", "perfil", "--segredo", SEGREDO], ["--segredo=" + SEGREDO]):
            codigo, r = self.externo(argv, {**AMBIENTE_EXTERNO, "VARELEIRA_HTTP_PERFIL": "corretor"})
            self.assertEqual(codigo, 1)
        codigo, r = self.externo(["--etapa", "perfil"], {**AMBIENTE_EXTERNO, "VARELEIRA_HTTP_PERFIL": "corretor", "VARELEIRA_HTTP_ETAPA": "sem-credenciais"})
        self.assertEqual((codigo, r["causa"]), (1, "etapa_conflitante"))


if __name__ == "__main__":
    unittest.main()
