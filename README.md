# Vareleira RAG

[![ORCID](https://img.shields.io/badge/ORCID-0009--0006--0765--4201-A6CE39?logo=orcid&logoColor=white)](https://orcid.org/0009-0006-0765-4201)
[![Status: em preparação](https://img.shields.io/badge/status-em_prepara%C3%A7%C3%A3o-yellow)](#estado-do-laboratório)
[![Código: MIT](https://img.shields.io/badge/C%C3%B3digo-MIT-yellow.svg)](LICENSES/MIT.txt)
[![Conteúdo: CC BY 4.0](https://img.shields.io/badge/Conte%C3%BAdo-CC%20BY%204.0-lightgrey.svg)](LICENSES/CC-BY-4.0.txt)
[![Último commit](https://img.shields.io/github/last-commit/EdneiMonteiro/vareleira-rag)](https://github.com/EdneiMonteiro/vareleira-rag/commits/main)

Laboratório educacional do **Assistente de Apólices com geração aumentada por
recuperação (RAG, do inglês Retrieval-Augmented Generation)** da
[Vareleira](https://vareleira.com/), uma seguradora inteiramente fictícia.
O objetivo é aprender a consultar condições gerais sintéticas de seguro
residencial, recuperar evidências e responder com fontes verificáveis.

**Este repositório está em preparação. Ainda não há aplicação executável,
base de apólices ou ambiente para provisionar.** A tecnologia será definida
durante a implementação; não há dependência de um provedor de nuvem ou modelo.

## O caso do laboratório

Na narrativa, em **2025**, Beatriz Torres, responsável pelo Atendimento,
identifica respostas divergentes para perguntas semelhantes: as equipes
consultam versões distintas de documentos. O piloto interno atende
**Atendimento e corretores** e começa pelo produto **Vareleira Lar**.
Teresa Moura, diretora técnica de Subscrição, é a autoridade sobre as regras
do produto.

O piloto é anterior ao assistente externo registrado no assessment de
agosto de 2026. As soluções em produção desse assessment pertencem à ficção,
não são entregas deste repositório.

Contexto adotado: **Vareleira 0.1.0**, na
[revisão d17a24b](https://github.com/EdneiMonteiro/vareleira/tree/d17a24bd9fdf16a5b3dba34e07764852a8477859).
Consulte a [introdução da jornada](https://vareleira.com/rag.html), o
[contexto estruturado versionado](https://github.com/EdneiMonteiro/vareleira/blob/d17a24bd9fdf16a5b3dba34e07764852a8477859/dados/contexto-v0.1.0.json)
e as [atribuições](NOTICE.md).

## Objetivos e limites

O laboratório deverá exercitar:

- Preparação de documentos sintéticos com produto, versão, vigência fictícia
  e autoridade da fonte.
- Recuperação de trechos pertinentes e identificação de documentos
  desatualizados ou de outra versão.
- Respostas sustentadas por referências localizáveis nos documentos.
- Tratamento de perguntas ambíguas, fora de escopo ou sem evidência suficiente.
- Avaliação reproduzível da recuperação e da fidelidade das respostas às fontes.

Por exemplo, **“O meu seguro cobre danos elétricos?”** não pode ser respondida
como confirmação de cobertura individual apenas com condições gerais.
O assistente deverá distinguir a explicação do produto da análise de uma
contratação e encaminhar o que estiver fora de seu escopo.
As coberturas, exclusões e franquias fictícias ainda serão definidas.

**Fora do escopo:** dados pessoais reais; decisões de cobertura individual,
indenização ou elegibilidade; emissão ou alteração de contratos; execução de
ações em sistemas; uso em produção sem avaliação própria.
O site institucional não substitui a futura base documental de seguros.

## Estado do laboratório

| Entrega | Situação |
| --- | --- |
| Escopo, contexto narrativo, licenças e políticas do repositório | Disponíveis |
| Condições gerais sintéticas e metadados documentais | Planejados |
| Implementação da ingestão, recuperação e geração com fontes | Planejada |
| Perguntas, critérios e execução da avaliação | Planejados |
| Roteiro de execução, pré-requisitos e orientações de custos | Planejados |

Ainda não existe uma release do laboratório. A versão 0.1.0 citada acima é
**do contexto Vareleira**, não deste código. Não há comandos de instalação
ou execução nesta etapa.

## Participação e suporte

| Necessidade | Referência |
| --- | --- |
| Tirar dúvidas e propor a evolução do laboratório | [Discussions](https://github.com/EdneiMonteiro/vareleira-rag/discussions) |
| Relatar um problema reproduzível | [Issues](https://github.com/EdneiMonteiro/vareleira-rag/issues) |
| Contribuir | [CONTRIBUTING.md](CONTRIBUTING.md) |
| Consultar suporte e seus limites | [SUPPORT.md](SUPPORT.md) |
| Entender ficção, privacidade e riscos | [DISCLAIMER.md](DISCLAIMER.md) |
| Relatar vulnerabilidades em privado | [SECURITY.md](SECURITY.md) |
| Consultar regras de convivência | [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) |
| Consultar autoria e créditos | [CONTRIBUTORS.md](CONTRIBUTORS.md) |

Projeto pessoal de **Ednei Monteiro**, sem afiliação, endosso ou suporte
oficial da Microsoft, do GitHub ou de uma seguradora. Suporte comunitário,
sem prazo de resposta garantido. Use somente dados sintéticos e nunca publique
segredos ou documentos reais de segurados.

## Licenças e citação

**Código e configurações:** [MIT](LICENSES/MIT.txt).
**Documentação, narrativa e dados sintéticos:** [CC BY 4.0](LICENSES/CC-BY-4.0.txt).
São escopos distintos, não opções de licença para o mesmo material.
Veja [LICENSE](LICENSE) e [NOTICE.md](NOTICE.md).

Referência sugerida:

> Monteiro, Ednei. *Vareleira RAG: laboratório educacional de consulta a
> condições gerais de seguro com fontes documentais*. 2026.
> https://github.com/EdneiMonteiro/vareleira-rag

Informe também a revisão utilizada. Os metadados estão em [CITATION.cff](CITATION.cff).
Este projeto não possui DOI próprio.
