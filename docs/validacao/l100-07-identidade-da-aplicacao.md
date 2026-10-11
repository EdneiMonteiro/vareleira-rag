# L100, Desafio 07: registro de validação

Registro de trabalho da validação do [Desafio 07](../../desafios/L100/07-identidade-da-aplicacao.md): o que foi
e o que não foi executado, a matriz de testes, as medições e as decisões de projeto. O guia do aluno traz a
[situação resumida](../../desafios/L100/07-identidade-da-aplicacao.md#situação-da-validação).
**A sequência principal foi concluída no Azure, em Windows e PowerShell**, incluindo identidade,
credencial, dois papéis, cinco operações, pergunta como aplicação e limpeza.
O histórico da primeira rodada, parcial, permanece abaixo; o
[complemento autorizado](#complemento-autorizado-execução-e-limpeza-da-aplicação) registra o fechamento.
As execuções Azure deste histórico usaram a versão com nome fixo; a
[correção posterior do verificador](#correção-posterior-do-verificador-11-de-outubro-de-2026)
foi conferida apenas localmente, sem nova execução Azure.

## Primeira rodada: antes da autorização

Esta rodada ocorreu antes da autorização para criar a identidade. As matrizes e a limpeza desta
seção descrevem somente essa primeira execução, não o estado atual do desafio.

### Escopo e ambiente

| Item | Descrição |
| --- | --- |
| Data de referência | 9 de outubro de 2026 |
| Destino | O mesmo grupo de recursos exclusivo da validação dos Desafios 01 a 06, excluído ao final. Os identificadores do ambiente não são publicados. |
| Execução | Sequência executada com apoio do GitHub Copilot CLI na estação do mantenedor. |
| Versões | Windows, Python 3.12.10, Azure CLI 2.89.0, Bicep CLI 0.48.1, `azure-keyvault-secrets` 4.11.3, `azure-identity` 1.26.0, `azure-core` 1.41.0 e as bibliotecas dos desafios anteriores. |
| Autorização para criar a identidade | A criação do registro de aplicação, do service principal e da credencial no tenant foi pedida ao mantenedor durante a sessão, com a descrição do que seria criado, do custo e da limpeza. Não houve resposta: o mantenedor não estava disponível. O projeto exige autorização explícita para criar identidades e credenciais, por isso **nada disso foi criado**. |
| Repetição dos comandos | Os blocos 1 a 10 do guia (24 linhas de comando) foram extraídos do próprio texto e executados linha a linha, com troca apenas do marcador de ID da assinatura, em PowerShell 7.6, em `brazilsouth`. As 24 linhas terminaram com o código esperado: 3 na linha do bloco 10 (o verificador com a conta do operador, que sai com 3 por desenho) e 0 nas demais. O bloco 18 (Etapa 8.2, excluir e expurgar o cofre) foi executado na limpeza final, com 3 linhas e código 0. Os blocos 11 a 17 (Etapas 5 a 8.1) não foram repetidos: dependem da identidade. |
| Aprovação do mantenedor | Ainda pendente nesta primeira rodada; confirmada posteriormente em 9 de outubro de 2026, conforme a seção de aprovação. |

### O que foi e o que não foi executado

| Etapa do guia | Situação | Evidência |
| --- | --- | --- |
| 1.1 Instalar a biblioteca | Executada | `pip check` sem conflitos; `azure-keyvault-secrets` 4.11.3 instalada junto de `azure-core` 1.41.0 |
| 1.2 Testes da identidade | Executada | `Ran 36 tests`, `OK` |
| 2 Cofre com Bicep | Executada | What-if antes da implantação: 2 recursos para criar (o cofre e o papel do operador), 6 para modificar (ruído) e 5 sem mudança. Implantação `Succeeded` em 78 s |
| 3 Segredo de teste | Executada | Gravado na primeira tentativa; ver a matriz |
| 4 Contraste com a conta do operador | Executada | Código de saída 3; 2 linhas `[OK]` e 3 `[FALHA]` por privilégio demais |
| 5 Criar a identidade da aplicação | **Não executada** | Sem autorização para criar identidade e credencial no tenant |
| 6 Conceder os dois papéis de leitura | **Não executada** | O módulo passa em `bicep lint` e `build-params`; as atribuições para o service principal não foram implantadas |
| 7 Verificar como aplicação e perguntar | **Não executada** | O formato das saídas vem dos testes automáticos |
| 8.1 Remover a aplicação | **Não executada** | A obtenção dos IDs do serviço de busca e do recurso de modelos (`az search service show` e `az cognitiveservices account show`) foi executada e devolveu os IDs; os papéis e a aplicação não existiam |
| 8.2 Excluir e expurgar o cofre | Executada | Bloco 18 do guia, literal, na limpeza final: ver a seção "Limpeza" |

### Matriz de validação

| Verificação | Resultado |
| --- | --- |
| Testes automáticos (`python -m unittest discover -s tests`) | Passaram, sem acessar o Azure, com `-X dev -W error`: 330 testes no total, com 36 casos novos em `test_identidade.py` e 2 em `test_repositorio.py` (Bicep do Desafio 07). Os 292 testes anteriores passam sem mudança de comportamento; só os dublês de `rodar_script` ganharam o parâmetro opcional `credencial` |
| Bicep | `az bicep lint` sem nenhuma linha de saída em `main.bicep`, `cofre.bicep` e `aplicacao.bicep`; `az bicep build-params` do `l100-desafio07.bicepparam` com código 0 |
| What-if, por propriedade | Os 6 itens `Modify` (recurso de modelos, deployments de embeddings e de geração, serviço de busca, `blobServices` e contêiner) só têm propriedades `Delete` que o serviço preenche (por exemplo, `deploymentState`, `endpoint`, `staticWebsite`); nenhuma é do template. Depois da implantação: "Resource changes: 6 to modify, 7 no change." Depois de a proteção contra expurgo ficar configurável, o cofre continuou `NoChange` |
| Papel do operador no cofre | Passou a valer na primeira tentativa de gravar, pouco depois da implantação |
| Guardar um segredo | Valor aleatório de 40 caracteres enviado por pipe a `guardar_segredo.py`, com validade de 3 dias. O valor não apareceu na saída. A versão, a validade (2026-10-12) e as etiquetas (`laboratorio` e `uso`) foram conferidas por `az keyvault secret show` com `--query` só de metadados |
| Ler de volta | O valor lido por `ler_segredo` era igual ao guardado (comparação feita sem imprimir). A validade registrada era de 3,0 dias, as etiquetas e o tipo de conteúdo (`text/plain`) estavam corretos |
| Erros reais traduzidos | Segredo inexistente: "O segredo '...' não existe no cofre '...'. Guarde-o com guardar_segredo.py ou confira o nome" (código 2). Cofre inexistente (nome válido, sem DNS): `ServiceRequestError` traduzido para "Não foi possível conectar ao cofre '...'" (código 2) |
| Tentativas de privilégio com a conta do operador | Ver a tabela abaixo |
| Segredo no histórico do terminal | O valor nunca foi um argumento de comando: o histórico mostra `$segredo \| python scripts\guardar_segredo.py ...`. A Atividade 2 (`Get-History`) é interativa e não foi repetida pelo roteiro |
| 403 do Key Vault, do Search e do Storage para uma identidade autenticada sem papel | **Não medido**: exige uma identidade sem papéis. Coberto por testes automáticos com respostas simuladas |
| Autenticação do service principal (`ClientSecretCredential`) e mensagens `AADSTS` | **Não medidas**. Os testes verificam a criação da credencial e a tradução dos códigos 7000215, 7000222, 700016 e 90002 |
| Suficiência dos dois papéis (`Search Index Data Reader` e `Cognitive Services OpenAI User`) para consultar o índice, gerar embeddings e gerar respostas | **Não medida** com a aplicação. Com a conta do operador, as duas primeiras operações passaram, mas ela tem papéis maiores |
| `perguntar.py --identidade aplicacao` | **Não executado** no Azure. Um teste automático confirma que a credencial chega ao índice, ao cliente de embeddings e ao de geração, e que sem a opção a saída não muda |

#### Tentativas de privilégio com a conta do operador

Execução real de `verificar_identidade.py --identidade operador`, na Etapa 4 e na repetição do guia, com a mesma saída. A conta do operador tinha os papéis dos Desafios 01 a 03 e o `Key Vault Secrets Officer` da Etapa 2.

| Tentativa | Esperado para a aplicação | Obtido com a conta do operador |
| --- | --- | --- |
| Consultar o índice (leitura) | Permitido | Permitido: `[OK]` |
| Gerar embeddings no recurso de modelos | Permitido | Permitido: `[OK]` |
| Alterar o serviço de busca (apagar um índice que não existe) | Negado | Permitido: `[FALHA]`, "PRIVILÉGIO DEMAIS" |
| Ler o segredo do cofre | Negado | Permitido: `[FALHA]`, "PRIVILÉGIO DEMAIS" |
| Listar os documentos da conta de armazenamento | Negado | Permitido: `[FALHA]`, "PRIVILÉGIO DEMAIS" |

Observação histórica (9 de outubro de 2026): na execução com o nome fixo
`vlr-verificacao-inexistente`, o alvo não existia e o serviço de busca **aceitou** a operação
(sem HTTP 404) para quem tinha permissão. O verificador já tratava os dois resultados (aceita ou
404 depois da autorização) como "permitido". A ausência do alvo naquela execução explica por que
nenhum índice foi alterado; não era uma garantia para repetir a versão antiga, que não verificava
a ausência antes da exclusão. Veja a
[correção posterior](#correção-posterior-do-verificador-11-de-outubro-de-2026).

### Decisões de projeto

- **Proteção contra expurgo.** A primeira versão do módulo do cofre deixava a proteção desligada, sem exceção declarada, o que contrariava a instrução do projeto de não desativar proteções como a do Key Vault. O módulo passou a ligá-la por padrão (`protecaoContraExpurgo = true`); só o arquivo `l100-desafio07.bicepparam` a desliga, de propósito, com o motivo em um comentário, no guia e na instrução de Bicep. O Azure não aceita o valor falso nessa propriedade, por isso o Bicep a omite (`null`). Dois testes automáticos conferem o padrão seguro e a exceção.
- **Papel do operador.** O operador recebe o `Key Vault Secrets Officer` (guardar e ler segredos) só no cofre. Para apenas executar a aplicação, `Key Vault Secrets User` bastaria; o laboratório não o atribui porque a mesma conta guarda o segredo.
- **Aplicação sem papel no cofre.** A aplicação não lê o cofre: quem lê o segredo é o operador, que o entrega à credencial em memória. O verificador tenta ler o segredo como aplicação e espera "negado".
- **Tentativas na execução histórica.** A tentativa de exclusão usou um índice de nome fixo que não existia naquela execução; as demais tentativas proibidas descartaram o resultado. Isso não garantia a ausência do alvo em outra execução da versão antiga. A mudança está na [correção posterior](#correção-posterior-do-verificador-11-de-outubro-de-2026).
- **Segredo.** Entra por entrada padrão ou variável de ambiente, nunca por argumento; nunca é impresso nem repetido em mensagens de erro (testes automáticos conferem a saída e as mensagens dos erros).
- **Escopo da opção `--identidade`.** Está em `perguntar.py` e em `verificar_identidade.py`. `agente_maf.py` e `avaliar_respostas.py` continuam usando a sessão do operador.

### Limpeza

A limpeza final foi feita depois das repetições dos blocos dos Desafios 02 a 04, na assinatura de teste, com os próprios blocos dos guias. Antes, conferências com o `az` (etiquetas do grupo, recursos e propriedades do cofre) confirmaram o alvo: o grupo tinha as etiquetas `laboratorio=vareleira-rag` e `nivel=L100` e quatro recursos (conta de armazenamento, serviço de busca, recurso de modelos e cofre), e o cofre estava com a proteção contra expurgo desligada, como no arquivo de parâmetros do laboratório.

| Passo | Resultado |
| --- | --- |
| Etapa 8.2 do Desafio 07 (bloco 18) | `az keyvault delete` em 6 s, com um aviso em inglês de que o nome do cofre só é reutilizável depois do expurgo; `az keyvault purge` em 16 s, sem saída; `az keyvault list-deleted` respondeu vazio. O texto do guia, que dizia que o `delete` não imprime nada, foi corrigido |
| Conferência do alvo da limpeza completa do Desafio 02 (bloco 23) | Etiquetas conferidas e três recursos restantes (o cofre já estava expurgado) |
| Limpeza completa do Desafio 02 (bloco 24, com `--yes` acrescentado pelo roteiro) | `az group delete` em 81 s; `az group exists` respondeu `false`; `list-deleted` listou o recurso de modelos; `az cognitiveservices account purge` em 38 s |
| Conferência final | Restaram só os sete grupos de recursos preexistentes; `az cognitiveservices account list-deleted` e `az keyvault list-deleted` vazios; nenhum recurso com a etiqueta do laboratório; nenhum registro de aplicação nem service principal com o nome usado no guia |

Nenhuma identidade, credencial ou papel de aplicação foi criado, então não havia o que remover no Microsoft Entra ID.

## Complemento autorizado: execução e limpeza da aplicação

Em 9 de outubro de 2026, após receber o relato das pendências, o mantenedor autorizou o
prosseguimento. A execução usou a assinatura de teste anteriormente indicada em local privado,
em `brazilsouth`, sem alterar o destino nem as políticas do tenant.
A aprovação do material não fez parte desta execução; foi confirmada posteriormente pelo mantenedor.

### Destino e preparação

O grupo do laboratório estava ausente. Antes de criar qualquer recurso, foram registrados os sete
grupos preexistentes, os oito papéis do operador e a ausência de uma aplicação com o nome do exercício.
O tenant ativo da Azure CLI foi comparado com o da assinatura de destino. Os comandos `az ad` usam
esse tenant ativo e não aceitam `--subscription`; as operações de recursos receberam a assinatura
explicitamente. Nenhuma configuração global da CLI foi trocada.

O registro da aplicação e o service principal foram criados antes de reconstruir a base, para
conferir a permissão no tenant sem iniciar o custo da busca. A credencial foi criada somente depois
do cofre. Essa ordem difere do roteiro didático; as operações das Etapas 5 a 7 foram executadas,
mas não houve repetição literal de todos os seus blocos.

O what-if da restauração mostrou 11 criações, todas no grupo exclusivo. O arquivo de parâmetros do
D03 restaurou armazenamento, busca e os dois deployments em 106,6 s. Os scripts existentes
simularam a carga, enviaram os três documentos sintéticos e conferiram seus hashes e metadados;
depois simularam a indexação, gravaram os 54 trechos e aprovaram `verificar_indice.py`.

O what-if do cofre mostrou 2 criações, 6 modificações e 5 itens sem mudança. As configurações
declaradas da base foram comparadas com a previsão anterior; a única normalização adicional,
`hostingMode: Default`, já estava no serviço de busca. As seis modificações continuaram sendo
propriedades preenchidas pelos serviços, ausentes do template. O cofre foi implantado em 75,5 s.

### Identidade, papéis e operações

O segredo de teste e a credencial foram enviados ao cofre por entrada padrão, sem valor em
argumentos, arquivo ou saída. Os metadados da credencial no Entra ID e a expiração de sete dias
do segredo no Key Vault foram conferidos separadamente.
O contexto privado contém identificadores e metadados, não o valor da credencial.

| Verificação | Resultado real |
| --- | --- |
| Dependências e testes da identidade | `pip check` sem conflitos; 36 testes de `test_identidade.py` aprovados com `-X dev -W error` |
| Contraste com o operador | Código 3 esperado: 2 operações necessárias permitidas e 3 operações excedentes permitidas |
| Aplicação antes dos papéis | Consulta, exclusão do índice inexistente, leitura do cofre e listagem de blobs recusadas com HTTP 403. Embeddings tiveram resultado inconclusivo de autenticação no verificador; não foi registrado como HTTP 403 |
| What-if da aplicação | Exatamente 2 novas atribuições, nos escopos da busca e dos modelos; configuração existente preservada |
| Papéis reais | `Search Index Data Reader` no serviço de busca e `Cognitive Services OpenAI User` no recurso de modelos; ambas as atribuições com `principalType: ServicePrincipal`, sem outras atribuições à aplicação na assinatura |
| Implantação dos papéis | `Succeeded`, em 76,2 s. A previsão omitiu `principalType`; o objeto foi conferido no Entra ID e o tipo foi verificado nas atribuições reais |
| Aplicação depois dos papéis | Código 0, 5 linhas `[OK]`: consulta e embeddings permitidos; exclusão de índice, leitura do segredo e listagem de blobs negadas com HTTP 403 |
| Pergunta como aplicação | Tipo documentada, resposta com a franquia de 10% e mínimo fictício de R$ 300,00; 2 citações literais conferidas, em `VLAR-FAQ-1_0-002` e `VLAR-FAQ-1_0-006` |
| Uso na pergunta do guia | Busca híbrida, 5 trechos, esforço `low`; 15 tokens de embeddings, 1.644 de entrada e 161 de saída na geração, dos quais 9 de raciocínio |
| Segredo inválido no Entra ID | Uma tentativa com valor sintético inválido foi recusada; `mensagem_do_entra` reconheceu `AADSTS7000215` sem mostrar o valor |
| Expiração no cofre | A expiração do segredo aleatório de teste foi colocada no passado; `ler_segredo` recusou a leitura com a orientação de segredo expirado. A credencial real da aplicação não foi alterada nesse teste |

A primeira conferência com os papéis encerrou 181 s depois do retorno da implantação, sem
repetição. Esse intervalo inclui a execução dos comandos e não mede o tempo exato de propagação.
O resultado inconclusivo dos embeddings antes dos papéis não foi diagnosticado isoladamente;
depois das duas atribuições, a mesma credencial usou embeddings e geração com sucesso.

A conferência cobre as cinco operações do verificador e a pergunta executada, não uma auditoria
de todas as permissões possíveis. Citações literais também não comprovam a fidelidade de cada frase.
Código Python, Bicep, dependências e conjuntos de avaliação foram preservados.
Nenhuma pergunta do conjunto de teste do D06 foi executada novamente.

### Limpeza e preservação

A limpeza removeu somente os objetos desta rodada, com seus identificadores privados conferidos.
A credencial foi excluída explicitamente antes da remoção da aplicação. As duas atribuições foram
removidas por seus IDs exatos, e a listagem da aplicação na assinatura retornou zero papéis.
O registro da aplicação e o service principal ficaram ausentes nas consultas ao tenant.

O cofre foi excluído e expurgado pela exceção de laboratório já documentada. Depois da conferência
das etiquetas e dos três recursos restantes, o grupo exclusivo foi excluído em 80,8 s.
O recurso de modelos foi expurgado usando seu nome, região e grupo originais; nenhum outro alvo
da exclusão reversível foi removido.

| Conferência final | Resultado |
| --- | --- |
| Credencial, papéis e identidade da aplicação | Credencial removida; zero atribuições; registro e service principal ausentes |
| Grupo do laboratório | Ausente |
| Cofre e recurso de modelos desta execução | Ausentes da exclusão reversível |
| Grupos preexistentes | Os mesmos sete da linha de base privada |
| Papéis preexistentes do operador | Os mesmos oito, sem diferença de nome, escopo ou condição |

Excluir identidades e papéis não promete revogar instantaneamente tokens já emitidos.
Os processos da aplicação terminaram; não houve login como service principal na Azure CLI nem
gravação de seu segredo em arquivo.

### Consulta de custo

A consulta ao Cost Management foi limitada ao grupo do laboratório e ao dia 9 de outubro de 2026.
A primeira tentativa recebeu HTTP 429; uma consulta posterior concluiu com HTTP 200 e retornou
um registro de armazenamento (`Storage`), em dólares dos Estados Unidos (USD).
Busca e modelos não apareceram nesse retorno, que também não
separa as duas rodadas realizadas com o mesmo grupo.

O valor retornado não é o custo completo do exercício nem comprova custo zero nos serviços
ausentes. A consolidação continua pendente. A
[orientação oficial sobre latência e limites](https://learn.microsoft.com/azure/cost-management-billing/costs/manage-automation#data-latency-and-rate-limits)
recomenda reduzir a frequência das consultas e respeitar a espera informada pelo serviço.
Todos os recursos desta rodada foram removidos antes dessa consulta; nenhum ficou ativo para
aguardar a consolidação.

### Verificações finais do complemento

A suíte local completa passou com 330 testes, com `-X dev -W error`, sem acessar o Azure.
Os 108 blocos PowerShell dos sete guias passaram na análise de sintaxe do PowerShell 7.6.6
e do Windows PowerShell 5.1.26100.9444. O verificador documental conferiu 32 arquivos,
561 links no texto e 82 URLs externas, sem falhas detectadas.
Esses resultados não representam execução nos outros sistemas operacionais nem aprovação humana.

## Pendências

| Item | Situação | Ação para encerrar |
| --- | --- | --- |
| Criar a identidade, a credencial, conceder os papéis e executar como aplicação | Concluído | Complemento autorizado acima; identidade e papéis removidos após a execução |
| Respostas HTTP 403 reais da aplicação (Search, Key Vault e Storage) | Concluído | Três recusas esperadas na Etapa 7 |
| Autenticação válida, segredo inválido e expiração no cofre | Concluído | Credencial válida usada; `AADSTS7000215` e recusa de segredo de teste expirado conferidos no Azure |
| Credencial expirada no Entra ID e demais códigos `AADSTS` | Pendente | `AADSTS7000222`, `700016` e `90002` continuam cobertos apenas pelos testes locais |
| Suficiência dos dois papéis para consultar, gerar embeddings e responder | Concluído | Cinco operações e pergunta com `perguntar.py --identidade aplicacao` aprovadas |
| Tempo exato de propagação dos papéis | Não isolado | A primeira conferência passou; o intervalo registrado inclui tempo de comandos e não estima a propagação |
| macOS, Linux e WSL | Pendente | Executar os comandos do guia nesses sistemas |
| Python diferente do 3.12 e Windows PowerShell 5.1 | Pendente | Repetir as Etapas 1 a 4; no Windows PowerShell 5.1, a análise de sintaxe dos blocos já passou na versão 5.1.26100, sem erros |
| Prompts para o Copilot do guia, exemplo de pedido de mudança e modo construtor | Pendente | Executar no VS Code e registrar as respostas |
| Custo completo e separado desta rodada | Parcial | Consulta executada, com retorno apenas de Storage; aguardar consolidação e distinguir o consumo das duas rodadas |
| Aprovação do conteúdo dos documentos sintéticos | Confirmada | Mantenedor, em 9 de outubro de 2026; registro no inventário |
| Aprovação do texto, do código e dos resultados do guia | Confirmada | Mantenedor, em 9 de outubro de 2026; as revisões por IA continuam identificadas separadamente |

## Revisão editorial

### Revisão inicial — Claude Sonnet 5.5

Revisão de 9 de outubro de 2026, feita por Claude Sonnet 5.5 no GitHub Copilot CLI, com verificação automatizada do texto do guia (termos informais, siglas sem definição no primeiro uso, ordem das referências, links e âncoras) e correções pontuais. Ao contrário da [revisão do Desafio 02](l100-02-indexar-documentos.md#revisão-editorial), não houve leitura integral do guia, categoria por categoria.

| Categoria | Alteração no guia |
| --- | --- |
| Siglas | SDK (*Software Development Kit*), CLI (*Command-Line Interface*) e HTTP definidas no primeiro uso |
| Termos informais | "rodou", "rodar" e "roda" substituídos por "funcionou", "funcionar" e "funciona"; "nosso assistente" por "o assistente deste laboratório"; "quebrado" por "inválido" |

### Revisão integral — GPT-6.1 Sol

Revisão de 9 de outubro de 2026 contra o guia de estilo do mantenedor, com leitura completa do guia e
deste registro, anterior ao complemento autorizado. O roteiro distingue implantação de recursos
de atribuição de papéis: `Contributor`
administra recursos, enquanto `User Access Administrator` administra acesso.
As funções foram conferidas na
[referência oficial dos papéis privilegiados](https://learn.microsoft.com/en-us/azure/role-based-access-control/built-in-roles/privileged).

O guia explica que o operador ainda lê o cofre e que a identidade gerenciada dispensa um segredo de
cliente, sem prometer ausência de riscos. A sequência da credencial descreve os quatro comandos;
as validades no Entra ID e no cofre são tratadas separadamente.
A conferência de privilégios foi limitada às cinco operações testadas.

Foram preservados os comandos, as medições e a pendência de autorização das Etapas 5 a 7 e 8.1.
Esta revisão não criou identidade, credencial ou recurso e não executou operações no Azure.

O guia foi relido após as correções e inspecionado na prévia Markdown local.
As [verificações integradas da revisão](l100-01-preparar-ambiente.md#revisão-editorial) incluem comparação
dos comandos e conferência de referências, tabelas, links e testes locais.

## Aprovação e encerramento

O mantenedor confirmou a aprovação do material existente em 9 de outubro de 2026.
Não ficou autorização humana em espera para encerrar o L100 no escopo Windows/Azure.
Outros ambientes, ampliações de amostra e erros ainda cobertos apenas localmente permanecem
identificados como limites de validação, não como execução já realizada.

A consulta atualizada de custo recebeu HTTP 429 com espera de oito segundos; após respeitá-la,
retornou HTTP 200, ainda com um registro de armazenamento em USD. O grupo continua ausente e
os sete grupos preexistentes permanecem iguais.
A [latência oficial dos dados de custo](https://learn.microsoft.com/azure/cost-management-billing/costs/understand-cost-mgt-data#cost-and-usage-data-updates-and-retention)
pode variar por serviço e assinatura; o fechamento de fatura é posterior ao uso.
Essa consolidação externa não exige recursos ativos nem impede o encerramento técnico do exercício.
O retorno parcial não foi tratado como custo completo ou custo zero dos demais serviços.

No fechamento após a aprovação, dois testes foram ajustados com Claude Sonnet 5.5:
o aviso de revisão usa um inventário de teste, e a gravação de segredo recebe uma data fixa no
dublê, sem depender da virada do dia em UTC (tempo universal coordenado).
As asserções de aviso, validade e ausência do valor do segredo foram preservadas.
A suíte completa passou com 330 testes; os documentos sintéticos conservaram seus hashes e tamanhos.
O verificador documental conferiu 32 arquivos, 562 links e 83 URLs externas, sem falhas detectadas.

## Autoria

Código, testes e texto produzidos com Claude Sonnet 5.5, no GitHub Copilot CLI. O Astra, modelo preferido do
mantenedor para a documentação, não estava disponível na sessão. O modelo de autoria é independente do modelo
que o aluno escolhe no Copilot e dos deployments da aplicação (`text-embedding-3-small` e `gpt-5.4-mini`).
O complemento operacional e a atualização deste registro foram coordenados por GPT-6.1 Sol.
Naquele fechamento de 9 de outubro de 2026, a lógica de produção permaneceu inalterada; os dois
ajustes de testes foram feitos com Claude Sonnet 5.5.

## Correção posterior do verificador (11 de outubro de 2026)

### Problema e mudança

A versão anterior de `verificar_identidade.py` enviava a tentativa de exclusão ao nome fixo
`vlr-verificacao-inexistente`, sem verificar a ausência. Se um índice com esse nome existisse e a
identidade tivesse permissão para excluí-lo, o pedido o apagaria. O guia compensava esse risco com
conferência manual de ausência e exclusividade do serviço. As tabelas e os resultados Azure acima
descrevem a execução histórica dessa versão e foram preservados.

A correção usa `vlr-verificacao-` seguido de 16 dígitos hexadecimais, gerados por
`secrets.token_hex(8)` (8 bytes, ou 64 bits, de aleatoriedade). Sorteia um nome novo a cada execução;
se coincidir com o índice informado em `--indice`, descarta o nome e sorteia de novo.
O alvo fixo foi retirado do código. A tentativa usa o nome aleatório de um índice que não existe,
sem criar esse índice nem alterar recursos existentes; continua sendo um pedido de escrita autenticado.

Para a tentativa de exclusão, a classificação não mudou: HTTP 403 indica recusa esperada;
operação aceita ou HTTP 404 depois da autorização indica "permitido", ou privilégio demais.
Na execução histórica, o serviço aceitou o pedido sem HTTP 404; isso não foi novamente observado
com o alvo aleatório.

### Mensagens e alcance

- O cabeçalho passa a ser `Verificação do privilégio mínimo, sem alterar recursos existentes · identidade: <descrição da identidade>`.
- A terceira tentativa passa a ser "Alterar o serviço de busca (apagar um índice de nome aleatório que não existe)".
- No código de saída 0, o fechamento informa que as duas operações necessárias funcionaram e as três proibidas foram recusadas, sem afirmar que a identidade não tenha outros acessos; orienta revisar também as atribuições de papel no Azure.
- No código de saída 3, o fechamento mantém "Privilégio divergente do esperado. Corrija os papéis e repita.", com o alcance limitado descrito abaixo.
- Nos códigos de saída 0 e 3, o fechamento delimita o resultado às cinco tentativas e explica que nenhum recurso existente foi alterado porque a exclusão usa o nome aleatório de um índice que não existe.
- O aviso intermediário de `--identidade operador` permanece inalterado.

Os exemplos do [guia](../../desafios/L100/07-identidade-da-aplicacao.md#etapa-4-ver-o-contraste-com-a-sua-conta)
usam as mensagens atuais como saída esperada, não como nova medição Azure.
Cinco tentativas não são uma auditoria de todos os acessos nem uma prova geral de privilégio mínimo.

### Verificação local e limite Azure

Foram aprovados **41 testes do módulo `test_identidade`**, com dublês e sem acessar o Azure.
Os testes novos de `VerificarIdentidadeTests` conferem:

- nome aleatório no formato válido e novo a cada chamada;
- alvo de exclusão diferente do índice informado;
- descarte de um nome sorteado igual ao índice informado;
- inexistência do nome fixo no código;
- alcance declarado das cinco tentativas, sem promessa de privilégio mínimo geral.

Na conferência documental desta atualização, os testes de `test_repositorio` e o controle de ausência
de perguntas de teste nos guias, registros e instruções passaram: **11 testes aprovados**.
Também foram conferidos 61 links e âncoras locais dos dois documentos e os exemplos de saída
contra dublês; `git diff --check` não apontou problemas.

**Não houve nova execução no Azure:** o mantenedor não autorizou novas operações nesta rodada.
A tentativa de exclusão com nome aleatório não foi reconferida no serviço, nem com o operador nem
com a aplicação. Os resultados reais de permissão, recusa e limpeza permanecem os históricos,
obtidos com o nome fixo; os dublês não substituem essa medição.

Correção do verificador e testes: Claude Sonnet 5.5, em 11 de outubro de 2026.
Texto desta atualização: GPT-6.1 Sol, por escolha explícita do mantenedor, com Astra indisponível.
