metadata name = 'Vareleira RAG · L300 · Contêiner da base documental e papéis de dados'
metadata description = 'Cria o contêiner de blobs base-documental-l300 na conta de armazenamento do L100 (que não é redeclarada nem alterada) e atribui, só no escopo desse contêiner, o papel de leitura à identidade gerenciada da busca e o papel de gravação a quem envia os documentos.'

// Módulo chamado por l300.bicep (fase rede), que define os valores padrão e explica cada parâmetro.
targetScope = 'resourceGroup'

@description('Nome da conta de armazenamento criada no L100. O recurso já existe: este módulo só cria um contêiner nele.')
param nomeConta string

@description('Nome do contêiner de blobs do L300, diferente do contêiner do L100 (que continua intacto).')
@minLength(3)
@maxLength(63)
param nomeContainer string

// Os IDs de objeto chegam como parâmetros com tamanho fixo de 36 caracteres: vazios ou truncados, o ARM recusa este módulo
// antes de criar o contêiner. As duas atribuições são obrigatórias: sem a primeira, o indexador não lê o contêiner;
// sem a segunda, ninguém consegue enviar documentos (o armazenamento não aceita chaves de conta).
@description('ID de objeto da identidade gerenciada do sistema do serviço de busca (habilitada no L200). Lido do próprio serviço por l300.bicep.')
@minLength(36)
@maxLength(36)
param principalIdBusca string

@description('ID de objeto, no Microsoft Entra ID, de quem envia os documentos ao contêiner do L300.')
@minLength(36)
@maxLength(36)
param principalIdCarga string

@description('Tipo da identidade informada em principalIdCarga.')
@allowed([
  'User'
  'Group'
  'ServicePrincipal'
])
param tipoPrincipalCarga string

// Papéis internos. Os IDs são públicos e iguais em todos os tenants.
var papelStorageBlobDataReader = '2a2b9908-6ea1-4ae2-8e65-a410df84e7d1' // lê blobs, sem gravar nem excluir
var papelStorageBlobDataContributor = 'ba92f5b4-2d11-453d-a403-e96b0029c9fe' // lê, grava e exclui blobs, sem gerenciar a conta

// A conta e o serviço de blobs são do L100: aqui eles só são referenciados. As políticas de exclusão reversível e de
// versões do serviço de blobs continuam as do L100, porque este módulo não as declara.
resource conta 'Microsoft.Storage/storageAccounts@2026-06-01' existing = {
  name: nomeConta
}

resource servicoBlob 'Microsoft.Storage/storageAccounts/blobServices@2026-06-01' existing = {
  parent: conta
  name: 'default'
}

resource containerDocumentos 'Microsoft.Storage/storageAccounts/blobServices/containers@2026-06-01' = {
  parent: servicoBlob
  name: nomeContainer
  properties: {
    publicAccess: 'None'
  }
}

// Menor escopo possível: os dois papéis valem só para este contêiner, nunca para a conta nem para o grupo de recursos.
// Exigem que quem implanta possa criar atribuições de papel (por exemplo, Owner ou User Access Administrator).
resource atribuicaoBuscaLerBlobs 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(containerDocumentos.id, principalIdBusca, papelStorageBlobDataReader)
  scope: containerDocumentos
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', papelStorageBlobDataReader)
    principalId: principalIdBusca
    principalType: 'ServicePrincipal'
  }
}

resource atribuicaoCarga 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(containerDocumentos.id, principalIdCarga, papelStorageBlobDataContributor)
  scope: containerDocumentos
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', papelStorageBlobDataContributor)
    principalId: principalIdCarga
    principalType: tipoPrincipalCarga
  }
}

output nomeContainer string = containerDocumentos.name
output papeisAtribuidos int = 2
