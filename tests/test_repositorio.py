import re
import unittest

import support  # noqa: F401  (configura o caminho dos scripts)
import lab_comum
import lab_geracao
import lab_indexacao
from support import RAIZ

PASTAS_PUBLICAS = ("infra", "scripts", "dados", "desafios", "docs", ".github", "requirements", "tests")
ARQUIVOS_NA_RAIZ = (
    "README.md", "DISCLAIMER.md", "SUPPORT.md", "SECURITY.md", "CONTRIBUTING.md", "CONTRIBUTORS.md",
    "CODE_OF_CONDUCT.md", "NOTICE.md", "LICENSE", "CITATION.cff",
)
EXTENSOES = {".md", ".py", ".bicep", ".bicepparam", ".json", ".txt", ".yml", ".yaml", ".cff"}
GUID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.IGNORECASE)
# Identificadores públicos de papéis internos do Azure (iguais em todos os tenants) e o GUID zerado de exemplos.
GUIDS_PERMITIDOS = {
    "ba92f5b4-2d11-453d-a403-e96b0029c9fe",  # Storage Blob Data Contributor
    "7ca78c08-252a-4471-8644-bb5ff32d4ba0",  # Search Service Contributor
    "8ebe5a00-799e-43f5-93ac-243d3dce84a7",  # Search Index Data Contributor
    "5e0bd9bd-7b93-4f28-af87-19fc36ad61bd",  # Cognitive Services OpenAI User
    "1407120a-92aa-4202-b7e9-c0e197c71c8f",  # Search Index Data Reader
    "b86a8fe4-44ce-4948-aee5-eccb2c155cd7",  # Key Vault Secrets Officer
    "00000000-0000-0000-0000-000000000000",
}


def arquivos_publicos():
    for pasta in PASTAS_PUBLICAS:
        for caminho in sorted((RAIZ / pasta).rglob("*")):
            if caminho.is_file() and caminho.suffix in EXTENSOES and "__pycache__" not in caminho.parts:
                yield caminho
    for nome in ARQUIVOS_NA_RAIZ:
        if (RAIZ / nome).is_file():
            yield RAIZ / nome


