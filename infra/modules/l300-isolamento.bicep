metadata name = 'Vareleira RAG · L300 · Isolamento dos serviços de dados'
metadata description = 'Fecha o acesso público (publicNetworkAccess = Disabled) da conta de armazenamento, do serviço de busca e do recurso de modelos (Foundry) criados no L100, que passam a aceitar só os endpoints privados. Como o ARM reaplica o recurso inteiro (PUT), este módulo repete a configuração completa do L100 e do L200 e só muda o acesso público. Só executa com a conectividade privada validada, as duas conexões compartilhadas da busca aprovadas e a configuração informada igual à atual.'

// Módulo chamado por l300.bicep (fase isolar), que define os valores padrão e explica cada parâmetro.
// ATENÇÃO: este é o único módulo do L300 que altera serviços existentes. Ele não remove nenhum recurso: contêineres,
// deployments, conexões, endpoints e atribuições de papel não são declarados aqui e ficam como estão.
targetScope = 'resourceGroup'

// ---- Guardas ----
// Os cinco valores abaixo são repassados ao módulo de guardas, cujos parâmetros aceitam um único valor. Os três recursos
// dependem desse módulo: se alguma guarda falhar, o ARM recusa a implantação antes de criar ou alterar qualquer serviço.

@description('Autorização explícita de quem opera: só use verdadeiro depois de demonstrar, na rede do L300, a consulta, a ingestão e a resolução de nomes privadas, e de ter autorização do responsável. É uma declaração, não uma medição: o Bicep não consegue conferir a rede.')
param conectividadePrivadaValidada bool

@description('Estado da conexão compartilhada da busca com o armazenamento, lido do serviço de busca por l300.bicep. Só Approved é aceito: a aprovação é feita no armazenamento, fora do Bicep.')
param estadoLinkArmazenamento string

@description('Estado da conexão compartilhada da busca com os modelos, lido do serviço de busca por l300.bicep. Só Approved é aceito: a aprovação é feita no recurso de modelos, fora do Bicep.')
param estadoLinkModelos string

@description('Resultado da comparação, feita por l300.bicep, entre a camada, as réplicas e as partições informadas e as do serviço de busca atual. Precisa ser verdadeiro, para o ARM não reverter uma configuração diferente.')
param configuracaoBuscaConfere bool

@description('Resultado da comparação, feita por l300.bicep, entre a redundância informada e a da conta de armazenamento atual. Precisa ser verdadeiro.')
param configuracaoArmazenamentoConfere bool

// ---- Armazenamento ----
@description('Nome da conta de armazenamento criada no L100.')
@minLength(3)
@maxLength(24)
param nomeConta string

@description('Região real da conta de armazenamento. Uma região diferente da atual faz o ARM recusar a reaplicação.')
param localizacaoArmazenamento string

@description('Redundância atual da conta de armazenamento. Sem valor padrão, de propósito: o ARM reaplica a configuração inteira, e uma redundância diferente da atual pediria a conversão da conta.')
@minLength(1)
@allowed([
  'Standard_LRS'
  'Standard_ZRS'
  'Standard_GRS'
])
param skuArmazenamento string

@description('Etiquetas atuais da conta de armazenamento. O ARM substitui as etiquetas: repita as que existem.')
param etiquetasArmazenamento object

// ---- Busca ----
@description('Nome do serviço de busca criado no L100.')
@minLength(2)
@maxLength(60)
param nomeBusca string

@description('Região real do serviço de busca.')
param localizacaoBusca string

@description('Camada atual do serviço de busca. Sem valor padrão, de propósito. Identidade gerenciada e conexões compartilhadas exigem "basic" ou superior.')
@minLength(1)
@allowed([
  'basic'
  'standard'
])
param skuBusca string

@description('Réplicas atuais do serviço de busca. Sem valor padrão: uma contagem diferente da atual escalaria o serviço.')
@minValue(1)
@maxValue(12)
param replicasBusca int

@description('Partições atuais do serviço de busca. Sem valor padrão: uma contagem diferente da atual escalaria o serviço.')
@allowed([
  1
  2
  3
  4
  6
  12
])
param particoesBusca int

@description('Etiquetas atuais do serviço de busca. O ARM substitui as etiquetas: repita as que existem.')
param etiquetasBusca object

// ---- Modelos ----
@description('Nome do recurso de modelos (Foundry) criado no L100. Também é o subdomínio do endereço, e não pode mudar.')
@minLength(2)
@maxLength(64)
param nomeModelos string

@description('Região real do recurso de modelos.')
param localizacaoModelos string

@description('Etiquetas atuais do recurso de modelos. O ARM substitui as etiquetas: repita as que existem.')
param etiquetasModelos object

module guarda 'l300-guarda-isolamento.bicep' = {
  name: 'l300-guarda-isolamento'
  params: {
    conectividadePrivadaValidada: conectividadePrivadaValidada
    estadoLinkArmazenamento: estadoLinkArmazenamento
    estadoLinkModelos: estadoLinkModelos
    configuracaoBuscaConfere: configuracaoBuscaConfere
    configuracaoArmazenamentoConfere: configuracaoArmazenamentoConfere
  }
}

// Os três recursos abaixo são do L100 (e, no caso da busca, do L200). As declarações repetem a configuração deles
// (infra/main.bicep, infra/modules/indexacao.bicep e infra/l200.bicep), com os mesmos tipos e versões de API: o que for
// omitido volta ao padrão da API. A única diferença é publicNetworkAccess = 'Disabled'. Os deployments de modelos e o
// serviço de blobs são recursos filhos e não são tocados. Confira com `az deployment group what-if`: a mudança esperada é
// só o acesso público de cada serviço.

resource conta 'Microsoft.Storage/storageAccounts@2026-06-01' = {
  name: nomeConta
  location: localizacaoArmazenamento
  tags: etiquetasArmazenamento
  sku: {
    name: skuArmazenamento
  }
  kind: 'StorageV2'
  dependsOn: [
    guarda
  ]
  properties: {
    accessTier: 'Hot'
    allowBlobPublicAccess: false
    allowSharedKeyAccess: false
    allowCrossTenantReplication: false
    defaultToOAuthAuthentication: true
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    publicNetworkAccess: 'Disabled'
  }
}

resource busca 'Microsoft.Search/searchServices@2025-05-01' = {
  name: nomeBusca
  location: localizacaoBusca
  tags: etiquetasBusca
  sku: {
    name: skuBusca
  }
  identity: {
    type: 'SystemAssigned'
  }
  dependsOn: [
    guarda
  ]
  properties: {
    replicaCount: replicasBusca
    partitionCount: particoesBusca
    publicNetworkAccess: 'Disabled'
    disableLocalAuth: true
  }
}

resource modelos 'Microsoft.CognitiveServices/accounts@2026-07-01' = {
  name: nomeModelos
  location: localizacaoModelos
  tags: etiquetasModelos
  kind: 'AIServices'
  sku: {
    name: 'S0'
  }
  dependsOn: [
    guarda
  ]
  properties: {
    customSubDomainName: nomeModelos
    disableLocalAuth: true
    publicNetworkAccess: 'Disabled'
  }
}

output acessoPublico object = {
  armazenamento: conta.properties.?publicNetworkAccess ?? 'desconhecido'
  busca: busca.properties.?publicNetworkAccess ?? 'desconhecido'
  modelos: modelos.properties.?publicNetworkAccess ?? 'desconhecido'
}

// Guardas que valeram quando o módulo executou (qualquer outro valor teria impedido a execução).
output guardasAtendidas object = guarda.outputs.atendidas
