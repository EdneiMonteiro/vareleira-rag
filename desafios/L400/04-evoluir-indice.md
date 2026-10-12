# L400 · Desafio 04: evoluir o índice sem perder a referência

[Início](../../README.md) · [Desafio 03](03-operar-deployments.md) · [Desafio 05](05-comparar-estrategias.md)

| Campo | Definição |
| --- | --- |
| Situação | Histórico preservado; candidato, promoção e retorno exercitados em 11 de outubro de 2026, com bloqueios do sanitizador e revisão humana; não é avaliação semântica |
| Público | Operações, arquitetura e desenvolvimento |
| Resultado | Reindexar em paralelo, registrar observações e promover/retornar pela fase aplicacao revisada |
| Custo | Reindexação recalcula embeddings; índices e serviços mantidos têm custos próprios |

## Conteúdo

- [Cenário](#cenário)
- [Objetivos](#objetivos)
- [Artefatos e disponibilidade](#artefatos-e-disponibilidade)
- [Tecnologias e conceitos](#tecnologias-e-conceitos)
- [Pré-requisitos](#pré-requisitos)
- [Etapa 1: identificar as duas configurações](#etapa-1-identificar-as-duas-configurações)
- [Etapa 2: reindexar em paralelo](#etapa-2-reindexar-em-paralelo)
- [Etapa 3: promover e retornar](#etapa-3-promover-e-retornar)
- [Como pedir uma mudança ao Copilot no VS Code](#como-pedir-uma-mudança-ao-copilot-no-vs-code)
- [Conferência do resultado](#conferência-do-resultado)
- [Solução de problemas](#solução-de-problemas)
- [Custos, pausa e limpeza](#custos-pausa-e-limpeza)
- [Situação da validação](#situação-da-validação)
- [Glossário e referências](#glossário-e-referências)
- [Autoria](#autoria)

## Cenário

O piloto fictício quer observar uma configuração de vetores menor sem modificar o índice que já
funciona. Teresa Moura exige que fontes e classes sejam preservadas; a equipe de operações
precisa de um retorno que não dependa de reconstruir a referência durante uma falha.

## Objetivos

1. Distinguir dimensão do vetor, modelo, versão e configuração do índice.
2. Criar um candidato separado com as mesmas fontes aprovadas.
3. Conferir recuperação e classes, além da contagem de trechos.
4. Testar promoção e retorno explícitos.

## Artefatos e disponibilidade

| Artefato | Uso e disponibilidade |
| --- | --- |
| [Gerenciador L300](../../scripts/gerenciar_ingestao_l300.py) | Disponível: criação, execução, conferência por leitura e remoção dos quatro objetos candidatos |
| [Manifesto](../../dados/l300/permissoes-documentais.json) | Disponível: quatro arquivos aprovados, hashes e classes, sem alterações nesta receita |
| [Definições da ingestão](../../scripts/lab_ingestao.py) e [ingestão L300](../../scripts/lab_ingestao_l300.py) | Disponíveis: índice, habilidade de embeddings, projeção e comparação de metadados |
| [Acesso documental](../../scripts/lab_acesso.py) | Disponível: filtro e validação dos trechos |
| [Operação L400](../../scripts/operar_l400.py) e [exemplos de testes](../../tests/test_operacao_l400.py) | Disponíveis: nomes exatos dos campos do descritor e dez conferências locais, sem coleta de observações |
| [Bicep L400](../../infra/l400.bicep) e [parâmetros](../../infra/levels/l400.bicepparam) | Disponíveis: perfil `referencia`/`candidato` na fase `aplicacao`, com as dimensões correspondentes |
| [Receita do Desafio 03](03-operar-deployments.md#receita-pública-implantar-por-fases) | Disponível: sessão, what-if, revisão, aplicação incremental e conferências |
| Receita desta página | Plano de migração, implantação incremental e consulta autenticada separados; aplicação L300 preservada |

Um **descritor** é um arquivo de dados preenchido na prática pelo operador com suas observações;
não é um relatório já entregue nem um coletor. Os exemplos dos testes são dublês, não medições.
Nenhuma declaração substitui leituras reais da definição, da ingestão e das consultas.

## Tecnologias e conceitos

**Embeddings** são vetores numéricos do texto. A **dimensão** é o número de posições de cada vetor.
O índice e a consulta precisam usar modelo, versão e dimensões compatíveis [1].

O exercício conserva `text-embedding-3-small`, versão `1`, e compara 1.536 com 768 dimensões.
O modelo permite esse intervalo [1]. Reduzir dimensões não comprova melhoria de qualidade,
latência ou custo do serviço; esses efeitos precisam de medição.

Alterar a estrutura do índice pode exigir reconstrução. Um índice separado permite experimentar
e retornar; um alias é outra estratégia possível, mas não é requisito deste exercício [2].
O caminho privado da aplicação não substitui as conexões de saída do indexador [3].

Um **pipeline** é a sequência que lê fontes, divide textos e gera trechos e vetores. A promoção
troca a configuração da aplicação, não os documentos. **Azure CLI** é a interface de linha de
comando que envia o Bicep ao **Azure Resource Manager (ARM)**, serviço de administração do Azure.
Seu **what-if**, simulação dos efeitos no destino, antecede a aplicação; o plano local não consulta
esse destino [4]. **Sanitização** reduz a saída privada sem comprovar seus alvos.
Uma **revisão** é a versão executável criada quando muda o template da aplicação [8].
**HTTP** (*Hypertext Transfer Protocol*) é o protocolo web; **HTTPS** protege sua conexão.
**JSON** (*JavaScript Object Notation*) é o formato de dados estruturados usado no descritor.

## Pré-requisitos

1. Use base e aplicação L300 preservadas, aplicação L400 já criada pelo
   [Desafio 03](03-operar-deployments.md), assinatura ativa, grupo exclusivo, região e orçamento
   autorizados. A execução histórica encerrada não permite repetir a rodada.
2. Tenha caminho de manutenção autorizado na rede privada e identidade com leitura das
   definições e trechos. Carga, reindexação, implantação ARM e exclusão exigem permissões e
   autorizações correspondentes, diferentes das da pessoa que entra no chat.
3. Conserve os destinos, a tag imutável, identidade, login e configurações aprovadas no
   Desafio 03. A imagem L400 precisa enviar a dimensão das consultas; uma imagem anterior
   sem essa implementação não serve para o candidato.
4. Use Visual Studio Code (VS Code) com a pasta completa, `.venv` e PowerShell 7. Prepare a pasta
   privada e os nomes novos dos arquivos de observação, descritor e relatório, fora do repositório.
5. Para reaplicar `aplicacao`, tenha a credencial vigente do login: informe-a novamente na
   sessão. O serviço não devolve seu valor por leitura; não o coloque em arquivo ou argumento.

Criação de objetos e reindexação **[altera o Azure]**. Simule os alvos e preserve a referência.
Não reabra serviços públicos para permitir que um terminal externo alcance os dados.
O roteiro pressupõe um executor de manutenção já autorizado; não cria uma sonda, identidade,
papel ou conexão privada. Sem esse caminho, a coleta real fica pendente e a promoção bloqueada.

## Etapa 1: identificar as duas configurações

| Configuração | Referência | Candidato |
| --- | --- | --- |
| Índice | `vareleira-lar-l300` | `vareleira-lar-l300-l400-768` |
| Dimensões | 1.536 | 768 |
| Modelo e versão | `text-embedding-3-small`, `1` | Os mesmos, com dimensão explícita |
| Fontes e classes | Quatro fontes aprovadas | As mesmas, com hashes conferidos |

O prefixo L300 do candidato mantém o contrato documental existente. O índice é separado
e não representa novas regras ou uma nova versão dos documentos.

```powershell
$indiceReferencia = "vareleira-lar-l300"
$indiceCandidato = "vareleira-lar-l300-l400-768"
.\.venv\Scripts\python.exe scripts\gerenciar_ingestao_l300.py --etapa validar
if ($LASTEXITCODE -ne 0) { throw "Manifesto e fontes locais não conferidos." }
```

**Resultado esperado:** quatro fontes aprovadas, arquivos e hashes locais conferidos, sem rede.
Isso não demonstra que o conteúdo já foi indexado no Azure.

## Etapa 2: reindexar em paralelo

1. Leia e registre a definição da referência.
2. Simule a criação dos quatro objetos do candidato.
3. Após autorização, crie e execute o indexador privado.
4. Confira dimensões do campo, da habilidade e das consultas.
5. Compare hashes, classes, contagens e perguntas de desenvolvimento.

O `gerenciar_ingestao_l300.py` recebe o índice e as dimensões explicitamente.
Primeiro confira o plano local:

```powershell
.\.venv\Scripts\python.exe scripts\operar_l400.py --etapa planejar --passo indice-candidato
```

Na rodada histórica o gerenciador foi usado por uma sonda privada. Na rodada de validação de
11 de outubro de 2026, sua interface pública rodou **dentro do Job**, pelo caminho abaixo.
Variáveis identificam o destino autorizado do aluno, não recursos do instrutor.
Recupere na sessão privada os nomes de `$busca`, `$grupo`, `$conta` e `$modelos`,
a assinatura em `$assinatura` e o identificador da identidade de manutenção em
`$clientIdManutencao`. Eles vêm do inventário próprio da base L300; o
[Desafio 03](03-operar-deployments.md#1-preparar-o-destino-e-a-sessão) define os demais destinos.
Um terminal comum do VS Code não passa a estar na rede privada por receber essas variáveis.
O terminal do operador só pode usar o caminho público dos dados **antes de esse acesso ser
fechado**, com sua credencial Azure CLI e seus papéis de dados; não use identidade gerenciada
num computador que não a possui. Depois do fechamento, é necessário um executor autorizado
na rede. A receita exercitada usou o Job, mesmo com os serviços ainda públicos.
Defina os destinos adicionais e arquivos novos de observação na pasta privada. Eles serão
produzidos pelas leituras abaixo, não são artefatos do repositório:

```powershell
$conta = Read-Host "Nome da conta de armazenamento L300 inventariada"
$clientIdManutencao = Read-Host "ID de cliente da identidade gerenciada de manutenção autorizada"
$referenciaAntes = Join-Path $pastaPrivada "referencia-antes.txt"
$referenciaDepois = Join-Path $pastaPrivada "referencia-depois.txt"
$candidatoDepois = Join-Path $pastaPrivada "candidato-depois.txt"
foreach ($arquivo in @($referenciaAntes, $referenciaDepois, $candidatoDepois)) {
    if (Test-Path -LiteralPath $arquivo) { throw "Escolha nomes novos; preserve as observações anteriores." }
}
```

### Executar o gerenciador dentro do Job

Reutilize o Job, as duas identidades, a imagem e `$variaveisBase` do
[L300 D04](../L300/04-dependencias-privadas.md#3-criar-um-job-manual-no-ambiente-l300).
`scripts/gerenciar_ingestao_l300.py` está na imagem da sonda. O
[mecanismo do L400 D06](06-testar-carga-interrupcao.md#4-executar-abaixo-do-limite-de-admissão)
troca o comando somente na execução, sem alterar permanentemente o Job.
Base64 é uma codificação de bytes como texto, **não criptografia**: os argumentos são
privados e não devem conter segredo.

**[altera o Azure]** ao iniciar cada execução do Job, mesmo para conferência ou plano.
Criar objetos e executar a ingestão exigem autorizações adicionais e consomem embeddings.
A função abaixo inicia uma execução e limita a espera a 900 segundos; terminar com
`Succeeded` ainda exige ler o console antes de prosseguir:

```powershell
function Iniciar-IngestaoNoJob {
    param([Parameter(Mandatory)][string[]]$Argumentos)
    $script:ultimaExecucaoIngestao = $null
    $lista = @("scripts/gerenciar_ingestao_l300.py") + $Argumentos
    $json = ConvertTo-Json -InputObject $lista -Compress
    $base64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($json))
    $entrada = "-cimport base64,json,runpy,sys; sys.path.insert(0,'scripts'); sys.argv=json.loads(base64.b64decode('$base64')); runpy.run_path(sys.argv[0],run_name='__main__')"
    $inicioJson = az containerapp job start --subscription $assinatura --resource-group $grupo `
        --name $job --container-name sonda --image $imagemSondaCompleta --cpu 0.25 --memory 0.5Gi `
        --env-vars @variaveisBase --command python --args=$entrada --output json
    if ($LASTEXITCODE -ne 0) { throw "Início não confirmado; confira as execuções antes de repetir." }
    $execucao = $inicioJson | ConvertFrom-Json
    $script:ultimaExecucaoIngestao = $execucao.name
    if (-not $execucao.name) { throw "Nome da execução não recuperado." }
    $limite = (Get-Date).AddSeconds(900)
    do {
        $estado = az containerapp job execution show --subscription $assinatura --resource-group $grupo `
            --name $job --job-execution-name $execucao.name --query properties.status --output tsv
        if ($LASTEXITCODE -ne 0) { throw "Estado não conferido; preserve a execução e leia os logs." }
        if ($estado -in @("Succeeded", "Failed")) { break }
        Start-Sleep -Seconds 5
    } while ((Get-Date) -lt $limite)
    if ($estado -ne "Succeeded") { throw "Execução falhou ou não terminou no prazo; confira o console privado." }
    return $execucao
}
$destinosIngestao = @(
    "--busca=$busca", "--assinatura=$assinatura", "--grupo=$grupo",
    "--conta=$conta", "--modelos=$modelos", "--identidade-gerenciada",
    "--client-id=$clientIdManutencao"
)
```

Os argumentos com valor usam `--opcao=valor`; os sinalizadores booleanos, como `--executar`,
não recebem valor. A lista inteira vira **um** argumento do Python. Confira imagem,
comando, argumentos e identidade na execução efetiva, como no D06.
Faça **uma linha por vez** da sequência exercitada; leia o console e autorize a próxima ação.
Para cada linha, atribua o retorno a `$execucao`:

| Ordem | Chamada com os destinos comuns | Observação da rodada |
| --- | --- | --- |
| 1. Referência antes | `$execucao = Iniciar-IngestaoNoJob -Argumentos ($destinosIngestao + @("--etapa=conferir", "--indice=$indiceReferencia", "--dimensoes=1536", "--privado"))` | Conferência aprovada, 24 trechos |
| 2. Plano do candidato | `$execucao = Iniciar-IngestaoNoJob -Argumentos ($destinosIngestao + @("--etapa=criar", "--indice=$indiceCandidato", "--dimensoes=768"))` | Sem `--executar`: quatro objetos a criar; revisar antes de autorizar |
| 3. Criar candidato | `$execucao = Iniciar-IngestaoNoJob -Argumentos ($destinosIngestao + @("--etapa=criar", "--indice=$indiceCandidato", "--dimensoes=768", "--executar"))` | Quatro objetos criados |
| 4. Indexar candidato | `$execucao = Iniciar-IngestaoNoJob -Argumentos ($destinosIngestao + @("--etapa=executar", "--indice=$indiceCandidato", "--executar", "--aguardar"))` | Quatro processados, zero falhas; `--aguardar` sem número usa 300 segundos |
| 5. Referência depois | `$execucao = Iniciar-IngestaoNoJob -Argumentos ($destinosIngestao + @("--etapa=conferir", "--indice=$indiceReferencia", "--dimensoes=1536", "--privado"))` | Conferência aprovada e referência preservada |
| 6. Candidato depois | `$execucao = Iniciar-IngestaoNoJob -Argumentos ($destinosIngestao + @("--etapa=conferir", "--indice=$indiceCandidato", "--dimensoes=768", "--privado"))` | 24 trechos, com as mesmas contagens por documento |

Não execute a tabela como um lote:
a aprovação do plano e a leitura do console são decisões entre as chamadas.
Prazo esgotado não cancela automaticamente o Job ou o indexador já iniciado; confira
o estado antes de autorizar uma retomada.

**Ler o console:** o gerenciador imprime texto, não uma linha `*_RESULTADO=`.
Reutilize a [API de Log Analytics do L300 D04](../L300/04-dependencias-privadas.md#5-ler-conclusão-e-resultado-separadamente),
mas filtre pelo grupo de contêineres dessa execução, não pelo prefixo da sonda.
KQL, *Kusto Query Language*, é a linguagem da consulta. Com `$customerId` já conferido,
escolha um arquivo novo na pasta privada:

```powershell
$nomeExecucao = $execucao.name
if ($nomeExecucao -notmatch "^[a-zA-Z0-9-]+$") { throw "Nome da execução não conferido." }
$arquivoKqlIngestao = Join-Path $pastaPrivada "$nomeExecucao-ingestao-kql.json"
@{
    query = "ContainerAppConsoleLogs_CL | where TimeGenerated > ago(3h) | where ContainerGroupName_s startswith '$nomeExecucao' | project TimeGenerated, Log_s | order by TimeGenerated asc"
} | ConvertTo-Json |
    Out-File -LiteralPath $arquivoKqlIngestao -Encoding utf8 -NoClobber -ErrorAction Stop
$consoleJson = az rest --method post `
    --url "https://api.loganalytics.io/v1/workspaces/$customerId/query" `
    --resource "https://api.loganalytics.io" --body "@$arquivoKqlIngestao" --output json
if ($LASTEXITCODE -ne 0) { throw "Console não recuperado; conferência pendente." }
$console = $consoleJson | ConvertFrom-Json
```

Cada linha de `tables[0].rows` traz horário e texto. Repita somente a leitura, com intervalo
e prazo limitados, enquanto os logs chegam; não reinicie a ingestão para refazer a coleta.
Confira o nome de execução e a completude do console. As contagens por documento do texto
são as observações usadas no descritor; não as substitua por números históricos.
Guarde console e associação somente em local privado. Se a função falhar, recupere o nome
em `$ultimaExecucaoIngestao` e conserve a tentativa antes de decidir a retomada.

Os comandos diretos nas subseções seguintes são a mesma interface para um executor que já
tenha o caminho e a credencial apropriados. Na rodada de validação de 11 de outubro de 2026,
essas etapas foram executadas pelo Job, não por um terminal comum fora da rede.

### Coletar a referência antes da reindexação

Esta conferência **só lê o Azure**. Inclua os quatro destinos para comparar também as definições
dos objetos, não apenas a dimensão do campo:

```powershell
.\.venv\Scripts\python.exe scripts\gerenciar_ingestao_l300.py --etapa conferir `
    --busca $busca --assinatura $assinatura --grupo $grupo --conta $conta --modelos $modelos `
    --indice $indiceReferencia --dimensoes 1536 --privado `
    --identidade-gerenciada --client-id $clientIdManutencao `
    *>&1 | Out-File -LiteralPath $referenciaAntes -Encoding utf8 -NoClobber -ErrorAction Stop
if ($LASTEXITCODE -ne 0) { throw "Referência inicial reprovada; preserve a saída privada e não reindexe." }
```

Confira antes que o caminho não existe, para não sobrescrever uma observação anterior.
Leia o arquivo apenas na sessão privada. Registre as contagens **por documento**, definições
conferidas e classes. As contagens históricas ou dos testes não substituem essa leitura.

### Criar e preencher o candidato

Simule a criação antes de enviar. O gerenciador consulta objetos existentes, mas não os grava
sem `--executar`; essa simulação não é o plano local sem rede:

```powershell
.\.venv\Scripts\python.exe scripts\gerenciar_ingestao_l300.py --etapa criar `
    --busca $busca --assinatura $assinatura --grupo $grupo --conta $conta --modelos $modelos `
    --indice $indiceCandidato --dimensoes 768 --identidade-gerenciada --client-id $clientIdManutencao
if ($LASTEXITCODE -ne 0) { throw "Plano do candidato reprovado." }
```

Depois de autorizar os alvos, **[altera o Azure]**:

```powershell
.\.venv\Scripts\python.exe scripts\gerenciar_ingestao_l300.py --etapa criar `
    --busca $busca --assinatura $assinatura --grupo $grupo --conta $conta --modelos $modelos `
    --indice $indiceCandidato --dimensoes 768 --identidade-gerenciada --client-id $clientIdManutencao --executar
if ($LASTEXITCODE -ne 0) { throw "Criação do candidato falhou." }
.\.venv\Scripts\python.exe scripts\gerenciar_ingestao_l300.py --etapa executar `
    --busca $busca --indice $indiceCandidato --identidade-gerenciada --client-id $clientIdManutencao `
    --executar --aguardar
if ($LASTEXITCODE -ne 0) { throw "Ingestão não concluída no prazo; não promova." }
```

A reindexação recalcula embeddings e ocupa o serviço de busca. Não corte vetores antigos nem
use `--substituir` para sobrescrever uma divergência sem revisar sua origem e os alvos.

### Coletar os dois índices depois da reindexação

As conferências **só leem**. Grave saídas novas e privadas, com os mesmos destinos e parâmetros
da criação:

```powershell
foreach ($arquivo in @($referenciaDepois, $candidatoDepois)) {
    if (Test-Path -LiteralPath $arquivo) { throw "Escolha arquivos novos de observação." }
}
.\.venv\Scripts\python.exe scripts\gerenciar_ingestao_l300.py --etapa conferir `
    --busca $busca --assinatura $assinatura --grupo $grupo --conta $conta --modelos $modelos `
    --indice $indiceReferencia --dimensoes 1536 --privado `
    --identidade-gerenciada --client-id $clientIdManutencao `
    *>&1 | Out-File -LiteralPath $referenciaDepois -Encoding utf8 -NoClobber -ErrorAction Stop
if ($LASTEXITCODE -ne 0) { throw "Referência depois da reindexação reprovada." }
.\.venv\Scripts\python.exe scripts\gerenciar_ingestao_l300.py --etapa conferir `
    --busca $busca --assinatura $assinatura --grupo $grupo --conta $conta --modelos $modelos `
    --indice $indiceCandidato --dimensoes 768 --privado `
    --identidade-gerenciada --client-id $clientIdManutencao `
    *>&1 | Out-File -LiteralPath $candidatoDepois -Encoding utf8 -NoClobber -ErrorAction Stop
if ($LASTEXITCODE -ne 0) { throw "Candidato reprovado; promoção bloqueada." }
```

Na sessão Azure CLI do operador, pelo caminho privado autorizado, substitua as opções de
identidade gerenciada por `--tenant-id $tenant`, recebendo `$tenant` do inventário; não combine
os mecanismos. A localização da sessão e os papéis de dados continuam necessários.

**Resultado esperado:** `Conferência aprovada.` nos três registros, quatro objetos presentes e
definidos, indexador `private`, última execução sem falhas/erros e avisos investigados.
O campo vetorial e a habilidade têm a dimensão escolhida; as quatro fontes têm metadados completos,
hashes e classes do manifesto. Referência antes/depois e candidato depois têm a mesma contagem
**por documento**. `secao` e `clausulas` continuam vazios nesta ingestão.

## Etapa 3: promover e retornar

Esta receita separa a conferência local das operações Azure e conserva autorização por ação.
As execuções históricas no [registro L400](../../docs/validacao/l400-validacao.md) usaram helpers
privados diferentes. A aplicação convencional L300 continua sempre na referência.

**Para guardar na memória:** índice e cliente são como tomada e plugue com a mesma disposição
de contatos. Trocar a etiqueta da tomada não adapta o plugue. Mudar só uma variável não comprova
compatibilidade: documentos reindexados e consultas também precisam produzir 768 posições.

### 1. Preencher o descritor com as leituras

Leia novamente os deployments pelo
[comando do Desafio 03](03-operar-deployments.md#4-conferir-a-contingência-por-leitura) para
registrar nome, modelo e versão atuais. Compare o deployment de embeddings com o empregado nas
definições conferidas. A habilidade declara modelo/deployment e dimensão, **não uma versão
independente do modelo**: a versão vem do deployment, conservado fixo durante a ingestão.
Se ele mudou no intervalo, a leitura atual não reconstrói a origem dos vetores; preserve a
divergência e não declare compatibilidade.

Crie `$descritorPrivado` como arquivo JSON na pasta privada. Os campos abaixo são os nomes
exatos aceitos por `operar_l400.py` [9]; não acrescente endereços, perguntas, tokens ou campos de comentário:

| Campo da raiz | Preenchimento |
| --- | --- |
| `versao` | Inteiro `1` |
| `origem` | `operador` somente com observações reais; `simulado` para dublês |
| `acao` | `promover` ou `retornar` |
| `manifesto_deployment` | Objetos `embeddings`, `geracao_principal` e `geracao_contingencia`; cada um contém apenas `deployment`, `modelo`, `versao`, como textos lidos nos deployments |
| `configuracao_atual` e `configuracao_alvo` | Cada objeto contém `indice`, `dimensoes` (inteiro) e `deployment_embeddings`; a atual é lida na aplicação, a alvo corresponde ao índice conferido |
| `indices` | Objetos `referencia` e `candidato`, com todos os campos da tabela seguinte |

| Campo de cada índice | Observação que o sustenta |
| --- | --- |
| `indice` | Nome passado à conferência e confirmado nos objetos |
| `dimensoes` | Inteiro: 1536 ou 768, conforme definição vetorial e habilidade comparadas com todos os destinos informados |
| `modelo_embeddings`, `versao_modelo_embeddings` | Modelo e versão do deployment usado na ingestão, iguais ao manifesto de deployment |
| `origem_observada` | `operador` para leitura real; `simulado` para dublê, coerente com a raiz |
| `fontes` | Lista de quatro objetos, cada um apenas com `documento_id`, `classe` e `sha256` |
| `contagem_antes` | Na referência, objeto `{"por_documento": {...}}` com as contagens de `$referenciaAntes`; no candidato, o campo é obrigatório, mas pode ser `null` |
| `contagem_depois` | Objeto `{"por_documento": {...}}` com as contagens de `$referenciaDepois` ou `$candidatoDepois` |

Faça o mapeamento das saídas do gerenciador:

1. **Definições dos objetos** e **Compatibilidade com o recuperador do L100** aprovadas sustentam
   nome, campo vetorial, perfil, dimensão e habilidade definidos. Informe todos os destinos:
   a mensagem “Definições não comparadas” é evidência incompleta, mesmo que outras linhas passem.
2. **Trechos do índice** traz o total e pares documento/quantidade. Em `por_documento`, use os
   identificadores `VLAR-CG-1.0`, `VLAR-GL-1.0`, `VLAR-FAQ-1.0` e `VLAR-OP-ATD-1.0` como chaves
   e as quantidades **observadas** como inteiros, não a contagem total repetida para cada fonte.
3. **Classe de acesso dos trechos** e completude aprovadas conferem classes, versões e hashes
   de metadados contra o manifesto. Só depois dessa igualdade, transcreva do manifesto
   `documentos[].id` → `documento_id`, `acesso` → `classe` e `sha256` → `sha256`.
   O resumo não imprime cada hash: não invente valores nem copie hashes de exemplo.
4. **Indexador: última execução** e **Ambiente de execução do indexador** registram a ingestão.
   Guarde essas provas fora do descritor: ele não tem campos para estado, erro, aviso ou conteúdo.

Os hashes são metadados da fonte comparados com arquivos locais aprovados, não uma medição
semântica dos vetores. A conferência não gera vetores de consulta nem avalia a resposta do chat.

| Ação | Configuração atual → alvo |
| --- | --- |
| `promover` | Referência, 1536 → candidato, 768 |
| `retornar` | Candidato, 768 → referência, 1536 |

Nas duas configurações, `deployment_embeddings` continua o mesmo. Os exemplos de
[`test_operacao_l400.py`](../../tests/test_operacao_l400.py) explicam a forma; suas contagens e
modelo de geração fictício **não são valores de uma observação Azure**.

### 2. Conferir a migração localmente

Escolha o descritor de entrada e `$relatorioMigracao` como caminho novo na pasta privada.
Confira o descritor antes da troca:

```powershell
$descritorPrivado = Read-Host "Caminho privado do descritor preenchido"
$relatorioMigracao = Read-Host "Caminho novo do relatório de migração, terminado em .json"
.\.venv\Scripts\python.exe scripts\operar_l400.py --etapa conferir-migracao `
    --descritor $descritorPrivado --relatorio $relatorioMigracao
if ($LASTEXITCODE -ne 0) { throw "Descritor reprovado ou inválido; troca bloqueada." }
$migracao = Get-Content -LiteralPath $relatorioMigracao -Raw | ConvertFrom-Json
if ($migracao.resultado -ne "aprovado" -or $migracao.origem_do_descritor -ne "operador") {
    throw "Exemplo simulado não libera uma troca real."
}
```

**Resultado esperado:** dez conferências atendidas e nenhuma reprovada, segundo os campos
declarados. Código 1 indica forma/entrada inválida; código 3 indica divergência.
Um descritor `simulado` pode obter código zero, mas continua **sem valor como prova real**.
O campo `evidencia_azure` fica `false` mesmo para `operador`: o helper não consulta Azure.
Não altere origem, contagens ou hashes para obter aprovação; investigue a observação ou a ingestão.

### 3. Preparar a promoção sem mudar o ingresso

O restante da receita usa as variáveis de sessão do Desafio 03. Receba o nome L400 do inventário
daquela implantação, não o da aplicação L300:

```powershell
$aplicacaoL400 = Read-Host "Nome da aplicação L400 conferida no inventário"
if (-not $aplicacaoL400 -or $aplicacaoL400 -eq $aplicacaoL300) { throw "Alvo L400 não conferido." }
$acaoMigracao = "promover"
if ($migracao.acao -ne $acaoMigracao) { throw "Descritor não corresponde à promoção." }
$appAntes = az containerapp show --subscription $assinatura --resource-group $grupo `
    --name $aplicacaoL400 --output json | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) { throw "Leitura inicial da aplicação falhou." }
$ingressoAntes = $appAntes.properties.configuration.ingress | ConvertTo-Json -Depth 20 -Compress
if ($appAntes.properties.configuration.ingress.external -notin @($true, $false)) {
    throw "Ingresso atual não identificado."
}
$env:VARELEIRA_L400_FASE = "aplicacao"
$env:VARELEIRA_L400_PERFIL_INDICE = "candidato"
$env:VARELEIRA_L400_INGRESSO_EXTERNO = ([bool]$appAntes.properties.configuration.ingress.external).ToString().ToLowerInvariant()
.\.venv\Scripts\python.exe scripts\operar_l400.py --etapa planejar --passo promover-indice
if ($LASTEXITCODE -ne 0) { throw "Plano local da promoção falhou." }
```

Esse bloco **só lê Azure e altera a sessão local**, não a aplicação. Preserve tag, repositório,
modelo, versão, identidade, modo de busca, quantidade de trechos, esforço, escala e login.
Confira que `configuracao_atual` do descritor corresponde a `VARELEIRA_INDICE`,
`VARELEIRA_DIMENSOES` e `VARELEIRA_DEPLOYMENT_EMBEDDINGS` lidos em `template.containers[0].env`.
Conserve o tenant e a ação sem login já conferidos por `az containerapp auth show`.
Se houver divergência em relação ao Bicep, pare para revisão; a fase reaplica a configuração
declarada, não somente duas variáveis.

### 4. Simular, sanitizar e aplicar a troca autorizada

1. Escolha nome de implantação e arquivos novos em `$pastaPrivada`, seguindo o mesmo padrão do
   [Desafio 03](03-operar-deployments.md#2-simular-e-revisar-o-what-if). O relatório de what-if
   não sobrescreve o de migração. Use prefixo próprio, como
   `vareleira-rag-l400-aplicacao-<sufixo-novo>`; o nome raiz não pode coincidir com módulos
   aninhados `l400-aplicacao`, `l400-contingencia` ou `l400-guardas`:

```powershell
$implantacao = Read-Host "Nome novo da implantação ARM para esta troca"
if ($implantacao -in @("l400-aplicacao", "l400-contingencia", "l400-guardas")) {
    throw "Nome raiz coincide com um módulo; escolha prefixo próprio e novo."
}
$arquivoWhatIf = Join-Path $pastaPrivada "$implantacao-whatif.json"
$novoRelatorio = Join-Path $pastaPrivada "$implantacao-resumo.json"
$erroWhatIf = Join-Path $pastaPrivada "$implantacao-whatif-erros.txt"
$erroImplantacao = Join-Path $pastaPrivada "$implantacao-implantacao-erros.txt"
$erroEspera = Join-Path $pastaPrivada "$implantacao-espera-erros.txt"
foreach ($arquivo in @($arquivoWhatIf, $novoRelatorio, $erroWhatIf, $erroImplantacao, $erroEspera)) {
    if (Test-Path -LiteralPath $arquivo) { throw "Escolha caminhos novos; preserve os anteriores." }
}
Remove-Item Env:\VARELEIRA_QUALIFICAR_NAO_SUPORTADO, Env:\VARELEIRA_QUALIFICAR_PROPRIEDADES_REMOVIDAS, Env:\VARELEIRA_PLANO_SHA256 -ErrorAction SilentlyContinue
```

2. Receba a credencial vigente novamente, pois o serviço não devolve o segredo de login:

```powershell
try {
    $env:VARELEIRA_SEGREDO_LOGIN = Read-Host "Credencial vigente do mesmo login aprovado" -MaskInput
    az deployment group what-if --subscription $assinatura --resource-group $grupo `
        --name $implantacao --parameters infra\levels\l400.bicepparam --mode Incremental `
        --result-format FullResourcePayloads --no-pretty-print --no-prompt true --output json `
        2> $erroWhatIf | Out-File -LiteralPath $arquivoWhatIf -Encoding utf8 -NoClobber -ErrorAction Stop
    if ($LASTEXITCODE -ne 0) { throw "What-if falhou; não aplique." }
    .\.venv\Scripts\python.exe scripts\operar_l400.py --etapa sanitizar-whatif `
        --arquivo $arquivoWhatIf --relatorio $novoRelatorio --rotulo $acaoMigracao
    $codigoSanitizacao = $LASTEXITCODE
    if ($codigoSanitizacao -notin @(0, 3)) { throw "Sanitização inválida; não aplique." }
    if ($codigoSanitizacao -eq 3) { Write-Warning "Troca bloqueada; revise a causa antes de qualificar." }
}
finally {
    Remove-Item Env:\VARELEIRA_SEGREDO_LOGIN -ErrorAction SilentlyContinue
}
```

#### Se o sanitizador bloquear por propriedades removidas

**O bloqueio é parte da conferência, não uma falha a esconder.** Na rodada de validação
de 11 de outubro de 2026, o what-if de uma aplicação **existente** trouxe dois `Modify`:
aplicativo L400 e `authConfigs`, sua configuração de autenticação. O sanitizador retornou
código 3 até a revisão humana das propriedades removidas e a qualificação exata.
Qualificar remoções de **propriedades** não permite `Delete` de recurso.

| Troca | Aplicativo | Autenticação |
| --- | --- | --- |
| Promoção | Cinco padrões removidos: `ingress.exposedPort`, `ingress.traffic`, `maxInactiveRevisions`, `scale.cooldownPeriod` e `scale.pollingInterval` | Uma remoção: `isAutoProvisioned` |
| Retorno | Quatro: os mesmos, exceto `maxInactiveRevisions`, que já não aparecia na leitura após promover | Uma remoção: `isAutoProvisioned` |

Essas remoções foram classificadas como padrões do serviço **naquela revisão**. A quantidade
mudou entre promoção e retorno; releia todos os deltas a cada simulação. Não qualifique por
nome ou quantidade copiados deste exemplo para vencer um bloqueio.

No terminal privado, o apoio abaixo achata `delta` e seus `children`, mostrando caminho,
tipo e antes → depois. GUIDs, identificadores globalmente únicos, são mascarados;
campos de segredo e textos não reconhecidos são ocultados. Objetos/listas também não
são despejados no console. Valores omitidos exigem revisão do bruto na pasta privada,
sem anexá-lo ao Copilot ou publicar seus conteúdos:

```powershell
$padraoGuid = "(?i)[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}"
function Valor-DeltaVisivel {
    param($Valor, [string]$Caminho)
    if ($Caminho -match "(?i)secret|password|token|senha|credential|connectionstring") { return "<oculto>" }
    if ($null -eq $Valor) { return "<ausente>" }
    if ($Valor -is [bool] -or $Valor -is [int] -or $Valor -is [long] -or
        $Valor -is [double] -or $Valor -is [decimal]) { return [string]$Valor }
    if ($Valor -is [string]) {
        $mascarado = [regex]::Replace($Valor, $padraoGuid, "<GUID>")
        if ($mascarado -eq "<GUID>") { return $mascarado }
        if ($Valor -in @("vareleira-lar-l300", "vareleira-lar-l300-l400-768", "1536", "768",
            "VARELEIRA_INDICE", "VARELEIRA_DIMENSOES")) { return $Valor }
        if ($Valor.StartsWith("[") -and $Valor.EndsWith("]")) { return "<expressão ARM>" }
        return "<texto privado omitido>"
    }
    return "<objeto/lista: revisão privada>"
}
function Mostrar-Delta {
    param($Deltas, [string]$Prefixo = "")
    foreach ($no in @($Deltas)) {
        if ($null -eq $no) { continue }
        $caminho = if ($Prefixo) { "$Prefixo.$($no.path)" } else { [string]$no.path }
        $visivel = [regex]::Replace($caminho, $padraoGuid, "<GUID>")
        if ($visivel -match "://|/subscriptions/|/resourceGroups/") { $visivel = "<caminho privado>" }
        $antes = Valor-DeltaVisivel -Valor $no.before -Caminho $caminho
        $depois = Valor-DeltaVisivel -Valor $no.after -Caminho $caminho
        "{0} | {1} | {2} -> {3}" -f $visivel, $no.propertyChangeType, $antes, $depois
        Mostrar-Delta -Deltas $no.children -Prefixo $caminho
    }
}
$planoArm = Get-Content -LiteralPath $arquivoWhatIf -Raw | ConvertFrom-Json
foreach ($mudanca in $planoArm.changes) {
    if ($mudanca.resourceId -match "/providers/Microsoft.App/containerApps/") {
        Mostrar-Delta -Deltas $mudanca.delta
    }
}
```

O apoio **não aprova nem classifica automaticamente** a mudança. Registre a revisão humana:

| Classe da revisão | O que foi encontrado e como conferir |
| --- | --- |
| ALVO | Troca conjunta de `VARELEIRA_INDICE` e `VARELEIRA_DIMENSOES` para o par conferido |
| RUÍDO de expressão ARM não resolvida | Três expressões: servidor do registro, imagem e `clientId`; comparar os valores efetivos antes/depois, sem aceitar a expressão como prova de igualdade |
| RUÍDO de ordem | 11 deltas de propriedades individuais das três sondas de saúde, trocadas de posição; comparar o **conjunto** completo, não apenas a posição das sondas |
| PADRÃO removido | Cada propriedade da tabela de remoções, revisada no estado real e no bruto; remoção não explicada mantém o bloqueio |

Depois de explicar cada delta e registrar a aprovação de **dois `Modify`**, informe as
quantidades **lidas nessa revisão**. Na promoção foram cinco e um; no retorno, quatro e um.
O sanitizador exige o tipo e a quantidade exata, e o relatório qualificado precisa ser novo:

```powershell
$n = [int](Read-Host "Remoções no aplicativo, contadas e aprovadas nesta simulação")
$m = [int](Read-Host "Remoções na autenticação, contadas e aprovadas nesta simulação")
$qualificacao = "Microsoft.App/containerApps=$n,Microsoft.App/containerApps/authConfigs=$m"
$relatorioQualificado = Join-Path $pastaPrivada "$implantacao-resumo-qualificado.json"
.\.venv\Scripts\python.exe scripts\operar_l400.py --etapa sanitizar-whatif `
    --arquivo $arquivoWhatIf --relatorio $relatorioQualificado --rotulo $acaoMigracao `
    --qualificar-propriedades-removidas $qualificacao
if ($LASTEXITCODE -ne 0) { throw "Qualificação recusada; a troca permanece bloqueada." }
$novoRelatorio = $relatorioQualificado
```

Essa chamada não altera Azure. Conserve o relatório bloqueado, a justificativa da revisão
e o novo relatório; não edite o bruto. Código 0 significa que a qualificação declarada
confere com as contagens, **não uma aprovação automática dos efeitos**. Para aplicar,
continue as conferências de escopo e tipo abaixo e, depois, exija as provas positivas
do passo 5. Uma simulação nova exige revisão nova, inclusive no retorno.

3. Execute as conferências locais de escopo, ações e contagem de `Modify` do
   [Desafio 03](03-operar-deployments.md#2-simular-e-revisar-o-what-if), com as variáveis desta
   simulação. Todo `resourceId` fica no grupo exclusivo.
   Recuse `Delete`, `Deploy`, `Unsupported`, tipo inesperado ou efeito não resolvido. O resumo
   aprovado não faz essa revisão por você.
4. No bruto privado, a troca altera **a aplicação L400 existente**, não cria outra. O alvo
   `Microsoft.App/containerApps` precisa ter o nome inventariado; autenticação e módulos ARM
   são os da mesma fase. Reveja cada `Modify` e aprove quantidade exata por tipo e propriedade.
   Índice/dimensão mudam juntos; ingresso, imagem, autenticação, identidade, escala e aplicação
   L300 continuam iguais. Mudança fora desse escopo impede a promoção.
5. **[altera o Azure]**: somente após autorização e revisão, aplique a mesma fase/valores do
   plano, com a mesma credencial vigente. A nova revisão tem efeitos de processamento e pode
   gerar cobrança; preserve a referência e o candidato durante a prova:

```powershell
$resumoWhatIf = Get-Content -LiteralPath $novoRelatorio -Raw | ConvertFrom-Json
$hashWhatIf = (Get-FileHash -LiteralPath $arquivoWhatIf -Algorithm SHA256).Hash.ToLowerInvariant()
if ($resumoWhatIf.decisao.codigo -ne 0 -or $hashWhatIf -ne $resumoWhatIf.bruto_sha256) {
    throw "Plano bloqueado ou bruto alterado depois da sanitização."
}
try {
    $env:VARELEIRA_SEGREDO_LOGIN = Read-Host "Mesma credencial vigente do what-if revisado" -MaskInput
    az deployment group create --subscription $assinatura --resource-group $grupo `
        --name $implantacao --parameters infra\levels\l400.bicepparam --mode Incremental `
        --no-prompt true --no-wait --output none 2> $erroImplantacao
    if ($LASTEXITCODE -ne 0) { throw "Pedido de troca falhou." }
}
finally {
    Remove-Item Env:\VARELEIRA_SEGREDO_LOGIN -ErrorAction SilentlyContinue
}
az deployment group wait --subscription $assinatura --resource-group $grupo `
    --name $implantacao --created --interval 15 --timeout 1200 --output none 2> $erroEspera
if ($LASTEXITCODE -ne 0) { throw "Troca não confirmada no prazo; leia o estado antes de recuperar." }
$estadoArm = az deployment group show --subscription $assinatura --resource-group $grupo `
    --name $implantacao --query properties.provisioningState --output tsv
if ($LASTEXITCODE -ne 0 -or $estadoArm -ne "Succeeded") { throw "Conclusão ARM não comprovada." }
```

O aceite de `--no-wait` não é conclusão. Prazo esgotado não cancela uma operação remota [5].
O modo `Complete` fica fora da receita; poderia remover a base não declarada por essa fase.
Não imprima `az bicep build-params --stdout` com valores reais. O bruto e os erros podem conter
segredo ecoado, mesmo com parâmetro seguro: mantenha-os privados e apague-os após a revisão.

### 5. Conferir a revisão e exigir a prova autenticada

Conserve `$appAntes` e as observações L300 anteriores à aplicação. A revisão precisa
demonstrar **positivamente** os itens abaixo; “não apareceu no resumo” não prova preservação:

| Item | Comparação depois de aplicar |
| --- | --- |
| ALVO | Índice e dimensão iguais à configuração alvo do descritor |
| Demais variáveis | Mesmos nomes e valores de todas as variáveis anteriores, exceto `VARELEIRA_INDICE` e `VARELEIRA_DIMENSOES` |
| Imagem e registro | Mesma imagem e configuração efetiva do registro; expressões não resolvidas no what-if não dispensam a comparação |
| Sondas | Mesmo conjunto das três definições, independentemente da ordem |
| Escala, identidade e ingresso | Configurações efetivas anteriores preservadas; explicar separadamente os padrões removidos |
| Revisão | Revisão atual pronta, não apenas pedido de implantação aceito |
| Referência L300 | Aplicação, revisão e ingresso preservados, além da definição e contagens do índice |

Na rodada de validação de 11 de outubro de 2026, essas comparações foram registradas nas duas
direções, e a quantidade de `Modify` aprovada foi dois. Isso não dispensa revisão humana
nem autoriza outro destino. Guarde diferenças e justificativas somente em local privado.

As leituras abaixo não exibem segredos. O limite de dez minutos é uma janela operacional de
conferência, não garantia de prontidão:

```powershell
$limiteRevisao = (Get-Date).AddMinutes(10)
do {
    $appDepois = az containerapp show --subscription $assinatura --resource-group $grupo `
        --name $aplicacaoL400 --output json | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0) { throw "Leitura após a troca falhou." }
    $p = $appDepois.properties
    $pronta = $p.provisioningState -eq "Succeeded" -and $p.latestRevisionName -and
        $p.latestRevisionName -eq $p.latestReadyRevisionName
    if ($p.provisioningState -in @("Failed", "Canceled")) { throw "Revisão terminou sem sucesso." }
    if ($pronta) { break }
    Start-Sleep -Seconds 5
} while ((Get-Date) -lt $limiteRevisao)
if (-not $pronta) { throw "Revisão não pronta no prazo." }
$ingressoDepois = $p.configuration.ingress | ConvertTo-Json -Depth 20 -Compress
if ($ingressoDepois -ne $ingressoAntes) { throw "Ingresso mudou; troca não aprovada." }
$variaveisApp = @{}
foreach ($item in $p.template.containers[0].env) { $variaveisApp[$item.name] = $item.value }
$alvo = (Get-Content -LiteralPath $descritorPrivado -Raw | ConvertFrom-Json).configuracao_alvo
if ($variaveisApp["VARELEIRA_INDICE"] -ne $alvo.indice -or
    $variaveisApp["VARELEIRA_DIMENSOES"] -ne [string]$alvo.dimensoes -or
    $variaveisApp["VARELEIRA_DEPLOYMENT_EMBEDDINGS"] -ne $alvo.deployment_embeddings -or
    $variaveisApp["VARELEIRA_EXIGIR_AUTENTICACAO"] -ne "true" -or
    $variaveisApp["VARELEIRA_EXIGIR_ACESSO_DOCUMENTAL"] -ne "true" -or
    $variaveisApp["VARELEIRA_EXIGIR_COORDENACAO"] -ne "true") {
    throw "Configuração da aplicação não corresponde ao alvo conferido."
}
$outrasAntes = @($appAntes.properties.template.containers[0].env |
    Where-Object { $_.name -notin @("VARELEIRA_INDICE", "VARELEIRA_DIMENSOES") } | Sort-Object name)
$outrasDepois = @($p.template.containers[0].env |
    Where-Object { $_.name -notin @("VARELEIRA_INDICE", "VARELEIRA_DIMENSOES") } | Sort-Object name)
if ((ConvertTo-Json -InputObject $outrasAntes -Depth 10 -Compress) -ne
    (ConvertTo-Json -InputObject $outrasDepois -Depth 10 -Compress)) {
    throw "Outras variáveis mudaram; migração não aprovada."
}
az containerapp revision list --subscription $assinatura --resource-group $grupo `
    --name $aplicacaoL400 --all `
    --query "[].{revisao:name,ativa:properties.active,saude:properties.healthState,estado:properties.provisioningState}" `
    --output table
if ($LASTEXITCODE -ne 0) { throw "Listagem das revisões falhou." }
$authDepois = az containerapp auth show --subscription $assinatura --resource-group $grupo `
    --name $aplicacaoL400 --output json | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) { throw "Autenticação não conferida após a troca." }
```

Confira no resultado de autenticação plataforma habilitada, conexão protegida, ação sem login,
tenant/emissor, cliente e audiência anteriores. Leia também a aplicação L300 e os dois índices:
configuração convencional, definição, fontes e contagens da referência continuam intactas [6][7].
Revisão pronta não comprova consulta vetorial.

Uma **consulta autenticada separada é obrigatória** antes de considerar a promoção ou o retorno
concluídos. Use uma pergunta de desenvolvimento sustentada pelas fontes sintéticas, nunca os
conjuntos finais. Receba um token autorizado para o chat, com tenant e papel reconhecidos, por
procedimento aprovado; não crie credencial ou amplie papéis para executar esta prova.
**Token** é o comprovante digital de autenticação. Quando o ingresso é interno, execute a
consulta de dentro do ambiente Container Apps autorizado; o terminal externo não ganha esse acesso.
O host interno inclui `.internal.`; leia o FQDN (*Fully Qualified Domain Name*, nome completo
de domínio) em `properties.configuration.ingress.fqdn`, sem montar `<app>.<domínio>`.
O bloco requer PowerShell 7 nesse executor autorizado. Se ele só dispõe de outro cliente HTTP,
use o cliente previamente aprovado e registre as mesmas provas; o guia não instala ferramentas
nem cria um executor para alcançar o endereço interno.

```powershell
$urlChat = "https://" + $appDepois.properties.configuration.ingress.fqdn
if (-not $appDepois.properties.configuration.ingress.fqdn) { throw "FQDN real não conferido." }
try {
    $env:VARELEIRA_L400_TOKEN_COORDENACAO = Read-Host "Token autorizado do chat L400" -MaskInput
    $perguntaDesenvolvimento = Read-Host "Pergunta de desenvolvimento sustentada pelas fontes sintéticas"
    $corpoConsulta = @{ pergunta = $perguntaDesenvolvimento } | ConvertTo-Json -Compress
    $respostaConsulta = Invoke-WebRequest -Uri ($urlChat + "/api/perguntar") `
        -Method Post -ContentType "application/json" -Body $corpoConsulta `
        -Headers @{ Authorization = "Bearer $env:VARELEIRA_L400_TOKEN_COORDENACAO" } `
        -SkipHttpErrorCheck -TimeoutSec 120
    if ($respostaConsulta.StatusCode -ne 200) { throw "Consulta autenticada falhou; preserve o resultado privado." }
}
finally {
    Remove-Item Env:\VARELEIRA_L400_TOKEN_COORDENACAO -ErrorAction SilentlyContinue
}
```

Essa chamada usa a aplicação e **consome tokens**, embora não altere sua configuração.
HTTP 200 sozinho não comprova o conteúdo: examine o contrato de resposta e as referências
somente em local privado, confira fonte autorizada e resultado documentado para a pergunta.
Confirme as recusas anônimas e de papel desconhecido sem forjar principal; saúde/prontidão são
provas diferentes. A execução não equivale a login humano, avaliação semântica integral ou
homologação. Sem caminho/token/prova, registre “configuração conferida; consulta pendente”,
conserve os índices e não anuncie migração concluída.

### 6. Retornar é a mesma troca ao contrário

1. Recolha observações novas dos dois índices; a referência permanece disponível e intacta.
2. Prepare **outro descritor**, com `acao=retornar`, atual candidato/768 e alvo referência/1536.
   Confira-o pelo passo 2 e mantenha relatório novo.
3. No bloco de [preparação da promoção](#3-preparar-a-promoção-sem-mudar-o-ingresso), conserve
   as leituras e a preservação do ingresso. Substitua as escolhas de ação, perfil e plano pelas
   do retorno:

```powershell
$acaoMigracao = "retornar"
if ($migracao.acao -ne $acaoMigracao) { throw "Descritor não corresponde ao retorno." }
$env:VARELEIRA_L400_FASE = "aplicacao"
$env:VARELEIRA_L400_PERFIL_INDICE = "referencia"
.\.venv\Scripts\python.exe scripts\operar_l400.py --etapa planejar --passo retornar-indice
if ($LASTEXITCODE -ne 0) { throw "Plano local do retorno falhou." }
```

4. Capture novamente o ingresso e a configuração **atuais**, preserve o mesmo ingresso e
   repita os passos 4 e 5: what-if novo, sanitização, revisão, autorização,
   aplicação **[altera o Azure]**, espera finita, leituras e consulta autenticada separada.
   O segredo vigente precisa entrar novamente pela sessão.
5. Confira `VARELEIRA_INDICE=vareleira-lar-l300` e `VARELEIRA_DIMENSOES=1536`. Preserve o
   candidato até retirar seus consumidores; retornar não o apaga.

**Resultado esperado:** nova revisão pronta, par índice/dimensão coerente, ingresso e
autenticação inalterados e consulta autenticada registrada em cada direção. A referência
permanece disponível durante toda a prática; uma falha exige decisão de retorno autorizada,
não uma troca silenciosa.

### Condições que impedem a promoção

- Base, destino, orçamento, cota ou autorização ausentes; manutenção fora da rede autorizada.
- Definições não comparadas, ingestão com falha/aviso não explicado, fonte/hash/classe divergente,
  documento sem trechos ou contagem da referência alterada.
- Modelo/versão/deployment de embeddings não demonstrados durante a ingestão ou dimensões
  diferentes entre índice, habilidade, configuração e cliente de consultas.
- Descritor inválido, reprovado, simulado ou diferente da configuração atual.
- What-if bloqueado, escopo/tipo inesperado, alteração fora da aplicação L400 ou `Modify`
  não revisado; imagem, autenticação, ingresso ou identidade que seriam alterados sem decisão.
- Revisão não pronta ou prova autenticada falha/pendente; retorno indisponível ou consumidor
  não inventariado.

Alterar variáveis **diretamente na aplicação** é uma alternativa consciente, mas **não recomendada**:
cria divergência em relação ao Bicep e sua próxima reaplicação pode desfazer a troca.
Esta receita não publica comandos dessa alternativa; a promoção e o retorno usam `aplicacao`.

## Como pedir uma mudança ao Copilot no VS Code

Abra a pasta completa e a prévia Markdown. Anexe este guia, `infra\l400.bicep`,
`infra\levels\l400.bicepparam`, `scripts\operar_l400.py`, o gerenciador L300 e
`tests\test_operacao_l400.py`. Use descritor **simulado**, sem valores do ambiente, para estudar
o formato; não anexe saídas brutas, tokens ou observações privadas:

```text
Revise a receita de promoção e retorno nos arquivos anexos.
Mapeie a saída de conferir do gerenciador para os campos exatos do descritor.
Separe o que é observado, o que é declarado e o que ainda exige consulta autenticada.
Confira o perfil do Bicep, o par índice/dimensão, ingresso, login e consumidores.
Explique o retorno e as condições que bloqueiam promoção ou remoção.
Não execute Azure, peça dados privados, altere fontes ou elimine a referência.
```

Revise o **diff**, comparação das alterações, em **Source Control**: a receita preserva fontes,
modelos, duas dimensões coerentes, segredo efêmero e referência. Execute plano e testes locais,
não Azure, ao conferir uma edição. A revisão do Copilot não autoriza a operação.

## Conferência do resultado

| Prova | Resultado necessário |
| --- | --- |
| Definições | Comparação completa dos quatro objetos com destinos, modelo/deployment e dimensão explícitos |
| Ingestão | Conclusão sem falhas, avisos tratados, classes e hashes do manifesto |
| Descritor | Dez condições atendidas, origem operador e registros privados que sustentam os campos |
| Revisão | Estado ARM concluído, revisão atual pronta, índice/dimensão coerentes e ingresso inalterado |
| Consulta | Chamada autenticada separada, vetor compatível e autorização preservada |
| Referência | Definição e fontes anteriores intactas |
| Retorno | Aplicação consulta novamente o índice anterior |

## Solução de problemas

| Sintoma | Ação |
| --- | --- |
| Serviço rejeita a dimensão | Confira índice, habilidade e cliente de embeddings |
| Contagem coincide, mas conteúdo diverge | Confira hashes, metadados e classes |
| Candidato substitui a referência | Interrompa e corrija nomes e condições de gravação |
| Consulta externa recebe 403 | Use o caminho privado autorizado, sem reabrir acesso |
| “Definições não comparadas” | Informe também assinatura, grupo, conta e modelos; leitura parcial não libera promoção |
| Descritor simulado passa | Serve para estudar a forma; confira `origem_do_descritor=operador` antes de uma troca real |
| Perfil muda, cliente ainda gera 1536 | Preserve a falha, confira imagem e dimensão enviada; configuração não adapta vetores antigos |
| What-if altera ingresso, imagem ou L300 | Interrompa e revise a divergência; não aceite todo `Modify` do recurso por conveniência |
| Reaplicação pede segredo novamente | Use a mesma credencial vigente aprovada pela sessão; o serviço não devolve seu valor |
| Espera termina ou HTTP falha | Leia estado/revisão e mantenha índices; aceite do pedido não comprova migração |
| Remoção termina, mas objetos não foram lidos | Rode o plano de remoção somente por leitura; 403 não é ausência |

## Custos, pausa e limpeza

Reindexação consome embeddings novamente. Defina prazo para coexistência e mantenha a referência
até conferir o retorno. A remoção do candidato não elimina a cobrança do serviço de busca.

1. Confirme retorno da aplicação L400 à referência, nova revisão pronta e consulta autenticada.
   Inventarie também outras aplicações, revisões ativas com tráfego, jobs e agendas. Sem
   consumidor identificado e retirado, preserve o candidato. Uma revisão inativa retida que
   depende dele não poderá ser reativada sem reconstrução após a remoção.
2. Pelo mesmo caminho/identidade de manutenção, simule a remoção. Ela **só lê Azure** e confere
   o marcador de propriedade dos objetos; não verifica consumidores automaticamente:

```powershell
.\.venv\Scripts\python.exe scripts\gerenciar_ingestao_l300.py --etapa remover `
    --busca $busca --indice $indiceCandidato --identidade-gerenciada --client-id $clientIdManutencao
if ($LASTEXITCODE -ne 0) { throw "Plano de remoção reprovado; preserve os objetos." }
```

3. **[altera o Azure]**: após autorização, remova somente indexador, conjunto de habilidades
   (*skillset*), fonte e índice candidatos, nessa ordem. Recriá-los depois exige nova ingestão
   e consumo de embeddings:

```powershell
.\.venv\Scripts\python.exe scripts\gerenciar_ingestao_l300.py --etapa remover `
    --busca $busca --indice $indiceCandidato --identidade-gerenciada --client-id $clientIdManutencao --executar
if ($LASTEXITCODE -ne 0) { throw "Remoção não concluída; leia os alvos antes de retomar." }
```

4. Repita o comando **sem `--executar`**, somente por leitura. Exija os quatro objetos
   `[ausente]` e a mensagem de que nenhum existe. O retorno da exclusão sozinho não comprova
   ausência; erro de autorização/listagem não conta como ausência. Confira novamente a
   referência com o comando completo de `conferir`, em um arquivo novo, e compare suas
   definições, fontes, classes e contagens com a linha de base.
5. Conserve relatório sanitizado e provas necessárias na política privada aprovada; retire
   bruto que possa conter segredo, token e variáveis sensíveis da sessão. Conexões compartilhadas,
   identidade, dados e serviços anteriores ficam; encerramento completo exige decisão própria
   no [Desafio 07](07-recuperar-limpar.md).

**Resultado esperado:** quatro objetos candidatos ausentes por leitura, referência intacta e
consumidores na configuração anterior. Isso não elimina a cobrança do serviço de busca,
registro, aplicação, rede ou modelos mantidos.

## Situação da validação

Na rodada histórica, referência e candidato tiveram quatro fontes e 24 trechos, com 1.536 e 768 dimensões,
mesmos hashes e classes. A promoção e o retorno tiveram consulta autenticada documentada
e borda preservada. O cliente L400 recebeu uma correção para enviar `dimensions=768`;
a primeira falha foi preservada no [registro](../../docs/validacao/l400-validacao.md).
A aplicação convencional permaneceu na referência de 1.536; não foi testada no candidato.

Na revisão local anterior à execução, a receita pública foi conferida por leitura dos artefatos e dos
mecanismos históricos, ajuda offline da Azure CLI 2.89.0 e testes locais de operação,
sanitização e repositório. Links e sintaxe PowerShell foram conferidos sem executar os blocos.
Essas verificações locais permanecem separadas dos resultados remotos.

**Rodada de validação de 11 de outubro de 2026:**

| Operação | Resultado observado |
| --- | --- |
| Caminho de manutenção | Gerenciador executado dentro do Job, com identidade de manutenção e argumento único Base64, sem depender de um terminal externo para alcançar o índice |
| Referência antes | Conferência aprovada; 24 trechos: 11 das Condições Gerais, cinco das perguntas frequentes, cinco do Glossário e três do roteiro operacional |
| Candidato de 768 dimensões | Plano com quatro objetos a criar; quatro objetos criados; quatro itens processados, zero falhas, cerca de dois segundos; conferência aprovada com 24 trechos e as mesmas contagens por documento |
| Referência depois | Conferência aprovada e configuração preservada |
| Descritor de migração | Somente observações reais; dez conferências atendidas, zero reprovadas, `origem_do_descritor=operador` e `evidencia_azure=false`, pois o conferidor é local |
| Promoção | Dois `Modify`, aplicação e autenticação; sanitizador inicialmente bloqueou com código 3. Cinco propriedades removidas no aplicativo e uma na autenticação foram revisadas e qualificadas; três expressões ARM não resolvidas e 11 deltas de ordem das três sondas foram conferidos depois. Aplicação em 64 segundos, revisão pronta, índice/dimensão no alvo e demais variáveis idênticas |
| Prova no candidato | Quatro pedidos, concorrência dois: quatro HTTP 200, zero divergentes; três `documentada` e um `sem_evidencia` |
| Retorno | Nova revisão dos deltas: quatro propriedades removidas no aplicativo e uma na autenticação, pois `maxInactiveRevisions` já estava ausente. Aplicação em 64 segundos; referência com 1.536 dimensões restabelecida e candidato preservado |
| Prova após retornar | Quatro HTTP 200: três `documentada` e um `sem_evidencia` |

Imagem, registro, conjunto das sondas, escala, identidade e ingresso foram conferidos
como inalterados nas trocas. A aplicação L300 permaneceu na referência.
O bloqueio inicial e a qualificação diferente no retorno continuam parte da evidência;
não reutilize uma contagem antiga de propriedades removidas.

As provas medem operação e contrato HTTP, **não fidelidade semântica nem homologação**.
Fase `isolar`, provas pós-isolamento, negativas externas, ingresso externo, login humano,
implantação por GitHub Actions/OpenID Connect (OIDC, protocolo de identidade), federação e nova avaliação
semântica não foram executados. O caminho privado foi observado com acesso público dos
serviços ainda habilitado; isso não comprova operação isolada.
Custo efetivo indisponível; a estimativa do coordenador é de poucos dólares, sem comprovar
fatura ou o teto estimado de US$ 30 da rodada inteira.
Os resultados e a limpeza aprovada estão no
[registro da rodada de 11 de outubro de 2026](../../docs/validacao/operacao-publica-azure-validacao-2026-10-11.md).

## Glossário e referências

| Termo | Significado |
| --- | --- |
| Dimensão | Quantidade de posições do vetor |
| Reindexação | Novo processamento das fontes para preencher um índice |
| Projeção | Mapeamento dos campos das fontes para os trechos |
| Alias | Nome indireto associado a um índice |
| Promoção | Troca autorizada da configuração usada pela aplicação |
| Descritor e JSON | Arquivo de campos declarados pelo operador e formato de dados estruturados |
| Pipeline e skillset | Sequência de ingestão e conjunto de habilidades que processa as fontes |
| Hash e metadado | Resumo criptográfico do conteúdo e informação descritiva propagada ao índice |
| Azure CLI e ARM | Interface de linha de comando e serviço de administração dos recursos Azure |
| What-if e sanitização | Simulação no destino e redução de dados privados da saída |
| Revisão e ingresso | Versão executável da aplicação e configuração de entrada dos pedidos |
| HTTP e HTTPS | Protocolo web e sua conexão protegida |
| Token, tenant e audiência | Comprovante de autenticação, diretório de identidades e destinatário do token |
| Retorno e consumidor | Troca de volta à referência e cliente/revisão/job que depende do índice |
| Diff | Comparação das alterações antes de aceitá-las |

1. [Índices vetoriais e dimensões](https://learn.microsoft.com/en-us/azure/search/vector-search-how-to-create-index).
2. [Atualização e reconstrução de índices](https://learn.microsoft.com/en-us/azure/search/search-howto-reindex).
3. [Saída privada do indexador](https://learn.microsoft.com/en-us/azure/search/search-indexer-howto-access-private).
4. [What-if e limites de previsão](https://learn.microsoft.com/en-us/azure/azure-resource-manager/bicep/deploy-what-if).
5. [Azure CLI: implantação, estado e espera](https://learn.microsoft.com/en-us/cli/azure/deployment/group?view=azure-cli-latest).
6. [Azure CLI: leitura da aplicação e revisões](https://learn.microsoft.com/en-us/cli/azure/containerapp/revision?view=azure-cli-latest).
7. [Azure CLI: autenticação da aplicação](https://learn.microsoft.com/en-us/cli/azure/containerapp/auth?view=azure-cli-latest).
8. [Atualizações e revisões de Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/revisions).
9. [Receita pública de implantação](03-operar-deployments.md#receita-pública-implantar-por-fases) e
   [contrato do descritor](../../tests/test_operacao_l400.py).

Os comandos Azure publicados foram conferidos com sua ajuda local `--help`, incluindo
parâmetros, sem consulta ao destino. Essa verificação e o parsing não validam a receita no Azure.

## Autoria

Texto por GPT-6.1 Sol; código por Claude Sonnet 5.5. Embeddings e modelo do Copilot são distintos.

Revisão documental por gpt-6-astra (Astra), em 11 de outubro de 2026, sem nova execução Azure.

Receita de implantação e promoção: GPT-6.1 Sol, com Astra indisponível, em 11 de outubro de 2026;
comandos verificados por ajuda offline; sem nova execução Azure.

Atualização pós-validação Azure de 11 de outubro de 2026: redigida por GPT-6.1 Sol com base nos fatos do coordenador; defeitos de código corrigidos com Sonnet 5.5; revisão do coordenador.
