# L400: registro da implementação e validação

| Campo | Situação |
| --- | --- |
| Data de referência | 11 de outubro de 2026, com operações externas registradas em UTC |
| Escopo | Sete desafios, coordenação limitada, operação de deployments, evolução de índice, comparação, carga e limpeza |
| Estado atual | Implementação, comparação, isolamento e encerramento dos temporários próprios verificados |
| Base | L300 validado e encerrado, conservado em cópia privada antes das alterações |
| Autorização | Pedido do mantenedor para implementar e executar até o final, sem perguntas intermediárias |
| Destino | Assinatura e tenant anteriores, região `brazilsouth` e grupo exclusivo novo |
| Custo | Teto anterior de US$90, sem renovação como segundo orçamento; cobrança efetiva L300/L400 indisponível |
| Publicação | Branch local; sem commit, push, release ou ativação de confiança GitHub nesta rodada |
| Autoria | Runtime e infraestrutura por Claude Sonnet 5.5; documentação, coordenação e helpers privados por GPT-6.1 Sol; Astra ausente do catálogo |

## Continuidade e decisões

O [registro Azure L300](l300-azure-validacao.md) permanece como evidência do nível anterior.
Antes de iniciar o L400, a coordenação conservou 60 arquivos em local privado, incluindo
alterações não commitadas, fontes, política e avaliações anteriores. A branch local L400 parte
da mesma revisão de base sem descartar o trabalho L300.

O exercício usa somente as quatro fontes sintéticas já aprovadas: condições gerais, glossário,
perguntas frequentes e roteiro operacional de Atendimento. Nenhuma nova regra de seguro,
documento de pessoa ou pergunta final de avaliação foi carregada.

A estratégia convencional continua como referência e padrão. A opção de coordenação exige
autenticação e autorização documental. Planejador e redator usam MAF, Microsoft Agent Framework;
filtros, compatibilidade e apresentação final ficam sob controle do programa.

O primário e a contingência preservam `gpt-5.4-mini`, versão `2026-03-17`.
`text-embedding-3-small`, versão `1`, é usado na referência de 1.536 dimensões e no candidato
de 768. Duas instâncias de geração não representam cota adicional nem disponibilidade regional
independente.

O contexto Vareleira 0.1.0, o piloto interno de 2025 e as medições L100/L200 permanecem intactos.
O L400 não implica homologação para produção. Document Swarm não foi executado.

## Preparação local conferida

| Comando ou observação | Resultado |
| --- | --- |
| `.\.venv\Scripts\python.exe --version` | Python 3.12.10 |
| `.\.venv\Scripts\python.exe -m pip check` | Sem dependências quebradas |
| `scripts\gerenciar_ingestao_l300.py --etapa validar` | Quatro fontes aprovadas, classes e hashes conferidos, sem rede |
| Pacotes MAF instalados | `agent-framework-core` 1.21.0 e `agent-framework-openai` 1.15.0 |
| API real de workflows | `WorkflowBuilder`, `Executor`, `handler`, `WorkflowContext` e `WorkflowEvent` disponíveis |
| API real de modelos MAF | `OpenAIChatClient` disponível; exemplos com `AzureOpenAIResponsesClient` não correspondem a esta instalação |
| Bicep CLI | 0.48.1 |
| Prévia estrutural dos guias | Sete guias e roteiro com 153 links e âncoras locais válidos, sem cercas incompletas |
| Linux local | WSL consultado, sem distribuição configurada; nenhum sistema foi instalado ou alterado |

A instalação de pacotes não foi alterada para copiar nomes de uma API diferente.

### Handoff de infraestrutura e operação

A frente Sonnet 5.5 entregou Bicep, parâmetros, `operar_l400.py`, `avaliar_l400.py` e testes.
Os comandos focados dessa frente tiveram 55 casos aprovados: 19 de infraestrutura, 19 de
avaliação e 17 de operação. A regressão de base, sem o módulo de orquestração ainda em ajuste,
teve 914 casos com resultado OK e um ignorado no Windows. Essa é uma execução parcial,
não a suíte integrada final L400.

