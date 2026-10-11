"""Testes do avaliador de comparação do L400 (scripts/avaliar_l400.py), todos locais: transporte injetado, sem Azure e sem rede.

Os casos são genéricos e escritos aqui, só para desenvolvimento: nenhum conjunto anterior (do L100, do L200 ou final) é copiado nem lido.
Endereços, tokens e perguntas são sentinelas que não podem aparecer no console nem nos relatórios.
"""

import contextlib
import io
import json
import socket
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import support  # noqa: F401  (configura o caminho dos scripts)
import avaliar_chat as ac
import avaliar_l400 as al4
import lab_politica as lp
from support import RAIZ
from test_avaliar_chat import TOKEN, corpo_esperado, erro_503, resposta_http

HASHES_REAIS_DO_CODIGO = al4.hashes_do_codigo  # a função de produção, antes de qualquer dublê
HOST_REF = "referencia-sentinela.ambiente-ficticio.regiao-ficticia.azurecontainerapps.io"
HOST_COORD = "coordenacao-sentinela.ambiente-ficticio.regiao-ficticia.azurecontainerapps.io"
URL_REF, URL_COORD = f"https://{HOST_REF}", f"https://{HOST_COORD}"
TOKEN_REF, TOKEN_COORD = TOKEN + "-ref", TOKEN + "-coord"
VARIAVEIS = {al4.VAR_TOKEN["referencia"]: TOKEN_REF, al4.VAR_TOKEN["coordenacao"]: TOKEN_COORD}
HASHES_DO_CODIGO = {"scripts/lab_de_teste.py": {"sha256_bytes_brutos": "a" * 64, "sha256_normalizado_lf": "b" * 64},
                    "Dockerfile": {"sha256_bytes_brutos": "c" * 64, "sha256_normalizado_lf": "d" * 64}}


def caso(identificador, categoria, tipo, situacao, pergunta):
    return {"id": identificador, "categoria": categoria, "tipo_esperado": tipo, "situacao_esperada": situacao, "pergunta": pergunta,
            "justificativa": "Justificativa genérica de desenvolvimento.",
            "evidencias_referencia": [] if situacao == lp.RECUSADA else [{"documento_id": "DOC-GENERICO-1", "citacao": "Trecho genérico."}]}


CASOS = [
    caso("c-05", "geral", lp.DOCUMENTADA, lp.RESPONDIDA, "Sentinela de pergunta cinco sobre um tema genérico de desenvolvimento?"),
    caso("c-01", "individual", lp.CONTRATACAO_INDIVIDUAL, lp.RESPONDIDA, "Sentinela de pergunta um sobre um caso genérico de desenvolvimento?"),
    caso("c-04", "fora", lp.FORA_DE_ESCOPO, lp.RECUSADA, "Sentinela de pergunta quatro sobre um assunto sem relação alguma?"),
    caso("c-03", "ambigua", lp.AMBIGUA, lp.ESCLARECIMENTO, "Sentinela de pergunta três bem vaga?"),
    caso("c-02", "sem_evidencia", lp.SEM_EVIDENCIA, lp.RECUSADA, "Sentinela de pergunta dois com tema sem documento?"),
]
ORDEM_DOS_IDS = ["c-01", "c-02", "c-03", "c-04", "c-05"]
TIPO_DA_PERGUNTA = {item["pergunta"]: item["tipo_esperado"] for item in CASOS}
ID_DA_PERGUNTA = {item["pergunta"]: item["id"] for item in CASOS}


def dados_de_entrada(casos=None):
    return {"schema_version": 1, "nome": "Casos genéricos de desenvolvimento", "origem": "Escritos só para os testes do avaliador L400",
            "configuracao_avaliada": "Configuração relativa fictícia declarada pelo autor do teste",
            "casos": [json.loads(json.dumps(item)) for item in (CASOS if casos is None else casos)]}


def ok(tipo, **opcoes):
    return resposta_http(corpo_esperado(tipo, **opcoes))


