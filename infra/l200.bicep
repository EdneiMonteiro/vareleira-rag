metadata name = 'Vareleira RAG · L200 · Identidades, registro de imagens e chat hospedado'
metadata description = 'Acrescenta ao L100 (armazenamento, busca e modelos, que já existem) a identidade gerenciada do serviço de busca para a ingestão e os papéis dela, e o necessário para hospedar o chat: registro de imagens, ambiente e aplicação do Azure Container Apps (plano Consumption) com identidade própria e login do Microsoft Entra ID. Etapas: (1) base do L200, com implantarAplicacao = false; (2) publicar a imagem no registro, fora do Bicep; (3) implantarAplicacao = true, com o ingresso fechado; (4) ingressoExterno = true.'

// Escopo: o mesmo grupo de recursos do L100. Este arquivo não recria o armazenamento, a busca nem os modelos:
// referencia o armazenamento e os modelos como recursos existentes e só reaplica a busca para ligar a identidade dela.
targetScope = 'resourceGroup'

@description('Nome da conta de armazenamento criada no L100 (saída nomeConta). O recurso já existe: o L200 só o referencia e não altera as proteções dele.')
@minLength(3)
@maxLength(24)
param nomeConta string

@description('Nome do contêiner de blobs com os documentos (o mesmo do L100).')
@minLength(3)
@maxLength(63)
param nomeContainer string = 'base-documental'

@description('Nome do serviço de busca criado no L100 (saída nomeBusca). Sem valor padrão, de propósito: um nome errado criaria outro serviço de busca, que cobra por hora.')
@minLength(2)
@maxLength(60)
param nomeBusca string

@description('Nome do recurso de modelos (Foundry) criado no L100 (saída nomeModelos). O recurso já existe: o L200 só o referencia.')
@minLength(2)
@maxLength(64)
param nomeModelos string

@description('Região do Azure para os recursos novos do L200. Por padrão, a do grupo de recursos.')
param localizacao string = resourceGroup().location

@description('Região do serviço de busca existente. Vazio: a região do grupo de recursos. Precisa ser a região real do serviço, porque o ARM não move recursos.')
param localizacaoBusca string = ''

@description('Ingestão gerenciada: declara o serviço de busca do L100 para ligar a identidade gerenciada do sistema dele e atribui a ela os papéis de leitura do contêiner de documentos e de uso dos modelos. Falso (padrão): o serviço de busca não é tocado.')
param habilitarIngestao bool = false

@description('Camada do serviço de busca existente. Precisa ser a atual: o ARM reaplica a configuração inteira do recurso. Identidade gerenciada exige "basic" ou superior; "free" não serve.')
@allowed([
  'basic'
  'standard'
])
param skuBusca string = 'basic'

@description('Réplicas do serviço de busca existente. Informe o valor atual: o ARM reaplica a configuração inteira, e o valor do L100 é 1.')
@minValue(1)
@maxValue(12)
param replicasBusca int = 1

@description('Partições do serviço de busca existente. Informe o valor atual: o ARM reaplica a configuração inteira, e o valor do L100 é 1.')
@allowed([
  1
  2
  3
  4
  6
  12
])
param particoesBusca int = 1

@description('Etiquetas do serviço de busca existente. O padrão repete as do L100, com nivel L100: o serviço é do L100, e a limpeza do L200 não deve removê-lo. Se o L100 usou etiquetasAdicionais, repita-as aqui, porque o ARM substitui as etiquetas.')
param etiquetasBusca object = {
  laboratorio: 'vareleira-rag'
  nivel: 'L100'
  desafio: '02'
  dados: 'sinteticos'
}

@description('Nome do registro de imagens (Azure Container Registry, camada Basic): de 5 a 50 caracteres, só letras minúsculas e números, único no Azure. A camada Basic cobra por dia enquanto o registro existir, mais o armazenamento das imagens.')
@minLength(5)
@maxLength(50)
param nomeRegistro string = 'crvlrag${uniqueString(resourceGroup().id)}'

