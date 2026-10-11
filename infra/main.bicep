metadata name = 'Vareleira RAG · L100 · Desafios 01 a 03 e 07'
metadata description = 'Desafio 01: conta de armazenamento e contêiner de blobs para os documentos sintéticos do Vareleira Lar. Desafio 02 (opcional): serviço de busca e deployment de embeddings. Desafio 03 (opcional): deployment de geração. Desafio 07 (opcional): cofre de segredos e papéis de leitura para a identidade da aplicação. O acesso aos dados usa apenas Microsoft Entra ID.'

// Escopo: grupo de recursos. O grupo é criado antes (az group create) e deve ser exclusivo do laboratório.
targetScope = 'resourceGroup'

@description('Nome da conta de armazenamento: 3 a 24 caracteres, apenas letras minúsculas e números. O padrão é estável para o mesmo grupo de recursos, o que torna a reimplantação previsível.')
@minLength(3)
@maxLength(24)
param nomeConta string = 'stvlrag${uniqueString(resourceGroup().id)}'

@description('Nome do contêiner de blobs que guardará os documentos (letras minúsculas, números e hífens).')
@minLength(3)
@maxLength(63)
param nomeContainer string = 'base-documental'

@description('Região do Azure. Por padrão, a mesma do grupo de recursos.')
param localizacao string = resourceGroup().location

@description('Redundância do armazenamento. LRS é a opção mais barata e basta para um laboratório com dados sintéticos.')
@allowed([
  'Standard_LRS'
  'Standard_ZRS'
  'Standard_GRS'
])
param sku string = 'Standard_LRS'

@description('Dias em que blobs e contêineres excluídos ou sobrescritos podem ser recuperados (exclusão reversível).')
@minValue(1)
@maxValue(365)
param retencaoExclusaoDias int = 7

@description('ID de objeto, no Microsoft Entra ID, de quem enviará os documentos (Desafio 01) e, no Desafio 02, criará o índice, indexará e consultará. Se ficar vazio, nenhum papel é atribuído e um administrador precisa conceder o acesso a dados.')
param principalIdCarga string = ''

@description('Tipo da identidade informada em principalIdCarga.')
@allowed([
  'User'
  'Group'
  'ServicePrincipal'
])
param tipoPrincipalCarga string = 'User'

@description('Desafio 02: cria também o serviço de busca e o recurso de modelos. Com o valor padrão (falso), só o armazenamento do Desafio 01 é criado.')
param implantarIndexacao bool = false

@description('Desafio 02: nome do serviço de busca, de 2 a 60 caracteres (letras minúsculas, números e hífens). Forma o endereço público do serviço.')
@minLength(2)
@maxLength(60)
param nomeBusca string = 'srch-vlr-${uniqueString(resourceGroup().id)}'

@description('Desafio 02: nome do recurso do Foundry, de 2 a 64 caracteres (letras minúsculas, números e hífens). Também é o subdomínio do endereço, exigido para autenticar com Entra ID.')
@minLength(2)
@maxLength(64)
param nomeModelos string = 'ais-vlr-${uniqueString(resourceGroup().id)}'

@description('Desafio 02: região do serviço de busca. Por padrão, a do grupo de recursos; use outra se a do grupo estiver sem capacidade para novos serviços de busca.')
param localizacaoBusca string = localizacao

@description('Desafio 02: região do recurso de modelos. Por padrão, a do grupo de recursos; confira a disponibilidade do modelo e a cota na região escolhida.')
param localizacaoModelos string = localizacao

@description('Desafio 02: camada do serviço de busca. "basic" cobra por hora enquanto existir e é a base dos próximos níveis; "free" não custa, mas só existe um por assinatura e não atende a recursos de níveis posteriores.')
@allowed([
  'free'
  'basic'
  'standard'
])
param skuBusca string = 'basic'

@description('Desafio 02: modelo de embeddings. Os vetores dos documentos e os das perguntas precisam vir do mesmo modelo e da mesma versão.')
param modeloEmbeddings string = 'text-embedding-3-small'

@description('Desafio 02: versão do modelo de embeddings. Fica fixa: uma troca automática de versão tornaria o índice incompatível.')
param versaoModeloEmbeddings string = '1'

@description('Desafio 02: nome do deployment de embeddings. É ele, e não o nome do modelo, que os scripts informam ao serviço.')
@minLength(2)
@maxLength(64)
param nomeDeploymentEmbeddings string = 'embeddings'

@description('Desafio 02: tipo de implantação do modelo. GlobalStandard cobra por uso e existe nas regiões testadas.')
@allowed([
  'GlobalStandard'
  'Standard'
  'DataZoneStandard'
])
param skuDeploymentEmbeddings string = 'GlobalStandard'

@description('Desafio 02: cota do deployment, em milhares de tokens por minuto. Reserva capacidade, não gera custo por si só; reduza se a sua cota regional for menor.')
@minValue(1)
@maxValue(1000)
param capacidadeEmbeddings int = 30

