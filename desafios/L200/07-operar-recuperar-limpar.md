# L200 — Desafio 07: operar revisões, recuperar e limpar

[Início do laboratório](../../README.md) · [Desafio 06](06-avaliar-chat.md)

| Item | Descrição |
| --- | --- |
| Situação | Exercício executável. Troca de revisão, retorno, remoção do grupo e expurgo foram conferidos no Azure em 10 de outubro de 2026; recursos preexistentes preservados. |
| Público | Pessoas de operações, arquitetura e desenvolvimento, com autorização para os alvos da limpeza. |
| Resultado | Revisão anterior recuperada, falhas localizadas por código de suporte e recursos temporários removidos ou mantidos com decisão explícita. |
| Custo | Duas revisões podem executar réplicas durante a recuperação; busca, registro, logs e modelos têm cobranças próprias. |

## Conteúdo

- [Cenário](#cenário)
- [Objetivos](#objetivos)
- [Artefatos e disponibilidade](#artefatos-e-disponibilidade)
- [Tecnologias e conceitos](#tecnologias-e-conceitos)
- [Pré-requisitos](#pré-requisitos)
- [Etapa 1: conferir revisão, logs e custo](#etapa-1-conferir-revisão-logs-e-custo)
- [Etapa 2: exercitar o retorno à revisão anterior](#etapa-2-exercitar-o-retorno-à-revisão-anterior)
- [Etapa 3: remover somente os objetos L200](#etapa-3-remover-somente-os-objetos-l200)
- [Etapa 4: encerrar o laboratório exclusivo](#etapa-4-encerrar-o-laboratório-exclusivo)
- [Como pedir uma mudança ao Copilot no VS Code](#como-pedir-uma-mudança-ao-copilot-no-vs-code)
- [Conferência do resultado](#conferência-do-resultado)
- [Solução de problemas](#solução-de-problemas)
- [Custos, pausa e limpeza](#custos-pausa-e-limpeza)
- [Situação da validação](#situação-da-validação)
- [Glossário](#glossário)
- [Referências](#referências)

## Cenário

No piloto fictício de 2025, Beatriz Torres precisa saber como recuperar a interface quando uma
implantação não atende aos critérios e como encerrar o exercício sem deixar cobranças evitáveis.
A equipe identifica revisões, observa falhas e registra o destino de cada recurso.

Uma revisão anterior do chat não restaura documentos ou índice. A recuperação de ingestão foi
demonstrada no Desafio 03; aqui a equipe recupera a configuração e o tráfego da aplicação.

## Objetivos

1. Identificar imagem, revisão ativa, configuração e estado de autenticação.
2. Localizar erros por identificador de requisição, sem guardar pergunta ou credencial no log.
3. Criar uma revisão de teste e retornar o tráfego à anterior.
4. Remover os objetos L200 sem atingir o índice L100.
5. Encerrar o grupo exclusivo e as identidades criadas fora dele, preservando recursos preexistentes.

## Artefatos e disponibilidade

| Artefato disponível | Uso |
| --- | --- |
| [Módulo da aplicação](../../infra/modules/l200-aplicacao.bicep) | Revisão, escala, saúde e autenticação |
| [Servidor](../../scripts/chat_web.py) | Logs sanitizados e códigos de suporte |
| [Gerenciador de ingestão](../../scripts/gerenciar_ingestao.py) | Remoção dos quatro objetos de busca L200 |
| [Infraestrutura da base](../../infra/l200.bicep) | Recursos e cinco atribuições acrescentadas |
| [Registro do desafio](../../docs/validacao/l200-07-operar-recuperar-limpar.md) | Recuperação, custo e limpeza efetivamente conferidos |

## Tecnologias e conceitos

Uma **revisão** conserva a imagem e a configuração de execução da aplicação. Mudanças de imagem,
variáveis ou recursos de computação podem criar outra revisão. O modo `multiple` permite manter
mais de uma ativa; pesos de tráfego determinam qual recebe pedidos [1][2].

Os comandos usam a Azure CLI, interface de linha de comando do Azure. A API, interface de programação
de aplicações, permite consultar estado e custo dos recursos. A administração desses recursos usa
o Azure Resource Manager (ARM).

Autenticação e ingresso são configurações da aplicação, não uma cópia isolada dentro de cada revisão.
Retornar à imagem anterior não desfaz automaticamente uma alteração nessas configurações.
Confira-as antes e depois da recuperação.

O **identificador da requisição** aparece como código de suporte e no log. O servidor registra rota
em vocabulário fechado, status, tempo e causa curta; não registra pergunta, resposta, token ou cabeçalho
de identidade. O Log Analytics recebe os logs do ambiente.

**Exclusão reversível** mantém temporariamente um recurso removido. **Expurgo** é sua remoção
definitiva quando o serviço permite. O recurso de modelos exige conferência própria após excluir
o grupo [3]. Aplicações e principais de serviço Entra ID são objetos do diretório, tratados
separadamente dos recursos do grupo [5].

## Pré-requisitos

Conclua a avaliação do Desafio 06 e conserve `$assinatura`, `$grupo`, `$tenant`, `$busca`, `$modelos`,
`$aplicacao`, `$urlChat`, `$idLogin` e `$idChaveLogin` em registro privado.
Tenha a lista dos recursos e papéis existentes **antes** do laboratório.

Cada remoção exige autorização do alvo e da consequência. Não exclua um grupo compartilhado.
Confirme quem é proprietário do registro Entra ID e se a credencial foi criada neste exercício.
Use PowerShell 7 no terminal do projeto no VS Code.

## Etapa 1: conferir revisão, logs e custo

1. Leia as revisões e a configuração da aplicação.
2. Registre a revisão de origem antes de modificá-la.
3. Consulte logs sem copiar conteúdo ou identificadores privados para pedidos de ajuda.

```powershell
az containerapp revision list --subscription $assinatura --resource-group $grupo --name $aplicacao --output table
$estadoApp = az containerapp show --subscription $assinatura --resource-group $grupo --name $aplicacao --output json | ConvertFrom-Json
$revisaoOrigem = $estadoApp.properties.latestReadyRevisionName
if (-not $revisaoOrigem) { throw "Não há revisão pronta para usar como referência." }
az containerapp revision show --subscription $assinatura --resource-group $grupo --name $aplicacao --revision $revisaoOrigem --output json
az containerapp auth show --subscription $assinatura --resource-group $grupo --name $aplicacao --output json
az containerapp logs show --subscription $assinatura --resource-group $grupo --name $aplicacao --type console --tail 30
```

Se o ambiente estiver em modo `multiple`, confira também a revisão que recebe o tráfego:
`latestReadyRevisionName` identifica a última pronta, não necessariamente a escolhida pelos pesos.
Use a revisão efetivamente aprovada como origem.

**Conferência:** imagem conhecida, revisão pronta, autenticação ativa e `Return401` para pedidos
anônimos. Um `503` com causa `resposta_descartada` significa que a política rejeitou a saída;
as causas `acesso_negado`, `rede` e `limite_do_servico` exigem diagnósticos distintos.

No Azure portal, consulte **Cost Management > Cost analysis**, selecione a assinatura e filtre o
grupo e o período da atividade. O procedimento pelo portal é uma referência de uso; a rodada de
validação consultou a API de custos. O processamento dos dados de cobrança tem atraso [4].
Registre moeda, período, serviços retornados e limitações; um retorno vazio exige consulta posterior
para confirmar o custo.

## Etapa 2: exercitar o retorno à revisão anterior

Esta prática usa a mesma imagem para demonstrar configuração e tráfego. Ela não injeta uma falha
nem mede tempo de recuperação de um incidente de produção.

1. Ative modo de múltiplas revisões e fixe 100% do tráfego na origem.
2. Copie a revisão para um sufixo novo.
3. Confira a revisão, transfira o tráfego e teste as rotas.

**[altera o Azure]** nos comandos de modo, cópia e tráfego:

```powershell
az containerapp revision set-mode --subscription $assinatura --resource-group $grupo --name $aplicacao --mode multiple --output none
az containerapp ingress traffic set --subscription $assinatura --resource-group $grupo --name $aplicacao --revision-weight "${revisaoOrigem}=100" --output none
$sufixo = "recuperacao-" + (Get-Date -Format "HHmmss")
az containerapp revision copy --subscription $assinatura --resource-group $grupo --name $aplicacao --from-revision $revisaoOrigem --revision-suffix $sufixo --output none
$revisaoTeste = "${aplicacao}--$sufixo"
az containerapp revision show --subscription $assinatura --resource-group $grupo --name $aplicacao --revision $revisaoTeste --output json
```

Confira `Provisioned`, imagem e configuração antes de transferir tráfego.
Após essa aprovação:

```powershell
az containerapp ingress traffic set --subscription $assinatura --resource-group $grupo --name $aplicacao --revision-weight "${revisaoTeste}=100" "${revisaoOrigem}=0" --output none
(Invoke-WebRequest ($urlChat + "/healthz") -SkipHttpErrorCheck).StatusCode
(Invoke-WebRequest ($urlChat + "/readyz") -SkipHttpErrorCheck).StatusCode
(Invoke-WebRequest $urlChat -SkipHttpErrorCheck).StatusCode
```

**Resultado esperado:** `200`, `200` e `401`. A autenticação permanece obrigatória.
Uma consulta autenticada pode ser feita como teste de operação, separada do conjunto final.

Para retornar à origem e desativar a revisão temporária:

```powershell
az containerapp ingress traffic set --subscription $assinatura --resource-group $grupo --name $aplicacao --revision-weight "${revisaoOrigem}=100" "${revisaoTeste}=0" --output none
(Invoke-WebRequest ($urlChat + "/healthz") -SkipHttpErrorCheck).StatusCode
(Invoke-WebRequest ($urlChat + "/readyz") -SkipHttpErrorCheck).StatusCode
(Invoke-WebRequest $urlChat -SkipHttpErrorCheck).StatusCode
az containerapp show --subscription $assinatura --resource-group $grupo --name $aplicacao --query properties.configuration.ingress.traffic --output json
az containerapp revision deactivate --subscription $assinatura --resource-group $grupo --name $aplicacao --revision $revisaoTeste --output none
```

**[altera o Azure]** no retorno e na desativação. Confira 100% na origem antes de desativar a outra.
O modo permanece `multiple`. O Bicep usa `Single` por padrão; uma futura reaplicação deve considerar
essa diferença. Mudar imediatamente para `single` pode escolher uma revisão diferente da desejada.

## Etapa 3: remover somente os objetos L200

Para o encerramento completo do nível, siga diretamente a Etapa 4. Esta etapa é uma alternativa
que conserva os recursos Azure e encerra apenas a comparação dos índices.

Se a intenção for apenas encerrar a comparação dos índices, simule:

```powershell
python scripts\gerenciar_ingestao.py --etapa remover --busca $busca --tenant-id $tenant
```

**Conferência:** somente indexador, skillset, fonte e índice L200, em ordem de dependência.
O marcador do laboratório protege contra remoção de objetos que não lhe pertencem.

Após aprovar esses alvos, **[altera o Azure]**:

```powershell
python scripts\gerenciar_ingestao.py --etapa remover --busca $busca --tenant-id $tenant --executar
python scripts\verificar_indice.py --busca $busca --modelos $modelos --tenant-id $tenant
```

**Resultado esperado:** quatro objetos removidos e índice L100 preservado.
A conferência vetorial L100 calcula embeddings de perguntas conhecidas, sem gerar respostas.
O chat configurado para o índice L200 deixa de responder consultas depois da remoção: encerre sua
exposição antes, ou escolha conscientemente continuar pelo índice L100 com nova configuração e avaliação.
Essa etapa não remove registro de imagens, ambiente, logs ou identidades.

## Etapa 4: encerrar o laboratório exclusivo

Antes de excluir o grupo, guarde nome e região do recurso de modelos:

```powershell
$regiaoModelos = az cognitiveservices account show --subscription $assinatura --resource-group $grupo --name $modelos --query location --output tsv
az resource list --subscription $assinatura --resource-group $grupo --output table
az ad app credential list --id $idLogin --output table
```

Confira cada recurso com o inventário inicial. A remoção completa só é permitida em grupo exclusivo.
A aplicação Entra ID não faz parte desse grupo; retire a credencial específica e o registro próprio.

**[altera o Azure]** e o Entra ID, após aprovação:

```powershell
az containerapp delete --subscription $assinatura --resource-group $grupo --name $aplicacao --yes --output none
az ad app credential delete --id $idLogin --key-id $idChaveLogin --output none
az ad app delete --id $idLogin --output none
az group delete --subscription $assinatura --name $grupo --yes
az group exists --subscription $assinatura --name $grupo
```

**Resultado esperado:** grupo ausente (`false`), registro e credencial de login removidos.
Confira também a ausência do principal de serviço próprio. Preserve registros e credenciais de
outros proprietários.

O recurso de modelos pode permanecer em exclusão reversível. Consulte os excluídos, confira
**nome, grupo e região**, e expurgue somente o recurso desta rodada se autorizado:

```powershell
az cognitiveservices account list-deleted --subscription $assinatura --output table
az cognitiveservices account purge --subscription $assinatura --resource-group $grupo --name $modelos --location $regiaoModelos --output none
az cognitiveservices account list-deleted --subscription $assinatura --output table
```

**[altera o Azure]** no expurgo, uma remoção definitiva. A lista final pode conter recursos de outras
atividades; preserve-os. Este nível não cria um cofre novo e não autoriza remover cofres existentes.

## Como pedir uma mudança ao Copilot no VS Code

Anexe este guia, `l200.bicep` e o módulo da aplicação:

```text
Prepare um plano de recuperação e limpeza do L200, somente por leitura.
Separe objetos de busca, recursos Azure e registro/credencial Entra ID.
Indique dependências, efeitos sobre o chat e conferências após cada remoção.
Não execute comandos, use curingas de exclusão ou remova recursos preexistentes.
Não peça valores de segredo ou saídas brutas do meu ambiente.
```

Revise o plano e seus alvos antes de autorizar execução. Em alterações de script, preserve ETags,
marcadores de propriedade e mensagens explícitas de divergência; confira o diff e os testes.
Um ETag identifica a versão do objeto e permite rejeitar uma alteração concorrente.

## Conferência do resultado

| Verificação | Evidência |
| --- | --- |
| Recuperação de revisão | Tráfego 100% na origem, rotas `200/200/401`, revisão temporária desativada |
| Remoção dos objetos de busca | Quatro objetos L200 ausentes e índice L100 conferido antes da exclusão completa |
| Limpeza completa | Grupo ausente; aplicação, principal e credencial Entra ID próprios ausentes |
| Expurgo de modelos | Recurso desta rodada ausente da lista de excluídos |
| Preservação | Grupos e papéis preexistentes iguais ao inventário inicial |
| Processos locais | Servidores próprios encerrados; nenhum processo alheio parado |
| Custo | Consulta com período, moeda e limites registrados, sem presumir total imediato |

## Solução de problemas

| Sintoma | Diagnóstico e ação |
| --- | --- |
| Revisão não provisiona | Confira imagem, configuração e eventos; conserve tráfego na origem. |
| Tráfego volta para revisão errada | Use o nome exato da revisão aprovada; evite `latest` como referência de recuperação. |
| Objeto sem marcador do laboratório | Interrompa e confira propriedade; não force sua remoção. |
| Grupo compartilhado | Preserve o grupo; prepare remoção individual com inventário e autorização específica. |
| Aplicação Entra ID permanece | Confira seu identificador próprio, tenant e principal; a exclusão do grupo não a remove. |
| Custo vazio ou parcial | Registre a resposta e consulte posteriormente; remova recursos autorizados sem esperar a fatura. |

## Custos, pausa e limpeza

Desativar uma revisão encerra suas réplicas [1], mas não todas as dependências.
Fechar o navegador ou o terminal não encerra a aplicação hospedada. Caso decida manter recursos para
o L300, registre proprietário, destino, prazo, orçamento e migração de identidade e rede.
Sem essa decisão, remova os temporários ao terminar.

## Situação da validação

A troca e o retorno de tráfego foram conferidos com a mesma imagem, preservando autenticação.
A revisão de teste foi desativada. Após a avaliação, a aplicação, os quatro objetos L200, o grupo
exclusivo e a credencial e identidade de login foram removidos; o recurso de modelos foi expurgado.
Sete grupos e oito papéis preexistentes permaneceram iguais à linha de base. A conferência está em
[docs/validacao/l200-07-operar-recuperar-limpar.md](../../docs/validacao/l200-07-operar-recuperar-limpar.md).
O exercício não mediu recuperação de dados de produção nem simulou falha de código.

## Glossário

| Termo | Significado |
| --- | --- |
| Revisão | Versão implantada da imagem e configuração da aplicação |
| Peso de tráfego | Percentual de pedidos destinado a uma revisão |
| Log Analytics | Serviço de consulta e retenção de logs |
| Código de suporte | Identificador que relaciona erro na interface e registro do servidor |
| Exclusão reversível | Retenção temporária de um recurso excluído |
| Expurgo | Remoção definitiva de um recurso excluído |
| Inventário inicial | Lista de recursos e permissões existentes antes do exercício |

## Referências

1. [Gerenciar revisões em Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/revisions-manage).
2. [Distribuir tráfego entre revisões](https://learn.microsoft.com/en-us/azure/container-apps/traffic-splitting).
3. [Recuperar e expurgar recursos de modelos excluídos](https://learn.microsoft.com/en-us/azure/ai-services/recover-purge-resources).
4. [Atualização e disponibilidade dos dados de custo](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/understand-cost-mgt-data).
5. [Aplicações e principais de serviço no Microsoft Entra ID](https://learn.microsoft.com/en-us/entra/identity-platform/app-objects-and-service-principals).

Texto e revisão: GPT-6.1 Sol. Código e testes: Claude Sonnet 5.5.
O Astra não estava disponível; as escolhas de modelos do aluno e da aplicação permanecem independentes.