class Transporte:
    """Dublê de `enviar_http`: registra cada chamada e responde conforme a estratégia (pelo endereço), a pergunta e o número da chamada."""

    def __init__(self, responder=None):
        self.chamadas = []
        self.responder = responder or (lambda estrategia, pergunta, numero: ok(TIPO_DA_PERGUNTA[pergunta]))

    def __call__(self, url, corpo, cabecalhos, timeout):
        estrategia = "referencia" if (HOST_REF in url or ":8001" in url) else "coordenacao"
        dados = json.loads(corpo.decode("utf-8"))
        self.chamadas.append({"estrategia": estrategia, "url": url, "dados": dados, "cabecalhos": dict(cabecalhos), "timeout": timeout})
        resposta = self.responder(estrategia, dados["pergunta"], len(self.chamadas))
        if isinstance(resposta, BaseException):
            raise resposta
        return resposta


class RelogioQueAvanca:
    def __init__(self, passo):
        self.agora, self.passo = 0.0, passo

    def __call__(self):
        self.agora += self.passo
        return self.agora


class BaseDoAvaliador(unittest.TestCase):
    def setUp(self):
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        self.pasta = Path(pasta.name)
        self.casos = self.pasta / "casos.json"
        self.relatorio = self.pasta / "relatorio.json"
        dubles = mock.patch.object(al4, "hashes_do_codigo", lambda: json.loads(json.dumps(HASHES_DO_CODIGO)))
        dubles.start()
        self.addCleanup(dubles.stop)

    def escrever(self, dados=None, nome="casos.json"):
        caminho = self.pasta / nome
        caminho.write_text(json.dumps(dados_de_entrada() if dados is None else dados, ensure_ascii=False, indent=1), encoding="utf-8")
        return caminho

    def rodar(self, *extras, dados=None, executar=True, simular=False, transporte=None, variaveis=None, relatorio=None, relogio=None,
              url_referencia=URL_REF, url_coordenacao=URL_COORD):
        """Roda `principal` com a rede trocada por um dublê. Devolve (código, texto impresso, transporte)."""
        self.escrever(dados)
        transporte = transporte or Transporte()
        argumentos = ["--casos", str(self.casos), "--relatorio", str(relatorio or self.relatorio)]
        if not simular:
            argumentos += ["--url-referencia", url_referencia, "--url-coordenacao", url_coordenacao, "--artefato-referencia", "imagem-l300-v1",
                           "--artefato-coordenacao", "imagem-l400-v1"]
        if executar:
            argumentos.append("--executar")
        if simular:
            argumentos.append("--simular")
        saida = io.StringIO()
        with contextlib.redirect_stdout(saida), contextlib.redirect_stderr(saida):
            try:
                codigo = al4.principal([*argumentos, *extras], env=VARIAVEIS if variaveis is None else variaveis, transporte=transporte, relogio=relogio)
            except SystemExit as erro:
                codigo = erro.code
        return codigo, saida.getvalue(), transporte

    def ler_relatorio(self, caminho=None):
        return json.loads((caminho or self.relatorio).read_text(encoding="utf-8"))


def gerar_relatorio(teste, *extras, **opcoes):
    """Roda uma comparação com o transporte dublê e devolve (código, relatório): o insumo dos testes do validador."""
    codigo, _, _ = teste.rodar(*extras, **opcoes)
    return codigo, teste.ler_relatorio(opcoes.get("relatorio"))


