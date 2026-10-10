"""Controles de segurança do Bicep do L200, conferidos sem Azure.

A maior parte lê a estrutura dos arquivos (recursos, escopos, papéis e valores de segurança), como os testes do L100.
Quando o Bicep CLI está instalado, um teste compila os arquivos e confere o lint e os parâmetros.
"""

import argparse
import functools
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path

import support  # noqa: F401  (configura o caminho dos scripts)
import lab_indexacao
from support import RAIZ

INFRA = RAIZ / "infra"
PRINCIPAL = INFRA / "l200.bicep"
IDENTIDADES = INFRA / "modules" / "l200-identidades.bicep"
APLICACAO = INFRA / "modules" / "l200-aplicacao.bicep"
PARAMETROS = INFRA / "levels" / "l200.bicepparam"
L100_PRINCIPAL = INFRA / "main.bicep"
L100_BUSCA_E_MODELOS = INFRA / "modules" / "indexacao.bicep"
CHAT = RAIZ / "scripts" / "lab_chat.py"

STORAGE_BLOB_DATA_READER = "2a2b9908-6ea1-4ae2-8e65-a410df84e7d1"
OPENAI_USER = "5e0bd9bd-7b93-4f28-af87-19fc36ad61bd"
SEARCH_INDEX_DATA_READER = "1407120a-92aa-4202-b7e9-c0e197c71c8f"
ACR_PULL = "7f951dda-4ed3-4680-a7ca-43fe172d538d"

GUID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.IGNORECASE)
TIPO_CONTAINER = "Microsoft.Storage/storageAccounts/blobServices/containers"
PAR_DE_TEXTO = r"(\w+):\s*'([^']*)'"


def ler(caminho: Path) -> str:
    """Texto do arquivo sem comentários de linha (sem tocar em textos entre aspas, como https://)."""
    return re.sub(r"('(?:[^'\\]|\\.)*')|//[^\n]*", lambda achado: achado.group(1) or "",
                  caminho.read_text(encoding="utf-8"))


def bloco(texto: str, abertura: int) -> str:
    """Conteúdo entre a chave em `abertura` e a chave que a fecha."""
    profundidade = 0
    for posicao in range(abertura, len(texto)):
        if texto[posicao] == "{":
            profundidade += 1
        elif texto[posicao] == "}":
            profundidade -= 1
            if profundidade == 0:
                return texto[abertura + 1:posicao]
    raise ValueError("chave sem fechamento")


def objeto(texto: str, cabecalho: str) -> dict[str, str]:
    """Pares chave: 'texto' do objeto que começa logo depois de `cabecalho` (uma expressão regular que termina em {)."""
    achado = re.search(cabecalho, texto)
    assert achado, cabecalho
    return dict(re.findall(PAR_DE_TEXTO, bloco(texto, achado.end() - 1)))


@dataclass
class Recurso:
    simbolo: str
    tipo: str
    versao: str
    existente: bool
    condicao: str | None
    corpo: str


def recursos(texto: str) -> dict[str, Recurso]:
    padrao = re.compile(r"^resource\s+(\w+)\s+'([^'@]+)@([^']+)'\s+(existing\s+)?=\s*(?:if\s*\((.*)\)\s*)?\{", re.M)
    return {achado.group(1): Recurso(achado.group(1), achado.group(2), achado.group(3), bool(achado.group(4)),
                                     achado.group(5), bloco(texto, achado.end() - 1))
            for achado in padrao.finditer(texto)}


def chamada_do_modulo(texto: str, simbolo: str) -> str:
    achado = re.search(rf"^module\s+{simbolo}\s+'[^']+'\s+=\s*(?:if\s*\(.*\)\s*)?\{{", texto, re.M)
    assert achado, f"módulo {simbolo} não encontrado"
    return bloco(texto, achado.end() - 1)


def parametros(texto: str) -> dict[str, str | None]:
    """Nome do parâmetro -> valor padrão em texto, ou None quando o parâmetro é obrigatório."""
    return {achado.group(1): (achado.group(2) or "").strip() or None
            for achado in re.finditer(r"^param\s+(\w+)\s+\w+(?:\s*=\s*(.*))?$", texto, re.M)}


