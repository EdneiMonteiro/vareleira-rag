# L200 — Desafio 05: hospedar o chat com autenticação

[Início do laboratório](../../README.md) · [Desafio 04](04-chat-local.md) · [Desafio 06](06-avaliar-chat.md)

| Item | Descrição |
| --- | --- |
| Situação | Infraestrutura, imagem, autenticação na borda e consultas com token real foram conferidas no Azure. O login interativo de uma pessoa permanece fora da validação executada. |
| Público | Pessoas de operações, arquitetura e desenvolvimento, com apoio de quem administra assinatura e tenant. |
| Resultado | Chat em Azure Container Apps, com identidade própria para dados e autenticação obrigatória para acesso. |
| Custo | Registro de imagens, construção remota, processamento da aplicação, requisições, logs, busca e tokens. |

## Conteúdo

- [Cenário](#cenário)
- [Objetivos](#objetivos)
- [Artefatos e disponibilidade](#artefatos-e-disponibilidade)
- [Tecnologias e conceitos](#tecnologias-e-conceitos)
- [Pré-requisitos](#pré-requisitos)
- [Etapa 1: publicar a imagem](#etapa-1-publicar-a-imagem)
- [Etapa 2: preparar o provedor de login](#etapa-2-preparar-o-provedor-de-login)
- [Etapa 3: implantar com ingresso interno](#etapa-3-implantar-com-ingresso-interno)
- [Etapa 4: conferir autenticação e abrir o ingresso](#etapa-4-conferir-autenticação-e-abrir-o-ingresso)
- [Como pedir uma mudança ao Copilot no VS Code](#como-pedir-uma-mudança-ao-copilot-no-vs-code)
- [Conferência do resultado](#conferência-do-resultado)
- [Solução de problemas](#solução-de-problemas)
- [Custos, pausa e limpeza](#custos-pausa-e-limpeza)
- [Situação da validação](#situação-da-validação)
- [Glossário](#glossário)
- [Referências](#referências)

## Cenário

No piloto interno fictício de 2025, Beatriz Torres quer disponibilizar a interface sem depender
do computador de quem opera os scripts. A equipe hospeda o chat e separa dois acessos:
quem entra no chat e qual identidade consulta os serviços Azure.

O endereço externo deste laboratório exige autenticação. A base continua sintética e compartilhada
entre pessoas do tenant autorizado, diretório de identidades da organização.
Restrição por pessoa e autorização por documento precisam de desenho adicional antes de ampliar o piloto.

## Objetivos

1. Construir uma imagem sem incluir dados, segredos ou histórico Git.
2. Usar identidade gerenciada da aplicação para baixar imagem, consultar busca e usar modelos.
3. Configurar Microsoft Entra ID como provedor de login.
4. Criar a aplicação com ingresso interno, conferir autenticação e somente então abrir o endereço externo.
5. Observar recusas anônimas e conferir uma consulta real.

## Artefatos e disponibilidade

| Artefato disponível | Uso |
| --- | --- |
| [Dockerfile](../../Dockerfile) e [.dockerignore](../../.dockerignore) | Imagem e lista dos arquivos enviados ao build |
| [Infraestrutura L200](../../infra/l200.bicep) e [parâmetros](../../infra/levels/l200.bicepparam) | Base e aplicação implantadas em etapas |
| [Módulo da aplicação](../../infra/modules/l200-aplicacao.bicep) | Identidade, configuração, escala, probes e autenticação |
| [Chat](../../scripts/chat_web.py) e [regras](../../scripts/lab_chat.py) | Fluxo fixo de consulta e política |
| [Testes da infraestrutura](../../tests/test_infra_l200.py) | Contratos e builds locais |
| [Registro do desafio](../../docs/validacao/l200-05-hospedar-chat.md) | Evidências Azure, autenticação e limitações |

## Tecnologias e conceitos

**Imagem de contêiner** reúne aplicação e dependências para execução. O **Azure Container Registry**
(ACR) guarda essa imagem, e ACR Tasks pode construí-la remotamente, sem Docker instalado no computador [1].
Uma **tag** identifica a versão; o **digest** é o resumo criptográfico da imagem.

**Azure Container Apps** executa o contêiner no perfil Consumption. A aplicação usa 0,5 vCPU,
um núcleo virtual de processamento fracionado, e 1 gibibyte (GiB) de memória, com escala de zero a uma réplica.
Escala a zero reduz cobrança de computação; registro, busca e outras dependências têm cobrança própria [2].

**Ingresso** define como pedidos chegam à aplicação. `external=false` limita o alcance ao ambiente
Container Apps; `external=true` permite alcançar o endereço de fora. A configuração exige HTTPS,
versão criptografada do protocolo HTTP (*Hypertext Transfer Protocol*), protegida por TLS
(*Transport Layer Security*) [3].

**EasyAuth**, autenticação integrada da plataforma, valida o token, comprovante digital de autenticação,
ou a sessão antes de encaminhar pedidos à aplicação [4]. O Python recebe a representação da identidade,
chamada **principal**, em `X-MS-CLIENT-PRINCIPAL`.
Esse cabeçalho não tem assinatura própria: o programa só pode confiar nele atrás do ingresso
com autenticação obrigatória.

| Identidade | Uso e credencial |
| --- | --- |
| Operador | Implanta recursos e configura login, com sua sessão e permissões autorizadas |
| Serviço de busca | Identidade do sistema: lê blobs e usa embeddings |
| Aplicação do chat | Identidade gerenciada atribuída pelo usuário: `AcrPull`, leitura do índice e modelos |
| Registro do login | Representa o chat no Entra ID; o segredo fica no provedor de autenticação |
| Pessoa que usa o chat | Autentica pelo fluxo Entra ID; não recebe as permissões Azure da aplicação |

A identidade gerenciada evita segredo para **dados e modelos** [5]. A configuração do login ainda
usa uma credencial específica. O template não cria esse registro no Entra ID.

## Pré-requisitos

Conclua os Desafios 01 a 04. Tenha autorização para a construção remota, implantação, ingresso
externo, registro de aplicação e credencial temporária. Permissões Azure e administração de aplicações
no Entra ID são escopos diferentes.

Use o tenant conferido, variáveis do destino, ambiente Python e PowerShell 7 no VS Code.
Confira o custo e as políticas da região. O procedimento demonstrado usa um registro de login novo;
reutilizar um registro exige inventário e aprovação de seus proprietários.

## Etapa 1: publicar a imagem

Recupere a base criada no Desafio 02, incluindo o endereço de retorno (URL, *Uniform Resource Locator*)
do provedor de login:

```powershell
$l200 = az deployment group show --subscription $assinatura --resource-group $grupo --name vareleira-rag-l200-base --output json | ConvertFrom-Json
$registro = $l200.properties.outputs.nomeRegistro.value
$servidorRegistro = $l200.properties.outputs.servidorRegistro.value
$urlRetorno = $l200.properties.outputs.urlRetornoLogin.value
$nomeIdentidade = $l200.properties.outputs.nomeIdentidadeAplicacao.value
if (-not $registro -or -not $urlRetorno) { throw "Confira as saídas da base L200." }
$tagImagem = "<TAG-NOVA-DA-IMAGEM>"
```

1. Revise Dockerfile, dependências e `.dockerignore`.
2. Confira os testes locais antes de enviar arquivos.
3. Autorize o build remoto, que envia somente o contexto permitido ao seu ACR.

```powershell
python -m unittest discover -s tests
python -m pip check
```

**[altera o Azure]** ao construir e publicar a imagem:

```powershell
az acr build --subscription $assinatura --registry $registro --image "vareleira-chat:$tagImagem" --file Dockerfile --no-logs .
az acr task list-runs --subscription $assinatura --registry $registro --output table
az acr repository show --subscription $assinatura --name $registro --image "vareleira-chat:$tagImagem" --query digest --output tsv
```

**Resultado esperado:** execução `Succeeded` e digest presente. Use uma tag nova, preservando a
imagem anterior. O Dockerfile executa o processo como usuário sem privilégios.
O contexto exclui documentos, gabaritos, `.venv`, `.git`, arquivos locais e segredos.

Uma falha de exibição dos logs no terminal pode ocorrer depois de o build remoto concluir.
Confira execução e digest antes de repetir o build, para evitar trabalho e cobrança duplicados.

## Etapa 2: preparar o provedor de login

**[altera o Azure]** e o Microsoft Entra ID: cria registro, principal de serviço e credencial.
Execute somente após autorização desses alvos e efeitos.

1. Confira que o tenant ativo corresponde ao autorizado.
2. Escolha um nome exclusivo e confira que não existe registro anterior com esse nome.
3. Crie o registro para um único tenant (*single-tenant*) e seu principal de serviço.

```powershell
$tenantAtivo = az account show --query tenantId --output tsv
if ($tenantAtivo -ne $tenant) { throw "A sessão ativa está em outro tenant." }
$nomeLogin = "<NOME-EXCLUSIVO-DO-LOGIN-DO-CHAT>"
az ad app list --display-name $nomeLogin --output table
```

Prossiga com a criação somente após conferir ausência ou inventário do registro existente:

```powershell
$login = az ad app create --display-name $nomeLogin --sign-in-audience AzureADMyOrg --web-redirect-uris $urlRetorno --enable-id-token-issuance true --output json | ConvertFrom-Json
$idLogin = $login.appId
if (-not $idLogin) { throw "O registro de login não foi criado." }
az ad app update --id $idLogin --identifier-uris "api://$idLogin" --output none
az ad sp create --id $idLogin --output none
```

O endereço de retorno deve terminar em `/.auth/login/aad/callback` e corresponder ao endereço
calculado para a aplicação. O provedor usa esse retorno para concluir o login [6].
O registro de login não recebe papéis de dados ou de administração Azure.

Crie uma credencial curta e mantenha seu valor apenas em memória:

```powershell
$nomeCredencial = "validacao-" + (Get-Date -Format "yyyyMMddHHmmss")
$fimCredencial = (Get-Date).ToUniversalTime().AddDays(1).ToString("yyyy-MM-ddTHH:mm:ssZ")
$credencial = az ad app credential reset --id $idLogin --append --display-name $nomeCredencial --end-date $fimCredencial --output json | ConvertFrom-Json
$chaves = @(az ad app credential list --id $idLogin --output json | ConvertFrom-Json | Where-Object displayName -eq $nomeCredencial)
if ($chaves.Count -ne 1 -or -not $credencial.password) { throw "A credencial de teste não foi identificada de forma única." }
$idChaveLogin = $chaves[0].keyId
$env:VARELEIRA_SEGREDO_LOGIN = $credencial.password
```

Registre **somente os identificadores** necessários à remoção em local privado.
Não exiba `$credencial`, não copie o segredo para prompt ou arquivo e não habilite logs de depuração.
`--append` preserva credenciais anteriores; o registro novo deve continuar exclusivo do laboratório.

## Etapa 3: implantar com ingresso interno

Preencha os parâmetros sem escrever o segredo no arquivo:

```powershell
$env:VARELEIRA_NOME_CONTA = $conta
$env:VARELEIRA_NOME_BUSCA = $busca
$env:VARELEIRA_NOME_MODELOS = $modelos
$env:VARELEIRA_TAG_IMAGEM = $tagImagem
$env:VARELEIRA_IMPLANTAR_APLICACAO = "true"
$env:VARELEIRA_INGRESSO_EXTERNO = "false"
$env:VARELEIRA_NOME_INDICE = "vareleira-lar-l200"
$env:VARELEIRA_ID_APLICACAO_LOGIN = $idLogin
$env:VARELEIRA_ID_TENANT_LOGIN = $tenant
$env:VARELEIRA_ACAO_SEM_LOGIN = "Return401"
```

O segredo é um parâmetro Bicep marcado como seguro. Evite `build-params --stdout` enquanto a variável
real estiver preenchida: esse comando local mostraria o valor.

Execute o plano enquanto o ingresso continua interno:

```powershell
az deployment group what-if --subscription $assinatura --resource-group $grupo --name vareleira-rag-l200-app --parameters infra\levels\l200.bicepparam
```

Revise o resultado. Após aprovar as mudanças, aplique a implantação autorizada e retire o segredo
do terminal. Se interromper o procedimento, retire essa variável antes de fechar o terminal:

```powershell
try {
    az deployment group create --subscription $assinatura --resource-group $grupo --name vareleira-rag-l200-app --parameters infra\levels\l200.bicepparam
    if ($LASTEXITCODE -ne 0) { throw "A implantação da aplicação falhou." }
}
finally {
    Remove-Item Env:\VARELEIRA_SEGREDO_LOGIN -ErrorAction SilentlyContinue
    Remove-Variable credencial -ErrorAction SilentlyContinue
}
```

**[altera o Azure]** na implantação. A aplicação nasce com ingresso interno; a configuração de
autenticação é aplicada depois da criação do recurso. Essa ordem evita abrir externamente a aplicação
antes de proteger a borda.

## Etapa 4: conferir autenticação e abrir o ingresso

1. Recupere o nome da aplicação e seu endereço.
2. Confira plataforma de autenticação, ação para pedidos sem login e exigência de HTTPS.
3. Somente após essa conferência, abra o ingresso externo autorizado.

```powershell
$implantacaoApp = az deployment group show --subscription $assinatura --resource-group $grupo --name vareleira-rag-l200-app --output json | ConvertFrom-Json
$aplicacao = $implantacaoApp.properties.outputs.nomeAplicacao.value
if (-not $aplicacao) { throw "Consulte a implantação e confirme o nome da aplicação." }
$auth = az containerapp auth show --subscription $assinatura --resource-group $grupo --name $aplicacao --output json | ConvertFrom-Json
$provedor = $auth.identityProviders.azureActiveDirectory
if (-not $auth.platform.enabled -or $auth.globalValidation.unauthenticatedClientAction -ne "Return401" -or -not $auth.httpSettings.requireHttps -or -not $provedor.enabled -or $provedor.registration.openIdIssuer -ne "https://login.microsoftonline.com/$tenant/v2.0" -or $provedor.validation.allowedAudiences -notcontains "api://$idLogin") {
    throw "A autenticação obrigatória não foi confirmada."
}
```

**[altera o Azure]** após conferir essas guardas e aprovar a exposição externa:

```powershell
az containerapp ingress enable --subscription $assinatura --resource-group $grupo --name $aplicacao --type external --target-port 8000 --transport auto --allow-insecure false --output none
$env:VARELEIRA_INGRESSO_EXTERNO = "true"
$fqdn = az containerapp show --subscription $assinatura --resource-group $grupo --name $aplicacao --query properties.configuration.ingress.fqdn --output tsv
$urlChat = "https://$fqdn"
```

**[altera o Azure]** no ingresso. `Return401` devolve erro para quem chega sem login; não redireciona
automaticamente a página inicial. Para o fluxo de pessoa, abra o endereço de login abaixo no navegador
e conclua a autenticação oficial, sem compartilhar senha, códigos ou tokens:

```powershell
$urlLogin = $urlChat + "/.auth/login/aad"
```

Abra o valor de `$urlLogin` no navegador. Esse passo é um procedimento de uso do provedor;
a rodada automatizada conferiu tokens de uma identidade de teste, não o login de uma pessoa.
O registro empresarial não exige atribuição a pessoas específicas nesta implementação: pessoas do
tenant que puderem autenticar têm acesso. Definir uma lista de usuários é uma alteração de acesso
separada, sujeita à autorização do administrador.

### Prompt para o Copilot: conferir o limite de confiança

Anexe o módulo da aplicação, `lab_chat.py` e este guia:

```text
Revise o desenho do chat sem alterar arquivos ou acessar o Azure.
Explique a ordem ingresso interno, configuração EasyAuth e abertura externa.
Separe credencial do login, identidade gerenciada da aplicação e identidade da pessoa.
Identifique o que precisa estar garantido para confiar em X-MS-CLIENT-PRINCIPAL.
Não proponha desativar autenticação, TLS ou ampliar papéis como diagnóstico.
```

## Como pedir uma mudança ao Copilot no VS Code

Delimite parâmetros e testes afetados ao pedir uma mudança. Revise os arquivos em **Source Control**,
execute testes, `az bicep lint` e `az bicep build`, e confira um novo `what-if` antes de implantar.
Uma troca de autenticação ou do público autorizado exige revisão própria; uma troca de imagem
deve conservar a revisão anterior para recuperação.

## Conferência do resultado

Os pedidos abaixo não usam segredo nem token:

```powershell
(Invoke-WebRequest ($urlChat + "/healthz") -SkipHttpErrorCheck).StatusCode
(Invoke-WebRequest ($urlChat + "/readyz") -SkipHttpErrorCheck).StatusCode
(Invoke-WebRequest $urlChat -SkipHttpErrorCheck).StatusCode
(Invoke-WebRequest ($urlChat + "/api/perguntar") -Method Post -ContentType "application/json" -Body '{"pergunta":"Teste sintético"}' -SkipHttpErrorCheck).StatusCode
```

**Resultado esperado:** `200`, `200`, `401`, `401`. Saúde e prontidão são isentas de login,
mas não consultam busca nem geração. Uma consulta autenticada real é necessária para conferir o fluxo
com a identidade gerenciada; o Desafio 06 oferece um avaliador HTTP de contrato.

Na validação, a identidade gerenciada também recebeu recusas `403` ao ler um blob, listar índices
administrativamente e consultar o recurso de armazenamento no ARM. Essas sondas foram executadas
na réplica; consultar somente os papéis do operador não substitui essa evidência.

## Solução de problemas

| Sintoma | Diagnóstico e recuperação |
| --- | --- |
| Imagem não baixa | Confira digest, registro, identidade da aplicação e `AcrPull`; preserve o administrador do ACR desabilitado. |
| Retorno de login inválido | Compare URL da aplicação e callback registrado, tenant e audiência do token. |
| `401` na página inicial | Com `Return401`, entre pelo endereço `/.auth/login/aad`; preserve a exigência de autenticação. |
| `503` com `resposta_nao_verificada` | O fluxo chegou à política, que descartou a resposta; mantenha a conferência das fontes. |
| `503` por acesso aos serviços | Confira a identidade da aplicação e seus dois papéis de dados, não os da pessoa no navegador. |
| Recurso de aplicação ausente na saída | Consulte a implantação completa e o recurso pelo nome confirmado; não invente uma URL. |

## Custos, pausa e limpeza

O perfil Consumption cobra uso da aplicação e pedidos HTTP. O ACR cobra enquanto existir,
e a construção remota também tem medição própria. Logs, busca, armazenamento e modelos são
dependências com cobrança independente [1][2].

O segredo de login temporário expira no prazo definido. Registre uma política de renovação antes
de transformar o exercício em serviço permanente. O Desafio 07 remove essa credencial, identidade
de login, aplicação e demais recursos temporários, preservando os preexistentes.

## Situação da validação

O Azure confirmou imagem, identidade, cinco papéis, ingresso inicialmente interno, autenticação
obrigatória e abertura externa posterior. Saúde e prontidão responderam `200`; pedidos anônimos e
cabeçalho artificial responderam `401`. Um token real de identidade de teste produziu resposta
geral com três evidências e recusa fora de escopo. Houve `503` por descarte da política, preservado
no [registro](../../docs/validacao/l200-05-hospedar-chat.md).

Autenticação interativa humana, restrição por pessoa, autorização por documento, disponibilidade
de produção e escala ampla permanecem fora do escopo conferido.

## Glossário

| Termo | Significado |
| --- | --- |
| ACR e ACR Tasks | Registro de imagens do Azure e serviço de construção remota |
| Imagem, tag e digest | Pacote executável, nome de versão e resumo criptográfico |
| Ingresso | Caminho pelo qual pedidos chegam à aplicação |
| Réplica | Instância em execução de uma revisão |
| EasyAuth | Autenticação integrada de Azure Container Apps |
| Tenant | Diretório de identidades |
| Principal de serviço | Representação de uma aplicação dentro de um tenant |
| Audiência do token | Aplicação ou serviço ao qual o token se destina |
| vCPU e GiB | Núcleo virtual de processamento e unidade de memória |

## Referências

1. [Construção remota com ACR Tasks](https://learn.microsoft.com/en-us/azure/container-registry/container-registry-tutorial-quick-task).
2. [Cobrança de Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/billing).
3. [Ingresso em Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/ingress-overview).
4. [Autenticação integrada em Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/authentication).
5. [Identidades gerenciadas em Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/managed-identity).
6. [Provedor Microsoft Entra ID](https://learn.microsoft.com/en-us/azure/container-apps/authentication-entra).

Texto e revisão: GPT-6.1 Sol. Código e testes: Claude Sonnet 5.5.
O Astra não estava disponível; essas escolhas de autoria não configuram os modelos do aluno.
