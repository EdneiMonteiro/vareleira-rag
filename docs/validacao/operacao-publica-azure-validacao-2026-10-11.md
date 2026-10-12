# Validação Azure das ferramentas públicas: 11 de outubro de 2026

Registro da rodada executada pelo coordenador, com documentação por GPT-6.1 Sol,
com Astra indisponível. As contagens abaixo vêm dos fatos conferidos pelo coordenador.
Não contém identificadores, nomes de recursos, endereços ou evidências brutas do destino.

## Situação

| Etapa | Resultado e alcance |
| --- | --- |
| Planejador no grupo mínimo | Aprovada após corrigir a leitura de atribuições herdadas; 13 passos com prova de ausência |
| Base L300 e sonda pública | Exercitadas com falhas e retomadas preservadas; ingestão, consulta interna e ciclo operacional observados |
| L400: contingência, carga e índice | Prova operacional parcial aprovada com bloqueios, falha de host e retomadas; não é avaliação semântica |
| Encerramento completo | Aprovado: 28 passos, 12 critérios atendidos, zero reprovados, zero pendentes e um não aplicável |
| Preservação e custo | Oito grupos, 46 recursos e 20 atribuições presentes na listagem final; custo efetivo indisponível |

**Limite central:** os serviços de dados ainda tinham acesso público habilitado.
O caminho privado observado **não comprova funcionamento isolado**. Não houve login humano,
ingresso externo, implantação federada ou homologação de produção.

## Escopo e autorização

O mantenedor autorizou uma rodada completa em etapas, no destino privado de testes e na
região anteriormente confirmados, em grupo exclusivo novo. O teto de US$ 30 foi uma
**estimativa para a rodada inteira**, não custo medido. Foram autorizadas identidades,
credenciais e atribuições temporárias, com remoção ao final.