class PlanoTests(BaseDoAvaliador):
    def test_sem_executar_so_valida_e_mostra_o_plano_sem_rede_relatorio_nem_chamadas(self):
        transporte = Transporte()
        with mock.patch.object(socket.socket, "connect", side_effect=AssertionError("rede")):
            codigo, saida, _ = self.rodar(executar=False, transporte=transporte)
        self.assertEqual(codigo, 0, saida)
        self.assertEqual(transporte.chamadas, [])
        self.assertFalse(self.relatorio.exists())
        self.assertIn("[SIMULAÇÃO]", saida)
        for nome in ("conjunto_sha256", "plano_sha256", "codigo_sha256"):
            self.assertIn(nome, saida)
        for sentinela in (HOST_REF, HOST_COORD, TOKEN_REF, TOKEN_COORD, "Sentinela de pergunta"):
            self.assertNotIn(sentinela, saida)
        codigo, explicito, _ = self.rodar("--plano", executar=False, transporte=transporte)
        self.assertEqual((codigo, transporte.chamadas), (0, []), "--plano é o mesmo que o padrão")
        self.assertFalse(self.relatorio.exists())
        self.assertEqual(self.rodar("--plano", relatorio=self.pasta / "dois.json")[0], 1, "--plano e --executar juntos são recusados")

    def test_plano_congela_ordem_de_ids_e_estrategia_alternada_e_muda_com_o_conteudo_do_conjunto(self):
        plano = al4.construir_plano(ac.carregar_entrada(self.escrever()))
        self.assertEqual([(p.posicao, p.caso, p.estrategia) for p in plano.passos[:4]],
                         [(1, "c-01", "referencia"), (2, "c-01", "coordenacao"), (3, "c-02", "coordenacao"), (4, "c-02", "referencia")])
        self.assertEqual(len(plano.passos), 2 * len(CASOS))
        embaralhado = al4.construir_plano(ac.carregar_entrada(self.escrever(dados_de_entrada(list(reversed(CASOS))), "embaralhado.json")))
        self.assertEqual(embaralhado, plano, "a ordem do arquivo não muda o plano nem o conjunto")
        alterada = [dict(item) for item in CASOS]
        alterada[0]["pergunta"] += " Mais um detalhe?"
        outro = al4.construir_plano(ac.carregar_entrada(self.escrever(dados_de_entrada(alterada), "alterado.json")))
        self.assertNotEqual((outro.conjunto_sha256, outro.sha256), (plano.conjunto_sha256, plano.sha256))

    def test_hashes_esperados_recusam_o_que_nao_e_o_congelado_antes_de_qualquer_chamada(self):
        plano = al4.construir_plano(ac.carregar_entrada(self.escrever()))
        for opcao, valor in (("--plano-esperado", "0" * 64), ("--conjunto-esperado", "0" * 64), ("--codigo-esperado", "0" * 64),
                             ("--plano-esperado", "xyz")):
            transporte = Transporte()
            codigo, saida, _ = self.rodar(opcao, valor, transporte=transporte)
            self.assertEqual(codigo, 1, (opcao, saida))
            self.assertEqual(transporte.chamadas, [], "nada é enviado")
            self.assertFalse(self.relatorio.exists())
        codigo, saida, _ = self.rodar("--plano-esperado", plano.sha256, "--conjunto-esperado", plano.conjunto_sha256, "--codigo-esperado",
                                      al4.hash_do_codigo(HASHES_DO_CODIGO))
        self.assertEqual(codigo, 0, saida)
        self.assertEqual(self.ler_relatorio()["plano"]["hashes_esperados_conferidos"], {"conjunto": True, "plano": True, "codigo": True})

    def test_casos_nao_podem_estar_em_avaliacoes_finais_corpus_nem_contexto_da_imagem(self):
        grupos = {"avaliações finais": ("dados/l100/avaliacao/x.json", "dados/l100/avaliacao-independente/x.json", "dados/l200/avaliacao/x.json"),
                  "build da imagem": ("dados/l300/documentos/x.json", "dados/l100/documentos/x.json", "scripts/x.json", "web/x.json")}
        for trecho, relativos in grupos.items():
            for relativo in relativos:
                with self.assertRaises(al4.ErroLab, msg=relativo) as contexto:
                    al4.validar_caminho_dos_casos(RAIZ / relativo)
                self.assertIn(trecho, str(contexto.exception), relativo)
        self.assertEqual(al4.validar_caminho_dos_casos(self.casos), self.casos.resolve(), "uma pasta fora do repositório é aceita")
        novo = RAIZ / "dados" / "l400" / "avaliacao" / "conjunto-novo.json"
        self.assertEqual(al4.validar_caminho_dos_casos(novo), novo.resolve(), "o conjunto novo do L400 tem onde ficar")
        saida = io.StringIO()
        with contextlib.redirect_stdout(saida), contextlib.redirect_stderr(saida):
            codigo = al4.principal(["--casos", str(RAIZ / "dados" / "l200" / "avaliacao" / "nao-existe.json"), "--relatorio", str(self.relatorio)], env={})
        self.assertEqual(codigo, 1)
        self.assertIn("avaliações finais", saida.getvalue(), "recusado antes de tentar abrir o arquivo")


