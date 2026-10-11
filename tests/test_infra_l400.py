"""Controles de segurança do Bicep do L400, conferidos sem Azure.

Três camadas, todas locais (as duas últimas exigem o Bicep CLI):
1. a estrutura dos arquivos (o que é declarado, o que só é referenciado e o que nunca aparece);
2. a compilação, o lint sem avisos e o `build-params`;
3. uma simulação, sobre o modelo ARM compilado, das guardas de cada fase (os auxiliares são os dos testes do L300). Ela não cria
   nada e não substitui o Azure: as leituras do estado dos deployments existentes usam fatos informados pelo teste.
"""

import json
import re
import unittest
from unittest import mock

import support  # noqa: F401  (configura o caminho dos scripts)
import lab_acesso
import lab_ingestao
import test_infra_l300 as base_l300
from test_infra_l200 import GUID, INFRA, chamada_do_modulo, ler, localizar_bicep, parametros, recursos
from test_infra_l300 import DESCONHECIDO, GUID_ZERO, compilar, executar_bicep, simular

PRINCIPAL = INFRA / "l400.bicep"
GUARDAS = INFRA / "modules" / "l400-guardas.bicep"
PARAMETROS = INFRA / "levels" / "l400.bicepparam"
L200_APLICACAO = INFRA / "modules" / "l200-aplicacao.bicep"
GERACAO = INFRA / "modules" / "geracao.bicep"
L300_PRINCIPAL = INFRA / "l300.bicep"
CHAT = base_l300.CHAT
ARQUIVOS_L400 = (PRINCIPAL, GUARDAS)

# Nomes de mentira para os testes: nenhum ID, nome ou segredo do ambiente de ninguém.
NOMES_DE_TESTE = {
    "VARELEIRA_NOME_MODELOS": "ais-lab-teste", "VARELEIRA_NOME_BUSCA": "srch-lab-teste", "VARELEIRA_NOME_REGISTRO": "crlabteste1",
    "VARELEIRA_NOME_IDENTIDADE_APLICACAO": "id-lab-teste", "VARELEIRA_L400_NOME_AMBIENTE": "cae-lab-teste",
    "VARELEIRA_L400_MODELO_CONTINGENCIA": "modelo-de-teste", "VARELEIRA_L400_VERSAO_MODELO_CONTINGENCIA": "2000-01-01",
    "VARELEIRA_L400_SKU_CONTINGENCIA": "GlobalStandard", "VARELEIRA_L400_CAPACIDADE_CONTINGENCIA": "7",
}
PARAMETROS_OBRIGATORIOS = ("nomeModelos", "nomeBusca", "nomeRegistro", "nomeIdentidadeAplicacao", "nomeAmbiente",
                           "modeloContingencia", "versaoModeloContingencia", "skuContingencia", "capacidadeContingencia")
VARIAVEIS_DO_L200 = ["VARELEIRA_BUSCA", "VARELEIRA_MODELOS", "VARELEIRA_INDICE", "VARELEIRA_DEPLOYMENT_EMBEDDINGS",
                     "VARELEIRA_DEPLOYMENT_GERACAO", "VARELEIRA_DIMENSOES", "VARELEIRA_MODO_BUSCA", "VARELEIRA_K", "VARELEIRA_ESFORCO",
                     "AZURE_CLIENT_ID", "VARELEIRA_EXIGIR_AUTENTICACAO", "VARELEIRA_TENANT_AUTORIZADO"]
TIPOS_DECLARADOS_PELO_L400 = {"Microsoft.CognitiveServices/accounts/deployments", "Microsoft.App/containerApps",
                              "Microsoft.App/containerApps/authConfigs"}

# Os deployments existentes (L100) e o de contingência, como o ARM os devolveria a `reference()`.
MODELO, VERSAO = "modelo-de-teste", "2000-01-01"
PRINCIPAL_ID = "Microsoft.CognitiveServices/accounts/deployments|ais-lab-teste|geracao"
EMBEDDINGS_ID = "Microsoft.CognitiveServices/accounts/deployments|ais-lab-teste|embeddings"
CONTINGENCIA_ID = "Microsoft.CognitiveServices/accounts/deployments|ais-lab-teste|geracao-contingencia"


