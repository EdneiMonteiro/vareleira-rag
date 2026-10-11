metadata name = 'Vareleira RAG · L300 · Rede privada, aplicação e isolamento'
metadata description = 'Reaproveita o armazenamento, a busca, os modelos, o registro de imagens, a identidade da aplicação e o workspace de logs do L100 e do L200 e prepara a topologia privada do L300 em três fases, escolhidas pelo parâmetro fase. rede: rede virtual, endpoints privados, zonas DNS, contêiner base-documental-l300, conexões compartilhadas da busca (pendentes de aprovação) e novo ambiente do Azure Container Apps integrado à rede, sem fechar nenhum acesso público. aplicacao: aplicação do L300 no novo ambiente, com ingresso fechado e login do Microsoft Entra ID. isolar: fecha o acesso público dos serviços de dados, só com a conectividade privada validada. O ambiente e a aplicação do L200 não são alterados.'

// Escopo: o mesmo grupo de recursos do L100 e do L200. Cada fase declara só os recursos dela; os recursos das fases
// anteriores entram como existentes. Implante sempre no modo incremental (o padrão do `az deployment group create`):
// o modo completo removeria recursos que este arquivo não declara.
targetScope = 'resourceGroup'

// ---- Fase e portões ----

@description('Fase da implantação. "rede" (padrão): cria rede, endpoints privados, zonas DNS, contêiner, conexões compartilhadas da busca e o ambiente do Container Apps, sem alterar o acesso público de nenhum serviço. "aplicacao": cria a aplicação do L300 no ambiente da fase anterior. "isolar": fecha o acesso público do armazenamento, da busca e dos modelos. Não pule a ordem: sem DNS, aprovações e ingestão privada funcionando, não feche o acesso público.')
@allowed([
  'rede'
  'aplicacao'
  'isolar'
])
param fase string = 'rede'

@description('Abre o ingresso externo da aplicação (endereço público, com login obrigatório). Falso (padrão): a aplicação nasce alcançável só de dentro do ambiente, recebe a autenticação e só então é aberta, depois de conferir o login e a autorização documental. Só tem efeito na fase aplicacao.')
param ingressoExterno bool = false

@description('Autorização explícita para fechar o acesso público dos serviços de dados. Falso (padrão): a fase isolar é recusada. Só use verdadeiro depois de demonstrar a consulta, a ingestão e a resolução de nomes pelo caminho privado, com autorização do responsável. É uma declaração de quem opera, não uma medição: o Bicep não confere a rede. Só tem efeito na fase isolar.')
param conectividadePrivadaValidada bool = false

// ---- Destinos que já existem (L100 e L200) ----
// Sem valor padrão, de propósito: um nome errado criaria outro recurso ou apontaria para o recurso errado.

@description('Nome da conta de armazenamento criada no L100 (saída nomeConta). O recurso já existe: o L300 só cria um contêiner nele.')
@minLength(3)
@maxLength(24)
param nomeConta string

@description('Nome do serviço de busca criado no L100 (saída nomeBusca), com a identidade gerenciada habilitada no L200. Camada Basic ou superior.')
@minLength(2)
@maxLength(60)
param nomeBusca string

@description('Nome do recurso de modelos (Foundry) criado no L100 (saída nomeModelos). Os deployments de embeddings e de geração do L100 continuam os mesmos.')
@minLength(2)
@maxLength(64)
param nomeModelos string

@description('Nome do registro de imagens do L200 (saída nomeRegistro). Camada Basic, endereço público autenticado: não é privatizado no L300.')
@minLength(5)
@maxLength(50)
param nomeRegistro string

@description('Nome da identidade gerenciada atribuída ao usuário criada no L200 (saída nomeIdentidadeAplicacao). A aplicação do L300 a reutiliza com os papéis que o L200 já atribuiu: o L300 não atribui papéis a ela.')
@minLength(3)
@maxLength(128)
param nomeIdentidadeAplicacao string

@description('Nome do workspace do Log Analytics criado no L200 (saída nomeWorkspaceLogs). Recebe os logs do novo ambiente.')
@minLength(4)
@maxLength(63)
param nomeWorkspaceLogs string

@description('ID de objeto, no Microsoft Entra ID, de quem envia os documentos ao contêiner do L300. Recebe o papel de gravação de blobs só nesse contêiner. Obrigatório.')
@minLength(36)
@maxLength(36)
param principalIdCarga string

