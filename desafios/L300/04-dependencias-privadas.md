# L300 — Desafio 04: preparar rede privada sem interromper a ingestão

[Início do laboratório](../../README.md) · [Desafio 03](03-filtrar-acesso.md) · [Desafio 05](05-automatizar-entrega.md)

| Item | Descrição |
| --- | --- |
| Situação | Topologia, DNS (sistema de nomes de domínio), ingestão e isolamento conferidos na rodada histórica; receita pública das sondas revisada localmente e por ajuda offline, sem nova execução Azure |
| Público | Operações, arquitetura e desenvolvimento, com apoio do administrador de rede e dos serviços |
| Resultado | Definição de rede, resolução de nomes e conexões privadas para consulta e ingestão |
| Custo | Endpoints, rede, serviços, construção e armazenamento de imagens, execuções do Job, logs e tokens têm cobranças próprias; confirme orçamento e duração |

## Conteúdo

- [Cenário](#cenário)
- [Objetivos](#objetivos)
- [Artefatos e disponibilidade](#artefatos-e-disponibilidade)
- [Tecnologias e conceitos](#tecnologias-e-conceitos)
- [Pré-requisitos](#pré-requisitos)
- [Etapa 1: mapear os caminhos](#etapa-1-mapear-os-caminhos)
- [Etapa 2: compilar e revisar a topologia](#etapa-2-compilar-e-revisar-a-topologia)
- [Etapa 3: aprovar conexões e produzir evidências](#etapa-3-aprovar-conexões-e-produzir-evidências)
- [Etapa 4: fechar acesso público com retorno definido](#etapa-4-fechar-acesso-público-com-retorno-definido)
- [Como pedir uma mudança ao Copilot no VS Code](#como-pedir-uma-mudança-ao-copilot-no-vs-code)
- [Conferência do resultado](#conferência-do-resultado)
- [Solução de problemas](#solução-de-problemas)
- [Custos, pausa e limpeza](#custos-pausa-e-limpeza)
- [Situação da validação](#situação-da-validação)
- [Glossário](#glossário)
- [Referências](#referências)
- [Autoria](#autoria)

## Cenário

No piloto fictício de 2025, Beatriz Torres quer manter a interface disponível ao público interno
autorizado, enquanto os serviços de dados deixam de aceitar conexões pela internet.
A equipe precisa preservar também o caminho que lê documentos e gera embeddings.

A migração testa consulta e atualização da base separadamente. O L200 oferece um caminho de
retorno enquanto o acesso público dos dados permanecer compatível com seu ambiente.

## Objetivos

1. Separar o ingresso do chat do acesso às dependências de dados.
2. Criar ambiente Container Apps integrado à rede, sem tentar trocar a rede do ambiente anterior.
3. Preparar endpoints, resolução de nomes e conexões de saída do serviço de busca.
4. Fechar acesso público somente depois das evidências de consulta, ingestão e manutenção.

Bloquear toda saída à internet, privatizar o registro de imagens e implantar uma rede privada
virtual de acesso remoto (VPN) são desenhos adicionais, fora desta topologia.

## Artefatos e disponibilidade

| Artefato | Uso |
| --- | --- |
| [Bicep L300](../../infra/l300.bicep) e [parâmetros](../../infra/levels/l300.bicepparam) | Definição por fases, com destinos recebidos por parâmetro |
| [Módulos L300](../../infra/modules) | Rede, fonte, endpoints, ambiente, conexões e guardas |
| [Aplicação L200](../../infra/modules/l200-aplicacao.bicep) | Base da imagem, identidade, autenticação e verificações de saúde |
| [Sonda interna pública](../../scripts/sonda_l300.py) | Uma etapa por execução dentro da rede; resultado reduzido a códigos, contagens e invariantes |
| [Montador do contexto](../../scripts/montar_contexto_sonda_l300.py), [Dockerfile](../../infra/sonda-l300/Dockerfile) e [lista de permissão](../../infra/sonda-l300/dockerignore) | Preparação offline de uma pasta própria para a imagem da sonda, derivada do chat |
| [Gerenciador de ingestão L300](../../scripts/gerenciar_ingestao_l300.py) | Ferramenta que a sonda chama com identidade gerenciada; alterações somente no namespace L300 |
| [Sonda externa do chat](../../scripts/sonda_http_externa_l300.py) e [negativas externas](../../scripts/sonda_negativas_externas_l300.py) | Coleta fora da rede, descrita no [Desafio 06](06-conferir-operacao.md#etapa-2-preparar-as-provas-azure) |
| [Operação L300](../../scripts/operar_l300.py) | Conferência local do descritor; não implanta o Job nem coleta as provas |
| [Testes de infraestrutura](../../tests/test_infra_l300.py) | Compilação e guardas locais |
| [Testes da sonda](../../tests/test_sonda_l300.py) e [do contexto](../../tests/test_montar_contexto_sonda_l300.py) | Contratos, dublês e conferência dos arquivos permitidos, sem Azure |
| [Roteiro L300](../../docs/roteiro-l300.md) | Critérios, custos e fronteiras |

As definições e a integração são conferidas localmente. Um plano Azure real exige assinatura,
destinos e permissões aprovados. A rodada autorizada conferiu planos e efeitos reais,
separados das definições locais no [registro Azure](../../docs/validacao/l300-azure-validacao.md).
As ferramentas públicas derivam dos helpers privados validados no Azure naquela rodada.
As versões públicas foram conferidas por testes locais com dublês; os comandos desta receita
foram verificados na ajuda offline da Azure CLI 2.89.0, interface de linha de comando do Azure,
não executados no Azure nesta revisão.

## Tecnologias e conceitos

**Azure Private Link** permite conectar a um serviço por um **endpoint privado**, interface com
endereço na rede do consumidor. **DNS**, sistema de nomes de domínio, traduz o nome usado pela
aplicação para esse endereço [1].
Os endereços usam o protocolo de internet (IP). **HTTP**, protocolo de transferência de hipertexto,
é usado na comunicação web; **HTTPS** acrescenta proteção à conexão.
A sonda confere faixas de **IPv4**, versão 4 do protocolo IP, definidas na **RFC 1918**,
especificação da série *Request for Comments* sobre endereços de uso privado.
**Embeddings** são vetores numéricos dos textos, calculados pelo modelo de representação.

**Azure Container Apps** usa uma rede definida na criação do ambiente. O tipo de rede não pode
ser trocado depois. No ambiente com perfis de carga (*workload profiles*), a sub-rede deve ser
dedicada, delegada a `Microsoft.App/environments` e ter tamanho compatível, no mínimo `/27` [2][3].
Um endereço de rede em notação `/27` identifica um bloco; o projeto de endereçamento também
precisa considerar intervalos reservados e redes já conectadas.

A busca é um serviço separado da rede da aplicação. O indexador precisa de **conexões privadas
compartilhadas**, chamadas *shared private links*, para sua saída ao armazenamento e ao modelo [4].
O endpoint privado de entrada do Search protege a consulta recebida, não essa saída.

Um **Container Apps Job** executa uma tarefa finita e termina; neste exercício, cada execução faz
uma única etapa da sonda. Ele compartilha rede e coleta de logs com o ambiente, sem hospedar outro
servidor web [7]. **Identidade gerenciada atribuída ao usuário** é um recurso independente que pode
ser associado ao chat e ao Job; apagar o Job não apaga essa identidade [8].
**RBAC**, controle de acesso baseado em papéis, concede operações em um escopo definido [9].
Papéis de dados, de administração dos recursos e de uso do chat são autorizações distintas.

## Pré-requisitos

Abra o projeto no Visual Studio Code (VS Code), use PowerShell 7 e o Bicep CLI fornecido pela
Azure CLI, interface de linha de comando do Azure. Os testes de infraestrutura precisam do compilador
local, mas não de login.
CLI significa interface de linha de comando também no nome Bicep CLI.
Confira a versão 0.48.1 ou superior. Compiladores distintos no PATH e na configuração da Azure CLI
podem ter versões diferentes; o helper local escolhe o mais recente entre os caminhos conhecidos.

Para executar a topologia, confirme grupo, região, nomes, configurações reais, plano de IPs e
assinatura ativa, além de permissões de criação e aprovação de conexões. Permissão de dados da aplicação não concede
aprovação de endpoints privados.

Para a receita das sondas, tenha também Python e as dependências L300 em `.venv`, imagem atual
do chat L300, registro de imagens e acesso de leitura aos logs. **ACR**, Azure Container Registry,
é o registro; **ACR Tasks** realiza a construção remota, chamada *build* [11].
Criar ou associar identidades e atribuir papéis exige autorização explícita de quem administra
o tenant, diretório de identidades, e a assinatura. Um login bem-sucedido não comprova essas
permissões nem acesso aos dados. Autorize separadamente a construção, o Job e cada alteração da fonte
ou do índice. A autorização histórica não permite repetir a rodada.

A camada da busca depende das habilidades e da disponibilidade da região. A documentação atual
admite vetorização integrada em Basic ou superior em regiões de alta capacidade e serviços criados
após 3 de abril de 2024 [4]. Confira sua composição antes de escolher ou alterar a camada.

## Etapa 1: mapear os caminhos

1. Liste consulta, ingestão, implantação e manutenção.
2. Identifique a identidade e a rede de cada caminho.
3. Marque o que deve permanecer público e o que será fechado.

| Caminho | Conectividade e identidade |
| --- | --- |
| Pessoa → chat | HTTPS e login; autorização documental no servidor |
| Chat → busca e modelos | Nova rede Container Apps, endpoints e identidade gerenciada |
| Indexador → Blob e embeddings | Conexões compartilhadas aprovadas e ambiente de execução privado |
| Operação → plano de controle | Identidade administrativa proporcional à fase |
| Carga e conferência → dados | Executor autorizado dentro da rede ou conectividade equivalente |
| Aplicação → registro de imagens Basic | Endereço público autenticado e papel de download, sem senha de administrador |

**Resultado esperado:** nenhum caminho necessário foi omitido. Um runner, computador executor,
hospedado fora da rede pode administrar a implantação e ainda não conseguir ler os dados privados.

### Prompt para o Copilot: analisar a conectividade

Anexe este guia, o Bicep L300, seus módulos e o pipeline:

```text
Explique os caminhos de consulta e de ingestão da topologia L300.
Identifique endpoints de entrada, conexões de saída, DNS e identidades.
Mostre o que permanece público e os custos adicionais.
Não trate um endpoint privado no Search como prova de ingestão privada.
Não implante, aprove conexões, altere acesso público ou amplie papéis.
```

**Conferência:** a resposta deve mencionar o novo ambiente, as conexões compartilhadas da busca
e a aprovação no armazenamento e nos modelos.

## Etapa 2: compilar e revisar a topologia

A compilação só usa arquivos locais:

```powershell
az bicep lint --file infra\l300.bicep
az bicep build --file infra\l300.bicep --stdout
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_infra_l300.py
```

**Resultado esperado:** lint sem avisos, build com código zero e testes aprovados.
Confira os resultados; o lint pode terminar com código zero mesmo exibindo avisos.
Para obter plano e compilação pelo helper local, sem parâmetros reais:

```powershell
.\.venv\Scripts\python.exe scripts\operar_l300.py --etapa plano --fase rede --validar-bicep
```

Revise as fases:

| Fase | Recursos e efeito |
| --- | --- |
| `rede` | Preparar rede, DNS, endpoints, contêiner L300 e conexões; conservar o acesso público existente |
| `aplicacao` | Criar a aplicação L300 com identidade e autorização; ingresso inicial fechado |
| `isolar` | Fechar o acesso público dos dados após evidências e autorização |

As fases são exclusivas: `aplicacao` e `isolar` referenciam os recursos das fases anteriores.
Use implantação incremental. O modo completo pode remover recursos que a fase escolhida
não declara.

O arquivo de parâmetros recebe a configuração por variáveis da sessão ou do workflow:

| Quando | Variáveis |
| --- | --- |
| Toda fase | `VARELEIRA_NOME_CONTA`, `VARELEIRA_NOME_BUSCA`, `VARELEIRA_NOME_MODELOS`, `VARELEIRA_NOME_REGISTRO`, `VARELEIRA_NOME_IDENTIDADE_APLICACAO`, `VARELEIRA_NOME_WORKSPACE_LOGS` e `VARELEIRA_ID_OBJETO_CARGA` |
| Controle | `VARELEIRA_L300_FASE`, `VARELEIRA_L300_INGRESSO_EXTERNO` e `VARELEIRA_L300_CONECTIVIDADE_PRIVADA_VALIDADA` |
| `aplicacao` | `VARELEIRA_TAG_IMAGEM`, `VARELEIRA_ID_APLICACAO_LOGIN`, `VARELEIRA_ID_TENANT_LOGIN` e segredo efêmero `VARELEIRA_SEGREDO_LOGIN` |
| `isolar` | `VARELEIRA_SKU_ARMAZENAMENTO`, `VARELEIRA_SKU_BUSCA`, `VARELEIRA_REPLICAS_BUSCA` e `VARELEIRA_PARTICOES_BUSCA`, com valores atuais |
| Regiões diferentes da região do grupo | `VARELEIRA_LOCALIZACAO_ARMAZENAMENTO`, `VARELEIRA_LOCALIZACAO_BUSCA` e `VARELEIRA_LOCALIZACAO_MODELOS` |

Os nomes identificam a configuração privada; os valores permanecem fora do repositório.
Leia as descrições do Bicep para parâmetros adicionais, como endereço de rede e etiquetas.
**Atenção:** `build-params --stdout` pode imprimir o segredo lido da sessão. Compile o template
para conferir tipos; a compilação de parâmetros com valores reais exige captura privada.

A fase `isolar` reaplica a configuração da base deste laboratório. Camada, réplicas, partições
e redundância são comparadas com os serviços existentes; etiquetas adicionais devem ser preservadas
explicitamente. Se a configuração tiver evoluído fora do laboratório, reveja o módulo antes de aplicar.
Confira o plano `what-if`, previsão calculada pelo Azure Resource Manager (ARM), antes da aplicação [5].

## Etapa 3: aprovar conexões e produzir evidências

Esta é a receita pública revisada para um destino **explicitamente autorizado**. Prepare os passos
no terminal PowerShell do VS Code, a partir da raiz do projeto, e execute-os separadamente.
Confira `$LASTEXITCODE` imediatamente após cada chamada; uma falha impede a próxima alteração.
O roteiro não cria recursos por si e não oferece simulação de criação do Job ou do build remoto:
revise alvos, configuração, contexto e custo antes de autorizar esses comandos.

Recupere os valores do inventário privado, sem colá-los no Copilot ou em arquivos versionados:

| Variáveis da sessão | O que devem identificar |
| --- | --- |
| `$assinatura`, `$grupo`, `$regiao`, `$conta`, `$busca`, `$modelos` | Destino aprovado e serviços reaproveitados |
| `$registro`, `$servidorRegistro`, `$idRegistro`, `$idBusca`, `$idModelos` | ACR, seu servidor e IDs completos dos recursos, conferidos no inventário |
| `$nomeIdentidade`, `$nomeManutencao`, `$nomeAmbiente`, `$job` | Identidade existente do chat, identidade temporária de manutenção, ambiente L300 e nome novo do Job |
| `$imagemChat`, `$imagemSonda`, `$contextoSonda` | Referência completa da imagem atual do chat; repositório e tag nova da sonda; pasta nova ou vazia escolhida para o contexto |
| `$urlChat`, `$idLogin` | Endereço oficial HTTPS do chat e ID de aplicativo do seu registro de login, para `http-interno` |

Uma **tag** identifica a versão da imagem. `$imagemChat` tem a forma
`<registro>.azurecr.io/<repositorio-do-chat>:<tag-do-chat>`; `$imagemSonda`,
`<repositorio-da-sonda>:<tag-nova>`. Use uma tag identificável, nunca `latest`, e confira que ela
ainda não foi usada. Reutilize o registro e o processo de construção, não a imagem anterior ao L300:
ela não contém a autorização documental.

### 1. Preparar identidades, papéis e conexões

**Objetivo:** separar manutenção, chat e ingestão, antes de atribuir qualquer permissão.
**[altera o Azure]** ao criar identidade, conceder papéis, implantar a fase `rede` ou aprovar conexões.

1. Quem administra confere propriedade, consumidores e ausência de conflito de nomes. Uma
   identidade existente pode ser reaproveitada somente com autorização de seu responsável.
2. Se uma identidade de manutenção **nova e temporária** foi autorizada, o administrador executa:

```powershell
az identity list --subscription $assinatura --resource-group $grupo --output json
```

Confira a ausência do nome escolhido na listagem antes da criação; uma coincidência interrompe
o procedimento. A criação autorizada e a leitura da identidade do chat são ações separadas:

```powershell
$manutencaoJson = az identity create --subscription $assinatura --resource-group $grupo --name $nomeManutencao --location $regiao --output json
if ($LASTEXITCODE -ne 0) { throw "A identidade de manutenção não foi criada." }
$manutencao = $manutencaoJson | ConvertFrom-Json
$chatJson = az identity show --subscription $assinatura --resource-group $grupo --name $nomeIdentidade --output json
if ($LASTEXITCODE -ne 0) { throw "A identidade existente do chat não foi conferida." }
$identidadeChat = $chatJson | ConvertFrom-Json
```

Para manutenção reaproveitada, use a leitura `az identity show` com seu nome autorizado em vez
da criação. Confira os três identificadores; eles **não são intercambiáveis**:

| Propriedade da identidade | Uso |
| --- | --- |
| `id` | ID do recurso Azure; associação ao Job e autenticação do registro |
| `principalId` | ID de objeto no Entra ID; atribuições RBAC e `principalIdCarga` do Bicep |
| `clientId` | Seleção da identidade que o processo usa, por `VARELEIRA_PROBE_CLIENT_ID` |

3. Informe **a identidade de manutenção** como responsável pela carga da fase `rede`:

```powershell
$env:VARELEIRA_ID_OBJETO_CARGA = $manutencao.principalId
```

**Atenção:** `tipoPrincipalCarga` deve ser `ServicePrincipal` para essa identidade gerenciada.
O Bicep principal assume `User` por padrão, e o arquivo de parâmetros versionado não expõe esse
tipo por variável. O administrador precisa informar `ServicePrincipal` explicitamente nos parâmetros
revisados da implantação da fase `rede`; definir apenas a variável acima não resolve essa diferença.
Na cópia privada de parâmetros aprovada para essa implantação, a declaração correspondente é:

```bicep
param tipoPrincipalCarga = 'ServicePrincipal'
```

Não aplique o padrão `User` para a identidade de manutenção nem mude o principal de uma carga
preexistente sem revisar seus consumidores.

O [módulo da fonte](../../infra/modules/l300-fonte-documental.bicep) cria **somente no contêiner
`base-documental-l300`** dois papéis: `Storage Blob Data Reader` para a identidade do serviço de busca
e `Storage Blob Data Contributor` para `principalIdCarga`. Essa é a permissão de escrita da manutenção;
não acrescente escrita na conta inteira. A fase `rede` não cria a identidade de manutenção nem
concede seus outros quatro papéis. A identidade da busca deve estar habilitada na base L200.

4. O administrador confere as atribuições atuais, guarda a linha de base em local privado e
   concede à manutenção somente o que estiver ausente e autorizado [9]:

```powershell
az role assignment list --subscription $assinatura --assignee-object-id $manutencao.principalId --all --fill-principal-name false --output json
```

| Papel temporário da manutenção | Escopo exato |
| --- | --- |
| `AcrPull` | Registro de imagens próprio, `$idRegistro` |
| `Search Service Contributor` | Serviço de busca próprio, `$idBusca`; administração dos objetos da ingestão |
| `Search Index Data Contributor` | Mesmo serviço de busca; acesso aos dados do índice |
| `Cognitive Services OpenAI User` | Recurso de modelos próprio, `$idModelos` |

O bloco a seguir é a referência **para quatro atribuições novas**, depois dessa revisão.
Se alguma já existir, preserve-a e prepare somente as concessões faltantes; não duplique nem
substitua atribuições. Registre imediatamente cada ID criado no inventário privado da atividade.

```powershell
$concessoes = @(
    @{ Papel = "AcrPull"; Escopo = $idRegistro }
    @{ Papel = "Search Service Contributor"; Escopo = $idBusca }
    @{ Papel = "Search Index Data Contributor"; Escopo = $idBusca }
    @{ Papel = "Cognitive Services OpenAI User"; Escopo = $idModelos }
)
$idsAtribuicoesNovas = @()
foreach ($concessao in $concessoes) {
    $idNovo = az role assignment create --subscription $assinatura --assignee-object-id $manutencao.principalId --assignee-principal-type ServicePrincipal --role $concessao.Papel --scope $concessao.Escopo --query id --output tsv
    if ($LASTEXITCODE -ne 0 -or -not $idNovo) { throw "A concessão falhou; confira os efeitos anteriores antes de continuar." }
    $idsAtribuicoesNovas += $idNovo
}
```

Esses papéis RBAC não são os papéis documentais `Vareleira.Atendimento` e `Vareleira.Corretor`.
Na busca, o escopo das concessões é o serviço; o namespace L300 é uma restrição da ferramenta,
não uma fronteira criada por esses papéis. Restrinja quem pode iniciar ou trocar a imagem do Job.
Conserve a identidade do chat com seus papéis anteriores de download, leitura da busca e uso dos
modelos. Ela também será associada ao Job, para `negativas-mi` e `http-interno`, sem receber
privilégios de manutenção.
Para `http-interno` com perfil Atendimento, o administrador do tenant deve conferir também a
atribuição do papel de **aplicação** correspondente à identidade usada no token do chat.
Esse acesso exige autorização própria; associar a identidade ao Job não o concede.

5. Aplique somente a fase `rede` autorizada, conservando a configuração pública atual. Confira
   destino, sub-recurso e origem das conexões pendentes; o administrador aprova somente as próprias.
   A aprovação do *shared private link*, conexão privada compartilhada, ocorre no recurso de destino [4].
   Depois, leia as conexões administradas pela busca:

```powershell
az search shared-private-link-resource list --subscription $assinatura --resource-group $grupo --service-name $busca --output json
az search shared-private-link-resource show --subscription $assinatura --resource-group $grupo --service-name $busca --name $nomeLink --output json
```

`$nomeLink` vem da conexão própria identificada na listagem; repita a leitura para armazenamento
e modelos. Confira **`Approved` e provisionamento `Succeeded`**, além do destino correto.
Nenhuma etapa da sonda coleta esses estados. A disposição dos campos pode variar entre a CLI
e a resposta ARM, serviço de administração Azure; interprete o objeto lido, sem presumir aprovação.
O grupo `openai_account` foi aceito com o recurso `AIServices` reaproveitado na rodada histórica,
com embeddings privados conferidos. Isso não garante outras regiões ou configurações.
Mudar para `foundry_account` exige rever habilidade, suporte e camada [4], sem troca por tentativa.

**Resultado esperado:** identidades distintas, quatro concessões de manutenção no recurso exato,
escrita somente no contêiner L300 e duas conexões aprovadas.
**Autorização, custo e limpeza:** os administradores autorizam criação, associação, concessões e
aprovações; essas ações não chamam modelos, mas a rede e os serviços preparados têm cobrança.
Registre os objetos novos, responsáveis e prazo; retire somente os temporários no encerramento
do [Desafio 07](07-recuperar-limpar.md), depois de conferir seus consumidores.

### 2. Montar o contexto e construir a imagem da sonda

**Objetivo:** enviar somente os arquivos permitidos e reutilizar os mesmos módulos do chat.
Antes da fase `aplicacao`, construa a imagem atual do código L300 pelo
[procedimento de construção L200](../L200/05-hospedar-chat.md#etapa-1-publicar-a-imagem).
Use esse procedimento somente para construir a imagem, não para reaplicar infraestrutura anterior
sobre serviços isolados.

1. Escolha `$contextoSonda` como pasta nova ou vazia, separada da raiz usada para o build do chat.
2. Execute o montador local, que não acessa rede, Azure ou Docker:

```powershell
.\.venv\Scripts\python.exe scripts\montar_contexto_sonda_l300.py --destino $contextoSonda --registro $registro --imagem-chat $imagemChat --imagem-sonda $imagemSonda
if ($LASTEXITCODE -ne 0) { throw "O contexto da sonda não foi aprovado." }
```

Ele confere 12 arquivos da lista fechada, mais `Dockerfile` e `.dockerignore`: ferramenta de
ingestão e módulos adicionais, inventário, manifesto e as quatro fontes sintéticas aprovadas.
Inclui também `gerar_carga_l400.py`, cuja prática está no
[Desafio 06 do L400](../L400/06-testar-carga-interrupcao.md).
Cada cópia tem seu hash SHA-256, impressão digital calculada pelo algoritmo Secure Hash Algorithm
de 256 bits, conferido contra a origem. Os módulos do chat vêm da imagem-base.

3. Revise o comando impresso. **[altera o Azure]**, somente após autorizar envio, build e publicação:

```powershell
az acr build --subscription $assinatura --registry $registro --image $imagemSonda --build-arg "IMAGEM_CHAT=$imagemChat" --file Dockerfile $contextoSonda
if ($LASTEXITCODE -ne 0) { throw "Confira o estado remoto do build antes de autorizar uma repetição." }
```

É o comando de referência do montador, com assinatura explícita. O **último argumento é a pasta
própria do contexto**; `--file Dockerfile` é relativo a ela. Na rodada histórica, um contexto errado
selecionou o Dockerfile da raiz, pertencente ao chat; não repita o build sem conferir o run anterior.
O valor de `--build-arg` é visível à equipe de suporte do ACR, conforme sua ajuda: use somente
a referência da imagem, nunca segredo ou token.
O Dockerfile deriva de `IMAGEM_CHAT`, sem valor padrão, conserva o usuário sem privilégios de
administrador (*root*) e executa `validar` durante a construção.

4. Confira o build por **leituras**, no terminal privado:

```powershell
az acr task list-runs --subscription $assinatura --registry $registro --output json
$digestSonda = az acr repository show --subscription $assinatura --name $registro --image $imagemSonda --query digest --output tsv
if ($LASTEXITCODE -ne 0 -or -not $digestSonda) { throw "A imagem da sonda não foi conferida no registro." }
```

Associe o run, execução do build, à tag e ao horário corretos; procure estado `Succeeded`, a etapa
`validar` aprovada e o **digest**, resumo criptográfico da imagem publicada.
O encerramento do comando no computador não substitui essa leitura do resultado remoto.

**Resultado esperado:** contexto com exatamente 14 arquivos e imagem nova, derivada da revisão
L300 do chat, com validação local aprovada no build.
**Autorização, custo e limpeza:** a montagem usa apenas arquivos locais; construir e guardar a imagem
consome ACR Tasks e armazenamento [11]. A sonda contém cópias das fontes sintéticas; restrinja seu
download. Retire a pasta de contexto quando ela não for mais necessária, sem tocar nos originais;
retire somente a imagem própria depois dos consumidores, conforme o Desafio 07.

### 3. Criar um Job manual no ambiente L300

**Objetivo:** executar a sonda no caminho de rede dos dados, com duração e recursos delimitados.
**[altera o Azure]** ao criar o Job e associar as duas identidades.

1. Confira que `$nomeAmbiente` é o ambiente L300 integrado à rede, não o ambiente anterior.
   “Dentro da rede” descreve o caminho dos dados; o Bicep mantém o ambiente com entrada externa
   e a aplicação inicialmente com ingresso interno. Criar o Job não abre o ingresso do chat.
2. Confira que o nome `$job` está livre; prepare a configuração somente na sessão:

```powershell
az containerapp job list --subscription $assinatura --resource-group $grupo --output json
$imagemSondaCompleta = "$servidorRegistro/$imagemSonda"
$variaveisBase = @(
    "VARELEIRA_PROBE_CONTA=$conta"
    "VARELEIRA_PROBE_BUSCA=$busca"
    "VARELEIRA_PROBE_MODELOS=$modelos"
    "VARELEIRA_PROBE_ASSINATURA=$assinatura"
    "VARELEIRA_PROBE_GRUPO=$grupo"
    "VARELEIRA_PROBE_CLIENT_ID=$($manutencao.clientId)"
    "VARELEIRA_PROBE_ESPERA_SEGUNDOS=600"
    "VARELEIRA_PROBE_LIMITE_SEGUNDOS=840"
    "VARELEIRA_PROBE_DEPLOYMENT_EMBEDDINGS=embeddings"
    "VARELEIRA_PROBE_DEPLOYMENT_GERACAO=geracao"
    "VARELEIRA_PROBE_DIMENSOES=1536"
    "VARELEIRA_PROBE_ESFORCO=low"
    "VARELEIRA_PROBE_GERACAO=sim"
)
```

3. Após revisão e autorização, crie o Job [12]:

```powershell
az containerapp job create --subscription $assinatura --resource-group $grupo --name $job `
    --environment $nomeAmbiente --workload-profile-name Consumption --trigger-type Manual `
    --replica-timeout 900 --replica-retry-limit 0 --replica-completion-count 1 --parallelism 1 `
    --container-name sonda --image $imagemSondaCompleta --cpu 0.25 --memory 0.5Gi `
    --mi-user-assigned $manutencao.id $identidadeChat.id `
    --registry-server $servidorRegistro --registry-identity $manutencao.id `
    --env-vars @variaveisBase "VARELEIRA_PROBE_ETAPA=validar" --output none
if ($LASTEXITCODE -ne 0) { throw "A criação do Job falhou; confira os efeitos antes de continuar." }
```

O perfil **Consumption** cobra a execução por consumo. A referência usa 0,25 **vCPU**, fração de
um núcleo virtual de processamento, e 0,5 **GiB**, gibibyte de memória, uma réplica, gatilho `Manual`,
zero tentativas automáticas e limite de 900 segundos [7]. Não há agenda.
O Job baixa a imagem pela identidade de manutenção, com `AcrPull`, sem senha do registro.
A ajuda de `--registry-identity` avisa que a CLI pode criar uma atribuição `AcrPull` automaticamente;
essa possível concessão também precisa estar coberta pela autorização e pelo inventário.
Conferir o papel antecipadamente não dispensa conferir os efeitos da criação.

**Atenção aos três relógios:** espera do indexador, limite da sonda e limite da réplica.
Esta receita escolhe **600 < 840 < 900 segundos**, deixando margem para a sonda emitir o resultado.
São escolhas de configuração, não uma medição de desempenho. A espera padrão da ferramenta é
900 segundos; usá-la com uma réplica também limitada a 900 pode interromper a sonda antes da linha.
Se precisar ampliar o prazo, revise custo e autorização; a sonda aceita espera de 10 a 1.500 segundos
e limite próprio de 30 a 1.750. Não retire os limites nem habilite repetição automática.

4. Leia a definição criada e compare ambiente, imagem, identidades, registro, variáveis e limites:

```powershell
az containerapp job show --subscription $assinatura --resource-group $grupo --name $job --output json
```

**Resultado esperado:** Job manual no ambiente correto, duas identidades associadas e download
por identidade, sem segredo. Nenhuma etapa foi iniciada pela criação.
**Autorização, custo e limpeza:** exige permissão para criar o Job e associar ambas as identidades,
além da aprovação de seus proprietários. Cada execução e seus logs têm custo; rede, registro e
serviços continuam cobrados separadamente. Remova o Job somente após sua última operação necessária.

### 4. Iniciar uma etapa por execução

**Objetivo:** manter o efeito de cada etapa distinguível. **[altera o Azure]** ao iniciar uma execução
do Job; o conteúdo da etapa pode ser somente leitura ou alterar dados, conforme a tabela adiante.

`VARELEIRA_PROBE_CLIENT_ID` seleciona **qual** identidade associada o processo usa: manutenção
nas etapas de dados; chat em `negativas-mi` e, nesta receita, `http-interno`.
As variáveis `VARELEIRA_PROBE_*` são configuração privada, não segredos.
Confirme as exigências de cada etapa:

| Etapa | Sufixos obrigatórios de `VARELEIRA_PROBE_` |
| --- | --- |
| `dns` | `CONTA`, `BUSCA`, `MODELOS` |
| `carregar`, `excluir`, `restaurar` | `CONTA`, `CLIENT_ID` da manutenção |
| `criar`, `conferir` | `CONTA`, `BUSCA`, `ASSINATURA`, `GRUPO`, `MODELOS`, `CLIENT_ID` da manutenção |
| `executar`, `resumo` | `BUSCA`, `CLIENT_ID` da manutenção |
| `acesso` | `BUSCA`, `MODELOS`, `CLIENT_ID` da manutenção |
| `negativas-mi` | `ASSINATURA`, `GRUPO`, `CONTA`, `BUSCA`, `CLIENT_ID` do chat |
| `http-interno` | `URL`, `APP_ID` do registro de login, `CLIENT_ID` do chat; confira também `PERFIL` |
| `validar` | Nenhum; `--exigir-configuracao` ou `EXIGIR_CONFIGURACAO=sim` exige os seis destinos básicos |

`DOCUMENTO_AUSENTE=VLAR-OP-ATD-1.0` só é usado na conferência após uma exclusão autorizada.
`GERACAO=nao` desativa a geração da etapa `acesso`, mas não seus embeddings.
`http-interno` aceita perfis `atendimento`, `corretor`, `ambos` e `sem-acesso`; mudar a variável
não muda o papel real da identidade. A URL, endereço do recurso, deve ser HTTPS no domínio
`*.azurecontainerapps.io`; domínio personalizado não é aceito.
Conserve os deployments, instâncias nomeadas dos modelos, e as 1.536 dimensões do L300.

1. Escolha uma única etapa. Refaça **toda** a lista de variáveis necessária a ela, em cada início.
   Para `dns`, por exemplo:

```powershell
$etapa = "dns"
$variaveisEtapa = $variaveisBase + @("VARELEIRA_PROBE_ETAPA=$etapa")
az containerapp job start --subscription $assinatura --resource-group $grupo --name $job `
    --container-name sonda --image $imagemSondaCompleta --cpu 0.25 --memory 0.5Gi `
    --env-vars @variaveisEtapa --output json
if ($LASTEXITCODE -ne 0) { throw "O início falhou; confira se uma execução foi criada antes de repetir." }
```

2. Para `negativas-mi`, reconstrua a lista, trocando somente a seleção de identidade e a etapa:

```powershell
$etapa = "negativas-mi"
$variaveisEtapa = @($variaveisBase | Where-Object { $_ -notlike "VARELEIRA_PROBE_CLIENT_ID=*" }) + @(
    "VARELEIRA_PROBE_CLIENT_ID=$($identidadeChat.clientId)"
    "VARELEIRA_PROBE_ETAPA=$etapa"
)
```

Use essa lista no **mesmo comando de início**, uma vez, e confira seu resultado antes de outra etapa.
Para `http-interno`, reconstrua-a a partir da base, com a identidade do chat, a etapa correspondente
e estes três valores adicionais:

```powershell
$etapa = "http-interno"
$variaveisEtapa = @($variaveisBase | Where-Object { $_ -notlike "VARELEIRA_PROBE_CLIENT_ID=*" }) + @(
    "VARELEIRA_PROBE_CLIENT_ID=$($identidadeChat.clientId)"
    "VARELEIRA_PROBE_ETAPA=$etapa"
    "VARELEIRA_PROBE_URL=$urlChat"
    "VARELEIRA_PROBE_APP_ID=$idLogin"
    "VARELEIRA_PROBE_PERFIL=atendimento"
)
```

**Limite da conferência da CLI:** a ajuda offline confirma `--env-vars`, `--args`, `--command`
e `--image` no início. Ela não comprova como a CLI combina a lista de variáveis com a definição
existente. A documentação avisa que substituir o template de execução pode substituir sua
configuração inteira [7]. **Se `--env-vars` substitui ou combina a lista neste caminho da CLI
não foi validado nesta rodada.** Por prudência, informe a lista completa em cada início,
preserve imagem e recursos, e confira a definição da execução. Não use só a variável da etapa
esperando herança implícita. O exemplo conserva o ponto de entrada da imagem, sem trocar
`--command` ou `--args`. A rodada histórica iniciou as execuções por REST (*Representational State
Transfer*), estilo de interface web baseado em recursos, não por estes comandos públicos.

**Resultado esperado:** uma execução identificada, com a etapa e a identidade previstas.
**Autorização, custo e limpeza:** autorize o início e o efeito da etapa antes de executar.
`carregar`, `criar`, `executar`, `excluir` e `restaurar` efetivamente alteram dados ou objetos,
pois a sonda passa `--executar` à CLI de ingestão. Chamar a ferramenta não substitui a autorização
administrativa, e ela não oferece simulação dessas etapas.
Use os planos do [Desafio 02](02-atualizar-base.md#etapa-2-preparar-carga-e-indexador-separados)
antes da autorização, num executor com caminho privado; essas simulações leem o Azure.
Permissão para iniciar o Job permite usar suas identidades e trocar comandos ou imagem [7]:
limite esse acesso a operadores confiáveis. Espere a conclusão e colete a prova antes de repetir;
remova os objetos temporários no encerramento, não durante uma execução.

### 5. Ler conclusão e resultado, separadamente

**Objetivo:** confirmar tanto o término da execução quanto o conteúdo da prova.
Estas chamadas **só leem o Azure**:

```powershell
az containerapp job execution list --subscription $assinatura --resource-group $grupo --name $job --output json
az containerapp job execution show --subscription $assinatura --resource-group $grupo --name $job --job-execution-name $nomeExecucao --output json
```

1. Identifique `$nomeExecucao` na resposta do início ou na listagem, pelo nome e horário privados.
   Confira estado final, contêiner, imagem e variáveis efetivamente enviados; aceite apenas o
   resultado da execução correspondente. Iniciar com sucesso não é concluir com sucesso.
2. No portal Azure, abra o workspace de logs do ambiente L300 em **Logs**, selecione uma janela
   que cubra essa execução e procure a linha iniciada por `L300_SONDA_RESULTADO=` nos logs de
   console. A documentação oficial confirma a tabela `ContainerAppConsoleLogs_CL` e as colunas
   `TimeGenerated` e `Log_s` para esse destino de logs [10]. Confira os campos realmente presentes
   para associar Job, execução e réplica; não suponha que um campo de revisão da aplicação
   identifique uma execução do Job.
3. Guarde os logs brutos e essa associação somente em local privado. A coleta correlacionada
   precisa ser conferida no seu workspace. **A leitura de logs pela CLI ficou pendente:** as duas
   superfícies de consulta tentadas não estavam disponíveis na instalação usada para a ajuda
   offline. Este guia não publica comando de extensão ou consulta KQL (*Kusto Query Language*),
   linguagem de consultas Kusto, não verificados. Sem recuperar a linha e associá-la à execução,
   a prova permanece pendente.
4. Leia o JSON, formato JavaScript Object Notation de dados estruturados, depois do prefixo.
   A sonda emite uma única linha, sem outro texto em saída padrão ou de erro, com chaves ordenadas
   e caracteres ASCII, conjunto básico de caracteres. Confira `v`, `sonda`, `etapa`, `veredicto`,
   `codigo`, `causa`, `dados` e `duracao_s`. `$linha` abaixo contém a linha recuperada, não uma
   declaração escrita pelo operador:

```powershell
$prefixo = "L300_SONDA_RESULTADO="
if (-not $linha.StartsWith($prefixo)) { throw "Falta a linha de resultado da execução." }
$resultado = $linha.Substring($prefixo.Length) | ConvertFrom-Json
if ($resultado.v -ne 1 -or $resultado.sonda -ne "l300" -or $resultado.etapa -ne $etapa) {
    throw "O resultado não corresponde à sonda, à versão ou à etapa escolhida."
}
if ($resultado.codigo -ne 0 -or $resultado.veredicto -ne "aprovado") {
    throw "A sonda não aprovou a etapa; preserve a causa e a pendência ou falha."
}
```

| Código de decisão | Interpretação |
| --- | --- |
| `0` | Etapa aprovada; confira também os dados exigidos pela prova |
| `1` | Uso ou configuração inválidos |
| `2` | Acesso, rede, serviço ou prazo impediram concluir |
| `3` | Divergência: etapa reprovada |
| `4` | Defeito ou saída bloqueada |

O estado **`Succeeded` do Job não prova aprovação**. O veredicto e o código devem ser lidos da
linha efetivamente emitida. Exija conclusão compatível, linha válida da etapa certa,
`veredicto=aprovado`, `codigo=0` e os fatos exigidos para cada campo do descritor.
A serialização reduz valores fora do vocabulário a marcadores; a barreira final procura padrões
de URL, identificador, token, IP, host e valores privados da configuração. Se detectar um deles,
substitui a linha por `saida_bloqueada`, com código `4`; o processo também termina com código
de saída `4`, sempre coerente com a linha emitida. Se a própria barreira falhar, a linha informa
`saida_invalida`, também com saída `4`. Um Job `Succeeded` sem linha válida, ou com
`saida_bloqueada`, **não é aprovação**.
Um nome de recurso igual a uma palavra do vocabulário pode provocar esse bloqueio.
Não desligue a barreira nem publique a saída bruta para diagnosticar.

**Resultado esperado:** cada prova tem execução, etapa, identidade, origem e resultado associados,
sem nomes ou IDs do ambiente no registro público.
**Autorização, custo e limpeza:** requer leitura da execução e dos logs; a coleta não muda dados,
mas ingestão, consulta e retenção de logs podem ter cobrança. Publique somente campos do vocabulário
fechado; conserve a proveniência privada pelo prazo aprovado e retire as cópias quando ele terminar.

### 6. Escolher a sequência antes e depois do isolamento

**Objetivo:** provar cada caminho antes de fechar o acesso público, sem confundir consulta,
ingestão e privilégio.

| Ordem e etapa, uma execução por vez | Quando usar e resultado esperado | Efeito e custo |
| --- | --- | --- |
| `validar` | No computador e no build; quatro fontes, módulos e manifesto conferem | Local, sem rede ou tokens |
| `dns` | Depois dos endpoints e aprovações; repetir após isolar. `dados.dns.blob/busca/modelos.todos_rfc1918=true` | Resolução dentro da rede; RFC 1918 identifica as faixas de endereços privados |
| `conferir` e `resumo` | Se o pipeline já existir, estabelecer o estado inicial; se não existir, registrar a ausência e conferir depois da criação | Leituras de objetos, classes, contagens e última execução |
| `acesso` | Depois de haver índice utilizável; repetir após isolar. Filtros corretos nos dois perfis e nos três modos; no máximo uma geração | Leituras, embeddings e, com `GERACAO=sim`, uma geração; consome tokens |
| `carregar` → `criar` → `executar` → `conferir`, depois `resumo` | Retorno ao Desafio 02 para primeira ingestão, ou manutenção autorizada; indexador privado e fontes/classes conferidos | **[altera o Azure]**: blobs e quatro objetos do namespace L300; indexação consome embeddings |
| `excluir` → `executar` → `conferir` → `restaurar` → `executar` → `conferir` | Somente para o ciclo operacional autorizado do Desafio 02; conferir ausência com `DOCUMENTO_AUSENTE` e retirar essa variável ao conferir a reposição | **[altera o Azure]**: somente cópia operacional L300 e reindexação; preservar fontes L100/L200 |
| `negativas-mi` | Com identidade do chat, dentro da rede funcional; três GETs, pedidos de leitura, devem dar 403 | Lê Blob original L100, administração de índices e conta no ARM; não mede isolamento externo |
| `http-interno` | Depois da fase `aplicacao` e do papel de aplicação; antes de abrir ingresso externo e novamente após isolar | Saúde/prontidão 200, anônimo/cabeçalho inventado 401 e uma consulta por perfil; no caminho autorizado, consome embeddings e uma geração |
| Negativas externas, no Desafio 06 | Preparar antes; executar depois de isolar, com operador autorizado fora da rede | Uma tentativa por serviço; não é a etapa `negativas-mi` |

Na primeira criação, a ausência de índice torna `conferir`, `resumo` e `acesso` ainda não atendidos;
faça carga e ingestão antes de exigir sua aprovação. Depois das alterações, repita as leituras e
o acesso, sem apagar a tentativa inicial.
As etapas de alteração chamam `gerenciar_ingestao_l300.py` com `--identidade-gerenciada`.
`dns`, `conferir`, `resumo`, `acesso`, `http-interno` e `negativas-mi` não modificam a fonte ou o índice.
Isso não torna `acesso` ou `http-interno` etapas sem consumo: ambas incluem chamadas aos modelos.
Em `http-interno`, a pergunta autenticada de um perfil autorizado usa embeddings e uma geração;
as verificações de saúde e prontidão, isoladamente, não chamam esses serviços.
As duas requisições sem identidade também enviam uma pergunta e devem receber `401`.
Se a borda as aceitar, o chat pode processá-las e consumir mais tokens; a etapa é reprovada.
Os nomes de serviços continuam oficiais; as zonas privadas mudam sua resolução nesse caminho.
Evite IP fixo no código ou edição de hosts como solução de produção [1].

**Lembre-se:** `resumo` pode aprovar classes e ainda mostrar indexador sem sucesso ou zero itens
processados. Leia os campos, não só o veredicto. Uma repetição idempotente pode processar zero
itens; preserve esse resultado. Se a prova exigir nova ingestão, autorize uma alteração operacional
ou o ciclo do Desafio 02, em vez de inventar contagens ou reprocessar por tentativa.
`negativas-mi` usa o contêiner original do L100 como alvo fixo; não o substitua nem conceda acesso
ao chat para fazê-lo passar.

**Resultado esperado:** provas positivas antes de isolar e repetição do caminho privado depois,
com negativas externas qualificadas. A pergunta operacional da sonda não é um conjunto final de avaliação.
**Autorização, custo e limpeza:** autorize separadamente cada linha que altera dados ou objetos;
as etapas de acesso e HTTP usam os modelos. Conserve os objetos necessários aos desafios seguintes
e encerre somente os temporários identificados.

### 7. Relacionar as provas à guarda de isolamento

**Objetivo:** sustentar a decisão da Etapa 4 com observações, não com uma variável declarada.
Leve os resultados ao [mapeamento do Desafio 06](06-conferir-operacao.md#etapa-2-preparar-as-provas-azure):
DNS, conexões, revisão, prontidão, consulta, ingestão e acessos positivos têm fontes diferentes.
Confira o descritor de origem `operador` antes de habilitar
`VARELEIRA_L300_CONECTIVIDADE_PRIVADA_VALIDADA`. O conferidor é local e não coleta essas observações.

**Para guardar na memória:** o descritor é a ficha da inspeção, não o instrumento de medição.
Assinar a ficha não liga o aparelho nem transforma um teste ausente em teste aprovado.

**Resultado esperado:** responsável, alvos e provas sustentam a guarda e o plano de retorno.
**Autorização, custo e limpeza:** organizar e conferir o descritor usa arquivos locais; a implantação
de `isolar` **[altera o Azure]**, requer aprovação própria e mantém os custos dos serviços.
Conserve as evidências privadas até conferir também o estado posterior.

### 8. Retirar os temporários quando não houver consumidores

**Objetivo:** encerrar a sonda sem retirar acesso necessário à recuperação ou à limpeza privada.
Antes de remover, confirme que terminou a última operação dependente, inclusive a do
[Desafio 07: recuperar e limpar](07-recuperar-limpar.md).
Confira propriedade, nome exato e inventário; preserve chat, ambiente, registro, identidades e
atribuições preexistentes.

**[altera o Azure]**, somente com autorização de remoção do Job próprio:

```powershell
az containerapp job delete --subscription $assinatura --resource-group $grupo --name $job --yes --output none
if ($LASTEXITCODE -ne 0) { throw "A remoção do Job não foi concluída." }
az containerapp job list --subscription $assinatura --resource-group $grupo --output json
```

Confira ausência real na listagem, não somente o código de saída.
O administrador retira as atribuições **criadas para esta atividade**, incluindo a escrita no
contêiner quando seu consumidor terminar, e a identidade temporária, segundo o roteiro do
Desafio 07. Apagar o Job não revoga papéis nem apaga identidades atribuídas ao usuário.
Não revogue por nome de papel, por curinga ou por uma listagem que inclua escopos herdados.

**Resultado esperado:** Job próprio ausente e acessos temporários encerrados no momento aprovado,
com a linha de base preservada.
**Autorização, custo e limpeza:** remover exige autorização por alvo; confira término das execuções
antes de retirar o Job. As cobranças de imagem, logs, rede e serviços mantidos continuam.
O Desafio 07 coordena esse encerramento; não exclua componentes do grupo gerenciado manualmente.

**Limite de reprodução:** executor, imagem e ferramentas externas agora têm arquivos públicos e
esta receita revisada. Isso não é uma nova validação Azure: as versões públicas, o build remoto,
os inícios pela CLI, sua combinação de variáveis e a coleta correlacionada de logs precisam ser
exercitados no destino autorizado. A receita foi conferida por leitura do código, testes locais
com dublês, validação local e ajuda offline; os helpers privados sustentam somente a rodada histórica.
Sem identidade autorizada, papel de aplicação, conexões aprovadas ou linha de resultado associada
à execução, mantenha a respectiva prova pendente, sem habilitar a guarda.

## Etapa 4: fechar acesso público com retorno definido

**[altera o Azure]** na fase de isolamento. Confirme previamente:

| Prova | Evidência observável |
| --- | --- |
| Consulta | `http-interno` Atendimento: resposta documentada, respondida e operacional; `acesso` complementa a prova dos filtros, sem substituir a borda HTTP |
| Ingestão | `conferir` confirma ambiente privado; `executar` ou `resumo` fornece resultado e contagens reais, com sucesso e sem falhas |
| Manutenção | `carregar` e leituras `conferir`/`resumo` no contêiner e índice próprios, com identidade de manutenção |
| DNS | `dns`: os três nomes resolvem somente para endereços RFC 1918 dentro da rede |
| Negativa externa | Procedimento e papéis do operador preparados; depois de isolar, helper externo observa 403 por acesso público desabilitado |
| Retorno | Configuração anterior, alvos e responsável definidos |

Uma variável declarando conectividade validada é uma guarda de execução, não uma medição.
Registre as provas que justificam habilitá-la, incluindo a leitura manual das conexões compartilhadas
e da revisão ativa, conforme o Desafio 06.
Depois do isolamento, repita DNS, consulta, manutenção e ingestão e execute a negativa externa;
preserve as falhas como parte do registro.
Reaplicar as definições L100 ou L200 pode reabrir o acesso público, pois elas descrevem a
configuração anterior. Esse retorno exige revisão e autorização, mesmo quando os nomes são iguais.

## Como pedir uma mudança ao Copilot no VS Code

Delimite a fase e os módulos ao pedir mudança. Mantenha os nomes e a região reais como parâmetros,
preserve o ambiente anterior e exija teste de recusa de isolamento sem evidências.
Revise o diff em **Source Control** antes de executar Bicep.
Gerar o código não autoriza alterar a rede ou aprovar uma conexão.

Para revisar a execução das sondas, anexe **somente** este guia, o Desafio 06, as três sondas,
o montador e os modelos de imagem públicos:

```text
Confira, por leitura, a receita pública das sondas L300.
Relacione cada etapa às variáveis obrigatórias, identidade, efeito, custo e limpeza.
Separe privilégio do chat, recusa de rede e verificação da borda HTTP.
Aponte o tipo ServicePrincipal da identidade de carga e a relação entre os três tempos limite.
Não execute Azure, crie credenciais, atribua papéis, abra ingresso ou altere arquivos.
Não peça inventário privado, IDs, segredo, token, pergunta final ou log bruto.
```

Revise qualquer diff proposto em **Source Control** e confronte os argumentos com a ajuda offline.
Confira o contexto de build e os testes locais antes de autorizar execução; o modelo usado no
Copilot do aluno não precisa ser o modelo de autoria deste texto.

## Conferência do resultado

Localmente, confira tipos, dependências, valores permitidos e fases pelo compilador e pelos testes.
Na nuvem, registre as provas da tabela anterior por identidade e origem de rede.
Verificações de saúde e prontidão do chat tratam processo e inicialização; registre a consulta
e a ingestão autenticadas como provas separadas.
Confira também etapa, identidade selecionada, estado do Job e linha de resultado correspondente.
Uma simulação da negativa externa ou um descritor completo não mede uma recusa real.

## Solução de problemas

| Sintoma | Diagnóstico e recuperação |
| --- | --- |
| Chat funciona, indexador falha | Confira shared private links, aprovações e ambiente de execução |
| DNS devolve endereço público dentro da rede | Confira zonas, vínculos e endpoint correto |
| Pessoa lê dados fora da rede após isolamento | Confira configuração de acesso público e alvos reais |
| L200 perde acesso depois de fechar dados | O isolamento também afeta clientes antigos; execute o plano de retorno autorizado |
| Nome existente seria recriado ou reconfigurado | Interrompa; reveja alvo e configuração completa no inventário |
| Job não baixa a imagem | Confira tag/digest, identidade de registro e `AcrPull` no recurso exato; não habilite senha de administrador |
| Job termina sem a linha da sonda | Confira timeout, contêiner e coleta de logs; mantenha a prova pendente e não inicie outra alteração |
| `Succeeded` sem linha válida ou junto de `saida_bloqueada` | Não aprove; confira associação da execução e colisão de nome com vocabulário, preservando a barreira |
| Etapa recebe configuração ausente após o início | Reenvie a lista completa na próxima execução autorizada e confira o template real; a combinação pela CLI ainda precisa de validação |
| Identidade de manutenção chega à fase `rede` como `User` | Interrompa; revise `tipoPrincipalCarga=ServicePrincipal`, `principalId` e consumidores antes de implantar |
| `http-interno` recebe 401 ou 403 inesperado | Confira alcance da URL, audiência do token, papel de aplicação e identidade selecionada; papel RBAC não concede perfil documental |
| `negativas-mi` falha por rede ou token | Não registre como recusa de papel; restaure o caminho autorizado, sem conceder privilégios extras |

## Custos, pausa e limpeza

Endpoints privados, DNS e recursos gerenciados do ambiente têm cobranças próprias.
Container Apps pode escalar a zero sem encerrar armazenamento, busca, registro, logs e rede [2][6].
O grupo gerenciado criado pela plataforma não deve ser alterado manualmente.

Preserve a rede enquanto uma aplicação depender dela. Remova alvos próprios após retirar tráfego
e conferir consumidores. Fechar o terminal não interrompe serviços hospedados.
O Job manual evita agenda, não o custo de uma execução iniciada. Builds repetidos, manutenção e
embeddings têm consumo próprio. Restrinja início do Job e download da imagem com as cópias sintéticas.
Registre início, fim, serviços mantidos e prazo das evidências; silêncio da consulta de cobrança
não significa custo zero. Siga o [encerramento do Desafio 07](07-recuperar-limpar.md) para os
temporários, preservando o grupo gerenciado.

## Situação da validação

O fechamento local registra compilação e testes de definição.
No Azure foram conferidos três endpoints privados, cinco zonas DNS, duas conexões de saída
aprovadas, ingresso autenticado e ingestão privada. A guarda recusou isolar sem evidências;
após as provas, os três serviços passaram a `publicNetworkAccess=Disabled`.
Consultas e manutenção dentro da rede continuaram funcionando; três chamadas externas
receberam 403 com papéis de dados conferidos. O registro de imagens permanece público autenticado.
O [registro local L300](../../docs/validacao/l300-validacao-local.md) lista compilação e testes;
o [registro Azure](../../docs/validacao/l300-azure-validacao.md) discrimina mecanismos, resultados
e limitações, incluindo o encerramento dos temporários.

**Receita pública, 11 de outubro de 2026:** ferramentas derivadas dos helpers privados da rodada
histórica, conferidas localmente com dublês; `sonda_l300.py --etapa validar` conferiu quatro fontes
e módulos, com rede bloqueada. A ajuda offline da Azure CLI 2.89.0 confirmou os argumentos publicados
de identidade, papéis, ACR, conexões, Job e suas execuções. As superfícies CLI de logs não estavam
disponíveis; a documentação oficial confirma tabela e colunas, e a coleta pelo portal precisa ser
associada à execução no destino autorizado. Não houve build remoto ou execução Azure das versões
públicas nesta revisão. Permanecem por conferir a combinação de variáveis no início pela CLI,
os efeitos reais desse caminho e a coleta correlacionada; o responsável pela nova execução
deve autorizar destino, custo, identidades e limpeza antes de encerrá-los.

## Glossário

| Termo | Significado |
| --- | --- |
| Private Link e endpoint privado | Conexão ao serviço e interface privada na rede |
| DNS | Sistema de resolução de nomes para endereços |
| Shared private link | Conexão privada de saída administrada pelo serviço de busca |
| Sub-rede | Parte do espaço de endereçamento da rede virtual |
| Workload profile | Perfil de execução do ambiente Container Apps |
| ARM | Serviço de administração dos recursos Azure |
| Runner | Computador que executa um workflow ou operação |
| IP, HTTP e HTTPS | Endereçamento de rede, protocolo web e sua forma com proteção da conexão |
| VPN | Rede privada virtual para conectividade remota |
| Job, execução e réplica | Definição da tarefa, uma rodada dessa tarefa e seu contêiner em execução |
| Identidade atribuída ao usuário | Recurso de identidade independente, associado ao Job ou ao chat |
| RBAC e escopo | Controle por papéis e limite de recursos em que uma concessão vale |
| `principalId`, `clientId` e `id` | ID de objeto para papéis, ID de cliente para selecionar credencial e ID do recurso para associação |
| ACR, build, run, tag e digest | Registro de imagens, construção, execução da construção, versão nomeada e resumo criptográfico |
| vCPU e GiB | Fração de núcleo virtual de processamento e gibibyte de memória |
| Namespace | Nomes e caminhos reservados ao L300 |
| IPv4 e RFC 1918 | Versão 4 do protocolo IP e especificação das faixas de endereços de uso privado |
| JSON e ASCII | Formato de dados estruturados e conjunto básico de caracteres da linha de resultado |
| REST e KQL | Estilo de interface web baseado em recursos e linguagem Kusto para consultar logs |

## Referências

1. [DNS de endpoints privados](https://learn.microsoft.com/en-us/azure/private-link/private-endpoint-dns).
2. [Rede e criação do ambiente Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/networking).
3. [Sub-redes e recursos gerenciados](https://learn.microsoft.com/en-us/azure/container-apps/custom-virtual-networks).
4. [Conexões privadas de saída do indexador](https://learn.microsoft.com/en-us/azure/search/search-indexer-howto-access-private).
5. [What-if e limitações de previsão](https://learn.microsoft.com/en-us/azure/azure-resource-manager/bicep/deploy-what-if).
6. [Cobrança de Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/billing).
7. [Jobs, início, limites e permissões em Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/jobs).
8. [Identidades gerenciadas em Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/managed-identity).
9. [Atribuir papéis Azure por CLI](https://learn.microsoft.com/en-us/azure/role-based-access-control/role-assignments-cli).
10. [Console e consulta de logs no Log Analytics](https://learn.microsoft.com/en-us/azure/container-apps/log-monitoring).
11. [Construção remota com ACR Tasks](https://learn.microsoft.com/en-us/azure/container-registry/container-registry-tutorial-quick-task).
12. [Referência CLI de Container Apps Jobs](https://learn.microsoft.com/en-us/cli/azure/containerapp/job).

## Autoria

Texto por GPT-6.1 Sol; código e testes por Claude Sonnet 5.5, com Astra indisponível.
O modelo de autoria não configura o modelo do Copilot ou os deployments Azure.

Revisão documental: gpt-6-astra (Astra), em 11 de outubro de 2026, por leitura integral e
conferência local dos artefatos; sem nova execução Azure.

Receita das sondas: GPT-6.1 Sol, com Astra indisponível, em 11 de outubro de 2026; ferramentas
públicas por Claude Sonnet 5.5; comandos verificados por ajuda offline; sem execução Azure.
