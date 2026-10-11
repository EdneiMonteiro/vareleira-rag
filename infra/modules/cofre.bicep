metadata name = 'Vareleira RAG · L100 · Desafio 07 · Cofre de segredos'
metadata description = 'Azure Key Vault com autorização por papéis (RBAC) para guardar o segredo da identidade da aplicação. Sem políticas de acesso antigas e com a proteção contra expurgo ligada por padrão.'

// Módulo chamado por main.bicep, que define os valores padrão e explica cada parâmetro.
targetScope = 'resourceGroup'

@description('Nome do cofre: de 3 a 24 caracteres, letras, números e hífens, começando por letra. Forma o endereço do cofre e é único no Azure.')
@minLength(3)
@maxLength(24)
param nomeCofre string

@description('Região do cofre.')
param localizacao string

@description('Dias em que um cofre ou um segredo excluído pode ser recuperado (exclusão reversível). O mínimo do Azure é 7.')
@minValue(7)
@maxValue(90)
param retencaoExclusaoDias int

@description('Liga a proteção contra expurgo: com ela, nem o dono nem o Azure expurgam o cofre ou os segredos excluídos antes do fim da retenção. Uma vez ligada, não pode ser desfeita, e o nome do cofre fica reservado durante a retenção. O padrão é ligada; o arquivo de parâmetros do laboratório a desliga para que a limpeza seja completa.')
param protecaoContraExpurgo bool = true

@description('ID de objeto, no Microsoft Entra ID, de quem guarda e lê os segredos. Vazio: nenhum papel é atribuído.')
param principalId string = ''

@description('Tipo da identidade informada em principalId.')
param tipoPrincipal string = 'User'

@description('Etiquetas aplicadas aos recursos criados por este módulo.')
param etiquetas object

// Papel interno "Key Vault Secrets Officer": cria, lê e exclui segredos, sem administrar o cofre nem as chaves.
// O ID é público e igual em todos os tenants.
var papelKeyVaultSecretsOfficer = 'b86a8fe4-44ce-4948-aee5-eccb2c155cd7'

// Segurança: o acesso aos segredos vem só dos papéis do Azure (enableRbacAuthorization). Quem pode criar o
// cofre não ganha, por isso, acesso aos segredos. A proteção contra expurgo vem ligada por padrão. O Azure não
// aceita o valor falso: para deixá-la desligada, a propriedade precisa ser omitida (null). O endereço
// continua público (autenticado); endpoints privados ficam para outro nível.
resource cofre 'Microsoft.KeyVault/vaults@2026-02-01' = {
  name: nomeCofre
  location: localizacao
  tags: etiquetas
  properties: {
    tenantId: tenant().tenantId
    sku: {
      family: 'A'
      name: 'standard'
    }
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: retencaoExclusaoDias
    enablePurgeProtection: protecaoContraExpurgo ? true : null
    publicNetworkAccess: 'Enabled'
  }
}

// Menor escopo possível: o papel vale somente para este cofre. Exige que quem implanta possa criar
// atribuições de papel (por exemplo, Owner ou User Access Administrator).
resource atribuicaoSegredos 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(principalId)) {
  name: guid(cofre.id, principalId, papelKeyVaultSecretsOfficer)
  scope: cofre
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', papelKeyVaultSecretsOfficer)
    principalId: principalId
    principalType: tipoPrincipal
  }
}

output nomeCofre string = cofre.name
output enderecoCofre string = cofre.properties.vaultUri
output papelDeSegredosAtribuido bool = !empty(principalId)
