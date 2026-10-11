# L300: execução Azure, controles de acesso e limpeza

| Campo | Situação |
| --- | --- |
| Data de referência | 10 e 11 de outubro de 2026; operações registradas em horário UTC |
| Escopo | Validação temporária no grupo exclusivo e na assinatura de testes confirmados pelo mantenedor |
| Região | `brazilsouth` |
| Autorização | Executar os laboratórios, realizar os testes necessários e remover e expurgar os recursos próprios ao terminar |
| Orçamento | Teto total de US$90; consulta de cobrança ainda sem linhas, não interpretada como custo zero |
| Situação | Validação temporária concluída; testes, recuperação, remoção e expurgos conferidos |
| Publicação | Sem push, release, execução Actions ou ativação de confiança federada nesta rodada |

## Continuidade e fontes

A [validação local](l300-validacao-local.md) permanece como registro do fechamento anterior.
O mantenedor posteriormente aprovou o roteiro sintético, confirmou assinatura, região e orçamento
e autorizou a execução e a limpeza da rodada Azure. Essas confirmações não alteram as medições
históricas L100/L200.

A carga usa os três documentos L100 e o roteiro operacional L300 aprovado. Nenhum documento real,
conjunto final de avaliação ou resposta esperada foi enviado ao armazenamento ou ao contexto
de construção das imagens. A aplicação conserva os deployments `embeddings` e `geracao`,
com `text-embedding-3-small` versão `1`, 1.536 dimensões, e `gpt-5.4-mini` versão `2026-03-17`.
Os dois usam `GlobalStandard`, por consumo, sem capacidade de modelos provisionados.

O grupo é exclusivo da rodada. A linha de base inicial contém nove grupos, incluindo o grupo
L300 criado anteriormente, e oito papéis do operador. Identificadores, inventários completos,
saídas ARM e configurações do ambiente são conservados somente no registro privado da sessão.

## Infraestrutura e caminhos

O provisionamento usou a base L100, a hospedagem L200 e o Bicep L300 versionados, com planos
`what-if` revisados e implantação incremental. A base contém armazenamento, busca Basic,
modelos, registro de imagens Basic, identidade gerenciada e logs.

O ambiente L300 é novo, integrado à rede virtual, separado do ambiente de referência L200.
A topologia contém três endpoints privados, cinco zonas DNS privadas e duas conexões
compartilhadas da busca. As conexões para Blob e modelos foram identificadas pela solicitação
da rodada e aprovadas nos destinos. `openai_account` foi aceito para o recurso `AIServices`
reaproveitado; a execução real de embeddings confirmou seu funcionamento nesta configuração.

O registro de imagens permanece público autenticado, com administrador local desativado.
O teste não representa bloqueio de toda saída à internet. A aplicação usa uma identidade somente
de leitura/uso de modelos; a sonda de manutenção usa outra identidade, com papéis proporcionais
nos recursos temporários e escrita somente no contêiner L300.

## Ingestão e atualização

| Conferência real | Resultado |
| --- | --- |
| Fontes L100 reconstruídas | Três documentos e 54 trechos no índice por código, hashes conferidos |
| Pipeline gerenciado L200 | Três documentos e 21 trechos; zero erros e avisos |
| Pipeline L300 | Quatro documentos e 24 trechos; 21 compartilhados e três de Atendimento |
| Metadados L300 | Nenhum trecho sem classe, com classe desconhecida, divergente ou fora do manifesto |
| Execução privada | Indexador `private`, sem agenda; quatro itens processados, zero falhas, erros e avisos |
| Carga repetida dentro da rede | Operação idempotente, sem duplicação das fontes |
| Exclusão operacional | Somente a cópia `VLAR-OP-ATD-1.0`; indexador reduziu o índice de 24 para 21 trechos |
| Restauração | Blob e metadados conferidos; nova execução retornou o índice a 24 trechos |
| Preservação | Fontes e namespaces L100/L200 conservados durante o ciclo |

Os efeitos foram observados por execuções manuais de um Container Apps Job no ambiente privado,
com uma réplica e nenhuma repetição automática. As sentinelas da sonda foram coletadas no
Log Analytics. O estado de conclusão do Job foi conferido junto dos resultados, sem tratá-lo
isoladamente como prova do conteúdo do índice.

## Acesso privado e privilégio mínimo

