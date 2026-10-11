"""Testes do planejador e verificador de encerramento (scripts/lab_encerramento.py e scripts/planejar_encerramento.py).

Tudo é local: sem Azure, sem rede e sem executar programas (um teste garante isso). Os identificadores são gerados a cada execução com
uuid4, e os valores sentinela servem para provar que nada do inventário vaza para as mensagens de conferência nem para os relatórios.
"""

import ast
import contextlib
import copy
import dataclasses
import functools
import io
import json
import os
import re
import shutil
import socket
import subprocess
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest import mock

import support  # noqa: F401  (configura o caminho dos scripts)
import lab_encerramento as enc
import planejar_encerramento as cli
from lab_comum import CODIGO_DIVERGENCIA, CODIGO_INESPERADO, CODIGO_OK, CODIGO_USO, ErroLab

RAIZ = support.RAIZ


def executar_separado(*argumentos: str) -> tuple[int, str, str]:
    """Roda a linha de comando e devolve (código de saída, stdout, stderr)."""
    saida, erro = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(saida), contextlib.redirect_stderr(erro):
        try:
            codigo = cli.principal(list(argumentos))
        except SystemExit as encerramento:
            codigo = encerramento.code
    return codigo, saida.getvalue(), erro.getvalue()


def executar(*argumentos: str) -> tuple[int, str]:
    codigo, saida, erro = executar_separado(*argumentos)
    return codigo, saida + erro


@contextlib.contextmanager
def sem_rede_e_sem_programas():
    """Qualquer tentativa de abrir conexão ou de executar um programa derruba o teste."""
    import http.client
    import urllib.request

    def proibido(*_argumentos, **_opcoes):
        raise AssertionError("a ferramenta tentou usar a rede ou executar um programa")

    alvos = [(socket.socket, "connect"), (socket, "create_connection"), (socket, "getaddrinfo"), (subprocess, "run"),
             (subprocess, "Popen"), (subprocess, "call"), (subprocess, "check_output"), (os, "system"), (os, "popen"),
             (urllib.request, "urlopen"), (http.client.HTTPConnection, "connect")]
    with contextlib.ExitStack() as pilha:
        for alvo, nome in alvos:
            pilha.enter_context(mock.patch.object(alvo, nome, proibido))
        yield


def novo_guid() -> str:
    return str(uuid.uuid4())


def junto(linhas: list[str]) -> str:
    """As linhas impressas como um texto só: o Windows PowerShell 5.1 quebra avisos longos no meio de uma frase."""
    return " ".join(" ".join(linhas).split())


def desembrulhar(bloco: str) -> str:
    """O corpo de um bloco protegido (o `else` final do comando composto), sem a indentação extra. Falha se a forma for outra."""
    linhas = bloco.splitlines()
    if linhas[0] != "if ($PSVersionTable.PSVersion.Major -lt 7) {" or "} else {" not in linhas or linhas[-1] != "}":
        raise AssertionError(f"o bloco não tem a forma protegida:\n{bloco}")
    corpo = linhas[linhas.index("} else {") + 1:-1]
    return "\n".join(linha[4:] if linha.startswith("    ") else linha for linha in corpo)


@functools.lru_cache(maxsize=1)
def powershell_5() -> str | None:
    """O Windows PowerShell 5.1 (powershell.exe), ou None. Confere a versão: em outros sistemas `powershell` pode ser outra coisa."""
    caminho = shutil.which("powershell")
    if not caminho:
        return None
    try:
        resultado = subprocess.run([caminho, "-NoProfile", "-NonInteractive", "-Command", "$PSVersionTable.PSVersion.ToString()"],
                                   capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError):
        return None
    return caminho if resultado.stdout.strip().startswith("5.1") else None


class Cenario:
    """Um laboratório sintético completo: inventário, linha de base e o estado final esperado depois do encerramento."""

    def __init__(self, maiusculas: bool = False) -> None:
        sufixo = uuid.uuid4().hex[:8]
        self.assinatura, self.tenant = novo_guid(), novo_guid()
        self.grupo = f"rg-lab-{sufixo}"
        self.gerenciado = f"ME_env_{self.grupo}_brazilsouth"
        if maiusculas:
            self.grupo, self.gerenciado = self.grupo.upper(), self.gerenciado.upper()
        self.mi1, self.mi2, self.sp1 = novo_guid(), novo_guid(), novo_guid()
        self.objeto1, self.app1, self.chave1 = novo_guid(), novo_guid(), novo_guid()
        self.objeto2, self.app2 = novo_guid(), novo_guid()
        self.papel1, self.papel2 = novo_guid(), novo_guid()
        self.nome_app1, self.nome_app2 = f"vlr-login-{sufixo}", f"vlr-sonda-{sufixo}"
        self.busca = f"srch-{sufixo}"
        self.atribuicao1 = f"{self.prefixo}/providers/Microsoft.Authorization/roleAssignments/{novo_guid()}"
        self.escopo2 = self.recurso("Microsoft.Storage/storageAccounts", f"st{sufixo}")
        self.atribuicao2 = f"{self.escopo2}/providers/Microsoft.Authorization/roleAssignments/{novo_guid()}"
        self._papeis: list[dict] | None = None

    @property
    def prefixo(self) -> str:
        return f"/subscriptions/{self.assinatura}/resourceGroups/{self.grupo}"

    def recurso(self, provedor_e_tipo: str, nome: str, grupo: str | None = None) -> str:
        base = self.prefixo if grupo is None else f"/subscriptions/{self.assinatura}/resourceGroups/{grupo}"
        namespace, _, tipo = provedor_e_tipo.partition("/")
        return f"{base}/providers/{namespace}/{tipo}/{nome}"

    def inventario(self) -> dict:
        r = self.recurso
        recursos = [("Microsoft.App/containerApps", "chat"), ("Microsoft.App/containerApps", "api"), ("Microsoft.App/jobs", "sonda"),
                    ("Microsoft.App/managedEnvironments", "env"), ("Microsoft.OperationalInsights/workspaces", "logs"),
                    ("Microsoft.Storage/storageAccounts", self.escopo2.rsplit("/", 1)[-1]),
                    ("Microsoft.Search/searchServices", self.busca), ("Microsoft.CognitiveServices/accounts", "ais"),
                    ("Microsoft.KeyVault/vaults", "kvlab")]
        return {
            "versao": 1, "assinatura": self.assinatura, "tenant": self.tenant, "regiao": "brazilsouth", "grupo": self.grupo,
            "grupo_exclusivo": True, "grupo_gerenciado": self.gerenciado,
            "principais_proprios": [self.mi1, self.mi2, self.sp1],
            "recursos_proprios": [{"id": r(tipo, nome), "tipo": tipo} for tipo, nome in recursos],
            "shared_private_links": [
                {"id": r("Microsoft.Search/searchServices", self.busca) + f"/sharedPrivateLinkResources/{nome}"} for nome in ("blob", "modelos")],
            "atribuicoes_proprias": [
                {"id": self.atribuicao1, "escopo": self.prefixo, "principal_id": self.mi1, "papel_id": self.papel1},
                {"id": self.atribuicao2, "escopo": self.escopo2, "principal_id": self.mi2, "papel_id": self.papel2}],
            "identidades_entra": [
                {"objeto_id": self.objeto1, "app_id": self.app1, "nome": self.nome_app1, "principal_id": self.sp1, "chaves": [self.chave1]},
                {"objeto_id": self.objeto2, "app_id": self.app2, "nome": self.nome_app2}],
            "expurgos": [{"tipo": "conta_de_modelos", "nome": "ais", "regiao": "brazilsouth", "grupo": self.grupo},
                         {"tipo": "cofre_de_chaves", "nome": "kvlab", "regiao": "brazilsouth"}],
        }

    def carregado(self) -> enc.Inventario:
        return enc.inventario_de_dados(self.inventario())

    # Formatos do Azure CLI, como os comandos de captura os exportam. A linha de base é gerada uma vez por cenário.
    def grupo_az(self, nome: str) -> dict:
        return {"id": f"/subscriptions/{self.assinatura}/resourceGroups/{nome}", "name": nome}

    def grupos_base(self) -> list[dict]:
        return [self.grupo_az(n) for n in ("rg-um", "rg-dois", "NetworkWatcherRG")]

    def recursos_base(self) -> list[dict]:
        return [{"id": self.recurso("Microsoft.Storage/storageAccounts", "stum", "rg-um"), "type": "Microsoft.Storage/storageAccounts"},
                {"id": self.recurso("Microsoft.KeyVault/vaults", "kvdois", "rg-dois"), "type": "Microsoft.KeyVault/vaults"},
                {"id": self.recurso("Microsoft.Network/networkWatchers", "nw", "NetworkWatcherRG"), "type": "Microsoft.Network/networkWatchers"}]

    def papel_az(self, identificador: str | None = None, principal: str | None = None, escopo: str | None = None) -> dict:
        escopo = escopo or f"/subscriptions/{self.assinatura}"
        return {"id": identificador or f"{escopo}/providers/Microsoft.Authorization/roleAssignments/{novo_guid()}",
                "principalId": principal or novo_guid(), "scope": escopo,
                "roleDefinitionId": f"/subscriptions/{self.assinatura}/providers/Microsoft.Authorization/roleDefinitions/{novo_guid()}"}

    def papeis_base(self) -> list[dict]:
        if self._papeis is None:
            self._papeis = [self.papel_az(), self.papel_az(escopo=f"/subscriptions/{self.assinatura}/resourceGroups/rg-um"), self.papel_az()]
        return copy.deepcopy(self._papeis)

    def presenca(self, estado: str = "ausente") -> dict:
        return {item.chave: estado for item in enc.itens_de_presenca(self.carregado())}


