# L200: roteiro da ingestão gerenciada ao chat autenticado

| Item | Definição |
| --- | --- |
| Situação | Planejamento: sete desafios definidos; código, infraestrutura e guias executáveis do L200 ainda não implementados |
| Público | Pessoas de Atendimento, operações, arquitetura e desenvolvimento que concluíram o L100 |
| Resultado pretendido | Comparar duas formas de ingestão e hospedar um chat com fontes, identidade própria e acesso autenticado em Azure Container Apps |
| Continuidade | Reutilizar documentos sintéticos, inventário, política, testes e parâmetros do L100; reconstruir recursos apenas em destino autorizado |
| Fora do escopo | Produção, documentos reais de segurados, decisões individuais de cobertura e as dependências privadas previstas para o L300 |

## Cenário e critérios de conclusão

No piloto interno fictício de 2025, Beatriz Torres quer disponibilizar o assistente para Atendimento
e corretores sem depender do terminal de uma pessoa. A equipe compara a ingestão por scripts com
uma ingestão operada pelo serviço de busca e prepara uma interface de chat. As regras continuam
nos documentos sintéticos aprovados; a mudança de interface não amplia o que o assistente pode decidir.

O nível termina quando a equipe consegue identificar a origem de cada trecho, comparar os dois
índices com critérios previamente definidos, consultar o chat com uma identidade autorizada,
observar recusas de acesso, recuperar uma revisão anterior e remover exclusivamente seus recursos.
Cada desafio terá cenário, objetivos, artefatos, conceitos, pré-requisitos, prática, conferência,
glossário, boas práticas e fontes conforme o [padrão de autoria](guia-de-autoria.md).

## Continuidade com o L100

Os recursos Azure da validação anterior foram removidos. Reaproveitar o L100 significa começar
pelos arquivos versionados, não presumir a existência de armazenamento, busca ou deployments.

| Artefato existente | Uso no L200 | Condição |
| --- | --- | --- |
| [Documentos e inventário](../dados/l100/inventario.json) | Mesmo produto e mesmas fontes na comparação | Preservar textos, versões e hashes; novas regras exigem aprovação |
| [Infraestrutura](../infra/main.bicep) | Base de armazenamento, busca e modelos | Conferir destino, compatibilidade, permissões e what-if antes da reconstrução |
| [Carga e indexação Python](../scripts/indexar_documentos.py) | Caminho de referência da comparação | Conservar o índice do L100 enquanto o novo é avaliado |
| [Política de resposta](../scripts/lab_politica.py) | Decisão compartilhada por console, agente e futura interface | A interface apresenta o tipo, as evidências e o aviso; não recupera o texto livre suprimido de casos individuais |
| [Agente do Microsoft Agent Framework](../scripts/lab_agente.py) | Reutilização da lógica de consulta | Separar lógica da aplicação e transporte HTTP, protocolo de comunicação da interface |
| [Avaliação](../scripts/lab_avaliacao.py) | Métricas e separação entre ajuste e teste | Manter o resultado histórico do D06; nova medição final usa novo conjunto congelado |
| [Identidade do L100](../desafios/L100/07-identidade-da-aplicacao.md) | Referência para papéis e recusas esperadas | O registro e o segredo temporários foram removidos; a aplicação hospedada adotará identidade gerenciada |

Modelos, versões, região e cotas do L200 serão definidos na implementação. A prioridade é
reaproveitar os deployments do laboratório quando forem compatíveis com o novo caminho.
O modelo do Copilot, o de autoria e os deployments Azure continuam sendo escolhas separadas.

## Sequência dos sete desafios