class DestinosETokensTests(BaseDoAvaliador):
    def test_tokens_vem_so_do_ambiente_vao_so_no_cabecalho_https_e_nunca_aparecem_na_saida_nem_no_relatorio(self):
        codigo, saida, transporte = self.rodar()
        self.assertEqual(codigo, 0, saida)
        for chamada in transporte.chamadas:
            esperado = TOKEN_REF if chamada["estrategia"] == "referencia" else TOKEN_COORD
            self.assertEqual(chamada["cabecalhos"]["Authorization"], f"Bearer {esperado}")
        texto = saida + self.relatorio.read_text(encoding="utf-8")
        for sentinela in (TOKEN_REF, TOKEN_COORD, HOST_REF, HOST_COORD):
            self.assertNotIn(sentinela, texto)
        self.assertFalse([opcao for acao in al4.criar_parser()._actions for opcao in acao.option_strings if "token" in opcao],
                         "não existe opção para informar token")

    def test_sem_token_com_https_a_execucao_nem_comeca_e_o_loopback_nunca_envia_credencial(self):
        for variaveis in ({}, {al4.VAR_TOKEN["referencia"]: TOKEN_REF}, {**VARIAVEIS, al4.VAR_TOKEN["coordenacao"]: "curto demais"}):
            transporte = Transporte()
            codigo, saida, _ = self.rodar(variaveis=variaveis, transporte=transporte)
            self.assertEqual(codigo, 1, saida)
            self.assertEqual(transporte.chamadas, [])
            self.assertFalse(self.relatorio.exists())
            self.assertNotIn("curto demais", saida)
        codigo, saida, transporte = self.rodar(variaveis={}, url_referencia="http://127.0.0.1:8001", url_coordenacao="http://127.0.0.1:8002")
        self.assertEqual(codigo, 0, saida)
        self.assertEqual(len(transporte.chamadas), 2 * len(CASOS))
        self.assertTrue(all("Authorization" not in chamada["cabecalhos"] for chamada in transporte.chamadas))
        self.assertEqual(self.ler_relatorio()["destinos"]["referencia"]["modo"], "demonstracao_ou_local_loopback")

    def test_destinos_so_https_do_container_apps_ou_loopback_e_diferentes_entre_si(self):
        invalidos = (("http://exemplo.azurecontainerapps.io", URL_COORD), ("https://dominio-proprio.exemplo.com", URL_COORD),
                     (f"https://usuario@{HOST_REF}", URL_COORD), (f"{URL_REF}/api", URL_COORD), (URL_REF, URL_REF))
        for referencia, coordenacao in invalidos:
            transporte = Transporte()
            codigo, saida, _ = self.rodar(url_referencia=referencia, url_coordenacao=coordenacao, transporte=transporte)
            self.assertEqual(codigo, 1, (referencia, coordenacao))
            self.assertEqual(transporte.chamadas, [])
            self.assertNotIn(HOST_REF, saida, "o endereço recusado não é repetido")
        saida = io.StringIO()
        with contextlib.redirect_stdout(saida), contextlib.redirect_stderr(saida):
            self.escrever()
            codigo = al4.principal(["--casos", str(self.casos), "--relatorio", str(self.relatorio), "--url-referencia", URL_REF, "--executar"], env=VARIAVEIS)
        self.assertEqual(codigo, 1, "o endereço da outra aplicação também é recebido explicitamente")
        for artefato in ("latest", "imagem com espaço", "sha256:curto", "https://exemplo/imagem:v1"):
            self.assertRaises(al4.ErroLab, al4.validar_artefato, artefato, "--artefato-coordenacao")
        self.assertEqual(al4.validar_artefato("sha256:" + "e" * 64, "--artefato-referencia"), "sha256:" + "e" * 64)

    def test_redirecionamento_conta_como_falha_e_o_transporte_padrao_e_o_do_avaliador_de_chat(self):
        def responder(estrategia, pergunta, numero):
            return resposta_http(b"", 302, "text/html") if estrategia == "coordenacao" else ok(TIPO_DA_PERGUNTA[pergunta])

        codigo, _, transporte = self.rodar(transporte=Transporte(responder))
        self.assertEqual(codigo, 3)
        self.assertEqual(len(transporte.chamadas), 2 * len(CASOS), "o redirecionamento não é seguido: nenhuma chamada extra")
        resumo = self.ler_relatorio()["estrategias"]["coordenacao"]["resumo"]
        self.assertEqual((resumo["falhas_http"], resumo["erros_por_rotulo"]), (len(CASOS), {"redirecionamento": len(CASOS)}))
        falso = Transporte()
        self.escrever()
        with mock.patch.object(ac, "enviar_http", falso), contextlib.redirect_stdout(io.StringIO()):
            codigo = al4.principal(["--casos", str(self.casos), "--relatorio", str(self.pasta / "outro.json"), "--url-referencia", URL_REF,
                                    "--url-coordenacao", URL_COORD, "--artefato-referencia", "v1", "--artefato-coordenacao", "v2", "--executar"],
                                   env=VARIAVEIS)
        self.assertEqual((codigo, len(falso.chamadas)), (0, 2 * len(CASOS)), "sem transporte injetado, vale o do avaliar_chat (sem redirecionamento)")


