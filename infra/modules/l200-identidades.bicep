metadata name = 'Vareleira RAG · L200 · Papéis das identidades gerenciadas'
metadata description = 'Atribui, no menor escopo possível, os papéis de dados das duas identidades gerenciadas do L200: a do serviço de busca (indexador e vetorização integrada) e a da aplicação do chat. O armazenamento, os modelos, a busca e o registro de imagens são criados fora deste módulo: aqui eles só são referenciados.'

// Módulo chamado por l200.bicep, que define os valores padrão e explica cada parâmetro.
targetScope = 'resourceGroup'

@description('Nome da conta de armazenamento do L100.')
param nomeConta string

@description('Nome do contêiner de blobs com os documentos do L100.')
param nomeContainer string

@description('Nome do serviço de busca do L100.')
param nomeBusca string

@description('Nome do recurso de modelos (Foundry) do L100.')
param nomeModelos string

@description('Nome do registro de imagens do L200.')
param nomeRegistro string

// Os IDs de objeto chegam como parâmetros, lidos dos próprios recursos pelo l200.bicep, para que o nome de cada
// atribuição (guid) mude quando uma identidade é recriada. Com isso, uma atribuição órfã de uma identidade excluída
// não bloqueia a nova (o ARM não permite trocar o principal de uma atribuição existente).
@description('ID de objeto da identidade gerenciada do sistema do serviço de busca. Vazio: a ingestão está desligada e nenhum papel é atribuído a ela.')
param principalIdBusca string = ''

@description('ID de objeto da identidade gerenciada atribuída ao usuário que a aplicação usa.')
param principalIdAplicacao string

// Papéis internos. Os IDs são públicos e iguais em todos os tenants.
var papelStorageBlobDataReader = '2a2b9908-6ea1-4ae2-8e65-a410df84e7d1' // lê blobs, sem gravar nem excluir
var papelCognitiveServicesOpenAIUser = '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd' // usa os deployments, sem administrá-los
var papelSearchIndexDataReader = '1407120a-92aa-4202-b7e9-c0e197c71c8f' // consulta documentos, sem gravar
var papelAcrPull = '7f951dda-4ed3-4680-a7ca-43fe172d538d' // baixa imagens, sem enviá-las nem apagá-las

// Os recursos pertencem ao L100 (armazenamento, busca e modelos) e a l200.bicep (registro). Aqui eles só são referenciados.
resource conta 'Microsoft.Storage/storageAccounts@2026-06-01' existing = {
  name: nomeConta
}

resource servicoBlob 'Microsoft.Storage/storageAccounts/blobServices@2026-06-01' existing = {
  parent: conta
  name: 'default'
}

resource containerDocumentos 'Microsoft.Storage/storageAccounts/blobServices/containers@2026-06-01' existing = {
  parent: servicoBlob
  name: nomeContainer
}

resource busca 'Microsoft.Search/searchServices@2025-05-01' existing = {
  name: nomeBusca
}

resource modelos 'Microsoft.CognitiveServices/accounts@2026-07-01' existing = {
  name: nomeModelos
}

resource registro 'Microsoft.ContainerRegistry/registries@2025-11-01' existing = {
  name: nomeRegistro
}

// Serviço de busca (ingestão gerenciada): lê os blobs só do contêiner dos documentos e usa o deployment de
// embeddings na vetorização integrada. Sem papel de escrita no armazenamento: o indexador lê, não altera a fonte.
// Exigem que quem implanta possa criar atribuições de papel (por exemplo, Owner ou User Access Administrator).
resource atribuicaoBuscaLerBlobs 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(principalIdBusca)) {
  name: guid(containerDocumentos.id, principalIdBusca, papelStorageBlobDataReader)
  scope: containerDocumentos
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', papelStorageBlobDataReader)
    principalId: principalIdBusca
    principalType: 'ServicePrincipal'
  }
}

resource atribuicaoBuscaUsarModelos 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(principalIdBusca)) {
  name: guid(modelos.id, principalIdBusca, papelCognitiveServicesOpenAIUser)
  scope: modelos
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      papelCognitiveServicesOpenAIUser
    )
    principalId: principalIdBusca
    principalType: 'ServicePrincipal'
  }
}

// Aplicação do chat: baixa a imagem do registro, consulta o índice e usa os deployments. Nenhum papel de escrita
// na busca, nenhum acesso aos documentos e nenhum cofre de segredos.
resource atribuicaoAplicacaoBaixarImagem 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(registro.id, principalIdAplicacao, papelAcrPull)
  scope: registro
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', papelAcrPull)
    principalId: principalIdAplicacao
    principalType: 'ServicePrincipal'
  }
}

resource atribuicaoAplicacaoConsultarIndice 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(busca.id, principalIdAplicacao, papelSearchIndexDataReader)
  scope: busca
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', papelSearchIndexDataReader)
    principalId: principalIdAplicacao
    principalType: 'ServicePrincipal'
  }
}

resource atribuicaoAplicacaoUsarModelos 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
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

output papeisAtribuidos int = (empty(principalIdBusca) ? 0 : 2) + 3
