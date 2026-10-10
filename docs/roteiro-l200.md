# L200: roteiro da ingestão gerenciada ao chat autenticado

| Item | Definição |
| --- | --- |
| Situação | Implementação e sete guias disponíveis; validação Azure executada por etapas, com avaliação final e limpeza registradas separadamente |
| Público | Pessoas de Atendimento, operações, arquitetura e desenvolvimento que concluíram o L100 |
| Resultado | Comparar duas formas de ingestão e hospedar um chat com fontes, identidade própria e acesso autenticado em Azure Container Apps |
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
Os guias incluem cenário, objetivos, artefatos, conceitos, pré-requisitos, prática, conferência,
glossário, boas práticas e fontes conforme o [padrão de autoria](guia-de-autoria.md).
O roteiro inicialmente publicado no commit `d4a93cc` era planejamento; esta versão registra
a implementação iniciada após a autorização posterior do mantenedor.

O teste final HTTP teve 11 de 18 casos conformes, duas divergências e cinco descartes HTTP 503.
As atividades foram executadas, mas o conjunto completo de atendimento ficou reprovado.
O [registro do Desafio 06](validacao/l200-06-avaliar-chat.md) conserva a medição única, sem alterar
perguntas ou parâmetros para eliminar os erros.

## Continuidade com o L100

Os recursos Azure da validação anterior foram removidos. Reaproveitar o L100 significa começar
pelos arquivos versionados, não presumir a existência de armazenamento, busca ou deployments.

| Artefato existente | Uso no L200 | Condição |
| --- | --- | --- |
| [Documentos e inventário](../dados/l100/inventario.json) | Mesmo produto e mesmas fontes na comparação | Preservar textos, versões e hashes; novas regras exigem aprovação |
| [Infraestrutura](../infra/main.bicep) | Base de armazenamento, busca e modelos | Conferir destino, compatibilidade, permissões e what-if antes da reconstrução |
| [Carga e indexação Python](../scripts/indexar_documentos.py) | Caminho de referência da comparação | Conservar o índice do L100 enquanto o novo é avaliado |
| [Política de resposta](../scripts/lab_politica.py) | Decisão compartilhada por console, agente e chat | A interface apresenta o tipo, as evidências e o aviso; não recupera o texto livre suprimido de casos individuais |
| [Agente do Microsoft Agent Framework](../scripts/lab_agente.py) | Referência de limites e rastro no console | O chat reutiliza recuperação, geração e política em fluxo fixo, sem escolha de ferramentas pelo agente |
| [Avaliação](../scripts/lab_avaliacao.py) | Métricas e separação entre ajuste e teste | Manter o resultado histórico do D06; nova medição final usa novo conjunto congelado |
| [Identidade do L100](../desafios/L100/07-identidade-da-aplicacao.md) | Referência para papéis e recusas esperadas | O registro e o segredo anteriores foram removidos; a aplicação hospedada usa identidade gerenciada |

O L200 reutiliza `text-embedding-3-small`, versão `1`, com 1.536 dimensões, e `gpt-5.4-mini`,
versão `2026-03-17`, conferidos em `brazilsouth`. Catálogo, região e cotas precisam ser conferidos
no destino do aluno antes de executar.
O modelo do Copilot, o de autoria e os deployments Azure continuam sendo escolhas separadas.

## Sequência dos sete desafios

