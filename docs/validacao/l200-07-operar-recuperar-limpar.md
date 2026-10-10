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

A consulta preliminar e a posterior à avaliação no Cost Management, API `2025-03-01`,
receberam HTTP 200 e zero linhas para o dia e grupo da execução. Não há total monetário confirmado.
Atraso de cobrança e reutilização
do nome do grupo impedem tratar o retorno como isolamento do custo L200.

## Limpeza

| Operação | Resultado conferido |
| --- | --- |
| Aplicação e revisões | Aplicação removida após encerrar a rodada final |
| Objetos da busca L200 | Indexador, skillset, fonte e índice removidos; simulação posterior confirmou ausência dos quatro |
| Referência L100 | 54 trechos, seis consultas de fumaça e acesso anônimo recusado conferidos antes da exclusão do grupo |
| Credencial de login | Identificador específico conferido, credencial removida e lista restante vazia |
| Registro e principal de login | Ambos próprios, removidos e ausência conferida por identificador da aplicação |
| Grupo exclusivo | Removido; ausência conferida após 1.641,5 s de execução. A conferência intermediária mostrou `Deleting` com somente o ambiente Container Apps ainda presente |
| Recurso de modelos | Expurgado pelo nome, grupo e região exatos; ausência na lista de excluídos conferida |
| Atribuições das identidades próprias | Nenhuma remanescente na consulta direta ao ARM |
| Recursos preexistentes | Sete grupos e oito papéis do operador iguais à linha de base; outros recursos excluídos preservados |

A remoção do grupo foi uma única operação. A espera pelo ambiente Container Apps não causou
novo pedido de exclusão. Não se deixou a aplicação atendendo enquanto os dados de custo eram processados.

O [resumo sanitizado da limpeza](l200-limpeza-final-sumario.json) registra a conferência final.
A listagem de atribuições usou o ARM, sem depender da resolução no Microsoft Graph de identidades
gerenciadas já removidas. Registro e principal de login foram conferidos separadamente no Entra ID.
Nenhum recurso desta rodada permaneceu ativo.

A [correção posterior](l200-correcao-v2.md#acesso-e-encerramento) teve uma rodada própria,
também removida e conferida. Seu resumo de limpeza preserva os mesmos sete grupos e oito papéis
preexistentes. As duas rodadas e suas medições permanecem separadas.

## Revisão editorial e documentação

Os sete guias foram lidos integralmente contra o guia de estilo do mantenedor: objetivo, cenários,
siglas, referentes, sequência operacional, custo, limites e fontes. A releitura corrigiu uma família
de comandos de conferência sem `--modelos`, sem mudar o código ou o conjunto final.

A prévia Markdown usou Markdig já disponível no PowerShell, sem instalar bibliotecas. Foram
conferidas 38 tabelas e 108 âncoras internas nos sete guias, sem colunas inconsistentes ou destinos
ausentes. A inspeção do conteúdo no navegador não encontrou caracteres de substituição nem
transbordamento horizontal da página; tabelas e código conservaram rolagem própria.

A conferência documental examinou 47 arquivos, links locais, referências e 105 URLs externas reais.
Sete URLs locais ou parametrizadas dos exemplos ficaram separadas da verificação pública.
Os 159 blocos PowerShell dos 14 guias passaram na análise de sintaxe, e os 108 L100 permaneceram
idênticos ao marco anterior. Servidor e aba da prévia foram encerrados, preservando a aba preexistente.

## Limites

A recuperação não substituiu avaliações de qualidade e não refez o teste histórico L100.
Os comandos de exclusão interativa sem `--yes`, login humano e operações pelo portal não foram
exercitados. Novos destinos, modelos e redes privadas exigem sua própria validação.
