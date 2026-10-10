# L100 — Desafio 05: um agente com Microsoft Agent Framework que decide quando buscar nos documentos

[Início do laboratório](../../README.md) · Nível L100: fundamentos · [Desafio 04](04-recusar-sem-evidencia.md)

| Item | Descrição |
| --- | --- |
| Situação | Exercício executável, validado no Azure em 9 de outubro de 2026 (Windows e PowerShell). Os documentos de seguro são sintéticos e novos. Estão pendentes a revisão do conteúdo pelo mantenedor e a revisão humana do texto; veja [Situação da validação](#situação-da-validação). |
| Público | Pessoas de negócio, arquitetura, operações e desenvolvimento. Use o Visual Studio Code (VS Code) para executar os comandos e conferir os resultados; escrever código é opcional. |
| Pré-requisito | [Desafio 04](04-recusar-sem-evidencia.md) concluído: este desafio reaproveita a política de resposta, o deployment de geração e o índice. |
| Resultado | O programa `agente_maf.py`: um agente do Microsoft Agent Framework (MAF) que decide quando e o que buscar nos documentos por uma ferramenta de busca. O programa limita as buscas, registra o rastro e confere a resposta com a política do Desafio 04. |
| Custo | Nenhum recurso novo. As chamadas ao modelo e as buscas consomem tokens; o total depende de quantas buscas o agente faz e dos trechos recebidos. Veja [Custos, pausa e limpeza](#custos-pausa-e-limpeza). |

## Conteúdo

- [Cenário](#cenário)
- [Objetivos](#objetivos)
- [Artefatos e disponibilidade](#artefatos-e-disponibilidade)
- [Tecnologias e conceitos](#tecnologias-e-conceitos)
- [Reaproveitamento e acréscimos](#reaproveitamento-e-acréscimos)
- [Pré-requisitos](#pré-requisitos)
- [Etapa 1: instalar o MAF e ver o que o agente recebe](#etapa-1-instalar-o-maf-e-ver-o-que-o-agente-recebe)
- [Etapa 2: perguntar com a recuperação obrigatória](#etapa-2-perguntar-com-a-recuperação-obrigatória)
- [Etapa 3: perguntar com a ferramenta de busca](#etapa-3-perguntar-com-a-ferramenta-de-busca)
- [Etapa 4: conhecer os limites do agente](#etapa-4-conhecer-os-limites-do-agente)
- [Etapa 5: testar o agente sem o Azure](#etapa-5-testar-o-agente-sem-o-azure)
- [Como pedir uma mudança ao Copilot no VS Code](#como-pedir-uma-mudança-ao-copilot-no-vs-code)
- [Conferência do resultado](#conferência-do-resultado)
- [Solução de problemas](#solução-de-problemas)
- [Custos, pausa e limpeza](#custos-pausa-e-limpeza)
- [Situação da validação](#situação-da-validação)
- [Glossário](#glossário)
- [Referências](#referências)

## Cenário

Em 2025, na história fictícia da Vareleira, o Atendimento já recebe respostas com fontes e recusas
decididas pelo programa (Desafios 03 e 04). Beatriz Torres, responsável pelo Atendimento, apresenta uma
pergunta com dois assuntos: "O seguro cobre alagamento e quantas vezes posso acionar a assistência
24 horas?". A exclusão e a regra de serviço estão em partes diferentes dos documentos. O fluxo atual
busca uma vez com a pergunta inteira; a resposta depende dos trechos encontrados.

Teresa Moura, diretora técnica de Subscrição, pede uma comparação: um agente que busca mais de uma vez,
sob as mesmas regras de verificação. A escolha deve considerar a resposta obtida, o tempo e os tokens
consumidos.

**Missão:** construir um agente com o Microsoft Agent Framework (MAF) que decide quando e o que buscar por meio de uma ferramenta, limitar o que ele pode fazer, registrar o que ele fez e comparar o resultado com o fluxo fixo.

> **Lembre-se:** o cenário é fictício. Não use apólices, nomes, endereços ou documentos de segurados reais, mesmo que tenha acesso a eles no trabalho.

## Objetivos

Ao concluir este desafio, você terá:

- instalado o MAF e visto o que um agente recebe: instruções, uma ferramenta e limites;
- executado o fluxo do Desafio 04 por um agente sem ferramentas (recuperação obrigatória);
- observado um agente que decide quando e o que buscar (recuperação por ferramenta) e lido o rastro das buscas dele;
- comparado os dois modos em tipo de resposta, buscas e tokens, com 2 e com 5 trechos por busca;
- visto o programa limitar as buscas e mostrar uma falha da busca que o agente não relata;
- executado os testes automáticos do agente, sem Azure, e identificado a biblioteca real e o serviço de modelos simulado usados nesses testes.

**Próximos desafios:** o [Desafio 06](06-avaliar-respostas.md) mede a qualidade da recuperação e das respostas; o [Desafio 07](07-identidade-da-aplicacao.md) usa service principal (identidade de uma aplicação no Microsoft Entra ID) e Azure Key Vault (serviço de guarda de segredos).

> **Para guardar na memória: L-C-R.** Para dar uma ferramenta a um agente, **L**imite o que ele pode pedir, **C**onfira o que ele afirma e **R**egistre o que ele fez. Mnemônico criado para este curso.

## Artefatos e disponibilidade

| Artefato | Onde encontrar | Situação |
| --- | --- | --- |
| Desafio anterior (política de resposta, deployment de geração e `perguntar.py`) | [04-recusar-sem-evidencia.md](04-recusar-sem-evidencia.md) | Disponível; pré-requisito |
| Pergunta e resposta do agente no console | [scripts\agente_maf.py](../../scripts/agente_maf.py) | Disponível; validado |
| Ferramenta de busca, limites, agente e verificação | [scripts\lab_agente.py](../../scripts/lab_agente.py) | Disponível; validado |
| Política de resposta: tipos, evidências e textos fixos | [scripts\lab_politica.py](../../scripts/lab_politica.py) | Disponível; do Desafio 04, sem alteração |
| Dependências do Python, com o MAF fixado | [requirements\l100.txt](../../requirements/l100.txt) | Disponível |
| Testes automáticos do agente (sem Azure) | [tests\test_agente.py](../../tests/test_agente.py) | Disponíveis |
| Documentos sintéticos e inventário | [dados\l100\inventario.json](../../dados/l100/inventario.json) | Disponível; aprovação do mantenedor confirmada |

> **Atenção:** este desafio não altera o Azure. As perguntas só leem o índice, mas consomem tokens (as unidades de texto que o modelo conta e cobra). O agente decide quando chamar a ferramenta; a decisão de executar o programa é sua, mesmo quando você pede ao Copilot que "implemente" ou "corrija" algo.

## Tecnologias e conceitos

| Componente | Função neste desafio | Limite ou cuidado |
| --- | --- | --- |
| Microsoft Agent Framework (MAF) | Biblioteca de código aberto da Microsoft para montar agentes: reúne instruções, cliente do modelo, ferramentas e o laço que executa as chamadas [1] | As versões estão fixadas em `requirements\l100.txt`; uma atualização exige conferir compatibilidade e repetir os testes |
| Agente (`Agent`) | Reúne o cliente, as instruções e as ferramentas; `agent.run` executa o laço até a resposta final [1][2] | O modelo decide se chama a ferramenta; o programa define o que a ferramenta permite |
| Cliente `OpenAIChatClient` | Fala com o deployment de geração pela API Responses (interface de programação, API, *Application Programming Interface*, em que o programa envia o pedido e recebe a resposta), com a identidade do Azure CLI (*Command-Line Interface*, interface de linha de comando) e sem chaves [3] | A resposta do serviço devolve o nome do deployment, não o do modelo |
| Ferramenta de função (`@tool`) | Função Python que o modelo pode pedir; o MAF monta o esquema em JSON (*JavaScript Object Notation*, formato de dados em texto) a partir dos tipos e das descrições [2] | O modelo escolhe os argumentos; a função precisa validá-los |
| Limites do laço | `max_function_calls`, `max_iterations` e `max_duration_seconds`: ao atingir um limite, o MAF para de executar ferramentas e pede a resposta final [2] | A conferência ocorre depois de cada lote; a ferramenta e o programa também impõem limites |
| Saída estruturada | O agente devolve o mesmo JSON do Desafio 04 (`tipo`, `resposta` e `evidencias`), pela opção `response_format` [4] | Garante o formato; o conteúdo continua sendo do modelo |
| Política do Desafio 04 | Aplica regras ao tipo, confere cada citação e escolhe o texto mostrado | As citações são verificadas; a correspondência e a completude da resposta exigem revisão |
| Deployment de geração, busca e embeddings | Os dos Desafios 02 e 03, sem mudança | |

**Conceitos necessários:** agente e laço, duas formas de entregar os trechos, quem controla o agente, o que a ferramenta devolve e limites da conferência.

**1. Agente e laço.** Um modelo de linguagem recebe texto e devolve texto. Um agente é o programa em volta dele: apresenta ao modelo uma lista de ferramentas (funções com nome, descrição e parâmetros) e, quando o modelo responde com um pedido de ferramenta ("chame `buscar_trechos` com a consulta X"), executa a função, devolve o resultado ao modelo e repete. Esse ciclo é o laço do agente. O MAF implementa o laço; o programa deste desafio escreve a ferramenta, os limites e a verificação [1][2].

> **Para guardar na memória: o estagiário e o arquivo.** O agente é um estagiário que pede pastas ao arquivo (a ferramenta) quantas vezes o chefe permite. O chefe (o programa) define quais pastas existem, anota cada pedido e confere cada nota de rodapé antes de assinar a resposta. Analogia criada para este curso.

**2. Duas formas de entregar os trechos.**

| Aspecto | Recuperação obrigatória | Recuperação por ferramenta |
| --- | --- | --- |
| Quem busca | O programa, uma vez, antes do modelo, com a pergunta inteira | O agente, de zero a várias vezes, com a consulta que ele escreve |
| O que o modelo recebe | A pergunta e os trechos | A pergunta; os trechos chegam como resultado da ferramenta |
| Idas ao modelo | Uma | Uma, mais uma por busca |
| Pode dispensar a busca | Não | Sim |
| Opção do programa | `--recuperacao obrigatoria` | `--recuperacao ferramenta` (padrão) |

A documentação do MAF recomenda escrever uma função comum quando ela resolve a tarefa e reservar o agente para as tarefas abertas, em que a escolha das ações depende do caso [1]. A Etapa 4 mede essa diferença com a mesma política nos dois modos.

**3. Quem controla o agente.** O modelo escolhe duas coisas: se chama a ferramenta e o texto da consulta. O programa controla o resto:

- a ferramenta fixa o modo de busca e o `k` (a quantidade de trechos por busca) e valida a consulta (de 1 a 300 caracteres);
- o programa limita as buscas por pergunta (padrão: 2; opção `--maximo-de-buscas`) em duas camadas: o laço do MAF para de executar ferramentas, e a própria ferramenta recusa buscas além do limite [2];
- o laço tem limites de idas ao modelo e de tempo, e o programa interrompe o agente que passa de 120 segundos;
- o programa registra cada busca e cada trecho devolvido, e é com esses trechos que confere as citações;
- a política do Desafio 04 decide o que a pessoa vê, com uma regra a mais: a resposta de um agente que classifica a pergunta como `documentada`, `contratacao_individual` ou `sem_evidencia` sem ter buscado é descartada, porque ele não leu nenhum documento.

**4. O que a ferramenta devolve é dado.** Os trechos voltam ao modelo dentro das marcas `<trecho>`, como no Desafio 03, e as instruções dizem que eles são dados, não ordens. Um documento com uma instrução escondida (um ataque indireto [5]) continua sendo um risco: o agente lê o resultado da ferramenta como lê qualquer texto. Uma ferramenta com mais poder que buscar (escrever, enviar ou executar) aumentaria o risco; por isso a única ferramenta deste desafio só lê.

**5. Limites da conferência.** A política confere se cada citação aparece literalmente em uma fonte
recuperada. A revisão humana compara o sentido da resposta com essas fontes e verifica se todos os
assuntos foram cobertos. Uma busca incompleta pode produzir uma recusa `sem_evidencia` mesmo quando o
documento contém a regra, ou uma resposta que cobre só parte da pergunta. A Etapa 4 permite observar
ambas as situações.

## Reaproveitamento e acréscimos

| Item | Situação | Observação |
| --- | --- | --- |
| Infraestrutura no Azure | Reaproveitada, sem alteração | Nenhum recurso novo, nenhum papel novo |
| Política (`lab_politica.py`), contexto e pedido (`lab_geracao.py`) | Reaproveitados | As regras não mudam; o agente usa as mesmas instruções, o mesmo esquema e a mesma verificação |
| `perguntar.py` | Mesmo comportamento | Uma função de exibição foi separada (`mostrar_decisao`) para o agente reaproveitá-la |
| `requirements\l100.txt` | Inclui `agent-framework-core` e `agent-framework-openai` | Instale as dependências na Etapa 1 |
| `lab_agente.py` e `agente_maf.py` | **Novos** | Ferramenta de busca, limites, agente, rastro e verificação |
| `lab_indexacao.py` e `lab_geracao.py` | Extensões | O erro 404 intermitente tem mensagem própria; o cliente de embeddings repete esse erro e abre uma conexão nova por pedido. Veja [Solução de problemas](#solução-de-problemas) |
| `lab_comum.py` | Pequena extensão | Sem `--detalhes`, o registro técnico do MAF fica oculto, como o do SDK (*Software Development Kit*, conjunto de bibliotecas de programação) do Azure |
| Testes | `tests\test_agente.py` novo | Executam a biblioteca MAF instalada contra um serviço de modelos simulado, sem Azure |
| Reverter | Deixar de usar `agente_maf.py` | Os desafios anteriores não dependem do MAF |

## Pré-requisitos

Os comandos deste guia são escritos para Windows e PowerShell, no terminal integrado do Visual Studio Code (VS Code), como nos desafios anteriores.

| Pré-requisito | Como preparar | Necessário agora? |
| --- | --- | --- |
| Desafio 04 concluído | O deployment de geração criado e `perguntar.py` funcionando com `--politica completa`, no mesmo grupo de recursos e na mesma assinatura | Sim |
| Variáveis do terminal | `$assinatura`, `$grupo`, `$busca`, `$modelos` e `$deploymentGeracao` definidas (veja abaixo) | Sim |
| Ambiente virtual do Python | O mesmo do Desafio 01; a Etapa 1 instala as bibliotecas novas | Sim |
| Assinatura e permissões | Assinatura Azure ativa e permissões de dados do Desafio 03 | Sim |
| Aceitar o custo | Cada pergunta consome tokens; o serviço de busca continua cobrando por hora | Sim |

Em um terminal novo, defina as variáveis de novo. Substitua `<ID-DA-SUA-ASSINATURA>` e use o nome do grupo criado no Desafio 01:

```powershell
$assinatura = "<ID-DA-SUA-ASSINATURA>"
$grupo = "rg-vareleira-rag-l100"
$busca = az deployment group show --subscription $assinatura --resource-group $grupo --name vareleira-rag-l100-d02 --query properties.outputs.nomeBusca.value --output tsv
$modelos = az deployment group show --subscription $assinatura --resource-group $grupo --name vareleira-rag-l100-d02 --query properties.outputs.nomeModelos.value --output tsv
$deploymentGeracao = az deployment group show --subscription $assinatura --resource-group $grupo --name vareleira-rag-l100-d03 --query properties.outputs.nomeDeploymentGeracao.value --output tsv
$busca
$modelos
$deploymentGeracao
```

**Resultado esperado:** `srch-vlr-...`, `ais-vlr-...` e `geracao`.

## Etapa 1: instalar o MAF e ver o que o agente recebe

**Objetivo:** instalar as bibliotecas novas e ler, sem acessar o Azure, as instruções, a ferramenta e os limites que o agente recebe.

### 1.1 Instalar as dependências

O arquivo `requirements\l100.txt` inclui `agent-framework-core`, o núcleo do MAF, e
`agent-framework-openai`, o provedor que se comunica com os modelos da OpenAI e do Azure OpenAI [3].
Ative o ambiente virtual do Desafio 01 ou use `.\.venv\Scripts\python.exe` no lugar de `python`:

```powershell
python -m pip install -r requirements\l100.txt
python -m pip check
python -m pip show agent-framework-openai
```

**Resultado esperado:** o primeiro comando instala os pacotes novos (ou informa `Requirement already satisfied`), o segundo informa `No broken requirements found.` e o terceiro mostra `Version: 1.15.0`.

> **Boa prática:** instale só o que `requirements\l100.txt` lista, com as versões fixadas. Outra versão do MAF pode renomear classes e opções e mudar o comportamento descrito neste guia.

### 1.2 Ver o que o agente recebe

```powershell
python scripts\agente_maf.py --busca $busca --modelos $modelos --deployment-geracao $deploymentGeracao --pergunta "O seguro cobre alagamento e quantas vezes posso acionar a assistência 24 horas?" --mostrar-agente
```

O comando mostra o agente sem consultar o Azure. As opções `--busca` e `--modelos` continuam obrigatórias em todos os comandos do programa.

**Exemplo de saída registrada** (resumido):

```text
--- Instruções do agente ---
Você consulta as Condições Gerais, o glossário e as perguntas frequentes do Vareleira Lar, ...
...
Como consultar os documentos:
- Os trechos não acompanham a pergunta. Para obtê-los, chame a ferramenta buscar_trechos com uma consulta curta e específica, em português. ...
- Se a primeira busca não trouxer o que falta, ou se a pergunta trata de mais de um assunto, busque de novo com outras palavras. Faça no máximo 2 chamada(s) à ferramenta.
- Não chame a ferramenta quando a pergunta claramente não trata de seguro residencial.
- Só classifique como sem_evidencia depois de buscar pelo menos uma vez.

--- Ferramenta que o agente pode chamar ---
Nome: buscar_trechos
Descrição: Busca, nos documentos do Vareleira Lar (...), os trechos mais pertinentes à consulta e os devolve entre marcas <trecho>. ...
Parâmetros (esquema JSON que o modelo recebe):
{
  "properties": {
    "consulta": {
      "description": "Palavras-chave ou frase curta, em português, sobre o assunto procurado (até 300 caracteres).",
      "title": "Consulta",
      "type": "string"
    }
  },
  "required": ["consulta"],
  ...
}

--- Limites ---
Chamadas da ferramenta: até 2 · idas ao modelo: até 4 · tempo do laço: 60 s · tempo total: 120 s
A ferramenta fixa o modo (hibrida) e a quantidade de trechos (5); o modelo escolhe só o texto da consulta.
```

As instruções começam com as do Desafio 04 (a classificação em cinco tipos e as regras de citação literal) e terminam com a seção sobre como consultar os documentos.

**Atividade 1:** no esquema JSON da ferramenta, localize o que o modelo pode escolher. Depois, na linha final de "Limites", localize o que o modelo não escolhe e diga onde o programa guarda cada valor.

**Conferência:** o único argumento que o modelo escolhe é `consulta`. O programa fixa o modo
(`hibrida`) e o `k` (5); a ferramenta não aceita argumentos para mudá-los.
O limite de chamadas vem de `--maximo-de-buscas`, e os limites de tempo ficam em `lab_agente.py`.

### Prompt para o Copilot: entender o agente antes de executar

Anexe `scripts\lab_agente.py` e `scripts\agente_maf.py`:

```text
Leia scripts/lab_agente.py e scripts/agente_maf.py anexados.
Explique, para quem não programa e com uma analogia, o que o MAF faz e o que o programa deste projeto faz quando o agente usa a ferramenta de busca.
Mostre onde o programa limita o número de buscas, onde registra os trechos devolvidos e onde descarta a resposta de um agente que não buscou.
Liste dois riscos de deixar o modelo escolher o texto da consulta e uma proteção do código para cada um.
Não edite arquivos, não execute comandos e não acesse o Azure.
```

**Conferência:** a resposta deve citar `FerramentaBusca` (limite e registro dos trechos), `configuracao_de_limites` (limites do laço) e `decidir` (descarte do agente que não buscou), e dizer que o modelo escolhe só o texto da consulta. Confira cada afirmação no código: o Copilot pode atribuir ao MAF controles que são do programa, ou o contrário.

## Etapa 2: perguntar com a recuperação obrigatória

**Objetivo:** executar o fluxo do Desafio 04 por um agente do MAF sem ferramentas, para separar o que muda (a biblioteca que fala com o modelo) do que permanece (a busca e a política). Esta etapa não altera o Azure.

Na recuperação obrigatória, o programa busca antes, como em `perguntar.py`. O agente recebe a pergunta e os trechos, sem ferramentas, e devolve o mesmo JSON do Desafio 04.

```powershell
python scripts\agente_maf.py --busca $busca --modelos $modelos --deployment-geracao $deploymentGeracao --pergunta "Qual é a franquia da cobertura de danos elétricos?" --recuperacao obrigatoria
```

**Exemplo de saída registrada** (resumido; o texto varia entre execuções):

```text
Tipo da pergunta: documentada nos trechos

Resposta:
  A franquia da cobertura de danos elétricos é de 10% do prejuízo, com mínimo de R$ 300,00. Ela só
  se aplica quando essa cobertura estiver contratada na apólice individual.

Evidências conferidas (cada citação aparece literalmente no trecho):
  [VLAR-FAQ-1_0-006] "danos elétricos têm 10% com mínimo de R$ 300,00;"
      Vareleira Lar — Perguntas frequentes para Atendimento e corretores · Como funciona a franquia? · versão 1.0 · vareleira-lar/faq-v1.0.md
  ...

Como esta resposta foi produzida:
  1. O programa buscou antes ('hibrida'): 5 trecho(s): VLAR-FAQ-1_0-006, VLAR-GL-1_0-009, ...
  2. O agente recebeu os trechos e a pergunta, sem ferramentas.
  3. O programa conferiu o tipo e as evidências (2 citação(ões) literais) e escolheu o texto mostrado.
  Uso (todas as idas ao modelo): 1644 tokens de entrada e 166 de saída (9 de raciocínio); busca: 15 tokens de embeddings.
```

**Atividade 2:** compare esta saída com a da Etapa 2.2 do Desafio 04 (`perguntar.py --politica completa`, com a mesma pergunta). Liste o que é igual e o que mudou.

**Conferência:** a busca e a política são as mesmas, enquanto a comunicação com o modelo usa o MAF.
O agente recebe os trechos sem ferramentas, e o programa lê a resposta com o esquema do Desafio 04.
Compare o tipo, as citações e o conteúdo das duas execuções; eles podem variar. O rastro identifica
essa recuperação obrigatória e informa o consumo de uma chamada ao modelo.

## Etapa 3: perguntar com a ferramenta de busca

**Objetivo:** observar o agente decidir quando e o que buscar, e ler o rastro. Esta etapa não altera o Azure.

### 3.1 Uma pergunta que mistura dois assuntos

```powershell
python scripts\agente_maf.py --busca $busca --modelos $modelos --deployment-geracao $deploymentGeracao --pergunta "O seguro cobre alagamento e quantas vezes posso acionar a assistência 24 horas?"
```

**Exemplo de saída registrada** (resumido; tipo, buscas, consultas e texto variam):

```text
Trechos recuperados (10):
  1. [VLAR-CG-1_0-006] pontuação 0.033 · 4. Assistência 24 horas: um serviço, não uma cobertura
  ...
  6. [VLAR-FAQ-1_0-011] pontuação 0.033 · O Vareleira Lar cobre alagamento ou enchente?
  ...

Tipo da pergunta: documentada nos trechos

Resposta:
  Não. Alagamento, inundação, enchente e ressaca são riscos excluídos desta versão do produto. Já a
  assistência 24 horas é um serviço separado da cobertura e pode ser acionada até 2 vezes por tipo
  de serviço em cada vigência, com pagamento da mão de obra até R$ 400,00 por acionamento.

Evidências conferidas (cada citação aparece literalmente no trecho):
  [VLAR-FAQ-1_0-011] "Não. Inundação, alagamento, enchente e ressaca estão entre os riscos excluídos ..."
  ...

Como esta resposta foi produzida:
  1. O agente recebeu a pergunta e as instruções, sem trechos.
  2. O agente chamou a ferramenta buscar_trechos 2 vez(es):
       busca 1: "alagamento assistência 24 horas quantas vezes acionar limite" → 5 trecho(s): VLAR-CG-1_0-006, ...
       busca 2: "alagamento cobertura imóvel água enchente inundação evento coberto" → 5 trecho(s): VLAR-FAQ-1_0-011, ...
  3. O programa conferiu o tipo e as evidências (3 citação(ões) literais) e escolheu o texto mostrado.
  Uso (todas as idas ao modelo): 5439 tokens de entrada e 372 de saída (81 de raciocínio); busca: 32 tokens de embeddings.
```

**Atividade 3:** leia o rastro. Quais consultas o agente escreveu e como elas se comparam com a pergunta original? Por que o total de trechos recuperados é maior que 5?

**Conferência:** no exemplo, o agente separou os assuntos em consultas e recuperou trechos sobre a
assistência e sobre alagamento. A lista "Trechos recuperados" reúne as fontes de todas as buscas,
sem repetição; as evidências precisam pertencer a essa lista. Na sua execução, confira se ambos os
assuntos chegaram ao modelo. Fazer uma segunda busca depende da decisão do agente: as séries
registradas incluíram tanto respostas documentadas como uma recusa `sem_evidencia`.

### 3.2 Perguntas que não precisam de busca

Antes de executar, anote se você espera que o agente busque em cada pergunta:

```powershell
python scripts\agente_maf.py --busca $busca --modelos $modelos --deployment-geracao $deploymentGeracao --pergunta "Qual é a capital da França?"
python scripts\agente_maf.py --busca $busca --modelos $modelos --deployment-geracao $deploymentGeracao --pergunta "Qual é o prazo?"
```

**Exemplo de saída registrada** (resumido):

```text
Tipo da pergunta: fora de escopo

Recusa:
  Esta pergunta não trata do Vareleira Lar nem de seguro residencial, e os documentos consultados não a cobrem.

Como esta resposta foi produzida:
  1. O agente recebeu a pergunta e as instruções, sem trechos.
  2. O agente não chamou a ferramenta: respondeu sem buscar.
  ...
  Uso (todas as idas ao modelo): 947 tokens de entrada e 46 de saída (15 de raciocínio); busca: 0 tokens de embeddings.
```

Para "Qual é o prazo?", o tipo é `ambígua`, e o texto é uma pergunta de esclarecimento, como no Desafio 04.

**Atividade 4:** compare sua previsão com o resultado. O que o agente dispensou, e o que isso economizou em relação ao Desafio 04?

**Conferência:** nas execuções registradas, o agente dispensou a ferramenta para essas duas perguntas.
Os tipos `fora_de_escopo` e `ambigua` permitem recusa ou esclarecimento sem busca. Essa decisão evita
embeddings e a inclusão de trechos no pedido, reduzindo o consumo em relação ao fluxo fixo.
Os tipos `documentada`, `contratacao_individual` e `sem_evidencia` exigem ao menos uma busca: sem ela,
o programa descarta a resposta com código 3.

### 3.3 A política continua valendo

```powershell
python scripts\agente_maf.py --busca $busca --modelos $modelos --deployment-geracao $deploymentGeracao --pergunta "Roubaram meu notebook na rua. O seguro paga?"
```

**O que conferir:** o tipo atribuído, a correspondência com as fontes, o aviso fixo de contratação
individual e as buscas no rastro. O texto e a quantidade de buscas dependem do modelo.

**Atividade 5:** leia a resposta e procure uma frase que conclua sobre o caso da pessoa, mesmo sem usar as palavras que a regra do programa detecta ("Sim.", "Não.", "seu seguro cobre", "será indenizado" e semelhantes).

**Conferência:** compare a resposta com a regra de roubo e furto qualificado e procure conclusões sobre
o caso individual. Uma execução registrada incluiu "Pela regra geral, a situação descrita na rua não se
enquadra nessa cobertura". Essa frase passou pelo detector do Desafio 04. O aviso permanece fixo,
e a conclusão sobre o caso ainda exige revisão. O Desafio 06 mede tipos, situações e fatos esperados,
sem substituir essa análise do sentido.

## Etapa 4: conhecer os limites do agente

**Objetivo:** perceber o que o agente melhora, o que ele custa e o que o programa precisa continuar controlando. Esta etapa não altera o Azure.

### 4.1 Poucos trechos por busca

```powershell
python scripts\agente_maf.py --busca $busca --modelos $modelos --deployment-geracao $deploymentGeracao --pergunta "O seguro cobre alagamento e quantas vezes posso acionar a assistência 24 horas?" --recuperacao obrigatoria --k 2
python scripts\agente_maf.py --busca $busca --modelos $modelos --deployment-geracao $deploymentGeracao --pergunta "O seguro cobre alagamento e quantas vezes posso acionar a assistência 24 horas?" --k 2
```

**Atividade 6:** execute cada comando três vezes e anote, em uma tabela, o tipo da pergunta, o número de buscas e os tokens de entrada. Qual modo respondeu à pergunta inteira? Por que o outro modo não respondeu?

**Referência para comparar sua medição:** sete execuções por comando no ambiente testado:

| Modo (`--k 2`) | Tipo da pergunta | Buscas | Tokens de entrada |
| --- | --- | --- | --- |
| Recuperação obrigatória | `sem_evidencia` nas 7 | 1, do programa | 1.108 |
| Recuperação por ferramenta | `documentada` em 5 e `sem_evidencia` em 2 | 2, do agente | de 3.736 a 4.043 |

**Conferência:** na amostra registrada, a busca única com `--k 2` trouxe dois trechos sobre a
assistência 24 horas (`VLAR-CG-1_0-006` e `VLAR-FAQ-1_0-003`) e deixou de fora o trecho das perguntas
frequentes (FAQ, *Frequently Asked Questions*) sobre alagamento (`VLAR-FAQ-1_0-011`). O fluxo fixo
recusou a pergunta inteira. Com uma consulta por assunto, o agente conseguiu reunir até quatro trechos,
mas ainda recusou em 2 das 7 execuções. O consumo de entrada ficou cerca de 3,5 vezes maior, porque as
chamadas posteriores ao modelo reenviam as instruções e os resultados anteriores.

### 4.2 Limite de uma busca

```powershell
python scripts\agente_maf.py --busca $busca --modelos $modelos --deployment-geracao $deploymentGeracao --pergunta "O seguro cobre alagamento e quantas vezes posso acionar a assistência 24 horas?" --maximo-de-buscas 1
```

O limite reduz as chamadas permitidas e restringe as oportunidades de completar a recuperação.
O fluxo fixo usa a pergunta inteira; o agente escreve uma consulta própria, que pode alcançar apenas
um dos assuntos.

**Atividade 7:** execute o comando três vezes. Em quais execuções a lista "Trechos recuperados" inclui `VLAR-FAQ-1_0-011`? O que o agente respondeu quando esse trecho faltou?

**Referência para comparar sua medição:** resultados registrados para a pergunta composta, com `--k 5`:

| Configuração | Execuções | `documentada` | `sem_evidencia` | `ambigua` |
| --- | --- | --- | --- | --- |
| Recuperação obrigatória (uma busca, com a pergunta inteira) | 5 | 5 | 0 | 0 |
| Agente com até 2 buscas (padrão) | 7 | 6 | 1 | 0 |
| Agente com até 1 busca | 12 | 3 | 7 | 2 |

A composição das amostras está nas
[séries de medição](../../docs/validacao/l100-05-agente-com-maf.md#séries-de-medição).

**Conferência:** confira se o rastro inclui fontes para os dois assuntos e compare-as com a resposta.
O programa pode aceitar `documentada` com citações válidas mesmo quando a resposta cobre só metade
da pergunta; esse caso apareceu na série registrada. Uma consulta por assunto pode melhorar a
recuperação, enquanto uma consulta que os mistura pode recuperar só um deles. O limite define quantas
tentativas o agente tem.

### 4.3 Falha da busca que o agente não relata

```powershell
python scripts\agente_maf.py --busca $busca --modelos $modelos --deployment-geracao $deploymentGeracao --deployment inexistente --pergunta "Qual é a franquia da cobertura de danos elétricos?"
python scripts\agente_maf.py --busca $busca --modelos $modelos --deployment-geracao $deploymentGeracao --deployment inexistente --pergunta "Qual é a franquia da cobertura de danos elétricos?" --detalhes
```

Nos dois comandos, `--deployment` é o deployment de embeddings, com um nome que não existe: toda busca da ferramenta falha. O segundo comando usa `--detalhes` e mostra o registro técnico.

**Resultado esperado:** o código de saída é 2, e a única resposta é o erro, sem tipo, sem resposta e sem evidências:

```text
[ERRO] O deployment 'inexistente' não foi encontrado no recurso 'ais-vlr-...'. Use o nome do deployment (saída nomeDeploymentEmbeddings da implantação), não o nome do modelo, e confira o nome do recurso.
```

**Atividade 8:** no resultado do segundo comando, procure a linha que contém "returning an error result to the model". Explique por que o programa mostra o erro e não a resposta que o agente daria depois da falha.

**Conferência:** o MAF não entrega o erro da ferramenta ao programa: ele devolve ao modelo um aviso genérico de falha, e o modelo decide o que escrever. Uma recusa produzida por uma busca com falha seria um "não sei" falso, porque o documento existe e a busca não o alcançou. A ferramenta guarda o primeiro erro, e o programa o apresenta, com a orientação do Desafio 02, no lugar da resposta.

## Etapa 5: testar o agente sem o Azure

**Objetivo:** executar os testes automáticos do agente. Eles não acessam o Azure nem consomem tokens.

```powershell
python -m unittest discover -s tests -p "test_agente.py"
```

**Resultado esperado:** uma linha de pontos, `Ran <N> tests` e `OK`.

**Atividade 9:** abra `tests\test_agente.py` e localize o teste do agente que responde sobre o produto sem buscar e o teste do limite de buscas. Descreva o que cada um garante e como o teste provoca a situação.

**Conferência:** os testes executam as bibliotecas MAF e OpenAI instaladas, com o transporte de rede
substituído pelo dublê `ServicoRespostasFalso`, de `tests\support.py`. O dublê responde a requisições
HTTP (*Hypertext Transfer Protocol*, protocolo de comunicação da web) seguindo um roteiro:
buscar, buscar, responder. A terceira requisição usa `tool_choice` igual a `none`, o que verifica o
desligamento da ferramenta no limite. O roteiro "responder sem buscar" verifica o descarte com
código 3, sem calcular embeddings.

## Como pedir uma mudança ao Copilot no VS Code

Use o [procedimento do Desafio 01](01-preparar-ambiente.md#como-pedir-uma-mudança-ao-copilot-no-vs-code):
contexto, plano, limites, revisão do diff (comparação entre versões dos arquivos) e verificação com
comandos autorizados. Em `lab_agente.py`, confira cada limite e argumento da ferramenta, porque eles
definem as ações permitidas ao agente.

### Exemplo: tornar o tempo máximo configurável

Cole com os arquivos anexados:

```text
Leia o README, o L100 Desafio 05, scripts/agente_maf.py e scripts/lab_agente.py anexados.
Quero uma opção nova em agente_maf.py: --tempo-maximo SEGUNDOS, que muda o tempo total que o agente pode levar (hoje, a constante TEMPO_MAXIMO).
Antes de editar, proponha o plano: arquivos, funções e testes.
Cuidados obrigatórios: valide o valor como número inteiro de 10 a 300 com o mesmo estilo dos outros argumentos (mensagem em pt-BR e código de saída 1);
o padrão continua sendo o valor atual; a mensagem de tempo esgotado cita o valor usado; o limite do laço do MAF (TEMPO_DO_LACO) continua menor que o tempo total;
não altere a política nem as instruções do agente.
Escreva testes com unittest e dublês, sem acessar o Azure.
Use o Python do ambiente virtual, .\.venv\Scripts\python.exe, e execute apenas:
.\.venv\Scripts\python.exe -m unittest discover -s tests
Não instale pacotes, não acesse o Azure e não altere o índice.
```

**Conferência:** o diff deve validar o argumento antes de usá-lo, manter o padrão atual, atualizar a mensagem de tempo esgotado e acrescentar testes para o valor válido, o inválido e a ausência da opção. Confira o acoplamento: com `--tempo-maximo 30`, o limite do laço (60 segundos) ficaria maior que o tempo total e deixaria de ter efeito. O Copilot pode esquecer de ajustar `TEMPO_DO_LACO` junto com o tempo total.

> **Dica:** peça uma explicação do diff, com palavras simples, antes de aceitá-lo. Outros pedidos para praticar: "explique cada teste de `test_agente.py` em uma frase" e "proponha três perguntas em que o agente deveria buscar duas vezes e uma em que não deveria buscar".

**Modo construtor (opcional).** Para ver como o Copilot resolveria o desafio, peça um plano em uma pasta separada e compare o resultado com os arquivos deste projeto pelo diff:

```text
Leia o L100, Desafio 05, o README e as instruções do projeto.
Proponha, sem editar, como um agente que busca por uma ferramenta deve ser limitado e verificado:
limite de chamadas, validação dos argumentos, registro dos trechos devolvidos, o que fazer quando a ferramenta falha e quando o agente responde sem buscar.
Defina quem decide o texto final mostrado à pessoa.
Não provisione recursos, atribua papéis, envie dados ou exclua arquivos.
```

Qualquer ação que altere o Azure continua dependendo da sua decisão.

## Conferência do resultado

| Verificação | Como conferir | Evidência esperada |
| --- | --- | --- |
| Dependências | Etapa 1.1 | `No broken requirements found.` e `Version: 1.15.0` |
| O que o agente recebe | Etapa 1.2 e a Atividade 1 | Instruções, ferramenta com o parâmetro `consulta` e limites |
| Recuperação obrigatória | Etapa 2 e a Atividade 2 | Tipo `documentada`, evidências conferidas e rastro sem ferramentas |
| Agente com ferramenta | Etapa 3.1 e a Atividade 3 | Uma ou duas buscas no rastro e evidências conferidas |
| Pergunta sem busca | Etapa 3.2 e a Atividade 4 | "O agente não chamou a ferramenta", com recusa ou esclarecimento do programa |
| Política mantida | Etapa 3.3 e a Atividade 5 | Aviso fixo no caso individual |
| Comparação dos modos | Etapas 4.1 e 4.2 e as Atividades 6 e 7 | Tipos, buscas e tokens anotados por modo |
| Falha da busca | Etapa 4.3 e a Atividade 8 | `[ERRO]` com código 2, sem resposta do agente |
| Testes sem Azure | `python -m unittest discover -s tests -p "test_agente.py"` | `OK` |

Antes de encerrar, registre em local privado o grupo de recursos, os nomes da busca e dos modelos e a decisão de manter, pausar ou remover os recursos. Ao compartilhar evidências, remova das saídas do terminal os identificadores do ambiente, os nomes de recursos e as contas de usuário.

## Solução de problemas

| Sintoma | O que conferir | O que evitar |
| --- | --- | --- |
| `[ERRO]` "Bibliotecas do Microsoft Agent Framework ou do Azure não encontradas" (código 1) | O ambiente virtual ativo e a Etapa 1.1: `python -m pip install -r requirements\l100.txt` | Instalar outras versões do MAF |
| `[FALHA]` "o agente respondeu sem buscar nos documentos: nenhuma busca foi feita" (código 3) | Repita o comando; se persistir, use `--recuperacao obrigatoria` | Remover a regra do programa para a resposta aparecer |
| `[FALHA]` "a citação de ... não aparece literalmente no trecho" ou "a fonte ... não está entre os trechos recuperados" (código 3) | Repita o comando; o agente pode ter parafraseado a citação. Se persistir, compare a citação com o trecho no rastro | Afrouxar a conferência |
| Recusa "sem evidência" para uma pergunta que os documentos respondem | As consultas no rastro: o agente buscou os dois assuntos? Aumente `--k` ou `--maximo-de-buscas`, ou compare com `--recuperacao obrigatoria` | Concluir que os documentos não têm a resposta |
| `[ERRO]` "O agente não terminou em 120 segundos" (código 2) | Repita com `--esforco none` ou `--maximo-de-buscas 1` | Aumentar o tempo sem entender o motivo |
| `[ERRO]` "O agente não terminou a resposta (limite de saída)" (código 2) | Repita com `--esforco low` ou `--esforco none`: o raciocínio consumiu o limite de saída | Aumentar o limite sem entender o consumo |
| `[ERRO]` "O modelo devolveu uma resposta fora do formato esperado" (código 2) | Repita o comando; se persistir, use `--detalhes` | Aceitar texto fora do formato |
| `[ERRO]` "O Azure respondeu 404 ('Subdomain does not map to a resource')" (código 2) | O nome em `$modelos`. Com o nome certo, o serviço de modelos às vezes responde assim de forma intermitente: aguarde alguns minutos e repita | Recriar o recurso ou o deployment só para o erro desaparecer |
| `[AVISO]` "O serviço de modelos respondeu 404 intermitente (tentativa N de 6)" | Nada: o programa repete sozinho esse erro. Se as seis tentativas falharem, siga a linha anterior | Interromper e recriar recursos |
| Ferramenta que escreve arquivos, executa comandos ou aceita o índice como argumento, proposta pelo Copilot | As instruções do projeto: a ferramenta do agente só lê, com modo e índice fixos pelo programa | Dar ao modelo uma ferramenta com efeito sobre arquivos ou sobre o Azure |
| Erros dos desafios anteriores (login, tenant, papéis, deployment, cota) | [Solução de problemas do Desafio 03](03-responder-com-fontes.md#solução-de-problemas) | Pular a conferência |

Se precisar de ajuda, consulte os [canais e limites do suporte](../../SUPPORT.md). Não conceda papéis,
altere políticas corporativas ou desative controles como tentativa de diagnóstico.

## Custos, pausa e limpeza

O uso do Copilot segue o plano da sua conta e as regras de consumo dele, separadamente da assinatura Azure. Este desafio não cria recursos: a cobrança do Azure continua vindo dos recursos dos Desafios 01 a 03.

**O que gera custo neste desafio:** os tokens de cada pergunta e, na recuperação por ferramenta, os embeddings de cada busca (de 10 a 20 tokens por busca). Cada ida ao modelo reenvia as instruções, a pergunta e os resultados anteriores, e por isso o agente com ferramenta usa mais tokens de entrada que o fluxo fixo. Na validação, a entrada somou:

| Pergunta | Modo | Tokens de entrada |
| --- | --- | --- |
| Franquia de danos elétricos (`k=5`) | Obrigatória | 1.644 |
| Franquia de danos elétricos (`k=5`) | Ferramenta, 1 busca | 3.087 |
| Pergunta composta (`k=5`) | Obrigatória | 1.414 |
| Pergunta composta (`k=5`) | Ferramenta, 1 busca | de 2.732 a 3.120 |
| Pergunta composta (`k=5`) | Ferramenta, 2 buscas | de 5.439 a 6.261 |
| Pergunta composta (`k=2`) | Obrigatória | 1.108 |
| Pergunta composta (`k=2`) | Ferramenta, 2 buscas | de 3.736 a 4.043 |
| Pergunta fora de escopo ou ambígua | Ferramenta, sem busca | 947 e 945 |

A saída ficou entre 43 e 578 tokens por pergunta, e o tempo, entre 6 e 22 segundos. Os custos em dinheiro não foram medidos, e os preços variam por região, modelo e data; consulte os [preços atuais dos modelos do Azure OpenAI](https://azure.microsoft.com/en-us/pricing/details/azure-openai/) [6].

**Pausa e limpeza.** Como o desafio não cria recursos, a pausa e a limpeza são as do [Desafio 03](03-responder-com-fontes.md#custos-pausa-e-limpeza) e do [Desafio 02](02-indexar-documentos.md#custos-pausa-e-limpeza).

## Situação da validação

Data de referência: 9 de outubro de 2026. O registro detalhado, com a matriz de testes, as séries de medição e as observações de operação, está em [docs\validacao\l100-05-agente-com-maf.md](../../docs/validacao/l100-05-agente-com-maf.md).

**Versões testadas:** Windows, Python 3.12.10, Azure CLI 2.89.0, `agent-framework-core` 1.21.0, `agent-framework-openai` 1.15.0, `openai` 3.23.0, `azure-search-documents` 12.0.0 e as bibliotecas dos desafios anteriores.

| Item | Situação | Detalhe |
| --- | --- | --- |
| Comandos das Etapas 1 a 5 | Concluído | Executados em PowerShell 7.6, em `brazilsouth`, sobre o ambiente dos Desafios 01 a 03 |
| Scripts e testes automáticos (sem Azure) | Concluído | Testes aprovados, com a biblioteca MAF instalada e o serviço de modelos simulado |
| Links, âncoras, URLs e referências dos guias | Concluído | Nenhum link ou âncora inválido |
| Aprovação do conteúdo dos documentos sintéticos | Confirmada | Pelo mantenedor, em 9 de outubro de 2026; registro no inventário |
| Aprovação do texto, do código e dos resultados | Confirmada | Pelo mantenedor, em 9 de outubro de 2026; não representa novos testes |
| Outros ambientes: macOS, Linux, WSL (Windows Subsystem for Linux), Python diferente do 3.12 e Windows PowerShell 5.1 | Pendente | Executar os comandos do guia nesses ambientes e registrar as diferenças |
| Outros modelos de geração, outras versões do MAF e outras perguntas | Pendente | Só o `gpt-5.4-mini` e as versões fixadas foram validados, com uma pergunta composta e poucas perguntas simples; o Desafio 06 amplia a amostra |
| Agente que responde sem buscar sobre o produto, no Azure | Pendente | Coberto só por testes automáticos; não ocorreu nas execuções da validação |
| Interações com o Copilot: prompts do guia, exemplo de pedido de mudança e modo construtor | Pendente | Executar no VS Code e registrar as respostas |
| Custo | Pendente | Medir o custo no Cost Management após uma execução completa |

**Autoria.** Código, testes e texto produzidos com apoio de inteligência artificial (IA), com Claude
Sonnet 5.5 no GitHub Copilot CLI; o Astra estava indisponível. Revisão editorial por GPT-6.1 Sol, em
9 de outubro de 2026. Os modelos de autoria e revisão são independentes do modelo escolhido no Copilot
e dos deployments da aplicação Azure (`text-embedding-3-small` e `gpt-5.4-mini`).

## Glossário

| Termo | Significado no exercício |
| --- | --- |
| Agente | Programa que combina um modelo, instruções e ferramentas e repete o ciclo "o modelo pede, o programa executa" até a resposta final |
| Microsoft Agent Framework (MAF) | Biblioteca de código aberto da Microsoft para criar agentes e fluxos de trabalho com agentes |
| Ferramenta (de função) | Função do programa que o modelo pode pedir, descrita por nome, descrição e parâmetros |
| Chamada de ferramenta | Pedido do modelo para executar uma ferramenta com certos argumentos |
| Laço (do agente) | Ciclo de pedir a ferramenta, executá-la e devolver o resultado ao modelo, até a resposta final |
| Esquema JSON (da ferramenta) | Descrição, em JSON, dos parâmetros que o modelo pode enviar a uma ferramenta |
| JSON | Formato de texto estruturado em pares nome-valor |
| API Responses | Interface do serviço de modelos em que o programa envia o pedido e recebe a resposta; o MAF a usa por meio do `OpenAIChatClient` |
| Recuperação obrigatória | Modo em que o programa busca antes do modelo e entrega os trechos ao agente, sem ferramentas |
| Recuperação por ferramenta | Modo em que o agente decide quando e o que buscar, por uma ferramenta |
| Consulta | Texto que a ferramenta recebe para buscar no índice; na recuperação por ferramenta, o agente a escreve |
| `k` | Quantidade de trechos que cada busca devolve e que o modelo recebe |
| Ida ao modelo | Uma chamada ao deployment de geração; o agente com ferramenta faz uma e mais uma por busca |
| Rastro | Registro do que o agente fez: as buscas, os trechos devolvidos e os tokens usados |
| Token | Fragmento de texto que o modelo conta e cobra, na entrada e na saída |
| Política (de resposta) | Regras do programa que decidem o que a pessoa vê; a `completa`, do Desafio 04, classifica, confere citações literais e recusa |
| Evidência | Par formado pelo id de um trecho e por uma frase copiada dele que sustenta a resposta |
| Descarte (da resposta) | Decisão do programa de não mostrar a resposta porque ela não passou na verificação |
| Veredito | Afirmação ou negação de que um caso está coberto ou será pago |
| Falso negativo | Caso em que uma regra deixa de agir quando devia, como uma frase de veredito que a regra por palavras não reconhece |
| Ataque indireto | Instrução escondida em um documento ou em outro dado que o modelo lê, na tentativa de mudar o que ele faz |
| FAQ | *Frequently Asked Questions*: perguntas frequentes |
| HTTP | Protocolo de comunicação da web, usado nos pedidos ao serviço de modelos |
| Dublê (de teste) | Peça que imita um serviço externo nos testes; aqui, o serviço de modelos simulado de `tests\support.py` |

## Referências

Fontes oficiais consultadas em 9 de outubro de 2026. Nomes de interface, limites, preços e disponibilidade mudam: confira a versão atual antes de aplicar.

1. [Microsoft Agent Framework: visão geral](https://learn.microsoft.com/en-us/agent-framework/overview/).
2. [Usar ferramentas de função com um agente](https://learn.microsoft.com/en-us/agent-framework/agents/tools/function-tools).
3. [Provedor OpenAI do Microsoft Agent Framework, inclusive com o Azure OpenAI](https://learn.microsoft.com/en-us/agent-framework/integrations/by-component/model-providers/openai).
4. [Produzir saídas estruturadas com agentes](https://learn.microsoft.com/en-us/agent-framework/agents/structured-outputs).
5. [Prompt Shields: ataques diretos e indiretos a modelos de linguagem](https://learn.microsoft.com/en-us/azure/ai-services/content-safety/concepts/jailbreak-detection).
6. [Preços dos modelos do Azure OpenAI](https://azure.microsoft.com/en-us/pricing/details/azure-openai/).

As atribuições do contexto fictício estão em [NOTICE.md](../../NOTICE.md). O texto deste guia está sob a licença Creative Commons Atribuição 4.0 (CC BY 4.0; veja [LICENSE](../../LICENSE)).