Lint e build dos arquivos novos e do módulo de aplicação reutilizado terminaram sem avisos
com Bicep 0.48.1. Parâmetros foram compilados somente com valores fictícios. A coordenação
também executou `operar_l400.py --etapa planejar --validar-bicep` e conferiu suas CLIs.
Nenhuma guarda ARM foi aplicada no Azure nesse marco.

Dois testes de cancelamento e desconexão da frente de runtime ainda falharam durante a integração.
O defeito foi encaminhado ao responsável antes de executar a suíte completa ou provisionar.
Os resultados parciais não foram apresentados como aprovação do novo runtime.

### Fechamento local integrado

O runtime teve 83 testes focados aprovados. A coordenação executou
`.\.venv\Scripts\python.exe -m unittest discover -s tests -v`: **997 casos em 158,396 segundos,
996 aprovados e um ignorado**, com saída completa conservada em local privado.
O teste ignorado depende de permissões POSIX indisponíveis no Windows.
`node --check web\app.js`, plano da CLI MAF e `git diff --check` passaram.
Um snapshot privado de 67 arquivos congelou o runtime, requisitos, templates e interface
antes do conjunto final novo e do provisionamento.

O travamento anterior foi corrigido tratando o cancelamento e a recepção de desconexão atrás
do middleware do servidor. O teste de Ctrl+C passou a aguardar a chamada em andamento,
mantendo a asserção de interrupção por requisição. O teste com uvicorn real verificou
desconexão sem chamadas remotas.

O agente relatou uma falha não capturada em uma das cinco execuções completas anteriores.
As execuções posteriores e a passagem registrada da coordenação aprovaram; a causa específica
dessa ocorrência não foi identificada e não é apresentada como resolvida.
Essa ressalva não foi omitida do histórico.

O resumo de logs recebeu padrões exatos de partida documental e de coordenação. Texto livre,
URLs, tokens e linhas desconhecidas continuam impedindo sua aprovação.

## Preflight Azure

A conta e a assinatura foram consultadas com destino explícito. A assinatura está ativa,
o tenant da sessão corresponde ao destino e o nome proposto do grupo exclusivo não existia.
A linha de base tem oito grupos, 46 recursos e oito atribuições do operador, conservados
em inventário privado.

O catálogo de `brazilsouth` contém os modelos e as versões acordados. A consulta de cota
`GlobalStandard` mostrou 500 unidades livres para geração e 1.000 para embeddings,
com unidade retornada `Count`. A observação foi usada para planejar capacidade pequena;
não foi convertida automaticamente em requisições por minuto.

Nenhum recurso foi criado antes da integração local. Configurações, IDs e inventários completos
permanecem fora dos arquivos versionados.

## Execução Azure e correções

O grupo exclusivo recebeu a base L100/L200, rede e ambiente privados L300, duas aplicações
autenticadas e uma sonda manual. O registro de imagens ficou público autenticado, sem administrador.
As identidades de consulta e manutenção ficaram separadas; a manutenção recebeu escrita somente
no contêiner L300 e papéis proporcionais nos recursos próprios.

O plano da hospedagem apresentou três atribuições que o ARM não conseguiu calcular e cinco
defaults da busca omitidos. Tipos, principais, escopos e propriedades foram revistos antes da
aplicação. A rede teve 24 criações e uma atribuição não calculada, também qualificada.
Nenhuma exclusão inesperada foi aceita.

As duas saídas privadas da busca foram identificadas pelo destino e pela mensagem de solicitação
da rodada, aprovadas nos recursos próprios e usadas pelo indexador `private`. A referência e
o candidato tiveram quatro fontes, 24 trechos, 21 compartilhados e três de Atendimento,
com hashes e classes conferidos e zero falhas, erros ou avisos.

