using '../l300.bicep'

// Parâmetros do nível L300. Não escreva aqui IDs de assinatura, de tenant, de aplicativos ou de pessoas, nem segredos:
// tudo isso entra por variáveis de ambiente, definidas só na sua sessão do terminal. As variáveis VARELEIRA_L300_* são
// deste nível e controlam as fases e os portões de segurança; o L200 não as usa, então uma variável esquecida do L200
// (como VARELEIRA_INGRESSO_EXTERNO) nunca abre o ingresso nem fecha o acesso público do L300.
// Não confunda estas variáveis, de quem implanta, com as que o Bicep define na aplicação (VARELEIRA_BUSCA e outras).

// Fase da implantação: rede (padrão), aplicacao ou isolar. Cada fase declara só os recursos dela; o valor inválido é
// recusado ao compilar os parâmetros. Execute na ordem: rede, aplicacao e, por último, isolar.
param fase = readEnvironmentVariable('VARELEIRA_L300_FASE', 'rede')

// Portões independentes, ambos falsos por padrão:
//   VARELEIRA_L300_INGRESSO_EXTERNO=true                abre o endereço público da aplicação (fase aplicacao), só depois
//                                                       de conferir o login e a autorização documental;
//   VARELEIRA_L300_CONECTIVIDADE_PRIVADA_VALIDADA=true  autoriza fechar o acesso público dos dados (fase isolar), só depois de
//                                                       demonstrar consulta, ingestão e resolução de nomes pelo caminho privado.
param ingressoExterno = bool(readEnvironmentVariable('VARELEIRA_L300_INGRESSO_EXTERNO', 'false'))
param conectividadePrivadaValidada = bool(readEnvironmentVariable('VARELEIRA_L300_CONECTIVIDADE_PRIVADA_VALIDADA', 'false'))

// Recursos do L100 e do L200 que o L300 reaproveita: os nomes vêm das saídas das implantações anteriores. Sem valor
// padrão, de propósito: o Bicep recusa nomes vazios, e um nome errado apontaria para o recurso errado.
param nomeConta = readEnvironmentVariable('VARELEIRA_NOME_CONTA', '')
param nomeBusca = readEnvironmentVariable('VARELEIRA_NOME_BUSCA', '')
param nomeModelos = readEnvironmentVariable('VARELEIRA_NOME_MODELOS', '')
param nomeRegistro = readEnvironmentVariable('VARELEIRA_NOME_REGISTRO', '')
param nomeIdentidadeAplicacao = readEnvironmentVariable('VARELEIRA_NOME_IDENTIDADE_APLICACAO', '')
param nomeWorkspaceLogs = readEnvironmentVariable('VARELEIRA_NOME_WORKSPACE_LOGS', '')

// ID de objeto de quem envia os documentos ao contêiner do L300 (o mesmo da variável do L100, Desafio 01). Obrigatório.
param principalIdCarga = readEnvironmentVariable('VARELEIRA_ID_OBJETO_CARGA', '')

// Contêiner e índice do L300: fixos neste arquivo, para não herdar um valor do L100 ou do L200 que tenha ficado na sessão.
param nomeContainer = 'base-documental-l300'
param nomeIndice = 'vareleira-lar-l300'

// Fase aplicacao: a imagem precisa estar publicada no registro antes. O segredo de cliente só existe na sua sessão: não o
// grave em arquivo, em prompt nem no histórico, e remova as variáveis ao terminar (Remove-Item Env:\NOME). Não use
// `bicep build-params --stdout` com o segredo real definido: o resultado o exibiria. A autenticação é obrigatória nos dois
// casos de acaoSemLogin (Return401 ou RedirectToLoginPage).
param tagImagem = readEnvironmentVariable('VARELEIRA_TAG_IMAGEM', '')
param idAplicacaoLogin = readEnvironmentVariable('VARELEIRA_ID_APLICACAO_LOGIN', '')
param tenantLogin = readEnvironmentVariable('VARELEIRA_ID_TENANT_LOGIN', '')
param segredoLogin = readEnvironmentVariable('VARELEIRA_SEGREDO_LOGIN', '')
param acaoSemLogin = readEnvironmentVariable('VARELEIRA_ACAO_SEM_LOGIN', 'Return401')

// Fase isolar: o ARM reaplica cada serviço inteiro, então informe a configuração ATUAL deles (confira no inventário, sem
// palpite). Vazios ou zerados, o módulo de isolamento recusa a implantação antes de alterar qualquer serviço, e valores
// diferentes dos atuais também são recusados. As regiões só precisam ser informadas se o serviço não estiver na região do
// grupo de recursos. Nas outras fases, estas variáveis não são usadas.
param localizacaoArmazenamento = readEnvironmentVariable('VARELEIRA_LOCALIZACAO_ARMAZENAMENTO', '')
param localizacaoBusca = readEnvironmentVariable('VARELEIRA_LOCALIZACAO_BUSCA', '')
param localizacaoModelos = readEnvironmentVariable('VARELEIRA_LOCALIZACAO_MODELOS', '')
param skuArmazenamento = readEnvironmentVariable('VARELEIRA_SKU_ARMAZENAMENTO', '')
param skuBusca = readEnvironmentVariable('VARELEIRA_SKU_BUSCA', '')
param replicasBusca = int(readEnvironmentVariable('VARELEIRA_REPLICAS_BUSCA', '0'))
param particoesBusca = int(readEnvironmentVariable('VARELEIRA_PARTICOES_BUSCA', '0'))
