"""Testes da operação protegida do L300 (scripts/operar_l300.py), todos locais: sem Azure, sem GitHub e sem rede.

Identificadores de ambiente (assinatura, principal, tenant) são GUIDs sorteados a cada execução, nunca valores fixos, e
os segredos de teste são sentinelas aleatórias: o que importa é que nenhum deles apareça no console nem nos relatórios.
"""

import ast
import contextlib
import copy
import hashlib
import inspect
import io
import json
import os
import re
import secrets
import socket
import stat
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest import mock

import support  # noqa: F401  (configura o caminho dos scripts)
import operar_l300
from lab_comum import CODIGO_DIVERGENCIA, CODIGO_INESPERADO, CODIGO_OK, CODIGO_USO
from support import RAIZ

SCRIPT = RAIZ / "scripts" / "operar_l300.py"


def executar(*argumentos: str, env: dict | None = None) -> tuple[int, str]:
    """Roda a linha de comando com um ambiente isolado e devolve (código de saída, tudo o que foi impresso)."""
    saida = io.StringIO()
    with contextlib.redirect_stdout(saida), contextlib.redirect_stderr(saida):
        try:
            codigo = operar_l300.principal(list(argumentos), env={} if env is None else env)
        except SystemExit as erro:
            codigo = erro.code
    return codigo, saida.getvalue()


@contextlib.contextmanager
def sem_rede():
    """Qualquer tentativa de abrir conexão ou de executar um programa derruba o teste."""
    def proibido(*_argumentos, **_opcoes):
        raise AssertionError("o script tentou usar a rede ou executar um programa")

    with contextlib.ExitStack() as pilha:
        for alvo, nome in ((socket.socket, "connect"), (socket, "create_connection"), (subprocess, "run"), (subprocess, "Popen")):
            pilha.enter_context(mock.patch.object(alvo, nome, proibido))
        yield


def variaveis_do_ambiente(fase: str = "rede") -> dict[str, str]:
    """vars do ambiente protegido para a fase: identidade de implantação (OIDC), destinos do Bicep e os parâmetros da fase."""
    variaveis = {
        "AZURE_CLIENT_ID": str(uuid.uuid4()), "AZURE_TENANT_ID": str(uuid.uuid4()), "AZURE_SUBSCRIPTION_ID": str(uuid.uuid4()),
        "VARELEIRA_GRUPO_RECURSOS": "rg-lab-teste", "VARELEIRA_NOME_CONTA": "stlabteste123",
        "VARELEIRA_NOME_BUSCA": "srch-lab-teste", "VARELEIRA_NOME_MODELOS": "ais-lab-teste",
        "VARELEIRA_NOME_REGISTRO": "acrlabteste123", "VARELEIRA_NOME_IDENTIDADE_APLICACAO": "id-lab-teste",
        "VARELEIRA_NOME_WORKSPACE_LOGS": "log-lab-teste", "VARELEIRA_ID_OBJETO_CARGA": str(uuid.uuid4()),
    }
    if fase == "aplicacao":
        variaveis |= {"VARELEIRA_ID_APLICACAO_LOGIN": str(uuid.uuid4()), "VARELEIRA_ID_TENANT_LOGIN": str(uuid.uuid4())}
    if fase == "isolar":
        variaveis |= {"VARELEIRA_SKU_ARMAZENAMENTO": "Standard_LRS", "VARELEIRA_SKU_BUSCA": "basic",
                      "VARELEIRA_REPLICAS_BUSCA": "1", "VARELEIRA_PARTICOES_BUSCA": "1"}
    return variaveis


def novo_segredo_do_login() -> str:
    """Segredo sintético do login da aplicação: aleatório a cada chamada, com a forma do que o Entra ID gera."""
    return "Q~" + secrets.token_urlsafe(30)


def ambiente_de_implantacao(**alteracoes: str) -> dict[str, str]:
    """Ambiente de um passo do workflow: contexto do GitHub, OIDC e as variáveis (vars) com valores sorteados.

    A fase vem de VARELEIRA_L300_FASE (padrão rede). Na fase aplicacao, o segredo do login entra como no workflow: variável
    efêmera do passo (vinda de secrets), nunca de vars.
    """
    fase = alteracoes.get("VARELEIRA_L300_FASE", "rede")
    env = {
        "GITHUB_ACTIONS": "true", "GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_REF": "refs/heads/main",
        "GITHUB_WORKFLOW_REF": "dono/repositorio/.github/workflows/l300-implantar.yml@refs/heads/main",
        "ACTIONS_ID_TOKEN_REQUEST_URL": "https://oidc.invalid/token?versao=1",
        "ACTIONS_ID_TOKEN_REQUEST_TOKEN": "token-" + secrets.token_hex(12),
        "VARELEIRA_L300_FASE": "rede", "VARELEIRA_APLICAR": "false", "VARELEIRA_L300_CONECTIVIDADE_PRIVADA_VALIDADA": "false",
        "VARELEIRA_L300_INGRESSO_EXTERNO": "false", "VARELEIRA_TAG_IMAGEM": "", "VARELEIRA_CONFIRMACAO": "",
        "VARELEIRA_VARS_JSON": json.dumps(variaveis_do_ambiente(fase)),
    }
    if fase == "aplicacao":
        env["VARELEIRA_SEGREDO_LOGIN"] = novo_segredo_do_login()
    env.update(alteracoes)
    return env


def identificadores(env: dict[str, str]) -> list[str]:
    """Valores que nunca podem aparecer na saída: os IDs de vars, o token do OIDC e o segredo do login da aplicação."""
    segredo = env.get("VARELEIRA_SEGREDO_LOGIN")
    return [*json.loads(env["VARELEIRA_VARS_JSON"]).values(), env["ACTIONS_ID_TOKEN_REQUEST_TOKEN"], *([segredo] if segredo else [])]


class ValidarTests(unittest.TestCase):
    def test_sem_fase_o_padrao_local_e_rede(self):
        codigo, saida = executar("--etapa", "validar")
        self.assertEqual(codigo, CODIGO_OK, saida)
        self.assertIn("Fase: rede", saida)
        self.assertIn("SIMULAÇÃO", saida)

    def test_fase_invalida_e_recusada_sem_repetir_o_valor(self):
        for valor in ("Rede", "rede; rm -rf /", "todas", "x" * 40, ""):
            if not valor:
                continue
            codigo, saida = executar("--etapa", "validar", env={"VARELEIRA_L300_FASE": valor})
            self.assertEqual(codigo, CODIGO_USO, saida)
            self.assertIn("Fase inválida", saida)
            self.assertNotIn(valor, saida)

    def test_na_implantacao_a_fase_precisa_ser_explicita(self):
        env = ambiente_de_implantacao()
        del env["VARELEIRA_L300_FASE"]
        codigo, saida = executar("--etapa", "validar", "--exigir-github", env=env)
        self.assertEqual(codigo, CODIGO_USO)
        self.assertIn("Fase ausente", saida)

    def test_aplicar_sem_confirmacao_exata_e_bloqueado_antes_de_qualquer_rede(self):
        with sem_rede():
            for confirmacao in ("", "APLICAR", "APLICAR-L300-ISOLAR", "aplicar-l300-rede", "APLICAR-L300-REDE "):
                codigo, saida = executar("--etapa", "validar", "--fase", "rede", "--aplicar", "--confirmacao", confirmacao)
                self.assertEqual(codigo, CODIGO_USO, confirmacao)
                self.assertIn("APLICAR-L300-REDE", saida)
                self.assertIn("Nada foi alterado", saida)

    def test_confirmacao_nomeia_a_fase_e_libera_cada_fase(self):
        for fase in operar_l300.FASES:
            argumentos = ["--etapa", "validar", "--fase", fase, "--aplicar", "--confirmacao", f"APLICAR-L300-{fase.upper()}"]
            if fase == "aplicacao":
                argumentos += ["--tag-imagem", "v1.2.3"]
            if fase == "isolar":
                argumentos += ["--conectividade-privada-validada"]
            codigo, saida = executar(*argumentos)
            self.assertEqual(codigo, CODIGO_OK, f"{fase}: {saida}")
            self.assertIn("APLICAÇÃO", saida)

    def test_confirmacao_so_importa_ao_aplicar(self):
        codigo, saida = executar("--etapa", "validar", "--fase", "rede", "--confirmacao", "qualquer coisa")
        self.assertEqual(codigo, CODIGO_OK, saida)

    def test_isolar_exige_a_conectividade_privada_validada_ate_para_simular(self):
        for aplicar in ((), ("--aplicar", "--confirmacao", "APLICAR-L300-ISOLAR")):
            codigo, saida = executar("--etapa", "validar", "--fase", "isolar", *aplicar)
            self.assertEqual(codigo, CODIGO_USO, saida)
            self.assertIn("conectividade_privada_validada=true", saida)
            self.assertIn("evidências", saida)
            self.assertIn("O Bicep recusa", saida)
            codigo, saida = executar("--etapa", "validar", "--fase", "isolar", *aplicar, "--conectividade-privada-validada")
            self.assertEqual(codigo, CODIGO_OK, saida)
            self.assertIn("atestada por quem dispara (não verificada pelo workflow)", saida)

    def test_so_a_fase_isolar_precisa_da_atestacao(self):
        for fase in ("rede", "aplicacao"):
            codigo, saida = executar("--etapa", "validar", "--fase", fase, "--tag-imagem", "v1")
            self.assertEqual(codigo, CODIGO_OK, saida)
            self.assertNotIn("atestada", saida)

    def test_ingresso_externo_so_existe_na_fase_aplicacao_e_vem_com_aviso(self):
        for fase in ("rede", "isolar"):
            codigo, saida = executar("--etapa", "validar", "--fase", fase, "--ingresso-externo", "--conectividade-privada-validada")
            self.assertEqual(codigo, CODIGO_USO, fase)
            self.assertIn("Ingresso externo: só existe na fase aplicacao", saida)
        codigo, saida = executar("--etapa", "validar", "--fase", "aplicacao", "--tag-imagem", "v1", "--ingresso-externo")
        self.assertEqual(codigo, CODIGO_OK, saida)
        self.assertIn("[AVISO] Ingresso externo LIGADO", saida)
        codigo, saida = executar("--etapa", "validar", "--fase", "aplicacao", "--tag-imagem", "v1")
        self.assertNotIn("Ingresso externo", saida)

    def test_tag_da_imagem_e_exigida_so_na_fase_aplicacao_e_nunca_e_mutavel(self):
        codigo, saida = executar("--etapa", "validar", "--fase", "aplicacao")
        self.assertEqual(codigo, CODIGO_USO, saida)
        self.assertIn("Tag da imagem ausente", saida)
        for fase, extra in (("rede", ()), ("isolar", ("--conectividade-privada-validada",))):
            codigo, saida = executar("--etapa", "validar", "--fase", fase, *extra)
            self.assertEqual(codigo, CODIGO_OK, f"{fase}: {saida}")
        for fase in operar_l300.FASES:
            for tag in ("latest", "LATEST", "v1; rm -rf", "$(id)", "a b", "-inicio", "x" * 129):
                codigo, saida = executar("--etapa", "validar", "--fase", fase, "--conectividade-privada-validada", f"--tag-imagem={tag}")
                self.assertEqual(codigo, CODIGO_USO, f"{fase}: {tag}")
                self.assertIn("Tag da imagem inválida", saida)
                if tag.lower() != "latest":  # a mensagem cita 'latest' como exemplo do que não usar
                    self.assertNotIn(tag, saida)
        codigo, saida = executar("--etapa", "validar", "--fase", "aplicacao", "--tag-imagem", "2026.10.10-ab12")
        self.assertEqual(codigo, CODIGO_OK, saida)

    def test_booleanos_aceitam_somente_true_ou_false(self):
        for valor in ("True", "1", "yes", "sim", "TRUE"):
            codigo, saida = executar("--etapa", "validar", env={"VARELEIRA_APLICAR": valor})
            self.assertEqual(codigo, CODIGO_USO, valor)
            self.assertIn("use exatamente 'true' ou 'false'", saida)
            self.assertNotIn(valor, saida.replace("'true' ou 'false'", ""))

    def test_qualificacoes_e_plano_esperado_malformados_sao_recusados_cedo(self):
        for nome, valor in (("VARELEIRA_QUALIFICAR_NAO_SUPORTADO", "tipo-sem-ponto=7x"),
                            ("VARELEIRA_QUALIFICAR_NAO_SUPORTADO", "Microsoft.Authorization/roleAssignments=tres"),
                            ("VARELEIRA_QUALIFICAR_PROPRIEDADES_REMOVIDAS", "Microsoft.Search/searchServices=5;ls"),
                            ("VARELEIRA_PLANO_SHA256", "ABC")):
            codigo, saida = executar("--etapa", "validar", env={nome: valor})
            self.assertEqual(codigo, CODIGO_USO, valor)
            self.assertIn(nome, saida)
            self.assertNotIn(valor, saida)

    def test_o_contexto_do_github_so_vale_no_workflow_manual_da_branch_principal(self):
        casos = (
            ({"GITHUB_ACTIONS": "false"}, "GITHUB_ACTIONS=true"),
            ({"GITHUB_EVENT_NAME": "pull_request"}, "disparo manual"),
            ({"GITHUB_EVENT_NAME": "push"}, "disparo manual"),
            ({"GITHUB_REF": "refs/heads/feature/x"}, "branch principal"),
            ({"GITHUB_REF": "refs/pull/7/merge"}, "branch principal"),
            ({"GITHUB_WORKFLOW_REF": "dono/repositorio/.github/workflows/outro.yml@refs/heads/main"}, "l300-implantar.yml"),
            ({"GITHUB_WORKFLOW_REF": "dono/repositorio/.github/workflows/l300-implantar.yml@refs/heads/feature"}, "l300-implantar.yml"),
        )
        for alteracao, trecho in casos:
            with self.subTest(alteracao=alteracao):
                codigo, saida = executar("--etapa", "validar", "--exigir-github", env=ambiente_de_implantacao(**alteracao))
                self.assertEqual(codigo, CODIGO_USO, saida)
                self.assertIn(trecho, saida)
        codigo, saida = executar("--etapa", "validar", "--exigir-github", env=ambiente_de_implantacao())
        self.assertEqual(codigo, CODIGO_OK, saida)

    def test_sem_oidc_o_login_nem_e_tentado(self):
        for faltando in ("ACTIONS_ID_TOKEN_REQUEST_URL", "ACTIONS_ID_TOKEN_REQUEST_TOKEN"):
            env = ambiente_de_implantacao()
            del env[faltando]
            codigo, saida = executar("--etapa", "validar", "--exigir-oidc", env=env)
            self.assertEqual(codigo, CODIGO_USO, faltando)
            self.assertIn("OIDC indisponível", saida)
            self.assertIn("id-token: write", saida)
        env = ambiente_de_implantacao()
        codigo, saida = executar("--etapa", "validar", "--exigir-oidc", env=env)
        self.assertEqual(codigo, CODIGO_OK, saida)
        self.assertNotIn(env["ACTIONS_ID_TOKEN_REQUEST_TOKEN"], saida)

    def test_variaveis_do_azure_ausentes_falham_antes_de_qualquer_chamada_listando_so_os_nomes(self):
        with sem_rede():
            env = ambiente_de_implantacao(VARELEIRA_VARS_JSON=json.dumps({"VARELEIRA_NOME_CONTA": "stlabteste123"}))
            codigo, saida = executar("--etapa", "validar", "--exigir-azure", env=env)
        self.assertEqual(codigo, CODIGO_USO, saida)
        for nome in ("AZURE_CLIENT_ID", "AZURE_TENANT_ID", "AZURE_SUBSCRIPTION_ID", "VARELEIRA_GRUPO_RECURSOS",
                     "VARELEIRA_NOME_BUSCA", "VARELEIRA_NOME_MODELOS", "VARELEIRA_NOME_REGISTRO",
                     "VARELEIRA_NOME_IDENTIDADE_APLICACAO", "VARELEIRA_NOME_WORKSPACE_LOGS", "VARELEIRA_ID_OBJETO_CARGA"):
            self.assertIn(nome, saida)
        self.assertNotIn("stlabteste123", saida)
        self.assertIn("sem valores padrão", saida)

    def test_variaveis_do_azure_com_formato_invalido_nao_sao_repetidas(self):
        sentinela = "SENTINELA-" + secrets.token_hex(8)
        variaveis = {**variaveis_do_ambiente(), "AZURE_TENANT_ID": sentinela,
                     "VARELEIRA_NOME_CONTA": "Conta_Com_Maiusculas-" + sentinela, "VARELEIRA_OUTRA": "valor com espaco " + sentinela}
        env = ambiente_de_implantacao(VARELEIRA_VARS_JSON=json.dumps(variaveis))
        codigo, saida = executar("--etapa", "validar", "--exigir-azure", env=env)
        self.assertEqual(codigo, CODIGO_USO, saida)
        for nome in ("AZURE_TENANT_ID", "VARELEIRA_NOME_CONTA", "VARELEIRA_OUTRA"):
            self.assertIn(nome, saida)
        self.assertNotIn(sentinela, saida)

    def test_implantacao_valida_nao_repete_nenhum_identificador(self):
        for fase in operar_l300.FASES:
            env = ambiente_de_implantacao(VARELEIRA_L300_FASE=fase, VARELEIRA_TAG_IMAGEM="v1.2.3" if fase == "aplicacao" else "",
                                          VARELEIRA_L300_CONECTIVIDADE_PRIVADA_VALIDADA="true" if fase == "isolar" else "false")
            codigo, saida = executar("--etapa", "validar", "--exigir-github", "--exigir-oidc", "--exigir-azure", env=env)
            self.assertEqual(codigo, CODIGO_OK, f"{fase}: {saida}")
            for valor in identificadores(env):
                if len(valor) > 3:  # os números curtos da fase isolar (como 1) aparecem em qualquer texto
                    self.assertNotIn(valor, saida, fase)
            self.assertIn("valores não exibidos", saida)

    def test_json_das_variaveis_invalido_e_recusado(self):
        for bruto in ("{", "[]", "null", '"texto"'):
            codigo, saida = executar("--etapa", "validar", "--exigir-azure", env=ambiente_de_implantacao(VARELEIRA_VARS_JSON=bruto))
            self.assertEqual(codigo, CODIGO_USO, bruto)
            self.assertIn("VARELEIRA_VARS_JSON", saida)

    def test_o_acesso_documental_do_l300_nao_pode_ser_desligado(self):
        variaveis = {**variaveis_do_ambiente(), "VARELEIRA_EXIGIR_ACESSO_DOCUMENTAL": "false"}
        codigo, saida = executar("--etapa", "validar", "--exigir-azure", env=ambiente_de_implantacao(VARELEIRA_VARS_JSON=json.dumps(variaveis)))
        self.assertEqual(codigo, CODIGO_USO, saida)
        self.assertIn("VARELEIRA_EXIGIR_ACESSO_DOCUMENTAL", saida)

    def test_valores_do_ambiente_vencem_os_do_json_das_variaveis(self):
        variaveis = {**variaveis_do_ambiente(), "VARELEIRA_L300_FASE": "isolar"}
        env = ambiente_de_implantacao(VARELEIRA_VARS_JSON=json.dumps(variaveis), VARELEIRA_L300_FASE="rede")
        self.assertEqual(operar_l300.validar_operacao(env, exigir_azure=True).fase, "rede")

    def test_segredos_nunca_entram_por_vars(self):
        segredo = "SEGREDO-" + secrets.token_hex(10)
        base = variaveis_do_ambiente()
        for nome in ("VARELEIRA_SEGREDO_LOGIN", "VARELEIRA_SENHA_X", "VARELEIRA_TOKEN_Y", "VARELEIRA_CHAVE_Z", "VARELEIRA_API_KEY",
                     "VARELEIRA_CLIENT_SECRET", "AZURE_CLIENT_SECRET", "AZURE_PASSWORD"):
            env = ambiente_de_implantacao(VARELEIRA_VARS_JSON=json.dumps({**base, nome: segredo}))
            codigo, saida = executar("--etapa", "validar", "--exigir-azure", env=env)
            self.assertEqual(codigo, CODIGO_USO, nome)
            self.assertIn(nome, saida)
            self.assertIn("segredos nunca ficam em variáveis do GitHub", saida)
            self.assertNotIn(segredo, saida)

    def test_exportar_para_o_github_env_leva_so_o_validado(self):
        variaveis = {**variaveis_do_ambiente("aplicacao"), "NAO_E_NOSSA": "x", "VARELEIRA_REGIAO": "brazilsouth"}
        env = ambiente_de_implantacao(VARELEIRA_VARS_JSON=json.dumps(variaveis), VARELEIRA_L300_FASE="aplicacao",
                                      VARELEIRA_TAG_IMAGEM="v1.0.0", VARELEIRA_CONFIRMACAO="texto qualquer")
        with tempfile.TemporaryDirectory() as pasta:
            destino = Path(pasta) / "github_env"
            env["GITHUB_ENV"] = str(destino)
            codigo, saida = executar("--etapa", "validar", "--exigir-github", "--exigir-azure", "--exportar-github-env", env=env)
            self.assertEqual(codigo, CODIGO_OK, saida)
            conteudo = destino.read_text(encoding="utf-8")
        linhas = conteudo.splitlines()
        exportado = dict(linha.split("=", 1) for linha in linhas)
        self.assertEqual(exportado["VARELEIRA_L300_FASE"], "aplicacao")
        self.assertEqual(exportado["VARELEIRA_L300_CONECTIVIDADE_PRIVADA_VALIDADA"], "false")
        self.assertEqual(exportado["VARELEIRA_L300_INGRESSO_EXTERNO"], "false")
        self.assertEqual(exportado["VARELEIRA_TAG_IMAGEM"], "v1.0.0")
        self.assertEqual(exportado["VARELEIRA_REGIAO"], "brazilsouth")
        self.assertEqual(exportado["VARELEIRA_ID_APLICACAO_LOGIN"], variaveis["VARELEIRA_ID_APLICACAO_LOGIN"])
        self.assertTrue(all(nome.startswith("VARELEIRA_") for nome in exportado), exportado.keys())
        for proibido in ("VARELEIRA_VARS_JSON", "VARELEIRA_CONFIRMACAO", "AZURE_CLIENT_ID", "AZURE_TENANT_ID", "NAO_E_NOSSA",
                         "VARELEIRA_SEGREDO_LOGIN"):
            self.assertNotIn(proibido, exportado)
        self.assertNotIn(env["VARELEIRA_SEGREDO_LOGIN"], conteudo, "o segredo do login nunca vai para o GITHUB_ENV")
        self.assertEqual(len(linhas), len(exportado))

    def test_a_confirmacao_so_e_repassada_quando_se_pede_para_aplicar(self):
        env = ambiente_de_implantacao(VARELEIRA_L300_FASE="rede", VARELEIRA_APLICAR="true", VARELEIRA_CONFIRMACAO="APLICAR-L300-REDE")
        self.assertEqual(operar_l300.validar_operacao(env, exigir_azure=True).exportar["VARELEIRA_CONFIRMACAO"], "APLICAR-L300-REDE")

    def test_exportar_recusa_valores_com_quebra_de_linha_ou_nomes_fora_do_padrao(self):
        with tempfile.TemporaryDirectory() as pasta:
            destino = Path(pasta) / "github_env"
            for exportar in ({"VARELEIRA_X": "a\nPATH=/x"}, {"PATH": "/x"}, {"VARELEIRA_X": "com espaco"}, {"VARELEIRA_X": "a" * 513}):
                with self.assertRaises(operar_l300.ErroLab):
                    operar_l300.escrever_github_env(str(destino), exportar)
            self.assertFalse(destino.exists(), "nada pode ser gravado quando algo é recusado")

    def test_exportar_exige_o_ambiente_do_github_actions(self):
        codigo, saida = executar("--etapa", "validar", "--exportar-github-env")
        self.assertEqual(codigo, CODIGO_USO, saida)
        self.assertIn("só funciona dentro do GitHub Actions", saida)


