"""Monta, OFFLINE, o contexto de build da imagem da sonda do L300 (modelos em infra/sonda-l300) em uma pasta própria.

Por que uma pasta própria. O Dockerfile e o .dockerignore da RAIZ do repositório são do chat: o teste do chat exige que a lista de
permissão deles seja exatamente o que o Dockerfile do chat copia, e a sonda não pode entrar lá. Na rodada Azure, um `az acr build`
com o contexto errado selecionou o Dockerfile da raiz, e a imagem "da sonda" saiu como a do chat. Aqui o contexto é uma pasta NOVA, montada
em separado, com só a lista fechada de arquivos da sonda e o Dockerfile dela; o comando de build aponta para essa pasta.

O que a pasta recebe (e nada além disto):
    scripts/sonda_l300.py; o gerador de carga do L400 (scripts/gerar_carga_l400.py), que a sonda não chama e que roda dentro da rede por
        substituição de comando (--command e --args) no início do Job; e a ferramenta de ingestão do L300 com os módulos que ela importa
        e o chat não tem (gerenciar_ingestao_l300, gerenciar_ingestao, lab_ingestao e lab_ingestao_l300);
    dados/l100/inventario.json e os três documentos sintéticos aprovados do L100;
    dados/l300/permissoes-documentais.json e o roteiro operacional sintético aprovado do L300;
    Dockerfile e .dockerignore (lista de permissão), gravados a partir de infra/sonda-l300/Dockerfile e infra/sonda-l300/dockerignore,
        com fins de linha LF. O .dockerignore da raiz do repositório não é tocado nem copiado.
São 12 arquivos da lista fechada, mais o Dockerfile e o .dockerignore. O ENTRYPOINT da imagem continua sendo a sonda.
Os módulos do chat (lab_comum, lab_acesso, lab_indexacao, lab_geracao, lab_politica, lab_chat e lab_orquestracao) NÃO são copiados: na
imagem eles vêm da base, a imagem do chat, informada no build por IMAGEM_CHAT.

O que confere. Antes de criar qualquer arquivo: os modelos (a lista de COPY do Dockerfile e a lista de permissão são exatamente a
lista fechada), o manifesto e o inventário (declaram só os documentos da lista) e cada origem (existe, é um arquivo comum, está dentro do
repositório). Depois: cada arquivo copiado tem o mesmo SHA-256 da origem, e a pasta tem exatamente os arquivos esperados. Se algo falhar,
o que foi criado é retirado. A pasta de destino precisa ser nova ou estar vazia: o montador RECUSA uma pasta com conteúdo.

Não usa rede, Azure, Docker nem az: só lê o repositório (os arquivos da lista fechada e os dois modelos) e grava na pasta indicada, que
precisa ser nova ou vazia. O build em si é um passo separado, que ALTERA o Azure
(envia o contexto e cria uma imagem no registro, com custo de execução do build e de armazenamento da imagem): o comando de referência
é só impresso, em PowerShell, e exige destinos e autorização seus. Limpeza: apague a pasta do contexto quando o build terminar (ela só
tem cópias); a imagem no registro é retirada pelo roteiro de limpeza do desafio, não por este script.

Código de saída: 0 montado; 1 uso, pasta de destino inválida ou erro ao gravar; 3 o repositório não confere (origem ausente, modelo
diferente da lista fechada, hash diferente depois da cópia); 4 defeito.

Exemplos:
    python scripts\\montar_contexto_sonda_l300.py --destino ..\\contexto-sonda-l300
    python scripts\\montar_contexto_sonda_l300.py --destino ..\\contexto-sonda-l300 --registro <registro> `
        --imagem-chat <registro>.azurecr.io/<repositorio-do-chat>:<tag-do-chat> --imagem-sonda <repositorio-da-sonda>:<tag-nova>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path

import lab_comum
from lab_comum import CODIGO_DIVERGENCIA, CODIGO_INESPERADO, CODIGO_OK, CODIGO_USO, ErroLab

RAIZ = lab_comum.RAIZ
PASTA_DOS_MODELOS = RAIZ / "infra" / "sonda-l300"
MODELO_DO_DOCKERFILE = PASTA_DOS_MODELOS / "Dockerfile"
MODELO_DA_LISTA = PASTA_DOS_MODELOS / "dockerignore"
DOCKERFILE, DOCKERIGNORE = "Dockerfile", ".dockerignore"

# A lista FECHADA: só estes arquivos do repositório entram no contexto (os caminhos são os do repositório e os da imagem).
ARQUIVOS = (
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
EXCLUSOES_FINAIS_OBRIGATORIAS = ("**/.env", "**/.env.*", "**/*.pem", "**/*.key", ".git", ".venv", "context.md", "session-state")

_PADRAO_REGISTRO = re.compile(r"[a-z0-9]{5,50}")
_PADRAO_REPOSITORIO = r"[a-z0-9]+(?:[._-][a-z0-9]+)*(?:/[a-z0-9]+(?:[._-][a-z0-9]+)*)*"
_PADRAO_TAG = r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}"
_PADRAO_IMAGEM_DO_CHAT = re.compile(r"([a-z0-9]{5,50})\.azurecr\.io/" + _PADRAO_REPOSITORIO + r"(?::" + _PADRAO_TAG + r"|@sha256:[0-9a-f]{64})")
_PADRAO_IMAGEM_DA_SONDA = re.compile(_PADRAO_REPOSITORIO + r":(" + _PADRAO_TAG + ")")

validar_registro = lab_comum.criar_validador(_PADRAO_REGISTRO, "O registro deve ter de 5 a 50 caracteres: letras minúsculas e números")


def validar_imagem_do_chat(valor: str) -> str:
    if not _PADRAO_IMAGEM_DO_CHAT.fullmatch(valor):
        raise argparse.ArgumentTypeError(
            f"A imagem do chat deve ser <registro>.azurecr.io/<repositório>:<tag> (ou @sha256:<digest>) (recebido: {valor!r}).")
    return valor


def validar_imagem_da_sonda(valor: str) -> str:
    achado = _PADRAO_IMAGEM_DA_SONDA.fullmatch(valor)
    if achado is None or achado.group(1) == "latest":
        raise argparse.ArgumentTypeError(
            f"A imagem da sonda deve ser <repositório>:<tag-nova>, com uma tag identificável e nunca latest (recebido: {valor!r}).")
    return valor


@dataclass(frozen=True)
class Copiado:
    relativo: str
    tamanho: int
    sha256: str


# --------------------------------------------------------------------------------------
# Modelos: o Dockerfile e a lista de permissão precisam ser exatamente a lista fechada
# --------------------------------------------------------------------------------------

def instrucoes_do_dockerfile(texto: str) -> list[tuple[str, str]]:
    """As instruções (nome, argumentos) de um Dockerfile, sem comentários e com as continuações (\\) juntadas."""
    instrucoes, atual = [], ""
    for linha in texto.splitlines():
        if not atual and (not linha.strip() or linha.lstrip().startswith("#")):
            continue
        continua = linha.rstrip().endswith("\\")
        atual += (linha.rstrip()[:-1] if continua else linha.rstrip()) + " "
        if not continua:
            instrucoes.append(atual.strip())
            atual = ""
    return [(item.split(None, 1)[0].upper(), item.split(None, 1)[1] if " " in item else "") for item in instrucoes]


def origens_copiadas(texto_do_dockerfile: str) -> list[str]:
    origens: list[str] = []
    for nome, argumentos in instrucoes_do_dockerfile(texto_do_dockerfile):
        if nome == "COPY":
            origens.extend([parte for parte in shlex.split(argumentos) if not parte.startswith("--")][:-1])
    return origens


def regras_do_dockerignore(texto: str) -> list[str]:
    return [linha.strip() for linha in texto.splitlines() if linha.strip() and not linha.lstrip().startswith("#")]


def conferir_modelos(texto_do_dockerfile: str, texto_da_lista: str) -> None:
    """Falha se o modelo do Dockerfile ou da lista de permissão não for exatamente a lista fechada e as proteções finais."""
    problemas: list[str] = []
    origens = origens_copiadas(texto_do_dockerfile)
    if len(origens) != len(set(origens)) or set(origens) != set(ARQUIVOS):
        problemas.append("os COPY do Dockerfile não são exatamente a lista fechada de arquivos do montador")
    instrucoes = instrucoes_do_dockerfile(texto_do_dockerfile)
    if instrucoes[:2] != [("ARG", "IMAGEM_CHAT"), ("FROM", "${IMAGEM_CHAT}")]:
        problemas.append("o Dockerfile precisa começar por ARG IMAGEM_CHAT (sem valor padrão) e FROM ${IMAGEM_CHAT}")
    usuarios = [argumentos for nome, argumentos in instrucoes if nome == "USER"]
    if len(usuarios) != 1 or not usuarios[0].split(":")[0].isdigit() or int(usuarios[0].split(":")[0]) == 0:
        problemas.append("o Dockerfile precisa de um único USER numérico diferente de root")
    regras = regras_do_dockerignore(texto_da_lista)
    permissoes = [regra[1:] for regra in regras if regra.startswith("!")]
    if not regras or regras[0] != "**" or len(permissoes) != len(set(permissoes)) or set(permissoes) != {*ARQUIVOS, DOCKERFILE}:
        problemas.append("a lista de permissão não é exatamente '**' mais os arquivos da lista fechada e o Dockerfile")
    else:
        finais = regras[max(i for i, regra in enumerate(regras) if regra.startswith("!")) + 1:]
        if any(regra.startswith("!") for regra in finais) or not set(EXCLUSOES_FINAIS_OBRIGATORIAS) <= set(finais):
            problemas.append("as exclusões finais de segredos, Git e sessões estão incompletas ou antes das permissões")
    if problemas:
        raise ErroLab("Os modelos em infra/sonda-l300 não conferem (nada foi criado):\n  - " + "\n  - ".join(problemas), CODIGO_DIVERGENCIA)


def conferir_documentos_declarados() -> None:
    """O manifesto L300 e o inventário L100 declaram só os documentos da lista: um documento novo exige revisar a lista fechada."""
    try:
        manifesto = json.loads((RAIZ / "dados" / "l300" / "permissoes-documentais.json").read_text(encoding="utf-8"))
        inventario = json.loads((RAIZ / "dados" / "l100" / "inventario.json").read_text(encoding="utf-8"))
        declarados = {documento["arquivo"] for documento in manifesto["documentos"]}
        declarados |= {f"dados/l100/{documento['arquivo']}" for documento in inventario["documentos"]}
    except (OSError, ValueError, KeyError, TypeError):
        raise ErroLab("Não foi possível ler o manifesto L300 e o inventário L100 para conferir os documentos (nada foi criado).",
                      CODIGO_DIVERGENCIA) from None
    da_lista = {arquivo for arquivo in ARQUIVOS if "/documentos/" in arquivo}
    if declarados != da_lista:
        raise ErroLab("O manifesto L300 e o inventário L100 declaram documentos diferentes dos da lista fechada do montador. Revise a lista "
                      "(e os modelos em infra/sonda-l300) antes de montar o contexto. Nada foi criado.", CODIGO_DIVERGENCIA)


def ler_modelo(caminho: Path) -> bytes:
    """O modelo em UTF-8 com fins de linha LF, qualquer que seja o fim de linha da cópia de trabalho (Git no Windows usa CRLF)."""
    try:
        dados = caminho.read_bytes().replace(b"\r\n", b"\n")
        dados.decode("utf-8")
    except (OSError, UnicodeDecodeError):
        raise ErroLab(f"Não foi possível ler o modelo infra/sonda-l300/{caminho.name} (nada foi criado).", CODIGO_DIVERGENCIA) from None
    return dados


def conferir_origem(relativo: str) -> Path:
    origem = RAIZ / relativo
    if origem.is_symlink() or not origem.is_file() or not origem.resolve().is_relative_to(RAIZ.resolve()):
        raise ErroLab(f"Origem da lista fechada ausente ou fora do repositório: {relativo}. Nada foi criado.", CODIGO_DIVERGENCIA)
    return origem


# --------------------------------------------------------------------------------------
# Destino e montagem
# --------------------------------------------------------------------------------------

def preparar_destino(destino: Path) -> tuple[Path, bool]:
    """O destino resolvido e se ele não existia (e portanto será criado). Recusa arquivo, pasta com conteúdo e pasta-mãe inexistente."""
    destino = destino.expanduser().resolve()
    if destino.exists():
        if not destino.is_dir():
            raise ErroLab("O destino existe e não é uma pasta. Informe uma pasta nova ou vazia.", CODIGO_USO)
        if any(destino.iterdir()):
            raise ErroLab("A pasta de destino não está vazia e não será usada nem alterada: o contexto precisa ser montado em uma pasta "
                          "nova ou vazia, para que só a lista fechada de arquivos entre nele. Escolha outra pasta.", CODIGO_USO)
        return destino, False
    if not destino.parent.is_dir():
        raise ErroLab("A pasta-mãe do destino não existe. Crie-a (ou escolha outro destino) e repita.", CODIGO_USO)
    return destino, True


def _sha256(dados: bytes) -> str:
    return hashlib.sha256(dados).hexdigest()


def _gravar(destino: Path, relativo: str, dados: bytes, criados: list[Path]) -> Path:
    alvo = destino / relativo
    for pasta in reversed(alvo.relative_to(destino).parents):
        if str(pasta) != "." and not (destino / pasta).exists():
            (destino / pasta).mkdir()
            criados.append(destino / pasta)
    alvo.write_bytes(dados)
    criados.append(alvo)
    return alvo


def _conferir_copia(alvo: Path, relativo: str, esperado: str) -> None:
    if _sha256(alvo.read_bytes()) != esperado:
        raise ErroLab(f"O hash de {relativo} depois da cópia é diferente do da origem. O que foi criado foi retirado.", CODIGO_DIVERGENCIA)


def arquivos_da_pasta(destino: Path) -> set[str]:
    return {caminho.relative_to(destino).as_posix() for caminho in destino.rglob("*") if caminho.is_file()}


def montar(destino: Path) -> list[Copiado]:
    """Copia a lista fechada e grava o Dockerfile e o .dockerignore, conferindo o hash de cada arquivo. Em falha, retira o que criou."""
    dockerfile, lista = ler_modelo(MODELO_DO_DOCKERFILE), ler_modelo(MODELO_DA_LISTA)
    conferir_modelos(dockerfile.decode("utf-8"), lista.decode("utf-8"))
    conferir_documentos_declarados()
    origens = {relativo: conferir_origem(relativo) for relativo in ARQUIVOS}
    destino, nova = preparar_destino(destino)
    criados: list[Path] = [destino] if nova else []
    if nova:
        destino.mkdir()
    copiados: list[Copiado] = []
    try:
        for relativo, origem in origens.items():
            dados = origem.read_bytes()
            alvo = _gravar(destino, relativo, dados, criados)
            _conferir_copia(alvo, relativo, _sha256(dados))
            copiados.append(Copiado(relativo, len(dados), _sha256(dados)))
        for nome, dados in ((DOCKERFILE, dockerfile), (DOCKERIGNORE, lista)):
            alvo = _gravar(destino, nome, dados, criados)
            _conferir_copia(alvo, nome, _sha256(dados))
            copiados.append(Copiado(nome, len(dados), _sha256(dados)))
        esperados = {*ARQUIVOS, DOCKERFILE, DOCKERIGNORE}
        if arquivos_da_pasta(destino) != esperados:
            raise ErroLab("A pasta do contexto não tem exatamente os arquivos esperados. O que foi criado foi retirado.", CODIGO_DIVERGENCIA)
    except BaseException:
        retirar(criados)
        raise
    return copiados


def retirar(criados: list[Path]) -> None:
    """Remove só o que ESTE montador criou (arquivos primeiro, depois as pastas vazias, das mais fundas para as mais rasas)."""
    for caminho in reversed(criados):
        try:
            caminho.rmdir() if caminho.is_dir() else caminho.unlink()
        except OSError:
            pass


def comando_de_build(destino: Path, registro: str | None, imagem_do_chat: str | None, imagem_da_sonda: str | None) -> str:
    """O comando de referência em PowerShell: a pasta do contexto é o ÚLTIMO argumento e o Dockerfile é o dela (--file)."""
    registro = registro or "<registro>"
    imagem_do_chat = imagem_do_chat or f"{registro}.azurecr.io/<repositorio-do-chat>:<tag-do-chat>"
    imagem_da_sonda = imagem_da_sonda or "<repositorio-da-sonda>:<tag-nova>"
    pasta = "'" + str(destino).replace("'", "''") + "'"
    return "\n".join(["az acr build `", f"    --registry {registro} `", f"    --image {imagem_da_sonda} `",
                      f"    --build-arg IMAGEM_CHAT={imagem_do_chat} `", f"    --file {DOCKERFILE} `", f"    {pasta}"])


def dentro_do_repositorio(destino: Path) -> bool:
    return destino.expanduser().resolve().is_relative_to(RAIZ.resolve())


def executar(args: argparse.Namespace) -> int:
    if args.registro and args.imagem_chat and not args.imagem_chat.startswith(f"{args.registro}.azurecr.io/"):
        raise ErroLab("A imagem do chat precisa estar no registro informado em --registro.", CODIGO_USO)
    destino = args.destino.expanduser().resolve()
    copiados = montar(args.destino)
    print("Contexto de build da sonda do L300 montado (sem rede, sem Azure, sem Docker e sem az).")
    print(f"Pasta do contexto: {destino}")
    if dentro_do_repositorio(destino):
        print("[AVISO] A pasta está DENTRO do repositório: não a versione (não faça git add nela) e apague-a depois do build. "
              "Uma pasta fora do repositório evita esse risco.")
    print(f"Arquivos copiados e conferidos por SHA-256 ({len(copiados)}):")
    for item in copiados:
        print(f"  [ok] {item.relativo}  {item.sha256[:12]}  {item.tamanho} bytes")
    print("Conferido: os COPY do Dockerfile e a lista de permissão são exatamente a lista fechada, e a pasta não tem nenhum outro arquivo.")
    print()
    print("Comando de build de referência (PowerShell). Ele ALTERA o Azure: envia este contexto ao registro e cria uma imagem nele. "
          "Só execute com autorização e com registro, imagem do chat e tag SEUS, trocando os valores entre < >:")
    print(comando_de_build(destino, args.registro, args.imagem_chat, args.imagem_sonda))
    print()
    print("Confira ao rodar: a pasta do contexto é o ÚLTIMO argumento e --file aponta o Dockerfile dela (o da raiz do repositório é o do chat). "
          "O log do build precisa mostrar ARG IMAGEM_CHAT e COPY scripts/sonda_l300.py, e terminar com a etapa validar aprovada. Use uma tag "
          "nova e identificável, nunca latest. O valor de --build-arg é visível ao suporte do registro: só a referência da imagem, "
          "nunca segredos.")
    print("A imagem também traz o gerador de carga do L400 (scripts/gerar_carga_l400.py), que o build não executa. O ENTRYPOINT continua "
          "sendo a sonda: o gerador roda por substituição de comando no início do Job (--command e --args).")
    return CODIGO_OK


def criar_parser() -> lab_comum.ParserLab:
    parser = lab_comum.ParserLab(description=__doc__)
    parser.add_argument("--destino", required=True, type=Path,
                        help="Pasta NOVA ou vazia onde o contexto será montado (uma pasta com conteúdo é recusada).")
    parser.add_argument("--registro", default=None, type=validar_registro,
                        help="(opcional) Nome do registro de contêineres, só para preencher o comando impresso.")
    parser.add_argument("--imagem-chat", default=None, type=validar_imagem_do_chat,
                        help="(opcional) Imagem do chat, <registro>.azurecr.io/<repositório>:<tag>, só para preencher o comando impresso.")
    parser.add_argument("--imagem-sonda", default=None, type=validar_imagem_da_sonda,
                        help="(opcional) <repositório>:<tag-nova> da imagem da sonda, só para preencher o comando impresso.")
    return parser


def principal(argv: list[str] | None = None) -> int:
    lab_comum.configurar_saida()
    args = criar_parser().parse_args(argv)
    try:
        return executar(args)
    except ErroLab as erro:
        print(f"[ERRO] {erro}", file=sys.stderr)
        return erro.codigo
    except OSError as erro:
        print(f"[ERRO] Não foi possível montar o contexto ({type(erro).__name__}). O que foi criado foi retirado; confira as permissões e o "
              "espaço da pasta de destino.", file=sys.stderr)
        return CODIGO_USO
    except Exception as erro:  # noqa: BLE001 - um defeito do script vira mensagem e código 4, sem traceback com caminhos do seu computador
        print(f"[ERRO] Erro inesperado do script ({type(erro).__name__}). O que foi criado foi retirado. Se persistir, abra uma issue "
              "sem dados do seu ambiente.", file=sys.stderr)
        return CODIGO_INESPERADO


if __name__ == "__main__":
    sys.exit(principal())
