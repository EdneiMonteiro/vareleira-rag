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

A rodada HTTP final ainda não foi executada neste registro. O código, a imagem e o conjunto serão
conferidos antes do envio; resultado, erros e casos não avaliados serão acrescentados sem reescrever
o conjunto congelado.

## Separação das medições

| Medição já existente | Escopo |
| --- | --- |
| L200, seis consultas de fumaça | Recuperação conhecida em dois índices e três modos; 6 de 6, sem geração |
| Política L100 local, 24 casos | Pós-processamento determinístico, sem modelos Azure; conflito de rótulos preservado |
| Política L100 Azure, 24 perguntas | Índice L100; 22 de 23 comparáveis conformes, uma divergência |
| Chat L200, demonstração local | Apresentação, transporte e isolamento; sem Azure |
| Chat L200, consultas reais de fumaça | Tokens e identidade; sucessos e descartes preservados |
| Chat L200, conjunto final de 18 | Medição HTTP própria, a registrar após execução |

O teste histórico L100 D06 não foi repetido e continua abaixo da meta registrada.
Prompts novos do Copilot, login humano e revisão semântica integral não foram executados nesta rodada.