class PlanoTests(unittest.TestCase):
    def test_cada_fase_diz_o_que_cria_reutiliza_altera_e_o_efeito_na_migracao(self):
        plano = operar_l300.montar_plano("todas")
        self.assertEqual([f["fase"] for f in plano["fases"]], ["rede", "aplicacao", "isolar"])
        self.assertEqual(plano["nuvem"], {"chamadas": 0, "executa": False})
        for fase in plano["fases"]:
            for chave in ("objetivo", "cria", "reutiliza", "altera", "efeito_na_migracao", "precondicoes", "portoes", "nao_faz"):
                self.assertIn(chave, fase)
            self.assertTrue(fase["efeito_na_migracao"], fase["fase"])
            self.assertTrue(any("APLICAR-L300-<FASE>" in portao for portao in fase["portoes"]), fase["fase"])
        rede, aplicacao, isolar = plano["fases"]
        self.assertTrue(any("novo ambiente" in item for item in rede["cria"]))
        self.assertTrue(any("ACR" in item for item in rede["reutiliza"]))
        self.assertTrue(any("vareleira-lar-l300" in item for item in aplicacao["cria"]))
        self.assertTrue(any("VARELEIRA_EXIGIR_ACESSO_DOCUMENTAL=true" in item for item in aplicacao["cria"]))
        self.assertTrue(any("runner" in item and "DENTRO da rede" in item for item in aplicacao["fora_do_bicep"]))

    def test_isolar_declara_o_efeito_no_l200_e_exige_a_prova_do_operador(self):
        isolar = operar_l300.montar_plano("isolar")["fases"][0]
        texto = " ".join(isolar["efeito_na_migracao"] + isolar["precondicoes"] + isolar["portoes"])
        self.assertIn("L200", texto)
        self.assertIn("perdem o acesso aos dados", texto)
        self.assertIn("SPL", texto)
        self.assertIn("aprovadas no destino".lower(), texto.lower())
        self.assertIn("prova positiva", texto)
        self.assertIn("prova negativa", texto)
        self.assertIn("atestação sua", texto)

    def test_o_plano_nao_toca_a_rede_e_a_saida_nao_tem_identificadores(self):
        with sem_rede():
            codigo, saida = executar("--etapa", "plano", "--fase", "todas")
        self.assertEqual(codigo, CODIGO_OK, saida)
        self.assertIn("nenhuma chamada de rede", saida)
        self.assertNotRegex(saida, operar_l300._GUID.pattern)
        self.assertIn("Efeito na migração", saida)

    def test_o_plano_em_json_e_valido_e_a_fase_invalida_e_recusada(self):
        codigo, saida = executar("--etapa", "plano", "--fase", "isolar", "--formato", "json")
        self.assertEqual(codigo, CODIGO_OK, saida)
        self.assertEqual(json.loads(saida)["fases"][0]["fase"], "isolar")
        codigo, saida = executar("--etapa", "plano", "--fase", "tudo")
        self.assertEqual(codigo, CODIGO_USO, saida)

    def test_validar_bicep_compila_localmente_e_aceita_so_lint_sem_avisos(self):
        with tempfile.TemporaryDirectory() as pasta:
            arquivo = Path(pasta) / "l300.bicep"
            arquivo.write_text("targetScope = 'resourceGroup'\n", encoding="utf-8")
            chamadas = []

            def falso(comando, **opcoes):
                chamadas.append(comando[1])
                dados = {"--version": ("Bicep CLI version 0.48.1 (abc)", ""), "build": ("{}", ""), "lint": ("", "")}
                saida, erro = dados[comando[1]]
                return mock.Mock(returncode=0, stdout=saida, stderr=erro)

            resultado = operar_l300.validar_bicep(arquivo, binario="bicep-falso", executar=falso)
        self.assertEqual(chamadas, ["--version", "build", "lint"])
        self.assertEqual(resultado, {"arquivo": "infra/l300.bicep", "versao_do_bicep": "0.48.1", "compila": True,
                                     "avisos_do_lint": 0, "erros_do_lint": 0})

    def test_validar_bicep_recusa_aviso_ou_qualquer_saida_do_lint_sem_imprimir_a_configuracao(self):
        sentinela = "SENTINELA-" + secrets.token_hex(8)
        diagnosticos = {
            "um aviso": f"C:\\{sentinela}\\l300.bicep(1,1) : Warning no-unused-vars: Variable \"{sentinela}\" não é usada. "
                        "[https://aka.ms/bicep/linter/no-unused-vars]\n",
            "avisos de tipos sem definição": "".join(
                f"C:\\x\\l300.bicep({n},1) : Warning BCP081: Resource type \"{sentinela}@2026-01-01\" does not have types.\n"
                for n in range(1, 4)),
            "nível informativo": f"C:\\x\\l300.bicep(2,2) : Info use-recent-api-versions: {sentinela}\n",
            "texto sem formato conhecido": f"alguma coisa {sentinela}\n",
        }
        with tempfile.TemporaryDirectory() as pasta:
            arquivo = Path(pasta) / "l300.bicep"
            arquivo.write_text("targetScope = 'resourceGroup'\n", encoding="utf-8")
            for descricao, texto in diagnosticos.items():
                for saida_do_lint in ({"stdout": texto, "stderr": ""}, {"stdout": "", "stderr": texto}):
                    def falso(comando, **opcoes):
                        dados = {"--version": ("Bicep CLI version 0.48.1 (abc)", ""), "build": ("{}", ""),
                                 "lint": (saida_do_lint["stdout"], saida_do_lint["stderr"])}
                        saida, erro = dados[comando[1]]
                        return mock.Mock(returncode=0, stdout=saida, stderr=erro)

                    with self.subTest(descricao, onde=[k for k, v in saida_do_lint.items() if v][0]):
                        with self.assertRaises(operar_l300.ErroLab) as contexto:
                            operar_l300.validar_bicep(arquivo, binario="bicep-falso", executar=falso)
                        mensagem = str(contexto.exception)
                        self.assertIn("lint do Bicep não está limpo", mensagem)
                        self.assertIn("lint SEM avisos, o mesmo do CI", mensagem)
                        self.assertIn("BICEP_VERSAO", mensagem)
                        self.assertNotIn(sentinela, mensagem)
                        self.assertNotIn("C:\\", mensagem, "nenhum caminho do diagnóstico é repetido")

    def test_validar_bicep_diz_quantos_avisos_e_de_quais_regras_sem_repetir_o_texto(self):
        with tempfile.TemporaryDirectory() as pasta:
            arquivo = Path(pasta) / "l300.bicep"
            arquivo.write_text("targetScope = 'resourceGroup'\n", encoding="utf-8")
            lint = ("a.bicep(1,1) : Warning BCP081: tipo sem definição\nb.bicep(2,2) : Warning BCP081: outro tipo\n"
                    "c.bicep(3,3) : Warning no-unused-params: sem uso\n")

            def falso(comando, **opcoes):
                dados = {"--version": ("Bicep CLI version 0.47.16 (abc)", ""), "build": ("{}", ""), "lint": (lint, "")}
                saida, erro = dados[comando[1]]
                return mock.Mock(returncode=0, stdout=saida, stderr=erro)

            with self.assertRaises(operar_l300.ErroLab) as contexto:
                operar_l300.validar_bicep(arquivo, binario="bicep-falso", executar=falso)
        self.assertIn("(3 aviso(s); regras: BCP081=2, no-unused-params=1)", str(contexto.exception))
        self.assertNotIn("tipo sem definição", str(contexto.exception))

    def test_validar_bicep_recusa_o_lint_que_termina_com_falha_mesmo_sem_saida(self):
        with tempfile.TemporaryDirectory() as pasta:
            arquivo = Path(pasta) / "l300.bicep"
            arquivo.write_text("targetScope = 'resourceGroup'\n", encoding="utf-8")

            def falso(comando, **opcoes):
                codigos = {"--version": 0, "build": 0, "lint": 1}
                return mock.Mock(returncode=codigos[comando[1]], stdout="Bicep CLI version 0.48.1" if comando[1] == "--version" else "",
                                 stderr="")

            with self.assertRaisesRegex(operar_l300.ErroLab, "lint do Bicep não está limpo"):
                operar_l300.validar_bicep(arquivo, binario="bicep-falso", executar=falso)

    def test_plano_com_validar_bicep_pela_linha_de_comando_recusa_aviso_e_so_conclui_com_lint_limpo(self):
        sentinela = "SENTINELA-" + secrets.token_hex(8)
        with tempfile.TemporaryDirectory() as pasta:
            arquivo = Path(pasta) / "l300.bicep"
            arquivo.write_text("targetScope = 'resourceGroup'\n", encoding="utf-8")

            def com_lint(texto):
                def falso(comando, **opcoes):
                    dados = {"--version": f"Bicep CLI version 0.48.1 ({sentinela})", "build": "{}", "lint": texto}
                    return mock.Mock(returncode=0, stdout=dados[comando[1]], stderr="")
                return falso

            original = operar_l300.validar_bicep
            with mock.patch.object(operar_l300, "validar_bicep", lambda: original(arquivo, binario="bicep-falso")):
                with mock.patch.object(operar_l300.subprocess, "run", com_lint(f"x.bicep(1,1) : Warning BCP081: {sentinela}\n")):
                    codigo, saida = executar("--etapa", "plano", "--fase", "rede", "--validar-bicep")
                self.assertEqual(codigo, CODIGO_USO, saida)
                self.assertIn("lint do Bicep não está limpo", saida)
                self.assertNotIn(sentinela, saida)
                with mock.patch.object(operar_l300.subprocess, "run", com_lint("")):
                    codigo, saida = executar("--etapa", "plano", "--fase", "rede", "--validar-bicep")
                self.assertEqual(codigo, CODIGO_OK, saida)
                self.assertIn("e o lint está limpo (sem avisos, como no CI)", saida)

    def test_validar_bicep_nao_finge_quando_falta_o_arquivo_o_binario_ou_a_compilacao_falha(self):
        with tempfile.TemporaryDirectory() as pasta:
            ausente = Path(pasta) / "l300.bicep"
            with self.assertRaisesRegex(operar_l300.ErroLab, "ainda não existe.*NÃO foi conferida"):
                operar_l300.validar_bicep(ausente, binario="bicep-falso")
            ausente.write_text("x", encoding="utf-8")
            with mock.patch.object(operar_l300, "localizar_bicep", return_value=None):
                with self.assertRaisesRegex(operar_l300.ErroLab, "Bicep CLI não encontrado.*NÃO foi conferida"):
                    operar_l300.validar_bicep(ausente)
            falha = mock.Mock(return_value=mock.Mock(returncode=1, stdout="", stderr="C:\\x : Error BCP001: segredo"))
            with self.assertRaisesRegex(operar_l300.ErroLab, "não compilou") as contexto:
                operar_l300.validar_bicep(ausente, binario="bicep-falso", executar=falha)
            self.assertNotIn("segredo", str(contexto.exception))

    def test_o_plano_separa_a_configuracao_privada_das_credenciais(self):
        plano = operar_l300.montar_plano("isolar")
        privada, nao_privada = plano["configuracao"]["privada"], plano["configuracao"]["nao_privada"]
        self.assertEqual(privada["variaveis"], list(operar_l300.VARS_PRIVADAS))
        self.assertEqual(nao_privada["variaveis"], list(operar_l300.VARS_NAO_PRIVADAS))
        self.assertIn("NÃO são credenciais", privada["o_que_e"])
        self.assertIn("secrets individuais do ambiente protegido", privada["onde"])
        self.assertIn("nunca vars nem vars serializado", privada["onde"])
        self.assertIn("variáveis (vars) do ambiente protegido, mapeadas uma a uma", nao_privada["onde"])
        self.assertNotIn("VARELEIRA_SEGREDO_LOGIN", privada["variaveis"] + nao_privada["variaveis"])
        codigo, saida = executar("--etapa", "plano", "--fase", "isolar")
        self.assertEqual(codigo, CODIGO_OK, saida)
        self.assertIn("Configuração (não é credencial):", saida)
        self.assertIn("  - Privada: identificadores e nomes", saida)
        self.assertIn("  - Não privada: SKUs, réplicas, partições, regiões e a ação sem login", saida)
        self.assertNotRegex(saida, operar_l300._GUID.pattern)

    def test_o_plano_declara_as_duas_credenciais_sem_nenhum_valor(self):
        plano = operar_l300.montar_plano("aplicacao")
        credenciais = plano["credenciais"]
        self.assertEqual(set(credenciais), {"implantacao_oidc", "login_da_aplicacao"})
        self.assertEqual(credenciais["implantacao_oidc"]["variaveis"], ["AZURE_CLIENT_ID", "AZURE_TENANT_ID", "AZURE_SUBSCRIPTION_ID"])
        self.assertIn("nenhum", credenciais["implantacao_oidc"]["segredo"])
        login = credenciais["login_da_aplicacao"]
        self.assertEqual(login["fase"], "aplicacao")
        for trecho in ("VARELEIRA_SEGREDO_LOGIN", "o único segredo aceito", "secrets do ambiente protegido", "@secure",
                       "nunca vai para vars, GITHUB_ENV, argumentos, console nem relatórios"):
            self.assertIn(trecho, login["segredo"])
        self.assertIn("não é a identidade de implantação", login["quem"].replace("\n", " "))
        precondicoes = " ".join(plano["fases"][0]["precondicoes"])
        self.assertIn("VARELEIRA_ID_APLICACAO_LOGIN", precondicoes)
        self.assertIn("não se confunde com a identidade de implantação (OIDC)", precondicoes)
        codigo, saida = executar("--etapa", "plano", "--fase", "aplicacao")
        self.assertEqual(codigo, CODIGO_OK, saida)
        self.assertIn("Implantação (OIDC):", saida)
        self.assertIn("Login da aplicação (fase aplicacao):", saida)
        plano_isolar = " ".join(operar_l300.montar_plano("isolar")["fases"][0]["precondicoes"])
        for nome in CONFIGURACAO_DO_ISOLAMENTO:
            self.assertIn(nome, plano_isolar)

    def test_o_plano_grava_relatorio_novo_e_nunca_sobrescreve(self):
        with tempfile.TemporaryDirectory() as pasta:
            destino = Path(pasta) / "plano.json"
            codigo, saida = executar("--etapa", "plano", "--fase", "rede", "--relatorio", str(destino))
            self.assertEqual(codigo, CODIGO_OK, saida)
            original = destino.read_bytes()
            codigo, saida = executar("--etapa", "plano", "--fase", "isolar", "--relatorio", str(destino))
            self.assertEqual(codigo, CODIGO_USO, saida)
            self.assertEqual(destino.read_bytes(), original)