A sonda executou os módulos reais de recuperação, geração e política da mesma imagem do chat.
Nos modos textual, vetorial e híbrido, o perfil Atendimento recuperou fontes permitidas;
Corretor não recebeu o roteiro operacional nem seu marcador. O filtro foi enviado ao serviço
de busca, com `preFilter` nas consultas vetoriais.

| Controle | Evidência |
| --- | --- |
| Resolução de nomes | Blob, Search e modelos resolveram somente para endereços RFC 1918 dentro da rede |
| Filtro documental | Nenhum resultado fora das classes permitidas nos dois perfis e três modos |
| Recusa antes dos serviços | Ausência de contexto, papel ou filtro e filtro inválido resultaram em zero chamadas a busca, embeddings e geração |
| Geração interna | Uma resposta documentada para Atendimento, com citação rastreável do roteiro |
| Limites da identidade do chat | Três operações recusadas com HTTP 403: listar blobs, administrar índices e administrar armazenamento |

As três recusas de privilégio foram executadas de dentro da rede, para distinguir ausência
de papel de bloqueio de rede. A sonda registra códigos, contagens e invariantes, sem pergunta,
texto de resposta, credencial, endpoint ou identificador de pessoa.

## Autenticação e perfis HTTP

O chat nasceu com ingresso interno. A configuração da borda foi conferida:
plataforma habilitada, `Return401`, HTTPS obrigatório e somente `/healthz` e `/readyz`
isentos. Em Container Apps, esse contrato usa `unauthenticatedClientAction`; a conferência
inicial procurou indevidamente um campo `requireAuthentication` de outra superfície.
Essa tentativa foi corrigida sem alterar ou enfraquecer a autenticação.

O teste interno teve `/healthz` e `/readyz` com 200, API anônima e principal artificial com 401,
e consulta autenticada por identidade gerenciada de Atendimento com 200 e fonte operacional.
Somente depois dessa prova o ingresso externo HTTPS foi aberto.

| Perfil ou chamada externa | Resultado |
| --- | --- |
| Saúde e prontidão | HTTP 200 nas duas rotas |
| API anônima | HTTP 401 |
| Cabeçalho de principal artificial | HTTP 401, sem aceitar a identidade fabricada |
| Atendimento | HTTP 200, resposta documentada, roteiro e marcador presentes |
| Corretor | HTTP 200, recusa sem roteiro ou marcador; tipo `fora_de_escopo` observado |
| Ambos os papéis | HTTP 200, resposta documentada, roteiro e marcador presentes |
| Sem papel reconhecido | HTTP 403, nenhuma permissão documental |

Uma pergunta sintética de operação foi enviada uma vez por perfil. O teste avalia acesso
e apresentação, não uma nova amostra cega de qualidade. O tipo de recusa do Corretor foi mantido
como observado, sem ajuste do classificador.

Os testes usaram clientes de aplicação temporários, não login interativo de pessoas.
Papéis foram conferidos nos tokens. As credenciais dos clientes foram retiradas após cada teste;
o segredo do provedor de login permaneceu somente no serviço autorizado durante a execução
e foi revogado na limpeza.

## Isolamento, retorno e limpeza

O teste negativo da guarda Azure recusou `conectividadePrivadaValidada=false`.
Após a recusa, os três serviços continuavam com `publicNetworkAccess=Enabled`.
O plano de isolamento com as evidências positivas aprovadas mostrou três modificações,
sem criar ou excluir recursos.

O plano omitia oito propriedades calculadas ou padrões dos serviços: três do recurso de modelos
e cinco da busca. Elas foram revisadas individualmente, não aceitas por uma regra geral.
A implantação terminou com sucesso. Os três serviços passaram a `publicNetworkAccess=Disabled`;
regiões, camadas, réplicas, partições e as propriedades comparadas conservaram os valores anteriores.

| Prova após o isolamento | Resultado |
| --- | --- |
| Operador fora da rede, Blob | HTTP 403 `AuthorizationFailure`; identidade e papel de dados no contêiner exato conferidos, acesso público desabilitado |
| Operador fora da rede, Search | HTTP 403; mensagem identifica `publicNetworkAccess: Disabled` |
| Operador fora da rede, modelos | HTTP 403; mensagem identifica acesso público desabilitado e conexão privada necessária |
| DNS dentro da rede | Três nomes continuam resolvendo somente para endereços RFC 1918 |
| Recuperação filtrada | Oito consultas em dois perfis e três modos, quatro chamadas de embeddings e zero geração; nenhum trecho fora do perfil |
| Chat autenticado | HTTP 200 com roteiro e marcador; saúde/prontidão 200, anônimo e principal artificial 401 |
| Manutenção da fonte | Quatro blobs iguais ao manifesto, sem criação, substituição ou duplicação |
| Reindexação forçada privada | Quatro fontes processadas, 24 trechos, zero falhas, erros, avisos ou classes divergentes |

