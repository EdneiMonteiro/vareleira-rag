metadata name = 'Vareleira RAG · L400 · Contingência de geração e aplicação com coordenação'
metadata description = 'Acrescenta ao L300, que já existe no grupo de recursos (rede privada, ambiente do Azure Container Apps, registro de imagens, identidade da aplicação, busca e modelos), dois recursos novos, em duas fases escolhidas pelo parâmetro fase. contingencia: um segundo deployment de geração (mesmo modelo e versão do principal, nome diferente) no recurso de modelos existente. aplicacao: uma aplicação do L400, separada da do L300, no ambiente existente, com login do Microsoft Entra ID, acesso documental e coordenação exigidos, ingresso fechado e o perfil de índice escolhido (referencia ou candidato). Nada do L100, do L200 e do L300 é redeclarado: os serviços de dados, os deployments e o ambiente entram como existentes, e o acesso público deles não é tocado.'

// Escopo: o mesmo grupo de recursos do L100 ao L300. Cada fase declara só os recursos dela. Implante sempre no modo
// incremental (o padrão do `az deployment group create`): o modo completo removeria recursos que este arquivo não declara.
//
// O que este arquivo NÃO faz: não redeclara o recurso de modelos, a busca nem o armazenamento (por isso nunca reabre o acesso
// público deles), não altera o deployment principal, não atribui papéis (a aplicação reutiliza a identidade do L300 e o papel
// de uso dos modelos já vale para todos os deployments do recurso), não cria Job, agenda, perfil dedicado, GPU nem capacidade
// provisionada, e não lê o índice de busca (que é do plano de dados): a existência e a compatibilidade do índice candidato são
// conferidas fora do Bicep.
targetScope = 'resourceGroup'

// ---- Fase e portões ----

@description('Fase da implantação. "contingencia" (padrão): declara só o deployment de geração de contingência no recurso de modelos existente. "aplicacao": cria a aplicação do L400 no ambiente do L300, depois da fase anterior. Cada fase declara só os recursos dela.')
@allowed([
  'contingencia'
  'aplicacao'
])
param fase string = 'contingencia'

@description('Abre o ingresso externo da aplicação (endereço público, com login obrigatório). Falso (padrão): a aplicação nasce alcançável só de dentro do ambiente, recebe a autenticação e só então é aberta, depois de conferir o login e a autorização documental. Só tem efeito na fase aplicacao.')
param ingressoExterno bool = false

@description('Perfil do índice que a aplicação consulta. "referencia" (padrão): o índice do L300, de 1536 dimensões, que este nível nunca altera. "candidato": o índice separado do L400, de 768 dimensões, só depois de reindexar e conferir a compatibilidade (scripts/operar_l400.py --etapa conferir-migracao). Escolher o perfil troca só a configuração da aplicação e não prova que os vetores são compatíveis; o retorno é a mesma troca ao contrário. Só tem efeito na fase aplicacao.')
@allowed([
  'referencia'
  'candidato'
])
param perfilIndice string = 'referencia'

// ---- Destinos que já existem (L100 ao L300) ----
// Sem valor padrão, de propósito: um nome errado apontaria para o recurso errado, e o ARM recusa nomes vazios.

@description('Nome do recurso de modelos (Foundry) criado no L100. O recurso já existe: o L400 só o referencia e acrescenta, na fase contingencia, um deployment filho. Os deployments principal e de embeddings são lidos, nunca alterados.')
@minLength(2)
@maxLength(64)
param nomeModelos string

@description('Nome do serviço de busca criado no L100. A aplicação do L400 o consulta pela identidade gerenciada, com o papel de leitura que o L200 já atribuiu.')
@minLength(2)
@maxLength(60)
param nomeBusca string

@description('Nome do registro de imagens do L200, de onde a aplicação baixa a imagem. Camada Basic, endereço público autenticado.')
@minLength(5)
@maxLength(50)
param nomeRegistro string

@description('Nome da identidade gerenciada atribuída ao usuário criada no L200, a mesma da aplicação do L300. A aplicação do L400 a reutiliza com os papéis que ela já tem: o L400 não atribui papéis.')
@minLength(3)
@maxLength(128)
param nomeIdentidadeAplicacao string

@description('Nome do ambiente do Azure Container Apps do L300 (saída nomeAmbiente do L300), integrado à rede virtual, que já existe. A aplicação do L400 entra nele, ao lado da do L300, que continua como referência.')
@minLength(2)
@maxLength(32)
param nomeAmbiente string

@description('Nome do deployment de embeddings que já existe (o mesmo do L100 ao L300). O L400 só o lê, para conferir se as dimensões do perfil de índice cabem no modelo.')
@minLength(2)
@maxLength(64)
param nomeDeploymentEmbeddings string = 'embeddings'