@description('Desafio 03: cria também o deployment de geração no recurso de modelos do Desafio 02. Só tem efeito junto com implantarIndexacao.')
param implantarGeracao bool = false

@description('Desafio 03: modelo de geração. O catálogo muda: confira a disponibilidade, a data de aposentadoria e a cota do modelo na região antes de trocá-lo.')
param modeloGeracao string = 'gpt-5.4-mini'

@description('Desafio 03: versão do modelo de geração. Fica fixa: o comportamento das respostas só muda quando você escolhe outra versão.')
param versaoModeloGeracao string = '2026-03-17'

@description('Desafio 03: nome do deployment de geração. É ele, e não o nome do modelo, que os scripts informam ao serviço.')
@minLength(2)
@maxLength(64)
param nomeDeploymentGeracao string = 'geracao'

@description('Desafio 03: tipo de implantação do modelo de geração. GlobalStandard cobra por uso e existe nas regiões testadas.')
@allowed([
  'GlobalStandard'
  'Standard'
  'DataZoneStandard'
])
param skuDeploymentGeracao string = 'GlobalStandard'

@description('Desafio 03: cota do deployment de geração, em milhares de tokens por minuto. Reserva capacidade, não gera custo por si só; reduza se a sua cota regional for menor.')
@minValue(1)
@maxValue(1000)
param capacidadeGeracao int = 50

@description('Desafio 07: cria também o Azure Key Vault para guardar o segredo da identidade da aplicação.')
param implantarCofre bool = false

@description('Desafio 07: nome do cofre, de 3 a 24 caracteres (letras, números e hífens, começando por letra). Forma o endereço do cofre e é único no Azure.')
@minLength(3)
@maxLength(24)
param nomeCofre string = 'kv-vlr-${uniqueString(resourceGroup().id)}'

@description('Desafio 07: dias em que um cofre ou um segredo excluído pode ser recuperado. O mínimo do Azure é 7; o nome de um cofre excluído fica reservado durante esse período, a menos que ele seja expurgado.')
@minValue(7)
@maxValue(90)
param retencaoCofreDias int = 7

@description('Desafio 07: liga a proteção contra expurgo do cofre. O padrão é ligada, e ela não pode ser desfeita depois: o cofre excluído passa a reservar o nome durante toda a retenção e não pode ser expurgado antes do fim dela. O arquivo de parâmetros do laboratório a desliga, de propósito, para que a limpeza seja completa; em produção, mantenha-a ligada.')
param protecaoCofreContraExpurgo bool = true

@description('Desafio 07: ID de objeto, no Microsoft Entra ID, do service principal da aplicação. Se ficar vazio, nenhum papel é atribuído à aplicação. Só tem efeito junto com implantarIndexacao.')
param principalIdAplicacao string = ''

@description('Etiquetas adicionais, combinadas com as do laboratório. Não inclua dados pessoais.')
param etiquetasAdicionais object = {}

var etiquetas = union(
  {
    laboratorio: 'vareleira-rag'
    nivel: 'L100'
    desafio: '01'
    dados: 'sinteticos'
  },
  etiquetasAdicionais
)

// Papel interno "Storage Blob Data Contributor": ler, gravar e excluir blobs, sem gerenciar a conta.
var papelStorageBlobDataContributor = 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'

// Segurança: quem tem permissão de criar a conta não ganha, por isso, acesso aos documentos.
// Chaves de conta e acesso anônimo ficam desativados; o acesso a dados usa Microsoft Entra ID.
// O endereço continua público (autenticado). Endpoints privados ficam para outro nível.
resource conta 'Microsoft.Storage/storageAccounts@2026-06-01' = {
  name: nomeConta
  location: localizacao
  tags: etiquetas
  sku: {
    name: sku
  }
  kind: 'StorageV2'
  properties: {
    accessTier: 'Hot'
    allowBlobPublicAccess: false
    allowSharedKeyAccess: false
    allowCrossTenantReplication: false
    defaultToOAuthAuthentication: true
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    publicNetworkAccess: 'Enabled'
  }
}

// A exclusão reversível também preserva a versão anterior quando um blob é sobrescrito.
resource servicoBlob 'Microsoft.Storage/storageAccounts/blobServices@2026-06-01' = {
  parent: conta
  name: 'default'
  properties: {
    deleteRetentionPolicy: {
      enabled: true
      days: retencaoExclusaoDias
    }
    containerDeleteRetentionPolicy: {
      enabled: true
      days: retencaoExclusaoDias
    }
  }
}

resource containerDocumentos 'Microsoft.Storage/storageAccounts/blobServices/containers@2026-06-01' = {
  parent: servicoBlob
  name: nomeContainer
  properties: {
    publicAccess: 'None'
  }
}