O código genérico do Blob não identifica sozinho o mecanismo da recusa. A qualificação combina
configuração ARM `Disabled`, papel no contêiner L300, token do operador correto e manutenção
funcional de dentro da rede. Search e modelos também identificam o bloqueio nas mensagens.
Essas negativas são diferentes dos três testes internos de privilégio da identidade do chat.

O teste de recuperação usou uma revisão temporária da mesma imagem, sem trocar política,
índice ou autenticação. O tráfego foi enviado integralmente à revisão temporária e devolvido
à origem. Nas duas posições, `/healthz` e `/readyz` retornaram 200 e a raiz anônima retornou 401.
Os pesos foram relidos, a origem conservou 100% do tráfego e a revisão temporária foi desativada.
Isso demonstra troca e retorno de configuração, não recuperação de incidente nem objetivo
de tempo de recuperação de produção.

As 21 sentinelas finais tiveram código 0 e resultado aprovado.
Elas registram execuções operacionais, não 21 perguntas de avaliação.
A aplicação temporária foi retirada somente após coletar as provas.
Após retirar o consumidor, o gerenciador simulou a remoção sem alterar os objetos,
removeu somente indexador, skillset, fonte e índice L300 e conferiu sua ausência.
Uma segunda execução foi idempotente. As definições e contagens de referência
L100/L200 permaneceram em 54/21 trechos; os quatro blobs L300 conservaram suas versões.
Isso confere a limpeza granular antes do encerramento completo do grupo temporário.

O segredo remanescente do provedor de login foi revogado. Os cinco registros de aplicação
e seus cinco service principals próprios foram removidos, com ausência conferida, e expurgados
individualmente no Microsoft Graph. O tipo, o ID e o aplicativo correspondente de cada objeto
foram conferidos antes do expurgo; nenhum objeto preexistente foi incluído.
Foram revogadas 16 atribuições próprias, com zero remanescentes. As oito atribuições anteriores
do operador conservaram IDs, principais, definições e escopos. O recurso `AIServices` próprio
foi expurgado após conferir nome, região, tipo e grupo; sua ausência na lista de excluídos
foi confirmada.

O Job foi removido. A plataforma recebeu a exclusão dos dois ambientes; o processo local
que aguardava o primeiro em `ScheduledForDelete` foi interrompido, sem cancelar a operação Azure.
O segundo foi solicitado sem espera, para não serializar as esperas da plataforma.
A primeira exclusão do grupo terminou com conflito na busca: os destinos das conexões
compartilhadas já haviam sido removidos, e o serviço não conseguiu conferir seus bloqueios
administrativos. A mensagem `LockedSPLResourceFound` não comprovava a existência de um bloqueio
real. Os dois links próprios, já desconectados, foram comparados com o inventário da rodada,
removidos pelo plano de controle da busca e tiveram sua ausência conferida.
A exclusão do grupo foi retomada sem recriar destinos, remover bloqueios ou ampliar permissões.

Na conferência final de 11 de outubro de 2026, às 03:36 UTC, o grupo exclusivo e o grupo
gerenciado estavam ausentes. A listagem da assinatura mostrou zero recursos próprios
remanescentes, os oito grupos anteriores e os 46 recursos de referência com os mesmos IDs,
tipos e grupos. Os oito papéis anteriores do operador também foram conferidos por ID,
principal, definição e escopo. Nenhum componente do grupo gerenciado foi excluído manualmente.

| Encerramento | Resultado conferido |
| --- | --- |
| Aplicação, Job e dois ambientes | Ausentes após retirada pelos serviços e encerramento do grupo |
| Grupo exclusivo e grupo gerenciado | Ausentes nas listagens finais; zero recursos próprios remanescentes |
| Conexões compartilhadas da busca | Dois links próprios removidos; lista vazia antes da retomada |
| Recurso de modelos | Removido e expurgado; ausente da lista de exclusão reversível |
| Aplicações e service principals | Cinco de cada, removidos e expurgados; segredo remanescente revogado |
| Identidades gerenciadas | Recursos retirados com o grupo; três principais associados ausentes no Entra ID |
| Papéis próprios | 16 retirados; zero atribuições próprias remanescentes |
| Preservação | Oito grupos, oito papéis do operador e 46 recursos anteriores conferidos |