@description('Nome do deployment de geração principal que já existe (o mesmo do L100 ao L300). O L400 só o lê, para conferir modelo e versão da contingência: nunca o recria nem o altera.')
@minLength(2)
@maxLength(64)
param nomeDeploymentGeracao string = 'geracao'

// ---- Contingência (fase contingencia) ----

@description('Nome do deployment de geração de contingência. Precisa ser diferente do principal e do de embeddings: um nome igual atualizaria o deployment existente em vez de criar um novo (uma guarda recusa a implantação).')
@minLength(2)
@maxLength(64)
param nomeDeploymentContingencia string = 'geracao-contingencia'

@description('Modelo da contingência. Precisa ser o mesmo do deployment principal, que a guarda lê do recurso de modelos. Sem valor padrão, de propósito: o catálogo muda, e o modelo é uma escolha explícita de quem implanta.')
@minLength(1)
@maxLength(64)
param modeloContingencia string

@description('Versão do modelo da contingência. Precisa ser a mesma do deployment principal. Fica fixa (NoAutoUpgrade): uma troca automática de versão mudaria o comportamento só da contingência. Sem valor padrão, de propósito.')
@minLength(1)
@maxLength(32)
param versaoModeloContingencia string

@description('Tipo de implantação do deployment de contingência. Só os tipos que cobram por uso são aceitos: a capacidade provisionada (PTU) fica fora do laboratório.')
@allowed([
  'GlobalStandard'
  'Standard'
  'DataZoneStandard'
])
param skuContingencia string

@description('Cota do deployment de contingência, em milhares de tokens por minuto. Valor explícito, sem padrão: o L400 não infere cota nova pelo fato de existirem dois deployments. Cada deployment consome a cota regional da assinatura, e o Bicep não a consulta: confira a cota disponível antes de implantar.')
@minValue(1)
@maxValue(1000)
param capacidadeContingencia int

// ---- Recursos novos do L400 ----

@description('Região da aplicação. Por padrão, a do grupo de recursos.')
param localizacao string = resourceGroup().location

@description('Nome da aplicação do L400, de 2 a 32 caracteres (letras minúsculas, números e hífens). Separada da aplicação do L300, que continua existindo como referência. Forma o endereço da aplicação.')
@minLength(2)
@maxLength(32)
param nomeAplicacao string = 'ca-vlr-l400-${uniqueString(resourceGroup().id)}'

@description('Etiquetas adicionais para os recursos criados pelo L400, combinadas com as do laboratório. Não inclua dados pessoais.')
param etiquetasAdicionais object = {}

// ---- Aplicação (fase aplicacao) ----

@description('Nome do repositório da imagem no registro. A imagem completa é <servidor do registro>/<repositorio>:<tag>.')
param repositorioImagem string = 'vareleira-chat'

@description('Tag da imagem publicada no registro antes da fase aplicacao (o Bicep não constrói imagens). Precisa ser uma imagem que tenha a coordenação: com a imagem do L300, a variável de coordenação seria ignorada. Use uma tag imutável. Obrigatória na fase aplicacao: o módulo da aplicação recusa valor vazio.')
param tagImagem string = ''

@description('ID do aplicativo (cliente) do registro de aplicativo do chat no Microsoft Entra ID, criado fora do Bicep, com o endereço de retorno da saída urlRetornoLogin. Obrigatório na fase aplicacao; não é segredo, mas não o fixe no repositório.')
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

@description('Modo de busca da aplicação: vetorial, texto ou hibrida. O padrão é o do L300: a comparação entre as duas aplicações só vale com a mesma configuração.')
@allowed([
  'vetorial'
  'texto'
  'hibrida'
])
param modoBusca string = 'hibrida'

@description('Quantidade de trechos recuperados por pergunta. O padrão é o do L300.')
@minValue(1)
@maxValue(10)
param quantidadeTrechos int = 3

@description('Esforço de raciocínio do modelo de geração. O padrão é o do L300.')
@allowed([
  'none'
  'low'
  'medium'
  'high'
])
param esforco string = 'low'

var etiquetas = union(
  {
    laboratorio: 'vareleira-rag'
    nivel: 'L400'
    dados: 'sinteticos'
  },
  etiquetasAdicionais
)

