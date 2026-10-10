# L200, Desafio 07: registro de validação

Registro do [guia de operação](../../desafios/L200/07-operar-recuperar-limpar.md).
Data de referência: 10 de outubro de 2026. Evidências com destinos e IDs permanecem privadas.

## Revisão e recuperação executadas

| Etapa | Resultado |
| --- | --- |
| Origem | Revisão pronta, ativa, com 100% do tráfego |
| Modo de revisões | Alterado para `multiple`, preservando tráfego na origem |
| Revisão de teste | Copiada da origem, com mesma imagem e sufixo exclusivo |
| Transferência | 100% do tráfego para a revisão de teste |
| Conferência da nova | Saúde 200, prontidão 200 e página anônima 401 |
| Retorno | 100% do tráfego para a origem, conferido no recurso |
| Conferência após retorno | Saúde 200, prontidão 200 e página anônima 401 |
| Revisão temporária | Desativada após conferir retorno |
| Autenticação | Permaneceu obrigatória durante todo o exercício |

A prática demonstrou mudança de configuração e tráfego com a mesma imagem.
Não injetou erro em código, não mediu tempo de recuperação de incidente e não restaurou dados.
O estado final de operação manteve modo `multiple`; a diferença para o Bicep `Single` foi documentada.

Uma implantação posterior da imagem integrada criou uma nova revisão pronta. Depois de conferir
imagem, rotas e revisão mais recente, o modo voltou a `Single` para o congelamento da avaliação.
Essa ação é separada do retorno à revisão anterior demonstrado acima.

## Logs e custos

Os registros do chat mostraram identificador, rota fechada, status, tempo e causa curta.
Descarte de política foi identificado como `resposta_descartada`, sem texto bruto ou credencial.

A consulta preliminar ao Cost Management, API `2025-03-01`, recebeu HTTP 200 e zero linhas
para o dia e grupo da execução. Não há total monetário confirmado. Atraso de cobrança e reutilização
do nome do grupo impedem tratar o retorno como isolamento do custo L200.

## Limpeza

O plano contempla retirada da credencial pelo identificador específico, registro e principal próprios,
aplicação e revisões, quatro objetos de busca L200, recursos da rodada e expurgo do recurso de modelos.
Os resultados de remoção e a comparação final com o inventário inicial serão acrescentados depois da
execução. Recursos Azure continuam ativos enquanto a avaliação final estiver em andamento.

## Limites

A recuperação não substituiu avaliações de qualidade e não refez o teste histórico L100.
Os comandos de exclusão interativa sem `--yes`, login humano e operações pelo portal não foram
exercitados. Novos destinos, modelos e redes privadas exigem sua própria validação.
