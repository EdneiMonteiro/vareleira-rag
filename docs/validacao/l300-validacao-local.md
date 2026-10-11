# L300: registro da validação local

| Campo | Situação |
| --- | --- |
| Data de referência | 10 de outubro de 2026 |
| Base preservada | Fechamento L200, commit `5af7612` |
| Entrega | Branch local `feat/l300-operacao-protegida`, sem publicação nesta rodada |
| Escopo | Código, dados sintéticos, Bicep, workflows e sete guias; testes locais sem Azure |
| Execução externa naquele marco | Após autorização individual, criado somente um grupo exclusivo em `brazilsouth`; sem serviços, carga, papéis, federação, conexões ou Actions |
| Autoria | Código e testes por Claude Sonnet 5.5; documentação e integração por GPT-6.1 Sol, com Astra indisponível; sem Document Swarm |
| Fechamento naquele marco | Entrega local validada e roteiro operacional aprovado; execução Azure/Actions ainda pendente |

Este registro preserva o fechamento local e as autorizações recebidas até aquele marco.
O mantenedor posteriormente autorizou executar, testar e expurgar os temporários do Azure.
O [registro da rodada Azure](l300-azure-validacao.md) contém o estado posterior;
os resultados e as pendências históricos abaixo não foram convertidos em provas de nuvem.

## Artefatos e continuidade

O [roteiro L300](../roteiro-l300.md) aponta os sete desafios.
O [manifesto](../../dados/l300/permissoes-documentais.json) referencia as três fontes L100 no lugar
e acrescenta um [roteiro operacional sintético](../../dados/l300/documentos/roteiro-interno-atendimento-v1.0.md).
O mantenedor aprovou esse documento em 10 de outubro de 2026 após sua apresentação.
Ele não cria regra de seguro; a aprovação abrange somente o conteúdo, sem autorizar carga ou
alterações externas.

O chat L300 mantém o fluxo fixo L200 de recuperação, geração e política. Papéis de aplicação
determinam classes por requisição, com filtro nos modos textual, vetorial e híbrido e `preFilter`
quando há vetor. O modo documental é opcional e falso por padrão, preservando o L200.

O Bicep cria ambiente e aplicação Container Apps separados; a base L200 não recebe rede in-place.
As fases são exclusivas e usam implantação incremental. O índice e o contêiner são L300;
as definições, fontes e medições anteriores permanecem preservadas.

## Evidências conferidas pela coordenação

Os comandos abaixo foram executados em Windows com PowerShell 7 e Python da `.venv`.
O Bicep CLI escolhido pela Azure CLI, pelos testes e pelo helper é 0.48.1.
Nenhum comando desta tabela faz login ou chama a nuvem.
A tabela preserva as conferências do fechamento local, anteriores à aprovação de conteúdo
registrada abaixo.

| Comando | Resultado observado |
| --- | --- |
| `.\.venv\Scripts\python.exe --version` | Python 3.12.10 |
| `.\.venv\Scripts\python.exe -m pip check` | Código 0, sem dependências quebradas |
| `.\.venv\Scripts\python.exe scripts\atualizar_hashes_inventario.py` | Código 0; três fontes L100 sem mudanças |
| `.\.venv\Scripts\python.exe scripts\gerenciar_ingestao_l300.py --etapa validar` | Código 0; quatro fontes e classes conferidas; aviso de revisão pendente preservado |
| `.\.venv\Scripts\python.exe scripts\gerenciar_ingestao_l300.py --help` | Código 0; interface e etapas documentadas |
| `.\.venv\Scripts\python.exe scripts\operar_l300.py --etapa plano --fase todas` | Código 0; plano das três fases, sem rede |
| `.\.venv\Scripts\python.exe scripts\operar_l300.py --etapa plano --fase rede --validar-bicep` | Código 0; template compilado e lint sem avisos |
| `az bicep lint --file infra\l300.bicep` | Código 0, sem avisos |
| `az bicep build --file infra\l300.bicep --stdout` | Código 0; saída descartada, template sem parâmetros reais |
| `node --check web\app.js` | Código 0; sintaxe preservada |
| `.\.venv\Scripts\python.exe -m unittest discover -s tests -v` | Código 0; 856 casos em 113,529 s, com 855 aprovados e um ignorado |
| `git diff --check` | Código 0; nenhuma falha de espaço em branco ou patch |

Os testes das três frentes tiveram resultados focados aprovados. A última suíte relatada pelo
agente de automação antes do fechamento foi de 834 testes, com um ignorado.
A coordenação executou a candidata integrada após as correções de comportamento:
**856 casos, 855 aprovados e um ignorado**. O teste ignorado é
`test_operacao_l300.SanitizarWhatIfTests.test_o_relatorio_e_legivel_so_pelo_dono`,
que depende de permissões POSIX, próprias de sistemas Unix e indisponíveis no Windows.
A execução desse teste e da matriz Linux em Actions permanece pendente; não foi contabilizada
como aprovação.

