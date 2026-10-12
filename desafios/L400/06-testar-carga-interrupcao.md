# L400 · Desafio 06: testar carga e interrupção

[Início](../../README.md) · [Desafio 05](05-comparar-estrategias.md) · [Desafio 07](07-recuperar-limpar.md)

| Campo | Definição |
| --- | --- |
| Situação | Histórico de progresso/cancelamento preservado; gerador público exercitado em 11 de outubro de 2026, com falha de host e duas cargas pequenas; não comprova capacidade |
| Público | Operações, arquitetura, Atendimento e desenvolvimento |
| Resultado | Planejar e interpretar carga finita, admissão e interrupção, preservando falhas e consumo desconhecido |
| Custo | Plano local sem Azure; carga, Job e construção de imagem têm custo e exigem orçamento aprovado antes |

## Conteúdo

- [Cenário](#cenário)
- [Objetivos](#objetivos)
- [Artefatos e disponibilidade](#artefatos-e-disponibilidade)
- [Tecnologias e conceitos](#tecnologias-e-conceitos)
- [Pré-requisitos](#pré-requisitos)
- [Etapa 1: definir uma carga finita](#etapa-1-definir-uma-carga-finita)
- [Etapa 2: conferir progresso e cancelamento](#etapa-2-conferir-progresso-e-cancelamento)
- [Etapa 3: observar falhas e isolamento](#etapa-3-observar-falhas-e-isolamento)
- [Como pedir uma mudança ao Copilot no VS Code](#como-pedir-uma-mudança-ao-copilot-no-vs-code)
- [Conferência do resultado](#conferência-do-resultado)
- [Solução de problemas](#solução-de-problemas)
- [Custos, pausa e limpeza](#custos-pausa-e-limpeza)
- [Situação da validação](#situação-da-validação)
- [Glossário e referências](#glossário-e-referências)
- [Autoria](#autoria)

## Cenário

Durante o piloto fictício, mais de uma pessoa pode consultar o assistente. Beatriz Torres precisa
ver o andamento sem receber texto ainda não verificado. A equipe de operações quer distinguir
sobrecarga, cancelamento e falha, conservando a autorização de cada requisição.

## Objetivos

1. Fixar número de pedidos, concorrência, prazo e condição de parada.
2. Conferir progresso sem expor resposta bruta.
3. Impedir próximas etapas de uma requisição cancelada.
4. Distinguir testes controlados de capacidade e disponibilidade de produção.
5. Interpretar admissão, resultado HTTP e consumo desconhecido sem confundir recusa com falha.

## Artefatos e disponibilidade

| Artefato | Uso |
| --- | --- |
| [Servidor do chat](../../scripts/chat_web.py) | Admissão e HTTP, protocolo de transferência de hipertexto usado pelo chat |
| [Contrato e erros](../../scripts/lab_chat.py) | Limites, causas e resposta verificada |
| [Gerador público de carga](../../scripts/gerar_carga_l400.py) | Disponível: plano local por padrão e pedidos concorrentes finitos; resultado interpretado por execução |
| [Testes do gerador](../../tests/test_gerar_carga_l400.py) | 101 testes locais com dublês: validação, transporte, classificação, parada e proteção das saídas |
| [Montador do contexto](../../scripts/montar_contexto_sonda_l300.py) e [imagem da sonda](../../infra/sonda-l300/Dockerfile) | Incluem o gerador; a sonda continua como ponto de entrada da imagem |
| [Bicep L400](../../infra/l400.bicep) e [módulo de hospedagem](../../infra/modules/l200-aplicacao.bicep) | Ingresso interno por padrão, mínimo de zero e máximo de uma réplica; não definem o limite de admissão |
| [Interface](../../web/app.js) | Envio e apresentação |
| [Operação L300](../../scripts/operar_l300.py) | Referência de resumo de logs sem conteúdo |

O [runtime L400](../../scripts/lab_orquestracao.py), componente de execução, e os
[testes](../../tests/test_orquestracao.py) implementam progresso e cancelamento.
O [avaliador do Desafio 05](05-comparar-estrategias.md#etapa-2-congelar-o-regime) usa
JSON, JavaScript Object Notation, formato de dados estruturados, em pedidos sequenciais;
ele não substitui o gerador concorrente nem consome eventos de progresso.
O gerador usa somente `POST /api/perguntar`: não exercita progresso nem cancelamento explícito.

## Tecnologias e conceitos

**Concorrência** é a quantidade de pedidos em execução ao mesmo tempo. Uma fila sem limite
não resolve falta de capacidade. **Timeout** é o prazo para interromper a espera.
No gerador, cada trabalhador espera a resposta antes de enviar seu próximo pedido:
esse **laço fechado** limita pedidos em andamento, não fixa uma taxa de chegada.

**Admissão** é a decisão de aceitar um pedido. O servidor usa um semáforo, contador de vagas,
sem espera: se estiver cheio, recusa imediatamente com HTTP 429 e erro público `ocupado`.
O cabeçalho `Retry-After: 2` sugere esperar dois segundos, mas o gerador não repete pedidos.
O limite vem de `VARELEIRA_MAX_CONCORRENCIA`, com padrão **4**, conforme o
[contrato](../../scripts/lab_chat.py); o Bicep L400 não define essa variável.
Confirme a configuração efetiva e a ausência de outra carga antes da prova.

**Latência** é o tempo observado até uma resposta. **p95**, percentil 95, é uma posição na lista
ordenada de durações. Nas pequenas amostras deste roteiro, o cálculo do
[gerador](../../scripts/gerar_carga_l400.py) faz o p95 coincidir com a maior duração.
Uma **réplica** é uma instância da aplicação. A hospedagem permite zero a uma réplica;
o primeiro pedido pode esperar a **partida a frio**, inicialização depois de uma pausa.
Um **Container Apps Job** executa uma tarefa finita em um contêiner e termina, em vez de
hospedar outro chat [5]. Uma execução do Job pode enviar vários pedidos concorrentes.
**Embeddings** são representações numéricas dos textos; **tokens** são unidades de texto
contabilizadas pelos modelos, com cobrança distinta do custo do executor.

**Para guardar na memória:** três mensageiros levam novos envelopes somente depois de voltar.
Se a volta demora, saem menos envelopes: isso não representa pessoas chegando sem parar.
Seis viagens, numa única porta com quatro vagas e que pode estar fechada no início, mostram
o comportamento daquela rodada. O p95 dessas seis viagens é apenas a mais demorada;
não é uma medição da capacidade do prédio nem um percentil de produção.

**Streaming** envia partes de uma resposta durante a execução. No exercício, o progresso
contém eventos de etapa; texto do modelo só pode ser apresentado depois das verificações.
O FastAPI oferece respostas por gerador, mas isso não valida automaticamente seu conteúdo [1].
O L400 usa eventos enviados pelo servidor, **Server-Sent Events (SSE)**, no
`POST /api/perguntar/progresso`, somente quando a coordenação está ativa.
O endpoint, endereço de uma operação, JSON anterior permanece sem alteração de formato.

**Cancelamento** impede a continuação da requisição no programa. Um pedido remoto já enviado
pode continuar consumindo tokens até concluir ou atingir seu próprio timeout.
Não anuncie cancelamento remoto instantâneo sem prova.

## Pré-requisitos

Abra a pasta completa no Visual Studio Code (VS Code), use o terminal PowerShell 7 e a
`.venv` do Desafio 01, com Python 3.12 ou superior e os
[requisitos L400](../../requirements/l400.txt). Use perguntas sintéticas de desenvolvimento,
nunca conjuntos finais ou suas paráfrases para ajustar limites ou gerar carga.

Prepare destino, origem de rede, identidade autorizada, perfil e quantidade exata de chamadas.
Para uma prova real, confirme assinatura ativa, permissões proporcionais e **nova autorização
de consumo e orçamento** do responsável pelo ambiente. O teto e a autorização históricos não
autorizam outra rodada. Login bem-sucedido não comprova autorização documental, de criação
do Job ou de consumo.

Os testes locais usam dublês e não têm consumo Azure. A execução de carga real é deliberada,
finita e autorizada; não use laço sem parada ou tentativas automáticas indefinidas.
Para os comandos `az containerapp`, confira a CLI de 64 bits e a pasta própria de extensões,
pela [nota do L300 D04](../L300/04-dependencias-privadas.md#3-criar-um-job-manual-no-ambiente-l300).

## Etapa 1: definir uma carga finita

**Roteiro público revisado de carga finita e concorrente.** Os oito passos abaixo separam
planejamento local de execução paga. Cada execução exige autorização própria; os achados
de encaminhamento de argumentos, endereço interno e leitura de logs abaixo não aprovam
automaticamente uma carga nem autorizam sua repetição.

| Condição | Resultado a conferir |
| --- | --- |
| Abaixo do limite de admissão, sem outra carga | Pedidos admitidos; conferir contrato, tipos, evidências e uso separadamente |
| Mais pedidos simultâneos que vagas | HTTP 429 com `ocupado`, recusa explícita sem fila |
| Modelo devolve 429 ou servidor atinge seu prazo | HTTP 503 com `indisponivel`, não `ocupado` |
| Cliente deixa de esperar | `timeout` ou pedido sem resultado; consumo remoto pode continuar |

### 1. Planejar por escrito e conferir o plano local

**Objetivo:** limitar efeitos antes de pedir token, criar Job ou enviar perguntas.

1. Registre o plano em local privado e peça aprovação do responsável pelo consumo:

| Item do plano | Rodada abaixo da admissão | Prova de admissão, se autorizada separadamente |
| --- | --- | --- |
| Pedidos e teto de envios HTTP | 6, sem repetição | 12, sem repetição |
| Concorrência | 3 | 8, nunca maior que os pedidos |
| Janela para novos pedidos | 300 segundos | 300 segundos |
| Prazo por pedido | 120 segundos | 120 segundos |
| Parada por resultados seguidos fora do esperado | 3 | 3 |
| Classes esperadas | `ok` | `ok,ocupado` |
| Destino, origem e perfil | Chat autorizado, caminho direto e perfil aprovado | Mesmo regime, sem alterar política ou réplica |
| Orçamento | Valor aprovado, serviços incluídos e responsável | Aprovação que cubra os 12 envios adicionais |

O teto de envios HTTP **não é um teto de chamadas aos modelos**: um pedido coordenado pode
fazer várias chamadas internas. Confira os limites do chat e da coordenação no plano de custo.
As duas rodadas somam no máximo 18 envios ao chat; o gerador não calcula nem bloqueia um valor
monetário. Inclua busca, embeddings, geração, contingência, Job, imagem, rede e logs no orçamento.

2. Confira os limites aceitos pelo programa, antes de escolher valores:

| Opção | Intervalo e padrão |
| --- | --- |
| `--pedidos` | 1 a 50; padrão 6 |
| `--concorrencia` | 1 a 8, no máximo os pedidos; padrão 3, reduzido se houver menos pedidos |
| `--tempo-maximo` | 10 a 600 segundos; padrão 300 |
| `--tempo-por-pedido` | 1 a 300 segundos; padrão 120 |
| `--falhas-seguidas` | 1 a 10; padrão 3 |
| `--esperar` | Lista de classes do passo 6; padrão `ok` |

Esses limites são conferidos antes de qualquer rede [10]. A carga para novos envios ao esgotar
a quantidade, vencer a janela de tempo, atingir a parada por resultados seguidos fora do
esperado ou receber Ctrl+C. Com concorrência, essa sequência é a ordem de conclusão dos
resultados, não a numeração dos pedidos; os já enviados ainda podem terminar.
O prazo por pedido vale por operação do soquete, conexão de rede, e pela leitura do corpo;
não é uma garantia de duração total isolada. O teto do programa impede
novos envios ao acabar `--tempo-maximo` e dá aos já enviados até **10 segundos adicionais**.
Com os valores acima, são até 310 segundos depois do primeiro envio; obter o token gerenciado
tem prazo próprio e fica fora dessa conta. Use prazo do cliente maior que os 90 segundos
padrão do chat, sem confundir timeout do cliente com HTTP 503 do servidor.

3. A partir da raiz do projeto, rode somente ajuda e plano. Este host é sintético, aceito pelo
   validador; não representa um chat provisionado e não deve ser usado para carga real:

```powershell
.\.venv\Scripts\python.exe scripts\gerar_carga_l400.py --help
$urlExemplo = "https://carga.exemplo.regiao.azurecontainerapps.io"
.\.venv\Scripts\python.exe scripts\gerar_carga_l400.py --url $urlExemplo `
    --pedidos 6 --concorrencia 3 --tempo-maximo 300 --tempo-por-pedido 120 --falhas-seguidas 3
if ($LASTEXITCODE -ne 0) { throw "O plano local não foi aprovado." }
```

Trecho real do plano sintético, obtido sem rede nesta revisão:

```text
Gerador de carga L400: pedidos concorrentes e finitos em POST /api/perguntar
  Destino: https://*.azurecontainerapps.io (mascarado; o endereço completo nunca é impresso nem gravado; caminho fixo /api/perguntar)
  Rede: conexão direta ao destino, com o certificado verificado; os proxies do ambiente são ignorados de propósito
  Pedidos: 6 (teto 50) · concorrência: 3 (teto 8, nunca acima dos pedidos)
```

**Resultado esperado:** código zero, limites e destino mascarado no plano e indicação
`[SIMULAÇÃO]`. Sem `--executar`, nada é enviado, nenhum token gerenciado é pedido e nenhum
relatório é criado, mesmo se `--relatorio` estiver informado. O plano não emite a linha final
de resultado da carga. Uma execução real exige **ambos** `--executar` e `--confirmo-consumo`;
faltar a confirmação é erro de uso, com saída 1.

Por padrão, quatro perguntas sintéticas embutidas são usadas em rodízio. Para desenvolvimento
próprio, `--perguntas-arquivo` aceita uma lista JSON de 1 a 20 textos, até 64 KiB, kibibytes.
Aceita UTF, formato de transformação Unicode, nas codificações UTF-8 com ou sem BOM,
marca de ordem de bytes, ou UTF-16 com essa marca. Não inclua dados pessoais ou novas regras
de seguro sem revisão.

A proteção recusa arquivos em pastas `avaliacao*` sob `dados\` e perguntas iguais, após
normalização, às encontradas nos arquivos JSON de `dados\`. Isso não detecta paráfrases.
Sem a pasta ou sem os conjuntos nela, a conferência por conteúdo fica indisponível:
a imagem da sonda leva documentos e manifestos, **não os conjuntos de avaliação**.
Não copie conjuntos finais para a imagem para contornar essa limitação. Quem opera continua
responsável por usar somente desenvolvimento.

**Autorização, custo e limpeza:** este passo é local, sem Azure ou tokens; não cria arquivos.
O plano prepara a aprovação, não a substitui. Nenhum temporário precisa ser removido.

### 2. Escolher o lugar de execução

**Objetivo:** executar de onde o chat é alcançável, conservando o ingresso aprovado.

1. Receba `$assinatura`, `$grupo` e `$aplicacaoL400` do inventário privado e leia o FQDN
   (*Fully Qualified Domain Name*, nome completo de domínio) **real** no ARM, Azure Resource
   Manager, serviço de administração. URL, Uniform Resource Locator, é o endereço do recurso.
   A saída pública do Bicep pode estar vazia com ingresso interno; não use o host do plano:

```powershell
$fqdnL400 = az containerapp show --subscription $assinatura --resource-group $grupo `
    --name $aplicacaoL400 --query properties.configuration.ingress.fqdn --output tsv
if ($LASTEXITCODE -ne 0 -or -not $fqdnL400) { throw "FQDN real do chat L400 não conferido." }
$urlChat = "https://$fqdnL400"
```

Com ingresso interno, o valor lido tem `.internal.`: use `https://<FQDN interno>` em
`$urlChat`. Não monte `https://<app>.<domínio>`; esse host pode responder 404 na borda,
antes de alcançar a aplicação.

2. Escolha uma origem e registre por que ela alcança esse endereço:

| Origem | Quando usar | Limite |
| --- | --- | --- |
| Computador do operador | URL alcançável diretamente, com autenticação autorizada | Não presume acesso ao ingresso interno |
| Job no ambiente integrado à rede | Caminho normal do L400 com ingresso interno | Exige imagem atual, identidade, criação/início e leitura de logs autorizados |

3. Confira as restrições do gerador: somente HTTPS, HTTP com proteção da conexão, porta 443
   e host padrão terminado em `.azurecontainerapps.io`. O formato
   `https://<app>.internal.<ambiente>.<região>.azurecontainerapps.io` também é aceito.
   Não aceita domínio personalizado, endereço IP, protocolo de internet, usuário, senha,
   query, parâmetros na URL, ou fragmento. O caminho é fixo em `/api/perguntar`.

O certificado é verificado com TLS, Transport Layer Security, proteção do transporte.
Redirecionamentos não são seguidos. Os proxies, intermediários de rede configurados no ambiente,
são **ignorados de propósito** para que o token não siga por um intermediário implícito.
Quem depende exclusivamente de proxy não consegue usar esta versão.
Fora da rede, um nome interno pode produzir `falha_de_rede` com causa `dns`, sistema de nomes
de domínio; se nenhum pedido receber resposta HTTP, a saída é 2. Isso não prova falha do chat.

**Resultado esperado:** origem compatível com o ingresso e destino explícito. Não abra o chat
à internet, altere resolução de nomes ou reduza autenticação para viabilizar a carga.
**Autorização, custo e limpeza:** escolher a origem é planejamento; a criação do Job e o build,
construção remota da imagem, **[altera o Azure]**, ficam no passo 3. Rede e serviços existentes
continuam cobrando; não há recurso novo a limpar neste passo.

### 3. Autorizar consumo e preparar autenticação e executor

**Objetivo:** separar autorização de consumo, identidade e permissão para operar o Job.

1. O responsável pelo ambiente aprova destino, plano, orçamento e limpeza. Quem administra
   o tenant, diretório de identidades do Microsoft Entra ID, autoriza a emissão do token
   e o papel de aplicação correspondente ao perfil; quem administra a assinatura autoriza
   recursos e associações. O gerador não cria identidades, credenciais ou papéis.
2. No computador, obtenha por um procedimento **já autorizado** um token de acesso
   (*Bearer*) para o chat. Sua origem e autorização não são responsabilidade do gerador.
   Use sessão PowerShell dedicada e leia o valor sem eco, nunca por argumento:

```powershell
$tokenProtegido = Read-Host "Token de acesso autorizado para o chat" -AsSecureString
$env:VARELEIRA_CARGA_TOKEN = [System.Net.NetworkCredential]::new("", $tokenProtegido).Password
```

O programa lê `VARELEIRA_CARGA_TOKEN`; `--token-env` aceita somente o **nome** de outra variável.
Não imprima a variável, não a anexe ao Copilot e não coloque o token em arquivos ou histórico.
Os blocos locais dos passos 4 e 5 retiram o token ao terminar, inclusive se ocorrer erro.

3. Para o Job, reaproveite a receita pública do L300 D04 [9], sem recriar objetos existentes:
   - [Identidades, papéis e conexões](../L300/04-dependencias-privadas.md#1-preparar-identidades-papéis-e-conexões):
     seleção e associação das identidades; a carga usa a identidade autorizada para chamar o
     **chat**. Associá-la ao Job ou conceder papéis de dados não concede o perfil documental.
   - [Contexto e imagem da sonda](../L300/04-dependencias-privadas.md#2-montar-o-contexto-e-construir-a-imagem-da-sonda):
     montagem offline com lista fechada de 12 arquivos, mais Dockerfile e lista de permissão.
     Construa uma imagem nova que inclua o gerador; a imagem histórica não é essa entrega.
   - [Job manual](../L300/04-dependencias-privadas.md#3-criar-um-job-manual-no-ambiente-l300):
     mesmo ambiente integrado, uma réplica de Job, paralelismo 1, zero tentativas automáticas
     e prazo de 900 segundos da receita. Confira também a nota de CLI/extensão de 64 bits.
     O prazo deve cobrir token, carga e coleta do resultado.

Antes do primeiro token para o chat, confira a atribuição `Vareleira.Atendimento` à
identidade gerenciada usada nessa prova pelo
[roteiro de papéis L300 D03](../L300/03-filtrar-acesso.md#etapa-2-preparar-papéis-de-aplicação).
Conceder esse papel **[altera o Entra ID]** e exige autorização do administrador.
Confirme novamente que `$urlChat` usa o FQDN L400 lido do ARM, com `.internal.` para
ingresso interno; não reutilize a URL do chat L300.

Paralelismo 1 significa um contêiner de Job nesta execução, não um único pedido HTTP;
os trabalhadores do gerador seguem `--concorrencia` dentro desse contêiner.
Construir imagem, criar/associar o Job e conceder papéis Azure **[altera o Azure]**;
exigem autorizações próprias. Não acrescente papéis administrativos para fazer a carga passar.
Esses procedimentos ficam no D04; este guia acrescenta somente a troca de comando na execução.
Não existe agenda nem gatilho automático neste roteiro.

Dentro do Job, `--identidade-gerenciada` usa a credencial do repositório, selecionada por
`--client-id`, com `--audiencia "api://<GUID>/.default"` [6]. GUID significa identificador
globalmente único. O primeiro valor é o ID de cliente da identidade associada; o segundo
identifica o aplicativo de login do chat. Não são o ID de recurso nem o ID de objeto.
Essa opção não se combina com `--token-env`.

Também é possível conferir esse plano **localmente, sem obter token**. Os GUIDs zero abaixo
são somente exemplos de formato, não credenciais válidas para uma execução:

```powershell
.\.venv\Scripts\python.exe scripts\gerar_carga_l400.py `
    --url "https://carga.internal.exemplo.regiao.azurecontainerapps.io" `
    --pedidos 12 --concorrencia 8 --tempo-maximo 300 --tempo-por-pedido 120 --falhas-seguidas 3 `
    --esperar "ok,ocupado" --identidade-gerenciada `
    --client-id "00000000-0000-0000-0000-000000000000" `
    --audiencia "api://00000000-0000-0000-0000-000000000000/.default"
if ($LASTEXITCODE -ne 0) { throw "O plano com identidade sintética não foi aprovado." }
```

**Resultado esperado:** plano e autorizações registrados privadamente; no Job, imagem e
identidades conferidas pela receita, sem execução de carga ainda.
**Custo e limpeza:** os planos locais não consomem Azure. Construção, armazenamento de imagem,
Job e logs têm cobrança própria; consumo de modelos fica sujeito ao plano aprovado.
Inventarie somente temporários novos e retire-os no passo 8. A receita não autoriza nova
implantação, concessão ou repetição da rodada histórica.

### 4. Executar abaixo do limite de admissão

**Objetivo:** observar seis pedidos com concorrência três, antes de pressionar a admissão.
**[altera o Azure]** ao consumir busca/modelos ou iniciar o Job.

1. Confira aprovação, configuração efetiva de admissão 4 e ausência de outra carga.
2. Escolha **um** dos caminhos, não ambos. No computador com URL alcançável, prepare
   `$relatorioNovo` como caminho de arquivo **novo**, em pasta privada existente.
   Refaça o plano do passo 1 com `$urlChat` e esse relatório, sem `--executar`.
   Só depois da aprovação e do token do passo 3, execute:

```powershell
try {
    $saidaCarga = .\.venv\Scripts\python.exe scripts\gerar_carga_l400.py --url $urlChat `
        --pedidos 6 --concorrencia 3 --tempo-maximo 300 --tempo-por-pedido 120 `
        --falhas-seguidas 3 --esperar ok --relatorio $relatorioNovo --executar --confirmo-consumo
    $codigoCarga = $LASTEXITCODE
} finally {
    Remove-Item Env:\VARELEIRA_CARGA_TOKEN -ErrorAction SilentlyContinue
    Remove-Variable tokenProtegido -ErrorAction SilentlyContinue
}
```

3. No caminho interno, use o Job e as variáveis preparados no D04: `$assinatura`, `$grupo`,
   `$job`, `$imagemSondaCompleta`, `$variaveisBase`, `$identidadeChat` e `$idLogin`.
   `$urlChat` agora identifica o chat **L400 interno**, com `.internal.` no FQDN lido do ARM
   no passo 2, não um host montado pelo nome. O ponto de entrada, `ENTRYPOINT`, continua
   sendo a sonda; substitua-o somente nesta execução:

```powershell
$autenticacaoJob = @(
    "--identidade-gerenciada"
    "--client-id=$($identidadeChat.clientId)"
    "--audiencia=api://$idLogin/.default"
)
$argumentosCarga = @(
    "scripts/gerar_carga_l400.py"
    "--url=$urlChat"
    "--pedidos=6"
    "--concorrencia=3"
    "--tempo-maximo=300"
    "--tempo-por-pedido=120"
    "--falhas-seguidas=3"
    "--esperar=ok"
) + $autenticacaoJob + @("--executar", "--confirmo-consumo")
$argumentosJson = ConvertTo-Json -InputObject $argumentosCarga -Compress
$argumentosBase64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($argumentosJson))
$entradaPython = "-cimport base64,json,runpy,sys; sys.path.insert(0,'scripts'); sys.argv=json.loads(base64.b64decode('$argumentosBase64')); runpy.run_path(sys.argv[0],run_name='__main__')"
$inicioExecucaoUtc = [DateTime]::UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ")
az containerapp job start --subscription $assinatura --resource-group $grupo --name $job `
    --container-name sonda --image $imagemSondaCompleta --cpu 0.25 --memory 0.5Gi `
    --env-vars @variaveisBase --command python --args=$entradaPython --output json
if ($LASTEXITCODE -ne 0) { throw "Confira se uma execução foi criada antes de autorizar qualquer repetição." }
```

`scripts/gerar_carga_l400.py` nesse bloco é o caminho **dentro do contêiner Linux**, não um
arquivo aberto pelo PowerShell. Preserve a lista completa de variáveis, imagem e recursos;
as variáveis `VARELEIRA_PROBE_*` não configuram os limites do gerador, que entram pelos argumentos.

A lista é codificada em **Base64**, representação de bytes como texto, e enviada como um
único argumento `-c` do Python. Ele recompõe os argumentos e executa o mesmo arquivo do
gerador. Isso evita que a CLI interprete `--url` e as outras opções do gerador como opções
Azure; a passagem de uma lista plana não passou nessa conferência do parser local.
Base64 **não é criptografia**: a lista continua sendo configuração privada e não deve
conter token. O mecanismo de argumento único também funcionou na rodada de validação de 11 de outubro de 2026: o processo
obteve o token da identidade gerenciada e enviou pedidos. Isso comprova o encaminhamento,
não o resultado da carga. Registre `$inicioExecucaoUtc`, em tempo universal coordenado (UTC),
antes de cada início, inclusive ao reconstruir o comando no passo 5.

**Ressalva da CLI, interface de linha de comando:** o encaminhamento `--command python`
com `--args=$entradaPython` foi exercitado no Azure [8]. Não deduza disso a forma de
combinação de variáveis em todas as versões da CLI. Siga a prudência do
[início de execução no D04](../L300/04-dependencias-privadas.md#4-iniciar-uma-etapa-por-execução):
confira a definição efetiva e o resultado da execução certa antes de outra operação.
Não altere permanentemente o Job para contornar uma divergência.

4. Espere a conclusão e leia os passos 6 e 7 antes de autorizar a prova acima do limite.

**Resultado esperado:** seis enviados e com resultado, zero não enviados, sem resultado,
divergentes ou `ocupado`, com saída 0, com serviço pronto e sem interferência. Registre
eventuais falhas de partida a frio ou serviço, sem descartá-las. `ok` confirma contrato,
não que todas as respostas têm fonte ou que seu conteúdo está correto; confira também
`tipos`, `respostas_ok_com_evidencia` e uso. Uma falha permanece registrada.
**Autorização, custo e limpeza:** iniciar exige permissão sobre o Job e aprovação de uso de
suas identidades; consultar o chat exige perfil autorizado. Cada envio pode consumir tokens;
o início do Job e os logs têm custo [7]. Preserve a evidência, retire token local e conserve
o Job apenas até a última prova autorizada, conforme o passo 8.

### 5. Exercitar admissão acima do limite

**Objetivo:** observar recusa explícita quando mais de quatro pedidos chegam simultaneamente.
**[altera o Azure]** ao enviar a segunda carga ou iniciar outra execução do Job.

1. Conserve destino, perfil, política e uma réplica do chat. Peça aprovação dos **12 envios
   adicionais**, com concorrência 8. Confira esse plano sem `--executar` antes de prosseguir.
2. No computador, obtenha novamente o token pelo passo 3 e escolha outro `$relatorioNovo`,
   sem apagar nem sobrescrever o primeiro:

```powershell
try {
    $saidaCarga = .\.venv\Scripts\python.exe scripts\gerar_carga_l400.py --url $urlChat `
        --pedidos 12 --concorrencia 8 --tempo-maximo 300 --tempo-por-pedido 120 `
        --falhas-seguidas 3 --esperar "ok,ocupado" --relatorio $relatorioNovo --executar --confirmo-consumo
    $codigoCarga = $LASTEXITCODE
} finally {
    Remove-Item Env:\VARELEIRA_CARGA_TOKEN -ErrorAction SilentlyContinue
    Remove-Variable tokenProtegido -ErrorAction SilentlyContinue
}
```

3. No Job, em vez do comando local, reconstrua a lista completa abaixo. Depois, refaça
   **a codificação e o início do passo 4**, a partir de `$argumentosJson`, uma vez,
   depois da conclusão e coleta da execução anterior. Não reutilize `$entradaPython`
   da primeira carga, que ainda contém os limites anteriores:

```powershell
$argumentosCarga = @(
    "scripts/gerar_carga_l400.py"
    "--url=$urlChat"
    "--pedidos=12"
    "--concorrencia=8"
    "--tempo-maximo=300"
    "--tempo-por-pedido=120"
    "--falhas-seguidas=3"
    "--esperar=ok,ocupado"
) + $autenticacaoJob + @("--executar", "--confirmo-consumo")
```

4. Confira no passo 6 se houve `ocupado`. Com `--esperar "ok,ocupado"`, essas recusas não
   contam como divergência nem acionam a parada; qualquer outra classe continua contando.
   O gerador não segue o `Retry-After` nem reenvia o pedido recusado.

**Para guardar na memória:** a portaria tem quatro crachás de entrada temporários.
Quem chega sem crachá disponível ouve “ocupado”; não fica numa fila escondida.
Essa recusa protege o limite de admissão e **não é falha do serviço**. Ela também não prova
que o prédio suporta um volume de pessoas por minuto.

**Resultado esperado:** respostas admitidas e recusas `ocupado` quando há sobreposição
acima das quatro vagas; não fixe uma quantidade exata de recusas.
Se todos os resultados são esperados e todos os pedidos foram enviados, a saída pode ser 0
mesmo com recusas. Se nenhum `ocupado` aparecer, o código 0 sozinho **não demonstra a admissão**:
o laço fechado e os tempos de rede podem não produzir a sobreposição necessária.
Registre a prova como não observada, confira a configuração e não repita por tentativa.
Um 429 vindo do modelo chega pelo contrato do chat como **503 `indisponivel`**;
um 429 sem erro público `ocupado` cai em `http`. Não junte essas causas.
**Autorização, custo e limpeza:** aprovação e orçamento são próprios desta segunda rodada;
`--confirmo-consumo` não concede permissão. Consumo ausente nas recusas é desconhecido,
não zero. Retire token e temporários pelos mesmos controles do passo 8; não aumente réplicas
nem limite de admissão para fabricar sucesso.

### 6. Ler conclusão, resultado e relatório

**Objetivo:** interpretar o que foi recebido, sem tratar término do processo como aprovação.

1. No computador, conserve `$codigoCarga`, capturado imediatamente após o programa, e obtenha
   `$linha` da última linha de `$saidaCarga`. `stdout` é a saída padrão; `stderr` é o fluxo
   separado de erros, que também precisa ser conferido:

```powershell
$linha = $saidaCarga | Select-Object -Last 1
```

2. No Job, use a [leitura de conclusão e logs do D04](../L300/04-dependencias-privadas.md#5-ler-conclusão-e-resultado-separadamente).
   Associe Job, execução, contêiner e janela de tempo privadamente. No console dessa execução,
   procure **`L400_CARGA_RESULTADO=`**, não o prefixo da sonda L300.
   A consulta HTTP de Log Analytics publicada no D04 já inclui os dois prefixos: na coleta,
   troque `$prefixoColeta` para `"L400_CARGA_RESULTADO="`. A resposta traz
   `tables[0].rows` com `[TimeGenerated, Log_s]`. Espere a ingestão com intervalo e limite,
   sem reiniciar a carga; não execute o validador de campos da sonda L300 nesse resultado.
   Copie para `$linha` apenas o conteúdo dessa linha, sem metadados privados do log.
   Confira `properties.status` pelo `job execution show` do D04. **`Succeeded` do Job não
   prova aprovação**; `Failed` indica saída não zero e exige ler a causa. Ausência da linha
   correta mantém a prova pendente.
3. Depois do prefixo há JSON em uma linha ASCII, conjunto básico de caracteres. O plano não
   produz essa linha; erros de uso anteriores à execução também podem encerrar sem resultado.
   Confira sua estrutura com comandos locais, sem chamar Azure ou repetir carga:

```powershell
$prefixo = "L400_CARGA_RESULTADO="
if (-not $linha -or -not $linha.StartsWith($prefixo)) { throw "Falta a linha de resultado da execução." }
$resultado = $linha.Substring($prefixo.Length) | ConvertFrom-Json
if ($resultado.esquema -ne 1 -or $resultado.relatorio -ne "carga_l400" -or
    $resultado.limite -ne "carga_pequena_nao_capacidade_producao") {
    throw "O resultado não corresponde ao contrato do gerador."
}
```

4. Interprete as classes, vocabulário fechado:

| Classe | Significado e limite |
| --- | --- |
| `ok` | HTTP 200 com contrato público válido e não simulado; não confere fidelidade, resposta documentada ou fonte correta |
| `ocupado` | HTTP 429 com erro público `ocupado`; recusa de admissão |
| `erro_publico` | Erro reconhecido do chat, como 503 `indisponivel`; leia `erros_publicos` |
| `http` | Resposta HTTP sem erro público reconhecido, inclusive recusas da borda EasyAuth, autenticação da plataforma |
| `timeout` | Cliente esgotou o prazo de espera; não demonstra interrupção remota |
| `falha_de_rede` | Causa fechada `dns`, `conexao` ou `tls` |
| `redirecionamento` | HTTP 3xx; destino seguinte não foi chamado |
| `formato_invalido` | Corpo ou formato recusado, inclusive acima de 128 KiB; não é uma resposta válida |
| `resposta_simulada` | Resposta marcada como demonstração; não é prova de geração Azure |

HTTP 401/403 gera saída 2, seja `http` na borda ou `erro_publico` no chat.
Recusas interceptadas pelo EasyAuth não trazem o `X-Request-Id` do servidor.
O gerador conta somente a **presença** desse cabeçalho, nunca seu valor.

| Código de saída | Interpretação |
| --- | --- |
| `0` | Plano local válido **ou**, em execução, todos enviados e dentro de `--esperar`; não aprova conteúdo ou capacidade |
| `1` | Uso/configuração: limites, URL, perguntas, token de variável, relatório ou confirmação inválidos; nada enviado |
| `2` | Token gerenciado indisponível, algum HTTP 401/403 ou resultados registrados somente de rede/prazo, sem resposta HTTP |
| `3` | Resultado fora do esperado, interrupção ou pedidos não enviados |
| `4` | Defeito do gerador ou falha ao registrar o relatório final |

Na execução, defeito tem prioridade sobre acesso, que tem prioridade sobre divergência:
**4, depois 2, depois 3**. Compare o código do processo com `codigo_de_saida` e o estado do Job.
Na falha de gravação final, o processo pode sair com 4 mesmo que a linha já calculada indique 0;
o erro no fluxo separado impede aprovar a coleta. Não reenvie perguntas para refazer um arquivo.

5. Confira as contagens e a abrangência da medição:

| Campos | Conferência |
| --- | --- |
| `pedidos` | `planejados = enviados + nao_enviados`; `enviados = com_resultado + sem_resultado`; não retire falhas do total |
| `classes`, `erros_publicos`, `codigos_http`, `causas_de_rede` | Separe admissão, falha do serviço, autenticação e rede; soma das classes igual a `com_resultado` |
| `esperado`, `divergentes`, `acessos_recusados` | Compare com o plano, sem ampliar classes esperadas depois de observar falhas |
| `respostas_com_id_requisicao`, `tipos`, `respostas_ok_com_evidencia` | Presença de identificador, tipo e contagem de evidências; não avaliação semântica |
| `concorrencia`, `tempo_decorrido_s`, `limites` | Regime e prazo, incluindo `folga_de_encerramento_s`; não taxa de chegada |
| `latencia_ms_ok`, `latencia_ms_respostas_http` | `n`, mínima, mediana, p95 e máxima em milissegundos; separar `ok` de recusas rápidas |
| `aviso_latencia`, `limite` | Amostra pequena, não capacidade ou percentis de produção |
| `uso` | Soma parcial do informado e pedidos sem informação; não consumo total ou fatura |
| `status`, `interrupcao`, `codigo_de_saida` | `concluido` ou `interrompido`, causa de parada e decisão; término não oculta divergências |

Timeouts sem resposta HTTP ficam nas contagens, não nesses percentis. Não use a latência
curta de `ocupado` para anunciar consultas mais rápidas.
Se usou `--relatorio`, leia o arquivo novo na pasta privada. Ele acrescenta `inicio_utc` e
`fim_utc`, em UTC, tempo universal coordenado, origem e quantidade de perguntas, `tetos`,
hashes SHA-256, impressões digitais pelo algoritmo Secure Hash Algorithm de 256 bits,
`avisos` e `pedidos_detalhe`.
`perguntas.conferencia_com_avaliacoes` é `nao_se_aplica` para as embutidas, `feita` para
arquivo conferido ou `indisponivel` sem conjuntos para comparar; `comparadas_com_avaliacoes`
registra a quantidade, não o texto.

O arquivo é reservado antes da rede em criação exclusiva: nunca sobrescreve.
No Linux, a permissão `0600` permite leitura e escrita somente ao dono; no Windows, proteja
a pasta por suas permissões de acesso.
URL, token, identificadores, perguntas, respostas e textos de citações não entram no relatório
nem na linha de resultado. No Job deste roteiro, recolha a linha do console; não há cópia
persistente de relatório configurada. Um arquivo dentro do contêiner não aparece no computador.

**Resultado esperado:** resultado associado à execução correta, códigos e denominadores
conferidos e limites mantidos explícitos.
**Autorização, custo e limpeza:** ler arquivo local não consome modelos; consultar execução e
logs exige acesso de leitura, com possível cobrança de consulta/retenção. Guarde somente pelo
prazo autorizado; nenhuma nova carga é necessária para interpretar o que já existe.

### 7. Registrar sem expor conteúdo nem ocultar consumo

**Objetivo:** conservar evidência auditável com contagens e vocabulário fechado.

1. Registre classes, causas públicas, códigos, contagens, limites, uso informado e desconhecido.
   Conserve a distinção entre plano, dublê local, consulta de fumaça, geração Azure e contrato
   HTTP. O hash do gerador não identifica sozinho a revisão do servidor.
2. Mantenha inventário, associação da execução, horários detalhados e logs brutos **privados**.
   A sanitização do gerador não sanitiza mensagens da CLI, metadados do Job ou logs da plataforma.
   Não publique URL, token, IDs, caminhos privados, pergunta ou resposta.
3. Preserve `sem_resultado`, divergências e interrupções. `ocupado`, erros e ausência de uso
   informado contam como **consumo desconhecido**, não zero. A soma informada não comprova
   total faturado nem atendimento ao orçamento.

**Resultado esperado:** registro reduzido, com falhas e consumo incerto preservados;
nenhuma reconstrução de respostas ou repetição do conjunto final.
**Autorização, custo e limpeza:** registro local não chama serviços; retenção de logs tem custo
e prazo. A publicação da evidência sanitizada exige revisão; descarte cópias privadas somente
depois do prazo aprovado.

### 8. Encerrar temporários próprios

**Objetivo:** terminar a carga e retirar apenas o que foi criado para ela.

1. Confirme término das execuções e colete as linhas antes de remover o executor.
   Não confunda parar o cliente ou apagar o Job com cancelar uma consulta já entregue ao chat.
2. **[altera o Azure]** para excluir o Job próprio: siga
   [retirar temporários no D04](../L300/04-dependencias-privadas.md#8-retirar-os-temporários-quando-não-houver-consumidores),
   com alvo explícito, autorização de remoção e ausência conferida na listagem.
3. Coordene imagem, identidades e atribuições **novas** pelo
   [roteiro de limpeza do D07 L300](../L300/07-recuperar-limpar.md#etapa-3-revisar-os-alvos-da-limpeza).
   Excluir Job não apaga identidade atribuída ao usuário nem revoga seus papéis.
   Preserve chat, ambiente, fontes, índices e acessos preexistentes; não manipule o grupo gerenciado.
4. Confira retirada do token da sessão dedicada; os blocos locais usam `finally` para isso.
   Retire somente cópias locais próprias do contexto quando não houver consumidor,
   conservando relatórios pelo prazo aprovado.

**Resultado esperado:** Job temporário ausente, linha de base preservada e evidências retidas
pelo prazo definido.
**Autorização, custo e limpeza:** cada remoção exige aprovação de seu proprietário e alvos
inventariados. Serviços, imagem, rede e logs preservados podem continuar cobrando.
O [Desafio 07 L400](07-recuperar-limpar.md) coordena o encerramento mais amplo.

**Atenção à interrupção local:** o primeiro Ctrl+C para novos pedidos e espera os enviados
dentro do teto do programa; o segundo sai sem esperar. Tempo máximo ou falhas seguidas também
param novos envios. É como desligar o rádio do mensageiro: isso não recolhe o envelope já
entregue. **Pedido remoto já enviado pode consumir tokens**. O gerador não chama
`POST /api/perguntar/cancelar`; a prova desse comando e do SSE permanece na Etapa 2.

## Etapa 2: conferir progresso e cancelamento

1. Inicie uma pergunta e observe os eventos de etapa.
2. Confira que nenhum evento apresenta resposta bruta ou fonte fora do perfil.
3. Interrompa antes da próxima etapa.
4. Confira contagens de chamadas já enviadas e etapas não executadas.
5. Execute outra requisição e confirme que ela não foi cancelada por engano.

**Resultado esperado:** interrupção específica da requisição e ausência de novas chamadas.
Consumo incerto fica registrado; cancelar a interface não deve virar um resultado documentado.
Use uma sessão PowerShell dedicada, a `.venv` preparada no Desafio 01 e a pasta completa
aberta no VS Code. Os comandos locais abaixo não iniciam uma carga remota.

O fluxo SSE emite `etapa`, `tentativa` e `resumo` com metadados. Somente depois da política
há `resposta`; uma falha gera `erro`, e o fluxo termina em `fim`.
Sem a opção L400, essa rota é inexistente, com 404.
A interface usa um controlador de interrupção do navegador, `AbortController`; isso não
revoga tokens nem cancela instantaneamente o processamento remoto [4].
Na prova Azure, fechar somente a conexão não interrompeu o workflow a tempo através da borda.
Um cancelamento no programa exige sinal explícito autenticado.

No L400, a interface recebe do servidor o cabeçalho `X-Request-Id` e envia primeiro
`POST /api/perguntar/cancelar` com `{"id_requisicao":"<identificador>"}`. Somente o mesmo ator
autenticado pode pedir a interrupção; ele recebe 202, solicitação aceita. Uma identidade diferente,
execução ausente ou já encerrada recebe 404. A confirmação de interrupção vem depois,
no evento `erro` com `cancelado` e no encerramento do fluxo, não apenas no 202.

O botão aguarda a solicitação por no máximo cinco segundos e depois encerra a leitura no navegador.
Sem identificador, ou se o servidor não confirmar a solicitação, a mensagem informa que somente
a espera local foi interrompida. A pergunta, o perfil e o filtro não fazem parte do pedido de cancelamento.

O registro conserva somente execuções ativas, com validade e limite iguais aos controles do processo.
Não guarda perguntas ou respostas e usa uma assinatura interna do ator, sem expor seus identificadores.
O registro sai ao terminar ou cancelar a consulta. Nesta implementação, **o cancelamento explícito
depende de um único processo e uma réplica**. Não aumente esse número sem redesenhar o encaminhamento
e o registro; uma chamada enviada a outra réplica não encontra a execução.

Os prazos fixados são 30 segundos por chamada de modelo e 20 por busca ou embedding.
O prazo do workflow é o timeout do chat menos dois segundos, normalmente 88 segundos.
Busca e embeddings síncronos já enviados podem terminar depois do cancelamento;
não há execução da etapa seguinte nem apresentação da resposta cancelada.

Confira localmente:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_orquestracao.py
node --check web\app.js
```

## Etapa 3: observar falhas e isolamento

1. Exercite uma falha transitória controlada.
2. Exercite acesso negado sem troca de identidade.
3. Confira filtro por perfil em chamadas concorrentes.
4. Confira as dependências de dentro e de fora da rede.
5. Separe o resultado do dublê do resultado do Azure.

Depois do isolamento, o operador externo também pode receber 403 apesar de possuir papel
de dados. Origem de rede e permissão são provas distintas.

## Como pedir uma mudança ao Copilot no VS Code

Abra a prévia Markdown e o terminal na raiz do projeto; confira o interpretador `.venv`.
Anexe este guia, o gerador, servidor, contrato e testes públicos. Para planejar, use somente
um plano sanitizado, sem destino, IDs ou orçamento privado:

```text
Revise por leitura meu plano de carga L400 de desenvolvimento.
Confira pedidos, concorrência, prazos, folga de encerramento, parada e classes esperadas.
Separe teto de envios HTTP, chamadas internas aos modelos e orçamento aprovado.
Explique computador versus Job interno, autorização, custo e limpeza sem pedir dados privados.
Não execute carga, Azure ou rede; não crie identidades, papéis ou arquivos.
Não abra conjuntos finais nem transforme esta amostra em capacidade de produção.
```

Depois, anexe somente a linha de resultado ou relatório sanitizados, não os logs brutos:

```text
Confira este resultado L400 pelo contrato do gerador, sem executar comandos.
Confira denominadores, classes, códigos de saída, respostas com evidência e uso desconhecido.
Separe 429 ocupado, 503 indisponivel, recusas da borda e falhas de rede.
Explique laço fechado, p95 da amostra pequena e partida a frio com uma réplica.
Não invente respostas, custo total, aprovação do Job ou cancelamento remoto.
Não peça token, IDs, destino, logs brutos ou perguntas finais; não repita nenhuma chamada.
```

Para analisar o cancelamento específico da Etapa 2, conserve o pedido:

```text
Anexo servidor, contrato e testes de limites L400.
Siga duas requisições simultâneas e cancele somente uma delas.
Confira a admissão, as próximas etapas e o conteúdo dos eventos.
Não envie carga real, altere permissões ou copie perguntas para logs.
```

Revise o diff, comparação das alterações, em **Source Control**, controle de versões do VS Code,
a sintaxe JavaScript e os testes relacionados antes de qualquer execução autorizada.
O modelo escolhido pelo aluno no Copilot não precisa ser o modelo de autoria; ambos são
independentes dos deployments, instâncias de geração e embeddings da aplicação Azure.

## Conferência do resultado

Registre pedidos concluídos, falhas, recusas, cancelamentos, tempo e uso conhecido ou incerto.
Os logs do programa podem não incluir recusas interceptadas pela borda; os testes HTTP
precisam ser conservados separadamente.
Confira código do processo, linha final, denominadores e regime pelo passo 6; preserve
falha de rede fora do ingresso interno como falha de alcance, não como indisponibilidade provada.
Uma rodada com `--esperar "ok,ocupado"` pode terminar com código 0 e recusas:
isso confere a expectativa escolhida, não capacidade nem qualidade.

## Solução de problemas

| Sintoma | Ação |
| --- | --- |
| Cancelar uma pergunta interrompe outra | Corrija o estado por requisição |
| Modelo continua após cancelamento | Separe chamada já enviada de nova etapa indevida |
| Progresso contém texto livre | Mantenha somente eventos fechados até a política aprovar |
| Carga fica em repetição | O gerador não repete pedidos; confira executor, bibliotecas cliente e contingência do servidor |
| Plano termina com 0, sem linha de resultado | Comportamento esperado sem `--executar`; não é medição HTTP |
| Saída 1, sem envios | Confira limites, confirmação, token de variável e relatório novo em pasta existente |
| `falha_de_rede` com causa `dns`, sem HTTP, saída 2 | Use executor no caminho privado; não abra ingresso nem trate como falha do chat |
| Conexão depende de proxy ou certificado falha | Esta versão exige caminho direto e TLS válido; não desative verificação |
| HTTP 401/403, saída 2 | Confira audiência, identidade selecionada e papel de aplicação com o administrador; login e papéis de dados não bastam |
| HTTP 404 em todos os pedidos, latência de dezenas de milissegundos | Host interno errado, como falta de `.internal.`, responde na borda antes do chat; não é falha comprovada da aplicação. Releia `properties.configuration.ingress.fqdn` no ARM antes de autorizar outra execução |
| `ocupado` com concorrência 3 | Confira limite efetivo e outra carga; não aumente vagas ou réplica automaticamente |
| Concorrência 8 sem `ocupado` | Registre que a recusa não foi observada; confira sobreposição e regime, sem repetir para escolher resultado |
| HTTP 503 `indisponivel` | Separe prazo de 90 segundos, limite do modelo e demais causas privadas; não classifique como admissão |
| Job conclui sem `L400_CARGA_RESULTADO=` | Confira execução, comando, argumentos e logs pelo D04; `Succeeded` não aprova a carga |
| Processo sai com 4 e relatório fica incompleto | Preserve linha e erro sanitizados; confira gravação sem reenviar perguntas |

## Custos, pausa e limpeza

Defina a quantidade de chamadas antes do teste. Parar o cliente não remove serviços Azure.
Colete as evidências e encerre os temporários próprios; logs, busca e rede podem continuar cobrando.
Orçamento aprovado e aceitação `--confirmo-consumo` são controles distintos. Uma resposta sem uso
ou consulta de cobrança sem linhas não comprova custo zero. O gerador soma somente tokens
informados; não calcula fatura. Siga o passo 8 para o Job e os roteiros vinculados para
temporários administrativos, preservando recursos e acessos anteriores.

## Situação da validação

Progresso, limites e cancelamento passaram nos testes locais, inclusive desconexão com
servidor uvicorn real. Na rodada histórica Azure, **um helper privado diferente do gerador
público** enviou seis pedidos com concorrência três, com HTTP 200 e fonte operacional [11];
o SSE concluiu com resposta verificada. O cancelamento direto no workflow impediu
a busca posterior e preservou uso incerto do embedding em voo. Já a desconexão HTTP não
interrompeu a execução através da borda Azure. O reparo explícito passou em 100 testes de runtime
e na suíte integrada de 1.015 casos, com 1.014 aprovados e um ignorado no Windows.
A prova Azure confirmou outro ator recusado com 404, dono aceito com 202, fluxo cancelado sem
resposta e execução encerrada ausente. O log do servidor mostrou uma chamada de modelo,
zero buscas e uso incerto da chamada já enviada. Uma nova consulta funcionou depois.
O [registro L400](../../docs/validacao/l400-validacao.md) separa origem e alcance dessas provas,
sem tratá-las como objetivos de nível de serviço de produção.

**Revisão local anterior:** gerador testado com dublês, em 101 testes.
Foram executados `--help`, dois planos diretos e um plano pelo argumento único
do Python, todos sintéticos e sem `--executar`, com saída 0. A ajuda offline de
`az containerapp job start` confirmou suas opções; o parser local confirmou o argumento único,
sem invocar comandos de recursos. Passaram os 11 testes de repositório e de ausência de
perguntas finais solicitados; links e âncoras foram conferidos e os blocos PowerShell
analisados sintaticamente em memória, sem executá-los ou criar arquivo temporário.
A revisão local não enviou pedidos. A ferramenta generaliza e restringe a carga histórica,
sem reavaliar suas respostas.

**Rodada de validação de 11 de outubro de 2026:** o gerador público executou dentro do Job,
com token da identidade gerenciada, FQDN interno L400 e limite de admissão efetivo quatro.
O mecanismo `--command python --args` com um argumento Base64 foi exercitado; estado
e resultado foram lidos por execução, sem substituir a tentativa que falhou.

| Execução | Resultado observado |
| --- | --- |
| Tentativa com host sem `.internal.` | Cinco pedidos enviados, cinco HTTP 404 da borda, latências de 21 a 46 milissegundos; interrompida após três falhas seguidas, código 3, sem consumo de modelos. Falha de operação por host errado, não do chat |
| Rodada 1: seis pedidos, concorrência três, `--esperar ok` | Seis enviados, seis HTTP 200, zero divergentes, código 0, 41,9 segundos; cinco respostas `documentada` e uma `sem_evidencia` |
| Latências da rodada 1 | Mínima 4,7 segundos, mediana 6,2 segundos e p95 36,2 segundos; amostra pequena com partida a frio, não percentil de produção |
| Rodada 2: 12 pedidos, concorrência oito, `--esperar ok,ocupado` | 12 enviados, quatro `ok` com HTTP 200 e oito `ocupado` com 429; zero divergentes, código 0, 6,2 segundos. Admissão observada com limite quatro |

| Uso informado | Embeddings | Entrada de geração | Raciocínio | Saída de geração |
| --- | --- | --- | --- | --- |
| Rodada 1 | 115 tokens | 13.030 tokens | 535 tokens | 1.270 tokens |
| Rodada 2, quatro respostas `ok` | 74 tokens | 10.310 tokens | 410 tokens | 916 tokens |

As oito recusas da segunda rodada não informaram uso; conserve essa ausência, sem
transformá-la em custo zero. A soma informada é parcial, não fatura.
Código 0 confere a expectativa da carga; `sem_evidencia` não virou uma resposta documentada.
As amostras são pequenas e finitas: **não medem capacidade, percentis de produção,
fidelidade semântica ou homologação**. O progresso e o cancelamento históricos não foram
repetidos por essas cargas.

| Pendência | Responsável ou decisão necessária |
| --- | --- |
| Fase `isolar`, repetição pós-isolamento e negativas externas | Não executadas nem cobertas por esta rodada; o caminho privado observado não comprova funcionamento com acesso público dos dados fechado |
| Ingresso externo, login humano, implantação Actions/OIDC e federação | Não executados; OpenID Connect (OIDC) é o protocolo de identidade da implantação federada |
| Nova avaliação semântica e matriz Linux local | Não executadas; cargas de operação não substituem a revisão de conteúdo |
| Custo efetivo | Custo indisponível; estimativa do coordenador de poucos dólares, sem comprovar fatura ou teto estimado de US$ 30. Limpeza final concluída e aprovada |
| Outra rodada ou destino | Exige decisão própria; estas medições não autorizam repetição |

Os temporários históricos e os próprios desta rodada foram removidos, sem autorizar repetição.
Falhas, retomadas, resultados e limpeza aprovada estão no
[registro da rodada de 11 de outubro de 2026](../../docs/validacao/operacao-publica-azure-validacao-2026-10-11.md).

## Glossário e referências

| Termo | Significado |
| --- | --- |
| Concorrência | Pedidos executados simultaneamente |
| Admissão | Decisão de aceitar um pedido para execução |
| Laço fechado | Cada trabalhador espera a resposta para enviar o próximo pedido; não fixa taxa de chegada |
| `ocupado` | Recusa explícita de admissão do chat, com HTTP 429, sem fila |
| HTTP e HTTPS | Protocolo de comunicação web e sua forma com conexão protegida |
| URL | Endereço de um recurso, como o chat autorizado |
| FQDN e ARM | Nome completo de domínio lido do ingresso e serviço de administração Azure |
| JSON e ASCII | Formato de dados estruturados e conjunto básico de caracteres usado na linha final |
| Base64 e parser | Codificação de bytes como texto, não criptografia, e interpretador de argumentos |
| Latência e p95 | Duração observada e posição de percentil 95; nesta amostra pequena, p95 é o máximo |
| Réplica e partida a frio | Instância da aplicação e sua inicialização depois de escalar a zero |
| Timeout | Prazo máximo de espera |
| Job e execução | Definição de uma tarefa finita e uma rodada dessa tarefa no Container Apps |
| Identidade gerenciada, token e audiência | Identidade associada ao executor, token de acesso e aplicativo a que ele se destina |
| GUID | Identificador globalmente único; ID de cliente, objeto e recurso têm usos distintos |
| Tenant e papel de aplicação | Diretório de identidades e autorização de perfil para usar o chat |
| DNS, IP e TLS | Resolução de nomes, protocolo de internet e proteção da conexão |
| Proxy | Intermediário de rede; os proxies implícitos não são usados pelo gerador |
| CLI, build e ENTRYPOINT | Interface de linha de comando, construção da imagem e seu comando padrão de início |
| stdout e stderr | Saída padrão de resultados e fluxo separado de erros |
| KiB, UTF e BOM | Kibibyte, codificação de texto Unicode e marca de ordem de bytes |
| UTC e SHA-256 | Tempo universal coordenado e algoritmo de impressão digital dos arquivos |
| Uso informado e desconhecido | Tokens retornados pelo chat e consumo que a medição não consegue quantificar |
| Streaming | Envio progressivo de partes de uma resposta |
| SSE | Eventos enviados pelo servidor; o gerador de carga não usa essa rota |
| Evento de etapa | Informação de progresso sem conteúdo bruto |

1. [Respostas por geradores no FastAPI](https://fastapi.tiangolo.com/advanced/custom-response/).
2. [Eventos e requisições de workflows do Microsoft Agent Framework (MAF)](https://learn.microsoft.com/en-us/agent-framework/workflows/human-in-the-loop).
3. [Cotas dos modelos](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/quota).
4. [AbortController no navegador](https://developer.mozilla.org/en-US/docs/Web/API/AbortController).
5. [Jobs, comandos por execução e limites em Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/jobs).
6. [Identidade gerenciada em Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/managed-identity).
7. [Cobrança de Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/billing).
8. [Referência CLI de Container Apps Jobs](https://learn.microsoft.com/en-us/cli/azure/containerapp/job).
9. [Receita pública de executor, imagem, conclusão e logs no L300 D04](../L300/04-dependencias-privadas.md#etapa-3-aprovar-conexões-e-produzir-evidências).
10. [Contrato e limites do gerador público](../../scripts/gerar_carga_l400.py).
11. [Provas históricas e limites L400](../../docs/validacao/l400-validacao.md#execução-azure-e-correções).

## Autoria

Texto por GPT-6.1 Sol; código por Claude Sonnet 5.5. As ferramentas de autoria não medem o Azure.

Revisão documental por gpt-6-astra (Astra), em 11 de outubro de 2026, sem nova execução Azure.

Roteiro de carga: GPT-6.1 Sol, com Astra indisponível, em 11 de outubro de 2026; gerador público por Claude Sonnet 5.5; revisado por leitura; sem execução Azure.

Atualização pós-validação Azure de 11 de outubro de 2026: redigida por GPT-6.1 Sol com base nos fatos do coordenador; defeitos de código corrigidos com Sonnet 5.5; revisão do coordenador.
