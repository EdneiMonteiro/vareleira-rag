# L400 · Desafio 07: recuperar e limpar

[Início](../../README.md) · [Desafio 06](06-testar-carga-interrupcao.md) · [Roteiro L400](../../docs/roteiro-l400.md)

| Campo | Definição |
| --- | --- |
| Situação | Retorno, remoção granular, limpeza e expurgos próprios conferidos no Azure |
| Público | Operações, arquitetura e desenvolvimento, com responsáveis pelo acesso |
| Resultado | Retornar à referência e encerrar somente recursos e acessos próprios |
| Custo | Temporários continuam cobrando até o encerramento de seus serviços |

## Conteúdo

- [Cenário](#cenário)
- [Objetivos](#objetivos)
- [Artefatos e disponibilidade](#artefatos-e-disponibilidade)
- [Tecnologias e conceitos](#tecnologias-e-conceitos)
- [Pré-requisitos](#pré-requisitos)
- [Etapa 1: conferir a recuperação](#etapa-1-conferir-a-recuperação)
- [Etapa 2: retirar consumidores e objetos](#etapa-2-retirar-consumidores-e-objetos)
- [Etapa 3: encerrar acesso e custo](#etapa-3-encerrar-acesso-e-custo)
- [Como pedir uma mudança ao Copilot no VS Code](#como-pedir-uma-mudança-ao-copilot-no-vs-code)
- [Conferência do resultado](#conferência-do-resultado)
- [Solução de problemas](#solução-de-problemas)
- [Custos, pausa e limpeza](#custos-pausa-e-limpeza)
- [Situação da validação](#situação-da-validação)
- [Glossário e referências](#glossário-e-referências)

## Cenário

O piloto fictício precisa encerrar o experimento sem deixar cobrança ou acesso temporário.
Teresa Moura quer conservar as evidências e a equipe de operações precisa distinguir retorno,
remoção, expurgo e preservação dos recursos anteriores.

## Objetivos

1. Conferir índice, aplicação, política e autenticação de referência.
2. Simular remoções e retirar consumidores antes das dependências.
3. Revogar somente credenciais e atribuições próprias.
4. Verificar ausência real, custo ainda desconhecido e recursos preservados.

## Artefatos e disponibilidade

| Artefato | Uso |
| --- | --- |
| [Recuperação e limpeza L300](../L300/07-recuperar-limpar.md) | Ordem e guardas já exercitadas |
| [Registro Azure L300](../../docs/validacao/l300-azure-validacao.md) | Conflitos reais e retomadas preservadas |
| [Gerenciador de ingestão](../../scripts/gerenciar_ingestao_l300.py) | Remoção dos quatro objetos de um namespace próprio |
| [Roteiro L400](../../docs/roteiro-l400.md) | Referência e condições do novo experimento |

O inventário completo da rodada permanece em local privado. Não publique IDs, credenciais
ou comandos de exclusão com destinos do instrutor.

O [plano de operação L400](../../scripts/operar_l400.py) apresenta efeitos e condições sem rede:

```powershell
.\.venv\Scripts\python.exe scripts\operar_l400.py --etapa planejar --passo limpeza
```

Ele não remove recursos nem substitui a autorização do operador.
O script privado que encerrou todos os recursos da rodada não integra a entrega.
O gerenciador público remove objetos do pipeline, não grupos, identidades ou credenciais.
Portanto, a limpeza completa exige inventário próprio e roteiro administrativo revisado;
sem eles, não execute exclusões deduzidas dos nomes ou das contagens deste registro.

## Tecnologias e conceitos

**Rollback**, retorno à configuração anterior, não significa reabrir acesso público por padrão.
Depois de isolar os dados, a referência também precisa de um caminho privado autorizado.

**Exclusão reversível** conserva um recurso por um período. **Expurgo** remove o objeto desse
estado recuperável quando o serviço e a autorização permitem. Remover um grupo no
Azure Resource Manager (ARM), serviço de administração, não comprova por si só todos os expurgos.

**Shared private links** são conexões privadas de saída da busca. Sua exclusão é assíncrona e
deve ser conferida no serviço. O destino já ausente pode impedir a exclusão da busca [1].

## Pré-requisitos

Antes de remover, conserve relatórios, inventário e linha de base.
Confirme assinatura ativa e autorização dos alvos. Limpeza **[altera o Azure]** e pode ser
irreversível; uma pergunta de modelo não concede essa autorização.

O ambiente Container Apps pode ter um grupo gerenciado. Retire o ambiente pelo serviço,
sem editar ou excluir componentes gerenciados manualmente [2].

## Etapa 1: conferir a recuperação

1. Retorne à configuração de referência.
2. Confira índice e dimensões compatíveis.
3. Execute uma consulta autenticada e a recusa correspondente.
4. Confira política, fontes e autenticação.
5. Registre o alcance da recuperação.

Trocar e retornar uma revisão da mesma imagem demonstra tráfego e configuração.
Isso não mede recuperação de incidente nem um objetivo de tempo de recuperação de produção.
Um checkpoint de workflow também não retoma automaticamente recursos Azure [3].

## Etapa 2: retirar consumidores e objetos

| Ordem | Alvo e condição |
| --- | --- |
| Consumidores | Retirar tráfego e execuções próprias que usam o candidato |
| Pipeline candidato | Simular, conferir propriedade e remover indexador antes dos objetos dependentes |
| Conexões de saída próprias | Retirar links sem consumidores antes do serviço de busca e seus destinos |
| Aplicações e ambientes próprios | Caminho suportado; grupo gerenciado sob ciclo de vida da plataforma |
| Recursos exclusivos | Remover após conferir que não há consumidor preservado |

Não remova um serviço reaproveitado de outro proprietário como parte da limpeza de um índice.
Não use curingas para descobrir alvos de exclusão durante a execução.

## Etapa 3: encerrar acesso e custo

1. Revogue credenciais próprias e retire atribuições temporárias.
2. Remova aplicativos e principais próprios depois dos consumidores.
3. Confira expurgos necessários por nome, tipo, região e ID exatos.
4. Compare grupos, recursos e papéis anteriores com a linha de base.
5. Consulte custos sem interpretar resposta vazia como zero.
6. Encerre processos locais próprios pelo identificador.

Um comando de espera que retorna código 0 não substitui a listagem real.
Confira falhas no histórico de atividade quando o grupo ou recurso ainda existir.
Uma listagem de acesso pode incluir atribuições fora do alvo de limpeza. Confira o escopo
de cada atribuição antes de considerar sua revogação; preserve papéis herdados e de outros recursos.

## Como pedir uma mudança ao Copilot no VS Code

```text
Anexo plano de encerramento e inventário sanitizado, sem IDs reais.
Confira dependências, consumidores, conexões e recursos preservados.
Separe rollback, exclusão, expurgo e prova de ausência.
Não execute remoções, revogue acesso ou remova bloqueios administrativos.
```

Revise o plano em Source Control e confira cada alvo antes de uma execução autorizada.

## Conferência do resultado

| Conferência | Evidência |
| --- | --- |
| Retorno | Consulta e recusa na configuração de referência |
| Objetos candidatos | Ausentes sem modificar a referência |
| Recursos próprios | Ausência em leituras reais, não apenas aceitação do pedido |
| Acesso temporário | Credenciais e papéis próprios encerrados |
| Preservação | Mesmos recursos, grupos e papéis anteriores |
| Custo | Período, moeda e dados disponíveis ou indisponibilidade explícita |

## Solução de problemas

| Sintoma | Ação |
| --- | --- |
| Busca não pode ser excluída | Confira e retire somente os links próprios autorizados antes de retomar |
| Grupo continua após espera | Leia estado, recursos e histórico de falhas |
| Listagem inclui papéis fora do grupo | Preserve esses papéis; restrinja a limpeza ao escopo e aos principais próprios inventariados |
| Referência perdeu acesso | Confira caminho privado e configuração, sem reabertura automática |
| API de custo não retorna linhas | Conserve a incerteza; não mantenha temporários esperando cobrança |

## Custos, pausa e limpeza

Conservar a referência durante a migração tem custo e prazo próprios.
Encerrar o terminal ou escalar uma aplicação a zero não remove busca, modelos, registro,
DNS (sistema de nomes de domínio) e logs.
Os recursos anteriores continuam sob seus proprietários; a rodada encerra somente seus temporários.

## Situação da validação

Promoção e retorno tiveram consultas autenticadas. A remoção granular retirou os quatro objetos
candidatos sem modificar a referência, com simulação e repetição idempotente.
O encerramento retirou consumidores, links próprios antes dos destinos, credencial, 15 atribuições,
cinco aplicativos e cinco principais de aplicação. Grupo exclusivo e gerenciado estão ausentes,
sem recursos ou papéis próprios; os objetos recuperáveis e a conta de modelos foram expurgados.

A verificação posterior confirmou oito grupos, 46 recursos e atribuições anteriores preservados.
A consulta final de custo retornou sem linhas, sem comprovar valor zero.
O [registro L400](../../docs/validacao/l400-validacao.md) preserva a falha de escopo dos papéis,
a retomada e as provas de ausência; o [resumo do encerramento](../../docs/validacao/l400-encerramento-final.json)
conserva contagens sanitizadas. Os temporários removidos não são um ambiente disponível para o aluno;
uma nova execução exige seus próprios destinos e autorização.

## Glossário e referências

| Termo | Significado |
| --- | --- |
| Rollback | Retorno à configuração anterior |
| ARM | Administração dos recursos Azure |
| Expurgo | Remoção do estado recuperável do objeto |
| Consumidor | Aplicação ou processo que depende de um recurso |
| Linha de base | Inventário anterior usado para conferir preservação |

1. [Exclusão e diagnóstico de links compartilhados](https://learn.microsoft.com/en-us/azure/search/troubleshoot-shared-private-link-resources#deleting-a-shared-private-link-resource).
2. [Rede e recursos gerenciados de Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/custom-virtual-networks).
3. [Checkpoints de workflows](https://learn.microsoft.com/en-us/agent-framework/workflows/checkpoints).
4. [Cobrança de Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/billing).

Texto por GPT-6.1 Sol; código por Claude Sonnet 5.5. Encerramento do experimento não homologa produção.

Revisão documental por gpt-6-astra (Astra), em 11 de outubro de 2026, sem nova execução Azure.
