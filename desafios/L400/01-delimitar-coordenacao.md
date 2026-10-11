# L400 · Desafio 01: delimitar a coordenação

[Início](../../README.md) · [Roteiro L400](../../docs/roteiro-l400.md) · [Desafio 02](02-coordenar-especialistas.md)

| Campo | Definição |
| --- | --- |
| Situação | Contrato, preparação local e coordenação exercitados no Azure autorizado |
| Público | Atendimento, operações, arquitetura e desenvolvimento |
| Resultado | Contrato explícito para comparar coordenação com a referência L300 |
| Custo | Leitura e testes locais não chamam modelos; serviços Azure exigem orçamento e destino |

## Conteúdo

- [Cenário](#cenário)
- [Objetivos](#objetivos)
- [Artefatos e disponibilidade](#artefatos-e-disponibilidade)
- [Tecnologias e conceitos](#tecnologias-e-conceitos)
- [Pré-requisitos](#pré-requisitos)
- [Etapa 1: conferir a referência](#etapa-1-conferir-a-referência)
- [Etapa 2: delimitar responsabilidades](#etapa-2-delimitar-responsabilidades)
- [Como pedir uma mudança ao Copilot no VS Code](#como-pedir-uma-mudança-ao-copilot-no-vs-code)
- [Conferência do resultado](#conferência-do-resultado)
- [Solução de problemas](#solução-de-problemas)
- [Custos, pausa e limpeza](#custos-pausa-e-limpeza)
- [Situação da validação](#situação-da-validação)
- [Glossário e referências](#glossário-e-referências)

## Cenário

No piloto fictício de 2025, Beatriz Torres quer consultar assuntos que atravessam mais de uma fonte.
Teresa Moura pede uma comparação antes de trocar o fluxo do Atendimento. O objetivo é avaliar
o efeito da coordenação, não presumir que ela substitui a geração aumentada por recuperação
(RAG, do inglês *Retrieval-Augmented Generation*) convencional.

O L300 já protege documentos por perfil. O L400 conserva essa fronteira e os resultados históricos.
Nenhuma conclusão sobre uma contratação individual fica a cargo dos novos agentes.

## Objetivos

1. Identificar a referência, as quatro fontes aprovadas e a configuração.
2. Separar responsabilidade dos agentes e decisões determinísticas do programa.
3. Fixar limites e condições de interrupção antes de chamar modelos.
4. Distinguir preparação local, execução Azure e homologação de produção.

## Artefatos e disponibilidade

| Artefato | Uso |
| --- | --- |
| [Roteiro L300](../../docs/roteiro-l300.md) | Referência de acesso e topologia |
| [Registro Azure L300](../../docs/validacao/l300-azure-validacao.md) | Provas anteriores e limitações preservadas |
| [Manifesto aprovado](../../dados/l300/permissoes-documentais.json) | Quatro fontes, classes e hashes |
| [Política L100](../../scripts/lab_politica.py) | Fontes, recusas e texto fixo para contratação individual |
| [Roteiro L400](../../docs/roteiro-l400.md) | Decisões e sequência do nível |

O [plano de operação L400](../../scripts/operar_l400.py) já está disponível para leitura local.
O runtime está integrado e as consultas reais foram exercitadas; o
[registro L400](../../docs/validacao/l400-validacao.md) separa preparação, comparação e operação.

## Tecnologias e conceitos

**Geração aumentada por recuperação (RAG)** combina consulta às fontes e geração de texto.
O fluxo convencional L300 recupera e responde. O **Microsoft Agent Framework (MAF)** permite
organizar etapas e agentes com responsabilidades específicas [1].

Um **workflow**, fluxo de execução, define quais etapas recebem e produzem dados.
Um **executor** é uma dessas etapas. Autorizar a pessoa, aplicar filtros e conferir referências
continua sendo responsabilidade do programa, mesmo quando um modelo sugere consultas.

**Opção explícita**, ou *opt-in*, significa ativar o L400 deliberadamente. A configuração anterior
permanece como padrão e referência; mudar a estratégia não muda as regras de seguro.

## Pré-requisitos

Abra a pasta completa no Visual Studio Code (VS Code), editor do projeto. Use o terminal PowerShell
e o interpretador Python da `.venv`. Os testes locais dispensam conta Azure.
Se estiver em uma cópia nova, prepare o ambiente virtual e instale
`requirements\l400.txt` conforme o [README](../../README.md#estrutura-do-repositório).
Uma cópia existente deve passar em `pip check`; não reinstale pacotes só para repetir a leitura.

Uma execução externa exige assinatura ativa, tenant (diretório de identidades) correto, destinos informados e permissões
proporcionais. Login bem-sucedido não comprova autorização de dados. Não copie valores do instrutor.

## Etapa 1: conferir a referência

1. Revise alterações locais e conserve a base L300.
2. Confira Python e dependências existentes.
3. Confira o manifesto sem enviar arquivos.
4. Registre a configuração anterior em local privado.

```powershell
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe scripts\gerenciar_ingestao_l300.py --etapa validar
.\.venv\Scripts\python.exe scripts\operar_l400.py --etapa planejar --validar-bicep
```

**Resultado esperado:** fontes aprovadas e configuração identificada. Uma divergência de hash
interrompe a preparação; não atualize o inventário para esconder mudança de conteúdo.

## Etapa 2: delimitar responsabilidades

| Etapa | Pode fazer | Não recebe como decisão do modelo |
| --- | --- | --- |
| Planejamento | Sugerir consultas curtas dentro do limite | Destino, filtro, papel ou cota |
| Recuperação | Consultar as classes permitidas | Permissão informada na pergunta |
| Verificação | Conferir fontes, versões e referências | Uma garantia de cobertura individual |
| Redação | Produzir uma saída estruturada | Credenciais ou ferramentas de implantação |
| Política | Escolher o texto e as evidências apresentadas | Texto livre do modelo como substituto da regra |

No chat, a identidade vem da borda autenticada. Um perfil escolhido na linha de comando pelo
operador é um cenário de teste, não prova de login de uma pessoa.

## Como pedir uma mudança ao Copilot no VS Code

Anexe o roteiro, o manifesto, a política e o registro L300:

```text
Explique a referência L300 e as responsabilidades propostas para o L400.
Separe decisões do modelo, autorização documental e verificações do programa.
Identifique limites de chamadas, duração, tokens e retorno.
Não altere arquivos, execute Azure ou abra os conjuntos finais L100/L200.
```

Revise propostas em **Source Control**, área de alterações do VS Code. Gerar código não autoriza
executar uma implantação, atribuir papel ou enviar dados.

## Conferência do resultado

O contrato deve identificar referência, fontes, papéis, ferramentas, limites, erros e retorno.
A aprovação de conteúdo anterior não representa aprovação automática de uma estratégia de resposta.
Concluir este nível também não representa homologação para produção.

## Solução de problemas

| Sintoma | Ação |
| --- | --- |
| Proposta muda regras do seguro | Preserve as fontes; encaminhe conteúdo novo para revisão |
| Modelo recebe o filtro como parâmetro livre | Mova a decisão para o contexto autenticado do servidor |
| Nova estratégia substitui a referência | Conserve o padrão e exija ativação explícita |
| Gabarito aparece no corpus | Retire da carga e investigue contaminação antes de medir |

## Custos, pausa e limpeza

Leitura e validação do manifesto não criam recursos. Modelos, busca, imagens e rede custam na
execução externa. Registre orçamento e duração sem confundir previsão com cobrança.

Conserve a base para comparar e retornar. Não exclua recursos anteriores para simplificar o L400.

## Situação da validação

As verificações da base L300 e o plano L400 com compilação Bicep foram conferidos localmente.
O [registro L400](../../docs/validacao/l400-validacao.md) distingue esses comandos das consultas
e operações reais na nuvem. A comparação teve 16/16 conformes nas duas estratégias, sem ganho
observado da coordenação; isso não comprova fidelidade semântica nem homologação para produção.

## Glossário e referências

| Termo | Significado |
| --- | --- |
| RAG | Geração com recuperação de fontes |
| MAF | Framework de agentes e workflows |
| Executor | Etapa com entradas e saídas definidas |
| Opt-in | Ativação explícita de uma opção |
| Tenant | Diretório que administra as identidades |

1. [Requisição e resposta em workflows MAF](https://learn.microsoft.com/en-us/agent-framework/workflows/human-in-the-loop).
2. [Autenticação em Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/authentication).
3. [Filtros de segurança da busca](https://learn.microsoft.com/en-us/azure/search/search-security-trimming-for-azure-search).

Texto por GPT-6.1 Sol; código por Claude Sonnet 5.5. Modelos da autoria, do Copilot e da aplicação
são escolhas distintas.

Revisão documental por gpt-6-astra (Astra), em 11 de outubro de 2026, sem nova execução Azure.
