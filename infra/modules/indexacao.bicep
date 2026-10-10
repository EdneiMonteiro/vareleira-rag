metadata name = 'Vareleira RAG · L100 · Desafio 02 · Busca e modelos'
metadata description = 'Serviço de busca (Azure AI Search) e recurso do Microsoft Foundry com um deployment de embeddings, ambos acessados somente por Microsoft Entra ID.'

// Módulo chamado por main.bicep, que define os valores padrão e explica cada parâmetro.
targetScope = 'resourceGroup'

@description('Nome do serviço de busca. Forma o endereço do serviço.')
param nomeBusca string

@description('Nome do recurso do Foundry. Também é o subdomínio do endereço, exigido para autenticar com Entra ID.')
param nomeModelos string

@description('Região do serviço de busca.')
param localizacaoBusca string

@description('Região do recurso de modelos.')
param localizacaoModelos string

@description('Camada do serviço de busca.')
param skuBusca string

@description('Nome do modelo de embeddings.')
param modeloEmbeddings string

@description('Versão do modelo de embeddings.')
param versaoModeloEmbeddings string

@description('Nome do deployment de embeddings.')
param nomeDeploymentEmbeddings string

@description('Tipo de implantação do modelo.')
param skuDeploymentEmbeddings string

@description('Cota do deployment, em milhares de tokens por minuto.')
param capacidadeEmbeddings int

@description('ID de objeto, no Microsoft Entra ID, de quem criará o índice, indexará e consultará. Vazio: nenhum papel é atribuído.')
param principalId string = ''

@description('Tipo da identidade informada em principalId.')
param tipoPrincipal string = 'User'

@description('Etiquetas aplicadas aos recursos criados por este módulo.')
param etiquetas object

// Papéis internos. Os IDs são públicos e iguais em todos os tenants.
var papelSearchServiceContributor = '7ca78c08-252a-4471-8644-bb5ff32d4ba0' // cria e altera índices
var papelSearchIndexDataContributor = '8ebe5a00-799e-43f5-93ac-243d3dce84a7' // grava e consulta documentos
var papelCognitiveServicesOpenAIUser = '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd' // usa os deployments, sem administrá-los

// Chaves de API desativadas (disableLocalAuth): só quem tem papel no Entra ID acessa os dados.
// Quem pode criar o serviço não ganha, por isso, acesso aos índices. O endereço continua público
// (autenticado); endpoints privados ficam para outro nível.
resource busca 'Microsoft.Search/searchServices@2025-05-01' = {
  name: nomeBusca
  location: localizacaoBusca
  tags: etiquetas
  sku: {
    name: skuBusca
  }
  properties: {
    replicaCount: 1
    partitionCount: 1
    publicNetworkAccess: 'Enabled'
    disableLocalAuth: true
  }
}

resource modelos 'Microsoft.CognitiveServices/accounts@2026-07-01' = {
  name: nomeModelos
  location: localizacaoModelos
  tags: etiquetas
  kind: 'AIServices'
  sku: {
    name: 'S0'
  }
  properties: {
    customSubDomainName: nomeModelos
    disableLocalAuth: true
    publicNetworkAccess: 'Enabled'
  }
}

// A versão fica fixa (NoAutoUpgrade): trocar o modelo ou a versão depois de indexar tornaria
// os vetores do índice incompatíveis com os das perguntas.
resource implantacaoEmbeddings 'Microsoft.CognitiveServices/accounts/deployments@2026-07-01' = {
  parent: modelos
  name: nomeDeploymentEmbeddings
  sku: {
    name: skuDeploymentEmbeddings
    capacity: capacidadeEmbeddings
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: modeloEmbeddings
      version: versaoModeloEmbeddings
    }
    versionUpgradeOption: 'NoAutoUpgrade'
  }
}

// Menor escopo que os papéis permitem aqui: o serviço de busca e o recurso de modelos, não o grupo.
// Exige que quem implanta possa criar atribuições de papel (por exemplo, Owner ou User Access Administrator).
resource atribuicaoCriarIndice 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(principalId)) {
  name: guid(busca.id, principalId, papelSearchServiceContributor)
  scope: busca
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', papelSearchServiceContributor)
    principalId: principalId
    principalType: tipoPrincipal
  }
}

resource atribuicaoDadosDoIndice 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(principalId)) {
  name: guid(busca.id, principalId, papelSearchIndexDataContributor)
  scope: busca
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', papelSearchIndexDataContributor)
    principalId: principalId
    principalType: tipoPrincipal
  }
}

resource atribuicaoUsarModelos 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(principalId)) {
  name: guid(modelos.id, principalId, papelCognitiveServicesOpenAIUser)
  scope: modelos
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      papelCognitiveServicesOpenAIUser
    )
    principalId: principalId
    principalType: tipoPrincipal
  }
}

output nomeBusca string = busca.name
output enderecoBusca string = busca.properties.endpoint
output nomeModelos string = modelos.name
output enderecoModelos string = modelos.properties.endpoint
output nomeDeploymentEmbeddings string = implantacaoEmbeddings.name
output modeloEmbeddings string = implantacaoEmbeddings.properties.model.name
output papeisDeDadosAtribuidos bool = !empty(principalId)