| Desafio disponível | Prática e conceitos | Resultado a conferir | Dependência |
| --- | --- | --- | --- |
| [01. Reconstruir a base](../desafios/L200/01-reconstruir-base.md) | Versão, destino, plano e base Python | Três documentos e índice de referência com 54 trechos | L100 e autorização do destino |
| [02. Ingestão gerenciada](../desafios/L200/02-ingestao-gerenciada.md) | Fonte, indexador, identidade e papéis [1][2] | Três documentos no índice separado, execução e falhas observáveis | Desafio 01 |
| [03. Dividir, vetorizar e comparar](../desafios/L200/03-comparar-ingestao.md) | Skillset, divisão, embeddings e comparação [3] | Diferenças 54/21 trechos explicadas e recuperação documental conferida | Desafio 02 |
| [04. Chat local com fontes](../desafios/L200/04-chat-local.md) | FastAPI, interface HTTP e conversas isoladas | Texto, citações, avisos e erros, sem histórico no servidor | Desafio 03 |
| [05. Hospedar com autenticação](../desafios/L200/05-hospedar-chat.md) | Imagem, identidade gerenciada, ingresso e login [4][5][6] | Consulta real, acesso anônimo recusado e papéis limitados | Desafio 04 e autorização de implantação e identidade |
| [06. Avaliar o contrato do chat](../desafios/L200/06-avaliar-chat.md) | Conjunto próprio e configuração congelada | Uma resposta por caso, divergências e uso conhecido, sem retunar pelo teste | Desafio 05 |
| [07. Operar, recuperar e limpar](../desafios/L200/07-operar-recuperar-limpar.md) | Revisões, logs, custo e alvos de remoção | Retorno à revisão anterior e preservação de recursos preexistentes | Desafio 06 |

Os [registros de validação](validacao) distinguem o que foi executado, as falhas e as limitações.
Sucesso de build, leitura de papéis, teste de fumaça e contrato de resposta têm evidências distintas.

## Decisões técnicas e fronteiras

### Comparar a ingestão sem substituir o índice de referência

O indexador de blobs recebe conteúdo de um contêiner e grava um índice de busca [1]. A identidade
gerenciada do serviço de busca precisa de papéis adequados no armazenamento e nos recursos
usados pelo processamento [2]. O exercício usa `ResourceId` e identidade gerenciada, sem chaves de conta.

A vetorização integrada acrescenta divisão e geração de vetores à ingestão. A vetorização na
consulta é uma configuração separada; quando adotada, deve usar um modelo compatível com o que
gerou os vetores dos documentos [3]. O L200 usa vetorização integrada **na ingestão** e cálculo
do embedding da pergunta em Python. Não configura um vetorizador de consulta no serviço.

O índice `vareleira-lar-l200` conserva o L100 como referência. A comparação operacional conferiu
fontes, campos, seis assuntos de fumaça e exclusão/reposição de documento. A adoção ainda depende
de avaliação de contrato e de fidelidade correspondente ao uso. Quantidade menor de trechos,
isoladamente, não demonstra melhoria de qualidade.

O pipeline gerenciado produziu 21 trechos para os mesmos três documentos, contra 54 do Python.
Os campos de seção e cláusulas ficam vazios; os identificadores dos trechos são gerados pela projeção.
Documento, versão e citação localizam a origem. O indexador lê o prefixo do contêiner, enquanto
a carga Python usa o inventário como lista de permissão.

### Separar a identidade da aplicação do login de quem usa o chat

A identidade gerenciada permite à aplicação hospedada obter acesso a recursos compatíveis sem
distribuir um segredo de cliente para a consulta a busca e modelos [4]. Ela recebe somente os
papéis necessários nesses recursos. A identidade do indexador e a da aplicação têm funções
distintas: o chat não grava blobs nem administra índices.

O login do usuário é outra relação. Azure Container Apps oferece autenticação integrada com
Microsoft Entra ID e outros provedores [5]. O exercício exige autenticação e aceita o público
autenticado do tenant configurado. O registro empresarial não exige atribuição a pessoas específicas.
A credencial do provedor fica em Container Apps Secrets; sua criação e remoção têm autorização própria.

O L200 usa uma base sintética compartilhada pelo público do piloto. Autorização por documento e
dependências privadas serão aprofundadas no L300, sem atribuir essas capacidades ao protótipo atual.

### Publicar uma interface sem transformar o piloto em serviço público