def deployment(modelo: str, versao: str) -> dict:
    return {"properties": {"model": {"name": modelo, "version": versao}}}


def fatos_l400(**mudancas) -> dict:
    fatos = {
        PRINCIPAL_ID: deployment(MODELO, VERSAO), EMBEDDINGS_ID: deployment("text-embedding-3-small", "1"),
        CONTINGENCIA_ID: deployment(MODELO, VERSAO),
        "Microsoft.ContainerRegistry/registries|crlabteste1": {"properties": {"loginServer": "crlabteste1.azurecr.io"}},
        "Microsoft.ManagedIdentity/userAssignedIdentities|id-lab-teste": {"properties": {"clientId": GUID_ZERO}},
    }
    fatos.update(mudancas)
    return fatos


def valores_l400(**extras) -> dict:
    """Parâmetros de l400.bicep de uma implantação de teste: só nomes de mentira e o GUID zerado."""
    return {"nomeModelos": "ais-lab-teste", "nomeBusca": "srch-lab-teste", "nomeRegistro": "crlabteste1",
            "nomeIdentidadeAplicacao": "id-lab-teste", "nomeAmbiente": "cae-lab-teste", "modeloContingencia": MODELO,
            "versaoModeloContingencia": VERSAO, "skuContingencia": "GlobalStandard", "capacidadeContingencia": 7, **extras}


def entradas_da_aplicacao(**extras) -> dict:
    # O segredo de teste é montado na hora e não parece um valor real.
    return {"fase": "aplicacao", "tagImagem": "v0", "idAplicacaoLogin": GUID_ZERO, "tenantLogin": GUID_ZERO,
            "segredoLogin": "s" * 24, **extras}


class ContextoL400(base_l300._Contexto):
    """O avaliador de expressões do L300, com as funções que o L400 acrescenta ao modelo ARM."""

    _FUNCOES = {"contains": lambda recipiente, item: item in recipiente, "startswith": lambda texto, prefixo: texto.startswith(prefixo),
                "greaterorequals": lambda a, b: a >= b, "lessorequals": lambda a, b: a <= b}

    def _chamada(self, nome: str, argumentos: list):
        if nome in self._FUNCOES:
            valores = [self._no(argumento) for argumento in argumentos]
            return DESCONHECIDO if DESCONHECIDO in valores else self._FUNCOES[nome](*valores)
        return super()._chamada(nome, argumentos)


def simular_l400(modelo: dict, valores: dict, fatos: dict) -> base_l300.Simulacao:
    with mock.patch.object(base_l300, "_Contexto", ContextoL400):
        return simular(modelo, valores, fatos)


# ---------------------------------------------------------------------------------------------------------------------
# Estrutura dos arquivos
# ---------------------------------------------------------------------------------------------------------------------