// Perfis do índice, fixos aqui para não herdar valor de outro nível. O candidato conserva o prefixo do L300 de propósito: o
// filtro de acesso documental e a autorização do chat só valem para índices desse namespace. As dimensões dos dois perfis são
// as de text-embedding-3-small: a referência usa o tamanho cheio, e o candidato, um vetor reduzido.
var prefixoIndiceL300 = 'vareleira-lar-l300'
var perfisDeIndice = {
  referencia: {
    nome: 'vareleira-lar-l300'
    dimensoes: 1536
  }
  candidato: {
    nome: 'vareleira-lar-l300-l400-768'
    dimensoes: 768
  }
}
var perfil = perfisDeIndice[perfilIndice]

// Dimensões que cada modelo de embeddings aceita (mínimo e máximo), as mesmas de scripts/lab_ingestao.py.
var limitesDeDimensoes = {
  'text-embedding-ada-002': {
    minimo: 1536
    maximo: 1536
  }
  'text-embedding-3-small': {
    minimo: 2
    maximo: 1536
  }
  'text-embedding-3-large': {
    minimo: 2
    maximo: 3072
  }
}

// Recursos que já existem. Aqui eles só são referenciados e lidos: nenhuma fase os redeclara.
resource modelos 'Microsoft.CognitiveServices/accounts@2026-07-01' existing = {
  name: nomeModelos
}

resource primario 'Microsoft.CognitiveServices/accounts/deployments@2026-07-01' existing = {
  parent: modelos
  name: nomeDeploymentGeracao
}

resource embeddingsAtual 'Microsoft.CognitiveServices/accounts/deployments@2026-07-01' existing = {
  parent: modelos
  name: nomeDeploymentEmbeddings
}

resource contingenciaExistente 'Microsoft.CognitiveServices/accounts/deployments@2026-07-01' existing = {
  parent: modelos
  name: nomeDeploymentContingencia
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

// ---- Guardas ----
// Cada fato abaixo é calculado na implantação, a partir dos parâmetros e do estado atual dos deployments existentes, e entregue
// ao módulo de guardas, cujos parâmetros aceitam um único valor (verdadeiro): se algum fato for falso, o ARM recusa o módulo
// e, por dependência, os recursos de cada fase, antes de criar ou alterar qualquer coisa. Leituras do estado dos recursos só
// acontecem onde a fase as usa: o `if` do ARM avalia só o ramo escolhido. O any() só desliga a checagem de tipo do compilador
// (um valor calculado na implantação não é literal); a recusa continua a cargo do ARM.

var nomesDeDeploymentsDistintos = nomeDeploymentContingencia != nomeDeploymentGeracao && nomeDeploymentContingencia != nomeDeploymentEmbeddings

var indiceNoNamespaceDoL300 = startsWith(perfil.nome, prefixoIndiceL300) && (perfilIndice == 'referencia' || perfil.nome != perfisDeIndice.referencia.nome)

var modeloDeEmbeddings = embeddingsAtual.properties.model.name
var dimensoesCompativeisComOModelo = contains(limitesDeDimensoes, modeloDeEmbeddings)
  ? (perfil.dimensoes >= limitesDeDimensoes[modeloDeEmbeddings].minimo && perfil.dimensoes <= limitesDeDimensoes[modeloDeEmbeddings].maximo)
  : false

var modeloDeclaradoIgualAoPrincipal = primario.properties.model.name == modeloContingencia && primario.properties.model.version == versaoModeloContingencia
var contingenciaAtualIgualAoPrincipal = fase == 'aplicacao'
  ? (contingenciaExistente.properties.model.name == primario.properties.model.name && contingenciaExistente.properties.model.version == primario.properties.model.version)
  : true

module guardas 'modules/l400-guardas.bicep' = {
  name: 'l400-guardas'
  params: {
    nomesDeDeploymentsDistintos: any(nomesDeDeploymentsDistintos)
    indiceNoNamespaceDoL300: any(indiceNoNamespaceDoL300)
    dimensoesCompativeisComOModelo: any(dimensoesCompativeisComOModelo)
    contingenciaComMesmoModeloEVersao: any(modeloDeclaradoIgualAoPrincipal && contingenciaAtualIgualAoPrincipal)
  }
}

// ---- Fase contingencia ----
// Só um deployment filho do recurso de modelos existente, reaproveitando o módulo do Desafio 03 do L100. O recurso de modelos
// não é redeclarado, e por isso nenhuma das propriedades dele (inclusive o acesso público) é reaplicada.

module contingencia 'modules/geracao.bicep' = if (fase == 'contingencia') {
  name: 'l400-contingencia'
  dependsOn: [
    guardas
  ]
  params: {
    nomeModelos: nomeModelos
    modeloGeracao: modeloContingencia
    versaoModeloGeracao: versaoModeloContingencia
    nomeDeploymentGeracao: nomeDeploymentContingencia
    skuDeploymentGeracao: skuContingencia
    capacidadeGeracao: capacidadeContingencia
  }
}

// ---- Fase aplicacao ----
// Reutiliza o módulo da aplicação do L200 no ambiente do L300. A identidade é a do L300, com os papéis que ela já tem: esta
// fase não atribui papéis. A aplicação nasce com o ingresso fechado, a menos que ingressoExterno seja verdadeiro, e a
// autenticação é criada junto com ela. O acesso documental e a coordenação são exigidos, nunca opcionais.

var servidorRegistro = fase == 'aplicacao' ? registro.properties.loginServer : ''
var clientIdIdentidade = fase == 'aplicacao' ? identidadeAplicacao.properties.clientId : ''

module aplicacao 'modules/l200-aplicacao.bicep' = if (fase == 'aplicacao') {
  name: 'l400-aplicacao'
  dependsOn: [
    guardas
  ]
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
    nomeIndice: perfil.nome
    nomeDeploymentEmbeddings: nomeDeploymentEmbeddings
    nomeDeploymentGeracao: nomeDeploymentGeracao
    dimensoes: perfil.dimensoes
    modoBusca: modoBusca
    quantidadeTrechos: quantidadeTrechos
    esforco: esforco
    exigirAcessoDocumental: true
    exigirCoordenacao: true
    nomeDeploymentContingencia: nomeDeploymentContingencia
  }
}