| Prova | Resultado observado |
| --- | --- |
| DNS interno | Blob, busca e modelos resolvem somente para endereços privados RFC 1918 |
| Coordenação na referência | Resposta documentada com fonte operacional e marcador; duas chamadas de modelo, uma de embeddings e uma busca |
| Índice candidato | 768 dimensões, mesmas fontes e contagens, sem modificar a referência de 1.536 |
| Contingência | Falha 503 injetada no transporte da sonda acionou o standby e concluiu; uso incerto preservado |
| Acesso negado | Falha 403 injetada interrompeu após uma tentativa de modelo, sem contingência |
| Cancelamento | Consulta interrompida com causa `cancelado`, sem busca posterior; embedding em voo pode continuar e seu uso fica incerto |
| Borda dos dois chats | Saúde e prontidão 200, anônimo e principal artificial 401; consulta autenticada 200 |
| Perfis externos | Atendimento, Corretor e ambos com 200; sem papel reconhecido com 403. Corretor não recebeu fonte operacional |
| SSE | Eventos de progresso, resposta verificada e fim, sem texto bruto nas etapas |
| Carga finita | Seis pedidos com concorrência três, todos com HTTP 200 e fonte operacional |
| Guarda ARM L400 | O módulo real sem recursos recusou declaração de versão incompatível com HTTP 400 `InvalidTemplate`; conexão com o template completo coberta localmente |

As falhas de 503/403 foram injetadas no transporte, não interrupções regionais reais.
Clientes externos temporários não representam login interativo de uma pessoa.
A carga pequena não estabelece capacidade máxima ou nível de serviço de produção.

### Correção comprovada após as primeiras provas

Na primeira coordenação no candidato, o cliente L400 não enviava `dimensions=768`.
O serviço devolveu 1.536 posições e a validação recusou o vetor antes da busca.
O adapter passou a enviar a dimensão reduzida, mantendo o pedido de 1.536 idêntico ao anterior.
Não houve troca de modelo, índice ou política para esconder a falha.

O cancelamento durante uma chamada síncrona de embeddings também expôs uma contagem de uso
indevidamente conhecida. O orçamento passou a identificar pedidos em voo como uso incerto.
A chamada remota já enviada pode terminar; nenhuma busca posterior é iniciada.

Seis regressões focadas cobriram essas falhas, elevando o módulo de runtime a 89 casos.
A suíte da coordenação após a correção teve **1.003 casos em 151,632 segundos:
1.002 aprovados e um ignorado no Windows**. A imagem corrigida recebeu tag nova, com a anterior
preservada. Os dois chats usaram o mesmo digest na comparação final.
O runtime foi congelado novamente antes das chamadas finais; o conjunto de 16 casos permaneceu intacto.

Os builds Linux da sonda tiveram três falhas de contexto: fixture de acesso, metadados da imagem
e arquivo de requisitos ainda ausentes. Os arquivos foram completados sem mudar as asserções.
O build completo passou com 83 casos de runtime e 24 de sanitização operacional; o build da versão
corrigida passou com **89 de runtime e 24 de sanitização operacional, sem ignorados no Linux**.
Os 24 casos são do grupo `test_operacao_l300.SanitizarWhatIfTests`, incluindo o teste
de leitura do relatório somente pelo dono em sistemas POSIX.
Isso é validação local em contêiner Linux, não execução GitHub Actions.

## Migração e retorno do índice

As definições e os metadados de ambos os índices foram lidos sem registrar conteúdo.
Dois descritores de observações reais tiveram dez conferências atendidas: nomes separados,
mesmos modelos, dimensões, fontes, classes, hashes e contagens da referência preservadas.
O helper valida o descritor; não produz essas observações.

A aplicação L400 foi apontada para o candidato de 768 dimensões, com uma consulta autenticada
documentada e as recusas de borda preservadas. O retorno a 1.536 também teve consulta autenticada
e fonte operacional. O índice candidato permaneceu disponível até o encerramento.
A aplicação convencional ficou sempre na referência de 1.536; não houve comparação convencional
no candidato nem promessa de compatibilidade automática para todo cliente anterior.

## Comparação final congelada

O [conjunto novo](../../dados/l400/avaliacao/comparacao-final-v1.json) foi criado depois do primeiro
congelamento do código, fora do corpus e das imagens. Antes das chamadas, suas referências
foram conferidas nos documentos aprovados. A correção de uma citação literal e do encoding do
conferidor ocorreu sem observar saída de modelo.

