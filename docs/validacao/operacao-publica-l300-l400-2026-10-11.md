# Operação pública L300/L400: 11 de outubro de 2026

Registro de 11 de outubro de 2026. Documentação por GPT-6.1 Sol, com Astra
indisponível no catálogo e por escolha explícita do mantenedor.
Preserva a autoria anterior e distingue implementação, testes locais,
integração GitHub e execuções Azure históricas.

**Situação:** os pull requests (PRs, propostas de alteração) anteriores foram
mesclados. O [PR #4](https://github.com/EdneiMonteiro/vareleira-rag/pull/4)
também foi mesclado, por ordem expressa do mantenedor. Foi publicada a
[pré-release `v0.4.1-l400`](https://github.com/EdneiMonteiro/vareleira-rag/releases/tag/v0.4.1-l400),
com tag anotada no commit de merge, contendo L100 a L400 com as correções.
Uma rodada Azure foi autorizada e está pendente de execução.
**Nenhuma ferramenta pública nova foi validada no Azure.**

## Escopo e autorização

O mantenedor pediu carregar o contexto e prosseguir. Confirmou o escopo completo:
encerramento com planejador/verificador offline, sonda L300, gerador de carga
L400 e receitas dos Desafios 03 e 04 do L400. Confirmou também os modelos de
autoria e a separação das correções em um PR.

A tarefa herdada compreende:

1. Corrigir o verificador do L100, Desafio 07.
2. Completar os roteiros públicos L300/L400 sem depender dos auxiliares privados
   usados nas execuções históricas.
3. Encerrar a busca pelos textos necessários à avaliação semântica histórica.
4. Analisar e integrar os PRs #1 → #2 → #3.

As correções foram mescladas pelo PR #4, aberto a partir da branch
`fix/operacao-publica-l300-l400`, com base `main`, em 11 de outubro de 2026,
por ordem expressa do mantenedor. A integração usou commit de merge e
preservou a branch. A pré-release `v0.4.1-l400` foi publicada com tag anotada
nesse commit de merge.

A autorização inicial não incluía novas execuções Azure, login humano, ativação de
automação de implantação por GitHub Actions, confiança federada ou publicação
de novas pré-releases. Os merges acionaram automaticamente a integração
contínua (CI) já publicada; isso não autoriza executar o workflow de implantação.

Posteriormente, o mantenedor autorizou uma única rodada Azure de validação das
ferramentas públicas: planejador de encerramento, sonda L300, gerador de carga
L400 e receitas L400 D03/D04. O escopo é completo e em etapas, na ordem
encerramento → sonda L300 em rede privada → carga e receitas L400, com parada
e limpeza ao primeiro bloqueio. O teto de US$ 30 é uma estimativa para a
rodada inteira, não um custo efetivo medido.

O destino é somente a assinatura de testes privada já confirmada e a região
`brazilsouth`, em grupo exclusivo novo. A criação de identidades, credenciais
e papéis temporários foi autorizada, com remoção ao final. A linha de base
deve ser capturada antes de criar o grupo; o planejador público orienta
a limpeza final, sem executá-la. Escopo e principal devem ser conferidos
contra o inventário antes de revogar, preservando todos os objetos anteriores.

Essa autorização não inclui outros destinos, execuções além desta rodada,
login humano do chat, implantação por GitHub Actions e OpenID Connect
(OIDC, protocolo de identidade), confiança federada ou publicações além de
`v0.4.1-l400`. A execução está pendente; resultados,
falhas, retomadas e limpeza serão documentados em um registro próprio em
`docs/validacao`, criado quando a rodada terminar. Custo indisponível não
significa custo zero. Identificadores e evidências brutas permanecem privados.

Os fatos de integração e CI abaixo foram conferidos pelo coordenador.
Esta redação usou somente arquivos locais e esses fatos, sem consultas de rede
ou comandos que consultem ou alterem a nuvem.

## Integração dos PRs #1 → #2 → #3

Os três foram integrados por commit de merge, com a ponta conferida pela opção
`--match-head-commit` de `gh pr merge --merge`. As branches foram preservadas.
O repositório permite commit de merge e, na conferência do coordenador, não
tinha proteção de branch nem conjuntos de regras de proteção.

| PR | Ponta conferida e preparação | Commit de merge na principal | Resultado |
| --- | --- | --- | --- |
| [#1](https://github.com/EdneiMonteiro/vareleira-rag/pull/1) | `5af7612`; não havia CI nesse PR, pois os workflows chegam no L300 | `eec82799fb383318efb5e1c569432e154fc26cf3`, às 15:18:48Z | 596 testes locais aprovados; árvore da principal idêntica à ponta |
| [#2](https://github.com/EdneiMonteiro/vareleira-rag/pull/2) | Base trocada para `main`; merge de teste com árvore idêntica a `0093629` | `9c61c419a2a1c3f3fcaaf3484d083658819a7fb9`, às 15:21:19Z | CI na principal, [execução 38150927830](https://github.com/EdneiMonteiro/vareleira-rag/actions/runs/38150927830): quatro tarefas com sucesso |
| [#3](https://github.com/EdneiMonteiro/vareleira-rag/pull/3) | Árvore do merge idêntica à ponta `a7e4b9e` | `ab72e6e67c6017a0a28c93db15b07a26543a66b2`, às 15:23:58Z | CI na principal, [execução 38151106129](https://github.com/EdneiMonteiro/vareleira-rag/actions/runs/38151106129): quatro tarefas com sucesso |

Os horários da tabela estão em tempo universal coordenado (UTC), indicado pelo
sufixo `Z`. As quatro tarefas foram Linux/Python 3.12, Windows/Python 3.12,
Bicep e JavaScript. No PR #3, a suíte Windows teve 1.015 casos, resultado OK
e um ignorado por permissões POSIX (interface portátil de sistemas operacionais),
próprias de sistemas Unix, em cerca de 116 segundos. No Linux, os 1.015 casos passaram.

Antes do merge do PR #1, o coordenador conferiu os 596 testes em 49,6 segundos,
oito arquivos Bicep com análise estática sem avisos e compilação, usando Bicep
0.48.1, a sintaxe de `web\app.js` e a ausência de segredos.

As tags `v0.3.0-l300` e `v0.4.0-l400` continuam nos commits originais `0093629`
e `429a4ba`. **Não incluem esta rodada.** O
[registro da publicação anterior](publicacao-l300-l400.md) conserva as árvores
e as verificações daquela entrega.

Na principal estão os arquivos de workflow, isto é, as definições da automação:

- [`validar.yml`](../../.github/workflows/validar.yml): CI em runners hospedados
  (computadores que executam as tarefas), com permissão de leitura e sem
  identidade Azure.
- [`l300-implantar.yml`](../../.github/workflows/l300-implantar.yml): somente
  disparo manual, `workflow_dispatch`; exige runner próprio com o rótulo
  `vareleira-l300`, ambiente protegido, configuração em Secrets e identidade
  federada ainda inexistentes. Nunca foi executado. Nenhuma federação por
  OpenID Connect (OIDC, protocolo de identidade) foi criada.

CI aprovada não comprova implantação, conexão privada, login humano ou
homologação de produção.

## Correção do verificador L100 D07

[`verificar_identidade.py`](../../scripts/verificar_identidade.py) passou do
nome fixo para `vlr-verificacao-<16 hex>`, um nome descartável aleatório,
gerado por `secrets.token_hex(8)`: 8 bytes, ou 64 bits, de aleatoriedade.
Se coincidir com o índice informado em `--indice`, o nome é descartado e
sorteado novamente. A tentativa não cria um índice de teste.

As mensagens delimitam o resultado às cinco tentativas. Elas não comprovam
todos os acessos da identidade nem uma condição geral de privilégio mínimo.
A tentativa de exclusão continua sendo um pedido de escrita autenticado,
que exige autorização; aleatoriedade não transforma o comando em uma
consulta de leitura.

O módulo [`test_identidade`](../../tests/test_identidade.py) tem 41 testes,
cinco novos. O [registro da correção](l100-07-identidade-da-aplicacao.md#correção-posterior-do-verificador-11-de-outubro-de-2026)
preserva as execuções Azure que usaram a versão de nome fixo.
**A versão corrigida não foi reconferida no Azure.**

## Encerramento da lacuna semântica

Os avaliadores descartam o texto das respostas por projeto. A busca local
corrigida varreu 33 históricos de eventos e procurou objetos JSON (notação de
objetos JavaScript) com o conjunto exato de campos do contrato da resposta.
Localizou três corpos exatos, todos simulados em testes locais, nenhum
associado a casos finais. A primeira varredura usou um nome de campo errado;
foi refeita, e essa retomada permanece registrada.

A [análise das evidências de resposta](avaliacao-semantica-2026-10-11.md)
encerra a revisão histórica como texto irrecuperável no alcance conhecido
da busca. “Não localizado” não equivale a “inexistente”. O conteúdo das 50
respostas finais continua sem avaliação semântica integral; não há aprovação
nem medida de fidelidade inferida dessa ausência.

Nenhum conjunto final foi reexecutado. Foram preservados os gabaritos, o código,
os relatórios, os denominadores, as duas divergências do L200 e os resultados
16/18 L200 e 16/16 por estratégia L400.

## Ferramentas e roteiros públicos

As ferramentas novas foram testadas somente com dublês, substitutos controlados
dos serviços. **Nenhuma foi validada no Azure.** Os auxiliares privados das
rodadas históricas não são dependências do aluno nem provas destas versões.

| Ferramenta pública | Guias que a usam | Testes locais |
| --- | --- | --- |
| [Planejador/verificador](../../scripts/planejar_encerramento.py) e [contrato de encerramento](../../scripts/lab_encerramento.py) | [L300 D07](../../desafios/L300/07-recuperar-limpar.md) e [L400 D07](../../desafios/L400/07-recuperar-limpar.md) | [100 testes](../../tests/test_encerramento.py), com 56 mutações injetadas, todas detectadas |
| [Sonda interna L300](../../scripts/sonda_l300.py) | [L300 D04](../../desafios/L300/04-dependencias-privadas.md) e [D06](../../desafios/L300/06-conferir-operacao.md) | [18 testes](../../tests/test_sonda_l300.py) |
| [Sonda HTTP externa](../../scripts/sonda_http_externa_l300.py), para o protocolo de transferência de hipertexto (HTTP) | L300 D04 e D06 | [6 testes](../../tests/test_sonda_http_externa_l300.py) |
| [Sonda de negativas externas](../../scripts/sonda_negativas_externas_l300.py) | L300 D04 e D06 | [32 testes](../../tests/test_sonda_negativas_externas_l300.py), um ignorado no Windows |
| [Montador de contexto](../../scripts/montar_contexto_sonda_l300.py), [Dockerfile](../../infra/sonda-l300/Dockerfile) e [lista de arquivos permitidos](../../infra/sonda-l300/dockerignore) | L300 D04 e [L400 D06](../../desafios/L400/06-testar-carga-interrupcao.md) | [31 testes](../../tests/test_montar_contexto_sonda_l300.py) |
| [Gerador de carga L400](../../scripts/gerar_carga_l400.py) | L400 D06 | [101 testes](../../tests/test_gerar_carga_l400.py), com 37 mutações injetadas, todas detectadas |

O planejador de encerramento é **offline**: lê os arquivos locais e imprime
comandos `az` para revisão. Não chama o Azure nem apaga nada. Usa inventário
versão 1, com 14 tipos de passo em oito fases; etapas `capturar`, `plano`,
`conferir` e `modelo`; códigos de saída 0, 1, 3 e 4. A etapa `capturar` também
só imprime comandos: a exportação real exige execução separada pelo operador.

A sonda interna foi preparada para rodar **dentro da rede**, em um Job,
tarefa finita do Azure Container Apps. Emite a linha `L300_SONDA_RESULTADO=`
e códigos de saída de 0 a 4. As etapas de ingestão podem alterar o Azure;
`http-interno` chama o chat e consome tokens. O montador prepara uma pasta
local com 12 arquivos permitidos, mais Dockerfile e `.dockerignore`: 14 no
contexto final, sem construir ou enviar a imagem.

O gerador de carga aceita de 1 a 50 pedidos, concorrência de 1 a 8 e até
600 segundos **para enviar pedidos**. Depois pode esperar mais 10 segundos
pelos pedidos em andamento; obter a credencial gerenciada tem prazo separado.
Exige `--executar` e `--confirmo-consumo` para usar a rede. Aceita somente
endereços `*.azurecontainerapps.io` na porta 443 e ignora proxies implícitos.
Emite `L400_CARGA_RESULTADO=`. Parar localmente não cancela um pedido remoto já
enviado, que pode continuar consumindo tokens. Esta carga pequena não mede
capacidade de produção nem avalia o conteúdo das respostas.

Os guias [L400 D03](../../desafios/L400/03-operar-deployments.md) e
[D04](../../desafios/L400/04-evoluir-indice.md) agora trazem receitas públicas
de implantação por fases e de evolução, promoção e retorno do índice.
Os roteiros L300 D07/L400 D07 usam o planejador público e conferências
administrativas explícitas. Nenhuma dessas receitas foi executada ou
validada no Azure nesta rodada.

## Revisões independentes e achados corrigidos

O coordenador solicitou uma revisão independente de código por componente.
Cada revisão encontrou três problemas de gravidade média. Os nove achados
foram corrigidos, com testes de regressão, sem execução Azure.

| Componente | Achados | Correções conferidas localmente |
| --- | --- | --- |
| Encerramento | Confusão entre identificador (ID) do aplicativo e ID de objeto podia dar falsa aprovação de ausência; guarda de papéis só funcionava no PowerShell 7; faltavam testes | IDs com papéis distintos e conferência antes de remover; recusa fora do PowerShell 7; testes de regressão e mutações |
| Sonda | Código de saída diferente da linha `saida_bloqueada`; descrição “só lê” incompatível com o consumo de `http-interno`; quatro controles sem teste | Código de saída igual ao efetivamente emitido; descrição do consumo corrigida; controles cobertos |
| Carga | Destino aceitava qualquer nome de domínio; bloqueio do arquivo de perguntas falhava aberto; testes dependiam de proxy | Restrição ao domínio Container Apps; recusa por padrão diante de falhas de resolução e bloqueio por conteúdo; proxies implícitos ignorados e testes de regressão |

A recusa de perguntas de avaliação é de melhor esforço. Não detecta
paráfrases. Na imagem do Job, sem a pasta dos conjuntos de avaliação, a
comparação por conteúdo fica indisponível; quem opera deve conservar a
separação entre carga e teste final.

## Verificações realizadas

### Medições conferidas pelo coordenador

Estas contagens descrevem a árvore de trabalho antes deste fechamento
documental. A linha de base na ponta L400 era de 1.015 casos, com um ignorado
no Windows. A diferença são 288 testes dos seis módulos novos e cinco do D07;
não são novas avaliações Azure.

| O que | Comando ou método | Resultado informado |
| --- | --- | --- |
| Suíte completa da árvore de trabalho | `python -m unittest discover -s tests` | 1.308 casos, resultado OK, três ignorados; Windows, Python 3.12.10, cerca de 182 segundos |
| Links e âncoras locais, antes deste registro | Verificador local somente leitura, sem rede | 72 arquivos, 1.571 links, zero quebrados |
| Sintaxe dos exemplos dos guias | Análise em memória pelo parser do PowerShell 7.6.6, sem executar os blocos | 268 blocos, zero erros de sintaxe |
| Espaços e alterações | `git diff --check` | Sem problemas |
| Sintaxe da interface | `node --check web\app.js` | Sem problemas |

O verificador documental tem seis falsos positivos conhecidos, anteriores
à rodada: referências definidas e não citadas nos guias L400 01, 02, 03,
05, 06 e 07. Não são links quebrados nem foram tratados como falhas novas.

### Conferências locais desta redação

Foi usado o Python 3.12.10 do ambiente virtual já existente; nenhum pacote
foi instalado. As ajudas e preparações abaixo não usaram rede.

| O que | Comando exato | Resultado |
| --- | --- | --- |
| Ajuda do planejador | `python scripts\planejar_encerramento.py --help` | Código 0; etapas e limites conferidos |
| Modelo do inventário | `python scripts\planejar_encerramento.py --etapa modelo` | Código 0; modelo com marcadores, deliberadamente inválido até ser preenchido; nenhuma exportação executada |
| Preparação da sonda | `python scripts\sonda_l300.py --etapa validar` | Código 0; quatro fontes e módulos conferidos, rede bloqueada |
| Ajuda do montador | `python scripts\montar_contexto_sonda_l300.py --help` | Código 0; lista de 12 arquivos mais os dois modelos conferida |
| Ajuda do gerador | `python scripts\gerar_carga_l400.py --help` | Código 0; limites, destino e confirmações conferidos |
| Políticas do repositório | `python -m unittest discover -s tests -p test_repositorio.py` | Dez testes aprovados, sem Azure |
| Perguntas finais fora dos textos públicos | `python -m unittest discover -s tests -p test_avaliacao.py -k test_as_perguntas_de_teste_nao_aparecem_em_guias_registros_nem_instrucoes` | Um teste aprovado |
| Links e âncoras dos sete arquivos deste fechamento | `python -`, com script de conferência em memória | 135 links locais e âncoras, zero problemas |
| Espaços e alterações | `git --no-pager diff --check` | Sem problemas; os sete arquivos também foram conferidos separadamente |
| Sintaxe da interface | `node --check web\app.js` | Sem problemas |
| Identificadores e valores sensíveis | `python -`, com script de conferência em memória | Nenhum identificador globalmente único (GUID) literal, caminho privado ou padrão de credencial encontrado |

`tests\test_instrucoes.py` não existe nesta árvore e não foi executado.
O controle de exposição de perguntas finais fica no teste de `test_avaliacao`
identificado na tabela. A suíte completa não foi reexecutada pelo redator;
o coordenador a reexecutou depois do fechamento documental (próxima seção).
O verificador geral sem rede leu 73 arquivos e 1.616 links no texto, sem links
ou âncoras quebrados. Retornou código 1 somente pelos seis alertas de
referências não citadas já conhecidos, listados acima.

`--help` não faz parte da interface das três sondas. Os comandos
`python scripts\sonda_l300.py --help`,
`python scripts\sonda_http_externa_l300.py --help` e
`python scripts\sonda_negativas_externas_l300.py --help` retornaram código 1,
com `uso_invalido`, sem acessar a rede. Seus parâmetros estão descritos
nos guias e no código; esses comandos não são publicados como consulta de ajuda.

### Reexecução final e integração contínua do PR

Depois do fechamento documental, o coordenador reexecutou a suíte e conferiu a CI
do PR #4, nos commits `97b931e` e `64f878b`. Todos os números abaixo são de testes com
dublês e de verificações estáticas; nenhum envolve o Azure.

| O que | Comando ou método | Resultado |
| --- | --- | --- |
| Suíte completa, ambiente virtual do projeto | `.\.venv\Scripts\python.exe -m unittest discover -s tests` | 1.308 casos, resultado OK, três ignorados; Windows, Python 3.12.10, cerca de 184 segundos |
| Dependências instaladas | `.\.venv\Scripts\python.exe -m pip check` | Nenhum requisito quebrado |
| Comandos offline das ferramentas novas | `python scripts\planejar_encerramento.py --help`, `--etapa modelo`, `python scripts\sonda_l300.py --etapa validar`, `python scripts\montar_contexto_sonda_l300.py --help` e `python scripts\gerar_carga_l400.py --help` | Código de saída 0 nos cinco, sem rede |
| CI do PR #4, commit `97b931e`, [execução 38163879531](https://github.com/EdneiMonteiro/vareleira-rag/actions/runs/38163879531), evento `pull_request` | Quatro tarefas do workflow `Validar` | Todas com sucesso: Windows com 1.308 casos, OK, três ignorados; Linux com 1.304 casos, OK, três ignorados; Bicep e JavaScript aprovados |
| CI do PR #4, commit `64f878b`, [execução 38164343920](https://github.com/EdneiMonteiro/vareleira-rag/actions/runs/38164343920), evento `pull_request` | Quatro tarefas do workflow `Validar` | Todas com sucesso: Windows com 1.308 casos, OK, três ignorados; Linux com 1.304 casos, OK, três ignorados; Bicep e JavaScript aprovados |

O Linux conta quatro casos a menos que o Windows porque a classe de testes do Windows
PowerShell 5.1 se ignora por inteiro quando o `powershell.exe` não existe: esses quatro
casos só rodam no Windows. Com o Python do sistema, sem os pacotes do projeto, o mesmo
comando falha por dependências ausentes (`azure`); use o ambiente virtual preparado com
os requisitos do projeto.

Esta seção registra as execuções dos commits `97b931e` e `64f878b`.
Não inclui uma execução de CI da principal no commit de merge do PR #4.

## O que não foi validado e limitações

1. **Nenhuma ferramenta pública nova foi validada no Azure.** Dublês,
   análise sintática e ajuda offline não comprovam identidade, conectividade,
   carga, consumo, expurgo ou preservação reais dessas versões.
2. O comportamento de `az containerapp job start` com `--env-vars`,
   `--command` e `--args`, e de `az containerapp job execution`, não foi
   validado no Azure nas versões atuais. A ajuda offline confirma somente
   a interface de argumentos.
3. A leitura dos logs do Job pela interface de linha de comando (CLI) continua
   pendente. Os guias descrevem portal e Log Analytics, com a tabela
   `ContainerAppConsoleLogs_CL`; a coleta e sua associação à execução
   precisam ser conferidas no destino autorizado.
4. A linha de base do encerramento precisa ser capturada **antes** de criar
   o grupo temporário. Um identificador globalmente único (GUID) errado,
   mas bem formado e distinto, não é detectável offline. Por isso o roteiro
   confere presença e identidade antes de apagar, com IDs de objeto separados
   dos IDs de aplicativo.
5. Os blocos do encerramento exigem preparação na mesma sessão do PowerShell 7.
   Os testes com `az` falso no Windows PowerShell 5.1 comprovam a recusa,
   não compatibilidade para executar a limpeza nesse ambiente.
6. As falhas e retomadas das limpezas históricas permanecem nos registros
   [L300](l300-azure-validacao.md) e [L400](l400-validacao.md#encerramento-verificado).
   A consulta de custo sem linhas não significa custo zero nem comprova
   atendimento ao orçamento.
7. Login humano, implantação por Actions/OIDC e homologação continuam não
   executados. A CI na principal não testa esses caminhos. As pré-releases
   `v0.3.0-l300` e `v0.4.0-l400` não contêm as correções atuais;
   `v0.4.1-l400` contém essas correções, ainda sem validação Azure.
8. Os textos finais são tratados como irrecuperáveis no alcance da busca;
   os resultados de contrato não demonstram fidelidade semântica.
9. O cancelamento L400 continua com registro de execuções ativas em memória,
   por processo e com uma réplica. Aumentar réplicas exige redesenho e testes.
   A simples desconexão não comprova interrupção através da borda Azure.
10. [`infra\l300.bicep`](../../infra/l300.bicep) conserva
    `tipoPrincipalCarga = 'User'`; o [arquivo de parâmetros](../../infra/levels/l300.bicepparam)
    não expõe essa opção. Para identidade gerenciada de manutenção, o L300 D04
    manda usar cópia privada com `ServicePrincipal`. Expor a opção por variável
    é melhoria futura sugerida, não implementada.

## Decisões e pendências do mantenedor

| Decisão | Limite atual |
| --- | --- |
| Mesclar o PR #4 | Decidido e concluído em 11 de outubro de 2026, por ordem expressa; commit de merge, branch preservada |
| Pré-releases corrigidas | Publicada somente `v0.4.1-l400`, com tag anotada no merge do PR #4. `v0.3.1-l300` e `v0.1.2-l100` não foram publicadas; separar a árvore corrigida exige reconstrução e novas verificações, pelas dependências L400 descritas abaixo |
| Rodada Azure das ferramentas públicas | Autorizada, pendente de execução: uma única rodada completa em etapas, na assinatura de testes privada e em `brazilsouth`, com grupo exclusivo novo e teto estimado de US$ 30 para toda a rodada; identidades, credenciais e papéis temporários autorizados, com remoção ao final e parada e limpeza ao primeiro bloqueio; demais limites na seção de escopo |
| Expor `tipoPrincipalCarga` por variável | Aguardando decisão, sem implementação. Define o tipo da identidade que recebe o papel de carga no Blob, o armazenamento de objetos: `User` para pessoa ou `ServicePrincipal` para identidade de aplicativo/gerenciada. A manutenção do L300 D04 exige `ServicePrincipal`; hoje o guia requer cópia privada de parâmetros |

O [montador do contexto da sonda](../../scripts/montar_contexto_sonda_l300.py)
inclui `scripts\gerar_carga_l400.py` na lista fechada de 12 arquivos.
O [guia L300 D04](../../desafios/L300/04-dependencias-privadas.md) também aponta
para o L400 D06. Por isso os guias corrigidos e a imagem da sonda dependem da
árvore L400. Uma entrega separada, como `v0.3.1-l300` ou `v0.1.2-l100`,
exigiria reconstrução e novas verificações; o mantenedor pode pedi-la depois.

## Autoria

| Papel nesta rodada | Responsável e alcance |
| --- | --- |
| Código e testes | Claude Sonnet 5.5, via subagentes, coordenados por Claude Sonnet 5.5 |
| Documentação | GPT-6.1 Sol, via subagentes, com Astra indisponível no catálogo; escolha explícita do mantenedor |
| Revisão independente de código | Agentes de revisão de código, um por componente; achados e correções informados pelo coordenador |
| Coordenação e revisão dos diffs de documentação | Claude Sonnet 5.5; fechamento da revisão a cargo do coordenador |
| Atualização de estado, publicação e autorização Azure | Redigida por GPT-6.1 Sol e revisada pelo coordenador Claude Sonnet 5.5; autoria anterior preservada |

As autorias e revisões anteriores permanecem nos guias e nos registros
históricos. Modelos de autoria e revisão não configuram o modelo do aluno
no Copilot nem os deployments de geração e embeddings da aplicação.