def atribuicoes(texto: str) -> list[dict[str, str | None]]:
    """Cada atribuição de papel: GUID do papel, tipo do recurso do escopo, parâmetro do principal e condição."""
    todos = recursos(texto)
    guids = dict(re.findall(r"^var\s+(papel\w+)\s*=\s*'([0-9a-f-]{36})'", texto, re.M))
    resultado = []
    for recurso in todos.values():
        if recurso.tipo.startswith("Microsoft.Authorization/roleAssignments"):
            escopo = re.search(r"\bscope:\s*(\w+)", recurso.corpo).group(1)
            papel = re.search(r"roleDefinitionId:\s*subscriptionResourceId\(\s*'[^']+',\s*(\w+)\s*\)", recurso.corpo)
            resultado.append({
                "papel": guids[papel.group(1)],
                "escopo": todos[escopo].tipo,
                "principal": re.search(r"\bprincipalId:\s*(\w+)", recurso.corpo).group(1),
                "tipo_do_principal": re.search(r"\bprincipalType:\s*'(\w+)'", recurso.corpo).group(1),
                "condicao": recurso.condicao,
            })
    return resultado


def configuracao_da_busca(recurso: Recurso, padroes: dict[str, str | None]) -> dict[str, str]:
    """Valores que o ARM reaplica à busca, com os parâmetros trocados pelos valores padrão."""
    def valor(expressao: str) -> str:
        texto = re.search(expressao, recurso.corpo).group(1)
        return padroes.get(texto) or texto

    return {
        "sku": valor(r"sku:\s*\{\s*name:\s*(\S+)"),
        "replicas": valor(r"replicaCount:\s*(\S+)"),
        "particoes": valor(r"partitionCount:\s*(\S+)"),
        "rede": valor(r"publicNetworkAccess:\s*(\S+)"),
        "chaves_de_api_desativadas": valor(r"disableLocalAuth:\s*(\S+)"),
    }


class BaseDoL100Tests(unittest.TestCase):
    def test_armazenamento_e_modelos_so_sao_referenciados_e_nenhuma_protecao_e_reescrita(self):
        l100 = {**recursos(ler(L100_PRINCIPAL)), **recursos(ler(L100_BUSCA_E_MODELOS))}
        versoes_do_l100 = {recurso.tipo: recurso.versao for recurso in l100.values()}
        for arquivo in (PRINCIPAL, IDENTIDADES, APLICACAO):
            for recurso in recursos(ler(arquivo)).values():
                if recurso.tipo.startswith(("Microsoft.Storage/", "Microsoft.CognitiveServices/")):
                    self.assertTrue(recurso.existente, f"{recurso.simbolo} é do L100: só pode ser referenciado")
                    self.assertEqual(recurso.versao, versoes_do_l100[recurso.tipo], "mesma API do L100")
            for propriedade in ("allowSharedKeyAccess", "allowBlobPublicAccess", "minimumTlsVersion",
                                "customSubDomainName", "publicAccess", "versionUpgradeOption"):
                self.assertNotIn(propriedade, ler(arquivo), f"{arquivo.name} não reescreve a conta nem os modelos")

    def test_busca_redeclarada_repete_a_configuracao_do_l100_e_so_acrescenta_a_identidade(self):
        principal = recursos(ler(PRINCIPAL))
        busca = principal["buscaGerenciada"]
        self.assertEqual(busca.condicao, "habilitarIngestao", "sem a ingestão, a busca não é tocada")
        self.assertEqual([r.simbolo for r in principal.values()
                          if r.tipo.startswith("Microsoft.Search/") and not r.existente], ["buscaGerenciada"])
        busca_l100 = recursos(ler(L100_BUSCA_E_MODELOS))["busca"]
        self.assertEqual(busca.versao, busca_l100.versao)
        # O módulo do L100 recebe a camada de main.bicep; os outros valores dele são fixos no próprio módulo.
        self.assertEqual(configuracao_da_busca(busca, parametros(ler(PRINCIPAL))),
                         configuracao_da_busca(busca_l100, parametros(ler(L100_PRINCIPAL))),
                         "o ARM reaplica a busca inteira: os valores precisam ser os do L100, senão são revertidos")
        self.assertEqual(re.findall(r"\bidentity:\s*\{\s*type:\s*'(\w+)'", busca.corpo), ["SystemAssigned"])

    def test_etiquetas_da_busca_compartilhada_ficam_no_l100_e_as_dos_recursos_novos_sao_do_l200(self):
        principal_l100 = ler(L100_PRINCIPAL)
        esperadas_da_busca = {
            **objeto(principal_l100, r"var etiquetas = union\(\s*\{"),
            **objeto(chamada_do_modulo(principal_l100, "indexacao"), r"etiquetas: union\(etiquetas, \{"),
        }
        principal = ler(PRINCIPAL)
        self.assertEqual(objeto(principal, r"param etiquetasBusca object = \{"), esperadas_da_busca)
        self.assertEqual(esperadas_da_busca["nivel"], "L100", "a limpeza do L200 não deve alcançar a busca do L100")
        l200 = objeto(principal, r"var etiquetas = union\(\s*\{")
        self.assertEqual((l200["laboratorio"], l200["nivel"]), ("vareleira-rag", "L200"))
        todos = recursos(principal)
        self.assertIn("tags: etiquetasBusca", todos["buscaGerenciada"].corpo)
        for simbolo in ("logs", "registro", "identidadeAplicacao", "ambiente"):
            self.assertRegex(todos[simbolo].corpo, r"tags: etiquetas\b(?!Busca)")

    def test_nomes_da_base_sao_explicitos_e_nomes_vazios_sao_recusados(self):
        principal, arquivo = ler(PRINCIPAL), ler(PARAMETROS)
        for nome, minimo in (("nomeConta", 3), ("nomeBusca", 2), ("nomeModelos", 2)):
            self.assertIsNone(parametros(principal)[nome], f"{nome} sem valor padrão: um nome errado criaria outro recurso")
            self.assertRegex(principal, rf"@minLength\({minimo}\)\s*@maxLength\(\d+\)\s*param {nome} string\n")
            self.assertRegex(arquivo, rf"param {nome} = readEnvironmentVariable\('VARELEIRA_\w+', ''\)")


