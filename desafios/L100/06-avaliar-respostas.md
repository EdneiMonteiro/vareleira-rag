# L100 — Desafio 06: medir a recuperação e as respostas com conjuntos de ajuste e de teste

[Início do laboratório](../../README.md) · Nível L100: fundamentos · [Desafio 05](05-agente-com-maf.md)

| Item | Descrição |
| --- | --- |
| Situação | Exercício executável, validado no Azure em 9 de outubro de 2026 (Windows e PowerShell). Os documentos de seguro e as perguntas são sintéticos e novos. Estão pendentes a revisão do conteúdo pelo mantenedor e a revisão humana do texto; veja [Situação da validação](#situação-da-validação). |
| Público | Pessoas de negócio, arquitetura, operações e desenvolvimento. Use o Visual Studio Code (VS Code) para executar os comandos e interpretar os números; escrever código é opcional. |
| Pré-requisito | [Desafio 05](05-agente-com-maf.md) concluído: este desafio mede os dois fluxos de resposta, a recuperação obrigatória (Desafios 03 e 04) e a recuperação por ferramenta (Desafio 05), com a política do Desafio 04. |
| Resultado | O programa `avaliar_respostas.py` e dois conjuntos de 12 perguntas, um de ajuste e um de teste. Você mede a recuperação e as respostas, escolhe uma configuração por um critério definido antes e mede o conjunto de teste uma única vez. |
| Custo | Nenhum recurso novo. Cada medição das respostas consome tokens: de 14 mil a 34 mil tokens de entrada por execução de 12 perguntas. Veja [Custos, pausa e limpeza](#custos-pausa-e-limpeza). |

## Conteúdo

- [Cenário](#cenário)
- [Objetivos](#objetivos)
- [Artefatos e disponibilidade](#artefatos-e-disponibilidade)
- [Tecnologias e conceitos](#tecnologias-e-conceitos)
- [Reaproveitamento e acréscimos](#reaproveitamento-e-acréscimos)
- [Pré-requisitos](#pré-requisitos)
- [Etapa 1: conhecer e validar os conjuntos](#etapa-1-conhecer-e-validar-os-conjuntos)
- [Etapa 2: medir a recuperação no conjunto de ajuste](#etapa-2-medir-a-recuperação-no-conjunto-de-ajuste)
- [Etapa 3: medir as respostas com a recuperação obrigatória](#etapa-3-medir-as-respostas-com-a-recuperação-obrigatória)
- [Etapa 4: comparar configurações](#etapa-4-comparar-configurações)
- [Etapa 5: repetir a medição e escolher](#etapa-5-repetir-a-medição-e-escolher)
- [Etapa 6: medir o conjunto de teste uma única vez](#etapa-6-medir-o-conjunto-de-teste-uma-única-vez)
- [Etapa 7: testar a avaliação sem o Azure](#etapa-7-testar-a-avaliação-sem-o-azure)
- [Como pedir uma mudança ao Copilot no VS Code](#como-pedir-uma-mudança-ao-copilot-no-vs-code)
- [Conferência do resultado](#conferência-do-resultado)
- [Solução de problemas](#solução-de-problemas)
- [Custos, pausa e limpeza](#custos-pausa-e-limpeza)
- [Situação da validação](#situação-da-validação)
- [Glossário](#glossário)
- [Referências](#referências)

## Cenário

Em 2025, na história fictícia da Vareleira, o piloto do Assistente de Apólices responde bem às perguntas que a equipe testou manualmente. Teresa Moura, diretora técnica de Subscrição, não aceita "funcionou nos exemplos" como motivo para ampliar o piloto. Ela quer números: quantas perguntas o assistente responde, quantas recusa e, principalmente, se alguma vez responde algo que os documentos não sustentam.

Beatriz Torres, responsável pelo Atendimento, reúne perguntas típicas do dia a dia. Teresa define o
procedimento do exercício: guardar metade das perguntas para uma medição final e escrever o critério
antes de medir o ajuste. A meta é não responder perguntas que o conjunto classifica como sem resposta
nos documentos e acertar a situação de pelo menos 11 das 12 perguntas em cada repetição. Entre as
configurações que cumprem a meta, o desempate usa a menor média de tokens de entrada.

**Missão:** montar uma medição repetível da recuperação e das respostas, escolher uma configuração pela meta de Teresa e medir o conjunto guardado uma única vez, aceitando o número que ele mostrar.

> **Lembre-se:** o cenário é fictício. Não use apólices, nomes, endereços ou documentos de segurados reais, mesmo que tenha acesso a eles no trabalho.

## Objetivos

Ao concluir este desafio, você terá:

- validado, sem Azure, que os dois conjuntos de perguntas conferem com os documentos;
- medido a recuperação com acerto@k (todos os assuntos entre os primeiros `k` trechos) e MRR (*mean reciprocal rank*, média do inverso da posição do primeiro trecho pertinente);
- medido as respostas dos dois fluxos, com tipo, situação, descartes, falsas recusas, falsas respostas e fatos esperados;
- repetido a medição para ver quanto o resultado varia sem mudar nada, e escolhido uma configuração pela meta definida antes;
- medido o conjunto de teste uma única vez e comparado o resultado com o do ajuste;
- executado os testes automáticos da avaliação, sem Azure.

**Próximos desafios:** o [Desafio 07](07-identidade-da-aplicacao.md) usa service principal (identidade de uma aplicação no Microsoft Entra ID) e Azure Key Vault (serviço de guarda de segredos).

> **Para guardar na memória: C-A-T.** Em toda medição, **C**ritério antes, **A**juste só com o conjunto de ajuste e **T**este uma vez. Mnemônico criado para este curso.

## Artefatos e disponibilidade

| Artefato | Onde encontrar | Situação |
| --- | --- | --- |
| Desafio anterior (agente, política de resposta e deployment de geração) | [05-agente-com-maf.md](05-agente-com-maf.md) | Disponível; pré-requisito |
| Conjunto de ajuste (12 perguntas) | [dados\l100\avaliacao\ajuste.json](../../dados/l100/avaliacao/ajuste.json) | Disponível; aprovação do mantenedor confirmada |
| Conjunto de teste (12 perguntas) | [dados\l100\avaliacao\teste.json](../../dados/l100/avaliacao/teste.json) | Disponível; abra só depois de medir (Etapa 6) |
| Programa de medição | [scripts\avaliar_respostas.py](../../scripts/avaliar_respostas.py) | Disponível; validado |
| Carregador dos conjuntos, métricas e respondedores | [scripts\lab_avaliacao.py](../../scripts/lab_avaliacao.py) | Disponível; validado |
| Política de resposta, tipos e evidências | [scripts\lab_politica.py](../../scripts/lab_politica.py) | Disponível; normalização das citações corrigida |
| Agente com ferramenta de busca | [scripts\lab_agente.py](../../scripts/lab_agente.py) | Disponível; do Desafio 05 |
| Testes automáticos da avaliação (sem Azure) | [tests\test_avaliacao.py](../../tests/test_avaliacao.py) | Disponíveis |
| Documentos sintéticos e inventário | [dados\l100\inventario.json](../../dados/l100/inventario.json) | Disponível; aprovação do mantenedor confirmada |

> **Atenção:** este desafio não altera o Azure. As medições só leem o índice, mas as das respostas consomem tokens (as unidades de texto que o modelo conta e cobra). Os conjuntos de perguntas ficam no repositório e não são enviados ao Blob Storage nem ao índice. A decisão de executar cada comando é sua, mesmo quando você pede ao Copilot que "meça" ou "execute" algo.

## Tecnologias e conceitos

| Componente | Função neste desafio | Limite ou cuidado |
| --- | --- | --- |
| Conjunto de ajuste (`ajuste.json`) | 12 perguntas sintéticas para comparar configurações; você pode lê-las, discuti-las e medi-las quantas vezes quiser | Quanto mais você ajusta, mais otimistas ficam os números nele |
| Conjunto de teste (`teste.json`) | 12 perguntas guardadas, com a mesma composição, medidas uma vez; o programa mostra só os números | Se você olhar as perguntas e mudar a configuração, ele deixa de ser teste: é o sobreajuste, quando algo se adapta demais ao que já viu e perde a capacidade de prever o que é novo [1] |
| Recuperação: acerto@k e MRR | Mede se os trechos pertinentes chegam ao modelo, nos modos vetorial, texto e híbrido [2] | Usa só as perguntas com resposta nos documentos; a pertinência vem das frases esperadas do conjunto |
| Respostas: tipo, situação, falsas recusas e falsas respostas | Aplica a política do Desafio 04 (e o agente do Desafio 05) a cada pergunta e compara com o esperado | Confere o que as regras conferem; métricas como completude e relevância da resposta [3] não fazem parte do programa |
| Fatos esperados | Frases curtas que a resposta mostrada deveria conter | Uma resposta correta com outras palavras conta como ausente |
| Repetições (`--repeticoes`) | Repete a medição de 1 a 5 vezes e mostra a faixa de cada número | Mais repetições custam mais tokens e não substituem um conjunto maior |
| Meta de escolha | Critério registrado antes de medir o ajuste no exercício | Define tolerância a erros e desempate; o histórico da validação está separado na situação ao final |

**Conceitos necessários:** medir com perguntas definidas antes, os dois conjuntos, medir a recuperação, medir as respostas, variação e tamanho da amostra, meta e sobreajuste.

**1. Medir com perguntas definidas antes.** Use as mesmas perguntas e os mesmos resultados esperados
para comparar mudanças no modo de busca, na quantidade de trechos, no modelo ou no fluxo.
O programa conta tipos, situações, citações verificadas e frases esperadas. Esses números permitem
comparar configurações segundo critérios específicos. A fundamentação de todas as afirmações e a
completude da resposta exigem avaliação adicional [3].

> **Para guardar na memória: o ensaio e a estreia.** O conjunto de ajuste é o ensaio: você repete, muda a marcação de cena e repete de novo. O conjunto de teste é a estreia: acontece uma vez, diante de gente que nunca viu o ensaio. Analogia criada para este curso.

**2. Os dois conjuntos.** Cada conjunto tem 12 perguntas sintéticas com a mesma composição, para que um número possa ser comparado com o outro: 5 simples (a resposta está em um trecho), 2 compostas (dois assuntos em trechos diferentes), 2 individuais (o caso de quem pergunta depende da apólice), 1 sem evidência (trata do produto, mas os documentos não respondem), 1 fora de escopo e 1 ambígua. Cada pergunta registra três coisas:

- o **tipo esperado**, um dos cinco tipos do Desafio 04, de onde vem a **situação esperada**: respondida (tipos `documentada` e `contratacao_individual`), recusada (`sem_evidencia` e `fora_de_escopo`) ou esclarecimento (`ambigua`);
- os **assuntos** que os trechos recuperados precisam cobrir: cada assunto tem uma ou mais **alternativas**, formadas por um documento e uma frase, e basta que uma alternativa apareça em um dos trechos; a pergunta composta tem dois assuntos, e os dois precisam aparecer;
- os **fatos** que a resposta deveria conter, como "30 dias" ou "R$ 500,00".

As perguntas sem evidência, fora de escopo e ambíguas não têm assuntos nem fatos no conjunto.
Os arquivos usam JSON (*JavaScript Object Notation*, formato de dados em texto).

**3. Medir a recuperação.** Antes da geração, confira a presença dos assuntos esperados nos trechos.
O programa usa duas medidas inspiradas em recuperação de informação [2]:

- **acerto@k** é a parte das perguntas cujos assuntos aparecem todos entre os `k` primeiros trechos. É uma variação do *recall at K* (a cobertura dos trechos pertinentes entre os `k` primeiros) que exige todos os assuntos da pergunta [2];
- **MRR** (*mean reciprocal rank*, média do inverso da posição) calcula, para cada pergunta, 1 dividido pela posição do primeiro trecho pertinente (1 para o primeiro lugar, 0,5 para o segundo, 0,33 para o terceiro) e tira a média [2].

Só entram as perguntas que têm resposta nos documentos: 9 de 12 em cada conjunto. A fonte recomenda testar também exemplos negativos, as perguntas que os documentos não respondem [2]. Neste desafio, elas são medidas na etapa das respostas, como falsas respostas.

**4. Medir as respostas.** Para cada pergunta, o programa executa o fluxo escolhido, aplica a política do Desafio 04 à saída do modelo e compara com o esperado:

| Medida | Significado |
| --- | --- |
| Tipo | O tipo atribuído (pelo modelo e pelas regras do programa) comparado com o esperado. É uma etiqueta de diagnóstico |
| Situação | O que a pessoa vê: respondida, recusada, esclarecimento ou descartada (a verificação reprovou a resposta e o programa não a mostra). É o que importa para quem pergunta |
| Falsa recusa | Pergunta com resposta nos documentos que foi recusada ou que recebeu um pedido de esclarecimento |
| Falsa resposta | Pergunta que o conjunto espera ver recusada ou esclarecida, mas que foi respondida. É um erro de conduta da resposta; essa contagem não avalia a fidelidade de cada frase |
| Fatos esperados | Quantos dos fatos esperados aparecem na resposta mostrada, sem diferenciar maiúsculas de minúsculas nem marcas de Markdown |
| Tokens, buscas e tempo | Médias por pergunta para comparar consumo e duração; o custo em dinheiro exige aplicar os preços dos serviços |

O tipo e a situação podem divergir: duas respostas com tipos diferentes podem levar à mesma recusa. Por isso a meta do cenário usa a situação.

**5. Variação e tamanho da amostra.** O mesmo comando pode produzir respostas diferentes.
Na medição das respostas, uma pergunta representa cerca de 8 pontos percentuais (1 em 12);
no acerto@k, cerca de 11 pontos (1 em 9). Uma diferença entre configurações pode refletir a variação do
modelo. Repetições mostram essa faixa, e conjuntos maiores, com perguntas representativas, ajudam a
reduzir a incerteza. Três rodadas deste exercício repetem as mesmas 12 perguntas; a variedade de
casos continua sendo de 12, ainda que o programa tenha gerado 36 respostas.

**6. Meta e sobreajuste.** A escolha feita no ajuste depende das perguntas já vistas.
Registre o critério antes de medir e reserve o teste para depois da escolha [1].
O teste estima o desempenho com perguntas que ficaram fora do ajuste, segundo as métricas usadas.
Se o resultado ficar abaixo da meta, registre a decisão e prepare um conjunto novo para uma nova
avaliação final.

## Reaproveitamento e acréscimos

| Item | Situação | Observação |
| --- | --- | --- |
| Infraestrutura no Azure | Reaproveitada, sem alteração | Nenhum recurso novo, nenhum papel novo |
| Política (`lab_politica.py`) | Normalização das citações corrigida | Marcas de ênfase (`**`, `_` e acento grave) são removidas sem inserir espaços; a pontuação permanece junto da frase. O defeito e sua correção estão no registro de validação |
| `perguntar.py` e `agente_maf.py` | Mesmo comportamento | O fluxo de cada um é o que a medição executa |
| `lab_agente.py`, `lab_geracao.py` e `lab_indexacao.py` | Pequenas extensões | O padrão de `--recuperacao` pode mudar por programa (aqui, `obrigatoria`); um formato de saída inesperado do modelo vira o erro `ErroDeFormato`, que a medição conta e segue; `--busca` e `--modelos` ficam opcionais só na etapa `validar` |
| `avaliar_respostas.py`, `lab_avaliacao.py` e os dois conjuntos | **Novos** | Medição, métricas e perguntas |
| Testes | `tests\test_avaliacao.py` novo, mais 2 casos em `tests\test_politica.py` | Executam sem Azure |
| Reverter | Deixar de usar `avaliar_respostas.py` | Os desafios anteriores não dependem dele |

## Pré-requisitos

Os comandos deste guia são escritos para Windows e PowerShell, no terminal integrado do Visual Studio Code (VS Code), como nos desafios anteriores.

| Pré-requisito | Como preparar | Necessário agora? |
| --- | --- | --- |
| Desafio 05 concluído | O agente funcionando (`agente_maf.py`) e as bibliotecas do Microsoft Agent Framework (MAF) instaladas, no mesmo grupo de recursos e na mesma assinatura | Sim |
| Variáveis do terminal | `$assinatura`, `$grupo`, `$busca`, `$modelos` e `$deploymentGeracao` definidas (veja abaixo) | Sim, a partir da Etapa 2 |
| Ambiente virtual do Python | O mesmo do Desafio 01; nenhuma biblioteca nova | Sim |
| Assinatura e permissões | Assinatura Azure ativa e permissões de dados do Desafio 03 | Sim, a partir da Etapa 2 |
| Aceitar o custo | Cada medição das respostas consome tokens; o serviço de busca continua cobrando por hora | Sim |
| Tempo | As execuções somam cerca de 15 minutos; a Etapa 5 é a mais longa | Sim |

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

### Registrar o critério antes de medir

Antes da Etapa 2, registre em local privado a configuração de referência e as três regras da escolha:

1. nenhuma falsa resposta em nenhuma repetição;
2. situação correta em pelo menos 11 das 12 perguntas em cada repetição;
3. menor média de tokens de entrada entre as configurações que cumprem as duas primeiras regras.

Mantenha o critério durante a comparação. No histórico de validação, a meta foi definida depois das
medições do ajuste e antes do teste; essa diferença em relação ao procedimento recomendado está no
[registro da ordem das medições](../../docs/validacao/l100-06-avaliar-respostas.md#ordem-das-medições-e-integridade-do-conjunto-de-teste).

## Etapa 1: conhecer e validar os conjuntos

**Objetivo:** ler a estrutura de uma pergunta e conferir, sem acessar o Azure, que cada evidência esperada existe nos documentos. Esta etapa não altera o Azure e não consome tokens.

### 1.1 Validar os conjuntos

```powershell
python scripts\avaliar_respostas.py --etapa validar
```

As opções `--busca` e `--modelos` não são necessárias nesta etapa.

**Resultado esperado:**

```text
Conjunto ajuste: 12 pergunta(s)
  simples 5 · composta 2 · individual 2 · sem evidência 1 · fora de escopo 1 · ambígua 1
Conjunto teste: 12 pergunta(s)
  simples 5 · composta 2 · individual 2 · sem evidência 1 · fora de escopo 1 · ambígua 1

Conferência: toda evidência esperada aparece em um dos 54 trechos dos documentos locais, nenhuma pergunta foi copiada dos documentos e os dois conjuntos não repetem ids nem perguntas.
```

### 1.2 Ler uma pergunta do conjunto de ajuste

Abra `dados\l100\avaliacao\ajuste.json` e localize `AJ-06`. Esta estrutura abreviada usa reticências no
lugar das alternativas; consulte o arquivo para ver o JSON completo:

```text
{
  "id": "AJ-06",
  "pergunta": "Qual é a diferença entre franquia e sublimite?",
  "tipo_esperado": "documentada",
  "assuntos": [
    { "nome": "franquia", "alternativas": [ ... ] },
    { "nome": "sublimite", "alternativas": [ ... ] }
  ],
  "fatos": ["prejuízo", "bens"]
}
```

**Atividade 1:** em `AJ-06`, conte os assuntos e as alternativas de cada um. Diga o que o programa exige para considerar a recuperação correta com `k=3` e quais fatos a resposta precisa conter.

**Conferência:** a pergunta tem dois assuntos, franquia e sublimite, e cada um tem mais de uma alternativa. Basta uma alternativa de cada assunto (o documento certo com a frase esperada) em um dos três primeiros trechos; o mesmo trecho pode cobrir os dois assuntos, ou cada assunto pode estar em um trecho. Os fatos esperados são as palavras "prejuízo" e "bens".

> **Atenção:** não abra `dados\l100\avaliacao\teste.json` agora. Quem conhece as perguntas do teste tende a ajustar o assistente a elas, mesmo sem querer.

### Prompt para o Copilot: entender o método antes de executar

Anexe `dados\l100\avaliacao\ajuste.json` e `scripts\lab_avaliacao.py`:

```text
Leia dados/l100/avaliacao/ajuste.json e scripts/lab_avaliacao.py anexados.
Explique, para quem não programa e com uma analogia, como o programa decide se um trecho recuperado é pertinente e como calcula o acerto@k e o MRR.
Use a pergunta AJ-06 como exemplo: mostre onde estão os dois assuntos, as alternativas de cada um e o que significa acertar essa pergunta com k=3.
Liste dois erros que esse método pode cometer e uma forma de reduzir cada um.
Não edite arquivos, não execute comandos, não acesse o Azure e não leia dados/l100/avaliacao/teste.json.
```

**Conferência:** a resposta deve dizer que cada assunto precisa de ao menos uma alternativa entre os `k` primeiros trechos (o documento certo e a frase esperada), que a pergunta composta só acerta com os dois assuntos e que o MRR olha só o primeiro trecho pertinente. Erros possíveis: uma frase esperada que também aparece em um trecho pouco útil (a recuperação parece melhor do que é) e uma alternativa escrita de forma estreita demais (uma busca boa parece falhar). Confira cada afirmação em `lab_avaliacao.py`: o Copilot pode descrever uma métrica de uso comum no lugar da que o programa calcula.

## Etapa 2: medir a recuperação no conjunto de ajuste

**Objetivo:** medir, nos três modos de busca, se os trechos pertinentes aparecem entre os primeiros. Esta etapa só lê o índice e leva cerca de 15 segundos.

```powershell
python scripts\avaliar_respostas.py --etapa recuperacao --conjunto ajuste --busca $busca --modelos $modelos
```

**Exemplo de saída registrada.** A recuperação dispensa geração de texto; os resultados dependem do
índice, dos documentos, dos embeddings e da busca:

```text
Recuperação · conjunto ajuste · 9 de 12 pergunta(s) têm resposta nos documentos e entram · acerto até k=10 · serviço de busca 'srch-vlr-...', índice 'vareleira-lar-l100'
  medindo o modo vetorial...
  medindo o modo texto...
  medindo o modo hibrida...

Perguntas com todos os assuntos entre os k primeiros trechos (acerto@k) e MRR (média de 1 sobre a posição do primeiro trecho pertinente):
  modo        acerto@1   acerto@3   acerto@5   acerto@10   MRR
  vetorial    7 de 9     9 de 9     9 de 9     9 de 9      1,00
  texto       5 de 9     7 de 9     9 de 9     9 de 9      0,78
  hibrida     6 de 9     9 de 9     9 de 9     9 de 9      0,87

Posição do primeiro trecho pertinente (- = nenhum nos 10 primeiros; * = faltam assuntos nos 10 primeiros):
  id      categoria       vetorial  texto     hibrida
  AJ-01   simples         1         1         1
  AJ-02   simples         1         1         1
  AJ-03   simples         1         1         1
  AJ-04   simples         1         1         1
  AJ-05   simples         1         2         1
  AJ-06   composta        1         3         2
  AJ-07   composta        1         1         1
  AJ-08   individual      1         5         3
  AJ-09   individual      1         1         1

Um trecho é pertinente quando contém uma das frases esperadas do conjunto. As perguntas sem resposta nos documentos ficam de fora, e a posição só vale dentro do mesmo modo.
```

**Atividade 2:** compare o acerto@1 com o acerto@3 de cada modo. Explique por que o acerto@1 do modo vetorial não passa de 7 de 9 e, mesmo assim, o MRR dele é 1,00.

**Conferência:** as duas perguntas compostas precisam de dois assuntos, e o primeiro trecho cobre um deles. Por isso as duas falham com `k=1` e o acerto@1 do modo vetorial para em 7 de 9. O MRR olha só o primeiro trecho que cobre algum assunto, e no modo vetorial esse trecho é o primeiro das 9 perguntas (MRR 1,00). O acerto@1 mede a composição das perguntas tanto quanto a busca; o acerto@3 e o acerto@5 informam melhor. Com `k=3`, os modos vetorial e híbrido acertam as 9 perguntas, e o modo texto só chega a 9 com `k=5`.

**Atividade 3:** na tabela de posições, localize `AJ-08` no modo texto (posição 5). Use
`buscar_trechos.py`, apresentado na Etapa 5 do Desafio 02, nos modos texto e vetorial e compare os
títulos dos cinco primeiros trechos:

```powershell
python scripts\buscar_trechos.py --busca $busca --modelos $modelos --pergunta "Meu seguro cobre vendaval se o telhado da minha casa voar?" --modo texto --k 5
python scripts\buscar_trechos.py --busca $busca --modelos $modelos --pergunta "Meu seguro cobre vendaval se o telhado da minha casa voar?" --modo vetorial --k 5
```

**Conferência:** no modo texto, os primeiros trechos são perguntas frequentes sobre outros assuntos ("Posso mudar de endereço e manter o seguro?", "O seguro cobre joias e relógios?" e "Se eu cancelar o seguro, quanto recebo de volta?"), e o primeiro trecho pertinente, "Como funciona a franquia?", é o quinto. No modo vetorial, o primeiro trecho é "Coberturas adicionais", que descreve vendaval e granizo. A busca por texto soma pontos por palavras em comum com a pergunta; a busca vetorial compara significados. Nenhum modo vence sempre, e a medição mostra onde cada um erra.

## Etapa 3: medir as respostas com a recuperação obrigatória

**Referência histórica:** os exemplos e números das Etapas 3 a 6 foram medidos com a política
anterior à correção de apresentação dos casos individuais. A política atual mantém tipo e situação,
mas substitui o texto individual por uma introdução fixa e citações. A métrica de fatos continua
olhando somente o texto mostrado, não as citações; por isso os fatos individuais dos exemplos
não são uma previsão de nova execução. O conjunto de teste original permanece medido uma única vez.

**Objetivo:** medir, para cada pergunta do conjunto de ajuste, o tipo, a situação e os fatos do fluxo dos Desafios 03 e 04: o programa busca antes (modo híbrido, `k=5`) e entrega os trechos ao modelo. Esta etapa não altera o Azure; consome cerca de 19 mil tokens de entrada e leva cerca de 45 segundos.

```powershell
python scripts\avaliar_respostas.py --etapa respostas --conjunto ajuste --busca $busca --modelos $modelos --deployment-geracao $deploymentGeracao
```

**Exemplo de saída registrada** (tipos, situações, tokens e tempos podem variar; no ajuste, perguntas
com falha aparecem abaixo de suas linhas):

```text
Respostas · conjunto ajuste · 12 pergunta(s) · recuperação obrigatória · modo hibrida · k 5 · esforço low · deployment 'geracao'
  [ok]    AJ-01  simples        tipo documentada            respondida     fatos 1/1   1458 tokens  12,3 s
  [ok]    AJ-02  simples        tipo documentada            respondida     fatos 2/2   1922 tokens   2,0 s
  [ok]    AJ-03  simples        tipo documentada            respondida     fatos 1/1   1557 tokens   3,2 s
  [ok]    AJ-04  simples        tipo documentada            respondida     fatos 1/1   1668 tokens   2,5 s
  [ok]    AJ-05  simples        tipo documentada            respondida     fatos 1/1   1079 tokens   2,2 s
  [ok]    AJ-06  composta       tipo documentada            respondida     fatos 2/2   1621 tokens   2,4 s
  [ok]    AJ-07  composta       tipo documentada            respondida     fatos 3/3   1783 tokens   3,1 s
  [ok]    AJ-08  individual     tipo contratacao_individual respondida     fatos 1/1   1697 tokens   4,2 s
  [ok]    AJ-09  individual     tipo contratacao_individual respondida     fatos 1/1   2093 tokens   4,0 s
  [falha] AJ-10  sem evidência  tipo fora_de_escopo         recusada       fatos -     1441 tokens   2,1 s  tipo fora_de_escopo, esperado sem_evidencia
           "Qual é o telefone do Atendimento?"
  [ok]    AJ-11  fora de escopo tipo fora_de_escopo         recusada       fatos -     1304 tokens   1,7 s
  [ok]    AJ-12  ambígua        tipo ambigua                esclarecimento fatos -     1530 tokens   2,2 s

Resumo
  Tipo da pergunta correto .......... 11 de 12
  Situação correta .................. 12 de 12 (respondeu, recusou ou pediu esclarecimento como devia)
  Respostas descartadas pela verificação .. 0
  Erros de formato do modelo ........ 0
  Falsas recusas .................... 0 (pergunta com resposta nos documentos que não foi respondida)
  Falsas respostas .................. 0 (pergunta sem resposta nos documentos que foi respondida)
  Fatos esperados presentes ......... 13 de 13 (nas respostas mostradas)
  Tokens de entrada (média) ......... 1596
  Tokens de saída (média) ........... 232
  Buscas por pergunta (média) ....... 1,0
  Tempo por pergunta (média) ........ 3,5 s

  categoria       perguntas  tipo certo  situação certa  fatos
  simples                 5           5               5  6/6
  composta                2           2               2  5/5
  individual              2           2               2  2/2
  sem evidência           1           0               1  -
  fora de escopo          1           1               1  -
  ambígua                 1           1               1  -
```

A primeira pergunta demorou mais nas execuções registradas; a causa permanece a confirmar.
A tabela final agrupa os resultados por categoria, sem listar o texto das perguntas.

**Atividade 4:** leia a linha `[falha]` e diferencie tipo de situação. Diga qual das duas medidas importa mais para quem pergunta e por que o programa conta as duas.

**Conferência:** `AJ-10` pergunta pelo telefone do Atendimento, que os documentos não informam.
O tipo esperado é `sem_evidencia`; nessa execução, o modelo propôs `fora_de_escopo`.
Ambos resultam em recusa: a situação foi correta, embora o tipo tenha divergido.
Use o tipo para diagnosticar a classificação e a situação para avaliar a conduta mostrada à pessoa.
Registre a diferença sem alterar o conjunto para acomodar o resultado.

**Atividade 5:** anote as oito medidas do resumo: tipo correto, situação correta, descartes, falsas recusas, falsas respostas, fatos presentes, tokens de entrada e tempo. Você as usará na Etapa 4.

## Etapa 4: comparar configurações

**Objetivo:** variar um parâmetro por vez e comparar as métricas e o consumo. Esta etapa mantém os
recursos do Azure; as execuções registradas consumiram de 14 mil a 34 mil tokens de entrada.

A configuração tem quatro parâmetros: fluxo (`--recuperacao obrigatoria` ou `ferramenta`), modo de busca
(`--modo`), quantidade de trechos (`--k`) e esforço do modelo (`--esforco`).
Mude um por vez e repita as medições para distinguir o efeito da mudança da variação do modelo.
Mantenha o esforço `low` nesta comparação.

```powershell
python scripts\avaliar_respostas.py --etapa respostas --conjunto ajuste --busca $busca --modelos $modelos --deployment-geracao $deploymentGeracao --k 3
python scripts\avaliar_respostas.py --etapa respostas --conjunto ajuste --busca $busca --modelos $modelos --deployment-geracao $deploymentGeracao --modo vetorial
python scripts\avaliar_respostas.py --etapa respostas --conjunto ajuste --busca $busca --modelos $modelos --deployment-geracao $deploymentGeracao --recuperacao ferramenta
```

Os três comandos mudam, respectivamente, a quantidade de trechos, o modo de busca e o fluxo (o agente do Desafio 05 decide quando buscar, com até 2 buscas). A execução da Etapa 3 é a quarta configuração.

**Referência para comparar sua medição:** uma execução por configuração, depois da correção do
normalizador. Tokens e tempo são médias por pergunta:

| Configuração | Tipo correto | Situação correta | Descartes | Falsas recusas | Falsas respostas | Fatos presentes | Tokens de entrada | Tempo por pergunta |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Obrigatória, vetorial, `k=3` | 11 de 12 | 12 de 12 | 0 | 0 | 0 | 12 de 13 | 1.182 | 3,1 s |
| Obrigatória, híbrida, `k=3` | 11 de 12 | 12 de 12 | 0 | 0 | 0 | 13 de 13 | 1.188 | 3,3 s |
| Obrigatória, vetorial, `k=5` | 11 de 12 | 12 de 12 | 0 | 0 | 0 | 12 de 13 | 1.590 | 3,3 s |
| Obrigatória, híbrida, `k=5` | 11 de 12 | 12 de 12 | 0 | 0 | 0 | 13 de 13 | 1.596 | 3,5 s |
| Ferramenta, vetorial, `k=5` | 12 de 12 | 12 de 12 | 0 | 0 | 0 | 12 de 13 | 2.547 | 6,8 s |
| Ferramenta, híbrida, `k=5` | 12 de 12 | 12 de 12 | 0 | 0 | 0 | 13 de 13 | 2.840 | 6,5 s |
| Ferramenta, híbrida, `k=3` | 12 de 12 | 12 de 12 | 0 | 0 | 0 | 13 de 13 | 2.235 | 6,3 s |

Os comandos do guia produzem as linhas 2, 3, 4 e 6. As linhas 1, 5 e 7 são extras, para consulta.

**Atividade 6:** preencha a sua tabela com as quatro execuções e responda: (a) alguma configuração teve falsa resposta? (b) Quanto o consumo de tokens de entrada muda de `k=5` para `k=3` e da recuperação obrigatória para a ferramenta? (c) As diferenças de qualidade são grandes o bastante para escolher uma configuração? Guarde a resposta de (c) para a Etapa 5.

**Conferência:** (a) nessa amostra, as sete configurações acertaram a situação das 12 perguntas, com
zero falsas respostas, falsas recusas e descartes. (b) Na recuperação obrigatória híbrida, `k=3`
consumiu cerca de 26% menos tokens que `k=5` (1.188 contra 1.596). A ferramenta consumiu de 1,6 a 1,9 vez
os tokens de entrada e aproximadamente o dobro do tempo. (c) As diferenças de tipo e de fatos presentes
precisam ser examinadas: a comparação por frase pode reprovar uma redação equivalente. A Etapa 5 repete
a medição para observar quanto esses resultados variam.

## Etapa 5: repetir a medição e escolher

**Objetivo:** medir a variação do modelo, aplicar a meta de Teresa e escolher uma configuração. Cada comando repete a medição três vezes, leva de 2 a 4 minutos e consome de 43 mil a 89 mil tokens de entrada. Esta etapa não altera o Azure.

A opção `--repeticoes` executa a medição de 1 a 5 vezes e mostra a faixa de cada número.
Aplique o critério registrado antes da Etapa 2:

1. nenhuma falsa resposta em nenhuma repetição;
2. em cada repetição, a situação correta em pelo menos 11 das 12 perguntas;
3. entre as configurações que cumprem as duas primeiras regras, a de menor consumo de tokens de entrada.

Escolha as candidatas na tabela da Etapa 4: as que cumprem a meta em uma execução e diferem no custo. Na validação, as candidatas foram a recuperação obrigatória com `k=3`, a recuperação obrigatória com `k=5` e a ferramenta com `k=3`. O modo vetorial ficou de fora: o ganho dele na recuperação (Etapa 2) não apareceu nas respostas.

```powershell
python scripts\avaliar_respostas.py --etapa respostas --conjunto ajuste --busca $busca --modelos $modelos --deployment-geracao $deploymentGeracao --k 3 --repeticoes 3
python scripts\avaliar_respostas.py --etapa respostas --conjunto ajuste --busca $busca --modelos $modelos --deployment-geracao $deploymentGeracao --k 5 --repeticoes 3
python scripts\avaliar_respostas.py --etapa respostas --conjunto ajuste --busca $busca --modelos $modelos --deployment-geracao $deploymentGeracao --k 3 --recuperacao ferramenta --repeticoes 3
```

Cada execução mostra o resumo completo, como na Etapa 3, e termina com a variação entre as repetições.

**Exemplo de saída registrada** (final do primeiro comando; os números variam):

```text
Variação entre as 3 execuções (o modelo não responde igual a cada vez)
  Tipo da pergunta correto .......... 11 de 12
  Situação correta .................. de 11 a 12 de 12
  Respostas descartadas ............. de 0 a 1
  Fatos esperados presentes ......... de 10 a 13
```

Referência para comparar sua medição: três repetições por candidata, com tokens e tempo médios por pergunta:

| Configuração | Tipo correto | Situação correta | Descartes | Falsas respostas | Fatos presentes | Tokens de entrada | Tempo por pergunta |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Obrigatória, híbrida, `k=3` | 11 de 12 nas 3 | de 11 a 12 de 12 | de 0 a 1 | 0 | de 10 a 13 | 1.188 | de 2,5 a 3,2 s |
| Obrigatória, híbrida, `k=5` | de 10 a 11 de 12 | de 11 a 12 de 12 | de 0 a 1 | 0 | de 11 a 13 | 1.596 | de 2,6 a 3,3 s |
| Ferramenta, híbrida, `k=3` | 12 de 12 nas 3 | 12 de 12 nas 3 | 0 | 0 | 13 de 13 nas 3 | de 2.293 a 2.732 | de 6,1 a 7,4 s |

Os fatos esperados são contados só nas respostas mostradas, e por isso o total muda de uma repetição para outra.

**Atividade 7:** aplique a meta às candidatas. Qual você escolhe e por quê? Considere: o agente acertou a situação nas 36 respostas das três repetições, a recuperação obrigatória com `k=3` errou 1 em 36 e a com `k=5` errou 2 em 36. Essa diferença é grande o bastante para decidir?

**Conferência:** na primeira amostra, as três candidatas cumpriram a meta. A recuperação obrigatória
híbrida com `k=3` foi escolhida pela menor média de entrada: 1.188 tokens por pergunta.
O agente teve zero falhas de situação, mas essa diferença de uma ou duas respostas em 36 é pequena
para sustentar uma escolha isoladamente. Ele consumiu de 1,9 a 2,3 vezes os tokens de entrada e
aproximadamente o dobro do tempo. Na segunda amostra, as três configurações acertaram a situação de
todas as 36 respostas. Registre sua escolha com o critério e os números usados antes de seguir.

Se uma resposta do ajuste for descartada, compare a citação com o trecho indicado. Unir o título e o
parágrafo com dois-pontos, por exemplo "Sublimite: Limite menor, ...", altera a frase e pode provocar
descarte. A investigação registrada de `AJ-06` está no
[relato dos descartes](../../docs/validacao/l100-06-avaliar-respostas.md#o-defeito-que-a-medição-encontrou).

## Etapa 6: medir o conjunto de teste uma única vez

**Objetivo:** estimar o desempenho com perguntas novas, com a configuração escolhida. O programa mostra só os números. Cada comando é executado uma única vez, e esta etapa não altera o Azure.

Com a escolha registrada, meça o conjunto de teste e mantenha a configuração durante a medição.
Os comandos abaixo correspondem à escolha do registro: recuperação obrigatória, modo híbrido,
`k=3`, esforço `low`. Se você escolheu outra configuração, ajuste seus argumentos **antes** de medir.
Alterar a configuração em resposta aos números do teste transforma esse conjunto em ajuste [1].

```powershell
python scripts\avaliar_respostas.py --etapa recuperacao --conjunto teste --busca $busca --modelos $modelos
python scripts\avaliar_respostas.py --etapa respostas --conjunto teste --busca $busca --modelos $modelos --deployment-geracao $deploymentGeracao --k 3
```

**Exemplo de saída registrada** (uma medição da recuperação e uma das respostas):

```text
Recuperação · conjunto teste · 9 de 12 pergunta(s) têm resposta nos documentos e entram · acerto até k=10 · serviço de busca 'srch-vlr-...', índice 'vareleira-lar-l100'
Conjunto de teste: meça uma vez, com a configuração que você escolheu no conjunto de ajuste. Mudar a configuração depois de ver estes números transforma o teste em ajuste. Só os números aparecem; --mostrar-perguntas mostra o resto.
  medindo o modo vetorial...
  medindo o modo texto...
  medindo o modo hibrida...

Perguntas com todos os assuntos entre os k primeiros trechos (acerto@k) e MRR (média de 1 sobre a posição do primeiro trecho pertinente):
  modo        acerto@1   acerto@3   acerto@5   acerto@10   MRR
  vetorial    4 de 9     7 de 9     8 de 9     9 de 9      0,79
  texto       5 de 9     7 de 9     8 de 9     8 de 9      0,83
  hibrida     5 de 9     8 de 9     8 de 9     9 de 9      0,85
```

```text
Respostas · conjunto teste · 12 pergunta(s) · recuperação obrigatória · modo hibrida · k 3 · esforço low · deployment 'geracao'
Conjunto de teste: meça uma vez, ... (o mesmo aviso)

Resumo
  Tipo da pergunta correto .......... 10 de 12
  Situação correta .................. 10 de 12 (respondeu, recusou ou pediu esclarecimento como devia)
  Respostas descartadas pela verificação .. 0
  Erros de formato do modelo ........ 0
  Falsas recusas .................... 2 (pergunta com resposta nos documentos que não foi respondida)
  Falsas respostas .................. 0 (pergunta sem resposta nos documentos que foi respondida)
  Fatos esperados presentes ......... 8 de 8 (nas respostas mostradas)
  Tokens de entrada (média) ......... 1150
  Tokens de saída (média) ........... 167
  Buscas por pergunta (média) ....... 1,0
  Tempo por pergunta (média) ........ 3,3 s

  categoria       perguntas  tipo certo  situação certa  fatos
  simples                 5           5               5  5/5
  composta                2           1               1  2/2
  individual              2           1               1  1/1
  sem evidência           1           1               1  -
  fora de escopo          1           1               1  -
  ambígua                 1           1               1  -
```

**Atividade 8:** compare o ajuste e o teste. (a) Na recuperação, qual modo liderava no ajuste e qual lidera no teste? (b) Nas respostas, compare a situação correta, as falsas recusas e as falsas respostas com o que você mediu nas repetições da Etapa 5 e com a meta de Teresa. (c) Escreva duas frases que você diria à Teresa.

**Conferência:** (a) O MRR liderou no modo vetorial no ajuste (1,00) e no híbrido no teste (0,85).
Com nove perguntas elegíveis por conjunto, a comparação é sensível à composição da amostra.
(b) A configuração escolhida passou de 11 ou 12 situações corretas no ajuste para 10 no teste,
com duas falsas recusas e zero falsas respostas. **A meta de pelo menos 11 em 12 não foi atingida.**
Uma nova avaliação final exige perguntas novas; qualquer aceitação de um critério diferente precisa
ser registrada como nova decisão. (c) Uma síntese para Teresa: "A situação foi correta em 10 das
12 perguntas guardadas; as duas falhas foram falsas recusas. A contagem de falsas respostas foi zero,
mas essa medida não examina a fidelidade de todas as afirmações. A amostra ainda é insuficiente para
estimar uma taxa de acerto geral com precisão."

> **Atenção:** `--mostrar-perguntas` revela o texto e o resultado de cada pergunta, inclusive no teste.
> Use-a depois de encerrar a avaliação final desse conjunto. Reserve perguntas novas para avaliar
> futuras mudanças.

### Prompt para o Copilot: interpretar os números sem olhar o teste

Cole os números das duas medições (a tabela da recuperação e o bloco "Resumo" do ajuste e do teste). Não cole perguntas:

```text
Vou colar abaixo os números de duas medições (ajuste e teste) de um assistente que responde sobre seguro residencial. Não vou colar as perguntas.
[cole aqui a tabela da recuperação e o bloco "Resumo" de cada medição]
Explique, para quem não programa, o que os números dizem e o que eles não permitem concluir.
Diga o que uma diferença de uma pergunta em 12 significa e por que não devo mudar a configuração depois de ver o resultado do teste.
Não proponha mudanças no código e não execute comandos.
```

**Conferência:** a resposta deve explicar o peso de uma pergunta em 12, distinguir estimação de ajuste
e apontar as duas falsas recusas. Se sugerir que `k=5` resolveria o problema, classifique a afirmação
como hipótese: só a configuração escolhida foi medida no teste. Zero falsas respostas também não
equivale a uma avaliação completa da fidelidade do texto.

## Etapa 7: testar a avaliação sem o Azure

**Objetivo:** executar os testes locais da avaliação. Eles usam dublês, objetos que simulam os
serviços externos, sem Azure ou consumo de tokens.

```powershell
python -m unittest discover -s tests -p "test_avaliacao.py"
```

**Resultado esperado:** uma linha de pontos, `Ran 48 tests` e `OK`.

**Atividade 9:** abra `tests\test_avaliacao.py` e localize três testes: o que garante que a pergunta composta só acerta com todos os assuntos dentro de `k`, o do conjunto de teste que mostra só os números até alguém pedir as perguntas e o que impede as perguntas do teste de aparecerem em guias, registros e instruções. Descreva o que cada um garante.

**Conferência:** `test_pergunta_composta_so_acerta_com_todos_os_assuntos_dentro_do_k` fixa a regra do acerto@k. `test_conjunto_de_teste_mostra_so_os_numeros_ate_pedir_as_perguntas` executa o programa com um serviço de modelos simulado e confirma que, sem `--mostrar-perguntas`, a saída não traz o texto nem os ids das perguntas do teste. `test_as_perguntas_de_teste_nao_aparecem_em_guias_registros_nem_instrucoes` percorre os guias, os registros, a pasta `.github`, o README, o CONTRIBUTING e as instruções do modelo, e falha se alguma pergunta do teste aparecer neles: é o que mantém o teste guardado também no repositório. Os testes trocam o Azure por dublês, como nos desafios anteriores.

## Como pedir uma mudança ao Copilot no VS Code

Use o [procedimento do Desafio 01](01-preparar-ambiente.md#como-pedir-uma-mudança-ao-copilot-no-vs-code):
contexto, plano, limites, revisão do diff (comparação entre versões dos arquivos) e verificação com
comandos autorizados. Preserve o teste: não anexe `dados\l100\avaliacao\teste.json` ao pedido nem use
suas perguntas para ajustar o assistente.

### Exemplo: salvar o resumo de cada medição em um arquivo

Cole com os arquivos anexados:

```text
Leia o README, o L100 Desafio 06, scripts/avaliar_respostas.py e scripts/lab_avaliacao.py anexados.
Quero uma opção nova em avaliar_respostas.py: --salvar CAMINHO, que grava em JSON o resumo de cada execução da etapa respostas: as contagens, as médias e a configuração usada (fluxo, modo, k e esforço).
Antes de editar, proponha o plano: arquivos, funções e testes.
Cuidados obrigatórios: não grave o texto das perguntas, os ids do conjunto de teste, os nomes dos recursos do Azure (busca e modelos) nem identificadores da assinatura;
se o arquivo já existir, recuse com mensagem em pt-BR e código de saída 1, sem sobrescrever; não altere as métricas, a política nem os conjuntos de perguntas.
Escreva testes com unittest e dublês, sem acessar o Azure.
Use o Python do ambiente virtual, .\.venv\Scripts\python.exe, e execute apenas:
.\.venv\Scripts\python.exe -m unittest discover -s tests
Não instale pacotes, não acesse o Azure, não leia dados/l100/avaliacao/teste.json e não altere o índice.
```

**Conferência:** o diff deve gravar só números e a configuração, recusar um arquivo que já existe e trazer testes para o caminho novo, o caminho existente e a ausência da opção. Confira o vazamento: o Copilot pode incluir `args.busca` e `args.modelos` "para documentar a execução", ou o texto das perguntas do teste "para facilitar a leitura". Confira também que as etapas `validar` e `recuperacao` continuam iguais, e revise o `git status` antes de qualquer commit: um arquivo de resultados não deve entrar no repositório por descuido.

> **Dica:** peça uma explicação do diff, com palavras simples, antes de aceitá-lo. Outros pedidos para praticar: "explique cada teste de `test_avaliacao.py` em uma frase" e "proponha, sem editar, três perguntas novas para formar um novo conjunto de teste, sem copiar frases dos documentos e com o assunto e os fatos esperados de cada uma". Escreva o novo conjunto de teste antes de ajustar qualquer coisa com ele.

**Modo construtor (opcional).** Para ver como o Copilot resolveria o desafio, peça um plano em uma pasta separada e compare o resultado com os arquivos deste projeto pelo diff:

```text
Leia o L100, Desafio 06, o README e as instruções do projeto.
Proponha, sem editar, como medir um assistente que responde sobre documentos com dois conjuntos de perguntas:
o que cada pergunta precisa registrar, como medir a recuperação e as respostas, como contar falsas respostas e falsas recusas,
como evitar que o conjunto de teste vire conjunto de ajuste e o que a medição não consegue provar.
Não provisione recursos, atribua papéis, envie dados nem exclua arquivos.
```

Qualquer ação que altere o Azure continua dependendo da sua decisão.

## Conferência do resultado

| Verificação | Como conferir | Evidência esperada |
| --- | --- | --- |
| Conjuntos válidos | Etapa 1.1 e a Atividade 1 | "Conferência: toda evidência esperada aparece em um dos 54 trechos..." |
| Recuperação no ajuste | Etapa 2 e as Atividades 2 e 3 | Tabela com os três modos; vetorial e híbrido com 9 de 9 em acerto@3 |
| Respostas com a recuperação obrigatória | Etapa 3 e as Atividades 4 e 5 | Resumo com tipos, situações, falsas recusas, falsas respostas e descartes, inclusive quando a meta falhar |
| Comparação das configurações | Etapa 4 e a Atividade 6 | Tabela com as quatro configurações e o consumo de tokens |
| Variação e escolha | Etapa 5 e a Atividade 7 | Faixas das três repetições e uma configuração escolhida pela meta |
| Conjunto de teste | Etapa 6 e a Atividade 8 | Uma medição por etapa, com configuração previamente escolhida; registrar os números e se a meta foi atingida |
| Testes sem Azure | Etapa 7 e a Atividade 9 | `Ran 48 tests` e `OK` |

Antes de encerrar, registre em local privado o grupo de recursos, os nomes da busca e dos modelos, a configuração escolhida e a decisão de manter, pausar ou remover os recursos. Ao compartilhar evidências, remova das saídas do terminal os identificadores do ambiente, os nomes de recursos e as contas de usuário.

## Solução de problemas

Faça repetições e diagnósticos por pergunta no **conjunto de ajuste**. No teste, preserve a
configuração, registre o resultado ou a interrupção e encerre essa avaliação antes de investigar as
perguntas. Mudanças posteriores exigem um conjunto novo para a próxima medição final.

| Sintoma | O que conferir | O que evitar |
| --- | --- | --- |
| `[ERRO]` "Informe o conjunto: --conjunto ajuste ou --conjunto teste." (código 1) | Acrescente `--conjunto` aos comandos das etapas `recuperacao` e `respostas` | Medir sem escolher o conjunto |
| `[ERRO]` "Ids fora do conjunto: ..." (código 1) | A mensagem lista os ids do conjunto escolhido; use um deles em `--ids` | Misturar ids do ajuste com o conjunto de teste |
| "As repetições devem ser um número de 1 a 5" (código 1) | Use `--repeticoes` com um valor de 1 a 5 | Repetir sem limite: o custo cresce com cada repetição |
| `[ERRO]` "Nenhuma das perguntas escolhidas tem resposta nos documentos..." (código 1) | Em `--etapa recuperacao`, inclua em `--ids` ao menos uma pergunta com resposta nos documentos | Tirar a conclusão de uma medição vazia |
| `[FALHA]` "Os conjuntos não conferem com os documentos locais" (código 3) | A lista abaixo da mensagem: evidência que não aparece nos trechos, pergunta copiada dos documentos ou id repetido. Se você editou um documento ou um conjunto, desfaça a edição ou corrija a evidência | Editar a evidência só para a medição passar |
| Linha `[falha]` com "resposta descartada: a citação de ... não aparece literalmente no trecho" | No ajuste, compare a citação com a fonte e investigue repetições com `perguntar.py --politica completa`. No teste, registre o descarte na medição final | Afrouxar a conferência de citações ou usar o teste para ajustar |
| "Erros de formato do modelo" maior que 0 | O modelo devolveu algo fora do formato esperado; a medição conta o erro e continua. Repita; se persistir, use `--detalhes` | Remover a pergunta do conjunto |
| O resultado muda a cada execução | É esperado: o modelo varia. Use `--repeticoes 3` e compare faixas, não números únicos | Escolher a melhor entre várias execuções |
| O teste ficou pior que o ajuste | Registre a diferença e compare com a meta previamente definida; o desempenho no ajuste pode ser favorecido pela escolha da configuração | Ler as perguntas do teste para ajustar o assistente a elas |
| Fato esperado ausente em uma resposta que parece correta | O fato é uma frase literal, e o modelo pode ter escrito com outras palavras (por exemplo, "R$ 5 mil"). Leia a resposta com `perguntar.py --politica completa` antes de concluir que ela está errada | Mudar o fato esperado para o número melhorar |
| `[ERRO]` durante a medição (login, permissão, tempo esgotado do agente) | A medição para e não calcula o resumo. No ajuste, corrija a causa e repita. No teste, registre a interrupção e a exposição já ocorrida antes de decidir uma nova avaliação final | Interpretar linhas parciais como medição concluída |
| `[ERRO]` "O Azure respondeu 404 ('Subdomain does not map to a resource')" (código 2) | O nome em `$modelos`. Com o nome certo, o serviço de modelos às vezes responde assim de forma intermitente: aguarde alguns minutos e repita | Recriar o recurso ou o deployment só para o erro desaparecer |
| `[AVISO]` "O serviço de modelos respondeu 404 intermitente (tentativa N de 6)" | Nada: o programa repete sozinho esse erro. Se as seis tentativas falharem, siga a linha anterior | Interromper e recriar recursos |
| Erros dos desafios anteriores (login, tenant, papéis, deployment, cota) | [Solução de problemas do Desafio 03](03-responder-com-fontes.md#solução-de-problemas) | Pular a conferência |

Se precisar de ajuda, consulte os [canais e limites do suporte](../../SUPPORT.md). Não conceda papéis,
altere políticas corporativas ou desative controles como tentativa de diagnóstico.

## Custos, pausa e limpeza

O uso do Copilot segue o plano da sua conta e as regras de consumo dele, separadamente da assinatura Azure. Este desafio não cria recursos: a cobrança do Azure continua vindo dos recursos dos Desafios 01 a 03.

**O que gera custo neste desafio:** os tokens de cada medição das respostas e, em escala muito menor, os embeddings das perguntas. As etapas `validar` e `recuperacao` não usam o modelo de geração. Na validação, uma execução de 12 perguntas consumiu:

| Medição | Tokens de entrada por pergunta (média) | Tokens de entrada em 12 perguntas (aprox.) |
| --- | --- | --- |
| Obrigatória, `k=3` | 1.188 | 14 mil |
| Obrigatória, `k=5` | 1.596 | 19 mil |
| Ferramenta, `k=3` | de 2.235 a 2.732 | de 27 mil a 33 mil |
| Ferramenta, `k=5` | 2.840 | 34 mil |

Cada repetição acrescenta consumo. `--repeticoes 3` costuma produzir um total próximo de três
execuções, mas o número de buscas e o tamanho das respostas podem variar. Nas medições registradas,
a média de saída ficou entre 167 e 255 tokens por pergunta. Para calcular o custo em dinheiro,
aplique os [preços dos modelos do Azure OpenAI](https://azure.microsoft.com/en-us/pricing/details/azure-openai/)
ao consumo de entrada, saída e embeddings [4].

**Pausa e limpeza.** Como o desafio não cria recursos, a pausa e a limpeza são as do [Desafio 03](03-responder-com-fontes.md#custos-pausa-e-limpeza) e do [Desafio 02](02-indexar-documentos.md#custos-pausa-e-limpeza).

## Situação da validação

Data de referência: 9 de outubro de 2026. O registro detalhado, com a matriz de testes, as séries de medição, o defeito que a medição encontrou e as observações de operação, está em [docs\validacao\l100-06-avaliar-respostas.md](../../docs/validacao/l100-06-avaliar-respostas.md).

**Versões testadas:** Windows, Python 3.12.10, Azure CLI (interface de linha de comando) 2.89.0, `agent-framework-core` 1.21.0, `agent-framework-openai` 1.15.0, `openai` 3.23.0, `azure-search-documents` 12.0.0 e as bibliotecas dos desafios anteriores.

| Item | Situação | Detalhe |
| --- | --- | --- |
| Comandos das Etapas 1 a 5 e 7 | Concluído | Extraídos do próprio guia e executados linha a linha em PowerShell 7.6, em `brazilsouth`, sobre o ambiente dos Desafios 01 a 03, com o código de saída esperado em todas as linhas |
| Comandos da Etapa 6 (conjunto de teste) | Concluído | Uma execução da recuperação e uma das respostas, com os argumentos do guia; preservadas como medições finais, sem repetição |
| Scripts e testes automáticos (sem Azure) | Concluído | Testes aprovados, com 48 casos novos em `test_avaliacao.py` |
| Links, âncoras, URLs e referências dos guias | Concluído | Nenhum link ou âncora inválido |
| Medição única do conjunto de teste | Concluído | Uma execução da recuperação e uma das respostas, com a configuração escolhida antes; nenhuma pergunta do teste foi exibida nas saídas |
| Meta de escolha no histórico | Concluído | Definida após o ajuste e antes do teste. O exercício recomenda registrá-la antes da Etapa 2; a diferença está documentada no registro |
| Resultado no teste | Concluído | 10 de 12 situações corretas, duas falsas recusas e zero falsas respostas; a meta de 11 em 12 não foi atingida |
| Independência dos conjuntos | Pendente | A autoria dos conjuntos, do código e da medição foi a mesma. Perguntas foram preservadas após a medição; um novo teste independente exige revisão ou autoria por outra pessoa |
| Aprovação dos conjuntos de perguntas | Confirmada | Pelo mantenedor, em 9 de outubro de 2026; a independência parcial e as medições anteriores permanecem registradas |
| Aprovação do conteúdo dos documentos sintéticos | Confirmada | Pelo mantenedor, em 9 de outubro de 2026; registro no inventário |
| Aprovação do texto, do código e dos resultados | Confirmada | Pelo mantenedor, em 9 de outubro de 2026; a meta não atingida continua registrada |
| Outros ambientes: macOS, Linux, WSL (Windows Subsystem for Linux), Python diferente do 3.12 e Windows PowerShell 5.1 | Pendente | Executar os comandos do guia nesses ambientes e registrar as diferenças |
| Outros modelos de geração, outras versões do MAF e conjuntos maiores | Pendente | Só o `gpt-5.4-mini` e as versões fixadas foram validados; 12 perguntas por conjunto e 3 repetições não permitem conclusões finas |
| Interações com o Copilot: prompts do guia, exemplo de pedido de mudança e modo construtor | Pendente | Executar no VS Code e registrar as respostas |
| Custo | Pendente | Medir o custo no Cost Management após uma execução completa |

**Autoria.** Código, testes e texto produzidos com apoio de inteligência artificial (IA), com Claude
Sonnet 5.5 no GitHub Copilot CLI; o Astra estava indisponível. Revisão editorial por GPT-6.1 Sol, em
9 de outubro de 2026. Os modelos de autoria e revisão são independentes do modelo escolhido no Copilot
e dos deployments da aplicação Azure (`text-embedding-3-small` e `gpt-5.4-mini`).

## Glossário

| Termo | Significado no exercício |
| --- | --- |
| Conjunto de ajuste | Perguntas que você pode ler e medir quantas vezes quiser para comparar configurações |
| Conjunto de teste | Perguntas guardadas, medidas uma única vez com a configuração já escolhida, para estimar o desempenho com perguntas novas |
| Sobreajuste | Adaptação excessiva ao que já foi visto, que piora a previsão do que é novo; aqui, a configuração escolhida só porque se saiu bem nas perguntas do ajuste |
| Configuração | Combinação de fluxo (recuperação obrigatória ou por ferramenta), modo de busca, `k` e esforço do modelo |
| Meta (critério de escolha) | Regra escrita antes de olhar os resultados, que diz quando uma configuração serve e como desempatar |
| Tipo esperado | Um dos cinco tipos do Desafio 04 que a pergunta deveria receber |
| Situação | O que a pessoa vê: respondida, recusada, esclarecimento ou descartada |
| Assunto (de uma pergunta) | Informação que os trechos recuperados precisam trazer para a pergunta ser respondida; a pergunta composta tem mais de um |
| Alternativa | Documento e frase que, se aparecerem em um trecho, satisfazem um assunto |
| Fato esperado | Frase curta que a resposta mostrada deveria conter |
| Pergunta composta | Pergunta com dois assuntos que moram em trechos diferentes |
| `k` | Quantidade de trechos que cada busca devolve e que o modelo recebe |
| acerto@k | Parte das perguntas cujos assuntos aparecem todos entre os `k` primeiros trechos |
| *Recall at K* | Cobertura: parte dos trechos pertinentes que aparece entre os `k` primeiros; o acerto@k é a variação que exige todos os assuntos |
| MRR | *Mean reciprocal rank*: média, entre as perguntas, de 1 dividido pela posição do primeiro trecho pertinente |
| Falsa recusa | Pergunta com resposta nos documentos que foi recusada ou que recebeu um pedido de esclarecimento |
| Falsa resposta | Pergunta cuja situação esperada é recusa ou esclarecimento, mas que foi respondida |
| Descarte (da resposta) | Decisão do programa de não mostrar a resposta porque ela não passou na verificação |
| Repetição | Nova execução da mesma medição, sem mudar nada, para ver a variação do modelo |
| Variação (entre execuções) | Diferença entre os resultados de execuções idênticas, causada pelo modelo |
| Amostra | Conjunto de perguntas medidas; quanto menor, mais cada pergunta pesa no resultado |
| Ponto percentual | Unidade da diferença entre duas porcentagens; uma pergunta em 12 vale cerca de 8 pontos percentuais |
| Token | Fragmento de texto que o modelo conta e cobra, na entrada e na saída |
| JSON | Formato de texto estruturado em pares nome-valor, usado nos conjuntos de perguntas |
| Dublê (de teste) | Peça que imita um serviço externo nos testes; aqui, o serviço de modelos simulado de `tests\support.py` |

## Referências

Fontes oficiais consultadas em 9 de outubro de 2026. Nomes de interface, limites, preços e disponibilidade mudam: confira a versão atual antes de aplicar.

1. [Evitar o sobreajuste e dados desbalanceados com o ML automatizado (Azure Machine Learning)](https://learn.microsoft.com/en-us/azure/machine-learning/concept-manage-ml-pitfalls).
2. [Desenvolver uma solução RAG no Azure: fase de recuperação de informações](https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/rag/rag-information-retrieval).
3. [Desenvolver uma solução RAG no Azure: fase de avaliação de ponta a ponta do modelo de linguagem](https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/rag/rag-llm-evaluation-phase).
4. [Preços dos modelos do Azure OpenAI](https://azure.microsoft.com/en-us/pricing/details/azure-openai/).

As atribuições do contexto fictício estão em [NOTICE.md](../../NOTICE.md). O texto deste guia está sob a licença Creative Commons Atribuição 4.0 (CC BY 4.0; veja [LICENSE](../../LICENSE)).