class Cenario:
    """Um what-if sintético com a mesma forma do que o ARM devolve, cheio de valores que não podem vazar."""

    def __init__(self, grupo_longo: bool = False):
        self.assinatura = str(uuid.uuid4())
        self.principal = str(uuid.uuid4())
        self.grupo = "rg-" + secrets.token_hex(40 if grupo_longo else 4)  # o ARM aceita grupos de até 90 caracteres
        self.nome = "recurso" + secrets.token_hex(4)
        self.segredo = "SEGREDO-" + secrets.token_hex(12)
        self.chave_secreta = secrets.token_hex(16)
        self.endereco = "10.77.33.12"
        self.modelo = "gpt-5.4-mini-2026-03-17"
        self.sentinelas = [self.assinatura, self.principal, self.grupo, self.nome, self.segredo, self.chave_secreta,
                           self.endereco, self.modelo, "text-embedding-3-small", "gpt-5.4-mini"]

    def id(self, namespace: str, *pares: str) -> str:
        return f"/subscriptions/{self.assinatura}/resourceGroups/{self.grupo}/providers/{namespace}/" + "/".join(pares)

    def mudanca(self, acao: str, resource_id: str, delta=None, antes=None, depois=None, motivo=None) -> dict:
        return {"after": depois, "before": antes, "changeType": acao, "delta": delta, "deploymentId": None, "extension": None,
                "identifiers": None, "resourceId": resource_id, "symbolicName": None, "unsupportedReason": motivo}

    def expressao(self, escopo: str) -> str:
        return (f"[extensionResourceId('{escopo}', 'Microsoft.Authorization/roleAssignments', guid('{escopo}', "
                f"reference('{self.id('Microsoft.ManagedIdentity', 'userAssignedIdentities', self.nome)}', '2024-11-30')"
                f".principalId, '{uuid.uuid4()}'))]")

    def delta_da_busca(self) -> list[dict]:
        servidor = [{"path": f"properties.{campo}", "propertyChangeType": "Delete", "before": self.endereco, "after": None,
                     "children": None} for campo in ("computeType", "encryptionWithCmk", "endpoint", "networkRuleSet", "semanticSearch")]
        return [
            {"path": "identity", "propertyChangeType": "Create", "before": None,
             "after": {"type": "SystemAssigned", "principalId": self.principal}, "children": None},
            {"path": f"identity.userAssignedIdentities.{self.id('Microsoft.ManagedIdentity', 'userAssignedIdentities', self.nome)}",
             "propertyChangeType": "Create", "before": None, "after": {"clientId": self.principal}, "children": None},
            {"path": f"tags.{self.chave_secreta}", "propertyChangeType": "Modify", "before": self.segredo, "after": self.segredo + "2",
             "children": None},
            {"path": "properties.ipRules", "propertyChangeType": "Array", "before": None, "after": None, "children": [
                {"path": "0", "propertyChangeType": "Modify", "before": self.endereco, "after": self.endereco + "9", "children": None}]},
            *servidor,
        ]

    def whatif(self) -> dict:
        busca = self.id("Microsoft.Search", "searchServices", self.nome)
        mudancas = [
            self.mudanca("Create", self.id("Microsoft.Network", "virtualNetworks", self.nome),
                         depois={"properties": {"addressSpace": {"addressPrefixes": [self.endereco + "/16"]}}}),
            self.mudanca("Create", self.id("Microsoft.CognitiveServices", "accounts", self.nome, "deployments", "geracao"),
                         depois={"properties": {"model": {"name": "gpt-5.4-mini", "version": "2026-03-17"}}, "id": self.modelo}),
            self.mudanca("Modify", busca, delta=self.delta_da_busca(), antes={"x": self.segredo}, depois={"x": self.segredo}),
            self.mudanca("Ignore", self.id("Microsoft.Storage", "storageAccounts", self.nome)),
            self.mudanca("NoChange", self.id("Microsoft.OperationalInsights", "workspaces", self.nome)),
        ]
        for escopo in (self.id("Microsoft.Storage", "storageAccounts", self.nome), busca,
                       self.id("Microsoft.CognitiveServices", "accounts", self.nome)):
            mudancas.append(self.mudanca(
                "Unsupported", self.expressao(escopo),
                motivo=f"Changes to the resource declared at 'properties.template.resources[5]' cannot be analyzed because its "
                       f"resource ID or API version cannot be calculated before deployment ({self.segredo})."))
        return {"changes": mudancas, "diagnostics": None, "error": None, "potentialChanges": None, "status": "Succeeded"}


QUALIFICADO = ("--qualificar-nao-suportado", "Microsoft.Authorization/roleAssignments=3",
               "--qualificar-propriedades-removidas", "Microsoft.Search/searchServices=5")


