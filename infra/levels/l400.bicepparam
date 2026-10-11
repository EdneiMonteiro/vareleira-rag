using '../l400.bicep'

// Parâmetros do nível L400. Não escreva aqui IDs de assinatura, de tenant, de aplicativos ou de pessoas, nem segredos: tudo
// isso entra por variáveis de ambiente, definidas só na sua sessão do terminal. As variáveis VARELEIRA_L400_* são deste nível e
// controlam as fases, os portões e as escolhas explícitas; as do L100 ao L300 (nomes dos recursos existentes e o login da
// aplicação) mantêm os nomes de lá. Nenhuma delas tem valor que identifique um ambiente: os valores vazios ou zerados são
// recusados ao compilar os parâmetros. Não confunda estas variáveis, de quem implanta, com as que o Bicep define na aplicação
// (VARELEIRA_BUSCA, VARELEIRA_EXIGIR_COORDENACAO e outras).

// Fase da implantação: contingencia (padrão) ou aplicacao; o valor inválido é recusado ao compilar os parâmetros. Execute na
// ordem: contingencia e, depois, aplicacao.
param fase = readEnvironmentVariable('VARELEIRA_L400_FASE', 'contingencia')

// Portão do ingresso, falso por padrão: VARELEIRA_L400_INGRESSO_EXTERNO=true abre o endereço público da aplicação (fase
// aplicacao), só depois de conferir o login e a autorização documental. O L300 usa outra variável: uma esquecida de lá nunca abre
// o ingresso do L400.
param ingressoExterno = bool(readEnvironmentVariable('VARELEIRA_L400_INGRESSO_EXTERNO', 'false'))

// Perfil do índice: referencia (padrão, o índice do L300) ou candidato (o índice separado do L400). Trocar o perfil troca só a
// configuração da aplicação: confira a migração antes (scripts\operar_l400.py --etapa conferir-migracao) e volte ao perfil
// referencia para o retorno.
param perfilIndice = readEnvironmentVariable('VARELEIRA_L400_PERFIL_INDICE', 'referencia')

// Recursos do L100 ao L300 que o L400 reaproveita: os nomes vêm das saídas das implantações anteriores. Sem valor padrão, de
// propósito: o Bicep recusa nomes vazios, e um nome errado apontaria para o recurso errado. O ambiente é o do L300.
param nomeModelos = readEnvironmentVariable('VARELEIRA_NOME_MODELOS', '')
param nomeBusca = readEnvironmentVariable('VARELEIRA_NOME_BUSCA', '')
param nomeRegistro = readEnvironmentVariable('VARELEIRA_NOME_REGISTRO', '')
param nomeIdentidadeAplicacao = readEnvironmentVariable('VARELEIRA_NOME_IDENTIDADE_APLICACAO', '')
param nomeAmbiente = readEnvironmentVariable('VARELEIRA_L400_NOME_AMBIENTE', '')

// Deployment de contingência: modelo, versão, tipo e cota explícitos, sem valores padrão. O modelo e a versão precisam ser os do
// deployment principal (uma guarda compara com o que existe no recurso de modelos), e a cota é uma escolha sua: o Bicep não a
// infere nem a consulta.
param modeloContingencia = readEnvironmentVariable('VARELEIRA_L400_MODELO_CONTINGENCIA', '')
param versaoModeloContingencia = readEnvironmentVariable('VARELEIRA_L400_VERSAO_MODELO_CONTINGENCIA', '')
param skuContingencia = readEnvironmentVariable('VARELEIRA_L400_SKU_CONTINGENCIA', '')
param capacidadeContingencia = int(readEnvironmentVariable('VARELEIRA_L400_CAPACIDADE_CONTINGENCIA', '0'))

// Fase aplicacao: a imagem, com a coordenação, precisa estar publicada no registro antes; a tag é do L400, para não herdar a do
// L300. O segredo de cliente só existe na sua sessão: não o grave em arquivo, em prompt nem no histórico, e remova as variáveis
// ao terminar (Remove-Item Env:\NOME). Não use `bicep build-params --stdout` com o segredo real definido: o resultado o
// exibiria. A autenticação é obrigatória nos dois casos de acaoSemLogin (Return401 ou RedirectToLoginPage).
param tagImagem = readEnvironmentVariable('VARELEIRA_L400_TAG_IMAGEM', '')
param idAplicacaoLogin = readEnvironmentVariable('VARELEIRA_ID_APLICACAO_LOGIN', '')
param tenantLogin = readEnvironmentVariable('VARELEIRA_ID_TENANT_LOGIN', '')
param segredoLogin = readEnvironmentVariable('VARELEIRA_SEGREDO_LOGIN', '')
param acaoSemLogin = readEnvironmentVariable('VARELEIRA_ACAO_SEM_LOGIN', 'Return401')
