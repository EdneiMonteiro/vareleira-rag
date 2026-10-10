using '../main.bicep'

// Parâmetros do L100, Desafio 07: tudo o que o Desafio 03 cria (os mesmos valores, para que a
// implantação incremental não altere o armazenamento, a busca nem os deployments) mais o cofre de
// segredos e, quando informado, os papéis de leitura da identidade da aplicação.
// Não escreva aqui IDs de assinatura, de tenant ou de pessoas.
param nomeContainer = 'base-documental'
param sku = 'Standard_LRS'
param retencaoExclusaoDias = 7

// O ID de objeto de quem vai operar o laboratório vem de uma variável de ambiente, definida apenas
// na sua sessão do terminal (veja o Desafio 01). Sem ela, nenhum papel é atribuído.
param principalIdCarga = readEnvironmentVariable('VARELEIRA_ID_OBJETO_CARGA', '')

param implantarIndexacao = true
param skuBusca = 'basic'
param modeloEmbeddings = 'text-embedding-3-small'
param versaoModeloEmbeddings = '1'
param nomeDeploymentEmbeddings = 'embeddings'
param skuDeploymentEmbeddings = 'GlobalStandard'
param capacidadeEmbeddings = 30

param implantarGeracao = true
param modeloGeracao = 'gpt-5.4-mini'
param versaoModeloGeracao = '2026-03-17'
param nomeDeploymentGeracao = 'geracao'
param skuDeploymentGeracao = 'GlobalStandard'
param capacidadeGeracao = 50

param implantarCofre = true
param retencaoCofreDias = 7

// Exceção de laboratório: a proteção contra expurgo fica DESLIGADA aqui, de propósito. Ligada, ela não pode ser
// desfeita e impediria a limpeza completa do laboratório (o cofre excluído reservaria o nome durante a retenção).
// Em produção, use o padrão do módulo (ligada).
param protecaoCofreContraExpurgo = false

// O ID de objeto do service principal da aplicação (não o ID da aplicação) vem de outra variável de
// ambiente, definida só na sua sessão. Vazia, nenhum papel é atribuído à aplicação.
param principalIdAplicacao = readEnvironmentVariable('VARELEIRA_ID_OBJETO_APLICACAO', '')
