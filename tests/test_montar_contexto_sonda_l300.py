"""Testes do montador do contexto de build da sonda do L300 e dos modelos em infra/sonda-l300 (scripts/montar_contexto_sonda_l300.py).

Tudo é local: o montador não usa rede, Azure, Docker nem az, e estes testes gravam só em pastas temporárias. O que se prova: o contexto
tem exatamente a lista fechada (mais o Dockerfile e o .dockerignore da sonda), cada arquivo confere por hash, uma pasta com conteúdo é
recusada, o Dockerfile da sonda é público, sem segredos nem GUID, e o Dockerfile e o .dockerignore da RAIZ (do chat) não são tocados.
"""

import ast
import contextlib
import hashlib
import io
import os
import re
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest import mock

import support  # noqa: F401  (configura o caminho dos scripts)
import lab_comum
import montar_contexto_sonda_l300 as montar
from support import RAIZ
from test_sonda_l300 import criar_link_simbolico

GUID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.IGNORECASE)
# A lista fechada, escrita por extenso: acrescentar ou retirar um arquivo da imagem da sonda exige mudar esta lista de propósito.
LISTA_FECHADA = (
    "scripts/sonda_l300.py",
    "scripts/gerar_carga_l400.py",
    "scripts/gerenciar_ingestao_l300.py",
    "scripts/gerenciar_ingestao.py",
    "scripts/lab_ingestao.py",
    "scripts/lab_ingestao_l300.py",
    "dados/l100/inventario.json",
    "dados/l100/documentos/vareleira-lar-condicoes-gerais-v1.0.md",
    "dados/l100/documentos/vareleira-lar-faq-v1.0.md",
    "dados/l100/documentos/vareleira-lar-glossario-v1.0.md",
    "dados/l300/permissoes-documentais.json",
    "dados/l300/documentos/roteiro-interno-atendimento-v1.0.md",
)
ESPERADOS = {*montar.ARQUIVOS, "Dockerfile", ".dockerignore"}


def sha256(caminho: Path) -> str:
    return hashlib.sha256(caminho.read_bytes()).hexdigest()


def executar(*argv: str) -> tuple[int, str, str]:
    saida, erro = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(saida), contextlib.redirect_stderr(erro):
        try:
            codigo = montar.principal(list(argv))
        except SystemExit as encerrado:
            codigo = encerrado.code
    return codigo, saida.getvalue(), erro.getvalue()


def modulos_importados(caminho: Path) -> set[str]:
    """Módulos que o arquivo importa, direta ou indiretamente por funções (import dentro de função também conta)."""
    importados: set[str] = set()
    for no in ast.walk(ast.parse(caminho.read_text(encoding="utf-8"))):
        if isinstance(no, ast.Import):
            importados |= {alias.name.split(".")[0] for alias in no.names}
        elif isinstance(no, ast.ImportFrom) and no.module and no.level == 0:
            importados.add(no.module.split(".")[0])
    return importados


def bloco_do_comando(saida: str) -> list[str]:
    """As linhas do comando de build impresso: de `Set-Location` até a linha que termina em ` .` (a origem do build)."""
    linhas = saida.splitlines()
    inicio = next((i for i, linha in enumerate(linhas) if linha.startswith("Set-Location")), None)
    fim = None if inicio is None else next((i for i in range(inicio, len(linhas)) if linhas[i].endswith(" .")), None)
    if inicio is None or fim is None:
        raise AssertionError("o comando de build (Set-Location ... az acr build ... .) não está na saída")
    return linhas[inicio:fim + 1]


class BaseDoMontador(unittest.TestCase):
    def setUp(self):
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        self.pasta = Path(pasta.name)
        self.destino = self.pasta / "contexto"

    def arquivos(self, destino=None) -> set[str]:
        return montar.arquivos_da_pasta(destino or self.destino)


