metadata name = 'Vareleira RAG · L100 · Desafio 03 · Deployment de geração'
metadata description = 'Deployment de um modelo de geração de texto no recurso do Microsoft Foundry criado no Desafio 02. O recurso, as chaves desativadas e os papéis já existem: o papel Cognitive Services OpenAI User vale para todos os deployments do recurso.'

// Módulo chamado por main.bicep, que define os valores padrão e explica cada parâmetro.
targetScope = 'resourceGroup'

@description('Nome do recurso do Foundry criado no Desafio 02.')
param nomeModelos string

@description('Nome do modelo de geração.')
param modeloGeracao string

@description('Versão do modelo de geração.')
param versaoModeloGeracao string

@description('Nome do deployment de geração.')
param nomeDeploymentGeracao string

@description('Tipo de implantação do modelo.')
param skuDeploymentGeracao string

@description('Cota do deployment, em milhares de tokens por minuto.')
param capacidadeGeracao int

// O recurso de modelos pertence ao módulo do Desafio 02. Aqui ele só é referenciado.
resource modelos 'Microsoft.CognitiveServices/accounts@2026-07-01' existing = {
  name: nomeModelos
}

// A versão fica fixa (NoAutoUpgrade): o comportamento das respostas só muda quando você
// escolhe outra versão. O deployment deixa de funcionar na data de aposentadoria do modelo.
resource implantacaoGeracao 'Microsoft.CognitiveServices/accounts/deployments@2026-07-01' = {
  parent: modelos
  name: nomeDeploymentGeracao
  sku: {
    name: skuDeploymentGeracao
    capacity: capacidadeGeracao
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: modeloGeracao
      version: versaoModeloGeracao
    }
    versionUpgradeOption: 'NoAutoUpgrade'
  }
}

output nomeDeploymentGeracao string = implantacaoGeracao.name
output modeloGeracao string = implantacaoGeracao.properties.model.name
