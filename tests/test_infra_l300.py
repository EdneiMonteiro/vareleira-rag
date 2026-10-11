"""Controles de segurança do Bicep do L300, conferidos sem Azure.

Três camadas, todas locais:
1. a estrutura dos arquivos (recursos, escopos, papéis e valores de segurança), com os auxiliares dos testes do L200;
2. a compilação, o lint e o `build-params`, quando o Bicep CLI está instalado;
3. uma simulação, sobre o modelo ARM compilado, de quais módulos cada fase implanta e de como o ARM validaria os parâmetros
   de cada módulo (valores permitidos, tamanhos e limites). Ela não cria nada e não substitui o Azure: as leituras do estado
   dos recursos existentes (`reference()`) usam fatos informados pelo teste. Serve para provar, antes de qualquer
   implantação, que as guardas recusam o fechamento prematuro do acesso público.
"""

import copy
import hashlib
import ipaddress
import json
import os
import re
import subprocess
import unittest
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import support  # noqa: F401  (configura o caminho dos scripts)
from test_infra_l200 import (
    ACR_PULL,
    CHAT,
    GUID,
    INFRA,
    L100_BUSCA_E_MODELOS,
    L100_PRINCIPAL,
    OPENAI_USER,
    SEARCH_INDEX_DATA_READER,
    STORAGE_BLOB_DATA_READER,
    TIPO_CONTAINER,
    bloco,
    chamada_do_modulo,
    ler,
    localizar_bicep,
    objeto,
    parametros,
    recursos,
)

STORAGE_BLOB_DATA_CONTRIBUTOR = "ba92f5b4-2d11-453d-a403-e96b0029c9fe"
GUID_ZERO = "00000000-0000-0000-0000-000000000000"

PRINCIPAL = INFRA / "l300.bicep"
PARAMETROS = INFRA / "levels" / "l300.bicepparam"
L200_PRINCIPAL = INFRA / "l200.bicep"
L200_APLICACAO = INFRA / "modules" / "l200-aplicacao.bicep"
NOMES_DOS_MODULOS = ("rede", "endpoints", "fonte-documental", "ingestao-privada", "ambiente", "guarda-isolamento", "isolamento")
MODULOS = {nome: INFRA / "modules" / f"l300-{nome}.bicep" for nome in NOMES_DOS_MODULOS}
ARQUIVOS_L300 = (PRINCIPAL, *MODULOS.values())

MODULOS_DA_FASE = {
    "rede": {"l300-rede", "l300-endpoints", "l300-fonte-documental", "l300-ingestao-privada", "l300-ambiente"},
    "aplicacao": {"l300-aplicacao"},
    "isolar": {"l300-isolamento"},
}
TIPOS_DE_DADOS = {"Microsoft.Storage/storageAccounts", "Microsoft.Search/searchServices", "Microsoft.CognitiveServices/accounts"}
TIPOS_DA_FASE_REDE = {
    "Microsoft.Network/virtualNetworks", "Microsoft.Network/virtualNetworks/subnets", "Microsoft.Network/privateDnsZones",
    "Microsoft.Network/privateDnsZones/virtualNetworkLinks", "Microsoft.Network/privateEndpoints",
    "Microsoft.Network/privateEndpoints/privateDnsZoneGroups", "Microsoft.Storage/storageAccounts/blobServices/containers",
    "Microsoft.Authorization/roleAssignments", "Microsoft.Search/searchServices/sharedPrivateLinkResources",
    "Microsoft.App/managedEnvironments",
}
TIPOS_DA_FASE_APLICACAO = {"Microsoft.App/containerApps", "Microsoft.App/containerApps/authConfigs"}

# Nomes de mentira para os testes: nenhum ID, nome ou segredo do ambiente de ninguém.
NOMES_DE_TESTE = {
    "VARELEIRA_NOME_CONTA": "stlabteste", "VARELEIRA_NOME_BUSCA": "srch-lab-teste", "VARELEIRA_NOME_MODELOS": "ais-lab-teste",
    "VARELEIRA_NOME_REGISTRO": "crlabteste1", "VARELEIRA_NOME_IDENTIDADE_APLICACAO": "id-lab-teste",
    "VARELEIRA_NOME_WORKSPACE_LOGS": "log-lab-teste", "VARELEIRA_ID_OBJETO_CARGA": GUID_ZERO,
}
PARAMETROS_DE_DESTINO = ("nomeConta", "nomeBusca", "nomeModelos", "nomeRegistro", "nomeIdentidadeAplicacao", "nomeWorkspaceLogs",
                         "principalIdCarga")
PADRAO_SEGREDO = r"(?i)SECRET|SEGREDO|SENHA|PASSWORD|TOKEN|KEY|CHAVE"
GUARDAS = ("conectividadePrivadaValidada", "estadoLinkArmazenamento", "estadoLinkModelos", "configuracaoBuscaConfere",
           "configuracaoArmazenamentoConfere")


def propriedades_simples(corpo: str, nome: str) -> dict[str, str]:
    """Pares `chave: valor` (de uma linha) do objeto `nome: { ... }` dentro de `corpo`."""
    achado = re.search(rf"\b{nome}:\s*\{{", corpo)
    assert achado, nome
    return {chave: valor for chave, valor in re.findall(r"^\s*(\w+):\s*(.+?)\s*$", bloco(corpo, achado.end() - 1), re.M)}


# ---------------------------------------------------------------------------------------------------------------------
# Simulação do ARM sobre o modelo compilado
# ---------------------------------------------------------------------------------------------------------------------


class _Desconhecido:
    def __repr__(self) -> str:
        return "<desconhecido>"


DESCONHECIDO = _Desconhecido()
_TOKEN = re.compile(r"\s*(?:'((?:[^']|'')*)'|(-?\d+)|([A-Za-z_]\w*)|([()\[\],.]))")


def _tokens(expressao: str) -> list[tuple[str, object]]:
    resultado, posicao = [], 0
    while expressao[posicao:].strip():
        achado = _TOKEN.match(expressao, posicao)
        if not achado:
            raise ValueError(f"expressão ARM não reconhecida na posição {posicao}: {expressao!r}")
        texto, numero, nome, simbolo = achado.groups()
        if texto is not None:
            resultado.append(("lit", texto.replace("''", "'")))
        elif numero is not None:
            resultado.append(("lit", int(numero)))
        else:
            resultado.append(("id", nome) if nome is not None else ("sym", simbolo))
        posicao = achado.end()
    return resultado


class _Analisador:
    """Analisa as expressões do modelo ARM: textos, números, chamadas de função, `.propriedade` e `[indice]`."""

    def __init__(self, expressao: str):
        self.tokens, self.posicao = _tokens(expressao), 0

    def _proximo(self):
        return self.tokens[self.posicao] if self.posicao < len(self.tokens) else (None, None)

    def _consumir(self, tipo: str, valor: object | None = None):
        achado = self._proximo()
        if achado[0] != tipo or (valor is not None and achado[1] != valor):
            raise ValueError(f"esperado {tipo} {valor!r}, encontrado {achado!r}")
        self.posicao += 1
        return achado[1]

    def analisar(self):
        no = self._expressao()
        if self.posicao != len(self.tokens):
            raise ValueError("sobrou texto depois da expressão")
        return no

    def _expressao(self):
        tipo, valor = self._proximo()
        if tipo == "lit":
            self.posicao += 1
            no = ("lit", valor)
        elif tipo == "id":
            self.posicao += 1
            self._consumir("sym", "(")
            argumentos = []
            if self._proximo() != ("sym", ")"):
                argumentos.append(self._expressao())
                while self._proximo() == ("sym", ","):
                    self.posicao += 1
                    argumentos.append(self._expressao())
            self._consumir("sym", ")")
            no = ("chamada", valor, argumentos)
        else:
            raise ValueError(f"início de expressão inesperado: {tipo} {valor!r}")
        while self._proximo() in (("sym", "."), ("sym", "[")):
            if self._consumir("sym") == ".":
                no = ("prop", no, self._consumir("id"))
            else:
                no = ("indice", no, self._expressao())
                self._consumir("sym", "]")
        return no


