metadata name = 'Vareleira RAG · L300 · Guardas do isolamento'
metadata description = 'Não cria recursos. Reúne as condições que precisam ser verdadeiras para fechar o acesso público dos serviços de dados: cada uma é um parâmetro com um único valor permitido, e o ARM recusa este módulo (e, por dependência, o isolamento) antes de criar ou alterar qualquer recurso se o valor recebido for outro.'

// Módulo chamado por l300-isolamento.bicep. Fica separado porque o compilador do Bicep só aceita valores calculados
// (leituras do estado atual dos recursos) em parâmetros sem valores permitidos; o módulo de isolamento recebe os valores e os repassa
// a estes parâmetros, que são os que impõem a regra.
targetScope = 'resourceGroup'

@description('Autorização explícita de quem opera: só verdadeiro. É uma declaração, não uma medição: o Bicep não consegue conferir a rede.')
@allowed([
  true
])
param conectividadePrivadaValidada bool

@description('Estado da conexão compartilhada da busca com o armazenamento: só Approved.')
@allowed([
  'Approved'
])
param estadoLinkArmazenamento string

@description('Estado da conexão compartilhada da busca com os modelos: só Approved.')
@allowed([
  'Approved'
])
param estadoLinkModelos string

@description('A camada, as réplicas e as partições informadas são as do serviço de busca atual: só verdadeiro.')
@allowed([
  true
])
param configuracaoBuscaConfere bool

@description('A redundância informada é a da conta de armazenamento atual: só verdadeiro.')
@allowed([
  true
])
param configuracaoArmazenamentoConfere bool

// Registro das guardas que valeram. O módulo só chega a produzir esta saída se todas foram atendidas.
output atendidas object = {
  conectividadePrivadaValidada: conectividadePrivadaValidada
  estadoLinkArmazenamento: estadoLinkArmazenamento
  estadoLinkModelos: estadoLinkModelos
  configuracaoBuscaConfere: configuracaoBuscaConfere
  configuracaoArmazenamentoConfere: configuracaoArmazenamentoConfere
}