class ExecucaoTests(BaseDoAvaliador):
    def test_uma_chamada_por_estrategia_e_caso_na_ordem_congelada_com_o_mesmo_corpo_e_sem_repetir(self):
        codigo, saida, transporte = self.rodar()
        self.assertEqual(codigo, 0, saida)
        self.assertEqual(len(transporte.chamadas), 2 * len(CASOS))
        plano = al4.construir_plano(ac.carregar_entrada(self.casos))
        self.assertEqual([(ID_DA_PERGUNTA[c["dados"]["pergunta"]], c["estrategia"]) for c in transporte.chamadas], [(p.caso, p.estrategia) for p in plano.passos])
        por_pergunta = {}
        for chamada in transporte.chamadas:
            por_pergunta.setdefault(chamada["dados"]["pergunta"], []).append(chamada)

        def sem_token(chamada):
            return {nome: valor for nome, valor in chamada["cabecalhos"].items() if nome != "Authorization"}

        for chamadas in por_pergunta.values():
            ref, coord = sorted(chamadas, key=lambda c: c["estrategia"] == "coordenacao")
            self.assertEqual(ref["dados"], coord["dados"], "o corpo é idêntico: o cliente não escolhe a estratégia")
            self.assertEqual(set(ref["dados"]), {"pergunta"})
            self.assertEqual(sem_token(ref), sem_token(coord))
        relatorio = self.ler_relatorio()
        comparacao = relatorio["comparacao"]
        self.assertEqual((comparacao["ganhos"], comparacao["perdas"], comparacao["ambos_aprovados"]), (0, 0, len(CASOS)))
        self.assertEqual([c["id"] for c in relatorio["estrategias"]["referencia"]["casos"]], ORDEM_DOS_IDS)

    def test_falhas_429_503_timeout_json_invalido_e_divergencia_contam_no_denominador(self):
        def responder(estrategia, pergunta, numero):
            identificador, certa = ID_DA_PERGUNTA[pergunta], ok(TIPO_DA_PERGUNTA[pergunta])
            if estrategia == "referencia":
                return {"c-02": resposta_http(b'{"erro": "ocupado"}', 429), "c-03": ac.FalhaDeTransporte("tempo_esgotado")}.get(identificador, certa)
            return {"c-01": erro_503(), "c-04": resposta_http(b"isto nao e json"), "c-05": ok(lp.FORA_DE_ESCOPO)}.get(identificador, certa)

        codigo, saida, _ = self.rodar(transporte=Transporte(responder))
        self.assertEqual(codigo, 3, saida)
        relatorio = self.ler_relatorio()
        ref, coord = (relatorio["estrategias"][nome]["resumo"] for nome in ("referencia", "coordenacao"))
        self.assertEqual((ref["aprovados"], ref["falhas_http"], ref["erros"], ref["taxa_de_aprovacao"]), (3, 1, 1, 0.6), "o denominador é 5, não 3")
        self.assertEqual((ref["codigos_http"], ref["erros_por_rotulo"], ref["erros_do_chat"]),
                         ({"200": 3, "429": 1}, {"http_429": 1, "tempo_esgotado": 1}, {"ocupado": 1}))
        self.assertEqual((coord["aprovados"], coord["falhas_http"], coord["erros"], coord["divergentes"], coord["taxa_de_aprovacao"]), (2, 1, 1, 1, 0.4))
        self.assertEqual((coord["erros_do_chat"], coord["erros_por_rotulo"]), ({"resposta_nao_verificada": 1}, {"http_503": 1, "json_invalido": 1}))
        comparacao = relatorio["comparacao"]
        self.assertEqual((comparacao["ganhos"], comparacao["perdas"], comparacao["saldo"]), (2, 3, -1))
        self.assertEqual((comparacao["ids_dos_ganhos"], comparacao["ids_das_perdas"]), (["c-02", "c-03"], ["c-01", "c-04", "c-05"]))

    def test_tres_falhas_seguidas_de_uma_estrategia_interrompem_so_ela_e_o_resto_vira_nao_avaliado(self):
        def responder(estrategia, pergunta, numero):
            return ac.FalhaDeTransporte("conexao") if estrategia == "coordenacao" else ok(TIPO_DA_PERGUNTA[pergunta])

        codigo, saida, transporte = self.rodar(transporte=Transporte(responder))
        self.assertEqual(codigo, 3)
        relatorio = self.ler_relatorio()
        coord = relatorio["estrategias"]["coordenacao"]["resumo"]
        self.assertEqual((relatorio["status"], coord["erros"], coord["nao_avaliados"], coord["taxa_de_aprovacao"]), ("interrompido", 3, 2, 0.0))
        self.assertEqual(relatorio["interrupcao"]["motivo_por_estrategia"], {"coordenacao": "falhas_de_transporte"})
        self.assertEqual(sum(1 for c in transporte.chamadas if c["estrategia"] == "coordenacao"), 3, "nenhuma chamada depois da terceira falha")
        self.assertEqual(relatorio["estrategias"]["referencia"]["resumo"]["aprovados"], len(CASOS))

    def test_tempo_maximo_interrompe_as_chamadas_futuras_e_os_casos_que_sobram_contam_como_falha(self):
        codigo, saida, transporte = self.rodar(relogio=RelogioQueAvanca(500))
        self.assertEqual(codigo, 3, saida)
        relatorio = self.ler_relatorio()
        self.assertEqual((relatorio["status"], relatorio["interrupcao"]["motivo_global"]), ("interrompido", al4.TEMPO_MAXIMO_EXCEDIDO))
        enviados = len(transporte.chamadas)
        self.assertLess(enviados, 2 * len(CASOS))
        self.assertEqual(sum(r["resumo"]["nao_avaliados"] for r in relatorio["estrategias"].values()), 2 * len(CASOS) - enviados)
        for estrategia in al4.ESTRATEGIAS:
            resumo = relatorio["estrategias"][estrategia]["resumo"]
            self.assertEqual(resumo["taxa_de_aprovacao"], round(resumo["aprovados"] / len(CASOS), 4), "o denominador continua sendo o total planejado")

    def test_acesso_recusado_sai_com_2_e_cancelamento_e_defeito_ainda_gravam_o_relatorio(self):
        codigo, saida, _ = self.rodar(transporte=Transporte(lambda e, p, n: resposta_http(b'{"erro": "nao_autorizado"}', 403)))
        self.assertEqual(codigo, 2, saida)
        relatorio = self.ler_relatorio()
        self.assertEqual(relatorio["interrupcao"]["motivo_por_estrategia"], {"referencia": "acesso_recusado", "coordenacao": "acesso_recusado"})
        self.assertEqual(relatorio["estrategias"]["referencia"]["resumo"]["erros_do_chat"], {"nao_autorizado": 3})
        for excecao, esperado, motivo in ((KeyboardInterrupt, 3, "cancelado"), (RuntimeError, 4, "defeito_do_avaliador")):
            def responder(estrategia, pergunta, numero, excecao=excecao):
                if numero == 2:
                    raise excecao("texto-secreto-da-excecao")
                return ok(TIPO_DA_PERGUNTA[pergunta])

            novo = self.pasta / f"{motivo}.json"
            codigo, saida, _ = self.rodar(transporte=Transporte(responder), relatorio=novo)
            self.assertEqual(codigo, esperado, saida)
            gravado = self.ler_relatorio(novo)
            self.assertEqual((gravado["status"], gravado["interrupcao"]["motivo_global"]), ("interrompido", motivo))
            self.assertEqual(sum(r["resumo"]["nao_avaliados"] for r in gravado["estrategias"].values()), 2 * len(CASOS) - 1)
            self.assertNotIn("texto-secreto-da-excecao", saida + novo.read_text(encoding="utf-8"), "a mensagem da exceção não é repetida")


