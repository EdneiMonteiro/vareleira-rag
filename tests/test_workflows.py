"""Controles de segurança dos workflows do GitHub Actions (CI e implantação manual do L300), conferidos sem GitHub.

Os arquivos YAML são lidos com o PyYAML (já instalado como dependência do Microsoft Agent Framework) e nada é executado:
estes testes provam o que está ESCRITO nos workflows, não que eles tenham rodado no GitHub ou no Azure.
"""

import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

import support  # noqa: F401  (configura o caminho dos scripts)
import operar_l300
from support import RAIZ

PASTA = RAIZ / ".github" / "workflows"
VALIDAR = PASTA / "validar.yml"
IMPLANTAR = PASTA / "l300-implantar.yml"
REUTILIZAVEL = "./.github/workflows/validar.yml"
EXPRESSAO_DO_SEGREDO_DO_LOGIN = "${{ inputs.fase == 'aplicacao' && secrets.VARELEIRA_SEGREDO_LOGIN || '' }}"

# Ações permitidas: repositório -> (SHA completo do commit, versão). Cada par foi conferido na API pública do GitHub, no
# repositório oficial da ação: a tag da versão aponta para esse commit, e a versão é a última release publicada na data.
ACOES_VERIFICADAS = {
    "actions/checkout": ("3d3c42e5aac5ba805825da76410c181273ba90b1", "v7.0.1"),
    "actions/setup-python": ("5fda3b95a4ea91299a34e894583c3862153e4b97", "v7.0.0"),
    "azure/login": ("a641126d1b8aa4d1fa005f4f92df94a3a4c4c906", "v3.1.0"),
}
RUNNERS_HOSPEDADOS = {"ubuntu-24.04", "windows-2025"}
GATILHOS_DE_CODIGO_NAO_CONFIAVEL = {"pull_request", "pull_request_target", "push", "schedule", "workflow_run", "issue_comment",
                                    "pull_request_review", "pull_request_review_comment", "issues", "fork"}
GUID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.IGNORECASE)
ENTRADAS_NO_AMBIENTE = {
    "VARELEIRA_L300_FASE": "inputs.fase",
    "VARELEIRA_APLICAR": "inputs.aplicar",
    "VARELEIRA_L300_CONECTIVIDADE_PRIVADA_VALIDADA": "inputs.conectividade_privada_validada",
    "VARELEIRA_L300_INGRESSO_EXTERNO": "inputs.ingresso_externo",
    "VARELEIRA_TAG_IMAGEM": "inputs.tag_imagem",
    "VARELEIRA_CONFIRMACAO": "inputs.confirmacao",
    "VARELEIRA_QUALIFICAR_NAO_SUPORTADO": "inputs.qualificar_nao_suportado",
    "VARELEIRA_QUALIFICAR_PROPRIEDADES_REMOVIDAS": "inputs.qualificar_propriedades_removidas",
    "VARELEIRA_PLANO_SHA256": "inputs.plano_sha256",
}


def texto(caminho) -> str:
    return caminho.read_text(encoding="utf-8")


def carregar(caminho) -> dict:
    return yaml.safe_load(texto(caminho))


def gatilhos(workflow: dict) -> dict:
    # No YAML 1.1 do PyYAML, a chave `on` é lida como o booleano True.
    bruto = workflow.get("on", workflow.get(True))
    return bruto if isinstance(bruto, dict) else {nome: None for nome in (bruto if isinstance(bruto, list) else [bruto])}


def passos(job: dict) -> list[dict]:
    return job.get("steps") or []


def comandos(job: dict) -> list[str]:
    return [passo.get("run", "") for passo in passos(job)]


def indice(job: dict, predicado, descricao: str) -> int:
    for posicao, passo in enumerate(passos(job)):
        if predicado(passo):
            return posicao
    raise AssertionError(f"passo não encontrado: {descricao}")


def usa(passo: dict, prefixo: str) -> bool:
    return str(passo.get("uses", "")).lower().startswith(prefixo)


def runners(job: dict) -> set[str]:
    destino = job.get("runs-on")
    if isinstance(destino, str) and "matrix.os" in destino:
        return set(job["strategy"]["matrix"]["os"])
    return {destino} if isinstance(destino, str) else set(destino)


def referencias_de_contexto(dado) -> set[tuple[str, str | None]]:
    """Todo (contexto, nome) de secrets e vars usado em expressões ${{ }}; o nome é None se o contexto inteiro for usado."""
    encontradas: set[tuple[str, str | None]] = set()
    if isinstance(dado, str):
        for expressao in re.findall(r"\$\{\{(.*?)\}\}", dado, re.S):
            for contexto, nome in re.findall(r"\b(secrets|vars)\b(?:\.([A-Za-z0-9_]+))?", expressao):
                encontradas.add((contexto, nome or None))
    elif isinstance(dado, dict):
        for chave, valor in dado.items():
            encontradas |= referencias_de_contexto(chave) | referencias_de_contexto(valor)
    elif isinstance(dado, list):
        for item in dado:
            encontradas |= referencias_de_contexto(item)
    return encontradas


