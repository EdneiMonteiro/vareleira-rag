metadata name = 'Vareleira RAG · L300 · Rede virtual e zonas DNS privadas'
metadata description = 'Cria a rede virtual do L300 com duas sub-redes dedicadas (ambiente do Azure Container Apps e endpoints privados) e as zonas DNS privadas usadas pelos endpoints de armazenamento (blob), busca e modelos, todas vinculadas à rede. Não altera nenhum serviço de dados existente.'

// Módulo chamado por l300.bicep (fase rede), que define os valores padrão e explica cada parâmetro.
targetScope = 'resourceGroup'

@description('Nome da rede virtual do L300.')
@minLength(2)
@maxLength(64)
param nomeRede string

@description('Região da rede virtual. A rede não pode ser movida de região depois de criada.')
param localizacao string

@description('Etiquetas aplicadas aos recursos criados por este módulo.')
param etiquetas object

@description('Espaço de endereços da rede virtual, em notação CIDR. As duas sub-redes precisam caber nele sem se sobrepor.')
param espacoEnderecos string

@description('Nome da sub-rede dedicada ao ambiente do Azure Container Apps.')
param nomeSubredeAmbiente string

@description('Prefixo CIDR da sub-rede do ambiente. O Azure Container Apps não permite trocar a sub-rede nem o tipo de rede depois que o ambiente existe.')
param prefixoSubredeAmbiente string

// Guardas calculadas por l300.bicep a partir dos prefixos: com valores fora dos limites, o ARM recusa este módulo antes de
// criar a rede. Um prefixo maior que /27 (menos endereços) não serve ao ambiente com perfis de carga.
@description('Bits de prefixo da sub-rede do ambiente. No máximo 27: /27 é o menor tamanho aceito pelo ambiente com perfis de carga.')
@minValue(16)
@maxValue(27)
param bitsPrefixoSubredeAmbiente int

@description('Nome da sub-rede dedicada aos endpoints privados.')
param nomeSubredeEndpoints string

@description('Prefixo CIDR da sub-rede dos endpoints privados. Cada endpoint ocupa um endereço, e o Azure reserva cinco por sub-rede.')
param prefixoSubredeEndpoints string

@description('Bits de prefixo da sub-rede dos endpoints. No máximo 28, para sobrar espaço além dos três endpoints do L300.')
@minValue(16)
@maxValue(28)
param bitsPrefixoSubredeEndpoints int

// Os nomes das zonas são os recomendados pela documentação do Private Link: só com eles os endpoints registram os
// endereços na zona sozinhos. O recurso de modelos (Foundry) pode expor três nomes públicos, e cada um precisa da zona
// correspondente. Nomes de nuvem pública.
var nomeZonaBlob = 'privatelink.blob.${environment().suffixes.storage}'
var nomeZonaBusca = 'privatelink.search.windows.net'
var nomeZonaCognitiveServices = 'privatelink.cognitiveservices.azure.com'
var nomeZonaOpenAI = 'privatelink.openai.azure.com'
var nomeZonaServicosIA = 'privatelink.services.ai.azure.com'

resource rede 'Microsoft.Network/virtualNetworks@2026-01-01' = {
  name: nomeRede
  location: localizacao
  tags: etiquetas
  properties: {
    addressSpace: {
      addressPrefixes: [
        espacoEnderecos
      ]
    }
  }
}

// As sub-redes são recursos filhos, e a rede não declara a propriedade `subnets`, como a documentação do Bicep recomenda:
// atualizar a rede sem essa propriedade mantém as sub-redes existentes, inclusive as que alguém acrescente depois (por
// exemplo, para um caminho de operação). Elas são criadas uma após a outra, para a rede não receber duas alterações ao
// mesmo tempo.
resource subredeAmbiente 'Microsoft.Network/virtualNetworks/subnets@2026-01-01' = {
  parent: rede
  name: nomeSubredeAmbiente
  properties: {
    addressPrefix: prefixoSubredeAmbiente
    delegations: [
      {
        name: 'Microsoft.App.environments'
        properties: {
          serviceName: 'Microsoft.App/environments'
        }
      }
    ]
  }
}