| Desafio planejado | Prática e conceitos | Resultado a conferir | Dependência |
| --- | --- | --- | --- |
| 01. Reconstruir a base a partir da release | Identificar a versão do código, definir o destino e simular a infraestrutura; reconstruir somente a base necessária | Documentos e hashes conferidos, busca por scripts reproduzível e custos previstos registrados | L100 e autorização específica para o ambiente |
| 02. Ler o Blob Storage com um indexador | Criar uma fonte de dados e um indexador, processo que lê dados e alimenta o índice; usar identidade gerenciada para acesso ao contêiner [1][2] | Conteúdo e metadados importados em um índice separado, com falhas e repetição observáveis | Desafio 01 |
| 03. Dividir e vetorizar com o serviço | Definir um skillset, conjunto de etapas de processamento, e comparar divisão, embeddings e campos com o caminho Python [3] | Índices comparáveis quanto a documentos, evidências e recuperação; diferenças explicadas, sem exigir IDs ou trechos idênticos | Desafio 02 |
| 04. Construir o chat local com fontes | Separar a lógica Python da interface HTTP; apresentar perguntas, tipos, citações, avisos e erros; isolar o estado de cada conversa | Testes locais da interface e da política, sem segredo no navegador e sem mistura de conversas | Desafio 03 e política compartilhada |
| 05. Hospedar o chat com acesso autenticado | Empacotar a aplicação, configurar identidade gerenciada, papéis de dados, ingresso e autenticação dos usuários [4][5][6] | Aplicação acessível por usuários autorizados; identidade da aplicação consulta busca e modelos, mas não administra a base | Desafio 04 e autorização para implantação, papéis e configuração de autenticação |
| 06. Avaliar o chat e a migração | Congelar configuração e conjunto independente; testar respostas, evidências, recusas, isolamento e falhas; distinguir teste local de execução Azure | Resultados por critério, limites e consumo registrados, sem ajustar a aplicação com o conjunto final | Desafio 05 |
| 07. Operar revisões, recuperar e limpar | Conferir configuração, revisão da aplicação, logs sanitizados, custos, retorno à versão anterior e remoção com alvos explícitos | Recuperação demonstrada e recursos temporários removidos; dependências preservadas ou migradas para o L300 | Desafio 06 |

Os títulos identificam desafios planejados, não guias disponíveis. Este roteiro não cria links
para arquivos futuros nem fornece comandos de implantação ainda não exercitados.

## Decisões técnicas e fronteiras

### Comparar a ingestão sem substituir o índice de referência

O indexador de blobs recebe conteúdo de um contêiner e grava um índice de busca [1]. A identidade
gerenciada do serviço de busca precisa de papéis adequados no armazenamento e nos recursos
usados pelo processamento [2]. O exercício continuará sem chaves de conta ou conexões com segredo.

A vetorização integrada acrescenta divisão e geração de vetores à ingestão. A vetorização na
consulta é uma configuração separada; quando adotada, deve usar um modelo compatível com o que
gerou os vetores dos documentos [3]. O L200 decidirá explicitamente qual caminho usar.

O novo índice terá nome próprio. Critérios de comparação serão definidos antes das medições:
correspondência com as fontes, cobertura dos assuntos recuperados, evidências localizáveis,
tratamento de atualizações e exclusões, custo e operação. Um tamanho de trecho diferente não é,
sozinho, defeito ou melhoria. A migração dependerá dos resultados e manterá um caminho de retorno.

### Separar a identidade da aplicação do login de quem usa o chat

A identidade gerenciada permite à aplicação hospedada obter acesso a recursos compatíveis sem
distribuir um segredo de cliente para a consulta a busca e modelos [4]. Ela receberá somente os
papéis necessários nesses recursos. A identidade do indexador e a da aplicação terão funções
distintas: ingerir conteúdo não exige que o chat possa gravá-lo.

O login do usuário é outra relação. Azure Container Apps oferece autenticação integrada com
Microsoft Entra ID e outros provedores [5]. O exercício exigirá autenticação e definirá quem pode
usar a aplicação. Credenciais e permissões eventualmente exigidas pela configuração do provedor
de login precisam de autorização própria; identidade gerenciada não elimina essa configuração.

Acesso autenticado ao chat não implica autorização para todos os documentos de uma organização.
O L200 continua com a base sintética compartilhada do piloto. Restrições por documento e
dependências privadas serão aprofundadas no L300, sem atribuir essas capacidades ao protótipo atual.

### Publicar uma interface sem transformar o piloto em serviço público