As saídas completas e a tentativa falha de conferência permanecem no registro privado.
Retorno de comando, aceitação de exclusão e ausência real foram tratados como evidências
diferentes; a conclusão usa as listagens finais, não apenas o código de saída.
Cinco saídas temporárias de ferramentas locais foram removidas. As evidências persistentes
da sessão foram preservadas; não restaram processos próprios pendentes.

## Descritores e registros de operação

O helper `scripts\operar_l300.py` conferiu dois descritores construídos a partir das observações
reais. Antes de isolar, houve 16 itens atendidos e três negativas não exigidas naquele momento.
Depois de isolar, houve 19 itens atendidos, nenhum pendente ou reprovado. Arquivos de origem,
horários e hashes da proveniência foram conservados em local privado. O helper valida o formato
e a coerência; não substitui as sondas ou produz as observações.

O resumo de um recorte real dos logs do chat reconheceu 315 linhas: 309 sondas de saúde/prontidão
e seis requisições de usuário, cinco com 200 e uma com 403 `sem_papel_conhecido`. Não houve linha
desconhecida ou 5xx nesse recorte. Os 401 interceptados pela borda estão nos testes HTTP,
não precisam aparecer no log da aplicação. As latências desse recorte pequeno não constituem
teste de carga, disponibilidade de produção ou objetivo de nível de serviço.

## Falhas e correções preservadas

| Ocorrência | Tratamento |
| --- | --- |
| `DeploymentActive` na primeira rede | A implantação raiz tinha o mesmo nome do módulo; retomada com nome raiz distinto, sem modificar a topologia |
| `Unsupported` no plano de papéis | Revisados os tipos, escopos e principais gerados; quantidades qualificadas explicitamente |
| Parser de expressões ARM | Literal longo desalinhava a leitura do tipo; corrigido com testes de regressão antes da sanitização do plano real |
| Primeira imagem da sonda | A CLI selecionou o Dockerfile da raiz; retomada da pasta do contexto correto após conferir o run falho |
| Instalação da extensão de logs | Dependência de construção indisponível; resultados recuperados pela API do Log Analytics sem alterar a instalação global |
| Primeira emissão de token externo | Falhou antes de chamar o chat; credencial retirada, nova emissão posterior funcionou sem mudar política ou configuração |
| Conferências do coordenador | Diferenças de formato entre saídas CLI e ARM e erros de sintaxe PowerShell, inclusive na limpeza local de saídas, foram corrigidos; tentativas preservadas |
| Observador da negativa externa | Primeiro interrompeu antes de HTTP por comparar o papel do contêiner com o escopo da conta; depois recebeu três 403, mas não reconheceu as mensagens de Search/modelos. Escopo e reconhecimento foram corrigidos, sem alterar papéis, rede, política ou serviços |
| Duração em PowerShell | Conversão automática de datas JSON produziu uma duração negativa. A leitura passou a usar `ConvertFrom-Json -DateKind String` e `DateTimeOffset` sobre o ISO original |
| Consulta Graph da limpeza | URL com mais de um parâmetro de consulta retornou dados, mas a invocação Windows terminou com erro; a conferência usou comandos `az ad ... show` por ID exato antes de qualquer exclusão |
| Script auxiliar de limpeza | O agente não entregou script ou testes; a coordenação encerrou essa frente e executou a limpeza por CLI, com inventários e verificações reais, sem apresentar o plano ausente como validado |
| Espera de exclusão dos ambientes | Primeiro ambiente permaneceu `ScheduledForDelete`; encerrada somente a espera local e solicitada a exclusão assíncrona do segundo, seguida do grupo dedicado. A aceitação não foi tratada como ausência final |
| Exclusão do grupo e da busca | O destino de um SPL já removido causou `ConflictError`/`LockedSPLResourceFound`. Os dois links próprios foram retirados e sua ausência conferida antes da retomada, sem remover bloqueios ou recriar dependências |
| Espera `az group wait --deleted` | Retornou código 0, mas o grupo e a busca ainda existiam e o histórico de atividade registrava falha. A conferência recusou o falso encerramento e só aprovou após a nova exclusão e as listagens reais |