class MontagemTests(BaseDoMontador):
    def test_monta_so_a_lista_fechada_mais_o_dockerfile_e_a_lista_de_permissao_da_sonda(self):
        codigo, saida, erro = executar("--destino", str(self.destino))
        self.assertEqual((codigo, erro), (0, ""))
        self.assertEqual(self.arquivos(), ESPERADOS)
        self.assertEqual(len(montar.ARQUIVOS), len(set(montar.ARQUIVOS)))
        for relativo in montar.ARQUIVOS:
            copiado, origem = self.destino / relativo, RAIZ / relativo
            self.assertEqual(copiado.read_bytes(), origem.read_bytes(), relativo)  # cópia byte a byte, conferida por hash
            self.assertIn(sha256(origem)[:12], saida)
        # Os dois arquivos gerados vêm dos modelos de infra/sonda-l300, com LF, e não do Dockerfile nem do .dockerignore da raiz.
        for gerado, modelo in (("Dockerfile", "Dockerfile"), (".dockerignore", "dockerignore")):
            dados = (self.destino / gerado).read_bytes()
            self.assertNotIn(b"\r", dados)
            self.assertEqual(dados, (RAIZ / "infra" / "sonda-l300" / modelo).read_bytes().replace(b"\r\n", b"\n"))
        self.assertNotEqual((self.destino / "Dockerfile").read_bytes().replace(b"\r\n", b"\n"),
                            (RAIZ / "Dockerfile").read_bytes().replace(b"\r\n", b"\n"))
        self.assertNotEqual((self.destino / ".dockerignore").read_bytes().replace(b"\r\n", b"\n"),
                            (RAIZ / ".dockerignore").read_bytes().replace(b"\r\n", b"\n"))
        self.assertIn(f"({len(ESPERADOS)})", saida)

    def test_a_lista_fechada_tem_12_arquivos_por_extenso_e_o_gerador_de_carga_do_l400_vai_junto(self):
        self.assertEqual(montar.ARQUIVOS, LISTA_FECHADA)
        self.assertEqual(len(LISTA_FECHADA), 12)
        codigo, saida, erro = executar("--destino", str(self.destino))
        self.assertEqual((codigo, erro), (0, ""))
        self.assertEqual(self.arquivos(), {*LISTA_FECHADA, "Dockerfile", ".dockerignore"})
        self.assertIn("(14)", saida)
        gerador = "scripts/gerar_carga_l400.py"
        self.assertEqual(sha256(self.destino / gerador), sha256(RAIZ / gerador))
        self.assertIn(sha256(RAIZ / gerador)[:12], saida)
        self.assertIn(gerador, montar.origens_copiadas((self.destino / "Dockerfile").read_text(encoding="utf-8")))
        self.assertIn("!" + gerador, (self.destino / ".dockerignore").read_text(encoding="utf-8").splitlines())
        # Nenhum outro script do repositório entra: nem as sondas do lado externo, nem este montador, nem os de encerramento.
        for nome in ("sonda_http_externa_l300", "sonda_negativas_externas_l300", "montar_contexto_sonda_l300", "planejar_encerramento",
                     "lab_encerramento", "operar_l300", "operar_l400", "chat_web"):
            self.assertNotIn(f"scripts/{nome}.py", self.arquivos())
        self.assertIn("ENTRYPOINT continua sendo a sonda", saida)
        for gerado in ("Dockerfile", ".dockerignore", gerador):
            self.assertEqual(GUID.findall((self.destino / gerado).read_text(encoding="utf-8")), [], gerado)

    def test_o_montador_nao_toca_no_dockerfile_nem_no_dockerignore_da_raiz(self):
        antes = {nome: sha256(RAIZ / nome) for nome in ("Dockerfile", ".dockerignore")}
        executar("--destino", str(self.destino))
        executar("--destino", str(self.destino))  # a segunda é recusada
        self.assertEqual({nome: sha256(RAIZ / nome) for nome in antes}, antes)
        self.assertEqual({p.name for p in (RAIZ / "infra" / "sonda-l300").iterdir()}, {"Dockerfile", "dockerignore"})

    def test_o_contexto_gerado_tem_os_copy_do_dockerfile_iguais_aos_arquivos_copiados(self):
        executar("--destino", str(self.destino))
        dockerfile = (self.destino / "Dockerfile").read_text(encoding="utf-8")
        origens = montar.origens_copiadas(dockerfile)
        self.assertEqual(len(origens), len(set(origens)), "nenhuma origem repetida")
        self.assertEqual(set(origens), self.arquivos() - {"Dockerfile", ".dockerignore"})
        self.assertEqual(set(origens), set(montar.ARQUIVOS))
        regras = montar.regras_do_dockerignore((self.destino / ".dockerignore").read_text(encoding="utf-8"))
        self.assertEqual(regras[0], "**")
        permissoes = [regra[1:] for regra in regras if regra.startswith("!")]
        self.assertEqual(set(permissoes), set(origens) | {"Dockerfile"})
        for origem in origens:
            self.assertTrue((self.destino / origem).is_file(), origem)
        destinos = {argumentos.split()[-1] for nome, argumentos in montar.instrucoes_do_dockerfile(dockerfile) if nome == "COPY"}
        self.assertEqual(destinos, {"./scripts/", "./dados/l100/inventario.json", "./dados/l100/documentos/",
                                    "./dados/l300/permissoes-documentais.json", "./dados/l300/documentos/roteiro-interno-atendimento-v1.0.md"})

    def test_aceita_pasta_vazia_e_recusa_pasta_com_conteudo_arquivo_ou_pasta_mae_inexistente(self):
        vazia = self.pasta / "vazia"
        vazia.mkdir()
        codigo, _, erro = executar("--destino", str(vazia))
        self.assertEqual((codigo, erro), (0, ""))
        self.assertEqual(self.arquivos(vazia), ESPERADOS)
        casos = {}
        com_conteudo = self.pasta / "com-conteudo"
        com_conteudo.mkdir()
        (com_conteudo / "x.txt").write_text("não é meu", encoding="utf-8")
        casos["conteúdo"] = (com_conteudo, "não está vazia")
        oculto = self.pasta / "com-oculto"
        oculto.mkdir()
        (oculto / ".env").write_text("A=1", encoding="utf-8")
        casos["oculto"] = (oculto, "não está vazia")
        arquivo = self.pasta / "arquivo.txt"
        arquivo.write_text("x", encoding="utf-8")
        casos["arquivo"] = (arquivo, "não é uma pasta")
        casos["pasta-mãe"] = (self.pasta / "nao-existe" / "ctx", "pasta-mãe")
        for nome, (destino, trecho) in casos.items():
            with self.subTest(nome):
                antes = sorted(p.name for p in destino.parent.iterdir()) if destino.parent.exists() else []
                codigo, saida, erro = executar("--destino", str(destino))
                self.assertEqual((codigo, saida), (lab_comum.CODIGO_USO, ""))
                self.assertIn(trecho, erro)
                self.assertTrue(erro.startswith("[ERRO]"))
                if destino.parent.exists():
                    self.assertEqual(sorted(p.name for p in destino.parent.iterdir()), antes, "nada foi criado nem alterado")
        self.assertEqual({p.name for p in com_conteudo.iterdir()}, {"x.txt"})
        self.assertEqual((oculto / ".env").read_text(encoding="utf-8"), "A=1")

    def test_destino_obrigatorio(self):
        codigo, _, erro = executar()
        self.assertEqual(codigo, lab_comum.CODIGO_USO)
        self.assertIn("--destino", erro)

    def test_dentro_do_repositorio_so_avisa(self):
        self.assertTrue(montar.dentro_do_repositorio(RAIZ / "build" / "ctx"))
        self.assertFalse(montar.dentro_do_repositorio(self.destino))
        _, saida, _ = executar("--destino", str(self.destino))
        self.assertNotIn("[AVISO]", saida)

    def test_uma_falha_no_meio_retira_o_que_foi_criado_e_nao_deixa_contexto_pela_metade(self):
        chamadas = []

        def falha_na_quarta(alvo, relativo, esperado):
            chamadas.append(relativo)
            if len(chamadas) == 4:
                raise lab_comum.ErroLab("hash diferente", lab_comum.CODIGO_DIVERGENCIA)

        with mock.patch.object(montar, "_conferir_copia", falha_na_quarta):
            codigo, saida, erro = executar("--destino", str(self.destino))
        self.assertEqual((codigo, saida), (lab_comum.CODIGO_DIVERGENCIA, ""))
        self.assertFalse(self.destino.exists(), "uma pasta nova que o montador criou some junto")
        existente = self.pasta / "existente"
        existente.mkdir()
        chamadas.clear()
        with mock.patch.object(montar, "_conferir_copia", falha_na_quarta):
            codigo, _, _ = executar("--destino", str(existente))
        self.assertEqual(codigo, lab_comum.CODIGO_DIVERGENCIA)
        self.assertEqual(list(existente.iterdir()), [], "uma pasta vazia que já existia volta a ficar vazia")

        original, contagem = Path.write_bytes, []

        def falha_ao_gravar(self_, dados):
            contagem.append(1)
            if len(contagem) == 3:
                raise OSError("disco cheio")
            return original(self_, dados)

        with mock.patch.object(Path, "write_bytes", falha_ao_gravar):
            codigo, _, erro = executar("--destino", str(self.pasta / "outra"))
        self.assertEqual(codigo, lab_comum.CODIGO_USO)
        self.assertIn("OSError", erro)
        self.assertFalse((self.pasta / "outra").exists())

    def test_um_defeito_do_script_vira_codigo_4_sem_traceback_e_nada_fica_criado(self):
        with mock.patch.object(montar, "arquivos_da_pasta", side_effect=RuntimeError("defeito com C:\\caminho\\privado")):
            codigo, saida, erro = executar("--destino", str(self.destino))
        self.assertEqual((codigo, saida), (lab_comum.CODIGO_INESPERADO, ""))
        self.assertIn("RuntimeError", erro)
        self.assertNotIn("privado", erro)
        self.assertNotIn("Traceback", erro)
        self.assertFalse(self.destino.exists())

    def test_o_hash_da_copia_e_conferido_depois_de_gravar(self):
        original = Path.write_bytes

        def corrompe(self_, dados):
            return original(self_, dados + b"x" if self_.name == "inventario.json" else dados)

        with mock.patch.object(Path, "write_bytes", corrompe):
            codigo, _, erro = executar("--destino", str(self.destino))
        self.assertEqual(codigo, lab_comum.CODIGO_DIVERGENCIA)
        self.assertIn("dados/l100/inventario.json", erro)
        self.assertFalse(self.destino.exists())

    def test_origem_ausente_ou_symlink_ou_fora_do_repositorio_nada_e_criado(self):
        with mock.patch.object(montar, "ARQUIVOS", (*montar.ARQUIVOS[:-1], "dados/l300/documentos/nao-existe.md")):
            codigo, _, erro = executar("--destino", str(self.destino))
        self.assertEqual(codigo, lab_comum.CODIGO_DIVERGENCIA)
        self.assertFalse(self.destino.exists())
        with mock.patch.object(Path, "is_symlink", lambda self_: self_.name == "vareleira-lar-faq-v1.0.md"):
            codigo, _, erro = executar("--destino", str(self.destino))
        self.assertEqual((codigo, self.destino.exists()), (lab_comum.CODIGO_DIVERGENCIA, False))
        self.assertIn("vareleira-lar-faq-v1.0.md", erro)

    def test_modelos_diferentes_da_lista_fechada_sao_recusados_antes_de_criar_qualquer_arquivo(self):
        dockerfile = (RAIZ / "infra" / "sonda-l300" / "Dockerfile").read_text(encoding="utf-8")
        lista = (RAIZ / "infra" / "sonda-l300" / "dockerignore").read_text(encoding="utf-8")
        variantes = {
            "COPY a mais": (dockerfile.replace("./dados/l300/permissoes-documentais.json\n", "./dados/l300/permissoes-documentais.json\n"
                                               "COPY scripts/chat_web.py ./scripts/\n", 1), lista),
            "COPY a menos": (dockerfile.replace("scripts/lab_ingestao.py ", "", 1), lista),
            "sem ARG": (dockerfile.replace("ARG IMAGEM_CHAT\n", "ARG IMAGEM_CHAT=python:3.12-slim\n", 1), lista),
            "USER root": (dockerfile.replace("USER 10001:10001", "USER root", 1), lista),
            "permissão a mais": (dockerfile, lista.replace("!Dockerfile\n", "!Dockerfile\n!scripts/chat_web.py\n", 1)),
            "permissão a menos": (dockerfile, lista.replace("!scripts/lab_ingestao.py\n", "", 1)),
            "exclusão final ausente": (dockerfile, lista.replace("**/.env\n", "", 1)),
            "exclusão antes das permissões": (dockerfile, lista.replace("**\n", "**\n**/.env\n", 1).replace("\n**/.env\n**/.env.*", "\n**/.env.*", 1)),
        }
        for nome, (texto_do_dockerfile, texto_da_lista) in variantes.items():
            with self.subTest(nome), self.assertRaises(lab_comum.ErroLab) as erro:
                montar.conferir_modelos(texto_do_dockerfile, texto_da_lista)
            self.assertEqual(erro.exception.codigo, lab_comum.CODIGO_DIVERGENCIA)
        montar.conferir_modelos(dockerfile, lista)
        modelo = self.pasta / "Dockerfile-ruim"
        modelo.write_text(variantes["COPY a mais"][0], encoding="utf-8")
        with mock.patch.object(montar, "MODELO_DO_DOCKERFILE", modelo):
            codigo, _, erro = executar("--destino", str(self.destino))
        self.assertEqual((codigo, self.destino.exists()), (lab_comum.CODIGO_DIVERGENCIA, False))
        self.assertIn("COPY do Dockerfile", erro)

    def test_documento_novo_no_manifesto_ou_no_inventario_exige_revisar_a_lista(self):
        with mock.patch.object(montar, "ARQUIVOS", montar.ARQUIVOS[:-1]):
            with self.assertRaises(lab_comum.ErroLab) as erro:
                montar.conferir_documentos_declarados()
        self.assertEqual(erro.exception.codigo, lab_comum.CODIGO_DIVERGENCIA)
        montar.conferir_documentos_declarados()

    def test_ler_modelo_normaliza_crlf_para_lf_e_recusa_o_que_nao_e_utf8(self):
        crlf = self.pasta / "m"
        crlf.write_bytes(b"A\r\nB\r\n")
        self.assertEqual(montar.ler_modelo(crlf), b"A\nB\n")
        crlf.write_bytes(b"\xff\xfe\x00")
        with self.assertRaises(lab_comum.ErroLab):
            montar.ler_modelo(crlf)