Ingresso externo e interno controlam caminhos diferentes de acesso em Container Apps [6].
A implementação escolherá o caminho de teste compatível com o ambiente autorizado e manterá
HTTPS. A exposição de um endereço externo exige autenticação; não será um chat anônimo.

A interface terá tratamento explícito de indisponibilidade, limites de consulta e apresentação
das fontes. Logs serão sanitizados e não guardarão credenciais ou conteúdo real de segurados.
Decisões de retenção de conversas, framework HTTP, interface, registro de imagens e coleta de
telemetria serão documentadas antes de implementar seus componentes.

## Uso do Copilot e portões de execução

Em cada desafio, o aluno abrirá a pasta completa no VS Code, identificará o terminal e anexará
somente os arquivos necessários. Os prompts separarão explicar, planejar, editar e executar.
O aluno revisará o diff, as dependências e a conferência prevista antes de qualquer ação externa.
Nomes e permissões recebidos pelo programa serão parâmetros, não valores do ambiente do instrutor.

| Etapa de trabalho | O que precisa estar definido antes |
| --- | --- |
| Gerar código e testes locais | Arquivos de escrita, contrato, dependências, erros esperados e critérios de teste |
| Criar ou alterar recursos | Assinatura, tenant, grupo, região, plano what-if, custo, efeitos e autorização correspondente |
| Criar identidades ou conceder papéis | Quem administra o escopo, identidade exata, papel, recurso de destino e remoção |
| Enviar conteúdo ou consultar modelos | Apenas dados sintéticos, destino explícito, configuração congelada e limite de consumo |
| Remover recursos | Identificadores conferidos, propriedade dos objetos e preservação das dependências preexistentes |

A publicação do roteiro não autoriza a execução desses passos no Azure.

## Custo, recuperação e transição

O planejamento considera busca cobrada enquanto o serviço existir, uso de modelos, operações de
armazenamento e os futuros recursos de hospedagem, imagens e telemetria. Preços e consumo serão
verificados na região escolhida; este roteiro não estima um valor monetário.
Pausar a interface não equivale a pausar todas as suas dependências.

Cada desafio registrará os objetos que acrescenta e o que precisa permanecer para o seguinte.
A limpeza removerá somente os recursos criados no destino autorizado. Antes da transição para
o L300, a equipe conservará parâmetros, fontes e resultados, definirá a migração de rede e
identidade e demonstrará o retorno ao caminho anterior.

## Glossário

| Termo | Significado no roteiro |
| --- | --- |
| Indexador | Processo do serviço de busca que lê uma fonte e alimenta o índice |
| Skillset | Conjunto de etapas de processamento usado durante a ingestão |
| Vetorização integrada | Geração de vetores incorporada ao caminho de ingestão ou de consulta |
| Identidade gerenciada | Identidade vinculada a um recurso ou criada separadamente, cuja credencial é administrada pelo Azure |
| Ingresso | Configuração que determina como requisições chegam à aplicação |
| Revisão da aplicação | Versão implantada de sua configuração e imagem; a estratégia de recuperação será exercitada no nível |

## Fontes e autoria

Fontes oficiais consultadas em 9 de outubro de 2026. Capacidades e configurações precisam ser
conferidas novamente antes da implementação.

1. [Indexador de Azure Blob Storage](https://learn.microsoft.com/en-us/azure/search/search-how-to-index-azure-blob-storage).
2. [Identidades gerenciadas no Azure AI Search](https://learn.microsoft.com/en-us/azure/search/search-how-to-managed-identities).
3. [Vetorização integrada no Azure AI Search](https://learn.microsoft.com/en-us/azure/search/vector-search-integrated-vectorization).
4. [Identidades gerenciadas em Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/managed-identity).
5. [Autenticação e autorização em Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/authentication).
6. [Ingresso em Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/ingress-overview).

Roteiro elaborado com GPT-6.1 Sol no GitHub Copilot CLI. O Astra, preferido para documentação,
não estava disponível na sessão. Nenhum componente do L200 foi implementado ou provisionado.
