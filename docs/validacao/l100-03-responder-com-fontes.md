# L100, Desafio 03: registro de validação

Registro de trabalho da validação do [Desafio 03](../../desafios/L100/03-responder-com-fontes.md): matriz de
testes, medições, correções e observações de operação. O guia do aluno traz a
[situação resumida](../../desafios/L100/03-responder-com-fontes.md#situação-da-validação).

## Escopo e ambiente

| Item | Descrição |
| --- | --- |
| Data de referência | 9 de outubro de 2026 |
| Destino | Assinatura de teste, em grupo de recursos exclusivo criado para a validação e excluído em seguida. Os identificadores do ambiente não são publicados. |
| Execução | Sequência executada com apoio do GitHub Copilot CLI na estação do mantenedor. |
| Versões | Windows, Python 3.12.10, Azure CLI 2.89.0, Bicep 0.48.1, `openai` 3.23.0, `azure-search-documents` 12.0.0 e as bibliotecas dos Desafios 01 e 02. |
| Repetição dos comandos | Os 14 blocos de PowerShell do guia foram extraídos do próprio texto e executados linha a linha, com troca apenas do marcador de ID da assinatura, em PowerShell 7.6, em `brazilsouth`, sobre um grupo novo com os Desafios 01 e 02 implantados pelos próprios arquivos de parâmetros. O deployment de geração foi removido (bloco 14) antes da repetição, para reproduzir o estado de quem começa o desafio. |
| Aprovação do mantenedor | Confirmada em 9 de outubro de 2026 para o material existente; não representa nova execução dos testes. |

## Matriz de validação

| Verificação | Resultado |
| --- | --- |
| Testes automáticos (`python -m unittest discover -s tests`) | Passaram, sem acesso ao Azure, com `-X dev -W error`; 32 casos novos de geração e de `perguntar.py`, mais 2 de repositório |
| Bicep | `az bicep lint` e `build` sem avisos no arquivo principal, no módulo novo e nos três arquivos de parâmetros |
| Região, modelo e cota | Em `brazilsouth`: `gpt-5.4-mini` versão `2026-03-17`, ciclo de vida `GenerallyAvailable`, SKUs `GlobalStandard`, `GlobalProvisionedManaged` e `GlobalBatch`. Cota: limite 1000, com 500 em uso por outros deployments da assinatura de teste, o que deixou 500 livres |
| Previsão e implantação | Uma criação (`deployments/geracao`), cinco `Modify` de ruído e cinco sem mudança (`1 to create, 5 to modify, 5 no change`); implantação em 72 a 75 s |
| Deployment criado | `gpt-5.4-mini`, `2026-03-17`, `GlobalStandard`, capacidade 50, `NoAutoUpgrade`; o papel `Cognitive Services OpenAI User` atribuído no Desafio 02 bastou para a API Responses |
| Pedido sem geração | `--sem-geracao` mostrou as instruções, três blocos `<trecho>` e a pergunta no fim, sem chamar o modelo; consumo de 8 a 11 tokens de embeddings |
| Primeira pergunta | "O meu seguro cobre danos elétricos?": 5 trechos, resposta correta com duas fontes (FAQ e Condições Gerais, cláusula 3), 1.456 tokens de entrada e de 126 a 186 de saída; de 11 a 15 s |
| Modos de busca | "franquia danos elétricos" respondeu "10% do prejuízo, com mínimo de R$ 300,00" nos modos `texto` e `vetorial`; pontuações de 8,9 a 11,0 (`texto`) e de 0,64 a 0,66 (`vetorial`) |
| Recuperação incompleta | "Roubaram meu notebook na rua. O seguro paga?": com `--k 5`, a cláusula 5.1 não chegou ao modelo, e a resposta disse que não há informação sobre o roubo de um notebook na rua; com `--k 10`, o trecho `VLAR-CG-1_0-007` chegou (7ª posição) e a resposta informou a exclusão de bens portáteis levados para fora do imóvel |
| Esforço de raciocínio | Para a mesma pergunta com 10 trechos (2.233 tokens de entrada): `none` com 50 a 53 tokens de saída e nenhum de raciocínio; `low` com 158 a 186 (60 a 90 de raciocínio); `medium` com 262 a 361 (165 a 264); `high` com 348 a 382 (256 a 289). O tempo total ficou entre 11,7 e 15 s em todos |
| Pergunta sem resposta | "Quanto custa o seguro por mês?" e "Qual é a capital da França?": o modelo disse que os trechos não informam e não citou fontes; o script mostrou o aviso de resposta sem fonte |
| Erros traduzidos | Deployment de geração inexistente (HTTP 404) e recurso de modelos inexistente (falha de conexão, após as tentativas automáticas): mensagens em pt-BR com o próximo passo, código 2, sem token e sem a mensagem bruta. Fonte desconhecida, resposta incompleta, recusa do modelo, filtro de conteúdo, 401, 403, 429 e formato inesperado: cobertos só por testes automáticos |
| Remoção do deployment | O bloco 14 removeu só o deployment de geração; o índice e o deployment de embeddings permaneceram |

## Correções feitas durante a validação

- O texto de acompanhamento passou a citar o deployment, e não o modelo: a resposta do serviço devolve o nome do deployment no campo `model`.
- O cliente de geração trata a recusa do modelo (conteúdo `refusal`) com mensagem própria.
- `--detalhes` passou a mostrar o erro original de qualquer erro já traduzido, em `lab_comum.executar_com_tratamento`.

## Observações de operação

- **Estado do catálogo.** Em 9 de outubro de 2026, o catálogo de `brazilsouth` listava para `GlobalStandard`, entre outros, `gpt-5.4-mini` (aposentadoria em 21 de setembro de 2027, segundo o cronograma oficial), os modelos `gpt-5.6` e `gpt-6`, que exigem solicitação de cota em algumas camadas, e os `gpt-4.1` e `gpt-4o`, em ciclo de vida `Legacy` ou `Deprecating`.
- **Temperatura.** Os modelos de raciocínio não aceitam `temperature`; o script não a envia, e o texto das respostas varia a cada execução.
- **Tempo.** O tempo total de uma pergunta (11 a 15 s) é dominado por autenticação, busca e rede; mudar o esforço quase não o alterou.
- **Armazenamento da resposta.** O script envia `store=False`; sem ele, o serviço guarda a resposta por 30 dias por padrão.
- **Exclusão do deployment de geração.** Depois de `az cognitiveservices account deployment delete` (concluído em 4 s, com a listagem de deployments do recurso já mostrando só o `embeddings`), o `geracao` continuou respondendo a chamadas da API Responses por mais de 16 minutos. Uma sonda com uma chamada mínima a cada 2 minutos obteve resposta até 16 min 46 s depois da exclusão e o HTTP 404 "Could not find an existing deployment to match the model in the request" a partir de 18 min 48 s, nas duas sondas seguintes. A hora da exclusão veio do registro de atividade do grupo de recursos. A causa não foi investigada.

## Alterações posteriores à validação

Registro de 9 de outubro de 2026, feito durante os Desafios 04 a 07.

- **Mensagem do 404 intermitente.** O cliente de geração mostra uma mensagem própria para o 404 "Subdomain does not map to a resource", a mesma dos *embeddings*, descrita no [registro do Desafio 02](l100-02-indexar-documentos.md#alterações-posteriores-à-validação). O guia ganhou a linha correspondente em "Solução de problemas". A rota de geração não apresentou o erro nas medições.
- **Credencial opcional.** O cliente de geração e o `perguntar.py` aceitam uma identidade de aplicação, usada no [Desafio 07](../../desafios/L100/07-identidade-da-aplicacao.md). Sem as novas opções, o comportamento é o mesmo.

**Conferência.** Os blocos 1 a 14 do guia foram executados de novo, linha a linha, em PowerShell 7.6.6, sobre o grupo de recursos em que os Desafios 03 a 07 foram validados (26 linhas, sem falhas). Como o deployment de geração já existia, o what-if mostrou `6 to modify, 5 no change, 1 to ignore`, sem criações; o Key Vault do Desafio 07 aparece como `Ignore`, porque o arquivo de parâmetros do Desafio 03 não o declara. O bloco 14 removeu o deployment de geração.

## Pendências

| Item | Situação | Ação para encerrar |
| --- | --- | --- |
| macOS, Linux e WSL | Pendente | Executar os comandos do guia nesses sistemas e registrar as diferenças de sintaxe |
| Python diferente do 3.12 | Pendente | Repetir as Etapas 1, 3 e 4 com outra versão suportada |
| Windows PowerShell 5.1 | Pendente | A análise de sintaxe passou na versão 5.1.26100; falta executar os comandos nesse ambiente |
| Outras regiões, outras cotas e outros modelos de geração | Pendente | Só o `gpt-5.4-mini` em `brazilsouth` foi validado |
| 401, 403, 429, filtro de conteúdo, resposta incompleta e formato inesperado | Pendente | Cobertos só por testes automáticos; provocar cada caso em ambiente de teste |
| Prompts para o Copilot do guia, exemplo de pedido de mudança e modo construtor | Pendente | Executar no VS Code e registrar as respostas |
| Medição de custo | Pendente | Consultar o Cost Management depois de uma execução completa |
| Aprovação do conteúdo dos documentos sintéticos | Confirmada | Mantenedor, em 9 de outubro de 2026; registro no inventário |
| Aprovação do texto, do código e dos resultados do guia | Confirmada | Mantenedor, em 9 de outubro de 2026; as revisões por IA continuam identificadas separadamente |

## Revisão editorial

### Revisão inicial — Claude Sonnet 5.5

Revisão de 9 de outubro de 2026, feita por Claude Sonnet 5.5 no GitHub Copilot CLI, com verificação automatizada do texto do guia (termos informais, siglas sem definição no primeiro uso, ordem das referências, links e âncoras) e correções pontuais. Ao contrário da [revisão do Desafio 02](l100-02-indexar-documentos.md#revisão-editorial), não houve leitura integral do guia, categoria por categoria.

| Categoria | Alteração no guia |
| --- | --- |
| Referências | Numeradas pela ordem da primeira citação no texto: a referência de Prompt Shields passou de 16 para 6, e as demais se deslocaram |
| Siglas | CLI definida no primeiro uso |
| Termos informais | "quebrado" substituído por "inválido" na situação da validação |
| Próximos desafios | "Planejados, ainda sem desafio escrito" deu lugar a links para os Desafios 04 a 07 |

### Revisão integral — GPT-6.1 Sol

Revisão de 9 de outubro de 2026 contra o guia de estilo do mantenedor, com leitura completa do guia e
deste registro. A conferência automática passou a ser descrita pelo que verifica: identificadores
de fontes recuperadas. A correspondência entre resposta e fonte permanece uma tarefa de revisão.
Exemplos gerados foram identificados como saídas registradas, sujeitas à variação.

Foram corrigidas as afirmações de que a versão fixa estabilizaria o texto e de que nenhum papel seria
reaplicado: o módulo de indexação declara as atribuições quando recebe `principalIdCarga`.
O guia distingue permissão para implantar de permissão para atribuir papéis.
Essa condição foi conferida no Bicep e na documentação de papéis; o cenário com permissões menores
continua pendente de execução. Código, comandos e medições foram preservados.

O guia foi relido após as correções e inspecionado na prévia Markdown local.
As [verificações integradas da revisão](l100-01-preparar-ambiente.md#revisão-editorial) incluem comparação
dos comandos e conferência de referências, tabelas, links e testes locais.

## Aprovação do material

O mantenedor confirmou a aprovação do material existente em 9 de outubro de 2026.
Essa confirmação não é uma nova medição: implementação, documentos e resultados anteriores
foram preservados, com suas limitações e distinções entre citação e fidelidade.

## Autoria

Código, testes e texto produzidos com Claude Sonnet 5.5, no GitHub Copilot CLI. O Astra, modelo preferido do
mantenedor para a documentação, não estava disponível na sessão. O modelo de autoria é independente do modelo
que o aluno escolhe no Copilot e dos deployments da aplicação (`text-embedding-3-small` e `gpt-5.4-mini`).
