# L400 · Desafio 03: operar deployments com contingência

[Início](../../README.md) · [Desafio 02](02-coordenar-especialistas.md) · [Desafio 04](04-evoluir-indice.md)

| Campo | Definição |
| --- | --- |
| Situação | Contingência e recusas históricas exercitadas; receita pública revisada, sem nova execução Azure |
| Público | Operações, arquitetura e desenvolvimento |
| Resultado | Revisar e implantar as fases de contingência e aplicação, conferir seus estados e exercitar falhas dentro dos limites |
| Custo | Plano e testes locais não chamam modelos; uso dos deployments, aplicação, imagem e dependências têm cobranças próprias |

## Conteúdo

- [Cenário](#cenário)
- [Objetivos](#objetivos)
- [Artefatos e disponibilidade](#artefatos-e-disponibilidade)
- [Tecnologias e conceitos](#tecnologias-e-conceitos)
- [Pré-requisitos](#pré-requisitos)
- [Etapa 1: distinguir modelo e deployment](#etapa-1-distinguir-modelo-e-deployment)
- [Receita pública: implantar por fases](#receita-pública-implantar-por-fases)
- [Etapa 2: classificar falhas](#etapa-2-classificar-falhas)
- [Etapa 3: conferir orçamento e retorno](#etapa-3-conferir-orçamento-e-retorno)
- [Como pedir uma mudança ao Copilot no VS Code](#como-pedir-uma-mudança-ao-copilot-no-vs-code)
- [Conferência do resultado](#conferência-do-resultado)
- [Solução de problemas](#solução-de-problemas)
- [Custos, pausa e limpeza](#custos-pausa-e-limpeza)
- [Situação da validação](#situação-da-validação)
- [Glossário e referências](#glossário-e-referências)
- [Autoria](#autoria)

## Cenário

A equipe do piloto fictício precisa que uma indisponibilidade temporária seja identificada,
sem transformar um erro de permissão em uma tentativa com identidade mais poderosa.
Teresa Moura exige que a contingência conserve modelo, fontes, política e autorização.

## Objetivos

1. Conferir versão, capacidade e endereço dos deployments autorizados.
2. Separar falhas transitórias de configuração, acesso e política.
3. Limitar tentativas e contabilizar chamadas que falham.
4. Testar retorno sem alegar disponibilidade de produção.
5. Separar plano local, simulação do Azure e conferência dos efeitos das duas fases.

## Artefatos e disponibilidade

| Artefato | Uso e disponibilidade |
| --- | --- |
| [Bicep L400](../../infra/l400.bicep) e [parâmetros](../../infra/levels/l400.bicepparam) | Disponíveis: fases `contingencia` e `aplicacao`, com configuração recebida da sessão |
| [Guardas L400](../../infra/modules/l400-guardas.bicep) | Disponíveis: recusam nomes, modelos, versões ou dimensões incompatíveis com as condições do template |
| [Deployment de geração L100](../../infra/modules/geracao.bicep) | Reutilizado: versão fixa, tipo e capacidade explícitos |
| [Topologia L300](../../infra/l300.bicep) | Dependência existente no destino autorizado, não implantada por este roteiro |
| [Operação L400](../../scripts/operar_l400.py) | Disponível: plano e sanitização locais; não implanta nem consulta serviços |
| [Testes L400](../../tests/test_operacao_l400.py) e [sanitização L300](../../tests/test_operacao_l300.py) | Disponíveis: contratos e recusas com dublês, sem Azure |
| [Construção da imagem L200](../L200/05-hospedar-chat.md#etapa-1-publicar-a-imagem) | Procedimento disponível; use somente a construção da imagem do código atual |
| [Roteiro L400](../../docs/roteiro-l400.md) e [tratamento do chat](../../scripts/lab_chat.py) | Disponíveis: primário, contingência, limites e códigos públicos |
| Receita desta página | Revisada com ajuda offline da interface de linha de comando do Azure (Azure CLI) e testes locais; não executada no Azure nesta revisão |

Na rodada histórica, primário e **standby**, deployment de contingência, usaram o mesmo modelo
e versão. Standby não é um serviço de outra região. Os recursos daquela rodada foram removidos;
seus helpers privados eram diferentes desta receita e não são dependências do aluno.

## Tecnologias e conceitos

Um **deployment** é uma instância nomeada de modelo. O nome `geracao` não é o nome
`gpt-5.4-mini`. O exercício usa primário e contingência do mesmo modelo e versão para reduzir
variáveis; isso não garante resposta idêntica.

**Azure CLI**, interface de linha de comando do Azure, envia a implantação ao **Azure Resource
Manager (ARM)**, serviço de administração dos recursos. O **what-if** é a simulação que o ARM
calcula comparando o Bicep com o destino atual [4]. A **sanitização** reduz essa saída a contagens,
tipos e caminhos de propriedades, sem os valores privados.

**Para guardar na memória:** o plano local é a lista de peças de um palco; o what-if é o ensaio
nesse palco, que revela o que já está montado e o que muda. Conferir a lista não ensaia a montagem.
O ensaio também não é a apresentação: só as leituras posteriores comprovam o estado implantado.

**Cota** limita a capacidade disponível. Dois deployments podem compartilhar a mesma cota
regional. Eles não criam automaticamente capacidade adicional nem disponibilidade independente [1].

**Retry**, nova tentativa, precisa consumir o orçamento da requisição. Um **circuit breaker**,
interrupção temporária de um destino após falhas, pode evitar repetição imediata. Ele não concede
papéis nem transforma uma resposta sem fontes em sucesso.

## Pré-requisitos

1. Abra a pasta completa no Visual Studio Code (VS Code), selecione o interpretador `.venv`
   e use PowerShell 7 com `Read-Host -MaskInput`, entrada oculta de texto. A receita foi conferida
   pela ajuda offline da Azure CLI **2.89.0** e pelo Bicep **0.48.1** instalado, sem acessar Azure.
2. Para uma execução futura, confirme assinatura ativa, grupo exclusivo do exercício, região
   aprovada e permissões de leitura, simulação, implantação e remoção proporcionais aos alvos.
   Login bem-sucedido não comprova autorização para dados ou implantação.
3. Tenha a base L100–L300 existente e conferida nesse grupo: modelos, busca, registro de imagens,
   identidade e papéis anteriores, ambiente privado, índice de referência e aplicação L300.
   Este Bicep não recria a base nem atribui papéis.
4. Confira catálogo, versão, cota regional, capacidade escolhida, orçamento e prazo de coexistência
   com os responsáveis. Conserve `gpt-5.4-mini`, versão `2026-03-17`, e
   `text-embedding-3-small`, versão `1`. Ausência de versão ou cota interrompe a implantação.
5. Autorize separadamente a construção da imagem, cada fase, o uso de modelos e sua limpeza.
   Para `aplicacao`, tenha registro de login, credencial vigente e endereço de retorno aprovados
   pelo administrador do Microsoft Entra ID, diretório de identidades. O guia não cria esses objetos.
6. Reserve uma pasta privada existente, fora do repositório e sem publicação automática, para
   inventário e saídas brutas. No Windows, confira quem pode lê-la; um nome “privado” não restringe
   permissões do arquivo.

Os testes locais dispensam Azure. A autorização histórica não autoriza nova execução, outro
destino, publicação ou federação. O L400 conserva o fechamento dos serviços de dados.

## Etapa 1: distinguir modelo e deployment

Registre em local privado nome, modelo, versão, capacidade, região e identidade.
Conserve a referência e use um nome diferente para a contingência.

| Instância | Modelo e finalidade |
| --- | --- |
| Primário de geração | Respostas estruturadas na configuração de referência |
| Contingência de geração | Mesmo contrato e autorização, quando uma falha transitória permite troca |
| Embeddings | Vetores compatíveis com o índice; não participa da troca de geração |

Não copie IDs ou endpoints reais para prompts, arquivos públicos ou logs.

O Bicep usa duas fases: `contingencia` acrescenta a instância no recurso existente;
`aplicacao` cria o chat L400 no ambiente privado, separado da referência. Os módulos ARM de
guardas e da fase também podem aparecer no plano. Dados, rede e identidade não são redeclarados.

Confira o plano local, sem alterar serviços:

```powershell
.\.venv\Scripts\python.exe scripts\operar_l400.py --etapa planejar --passo contingencia --validar-bicep
```

**Resultado esperado:** plano declarativo, nenhuma chamada de rede e compilação com lint sem
avisos. Esse comando compila o template, não o arquivo de parâmetros nem o destino Azure.

## Receita pública: implantar por fases

Esta é uma **receita revisada**, com comandos verificados por ajuda offline e pelos testes locais
das ferramentas existentes; **não executada nesta rodada de revisão**. As execuções históricas
estão no [registro L400](../../docs/validacao/l400-validacao.md) e usaram helpers privados diferentes.
Os blocos que consultam o Azure são instruções para uma futura sessão autorizada do aluno.
Execute um bloco por vez e confira `$LASTEXITCODE` imediatamente: falha impede o próximo bloco.

### 1. Preparar o destino e a sessão

Receba os valores do inventário aprovado, sem colá-los em arquivos ou prompts do Copilot:

```powershell
$assinatura = Read-Host "ID da assinatura autorizada"
$grupo = Read-Host "Grupo exclusivo com a base L300 conferida"
$regiaoAutorizada = Read-Host "Região autorizada do grupo e do ambiente"
$modelos = Read-Host "Nome do recurso de modelos existente"
$busca = Read-Host "Nome do serviço de busca existente"
$registro = Read-Host "Nome do registro de imagens existente"
$nomeIdentidade = Read-Host "Nome da identidade gerenciada da aplicação L300"
$ambiente = Read-Host "Nome do ambiente privado Container Apps L300"
$aplicacaoL300 = Read-Host "Nome da aplicação L300 que deve ser preservada"
$pastaPrivada = Read-Host "Pasta privada existente para as evidências"
if (-not (Test-Path -LiteralPath $pastaPrivada -PathType Container)) {
    throw "Prepare a pasta privada e suas permissões antes de continuar."
}
```

As próximas chamadas **só leem**. A consulta de conta informa o estado registrado da assinatura;
confirme também sua vigência e as permissões efetivas com o administrador. Elas não são um teste
de leitura dos dados nem de implantação:

```powershell
$estadoAssinatura = az account show --subscription $assinatura --query state --output tsv
if ($LASTEXITCODE -ne 0 -or $estadoAssinatura -ne "Enabled") {
    throw "Assinatura ativa não conferida."
}
$regiaoGrupo = az group show --subscription $assinatura --name $grupo --query location --output tsv
if ($LASTEXITCODE -ne 0 -or $regiaoGrupo -ne $regiaoAutorizada) {
    throw "Grupo ou região diverge do destino aprovado."
}
```

Defina as variáveis pelos nomes efetivamente lidos pelo arquivo de parâmetros:

```powershell
$env:VARELEIRA_NOME_MODELOS = $modelos
$env:VARELEIRA_NOME_BUSCA = $busca
$env:VARELEIRA_NOME_REGISTRO = $registro
$env:VARELEIRA_NOME_IDENTIDADE_APLICACAO = $nomeIdentidade
$env:VARELEIRA_L400_NOME_AMBIENTE = $ambiente
$env:VARELEIRA_L400_MODELO_CONTINGENCIA = "gpt-5.4-mini"
$env:VARELEIRA_L400_VERSAO_MODELO_CONTINGENCIA = "2026-03-17"
$env:VARELEIRA_L400_SKU_CONTINGENCIA = Read-Host "Tipo autorizado e disponível para o mesmo modelo"
$env:VARELEIRA_L400_CAPACIDADE_CONTINGENCIA = Read-Host "Capacidade aprovada após conferir a cota"
$env:VARELEIRA_L400_FASE = "contingencia"
$env:VARELEIRA_L400_INGRESSO_EXTERNO = "false"
$env:VARELEIRA_L400_PERFIL_INDICE = "referencia"
$env:VARELEIRA_ACAO_SEM_LOGIN = "Return401"
```

| Quando | Variáveis e condição |
| --- | --- |
| Ambas as fases | Os cinco destinos `VARELEIRA_NOME_*`/`VARELEIRA_L400_NOME_AMBIENTE` e os quatro valores `VARELEIRA_L400_*_CONTINGENCIA` acima |
| Controle | `VARELEIRA_L400_FASE`, `VARELEIRA_L400_INGRESSO_EXTERNO`, `VARELEIRA_L400_PERFIL_INDICE` e `VARELEIRA_ACAO_SEM_LOGIN` |
| `aplicacao` | `VARELEIRA_L400_TAG_IMAGEM`, `VARELEIRA_ID_APLICACAO_LOGIN`, `VARELEIRA_ID_TENANT_LOGIN` e `VARELEIRA_SEGREDO_LOGIN`, definidos no passo 5 |

O tipo, chamado **SKU**, configuração comercial do deployment, precisa ser um dos permitidos
no Bicep: `GlobalStandard`, `Standard` ou `DataZoneStandard`. Isso não comprova sua disponibilidade.
A capacidade é um inteiro de 1 a 1.000 no template; confira a unidade da cota para esse modelo e
tipo, sem transformar uma contagem do catálogo em requisições por minuto.

Esta receita usa os defaults existentes `geracao`, `embeddings` e `geracao-contingencia`,
repositório de imagem `vareleira-chat` e região do grupo. O nome da nova aplicação é calculado
pelo Bicep a partir do grupo e conferido no what-if. Essas escolhas não têm variáveis adicionais
no `.bicepparam`. Se sua base ou aplicação L400 já usa outra configuração, interrompa e revise
os parâmetros com o responsável; não invente uma variável nem crie outra aplicação por acidente.

Antes da primeira alteração, guarde em seu inventário privado as leituras dos deployments e da
aplicação L300. O comando de deployments do passo 4 serve também para essa linha de base.
Se `geracao-contingencia` ou a aplicação calculada já existe, identifique seu proprietário e
configuração antes de continuar. Nome coincidente não comprova que o recurso é próprio:
sem essa confirmação, não atualize nem inclua o alvo na limpeza.
**Resultado esperado:** destino e configurações anteriores identificados; cota e custo aprovados,
não inferidos pelo plano local.

### 2. Simular e revisar o what-if

Este passo **consulta o Azure**, mas não aplica o template. Use-o primeiro para `contingencia`
e repita-o para `aplicacao` depois do passo 5 [4].

1. Escolha um nome novo de implantação ARM, curto e com letras, números e hífens.
2. Gere arquivos novos na pasta privada. Não filtre tipos de mudança da simulação.
3. Sanitize o JSON (*JavaScript Object Notation*, formato de dados estruturados) bruto.
4. Revise alvos, tipos, valores e número de alterações antes de autorizar a aplicação.

```powershell
$implantacao = Read-Host "Nome novo da implantação ARM desta fase"
$arquivoWhatIf = Join-Path $pastaPrivada "$implantacao-whatif.json"
$novoRelatorio = Join-Path $pastaPrivada "$implantacao-resumo.json"
$erroWhatIf = Join-Path $pastaPrivada "$implantacao-whatif-erros.txt"
$erroImplantacao = Join-Path $pastaPrivada "$implantacao-implantacao-erros.txt"
$erroEspera = Join-Path $pastaPrivada "$implantacao-espera-erros.txt"
foreach ($arquivo in @($arquivoWhatIf, $novoRelatorio, $erroWhatIf, $erroImplantacao, $erroEspera)) {
    if (Test-Path -LiteralPath $arquivo) { throw "Escolha caminhos novos; preserve as evidências anteriores." }
}
Remove-Item Env:\VARELEIRA_QUALIFICAR_NAO_SUPORTADO, Env:\VARELEIRA_QUALIFICAR_PROPRIEDADES_REMOVIDAS, Env:\VARELEIRA_PLANO_SHA256 -ErrorAction SilentlyContinue
try {
    if ($env:VARELEIRA_L400_FASE -eq "aplicacao") {
        $env:VARELEIRA_SEGREDO_LOGIN = Read-Host "Segredo vigente do login autorizado" -MaskInput
    }
    az deployment group what-if --subscription $assinatura --resource-group $grupo `
        --name $implantacao --parameters infra\levels\l400.bicepparam --mode Incremental `
        --result-format FullResourcePayloads --no-pretty-print --no-prompt true --output json `
        2> $erroWhatIf | Out-File -LiteralPath $arquivoWhatIf -Encoding utf8 -NoClobber -ErrorAction Stop
    if ($LASTEXITCODE -ne 0) { throw "What-if falhou; reveja o erro somente na pasta privada." }
    .\.venv\Scripts\python.exe scripts\operar_l400.py --etapa sanitizar-whatif `
        --arquivo $arquivoWhatIf --relatorio $novoRelatorio --rotulo $env:VARELEIRA_L400_FASE
    if ($LASTEXITCODE -ne 0) { throw "Sanitização bloqueou o plano; não aplique." }
}
finally {
    Remove-Item Env:\VARELEIRA_SEGREDO_LOGIN -ErrorAction SilentlyContinue
}
```

As três variáveis removidas são qualificações e hash de **um plano anterior**, que não devem
aprovar ou bloquear uma fase nova por herança da sessão L300. Isso não remove recursos nem
evidências. Para comparar uma nova simulação com uma já revisada, o helper aceita
`--plano-esperado` com o hash aprovado. O nome impresso é `plano_sha256`; no JSON ele é
`conteudo_sha256`. Esse hash não compara destinos nem todos os valores privados.

**Atenção:** `FullResourcePayloads` conserva os dados necessários à revisão, inclusive valores
que o ARM pode ecoar. Trate o bruto e os erros como arquivos sensíveis, mesmo com parâmetro seguro.
Não os anexe ao Copilot, publique em logs ou imprima `az bicep build-params --stdout` com valores
reais. O segredo do login só entra pela sessão e pelo parâmetro `@secure()`; nunca pelo argumento
do comando ou por arquivo de parâmetros preenchido.

O helper reutiliza a sanitização L300. Sua decisão tem estes limites:

| Entrada ou resultado | Interpretação |
| --- | --- |
| Código 0, `decisao.resultado=concluido` | Forma e guardas da sanitização atendidas; ainda falta revisão do destino e dos efeitos |
| Código 1 | Uso inválido, arquivo ilegível ou relatório existente; escolha entrada/caminho correto, sem sobrescrever |
| Código 3, `bloqueado` | Estado ARM diferente de `Succeeded`, erro, `Delete` de recurso, mudança potencial, diagnóstico `Error`, qualificação ausente/divergente ou hash diferente |
| Código 4 | Defeito inesperado do script: interrompa e encaminhe diagnóstico sanitizado; não trate como plano aprovado |
| Forma desconhecida | JSON, `resourceId`, ação ou delta não interpretável: recusa, sem preencher campos por suposição |
| `Unsupported` ou propriedade `Delete` | O helper oferece qualificação por **tipo e quantidade exata**; não comprova os efeitos nem autoriza a implantação |
| `Modify`, `Deploy`, avisos ou plano vazio | Podem passar pela sanitização; isso não os torna aprovados por esta receita |

Esta receita admite somente `Create` (criar), `NoChange` (sem mudança), `Ignore` (sem efeito
aplicável) e o número **explicitamente revisado** de `Modify` (alterar).
Recuse `Delete`, `Deploy`, `Unsupported`, tipo inesperado ou efeito não resolvido.
Uma reprovação é diagnóstico para investigar com o responsável, não convite para editar o JSON,
ocultar mudanças ou adicionar qualificações até obter código zero.

Confira localmente o escopo de **cada** `resourceId`, sem exibir seus valores:

```powershell
$planoArm = Get-Content -LiteralPath $arquivoWhatIf -Raw | ConvertFrom-Json
$resumoPlano = Get-Content -LiteralPath $novoRelatorio -Raw | ConvertFrom-Json
$prefixoGrupo = "/subscriptions/$assinatura/resourceGroups/$grupo/"
if ($planoArm.status -ne "Succeeded" -or @($planoArm.changes).Count -eq 0) {
    throw "Plano sem conclusão ou sem alvos: revise antes de continuar."
}
foreach ($mudanca in $planoArm.changes) {
    if ($mudanca.changeType -notin @("Create", "NoChange", "Ignore", "Modify") -or
        -not ([string]$mudanca.resourceId).StartsWith($prefixoGrupo, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Ação ou escopo fora da receita; não aplique."
    }
}
$modificacoesAprovadas = [int](Read-Host "Número de Modify autorizado após revisar cada tipo, alvo e propriedade")
if (@($planoArm.changes | Where-Object changeType -eq "Modify").Count -ne $modificacoesAprovadas) {
    throw "Quantidade de alterações diverge da revisão."
}
```

A quantidade digitada vem do registro da revisão humana, não de uma aprovação automática da
contagem encontrada. Confira também a distribuição por tipo em `por_tipo` e cada alvo no bruto:

| Fase | Alvos permitidos para criação/alteração |
| --- | --- |
| `contingencia` | Somente `Microsoft.CognitiveServices/accounts/deployments` da contingência própria e módulos `Microsoft.Resources/deployments` desta fase |
| `aplicacao` | Somente a aplicação L400 (`Microsoft.App/containerApps`), sua autenticação `Microsoft.App/containerApps/authConfigs` e módulos ARM desta fase |

Dependências inventariadas podem aparecer com `NoChange`/`Ignore`: recurso de modelos,
deployments anteriores, registro, identidade e ambiente. Um nome desconhecido, papel novo,
alteração na aplicação L300, rede ou acesso público dos dados impede a aplicação.
O helper **não verifica escopo, propriedade dos alvos, tipos permitidos nem quantidade aprovada
de `Modify`**; o bloco acima cobre escopo, ações e contagem total, e a revisão cobre nomes,
tipos, propriedades e contagens por tipo.

**Resultado esperado:** bruto privado, resumo novo e revisão explícita das mudanças da fase.
Se código, parâmetros, destino ou estado relevante mudar, gere e revise outro what-if.

### 3. Aplicar a fase revisada

**[altera o Azure]**. Para `contingencia`, cria/reserva capacidade do deployment adicional.
Para `aplicacao`, cria ou reaplica a configuração do chat L400. Só execute após autorização
dos efeitos e do custo, com os mesmos arquivos e valores revisados; nunca use modo `Complete`.
O modo **incremental** conserva recursos não declarados pela fase, mas ainda pode reconfigurar
um recurso declarado [5].

O bloco serve às duas fases. Na fase `aplicacao`, informe novamente **a mesma credencial vigente**
usada no plano; a remoção da variável não a revoga no Entra ID:

```powershell
$resumoPlano = Get-Content -LiteralPath $novoRelatorio -Raw | ConvertFrom-Json
$hashBruto = (Get-FileHash -LiteralPath $arquivoWhatIf -Algorithm SHA256).Hash.ToLowerInvariant()
if ($resumoPlano.decisao.codigo -ne 0 -or $hashBruto -ne $resumoPlano.bruto_sha256) {
    throw "Plano bloqueado ou arquivo diferente do sanitizado."
}
try {
    if ($env:VARELEIRA_L400_FASE -eq "aplicacao") {
        $env:VARELEIRA_SEGREDO_LOGIN = Read-Host "Mesma credencial vigente do plano revisado" -MaskInput
    }
    az deployment group create --subscription $assinatura --resource-group $grupo `
        --name $implantacao --parameters infra\levels\l400.bicepparam --mode Incremental `
        --no-prompt true --no-wait --output none 2> $erroImplantacao
    if ($LASTEXITCODE -ne 0) { throw "Pedido de implantação falhou; não prossiga." }
}
finally {
    Remove-Item Env:\VARELEIRA_SEGREDO_LOGIN -ErrorAction SilentlyContinue
}
az deployment group wait --subscription $assinatura --resource-group $grupo `
    --name $implantacao --created --interval 15 --timeout 1200 --output none 2> $erroEspera
if ($LASTEXITCODE -ne 0) { throw "Implantação não confirmada no prazo; leia o estado antes de decidir a recuperação." }
$estadoArm = az deployment group show --subscription $assinatura --resource-group $grupo `
    --name $implantacao --query properties.provisioningState --output tsv
if ($LASTEXITCODE -ne 0 -or $estadoArm -ne "Succeeded") {
    throw "Estado final Succeeded não comprovado."
}
```

`--no-wait` confirma somente que o pedido foi aceito. A espera é limitada a 1.200 segundos,
janela operacional escolhida para esta receita, não garantia do serviço [6].
Tempo esgotado ou terminal fechado não cancela o trabalho remoto. Leia o estado, conserve a falha
e decida retomada ou limpeza autorizada; não envie outra criação por suposição.

### 4. Conferir a contingência por leitura

No terminal privado, liste os deployments do recurso autorizado [7]:

```powershell
az cognitiveservices account deployment list --subscription $assinatura --resource-group $grupo `
    --name $modelos `
    --query "[].{nome:name,modelo:properties.model.name,versao:properties.model.version,politica:properties.versionUpgradeOption,tipo:sku.name,capacidade:sku.capacity,estado:properties.provisioningState}" `
    --output table
if ($LASTEXITCODE -ne 0) { throw "Leitura dos deployments falhou." }
```

**Resultado esperado:** principal e contingência distintos, ambos `gpt-5.4-mini`,
versão `2026-03-17`, política `NoAutoUpgrade` e estado `Succeeded`; capacidade da contingência
igual à aprovada. Embeddings continuam `text-embedding-3-small`, versão `1`.
Compare principal e embeddings com o inventário anterior, incluindo capacidade.
A guarda Bicep compara modelo/versão e limites declarados; não consulta cota, fatura ou índice.
Uma listagem bem-sucedida não mede disponibilidade regional ou comportamento da resposta.

### 5. Preparar e aplicar a fase aplicacao

1. Construa a imagem do **código L400 atual**, seguindo somente a
   [etapa de imagem L200](../L200/05-hospedar-chat.md#etapa-1-publicar-a-imagem).
   **[altera o Azure]**: envio de contexto, construção e publicação no registro têm custo.
   Revise Dockerfile e `.dockerignore`, use tag **nova e imutável**, confira execução e digest,
   resumo criptográfico da imagem, e preserve a anterior. Não reaplique a infraestrutura L200.
2. Defina a fase, a tag e os identificadores do login na sessão:

```powershell
$env:VARELEIRA_L400_FASE = "aplicacao"
$env:VARELEIRA_L400_PERFIL_INDICE = "referencia"
$env:VARELEIRA_L400_INGRESSO_EXTERNO = "false"
$env:VARELEIRA_L400_TAG_IMAGEM = Read-Host "Tag nova e imutável da imagem L400 publicada"
$env:VARELEIRA_ID_APLICACAO_LOGIN = Read-Host "ID do aplicativo de login autorizado"
$env:VARELEIRA_ID_TENANT_LOGIN = Read-Host "ID do tenant autorizado para o login"
$env:VARELEIRA_ACAO_SEM_LOGIN = "Return401"
.\.venv\Scripts\python.exe scripts\operar_l400.py --etapa planejar --passo aplicacao
if ($LASTEXITCODE -ne 0) { throw "Plano local da aplicação falhou." }
```

3. Repita [simulação e revisão do what-if](#2-simular-e-revisar-o-what-if) com nome de implantação
   e arquivos **novos**. O segredo é recebido por
   entrada oculta dentro daquele bloco e removido no `finally`.
4. No plano já conferido, identifique a aplicação nova e seu endereço de retorno:

```powershell
$alvosApp = @($planoArm.changes | Where-Object {
    $_.resourceId -match "/providers/Microsoft.App/containerApps/[^/]+$"
})
if ($alvosApp.Count -ne 1) { throw "Plano não identifica uma única aplicação L400." }
$aplicacaoL400 = ([string]$alvosApp[0].resourceId -split "/")[-1]
if ($aplicacaoL400 -eq $aplicacaoL300) { throw "Alvo é a referência L300; não aplique." }
$dominioAmbiente = az containerapp env show --subscription $assinatura --resource-group $grupo `
    --name $ambiente --query properties.defaultDomain --output tsv
if ($LASTEXITCODE -ne 0 -or -not $dominioAmbiente) { throw "Domínio do ambiente não conferido." }
$urlRetornoLogin = "https://$aplicacaoL400.$dominioAmbiente/.auth/login/aad/callback"
```

5. O administrador confere esse endereço no registro de login autorizado, sem copiar seus
   identificadores para o repositório. Alterá-lo no Entra ID exige autorização própria.
   Se o retorno não está preparado, preserve o ingresso fechado e interrompa a implantação.
6. Após revisar todos os efeitos, execute [aplicação da fase revisada](#3-aplicar-a-fase-revisada)
   **[altera o Azure]** para `aplicacao`.
   O segredo vai ao parâmetro seguro e a **Container Apps Secrets**, armazenamento de segredos
   da plataforma; não vira variável do contêiner. Esta fase não abre o ingresso.

### 6. Conferir a aplicação por leitura

Confirme que a saída da implantação aponta para o alvo revisado e diferente da referência:

```powershell
$nomeConfirmado = az deployment group show --subscription $assinatura --resource-group $grupo `
    --name $implantacao --query properties.outputs.nomeAplicacao.value --output tsv
if ($LASTEXITCODE -ne 0 -or $nomeConfirmado -ne $aplicacaoL400) {
    throw "Aplicação implantada diverge do alvo revisado."
}
$limiteRevisao = (Get-Date).AddMinutes(10)
do {
    $appL400 = az containerapp show --subscription $assinatura --resource-group $grupo `
        --name $aplicacaoL400 --output json | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0) { throw "Leitura da aplicação falhou." }
    $p = $appL400.properties
    $pronta = $p.provisioningState -eq "Succeeded" -and $p.latestRevisionName -and
        $p.latestRevisionName -eq $p.latestReadyRevisionName
    if ($p.provisioningState -in @("Failed", "Canceled")) { throw "Aplicação terminou sem sucesso." }
    if ($pronta) { break }
    Start-Sleep -Seconds 5
} while ((Get-Date) -lt $limiteRevisao)
if (-not $pronta) { throw "Revisão não ficou pronta na janela de conferência." }
if ($p.configuration.ingress.external -ne $false -or $p.configuration.ingress.allowInsecure -ne $false) {
    throw "Ingresso fechado e conexão protegida não confirmados."
}
az containerapp revision list --subscription $assinatura --resource-group $grupo `
    --name $aplicacaoL400 --all `
    --query "[].{revisao:name,ativa:properties.active,saude:properties.healthState,estado:properties.provisioningState}" `
    --output table
if ($LASTEXITCODE -ne 0) { throw "Leitura das revisões falhou." }
$auth = az containerapp auth show --subscription $assinatura --resource-group $grupo `
    --name $aplicacaoL400 --output json | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) { throw "Leitura da autenticação falhou." }
$aad = $auth.identityProviders.azureActiveDirectory
if (-not $auth.platform.enabled -or -not $auth.httpSettings.requireHttps -or
    $auth.globalValidation.unauthenticatedClientAction -ne $env:VARELEIRA_ACAO_SEM_LOGIN -or
    -not $aad.enabled -or $aad.registration.clientId -ne $env:VARELEIRA_ID_APLICACAO_LOGIN) {
    throw "Autenticação integrada obrigatória não conferida."
}
```

Essas leituras não usam `--show-secrets` e não devolvem a credencial de login.
Confira também tenant/emissor e audiência, destinatário aceito do token, como no
[guia de hospedagem L200](../L200/05-hospedar-chat.md#etapa-4-conferir-autenticação-e-abrir-o-ingresso),
**sem executar sua abertura de ingresso**.
O token é o comprovante digital de autenticação; **EasyAuth** é a autenticação integrada na borda.
Confira imagem/tag, identidade anterior, índice `vareleira-lar-l300`, dimensão `1536`,
autenticação, acesso documental e coordenação exigidos nas variáveis de `template.containers`.
Leia a aplicação L300 antes e depois e compare com o inventário, sem publicar o objeto bruto [8][9][10].

**Resultado esperado:** recurso L400 presente, revisão atual também pronta, ingresso interno
(`external=false`), conexão **HTTPS**, protocolo web protegido, e EasyAuth conferida.
Revisão pronta e verificações de saúde não comprovam busca, geração ou login de uma pessoa.
Uma consulta autenticada, pelo caminho autorizado **dentro do ambiente** quando o ingresso é
interno, é prova separada e consome tokens. Sem esse executor ou credencial, registre a prova
pendente; não abra o ingresso nem use cabeçalho artificial para completá-la.

## Etapa 2: classificar falhas

| Falha | Tratamento a conferir |
| --- | --- |
| 429, limite de capacidade | Tentativa ou contingência somente se orçamento e prazo permitirem |
| 5xx ou falha transitória de rede | Tratamento limitado e causa explícita |
| 401 ou 403 | Interromper; conferir identidade e permissão, sem contingência para contornar acesso |
| 404 | Interromper; conferir deployment e destino |
| Saída inválida ou referência inventada | Recusar; não repetir para buscar uma resposta que pareça aprovada |

Uma falha injetada no transporte de teste é diferente de uma interrupção real do serviço Azure.
Registre a origem de cada falha para não anunciar disponibilidade comprovada por um dublê.

## Etapa 3: conferir orçamento e retorno

1. Configure limites finitos antes da execução.
2. Confira se tentativas do SDK (*Software Development Kit*, biblioteca do serviço) também são contadas.
3. Simule falha antes de uma chamada e depois de um pedido já enviado.
4. Confira uso conhecido, uso incerto e tempo restante.
5. Retorne ao primário somente pelas condições definidas.

Tokens de raciocínio podem fazer parte dos tokens de saída. Não some a mesma parcela duas vezes.
Uso indisponível não representa consumo zero. Tarifas informadas produzem estimativa, não fatura.
Confira o tratamento implementado com dublês, sem provocar falhas em serviços reais:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_orquestracao.py
```

**Resultado esperado:** os testes de tentativas e contingência passam. Isso confere decisões
do código; não mede disponibilidade do deployment ou capacidade regional.

## Como pedir uma mudança ao Copilot no VS Code

Abra a pasta completa, use a prévia Markdown e o terminal PowerShell do projeto. Para revisar a
receita, anexe este guia, `infra\l400.bicep`, `infra\levels\l400.bicepparam`,
`infra\modules\l400-guardas.bicep`, `scripts\operar_l400.py` e seus testes. Anexe somente o
resumo sanitizado quando necessário, nunca bruto, IDs, segredo ou inventário privado:

```text
Revise a receita das fases contingencia e aplicacao usando os arquivos anexos.
Confira nomes de variáveis, captura do what-if, limites da sanitização,
implantação incremental e leituras de estado, revisão, ingresso e autenticação.
Separe controles automatizados de decisões humanas e provas ainda pendentes.
Explique por que plano local e comando aceito não comprovam implantação.
Não execute Azure, crie credenciais, amplie papéis, altere modelos ou solicite saídas privadas.
```

Para o comportamento de falhas, anexe também o roteiro e o tratamento do chat e peça o percurso
de 503 e 403 até a decisão de contingência. Revise o **diff**, comparação das alterações, em
**Source Control**: destinos continuam variáveis, segredo não aparece e limpeza não atinge L300.
Execute apenas plano e testes locais nesta revisão. Gerar ou revisar código não autoriza executá-lo.

## Conferência do resultado

| Conferência | Evidência necessária |
| --- | --- |
| Local | Plano sem rede, lint limpo e testes; não é simulação do destino |
| What-if | Bruto privado, resumo sanitizado, todos os alvos no grupo e alterações revisadas por tipo |
| ARM | Estado final `Succeeded`, não apenas aceite de `create --no-wait` |
| Deployments | Nomes, modelo/versão fixa e capacidade da contingência; principal e embeddings preservados |
| Aplicação | Revisão atual pronta, imagem correta, ingresso fechado, identidade e autenticação conferidas |
| Fluxo autenticado | Consulta com fontes e política, separada de saúde/prontidão; pendente sem execução autorizada |
| Limpeza | Listagens bem-sucedidas comprovam ausência dos alvos próprios e presença da referência |

Registre tentativas, destino lógico, duração, causa e uso de tokens, sem endereço ou credencial.
Uma resposta final continua passando pela política e pelas referências da requisição.

## Solução de problemas

| Sintoma | Ação |
| --- | --- |
| Ambos os deployments recebem 429 | Confira cota compartilhada e concorrência, sem prometer capacidade extra |
| 403 aciona contingência | Corrija a classificação; acesso negado deve interromper |
| Número de chamadas parece menor que o real | Confira retries internos e tentativas que falharam |
| Uso ausente aparece como zero | Preserve a incerteza e a reserva de orçamento |
| Sanitização reprovada ou `Unsupported` | Investigue a causa e revise o efeito; não edite o bruto nem qualifique por tentativa |
| Resumo aprovado, mas alvo ou tipo inesperado | Interrompa: o helper não comprova grupo, propriedade ou autorização da mudança |
| `create --no-wait` retorna zero, mas a espera falha | Leia `deployment group show`; prazo esgotado não cancela nem comprova conclusão |
| Aplicação presente, revisão ainda não pronta | Confira estado, imagem e identidade; preserve a falha e não declare fluxo funcional |
| Login falha ou credencial ausente ao reaplicar | Reconfira retorno, tenant e credencial vigente com o administrador; não peça o segredo ao serviço |
| Exclusão aceita, recurso ainda listado | Registre remoção pendente e repita apenas leituras no prazo aprovado |

## Custos, pausa e limpeza

Uma chamada que falha depois de ser enviada pode ter custo. Limite quantidade e duração.
Dois deployments reservam cota, não criam independência regional. A aplicação pode escalar a zero,
mas busca, registro, rede, logs e ambiente têm cobranças independentes [11].
Defina janela de uso e retorno antes da aplicação; fechar o terminal não pausa o Azure.

1. Antes de retirar a contingência, retire todos os seus consumidores próprios, inclusive a
   aplicação L400. A troca de índice do [Desafio 04](04-evoluir-indice.md#etapa-3-promover-e-retornar)
   não desliga a contingência de geração.
2. **[altera o Azure]**: depois de conservar as provas e autorizar a remoção, exclua somente
   a aplicação identificada no plano e inventário. O ambiente, identidade e aplicação L300 ficam:

```powershell
if (-not $aplicacaoL400 -or $aplicacaoL400 -eq $aplicacaoL300) {
    throw "Alvo próprio L400 não conferido."
}
az containerapp delete --subscription $assinatura --resource-group $grupo `
    --name $aplicacaoL400 --yes --no-wait --output none
if ($LASTEXITCODE -ne 0) { throw "Pedido de remoção da aplicação falhou." }
```

3. A próxima operação **só lê**. Repita a listagem com intervalo e prazo finitos:

```powershell
$limiteRemocao = (Get-Date).AddMinutes(10)
do {
    $nomesApps = @(az containerapp list --subscription $assinatura --resource-group $grupo `
        --query "[].name" --output json | ConvertFrom-Json)
    if ($LASTEXITCODE -ne 0) { throw "Listagem falhou; ausência não comprovada." }
    if ($nomesApps -notcontains $aplicacaoL400) { break }
    Start-Sleep -Seconds 5
} while ((Get-Date) -lt $limiteRemocao)
if ($nomesApps -contains $aplicacaoL400 -or $nomesApps -notcontains $aplicacaoL300) {
    throw "Remoção própria e preservação da referência não comprovadas."
}
```

4. **[altera o Azure]**: após confirmar que nenhum outro consumidor usa o standby, exclua
   somente o deployment próprio, nunca o recurso de modelos inteiro:

```powershell
az cognitiveservices account deployment delete --subscription $assinatura --resource-group $grupo `
    --name $modelos --deployment-name geracao-contingencia --output none
if ($LASTEXITCODE -ne 0) { throw "Remoção da contingência falhou." }
$nomesDeployments = @(az cognitiveservices account deployment list --subscription $assinatura `
    --resource-group $grupo --name $modelos --query "[].name" --output json | ConvertFrom-Json)
if ($LASTEXITCODE -ne 0 -or $nomesDeployments -contains "geracao-contingencia" -or
    $nomesDeployments -notcontains "geracao" -or $nomesDeployments -notcontains "embeddings") {
    throw "Ausência da contingência e preservação dos deployments anteriores não comprovadas."
}
```

5. Compare novamente modelos, versões e capacidades pelo comando do passo 4 da receita.
   Se uma remoção ainda estiver em curso, repita **somente a leitura** com prazo aprovado;
   403 ou falha de listagem nunca representam ausência. A reaplicação futura da fase
   `contingencia` recria capacidade e exige novo plano, cota e autorização.

Excluir a aplicação retira seu segredo da plataforma, mas não revoga a credencial no Entra ID.
Login ou credencial exclusivos do L400 exigem encerramento administrativo próprio, depois de
conferir consumidores; os compartilhados com L300 são preservados. Use o
[Desafio 07](07-recuperar-limpar.md) para decidir o encerramento completo, não para excluir
automaticamente a base reaproveitada.
Depois de conservar o resumo e as provas necessárias, apague somente os arquivos brutos e de
erro criados nesta prática e remova o segredo da sessão. A remoção dos arquivos não desfaz Azure:

```powershell
Remove-Item Env:\VARELEIRA_SEGREDO_LOGIN -ErrorAction SilentlyContinue
Remove-Variable planoArm -ErrorAction SilentlyContinue
```

**Resultado esperado:** ausência da aplicação e do deployment próprios comprovada por listagem;
base, identidade, papéis e aplicação L300 preservados. Não há prova de custo zero.

## Situação da validação

Na rodada histórica, catálogo, modelos e cotas foram conferidos; a guarda real do módulo recusou declaração
de versão incompatível. Uma falha 503 injetada no transporte da sonda acionou a contingência
e concluiu com fonte documentada; uma falha 403 parou após uma tentativa, sem troca.
Não houve interrupção regional real nem comprovação de cota adicional.
O [registro L400](../../docs/validacao/l400-validacao.md) preserva uso incerto e origem das falhas.

Em **11 de outubro de 2026**, esta receita foi revisada por leitura dos artefatos, ajuda offline
da Azure CLI 2.89.0, planos dos nove passos, compilação Bicep 0.48.1 e testes locais de operação,
sanitização e repositório. Blocos PowerShell e links foram conferidos localmente.
**Nenhuma consulta, implantação, construção de imagem, login ou limpeza Azure foi executada
nesta revisão.** Execução desta sequência no destino do aluno, prontidão real, consulta
autenticada e limpeza ficam pendentes de autorização e validação do operador.

## Glossário e referências

| Termo | Significado |
| --- | --- |
| Deployment | Instância nomeada de um modelo |
| Cota | Limite de capacidade disponível |
| SDK | Biblioteca usada para chamar um serviço |
| Retry | Nova tentativa após falha |
| Circuit breaker | Suspensão temporária de um destino após falhas |
| Azure CLI e ARM | Interface de linha de comando e serviço de administração dos recursos Azure |
| What-if e plano local | Simulação do destino pelo ARM e descrição local sem consulta ao destino |
| Sanitização e JSON | Redução de dados privados e formato de dados estruturados |
| SKU e capacidade | Tipo comercial de implantação e quantidade atribuída, na unidade correspondente |
| Implantação incremental | Reaplica os recursos declarados sem remover os que a fase não declara |
| Revisão e ingresso | Versão executável da aplicação e configuração de entrada dos pedidos |
| Tag e digest | Nome de versão da imagem e resumo criptográfico de seu conteúdo |
| Tenant, token e audiência | Diretório de identidades, comprovante de autenticação e seu destinatário |
| EasyAuth e HTTPS | Autenticação integrada na borda e protocolo web protegido |
| Diff | Comparação das alterações de arquivos antes de aceitá-las |

1. [Gestão de cotas dos modelos](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/quota).
2. [Autenticação por identidade gerenciada em Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/managed-identity).
3. [Princípios de novas tentativas](https://learn.microsoft.com/en-us/azure/architecture/patterns/retry).
4. [What-if e limites de previsão](https://learn.microsoft.com/en-us/azure/azure-resource-manager/bicep/deploy-what-if).
5. [Azure CLI: implantação de grupo](https://learn.microsoft.com/en-us/cli/azure/deployment/group?view=azure-cli-latest).
6. [Azure CLI: espera da implantação](https://learn.microsoft.com/en-us/cli/azure/deployment/group?view=azure-cli-latest#az-deployment-group-wait).
7. [Azure CLI: deployments de modelos](https://learn.microsoft.com/en-us/cli/azure/cognitiveservices/account/deployment?view=azure-cli-latest).
8. [Azure CLI: aplicação, listagem e remoção](https://learn.microsoft.com/en-us/cli/azure/containerapp?view=azure-cli-latest).
9. [Azure CLI: revisões](https://learn.microsoft.com/en-us/cli/azure/containerapp/revision?view=azure-cli-latest).
10. [Azure CLI: autenticação da aplicação](https://learn.microsoft.com/en-us/cli/azure/containerapp/auth?view=azure-cli-latest).
11. [Cobrança de Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/billing).

A ajuda local `--help` de cada comando Azure publicado foi conferida, incluindo seus parâmetros.
Referências online explicam o serviço; ajuda offline e parsing não comprovam uma execução Azure.

## Autoria

Texto por GPT-6.1 Sol; código por Claude Sonnet 5.5. Autoria, Copilot e modelos Azure são distintos.

Revisão documental por gpt-6-astra (Astra), em 11 de outubro de 2026, sem nova execução Azure.

Receita de implantação e promoção: GPT-6.1 Sol, com Astra indisponível, em 11 de outubro de 2026;
comandos verificados por ajuda offline; sem nova execução Azure.