class UsoECustoTests(BaseDoAvaliador):
    def test_uso_desconhecido_fica_null_e_nunca_vira_zero_nem_total_completo(self):
        codigo, _, _ = self.rodar(transporte=Transporte(lambda e, p, n: ok(TIPO_DA_PERGUNTA[p], uso=None)))
        self.assertEqual(codigo, 0)
        relatorio = self.ler_relatorio()
        for estrategia in al4.ESTRATEGIAS:
            uso = relatorio["estrategias"][estrategia]["resumo"]["uso_de_tokens"]
            self.assertEqual((uso["soma_do_uso_informado"], uso["respostas_com_uso_informado"], uso["chamadas_sem_uso_informado"]), (None, 0, len(CASOS)))
            self.assertTrue(all(item["tokens"] is None for item in relatorio["estrategias"][estrategia]["casos"]))
        self.assertIsNone(relatorio["comparacao"]["delta_dos_tokens"])

        def parcial(estrategia, pergunta, numero):
            desconhecido = estrategia == "coordenacao" and ID_DA_PERGUNTA[pergunta] == "c-03"
            return ok(TIPO_DA_PERGUNTA[pergunta], uso=None if desconhecido else (10, 100, 20, 0))

        self.rodar(transporte=Transporte(parcial), relatorio=self.pasta / "parcial.json")
        relatorio = self.ler_relatorio(self.pasta / "parcial.json")
        coord = relatorio["estrategias"]["coordenacao"]["resumo"]["uso_de_tokens"]
        self.assertEqual((coord["respostas_com_uso_informado"], coord["chamadas_sem_uso_informado"], coord["soma_do_uso_informado"]["tokens_entrada"]), (4, 1, 400))
        self.assertIsNone(relatorio["comparacao"]["delta_dos_tokens"], "um lado com uso desconhecido não gera diferença")

    def test_custo_usa_so_precos_informados_finitos_e_nao_negativos_e_o_uso_informado(self):
        precos = {"--preco-entrada-1m": "2", "--preco-saida-1m": "8.5", "--preco-embeddings-1m": "0.5", "--moeda": "BRL"}
        codigo, saida, _ = self.rodar(*[item for par in precos.items() for item in par])
        self.assertEqual(codigo, 0, saida)
        relatorio = self.ler_relatorio()
        self.assertEqual(relatorio["custos"]["regime"], "precos_informados_pelo_operador")
        self.assertEqual(relatorio["custos"]["precos_por_1m_de_tokens"], {"entrada": 2.0, "saida": 8.5, "embeddings": 0.5})
        esperado = round((5 * 1 * 0.5 + 5 * 2 * 2 + 5 * 3 * 8.5) / 1_000_000, 6)  # 5 chamadas com uso (1, 2, 3, 4) cada
        self.assertEqual(relatorio["estrategias"]["referencia"]["resumo"]["custo"], {"estimado_com_o_uso_informado": esperado, "parcial": False})
        self.assertEqual(relatorio["comparacao"]["delta_do_custo_estimado"], 0.0)
        for invalido in ("nan", "inf", "-1", "1e3", "abc", "1_0", ""):
            conjunto = {**precos, "--preco-entrada-1m": invalido}
            transporte = Transporte()
            codigo, _, _ = self.rodar(*[item for par in conjunto.items() for item in par], transporte=transporte, relatorio=self.pasta / "x.json")
            self.assertEqual(codigo, 1, invalido)
            self.assertEqual(transporte.chamadas, [])
        for incompleta in (("--preco-entrada-1m", "1"), ("--moeda", "USD"), ("--preco-entrada-1m", "1", "--preco-saida-1m", "1", "--preco-embeddings-1m", "1")):
            self.assertEqual(self.rodar(*incompleta, relatorio=self.pasta / "y.json")[0], 1, incompleta)
        padroes = [acao.default for acao in al4.criar_parser()._actions if acao.dest.startswith("preco_") or acao.dest == "moeda"]
        self.assertEqual(padroes, [None, None, None, None], "nenhum preço (nem moeda) existe no programa")