@description('Nome do ambiente do Azure Container Apps (plano Consumption, sem rede virtual própria). Só o perfil Consumption: o ambiente não tem custo fixo, e a aplicação cobra pelo uso.')
@minLength(2)
@maxLength(32)
param nomeAmbiente string = 'cae-vlr-${uniqueString(resourceGroup().id)}'

@description('Nome da identidade gerenciada atribuída ao usuário que a aplicação usa. A identidade em si não tem custo. É um recurso separado da aplicação para receber os papéis antes de a aplicação existir.')
@minLength(3)
@maxLength(128)
param nomeIdentidadeAplicacao string = 'id-vlr-chat-${uniqueString(resourceGroup().id)}'

@description('Nome da aplicação do chat, de 2 a 32 caracteres (letras minúsculas, números e hífens). Forma o endereço público dela.')
@minLength(2)
@maxLength(32)
param nomeAplicacao string = 'ca-vlr-chat-${uniqueString(resourceGroup().id)}'

@description('Cria o workspace do Log Analytics e envia a ele os logs do ambiente. O workspace cobra por volume de logs ingeridos e retidos. Falso: o ambiente não guarda logs, e só a transmissão ao vivo fica disponível.')
param registrarLogs bool = true

@description('Nome do workspace do Log Analytics. Só tem efeito com registrarLogs.')
@minLength(4)
@maxLength(63)
param nomeWorkspaceLogs string = 'log-vlr-${uniqueString(resourceGroup().id)}'

@description('Dias de retenção dos logs no workspace. Só tem efeito com registrarLogs.')
@minValue(30)
@maxValue(730)
param retencaoLogsDias int = 30

@description('Cria a aplicação do chat. Só use depois de publicar a imagem no registro e de preencher tagImagem, idAplicacaoLogin, tenantLogin e segredoLogin: sem eles, o módulo da aplicação recusa a implantação. Falso (padrão): só a base do L200 é criada.')
param implantarAplicacao bool = false

@description('Abre o ingresso externo (endereço público, com login obrigatório). Mantenha falso na primeira implantação da aplicação: ela nasce alcançável só de dentro do ambiente, recebe a autenticação e só então é aberta. Só tem efeito junto com implantarAplicacao.')
param ingressoExterno bool = false

@description('Nome do repositório da imagem no registro. A imagem completa é <servidor do registro>/<repositorio>:<tag>.')
param repositorioImagem string = 'vareleira-chat'

@description('Tag da imagem publicada no registro antes da implantação (o Bicep não constrói imagens). Use uma tag imutável, como uma versão. Obrigatória com implantarAplicacao.')
param tagImagem string = ''

@description('ID do aplicativo (cliente) do registro de aplicativo próprio do chat no Microsoft Entra ID, criado fora do Bicep. Obrigatório com implantarAplicacao; não é segredo, mas não o fixe no repositório.')
@maxLength(36)
param idAplicacaoLogin string = ''

@description('ID do tenant do Microsoft Entra ID do registro de aplicativo. Obrigatório com implantarAplicacao; só pessoas desse tenant entram.')
@maxLength(36)
param tenantLogin string = ''

@description('Segredo de cliente do registro de aplicativo, necessário ao fluxo de login. Obrigatório com implantarAplicacao. Entra por variável de ambiente, nunca pelo arquivo de parâmetros nem pelo histórico.')
@secure()
param segredoLogin string = ''

@description('O que a plataforma faz com quem chega sem login: "Return401" responde 401; "RedirectToLoginPage" envia o navegador à página de login do Microsoft Entra ID.')
@allowed([
  'Return401'
  'RedirectToLoginPage'
])
param acaoSemLogin string = 'Return401'

@description('Nome do índice que a aplicação consulta e o ingestor do L200 cria, diferente do índice do L100. Os dois precisam usar o mesmo nome.')
@minLength(2)
@maxLength(128)
param nomeIndice string = 'vareleira-lar-l200'

@description('Nome do deployment de embeddings do L100. Indexação e consulta usam o mesmo deployment e as mesmas dimensões.')
param nomeDeploymentEmbeddings string = 'embeddings'