class PapeisTests(unittest.TestCase):
    def test_papeis_das_identidades_no_menor_escopo_e_com_ids_lidos_dos_recursos(self):
        achados = atribuicoes(ler(IDENTIDADES))
        esperado = [
            (STORAGE_BLOB_DATA_READER, TIPO_CONTAINER, "principalIdBusca"),
            (OPENAI_USER, "Microsoft.CognitiveServices/accounts", "principalIdBusca"),
            (ACR_PULL, "Microsoft.ContainerRegistry/registries", "principalIdAplicacao"),
            (SEARCH_INDEX_DATA_READER, "Microsoft.Search/searchServices", "principalIdAplicacao"),
            (OPENAI_USER, "Microsoft.CognitiveServices/accounts", "principalIdAplicacao"),
        ]
        self.assertEqual(sorted((a["papel"], a["escopo"], a["principal"]) for a in achados), sorted(esperado),
                         "só estes papéis, cada um no recurso ou contêiner de que precisa, nunca no grupo")
        self.assertEqual({a["tipo_do_principal"] for a in achados}, {"ServicePrincipal"})
        # A identidade da busca só recebe papéis com a ingestão ligada; os da aplicação são sempre atribuídos.
        self.assertEqual({a["principal"]: a["condicao"] for a in achados},
                         {"principalIdBusca": "!empty(principalIdBusca)", "principalIdAplicacao": None})
        # A quantidade informada na saída acompanha as atribuições declaradas.
        formula = re.search(r"output papeisAtribuidos int = \(empty\(principalIdBusca\) \? 0 : (\d+)\) \+ (\d+)",
                            ler(IDENTIDADES))
        self.assertEqual((int(formula.group(1)), int(formula.group(2))),
                         (sum(a["principal"] == "principalIdBusca" for a in achados),
                          sum(a["principal"] == "principalIdAplicacao" for a in achados)))
        principal = ler(PRINCIPAL)
        chamada = chamada_do_modulo(principal, "identidades")
        self.assertIn("principalIdBusca: buscaGerenciada.?identity.principalId ?? ''", chamada)
        self.assertIn("principalIdAplicacao: identidadeAplicacao.properties.principalId", chamada)
        self.assertFalse([nome for nome in parametros(principal) if nome.lower().startswith("principalid")],
                         "IDs de objeto das identidades vêm dos recursos, não de parâmetros digitados")

    def test_nome_das_atribuicoes_inclui_o_id_de_objeto_para_nao_colidir_com_atribuicoes_orfas(self):
        for recurso in recursos(ler(IDENTIDADES)).values():
            if recurso.tipo.startswith("Microsoft.Authorization/roleAssignments"):
                self.assertRegex(recurso.corpo, r"name:\s*guid\(\w+\.id, principalId\w+, papel\w+\)", recurso.simbolo)