Uma execução conjunta anterior dos módulos `test_acesso`, `test_ingestao_l300`,
`test_avaliar_chat`, `test_chat` e `test_infra_l300` teve **254 testes aprovados**.
Ela apoiou a integração e não se soma à suíte final como casos independentes.

## Correções da integração

| Correção | Motivo e verificação |
| --- | --- |
| Destinos do workflow | Validar todos os nomes, IDs e parâmetros de fase exigidos pelo Bicep antes do `what-if` |
| Credenciais separadas | Identidade de implantação por OIDC distinta do registro que autentica pessoas no chat |
| Segredo do provedor | Somente na fase `aplicacao`, em passos efêmeros e parâmetro Bicep seguro; sem argumento, arquivo público ou `GITHUB_ENV` |
| Entrada privada dos passos | IDs e nomes não podem aparecer em `env` ou `with` antes da máscara do runner |
| Rastreabilidade do chat | Incluir o novo módulo de acesso na impressão digital do código avaliado, sem modificar avaliações históricas |
| Restauração divergente | Conteúdo diferente do manifesto deve interromper a aprovação e a reaplicação de metadados, com estado parcial explícito |
| Fronteira do manifesto | Lista de carga e autorização por classe são mecanismos diferentes; o indexador lê o prefixo inteiro |
| Proteção do ambiente | Regras, restrição de branches e aprovação registrada são exigidas juntas; resposta indisponível, ilegível ou parcial bloqueia, sem fallback por atestação |
| Lint estrito | Helper recusa avisos ou saída inesperada, mesmo com código 0; padrão alinhado ao CI |

Após a suíte integrada, duas pré-condições textuais do plano foram sincronizadas com os secrets
individuais de configuração. O comportamento e o YAML permaneceram intactos;
os 13 testes existentes da classe `PlanoTests` passaram após essa atualização.

## Verificações documentais e interfaces

Os sete guias foram lidos e corrigidos contra o padrão de autoria do repositório e o guia
de estilo do mantenedor. A revisão tratou siglas no ponto de uso, ordens de execução, comandos
reais, origem dos parâmetros, estado de validação, custos, efeitos e retorno.
Os guias agora distinguem preparação local, fase de rede, retomada da carga, imagem construída
da revisão L300 e operações administrativas.

Ferramentas de conferência da sessão verificaram links, âncoras, tabelas, cercas, referências e
URLs públicas; a passagem teve código 0. O parser PowerShell 7.6.6 aceitou os 186 blocos
dos guias L100/L200/L300 sem erro de sintaxe.
A compilação estrita dos **16 arquivos Bicep** pela Azure CLI passou com zero avisos.
Uma tentativa inicial usou o executável antigo 0.47.16 no PATH e encontrou avisos BCP081;
a diferença foi identificada, sem mudar as APIs, e a conferência usou o 0.48.1 já instalado.

As CLIs foram exercitadas em **nove cenários sintéticos**: plano, intenção de simulação,
aplicação sem confirmação, isolamento sem evidência, descritor pendente antes/depois,
sanitização de what-if, recusa de relatório existente e resumo de logs. Os resultados esperados
foram conferidos por código de saída. Um primeiro fixture de log sem prefixo de servidor foi
recusado; o fixture foi corrigido para o formato real e as nove conferências passaram.
Nenhum dado sintético desses cenários foi enviado a serviço externo.

Prévia Markdown renderizada com Markdig foi inspecionada no navegador local: sete guias,
roteiro, registro e README com HTTP 200, âncoras presentes, texto visível, sem caracteres
substituídos e sem excesso de largura na página a 1440 px. Tabelas e blocos longos mantêm
rolagem horizontal própria. A política da prévia bloqueia imagens externas; os cinco badges
do README foram bloqueados de propósito e geraram avisos no console, sem envio externo.
Essa inspeção é de formato e navegação, separada da leitura editorial.
O servidor de prévia foi encerrado.

## Autorizações e atividades externas

A tabela abaixo retrata o marco local. A execução Azure posterior está no registro separado,
sem ativação de Actions ou confiança federada.

| Atividade | Situação e condição para execução |
| --- | --- |
| Aprovação do roteiro operacional novo | Concluída em 10 de outubro de 2026; estado `aprovada` no manifesto, sem alteração do conteúdo |
| Grupo de recursos L300 | Criado e conferido após confirmação de assinatura e região; vazio, sem implantação de serviços |
| Reconstrução dos recursos L200 | Provisionamento dos serviços ainda depende de autorização; grupo e região confirmados, recursos de validações anteriores removidos |
| Papéis de aplicação e login | Administrador deve autorizar e conferir atribuições, sessões e claims reais |
| Rede, endpoints e DNS | Nenhuma rede ou dependência privada implantada; testar consulta, ingestão e manutenção após autorização |
| Shared private links | Aprovação nos destinos e compatibilidade do grupo de modelos ainda dependem de prova Azure |
| Isolamento público | Somente após provas e autorização; considerar também clientes L200 e executores fora da rede |
| Workflows Actions | Ambiente, proteção de origem, runner, configuração privada e relação OIDC não ativados |
| Passagem de parâmetros segura | Nenhum `what-if` Azure L300 ou compilação de parâmetros reais realizada |
| Imagem de contêiner | Inclusão de módulos conferida por testes locais; novo build/publicação da imagem não realizado |
| Matriz Linux e permissões POSIX | Definidas no CI, não executadas nesta rodada Windows |
| Recuperação e limpeza | Grupo exclusivo vazio mantido; remoção futura exige autorização correspondente |

