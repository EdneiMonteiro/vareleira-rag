import contextlib
import dataclasses
import io
import json
import subprocess
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

import support  # noqa: F401  (configura o caminho dos scripts)
import avaliar_politica_local as ap
import lab_comum

DOC = "TST-DOC-1.0"
TEXTO_DO_DOCUMENTO = (
    "## 1. Prazos\n\n1.1. O aviso à seguradora deve ser feito em até sete dias corridos depois do fato.\n\n"
    "## 2. Franquias\n\n2.1. A franquia da cobertura básica corresponde a dez por cento do prejuízo apurado.\n")
PRAZO = "O aviso à seguradora deve ser feito em até sete dias corridos depois do fato."
FRANQUIA = "A franquia da cobertura básica corresponde a dez por cento do prejuízo apurado."
INVENTADA = "O prazo para avisar a seguradora é de trinta dias úteis, conforme uma regra que não existe."
ENTRE_TRECHOS = "depois do fato.\n\n## 2. Franquias"  # existe no documento, mas atravessa dois trechos
PERGUNTA, RESPOSTA = "ZXQ-PERGUNTA", "ZXQ-RESPOSTA"

POLITICA = '''\
from __future__ import annotations

from dataclasses import dataclass

DOCUMENTADA, CONTRATACAO_INDIVIDUAL, SEM_EVIDENCIA = "documentada", "contratacao_individual", "sem_evidencia"
FORA_DE_ESCOPO, AMBIGUA = "fora_de_escopo", "ambigua"
RESPONDIDA, RECUSADA, ESCLARECIMENTO, DESCARTADA = "respondida", "recusada", "esclarecimento", "descartada"
TEXTO_SEM_VEREDITO = "Texto fixo do programa para o caso individual."
AVISO_CONTRATACAO_INDIVIDUAL = "Aviso fixo do programa."
MENSAGEM_SEM_EVIDENCIA = "Recusa fixa do programa: sem evidência."
MENSAGEM_FORA_DE_ESCOPO = "Recusa fixa do programa: fora de escopo."
MENSAGEM_ESCLARECIMENTO = "Esclarecimento fixo do programa."
REPASSA_O_TEXTO_DO_MODELO = False


def normalizar(texto):
    return " ".join(texto.casefold().split())


@dataclass(frozen=True)
class Evidencia:
    fonte: str
    citacao: str


@dataclass(frozen=True)
class Decisao:
    situacao: str
    tipo: str
    texto: str
    aviso: str
    evidencias: tuple[Evidencia, ...]
    problemas: tuple[str, ...]


def aplicar_politica(saida, resultados, pergunta):
    tipo, resposta = saida["tipo"], saida["resposta"].strip()
    if tipo == SEM_EVIDENCIA:
        return Decisao(RECUSADA, tipo, MENSAGEM_SEM_EVIDENCIA, "", (), ())
    if tipo == FORA_DE_ESCOPO:
        return Decisao(RECUSADA, tipo, MENSAGEM_FORA_DE_ESCOPO, "", (), ())
    if tipo == AMBIGUA:
        return Decisao(ESCLARECIMENTO, tipo, resposta, "", (), ())
    textos = {trecho["id"]: normalizar(trecho["conteudo"]) for trecho in resultados}
    evidencias = tuple(Evidencia(item["fonte"], item["citacao"].strip()) for item in saida["evidencias"]
                       if normalizar(item["citacao"]) in textos.get(item["fonte"], ""))
    if len(evidencias) < len(saida["evidencias"]):
        return Decisao(DESCARTADA, tipo, "", "", (), ("citação que não está no trecho",))
    if tipo == CONTRATACAO_INDIVIDUAL:
        texto = resposta if REPASSA_O_TEXTO_DO_MODELO else TEXTO_SEM_VEREDITO
        return Decisao(RESPONDIDA, tipo, texto, AVISO_CONTRATACAO_INDIVIDUAL, evidencias, ())
    return Decisao(RESPONDIDA, tipo, resposta, "", evidencias, ())
'''
POLITICA_COM_DEFEITO = POLITICA.replace("REPASSA_O_TEXTO_DO_MODELO = False", "REPASSA_O_TEXTO_DO_MODELO = True")
POLITICA_COM_TEXTO_ALTERADO = POLITICA.replace(
    'Decisao(RECUSADA, tipo, MENSAGEM_SEM_EVIDENCIA, "", (), ())',
    'Decisao(RECUSADA, tipo, "Texto que o programa não declara.", "", (), ())')