class ConferenciaDeOrigemTests(BaseDoMontador):
    """conferir_origem com a função REAL, sobre um repositório de verdade em pasta temporária: só a RAIZ é trocada por ela."""

    def setUp(self):
        super().setUp()
        self.repositorio, self.fora = self.pasta / "repositorio", self.pasta / "fora"
        (self.repositorio / "dados").mkdir(parents=True)
        self.fora.mkdir()
        (self.repositorio / "dados" / "dentro.md").write_text("dentro", encoding="utf-8")
        (self.fora / "fora.md").write_text("fora do repositório", encoding="utf-8")
        patch = mock.patch.object(montar, "RAIZ", self.repositorio)
        patch.start()
        self.addCleanup(patch.stop)

    def recusa(self, relativo):
        with self.assertRaises(lab_comum.ErroLab) as erro:
            montar.conferir_origem(relativo)
        self.assertEqual(erro.exception.codigo, lab_comum.CODIGO_DIVERGENCIA)
        self.assertIn(relativo, str(erro.exception))

    def test_aceita_um_arquivo_comum_dentro_da_raiz(self):
        self.assertEqual(montar.conferir_origem("dados/dentro.md"), self.repositorio / "dados" / "dentro.md")

    def test_recusa_um_arquivo_real_fora_da_raiz_mesmo_sem_nenhum_link(self):
        # Existe, é um arquivo comum e não é link: só a conferência de que o caminho resolvido fica dentro do repositório o recusa.
        self.assertTrue((self.repositorio / ".." / "fora" / "fora.md").is_file())
        self.recusa("../fora/fora.md")

    def test_recusa_uma_pasta_que_e_link_para_fora_da_raiz(self):
        criar_link_simbolico(self.repositorio / "ligacao", self.fora, pasta=True)
        self.recusa("ligacao/fora.md")

    def test_recusa_um_arquivo_que_e_link_mesmo_apontando_para_dentro_da_raiz(self):
        criar_link_simbolico(self.repositorio / "dados" / "atalho.md", self.repositorio / "dados" / "dentro.md")
        self.recusa("dados/atalho.md")

    def test_recusa_origem_ausente_e_pasta(self):
        self.recusa("dados/nao-existe.md")
        self.recusa("dados")


