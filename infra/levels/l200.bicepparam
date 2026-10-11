using '../l200.bicep'

// Parâmetros do nível L200 (Desafios 01, 05 e 07). Não escreva aqui IDs de assinatura, de tenant, de aplicativos
// ou de pessoas, nem segredos: tudo isso entra por variáveis de ambiente, definidas só na sua sessão do terminal.
// As variáveis abaixo são deste arquivo, de quem implanta. Não as confunda com as variáveis de ambiente que o Bicep
// define na aplicação (VARELEIRA_BUSCA, VARELEIRA_MODELOS e outras).

// Base do L100, que já existe no grupo de recursos: os nomes vêm das saídas da implantação do L100. Sem valor padrão,
// de propósito: o Bicep recusa nomes vazios, e um nome errado criaria outro serviço de busca, que cobra por hora.
param nomeConta = readEnvironmentVariable('VARELEIRA_NOME_CONTA', '')
param nomeBusca = readEnvironmentVariable('VARELEIRA_NOME_BUSCA', '')
param nomeModelos = readEnvironmentVariable('VARELEIRA_NOME_MODELOS', '')
param nomeContainer = 'base-documental'

// Ingestão gerenciada: o serviço de busca é reaplicado para ligar a identidade dele, com os mesmos valores do L100
// (os padrões do L100, Desafio 02). Se você escalou o serviço depois do L100, informe aqui os valores atuais.
// A região só precisa ser informada se o serviço do L100 não estiver na região do grupo de recursos.
param habilitarIngestao = true
param skuBusca = 'basic'
param replicasBusca = 1
param particoesBusca = 1
param localizacaoBusca = readEnvironmentVariable('VARELEIRA_LOCALIZACAO_BUSCA', '')

// Aplicação do chat, em etapas. Sem as variáveis, só a base do L200 é criada (registro, ambiente, identidades e papéis).
//   VARELEIRA_IMPLANTAR_APLICACAO=true  cria a aplicação, com o ingresso ainda fechado e a autenticação ligada;
//   VARELEIRA_INGRESSO_EXTERNO=true     abre o endereço público depois de conferir a autenticação.
param implantarAplicacao = bool(readEnvironmentVariable('VARELEIRA_IMPLANTAR_APLICACAO', 'false'))
param ingressoExterno = bool(readEnvironmentVariable('VARELEIRA_INGRESSO_EXTERNO', 'false'))

// A imagem precisa estar publicada no registro antes da etapa da aplicação.
param tagImagem = readEnvironmentVariable('VARELEIRA_TAG_IMAGEM', '')

// O índice que a aplicação consulta é o mesmo que o ingestor do L200 cria. Só mude se os dois usarem outro nome.
param nomeIndice = readEnvironmentVariable('VARELEIRA_NOME_INDICE', 'vareleira-lar-l200')

// Login dos usuários, com o registro de aplicativo próprio do chat no Microsoft Entra ID. O segredo de cliente só
// existe na sua sessão: não o grave em arquivo, em prompt nem no histórico, e remova as variáveis ao terminar
// (Remove-Item Env:\NOME). Quem chega sem login recebe, por padrão, 401 (Return401); RedirectToLoginPage envia o
// navegador à página de login. A autenticação é obrigatória nos dois casos.
param idAplicacaoLogin = readEnvironmentVariable('VARELEIRA_ID_APLICACAO_LOGIN', '')
param tenantLogin = readEnvironmentVariable('VARELEIRA_ID_TENANT_LOGIN', '')
param segredoLogin = readEnvironmentVariable('VARELEIRA_SEGREDO_LOGIN', '')
param acaoSemLogin = readEnvironmentVariable('VARELEIRA_ACAO_SEM_LOGIN', 'Return401')