class SanitizarWhatIfTests(unittest.TestCase):
    def setUp(self):
        self._pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self._pasta.cleanup)
        self.pasta = Path(self._pasta.name)
        self.cenario = Cenario()

    def arquivo(self, dados, nome="whatif.json") -> Path:
        caminho = self.pasta / nome
        caminho.write_text(json.dumps(dados), encoding="utf-8")
        return caminho

    def sanitizar(self, dados, *extras: str, relatorio="relatorio.json", env=None) -> tuple[int, str, dict | None]:
        entrada = self.arquivo(dados, f"entrada-{secrets.token_hex(3)}.json")
        destino = self.pasta / relatorio
        codigo, saida = executar("--etapa", "sanitizar-whatif", "--arquivo", str(entrada), "--relatorio", str(destino), *extras,
                                 env=env)
        return codigo, saida, (json.loads(destino.read_text(encoding="utf-8")) if destino.exists() else None)

    def test_plano_qualificado_conclui_e_nada_secreto_chega_ao_console_nem_ao_relatorio(self):
        codigo, saida, relatorio = self.sanitizar(self.cenario.whatif(), *QUALIFICADO, "--rotulo", "rede")
        self.assertEqual(codigo, CODIGO_OK, saida)
        texto = json.dumps(relatorio, ensure_ascii=False) + saida + (self.pasta / "relatorio.json").read_text(encoding="utf-8")
        for sentinela in self.cenario.sentinelas:
            self.assertNotIn(sentinela, texto)
        self.assertNotRegex(texto, r"https?://")
        self.assertNotRegex(texto, operar_l300._GUID.pattern)
        self.assertEqual(relatorio["decisao"], {"codigo": 0, "resultado": "concluido", "motivos": []})
        self.assertIn("Resultado: CONCLUÍDO", saida)

    def test_o_relatorio_guarda_contagens_tipos_e_caminhos(self):
        _, _, relatorio = self.sanitizar(self.cenario.whatif(), *QUALIFICADO)
        self.assertEqual(relatorio["por_mudanca"], {"Create": 2, "Delete": 0, "Deploy": 0, "Ignore": 1, "Modify": 1, "NoChange": 1,
                                                    "Unsupported": 3})
        tipos = {entrada["tipo"]: entrada for entrada in relatorio["por_tipo"]}
        self.assertEqual(set(tipos), {"Microsoft.Network/virtualNetworks", "Microsoft.CognitiveServices/accounts/deployments",
                                      "Microsoft.Search/searchServices", "Microsoft.Storage/storageAccounts",
                                      "Microsoft.OperationalInsights/workspaces", "Microsoft.Authorization/roleAssignments"})
        self.assertEqual(relatorio["nao_suportados"], {"Microsoft.Authorization/roleAssignments": 3})
        self.assertEqual(relatorio["motivos_nao_suportado"], {"id_ou_versao_nao_calculavel": 3})
        self.assertEqual(relatorio["propriedades_removidas"], {"Microsoft.Search/searchServices": 5})
        caminhos = {(c["caminho"], c["mudanca"]) for c in tipos["Microsoft.Search/searchServices"]["caminhos"]}
        self.assertIn(("identity", "Create"), caminhos)
        self.assertIn(("properties.networkRuleSet", "Delete"), caminhos)
        self.assertIn(("properties.ipRules.*", "Modify"), caminhos, "índices de lista viram '*'")
        self.assertIn(("identity.userAssignedIdentities.<chave>.<chave>", "Create"), caminhos, "chaves com IDs viram <chave>")
        self.assertIn(("tags.<chave>", "Modify"), caminhos, "chaves que parecem segredo viram <chave>")
        for caminho, _ in caminhos:
            self.assertRegex(caminho, r"^[A-Za-z_.*<>]+$")

    def test_o_hash_do_arquivo_bruto_e_registrado_e_o_do_conteudo_independe_da_ordem(self):
        dados = self.cenario.whatif()
        entrada = self.arquivo(dados)
        _, _, relatorio = self.sanitizar(dados, *QUALIFICADO)
        self.assertEqual(relatorio["bruto_sha256"], hashlib.sha256(entrada.read_bytes()).hexdigest())
        invertido = copy.deepcopy(dados)
        invertido["changes"].reverse()
        _, _, outro = self.sanitizar(invertido, *QUALIFICADO, relatorio="outro.json")
        self.assertNotEqual(outro["bruto_sha256"], relatorio["bruto_sha256"])
        self.assertEqual(outro["conteudo_sha256"], relatorio["conteudo_sha256"])

    def test_plano_esperado_vincula_a_aplicacao_ao_plano_revisado(self):
        dados = self.cenario.whatif()
        _, _, revisado = self.sanitizar(dados, *QUALIFICADO)
        codigo, saida, relatorio = self.sanitizar(dados, *QUALIFICADO, "--plano-esperado", revisado["conteudo_sha256"],
                                                  relatorio="igual.json")
        self.assertEqual(codigo, CODIGO_OK, saida)
        alterado = copy.deepcopy(dados)
        alterado["changes"].append(self.cenario.mudanca("Create", self.cenario.id("Microsoft.Network", "privateEndpoints", "x")))
        codigo, saida, relatorio = self.sanitizar(alterado, *QUALIFICADO, "--plano-esperado", revisado["conteudo_sha256"],
                                                  relatorio="diferente.json")
        self.assertEqual(codigo, CODIGO_DIVERGENCIA, saida)
        self.assertEqual(relatorio["decisao"]["motivos"][0]["codigo"], "plano_diferente_do_revisado")

    def test_exclusao_de_recurso_e_inesperada_e_devolve_3(self):
        dados = self.cenario.whatif()
        dados["changes"].append(self.cenario.mudanca("Delete", self.cenario.id("Microsoft.Storage", "storageAccounts", "outra")))
        codigo, saida, relatorio = self.sanitizar(dados, *QUALIFICADO)
        self.assertEqual(codigo, CODIGO_DIVERGENCIA, saida)
        self.assertIn("exclui 1 recurso", saida)
        self.assertIn("Resultado: BLOQUEADO (código 3)", saida)
        self.assertEqual([m["codigo"] for m in relatorio["decisao"]["motivos"]], ["exclusao_de_recurso"])
        self.assertNotIn("outra", saida + json.dumps(relatorio))

    def test_item_nao_suportado_sem_qualificacao_devolve_3_e_diz_como_qualificar(self):
        codigo, saida, relatorio = self.sanitizar(self.cenario.whatif(), "--qualificar-propriedades-removidas",
                                                  "Microsoft.Search/searchServices=5")
        self.assertEqual(codigo, CODIGO_DIVERGENCIA, saida)
        self.assertIn("--qualificar-nao-suportado Microsoft.Authorization/roleAssignments=3", saida)
        self.assertIn("não é aprovado automaticamente", saida)
        self.assertEqual(relatorio["decisao"]["motivos"][0]["codigo"], "nao_suportado_sem_qualificacao")

    def test_a_qualificacao_precisa_da_quantidade_exata(self):
        for texto in ("Microsoft.Authorization/roleAssignments=2", "Microsoft.Authorization/roleAssignments=4",
                      "Microsoft.Authorization/roleAssignments=3,Microsoft.Network/virtualNetworks=1"):
            codigo, saida, relatorio = self.sanitizar(self.cenario.whatif(), "--qualificar-nao-suportado", texto,
                                                      "--qualificar-propriedades-removidas", "Microsoft.Search/searchServices=5",
                                                      relatorio=f"r-{secrets.token_hex(3)}.json")
            self.assertEqual(codigo, CODIGO_DIVERGENCIA, texto)
            self.assertIn("qualificacao_diverge", json.dumps(relatorio))

    def test_propriedades_removidas_em_recurso_existente_tambem_exigem_qualificacao(self):
        codigo, saida, relatorio = self.sanitizar(self.cenario.whatif(), "--qualificar-nao-suportado",
                                                  "Microsoft.Authorization/roleAssignments=3")
        self.assertEqual(codigo, CODIGO_DIVERGENCIA, saida)
        self.assertEqual(relatorio["decisao"]["motivos"][0]["codigo"], "propriedade_removida_sem_qualificacao")
        self.assertIn("Microsoft.Search/searchServices=5", saida)

    def test_item_nao_suportado_sem_tipo_identificavel_nao_pode_ser_qualificado(self):
        dados = self.cenario.whatif()
        dados["changes"] = [self.cenario.mudanca("Unsupported", "[concat('a', parameters('b'))]")]
        codigo, saida, relatorio = self.sanitizar(dados, "--qualificar-nao-suportado", "Microsoft.Authorization/roleAssignments=1")
        self.assertEqual(codigo, CODIGO_DIVERGENCIA, saida)
        self.assertIn("não pode ser qualificado", saida)
        self.assertEqual(relatorio["nao_suportados"], {"<tipo-nao-identificado>": 1})

    def test_mudancas_potenciais_nao_resolvidas_impedem_o_codigo_0(self):
        dados = self.cenario.whatif()
        dados["potentialChanges"] = [self.cenario.mudanca("Modify", self.cenario.id("Microsoft.Search", "searchServices", "x"))]
        codigo, saida, relatorio = self.sanitizar(dados, *QUALIFICADO)
        self.assertEqual(codigo, CODIGO_DIVERGENCIA, saida)
        self.assertEqual(relatorio["mudancas_potenciais"], 1)
        self.assertIn("não está concluído", saida)

    def test_status_de_erro_do_arm_falha_sem_repetir_a_mensagem(self):
        for status in ("Failed", "Canceled"):
            dados = {"status": status, "changes": None, "potentialChanges": None, "diagnostics": None,
                     "error": {"code": "InvalidTemplate", "message": self.cenario.segredo + " " + self.cenario.assinatura}}
            codigo, saida, relatorio = self.sanitizar(dados, relatorio=f"{status}.json")
            self.assertEqual(codigo, CODIGO_DIVERGENCIA, saida)
            self.assertIn(status, saida)
            self.assertIn("InvalidTemplate", saida)
            for sentinela in (self.cenario.segredo, self.cenario.assinatura):
                self.assertNotIn(sentinela, saida + json.dumps(relatorio))

    def test_diagnostico_de_nivel_error_bloqueia_e_as_mensagens_sao_descartadas(self):
        dados = self.cenario.whatif()
        dados["diagnostics"] = [{"code": "NoEffect", "level": "Warning", "message": self.cenario.segredo, "target": self.cenario.nome},
                                {"code": "Falha", "level": "Error", "message": self.cenario.segredo, "target": self.cenario.nome}]
        codigo, saida, relatorio = self.sanitizar(dados, *QUALIFICADO)
        self.assertEqual(codigo, CODIGO_DIVERGENCIA, saida)
        self.assertEqual(relatorio["diagnosticos"], {"Error": 1, "Warning": 1})
        self.assertNotIn(self.cenario.segredo, saida + json.dumps(relatorio))

    def test_formas_desconhecidas_falham_sem_gravar_nada_nem_repetir_o_conteudo(self):
        base = self.cenario.whatif()
        sem_status = {chave: valor for chave, valor in base.items() if chave != "status"}
        mudanca_sem_id = {**base, "changes": [{**base["changes"][0], "resourceId": None}]}
        tipo_desconhecido = {**base, "changes": [{**base["changes"][0], "changeType": "Explodir"}]}
        id_sem_tipo = {**base, "changes": [self.cenario.mudanca("Create", f"/subscriptions/{self.cenario.assinatura}")]}
        casos = {
            "nulo": None, "lista": [1, 2], "texto": self.cenario.segredo, "sem_status": sem_status,
            "changes_nulo": {**base, "changes": None}, "changes_objeto": {**base, "changes": {"a": 1}},
            "mudanca_sem_id": mudanca_sem_id, "tipo_desconhecido": tipo_desconhecido, "id_sem_tipo": id_sem_tipo,
            "delta_invalido": {**base, "changes": [{**base["changes"][2], "delta": [{"path": 1, "propertyChangeType": "Create"}]}]},
            "potenciais_invalido": {**base, "potentialChanges": "x"},
        }
        for nome, dados in casos.items():
            with self.subTest(nome):
                relatorio = f"{nome}.json"
                codigo, saida, gravado = self.sanitizar(dados, *QUALIFICADO, relatorio=relatorio)
                self.assertEqual(codigo, CODIGO_DIVERGENCIA, saida)
                self.assertIn("não tem a forma de um what-if", saida)
                self.assertIsNone(gravado, "nada é gravado quando a forma é desconhecida")
                self.assertNotIn(self.cenario.segredo, saida)

    def test_entrada_ilegivel_ou_inexistente_e_erro_de_uso(self):
        destino = self.pasta / "r.json"
        codigo, saida = executar("--etapa", "sanitizar-whatif", "--arquivo", str(self.pasta / "nao-existe.json"), "--relatorio", str(destino))
        self.assertEqual(codigo, CODIGO_USO, saida)
        quebrado = self.pasta / "quebrado.json"
        quebrado.write_text("{ " + self.cenario.segredo, encoding="utf-8")
        codigo, saida = executar("--etapa", "sanitizar-whatif", "--arquivo", str(quebrado), "--relatorio", str(destino))
        self.assertEqual(codigo, CODIGO_USO, saida)
        self.assertIn("não contém JSON válido", saida)
        self.assertNotIn(self.cenario.segredo, saida)
        codigo, saida = executar("--etapa", "sanitizar-whatif", "--arquivo", str(quebrado))
        self.assertEqual(codigo, CODIGO_USO, saida)
        self.assertFalse(destino.exists())

    def test_arquivo_grande_demais_nao_e_lido(self):
        grande = self.pasta / "grande.json"
        grande.write_text("{}", encoding="utf-8")
        with mock.patch.object(operar_l300, "LIMITE_ARQUIVO_BYTES", 1):
            codigo, saida = executar("--etapa", "sanitizar-whatif", "--arquivo", str(grande), "--relatorio", str(self.pasta / "r.json"))
        self.assertEqual(codigo, CODIGO_USO, saida)
        self.assertIn("passa do limite", saida)

    def test_entrada_em_utf16_do_powershell_e_aceita(self):
        entrada = self.pasta / "utf16.json"
        entrada.write_bytes(json.dumps(self.cenario.whatif()).encode("utf-16"))
        codigo, saida = executar("--etapa", "sanitizar-whatif", "--arquivo", str(entrada), "--relatorio", str(self.pasta / "r.json"),
                                 *QUALIFICADO)
        self.assertEqual(codigo, CODIGO_OK, saida)

    def test_nunca_sobrescreve_um_relatorio_existente(self):
        existente = self.pasta / "relatorio.json"
        existente.write_text("ORIGINAL", encoding="utf-8")
        entrada = self.arquivo(self.cenario.whatif())
        codigo, saida = executar("--etapa", "sanitizar-whatif", "--arquivo", str(entrada), "--relatorio", str(existente), *QUALIFICADO)
        self.assertEqual(codigo, CODIGO_USO, saida)
        self.assertIn("já existe e não é sobrescrito", saida)
        self.assertEqual(existente.read_text(encoding="utf-8"), "ORIGINAL")

    def test_nome_e_rotulo_do_relatorio_tem_formato_limitado(self):
        entrada = self.arquivo(self.cenario.whatif())
        for nome in ("sem-extensao", "com espaco.json", "-comeca-com-hifen.json", "a" * 120 + ".json", "..json"):
            codigo, saida = executar("--etapa", "sanitizar-whatif", "--arquivo", str(entrada), f"--relatorio={self.pasta / nome}")
            self.assertEqual(codigo, CODIGO_USO, nome)
        for rotulo in ("tem espaco", "x" * 65, "ponto;e;virgula", "-hifen"):
            codigo, saida = executar("--etapa", "sanitizar-whatif", "--arquivo", str(entrada), "--relatorio",
                                     str(self.pasta / f"r-{secrets.token_hex(3)}.json"), f"--rotulo={rotulo}", *QUALIFICADO)
            self.assertEqual(codigo, CODIGO_USO, rotulo)
            self.assertIn("O rótulo", saida)
            self.assertNotIn(rotulo, saida)

    def test_rotulo_qualificacoes_e_plano_podem_vir_do_ambiente_do_workflow(self):
        _, _, revisado = self.sanitizar(self.cenario.whatif(), *QUALIFICADO, relatorio="a.json")
        env = {"VARELEIRA_L300_FASE": "aplicacao", "VARELEIRA_QUALIFICAR_NAO_SUPORTADO": "Microsoft.Authorization/roleAssignments=3",
               "VARELEIRA_QUALIFICAR_PROPRIEDADES_REMOVIDAS": "Microsoft.Search/searchServices=5",
               "VARELEIRA_PLANO_SHA256": revisado["conteudo_sha256"]}
        codigo, saida, relatorio = self.sanitizar(self.cenario.whatif(), env=env, relatorio="b.json")
        self.assertEqual(codigo, CODIGO_OK, saida)
        self.assertEqual(relatorio["rotulo"], "aplicacao")

    @unittest.skipIf(os.name == "nt", "as permissões POSIX não existem no Windows")
    def test_o_relatorio_e_legivel_so_pelo_dono(self):
        self.sanitizar(self.cenario.whatif(), *QUALIFICADO)
        self.assertEqual(stat.S_IMODE((self.pasta / "relatorio.json").stat().st_mode), 0o600)

    def test_o_tipo_vem_do_resource_id_ou_da_expressao_nao_resolvida(self):
        c = self.cenario
        self.assertEqual(operar_l300.tipo_do_recurso(c.id("Microsoft.Search", "searchServices", "x")), "Microsoft.Search/searchServices")
        self.assertEqual(operar_l300.tipo_do_recurso(c.id("Microsoft.Network", "virtualNetworks", "v", "subnets", "s")),
                         "Microsoft.Network/virtualNetworks/subnets")
        extensao = c.id("Microsoft.Storage", "storageAccounts", "s") + "/providers/Microsoft.Authorization/roleAssignments/" + c.principal
        self.assertEqual(operar_l300.tipo_do_recurso(extensao), "Microsoft.Authorization/roleAssignments")
        self.assertEqual(operar_l300.tipo_do_recurso(c.expressao(c.id("Microsoft.Search", "searchServices", "x"))),
                         "Microsoft.Authorization/roleAssignments")
        self.assertEqual(operar_l300.tipo_do_recurso(f"/subscriptions/{c.assinatura}/resourceGroups/{c.grupo}"),
                         "Microsoft.Resources/resourceGroups")
        for invalido in (None, "", 7, "/subscriptions/x", "[concat('a')]", "/providers/Microsoft.Search/searchServices",
                         "/providers/Microsoft.Search/searchServices/x/filhos"):
            self.assertIsNone(operar_l300.tipo_do_recurso(invalido), invalido)

    def test_literal_longo_antes_do_tipo_nao_desalinha_as_aspas_e_a_qualificacao_por_tipo_e_quantidade_vale(self):
        longo = Cenario(grupo_longo=True)
        escopo = longo.id("Microsoft.ContainerRegistry", "registries", longo.nome)
        self.assertGreater(len(escopo), 160, "o escopo passa do limite fixo de 160 caracteres que desalinhava as aspas")
        self.assertEqual(operar_l300.tipo_do_recurso(longo.expressao(escopo)), "Microsoft.Authorization/roleAssignments")
        codigo, saida, relatorio = self.sanitizar(longo.whatif(), *QUALIFICADO, "--rotulo", "rede")
        self.assertEqual(codigo, CODIGO_OK, saida)
        self.assertEqual(relatorio["nao_suportados"], {"Microsoft.Authorization/roleAssignments": 3})
        self.assertEqual(relatorio["decisao"], {"codigo": 0, "resultado": "concluido", "motivos": []})
        texto = json.dumps(relatorio, ensure_ascii=False) + saida
        self.assertNotIn(operar_l300.TIPO_NAO_IDENTIFICADO, texto)
        for sentinela in longo.sentinelas:
            self.assertNotIn(sentinela, texto)
        self.assertNotRegex(texto, operar_l300._GUID.pattern)
        codigo, saida, relatorio = self.sanitizar(longo.whatif(), "--qualificar-nao-suportado", "Microsoft.Authorization/roleAssignments=2",
                                                  "--qualificar-propriedades-removidas", "Microsoft.Search/searchServices=5",
                                                  relatorio="quantidade-errada.json")
        self.assertEqual(codigo, CODIGO_DIVERGENCIA, saida)
        self.assertIn("qualificacao_diverge", json.dumps(relatorio))

    def test_os_literais_da_expressao_seguem_as_aspas_do_arm_e_a_falha_e_fechada(self):
        tipo = "Microsoft.Authorization/roleAssignments"
        escopo = f"/subscriptions/{uuid.uuid4()}/resourceGroups/{'g' * 90}/providers/Microsoft.ContainerRegistry/registries/{'r' * 50}"
        aceitos = {
            "literais longos antes e depois do tipo": f"[extensionResourceId('{escopo}', '{tipo}', guid('{escopo}', '{uuid.uuid4()}'))]",
            "literal que termina com aspa escapada": f"[extensionResourceId('abc''', '{tipo}', guid('y'))]",
            "aspa escapada no meio de um literal": f"[extensionResourceId('o''neil', '{tipo}')]",
            "literal longo com aspas escapadas": f"[extensionResourceId('{escopo}''{escopo}''', '{tipo}')]",
        }
        for nome, expressao in aceitos.items():
            self.assertEqual(operar_l300.tipo_do_recurso(expressao), tipo, nome)
        recusados = {
            "tipo dentro de um texto com aspas escapadas": f"[concat('x'', ''{tipo}')]",
            "literal que nunca fecha, depois do tipo": f"[extensionResourceId('x', '{tipo}', guid('abc))]",
            "aspa escapada sem fechamento": f"[concat('{tipo}', 'abc'')]",
            "só o ID do escopo": f"[concat('{escopo}', parameters('b'))]",
            "tipo com texto a mais": f"[concat('{tipo} extra')]",
            "formas que não são tipo": "[concat('Microsoft.Search/search-Services', 'Microsoft.Search/1x', 'Search/x', 'Microsoft/x')]",
            "tipo longo demais": f"[concat('Microsoft.{'A' * 200}/x')]",
            "sem literais": "[parameters('x')]",
        }
        for nome, expressao in recusados.items():
            self.assertIsNone(operar_l300.tipo_do_recurso(expressao), nome)

    def test_texto_livre_com_aspas_escapadas_nao_vira_tipo_nem_permite_qualificar(self):
        dados = self.cenario.whatif()
        dados["changes"] = [self.cenario.mudanca("Unsupported", "[concat('x'', ''Microsoft.Authorization/roleAssignments')]")]
        codigo, saida, relatorio = self.sanitizar(dados, "--qualificar-nao-suportado", "Microsoft.Authorization/roleAssignments=1")
        self.assertEqual(codigo, CODIGO_DIVERGENCIA, saida)
        self.assertIn("não pode ser qualificado", saida)
        self.assertEqual(relatorio["nao_suportados"], {operar_l300.TIPO_NAO_IDENTIFICADO: 1})


