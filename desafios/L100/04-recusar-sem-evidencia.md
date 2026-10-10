# L100 — Desafio 04: reconhecer a falta de evidência e recusar o que os documentos não autorizam

[Início do laboratório](../../README.md) · Nível L100: fundamentos · [Desafio 03](03-responder-com-fontes.md)

| Item | Descrição |
| --- | --- |
| Situação | Exercício executável, validado no Azure em 9 de outubro de 2026 (Windows e PowerShell). Os documentos de seguro são sintéticos e novos. Estão pendentes a revisão do conteúdo pelo mantenedor e a revisão humana do texto; veja [Situação da validação](#situação-da-validação). |
| Público | Pessoas de negócio, arquitetura, operações e desenvolvimento. Use o Visual Studio Code (VS Code) para executar os comandos e conferir os resultados; escrever código é opcional. |
| Pré-requisito | [Desafio 03](03-responder-com-fontes.md) concluído: este desafio usa o deployment de geração e o programa `perguntar.py` que ele criou. |
| Resultado | A opção `--politica completa` do `perguntar.py`: o modelo propõe o tipo e a resposta; o programa aplica as regras de classificação, confere as citações literais e escolhe entre resposta, recusa, esclarecimento e descarte. |
| Custo | Nenhum recurso novo. Cada pergunta consome tokens como no Desafio 03; as instruções da política completa acrescentam texto ao pedido. Veja [Custos, pausa e limpeza](#custos-pausa-e-limpeza). |

## Conteúdo

- [Cenário](#cenário)
- [Objetivos](#objetivos)
- [Artefatos e disponibilidade](#artefatos-e-disponibilidade)
- [Tecnologias e conceitos](#tecnologias-e-conceitos)
- [Reaproveitamento e acréscimos](#reaproveitamento-e-acréscimos)
- [Pré-requisitos](#pré-requisitos)
- [Etapa 1: ver o limite da política básica](#etapa-1-ver-o-limite-da-política-básica)
- [Etapa 2: aplicar a política completa](#etapa-2-aplicar-a-política-completa)
- [Etapa 3: testar as regras sem o Azure](#etapa-3-testar-as-regras-sem-o-azure)
- [Etapa 4: conhecer os limites das regras](#etapa-4-conhecer-os-limites-das-regras)
- [Como pedir uma mudança ao Copilot no VS Code](#como-pedir-uma-mudança-ao-copilot-no-vs-code)
- [Conferência do resultado](#conferência-do-resultado)
- [Solução de problemas](#solução-de-problemas)
- [Custos, pausa e limpeza](#custos-pausa-e-limpeza)
- [Situação da validação](#situação-da-validação)
- [Glossário](#glossário)
- [Referências](#referências)

## Cenário

Em 2025, na história fictícia da Vareleira, o Atendimento já recebe respostas com fonte (Desafio 03). Beatriz Torres, responsável pelo Atendimento, leva duas respostas a Teresa Moura, diretora técnica de Subscrição. Na primeira, a pergunta sobre um notebook roubado na rua recebeu um "Não." direto, como se o assistente tivesse analisado a apólice daquela pessoa. Na segunda, a pergunta sobre o preço do seguro só foi bem tratada porque o modelo se lembrou de admitir que não sabia.

Teresa define a regra do piloto: o assistente explica o produto; a apólice individual é a fonte para
conferir as coberturas contratadas (Condições Gerais sintéticas, cláusulas 1.3 e 11.1).
O programa precisa aplicar verificações próprias, porque o modelo pode ignorar instruções.

**Missão:** passar essas regras do pedido para o programa. O programa classifica a pergunta, exige evidências verificáveis e escolhe o texto que a pessoa vê, inclusive o texto das recusas.

> **Lembre-se:** o cenário é fictício. Não use apólices, nomes, endereços ou documentos de segurados reais, mesmo que tenha acesso a eles no trabalho.

## Objetivos

Ao concluir este desafio, você terá:

- visto como a política básica do Desafio 03 deixa o modelo dar um veredito sobre o caso de uma pessoa;
- classificado perguntas em cinco tipos e observado o que o programa mostra em cada um;
- conferido que cada evidência é uma citação literal de um trecho recuperado, e que o programa descarta a resposta quando não é;
- observado recusas com texto do programa para perguntas sem evidência e fora de escopo, e o aviso que acompanha a explicação geral de um caso individual;
- executado os testes automáticos da política, sem Azure;
- explicado os limites das regras: classificação errada, palavras que as regras não preveem, veredito escrito de outro modo e recuperação incompleta.

**Próximos desafios:** o [Desafio 05](05-agente-com-maf.md) implementa o agente com Microsoft Agent Framework (MAF); o [Desafio 06](06-avaliar-respostas.md) mede a qualidade da recuperação e das respostas; o [Desafio 07](07-identidade-da-aplicacao.md) usa service principal (identidade de uma aplicação no Microsoft Entra ID) e Azure Key Vault (serviço de guarda de segredos).

> **Para guardar na memória: C-P-R.** **C**lassifique a pergunta, **P**rocure as citações nos trechos
> e **R**evise a resposta antes de usá-la. A citação literal confirma a origem da evidência;
> a revisão confere o sentido da resposta. Mnemônico criado para este curso.

## Artefatos e disponibilidade

| Artefato | Onde encontrar | Situação |
| --- | --- | --- |
| Desafio anterior (deployment de geração e `perguntar.py`) | [03-responder-com-fontes.md](03-responder-com-fontes.md) | Disponível; pré-requisito |
| Pergunta e resposta no console, com a opção `--politica` | [scripts\perguntar.py](../../scripts/perguntar.py) | Disponível; validado |
| Regras da política: tipos, evidências literais e textos fixos | [scripts\lab_politica.py](../../scripts/lab_politica.py) | Disponível; validado |
| Regras de contexto, pedido, saída e fontes | [scripts\lab_geracao.py](../../scripts/lab_geracao.py) | Disponível |
| Testes automáticos da política (sem Azure) | [tests\test_politica.py](../../tests/test_politica.py) | Disponíveis |
| Documentos sintéticos e inventário | [dados\l100\inventario.json](../../dados/l100/inventario.json) | Disponível; aprovação do mantenedor confirmada |

> **Atenção:** este desafio não altera o Azure. As perguntas só leem o índice, mas consomem tokens, que são cobrados por uso. A decisão de executar é sua, mesmo quando você pede ao Copilot que "implemente" ou "corrija" algo.

## Tecnologias e conceitos

| Componente | Função neste desafio | Limite ou cuidado |
| --- | --- | --- |
| Política completa (`--politica completa`) | Aplica regras ao tipo proposto, confere as evidências e escolhe o texto mostrado | A qualidade depende também da classificação, da recuperação e da revisão do texto |
| Saída estruturada em JSON (*JavaScript Object Notation*, formato de dados em texto) | O modelo devolve `tipo`, `resposta` e uma lista de `evidencias`. O esquema limita os valores de `tipo` com `enum`, uma lista de valores permitidos [1] | O formato é imposto pelo esquema; a fidelidade do conteúdo exige conferência |
| Regras do programa (`lab_politica.py`) | Guardam os textos das recusas, conferem as citações e identificam algumas formas de caso individual | As condições estão no código; frases que essas condições não preveem podem passar |
| Deployment de geração e busca | Os do Desafio 03, sem mudança | |

**Conceitos necessários:** quem decide, evidência literal, caso individual e limites das regras.

**1. Quem decide.** O modelo **propõe** o tipo e a resposta; o programa aplica a política e **decide**
o que a pessoa vê. As recusas e o aviso de contratação individual usam textos fixos de
`lab_politica.py`. Quando a resposta passa pelas verificações, o conteúdo continua sendo proposto
pelo modelo e precisa de revisão.

Os cinco tipos de pergunta e a conduta do programa:

| Tipo | Quando ocorre | O que o programa mostra |
| --- | --- | --- |
| `documentada` | Os trechos trazem a regra pedida | A resposta do modelo, com as evidências conferidas |
| `contratacao_individual` | A pessoa pergunta se o seguro dela cobre ou paga um caso dela | Texto do modelo ou frase padrão quando o detector reconhece um veredito, com evidências e aviso fixo |
| `sem_evidencia` | O assunto é do produto, mas os trechos não trazem a informação | Uma recusa com texto do programa; nada do que o modelo escreveu |
| `fora_de_escopo` | A pergunta não trata do Vareleira Lar nem de seguro residencial | Uma recusa com texto do programa |
| `ambigua` | A pergunta admite mais de um sentido | A pergunta de esclarecimento escrita pelo modelo |

**2. Evidência literal.** Em cada resposta de tipo `documentada` ou `contratacao_individual`, o modelo lista as **evidências**: o id do trecho e uma frase copiada dele, com pelo menos 20 caracteres. O programa procura a frase no texto do trecho, sem diferenciar maiúsculas de minúsculas e ignorando marcas de Markdown (como `**`) e espaços repetidos. Uma citação que não aparece no trecho, ou que aponta para um trecho que não foi recuperado, descarta a resposta inteira: o programa não a mostra. As citações com menos de 20 caracteres são ignoradas e não contam como evidência. Sem nenhuma evidência válida, a resposta também é descartada.

> **Para guardar na memória: a nota fiscal.** Cada evidência é um item da nota fiscal da resposta. O fiscal (o programa) abre a caixa e confere se o item da nota está mesmo no estoque, que são os trechos recuperados. Nota com item que não existe invalida a entrega inteira. Analogia criada para este curso.

**3. Caso individual.** O modelo propõe o tipo. A regra do programa muda `documentada` para
`contratacao_individual` quando encontra um possessivo ("meu", "minha") junto de um assunto de seguro
("seguro", "apólice", "imóvel", "sinistro"). Se o detector de veredito reconhece formas como "Sim.",
"Não.", "seu seguro cobre" ou "será indenizado", o programa substitui o texto por uma frase padrão
e mantém as evidências. Todo caso classificado como individual recebe o aviso fixo.

**4. Limites.** Confira quatro situações:

1. **Classificação:** o modelo pode propor o tipo errado.
2. **Regra por palavras:** uma pergunta geral com "meu corretor" pode receber o aviso de caso individual
   (falso positivo), enquanto um caso sem possessivo pode passar pela regra (falso negativo).
3. **Veredito:** o detector procura formas específicas. Uma abertura como "Em regra, não." pode passar
   mesmo quando conclui sobre o caso da pessoa.
4. **Recuperação:** a ausência de um trecho necessário limita a informação disponível para a resposta.

Uma citação literal também pode acompanhar uma explicação que distorce seu sentido. Compare o texto da
resposta com a fonte. O Desafio 06 mede tipos, situações e frases esperadas; a revisão do sentido continua
necessária.

Instruções escondidas em documentos são ataques indiretos. Marcar os trechos como dados e limitar as
ações do programa reduz a exposição a esses ataques [2].

## Reaproveitamento e acréscimos

| Item | Situação | Observação |
| --- | --- | --- |
| Infraestrutura no Azure | Reaproveitada, sem alteração | Nenhum recurso novo, nenhum papel novo |
| `perguntar.py` | Inclui `--politica` | O padrão continua sendo `basica`, a do Desafio 03 |
| `lab_politica.py` | **Novo** | Tipos, instruções e esquema da política completa, conferência das evidências e textos fixos |
| `lab_geracao.py` | Pequenas extensões | O contrato de saída aceita listas de objetos, e a descrição da fonte pode sair sem o id |
| Testes | `tests\test_politica.py` novo | Cobrem as regras e o `perguntar.py` com a política completa, sem Azure |
| Reverter | Omitir `--politica` | O pedido volta às instruções do Desafio 03 |

## Pré-requisitos

Os comandos deste guia são escritos para Windows e PowerShell, no terminal integrado do Visual Studio Code (VS Code), como nos desafios anteriores.

| Pré-requisito | Como preparar | Necessário agora? |
| --- | --- | --- |
| Desafio 03 concluído | O deployment de geração criado e `perguntar.py` funcionando, no mesmo grupo de recursos e na mesma assinatura | Sim |
| Variáveis do terminal | `$assinatura`, `$grupo`, `$busca`, `$modelos` e `$deploymentGeracao` definidas (veja abaixo) | Sim |
| Ambiente virtual do Python | O mesmo do Desafio 01, com `requirements\l100.txt` instalado | Sim |
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

## Etapa 1: ver o limite da política básica

**Objetivo:** observar um comportamento que as instruções do Desafio 03 não impedem. Com a política básica, o programa só confere que as fontes citadas foram recuperadas.

Com o ambiente virtual do Desafio 01 ativo (ou use `.\.venv\Scripts\python.exe` no lugar de `python`):

```powershell
python scripts\perguntar.py --busca $busca --modelos $modelos --deployment-geracao $deploymentGeracao --pergunta "Roubaram meu notebook na rua. O seguro paga?" --k 10
```

**Exemplo de saída registrada** (resumido; o texto varia entre execuções):

```text
Resposta:
  Não. O seguro não indeniza bens portáteis levados para fora do imóvel segurado. A cobertura de
  roubo e furto qualificado vale para o conteúdo do imóvel subtraído mediante arrombamento ou roubo
  no imóvel, com boletim de ocorrência.

Fontes citadas:
  [VLAR-CG-1_0-007] Vareleira Lar — Condições Gerais · 5. Riscos excluídos (cláusulas 5.1, 5.2) · versão 1.0 · ...
  [VLAR-CG-1_0-005] Vareleira Lar — Condições Gerais · 3. Coberturas adicionais (cláusulas 3.4, 3.5) · versão 1.0 · ...
```

**Atividade 1:** localize, na resposta, a frase que afirma ou nega a cobertura do caso. Explique por que o programa não deveria mostrá-la como está.

**Conferência:** a resposta começa com "Não.", um veredito sobre o caso de uma pessoa. As fontes estão corretas e a regra geral citada existe (cláusula 5.1, item h), mas as Condições Gerais descrevem regras do produto: elas não dizem o que foi contratado por quem perguntou nem se o caso será aceito. Só a apólice individual comprova as coberturas contratadas (cláusulas 1.3 e 11.1). A conferência das fontes não percebe o problema, porque as citações são válidas.

## Etapa 2: aplicar a política completa

**Objetivo:** ver o que o programa faz com cada tipo de pergunta. Esta etapa não altera o Azure.

### 2.1 Ver o pedido da política completa

```powershell
python scripts\perguntar.py --busca $busca --modelos $modelos --deployment-geracao $deploymentGeracao --pergunta "Roubaram meu notebook na rua. O seguro paga?" --k 10 --politica completa --sem-geracao
```

O comando recupera os trechos e mostra o pedido, sem chamar o modelo de geração. Compare as instruções com as do Desafio 03: elas agora pedem a classificação em cinco tipos, dizem o que escrever em cada tipo e exigem que cada evidência traga o id do trecho e uma frase copiada exatamente, com pelo menos 20 caracteres. O trecho final do pedido, com a pergunta, não mudou.

### Prompt para o Copilot: entender a política antes de executar

Anexe `scripts\lab_politica.py` e `scripts\perguntar.py`:

```text
Leia scripts/lab_politica.py e scripts/perguntar.py anexados.
Explique, para quem não programa e com uma analogia, o que o programa decide e o que o modelo decide em cada um dos cinco tipos de pergunta.
Diga onde o programa confere as citações literais e o que acontece quando uma citação não aparece no trecho.
Liste uma pergunta que a regra por palavras trataria como caso individual sem ser, e uma que ela deixaria passar.
Não edite arquivos, não execute comandos e não acesse o Azure.
```

**Conferência:** a resposta deve citar `verificar_evidencias` e `aplicar_politica`, dizer que a resposta é descartada quando uma citação não está no trecho e que os textos das recusas vêm do programa. Confira cada afirmação no código: o Copilot pode inventar regras que o programa não tem.

### 2.2 Pergunta documentada

```powershell
python scripts\perguntar.py --busca $busca --modelos $modelos --deployment-geracao $deploymentGeracao --pergunta "Qual é a franquia da cobertura de danos elétricos?" --politica completa
```

**Exemplo de saída registrada** (resumido):

```text
Tipo da pergunta: documentada nos trechos

Resposta:
  A franquia da cobertura de danos elétricos é de 10% do prejuízo, com mínimo de R$ 300,00.

Evidências conferidas (cada citação aparece literalmente no trecho):
  [VLAR-FAQ-1_0-006] "danos elétricos têm 10% com mínimo de R$ 300,00"
      Vareleira Lar — Perguntas frequentes para Atendimento e corretores · Como funciona a franquia? · versão 1.0 · vareleira-lar/faq-v1.0.md
  ...

Como esta resposta foi produzida:
  1. A pergunta virou um vetor (15 tokens de embeddings).
  2. A busca 'hibrida' devolveu 5 trecho(s): ...
  3. O deployment 'geracao' classificou a pergunta e propôs a resposta.
  4. O programa conferiu o tipo e as evidências (3 citação(ões) literais) e escolheu o texto mostrado.
  Uso na geração: 1644 tokens de entrada e 227 de saída (15 de raciocínio).
```

As evidências variam a cada execução. O que não varia é a regra: cada citação mostrada aparece no trecho indicado.

### 2.3 Caso individual

```powershell
python scripts\perguntar.py --busca $busca --modelos $modelos --deployment-geracao $deploymentGeracao --pergunta "Roubaram meu notebook na rua. O seguro paga?" --k 10 --politica completa
```

**Exemplo de saída registrada** (resumido):

```text
Tipo da pergunta: contratação individual

Resposta:
  Pela regra geral do produto, bens portáteis levados para fora do imóvel segurado não são
  indenizados. A cobertura de roubo e furto qualificado indeniza o conteúdo do imóvel subtraído
  mediante arrombamento ou mediante roubo no imóvel. Portanto, a análise do caso concreto depende da
  apólice e das circunstâncias do evento, ...

Evidências conferidas (cada citação aparece literalmente no trecho):
  [VLAR-CG-1_0-007] "h) bens portáteis levados para fora do imóvel segurado;"
      Vareleira Lar — Condições Gerais · 5. Riscos excluídos (cláusulas 5.1, 5.2) · versão 1.0 · ...
  ...

Aviso:
  Esta resposta explica a regra geral do produto. Só a apólice individual comprova as coberturas
  contratadas (Condições Gerais, cláusulas 1.3 e 11.1). Para saber se o seu caso está coberto,
  consulte o Atendimento ou o seu corretor.
```

**Atividade 2:** compare esta resposta com a da Etapa 1. Liste três diferenças e diga se a resposta ainda traz algum veredito, mesmo atenuado.

**Conferência:** compare a resposta com a exclusão da cláusula 5.1, item h, e confira as evidências e o
aviso fixo. Procure uma conclusão sobre o caso da pessoa, inclusive aberturas como "Em regra, não.".
Essa forma passa pelo detector. No ambiente testado, vereditos atenuados apareceram em 6 de 9 execuções;
a distribuição está no
[registro do limite do detector](../../docs/validacao/l100-04-recusar-sem-evidencia.md#alterações-posteriores-à-validação).

### 2.4 Pergunta sem evidência

```powershell
python scripts\perguntar.py --busca $busca --modelos $modelos --deployment-geracao $deploymentGeracao --pergunta "Quanto custa o seguro por mês?" --politica completa
```

**Exemplo de saída registrada** (resumido):

```text
Tipo da pergunta: sem evidência nos documentos

Recusa:
  Não encontrei, nos documentos consultados, a informação necessária para responder a esta pergunta.
  Reformule a pergunta ou consulte o Atendimento.
```

O texto da recusa é do programa. Mesmo que o modelo escrevesse uma resposta, o programa não a mostraria.

### 2.5 Pergunta fora de escopo

```powershell
python scripts\perguntar.py --busca $busca --modelos $modelos --deployment-geracao $deploymentGeracao --pergunta "Qual é a capital da França?" --politica completa
```

**Exemplo de saída registrada:** `Tipo da pergunta: fora de escopo` e a recusa "Esta pergunta não trata
do Vareleira Lar nem de seguro residencial, e os documentos consultados não a cobrem."

### 2.6 Pergunta ambígua

```powershell
python scripts\perguntar.py --busca $busca --modelos $modelos --deployment-geracao $deploymentGeracao --pergunta "Qual é o prazo?" --politica completa
```

**Exemplo de saída registrada** (resumido; a pergunta de esclarecimento varia):

```text
Tipo da pergunta: ambígua

Pergunta de esclarecimento:
  Prazo de quê: da vigência, do pagamento do prêmio, do aviso de sinistro ou da análise do sinistro?
```

**Atividade 3:** antes de executar as perguntas das Etapas 2.2 a 2.6, escreva o tipo que você espera para cada uma. Depois execute e compare. Em quais o modelo e você divergiram?

**Conferência:** "Quanto é a franquia?" admite dois critérios: responder as franquias de todas as
coberturas (`documentada`) ou pedir a cobertura desejada (`ambigua`). Registre o critério do produto
antes de avaliar o tipo proposto pelo modelo. No Desafio 06, cada pergunta tem um tipo esperado
definido no conjunto de avaliação.

## Etapa 3: testar as regras sem o Azure

**Objetivo:** executar os testes locais da política com dublês, objetos que simulam o modelo e o
índice. Eles dispensam Azure e consumo de tokens.

```powershell
python -m unittest discover -s tests -p "test_politica.py"
```

**Resultado esperado:** uma linha de pontos, `Ran <N> tests` e `OK`.

**Atividade 4:** abra `tests\test_politica.py`, localize o teste que descarta uma resposta com citação inventada e descreva o que ele garante. Depois leia os dois testes que conferem que a política básica continua sendo o padrão e que o pedido da completa usa instruções e esquema próprios.

**Conferência:** o teste da citação inventada fornece ao programa uma resposta do modelo cuja citação não está em nenhum trecho e confirma que o programa não a mostra e sai com código 3. Os outros dois testes confirmam que, sem `--politica`, o pedido tem as instruções do Desafio 03 e que, com `--politica completa`, o pedido leva as instruções e o esquema da política completa.

## Etapa 4: conhecer os limites das regras

**Objetivo:** perceber o que a política não resolve. Os comandos abaixo repetem perguntas com configurações que expõem os limites.

### 4.1 Recuperação incompleta

```powershell
python scripts\perguntar.py --busca $busca --modelos $modelos --deployment-geracao $deploymentGeracao --pergunta "Roubaram meu notebook na rua. O seguro paga?" --k 5 --politica completa
```

**Atividade 5:** compare esta resposta com a da Etapa 2.3, que usou `--k 10`. Que informação falta, e por quê?

**Conferência:** no exemplo registrado com `--k 5`, o trecho das exclusões (cláusula 5.1) ficou fora do
pedido. A resposta explicou a cobertura de roubo e furto qualificado e trouxe o aviso. Confira a lista
da sua execução e procure também vereditos atenuados: o aviso acompanha a resposta, mas a revisão do
texto continua necessária.

### 4.2 Falso positivo da regra por palavras

```powershell
python scripts\perguntar.py --busca $busca --modelos $modelos --deployment-geracao $deploymentGeracao --pergunta "Como o meu corretor avisa um sinistro?" --politica completa
```

**Exemplo de saída registrada** (resumido):

```text
Tipo da pergunta: contratação individual (o modelo classificou como documentada nos trechos; uma regra do programa mudou o tipo)

Resposta:
  O aviso de sinistro pode ser feito pelo atendimento ou pelo corretor. Ele deve ser comunicado
  assim que o segurado souber do evento e, no máximo, em 7 dias corridos.
...
Aviso:
  Esta resposta explica a regra geral do produto. ...
```

**Atividade 6:** por que o programa mudou o tipo? A mudança causou algum dano? Como você reduziria esse falso positivo sem criar falsos negativos?

**Conferência:** a pergunta contém "meu" e "sinistro", e a regra a tratou como caso individual, embora
ela peça um procedimento. O efeito observado foi um aviso desnecessário. Uma exceção para perguntas de
procedimento pode reduzir esse falso positivo e também deixar passar casos individuais. Avalie ambas
as consequências antes de alterar a regra.

## Como pedir uma mudança ao Copilot no VS Code

Use o [procedimento do Desafio 01](01-preparar-ambiente.md#como-pedir-uma-mudança-ao-copilot-no-vs-code):
contexto, plano, limites, revisão do diff (comparação entre versões dos arquivos) e verificação com
comandos autorizados. Uma mudança em `lab_politica.py` altera a resposta exibida; revise os textos fixos
de recusa e aviso.

### Exemplo: tornar o tamanho mínimo da citação configurável

Cole com os arquivos anexados:

```text
Leia o README, o L100 Desafio 04, scripts/perguntar.py e scripts/lab_politica.py anexados.
Quero uma opção nova em perguntar.py: --minimo-citacao N, que muda o tamanho mínimo, em caracteres, das citações literais da política completa.
Antes de editar, proponha o plano: arquivos, funções e testes.
Cuidados obrigatórios: valide N como inteiro de 10 a 200 com o mesmo estilo dos outros argumentos (mensagem em pt-BR e código de saída 1);
o padrão continua sendo o valor atual de MINIMO_DA_CITACAO; a política básica ignora a opção; mantenha os textos fixos de recusa e aviso;
nas instruções da política completa, ajuste apenas o mínimo solicitado ao modelo para que ele corresponda ao valor usado pelo programa.
Escreva testes com unittest e dublês, sem acessar o Azure.
Use o Python do ambiente virtual, .\.venv\Scripts\python.exe, e execute apenas:
.\.venv\Scripts\python.exe -m unittest discover -s tests
Não instale pacotes, não acesse o Azure e não altere o índice.
```

**Conferência:** o diff deve validar o argumento, manter o padrão atual e os textos fixos e acrescentar
testes para valores válidos, inválidos e para a ausência da opção. Confira se o mínimo nas instruções
enviadas ao modelo coincide com o mínimo aplicado pelo programa.

> **Dica:** peça uma explicação do diff, com palavras simples, antes de aceitá-lo. Outros pedidos para praticar: "explique cada teste de `test_politica.py` em uma frase" e "proponha três perguntas novas que a regra por palavras trataria de modo errado".

**Modo construtor (opcional).** Para ver como o Copilot resolveria o desafio, peça um plano em uma pasta separada e compare o resultado com os arquivos deste projeto pelo diff:

```text
Leia o L100, Desafio 04, o README e as instruções do projeto.
Proponha, sem editar, como um programa que responde com base em trechos recuperados deve tratar: pergunta sem informação nos documentos, pergunta fora de escopo, pergunta ambígua e pergunta sobre o caso de uma pessoa.
Defina quem decide o texto de cada recusa e como o programa confere as citações do modelo.
Não provisione recursos, atribua papéis, envie dados ou exclua arquivos.
```

Qualquer ação que altere o Azure continua dependendo da sua decisão.

## Conferência do resultado

| Verificação | Como conferir | Evidência esperada |
| --- | --- | --- |
| Limite da política básica | Etapa 1 e a Atividade 1 | Você identifica o veredito sobre o caso individual |
| Pedido da política completa | Etapa 2.1 | Instruções com os cinco tipos e a exigência de citação literal |
| Pergunta documentada | Etapa 2.2 | Tipo `documentada`, resposta e evidências conferidas |
| Caso individual | Etapa 2.3 e a Atividade 2 | Regra geral, evidências e aviso fixo; um veredito atenuado pode passar pela regra |
| Pergunta sem evidência | Etapa 2.4 | Recusa com o texto do programa, sem fontes |
| Pergunta fora de escopo | Etapa 2.5 | Recusa com o texto do programa |
| Pergunta ambígua | Etapa 2.6 | Pergunta de esclarecimento |
| Testes sem Azure | `python -m unittest discover -s tests -p "test_politica.py"` | `OK` |
| Limites explicados | Atividades 5 e 6 | Você explica a recuperação incompleta e o falso positivo |

Antes de encerrar, registre em local privado o grupo de recursos, os nomes da busca e dos modelos e a decisão de manter, pausar ou remover os recursos. Ao compartilhar evidências, remova das saídas do terminal os identificadores do ambiente, os nomes de recursos e as contas de usuário.

## Solução de problemas

| Sintoma | O que conferir | O que evitar |
| --- | --- | --- |
| `[FALHA]` "A resposta do modelo foi descartada" com "não aparece literalmente no trecho" (código 3) | Repita o comando; o modelo pode ter parafraseado, trocado a pontuação ou usado reticências. Se persistir, use `--mostrar-prompt` e compare a citação com o trecho | Afrouxar a conferência para a resposta aparecer |
| `[FALHA]` com "nenhuma evidência foi informada" ou "nenhuma citação tem pelo menos 20 caracteres" (código 3) | Repita o comando; se persistir em uma pergunta de tipo `documentada`, aumente `--k` ou mude o modo | Reduzir o mínimo de caracteres sem entender o efeito |
| `[FALHA]` com "a fonte ... não está entre os trechos recuperados" (código 3) | Repita o comando; a citação de um id inexistente é o sinal de uma resposta inventada | Aceitar a resposta |
| Recusa "sem evidência" para uma pergunta que os documentos respondem | Se o trecho necessário foi recuperado (`--mostrar-prompt`); aumente `--k` ou mude `--modo` | Concluir que os documentos não têm a resposta |
| Aviso de caso individual em uma pergunta geral | A pergunta tem um possessivo junto de um assunto de seguro (Atividade 6); reformule sem "meu" ou "minha" | Remover o aviso do programa |
| Resposta de caso individual com a frase padrão no lugar do texto do modelo | O modelo afirmou ou negou a cobertura do caso; o programa trocou o texto e manteve as evidências | Reaproveitar o texto original do modelo |
| Erros dos desafios anteriores (login, tenant, papéis, deployment, cota) | [Solução de problemas do Desafio 03](03-responder-com-fontes.md#solução-de-problemas) | Pular a conferência |

Se precisar de ajuda, consulte os [canais e limites do suporte](../../SUPPORT.md). Não conceda papéis,
altere políticas corporativas ou desative controles como tentativa de diagnóstico.

## Custos, pausa e limpeza

O uso do Copilot segue o plano da sua conta e as regras de consumo dele, separadamente da assinatura Azure. Este desafio não cria recursos: a cobrança do Azure continua vindo dos recursos dos Desafios 01 a 03.

**O que gera custo neste desafio:** os tokens de cada pergunta. As instruções da política completa são maiores que as da básica, e a resposta traz as evidências. Na validação, uma pergunta usou de 1.223 a 2.565 tokens de entrada e de 46 a 476 de saída, conforme a pergunta e o `k`. Os custos não foram medidos, e os preços variam por região, modelo e data; consulte os [preços atuais dos modelos do Azure OpenAI](https://azure.microsoft.com/en-us/pricing/details/azure-openai/) [3].

**Pausa e limpeza.** Como o desafio não cria recursos, a pausa e a limpeza são as do [Desafio 03](03-responder-com-fontes.md#custos-pausa-e-limpeza) e do [Desafio 02](02-indexar-documentos.md#custos-pausa-e-limpeza).

## Situação da validação

Data de referência: 9 de outubro de 2026. O registro detalhado, com a matriz de testes, as medições e as observações de operação, está em [docs\validacao\l100-04-recusar-sem-evidencia.md](../../docs/validacao/l100-04-recusar-sem-evidencia.md).

**Versões testadas:** Windows, Python 3.12.10, Azure CLI (interface de linha de comando) 2.89.0, `openai` 3.23.0, `azure-search-documents` 12.0.0 e as bibliotecas dos desafios anteriores.

| Item | Situação | Detalhe |
| --- | --- | --- |
| Comandos das Etapas 1 a 4 | Concluído | Executados em PowerShell 7.6, em `brazilsouth`, sobre o ambiente dos Desafios 01 a 03 |
| Scripts e testes automáticos (sem Azure) | Concluído | Testes aprovados |
| Links, âncoras, URLs e referências dos guias | Concluído | Nenhum link ou âncora inválido |
| Aprovação do conteúdo dos documentos sintéticos | Confirmada | Pelo mantenedor, em 9 de outubro de 2026; registro no inventário |
| Aprovação do texto, do código e dos resultados | Confirmada | Pelo mantenedor, em 9 de outubro de 2026; limites do detector preservados |
| Outros ambientes: macOS, Linux, WSL (Windows Subsystem for Linux), Python diferente do 3.12 e Windows PowerShell 5.1 | Pendente | Executar os comandos do guia nesses ambientes e registrar as diferenças |
| Outros modelos de geração e outras perguntas | Pendente | Só o `gpt-5.4-mini` foi validado, com poucas perguntas por tipo; o Desafio 06 amplia a amostra |
| Resposta descartada por citação inventada no Azure | Pendente | Coberta só por testes automáticos; não ocorreu nas execuções da validação |
| Detector de veredito | Limite conhecido | Reconhece só "Sim" ou "Não" no início e frases fixas; um veredito atenuado, como "Em regra, não.", passou em 6 de 9 execuções do caso do notebook (detalhes no registro de validação) |
| Interações com o Copilot: prompts do guia, exemplo de pedido de mudança e modo construtor | Pendente | Executar no VS Code e registrar as respostas |
| Custo | Pendente | Medir o custo no Cost Management após uma execução completa |

**Autoria.** Código, testes e texto produzidos com apoio de inteligência artificial (IA), com Claude
Sonnet 5.5 no GitHub Copilot CLI; o Astra estava indisponível. Revisão editorial por GPT-6.1 Sol, em
9 de outubro de 2026. Os modelos de autoria e revisão são independentes do modelo escolhido no Copilot
e dos deployments da aplicação Azure (`text-embedding-3-small` e `gpt-5.4-mini`).

## Glossário

| Termo | Significado no exercício |
| --- | --- |
| Política (de resposta) | Conjunto de regras que decide o que a pessoa vê; `basica` confere as fontes citadas, e `completa` também classifica, confere citações literais e recusa |
| Tipo (da pergunta) | Classificação da pergunta em `documentada`, `contratacao_individual`, `sem_evidencia`, `fora_de_escopo` ou `ambigua` |
| Apólice individual | Documento que identifica o segurado, o imóvel, as coberturas contratadas, os limites e as franquias de cada contratação |
| Contratação individual | Caso em que a pessoa pergunta se o seguro dela cobre ou paga um caso dela |
| Veredito | Afirmação ou negação de que um caso está coberto ou será pago |
| Evidência | Par formado pelo id de um trecho e por uma frase copiada dele que sustenta a resposta |
| Citação literal | Frase que aparece exatamente no texto do trecho, ignorando maiúsculas, marcas de Markdown e espaços repetidos |
| Descarte (da resposta) | Decisão do programa de não mostrar a resposta do modelo porque ela não passou na verificação |
| Recusa | Resposta do programa que explica que os documentos não autorizam responder; o texto é do programa |
| Pergunta de esclarecimento | Pergunta que o modelo faz quando a pergunta original admite mais de um sentido |
| Regra do programa | Verificação escrita no código, que vale independentemente do que o modelo responde |
| Falso positivo | Caso em que uma regra age sem necessidade, como o aviso de caso individual em uma pergunta geral |
| Falso negativo | Caso em que uma regra deixa de agir quando devia, como um caso individual escrito sem possessivo |
| Ataque indireto | Instrução escondida em um documento ou em outro dado que o modelo lê, na tentativa de mudar o que ele faz |
| Saída estruturada | Formato de resposta imposto por um esquema JSON, aqui com `tipo`, `resposta` e `evidencias` |
| JSON | Formato de texto estruturado em pares nome-valor |
| Recuperação incompleta | Situação em que a busca não traz um trecho necessário, e a resposta fica incompleta mesmo sem erro do modelo |
| `k` | Quantidade de trechos que a busca devolve e que o modelo recebe |

## Referências

Fontes oficiais consultadas em 9 de outubro de 2026. Nomes de interface, limites, preços e disponibilidade mudam: confira a versão atual antes de aplicar.

1. [Saídas estruturadas](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/structured-outputs).
2. [Prompt Shields: ataques diretos e indiretos a modelos de linguagem](https://learn.microsoft.com/en-us/azure/ai-services/content-safety/concepts/jailbreak-detection).
3. [Preços dos modelos do Azure OpenAI](https://azure.microsoft.com/en-us/pricing/details/azure-openai/).

As atribuições do contexto fictício estão em [NOTICE.md](../../NOTICE.md). O texto deste guia está sob a licença Creative Commons Atribuição 4.0 (CC BY 4.0; veja [LICENSE](../../LICENSE)).
