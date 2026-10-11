metadata name = 'Vareleira RAG · L300 · Ambiente do Azure Container Apps integrado à rede'
metadata description = 'Cria o ambiente do Azure Container Apps do L300 (perfil Consumption) integrado à sub-rede dedicada da rede virtual do L300, com endereço de entrada externo (as aplicações continuam exigindo login) e logs enviados ao workspace do Log Analytics do L200, que já existe e é só referenciado. O ambiente do L200 não é alterado.'

// Módulo chamado por l300.bicep (fase rede), que define os valores padrão e explica cada parâmetro.
targetScope = 'resourceGroup'

@description('Nome do ambiente do L300, de 2 a 32 caracteres. Separado do ambiente do L200, porque a integração com uma rede virtual só é definida na criação do ambiente.')
@minLength(2)
@maxLength(32)
param nomeAmbiente string

@description('Região do ambiente, a mesma da rede virtual.')
param localizacao string

@description('Etiquetas aplicadas ao ambiente.')
param etiquetas object

@description('ID da sub-rede dedicada ao ambiente (delegada a Microsoft.App/environments). Depois de criado, o ambiente não troca de sub-rede nem de tipo de rede.')
param idSubredeAmbiente string

@description('Nome do workspace do Log Analytics criado no L200. O recurso já existe, no mesmo grupo de recursos.')
param nomeWorkspaceLogs string

resource logs 'Microsoft.OperationalInsights/workspaces@2026-03-01' existing = {
  name: nomeWorkspaceLogs
}

// Perfil Consumption, sem custo fixo de perfil dedicado. O ambiente tem rede virtual externa (internal = false): o endereço
// de entrada é público, e a aplicação do L300 ainda exige o login do Microsoft Entra ID. A plataforma exige a chave do
// workspace para enviar os logs: o Bicep a lê na hora da implantação e não a registra nas saídas. Ao criar o ambiente, a
// plataforma também cria um grupo de recursos gerenciado (ME_...), cujos recursos geram cobrança própria: não os altere
// nem os exclua manualmente.
resource ambiente 'Microsoft.App/managedEnvironments@2026-07-01' = {
  name: nomeAmbiente
  location: localizacao
  tags: etiquetas
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logs.properties.customerId
        sharedKey: logs.listKeys().primarySharedKey
      }
    }
    vnetConfiguration: {
      infrastructureSubnetId: idSubredeAmbiente
      internal: false
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

output idAmbiente string = ambiente.id
output nome string = ambiente.name
output dominioPadrao string = ambiente.properties.defaultDomain
output grupoRecursosGerenciado string = ambiente.properties.?infrastructureResourceGroup ?? ''
