# L300 — Desafio 07: recuperar a aplicação e encerrar os objetos do nível

[Início do laboratório](../../README.md) · [Desafio 06](06-conferir-operacao.md)

| Item | Descrição |
| --- | --- |
| Situação | Encerramento Azure histórico; roteiro de IDs e sessão revisado por leitura; ferramenta testada localmente, sem nova execução Azure |
| Público | Operações, arquitetura e desenvolvimento, com autorização dos responsáveis pelos alvos |
| Resultado | IDs de objeto conferidos antes das remoções, blocos revisados na mesma sessão e encerramento próprio comparado com a linha de base |
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
- [Roteiro administrativo revisado de encerramento completo](#roteiro-administrativo-revisado-de-encerramento-completo)
- [Como pedir uma mudança ao Copilot no VS Code](#como-pedir-uma-mudança-ao-copilot-no-vs-code)
- [Conferência do resultado](#conferência-do-resultado)
- [Solução de problemas](#solução-de-problemas)
- [Custos, pausa e limpeza](#custos-pausa-e-limpeza)
- [Situação da validação](#situação-da-validação)
- [Glossário](#glossário)
- [Referências](#referências)
- [Autoria](#autoria)

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
5. Preparar um inventário privado, revisar os comandos impressos e distinguir ausência,
   preservação comprovada e conferência pendente.

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
| [Planejador de encerramento](../../scripts/planejar_encerramento.py) | Público; valida arquivos e imprime modelo, captura, plano e conferência, sem chamar o Azure ou excluir objetos |
| [Contrato do encerramento](../../scripts/lab_encerramento.py) | Esquema versão 1, guardas, fases e critérios da conferência |
| [Testes do encerramento](../../tests/test_encerramento.py) | Dublês locais, dados sintéticos, execução em PowerShell 7 e recusa no Windows PowerShell 5.1 com interface de linha de comando falsa |

Um **namespace** reserva nomes e caminhos ao nível. Use o gerenciador L300 para seus objetos.
A ferramenta L200 conserva o namespace anterior. `operar_l300.py` confere planos e evidências,
sem etapa de exclusão ou opção `--executar`.
O inventário de encerramento e os instantâneos são arquivos que o aluno produz em local privado;
não são arquivos prontos do repositório. O planejador também não tem opção `--executar`.
Ele pode gravar um relatório novo e sanitizado quando recebe `--relatorio`; o plano completo
continua privado.

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

O **Azure CLI** (*Azure Command-Line Interface*) é a interface de linha de comando do Azure.
O planejador imprime comandos para essa interface; quem os revisa e executa é o operador.
Um **inventário** registra identificadores (IDs), tipos e propriedade dos alvos. A **linha de
base** registra o que existia antes do laboratório; um **instantâneo** é uma exportação de
estado em determinado momento. Um **hash** é um resumo calculado do conteúdo de um arquivo,
usado para reconhecer alterações, não para conceder autorização.

O **Microsoft Entra ID** administra identidades no tenant. Um **principal de serviço** representa
um aplicativo nesse diretório; identidades gerenciadas também têm principais associados.
O **RBAC** (*Role-Based Access Control*, controle de acesso baseado em papéis) do Azure relaciona
principal, definição de papel e escopo. Remover o aplicativo não comprova a retirada de todas
as suas atribuições Azure.

**Expurgo** é a remoção permanente do estado recuperável de um objeto. O **Microsoft Graph**
é a interface de acesso aos objetos do Entra ID. Na conferência individual, o código
**HTTP** (*Hypertext Transfer Protocol*, protocolo de transferência de hipertexto) 404 significa
objeto ausente somente se a consulta usa o tenant e o ID de objeto corretos.
Usar um ID de cliente no lugar do ID de objeto pode devolver 404 mesmo com o objeto presente;
uma falha de autorização também não significa ausência.

Um **Job do Container Apps** executa uma tarefa no ambiente, como uma atividade de manutenção.
Ele é um consumidor que precisa ser encerrado antes de suas dependências, depois de conservar
as provas e terminar a manutenção autorizada.

## Pré-requisitos

Conserve inventário anterior, revisão aprovada, parâmetros, imagem, destinos e evidências em
local privado. Abra o projeto no Visual Studio Code (VS Code), selecione `.venv` e use PowerShell 7.
A revisão local do plano dispensa login.
Abra o PowerShell 7 com `pwsh` antes de definir as variáveis. Os comandos e verificações dos
passos impressos exigem a Preparação concluída na mesma janela; conserve a conta, a assinatura
e o tenant até o fim da sequência. As capturas têm sua própria guarda de versão.
O **tenant** é o diretório de identidades, separado da assinatura de recursos.
O **DNS**, sistema de nomes de domínio, mantém a resolução dos serviços na rede.

Qualquer execução externa exige assinatura Azure ativa e autorização dos alvos. Separe remoção
de objetos de busca, blobs, recursos Azure e configurações Entra ID/GitHub.
Confirme dependências compartilhadas antes de iniciar a limpeza.
Para o encerramento completo, obtenha autorização escrita de quem responde pela assinatura e,
para os objetos do Entra ID, de quem administra esses alvos no tenant. A autorização deve cobrir
exclusões permanentes e expurgos, não apenas leitura. As permissões precisam permitir as leituras
da assinatura e dos papéis, as alterações dos recursos próprios e as operações Graph indicadas
no plano. A remoção granular da busca exige também autorização de dados. Login bem-sucedido não
comprova nenhuma dessas permissões.
Execute cada comando separadamente, confira `$LASTEXITCODE` e interrompa a sequência diante de
falha. Dentro da rede, os exemplos do gerenciador podem usar a identidade gerenciada autorizada:
substitua `--tenant-id $tenant` por `--identidade-gerenciada --client-id $clientId`,
como no Desafio 02, sem combinar as opções.
Esse `clientId` seleciona a credencial de execução; não o copie para os campos de objeto
do inventário de encerramento.

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
O retorno do pedido de exclusão não comprova conclusão: confira a ausência na listagem do
serviço [7]. O [roteiro administrativo abaixo](#roteiro-administrativo-revisado-de-encerramento-completo)
usa a ferramenta pública para revisar a ordem dos demais alvos. Ela imprime os comandos,
mas nunca os executa; o gerenciador acima continua limitado aos quatro objetos de busca.

Na rodada de validação, excluir o grupo inteiro removeu o armazenamento antes da busca.
O serviço então recusou sua exclusão com `LockedSPLResourceFound`, pois não conseguiu conferir
bloqueios no destino já ausente. A recuperação removeu somente os dois links próprios e retomou
o encerramento. Não remova bloqueios administrativos nem recrie recursos como correção automática.

## Etapa 4: encerrar acesso e custos

1. Confira ausência dos objetos próprios e continuidade das dependências preservadas.
2. O administrador retira atribuições próprias **[altera o Azure]** e configurações temporárias
   autorizadas de identidade **[altera o Microsoft Entra ID]**, conforme o inventário.
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

## Roteiro administrativo revisado de encerramento completo

**Objetivo:** encerrar um grupo exclusivo do laboratório, seus acessos e objetos recuperáveis,
sem apagar o que existia antes. Esta sequência serve também ao L400, com inventário e linha de
base próprios daquele exercício. A ferramenta pública trabalha somente com arquivos locais;
ela não confirma autorização, não descobre todos os consumidores e não mede custo [8][9].

**Atenção:** o roteiro foi revisado por leitura. A ferramenta tem testes locais com dublês,
inclusive execução no PowerShell 7 e recusa no Windows PowerShell 5.1 com uma CLI falsa [10].
Os encerramentos históricos usaram outro procedimento privado; seus conflitos e retomadas
continuam no [registro Azure L300][11].
Nenhuma execução deste novo roteiro no Azure foi realizada nesta rodada. Os formatos reais das
respostas, a projeção `id:id` de `--query`, a conclusão da exclusão de links e o alcance real da
listagem de papéis por escopo continuam pendentes de qualificação em um destino autorizado.

### 1. Preparar o inventário privado desde o início

**Objetivo:** registrar os alvos quando são criados, sem tentar reconstruí-los por nomes no fim.
**Autorização e custo:** preparar arquivos é uma operação local, sem cobrança Azure. A criação
dos itens pertence aos desafios anteriores e exige autorização própria; esta seção não os cria.

1. Abra a raiz do projeto no VS Code e use seu terminal PowerShell 7.
2. Escolha uma pasta local de evidências fora do repositório, com acesso restrito. Substitua todos
   os marcadores abaixo pelos seus valores somente na sessão do terminal. `<GUID>` representa
   um identificador globalmente único; os marcadores não são destinos executáveis.
3. Prepare os caminhos. Os nomes de arquivos abaixo são os produzidos pela captura, não exemplos
   de evidências já existentes:

```powershell
$assinatura = '<GUID>'
$grupo = '<grupo-exclusivo-do-laboratorio>'
$pastaEncerramento = '<pasta-local-de-evidencias>'
$inventario = Join-Path $pastaEncerramento 'inventario.json'
$gruposAntes = Join-Path $pastaEncerramento 'grupos-antes.json'
$recursosAntes = Join-Path $pastaEncerramento 'recursos-antes.json'
$papeisAntes = Join-Path $pastaEncerramento 'papeis-antes.json'
$gruposDepois = Join-Path $pastaEncerramento 'grupos-depois.json'
$recursosDepois = Join-Path $pastaEncerramento 'recursos-depois.json'
$papeisDepois = Join-Path $pastaEncerramento 'papeis-depois.json'
$presencaDepois = Join-Path $pastaEncerramento 'presenca-depois.json'
$relatorioPlano = Join-Path $pastaEncerramento 'plano-relatorio.json'
$relatorioConferencia = Join-Path $pastaEncerramento 'conferencia.json'
```

4. Gere o modelo em **JSON** (*JavaScript Object Notation*, formato de dados estruturados).
   O PowerShell grava a saída; a ferramenta apenas a imprime. As orientações de preenchimento
   permanecem no terminal. Preserve um inventário já existente:

```powershell
if (-not (Test-Path -LiteralPath $pastaEncerramento -PathType Container)) {
    New-Item -ItemType Directory -Path $pastaEncerramento | Out-Null
}
if (Test-Path -LiteralPath $inventario) {
    throw 'O inventario ja existe. Preserve-o e revise a copia privada.'
}
.\.venv\Scripts\python.exe scripts\planejar_encerramento.py --etapa modelo |
    Out-File -LiteralPath $inventario -Encoding utf8 -NoClobber
if ($LASTEXITCODE -ne 0) { throw 'A geracao do modelo falhou.' }
```

5. Capture a linha de base no passo 2 **antes de criar o grupo**. Depois, mantenha o inventário
   atualizado durante cada criação autorizada:

| Campo do esquema versão 1 | Quando e o que registrar |
| --- | --- |
| `versao`, `assinatura`, `tenant`, `regiao`, `grupo` | Ao definir o destino; `versao` é 1. O tenant é obrigatório se houver `identidades_entra` ou `principais_proprios` |
| `grupo_exclusivo` | Atestar `true` somente depois de conferir que todo o grupo pertence ao laboratório. O modelo começa com `false` de propósito |
| `grupo_gerenciado` | Nome observado ao criar o ambiente Container Apps, se houver; é apenas conferido como ausente, nunca manipulado |
| `recursos_proprios` | Cada recurso criado no grupo exclusivo, com `{id,tipo}`; incluir aplicações, Jobs, ambientes, workspace de logs, rede, armazenamento, busca, registro e modelos que sejam próprios |
| `shared_private_links` | Cada conexão de saída própria da busca, com `{id}`; registrar também destino e consumidores na evidência privada de criação |
| `principais_proprios` | IDs de **objeto** dos principais próprios: `principalId` da identidade gerenciada ou `id` do principal de serviço; nunca `clientId` ou `appId` |
| `atribuicoes_proprias` | Após cada concessão autorizada: `{id,escopo,principal_id,papel_id}`. `principal_id` é o ID de objeto já listado em `principais_proprios`; escopo próprio e definição de papel precisam conferir |
| `identidades_entra` | `objeto_id` é o `id` de objeto do aplicativo; `app_id` é seu `appId`, outro GUID. Registrar nome exato sem espaços, `principal_id` de objeto do principal de serviço e IDs de credencial em `chaves`, quando houver; nunca segredos |
| `expurgos` | Ao criar itens recuperáveis próprios: `conta_de_modelos` com nome, região e grupo exclusivo; `cofre_de_chaves` com nome e região |

Todas as seis listas principais são obrigatórias; use `[]` quando não houver itens.
`principal_id` e `chaves` de um aplicativo podem ser omitidos se não se aplicarem. Campos
desconhecidos são recusados. Links e atribuições têm suas próprias listas; não os duplique em
`recursos_proprios`. Não inclua componentes do grupo gerenciado nem recursos compartilhados.
Use as orientações impressas por `modelo` para conferir valores por leitura autorizada, sem
deduzir IDs.

**Lembre-se:** o nome `id` depende do objeto lido. Em uma identidade gerenciada, `id` é o
caminho completo do recurso Azure, usado em `recursos_proprios`; `principalId` é o GUID de
objeto do principal no Entra ID; `clientId` seleciona a identidade para autenticação e não serve
em `principais_proprios` ou `principal_id`. A
[tabela de identificadores do Desafio 04](04-dependencias-privadas.md#1-preparar-identidades-papéis-e-conexões)
mostra esses usos [12]. Nas leituras de aplicativo e principal de serviço, a propriedade `id` é o
GUID de objeto, enquanto `appId` é a identificação de cliente do aplicativo.

**Para guardar na memória:** pense no endereço de uma instalação, na ficha do responsável e
na etiqueta que o seleciona para entrar. O `id` do recurso localiza a instalação;
`principalId` localiza a ficha no diretório; `clientId` seleciona a identidade na autenticação.
Buscar uma ficha pelo número da etiqueta pode retornar “não encontrado” sem que a ficha tenha
sido removida. Por isso `objeto_id` e todos os campos `principal_id` exigem IDs de objeto.

Cada GUID tem uma única **função no inventário**: assinatura, tenant, principal, objeto de
aplicativo, cliente do aplicativo, credencial ou definição de papel. Reutilizar o mesmo GUID em
funções diferentes é recusado com código 1, inclusive entre identidades ou em `principais_proprios`;
a mensagem identifica apenas os campos envolvidos. Referenciar o mesmo principal da lista
na identidade correspondente e em suas atribuições é correto: a função continua sendo
principal. Isso não permite duplicar entradas na lista nem credenciais entre identidades.
A mesma definição de papel pode ser referenciada em atribuições diferentes, mantendo sua função.

Um GUID errado, mas distinto e bem formado, **não é detectável offline** [9]. Confira os valores
com as leituras impressas por `modelo` e com a prova de criação. Antes de apagar, faça também
a conferência cruzada de presença descrita no passo 4, esperando `presente` para cada objeto
próprio ainda ativo. Código 0 do plano e um 404 isolado não corrigem um inventário errado.

**Resultado esperado:** inventário privado preenchido com todos os recursos próprios, nomes
exatos, funções de GUID consistentes e IDs de objeto conferidos por leitura antes das remoções.
O modelo original é deliberadamente inválido até o preenchimento.
O inventário, o plano e os instantâneos contêm IDs reais: não os anexe ao Copilot, a issues ou ao
histórico Git. Guarde credenciais e tokens fora desses arquivos.

### 2. Capturar a linha de base antes do grupo exclusivo

**Objetivo:** conservar uma prova do estado anterior. **Autorização:** leitura da assinatura e
das atribuições de papel, com visibilidade suficiente para exportar as listas completas.
**Custo e efeito:** o gerador é local; os blocos impressos só leem o Azure e gravam arquivos
privados, sem criar serviços nem encerrar cobranças. Não há exclusão ou expurgo.

1. Antes de criar o grupo, peça os comandos de captura:

```powershell
.\.venv\Scripts\python.exe scripts\planejar_encerramento.py --etapa capturar --momento antes `
    --assinatura $assinatura --grupo $grupo --pasta $pastaEncerramento
if ($LASTEXITCODE -ne 0) { throw 'A geracao da captura falhou. Nada foi consultado no Azure.' }
```

2. Leia e cole o **bloco inteiro** impresso no PowerShell 7. A captura é um comando composto,
   agrupado sob uma condição: no Windows PowerShell 5.1 só emite aviso e não consulta nem grava.
   No PowerShell 7, confere que o grupo ainda não existe, lê grupos, recursos e papéis da
   assinatura e recusa sobrescrever arquivos. A captura tem guarda própria de versão e não
   depende da marca de Preparação do plano. **Gerar o bloco não o executa**; sua execução exige
   autorização de leitura.
3. Confira a gravação dos três arquivos. Eles devem conter listas JSON completas, com os campos
   projetados pela ferramenta, sem nomes de pessoas ou e-mails:

| Instantâneo | Campos usados |
| --- | --- |
| `grupos-antes.json` | `id`, `name` |
| `recursos-antes.json` | `id`, `type` |
| `papeis-antes.json` | `id`, `principalId`, `roleDefinitionId`, `scope` |

As atribuições herdadas lembram regras municipais que valem para todo o bairro, mas que um
morador não pode alterar. Assinaturas sob um grupo de gerenciamento podem trazer na listagem
atribuições da raiz do tenant e de grupos de gerenciamento. Com `id` e `scope` coerentes,
a ferramenta aceita esses itens, ignora-os e avisa apenas a contagem; não os altera nem compara,
portanto a conferência **não detecta mudanças neles**. Itens de outra assinatura, com `id` e
`scope` incoerentes ou de formato desconhecido continuam recusados com código 1. Na rodada
Azure de 11 de outubro de 2026, três das 20 atribuições eram herdadas; o validador anterior
as recusou, e a correção foi testada com os arquivos reais dessa rodada. A validação Azure
continua em andamento; o registro final virá depois.

Uma resposta com `nextLink`, endereço da próxima página, é recusada: a listagem precisa ser
completada por um método suportado. Não elimine páginas nem edite os instantâneos à mão para
passar na guarda. Se uma leitura falhar, a captura não comprova a linha de base.

**Para guardar na memória:** a linha de base funciona como a fotografia da sala antes de
montar a bancada do exercício. Fotografar depois não revela quais peças já estavam na sala.
Mesmo um grupo vazio criado antes da foto pertence ao estado capturado e bloqueia o plano.

| Situação encontrada | O que continua possível e o que fica pendente |
| --- | --- |
| Há uma captura íntegra anterior ao grupo | Usar os três arquivos originais, conservando sua proveniência |
| O grupo já foi criado e não há captura anterior | Validar o inventário e gerar apenas uma prévia sem a linha de base. Conferir o estado atual e a ausência dos alvos por leitura ainda é possível; comprovar preservação anterior fica pendente |
| O grupo consta na captura apresentada como `antes` | Plano e conferência recusam essa base com código 1. Não retire o grupo ou recursos do arquivo, não fabrique listas vazias e não recrie o grupo para contornar |
| As três listas anteriores estão vazias | O plano é prévia e a conferência fica pendente: pode ser a assinatura errada |

Sem uma base anterior válida, o fluxo suportado não autoriza executar o plano completo.
A remoção granular da etapa 3 mantém seu próprio contrato e pode ser autorizada separadamente;
ela não comprova preservação de grupos, recursos e papéis anteriores. A conferência completa
exige os seis instantâneos; faltar a base é erro de uso, não uma aprovação parcial.
Registre a lacuna e encaminhe a decisão de encerramento aos administradores, sem inventar um
contorno na ferramenta.

**Resultado esperado:** os três arquivos anteriores íntegros, capturados antes do grupo, com
assinatura e alcance de leitura conferidos. A criação posterior continua sujeita à sua autorização.

### 3. Gerar e revisar o plano, sem executar

**Objetivo:** conferir inventário, linha de base e ordem de remoção.
**Autorização, custo e efeito:** operação local, sem login, alteração Azure ou cobrança de
serviços. Produzir o plano não concede autorização para executá-lo.

```powershell
.\.venv\Scripts\python.exe scripts\planejar_encerramento.py --etapa plano --inventario $inventario `
    --grupos-antes $gruposAntes --recursos-antes $recursosAntes --papeis-antes $papeisAntes `
    --relatorio $relatorioPlano
if ($LASTEXITCODE -ne 0) { throw 'O plano foi recusado. Revise a entrada antes de continuar.' }
```

Informe os três arquivos anteriores juntos, nunca uma base parcial. Para estudar uma prévia,
omita os três e o relatório, mas mantenha `--inventario`; o aviso de prévia impede tratar código 0
como liberação para excluir. `--formato json` muda apenas a apresentação do plano, não o executa.
O relatório precisa ser novo e contém contagens por tipo e efeito, total e hash do inventário.

Revise a preparação e cada unidade de comando e verificação. Há 14 tipos de passo, organizados
nas oito fases abaixo; fases sem itens são omitidas, não comprovadas como concluídas [9].
Antes de encerrar consumidores usados na manutenção, conclua a remoção granular explicada no
passo 8.

| Fase | O que revisar antes da execução autorizada | Efeito e autorização | Resultado e custo |
| --- | --- | --- | --- |
| 1. Consumidores | Aplicações e Jobs próprios, tráfego retirado, provas salvas e nenhum consumidor preservado dependente | **[altera o Azure]**; exclusão irreversível desses recursos, autorizada por seus responsáveis | Consumidores ausentes; dependências mantidas continuam cobrando |
| 2. Shared private links da busca | ID, destino e proprietário de cada link; concluir antes da busca e dos destinos para evitar `LockedSPLResourceFound` | **[altera o Azure]**; remoção irreversível da conexão própria, sem retirar bloqueios administrativos | Links próprios ausentes na listagem; rede e serviços restantes ainda podem cobrar |
| 3. Identidades do Entra ID | Leitura bem-sucedida com `id` de objeto e `appId` iguais ao inventário; para o aplicativo, também nome exato. Conferir credenciais e objetos em `directory/deletedItems`, área de objetos excluídos | **[altera o Microsoft Entra ID]**; revogar credenciais é irreversível. Aplicativo e principal podem ser recuperáveis até o expurgo, que é permanente. Exige administrador autorizado desses objetos | Credenciais revogadas, aplicativos e principais removidos e expurgados; não encerra sozinho serviços Azure |
| 4. Atribuições próprias | Leitura bem-sucedida trazendo exatamente uma atribuição com o ID inventariado, cujo principal de objeto, definição de papel e escopo também coincidem; preservar as demais | **[altera o Azure]**; revogação irreversível da atribuição, com autorização de acesso proporcional ao escopo | Atribuições próprias ausentes; papéis anteriores iguais. Revogação não encerra cobrança dos recursos |
| 5. Workspace de logs | Evidências já exportadas e workspace do Log Analytics, área de armazenamento e consulta de logs, exclusivo | **[altera o Azure]**; exclusão forçada permanente, autorizada também pelo responsável pela retenção | Workspace ausente e registros não recuperáveis; cobrança acumulada permanece sujeita à consulta |
| 6. Ambientes Container Apps | Aplicações e Jobs já retirados; ambiente próprio removido pelo serviço, não por seus componentes | **[altera o Azure]**; exclusão irreversível, autorizada para o ambiente próprio | Ambiente ausente por leitura; aguardar a plataforma, sem tocar o grupo gerenciado. Demais serviços continuam cobrando |
| 7. Grupo exclusivo | Todo recurso ainda presente consta no inventário e não é compartilhado. A guarda faz nova leitura antes da exclusão | **[altera o Azure]**; exclusão irreversível do grupo e dos recursos sem passo próprio, somente com autorização de encerramento completo | Grupo ausente; busca, armazenamento, registro, modelos e rede próprios saem com ele. Cobrança acumulada não é apagada |
| 8. Expurgos | Conta de modelos por nome, região e grupo; cofre de chaves com `vaultId`, identificador de origem, no grupo exclusivo | **[altera o Azure]**; expurgos permanentes, explicitamente autorizados. Proteção contra expurgo pode impedir a ação | Objetos ausentes das listas de excluídos; custo final permanece sujeito à consulta |

**Resultado esperado:** plano privado sem aviso de prévia, com propriedade, dependências,
efeitos irreversíveis e permissões revisados por uma pessoa. Recursos de outros grupos são
recusados. Um recurso ainda presente fora do inventário bloqueia a exclusão do grupo: investigue
sua propriedade, não amplie a lista apenas para vencer a guarda.

### 4. Executar os comandos revisados, um bloco por vez

**Objetivo:** aplicar somente o encerramento autorizado. As fases Azure levam a marcação
**[altera o Azure]**; os blocos de identidade levam **[altera o Microsoft Entra ID]**.
**Autorização:** os administradores aprovam por escrito assinatura, tenant, grupo, alvos, acessos
e expurgos. A autorização histórica do curso não vale para outra execução.
**Custo:** os serviços restantes continuam cobrando durante a execução e as esperas; respeite
prazo e orçamento aprovados. Os efeitos permanentes são os da tabela e de cada passo impresso.

1. Conserve fontes, relatórios e provas antes de remover aplicações, Jobs ou logs.
2. Abra `pwsh` e cole **primeiro a Preparação completa**, na mesma janela em que executa os passos.
   Ela confere a conta e, quando necessário, obtém um token Graph para o tenant do inventário.
   Aguarde sua conclusão; um aviso ou uma falha não libera os passos. Não publique o token.
   A marca da preparação é uma variável desta sessão, não uma revalidação da conta em cada
   comando. **Não troque conta, assinatura ou tenant entre a Preparação e o fim**; se trocar
   ou abrir outra janela, confira o destino autorizado e execute novamente a Preparação antes
   de qualquer passo. Não copie ou preencha a marca de sessão manualmente.
3. Antes de apagar, use somente as leituras impressas por `modelo` e os blocos inteiros
   **Verificar a ausência** dos alvos ainda ativos para cruzar o inventário com os objetos reais.
   Nessa conferência **prévia**, espere `presente`, não `ausente`, para cada alvo ativo. Confira
   também os IDs lidos e suas relações: presença sozinha não comprova propriedade.
   Para incluir os principais das identidades gerenciadas, pode gerar a captura
   `--momento depois` com o inventário, apontando `--pasta` a outra pasta privada inédita, e
   executar o bloco inteiro só por leitura antes das remoções. As entradas de aplicativos e
   principais ativos precisam estar `presente`; objetos ainda não excluídos não precisam
   constar em `directory/deletedItems` ou nas listas de expurgo. Essa captura prévia, apesar dos
   nomes de arquivo com `depois`, **não é o instantâneo final nem a linha de base**: conserve-a
   separadamente e não a forneça como estado final na conferência.
4. Copie somente o bloco **Executar (cole o bloco inteiro)** do primeiro passo ainda necessário.
   Execute-o por sua conta e responsabilidade, leia avisos e registre `$LASTEXITCODE` do comando externo.
   Erro, exceção ou guarda recusando exige parada, mesmo que nenhum alvo tenha sido alterado.
5. Execute o bloco inteiro **Verificar a ausência** daquele passo. Agora o resultado esperado
   é `ausente`, pois se trata da prova **posterior** à remoção. Continue apenas com ausência
   comprovada; `presente` exige acompanhar o estado e `indeterminado` exige investigar a leitura.
   Um código de saída 0, a aceitação de exclusão ou o fim de uma espera não substituem essa prova.
6. Registre em evidência privada passo, responsável, momento, efeito e resultado antes de avançar.
   Repita manualmente a verificação quando a plataforma ainda processar o pedido.

Comandos e verificações dos passos, inclusive a verificação do grupo gerenciado no fechamento,
são comandos compostos protegidos: no Windows PowerShell 5.1 ou sem Preparação nesta janela,
só avisam e não executam o corpo. A verificação recusada responde `indeterminado`, nunca
`ausente`. O `$LASTEXITCODE` pode continuar com o valor de um comando anterior; aviso, recusa e
valor residual não comprovam execução ou ausência. Cole cada bloco completo, sem recortar
as condições. A Preparação e as capturas verificam a versão por suas próprias guardas;
a captura não exige a marca de Preparação do plano.

Não encaminhe a saída do planejador a um mecanismo de execução, não execute todas as fases de
uma vez e não acrescente curingas. Não retire bloqueios, recrie dependências ou amplie permissões
como reação automática. O grupo gerenciado do Container Apps é somente conferido; se permanecer,
investigue o ambiente pelo serviço e encaminhe a pendência à administração.

**Resultado esperado:** IDs e presença cruzados antes de apagar, Preparação concluída na mesma
sessão sem troca de conta e cada passo necessário com execução autorizada e prova posterior
de ausência. Uma recusa de bloco não conta como ação concluída. Uma falha interrompe a sequência
no ponto real, sem produzir um registro de encerramento limpo.

### 5. Capturar o estado final e conferir os arquivos

**Objetivo:** verificar ausência e preservação depois das operações.
**Autorização:** leitura da assinatura, papéis, objetos Graph e itens recuperáveis indicados.
**Custo e efeito:** gerar e conferir são locais; executar a captura só lê serviços e grava
evidências privadas. Não há exclusão, expurgo ou garantia sobre a cobrança.

1. Peça os blocos de captura final. `--inventario` é obrigatório nesse momento:

```powershell
.\.venv\Scripts\python.exe scripts\planejar_encerramento.py --etapa capturar --momento depois `
    --assinatura $assinatura --grupo $grupo --pasta $pastaEncerramento --inventario $inventario
if ($LASTEXITCODE -ne 0) { throw 'A geracao da captura final falhou. Nada foi consultado no Azure.' }
```

2. Revise e execute o **bloco inteiro** impresso, somente por leitura e no PowerShell 7.
   A captura tem guarda própria de versão; quando usa Graph, inclui a conferência da conta e
   a obtenção do token do tenant. No Windows PowerShell 5.1 avisa e não consulta nem grava.
   Esse é o estado final real, não a captura prévia usada para cruzar IDs. O bloco produz
   `grupos-depois.json`, `recursos-depois.json` e `papeis-depois.json`, com os mesmos campos da
   base. Havendo objetos Entra ou expurgos, produz também `presenca-depois.json`.
   O Graph associa 404 a `ausente` somente com IDs de objeto e tenant corretos, sucesso a
   `presente` e outros resultados a `indeterminado`;
   nas listas de itens recuperáveis, uma leitura que falha também fica indeterminada.
   O arquivo de presença usa chaves lógicas calculadas, não IDs completos.
3. Rode a conferência local:

```powershell
.\.venv\Scripts\python.exe scripts\planejar_encerramento.py --etapa conferir --inventario $inventario `
    --grupos-antes $gruposAntes --recursos-antes $recursosAntes --papeis-antes $papeisAntes `
    --grupos-depois $gruposDepois --recursos-depois $recursosDepois --papeis-depois $papeisDepois `
    --presenca $presencaDepois --relatorio $relatorioConferencia
$codigoConferencia = $LASTEXITCODE
"Codigo da conferencia: $codigoConferencia"
```

Se não houver nenhuma categoria de presença no inventário, a captura não cria esse arquivo;
omita `--presenca` em vez de inventá-lo. Se houver alvos e a presença ainda não tiver sido
produzida, omitir `--presenca` registra as respectivas verificações como pendentes.
Informar um caminho de arquivo inexistente é erro de uso, código 1. Relatórios são novos;
em outra conferência, escolha outro nome privado para `$relatorioConferencia`, sem sobrescrever
o resultado anterior.

| Critérios da conferência | O que os arquivos precisam comprovar |
| --- | --- |
| Linha de base | Pelo menos um item entre as três listas; totalmente vazia fica pendente |
| Grupo próprio e grupo gerenciado | Ausentes, com o segundo critério aplicável somente quando informado |
| Grupos anteriores | Todos os nomes da linha de base continuam presentes |
| Recursos anteriores | Mesmos IDs e tipos; isto não compara todas as configurações dos serviços |
| Recursos próprios | Nenhum remanescente no grupo exclusivo ou gerenciado |
| Atribuições anteriores da assinatura | Mesmos IDs, principais, definições de papel e escopos, inclusive as anteriores fora do grupo; herdadas de escopos acima da assinatura não são comparadas |
| Atribuições próprias | Nenhum ID inventariado ou atribuição no escopo próprio permanece |
| Aplicativos, principais e objetos excluídos Entra | Ausentes no Graph, em verificações separadas do estado ativo e recuperável |
| Conta de modelos e cofre de chaves | Ausentes das listas de excluídos, quando inventariados |

Esses grupos de verificações correspondem aos 13 critérios do código [9]. Categorias sem alvos
são marcadas como não aplicáveis; retirar um alvo do inventário não comprova sua ausência.
A ferramenta compara os arquivos exportados, não o estado atual do Azure nem todos os objetos
externos ao inventário. Um 404 com `clientId` ou `appId` no lugar do ID de objeto pode produzir
um falso encerramento. O limite do relatório explicita essa condição: um GUID distinto e bem
formado não comprova que o objeto correto foi inventariado. A preservação de configurações e
consumidores exige também as provas operacionais dos desafios anteriores.

| Código de saída | Interpretação e ação |
| --- | --- |
| 0 | Etapa local concluída. Em `modelo`, o modelo ainda precisa ser preenchido; em `plano`, confira se é prévia. Em `conferir`, aprovado somente com todos os critérios aplicáveis atendidos |
| 1 | Uso inválido ou guarda recusando; corrija a entrada ou registre a lacuna, sem executar exclusões |
| 3 | Conferência reprovada ou pendente; leia os critérios, mantenha os temporários restantes sob decisão explícita e não declare encerramento aprovado |
| 4 | Defeito do script; interrompa. `--detalhes` ajuda o diagnóstico privado, mas pode conter dados do ambiente |

`presente` reprova o critério; `indeterminado` ou prova faltante deixa-o pendente. Havendo ambos,
o resultado geral é reprovado. Se os três arquivos finais forem idênticos, byte a byte, aos
anteriores, há um aviso mesmo que a conferência aprove: confirme exportações independentes,
pois informar o mesmo arquivo duas vezes produz a mesma aparência.

**Resultado esperado:** conferência aprovada apenas sobre evidências completas e válidas, ou
pendências e divergências explícitas. Mudanças de terceiros em itens anteriores podem reprovar
a preservação; investigue sem editar a base para ajustar o resultado.

### 6. Consultar custo e registrar a indisponibilidade

**Objetivo:** verificar cobrança acumulada e recursos ainda mantidos.
**Autorização:** leitura de custos concedida pelo responsável pela assinatura.
**Custo e efeito:** consulta de leitura; não exclui recursos nem apaga valores acumulados.

1. No Cost Management do portal, consulte a assinatura, o período da atividade, o grupo
   exclusivo e o grupo gerenciado, quando houver. Registre período, moeda e alcance da consulta.
2. Se os dados estiverem disponíveis, registre o valor observado, não uma estimativa como fatura.
   Se vierem vazios, com erro ou sem valor e moeda, registre **indisponível**, nunca zero.
3. Registre os recursos ainda mantidos, proprietário, prazo e decisão de orçamento.
   Não conserve serviços próprios ativos apenas para aguardar atualização da cobrança.

A ferramenta não imprime comando de custo e não verifica atendimento ao teto. Uma assinatura
sem recursos próprios remanescentes ainda pode receber cobranças anteriores. A consulta vazia
histórica permanece registrada como custo indisponível [11].

**Resultado esperado:** custo documentado com evidência ou indisponibilidade explícita, separado
do resultado da conferência de recursos.

### 7. Retomar uma falha sem repetir o que já terminou

**Objetivo:** continuar do ponto observado, preservando as tentativas.
**Autorização e custo:** novas leituras precisam do acesso correspondente; qualquer nova
alteração Azure ou Entra exige autorização vigente dos mesmos alvos. Serviços restantes ainda
podem cobrar. Expurgos mantêm seu efeito permanente, mesmo numa retomada.

1. Preserve o inventário inicial, plano e resultados; anote o último passo com prova de conclusão.
   Não retire do inventário alvos já excluídos, pois a conferência ainda precisa verificar sua ausência.
2. Se a sessão foi encerrada ou mudou, abra PowerShell 7 e conclua novamente a Preparação para o
   mesmo destino autorizado. Mantenha a conta inalterada e releia somente os estados necessários.
   Salte um comando concluído apenas com a prova conservada e a verificação atual aplicável;
   não trate um erro genérico como alvo já ausente.
3. Em `LockedSPLResourceFound`, volte à conferência dos consumidores e links próprios antes do
   grupo. A mensagem não prova um bloqueio administrativo real. Confira ausência dos links na
   busca, sem remover bloqueios ou recriar destinos [7][11].
4. Se a guarda de papéis recusar, confira uma leitura bem-sucedida com exatamente uma atribuição
   daquele ID e com principal de objeto, definição e escopo iguais ao inventário. Uma listagem
   pode trazer atribuições herdadas ou externas; preserve-as. As guardas de aplicativo e principal
   de serviço também conferem o ID de objeto lido e o `appId`; a de aplicativo confere ainda
   o nome, e ambas exigem sucesso da leitura. Não mude o alvo para a guarda passar.
5. Se a verificação retornar `indeterminado`, confira primeiro se houve recusa por versão ou
   falta de Preparação. Para uma leitura Graph efetivamente executada, investigue ID de objeto,
   tenant, permissão e estado. Após uma remoção, a propagação pode manter `presente` por um
   período; repita a leitura, não a exclusão ou o expurgo já comprovados.
6. Para renovar a presença, preserve ou renomeie `presenca-depois.json` e escolha outra pasta
   privada inédita para a captura. Execute novamente o **bloco completo** impresso e atualize
   todos os caminhos `Depois` e o nome novo do relatório. A captura recusa sobrescrever também
   os outros três instantâneos: retirar só a presença não libera a gravação completa.
   Não recorte o trecho Graph nem a gravação para ignorar a guarda do bloco.

Não transforme presença indeterminada em ausência nem use uma captura posterior como linha
de base anterior. Uma correção legítima do inventário exige conservar a versão original,
justificar a propriedade e revisar um plano novo contra a mesma base íntegra.

**Resultado esperado:** retomada manual com ações já feitas preservadas, nova prova para o
que faltava e pendências que permanecem visíveis até sua resolução.

### 8. Encaixar as ferramentas de operação antes do encerramento

**Objetivo:** distinguir limpeza granular de encerramento administrativo.
**Autorização e custo:** os planos locais não alteram serviços; executar a remoção granular
**[altera o Azure]** exige autorização dos quatro objetos de busca. Remover o índice elimina seus
trechos; reconstruí-los exige nova ingestão e consumo de embeddings, representações vetoriais.

| Ferramenta ou ação | Lugar na sequência e limite |
| --- | --- |
| `gerenciar_ingestao_l300.py --etapa remover` | Na etapa 3, depois de retirar o tráfego consumidor e antes de perder a identidade ou o caminho de manutenção; sem `--executar`, lê o Azure e simula |
| Remoção granular autorizada | Retira indexador, skillset, fonte de dados e índice do namespace próprio; não retira blobs, grupo, serviços, identidade ou credencial |
| `operar_l400.py --etapa planejar --passo limpeza` | No L400, prepara o escopo funcional do candidato sem rede; não é o plano administrativo de exclusão |
| `planejar_encerramento.py --etapa plano` | Depois das provas e da revisão do inventário, imprime as fases do encerramento completo; não executa nenhuma delas |

Quando for necessário operar dentro da rede, consulte os guias de
[dependências privadas](04-dependencias-privadas.md) e
[conferência da operação](06-conferir-operacao.md). O
[Desafio 07 L400](../L400/07-recuperar-limpar.md) delimita aplicação, contingência e candidato.

**Resultado esperado:** provas da limpeza granular conservadas antes da retirada dos
consumidores administrativos, e nenhum serviço compartilhado excluído como consequência de
remover apenas um índice.

## Como pedir uma mudança ao Copilot no VS Code

Peça alvos e conferências antes de pedir código. Em uma mudança de limpeza, exija teste
para marcador ausente, ETag alterado e recurso de outro nível.
Revise o diff em **Source Control** e mantenha a simulação como padrão.
O pedido de gerar o plano não autoriza sua execução.

Para revisar o encerramento, abra a prévia Markdown deste guia e anexe os dois scripts públicos.
Prepare versões sanitizadas do inventário e do plano, substituindo todos os IDs reais por
`<GUID>` e nomes privados por marcadores. Elas servem para leitura, não para executar ou validar
um destino. Use marcadores distintos para alvos distintos e o mesmo marcador para o mesmo alvo
no inventário e no plano. Não anexe os instantâneos brutos nem tokens.

```text
Revise por leitura meu inventário e meu plano de encerramento sanitizados.
Use este guia, planejar_encerramento.py e lab_encerramento.py como contexto.
Confira esquema, exclusividade, base anterior ao grupo, consumidores, links da busca,
relações de identidade, escopos de papéis, expurgos e provas de ausência.
Confira a diferença entre IDs de objeto e de cliente, as funções dos GUIDs e
a Preparação na mesma sessão sem troca de conta. Separe presença prévia de ausência final.
Explique cada risco para quem não programa e separe reprovado de pendente.
Liste decisões humanas e limitações; não invente valores para os marcadores.
Não execute comandos, acesse Azure ou Entra ID, remova bloqueios ou revogue acesso.
Não escreva um executor de remoções nem reexecute avaliações finais.
```

Confira a análise contra o contrato público e revise qualquer alteração de texto no diff.
O modelo escolhido no Copilot ajuda a leitura; não decide propriedade, permissão ou expurgo.

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
| Encerramento completo | Seis instantâneos e presença aplicável, conferência local aprovada e provas privadas das leituras reais |
| Limite da preservação | IDs, tipos e atribuições comparados; configurações e consumidores conferidos separadamente |
| IDs e presença prévios | IDs de objeto confirmados nas leituras e alvos ativos presentes antes de qualquer remoção |
| Guarda de sessão | Preparação e blocos completos na mesma janela PowerShell 7, sem troca de conta; aviso ou `indeterminado` não prova execução |

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
| Grupo já existia quando a base foi capturada | Plano e conferência recusam essa base; use uma captura anterior íntegra se existir. Sem ela, mantenha a prévia e a preservação pendente |
| Instantâneo paginado ou leitura recusada | Complete a exportação autorizada; não edite o JSON nem trate falta de permissão como ausência |
| Guarda encontra recurso fora do inventário | Pare, confirme proprietário e exclusividade; preserve versões e revise o plano, sem acrescentar alvos alheios |
| Guarda de atribuição não confere | Exija exatamente um item com aquele ID e principal de objeto, papel e escopo iguais, após leitura bem-sucedida; conserve atribuições herdadas e externas |
| Bloco só avisa e não executa | Abra `pwsh`, conclua a Preparação na mesma janela e cole o bloco inteiro; Windows PowerShell 5.1, aviso ou código residual não comprova remoção |
| GUID usado em duas funções ou credencial repetida | Releia os campos citados no erro e as provas de criação; principal, objeto, cliente, credencial, tenant, assinatura e definição de papel não compartilham GUIDs |
| Presença prévia fica `ausente` | Confira ID de objeto e relações do inventário antes de apagar; um cliente consultado como objeto pode devolver 404 falso |
| Graph retorna `indeterminado` ou ainda `presente` após remoção | Confira Preparação, ID de objeto, tenant, autorização e propagação; repita a leitura de presença, não operações já comprovadas |
| Captura ou relatório recusa arquivo existente | Preserve a evidência e use outra pasta ou nome novo; a ferramenta não sobrescreve |
| Cofre protegido contra expurgo | Registre a pendência e respeite a retenção; não desative proteção como contorno |
| Conferência aponta divergência de terceiro | Investigue com o proprietário, mantendo a base original e o resultado reprovado |

## Custos, pausa e limpeza

Defina prazo para a coexistência e para a retenção das evidências.
Uma limpeza parcial mantém dependências cobradas; registre a decisão em vez de tratá-la
como encerramento completo. O L400 parte dos arquivos e das evidências L300, sem exigir
um ambiente do instrutor ativo.
O roteiro completo acima separa planos locais, leituras autorizadas e exclusões permanentes.
Arquivos privados precisam de prazo e responsável pela retenção. Custo sem dados permanece
indisponível, inclusive depois de uma conferência aprovada; aprovação não comprova custo zero.

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

O roteiro público de encerramento foi acrescentado em 11 de outubro de 2026 por revisão de
leitura do código e dos registros. A ferramenta foi testada localmente com dados sintéticos e
dublês, inclusive execução no PowerShell 7 e recusa no Windows PowerShell 5.1 com uma CLI falsa;
isso não valida respostas de serviços reais. As guardas de função dos GUIDs, identidade e sessão
foram incorporadas ao roteiro por leitura e geração de planos e capturas sintéticos.
O encerramento histórico acima não foi repetido nem atribuído à nova ferramenta.
Ficam pendentes a execução autorizada da nova sequência, a projeção `id:id` de `--query`,
os formatos reais das respostas, a conclusão dos links e a semântica da listagem de papéis
por escopo. Os administradores decidem destino, permissões, orçamento e expurgos antes
dessa qualificação.

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
| Azure CLI | Interface de linha de comando do Azure; o planejador só imprime seus comandos |
| Inventário e instantâneo | Registro de alvos próprios e exportação de estado em um momento |
| Linha de base | Três listas capturadas antes do grupo exclusivo para comparar o que já existia |
| GUID e ID | Identificador globalmente único e identificador de um objeto ou recurso |
| JSON | Formato de dados estruturados usado no inventário e nas evidências |
| Principal de serviço | Representação de um aplicativo no Microsoft Entra ID |
| RBAC e escopo | Acesso baseado em papéis e o alvo ao qual uma atribuição se aplica |
| Microsoft Graph e HTTP 404 | Interface dos objetos Entra e resposta de ausência condicionada a tenant e ID de objeto corretos |
| Expurgo | Remoção permanente de um objeto recuperável |
| Workspace do Log Analytics | Área de armazenamento e consulta de logs; o plano solicita exclusão permanente |
| Presença indeterminada | Leitura ou bloco recusado sem prova suficiente de presença ou ausência |
| Hash | Resumo calculado de um arquivo, usado para reconhecer alterações |
| Shared private link | Conexão privada de saída da busca, retirada antes do serviço e dos destinos |
| Job do Container Apps | Execução de tarefa no ambiente, com consumidores e dependências próprios |
| ID de objeto e ID de cliente | `id` do aplicativo/principal ou `principalId` da identidade localiza o objeto Entra; `appId`/`clientId` identifica o cliente para autenticação |
| Função do GUID no inventário | Categoria como assinatura, tenant, principal ou cliente; o mesmo GUID não pode ocupar categorias distintas |
| Preparação e sessão | Conferência inicial que marca a janela PowerShell 7; a marca não revalida a conta em cada passo |
| Comando composto | Bloco agrupado sob condições, a colar inteiro para preservar suas guardas |
| Conferência cruzada prévia | Leitura que confirma IDs e presença dos objetos ativos antes de apagar; não é o instantâneo final |

## Referências

1. [Revisões em Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/revisions-manage).
2. [Redes e recursos gerenciados do ambiente](https://learn.microsoft.com/en-us/azure/container-apps/custom-virtual-networks).
3. [Detecção de exclusão e restauração no indexador](https://learn.microsoft.com/en-us/azure/search/search-how-to-index-azure-blob-changed-deleted).
4. [Concorrência no Blob Storage](https://learn.microsoft.com/en-us/azure/storage/blobs/concurrency-manage).
5. [Papéis de aplicação e atribuições Entra ID](https://learn.microsoft.com/en-us/entra/identity-platform/howto-add-app-roles-in-apps).
6. [Cobrança em Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/billing).
7. [Diagnóstico e exclusão de conexões compartilhadas da busca](https://learn.microsoft.com/en-us/azure/search/troubleshoot-shared-private-link-resources#deleting-a-shared-private-link-resource).
8. [Ajuda e interface do planejador público](../../scripts/planejar_encerramento.py).
9. [Esquema, guardas, fases e critérios do encerramento](../../scripts/lab_encerramento.py).
10. [Testes locais do encerramento, sem Azure](../../tests/test_encerramento.py).
11. [Encerramento histórico e falhas L300](../../docs/validacao/l300-azure-validacao.md).
12. [IDs da identidade gerenciada e seus usos no Desafio 04](04-dependencias-privadas.md#1-preparar-identidades-papéis-e-conexões).

[11]: ../../docs/validacao/l300-azure-validacao.md

## Autoria

Texto por GPT-6.1 Sol; código e testes por Claude Sonnet 5.5, com Astra indisponível.
As escolhas de autoria, Copilot e deployments Azure permanecem independentes.

Revisão documental: gpt-6-astra (Astra), em 11 de outubro de 2026, por leitura integral e
conferência local dos artefatos; sem nova execução Azure.

Roteiro de encerramento: GPT-6.1 Sol, com Astra indisponível, em 11 de outubro de 2026;
ferramenta pública por Claude Sonnet 5.5; revisado por leitura; sem execução Azure.

Sincronização final do roteiro: GPT-6.1 Sol, com Astra indisponível, em 11 de outubro de 2026;
adequação às guardas de IDs e sessão da ferramenta de Claude Sonnet 5.5, por leitura e
conferência local; sem execução Azure.

Nota sobre atribuições herdadas: redigida por GPT-6.1 Sol em 11 de outubro de 2026
e revisada pelo coordenador.