class VerificarAmbienteTests(unittest.TestCase):
    NOME = operar_l300.AMBIENTE_GITHUB

    def aprovacoes(self, usuario="login-de-teste", estado="approved", ambiente=None):
        return [{"state": estado, "comment": "", "user": {"login": usuario}, "environments": [{"name": ambiente or self.NOME}]}]

    def ambiente(self, revisores=1, politica=True, autoaprovacao=True, **extras):
        regras = [{"type": "branch_policy"}]
        if revisores:
            regras.append({"type": "required_reviewers", "prevent_self_review": autoaprovacao,
                           "reviewers": [{"type": "User", "reviewer": {"login": f"r{i}"}} for i in range(revisores)]})
        return {"name": self.NOME, "protection_rules": regras, "can_admins_bypass": False,
                "deployment_branch_policy": {"protected_branches": False, "custom_branch_policies": True} if politica else None, **extras}

    def test_aprovacao_registrada_e_regras_comprovam_a_protecao(self):
        resultado = operar_l300.avaliar_ambiente(self.aprovacoes(), self.ambiente())
        self.assertEqual((resultado["estado"], resultado["motivos"]), ("comprovado", []))

    def test_uma_evidencia_so_nao_comprova_e_a_que_falta_bloqueia_com_motivo_explicito(self):
        so_aprovacao = operar_l300.avaliar_ambiente(self.aprovacoes(), None)
        self.assertEqual(so_aprovacao["estado"], "reprovado")
        self.assertEqual(so_aprovacao["regras"], "indisponivel")
        self.assertTrue(any("regras do ambiente não puderam ser lidas" in motivo for motivo in so_aprovacao["motivos"]))
        so_regras = operar_l300.avaliar_ambiente(None, self.ambiente())
        self.assertEqual(so_regras["estado"], "reprovado")
        self.assertEqual(so_regras["aprovacoes"], "indisponivel")
        self.assertTrue(any("aprovações desta execução não puderam ser lidas" in motivo for motivo in so_regras["motivos"]))

    def test_ambiente_criado_automaticamente_sem_regras_e_reprovado(self):
        recem_criado = {"name": self.NOME, "protection_rules": [], "deployment_branch_policy": None}
        for aprovacoes in (None, []):
            resultado = operar_l300.avaliar_ambiente(aprovacoes, recem_criado)
            self.assertEqual(resultado["estado"], "reprovado")
            self.assertTrue(any("sem regras" in motivo for motivo in resultado["motivos"]))

    def test_lista_vazia_de_aprovacoes_e_evidencia_contraria(self):
        resultado = operar_l300.avaliar_ambiente([], self.ambiente())
        self.assertEqual(resultado["estado"], "reprovado")
        self.assertTrue(any("nenhuma aprovação humana" in motivo for motivo in resultado["motivos"]))

    def test_ambiente_sem_revisores_ou_que_aceita_qualquer_branch_e_reprovado_mesmo_com_aprovacao_registrada(self):
        sem_revisores = operar_l300.avaliar_ambiente(self.aprovacoes(), self.ambiente(revisores=0))
        self.assertEqual(sem_revisores["estado"], "reprovado")
        self.assertTrue(any("não tem revisores obrigatórios" in motivo for motivo in sem_revisores["motivos"]))
        sem_politica = operar_l300.avaliar_ambiente(self.aprovacoes(), self.ambiente(politica=False))
        self.assertEqual(sem_politica["estado"], "reprovado")
        self.assertTrue(any("qualquer branch" in motivo for motivo in sem_politica["motivos"]))

    def test_a_politica_de_branches_precisa_restringir_de_verdade(self):
        for politica in ({}, {"protected_branches": False, "custom_branch_policies": False}, [], "x"):
            resultado = operar_l300.avaliar_ambiente(self.aprovacoes(), {**self.ambiente(), "deployment_branch_policy": politica})
            self.assertEqual(resultado["estado"], "reprovado", politica)
            self.assertFalse(resultado["detalhes_das_regras"]["restringe_branches"])
        for politica in ({"protected_branches": True, "custom_branch_policies": False},
                         {"protected_branches": False, "custom_branch_policies": True}):
            resultado = operar_l300.avaliar_ambiente(self.aprovacoes(), {**self.ambiente(), "deployment_branch_policy": politica})
            self.assertEqual(resultado["estado"], "comprovado", politica)

    def test_sem_evidencia_utilizavel_bloqueia_explicitamente_e_nao_existe_atestacao(self):
        erro_da_api = {"message": "Resource not accessible by integration", "status": "403"}
        for aprovacoes, ambiente in ((None, None), (erro_da_api, erro_da_api), ("texto", []), ([], {"name": self.NOME})):
            resultado = operar_l300.avaliar_ambiente(aprovacoes, ambiente)
            self.assertEqual(resultado["estado"], "reprovado", (aprovacoes, ambiente))
            self.assertGreaterEqual(len(resultado["motivos"]), 2, "cada evidência que falta é um motivo explícito")
            self.assertFalse(any("VARELEIRA_AMBIENTE_APROVADO" in motivo or "atestação" in motivo for motivo in resultado["motivos"]))
            self.assertEqual(resultado["avisos"], [], "avisos só existem quando há prova real")
        assinatura = inspect.signature(operar_l300.avaliar_ambiente)
        self.assertEqual(set(assinatura.parameters), {"aprovacoes", "ambiente", "nome", "ator"}, "não há parâmetro de atestação")
        self.assertFalse(hasattr(operar_l300, "VAR_AMBIENTE_APROVADO"))

    def test_resposta_de_outro_ambiente_nao_conta_como_evidencia(self):
        resultado = operar_l300.avaliar_ambiente(self.aprovacoes(ambiente="outro"), {**self.ambiente(), "name": "outro"})
        self.assertEqual(resultado["estado"], "reprovado")

    def test_avisos_de_autoaprovacao_e_de_bypass_de_administradores(self):
        resultado = operar_l300.avaliar_ambiente(self.aprovacoes("EU"), self.ambiente(autoaprovacao=False, can_admins_bypass=True),
                                                 ator="eu")
        self.assertEqual(resultado["estado"], "comprovado")
        textos = " ".join(resultado["avisos"])
        self.assertIn("prevent_self_review desligado", textos)
        self.assertIn("veio de quem disparou", textos)
        self.assertIn("can_admins_bypass", textos)

    def test_pela_linha_de_comando_o_login_so_e_liberado_com_a_prova_completa(self):
        with tempfile.TemporaryDirectory() as pasta:
            pasta = Path(pasta)

            def gravar(nome: str, dado, bruto: bool = False) -> str:
                (pasta / nome).write_text(dado if bruto else json.dumps(dado), encoding="utf-8")
                return str(pasta / nome)

            aprovacoes, ambiente = gravar("aprovacoes.json", self.aprovacoes()), gravar("ambiente.json", self.ambiente())
            codigo, saida = executar("--etapa", "verificar-ambiente", "--aprovacoes", aprovacoes, "--ambiente", ambiente, "--ator", "alguem")
            self.assertEqual(codigo, CODIGO_OK, saida)
            self.assertIn("PROTEÇÃO COMPROVADA", saida)
            self.assertNotIn("login-de-teste", saida, "nomes de usuários não são repetidos")
            erro = gravar("erro.json", {"message": "Not Found", "status": "404"})
            sem_regras = gravar("sem-regras.json", {"name": self.NOME, "protection_rules": []})
            ilegivel = gravar("ilegivel.json", "{", bruto=True)
            incompleto = gravar("incompleto.json", {"name": self.NOME})
            vazias = gravar("vazias.json", [])
            sem_revisores = gravar("sem-revisores.json", self.ambiente(revisores=0))
            sem_politica = gravar("sem-politica.json", self.ambiente(politica=False))
            ausente = str(pasta / "nao-existe.json")
            bloqueios = {
                "aprovações e regras com erro da API": (erro, erro),
                "regras sem revisores nem aprovações": (erro, sem_regras),
                "só as aprovações (regras ausentes)": (aprovacoes, ausente),
                "só as regras (aprovações ausentes)": (ausente, ambiente),
                "aprovações ilegíveis": (ilegivel, ambiente),
                "regras ilegíveis": (aprovacoes, ilegivel),
                "regras incompletas": (aprovacoes, incompleto),
                "regras com erro 404": (aprovacoes, erro),
                "sem aprovação registrada": (vazias, ambiente),
                "sem revisores obrigatórios": (aprovacoes, sem_revisores),
                "qualquer branch": (aprovacoes, sem_politica),
                "nada informado": (None, None),
            }
            for descricao, (arq_aprovacoes, arq_ambiente) in bloqueios.items():
                for env in ({}, {"VARELEIRA_AMBIENTE_APROVADO": "true"}, {"VARELEIRA_AMBIENTE_APROVADO": "sim"}):
                    with self.subTest(descricao, env=env):
                        argumentos = ["--etapa", "verificar-ambiente"]
                        if arq_aprovacoes:
                            argumentos += ["--aprovacoes", arq_aprovacoes]
                        if arq_ambiente:
                            argumentos += ["--ambiente", arq_ambiente]
                        codigo, saida = executar(*argumentos, env=env)
                        self.assertEqual(codigo, CODIGO_DIVERGENCIA, saida)
                        self.assertIn("o login no Azure não será tentado", saida)
                        self.assertIn("nenhuma atestação substitui essa prova", saida)
                        self.assertNotIn("COMPROVADA pelo GitHub", saida)
                        self.assertNotIn("VARELEIRA_AMBIENTE_APROVADO", saida, "a variável antiga nem é citada: nada a lê")

    def test_nome_do_ambiente_tem_formato_limitado(self):
        codigo, saida = executar("--etapa", "verificar-ambiente", "--nome-ambiente", "a b;c")
        self.assertEqual(codigo, CODIGO_USO, saida)


def descritor(**alteracoes) -> dict:
    base = {
        "versao": 1, "origem": "simulado",
        "dns_privado": {"armazenamento": True, "busca": True, "modelos": True},
        "spl_busca": {"armazenamento": "aprovado", "modelos": "aprovado"},
        "aplicacao": {"prontidao_http": 200, "revisao_ativa": True, "consulta_respondida": True},
        "ingestao": {"indice": "vareleira-lar-l300", "ambiente_de_execucao": "private", "ultima_execucao": "success",
                     "itens_processados": 3, "itens_com_falha": 0},
        "acesso_privado": {d: {"positiva": True, "negativa": None} for d in ("armazenamento", "busca", "modelos")},
    }
    base.update(alteracoes)
    return base


def ingestao(**alteracoes) -> dict:
    return {**descritor()["ingestao"], **alteracoes}


class ConferirTests(unittest.TestCase):
    def test_descritor_completo_antes_de_isolar_nao_exige_a_prova_negativa_e_nao_afirma_seguranca(self):
        resultado = operar_l300.conferir_descritor(descritor(), "antes-de-isolar")
        self.assertEqual(resultado["resultado"], "completo")
        self.assertEqual(resultado["contagem"]["nao_exigida_agora"], 3)
        self.assertIn("NÃO é uma prova de segurança", resultado["limite"])
        self.assertTrue(all(item["origem"] == "descritor do operador" for item in resultado["verificacoes"]))

    def test_depois_de_isolar_a_prova_negativa_e_exigida(self):
        resultado = operar_l300.conferir_descritor(descritor(), "depois-de-isolar")
        self.assertEqual(resultado["resultado"], "incompleto")
        pendentes = {item["id"] for item in resultado["verificacoes"] if item["estado"] == "pendente"}
        self.assertEqual(pendentes, {f"acesso_privado.{d}.negativa" for d in ("armazenamento", "busca", "modelos")})
        completo = descritor(acesso_privado={d: {"positiva": True, "negativa": True} for d in ("armazenamento", "busca", "modelos")})
        self.assertEqual(operar_l300.conferir_descritor(completo, "depois-de-isolar")["resultado"], "completo")

    def test_so_a_prontidao_http_200_e_o_login_publico_200_nao_validam_nada(self):
        so_a_aplicacao = {"versao": 1, "origem": "operador", "aplicacao": {"prontidao_http": 200, "revisao_ativa": True,
                                                                           "login_publico_http": 200}}
        resultado = operar_l300.conferir_descritor(so_a_aplicacao, "antes-de-isolar")
        self.assertEqual(resultado["resultado"], "incompleto")
        estados = {item["id"]: item["estado"] for item in resultado["verificacoes"]}
        self.assertEqual(estados["aplicacao.prontidao_http"], "atendido")
        self.assertEqual(estados["aplicacao.consulta_respondida"], "pendente", "estar de pé não é responder uma pergunta")
        for dependencia in ("armazenamento", "busca", "modelos"):
            self.assertEqual(estados[f"dns_privado.{dependencia}"], "pendente")
            self.assertEqual(estados[f"acesso_privado.{dependencia}.positiva"], "pendente")
        self.assertEqual(estados["ingestao.ultima_execucao"], "pendente")
        self.assertEqual(estados["ingestao.ambiente_de_execucao"], "pendente")
        self.assertTrue(any("IGNORADO" in aviso for aviso in resultado["avisos"]))

    def test_cada_lacuna_ou_contradicao_reprova_com_o_item_exato(self):
        casos = {
            "dns_privado.busca": descritor(dns_privado={"armazenamento": True, "busca": False, "modelos": True}),
            "spl_busca.modelos": descritor(spl_busca={"armazenamento": "aprovado", "modelos": "pendente"}),
            "spl_busca.armazenamento": descritor(spl_busca={"armazenamento": "rejeitado", "modelos": "aprovado"}),
            "aplicacao.prontidao_http": descritor(aplicacao={"prontidao_http": 503, "revisao_ativa": True, "consulta_respondida": True}),
            "aplicacao.consulta_respondida": descritor(aplicacao={"prontidao_http": 200, "revisao_ativa": True}),
            "ingestao.indice": descritor(ingestao=ingestao(indice="vareleira-lar-l200")),
            "ingestao.ambiente_de_execucao": descritor(ingestao=ingestao(ambiente_de_execucao="standard")),
            "ingestao.ultima_execucao": descritor(ingestao=ingestao(ultima_execucao="error")),
            "ingestao.itens_processados": descritor(ingestao=ingestao(itens_processados=0)),
            "ingestao.itens_com_falha": descritor(ingestao=ingestao(itens_com_falha=1)),
            "acesso_privado.modelos.positiva": descritor(acesso_privado={
                "armazenamento": {"positiva": True}, "busca": {"positiva": True}, "modelos": {"positiva": False}}),
        }
        for item, dados in casos.items():
            with self.subTest(item):
                resultado = operar_l300.conferir_descritor(dados, "antes-de-isolar")
                estados = {v["id"]: v["estado"] for v in resultado["verificacoes"]}
                self.assertNotEqual(estados[item], "atendido")
                self.assertNotEqual(resultado["resultado"], "completo")

    def test_o_indexador_no_ambiente_padrao_nao_prova_o_caminho_privado(self):
        resultado = operar_l300.conferir_descritor(descritor(ingestao=ingestao(ambiente_de_execucao="standard")), "antes-de-isolar")
        estados = {v["id"]: v["estado"] for v in resultado["verificacoes"]}
        self.assertEqual(estados["ingestao.ambiente_de_execucao"], "reprovado")
        self.assertEqual(resultado["resultado"], "reprovado")

    def test_formas_invalidas_sao_erro_de_uso_sem_repetir_os_valores(self):
        sentinela = "SENTINELA-" + secrets.token_hex(8)
        invalidos = [
            [], {"versao": 2, "origem": "operador"}, {"versao": 1, "origem": "qualquer"},
            descritor(dns_privado={"armazenamento": "true"}), descritor(dns_privado=[1]), descritor(extra=1),
            descritor(dns_privado={"armazenamento": True, sentinela: True}),
            descritor(aplicacao={"prontidao_http": "200"}), descritor(aplicacao={"prontidao_http": True}),
            descritor(aplicacao={"consulta_respondida": "sim"}),
            descritor(ingestao={"itens_processados": -1}), descritor(ingestao={"ultima_execucao": "com espaco " + sentinela}),
            descritor(ingestao={"ambiente_de_execucao": "com espaco " + sentinela}),
            descritor(spl_busca={"armazenamento": "talvez"}), descritor(acesso_privado={"busca": "sim"}),
            descritor(acesso_privado={"busca": {"positiva": "sim", "outra": True}}),
        ]
        for dados in invalidos:
            with self.assertRaises(operar_l300.ErroLab) as contexto:
                operar_l300.conferir_descritor(dados, "antes-de-isolar")
            self.assertNotIn(sentinela, str(contexto.exception))

    def test_linha_de_comando_devolve_3_para_incompleto_e_0_para_completo_e_grava_relatorio_novo(self):
        with tempfile.TemporaryDirectory() as pasta:
            pasta = Path(pasta)
            (pasta / "completo.json").write_text(json.dumps(descritor()), encoding="utf-8")
            incompleto = descritor(dns_privado={"armazenamento": True})
            (pasta / "incompleto.json").write_text(json.dumps(incompleto), encoding="utf-8")
            codigo, saida = executar("--etapa", "conferir", "--descritor", str(pasta / "completo.json"),
                                     "--relatorio", str(pasta / "matriz.json"))
            self.assertEqual(codigo, CODIGO_OK, saida)
            self.assertIn("NÃO é uma prova de segurança", saida)
            self.assertEqual(json.loads((pasta / "matriz.json").read_text(encoding="utf-8"))["resultado"], "completo")
            codigo, saida = executar("--etapa", "conferir", "--descritor", str(pasta / "completo.json"),
                                     "--relatorio", str(pasta / "matriz.json"))
            self.assertEqual(codigo, CODIGO_USO, saida)
            codigo, saida = executar("--etapa", "conferir", "--descritor", str(pasta / "incompleto.json"))
            self.assertEqual(codigo, CODIGO_DIVERGENCIA, saida)
            self.assertIn("NÃO pode ser considerada validada", saida)
            codigo, saida = executar("--etapa", "conferir", "--descritor", str(pasta / "completo.json"), "--momento", "depois-de-isolar")
            self.assertEqual(codigo, CODIGO_DIVERGENCIA, saida)


def linha_do_servidor(rota="perguntar", status=200, ms=100, causa=None, nivel=None, tempo=True) -> str:
    prefixo = "2026-10-10 13:45:20,982 " if tempo else ""
    nivel = nivel or ("WARNING" if status >= 500 else "INFO")
    sufixo = f" causa={causa}" if causa else ""
    return f"{prefixo}{nivel} vareleira.chat requisicao id={secrets.token_hex(16)} rota={rota} status={status} ms={ms}{sufixo}"


def envelope(texto: str) -> str:
    return json.dumps({"TimeStamp": "2026-10-10T13:43:33.1310949+00:00", "Log": "F " + texto})