class ComandoDeBuildTests(BaseDoMontador):
    def verificar_a_forma_do_comando(self, comando):
        """A forma que funcionou no Azure: o az resolve --file a partir do diretório atual, então o build roda de dentro da pasta do contexto."""
        texto, az = "\n".join(comando), "\n".join(comando[1:])
        self.assertTrue(comando[0].startswith("Set-Location "), "o diretório atual precisa ser a pasta do contexto")
        self.assertEqual(comando[1], "az acr build `")
        self.assertNotIn("--file", texto)
        self.assertIsNone(re.search(r"\s-f\s", texto))
        self.assertNotIn("Dockerfile", texto, "sem --file o az usa o Dockerfile da pasta atual, que é a do contexto")
        self.assertTrue(texto.endswith(" ."), "a origem do build é `.`, a pasta atual")
        self.assertEqual(texto.split()[-1], ".")
        self.assertEqual(comando[-1], "    --no-logs .")
        self.assertIn("    --subscription <assinatura> `", comando)
        self.assertNotIn(str(self.destino.resolve()), az, "a pasta do contexto não é argumento do az")
        self.assertEqual(re.findall(r"^\s+(--[a-z-]+)", az, re.MULTILINE),
                         ["--subscription", "--registry", "--image", "--build-arg", "--no-logs"])  # as opções de `az acr build --help`

    def test_o_comando_de_referencia_entra_na_pasta_do_contexto_e_usa_ponto_como_origem_sem_file(self):
        codigo, saida, _ = executar("--destino", str(self.destino))
        self.assertEqual(codigo, 0)
        comando = bloco_do_comando(saida)
        self.verificar_a_forma_do_comando(comando)
        self.assertEqual(comando, [f"Set-Location -LiteralPath '{self.destino.resolve()}'", "az acr build `",
                                   "    --subscription <assinatura> `", "    --registry <registro> `",
                                   "    --image <repositorio-da-sonda>:<tag-nova> `",
                                   "    --build-arg IMAGEM_CHAT=<registro>.azurecr.io/<repositorio-do-chat>:<tag-do-chat> `", "    --no-logs ."])
        self.assertEqual(GUID.findall(saida), [], "o comando traz só marcadores < >: nenhum valor real do ambiente")
        self.assertIn("ALTERA o Azure", saida)
        self.assertIn("nunca latest", saida)
        self.assertIn("só a referência da imagem, nunca segredos", saida)

    def test_a_explicacao_diz_por_que_o_build_roda_de_dentro_da_pasta_e_como_ler_o_log_depois(self):
        _, saida, _ = executar("--destino", str(self.destino), "--registro", "registroteste")
        linhas = saida.splitlines()
        depois = linhas[linhas.index("    --no-logs .") + 1:]
        posicao = depois.index("$env:PYTHONIOENCODING = 'utf-8'")
        self.assertEqual(depois[posicao:posicao + 2], ["$env:PYTHONIOENCODING = 'utf-8'", "az acr task logs --subscription <assinatura> "
                                                       "--registry registroteste --run-id <run-id>"])
        explicacao = " ".join(depois[:posicao])
        for trecho in ("O az resolve --file a partir do diretório atual, e não do contexto", "roda de dentro da pasta do contexto",
                       "o --no-logs evita a falha de Unicode do Windows", "az acr task logs --run-id", "o run-id está no JSON final do build"):
            self.assertIn(trecho, explicacao)
        for antigo in ("ÚLTIMO argumento", "--file aponta", "aponta o Dockerfile dela"):
            self.assertNotIn(antigo, saida)
        for trecho in ("diretório ATUAL", "Set-Location", "`.` como origem", "az acr task logs --run-id"):
            self.assertIn(trecho, montar.__doc__)

    def test_a_assinatura_nunca_vem_do_ambiente_e_os_marcadores_continuam_no_comando(self):
        assinatura = str(uuid.uuid4())  # gerado agora: o repositório não guarda GUIDs literais
        with mock.patch.dict(os.environ, {"AZURE_SUBSCRIPTION_ID": assinatura, "ARM_SUBSCRIPTION_ID": assinatura}):
            _, saida, _ = executar("--destino", str(self.destino))
        self.assertNotIn(assinatura, saida)
        self.assertEqual(saida.count("<assinatura>"), 2, "um no build e outro na leitura do log")

    def test_valores_informados_preenchem_o_comando_depois_de_validados(self):
        imagem_do_chat = "registroteste.azurecr.io/vareleira/chat-l300:20261011-1"
        codigo, saida, _ = executar("--destino", str(self.destino), "--registro", "registroteste", "--imagem-chat", imagem_do_chat,
                                    "--imagem-sonda", "vareleira/sonda-l300:20261011-2")
        self.assertEqual(codigo, 0)
        self.assertIn("    --registry registroteste `", saida)
        self.assertIn(f"    --build-arg IMAGEM_CHAT={imagem_do_chat} `", saida)
        self.assertIn("    --image vareleira/sonda-l300:20261011-2 `", saida)
        self.verificar_a_forma_do_comando(bloco_do_comando(saida))
        digest = "registroteste.azurecr.io/vareleira/chat-l300@sha256:" + "a" * 64
        self.assertEqual(montar.validar_imagem_do_chat(digest), digest)
        for invalido, funcao in (("RegistroMaiusculo", montar.validar_registro), ("curt", montar.validar_registro),
                                 ("registro.com/x", montar.validar_registro),
                                 ("exemplo.com/chat:1", montar.validar_imagem_do_chat), ("registroteste.azurecr.io/Chat:1", montar.validar_imagem_do_chat),
                                 ("registroteste.azurecr.io/chat", montar.validar_imagem_do_chat),
                                 ("registroteste.azurecr.io/chat:1; rm -rf", montar.validar_imagem_do_chat),
                                 ("vareleira/sonda-l300", montar.validar_imagem_da_sonda), ("vareleira/sonda-l300:latest", montar.validar_imagem_da_sonda),
                                 ("Sonda:1", montar.validar_imagem_da_sonda)):
            with self.subTest(invalido), self.assertRaises(Exception):
                funcao(invalido)
        outro = self.pasta / "outro"
        codigo, _, erro = executar("--destino", str(outro), "--registro", "registroteste", "--imagem-chat",
                                   "outroregistro.azurecr.io/chat:1")
        self.assertEqual((codigo, outro.exists()), (lab_comum.CODIGO_USO, False))
        self.assertIn("--registro", erro)
        codigo, _, _ = executar("--destino", str(outro), "--imagem-sonda", "vareleira/sonda-l300:latest")
        self.assertEqual((codigo, outro.exists()), (lab_comum.CODIGO_USO, False))

    def test_a_pasta_com_aspas_espacos_e_colchetes_vira_um_literal_valido_do_powershell(self):
        pasta = Path("C:/Users/Ana O'Neil/contexto [sonda]")
        primeira = montar.comando_de_build(pasta, None, None, None).splitlines()[0]
        self.assertEqual(primeira, "Set-Location -LiteralPath '" + str(pasta).replace("'", "''") + "'")
        self.assertIn("O''Neil", primeira)
        self.assertIn("-LiteralPath", primeira, "colchetes no caminho não podem virar curinga do PowerShell")


