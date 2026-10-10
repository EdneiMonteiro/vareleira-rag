# L200 — Desafio 02: ler os documentos com um indexador

[Início do laboratório](../../README.md) · [Desafio 01](01-reconstruir-base.md) · [Desafio 03](03-comparar-ingestao.md)

| Item | Descrição |
| --- | --- |
| Situação | Exercício executável, conferido no Azure em 10 de outubro de 2026. |
| Público | Pessoas de negócio, operações, arquitetura e desenvolvimento; escrever código é opcional. |
| Resultado | Fonte de dados, processamento e indexador disponíveis em um índice separado, usando a identidade do serviço de busca. |
| Custo | Embeddings dos trechos ingeridos, busca e armazenamento. A implantação também prepara registro de imagens, identidade, ambiente e logs para o chat; esses recursos têm custos próprios. |

## Conteúdo

- [Cenário](#cenário)
- [Objetivos](#objetivos)
- [Artefatos e disponibilidade](#artefatos-e-disponibilidade)
- [Tecnologias e conceitos](#tecnologias-e-conceitos)
- [Pré-requisitos](#pré-requisitos)
- [Etapa 1: preparar identidade e papéis](#etapa-1-preparar-identidade-e-papéis)
- [Etapa 2: simular e criar o pipeline](#etapa-2-simular-e-criar-o-pipeline)
- [Etapa 3: executar e conferir a ingestão](#etapa-3-executar-e-conferir-a-ingestão)
- [Como pedir uma mudança ao Copilot no VS Code](#como-pedir-uma-mudança-ao-copilot-no-vs-code)
- [Conferência do resultado](#conferência-do-resultado)
- [Solução de problemas](#solução-de-problemas)
- [Custos, pausa e limpeza](#custos-pausa-e-limpeza)
- [Situação da validação](#situação-da-validação)
- [Glossário](#glossário)
- [Referências](#referências)

## Cenário

No piloto fictício de 2025, Beatriz Torres quer que a entrada de documentos tenha execução e falhas
observáveis pelo serviço, em vez de depender de um script completo no computador de uma pessoa.
A equipe acrescenta um caminho de ingestão e conserva o índice Python para comparar os resultados.

O **indexador** é o processo do Azure AI Search que lê uma fonte e alimenta o índice [1].
A fonte continua sendo o contêiner dos três documentos sintéticos. O serviço de busca recebe uma
identidade própria para lê-los e calcular embeddings.

## Objetivos

1. Separar a identidade do operador, a do serviço de busca e a do futuro chat.
2. Criar os quatro objetos do pipeline, sequência de processamento: índice, fonte, skillset e indexador.
3. Ver o plano antes de gravar; criar o indexador desabilitado e executá-lo em uma etapa separada.
4. Conferir documentos, metadados e falhas, preservando `vareleira-lar-l100`.

## Artefatos e disponibilidade

| Artefato disponível | Uso |
| --- | --- |
| [Infraestrutura L200](../../infra/l200.bicep) e [parâmetros](../../infra/levels/l200.bicepparam) | Identidades, cinco papéis e base de hospedagem |
| [Módulo de papéis](../../infra/modules/l200-identidades.bicep) | Escopos de leitura, modelos e registro de imagens |
| [Gerenciador](../../scripts/gerenciar_ingestao.py) e [regras da ingestão](../../scripts/lab_ingestao.py) | Plano, criação, execução, conferência e remoção |
| [Inventário](../../dados/l100/inventario.json) | Base sintética reaproveitada |
| [Testes de ingestão](../../tests/test_ingestao.py) e [infraestrutura](../../tests/test_infra_l200.py) | Validação local, sem Azure |
| [Registro do desafio](../../docs/validacao/l200-02-ingestao-gerenciada.md) | Resultados e limites da execução |

## Tecnologias e conceitos

| Componente | Função e limite |
| --- | --- |
| Fonte de dados (*data source*) | Aponta para o contêiner e prefixo de blobs. Usa o identificador do recurso com identidade gerenciada, sem chave de armazenamento [1][2]. |
| Skillset | Conjunto de habilidades: dividir texto e gerar embeddings. O Desafio 03 explica seus parâmetros. |
| Projeção de índice | Grava um documento pesquisável para cada trecho e mantém a relação com o blob de origem [3]. |
| Indexador | Executa leitura e processamento; seu histórico informa itens, falhas, erros e avisos. |
| Identidade gerenciada | Identidade cuja credencial é administrada pelo Azure. A identidade do sistema acompanha o serviço de busca; a atribuída pelo usuário é um recurso separado para o chat [2]. |

O inventário controla a **carga Python**. O indexador gerenciado lê os blobs que estiverem no prefixo
configurado; ele não consulta o inventário como lista de permissão. Mantenha somente os documentos
aprovados nesse prefixo e confira o armazenamento antes da ingestão. Perguntas e gabaritos de avaliação
ficam fora do contêiner.

**Metadados** são informações que identificam a fonte, como documento, produto e versão.
O pipeline os lê do blob e os mapeia para os campos do índice.

## Pré-requisitos

Conclua o Desafio 01 e mantenha `$assinatura`, `$grupo`, `$regiao`, `$tenant`, `$conta`, `$busca` e
`$modelos` no terminal PowerShell 7. Em um terminal novo, recupere essas variáveis pelo procedimento
do desafio anterior.

Você precisa de permissão para implantar recursos e atribuir os papéis previstos, além de
`Search Service Contributor` para administrar os objetos da busca e dos papéis de consulta do L100.
A conta deve ter exclusão reversível de blobs ativa e versionamento desativado para a política
de exclusão nativa usada neste pipeline [4].

> **Atenção:** o Bicep L200 prepara quatro recursos de hospedagem antes da existência do chat:
> registro de imagens, ambiente Container Apps, identidade atribuída pelo usuário e workspace
> de logs. Revise esse acréscimo e seu custo antes de implantar; a busca continua sendo a do L100.

## Etapa 1: preparar identidade e papéis

1. Confira a configuração atual da busca, especialmente região, camada, réplicas, partições e etiquetas.
2. Preencha os nomes em variáveis de ambiente do terminal.
3. Execute `what-if` e confira cada mudança.

```powershell
az search service show --subscription $assinatura --resource-group $grupo --name $busca --output json
$env:VARELEIRA_NOME_CONTA = $conta
$env:VARELEIRA_NOME_BUSCA = $busca
$env:VARELEIRA_NOME_MODELOS = $modelos
$env:VARELEIRA_LOCALIZACAO_BUSCA = az search service show --subscription $assinatura --resource-group $grupo --name $busca --query location --output tsv
$env:VARELEIRA_IMPLANTAR_APLICACAO = "false"
$env:VARELEIRA_INGRESSO_EXTERNO = "false"
az deployment group what-if --subscription $assinatura --resource-group $grupo --name vareleira-rag-l200-base --parameters infra\levels\l200.bicepparam
```

**Conferência:** armazenamento e modelos são referências existentes. A busca recebe identidade
`SystemAssigned`; o template reaplica sua configuração. Se a busca tiver sido escalada ou recebido
etiquetas próprias, adapte os parâmetros antes de implantar, preservando esses valores.

| Identidade | Papel e escopo |
| --- | --- |
| Serviço de busca | `Storage Blob Data Reader` no contêiner e `Cognitive Services OpenAI User` no recurso de modelos |
| Futuro chat | `AcrPull` no registro, `Search Index Data Reader` na busca e `Cognitive Services OpenAI User` nos modelos |

Os identificadores das identidades novas podem deixar atribuições como `Unsupported` no `what-if`
do Azure Resource Manager (ARM), serviço de administração dos recursos.
Confira expressões, papéis e escopos; depois da implantação, confira as cinco atribuições reais.

**[altera o Azure]** após aprovação do plano:

```powershell
az deployment group create --subscription $assinatura --resource-group $grupo --name vareleira-rag-l200-base --parameters infra\levels\l200.bicepparam
$l200 = az deployment group show --subscription $assinatura --resource-group $grupo --name vareleira-rag-l200-base --output json | ConvertFrom-Json
$principalBusca = az search service show --subscription $assinatura --resource-group $grupo --name $busca --query identity.principalId --output tsv
az role assignment list --subscription $assinatura --assignee $principalBusca --all --output table
```

**Resultado esperado:** identidade da busca habilitada, dois papéis para ingestão e três para a
identidade do chat. O Desafio 05 usa as saídas da base para construir a imagem e configurar a aplicação.

## Etapa 2: simular e criar o pipeline

1. Confira novamente os documentos do contêiner.
2. Simule a criação. O gerenciador só lê por padrão.
3. Revise nomes, prefixo, modelo, dimensões e diferenças.

```powershell
python scripts\verificar_documentos.py --conta $conta --tenant-id $tenant
python scripts\gerenciar_ingestao.py --etapa criar --busca $busca --assinatura $assinatura --grupo $grupo --conta $conta --modelos $modelos --tenant-id $tenant
```

**Resultado esperado:** quatro objetos a criar, com nomes derivados de `vareleira-lar-l200`.
O prefixo padrão é `vareleira-lar`; os objetos apontam para `base-documental`.

**[altera o Azure]** para criar os objetos, ainda sem processar documentos:

```powershell
python scripts\gerenciar_ingestao.py --etapa criar --busca $busca --assinatura $assinatura --grupo $grupo --conta $conta --modelos $modelos --tenant-id $tenant --executar
```

O indexador nasce **desabilitado**. A política `NativeBlobSoftDeleteDeletionDetectionPolicy` é
configurada na fonte desde a primeira execução. Com projeções, ela permite remover os trechos
de um blob cuja exclusão foi detectada [3][4].

Objetos iguais são preservados. Uma divergência para o comando; `--substituir` exige decisão explícita.
O gerenciador não atribui papéis nem altera o armazenamento.

### Prompt para o Copilot: explicar o plano

No VS Code, anexe este guia, `l200.bicep`, `l200.bicepparam` e `lab_ingestao.py`:

```text
Explique a ingestão gerenciada do L200 para alguém que não programa.
Identifique quem lê os blobs, quem chama embeddings e onde cada trecho é gravado.
Compare os cinco papéis com as tarefas de cada identidade.
Explique por que criar o indexador desabilitado separa criação de execução.
Não execute comandos, atribua permissões ou altere arquivos.
```

**Conferência:** o chat não recebe papel de leitura do Blob Storage nem de administração do índice.
O Copilot deve distinguir a identidade que ingere da que consulta.

## Etapa 3: executar e conferir a ingestão

A simulação abaixo informa o efeito previsto:

```powershell
python scripts\gerenciar_ingestao.py --etapa executar --busca $busca --tenant-id $tenant
```

**[altera o Azure]** ao habilitar e executar o indexador; o processamento consome embeddings:

```powershell
python scripts\gerenciar_ingestao.py --etapa executar --busca $busca --tenant-id $tenant --executar --aguardar 300
python scripts\gerenciar_ingestao.py --etapa conferir --busca $busca --assinatura $assinatura --grupo $grupo --conta $conta --modelos $modelos --tenant-id $tenant
```

Habilitar o indexador inicia a primeira execução; o script acompanha essa rodada sem pedir uma segunda
em paralelo. **Resultado esperado:** três blobs processados, nenhuma falha, erro ou aviso e trechos
dos três documentos no índice. Nesta versão foram conferidos 21 trechos.

Leia a **última execução**, não apenas o estado geral `running`: esse estado também apareceu quando
a última execução já era `success`. Ao atingir o limite de espera, o processamento pode continuar;
consulte `conferir` antes de decidir executar novamente.

## Como pedir uma mudança ao Copilot no VS Code

Para alterar tamanho de trecho ou prefixo, peça primeiro uma explicação do impacto. Em seguida,
delimite `lab_ingestao.py` e seus testes, preserve o índice L100 e exija erro explícito para definições
divergentes. Revise o diff em **Source Control** e execute:

```powershell
python -m unittest discover -s tests -p test_ingestao.py
az bicep lint --file infra\l200.bicep
az bicep build --file infra\l200.bicep --stdout
```

Os comandos locais não autorizam substituir objetos no Azure.

## Conferência do resultado

Repita `--etapa criar` **sem** `--executar`: os quatro objetos devem aparecer iguais.
Repita `--etapa conferir` com os quatro parâmetros de origem para comparar suas definições.
O índice L100 deve continuar com seus 54 trechos.

## Solução de problemas

| Sintoma | Ação |
| --- | --- |
| `403` no Blob ou modelos | Confira identidade da busca e os dois papéis, nos escopos da tabela. Preserve a autenticação Entra ID. |
| Primeiro processamento com zero blobs | Confira contêiner, prefixo e carga. O script marca esse resultado como divergência. |
| `documento_id` vazio | Confira os metadados enviados pela carga do L100 e o mapeamento da projeção. |
| `secao` e `clausulas` vazios | Comportamento desta implementação: Text Split divide texto, sem identificar essas estruturas. |
| `409` por execução em andamento | O script acompanha a rodada existente; evite reinicializações ou execuções redundantes. |
| Mil ou mais trechos ou continuação de página | O gerenciador para com erro explícito; sua conferência é limitada ao laboratório, não uma solução de paginação para produção. |

## Custos, pausa e limpeza

O registro de imagens começa a cobrar antes do chat. Logs cobram por ingestão e retenção; busca
e armazenamento permanecem ativos. Confira as cobranças próprias de cada serviço [5][6].
O indexador deste exercício executa sob demanda, sem agenda periódica.

Mantenha os objetos para o [Desafio 03](03-comparar-ingestao.md). A etapa `remover`, primeiro simulada
e depois autorizada com `--executar`, remove somente indexador, skillset, fonte e índice L200.
Ela conserva os recursos Azure e o índice L100. A limpeza completa está no Desafio 07.

## Situação da validação

A execução Azure confirmou cinco papéis, criação separada da execução, três blobs e 21 trechos,
sem erros ou avisos. A repetição conservou definições e contagens; o contador de itens após um teste
de exclusão foi `1`, não uma prova de consumo zero. Veja o
[registro](../../docs/validacao/l200-02-ingestao-gerenciada.md).

## Glossário

| Termo | Significado |
| --- | --- |
| Pipeline | Sequência de leitura e processamento |
| Indexador | Processo que lê a fonte e alimenta o índice |
| Fonte de dados | Definição do local de leitura e autenticação |
| Skillset | Conjunto de habilidades de processamento |
| Projeção | Mapeamento que grava cada trecho como um documento pesquisável |
| Identidade gerenciada | Identidade com credencial administrada pelo Azure |
| Prefixo | Parte inicial do nome dos blobs selecionados para leitura |
| Exclusão reversível | Retenção temporária de um objeto excluído |

## Referências

1. [Indexador de Azure Blob Storage](https://learn.microsoft.com/en-us/azure/search/search-how-to-index-azure-blob-storage).
2. [Identidades gerenciadas no Azure AI Search](https://learn.microsoft.com/en-us/azure/search/search-how-to-managed-identities).
3. [Projeções e ciclo de vida dos documentos](https://learn.microsoft.com/en-us/azure/search/search-how-to-define-index-projections).
4. [Detecção de alterações e exclusões no armazenamento](https://learn.microsoft.com/en-us/azure/search/search-how-to-index-azure-blob-changed-deleted).
5. [Cobrança do Azure Container Registry](https://azure.microsoft.com/pricing/details/container-registry/).
6. [Cobrança do Azure Monitor](https://azure.microsoft.com/pricing/details/monitor/).

Texto e revisão: GPT-6.1 Sol. Código e testes: Claude Sonnet 5.5.
O Astra não estava disponível; os modelos do aluno e da aplicação são escolhas separadas.