@dataclass
class _Contexto:
    parametros: dict
    variaveis: dict
    fatos: dict
    cache: dict = field(default_factory=dict)

    def avaliar(self, valor):
        """Avalia um valor do modelo ARM: textos entre colchetes são expressões; listas e objetos são percorridos."""
        if isinstance(valor, str):
            if valor.startswith("[[") or not (valor.startswith("[") and valor.endswith("]")):
                return valor
            return self._no(_Analisador(valor[1:-1]).analisar())
        if isinstance(valor, list):
            return [self.avaliar(item) for item in valor]
        if isinstance(valor, dict):
            return {chave: self.avaliar(item) for chave, item in valor.items()}
        return valor

    def _no(self, no):
        if no[0] == "lit":
            return no[1]
        if no[0] == "prop":
            base = self._no(no[1])
            return base.get(no[2], DESCONHECIDO) if isinstance(base, dict) else DESCONHECIDO
        if no[0] == "indice":
            base, indice = self._no(no[1]), self._no(no[2])
            try:
                return DESCONHECIDO if DESCONHECIDO in (base, indice) else base[indice]
            except (KeyError, IndexError, TypeError):
                return DESCONHECIDO
        return self._chamada(no[1].lower(), no[2])

    def _chamada(self, nome: str, argumentos: list):
        # Funções que não avaliam todos os argumentos: o ARM só avalia o ramo escolhido de `if`.
        if nome == "if":
            condicao = self._no(argumentos[0])
            return DESCONHECIDO if condicao is DESCONHECIDO else self._no(argumentos[1] if condicao else argumentos[2])
        if nome in ("and", "or"):
            valores, decisivo = [self._no(argumento) for argumento in argumentos], nome == "or"
            if any(valor is not DESCONHECIDO and bool(valor) == decisivo for valor in valores):
                return decisivo
            return DESCONHECIDO if DESCONHECIDO in valores else not decisivo
        if nome == "coalesce":
            for argumento in argumentos:
                valor = self._no(argumento)
                if valor is DESCONHECIDO or valor is not None:
                    return valor
            return None
        valores = [self._no(argumento) for argumento in argumentos]
        if nome == "parameters":
            return self.parametros.get(valores[0], DESCONHECIDO)
        if nome == "variables":
            if valores[0] not in self.cache:
                self.cache[valores[0]] = self.avaliar(self.variaveis[valores[0]]) if valores[0] in self.variaveis else DESCONHECIDO
            return self.cache[valores[0]]
        if nome in ("null", "true", "false"):
            return {"null": None, "true": True, "false": False}[nome]
        if nome == "resourcegroup":
            return {"id": "grupo-de-teste", "name": "rg-teste", "location": "brazilsouth"}
        if nome == "environment":
            return {"suffixes": {"storage": "core.windows.net"}}
        if nome == "createarray":
            return list(valores)
        if nome == "resourceid":
            return "|".join(map(str, valores)) if valores and DESCONHECIDO not in valores else DESCONHECIDO
        if nome == "reference":
            achado = DESCONHECIDO if DESCONHECIDO in valores else self.fatos.get(valores[0], DESCONHECIDO)
            return achado if achado is DESCONHECIDO or "full" in valores[2:] else achado.get("properties", {})
        if nome == "tryget":
            atual = valores[0]
            for chave in valores[1:]:
                if atual is DESCONHECIDO:
                    return DESCONHECIDO
                atual = atual.get(chave) if isinstance(atual, dict) else None
            return atual
        if DESCONHECIDO in valores:
            return DESCONHECIDO
        funcoes = {
            "equals": lambda a, b: a == b, "not": lambda a: not a, "empty": lambda a: a in (None, "", [], {}),
            "int": int, "string": str, "split": lambda texto, separador: texto.split(separador),
            "concat": lambda *itens: [i for lista in itens for i in lista] if all(isinstance(x, list) for x in itens)
            else "".join(map(str, itens)),
            "format": lambda formato, *itens: re.sub(r"\{(\d+)\}", lambda m: str(itens[int(m.group(1))]), formato),
            "union": lambda *itens: {k: v for item in itens for k, v in item.items()},
            "uniquestring": lambda *itens: hashlib.sha256("|".join(map(str, itens)).encode()).hexdigest()[:13],
            "createobject": lambda *itens: {itens[i]: itens[i + 1] for i in range(0, len(itens), 2)},
        }
        return funcoes[nome](*valores) if nome in funcoes else DESCONHECIDO


def _problemas_de_restricao(definicao: dict, valor) -> list[str]:
    """Violações que o ARM acusaria para `valor`. Valores seguros não são ecoados."""
    tipo = str(definicao.get("type", "")).lower()
    problemas, permitidos = [], definicao.get("allowedValues")
    if permitidos is not None and not any(type(item) is type(valor) and item == valor for item in permitidos):
        problemas.append(f"{'<oculto>' if tipo == 'securestring' else repr(valor)} fora dos valores permitidos")
    if tipo in ("string", "securestring") and isinstance(valor, str):
        if len(valor) < definicao.get("minLength", 0):
            problemas.append(f"menos de {definicao['minLength']} caracteres")
        if len(valor) > definicao.get("maxLength", len(valor)):
            problemas.append(f"mais de {definicao['maxLength']} caracteres")
    if tipo == "int" and isinstance(valor, int) and not isinstance(valor, bool):
        if valor < definicao.get("minValue", valor) or valor > definicao.get("maxValue", valor):
            problemas.append(f"{valor} fora dos limites {definicao.get('minValue')}..{definicao.get('maxValue')}")
    return problemas


@dataclass
class Simulacao:
    violacoes: list[str] = field(default_factory=list)  # o que o ARM recusaria
    nao_avaliados: list[str] = field(default_factory=list)  # valores com restrição que a simulação não conseguiu calcular
    modulos_ativos: list[str] = field(default_factory=list)
    recursos: list[dict] = field(default_factory=list)
    parametros_dos_modulos: dict[str, dict] = field(default_factory=dict)

    def violacoes_de(self, parametro: str) -> list[str]:
        return [texto for texto in self.violacoes if f": {parametro} " in texto]

    def modulos(self) -> set[str]:
        return {caminho.split("/")[1] for caminho in self.modulos_ativos}


def simular(modelo: dict, valores: dict, fatos: dict | None = None) -> Simulacao:
    """Simula, sobre o modelo compilado, a validação dos parâmetros e a escolha dos módulos de uma implantação."""
    resultado = Simulacao()
    _percorrer(modelo, valores, fatos or {}, "l300", resultado)
    return resultado


def _percorrer(modelo: dict, entrada: dict, fatos: dict, caminho: str, resultado: Simulacao) -> None:
    sem_parametros, resolvidos = _Contexto({}, modelo.get("variables", {}), fatos), {}
    for nome, definicao in modelo.get("parameters", {}).items():
        if nome in entrada:
            valor = entrada[nome]
        elif "defaultValue" in definicao:
            valor = sem_parametros.avaliar(definicao["defaultValue"])
        else:
            resultado.violacoes.append(f"{caminho}: {nome} é obrigatório e não recebeu valor")
            continue
        resolvidos[nome] = valor
        if valor is not DESCONHECIDO:
            resultado.violacoes.extend(f"{caminho}: {nome} {problema}" for problema in _problemas_de_restricao(definicao, valor))
        elif any(chave in definicao for chave in ("allowedValues", "minLength", "maxLength", "minValue", "maxValue")):
            resultado.nao_avaliados.append(f"{caminho}: {nome}")
    contexto = _Contexto(resolvidos, modelo.get("variables", {}), fatos)
    for recurso in modelo.get("resources", []):
        ativo = True if "condition" not in recurso else contexto.avaliar(recurso["condition"])
        if ativo is DESCONHECIDO:
            resultado.nao_avaliados.append(f"{caminho}: condição de {recurso['name']}")
        elif not ativo:
            continue
        if recurso["type"] != "Microsoft.Resources/deployments":
            resultado.recursos.append(recurso)
            continue
        interno = f"{caminho}/{contexto.avaliar(recurso['name'])}"
        resultado.modulos_ativos.append(interno)
        valores_internos = {}
        for parametro, definicao in recurso["properties"].get("parameters", {}).items():
            # Uma expressão devolve o objeto inteiro ({"value": ...}), quando o valor depende de uma condição.
            bruto = contexto.avaliar(definicao) if isinstance(definicao, str) else {"value": contexto.avaliar(definicao["value"])}
            valores_internos[parametro] = bruto.get("value", DESCONHECIDO) if isinstance(bruto, dict) else DESCONHECIDO
        resultado.parametros_dos_modulos[interno] = valores_internos
        _percorrer(recurso["properties"]["template"], valores_internos, fatos, interno, resultado)


# ---------------------------------------------------------------------------------------------------------------------
# Bicep CLI e cenários de teste
# ---------------------------------------------------------------------------------------------------------------------


