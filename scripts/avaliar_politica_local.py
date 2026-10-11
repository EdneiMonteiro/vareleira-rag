"""Mede, sem Azure, o pós-processamento das políticas de resposta de dois commits (L100, Desafio 04).

Para cada caso do conjunto, o avaliador entrega à política `aplicar_politica` uma saída candidata sintética e os trechos
reais dos documentos locais que contêm as citações. A mesma entrada vai à política do commit --baseline e à do commit
--candidata, lidas com `git show` em módulos separados, sem trocar de branch nem tocar nos arquivos. Cada política é
conferida em dois eixos, contados separadamente:

  A. Esperado literal: tipo e situação iguais ao `esperado` do JSON, sem equivalência alguma, e texto livre conforme
     `esperado.texto_livre` (conservado quando verdadeiro; não retransmitido quando falso).
  B. Apresentação: o texto mostrado (o do modelo quando o texto livre é permitido; o texto fixo do programa nos demais
     casos), o aviso e as citações corretas mantidas. Não considera tipo nem situação e não é aprovação total.

Isto NÃO mede busca nem geração: a seleção já entrega ao programa o trecho que contém cada citação, e as saídas dos
modelos são sintéticas. Não acessa o Azure, o GitHub nem a web. O relatório (JSON) traz hashes, contagens por eixo, ids e
um resumo do esperado e do observado de cada caso; não traz perguntas, respostas candidatas nem citações, e um arquivo
existente nunca é sobrescrito. Meça uma vez: ajustar casos ou política depois de ver o resultado faz do conjunto um ajuste.

Saídas: 0 se todos os casos da candidata ficam conformes nos dois eixos (a baseline pode divergir), 3 se algum caso da
candidata diverge em qualquer eixo ou fica inconclusivo e 1 para erro de entrada (commit inexistente, JSON inválido,
relatório já existente...).

Exemplo:
    python scripts\\avaliar_politica_local.py --casos <casos.json> --baseline <commit> --candidata <commit> --relatorio <saida.json>
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import types
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import lab_comum
import lab_indexacao
from lab_comum import ErroLab

CAMINHO_DA_POLITICA = "scripts/lab_politica.py"
VERSAO_DO_RELATORIO = 2
PAPEIS = ("baseline", "candidata")
TEXTOS_DO_PROGRAMA = ("TEXTO_SEM_VEREDITO", "MENSAGEM_SEM_EVIDENCIA", "MENSAGEM_FORA_DE_ESCOPO", "MENSAGEM_ESCLARECIMENTO")
AVISOS_DO_PROGRAMA = ("AVISO_CONTRATACAO_INDIVIDUAL",)

ESCOPO = {
    "mede": "o que lab_politica.aplicar_politica devolve para saídas candidatas sintéticas (pós-processamento local)",
    "nao_mede": ["busca e recuperação de trechos", "geração por modelo de linguagem", "qualquer recurso do Azure"],
    "trechos": ("cada caso recebe o trecho real que contém a citação (a seleção já entrega a evidência ao programa); uma citação "
                "declarada fabricada recebe um trecho real do mesmo documento e continua inválida"),
}
CRITERIO = {
    "perfil": "estrito",
    "esperado_literal": ("tipo e situação iguais ao esperado do JSON, sem equivalências, e texto livre conforme "
                         "esperado.texto_livre (conservado quando verdadeiro; não retransmitido quando falso)"),
    "apresentacao": ("texto mostrado (o do modelo quando o texto livre é permitido; o texto fixo do programa nos demais "
                     "casos), aviso e citações corretas mantidas; não considera tipo nem situação e não é aprovação total"),
}

_PADRAO_HASH_COMPLETO = re.compile(r"[0-9a-f]{40}")
validar_commit = lab_comum.criar_validador(
    re.compile(r"[0-9a-f]{7,40}"), "O commit deve ser um hash hexadecimal em minúsculas, de 7 a 40 caracteres")


# --------------------------------------------------------------------------------------
# Casos e corpus
# --------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Caso:
    id: str
    categoria: str
    pergunta: str
    tipo_do_modelo: str
    resposta: str
    evidencias: tuple[tuple[str, str], ...]  # (id do documento, citação)
    fabricadas: frozenset[int]  # posições das evidências que o conjunto declara fabricadas
    tipo_esperado: str
    situacao_esperada: str
    texto_livre: bool


@dataclass(frozen=True)
class ConjuntoDeCasos:
    caminho: Path
    sha256: str
    casos: tuple[Caso, ...]


@dataclass(frozen=True)
class Corpus:
    documentos: tuple[lab_comum.Documento, ...]
    textos: dict[str, str]
    trechos: dict[str, list[lab_indexacao.Trecho]]


def _ler_caso(entrada: Any, indice: int, fabricadas: Mapping[str, set[int]], problemas: list[str]) -> Caso | None:
    rotulo = f"casos[{indice}]"
    if not isinstance(entrada, dict):
        problemas.append(f"{rotulo}: deve ser um objeto.")
        return None
    inicio = len(problemas)

    def texto(origem: Mapping[str, Any], chave: str, *, vazio: bool = False) -> str:
        valor = origem.get(chave)
        if not isinstance(valor, str) or not (valor.strip() or vazio):
            problemas.append(f"{rotulo}: campo '{chave}' ausente ou inválido.")
            return ""
        return valor

    identificador = texto(entrada, "id")
    rotulo = identificador or rotulo
    categoria = texto(entrada, "categoria")
    pergunta = texto(entrada, "pergunta")
    tipo_do_modelo = texto(entrada, "tipo_do_modelo")
    resposta = texto(entrada, "resposta_do_modelo", vazio=True)

    evidencias: list[tuple[str, str]] = []
    brutas = entrada.get("evidencias")
    if not isinstance(brutas, list):
        problemas.append(f"{rotulo}: 'evidencias' deve ser uma lista.")
    else:
        for bruta in brutas:
            if isinstance(bruta, dict):
                evidencias.append((texto(bruta, "documento_id"), texto(bruta, "citacao")))
            else:
                problemas.append(f"{rotulo}: cada evidência deve ser um objeto.")

    esperado = entrada.get("esperado")
    tipo_esperado = situacao_esperada = ""
    texto_livre = False
    if not isinstance(esperado, dict):
        problemas.append(f"{rotulo}: 'esperado' deve ser um objeto.")
    else:
        tipo_esperado, situacao_esperada = texto(esperado, "tipo"), texto(esperado, "situacao")
        texto_livre = esperado.get("texto_livre")
        if not isinstance(texto_livre, bool):
            problemas.append(f"{rotulo}: 'esperado.texto_livre' deve ser verdadeiro ou falso.")
            texto_livre = False

    marcadas = fabricadas.get(identificador, set())
    if any(not 0 <= posicao < len(evidencias) for posicao in marcadas):
        problemas.append(f"{rotulo}: 'origem.citacoes_fabricadas' aponta para uma evidência que não existe.")
    if len(problemas) > inicio:
        return None
    return Caso(identificador, categoria, pergunta, tipo_do_modelo, resposta, tuple(evidencias), frozenset(marcadas),
                tipo_esperado, situacao_esperada, texto_livre)


def carregar_casos(caminho: Path) -> ConjuntoDeCasos:
    """Lê e valida o conjunto de casos. O hash é o do arquivo exatamente como está no disco."""
    try:
        dados = Path(caminho).read_bytes()
    except OSError as erro:
        raise ErroLab(f"Não foi possível ler os casos ({type(erro).__name__}). Confira o caminho de --casos.") from erro
    try:
        bruto = json.loads(dados.decode("utf-8"))
    except UnicodeDecodeError:
        raise ErroLab("Os casos precisam estar codificados em UTF-8.") from None
    except json.JSONDecodeError as erro:
        raise ErroLab(f"Casos com JSON inválido (linha {erro.lineno}, coluna {erro.colno}).") from None
    if not isinstance(bruto, dict):
        raise ErroLab("Os casos precisam ser um objeto JSON.")

    problemas: list[str] = []
    if bruto.get("schema_version") != 1:
        problemas.append("'schema_version' deve ser 1.")
    if bruto.get("sintetico") is not True:
        problemas.append("Os casos precisam declarar \"sintetico\": true. Use apenas dados sintéticos.")

    fabricadas: dict[str, set[int]] = {}
    origem = bruto.get("origem")
    declaradas = origem.get("citacoes_fabricadas", []) if isinstance(origem, dict) else []
    if not isinstance(declaradas, list):
        problemas.append("'origem.citacoes_fabricadas' deve ser uma lista.")
        declaradas = []
    for item in declaradas:
        identificador = item.get("caso_id") if isinstance(item, dict) else None
        posicao = item.get("indice_evidencia") if isinstance(item, dict) else None
        if not isinstance(identificador, str) or not isinstance(posicao, int) or isinstance(posicao, bool):
            problemas.append("Cada item de 'origem.citacoes_fabricadas' precisa de 'caso_id' e 'indice_evidencia'.")
            continue
        fabricadas.setdefault(identificador, set()).add(posicao)

    entradas = bruto.get("casos")
    casos: list[Caso] = []
    if not isinstance(entradas, list) or not entradas:
        problemas.append("'casos' deve ser uma lista com pelo menos um item.")
    else:
        for indice, entrada in enumerate(entradas):
            caso = _ler_caso(entrada, indice, fabricadas, problemas)
            if caso:
                casos.append(caso)
        vistos: set[str] = set()
        for caso in casos:
            if caso.id in vistos:
                problemas.append(f"Id repetido: {caso.id}.")
            vistos.add(caso.id)
        for identificador in sorted(set(fabricadas) - vistos):
            problemas.append(f"'origem.citacoes_fabricadas' cita um caso que não existe: {identificador}.")
    if problemas:
        raise ErroLab("Casos inválidos:\n  - " + "\n  - ".join(problemas))
    return ConjuntoDeCasos(Path(caminho), lab_comum.calcular_sha256(dados), tuple(casos))


def carregar_corpus(caminho: Path) -> Corpus:
    """Confere o inventário (tamanho e hash) e divide cada documento em trechos com a função de divisão do laboratório."""
    inventario = lab_comum.carregar_e_validar(caminho)
    textos = {documento.id: lab_comum.ler_conteudo(documento).decode("utf-8") for documento in inventario.documentos}
    trechos = {documento.id: lab_indexacao.dividir_documento(documento, textos[documento.id])
               for documento in inventario.documentos}
    return Corpus(inventario.documentos, textos, trechos)


# --------------------------------------------------------------------------------------
# Políticas lidas do Git
# --------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Politica:
    papel: str
    commit: str
    sha256: str
    modulo: types.ModuleType


def _git(*argumentos: str) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(["git", *argumentos], cwd=lab_comum.RAIZ, capture_output=True, check=False)
    except OSError as erro:
        raise ErroLab(f"Não foi possível executar o git ({type(erro).__name__}). "
                      "Confirme que ele está instalado e no PATH.") from erro


def resolver_commit(valor: str) -> str:
    """Resolve o valor para o hash completo de um commit que existe; qualquer outra coisa é erro de entrada."""
    resultado = _git("rev-parse", "--verify", "--quiet", f"{valor}^{{commit}}")
    completo = resultado.stdout.decode("ascii", errors="replace").strip()
    if resultado.returncode != 0 or not _PADRAO_HASH_COMPLETO.fullmatch(completo):
        raise ErroLab(f"O commit {valor} não existe neste repositório (ou a abreviação é ambígua). "
                      "Informe o hash de um commit existente (git log --oneline).")
    return completo


def carregar_modulo(nome: str, codigo: bytes, origem: str) -> types.ModuleType:
    """Executa o código em um módulo novo. O módulo é registrado antes porque os dataclasses o procuram pelo nome."""
    modulo = types.ModuleType(nome)
    sys.modules[nome] = modulo
    try:
        exec(compile(codigo.decode("utf-8"), origem, "exec", dont_inherit=True), modulo.__dict__)
    except Exception as erro:  # noqa: BLE001 - qualquer falha ao carregar torna a política inutilizável
        sys.modules.pop(nome, None)
        raise ErroLab(f"Não foi possível carregar {origem} ({type(erro).__name__}).") from erro
    return modulo


def carregar_politica(papel: str, valor: str) -> Politica:
    commit = resolver_commit(valor)
    resultado = _git("show", f"{commit}:{CAMINHO_DA_POLITICA}")
    if resultado.returncode != 0:
        raise ErroLab(f"O commit {commit[:12]} não tem {CAMINHO_DA_POLITICA}. Informe um commit que contenha a política.")
    modulo = carregar_modulo(f"lab_politica_{papel}_{commit[:12]}", resultado.stdout, f"{commit[:12]}:{CAMINHO_DA_POLITICA}")
    return Politica(papel, commit, lab_comum.calcular_sha256(resultado.stdout), modulo)


# --------------------------------------------------------------------------------------
# Entrada de cada caso e comparação
# --------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Entrada:
    caso: Caso
    saida: dict[str, Any]  # a saída candidata, como o modelo a devolveria
    trechos: list[dict[str, Any]]  # os trechos reais entregues à política
    mantidas: list[tuple[str, str]]  # (id do trecho, citação) das citações corretas, que a política deve manter
    erro: str | None = None


@dataclass(frozen=True)
class Apresentacao:
    """O que a pessoa deve ver para o tipo e a situação esperados; fora tipo e situação, que o eixo A compara com o JSON."""

    texto: str
    aviso: str
    citacoes: list[tuple[str, str]] | None  # None: o gabarito não exige nada sobre as citações


@dataclass(frozen=True)
class Resultado:
    id: str
    categoria: str
    esperado: dict[str, Any]
    observado: dict[str, Any] | None
    esperado_literal: dict[str, bool]  # eixo A, campo a campo
    conforme_ao_esperado_literal: bool
    apresentacao: dict[str, bool]  # eixo B, verificação a verificação
    conforme_na_apresentacao: bool
    erro: str | None


def montar_entrada(caso: Caso, corpus: Corpus, normalizar: Callable[[str], str]) -> Entrada:
    """Escolhe o trecho real de cada citação. O que não dá para escolher sem adaptar o caso vira erro (inconclusivo)."""
    def com_erro(codigo: str) -> Entrada:
        return Entrada(caso, {}, [], [], codigo)

    trechos: dict[str, dict[str, Any]] = {}
    evidencias: list[dict[str, str]] = []
    mantidas: list[tuple[str, str]] = []
    for posicao, (documento_id, citacao) in enumerate(caso.evidencias):
        candidatos = corpus.trechos.get(documento_id)
        if not candidatos:
            return com_erro("documento_sem_trechos")
        procurada = normalizar(citacao)
        achados = [trecho for trecho in candidatos if procurada in normalizar(trecho.conteudo)]
        no_documento = procurada in normalizar(corpus.textos[documento_id])
        if posicao in caso.fabricadas:
            if achados or no_documento:
                return com_erro("citacao_fabricada_existe_no_documento")
            trecho = candidatos[0]  # qualquer trecho serve: a citação não está em nenhum deles
        else:
            if not achados:
                return com_erro("citacao_nao_cabe_em_um_trecho" if no_documento else "citacao_nao_esta_no_documento")
            trecho = achados[0]
            mantidas.append((trecho.id, citacao.strip()))
        trechos.setdefault(trecho.id, trecho.campos())
        evidencias.append({"fonte": trecho.id, "citacao": citacao})
    saida = {"tipo": caso.tipo_do_modelo, "resposta": caso.resposta, "evidencias": evidencias}
    return Entrada(caso, saida, list(trechos.values()), mantidas)


def esperar_apresentacao(modulo: Any, caso: Caso, mantidas: Sequence[tuple[str, str]]) -> Apresentacao | None:
    """Traduz o gabarito do caso na apresentação esperada; None quando o avaliador não tem regra para ele.

    Os textos do programa vêm das constantes do módulo avaliado: o conjunto não presume nenhum texto do programa. Esta regra
    escolhe o texto e o aviso esperados; ela não decide se tipo e situação estão certos (isso é o eixo A, literal).
    """
    tipo, situacao, livre = caso.tipo_esperado, caso.situacao_esperada, caso.texto_livre
    resposta = caso.resposta.strip()
    if situacao == modulo.DESCARTADA and not livre:
        return Apresentacao("", "", [])
    if livre and (tipo, situacao) == (modulo.DOCUMENTADA, modulo.RESPONDIDA):
        return Apresentacao(resposta, "", list(mantidas))
    if livre and (tipo, situacao) == (modulo.AMBIGUA, modulo.ESCLARECIMENTO):
        return Apresentacao(resposta, "", None)
    if livre:
        return None
    if (tipo, situacao) == (modulo.SEM_EVIDENCIA, modulo.RECUSADA):
        return Apresentacao(modulo.MENSAGEM_SEM_EVIDENCIA, "", None)
    if (tipo, situacao) == (modulo.FORA_DE_ESCOPO, modulo.RECUSADA):
        return Apresentacao(modulo.MENSAGEM_FORA_DE_ESCOPO, "", None)
    if tipo == modulo.CONTRATACAO_INDIVIDUAL and situacao in (modulo.RECUSADA, modulo.RESPONDIDA):
        return Apresentacao(modulo.TEXTO_SEM_VEREDITO, modulo.AVISO_CONTRATACAO_INDIVIDUAL, list(mantidas))
    return None


def _origem_do_texto(modulo: Any, texto: str, nomes: Sequence[str], livre: str | None = None) -> str:
    """Diz de onde veio um texto mostrado sem repeti-lo: vazio, constante do programa, texto do modelo ou outro."""
    if not texto:
        return "vazio"
    for nome in nomes:
        if texto == getattr(modulo, nome, None):
            return nome
    return "texto_do_modelo" if texto == livre else "outro"


def avaliar_caso(politica: Any, entrada: Entrada) -> Resultado:
    """Aplica a política à entrada e confere o resultado nos dois eixos: esperado literal (A) e apresentação (B)."""
    caso = entrada.caso
    esperado_resumo = {"tipo": caso.tipo_esperado, "situacao": caso.situacao_esperada, "texto_livre": caso.texto_livre,
                       "citacoes_corretas": len(entrada.mantidas)}

    def sem_comparacao(erro: str) -> Resultado:
        return Resultado(caso.id, caso.categoria, esperado_resumo, None, {}, False, {}, False, erro)

    if entrada.erro:
        return sem_comparacao(entrada.erro)
    esperada = esperar_apresentacao(politica, caso, entrada.mantidas)
    if esperada is None:
        return sem_comparacao("gabarito_sem_regra_de_apresentacao")
    try:
        decisao = politica.aplicar_politica(entrada.saida, entrada.trechos, caso.pergunta)
    except Exception as erro:  # noqa: BLE001 - uma versão que falha em um caso não pode impedir a medição dos outros
        return sem_comparacao(f"excecao_da_politica:{type(erro).__name__}")
    livre = caso.resposta.strip()
    retransmitido = bool(livre) and livre in decisao.texto
    esperado_literal = {
        "tipo": decisao.tipo == caso.tipo_esperado,
        "situacao": decisao.situacao == caso.situacao_esperada,
        "texto_livre": decisao.texto == livre if caso.texto_livre else not retransmitido,
    }
    citacoes = [(item.fonte, item.citacao) for item in decisao.evidencias]
    apresentacao = {"texto": decisao.texto == esperada.texto, "aviso": decisao.aviso == esperada.aviso}
    if esperada.citacoes is not None:
        apresentacao["citacoes"] = citacoes == esperada.citacoes
    observado = {
        "tipo": decisao.tipo,
        "situacao": decisao.situacao,
        "texto": _origem_do_texto(politica, decisao.texto, TEXTOS_DO_PROGRAMA, livre),
        "aviso": _origem_do_texto(politica, decisao.aviso, AVISOS_DO_PROGRAMA),
        "citacoes_mantidas": len(citacoes),
        "problemas": len(decisao.problemas),
    }
    return Resultado(caso.id, caso.categoria, esperado_resumo, observado, esperado_literal, all(esperado_literal.values()),
                     apresentacao, all(apresentacao.values()), None)


# --------------------------------------------------------------------------------------
# Relatório e saída
# --------------------------------------------------------------------------------------

def resumir(resultados: Sequence[Resultado]) -> dict[str, Any]:
    """Conta os dois eixos separadamente. Um caso inconclusivo diverge nos dois."""
    eixos = {"esperado_literal": ("esperado_literal", "conforme_ao_esperado_literal"),
             "apresentacao": ("apresentacao", "conforme_na_apresentacao")}
    resumo: dict[str, Any] = {"casos": len(resultados), "inconclusivos": sum(resultado.erro is not None for resultado in resultados)}
    for eixo, (verificacoes, conforme) in eixos.items():
        divergentes: Counter[str] = Counter()
        por_categoria: dict[str, dict[str, int]] = {}
        for resultado in resultados:
            parte = por_categoria.setdefault(resultado.categoria, {"casos": 0, "conformes": 0})
            parte["casos"] += 1
            parte["conformes"] += int(getattr(resultado, conforme))
            divergentes.update(nome for nome, ok in getattr(resultado, verificacoes).items() if not ok)
        conformes = sum(getattr(resultado, conforme) for resultado in resultados)
        resumo[eixo] = {
            "conformes": conformes,
            "divergentes": len(resultados) - conformes,
            "ids_divergentes": [resultado.id for resultado in resultados if not getattr(resultado, conforme)],
            "verificacoes_divergentes": dict(sorted(divergentes.items())),
            "por_categoria": por_categoria,
        }
    resumo["por_id"] = [asdict(resultado) for resultado in resultados]
    return resumo


def _caminho_no_relatorio(caminho: Path) -> str:
    """Caminho relativo à raiz do repositório, com barras normais; fora dela, só o nome do arquivo."""
    try:
        return Path(caminho).resolve().relative_to(lab_comum.RAIZ.resolve()).as_posix()
    except ValueError:
        return Path(caminho).name


def _descrever_documento(documento: lab_comum.Documento, trechos: int) -> dict[str, Any]:
    conteudo = lab_comum.ler_conteudo(documento)
    return {"id": documento.id, "arquivo": _caminho_no_relatorio(documento.arquivo),
            "sha256": lab_comum.calcular_sha256(conteudo), "tamanho_bytes": len(conteudo), "trechos": trechos}


def descrever_relatorio_anterior(caminho: Path) -> dict[str, Any]:
    """Registra, sem alterar o arquivo, uma medição anterior: nome, hash e as equivalências que ela declarava."""
    try:
        dados = Path(caminho).read_bytes()
        bruto = json.loads(dados.decode("utf-8"))
    except (OSError, ValueError) as erro:  # ValueError cobre o JSON inválido e o UTF-8 inválido
        raise ErroLab(f"Não foi possível ler o relatório anterior ({type(erro).__name__}). "
                      "Confira o caminho de --relatorio-anterior.") from erro
    if not isinstance(bruto, dict):
        raise ErroLab("O relatório anterior precisa ser um objeto JSON.")
    equivalencias = bruto.get("equivalencias_de_gabarito") or []
    resultados = bruto.get("resultados") if isinstance(bruto.get("resultados"), dict) else {}
    chaves = ("casos", "aprovados", "situacao_aceita_por_equivalencia")
    descricao: dict[str, Any] = {
        "arquivo": Path(caminho).name,
        "sha256": lab_comum.calcular_sha256(dados),
        "equivalencias_de_gabarito": equivalencias,
        "contagens": {papel: {chave: resultados[papel].get(chave) for chave in chaves}
                      for papel in PAPEIS if isinstance(resultados.get(papel), dict)},
    }
    if equivalencias:
        descricao["observacao"] = ("Relatório anterior, preservado como histórico: suas contagens aprovadas usaram as "
                                   "equivalências acima e não são contagens estritas; não as compare com as deste relatório.")
    return descricao


def montar_relatorio(conjunto: ConjuntoDeCasos, corpus: Corpus, inventario: Path, politicas: Sequence[Politica],
                     anteriores: Sequence[dict[str, Any]], resumos: Mapping[str, dict[str, Any]]) -> dict[str, Any]:
    divisao = lab_comum.normalizar_texto(Path(lab_indexacao.__file__).read_bytes())
    return {
        "schema_version": VERSAO_DO_RELATORIO,
        "escopo": ESCOPO,
        "criterio": CRITERIO,
        "casos": {
            "caminho": _caminho_no_relatorio(conjunto.caminho),
            "sha256": conjunto.sha256,
            "quantidade": len(conjunto.casos),
            "por_categoria": dict(Counter(caso.categoria for caso in conjunto.casos)),
        },
        "corpus": {
            "inventario": {"caminho": _caminho_no_relatorio(inventario),
                           "sha256": lab_comum.calcular_sha256(Path(inventario).read_bytes())},
            "divisao_em_trechos": {
                "modulo": "scripts/lab_indexacao.py",
                "sha256": lab_comum.calcular_sha256(divisao),
                "tamanho_maximo": lab_indexacao.TAMANHO_MAXIMO_PADRAO,
                "trechos": sum(len(lista) for lista in corpus.trechos.values()),
            },
            "documentos": [_descrever_documento(documento, len(corpus.trechos[documento.id]))
                           for documento in corpus.documentos],
        },
        "politicas": {
            politica.papel: {"commit": politica.commit, "arquivo": CAMINHO_DA_POLITICA, "sha256": politica.sha256}
            for politica in politicas
        },
        "relatorios_anteriores": list(anteriores),
        "resultados": dict(resumos),
    }


def gravar_relatorio(caminho: Path, relatorio: Mapping[str, Any]) -> None:
    texto = json.dumps(relatorio, ensure_ascii=False, indent=2) + "\n"
    try:
        with open(caminho, "x", encoding="utf-8", newline="\n") as arquivo:
            arquivo.write(texto)
    except FileExistsError:
        raise ErroLab(f"O relatório já existe: {caminho}. Esta medição não sobrescreve arquivos; escolha outro caminho.") from None
    except OSError as erro:
        raise ErroLab(f"Não foi possível gravar o relatório ({type(erro).__name__}). Confira o caminho e as permissões.") from erro


def _mostrar_eixo(titulo: str, eixo: str, resumos: Mapping[str, dict[str, Any]]) -> None:
    print(f"\n{titulo}")
    print(f"  {'categoria':<32} {'casos':>5} {'baseline':>9} {'candidata':>9}")
    for categoria, parte in resumos["candidata"][eixo]["por_categoria"].items():
        base = resumos["baseline"][eixo]["por_categoria"][categoria]
        print(f"  {categoria:<32} {parte['casos']:>5} {base['conformes']:>9} {parte['conformes']:>9}")
    for papel in PAPEIS:
        resumo = resumos[papel][eixo]
        linha = f"  {papel.capitalize()}: {resumo['conformes']} de {resumos[papel]['casos']} caso(s) conformes"
        if resumo["ids_divergentes"]:
            linha += f"; divergentes: {', '.join(resumo['ids_divergentes'])}"
            campos = ", ".join(f"{nome} {quantidade}" for nome, quantidade in resumo["verificacoes_divergentes"].items())
            linha += f" (verificações divergentes: {campos})" if campos else ""
        print(linha)


def mostrar_resumo(conjunto: ConjuntoDeCasos, corpus: Corpus, politicas: Sequence[Politica],
                   resumos: Mapping[str, dict[str, Any]], caminho_do_relatorio: Path) -> None:
    trechos = sum(len(lista) for lista in corpus.trechos.values())
    print("Avaliação local do pós-processamento de políticas, perfil estrito. Não usa o Azure e não mede busca nem geração: "
          "a seleção entrega a cada caso o trecho real que contém a citação.")
    print(f"Casos: {len(conjunto.casos)} (sha256 {conjunto.sha256[:12]}…) · documentos: {len(corpus.documentos)} · trechos: {trechos}")
    for politica in politicas:
        print(f"  {politica.papel:<9} commit {politica.commit[:12]} · {CAMINHO_DA_POLITICA} sha256 {politica.sha256[:12]}…")
    _mostrar_eixo("Eixo A · esperado literal: tipo, situação e texto livre iguais ao JSON, sem equivalências",
                  "esperado_literal", resumos)
    _mostrar_eixo("Eixo B · apresentação: texto, aviso e citações corretas (não é aprovação total)", "apresentacao", resumos)
    inconclusivos = {papel: resumos[papel]["inconclusivos"] for papel in PAPEIS}
    if any(inconclusivos.values()):
        print(f"\nInconclusivos (divergem nos dois eixos): baseline {inconclusivos['baseline']}, candidata {inconclusivos['candidata']}.")
    print(f"\nRelatório gravado em {caminho_do_relatorio}. Perguntas, respostas candidatas e citações não são impressas nem gravadas.")


def executar(args: argparse.Namespace) -> int:
    conjunto = carregar_casos(args.casos)
    corpus = carregar_corpus(args.inventario)
    anteriores = [descrever_relatorio_anterior(caminho) for caminho in args.anteriores]
    politicas = [carregar_politica(papel, valor) for papel, valor in zip(PAPEIS, (args.baseline, args.candidata))]
    # A seleção usa a normalização da candidata, para que os dois commits recebam exatamente os mesmos trechos.
    entradas = [montar_entrada(caso, corpus, politicas[1].modulo.normalizar) for caso in conjunto.casos]
    resultados = {politica.papel: [avaliar_caso(politica.modulo, entrada) for entrada in entradas] for politica in politicas}
    resumos = {papel: resumir(lista) for papel, lista in resultados.items()}
    gravar_relatorio(args.relatorio, montar_relatorio(conjunto, corpus, args.inventario, politicas, anteriores, resumos))
    mostrar_resumo(conjunto, corpus, politicas, resumos, args.relatorio)
    literal, apresentacao = (resumos["candidata"][eixo]["divergentes"] for eixo in ("esperado_literal", "apresentacao"))
    if literal or apresentacao:
        print(f"[FALHA] A candidata diverge do esperado literal em {literal} caso(s) e da apresentação esperada em {apresentacao} "
              "caso(s). Nenhuma equivalência foi aplicada; os casos e a política não foram alterados por este avaliador.")
        return lab_comum.CODIGO_DIVERGENCIA
    print("Todos os casos da candidata ficaram conformes ao esperado literal e à apresentação.")
    return lab_comum.CODIGO_OK


def principal(argv: list[str] | None = None) -> int:
    lab_comum.configurar_saida()
    parser = lab_comum.ParserLab(description=__doc__)
    parser.add_argument("--casos", required=True, type=Path, help="Conjunto de casos (JSON) com saídas candidatas sintéticas.")
    parser.add_argument("--baseline", required=True, type=validar_commit,
                        help="Commit com a política de referência (hash de 7 a 40 caracteres).")
    parser.add_argument("--candidata", required=True, type=validar_commit,
                        help="Commit com a política candidata (hash de 7 a 40 caracteres).")
    parser.add_argument("--relatorio", required=True, type=Path,
                        help="Onde gravar o relatório JSON. Um arquivo que já existe não é sobrescrito.")
    parser.add_argument("--relatorio-anterior", dest="anteriores", action="append", default=[], type=Path, metavar="CAMINHO",
                        help="Relatório de uma medição anterior, só para registro (o arquivo não é alterado): nome, hash e "
                             "equivalências que ele declara entram no novo relatório. Pode ser repetido.")
    parser.add_argument("--inventario", type=Path, default=lab_comum.INVENTARIO_PADRAO,
                        help="Caminho do inventário dos documentos (padrão: dados/l100/inventario.json).")
    parser.add_argument("--detalhes", action="store_true", help="Mostra o erro técnico, se houver.")
    args = parser.parse_args(argv)
    return lab_comum.executar_com_tratamento(executar, args)


if __name__ == "__main__":
    sys.exit(principal())