class WorkflowsEmGeralTests(unittest.TestCase):
    def test_os_workflows_existem_e_sao_yaml_valido(self):
        self.assertTrue(VALIDAR.is_file())
        self.assertTrue(IMPLANTAR.is_file())
        for caminho in sorted(PASTA.glob("*.yml")):
            workflow = carregar(caminho)
            self.assertIsInstance(workflow["jobs"], dict, caminho.name)
            self.assertTrue(workflow.get("name"), caminho.name)

    def test_toda_acao_externa_esta_fixada_por_sha_completo_verificado_e_comentado_com_a_versao(self):
        usadas = set()
        for caminho in sorted(PASTA.glob("*.yml")):
            fonte = texto(caminho)
            workflow = carregar(caminho)
            for job in workflow["jobs"].values():
                for referencia in [job.get("uses"), *[p.get("uses") for p in passos(job)]]:
                    if not referencia or referencia == REUTILIZAVEL:
                        continue
                    achado = re.fullmatch(r"([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)@([0-9a-f]{40})", referencia)
                    self.assertIsNotNone(achado, f"{caminho.name}: {referencia} precisa de um SHA completo, não de uma tag")
                    repositorio, sha = achado.group(1).lower(), achado.group(2)
                    self.assertIn(repositorio, ACOES_VERIFICADAS, f"{caminho.name}: {repositorio} não está na lista verificada")
                    esperado_sha, versao = ACOES_VERIFICADAS[repositorio]
                    self.assertEqual(sha, esperado_sha, repositorio)
                    self.assertRegex(fonte, rf"(?im)uses: {re.escape(achado.group(1))}@{sha} # {re.escape(versao)}\s*$",
                                     f"{caminho.name}: o SHA de {repositorio} precisa do comentário com a versão")
                    usadas.add(repositorio)
        self.assertEqual(usadas, set(ACOES_VERIFICADAS), "toda ação verificada é usada: sem pins esquecidos")

    def test_workflows_com_gatilho_de_codigo_nao_confiavel_nao_tocam_runner_confiavel_ambiente_nem_oidc(self):
        for caminho in sorted(PASTA.glob("*.yml")):
            workflow = carregar(caminho)
            if not set(gatilhos(workflow)) & GATILHOS_DE_CODIGO_NAO_CONFIAVEL:
                continue
            fonte = texto(caminho)
            self.assertNotIn("pull_request_target", set(gatilhos(workflow)), caminho.name)
            for nome in ("self-hosted", "vareleira-l300", "id-token", "azure/login", "secrets.", "environment:"):
                self.assertNotIn(nome, fonte, f"{caminho.name} roda para pull requests e não pode usar {nome}")
            for job in workflow["jobs"].values():
                self.assertNotIn("environment", job)
                self.assertNotIn("self-hosted", json.dumps(job.get("runs-on")))

    def test_nenhum_workflow_tem_identificador_do_ambiente_nem_segredo_embutido(self):
        for caminho in sorted(PASTA.glob("*.yml")):
            fonte = texto(caminho)
            self.assertEqual(GUID.findall(fonte), [], f"{caminho.name}: GUID no arquivo")
            for proibido in ("client-secret", "creds:", "AZURE_CREDENTIALS", "password", "continue-on-error", "ACTIONS_STEP_DEBUG",
                             "upload-artifact", "actions/cache@", "set-output", "build-params"):
                self.assertNotIn(proibido, fonte, f"{caminho.name}: {proibido}")
            # Comentários ficam de fora: só conta o que o GitHub executa. Só o implantar usa secrets: a configuração privada (um por
            # campo) e a única credencial com segredo, a do login da aplicação.
            executado = json.dumps(carregar(caminho), ensure_ascii=False)
            referencias = set(re.findall(r"secrets\.\w+", executado))
            esperadas = ({f"secrets.{nome}" for nome in (*operar_l300.VARS_PRIVADAS, operar_l300.VAR_SEGREDO_LOGIN)}
                         if caminho == IMPLANTAR else set())
            self.assertEqual(referencias, esperadas, f"{caminho.name}: segredos do GitHub usados")
            self.assertNotIn("inherit", executado, f"{caminho.name}: secrets: inherit repassaria todos os segredos")
            self.assertNotIn("toJSON", executado, f"{caminho.name}: serializar vars ou secrets imprime os valores em claro")

    def test_todo_job_tem_limite_de_tempo(self):
        for caminho in sorted(PASTA.glob("*.yml")):
            for nome, job in carregar(caminho)["jobs"].items():
                if "uses" not in job:
                    self.assertLessEqual(job.get("timeout-minutes", 999), 90, f"{caminho.name}/{nome}")


class ValidarTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = carregar(VALIDAR)
        cls.fonte = texto(VALIDAR)

    def test_roda_em_pull_request_e_na_branch_principal_e_pode_ser_reutilizado(self):
        entradas = gatilhos(self.workflow)
        self.assertEqual(set(entradas), {"pull_request", "push", "workflow_call"})
        self.assertEqual(entradas["push"], {"branches": ["main"]})

    def test_so_le_o_conteudo_sem_oidc_ambiente_segredos_ou_runner_proprio(self):
        self.assertEqual(self.workflow["permissions"], {"contents": "read"})
        for nome, job in self.workflow["jobs"].items():
            self.assertNotIn("permissions", job, f"{nome} herda só contents: read")
            self.assertNotIn("environment", job)
        for proibido in ("id-token", "azure/login", "self-hosted", "vareleira-l300", "secrets.", "bicepparam", "build-params",
                         "VARELEIRA_SEGREDO_LOGIN"):
            self.assertNotIn(proibido, self.fonte)
        self.assertNotRegex(self.fonte, r"\baz login\b")

    def test_so_usa_runners_hospedados_fixados(self):
        for nome, job in self.workflow["jobs"].items():
            self.assertTrue(runners(job) <= RUNNERS_HOSPEDADOS, nome)
        self.assertEqual(self.workflow["jobs"]["testes"]["strategy"]["matrix"]["os"], ["ubuntu-24.04", "windows-2025"])
        self.assertFalse(self.workflow["jobs"]["testes"]["strategy"]["fail-fast"], "uma plataforma não esconde a outra")

    def test_executa_testes_python_3_12_lint_e_build_do_bicep_e_sintaxe_do_javascript(self):
        jobs = self.workflow["jobs"]
        testes = comandos(jobs["testes"])
        configuracao = next(p for p in passos(jobs["testes"]) if usa(p, "actions/setup-python@"))["with"]
        self.assertEqual(configuracao["python-version"], "3.12")
        self.assertIn("python -m pip install -r requirements/l300.txt", testes)
        self.assertIn("python -m pip check", testes)
        self.assertIn("python -m unittest discover -s tests", testes)
        bicep = "\n".join(comandos(jobs["bicep"]))
        self.assertIn("find infra -name '*.bicep'", bicep)
        self.assertRegex(bicep, r'"\$bicep" lint "\$arquivo"')
        self.assertRegex(bicep, r'"\$bicep" build "\$arquivo" --stdout')
        self.assertIn('[ -n "$saida" ]', bicep, "o lint precisa estar limpo: aviso também reprova")
        self.assertIn("node --check web/app.js", comandos(jobs["javascript"]))

    def test_o_bicep_fixado_e_instalado_antes_dos_testes_e_do_lint(self):
        versao = self.workflow["env"]["BICEP_VERSAO"]
        self.assertRegex(versao, r"^v\d+\.\d+\.\d+$")
        instalar = 'az bicep install --version "$BICEP_VERSAO"'
        for nome, depois in (("testes", "python -m unittest discover -s tests"), ("bicep", None)):
            lista = comandos(self.workflow["jobs"][nome])
            self.assertIn(instalar, lista, nome)
            if depois:
                self.assertLess(lista.index(instalar), lista.index(depois))
        conferir = next(c for c in comandos(self.workflow["jobs"]["bicep"]) if '"$HOME/.azure/bin/bicep" --version' in c)
        self.assertIn('exit 1', conferir)

    def test_o_manifesto_do_l300_existe_e_reaproveita_o_do_l200(self):
        linhas = [l for l in texto(RAIZ / "requirements" / "l300.txt").splitlines() if l and not l.startswith("#")]
        self.assertEqual(linhas, ["-r l200.txt"])

    def test_pull_requests_substituidos_cancelam_a_execucao_antiga_mas_implantacoes_nao(self):
        self.assertIn("pull_request", self.workflow["concurrency"]["cancel-in-progress"])

    def test_nenhum_script_recebe_expressoes_do_github_diretamente(self):
        for nome, job in self.workflow["jobs"].items():
            for comando in comandos(job):
                self.assertNotIn("${{", comando, nome)


class ImplantarTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = carregar(IMPLANTAR)
        cls.fonte = texto(IMPLANTAR)
        cls.job = cls.workflow["jobs"]["implantar"]

    def test_so_dispara_manualmente(self):
        self.assertEqual(set(gatilhos(self.workflow)), {"workflow_dispatch"})

    def test_entradas_sao_enumeradas_booleanas_ou_texto_e_o_padrao_e_so_simular(self):
        entradas = gatilhos(self.workflow)["workflow_dispatch"]["inputs"]
        self.assertEqual(set(entradas), {"fase", "aplicar", "conectividade_privada_validada", "ingresso_externo", "tag_imagem",
                                         "confirmacao", "qualificar_nao_suportado", "qualificar_propriedades_removidas",
                                         "plano_sha256"})
        fase = entradas["fase"]
        self.assertEqual((fase["type"], fase["default"], fase["options"]), ("choice", "rede", list(operar_l300.FASES)))
        for nome in ("aplicar", "conectividade_privada_validada", "ingresso_externo"):
            self.assertEqual((entradas[nome]["type"], entradas[nome]["default"]), ("boolean", False), nome)
        for nome in ("tag_imagem", "confirmacao", "qualificar_nao_suportado", "qualificar_propriedades_removidas", "plano_sha256"):
            self.assertEqual((entradas[nome]["type"], entradas[nome]["default"]), ("string", ""), nome)

    def test_texto_do_usuario_nunca_entra_direto_em_scripts_so_pelo_ambiente(self):
        for nome, job in self.workflow["jobs"].items():
            for comando in comandos(job):
                self.assertNotIn("${{", comando, nome)
        for nome in ("entradas", "implantar"):
            validar = next(p for p in passos(self.workflow["jobs"][nome]) if "--etapa validar" in p.get("run", ""))
            mapeado = {chave: valor for chave, valor in validar["env"].items() if chave in ENTRADAS_NO_AMBIENTE}
            self.assertEqual(mapeado, {chave: "${{ " + entrada + " }}" for chave, entrada in ENTRADAS_NO_AMBIENTE.items()}, nome)

    def test_os_nomes_do_ambiente_batem_com_as_constantes_do_script(self):
        self.assertEqual(set(ENTRADAS_NO_AMBIENTE), {
            operar_l300.VAR_FASE, operar_l300.VAR_APLICAR, operar_l300.VAR_CONECTIVIDADE, operar_l300.VAR_INGRESSO_EXTERNO,
            operar_l300.VAR_TAG, operar_l300.VAR_CONFIRMACAO, operar_l300.VAR_QUALIFICAR_NAO_SUPORTADO,
            operar_l300.VAR_QUALIFICAR_REMOVIDAS, operar_l300.VAR_PLANO_SHA256})
        self.assertEqual(self.job["environment"], operar_l300.AMBIENTE_GITHUB)
        self.assertEqual(self.job["runs-on"], list(operar_l300.RUNNER_ROTULOS))
        self.assertEqual(self.job["if"], f"github.ref == '{operar_l300.REF_PERMITIDA}' && github.event_name == 'workflow_dispatch'")
        self.assertIn(f"environments/{operar_l300.AMBIENTE_GITHUB}", "\n".join(comandos(self.job)))
        self.assertIn(f"--nome-ambiente {operar_l300.AMBIENTE_GITHUB}", "\n".join(comandos(self.job)))
        self.assertEqual(operar_l300.ARQUIVO_DO_WORKFLOW, IMPLANTAR.name)

    def test_so_o_job_de_implantacao_usa_o_runner_confiavel_o_ambiente_protegido_e_o_oidc(self):
        self.assertEqual(self.workflow["permissions"], {"contents": "read"})
        for nome, job in self.workflow["jobs"].items():
            if nome == "implantar":
                continue
            self.assertNotIn("environment", job, nome)
            self.assertNotIn("self-hosted", json.dumps(job.get("runs-on")), nome)
            self.assertNotIn("id-token", job.get("permissions", {}), nome)
        self.assertEqual(self.job["permissions"], {"contents": "read", "actions": "read", "id-token": "write"})
        self.assertEqual(self.fonte.count("id-token"), 1)
        self.assertEqual(self.fonte.count("self-hosted"), 2, "um no runs-on e um no comentário de configuração")

    def test_a_implantacao_so_roda_na_main_depois_das_entradas_e_do_ci_da_mesma_revisao(self):
        self.assertEqual(self.job["needs"], ["entradas", "ci"])
        ci = self.workflow["jobs"]["ci"]
        self.assertEqual((ci["uses"], ci["needs"], ci["permissions"]), (REUTILIZAVEL, "entradas", {"contents": "read"}))
        self.assertNotIn("secrets", ci, "o CI não recebe segredos")
        self.assertTrue((RAIZ / REUTILIZAVEL).is_file())
        for nome in ("entradas", "implantar"):
            checkout = next(p for p in passos(self.workflow["jobs"][nome]) if usa(p, "actions/checkout@"))
            self.assertEqual(checkout["with"], {"ref": "${{ github.sha }}", "persist-credentials": False}, nome)
        self.assertEqual(self.workflow["concurrency"], {"group": "l300-implantar", "cancel-in-progress": False})

    def test_a_ordem_bloqueia_antes_de_qualquer_chamada_ao_azure(self):
        validar = indice(self.job, lambda p: "--exigir-azure" in p.get("run", ""), "validar")
        mascara = indice(self.job, lambda p: "::add-mask::" in p.get("run", ""), "máscara")
        ambiente = indice(self.job, lambda p: "--etapa verificar-ambiente" in p.get("run", ""), "ambiente")
        login = indice(self.job, lambda p: usa(p, "azure/login@"), "login")
        simular = indice(self.job, lambda p: "what-if" in p.get("run", ""), "what-if")
        aplicar = indice(self.job, lambda p: "deployment group create" in p.get("run", ""), "aplicar")
        self.assertLess(indice(self.job, lambda p: usa(p, "actions/checkout@"), "checkout"), mascara)
        self.assertTrue(mascara < validar < ambiente < login < simular < aplicar, (mascara, validar, ambiente, login, simular, aplicar))
        antes_do_login = "\n".join(comandos({"steps": passos(self.job)[:login]}))
        self.assertNotRegex(antes_do_login, r"(?m)(?:^|[;&|(])\s*az\s+(login|account|deployment|group|resource|bicep|rest|ad)\b",
                            "nada fala com o Azure antes do login")
        self.assertIn("--exigir-github --exigir-oidc --exigir-azure --exportar-github-env", passos(self.job)[validar]["run"])
        usam_contexto = [posicao for posicao, passo in enumerate(passos(self.job)) if referencias_de_contexto(passo)]
        self.assertEqual(usam_contexto[0], mascara, "o passo que mascara a configuração privada é o primeiro a recebê-la")

    def test_a_configuracao_privada_vem_de_secrets_individuais_e_a_nao_privada_de_vars_enumeradas(self):
        validar = next(p for p in passos(self.job) if "--exigir-azure" in p.get("run", ""))
        mascara = next(p for p in passos(self.job) if "::add-mask::" in p.get("run", ""))
        privadas = {nome: f"${{{{ secrets.{nome} }}}}" for nome in operar_l300.VARS_PRIVADAS}
        nao_privadas = {nome: f"${{{{ vars.{nome} }}}}" for nome in operar_l300.VARS_NAO_PRIVADAS}
        self.assertEqual({k: v for k, v in validar["env"].items() if k in privadas}, privadas)
        self.assertEqual({k: v for k, v in validar["env"].items() if "vars." in str(v)}, nao_privadas)
        self.assertEqual(mascara["env"], privadas, "a máscara adicional recebe exatamente a configuração privada, de secrets")
        login = next(p for p in passos(self.job) if usa(p, "azure/login@"))
        self.assertEqual(login["with"], {"client-id": "${{ secrets.AZURE_CLIENT_ID }}", "tenant-id": "${{ secrets.AZURE_TENANT_ID }}",
                                         "subscription-id": "${{ secrets.AZURE_SUBSCRIPTION_ID }}"})
        for nome in operar_l300.VARS_PRIVADAS:
            self.assertFalse(operar_l300.nome_de_segredo(nome), f"{nome} é configuração privada, não uma credencial")
            esta_na_mascara = nome in operar_l300.VARS_DE_IDENTIDADE or re.match(r"VARELEIRA_(NOME|ID|GRUPO)_", nome)
            self.assertTrue(esta_na_mascara, f"{nome}: a máscara só enumera AZURE_* e VARELEIRA_(NOME|ID|GRUPO)_*")
        for nome in operar_l300.VARS_DE_IDENTIDADE:
            self.assertIn(nome, mascara["run"])
        self.assertIn("grep -E '^VARELEIRA_(NOME|ID|GRUPO)_'", mascara["run"])
        for variacao in ('"::add-mask::$valor"', '"::add-mask::${valor,,}"', '"::add-mask::${valor^^}"'):
            self.assertIn(variacao, mascara["run"], "GUIDs e nomes também são mascarados em minúsculas e maiúsculas")
        self.assertNotRegex(self.fonte, r"\$\{\{\s*(vars|secrets)\.\w+\s*\|\|", "campo ausente nunca vira valor padrão em silêncio")

    def test_nenhum_campo_privado_entra_por_vars_nem_por_contexto_inteiro_e_o_runner_nao_o_imprime_em_claro(self):
        # O runner imprime env e with de cada passo ANTES do run, e só mascara o que vem de secrets.
        contextos = referencias_de_contexto(self.workflow)
        de_vars = {nome for contexto, nome in contextos if contexto == "vars"}
        de_secrets = {nome for contexto, nome in contextos if contexto == "secrets"}
        self.assertEqual(de_vars, set(operar_l300.VARS_NAO_PRIVADAS))
        self.assertEqual(de_vars & set(operar_l300.VARS_PRIVADAS), set(), "campo privado vindo de vars sairia em claro no registro")
        self.assertEqual(de_secrets, set(operar_l300.VARS_PRIVADAS) | {operar_l300.VAR_SEGREDO_LOGIN})
        self.assertNotIn(None, {nome for _, nome in contextos}, "o contexto vars ou secrets inteiro (serializado) nunca é usado")
        executado = json.dumps(self.workflow, ensure_ascii=False)
        self.assertNotIn("toJSON", executado)
        self.assertNotIn(operar_l300.VAR_VARIAVEIS_JSON, self.fonte, "o JSON de vars é só para testes locais do script")
        for passo in passos(self.job):
            for chave in ("env", "with"):
                for nome, valor in (passo.get(chave) or {}).items():
                    if "vars." in str(valor):
                        self.assertIn(nome, operar_l300.VARS_NAO_PRIVADAS, passo.get("name"))

    def test_as_variaveis_do_azure_ficam_sem_valor_padrao_e_o_script_valida_tudo_antes_do_login(self):
        validar = next(p for p in passos(self.job) if "--exigir-azure" in p.get("run", ""))
        self.assertNotRegex(self.fonte, r"\$\{\{\s*(vars|secrets)\.\w+\s*(\|\||\?)")
        for nome in (*operar_l300.VARS_PRIVADAS, *operar_l300.VARS_NAO_PRIVADAS):
            self.assertIn(nome, validar["env"], f"{nome}: o script só vê o que o passo de validação recebe")

    def test_a_unica_credencial_com_segredo_e_a_do_login_da_aplicacao_so_em_tres_passos_e_so_na_fase_aplicacao(self):
        referencias = re.findall(r"secrets\.VARELEIRA_SEGREDO_LOGIN\b", json.dumps(self.workflow, ensure_ascii=False))
        self.assertEqual(len(referencias), 3)
        self.assertTrue(operar_l300.nome_de_segredo(operar_l300.VAR_SEGREDO_LOGIN))
        self.assertNotIn("secrets", json.dumps(self.workflow.get("env", {})), "nada no nível do workflow")
        com_segredo = []
        for nome, job in self.workflow["jobs"].items():
            sem_passos = {chave: valor for chave, valor in job.items() if chave != "steps"}
            self.assertNotIn("secrets", json.dumps(sem_passos), f"{nome}: nada no nível do job, onde todos os passos o veriam")
            for posicao, passo in enumerate(passos(job)):
                if "secrets.VARELEIRA_SEGREDO_LOGIN" not in json.dumps(passo):
                    continue
                com_segredo.append((nome, posicao))
                self.assertEqual(passo["env"]["VARELEIRA_SEGREDO_LOGIN"], EXPRESSAO_DO_SEGREDO_DO_LOGIN,
                                 "só na fase aplicacao; nas outras, vazio")
                credenciais = [chave for chave, valor in passo["env"].items()
                               if "secrets." in str(valor) and operar_l300.nome_de_segredo(chave)]
                self.assertEqual(credenciais, ["VARELEIRA_SEGREDO_LOGIN"], "o resto que vem de secrets é configuração privada")
                self.assertNotIn("secrets.VARELEIRA_SEGREDO_LOGIN",
                                 json.dumps({chave: valor for chave, valor in passo.items() if chave != "env"}),
                                 "só em env: nunca em run, with ou if")
        self.assertEqual(com_segredo, [
            ("implantar", indice(self.job, lambda p: "--exigir-azure" in p.get("run", ""), "validar")),
            ("implantar", indice(self.job, lambda p: "what-if" in p.get("run", ""), "simular")),
            ("implantar", indice(self.job, lambda p: "deployment group create" in p.get("run", ""), "aplicar")),
        ], "só os passos que validam, simulam e aplicam recebem o segredo")

    def test_o_segredo_do_login_nao_e_pre_requisito_do_runner_e_nunca_e_impresso_nem_exportado(self):
        todos = "\n".join(comando for job in self.workflow["jobs"].values() for comando in comandos(job))
        self.assertEqual(re.findall(r"VARELEIRA_SEGREDO_LOGIN", todos), ["VARELEIRA_SEGREDO_LOGIN"],
                         "nenhum script cita o segredo, a não ser a checagem de que o runner NÃO o tem")
        guarda = next(p for p in passos(self.job) if "VARELEIRA_SEGREDO_LOGIN" in p.get("run", ""))
        self.assertIn('if [ -n "${VARELEIRA_SEGREDO_LOGIN:-}" ]; then', guarda["run"])
        self.assertIn("exit 1", guarda["run"])
        self.assertNotIn("GITHUB_ENV", guarda["run"])
        self.assertNotIn("env", guarda, "este passo vê só o ambiente do runner, sem o mapeamento do segredo")
        self.assertLess(passos(self.job).index(guarda), indice(self.job, lambda p: "--exigir-azure" in p.get("run", ""), "validar"))

    def test_a_identidade_de_implantacao_e_o_login_da_aplicacao_nao_se_misturam(self):
        login = next(p for p in passos(self.job) if usa(p, "azure/login@"))
        self.assertEqual(set(login["with"]), {"client-id", "tenant-id", "subscription-id"})
        self.assertNotIn("env", login, "nenhum segredo no passo do login OIDC")
        analisado = json.dumps(self.workflow, ensure_ascii=False)
        for proibido in ("AZURE_CLIENT_SECRET", "AZURE_PASSWORD", "AZURE_USERNAME", "AZURE_CLIENT_CERTIFICATE", "client-secret",
                         "AZURE_CREDENTIALS"):
            self.assertNotIn(proibido, analisado)
        self.assertNotIn("VARELEIRA_SEGREDO_LOGIN", json.dumps(login))
        self.assertNotIn("SEGREDO", json.dumps({nome: job for nome, job in self.workflow["jobs"].items() if nome != "implantar"}),
                         "as entradas e o CI não recebem o segredo")

    def test_o_workflow_nunca_compila_nem_imprime_o_arquivo_de_parametros(self):
        for proibido in ("build-params", "--stdout", "bicep build", "bicep decompile"):
            self.assertNotIn(proibido, self.fonte)
        usos = [passo["run"] for passo in passos(self.job) if "--parameters" in passo.get("run", "")]
        self.assertEqual(len(usos), 2, "o arquivo de parâmetros só é passado ao az na simulação e na aplicação")
        for comando in usos:
            self.assertIn("--parameters infra/levels/l300.bicepparam", comando)
            self.assertRegex(comando, r"az deployment group (what-if|create)")

    def test_nenhum_passo_despeja_o_ambiente_nem_ativa_a_depuracao_do_shell(self):
        proibido = (r"\bset\s+-[A-Za-z]*x|xtrace|\bprintenv\b|(?m:(?:^|[;&|(])\s*env\s*(?:$|[|>;)]))|\bexport\s+-p\b|"
                    r"\bdeclare\s+-[A-Za-z]*p\b|/proc/\S*environ")
        for nome, job in self.workflow["jobs"].items():
            for comando in comandos(job):
                self.assertNotRegex(comando, proibido, nome)

    def test_a_protecao_do_ambiente_e_comprovada_pela_api_do_github_antes_do_login(self):
        passo = next(p for p in passos(self.job) if "--etapa verificar-ambiente" in p.get("run", ""))
        self.assertEqual(passo["env"], {"GH_TOKEN": "${{ github.token }}", "ATOR": "${{ github.triggering_actor }}"},
                         "nenhuma variável de atestação: só a prova lida da API libera o login")
        self.assertNotIn("AMBIENTE_APROVADO", self.fonte)
        self.assertNotRegex(passo["run"], r"(?i)atest|APROVADO|\bvars\.")
        comando = passo["run"]
        self.assertLess(comando.index('"${GITHUB_API_URL}" != "https://api.github.com"'), comando.index("curl"),
                        "o token só é enviado ao destino esperado da API do GitHub")
        self.assertIn('actions/runs/${GITHUB_RUN_ID}/approvals', comando)
        self.assertIn('environments/vareleira-l300', comando)
        self.assertEqual(comando.count("$GH_TOKEN"), 1, "o token só aparece dentro do printf que alimenta o --config do curl")
        self.assertIn("--config <(printf", comando)
        achado = re.search(r"--config <\(printf '([^']*)' \"\$GH_TOKEN\"\)", comando)
        self.assertIsNotNone(achado, "o cabeçalho sai de um printf com o token como ARGUMENTO, nunca da linha de comando do curl")
        self.assertEqual(achado.group(1), 'header = "Authorization: Bearer %s"\\n')
        self.assertNotIn("******", comando, "a máscara de exibição de uma ferramenta não pode ter virado o conteúdo do arquivo")
        self.assertNotRegex(comando, r"(?i)\baz\b|set-output|echo .*GH_TOKEN")
        self.assertEqual(self.job["permissions"]["actions"], "read")

    def test_o_plano_bruto_do_what_if_nunca_vai_para_log_nem_artefato(self):
        passo = next(p for p in passos(self.job) if "what-if" in p.get("run", ""))
        comando = passo["run"]
        self.assertIn('${RUNNER_TEMP}', comando)
        for exigido in ("umask 077", 'chmod 600 "$bruto"', '> "$bruto" 2> "$pasta/erro.txt"', "--no-pretty-print", "--output json",
                        "sanitizar-whatif", "trap 'rm -rf \"$pasta\"' EXIT"):
            self.assertIn(exigido, comando)
        self.assertNotRegex(comando, r"(?m)^\s*(cat|tee|head|tail|jq|echo|printf)\b[^\n]*\$(bruto|pasta/erro)")
        self.assertNotRegex(comando, r"\$bruto[^\n]*\|\s*(tee|cat|jq)")
        self.assertLess(comando.index("what-if"), comando.index("sanitizar-whatif"))
        self.assertIn("--rotulo", comando)
        for nome, job in self.workflow["jobs"].items():
            self.assertNotIn("GITHUB_STEP_SUMMARY", "\n".join(comandos(job)), nome)

    def test_a_aplicacao_so_acontece_com_aplicar_true_em_modo_incremental_e_revalida_os_portoes(self):
        passo = next(p for p in passos(self.job) if "deployment group create" in p.get("run", ""))
        self.assertEqual(passo["if"], "inputs.aplicar == true")
        comando = passo["run"]
        self.assertLess(comando.index("--etapa validar --exigir-github"), comando.index("az deployment group create"))
        self.assertIn("--etapa validar --exigir-github --exigir-segredo-login", comando,
                      "a aplicação revalida a presença e o formato do segredo do login antes do Azure")
        self.assertIn("--mode Incremental", comando)
        self.assertIn("--output none", comando)
        self.assertIn("--resource-group \"$VARELEIRA_GRUPO_RECURSOS\"", comando)
        self.assertEqual(self.fonte.count("az deployment group create"), 1)
        self.assertEqual(self.fonte.count("az deployment group what-if"), 1)
        self.assertNotRegex(self.fonte, r"(?i)--mode\s+Complete|\bdelete\b|\bpurge\b|group\s+delete|role\s+assignment|--what-if\b")

    def test_a_sessao_do_azure_fica_isolada_no_job_e_e_encerrada_sempre(self):
        isolar = next(p for p in passos(self.job) if "AZURE_CONFIG_DIR" in p.get("run", ""))
        self.assertIn('${RUNNER_TEMP}/azure-cli', isolar["run"])
        encerrar = passos(self.job)[-1]
        self.assertEqual(encerrar["if"], "always()")
        self.assertIn("az logout", encerrar["run"])
        self.assertLess(passos(self.job).index(isolar), indice(self.job, lambda p: usa(p, "azure/login@"), "login"))

    def test_o_runner_precisa_das_ferramentas_e_do_bicepparam_do_l300_e_diz_isso_antes_de_usar_a_nuvem(self):
        passo = next(p for p in passos(self.job) if "command -v" in p.get("run", ""))
        for ferramenta in ("az", "bicep", "python3", "curl"):
            self.assertRegex(passo["run"], rf"\b{ferramenta}\b")
        self.assertIn("infra/levels/l300.bicepparam", passo["run"])

    def test_o_comentario_de_configuracao_externa_cobre_oidc_imutavel_ambiente_novo_runner_e_as_duas_credenciais(self):
        cabecalho = re.sub(r"\s*\n#\s*", " ", self.fonte.split("name:", 1)[0])
        for trecho in ("15/07/2026", "sub imutável", "formato legado", "SEM nenhuma regra",
                       "Segredo de cliente da identidade de implantação: nunca no GitHub", "[self-hosted, linux, vareleira-l300]",
                       "não cria nem altera nada", "DUAS credenciais diferentes, que nunca se confundem",
                       "IDENTIDADE DE IMPLANTAÇÃO (quem executa o Azure)", "LOGIN DA APLICAÇÃO (quem entra no chat)", "OUTRO objeto",
                       "ÚNICA credencial com segredo", "secret VARELEIRA_SEGREDO_LOGIN", "nunca em vars", "variável efêmera",
                       "só nos três passos que precisam dele", "NÃO é pré-requisito",
                       "CONFIGURAÇÃO PRIVADA, em SECRETS individuais do ambiente protegido", "NÃO são credenciais",
                       "ANTES de executá-lo e só mascara o que vem de secrets",
                       "nunca vêm de vars nem do contexto vars serializado",
                       "CONFIGURAÇÃO NÃO PRIVADA, em variáveis (vars) do ambiente, mapeadas uma a uma",
                       "os IDs acima não são credenciais"):
            self.assertIn(trecho, cabecalho)
        self.assertNotRegex(cabecalho, r"repo:[\w.-]+/[\w.-]+:")
        self.assertNotIn("Segredos NÃO vêm do GitHub", cabecalho, "o contrato mudou: há uma única credencial com segredo")
        privadas = cabecalho.split("CONFIGURAÇÃO NÃO PRIVADA", 1)[0]
        for nome in operar_l300.VARS_PRIVADAS:
            self.assertIn(nome, privadas, f"{nome} precisa estar documentada como configuração privada")

    def test_o_workflow_passa_ao_bicep_do_l300_as_variaveis_que_ele_le(self):
        parametros = RAIZ / "infra" / "levels" / "l300.bicepparam"
        principal = RAIZ / "infra" / "l300.bicep"
        if not parametros.is_file() or not principal.is_file():
            self.skipTest("infra/l300.bicep e infra/levels/l300.bicepparam ainda não existem: o contrato da fase NÃO foi conferido")
        lidas = set(re.findall(r"readEnvironmentVariable\('([A-Z0-9_]+)'", texto(parametros)))
        # As variáveis que o workflow exporta ao Bicep precisam ser as que o bicepparam lê: do contrário, a fase escolhida
        # seria ignorada em silêncio e o Bicep usaria o padrão (rede).
        for exportada in (operar_l300.VAR_FASE, operar_l300.VAR_CONECTIVIDADE, operar_l300.VAR_INGRESSO_EXTERNO, operar_l300.VAR_TAG):
            self.assertIn(exportada, lidas, f"{exportada}: o bicepparam do L300 não a lê")
        exigidas = (*operar_l300.VARS_DE_DESTINO, *(nome for nomes in operar_l300.VARS_POR_FASE.values() for nome in nomes),
                    operar_l300.VAR_SEGREDO_LOGIN)
        for exigida in exigidas:
            self.assertIn(exigida, lidas, f"{exigida}: o workflow a exige, mas o bicepparam não a lê")
        fases = re.search(r"@allowed\(\[(.*?)\]\)\s*param fase ", texto(principal), re.S)
        self.assertIsNotNone(fases, "l300.bicep precisa declarar o parâmetro fase com @allowed")
        self.assertEqual(re.findall(r"'(\w+)'", fases.group(1)), list(operar_l300.FASES))
        self.assertNotIn("VARELEIRA_FASE", lidas, "a fase do L300 usa o prefixo VARELEIRA_L300_, para não herdar uma variável do L200")


