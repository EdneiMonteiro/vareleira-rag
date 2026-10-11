using '../main.bicep'

// Parâmetros do L100, Desafio 02: o armazenamento do Desafio 01 (os mesmos valores, para que
// a implantação incremental não o altere) mais o serviço de busca e o deployment de embeddings.
// Não escreva aqui IDs de assinatura, de tenant ou de pessoas.
param nomeContainer = 'base-documental'
param sku = 'Standard_LRS'
param retencaoExclusaoDias = 7

// O ID de objeto de quem vai operar o laboratório vem de uma variável de ambiente, definida apenas
// na sua sessão do terminal (veja o Desafio 01). Sem ela, nenhum papel é atribuído: um administrador
// precisará conceder os acessos a dados do armazenamento, da busca e dos modelos.
param principalIdCarga = readEnvironmentVariable('VARELEIRA_ID_OBJETO_CARGA', '')

param implantarIndexacao = true
param skuBusca = 'basic'
param modeloEmbeddings = 'text-embedding-3-small'
param versaoModeloEmbeddings = '1'
param nomeDeploymentEmbeddings = 'embeddings'
param skuDeploymentEmbeddings = 'GlobalStandard'
param capacidadeEmbeddings = 30