class ResumirLogsTests(unittest.TestCase):
    PARTIDA = [
        json.dumps({"TimeStamp": "2026-10-10T13:48:25.0661", "Log": "Connecting to the container 'chat'..."}),
        json.dumps({"TimeStamp": "2026-10-10T13:48:25.106", "Log": "Successfully Connected to container: 'chat' "
                    "[Revision: 'ca-x--abc', Replica: 'ca-x--abc-8448d784fb-kf94v']"}),
        envelope("Chat do Vareleira Lar, autenticação exigida: a identidade do Azure Container Apps é conferida contra o tenant autorizado."),
        envelope("Endereço: http://0.0.0.0:8000  (encerre com Ctrl+C)"),
        envelope("2026-10-10 13:43:24,029 INFO uvicorn.error Started server process [1]"),
        envelope("2026-10-10 13:43:24,648 INFO vareleira.chat assistente pronto modo=nuvem autenticacao=sim indice=vareleira-lar-l300 "
                 "deployment_embeddings=embeddings dimensoes=1536 deployment_geracao=geracao esforco=low modo_busca=hibrida k=3 "
                 "concorrencia=4 tempo=90s"),
        envelope("2026-10-10 13:43:24,650 INFO uvicorn.error Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)"),
    ]

    def test_conta_status_rotas_latencia_e_causas(self):
        linhas = [*self.PARTIDA]
        linhas += [envelope(linha_do_servidor("perguntar", 200, ms, tempo=True)) for ms in range(10, 101, 10)]
        linhas += [linha_do_servidor("perguntar", 503, 5000, causa="resposta_descartada"),
                   linha_do_servidor("perguntar", 503, 4000, causa="resposta_descartada"),
                   linha_do_servidor("perguntar", 503, 3000),
                   linha_do_servidor("perguntar", 401, 1, causa="nao_autenticado", tempo=False),
                   linha_do_servidor("saude", 200, 1), linha_do_servidor("saude", 200, 0), linha_do_servidor("prontidao", 503, 2, causa="nao_pronto"),
                   "", "   "]
        resumo = operar_l300.resumir_logs(linhas)
        self.assertEqual(resumo["decisao"]["codigo"], CODIGO_OK)
        self.assertEqual(resumo["linhas"]["desconhecidas"], 0)
        self.assertEqual(resumo["linhas"]["vazias"], 2)
        self.assertEqual(resumo["linhas"]["ignoradas_conhecidas"], {"ciclo_do_servidor": 2, "partida": 3, "plataforma": 2})
        self.assertEqual(resumo["requisicoes"], {"total": 17, "sondas_de_saude": {"prontidao": 1, "saude": 2}, "de_usuario": 14})
        self.assertEqual(resumo["por_status"], {"200": 12, "401": 1, "503": 4})
        self.assertEqual(resumo["por_classe"], {"2xx": 12, "4xx": 1, "5xx": 4})
        self.assertEqual(resumo["causas_por_status"]["503"], {"nao_pronto": 1, "resposta_descartada": 2, "sem_causa": 1})
        self.assertEqual(resumo["causas_por_status"]["401"], {"nao_autenticado": 1})
        perguntar = resumo["por_rota"]["perguntar"]
        self.assertEqual(perguntar["total"], 14)
        self.assertEqual(perguntar["latencia_ms"], {"minimo": 1, "p50": 60, "p95": 5000, "maximo": 5000, "media": 896})
        self.assertEqual(resumo["taxa_5xx_de_usuario"], round(3 / 14, 4))

    def test_a_503_sem_causa_conhecida_nao_e_escondida(self):
        resumo = operar_l300.resumir_logs([linha_do_servidor("perguntar", 503, 10)])
        self.assertEqual(resumo["causas_por_status"], {"503": {"sem_causa": 1}})

    def test_linha_desconhecida_falha_fechada_sem_repetir_o_texto(self):
        pergunta = "Qual a franquia do seguro? " + secrets.token_hex(6)
        linhas = [linha_do_servidor(), f"pergunta={pergunta}", linha_do_servidor() + f" pergunta={pergunta}",
                  envelope("WARNING uvicorn.error Invalid HTTP request received."), "{ nao e json", "P pedaço de linha longa",
                  json.dumps({"mensagem": pergunta})]
        resumo = operar_l300.resumir_logs(linhas)
        self.assertEqual(resumo["linhas"]["desconhecidas"], 6)
        self.assertEqual(resumo["linhas"]["primeiras_desconhecidas"], [2, 3, 4, 5, 6, 7])
        self.assertEqual(resumo["decisao"]["codigo"], CODIGO_DIVERGENCIA)
        self.assertEqual(resumo["requisicoes"]["total"], 1, "a linha conhecida ainda é contada")
        self.assertNotIn(pergunta, json.dumps(resumo, ensure_ascii=False))

    def test_linha_gigante_e_desconhecida(self):
        resumo = operar_l300.resumir_logs([linha_do_servidor() + " " * (operar_l300.LIMITE_LINHA_DE_LOG + 1)])
        self.assertEqual(resumo["linhas"]["desconhecidas"], 1)

    def test_a_saida_so_tem_contagens_nunca_perguntas_respostas_tokens_ou_urls(self):
        segredos = ["Bearer " + secrets.token_hex(10), "https://" + secrets.token_hex(4) + ".example.invalid/api", "pergunta-" + secrets.token_hex(6)]
        linhas = [*self.PARTIDA, linha_do_servidor("perguntar", 200, 5), f"{segredos[0]} {segredos[1]} {segredos[2]}"]
        with tempfile.TemporaryDirectory() as pasta:
            origem, destino = Path(pasta) / "logs.txt", Path(pasta) / "resumo.json"
            origem.write_text("\n".join(linhas), encoding="utf-8")
            codigo, saida = executar("--etapa", "resumir-logs", "--logs", str(origem), "--relatorio", str(destino))
            relatorio = destino.read_text(encoding="utf-8")
        self.assertEqual(codigo, CODIGO_DIVERGENCIA, saida)
        self.assertIn("falha fechado", saida)
        for segredo in segredos:
            self.assertNotIn(segredo, saida + relatorio)
        for trecho in ("http://", "https://", "Replica", "Revision", "vareleira-lar", "deployment_"):
            self.assertNotIn(trecho, saida + relatorio, "nem as linhas conhecidas e ignoradas são copiadas")

    def test_linha_de_comando_com_arquivo_limpo_conclui_com_codigo_0(self):
        with tempfile.TemporaryDirectory() as pasta:
            origem = Path(pasta) / "logs.txt"
            origem.write_text("\r\n".join([*self.PARTIDA, linha_do_servidor("perguntar", 200, 7), linha_do_servidor("saude", 200, 1)]) + "\r\n",
                              encoding="utf-8")
            codigo, saida = executar("--etapa", "resumir-logs", "--logs", str(origem))
        self.assertEqual(codigo, CODIGO_OK, saida)
        self.assertIn("todas as linhas foram reconhecidas", saida)
        self.assertIn("sondas de saúde: saude=1", saida)

    def test_arquivo_de_logs_ausente_ou_com_codificacao_invalida_e_erro_de_uso(self):
        with tempfile.TemporaryDirectory() as pasta:
            codigo, _ = executar("--etapa", "resumir-logs", "--logs", str(Path(pasta) / "nada.txt"))
            self.assertEqual(codigo, CODIGO_USO)
            binario = Path(pasta) / "bin.txt"
            binario.write_bytes(b"\x80\x81\x82")
            codigo, saida = executar("--etapa", "resumir-logs", "--logs", str(binario))
            self.assertEqual(codigo, CODIGO_USO, saida)
            codigo, saida = executar("--etapa", "resumir-logs")
            self.assertEqual(codigo, CODIGO_USO, saida)

    def test_e_somente_leitura_do_arquivo_de_origem(self):
        with tempfile.TemporaryDirectory() as pasta:
            origem = Path(pasta) / "logs.txt"
            origem.write_text(linha_do_servidor() + "\n", encoding="utf-8")
            antes = origem.read_bytes()
            executar("--etapa", "resumir-logs", "--logs", str(origem))
            self.assertEqual(origem.read_bytes(), antes)
            self.assertEqual([p.name for p in Path(pasta).iterdir()], ["logs.txt"])


DESTINOS_DO_BICEPPARAM = ("VARELEIRA_NOME_REGISTRO", "VARELEIRA_NOME_IDENTIDADE_APLICACAO", "VARELEIRA_NOME_WORKSPACE_LOGS",
                          "VARELEIRA_ID_OBJETO_CARGA")
CONFIGURACAO_DO_ISOLAMENTO = ("VARELEIRA_SKU_ARMAZENAMENTO", "VARELEIRA_SKU_BUSCA", "VARELEIRA_REPLICAS_BUSCA",
                              "VARELEIRA_PARTICOES_BUSCA")


def validar_na_implantacao(fase: str, *, remover: tuple[str, ...] = (), alterar: dict[str, str] | None = None,
                           argumentos: tuple[str, ...] = ("--exigir-github", "--exigir-oidc", "--exigir-azure"),
                           **env_extra: str) -> tuple[int, str, dict[str, str]]:
    """Roda `validar` como o passo do workflow, com as vars da fase removidas ou alteradas e o ambiente do passo ajustado."""
    variaveis = {**variaveis_do_ambiente(fase), **(alterar or {})}
    for nome in remover:
        variaveis.pop(nome, None)
    portoes = {"VARELEIRA_TAG_IMAGEM": "v1.2.3"} if fase == "aplicacao" else {}
    if fase == "isolar":
        portoes["VARELEIRA_L300_CONECTIVIDADE_PRIVADA_VALIDADA"] = "true"
    env = ambiente_de_implantacao(VARELEIRA_L300_FASE=fase, VARELEIRA_VARS_JSON=json.dumps(variaveis), **portoes, **env_extra)
    codigo, saida = executar("--etapa", "validar", *argumentos, env=env)
    return codigo, saida, env


