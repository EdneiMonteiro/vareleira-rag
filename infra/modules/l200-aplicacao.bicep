metadata name = 'Vareleira RAG · L200 · Aplicação do chat'
metadata description = 'Aplicação do chat em Azure Container Apps (plano Consumption): a imagem vem do registro do L200 pela identidade gerenciada atribuída ao usuário, que também consulta o índice e usa os modelos, sem chaves. O acesso exige autenticação integrada do Microsoft Entra ID, com um registro de aplicativo próprio.'

// Módulo chamado por l200.bicep, que define os valores padrão e explica cada parâmetro.
targetScope = 'resourceGroup'

@description('Nome da aplicação. Forma o endereço público dela.')
@minLength(2)
@maxLength(32)
param nomeAplicacao string

@description('Região da aplicação, a mesma do ambiente.')
param localizacao string

@description('Etiquetas aplicadas aos recursos criados por este módulo.')
param etiquetas object

@description('ID do recurso do ambiente de Container Apps.')
param idAmbiente string

@description('Endereço do registro de imagens (loginServer).')
param servidorRegistro string

@description('ID do recurso da identidade gerenciada atribuída ao usuário, que já recebeu os papéis de dados.')
param idIdentidade string

@description('ID do cliente da identidade gerenciada (não é segredo). A aplicação o usa para pedir tokens com essa identidade.')
param clientIdIdentidade string

@description('Nome do repositório da imagem no registro.')
param repositorioImagem string

// Guardas das entradas obrigatórias: com valores vazios ou curtos demais, o ARM recusa este módulo antes de criar a aplicação.
@description('Tag da imagem já publicada no registro. Use uma tag imutável (por exemplo, uma versão): com "latest", uma nova imagem não gera nova revisão.')
@minLength(1)
@maxLength(128)
param tagImagem string

@description('Abre o ingresso externo (endereço público, ainda com login obrigatório). Falso: a aplicação só é alcançável de dentro do ambiente.')
param ingressoExterno bool

@description('ID do aplicativo (cliente) do registro de aplicativo do Microsoft Entra ID que representa o chat.')
@minLength(36)
@maxLength(36)
param idAplicacaoLogin string

@description('ID do tenant do Microsoft Entra ID em que o registro de aplicativo existe. Só pessoas desse tenant entram.')
@minLength(36)
@maxLength(36)
param tenantLogin string

@description('Segredo de cliente do registro de aplicativo. Fica como segredo da aplicação, nunca como variável de ambiente.')
@secure()
@minLength(16)
param segredoLogin string

@description('O que a plataforma faz com quem chega sem login: responde 401 ou envia para a página de login do Microsoft Entra ID.')
@allowed([
  'Return401'
  'RedirectToLoginPage'
])
param acaoSemLogin string

@description('Nome do serviço de busca do L100.')
param nomeBusca string

@description('Nome do recurso de modelos (Foundry) do L100.')
param nomeModelos string

@description('Nome do índice que a aplicação consulta.')
param nomeIndice string

@description('Nome do deployment de embeddings.')
param nomeDeploymentEmbeddings string

@description('Nome do deployment de geração.')
param nomeDeploymentGeracao string

@description('Dimensões dos vetores do índice.')
param dimensoes int

@description('Modo de busca da aplicação: vetorial, texto ou hibrida.')
param modoBusca string

@description('Quantidade de trechos recuperados por pergunta.')
@minValue(1)
@maxValue(10)
param quantidadeTrechos int

@description('Esforço de raciocínio do modelo de geração.')
param esforco string

var portaAplicacao = 8000
var nomeSegredoLogin = 'login-entraid'