// Menor escopo possível: o papel vale somente para este contêiner. Exige que quem implanta
// possa criar atribuições de papel (por exemplo, Owner ou User Access Administrator).
resource atribuicaoCarga 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(principalIdCarga)) {
  name: guid(containerDocumentos.id, principalIdCarga, papelStorageBlobDataContributor)
  scope: containerDocumentos
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', papelStorageBlobDataContributor)
    principalId: principalIdCarga
    principalType: tipoPrincipalCarga
  }
}

output nomeConta string = conta.name
output nomeContainer string = containerDocumentos.name
output enderecoBlob string = conta.properties.primaryEndpoints.blob
output papelDeDadosAtribuido bool = !empty(principalIdCarga)

// Desafio 02: o serviço de busca e o recurso de modelos ficam em um módulo, criado só quando pedido.
module indexacao 'modules/indexacao.bicep' = if (implantarIndexacao) {
  name: 'indexacao'
  params: {
    nomeBusca: nomeBusca
    nomeModelos: nomeModelos
    localizacaoBusca: localizacaoBusca
    localizacaoModelos: localizacaoModelos
    skuBusca: skuBusca
    modeloEmbeddings: modeloEmbeddings
    versaoModeloEmbeddings: versaoModeloEmbeddings
    nomeDeploymentEmbeddings: nomeDeploymentEmbeddings
    skuDeploymentEmbeddings: skuDeploymentEmbeddings
    capacidadeEmbeddings: capacidadeEmbeddings
    principalId: principalIdCarga
    tipoPrincipal: tipoPrincipalCarga
    etiquetas: union(etiquetas, { desafio: '02' })
  }
}

// Vazios quando o Desafio 02 não foi implantado.
output nomeBusca string = indexacao.?outputs.nomeBusca ?? ''
output enderecoBusca string = indexacao.?outputs.enderecoBusca ?? ''
output nomeModelos string = indexacao.?outputs.nomeModelos ?? ''
output enderecoModelos string = indexacao.?outputs.enderecoModelos ?? ''
output nomeDeploymentEmbeddings string = indexacao.?outputs.nomeDeploymentEmbeddings ?? ''
output modeloEmbeddings string = indexacao.?outputs.modeloEmbeddings ?? ''
output papeisDeDadosIndexacaoAtribuidos bool = implantarIndexacao && !empty(principalIdCarga)

// Desafio 03: o deployment de geração fica em outro módulo, criado só quando pedido e depois do
// módulo do Desafio 02. A dependência serializa as operações no mesmo recurso de modelos, que
// recusa alterações simultâneas nos deployments.
module geracao 'modules/geracao.bicep' = if (implantarIndexacao && implantarGeracao) {
  name: 'geracao'
  dependsOn: [
    indexacao
  ]
  params: {
    nomeModelos: nomeModelos
    modeloGeracao: modeloGeracao
    versaoModeloGeracao: versaoModeloGeracao
    nomeDeploymentGeracao: nomeDeploymentGeracao
    skuDeploymentGeracao: skuDeploymentGeracao
    capacidadeGeracao: capacidadeGeracao
  }
}

// Vazios quando o Desafio 03 não foi implantado.
output nomeDeploymentGeracao string = geracao.?outputs.nomeDeploymentGeracao ?? ''
output modeloGeracao string = geracao.?outputs.modeloGeracao ?? ''

// Desafio 07: o cofre de segredos fica em um módulo, criado só quando pedido. Quem opera o laboratório
// (principalIdCarga) recebe o papel de guardar e ler segredos neste cofre, e só nele.
module cofre 'modules/cofre.bicep' = if (implantarCofre) {
  name: 'cofre'
  params: {
    nomeCofre: nomeCofre
    localizacao: localizacao
    retencaoExclusaoDias: retencaoCofreDias
    protecaoContraExpurgo: protecaoCofreContraExpurgo
    principalId: principalIdCarga
    tipoPrincipal: tipoPrincipalCarga
    etiquetas: union(etiquetas, { desafio: '07' })
  }
}

// Desafio 07: a aplicação recebe só papéis de leitura (consultar o índice e usar os modelos). Fica depois
// do módulo do Desafio 02, que cria os dois recursos.
module aplicacao 'modules/aplicacao.bicep' = if (implantarIndexacao && !empty(principalIdAplicacao)) {
  name: 'aplicacao'
  dependsOn: [
    indexacao
  ]
  params: {
    nomeBusca: nomeBusca
    nomeModelos: nomeModelos
    principalIdAplicacao: principalIdAplicacao
  }
}

// Vazios quando o Desafio 07 não foi implantado.
output nomeCofre string = cofre.?outputs.nomeCofre ?? ''
output enderecoCofre string = cofre.?outputs.enderecoCofre ?? ''
output papelDeSegredosAtribuido bool = cofre.?outputs.papelDeSegredosAtribuido ?? false
output papeisDaAplicacaoAtribuidos bool = implantarIndexacao && !empty(principalIdAplicacao)
