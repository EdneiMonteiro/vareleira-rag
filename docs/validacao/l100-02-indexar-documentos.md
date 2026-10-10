# L100, Desafio 02: registro de validação

Registro de trabalho da validação do [Desafio 02](../../desafios/L100/02-indexar-documentos.md): matriz de
testes, medições, correções e observações de operação. O guia do aluno traz a
[situação resumida](../../desafios/L100/02-indexar-documentos.md#situação-da-validação).

## Escopo e ambiente

| Item | Descrição |
| --- | --- |
| Data de referência | 9 de outubro de 2026 |
| Destino | Assinatura de teste, em grupos de recursos exclusivos criados para a validação e excluídos em seguida. Os identificadores do ambiente não são publicados. |
| Execução | Sequência executada com apoio do GitHub Copilot CLI na estação do mantenedor. |
| Versões | Windows, Python 3.12.10, Azure CLI 2.89.0, Bicep 0.48.1, `azure-search-documents` 12.0.0, `openai` 3.23.0 e as bibliotecas do Desafio 01. |
| Repetição dos comandos | Os 24 blocos de PowerShell do guia foram extraídos do próprio texto e executados linha a linha, com troca apenas dos marcadores de ID, em PowerShell 7.6, na região `brazilsouth`, sobre um grupo novo criado pelo Desafio 01. Os blocos somente de leitura, a reexecução do índice e as consultas foram repetidos no Windows PowerShell 5.1. Executados à parte: a camada gratuita, a busca em outra região e a retirada de papéis. |
| Aprovação do mantenedor | Confirmada em 9 de outubro de 2026 para o material existente; não representa nova execução dos testes. |

## Matriz de validação

| Verificação | Resultado |
| --- | --- |
| Testes automáticos (`python -m unittest discover -s tests`) | Passaram: 137 casos, sem acesso ao Azure; repetidos em ordem aleatória (três sementes), de outro diretório e com `-X dev -W error`. Quinze mutações manuais no código, feitas antes das últimas correções de mensagens, foram todas detectadas |
| Bicep | `az bicep lint`, `build` e `format` sem avisos nem diferenças, no arquivo principal, no módulo e nos dois arquivos de parâmetros. A primeira repetição do guia mostrou um aviso `BCP036` (a propriedade `hostingMode`) que havia passado despercebido, porque o lint sai com código 0 mesmo com avisos; a propriedade, desnecessária, foi retirada |
| Documentos | Nenhum link local ou âncora inválido, 56 URLs externas únicas respondendo no repositório, 20 referências todas citadas e 45 blocos de PowerShell dos dois guias sem erro de sintaxe nas duas versões do PowerShell |
| Desafio 01 depois das mudanças compartilhadas | Repetido em grupo novo: quatro criações, três documentos enviados e conferidos, reexecução com três `[igual]`, divergência provocada e restaurada |
| Região, modelo e cota | Em `brazilsouth`: `text-embedding-3-small` versão 1, só `GlobalStandard`, e `usado 0 de 1000` com a conta limpa. Em `eastus2`, o recurso de modelos foi aceito e o serviço de busca (`Free` e `basic`) foi recusado com `InsufficientResourcesAvailable`; com `localizacaoBusca=brazilsouth`, a busca ficou em `brazilsouth`, o restante em `eastus2`, e o pipeline passou |
| Previsão e implantação | Seis criações, dois `Modify` de ruído e dois sem mudança (`6 to create, 2 to modify, 2 no change`); implantação em 72 s (113 s em outra execução e 79 s na camada gratuita). Repetida sobre o ambiente pronto: `5 to modify, 5 no change`, sem criações |
| Infraestrutura criada | Três recursos; busca `basic` com uma réplica e uma partição; chaves de API desativadas na busca e nos modelos; deployment com modelo e versão fixos (`NoAutoUpgrade`), `GlobalStandard` e capacidade 30 |
| Papéis | Pelo Bicep (dois na busca e um nos modelos, tipo `User`) e pela concessão administrativa do guia, que valeu em menos de 1 minuto. Em outro teste, retirar `Search Index Data Contributor` bloqueou os documentos em cerca de 30 segundos, mesmo para um proprietário da assinatura; depois de recriar o papel dos modelos, o HTTP 401 alternou com respostas de sucesso por alguns minutos |
| Divisão local | 54 trechos com o tamanho padrão; 108, 67, 60 e 51 com 300, 600, 800 e 2500 caracteres |
| Simulação e indexação | A simulação previu 54 criações e cerca de 7.532 tokens, sem chamar o modelo; a execução criou o índice e 54 trechos, usou 7.134 tokens e levou de 19 a 24 s |
| Verificação | Cinco conferências aprovadas; as seis perguntas com o trecho esperado em primeiro lugar; pedidos sem credencial recusados com HTTP 401 na busca e nos modelos |
| Reexecução | Simulação e `--executar` com 54 `iguais`, `nada a fazer` e nenhuma chamada ao modelo, também no Windows PowerShell 5.1 |
| Divergência provocada | Com `--tamanho-maximo 800`: 6 a criar, 25 iguais e 29 divergentes; parada com código 3 e nada alterado, com ou sem `--executar`. Com `--substituir-divergentes`: 35 vetores e verificação reprovada (`60 no índice para 54 esperados`). A volta com `--remover-orfaos` recalculou 29, removeu 6 e a verificação passou. `--recriar-indice` também foi testado: apagou e recriou o índice |
| Consulta | Os três modos funcionaram. "O meu seguro cobre danos elétricos?": 0,766 (FAQ) e 0,731 (glossário). "Quanto custa o seguro por mês?": três trechos perto de 0,65. "Roubaram meu notebook...": a cláusula 5.1 na 8ª posição nos modos vetorial e híbrido, e fora dos dez primeiros no modo `texto` |
| Camada gratuita | Em teste à parte, `free` funcionou de ponta a ponta, só com papéis e índice vetorial |
| Pausar e retomar | A exclusão da busca, a do recurso de modelos e a purga levaram cerca de um minuto; só a conta de armazenamento ficou. Cerca de dois minutos depois, a implantação com o mesmo nome de busca falhou com `ServiceDeleting`; com `nomeBusca` novo, funcionou em 75 s; os papéis foram concedidos como administrador, o índice foi refeito a partir do Blob e a verificação passou |
| Erros traduzidos | Deployment inexistente, busca ou recurso de modelos inexistente, índice inexistente, documentos ausentes no Blob (código 3), argumento inválido (código 1) e falta do papel de dados da busca (HTTP 403): mensagens em pt-BR com o próximo passo, sem token e sem a mensagem bruta do serviço |
| Limpeza | Grupo excluído, `az group exists` respondeu `false`, recurso de modelos purgado e `list-deleted` vazio; os grupos preexistentes ficaram intactos |

## Correções feitas durante a validação

- O esquema do índice declara todos os atributos; o serviço ligava sozinho os omitidos.
- O divisor de frases não corta mais depois de "3.2.".
- A estimativa de tokens do visualizador conta o texto enviado ao modelo.
- O plano deixa de dizer que falta uma opção já informada.
- O módulo Bicep deixou de usar um valor que o tipo não aceita.

## Observações de operação

- **Capacidade.** Em 9 de outubro de 2026, o serviço de busca (`Free` e `basic`) em `eastus2` falhou com
  `InsufficientResourcesAvailable`; o recurso de modelos e o deployment nessa região foram criados. Em
  `brazilsouth`, o `text-embedding-3-small` versão 1 oferece só `GlobalStandard`; `eastus2` oferece também
  `Standard` e `DataZone`.
- **Cota.** O valor `usado N de 1000` conta todos os deployments do modelo na região, 30 por deployment.
- **Exclusão reversível.** O recurso de modelos excluído permanece 48 horas em exclusão reversível, e o mesmo
  nome falha com `FlagMustBeSetForRestore`. A purga funciona mesmo depois da exclusão do grupo.
- **`ServiceDeleting`.** Depois de excluir um grupo com um serviço de busca `Free`, o mesmo nome permaneceu
  bloqueado por 18 a 27 minutos.
- **Propagação de papéis.** Depois de recriar um papel, o endpoint dos modelos alternou entre HTTP 200 e
  HTTP 401 (`PermissionDenied`) por alguns minutos. A remoção de um papel propaga com atraso, e um resultado de
  sucesso logo após a remoção pode vir de cache. Nos documentos da busca, remover `Search Index Data Contributor`
  gerou HTTP 403 em cerca de 30 segundos, mesmo para um proprietário. A criação e a leitura do índice funcionaram
  como proprietário sem o `Search Service Contributor`, pelas ações `Microsoft.Search/searchServices/*`.
- **Endereços dos modelos.** Os hosts `*.openai.azure.com` e `*.cognitiveservices.azure.com` funcionam, com os
  escopos `cognitiveservices` e `ai.azure.com`. A resposta informa o modelo `text-embedding-3-small`.
- **Tokens.** A indexação consumiu 7.134 tokens para 22.594 caracteres (3,17 caracteres por token); a
  estimativa do script usa 3.
- **Pontuações.** Perguntas bem atendidas pontuaram de 0,69 a 0,77 no modo vetorial. "Quanto custa o seguro por
  mês?" pontuou perto de 0,65 e uma pergunta sem relação ("capital da França"), perto de 0,57.

## Alterações posteriores à validação

Registro de 9 de outubro de 2026, feito durante os Desafios 03 a 07. Os scripts do Desafio 02 mudaram em dois
pontos depois da validação descrita acima, e parte dos blocos do guia foi repetida no Azure para conferir que o
comportamento para o aluno continua o mesmo.

### Falha intermitente 404 nos *embeddings*

O endereço `/openai/v1/embeddings` do recurso de modelos respondeu HTTP 404 ("Subdomain does not map to a
resource") de forma intermitente, com o recurso, o deployment e o token corretos. A falha surgiu durante o
[Desafio 05](l100-05-agente-com-maf.md#observações-de-operação) e não ocorreu em nenhuma execução da validação
acima. A causa não foi identificada.

| Medição | Falhas |
| --- | --- |
| Antes da mudança: 12 pedidos HTTP diretos à rota v1 de embeddings | 6 de 12 |
| Antes da mudança: 26 execuções do script, cada uma em um processo novo | 14 de 26 |
| Antes da mudança: 20 chamadas em paralelo | 16 de 20 |
| Antes da mudança: 20 chamadas seguidas pelo mesmo cliente | 0 de 20 |
| Rota clássica de embeddings (`/openai/deployments/<nome>/embeddings`), 12 pedidos HTTP diretos | 0 de 12 |
| Rota `responses` do mesmo recurso, 12 pedidos HTTP diretos | 0 de 12 |
| Depois da mudança: 40 chamadas com o código novo | 0 de 40; 3 precisaram de uma repetição |

As falhas apareceram em processos novos e em chamadas em paralelo, e não em chamadas seguidas pelo mesmo cliente; a
rota de geração não foi afetada. Nenhum 404 apareceu nas cerca de 30 execuções de medição do Desafio 06.

**Mudanças no código** (`scripts/lab_indexacao.py`):

- O cliente de embeddings repete o 404 "Subdomain does not map to a resource", e só ele, até 6 vezes, com espera
  de 0,5 s multiplicada pelo número da tentativa, e mostra um `[AVISO]` a cada repetição. Os demais erros não são
  repetidos.
- O cliente envia `Connection: close`, de modo que cada pedido usa uma conexão nova. A escolha é empírica: ela
  acompanhou os 40 pedidos aprovados, sem provar a causa.
- O 404 que persiste depois das seis tentativas mostra uma mensagem própria, que manda conferir o nome do recurso e
  aguardar alguns minutos; o 404 de deployment inexistente mantém a mensagem anterior. O guia traz a linha
  correspondente em "Solução de problemas".
- As funções que criam clientes aceitam uma credencial opcional, usada no
  [Desafio 07](../../desafios/L100/07-identidade-da-aplicacao.md). Sem ela, o comportamento é o mesmo: identidade do
  Azure CLI.

### Conferência depois das mudanças

A suíte completa (330 casos, dos Desafios 01 a 07) passa com `-X dev -W error`, sem acesso ao Azure. Os blocos 1, 8,
12 a 15 e 19 a 21 do guia foram executados de novo, linha a linha, em PowerShell 7.6.6, sobre o grupo de recursos em
que os Desafios 03 a 07 foram validados (20 linhas, sem falhas):

- instalação das dependências, simulação e execução da indexação: 54 trechos `iguais` e "nada a fazer";
- verificação: cinco conferências aprovadas, as seis perguntas com o trecho esperado em primeiro lugar e pedidos sem
  credencial recusados com HTTP 401;
- consultas: 0,766 (FAQ) e 0,731 (glossário) para "O meu seguro cobre danos elétricos?", 11,049 no modo `texto` para
  "danos elétricos franquia" e três trechos perto de 0,65 para "Quanto custa o seguro por mês?", como na validação.

Os blocos 23 e 24 (limpeza completa) foram executados ao final, na limpeza do ambiente de teste (7 linhas, sem
falhas; ver "Limpeza" no [registro do Desafio 07](l100-07-identidade-da-aplicacao.md#limpeza)). Os demais blocos
(criação do ambiente, divergência provocada, camada gratuita, pausa e retomada) não foram repetidos depois das
mudanças. Nenhum 404 intermitente apareceu nesta repetição.

## Pendências

| Item | Situação | Ação para encerrar |
| --- | --- | --- |
| macOS, Linux e WSL | Pendente | Executar os comandos do guia nesses sistemas e registrar as diferenças de sintaxe |
| Python diferente do 3.12 | Pendente | Repetir as Etapas 3 a 5 com outra versão suportada |
| Instalação das dependências a partir do PyPI público | Pendente | A rede do teste usou um espelho, e as versões fixadas foram conferidas na API pública do PyPI; repetir `pip install -r requirements\l100.txt` em uma rede com acesso direto |
| Regiões além de `brazilsouth` e `eastus2` | Pendente | Validar cada região antes de recomendá-la |
| Outro modelo de embeddings ou outra quantidade de dimensões na nuvem | Pendente | Cobertos só por testes automáticos; repetir a Etapa 4 com `--dimensoes` e `--indice` |
| Assinaturas gratuitas ou estudantis e políticas restritivas | Pendente | Repetir a Etapa 2 nesses ambientes |
| Implantação e concessão de papéis com permissões menores que *Owner* | Pendente | A conta de teste era proprietária; repetir a Etapa 2 com *Contributor* e a concessão administrativa dos três papéis |
| Mensagens `InsufficientQuota`, `RequestDisallowedByPolicy` e `AuthorizationFailed` da tabela de problemas | Pendente | Provocar cada erro em ambiente de teste e confirmar a orientação da tabela |
| Limite de requisições (HTTP 429) | Pendente | Coberto só por testes automáticos; provocar o limite no Azure |
| Confirmação interativa de `az group delete` | Pendente | O teste usou `--yes`; executar o comando sem a opção |
| Windows PowerShell 5.1 na implantação e na limpeza | Pendente | Repetir as Etapas 2 e a limpeza no Windows PowerShell 5.1 |
| Prompts para o Copilot do guia, exemplo de pedido de mudança e modo construtor | Pendente | Executar no VS Code e registrar as respostas; o método de anexos, o modo **Agent** e as permissões foram conferidos no Desafio 01 |
| Medição de custo | Pendente | Consultar o Cost Management depois de uma execução completa |
| Aprovação do conteúdo dos documentos sintéticos | Confirmada | Mantenedor, em 9 de outubro de 2026; registro no inventário |
| Aprovação do texto, do código e dos resultados do guia | Confirmada | Mantenedor, em 9 de outubro de 2026; as revisões por IA continuam identificadas separadamente |

## Revisão editorial

### Revisão inicial — Claude Sonnet 5.5

Revisão de 9 de outubro de 2026, conforme o guia de estilo do mantenedor (documento externo ao repositório),
feita por Claude Sonnet 5.5 no GitHub Copilot CLI. Leitura integral do guia na versão revisada, correções por
categoria e nova conferência dos trechos alterados depois da leitura.

| Categoria | Alteração no guia |
| --- | --- |
| Estrutura e títulos | Títulos padronizados (Conteúdo, Cenário, Objetivos, Tecnologias e conceitos, Pré-requisitos, Conferência do resultado, Solução de problemas, Situação da validação, Glossário), sub-etapas numeradas (1.1 a 1.2, 2.1 a 2.5, 4.1 a 4.4 e 5.1 a 5.3) e âncoras atualizadas no guia e no README |
| Voz e tempo verbal | Referências a quem escreveu o guia retiradas; "O que o autor viu" passou a "Resultado observado na validação" |
| Construção afirmativa | Negativas dispensáveis e contrastes reescritos; negativas mantidas em proibições, riscos e condições de erro |
| Qualificadores e nomes informais | "próximo da estimativa", "maior custo esperado", "de 5 a 8 mil tokens", "rapidamente", "rápida", "quebrado", "rode", "sumir" e "à mão" substituídos por medida, mecanismo ou termo neutro |
| Siglas e termos | Siglas definidas no primeiro uso (API, SHA-256, HNSW, HTTP, SDK, RAG e outras); "implantação" (Bicep), "deployment" (instância de modelo) e "tipo de deployment" (`GlobalStandard`) separados no texto e no glossário; "grupo de testes" unificado como "grupo de recursos do laboratório" |
| Fontes e números | A razão de 3 caracteres por token deixou de ser atribuída à referência [4] e passou a constar como medição (22.594 caracteres e 7.134 tokens); referência então numerada como [21] acrescentada para a camada gratuita sem ranking semântico; "região" corrigida para "geografia" ao tratar dos dados em repouso do tipo `GlobalStandard`; custo declarado como não medido na validação |
| Coerência com o código | A afirmação de que a busca fica sempre na região do grupo passou a registrar o padrão e a exceção `localizacaoBusca`; a Etapa 5.1 informa que nenhum dos três resultados vem das Condições Gerais; a Atividade 2 usa `--k 10` |
| Separação de registros | Matriz de validação, correções e observações de operação movidas para este registro; o guia mantém só a situação da validação |
| Prompts | Uma linha do prompt "analisar uma recuperação" passou de "Leia o trecho do índice abaixo" para "Leia o resultado da busca abaixo", que descreve o que o aluno cola; o prompt reescrito não foi reexecutado no Copilot |

**Verificações finais.** Os blocos de código do guia (35) ficaram idênticos aos de antes da revisão, exceto a
linha do prompt citada acima. Os 24 blocos de PowerShell passaram na análise de sintaxe do PowerShell 7.6 e do
Windows PowerShell 5.1. Links locais, âncoras, URLs externas (todas com resposta HTTP 200) e referências
numeradas foram conferidos. Os 137 testes automáticos passaram. Nenhum comando foi executado no Azure nessa revisão.

### Revisão integral — GPT-6.1 Sol

Revisão de 9 de outubro de 2026 contra o guia de estilo do mantenedor, com leitura completa do guia e
deste registro. As correções distinguem instalação de bibliotecas de atualização do Python,
trechos por seção e tamanho de trechos necessariamente monotemáticos, e cobrança por hora da busca
de cobrança por tokens dos modelos. Referências foram renumeradas pela primeira citação.

A orientação do prompt de recuperação agora inclui as Condições Gerais entre os anexos.
A opção de filtro continua sendo um exercício de implementação, com instrução para manter todos
os argumentos do comando ao conferi-la. Os comandos PowerShell e as medições anteriores permanecem
preservados; esta revisão não executou atividades no Azure.

O guia foi relido após as correções e inspecionado na prévia Markdown local.
As [verificações integradas da revisão](l100-01-preparar-ambiente.md#revisão-editorial) incluem comparação
dos comandos e conferência de referências, tabelas, links e testes locais.

## Aprovação do material

O mantenedor confirmou a aprovação do material existente em 9 de outubro de 2026.
O inventário registra os três documentos como `aprovada`, sem alterar texto, hashes, metadados
dos blobs ou trechos. As medições permanecem históricas; o exemplo de simulação deixou de mostrar
o aviso de revisão pendente, conforme o estado atual do inventário.

## Autoria

Código, testes e texto produzidos com Claude Sonnet 5.5, no GitHub Copilot CLI. O Astra, modelo preferido do
mantenedor para a documentação, não estava disponível na sessão. O modelo de autoria é independente do modelo
que o aluno escolhe no Copilot e do modelo de embeddings da aplicação (`text-embedding-3-small`).