class DestinosDoBicepparamTests(unittest.TestCase):
    """Tudo que o infra/levels/l300.bicepparam exige é conferido ANTES do what-if, com mensagens que só citam nomes."""

    def test_a_implantacao_completa_de_cada_fase_e_aceita(self):
        for fase in operar_l300.FASES:
            codigo, saida, _ = validar_na_implantacao(fase)
            self.assertEqual(codigo, CODIGO_OK, f"{fase}: {saida}")

    def test_cada_destino_obrigatorio_do_bicepparam_e_exigido_em_todas_as_fases(self):
        for fase in operar_l300.FASES:
            for nome in DESTINOS_DO_BICEPPARAM:
                with self.subTest(fase=fase, nome=nome):
                    codigo, saida, _ = validar_na_implantacao(fase, remover=(nome,))
                    self.assertEqual(codigo, CODIGO_USO, saida)
                    self.assertIn(nome, saida)
                    self.assertIn("sem valores padrão", saida)

    def test_o_formato_de_cada_destino_e_conferido_sem_repetir_o_valor(self):
        sentinela = "Sentinela" + secrets.token_hex(8)
        invalidos = {
            "VARELEIRA_NOME_REGISTRO": "reg-" + sentinela,
            "VARELEIRA_NOME_IDENTIDADE_APLICACAO": "id com espaco " + sentinela,
            "VARELEIRA_NOME_WORKSPACE_LOGS": "-" + sentinela,
            "VARELEIRA_ID_OBJETO_CARGA": "nao-e-guid-" + sentinela,
        }
        for nome, valor in invalidos.items():
            with self.subTest(nome=nome):
                codigo, saida, _ = validar_na_implantacao("rede", alterar={nome: valor})
                self.assertEqual(codigo, CODIGO_USO, saida)
                self.assertIn(f"{nome}: formato inválido", saida)
                self.assertNotIn(sentinela, saida)

    def test_os_limites_de_tamanho_dos_destinos_novos_sao_os_do_bicep(self):
        limites = {
            "VARELEIRA_NOME_REGISTRO": (("abcd", "a" * 51), ("abcde", "a" * 50)),
            "VARELEIRA_NOME_IDENTIDADE_APLICACAO": (("ab", "a" * 129), ("abc", "a" * 128)),
            "VARELEIRA_NOME_WORKSPACE_LOGS": (("abc", "a" * 64, "abcd-"), ("abcd", "a" * 63, "a-b-c")),
            "VARELEIRA_ID_OBJETO_CARGA": ((str(uuid.uuid4())[:-1], str(uuid.uuid4()) + "0"), (str(uuid.uuid4()),)),
        }
        for nome, (recusados, aceitos) in limites.items():
            for valor in recusados:
                codigo, saida, _ = validar_na_implantacao("rede", alterar={nome: valor})
                self.assertEqual(codigo, CODIGO_USO, f"{nome} deveria recusar {len(valor)} caracteres")
                self.assertIn(nome, saida)
            for valor in aceitos:
                codigo, saida, _ = validar_na_implantacao("rede", alterar={nome: valor})
                self.assertEqual(codigo, CODIGO_OK, f"{nome} deveria aceitar {len(valor)} caracteres: {saida}")

    def test_isolar_exige_a_configuracao_atual_dos_servicos_de_dados_e_as_outras_fases_nao(self):
        for nome in CONFIGURACAO_DO_ISOLAMENTO:
            codigo, saida, _ = validar_na_implantacao("isolar", remover=(nome,))
            self.assertEqual(codigo, CODIGO_USO, saida)
            self.assertIn(nome, saida)
            self.assertIn("configuração ATUAL dos serviços de dados", saida)
            self.assertIn("sem valores padrão", saida)
        for fase in ("rede", "aplicacao"):
            codigo, saida, env = validar_na_implantacao(fase)
            self.assertEqual(codigo, CODIGO_OK, saida)
            self.assertFalse(set(CONFIGURACAO_DO_ISOLAMENTO) & set(json.loads(env["VARELEIRA_VARS_JSON"])))

    def test_isolar_recusa_o_que_o_modulo_de_isolamento_nao_aceita(self):
        invalidos = {
            "VARELEIRA_SKU_ARMAZENAMENTO": ("Premium_LRS", "standard_lrs", "Standard_RAGRS", "LRS"),
            "VARELEIRA_SKU_BUSCA": ("free", "Basic", "storage_optimized_l1"),
            "VARELEIRA_REPLICAS_BUSCA": ("0", "13", "abc", "-1", "01"),
            "VARELEIRA_PARTICOES_BUSCA": ("0", "5", "7", "24", "abc"),
        }
        validos = {
            "VARELEIRA_SKU_ARMAZENAMENTO": ("Standard_LRS", "Standard_ZRS", "Standard_GRS"),
            "VARELEIRA_SKU_BUSCA": ("basic", "standard"),
            "VARELEIRA_REPLICAS_BUSCA": ("1", "7", "12"),
            "VARELEIRA_PARTICOES_BUSCA": ("1", "2", "3", "4", "6", "12"),
        }
        for nome, valores in invalidos.items():
            for valor in valores:
                codigo, saida, _ = validar_na_implantacao("isolar", alterar={nome: valor})
                self.assertEqual(codigo, CODIGO_USO, f"{nome}={valor}: {saida}")
                self.assertIn(f"{nome}: formato inválido", saida)
        for nome, valores in validos.items():
            for valor in valores:
                codigo, saida, _ = validar_na_implantacao("isolar", alterar={nome: valor})
                self.assertEqual(codigo, CODIGO_OK, f"{nome}={valor}: {saida}")

    def test_replicas_e_particoes_so_aceitam_inteiros_em_qualquer_fase_porque_o_bicepparam_usa_int(self):
        for fase in ("rede", "aplicacao"):
            for nome in ("VARELEIRA_REPLICAS_BUSCA", "VARELEIRA_PARTICOES_BUSCA"):
                codigo, saida, _ = validar_na_implantacao(fase, alterar={nome: "muitas"})
                self.assertEqual(codigo, CODIGO_USO, saida)
                self.assertIn(nome, saida)
                self.assertIn("int()", saida)
                codigo, saida, _ = validar_na_implantacao(fase, alterar={nome: "0"})
                self.assertEqual(codigo, CODIGO_OK, f"zero é o padrão do bicepparam ('não informado'): {saida}")

    def test_regioes_sao_opcionais_mas_conferidas_e_isolar_avisa_quando_nao_vem_nenhuma(self):
        codigo, saida, _ = validar_na_implantacao("isolar")
        self.assertEqual(codigo, CODIGO_OK, saida)
        self.assertIn("[AVISO] Regiões dos serviços de dados não informadas", saida)
        codigo, saida, _ = validar_na_implantacao("isolar", alterar={nome: "brazilsouth" for nome in operar_l300.VARS_DE_REGIAO})
        self.assertEqual(codigo, CODIGO_OK, saida)
        self.assertNotIn("Regiões dos serviços de dados não informadas", saida)
        for nome in operar_l300.VARS_DE_REGIAO:
            codigo, saida, _ = validar_na_implantacao("rede", alterar={nome: "Brazil South"})
            self.assertEqual(codigo, CODIGO_USO, saida)
            self.assertIn(f"{nome}: formato inválido", saida)
            self.assertNotIn("Brazil South", saida)

    def test_aplicacao_exige_o_registro_de_login_e_diz_que_nao_e_a_identidade_de_implantacao(self):
        for nome in ("VARELEIRA_ID_APLICACAO_LOGIN", "VARELEIRA_ID_TENANT_LOGIN"):
            codigo, saida, _ = validar_na_implantacao("aplicacao", remover=(nome,))
            self.assertEqual(codigo, CODIGO_USO, saida)
            self.assertIn(nome, saida)
            self.assertIn("login da aplicação", saida)
            self.assertIn("NÃO é a identidade de implantação (OIDC)", saida)
        sentinela = "Sentinela" + secrets.token_hex(8)
        for nome in ("VARELEIRA_ID_APLICACAO_LOGIN", "VARELEIRA_ID_TENANT_LOGIN"):
            codigo, saida, _ = validar_na_implantacao("aplicacao", alterar={nome: "nao-e-guid-" + sentinela})
            self.assertEqual(codigo, CODIGO_USO, saida)
            self.assertIn(f"{nome}: formato inválido", saida)
            self.assertNotIn(sentinela, saida)
        for fase in ("rede", "isolar"):
            codigo, saida, env = validar_na_implantacao(fase)
            self.assertEqual(codigo, CODIGO_OK, saida)
            self.assertNotIn("VARELEIRA_ID_APLICACAO_LOGIN", env["VARELEIRA_VARS_JSON"])

    def test_o_registro_de_login_nunca_pode_ser_a_identidade_de_implantacao(self):
        variaveis = variaveis_do_ambiente("aplicacao")
        for transformar in (str, str.upper):
            igual = {**variaveis, "VARELEIRA_ID_APLICACAO_LOGIN": transformar(variaveis["AZURE_CLIENT_ID"])}
            codigo, saida, _ = validar_na_implantacao("aplicacao", alterar=igual)
            self.assertEqual(codigo, CODIGO_USO, saida)
            self.assertIn("VARELEIRA_ID_APLICACAO_LOGIN: é igual a AZURE_CLIENT_ID", saida)
            self.assertIn("IMPLANTA (OIDC, sem segredo)", saida)
            self.assertNotIn(variaveis["AZURE_CLIENT_ID"], saida)
        mesmo_tenant = {**variaveis, "VARELEIRA_ID_TENANT_LOGIN": variaveis["AZURE_TENANT_ID"]}
        codigo, saida, _ = validar_na_implantacao("aplicacao", alterar=mesmo_tenant)
        self.assertEqual(codigo, CODIGO_OK, f"o tenant pode ser o mesmo; só o aplicativo de login não pode ser a identidade de implantação: {saida}")

    def test_acao_sem_login_aceita_so_os_dois_valores_do_bicep(self):
        for valor in ("Return401", "RedirectToLoginPage"):
            codigo, saida, _ = validar_na_implantacao("aplicacao", alterar={"VARELEIRA_ACAO_SEM_LOGIN": valor})
            self.assertEqual(codigo, CODIGO_OK, f"{valor}: {saida}")
        for valor in ("Allow", "return401", "Return403", "Redirect"):
            codigo, saida, _ = validar_na_implantacao("aplicacao", alterar={"VARELEIRA_ACAO_SEM_LOGIN": valor})
            self.assertEqual(codigo, CODIGO_USO, f"{valor}: {saida}")
            self.assertIn("VARELEIRA_ACAO_SEM_LOGIN: formato inválido", saida)

    def test_a_validacao_mostra_as_duas_credenciais_como_coisas_diferentes(self):
        codigo, saida, _ = validar_na_implantacao("aplicacao")
        self.assertEqual(codigo, CODIGO_OK, saida)
        self.assertIn("identidade de implantação (OIDC): AZURE_CLIENT_ID, AZURE_TENANT_ID e AZURE_SUBSCRIPTION_ID presentes", saida)
        self.assertIn("login da aplicação (registro do Entra ID do chat, distinto da identidade de implantação)", saida)
        self.assertIn("Credenciais: a implantação usa a identidade federada (OIDC), sem segredo; o login da aplicação é OUTRA credencial",
                      saida)
        self.assertIn("Configuração privada (IDs e nomes; NÃO são credenciais): vem de secrets individuais do ambiente protegido", saida)
        self.assertIn("a não privada (SKUs, réplicas, partições, regiões e ação sem login) vem de vars, uma a uma", saida)

    def test_as_variaveis_ausentes_dizem_se_vem_de_secrets_individuais_ou_de_vars(self):
        codigo, saida, _ = validar_na_implantacao("aplicacao", remover=("AZURE_CLIENT_ID", "VARELEIRA_NOME_REGISTRO",
                                                                         "VARELEIRA_ID_TENANT_LOGIN"))
        self.assertEqual(codigo, CODIGO_USO, saida)
        self.assertEqual(saida.count("configuração privada: secrets individuais do ambiente protegido"), 3,
                         "identidade de implantação, destinos e login da aplicação são configuração privada")
        self.assertNotIn("configure-as como variáveis do ambiente protegido", saida)
        codigo, saida, _ = validar_na_implantacao("isolar", remover=("VARELEIRA_SKU_BUSCA",))
        self.assertEqual(codigo, CODIGO_USO, saida)
        self.assertIn("não é privada: variáveis (vars) do ambiente protegido, uma a uma", saida)
        self.assertNotIn("configuração privada: secrets", saida)

    def test_o_workflow_entrega_cada_campo_enumerado_no_ambiente_sem_o_json_de_vars(self):
        # Como no workflow: nenhum VARELEIRA_VARS_JSON; cada campo mapeado chega ao passo, vazio quando não está configurado.
        for fase in operar_l300.FASES:
            variaveis = variaveis_do_ambiente(fase)
            env = ambiente_de_implantacao(VARELEIRA_L300_FASE=fase, VARELEIRA_TAG_IMAGEM="v1.2.3" if fase == "aplicacao" else "",
                                          VARELEIRA_L300_CONECTIVIDADE_PRIVADA_VALIDADA="true" if fase == "isolar" else "false")
            del env["VARELEIRA_VARS_JSON"]
            env.update({nome: variaveis.get(nome, "") for nome in (*operar_l300.VARS_PRIVADAS, *operar_l300.VARS_NAO_PRIVADAS)})
            with tempfile.TemporaryDirectory() as pasta:
                destino = Path(pasta) / "github_env"
                env["GITHUB_ENV"] = str(destino)
                codigo, saida = executar("--etapa", "validar", "--exigir-github", "--exigir-oidc", "--exigir-azure",
                                         "--exportar-github-env", env=env)
                self.assertEqual(codigo, CODIGO_OK, f"{fase}: {saida}")
                conteudo = destino.read_text(encoding="utf-8")
            exportado = dict(linha.split("=", 1) for linha in conteudo.splitlines())
            esperado = {nome for nome in (*operar_l300.VARS_PRIVADAS, *operar_l300.VARS_NAO_PRIVADAS)
                        if variaveis.get(nome) and nome.startswith("VARELEIRA_")}
            self.assertEqual(set(exportado) & esperado, esperado, f"{fase}: o que está configurado é exportado")
            self.assertFalse({nome for nome, valor in exportado.items() if not valor}, "campo vazio nunca é exportado")
            self.assertFalse(set(exportado) & {"AZURE_CLIENT_ID", "AZURE_TENANT_ID", "AZURE_SUBSCRIPTION_ID", "VARELEIRA_VARS_JSON",
                                              "VARELEIRA_SEGREDO_LOGIN"}, "identidade, JSON de vars e segredo nunca vão ao GITHUB_ENV")
            for valor in (*variaveis.values(), env["ACTIONS_ID_TOKEN_REQUEST_TOKEN"], env.get("VARELEIRA_SEGREDO_LOGIN", "")):
                if len(valor) > 3:  # os números curtos da fase isolar (como 1) aparecem em qualquer texto
                    self.assertNotIn(valor, saida, f"{fase}: nenhum valor privado é impresso")
            if fase != "isolar":
                self.assertFalse({"VARELEIRA_SKU_BUSCA", "VARELEIRA_REPLICAS_BUSCA"} & set(exportado))
            if fase == "isolar":
                self.assertEqual(exportado["VARELEIRA_SKU_BUSCA"], "basic")

    def test_campo_privado_que_o_runner_deixa_vazio_conta_como_ausente(self):
        # Um secret não criado chega ao passo como texto vazio (nunca como erro): o script precisa tratá-lo como ausente.
        env = ambiente_de_implantacao()
        del env["VARELEIRA_VARS_JSON"]
        env.update({nome: variaveis_do_ambiente().get(nome, "") for nome in (*operar_l300.VARS_PRIVADAS, *operar_l300.VARS_NAO_PRIVADAS)})
        env["AZURE_CLIENT_ID"] = ""
        env["VARELEIRA_NOME_WORKSPACE_LOGS"] = ""
        codigo, saida = executar("--etapa", "validar", "--exigir-azure", env=env)
        self.assertEqual(codigo, CODIGO_USO, saida)
        self.assertIn("AZURE_CLIENT_ID", saida)
        self.assertIn("VARELEIRA_NOME_WORKSPACE_LOGS", saida)
        self.assertIn("sem valores padrão", saida)


class SegredoDoLoginDaAplicacaoTests(unittest.TestCase):
    """O único segredo do L300: efêmero, só na fase aplicacao, vindo de secrets, e nunca impresso nem gravado."""

    def test_a_fase_aplicacao_exige_o_segredo_e_orienta_secrets_do_ambiente_protegido(self):
        for argumentos in (("--exigir-github", "--exigir-azure"), ("--exigir-github", "--exigir-segredo-login")):
            codigo, saida, _ = validar_na_implantacao("aplicacao", argumentos=argumentos, VARELEIRA_SEGREDO_LOGIN="")
            self.assertEqual(codigo, CODIGO_USO, f"{argumentos}: {saida}")
            self.assertIn("a fase aplicacao exige VARELEIRA_SEGREDO_LOGIN", saida)
            self.assertIn("secrets do ambiente protegido", saida)
            self.assertIn("não é a identidade de implantação por OIDC", saida)
            self.assertIn("nunca de vars, argumentos nem arquivos", saida)

    def test_sem_exigencia_a_validacao_local_nao_cobra_o_segredo(self):
        codigo, saida = executar("--etapa", "validar", "--fase", "aplicacao", "--tag-imagem", "v1")
        self.assertEqual(codigo, CODIGO_OK, saida)

    def test_o_formato_do_segredo_e_conferido_sem_repetir_o_valor(self):
        sentinela = secrets.token_hex(12)
        for ruim in ("curto", "com espaco " + sentinela, sentinela * 2 + "\n", sentinela * 2 + "\t", "açúcar-" + sentinela, "x" * 300):
            with self.subTest(tamanho=len(ruim)):
                codigo, saida, _ = validar_na_implantacao("aplicacao", VARELEIRA_SEGREDO_LOGIN=ruim)
                self.assertEqual(codigo, CODIGO_USO, saida)
                self.assertIn("VARELEIRA_SEGREDO_LOGIN: formato inválido", saida)
                self.assertNotIn(sentinela, saida)
                self.assertNotIn("x" * 20, saida)

    def test_segredo_valido_passa_e_nunca_aparece_no_console(self):
        codigo, saida, env = validar_na_implantacao("aplicacao")
        self.assertEqual(codigo, CODIGO_OK, saida)
        self.assertIn("[ok] login da aplicação: segredo do registro do Entra ID presente e com formato válido", saida)
        self.assertNotIn(env["VARELEIRA_SEGREDO_LOGIN"], saida)

    def test_fora_da_fase_aplicacao_o_segredo_nao_pode_existir(self):
        for fase in ("rede", "isolar"):
            segredo = novo_segredo_do_login()
            codigo, saida, _ = validar_na_implantacao(fase, VARELEIRA_SEGREDO_LOGIN=segredo)
            self.assertEqual(codigo, CODIGO_USO, saida)
            self.assertIn("só existe na fase aplicacao", saida)
            self.assertNotIn(segredo, saida)
            codigo, saida, _ = validar_na_implantacao(fase, VARELEIRA_SEGREDO_LOGIN="")
            self.assertEqual(codigo, CODIGO_OK, f"vazio equivale a ausente: {saida}")
        segredo = novo_segredo_do_login()
        codigo, saida = executar("--etapa", "validar", "--fase", "rede", env={"VARELEIRA_SEGREDO_LOGIN": segredo})
        self.assertEqual(codigo, CODIGO_USO, "até a validação local recusa o segredo fora da fase aplicacao")
        self.assertNotIn(segredo, saida)

    def test_nenhuma_outra_credencial_e_aceita_em_nenhuma_fase(self):
        nomes = ("AZURE_CLIENT_SECRET", "AZURE_PASSWORD", "AZURE_USERNAME", "AZURE_CLIENT_CERTIFICATE_PATH",
                 "AZURE_CLIENT_CERTIFICATE_PASSWORD", "AZURE_OPENAI_API_KEY", "VARELEIRA_SENHA_X", "VARELEIRA_TOKEN_Y",
                 "VARELEIRA_CHAVE_Z")
        for fase in operar_l300.FASES:
            for nome in nomes:
                valor = "valor-" + secrets.token_hex(10)
                with self.subTest(fase=fase, nome=nome):
                    codigo, saida, _ = validar_na_implantacao(fase, **{nome: valor})
                    self.assertEqual(codigo, CODIGO_USO, saida)
                    self.assertIn(nome, saida)
                    self.assertIn("o único segredo aceito é VARELEIRA_SEGREDO_LOGIN", saida)
                    self.assertIn("não use AZURE_CLIENT_SECRET", saida)
                    self.assertNotIn(valor, saida)
        codigo, saida, _ = validar_na_implantacao("rede", AZURE_CLIENT_SECRET="")
        self.assertEqual(codigo, CODIGO_OK, f"variável vazia não é credencial: {saida}")

    def test_o_segredo_em_vars_e_recusado_com_a_orientacao_de_troca(self):
        segredo = novo_segredo_do_login()
        base = variaveis_do_ambiente("aplicacao")
        codigo, saida, _ = validar_na_implantacao("aplicacao", alterar={**base, "VARELEIRA_SEGREDO_LOGIN": segredo})
        self.assertEqual(codigo, CODIGO_USO, saida)
        self.assertIn("VARELEIRA_SEGREDO_LOGIN: o segredo do login da aplicação não pode ficar em vars", saida)
        self.assertIn("gere um segredo novo", saida)
        self.assertIn("só em secrets do ambiente protegido", saida)
        self.assertNotIn(segredo, saida)

    def test_o_segredo_nunca_vai_para_o_github_env(self):
        segredo = "Seg" + secrets.token_hex(12)
        with tempfile.TemporaryDirectory() as pasta:
            destino = Path(pasta) / "github_env"
            with self.assertRaisesRegex(operar_l300.ErroLab, "segredos nunca são exportados"):
                operar_l300.escrever_github_env(str(destino), {"VARELEIRA_REGIAO": "brazilsouth", "VARELEIRA_SEGREDO_LOGIN": segredo})
            self.assertFalse(destino.exists(), "nada é gravado quando um segredo é recusado")

    def test_nao_existe_opcao_para_informar_segredos_por_argumento(self):
        parser = operar_l300.criar_parser()
        for acao in parser._actions:
            for opcao in acao.option_strings:
                if opcao == "--exigir-segredo-login":
                    self.assertEqual(acao.nargs, 0, "esta opção só exige a presença; nunca recebe o valor")
                else:
                    self.assertNotRegex(opcao, r"(?i)segredo|secret|senha|token|chave|password|credencial")

    def test_o_console_nunca_mostra_o_segredo_nem_quando_ele_chega_por_um_caminho_inesperado(self):
        segredo = "Seg" + secrets.token_hex(16)  # só letras e números: passaria nos formatos de nome de ambiente e de rótulo
        env = {"VARELEIRA_SEGREDO_LOGIN": segredo}
        codigo, saida = executar("--etapa", "verificar-ambiente", f"--nome-ambiente={segredo}", env=env)
        self.assertEqual(codigo, CODIGO_DIVERGENCIA, saida)
        self.assertNotIn(segredo, saida)
        self.assertIn("***", saida)

    def test_relatorio_que_traria_o_segredo_nao_e_gravado(self):
        segredo = "Seg" + secrets.token_hex(16)
        with tempfile.TemporaryDirectory() as pasta:
            pasta = Path(pasta)
            (pasta / "whatif.json").write_text(json.dumps(Cenario().whatif()), encoding="utf-8")
            codigo, saida = executar("--etapa", "sanitizar-whatif", "--arquivo", str(pasta / "whatif.json"),
                                     "--relatorio", str(pasta / "r.json"), f"--rotulo={segredo}", *QUALIFICADO,
                                     env={"VARELEIRA_SEGREDO_LOGIN": segredo})
            self.assertEqual(codigo, CODIGO_INESPERADO, saida)
            self.assertFalse((pasta / "r.json").exists(), "o relatório com o segredo não pode existir")
        self.assertIn("NÃO foi gravado", saida)
        self.assertNotIn(segredo, saida)

    def test_eco_do_segredo_no_what_if_bruto_e_avisado_sem_vazar(self):
        segredo = novo_segredo_do_login()
        dados = Cenario().whatif()
        dados["changes"][2]["after"] = {"valor": segredo, "escapado": json.dumps(segredo)}
        with tempfile.TemporaryDirectory() as pasta:
            pasta = Path(pasta)
            (pasta / "whatif.json").write_text(json.dumps(dados), encoding="utf-8")
            codigo, saida = executar("--etapa", "sanitizar-whatif", "--arquivo", str(pasta / "whatif.json"),
                                     "--relatorio", str(pasta / "r.json"), *QUALIFICADO, env={"VARELEIRA_SEGREDO_LOGIN": segredo})
            conteudo = (pasta / "r.json").read_text(encoding="utf-8")
        self.assertEqual(codigo, CODIGO_OK, saida)
        self.assertIn("[AVISO] O JSON bruto do what-if contém o valor do segredo do login da aplicação", saida)
        self.assertIn("ecoou", conteudo)
        for texto in (saida, conteudo):
            self.assertNotIn(segredo, texto)
            self.assertNotIn(json.dumps(segredo)[1:-1], texto)

    def test_o_bicep_e_a_procura_dele_rodam_sem_nenhuma_credencial_no_ambiente(self):
        segredo = novo_segredo_do_login()
        contaminado = {"VARELEIRA_SEGREDO_LOGIN": segredo, "AZURE_CLIENT_SECRET": "x-" + secrets.token_hex(8),
                       "AZURE_USERNAME": "u-" + secrets.token_hex(4), "GH_TOKEN": "t-" + secrets.token_hex(8),
                       "ACTIONS_ID_TOKEN_REQUEST_TOKEN": "t-" + secrets.token_hex(8)}
        capturados: list[dict | None] = []

        def falso(comando, **opcoes):
            capturados.append(opcoes.get("env"))
            dados = {"--version": ("Bicep CLI version 0.48.1 (abc)", ""), "build": ("{}", ""), "lint": ("", "")}
            saida, erro = dados[comando[1]]
            return mock.Mock(returncode=0, stdout=saida, stderr=erro)

        with tempfile.TemporaryDirectory() as pasta, mock.patch.dict(os.environ, contaminado):
            arquivo = Path(pasta) / "l300.bicep"
            arquivo.write_text("targetScope = 'resourceGroup'\n", encoding="utf-8")
            operar_l300.validar_bicep(arquivo, binario="bicep-falso", executar=falso)
            nome = "bicep.exe" if os.name == "nt" else "bicep"
            (Path(pasta) / "bin").mkdir()
            (Path(pasta) / "bin" / nome).write_text("", encoding="utf-8")
            with mock.patch.dict(os.environ, {"AZURE_CONFIG_DIR": pasta}), \
                    mock.patch.object(operar_l300.subprocess, "run", lambda comando, **opcoes: falso([comando[0], "--version"], **opcoes)):
                operar_l300.localizar_bicep()
        self.assertGreaterEqual(len(capturados), 4, "três chamadas do validar_bicep e ao menos uma da procura do binário")
        for ambiente in capturados:
            self.assertIsNotNone(ambiente, "o ambiente do programa filho precisa ser explícito, sem herdar as credenciais")
            self.assertTrue(set(contaminado).isdisjoint(ambiente), set(contaminado) & set(ambiente))
            self.assertNotIn(segredo, ambiente.values())
            self.assertIn("PATH", {nome.upper() for nome in ambiente}, "o resto do ambiente continua disponível")