// ---- Saídas (sem segredos) ----
// Vazias quando a fase correspondente não foi executada.

output fase string = fase
output nomeDeploymentContingencia string = contingencia.?outputs.nomeDeploymentGeracao ?? ''
output modeloDaContingencia string = contingencia.?outputs.modeloGeracao ?? ''
output guardasAtendidas object = guardas.outputs.atendidas
output perfilIndice string = fase == 'aplicacao' ? perfilIndice : ''
output nomeIndice string = fase == 'aplicacao' ? perfil.nome : ''
output dimensoes int = fase == 'aplicacao' ? perfil.dimensoes : 0
output nomeAplicacao string = aplicacao.?outputs.nome ?? ''
output nomeRevisaoAtual string = aplicacao.?outputs.nomeRevisaoAtual ?? ''

// Informe este endereço de retorno no registro de aplicativo antes da fase aplicacao: o endereço da aplicação do L400 é
// diferente do da aplicação do L300, e um endereço de retorno que o registro não conhece faz o login falhar.
output urlRetornoLogin string = fase == 'aplicacao'
  ? 'https://${nomeAplicacao}.${ambienteExistente.properties.defaultDomain}/.auth/login/aad/callback'
  : ''
output urlAplicacao string = fase == 'aplicacao' && ingressoExterno
  ? 'https://${aplicacao.?outputs.enderecoAplicacao ?? ''}'
  : ''

// Descritor para conferir a implantação. As guardas só provam o que o Bicep consegue ler (nomes, modelo e versão dos
// deployments, dimensões do modelo); o resto é conferido fora do Bicep, e escolher um perfil de índice não prova compatibilidade.
output descritorVerificacao object = {
  fase: fase
  aviso: 'As guardas do Bicep provam só o que ele lê: nomes distintos, mesmo modelo e versão no principal e na contingência, e dimensões do perfil dentro do limite do modelo de embeddings. Escolher o perfil de índice troca configuração e não prova que os vetores são compatíveis.'
  topologia: {
    aplicacaoDoL300: 'preservada, como referência da comparação; não é alterada por este nível'
    aplicacaoDoL400: 'ambiente do L300, ingresso fechado até a abertura explícita, login do Microsoft Entra ID, acesso documental e coordenação exigidos'
    deploymentDeContingencia: 'filho do recurso de modelos existente; mesmo modelo e versão do principal; cota explícita, sem inferência'
    identidade: 'a do L300, sem novos papéis; o papel de uso dos modelos vale para todos os deployments do recurso'
  }
  perfisDeIndice: {
    referencia: perfisDeIndice.referencia
    candidato: perfisDeIndice.candidato
  }
  foraDoBicep: [
    'Criação, carga e conferência do índice candidato (scripts/gerenciar_ingestao_l300.py com --indice e --dimensoes do perfil candidato).'
    'Conferência offline da migração (scripts/operar_l400.py --etapa conferir-migracao) antes de escolher o perfil candidato, e de novo antes do retorno.'
    'Registro do endereço de retorno da saída urlRetornoLogin no registro de aplicativo, e os papéis de aplicação, no Microsoft Entra ID.'
    'Publicação da imagem com a coordenação no registro, antes da fase aplicacao.'
    'Consulta da cota regional dos modelos e limpeza dos recursos temporários do L400 ao fim.'
  ]
}