def executar_bicep(*argumentos: str, **ambiente: str) -> subprocess.CompletedProcess:
    variaveis = {chave: valor for chave, valor in os.environ.items() if not chave.startswith("VARELEIRA_")}
    variaveis.update(ambiente)
    return subprocess.run([localizar_bicep(), *argumentos], capture_output=True, text=True, encoding="utf-8",
                          env=variaveis, timeout=180, check=False)


@lru_cache(maxsize=None)
def compilar(caminho: Path) -> dict:
    compilacao = executar_bicep("build", str(caminho), "--stdout")
    assert compilacao.returncode == 0, compilacao.stderr
    return json.loads(compilacao.stdout)


def valores_de_teste(**extras) -> dict:
    """Parâmetros de l300.bicep de uma implantação de teste: só nomes de mentira e o GUID zerado."""
    return {"nomeConta": "stlabteste", "nomeBusca": "srch-lab-teste", "nomeModelos": "ais-lab-teste", "nomeRegistro": "crlabteste1",
            "nomeIdentidadeAplicacao": "id-lab-teste", "nomeWorkspaceLogs": "log-lab-teste", "principalIdCarga": GUID_ZERO, **extras}


def entradas_de_aplicacao(**extras) -> dict:
    # O segredo de teste é montado na hora e não parece um valor real.
    return {"tagImagem": "v0", "idAplicacaoLogin": GUID_ZERO, "tenantLogin": GUID_ZERO, "segredoLogin": "s" * 24, **extras}


def configuracao_atual(**extras) -> dict:
    return {"skuArmazenamento": "Standard_LRS", "skuBusca": "basic", "replicasBusca": 1, "particoesBusca": 1, **extras}


SPL_BLOB = "Microsoft.Search/searchServices/sharedPrivateLinkResources|srch-lab-teste|spl-blob-vlr-l300"
SPL_MODELOS = "Microsoft.Search/searchServices/sharedPrivateLinkResources|srch-lab-teste|spl-modelos-vlr-l300"
BUSCA = "Microsoft.Search/searchServices|srch-lab-teste"
ARMAZENAMENTO = "Microsoft.Storage/storageAccounts|stlabteste"


def fatos_de_teste() -> dict:
    """Estado simulado dos recursos existentes, como o ARM o devolveria a `reference()`."""
    return {
        BUSCA: {"sku": {"name": "basic"}, "identity": {"principalId": GUID_ZERO},
                "properties": {"replicaCount": 1, "partitionCount": 1}},
        ARMAZENAMENTO: {"sku": {"name": "Standard_LRS"}, "properties": {}},
        SPL_BLOB: {"properties": {"status": "Approved"}},
        SPL_MODELOS: {"properties": {"status": "Approved"}},
        "Microsoft.ContainerRegistry/registries|crlabteste1": {"properties": {"loginServer": "crlabteste1.azurecr.io"}},
        "Microsoft.ManagedIdentity/userAssignedIdentities|id-lab-teste": {"properties": {"clientId": GUID_ZERO}},
    }


# ---------------------------------------------------------------------------------------------------------------------
# Estrutura dos arquivos
# ---------------------------------------------------------------------------------------------------------------------


