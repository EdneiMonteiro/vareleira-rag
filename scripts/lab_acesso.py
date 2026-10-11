"""Autorização documental do L300: papéis de aplicação, classes de acesso e filtro de segurança da busca.

Cada requisição passa por uma única decisão. O servidor lê os papéis nas claims da identidade que a plataforma de autenticação
validou (o cabeçalho X-MS-CLIENT-PRINCIPAL, decodificado em lab_chat), traduz cada papel reconhecido nas classes de documento
que ele pode ler, por tabelas estáticas deste arquivo, e monta o filtro OData da consulta só com essas classes. Nada que a
pessoa escreve (pergunta, JSON, query, cabeçalhos) entra no filtro, e um papel ausente, desconhecido ou com outra grafia vale
como nenhum papel: a requisição é recusada antes de qualquer busca, embedding ou chamada ao modelo.

As classes são o campo `acesso` de cada trecho do índice, que o indexador projeta do metadado `acesso` do blob. Um trecho sem
classe, ou com uma classe fora da lista, nunca satisfaz o filtro. O filtro decide por classe, não por documento: ele não conhece o
manifesto da ingestão nem limita IDs, e um trecho de qualquer documento com uma classe permitida é recuperável. Os papéis do
exercício (Vareleira.Atendimento e Vareleira.Corretor) são papéis de aplicação do laboratório, não papéis administrativos do Azure.

Este módulo usa só a biblioteca padrão e o `lab_comum`. Nada aqui guarda estado: o contexto de acesso é um valor imutável
criado por requisição.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from lab_comum import CODIGO_ACESSO, ErroLab

PAPEL_ATENDIMENTO = "Vareleira.Atendimento"
PAPEL_CORRETOR = "Vareleira.Corretor"
PAPEIS = (PAPEL_ATENDIMENTO, PAPEL_CORRETOR)

CLASSE_COMPARTILHADO = "compartilhado"
CLASSE_ATENDIMENTO = "atendimento"
CLASSE_CORRETOR = "corretor"
CLASSES = (CLASSE_COMPARTILHADO, CLASSE_ATENDIMENTO, CLASSE_CORRETOR)

# Perfis do exercício: o que cada papel pode recuperar. Quem tem os dois papéis recupera a união.
CLASSES_POR_PAPEL: Mapping[str, tuple[str, ...]] = {
    PAPEL_ATENDIMENTO: (CLASSE_COMPARTILHADO, CLASSE_ATENDIMENTO),
    PAPEL_CORRETOR: (CLASSE_COMPARTILHADO, CLASSE_CORRETOR),
}

CAMPO_ACESSO = "acesso"
MODO_PRE_FILTRO = "preFilter"  # com busca vetorial, o filtro age antes de escolher os vizinhos mais próximos

# O Entra ID entrega os papéis de aplicação na claim `roles`; a autenticação integrada pode expô-la pela URI longa.
TIPOS_DE_CLAIM_DE_PAPEL = ("roles", "http://schemas.microsoft.com/ws/2008/06/identity/claims/role")

PREFIXO_INDICE = "vareleira-lar-l300"
INDICE_PADRAO = PREFIXO_INDICE
PADRAO_INDICE_L300 = re.compile(re.escape(PREFIXO_INDICE) + r"(?:-[a-z0-9]{1,20}){0,3}")

_PADRAO_CAUSA = re.compile(r"[a-z_]{1,40}")
_PADRAO_FILTRO = re.compile(r"search\.in\(" + CAMPO_ACESSO + r",'([a-z]+(?:,[a-z]+)*)',','\)")


class ErroAcesso(ErroLab):
    """A regra de acesso documental foi violada ou não pôde ser aplicada: a consulta nunca segue sem o filtro."""

    def __init__(self, mensagem: str, causa: str = "filtro_de_acesso"):
        super().__init__(mensagem, CODIGO_ACESSO)
        self.causa = causa if _PADRAO_CAUSA.fullmatch(causa) else "filtro_de_acesso"


class ErroSemPapel(ErroAcesso):
    """A identidade não traz nenhum papel reconhecido pelo exercício."""

    def __init__(self) -> None:
        super().__init__("A identidade não traz nenhum papel de aplicação reconhecido: nenhuma classe de documento é permitida.",
                         "sem_papel_conhecido")


def indice_l300(nome: object) -> bool:
    """Só o índice do L300 (o prefixo e até três sufixos): o L100 e o L200 ficam fora do acesso documental."""
    return isinstance(nome, str) and PADRAO_INDICE_L300.fullmatch(nome) is not None


def papeis_dos_claims(claims: Iterable[Any]) -> tuple[str, ...]:
    """Papéis reconhecidos entre as claims, na ordem de PAPEIS. Qualquer outro valor é ignorado e nunca repassado."""
    encontrados = {
        claim["val"] for claim in claims
        if isinstance(claim, Mapping) and claim.get("typ") in TIPOS_DE_CLAIM_DE_PAPEL and isinstance(claim.get("val"), str)
    }
    return tuple(papel for papel in PAPEIS if papel in encontrados)


def classes_dos_papeis(papeis: Iterable[Any]) -> tuple[str, ...]:
    """Classes permitidas aos papéis reconhecidos, na ordem de CLASSES e sem repetição; vazio se nenhum for reconhecido."""
    recebidos = [papel for papel in papeis if isinstance(papel, str)]
    permitidas = {classe for papel in PAPEIS if papel in recebidos for classe in CLASSES_POR_PAPEL[papel]}
    return tuple(classe for classe in CLASSES if classe in permitidas)


def construir_filtro(classes: Iterable[Any]) -> str:
    """Filtro OData do Azure AI Search, montado só com as classes da lista fixa. Classe fora dela, ou lista vazia, é erro."""
    recebidas = list(classes)
    if not recebidas or not all(isinstance(classe, str) and classe in CLASSES for classe in recebidas):
        raise ErroAcesso("O filtro de acesso exige uma ou mais classes da lista fixa: " + ", ".join(CLASSES) + ".",
                         "classe_invalida")
    canonicas = [classe for classe in CLASSES if classe in recebidas]
    return f"search.in({CAMPO_ACESSO},'{','.join(canonicas)}',',')"


def classes_do_filtro(filtro: object) -> tuple[str, ...]:
    """Classes de um filtro gerado por `construir_filtro`. Qualquer outro texto é recusado: nenhum filtro livre chega à busca."""
    achado = _PADRAO_FILTRO.fullmatch(filtro) if isinstance(filtro, str) else None
    if achado is not None:
        classes = tuple(achado.group(1).split(","))
        try:
            if construir_filtro(classes) == filtro:
                return classes
        except ErroAcesso:
            pass
    raise ErroAcesso("O filtro de acesso não é o que a autorização documental gera: a consulta foi recusada.", "filtro_invalido")


def validar_filtro(filtro: object) -> str:
    classes_do_filtro(filtro)
    return str(filtro)


@dataclass(frozen=True)
class ContextoAcesso:
    """A decisão de acesso de uma requisição: papéis reconhecidos, classes permitidas e o filtro da busca.

    Os campos são conferidos na criação: uma instância inconsistente não existe. Use `autorizar` para criá-la.
    """

    papeis: tuple[str, ...]
    classes: tuple[str, ...]
    filtro: str

    def __post_init__(self) -> None:
        consistente = (isinstance(self.papeis, tuple) and bool(self.papeis) and self.papeis == papeis_ordenados(self.papeis)
                       and self.classes == classes_dos_papeis(self.papeis) and self.filtro == construir_filtro(self.classes))
        if not consistente:
            raise ErroAcesso("Contexto de acesso inconsistente: ele só pode ser criado por 'autorizar'.", "contexto_invalido")

    def permite(self, trecho: Mapping[str, Any]) -> bool:
        """Verdadeiro só para um trecho cuja classe é uma das permitidas. Classe ausente, vazia ou desconhecida nunca passa."""
        valor = trecho.get(CAMPO_ACESSO)
        return isinstance(valor, str) and valor in self.classes

    def exigir_resultados_permitidos(self, resultados: Sequence[Mapping[str, Any]]) -> None:
        """Última conferência, depois da busca e antes do modelo: o índice só pode devolver trechos que o filtro permite.

        Não substitui o filtro (que age antes da busca); só impede que um defeito do índice ou do filtro entregue ao modelo
        um trecho fora do perfil. Qualquer divergência interrompe a requisição, sem aproveitar os trechos permitidos.
        """
        if not all(self.permite(trecho) for trecho in resultados):
            raise ErroAcesso("A busca devolveu um trecho fora das classes permitidas: nada foi enviado ao modelo.",
                             "resultado_fora_do_perfil")


def papeis_ordenados(papeis: Sequence[Any]) -> tuple[str, ...]:
    """Os papéis na ordem de PAPEIS, sem repetição e sem valores desconhecidos (para comparar com o que veio)."""
    return tuple(papel for papel in PAPEIS if papel in papeis)


def autorizar(papeis: Iterable[Any]) -> ContextoAcesso:
    """O contexto de acesso dos papéis recebidos. Sem nenhum papel reconhecido, levanta `ErroSemPapel` (HTTP 403 no chat)."""
    recebidos = [papel for papel in papeis if isinstance(papel, str)]
    conhecidos = papeis_ordenados(recebidos)
    if not conhecidos:
        raise ErroSemPapel()
    classes = classes_dos_papeis(conhecidos)
    return ContextoAcesso(conhecidos, classes, construir_filtro(classes))
