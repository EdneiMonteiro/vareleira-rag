# L300 — Desafio 07: recuperar a aplicação e encerrar os objetos do nível

[Início do laboratório](../../README.md) · [Desafio 06](06-conferir-operacao.md)

| Item | Descrição |
| --- | --- |
| Situação | Restauração, retorno, remoção granular e encerramento dos temporários conferidos no Azure |
| Público | Operações, arquitetura e desenvolvimento, com autorização dos responsáveis pelos alvos |
| Resultado | Retorno definido por fase, dependências preservadas e remoção limitada aos objetos próprios |
| Custo | Coexistência de ambientes, rede, busca, registro e logs tem custo; escala a zero não encerra todas as cobranças |

## Conteúdo

- [Cenário](#cenário)
- [Objetivos](#objetivos)
- [Artefatos e disponibilidade](#artefatos-e-disponibilidade)
- [Tecnologias e conceitos](#tecnologias-e-conceitos)
- [Pré-requisitos](#pré-requisitos)
- [Etapa 1: escolher o retorno por fase](#etapa-1-escolher-o-retorno-por-fase)
- [Etapa 2: recuperar a fonte sem alterar o L100](#etapa-2-recuperar-a-fonte-sem-alterar-o-l100)
- [Etapa 3: revisar os alvos da limpeza](#etapa-3-revisar-os-alvos-da-limpeza)
- [Etapa 4: encerrar acesso e custos](#etapa-4-encerrar-acesso-e-custos)
- [Como pedir uma mudança ao Copilot no VS Code](#como-pedir-uma-mudança-ao-copilot-no-vs-code)
- [Conferência do resultado](#conferência-do-resultado)
- [Solução de problemas](#solução-de-problemas)
- [Custos, pausa e limpeza](#custos-pausa-e-limpeza)
- [Situação da validação](#situação-da-validação)
- [Glossário](#glossário)
- [Referências](#referências)

## Cenário

No piloto fictício de 2025, Beatriz Torres precisa recuperar o atendimento quando uma migração
não atende aos critérios. A equipe mantém a configuração anterior e identifica quais mudanças
de aplicação, documento, rede e acesso precisam ser desfeitas.

Teresa Moura conserva as fontes originais. O encerramento trata objetos do exercício e acessos
temporários; ele preserva recursos compartilhados e o histórico das avaliações.

## Objetivos

1. Definir um retorno compatível com a fase de migração.
2. Recuperar uma fonte sintética no namespace L300 sem modificar documentos originais.
3. Remover somente objetos cuja propriedade e dependências estejam conferidas.
4. Encerrar credenciais, atribuições e serviços temporários com autorização correspondente.

A limpeza de um grupo compartilhado e a remoção de recursos gerenciados manualmente ficam
fora deste procedimento.

## Artefatos e disponibilidade

| Artefato | Uso |
| --- | --- |
| [Bicep L300](../../infra/l300.bicep) | Rede e aplicação separadas, isolamento por fase |
| [Manifesto L300](../../dados/l300/permissoes-documentais.json) | Classificação e fontes do exercício |
| [Operação L300](../../scripts/operar_l300.py) | Guardas do plano e declaração das evidências |
| [Gerenciador L300](../../scripts/gerenciar_ingestao_l300.py) | Exclusão/restauração operacional e remoção dos quatro objetos de busca |
| [Gerenciador L200](../../scripts/gerenciar_ingestao.py) | Referência dos marcadores e remoção por dependência |
| [Recuperação L200](../L200/07-operar-recuperar-limpar.md) | Contrato anterior de revisão, tráfego e limpeza |

Um **namespace** reserva nomes e caminhos ao nível. Use o gerenciador L300 para seus objetos.
A ferramenta L200 conserva o namespace anterior. `operar_l300.py` confere planos e evidências,
sem etapa de exclusão ou opção `--executar`.

## Tecnologias e conceitos

Uma **revisão** identifica imagem e configuração de execução da aplicação. Os pesos de tráfego
escolhem qual revisão recebe pedidos [1]. Autenticação e ingresso são configurações da aplicação;
o retorno da imagem exige também conferir essas configurações.

O L300 cria outro ambiente Container Apps porque a rede é definida na criação [2].
Voltar ao ambiente L200 exige verificar se ele alcança os serviços depois do isolamento.

A **exclusão reversível** do Blob Storage conserva o objeto durante a retenção configurada.
O indexador só detecta a exclusão se processar esse estado dentro da retenção e se a política
estiver configurada desde a primeira execução [3]. Após restaurar um blob, confira e atualize
seus metadados para que o indexador perceba a alteração.

Um **ETag** identifica a versão de um objeto. Condições por ETag impedem que o programa
sobrescreva ou remova uma versão alterada por outra operação [4].
O **marcador de propriedade** identifica os objetos do laboratório; ele limita as ações da
ferramenta, sem substituir a autorização Azure.

## Pré-requisitos

Conserve inventário anterior, revisão aprovada, parâmetros, imagem, destinos e evidências em
local privado. Abra o projeto no Visual Studio Code (VS Code), selecione `.venv` e use PowerShell 7.
A revisão local do plano dispensa login.
O **tenant** é o diretório de identidades, separado da assinatura de recursos.
O **DNS**, sistema de nomes de domínio, mantém a resolução dos serviços na rede.

Qualquer execução externa exige assinatura Azure ativa e autorização dos alvos. Separe remoção
de objetos de busca, blobs, recursos Azure e configurações Entra ID/GitHub.
Confirme dependências compartilhadas antes de iniciar a limpeza.
Execute cada comando separadamente, confira `$LASTEXITCODE` e interrompa a sequência diante de
falha. Dentro da rede, os exemplos do gerenciador podem usar a identidade gerenciada autorizada:
substitua `--tenant-id $tenant` por `--identidade-gerenciada --client-id $clientId`,
como no Desafio 02, sem combinar as opções.

## Etapa 1: escolher o retorno por fase

1. Identifique a última fase efetivamente aplicada.
2. Confira quais aplicações usam os dados e quais caminhos ainda funcionam.
3. Registre o alvo de retorno e a condição para manter ou retirar a rede nova.

| Fase alcançada | Retorno a revisar |
| --- | --- |
| Apenas rede | Conservar L200; retirar novas conexões somente após conferir consumidores |
| Nova aplicação, dados públicos mantidos | Retornar à aplicação anterior somente se o público e as fontes continuarem compatíveis; o chat L200 não aplica autorização por classes |
| Dados isolados | Manter uma revisão funcional na rede ou autorizar reabertura específica dos dados |
| Classificação documental alterada | Restaurar metadados aprovados, executar ingestão e conferir perfis |

**Resultado esperado:** uma configuração de retorno que preserva as mesmas fontes e controles
do caminho autorizado.
Desabilitar a autenticação ou conceder fontes a todos não constitui recuperação aceitável.
Se a autorização documental já for requisito, o retorno a L200 não preserva esse controle.
Prefira uma revisão funcional L300 na rede autorizada ou suspenda a exposição até haver uma
recuperação compatível; não aponte o chat L200 para o índice restrito.
O plano declarativo das fases está disponível sem acesso à nuvem:

```powershell
.\.venv\Scripts\python.exe scripts\operar_l300.py --etapa plano --fase todas
```

### Prompt para o Copilot: preparar o retorno

Anexe este guia, o roteiro L300, o Bicep e o manifesto:

```text
Prepare um plano de retorno e limpeza L300, somente por leitura.
Considere a fase efetivamente aplicada e a conectividade da aplicação anterior.
Separe revisão, ingresso, autenticação, índice, documento, rede e confiança federada.
Identifique consumidores e as conferências após cada alteração.
Não execute Azure, reabra dados públicos, revogue acesso ou exclua recursos.
Não use curingas ou nomes do ambiente do instrutor.
```

## Etapa 2: recuperar a fonte sem alterar o L100

Esta etapa foi conferida com a cópia sintética operacional na rodada Azure.
Restaurar ou repor a fonte e executar o indexador **[altera o Azure]**.

1. Confira caminho, hash, classe e propriedade do documento sintético L300.
2. Escolha restauração dentro da retenção ou reposição da cópia aprovada, conforme o estado real.
3. Preserve classes e demais metadados; atualize a data de modificação ao restaurar [3].
4. Execute o indexador L300 e confira a presença dos trechos por fonte e classe.
5. Confira os dois perfis de acesso e a ausência de documentos duplicados.

A reposição usa a mesma cópia aprovada, sem alterar regras de seguro ou os bytes das três fontes
originais. Estado do blob e estado do índice são conferências separadas.
Use condições de versão para interromper conflitos em vez de sobrescrever alterações concorrentes [4].
A ferramenta reaplica metadados somente quando o hash restaurado confere.
Uma divergência termina com código 3 e informa que o blob já foi restaurado com sua classificação
anterior. Suspenda o indexador e reveja a reposição autorizada antes de continuar.
Os comandos de exclusão e restauração do documento operacional estão no
[Desafio 02](02-atualizar-base.md#etapa-3-conferir-atualização-e-exclusão).

## Etapa 3: revisar os alvos da limpeza

1. Retire o tráfego da aplicação que depende dos objetos.
2. Simule a remoção no namespace L300.
3. Confira marcador, versão e consumidores de cada alvo.
4. Após autorização, remova em ordem de dependência.

| Alvo | Condição e efeito |
| --- | --- |
| Indexador, skillset, fonte e índice L300 | Marcador próprio; retirar o indexador antes de suas dependências |
| Blobs L300 | Hash e metadados conferidos; preservar fontes L100 e namespace L200 |
| Aplicação e ambiente L300 | Tráfego retirado e consumidores conferidos; preservar ambiente anterior |
| Endpoints, conexões compartilhadas e resolução de nomes | Nenhum consumidor preservado depende deles |
| Armazenamento, busca, modelos, registro e logs reutilizados | Conservar, salvo autorização específica de encerramento completo |
| Papéis e confiança temporários | Conferir quem os criou, seus consumidores e a autorização de revogação |

**[altera o Azure]** em cada remoção externa, após aprovação dos alvos.
O plano público apresenta quantidades e efeitos. A lista completa de identificadores permanece
em local privado; nenhum comando de exclusão por curinga participa do procedimento.

Para os quatro objetos da busca, o comando abaixo **só lê o Azure** e mostra o plano.
É uma referência com login do operador; a rodada usou identidade gerenciada dentro da rede.
`$busca` e `$tenant` devem identificar seu destino autorizado:

```powershell
.\.venv\Scripts\python.exe scripts\gerenciar_ingestao_l300.py --etapa remover --busca $busca --tenant-id $tenant
```

Depois de retirar o tráfego consumidor e autorizar esses alvos, **[altera o Azure]**:

```powershell
.\.venv\Scripts\python.exe scripts\gerenciar_ingestao_l300.py --etapa remover --busca $busca --tenant-id $tenant --executar
```

**Resultado esperado:** indexador, skillset, fonte e índice L300 removidos, com índices L100/L200
preservados. Blobs, ambiente, endpoints, registro e logs permanecem. A remoção desses outros
recursos exige inventário, consumidores e autorização próprios; o helper não os exclui.

O ambiente integrado pode criar um grupo gerenciado pela plataforma. A documentação orienta
preservar esses recursos e deixar seu ciclo de vida sob gestão do Container Apps [2].
Retire o ambiente pelo caminho suportado, sem excluir seus componentes manualmente.

Num encerramento completo autorizado, retire também os **shared private links**, conexões
privadas compartilhadas de saída da busca, antes de excluir o serviço e seus destinos.
Confira os IDs, os recursos de destino e os consumidores; não remova conexões de outra aplicação.
A exclusão é assíncrona: espere a ausência na listagem do serviço [7].
O script de limpeza completa não foi entregue na rodada registrada; os comandos de remoção do
gerenciador acima cobrem apenas os quatro objetos de busca. Sem inventário e roteiro administrativo
revisado para os demais recursos, o encerramento automatizado fica bloqueado.

Na rodada de validação, excluir o grupo inteiro removeu o armazenamento antes da busca.
O serviço então recusou sua exclusão com `LockedSPLResourceFound`, pois não conseguiu conferir
bloqueios no destino já ausente. A recuperação removeu somente os dois links próprios e retomou
o encerramento. Não remova bloqueios administrativos nem recrie recursos como correção automática.

## Etapa 4: encerrar acesso e custos

1. Confira ausência dos objetos próprios e continuidade das dependências preservadas.
2. O administrador retira atribuições e confiança federada temporárias autorizadas.
3. Confira sessões novas e limites de expiração dos tokens.
4. Registre recursos mantidos, proprietário, prazo e orçamento.
5. Encerre servidores e helpers locais próprios pelo identificador do processo.

Retire somente configurações realmente criadas e registradas para a atividade. Não houve confiança
federada GitHub na rodada histórica L300, portanto ela não é um alvo daquela limpeza.
Uma listagem de atribuições pode incluir papéis herdados: compare escopo exato e principal
com o inventário próprio antes de revogar; depois confira a linha de base preservada.

A remoção de uma definição de papel ou arquivo YAML deixa outras configurações intactas.
YAML (*YAML Ain't Markup Language*) é o formato de configuração dos workflows.
Desabilitar um papel Entra ID conserva atribuições existentes; retire as atribuições para impedir
que o papel continue nos novos tokens [5].

A migração pode manter dois ambientes temporariamente. Encerrar réplicas ou fechar o terminal
deixa busca, armazenamento, registro, DNS, endpoints e logs cobrando conforme seus serviços [6].

## Como pedir uma mudança ao Copilot no VS Code

Peça alvos e conferências antes de pedir código. Em uma mudança de limpeza, exija teste
para marcador ausente, ETag alterado e recurso de outro nível.
Revise o diff em **Source Control** e mantenha a simulação como padrão.
O pedido de gerar o plano não autoriza sua execução.

## Conferência do resultado

Confira localmente as decisões de propriedade, versão e operação:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_ingestao_l300.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_operacao_l300.py
```

| Conferência | Evidência necessária |
| --- | --- |
| Aplicação recuperada | Revisão e ingresso previstos, autenticação preservada e consulta autorizada |
| Fonte recuperada | Hash e classe conferidos, indexador concluído e trechos presentes |
| Objetos L300 removidos | Ausência dos alvos próprios, sem remoções de outros níveis |
| Dependências preservadas | Inventário e configuração compatíveis com os consumidores mantidos |
| Acesso temporário encerrado | Atribuições e confiança próprias retiradas, conferência com sessão nova |
| Custo residual | Lista dos recursos mantidos e prazo para encerrá-los |

Os testes locais conferem decisões e conflitos com dublês. A ausência de um recurso Azure
é registrada somente depois da leitura real de seu estado no destino autorizado.

## Solução de problemas

| Sintoma | Diagnóstico e ação |
| --- | --- |
| L200 deixa de alcançar dados isolados | Escolha revisão no ambiente privado ou plano de reabertura específica aprovado |
| Fonte restaurada não reaparece | Confira metadados, `LastModified` e estado do indexador |
| Objeto sem marcador próprio | Interrompa a remoção e confirme proprietário |
| ETag mudou | Releia e revise o plano; preserve a alteração concorrente |
| DNS ou endpoint atende outra aplicação | Preserve o recurso e revise sua dependência |
| Custo continua após parar réplicas | Confira todos os serviços mantidos, endpoints e retenção de logs |
| Exclusão da busca falha com `LockedSPLResourceFound` | Confira estado e destinos dos links próprios; retire-os após autorização e confira ausência antes de retomar, sem remover bloqueios automaticamente |
| Comando de espera retorna 0, mas o grupo ainda existe | Confira grupo, recursos e falhas no histórico de atividade; código de saída não substitui ausência real |

## Custos, pausa e limpeza

Defina prazo para a coexistência e para a retenção das evidências.
Uma limpeza parcial mantém dependências cobradas; registre a decisão em vez de tratá-la
como encerramento completo. O L400 parte dos arquivos e das evidências L300, sem exigir
um ambiente do instrutor ativo.

## Situação da validação

A integração local confere as guardas de plano, versão e propriedade.
No Azure, a restauração devolveu o índice de 21 para 24 trechos. A troca para uma revisão
temporária da mesma imagem e o retorno à origem preservaram 200/200/401 nas rotas conferidas;
a revisão temporária foi desativada e a origem ficou com 100% do tráfego.
Isso não mede recuperação de incidente nem retorno a uma versão anterior com código diferente.
A remoção granular conferiu quatro objetos L300 ausentes, repetição idempotente,
definições L100/L200 preservadas e quatro blobs sem alteração de versão.
Aplicações e service principals temporários foram removidos e expurgados, após revogar
o segredo remanescente do login. Os 16 papéis próprios foram retirados; o recurso de modelos
foi expurgado. Grupo exclusivo e gerenciado ficaram ausentes, com zero recursos próprios.
Os oito grupos, oito papéis do operador e 46 recursos anteriores foram conferidos.
O conflito na primeira exclusão e a retomada após remover os links próprios estão preservados
no registro; a limpeza não foi apresentada como uma execução sem falhas.
O [registro local L300](../../docs/validacao/l300-validacao-local.md) detalha decisões e conflitos
testados sem efeitos externos; o [registro Azure](../../docs/validacao/l300-azure-validacao.md)
conserva as operações reais e o estado da limpeza.

## Glossário

| Termo | Significado |
| --- | --- |
| Revisão e peso de tráfego | Versão de execução e percentual de pedidos destinado a ela |
| Exclusão reversível | Retenção temporária do objeto excluído |
| ETag | Identificador da versão usado em condições de alteração |
| Marcador de propriedade | Metadado que identifica os objetos do exercício |
| Namespace | Conjunto de nomes e caminhos reservado ao nível |
| Retenção | Período pelo qual dados ou evidências são conservados |
| Revogação | Retirada de uma autorização ou relação de confiança |

## Referências

1. [Revisões em Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/revisions-manage).
2. [Redes e recursos gerenciados do ambiente](https://learn.microsoft.com/en-us/azure/container-apps/custom-virtual-networks).
3. [Detecção de exclusão e restauração no indexador](https://learn.microsoft.com/en-us/azure/search/search-how-to-index-azure-blob-changed-deleted).
4. [Concorrência no Blob Storage](https://learn.microsoft.com/en-us/azure/storage/blobs/concurrency-manage).
5. [Papéis de aplicação e atribuições Entra ID](https://learn.microsoft.com/en-us/entra/identity-platform/howto-add-app-roles-in-apps).
6. [Cobrança em Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/billing).
7. [Diagnóstico e exclusão de conexões compartilhadas da busca](https://learn.microsoft.com/en-us/azure/search/troubleshoot-shared-private-link-resources#deleting-a-shared-private-link-resource).

Texto por GPT-6.1 Sol; código e testes por Claude Sonnet 5.5, com Astra indisponível.
As escolhas de autoria, Copilot e deployments Azure permanecem independentes.

Revisão documental: gpt-6-astra (Astra), em 11 de outubro de 2026, por leitura integral e
conferência local dos artefatos; sem nova execução Azure.