Ingresso externo e interno controlam caminhos diferentes de acesso em Container Apps [6].
O caminho conferido mantém HTTPS e cria a aplicação com ingresso interno.
A exposição externa ocorre somente depois de conferir autenticação obrigatória.

A interface trata indisponibilidade, limites e fontes. O servidor não guarda conversa; o navegador
mantém mensagens apenas em memória e envia a pergunta atual. Logs usam rota e causa em vocabulário
fechado, sem pergunta ou resposta. O chat usa FastAPI; a imagem fica no ACR e logs no Log Analytics.
Descartes de política retornam HTTP 503, sem apresentar texto rejeitado.

## Uso do Copilot e portões de execução

Em cada desafio, o aluno abre a pasta completa no VS Code, identifica o terminal e anexa
somente os arquivos necessários. Os prompts separam explicar, planejar, editar e executar.
O aluno revisa o diff, as dependências e as conferências antes de qualquer ação externa.
Nomes e permissões são parâmetros, não valores do ambiente do instrutor.

| Etapa de trabalho | O que precisa estar definido antes |
| --- | --- |
| Gerar código e testes locais | Arquivos de escrita, contrato, dependências, erros esperados e critérios de teste |
| Criar ou alterar recursos | Assinatura, tenant, grupo, região, plano what-if, custo, efeitos e autorização correspondente |
| Criar identidades ou conceder papéis | Quem administra o escopo, identidade exata, papel, recurso de destino e remoção |
| Enviar conteúdo ou consultar modelos | Apenas dados sintéticos, destino explícito, configuração congelada e limite de consumo |
| Remover recursos | Identificadores conferidos, propriedade dos objetos e preservação das dependências preexistentes |

A publicação do roteiro não autoriza a execução desses passos no Azure.

## Custo, recuperação e transição

O nível acrescenta hospedagem, imagens e telemetria à busca, modelos e armazenamento.
Confira preços e consumo na região escolhida; este roteiro não estima um valor monetário.
Pausar a interface não equivale a pausar todas as suas dependências.

Cada desafio registra objetos acrescentados e dependências para o seguinte.
A limpeza usa alvos identificados e preserva recursos preexistentes. Para a transição ao
L300, conserve parâmetros, fontes e resultados e defina a migração de rede e identidade.
L300 e L400 ainda não têm implementação autorizada nesta entrega.

## Glossário

| Termo | Significado no roteiro |
| --- | --- |
| Indexador | Processo do serviço de busca que lê uma fonte e alimenta o índice |
| Skillset | Conjunto de etapas de processamento usado durante a ingestão |
| Vetorização integrada | Geração de vetores incorporada ao caminho de ingestão ou de consulta |
| Identidade gerenciada | Identidade vinculada a um recurso ou criada separadamente, cuja credencial é administrada pelo Azure |
| Ingresso | Configuração que determina como requisições chegam à aplicação |
| Revisão da aplicação | Versão implantada de sua configuração e imagem; sua recuperação é exercitada no nível |

## Fontes e autoria

Fontes oficiais consultadas em 9 e 10 de outubro de 2026. Confira capacidades e cotas no destino
de cada execução.

1. [Indexador de Azure Blob Storage](https://learn.microsoft.com/en-us/azure/search/search-how-to-index-azure-blob-storage).
2. [Identidades gerenciadas no Azure AI Search](https://learn.microsoft.com/en-us/azure/search/search-how-to-managed-identities).
3. [Vetorização integrada no Azure AI Search](https://learn.microsoft.com/en-us/azure/search/vector-search-integrated-vectorization).
4. [Identidades gerenciadas em Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/managed-identity).
5. [Autenticação e autorização em Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/authentication).
6. [Ingresso em Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/ingress-overview).

Roteiro e guias elaborados com GPT-6.1 Sol no GitHub Copilot CLI. O Astra, preferido para documentação,
não estava disponível. Implementação e testes por Claude Sonnet 5.5. Nenhum Document Swarm foi iniciado.