class EstruturaTests(unittest.TestCase):
    def test_arquivos_do_l400_sao_os_esperados_e_nao_se_misturam_com_os_do_l300(self):
        self.assertEqual({caminho.name for caminho in (INFRA / "modules").glob("l400-*.bicep")}, {"l400-guardas.bicep"})
        self.assertEqual([caminho.name for caminho in INFRA.glob("l400*")], ["l400.bicep"])
        self.assertTrue(PARAMETROS.is_file())
        self.assertNotIn("l400", ler(L300_PRINCIPAL), "o L300 não conhece o L400")

    def test_servicos_existentes_so_sao_referenciados_e_o_acesso_publico_e_os_papeis_nao_sao_tocados(self):
        for recurso in recursos(ler(PRINCIPAL)).values():
            self.assertTrue(recurso.existente, f"l400.bicep só referencia: {recurso.simbolo}")
        declarados = {recurso.tipo for caminho in (GUARDAS, GERACAO, L200_APLICACAO) for recurso in recursos(ler(caminho)).values()
                      if not recurso.existente}
        self.assertEqual(declarados, TIPOS_DECLARADOS_PELO_L400, "só o deployment filho, a aplicação e a autenticação dela")
        for caminho in (*ARQUIVOS_L400, PARAMETROS, GERACAO, L200_APLICACAO):
            texto = ler(caminho)
            self.assertNotRegex(texto, r"publicNetworkAccess|roleAssignments|deploymentScripts|Microsoft\.App/jobs|Complete",
                                f"{caminho.name}: o L400 não reaplica a base nem atribui papéis")
            self.assertNotRegex(texto, r"workloadProfileType|ProvisionedManaged|Dedicated", caminho.name)
            self.assertNotRegex(texto, r"@[0-9-]+-preview", f"{caminho.name}: só APIs estáveis")
            self.assertEqual(GUID.findall(caminho.read_text(encoding="utf-8")), [], f"{caminho.name}: nenhum ID no repositório")

    def test_contingencia_tem_modelo_versao_tipo_e_cota_explicitos_e_nunca_capacidade_provisionada(self):
        declarados = parametros(ler(PRINCIPAL))
        for nome in ("modeloContingencia", "versaoModeloContingencia", "skuContingencia", "capacidadeContingencia", *PARAMETROS_OBRIGATORIOS):
            self.assertIsNone(declarados[nome], f"{nome}: sem valor padrão, de propósito")
        principal = ler(PRINCIPAL)
        self.assertRegex(principal, r"@allowed\(\[\s*'GlobalStandard'\s*'Standard'\s*'DataZoneStandard'\s*\]\)\s*param skuContingencia string")
        self.assertRegex(principal, r"@minValue\(1\)\s*@maxValue\(1000\)\s*param capacidadeContingencia int")
        self.assertIn("versionUpgradeOption: 'NoAutoUpgrade'", ler(GERACAO), "a versão da contingência não muda sozinha")
        chamada = chamada_do_modulo(principal, "contingencia")
        for trecho in ("nomeDeploymentGeracao: nomeDeploymentContingencia", "capacidadeGeracao: capacidadeContingencia",
                       "modeloGeracao: modeloContingencia"):
            self.assertIn(trecho, chamada)
        self.assertRegex(chamada, r"dependsOn:\s*\[\s*guardas\s*\]", "a contingência só nasce depois das guardas")

    def test_aplicacao_do_l400_e_separada_da_do_l300_e_exige_login_acesso_documental_e_coordenacao(self):
        principal = ler(PRINCIPAL)
        self.assertRegex(principal, r"module aplicacao 'modules/l200-aplicacao\.bicep' = if \(fase == 'aplicacao'\)")
        chamada = chamada_do_modulo(principal, "aplicacao")
        for trecho in ("exigirAcessoDocumental: true", "exigirCoordenacao: true", "ingressoExterno: ingressoExterno",
                       "nomeIndice: perfil.nome", "dimensoes: perfil.dimensoes", "nomeDeploymentContingencia: nomeDeploymentContingencia",
                       "acaoSemLogin: acaoSemLogin"):
            self.assertIn(trecho, chamada)
        self.assertRegex(chamada, r"dependsOn:\s*\[\s*guardas\s*\]")
        padroes, antigo = parametros(principal), parametros(ler(L300_PRINCIPAL))
        self.assertEqual((padroes["ingressoExterno"], padroes["acaoSemLogin"], padroes["fase"]), ("false", "'Return401'", "'contingencia'"))
        self.assertRegex(padroes["nomeAplicacao"], r"'ca-vlr-l400-\$\{uniqueString\(resourceGroup\(\)\.id\)\}'")
        self.assertNotEqual(padroes["nomeAplicacao"], antigo["nomeAplicacao"], "a aplicação do L300 continua como referência")
        for nome in ("modoBusca", "quantidadeTrechos", "esforco"):
            self.assertEqual(padroes[nome], antigo[nome], f"{nome}: a comparação exige a mesma configuração do L300")
        self.assertNotIn("AllowAnonymous", principal)
        self.assertEqual(re.findall(r"resourceGroup\(\)\.location", principal), ["resourceGroup().location"])

    def test_perfis_de_indice_ficam_no_namespace_do_l300_e_as_dimensoes_cabem_no_modelo(self):
        compilado = compilar(PRINCIPAL)["variables"]
        perfis = compilado["perfisDeIndice"]
        self.assertEqual(set(perfis), {"referencia", "candidato"})
        for perfil in perfis.values():
            self.assertTrue(lab_acesso.indice_l300(perfil["nome"]), "só o namespace do L300 recebe o filtro de acesso documental")
            lab_ingestao_l300_nomes(perfil["nome"])
        self.assertNotEqual(perfis["referencia"]["nome"], perfis["candidato"]["nome"])
        self.assertEqual((perfis["referencia"]["dimensoes"], perfis["candidato"]["dimensoes"]), (1536, 768))
        self.assertEqual(perfis["referencia"]["nome"], lab_acesso.INDICE_PADRAO, "a referência é o índice do L300")
        limites = {modelo: (item["minimo"], item["maximo"]) for modelo, item in compilado["limitesDeDimensoes"].items()}
        self.assertEqual(limites, dict(lab_ingestao.DIMENSOES_DOS_MODELOS), "os limites do Bicep repetem os do script de ingestão")

    def test_variaveis_novas_so_existem_com_a_coordenacao_e_seguem_o_contrato_do_chat(self):
        aplicacao = ler(L200_APLICACAO)
        novas = re.findall(r"value: (.+)\s+name: '(VARELEIRA_\w+)'", aplicacao)
        self.assertEqual([nome for _, nome in novas], ["VARELEIRA_EXIGIR_COORDENACAO", "VARELEIRA_DEPLOYMENT_CONTINGENCIA"])
        self.assertEqual(novas[0][0].strip(), "'true'")
        self.assertRegex(aplicacao, r"param exigirCoordenacao bool = false\n")
        self.assertRegex(aplicacao, r"@maxLength\(64\)\s*param nomeDeploymentContingencia string = ''\n")
        self.assertNotIn("exigirCoordenacao", ler(INFRA / "l200.bicep") + ler(L300_PRINCIPAL), "L200 e L300 não passam a opção: o padrão vale")
        lidas = set(re.findall(r'^VAR_\w+ = "(\w+)"', CHAT.read_text(encoding="utf-8"), re.M)) if CHAT.is_file() else set()
        if not {nome for _, nome in novas} <= lidas:
            self.skipTest("scripts/lab_chat.py ainda não define as variáveis da coordenação: só o contrato literal foi conferido")

    def test_bicepparam_nao_fixa_ids_nem_segredos_e_toda_variavel_tem_dono_no_operar_l400(self):
        import operar_l400

        principal, arquivo = ler(PRINCIPAL), ler(PARAMETROS)
        declarados = parametros(principal)
        atribuidos = set(re.findall(r"^param\s+(\w+)\s*=", arquivo, re.M))
        self.assertIn("using '../l400.bicep'", arquivo)
        self.assertLessEqual(atribuidos, set(declarados), "todo parâmetro do arquivo existe em l400.bicep")
        self.assertLessEqual({nome for nome, padrao in declarados.items() if padrao is None}, atribuidos,
                             "o arquivo informa todos os parâmetros obrigatórios")
        lidas = set(re.findall(r"readEnvironmentVariable\('(\w+)'", arquivo))
        self.assertEqual(lidas, set(operar_l400.VARIAVEIS_DO_BICEPPARAM), "o operar_l400 conhece cada variável que o Bicep lê")
        for nome, variavel in (("ingressoExterno", "VARELEIRA_L400_INGRESSO_EXTERNO"),):
            self.assertIn(f"param {nome} = bool(readEnvironmentVariable('{variavel}', 'false'))", arquivo)
        self.assertIn("param fase = readEnvironmentVariable('VARELEIRA_L400_FASE', 'contingencia')", arquivo)
        self.assertIn("param perfilIndice = readEnvironmentVariable('VARELEIRA_L400_PERFIL_INDICE', 'referencia')", arquivo)
        for esquecida in ("VARELEIRA_L300_INGRESSO_EXTERNO", "VARELEIRA_L300_FASE", "VARELEIRA_TAG_IMAGEM", "VARELEIRA_INGRESSO_EXTERNO"):
            self.assertNotIn(esquecida, arquivo, f"{esquecida} é de outro nível: uma variável esquecida não pode mudar o L400")
        self.assertNotRegex(arquivo, r"param \w+ = '(?!contingencia|referencia)")


