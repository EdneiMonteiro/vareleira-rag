metadata name = 'Vareleira RAG · L100 · Desafio 07 · Papéis da aplicação'
metadata description = 'Atribui à identidade da aplicação (service principal) só os papéis de leitura de que o assistente precisa: consultar o índice de busca e usar os deployments de modelos. Nenhum papel de escrita, de administração ou de acesso aos documentos e aos segredos.'

// Módulo chamado por main.bicep, que define os valores padrão e explica cada parâmetro.
targetScope = 'resourceGroup'

@description('Nome do serviço de busca criado no Desafio 02.')
param nomeBusca string

@description('Nome do recurso do Foundry criado no Desafio 02.')
param nomeModelos string

@description('ID de objeto, no Microsoft Entra ID, do service principal da aplicação (não é o ID da aplicação).')
param principalIdAplicacao string

// Papéis internos. Os IDs são públicos e iguais em todos os tenants.
var papelSearchIndexDataReader = '1407120a-92aa-4202-b7e9-c0e197c71c8f' // consulta documentos, sem gravar
var papelCognitiveServicesOpenAIUser = '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd' // usa os deployments, sem administrá-los

// Os dois recursos pertencem ao módulo do Desafio 02. Aqui eles só são referenciados.
resource busca 'Microsoft.Search/searchServices@2025-05-01' existing = {
  name: nomeBusca
}

resource modelos 'Microsoft.CognitiveServices/accounts@2026-07-01' existing = {
  name: nomeModelos
}

// Menor escopo que os papéis permitem aqui: o serviço de busca e o recurso de modelos, não o grupo.
// Exige que quem implanta possa criar atribuições de papel (por exemplo, Owner ou User Access Administrator).
resource atribuicaoConsultarIndice 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(busca.id, principalIdAplicacao, papelSearchIndexDataReader)
  scope: busca
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', papelSearchIndexDataReader)
    principalId: principalIdAplicacao
    principalType: 'ServicePrincipal'
  }
}

resource atribuicaoUsarModelos 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(modelos.id, principalIdAplicacao, papelCognitiveServicesOpenAIUser)
  scope: modelos
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      papelCognitiveServicesOpenAIUser
    )
    principalId: principalIdAplicacao
    principalType: 'ServicePrincipal'
  }
}

output papeisDaAplicacaoAtribuidos int = 2
