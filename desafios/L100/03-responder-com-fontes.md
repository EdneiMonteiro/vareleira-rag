# L100 — Desafio 03: responder com fontes

[Início do laboratório](../../README.md) · Nível L100: fundamentos · [Desafio 02](02-indexar-documentos.md)

| Item | Descrição |
| --- | --- |
| Situação | Exercício executável, validado no Azure e aprovado pelo mantenedor em 9 de outubro de 2026 (Windows e PowerShell). Os documentos de seguro são sintéticos. Veja os limites em [Situação da validação](#situação-da-validação). |
| Público | Pessoas de negócio, arquitetura, operações e desenvolvimento. Use o Visual Studio Code (VS Code) para executar os comandos e conferir os resultados; escrever código é opcional. |
| Pré-requisito | [Desafio 02](02-indexar-documentos.md) concluído: este desafio consulta o índice e o recurso de modelos que ele criou. |
| Resultado | Um programa de console que recebe uma pergunta, recupera trechos do índice, pede a um modelo de geração que responda só com esses trechos e mostra a resposta, as fontes citadas e o caminho percorrido. |
| Custo | O deployment de geração cobra por token processado e não cobra por existir. O serviço de busca do Desafio 02 continua cobrando por hora. Veja [Custos, pausa e limpeza](#custos-pausa-e-limpeza). |

## Conteúdo

- [Cenário](#cenário)
- [Objetivos](#objetivos)
- [Artefatos e disponibilidade](#artefatos-e-disponibilidade)
- [Tecnologias e conceitos](#tecnologias-e-conceitos)
- [Reaproveitamento e acréscimos](#reaproveitamento-e-acréscimos)
- [Pré-requisitos](#pré-requisitos)
- [Etapa 1: ver o pedido que o modelo recebe](#etapa-1-ver-o-pedido-que-o-modelo-recebe)
- [Etapa 2: criar o deployment de geração com Bicep](#etapa-2-criar-o-deployment-de-geração-com-bicep)
- [Etapa 3: perguntar com fontes](#etapa-3-perguntar-com-fontes)
- [Etapa 4: comparar modo de busca, quantidade de trechos e esforço](#etapa-4-comparar-modo-de-busca-quantidade-de-trechos-e-esforço)
- [Como pedir uma mudança ao Copilot no VS Code](#como-pedir-uma-mudança-ao-copilot-no-vs-code)
- [Conferência do resultado](#conferência-do-resultado)
- [Solução de problemas](#solução-de-problemas)
- [Custos, pausa e limpeza](#custos-pausa-e-limpeza)
- [Situação da validação](#situação-da-validação)
- [Glossário](#glossário)
- [Referências](#referências)

## Cenário

Em 2025, na história fictícia da Vareleira, Beatriz Torres, responsável pelo Atendimento, já dispõe da busca
do Desafio 02. O Atendimento e os corretores querem uma resposta escrita em português que explique a
regra e mostre de onde ela vem. Teresa Moura, diretora técnica de Subscrição, exige que as afirmações possam
ser localizadas nos documentos.

**Missão:** ligar a busca a um modelo de geração de texto. O pedido orienta o modelo a usar os trechos
recuperados e citar as fontes; o programa verifica se os identificadores citados pertencem à busca.
Você compara o conteúdo da resposta com as fontes. O Desafio 04 acrescenta regras para perguntas sem
evidência e sobre uma contratação individual.

> **Lembre-se:** o cenário é fictício. Não use apólices, nomes, endereços ou documentos de segurados reais, mesmo que tenha acesso a eles no trabalho.

## Objetivos

Ao concluir este desafio, você terá:

- visto, sem chamar o modelo de geração, o pedido exato que ele recebe: instruções, trechos e pergunta;
- criado, com Bicep, um deployment de geração no recurso de modelos do Desafio 02;
- obtido respostas que citam os trechos usados e conferido, por script, que cada fonte citada foi recuperada;
- comparado como o modo de busca, a quantidade de trechos e o esforço de raciocínio mudam a resposta e o uso de tokens;
- explicado um caso em que a recuperação incompleta produz uma resposta incompleta;
- aprendido a remover o deployment de geração e a limpar o laboratório.

**Próximos desafios:** o [Desafio 04](04-recusar-sem-evidencia.md) reconhece a falta de evidência e recusa o que os documentos não autorizam; o [Desafio 05](05-agente-com-maf.md) implementa o agente com Microsoft Agent Framework (MAF); o [Desafio 06](06-avaliar-respostas.md) mede a qualidade da recuperação e das respostas; o [Desafio 07](07-identidade-da-aplicacao.md) usa service principal (identidade de uma aplicação no Microsoft Entra ID) e Azure Key Vault (serviço de guarda de segredos).

> **Para guardar na memória: B-M-C.** Para responder com fontes, **B**usque os trechos, **M**onte o pedido e **C**onfira as citações. Mnemônico criado para este curso.

## Artefatos e disponibilidade

| Artefato | Onde encontrar | Situação |
| --- | --- | --- |
| Desafio anterior (índice com 54 trechos) | [02-indexar-documentos.md](02-indexar-documentos.md) | Disponível; pré-requisito |
| Infraestrutura (Bicep), com o parâmetro `implantarGeracao` | [infra\main.bicep](../../infra/main.bicep) | Disponível; validada |
| Módulo do deployment de geração | [infra\modules\geracao.bicep](../../infra/modules/geracao.bicep) | Disponível; validado |
| Parâmetros do Desafio 03 | [infra\levels\l100-desafio03.bicepparam](../../infra/levels/l100-desafio03.bicepparam) | Disponível; validado |
| Pergunta e resposta no console | [scripts\perguntar.py](../../scripts/perguntar.py) | Disponível; validado |
| Regras de contexto, pedido, saída e fontes | [scripts\lab_geracao.py](../../scripts/lab_geracao.py) | Disponível |
| Regras de busca e erros dos desafios anteriores | [scripts\lab_indexacao.py](../../scripts/lab_indexacao.py) e [scripts\lab_comum.py](../../scripts/lab_comum.py) | Disponíveis |
| Documentos sintéticos e inventário | [dados\l100\inventario.json](../../dados/l100/inventario.json) | Disponível; aprovação do mantenedor confirmada |
| Dependências Python | [requirements\l100.txt](../../requirements/l100.txt) | Disponível; sem mudança |
| Testes automáticos (sem Azure) | pasta `tests` | Disponíveis |

> **Atenção:** os momentos que alteram o Azure têm a marca **[altera o Azure]**: criar o deployment de geração (Etapa 2) e remover recursos. As perguntas das Etapas 1, 3 e 4 só leem o índice, mas consomem tokens, que são cobrados por uso. A decisão de executar é sua, mesmo quando você pede ao Copilot que "implemente" ou "corrija" algo.

## Tecnologias e conceitos

| Tecnologia | Função neste desafio | Limite ou cuidado |
| --- | --- | --- |
| Deployment de geração | Instância nomeada do modelo `gpt-5.4-mini`, que escreve texto a partir de instruções e de um contexto [1][2] | Pode produzir afirmações sem apoio nos trechos; a comparação com as fontes exige revisão |
| API Responses | Interface de programação de aplicações (API, *Application Programming Interface*) em que o script envia o pedido e recebe a resposta [3] | O serviço guarda a resposta por 30 dias por padrão; o script envia `store=False` |
| Saída estruturada | Obriga o modelo a devolver um JSON (*JavaScript Object Notation*, texto estruturado em pares nome-valor) com os campos `resposta` e `fontes` [4] | Garante o formato, não a verdade do conteúdo |
| Biblioteca `openai` | Chama o deployment com a sua identidade, como nos embeddings do Desafio 02 | Autentica com token do Entra ID, sem chave de API |
| Microsoft Entra ID e papéis | O papel `Cognitive Services OpenAI User`, atribuído no Desafio 02 ao recurso de modelos, também permite usar o deployment de geração [5] | Nenhum papel novo é necessário |

**Conceitos necessários:** geração com recuperação, pedido ao modelo, raciocínio e conferência das fontes.

**1. Geração com recuperação.** A **geração aumentada por recuperação** (RAG, do inglês *Retrieval-Augmented Generation*) separa dois trabalhos: o programa busca os trechos nos documentos e o modelo escreve a resposta com base neles. O modelo não consulta o índice: ele só enxerga o que o programa coloca no pedido.

**2. Pedido ao modelo.** O pedido tem três partes: as **instruções** (as regras do trabalho), o **contexto** (os trechos recuperados, cada um com seu identificador, ou ID) e a **pergunta**. O script marca cada trecho com `<trecho>` e trata o conteúdo como dado: uma frase de um documento que mande "ignorar as regras" não é uma ordem. Instruções escondidas em documentos são um tipo de ataque indireto, e essa marcação reduz o risco, mas não o elimina [6].

> **Para guardar na memória: o dossiê do estagiário.** O pedido é um dossiê entregue a um estagiário: a folha de regras, as páginas recortadas dos documentos e a pergunta do cliente. O estagiário só pode usar as páginas do dossiê e precisa dizer de qual página tirou cada informação. Analogia criada para este curso.

**3. Modelos de raciocínio.** O `gpt-5.4-mini` é um modelo de raciocínio: antes de escrever, ele gera **tokens de raciocínio**, que não aparecem na resposta, ocupam espaço no contexto e são cobrados como tokens de saída [7]. O parâmetro **esforço** (`--esforco`: `none`, `low`, `medium` ou `high`) controla quanto o modelo raciocina [7]. Esses modelos não aceitam o parâmetro `temperature`, por isso o script não o envia [7].

**4. Conferência das fontes.** O modelo devolve os identificadores dos trechos que declara ter usado.
O script compara cada identificador com a lista recuperada e bloqueia respostas com fontes desconhecidas.
Essa conferência verifica a origem declarada. Você verifica a correspondência entre cada afirmação e
o conteúdo da fonte nas atividades.

## Reaproveitamento e acréscimos

| Item | Situação | Observação |
| --- | --- | --- |
| Conta de armazenamento, índice, serviço de busca, recurso de modelos e deployment de embeddings | Reaproveitados, sem alteração | Este desafio só lê o índice e usa o deployment de embeddings para a pergunta |
| `main.bicep` | Inclui o parâmetro `implantarGeracao`, desligado por padrão | Os parâmetros do Desafio 02 preservam os recursos daquele desafio |
| Deployment de geração | **Novo**, criado por `l100-desafio03.bicepparam` | Cobra por token; veja [Custos, pausa e limpeza](#custos-pausa-e-limpeza) |
| Papéis de dados | Nenhum novo | O papel `Cognitive Services OpenAI User` do Desafio 02 vale para todos os deployments do recurso |
| `requirements\l100.txt` | Sem mudança | A biblioteca `openai` já está instalada |
| Scripts dos Desafios 01 e 02 | Sem mudança de comportamento | Com `--detalhes`, `lab_comum.py` passou a mostrar também o erro original de um erro já traduzido |
| Reverter | Excluir só o deployment de geração mantém o restante | Os comandos estão em [Custos, pausa e limpeza](#custos-pausa-e-limpeza) |

## Pré-requisitos

Os comandos deste guia são escritos para Windows e PowerShell, no terminal integrado do Visual Studio Code (VS Code), como nos desafios anteriores.

| Pré-requisito | Como preparar | Necessário agora? |
| --- | --- | --- |
| Desafio 02 concluído | `verificar_indice.py` aprovado, no mesmo grupo de recursos e na mesma assinatura | Sim |
| Variáveis do terminal | `$assinatura`, `$grupo`, `$busca` e `$modelos` definidas (veja abaixo) | Sim |
| Ambiente virtual do Python | O mesmo do Desafio 01, com `requirements\l100.txt` instalado | Sim |
| Assinatura Azure ativa | Use a assinatura autorizada nos desafios anteriores | Sim |
| Permissão para criar recursos | Papel como *Contributor* no grupo de recursos | Sim, na Etapa 2 |
| Permissão para atribuir papéis | O arquivo reaplica os papéis anteriores quando `VARELEIRA_ID_OBJETO_CARGA` está preenchida; executar essa implantação exige permissão para atribuí-los | Sim, com a variável preenchida |
| Cota do modelo de geração | Confira abaixo; o Bicep reserva 50 mil tokens por minuto | Sim |
| Aceitar o custo | O deployment cobra por token; o serviço de busca continua cobrando por hora | Sim |

Em um terminal novo, defina as variáveis de novo. Substitua `<ID-DA-SUA-ASSINATURA>` e use o nome do grupo criado no Desafio 01:

```powershell
$assinatura = "<ID-DA-SUA-ASSINATURA>"
$grupo = "<NOME-DO-GRUPO-EXCLUSIVO-AUTORIZADO>"
$busca = az deployment group show --subscription $assinatura --resource-group $grupo --name vareleira-rag-l100-d02 --query properties.outputs.nomeBusca.value --output tsv
$modelos = az deployment group show --subscription $assinatura --resource-group $grupo --name vareleira-rag-l100-d02 --query properties.outputs.nomeModelos.value --output tsv
$busca
$modelos
```

**Resultado esperado:** `srch-vlr-...` e `ais-vlr-...`, os nomes do serviço de busca e do recurso de modelos do Desafio 02.

### Conferir região, modelo e cota (somente leitura)

O deployment de geração fica na região do recurso de modelos, que pode diferir da região do grupo.
Os comandos abaixo consultam a região efetiva desse recurso, o catálogo e a cota [8].
A consulta ajustada da região foi conferida documentalmente nesta revisão, sem nova execução Azure:

```powershell
$regiao = az cognitiveservices account show --subscription $assinatura --resource-group $grupo --name $modelos --query location --output tsv
(az cognitiveservices model list --subscription $assinatura --location $regiao --output json | ConvertFrom-Json) | Where-Object { $_.model.name -eq "gpt-5.4-mini" } | Select-Object -First 1 | ForEach-Object { "$($_.model.name) versao $($_.model.version) ($($_.model.lifecycleStatus)): $(($_.model.skus | ForEach-Object { $_.name }) -join ', ')" }
(az cognitiveservices usage list --subscription $assinatura --location $regiao --output json | ConvertFrom-Json) | Where-Object { $_.name.value -eq "OpenAI.GlobalStandard.gpt-5.4-mini" } | ForEach-Object { "usado $($_.currentValue) de $($_.limit)" }
```

**Resultado esperado** (em `brazilsouth`): `gpt-5.4-mini versao 2026-03-17 (GenerallyAvailable): GlobalStandard, GlobalProvisionedManaged, GlobalBatch` e `usado <N> de <limite>`. A cota livre é o limite menos o valor em uso, e ela precisa cobrir a capacidade do Bicep (50). No Windows PowerShell 5.1, os números aparecem com casa decimal (`1000.0`). Se a cota livre for menor que 50, avalie reduzir `capacidadeGeracao` no `what-if` e na implantação da Etapa 2. Se o modelo não aparecer ou outra região for necessária, interrompa e planeje uma migração autorizada, preservando o recurso existente.

O catálogo de modelos muda. O `gpt-5.4-mini` versão `2026-03-17` tem aposentadoria prevista para 21 de setembro de 2027 [9]. Depois dessa data o deployment deixa de funcionar, e a troca de modelo exige repetir as conferências da Etapa 4.

## Etapa 1: ver o pedido que o modelo recebe

**Objetivo:** entender o pedido antes de pagar pela geração. Esta etapa recupera os trechos do índice e mostra o pedido, sem chamar o modelo de geração; o único consumo é o embedding da pergunta (cerca de 10 tokens).

Com o ambiente virtual do Desafio 01 ativo (ou use `.\.venv\Scripts\python.exe` no lugar de `python`):

```powershell
python scripts\perguntar.py --busca $busca --modelos $modelos --pergunta "Qual é a franquia da cobertura de danos elétricos?" --k 3 --sem-geracao
```

**Resultado esperado** (resumido):

```text
Pergunta: Qual é a franquia da cobertura de danos elétricos?
Recuperação: modo hibrida · 3 trecho(s) · serviço de busca '<busca>', índice 'vareleira-lar-l100'
Trechos recuperados (3):
  1. [VLAR-FAQ-1_0-006] pontuação 0.033 · Como funciona a franquia?
  2. [VLAR-GL-1_0-009] pontuação 0.033 · Danos elétricos
  3. [VLAR-FAQ-1_0-002] pontuação 0.032 · Danos elétricos estão incluídos em todas as contratações do Vareleira Lar?

--- Instruções enviadas ao modelo ---
Você consulta as Condições Gerais, o glossário e as perguntas frequentes do Vareleira Lar, ...
...
--- Entrada enviada ao modelo ---
<trecho id="VLAR-FAQ-1_0-006" documento="VLAR-FAQ-1.0" versao="1.0" secao="Como funciona a franquia?" clausulas="-">
## Como funciona a franquia?
...
</trecho>
...
Pergunta: Qual é a franquia da cobertura de danos elétricos?
--- Fim do pedido ---

Simulação: o modelo de geração não foi chamado. Repita sem --sem-geracao para obter a resposta.
```

Os ids e as pontuações dependem do índice, e a ordem pode variar. A pontuação da busca híbrida fica na faixa de 0,02 a 0,04 porque combina duas listas por posição; só ordena resultados do mesmo modo (veja o Desafio 02).

O pedido tem três blocos:

1. as **instruções**: quatro regras que mandam responder só com os trechos, citar os ids usados, admitir quando os trechos não informam e escrever em português, em até 120 palavras;
2. o **contexto**: um bloco `<trecho>` por trecho recuperado, com o id e os metadados (documento, versão, seção e cláusulas);
3. a **pergunta**, sempre no fim.

O pedido não inclui o nome do serviço de busca nem o do recurso de modelos.

**Atividade 1:** localize, no bloco de entrada, a frase que informa a franquia de danos elétricos e o id do trecho que a contém. Depois abra `dados\l100\documentos\vareleira-lar-condicoes-gerais-v1.0.md` e encontre a mesma regra na cláusula 6.3.

**Conferência:** o trecho `VLAR-FAQ-1_0-006` traz a frase "danos elétricos têm 10% com mínimo de R$ 300,00", e a tabela de franquias da cláusula 6.3 das Condições Gerais traz a mesma regra. O modelo ainda não participou: tudo o que ele recebe está nesta tela.

### Prompt para o Copilot: entender o fluxo antes de executar

Anexe `scripts\perguntar.py` e `scripts\lab_geracao.py`:

```text
Leia scripts/perguntar.py e scripts/lab_geracao.py anexados.
Explique, para quem não programa e com uma analogia, o caminho de uma pergunta: busca, montagem do pedido, chamada ao modelo e conferência das fontes.
Mostre onde o script decide o que vai ao modelo e onde confere as fontes citadas.
Liste dois riscos de uma resposta gerada por modelo e diga qual deles a conferência das fontes cobre.
Não edite arquivos, não execute comandos e não acesse o Azure.
```

**Conferência:** a resposta deve citar as funções `montar_contexto`, `montar_pedido` e `fontes_desconhecidas`, e dizer que a conferência cobre citações de trechos que não foram recuperados, não respostas que distorcem um trecho recuperado. Confira cada afirmação no código: o Copilot pode inventar regras que o script não tem.

## Etapa 2: criar o deployment de geração com Bicep

**[altera o Azure]** nos comandos `az deployment group create`.

**Objetivo:** acrescentar ao recurso de modelos do Desafio 02 um segundo deployment, o de geração.
O [módulo de geração](../../infra/modules/geracao.bicep) referencia o recurso existente.
O [arquivo principal](../../infra/main.bicep) chama esse módulo quando `implantarGeracao` é verdadeiro, e
os [parâmetros do Desafio 03](../../infra/levels/l100-desafio03.bicepparam) habilitam o deployment e
mantêm as escolhas anteriores. [10]

Se você personalizou nomes, regiões, camada ou capacidade no Desafio 02, informe os mesmos valores
no `what-if` e na implantação deste desafio. O arquivo de parâmetros não lê as escolhas anteriores.
Não mude a região de um recurso existente para resolver falta de cota: interrompa e planeje uma
migração autorizada. Tampouco reaplique o L100 sobre recursos isolados pelo L300/L400, pois isso
pode reabrir seu acesso público.

### Decisões de configuração do Bicep

| Decisão do Bicep | O que faz | Por que importa |
| --- | --- | --- |
| Modelo `gpt-5.4-mini`, versão `2026-03-17` | Usa um modelo de raciocínio com saída estruturada e chamada de ferramentas [1] | Foi usado nas medições do exercício; confira disponibilidade e preço antes de trocá-lo |
| Versão fixa (`NoAutoUpgrade`) | Evita atualização automática da versão selecionada | O texto das respostas ainda varia entre execuções com a mesma versão |
| Tipo `GlobalStandard`, capacidade 50 | Cobra por tokens usados; a capacidade 50 reserva 50 mil tokens por minuto de cota | A capacidade define a cota reservada, e a cobrança vem dos tokens usados [2] |
| Módulo que referencia o recurso de modelos | Acrescenta o deployment ao recurso existente | O arquivo principal também mantém o módulo de indexação e suas atribuições de papéis |
| Dependência do módulo do Desafio 02 | Serializa as operações no mesmo recurso | O recurso recusa alterações simultâneas nos deployments |

### Prompt para o Copilot: entender o Bicep

```text
Leia infra/main.bicep, infra/modules/geracao.bicep e infra/levels/l100-desafio03.bicepparam anexados.
Explique, para quem não programa, o que o Desafio 03 cria e o que ele reaproveita do Desafio 02.
Diga o que o what-if mostrará quando o Desafio 02 já foi implantado e o que acontece se a variável VARELEIRA_ID_OBJETO_CARGA estiver vazia.
Aponte qualquer coisa que pareça insegura ou que eu deva conferir antes de implantar.
Não edite arquivos nem execute comandos.
```

**Conferência:** a resposta deve dizer que só o deployment de geração é novo, que o recurso de modelos e os papéis vêm do Desafio 02 e que o what-if lista como mudança real só a criação do deployment. Se a resposta sugerir ligar chaves, abrir o acesso ou executar algo agora, peça a correção.

### 2.1 Informar quem opera o laboratório

Use o terminal e as variáveis definidas em Pré-requisitos. Defina a mesma variável dos desafios anteriores; ela vale só nesta sessão do terminal: [11]

```powershell
$env:VARELEIRA_ID_OBJETO_CARGA = az ad signed-in-user show --query id --output tsv
```

O comando não imprime nada quando conclui com sucesso.

O deployment usa o papel `Cognitive Services OpenAI User` já atribuído no Desafio 02. O arquivo de
parâmetros também reaplica as atribuições anteriores quando a variável está preenchida. Se você pode
implantar recursos, mas não atribuir papéis, peça essa implantação a um administrador ou mantenha a
variável ausente e preserve os papéis já concedidos. Confira as permissões de dados antes das perguntas.

Se seguir a alternativa com a variável ausente, omita o bloco da Etapa 2.1 e a linha
`Remove-Item Env:\VARELEIRA_ID_OBJETO_CARGA` da Etapa 2.3. O restante da implantação permanece igual.

### 2.2 Simular a implantação (what-if)

O **what-if** mostra o que seria criado, sem criar nada: [12]

```powershell
az deployment group what-if --subscription $assinatura --resource-group $grupo --name vareleira-rag-l100-d03 --parameters infra\levels\l100-desafio03.bicepparam
```

**Resultado esperado:** uma criação, `deployments/geracao`. A previsão registrada também mostrou
cinco itens `~ Modify` por propriedades preenchidas pelos serviços, terminando em
`Resource changes: 1 to create, 5 to modify, 5 no change.` Confira os detalhes da sua previsão.
Se houver exclusão de recurso (`- Delete`) ou recriação do armazenamento, da busca ou do deployment
de embeddings, interrompa e confira o grupo e os parâmetros.

### 2.3 Implantar

Execute a implantação e remova a variável:

```powershell
az deployment group create --subscription $assinatura --resource-group $grupo --name vareleira-rag-l100-d03 --parameters infra\levels\l100-desafio03.bicepparam
Remove-Item Env:\VARELEIRA_ID_OBJETO_CARGA
```

**Tempo de referência:** de 70 a 80 segundos, medidos em `brazilsouth`. Para mudar a cota, acrescente
`--parameters capacidadeGeracao=<mil-tokens-por-minuto>` ao comando.

### 2.4 Registrar o nome do deployment

```powershell
$deploymentGeracao = az deployment group show --subscription $assinatura --resource-group $grupo --name vareleira-rag-l100-d03 --query properties.outputs.nomeDeploymentGeracao.value --output tsv
$deploymentGeracao
```

**Resultado esperado:** `geracao`, o nome do deployment, que o script usa por padrão. O nome do deployment e o nome do modelo (`gpt-5.4-mini`) são valores distintos.

### 2.5 Conferir o deployment

```powershell
az cognitiveservices account deployment show --subscription $assinatura --resource-group $grupo --name $modelos --deployment-name $deploymentGeracao --query "{Deployment:name,Modelo:properties.model.name,Versao:properties.model.version,Implantacao:sku.name,Capacidade:sku.capacity,Atualizacao:properties.versionUpgradeOption}" --output json
```

**Resultado esperado:**

```text
{
  "Atualizacao": "NoAutoUpgrade",
  "Capacidade": 50,
  "Deployment": "geracao",
  "Implantacao": "GlobalStandard",
  "Modelo": "gpt-5.4-mini",
  "Versao": "2026-03-17"
}
```

## Etapa 3: perguntar com fontes

**Objetivo:** obter uma resposta que cita os trechos usados, e conferir o caminho que ela percorreu. Esta etapa só lê o índice e consome tokens.

### 3.1 Fazer a primeira pergunta

```powershell
python scripts\perguntar.py --busca $busca --modelos $modelos --deployment-geracao $deploymentGeracao --pergunta "O meu seguro cobre danos elétricos?"
```

**Exemplo de saída registrada** (resumido; o texto e o consumo variam entre execuções):

```text
Pergunta: O meu seguro cobre danos elétricos?
Recuperação: modo hibrida · 5 trecho(s) · serviço de busca '<busca>', índice 'vareleira-lar-l100'
Trechos recuperados (5):
  1. [VLAR-GL-1_0-009] pontuação 0.033 · Danos elétricos
  2. [VLAR-FAQ-1_0-002] pontuação 0.033 · Danos elétricos estão incluídos em todas as contratações do Vareleira Lar?
  ...
Geração: deployment 'geracao' · esforço de raciocínio low

Resposta:
  Danos elétricos são uma cobertura adicional. Só há cobertura se ela tiver sido contratada e
  constar na apólice individual. Quando contratada, ela indeniza danos a instalações elétricas fixas
  e a aparelhos elétricos e eletrônicos do imóvel causados por curto-circuito, sobrecarga ou
  variação anormal de tensão. ...

Fontes citadas:
  [VLAR-FAQ-1_0-002] Vareleira Lar — Perguntas frequentes para Atendimento e corretores · Danos elétricos estão incluídos ... · versão 1.0 · vareleira-lar/faq-v1.0.md
  [VLAR-CG-1_0-004] Vareleira Lar — Condições Gerais · 3. Coberturas adicionais (cláusulas 3.1, 3.2, 3.3) · versão 1.0 · vareleira-lar/condicoes-gerais-v1.0.md

Como esta resposta foi produzida:
  1. A pergunta virou um vetor (11 tokens de embeddings).
  2. A busca 'hibrida' devolveu 5 trecho(s): VLAR-GL-1_0-009, VLAR-FAQ-1_0-002, ...
  3. O deployment 'geracao' recebeu esses trechos e a pergunta, e citou 2.
  4. O script conferiu que cada fonte citada está entre os trechos recuperados.
  Uso na geração: 1456 tokens de entrada e 186 de saída (55 de raciocínio).

Lembrete: a resposta explica regras do produto; ela não confirma as coberturas de uma contratação.
```

As execuções registradas levaram de 11 a 15 segundos. Cada bloco da saída tem uma função:

| Bloco | O que mostra |
| --- | --- |
| Trechos recuperados | O que a busca devolveu, na ordem de pontuação, antes de o modelo participar |
| Resposta | O texto proposto pelo modelo; você confere se ele corresponde aos trechos |
| Fontes citadas | Os trechos que o modelo declarou usar, com documento, seção, cláusulas, versão e arquivo; os metadados vêm do índice, não do modelo |
| Como esta resposta foi produzida | O percurso e o uso de tokens: embedding da pergunta, trechos, citações e geração |

### 3.2 Conferir a fonte no documento

**Atividade 2:** abra o arquivo do documento citado (por exemplo, `dados\l100\documentos\vareleira-lar-condicoes-gerais-v1.0.md`) e localize a cláusula 3.2. Compare cada afirmação da resposta com o texto da cláusula.

**Conferência:** a resposta reproduz o que as cláusulas 3.1 e 3.2 dizem: a cobertura é adicional, vale só se constar na apólice individual e cobre curto-circuito, sobrecarga e variação anormal de tensão. O script conferiu que os ids citados foram recuperados; só você confere que o texto corresponde à fonte. Uma resposta pode citar um trecho recuperado e ainda distorcê-lo.

## Etapa 4: comparar modo de busca, quantidade de trechos e esforço

**Objetivo:** perceber como as escolhas da recuperação e do modelo mudam a resposta. Cada comando abaixo faz uma pergunta; compare as respostas e as fontes.

### 4.1 Modo de busca

```powershell
python scripts\perguntar.py --busca $busca --modelos $modelos --deployment-geracao $deploymentGeracao --pergunta "franquia danos elétricos" --modo texto --k 3
python scripts\perguntar.py --busca $busca --modelos $modelos --deployment-geracao $deploymentGeracao --pergunta "franquia danos elétricos" --modo vetorial --k 3
```

No modo `texto`, a busca compara palavras e dispensa o embedding da pergunta. Compare a lista de
trechos recuperados com a resposta sobre a franquia. Nas execuções registradas, os dois modos
informaram "10% do prejuízo, com mínimo de R$ 300,00", usando as perguntas frequentes (FAQ,
*Frequently Asked Questions*), o glossário ou a cláusula 6.
As pontuações usam escalas diferentes: compare posições dentro de cada modo, como no Desafio 02.

### 4.2 Quantidade de trechos

```powershell
python scripts\perguntar.py --busca $busca --modelos $modelos --deployment-geracao $deploymentGeracao --pergunta "Roubaram meu notebook na rua. O seguro paga?" --k 5
python scripts\perguntar.py --busca $busca --modelos $modelos --deployment-geracao $deploymentGeracao --pergunta "Roubaram meu notebook na rua. O seguro paga?" --k 10
```

**Atividade 3:** compare as duas respostas e as listas de trechos recuperados. Em qual execução aparece o trecho `VLAR-CG-1_0-007`, da seção "5. Riscos excluídos"? O que o modelo afirma em cada caso?

**Conferência:** no exemplo registrado, `--k 5` deixou o trecho das exclusões fora do pedido. A resposta
descreveu a cobertura de roubo e furto qualificado e apontou falta de informação sobre o notebook na rua.
Com `--k 10`, o trecho chegou ao modelo, que informou a exclusão de bens portáteis levados para fora do
imóvel (cláusula 5.1, item h). Confira as listas da sua execução: a posição e o texto podem variar.
O exercício mostra como a recuperação incompleta limita a resposta mesmo quando o modelo segue o pedido.

Aumentar o `k` tem um preço: o pedido com 10 trechos usou 2.233 tokens de entrada na validação, contra cerca de 1.200 a 1.500 com 5 trechos.

### 4.3 Esforço de raciocínio

```powershell
python scripts\perguntar.py --busca $busca --modelos $modelos --deployment-geracao $deploymentGeracao --pergunta "Roubaram meu notebook na rua. O seguro paga?" --k 10 --esforco none
python scripts\perguntar.py --busca $busca --modelos $modelos --deployment-geracao $deploymentGeracao --pergunta "Roubaram meu notebook na rua. O seguro paga?" --k 10 --esforco high
```

Na validação, a mesma pergunta com 10 trechos usou 2.233 tokens de entrada em todos os esforços e variou na saída:

| Esforço | Tokens de saída | Tokens de raciocínio (parte da saída) | Tempo total |
| --- | --- | --- | --- |
| `none` | 50 a 53 | 0 | cerca de 12 s |
| `low` (padrão) | 158 a 186 | 60 a 90 | de 13 a 15 s |
| `medium` | 262 a 361 | 165 a 264 | cerca de 13 s |
| `high` | 348 a 382 | 256 a 289 | cerca de 13 s |

O tempo total variou pouco nessa amostra. O consumo de saída aumentou com o esforço, e os tokens de
raciocínio são cobrados como saída [7]. Para começar a comparação, use `none` ou `low` quando os trechos
já contêm a regra pedida. Antes de aumentar o esforço para combinar regras, confira se a qualidade da
resposta melhora nas mesmas perguntas.

### 4.4 Pergunta sem resposta nos documentos

```powershell
python scripts\perguntar.py --busca $busca --modelos $modelos --deployment-geracao $deploymentGeracao --pergunta "Quanto custa o seguro por mês?"
```

**Exemplo de saída registrada:** resposta sem fontes para uma pergunta cujo preço os documentos
não informam. O programa mostra um aviso sempre que a lista de fontes vem vazia:

```text
Resposta:
  Os trechos não informam quanto custa o seguro por mês.

[AVISO] A resposta não cita nenhuma fonte: não a use como regra do produto.
```

O modelo seguiu a regra 3 das instruções e admitiu que não sabe. Essa conduta depende da instrução e do modelo: o script apenas avisa quando não há fonte e não impede uma resposta inventada. O próximo desafio transforma essa regra em verificação do programa.

## Como pedir uma mudança ao Copilot no VS Code

Use o [procedimento do Desafio 01](01-preparar-ambiente.md#como-pedir-uma-mudança-ao-copilot-no-vs-code):
contexto, plano, limites, revisão do diff (comparação entre versões dos arquivos) e verificação com
comandos autorizados. Uma mudança no pedido altera o contexto recebido pelo modelo; compare as
respostas e as fontes antes de aceitar.

### Exemplo: uma saída em JSON para outro programa

Cole com os arquivos anexados. Os testes usam **dublês**, objetos que simulam os serviços externos:

```text
Leia o README, o L100 Desafio 03, scripts/perguntar.py e scripts/lab_geracao.py anexados.
Quero uma opção nova em perguntar.py: --saida-json. Com ela, o script imprime só um objeto JSON com
pergunta, resposta, fontes (id, documento, seção, cláusulas, versão e arquivo) e o uso de tokens, para outro programa ler.
Antes de editar, proponha o plano: arquivos, funções e testes.
Cuidados obrigatórios: não inclua nos dados o nome do serviço de busca, o do recurso de modelos nem o texto do pedido;
reaproveite lab_geracao; mensagens em pt-BR; mantenha o comportamento atual quando a opção não for usada.
Escreva testes com unittest e dublês, sem acessar o Azure.
Use o Python do ambiente virtual, .\.venv\Scripts\python.exe, e execute apenas:
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_geracao.py"
Não instale pacotes, não acesse o Azure e não altere o índice.
```

**Conferência:** o diff deve manter a saída padrão, imprimir JSON válido sem textos de acompanhamento,
omitir os nomes do ambiente e incluir testes para as duas saídas. Depois de revisar a implementação,
repita o comando completo da Etapa 3.1 e acrescente `--saida-json`. Confira a estrutura do objeto e a
origem das fontes; o texto e as fontes escolhidas podem variar entre chamadas ao modelo.

> **Dica:** peça uma explicação do diff, com palavras simples, antes de aceitá-lo. Outros pedidos para praticar: "explique o que cada regra das instruções do modelo impede" e "proponha duas perguntas de teste que façam o modelo citar um id inexistente".

**Modo construtor (opcional).** Para ver como o Copilot resolveria o desafio, peça um plano em uma pasta separada e compare o resultado com os arquivos deste projeto pelo diff:

```text
Leia o L100, Desafio 03, o README e as instruções do projeto.
Proponha, sem editar, como responder a uma pergunta com trechos recuperados do Azure AI Search e um modelo do Azure OpenAI, com Python.
Receba os destinos explicitamente. Use acesso por Entra ID, sem chaves de API.
Defina o que o programa faz quando o modelo cita um trecho que não foi recuperado; não apresente essa resposta.
Não provisione recursos, atribua papéis, envie dados ou exclua arquivos.
```

Qualquer ação que altere o Azure continua dependendo da sua decisão.

## Conferência do resultado

| Verificação | Como conferir | Evidência esperada |
| --- | --- | --- |
| Região, modelo e cota | Comandos de "Conferir região, modelo e cota" | Modelo disponível e cota livre de pelo menos 50 |
| Pedido compreendido | Etapa 1 e a Atividade 1 | Você localiza a frase da franquia e o id do trecho no pedido |
| Plano da infraestrutura | `az deployment group what-if` | Uma criação (`deployments/geracao`); nada removido |
| Deployment criado | `az cognitiveservices account deployment show` | `gpt-5.4-mini`, versão `2026-03-17`, `GlobalStandard`, capacidade 50, `NoAutoUpgrade` |
| Resposta com fontes | `perguntar.py` com a primeira pergunta | Resposta, fontes citadas com metadados e código de saída 0 |
| Fontes conferidas por você | Atividade 2 | A resposta corresponde ao texto das cláusulas citadas |
| Recuperação incompleta explicada | Atividade 3 | Você explica por que `--k 5` e `--k 10` levam a respostas diferentes |
| Pergunta sem resposta | Etapa 4.4 | Aviso de resposta sem fontes |

Antes de encerrar, registre em local privado o grupo de recursos, os nomes da busca e dos modelos e a decisão de manter, pausar ou remover os recursos. Ao compartilhar evidências, remova das saídas do terminal os identificadores do ambiente, os nomes de recursos e as contas de usuário.

## Solução de problemas

As respostas dos serviços usam códigos HTTP (*Hypertext Transfer Protocol*, protocolo da web): 401
indica falha de autenticação; 403, recusa de acesso; e 429, excesso de requisições.

| Sintoma | O que conferir | O que evitar |
| --- | --- | --- |
| `InsufficientQuota` ao criar o deployment | Confira a cota; reduza `capacidadeGeracao` no plano e na implantação, se viável. Excluir deployments próprios ou migrar para outra região exige autorização e plano separados | Excluir deployments preexistentes ou tentar mudar a região do recurso existente para contornar |
| `InvalidResourceProperties` ou `DeploymentModelNotSupported` | O modelo, a versão ou o tipo de deployment não existem na região: refaça "Conferir região, modelo e cota" e ajuste os parâmetros | Escolher um modelo qualquer sem ver a lista da região |
| `[ERRO]` "O deployment de geração ... não foi encontrado" (código 2) | O nome do **deployment** (`$deploymentGeracao`), não o do modelo, e o nome do recurso | Criar outro deployment só para o erro desaparecer |
| `[ERRO]` "O Azure respondeu 404 ('Subdomain does not map to a resource')" (código 2) | O nome em `$modelos`. Com o nome certo, o serviço de modelos às vezes responde assim de forma intermitente: aguarde alguns minutos e repita (veja também o [Desafio 02](02-indexar-documentos.md#solução-de-problemas)) | Recriar o recurso ou o deployment só para o erro desaparecer |
| `[ERRO]` "O serviço de modelos recusou o pedido (HTTP 401 ou 403)" (código 2) | O papel `Cognitive Services OpenAI User`, o `az login` e o tenant (`--tenant-id`); logo após uma atribuição, aguarde até 10 minutos [13] | Colar tokens no chat ou em arquivos |
| `[ERRO]` "atingiu o limite de requisições ou de tokens por minuto (HTTP 429)" (código 2) | Aguarde um minuto e repita; se persistir, aumente `capacidadeGeracao` dentro da cota livre | Aumentar a cota sem necessidade |
| `[ERRO]` "Não foi possível conectar ao recurso de modelos" (código 2) | O nome em `$modelos`, a rede e se o recurso existe (pode ter sido pausado) | Inventar um nome |
| `[ERRO]` "O modelo não terminou a resposta (max_output_tokens)" (código 2) | Repita com `--esforco low` ou `--esforco none`: o raciocínio consumiu o limite de saída | Aumentar o limite sem entender o consumo |
| `[ERRO]` "O filtro de conteúdo do serviço bloqueou o pedido" (código 2) | Reformule a pergunta sem o trecho que disparou o filtro | Tentar contornar o filtro |
| `[ERRO]` "O modelo devolveu uma resposta fora do formato esperado" (código 2) | Repita o comando; se persistir, use `--detalhes` | Aceitar texto fora do formato |
| `[FALHA]` "O modelo citou fontes que não estão entre os trechos recuperados" (código 3) | Repita o comando; se persistir, use `--mostrar-prompt` e examine o pedido | Remover a conferência para a resposta aparecer |
| `[AVISO]` "A resposta não cita nenhuma fonte" | A pergunta pode não ter resposta nos documentos; aumente `--k` ou reformule | Usar a resposta como regra do produto |
| A resposta ignora uma regra que você conhece | Se o trecho da regra está entre os recuperados (`--mostrar-prompt`); aumente `--k` ou mude o modo | Concluir que o modelo "errou" sem examinar o pedido |
| Erros dos desafios anteriores (login, tenant, papéis, busca, embeddings) | [Solução de problemas do Desafio 02](02-indexar-documentos.md#solução-de-problemas) | Pular a conferência |

Se precisar de ajuda, consulte os [canais e limites do suporte](../../SUPPORT.md). Não conceda papéis,
altere políticas corporativas ou desative controles como tentativa de diagnóstico.

## Custos, pausa e limpeza

O uso do Copilot segue o plano da sua conta e as regras de consumo dele, separadamente da assinatura Azure. A cobrança do Azure vem dos recursos criados nos Desafios 01, 02 e 03.

**O que gera custo neste desafio:**

- **Deployment de geração:** cobra por token processado e não cobra por existir; a capacidade define a cota [2]. Cada pergunta usou, na validação, de 899 a 2.233 tokens de entrada e de 48 a 382 de saída, conforme a quantidade de trechos e o esforço. Os tokens de raciocínio contam como saída [7].
- **Embeddings:** cada pergunta usa cerca de 10 tokens para calcular o vetor, no modo `vetorial` ou `hibrida`.
- **Serviço de busca da camada `basic`:** continua cobrando por hora enquanto existir, como descrito no Desafio 02.

Os custos não foram medidos na validação, e os preços variam por região, modelo e data. Consulte os [preços atuais dos modelos do Azure OpenAI](https://azure.microsoft.com/en-us/pricing/details/azure-openai/) para a sua região [14], calcule o custo na [calculadora de preços](https://azure.microsoft.com/en-us/pricing/calculator/) e acompanhe o consumo no Cost Management. Os orçamentos enviam alertas, e o consumo continua até a remoção dos recursos. [15]

**Pausa e continuidade.** Os próximos desafios reutilizam o deployment de geração. Para continuar nos
próximos dias, mantenha os recursos. Em uma pausa longa, siga
[Pausar, no Desafio 02](02-indexar-documentos.md#pausar-altera-o-azure), que remove a busca e o recurso de
modelos, inclusive os dois deployments.

### Remover só o deployment de geração **[altera o Azure]**

Como o deployment não cobra por existir, a remoção isolada serve para liberar a cota ou trocar de modelo:

```powershell
az cognitiveservices account deployment delete --subscription $assinatura --resource-group $grupo --name $modelos --deployment-name $deploymentGeracao
```

Para recriar o deployment, repita a Etapa 2. O índice e o deployment de embeddings permanecem.

A exclusão pode demorar a interromper as chamadas: no ambiente testado, o deployment respondeu por mais
de 16 minutos após sair da listagem. Antes de depender da remoção, por exemplo para trocar de modelo,
repita uma pergunta e confirme o erro "O deployment de geração '...' não foi encontrado".
Os tempos e o método dessa verificação estão nas
[observações de operação](../../docs/validacao/l100-03-responder-com-fontes.md#observações-de-operação).

### Limpeza completa **[altera o Azure]**

A limpeza completa é a do [Desafio 02](02-indexar-documentos.md#limpeza-completa-altera-o-azure): confira o alvo, exclua o grupo de recursos do laboratório e purgue o recurso de modelos, que continua em exclusão reversível por 48 horas. [16]

## Situação da validação

Data de referência: 9 de outubro de 2026. O registro detalhado, com a matriz de testes, as medições e as observações de operação, está em [docs\validacao\l100-03-responder-com-fontes.md](../../docs/validacao/l100-03-responder-com-fontes.md).

**Versões testadas:** Windows, Python 3.12.10, Azure CLI (interface de linha de comando) 2.89.0, Bicep 0.48.1, `openai` 3.23.0, `azure-search-documents` 12.0.0 e as bibliotecas dos desafios anteriores.

| Item | Situação | Detalhe |
| --- | --- | --- |
| Comandos das Etapas 1 a 4 e remoção do deployment | Concluído | Executados em PowerShell 7.6, em `brazilsouth`, sobre um grupo novo com os Desafios 01 e 02 implantados |
| Scripts, Bicep e testes automáticos (sem Azure) | Concluído | Testes aprovados; `az bicep lint`, `build` e `format` sem avisos |
| Links, âncoras, URLs e referências dos guias | Concluído | Nenhum link ou âncora inválido |
| Aprovação do conteúdo dos documentos sintéticos | Confirmada | Pelo mantenedor, em 9 de outubro de 2026; registro no inventário |
| Aprovação do texto, do código e dos resultados | Confirmada | Pelo mantenedor, em 9 de outubro de 2026; não representa novos testes |
| Outros ambientes: macOS, Linux, WSL (Windows Subsystem for Linux), Python diferente do 3.12 e Windows PowerShell 5.1 | Pendente | Executar os comandos do guia nesses ambientes e registrar as diferenças |
| Outras regiões, outras cotas e outros modelos de geração | Pendente | Repetir a Etapa 2 em cada cenário; só o `gpt-5.4-mini` foi validado |
| Falhas do serviço: filtro de conteúdo, limite de requisições (HTTP 429), resposta incompleta e papel ausente | Pendente | Coberto só por testes automáticos; provocar cada caso em ambiente de teste |
| Interações com o Copilot: prompts do guia, exemplo de pedido de mudança e modo construtor | Pendente | Executar no VS Code e registrar as respostas |
| Custo | Pendente | Medir o custo no Cost Management após uma execução completa |

**Autoria.** Código, testes e texto produzidos com apoio de inteligência artificial (IA), com Claude
Sonnet 5.5 no GitHub Copilot CLI; o Astra estava indisponível. Revisão editorial por GPT-6.1 Sol, em
9 de outubro de 2026. Os modelos de autoria e revisão são independentes do modelo escolhido no Copilot
e dos deployments da aplicação Azure (`text-embedding-3-small` e `gpt-5.4-mini`).

Revisão editorial e técnica por **gpt-6-astra (Astra)**, em 11 de outubro de 2026: leitura integral,
conferência de referências locais e confronto com a implementação. Não houve nova execução Azure;
autoria, revisões anteriores, aprovação histórica e limites das medições permanecem preservados.

## Glossário

| Termo | Significado no exercício |
| --- | --- |
| Geração (de texto) | Escrita de um texto novo por um modelo, a partir de instruções e de um contexto |
| RAG | *Retrieval-Augmented Generation* (geração aumentada por recuperação): geração de respostas apoiada em evidências recuperadas de uma base |
| Deployment de geração | Instância nomeada de um modelo de geração, que recebe as chamadas; o nome do deployment é distinto do nome do modelo |
| `gpt-5.4-mini` | Modelo de raciocínio de porte pequeno, usado aqui para escrever as respostas |
| Modelo de raciocínio | Modelo que gera tokens de raciocínio antes da resposta visível |
| Esforço (de raciocínio) | Parâmetro que controla quanto o modelo raciocina: `none`, `low`, `medium` ou `high` |
| Token de raciocínio | Token que o modelo gera ao raciocinar; não aparece na resposta e é cobrado como token de saída |
| API Responses | Interface do Azure OpenAI em que o script envia instruções, entrada e formato de saída e recebe a resposta |
| Pedido (ao modelo) | O conjunto de instruções, contexto e pergunta enviado ao modelo |
| Instruções | Regras de trabalho que acompanham todo pedido, escritas em `INSTRUCOES` |
| Contexto | Os trechos recuperados, cada um em um bloco `<trecho>` com id e metadados |
| Saída estruturada | Formato de resposta imposto por um esquema JSON, aqui com `resposta` e `fontes` |
| JSON | Formato de texto estruturado em pares nome-valor |
| Fonte (citada) | Id de um trecho que o modelo declara ter usado; o script confere que ele foi recuperado |
| Conferência das fontes | Verificação do script de que todo id citado está entre os trechos recuperados |
| Resposta sem fonte | Resposta que não cita trecho algum; o script a apresenta com aviso |
| `k` | Quantidade de trechos que a busca devolve e que o modelo recebe |
| Cota (de tokens por minuto) | Limite de uso por região e modelo; a capacidade do deployment reserva parte dela, sem cobrança por si só |
| `GlobalStandard` | Tipo de deployment que cobra por token e pode processar o texto em qualquer geografia Azure |
| Versão fixa (`NoAutoUpgrade`) | Configuração que mantém o deployment na versão escolhida |
| Aposentadoria (de modelo) | Data em que o serviço deixa de aceitar chamadas a uma versão de modelo |
| What-if | Previsão de alterações de infraestrutura antes da implantação |
| Prompt | Pedido e contexto fornecidos ao Copilot ou a outro modelo |

## Referências

Fontes oficiais consultadas em 9 de outubro de 2026. Nomes de interface, limites, preços e disponibilidade mudam: confira a versão atual antes de aplicar.

1. [Modelos do Foundry vendidos pelo Azure: GPT-5.4](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/models-sold-directly-by-azure#gpt-54).
2. [Implantar modelos no Microsoft Foundry: tipos de implantação](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/deployment-types).
3. [Usar a API Responses do Azure OpenAI](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/responses).
4. [Saídas estruturadas](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/structured-outputs).
5. [Controle de acesso baseado em papéis do Azure OpenAI](https://learn.microsoft.com/en-us/azure/ai-foundry/openai/how-to/role-based-access-control).
6. [Prompt Shields: ataques diretos e indiretos a modelos de linguagem](https://learn.microsoft.com/en-us/azure/ai-services/content-safety/concepts/jailbreak-detection).
7. [Modelos de raciocínio do Azure OpenAI](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/reasoning).
8. [Cotas e limites do Azure OpenAI no Foundry](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/quota).
9. [Cronograma de aposentadoria de modelos](https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/model-retirement-schedule).
10. [Referência Bicep dos recursos de IA](https://learn.microsoft.com/en-us/azure/templates/microsoft.cognitiveservices/accounts).
11. [Funções de arquivos de parâmetros do Bicep, incluindo `readEnvironmentVariable`](https://learn.microsoft.com/en-us/azure/azure-resource-manager/bicep/bicep-functions-parameters-file).
12. [Previsão de alterações com Bicep what-if](https://learn.microsoft.com/en-us/azure/azure-resource-manager/bicep/deploy-what-if).
13. [Solução de problemas do RBAC do Azure](https://learn.microsoft.com/en-us/azure/role-based-access-control/troubleshooting).
14. [Preços dos modelos do Azure OpenAI](https://azure.microsoft.com/en-us/pricing/details/azure-openai/).
15. [Orçamentos e alertas no Azure Cost Management](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/tutorial-acm-create-budgets).
16. [Recuperar ou purgar recursos do Foundry excluídos](https://learn.microsoft.com/en-us/azure/ai-services/recover-purge-resources).

As atribuições do contexto fictício estão em [NOTICE.md](../../NOTICE.md). O texto deste guia está sob a licença Creative Commons Atribuição 4.0 (CC BY 4.0; veja [LICENSE](../../LICENSE)).