resource subredeEndpoints 'Microsoft.Network/virtualNetworks/subnets@2026-01-01' = {
  parent: rede
  name: nomeSubredeEndpoints
  dependsOn: [
    subredeAmbiente
  ]
  properties: {
    addressPrefix: prefixoSubredeEndpoints
    privateEndpointNetworkPolicies: 'Disabled'
  }
}

// Zonas privadas e vínculos com a rede. Sem registro automático de máquinas (registrationEnabled = false) e com a
// política de resolução padrão: nomes do mesmo tipo de serviço sem endpoint privado nesta rede não resolvem aqui. Os
// vínculos esperam as sub-redes, para a rede não receber duas alterações ao mesmo tempo.
resource zonaBlob 'Microsoft.Network/privateDnsZones@2024-06-01' = {
  name: nomeZonaBlob
  location: 'global'
  tags: etiquetas
}

resource zonaBusca 'Microsoft.Network/privateDnsZones@2024-06-01' = {
  name: nomeZonaBusca
  location: 'global'
  tags: etiquetas
}

resource zonaCognitiveServices 'Microsoft.Network/privateDnsZones@2024-06-01' = {
  name: nomeZonaCognitiveServices
  location: 'global'
  tags: etiquetas
}

resource zonaOpenAI 'Microsoft.Network/privateDnsZones@2024-06-01' = {
  name: nomeZonaOpenAI
  location: 'global'
  tags: etiquetas
}

resource zonaServicosIA 'Microsoft.Network/privateDnsZones@2024-06-01' = {
  name: nomeZonaServicosIA
  location: 'global'
  tags: etiquetas
}

resource vinculoBlob 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = {
  parent: zonaBlob
  name: 'vinculo-${nomeRede}'
  location: 'global'
  tags: etiquetas
  dependsOn: [
    subredeEndpoints
  ]
  properties: {
    registrationEnabled: false
    virtualNetwork: {
      id: rede.id
    }
  }
}

resource vinculoBusca 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = {
  parent: zonaBusca
  name: 'vinculo-${nomeRede}'
  location: 'global'
  tags: etiquetas
  dependsOn: [
    subredeEndpoints
  ]
  properties: {
    registrationEnabled: false
    virtualNetwork: {
      id: rede.id
    }
  }
}

resource vinculoCognitiveServices 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = {
  parent: zonaCognitiveServices
  name: 'vinculo-${nomeRede}'
  location: 'global'
  tags: etiquetas
  dependsOn: [
    subredeEndpoints
  ]
  properties: {
    registrationEnabled: false
    virtualNetwork: {
      id: rede.id
    }
  }
}

resource vinculoOpenAI 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = {
  parent: zonaOpenAI
  name: 'vinculo-${nomeRede}'
  location: 'global'
  tags: etiquetas
  dependsOn: [
    subredeEndpoints
  ]
  properties: {
    registrationEnabled: false
    virtualNetwork: {
      id: rede.id
    }
  }
}

resource vinculoServicosIA 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = {
  parent: zonaServicosIA
  name: 'vinculo-${nomeRede}'
  location: 'global'
  tags: etiquetas
  dependsOn: [
    subredeEndpoints
  ]
  properties: {
    registrationEnabled: false
    virtualNetwork: {
      id: rede.id
    }
  }
}

output idRede string = rede.id
output idSubredeAmbiente string = subredeAmbiente.id
output idSubredeEndpoints string = subredeEndpoints.id
output subredes object = {
  ambiente: {
    nome: nomeSubredeAmbiente
    prefixo: prefixoSubredeAmbiente
    bitsPrefixo: bitsPrefixoSubredeAmbiente
    delegadaA: 'Microsoft.App/environments'
  }
  endpoints: {
    nome: nomeSubredeEndpoints
    prefixo: prefixoSubredeEndpoints
    bitsPrefixo: bitsPrefixoSubredeEndpoints
  }
}
output idZonaBlob string = zonaBlob.id
output idZonaBusca string = zonaBusca.id
output idZonaCognitiveServices string = zonaCognitiveServices.id
output idZonaOpenAI string = zonaOpenAI.id
output idZonaServicosIA string = zonaServicosIA.id
output nomesZonas array = [
  nomeZonaBlob
  nomeZonaBusca
  nomeZonaCognitiveServices
  nomeZonaOpenAI
  nomeZonaServicosIA
]
