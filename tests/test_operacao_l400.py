"""Testes da operação offline do L400 (scripts/operar_l400.py), todos locais: sem Azure, sem GitHub e sem rede.

Os identificadores e nomes de ambiente são sentinelas sorteadas a cada execução: o que importa é que nenhuma delas apareça no console nem
nos relatórios. Os relatórios de comparação vêm do avaliador (com transporte dublê) e os conjuntos de casos são genéricos, só de desenvolvimento.
"""

import contextlib
import copy
import io
import json
import socket
import subprocess
import unittest
import uuid
from pathlib import Path
from unittest import mock

import support  # noqa: F401  (configura o caminho dos scripts)
import avaliar_l400 as al4
import operar_l400 as op
from lab_comum import CODIGO_DIVERGENCIA, CODIGO_OK, CODIGO_USO, ErroLab
from test_avaliacao_l400 import CASOS, ID_DA_PERGUNTA, TIPO_DA_PERGUNTA, BaseDoAvaliador, Transporte, ok, gerar_relatorio, resposta_http
from test_infra_l200 import localizar_bicep


def executar(*argumentos: str, env: dict | None = None) -> tuple[int, str]:
    """Roda a linha de comando com um ambiente isolado e devolve (código de saída, tudo o que foi impresso)."""
    saida = io.StringIO()
    with contextlib.redirect_stdout(saida), contextlib.redirect_stderr(saida):
        try:
            codigo = op.principal(list(argumentos), env={} if env is None else env)
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


