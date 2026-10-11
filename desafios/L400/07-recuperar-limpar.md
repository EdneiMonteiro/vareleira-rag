# L400 · Desafio 07: recuperar e limpar

[Início](../../README.md) · [Desafio 06](06-testar-carga-interrupcao.md) · [Roteiro L400](../../docs/roteiro-l400.md)

| Campo | Definição |
| --- | --- |
| Situação | Encerramento Azure histórico; roteiro de IDs e sessão revisado por leitura; ferramenta testada localmente, sem nova execução Azure |
| Público | Operações, arquitetura e desenvolvimento, com responsáveis pelo acesso |
| Resultado | IDs de objeto L400 conferidos antes das remoções, blocos revisados na mesma sessão e encerramento próprio sem alterar a base anterior |
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
  - [Roteiro administrativo revisado de encerramento completo](#roteiro-administrativo-revisado-de-encerramento-completo)
- [Como pedir uma mudança ao Copilot no VS Code](#como-pedir-uma-mudança-ao-copilot-no-vs-code)
- [Conferência do resultado](#conferência-do-resultado)
- [Solução de problemas](#solução-de-problemas)
- [Custos, pausa e limpeza](#custos-pausa-e-limpeza)
- [Situação da validação](#situação-da-validação)
- [Glossário e referências](#glossário-e-referências)
- [Autoria](#autoria)

## Cenário

O piloto fictício precisa encerrar os serviços e acessos temporários do experimento, conservando
a cobrança acumulada como uma conferência separada.
Teresa Moura quer conservar as evidências e a equipe de operações precisa distinguir retorno,
remoção, expurgo e preservação dos recursos anteriores.

## Objetivos

1. Conferir índice, aplicação, política e autenticação de referência.
2. Simular remoções e retirar consumidores antes das dependências.
3. Revogar somente credenciais e atribuições próprias.
4. Verificar ausência real, custo ainda desconhecido e recursos preservados.
5. Usar inventário e linha de base próprios para revisar um plano que apenas imprime comandos,
   distinguindo aprovação, reprovação e pendência.

## Artefatos e disponibilidade

| Artefato | Uso |
| --- | --- |
| [Roteiro administrativo L300](../L300/07-recuperar-limpar.md#roteiro-administrativo-revisado-de-encerramento-completo) | Sequência comum da ferramenta pública; revisada por leitura, sem nova execução Azure |
| [Registro Azure L300](../../docs/validacao/l300-azure-validacao.md) | Conflitos reais e retomadas preservadas |
| [Gerenciador de ingestão](../../scripts/gerenciar_ingestao_l300.py) | Remoção dos quatro objetos com nomes reservados a um índice próprio |
| [Roteiro L400](../../docs/roteiro-l400.md) | Referência e condições do novo experimento |
| [Planejador de encerramento](../../scripts/planejar_encerramento.py) | Público; valida inventário, imprime captura e plano, compara evidências; nunca chama o Azure nem exclui objetos |
| [Contrato do encerramento](../../scripts/lab_encerramento.py) | Esquema versão 1, fases, guardas e critérios da conferência |
| [Testes do encerramento](../../tests/test_encerramento.py) | Dublês locais, execução no PowerShell 7 e recusa no Windows PowerShell 5.1 com interface de linha de comando falsa |
| [Registro Azure L400](../../docs/validacao/l400-validacao.md) | Encerramento histórico por procedimento privado diferente, com falha e retomada preservadas |

O inventário completo da rodada permanece em local privado. Não publique identificadores (IDs),
credenciais ou comandos de exclusão com destinos do instrutor.

O [plano de operação L400](../../scripts/operar_l400.py) apresenta efeitos e condições sem rede:

```powershell
.\.venv\Scripts\python.exe scripts\operar_l400.py --etapa planejar --passo limpeza
```

Ele não remove recursos nem substitui a autorização do operador.
O roteiro público usa `planejar_encerramento.py` com as etapas `modelo`, `capturar`, `plano`
e `conferir`. A ferramenta lê arquivos e imprime texto; quem revisa e executa os comandos é o
aluno, depois da autorização correspondente [6]. Ela não substitui o gerenciador de ingestão:
esse gerenciador continua removendo apenas os quatro objetos de busca do **namespace** escolhido,
conjunto de nomes reservado ao índice.
Inventário, plano e instantâneos reais são privados; os relatórios opcionais novos são sanitizados.

## Tecnologias e conceitos

**Rollback**, retorno à configuração anterior, não significa reabrir acesso público por padrão.
Depois de isolar os dados, a referência também precisa de um caminho privado autorizado.

**Exclusão reversível** conserva um recurso por um período. **Expurgo** remove o objeto desse
estado recuperável quando o serviço e a autorização permitem. Remover um grupo no
Azure Resource Manager (ARM), serviço de administração, não comprova por si só todos os expurgos.

**Shared private links** são conexões privadas de saída da busca. Trate a exclusão como pendente
até confirmar ausência na listagem do serviço, sem tratar aceitação como conclusão.
O destino já ausente pode impedir a exclusão da busca [1]. A conclusão das operações impressas
pelo planejador não foi qualificada em uma nova execução Azure.

Um **deployment** é uma implantação nomeada de modelo na conta de modelos. A contingência L400
é um deployment separado; o candidato de busca usa 768 dimensões e é distinto do índice de
referência. Retirar apenas o candidato não encerra a conta de modelos ou o serviço de busca.

O **Azure CLI** (*Azure Command-Line Interface*) é a interface de linha de comando do Azure.
O planejador imprime seus comandos, não os executa. **JSON** (*JavaScript Object Notation*) é o
formato dos arquivos de inventário e evidências. A **linha de base** contém grupos, recursos e
atribuições anteriores; o **instantâneo final** registra o estado exportado depois do encerramento.

O **RBAC** (*Role-Based Access Control*, controle de acesso baseado em papéis) do Azure associa
principal, papel e escopo. Um **principal de serviço** representa um aplicativo no
Microsoft Entra ID. O **Microsoft Graph** permite conferir seus objetos: código
**HTTP** (*Hypertext Transfer Protocol*, protocolo de transferência de hipertexto) 404 comprova
ausência individual somente com tenant e ID de objeto corretos. Consultar `clientId` ou `appId`
como ID de objeto pode devolver 404 mesmo com o objeto presente. Falhas de autorização ficam
indeterminadas, não ausentes.

Um **Job do Container Apps** executa uma tarefa no ambiente, como manutenção. Conserve suas
provas antes de encerrá-lo. Um **workspace do Log Analytics** armazena logs para consulta;
o plano de encerramento solicita sua exclusão permanente quando ele é próprio.

## Pré-requisitos

Antes de remover, conserve relatórios, inventário e linha de base.
Confirme assinatura ativa e autorização dos alvos. Limpeza **[altera o Azure]** e pode ser
irreversível; uma pergunta de modelo não concede essa autorização.
Operações de identidade **[altera o Microsoft Entra ID]** exigem também autorização dos
administradores desses objetos no **tenant**, diretório de identidades separado da assinatura.
O encerramento completo requer aprovação escrita de exclusões e expurgos, permissões
proporcionais e leitura dos papéis e dos custos. Login não comprova essas autorizações.

Abra a raiz do projeto no Visual Studio Code (VS Code), selecione o interpretador `.venv` e use
PowerShell 7, aberto com `pwsh`. Cole a Preparação completa do plano primeiro, na mesma janela dos
passos, e não troque conta, assinatura ou tenant até terminar. As capturas têm guarda própria de
versão, sem depender da marca de Preparação do plano. Para uma nova rodada, capture a base
**antes de criar o grupo exclusivo L400**.
Não reutilize os inventários privados da rodada histórica ou do L300 como lista de remoções L400.
Sem base anterior válida, há apenas prévia do plano e a preservação fica pendente; o
[roteiro L300](../L300/07-recuperar-limpar.md#2-capturar-a-linha-de-base-antes-do-grupo-exclusivo)
explica a recusa, sem contorno por edição de arquivos ou recriação do grupo.

O ambiente Container Apps pode ter um grupo gerenciado. Retire o ambiente pelo serviço,
sem editar ou excluir componentes gerenciados manualmente [2].

## Etapa 1: conferir a recuperação

**Objetivo:** conservar a referência autorizada antes de retirar o candidato.
Trocar configuração ou tráfego **[altera o Azure]** exige autorização da aplicação; consultas
reais usam modelos e busca e podem cobrar. Leituras e retorno foram conferidos na rodada
histórica, não repetidos com este roteiro.

1. Retorne à configuração de referência.
2. Confira índice e dimensões compatíveis.
3. Execute uma consulta autenticada e a recusa correspondente.
4. Confira política, fontes e autenticação.
5. Registre o alcance da recuperação.

Trocar e retornar uma revisão da mesma imagem demonstra tráfego e configuração.
Isso não mede recuperação de incidente nem um objetivo de tempo de recuperação de produção.
Um checkpoint de workflow também não retoma automaticamente recursos Azure [3].

## Etapa 2: retirar consumidores e objetos

**Objetivo:** retirar somente o candidato e conservar as provas antes de encerrar o grupo.
Retirar tráfego ou excluir recursos **[altera o Azure]** exige aprovação dos responsáveis pelos
alvos. Serviços mantidos continuam cobrando; a remoção dos trechos do índice não tem restauração
direta pela ferramenta e uma reconstrução exige nova ingestão e embeddings, representações vetoriais.

| Ordem | Alvo e condição |
| --- | --- |
| Consumidores | Retirar tráfego e execuções próprias que usam o candidato |
| Pipeline candidato | Simular, conferir propriedade e remover indexador antes dos objetos dependentes |
| Conexões de saída próprias | Retirar links sem consumidores antes do serviço de busca e seus destinos |
| Aplicações e ambientes próprios | Caminho suportado; grupo gerenciado sob ciclo de vida da plataforma |
| Recursos exclusivos | Remover após conferir que não há consumidor preservado |

As linhas de conexões, aplicações, ambientes e recursos exclusivos pertencem ao encerramento
completo da etapa 3. Numa limpeza apenas do candidato, conserve as dependências da referência.
Não remova um serviço reaproveitado de outro proprietário como parte da limpeza de um índice.
Não use curingas para descobrir alvos de exclusão durante a execução.

1. Confira que nenhum consumidor preservado depende do candidato. Termine a coleta das provas
   antes de retirar o caminho ou a identidade usados na manutenção.
2. Preencha seu destino de busca e tenant somente na sessão. O nome abaixo é o candidato
   definido pelo curso; confirme-o contra sua implantação:

```powershell
$busca = '<nome-do-servico-de-busca>'
$tenant = '<GUID>'
$indiceCandidato = 'vareleira-lar-l300-l400-768'
.\.venv\Scripts\python.exe scripts\gerenciar_ingestao_l300.py --etapa remover `
    --busca $busca --tenant-id $tenant --indice $indiceCandidato
if ($LASTEXITCODE -ne 0) { throw 'A simulacao foi recusada. Preserve os objetos e revise o alvo.' }
```

Esse comando **lê o Azure e simula**; não é uma etapa offline do planejador de encerramento.
`<GUID>` representa um identificador globalmente único e precisa ser substituído pelo seu valor
na sessão. Para um destino que só é alcançável dentro da rede, consulte os guias existentes de
[dependências privadas L300](../L300/04-dependencias-privadas.md) e
[operação L300](../L300/06-conferir-operacao.md), sem reabrir acesso público para limpar.

3. Revise marcador de propriedade, versões e os quatro nomes. Com tráfego retirado e autorização
   de dados para esses alvos, **[altera o Azure]**:

```powershell
.\.venv\Scripts\python.exe scripts\gerenciar_ingestao_l300.py --etapa remover `
    --busca $busca --tenant-id $tenant --indice $indiceCandidato --executar
if ($LASTEXITCODE -ne 0) { throw 'A remocao nao foi concluida. Registre o ponto e confira o estado.' }
```

4. Confira ausência e preservação. O gerenciador retira indexador, skillset, fonte de dados e
   índice derivados de `$indiceCandidato`, nessa ordem de dependência, não os objetos da referência.
   Blobs, conta de modelos, deployments, serviço de busca, grupo, identidades e credenciais
   continuam fora dessa remoção.

**Resultado esperado:** quatro objetos candidatos ausentes, referência conservada e provas
privadas guardadas antes de excluir aplicações, Jobs ou logs próprios. A simulação e a remoção
granular não autorizam o encerramento do grupo.

## Etapa 3: encerrar acesso e custo

**Objetivo:** encerrar os temporários administrativos, com ausência real e preservação anterior.
**Autorização e custo:** exclusões Azure e alterações Entra exigem aprovações próprias, inclusive
dos efeitos permanentes. A ferramenta só planeja e confere arquivos; recursos restantes seguem
cobrando. Encerre também processos locais próprios pelo identificador do processo.

### Roteiro administrativo revisado de encerramento completo

A sequência, as variáveis PowerShell, os comandos de geração e os critérios estão no
[roteiro administrativo L300](../L300/07-recuperar-limpar.md#roteiro-administrativo-revisado-de-encerramento-completo) [5].
Siga seus passos 1 a 8, usando assinatura, tenant, grupo, pasta e inventário **da sua rodada L400**.
Os blocos são comuns; as decisões específicas abaixo delimitam seus alvos, sem duplicar comandos
de exclusão.

1. **Antes da criação**, prepare o inventário privado e capture as três listas da linha de base,
   revisando e executando apenas os blocos de leitura impressos. O grupo exclusivo e os recursos
   próprios não podem estar nessa base. Se a captura faltou, a prévia ainda valida a estrutura
   do inventário e as leituras atuais podem conferir ausência; a preservação anterior permanece
   pendente e o fluxo suportado de execução completa fica bloqueado.
2. **Durante cada criação autorizada**, registre os itens próprios conforme o esquema versão 1:

| Alvo L400 | Cobertura da ferramenta e decisão do operador |
| --- | --- |
| Aplicação L400 e Jobs próprios | `{id,tipo}` em `recursos_proprios`; têm passos próprios na fase de consumidores. Guardar provas e retirar tráfego antes de excluir |
| Referência recriada no grupo temporário | Só inventariar se foi criada nesta rodada e o encerramento completo a inclui. A aplicação e os recursos L300 preexistentes fora desse grupo são preservados |
| Deployment de contingência | Quando pertence à conta própria do grupo exclusivo, registrar o recurso aplicável e a conta. Não há passo dedicado para excluir só um deployment: ele sai com a conta na exclusão do grupo |
| Conta de modelos própria | Recurso no grupo e item `conta_de_modelos` em `expurgos`, com nome, região e grupo exatos. Expurgo é permanente; conservar modelos e versões da referência não significa conservar essa conta temporária |
| Índice candidato de 768 dimensões | Não é um recurso ARM inventariado pelo planejador. A etapa 2 usa o gerenciador de ingestão para os quatro objetos; a prova granular é responsabilidade do operador |
| Links de saída próprios da busca | Lista `shared_private_links`; retirar e conferir antes da busca e dos destinos, sem apagar conexões alheias |
| Workspace de logs e ambientes próprios | Recursos com seus tipos; exclusão permanente do workspace e retirada dos ambientes pelo serviço. O grupo gerenciado é só observado, nunca manipulado |
| Aplicativos, credenciais, principais e atribuições | Listas próprias do esquema; `objeto_id` e `principal_id` são IDs de objeto, nunca `clientId`/`appId`. `app_id` é o cliente do aplicativo. Atribuições somente no escopo exclusivo e de principais próprios; IDs de credencial, nunca segredos |
| Cofre próprio, se existir | Item `cofre_de_chaves` em `expurgos`; a guarda confere a origem no grupo exclusivo. Proteção contra expurgo não é removida |

As listas principais são obrigatórias, mesmo vazias. O modelo inicial tem marcadores e
`grupo_exclusivo` definido como `false` de propósito; preencha-o, não relaxe as guardas.
Tipos de recursos sem passo próprio são removidos com o grupo, não por comandos individuais.
A ferramenta não inventaria automaticamente consumidores, configurações, objetos de busca
ou dependências compartilhadas.

Em `principais_proprios`, use `principalId` da identidade gerenciada ou `id` de objeto do
principal de serviço. O `id` de uma identidade gerenciada é o caminho do recurso Azure e tem
outro uso. A
[tabela de identificadores L300](../L300/04-dependencias-privadas.md#1-preparar-identidades-papéis-e-conexões)
e o [passo do inventário](../L300/07-recuperar-limpar.md#1-preparar-o-inventário-privado-desde-o-início)
explicam a diferença entre ficha de objeto, identificação de cliente e endereço do recurso [10].
Cada GUID só pode ocupar uma função no inventário; misturar principal, objeto, cliente,
credencial, assinatura, tenant ou definição de papel é recusado, sem publicar os valores [7].
Referenciar o mesmo principal nos campos corretos continua válido; repetir credencial entre
identidades não é válido. Um GUID distinto e bem formado pode estar errado sem que a validação
offline perceba: confirme as leituras de criação e a presença antes de apagar.

**Atenção:** se a conta de modelos for preexistente ou compartilhada, seu ID não pertence ao
inventário de exclusão do grupo L400. A remoção **isolada** do deployment de contingência continua
responsabilidade do operador, com procedimento específico revisado e autorização
**[altera o Azure]**; o planejador não imprime esse comando. Confira a operação aplicável no
[Desafio 03](03-operar-deployments.md) e com a administração, sem excluir a conta como atalho.
O mesmo limite vale para qualquer alvo próprio que esteja fora do grupo exclusivo.

3. **Depois da limpeza granular**, gere e revise o plano administrativo local contra a base
   anterior. A ordem é consumidores, links da busca, objetos Entra, atribuições próprias, logs,
   ambientes, grupo exclusivo e expurgos. Com autorização de leitura, cole primeiro a
   **Preparação inteira na mesma janela PowerShell 7** e faça a
   [conferência cruzada de IDs e presença](../L300/07-recuperar-limpar.md#4-executar-os-comandos-revisados-um-bloco-por-vez):
   objetos ainda ativos devem responder `presente`, e as leituras precisam confirmar seus IDs
   e relações. Não use uma captura prévia como estado final. Depois de autorizar as remoções,
   execute manualmente **um bloco inteiro por vez**: fases de recursos **[altera o Azure]**, fase de identidade
   **[altera o Microsoft Entra ID]**. Confira código de saída, avisos e a verificação de ausência
   impressa antes de continuar. Não remova bloqueios, manipule o grupo gerenciado, use curingas
   ou execute automaticamente a saída da ferramenta.
4. **Depois das operações**, gere a captura final, revise e execute o bloco completo de leitura
   no PowerShell 7, mantendo as provas prévias separadas.
   Rode a conferência com os seis instantâneos e a presença aplicável. Código 0 em `conferir`
   significa critérios aplicáveis atendidos nos arquivos; código 3 significa reprovado ou
   pendente. Código 1 é uso ou guarda recusando; 4 é defeito. Um plano com código 0 ainda pode
   ser apenas prévia. Guarde relatórios novos, sem sobrescrever os anteriores.

Um comando de espera que retorna 0 não substitui a listagem real. Grupos e recursos anteriores
precisam continuar presentes; atribuições anteriores, inclusive fora do grupo, precisam conservar
ID, principal, definição e escopo. A conferência não compara todas as configurações do L300,
não garante ausência de objetos não inventariados e não mede custo.

Os comandos e verificações dos passos e a verificação do grupo gerenciado no fechamento só
executam depois da Preparação na mesma sessão PowerShell 7. No Windows PowerShell 5.1 ou em
outra janela sem Preparação, emitem aviso e não executam o corpo; a verificação recusada responde
`indeterminado`. Aviso e `$LASTEXITCODE` residual não provam ausência. A marca é uma variável
de sessão: ela não revalida a conta se você a trocar depois. Mantenha conta, assinatura e tenant
inalterados até o fim; se a sessão ou o destino mudar, confira novamente e conclua a Preparação
antes de qualquer passo, sem preencher a marca manualmente.

A guarda de papel exige leitura bem-sucedida com exatamente uma atribuição daquele ID e
principal de objeto, escopo e definição iguais ao inventário. As guardas de aplicativo e
principal de serviço conferem o `id` de objeto e o `appId`; a do aplicativo também confere o
nome. Sucesso na leitura é obrigatório. Use os blocos que a ferramenta imprime, sem retirar
condições ou substituir IDs para vencer uma guarda.

Consulte custo por leitura autorizada no Cost Management, com período, moeda e grupos explícitos.
A ferramenta não imprime comando de custo; resposta vazia, erro ou valor sem comprovação deve
ficar **indisponível**, não zero. Não deixe serviços próprios ativos esperando a fatura.

Se um passo falhar, preserve o inventário e a tentativa e retome do último ponto ainda necessário,
sem repetir remoções já comprovadas. A guarda histórica de papéis recusou atribuições fora do
alvo; esse conflito e a retomada continuam no [registro L400](../../docs/validacao/l400-validacao.md#encerramento-verificado) [9].
No Graph, `indeterminado` nunca comprova ausência; na conferência final, `presente` reprova o
critério. Na conferência prévia de um objeto ativo, `presente` é o resultado esperado.
Investigue recusa de bloco, IDs de objeto, autorização e propagação antes de repetir somente
a leitura aplicável. A
[orientação de retomada L300](../L300/07-recuperar-limpar.md#7-retomar-uma-falha-sem-repetir-o-que-já-terminou)
explica como renovar presença ou capturar em outra pasta sem sobrescrever provas.

**Resultado esperado:** ausência dos temporários próprios e dos objetos recuperáveis
inventariados com IDs de objeto corretos, Preparação e blocos íntegros na mesma sessão sem troca
de conta, referência anterior preservada no alcance conferido e custo disponível ou
explicitamente indisponível. Sem base ou prova de presença, o encerramento não recebe aprovação
completa quando essas provas são exigidas. Este roteiro foi revisado por leitura; sua execução
Azure permanece não realizada.

## Como pedir uma mudança ao Copilot no VS Code

Abra a prévia Markdown e anexe este guia, o roteiro de encerramento L300 e os dois scripts
públicos. Use cópias sanitizadas de plano e inventário: substitua IDs por `<GUID>` e nomes
privados por marcadores, sem anexar instantâneos brutos, credenciais ou tokens.
Mantenha marcadores distintos para alvos distintos e repita o mesmo marcador para o mesmo alvo
nos dois arquivos. As cópias são contexto de leitura, não inventários executáveis.

```text
Anexo plano de encerramento e inventário sanitizado, sem IDs reais.
Revise por leitura o esquema, a base anterior ao grupo e a exclusividade L400.
Confira consumidores, links, papéis por ID e escopo, identidade, expurgos e provas.
Confira funções dos GUIDs, IDs de objeto versus cliente e Preparação na mesma sessão.
Separe presença prévia de ausência final e explique o limite da validação offline.
Distinga aplicação L400, contingência e candidato da referência L300 preservada.
Explique o que a ferramenta cobre e o que depende de procedimento do operador.
Separe rollback, exclusão, expurgo e prova de ausência.
Liste decisões humanas e critérios reprovados ou pendentes, sem preencher marcadores.
Não execute comandos, acesse Azure ou Entra ID, revogue acesso ou remova bloqueios.
Não gere um executor de remoções nem reexecute os conjuntos finais de avaliação.
```

Confira a análise contra o código público. Revise alterações propostas no diff em
**Source Control** e confira cada alvo antes de uma execução autorizada.
O modelo do Copilot ajuda a revisão, não escolhe destino, permissão ou expurgo.

## Conferência do resultado

| Conferência | Evidência |
| --- | --- |
| Retorno | Consulta e recusa na configuração de referência |
| Objetos candidatos | Ausentes sem modificar a referência |
| Recursos próprios | Ausência em leituras reais, não apenas aceitação do pedido |
| Acesso temporário | Credenciais e papéis próprios encerrados |
| Preservação | Mesmos recursos, grupos e papéis anteriores |
| Custo | Período, moeda e dados disponíveis ou indisponibilidade explícita |
| Plano público | Base anterior válida, inventário exclusivo e efeitos revisados; nada executado pela ferramenta |
| Conferência completa | Seis instantâneos e presença aplicável; aprovado apenas nos critérios verificáveis |
| Contingência em conta preservada | Procedimento isolado do operador e prova própria; não há passo dedicado no planejador |
| IDs e sessão | Objetos ativos presentes antes de apagar, IDs lidos conferidos e Preparação na mesma janela PowerShell 7, sem troca de conta |

Testes com dublês conferem decisões locais, não o estado de serviços reais.
As verificações do planejador usam IDs e tipos de recursos e os campos das atribuições;
configurações, consumidores e objetos candidatos exigem suas evidências próprias.

## Solução de problemas

| Sintoma | Ação |
| --- | --- |
| Busca não pode ser excluída | Confira e retire somente os links próprios autorizados antes de retomar |
| Grupo continua após espera | Leia estado, recursos e histórico de falhas |
| Listagem inclui papéis fora do grupo | Preserve esses papéis; restrinja a limpeza ao escopo e aos principais próprios inventariados |
| Referência perdeu acesso | Confira caminho privado e configuração, sem reabertura automática |
| Consulta de custo não retorna linhas | Conserve a incerteza; não mantenha temporários esperando cobrança |
| Grupo L400 já consta na base | Use uma captura anterior íntegra se existir; caso contrário, mantenha prévia e preservação pendente, sem editar a base |
| Conta compartilhada aparece como alvo | Preserve-a; revise procedimento específico da contingência, sem ampliar o encerramento do grupo |
| Objeto candidato não tem marcador próprio | Interrompa a remoção e confira proprietário e índice; a ferramenta não deve apagar um objeto alheio |
| Guarda do grupo encontra item não inventariado | Pare e confira a propriedade real, preservando versões; não acrescente recursos alheios para passar |
| Bloco só avisa e não executa | Abra `pwsh`, conclua a Preparação na mesma janela e cole o bloco inteiro; recusa ou código residual não comprova ação |
| GUID em duas funções ou credencial repetida | Releia os campos citados e a prova de criação; preserve a distinção entre IDs de objeto, principal, cliente e demais funções |
| Presença prévia retorna `ausente` | Confira ID de objeto, tenant e relações antes de apagar; `clientId` consultado como objeto pode dar 404 falso |
| Presença Graph indeterminada | Confira versão, Preparação, ID de objeto, tenant, autorização e propagação; execute nova captura inteira em pasta inédita, sem repetir expurgo já comprovado |
| Guarda de papel ou identidade recusa a leitura | Confira sucesso da leitura, correspondência dos IDs e exatamente uma atribuição alvo; preserve objetos e papéis alheios |
| Arquivo final ou relatório já existe | Preserve a evidência e use outra pasta ou nome novo; não substitua a linha de base |
| Cofre protegido contra expurgo | Registre pendência e respeite a retenção; não remova a proteção |
| Conferência reprovada por alteração de terceiro | Investigue a divergência com o proprietário, mantendo base e resultado originais |

## Custos, pausa e limpeza

Conservar a referência durante a migração tem custo e prazo próprios.
Encerrar o terminal ou escalar uma aplicação a zero não remove busca, modelos, registro,
DNS (sistema de nomes de domínio) e logs.
Os recursos anteriores continuam sob seus proprietários; a rodada encerra somente seus temporários.
Os relatórios de plano e conferência são novos e sanitizados; evidências completas têm retenção
privada própria. Custo continua separado da aprovação de ausência. O teto histórico não autoriza
um novo orçamento, e uma resposta sem dados deve ficar registrada como indisponível.

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

O roteiro público foi acrescentado em 11 de outubro de 2026, por leitura do código e dos
registros. A ferramenta pública tem testes locais com dublês, inclusive execução no PowerShell 7
e recusa no Windows PowerShell 5.1 com interface Azure CLI falsa [8]. As guardas de função dos GUIDs,
identidade e sessão foram incorporadas por leitura e geração de planos e capturas sintéticos.
Ela não foi usada no encerramento histórico, que empregou um script privado diferente.
O roteiro novo não foi executado no Azure e os conjuntos finais não foram repetidos.
Projeção `id:id` de `--query`, formatos reais das respostas, conclusão dos links e semântica da
listagem de papéis por escopo permanecem pendentes de qualificação autorizada.
A remoção isolada da contingência em conta compartilhada e qualquer alvo fora do grupo exigem
decisão e procedimento próprios do operador.

## Glossário e referências

| Termo | Significado |
| --- | --- |
| Rollback | Retorno à configuração anterior |
| ARM | Administração dos recursos Azure |
| Expurgo | Remoção do estado recuperável do objeto |
| Consumidor | Aplicação ou processo que depende de um recurso |
| Linha de base | Inventário anterior usado para conferir preservação |
| Instantâneo | Exportação de estado; os arquivos anteriores devem preceder a criação do grupo |
| Azure CLI | Interface de linha de comando; o planejador só imprime comandos para ela |
| JSON | Formato de dados estruturados do inventário e das evidências |
| GUID e ID | Identificador globalmente único e identificador de um objeto ou recurso |
| Deployment de contingência | Implantação adicional do modelo, separada da geração de referência |
| Namespace candidato | Nomes dos quatro objetos de busca derivados do índice candidato |
| RBAC e escopo | Acesso baseado em papéis e o alvo ao qual a atribuição se aplica |
| Principal de serviço e tenant | Representação do aplicativo e seu diretório Microsoft Entra ID |
| Microsoft Graph e HTTP 404 | Interface dos objetos Entra e ausência condicionada a tenant e ID de objeto corretos |
| Presença indeterminada | Leitura ou bloco recusado sem prova suficiente de presença ou ausência |
| Grupo gerenciado | Grupo sob ciclo de vida do Container Apps, nunca manipulado manualmente |
| Job e workspace | Execução de tarefa no Container Apps e área de armazenamento de logs no Log Analytics |
| ID de objeto e ID de cliente | `id` do aplicativo/principal ou `principalId` da identidade localiza o objeto Entra; `appId`/`clientId` identifica o cliente para autenticação |
| Função do GUID | Categoria do identificador no inventário; categorias distintas não compartilham o mesmo GUID |
| Preparação e sessão | Conferência inicial vinculada à janela PowerShell 7; a marca não revalida a conta em cada passo |
| Comando composto e presença prévia | Bloco agrupado com guardas e leitura de objetos ativos antes da remoção, esperando `presente` |

1. [Exclusão e diagnóstico de links compartilhados](https://learn.microsoft.com/en-us/azure/search/troubleshoot-shared-private-link-resources#deleting-a-shared-private-link-resource).
2. [Rede e recursos gerenciados de Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/custom-virtual-networks).
3. [Checkpoints de workflows](https://learn.microsoft.com/en-us/agent-framework/workflows/checkpoints).
4. [Cobrança de Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/billing).
5. [Roteiro administrativo público, esquema e critérios L300](../L300/07-recuperar-limpar.md#roteiro-administrativo-revisado-de-encerramento-completo).
6. [Interface do planejador de encerramento](../../scripts/planejar_encerramento.py).
7. [Contrato e guardas do encerramento](../../scripts/lab_encerramento.py).
8. [Testes locais com dados sintéticos](../../tests/test_encerramento.py).
9. [Falha e retomada do encerramento histórico L400](../../docs/validacao/l400-validacao.md#encerramento-verificado).
10. [Identificadores da identidade gerenciada L300](../L300/04-dependencias-privadas.md#1-preparar-identidades-papéis-e-conexões).

## Autoria

Texto por GPT-6.1 Sol; código por Claude Sonnet 5.5. Encerramento do experimento não homologa produção.

Revisão documental por gpt-6-astra (Astra), em 11 de outubro de 2026, sem nova execução Azure.

Roteiro de encerramento: GPT-6.1 Sol, com Astra indisponível, em 11 de outubro de 2026;
ferramenta pública por Claude Sonnet 5.5; revisado por leitura; sem execução Azure.

Sincronização final do roteiro: GPT-6.1 Sol, com Astra indisponível, em 11 de outubro de 2026;
adequação às guardas de IDs e sessão da ferramenta de Claude Sonnet 5.5, por leitura e
conferência local; sem execução Azure.