def escrever_corpus(pasta: Path) -> Path:
    """Inventário com um documento sintético, no formato que o laboratório valida."""
    (pasta / "documentos").mkdir(parents=True)
    dados = TEXTO_DO_DOCUMENTO.encode("utf-8")
    (pasta / "documentos" / "doc-teste.md").write_bytes(dados)
    entrada = {
        "id": DOC, "titulo": "Documento sintético de teste", "tipo": "teste", "produto": "teste", "versao": "1.0",
        "autoridade_narrativa": "teste", "origem": "teste", "licenca": "teste", "arquivo": "documentos/doc-teste.md",
        "blob": "teste/doc-teste.md", "tipo_conteudo": "text/markdown; charset=utf-8",
        "sha256": lab_comum.calcular_sha256(dados), "tamanho_bytes": len(dados),
        "vigencia_ficticia": {"inicio": "2025-01-01", "fim": None}, "classificacao_acesso": {"nivel": "interno"},
        "revisao_real": {"status": "aprovada"}}
    caminho = pasta / "inventario.json"
    caminho.write_text(json.dumps({"schema_version": 1, "sintetico": True, "documentos": [entrada]}), encoding="utf-8")
    return caminho


def escrever_casos(caminho: Path, situacao_do_individual: str) -> Path:
    def caso(identificador, categoria, tipo_do_modelo, citacoes, tipo, situacao, livre):
        return {"id": identificador, "categoria": categoria, "pergunta": f"{PERGUNTA} {identificador}?",
                "tipo_do_modelo": tipo_do_modelo, "resposta_do_modelo": f"  {RESPOSTA} {identificador}.  ",
                "evidencias": [{"documento_id": DOC, "citacao": citacao} for citacao in citacoes],
                "esperado": {"tipo": tipo, "situacao": situacao, "texto_livre": livre}}

    casos = [
        caso("T-01", "documentada_geral", "documentada", [PRAZO], "documentada", "respondida", True),
        caso("T-02", "individual", "contratacao_individual", [FRANQUIA], "contratacao_individual", situacao_do_individual, False),
        caso("T-03", "sem_evidencia", "sem_evidencia", [PRAZO], "sem_evidencia", "recusada", False),
        caso("T-04", "fora_de_escopo", "fora_de_escopo", [], "fora_de_escopo", "recusada", False),
        caso("T-05", "ambigua", "ambigua", [], "ambigua", "esclarecimento", True),
        caso("T-06", "documentada_citacao_fabricada", "documentada", [INVENTADA], "documentada", "descartada", False),
    ]
    origem = {"citacoes_fabricadas": [{"caso_id": "T-06", "indice_evidencia": 0}]}
    caminho.write_text(json.dumps({"schema_version": 1, "sintetico": True, "origem": origem, "casos": casos}), encoding="utf-8")
    return caminho


def criar_repositorio(pasta: Path, versoes: tuple[str, ...]) -> list[str]:
    """Repositório de teste com um commit por versão de scripts/lab_politica.py; devolve os hashes completos."""
    def git(*argumentos: str) -> str:
        resultado = subprocess.run(
            ["git", "-c", "user.name=Teste", "-c", "user.email=teste@example.invalid", "-c", "commit.gpgsign=false", *argumentos],
            cwd=pasta, check=True, capture_output=True, text=True)
        return resultado.stdout.strip()

    git("init", "-q")
    (pasta / "scripts").mkdir()
    hashes = []
    for versao in versoes:
        (pasta / "scripts" / "lab_politica.py").write_text(versao, encoding="utf-8", newline="\n")
        git("add", "scripts/lab_politica.py")
        git("commit", "-q", "-m", "versão da política")
        hashes.append(git("rev-parse", "HEAD"))
    return hashes