class ComPasta(unittest.TestCase):
    def setUp(self):
        import tempfile

        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        self.pasta = Path(pasta.name)

    def escrever(self, dados, nome="arquivo.json") -> Path:
        caminho = self.pasta / nome
        caminho.write_text(dados if isinstance(dados, str) else json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
        return caminho

    def arquivos(self) -> list[str]:
        return sorted(item.name for item in self.pasta.iterdir())


class PlanoTests(ComPasta):
    def test_plano_e_declarativo_sem_rede_com_passos_de_vocabulario_fechado_e_nao_cria_arquivo_sem_pedir(self):
        with sem_rede():
            codigo, saida = executar("--etapa", "planejar", "--formato", "json")
        self.assertEqual(codigo, CODIGO_OK, saida)
        plano = json.loads(saida)
        self.assertEqual(plano["nuvem"], {"chamadas": 0, "executa": False})
        self.assertEqual([passo["passo"] for passo in plano["passos"]],
                         ["contingencia", "indice-candidato", "conferir-migracao", "aplicacao", "comparar", "promover-indice", "retornar-indice",
                          "carga-interrupcao", "limpeza"])
        for passo in plano["passos"]:
            self.assertIn(passo["executor"], plano["executores"], passo["passo"])
            self.assertTrue(passo["objetivo"] and isinstance(passo["nuvem"], bool), passo["passo"])
            for chave in ("cria", "reutiliza", "altera", "custo", "efeito_na_migracao", "precondicoes", "portoes", "variaveis", "comandos", "limpeza"):
                self.assertIsInstance(passo[chave], list, f"{passo['passo']}.{chave}")
        offline = next(passo for passo in plano["passos"] if passo["passo"] == "conferir-migracao")
        self.assertEqual((offline["executor"], offline["nuvem"]), ("offline", False))
        self.assertIn("--dimensoes 768", " ".join(next(p for p in plano["passos"] if p["passo"] == "indice-candidato")["comandos"]))
        self.assertEqual(self.arquivos(), [], "sem --relatorio, nada é gravado")
        self.assertEqual(executar("--etapa", "planejar", "--passo", "inexistente")[0], CODIGO_USO)
        codigo, saida = executar("--etapa", "planejar", "--passo", "limpeza")
        self.assertEqual(codigo, CODIGO_OK)
        self.assertIn("nenhum script deste nível apaga recursos", saida)

    def test_plano_mostra_so_nomes_de_variaveis_nunca_valores_e_o_relatorio_nunca_sobrescreve(self):
        sentinelas = {nome: f"sentinela-{uuid.uuid4().hex}" for nome in op.VARIAVEIS_DO_BICEPPARAM}
        relatorio = self.pasta / "plano.json"
        with sem_rede():
            codigo, saida = executar("--etapa", "planejar", "--relatorio", str(relatorio), env=sentinelas)
        self.assertEqual(codigo, CODIGO_OK, saida)
        texto = saida + relatorio.read_text(encoding="utf-8")
        for nome, valor in sentinelas.items():
            self.assertIn(nome, texto)
            self.assertNotIn(valor, texto, f"o valor de {nome} nunca é repetido")
        antes = relatorio.read_bytes()
        codigo, saida = executar("--etapa", "planejar", "--relatorio", str(relatorio))
        self.assertEqual(codigo, CODIGO_USO)
        self.assertEqual(relatorio.read_bytes(), antes, "o relatório existente não foi tocado")
        self.assertEqual(executar("--etapa", "planejar", "--relatorio", str(self.pasta / "sem-pasta" / "x.json"))[0], CODIGO_USO)
        self.assertEqual(executar("--etapa", "planejar", "--relatorio", str(self.pasta / "nome ruim.json"))[0], CODIGO_USO)

    @unittest.skipUnless(localizar_bicep(), "Bicep CLI não encontrado: a compilação não foi conferida")
    def test_validar_bicep_compila_o_l400_e_exige_lint_sem_avisos(self):
        codigo, saida = executar("--etapa", "planejar", "--passo", "limpeza", "--validar-bicep")
        self.assertEqual(codigo, CODIGO_OK, saida)
        self.assertIn("infra/l400.bicep compila", saida)
        self.assertNotIn("l300.bicep", saida)


def descritor(acao="promover", origem="operador"):
    """Descritor de promoção ou de retorno, montado a partir do manifesto real do L300 (só ids, classes e hashes de conteúdo)."""
    fontes = [dict(fonte) for fonte in op.fontes_do_manifesto()]
    por_documento = {fonte["documento_id"]: 4 for fonte in fontes}
    manifesto = {"embeddings": {"deployment": "embeddings", "modelo": "text-embedding-3-small", "versao": "1"},
                 "geracao_principal": {"deployment": "geracao", "modelo": "modelo-de-teste", "versao": "2000-01-01"},
                 "geracao_contingencia": {"deployment": "geracao-contingencia", "modelo": "modelo-de-teste", "versao": "2000-01-01"}}

    def indice(nome, dimensoes, antes):
        return {"indice": nome, "dimensoes": dimensoes, "modelo_embeddings": "text-embedding-3-small", "versao_modelo_embeddings": "1",
                "origem_observada": origem, "fontes": copy.deepcopy(fontes),
                "contagem_antes": {"por_documento": dict(por_documento)} if antes else None,
                "contagem_depois": {"por_documento": dict(por_documento)}}

    referencia, candidato = indice(op.INDICE_REFERENCIA, 1536, True), indice(op.INDICE_CANDIDATO, 768, False)
    atual, alvo = (referencia, candidato) if acao == "promover" else (candidato, referencia)

    def configuracao(item):
        return {"indice": item["indice"], "dimensoes": item["dimensoes"], "deployment_embeddings": "embeddings"}

    return {"versao": 1, "origem": origem, "acao": acao, "manifesto_deployment": manifesto, "configuracao_atual": configuracao(atual),
            "configuracao_alvo": configuracao(alvo), "indices": {"referencia": referencia, "candidato": candidato}}


def reprovados(dados):
    resultado = op.conferir_migracao(dados, op.fontes_do_manifesto())
    return {item["id"] for item in resultado["verificacoes"] if item["estado"] == "reprovado"}


class MigracaoTests(ComPasta):
    def test_promocao_e_retorno_validos_sao_aprovados_e_nunca_geram_evidencia_de_azure(self):
        for acao in op.ACOES:
            resultado = op.conferir_migracao(descritor(acao), op.fontes_do_manifesto())
            self.assertEqual((resultado["resultado"], resultado["acao"], resultado["evidencia_azure"]), ("aprovado", acao, False), acao)
            self.assertEqual(resultado["contagem"], {"atendido": 10, "reprovado": 0})
            hashes = resultado["hashes_das_fontes_e_classes"]
            self.assertEqual(hashes["esperado"], hashes["referencia"])
            self.assertEqual(hashes["esperado"], hashes["candidato"])
            self.assertEqual(resultado["totais_de_trechos"], {"referencia_antes": 16, "referencia_depois": 16, "candidato_depois": 16})
            self.assertIn("NÃO prova que os vetores são compatíveis", resultado["limite"])
        simulado = op.conferir_migracao(descritor(origem="simulado"), op.fontes_do_manifesto())
        self.assertEqual((simulado["resultado"], simulado["origem_do_descritor"]), ("aprovado", "simulado"))
        self.assertIn("SIMULADO", " ".join(simulado["avisos"]))

    def test_mesmo_indice_fora_do_namespace_ou_referencia_trocada_e_reprovado(self):
        casos = {"mesmo indice": lambda d: d["indices"]["candidato"].update(indice=op.INDICE_REFERENCIA),
                 "indice do L200": lambda d: d["indices"]["candidato"].update(indice="vareleira-lar-l200"),
                 "fora do namespace": lambda d: d["indices"]["candidato"].update(indice="indice-qualquer"),
                 "referencia que nao e a do L300": lambda d: d["indices"]["referencia"].update(indice="vareleira-lar-l300-outro")}
        for nome, alterar in casos.items():
            dados = descritor()
            alterar(dados)
            self.assertIn("indices.namespace_e_nomes_distintos", reprovados(dados), nome)

    def test_trocar_a_configuracao_nao_prova_compatibilidade_de_dimensoes_modelo_ou_deployment(self):
        casos = {
            "dimensoes da configuracao diferentes das observadas": (lambda d: d["configuracao_alvo"].update(dimensoes=1536), "configuracao.igual_ao_indice_observado"),
            "indice observado com outras dimensoes": (lambda d: d["indices"]["candidato"].update(dimensoes=1024), "configuracao.igual_ao_indice_observado"),
            "indice construido com outro modelo": (lambda d: d["indices"]["candidato"].update(modelo_embeddings="text-embedding-3-large"), "manifesto.embeddings_iguais_nos_indices"),
            "indice construido com outra versao": (lambda d: d["indices"]["candidato"].update(versao_modelo_embeddings="2"), "manifesto.embeddings_iguais_nos_indices"),
            "deployment de embeddings da configuracao": (lambda d: d["configuracao_alvo"].update(deployment_embeddings="outro"), "manifesto.embeddings_iguais_nos_indices"),
            "dimensoes acima do limite do modelo": (lambda d: (d["indices"]["candidato"].update(dimensoes=2000), d["configuracao_alvo"].update(dimensoes=2000)), "dimensoes.cabem_no_modelo"),
            "modelo sem limite conhecido": (lambda d: d["manifesto_deployment"]["embeddings"].update(modelo="modelo-desconhecido"), "dimensoes.cabem_no_modelo"),
            "contingencia com outro modelo": (lambda d: d["manifesto_deployment"]["geracao_contingencia"].update(modelo="outro-modelo"), "manifesto.contingencia_distinta_com_mesmo_modelo"),
            "contingencia com o nome do principal": (lambda d: d["manifesto_deployment"]["geracao_contingencia"].update(deployment="geracao"), "manifesto.contingencia_distinta_com_mesmo_modelo"),
        }
        for nome, (alterar, esperado) in casos.items():
            dados = descritor()
            alterar(dados)
            self.assertIn(esperado, reprovados(dados), nome)

    def test_fontes_classes_e_contagens_precisam_ser_as_aprovadas_iguais_e_suficientes(self):
        def trocar_hash(dados):
            dados["indices"]["candidato"]["fontes"][0]["sha256"] = "0" * 64

        def trocar_classe(dados):
            dados["indices"]["candidato"]["fontes"][0]["classe"] = "corretor"

        def tirar_fonte(dados):
            dados["indices"]["candidato"]["fontes"].pop()
            dados["indices"]["candidato"]["contagem_depois"]["por_documento"].popitem()

        def contagem_zero(dados):
            primeiro = next(iter(dados["indices"]["candidato"]["contagem_depois"]["por_documento"]))
            dados["indices"]["candidato"]["contagem_depois"]["por_documento"][primeiro] = 0

        def contagem_diferente(dados):
            primeiro = next(iter(dados["indices"]["candidato"]["contagem_depois"]["por_documento"]))
            dados["indices"]["candidato"]["contagem_depois"]["por_documento"][primeiro] += 1

        def referencia_mudou(dados):
            primeiro = next(iter(dados["indices"]["referencia"]["contagem_depois"]["por_documento"]))
            dados["indices"]["referencia"]["contagem_depois"]["por_documento"][primeiro] -= 1

        def fonte_a_mais(dados):
            for chave in ("referencia", "candidato"):
                dados["indices"][chave]["fontes"].append({"documento_id": "VLAR-NOVO-1.0", "classe": "compartilhado", "sha256": "1" * 64})
                dados["indices"][chave]["contagem_depois"]["por_documento"]["VLAR-NOVO-1.0"] = 1

        casos = {"hash de conteudo": (trocar_hash, "fontes.mesmas_do_manifesto"), "classe de acesso": (trocar_classe, "fontes.mesmas_do_manifesto"),
                 "fonte faltando": (tirar_fonte, "fontes.mesmas_do_manifesto"), "fonte nao aprovada": (fonte_a_mais, "fontes.mesmas_do_manifesto"),
                 "contagem zero": (contagem_zero, "contagens.candidato_igual_a_referencia"),
                 "contagem diferente da referencia": (contagem_diferente, "contagens.candidato_igual_a_referencia"),
                 "referencia modificada": (referencia_mudou, "contagens.referencia_preservada")}
        for nome, (alterar, esperado) in casos.items():
            dados = descritor()
            alterar(dados)
            self.assertIn(esperado, reprovados(dados), nome)

    def test_origem_e_acao_precisam_ser_coerentes_com_o_que_foi_observado(self):
        dados = descritor()
        dados["indices"]["candidato"]["origem_observada"] = "simulado"
        self.assertIn("origem.explicita", reprovados(dados), "observação simulada em descritor do operador")
        dados = descritor()
        dados["configuracao_atual"], dados["configuracao_alvo"] = dados["configuracao_alvo"], dados["configuracao_atual"]
        self.assertIn("acao.coerente", reprovados(dados), "promover partindo do candidato")
        dados = descritor("retornar")
        dados["acao"] = "promover"
        self.assertIn("acao.coerente", reprovados(dados))

    def test_dados_ausentes_ou_incompletos_sao_recusados_sem_valor_padrao_nem_eco_de_valores(self):
        sentinela = f"sentinela-{uuid.uuid4().hex}"

        def faltando(*caminho):
            def alterar(dados):
                for chave in caminho[:-1]:
                    dados = dados[chave]
                del dados[caminho[-1]]
            return alterar

        casos = [faltando("origem"), faltando("acao"), faltando("manifesto_deployment", "embeddings"), faltando("configuracao_alvo", "dimensoes"),
                 faltando("indices", "candidato"), faltando("indices", "referencia", "contagem_antes"),
                 faltando("indices", "referencia", "origem_observada"), faltando("indices", "candidato", "fontes"),
                 lambda d: d.update({sentinela: 1}), lambda d: d["indices"]["candidato"].update(dimensoes="768"),
                 lambda d: d["indices"]["candidato"].update(dimensoes=True), lambda d: d.update(versao=2),
                 lambda d: d["indices"]["referencia"]["contagem_antes"].update(por_documento={}),
                 lambda d: d["indices"]["referencia"]["contagem_depois"]["por_documento"].update({"VLAR-CG-1.0": -1}),
                 lambda d: d["indices"]["candidato"]["fontes"].append(dict(d["indices"]["candidato"]["fontes"][0])),
                 lambda d: d["indices"]["candidato"].update(origem_observada="talvez"), lambda d: d.update(origem=None)]
        for posicao, alterar in enumerate(casos):
            dados = descritor()
            alterar(dados)
            with self.assertRaises(ErroLab, msg=posicao) as contexto:
                op.conferir_migracao(dados, op.fontes_do_manifesto())
            self.assertEqual(contexto.exception.codigo, CODIGO_USO)
            self.assertNotIn(sentinela, str(contexto.exception), "nenhum valor é repetido")
        with self.assertRaises(ErroLab):
            op.conferir_migracao([], op.fontes_do_manifesto())

    def test_linha_de_comando_aprova_reprova_e_recusa_sem_rede_e_nunca_sobrescreve_o_relatorio(self):
        arquivo, relatorio = self.escrever(descritor()), self.pasta / "migracao.json"
        with sem_rede():
            codigo, saida = executar("--etapa", "conferir-migracao", "--descritor", str(arquivo), "--relatorio", str(relatorio))
        self.assertEqual(codigo, CODIGO_OK, saida)
        gravado = json.loads(relatorio.read_text(encoding="utf-8"))
        self.assertEqual((gravado["resultado"], gravado["evidencia_azure"], gravado["origem_do_descritor"]), ("aprovado", False, "operador"))
        self.assertEqual(executar("--etapa", "conferir-migracao", "--descritor", str(arquivo), "--relatorio", str(relatorio))[0], CODIGO_USO)
        reprovado = descritor()
        reprovado["indices"]["candidato"]["indice"] = op.INDICE_REFERENCIA
        codigo, saida = executar("--etapa", "conferir-migracao", "--descritor", str(self.escrever(reprovado, "ruim.json")), "--relatorio", str(self.pasta / "ruim-rel.json"))
        self.assertEqual(codigo, CODIGO_DIVERGENCIA, saida)
        self.assertEqual(json.loads((self.pasta / "ruim-rel.json").read_text(encoding="utf-8"))["resultado"], "reprovado", "o reprovado também fica registrado")
        incompleto = descritor()
        del incompleto["origem"]
        codigo, saida = executar("--etapa", "conferir-migracao", "--descritor", str(self.escrever(incompleto, "incompleto.json")), "--relatorio", str(self.pasta / "inc-rel.json"))
        self.assertEqual(codigo, CODIGO_USO, saida)
        self.assertFalse((self.pasta / "inc-rel.json").exists())
        self.assertEqual(executar("--etapa", "conferir-migracao")[0], CODIGO_USO, "sem descritor não há conferência")
        self.assertEqual(executar("--etapa", "conferir-migracao", "--descritor", str(self.escrever("não é json", "x.json")))[0], CODIGO_USO)


def what_if(*mudancas):
    base = "/subscriptions/{0}/resourceGroups/rg-sentinela/providers/Microsoft.CognitiveServices/accounts/ais-sentinela/deployments/{1}"
    return {"status": "Succeeded", "changes": [{"changeType": tipo, "resourceId": base.format(uuid.uuid4(), nome), "delta": []} for tipo, nome in mudancas]}


class WhatIfETLogsTests(ComPasta):
    def test_whatif_sanitizado_bloqueia_exclusao_nao_repete_nomes_e_o_rotulo_padrao_e_a_fase_do_l400(self):
        relatorio = self.pasta / "whatif.json"
        codigo, saida = executar("--etapa", "sanitizar-whatif", "--arquivo", str(self.escrever(what_if(("Create", "geracao-contingencia")))), "--relatorio", str(relatorio),
                                 env={op.VAR_FASE: "contingencia"})
        self.assertEqual(codigo, CODIGO_OK, saida)
        gravado = json.loads(relatorio.read_text(encoding="utf-8"))
        self.assertEqual((gravado["rotulo"], gravado["por_mudanca"]["Create"]), ("contingencia", 1))
        self.assertNotIn("sentinela", saida + relatorio.read_text(encoding="utf-8"))
        codigo, saida = executar("--etapa", "sanitizar-whatif", "--arquivo", str(self.escrever(what_if(("Delete", "geracao")), "exclui.json")),
                                 "--relatorio", str(self.pasta / "exclui-rel.json"))
        self.assertEqual(codigo, CODIGO_DIVERGENCIA, "uma exclusão nunca é esperada")
        self.assertNotIn("sentinela", saida)
        self.assertEqual(executar("--etapa", "sanitizar-whatif", "--arquivo", str(self.pasta / "exclui.json"))[0], CODIGO_USO, "o relatório é obrigatório")

    def test_resumo_de_logs_conta_os_eventos_da_coordenacao_e_falha_fechado_diante_de_linha_desconhecida(self):
        tempo = "2026-01-01 10:00:0{},001 INFO vareleira.chat "
        # As linhas de partida são as que o chat escreve de verdade: o texto exato, sem trecho livre.
        acesso = ("Acesso documental ativo: os papéis de aplicação da identidade definem as classes de documento da busca, e quem não tem papel "
                  "reconhecido recebe 403 antes de qualquer consulta.")
        coordenacao = ("Coordenação L400 ativa: planejamento, recuperação filtrada, verificação e redação com limites finitos; contingência de geração "
                       "{}configurada; progresso por eventos em POST /api/perguntar/progresso.")
        linhas = [acesso, coordenacao.format(""), coordenacao.format("não "),
                  tempo.format(1) + "requisicao id=abc12345 rota=perguntar status=200 ms=1200",
                  tempo.format(2) + "coordenacao id=abc12345 resultado=concluido chamadas=5 buscas=1 contingencia=nao uso_incerto=nao", "",
                  tempo.format(3) + "requisicao id=def67890 rota=progresso status=499 ms=300 causa=cancelado",
                  tempo.format(4) + "coordenacao id=def67890 resultado=cancelado chamadas=2 buscas=1 contingencia=sim uso_incerto=sim"]
        relatorio = self.pasta / "logs.json"
        with sem_rede():
            codigo, saida = executar("--etapa", "resumir-logs", "--logs", str(self.escrever("\n".join(linhas), "logs.txt")), "--relatorio", str(relatorio))
        self.assertEqual(codigo, CODIGO_OK, saida)
        resumo = json.loads(relatorio.read_text(encoding="utf-8"))
        self.assertEqual(resumo["coordenacao"], {"eventos": 2, "por_resultado": {"concluido": 1, "erro": 0, "cancelado": 1}, "com_contingencia": 1,
                                                 "com_uso_incerto": 1, "chamadas_total": 7, "buscas_total": 2})
        self.assertEqual((resumo["linhas"]["total"], resumo["linhas"]["vazias"], resumo["linhas"]["desconhecidas"]), (8, 1, 0))
        self.assertEqual(resumo["linhas"]["ignoradas_conhecidas"], {"coordenacao": 2, "partida": 3})
        self.assertEqual(resumo["por_rota"]["progresso"]["status"], {"499": 1})
        self.assertEqual(resumo["causas_por_status"], {"499": {"cancelado": 1}})
        ruins = (tempo.format(5) + "coordenacao id=x1234567 resultado=sucesso chamadas=1 buscas=1 contingencia=nao uso_incerto=nao",
                 "Pergunta sentinela: qual é a cobertura do meu caso?",
                 acesso + " sentinela",
                 coordenacao.format("").replace("configurada", "sentinela"),
                 "Coordenação L400 ativa: sentinela https://exemplo.invalid/?token=abc")
        for indice, ruim in enumerate(ruins):
            codigo, saida = executar("--etapa", "resumir-logs", "--logs", str(self.escrever("\n".join([*linhas, ruim]), "ruim.txt")),
                                     "--relatorio", str(self.pasta / f"ruim-{indice}.json"))
            self.assertEqual(codigo, CODIGO_DIVERGENCIA, f"a linha desconhecida derruba o resultado: {indice}")
            self.assertNotIn("sentinela", saida)
            self.assertNotIn("sentinela", "".join(p.read_text(encoding="utf-8") for p in self.pasta.glob("ruim-*.json")))


class ComparacaoTests(BaseDoAvaliador):
    """O validador lê o relatório que o avaliador gera de verdade (transporte dublê), e o que for adulterado é recusado."""

    def valido(self, *extras, **opcoes):
        codigo, relatorio = gerar_relatorio(self, *extras, **opcoes)
        return relatorio

    def verificar(self, relatorio, **esperados):
        resultado = op.validar_comparacao(relatorio, **esperados)
        return resultado, {item["id"] for item in resultado["verificacoes"] if item["estado"] == "reprovado"}

    def test_relatorio_do_avaliador_passa_com_os_hashes_congelados_e_avisa_quando_o_congelamento_nao_foi_comprovado(self):
        relatorio = self.valido()
        resultado, falhas = self.verificar(relatorio, conjunto_esperado=relatorio["entrada"]["conjunto_sha256"], plano_esperado=relatorio["plano"]["sha256"],
                                           codigo_esperado=relatorio["codigo_sha256"])
        self.assertEqual((resultado["resultado"], falhas, resultado["avisos"], resultado["evidencia_azure"]), ("valido_completo", set(), [], False))
        sem_hashes, _ = self.verificar(relatorio)
        self.assertEqual(sem_hashes["resultado"], "valido_completo")
        self.assertIn("congelamento não foi comprovado", " ".join(sem_hashes["avisos"]))
        congelado = self.valido("--plano-esperado", relatorio["plano"]["sha256"], "--conjunto-esperado", relatorio["entrada"]["conjunto_sha256"],
                                "--codigo-esperado", relatorio["codigo_sha256"], relatorio=self.pasta / "congelado.json")
        self.assertEqual(self.verificar(congelado)[0]["avisos"], [], "o próprio avaliador já conferiu os três hashes")

    def test_hashes_esperados_diferentes_tornam_o_relatorio_nao_comparavel(self):
        relatorio = self.valido()
        for nome in ("conjunto_esperado", "plano_esperado", "codigo_esperado"):
            resultado, falhas = self.verificar(relatorio, **{nome: "0" * 64})
            self.assertEqual(resultado["resultado"], "invalido", nome)
            self.assertEqual(len(falhas), 1, nome)
            self.assertIn("não comparável", json.dumps(resultado, ensure_ascii=False))
        with self.assertRaises(ErroLab):
            op.validar_comparacao(relatorio, conjunto_esperado="não é um hash")

    def test_relatorio_adulterado_e_recusado_em_cada_invariante(self):
        def sem_denominador(r):
            resumo = r["estrategias"]["referencia"]["resumo"]
            resumo["taxa_de_aprovacao"] = round(resumo["aprovados"] / (resumo["casos_planejados"] - resumo["falhas_http"] - resumo["erros"]), 4)

        def uso_zero(r):
            r["estrategias"]["coordenacao"]["resumo"]["uso_de_tokens"]["soma_do_uso_informado"] = dict.fromkeys(
                ("tokens_embeddings", "tokens_entrada", "tokens_saida", "tokens_raciocinio"), 0)

        def mudar(*caminho, valor):
            def alterar(r):
                for chave in caminho[:-1]:
                    r = r[chave]
                r[caminho[-1]] = valor
            return alterar

        def tirar_caso(r):
            r["estrategias"]["coordenacao"]["casos"].pop()

        def com_pergunta(r):
            r["estrategias"]["referencia"]["casos"][0]["pergunta"] = "Qual é a cobertura?"

        def com_endereco(r):
            r["avisos"].append("destino https://exemplo.azurecontainerapps.io/api")

        def com_token(r):
            r["avisos"].append("cabeçalho Bearer abcdefghijklmnop")

        def campo_novo(r):
            r["corpo_bruto"] = "..."

        def sem_aviso(r):
            r["interpretacao"]["nao_permite"] = r["interpretacao"]["nao_permite"][1:]

        def preco_negativo(r):
            r["custos"].update(regime="precos_informados_pelo_operador", moeda="USD", precos_por_1m_de_tokens={"entrada": -1, "saida": 1, "embeddings": 1})

        def l200(r):
            r["relatorio"] = "avaliacao_http_do_chat"

        def com_falhas(estrategia, pergunta, numero):
            if estrategia == "referencia" and ID_DA_PERGUNTA[pergunta] == "c-02":
                return resposta_http(b'{"erro": "ocupado"}', 429)
            return ok(TIPO_DA_PERGUNTA[pergunta])

        casos = {"denominador sem os descartes": (sem_denominador, "denominador"),
                 "ganhos adulterados": (mudar("comparacao", "ganhos", valor=3), "ganho_e_perda"),
                 "conjuntos diferentes entre as estratégias": (tirar_caso, "mesmo_conjunto_e_plano"), "pergunta no relatório": (com_pergunta, "sem_conteudo_bruto"),
                 "endereço no relatório": (com_endereco, "sem_conteudo_bruto"), "token no relatório": (com_token, "sem_conteudo_bruto"),
                 "campo fora do esquema": (campo_novo, "tipo_e_campos"), "hash do código adulterado": (mudar("codigo_sha256", valor="9" * 64), "hashes"),
                 "leitura permitida alterada": (sem_aviso, "interpretacao"), "preço negativo": (preco_negativo, "custos"),
                 "artefato verificado pelo avaliador": (mudar("artefatos", "referencia", "verificada_pelo_avaliador", valor=True), "artefatos"),
                 "relatório do L200": (l200, "tipo_e_campos")}
        base = self.valido(transporte=Transporte(com_falhas))
        self.assertEqual(self.verificar(base)[0]["resultado"], "valido_completo", "falhas contam como falha, mas o relatório completo é válido")
        for nome, (alterar, esperado) in casos.items():
            relatorio = copy.deepcopy(base)
            alterar(relatorio)
            resultado, falhas = self.verificar(relatorio)
            self.assertEqual(resultado["resultado"], "invalido", nome)
            self.assertIn(esperado, falhas, nome)
        sem_uso = self.valido(transporte=Transporte(lambda e, p, n: ok(TIPO_DA_PERGUNTA[p], uso=None)), relatorio=self.pasta / "sem-uso.json")
        self.assertEqual(self.verificar(sem_uso)[0]["resultado"], "valido_completo", "uso desconhecido é null e o relatório é válido")
        uso_zero(sem_uso)
        resultado, falhas = self.verificar(sem_uso)
        self.assertEqual((resultado["resultado"], "uso_de_tokens" in falhas), ("invalido", True), "uso desconhecido tratado como zero")
        resultado, _ = self.verificar(l200_com(base))
        self.assertIn("L200", json.dumps(resultado, ensure_ascii=False), "o relatório do L200 não é reinterpretado como L400")
        self.assertEqual(op.validar_comparacao("lixo")["resultado"], "invalido")
        self.assertEqual(op.validar_comparacao({})["resultado"], "invalido")

    def test_ensaio_interrupcao_e_destino_local_nao_valem_como_comparacao_completa(self):
        simulado = self.valido(executar=False, simular=True, variaveis={}, relatorio=self.pasta / "ensaio.json")
        self.assertEqual(self.verificar(simulado)[0]["resultado"], "ensaio_simulado")
        interrompido = self.valido(transporte=Transporte(lambda e, p, n: al4.ac.FalhaDeTransporte("conexao") if e == "coordenacao" else ok(TIPO_DA_PERGUNTA[p])),
                                   relatorio=self.pasta / "interrompido.json")
        resultado, falhas = self.verificar(interrompido)
        self.assertEqual((resultado["resultado"], falhas), ("valido_incompleto", set()), "falhas e não avaliados contam como falha: o relatório é válido, mas incompleto")
        local = self.valido(variaveis={}, url_referencia="http://127.0.0.1:8001", url_coordenacao="http://127.0.0.1:8002", relatorio=self.pasta / "local.json")
        self.assertEqual(self.verificar(local)[0]["resultado"], "valido_incompleto")

    def test_linha_de_comando_valida_o_relatorio_em_arquivo_sem_rede_e_nunca_sobrescreve_o_resultado(self):
        relatorio = self.valido()
        arquivo, saida_do_validador = self.pasta / "comparacao.json", self.pasta / "validacao.json"
        arquivo.write_text(json.dumps(relatorio), encoding="utf-8")
        argumentos = ("--etapa", "validar-comparacao", "--comparacao", str(arquivo), "--conjunto-esperado", relatorio["entrada"]["conjunto_sha256"],
                      "--plano-avaliacao-esperado", relatorio["plano"]["sha256"], "--codigo-esperado", relatorio["codigo_sha256"])
        with sem_rede():
            codigo, saida = executar(*argumentos, "--relatorio", str(saida_do_validador))
        self.assertEqual(codigo, CODIGO_OK, saida)
        self.assertEqual(json.loads(saida_do_validador.read_text(encoding="utf-8"))["resultado"], "valido_completo")
        self.assertEqual(executar(*argumentos, "--relatorio", str(saida_do_validador))[0], CODIGO_USO, "o resultado existente não é sobrescrito")
        relatorio["comparacao"]["perdas"] += 1
        arquivo.write_text(json.dumps(relatorio), encoding="utf-8")
        codigo, saida = executar("--etapa", "validar-comparacao", "--comparacao", str(arquivo))
        self.assertEqual(codigo, CODIGO_DIVERGENCIA, saida)
        self.assertIn("[reprovado] ganho_e_perda", saida)
        self.assertEqual(executar("--etapa", "validar-comparacao")[0], CODIGO_USO)


def l200_com(relatorio):
    copia = copy.deepcopy(relatorio)
    copia["relatorio"] = "avaliacao_http_do_chat"
    return copia


if __name__ == "__main__":
    unittest.main()
