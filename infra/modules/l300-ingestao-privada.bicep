metadata name = 'Vareleira RAG · L300 · Conexões privadas compartilhadas da busca'
metadata description = 'Cria as duas conexões privadas compartilhadas (shared private links) do serviço de busca existente: uma para o armazenamento (grupo blob) e outra para o recurso de modelos (grupo openai_account), usadas pelo indexador no ambiente de execução privado. A criação NÃO aprova as conexões: elas ficam pendentes até a aprovação, fora do Bicep, em cada recurso de destino.'

// Módulo chamado por l300.bicep (fase rede), que define os valores padrão e explica cada parâmetro.
targetScope = 'resourceGroup'

@description('Nome do serviço de busca criado no L100. O recurso já existe: este módulo só acrescenta as conexões compartilhadas a ele e não redeclara o serviço.')
param nomeBusca string

@description('ID do recurso da conta de armazenamento do L100 (destino da conexão blob).')
param idConta string

@description('ID do recurso de modelos (Foundry) do L100 (destino da conexão de modelos).')
param idModelos string

@description('Nome da conexão compartilhada com o armazenamento: de 1 a 60 caracteres (letras, números, hífen, ponto e sublinhado).')
@minLength(1)
@maxLength(60)
param nomeLinkBlob string

@description('Nome da conexão compartilhada com os modelos.')
@minLength(1)
@maxLength(60)
param nomeLinkModelos string

@description('Grupo (subrecurso) da conexão com os modelos, sensível a maiúsculas. openai_account é o documentado para modelos de embeddings do Azure OpenAI na vetorização integrada. foundry_account é o grupo documentado para habilidades com modelos hospedados em recurso Foundry, e a documentação da camada Basic restringe conexões privadas com recurso Foundry.')
@allowed([
  'openai_account'
  'foundry_account'
])
param grupoLinkModelos string

var mensagemSolicitacao = 'Vareleira L300: indexador privado da busca'

resource busca 'Microsoft.Search/searchServices@2025-05-01' existing = {
  name: nomeBusca
}

// A criação é lenta e fica pendente: o proprietário do recurso de destino precisa aprovar a conexão. Só existe uma
// conexão por combinação de recurso e subrecurso. Por precaução, a segunda conexão espera a primeira: o serviço de busca
// pode recusar alterações simultâneas.
resource linkBlob 'Microsoft.Search/searchServices/sharedPrivateLinkResources@2025-05-01' = {
  parent: busca
  name: nomeLinkBlob
  properties: {
    groupId: 'blob'
    privateLinkResourceId: idConta
    requestMessage: mensagemSolicitacao
  }
}

resource linkModelos 'Microsoft.Search/searchServices/sharedPrivateLinkResources@2025-05-01' = {
  parent: busca
  name: nomeLinkModelos
  dependsOn: [
    linkBlob
  ]
  properties: {
    groupId: grupoLinkModelos
    privateLinkResourceId: idModelos
    requestMessage: mensagemSolicitacao
  }
}

// O estado esperado logo após a criação é Pending: aprove cada conexão no recurso de destino antes de fechar o acesso público.
output links array = [
  {
    nome: linkBlob.name
    id: linkBlob.id
    grupo: 'blob'
    idRecursoDestino: idConta
    estado: linkBlob.properties.?status ?? 'desconhecido'
    estadoProvisionamento: linkBlob.properties.?provisioningState ?? 'desconhecido'
  }
  {
    nome: linkModelos.name
    id: linkModelos.id
    grupo: grupoLinkModelos
    idRecursoDestino: idModelos
    estado: linkModelos.properties.?status ?? 'desconhecido'
    estadoProvisionamento: linkModelos.properties.?provisioningState ?? 'desconhecido'
  }
]