O parser corrigido reconhece tipos de recursos em literais ARM longos e continua recusando
expressões inválidas e texto livre. Os testes finais de regressão local são registrados
separadamente, sem somar execuções repetidas como casos independentes.

## Regressão local após a execução Azure

O comando `.\.venv\Scripts\python.exe -m unittest discover -s tests -v` terminou com
859 casos: 858 aprovados e um ignorado por permissões POSIX no Windows.
Os três casos acrescentados cobrem o parser de expressões encontrado no plano Azure.
A conferência POSIX continua pendente em Linux; o workflow escrito não foi executado no GitHub.

## Comandos e alcance da conferência final

Os comandos Azure abaixo receberam assinatura, grupo, nomes ou IDs exatos do inventário privado.
São os comandos efetivamente usados, não uma receita com destinos públicos.

| Comando ou operação | Resultado observado |
| --- | --- |
| `az deployment group create`, fase `isolar` | Concluído; três serviços com acesso público desabilitado e propriedades comparadas preservadas |
| `az rest`, início e leitura das execuções do Job | 21 sentinelas operacionais aprovadas; provas privadas e remoção granular conferidas |
| `scripts\operar_l300.py --etapa conferir` | Descritores reais antes/depois completos, sem pendência ou reprovação |
| `scripts\operar_l300.py --etapa resumir-logs` | 315 linhas reais reconhecidas; sondas separadas das seis requisições de usuário |
| `az containerapp revision show`, `ingress traffic set` e `revision deactivate` | Troca e retorno conferidos, origem com 100% e revisão temporária desativada |
| `az ad app credential delete`, `az ad sp delete`, `az ad app delete` | Segredo restante revogado; cinco apps e cinco service principals removidos |
| `az rest`, Graph `directory/deletedItems` | Dez objetos próprios expurgados e ausência permanente conferida |
| `az role assignment delete` e listagem posterior | 16 atribuições próprias retiradas; oito anteriores intactas |
| `az containerapp delete`, `job delete` e `env delete` | Consumidor, sonda e ambientes retirados; esperas e retomadas preservadas |
| `az rest`, exclusão e listagem de `sharedPrivateLinkResources` | Dois links próprios removidos, com lista vazia antes da retomada do grupo |
| `az group delete`, `az group list` e `az resource list` | Após a retomada, grupo exclusivo e gerenciado ausentes; zero recursos próprios e 46 anteriores presentes |
| `az cognitiveservices account purge` e `list-deleted` | Recurso de modelos próprio expurgado e ausência conferida |
| `az rest`, Cost Management `ActualCost` | Consulta após a limpeza ainda sem linhas; não interpretada como custo zero |
| `.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_repositorio.py` | Dez testes aprovados após a atualização dos guias |
| Parser PowerShell e conferência de links | 30 blocos sem erros; 303 links locais em 14 documentos conferidos, sem executar exemplos |
| Destinos privados nos arquivos alterados | 50 arquivos conferidos sem os valores privados da rodada; evidências completas conservadas somente na sessão |

Login humano, teste de carga, matriz Linux, proteção do ambiente GitHub e execução Actions/OIDC
continuam não executados. O L300 não altera a classificação histórica L100/L200 nem representa
homologação para produção. A entrega permanece local, sem commit, push ou release L300 nesta rodada.

## Custo e limites

Foram consultados medidores oficiais em USD: Search Basic por unidade/hora, registro Basic,
computação por consumo e endpoints privados padrão. A execução limita réplicas e duração,
sem GPU, perfil dedicado ou modelo provisionado. Há custos adicionais de armazenamento, DNS,
tráfego, logs e recursos gerenciados.

A consulta após a limpeza usou `ActualCost`, de 11 a 12 de outubro de 2026 UTC,
incluindo o grupo exclusivo e o grupo gerenciado do novo ambiente. Retornou zero linhas
e nenhuma continuação de paginação; a moeda efetiva e o total não vieram no resultado.
Essa ausência é atraso ou indisponibilidade de dados de cobrança, não confirmação de custo zero
nem total final. O teto autorizado foi US$90; o gasto efetivo não pôde ser comprovado pela API.
Os recursos próprios foram encerrados, sem manter serviços da rodada à espera da cobrança.

Código da aplicação e sonda principal por Claude Sonnet 5.5; coordenação, helpers privados
de execução e documentação por GPT-6.1 Sol.
Esses modelos são distintos dos deployments da aplicação e do Copilot do aluno.