def fabricar_caso(**mudancas) -> ap.Caso:
    base = dict(id="T-00", categoria="teste", pergunta=f"{PERGUNTA}?", tipo_do_modelo="documentada",
                resposta=f"  {RESPOSTA}, com espaços nas pontas.  ", evidencias=((DOC, PRAZO),), fabricadas=frozenset(),
                tipo_esperado="documentada", situacao_esperada="respondida", texto_livre=True)
    return ap.Caso(**{**base, **mudancas})


def com_decisao_alterada(modulo, **campos):
    """Cópia do módulo cuja política devolve a decisão original com os campos trocados: simula uma versão com defeito."""
    copia = types.SimpleNamespace(**vars(modulo))
    copia.aplicar_politica = lambda *argumentos: dataclasses.replace(modulo.aplicar_politica(*argumentos), **campos)
    return copia


def falhas(resultado: ap.Resultado) -> set[str]:
    """Nomes das verificações que divergiram, nos dois eixos (os nomes não se repetem entre eles)."""
    return {nome for eixo in (resultado.esperado_literal, resultado.apresentacao) for nome, ok in eixo.items() if not ok}


INDIVIDUAL = dict(tipo_do_modelo="contratacao_individual", resposta="Sim, o seu seguro cobre este caso.",
                  evidencias=((DOC, FRANQUIA),), tipo_esperado="contratacao_individual", texto_livre=False)


class AvaliacaoDeCasosTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pasta = Path(cls.enterClassContext(tempfile.TemporaryDirectory()))
        cls.corpus = ap.carregar_corpus(escrever_corpus(pasta))
        cls.correta = ap.carregar_modulo("lab_politica_de_teste", POLITICA.encode(), "politica-de-teste")
        cls.com_defeito = ap.carregar_modulo("lab_politica_de_teste_com_defeito", POLITICA_COM_DEFEITO.encode(), "politica-com-defeito")

    def entrada(self, **mudancas) -> ap.Entrada:
        return ap.montar_entrada(fabricar_caso(**mudancas), self.corpus, self.correta.normalizar)

    def test_texto_livre_so_e_conforme_quando_o_texto_do_modelo_e_conservado(self):
        entrada = self.entrada()
        conservado = ap.avaliar_caso(self.correta, entrada)
        self.assertEqual((conservado.conforme_ao_esperado_literal, conservado.conforme_na_apresentacao), (True, True), conservado)
        self.assertEqual(conservado.observado["texto"], "texto_do_modelo")
        resumido = ap.avaliar_caso(com_decisao_alterada(self.correta, texto="Resumo feito pelo programa."), entrada)
        self.assertEqual(falhas(resumido), {"texto_livre", "texto"})
        self.assertEqual(resumido.observado["texto"], "outro")

    def test_tipo_e_situacao_sao_comparados_literalmente_com_o_json(self):
        recusada = ap.avaliar_caso(self.correta, self.entrada(situacao_esperada="recusada", **INDIVIDUAL))
        self.assertEqual((recusada.esperado["situacao"], recusada.observado["situacao"]), ("recusada", "respondida"))
        self.assertEqual(recusada.esperado_literal, {"tipo": True, "situacao": False, "texto_livre": True})
        self.assertFalse(recusada.conforme_ao_esperado_literal)
        self.assertTrue(recusada.conforme_na_apresentacao)  # texto fixo, aviso e citações certos não compensam a situação
        respondida = self.entrada(situacao_esperada="respondida", **INDIVIDUAL)
        self.assertTrue(ap.avaliar_caso(self.correta, respondida).conforme_ao_esperado_literal)
        outro_tipo = ap.avaliar_caso(com_decisao_alterada(self.correta, tipo="documentada"), respondida)
        self.assertEqual(falhas(outro_tipo), {"tipo"})

    def test_individual_exige_o_texto_fixo_o_aviso_e_as_citacoes_do_programa(self):
        entrada = self.entrada(situacao_esperada="respondida", **INDIVIDUAL)
        correto = ap.avaliar_caso(self.correta, entrada)
        self.assertEqual((correto.conforme_ao_esperado_literal, correto.conforme_na_apresentacao), (True, True), correto)
        self.assertEqual((correto.observado["texto"], correto.observado["aviso"]),
                         ("TEXTO_SEM_VEREDITO", "AVISO_CONTRATACAO_INDIVIDUAL"))
        repassado = ap.avaliar_caso(self.com_defeito, entrada)
        self.assertEqual(repassado.observado["texto"], "texto_do_modelo")
        self.assertEqual(falhas(repassado), {"texto_livre", "texto"})
        self.assertEqual(falhas(ap.avaliar_caso(com_decisao_alterada(self.correta, aviso=""), entrada)), {"aviso"})
        self.assertEqual(falhas(ap.avaliar_caso(com_decisao_alterada(self.correta, evidencias=()), entrada)), {"citacoes"})

    def test_citacao_fabricada_exige_descarte_integral(self):
        entrada = self.entrada(evidencias=((DOC, INVENTADA),), fabricadas=frozenset({0}),
                               situacao_esperada="descartada", texto_livre=False)
        descartada = ap.avaliar_caso(self.correta, entrada)
        self.assertEqual((descartada.conforme_ao_esperado_literal, descartada.conforme_na_apresentacao), (True, True), descartada)
        self.assertEqual((descartada.observado["texto"], descartada.observado["citacoes_mantidas"]), ("vazio", 0))
        mantida = ap.avaliar_caso(com_decisao_alterada(self.correta, situacao="respondida", texto="Explicação pertinente."), entrada)
        self.assertEqual(falhas(mantida), {"situacao", "texto"})

    def test_selecao_entrega_trechos_reais_e_nao_adapta_o_que_nao_cabe_em_um_trecho(self):
        primeiro, segundo = self.corpus.trechos[DOC]
        entrada = self.entrada(evidencias=((DOC, PRAZO), (DOC, FRANQUIA)))
        self.assertEqual([item["fonte"] for item in entrada.saida["evidencias"]], [primeiro.id, segundo.id])
        self.assertEqual([trecho["conteudo"] for trecho in entrada.trechos], [primeiro.conteudo, segundo.conteudo])
        self.assertEqual(entrada.mantidas, [(primeiro.id, PRAZO), (segundo.id, FRANQUIA)])
        fabricada = self.entrada(evidencias=((DOC, INVENTADA),), fabricadas=frozenset({0}))
        self.assertIsNone(fabricada.erro)
        self.assertEqual(fabricada.mantidas, [])
        self.assertIn(fabricada.saida["evidencias"][0]["fonte"], {primeiro.id, segundo.id})
        cenarios = ((ENTRE_TRECHOS, frozenset(), "citacao_nao_cabe_em_um_trecho"),
                    (INVENTADA, frozenset(), "citacao_nao_esta_no_documento"),
                    (PRAZO, frozenset({0}), "citacao_fabricada_existe_no_documento"))
        for citacao, fabricadas, erro in cenarios:
            with self.subTest(erro=erro):
                inconclusiva = self.entrada(evidencias=((DOC, citacao),), fabricadas=fabricadas)
                resultado = ap.avaliar_caso(self.correta, inconclusiva)
                self.assertEqual((inconclusiva.erro, resultado.erro, resultado.conforme_ao_esperado_literal,
                                  resultado.conforme_na_apresentacao, resultado.observado),
                                 (erro, erro, False, False, None))


class LinhaDeComandoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pasta = Path(cls.enterClassContext(tempfile.TemporaryDirectory(ignore_cleanup_errors=True)))
        cls.repositorio = cls.pasta / "repositorio"
        cls.repositorio.mkdir()
        cls.com_defeito, cls.corrigido, cls.com_texto_alterado = criar_repositorio(
            cls.repositorio, (POLITICA_COM_DEFEITO, POLITICA, POLITICA_COM_TEXTO_ALTERADO))
        cls.inventario = escrever_corpus(cls.pasta / "dados")
        cls.casos = escrever_casos(cls.pasta / "casos.json", "respondida")
        cls.casos_com_recusada = escrever_casos(cls.pasta / "casos-recusada.json", "recusada")

    def relatorio(self) -> Path:
        return Path(self.enterContext(tempfile.TemporaryDirectory())) / "relatorio.json"

    def executar(self, baseline: str, candidata: str, relatorio: Path, casos: Path | None = None,
                 anteriores: tuple[Path, ...] = ()) -> tuple[int, str]:
        argumentos = ["--casos", str(casos or self.casos), "--baseline", baseline, "--candidata", candidata,
                      "--relatorio", str(relatorio), "--inventario", str(self.inventario)]
        for anterior in anteriores:
            argumentos += ["--relatorio-anterior", str(anterior)]
        saida = io.StringIO()
        with mock.patch.object(lab_comum, "RAIZ", self.repositorio), \
                contextlib.redirect_stdout(saida), contextlib.redirect_stderr(saida):
            try:
                codigo = ap.principal(argumentos)
            except SystemExit as erro_de_argumentos:
                codigo = erro_de_argumentos.code
        return codigo, saida.getvalue()

    def test_candidata_conforme_nos_dois_eixos_sai_0_mesmo_com_baseline_divergente_e_o_relatorio_nao_expoe_os_textos(self):
        relatorio = self.relatorio()
        codigo, saida = self.executar(self.com_defeito, self.corrigido, relatorio)
        self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)
        bruto = relatorio.read_text(encoding="utf-8")
        dados = json.loads(bruto)
        self.assertEqual(dados["politicas"]["baseline"]["commit"], self.com_defeito)
        self.assertEqual(dados["politicas"]["candidata"]["commit"], self.corrigido)
        self.assertEqual(dados["politicas"]["candidata"]["sha256"], lab_comum.calcular_sha256(POLITICA.encode()))
        self.assertEqual(dados["casos"]["sha256"], lab_comum.calcular_sha256(self.casos.read_bytes()))
        self.assertEqual(dados["corpus"]["documentos"][0]["sha256"], lab_comum.calcular_sha256(TEXTO_DO_DOCUMENTO.encode()))
        baseline, candidata = dados["resultados"]["baseline"], dados["resultados"]["candidata"]
        self.assertEqual((baseline["esperado_literal"]["ids_divergentes"], baseline["esperado_literal"]["verificacoes_divergentes"]),
                         (["T-02"], {"texto_livre": 1}))
        self.assertEqual((baseline["apresentacao"]["ids_divergentes"], baseline["apresentacao"]["verificacoes_divergentes"]),
                         (["T-02"], {"texto": 1}))
        self.assertEqual((candidata["esperado_literal"]["divergentes"], candidata["apresentacao"]["divergentes"]), (0, 0))
        self.assertEqual(candidata["esperado_literal"]["por_categoria"]["individual"], {"casos": 1, "conformes": 1})
        for texto in (PERGUNTA, RESPOSTA, PRAZO, FRANQUIA, INVENTADA):
            self.assertNotIn(texto, bruto)
            self.assertNotIn(texto, saida)

    def test_candidata_que_diverge_do_esperado_literal_sai_3_ainda_que_a_apresentacao_passe(self):
        relatorio = self.relatorio()
        codigo, saida = self.executar(self.com_defeito, self.corrigido, relatorio, self.casos_com_recusada)
        self.assertEqual(codigo, lab_comum.CODIGO_DIVERGENCIA, saida)
        candidata = json.loads(relatorio.read_text(encoding="utf-8"))["resultados"]["candidata"]
        self.assertEqual((candidata["esperado_literal"]["conformes"], candidata["esperado_literal"]["ids_divergentes"],
                          candidata["esperado_literal"]["verificacoes_divergentes"]), (5, ["T-02"], {"situacao": 1}))
        self.assertEqual((candidata["apresentacao"]["conformes"], candidata["apresentacao"]["divergentes"]), (6, 0))
        individual = next(item for item in candidata["por_id"] if item["id"] == "T-02")
        self.assertEqual((individual["esperado"]["situacao"], individual["observado"]["situacao"]), ("recusada", "respondida"))
        self.assertEqual((individual["conforme_ao_esperado_literal"], individual["conforme_na_apresentacao"]), (False, True))
        self.assertIn("esperado literal em 1 caso(s)", saida)

    def test_candidata_que_so_diverge_na_apresentacao_tambem_sai_3(self):
        relatorio = self.relatorio()
        codigo, saida = self.executar(self.corrigido, self.com_texto_alterado, relatorio)
        self.assertEqual(codigo, lab_comum.CODIGO_DIVERGENCIA, saida)
        candidata = json.loads(relatorio.read_text(encoding="utf-8"))["resultados"]["candidata"]
        self.assertEqual(candidata["esperado_literal"]["divergentes"], 0)
        self.assertEqual(candidata["apresentacao"]["ids_divergentes"], ["T-03"])

    def test_relatorio_anterior_com_equivalencia_e_registrado_sem_ser_alterado(self):
        anterior = self.pasta / "relatorio-anterior.json"
        anterior.write_text(json.dumps({
            "equivalencias_de_gabarito": [{"gabarito": "tipo de teste / recusada"}],
            "resultados": {"candidata": {"casos": 6, "aprovados": 6, "situacao_aceita_por_equivalencia": 1, "por_id": []}}}),
            encoding="utf-8")
        bytes_antes = anterior.read_bytes()
        relatorio = self.relatorio()
        codigo, saida = self.executar(self.com_defeito, self.corrigido, relatorio, anteriores=(anterior,))
        self.assertEqual(codigo, lab_comum.CODIGO_OK, saida)
        registro = json.loads(relatorio.read_text(encoding="utf-8"))["relatorios_anteriores"][0]
        self.assertEqual(registro["sha256"], lab_comum.calcular_sha256(bytes_antes))
        self.assertEqual(registro["equivalencias_de_gabarito"], [{"gabarito": "tipo de teste / recusada"}])
        self.assertEqual(registro["contagens"],
                         {"candidata": {"casos": 6, "aprovados": 6, "situacao_aceita_por_equivalencia": 1}})
        self.assertIn("não são contagens estritas", registro["observacao"])
        self.assertEqual(anterior.read_bytes(), bytes_antes)

    def test_erro_de_entrada_nunca_vira_aprovacao_nem_gera_relatorio(self):
        inexistente = "0123456789abcdef0123456789abcdef01234567"
        invalido = self.pasta / "invalido.json"
        invalido.write_text("{", encoding="utf-8")
        cenarios = {
            "baseline inexistente": (inexistente, self.corrigido, None),
            "candidata inexistente": (self.com_defeito, inexistente, None),
            "nome de branch em vez de hash": ("master", self.corrigido, None),
            "JSON inválido": (self.com_defeito, self.corrigido, invalido),
        }
        for nome, (baseline, candidata, casos) in cenarios.items():
            with self.subTest(nome):
                relatorio = self.relatorio()
                codigo, saida = self.executar(baseline, candidata, relatorio, casos)
                self.assertEqual(codigo, lab_comum.CODIGO_USO, saida)
                self.assertFalse(relatorio.exists())

    def test_relatorio_existente_nao_e_sobrescrito(self):
        relatorio = self.relatorio()
        relatorio.write_text("medição anterior", encoding="utf-8")
        codigo, saida = self.executar(self.com_defeito, self.corrigido, relatorio)
        self.assertEqual(codigo, lab_comum.CODIGO_USO, saida)
        self.assertEqual(relatorio.read_text(encoding="utf-8"), "medição anterior")


if __name__ == "__main__":
    unittest.main()