@description('Nome do deployment de geração do L100.')
param nomeDeploymentGeracao string = 'geracao'

@description('Dimensões dos vetores do índice, iguais às do modelo de embeddings (1536 para o text-embedding-3-small).')
@minValue(1)
@maxValue(3072)
param dimensoes int = 1536

@description('Modo de busca da aplicação: vetorial, texto ou hibrida. O padrão é o escolhido no Desafio 06 do L100.')
@allowed([
  'vetorial'
  'texto'
  'hibrida'
])
param modoBusca string = 'hibrida'

@description('Quantidade de trechos recuperados por pergunta. O padrão é o escolhido no Desafio 06 do L100.')
@minValue(1)
@maxValue(10)
param quantidadeTrechos int = 3

@description('Esforço de raciocínio do modelo de geração. O padrão é o do Desafio 06 do L100.')
@allowed([
  'none'
  'low'
  'medium'
  'high'
])
param esforco string = 'low'

@description('Etiquetas adicionais para os recursos criados pelo L200, combinadas com as do laboratório. Não inclua dados pessoais.')
param etiquetasAdicionais object = {}

var etiquetas = union(
  {
    laboratorio: 'vareleira-rag'
    nivel: 'L200'
    dados: 'sinteticos'
  },
  etiquetasAdicionais
)

var regiaoBusca = empty(localizacaoBusca) ? localizacao : localizacaoBusca

// ATENÇÃO: o serviço de busca é do L100. Para ligar a identidade dele, o ARM exige a declaração completa do
// recurso (PUT): o que for omitido volta ao padrão da API. Esta declaração repete, por isso, a configuração do L100
// (infra/modules/indexacao.bicep): região, camada, réplicas, partições, chaves de API desativadas (só Entra ID), endereço
// público e etiquetas. O único acréscimo é `identity`. Confira com `az deployment group what-if`: a mudança esperada é só a
// identidade. Se o serviço foi escalado ou recebeu etiquetas depois do L100, informe os valores atuais antes de
// implantar, senão o ARM os reverte. Se o nome não existir, o ARM cria um serviço novo, cobrado por hora.
// Com habilitarIngestao = falso, nada disso é declarado e a busca não é tocada.
// O L200 não exclui este serviço: nenhuma etapa do Bicep remove recursos.
resource buscaGerenciada 'Microsoft.Search/searchServices@2025-05-01' = if (habilitarIngestao) {
  name: nomeBusca
  location: regiaoBusca
  tags: etiquetasBusca
  sku: {
    name: skuBusca
  }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    replicaCount: replicasBusca
    partitionCount: particoesBusca
    publicNetworkAccess: 'Enabled'
    disableLocalAuth: true
  }
}

resource logs 'Microsoft.OperationalInsights/workspaces@2026-03-01' = if (registrarLogs) {
  name: nomeWorkspaceLogs
  location: localizacao
  tags: etiquetas
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: retencaoLogsDias
  }
}

// Sem usuário e senha de administrador: a identidade da aplicação baixa imagens pelo papel AcrPull. O endereço
// continua público (autenticado); endpoints privados ficam para outro nível, e exigiriam a camada Premium.
resource registro 'Microsoft.ContainerRegistry/registries@2025-11-01' = {
  name: nomeRegistro
  location: localizacao
  tags: etiquetas
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: false
    publicNetworkAccess: 'Enabled'
  }
}

resource identidadeAplicacao 'Microsoft.ManagedIdentity/userAssignedIdentities@2024-11-30' = {
  name: nomeIdentidadeAplicacao
  location: localizacao
  tags: etiquetas
}