class RepositorioTests(unittest.TestCase):
    def test_bicep_mantem_os_controles_de_seguranca(self):
        bicep = (RAIZ / "infra" / "main.bicep").read_text(encoding="utf-8")
        for exigido in (
            "allowBlobPublicAccess: false",
            "allowSharedKeyAccess: false",
            "defaultToOAuthAuthentication: true",
            "minimumTlsVersion: 'TLS1_2'",
            "supportsHttpsTrafficOnly: true",
            "publicAccess: 'None'",
        ):
            self.assertIn(exigido, bicep)
        self.assertNotIn("listKeys", bicep, "o laboratório não usa chaves de conta")

    def test_parametros_do_l100_combinam_com_os_scripts_e_nao_fixam_identidades(self):
        parametros = (RAIZ / "infra" / "levels" / "l100.bicepparam").read_text(encoding="utf-8")
        self.assertIn(f"param nomeContainer = '{lab_comum.CONTAINER_PADRAO}'", parametros)
        self.assertNotRegex(parametros, r"param principalIdCarga = '[^']+'")
        self.assertNotIn("implantarIndexacao", parametros, "o Desafio 01 continua criando só o armazenamento")

    def test_bicep_do_desafio_02_mantem_so_entra_id_e_nao_lista_chaves(self):
        modulo = (RAIZ / "infra" / "modules" / "indexacao.bicep").read_text(encoding="utf-8")
        self.assertEqual(modulo.count("disableLocalAuth: true"), 2, "busca e modelos sem chaves de API")
        for proibido in ("listKeys", "listAdminKeys", "primaryKey", "queryKey"):
            self.assertNotIn(proibido, modulo)
        self.assertIn("versionUpgradeOption: 'NoAutoUpgrade'", modulo, "uma troca de versão invalidaria o índice")
        principal = (RAIZ / "infra" / "main.bicep").read_text(encoding="utf-8")
        self.assertIn("param implantarIndexacao bool = false", principal)
        for regiao in ("localizacaoBusca", "localizacaoModelos"):
            self.assertIn(f"param {regiao} string = localizacao", principal, "por padrão, a região do grupo")

    def test_parametros_do_desafio_02_ligam_a_indexacao_e_combinam_com_os_scripts(self):
        parametros = (RAIZ / "infra" / "levels" / "l100-desafio02.bicepparam").read_text(encoding="utf-8")
        self.assertIn("param implantarIndexacao = true", parametros)
        self.assertNotRegex(parametros, r"param principalIdCarga = '[^']+'")
        self.assertIn(f"param nomeDeploymentEmbeddings = '{lab_indexacao.DEPLOYMENT_PADRAO}'", parametros)
        self.assertIn("param modeloEmbeddings = 'text-embedding-3-small'", parametros)
        self.assertEqual(lab_indexacao.DIMENSOES_PADRAO, 1536, "dimensões do text-embedding-3-small")
        # Mesmos valores do Desafio 01: a implantação incremental não deve alterar o armazenamento.
        for linha in ("param nomeContainer", "param sku ", "param retencaoExclusaoDias"):
            antigo = next(l for l in (RAIZ / "infra" / "levels" / "l100.bicepparam").read_text(encoding="utf-8").splitlines()
                          if l.startswith(linha))
            self.assertIn(antigo, parametros)

    def test_bicep_do_desafio_03_so_acrescenta_um_deployment_de_versao_fixa(self):
        modulo = (RAIZ / "infra" / "modules" / "geracao.bicep").read_text(encoding="utf-8")
        self.assertIn("versionUpgradeOption: 'NoAutoUpgrade'", modulo)
        self.assertIn("accounts@2026-07-01' existing", modulo, "o recurso de modelos é do Desafio 02: aqui só é referenciado")
        for proibido in ("listKeys", "disableLocalAuth", "roleAssignments", "Microsoft.Search"):
            self.assertNotIn(proibido, modulo)
        principal = (RAIZ / "infra" / "main.bicep").read_text(encoding="utf-8")
        self.assertIn("param implantarGeracao bool = false", principal)
        self.assertRegex(principal, r"dependsOn:\s*\[\s*indexacao\s*\]", "deployments do mesmo recurso são serializados")

    def test_parametros_do_desafio_03_ligam_a_geracao_e_repetem_os_do_desafio_02(self):
        parametros = (RAIZ / "infra" / "levels" / "l100-desafio03.bicepparam").read_text(encoding="utf-8")
        self.assertIn("param implantarGeracao = true", parametros)
        self.assertIn("param implantarIndexacao = true", parametros)
        self.assertNotRegex(parametros, r"param principalIdCarga = '[^']+'")
        self.assertIn(f"param nomeDeploymentGeracao = '{lab_geracao.DEPLOYMENT_GERACAO_PADRAO}'", parametros)
        # Mesmos valores do Desafio 02: a implantação incremental não deve alterar nada do que já existe.
        antigo = (RAIZ / "infra" / "levels" / "l100-desafio02.bicepparam").read_text(encoding="utf-8").splitlines()
        for linha in (l for l in antigo if l.startswith("param ") and "principalIdCarga" not in l):
            self.assertIn(linha, parametros)

    def test_bicep_do_desafio_07_cofre_so_com_papeis_e_aplicacao_so_com_leitura(self):
        cofre = (RAIZ / "infra" / "modules" / "cofre.bicep").read_text(encoding="utf-8")
        self.assertIn("enableRbacAuthorization: true", cofre)
        self.assertIn("enableSoftDelete: true", cofre)
        self.assertIn("param protecaoContraExpurgo bool = true", cofre, "o padrão do módulo é o seguro")
        self.assertIn("enablePurgeProtection: protecaoContraExpurgo ? true : null", cofre, "o Azure não aceita false")
        for proibido in ("accessPolicies", "listKeys", "principalIdAplicacao"):
            self.assertNotIn(proibido, cofre, "a aplicação não recebe acesso ao cofre")
        aplicacao = (RAIZ / "infra" / "modules" / "aplicacao.bicep").read_text(encoding="utf-8")
        self.assertEqual(aplicacao.count("Microsoft.Authorization/roleAssignments@"), 2)
        self.assertEqual(aplicacao.count("principalType: 'ServicePrincipal'"), 2)
        for papel in ("1407120a-92aa-4202-b7e9-c0e197c71c8f", "5e0bd9bd-7b93-4f28-af87-19fc36ad61bd"):
            self.assertIn(papel, aplicacao, "consultar o índice e usar os modelos")
        for proibido in ("7ca78c08", "8ebe5a00", "ba92f5b4", "b86a8fe4", "listKeys"):
            self.assertNotIn(proibido, aplicacao, "administrar o índice, gravar nele, blobs ou segredos")
        principal = (RAIZ / "infra" / "main.bicep").read_text(encoding="utf-8")
        self.assertIn("param implantarCofre bool = false", principal)
        self.assertIn("param protecaoCofreContraExpurgo bool = true", principal)
        self.assertIn("param principalIdAplicacao string = ''", principal)

    def test_parametros_do_desafio_07_repetem_os_do_desafio_03_e_desligam_a_protecao_so_no_laboratorio(self):
        parametros = (RAIZ / "infra" / "levels" / "l100-desafio07.bicepparam").read_text(encoding="utf-8")
        self.assertIn("param implantarCofre = true", parametros)
        self.assertIn("param protecaoCofreContraExpurgo = false", parametros)
        self.assertIn("Exceção de laboratório", parametros, "a exceção tem o motivo escrito")
        self.assertNotRegex(parametros, r"param principalIdCarga = '[^']+'")
        self.assertNotRegex(parametros, r"param principalIdAplicacao = '[^']+'")
        self.assertIn("readEnvironmentVariable('VARELEIRA_ID_OBJETO_APLICACAO', '')", parametros)
        # Mesmos valores do Desafio 03: a implantação incremental não deve alterar nada do que já existe.
        antigo = (RAIZ / "infra" / "levels" / "l100-desafio03.bicepparam").read_text(encoding="utf-8").splitlines()
        for linha in (l for l in antigo if l.startswith("param ") and "principalIdCarga" not in l):
            self.assertIn(linha, parametros)

    def test_dependencias_diretas_estao_fixadas(self):
        linhas = [l for l in (RAIZ / "requirements" / "l100.txt").read_text(encoding="utf-8").splitlines()
                  if l and not l.startswith("#")]
        for pacote in ("azure-identity", "azure-keyvault-secrets", "azure-storage-blob", "azure-search-documents", "openai",
                       "agent-framework-core", "agent-framework-openai"):
            self.assertTrue(any(l.startswith(f"{pacote}==") for l in linhas), pacote)

    def test_nenhum_identificador_do_ambiente_nos_arquivos_publicos(self):
        encontrados = []
        for caminho in arquivos_publicos():
            for achado in GUID.findall(caminho.read_text(encoding="utf-8")):
                if achado.lower() not in GUIDS_PERMITIDOS:
                    encontrados.append(f"{caminho.relative_to(RAIZ)}: {achado[:8]}...")
        self.assertEqual(encontrados, [], "IDs de assinatura, tenant ou pessoas não podem ficar no repositório")


if __name__ == "__main__":
    unittest.main()