# ---------------------------------------------------------------------------------------------------------------------
# Compilação (exige o Bicep CLI)
# ---------------------------------------------------------------------------------------------------------------------


def lab_ingestao_l300_nomes(indice: str) -> None:
    import lab_ingestao_l300

    lab_ingestao_l300.nomes_dos_objetos(indice)  # o índice do perfil é aceito pela ferramenta de ingestão do L300


@unittest.skipUnless(localizar_bicep(), "Bicep CLI não encontrado: a compilação não foi conferida")
class CompilacaoTests(unittest.TestCase):
    def test_arquivos_compilam_e_o_lint_nao_tem_avisos(self):
        for caminho in (*ARQUIVOS_L400, L200_APLICACAO):
            compilar(caminho)
            lint = executar_bicep("lint", str(caminho))
            self.assertEqual((lint.stdout + lint.stderr).strip(), "", f"lint de {caminho.name}")

    def test_parametros_compilam_so_com_nomes_de_teste_e_destinos_ou_escolhas_vazios_sao_recusados(self):
        saida = executar_bicep("build-params", str(PARAMETROS), "--stdout", **NOMES_DE_TESTE)
        self.assertEqual(saida.returncode, 0, saida.stderr)
        texto = json.loads(saida.stdout)["parametersJson"]
        valores = json.loads(texto)["parameters"]
        self.assertEqual((valores["fase"]["value"], valores["perfilIndice"]["value"], valores["ingressoExterno"]["value"]),
                         ("contingencia", "referencia", False))
        for nome in ("segredoLogin", "tagImagem", "idAplicacaoLogin", "tenantLogin"):
            self.assertEqual(valores[nome]["value"], "", f"{nome} não é necessário na fase contingencia")
        self.assertEqual(GUID.findall(texto), [], "nenhum ID de ambiente nos parâmetros compilados")

        vazia = executar_bicep("build-params", str(PARAMETROS), "--stdout")
        self.assertNotEqual(vazia.returncode, 0)
        arquivo = PARAMETROS.read_text(encoding="utf-8").splitlines()
        recusados = {re.match(r"param (\w+)", arquivo[int(linha) - 1]).group(1)
                     for linha in re.findall(r"\.bicepparam\((\d+),\d+\) : Error BCP(?:333|033)", vazia.stderr)}
        self.assertEqual(recusados, {nome for nome in PARAMETROS_OBRIGATORIOS if nome != "capacidadeContingencia"}, vazia.stderr)
        for ambiente in ({"VARELEIRA_L400_FASE": "tudo"}, {"VARELEIRA_L400_PERFIL_INDICE": "outro"}, {"VARELEIRA_L400_SKU_CONTINGENCIA": "ProvisionedManaged"},
                         {"VARELEIRA_L400_INGRESSO_EXTERNO": "talvez"}, {"VARELEIRA_L400_PERFIL_INDICE": ""}):
            recusa = executar_bicep("build-params", str(PARAMETROS), "--stdout", **{**NOMES_DE_TESTE, **ambiente})
            self.assertNotEqual(recusa.returncode, 0, ambiente)

    def test_saidas_e_parametros_dos_modelos_compilados_nao_expoem_segredos(self):
        for caminho in (*ARQUIVOS_L400, L200_APLICACAO):
            modelo = compilar(caminho)
            for nome, saida in modelo.get("outputs", {}).items():
                self.assertNotRegex(nome, base_l300.PADRAO_SEGREDO, f"{caminho.name}: saída {nome}")
                self.assertNotRegex(json.dumps(saida), r"listKeys|primarySharedKey|segredoLogin|listCredentials", f"{caminho.name}: {nome}")
            for nome, definicao in modelo.get("parameters", {}).items():
                if re.search(r"(?i)segredo|secret|password|senha", nome):
                    self.assertEqual(definicao["type"], "securestring", f"{caminho.name}: {nome}")

    def test_guardas_compiladas_aceitam_so_verdadeiro_e_toda_fase_depende_delas(self):
        guardas = compilar(GUARDAS)["parameters"]
        self.assertEqual({nome: definicao["allowedValues"] for nome, definicao in guardas.items()},
                         {"nomesDeDeploymentsDistintos": [True], "indiceNoNamespaceDoL300": [True],
                          "dimensoesCompativeisComOModelo": [True], "contingenciaComMesmoModeloEVersao": [True]})
        self.assertEqual(compilar(GUARDAS)["resources"], [], "o módulo de guardas não cria nada")
        modelo = compilar(PRINCIPAL)
        modulos = {recurso["name"]: recurso for recurso in modelo["resources"]}
        self.assertEqual(set(modulos), {"l400-guardas", "l400-contingencia", "l400-aplicacao"})
        self.assertNotIn("condition", modulos["l400-guardas"], "as guardas valem nas duas fases")
        for nome in ("l400-contingencia", "l400-aplicacao"):
            self.assertIn("l400-guardas", " ".join(modulos[nome]["dependsOn"]), f"{nome} só nasce depois das guardas")
        self.assertEqual(set(modelo["parameters"]["fase"]["allowedValues"]), {"contingencia", "aplicacao"})
        self.assertEqual(modelo["parameters"]["capacidadeContingencia"]["minValue"], 1)

    def test_modulo_da_aplicacao_do_l200_preserva_as_variaveis_do_l200_e_do_l300_por_padrao(self):
        modelo = compilar(L200_APLICACAO)
        self.assertEqual((modelo["parameters"]["exigirCoordenacao"]["defaultValue"], modelo["parameters"]["nomeDeploymentContingencia"]["defaultValue"]),
                         (False, ""))
        base = {"nomeBusca": "b", "nomeModelos": "m", "nomeIndice": "vareleira-lar-l200", "nomeDeploymentEmbeddings": "embeddings",
                "nomeDeploymentGeracao": "geracao", "dimensoes": 1536, "modoBusca": "hibrida", "quantidadeTrechos": 3, "esforco": "low",
                "clientIdIdentidade": GUID_ZERO, "tenantLogin": GUID_ZERO, "exigirAcessoDocumental": False}
        aplicacao = next(r for r in modelo["resources"] if r["type"] == "Microsoft.App/containerApps")
        self.assertEqual(aplicacao["properties"]["template"]["containers"][0]["env"],
                         "[concat(variables('variaveisDeAmbiente'), variables('variaveisDaCoordenacao'))]")

        def variaveis(**extras) -> list[dict]:
            contexto = base_l300._Contexto({**base, **extras}, modelo["variables"], {})
            return contexto.avaliar("[concat(variables('variaveisDeAmbiente'), variables('variaveisDaCoordenacao'))]")

        padrao = variaveis(exigirCoordenacao=False, nomeDeploymentContingencia="")
        self.assertEqual([item["name"] for item in padrao], VARIAVEIS_DO_L200, "o padrão é exatamente o do L200")
        self.assertEqual(variaveis(exigirCoordenacao=False, nomeDeploymentContingencia="geracao-contingencia"), padrao,
                         "sem a coordenação, um nome de contingência não define nada")
        self.assertEqual(variaveis(exigirCoordenacao=False, nomeDeploymentContingencia="", exigirAcessoDocumental=True)[-1],
                         {"name": "VARELEIRA_EXIGIR_ACESSO_DOCUMENTAL", "value": "true"}, "a opção do L300 segue como era")
        com_coordenacao = variaveis(exigirCoordenacao=True, nomeDeploymentContingencia="geracao-contingencia")
        self.assertEqual(com_coordenacao[:len(padrao)], padrao)
        self.assertEqual(sorted(item["name"] + "=" + item["value"] for item in com_coordenacao[len(padrao):]),
                         ["VARELEIRA_DEPLOYMENT_CONTINGENCIA=geracao-contingencia", "VARELEIRA_EXIGIR_COORDENACAO=true"])
        sem_contingencia = variaveis(exigirCoordenacao=True, nomeDeploymentContingencia="")
        self.assertEqual(sem_contingencia[len(padrao):], [{"name": "VARELEIRA_EXIGIR_COORDENACAO", "value": "true"}])