def encontrar_bash() -> str | None:
    """Um bash que aceite substituição de processos, <(...), como o do passo de proteção: o do sistema ou o do Git for Windows."""
    candidatos: list[str | None] = []
    if os.name == "nt":
        for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramW6432"), os.environ.get("ProgramFiles(x86)")):
            if base:
                candidatos += [str(Path(base) / "Git" / "usr" / "bin" / "bash.exe"), str(Path(base) / "Git" / "bin" / "bash.exe")]
    candidatos.append(shutil.which("bash"))
    for candidato in candidatos:
        if not candidato or not Path(candidato).is_file():
            continue
        try:
            sonda = subprocess.run([candidato, "-c", "cat <(echo ok)"], capture_output=True, text=True, timeout=60, check=False)
        except (OSError, subprocess.SubprocessError):
            continue
        if sonda.returncode == 0 and sonda.stdout.strip() == "ok":
            return candidato
    return None


CURL_FALSO = """# Dublê do curl: uma função que sobrepõe o programa, registra o que recebeu e responde com os arquivos de teste. Nunca faz rede.
curl() {
  local registro="${DUBLE_REGISTRO:?}" saida="" url=""
  printf 'argv=%s\\n' "$*" >> "$registro"
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --config) printf 'config=%s\\n' "$(cat "$2")" >> "$registro"; shift 2 ;;
      --output) saida="$2"; shift 2 ;;
      --header|--max-time) shift 2 ;;
      --silent|--show-error) shift ;;
      *) url="$1"; shift ;;
    esac
  done
  printf 'url=%s\\n' "$url" >> "$registro"
  if [ -n "${DUBLE_FALHAR:-}" ]; then return 22; fi
  case "$url" in
    */approvals) cp "${DUBLE_APROVACOES:?}" "$saida" ;;
    */environments/*) cp "${DUBLE_AMBIENTE:?}" "$saida" ;;
    *) return 22 ;;
  esac
}
python3() { "${DUBLE_PYTHON:?}" "$@"; }
"""
APROVADO = [{"state": "approved", "environments": [{"name": "vareleira-l300"}], "user": {"login": "revisor"}}]
AMBIENTE_PROTEGIDO = {"name": "vareleira-l300", "can_admins_bypass": False,
                      "protection_rules": [{"type": "required_reviewers", "reviewers": [{"type": "User"}], "prevent_self_review": True}],
                      "deployment_branch_policy": {"protected_branches": False, "custom_branch_policies": True}}