// Ambiente com o perfil Consumption e sem rede virtual própria. A plataforma exige a chave do workspace para
// enviar os logs (destination log-analytics): o Bicep a lê na hora da implantação e não a registra nas saídas.
resource ambiente 'Microsoft.App/managedEnvironments@2026-07-01' = {
  name: nomeAmbiente
  location: localizacao
  tags: etiquetas
  properties: {
    appLogsConfiguration: registrarLogs
      ? {
          destination: 'log-analytics'
          logAnalyticsConfiguration: {
            customerId: logs!.properties.customerId
            sharedKey: logs!.listKeys().primarySharedKey
          }
        }
      : {
          destination: 'none'
        }
    workloadProfiles: [
      {
        name: 'Consumption'
        workloadProfileType: 'Consumption'
      }
    ]
    zoneRedundant: false
    publicNetworkAccess: 'Enabled'
  }
}

// Papéis de dados das duas identidades, no menor escopo. Os IDs de objeto são lidos dos próprios recursos, o que
// também faz o módulo esperar a identidade da busca. A ordem importa: os papéis precisam existir antes de a aplicação
// baixar a imagem e consultar a busca.
module identidades 'modules/l200-identidades.bicep' = {
  name: 'l200-identidades'
  dependsOn: [
    registro
  ]
  params: {
    nomeConta: nomeConta
    nomeContainer: nomeContainer
    nomeBusca: nomeBusca
    nomeModelos: nomeModelos
    nomeRegistro: nomeRegistro
    principalIdBusca: buscaGerenciada.?identity.principalId ?? ''
    principalIdAplicacao: identidadeAplicacao.properties.principalId
  }
}

module aplicacao 'modules/l200-aplicacao.bicep' = if (implantarAplicacao) {
  name: 'l200-aplicacao'
  dependsOn: [
    identidades
  ]
  params: {
    nomeAplicacao: nomeAplicacao
    localizacao: localizacao
    etiquetas: etiquetas
    idAmbiente: ambiente.id
    servidorRegistro: registro.properties.loginServer
    idIdentidade: identidadeAplicacao.id
    clientIdIdentidade: identidadeAplicacao.properties.clientId
    repositorioImagem: repositorioImagem
    tagImagem: tagImagem
    ingressoExterno: ingressoExterno
    idAplicacaoLogin: idAplicacaoLogin
    tenantLogin: tenantLogin
    segredoLogin: segredoLogin
    acaoSemLogin: acaoSemLogin
    nomeBusca: nomeBusca
    nomeModelos: nomeModelos
    nomeIndice: nomeIndice
    nomeDeploymentEmbeddings: nomeDeploymentEmbeddings
    nomeDeploymentGeracao: nomeDeploymentGeracao
    dimensoes: dimensoes
    modoBusca: modoBusca
    quantidadeTrechos: quantidadeTrechos
    esforco: esforco
  }
}

output nomeRegistro string = registro.name
output servidorRegistro string = registro.properties.loginServer
output nomeAmbiente string = ambiente.name
output dominioAmbiente string = ambiente.properties.defaultDomain
output nomeIdentidadeAplicacao string = identidadeAplicacao.name
output principalIdIdentidadeAplicacao string = identidadeAplicacao.properties.principalId
output clientIdIdentidadeAplicacao string = identidadeAplicacao.properties.clientId
output nomeWorkspaceLogs string = logs.?name ?? ''
output principalIdBusca string = buscaGerenciada.?identity.principalId ?? ''
output papeisAtribuidos int = identidades.outputs.papeisAtribuidos

// Informe este endereço de retorno no registro de aplicativo antes da etapa da aplicação. Vale para o ingresso
// externo: o endereço da aplicação é <nome>.<domínio do ambiente>.
output urlRetornoLogin string = 'https://${nomeAplicacao}.${ambiente.properties.defaultDomain}/.auth/login/aad/callback'
output idAplicacaoLogin string = idAplicacaoLogin

// Vazios quando a aplicação não foi implantada.
var enderecoAplicacao = aplicacao.?outputs.enderecoAplicacao ?? ''

output nomeAplicacao string = aplicacao.?outputs.nome ?? ''
output nomeRevisaoAtual string = aplicacao.?outputs.nomeRevisaoAtual ?? ''
output urlAplicacao string = implantarAplicacao && ingressoExterno ? 'https://${enderecoAplicacao}' : ''
