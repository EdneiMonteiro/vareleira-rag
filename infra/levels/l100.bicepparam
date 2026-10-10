using '../main.bicep'

// Parâmetros do nível L100. Não escreva aqui IDs de assinatura, de tenant ou de pessoas.
param nomeContainer = 'base-documental'
param sku = 'Standard_LRS'
param retencaoExclusaoDias = 7

// O ID de objeto de quem enviará os documentos vem de uma variável de ambiente,
// definida apenas na sua sessão do terminal (veja o Desafio 01).
// Sem a variável, nenhum papel é atribuído: um administrador precisará conceder o acesso a dados.
param principalIdCarga = readEnvironmentVariable('VARELEIRA_ID_OBJETO_CARGA', '')