A [impressão digital final](l400-congelamento-final.json) e o
[relatório](l400-comparacao-final-v1.json) conservam o regime da versão corrigida.
Foram 32 POST, uma resposta por estratégia e caso, com ordem alternada e sem novas tentativas.
As duas aplicações usaram o mesmo digest, as mesmas fontes, perfil Atendimento e índice de referência.
Os fluxos conservam políticas de execução próprias: a coordenação limita e contabiliza tentativas,
enquanto a referência mantém os clientes anteriores. A comparação avalia essas implementações
completas; não isola estatisticamente o efeito de uma etapa ou o comportamento sob todas as falhas.

| Medição | Referência convencional | Coordenação L400 |
| --- | ---: | ---: |
| Casos conformes | 16/16 | 16/16 |
| HTTP 200 | 16 | 16 |
| Falhas, descartes ou não avaliados | 0 | 0 |
| Latência mediana | 2,69 s | 4,88 s |
| Tokens de entrada | 28.417 | 36.851 |
| Tokens de saída | 2.120 | 3.482 |
| Tokens de embeddings | 452 | 243 |

Houve zero ganhos e zero perdas de conformidade. A coordenação não demonstrou melhoria no
contrato, teve mediana maior e consumiu mais tokens de geração. Neste regime, a medição sustenta
conservar o fluxo convencional como padrão, sem impedir uso especializado da coordenação.

O primeiro pedido da referência levou 28,5 segundos e elevou seu percentil 95 a 28,52 segundos;
o da coordenação ficou em 6,20 segundos. Esse outlier e a amostra pequena impedem interpretar
a diferença como garantia de menor latência em produção.

O avaliador confere tipo, situação e invariantes da apresentação. Ele não julga fidelidade
semântica do texto nem comprova homologação. As citações passam pela política do programa,
mas isso não equivale à revisão humana integral das respostas.
O conjunto não foi repetido nem usado para ajustar o runtime depois da medição.
As credenciais externas foram revogadas no encerramento de cada execução.

## Falhas operacionais preservadas

| Ocorrência | Tratamento |
| --- | --- |
| Saída Windows do build | A CLI falhou ao escrever logs Unicode, mas o run remoto tinha `Succeeded`; digest conferido, sem reconstrução desnecessária |
| Planos ARM | Itens não calculados e defaults omitidos qualificados por tipo, escopo e propriedade, não aceitos genericamente |
| Início de Job | GET incluía `volumes`, campo não aceito pelo DTO de início; corpo corrigido para `containers`, antes de executar a sonda |
| URL HTTP interna | A saída pública Bicep estava vazia com ingresso interno; helper corrigido para o FQDN real do ARM |
| Emissão de token | Duas tentativas falharam com `AADSTS7000215` antes do chat; credenciais retiradas. Emissão posterior após espera limitada funcionou, sem alterar política ou papéis |
| Plano de custo da comparação | Dois preços sem a tarifa de embeddings foram recusados antes das chamadas; consulta de tarifa retornou 429, então todos os opcionais de custo foram retirados, sem assumir zero |
| Dimensão 768 e cancelamento | Defeitos reais corrigidos com regressões antes do conjunto final; imagem e código anteriores preservados |
| Falha local não capturada | Uma execução histórica do agente teve uma falha cujo teste não foi identificado; a passagem final registrada aprovou, sem alegar diagnóstico dessa ocorrência |
| Limpeza e papéis herdados | Primeiro processo interrompido com `ValueError`; a guarda foi corrigida para preservar atribuições fora do grupo, testada sem rede e retomada somente nos alvos próprios |
| Consulta de custo após limpeza | Primeiro pedido recebeu 429; uma nova consulta após espera limitada retornou sem linhas, sem converter indisponibilidade em custo zero |

O resumo de um recorte real de logs reconheceu 400 linhas: 389 requisições e 11 eventos
de coordenação. Saúde e prontidão foram separadas das consultas. Não houve linha desconhecida.
O recorte não inclui necessariamente os 401 interceptados pela borda e não é medição de produção.

## Isolamento público e provas posteriores

