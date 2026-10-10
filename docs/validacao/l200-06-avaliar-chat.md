# L200, Desafio 06: registro de avaliação

Registro do [guia de avaliação](../../desafios/L200/06-avaliar-chat.md).
As perguntas finais permanecem somente no conjunto próprio, fora dos guias e do conteúdo recuperável.

## Conjunto e congelamento

| Item | Registro |
| --- | --- |
| Conjunto | `dados\l200\avaliacao\chat-teste-v1.json` |
| Quantidade | 18: seis documentados, seis individuais, dois ambíguos, dois sem evidência e dois fora de escopo |
| Autoria | Contexto separado que leu somente os três documentos sintéticos; contrato fornecido antes da escrita |
| Acesso do autor | Sem código, testes, conjuntos anteriores, resultados ou Azure |
| Citações de referência | 35 de 35 literais nos documentos indicados; são diagnóstico de referência, não entradas injetadas no modelo |
| Hash UTF-8/LF | `94c1f0ed73e38076a0b268b44a3110bd4a4c8ec18c94bfc587bd0ef91c86be01` |
| Metadados posteriores | Somente identificação sintética foi ajustada antes do congelamento; casos, rótulos e citações permaneceram iguais |
| Configuração no conjunto | Metadado “a congelar antes da execução” preservado; configuração efetiva registrada separadamente |

O autor do conjunto não recebeu os resultados de execução. O avaliador foi escrito separadamente,
sem ler as perguntas finais. A independência é de contexto de trabalho, não avaliação humana certificada.

## Critérios e limites definidos antes da medição

Uma resposta por caso; índice L200, híbrida, `k=3`, `low`, embeddings de 1.536 dimensões,
deployment de geração reaproveitado do L100, autenticação da borda obrigatória.
Tipos e situações são comparados literalmente. HTTP 503, transporte e resposta inválida contam como
falha; o texto individual precisa ser o fixo da política, com aviso e evidências.

O avaliador não mede fidelidade semântica, não vê tentativas internas dos serviços e soma apenas
tokens informados. Não será ajustado por divergências encontradas no conjunto final.

## Resultado da rodada

**Rodada reprovada quanto ao contrato completo:** 11 de 18 casos conformes, em uma execução única
de 10 de outubro de 2026. O avaliador retornou código 3. Houve duas divergências de classificação
e cinco HTTP 503 por resposta não verificada; nenhuma falha de transporte, formato ou caso não avaliado.

| Tipo esperado | Casos | Conformes | Divergências | HTTP 503 |
| --- | --- | --- | --- | --- |
| Documentada | 6 | 4 | 1 | 1 |
| Contratação individual | 6 | 2 | 0 | 4 |
| Ambígua | 2 | 1 | 1 | 0 |
| Sem evidência | 2 | 2 | 0 | 0 |
| Fora de escopo | 2 | 2 | 0 | 0 |
| Total | 18 | 11 | 2 | 5 |

| Identificadores | Resultado |
| --- | --- |
| L200-05 | Esperado `ambigua`/`esclarecimento`; observado `sem_evidencia`/`recusada` |
| L200-07 | Esperado `documentada`/`respondida`; observado `sem_evidencia`/`recusada` |
| L200-02, L200-04, L200-09, L200-12 e L200-18 | HTTP 503, `resposta_nao_verificada`; a resposta descartada não foi apresentada |

As duas respostas individuais conformes mantiveram texto fixo, aviso e evidências.
Os quatro descartes individuais foram contados como falhas de atendimento, sem tratá-los como acertos
pela proteção da política. A geração/classificação continua impedindo homologar o conjunto completo.

## Código, imagem e consumo observado

| Item | Registro |
| --- | --- |
| Código congelado | Commit `e57c5959cc8608309ccde8e8d4c9f33749f980b4`, conferido antes do envio |
| Imagem | Build ACR `cq3`, `Succeeded`, com a correção dos identificadores longos |
| Digest da imagem | `sha256:826c13b030f0d33ec8ceb94f42d7c78d9269aded41aefa3a41f994731e4598cc` |
| Configuração | Índice L200, híbrida, `k=3`, `low`, 1.536 dimensões, modo `Single`, autenticação obrigatória |
| Modelos conferidos no recurso | `text-embedding-3-small`, versão `1`; `gpt-5.4-mini`, versão `2026-03-17`, GlobalStandard |
| Identidade | Token real de aplicação temporária; não login humano |
| Pedidos HTTP ao chat | 18, uma pergunta por caso; 13 respostas 200 e cinco respostas 503 |
| Tempo total | 69,828 s; 69,078 s nas chamadas |
| Uso informado | 13 de 18 respostas; 415 tokens de embeddings, 26.051 de entrada e 3.457 de saída |
| Raciocínio | 976 tokens já incluídos nos 3.457 de saída |
| Uso não informado | Cinco erros; o consumo é desconhecido, não zero, e a soma acima é parcial |

O [relatório sanitizado](l200-chat-avaliacao-final-v1.json) foi copiado sem alterações, com SHA-256
`b80294fc4dbc680b407f7bc9028dc677e86e192f0c7385c1415145811c151865`.
O [congelamento efetivo](l200-congelamento-final.json) registra commit, imagem e parâmetros,
separadamente do metadado histórico do conjunto.

O conjunto, seus rótulos e o código de produção não foram alterados após observar os resultados.
Não houve repetição de caso nem ajuste de política para eliminar os descartes. Corrigir qualidade
exige casos de desenvolvimento próprios, hipótese explícita e um conjunto final novo.
A publicação é experimental, não homologação do atendimento.

## Separação das medições

| Medição já existente | Escopo |
| --- | --- |
| L200, seis consultas de fumaça | Recuperação conhecida em dois índices e três modos; 6 de 6, sem geração |
| Política L100 local, 24 casos | Pós-processamento determinístico, sem modelos Azure; conflito de rótulos preservado |
| Política L100 Azure, 24 perguntas | Índice L100; 22 de 23 comparáveis conformes, uma divergência |
| Chat L200, demonstração local | Apresentação, transporte e isolamento; sem Azure |
| Chat L200, consultas reais de fumaça | Tokens e identidade; sucessos e descartes preservados |
| Chat L200, conjunto final de 18 | 11 de 18 conformes; duas divergências e cinco descartes HTTP 503, registrados sem repetição |

O teste histórico L100 D06 não foi repetido e continua abaixo da meta registrada.
Prompts novos do Copilot, login humano e revisão semântica integral não foram executados nesta rodada.
