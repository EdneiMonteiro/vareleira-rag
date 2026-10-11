metadata name = 'Vareleira RAG · L300 · Endpoints privados dos serviços de dados'
metadata description = 'Cria, na sub-rede de endpoints, um endpoint privado para o armazenamento (blob), um para a busca e um para o recurso de modelos (Foundry), cada um ligado às zonas DNS privadas correspondentes. Os serviços de destino já existem e não são alterados: o acesso público continua como está.'

// Módulo chamado por l300.bicep (fase rede), que define os valores padrão e explica cada parâmetro.
targetScope = 'resourceGroup'

@description('Região dos endpoints, a mesma da rede virtual.')
param localizacao string

@description('Etiquetas aplicadas aos recursos criados por este módulo.')
param etiquetas object

@description('ID da sub-rede dos endpoints privados.')
param idSubredeEndpoints string

@description('ID da zona DNS privada do blob.')
param idZonaBlob string

@description('ID da zona DNS privada da busca.')
param idZonaBusca string

@description('ID da zona DNS privada de cognitiveservices.azure.com.')
param idZonaCognitiveServices string

@description('ID da zona DNS privada de openai.azure.com.')
param idZonaOpenAI string

@description('ID da zona DNS privada de services.ai.azure.com.')
param idZonaServicosIA string

@description('ID do recurso da conta de armazenamento do L100 (destino do endpoint blob).')
param idConta string

@description('ID do recurso do serviço de busca do L100 (destino do endpoint da busca).')
param idBusca string

@description('ID do recurso de modelos (Foundry) do L100 (destino do endpoint de modelos).')
param idModelos string

@description('Nome do endpoint privado do armazenamento.')
param nomeEndpointBlob string

@description('Nome do endpoint privado da busca.')
param nomeEndpointBusca string

@description('Nome do endpoint privado dos modelos.')
param nomeEndpointModelos string

var mensagemSolicitacao = 'Vareleira L300: endpoint privado da aplicação do chat'

// Cada endpoint pede a conexão pelo caminho automático (privateLinkServiceConnections). Ela só é aprovada na hora se quem
// implanta puder aprovar conexões no recurso de destino; caso contrário, fica pendente e precisa de aprovação no
// destino. O estado real aparece nas saídas: não o presuma. Os endpoints ficam na mesma sub-rede e são criados um após o
// outro (dependsOn), para evitar alterações simultâneas nela, que a plataforma pode recusar.
resource endpointBlob 'Microsoft.Network/privateEndpoints@2026-01-01' = {
  name: nomeEndpointBlob
  location: localizacao
  tags: etiquetas
  properties: {
    subnet: {
      id: idSubredeEndpoints
    }
    privateLinkServiceConnections: [
      {
        name: 'conexao-blob'
        properties: {
          privateLinkServiceId: idConta
          groupIds: [
            'blob'
          ]
          requestMessage: mensagemSolicitacao
        }
      }
    ]
  }
}

resource zonasBlob 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2026-01-01' = {
  parent: endpointBlob
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'blob'
        properties: {
          privateDnsZoneId: idZonaBlob
        }
      }
    ]
  }
}

resource endpointBusca 'Microsoft.Network/privateEndpoints@2026-01-01' = {
  name: nomeEndpointBusca
  location: localizacao
  tags: etiquetas
  dependsOn: [
    endpointBlob
  ]
  properties: {
    subnet: {
      id: idSubredeEndpoints
    }
    privateLinkServiceConnections: [
      {
        name: 'conexao-busca'
        properties: {
          privateLinkServiceId: idBusca
          groupIds: [
            'searchService'
          ]
          requestMessage: mensagemSolicitacao
        }
      }
    ]
  }
}

resource zonasBusca 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2026-01-01' = {
  parent: endpointBusca
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'busca'
        properties: {
          privateDnsZoneId: idZonaBusca
        }
      }
    ]
  }
}

resource endpointModelos 'Microsoft.Network/privateEndpoints@2026-01-01' = {
  name: nomeEndpointModelos
  location: localizacao
  tags: etiquetas
  dependsOn: [
    endpointBusca
  ]
  properties: {
    subnet: {
      id: idSubredeEndpoints
    }
    privateLinkServiceConnections: [
      {
        name: 'conexao-modelos'
        properties: {
          privateLinkServiceId: idModelos
          groupIds: [
            'account'
          ]
          requestMessage: mensagemSolicitacao
        }
      }
    ]
  }
}

// Um recurso Foundry pode expor os três nomes públicos (cognitiveservices, openai e services.ai): cada um precisa da zona dele.
resource zonasModelos 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2026-01-01' = {
  parent: endpointModelos
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'cognitiveservices'
        properties: {
          privateDnsZoneId: idZonaCognitiveServices
        }
      }
      {
        name: 'openai'
        properties: {
          privateDnsZoneId: idZonaOpenAI
        }
      }
      {
        name: 'servicosia'
        properties: {
          privateDnsZoneId: idZonaServicosIA
        }
      }
    ]
  }
}

// Estado de cada conexão e endereços DNS previstos, sem segredos. Servem para conferir, de dentro da rede, o que a
// resolução de nomes deve devolver. O estado vem da lista automática ou, se a conexão exigir aprovação, da lista manual.
output endpoints array = [
  {
    nome: endpointBlob.name
    alvo: 'armazenamento'
    grupo: 'blob'
    estadoConexao: endpointBlob.properties.?privateLinkServiceConnections[?0].?properties.?privateLinkServiceConnectionState.?status ?? endpointBlob.properties.?manualPrivateLinkServiceConnections[?0].?properties.?privateLinkServiceConnectionState.?status ?? 'desconhecido'
    configuracoesDns: endpointBlob.properties.?customDnsConfigs ?? []
  }
  {
    nome: endpointBusca.name
    alvo: 'busca'
    grupo: 'searchService'
    estadoConexao: endpointBusca.properties.?privateLinkServiceConnections[?0].?properties.?privateLinkServiceConnectionState.?status ?? endpointBusca.properties.?manualPrivateLinkServiceConnections[?0].?properties.?privateLinkServiceConnectionState.?status ?? 'desconhecido'
    configuracoesDns: endpointBusca.properties.?customDnsConfigs ?? []
  }
  {
    nome: endpointModelos.name
    alvo: 'modelos'
    grupo: 'account'
    estadoConexao: endpointModelos.properties.?privateLinkServiceConnections[?0].?properties.?privateLinkServiceConnectionState.?status ?? endpointModelos.properties.?manualPrivateLinkServiceConnections[?0].?properties.?privateLinkServiceConnectionState.?status ?? 'desconhecido'
    configuracoesDns: endpointModelos.properties.?customDnsConfigs ?? []
  }
]