class AplicacaoTests(unittest.TestCase):
    def test_registro_e_aplicacao_sem_chaves_nem_credenciais_de_registro(self):
        principal, aplicacao, identidades = ler(PRINCIPAL), ler(APLICACAO), ler(IDENTIDADES)
        registro = recursos(principal)["registro"]
        self.assertIn("name: 'Basic'", registro.corpo)
        self.assertIn("adminUserEnabled: false", registro.corpo)
        cabecalho = recursos(aplicacao)["aplicacao"].corpo.split("properties:")[0]
        self.assertEqual(re.findall(r"type: '(\w+)'", cabecalho), ["UserAssigned"],
                         "identidade separada: os papéis existem antes da aplicação, sem dependência circular")
        self.assertIn("identity: idIdentidade", aplicacao, "a imagem é baixada pela identidade da aplicação")
        for proibido in ("username:", "passwordSecretRef", "listCredentials", "keyVaultUrl"):
            self.assertNotIn(proibido, principal + aplicacao + identidades)
        # A única chave lida é a do workspace de logs, que a plataforma exige para enviar os logs do ambiente.
        self.assertEqual(re.findall(r"(\w+)!?\.listKeys\(\)", principal), ["logs"])
        self.assertNotIn("listKeys", aplicacao + identidades)

    def test_login_do_entra_obrigatorio_e_segredo_so_como_segredo_da_aplicacao(self):
        principal, aplicacao = ler(PRINCIPAL), ler(APLICACAO)
        autenticacao = recursos(aplicacao)["autenticacao"]
        self.assertEqual(autenticacao.tipo, "Microsoft.App/containerApps/authConfigs")
        self.assertIn("parent: aplicacao", autenticacao.corpo, "a autenticação é filha da aplicação e vai junto com ela")
        self.assertIn("unauthenticatedClientAction: acaoSemLogin", autenticacao.corpo)
        self.assertRegex(aplicacao, r"@allowed\(\[\s*'Return401'\s*'RedirectToLoginPage'\s*\]\)\s*param acaoSemLogin string")
        self.assertEqual(parametros(principal)["acaoSemLogin"], "'Return401'")
        self.assertNotIn("AllowAnonymous", principal + aplicacao, "nunca anônimo")
        caminhos = re.search(r"excludedPaths:\s*\[(.*?)\]", autenticacao.corpo, re.S).group(1).split()
        self.assertEqual(caminhos, ["'/healthz'", "'/readyz'"], "só as verificações de saúde ficam sem login")
        self.assertIn("requireHttps: true", autenticacao.corpo)
        self.assertIn("allowInsecure: false", aplicacao)
        self.assertIn("'${environment().authentication.loginEndpoint}${tenantLogin}/v2.0'", autenticacao.corpo,
                      "emissor do tenant informado")
        self.assertIn("'api://${idAplicacaoLogin}'", autenticacao.corpo)

        # O segredo de cliente: parâmetro seguro, segredo da aplicação e referência por nome; nunca variável de ambiente.
        for texto in (principal, aplicacao):
            self.assertRegex(texto, r"@secure\(\)\s*(?:@minLength\(\d+\)\s*)?param segredoLogin string")
        usos = {caminho: [linha.strip() for linha in re.findall(r"^.*\bsegredoLogin\b.*$", texto, re.M)
                          if not linha.startswith(("param", "@"))] for caminho, texto in ((PRINCIPAL, principal),
                                                                                         (APLICACAO, aplicacao))}
        self.assertEqual(usos, {PRINCIPAL: ["segredoLogin: segredoLogin"], APLICACAO: ["value: segredoLogin"]})
        self.assertRegex(aplicacao, r"secrets: \[\s*\{\s*name: nomeSegredoLogin\s*value: segredoLogin\s*\}\s*\]")
        self.assertIn("clientSecretSettingName: nomeSegredoLogin", autenticacao.corpo)
        self.assertFalse([saida for saida in re.findall(r"^output\s+.*$", principal + aplicacao, re.M)
                          if "segredoLogin" in saida])
        ambiente = re.findall(r"\{ name: '(\w+)', value: .+ \}", aplicacao)
        self.assertLessEqual({"VARELEIRA_BUSCA", "VARELEIRA_MODELOS", "VARELEIRA_INDICE", "AZURE_CLIENT_ID",
                              "VARELEIRA_EXIGIR_AUTENTICACAO", "VARELEIRA_TENANT_AUTORIZADO"}, set(ambiente))
        self.assertFalse([nome for nome in ambiente if re.search(r"SECRET|SEGREDO|SENHA|PASSWORD|TOKEN|KEY|CHAVE", nome)])
        self.assertNotIn("secretRef", aplicacao, "nenhuma variável de ambiente vem de um segredo")

    @unittest.skipUnless(CHAT.is_file(), "scripts/lab_chat.py não existe: o contrato com o chat não foi conferido")
    def test_variaveis_de_ambiente_sao_as_que_o_chat_le_e_incluem_as_obrigatorias_na_nuvem(self):
        lidas = set(re.findall(r'^VAR_\w+ = "(\w+)"', CHAT.read_text(encoding="utf-8"), re.M))
        definidas = set(re.findall(r"\{ name: '(\w+)', value: .+ \}", ler(APLICACAO)))
        self.assertEqual(definidas - lidas, set(), "o Bicep define variáveis que o chat não lê")
        self.assertLessEqual({"VARELEIRA_EXIGIR_AUTENTICACAO", "VARELEIRA_TENANT_AUTORIZADO", "VARELEIRA_BUSCA",
                              "VARELEIRA_MODELOS"}, definidas, "sem elas, o chat não inicia na nuvem")

    def test_aplicacao_so_nasce_com_entradas_validas_e_com_o_ingresso_fechado(self):
        principal, aplicacao = ler(PRINCIPAL), ler(APLICACAO)
        padroes = parametros(principal)
        self.assertEqual((padroes["implantarAplicacao"], padroes["ingressoExterno"]), ("false", "false"),
                         "a base não cobra nem expõe nada sem pedido; a aplicação nasce fechada, com a autenticação")
        self.assertRegex(principal, r"module aplicacao '[^']+' = if \(implantarAplicacao\) \{")
        self.assertIn("external: ingressoExterno", aplicacao)
        # Sem imagem, login e segredo, o módulo recusa a implantação antes de criar a aplicação.
        self.assertRegex(aplicacao, r"@minLength\(1\)\s*@maxLength\(128\)\s*param tagImagem string")
        for nome in ("idAplicacaoLogin", "tenantLogin"):
            self.assertRegex(aplicacao, rf"@minLength\(36\)\s*@maxLength\(36\)\s*param {nome} string")
        self.assertRegex(aplicacao, r"@secure\(\)\s*@minLength\(\d{2}\)\s*param segredoLogin string")
        for nome in ("tagImagem", "idAplicacaoLogin", "tenantLogin", "segredoLogin"):
            self.assertEqual(padroes[nome], "''", "vazios na base: só a etapa da aplicação os exige")
        self.assertIn("image: '${servidorRegistro}/${repositorioImagem}:${tagImagem}'", aplicacao,
                      "a imagem sai do registro que recebeu o papel AcrPull")

    def test_aplicacao_de_laboratorio_no_plano_consumption_de_zero_a_uma_replica_na_porta_8000(self):
        aplicacao = ler(APLICACAO)
        corpo = recursos(aplicacao)["aplicacao"].corpo
        self.assertIn("var portaAplicacao = 8000", aplicacao)
        self.assertIn("targetPort: portaAplicacao", corpo)
        self.assertIn("workloadProfileName: 'Consumption'", corpo)
        self.assertRegex(corpo, r"cpu: json\('0\.5'\)\s*memory: '1Gi'")
        self.assertRegex(corpo, r"minReplicas: 0\s*maxReplicas: 1")
        self.assertEqual(re.findall(r"type: '(Startup|Liveness|Readiness)'\s*httpGet: \{\s*path: '(/\w+)'", corpo),
                         [("Startup", "/healthz"), ("Liveness", "/healthz"), ("Readiness", "/readyz")])
        ambiente = recursos(ler(PRINCIPAL))["ambiente"].corpo
        self.assertIn("workloadProfileType: 'Consumption'", ambiente)
        self.assertNotIn("vnetConfiguration", ambiente, "sem rede virtual própria")
        self.assertNotIn("Dedicated", ambiente, "sem o custo fixo de um perfil dedicado")


