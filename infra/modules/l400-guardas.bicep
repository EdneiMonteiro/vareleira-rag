metadata name = 'Vareleira RAG · L400 · Guardas da contingência e da aplicação'
metadata description = 'Não cria recursos. Reúne as condições que precisam ser verdadeiras antes de criar a contingência ou a aplicação do L400: cada uma é um parâmetro com um único valor permitido, e o ARM recusa este módulo (e, por dependência, os recursos de cada fase) antes de criar ou alterar qualquer recurso se o valor recebido for outro.'

// Módulo chamado por l400.bicep, que calcula cada fato a partir dos parâmetros e do estado atual dos deployments existentes.
targetScope = 'resourceGroup'

@description('O nome do deployment de contingência é diferente do principal e do de embeddings: só verdadeiro. Um nome igual atualizaria um deployment existente em vez de criar a contingência.')
@allowed([
  true
])
param nomesDeDeploymentsDistintos bool

@description('O índice do perfil escolhido está no namespace do L300 (o prefixo que o filtro de acesso documental reconhece) e, no perfil candidato, é diferente do índice de referência: só verdadeiro.')
@allowed([
  true
])
param indiceNoNamespaceDoL300 bool

@description('As dimensões do perfil de índice cabem no modelo do deployment de embeddings que existe: só verdadeiro. O modelo é lido do recurso de modelos, não de um parâmetro.')
@allowed([
  true
])
param dimensoesCompativeisComOModelo bool

@description('A contingência tem o mesmo modelo e a mesma versão do deployment principal: só verdadeiro. Na fase contingencia compara o declarado com o principal; na fase aplicacao, também o deployment de contingência que existe.')
@allowed([
  true
])
param contingenciaComMesmoModeloEVersao bool

// Registro das guardas que valeram. O módulo só chega a produzir esta saída se todas foram atendidas.
output atendidas object = {
  nomesDeDeploymentsDistintos: nomesDeDeploymentsDistintos
  indiceNoNamespaceDoL300: indiceNoNamespaceDoL300
  dimensoesCompativeisComOModelo: dimensoesCompativeisComOModelo
  contingenciaComMesmoModeloEVersao: contingenciaComMesmoModeloEVersao
}