class ContratoDoScriptTests(unittest.TestCase):
    """O que o script promete: local, sem nuvem, sem execução e sem etapa destrutiva."""

    @classmethod
    def setUpClass(cls):
        cls.codigo = SCRIPT.read_text(encoding="utf-8")
        cls.arvore = ast.parse(cls.codigo)

    def test_o_script_conhece_toda_variavel_que_o_bicepparam_le_e_os_limites_do_bicep(self):
        parametros = RAIZ / "infra" / "levels" / "l300.bicepparam"
        principal = RAIZ / "infra" / "l300.bicep"
        if not parametros.is_file() or not principal.is_file():
            self.skipTest("infra/l300.bicep e infra/levels/l300.bicepparam ainda não existem: o contrato NÃO foi conferido")
        lidas = set(re.findall(r"readEnvironmentVariable\('([A-Z0-9_]+)'", parametros.read_text(encoding="utf-8")))
        self.assertEqual(lidas - operar_l300.VARIAVEIS_DO_BICEPPARAM, set(),
                         "o bicepparam ganhou uma variável que o script não valida: inclua-a na tabela do script")
        self.assertEqual(operar_l300.VARIAVEIS_DO_BICEPPARAM - lidas, set(), "o script espera uma variável que o bicepparam não lê")
        bicep = principal.read_text(encoding="utf-8")
        nomes = {"VARELEIRA_NOME_CONTA": "nomeConta", "VARELEIRA_NOME_BUSCA": "nomeBusca", "VARELEIRA_NOME_MODELOS": "nomeModelos",
                 "VARELEIRA_NOME_REGISTRO": "nomeRegistro", "VARELEIRA_NOME_IDENTIDADE_APLICACAO": "nomeIdentidadeAplicacao",
                 "VARELEIRA_NOME_WORKSPACE_LOGS": "nomeWorkspaceLogs"}
        for variavel, parametro in nomes.items():
            achado = re.search(rf"@minLength\((\d+)\)\s*@maxLength\((\d+)\)\s*param {parametro}\b", bicep)
            self.assertIsNotNone(achado, f"{parametro}: o Bicep precisa declarar @minLength e @maxLength")
            minimo, maximo = int(achado.group(1)), int(achado.group(2))
            padrao = operar_l300._VALIDADORES_POR_NOME[variavel][0]
            for tamanho, esperado in ((minimo - 1, False), (minimo, True), (maximo, True), (maximo + 1, False)):
                self.assertEqual(bool(padrao.fullmatch("a" * tamanho)), esperado, f"{variavel} com {tamanho} caracteres")
        carga = re.search(r"@minLength\((\d+)\)\s*@maxLength\((\d+)\)\s*param principalIdCarga\b", bicep)
        self.assertEqual((carga.group(1), carga.group(2)), ("36", "36"), "o ID de carga é um GUID de 36 caracteres")
        acoes = re.search(r"@allowed\(\[((?:(?!\]\)).)*)\]\)\s*param acaoSemLogin\b", bicep, re.S)
        self.assertIsNotNone(acoes, "l300.bicep precisa declarar acaoSemLogin com @allowed")
        self.assertEqual(set(re.findall(r"'(\w+)'", acoes.group(1))), {"Return401", "RedirectToLoginPage"})
        for acao in ("Return401", "RedirectToLoginPage"):
            self.assertTrue(operar_l300._ACAO_SEM_LOGIN.fullmatch(acao))
        self.assertIn("@secure()\nparam segredoLogin", bicep.replace("\r\n", "\n"), "o segredo do login entra como parâmetro seguro")

    def test_o_bicep_do_script_so_compila_o_template_e_nunca_os_parametros(self):
        literais = {no.value for no in ast.walk(self.arvore) if isinstance(no, ast.Constant) and isinstance(no.value, str)}
        self.assertNotIn("build-params", literais, "compilar o arquivo de parâmetros leria o segredo do login")
        usos = 0
        for no in ast.walk(self.arvore):
            if isinstance(no, ast.List):
                constantes = [elemento.value for elemento in no.elts if isinstance(elemento, ast.Constant)]
                if "--stdout" in constantes:
                    usos += 1
                    self.assertIn("build", constantes)
        self.assertEqual(usos, 1, "--stdout só aparece na compilação do template infra/l300.bicep")

    def test_a_classificacao_privada_e_nao_privada_cobre_tudo_que_o_bicepparam_e_o_az_usam_e_nenhuma_e_credencial(self):
        privadas, nao_privadas = set(operar_l300.VARS_PRIVADAS), set(operar_l300.VARS_NAO_PRIVADAS)
        self.assertEqual(privadas & nao_privadas, set())
        portoes_tag_e_credencial = {operar_l300.VAR_FASE, operar_l300.VAR_INGRESSO_EXTERNO, operar_l300.VAR_CONECTIVIDADE,
                                    operar_l300.VAR_TAG, operar_l300.VAR_SEGREDO_LOGIN}
        usadas = operar_l300.VARIAVEIS_DO_BICEPPARAM | set(operar_l300.VARS_DE_IDENTIDADE) | {operar_l300.VAR_GRUPO}
        self.assertEqual(privadas | nao_privadas | portoes_tag_e_credencial, usadas,
                         "toda variável nova precisa ser classificada: privada (secret) ou não privada (var)")
        for nome in privadas | nao_privadas:
            self.assertFalse(operar_l300.nome_de_segredo(nome), f"{nome} é configuração, não credencial")
        self.assertTrue(operar_l300.nome_de_segredo(operar_l300.VAR_SEGREDO_LOGIN))
        self.assertNotIn(operar_l300.VAR_SEGREDO_LOGIN, privadas | nao_privadas)
        # O que o runner imprimiria e revelaria (IDs e nomes) é privado: é o mesmo padrão que o workflow mascara de novo.
        padrao_da_mascara = re.compile(r"AZURE_(?:CLIENT|TENANT|SUBSCRIPTION)_ID|VARELEIRA_(?:NOME|ID|GRUPO)_\w+")
        self.assertEqual({nome for nome in privadas | nao_privadas if padrao_da_mascara.fullmatch(nome)}, privadas)

    def test_a_ajuda_distingue_configuracao_privada_de_credenciais(self):
        codigo, ajuda = executar("--help")
        self.assertEqual(codigo, CODIGO_OK, ajuda)
        texto = re.sub(r"\s+", " ", ajuda)
        for trecho in ("Configuração privada × credenciais", "configuração privada identificadores e nomes que sozinhos não dão acesso",
                       "um SECRET individual do ambiente protegido, que o runner mascara desde o primeiro uso",
                       "nunca de vars (nem do contexto vars serializado), que o runner imprimiria em claro antes de qualquer máscara",
                       "NÃO são credenciais", "vem de vars, uma variável por vez",
                       "A configuração privada (IDs e nomes; não são credenciais) vem de secrets individuais do ambiente; "
                       "a não privada, de vars"):
            self.assertIn(trecho, texto, trecho)

    def test_a_ajuda_distingue_a_identidade_de_implantacao_do_login_da_aplicacao(self):
        codigo, ajuda = executar("--help")
        self.assertEqual(codigo, CODIGO_OK, ajuda)
        for trecho in ("implantação (OIDC)", "login da aplicação", "secrets.VARELEIRA_SEGREDO_LOGIN", "o ÚNICO segredo aceito",
                       "efêmera", "AZURE_CLIENT_SECRET", "--exigir-segredo-login", "TODOS os destinos"):
            self.assertIn(trecho, re.sub(r"\s+", " ", ajuda), trecho)

    def test_a_ajuda_funciona_como_programa_e_lista_as_etapas(self):
        resultado = subprocess.run([sys.executable, str(SCRIPT), "--help"], capture_output=True, text=True, encoding="utf-8",
                                   env={**os.environ, "PYTHONIOENCODING": "utf-8"}, timeout=60, check=False)
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        for etapa in ("validar", "plano", "sanitizar-whatif", "verificar-ambiente", "conferir", "resumir-logs"):
            self.assertIn(etapa, resultado.stdout)
        self.assertIn("Códigos de saída", resultado.stdout)

    def test_nao_ha_opcao_de_executar_nem_etapa_destrutiva(self):
        parser = operar_l300.criar_parser()
        opcoes = {opcao for acao in parser._actions for opcao in acao.option_strings}
        for proibida in ("--executar", "--substituir", "--forcar", "--remover", "--apagar", "--limpar", "--yes"):
            self.assertNotIn(proibida, opcoes)
        self.assertEqual(set(operar_l300.ETAPAS), {"validar", "plano", "sanitizar-whatif", "verificar-ambiente", "conferir",
                                                   "resumir-logs"})
        codigo, saida = executar("--etapa", "limpar")
        self.assertEqual(codigo, CODIGO_USO, saida)
        codigo, saida = executar("--etapa", "plano", "--executar")
        self.assertEqual(codigo, CODIGO_USO, saida)

    def test_nao_importa_rede_nem_sdks_e_so_a_checagem_do_bicep_executa_programas(self):
        importados = set()
        for no in ast.walk(self.arvore):
            if isinstance(no, ast.Import):
                importados |= {alias.name.split(".")[0] for alias in no.names}
            elif isinstance(no, ast.ImportFrom) and no.module:
                importados.add(no.module.split(".")[0])
        proibidos = {"socket", "ssl", "http", "urllib", "urllib3", "requests", "httpx", "httpx2", "aiohttp", "ftplib", "smtplib",
                     "azure", "openai", "agent_framework", "msal", "paramiko"}
        self.assertEqual(importados & proibidos, set())
        for funcao in self.arvore.body:
            if isinstance(funcao, ast.FunctionDef) and funcao.name not in ("localizar_bicep", "validar_bicep"):
                for no in ast.walk(funcao):
                    if isinstance(no, ast.Attribute) and isinstance(no.value, ast.Name) and no.value.id == "subprocess":
                        self.fail(f"{funcao.name} usa subprocess: só a checagem local do Bicep pode executar programas")

    def test_nao_apaga_nem_move_nada_e_nao_invoca_az_nem_gh(self):
        proibidos = {"unlink", "remove", "rmdir", "rmtree", "removedirs", "rename", "replace", "system", "popen"}
        for no in ast.walk(self.arvore):
            if isinstance(no, ast.Attribute):
                self.assertNotIn(no.attr, proibidos, f"linha {no.lineno}")
        literais = [no.value for no in ast.walk(self.arvore) if isinstance(no, ast.Constant) and isinstance(no.value, str)]
        self.assertFalse([t for t in literais if t.strip() in ("az", "gh", "curl")])

    def test_as_constantes_do_contrato_batem_com_o_combinado(self):
        self.assertEqual(operar_l300.FASES, ("rede", "aplicacao", "isolar"))
        self.assertEqual(operar_l300.FASE_PADRAO, "rede")
        self.assertEqual(operar_l300.AMBIENTE_GITHUB, "vareleira-l300")
        self.assertEqual(operar_l300.RUNNER_ROTULOS, ("self-hosted", "linux", "vareleira-l300"))
        self.assertEqual(operar_l300.INDICE_L300, "vareleira-lar-l300")
        self.assertEqual(operar_l300.REF_PERMITIDA, "refs/heads/main")

    def test_o_script_e_a_biblioteca_padrao_mais_o_lab_comum(self):
        # O runner confiável não instala pacotes: só precisa do Python 3.12 e desta pasta.
        locais = {"lab_comum"}
        importados = {no.module.split(".")[0] for no in ast.walk(self.arvore) if isinstance(no, ast.ImportFrom) and no.module
                      and no.module != "__future__"}
        importados |= {alias.name.split(".")[0] for no in ast.walk(self.arvore) if isinstance(no, ast.Import) for alias in no.names}
        for modulo in importados - locais:
            self.assertIn(modulo, sys.stdlib_module_names, modulo)

    def test_nenhuma_etapa_abre_rede_nem_executa_programas(self):
        cenario = Cenario()
        with tempfile.TemporaryDirectory() as pasta:
            pasta = Path(pasta)
            (pasta / "whatif.json").write_text(json.dumps(cenario.whatif()), encoding="utf-8")
            (pasta / "descritor.json").write_text(json.dumps(descritor()), encoding="utf-8")
            (pasta / "logs.txt").write_text(linha_do_servidor() + "\n", encoding="utf-8")
            (pasta / "aprovacoes.json").write_text("[]", encoding="utf-8")
            execucoes = (
                (("--etapa", "validar", "--fase", "rede"), CODIGO_OK),
                (("--etapa", "plano", "--fase", "todas"), CODIGO_OK),
                (("--etapa", "sanitizar-whatif", "--arquivo", str(pasta / "whatif.json"), "--relatorio", str(pasta / "r.json"),
                  *QUALIFICADO), CODIGO_OK),
                (("--etapa", "verificar-ambiente", "--aprovacoes", str(pasta / "aprovacoes.json")), CODIGO_DIVERGENCIA),
                (("--etapa", "conferir", "--descritor", str(pasta / "descritor.json")), CODIGO_OK),
                (("--etapa", "resumir-logs", "--logs", str(pasta / "logs.txt")), CODIGO_OK),
            )
            with sem_rede():
                for argumentos, esperado in execucoes:
                    codigo, saida = executar(*argumentos)
                    self.assertEqual(codigo, esperado, f"{argumentos[1]}: {saida}")

    def test_erro_inesperado_nao_vaza_detalhes(self):
        sentinela = "SENTINELA-" + secrets.token_hex(6)
        with mock.patch.object(operar_l300, "montar_plano", side_effect=RuntimeError(sentinela)):
            codigo, saida = executar("--etapa", "plano")
        self.assertEqual(codigo, 4, saida)
        self.assertIn("RuntimeError", saida)
        self.assertNotIn(sentinela, saida)


if __name__ == "__main__":
    unittest.main()