class ParametrosEHigieneTests(unittest.TestCase):
    def test_parametros_cobrem_os_obrigatorios_e_nao_fixam_ids_nem_segredos(self):
        principal, arquivo = ler(PRINCIPAL), ler(PARAMETROS)
        self.assertIn("using '../l200.bicep'", arquivo)
        atribuidos = set(re.findall(r"^param\s+(\w+)\s*=", arquivo, re.M))
        declarados = parametros(principal)
        self.assertLessEqual(atribuidos, set(declarados), "todo parâmetro do arquivo existe em l200.bicep")
        self.assertLessEqual({nome for nome, padrao in declarados.items() if padrao is None}, atribuidos,
                             "o arquivo informa todos os parâmetros obrigatórios")
        self.assertIn("param habilitarIngestao = true", arquivo)
        for nome in ("implantarAplicacao", "ingressoExterno"):
            self.assertRegex(arquivo, rf"param {nome} = bool\(readEnvironmentVariable\('VARELEIRA_\w+', 'false'\)\)")
        for nome in ("tagImagem", "idAplicacaoLogin", "tenantLogin", "segredoLogin"):
            self.assertRegex(arquivo, rf"param {nome} = readEnvironmentVariable\('VARELEIRA_\w+', ''\)")
        for nome in ("nomeIndice", "acaoSemLogin"):
            padrao = re.search(rf"param {nome} = readEnvironmentVariable\('VARELEIRA_\w+', '([^']+)'\)", arquivo)
            self.assertEqual(f"'{padrao.group(1)}'", declarados[nome], "o padrão do arquivo repete o do Bicep")
        self.assertNotRegex(
            arquivo, r"param (?:nomeConta|nomeBusca|nomeModelos|segredoLogin|idAplicacaoLogin|tenantLogin) = '")
        # Os únicos GUIDs dos arquivos do L200 são os IDs públicos de papéis internos do Azure.
        papeis = {STORAGE_BLOB_DATA_READER, OPENAI_USER, SEARCH_INDEX_DATA_READER, ACR_PULL}
        for caminho, esperados in ((PRINCIPAL, set()), (APLICACAO, set()), (PARAMETROS, set()), (IDENTIDADES, papeis)):
            achados = {g.lower() for g in GUID.findall(caminho.read_text(encoding="utf-8"))}
            self.assertEqual(achados, esperados, caminho.name)

    def test_bicep_do_l200_nao_tem_scripts_de_implantacao_nem_exclusoes(self):
        for caminho in (PRINCIPAL, IDENTIDADES, APLICACAO, PARAMETROS):
            self.assertNotRegex(ler(caminho), r"(?i)deploymentScripts|\bdelete\b|\bremove-|\baz\s+\w+\s+delete",
                                caminho.name)


