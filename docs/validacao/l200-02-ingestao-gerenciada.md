# L200, Desafio 02: registro de validação

Registro do [guia de ingestão](../../desafios/L200/02-ingestao-gerenciada.md), executado em 10 de outubro
de 2026 no mesmo destino autorizado do Desafio 01. Identificadores privados não são publicados.

## Infraestrutura e papéis

| Verificação | Resultado |
| --- | --- |
| `what-if` da base L200 | Quatro recursos novos: ACR, ambiente Container Apps, identidade atribuída pelo usuário e Log Analytics |
| Busca existente | Reaplicada com identidade `SystemAssigned`, mantendo configuração L100 |
| Propriedades preenchidas pelo serviço | Diferenças apresentadas pelo ARM foram analisadas, não tratadas automaticamente como exclusões conhecidas |
| Atribuições `Unsupported` | Expressões, identidades, papéis e escopos conferidos antes; cinco atribuições reais conferidas após implantação |
| Tempo da base | Aproximadamente 223,9 s |
| Identidade da busca | `Storage Blob Data Reader` no contêiner; `Cognitive Services OpenAI User` nos modelos |
| Identidade do chat | `AcrPull` no ACR; `Search Index Data Reader` na busca; `Cognitive Services OpenAI User` nos modelos |

O Bicep não alterou a conta de armazenamento nem o recurso de modelos.
O novo serviço de logs foi preparado antes da aplicação; o custo desse acréscimo foi explicitado no guia.

## Pipeline executado

| Etapa de `scripts\gerenciar_ingestao.py` | Resultado |
| --- | --- |
| `criar`, sem `--executar` | Plano dos quatro objetos, sem gravação |
| `criar --executar` | Índice, fonte, skillset e indexador criados; indexador desabilitado |
| Política de exclusão | `NativeBlobSoftDeleteDeletionDetectionPolicy` presente desde a criação |
| Autenticação da fonte | `ResourceId` da conta, identidade gerenciada e nenhuma chave |
| `executar --executar --aguardar 300` | Habilitação iniciou a primeira rodada; nenhuma chamada redundante de execução |
| Primeira rodada | Três blobs, zero falhas, zero erros e zero avisos |
| `conferir` com origem completa | Quatro definições iguais às do script e campos esperados disponíveis |
| Conteúdo indexado | 21 trechos: 11 de Condições Gerais, 5 de FAQ e 5 de glossário |
| Metadados | Documento, título, conteúdo, fonte, versão, produto, hash declarado e marca sintética preenchidos |
| Campos ausentes | `secao` e `clausulas` vazios; Text Split não os produz |
| Índice L100 | Preservado com 54 trechos |

API REST do plano de dados: `2026-04-01`. Modelo: `text-embedding-3-small`, 1.536 dimensões.
Divisão: 1.200 caracteres e sobreposição de 100.

## Repetição e observações

A simulação posterior mostrou quatro objetos iguais mesmo depois de habilitar o indexador.
Uma nova execução após o exercício de exclusão terminou com um item processado, sem falhas ou avisos;
os três documentos e 21 trechos permaneceram conferidos. O contador não foi interpretado como
zero consumo de embeddings.

O estado geral `running` coexistiu com última execução `success`; a conferência usou o resultado,
itens, erros e avisos da última rodada. A exclusão e reposição ficam no
[registro do Desafio 03](l200-03-comparar-ingestao.md).

## Testes e limites

Os testes locais cobrem definições, ETags, propriedade dos objetos, erros, paginação e separação
entre simular e executar. A [suíte integrada](l200-01-reconstruir-base.md#verificações-locais-integradas)
foi executada pelo coordenador.

O gerenciador pede até mil trechos e para explicitamente se houver mil ou mais ou continuação.
Essa proteção limita a conferência ao laboratório; não representa paginação completa de produção.
O indexador lê o prefixo do contêiner, não o inventário como lista de permissão.

Os prompts novos do Copilot foram revisados documentalmente, mas não enviados interativamente no
VS Code. Isso não é apresentado como teste da seleção de modelos ou das permissões do editor.