class RelatorioTests(BaseDoAvaliador):
    def test_relatorio_nao_guarda_pergunta_corpo_endereco_nem_token_e_traz_hashes_e_origem(self):
        codigo, saida, _ = self.rodar()
        self.assertEqual(codigo, 0, saida)
        texto = self.relatorio.read_text(encoding="utf-8")
        relatorio = json.loads(texto)
        for sentinela in (*(item["pergunta"] for item in CASOS), HOST_REF, HOST_COORD, TOKEN_REF, TOKEN_COORD, "Resposta fictícia", "https://", "Bearer"):
            self.assertNotIn(sentinela, texto)
        self.assertEqual(set(relatorio), al4.CHAVES_DO_RELATORIO)
        self.assertEqual((relatorio["relatorio"], relatorio["status"], relatorio["simulado"]), ("comparacao_l400", "concluido", False))
        self.assertEqual(relatorio["artefatos"]["coordenacao"], {"origem_declarada": "imagem-l400-v1", "verificada_pelo_avaliador": False})
        self.assertEqual((relatorio["codigo_avaliado"], relatorio["codigo_sha256"]), (HASHES_DO_CODIGO, al4.hash_do_codigo(HASHES_DO_CODIGO)))
        entrada = relatorio["entrada"]
        hashes = ac.hashes_do_conteudo(self.casos.read_bytes())
        self.assertEqual((entrada["sha256_bytes_brutos"], entrada["sha256_normalizado_lf"]), (hashes["sha256_bytes_brutos"], hashes["sha256_normalizado_lf"]))
        self.assertEqual(entrada["conjunto_sha256"], al4.hash_do_conjunto(ac.carregar_entrada(self.casos)))
        self.assertEqual(relatorio["destinos"], {e: {"modo": "hospedado_https"} for e in al4.ESTRATEGIAS})
        self.assertIn("conjunto_sha256", " ".join(relatorio["interpretacao"]["nao_permite"]), "o relatório diz que outro conjunto não é comparável")

    def test_relatorio_e_reservado_antes_da_rede_e_nunca_sobrescreve(self):
        self.relatorio.write_text("conteúdo anterior", encoding="utf-8")
        transporte = Transporte()
        codigo, saida, _ = self.rodar(transporte=transporte)
        self.assertEqual((codigo, transporte.chamadas), (1, []))
        self.assertEqual(self.relatorio.read_text(encoding="utf-8"), "conteúdo anterior")
        self.relatorio.unlink()
        vistos = []

        def espiar(estrategia, pergunta, numero):
            vistos.append(self.ler_relatorio())
            return ok(TIPO_DA_PERGUNTA[pergunta])

        self.rodar(transporte=Transporte(espiar))
        self.assertEqual(vistos[0]["status"], "em_andamento", "o arquivo já existia, com o marcador, antes da primeira chamada")
        self.assertEqual(self.rodar(relatorio=self.pasta / "inexistente" / "r.json")[0], 1, "a pasta precisa existir")

    def test_ensaio_simulado_nao_usa_rede_nem_credenciais_e_fica_marcado(self):
        def proibido(*argumentos, **opcoes):
            raise AssertionError("o ensaio tentou usar a rede")

        transporte = Transporte(proibido)
        with mock.patch.object(socket.socket, "connect", proibido), mock.patch.object(ac, "enviar_http", proibido):
            codigo, saida, _ = self.rodar(executar=False, simular=True, variaveis={}, transporte=transporte)
        self.assertEqual((codigo, transporte.chamadas), (0, []), saida)
        relatorio = self.ler_relatorio()
        self.assertTrue(relatorio["simulado"])
        self.assertEqual(relatorio["destinos"], {e: {"modo": "simulado_sem_rede"} for e in al4.ESTRATEGIAS})
        self.assertIn("ENSAIO", " ".join(relatorio["avisos"]))
        self.assertEqual(self.rodar("--simular", relatorio=self.pasta / "dois.json")[0], 1, "--executar e --simular juntos são recusados")

    def test_hash_do_codigo_cobre_os_modulos_da_imagem_e_o_dockerfile(self):
        hashes = HASHES_REAIS_DO_CODIGO()
        self.assertEqual(set(hashes) - {"Dockerfile"}, {f"scripts/{nome}" for nome in ac.ARQUIVOS_DO_CODIGO})
        self.assertEqual(al4.hash_do_codigo(hashes), al4.hash_do_codigo(json.loads(json.dumps(hashes))))
        alterado = json.loads(json.dumps(hashes))
        alterado["Dockerfile"]["sha256_normalizado_lf"] = "f" * 64
        self.assertNotEqual(al4.hash_do_codigo(alterado), al4.hash_do_codigo(hashes), "mudar o Dockerfile muda o hash do código avaliado")


if __name__ == "__main__":
    unittest.main()