@description('Tipo da identidade informada em principalIdCarga.')
@allowed([
  'User'
  'Group'
  'ServicePrincipal'
])
param tipoPrincipalCarga string = 'User'

// ---- Recursos novos do L300 ----

@description('Região dos recursos novos do L300 (rede, endpoints, ambiente e aplicação). Por padrão, a do grupo de recursos.')
param localizacao string = resourceGroup().location

@description('Nome do contêiner de blobs do L300, criado neste nível na conta de armazenamento do L100. O contêiner do L100 continua intacto.')
@minLength(3)
@maxLength(63)
param nomeContainer string = 'base-documental-l300'

@description('Nome da rede virtual do L300. O padrão é estável para o mesmo grupo de recursos e leva o prefixo l300.')
@minLength(2)
@maxLength(64)
param nomeRede string = 'vnet-vlr-l300-${uniqueString(resourceGroup().id)}'

@description('Espaço de endereços da rede virtual, em CIDR. Escolha um espaço que não se sobreponha a redes que serão conectadas à do L300 nem aos intervalos que o ambiente do Container Apps reserva (169.254.0.0/16, 172.30.0.0/16, 172.31.0.0/16, 192.0.2.0/24 e, no ambiente com perfis de carga, 100.100.0.0/17, 100.100.128.0/19, 100.100.160.0/19 e 100.100.192.0/19).')
param espacoEnderecosRede string = '10.30.0.0/24'

@description('Prefixo CIDR da sub-rede do ambiente do Container Apps: /27 ou maior (no máximo 27 bits de prefixo), dedicada ao ambiente. O ambiente com perfis de carga exige a sub-rede delegada a Microsoft.App/environments, e nem a sub-rede, nem o tamanho dela, nem o tipo de rede mudam depois que o ambiente existe. O padrão (/26) deixa 50 endereços úteis, contra 18 de uma /27.')
param prefixoSubredeAmbiente string = '10.30.0.0/26'

@description('Prefixo CIDR da sub-rede dos endpoints privados (no máximo 28 bits de prefixo). Precisa caber no espaço de endereços sem se sobrepor à sub-rede do ambiente.')
param prefixoSubredeEndpoints string = '10.30.0.64/27'

@description('Grupo (subrecurso) da conexão compartilhada da busca com o recurso de modelos. openai_account (padrão) é o grupo documentado para modelos de embeddings do Azure OpenAI na vetorização integrada. foundry_account é o grupo documentado para habilidades com modelos hospedados em recurso Foundry, e a documentação da camada Basic restringe conexões privadas com recurso Foundry. Troque só se a criação com o padrão for recusada, e confira a documentação atual.')
@allowed([
  'openai_account'
  'foundry_account'
])
param grupoLinkModelos string = 'openai_account'

@description('Nome do ambiente do Azure Container Apps do L300 (perfil Consumption, integrado à rede virtual). Novo e separado do ambiente do L200, porque a integração com a rede só é definida na criação do ambiente.')
@minLength(2)
@maxLength(32)
param nomeAmbiente string = 'cae-vlr-l300-${uniqueString(resourceGroup().id)}'

@description('Nome da aplicação do L300, de 2 a 32 caracteres (letras minúsculas, números e hífens). Separado da aplicação do L200, que continua existindo até a conferência da nova. Forma o endereço da aplicação.')
@minLength(2)
@maxLength(32)
param nomeAplicacao string = 'ca-vlr-l300-${uniqueString(resourceGroup().id)}'

@description('Etiquetas adicionais para os recursos criados pelo L300, combinadas com as do laboratório. Não inclua dados pessoais.')
param etiquetasAdicionais object = {}

// ---- Aplicação (fase aplicacao) ----

@description('Nome do repositório da imagem no registro. A imagem completa é <servidor do registro>/<repositorio>:<tag>.')
param repositorioImagem string = 'vareleira-chat'

@description('Tag da imagem publicada no registro antes da fase aplicacao (o Bicep não constrói imagens). Use uma tag imutável. Obrigatória na fase aplicacao: o módulo da aplicação recusa valor vazio.')
param tagImagem string = ''