Depois da comparação e do retorno à referência, o plano de isolamento mostrou três alterações,
sem criar ou remover recursos. Oito propriedades calculadas ou defaults da busca e dos modelos
foram comparadas por caminho e qualificadas antes de aplicar.
O ARM concluiu; armazenamento, busca e modelos ficaram com `publicNetworkAccess=Disabled`.
Região, camada, réplicas, partições e as propriedades comparadas conservaram os valores anteriores.

As três chamadas externas receberam 403 usando o token do operador e papéis de dados
previamente conferidos. Busca e modelos identificaram o bloqueio público nas mensagens.
No Blob, `AuthorizationFailure` é genérico: foi qualificado com o papel no contêiner
`base-documental`, configuração `Disabled` e funcionamento de manutenção dentro da rede.
Essa prova não foi confundida com ausência de papel no contêiner L300.

Após o fechamento, a reindexação privada forçada processou quatro fontes, preservou 24 trechos,
classes e hashes, sem erros ou avisos. O chat L400 continuou respondendo com fonte operacional,
saúde/prontidão 200 e chamadas anônimas ou artificiais 401.
A identidade de consulta recebeu três 403 de dentro da rede para listar Blob, administrar índices
e administrar armazenamento, demonstrando privilégio mínimo sem depender do bloqueio externo.

## Remoção granular e limite da desconexão HTTP

Após o retorno da aplicação, o gerenciador simulou a remoção do candidato sem alterar seus
objetos. Foram removidos somente indexador, skillset, fonte e índice candidatos, com ausência
conferida e segunda execução idempotente. A referência permaneceu com 24 trechos e a mesma definição.

Uma prova adicional fechou a conexão SSE após o primeiro evento. O log correlacionado do servidor
mostrou que a borda Azure não propagou a desconexão a tempo: o cliente fechou a conexão e o workflow
terminou depois, com quatro chamadas e uma busca. Isso não é cancelamento remoto aprovado.
O resultado difere dos testes com uvicorn local e do cancelamento direto no workflow.

O reparo acrescentou um comando explícito de cancelamento autenticado.
A comparação da versão anterior continua congelada e não foi repetida para ajustar qualidade.
O comando limita o registro às execuções ativas, exige o mesmo ator autenticado
e retira o estado ao terminar. A limpeza final foi conferida separadamente depois dessas provas.

### Cancelamento explícito da versão final

O reparo acrescentou `POST /api/perguntar/cancelar` somente ao modo L400, com o identificador
servidor de uma consulta SSE ativa. O mesmo middleware confere identidade, tenant e papel;
uma chave HMAC do ator vincula a execução ao dono sem guardar os IDs em texto aberto.
Uma execução de outra identidade ou ausente recebe 404; o dono recebe 202 ao solicitar cancelamento.
Entradas inválidas, campos extras e falta de autenticação continuam sendo recusados.

O registro vive somente no processo e guarda sinal de cancelamento, assinatura do ator e validade.
A quantidade é limitada pela admissão e o estado sai ao terminar, cancelar, desconectar ou vencer.
A interface solicita o cancelamento ao servidor antes de usar `AbortController`, com limite de cinco
segundos e mensagem distinta quando apenas a espera local é interrompida.
O Bicep conserva uma réplica; essa implementação não oferece cancelamento distribuído entre réplicas.

A suíte integrada da versão de cancelamento teve **1.015 casos em 143,865 segundos:
1.014 aprovados e um ignorado no Windows**. O módulo de runtime teve 100 casos aprovados,
incluindo outro ator, expiração, duplicidade, limites do registro e servidor uvicorn real.
A imagem recebeu outra tag, sem sobrescrever os digests anteriores.
Sua construção Linux também passou em 100 testes do runtime e nos 24 de sanitização operacional,
incluindo o teste de permissões POSIX.

A comparação final continua vinculada à versão anterior que respondeu os 32 POST.
Não houve repetição do conjunto nem alteração de classificação, planejamento ou redação
para aumentar a nota depois de observar o resultado. O cancelamento final foi qualificado
por teste específico e logs reais, não por reuso daquela nota.