Ao pedir **“Proceda com o que for necessário para finalizar!”**, o mantenedor delegou
o fechamento em modo autônomo. O coordenador interpretou essa delegação como autorização
para corrigir os achados, mesclar os pull requests (PRs, propostas de alteração)
[#5](https://github.com/EdneiMonteiro/vareleira-rag/pull/5) e
[#6](https://github.com/EdneiMonteiro/vareleira-rag/pull/6) e publicar a pré-release
[`v0.4.2-l400`](https://github.com/EdneiMonteiro/vareleira-rag/releases/tag/v0.4.2-l400).
Os PRs foram mesclados e a pré-release foi publicada por essa delegação.

Essa interpretação **não incluiu** outros destinos, repetição da rodada, fase `isolar`,
login humano do chat, implantação GitHub Actions por OpenID Connect (OIDC, protocolo de
identidade) ou criação de confiança federada. A integração contínua (CI) do repositório
é distinta desse workflow de implantação. O registro de execução não concede nova permissão.

## Ambiente e ferramentas

| Componente | Versão ou configuração conferida |
| --- | --- |
| Azure CLI, interface de linha de comando | 2.89.0 de 64 bits, em ambiente virtual próprio; extensão `containerapp` 1.3.0b5 |
| Executor | Job, tarefa finita do Azure Container Apps, dentro da rede privada; 0,25 vCPU, fração de núcleo virtual, 0,5 GiB, gibibyte de memória, e limite de réplica de 900 segundos |
| Identidades do Job | Identidades gerenciadas de manutenção e do chat; download da imagem pela manutenção |
| Sonda e gerador | Código do merge do PR #4, `cd9c95a` |
| Planejador com correção de herdadas | Merge do PR #5, `d881a4e` |
| Imagens do chat e da sonda | Construídas da árvore `fe324f8`, com tag de mesmo nome |
| Correção do comando de construção | Montador no commit `f0bc6a8`, incluído no PR #6 |

Os arquivos públicos usados são o
[planejador](../../scripts/planejar_encerramento.py),
[contrato de encerramento](../../scripts/lab_encerramento.py),
[montador](../../scripts/montar_contexto_sonda_l300.py),
[sonda](../../scripts/sonda_l300.py),
[gerador de carga](../../scripts/gerar_carga_l400.py) e
[gerenciador de ingestão](../../scripts/gerenciar_ingestao_l300.py).
Os guias afetados são L300
[D03](../../desafios/L300/03-filtrar-acesso.md),
[D04](../../desafios/L300/04-dependencias-privadas.md),
[D06](../../desafios/L300/06-conferir-operacao.md),
[D07](../../desafios/L300/07-recuperar-limpar.md) e L400
[D03](../../desafios/L400/03-operar-deployments.md),
[D04](../../desafios/L400/04-evoluir-indice.md),
[D06](../../desafios/L400/06-testar-carga-interrupcao.md) e
[D07](../../desafios/L400/07-recuperar-limpar.md).

## Resultados por etapa

### 1. Planejador no grupo mínimo

A linha de base foi capturada **antes** de criar o grupo: oito grupos, 46 recursos e
20 atribuições, sendo três herdadas de grupo de gerenciamento ou da raiz do tenant,
diretório de identidades.

| Conferência | Resultado observado |
| --- | --- |
| Composição do grupo mínimo | Identidade gerenciada, armazenamento, cofre de chaves, workspace de logs, conta de modelos, ambiente Container Apps, Job, aplicativo e principal de serviço Entra, uma credencial e duas atribuições de papel |
| Presença prévia | Nove presentes e quatro ausentes, estes últimos os expurgos esperados |
| Execução | 13 passos, cada um com prova de ausência; ambiente em `ScheduledForDelete`, exclusão agendada, por cerca de 30 minutos |
| Conferência final | Aprovada: 12 atendidos, zero reprovados, zero pendentes e um não aplicável; oito grupos ao final |
| Correção necessária | O validador recusou as herdadas com código 1. Após o PR #5, aceitou, ignorou e contou esses itens; arquivos reais conferidos sem editar os instantâneos |
| Provas locais da correção | Módulo de encerramento passou de 100 para 111 testes; 48 mutações detectadas |

### 2. Base L300, construção e sonda

Nova linha de base foi capturada antes do grupo exclusivo: oito grupos, 46 recursos
e 20 atribuições. As cotas consultadas foram zero de 1.000 para embeddings e
500 de 1.000 para `gpt-5.4-mini`; isso é leitura de cota, não prova de disponibilidade futura.
Embeddings são representações vetoriais do texto.

| Operação | Resultado observado |
| --- | --- |
| Reconstrução L100/L200 | L100 com 11 criações em 77 segundos; base L200 em 224 segundos |
| Manutenção e imagem do chat | Identidade de manutenção e quatro papéis; imagem do chat construída em 67 segundos |
| Plano da fase `rede` | 24 `Create`, oito `Ignore` e um `Unsupported` qualificado |
| Falhas da fase `rede` | Duas tentativas: `OperationResultNotFound`, depois `InvalidResponseFromPrivateLinkService`, do provedor CognitiveServices, com conta de modelos saudável em `Succeeded` |
| Recuperação da rede | Exclusão somente do endpoint privado próprio com falha e reaplicação da mesma fase incremental; terceira tentativa concluída em cerca de 440 segundos |
| Conexões da busca | Duas conexões privadas compartilhadas, shared private links (SPLs), pendentes: armazenamento e modelos. Aprovação no destino; estados `Approved` e `Succeeded`. As conexões dos endpoints do chat não exigiram aprovação |
| Papéis Entra | `Vareleira.Atendimento` e `Vareleira.Corretor`, exigência `appRoleAssignmentRequired=true` e Atendimento atribuído à identidade gerenciada do chat antes do primeiro token |
| Construção da sonda | Comando antigo selecionava o Dockerfile pela pasta atual ou não o encontrava. Entrar no contexto e usar `--no-logs .` corrigiu o caminho; 14 passos em cerca de 66 segundos |
| Evidência da imagem | Log com `ARG IMAGEM_CHAT`, `COPY scripts/sonda_l300.py` e `validar` aprovado |
| Execução e coleta | Job criado no ambiente L300, com duas identidades; lista completa em `job start --env-vars` aplicou a etapa pedida. Python com argumento único Base64 também funcionou |
| Logs | API, interface de programação, do Log Analytics funcionou com KQL, linguagem de consultas Kusto; tabela `ContainerAppConsoleLogs_CL`, colunas `TimeGenerated`, `Log_s`, `ContainerJobName_s` e `ContainerGroupName_s`. Ingestão de segundos a poucos minutos |

| Etapa da sonda | Resultado observado |
| --- | --- |
| `dns` | Código 0; um endereço de uso privado RFC 1918 para Blob, busca e modelos, respectivamente. RFC é a série de especificações Request for Comments |
| `conferir`/`resumo` antes do pipeline | Código 3 e resposta 404 da busca; ausência esperada preservada |
| `carregar`/`criar` | Quatro documentos criados e quatro objetos de busca |
| `executar` | Quatro itens processados; 24 trechos, 21 compartilhados e três de Atendimento |
| `conferir`/`resumo` após a criação | Nove verificações atendidas na conferência; etapas aprovadas com código 0 |
| `acesso` | Nove consultas à busca, cinco embeddings e uma geração; filtros por perfil e quatro recusas sem chamar o modelo |
| Fase `aplicacao` | 72 segundos, aplicativo interno, uma réplica e autenticação integrada EasyAuth com `Return401` |
| `http-interno` | HTTP, protocolo de transferência de hipertexto: saúde, prontidão e consulta autenticada com 200; anônimo e principal forjado com 401; resposta documentada com marcador operacional |
| `negativas-mi` | ARM, Azure Resource Manager, serviço de administração, Blob e busca recusados com 403 para a identidade do chat |

### 3. Ciclo de exclusão e restauração

| Ordem | Observação |
| --- | --- |
| `excluir` | Um blob excluído |
| `executar` | 21 trechos; zero da fonte operacional sintética |
| `conferir` com ausência declarada | Dez verificações atendidas, incluindo ausência da fonte |
| `restaurar` | Um blob restaurado |
| `executar` novamente | 24 trechos |
| `conferir` depois de restaurar | Nove verificações atendidas |

Cada etapa levou aproximadamente um a 12 segundos dentro do Job.
O ciclo alterou a cópia operacional, não criou regras de seguro nem reexecutou avaliações finais.

### 4. L400 D03: contingência e aplicação

| Operação | Resultado observado |
| --- | --- |
| Contingência | What-if com um `Create`; aplicação em 50 segundos |
| Deployments, instâncias nomeadas de modelo | `embeddings`, `geracao` e `geracao-contingencia` em `Succeeded`, com capacidades lidas de 30, 50 e dez. Geração e contingência conservaram `gpt-5.4-mini`, versão `2026-03-17` |
| Plano de aplicação | Dois `Create`, 28 `Ignore` e zero `Modify` |
| Bloqueio do guia | Filtro encontrou dois aplicativos, criação L400 e referência L300 como `Ignore`; a trava `Count -ne 1` impediu continuar. Corrigida a seleção para `Create`/`Modify` |
| Retomada | Aplicação em 77 segundos, coordenação habilitada, contingência configurada, ingresso interno e EasyAuth; referência L300 com mesma revisão e ingresso interno |
| Endereço | FQDN, nome completo de domínio, interno lido do ARM, com `.internal.`; host montado sem esse trecho respondia 404 na borda |
| Retornos do login | L300 e L400 cadastrados no formato externo; não testados com pessoa. Atualizar `--web-redirect-uris` substitui a lista |
| Credenciais | Recriadas a cada aplicação e acumuladas; as seis foram retiradas no encerramento completo |
| `http-interno` L400 | Saúde, prontidão e consulta autenticada com 200 e resposta documentada; anônimo e principal forjado com 401 |

### 5. L400 D06: falha de host e cargas pequenas

| Execução | Resultado observado |
| --- | --- |
| Tentativa 1, sem `.internal.` | Cinco envios, cinco HTTP 404 da borda, latências de 21 a 46 milissegundos; parada por três falhas seguidas, código 3, sem consumo de modelos. Falha da operação, não do chat |
| Rodada 1: seis pedidos, concorrência três | Seis envios, seis HTTP 200, zero divergentes, código 0 e 41,9 segundos; cinco `documentada` e uma `sem_evidencia` |
| Latências da rodada 1 | Mínima 4,7 segundos, mediana 6,2 segundos e p95, percentil 95, de 36,2 segundos; amostra pequena com partida a frio |
| Rodada 2: 12 pedidos, concorrência oito | 12 envios, quatro `ok` com 200 e oito `ocupado` com 429; zero divergentes, código 0 e 6,2 segundos. Limite de admissão quatro observado |

| Uso informado | Embeddings | Entrada de geração | Raciocínio | Saída de geração |
| --- | --- | --- | --- | --- |
| Rodada 1 | 115 tokens | 13.030 tokens | 535 tokens | 1.270 tokens |
| Rodada 2, quatro `ok` | 74 tokens | 10.310 tokens | 410 tokens | 916 tokens |

Tokens são unidades contabilizadas pelos modelos. As recusas da segunda rodada não
informaram uso; isso não significa custo zero. A carga finita não mede capacidade nem
percentis de produção. `ok` confere o contrato, não fidelidade semântica.

### 6. L400 D04: candidato, promoção e retorno

| Operação | Resultado observado |
| --- | --- |
| Caminho de ingestão | Gerenciador dentro do Job, com identidade de manutenção e argumento único Base64 |
| Referência antes | Conferência aprovada, 24 trechos: Condições Gerais 11, perguntas frequentes cinco, Glossário cinco e roteiro operacional três |
| Candidato de 768 dimensões | Plano com quatro objetos a criar, quatro criados, quatro processados, zero falhas em cerca de dois segundos; conferência aprovada com as mesmas contagens por documento |
| Referência depois | Conferência aprovada e preservada |
| Descritor local | Dez atendidos, zero reprovados; `origem_do_descritor=operador`, `evidencia_azure=false`. O conferidor não coleta Azure |
| Promoção | Dois `Modify`; sanitizador bloqueou com código 3 até revisar cinco propriedades removidas no aplicativo e uma na autenticação |
| Deltas revisados | Três expressões ARM não resolvidas e **11 deltas de ordem** das três sondas; alvo real limitado a índice e dimensão |
| Aplicação da promoção | 64 segundos, revisão pronta, demais variáveis idênticas; imagem, registro, conjunto de sondas, escala, identidade e ingresso conferidos; L300 preservada |
| Prova no candidato | Quatro pedidos, concorrência dois: quatro 200, zero divergentes; três `documentada` e uma `sem_evidencia` |
| Retorno | Quatro propriedades removidas no aplicativo e uma na autenticação, pois `maxInactiveRevisions` já estava ausente; qualificação revista, aplicação em 64 segundos |
| Prova após retornar | Referência com 1.536 dimensões, quatro 200, três `documentada` e uma `sem_evidencia`; candidato preservado |

As cinco remoções da promoção foram `ingress.exposedPort`, `ingress.traffic`,
`maxInactiveRevisions`, `scale.cooldownPeriod` e `scale.pollingInterval`; na autenticação,
`isAutoProvisioned`. No retorno, o aplicativo teve quatro, sem `maxInactiveRevisions`.
As quantidades exatas foram cinco/um e quatro/um, após revisão humana.
Isso não transforma a qualificação do sanitizador em aprovação automática.

## Defeitos encontrados e destino

A numeração só organiza esta tabela. Advertências de roteiro são separadas de defeitos de código.

| Nº | Defeito ou achado | Natureza | Destino da correção |
| --- | --- | --- | --- |
| 1 | Herdadas recusadas na captura | Código | PR #5; [contrato](../../scripts/lab_encerramento.py), [planejador](../../scripts/planejar_encerramento.py) e L300 D07. Aceitas, ignoradas e contadas; exportação de outra assinatura continua recusada |
| 2 | Construção da sonda escolhia Dockerfile pela pasta atual | Código e guia | `f0bc6a8`, [montador](../../scripts/montar_contexto_sonda_l300.py) e L300 D04; entrar no contexto, usar `--no-logs .` e ler logs depois |
| 3 | Trava com dois aplicativos no what-if | Guia | L400 D03: selecionar só `Create`/`Modify`, preservando a referência como `Ignore` |
| 4 | Nome raiz de implantação coincidente com módulo | Advertência de guia | L400 D03/D04: prefixo próprio, distinto dos módulos. A colisão (`DeploymentActive`) já constava no [registro Azure L300](l300-azure-validacao.md) histórico; nesta rodada foi evitada, sem ocorrência nova |
| 5 | Host interno montado sem `.internal.` | Guia | L400 D03/D04/D06 e L300 D04: ler FQDN do ARM; tentativa 404 preservada |
| 6 | Duas falhas transitórias do endpoint dos modelos | Ambiente/serviço | L300 D04: conta saudável, remoção só do endpoint próprio com falha e mesma fase incremental após novo plano |
| 7 | Remoções sem qualificação bloqueavam promoção | Revisão operacional e guia | L400 D04: revisão de cada delta e qualificação exata por tipo; cinco/um na promoção e quatro/um no retorno |
| 8 | CLI de 32 bits não instalava `containerapp` | Ambiente | CLI de 64 bits em ambiente virtual próprio e pasta própria de extensões; L300 D04 e remissões |
| 9 | `VARELEIRA_ID_OBJETO_CARGA` reutilizada entre L100 e L300 | Advertência de guia | L300 D04: conferir principal, redefinir/limpar entre fases e usar cópia privada com `ServicePrincipal` |
| 10 | Atualização de retornos substitui a lista | Advertência de guia | L400 D03: conservar retornos L300/L400; cadastro externo não foi prova de login humano |
| 11 | Mensagem de exclusão do ambiente subestimava a espera | Código e guias | [Contrato do planejador](../../scripts/lab_encerramento.py), L300/L400 D07: cerca de 30 minutos; 111 testes do módulo aprovados |
| 12 | Roteiro sem caminho executável na rede para o candidato | Guia | L400 D04: gerenciador dentro do Job, argumento Base64 e console filtrado pela execução no Log Analytics |

## Falhas e retomadas

1. **Primeira falha de `rede`:** `OperationResultNotFound` no endpoint dos modelos,
   com a conta saudável. A tentativa ficou registrada antes da seguinte.
2. **Segunda falha de `rede`:** `InvalidResponseFromPrivateLinkService`. Nova conferência
   e recuperação restrita ao endpoint próprio com falha e à mesma fase incremental;
   terceira tentativa concluída, sem remover a conta.
3. **Construção da sonda:** Dockerfile resolvido pela pasta atual. Corrigido o comando
   para entrar no contexto, construir com `.` e recuperar o log em UTF-8, codificação Unicode.
4. **Conferências iniciais da ingestão:** `conferir`/`resumo` deram código 3 e 404 sem
   pipeline. A ausência não foi descartada; carga e criação precederam novas conferências.
5. **Trava L400 D03:** `Count -ne 1` bloqueou o plano com criação L400 e referência ignorada.
   Corrigido o filtro, sem retirar a referência da revisão; implantação retomada.
6. **Tentativa 1 de carga:** cinco 404 por host incorreto. A falha foi contada; FQDN interno
   lido do ARM antes das cargas seguintes. Nenhuma resposta substituiu a tentativa anterior.
7. **Sanitizador na promoção:** código 3 por remoções não qualificadas. Deltas revisados
   um a um e qualificação exata registrada; no retorno, a contagem foi relida e mudou.
8. **Passo 25 da limpeza:** verificação ainda `presente` após exclusão assíncrona.
   Foi uma parada esperada, não falha de exclusão. Iniciado o passo 26 em paralelo;
   repetidas somente as leituras até os dois ambientes ficarem ausentes.

Nenhum bloqueio administrativo foi removido e nada foi recriado durante a limpeza final.
As retomadas não apagam a origem de cada bloqueio nem autorizam repetir a rodada.

## Limpeza e linha de base

O inventário próprio foi montado por leituras: 29 recursos, três principais,
oito atribuições próprias, um aplicativo Entra com seu principal de serviço e seis
credenciais, dois shared private links e um expurgo de conta de modelos.
Os 29 recursos incluíam dois aplicativos Container Apps, um Job, dois ambientes,
modelos, registro, duas identidades, três interfaces de rede, cinco zonas DNS e cinco
vínculos, três endpoints, rede virtual, workspace, busca e armazenamento.
DNS é o sistema de nomes de domínio.

O plano teve 28 passos, 26 irreversíveis e dois reversíveis. A presença prévia foi
25 presentes e três ausentes, os expurgos previstos. **Cada passo teve prova de ausência.**

| Passos | Objetos encerrados |
| --- | --- |
| 1–3 | Dois aplicativos Container Apps e um Job |
| 4–5 | Dois shared private links; primeiro exercício real dessa fase do planejador público |
| 6–11 | Seis credenciais Entra |
| 12–15 | Principal de serviço e aplicativo, com expurgos separados |
| 16–23 | Oito atribuições de papel, por ID, identificador, exato |
| 24 | Workspace de logs, com `--force` |
| 25–26 | Dois ambientes; ausência observada após cerca de 23 minutos, com leitura a cada aproximadamente 90 segundos |
| 27 | Grupo exclusivo |
| 28 | Expurgo da conta de modelos |

O grupo gerenciado desapareceu com o ambiente e **nunca foi manipulado**. Nenhum passo
de exclusão falhou; a espera do passo 25 permaneceu registrada.

| Conferência final | Resultado |
| --- | --- |
| Presença | Sete ausentes na captura nova |
| Critérios | Aprovado: 12 atendidos, zero reprovados, zero pendentes e um não aplicável |
| Não aplicável | Cofre de chaves: não existia no inventário desta segunda execução |
| Linha de base | Oito grupos, 46 recursos e 17 atribuições comparadas; três herdadas ignoradas e contadas antes/depois |
| Leitura direta final | Oito grupos, 46 recursos e 20 atribuições, incluindo herdadas; grupo exclusivo, grupos gerenciados temporários e aplicativo de login ausentes |
| Instantâneos | Exportações novas, de momentos distintos, idênticas byte a byte às anteriores; aviso de igualdade esperado, não reutilização do mesmo arquivo |
| Duração do laboratório completo | Aproximadamente duas horas e sete minutos |
| Limpeza local | CLI de 64 bits e pasta temporária de extensões retiradas; evidências privadas não versionadas |

As herdadas não são comparadas pela ferramenta: uma mudança nelas não seria detectada
por esse critério. A conferência mede arquivos exportados, não todas as configurações,
consumidores ou custo. O cofre foi exercitado no grupo mínimo, não nesta limpeza completa.

## Custo

A consulta de Cost Management do grupo, durante e depois do encerramento, retornou
**zero linhas**. Resultado registrado: **indisponível**, não custo zero.
O coordenador estimou poucos dólares e considerou essa estimativa abaixo de US$ 30;
isso **não é medição, fatura nem comprovação de atendimento ao teto**.
A estimativa preliminar considerou serviços ligados por cerca de três horas; a duração
observada do laboratório completo foi aproximadamente duas horas e sete minutos.

## O que não foi executado

- Fase `isolar` e todas as provas pós-isolamento; os dados continuavam com acesso público.
- Negativas externas L300 e nova medição do descritor L300/helper HTTP externo.
- Login humano, teste dos retornos por pessoa e ingresso externo.
- Implantação GitHub Actions/OIDC, confiança federada e matriz Linux local.
- Nova avaliação semântica, homologação ou repetição dos conjuntos finais.
- Encerramento após `isolar` e recuperação de `LockedSPLResourceFound` com o planejador
  público nesta rodada; o conflito histórico permanece em seu registro anterior.
- Cofre de chaves na segunda execução de encerramento.
- Exposição de `tipoPrincipalCarga` por variável no arquivo de parâmetros: não implementada;
  foi usada cópia privada. O coordenador adiou a mudança por delegação (ver as decisões
  abaixo); só será reaberta por pedido do mantenedor.
- Medição de custo efetivo.

O verificador L100 D07 corrigido e as ferramentas HTTP externas não recebem uma nova
validação Azure por associação com as provas da sonda interna.

## Decisões do coordenador no modo autônomo

O coordenador tratou os bloqueios dentro dos alvos autorizados, conservou as tentativas,
usou o planejador público no encerramento e limitou a prova ao caminho privado sem isolar.
Interpretou a delegação final para mesclar PR #5 e PR #6 e publicar `v0.4.2-l400`.

Ao fim, o mantenedor reforçou: “Tome todas as decisões para finalizar. Vou dormir.”
Dentro desse limite, o coordenador decidiu:

- **Não abrir outra rodada Azure** para `isolar`. Repetir a execução, recriar o ambiente e
  fechar o acesso público dos dados exigem autorização própria, e a delegação era para
  finalizar, não para ampliar a prova.
- **Não implementar `tipoPrincipalCarga` por variável.** A mudança não é necessária para
  concluir, alteraria a infraestrutura sem validação Azure e o guia segue com a cópia privada
  de parâmetros.
- **Não executar** login humano, implantação GitHub Actions/OIDC, confiança federada nem nova
  avaliação semântica, que exigem pessoas, configurações do repositório ou autorização própria.

Esses itens permanecem como pendências recomendadas e só são reabertos por pedido do mantenedor.

A pré-release inclui correções e este registro; `v0.4.1-l400` e as anteriores permanecem
intactas e não contêm esta evidência Azure. Versões corrigidas separadas L300/L100 não
foram publicadas: o contexto da sonda e os guias corrigidos dependem da árvore L400.
Publicar não concede autorização para recriar o ambiente ou ampliar essa prova parcial.

## Autoria

Texto por GPT-6.1 Sol, com Astra indisponível, a partir dos fatos do coordenador.
Código e testes por Claude Sonnet 5.5; coordenação e revisão pelo coordenador.
As autorias históricas permanecem nos guias e registros anteriores.
O modelo de autoria não configura o modelo escolhido no Copilot nem os deployments Azure.