@description('ID do aplicativo (cliente) do registro de aplicativo do chat no Microsoft Entra ID, criado fora do Bicep, com o endereço de retorno da saída urlRetornoLogin. Obrigatório na fase aplicacao; não é segredo, mas não o fixe no repositório. Os papéis de aplicação Vareleira.Atendimento e Vareleira.Corretor também são definidos fora do Bicep.')
@maxLength(36)
param idAplicacaoLogin string = ''

@description('ID do tenant do Microsoft Entra ID do registro de aplicativo. Obrigatório na fase aplicacao; o login continua aceitando só pessoas desse tenant, e a aplicação ainda exige os papéis do L300 para liberar os documentos.')
@maxLength(36)
param tenantLogin string = ''

@description('Segredo de cliente do registro de aplicativo, necessário ao fluxo de login. Obrigatório na fase aplicacao. Entra por variável de ambiente, nunca pelo arquivo de parâmetros nem pelo histórico.')
@secure()
param segredoLogin string = ''

@description('O que a plataforma faz com quem chega sem login: "Return401" responde 401; "RedirectToLoginPage" envia o navegador à página de login do Microsoft Entra ID. A autenticação é obrigatória nos dois casos.')
@allowed([
  'Return401'
  'RedirectToLoginPage'
])
param acaoSemLogin string = 'Return401'

@description('Nome do índice que a aplicação do L300 consulta e o ingestor do L300 cria, diferente dos índices do L100 e do L200.')
@minLength(2)
@maxLength(128)
param nomeIndice string = 'vareleira-lar-l300'

@description('Nome do deployment de embeddings do L100, o mesmo do L200: o L300 não cria deployments nem troca versões de modelo.')
param nomeDeploymentEmbeddings string = 'embeddings'

@description('Nome do deployment de geração do L100, o mesmo do L200.')
param nomeDeploymentGeracao string = 'geracao'

@description('Dimensões dos vetores do índice, iguais às do modelo de embeddings (1536 para o text-embedding-3-small).')
@minValue(1)
@maxValue(3072)
param dimensoes int = 1536

@description('Modo de busca da aplicação: vetorial, texto ou hibrida. O padrão é o do L200.')
@allowed([
  'vetorial'
  'texto'
  'hibrida'
])
param modoBusca string = 'hibrida'

@description('Quantidade de trechos recuperados por pergunta. O padrão é o do L200.')
@minValue(1)
@maxValue(10)
param quantidadeTrechos int = 3

@description('Esforço de raciocínio do modelo de geração. O padrão é o do L200.')
@allowed([
  'none'
  'low'
  'medium'
  'high'
])
param esforco string = 'low'

// ---- Configuração atual dos serviços existentes (só na fase isolar) ----
// O ARM reaplica o recurso inteiro (PUT): o que for omitido volta ao padrão da API. Por isso a fase isolar repete a
// configuração completa do L100 e do L200 e exige estes valores, sem palpite: vazios ou zerados, o módulo de isolamento
// recusa a implantação antes de alterar qualquer serviço. Nas outras fases eles não são usados.

@description('Região real da conta de armazenamento. Vazio: a região dos recursos do L300. Informe a região real se a conta do L100 não estiver nela.')
param localizacaoArmazenamento string = ''

@description('Região real do serviço de busca. Vazio: a região dos recursos do L300. Precisa ser a região real, porque o ARM não move recursos.')
param localizacaoBusca string = ''

@description('Região real do recurso de modelos. Vazio: a região dos recursos do L300.')
param localizacaoModelos string = ''

@description('Redundância atual da conta de armazenamento (Standard_LRS, Standard_ZRS ou Standard_GRS). Obrigatória na fase isolar. Sem valor padrão, de propósito: o L100 usa Standard_LRS por padrão, mas o que vale é o que a conta tem hoje.')
param skuArmazenamento string = ''

@description('Camada atual do serviço de busca (basic ou standard). Obrigatória na fase isolar. Sem valor padrão, de propósito: uma camada diferente da atual não é aceita.')
param skuBusca string = ''

@description('Réplicas atuais do serviço de busca. Obrigatório na fase isolar (de 1 a 12); zero significa não informado.')
param replicasBusca int = 0

@description('Partições atuais do serviço de busca (1, 2, 3, 4, 6 ou 12). Obrigatório na fase isolar; zero significa não informado.')
param particoesBusca int = 0