AMBIENTE_SEM_REGRAS = {"name": "vareleira-l300", "protection_rules": [], "deployment_branch_policy": None, "can_admins_bypass": True}
ERRO_403 = {"message": "Resource not accessible by integration", "status": "403"}


class Bruto(str):
    """Texto gravado como está (para simular uma resposta que não é JSON), em vez de passar por json.dumps."""


class ProtecaoDoAmbienteComDubleDoCurlTests(unittest.TestCase):
    """Executa DE VERDADE o script do passo de proteção, com um curl falso que só registra o que recebeu: sem rede, sem GitHub."""

    @classmethod
    def setUpClass(cls):
        cls.bash = encontrar_bash()
        if cls.bash is None:
            raise unittest.SkipTest("precisa de um bash com substituição de processos (Linux, macOS ou Git for Windows)")
        job = carregar(IMPLANTAR)["jobs"]["implantar"]
        cls.script = next(p for p in passos(job) if "--etapa verificar-ambiente" in p.get("run", ""))["run"]

    def setUp(self):
        self._pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self._pasta.cleanup)
        self.pasta = Path(self._pasta.name)
        (self.pasta / "runner_temp").mkdir()
        (self.pasta / "passo.sh").write_text(self.script, encoding="utf-8", newline="\n")
        # O dublê é um trecho de shell que sobrepõe curl e python3 como funções e depois lê o script real do passo, sem alterá-lo.
        (self.pasta / "duble.sh").write_text(f'{CURL_FALSO}source "{(self.pasta / "passo.sh").as_posix()}"\n', encoding="utf-8",
                                             newline="\n")
        self.registro = self.pasta / "registro.txt"

    def executar(self, *, token: str, api: str = "https://api.github.com", aprovacoes=APROVADO, ambiente=AMBIENTE_PROTEGIDO,
                 extras: dict[str, str] | None = None):
        for nome, dado in (("aprovacoes.json", aprovacoes), ("ambiente.json", ambiente)):
            (self.pasta / nome).write_text(dado if isinstance(dado, Bruto) else json.dumps(dado), encoding="utf-8")
        env = operar_l300.ambiente_sem_credenciais()
        env.update({
            "PATH": os.pathsep.join([str(Path(self.bash).parent), env.get("PATH", "")]),
            "RUNNER_TEMP": (self.pasta / "runner_temp").as_posix(), "GITHUB_API_URL": api, "GITHUB_REPOSITORY": "dono/repositorio",
            "GITHUB_RUN_ID": "4242", "GH_TOKEN": token, "ATOR": "quem-disparou",
            "DUBLE_REGISTRO": self.registro.as_posix(), "DUBLE_APROVACOES": (self.pasta / "aprovacoes.json").as_posix(),
            "DUBLE_AMBIENTE": (self.pasta / "ambiente.json").as_posix(), "DUBLE_PYTHON": Path(sys.executable).as_posix(),
            "PYTHONIOENCODING": "utf-8",
            # Rede de segurança: se o dublê falhasse em interceptar, um curl de verdade não chegaria a lugar nenhum.
            "HTTPS_PROXY": "http://127.0.0.1:9", "https_proxy": "http://127.0.0.1:9", "ALL_PROXY": "http://127.0.0.1:9",
            **(extras or {}),
        })
        # Como o runner: bash --noprofile --norc -eo pipefail <arquivo com o script do passo>.
        return subprocess.run([self.bash, "--noprofile", "--norc", "-eo", "pipefail", (self.pasta / "duble.sh").as_posix()],
                              cwd=RAIZ, env=env, capture_output=True, text=True, encoding="utf-8", timeout=180, check=False)

    def exigir_bloqueio(self, resultado, token: str, descricao: str):
        """O passo precisa falhar com CODIGO_DIVERGENCIA (3), dizer que o login não será tentado e nunca imprimir o token."""
        saida = resultado.stdout + resultado.stderr
        self.assertEqual(resultado.returncode, 3, f"{descricao}: {saida.replace(token, '<token>')}")
        self.assertIn("Proteção do ambiente NÃO comprovada", saida, descricao)
        self.assertIn("o login no Azure não será tentado", saida, descricao)
        self.assertNotIn("PROTEÇÃO COMPROVADA", saida, descricao)
        self.assertNotIn(token, saida, descricao)
        return saida

    def test_o_cabecalho_authorization_chega_ao_curl_exato_sem_ir_para_a_linha_de_comando_nem_para_a_saida(self):
        token = "ghs_" + secrets.token_hex(20)
        resultado = self.executar(token=token)
        saida = resultado.stdout + resultado.stderr
        self.assertEqual(resultado.returncode, 0, saida.replace(token, "<token>"))
        registro = self.registro.read_text(encoding="utf-8").splitlines()
        configuracoes = [linha for linha in registro if linha.startswith("config=")]
        self.assertEqual(len(configuracoes), 2, "uma por consulta: as aprovações da execução e as regras do ambiente")
        self.assertTrue(all(linha == f'config=header = "Authorization: Bearer {token}"' for linha in configuracoes),
                        "o --config do curl não traz exatamente 'Authorization: Bearer <token>'")
        argumentos = [linha for linha in registro if linha.startswith("argv=")]
        self.assertEqual(len(argumentos), 2)
        self.assertFalse(any(token in linha for linha in argumentos), "o token foi parar na linha de comando do curl")
        for linha in argumentos:
            self.assertRegex(linha, r"--config /dev/fd/\d+", "a configuração é um descritor temporário, nunca um arquivo no disco")
            self.assertIn("--header Accept: application/vnd.github+json --header X-GitHub-Api-Version: 2022-11-28", linha)
            self.assertIn("--max-time 30", linha)
        self.assertEqual([linha[4:] for linha in registro if linha.startswith("url=")], [
            "https://api.github.com/repos/dono/repositorio/actions/runs/4242/approvals",
            "https://api.github.com/repos/dono/repositorio/environments/vareleira-l300"])
        self.assertNotIn(token, saida, "o token nunca é impresso")
        self.assertIn("PROTEÇÃO COMPROVADA", saida)
        self.assertEqual(list((self.pasta / "runner_temp").iterdir()), [], "as evidências baixadas são apagadas ao sair")

    def test_destino_inesperado_para_a_api_aborta_antes_de_enviar_o_token(self):
        token = "ghs_" + secrets.token_hex(20)
        resultado = self.executar(token=token, api="https://api.exemplo.invalid")
        saida = resultado.stdout + resultado.stderr
        self.assertEqual(resultado.returncode, 1, saida.replace(token, "<token>"))
        self.assertIn("Destino inesperado para a API do GitHub", saida)
        self.assertFalse(self.registro.exists(), "o curl nem chegou a ser chamado")
        self.assertNotIn(token, saida)

    def test_so_a_prova_completa_libera_o_login_e_a_atestacao_antiga_nao_muda_nada(self):
        token = "ghs_" + secrets.token_hex(20)
        antiga = {"VARELEIRA_AMBIENTE_APROVADO": "true"}  # a variável de atestação não existe mais: nada a lê
        outro_ambiente = [{**APROVADO[0], "environments": [{"name": "outro"}]}]
        casos = {
            "ambiente criado sem regras e sem aprovação": dict(aprovacoes=[], ambiente=AMBIENTE_SEM_REGRAS),
            "regras protegidas, mas sem aprovação registrada": dict(aprovacoes=[]),
            "regras protegidas, mas só aprovação de outro ambiente": dict(aprovacoes=outro_ambiente),
            "regras protegidas, mas a aprovação está pendente": dict(aprovacoes=[{**APROVADO[0], "state": "pending"}]),
            "aprovação registrada, mas sem revisores obrigatórios": dict(ambiente={**AMBIENTE_PROTEGIDO, "protection_rules": []}),
            "aprovação registrada, mas o ambiente aceita qualquer branch": dict(
                ambiente={**AMBIENTE_PROTEGIDO, "deployment_branch_policy": None}),
            "aprovações com erro 403 e regras protegidas": dict(aprovacoes=ERRO_403),
            "regras com erro 403 e aprovação registrada": dict(ambiente=ERRO_403),
            "aprovações ilegíveis": dict(aprovacoes=Bruto("{")),
            "regras ilegíveis": dict(ambiente=Bruto("isto não é json")),
            "regras incompletas (sem protection_rules)": dict(ambiente={"name": "vareleira-l300"}),
            "regras de outro ambiente": dict(ambiente={**AMBIENTE_PROTEGIDO, "name": "outro"}),
        }
        for descricao, evidencias in casos.items():
            with self.subTest(descricao):
                self.exigir_bloqueio(self.executar(token=token, extras=antiga, **evidencias), token, descricao)

    def test_curl_que_falha_deixa_as_duas_evidencias_ilegiveis_e_bloqueia_o_login(self):
        token = "ghs_" + secrets.token_hex(20)
        resultado = self.executar(token=token, extras={"DUBLE_FALHAR": "1", "VARELEIRA_AMBIENTE_APROVADO": "true"})
        saida = self.exigir_bloqueio(resultado, token, "curl falhou")
        self.assertIn("aprovações ilegivel, ambiente ilegivel", saida)
        self.assertEqual(list((self.pasta / "runner_temp").iterdir()), [], "as evidências são apagadas mesmo no bloqueio")


if __name__ == "__main__":
    unittest.main()
