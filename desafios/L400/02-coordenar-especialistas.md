# L400 · Desafio 02: coordenar especialistas com limites

[Início](../../README.md) · [Desafio 01](01-delimitar-coordenacao.md) · [Desafio 03](03-operar-deployments.md)

| Campo | Definição |
| --- | --- |
| Situação | Runtime e plano validados localmente; consultas com filtro e política exercitadas no Azure |
| Público | Atendimento, arquitetura e desenvolvimento, com apoio de operações |
| Resultado | Planejar, recuperar, verificar e responder preservando a autorização |
| Custo | Dublês locais não usam modelos; coordenação real pode acrescentar chamadas e duração |

## Conteúdo

- [Cenário](#cenário)
- [Objetivos](#objetivos)
- [Artefatos e disponibilidade](#artefatos-e-disponibilidade)
- [Tecnologias e conceitos](#tecnologias-e-conceitos)
- [Pré-requisitos](#pré-requisitos)
- [Etapa 1: examinar o fluxo](#etapa-1-examinar-o-fluxo)
- [Etapa 2: conferir as fronteiras](#etapa-2-conferir-as-fronteiras)
- [Como pedir uma mudança ao Copilot no VS Code](#como-pedir-uma-mudança-ao-copilot-no-vs-code)
- [Conferência do resultado](#conferência-do-resultado)
- [Solução de problemas](#solução-de-problemas)
- [Custos, pausa e limpeza](#custos-pausa-e-limpeza)
- [Situação da validação](#situação-da-validação)
- [Glossário e referências](#glossário-e-referências)

## Cenário

Beatriz Torres consulta assuntos que podem exigir duas buscas diferentes. Teresa Moura pede que
o planejamento amplie a recuperação sem ampliar acesso nem transformar um verificador em juiz
infalível. O piloto fictício de 2025 continua explicando regras gerais, não contratações individuais.

## Objetivos

1. Distinguir agente de modelo e executor de programa.
2. Conferir filtro documental antes de cada recuperação.
3. Tratar referências, versões e falhas com verificações explícitas.
4. Conservar a política e o contrato público de resposta.

## Artefatos e disponibilidade

| Artefato | Responsabilidade |
| --- | --- |
| [Acesso documental](../../scripts/lab_acesso.py) | Classes e contexto da requisição |
| [Chat de referência](../../scripts/lab_chat.py) | Referências curtas e apresentação final |
| [Política](../../scripts/lab_politica.py) | Texto fixo, recusas e evidências |
| [Agente L100](../../scripts/lab_agente.py) | Uso anterior do MAF, sem confundir com a coordenação L400 |

O [runtime L400](../../scripts/lab_orquestracao.py), código que executa a coordenação,
a [interface de linha de comando (CLI)](../../scripts/coordenar_maf.py)
e os [testes de orquestração](../../tests/test_orquestracao.py) estão disponíveis.
O plano foi conferido sem rede; as consultas na nuvem têm evidências separadas no
[registro L400](../../docs/validacao/l400-validacao.md).

## Tecnologias e conceitos

O **Microsoft Agent Framework (MAF)** organiza agentes e executores em um workflow, fluxo com
entradas e saídas definidas. A implementação usa a API, interface de programação, disponível
nas versões fixadas do projeto. Um exemplo de outra versão pode usar nomes que não existem
na instalação atual.

O **planejador** sugere consultas; o **redator** produz saída estruturada. Recuperação e conferência
podem ser executores determinísticos. Não é necessário atribuir uma chamada de modelo a cada etapa.
O MAF oferece mensagens tipadas e eventos para organizar esse fluxo [1].

Os IDs curtos `T1`, `T2` são referências temporárias da requisição, não nomes universais de fontes.
O código resolve esses IDs para trechos recuperados, monta citações e aplica a política original.

## Pré-requisitos

Conclua o contrato do Desafio 01. Abra a pasta no VS Code, selecione a `.venv` e confira a versão
dos pacotes fixados. Os testes usam dublês, implementações falsas sem chamadas Azure.

A execução real exige índice compatível, identidade de dados e perfil autenticado. Sem contexto
de acesso, a coordenação deve parar antes de qualquer busca ou modelo.

## Etapa 1: examinar o fluxo

1. Identifique a entrada validada e o contexto de acesso.
2. Confira o limite de consultas do planejador.
3. Siga a expressão de filtro até o serviço de busca.
4. Confira referências e conteúdo antes da apresentação.

| Passagem | Condição |
| --- | --- |
| Planejador para recuperação | Consultas válidas, quantidade finita e filtro do programa |
| Recuperação para verificação | Nenhum trecho fora do perfil |
| Verificação para redator | Fontes disponíveis e contexto dentro do limite |
| Redator para política | Esquema válido e referências desta requisição |
| Política para interface | Resposta verificada ou recusa explícita |

Não invente vigência ou autoridade que os metadados não fornecem. Um conflito entre versões
precisa ser informado e tratado; escolher silenciosamente um texto não comprova precedência.

Confira o grafo real e os limites, sem identidade ou chamadas de serviço:

```powershell
.\.venv\Scripts\python.exe scripts\coordenar_maf.py --mostrar-plano
```

O grafo tem cinco etapas, com agentes MAF no planejamento e na redação. No chat, os limites
são oito chamadas no total, até quatro tentativas de geração e duas buscas, com reserva
máxima de 30.000 tokens de geração. Embeddings têm contagem e chamadas próprias, sem reserva
monetária automática. O planejamento limita a saída a 1.000 tokens e a redação a 3.000;
essas contagens incluem raciocínio. São valores desta implementação, não limites do serviço.

Para executar uma consulta no destino privado autorizado, use a identidade da aplicação.
O comando abaixo é referência da CLI, não um modo de simulação: ao executá-lo, a pergunta
é enviada aos serviços e pode consumir tokens. Defina `$busca`, `$modelos`,
`$clientIdConsulta` e `$perguntaSintetica` somente na sessão privada, com os destinos autorizados
e uma pergunta de desenvolvimento. A identidade gerenciada só está disponível no recurso
Azure ao qual foi atribuída; este comando não funciona como login do aluno no computador.
A rodada exercitou o runtime pela sonda e pelo chat, não comprovou esta invocação exata da CLI:

```powershell
.\.venv\Scripts\python.exe scripts\coordenar_maf.py --busca $busca --modelos $modelos --perfil atendimento --indice vareleira-lar-l300 --deployment-contingencia geracao-contingencia --identidade-gerenciada --client-id $clientIdConsulta --pergunta $perguntaSintetica
```

`--perfil` é escolha do operador da CLI. Na interface HTTP, protocolo de comunicação do chat,
ele vem somente dos papéis
da identidade autenticada; o navegador não pode escolhê-lo.

## Etapa 2: conferir as fronteiras

1. Exercite identidade sem papel e contexto ausente.
2. Introduza uma referência desconhecida em um dublê do modelo.
3. Simule trecho fora da classe permitida.
4. Execute duas requisições e confira a ausência de mistura de contexto.
5. Confira uma pergunta classificada como contratação individual.

**Resultado esperado:** recusas explícitas, nenhuma fonte fora do perfil e o texto fixo original
nos casos classificados como individuais. Um modelo verificador pode errar; verificações
determinísticas e avaliação independente permanecem necessárias.

Execute os testes locais de integração do MAF e fronteiras:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_orquestracao.py
```

Os agentes e o grafo são reais; os transportes dos modelos são dublês, sem consumo Azure.

## Como pedir uma mudança ao Copilot no VS Code

Anexe acesso, chat, política e a implementação L400 disponível:

```text
Siga o contexto de acesso de uma requisição até todas as buscas.
Confira se o modelo consegue trocar filtro, índice, papel ou destino.
Proponha um teste para referência inventada e outro para duas requisições.
Preserve a política L100 e o comportamento padrão L300.
Não execute Azure nem abra os conjuntos finais de avaliação.
```

Revise o diff e execute os testes relacionados. Um erro de filtro não deve ser corrigido repetindo
a consulta sem filtro.

## Conferência do resultado

Registre etapas e contagens, sem perguntas, tokens de autenticação ou resposta bruta em logs públicos.
Uma execução do workflow com dublês prova a integração do framework, não disponibilidade Azure.

## Solução de problemas

| Sintoma | Ação |
| --- | --- |
| Exemplo não importa uma classe MAF | Confira a versão e a API instalada antes de trocar dependências |
| Modelo cita ID inexistente | Recuse a saída inteira; não aproveite frases isoladas |
| Sem trechos, o redator continua | Interrompa a etapa e aplique a recusa do programa |
| Fonte de Atendimento aparece para Corretor | Interrompa uso e investigue filtros e isolamento de contexto |

## Custos, pausa e limpeza

Planejamento e redação podem consumir tokens separados. Registre todas as chamadas e tentativas;
não apresente apenas o uso da última resposta. Conserve o modo convencional para comparar.

Interromper localmente não garante que uma chamada remota já enviada pare de consumir tokens.
As próximas etapas devem deixar de executar.

## Situação da validação

O runtime teve 89 testes focados após corrigir dimensão reduzida e uso incerto de embeddings
em voo. O reparo posterior de cancelamento explícito elevou o módulo a 100 casos.
A suíte integrada final teve 1.015 casos: 1.014 aprovados e um ignorado no Windows;
100 testes de runtime e 24 de sanitização operacional, incluindo permissões POSIX,
passaram em Linux, sem ignorados.
Uma coordenação real na referência e no candidato recuperou a fonte operacional com filtro,
referência e política. O [registro L400](../../docs/validacao/l400-validacao.md)
preserva as falhas anteriores e o alcance das provas. A comparação continua vinculada à versão
anterior ao reparo de cancelamento, sem repetir as perguntas finais.

## Glossário e referências

| Termo | Significado |
| --- | --- |
| Dublê | Implementação de teste que substitui um serviço |
| API | Interface pela qual o código chama uma biblioteca ou serviço |
| Schema | Definição do formato dos dados |
| Contexto de acesso | Classes e filtro derivados da identidade autorizada |
| Referência curta | ID temporário associado a um trecho da requisição |

1. [Workflows MAF com requisição e resposta](https://learn.microsoft.com/en-us/agent-framework/workflows/human-in-the-loop).
2. [Filtros de segurança na busca](https://learn.microsoft.com/en-us/azure/search/search-security-trimming-for-azure-search).
3. [Respostas e streaming no FastAPI](https://fastapi.tiangolo.com/advanced/custom-response/).

Texto por GPT-6.1 Sol; código por Claude Sonnet 5.5. A autoria não seleciona o modelo do aluno.

Revisão documental por gpt-6-astra (Astra), em 11 de outubro de 2026, sem nova execução Azure.
