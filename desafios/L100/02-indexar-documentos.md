# L100 — Desafio 02: dividir, vetorizar e indexar os documentos

[Início do laboratório](../../README.md) · Nível L100: fundamentos · [Desafio 01](01-preparar-ambiente.md)

| Item | Descrição |
| --- | --- |
| Situação | Exercício executável, validado no Azure e aprovado pelo mantenedor em 9 de outubro de 2026 (Windows e PowerShell). Os documentos de seguro são sintéticos. Veja os limites em [Situação da validação](#situação-da-validação). |
| Público | Pessoas de negócio, arquitetura, operações e desenvolvimento. Use o Visual Studio Code (VS Code) para executar os comandos e conferir os resultados; escrever código é opcional. |
| Pré-requisito | [Desafio 01](01-preparar-ambiente.md) concluído: este desafio parte dos documentos que ele guardou no Azure. |
| Resultado | Um índice no Azure AI Search com 54 trechos dos três documentos, cada um com vetor (*embedding*), fonte e impressão digital, e consulta por vetor, por palavras e pelos dois. |
| Custo | O serviço de busca da camada `basic` cobra por hora enquanto existir, e os embeddings cobram por token. Veja [Custos, pausa e limpeza](#custos-pausa-e-limpeza). |

## Conteúdo

- [Cenário](#cenário)
- [Objetivos](#objetivos)
- [Artefatos e disponibilidade](#artefatos-e-disponibilidade)
- [Tecnologias e conceitos](#tecnologias-e-conceitos)
- [Reaproveitamento e acréscimos](#reaproveitamento-e-acréscimos)
- [Pré-requisitos](#pré-requisitos)
- [Etapa 1: ver como os documentos viram trechos](#etapa-1-ver-como-os-documentos-viram-trechos)
- [Etapa 2: criar a busca e o deployment de embeddings com Bicep](#etapa-2-criar-a-busca-e-o-deployment-de-embeddings-com-bicep)
- [Etapa 3: instalar as bibliotecas Python](#etapa-3-instalar-as-bibliotecas-python)
- [Etapa 4: indexar e conferir](#etapa-4-indexar-e-conferir)
- [Etapa 5: consultar o índice](#etapa-5-consultar-o-índice)
- [Como pedir uma mudança ao Copilot no VS Code](#como-pedir-uma-mudança-ao-copilot-no-vs-code)
- [Conferência do resultado](#conferência-do-resultado)
- [Solução de problemas](#solução-de-problemas)
- [Custos, pausa e limpeza](#custos-pausa-e-limpeza)
- [Situação da validação](#situação-da-validação)
- [Glossário](#glossário)
- [Referências](#referências)

## Cenário

Em 2025, na história fictícia da Vareleira, os documentos do Vareleira Lar já estão guardados e
conferidos. Beatriz Torres, responsável pelo Atendimento, apresenta o próximo problema: as pessoas
procuram nos documentos pelas **mesmas palavras** do texto. Quem digita "meu aparelho queimou" não
encontra a cláusula de "danos elétricos", e quem pergunta pela "franquia" precisa saber em qual dos três
documentos procurar.

Antes de qualquer assistente responder, a sua equipe precisa preparar os documentos para uma busca por
**significado**: dividir cada um em pedaços pequenos, calcular para cada pedaço uma representação numérica
do seu sentido e guardar tudo em um serviço de busca. Teresa Moura continua sendo a autoridade sobre as
regras, e por isso cada pedaço guarda a sua origem (documento, versão, seção, cláusulas e arquivo): um
trecho com fonte identificada pode sustentar uma resposta.

**Missão:** preparar o índice de busca e conferir que ele encontra os trechos certos. A resposta escrita por
modelo e o chat ficam para os próximos desafios.

> **Lembre-se:** o cenário é fictício. Não use apólices, nomes, endereços ou documentos de segurados
> reais, mesmo que tenha acesso a eles no trabalho.

## Objetivos

Ao concluir este desafio, você terá:

- visto, sem usar o Azure, como cada documento é dividido em **trechos** e como o tamanho máximo altera o
  resultado;
- criado, com Bicep, um serviço de busca e um *deployment* (instância nomeada de um modelo) de embeddings,
  ambos com as chaves de API (credenciais compartilhadas de acesso ao serviço) desativadas. API
  (*Application Programming Interface*) é a interface pela qual um programa usa um serviço; o acesso
  neste laboratório usa o Microsoft Entra ID, serviço de identidade do Azure;
- calculado os *embeddings* (representações numéricas dos textos) e indexado os trechos com um script que
  simula antes de agir e só troca ou remove trechos a pedido explícito;
- conferido o índice: definição, trechos, modelo dos vetores, perguntas de exemplo e recusa de pedidos sem
  credencial;
- consultado o índice por vetor, por palavras e pelos dois, e explicado um caso em que a busca falha;
- aprendido a pausar o que cobra e a remover o que criou.

**Próximos desafios:** o [Desafio 03](03-responder-com-fontes.md) pede a um modelo de linguagem que escreva a
resposta com base nos trechos e cite as fontes; o [Desafio 04](04-recusar-sem-evidencia.md) reconhece quando
não há evidência; o [Desafio 05](05-agente-com-maf.md) implementa o agente com Microsoft Agent Framework
(MAF); o [Desafio 06](06-avaliar-respostas.md) mede a qualidade da recuperação e das respostas; e o
[Desafio 07](07-identidade-da-aplicacao.md) usa service principal (identidade de uma aplicação no Microsoft
Entra ID) e Azure Key Vault (serviço de guarda de segredos). Comparar estratégias de divisão, usar ranking
semântico e filtrar por versão ou vigência ficam para depois, ainda sem desafio escrito.

> **Para guardar na memória: D-V-I.** Para preparar documentos para busca, **D**ivida em trechos,
> **V**etorize cada trecho e **I**ndexe tudo com a fonte. Mnemônico criado para este curso.

## Artefatos e disponibilidade

| Artefato | Onde encontrar | Situação |
| --- | --- | --- |
| Desafio anterior (base documental no Blob Storage) | [01-preparar-ambiente.md](01-preparar-ambiente.md) | Disponível; pré-requisito |
| Infraestrutura (Bicep), com o parâmetro `implantarIndexacao` | [infra\main.bicep](../../infra/main.bicep) | Disponível; validada |
| Módulo da busca e dos modelos | [infra\modules\indexacao.bicep](../../infra/modules/indexacao.bicep) | Disponível; validado |
| Parâmetros do Desafio 02 | [infra\levels\l100-desafio02.bicepparam](../../infra/levels/l100-desafio02.bicepparam) | Disponível; validado |
| Ver a divisão em trechos (sem Azure) | [scripts\visualizar_trechos.py](../../scripts/visualizar_trechos.py) | Disponível; validado |
| Indexação | [scripts\indexar_documentos.py](../../scripts/indexar_documentos.py) | Disponível; validada |
| Conferência do índice | [scripts\verificar_indice.py](../../scripts/verificar_indice.py) | Disponível; validada |
| Consulta ao índice | [scripts\buscar_trechos.py](../../scripts/buscar_trechos.py) | Disponível; validada |
| Regras compartilhadas: trechos, plano, índice e erros | [scripts\lab_indexacao.py](../../scripts/lab_indexacao.py) e [scripts\lab_comum.py](../../scripts/lab_comum.py) | Disponíveis |
| Perguntas de conferência | [dados\l100\conferencia-recuperacao.json](../../dados/l100/conferencia-recuperacao.json) | Disponível |
| Documentos sintéticos e inventário | [dados\l100\inventario.json](../../dados/l100/inventario.json) | Disponível; aprovação do mantenedor confirmada |
| Dependências Python | [requirements\l100.txt](../../requirements/l100.txt) | Disponível |
| Testes automáticos (sem Azure) | pasta `tests` | Disponíveis |

> **Atenção:** os momentos que alteram o Azure têm a marca **[altera o Azure]**: criar a infraestrutura
> (Etapa 2), indexar com `--executar` (Etapa 4) e pausar ou remover recursos. Leituras e consultas não
> alteram nada. A decisão de executar é sua, mesmo quando você pede ao Copilot que
> "implemente" ou "corrija" algo.

## Tecnologias e conceitos

| Tecnologia | Função neste desafio | Limite ou cuidado |
| --- | --- | --- |
| Azure AI Search | Guarda os trechos em um **índice** e encontra os mais parecidos com uma pergunta [1][2] | Devolve trechos; a escrita de respostas cabe a outro componente |
| Índice de busca | Coleção de registros, um por trecho, com texto, metadados e um **vetor** | É uma cópia preparada para busca; o documento original continua no Blob |
| Microsoft Foundry (recurso de modelos) | Hospeda modelos de inteligência artificial (IA); aqui, só o de embeddings [3] | Calcula os embeddings dos textos enviados; os documentos continuam no Blob Storage |
| Deployment de embeddings | Instância nomeada do modelo `text-embedding-3-small`, que transforma texto em números [3][4] | Gera vetores, não texto; o nome do deployment e o nome do modelo são valores distintos |
| Biblioteca `azure-search-documents` | Cria o índice, grava trechos e consulta, em Python | O acesso depende dos papéis atribuídos |
| Biblioteca `openai` | Chama o deployment pela API compatível da OpenAI, com a sua identidade [4] | Autentica com token do Entra ID, sem chave de API |
| Microsoft Entra ID e papéis | Definem quem pode criar o índice, gravar, consultar e usar o modelo [5] | A autenticação identifica você; os papéis concedem o acesso aos dados |

**Conceitos necessários:** embedding, busca vetorial e trechos.

**1. Embedding.** É uma lista de números, 1.536 neste laboratório, que representa o **significado** de um
texto. Textos com sentido parecido recebem listas parecidas, mesmo sem palavras em comum. Quem calcula a
lista é o modelo do deployment. [4]

**2. Busca vetorial.** O índice guarda a lista de cada trecho. Para uma pergunta, o script calcula a lista
dela e pede ao índice os trechos cujas listas "apontam para o mesmo lado". A medida usada aqui é o
**cosseno**, que compara a direção das listas, e não o tamanho. Para evitar a comparação da pergunta com
todos os vetores, o índice organiza as listas em um grafo de vizinhos chamado **HNSW** (*Hierarchical
Navigable Small World*), que percorre os vizinhos mais próximos e devolve um resultado aproximado. [6]

> **Para guardar na memória: o fichário da biblioteca.** Cada trecho é uma ficha. O embedding é a
> coordenada da ficha no mapa dos assuntos; a pergunta também ganha uma coordenada, e o bibliotecário traz
> as fichas mais próximas. Ele sempre traz as mais próximas, mesmo quando nenhuma serve. Analogia criada
> para este curso.

**3. Trechos.** Um modelo de embeddings representa **um texto em uma lista de números**. Quando o texto
mistura assuntos, a representação também os combina, o que pode dificultar a localização da cláusula
pedida. O programa divide cada documento por seção e tamanho máximo, preservando parágrafos quando
cabem; um trecho ainda pode reunir várias cláusulas. A divisão é
uma decisão de projeto com efeito direto na qualidade da recuperação; a comparação de estratégias fica
para mais adiante. [7][8]

### Regras de divisão em trechos

O script aplica as mesmas regras na pré-visualização, na indexação e na conferência:

1. cada título do Markdown abre uma **seção** nova, e um trecho nunca atravessa duas seções;
2. dentro da seção, parágrafos inteiros são agrupados até o **tamanho máximo** (padrão: 1.200 caracteres,
   cerca de 400 tokens), e uma cláusula nunca é cortada ao meio se couber;
3. uma lista ou tabela fica junto do parágrafo que a introduz;
4. cada trecho começa pela linha do título da sua seção;
5. o texto enviado ao modelo leva também o título do documento, o que dá contexto a trechos curtos, como o
   de um termo do glossário;
6. cada trecho guarda o documento, a versão, a seção, os números das cláusulas e o arquivo de origem.

Um **token** é um pedaço de texto, em geral uma palavra ou parte dela, e é a unidade em que os modelos
leem e cobram. [4] Na indexação deste laboratório, 22.594 caracteres consumiram 7.134 tokens (cerca de 3,2
caracteres por token); o script usa 3 caracteres por token em suas estimativas.

### Impressão digital e plano de indexação

Cada trecho tem uma **impressão digital**: um hash (resumo calculado do conteúdo) SHA-256 (*Secure Hash
Algorithm*, 256 bits) de tudo o que define o seu registro, isto é, o texto, os metadados, o nome do
deployment e o tamanho do vetor. O plano compara a impressão calculada agora com a gravada no índice.
Impressão igual significa `igual`; diferente
significa `divergente`; ausente significa `criar`; e um trecho do índice que os documentos não produzem
mais é `órfão`. Por isso, repetir o comando calcula embeddings só dos trechos `criar` e `divergente` e não
sobrescreve nada em silêncio.

### Papéis necessários

Além do crachá, da autorização de obra e da chave do cofre do Desafio 01, este desafio usa três
**papéis** novos, atribuídos separadamente: um para administrar índices e dois para acessar dados
e modelos.

| Papel | Onde | Permite |
| --- | --- | --- |
| `Search Service Contributor` | Serviço de busca | Criar e alterar índices |
| `Search Index Data Contributor` | Serviço de busca | Gravar e consultar documentos do índice |
| `Cognitive Services OpenAI User` | Recurso de modelos | Usar o deployment, sem administrá-lo |

O Bicep atribui cada papel a você no menor escopo possível: o serviço de busca ou o recurso de modelos,
e não o grupo de recursos. [5]

## Reaproveitamento e acréscimos

| Item | Situação | Observação |
| --- | --- | --- |
| Conta de armazenamento, contêiner e documentos | Reaproveitados, sem alteração | A indexação **lê** do Blob; nada é gravado lá |
| `main.bicep` e `l100.bicepparam` | `main.bicep` inclui o parâmetro `implantarIndexacao`, desligado por padrão | O `l100.bicepparam` do Desafio 01 mantém só a conta de armazenamento |
| Serviço de busca, recurso de modelos e deployment | **Novos**, criados por `l100-desafio02.bicepparam` | A busca cobra por hora; os embeddings, por tokens. Veja [Custos, pausa e limpeza](#custos-pausa-e-limpeza) |
| Papéis de dados | Três **novos**, atribuídos pela mesma variável `VARELEIRA_ID_OBJETO_CARGA` | Sem permissão para atribuir papéis, um administrador os concede |
| `requirements\l100.txt` | Inclui `azure-search-documents` e `openai` | Instale as dependências na Etapa 3 |
| Scripts do Desafio 01 | Sem mudança de comportamento | `lab_comum.py` ganhou funções compartilhadas |
| Reverter | Reaplicar o `l100.bicepparam` mantém os recursos novos | A implantação incremental preserva recursos ausentes do arquivo; a remoção é manual e está em [Custos, pausa e limpeza](#custos-pausa-e-limpeza) |

## Pré-requisitos

Os comandos deste guia são escritos para Windows e PowerShell, no terminal integrado do Visual Studio Code
(VS Code), como no Desafio 01.

| Pré-requisito | Como preparar | Necessário agora? |
| --- | --- | --- |
| Desafio 01 concluído | `verificar_documentos.py` aprovado, no mesmo grupo de recursos e na mesma assinatura | Sim |
| Variáveis do terminal | `$assinatura`, `$grupo` e `$conta` definidas (veja abaixo) | Sim |
| Assinatura Azure ativa | Use a assinatura autorizada no Desafio 01 e confirme as permissões para as novas atividades | Sim |
| Permissão para criar recursos | Papel como *Contributor* no grupo de recursos | Sim, na Etapa 2 |
| Permissão para atribuir papéis (opcional) | *Owner*, *User Access Administrator* ou equivalente no escopo; sem ela, um administrador concede os três papéis | Dispensável, se um administrador ajudar |
| Região com busca e modelo disponíveis | O grupo do Desafio 01 já tem uma região; confira o modelo e a cota abaixo | Sim |
| Aceitar o custo | O serviço de busca da camada `basic` cobra por hora **enquanto existir**; veja [Custos, pausa e limpeza](#custos-pausa-e-limpeza) | Sim |
| VS Code, Azure CLI (interface de linha de comando do Azure), Bicep e Python | Os mesmos do Desafio 01 | Sim |

Em um terminal novo, defina as variáveis de novo. Substitua `<ID-DA-SUA-ASSINATURA>` e use o nome do
grupo criado no Desafio 01:

```powershell
$assinatura = "<ID-DA-SUA-ASSINATURA>"
$grupo = "rg-vareleira-rag-l100"
$conta = az deployment group show --subscription $assinatura --resource-group $grupo --name vareleira-rag-l100 --query properties.outputs.nomeConta.value --output tsv
$conta
```

**Resultado esperado:** o nome da conta de armazenamento do Desafio 01.

> **Atenção:** este desafio cria recursos que **cobram**, e a cobrança continua até a remoção deles: fechar
> o VS Code ou o terminal não a encerra. Leia [Custos, pausa e limpeza](#custos-pausa-e-limpeza) antes da
> Etapa 2 e decida agora quando pausar ou remover os recursos.

### Conferir região e cota (somente leitura)

Por padrão, o serviço de busca e o recurso de modelos são criados na **região do grupo**, e o modelo de
embeddings precisa estar disponível nessa região. Os três comandos abaixo só leem: mostram a região do
grupo, se o modelo existe nela e quanta cota do modelo já está em uso. [9]

```powershell
$regiao = az group show --subscription $assinatura --name $grupo --query location --output tsv
(az cognitiveservices model list --subscription $assinatura --location $regiao --output json | ConvertFrom-Json) | Where-Object { $_.model.name -eq "text-embedding-3-small" } | Select-Object -First 1 | ForEach-Object { "$($_.model.name) versao $($_.model.version): $(($_.model.skus | ForEach-Object { $_.name }) -join ', ')" }
(az cognitiveservices usage list --subscription $assinatura --location $regiao --output json | ConvertFrom-Json) | Where-Object { $_.name.value -eq "OpenAI.GlobalStandard.text-embedding-3-small" } | ForEach-Object { "usado $($_.currentValue) de $($_.limit)" }
```

**Resultado esperado** (em `brazilsouth`, sem outros deployments do modelo): `text-embedding-3-small versao 1:
GlobalStandard` e `usado 0 de 1000`. No Windows PowerShell 5.1, os números aparecem com casa decimal
(`1000.0`). A cota é medida em milhares de tokens por minuto e é descontada de cada deployment que você
cria, mesmo sem uso. Se o modelo não aparecer, ou a cota livre for menor que a do Bicep (30), escolha outra
região ou reduza `capacidadeEmbeddings`.

A disponibilidade do serviço de busca é conferida durante a implantação. Se ela falhar com
`InsufficientResourcesAvailable`, preserve o armazenamento do Desafio 01 e crie só a busca em outra
região permitida, com `--parameters localizacaoBusca=<outra-região>` nos comandos da Etapa 2. [10]
O [registro de capacidade regional](../../docs/validacao/l100-02-indexar-documentos.md#observações-de-operação)
descreve a recusa observada em `eastus2`.

## Etapa 1: ver como os documentos viram trechos

**Objetivo:** entender a divisão antes de calcular embeddings, que cobram por token processado. Esta etapa
lê apenas arquivos locais e funciona sem Azure, login, assinatura ou permissões, sem alterar nada.

### 1.1 Listar os trechos

Com o ambiente virtual do Desafio 01 ativo (ou use `.\.venv\Scripts\python.exe` no lugar de `python`):

```powershell
python scripts\visualizar_trechos.py
```

O script confere o inventário (tamanho e hash) e lista cada trecho. Início da saída:

```text
Divisão local, sem Azure: no máximo 1200 caracteres por trecho.
Inventário: 3 documento(s) conferidos por tamanho e hash.

VLAR-CG-1.0 — Vareleira Lar — Condições Gerais: 15 trecho(s)
  ordem  caracteres  seção                                     cláusulas
      1         586  Apresentação do documento
      2        1104  1. Objetivo e como ler este documento     1.1, 1.2, 1.3, 1.4, 1.5
      3         564  2. Coberturas básicas                     2.1, 2.2, 2.3
      4        1108  3. Coberturas adicionais                  3.1, 3.2, 3.3
      5         645  3. Coberturas adicionais                  3.4, 3.5
...
Resumo: 54 trecho(s) em 3 documento(s), em média 378 caracteres. ...
```

**Resultado esperado:** 54 trechos: 15 das Condições Gerais, 24 do glossário (a apresentação e um por
termo) e 15 das perguntas frequentes (a apresentação e um por pergunta). A seção 3 das Condições Gerais
virou dois trechos, porque excede o tamanho máximo.

### 1.2 Ver o texto de um documento e variar o tamanho máximo

O primeiro comando mostra o texto completo do glossário, e o segundo divide todos os documentos em trechos de
até 600 caracteres:

```powershell
python scripts\visualizar_trechos.py --documento VLAR-GL-1.0 --completo
python scripts\visualizar_trechos.py --tamanho-maximo 600
```

| Tamanho máximo (caracteres) | 300 | 600 | 800 | 1200 (padrão) | 2500 |
| --- | --- | --- | --- | --- | --- |
| Trechos no total | 108 | 67 | 60 | 54 | 51 |

**O que observar:** trechos menores localizam melhor a cláusula, mas perdem contexto e geram mais
registros para calcular; trechos maiores guardam mais contexto, mas misturam assuntos. O glossário quase
não muda, porque cada termo já é curto.

**Atividade 1:** encontre, na saída completa das Condições Gerais, o trecho que contém a cláusula 3.2
(danos elétricos) e diga com quais outras cláusulas ele aparece. Depois descubra qual tamanho máximo faz a
3.2 ficar em um trecho só dela.

**Conferência:** com o tamanho padrão, a cláusula 3.2 está no trecho 4, junto com as cláusulas 3.1 e 3.3. Com 700
caracteres ela fica sozinha e inteira: a cláusula, com os itens a), b) e c), e o título da seção somam cerca de
630. Com 600 o script precisa dividi-la: os itens a) e b) ficam em um trecho, e o c) abre o seguinte, que a coluna
`cláusulas` rotula só como 3.3 (um exemplo do que se perde ao dividir por tamanho). Com 800 a 3.2 volta a dividir
o trecho com a 3.1. O tamanho máximo é uma decisão de projeto: cada valor equilibra contexto e precisão.

### Prompt para o Copilot: entender a divisão

Anexe `scripts\lab_indexacao.py` e o README:

```text
Leia scripts/lab_indexacao.py, funções dividir_documento, _ler_secoes, _empacotar e extrair_clausulas.
Explique, para quem não programa e com uma analogia, como um documento Markdown vira trechos.
Diga o que acontece com uma lista, com uma tabela e com um parágrafo maior que o limite.
Liste dois riscos de dividir mal (um para trechos grandes, outro para trechos pequenos).
Não edite arquivos, não execute comandos e não acesse o Azure.
```

**Conferência:** a resposta deve citar seções, agrupamento até o tamanho máximo e o título repetido no início de
cada trecho. Confira cada afirmação no código: o Copilot pode inventar regras que o script não tem.

## Etapa 2: criar a busca e o deployment de embeddings com Bicep

**[altera o Azure]** nos comandos `az deployment group create` e, se necessário, `az role assignment create`.

**Objetivo:** acrescentar ao grupo do Desafio 01 um serviço de busca e um deployment de embeddings, com
chaves de API desativadas, e atribuir a você somente os papéis necessários. O arquivo
[infra\modules\indexacao.bicep](../../infra/modules/indexacao.bicep) descreve os recursos, o
[infra\main.bicep](../../infra/main.bicep) o chama quando `implantarIndexacao` é verdadeiro, e o
[infra\levels\l100-desafio02.bicepparam](../../infra/levels/l100-desafio02.bicepparam) habilita esse parâmetro e
mantém as escolhas do Desafio 01 para que a conta de armazenamento permaneça inalterada. [11]

### Decisões de configuração do Bicep

| Decisão do Bicep | O que faz | Por que importa |
| --- | --- | --- |
| Chaves de API desativadas (`disableLocalAuth: true`) na busca e nos modelos | Só o Entra ID autentica | Conexões sem chave: o acesso passa pelos papéis do Entra ID, atribuídos por identidade [5] |
| Três papéis de dados, cada um no recurso a que se refere | Você cria e consulta o índice e usa o modelo | Aplica o menor privilégio: cada papel vale só no recurso a que se refere |
| Versão do modelo fixa (`NoAutoUpgrade`) | O modelo permanece na versão escolhida | Vetores de versões diferentes são incomparáveis: uma troca automática de versão tornaria o índice incompatível |
| Camada `basic` da busca (padrão) | Serviço dedicado, base dos próximos níveis | Cobra por hora enquanto existir; a camada `free` é uma alternativa limitada a 50 MB de armazenamento [12] |
| Tipo de deployment `GlobalStandard`, capacidade 30 | Cobra por tokens usados; a capacidade 30 reserva 30 mil tokens por minuto de cota | A capacidade define a cota reservada, e a cobrança vem dos tokens usados; o tipo `GlobalStandard` pode processar o texto em qualquer geografia Azure [13] |
| Endereços públicos, mas autenticados | O endereço é acessível pela internet; só quem tem papel usa o serviço | Dispensa a configuração de rede privada neste nível; redes privadas ficam para outro nível |
| `implantarIndexacao` desligado por padrão | O `l100.bicepparam` continua criando só a conta | Preserva o comportamento validado no Desafio 01 |

> **Atenção:** o tipo de deployment `GlobalStandard` pode processar o texto enviado em qualquer geografia
> Azure, e os dados em repouso permanecem na geografia designada para o recurso. [13] Os documentos deste
> laboratório são sintéticos; com dados reais, avalie o tipo de deployment com a sua organização.

### Prompt para o Copilot: entender o Bicep

```text
Leia infra/main.bicep, infra/modules/indexacao.bicep e infra/levels/l100-desafio02.bicepparam anexados.
Explique, para quem não programa, cada recurso novo e cada configuração de segurança.
Diga o que o what-if mostrará quando o Desafio 01 já foi implantado e o que acontece se a
variável VARELEIRA_ID_OBJETO_CARGA estiver vazia.
Aponte qualquer coisa que pareça insegura ou que eu deva conferir antes de implantar.
Não edite arquivos nem execute comandos.
```

**Conferência:** a resposta deve citar a busca, o recurso de modelos, o deployment e os três papéis; dizer que
as chaves de API estão desativadas; e explicar que a conta de armazenamento deve permanecer inalterada. Se a
resposta sugerir ligar chaves, abrir o acesso ou executar algo agora, peça a correção.

### 2.1 Informar quem opera o laboratório

Use o terminal e as variáveis definidas em Pré-requisitos. Defina a mesma variável do Desafio 01, que
identifica quem opera o laboratório e vale só nesta sessão do terminal: [14]

```powershell
$env:VARELEIRA_ID_OBJETO_CARGA = az ad signed-in-user show --query id --output tsv
```

O comando não imprime nada quando conclui com sucesso.

### 2.2 Simular a implantação (what-if)

O **what-if** mostra o que seria criado, sem criar nada: [15]

```powershell
az deployment group what-if --subscription $assinatura --resource-group $grupo --name vareleira-rag-l100-d02 --parameters infra\levels\l100-desafio02.bicepparam
```

**Resultado esperado:** seis recursos marcados com `+ Create`: o recurso de modelos (`accounts`), o
deployment de embeddings, o serviço de busca (`searchServices`) e três `roleAssignments`. A conta de
armazenamento deve aparecer como `= Nochange`. Na previsão registrada, `blobServices` e `containers`
apareceram como `~ Modify` por propriedades preenchidas pelo serviço, com a linha
`Resource changes: 6 to create, 2 to modify, 2 no change.` Confira cada diferença antes de aceitá-la.
Se algo for removido (`- Delete`) ou se a conta
de armazenamento aparecer como `Create`, interrompa: o grupo ou o arquivo de parâmetros não corresponde ao
do Desafio 01.

### 2.3 Implantar

Execute a implantação e remova a variável:

```powershell
az deployment group create --subscription $assinatura --resource-group $grupo --name vareleira-rag-l100-d02 --parameters infra\levels\l100-desafio02.bicepparam
Remove-Item Env:\VARELEIRA_ID_OBJETO_CARGA
```

**Tempo de referência:** de 1 a 2 minutos, medidos em `brazilsouth`. Para usar a camada gratuita da busca,
acrescente `--parameters skuBusca=free` ao comando; para criar a busca em outra região, acrescente
`--parameters localizacaoBusca=<região>`.

### 2.4 Registrar os nomes gerados

Os nomes são gerados a partir do identificador do grupo de recursos e permanecem estáveis para esse
grupo. Guarde-os em variáveis:

```powershell
$busca = az deployment group show --subscription $assinatura --resource-group $grupo --name vareleira-rag-l100-d02 --query properties.outputs.nomeBusca.value --output tsv
$modelos = az deployment group show --subscription $assinatura --resource-group $grupo --name vareleira-rag-l100-d02 --query properties.outputs.nomeModelos.value --output tsv
$deployment = az deployment group show --subscription $assinatura --resource-group $grupo --name vareleira-rag-l100-d02 --query properties.outputs.nomeDeploymentEmbeddings.value --output tsv
$busca
$modelos
$deployment
```

**Resultado esperado:** `srch-vlr-...`, `ais-vlr-...` e `embeddings`. O último é o nome do deployment, que o
script usa por padrão.

### Atribuição dos papéis por um administrador

Sem permissão para criar atribuições de papel, a implantação falha em `roleAssignments`. Se você tinha
definido a variável, remova-a (`Remove-Item Env:\VARELEIRA_ID_OBJETO_CARGA`), implante de novo e peça a um
administrador os três papéis, para o seu usuário. Com o ID de objeto que você obteve no Desafio 01 e com
`$assinatura`, `$grupo`, `$busca` e `$modelos` definidos, o administrador executa **[altera o Azure]**:

```powershell
$idBusca = az search service show --subscription $assinatura --resource-group $grupo --name $busca --query id --output tsv
$idModelos = az cognitiveservices account show --subscription $assinatura --resource-group $grupo --name $modelos --query id --output tsv
az role assignment create --assignee-object-id "<ID-DE-OBJETO-DE-QUEM-VAI-OPERAR>" --assignee-principal-type User --role "Search Service Contributor" --scope $idBusca
az role assignment create --assignee-object-id "<ID-DE-OBJETO-DE-QUEM-VAI-OPERAR>" --assignee-principal-type User --role "Search Index Data Contributor" --scope $idBusca
az role assignment create --assignee-object-id "<ID-DE-OBJETO-DE-QUEM-VAI-OPERAR>" --assignee-principal-type User --role "Cognitive Services OpenAI User" --scope $idModelos
```

Um papel novo pode levar até 10 minutos para valer [16], e nesse intervalo o serviço de modelos pode
alternar entre aceitar e recusar o pedido (resposta 401 do HTTP, *Hypertext Transfer Protocol*, o protocolo
da web). Aguarde e repita.

### 2.5 Conferir a infraestrutura

```powershell
az resource list --subscription $assinatura --resource-group $grupo --query "[].{Nome:name,Tipo:type}" --output table
az search service show --subscription $assinatura --resource-group $grupo --name $busca --query "{Camada:sku.name,Replicas:replicaCount,Particoes:partitionCount,ChavesDeApiDesativadas:disableLocalAuth,AcessoPublico:publicNetworkAccess}" --output json
az cognitiveservices account show --subscription $assinatura --resource-group $grupo --name $modelos --query "{Tipo:kind,Camada:sku.name,ChavesDesativadas:properties.disableLocalAuth,AcessoPublico:properties.publicNetworkAccess}" --output json
az cognitiveservices account deployment show --subscription $assinatura --resource-group $grupo --name $modelos --deployment-name $deployment --query "{Deployment:name,Modelo:properties.model.name,Versao:properties.model.version,Implantacao:sku.name,Capacidade:sku.capacity,Atualizacao:properties.versionUpgradeOption}" --output json
```

**Resultado esperado:**

- três recursos no grupo: a conta de armazenamento, o serviço de busca e o recurso de modelos;
- busca com `Camada` igual a `basic`, uma réplica, uma partição e `ChavesDeApiDesativadas` verdadeiro;
- modelos com `Tipo` igual a `AIServices` e `ChavesDesativadas` verdadeiro;
- deployment com `Modelo` igual a `text-embedding-3-small`, `Versao` 1, `Implantacao` `GlobalStandard`, `Capacidade` 30 e
  `Atualizacao` igual a `NoAutoUpgrade`.

Confira também os papéis atribuídos pelo Bicep ou pelo administrador:

```powershell
$idBusca = az search service show --subscription $assinatura --resource-group $grupo --name $busca --query id --output tsv
$idModelos = az cognitiveservices account show --subscription $assinatura --resource-group $grupo --name $modelos --query id --output tsv
az role assignment list --subscription $assinatura --scope $idBusca --query "[].{Papel:roleDefinitionName,Tipo:principalType}" --output table
az role assignment list --subscription $assinatura --scope $idModelos --query "[].{Papel:roleDefinitionName,Tipo:principalType}" --output table
```

**Resultado esperado:** `Search Service Contributor` e `Search Index Data Contributor` na busca, e
`Cognitive Services OpenAI User` nos modelos, todos para o tipo `User`.

> **Boa prática:** reimplantar o mesmo Bicep é idempotente: o Azure aplica só a diferença em relação ao
> estado atual, e um papel removido volta com a implantação. A previsão pode listar `Modify` para
> propriedades que o serviço preenche sozinho (como `properties.endpoint` ou `properties.semanticSearch`),
> o que pode aparecer como ruído. [15] Confira os detalhes de cada diferença antes de decidir;
> as previsões medidas estão no registro de validação.

## Etapa 3: instalar as bibliotecas Python

**Objetivo:** instalar as bibliotecas de busca e de modelos, com as versões fixadas no projeto. Use o
ambiente virtual do Desafio 01; esta etapa mantém a versão do interpretador Python.

```powershell
python -m pip install -r requirements\l100.txt
python -c "import azure.search.documents, openai; print('bibliotecas ok')"
```

**Resultado esperado:** a instalação termina sem erro, e o segundo comando imprime `bibliotecas ok`. Se o
PowerShell bloquear a ativação do ambiente virtual, substitua `python` por `.\.venv\Scripts\python.exe`, como
no Desafio 01. Os scripts autenticam com a identidade do Azure CLI (`az login`); nenhuma chave é usada. Com
mais de um tenant, acrescente `--tenant-id <ID-DO-TENANT>` aos comandos.

## Etapa 4: indexar e conferir

**[altera o Azure]** no comando com `--executar` e nos experimentos opcionais.

**Objetivo:** gravar no índice um registro por trecho, com o vetor, a fonte e a impressão digital, e
verificar que o índice corresponde aos documentos.

### 4.1 Simular a indexação

A **simulação** é o padrão: o script lê o contêiner e o índice, divide os documentos e mostra o plano, mas
não calcula embeddings nem grava nada. Ela também testa as suas permissões de leitura no Blob e no serviço de busca.

```powershell
python scripts\indexar_documentos.py --conta $conta --busca $busca --modelos $modelos
```

**Resultado esperado:**

```text
Modo: SIMULAÇÃO (nenhuma alteração será feita)
Origem: conta '<conta>', contêiner 'base-documental'
Destino: serviço de busca '<busca>', índice 'vareleira-lar-l100'
Embeddings: deployment 'embeddings' do recurso '<modelos>' (1536 dimensões)
Inventário: 3 documento(s).
Contêiner: 3 documento(s) conferidos por tamanho e hash.
Divisão: 54 trecho(s) de até 1200 caracteres.
Plano:
  [criar     ] índice 'vareleira-lar-l100': definição com busca vetorial (HNSW, cosseno, 1536 dimensões)
  VLAR-CG-1.0     15 trecho(s): 15 a criar, 0 iguais, 0 divergentes
  VLAR-GL-1.0     24 trecho(s): 24 a criar, 0 iguais, 0 divergentes
  VLAR-FAQ-1.0    15 trecho(s): 15 a criar, 0 iguais, 0 divergentes
  Total: 54 trecho(s): 54 a criar, 0 iguais, 0 divergentes; 0 órfão(s).
  Embeddings a gerar: 54 trecho(s), cerca de 7532 tokens (estimativa; o serviço informa o uso real).
Simulação concluída. Para indexar, repita o comando com --executar.
```

Antes de tudo, o script **confere no contêiner**, por tamanho e hash, os documentos que vai ler. Se o
Desafio 01 não foi concluído, o script para com código 3 e indica o Desafio 01. Se aparecer `[ERRO]`,
consulte [Solução de problemas](#solução-de-problemas).

### Prompt para o Copilot: ler o plano

```text
A simulação do indexador mostrou o resultado abaixo, que revisei para remover nomes do ambiente.
Explique, linha por linha e sem jargão, o que cada parte do plano quer dizer.
Diga o que significam criar, igual, divergente e órfão, e por que o script não calcula
embeddings durante a simulação.
Não execute comandos, não altere arquivos e não acesse o Azure.

[Cole aqui apenas o trecho da saída a partir de "Plano:".]
```

**Conferência:** a explicação deve dizer que nada foi gravado, que `criar` é trecho ainda ausente do índice e que
o cálculo de embeddings (que gasta tokens) só ocorre com `--executar`.

### 4.2 Indexar

```powershell
python scripts\indexar_documentos.py --conta $conta --busca $busca --modelos $modelos --executar
```

**Resultado esperado** (as últimas linhas):

```text
[EMBEDDINGS] 54 vetor(es) de 1536 dimensões gerados com o modelo 'text-embedding-3-small' (7134 tokens usados).
[CRIADO] Índice 'vareleira-lar-l100'.
[INDEXADO] 54 criado(s), 0 trocado(s).
Concluído: 54 criado(s), 0 trocado(s), 0 já igual(is), 0 removido(s).
O índice pode levar alguns segundos para refletir as gravações.
Próximo passo: python scripts\verificar_indice.py --busca <busca> --modelos <modelos>
```

O script **calcula todos os embeddings antes de criar ou alterar qualquer coisa**: se o serviço de modelos
falhar, o índice não é criado e nada é gravado. Na validação, os 54 trechos usaram 7.134 tokens, cerca de 5% abaixo
da estimativa de 7.532, e a execução levou de 19 a 24 segundos. O custo dos embeddings é o número de tokens
multiplicado pelo preço por token da sua região. [17]

### 4.3 Conferir o índice

```powershell
python scripts\verificar_indice.py --busca $busca --modelos $modelos
```

**Resultado esperado:**

```text
[OK   ] Definição do índice: 16 campo(s); vetor de 1536 dimensões (HNSW, cosseno)
[OK   ] Trechos do índice: 54 trecho(s) no índice e 54 esperados, todos com a impressão digital esperada
[OK   ] Modelo dos vetores: o índice e o deployment usam o modelo 'text-embedding-3-small'
[OK   ] Busca vetorial (6 perguntas): o trecho esperado apareceu entre os 3 primeiros em 6 de 6 perguntas
    R1: esperado na posição 1; primeiro resultado VLAR-FAQ-1_0-011
    ...
[OK   ] Acesso sem credenciais negado: pedidos sem credencial recusados: busca HTTP 401; modelos HTTP 401
Verificação aprovada.
```

A verificação **só lê** o índice e consome tokens apenas para calcular o embedding das seis perguntas, que
são curtas. Ela confere:

1. a **definição** do índice: campos, tipos, atributos e a configuração vetorial;
2. os **trechos**: a quantidade e o conteúdo coincidem com o que os documentos produzem;
3. o **modelo**: o índice e o deployment usam o mesmo modelo, porque vetores de modelos diferentes são
   incomparáveis;
4. a **recuperação**: para cada pergunta do arquivo
   [dados\l100\conferencia-recuperacao.json](../../dados/l100/conferencia-recuperacao.json), um dos trechos
   esperados aparece entre os três primeiros. É um **teste de fumaça**, uma conferência inicial com poucos
   casos; a avaliação com conjuntos mais amplos fica para o Desafio 06. As perguntas ficam fora da pasta
   dos documentos, para não entrarem no conteúdo
   recuperável;
5. o **acesso**: pedidos sem credencial à busca e aos modelos são recusados (HTTP 401 ou 403). Uma resposta
   de sucesso indica uma falha de configuração a corrigir antes de seguir.

O índice leva alguns segundos para refletir o que foi gravado; por isso a verificação espera até 30
segundos antes de reprovar uma divergência.

### 4.4 Reexecutar a indexação

Execute de novo a simulação e depois `--executar`. O plano mostra `54 iguais`, o script informa que não há
nada a fazer e **não chama o modelo**: sem consumo de tokens e sem gravação. Esse comportamento é a
**reexecução previsível**. Se um documento mudar, só os trechos afetados são calculados de novo.

| Código de saída | Significa |
| --- | --- |
| 0 | Concluído sem problemas |
| 1 | Argumentos, inventário, perguntas ou arquivos locais inválidos |
| 2 | Falha de autenticação, permissão, rede ou serviço do Azure |
| 3 | O contêiner, o índice ou os documentos divergem do esperado |
| 4 | Defeito do script; execute com `--detalhes` e peça ajuda sem dados do seu ambiente |

### Experimento opcional: provocar uma divergência

Este experimento mostra a parada do script diante de uma divergência. Mudar o tamanho máximo altera os
trechos, e o índice passa a conter trechos que o plano não reconhece:

```powershell
python scripts\indexar_documentos.py --conta $conta --busca $busca --modelos $modelos --tamanho-maximo 800
python scripts\indexar_documentos.py --conta $conta --busca $busca --modelos $modelos --tamanho-maximo 800 --executar
```

**Resultado esperado:** o plano mostra `[divergente ]` e `60 trecho(s)`, com `6 a criar, 25 iguais, 29 divergentes`,
e o script para com `[PARADA]` e código 3, **sem alterar nada**, mesmo com `--executar`. Para trocar de propósito
e ver a verificação reprovar:

```powershell
python scripts\indexar_documentos.py --conta $conta --busca $busca --modelos $modelos --tamanho-maximo 800 --executar --substituir-divergentes
python scripts\verificar_indice.py --busca $busca --modelos $modelos
```

**Resultado esperado:** só os 35 trechos novos ou diferentes são calculados, e a verificação, com o
tamanho padrão, reprova: `Trechos do índice: 60 no índice para 54 esperados: 29 com conteúdo diferente ...; 6 sobrando ...`.
Para voltar ao estado anterior, de propósito:

```powershell
python scripts\indexar_documentos.py --conta $conta --busca $busca --modelos $modelos --executar --substituir-divergentes --remover-orfaos
python scripts\verificar_indice.py --busca $busca --modelos $modelos
```

Os trechos excedentes são **órfãos**: o índice os contém, os documentos não os produzem mais, e o script só os
remove com `--remover-orfaos`. Se você trocar o modelo ou as dimensões, o índice fica incompatível: o script
para e oferece outro nome de índice ou `--recriar-indice`, que **apaga** o índice do laboratório e o cria de
novo. Use `--recriar-indice` somente depois de conferir o nome do índice.

## Etapa 5: consultar o índice

**Objetivo:** observar a recuperação e entender onde ela falha. Esta etapa só lê o índice e usa poucos
tokens, para calcular o embedding de cada pergunta. O script devolve trechos; **nenhuma resposta é
escrita aqui.**

### 5.1 Consultar por significado (modo vetorial)

```powershell
python scripts\buscar_trechos.py --busca $busca --modelos $modelos --pergunta "O meu seguro cobre danos elétricos?"
```

**Resultado esperado** (resumido):

```text
1. [pontuação 0.766] Vareleira Lar — Perguntas frequentes para Atendimento e corretores · Danos elétricos estão incluídos em todas as contratações do Vareleira Lar?
   fonte: vareleira-lar/faq-v1.0.md · versão 1.0 · trecho VLAR-FAQ-1_0-002
   Danos elétricos estão incluídos em todas as contratações do Vareleira Lar? Não. Danos elétricos é uma cobertura adicional ...

2. [pontuação 0.731] Vareleira Lar — Glossário · Danos elétricos
   fonte: vareleira-lar/glossario-v1.0.md · versão 1.0 · trecho VLAR-GL-1_0-009
   ...
```

Cada resultado traz a **pontuação**, o documento, a seção, as cláusulas (quando há), a **fonte** e o início do
texto. Esses metadados permitem apresentar as fontes junto das respostas no Desafio 03. Neste exemplo,
nenhum dos três resultados vem das Condições Gerais, onde a cláusula 3.2 define a cobertura: a FAQ
(*Frequently Asked Questions*, perguntas frequentes) e o glossário
repetem o conteúdo dela em palavras mais próximas da pergunta. A cláusula tem a autoridade sobre a regra, e os
outros dois documentos são material explicativo; essa distinção cabe a uma etapa posterior à busca.

### 5.2 Comparar os três modos de busca

```powershell
python scripts\buscar_trechos.py --busca $busca --modelos $modelos --pergunta "danos elétricos franquia" --modo texto --k 2
python scripts\buscar_trechos.py --busca $busca --modelos $modelos --pergunta "quanto tempo para pagar a indenização?" --modo hibrida --k 2
```

| Modo | O que compara | Bom para | Cuidado |
| --- | --- | --- | --- |
| `vetorial` (padrão) | O significado da pergunta com o dos trechos | Perguntas com palavras diferentes do texto | Sempre devolve algo, mesmo quando nada serve |
| `texto` | As palavras da pergunta com as dos trechos (BM25, algoritmo clássico de pontuação por frequência das palavras), com análise do português | Termos exatos, siglas, números | Compara palavras, sem reconhecer sinônimos |
| `hibrida` | Os dois, combinados por um ranking de fusão (que usa a posição de cada trecho nas duas listas) | Uso geral | A pontuação tem escala própria; compare só resultados do mesmo modo |

**Atividade 2:** execute as três buscas (`--modo vetorial`, `texto` e `hibrida`) para a mesma pergunta, com
`--k 10`, e compare os resultados. Em qual modo a cláusula de origem ficou em melhor posição, ou em nenhum?
Por que as pontuações de cada modo têm escalas diferentes?

**Conferência:** nenhum modo vence em todas as perguntas. As pontuações vêm de cálculos diferentes
(similaridade do cosseno, BM25 e fusão por posição) e só ordenam resultados dentro do mesmo modo.

### 5.3 Casos em que a busca falha

Duas perguntas expõem os limites da busca: a primeira não tem resposta nos documentos, e a segunda tem uma
resposta que a busca encontra mal:

```powershell
python scripts\buscar_trechos.py --busca $busca --modelos $modelos --pergunta "Quanto custa o seguro por mês?"
python scripts\buscar_trechos.py --busca $busca --modelos $modelos --pergunta "Roubaram meu notebook na rua. O seguro paga?" --k 10
```

**Resultado observado na validação:**

- Os documentos **não informam** o preço do seguro, e a busca devolveu três trechos mesmo assim, com
  pontuações perto de 0,65 (sobre "joias e relógios", "franquia" e "segurado"), contra 0,69 a 0,77 nas
  perguntas bem atendidas. A busca **sempre devolve os `k` trechos mais próximos** e não sinaliza "não há
  evidência". Uma pontuação mais baixa é um indício; a amostra deste laboratório é pequena demais para
  definir um limite de corte.
- Para o notebook roubado, a cláusula que importa é a exclusão de **bens portáteis levados para fora do imóvel**
  (cláusula 5.1, item h), no trecho `VLAR-CG-1_0-007`. Nos modos vetorial e híbrido, ela só apareceu na
  **8ª posição**, atrás de trechos sobre joias, sinistro e roubo de conteúdo; no modo `texto`, ficou fora dos
  dez primeiros. Com o `k` padrão (3), ela não chegaria a quem escreve a resposta.

**Atividade 3:** explique por que a recuperação da pergunta sobre o notebook falhou. Em que o texto da
pergunta se parece com os trechos que vieram primeiro, e em que se afasta do trecho da exclusão? O que você
mudaria: o tamanho dos trechos, o `k`, o modo ou o texto dos documentos?

**Conferência:** há mais de uma resposta possível. Hipóteses plausíveis: a pergunta fala de "roubo", e vários
trechos falam de roubo; a exclusão está num trecho com nove outros itens, o que dilui o seu sentido;
"notebook" não aparece no documento, que diz "bens portáteis". Recuperar bem e responder bem são problemas
diferentes: reconhecer a ausência de evidência e recusar a confirmação de uma cobertura individual são
tarefas de uma etapa posterior do curso.

### Prompt para o Copilot: analisar uma recuperação

Anexe `scripts\lab_indexacao.py` e as Condições Gerais sintéticas. Cole o resultado da busca sem
identificadores do seu ambiente:

```text
Leia o resultado da busca abaixo e as Condições Gerais anexadas.
Pergunta: "Roubaram meu notebook na rua. O seguro paga?"
Resultado da busca vetorial com k=10: [cole aqui só a lista de documentos, seções e pontuações].
Explique, em linguagem simples, por que o trecho da cláusula 5.1 não veio entre os primeiros.
Proponha três mudanças possíveis (no tamanho dos trechos, na busca ou nos documentos) e o risco de cada uma.
Não edite arquivos, não execute comandos e não acesse o Azure.
```

**Conferência:** confira cada hipótese no texto da cláusula 5.1 e na saída. O Copilot pode propor mudanças
que pioram outro caso: teste qualquer ideia com as perguntas de conferência antes de aceitá-la.

## Como pedir uma mudança ao Copilot no VS Code

O método do [Desafio 01](01-preparar-ambiente.md#como-pedir-uma-mudança-ao-copilot-no-vs-code) vale aqui:
comece com o projeto limpo, dê o contexto, peça o plano antes de editar, delimite, revise o diff
(comparação entre versões dos arquivos) e verifique
com comandos. Releia também a seção sobre aprovar os comandos do agente (permissões manuais). Neste
desafio, o código acessa o Blob, o serviço de busca e o recurso de modelos, e uma mudança pequena pode
afetar a segurança ou o custo.

### Exemplo: filtrar a busca por documento

Cole com os arquivos anexados. Os testes usam **dublês**, objetos que simulam os serviços externos:

```text
Leia o README, o L100 Desafio 02, scripts/buscar_trechos.py e scripts/lab_indexacao.py anexados.
Quero uma opção nova em buscar_trechos.py: --documento <ID> (por exemplo, VLAR-CG-1.0), para buscar só nos
trechos daquele documento, usando o campo filtrável documento_id do índice.
Antes de editar, proponha o plano: arquivos, funções e testes.
Cuidados obrigatórios: valide o valor com o mesmo padrão dos identificadores do inventário antes de montar o
filtro; nunca monte o filtro concatenando texto sem validar; reaproveite lab_comum e lab_indexacao; mensagens
em pt-BR; mantenha o comportamento atual quando a opção não for usada.
Escreva testes com unittest e dublês, sem acessar o Azure.
Use o Python do ambiente virtual, .\.venv\Scripts\python.exe, e execute apenas:
.\.venv\Scripts\python.exe -m unittest discover -s tests
Não instale pacotes, não acesse o Azure e não altere o índice.
```

**Conferência:** o diff deve validar o identificador antes de usá-lo no filtro (um valor com aspas ou barras
poderia alterar a consulta), acrescentar testes para o valor válido, o inválido e a ausência da opção, e
deixar a indexação intacta. Depois de revisar a implementação da opção, repita um comando completo da
Etapa 5, mantendo `--busca`, `--modelos` e `--pergunta`, e acrescente `--documento VLAR-GL-1.0`.
Um filtro altera os resultados: compare com a busca sem filtro antes de confiar.

> **Dica:** peça uma explicação do diff, com palavras simples, antes de aceitá-lo. Outros pedidos para
> praticar: "explique o que cada campo do índice faz", "gere um roteiro de revisão do tamanho dos trechos
> para o mantenedor" e "mostre como o plano decide entre criar, igual e divergente".

**Modo construtor (opcional).** Para ver como o Copilot resolveria o desafio, peça um plano em uma pasta
separada e compare o resultado com os arquivos deste projeto pelo diff:

```text
Leia o L100, Desafio 02, o README e as instruções do projeto.
Proponha, sem editar, como dividir documentos Markdown em trechos, calcular embeddings e indexar
em Azure AI Search com Python.
Receba destinos explicitamente. Use acesso por Entra ID, sem chaves de API.
Defina o que acontece ao reexecutar e ao encontrar um trecho divergente; não sobrescreva em silêncio.
Não provisione recursos, atribua papéis, envie dados ou exclua arquivos.
```

Qualquer ação que altere o Azure continua dependendo da sua decisão.

## Conferência do resultado

| Verificação | Como conferir | Evidência esperada |
| --- | --- | --- |
| Divisão compreendida | Etapa 1 e Atividade 1 | 54 trechos; você explica o efeito do tamanho máximo |
| Região, modelo e cota | Comandos de "Conferir região e cota" | Modelo disponível e cota livre |
| Plano da infraestrutura | `az deployment group what-if` | Seis criações e a conta de armazenamento sem mudança |
| Infraestrutura criada | `az resource list` e os `show` da Etapa 2 | Três recursos; chaves de API desativadas; modelo e versão fixos |
| Papéis atribuídos | `az role assignment list` | Dois papéis na busca e um nos modelos |
| Simulação | `indexar_documentos.py` sem `--executar` | 54 trechos a criar, nenhum embedding gerado |
| Indexação | `indexar_documentos.py --executar` | 54 criados; tokens usados informados |
| Índice conferido | `verificar_indice.py` | Cinco conferências aprovadas |
| Reexecução previsível | Simulação e `--executar` de novo | 54 iguais; nenhuma chamada ao modelo |
| Divergência tratada | Experimento opcional | `[PARADA]`, código 3 e nada alterado |
| Consulta | `buscar_trechos.py` nos três modos | Trechos com pontuação e fonte; nenhuma resposta escrita |
| Caso de falha explicado | Atividade 3 | Hipótese sobre o trecho da exclusão, conferida no texto |

Antes de encerrar, registre em local privado o grupo de recursos, os nomes da busca e dos modelos e a decisão
de manter, pausar ou remover os recursos. Ao compartilhar evidências, remova das saídas do terminal os
identificadores do ambiente, os nomes de recursos e as contas de usuário.

## Solução de problemas

| Sintoma | O que conferir | O que evitar |
| --- | --- | --- |
| `InsufficientResourcesAvailable` ao criar o serviço de busca | A região está sem capacidade para novos serviços naquela camada. Crie só a busca em outra região permitida, com `--parameters localizacaoBusca=<região>`, e repita a Etapa 2 | Insistir indefinidamente ou trocar de assinatura sem autorização |
| `FlagMustBeSetForRestore` ao criar o recurso de modelos | Um recurso com o mesmo nome foi excluído há menos de 48 horas e está em exclusão reversível; purgue-o (veja [Custos, pausa e limpeza](#custos-pausa-e-limpeza)) | Restaurar um recurso antigo sem saber o que havia nele |
| `ServiceDeleting` ao criar o serviço de busca | O nome ainda está sendo liberado em segundo plano. Aparece logo depois de excluir um serviço de busca, inclusive na camada `basic`; na validação, com a camada gratuita, o nome só voltou a ficar livre de 18 a 27 minutos depois. Aguarde ou use outro nome com `--parameters nomeBusca=<novo-nome>` | Repetir o comando sem parar, em laço |
| `InvalidResourceProperties` ou `DeploymentModelNotSupported` | O modelo, a versão ou o tipo de deployment não existem na região: refaça "Conferir região e cota" e ajuste os parâmetros | Escolher um modelo qualquer sem ver a lista da região |
| `InsufficientQuota` ao criar o deployment | A cota regional do modelo acabou: reduza `capacidadeEmbeddings`, exclua deployments sem uso ou escolha outra região | Pedir aumento de cota sem necessidade |
| `AuthorizationFailed` ou falha em `roleAssignments` | Seu papel no escopo; veja "Atribuição dos papéis por um administrador" | Pedir acesso de proprietário da assinatura só para simplificar |
| `RequestDisallowedByPolicy` | A política citada no erro e a região escolhida | Desativar a política ou afrouxar as proteções do Bicep para passar |
| `[ERRO]` "A base documental no contêiner não confere com o inventário" (código 3) | O Desafio 01: envie e verifique os documentos | Indexar a partir de uma cópia local sem conferir |
| `[ERRO]` "A sua identidade não tem permissão no serviço de busca" (código 2) | Os papéis `Search Service Contributor` e `Search Index Data Contributor`; aguarde até 10 minutos depois de atribuí-los [16] | Ligar chaves de API ou abrir a rede |
| `[ERRO]` "O serviço de modelos recusou o pedido (HTTP 401 ou 403)" (código 2) | O papel `Cognitive Services OpenAI User`, o `az login` e o tenant (`--tenant-id`); logo após uma atribuição, o 401 pode ir e voltar por alguns minutos [16] | Colar tokens no chat ou em arquivos |
| `[ERRO]` "O deployment ... não foi encontrado" (código 2) | O nome do **deployment** (`$deployment`), não o do modelo, e o nome do recurso | Criar outro deployment só para o erro desaparecer |
| `[ERRO]` "O Azure respondeu 404 ('Subdomain does not map to a resource')" (código 2) | O nome em `$modelos`. Com o nome certo, o serviço de modelos às vezes responde assim de forma intermitente; o script já repete até seis vezes, com conexão nova a cada pedido. Se persistir, aguarde alguns minutos e repita | Recriar o recurso ou o deployment só para o erro desaparecer |
| `[ERRO]` "Não foi possível conectar ao serviço de busca" ou "ao recurso de modelos" (código 2) | O nome em `$busca` ou `$modelos`, a rede e se o recurso existe (pode ter sido pausado) | Inventar um nome |
| `[ERRO]` "limite de requisições ou de tokens por minuto (HTTP 429)" (código 2) | Aguarde um minuto e repita: o script retoma sem duplicar | Aumentar a cota sem necessidade |
| `[ERRO]` "falta informar o valor" ou "faltam argumentos obrigatórios: --busca" (código 1) | `$busca` ou `$modelos` vazia: repita a consulta dos nomes, na Etapa 2 | Inventar os nomes |
| `[ERRO]` "devolveu vetores de N dimensões" (código 1) | O modelo do deployment tem outro tamanho de vetor: use `--dimensoes N` com um índice novo (`--indice`) | Alterar o índice existente manualmente |
| `[PARADA]` com índice de outra definição (código 3) | As diferenças listadas; use outro `--indice` ou, de propósito, `--recriar-indice` | Usar `--recriar-indice` sem conferir o nome do índice |
| `[PARADA]` com `[divergente]` (código 3) | Quem mudou os documentos, o tamanho máximo ou o deployment, e por quê | Usar `--substituir-divergentes` sem investigar |
| `[PARADA]` com `[órfão]` (código 3) | Se os documentos encolheram ou o tamanho mudou | Usar `--remover-orfaos` sem investigar |
| `FALHA` em "Trechos do índice" logo depois de indexar | O índice leva segundos para refletir a gravação; repita. Se persistir, execute a simulação | Indexar outra vez sem olhar o plano |
| `FALHA` em "Modelo dos vetores" | O deployment mudou de modelo depois da indexação; recrie o índice com `--recriar-indice` | Misturar vetores de modelos diferentes no mesmo índice |
| `FALHA` em "Busca vetorial" | Se o índice foi indexado com o tamanho padrão; se os documentos mudaram; veja o primeiro resultado de cada pergunta | Afrouxar as perguntas só para passar |
| `FALHA` em "Acesso sem credenciais negado" | Configuração da busca e dos modelos (`disableLocalAuth`); não siga até corrigir | Ignorar a falha ou ligar chaves de API |
| Copilot propõe chave de API, `--yes`, `--recriar-indice` ou conceder papel | As instruções do projeto; refaça o pedido com os limites | Executar a proposta como se fosse material validado |

As demais situações (`az`, login, tenant, Python, ambiente virtual, `Restricted Mode`) estão na
[Solução de problemas do Desafio 01](01-preparar-ambiente.md#solução-de-problemas). Se precisar de ajuda,
consulte os [canais e limites do suporte](../../SUPPORT.md). Não conceda papéis, altere políticas corporativas ou desative controles
como tentativa de diagnóstico.

## Custos, pausa e limpeza

O uso do Copilot segue o plano da sua conta e as regras de consumo dele, separadamente da assinatura Azure.
A cobrança do Azure vem dos recursos criados nos Desafios 01 e 02.

**O que gera custo:**

- **Serviço de busca da camada `basic`:** cobra por hora **enquanto o serviço existir**, mesmo sem uso. É o
  recurso cuja cobrança continua durante períodos sem consultas. Os embeddings cobram por tokens usados,
  e os documentos ocupam cerca de 21 KB no Blob. A camada `free` não cobra e permite um serviço por assinatura, com 50 MB
  de armazenamento; um serviço `free` inativo por um longo período pode ser excluído. [12][18] A camada
  `free` também não oferece ranking semântico, previsto para níveis posteriores. [19]
- **Embeddings:** cobrados por token processado. Na validação, uma indexação completa usou 7.134 tokens, e
  cada pergunta de consulta usa cerca de 10 a 15 tokens (estimativa pelo tamanho do texto). O deployment
  `GlobalStandard` não cobra por existir: a cobrança vem dos tokens, e a capacidade define a cota. [17]
- **Armazenamento:** o Blob Storage do Desafio 01, descrito em
  [Custos, pausa e limpeza](01-preparar-ambiente.md#custos-pausa-e-limpeza) daquele guia.

Os custos não foram medidos na validação, e os preços variam por região, camada e data. Consulte os
[preços atuais do Azure AI Search](https://azure.microsoft.com/en-us/pricing/details/search/) e dos
[modelos do Azure OpenAI](https://azure.microsoft.com/en-us/pricing/details/azure-openai/) para a sua região,
calcule o custo na [calculadora de preços](https://azure.microsoft.com/en-us/pricing/calculator/) e acompanhe
o consumo no Cost Management. Os orçamentos enviam alertas, e o consumo continua até a remoção dos
recursos. [20]

**Pausa e continuidade.** Os próximos desafios reutilizam o índice, o recurso de modelos e o deployment.
Para continuar nos próximos dias, mantenha-os. Em uma pausa longa, remova os recursos de busca e modelos
pelo procedimento abaixo e preserve os documentos no Blob. A retomada recria esses recursos e o índice.

### Pausar **[altera o Azure]**

Apague só o serviço de busca e o recurso de modelos, que estão no mesmo grupo da conta de armazenamento.
Antes, confira os nomes em `$busca` e `$modelos` e as etiquetas do grupo: cada comando apaga o recurso que
apontar.

```powershell
$regiao = az resource show --subscription $assinatura --resource-group $grupo --name $modelos --resource-type Microsoft.CognitiveServices/accounts --query location --output tsv
az search service delete --subscription $assinatura --resource-group $grupo --name $busca --yes
az cognitiveservices account delete --subscription $assinatura --resource-group $grupo --name $modelos
az cognitiveservices account purge --subscription $assinatura --location $regiao --resource-group $grupo --name $modelos
```

O recurso de modelos excluído fica em **exclusão reversível por 48 horas**, e o nome não pode ser reutilizado
nesse prazo. O comando `purge` o exclui definitivamente e exige o papel *Contributor* na assinatura, não só
no grupo. [21] A variável `$regiao` contém a região do **recurso de modelos**.

Para **retomar**, repita a Etapa 2 e depois a Etapa 4. Se aparecer `ServiceDeleting`, o nome da
busca ainda está sendo liberado: aguarde ou implante com `--parameters nomeBusca=<novo-nome>` e use esse nome em
`$busca`. Confira o índice com `verificar_indice.py` antes de continuar para o Desafio 03.

### Limpeza completa **[altera o Azure]**

Faça a limpeza ao encerrar o laboratório. Confira o alvo antes de apagar:

```powershell
az group show --subscription $assinatura --name $grupo --query "{Nome:name,Etiquetas:tags}" --output json
az resource list --subscription $assinatura --resource-group $grupo --query "[].{Nome:name,Tipo:type}" --output table
$regiao = az resource show --subscription $assinatura --resource-group $grupo --name $modelos --resource-type Microsoft.CognitiveServices/accounts --query location --output tsv
```

Prossiga somente se as etiquetas mostrarem `laboratorio` com o valor `vareleira-rag` e a lista tiver apenas
o que foi criado nos Desafios 01 e 02 (mais o Key Vault, se você fez o
[Desafio 07](07-identidade-da-aplicacao.md): exclua e expurgue o cofre antes, pela Etapa 8.2 dele). Então
exclua **o grupo de recursos do laboratório** (o comando pede confirmação) e purgue o recurso de modelos, que
continua em exclusão reversível:

```powershell
az group delete --subscription $assinatura --name $grupo
az group exists --subscription $assinatura --name $grupo
az cognitiveservices account list-deleted --subscription $assinatura --query "[].{Nome:name,Regiao:location}" --output table
az cognitiveservices account purge --subscription $assinatura --location $regiao --resource-group $grupo --name $modelos
```

O segundo comando deve responder `false`. O terceiro lista o recurso de modelos aguardando a purga, e o
último o exclui definitivamente. A purga funciona mesmo depois que o grupo foi apagado. Sem a purga, o nome
fica preso por 48 horas e, se você recriar o grupo com o mesmo nome, o Bicep falha com
`FlagMustBeSetForRestore`. O nome do serviço de busca também demora a ser liberado, em segundo plano: na
validação, de 18 a 27 minutos na camada gratuita. Para recriar o grupo logo, use outro valor em
`nomeBusca`.

> **Atenção:** nunca exclua um grupo compartilhado ou que já existia antes do laboratório. Nesse caso, exclua
> somente o serviço de busca e o recurso de modelos criados aqui, como em "Pausar", depois de conferir os
> nomes e as etiquetas `laboratorio=vareleira-rag`.

## Situação da validação

Data de referência: 9 de outubro de 2026. O registro detalhado, com a matriz de testes, as medições, as
correções e as observações de operação, está em
[docs\validacao\l100-02-indexar-documentos.md](../../docs/validacao/l100-02-indexar-documentos.md).

**Versões testadas:** Windows, Python 3.12.10, Azure CLI 2.89.0, Bicep 0.48.1, `azure-search-documents`
12.0.0, `openai` 3.23.0 e as bibliotecas do Desafio 01.

| Item | Situação | Detalhe |
| --- | --- | --- |
| Comandos das Etapas 1 a 5, experimento de divergência, pausa, retomada e limpeza | Concluído | Os 24 blocos de PowerShell do guia foram executados em PowerShell 7.6, em `brazilsouth`, sobre um grupo novo criado pelo Desafio 01; leituras, reexecução e consultas também no Windows PowerShell 5.1 |
| Camada gratuita (`free`) e serviço de busca em região diferente da dos modelos (`localizacaoBusca`) | Concluído | Testados à parte, de ponta a ponta |
| Scripts, Bicep e testes automáticos (sem Azure) | Concluído | Testes aprovados; `az bicep lint`, `build` e `format` sem avisos |
| Desafio 01 depois das mudanças em `lab_comum.py` e `main.bicep` | Concluído | Repetido em um grupo novo |
| Links, âncoras, URLs e referências dos guias | Concluído | Nenhum link ou âncora inválido |
| Aprovação do conteúdo dos documentos sintéticos | Confirmada | Pelo mantenedor, em 9 de outubro de 2026; registro no inventário |
| Aprovação do texto, do código e dos resultados | Confirmada | Pelo mantenedor, em 9 de outubro de 2026; não representa novos testes |
| Outros ambientes: macOS, Linux, WSL (Windows Subsystem for Linux), Python diferente do 3.12, instalação pelo PyPI (repositório público de pacotes Python) e Windows PowerShell 5.1 na implantação e na limpeza | Pendente | Executar os comandos do guia nesses ambientes e registrar as diferenças |
| Contas e regiões: assinaturas gratuitas ou estudantis, políticas restritivas, papéis menores que *Owner* e regiões além de `brazilsouth` e `eastus2` | Pendente | Repetir a Etapa 2 em cada cenário |
| Mensagens de erro `InsufficientQuota`, `RequestDisallowedByPolicy` e `AuthorizationFailed`; limite de requisições (HTTP 429); outro modelo ou outra dimensão de embeddings | Pendente | Provocar cada caso em ambiente de teste e confirmar a orientação da tabela de problemas; HTTP 429 e outras dimensões estão cobertos só por testes automáticos |
| Interações com o Copilot: prompts do guia, exemplo de pedido de mudança e modo construtor | Pendente | Executar no VS Code e registrar as respostas |
| Custo e exclusão interativa | Pendente | Medir o custo no Cost Management após uma execução completa e executar `az group delete` sem `--yes` |

**Autoria.** Código, testes e texto produzidos com apoio de IA (Claude Sonnet 5.5, no GitHub Copilot CLI); o
Astra, modelo preferido do mantenedor para a documentação, não estava disponível. Revisão editorial por
GPT-6.1 Sol, em 9 de outubro de 2026. Os modelos de autoria e revisão são
independentes do modelo que você escolhe no Copilot e do modelo de embeddings da aplicação
(`text-embedding-3-small`).

## Glossário

| Termo | Significado no exercício |
| --- | --- |
| Azure AI Search | Serviço de busca do Azure; guarda índices e encontra registros por palavras, por vetores ou pelos dois |
| Índice (de busca) | Coleção de registros pesquisáveis; aqui, um registro por trecho de documento |
| Trecho (*chunk*) | Parte de um documento tratada como unidade na busca; o programa a divide por seção e tamanho máximo |
| Seção | Parte do documento aberta por um título; um trecho nunca atravessa duas seções |
| Embedding | Lista de números que representa o significado de um texto |
| Vetor | A lista de números de um embedding; aqui, com 1.536 posições |
| Dimensões | Quantidade de números de cada vetor; o índice e o modelo precisam usar a mesma |
| Busca vetorial | Busca pelos vetores mais próximos do vetor da pergunta |
| Busca por texto | Busca pelas palavras da pergunta, com pontuação BM25 (algoritmo clássico de pontuação por frequência das palavras) |
| Busca híbrida | Combinação da busca por texto e da vetorial, unida por um ranking de fusão |
| Cosseno (similaridade) | Medida que compara a direção de dois vetores, e não o tamanho |
| HNSW | Estrutura em grafo que encontra vetores parecidos sem comparar todos, com resultado aproximado |
| Pontuação | Número que ordena os resultados de uma busca; só se compara dentro do mesmo modo |
| Token | Pedaço de texto, em geral uma palavra ou parte dela; unidade de leitura e de cobrança dos modelos |
| Microsoft Foundry (recurso de modelos) | Plataforma do Azure para modelos de inteligência artificial (IA); o recurso `AIServices` hospeda os deployments |
| Implantação (de infraestrutura) | Aplicação de um arquivo Bicep para criar ou atualizar recursos; distinta do deployment de modelo |
| Deployment (de modelo) | Instância nomeada de um modelo, que recebe as chamadas; o nome do deployment é distinto do nome do modelo |
| `text-embedding-3-small` | Modelo de embeddings usado aqui, versão 1, com vetores de 1.536 números |
| `GlobalStandard` | Tipo de deployment que cobra por token e pode processar o texto em qualquer geografia Azure |
| Cota (de tokens por minuto) | Limite de uso por região e modelo; a capacidade do deployment reserva parte dela, sem cobrança por si só |
| Camada (SKU) | Nível de um serviço, que define capacidade, recursos e preço; na busca: `free`, `basic` ou `standard` |
| Chaves de API desativadas | Configuração que impede autenticar com chave: só o Entra ID autentica |
| Search Service Contributor | Papel que permite criar e alterar índices |
| Search Index Data Contributor | Papel que permite gravar e consultar documentos de um índice |
| Cognitive Services OpenAI User | Papel que permite usar os deployments de um recurso, sem administrá-los |
| Impressão digital | Hash SHA-256 do que define o registro de um trecho; mostra se ele mudou |
| Trecho órfão | Trecho que está no índice, mas que os documentos não produzem mais |
| Teste de fumaça | Conferência inicial de funcionamento com poucos casos; a avaliação da qualidade exige um conjunto mais amplo |
| Exclusão reversível (recurso de modelos) | Retenção por 48 horas do recurso excluído; o nome só volta a ser usado depois da purga |
| Purga | Exclusão definitiva de um recurso em exclusão reversível |
| Tamanho máximo do trecho | Limite, em caracteres, que o script usa ao agrupar parágrafos |
| RAG | *Retrieval-Augmented Generation* (geração aumentada por recuperação): geração de respostas apoiada em evidências recuperadas de uma base |
| Recuperação | Etapa que encontra os trechos que sustentarão uma resposta |
| MAF | Microsoft Agent Framework, biblioteca usada para implementar o agente do Desafio 05 |
| SDK | *Software Development Kit*: conjunto de bibliotecas para usar um serviço a partir de uma linguagem de programação |
| API | *Application Programming Interface*: interface pela qual um programa usa um serviço |
| HTTP | *Hypertext Transfer Protocol*, protocolo da web; nas respostas, 401 indica falta de autenticação, 403 falta de permissão e 429 excesso de requisições |
| Hash | Resumo calculado do conteúdo para conferir sua integridade |
| What-if | Previsão de alterações de infraestrutura antes da implantação |
| Reexecução previsível | Repetir um comando sem duplicar nem alterar o que já está certo; também chamada de idempotência |

## Referências

Fontes oficiais consultadas em 9 de outubro de 2026. Nomes de interface, limites, preços e disponibilidade
mudam: confira a versão atual antes de aplicar.

1. [O que é o Azure AI Search](https://learn.microsoft.com/en-us/azure/search/search-what-is-azure-search).
2. [Criar um índice no Azure AI Search](https://learn.microsoft.com/en-us/azure/search/search-how-to-create-search-index).
3. [Implantar modelos no Microsoft Foundry: tipos de implantação](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/deployment-types).
4. [Gerar embeddings com o Azure OpenAI](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/embeddings).
5. [Conectar-se ao Azure AI Search com papéis](https://learn.microsoft.com/en-us/azure/search/search-security-rbac).
6. [Criar um índice vetorial no Azure AI Search](https://learn.microsoft.com/en-us/azure/search/vector-search-how-to-create-index).
7. [Dividir documentos grandes para a busca vetorial](https://learn.microsoft.com/en-us/azure/search/vector-search-how-to-chunk-documents).
8. [Fase de divisão em trechos de uma solução RAG](https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/rag/rag-chunking-phase).
9. [Cotas e limites do Azure OpenAI no Foundry](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/quota).
10. [Escolher o preço e a camada do Azure AI Search, com a disponibilidade por região](https://learn.microsoft.com/en-us/azure/search/search-sku-tier).
11. [Referência Bicep do serviço de busca](https://learn.microsoft.com/en-us/azure/templates/microsoft.search/searchservices) e [dos recursos de IA](https://learn.microsoft.com/en-us/azure/templates/microsoft.cognitiveservices/accounts).
12. [Limites de serviço do Azure AI Search](https://learn.microsoft.com/en-us/azure/search/search-limits-quotas-capacity).
13. [Tipos de implantação e onde os dados são processados](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/deployment-types#data-processing-locations).
14. [Funções de arquivos de parâmetros do Bicep, incluindo `readEnvironmentVariable`](https://learn.microsoft.com/en-us/azure/azure-resource-manager/bicep/bicep-functions-parameters-file).
15. [Previsão de alterações com Bicep what-if](https://learn.microsoft.com/en-us/azure/azure-resource-manager/bicep/deploy-what-if).
16. [Solução de problemas do RBAC do Azure](https://learn.microsoft.com/en-us/azure/role-based-access-control/troubleshooting).
17. [Preços dos modelos do Azure OpenAI](https://azure.microsoft.com/en-us/pricing/details/azure-openai/).
18. [Preços do Azure AI Search](https://azure.microsoft.com/en-us/pricing/details/search/).
19. [Experimentar o Azure AI Search gratuitamente](https://learn.microsoft.com/en-us/azure/search/search-try-for-free).
20. [Orçamentos e alertas no Azure Cost Management](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/tutorial-acm-create-budgets).
21. [Recuperar ou purgar recursos do Foundry excluídos](https://learn.microsoft.com/en-us/azure/ai-services/recover-purge-resources).

As atribuições do contexto fictício estão em [NOTICE.md](../../NOTICE.md). O texto deste guia está sob a
licença Creative Commons Atribuição 4.0 (CC BY 4.0; veja [LICENSE](../../LICENSE)).
