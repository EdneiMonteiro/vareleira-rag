# L200 — Desafio 01: reconstruir a base a partir da release

[Início do laboratório](../../README.md) · Nível L200: ingestão gerenciada e chat · [Desafio 02](02-ingestao-gerenciada.md)

| Item | Descrição |
| --- | --- |
| Situação | Exercício executável. A reconstrução foi conferida no Azure em 10 de outubro de 2026, em Windows com PowerShell. Veja [Situação da validação](#situação-da-validação). |
| Público | Pessoas de Atendimento, operações, arquitetura e desenvolvimento que concluíram o L100. |
| Resultado | Três documentos sintéticos conferidos no armazenamento e o índice Python do L100 disponível como referência para a migração. |
| Custo | Armazenamento, serviço de busca Basic cobrado enquanto existir e tokens, unidades de texto cobradas pelos modelos. Embeddings são vetores numéricos do texto; o deployment, instância nomeada do modelo, de geração fica disponível para os próximos desafios. |

## Conteúdo

- [Cenário](#cenário)
- [Objetivos](#objetivos)
- [Artefatos e disponibilidade](#artefatos-e-disponibilidade)
- [Tecnologias e conceitos](#tecnologias-e-conceitos)
- [Pré-requisitos](#pré-requisitos)
- [Etapa 1: identificar a versão e preparar o terminal](#etapa-1-identificar-a-versão-e-preparar-o-terminal)
- [Etapa 2: conferir o destino e o plano](#etapa-2-conferir-o-destino-e-o-plano)
- [Etapa 3: reconstruir documentos e índice de referência](#etapa-3-reconstruir-documentos-e-índice-de-referência)
- [Como pedir uma mudança ao Copilot no VS Code](#como-pedir-uma-mudança-ao-copilot-no-vs-code)
- [Conferência do resultado](#conferência-do-resultado)
- [Solução de problemas](#solução-de-problemas)
- [Custos, pausa e limpeza](#custos-pausa-e-limpeza)
- [Situação da validação](#situação-da-validação)
- [Glossário](#glossário)
- [Referências](#referências)

## Cenário

No piloto interno fictício de 2025, Beatriz Torres quer que Atendimento e corretores usem o assistente
por uma interface de chat. Antes de mudar a ingestão, a equipe precisa recuperar a base que funcionou
no L100. Os recursos daquela validação foram removidos; os arquivos versionados permitem reconstruí-los.

Teresa Moura continua sendo a autoridade técnica das regras do produto na narrativa. O L200 usa
os mesmos documentos sintéticos aprovados para o exercício. O contexto Vareleira 0.1.0 e os resultados
históricos do assessment de agosto de 2026 permanecem inalterados.

## Objetivos

1. Identificar a release, publicação nomeada de uma versão, e a revisão do código em uso.
2. Escolher um destino Azure exclusivo e conferir permissões, região, modelos e custo.
3. Simular a infraestrutura antes de criar recursos.
4. Reconstruir o armazenamento e o índice `vareleira-lar-l100`, mantendo a referência para o L200.

Este desafio ainda usa os scripts Python do L100. A ingestão gerenciada começa no Desafio 02.
Nenhum documento real de segurado participa do curso.

## Artefatos e disponibilidade

| Artefato disponível | Uso |
| --- | --- |
| [Pré-release L100](https://github.com/EdneiMonteiro/vareleira-rag/releases/tag/v0.1.0-l100) | Referência congelada, commit `d4a93cc`; inclui as limitações conhecidas |
| [Infraestrutura da base](../../infra/main.bicep) e [parâmetros do D03](../../infra/levels/l100-desafio03.bicepparam) | Armazenamento, busca e deployments de embeddings e geração |
| [Inventário](../../dados/l100/inventario.json) | Três fontes sintéticas, tamanhos e hashes |
| [Carga](../../scripts/carregar_documentos.py) e [conferência dos documentos](../../scripts/verificar_documentos.py) | Envio autorizado e comparação com o inventário |
| [Indexação Python](../../scripts/indexar_documentos.py) e [conferência do índice](../../scripts/verificar_indice.py) | Índice de referência do L100 |
| [Dependências L200](../../requirements/l200.txt) | Dependências L100 e bibliotecas do chat |
| [Registro do desafio](../../docs/validacao/l200-01-reconstruir-base.md) | Evidências de execução e limites |

Abra a entrega que contém os guias L200. A pré-release L100, usada como referência, ainda não contém
esses guias nem a implementação do chat.

## Tecnologias e conceitos

**Git** registra versões dos arquivos. Uma **tag** nomeia uma revisão, e um **commit** identifica
uma alteração versionada. Conferir a tag evita comparar índices construídos a partir de bases diferentes.

**Bicep** descreve infraestrutura como código. O Azure Resource Manager (ARM), serviço que administra
recursos Azure, aplica essa descrição ao grupo escolhido. O comando `what-if` calcula mudanças previstas
sem executar a implantação [1].

**Azure Blob Storage** guarda os documentos; **Azure AI Search** guarda os trechos pesquisáveis.
Um **embedding** é um vetor numérico calculado a partir do texto. Documentos e perguntas precisam usar
modelos compatíveis para que a busca vetorial tenha significado.

O L200 reaproveita `text-embedding-3-small`, versão `1`, com 1.536 dimensões, e `gpt-5.4-mini`,
versão `2026-03-17`, configurados na base. O modelo do aluno no GitHub Copilot é uma escolha separada.
Confira catálogo, cota e ciclo de vida na sua região antes da implantação, pelo
[procedimento do L100](../L100/03-responder-com-fontes.md#conferir-região-modelo-e-cota-somente-leitura).

## Pré-requisitos

| Necessidade | Condição para prosseguir |
| --- | --- |
| Visual Studio Code (VS Code), Git, Python 3.12 ou superior e Azure CLI, interface de linha de comando do Azure | Ferramentas disponíveis no terminal PowerShell |
| L100 concluído | Entender inventário, carga, busca, política e autorização |
| Assinatura Azure ativa e destino explícito | Grupo exclusivo, região e custo aprovados pelo responsável |
| Implantação e atribuição de papéis | Permissão para criar recursos e escrever atribuições nos escopos previstos; *Contributor* sozinho não atribui papéis |
| Dados e modelos | Papéis do L100 para operar armazenamento, índice e modelos; cota suficiente |
| Uso assistido | Acesso ao GitHub Copilot; revisão dos comandos continua sendo responsabilidade de quem executa |

Use PowerShell 7 para os comandos do L200. Abra a **pasta completa** no VS Code, este guia na prévia
Markdown e **Terminal > New Terminal**. No comando **Python: Select Interpreter**, selecione o
Python da pasta `.venv`. A extensão Python e o interpretador são instalações distintas.

## Etapa 1: identificar a versão e preparar o terminal

1. Confira alterações locais antes de qualquer troca de versão.
2. Obtenha a tag de referência e confira o commit. Esses comandos não alteram arquivos de trabalho.
3. Em uma instalação nova, crie o ambiente virtual e instale as dependências.

```powershell
git --no-pager status --short
git fetch origin tag v0.1.0-l100
git rev-parse "v0.1.0-l100^{commit}"
git --no-pager log -1 --oneline
```

**Resultado esperado:** a tag aponta para `d4a93cca4c43e1587ae1b9203a06bd450412e231`.
Registre também a revisão L200 em uso. Preserve alterações preexistentes; não use comandos de descarte
para deixar o diretório vazio.

Para uma cópia nova do projeto:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements\l200.txt
python -m unittest discover -s tests
python -m pip check
```

Se o ambiente já existe, ative-o e confira suas dependências antes de reinstalar.
Os testes não acessam o Azure.

### Prompt para o Copilot: conferir a continuidade

Anexe este guia, o inventário, `main.bicep` e `l100-desafio03.bicepparam`:

```text
Explique como reconstruir a base do L100 para comparar a ingestão no L200.
Identifique recursos, papéis, modelos e arquivos que serão reutilizados.
Separe verificações locais, leituras Azure, consumo de tokens e alterações Azure.
Não edite arquivos, instale dependências nem execute comandos.
Não peça IDs, credenciais ou dados reais no chat.
```

**Conferência:** a resposta deve conservar os três documentos e o índice L100; a reconstrução não
depende da identidade ou do cofre temporários do D07, removidos anteriormente.

## Etapa 2: conferir o destino e o plano

Defina as variáveis no terminal, com os valores autorizados para **o seu ambiente**:

```powershell
$assinatura = "<ID-DA-ASSINATURA-AUTORIZADA>"
$grupo = "<GRUPO-EXCLUSIVO-DO-LABORATORIO>"
$regiao = "<REGIAO-CONFIRMADA>"
$tenant = az account show --subscription $assinatura --query tenantId --output tsv
az account show --subscription $assinatura --query state --output tsv
$tenantAtivo = az account show --query tenantId --output tsv
if ($tenantAtivo -ne $tenant) { throw "Confirme a sessão do Entra ID antes de continuar." }
$env:VARELEIRA_ID_OBJETO_CARGA = az ad signed-in-user show --query id --output tsv
```

**Resultado esperado:** assinatura `Enabled`, tenant correto e identidade do operador conhecida.
O tenant é o diretório de identidades do Microsoft Entra ID. Essa consulta não comprova autorização
para implantar nem para acessar dados. Execute cada comando separadamente, confira `$LASTEXITCODE`
imediatamente e pare se houver falha; o PowerShell não interrompe automaticamente uma sequência
quando um programa externo retorna erro.
As operações `az ad` usam o tenant da sessão ativa; elas não recebem `--subscription`.
Confira os papéis e políticas pelo
[procedimento de acesso do L100](../L100/01-preparar-ambiente.md#24-conferir-permissões-e-políticas).
Mantenha identificadores em variáveis, fora de arquivos e prompts.

Se o grupo ainda não existe, sua criação é uma operação **[altera o Azure]**:

```powershell
az group exists --subscription $assinatura --name $grupo
```

Prossiga somente quando o grupo for novo ou sua reutilização tiver sido aprovada após inventário.
Em um grupo existente, confira também sua região: os parâmetros publicados usam a região do grupo
para os serviços. A variável `$regiao` usada na criação não migra um grupo ou serviço já existente.

```powershell
az group create --subscription $assinatura --name $grupo --location $regiao --tags laboratorio=vareleira-rag dados=sinteticos
az deployment group what-if --subscription $assinatura --resource-group $grupo --name vareleira-rag-l100-d03 --parameters infra\levels\l100-desafio03.bicepparam
```

**Conferência:** o plano inclui armazenamento privado quanto a dados, busca Basic com autenticação
Entra ID e dois deployments; o cofre do L100 D07 permanece fora da implantação. Pare diante de
exclusões ou substituições de recursos preexistentes. Revise mudanças `Unsupported` antes de aplicar:
o plano pode depender de identificadores que só estarão disponíveis após a criação [1].

## Etapa 3: reconstruir documentos e índice de referência

**[altera o Azure]** na implantação, na carga com `--executar` e na indexação com `--executar`.
A simulação da indexação consulta o destino, mas não calcula embeddings.

1. Aplique o plano aprovado, em modo incremental.
2. Recupere os nomes reais das saídas da implantação.
3. Simule a carga, envie os três documentos e confira-os.
4. Simule a indexação, execute-a e confira o índice.

```powershell
az deployment group create --subscription $assinatura --resource-group $grupo --name vareleira-rag-l100-d03 --parameters infra\levels\l100-desafio03.bicepparam
$base = az deployment group show --subscription $assinatura --resource-group $grupo --name vareleira-rag-l100-d03 --output json | ConvertFrom-Json
$conta = $base.properties.outputs.nomeConta.value
$busca = $base.properties.outputs.nomeBusca.value
$modelos = $base.properties.outputs.nomeModelos.value
if (-not $conta -or -not $busca -or -not $modelos) { throw "As saídas da base estão incompletas." }
python scripts\carregar_documentos.py --conta $conta --tenant-id $tenant
python scripts\carregar_documentos.py --conta $conta --tenant-id $tenant --executar
python scripts\verificar_documentos.py --conta $conta --tenant-id $tenant
python scripts\indexar_documentos.py --conta $conta --busca $busca --modelos $modelos --tenant-id $tenant
python scripts\indexar_documentos.py --conta $conta --busca $busca --modelos $modelos --tenant-id $tenant --executar
python scripts\verificar_indice.py --busca $busca --modelos $modelos --tenant-id $tenant
```

**Resultado esperado:** conferência dos três blobs aprovada; `vareleira-lar-l100` com 54 trechos
para os arquivos e parâmetros desta versão, conforme o
[registro da reconstrução](../../docs/validacao/l200-01-reconstruir-base.md).
Cada script deve terminar com código de saída `0`.
No PowerShell, confira `$LASTEXITCODE` após cada comando e pare quando houver falha.

O código compara definições e hashes antes de repetir a carga ou indexação. Investigue divergências
antes de usar uma opção de substituição; a existência de um recurso com nome semelhante não identifica
seu proprietário.

## Como pedir uma mudança ao Copilot no VS Code

Abra **Source Control** para revisar o diff, comparação das alterações. Para adaptar apenas a explicação
de região ou cota, anexe este guia e os parâmetros, delimite os arquivos e peça verificações locais.
Para alterar Bicep, exija `lint`, `build` e um novo `what-if`; gerar uma alteração não autoriza aplicá-la.

## Conferência do resultado

Repita somente os verificadores, que não gravam dados. A conferência vetorial do índice
calcula embeddings de perguntas conhecidas, cobrados por uso:

```powershell
python scripts\verificar_documentos.py --conta $conta --tenant-id $tenant
python scripts\verificar_indice.py --busca $busca --modelos $modelos --tenant-id $tenant
```

Guarde revisão, região, configuração dos deployments e resultado de cada comando em um registro privado.
Publique somente evidências sanitizadas, sem identificadores do ambiente.

## Solução de problemas

| Sintoma | Diagnóstico e recuperação |
| --- | --- |
| `403` | Confira identidade, papel e escopo da operação; aguarde propagação quando um papel acabou de ser atribuído. Solicite ao administrador apenas o acesso necessário [2]. |
| Falta de cota ou modelo indisponível | Confira catálogo e cota na região; uma troca de modelo exige nova indexação ou avaliação, conforme o componente. |
| Hash divergente | Compare o arquivo com a versão aprovada. Preserve a cópia divergente para investigar; não atualize o inventário apenas para passar no teste. |
| Saída de implantação vazia | Consulte `az deployment group show` e confirme o sucesso antes de recuperar nomes. |
| Índice existente diferente | Reveja o plano e a origem do índice; preserve a referência L100 até concluir a comparação. |

## Custos, pausa e limpeza

A busca Basic continua cobrada enquanto existir. Encerrar o terminal não remove recursos.
Embeddings são cobrados quando calculados; os próximos desafios usam o deployment de geração.
Confira preços na região e moeda escolhidas, sem presumir franquia gratuita [3][4].

Mantenha a base para o [Desafio 02](02-ingestao-gerenciada.md). Para encerrar o nível, siga a limpeza
com alvos explícitos do [Desafio 07](07-operar-recuperar-limpar.md). Excluir o grupo só é apropriado
quando **todos** os seus recursos pertencem ao laboratório.

## Situação da validação

A reconstrução foi executada no Azure em 10 de outubro de 2026: infraestrutura, três documentos,
hashes e índice Python com 54 trechos conferidos. O ambiente foi Windows, PowerShell 7 e Python 3.12.
O [registro](../../docs/validacao/l200-01-reconstruir-base.md) distingue essa execução dos resultados
históricos do L100 e registra a limpeza posterior.

## Glossário

| Termo | Significado |
| --- | --- |
| Release e pré-release | Publicação nomeada de uma versão; pré-release identifica uma entrega com limites ainda em avaliação |
| Tag e commit | Nome de uma revisão e identificador de uma alteração versionada |
| Grupo de recursos | Contêiner administrativo de recursos Azure |
| ARM e Bicep | Serviço de administração do Azure e linguagem usada para descrever a infraestrutura |
| `what-if` | Previsão das mudanças de uma implantação |
| Embedding | Vetor numérico calculado a partir de texto |
| Deployment | Instância nomeada de um modelo |
| Hash | Resumo calculado do conteúdo para conferir correspondência entre arquivos |

## Referências

1. [Prever mudanças de implantação com what-if](https://learn.microsoft.com/en-us/azure/azure-resource-manager/bicep/deploy-what-if).
2. [Papéis de dados no Azure AI Search](https://learn.microsoft.com/en-us/azure/search/search-security-rbac).
3. [Preços do Azure AI Search](https://azure.microsoft.com/pricing/details/search/).
4. [Preços do Azure OpenAI](https://azure.microsoft.com/pricing/details/cognitive-services/openai-service/).

Texto e revisão: GPT-6.1 Sol. Implementação reutilizada e testes: Claude Sonnet 5.5.
O Astra, preferido para documentação, não estava disponível. A autoria, o modelo escolhido pelo aluno
no Copilot e os deployments Azure são escolhas independentes.

Revisão documental: gpt-6-astra (Astra), em 11 de outubro de 2026, por leitura integral e
conferência local dos artefatos; sem nova execução Azure.