class EstruturaTests(unittest.TestCase):
    def test_arquivos_do_l300_sao_exatamente_os_esperados(self):
        encontrados = {caminho.name for caminho in (INFRA / "modules").glob("l300-*.bicep")}
        self.assertEqual(encontrados, {f"l300-{nome}.bicep" for nome in NOMES_DOS_MODULOS},
                         "sobrou ou faltou um módulo do L300 (arquivos de experimento não ficam no repositório)")
        self.assertEqual([caminho.name for caminho in INFRA.glob("l300*")], ["l300.bicep"])
        self.assertTrue(PARAMETROS.is_file())

    def test_apis_dos_servicos_reaproveitados_sao_as_do_l100_e_do_l200_e_nenhuma_etapa_remove_recursos(self):
        versoes = {}
        for arquivo in (L100_PRINCIPAL, L100_BUSCA_E_MODELOS, L200_PRINCIPAL, L200_APLICACAO, INFRA / "modules" / "l200-identidades.bicep"):
            for recurso in recursos(ler(arquivo)).values():
                versoes.setdefault(recurso.tipo, set()).add(recurso.versao)
        rede = {}
        for arquivo in ARQUIVOS_L300:
            for recurso in recursos(ler(arquivo)).values():
                if recurso.tipo.startswith("Microsoft.Network/"):
                    rede.setdefault(recurso.tipo, set()).add(recurso.versao)
                    continue
                tipo = recurso.tipo  # um recurso filho novo usa a API do serviço pai
                while tipo not in versoes:
                    self.assertIn("/", tipo.removeprefix("Microsoft."), f"{arquivo.name}: {recurso.tipo} sem API de referência")
                    tipo = tipo.rsplit("/", 1)[0]
                self.assertIn(recurso.versao, versoes[tipo], f"{arquivo.name}: {recurso.tipo}")
        self.assertEqual(rede, {
            "Microsoft.Network/virtualNetworks": {"2026-01-01"}, "Microsoft.Network/virtualNetworks/subnets": {"2026-01-01"},
            "Microsoft.Network/privateEndpoints": {"2026-01-01"}, "Microsoft.Network/privateEndpoints/privateDnsZoneGroups": {"2026-01-01"},
            "Microsoft.Network/privateDnsZones": {"2024-06-01"}, "Microsoft.Network/privateDnsZones/virtualNetworkLinks": {"2024-06-01"}})
        for arquivo in (*ARQUIVOS_L300, PARAMETROS):
            texto = ler(arquivo)
            self.assertNotRegex(texto, r"@[0-9-]+-preview", f"{arquivo.name}: só APIs estáveis")
            self.assertNotRegex(texto, r"(?i)deploymentScripts|\bdelete\b|\bremove-|\baz\s+\w+\s+delete|Complete", arquivo.name)

    def test_servicos_existentes_so_sao_referenciados_e_so_o_isolamento_mexe_em_acesso_publico(self):
        for recurso in recursos(ler(PRINCIPAL)).values():
            self.assertTrue(recurso.existente, f"l300.bicep só referencia: {recurso.simbolo}")
        for nome, caminho in MODULOS.items():
            texto = ler(caminho)
            if nome != "isolamento":
                for recurso in recursos(texto).values():
                    if recurso.tipo in TIPOS_DE_DADOS:
                        self.assertTrue(recurso.existente, f"{caminho.name}: {recurso.simbolo} é de outro nível")
            if nome not in ("isolamento", "ambiente"):
                self.assertNotIn("publicNetworkAccess", texto, f"{caminho.name} não mexe em acesso público")
        self.assertNotIn("publicNetworkAccess", ler(PRINCIPAL))

    def test_isolamento_repete_a_configuracao_completa_do_l100_e_do_l200_e_so_fecha_o_acesso_publico(self):
        isolamento = recursos(ler(MODULOS["isolamento"]))
        self.assertEqual(set(isolamento), {"conta", "busca", "modelos"})
        l100 = {**recursos(ler(L100_PRINCIPAL)), **recursos(ler(L100_BUSCA_E_MODELOS))}
        origem = {"conta": l100["conta"], "busca": recursos(ler(L200_PRINCIPAL))["buscaGerenciada"], "modelos": l100["modelos"]}
        for simbolo, recurso in isolamento.items():
            self.assertFalse(recurso.existente)
            self.assertIsNone(recurso.condicao)
            self.assertEqual((recurso.tipo, recurso.versao), (origem[simbolo].tipo, origem[simbolo].versao),
                             "mesma API: o que o PUT omite volta ao padrão")
            atual, esperada = (propriedades_simples(r.corpo, "properties") for r in (recurso, origem[simbolo]))
            self.assertEqual((esperada.pop("publicNetworkAccess"), atual.pop("publicNetworkAccess")), ("'Enabled'", "'Disabled'"))
            self.assertEqual(atual, esperada, f"{simbolo}: a única mudança é o acesso público")
            self.assertRegex(recurso.corpo, r"dependsOn:\s*\[\s*guarda\s*\]", f"{simbolo} só muda depois das guardas")
        self.assertIn("kind: 'StorageV2'", isolamento["conta"].corpo)
        self.assertIn("kind: 'AIServices'", isolamento["modelos"].corpo)
        self.assertRegex(isolamento["modelos"].corpo, r"sku:\s*\{\s*name: 'S0'\s*\}")
        self.assertRegex(isolamento["busca"].corpo, r"identity:\s*\{\s*type: 'SystemAssigned'\s*\}")
        self.assertRegex(isolamento["conta"].corpo, r"sku:\s*\{\s*name: skuArmazenamento\s*\}")
        self.assertRegex(isolamento["busca"].corpo, r"sku:\s*\{\s*name: skuBusca\s*\}")

    def test_etiquetas_padrao_dos_servicos_existentes_repetem_as_do_l100(self):
        l100, principal = ler(L100_PRINCIPAL), ler(PRINCIPAL)
        base = objeto(l100, r"var etiquetas = union\(\s*\{")
        modulo = objeto(chamada_do_modulo(l100, "indexacao"), r"etiquetas: union\(etiquetas, \{")
        self.assertEqual(objeto(principal, r"param etiquetasArmazenamento object = \{"), base)
        self.assertEqual(objeto(principal, r"param etiquetasBusca object = \{"), {**base, **modulo})
        self.assertEqual(objeto(principal, r"param etiquetasModelos object = \{"), {**base, **modulo})
        self.assertEqual((base["nivel"], objeto(principal, r"var etiquetas = union\(\s*\{")["nivel"]), ("L100", "L300"),
                         "o L300 não reclassifica os serviços do L100 e marca só o que cria")

    def test_destinos_existentes_nao_tem_valor_padrao_e_os_nomes_novos_levam_o_prefixo_l300(self):
        principal, arquivo = ler(PRINCIPAL), ler(PARAMETROS)
        declarados = parametros(principal)
        minimos = dict(zip(PARAMETROS_DE_DESTINO, (3, 2, 2, 5, 3, 4, 36)))
        for nome, minimo in minimos.items():
            self.assertIsNone(declarados[nome], f"{nome}: sem valor padrão, de propósito")
            self.assertRegex(principal, rf"@minLength\({minimo}\)\s*@maxLength\(\d+\)\s*param {nome} string\n")
            self.assertRegex(arquivo, rf"param {nome} = readEnvironmentVariable\('VARELEIRA_\w+', ''\)")
        for nome in ("nomeRede", "nomeAmbiente", "nomeAplicacao"):
            self.assertRegex(declarados[nome], r"'[a-z]+-vlr-l300-\$\{uniqueString\(resourceGroup\(\)\.id\)\}'", nome)
        antigo = parametros(ler(L200_PRINCIPAL))
        for nome in ("nomeAmbiente", "nomeAplicacao"):
            self.assertNotEqual(declarados[nome], antigo[nome], "o ambiente e a aplicação do L300 não colidem com os do L200")
        self.assertEqual((declarados["nomeContainer"], declarados["nomeIndice"]), ("'base-documental-l300'", "'vareleira-lar-l300'"))
        self.assertEqual(re.findall(r"resourceGroup\(\)\.location", principal), ["resourceGroup().location"],
                         "a região do grupo só aparece como padrão do parâmetro")

    def test_parametros_do_nivel_nao_fixam_ids_nem_segredos_e_os_portoes_nascem_fechados(self):
        principal, arquivo = ler(PRINCIPAL), ler(PARAMETROS)
        declarados = parametros(principal)
        self.assertIn("using '../l300.bicep'", arquivo)
        atribuidos = set(re.findall(r"^param\s+(\w+)\s*=", arquivo, re.M))
        self.assertLessEqual(atribuidos, set(declarados), "todo parâmetro do arquivo existe em l300.bicep")
        self.assertLessEqual({nome for nome, padrao in declarados.items() if padrao is None}, atribuidos,
                             "o arquivo informa todos os parâmetros obrigatórios")
        self.assertIn("param fase = readEnvironmentVariable('VARELEIRA_L300_FASE', 'rede')", arquivo)
        self.assertEqual(declarados["fase"], "'rede'")
        for nome, variavel in (("ingressoExterno", "VARELEIRA_L300_INGRESSO_EXTERNO"),
                               ("conectividadePrivadaValidada", "VARELEIRA_L300_CONECTIVIDADE_PRIVADA_VALIDADA")):
            self.assertIn(f"param {nome} = bool(readEnvironmentVariable('{variavel}', 'false'))", arquivo)
            self.assertEqual(declarados[nome], "false")
        for esquecida in ("VARELEIRA_INGRESSO_EXTERNO", "VARELEIRA_IMPLANTAR_APLICACAO", "VARELEIRA_NOME_INDICE"):
            self.assertNotIn(esquecida, arquivo, f"{esquecida} é do L200: uma variável esquecida não pode mudar o L300")
        for nome in ("tagImagem", "idAplicacaoLogin", "tenantLogin", "segredoLogin"):
            self.assertRegex(arquivo, rf"param {nome} = readEnvironmentVariable\('VARELEIRA_\w+', ''\)")
        self.assertNotRegex(arquivo, r"param (?:nome\w+|principalIdCarga|segredoLogin|idAplicacaoLogin|tenantLogin) = '(?!base-|vareleira-)")
        for caminho in (PRINCIPAL, PARAMETROS):
            self.assertEqual(GUID.findall(caminho.read_text(encoding="utf-8")), [], caminho.name)
        for nome in ("skuArmazenamento", "skuBusca"):
            self.assertEqual(declarados[nome], "''", f"{nome}: sem palpite")
        for nome in ("replicasBusca", "particoesBusca"):
            self.assertEqual(declarados[nome], "0", f"{nome}: sem palpite")
        self.assertRegex(arquivo, r"param replicasBusca = int\(readEnvironmentVariable\('VARELEIRA_REPLICAS_BUSCA', '0'\)\)")

    def test_papeis_ficam_no_escopo_do_conteiner_e_so_no_modulo_da_fonte_documental(self):
        fonte = MODULOS["fonte-documental"]
        for arquivo in (*ARQUIVOS_L300, PARAMETROS):
            guids = {g.lower() for g in GUID.findall(arquivo.read_text(encoding="utf-8"))}
            self.assertEqual(guids, {STORAGE_BLOB_DATA_READER, STORAGE_BLOB_DATA_CONTRIBUTOR} if arquivo == fonte else set(),
                             f"{arquivo.name}: só IDs públicos de papéis, só na fonte documental")
            if arquivo != fonte:
                self.assertNotIn("roleAssignments", ler(arquivo), f"{arquivo.name} não atribui papéis")
        texto = ler(fonte)
        todos = recursos(texto)
        atribuicoes = {r.simbolo: r.corpo for r in todos.values() if r.tipo.startswith("Microsoft.Authorization/roleAssignments")}
        self.assertEqual(set(atribuicoes), {"atribuicaoBuscaLerBlobs", "atribuicaoCarga"})
        papeis = dict(re.findall(r"^var\s+(papel\w+)\s*=\s*'([0-9a-f-]{36})'", texto, re.M))
        self.assertEqual(set(papeis), {"papelStorageBlobDataReader", "papelStorageBlobDataContributor"}, "nenhum papel amplo")
        esperado = {"atribuicaoBuscaLerBlobs": (STORAGE_BLOB_DATA_READER, "principalIdBusca", "'ServicePrincipal'"),
                    "atribuicaoCarga": (STORAGE_BLOB_DATA_CONTRIBUTOR, "principalIdCarga", "tipoPrincipalCarga")}
        self.assertEqual(todos["containerDocumentos"].tipo, TIPO_CONTAINER)
        for simbolo, (papel, principal, tipo) in esperado.items():
            corpo = atribuicoes[simbolo]
            self.assertEqual(re.search(r"\bscope:\s*(\w+)", corpo).group(1), "containerDocumentos", "menor escopo: o contêiner")
            self.assertEqual(papeis[re.search(r"subscriptionResourceId\(\s*'[^']+',\s*(\w+)\s*\)", corpo).group(1)], papel)
            self.assertEqual(re.search(r"\bprincipalId:\s*(\w+)", corpo).group(1), principal)
            self.assertEqual(re.search(r"\bprincipalType:\s*(\S+)", corpo).group(1), tipo)
            self.assertRegex(corpo, rf"name:\s*guid\(containerDocumentos\.id, {principal}, papel\w+\)")
        for nome in ("principalIdBusca", "principalIdCarga"):
            self.assertRegex(texto, rf"@minLength\(36\)\s*@maxLength\(36\)\s*param {nome} string")
        principal = ler(PRINCIPAL)
        self.assertRegex(principal, r"principalIdBusca: busca\.\?identity\.principalId \?\? ''")
        self.assertFalse([nome for nome in parametros(principal) if "principalIdBusca" in nome or "principalIdAplicacao" in nome])
        # A identidade da aplicação é a do L200, com os papéis que ela já tem: o L300 não os reatribui.
        self.assertFalse({ACR_PULL, SEARCH_INDEX_DATA_READER, OPENAI_USER} & {g.lower() for g in GUID.findall(texto)})
        self.assertNotIn("l200-identidades", principal)

    def test_conexoes_compartilhadas_endpoints_e_zonas_cobrem_armazenamento_busca_e_modelos(self):
        ingestao = ler(MODULOS["ingestao-privada"])
        todos = recursos(ingestao)
        self.assertEqual({r.simbolo for r in todos.values() if not r.existente}, {"linkBlob", "linkModelos"})
        self.assertTrue(todos["busca"].existente, "a busca só é referenciada")
        self.assertEqual(todos["busca"].versao, recursos(ler(L200_PRINCIPAL))["buscaGerenciada"].versao)
        self.assertIn("groupId: 'blob'", todos["linkBlob"].corpo)
        self.assertIn("groupId: grupoLinkModelos", todos["linkModelos"].corpo)
        self.assertRegex(ingestao, r"@allowed\(\[\s*'openai_account'\s*'foundry_account'\s*\]\)\s*param grupoLinkModelos string")
        self.assertEqual(parametros(ler(PRINCIPAL))["grupoLinkModelos"], "'openai_account'")
        for simbolo in ("linkBlob", "linkModelos"):
            self.assertIn("parent: busca", todos[simbolo].corpo)
        self.assertRegex(todos["linkModelos"].corpo, r"dependsOn:\s*\[\s*linkBlob\s*\]", "o serviço recusa alterações simultâneas")
        self.assertNotRegex(ingestao, r"status:|Approved", "criar a conexão não a aprova")
        endpoints = ler(MODULOS["endpoints"])
        self.assertEqual(re.findall(r"groupIds: \[\s*'(\w+)'\s*\]", endpoints), ["blob", "searchService", "account"])
        self.assertEqual(re.findall(r"privateDnsZoneId: (\w+)", endpoints),
                         ["idZonaBlob", "idZonaBusca", "idZonaCognitiveServices", "idZonaOpenAI", "idZonaServicosIA"])
        self.assertNotIn("manualPrivateLinkServiceConnections:", endpoints.split("output ")[0])
        rede = ler(MODULOS["rede"])
        self.assertEqual(re.findall(r"^var nomeZona\w+ = '(privatelink\.[^']+)'", rede, re.M),
                         ["privatelink.blob.${environment().suffixes.storage}", "privatelink.search.windows.net",
                          "privatelink.cognitiveservices.azure.com", "privatelink.openai.azure.com", "privatelink.services.ai.azure.com"])
        self.assertEqual((rede.count("registrationEnabled: false"), rede.count("virtualNetworkLinks@")), (5, 5))

    def test_ambiente_novo_com_rede_virtual_e_segredos_so_como_parametro_seguro(self):
        ambiente = ler(MODULOS["ambiente"])
        todos = recursos(ambiente)
        for trecho in ("infrastructureSubnetId: idSubredeAmbiente", "internal: false", "workloadProfileType: 'Consumption'",
                       "publicNetworkAccess: 'Enabled'"):
            self.assertIn(trecho, todos["ambiente"].corpo)
        self.assertNotIn("Dedicated", todos["ambiente"].corpo)
        self.assertTrue(todos["logs"].existente, "o workspace é o do L200, só referenciado")
        self.assertEqual(todos["logs"].versao, recursos(ler(L200_PRINCIPAL))["logs"].versao)
        for arquivo in (*ARQUIVOS_L300, PARAMETROS):
            texto = ler(arquivo)
            self.assertEqual(re.findall(r"(\w+)!?\.listKeys\(\)", texto), ["logs"] if arquivo == MODULOS["ambiente"] else [], arquivo.name)
            for proibido in ("username:", "passwordSecretRef", "listCredentials", "keyVaultUrl", "adminUserEnabled"):
                self.assertNotIn(proibido, texto)
        principal = ler(PRINCIPAL)
        self.assertRegex(principal, r"@secure\(\)\s*param segredoLogin string = ''")
        usos = [linha.strip() for linha in re.findall(r"^.*\bsegredoLogin\b.*$", principal, re.M) if not linha.startswith(("param", "@"))]
        self.assertEqual(usos, ["segredoLogin: segredoLogin"], "o segredo só vai ao módulo da aplicação")

    def test_sub_redes_dedicadas_tem_o_tamanho_minimo_e_nao_se_sobrepoem(self):
        principal, rede = ler(PRINCIPAL), ler(MODULOS["rede"])
        padroes = parametros(principal)
        espaco, ambiente, endpoints = (ipaddress.ip_network(padroes[nome].strip("'")) for nome in (
            "espacoEnderecosRede", "prefixoSubredeAmbiente", "prefixoSubredeEndpoints"))
        self.assertLessEqual(ambiente.prefixlen, 27, "o ambiente com perfis de carga precisa de /27 ou maior")
        self.assertLessEqual(endpoints.prefixlen, 28)
        self.assertTrue(ambiente.subnet_of(espaco) and endpoints.subnet_of(espaco))
        self.assertFalse(ambiente.overlaps(endpoints))
        reservados = ("169.254.0.0/16", "172.30.0.0/16", "172.31.0.0/16", "192.0.2.0/24",  # reservados pelo AKS
                      "100.100.0.0/17", "100.100.128.0/19", "100.100.160.0/19", "100.100.192.0/19")  # e pelo ambiente
        for reservado in map(ipaddress.ip_network, reservados):
            self.assertFalse(espaco.overlaps(reservado), f"o espaço padrão invade o intervalo reservado {reservado}")
        sub_redes = {r.simbolo: r.corpo for r in recursos(rede).values() if r.tipo.endswith("/subnets")}
        self.assertEqual(set(sub_redes), {"subredeAmbiente", "subredeEndpoints"})
        self.assertIn("serviceName: 'Microsoft.App/environments'", sub_redes["subredeAmbiente"])
        self.assertNotIn("delegations", sub_redes["subredeEndpoints"], "a sub-rede dos endpoints é dedicada e não é delegada")
        self.assertNotIn("subnets:", recursos(rede)["rede"].corpo, "sub-redes filhas: reaplicar a fase não remove as de outros")
        self.assertRegex(sub_redes["subredeEndpoints"], r"dependsOn:\s*\[\s*subredeAmbiente\s*\]")
        self.assertRegex(rede, r"@minValue\(16\)\s*@maxValue\(27\)\s*param bitsPrefixoSubredeAmbiente int")
        self.assertRegex(rede, r"@minValue\(16\)\s*@maxValue\(28\)\s*param bitsPrefixoSubredeEndpoints int")
        chamada = chamada_do_modulo(principal, "rede")
        for nome in ("Ambiente", "Endpoints"):
            self.assertIn(f"bitsPrefixoSubrede{nome}: int(split(prefixoSubrede{nome}, '/')[1])", chamada)

    def test_aplicacao_reutiliza_o_modulo_do_l200_com_ingresso_fechado_e_o_padrao_do_l200_preservado(self):
        principal, aplicacao = ler(PRINCIPAL), ler(L200_APLICACAO)
        chamada = chamada_do_modulo(principal, "aplicacao")
        self.assertRegex(principal, r"module aplicacao 'modules/l200-aplicacao\.bicep' = if \(fase == 'aplicacao'\)")
        for trecho in ("ingressoExterno: ingressoExterno", "exigirAcessoDocumental: true", "nomeIndice: nomeIndice"):
            self.assertIn(trecho, chamada)
        padroes = parametros(principal)
        self.assertEqual((padroes["ingressoExterno"], padroes["acaoSemLogin"]), ("false", "'Return401'"))
        self.assertNotIn("AllowAnonymous", principal)
        self.assertEqual({nome: padroes[nome] for nome in ("nomeDeploymentEmbeddings", "nomeDeploymentGeracao", "dimensoes", "modoBusca",
                                                           "quantidadeTrechos", "esforco")},
                         {"nomeDeploymentEmbeddings": "'embeddings'", "nomeDeploymentGeracao": "'geracao'", "dimensoes": "1536",
                          "modoBusca": "'hibrida'", "quantidadeTrechos": "3", "esforco": "'low'"},
                         "os deployments e a política de busca são os do L200")
        self.assertRegex(aplicacao, r"param exigirAcessoDocumental bool = false\n")
        self.assertNotIn("exigirAcessoDocumental", ler(L200_PRINCIPAL), "o L200 não passa o parâmetro: o padrão vale")
        self.assertEqual([nome for nome, _ in re.findall(r"\{ name: '(\w+)', value: (.+) \}", aplicacao)], [
            "VARELEIRA_BUSCA", "VARELEIRA_MODELOS", "VARELEIRA_INDICE", "VARELEIRA_DEPLOYMENT_EMBEDDINGS", "VARELEIRA_DEPLOYMENT_GERACAO",
            "VARELEIRA_DIMENSOES", "VARELEIRA_MODO_BUSCA", "VARELEIRA_K", "VARELEIRA_ESFORCO", "AZURE_CLIENT_ID",
            "VARELEIRA_EXIGIR_AUTENTICACAO", "VARELEIRA_TENANT_AUTORIZADO"], "as 12 variáveis do L200 não mudam")

    def test_variavel_de_acesso_documental_segue_o_contrato_do_chat(self):
        aplicacao = ler(L200_APLICACAO)
        self.assertEqual(re.findall(r"name: '(\w+)'\s*value: '(\w+)'", aplicacao), [("VARELEIRA_EXIGIR_ACESSO_DOCUMENTAL", "true")])
        lidas = set(re.findall(r'^VAR_\w+ = "(\w+)"', CHAT.read_text(encoding="utf-8"), re.M)) if CHAT.is_file() else set()
        if "VARELEIRA_EXIGIR_ACESSO_DOCUMENTAL" not in lidas:
            self.skipTest("scripts/lab_chat.py ainda não define VARELEIRA_EXIGIR_ACESSO_DOCUMENTAL: só o contrato literal foi conferido")
        definidas = {nome for nome, _ in re.findall(r"\{ name: '(\w+)', value: (.+) \}", aplicacao)}
        self.assertEqual(definidas - lidas, set(), "o Bicep define variáveis que o chat não lê")