class DockerfileDaSondaTests(unittest.TestCase):
    def setUp(self):
        self.texto = (RAIZ / "infra" / "sonda-l300" / "Dockerfile").read_text(encoding="utf-8")
        self.instrucoes = montar.instrucoes_do_dockerfile(self.texto)
        self.do_chat = montar.instrucoes_do_dockerfile((RAIZ / "Dockerfile").read_text(encoding="utf-8"))

    def test_deriva_da_imagem_do_chat_informada_no_build_sem_valor_padrao(self):
        self.assertEqual(self.instrucoes[0], ("ARG", "IMAGEM_CHAT"))
        self.assertEqual(self.instrucoes[1], ("FROM", "${IMAGEM_CHAT}"))
        self.assertEqual([argumentos for nome, argumentos in self.instrucoes if nome == "FROM"], ["${IMAGEM_CHAT}"])
        self.assertEqual([argumentos for nome, argumentos in self.instrucoes if nome == "ARG"], ["IMAGEM_CHAT"])

    def test_nao_tem_segredos_configuracao_embutida_nem_guid(self):
        self.assertEqual(GUID.findall(self.texto), [])
        for nome, argumentos in self.instrucoes:
            if nome in {"ENV", "ARG"}:
                self.assertNotRegex(argumentos, r"(?i)secret|password|token|key|credential|connection")
                self.assertNotRegex(argumentos, r"VARELEIRA_|AZURE_")
        for proibido in ("--demo", "--trusted-host", ".env", "pip install", "curl", "wget", "az login"):
            self.assertNotIn(proibido, self.texto)
        self.assertNotIn("ADD", [nome for nome, _ in self.instrucoes])
        self.assertNotIn("EXPOSE", [nome for nome, _ in self.instrucoes])
        self.assertNotRegex(self.texto, r"(?m)^COPY +\.")

    def test_roda_sem_root_com_o_mesmo_uid_do_chat_e_sem_servidor(self):
        usuarios = [argumentos for nome, argumentos in self.instrucoes if nome == "USER"]
        usuarios_do_chat = [argumentos for nome, argumentos in self.do_chat if nome == "USER"]
        self.assertEqual(usuarios, usuarios_do_chat)
        self.assertTrue(usuarios[0].split(":")[0].isdigit() and int(usuarios[0].split(":")[0]) > 0)
        indice = {nome: posicao for posicao, (nome, _) in reversed(list(enumerate(self.instrucoes)))}
        self.assertLess(indice["USER"], indice["RUN"], "o build de validação já roda sem privilégios")
        self.assertIn(("HEALTHCHECK", "NONE"), self.instrucoes)

    def test_valida_no_build_e_o_ponto_de_entrada_e_a_sonda(self):
        execucoes = [argumentos for nome, argumentos in self.instrucoes if nome == "RUN"]
        self.assertEqual(execucoes, ['["python", "scripts/sonda_l300.py", "--etapa", "validar"]'])
        self.assertEqual([argumentos for nome, argumentos in self.instrucoes if nome == "ENTRYPOINT"], ['["python", "scripts/sonda_l300.py"]'])
        self.assertEqual(self.instrucoes[-2][0], "ENTRYPOINT")
        self.assertEqual(self.instrucoes[-1], ("CMD", "[]"))

    def test_copia_so_o_que_o_chat_nao_tem_e_nada_do_lado_externo(self):
        origens = montar.origens_copiadas(self.texto)
        self.assertEqual(set(origens), set(montar.ARQUIVOS))
        base = {Path(origem).stem for origem in montar.origens_copiadas((RAIZ / "Dockerfile").read_text(encoding="utf-8"))
                if origem.startswith("scripts/")}
        enviados = {Path(origem).stem for origem in origens if origem.startswith("scripts/")}
        self.assertEqual(enviados & base, set(), "um módulo que a base já tem não é enviado de novo")
        self.assertTrue({"lab_comum", "lab_acesso", "lab_indexacao", "lab_geracao", "lab_politica", "lab_chat"} <= base)
        for nome in ("sonda_http_externa_l300", "sonda_negativas_externas_l300", "montar_contexto_sonda_l300"):
            self.assertNotIn(f"scripts/{nome}.py", origens)
        self.assertFalse(any(origem.startswith(("tests/", "docs/", "desafios/", "infra/", "web/", "requirements/")) for origem in origens))

    def test_as_importacoes_dos_arquivos_enviados_estao_na_imagem_ou_na_base(self):
        base = {Path(origem).stem for origem in montar.origens_copiadas((RAIZ / "Dockerfile").read_text(encoding="utf-8"))
                if origem.startswith("scripts/")}
        enviados = {Path(origem).stem for origem in montar.ARQUIVOS if origem.startswith("scripts/")}
        locais = {arquivo.stem for arquivo in (RAIZ / "scripts").glob("*.py")}
        for modulo in sorted(enviados):
            faltando = modulos_importados(RAIZ / "scripts" / f"{modulo}.py") & locais - enviados - base
            self.assertEqual(faltando, set(), modulo)
        # O gerador de carga do L400 também vai na imagem: o que ele importa (inclusive o import sob demanda, dentro de função) está na
        # base do chat ou entre os arquivos enviados.
        gerador = modulos_importados(RAIZ / "scripts" / "gerar_carga_l400.py") & locais
        self.assertIn("gerar_carga_l400", enviados)
        self.assertEqual(gerador - enviados - base, set())
        self.assertTrue({"lab_ingestao_l300", "lab_ingestao"} <= enviados, "a identidade gerenciada do gerador usa estes dois módulos")
        self.assertIn("lab_ingestao_l300", gerador, "o import sob demanda, dentro de função, também é visto")
        # A sonda importa os módulos do laboratório por nome (mod.<nome> e a lista de verificar_modulos): todos precisam existir na imagem.
        arvore = ast.parse((RAIZ / "scripts" / "sonda_l300.py").read_text(encoding="utf-8"))
        por_nome = {no.value for no in ast.walk(arvore) if isinstance(no, ast.Constant) and isinstance(no.value, str) and no.value in locais}
        por_atributo = {no.attr for no in ast.walk(arvore) if isinstance(no, ast.Attribute) and isinstance(no.value, ast.Name)
                        and no.value.id == "mod"}
        self.assertTrue({"lab_chat", "gerenciar_ingestao_l300"} <= por_nome | por_atributo)
        self.assertEqual((por_nome | por_atributo) - enviados - base, set())

    def test_o_gerador_de_carga_esta_na_imagem_e_roda_por_substituicao_de_comando_sem_mudar_o_entrypoint(self):
        self.assertIn("scripts/gerar_carga_l400.py", montar.origens_copiadas(self.texto))
        lista = (RAIZ / "infra" / "sonda-l300" / "dockerignore").read_text(encoding="utf-8")
        self.assertIn("!scripts/gerar_carga_l400.py", montar.regras_do_dockerignore(lista))
        comentarios = " ".join(linha.lstrip("# ") for linha in self.texto.splitlines() if linha.startswith("#"))
        for trecho in ("gerar_carga_l400", "ENTRYPOINT continua sendo a sonda", "--command", "--args"):
            self.assertIn(trecho, comentarios)
        self.assertEqual([argumentos for nome, argumentos in self.instrucoes if nome == "ENTRYPOINT"], ['["python", "scripts/sonda_l300.py"]'])
        executaveis = " ".join(argumentos for nome, argumentos in self.instrucoes if nome in {"ENTRYPOINT", "CMD", "RUN"})
        self.assertNotIn("gerar_carga_l400", executaveis, "o build não executa o gerador e o ponto de entrada continua sendo a sonda")

    def test_lista_de_permissao_so_libera_o_que_o_dockerfile_copia_e_termina_com_as_exclusoes(self):
        regras = montar.regras_do_dockerignore((RAIZ / "infra" / "sonda-l300" / "dockerignore").read_text(encoding="utf-8"))
        self.assertEqual(regras[0], "**")
        permissoes = [regra[1:] for regra in regras if regra.startswith("!")]
        self.assertEqual(set(permissoes), set(montar.origens_copiadas(self.texto)) | {"Dockerfile"})
        ultima = max(posicao for posicao, regra in enumerate(regras) if regra.startswith("!"))
        finais = set(regras[ultima + 1:])
        for exigida in ("**/.env", "**/.env.*", "**/*.pem", "**/*.key", ".git", ".venv", ".playwright-mcp", "context.md", "session-state"):
            self.assertIn(exigida, finais)
        self.assertFalse(any(regra.startswith("!") for regra in regras[ultima + 1:]))
        self.assertEqual(GUID.findall((RAIZ / "infra" / "sonda-l300" / "dockerignore").read_text(encoding="utf-8")), [])

    def test_a_raiz_continua_sendo_a_do_chat(self):
        raiz = (RAIZ / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("scripts/chat_web.py", raiz)
        self.assertNotIn("sonda", raiz.lower())
        self.assertNotIn("sonda", (RAIZ / ".dockerignore").read_text(encoding="utf-8").lower())


if __name__ == "__main__":
    unittest.main()