O helper de operação confere um descritor fornecido pelo operador, sem coletar medidas da nuvem.
Um JSON sintético aceito demonstra o validador, não acesso efetivo. Parsing de YAML e compilação
Bicep também permanecem evidências locais.

### Aprovação posterior ao fechamento local

Após apresentar o roteiro, o mantenedor respondeu «autorizo!». A confirmação corresponde ao
conteúdo de `VLAR-OP-ATD-1.0`, apresentado como primeiro item da coleta de autorizações.
O estado `revisao_real.status` passou de `pendente` para `aprovada`; o texto, a versão 1.0,
o tamanho normalizado de 2.977 bytes e o hash permaneceram intactos.

A validação inicial com aviso de revisão pendente fica preservada na tabela histórica.
A nova execução de `scripts\gerenciar_ingestao_l300.py --etapa validar` terminou com código 0,
quatro fontes aprovadas e sem aviso de revisão pendente, mantendo os hashes anteriores.
Com `PYTHONPATH` apontando para `tests`, o comando
`.\.venv\Scripts\python.exe -m unittest test_ingestao_l300 test_repositorio`
teve **42 testes aprovados**. A conferência documental sem rede e `git diff --check`
também passaram.

Essa aprovação não concede permissão de upload, provisionamento, papéis, federação ou publicação.
O teste de saída foi ajustado
pelo integrador GPT-6.1 Sol para acompanhar o estado real das fontes, sem alterar a lógica
do gerenciador.

### Criação do grupo após confirmações individuais

Em 10 de outubro de 2026, o mantenedor confirmou a assinatura de testes anteriormente indicada,
autorizou criar um grupo exclusivo e escolheu `brazilsouth`. A execução criou somente o grupo,
sem implantar os serviços do laboratório. Nome, assinatura e tenant efetivos ficam no registro
privado da sessão, fora dos parâmetros públicos do projeto.

A consulta inicial confirmou assinatura ativa e tenant do destino. O nome escolhido não existia.
Depois da criação, a leitura do Azure confirmou região `brazilsouth`, estado `Succeeded`,
**zero recursos dentro do grupo** e preservação dos **oito grupos preexistentes** nessa etapa.
Essa linha de base é a da criação atual; as medições anteriores permanecem intactas.

A primeira tentativa pela ferramenta ARM foi recusada com `InvalidAuthenticationTokenTenant`,
pois sua credencial pertencia a outro tenant. A criação ocorreu pela Azure CLI com a assinatura
explícita e a sessão já conferida, sem trocar o perfil compartilhado. Uma consulta de contagem
com expressão de query falhou; a listagem JSON sem essa expressão permitiu conferir o grupo
vazio. As falhas e a recuperação não foram tratadas como uma execução sem incidentes.

| Operação | Resultado |
| --- | --- |
| Consulta da assinatura e inventário de grupos | Destino confirmado, nome novo e linha de base registrada em local privado |
| `az group create`, com assinatura, nome, região e etiquetas explícitos | Código 0; somente grupo criado |
| `az group show` e `az resource list`, com assinatura explícita | Código 0; `Succeeded`, `brazilsouth` e lista vazia de recursos |
| Nova listagem dos grupos | Oito grupos anteriores presentes; nenhum deles substituído ou removido |

Essa autorização não inclui serviços, carga de dados, identidades, atribuições de papéis,
aprovação de conexões privadas, publicação ou Actions. Prazo de permanência e demais operações
continuam na coleta de confirmações, uma decisão por vez.

## Resultados históricos preservados

O teste HTTP L200 original permanece em 11/18; o novo teste v2 permanece em 16/18,
sem descartes e com duas divergências de classificação. Os conjuntos não foram abertos
para ajustar o L300 nem avaliados novamente nesta rodada.
As fontes L100, política de resposta, versões de modelos e resultados históricos permanecem
inalterados. Não houve homologação de negócio ou execução de nova avaliação cega.

## Custos e publicação

Os testes locais usam dublês e arquivos. A etapa externa até esse marco criou somente o grupo vazio,
sem implantar serviços cobrados do laboratório.
Uma execução futura cobra serviços reutilizados e recursos novos, incluindo endpoints, DNS,
ambiente e seus recursos gerenciados, busca, modelos, registro e logs. O ACR Basic, registro
de imagens, permanece público autenticado.

Nenhuma branch L300 foi enviada, nenhuma release L300 foi criada e o PR #1 não foi mesclado.
Publicação de workflows pode habilitar verificações remotas; a definição local permanece
separada dessa decisão.