# ---------------------------------------------------------------------------------------------------------------------
# Compilação (exige o Bicep CLI)
# ---------------------------------------------------------------------------------------------------------------------


@unittest.skipUnless(localizar_bicep(), "Bicep CLI não encontrado: a compilação não foi conferida")
class CompilacaoTests(unittest.TestCase):
    def test_arquivos_compilam_e_o_lint_nao_tem_avisos(self):
        for caminho in (*ARQUIVOS_L300, L200_APLICACAO):
            compilar(caminho)
            lint = executar_bicep("lint", str(caminho))
            self.assertEqual((lint.stdout + lint.stderr).strip(), "", f"lint de {caminho.name}")

    def test_parametros_da_fase_rede_compilam_so_com_nomes_de_teste_e_sem_segredos(self):
        saida = executar_bicep("build-params", str(PARAMETROS), "--stdout", **NOMES_DE_TESTE)
        self.assertEqual(saida.returncode, 0, saida.stderr)
        texto = json.loads(saida.stdout)["parametersJson"]
        valores = json.loads(texto)["parameters"]
        self.assertEqual((valores["fase"]["value"], valores["ingressoExterno"]["value"],
                          valores["conectividadePrivadaValidada"]["value"]), ("rede", False, False))
        self.assertEqual((valores["nomeContainer"]["value"], valores["nomeIndice"]["value"]),
                         ("base-documental-l300", "vareleira-lar-l300"))
        for nome in ("segredoLogin", "tagImagem", "idAplicacaoLogin", "tenantLogin", "skuArmazenamento", "skuBusca"):
            self.assertEqual(valores[nome]["value"], "", f"{nome} não é necessário na fase rede")
        self.assertEqual({g.lower() for g in GUID.findall(texto)}, {GUID_ZERO}, "nenhum ID além do informado")

    def test_destinos_vazios_sao_recusados_ao_compilar_os_parametros_e_nenhum_tem_valor_padrao(self):
        saida = executar_bicep("build-params", str(PARAMETROS), "--stdout")
        self.assertNotEqual(saida.returncode, 0)
        arquivo = PARAMETROS.read_text(encoding="utf-8").splitlines()
        recusados = {re.match(r"param (\w+)", arquivo[int(linha) - 1]).group(1)
                     for linha in re.findall(r"\.bicepparam\((\d+),\d+\) : Error BCP333", saida.stderr)}
        self.assertEqual(recusados, set(PARAMETROS_DE_DESTINO), saida.stderr)

    def test_fase_e_portoes_invalidos_sao_recusados_e_as_tres_fases_sao_aceitas(self):
        for ambiente in ({"VARELEIRA_L300_FASE": "tudo"}, {"VARELEIRA_L300_FASE": ""}, {"VARELEIRA_L300_INGRESSO_EXTERNO": "talvez"},
                         {"VARELEIRA_L300_CONECTIVIDADE_PRIVADA_VALIDADA": ""}):
            recusa = executar_bicep("build-params", str(PARAMETROS), "--stdout", **NOMES_DE_TESTE, **ambiente)
            self.assertNotEqual(recusa.returncode, 0, ambiente)
        for fase in ("aplicacao", "isolar"):
            aceita = executar_bicep("build-params", str(PARAMETROS), "--stdout", **NOMES_DE_TESTE, VARELEIRA_L300_FASE=fase)
            self.assertEqual(aceita.returncode, 0, aceita.stderr)
            self.assertEqual(json.loads(json.loads(aceita.stdout)["parametersJson"])["parameters"]["fase"]["value"], fase)

    def test_saidas_e_parametros_dos_modelos_compilados_nao_expoem_segredos(self):
        for caminho in ARQUIVOS_L300:
            modelo = compilar(caminho)
            for nome, saida in modelo.get("outputs", {}).items():
                self.assertNotRegex(nome, PADRAO_SEGREDO, f"{caminho.name}: saída {nome}")
                self.assertNotRegex(json.dumps(saida), r"listKeys|primarySharedKey|segredoLogin|listCredentials", f"{caminho.name}: {nome}")
            for nome, definicao in modelo.get("parameters", {}).items():
                if re.search(r"(?i)segredo|secret|password|senha", nome):
                    self.assertEqual(definicao["type"], "securestring", f"{caminho.name}: {nome}")

    def test_descritor_de_verificacao_explica_dns_aprovacoes_e_condicoes_antes_de_isolar(self):
        saidas = compilar(PRINCIPAL)["outputs"]
        descritor = saidas["descritorVerificacao"]["value"]
        self.assertIn("não prova o caminho privado", descritor["aviso"])
        condicoes = " ".join(descritor["condicoesAntesDeIsolar"])
        for esperado in ("Zonas DNS privadas", "Approved", "executionEnvironment = private", "não desabilite o acesso público"):
            self.assertIn(esperado, condicoes)
        requisitos = " ".join(descritor["requisitosDaBusca"])
        for esperado in ("Basic ou superior", "3 de abril de 2024", "S1 ou superior", "Não aumente a camada"):
            self.assertIn(esperado, requisitos)
        aprovacoes = " ".join(descritor["aprovacoesNecessarias"])
        self.assertIn("pendente", aprovacoes)
        self.assertIn("Approved", aprovacoes)
        for esperado in ("Vareleira.Atendimento", "ME_", "fora do Bicep"):
            self.assertIn(esperado, " ".join(descritor["limites"]))
        for nome in ("urlRetornoLogin", "endpointsPrivados", "linksCompartilhados", "grupoRecursosGerenciado", "acessoPublicoDados"):
            self.assertIn(nome, saidas)

    def test_guardas_do_isolamento_compiladas_no_modelo_arm(self):
        modelo = compilar(PRINCIPAL)
        interno = next(r for r in modelo["resources"] if r["name"] == "l300-isolamento")["properties"]["template"]
        guarda = next(r for r in interno["resources"] if r["type"] == "Microsoft.Resources/deployments")
        self.assertEqual(guarda["properties"]["template"]["resources"], [], "o módulo de guardas não cria nada")
        permitidos = {nome: definicao["allowedValues"] for nome, definicao in guarda["properties"]["template"]["parameters"].items()}
        self.assertEqual(permitidos, {"conectividadePrivadaValidada": [True], "estadoLinkArmazenamento": ["Approved"],
                                      "estadoLinkModelos": ["Approved"], "configuracaoBuscaConfere": [True],
                                      "configuracaoArmazenamentoConfere": [True]})
        servicos = [r for r in interno["resources"] if r["type"] != "Microsoft.Resources/deployments"]
        self.assertEqual({r["type"] for r in servicos}, TIPOS_DE_DADOS)
        for recurso in servicos:
            self.assertEqual(recurso["properties"]["publicNetworkAccess"], "Disabled")
            self.assertIn("l300-guarda-isolamento", " ".join(recurso["dependsOn"]), "nenhum serviço muda antes das guardas")
        gate = modelo["parameters"]["conectividadePrivadaValidada"]
        self.assertEqual((gate["defaultValue"], "allowedValues" in gate), (False, False), "fase rede e aplicacao aceitam o portão falso")
        for recurso in modelo["resources"]:
            self.assertRegex(recurso["condition"], r"^\[equals\(parameters\('fase'\), '(rede|aplicacao|isolar)'\)\]$", recurso["name"])
        # Leituras do estado dos recursos existentes só acontecem na fase que as usa (o `if` do ARM avalia só o ramo escolhido).
        entradas = {r["name"]: r["properties"]["parameters"] for r in modelo["resources"]}
        for parametro in ("estadoLinkArmazenamento", "estadoLinkModelos", "configuracaoBuscaConfere", "configuracaoArmazenamentoConfere"):
            self.assertTrue(entradas["l300-isolamento"][parametro].startswith("[if(equals(parameters('fase'), 'isolar'),"), parametro)
        for parametro in ("servidorRegistro", "clientIdIdentidade"):
            self.assertTrue(entradas["l300-aplicacao"][parametro].startswith("[if(equals(parameters('fase'), 'aplicacao'),"), parametro)

    def test_ordem_das_operacoes_da_fase_rede_evita_alteracoes_simultaneas_nos_mesmos_recursos(self):
        def dependencias(modelo: dict) -> dict[str, set[str]]:
            return {r["name"]: {re.search(r"'([^']+)'\)\]$", d).group(1) for d in r.get("dependsOn", [])} for r in modelo["resources"]}

        principal = dependencias(compilar(PRINCIPAL))
        self.assertLessEqual({"l300-rede"}, principal["l300-endpoints"])
        self.assertLessEqual({"l300-endpoints"}, principal["l300-ambiente"], "o ambiente não altera a rede junto com os endpoints")
        self.assertLessEqual({"l300-endpoints"}, principal["l300-fonte-documental"])
        self.assertLessEqual({"l300-endpoints", "l300-fonte-documental"}, principal["l300-ingestao-privada"])
        endpoints = compilar(MODULOS["endpoints"])
        pes = [r for r in endpoints["resources"] if r["type"] == "Microsoft.Network/privateEndpoints"]
        parametro_do_nome = lambda recurso: re.search(r"parameters\('(\w+)'\)", recurso["name"]).group(1)  # noqa: E731
        self.assertEqual([parametro_do_nome(r) for r in pes], ["nomeEndpointBlob", "nomeEndpointBusca", "nomeEndpointModelos"])
        for anterior, atual in zip(pes, pes[1:]):
            self.assertIn(parametro_do_nome(anterior), " ".join(atual["dependsOn"]), "endpoints na mesma sub-rede, um por vez")
        links = compilar(MODULOS["ingestao-privada"])["resources"]
        modelos = next(r for r in links if r["type"].endswith("sharedPrivateLinkResources") and "nomeLinkModelos" in r["name"])
        self.assertIn("nomeLinkBlob", " ".join(modelos["dependsOn"]), "o serviço de busca recusa alterações simultâneas")
        rede = compilar(MODULOS["rede"])["resources"]
        vinculos = [r for r in rede if r["type"].endswith("virtualNetworkLinks")]
        self.assertEqual(len(vinculos), 5)
        for vinculo in vinculos:
            self.assertIn("nomeSubredeEndpoints", " ".join(vinculo["dependsOn"]), "a rede recebe uma alteração por vez")

    def test_nomes_para_resolver_do_descritor_batem_com_as_zonas_criadas_pelo_modulo_de_rede(self):
        principal, rede = compilar(PRINCIPAL), compilar(MODULOS["rede"])
        parametros_de_teste = {"nomeConta": "stlabteste", "nomeBusca": "srch-lab-teste", "nomeModelos": "ais-lab-teste", "fase": "rede"}
        nomes = _Contexto(parametros_de_teste, principal["variables"], {}).avaliar(
            principal["outputs"]["descritorVerificacao"]["value"]["nomesParaResolver"])
        zonas = _Contexto({}, rede["variables"], {}).avaliar(rede["outputs"]["nomesZonas"]["value"])
        self.assertEqual(sorted(item["zona"] for item in nomes), sorted(zonas))
        for item in nomes:
            self.assertTrue(item["nome"].endswith("." + item["zona"].removeprefix("privatelink.")), item)
            self.assertTrue(item["nome"].startswith(("stlabteste.", "srch-lab-teste.", "ais-lab-teste.")), item)

    def test_modulo_da_aplicacao_do_l200_preserva_as_variaveis_do_l200_por_padrao(self):
        modelo = compilar(L200_APLICACAO)
        self.assertEqual(modelo["parameters"]["exigirAcessoDocumental"]["defaultValue"], False)
        base = {"nomeBusca": "b", "nomeModelos": "m", "nomeIndice": "vareleira-lar-l200", "nomeDeploymentEmbeddings": "embeddings",
                "nomeDeploymentGeracao": "geracao", "dimensoes": 1536, "modoBusca": "hibrida", "quantidadeTrechos": 3, "esforco": "low",
                "clientIdIdentidade": GUID_ZERO, "tenantLogin": GUID_ZERO}

        def variaveis(**extras):
            contexto = _Contexto({**base, "exigirAcessoDocumental": False, **extras}, modelo["variables"], {})
            return [item["name"] for item in contexto.avaliar("[variables('variaveisDeAmbiente')]")]

        padrao = variaveis()
        self.assertEqual(len(padrao), 12, "o padrão é exatamente o do L200")
        self.assertNotIn("VARELEIRA_EXIGIR_ACESSO_DOCUMENTAL", padrao)
        self.assertEqual(variaveis(exigirAcessoDocumental=True), padrao + ["VARELEIRA_EXIGIR_ACESSO_DOCUMENTAL"])