class ComPasta(unittest.TestCase):
    def setUp(self) -> None:
        self.reiniciar()

    def reiniciar(self, **opcoes) -> Cenario:
        """Nova pasta e novo cenário: para os subtestes que gravam arquivos de nomes fixos."""
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        self.pasta = Path(pasta.name)
        self.c = Cenario(**opcoes)
        return self.c

    def escrever(self, nome: str, dados) -> Path:
        caminho = self.pasta / nome
        caminho.write_text(dados if isinstance(dados, str) else json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
        return caminho

    def arquivos(self) -> list[str]:
        return sorted(item.name for item in self.pasta.iterdir())

    def montar(self, inventario=None, base=None, depois=None, presenca="padrao") -> dict[str, Path]:
        """Grava inventário, linha de base e estado final (por padrão, um encerramento perfeito) e devolve os caminhos."""
        c = self.c
        base = base or (c.grupos_base(), c.recursos_base(), c.papeis_base())
        # o estado final padrão é o mesmo conteúdo em outra ordem: um `az` real não repete a ordem nem o texto exatos
        depois = depois or tuple(list(reversed(copy.deepcopy(lista))) for lista in base)
        caminhos = {
            "inventario": self.escrever("inventario.json", inventario if inventario is not None else c.inventario()),
            "grupos-antes": self.escrever("grupos-antes.json", base[0]), "recursos-antes": self.escrever("recursos-antes.json", base[1]),
            "papeis-antes": self.escrever("papeis-antes.json", base[2]),
            "grupos-depois": self.escrever("grupos-depois.json", depois[0]), "recursos-depois": self.escrever("recursos-depois.json", depois[1]),
            "papeis-depois": self.escrever("papeis-depois.json", depois[2]),
        }
        if presenca == "padrao":
            presenca = c.presenca()
        if presenca is not None:
            caminhos["presenca"] = self.escrever("presenca-depois.json", presenca)
        return caminhos

    @staticmethod
    def argumentos(caminhos: dict[str, Path], *extras: str, sem: tuple[str, ...] = ()) -> list[str]:
        resultado = ["--etapa", "conferir"]
        for chave, caminho in caminhos.items():
            if chave not in sem:
                resultado += [f"--{chave}", str(caminho)]
        return resultado + list(extras)

    def conferir(self, caminhos, *extras, sem=()) -> tuple[int, str]:
        return executar(*self.argumentos(caminhos, *extras, sem=sem))


def blocos_de_powershell(c: Cenario, plano: enc.Plano, pasta: str = "./encerramento") -> list[tuple[str, str, str]]:
    """Todo bloco PowerShell que a ferramenta imprime para este cenário: (rótulo, bloco, categoria).

    Categorias: preparacao, comando, verificacao (decide ausência: se recusa com 'indeterminado') e captura.
    """
    inv = c.carregado()
    blocos = [("preparacao", plano.preparacao, "preparacao")]
    for passo in plano.passos:
        blocos += [(f"passo {passo.numero} ({passo.tipo}) comando", passo.comando, "comando"),
                   (f"passo {passo.numero} ({passo.tipo}) verificacao", passo.verificacao, "verificacao")]
    blocos += [(f"fechamento {numero}", item.comando, "verificacao") for numero, item in enumerate(plano.fechamento, 1)
               if item.comando and not item.comando.startswith(".")]
    blocos += [("captura antes", enc.comandos_de_captura(c.assinatura, c.grupo, "antes", pasta), "captura"),
               ("captura depois", enc.comandos_de_captura(c.assinatura, c.grupo, "depois", pasta, inv), "captura")]
    return blocos


# ----------------------------------------------------------------------------------------------------------------------
# Inventário e guardas
# ----------------------------------------------------------------------------------------------------------------------

class InventarioTests(ComPasta):
    def recusa(self, dados, *trechos: str) -> str:
        with self.assertRaises(ErroLab) as contexto:
            enc.inventario_de_dados(dados)
        mensagem = str(contexto.exception)
        for trecho in trechos:
            self.assertIn(trecho, mensagem)
        return mensagem

    def test_inventario_valido_e_normalizado(self):
        inv = self.c.carregado()
        self.assertEqual(inv.prefixo, self.c.prefixo)
        self.assertEqual(len(inv.recursos), 9)
        self.assertEqual(inv.identidades[1].principal_id, None, "o principal de serviço é opcional")
        self.assertEqual(inv.identidades[1].chaves, ())
        self.assertTrue(all(p == p.lower() for p in inv.principais_proprios), "GUIDs normalizados em minúsculas")
        self.assertEqual(inv.links[0].servico, self.c.busca)
        self.assertEqual(inv.links[0].nome, "blob")

    def test_modelo_tem_todos_os_campos_e_e_recusado_ate_ser_preenchido(self):
        modelo = enc.modelo_de_inventario()
        self.assertEqual(set(modelo), set(enc.CAMPOS_DO_INVENTARIO))
        self.assertIs(modelo["grupo_exclusivo"], False, "a atestação nunca vem pronta")
        self.recusa(modelo)

    def test_grupo_precisa_ser_atestado_como_exclusivo(self):
        for valor in (False, "true", 1, None):
            with self.subTest(valor=valor):
                dados = self.c.inventario()
                dados["grupo_exclusivo"] = valor
                self.recusa(dados, "grupo_exclusivo")
        dados = self.c.inventario()
        del dados["grupo_exclusivo"]
        self.recusa(dados, "grupo_exclusivo")

    def test_campos_desconhecidos_ausentes_versao_e_tipos(self):
        dados = self.c.inventario()
        dados["atribuicoes_propias"] = []
        self.recusa(dados, "campo desconhecido: atribuicoes_propias")
        dados = self.c.inventario()
        del dados["atribuicoes_proprias"]
        self.recusa(dados, "atribuicoes_proprias: campo obrigatório ausente")
        for versao in (2, True, "1", None):
            dados = self.c.inventario()
            dados["versao"] = versao
            self.recusa(dados, "versao")
        dados = self.c.inventario()
        dados["recursos_proprios"] = {"id": "x"}
        self.recusa(dados, "deve ser uma lista")
        dados = self.c.inventario()
        dados["recursos_proprios"][0]["extra"] = "x"
        self.recusa(dados, "campo desconhecido: extra")
        self.recusa([], "objeto JSON")

    def test_listas_vazias_sao_aceitas_e_listas_de_menos_de_um_limite(self):
        dados = self.c.inventario()
        for chave in ("recursos_proprios", "shared_private_links", "atribuicoes_proprias", "identidades_entra", "expurgos"):
            dados[chave] = []
        inv = enc.inventario_de_dados(dados)
        self.assertEqual((inv.recursos, inv.links, inv.atribuicoes, inv.identidades, inv.expurgos), ((), (), (), (), ()))
        dados["recursos_proprios"] = [{"id": self.c.recurso("Microsoft.App/jobs", f"j{i}"), "tipo": "Microsoft.App/jobs"}
                                      for i in range(enc.LIMITE_DE_ITENS + 1)]
        self.recusa(dados, "itens demais")

    def test_todo_id_precisa_do_prefixo_exato_do_grupo_exclusivo(self):
        c = self.c
        casos = {
            "outro grupo": c.recurso("Microsoft.Storage/storageAccounts", "st", "rg-outro"),
            "grupo gerenciado": c.recurso("Microsoft.Storage/storageAccounts", "st", c.gerenciado),
            "grupo cujo nome começa com o exclusivo": c.recurso("Microsoft.Storage/storageAccounts", "st", c.grupo + "-outro"),
            "outra assinatura": f"/subscriptions/{novo_guid()}/resourceGroups/{c.grupo}/providers/Microsoft.Storage/storageAccounts/st",
            "sem o grupo": f"/subscriptions/{c.assinatura}/providers/Microsoft.Storage/storageAccounts/st",
            "relativo": f"resourceGroups/{c.grupo}/providers/Microsoft.Storage/storageAccounts/st",
        }
        for rotulo, id_ in casos.items():
            with self.subTest(rotulo):
                dados = c.inventario()
                dados["recursos_proprios"][5]["id"] = id_
                self.recusa(dados, "recursos_proprios[5].id")
                dados = c.inventario()
                dados["shared_private_links"][0]["id"] = id_ + "/sharedPrivateLinkResources/x"
                self.recusa(dados, "shared_private_links[0].id")
        dados = c.inventario()  # o prefixo é comparado sem diferenciar caixa
        dados["recursos_proprios"][5]["id"] = dados["recursos_proprios"][5]["id"].replace("/resourceGroups/", "/RESOURCEGROUPS/").replace(c.grupo, c.grupo.upper())
        enc.inventario_de_dados(dados)

    def test_ids_recusam_escape_aspas_curingas_e_separadores(self):
        proibidos = ["?", "#", "\\", "/../", "/./", "%", " ", "'", '"', ";", "`", "$", "*", "//", "|", "&", "<", ">", "(", ")", "{", "}", "[", "]",
                     "\n", "ã", ",", "/..", "/."]
        for proibido in proibidos:
            with self.subTest(repr(proibido)):
                dados = self.c.inventario()
                dados["recursos_proprios"][0]["id"] = dados["recursos_proprios"][0]["id"] + proibido + "x"
                self.recusa(dados, "recursos_proprios[0].id")
                dados = self.c.inventario()
                dados["shared_private_links"][0]["id"] += proibido
                self.recusa(dados, "shared_private_links[0].id")
                dados = self.c.inventario()
                dados["atribuicoes_proprias"][1]["escopo"] += proibido
                self.recusa(dados, "atribuicoes_proprias[1].escopo")
        # a mensagem diz qual caractere é o problema (sem repetir o ID)
        dados = self.c.inventario()
        dados["recursos_proprios"][0]["id"] += "*x"
        self.recusa(dados, "curinga '*'")

    def test_guid_e_nomes_seguem_padroes_fechados(self):
        def altera(caminho, valor):
            dados = self.c.inventario()
            alvo = dados
            for parte in caminho[:-1]:
                alvo = alvo[parte]
            alvo[caminho[-1]] = valor
            return dados
        casos = [(("assinatura",), "nao-e-guid"), (("tenant",), novo_guid()[:-1]), (("regiao",), "Brazil South"), (("grupo",), "rg lab"),
                 (("grupo",), "rg-lab."), (("grupo",), "a" * 91), (("grupo_gerenciado",), "ME 1"), (("principais_proprios", 0), "x"),
                 (("identidades_entra", 0, "nome"), "com espaço"), (("identidades_entra", 0, "nome"), "a'b"),
                 (("identidades_entra", 0, "objeto_id"), "x"), (("identidades_entra", 0, "chaves", 0), "x"),
                 (("atribuicoes_proprias", 0, "papel_id"), "x"), (("atribuicoes_proprias", 0, "principal_id"), "x"),
                 (("expurgos", 1, "nome"), "ab"), (("expurgos", 1, "nome"), "1cofre"), (("expurgos", 1, "regiao"), "Brazil"),
                 (("recursos_proprios", 0, "tipo"), "Microsoft.App")]
        for caminho, valor in casos:
            with self.subTest(caminho=caminho, valor=valor):
                self.recusa(altera(caminho, valor))

    def test_tipo_precisa_combinar_com_o_id_e_tipos_reservados_tem_lista_propria(self):
        dados = self.c.inventario()
        dados["recursos_proprios"][0]["tipo"] = "Microsoft.App/jobs"
        self.recusa(dados, "o tipo não combina com o ID")
        dados = self.c.inventario()
        dados["recursos_proprios"].append({"id": dados["shared_private_links"][0]["id"], "tipo": "Microsoft.Search/searchServices/sharedPrivateLinkResources"})
        self.recusa(dados, "shared_private_links")
        dados = self.c.inventario()
        dados["recursos_proprios"].append({"id": dados["atribuicoes_proprias"][0]["id"], "tipo": "Microsoft.Authorization/roleAssignments"})
        self.recusa(dados, "atribuicoes_proprias")
        dados = self.c.inventario()
        dados["recursos_proprios"].append(dict(dados["recursos_proprios"][0]))
        self.recusa(dados, "IDs repetidos")

    def test_link_precisa_ser_filho_de_um_servico_de_busca(self):
        dados = self.c.inventario()
        dados["shared_private_links"][0]["id"] = self.c.recurso("Microsoft.Storage/storageAccounts", "st")
        self.recusa(dados, "ID de um link")

    def test_guarda_de_papeis_herdados_escopo_principal_e_id_da_atribuicao(self):
        c = self.c
        # atribuições do grupo e de um recurso dele são aceitas
        enc.inventario_de_dados(c.inventario())
        for rotulo, mutacao in {
            "escopo da assinatura": lambda a: a.update(escopo=f"/subscriptions/{c.assinatura}"),
            "escopo de outro grupo": lambda a: a.update(escopo=f"/subscriptions/{c.assinatura}/resourceGroups/rg-um"),
            "escopo do grupo gerenciado": lambda a: a.update(escopo=f"/subscriptions/{c.assinatura}/resourceGroups/{c.gerenciado}"),
            "ID de outro escopo": lambda a: a.update(id=f"/subscriptions/{c.assinatura}/providers/Microsoft.Authorization/roleAssignments/{novo_guid()}"),
            "ID sem GUID": lambda a: a.update(id=a["escopo"] + "/providers/Microsoft.Authorization/roleAssignments/nao-e-guid"),
            "ID de outro tipo": lambda a: a.update(id=a["escopo"] + f"/providers/Microsoft.Authorization/roleDefinitions/{novo_guid()}"),
            "principal desconhecido": lambda a: a.update(principal_id=novo_guid()),
        }.items():
            with self.subTest(rotulo):
                dados = c.inventario()
                mutacao(dados["atribuicoes_proprias"][0])
                mensagem = self.recusa(dados, "atribuicoes_proprias[0]")
                if rotulo == "principal desconhecido":
                    self.assertIn("preserve papéis herdados", mensagem)
        dados = c.inventario()
        dados["atribuicoes_proprias"][0]["escopo"] = c.prefixo.upper()  # igual ao grupo, sem diferenciar caixa
        dados["atribuicoes_proprias"][0]["id"] = c.prefixo.upper() + dados["atribuicoes_proprias"][0]["id"][len(c.prefixo):]
        enc.inventario_de_dados(dados)

    def test_identidades_e_principais_sao_consistentes(self):
        dados = self.c.inventario()
        dados["identidades_entra"][0]["principal_id"] = novo_guid()
        self.recusa(dados, "principais_proprios")
        dados = self.c.inventario()
        dados["identidades_entra"][1]["objeto_id"] = dados["identidades_entra"][0]["objeto_id"]
        self.recusa(dados, "objeto_id repetido")
        dados = self.c.inventario()
        dados["identidades_entra"][1]["app_id"] = dados["identidades_entra"][0]["app_id"]
        self.recusa(dados, "app_id repetido")
        dados = self.c.inventario()
        dados["identidades_entra"][0]["chaves"] = [self.c.chave1, self.c.chave1]
        self.recusa(dados, "GUIDs repetidos")
        dados = self.c.inventario()
        dados["principais_proprios"].append(dados["principais_proprios"][0])
        self.recusa(dados, "GUIDs repetidos")
        dados = self.c.inventario()
        dados["identidades_entra"][0]["objeto_id"] = dados["identidades_entra"][0]["principal_id"]
        self.recusa(dados, "objeto_id")

    def test_um_guid_so_pode_ter_um_papel_e_a_mensagem_nao_repete_o_valor(self):
        casos = {
            "objeto_id igual ao app_id da mesma identidade": lambda d: d["identidades_entra"][1].update(app_id=d["identidades_entra"][1]["objeto_id"]),
            "app_id igual ao principal_id da mesma identidade": lambda d: d["identidades_entra"][0].update(app_id=d["identidades_entra"][0]["principal_id"]),
            "objeto_id igual ao principal_id da mesma identidade": lambda d: d["identidades_entra"][0].update(objeto_id=d["identidades_entra"][0]["principal_id"]),
            "objeto_id igual ao app_id de outra identidade": lambda d: d["identidades_entra"][1].update(objeto_id=d["identidades_entra"][0]["app_id"]),
            "app_id igual ao objeto_id de outra identidade": lambda d: d["identidades_entra"][1].update(app_id=d["identidades_entra"][0]["objeto_id"]),
            "principais_proprios com o objeto_id de uma identidade": lambda d: d["principais_proprios"].append(d["identidades_entra"][1]["objeto_id"]),
            "principais_proprios com o app_id de uma identidade": lambda d: d["principais_proprios"].append(d["identidades_entra"][1]["app_id"]),
            "credencial igual ao objeto_id": lambda d: d["identidades_entra"][0]["chaves"].append(d["identidades_entra"][0]["objeto_id"]),
            "assinatura igual ao tenant": lambda d: d.update(tenant=d["assinatura"]),
            "papel_id igual a um principal": lambda d: d["atribuicoes_proprias"][0].update(papel_id=d["principais_proprios"][1]),
        }
        for rotulo, mutacao in casos.items():
            with self.subTest(rotulo):
                dados = self.c.inventario()
                mutacao(dados)
                mensagem = self.recusa(dados, "também aparece como", "cada GUID tem um só papel")
                for guid in set(re.findall(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", json.dumps(dados).lower())):
                    self.assertNotIn(guid, mensagem.lower(), "a mensagem cita os campos, nunca o valor")

    def test_repetir_o_mesmo_papel_e_normal_mas_credencial_repetida_entre_identidades_nao(self):
        dados = self.c.inventario()  # o mesmo principal e o mesmo papel em duas atribuições
        dados["atribuicoes_proprias"][1].update(principal_id=dados["atribuicoes_proprias"][0]["principal_id"],
                                                papel_id=dados["atribuicoes_proprias"][0]["papel_id"])
        enc.inventario_de_dados(dados)
        dados = self.c.inventario()
        dados["identidades_entra"][1]["chaves"] = list(dados["identidades_entra"][0]["chaves"])
        self.recusa(dados, "credenciais (chaves) repetidas")

    def test_tenant_so_e_opcional_sem_objetos_do_entra(self):
        dados = self.c.inventario()
        del dados["tenant"]
        self.recusa(dados, "tenant", "diretório errado")
        dados["principais_proprios"], dados["identidades_entra"] = [], []
        dados["atribuicoes_proprias"] = []
        self.assertIsNone(enc.inventario_de_dados(dados).tenant)

    def test_expurgos_so_do_grupo_exclusivo_e_de_tipos_conhecidos(self):
        dados = self.c.inventario()
        dados["expurgos"][0]["grupo"] = "rg-um"
        self.recusa(dados, "expurgos[0].grupo")
        dados = self.c.inventario()
        dados["expurgos"].append({"tipo": "storage", "nome": "x", "regiao": "brazilsouth"})
        self.recusa(dados, "'tipo' deve ser")
        dados = self.c.inventario()
        dados["expurgos"][1]["grupo"] = self.c.grupo
        self.recusa(dados, "campo desconhecido: grupo")

    def test_mensagens_de_recusa_nunca_repetem_valores(self):
        sentinela = f"sentinela-{uuid.uuid4().hex}"
        dados = self.c.inventario()
        dados["recursos_proprios"][0]["id"] = f"/{sentinela}/x"
        dados["assinatura_x"] = sentinela
        dados[sentinela] = sentinela
        dados["identidades_entra"][0]["nome"] = f"{sentinela} com espaço"
        dados["expurgos"][0]["nome"] = f"{sentinela}!"
        mensagem = self.recusa(dados)
        self.assertNotIn(sentinela, mensagem)
        self.assertNotIn("sentinela", mensagem)

    def test_leitura_de_arquivo_recusa_json_invalido_e_aceita_bom_e_utf16(self):
        caminho = self.escrever("inv.json", "{ não é json")
        with self.assertRaises(ErroLab) as contexto:
            enc.carregar_inventario(caminho)
        self.assertIn("não contém JSON válido", str(contexto.exception))
        self.assertNotIn(str(caminho), str(contexto.exception))
        dados = json.dumps(self.c.inventario())
        (self.pasta / "bom.json").write_bytes(b"\xef\xbb\xbf" + dados.encode("utf-8"))
        (self.pasta / "utf16.json").write_bytes(dados.encode("utf-16"))
        for nome in ("bom.json", "utf16.json"):
            self.assertEqual(enc.carregar_inventario(self.pasta / nome).grupo, self.c.grupo, nome)
        (self.pasta / "nan.json").write_text('{"versao": NaN}', encoding="utf-8")
        with self.assertRaises(ErroLab):
            enc.carregar_inventario(self.pasta / "nan.json")
        with self.assertRaises(ErroLab) as contexto:
            enc.carregar_inventario(self.pasta / "nao-existe.json")
        self.assertIn("não encontrado", str(contexto.exception))

    def test_arquivo_acima_do_limite_de_32_mib_e_recusado_sem_ser_lido(self):
        self.assertEqual(enc.LIMITE_DE_ARQUIVO_BYTES, 32 * 1024 * 1024)
        grande = self.pasta / "grande.json"
        with grande.open("wb") as arquivo:
            arquivo.truncate(enc.LIMITE_DE_ARQUIVO_BYTES + 1)
        with mock.patch.object(Path, "read_bytes", side_effect=AssertionError("o arquivo acima do limite foi lido")):
            with self.assertRaises(ErroLab) as contexto:
                enc.carregar_inventario(grande)
        self.assertIn("passa de 32 MiB", str(contexto.exception))
        self.assertNotIn(str(grande), str(contexto.exception))

    def test_o_limite_de_tamanho_aceita_exatamente_o_limite_e_recusa_um_byte_a_mais(self):
        with mock.patch.object(enc, "LIMITE_DE_ARQUIVO_BYTES", 16):
            exato, maior = self.pasta / "exato.json", self.pasta / "maior.json"
            exato.write_bytes(b"[1]" + b" " * 13)
            maior.write_bytes(b"[1]" + b" " * 14)
            self.assertEqual(enc.ler_json(exato, "--teste")[0], [1])
            with self.assertRaises(ErroLab) as contexto:
                enc.ler_json(maior, "--teste")
            self.assertIn("passa de", str(contexto.exception))


# ----------------------------------------------------------------------------------------------------------------------
# Instantâneos e linha de base
# ----------------------------------------------------------------------------------------------------------------------

class InstantaneoTests(ComPasta):
    def carregar(self, grupos=None, recursos=None, papeis=None, assinatura=None):
        c = self.c
        arquivos = [self.escrever(f"{nome}.json", dados) for nome, dados in
                    (("g", c.grupos_base() if grupos is None else grupos), ("r", c.recursos_base() if recursos is None else recursos),
                     ("p", c.papeis_base() if papeis is None else papeis))]
        return enc.carregar_instantaneo(*arquivos, assinatura or c.assinatura, "antes")

    def recusa(self, trecho, **arquivos):
        with self.assertRaises(ErroLab) as contexto:
            self.carregar(**arquivos)
        self.assertIn(trecho, str(contexto.exception))
        return str(contexto.exception)

    def test_instantaneo_valido_e_normalizado_em_minusculas(self):
        base = self.carregar()
        self.assertEqual(base.grupos, {"rg-um", "rg-dois", "networkwatcherrg"})
        self.assertEqual(len(base.recursos), 3)
        self.assertEqual(len(base.atribuicoes), 3)
        self.assertEqual(len(base.sha256), 3)

    def test_json_invalido_ou_com_tipos_errados_e_recusado_com_orientacao(self):
        with self.assertRaises(ErroLab) as contexto:
            enc.carregar_instantaneo(self.escrever("g1.json", "{ quebrado"), self.escrever("r1.json", []), self.escrever("p1.json", []), self.c.assinatura, "antes")
        self.assertIn("não contém JSON válido", str(contexto.exception))
        self.assertIn("--grupos-antes", str(contexto.exception))
        self.recusa("deve ser uma lista JSON", grupos={"value": []})
        self.recusa("deve ser uma lista JSON", recursos='"texto"')
        self.recusa("deve ser uma lista JSON", papeis=7)
        self.recusa("'id' e 'name'", grupos=["rg-um"])
        self.recusa("'id' e 'name'", grupos=[{"id": 1, "name": "x"}])
        self.recusa("'id' e 'type'", recursos=[{"id": "/subscriptions/x"}])
        self.recusa("id, principalId, roleDefinitionId e scope", papeis=[{"id": "x"}])

    def test_lista_paginada_com_nextlink_e_recusada_pedindo_para_completar(self):
        for chave in ("nextLink", "@odata.nextLink"):
            with self.subTest(chave):
                mensagem = self.recusa("completar", recursos={"value": self.c.recursos_base(), chave: "https://exemplo.invalido/pagina2"})
                self.assertIn("completar a listagem antes de continuar", mensagem)
                self.assertNotIn("exemplo.invalido", mensagem)

    def test_itens_de_outra_assinatura_ou_inconsistentes_sao_recusados(self):
        c = self.c
        outra = novo_guid()
        self.recusa("assinatura do inventário", grupos=[{"id": f"/subscriptions/{outra}/resourceGroups/rg-um", "name": "rg-um"}])
        self.recusa("assinatura do inventário", grupos=[{"id": f"/subscriptions/{c.assinatura}/resourceGroups/rg-um", "name": "rg-dois"}])
        self.recusa("assinatura do inventário", recursos=[{"id": f"/subscriptions/{outra}/resourceGroups/rg/providers/X.Y/z/a", "type": "X.Y/z"}])
        self.recusa("assinatura do inventário", papeis=[c.papel_az(escopo=f"/subscriptions/{outra}")])
        mg = c.papel_az()
        mg["scope"] = "/providers/Microsoft.Management/managementGroups/raiz"
        self.recusa("grupo de gerenciamento", papeis=[mg])
        self.recusa("tipos diferentes", recursos=[{"id": c.recursos_base()[0]["id"], "type": "A.B/c"}, {"id": c.recursos_base()[0]["id"], "type": "A.B/d"}])
        papel = c.papel_az()
        self.recusa("valores diferentes", papeis=[papel, dict(papel, principalId=novo_guid())])

    def test_utf16_do_powershell_5_e_aceito(self):
        caminhos = []
        for nome, dados in (("g", self.c.grupos_base()), ("r", self.c.recursos_base()), ("p", self.c.papeis_base())):
            caminho = self.pasta / f"{nome}.json"
            caminho.write_bytes(json.dumps(dados).encode("utf-16"))
            caminhos.append(caminho)
        self.assertEqual(len(enc.carregar_instantaneo(*caminhos, self.c.assinatura, "antes").grupos), 3)


class LinhaDeBaseTests(ComPasta):
    def validar(self, grupos=None, recursos=None, papeis=None, inventario=None):
        c = self.c
        base = enc.carregar_instantaneo(
            self.escrever("g.json", c.grupos_base() if grupos is None else grupos), self.escrever("r.json", c.recursos_base() if recursos is None else recursos),
            self.escrever("p.json", c.papeis_base() if papeis is None else papeis), c.assinatura, "antes")
        enc.validar_linha_de_base(enc.inventario_de_dados(inventario or c.inventario()), base)

    def recusa(self, *trechos, **kwargs):
        with self.assertRaises(ErroLab) as contexto:
            self.validar(**kwargs)
        for trecho in trechos:
            self.assertIn(trecho, str(contexto.exception))
        return str(contexto.exception)

    def test_linha_de_base_sem_conflitos_e_aceita(self):
        self.validar()

    def test_grupo_exclusivo_ou_gerenciado_na_linha_de_base_recusa_o_plano(self):
        self.recusa("já existia", grupos=self.c.grupos_base() + [self.c.grupo_az(self.c.grupo)])
        self.recusa("já existia", grupos=self.c.grupos_base() + [self.c.grupo_az(self.c.grupo.upper())])
        self.recusa("gerenciado já existia", grupos=self.c.grupos_base() + [self.c.grupo_az(self.c.gerenciado)])

    def test_nunca_se_planeja_apagar_o_que_ja_existia(self):
        c = self.c
        inventario = c.inventario()
        for chave, indice, base, fonte in (
                ("recursos_proprios", 0, "recursos", lambda: {"id": inventario["recursos_proprios"][0]["id"].upper(), "type": inventario["recursos_proprios"][0]["tipo"]}),
                ("atribuicoes_proprias", 0, "papeis", lambda: c.papel_az(identificador=inventario["atribuicoes_proprias"][0]["id"].upper(), principal=novo_guid(), escopo=f"/subscriptions/{c.assinatura}")),
        ):
            with self.subTest(chave):
                dados = {"recursos": c.recursos_base(), "papeis": c.papeis_base()}
                dados[base] = dados[base] + [fonte()]
                mensagem = self.recusa("já constam na linha de base", **dados)
                self.assertNotIn(inventario[chave][indice]["id"], mensagem)

    def test_linha_de_base_com_itens_dentro_do_grupo_recusa(self):
        c = self.c
        self.recusa("dentro do grupo exclusivo", recursos=c.recursos_base() + [{"id": c.recurso("Microsoft.Storage/storageAccounts", "outro"), "type": "Microsoft.Storage/storageAccounts"}])
        self.recusa("dentro do grupo exclusivo", recursos=c.recursos_base() + [{"id": c.recurso("Microsoft.Storage/storageAccounts", "outro", c.gerenciado), "type": "X.Y/z"}])
        self.recusa("escopo do grupo exclusivo", papeis=c.papeis_base() + [c.papel_az(escopo=c.prefixo)])
        self.recusa("escopo do grupo exclusivo", papeis=c.papeis_base() + [c.papel_az(escopo=c.recurso("Microsoft.Storage/storageAccounts", "z"))])

    def test_principal_proprio_com_papel_na_linha_de_base_nao_e_proprio(self):
        mensagem = self.recusa("já existiam antes do laboratório", papeis=self.c.papeis_base() + [self.c.papel_az(principal=self.c.mi2)])
        self.assertNotIn(self.c.mi2, mensagem)

    def test_linha_de_base_de_outra_assinatura_e_recusada_na_leitura(self):
        with self.assertRaises(ErroLab):
            self.validar(grupos=[{"id": f"/subscriptions/{novo_guid()}/resourceGroups/rg", "name": "rg"}])


# ----------------------------------------------------------------------------------------------------------------------
# Plano
# ----------------------------------------------------------------------------------------------------------------------

class PlanoTests(ComPasta):
    def plano(self, dados=None, base=True) -> enc.Plano:
        return enc.montar_plano(enc.inventario_de_dados(dados or self.c.inventario()), base)

    def test_ordem_obrigatoria_das_fases_e_dos_tipos(self):
        plano = self.plano()
        esperado = (["aplicativo_container_app"] * 2 + ["job_container_app"] + ["link_privado_busca"] * 2
                    + ["credencial_entra", "principal_servico_entra", "expurgo_principal_servico", "aplicativo_entra", "expurgo_aplicativo"]
                    + ["aplicativo_entra", "expurgo_aplicativo"] + ["atribuicao_papel"] * 2 + ["workspace_logs", "ambiente_container_apps",
                                                                                           "grupo_exclusivo", "expurgo_conta_de_modelos", "expurgo_cofre_de_chaves"])
        self.assertEqual([p.tipo for p in plano.passos], esperado)
        self.assertEqual({p.tipo for p in plano.passos}, set(enc.TIPOS_DE_PASSO), "o cenário cobre todos os tipos de passo")
        fases = [p.fase for p in plano.passos]
        self.assertEqual(fases, sorted(fases))
        self.assertEqual(sorted(set(fases)), list(range(1, 9)))
        self.assertEqual([p.numero for p in plano.passos], list(range(1, len(plano.passos) + 1)))
        for passo in plano.passos:
            self.assertEqual(passo.fase, enc.TIPOS_DE_PASSO[passo.tipo][0])
        indice = {p.tipo: n for n, p in reversed(list(enumerate(plano.passos)))}
        self.assertLess(max(n for n, p in enumerate(plano.passos) if p.tipo == "link_privado_busca"), min(n for n, p in enumerate(plano.passos) if p.tipo == "grupo_exclusivo"))
        self.assertLess(max(n for n, p in enumerate(plano.passos) if p.fase < 7), indice["grupo_exclusivo"])
        self.assertEqual(plano.passos[-3].tipo, "grupo_exclusivo", "o grupo é o último passo antes dos expurgos")

    def test_inventario_sem_itens_de_um_tipo_omite_o_passo_e_a_fase(self):
        casos = {
            "consumidores": (lambda d: d.update(recursos_proprios=[r for r in d["recursos_proprios"] if "containerApps" not in r["id"] and "/jobs/" not in r["id"]]), 1,
                             {"aplicativo_container_app", "job_container_app"}),
            "links": (lambda d: d.update(shared_private_links=[]), 2, {"link_privado_busca"}),
            "entra": (lambda d: d.update(identidades_entra=[]), None, {"credencial_entra", "principal_servico_entra", "expurgo_principal_servico", "aplicativo_entra", "expurgo_aplicativo"}),
            "atribuicoes": (lambda d: d.update(atribuicoes_proprias=[]), 4, {"atribuicao_papel"}),
            "workspace": (lambda d: d.update(recursos_proprios=[r for r in d["recursos_proprios"] if "workspaces" not in r["id"]]), 5, {"workspace_logs"}),
            "ambientes": (lambda d: d.update(recursos_proprios=[r for r in d["recursos_proprios"] if "managedEnvironments" not in r["id"]]), 6, {"ambiente_container_apps"}),
            "expurgos": (lambda d: d.update(expurgos=[]), 8, {"expurgo_conta_de_modelos", "expurgo_cofre_de_chaves"}),
        }
        for rotulo, (mutacao, fase, tipos) in casos.items():
            with self.subTest(rotulo):
                dados = self.c.inventario()
                mutacao(dados)
                plano = self.plano(dados)
                self.assertFalse(tipos & {p.tipo for p in plano.passos})
                if fase:
                    self.assertIn(fase, plano.fases_omitidas)
                    self.assertNotIn(f"FASE {fase} de 8", enc.plano_em_texto(plano))
                self.assertIn("grupo_exclusivo", {p.tipo for p in plano.passos}, "o grupo sempre existe")
        dados = self.c.inventario()
        for chave in ("recursos_proprios", "shared_private_links", "atribuicoes_proprias", "identidades_entra", "expurgos", "principais_proprios"):
            dados[chave] = []
        del dados["tenant"], dados["grupo_gerenciado"]
        plano = self.plano(dados)
        self.assertEqual([p.tipo for p in plano.passos], ["grupo_exclusivo"])
        self.assertNotIn("Get-EstadoGraph", plano.preparacao, "sem objetos do Entra ID não há helper do Graph")

    def test_cada_passo_tem_titulo_efeito_comando_e_verificacao_de_ausencia(self):
        plano = self.plano()
        for passo in plano.passos:
            with self.subTest(passo.numero):
                self.assertTrue(passo.titulo and passo.comando and passo.verificacao)
                self.assertIn(passo.efeito, (enc.REVERSIVEL, enc.IRREVERSIVEL))
                # a verificação responde ausente, presente ou indeterminado: por listagem ou por consulta direta ao Graph
                corpo = desembrulhar(passo.verificacao)
                self.assertTrue(("'ausente'" in corpo and "'presente'" in corpo and "'indeterminado'" in corpo)
                                or corpo.startswith("Get-EstadoGraph '"), corpo)
        efeitos = {p.tipo: p.efeito for p in plano.passos}
        self.assertEqual(efeitos["principal_servico_entra"], "reversivel")
        self.assertEqual(efeitos["aplicativo_entra"], "reversivel")
        self.assertEqual(efeitos["grupo_exclusivo"], "irreversivel")
        self.assertEqual(efeitos["expurgo_aplicativo"], "irreversivel")

    def test_comandos_exatos_com_valores_validados_entre_aspas_simples(self):
        c, plano = self.c, self.plano()
        texto = "\n".join(p.comando for p in plano.passos)
        sub, grupo = f"'{c.assinatura}'", f"'{c.grupo}'"
        esperados = [
            f"az containerapp delete --ids '{c.recurso('Microsoft.App/containerApps', 'chat')}' --yes",
            f"az containerapp job delete --ids '{c.recurso('Microsoft.App/jobs', 'sonda')}' --yes",
            f"az search shared-private-link-resource delete --resource-group {grupo} --service-name '{c.busca}' --name 'blob' --subscription {sub} --yes",
            f"az ad app credential delete --id '{c.objeto1}' --key-id '{c.chave1}'",
            f"az ad sp delete --id '{c.sp1}'",
            f"az ad app delete --id '{c.objeto1}'",
            f"az rest --method delete --url 'https://graph.microsoft.com/v1.0/directory/deletedItems/{c.sp1}'",
            f"az rest --method delete --url 'https://graph.microsoft.com/v1.0/directory/deletedItems/{c.objeto1}'",
            f"az role assignment delete --ids '{c.atribuicao1}'",
            f"az monitor log-analytics workspace delete --ids '{c.recurso('Microsoft.OperationalInsights/workspaces', 'logs')}' --force true --yes",
            f"az containerapp env delete --ids '{c.recurso('Microsoft.App/managedEnvironments', 'env')}' --yes --no-wait",
            f"az group delete --name {grupo} --subscription {sub} --yes",
            f"az cognitiveservices account purge --location 'brazilsouth' --resource-group {grupo} --name 'ais' --subscription {sub}",
            f"az keyvault purge --name 'kvlab' --location 'brazilsouth' --subscription {sub}",
        ]
        for esperado in esperados:
            self.assertIn(esperado, texto)
        self.assertEqual(texto.count("az group delete"), 1)
        self.assertEqual(texto.count("az role assignment delete"), 2, "uma revogação por atribuição do inventário")
        self.assertEqual(texto.count("az ad app delete"), 2)
        self.assertNotIn("--ids '" + c.atribuicao1 + "' '", texto)

    def test_nenhum_comando_usa_curinga_all_filtro_ou_id_deduzido(self):
        plano = self.plano()
        for passo in plano.passos:
            for bloco in (passo.comando, passo.verificacao):
                for proibido in ("*", "--all", "--filter", "-like", "--assignee", "--role ", "?", "%", "az group wait", " wait ", "--query \"", "\"", "`"):
                    self.assertNotIn(proibido, bloco, f"passo {passo.numero}: {proibido!r}")
        # todo GUID impresso vem do inventário
        inv = self.c.carregado()
        conhecidos = {inv.assinatura, inv.tenant, *inv.principais_proprios}
        for i in inv.identidades:
            conhecidos |= {i.objeto_id, i.app_id, *i.chaves}
        for a in inv.atribuicoes:
            conhecidos |= {a.papel_id, a.id.rsplit("/", 1)[-1].lower()}
        import re
        impressos = set(re.findall(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", (enc.plano_em_texto(plano) + plano.preparacao).lower()))
        self.assertEqual(impressos - conhecidos, set(), "nenhum identificador foi deduzido")
        # o grupo gerenciado nunca é alvo de um comando de alteração
        texto = "\n".join(p.comando for p in plano.passos)
        self.assertNotIn(self.c.gerenciado, texto)
        fechamento = "\n".join(i.texto + "\n" + i.comando for i in plano.fechamento)
        self.assertIn(f"az group exists --name '{self.c.gerenciado}'", fechamento)
        self.assertNotIn("delete", fechamento.replace("--momento depois", ""), "o fechamento só lê")

    def test_guardas_de_execucao_conferem_o_objeto_antes_de_apagar(self):
        passos: dict[str, enc.Passo] = {}
        for passo in self.plano().passos:
            passos.setdefault(passo.tipo, passo)  # o primeiro de cada tipo é o da primeira identidade
        app, sp, item = passos["aplicativo_entra"].comando, passos["principal_servico_entra"].comando, passos["expurgo_aplicativo"].comando
        # o `az ad ... --id` resolve primeiro pelo appId: o ID de OBJETO lido também precisa conferir, além do appId e do nome
        for exigido in (f"$app.id -eq '{self.c.objeto1}'", f"$app.appId -eq '{self.c.app1}'", f"$app.nome -eq '{self.c.nome_app1}'",
                        "--query '{id:id,appId:appId,nome:displayName}'", "$LASTEXITCODE -eq 0", "$app = $null"):
            self.assertIn(exigido, app)
        for exigido in (f"$sp.id -eq '{self.c.sp1}'", f"$sp.appId -eq '{self.c.app1}'", "--query '{id:id,appId:appId}'", "$LASTEXITCODE -eq 0", "$sp = $null"):
            self.assertIn(exigido, sp)
        for exigido in (f"$item.id -eq '{self.c.objeto1}'", f"$item.appId -eq '{self.c.app1}'", "$LASTEXITCODE -eq 0", "$item = $null"):
            self.assertIn(exigido, item)
        papel = passos["atribuicao_papel"].comando
        for exigido in ("$todas = az role assignment list", "$achadas = @(@($todas) | Where-Object { $_ -and $_.id -ieq",
                        "$achadas.Count -eq 1", f"$achadas[0].principalId -ieq '{self.c.mi1}'", f"$achadas[0].scope -ieq '{self.c.prefixo}'",
                        f"/{self.c.papel1}'", "$LASTEXITCODE -eq 0", "$todas = $null; $achadas = $null"):
            self.assertIn(exigido, papel)
        self.assertNotIn("ConvertFrom-Json | Where-Object", papel,
                         "no Windows PowerShell 5.1 isso entrega a lista inteira ao filtro: a leitura e o filtro são etapas separadas")
        grupo = passos["grupo_exclusivo"].comando
        self.assertIn("$_ -notin $esperados", grupo, "o grupo só é apagado se tudo o que ele contém está no inventário")
        for recurso in self.c.inventario()["recursos_proprios"]:
            self.assertIn(f"'{recurso['id']}'", grupo)
        cofre = passos["expurgo_cofre_de_chaves"].comando
        self.assertIn("StartsWith('" + self.c.prefixo + "/'", cofre)
        self.assertIn("$cofre -is [string]", cofre)

    def test_a_atribuicao_avisa_que_o_principal_e_o_id_de_objeto_e_nunca_o_clientid(self):
        plano = self.plano()
        atribuicoes = [p for p in plano.passos if p.tipo == "atribuicao_papel"]
        self.assertEqual(len(atribuicoes), 2)
        for passo in atribuicoes:
            self.assertIn("ID de OBJETO (principalId), nunca o clientId", passo.nota)
        self.assertIn("IDs de OBJETO, nunca o clientId nem o appId", " ".join(plano.precondicoes))
        self.assertIn("nunca o clientId", enc.modelo_de_inventario()["principais_proprios"][0])
        self.assertIn("ID de OBJETO", enc.modelo_de_inventario()["identidades_entra"][0]["principal_id"])
        self.assertIn("IDs de OBJETO", enc.comandos_de_captura(self.c.assinatura, self.c.grupo, "depois", str(self.pasta), self.c.carregado()))

    def test_a_verificacao_nunca_aceita_codigo_de_saida_ou_espera_como_prova(self):
        for passo in self.plano().passos:
            self.assertNotIn("wait", passo.verificacao.lower())
            self.assertNotIn(" wait ", passo.comando.lower())
            corpo = desembrulhar(passo.verificacao)
            if "az " in corpo:
                self.assertIn("$LASTEXITCODE", corpo)
                self.assertIn("NÃO prova ausência", corpo)
        texto = enc.plano_em_texto(self.plano())
        self.assertIn("NÃO prova ausência", texto)
        self.assertIn("nenhum bloqueio administrativo será removido", texto.lower())
        self.assertIn("Sem curingas", texto)
        self.assertIn("LockedSPLResourceFound", texto)

    def test_plano_abre_com_precondicoes_e_fecha_com_a_conferencia_e_os_custos(self):
        plano = self.plano()
        pre = " ".join(plano.precondicoes).lower()
        for exigido in ("autorizou", "linha de base", "custo", "bloqueio", "curinga", "grupo gerenciado", "papéis herdados", "powershell 7",
                        "mesma janela"):
            self.assertIn(exigido, pre)
        fechamento = " ".join(i.texto + " " + i.comando for i in plano.fechamento)
        self.assertIn("--etapa capturar --momento depois", fechamento)
        self.assertIn("--etapa conferir", fechamento)
        self.assertIn("custo zero", fechamento)
        self.assertIn("resposta vazia", fechamento)
        texto = enc.plano_em_texto(plano)
        preparacao = texto.index("PREPARAÇÃO (cole PRIMEIRO")
        self.assertLess(texto.index("ANTES DE COMEÇAR"), preparacao)
        self.assertLess(preparacao, texto.index("FASE 1"))
        self.assertLess(texto.index("FASE 8"), texto.index("FECHAMENTO"))

    def test_sem_linha_de_base_o_plano_e_uma_previa_e_diz_isso(self):
        previa = enc.plano_em_texto(self.plano(base=False))
        self.assertIn("PRÉVIA", previa)
        self.assertIn("NÃO CONFERIDA", previa)
        self.assertNotIn("PRÉVIA", enc.plano_em_texto(self.plano(base=True)))

    def test_link_usa_nomes_extraidos_do_id_literal_do_inventario(self):
        plano = self.plano()
        links = [p for p in plano.passos if p.tipo == "link_privado_busca"]
        self.assertIn("--name 'modelos'", links[1].comando)
        self.assertIn(f"--service-name '{self.c.busca}'", links[1].comando)

    def test_plano_em_json_equivale_ao_texto(self):
        plano = self.plano()
        dados = enc.plano_em_dict(plano)
        self.assertEqual([p["tipo"] for p in dados["passos"]], [p.tipo for p in plano.passos])
        self.assertTrue(dados["somente_texto"])
        self.assertEqual(dados["linha_de_base"], "conferida")
        self.assertEqual(json.loads(json.dumps(dados))["passos"][0]["comando"], plano.passos[0].comando)

    def test_preparacao_confere_a_conta_ativa_e_obtem_o_token_do_tenant_do_inventario(self):
        plano = self.plano()
        self.assertIn(f"$conta.id -ne '{self.c.assinatura}'", plano.preparacao)
        self.assertIn(f"$conta.tenantId -ne '{self.c.tenant}'", plano.preparacao)
        self.assertIn(f"--tenant '{self.c.tenant}'", plano.preparacao)
        self.assertIn("-SkipHttpErrorCheck", plano.preparacao)
        self.assertIn("-MaximumRedirection 0", plano.preparacao)
        # o token só é atribuído, testado e enviado no cabeçalho do Graph: nunca impresso nem gravado
        for texto in (plano.preparacao, enc.comandos_de_captura(self.c.assinatura, self.c.grupo, "depois", str(self.pasta), self.c.carregado())):
            restante = texto
            for permitido in ("$script:TokenGraph = az account get-access-token", "-not $script:TokenGraph", "('Bearer ' + $script:TokenGraph)"):
                restante = restante.replace(permitido, "")
            self.assertNotIn("TokenGraph", restante)
            self.assertIn("https://graph.microsoft.com/v1.0/", texto, "o token só vai para o endereço do Graph")
            self.assertEqual(texto.count("Invoke-WebRequest"), 1)

    def test_todo_bloco_impresso_e_um_comando_composto_que_recusa_fora_do_powershell_7_e_sem_a_preparacao(self):
        c = self.c
        marca = f"'{c.assinatura}/{c.grupo}'"
        blocos = blocos_de_powershell(c, self.plano(), str(self.pasta))
        self.assertEqual({categoria for _, _, categoria in blocos}, {"preparacao", "comando", "verificacao", "captura"})
        for rotulo, bloco, categoria in blocos:
            with self.subTest(rotulo):
                linhas = bloco.splitlines()
                self.assertTrue(all(linha.strip() for linha in linhas), "sem linhas em branco: o console as trataria como o fim do bloco")
                if categoria == "captura":
                    self.assertTrue(all(linha.startswith("#") for linha in linhas[:2]))
                    self.assertEqual(linhas[2], "if ($PSVersionTable.PSVersion.Major -lt 7) {")
                    self.assertIn("PowerShell 7 (pwsh)", linhas[3])
                    self.assertEqual((linhas[4], linhas[-1]), ("} else {", "}"))
                elif categoria == "preparacao":
                    self.assertEqual(linhas[:2], ["$script:EncerramentoPronto = $null", "if ($PSVersionTable.PSVersion.Major -lt 7) {"],
                                     "uma preparação que falha apaga a marca de uma preparação anterior")
                    self.assertIn("PowerShell 7 (pwsh)", linhas[2])
                    self.assertEqual(linhas[3], "} else {")
                    self.assertEqual(linhas[-3:], [f"    $script:EncerramentoPronto = {marca}", "    'Preparação concluída nesta janela: a conta ativa "
                                                                                              "confere com o inventário.'", "}"])
                    for conferencia in ("throw 'A conta ativa", "throw 'Não foi possível obter o token"):
                        self.assertLess(bloco.index(conferencia), bloco.index(f"$script:EncerramentoPronto = {marca}"),
                                        "a marca só é gravada depois de todas as conferências")
                else:
                    self.assertEqual(linhas[0], "if ($PSVersionTable.PSVersion.Major -lt 7) {")
                    self.assertTrue(linhas[1].startswith("    Write-Warning '") and "PowerShell 7 (pwsh)" in linhas[1] and "Nada foi executado." in linhas[1])
                    self.assertEqual(linhas[2], f"}} elseif ($script:EncerramentoPronto -ne {marca}) {{")
                    self.assertTrue(linhas[3].startswith("    Write-Warning '") and "PREPARAÇÃO" in linhas[3] and "Nada foi executado." in linhas[3])
                    self.assertEqual((linhas[4], linhas[-1]), ("} else {", "}"))
                    if categoria == "verificacao":
                        self.assertTrue(linhas[1].endswith("'; 'indeterminado'") and linhas[3].endswith("'; 'indeterminado'"),
                                        "um bloco que decide ausência nunca responde 'ausente' quando se recusa")
                    else:
                        self.assertNotIn("indeterminado", linhas[1] + linhas[3])

    def test_nenhum_trecho_depende_de_recurso_exclusivo_do_powershell_7_fora_do_auxiliar_do_graph(self):
        proibidos = ((r"&&", "encadeamento &&"), (r"\|\|", "encadeamento ||"), (r"\?", "?? , ?. , ?[ ou ternário"), (r"-Parallel\b", "-Parallel"),
                     (r"-AsHashtable\b", "-AsHashtable"), (r"-NoEnumerate\b", "-NoEnumerate"), (r"\$Is(Windows|Linux|MacOS)\b", "$IsWindows e afins"),
                     (r"\$PSStyle\b", "$PSStyle"), (r"\b(Get-Error|Join-String|Test-Json)\b", "cmdlet do PowerShell 7"),
                     (r"utf8NoBOM", "-Encoding utf8NoBOM"), (r"-(ResponseHeaders|StatusCode)Variable\b", "variável de resposta do web cmdlet"),
                     (r"-SkipCertificateCheck\b", "-SkipCertificateCheck"))
        for rotulo, bloco, _ in blocos_de_powershell(self.c, self.plano(), str(self.pasta)):
            with self.subTest(rotulo):
                sem_textos = re.sub(r"'[^']*'", "''", re.sub(r"(?m)^\s*#.*$", "", bloco))
                for padrao, descricao in proibidos:
                    self.assertIsNone(re.search(padrao, sem_textos), f"{rotulo}: {descricao} só existe no PowerShell 7 e não tem guarda")
                if "-SkipHttpErrorCheck" in bloco:  # a única exceção: o auxiliar do Graph, que só é definido depois da guarda de versão
                    self.assertIn("function Get-EstadoGraph {", bloco)
                    self.assertTrue(rotulo.startswith(("preparacao", "captura")), rotulo)

    def test_a_barreira_final_recusa_valor_fora_do_conjunto_seguro_com_codigo_de_defeito(self):
        for valor in ("", "a b", "a'b", 'a"b', "a;b", "a$b", "a`b", "a\nb", "a|b", "a&b", "a(b)", "a{b}", "a*b", "a?b", "a%b", "a\\b", "ã", "a\x00b"):
            with self.subTest(valor=valor):
                with self.assertRaises(ErroLab) as contexto:
                    enc._aspas(valor)
                self.assertEqual(contexto.exception.codigo, CODIGO_INESPERADO)
        self.assertEqual(enc._aspas("abc-1.2_3/x:y"), "'abc-1.2_3/x:y'")
        with self.assertRaises(ErroLab) as contexto:
            enc._preencher("a @@X@@ b @@Y@@", X="1")
        self.assertEqual(contexto.exception.codigo, CODIGO_INESPERADO)

    def test_valor_perigoso_que_escapa_da_validacao_nao_chega_a_nenhum_comando(self):
        inv = self.c.carregado()
        perigoso = "x'; Remove-Item -Recurse C:\\ #"
        identidade, atribuicao, expurgo = inv.identidades[0], inv.atribuicoes[0], inv.expurgos[0]
        forjados = {
            "grupo": dataclasses.replace(inv, grupo=perigoso),
            "assinatura": dataclasses.replace(inv, assinatura=perigoso),
            "recurso": dataclasses.replace(inv, recursos=(enc.Recurso(inv.recursos[0].id + perigoso, inv.recursos[0].tipo), *inv.recursos[1:])),
            "link": dataclasses.replace(inv, links=(enc.Link(inv.links[0].id, perigoso, "x"), *inv.links[1:])),
            "identidade": dataclasses.replace(inv, identidades=(dataclasses.replace(identidade, nome=perigoso), *inv.identidades[1:])),
            "credencial": dataclasses.replace(inv, identidades=(dataclasses.replace(identidade, chaves=(perigoso,)), *inv.identidades[1:])),
            "atribuicao": dataclasses.replace(inv, atribuicoes=(dataclasses.replace(atribuicao, escopo=perigoso), *inv.atribuicoes[1:])),
            "expurgo": dataclasses.replace(inv, expurgos=(dataclasses.replace(expurgo, nome=perigoso), *inv.expurgos[1:])),
        }
        for rotulo, forjado in forjados.items():
            with self.subTest(rotulo):
                with self.assertRaises(ErroLab) as contexto:
                    enc.montar_plano(forjado, True)
                self.assertEqual(contexto.exception.codigo, CODIGO_INESPERADO)
        with self.assertRaises(ErroLab):
            enc.comandos_de_captura(perigoso, self.c.grupo, "antes", "pasta")

    def test_relatorio_do_plano_so_tem_contagens_e_vocabulario_fechado(self):
        sentinela = f"sentinela-{uuid.uuid4().hex}"
        dados = self.c.inventario()
        dados["identidades_entra"][0]["nome"] = sentinela
        dados["recursos_proprios"][0]["id"] = dados["recursos_proprios"][0]["id"].replace("/chat", f"/{sentinela}")
        plano = self.plano(dados)
        relatorio = enc.relatorio_do_plano(plano)
        texto = json.dumps(relatorio, ensure_ascii=False)
        for valor in (sentinela, self.c.assinatura, self.c.tenant, self.c.grupo, self.c.objeto1, "az ", "--ids"):
            self.assertNotIn(valor, texto)
        self.assertEqual(relatorio["total_de_passos"], len(plano.passos))
        self.assertEqual(sum(relatorio["passos_por_tipo"].values()), len(plano.passos))
        self.assertTrue(set(relatorio["passos_por_tipo"]) <= set(enc.TIPOS_DE_PASSO))
        self.assertEqual(relatorio["recursos_removidos_com_o_grupo"], 4)
        self.assertEqual(set(relatorio["passos_por_efeito"]), {"reversivel", "irreversivel"})


# ----------------------------------------------------------------------------------------------------------------------
# Captura
# ----------------------------------------------------------------------------------------------------------------------

class CapturaTests(ComPasta):
    def test_captura_antes_exporta_tres_listas_sem_sobrescrever_e_exige_grupo_inexistente(self):
        texto = enc.comandos_de_captura(self.c.assinatura, self.c.grupo, "antes", str(self.pasta))
        for esperado in ("az group list --subscription $assinatura", "az resource list --subscription $assinatura",
                         "az role assignment list --all --subscription $assinatura", "--fill-principal-name false",
                         "--fill-role-definition-name false", "Test-Path -LiteralPath", "az group exists --name $grupo",
                         "'grupos-antes.json'", "'recursos-antes.json'", "'papeis-antes.json'", "$LASTEXITCODE"):
            self.assertIn(esperado, texto)
        self.assertIn("if ($existe -ne 'false') { throw", texto, "a linha de base só vale se o grupo ainda não existir")
        linhas_de_gravacao = [linha for linha in texto.splitlines() if "Out-File" in linha]
        self.assertEqual(len(linhas_de_gravacao), 3)
        self.assertTrue(all("-NoClobber" in linha for linha in linhas_de_gravacao), "nenhuma gravação pode sobrescrever")
        self.assertIn(f"$assinatura = '{self.c.assinatura}'", texto)
        self.assertNotIn("presenca", texto)
        self.assertNotIn("delete", texto)
        self.assertNotIn("Get-EstadoGraph", texto)
        self.assertLess(texto.index("az group exists"), texto.index("az group list"), "o grupo é conferido antes de qualquer leitura")
        self.assertLess(texto.index("az role assignment list"), texto.index("Out-File"), "as leituras acontecem antes de gravar")
        self.assertEqual(texto.count("throw"), 6, "cada consulta, cada leitura e os arquivos existentes interrompem o bloco antes de gravar")
        self.assertIn("Write-Warning", texto.splitlines()[3], "a versão é recusada pelo comando composto, sem throw solto")

    def test_captura_depois_inclui_presenca_com_identificadores_logicos_sem_ids(self):
        inv = self.c.carregado()
        texto = enc.comandos_de_captura(self.c.assinatura, self.c.grupo, "depois", str(self.pasta), inv)
        for esperado in ("'grupos-depois.json'", "'recursos-depois.json'", "'papeis-depois.json'", "'presenca-depois.json'", "Get-EstadoGraph",
                         f"applications/{self.c.objeto1}", f"servicePrincipals/{self.c.mi1}", f"directory/deletedItems/{self.c.sp1}",
                         "az cognitiveservices account list-deleted", "az keyvault list-deleted", "$conta.tenantId"):
            self.assertIn(esperado, texto)
        itens = enc.itens_de_presenca(inv)
        self.assertEqual(len(itens), 2 + 3 + 3 + 2, "aplicativos, principais, itens excluídos e expurgos")
        for item in itens:
            self.assertIn(f"$estados['{item.chave}']", texto)
            for id_ in (self.c.objeto1, self.c.sp1, self.c.mi1, "ais", "kvlab"):
                self.assertNotIn(id_, item.chave, "o identificador lógico não traz o ID")
        self.assertEqual({i.categoria for i in itens}, {enc.ENTRA_APLICATIVOS, enc.ENTRA_PRINCIPAIS, enc.ENTRA_EXCLUIDOS, enc.EXPURGO_MODELOS, enc.EXPURGO_COFRE})

    def test_identificador_logico_e_estavel_mesmo_se_a_ordem_do_inventario_mudar(self):
        dados = self.c.inventario()
        original = {i.chave for i in enc.itens_de_presenca(enc.inventario_de_dados(dados))}
        dados["identidades_entra"].reverse()
        dados["principais_proprios"].reverse()
        dados["expurgos"].reverse()
        self.assertEqual({i.chave for i in enc.itens_de_presenca(enc.inventario_de_dados(dados))}, original)

    def test_captura_depois_sem_objetos_do_entra_nao_traz_o_helper_do_graph(self):
        dados = self.c.inventario()
        dados["principais_proprios"], dados["identidades_entra"], dados["atribuicoes_proprias"], dados["expurgos"] = [], [], [], []
        texto = enc.comandos_de_captura(self.c.assinatura, self.c.grupo, "depois", str(self.pasta), enc.inventario_de_dados(dados))
        self.assertNotIn("Get-EstadoGraph", texto)
        self.assertNotIn("presenca-depois", texto)
        self.assertNotIn("get-access-token", texto)

    def test_captura_depois_exige_inventario_e_recusa_assinatura_ou_grupo_diferentes(self):
        with self.assertRaises(ErroLab) as contexto:
            enc.comandos_de_captura(self.c.assinatura, self.c.grupo, "depois", str(self.pasta))
        self.assertIn("--inventario", str(contexto.exception))
        inv = self.c.carregado()
        for assinatura, grupo in ((novo_guid(), self.c.grupo), (self.c.assinatura, "rg-outro")):
            with self.assertRaises(ErroLab) as contexto:
                enc.comandos_de_captura(assinatura, grupo, "depois", str(self.pasta), inv)
            self.assertIn("não combinam com o inventário", str(contexto.exception))

    def test_pasta_com_aspas_ou_expansao_e_recusada(self):
        for pasta in ("C:\\x'; Remove-Item -Recurse C:\\ #", "$(Get-Date)", "a`b", "a;b", "a\nb", "a'b", "a\"b", "‘a’", "a|b", "a&b", "", " a", "a ", "x" * 241, "a[1]", "a*", "a?"):
            with self.subTest(pasta=pasta):
                with self.assertRaises(ErroLab):
                    enc.comandos_de_captura(self.c.assinatura, self.c.grupo, "antes", pasta)
        for pasta in (r"C:\Users\João Silva\encerramento", "./encerramento", "pasta (1)", "~/lab"):
            self.assertIn(f"$pasta = '{pasta}'", enc.comandos_de_captura(self.c.assinatura, self.c.grupo, "antes", pasta))

    def test_momento_invalido_e_recusado(self):
        with self.assertRaises(ErroLab):
            enc.comandos_de_captura(self.c.assinatura, self.c.grupo, "durante", "p")


# ----------------------------------------------------------------------------------------------------------------------
# Conferência
# ----------------------------------------------------------------------------------------------------------------------

class ConferenciaTests(ComPasta):
    def estado(self, saida: str, criterio: str) -> str:
        for linha in saida.splitlines():
            if f"] {criterio}:" in linha:
                return linha.split("]")[0].strip("[ ").lower()
        raise AssertionError(f"critério {criterio} ausente da saída:\n{saida}")

    def reprovados(self, saida: str) -> set[str]:
        return {linha.split("] ")[1].split(":")[0] for linha in saida.splitlines() if linha.strip().startswith("[REPROVADO]")}

    def test_ciclo_completo_plano_e_conferencia_aprovada(self):
        caminhos = self.montar()
        relatorio = self.pasta / "plano.json"
        codigo, saida, erro = executar_separado("--etapa", "plano", "--inventario", str(caminhos["inventario"]), "--grupos-antes", str(caminhos["grupos-antes"]),
                                               "--recursos-antes", str(caminhos["recursos-antes"]), "--papeis-antes", str(caminhos["papeis-antes"]), "--relatorio", str(relatorio))
        self.assertEqual(codigo, CODIGO_OK, saida + erro)
        self.assertIn("FASE 8 de 8", saida)
        self.assertNotIn("PRÉVIA", saida)
        self.assertEqual(json.loads(relatorio.read_text(encoding="utf-8"))["linha_de_base"], "conferida")
        conferencia = self.pasta / "conferencia.json"
        codigo, saida = self.conferir(caminhos, "--relatorio", str(conferencia))
        self.assertEqual(codigo, CODIGO_OK, saida)
        self.assertIn("Resultado: APROVADO", saida)
        dados = json.loads(conferencia.read_text(encoding="utf-8"))
        self.assertEqual(dados["resultado"], "aprovado")
        self.assertEqual(dados["contagem"], {"atendido": 13, "reprovado": 0, "pendente": 0, "nao_aplicavel": 0})
        self.assertEqual({v["id"] for v in dados["verificacoes"]}, set(enc.CRITERIOS))
        self.assertEqual(dados["linha_de_base"], {"grupos": 3, "recursos": 3, "atribuicoes": 3})
        self.assertEqual(dados["avisos"], [], "uma exportação real nunca repete a ordem e o texto da linha de base")
        self.assertEqual(len(dados["entradas_sha256"]), 1 + 3 + 3)

    def test_cada_criterio_reprova_quando_o_resultado_diverge(self):
        def casos(c: Cenario) -> dict:
            recurso_proprio = {"id": c.recurso("Microsoft.Storage/storageAccounts", "restou"), "type": "Microsoft.Storage/storageAccounts"}
            return {
                "grupo_proprio_ausente": lambda g, r, p: (g + [c.grupo_az(c.grupo.upper())], r, p),
                "grupo_gerenciado_ausente": lambda g, r, p: (g + [c.grupo_az(c.gerenciado)], r, p),
                "grupos_anteriores_preservados": lambda g, r, p: (g[1:], r, p),
                "recursos_anteriores_preservados": lambda g, r, p: (g, r[1:], p),
                "recursos_anteriores_preservados:tipo": lambda g, r, p: (g, [dict(r[0], type="Outro.Tipo/x")] + r[1:], p),
                "recursos_proprios_ausentes": lambda g, r, p: (g, r + [recurso_proprio], p),
                "recursos_proprios_ausentes:gerenciado": lambda g, r, p: (g, r + [{"id": c.recurso("Microsoft.Network/x", "n", c.gerenciado), "type": "Microsoft.Network/x"}], p),
                "atribuicoes_anteriores_preservadas": lambda g, r, p: (g, r, p[1:]),
                "atribuicoes_anteriores_preservadas:principal": lambda g, r, p: (g, r, [dict(p[0], principalId=novo_guid())] + p[1:]),
                "atribuicoes_anteriores_preservadas:papel": lambda g, r, p: (g, r, [dict(p[0], roleDefinitionId="/x/" + novo_guid())] + p[1:]),
                "atribuicoes_anteriores_preservadas:escopo": lambda g, r, p: (g, r, [dict(p[1], scope=f"/subscriptions/{c.assinatura}")] + p[:1] + p[2:]),
                "atribuicoes_proprias_ausentes": lambda g, r, p: (g, r, p + [c.papel_az(identificador=c.atribuicao1)]),
                "atribuicoes_proprias_ausentes:escopo": lambda g, r, p: (g, r, p + [c.papel_az(escopo=c.prefixo, principal=novo_guid())]),
                "atribuicoes_proprias_ausentes:recurso": lambda g, r, p: (g, r, p + [c.papel_az(escopo=c.recurso("Microsoft.Storage/storageAccounts", "z"))]),
            }
        for rotulo in casos(self.c):
            with self.subTest(rotulo):
                c = self.reiniciar()
                base = (c.grupos_base(), c.recursos_base(), c.papeis_base())
                depois = casos(c)[rotulo](*(copy.deepcopy(x) for x in base))
                codigo, saida = self.conferir(self.montar(base=base, depois=depois))
                esperado = rotulo.split(":")[0]
                self.assertEqual(codigo, CODIGO_DIVERGENCIA, saida)
                self.assertEqual(self.estado(saida, esperado), "reprovado", saida)
                self.assertIn("Encerramento REPROVADO", saida)
                self.assertNotIn("Resultado: APROVADO", saida)
        # uma atribuição fora do grupo que não estava na linha de base nem no inventário não é cobrada nem revogada
        c = self.reiniciar()
        caminhos = self.montar(depois=(c.grupos_base(), c.recursos_base(), c.papeis_base() + [c.papel_az()]))
        self.assertEqual(self.conferir(caminhos)[0], CODIGO_OK)

    def test_presenca_presente_reprova_e_indeterminado_ou_ausente_do_arquivo_fica_pendente_nunca_aprovado(self):
        def por_categoria(c: Cenario) -> dict[str, list[str]]:
            agrupado: dict[str, list[str]] = {}
            for item in enc.itens_de_presenca(c.carregado()):
                agrupado.setdefault(item.categoria, []).append(item.chave)
            return agrupado
        categorias = por_categoria(self.c)
        self.assertEqual(set(categorias), {enc.ENTRA_APLICATIVOS, enc.ENTRA_PRINCIPAIS, enc.ENTRA_EXCLUIDOS, enc.EXPURGO_MODELOS, enc.EXPURGO_COFRE})
        for categoria in categorias:
            for situacao, esperado in (("presente", "reprovado"), ("indeterminado", "pendente"), ("faltando", "pendente")):
                with self.subTest(categoria, estado=situacao):
                    c = self.reiniciar()
                    chave = por_categoria(c)[categoria][0]
                    presenca = c.presenca()
                    if situacao == "faltando":
                        del presenca[chave]
                    else:
                        presenca[chave] = situacao
                    codigo, saida = self.conferir(self.montar(presenca=presenca))
                    self.assertEqual((codigo, self.estado(saida, categoria)), (CODIGO_DIVERGENCIA, esperado), saida)
                    self.assertNotIn("Resultado: APROVADO", saida)
                    self.assertIn("Encerramento " + esperado.upper(), saida)
        c = self.reiniciar()
        codigo, saida = self.conferir(self.montar(presenca=None))
        self.assertEqual(codigo, CODIGO_DIVERGENCIA, "sem o arquivo de presença nada do Entra ID foi conferido")
        self.assertIn("NÃO conferido", saida)
        self.assertEqual(self.estado(saida, enc.ENTRA_APLICATIVOS), "pendente")

    def test_reprovado_prevalece_sobre_pendente(self):
        presenca = self.c.presenca("indeterminado")
        caminhos = self.montar(depois=(self.c.grupos_base() + [self.c.grupo_az(self.c.grupo)], self.c.recursos_base(), self.c.papeis_base()), presenca=presenca)
        relatorio = self.pasta / "r.json"
        codigo, saida = self.conferir(caminhos, "--relatorio", str(relatorio))
        self.assertEqual(codigo, CODIGO_DIVERGENCIA)
        self.assertEqual(json.loads(relatorio.read_text(encoding="utf-8"))["resultado"], "reprovado", "o relatório é gravado mesmo sem aprovação")

    def test_inventario_sem_objetos_de_um_tipo_marca_o_criterio_como_nao_aplicavel_e_dispensa_a_presenca(self):
        dados = self.c.inventario()
        dados["principais_proprios"], dados["identidades_entra"], dados["atribuicoes_proprias"], dados["expurgos"] = [], [], [], []
        del dados["grupo_gerenciado"]
        caminhos = self.montar(inventario=dados, presenca=None)
        codigo, saida = self.conferir(caminhos)
        self.assertEqual(codigo, CODIGO_OK, saida)
        self.assertEqual(self.estado(saida, "grupo_gerenciado_ausente"), "não se aplica")
        self.assertEqual(self.estado(saida, enc.EXPURGO_COFRE), "não se aplica")

    def test_arquivo_de_presenca_de_outro_inventario_ou_com_estado_invalido_e_recusado(self):
        presenca = self.c.presenca()
        presenca["aplicativo-" + uuid.uuid4().hex[:8]] = "ausente"
        codigo, saida = self.conferir(self.montar(presenca=presenca))
        self.assertEqual(codigo, CODIGO_USO)
        self.assertIn("outro inventário", saida)
        for invalido in ("Ausente", "ok", None, True, 404):
            with self.subTest(invalido=invalido):
                c = self.reiniciar()
                presenca = c.presenca()
                presenca[next(iter(presenca))] = invalido
                codigo, saida = self.conferir(self.montar(presenca=presenca))
                self.assertEqual(codigo, CODIGO_USO, saida)
                self.assertIn("estado(s) inválido(s)", saida)
        self.reiniciar()
        codigo, saida = self.conferir(self.montar(presenca=["ausente"]))
        self.assertEqual(codigo, CODIGO_USO)

    def test_a_linha_de_base_e_conferida_tambem_na_conferencia(self):
        base = (self.c.grupos_base() + [self.c.grupo_az(self.c.grupo)], self.c.recursos_base(), self.c.papeis_base())
        codigo, saida = self.conferir(self.montar(base=base, depois=(self.c.grupos_base(), self.c.recursos_base(), self.c.papeis_base())))
        self.assertEqual(codigo, CODIGO_USO)
        self.assertIn("já existia", saida)

    def test_linha_de_base_totalmente_vazia_nao_prova_nada_e_fica_pendente(self):
        caminhos = self.montar(base=([], [], []), depois=([], [], []))
        relatorio = self.pasta / "r.json"
        codigo, saida = self.conferir(caminhos, "--relatorio", str(relatorio))
        self.assertEqual(codigo, CODIGO_DIVERGENCIA, saida)
        self.assertEqual(self.estado(saida, "linha_de_base_com_itens"), "pendente")
        self.assertIn("assinatura errada", saida)
        dados = json.loads(relatorio.read_text(encoding="utf-8"))
        self.assertEqual(dados["resultado"], "pendente")
        self.assertEqual(dados["avisos"], ["instantaneos_identicos_aos_da_linha_de_base"],
                         "a linha de base totalmente vazia já é um critério: não repete os avisos por lista")
        codigo, saida, erro = executar_separado("--etapa", "plano", "--inventario", str(caminhos["inventario"]), "--grupos-antes", str(caminhos["grupos-antes"]),
                                               "--recursos-antes", str(caminhos["recursos-antes"]), "--papeis-antes", str(caminhos["papeis-antes"]))
        self.assertEqual(codigo, CODIGO_OK)
        self.assertIn("PRÉVIA", saida)
        self.assertIn("totalmente vazia", erro)

    def test_linha_de_base_parcialmente_vazia_aprova_mas_avisa_que_nada_foi_comparado_na_lista_vazia(self):
        base = (self.c.grupos_base(), [], [])
        caminhos = self.montar(base=base, depois=(list(reversed(self.c.grupos_base())), [], []))
        relatorio = self.pasta / "r.json"
        codigo, saida = self.conferir(caminhos, "--relatorio", str(relatorio))
        self.assertEqual(codigo, CODIGO_OK, saida)
        self.assertEqual(saida.count("[AVISO]"), 2)
        self.assertEqual(json.loads(relatorio.read_text(encoding="utf-8"))["avisos"], ["linha_de_base_sem_recursos", "linha_de_base_sem_atribuicoes"])

    def test_estado_final_identico_a_linha_de_base_aprova_mas_avisa_para_confirmar_que_sao_exportacoes_diferentes(self):
        c = self.c
        caminhos = self.montar(depois=(c.grupos_base(), c.recursos_base(), c.papeis_base()))
        relatorio = self.pasta / "r.json"
        codigo, saida = self.conferir(caminhos, "--relatorio", str(relatorio))
        self.assertEqual(codigo, CODIGO_OK, saida)
        self.assertIn("[AVISO]", saida)
        self.assertIn("idênticos, byte a byte", saida)
        self.assertEqual(json.loads(relatorio.read_text(encoding="utf-8"))["avisos"], ["instantaneos_identicos_aos_da_linha_de_base"])
        # basta um dos três arquivos ser diferente para o aviso desaparecer
        c = self.reiniciar()
        caminhos = self.montar(depois=(c.grupos_base(), c.recursos_base(), c.papeis_base() + [c.papel_az()]))
        codigo, saida = self.conferir(caminhos)
        self.assertEqual(codigo, CODIGO_OK, saida)
        self.assertNotIn("[AVISO]", saida)

    def test_listas_depois_vazias_com_linha_de_base_cheia_nao_viram_aprovacao(self):
        codigo, saida = self.conferir(self.montar(depois=([], [], [])))
        self.assertEqual(codigo, CODIGO_DIVERGENCIA)
        self.assertEqual(self.reprovados(saida), {"grupos_anteriores_preservados", "recursos_anteriores_preservados", "atribuicoes_anteriores_preservadas"})

    def test_instantaneo_depois_invalido_ou_paginado_interrompe_com_codigo_de_uso(self):
        caminhos = self.montar()
        caminhos["recursos-depois"].write_text(json.dumps({"value": [], "nextLink": "https://exemplo.invalido/p2"}), encoding="utf-8")
        codigo, saida = self.conferir(caminhos)
        self.assertEqual(codigo, CODIGO_USO)
        self.assertIn("completar", saida)
        self.assertIn("--recursos-depois", saida)
        caminhos["recursos-depois"].write_text("[ quebrado", encoding="utf-8")
        self.assertEqual(self.conferir(caminhos)[0], CODIGO_USO)

    def test_opcoes_obrigatorias_da_conferencia(self):
        caminhos = self.montar()
        for chave in ("grupos-antes", "recursos-depois", "papeis-depois"):
            codigo, saida = self.conferir(caminhos, sem=(chave,))
            self.assertEqual(codigo, CODIGO_USO)
            self.assertIn(f"--{chave}", saida)
        codigo, saida = self.conferir(caminhos, sem=("inventario",))
        self.assertEqual(codigo, CODIGO_USO)

    def test_mensagens_e_relatorio_de_conferencia_nunca_repetem_valores_do_inventario(self):
        sentinela = f"sentinela-{uuid.uuid4().hex}"
        dados = self.c.inventario()
        dados["identidades_entra"][0]["nome"] = sentinela
        dados["expurgos"][0]["nome"] = sentinela
        dados["recursos_proprios"][0]["id"] = dados["recursos_proprios"][0]["id"].replace("/chat", f"/{sentinela}")
        base = (self.c.grupos_base(), self.c.recursos_base(), self.c.papeis_base())
        divergente = (base[0] + [self.c.grupo_az(self.c.grupo), self.c.grupo_az(self.c.gerenciado)], base[1][1:],
                      base[2][1:] + [self.c.papel_az(identificador=self.c.atribuicao1)])
        divergente[1].append({"id": dados["recursos_proprios"][0]["id"], "type": "Microsoft.App/containerApps"})
        presenca = {item.chave: "presente" for item in enc.itens_de_presenca(enc.inventario_de_dados(dados))}
        caminhos = self.montar(inventario=dados, base=base, depois=divergente, presenca=presenca)
        relatorio = self.pasta / "r.json"
        codigo, saida = self.conferir(caminhos, "--relatorio", str(relatorio))
        self.assertEqual(codigo, CODIGO_DIVERGENCIA)
        texto = saida + relatorio.read_text(encoding="utf-8")
        segredos = [sentinela, self.c.assinatura, self.c.tenant, self.c.grupo, self.c.gerenciado, self.c.objeto1, self.c.app1, self.c.sp1, self.c.mi1,
                    self.c.mi2, self.c.chave1, self.c.atribuicao1, self.c.nome_app1, self.c.busca, str(self.pasta)]
        segredos += [r["id"] for r in dados["recursos_proprios"]] + [r["id"] for r in base[1]] + [g["id"] for g in base[0]] + [p["id"] for p in base[2]]
        for valor in segredos:
            self.assertNotIn(valor, texto)
        for chave in presenca:
            self.assertNotIn(chave, texto, "os identificadores lógicos de presença também ficam fora das mensagens")
        # só aparecem rótulos curtos: tipo e os 8 primeiros caracteres
        self.assertIn("Exemplos (8 primeiros caracteres)", saida)

    def test_grupos_com_letras_maiusculas_sao_comparados_sem_diferenciar_caixa(self):
        """O Azure devolve os nomes em outra caixa: com o grupo do inventário em maiúsculas, nada pode escapar da comparação."""
        def casos(c: Cenario) -> dict:
            return {
                "grupo_proprio_ausente": lambda g, r, p: (g + [c.grupo_az(c.grupo.lower())], r, p),
                "grupo_gerenciado_ausente": lambda g, r, p: (g + [c.grupo_az(c.gerenciado.lower())], r, p),
                "recursos_proprios_ausentes": lambda g, r, p: (g, r + [{"id": c.recurso("Microsoft.Storage/storageAccounts", "restou").lower(),
                                                                       "type": "Microsoft.Storage/storageAccounts"}], p),
                "atribuicoes_proprias_ausentes": lambda g, r, p: (g, r, p + [c.papel_az(escopo=c.prefixo.lower(), principal=novo_guid())]),
            }
        c = self.reiniciar(maiusculas=True)
        self.assertNotEqual(c.grupo, c.grupo.lower())
        self.assertNotEqual(c.gerenciado, c.gerenciado.lower())
        codigo, saida = self.conferir(self.montar())
        self.assertEqual(codigo, CODIGO_OK, saida)
        for esperado in casos(c):
            with self.subTest(esperado):
                c = self.reiniciar(maiusculas=True)
                base = (c.grupos_base(), c.recursos_base(), c.papeis_base())
                depois = casos(c)[esperado](*(copy.deepcopy(x) for x in base))
                codigo, saida = self.conferir(self.montar(base=base, depois=depois))
                self.assertEqual((codigo, self.estado(saida, esperado)), (CODIGO_DIVERGENCIA, "reprovado"), saida)
        for nome, extra in (("grupo", lambda c: c.grupo_az(c.grupo.lower())), ("gerenciado", lambda c: c.grupo_az(c.gerenciado.lower()))):
            with self.subTest(f"{nome} na linha de base"):
                c = self.reiniciar(maiusculas=True)
                base = (c.grupos_base() + [extra(c)], c.recursos_base(), c.papeis_base())
                codigo, saida = self.conferir(self.montar(base=base, depois=(c.grupos_base(), c.recursos_base(), c.papeis_base())))
                self.assertEqual(codigo, CODIGO_USO, saida)
                self.assertIn("já existia", saida)

    def test_relatorio_de_conferencia_tem_so_vocabulario_fechado_e_numeros(self):
        relatorio = self.pasta / "r.json"
        codigo, _ = self.conferir(self.montar(), "--relatorio", str(relatorio))
        self.assertEqual(codigo, CODIGO_OK)
        dados = json.loads(relatorio.read_text(encoding="utf-8"))
        self.assertEqual(set(dados), {"versao_relatorio", "tipo", "resultado", "contagem", "verificacoes", "linha_de_base", "inventario", "avisos",
                                      "entradas_sha256", "limite"})
        self.assertIn(dados["resultado"], ("aprovado", "reprovado", "pendente"))
        for verificacao in dados["verificacoes"]:
            self.assertEqual(set(verificacao), {"id", "estado", "conferidos", "divergentes", "pendentes"})
            self.assertIn(verificacao["estado"], enc.ESTADOS_DE_CRITERIO)
            self.assertTrue(all(isinstance(verificacao[k], int) for k in ("conferidos", "divergentes", "pendentes")))
        self.assertTrue(all(isinstance(v, int) for v in dados["linha_de_base"].values()))
        self.assertTrue(all(isinstance(v, int) for v in dados["inventario"].values()))
        self.assertTrue(all(len(h) == 64 for h in dados["entradas_sha256"].values()))


class RelatorioNovoTests(ComPasta):
    def test_o_relatorio_nunca_sobrescreve_e_e_validado_antes_de_qualquer_trabalho(self):
        caminhos = self.montar()
        relatorio = self.pasta / "existente.json"
        relatorio.write_text("conteudo anterior", encoding="utf-8")
        codigo, saida = executar(*self.argumentos(caminhos, "--relatorio", str(relatorio)))
        self.assertEqual(codigo, CODIGO_USO)
        self.assertIn("não é sobrescrito", saida)
        self.assertEqual(relatorio.read_text(encoding="utf-8"), "conteudo anterior")
        for ruim in (self.pasta / "sem-pasta" / "x.json", self.pasta / "nome ruim.json", self.pasta / "sem-extensao", self.pasta / ".json"):
            self.assertEqual(executar(*self.argumentos(caminhos, "--relatorio", str(ruim)))[0], CODIGO_USO, str(ruim.name))
        nao_foi_criado = executar("--etapa", "plano", "--inventario", str(caminhos["inventario"]), "--relatorio", str(self.pasta / "ok.json"))
        self.assertEqual(nao_foi_criado[0], CODIGO_OK)
        self.assertTrue((self.pasta / "ok.json").is_file())
        self.assertEqual(executar("--etapa", "plano", "--inventario", str(caminhos["inventario"]), "--relatorio", str(self.pasta / "ok.json"))[0], CODIGO_USO)

    def test_a_gravacao_usa_criacao_exclusiva_e_modo_restrito(self):
        caminho = self.pasta / "novo.json"
        enc.gravar_relatorio(caminho, {"a": 1})
        with self.assertRaises(ErroLab):
            enc.gravar_relatorio(caminho, {"a": 2})
        self.assertEqual(json.loads(caminho.read_text(encoding="utf-8")), {"a": 1})
        if os.name == "posix":
            self.assertEqual(caminho.stat().st_mode & 0o777, 0o600)
        with mock.patch.object(os, "open", wraps=os.open) as aberto:
            enc.gravar_relatorio(self.pasta / "outro.json", {})
        sinalizadores, modo = aberto.call_args.args[1], aberto.call_args.args[2]
        self.assertTrue(sinalizadores & os.O_EXCL and sinalizadores & os.O_CREAT)
        self.assertEqual(modo, 0o600)

    def test_plano_sem_relatorio_nao_cria_arquivos(self):
        caminhos = self.montar()
        antes = set(self.arquivos())
        self.assertEqual(executar("--etapa", "plano", "--inventario", str(caminhos["inventario"]))[0], CODIGO_OK)
        self.assertEqual(set(self.arquivos()), antes)
        executar("--etapa", "capturar", "--momento", "antes", "--assinatura", self.c.assinatura, "--grupo", self.c.grupo, "--pasta", str(self.pasta / "novo"))
        self.assertEqual(set(self.arquivos()), antes, "capturar só imprime: nem a pasta é criada")


# ----------------------------------------------------------------------------------------------------------------------
# Linha de comando
# ----------------------------------------------------------------------------------------------------------------------

class CliTests(ComPasta):
    def test_ajuda_completa_com_exemplos_em_powershell(self):
        codigo, saida = executar("--help")
        self.assertEqual(codigo, 0)
        for esperado in ("modelo", "capturar", "plano", "conferir", "--momento", "--pasta", "--presenca", "--relatorio", "--grupos-antes", "--papeis-depois",
                         "Códigos de saída", ".\\.venv\\Scripts\\python.exe scripts\\planejar_encerramento.py", "PowerShell 7", "curinga",
                         "SOMENTE LEITURA", "nunca chama o Azure"):
            self.assertIn(esperado, saida)

    def test_ajuda_e_modelo_explicam_que_os_principais_sao_ids_de_objeto_e_nunca_o_clientid(self):
        codigo, saida = executar("--help")
        self.assertEqual(codigo, 0)
        normalizado = " ".join(saida.split())
        for esperado in ("principais_proprios e principal_id são IDs de OBJETO (principalId), nunca o clientId", "um GUID só pode ter UM papel",
                         "se recusa a rodar, sem executar nada, fora do PowerShell 7"):
            self.assertIn(esperado, normalizado)
        codigo, _, erro = executar_separado("--etapa", "modelo")
        self.assertEqual(codigo, CODIGO_OK)
        orientacao = " ".join(erro.split())
        for esperado in ("são IDs de OBJETO", "NUNCA o clientId nem o appId", "az identity show --ids <ID da identidade>",
                         "principal_id é o `id`, não o appId"):
            self.assertIn(esperado, orientacao)

    def test_uso_incorreto_retorna_codigo_1(self):
        c = self.c
        casos = [[], ["--etapa", "apagar"], ["--etapa", "capturar"], ["--etapa", "capturar", "--momento", "antes", "--assinatura", "x", "--grupo", c.grupo, "--pasta", "p"],
                 ["--etapa", "capturar", "--momento", "antes", "--assinatura", c.assinatura, "--grupo", "grupo ruim", "--pasta", "p"],
                 ["--etapa", "capturar", "--momento", "durante", "--assinatura", c.assinatura, "--grupo", c.grupo, "--pasta", "p"],
                 ["--etapa", "plano"], ["--etapa", "plano", "--inventario", str(self.pasta / "nao-existe.json")], ["--etapa", "conferir"]]
        for argumentos in casos:
            with self.subTest(argumentos=argumentos):
                self.assertEqual(executar(*argumentos)[0], CODIGO_USO)
        codigo, saida = executar("--etapa", "capturar", "--momento", "antes", "--assinatura", "segredo-digitado", "--grupo", c.grupo, "--pasta", "p")
        self.assertNotIn("segredo-digitado", saida, "um GUID inválido não é repetido na mensagem")

    def test_modelo_imprime_json_no_stdout_e_orientacao_no_stderr(self):
        codigo, saida, erro = executar_separado("--etapa", "modelo")
        self.assertEqual(codigo, CODIGO_OK)
        self.assertEqual(set(json.loads(saida)), set(enc.CAMPOS_DO_INVENTARIO))
        self.assertIn("NÃO é válido de propósito", erro)
        self.assertIn("az resource list", erro)
        caminho = self.escrever("modelo.json", saida)
        codigo, texto = executar("--etapa", "plano", "--inventario", str(caminho))
        self.assertEqual(codigo, CODIGO_USO, "o modelo é recusado até ser preenchido")

    def test_linha_de_base_parcial_e_recusada_e_a_ausente_gera_previa(self):
        caminhos = self.montar()
        codigo, saida = executar("--etapa", "plano", "--inventario", str(caminhos["inventario"]), "--grupos-antes", str(caminhos["grupos-antes"]))
        self.assertEqual(codigo, CODIGO_USO)
        self.assertIn("TRÊS arquivos", saida)
        codigo, saida, erro = executar_separado("--etapa", "plano", "--inventario", str(caminhos["inventario"]))
        self.assertEqual(codigo, CODIGO_OK)
        self.assertIn("PRÉVIA", saida)
        self.assertIn("[AVISO]", erro)

    def test_plano_recusa_inventario_que_toca_a_linha_de_base(self):
        base = (self.c.grupos_base() + [self.c.grupo_az(self.c.grupo)], self.c.recursos_base(), self.c.papeis_base())
        caminhos = self.montar(base=base)
        codigo, saida = executar("--etapa", "plano", "--inventario", str(caminhos["inventario"]), "--grupos-antes", str(caminhos["grupos-antes"]),
                                 "--recursos-antes", str(caminhos["recursos-antes"]), "--papeis-antes", str(caminhos["papeis-antes"]))
        self.assertEqual(codigo, CODIGO_USO)
        self.assertNotIn("FASE 1", saida, "nenhum comando é impresso quando uma guarda recusa")
        self.assertNotIn(" delete ", saida)

    def test_plano_em_json_e_stdout_puro(self):
        caminhos = self.montar()
        codigo, saida, erro = executar_separado("--etapa", "plano", "--inventario", str(caminhos["inventario"]), "--grupos-antes", str(caminhos["grupos-antes"]),
                                               "--recursos-antes", str(caminhos["recursos-antes"]), "--papeis-antes", str(caminhos["papeis-antes"]),
                                               "--formato", "json", "--relatorio", str(self.pasta / "r.json"))
        self.assertEqual(codigo, CODIGO_OK, erro)
        self.assertEqual(json.loads(saida)["linha_de_base"], "conferida")
        self.assertIn("gravado", erro)

    def test_erro_inesperado_nao_vaza_o_texto_tecnico(self):
        caminhos = self.montar()
        sentinela = f"sentinela-{uuid.uuid4().hex}"
        with mock.patch.object(enc, "montar_plano", side_effect=RuntimeError(sentinela)):
            codigo, saida = executar("--etapa", "plano", "--inventario", str(caminhos["inventario"]))
        self.assertEqual(codigo, 4)
        self.assertNotIn(sentinela, saida)
        self.assertIn("RuntimeError", saida)


# ----------------------------------------------------------------------------------------------------------------------
# Nada de rede, de az nem de subprocessos
# ----------------------------------------------------------------------------------------------------------------------

class SemRedeTests(ComPasta):
    def test_todas_as_etapas_rodam_sem_rede_sem_az_e_sem_subprocessos(self):
        c = self.c
        caminhos = self.montar()
        argumentos_da_linha_de_base = ["--grupos-antes", str(caminhos["grupos-antes"]), "--recursos-antes", str(caminhos["recursos-antes"]),
                                       "--papeis-antes", str(caminhos["papeis-antes"])]
        execucoes = [
            (["--etapa", "modelo"], CODIGO_OK),
            (["--etapa", "capturar", "--momento", "antes", "--assinatura", c.assinatura, "--grupo", c.grupo, "--pasta", str(self.pasta)], CODIGO_OK),
            (["--etapa", "capturar", "--momento", "depois", "--assinatura", c.assinatura, "--grupo", c.grupo, "--pasta", str(self.pasta),
              "--inventario", str(caminhos["inventario"])], CODIGO_OK),
            (["--etapa", "plano", "--inventario", str(caminhos["inventario"])], CODIGO_OK),
            (["--etapa", "plano", "--inventario", str(caminhos["inventario"]), "--formato", "json", *argumentos_da_linha_de_base,
              "--relatorio", str(self.pasta / "plano.json")], CODIGO_OK),
            (self.argumentos(caminhos, "--relatorio", str(self.pasta / "aprovado.json")), CODIGO_OK),
        ]
        with sem_rede_e_sem_programas():
            for argumentos, esperado in execucoes:
                with self.subTest(etapa=argumentos[1]):
                    codigo, saida = executar(*argumentos)
                    self.assertEqual(codigo, esperado, saida)
            # o estado final reprovado reaproveita os nomes dos arquivos: só é gravado depois da conferência aprovada
            reprovado = self.montar(depois=(c.grupos_base() + [c.grupo_az(c.grupo)], c.recursos_base(), c.papeis_base()))
            codigo, saida = executar(*self.argumentos(reprovado))
            self.assertEqual(codigo, CODIGO_DIVERGENCIA, saida)

    def test_os_modulos_nao_importam_nem_chamam_nada_de_rede_ou_de_programas(self):
        permitidos = {"__future__", "argparse", "hashlib", "json", "os", "re", "sys", "collections", "dataclasses", "pathlib", "typing", "lab_comum",
                      "lab_encerramento"}
        proibidas_em_os = {"system", "popen", "startfile", "spawnl", "spawnv", "execv", "execl", "fork", "posix_spawn"}
        for nome in ("lab_encerramento.py", "planejar_encerramento.py"):
            arvore = ast.parse((RAIZ / "scripts" / nome).read_text(encoding="utf-8"))
            for no in ast.walk(arvore):
                if isinstance(no, ast.Import):
                    importados = {alias.name.split(".")[0] for alias in no.names}
                elif isinstance(no, ast.ImportFrom):
                    importados = {(no.module or "").split(".")[0]}
                else:
                    importados = set()
                self.assertLessEqual(importados, permitidos, f"{nome}: import não previsto (rede, az ou subprocessos?)")
                if isinstance(no, ast.Call) and isinstance(no.func, ast.Name):
                    self.assertNotIn(no.func.id, {"eval", "exec", "compile", "__import__"}, nome)
                if isinstance(no, ast.Attribute) and isinstance(no.value, ast.Name) and no.value.id == "os":
                    self.assertNotIn(no.attr, proibidas_em_os, nome)


def analisar_sintaxe(executavel: str, blocos: list[str]) -> str:
    """Pede ao analisador do próprio PowerShell que leia cada bloco (sem executá-lo). Devolve as mensagens e, na última linha, 'falhas=N'."""
    script = ("$blocos = [Console]::In.ReadToEnd() | ConvertFrom-Json; $falhas = 0\n"
              "foreach ($b in $blocos) { $e = $null; [void][System.Management.Automation.Language.Parser]::ParseInput($b, [ref]$null, [ref]$e); "
              "if ($e) { $falhas++; $e | ForEach-Object { 'ERRO: ' + $_.Message } } }\n"
              "'falhas=' + $falhas")
    # json.dumps escapa o que não é ASCII: o texto entra no PowerShell sem depender da página de código do console
    resultado = subprocess.run([executavel, "-NoProfile", "-NonInteractive", "-Command", script], input=json.dumps(blocos), capture_output=True,
                               text=True, encoding="utf-8", timeout=180)
    return resultado.stdout + resultado.stderr


@unittest.skipUnless(shutil.which("pwsh"), "pwsh não encontrado: a sintaxe PowerShell dos blocos não foi conferida")
class SintaxeDoPowerShellTests(ComPasta):
    def test_todos_os_blocos_impressos_sao_powershell_valido(self):
        inv = self.c.carregado()
        plano = enc.montar_plano(inv, True)
        blocos = [plano.preparacao]
        for passo in plano.passos:
            blocos += [passo.comando, passo.verificacao]
        blocos += [i.comando for i in plano.fechamento if i.comando and not i.comando.startswith(".")]
        blocos.append(enc.comandos_de_captura(self.c.assinatura, self.c.grupo, "antes", r"C:\Users\João Silva\encerramento"))
        blocos.append(enc.comandos_de_captura(self.c.assinatura, self.c.grupo, "depois", "./encerramento", inv))
        saida = analisar_sintaxe(shutil.which("pwsh"), blocos)
        self.assertEqual(saida.strip().splitlines()[-1], "falhas=0", saida)


FALSO_AZ_E_WEB = r"""
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$global:Chamadas = New-Object System.Collections.ArrayList
$global:Regras = @()
function Set-Regras([string]$json) {
    $global:Regras = @()
    foreach ($regra in @(ConvertFrom-Json -InputObject $json)) { $global:Regras += $regra }
}
function Invoke-Colado([string]$texto) {
    $acumulado = $null
    foreach ($linha in ($texto -split "\r?\n")) {
        $acumulado = if ($null -eq $acumulado) { $linha } else { $acumulado + "`n" + $linha }
        $erros = $null
        [void][System.Management.Automation.Language.Parser]::ParseInput($acumulado, [ref]$null, [ref]$erros)
        if (@($erros | Where-Object { $_.IncompleteInput }).Count -gt 0) { continue }
        try { Invoke-Expression $acumulado } catch { 'ERRO: ' + $_.Exception.Message }
        $acumulado = $null
    }
}
function az {
    $linha = ($args | ForEach-Object { "$_" }) -join ' '
    [void]$global:Chamadas.Add($linha)
    $global:LASTEXITCODE = 0
    foreach ($regra in $global:Regras) {
        if ($linha -match $regra.padrao) {
            $global:LASTEXITCODE = [int]$regra.codigo
            if ($regra.saida) { $regra.saida -split "`n" }
            return
        }
    }
    [void]$global:Chamadas.Add('INESPERADO: ' + $linha)
    $global:LASTEXITCODE = 99
}
function Invoke-WebRequest {
    param([string]$Method, [string]$Uri, $Headers, [switch]$SkipHttpErrorCheck, $MaximumRedirection, $TimeoutSec)
    [void]$global:Chamadas.Add('GET ' + $Uri + ' auth=' + [bool]$Headers.Authorization + ' sem-erro-http=' + $SkipHttpErrorCheck.IsPresent + ' redirecoes=' + $MaximumRedirection)
    switch ($Uri.Split('/')[-1].Substring(0, 1)) {
        'a' { return [pscustomobject]@{ StatusCode = 404 } }
        'b' { return [pscustomobject]@{ StatusCode = 200 } }
        'c' { return [pscustomobject]@{ StatusCode = 403 } }
        'd' { throw 'falha de rede' }
        default { return [pscustomobject]@{ StatusCode = 500 } }
    }
}
"""


def guid_com_inicial(inicial: str) -> str:
    """GUID aleatório cujo primeiro caractere é `inicial`: o Invoke-WebRequest falso escolhe o status pela inicial do último segmento."""
    return inicial + novo_guid()[1:]


class HarnessDoPowerShell(ComPasta):
    """Roda blocos PowerShell com um `az` e um `Invoke-WebRequest` FALSOS: nada de Azure, de rede nem de `az` real."""

    def rodar(self, casos: list[tuple[str, str, list[dict]]], windows_powershell: bool = False,
              colando: bool = False, direto: bool = False) -> dict[str, tuple[list[str], list[str]]]:
        """Cada caso é (nome, bloco, regras do az falso). Devolve {nome: (linhas impressas, chamadas registradas)}.

        Cada caso começa sem a marca da PREPARAÇÃO e sem chamadas registradas; `windows_powershell` troca o pwsh pelo powershell.exe (5.1).
        Por padrão o bloco roda dentro de um `try`: o primeiro erro o interrompe. Com `colando`, o bloco é entregue como numa colagem no
        console: linha a linha, executando cada comando assim que ele está completo (um `throw` de nível superior mostra o erro e as linhas
        seguintes continuam). Com `direto`, o bloco fica no nível superior do script, sem `try`: um erro que termina só o comando (como um
        JSON inválido em `ConvertFrom-Json`) deixa o comando seguinte executar, como no console.
        """
        partes = [FALSO_AZ_E_WEB]
        for nome, bloco, regras in casos:
            regras_json = json.dumps(regras, ensure_ascii=False).replace("'", "''")
            if colando:
                execucao = f"Invoke-Colado '{bloco.replace(chr(39), chr(39) * 2)}'"
            elif direto:
                execucao = bloco
            else:
                execucao = f"try {{ & {{\n{bloco}\n}} }} catch {{ 'EXCECAO: ' + $_.Exception.Message }}"
            partes.append(f"'@@CASO {nome}'\n$script:EncerramentoPronto = $null\n$global:Chamadas = New-Object System.Collections.ArrayList\n"
                          f"Set-Regras '{regras_json}'\n{execucao}\n"
                          "'@@CHAMADAS'\n$global:Chamadas | ForEach-Object { $_ }")
        script = self.pasta / "casos.ps1"
        script.write_bytes(b"\xef\xbb\xbf" + "\n".join(partes).encode("utf-8"))  # com BOM: o 5.1 só lê UTF-8 assim
        comando = ([powershell_5(), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(script)] if windows_powershell
                   else [shutil.which("pwsh"), "-NoProfile", "-NonInteractive", "-File", str(script)])
        resultado = subprocess.run(comando, capture_output=True, text=True, encoding="utf-8-sig", timeout=240)
        self.assertEqual(resultado.returncode, 0, resultado.stdout + resultado.stderr)
        saidas: dict[str, tuple[list[str], list[str]]] = {}
        atual, modo = None, "saida"
        for linha in resultado.stdout.splitlines():
            if linha.startswith("@@CASO "):
                atual, modo = linha[len("@@CASO "):], "saida"
                saidas[atual] = ([], [])
            elif linha == "@@CHAMADAS":
                modo = "chamadas"
            elif atual is not None and linha.strip():
                saidas[atual][0 if modo == "saida" else 1].append(linha)
        return saidas

    @staticmethod
    def regra(padrao: str, saida=None, codigo: int = 0) -> dict:
        return {"padrao": padrao, "codigo": codigo, "saida": saida if isinstance(saida, str) or saida is None else json.dumps(saida)}

    def com_preparacao(self, plano: enc.Plano, c: Cenario | None = None) -> tuple[str, list[dict]]:
        """A PREPARAÇÃO real do plano, as respostas do `az` falso para ela passar e um zerar das chamadas: o bloco seguinte começa limpo."""
        c = c or self.c
        regras = [self.regra("account show", {"id": c.assinatura, "tenantId": c.tenant}), self.regra("get-access-token", "token-falso")]
        return plano.preparacao + "\n$global:Chamadas.Clear()\n", regras

    def casos_das_guardas(self, comando_de, c: Cenario | None = None) -> tuple[list[tuple[str, str, list[dict]]], set[str]]:
        """Os casos das guardas de exclusão, os mesmos para os dois PowerShell. `comando_de(tipo)` devolve o bloco do primeiro passo daquele
        tipo. Devolve (casos, nomes dos casos em que o bloco DEVE apagar)."""
        c = c or self.c
        inv = c.inventario()
        regra = self.regra
        papel_ok = {"id": c.atribuicao1, "principalId": c.mi1, "scope": c.prefixo,
                    "roleDefinitionId": f"/subscriptions/{c.assinatura}/providers/Microsoft.Authorization/roleDefinitions/{c.papel1}"}
        outra = dict(papel_ok, id=c.atribuicao2)  # outra atribuição que coincide em principal, escopo e papel, mas não é a alvo
        sp, app, item = {"id": c.sp1, "appId": c.app1}, {"id": c.objeto1, "appId": c.app1, "nome": c.nome_app1}, {"id": c.objeto1, "appId": c.app1}
        cofre = c.prefixo + "/providers/Microsoft.KeyVault/vaults/kvlab"
        todos_os_recursos = "\n".join(r["id"].lower() for r in inv["recursos_proprios"])
        deve_apagar = {"sp|confere", "app|confere", "expurgo|confere", "papel|confere", "grupo|so-inventario", "grupo|vazio", "cofre|do-grupo"}
        casos = [
            ("sp|confere", "principal_servico_entra", [regra("ad sp show", sp), regra("ad sp delete")]),
            ("sp|outro-app", "principal_servico_entra", [regra("ad sp show", dict(sp, appId=novo_guid())), regra("ad sp delete")]),
            ("sp|id-diferente", "principal_servico_entra", [regra("ad sp show", dict(sp, id=novo_guid())), regra("ad sp delete")]),
            ("sp|inexistente", "principal_servico_entra", [regra("ad sp show", "", 1), regra("ad sp delete")]),
            ("sp|az-falhou-com-saida", "principal_servico_entra", [regra("ad sp show", sp, 1), regra("ad sp delete")]),
            ("app|confere", "aplicativo_entra", [regra("ad app show", app), regra("ad app delete")]),
            ("app|nome-diferente", "aplicativo_entra", [regra("ad app show", dict(app, nome="outro")), regra("ad app delete")]),
            ("app|app-diferente", "aplicativo_entra", [regra("ad app show", dict(app, appId=novo_guid())), regra("ad app delete")]),
            ("app|id-diferente", "aplicativo_entra", [regra("ad app show", dict(app, id=novo_guid())), regra("ad app delete")]),
            ("app|az-falhou-com-saida", "aplicativo_entra", [regra("ad app show", app, 1), regra("ad app delete")]),
            ("expurgo|confere", "expurgo_aplicativo", [regra("rest --method get", item), regra("rest --method delete")]),
            ("expurgo|outro-id", "expurgo_aplicativo", [regra("rest --method get", dict(item, id=novo_guid())), regra("rest --method delete")]),
            ("expurgo|outro-app", "expurgo_aplicativo", [regra("rest --method get", dict(item, appId=novo_guid())), regra("rest --method delete")]),
            ("expurgo|ja-expurgado", "expurgo_aplicativo", [regra("rest --method get", "", 1), regra("rest --method delete")]),
            ("expurgo|az-falhou-com-saida", "expurgo_aplicativo", [regra("rest --method get", item, 1), regra("rest --method delete")]),
            ("papel|confere", "atribuicao_papel", [regra("role assignment list", [papel_ok, outra]), regra("role assignment delete")]),
            ("papel|principal", "atribuicao_papel", [regra("role assignment list", [dict(papel_ok, principalId=novo_guid())]), regra("role assignment delete")]),
            ("papel|escopo", "atribuicao_papel", [regra("role assignment list", [dict(papel_ok, scope=f"/subscriptions/{c.assinatura}")]), regra("role assignment delete")]),
            ("papel|papel", "atribuicao_papel", [regra("role assignment list", [dict(papel_ok, roleDefinitionId="/x/" + novo_guid())]), regra("role assignment delete")]),
            ("papel|ausente", "atribuicao_papel", [regra("role assignment list", [outra]), regra("role assignment delete")]),
            # outra atribuição da MESMA listagem coincide com o inventário: no 5.1, ConvertFrom-Json | Where-Object entrega a lista inteira
            ("papel|principal-errado-com-outra-coincidente", "atribuicao_papel",
             [regra("role assignment list", [dict(papel_ok, principalId=novo_guid()), outra]), regra("role assignment delete")]),
            ("papel|escopo-errado-com-outra-coincidente", "atribuicao_papel",
             [regra("role assignment list", [dict(papel_ok, scope=f"/subscriptions/{c.assinatura}"), outra]), regra("role assignment delete")]),
            ("papel|papel-errado-com-outra-coincidente", "atribuicao_papel",
             [regra("role assignment list", [dict(papel_ok, roleDefinitionId="/x/" + novo_guid()), outra]), regra("role assignment delete")]),
            ("papel|id-duplicado", "atribuicao_papel",
             [regra("role assignment list", [papel_ok, dict(papel_ok, principalId=novo_guid())]), regra("role assignment delete")]),
            ("papel|az-falhou-com-saida", "atribuicao_papel", [regra("role assignment list", [papel_ok], 1), regra("role assignment delete")]),
            ("grupo|so-inventario", "grupo_exclusivo", [regra("resource list", todos_os_recursos), regra("group delete")]),
            ("grupo|vazio", "grupo_exclusivo", [regra("resource list", ""), regra("group delete")]),
            ("grupo|intruso", "grupo_exclusivo",
             [regra("resource list", todos_os_recursos + "\n" + c.recurso("Microsoft.Storage/storageAccounts", "intruso")), regra("group delete")]),
            ("grupo|listagem-falhou", "grupo_exclusivo", [regra("resource list", "", 1), regra("group delete")]),
            ("cofre|do-grupo", "expurgo_cofre_de_chaves", [regra("keyvault show-deleted", cofre.replace(c.prefixo, c.prefixo.upper())), regra("keyvault purge")]),
            ("cofre|de-outro-grupo", "expurgo_cofre_de_chaves",
             [regra("keyvault show-deleted", f"/subscriptions/{c.assinatura}/resourceGroups/outro/providers/Microsoft.KeyVault/vaults/kvlab"), regra("keyvault purge")]),
            ("cofre|grupo-com-o-mesmo-prefixo", "expurgo_cofre_de_chaves",
             [regra("keyvault show-deleted", c.prefixo + "-outro/providers/Microsoft.KeyVault/vaults/kvlab"), regra("keyvault purge")]),
            ("cofre|duas-linhas", "expurgo_cofre_de_chaves", [regra("keyvault show-deleted", cofre + "\n" + cofre + "-2"), regra("keyvault purge")]),
            ("cofre|az-falhou-com-saida", "expurgo_cofre_de_chaves", [regra("keyvault show-deleted", cofre, 1), regra("keyvault purge")]),
            ("cofre|inexistente", "expurgo_cofre_de_chaves", [regra("keyvault show-deleted", "", 1), regra("keyvault purge")]),
        ]
        return [(nome, comando_de(tipo), regras) for nome, tipo, regras in casos], deve_apagar

    def conferir_guardas(self, saidas: dict[str, tuple[list[str], list[str]]], deve_apagar: set[str], c: Cenario | None = None) -> None:
        c = c or self.c
        for nome, (linhas, chamadas) in saidas.items():
            self.assertFalse(any("INESPERADO" in x for x in chamadas), f"{nome}: {chamadas}")
            apagou = any(re.search(r"\b(delete|purge)\b", x) for x in chamadas)
            self.assertEqual(apagou, nome in deve_apagar, f"{nome}: {linhas} {chamadas}")
            if nome not in deve_apagar:
                explicacao = junto(linhas)
                self.assertTrue("nada foi" in explicacao or "fora do inventário" in explicacao,
                                f"{nome} precisa explicar por que nada foi apagado: {linhas}")
        # o que é apagado é exatamente o alvo do inventário, e nada mais
        self.assertEqual([x for x in saidas["papel|confere"][1] if "role assignment delete" in x], [f"role assignment delete --ids {c.atribuicao1}"])
        self.assertEqual([x for x in saidas["grupo|vazio"][1] if "group delete" in x], [f"group delete --name {c.grupo} --subscription {c.assinatura} --yes"])
        self.assertEqual([x for x in saidas["sp|confere"][1] if "ad sp delete" in x], [f"ad sp delete --id {c.sp1}"])
        self.assertEqual([x for x in saidas["app|confere"][1] if "ad app delete" in x], [f"ad app delete --id {c.objeto1}"])


@unittest.skipUnless(shutil.which("pwsh"), "pwsh não encontrado: o comportamento dos blocos PowerShell não foi conferido")
class ComportamentoDoPowerShellTests(HarnessDoPowerShell):
    """Roda os blocos impressos no PowerShell 7 com um `az` e um `Invoke-WebRequest` FALSOS: nada de Azure, de rede nem de `az` real."""

    def inventario_com_principais_ausentes_no_graph(self) -> dict:
        """O inventário do cenário com os GUIDs consultados no Graph trocados por outros que começam com 'a' (o Graph falso responde 404)."""
        texto = json.dumps(self.c.inventario())
        for antigo in (self.c.mi1, self.c.mi2, self.c.sp1, self.c.objeto1, self.c.objeto2):
            texto = texto.replace(antigo, "a" + antigo[1:])
        return json.loads(texto)

    def test_consulta_ao_graph_mapeia_404_200_e_qualquer_outro_resultado_sem_expor_o_token(self):
        c = self.c
        plano = enc.montar_plano(c.carregado(), True)
        token = f"token-sentinela-{uuid.uuid4().hex}"
        conta = self.regra("account show", {"id": c.assinatura, "tenantId": c.tenant})
        esperado = {"a": "ausente", "b": "presente", "c": "indeterminado", "d": "indeterminado", "e": "indeterminado"}
        chamadas_do_graph = "\n".join(f"'{i}=' + (Get-EstadoGraph 'applications/{guid_com_inicial(i)}')" for i in esperado)
        saidas = self.rodar([
            ("estados", plano.preparacao + "\n" + chamadas_do_graph, [conta, self.regra("get-access-token", token)]),
            ("token-falhou", plano.preparacao + "\n'DEPOIS DO TOKEN'", [conta, self.regra("get-access-token", "", 1)]),
            ("conta-diferente", plano.preparacao + "\n'DEPOIS DA CONTA'", [self.regra("account show", {"id": novo_guid(), "tenantId": c.tenant}),
                                                                         self.regra("get-access-token", token)]),
            ("tenant-diferente", plano.preparacao + "\n'DEPOIS DO TENANT'", [self.regra("account show", {"id": c.assinatura, "tenantId": novo_guid()}),
                                                                           self.regra("get-access-token", token)]),
        ])
        linhas, chamadas = saidas["estados"]
        self.assertEqual({linha.split("=")[0]: linha.split("=")[1] for linha in linhas if "=" in linha}, esperado, linhas)
        self.assertFalse(any("INESPERADO" in x for x in chamadas), chamadas)
        self.assertIn(f"account get-access-token --resource-type ms-graph --tenant {c.tenant} --query accessToken --output tsv", chamadas)
        consultas = [x for x in chamadas if x.startswith("GET ")]
        self.assertEqual(len(consultas), 5)
        for consulta in consultas:
            self.assertTrue(consulta.startswith("GET https://graph.microsoft.com/v1.0/applications/"), consulta)
            self.assertTrue(consulta.endswith("auth=True sem-erro-http=True redirecoes=0"), consulta)
        self.assertNotIn(token, "\n".join(linhas + chamadas), "o token nunca é impresso")
        for caso, depois in (("token-falhou", "DEPOIS DO TOKEN"), ("conta-diferente", "DEPOIS DA CONTA"), ("tenant-diferente", "DEPOIS DO TENANT")):
            linhas, chamadas = saidas[caso]
            self.assertTrue(any(x.startswith("EXCECAO:") for x in linhas), caso)
            self.assertNotIn(depois, linhas, f"{caso}: a preparação interrompe o bloco")
        self.assertFalse(any("get-access-token" in x for x in saidas["conta-diferente"][1]), "conta errada: o token nem é pedido")

    def test_verificacao_por_listagem_nunca_toma_falha_ou_resposta_vazia_por_ausencia_confirmada_sem_explicar(self):
        c = self.c
        plano = enc.montar_plano(c.carregado(), True)
        passos = {}
        for passo in plano.passos:
            passos.setdefault(passo.tipo, passo)
        preparo, regras_do_preparo = self.com_preparacao(plano)
        casos = []
        for tipo, padrao, alvo in (("aplicativo_container_app", "containerapp list", c.recurso("Microsoft.App/containerApps", "chat")),
                                   ("link_privado_busca", "shared-private-link-resource list", c.inventario()["shared_private_links"][0]["id"]),
                                   ("atribuicao_papel", "role assignment list", c.atribuicao1),
                                   ("workspace_logs", "log-analytics workspace list", c.recurso("Microsoft.OperationalInsights/workspaces", "logs")),
                                   ("ambiente_container_apps", "containerapp env list", c.recurso("Microsoft.App/managedEnvironments", "env")),
                                   ("expurgo_conta_de_modelos", "account list-deleted", "ais"), ("expurgo_cofre_de_chaves", "keyvault list-deleted", "kvlab"),
                                   ("credencial_entra", "credential list", c.chave1)):
            bloco = preparo + passos[tipo].verificacao
            outro = c.recurso("Microsoft.App/containerApps", "outro")
            casos += [(f"{tipo}|presente", bloco, regras_do_preparo + [self.regra(padrao, alvo.upper() + "\n" + outro)]),
                      (f"{tipo}|ausente", bloco, regras_do_preparo + [self.regra(padrao, outro)]),
                      (f"{tipo}|vazio", bloco, regras_do_preparo + [self.regra(padrao, "")]),
                      (f"{tipo}|falha", bloco, regras_do_preparo + [self.regra(padrao, "", 1)])]
        grupo = preparo + passos["grupo_exclusivo"].verificacao
        casos += [("grupo|false", grupo, regras_do_preparo + [self.regra("group exists", "false")]),
                  ("grupo|true", grupo, regras_do_preparo + [self.regra("group exists", "true")]),
                  ("grupo|falha", grupo, regras_do_preparo + [self.regra("group exists", "", 1)])]
        saidas = self.rodar(casos)
        for nome, (linhas, chamadas) in saidas.items():
            self.assertFalse(any("INESPERADO" in x for x in chamadas), f"{nome}: {chamadas}")
            resultado = linhas[-1]
            esperado = {"presente": "presente", "ausente": "ausente", "vazio": "ausente", "falha": "indeterminado", "false": "ausente", "true": "presente"}[nome.split("|")[1]]
            self.assertEqual(resultado, esperado, f"{nome}: {linhas}")
            if nome.endswith("|falha"):
                self.assertTrue(any("NÃO prova ausência" in x for x in linhas), f"{nome}: a falha precisa ser explicada")

    def test_guardas_so_apagam_o_que_confere_com_o_inventario(self):
        plano = enc.montar_plano(self.c.carregado(), True)
        passos = {}
        for passo in plano.passos:
            passos.setdefault(passo.tipo, passo)
        preparo, regras_do_preparo = self.com_preparacao(plano)
        casos, deve_apagar = self.casos_das_guardas(lambda tipo: preparo + passos[tipo].comando)
        saidas = self.rodar([(nome, bloco, regras_do_preparo + regras) for nome, bloco, regras in casos])
        self.conferir_guardas(saidas, deve_apagar)

    def test_confusao_entre_id_de_objeto_e_appid_nao_apaga_mesmo_com_o_inventario_forjado(self):
        """O PoC do revisor: o mesmo GUID como objeto_id e app_id. A validação já recusa o inventário; aqui o inventário é forjado para provar
        que o bloco, sozinho, também recusa: `az ad ... --id` resolve pelo appId e devolve um `id` (objeto) diferente do que o inventário diz."""
        c = self.c
        inv = c.carregado()
        confuso, objeto_real, sp_real = novo_guid(), novo_guid(), novo_guid()
        forjado = dataclasses.replace(inv, identidades=(dataclasses.replace(inv.identidades[0], objeto_id=confuso, app_id=confuso),))
        plano = enc.montar_plano(forjado, True)
        passos = {p.tipo: p for p in plano.passos}
        preparo, regras_do_preparo = self.com_preparacao(plano)
        regras = [self.regra("ad app show", {"id": objeto_real, "appId": confuso, "nome": c.nome_app1}), self.regra("ad app delete"),
                  self.regra("ad sp show", {"id": sp_real, "appId": confuso}), self.regra("ad sp delete"),
                  self.regra("rest --method get", "", 1), self.regra("rest --method delete")]
        casos = [(tipo, preparo + passos[tipo].comando, regras_do_preparo + regras)
                 for tipo in ("aplicativo_entra", "principal_servico_entra", "expurgo_aplicativo", "expurgo_principal_servico")]
        for nome, (linhas, chamadas) in self.rodar(casos).items():
            self.assertFalse(any(re.search(r"\bdelete\b", x) for x in chamadas), f"{nome}: {chamadas}")
            self.assertIn("nada foi apagado", junto(linhas), nome)
        with self.assertRaises(ErroLab):  # e o inventário em si é recusado antes de qualquer plano
            dados = c.inventario()
            dados["identidades_entra"][0]["app_id"] = dados["identidades_entra"][0]["objeto_id"]
            enc.inventario_de_dados(dados)

    def test_leitura_que_falha_no_meio_nao_reaproveita_o_valor_de_um_bloco_anterior(self):
        """Um JSON inválido interrompe só aquele comando (as linhas seguintes continuam): a variável ficaria com o valor do bloco anterior."""
        c = self.c
        plano = enc.montar_plano(c.carregado(), True)
        preparo, regras_do_preparo = self.com_preparacao(plano)
        papel_ok = {"id": c.atribuicao1, "principalId": c.mi1, "scope": c.prefixo,
                    "roleDefinitionId": f"/subscriptions/{c.assinatura}/providers/Microsoft.Authorization/roleDefinitions/{c.papel1}"}
        revogacao = next(p.comando for p in plano.passos if p.tipo == "atribuicao_papel")
        principal = next(p.comando for p in plano.passos if p.tipo == "principal_servico_entra")
        validas = [self.regra("role assignment list", [papel_ok]), self.regra("role assignment delete"),
                   self.regra("ad sp show", {"id": c.sp1, "appId": c.app1}), self.regra("ad sp delete")]
        invalidas = [self.regra("role assignment list", "{ruim"), self.regra("role assignment delete"),
                     self.regra("ad sp show", "{ruim"), self.regra("ad sp delete")]
        trocar = "Set-Regras '" + json.dumps(invalidas).replace("'", "''") + "'"
        saidas = self.rodar([("duas-vezes", "\n".join([preparo, revogacao, principal, trocar, revogacao, principal]), regras_do_preparo + validas)],
                            direto=True)
        apagou = [x for x in saidas["duas-vezes"][1] if re.search(r"\bdelete\b", x)]
        self.assertEqual(apagou, [f"role assignment delete --ids {c.atribuicao1}", f"ad sp delete --id {c.sp1}"],
                         "a segunda rodada, com a leitura quebrada, não pode apagar de novo com o valor da primeira")

    def test_nenhum_bloco_executa_nada_antes_da_preparacao_ou_com_a_preparacao_de_outro_inventario(self):
        c, outro = self.c, Cenario()
        plano, plano_do_outro = enc.montar_plano(c.carregado(), True), enc.montar_plano(outro.carregado(), True)
        preparo_do_outro, regras_do_outro = self.com_preparacao(plano_do_outro, outro)
        casos, categorias = [], {}
        for rotulo, bloco, categoria in blocos_de_powershell(c, plano, str(self.pasta)):
            if categoria not in ("comando", "verificacao"):
                continue
            casos += [(f"sem|{rotulo}", bloco, []), (f"outro|{rotulo}", preparo_do_outro + bloco, regras_do_outro)]
            categorias[f"sem|{rotulo}"] = categorias[f"outro|{rotulo}"] = categoria
        self.assertGreater(len(casos), 40)
        for nome, (linhas, chamadas) in self.rodar(casos).items():
            self.assertEqual(chamadas, [], f"{nome}: nenhum az e nenhuma consulta ao Graph")
            self.assertTrue(any("PREPARAÇÃO" in x for x in linhas), f"{nome}: {linhas}")
            if categorias[nome] == "verificacao":
                self.assertEqual(linhas[-1], "indeterminado", f"{nome}: um bloco que decide ausência nunca responde 'ausente' sem a preparação")
            else:
                self.assertFalse(any(x.strip() in ("ausente", "presente", "indeterminado") for x in linhas), nome)

    def test_a_preparacao_que_falha_apaga_a_marca_de_uma_preparacao_anterior(self):
        c = self.c
        plano = enc.montar_plano(c.carregado(), True)
        comando = next(p.comando for p in plano.passos if p.tipo == "aplicativo_container_app")
        marca = f"$script:EncerramentoPronto = '{c.assinatura}/{c.grupo}'"
        conta_certa = self.regra("account show", {"id": c.assinatura, "tenantId": c.tenant})
        conta_errada = self.regra("account show", {"id": novo_guid(), "tenantId": c.tenant})
        regras = [self.regra("get-access-token", "token-falso"), self.regra("containerapp delete")]
        repetir = f"try {{ & {{\n{plano.preparacao}\n}} }} catch {{ 'EXCECAO: ' + $_.Exception.Message }}\n{comando}"
        saidas = self.rodar([
            ("marca-antiga-e-preparacao-falha", f"{marca}\n{repetir}", [conta_errada] + regras),
            ("preparacao-certa", f"{marca}\n{repetir}", [conta_certa] + regras),
        ])
        linhas, chamadas = saidas["marca-antiga-e-preparacao-falha"]
        self.assertTrue(any(x.startswith("EXCECAO:") for x in linhas), linhas)
        self.assertFalse(any("containerapp delete" in x for x in chamadas), "a marca de uma preparação anterior não vale depois de uma preparação que falhou")
        self.assertTrue(any("containerapp delete" in x for x in saidas["preparacao-certa"][1]), "com a preparação concluída, o bloco executa")

    def test_colado_linha_a_linha_sem_a_preparacao_nenhum_bloco_executa_nada(self):
        c = self.c
        plano = enc.montar_plano(c.carregado(), True)
        blocos = [(rotulo, bloco, []) for rotulo, bloco, categoria in blocos_de_powershell(c, plano, str(self.pasta)) if categoria in ("comando", "verificacao")]
        self.assertGreater(len(blocos), 30)
        papel_ok = {"id": c.atribuicao1, "principalId": c.mi1, "scope": c.prefixo,
                    "roleDefinitionId": f"/subscriptions/{c.assinatura}/providers/Microsoft.Authorization/roleDefinitions/{c.papel1}"}
        preparo, regras_do_preparo = self.com_preparacao(plano)
        revogacao = next(p.comando for p in plano.passos if p.tipo == "atribuicao_papel")
        saidas = self.rodar(blocos + [
            ("controle-az", "az ping", [self.regra("ping")]),
            ("com-preparacao", preparo + revogacao, regras_do_preparo + [self.regra("role assignment list", [papel_ok]), self.regra("role assignment delete")]),
        ], colando=True)
        for rotulo, (linhas, chamadas) in saidas.items():
            if rotulo in ("controle-az", "com-preparacao"):
                continue
            self.assertEqual(chamadas, [], f"{rotulo}: colado linha a linha, nada do corpo pode executar sem a preparação")
        self.assertEqual(saidas["controle-az"][1], ["ping"], "o ensaio registra as chamadas ao az")
        self.assertEqual([x for x in saidas["com-preparacao"][1] if "delete" in x], [f"role assignment delete --ids {c.atribuicao1}"],
                         "com a preparação colada antes, na mesma janela, o mesmo bloco executa")

    def test_listagem_de_excluidos_que_falha_vira_indeterminado_e_a_conferencia_fica_pendente(self):
        dados = self.inventario_com_principais_ausentes_no_graph()
        inv, c = enc.inventario_de_dados(dados), self.c
        pasta = self.pasta / "depois"
        grupos, recursos, papeis = c.grupos_base(), c.recursos_base(), c.papeis_base()
        listagens = [self.regra("group list", grupos), self.regra("resource list", recursos), self.regra("role assignment list", papeis)]
        regras = [self.regra("account show", {"id": c.assinatura, "tenantId": c.tenant}), self.regra("get-access-token", "token-falso"),
                  self.regra("account list-deleted", "", 1), self.regra("keyvault list-deleted", "", 1)] + listagens
        self.rodar([("depois", enc.comandos_de_captura(c.assinatura, c.grupo, "depois", str(pasta), inv), regras)])
        presenca = json.loads((pasta / "presenca-depois.json").read_text(encoding="utf-8-sig"))
        for item in enc.itens_de_presenca(inv):
            esperado = "indeterminado" if item.categoria in (enc.EXPURGO_MODELOS, enc.EXPURGO_COFRE) else "ausente"
            self.assertEqual(presenca[item.chave], esperado, f"{item.categoria}: uma listagem que falha nunca vale como ausência")
        argumentos = ["--etapa", "conferir", "--inventario", str(self.escrever("inventario.json", dados)), "--presenca", str(pasta / "presenca-depois.json")]
        for nome, lista in (("grupos", grupos), ("recursos", recursos), ("papeis", papeis)):
            argumentos += [f"--{nome}-antes", str(self.escrever(f"{nome}-antes.json", lista)), f"--{nome}-depois", str(pasta / f"{nome}-depois.json")]
        codigo, saida = executar(*argumentos)
        self.assertEqual(codigo, CODIGO_DIVERGENCIA, saida)
        for criterio in (enc.EXPURGO_MODELOS, enc.EXPURGO_COFRE):
            self.assertIn(f"[PENDENTE] {criterio}:", saida)
        self.assertIn("Encerramento PENDENTE", saida)
        self.assertNotIn("Resultado: APROVADO", saida)

    def test_capturas_gravam_sem_sobrescrever_e_alimentam_a_conferencia_aprovada(self):
        dados = self.inventario_com_principais_ausentes_no_graph()
        inv = enc.inventario_de_dados(dados)
        c = self.c
        pasta_antes, pasta_depois = self.pasta / "antes", self.pasta / "depois"
        antes = enc.comandos_de_captura(c.assinatura, c.grupo, "antes", str(pasta_antes))
        depois = enc.comandos_de_captura(c.assinatura, c.grupo, "depois", str(pasta_depois), inv)
        grupos, recursos, papeis = c.grupos_base(), c.recursos_base(), c.papeis_base()
        listagens = [self.regra("group list", grupos), self.regra("resource list", recursos), self.regra("role assignment list", papeis)]
        regras_antes = [self.regra("group exists", "false")] + listagens
        regras_depois = [self.regra("account show", {"id": c.assinatura, "tenantId": c.tenant}), self.regra("get-access-token", "token-falso"),
                         self.regra("account list-deleted", ""), self.regra("keyvault list-deleted", "")] + listagens
        saidas = self.rodar([
            ("antes", antes, regras_antes),
            ("antes-de-novo", antes, regras_antes),
            ("antes-grupo-existe", antes.replace(str(pasta_antes), str(self.pasta / "outra")), [self.regra("group exists", "true")] + listagens),
            ("antes-leitura-falhou", antes.replace(str(pasta_antes), str(self.pasta / "falha")), [self.regra("group exists", "false"), self.regra("group list", grupos),
                                                                                                    self.regra("resource list", "", 1), self.regra("role assignment list", papeis)]),
            ("depois", depois, regras_depois),
            ("depois-de-novo", depois, regras_depois),
        ])
        self.assertEqual(sorted(p.name for p in pasta_antes.iterdir()), ["grupos-antes.json", "papeis-antes.json", "recursos-antes.json"])
        self.assertEqual(sorted(p.name for p in pasta_depois.iterdir()), ["grupos-depois.json", "papeis-depois.json", "presenca-depois.json", "recursos-depois.json"])
        self.assertTrue(any(x.startswith("EXCECAO:") and "já existe" in x for x in saidas["antes-de-novo"][0]), saidas["antes-de-novo"])
        self.assertTrue(any(x.startswith("EXCECAO:") and "já existe" in x for x in saidas["depois-de-novo"][0]), saidas["depois-de-novo"])
        for caso in ("antes-grupo-existe", "antes-leitura-falhou"):
            self.assertTrue(any(x.startswith("EXCECAO:") for x in saidas[caso][0]), caso)
        self.assertFalse((self.pasta / "outra").exists(), "grupo já existente: nada é gravado")
        self.assertFalse((self.pasta / "falha").exists() and any((self.pasta / "falha").iterdir()), "uma leitura falhou: nada é gravado")
        self.assertFalse(any(x.startswith(("group list", "resource list")) for x in saidas["antes-grupo-existe"][1]), "grupo existente: nenhuma listagem foi lida")
        # o que o PowerShell gravou é o que o Python lê, e a conferência aprova o encerramento perfeito
        presenca = json.loads((pasta_depois / "presenca-depois.json").read_text(encoding="utf-8-sig"))
        self.assertEqual(set(presenca.values()), {"ausente"}, presenca)
        self.assertEqual(set(presenca), {item.chave for item in enc.itens_de_presenca(inv)})
        inventario = self.escrever("inventario.json", dados)
        argumentos = ["--etapa", "conferir", "--inventario", str(inventario), "--presenca", str(pasta_depois / "presenca-depois.json")]
        for momento, pasta in (("antes", pasta_antes), ("depois", pasta_depois)):
            for nome in ("grupos", "recursos", "papeis"):
                argumentos += [f"--{nome}-{momento}", str(pasta / f"{nome}-{momento}.json")]
        codigo, saida = executar(*argumentos)
        self.assertEqual(codigo, CODIGO_OK, saida)
        self.assertIn("Resultado: APROVADO", saida)
        # com um aplicativo ainda presente no Graph (200), o MESMO bloco produz uma presença que reprova a conferência
        objeto = dados["identidades_entra"][0]["objeto_id"]
        presente = json.loads(json.dumps(dados).replace(objeto, "b" + objeto[1:]))
        self.rodar([("presente", enc.comandos_de_captura(c.assinatura, c.grupo, "depois", str(self.pasta / "presente"), enc.inventario_de_dados(presente)), regras_depois)])
        estados = json.loads((self.pasta / "presente" / "presenca-depois.json").read_text(encoding="utf-8-sig"))
        self.assertIn("presente", estados.values())
        argumentos_presente = list(argumentos)
        argumentos_presente[3] = str(self.escrever("inventario-presente.json", presente))
        argumentos_presente[5] = str(self.pasta / "presente" / "presenca-depois.json")
        codigo, saida = executar(*argumentos_presente)
        self.assertEqual(codigo, CODIGO_DIVERGENCIA, saida)


class ComportamentoNoWindowsPowerShell5Tests(HarnessDoPowerShell):
    """O mesmo trabalho no Windows PowerShell 5.1, onde `ConvertFrom-Json | Where-Object` entrega a lista inteira ao filtro e o
    `-SkipHttpErrorCheck` nem existe. Só roda onde o powershell.exe 5.1 existe (o `az` e o Graph continuam FALSOS)."""

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        if not powershell_5():
            raise unittest.SkipTest("Windows PowerShell 5.1 (powershell.exe) não encontrado: o comportamento dos blocos nele não foi conferido")

    def blocos(self) -> list[tuple[str, str, str]]:
        return blocos_de_powershell(self.c, enc.montar_plano(self.c.carregado(), True), "./encerramento")

    def test_os_blocos_impressos_tambem_passam_pelo_analisador_de_sintaxe_do_5_1(self):
        saida = analisar_sintaxe(powershell_5(), [bloco for _, bloco, _ in self.blocos()])
        self.assertEqual(saida.strip().splitlines()[-1], "falhas=0", saida)

    def test_todo_bloco_recusa_no_5_1_sem_chamar_o_az_e_sem_responder_ausente(self):
        blocos = self.blocos()
        saidas = self.rodar([(rotulo, bloco, []) for rotulo, bloco, _ in blocos], windows_powershell=True)
        self.assertEqual(set(saidas), {rotulo for rotulo, _, _ in blocos})
        for rotulo, _, categoria in blocos:
            linhas, chamadas = saidas[rotulo]
            self.assertEqual(chamadas, [], f"{rotulo}: nenhum az e nenhuma consulta ao Graph")
            self.assertIn("PowerShell 7", junto(linhas), rotulo)
            self.assertFalse(any(x.strip() in ("ausente", "presente") for x in linhas), rotulo)
            if categoria == "verificacao":
                self.assertEqual(linhas[-1], "indeterminado", rotulo)

    def test_colado_linha_a_linha_no_5_1_nenhum_bloco_executa_nada(self):
        blocos = [(rotulo, bloco, []) for rotulo, bloco, _ in self.blocos()]
        saidas = self.rodar(blocos + [("controle-az", "az ping", [self.regra("ping")])], windows_powershell=True, colando=True)
        self.assertEqual(set(saidas), {rotulo for rotulo, _, _ in blocos} | {"controle-az"})
        self.assertEqual(saidas["controle-az"][1], ["ping"], "o ensaio registra as chamadas ao az")
        for rotulo, _, _ in blocos:
            self.assertEqual(saidas[rotulo][1], [], f"{rotulo}: um throw solto não impediria as linhas seguintes; o comando composto impede")

    def test_o_corpo_das_guardas_confere_o_inventario_no_5_1_como_no_7(self):
        plano = enc.montar_plano(self.c.carregado(), True)
        passos = {}
        for passo in plano.passos:
            passos.setdefault(passo.tipo, passo)
        casos, deve_apagar = self.casos_das_guardas(lambda tipo: desembrulhar(passos[tipo].comando))
        self.conferir_guardas(self.rodar(casos, windows_powershell=True), deve_apagar)


if __name__ == "__main__":
    unittest.main()