A prova Azure da versão final confirmou o comando: o ator Corretor recebeu 404 ao tentar cancelar
a execução de Atendimento; o dono recebeu 202, o fluxo terminou com `cancelado` e sem resposta,
e uma nova tentativa para a execução já encerrada recebeu 404.
O log correlacionado do servidor registrou `resultado=cancelado`, uma chamada de modelo e
zero buscas. O uso da chamada já enviada permaneceu incerto. O ensaio levou 3,677 segundos,
sem representar garantia de latência ou cancelamento remoto instantâneo.
O mesmo ambiente recebeu uma consulta de fumaça adicional para conferir continuidade,
com HTTP 200, resposta documentada e fonte operacional, separada do conjunto final de qualidade.
O [resumo sanitizado do cancelamento](l400-cancelamento-final.json) conserva essas provas e limites.

## Orçamento de controle

O limite anterior de US$90 foi conservado como limite de controle, não como orçamento novo.
A consulta `ActualCost` da rodada L300 continua sem linhas. Isso não prova custo zero.
Foi separada uma reserva conservadora de US$25 para L300 e US$25 para L400;
essa reserva interna não garante o valor da cobrança.

A API oficial de preços retornou medidores `Foundry Models` para `brazilsouth`, por um milhão
de tokens: US$0,75 de entrada e US$4,50 de saída para `5.4 mini` Global.
O controle não desconta entrada em cache nem usa preços Batch ou Priority.
A página HTML de preços não forneceu valores numéricos, e a primeira consulta filtrada por
`serviceName=Azure OpenAI` retornou zero medidores. A consulta foi corrigida para o nome real
do serviço; zero medidores não foi tratado como tarifa zero.

As quantidades planejadas são finitas. Modelos, embeddings, busca, imagens, DNS, rede, logs
e armazenamento podem gerar cobrança. Os temporários próprios foram removidos depois das provas,
sem manter serviços ativos à espera da fatura.

O relatório de comparação não estima custo monetário: a tarifa de embeddings não pôde ser
qualificada na consulta que recebeu 429, e o avaliador exige três tarifas ou nenhuma.
As contagens de tokens foram conservadas; nenhum valor ausente virou zero.

Depois da limpeza, a consulta `ActualCost`, filtrada somente pelo grupo L400 e seu grupo
gerenciado, recebeu 429. Uma nova consulta após 120 segundos terminou com HTTP 200,
uma página, zero linhas e sem continuação, no período de 11 de outubro de 2026 às 00:00 UTC
a 12 de outubro às 00:00 UTC. A leitura anterior vazia também foi preservada.
Valor e moeda efetivamente cobrados continuam indisponíveis; isso não comprova custo zero
nem atendimento ao teto. As reservas de controle não foram apresentadas como fatura.

## Encerramento verificado

A limpeza começou depois de conservar as provas. O primeiro processo retirou os consumidores,
os dois links de saída, os aplicativos e os 15 papéis próprios, mas terminou com `ValueError`.
A listagem ARM de atribuições também retornava papéis fora do grupo temporário.
A guarda passou a separar o escopo exato e seus descendentes antes de verificar o principal;
atribuições herdadas e de outros recursos foram preservadas, não revogadas para permitir a execução.

Um dublê sem rede conferiu preservação dos nove papéis retornados fora do grupo, recusa de
principal desconhecido dentro do grupo, conservação do inventário inicial e retomada sem
duplicar ações. O verificador final também foi testado com atribuição anterior ausente ou alterada
e com HTTP 403: esses casos não produziram aprovação. A primeira falha e o reparo permanecem
registrados em local privado.

A retomada concluiu às 08:00:36 UTC de 11 de outubro de 2026, com código 0 e 45 ações únicas
no journal. A verificação posterior, somente de leitura, aprovou às 08:02:05 UTC:

| Alvo ou verificação | Resultado observado |
| --- | --- |
| Consumidores | Duas aplicações e um Job removidos |
| Shared private links próprios | Dois removidos antes da busca e dos destinos |
| Credencial de login | Revogada antes da remoção do aplicativo |
| Aplicativos e principais de aplicação | Cinco de cada removidos e expurgados; ausentes no estado ativo e recuperável |
| Atribuições próprias | 15 revogadas; zero remanescentes no grupo e descendentes |
| Identidades gerenciadas | Três principais próprios ausentes no Microsoft Graph |
| Workspace de logs próprio | Exclusão permanente com `force=true` e ausência conferida |
| Ambientes Container Apps | Dois excluídos pelo serviço; nenhum componente do grupo gerenciado foi manipulado manualmente |
| Grupo exclusivo e grupo gerenciado | Ausentes nas listagens finais; zero recursos próprios |
| Conta de modelos | Ausente e expurgada do estado recuperável |
| Grupos e recursos anteriores | Oito grupos e 46 recursos preservados, com os mesmos IDs e tipos dos recursos inventariados |
| Atribuições anteriores | Oito do operador e 20 fora da rodada preservadas por ID, principal, definição de papel e escopo |

As oito atribuições do operador estão incluídas nas 20 fora da rodada; não são contagens aditivas.
Listagens de grupos, recursos e papéis foram percorridas até o fim. Para objetos individuais,
somente HTTP 404 foi aceito como ausência; falta de autorização não foi tratada como exclusão.
O [resumo sanitizado do encerramento](l400-encerramento-final.json) conserva contagens,
limitações e hashes das evidências privadas, sem publicar IDs ou nomes do ambiente.

## Situação final e limites

| Frente | Evidência e alcance |
| --- | --- |
| Runtime | Suíte Windows final: 1.015 casos, 1.014 aprovados e um ignorado POSIX; chamadas reais e uso incerto conferidos |
| Linux | 100 testes de runtime e 24 de sanitização operacional aprovados, incluindo permissões POSIX; não equivale à suíte completa GitHub Actions |
| Infraestrutura | Implantação, isolamento público e provas posteriores conferidos |
| Migração | Promoção e retorno conferidos, sem alterar referência |
| Comparação | V2 executada uma vez, 16/16 em ambas, sem ganho; relatório e hashes preservados |
| Carga | Seis pedidos e concorrência três conferidos; não representa capacidade máxima |
| Cancelamento | V3 conferida separadamente: outro ator 404, dono 202, execução encerrada 404, sem resposta e zero buscas posteriores |
| Encerramento | Grupo exclusivo e gerenciado ausentes, zero recursos e papéis próprios, expurgos conferidos |
| Preservação | Oito grupos, 46 recursos e atribuições anteriores conferidos após o encerramento |
| Cobrança | Consulta final sem linhas; valor e moeda indisponíveis, não zero |
| Não executado | Publicação L300/L400, Actions/OIDC, login humano, avaliação semântica integral e homologação de produção |

Os temporários da rodada não estão disponíveis para novas consultas. A reprodução depende dos
arquivos e de nova autorização de destino, orçamento e execução. Uma definição Bicep, um JSON
de observações ou um retorno de processo não substitui a leitura real dos serviços.

## Fontes e limites

- [Eventos e requisição/resposta do MAF](https://learn.microsoft.com/en-us/agent-framework/workflows/human-in-the-loop).
- [Checkpoint de workflow](https://learn.microsoft.com/en-us/agent-framework/workflows/checkpoints).
- [Cota de modelos](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/quota).
- [Dimensões e índices vetoriais](https://learn.microsoft.com/en-us/azure/search/vector-search-how-to-create-index).
- [Reconstrução de índices](https://learn.microsoft.com/en-us/azure/search/search-howto-reindex).
- [Princípios de novas tentativas](https://learn.microsoft.com/en-us/azure/architecture/patterns/retry).
- [Jobs finitos em Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/jobs).
- [Preços públicos Azure](https://prices.azure.com/api/retail/prices).
- [Listagem de atribuições e filtros de escopo](https://learn.microsoft.com/en-us/azure/role-based-access-control/role-assignments-list-rest).

Essas fontes sustentam o desenho; a rodada L400 foi encerrada com as limitações acima.
Modelos de autoria, Copilot do aluno e deployments da aplicação são escolhas independentes.