# ---------------------------------------------------------------------------------------------------------------------
# Simulação das fases e das guardas (exige o Bicep CLI)
# ---------------------------------------------------------------------------------------------------------------------


@unittest.skipUnless(localizar_bicep(), "Bicep CLI não encontrado: a simulação das fases não foi conferida")
class FasesSimuladasTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.modelo = compilar(PRINCIPAL)

    def simular(self, fase: str, *, fatos: dict | None = None, **valores):
        extras = entradas_da_aplicacao() if fase == "aplicacao" else {"fase": fase}
        return simular_l400(self.modelo, valores_l400(**{**extras, **valores}), fatos_l400() if fatos is None else fatos)

    def test_cada_fase_implanta_so_os_modulos_dela_sem_violacoes_nem_valores_nao_avaliados(self):
        for fase, esperados, tipos in (("contingencia", {"l400-guardas", "l400-contingencia"}, set()),
                                       ("aplicacao", {"l400-guardas", "l400-aplicacao"}, {"Microsoft.App/containerApps",
                                                                                          "Microsoft.App/containerApps/authConfigs"})):
            simulacao = self.simular(fase)
            self.assertEqual(simulacao.modulos(), esperados, fase)
            self.assertEqual(simulacao.violacoes, [], fase)
            self.assertEqual(simulacao.nao_avaliados, [], f"{fase}: toda restrição precisa ter sido calculada")
            self.assertEqual({recurso["type"] for recurso in simulacao.recursos}, {"Microsoft.CognitiveServices/accounts/deployments"} if fase == "contingencia" else tipos)

    def test_contingencia_nasce_com_o_modelo_a_versao_e_a_cota_declarados_e_sem_tocar_no_principal(self):
        simulacao = self.simular("contingencia")
        (recurso,) = simulacao.recursos
        self.assertEqual(recurso["type"], "Microsoft.CognitiveServices/accounts/deployments")
        parametros_do_modulo = simulacao.parametros_dos_modulos["l300/l400-contingencia"]
        self.assertEqual({nome: parametros_do_modulo[nome] for nome in ("nomeDeploymentGeracao", "modeloGeracao", "versaoModeloGeracao",
                                                                       "skuDeploymentGeracao", "capacidadeGeracao")},
                         {"nomeDeploymentGeracao": "geracao-contingencia", "modeloGeracao": MODELO, "versaoModeloGeracao": VERSAO,
                          "skuDeploymentGeracao": "GlobalStandard", "capacidadeGeracao": 7})

    def test_guarda_recusa_contingencia_com_o_nome_do_principal_ou_o_do_embeddings(self):
        for nome in ("geracao", "embeddings"):
            simulacao = self.simular("contingencia", nomeDeploymentContingencia=nome)
            self.assertEqual(len(simulacao.violacoes_de("nomesDeDeploymentsDistintos")), 1, nome)
        self.assertEqual(self.simular("contingencia").violacoes_de("nomesDeDeploymentsDistintos"), [])

    def test_guarda_recusa_modelo_ou_versao_da_contingencia_diferentes_dos_do_principal(self):
        for mudanca in ({"modeloContingencia": "outro-modelo"}, {"versaoModeloContingencia": "1999-01-01"}):
            simulacao = self.simular("contingencia", **mudanca)
            self.assertEqual(len(simulacao.violacoes_de("contingenciaComMesmoModeloEVersao")), 1, mudanca)
        # Na fase aplicacao, vale também o deployment de contingência que existe: se alguém o trocou, a aplicação não nasce.
        trocado = fatos_l400(**{CONTINGENCIA_ID: deployment("outro-modelo", VERSAO)})
        self.assertEqual(len(self.simular("aplicacao", fatos=trocado).violacoes_de("contingenciaComMesmoModeloEVersao")), 1)
        sem_contingencia = {chave: valor for chave, valor in fatos_l400().items() if chave != CONTINGENCIA_ID}
        simulacao = self.simular("aplicacao", fatos=sem_contingencia)
        self.assertTrue(simulacao.nao_avaliados or simulacao.violacoes, "sem a contingência existente, a guarda não é dada por atendida")
        self.assertEqual(self.simular("contingencia", fatos=sem_contingencia).violacoes, [], "a fase contingencia não depende dela")

    def test_guarda_recusa_dimensoes_que_o_modelo_de_embeddings_existente_nao_aceita(self):
        ada = fatos_l400(**{EMBEDDINGS_ID: deployment("text-embedding-ada-002", "2")})
        self.assertEqual(self.simular("aplicacao", fatos=ada).violacoes_de("dimensoesCompativeisComOModelo"), [], "1536 cabe no ada-002")
        self.assertEqual(len(self.simular("aplicacao", fatos=ada, perfilIndice="candidato").violacoes_de("dimensoesCompativeisComOModelo")), 1,
                         "o ada-002 só aceita 1536: o candidato de 768 dimensões é recusado")
        desconhecido = fatos_l400(**{EMBEDDINGS_ID: deployment("modelo-sem-limite-conhecido", "1")})
        self.assertEqual(len(self.simular("contingencia", fatos=desconhecido).violacoes_de("dimensoesCompativeisComOModelo")), 1)

    def test_aplicacao_nasce_com_o_perfil_escolhido_flags_ligadas_e_ingresso_fechado(self):
        for perfil, indice, dimensoes in (("referencia", lab_acesso.INDICE_PADRAO, 1536), ("candidato", "vareleira-lar-l300-l400-768", 768)):
            simulacao = self.simular("aplicacao", perfilIndice=perfil)
            self.assertEqual(simulacao.violacoes, [], perfil)
            modulo = simulacao.parametros_dos_modulos["l300/l400-aplicacao"]
            self.assertEqual({nome: modulo[nome] for nome in ("nomeIndice", "dimensoes", "exigirAcessoDocumental", "exigirCoordenacao",
                                                              "ingressoExterno", "nomeDeploymentContingencia", "nomeDeploymentGeracao")},
                             {"nomeIndice": indice, "dimensoes": dimensoes, "exigirAcessoDocumental": True, "exigirCoordenacao": True,
                              "ingressoExterno": False, "nomeDeploymentContingencia": "geracao-contingencia", "nomeDeploymentGeracao": "geracao"})
        self.assertIs(self.simular("aplicacao", ingressoExterno=True).parametros_dos_modulos["l300/l400-aplicacao"]["ingressoExterno"], True)

    def test_fase_aplicacao_exige_imagem_login_e_segredo_e_cota_vazia_ou_zerada_e_recusada(self):
        for faltando in ("tagImagem", "idAplicacaoLogin", "tenantLogin", "segredoLogin"):
            simulacao = self.simular("aplicacao", **{faltando: ""})
            self.assertTrue(simulacao.violacoes_de(faltando), faltando)
        for mudanca in ({"capacidadeContingencia": 0}, {"skuContingencia": "ProvisionedManaged"}, {"modeloContingencia": ""}):
            simulacao = simular_l400(self.modelo, valores_l400(fase="contingencia", **mudanca), fatos_l400())
            nome = next(iter(mudanca))
            self.assertTrue(simulacao.violacoes_de(nome), mudanca)


if __name__ == "__main__":
    unittest.main()