@description('Etiquetas atuais da conta de armazenamento. O padrão repete as do L100 (Desafio 01). Se o L100 usou etiquetasAdicionais, repita-as aqui, porque o ARM substitui as etiquetas.')
param etiquetasArmazenamento object = {
  laboratorio: 'vareleira-rag'
  nivel: 'L100'
  desafio: '01'
  dados: 'sinteticos'
}

@description('Etiquetas atuais do serviço de busca. O padrão repete as do L100 (Desafio 02), as mesmas do L200.')
param etiquetasBusca object = {
  laboratorio: 'vareleira-rag'
  nivel: 'L100'
  desafio: '02'
  dados: 'sinteticos'
}

@description('Etiquetas atuais do recurso de modelos. O padrão repete as do L100 (Desafio 02).')
param etiquetasModelos object = {
  laboratorio: 'vareleira-rag'
  nivel: 'L100'
  desafio: '02'
  dados: 'sinteticos'
}

var etiquetas = union(
  {
    laboratorio: 'vareleira-rag'
    nivel: 'L300'
    dados: 'sinteticos'
  },
  etiquetasAdicionais
)

var nomeSubredeAmbiente = 'snet-ambiente-l300'
var nomeSubredeEndpoints = 'snet-endpoints-l300'
var nomeEndpointBlob = 'pe-blob-vlr-l300'
var nomeEndpointBusca = 'pe-busca-vlr-l300'
var nomeEndpointModelos = 'pe-modelos-vlr-l300'
var nomeLinkBlob = 'spl-blob-vlr-l300'
var nomeLinkModelos = 'spl-modelos-vlr-l300'

var regiaoArmazenamento = empty(localizacaoArmazenamento) ? localizacao : localizacaoArmazenamento
var regiaoBusca = empty(localizacaoBusca) ? localizacao : localizacaoBusca
var regiaoModelos = empty(localizacaoModelos) ? localizacao : localizacaoModelos