// Só valores que não são segredo, com os nomes que scripts/lab_chat.py lê. O segredo de login fica em `secrets` e só
// a autenticação integrada o lê. AZURE_CLIENT_ID é o ID do cliente da identidade atribuída ao usuário: sem ele, a
// aplicação pediria o token da identidade do sistema, que ela não tem.
var variaveisDeAmbiente = [
  { name: 'VARELEIRA_BUSCA', value: nomeBusca }
  { name: 'VARELEIRA_MODELOS', value: nomeModelos }
  { name: 'VARELEIRA_INDICE', value: nomeIndice }
  { name: 'VARELEIRA_DEPLOYMENT_EMBEDDINGS', value: nomeDeploymentEmbeddings }
  { name: 'VARELEIRA_DEPLOYMENT_GERACAO', value: nomeDeploymentGeracao }
  { name: 'VARELEIRA_DIMENSOES', value: string(dimensoes) }
  { name: 'VARELEIRA_MODO_BUSCA', value: modoBusca }
  { name: 'VARELEIRA_K', value: string(quantidadeTrechos) }
  { name: 'VARELEIRA_ESFORCO', value: esforco }
  { name: 'AZURE_CLIENT_ID', value: clientIdIdentidade }
  { name: 'VARELEIRA_EXIGIR_AUTENTICACAO', value: 'true' }
  { name: 'VARELEIRA_TENANT_AUTORIZADO', value: tenantLogin }
]

// Sem chaves de registro: a identidade atribuída ao usuário baixa a imagem (papel AcrPull, atribuído antes) e
// também acessa busca e modelos. Escala de 0 a 1 réplica: com zero réplicas, não há computação cobrada.
resource aplicacao 'Microsoft.App/containerApps@2026-07-01' = {
  name: nomeAplicacao
  location: localizacao
  tags: etiquetas
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${idIdentidade}': {}
    }
  }
  properties: {
    environmentId: idAmbiente
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: ingressoExterno
        targetPort: portaAplicacao
        allowInsecure: false
      }
      registries: [
        {
          server: servidorRegistro
          identity: idIdentidade
        }
      ]
      secrets: [
        {
          name: nomeSegredoLogin
          value: segredoLogin
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'chat'
          image: '${servidorRegistro}/${repositorioImagem}:${tagImagem}'
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: variaveisDeAmbiente
          // Limites da API: até 10 falhas e 240 s entre verificações. Até 100 s para a primeira resposta de /healthz.
          probes: [
            {
              type: 'Startup'
              httpGet: {
                path: '/healthz'
                port: portaAplicacao
              }
              periodSeconds: 10
              timeoutSeconds: 3
              failureThreshold: 10
            }
            {
              type: 'Liveness'
              httpGet: {
                path: '/healthz'
                port: portaAplicacao
              }
              periodSeconds: 30
              timeoutSeconds: 5
              failureThreshold: 3
            }
            {
              type: 'Readiness'
              httpGet: {
                path: '/readyz'
                port: portaAplicacao
              }
              periodSeconds: 10
              timeoutSeconds: 5
              failureThreshold: 3
            }
          ]
        }
      ]
      scale: {
        minReplicas: 0
        maxReplicas: 1
      }
    }
  }
}

// O ARM só cria a autenticação depois da aplicação. Por isso o ingresso externo é uma etapa separada de l200.bicep
// (ingressoExterno = falso na primeira implantação): a aplicação nasce alcançável só de dentro do ambiente, ganha a
// autenticação e só então é aberta. Quem chega sem login recebe a ação de acaoSemLogin; sem esta configuração,
// o endereço externo seria anônimo.
// Sem filtro de usuários: qualquer pessoa do tenant autenticada entra, a menos que o aplicativo empresarial do
// registro exija atribuição de usuários (configuração do Entra ID, fora do Bicep).
resource autenticacao 'Microsoft.App/containerApps/authConfigs@2026-07-01' = {
  parent: aplicacao
  name: 'current'
  properties: {
    platform: {
      enabled: true
    }
    globalValidation: {
      unauthenticatedClientAction: acaoSemLogin
      excludedPaths: [
        '/healthz'
        '/readyz'
      ]
    }
    identityProviders: {
      azureActiveDirectory: {
        enabled: true
        registration: {
          clientId: idAplicacaoLogin
          clientSecretSettingName: nomeSegredoLogin
          openIdIssuer: '${environment().authentication.loginEndpoint}${tenantLogin}/v2.0'
        }
        validation: {
          allowedAudiences: [
            idAplicacaoLogin
            'api://${idAplicacaoLogin}'
          ]
        }
      }
    }
    httpSettings: {
      requireHttps: true
    }
  }
}

output nome string = aplicacao.name
output enderecoAplicacao string = aplicacao.properties.configuration.ingress.fqdn
output nomeRevisaoAtual string = aplicacao.properties.latestRevisionName