# ---------------------------------------------------------------------------------------------------------------------
# Simulação das fases e das guardas (exige o Bicep CLI)
# ---------------------------------------------------------------------------------------------------------------------


@unittest.skipUnless(localizar_bicep(), "Bicep CLI não encontrado: a simulação das fases não foi conferida")
class FasesSimuladasTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.modelo = compilar(PRINCIPAL)

    def simular(self, fase: str, *, fatos: dict | None = None, **valores) -> Simulacao:
        return simular(self.modelo, valores_de_teste(fase=fase, **valores), fatos_de_teste() if fatos is None else fatos)

    def isolar(self, *, fatos: dict | None = None, **valores) -> Simulacao:
        return self.simular("isolar", fatos=fatos, **{"conectividadePrivadaValidada": True, **configuracao_atual(), **valores})

    def test_cada_fase_implanta_so_os_modulos_dela_sem_violacoes_nem_valores_nao_avaliados(self):
        extras = {"rede": {}, "aplicacao": entradas_de_aplicacao(), "isolar": {"conectividadePrivadaValidada": True, **configuracao_atual()}}
        for fase, esperado in MODULOS_DA_FASE.items():
            simulacao = self.simular(fase, **extras[fase])
            self.assertEqual(simulacao.modulos(), esperado, fase)
            self.assertEqual(simulacao.violacoes, [], fase)
            self.assertEqual(simulacao.nao_avaliados, [], f"{fase}: toda restrição precisa ter sido calculada")

    def test_fase_rede_cria_a_topologia_sem_fechar_acesso_publico_mesmo_com_o_portao_falso(self):
        simulacao = self.simular("rede", conectividadePrivadaValidada=False)
        tipos = {recurso["type"] for recurso in simulacao.recursos}
        self.assertEqual(tipos, TIPOS_DA_FASE_REDE)
        self.assertFalse(tipos & TIPOS_DE_DADOS, "a fase rede não redeclara armazenamento, busca nem modelos")
        self.assertNotIn("l300-isolamento", simulacao.modulos())
        for recurso in simulacao.recursos:
            self.assertNotEqual(recurso.get("properties", {}).get("publicNetworkAccess"), "Disabled", recurso["type"])
        ambiente = next(r for r in simulacao.recursos if r["type"] == "Microsoft.App/managedEnvironments")
        self.assertEqual(ambiente["properties"]["publicNetworkAccess"], "Enabled")
        self.assertEqual(simulacao.parametros_dos_modulos["l300/l300-fonte-documental"]["nomeContainer"], "base-documental-l300")
        self.assertEqual(simulacao.parametros_dos_modulos["l300/l300-ingestao-privada"]["grupoLinkModelos"], "openai_account")

    def test_fase_rede_exige_a_identidade_da_busca_o_id_de_carga_e_sub_rede_do_tamanho_minimo(self):
        sem_identidade = fatos_de_teste()
        sem_identidade[BUSCA] = {"sku": {"name": "basic"}, "properties": {}}
        self.assertTrue(self.simular("rede", fatos=sem_identidade).violacoes_de("principalIdBusca"),
                        "sem a identidade do L200, o contêiner não é criado")
        curto = self.simular("rede", principalIdCarga="curto")
        self.assertTrue(curto.violacoes_de("principalIdCarga") and "curto" not in " ".join(curto.violacoes_de("principalIdCarga")))
        self.assertEqual(self.simular("rede", prefixoSubredeAmbiente="10.30.0.0/27").violacoes, [])
        self.assertTrue(self.simular("rede", prefixoSubredeAmbiente="10.30.0.0/28").violacoes_de("bitsPrefixoSubredeAmbiente"))
        self.assertTrue(self.simular("rede", prefixoSubredeEndpoints="10.30.0.64/29").violacoes_de("bitsPrefixoSubredeEndpoints"))
        self.assertTrue(simular(self.modelo, valores_de_teste(fase="tudo"), fatos_de_teste()).violacoes_de("fase"))

    def test_fase_aplicacao_exige_imagem_login_e_segredo_e_nasce_fechada_com_acesso_documental(self):
        vazia = self.simular("aplicacao")
        for nome in ("tagImagem", "idAplicacaoLogin", "tenantLogin", "segredoLogin"):
            self.assertTrue(vazia.violacoes_de(nome), f"{nome} vazio deveria ser recusado: {vazia.violacoes}")
        curto = self.simular("aplicacao", **entradas_de_aplicacao(segredoLogin="xyz"))
        self.assertTrue(curto.violacoes_de("segredoLogin") and "xyz" not in " ".join(curto.violacoes), "o segredo não é ecoado")
        completa = self.simular("aplicacao", **entradas_de_aplicacao())
        self.assertEqual(completa.violacoes, [])
        modulo = completa.parametros_dos_modulos["l300/l300-aplicacao"]
        self.assertIs(modulo["ingressoExterno"], False, "ingresso fechado por padrão")
        self.assertIs(modulo["exigirAcessoDocumental"], True)
        self.assertEqual((modulo["nomeIndice"], modulo["acaoSemLogin"], modulo["servidorRegistro"]),
                         ("vareleira-lar-l300", "Return401", "crlabteste1.azurecr.io"))
        aberta = self.simular("aplicacao", ingressoExterno=True, **entradas_de_aplicacao())
        self.assertIs(aberta.parametros_dos_modulos["l300/l300-aplicacao"]["ingressoExterno"], True, "o portão é independente da fase")
        self.assertEqual({recurso["type"] for recurso in completa.recursos}, TIPOS_DA_FASE_APLICACAO)
        autenticacao = next(r for r in completa.recursos if r["type"].endswith("/authConfigs"))
        self.assertEqual(autenticacao["properties"]["globalValidation"]["unauthenticatedClientAction"], "[parameters('acaoSemLogin')]")

    def test_fase_isolar_so_executa_com_o_portao_as_conexoes_aprovadas_e_a_configuracao_igual_a_atual(self):
        sem_nada = self.simular("isolar")
        for parametro in (*GUARDAS[:1], "skuArmazenamento", "skuBusca", "replicasBusca", "particoesBusca", *GUARDAS[3:]):
            self.assertTrue(sem_nada.violacoes_de(parametro), f"{parametro}: {sem_nada.violacoes}")
        sem_portao = self.simular("isolar", **configuracao_atual())
        self.assertEqual(len(sem_portao.violacoes), 1, sem_portao.violacoes)
        self.assertTrue(sem_portao.violacoes_de("conectividadePrivadaValidada"), "só o portão impede o isolamento")

        pronto = self.isolar()
        self.assertEqual((pronto.violacoes, pronto.nao_avaliados), ([], []))
        self.assertEqual({r["type"] for r in pronto.recursos}, TIPOS_DE_DADOS)
        for recurso in pronto.recursos:
            self.assertEqual(recurso["properties"]["publicNetworkAccess"], "Disabled")

    def test_fase_isolar_recusa_conexao_pendente_ou_recusada_no_destino(self):
        for link, estado, parametro in ((SPL_BLOB, "Pending", "estadoLinkArmazenamento"), (SPL_MODELOS, "Pending", "estadoLinkModelos"),
                                        (SPL_BLOB, "Rejected", "estadoLinkArmazenamento"), (SPL_MODELOS, "Disconnected", "estadoLinkModelos")):
            fatos = fatos_de_teste()
            fatos[link] = {"properties": {"status": estado}}
            simulacao = self.isolar(fatos=fatos)
            self.assertEqual([texto.split(": ")[1].split()[0] for texto in simulacao.violacoes], [parametro], (link, estado))

    def test_fase_isolar_recusa_configuracao_informada_diferente_da_atual(self):
        for rotulo, ajuste, valores, guarda in (
                ("réplicas escaladas depois do L100", lambda f: f[BUSCA]["properties"].update(replicaCount=2), {}, "configuracaoBuscaConfere"),
                ("partições aumentadas", lambda f: f[BUSCA]["properties"].update(partitionCount=2), {}, "configuracaoBuscaConfere"),
                ("camada informada diferente", lambda f: None, {"skuBusca": "standard"}, "configuracaoBuscaConfere"),
                ("redundância informada diferente", lambda f: None, {"skuArmazenamento": "Standard_ZRS"}, "configuracaoArmazenamentoConfere")):
            fatos = fatos_de_teste()
            ajuste(fatos)
            self.assertEqual([texto.split(": ")[1].split()[0] for texto in self.isolar(fatos=fatos, **valores).violacoes], [guarda], rotulo)

    def test_fase_isolar_sem_o_estado_atual_dos_recursos_nao_da_a_guarda_por_atendida(self):
        for ausente in (BUSCA, ARMAZENAMENTO, SPL_BLOB, SPL_MODELOS):
            fatos = {chave: valor for chave, valor in fatos_de_teste().items() if chave != ausente}
            self.assertTrue(self.isolar(fatos=fatos).nao_avaliados, f"sem {ausente}")

    def test_fases_aplicacao_e_isolar_nao_recriam_rede_endpoints_nem_conexoes(self):
        for simulacao in (self.simular("aplicacao", **entradas_de_aplicacao()), self.isolar()):
            self.assertFalse({recurso["type"] for recurso in simulacao.recursos} & TIPOS_DA_FASE_REDE)

    def test_a_simulacao_depende_das_guardas_compiladas_e_nao_de_uma_conclusao_fixa(self):
        sem_guarda = copy.deepcopy(self.modelo)
        isolamento = next(r for r in sem_guarda["resources"] if r["name"] == "l300-isolamento")
        guarda = next(r for r in isolamento["properties"]["template"]["resources"] if r["type"] == "Microsoft.Resources/deployments")
        del guarda["properties"]["template"]["parameters"]["conectividadePrivadaValidada"]["allowedValues"]
        valores = valores_de_teste(fase="isolar", **configuracao_atual())
        self.assertTrue(simular(self.modelo, valores, fatos_de_teste()).violacoes_de("conectividadePrivadaValidada"))
        self.assertFalse(simular(sem_guarda, valores, fatos_de_teste()).violacoes_de("conectividadePrivadaValidada"),
                         "controle negativo: sem a restrição no modelo, a simulação não pode recusar")

    def test_nomes_padrao_cabem_nos_limites_dos_servicos(self):
        padrao = _Contexto({}, self.modelo["variables"], {})
        for nome, limite in (("nomeRede", 64), ("nomeAmbiente", 32), ("nomeAplicacao", 32)):
            texto = padrao.avaliar(self.modelo["parameters"][nome]["defaultValue"])
            self.assertLessEqual(len(texto), limite, nome)
            self.assertIn("-l300-", texto)


if __name__ == "__main__":
    unittest.main()