// Recursos que já existem. Aqui eles só são referenciados: nenhuma fase os redeclara, exceto o módulo de isolamento.
resource conta 'Microsoft.Storage/storageAccounts@2026-06-01' existing = {
  name: nomeConta
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

resource identidadeAplicacao 'Microsoft.ManagedIdentity/userAssignedIdentities@2024-11-30' existing = {
  name: nomeIdentidadeAplicacao
}

resource ambienteExistente 'Microsoft.App/managedEnvironments@2026-07-01' existing = {
  name: nomeAmbiente
}

// Conexões compartilhadas criadas na fase rede: a fase isolar lê o estado delas.
resource linkBlobAtual 'Microsoft.Search/searchServices/sharedPrivateLinkResources@2025-05-01' existing = {
  parent: busca
  name: nomeLinkBlob
}

resource linkModelosAtual 'Microsoft.Search/searchServices/sharedPrivateLinkResources@2025-05-01' existing = {
  parent: busca
  name: nomeLinkModelos
}

// Leituras do estado atual dos recursos existentes. Cada uma só é feita na fase que a usa: a função if do ARM avalia só o
// ramo escolhido. Assim, a fase rede não depende de conexões compartilhadas que ela mesma ainda vai criar, e a fase isolar
// compara o que foi informado com o que existe.
var estadoLinkArmazenamento = fase == 'isolar' ? linkBlobAtual.properties.status : ''
var estadoLinkModelos = fase == 'isolar' ? linkModelosAtual.properties.status : ''
var configuracaoBuscaConfere = fase == 'isolar'
  ? (busca.sku.name == skuBusca && busca.properties.replicaCount == replicasBusca && busca.properties.partitionCount == particoesBusca)
  : false
var configuracaoArmazenamentoConfere = fase == 'isolar' ? conta.sku.name == skuArmazenamento : false
var servidorRegistro = fase == 'aplicacao' ? registro.properties.loginServer : ''
var clientIdIdentidade = fase == 'aplicacao' ? identidadeAplicacao.properties.clientId : ''

// ---- Fase rede ----
// Cria o que o L300 precisa para os caminhos privados e não fecha nada: o acesso público dos serviços de dados continua
// como está, e a aplicação do L200 segue funcionando.

module rede 'modules/l300-rede.bicep' = if (fase == 'rede') {
  name: 'l300-rede'
  params: {
    nomeRede: nomeRede
    localizacao: localizacao
    etiquetas: etiquetas
    espacoEnderecos: espacoEnderecosRede
    nomeSubredeAmbiente: nomeSubredeAmbiente
    prefixoSubredeAmbiente: prefixoSubredeAmbiente
    bitsPrefixoSubredeAmbiente: int(split(prefixoSubredeAmbiente, '/')[1])
    nomeSubredeEndpoints: nomeSubredeEndpoints
    prefixoSubredeEndpoints: prefixoSubredeEndpoints
    bitsPrefixoSubredeEndpoints: int(split(prefixoSubredeEndpoints, '/')[1])
  }
}

module endpoints 'modules/l300-endpoints.bicep' = if (fase == 'rede') {
  name: 'l300-endpoints'
  params: {
    localizacao: localizacao
    etiquetas: etiquetas
    idSubredeEndpoints: rede!.outputs.idSubredeEndpoints
    idZonaBlob: rede!.outputs.idZonaBlob
    idZonaBusca: rede!.outputs.idZonaBusca
    idZonaCognitiveServices: rede!.outputs.idZonaCognitiveServices
    idZonaOpenAI: rede!.outputs.idZonaOpenAI
    idZonaServicosIA: rede!.outputs.idZonaServicosIA
    idConta: conta.id
    idBusca: busca.id
    idModelos: modelos.id
    nomeEndpointBlob: nomeEndpointBlob
    nomeEndpointBusca: nomeEndpointBusca
    nomeEndpointModelos: nomeEndpointModelos
  }
}

// O ID de objeto da busca é lido do próprio serviço: sem a identidade habilitada no L200, o módulo recusa a implantação.
// As operações na rede, no armazenamento e na busca ficam em fila (dependsOn), para evitar alterações simultâneas no mesmo
// recurso, que os serviços podem recusar.
module fonteDocumental 'modules/l300-fonte-documental.bicep' = if (fase == 'rede') {
  name: 'l300-fonte-documental'
  dependsOn: [
    endpoints
  ]
  params: {
    nomeConta: nomeConta
    nomeContainer: nomeContainer
    principalIdBusca: busca.?identity.principalId ?? ''
    principalIdCarga: principalIdCarga
    tipoPrincipalCarga: tipoPrincipalCarga
  }
}

module ingestaoPrivada 'modules/l300-ingestao-privada.bicep' = if (fase == 'rede') {
  name: 'l300-ingestao-privada'
  dependsOn: [
    endpoints
    fonteDocumental
  ]
  params: {
    nomeBusca: nomeBusca
    idConta: conta.id
    idModelos: modelos.id
    nomeLinkBlob: nomeLinkBlob
    nomeLinkModelos: nomeLinkModelos
    grupoLinkModelos: grupoLinkModelos
  }
}

module ambiente 'modules/l300-ambiente.bicep' = if (fase == 'rede') {
  name: 'l300-ambiente'
  dependsOn: [
    endpoints
  ]
  params: {
    nomeAmbiente: nomeAmbiente
    localizacao: localizacao
    etiquetas: etiquetas
    idSubredeAmbiente: rede!.outputs.idSubredeAmbiente
    nomeWorkspaceLogs: nomeWorkspaceLogs
  }
}

// ---- Fase aplicacao ----
// Reutiliza o módulo da aplicação do L200 no ambiente novo. A identidade é a do L200, com os papéis que ela já tem (baixar
// imagens, consultar o índice e usar os modelos): esta fase não atribui papéis. A aplicação nasce com o ingresso fechado,
// a menos que ingressoExterno seja verdadeiro, e a autenticação é criada junto com ela.

module aplicacao 'modules/l200-aplicacao.bicep' = if (fase == 'aplicacao') {
  name: 'l300-aplicacao'
  params: {
    nomeAplicacao: nomeAplicacao
    localizacao: localizacao
    etiquetas: etiquetas
    idAmbiente: ambienteExistente.id
    servidorRegistro: servidorRegistro
    idIdentidade: identidadeAplicacao.id
    clientIdIdentidade: clientIdIdentidade
    repositorioImagem: repositorioImagem
    tagImagem: tagImagem
    ingressoExterno: ingressoExterno
    idAplicacaoLogin: idAplicacaoLogin
    tenantLogin: tenantLogin
    segredoLogin: segredoLogin
    acaoSemLogin: acaoSemLogin
    nomeBusca: nomeBusca
    nomeModelos: nomeModelos
    nomeIndice: nomeIndice
    nomeDeploymentEmbeddings: nomeDeploymentEmbeddings
    nomeDeploymentGeracao: nomeDeploymentGeracao
    dimensoes: dimensoes
    modoBusca: modoBusca
    quantidadeTrechos: quantidadeTrechos
    esforco: esforco
    exigirAcessoDocumental: true
  }
}

// ---- Fase isolar ----
// Único ponto que fecha o acesso público. As guardas do módulo (parâmetros com um único valor permitido) fazem o ARM
// recusar a fase, antes de alterar qualquer serviço, se: a conectividade privada não foi declarada validada; alguma
// conexão compartilhada da busca não está Approved; ou a camada, as réplicas, as partições ou a redundância informadas
// diferem das atuais. Fora da fase isolar, nenhuma dessas leituras é feita.

module isolamento 'modules/l300-isolamento.bicep' = if (fase == 'isolar') {
  name: 'l300-isolamento'
  params: {
    conectividadePrivadaValidada: conectividadePrivadaValidada
    estadoLinkArmazenamento: estadoLinkArmazenamento
    estadoLinkModelos: estadoLinkModelos
    configuracaoBuscaConfere: configuracaoBuscaConfere
    configuracaoArmazenamentoConfere: configuracaoArmazenamentoConfere
    nomeConta: nomeConta
    localizacaoArmazenamento: regiaoArmazenamento
    skuArmazenamento: skuArmazenamento
    etiquetasArmazenamento: etiquetasArmazenamento
    nomeBusca: nomeBusca
    localizacaoBusca: regiaoBusca
    skuBusca: skuBusca
    replicasBusca: replicasBusca
    particoesBusca: particoesBusca
    etiquetasBusca: etiquetasBusca
    nomeModelos: nomeModelos
    localizacaoModelos: regiaoModelos
    etiquetasModelos: etiquetasModelos
  }
}

// ---- Saídas (sem segredos) ----
// Vazias quando a fase correspondente não foi executada.

var dominioAmbiente = ambiente.?outputs.dominioPadrao ?? ''

output fase string = fase
output nomeRede string = fase == 'rede' ? nomeRede : ''
output nomeAmbiente string = ambiente.?outputs.nome ?? ''
output dominioAmbiente string = dominioAmbiente
output grupoRecursosGerenciado string = ambiente.?outputs.grupoRecursosGerenciado ?? ''
output nomeContainer string = fonteDocumental.?outputs.nomeContainer ?? ''
output papeisAtribuidos int = fonteDocumental.?outputs.papeisAtribuidos ?? 0
output endpointsPrivados array = endpoints.?outputs.endpoints ?? []
output linksCompartilhados array = ingestaoPrivada.?outputs.links ?? []
output nomeIndice string = nomeIndice

// Informe este endereço de retorno no registro de aplicativo antes da fase aplicacao. O endereço da aplicação é
// <nome>.<domínio do ambiente>. Na fase aplicacao, o domínio é lido do ambiente já existente.
output urlRetornoLogin string = fase == 'rede'
  ? 'https://${nomeAplicacao}.${dominioAmbiente}/.auth/login/aad/callback'
  : (fase == 'aplicacao'
      ? 'https://${nomeAplicacao}.${ambienteExistente.properties.defaultDomain}/.auth/login/aad/callback'
      : '')
output idAplicacaoLogin string = fase == 'aplicacao' ? idAplicacaoLogin : ''

output nomeAplicacao string = aplicacao.?outputs.nome ?? ''
output nomeRevisaoAtual string = aplicacao.?outputs.nomeRevisaoAtual ?? ''
output urlAplicacao string = fase == 'aplicacao' && ingressoExterno
  ? 'https://${aplicacao.?outputs.enderecoAplicacao ?? ''}'
  : ''

output acessoPublicoDados object = isolamento.?outputs.acessoPublico ?? {}

// Descritor para conferir a topologia depois da fase rede. A resolução de nomes feita de fora da rede devolve o endereço
// público e não prova o caminho privado: a conferência precisa ser feita de dentro da rede do L300 (por exemplo, no
// próprio ambiente), com a identidade prevista.
output descritorVerificacao object = {
  fase: fase
  aviso: 'A resolução de nomes feita fora da rede virtual do L300 devolve o endereço público e não prova o caminho privado. Confira de dentro da rede, com a identidade prevista. Depois de fechar o acesso público, a recusa fora da rede também precisa ser observada.'
  topologia: {
    ingressoDoChat: 'externo, HTTPS, com login do Microsoft Entra ID e papéis de aplicação exigidos pelo servidor'
    redeDoAmbiente: 'integrada à rede virtual do L300, tipo externo, definido na criação e imutável'
    registroDeImagens: 'camada Basic, endereço público autenticado pela identidade gerenciada; a saída à internet não é bloqueada'
    ambienteDoL200: 'preservado, sem rede virtual própria; deixa de alcançar os dados depois da fase isolar'
  }
  zonasDns: rede.?outputs.nomesZonas ?? []
  nomesParaResolver: [
    {
      servico: 'armazenamento (blob)'
      nome: '${nomeConta}.blob.${environment().suffixes.storage}'
      zona: 'privatelink.blob.${environment().suffixes.storage}'
    }
    {
      servico: 'busca'
      nome: '${nomeBusca}.search.windows.net'
      zona: 'privatelink.search.windows.net'
    }
    {
      servico: 'modelos (openai)'
      nome: '${nomeModelos}.openai.azure.com'
      zona: 'privatelink.openai.azure.com'
    }
    {
      servico: 'modelos (cognitiveservices)'
      nome: '${nomeModelos}.cognitiveservices.azure.com'
      zona: 'privatelink.cognitiveservices.azure.com'
    }
    {
      servico: 'modelos (services.ai)'
      nome: '${nomeModelos}.services.ai.azure.com'
      zona: 'privatelink.services.ai.azure.com'
    }
  ]
  subredes: rede.?outputs.subredes ?? {}
  gruposDeLinkCompartilhado: {
    armazenamento: 'blob'
    modelos: grupoLinkModelos
  }
  aprovacoesNecessarias: [
    'Aprovar, no armazenamento, a conexão pendente criada pela conexão compartilhada da busca (grupo blob).'
    'Aprovar, no recurso de modelos, a conexão pendente criada pela conexão compartilhada da busca.'
    'Conferir que as duas conexões compartilhadas da busca estão Approved e com provisionamento Succeeded.'
  ]
  condicoesAntesDeIsolar: [
    'Zonas DNS privadas vinculadas à rede do L300 e nomes dos serviços resolvendo para endereços privados, conferidos de dentro da rede.'
    'Conexões compartilhadas da busca aprovadas nos recursos de destino (estado Approved).'
    'Indexador do L300 criado com executionEnvironment = private e concluído sem falhas pelo caminho privado.'
    'Consulta do chat do L300 funcionando pelos endpoints privados, com as identidades previstas.'
    'Autorização explícita do responsável e plano de retorno definido. Sem DNS, ingestão e conexões compartilhadas prontos, não desabilite o acesso público.'
  ]
  requisitosDaBusca: [
    'Indexadores sem skillset: camada Basic ou superior, sem exigência de região nem de data de criação do serviço.'
    'Skillsets com habilidades de embedding (vetorização integrada): Basic ou superior, em regiões de alta capacidade e em serviços criados depois de 3 de abril de 2024. Indexadores com mais de duas habilidades de embedding não rodam no ambiente privado.'
    'Skillsets com outras habilidades internas ou personalizadas: S1 ou superior, em serviços criados depois de 3 de abril de 2024. Na camada Basic, a documentação não admite conexões privadas com recurso Foundry para skillsets.'
    'Não aumente a camada sem conferir a composição do skillset e o custo.'
  ]
  limites: [
    'O L300 não cria objetos do índice (índice, fonte de dados, skillset, indexador): o script de ingestão os cria, com executionEnvironment = private.'
    'Os papéis de aplicação Vareleira.Atendimento e Vareleira.Corretor e o registro do aplicativo são feitos no Microsoft Entra ID, fora do Bicep.'
    'A aprovação das conexões compartilhadas é feita nos recursos de destino, fora do Bicep.'
    'Depois da fase isolar, computadores e executores sem caminho na rede perdem o acesso aos dados, e a aplicação do L200 também.'
    'O grupo de recursos ME_ criado pela plataforma para o ambiente gera cobrança própria e não deve ser alterado nem excluído manualmente.'
  ]
}