@functools.lru_cache(maxsize=1)
def localizar_bicep() -> str | None:
    """O Bicep CLI mais novo entre o do `az bicep`, o de ~/.azure e o do PATH (versões antigas não tipam as APIs novas)."""
    nome = "bicep.exe" if os.name == "nt" else "bicep"
    pastas = [os.environ.get("AZURE_CONFIG_DIR"), str(Path.home() / ".azure")]
    candidatos = {str(Path(pasta) / "bin" / nome) for pasta in pastas if pasta}
    candidatos.add(shutil.which("bicep") or "")

    def versao(executavel: str) -> tuple[int, ...]:
        try:
            saida = subprocess.run([executavel, "--version"], capture_output=True, text=True, timeout=30, check=False).stdout
        except (OSError, subprocess.SubprocessError):
            return (0,)
        achado = re.search(r"(\d+)\.(\d+)\.(\d+)", saida)
        return tuple(int(parte) for parte in achado.groups()) if achado else (0,)

    return max((c for c in candidatos if c and Path(c).is_file()), key=versao, default=None)


@unittest.skipUnless(localizar_bicep(), "Bicep CLI não encontrado: a compilação não foi conferida")
class CompilacaoTests(unittest.TestCase):
    @staticmethod
    def bicep(*argumentos: str, **ambiente: str) -> subprocess.CompletedProcess:
        variaveis = {chave: valor for chave, valor in os.environ.items() if not chave.startswith("VARELEIRA_")}
        variaveis.update(ambiente)
        return subprocess.run([localizar_bicep(), *argumentos], capture_output=True, text=True, encoding="utf-8",
                              env=variaveis, timeout=180, check=False)

    def test_arquivos_compilam_e_o_lint_nao_tem_avisos(self):
        for caminho in (PRINCIPAL, IDENTIDADES, APLICACAO):
            compilacao = self.bicep("build", str(caminho), "--stdout")
            self.assertEqual(compilacao.returncode, 0, compilacao.stderr)
            lint = self.bicep("lint", str(caminho))
            self.assertEqual((lint.stdout + lint.stderr).strip(), "", f"lint de {caminho.name}")

    def test_parametros_compilam_com_os_nomes_da_base_e_falham_sem_eles(self):
        sem_nomes = self.bicep("build-params", str(PARAMETROS), "--stdout")
        self.assertNotEqual(sem_nomes.returncode, 0, "nomes vazios são recusados antes de qualquer implantação")
        self.assertIn("minimum allowable length", sem_nomes.stderr)
        com_nomes = self.bicep("build-params", str(PARAMETROS), "--stdout", VARELEIRA_NOME_CONTA="stlabteste",
                               VARELEIRA_NOME_BUSCA="srch-lab-teste", VARELEIRA_NOME_MODELOS="ais-lab-teste")
        self.assertEqual(com_nomes.returncode, 0, com_nomes.stderr)
        valores = json.loads(json.loads(com_nomes.stdout)["parametersJson"])["parameters"]
        self.assertEqual((valores["implantarAplicacao"]["value"], valores["ingressoExterno"]["value"]), (False, False))
        self.assertTrue(valores["habilitarIngestao"]["value"])

    def test_trechos_por_pergunta_acima_do_limite_do_chat_sao_recusados_antes_de_criar_a_aplicacao(self):
        def chat_aceita(k: int) -> bool:
            try:
                lab_indexacao.validar_k(str(k))
            except argparse.ArgumentTypeError:
                return False
            return True

        aceitos = [k for k in range(-1, 101) if chat_aceita(k)]
        minimo, maximo = min(aceitos), max(aceitos)

        # Guarda do módulo da aplicação, que o ARM aplica ao criá-la: o intervalo é o que o chat aceita em VARELEIRA_K.
        guarda = json.loads(self.bicep("build", str(APLICACAO), "--stdout").stdout)["parameters"]["quantidadeTrechos"]
        self.assertEqual((guarda.get("minValue"), guarda.get("maxValue")), (minimo, maximo))

        # No modelo principal, o Bicep recusa o valor acima do limite ao compilar os parâmetros, antes de qualquer
        # implantação. O valor no limite compila: a recusa se deve só à quantidade de trechos.
        with tempfile.TemporaryDirectory() as pasta:
            infra = Path(pasta) / "infra"
            shutil.copytree(INFRA, infra)
            arquivo = infra / "levels" / "trechos.bicepparam"
            for k in (maximo, maximo + 1):
                arquivo.write_text(
                    "using '../l200.bicep'\n\nparam nomeConta = 'stlabteste'\nparam nomeBusca = 'srch-lab-teste'\n"
                    f"param nomeModelos = 'ais-lab-teste'\nparam quantidadeTrechos = {k}\n", encoding="utf-8")
                compilacao = self.bicep("build-params", str(arquivo), "--stdout")
                self.assertEqual(compilacao.returncode == 0, chat_aceita(k), f"k={k}: {compilacao.stderr}")


if __name__ == "__main__":
    unittest.main()
