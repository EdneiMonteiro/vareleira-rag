# L400 · Desafio 05: comparar estratégias com evidência

[Início](../../README.md) · [Desafio 04](04-evoluir-indice.md) · [Desafio 06](06-testar-carga-interrupcao.md)

| Campo | Definição |
| --- | --- |
| Situação | Comparação final executada uma vez; 16/16 conformes em ambas, sem ganho observado da coordenação |
| Público | Atendimento, arquitetura, operações e desenvolvimento |
| Resultado | Comparação de conformidade, duração, uso e falhas sem contaminar o teste |
| Custo | Comparação real chama as duas estratégias; desenvolvimento e teste têm consumo próprio |

## Conteúdo

- [Cenário](#cenário)
- [Objetivos](#objetivos)
- [Artefatos e disponibilidade](#artefatos-e-disponibilidade)
- [Tecnologias e conceitos](#tecnologias-e-conceitos)
- [Pré-requisitos](#pré-requisitos)
- [Etapa 1: separar desenvolvimento e teste](#etapa-1-separar-desenvolvimento-e-teste)
- [Etapa 2: congelar o regime](#etapa-2-congelar-o-regime)
- [Etapa 3: executar e interpretar](#etapa-3-executar-e-interpretar)
- [Como pedir uma mudança ao Copilot no VS Code](#como-pedir-uma-mudança-ao-copilot-no-vs-code)
- [Conferência do resultado](#conferência-do-resultado)
- [Solução de problemas](#solução-de-problemas)
- [Custos, pausa e limpeza](#custos-pausa-e-limpeza)
- [Situação da validação](#situação-da-validação)
- [Glossário e referências](#glossário-e-referências)

## Cenário

Beatriz Torres quer saber se a coordenação ajuda perguntas que precisam de mais de uma consulta.
Teresa Moura exige fontes verificáveis e a equipe de operações compara duração e consumo.
O piloto fictício não troca estratégia apenas porque o novo fluxo tem mais etapas.

## Objetivos

1. Separar conjunto de desenvolvimento e teste final.
2. Comparar as duas estratégias nas mesmas perguntas e configuração documentada.
3. Contar erros e descartes como falhas.
4. Interpretar custo e duração sem anunciar precisão estatística que a amostra não oferece.

## Artefatos e disponibilidade

| Artefato | Uso |
| --- | --- |
| [Contrato do chat](../../scripts/lab_chat.py) | Tipo, situação, texto e evidências |
| [Avaliador HTTP anterior](../../scripts/avaliar_chat.py) | Referência de transporte e proteção dos relatórios |
| [Registro L200](../../docs/validacao/l200-06-avaliar-chat.md) | Resultado histórico preservado, sem reaplicar seu conjunto final |
| [Roteiro L400](../../docs/roteiro-l400.md) | Condições da comparação nova |

O [avaliador L400](../../scripts/avaliar_l400.py) e o
[validador de operação](../../scripts/operar_l400.py) estão disponíveis.
O conjunto final novo foi criado depois de congelar o runtime e executado uma vez.
Ele é material de avaliação, não exemplo de implementação ou fonte recuperável;
não use suas perguntas para ajustar e repetir a mesma medição.

## Tecnologias e conceitos

**Conformidade** é atendimento ao contrato de resposta e às evidências esperadas no exercício.
O avaliador automatizado confere tipo, situação e invariantes da apresentação, mas não compara
a sustentação semântica da resposta com o gabarito de evidências.
A contagem aprovada não equivale a fidelidade semântica, decisão de cobertura ou aprovação regulatória.

**Latência** é a duração observada. **Percentil** resume uma posição da distribuição, mas uma
amostra pequena não estabelece um objetivo de nível de serviço.

Tokens informados pelo serviço ajudam a estimar consumo. A cobrança pode chegar depois da
execução e depende do regime do modelo; cota e custo são conceitos diferentes [1].
Uma estimativa com tarifas do operador não é uma fatura.

## Pré-requisitos

Conclua os testes de desenvolvimento e conserve código e configuração.
Prepare destinos HTTP, protocolo de comunicação, autenticados e explícitos.
Tokens de acesso entram somente em memória ou variáveis privadas, nunca em argumentos ou arquivo público.

O conjunto final novo fica fora do corpus, das imagens e dos prompts de implementação.
Os resultados L100/L200 permanecem intactos.
O teste final publicado já foi executado e não deve ser reenviado para conferir esta revisão.
Os comandos de execução abaixo documentam o procedimento; uma futura avaliação após mudanças
exige novo conjunto, congelamento e autorização. A análise das respostas existentes é uma
atividade separada, sem chamadas aos modelos.

## Etapa 1: separar desenvolvimento e teste

1. Use casos de desenvolvimento para depurar o fluxo.
2. Registre a candidata e suas condições de execução.
3. Prepare um conjunto final independente depois desse congelamento.
4. Confira fontes e expectativas antes de executar.

Uma pergunta sintética não é automaticamente um teste cego. Se seu resultado orientou o ajuste,
ela passou a fazer parte do desenvolvimento.

## Etapa 2: congelar o regime

Registre em local privado revisão e hash do código, hash do conjunto, ordem das chamadas,
índice, dimensões, deployments, modelos, limites, perfil e horário.

| Variável | Regra |
| --- | --- |
| Perguntas | As mesmas nas duas estratégias |
| Perfil | O mesmo, com autorização documental conservada |
| Fonte | Mesmo corpus e configuração durante a comparação principal |
| Chamadas | Uma resposta por estratégia e caso, sem escolher a melhor de várias |
| Falhas | Permanecem no denominador |
| Migração de dimensão | Comparação separada, sem atribuir todo efeito à coordenação |

Não misture a troca de índice e a troca de estratégia em um único resultado que pretenda
demonstrar o efeito isolado de cada uma.

O avaliador faz uma chamada por estratégia e caso, alternando qual delas vai primeiro.
Ele usa o JSON de `/api/perguntar`, não o fluxo de progresso. O plano é o padrão e não envia
perguntas. Os artefatos devem ser tags imutáveis ou digests de imagem conferidos pelo operador;
o avaliador não os consulta no Azure.

```powershell
.\.venv\Scripts\python.exe scripts\avaliar_l400.py --casos $conjuntoNovo --url-referencia $urlReferencia --url-coordenacao $urlCoordenacao --artefato-referencia $artefatoReferencia --artefato-coordenacao $artefatoCoordenacao --relatorio $relatorioNovo --plano
```

As duas URLs identificam o destino autorizado, HTTPS em Container Apps ou HTTP de loopback.
Tokens entram em `VARELEIRA_L400_TOKEN_REFERENCIA` e `VARELEIRA_L400_TOKEN_COORDENACAO`, somente
na sessão privada. O avaliador não segue redirecionamentos.

Registre `conjunto_sha256`, `plano_sha256` e `codigo_sha256` mostrados pelo plano antes de
enviar. Não troque esses valores para aceitar alterações posteriores.

## Etapa 3: executar e interpretar

1. Simule o plano, confira destino e orçamento.
2. Após autorização, execute a rodada congelada.
3. Guarde relatório sanitizado e configuração privada.
4. Compare conformidade, falhas, duração e uso.
5. Preserve resultados abaixo da meta sem retunar o mesmo teste.

Depois de conferir o plano e autorizar as chamadas, use os três hashes congelados:

```powershell
.\.venv\Scripts\python.exe scripts\avaliar_l400.py --casos $conjuntoNovo --url-referencia $urlReferencia --url-coordenacao $urlCoordenacao --artefato-referencia $artefatoReferencia --artefato-coordenacao $artefatoCoordenacao --relatorio $relatorioNovo --conjunto-esperado $hashConjunto --plano-esperado $hashPlano --codigo-esperado $hashCodigo --executar
.\.venv\Scripts\python.exe scripts\operar_l400.py --etapa validar-comparacao --comparacao $relatorioNovo --conjunto-esperado $hashConjunto --plano-avaliacao-esperado $hashPlano --codigo-esperado $hashCodigo
```

Esses comandos foram exercitados na rodada final com os hashes congelados e variáveis
do destino autorizado. Um relatório simulado não representa medição.
Tarifas por milhão de tokens e moeda são opções do operador; não há preço embutido no programa.
Informe as três tarifas ou nenhuma. A rodada conservou somente tokens, pois não conseguiu
qualificar a tarifa de embeddings; nenhum preço ausente foi tratado como zero.

| Observação | Interpretação |
| --- | --- |
| Mesmo resultado, maior uso | A complexidade não demonstrou benefício suficiente nesse regime |
| Melhor recuperação, pior resposta | Recuperação e geração exigem análise separada |
| 503 ou timeout | Falha do caso, não oportunidade de reduzir o denominador |
| Uso indisponível | Consumo desconhecido, não zero |
| Amostra pequena | Evidência do exercício, não garantia de produção |

## Como pedir uma mudança ao Copilot no VS Code

Use relatório sem perguntas finais, com o contrato e os testes de desenvolvimento:

```text
Confira denominadores, falhas, uso ausente e comparabilidade deste relatório.
Diferencie efeito da estratégia, efeito do índice e limitações da amostra.
Não abra o conjunto final, altere o runtime ou repita chamadas ao modelo.
Não transforme estimativa em custo faturado.
```

Um modelo pode apoiar a análise, mas não garante sozinho a fidelidade das evidências.

## Conferência do resultado

O relatório deve contar todos os casos, identificar o regime e manter erros explícitos.
Confira se a impressão digital do código corresponde à versão que respondeu.
Resultados de conjuntos diferentes não são comparação controlada.
O relatório sanitizado guarda tipo, situação e quantidade de citações, mas não o texto
da resposta nem das citações. Sem essas saídas originais, a revisão semântica integral
não é recuperável a partir das contagens; não complete a evidência gerando outra resposta.

## Solução de problemas

| Sintoma | Ação |
| --- | --- |
| Resultado melhora após repetição do teste | Preserve as rodadas e use novo conjunto após ajuste |
| Falhas desaparecem do total | Corrija denominador e classificação |
| Uso nulo é convertido para zero | Registre indisponibilidade sem inventar cobrança |
| Perfil recebe fonte indevida | Interrompa comparação e trate o defeito de acesso |

## Custos, pausa e limpeza

Planeje a quantidade de chamadas das duas estratégias antes de executar.
Não deixe aplicações e serviços ativos esperando dados de cobrança.
Conserve relatórios e retire temporários próprios após coletar as evidências.

## Situação da validação

O avaliador e o validador passaram nos testes locais. A rodada final teve 16/16 conformes na
referência e 16/16 na coordenação, com 32 HTTP 200 e zero descartes.
A mediana foi 2,69 segundos na referência e 4,88 na coordenação, que consumiu mais tokens
de geração. Não houve ganho de conformidade neste conjunto; conservar o fluxo convencional
como padrão é a decisão sustentada por essa medição.
O [registro L400](../../docs/validacao/l400-validacao.md) identifica o outlier de latência,
o regime congelado e o limite: contrato e apresentação, não fidelidade semântica ou produção.

## Glossário e referências

| Termo | Significado |
| --- | --- |
| Fixture | Dados preparados para um teste local |
| Denominador | Total de casos usado no cálculo |
| Latência | Duração observada da chamada |
| Percentil | Posição na distribuição de durações |
| Hash | Impressão digital de um arquivo |

1. [Cotas e consumo dos modelos](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/quota).
2. [Índices e reconstrução](https://learn.microsoft.com/en-us/azure/search/search-howto-reindex).
3. [FastAPI e formatos de resposta](https://fastapi.tiangolo.com/advanced/custom-response/).

Texto por GPT-6.1 Sol; código por Claude Sonnet 5.5. A análise não configura o modelo do aluno.

Revisão documental por gpt-6-astra (Astra), em 11 de outubro de 2026, sem nova execução Azure.
