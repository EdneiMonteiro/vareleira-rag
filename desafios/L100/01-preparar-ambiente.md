# L100 — Desafio 01: preparar o ambiente e organizar a base documental

[Início do laboratório](../../README.md) · Nível L100: fundamentos

| Item | Descrição |
| --- | --- |
| Situação | Exercício executável, validado no Azure em 9 de outubro de 2026 (Windows e PowerShell). Os documentos de seguro são sintéticos e novos. Estão pendentes a revisão do conteúdo pelo mantenedor e a revisão humana do texto; veja [Situação da validação](#situação-da-validação). |
| Público | Pessoas de negócio, arquitetura, operações e desenvolvimento. Use o Visual Studio Code (VS Code) para executar os comandos e conferir os resultados; escrever código é opcional. |
| Resultado | Uma conta de armazenamento no Azure com os três documentos sintéticos do Vareleira Lar, enviados e conferidos por script. |
| Custo | O Azure Blob Storage cobra por capacidade armazenada e por operações; este desafio armazena cerca de 21 KB. A remoção dos recursos está em [Custos, pausa e limpeza](#custos-pausa-e-limpeza). |

## Conteúdo

- [Cenário](#cenário)
- [Objetivos](#objetivos)
- [Artefatos e disponibilidade](#artefatos-e-disponibilidade)
- [Tecnologias e conceitos](#tecnologias-e-conceitos)
- [Pré-requisitos](#pré-requisitos)
- [Etapa 1: abrir o projeto no VS Code](#etapa-1-abrir-o-projeto-no-vs-code)
- [Etapa 2: conferir o acesso ao Azure](#etapa-2-conferir-o-acesso-ao-azure)
- [Etapa 3: conhecer a base documental e o inventário](#etapa-3-conhecer-a-base-documental-e-o-inventário)
- [Etapa 4: criar a infraestrutura com Bicep](#etapa-4-criar-a-infraestrutura-com-bicep)
- [Etapa 5: enviar e conferir os documentos](#etapa-5-enviar-e-conferir-os-documentos)
- [Como pedir uma mudança ao Copilot no VS Code](#como-pedir-uma-mudança-ao-copilot-no-vs-code)
- [Conferência do resultado](#conferência-do-resultado)
- [Solução de problemas](#solução-de-problemas)
- [Custos, pausa e limpeza](#custos-pausa-e-limpeza)
- [Situação da validação](#situação-da-validação)
- [Glossário](#glossário)
- [Referências](#referências)

## Cenário

Em 2025, na história fictícia da Vareleira, Beatriz Torres, responsável pelo Atendimento, identifica
respostas diferentes para perguntas semelhantes: as equipes consultam versões distintas dos documentos.
Antes de construir um assistente, a sua equipe precisa decidir quais fontes ele poderá consultar.

O primeiro produto é o **Vareleira Lar**, seguro residencial fictício. Teresa Moura, diretora técnica de
Subscrição, é a autoridade sobre as regras do produto, e Beatriz representa as necessidades de
Atendimento e corretores. A [introdução oficial da jornada](https://vareleira.com/rag.html) descreve o
contexto.

**Missão:** preparar a estação de trabalho, conhecer a base documental e guardá-la no Azure Blob
Storage, serviço de armazenamento de objetos. Busca, respostas de modelo e chat ficam para os próximos
desafios.

> **Lembre-se:** o cenário é fictício. Não use apólices, nomes, endereços ou documentos de segurados
> reais, mesmo que tenha acesso a eles no trabalho.

## Objetivos

Ao concluir este desafio, você terá:

- aberto o projeto no Visual Studio Code (VS Code) e usado o GitHub Copilot para entendê-lo antes de
  executar comandos;
- identificado a assinatura de destino e conferido as suas permissões, sem alterar nada;
- lido o inventário e a base documental sintética do Vareleira Lar: Condições Gerais, glossário e
  perguntas frequentes;
- criado, com Bicep, uma conta de armazenamento com acesso anônimo e chaves de conta desativados, e um
  contêiner de blobs;
- enviado os documentos com um script que simula antes de agir e só troca um blob divergente a pedido
  explícito;
- conferido o conteúdo, os metadados e a recusa de leitura anônima;
- aprendido a remover os recursos criados.

**Próximos desafios:** o [Desafio 02](02-indexar-documentos.md) calcula as representações numéricas dos
textos, chamadas de *embeddings*, e indexa os documentos no Azure AI Search. Em seguida, o
[Desafio 03](03-responder-com-fontes.md) gera respostas com fontes usando um modelo no Microsoft Foundry;
o [Desafio 04](04-recusar-sem-evidencia.md) recusa o que os documentos não autorizam; o
[Desafio 05](05-agente-com-maf.md) implementa o agente com Microsoft Agent Framework (MAF); o
[Desafio 06](06-avaliar-respostas.md) mede a qualidade da recuperação e das respostas; e o
[Desafio 07](07-identidade-da-aplicacao.md) usa service principal (identidade de uma aplicação no
Microsoft Entra ID) e Azure Key Vault (serviço de guarda de segredos).

Os desafios do curso constroem, em conjunto, uma solução de **geração aumentada por recuperação** (RAG,
do inglês *Retrieval-Augmented Generation*): ela recupera trechos de documentos e os usa para gerar a
resposta. Este desafio prepara as fontes, a primeira parte da solução.

## Artefatos e disponibilidade

| Artefato | Onde encontrar | Situação |
| --- | --- | --- |
| Contexto e limites do laboratório | [README](../../README.md) | Disponível |
| Contexto Vareleira 0.1.0 | [Contexto em JSON (*JavaScript Object Notation*, formato de dados em texto)](https://github.com/EdneiMonteiro/vareleira/blob/d17a24bd9fdf16a5b3dba34e07764852a8477859/dados/contexto-v0.1.0.json) | Disponível; traz personagens e escopo, sem condições gerais |
| Avisos de uso | [Ficção, dados, custos e limites de uso](../../DISCLAIMER.md) | Disponível |
| Instruções do projeto para o Copilot | [.github\copilot-instructions.md](../../.github/copilot-instructions.md) e [Python](../../.github/instructions/python-azure.instructions.md), [Bicep](../../.github/instructions/bicep.instructions.md), [dados](../../.github/instructions/dados-sinteticos.instructions.md) | Disponíveis |
| Infraestrutura (Bicep) | [infra\main.bicep](../../infra/main.bicep) | Disponível; validada |
| Parâmetros do L100 | [infra\levels\l100.bicepparam](../../infra/levels/l100.bicepparam) | Disponível; validado |
| Inventário da base documental | [dados\l100\inventario.json](../../dados/l100/inventario.json) | Disponível |
| Condições Gerais sintéticas | [vareleira-lar-condicoes-gerais-v1.0.md](../../dados/l100/documentos/vareleira-lar-condicoes-gerais-v1.0.md) | Disponível; aprovação do mantenedor confirmada |
| Glossário sintético | [vareleira-lar-glossario-v1.0.md](../../dados/l100/documentos/vareleira-lar-glossario-v1.0.md) | Disponível; aprovação do mantenedor confirmada |
| Perguntas frequentes sintéticas | [vareleira-lar-faq-v1.0.md](../../dados/l100/documentos/vareleira-lar-faq-v1.0.md) | Disponível; aprovação do mantenedor confirmada |
| Carga de documentos | [scripts\carregar_documentos.py](../../scripts/carregar_documentos.py) | Disponível; validada |
| Conferência da carga | [scripts\verificar_documentos.py](../../scripts/verificar_documentos.py) | Disponível; validada |
| Atualização dos hashes (para quem edita documentos) | [scripts\atualizar_hashes_inventario.py](../../scripts/atualizar_hashes_inventario.py) | Disponível |
| Código compartilhado dos scripts | [scripts\lab_comum.py](../../scripts/lab_comum.py) | Disponível |
| Dependências Python | [requirements\l100.txt](../../requirements/l100.txt) | Disponível |
| Testes automáticos (sem Azure) | pasta `tests` | Disponíveis |

> **Atenção:** os momentos que alteram o Azure têm a marca **[altera o Azure]**: criar a infraestrutura
> (Etapa 4), enviar os documentos e executar o experimento opcional de divergência (Etapa 5) e remover os
> recursos. Leituras de arquivos e consultas não alteram nada. A decisão de executar é sua, mesmo quando você
> pede ao Copilot que "implemente" ou "corrija" algo.

## Tecnologias e conceitos

| Tecnologia | Função neste desafio | Limite ou cuidado |
| --- | --- | --- |
| VS Code | Abrir os arquivos, visualizar Markdown e usar terminal e chat no mesmo projeto | As permissões no Azure dependem dos papéis atribuídos à sua conta |
| Git e GitHub | Obter o repositório e acompanhar versões e alterações | O repositório guarda os documentos de origem; a carga os copia para o Azure Blob Storage |
| GitHub Copilot | Explicar, planejar e propor mudanças nos arquivos | Respostas e alterações exigem revisão; o consumo é cobrado à parte do Azure |
| Azure CLI (*command-line interface*, interface de linha de comando) | Executar comandos de administração e consulta ao Azure | Depois do `az login`, as permissões são as dos papéis atribuídos à sua conta |
| Microsoft Entra ID | Identificar usuários e aplicações que acessam os recursos | Autentica a identidade; a autorização depende dos papéis atribuídos |
| Bicep | Descrever a infraestrutura que deve existir no Azure | Cria os recursos; os scripts enviam os documentos |
| Azure Blob Storage | Armazenar os documentos que o Desafio 02 prepara para a busca (ingestão) | Guarda os arquivos; a busca e o modelo de linguagem são serviços separados |
| Python | Executar os scripts de carga e conferência | A extensão Python do VS Code ajuda a editar e a escolher o interpretador; o Python é instalado à parte |
| SDK (*Software Development Kit*, conjunto de bibliotecas de programação) do Azure para Python | Bibliotecas `azure-identity` e `azure-storage-blob`, que os scripts usam para acessar o Blob Storage | O acesso aos dados exige um papel de dados atribuído à sua conta |

Um **tenant** é o diretório de identidades do Microsoft Entra ID. Uma **assinatura** organiza o uso e a
cobrança de recursos Azure e está associada a um diretório. Um **grupo de recursos**, dentro da
assinatura, reúne recursos administrados em conjunto, como os deste laboratório. [1]

No Blob Storage, a hierarquia é:

```text
Conta de armazenamento
    Contêiner de blobs
        Documento sintético
        Outro documento sintético
```

Um **blob** é o objeto armazenado, por exemplo um arquivo de texto, e o **contêiner de blobs** agrupa
blobs dentro da conta de armazenamento. [2]

> **Lembre-se:** o contêiner de blobs guarda documentos; o contêiner de aplicação, como o que hospedará
> o chat em um nível posterior, executa software.

Três elementos distintos entram neste desafio, e cada um é obtido separadamente: a autenticação, o papel de
gerenciamento e o papel de dados.

> **Para guardar na memória: crachá, obra e cofre.** O **crachá** é a autenticação: `az login` comprova
> quem você é. A **autorização de obra** é o papel de gerenciamento que permite construir, como criar a
> conta de armazenamento. A **chave do cofre** é o papel de dados, como *Storage Blob Data Contributor*,
> que permite ler e gravar os documentos. Mnemônico criado para este curso.

## Pré-requisitos

Os comandos deste guia são escritos para Windows e PowerShell, no terminal integrado do VS Code. Em
outros sistemas, adapte e revise a sintaxe antes de executar.

| Pré-requisito | Como preparar | Necessário agora? |
| --- | --- | --- |
| Assinatura Azure ativa | Obtenha acesso à sua assinatura ou à disponibilizada pelo instrutor | Sim |
| Autorização da organização | Confirme tenant, assinatura, região e restrições com o responsável | Sim |
| Permissão para criar recursos | Papel como *Contributor* no grupo de recursos ou na assinatura | Sim, na Etapa 4 |
| Permissão para atribuir papéis (opcional) | *Owner*, *User Access Administrator* ou equivalente no escopo; sem ela, um administrador concede o papel de dados | Dispensável, se um administrador ajudar |
| VS Code e Git | Instale o editor e o Git conforme a política da sua máquina | Sim |
| Conta GitHub com acesso ao Copilot | Siga a [configuração oficial do Copilot](https://code.visualstudio.com/docs/setup/copilot) | Sim, para os exercícios assistidos |
| Azure CLI | Siga a [instalação oficial no Windows](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli-windows). Versão testada: 2.89.0 | Sim |
| Bicep | Vem pela Azure CLI. Se ela avisar que não encontrou o Bicep, execute `az bicep install`. Opcional: a extensão Bicep do VS Code realça e valida o arquivo [3] | Sim, na Etapa 4 |
| Python 3.12 ou superior e extensão Python da Microsoft | Consulte o [guia do VS Code](https://code.visualstudio.com/docs/languages/python) | Sim, na Etapa 5 |

Os nomes dos comandos do editor podem variar com o idioma e a versão. A conta GitHub (Copilot) e a conta
Azure são independentes: autentique-se em cada uma.

O acesso aos blobs pelo Entra ID exige um papel de dados, como **Storage Blob Data Contributor**, no
escopo adequado; criar a conta de armazenamento não o concede. [4] Atribuir papéis também exige uma
permissão própria. Peça ao administrador o papel de dados restrito ao contêiner (menor privilégio), em vez
de acesso de proprietário da assinatura.

> **Boa prática:** confira a assinatura, as suas permissões e as políticas da organização em verificações
> separadas, como na Etapa 2. O estado `Enabled` indica que a assinatura está ativa; as permissões e as
> políticas determinam o que você pode criar e ler.

## Etapa 1: abrir o projeto no VS Code

**Objetivo:** trabalhar com a pasta completa e permitir que o Copilot consulte o contexto do curso, em
vez de responder apenas com base na pergunta.

1. Se já tiver o repositório local, use **File > Open Folder** e escolha a pasta `vareleira-rag`.
   Caso contrário, abra a Paleta de Comandos com `Ctrl+Shift+P`, escolha **Git: Clone** e informe
   `https://github.com/EdneiMonteiro/vareleira-rag.git`.
2. Confirme que o Explorador mostra `README.md`, `infra`, `scripts` e `dados`. Se você recebeu uma
   revisão específica do instrutor, confira que está nela.
3. Se o VS Code perguntar se você **confia nos autores** da pasta, ou mostrar **Restricted Mode** (modo
   restrito) na barra de status, leia antes "Confiança na pasta e modo restrito", logo abaixo.
4. Abra este desafio. Use **Markdown: Open Preview to the Side**, pela Paleta de Comandos, para
   visualizar o texto e os links ao lado do arquivo. Se as tabelas ficarem cortadas, use **Markdown:
   Open Preview** para abrir a prévia em uma aba inteira.
5. Abra **Terminal > New Terminal** e escolha PowerShell. Confira que o terminal está na pasta do
   repositório antes de executar comandos.
6. Configure o GitHub Copilot conforme o guia oficial e abra a visualização de chat. Digite `#` no chat
   para escolher arquivos (ou use a opção de anexar contexto) e inclua este desafio e o README: digite
   parte do nome, como `#01-prepar`, e escolha o arquivo na lista; se a lista não abrir, use
   `Ctrl+Espaço`. Deixe **um espaço** antes de cada novo `#`: sem ele, a lista responde "No suggestions".
7. Escolha o modo e as permissões do chat. Quando houver modo de perguntas ou de planejamento, use-o
   para pedir explicações antes de mudanças; os nomes e recursos dependem da configuração. [5] Na
   interface testada (VS Code 1.141), o seletor ofereceu **Agent** e agentes personalizados instalados por
   plugins. Para seguir o procedimento, selecione **Agent** e mantenha as permissões em **Manual**.
   Nesse ajuste, o Copilot pede a sua aprovação antes de
   executar comandos de terminal e outras ações não liberadas. [6] As edições comuns de arquivos do
   projeto são gravadas direto, sem pedir aprovação, e ficam para a sua revisão no diff (comparação
   entre versões dos arquivos). [7] Se um
   agente personalizado de outro projeto estiver selecionado, troque-o: as regras dele podem divergir das
   deste curso.

O projeto traz **instruções que o Copilot lê automaticamente**. O arquivo `.github\copilot-instructions.md`
vale para todo o projeto, e os arquivos em `.github\instructions` valem para tipos de arquivo: Python,
Bicep e dados. Elas aplicam regras do curso, como "nunca usar chaves de conta" e "simular antes de
alterar o Azure", sem que você as repita em cada pedido. [8] Para conferir se foram carregadas, abra a
engrenagem do chat (**Open Customizations**) e veja **Instructions**: devem aparecer quatro arquivos do
projeto, `copilot-instructions.md` e os três de `.github\instructions`.

> **Dica:** informe a tarefa, os arquivos relevantes, as restrições e o resultado que você espera.
> Se a interface do chat mostrar as
> referências usadas na resposta, confira se as instruções do projeto aparecem.

### Confiança na pasta e modo restrito

Ao abrir uma pasta nova, o VS Code pergunta se você **confia nos autores** dela. Sem essa confiança, a
pasta abre em **Restricted Mode** (modo restrito): o VS Code desativa ou limita os agentes de inteligência
artificial (IA), o terminal, as tarefas, a depuração, parte das configurações e as extensões. [9] O modo
restrito impede a execução automática de código desconhecido.

- **Confie** só quando a pasta vier do repositório oficial deste curso ou do seu instrutor. Em caso de
  dúvida, continue no modo restrito: você ainda lê os arquivos e a prévia do Markdown.
- A decisão fica gravada no seu VS Code e vale para a pasta aberta. Para revisá-la ou revogá-la, use
  **Workspaces: Manage Workspace Trust** na Paleta de Comandos.
- No VS Code 1.141, o chat do Copilot não lista modelos no modo restrito. Depois de confiar na pasta, as
  instruções do projeto podem aparecer em **Open Customizations** só após reabrir o VS Code; a Paleta de
  Comandos também oferece **Developer: Reload Window**.

### Prompt para o Copilot: entender antes de executar

Cole no chat, com os dois documentos anexados:

```text
Estou começando o laboratório Vareleira RAG e não sou desenvolvedor.
Leia o README e o L100, Desafio 01 anexados.
Explique o objetivo e liste os arquivos de infraestrutura, dados e scripts que o desafio usa.
Separe o que apenas lê do que altera o Azure.
Mostre onde encontro o terminal, a prévia Markdown e as alterações dos arquivos.
Não edite arquivos, instale ferramentas nem execute comandos.
Não peça credenciais ou documentos reais.
Ao final, faça três perguntas para conferir meu entendimento.
```

**Conferência:** a resposta deve citar o Bicep, o inventário e os scripts de carga e de verificação, e informar que criar a
infraestrutura e enviar os documentos alteram o Azure e dependem da sua decisão. Se a resposta sugerir chaves de
conta, acesso público ou a execução de comandos nesta etapa, peça a correção e lembre que a execução depende da sua decisão.

## Etapa 2: conferir o acesso ao Azure

**Objetivo:** identificar a assinatura de destino e conferir as suas permissões. Todos os comandos desta
etapa só leem informações.

### 2.1 Verificar as ferramentas

No terminal PowerShell, consulte as versões das ferramentas:

```powershell
git --version
az version
python --version
```

Se uma ferramenta não for encontrada, siga a instalação oficial e reabra o terminal. Não desative
controles corporativos para contornar a instalação.

### 2.2 Entrar no Azure e listar as assinaturas

Se ainda não estiver autenticado no Azure CLI, execute `az login` e conclua a autenticação no fluxo
oficial aberto pela ferramenta. Não cole senha, código de autenticação ou token no chat do Copilot.
Depois, consulte as assinaturas visíveis e a seleção padrão:

```powershell
az account list --query "[].{Nome:name,Id:id,Estado:state}" --output table
az account show --query "{Id:id,Estado:state,Padrao:isDefault}" --output json
```

### 2.3 Confirmar a assinatura de destino

Guarde em uma variável do terminal o identificador confirmado com o instrutor e consulte explicitamente
a assinatura destinada ao laboratório. Substitua `<ID-DA-SUA-ASSINATURA>` pelo valor real:

```powershell
$assinatura = "<ID-DA-SUA-ASSINATURA>"
az account show --subscription $assinatura --query "{Id:id,Estado:state,Padrao:isDefault}" --output json
```

**Resultado esperado:** o `Id` corresponde à assinatura combinada e `Estado` é `Enabled`. `Padrao` igual
a `false` é esperado quando a consulta indica uma assinatura diferente da padrão do Azure CLI. Se a
assinatura não aparecer ou o estado for diferente de `Enabled`, interrompa e confirme a conta e o acesso
com o responsável. [1]

### 2.4 Conferir permissões e políticas

Confira o que a sua conta pode fazer na assinatura. Os comandos abaixo só leem:

```powershell
$idObjeto = az ad signed-in-user show --query id --output tsv
az role assignment list --assignee $idObjeto --scope "/subscriptions/$assinatura" --include-inherited --query "[].{Papel:roleDefinitionName,Escopo:scope}" --output table
az policy assignment list --subscription $assinatura --query "[].{Politica:displayName,Modo:enforcementMode}" --output table
```

O primeiro comando obtém o seu **ID de objeto**, o identificador da sua conta no Entra ID. [10] O
segundo lista os seus papéis: *Owner* e *Contributor* permitem criar recursos, e a atribuição de papéis
exige *Owner*, *User Access Administrator* ou outro papel com permissão para escrever atribuições. [11] O
terceiro lista as políticas da organização: se alguma restringir regiões, acesso público ou chaves de
armazenamento, confirme com o responsável como ela afeta o laboratório. Uma lista vazia é um resultado
válido.

> **Atenção:** o identificador da assinatura e o seu ID de objeto identificam o seu ambiente. Publicados
> em arquivos versionados, em exemplos ou em pedidos de ajuda, eles expõem a estrutura da sua conta.
> Mantenha-os em variáveis do terminal e compartilhe só o trecho necessário, sem identificadores, tokens
> ou contas.

### Prompt para o Copilot: investigar sem conceder permissões

```text
A consulta de assinatura apresentou o erro abaixo, que revisei para remover
dados do ambiente. Explique causas possíveis e proponha verificações somente
de leitura. Separe problema de login, assinatura selecionada e autorização.
Não execute comandos, troque a assinatura padrão ou conceda papéis.
Se precisar de administrador, explique exatamente o que devo confirmar.

[Cole aqui apenas a mensagem de erro sanitizada.]
```

## Etapa 3: conhecer a base documental e o inventário

**Objetivo:** identificar os documentos que poderão responder às perguntas e entender como o laboratório
garante que só eles sejam enviados. Esta etapa é documental e dispensa programação.

O contexto Vareleira 0.1.0 descreve personagens e escopo; as coberturas, exclusões e franquias são
**conteúdo novo** deste laboratório: regras de seguro **sintéticas**, criadas para o exercício, sem
equivalente no contexto original. O mantenedor confirmou a aprovação desse conteúdo para o
exercício em 9 de outubro de 2026.

A base do L100 tem três documentos do Vareleira Lar, versão 1.0:

| Documento | Identificador | Para que serve |
| --- | --- | --- |
| [Condições Gerais](../../dados/l100/documentos/vareleira-lar-condicoes-gerais-v1.0.md) | VLAR-CG-1.0 | Regras do produto, em cláusulas numeradas |
| [Glossário](../../dados/l100/documentos/vareleira-lar-glossario-v1.0.md) | VLAR-GL-1.0 | Explica termos e remete às cláusulas |
| [Perguntas frequentes](../../dados/l100/documentos/vareleira-lar-faq-v1.0.md) | VLAR-FAQ-1.0 | Resume as regras para Atendimento e corretores, apontando a cláusula de origem |

Leia pelo menos as cláusulas 3 (coberturas adicionais), 4 (assistência 24 horas) e 6 (franquias) das
Condições Gerais. Versões conflitantes e documentos de contratação individual ficam para exercícios
posteriores.

O [inventário](../../dados/l100/inventario.json) é a **lista de permissão** da carga: só o que está nele
pode ser enviado. Cada entrada registra:

| Campo do inventário | O que registra | Por que importa |
| --- | --- | --- |
| `id` | Código estável do documento, como `VLAR-CG-1.0` | Localizar a fonte sem depender apenas do nome do arquivo |
| `produto` | `vareleira-lar` | Manter os produtos separados na recuperação |
| `tipo` | Condições gerais, glossário ou FAQ (*Frequently Asked Questions*, perguntas frequentes) | Diferenciar regra do produto de material explicativo |
| `versao` e `vigencia_ficticia` | Revisão e período ao qual o conteúdo se aplica | Distinguir mudança de regra de mudança de redação |
| `autoridade_narrativa` | Papel responsável na história, aqui Teresa Moura | Dizer quem responde pelas regras dentro da ficção |
| `revisao_real` | Situação da aprovação do conteúdo, hoje `aprovada` | Distinguir a validação fictícia da aprovação pelo mantenedor |
| `classificacao_acesso` | Público interno do piloto e restrições previstas | Preparar controles de acesso dos níveis posteriores |
| `origem` e `licenca` | Conteúdo sintético criado para o laboratório, sob a licença Creative Commons Atribuição 4.0 (CC BY 4.0) | Permitir atribuição e reutilização |
| `arquivo`, `blob`, `tamanho_bytes` e `sha256` | Caminho local, nome no Azure, tamanho e hash | Conferir se a cópia enviada corresponde ao arquivo revisado |

Um **hash** é um resumo calculado do conteúdo, usado para comparar o arquivo de origem com a cópia
enviada. Os scripts calculam esse resumo com os mesmos finais de linha nos dois arquivos.
A correção das regras de seguro, a autorização de uso e a vigência dependem da revisão do conteúdo e
da autoridade da fonte.

Os scripts protegem a carga de quatro formas:

1. enviam somente arquivos listados no inventário e recusam arquivos a mais na pasta;
2. conferem tamanho e hash antes de qualquer acesso ao Azure;
3. calculam o hash sobre o texto com finais de linha normalizados, para que o mesmo documento tenha o
   mesmo hash no Windows e em outros sistemas;
4. avisam enquanto houver revisão de conteúdo pendente.

> **Para guardar na memória: FAVA.** Antes de aceitar uma fonte, confira **F**onte, **A**utoridade,
> **V**ersão e **A**cesso. Mnemônico criado para este curso.

**Atividade 1:** a FAQ descreve a cobertura de danos elétricos. Identifique qual documento define se uma
contratação individual tem essa cobertura e qual é o papel da FAQ. Depois identifique quem, na narrativa,
responde pelas regras do produto e quem representa o Atendimento.

**Conferência:** a cobertura de uma contratação individual consta dos documentos de contratação
individual, fora do escopo do piloto; as Condições Gerais definem as regras do produto, e a FAQ as resume
para o Atendimento. Teresa Moura é a autoridade técnica, e Beatriz Torres representa o Atendimento.

**Atividade 2:** localize, nas Condições Gerais, a franquia de danos elétricos e o que a FAQ afirma sobre
ela. Os dois textos concordam?

**Conferência:** a franquia está na cláusula 6.3 (10% do prejuízo, com mínimo de R$ 300,00), e a FAQ a
repete com a referência de origem. Se achar uma divergência, registre-a: ela pode ser um erro do
material, a ser corrigido na revisão.

### Prompt para o Copilot: revisar a base sem editá-la

Anexe o inventário e os três documentos:

```text
Leia o inventário e os três documentos sintéticos do Vareleira Lar anexados.
Compare Condições Gerais, glossário e perguntas frequentes e liste, em uma tabela:
1. referências de cláusula que não existem;
2. valores, prazos ou franquias que diferem entre os documentos;
3. termos usados sem definição no glossário.
Indique o documento e a cláusula de cada achado. Não edite arquivos nem execute comandos.
Informe explicitamente as categorias em que não encontrar problemas.
```

**Conferência:** confira cada achado no arquivo antes de aceitá-lo. O Copilot pode apontar problemas que
não existem; a revisão final é humana.

## Etapa 4: criar a infraestrutura com Bicep

**[altera o Azure]** nos comandos `az group create` e `az deployment group create`.

**Objetivo:** criar, em um grupo de recursos exclusivo do laboratório, uma conta de armazenamento e um
contêiner para os documentos, e conceder a você acesso de dados restrito a esse contêiner.

**Infraestrutura como código (IaC, *Infrastructure as Code*)** é a prática de descrever recursos em arquivos versionados, e o
Bicep é a linguagem do Azure para essa prática. O arquivo [infra\main.bicep](../../infra/main.bicep)
descreve os recursos, e [infra\levels\l100.bicepparam](../../infra/levels/l100.bicepparam) fornece as
escolhas do nível, sem fixar identificadores do seu ambiente. [12][13]

### Decisões de configuração do Bicep

| Decisão do Bicep | O que faz | Por que importa |
| --- | --- | --- |
| Sem acesso anônimo (`allowBlobPublicAccess: false`, contêiner `publicAccess: None`) | Ninguém lê um documento sem credencial | Evita expor documentos por engano [14] |
| Sem chaves de conta (`allowSharedKeyAccess: false`) | O acesso aos dados usa a identidade do Entra ID | Evita distribuir uma credencial compartilhada com acesso amplo à conta [15] |
| Entra ID como padrão (`defaultToOAuthAuthentication: true`) | Ferramentas passam a usar a sua identidade | Mantém o acesso rastreável por pessoa |
| TLS (*Transport Layer Security*) 1.2 e somente HTTPS (HTTP, *Hypertext Transfer Protocol*, com criptografia) | Comunicação criptografada em trânsito | Protege tokens e conteúdo durante a transmissão |
| Exclusão reversível por 7 dias | Blobs e contêineres apagados ou sobrescritos ficam recuperáveis | Reduz o dano de um engano [16] |
| Papel de dados só no contêiner | `Storage Blob Data Contributor` apenas em `base-documental` | Aplica o menor privilégio: o papel vale só no contêiner |
| Endereço público, mas autenticado | Qualquer pessoa alcança o endereço, só quem tem papel lê | Dispensa a configuração de rede privada neste nível; redes privadas ficam para outro nível |
| Redundância local (LRS, *locally redundant storage*) | Cópias dentro de um único local físico da região | Opção de menor custo; os documentos sintéticos podem ser reenviados a partir do repositório |

### Prompt para o Copilot: entender o Bicep

```text
Leia infra/main.bicep e infra/levels/l100.bicepparam anexados.
Explique, para quem não programa, cada recurso criado e cada configuração de segurança.
Diga o que o what-if mostrará e o que acontece se a variável VARELEIRA_ID_OBJETO_CARGA estiver vazia.
Aponte qualquer coisa que pareça insegura ou que eu deva conferir antes de implantar.
Não edite arquivos nem execute comandos.
```

### 4.1 Criar o grupo de recursos

Use o terminal da Etapa 2, onde `$assinatura` já está definida; em um terminal novo, defina-a de novo.
Substitua `<REGIAO>` por uma região permitida pela sua organização, por exemplo `brazilsouth`. As regiões
`brazilsouth` e `eastus2` foram validadas. Se a região recusar os recursos, consulte
`RequestDisallowedByAzure` em [Solução de problemas](#solução-de-problemas).

```powershell
$grupo = "rg-vareleira-rag-l100"
$regiao = "<REGIAO>"
az group create --subscription $assinatura --name $grupo --location $regiao --tags laboratorio=vareleira-rag nivel=L100
```

**Resultado esperado:** um JSON (texto estruturado em pares nome-valor) com `provisioningState` igual a
`Succeeded`, a região escolhida e as duas etiquetas.

Se o instrutor entregou um grupo de recursos vazio e exclusivo, use o nome dele em `$grupo` e omita o
`az group create`. As etiquetas identificam o grupo na limpeza. [17]

### 4.2 Informar quem envia os documentos

Defina o ID de objeto da conta que enviará os documentos. A variável vale só nesta sessão do terminal, e o
arquivo de parâmetros a lê: [18]

```powershell
$env:VARELEIRA_ID_OBJETO_CARGA = az ad signed-in-user show --query id --output tsv
```

O comando não imprime nada quando conclui com sucesso.

### 4.3 Simular a implantação (what-if)

O **what-if** mostra o que seria criado, sem criar nada: [19]

```powershell
az deployment group what-if --subscription $assinatura --resource-group $grupo --name vareleira-rag-l100 --parameters infra\levels\l100.bicepparam
```

**Resultado esperado:** quatro recursos marcados com `+ Create`: `storageAccounts`, `blobServices`,
`containers` e `roleAssignments`, e a linha final `Resource changes: 4 to create.` A CLI também avisa que
a previsão pode ter falsos positivos (ruído). Se aparecerem só três, com `3 to create` e sem
`roleAssignments`, a variável não foi lida: repita o comando da seção 4.2. Se aparecer algo que você não
esperava, interrompa e investigue antes de implantar.

### 4.4 Implantar

Execute a implantação e, em seguida, remova a variável:

```powershell
az deployment group create --subscription $assinatura --resource-group $grupo --name vareleira-rag-l100 --parameters infra\levels\l100.bicepparam
Remove-Item Env:\VARELEIRA_ID_OBJETO_CARGA
```

**Tempo de referência:** de 35 a 40 segundos, medidos em `brazilsouth`. A saída em JSON traz
`provisioningState` com o valor `Succeeded` e as saídas do Bicep (`outputs`): `nomeConta`,
`nomeContainer`, `enderecoBlob` e `papelDeDadosAtribuido`.

### 4.5 Registrar o nome da conta

O nome da conta é gerado a partir do identificador do grupo de recursos e permanece estável para esse
grupo. Guarde-o em uma variável:

```powershell
$conta = az deployment group show --subscription $assinatura --resource-group $grupo --name vareleira-rag-l100 --query properties.outputs.nomeConta.value --output tsv
$conta
```

### Atribuir o papel de dados por um administrador

Quem implanta precisa de permissão para criar atribuições de papel. Sem ela, a implantação falha ao
criar `roleAssignments`. Remova a variável (`Remove-Item Env:\VARELEIRA_ID_OBJETO_CARGA`), implante de
novo e peça a um administrador o papel **Storage Blob Data Contributor** no contêiner `base-documental`,
para o seu usuário. [4]

Com o ID de objeto que você obteve na Etapa 2 e com `$assinatura`, `$grupo` e `$conta` definidos, o
administrador executa **[altera o Azure]**:

```powershell
$escopo = az storage account show --subscription $assinatura --resource-group $grupo --name $conta --query id --output tsv
az role assignment create --assignee-object-id "<ID-DE-OBJETO-DE-QUEM-VAI-ENVIAR>" --assignee-principal-type User --role "Storage Blob Data Contributor" --scope "$escopo/blobServices/default/containers/base-documental"
```

Sem a variável, a implantação cria três recursos e a saída `papelDeDadosAtribuido` é `false`. Depois da
concessão, o papel pode levar até 10 minutos para valer [11] (cerca de 100 segundos na validação); até
lá, a simulação informa falta de permissão de dados.

### 4.6 Conferir a infraestrutura

```powershell
az resource list --subscription $assinatura --resource-group $grupo --query "[].{Nome:name,Tipo:type}" --output table
az storage account show --subscription $assinatura --resource-group $grupo --name $conta --query "{AcessoPublicoABlobs:allowBlobPublicAccess,ChavesDeConta:allowSharedKeyAccess,TlsMinimo:minimumTlsVersion,SomenteHttps:enableHttpsTrafficOnly}" --output json
$escopo = az storage account show --subscription $assinatura --resource-group $grupo --name $conta --query id --output tsv
az role assignment list --scope "$escopo/blobServices/default/containers/base-documental" --query "[].{Papel:roleDefinitionName,Tipo:principalType}" --output table
```

**Resultado esperado:** um único recurso no grupo, a conta de armazenamento; `AcessoPublicoABlobs` e
`ChavesDeConta` com `false`, `TlsMinimo` com `TLS1_2` e `SomenteHttps` com `true`; e o papel
`Storage Blob Data Contributor` para o tipo `User` no contêiner. Um papel novo pode levar até 10 minutos
para valer nos dados. [11]

> **Boa prática:** reimplantar o mesmo Bicep é idempotente: o arquivo descreve o estado desejado, e o
> Azure aplica apenas a diferença em relação ao estado atual. Na reimplantação, o `what-if` pode listar
> `Modify` para propriedades padrão do serviço que o arquivo não menciona; esse comportamento é uma
> limitação conhecida da previsão (ruído). [19] Confira se cada diferença corresponde a uma propriedade
> preenchida pelo serviço ou a uma alteração que você pediu, antes de decidir.

## Etapa 5: enviar e conferir os documentos

**[altera o Azure]** nos comandos com `--executar` e no experimento opcional de divergência.

**Objetivo:** guardar no contêiner somente os documentos do inventário (o script cria apenas blobs ausentes
e para diante de divergências) e verificar que o conteúdo enviado corresponde ao inventário.

### 5.1 Preparar o Python

Um **ambiente virtual** é uma pasta com um Python e pacotes exclusivos deste projeto, isolados do restante
da máquina. Crie e ative o ambiente e instale as dependências, que têm as versões fixadas: [20]

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements\l100.txt
```

O prompt passa a mostrar `(.venv)`. No VS Code, use **Python: Select Interpreter** na Paleta de Comandos e
escolha o Python da pasta `.venv`, marcado como **Recommended**. [21] A partir daí, os terminais novos
ativam o ambiente automaticamente: o prompt já começa com `(.venv)`, sem repetir `Activate.ps1`. Para
ativar o ambiente, a extensão usa uma política de execução restrita àquele terminal, sem alterar a
máquina. Se ainda não houver ambiente, a mesma lista oferece **Create Virtual Environment...**, equivalente
a **Python: Create Environment**. [20]

Se o PowerShell bloquear o script de ativação por política de execução, mantenha a política da máquina e
substitua `python` por `.\.venv\Scripts\python.exe` nos comandos seguintes.

Os scripts autenticam com a identidade do Azure CLI (a do `az login`); nenhuma chave é usada. [22] Se a
sua conta tiver mais de um tenant, acrescente `--tenant-id <ID-DO-TENANT>` aos comandos.

### 5.2 Simular a carga

A **simulação** é o padrão: o script valida o inventário, lê o contêiner e mostra o plano, mas não envia
nada. Ela também testa a sua permissão de leitura.

```powershell
python scripts\carregar_documentos.py --conta $conta
```

**Resultado esperado:**

```text
Modo: SIMULAÇÃO (nenhuma alteração será feita)
Destino: conta '<nome-da-conta>', contêiner 'base-documental'
Inventário: 3 documento(s) conferidos por tamanho e hash.
Plano:
  [criar     ] VLAR-CG-1.0    vareleira-lar/condicoes-gerais-v1.0.md
  [criar     ] VLAR-GL-1.0    vareleira-lar/glossario-v1.0.md
  [criar     ] VLAR-FAQ-1.0   vareleira-lar/faq-v1.0.md
Simulação concluída. Para enviar, repita o comando com --executar.
```

O inventário atual tem os três documentos aprovados, por isso não mostra aviso de revisão.
O aviso continua sendo esperado para documentos novos ainda pendentes. Se aparecer `[ERRO]`,
consulte [Solução de problemas](#solução-de-problemas).

### 5.3 Enviar os documentos

```powershell
python scripts\carregar_documentos.py --conta $conta --executar
```

O script cria cada blob somente se ele **ainda não existir** e termina com `Concluído: 3 criado(s), 0
trocado(s), 0 já igual(is).`

### 5.4 Conferir a carga

```powershell
python scripts\verificar_documentos.py --conta $conta
```

**Resultado esperado:**

```text
[OK   ] Quantidade e identificadores: 3 blob(s) no contêiner e 3 no inventário
[OK   ] VLAR-CG-1.0: conteúdo, tipo e metadados conferem com o inventário
[OK   ] VLAR-GL-1.0: conteúdo, tipo e metadados conferem com o inventário
[OK   ] VLAR-FAQ-1.0: conteúdo, tipo e metadados conferem com o inventário
[OK   ] Leitura anônima negada: 4 endereço(s) testados sem credenciais; resposta: HTTP 409
Verificação aprovada.
```

A verificação **só lê**. Ela compara o conteúdo baixado com o hash do inventário, procura blobs que não
constam do inventário e pede cada endereço **sem credencial**. Uma resposta de sucesso (HTTP 2xx) indica
falha de configuração; o resultado esperado é uma recusa, com código 409, 404, 403 ou 401.

### 5.5 Reexecutar a carga

Execute de novo `python scripts\carregar_documentos.py --conta $conta --executar`. O plano mostra
`[igual]` nos três documentos, e o script não envia nada. Esse comportamento é a **reexecução previsível**
(idempotência): repetir o comando não duplica nem altera o que já está correto.

| Código de saída | Significa |
| --- | --- |
| 0 | Concluído sem problemas |
| 1 | Argumentos, inventário ou arquivos locais inválidos |
| 2 | Falha de autenticação, permissão, rede ou serviço do Azure |
| 3 | O conteúdo do Azure difere do inventário |
| 4 | Defeito do script; execute com `--detalhes` e peça ajuda sem dados do seu ambiente |

No PowerShell, `$LASTEXITCODE` mostra o código do último programa executado.

### Experimento opcional: provocar uma divergência

Este experimento mostra a parada do script diante de uma divergência. Ele altera um blob **seu**, dentro
do grupo de recursos do laboratório, e depois o restaura. O parâmetro `--data` está em pré-visualização na Azure CLI, que
exibe um aviso.

```powershell
az storage blob upload --account-name $conta --container-name base-documental --name vareleira-lar/faq-v1.0.md --data "conteudo alterado fora do script" --overwrite true --auth-mode login
python scripts\carregar_documentos.py --conta $conta --executar
python scripts\verificar_documentos.py --conta $conta
```

**Resultado esperado:** o carregador mostra `[divergente]` e para com `[PARADA]` e código 3, **sem alterar
nenhum blob**, inclusive os que estavam corretos. O verificador reprova o documento. Para restaurar de
propósito:

```powershell
python scripts\carregar_documentos.py --conta $conta --executar --substituir-divergentes
python scripts\verificar_documentos.py --conta $conta
```

O script troca o blob usando o **ETag**, a marca de versão dele: se alguém mudar o blob entre a simulação
e o envio, a troca é recusada. As versões anteriores continuam existindo por 7 dias como instantâneos
apagados, graças à exclusão reversível. Para vê-las:

```powershell
az storage blob list --account-name $conta --container-name base-documental --include ds --auth-mode login --query "[?name=='vareleira-lar/faq-v1.0.md'].{Nome:name,Instantaneo:snapshot,Apagado:deleted,Tamanho:properties.contentLength}" --output table
```

**Resultado esperado:** três linhas para `faq-v1.0.md`: duas com `Apagado` verdadeiro e `Instantaneo`
preenchido (a versão original, com 5452 bytes, e a divergente, com 32 bytes) e a linha do blob atual, sem
instantâneo, com 5452 bytes.

O procedimento de recuperação das versões está descrito na documentação oficial. [16]

## Como pedir uma mudança ao Copilot no VS Code

Para evoluir o projeto, peça a mudança ao Copilot e **revise o resultado**; escrever o código não é
necessário. O método abaixo vale para qualquer pedido de implementação, e as instruções do projeto
aplicam as regras do curso sem que você as repita. [5][8]

1. **Comece com o projeto limpo.** Abra **Source Control** e confira que não há alterações misturadas;
   se houver, guarde-as antes.
2. **Dê o contexto.** Anexe os arquivos relevantes, por exemplo `scripts\lab_comum.py`, o inventário e
   este desafio.
3. **Peça um plano primeiro.** Use o modo de perguntas ou de planejamento, quando disponível, e só então
   permita edições. Peça arquivos, funções e testes antes de qualquer mudança. Sem esses modos (caso do
   VS Code 1.141), escreva no pedido: "antes de editar, proponha o plano".
4. **Delimite.** Informe os arquivos e os comandos permitidos e que o Copilot **não deve acessar o
   Azure**.
5. **Revise o diff.** Em **Source Control**, abra a comparação de cada arquivo e leia por inteiro o
   conteúdo dos arquivos novos. Peça ao Copilot que explique o que você não entendeu, sem modificar nada.
   As edições já estão gravadas nesse ponto. Para descartar o pedido, apague os arquivos novos e
   descarte as mudanças dos arquivos alterados em **Source Control**, depois de conferir o que será
   perdido. O ponto de restauração do chat [7] tem alcance limitado: no VS Code 1.141, o botão
   **Clears the chat and undoes all changes** pede confirmação, limpa a conversa e **mantém os arquivos
   que o agente criou**; use **Source Control** para desfazê-los.
6. **Verifique com comandos.** Execute os comandos combinados no pedido e leia cada pedido de aprovação,
   como descrito a seguir. A confirmação de conclusão no chat é o relato do agente; a evidência é o
   resultado dos comandos e dos testes.

### Aprovar os comandos do agente

Com as **permissões manuais**, o agente para antes de cada comando de terminal e mostra o texto exato.
Leia-o antes de decidir: o que será executado, com qual Python e se estava no pedido. O botão principal e o
menu ao lado dele oferecem estas escolhas; os nomes estão em inglês, como na interface do VS Code 1.141. [6]

| Escolha | Efeito | Neste curso |
| --- | --- | --- |
| **Allow Once**, no menu ao lado do botão principal | Libera só este comando | É o padrão |
| **Allow in this Session**, o botão azul principal | Libera para o resto da conversa | Evite |
| **Allow ... in this Workspace** e **Always Allow ...** | Gravam uma regra permanente; algumas valem para qualquer comando que comece com o mesmo programa | Não use |
| **Skip** | Recusa o comando; o agente segue sem ele | Use para o que fugir do combinado |

> **Atenção:** o botão azul grande libera o comando para o resto da conversa. Para liberar só um comando,
> abra o menu ao lado dele e escolha **Allow Once**.

Um comando que não estava no pedido exige interrupção e revisão. Se ele só consulta o ambiente, como
listar pastas ou os pacotes do Python, liberar uma vez é razoável. Se ele instala pacotes (`pip install`),
usa o `az`, apaga arquivos ou envia algo (`git push`), use **Skip** e refaça o pedido com limites mais
claros. Para revisar regras já gravadas, abra **Configure Auto Approve...** no mesmo menu.

### Exemplo: um script novo, local e somente leitura

Cole com os arquivos anexados:

```text
Leia o README, o L100 Desafio 01 e scripts/lab_comum.py anexados.
Quero um script novo, local e somente leitura: scripts/listar_documentos.py.
Ele deve listar os documentos do inventário (identificador, título, versão e situação da
revisão real) em uma tabela simples e terminar com a contagem de documentos com revisão pendente.
Antes de editar, proponha o plano: arquivos, funções e como vai testar.
Siga as instruções do projeto: reaproveite lab_comum, escreva mensagens em pt-BR e use unittest.
Não acesse o Azure, não instale pacotes novos e execute apenas
python scripts\listar_documentos.py e python -m unittest discover -s tests.
```

**Conferência:** o diff deve acrescentar o script e um teste, reaproveitar `lab_comum`, omitir
credenciais e identificadores do seu ambiente, e os testes devem passar. Peça ao Copilot que explique cada
função com palavras simples antes de aceitar.

**O que revisar no código proposto pelo Copilot:**

- **Interpretador.** O terminal do agente pode usar o Python do sistema em vez do ambiente virtual da
  Etapa 5 e falhar com `ModuleNotFoundError: No module named 'azure'`. Inclua no pedido: "Use o Python do
  ambiente virtual, `.\.venv\Scripts\python.exe`".
- **Comandos fora do combinado.** Leia cada comando e confira se o executável e os argumentos estão
  entre os autorizados. Revise o pedido antes de liberar uma execução diferente.
- **Testes novos.** Os testes escritos pelo agente também exigem revisão e podem falhar na primeira
  execução; peça a correção e repita a suíte.
- **Critério de revisão.** Reaproveite `lab_comum.aviso_de_revisao`: o projeto considera pendente todo
  documento cujo campo `revisao_real` difere de `aprovada`. Um script que conte apenas o valor `pendente`
  omite outros estados ainda sem aprovação.

As execuções desse exemplo no chat estão no
[registro do pedido de mudança](../../docs/validacao/l100-01-preparar-ambiente.md#pedido-de-mudança-no-chat-observações).

> **Dica:** quando o resultado não atender, refine em vez de recomeçar: descreva a mudança em um pedido
> pequeno, como "mostre também o tipo documental" ou "troque a tabela por uma lista"; depois confira no
> diff que o restante permaneceu igual. Outros pedidos para praticar: "explique cada função de `lab_comum.py` para quem
> não programa" e "gere um roteiro de revisão das Condições Gerais para o mantenedor".

**Modo construtor (opcional).** Para ver como o Copilot resolveria o desafio, peça um plano em uma
pasta separada e compare o resultado com os arquivos deste projeto pelo diff:

```text
Leia o L100, Desafio 01, o README e as instruções do projeto.
Proponha, sem editar, como armazenar documentos sintéticos em Blob Storage com Bicep e Python.
Receba assinatura e destino explicitamente. Use acesso por Entra ID, sem chaves e sem leitura anônima.
Defina o que acontece ao reenviar um arquivo e ao encontrar divergência; não sobrescreva em silêncio.
Não provisione recursos, atribua papéis, envie dados ou exclua arquivos.
```

Qualquer ação que altere o Azure continua dependendo da sua decisão.

## Conferência do resultado

| Verificação | Como conferir | Evidência esperada |
| --- | --- | --- |
| Projeto aberto corretamente | Explorador e prévia Markdown no VS Code | README e este desafio visíveis; revisão identificada |
| Uso orientado do Copilot | Resposta ao primeiro prompt | Cita os artefatos reais e separa o que altera o Azure |
| Assinatura identificada | `az account show --subscription` | `Id` combinado e estado `Enabled`; as permissões são conferidas na linha seguinte |
| Permissões conferidas | `az role assignment list` | Papel que permite criar recursos; papel de dados após a Etapa 4 |
| Fontes compreendidas | Atividades da Etapa 3 | Respostas revisadas, com a divergência (se houver) registrada |
| Infraestrutura criada | `az resource list` no grupo | Só a conta de armazenamento, no grupo exclusivo |
| Segurança da conta | `az storage account show` com a consulta da Etapa 4 | Acesso público e chaves `false`, TLS 1.2, somente HTTPS |
| Conteúdo carregado | `verificar_documentos.py` | Identificadores, quantidade, hashes, tipo e metadados conferem |
| Acesso conferido | `verificar_documentos.py` | Leitura com a sua identidade funciona; leitura anônima negada |
| Reexecução previsível | `carregar_documentos.py --executar` de novo | Três `[igual]` e nenhum envio; a divergência interrompe o script |

Antes de encerrar, registre em local privado o grupo de recursos, o nome da conta e a decisão de manter
ou remover os recursos. Ao compartilhar evidências, remova das saídas do terminal os identificadores do
ambiente, os nomes de conta e as contas de usuário.

## Solução de problemas

| Sintoma | O que conferir | O que evitar |
| --- | --- | --- |
| `az`, `git` ou `python` não é reconhecido | Instalação e abertura de um novo terminal | Instalar executáveis de origem desconhecida |
| A CLI não encontra o Bicep | Execute `az bicep install` e repita | Baixar binários de fontes desconhecidas |
| Assinatura não aparece | Conta, tenant e acesso concedido pelo responsável | Usar outra assinatura só para avançar |
| `Padrao` é `false` | Se o ID consultado explicitamente é o correto | Alterar a seleção global sem necessidade |
| `AuthorizationFailed` ao criar o grupo ou implantar | Seu papel no escopo; peça *Contributor* no grupo de recursos | Pedir acesso de proprietário da assinatura só para simplificar |
| Falha ao criar `roleAssignments` | Você precisa poder atribuir papéis; veja "Atribuir o papel de dados por um administrador" | Conceder papéis amplos para contornar |
| `RequestDisallowedByPolicy` | A política da organização citada no erro e a região escolhida | Desativar a política ou afrouxar as proteções do Bicep para passar |
| `RequestDisallowedByAzure` ("região sem novos clientes") | Escolha outra região permitida; exclua o grupo vazio e crie-o de novo | Insistir na mesma região ou trocar de assinatura sem autorização |
| `[ERRO]` de permissão de dados (código 2) | Papel no contêiner, mensagem completa, nome do contêiner e espera de alguns minutos [11] | Tornar o contêiner público ou usar uma chave de conta |
| `[ERRO]` "contêiner ... não existe" ou "Conta ... não encontrado" (código 2) | Nome da conta (`$conta`), nome do contêiner (`base-documental`) e se a implantação terminou | Criar outro contêiner só para o erro desaparecer |
| `[ERRO]` "recusou a autenticação ou a autorização (AuthorizationFailure)" (código 2) | Regras de rede da conta, VPN (rede privada virtual) e `az login` | Abrir a conta para todas as redes só para contornar |
| `[ERRO]` "falta informar o valor" ou "faltam argumentos obrigatórios: --conta" (código 1) | `$conta` vazia: repita a consulta do nome da conta, na Etapa 4 | Inventar o nome da conta |
| "Bibliotecas do Azure não encontradas" | Ambiente virtual ativo e `pip install -r requirements\l100.txt` | Instalar pacotes sugeridos aleatoriamente |
| `No module named 'azure'` quando o **agente** executa os testes | O terminal do agente usou outro Python; peça "use `.\.venv\Scripts\python.exe`" e libere só esse comando | Pedir ao agente que instale pacotes no Python do sistema |
| Acentos aparecem como `�` na saída que o agente mostra | A saída capturada precisa sair em UTF-8 (codificação que preserva acentos): `lab_comum.configurar_saida()` já faz isso; em outro script, peça para reaproveitá-la ou para executar com `python -X utf8` | Trocar os textos por versões sem acento |
| Erro de autenticação do Azure CLI (código 2) | `az login`, `az account show` e, se necessário, `--tenant-id` | Colar token no chat ou em arquivos |
| "o conteúdo é diferente do inventário revisado" (código 1) | Se você editou o documento; restaure-o com Git ou, se a mudança for revisada, atualize o inventário | Editar o hash manualmente sem revisar o conteúdo |
| `[PARADA]` com `[divergente]` (código 3) | Quem alterou o blob e por quê | Usar `--substituir-divergentes` sem investigar |
| `FALHA` em "Leitura anônima negada" | Configuração da conta e do contêiner; não siga até corrigir | Ignorar a falha ou liberar o acesso público |
| Python não aparece no editor | Interpretador instalado e **Python: Select Interpreter** | Confundir a extensão com a instalação do Python |
| Copilot não vê o desafio | Pasta aberta, revisão recebida e arquivo anexado | Supor que ele conhece arquivos fora do contexto |
| VS Code em **Restricted Mode**: Copilot sem modelos, terminal bloqueado ou instruções ausentes | Se a pasta é a oficial, confie nela ("Confiança na pasta e modo restrito") e reabra o VS Code | Confiar em uma pasta desconhecida só para destravar |
| Copilot propõe chave de conta, `--yes` ou conceder papel | As instruções do projeto; refaça o pedido com os limites | Executar a proposta como se fosse material validado |

Se precisar de ajuda, consulte os [canais e limites do suporte](../../SUPPORT.md). Não conceda papéis, altere políticas
corporativas ou desative controles como tentativa de diagnóstico.

## Custos, pausa e limpeza

O uso do Copilot segue o plano da sua conta e as regras de consumo dele, separadamente da assinatura
Azure. [23] A cobrança do Azure vem dos recursos criados neste desafio.

**O que gera custo:** o Blob Storage cobra por capacidade armazenada (gigabyte por mês), por operações de
leitura e gravação e pelas versões mantidas na exclusão reversível. O volume deste desafio é de três
documentos (cerca de 21 KB) e algumas dezenas de operações. O custo não foi medido na validação, e os preços
variam por região, redundância e data. Consulte os
[preços atuais do Blob Storage](https://azure.microsoft.com/en-us/pricing/details/storage/blobs/) para a
sua região, calcule o custo na [calculadora de preços](https://azure.microsoft.com/en-us/pricing/calculator/)
e acompanhe o consumo no Cost Management. [24]

Os orçamentos do Azure Cost Management enviam alertas, e o consumo continua até que os recursos sejam
removidos. Fechar o VS Code ou o terminal não remove recursos nem encerra cobranças. [25]

**Pausa e continuidade.** O armazenamento é reutilizado nos próximos desafios; para continuar, **mantenha**
os recursos. O [Desafio 02](02-indexar-documentos.md) parte dos documentos que já estão nele, no mesmo
grupo de recursos, para dividi-los em trechos, calcular embeddings e indexá-los por código.

### Limpeza **[altera o Azure]**

Faça a limpeza ao encerrar o laboratório ou antes de uma pausa longa. Confira o alvo antes de apagar:

```powershell
az group show --subscription $assinatura --name $grupo --query "{Nome:name,Etiquetas:tags}" --output json
az resource list --subscription $assinatura --resource-group $grupo --query "[].{Nome:name,Tipo:type}" --output table
```

Prossiga somente se as etiquetas mostrarem `laboratorio` com o valor `vareleira-rag` e a lista tiver
apenas o que você criou neste desafio. Então exclua **o grupo de recursos do laboratório**; o comando pede confirmação:

```powershell
az group delete --subscription $assinatura --name $grupo
az group exists --subscription $assinatura --name $grupo
```

O último comando deve responder `false`. A exclusão do grupo apaga tudo o que há nele, inclusive os
documentos e as versões da exclusão reversível. [17]

> **Atenção:** nunca exclua um grupo compartilhado ou que já existia antes do laboratório. Nesse caso,
> exclua somente a conta criada aqui, depois de conferir o nome e a etiqueta `laboratorio=vareleira-rag`:

```powershell
az storage account show --subscription $assinatura --resource-group $grupo --name $conta --query tags --output json
az storage account delete --subscription $assinatura --resource-group $grupo --name $conta
```

A CLI pede confirmação; a opção `--yes` a dispensa e só deve ser usada por quem tem certeza do alvo.
Resultado esperado: o comando remove só a conta, o grupo e os demais recursos permanecem, e
`verificar_documentos.py` passa a responder que a conta não existe.

## Situação da validação

Data de referência: 9 de outubro de 2026. O registro detalhado, com a matriz de testes, as medições e as
correções, está em [docs\validacao\l100-01-preparar-ambiente.md](../../docs/validacao/l100-01-preparar-ambiente.md).

**Versões testadas:** Windows, Python 3.12.10, Azure CLI 2.89.0, Bicep 0.48.1, VS Code 1.141,
`azure-identity` 1.26.0 e `azure-storage-blob` 12.31.0.

| Item | Situação | Detalhe |
| --- | --- | --- |
| Comandos das Etapas 2 a 5, experimento de divergência e limpeza | Concluído | Executados em uma assinatura de teste, em grupos de recursos exclusivos e excluídos em seguida; PowerShell 7.6 em `brazilsouth` e Windows PowerShell 5.1 em `eastus2` |
| Scripts, Bicep e testes automáticos (sem Azure) | Concluído | Testes aprovados; `az bicep lint`, `build` e `format` sem avisos |
| Links, âncoras, URLs e referências do guia | Concluído | Nenhum link ou âncora inválido |
| Passos no VS Code: confiança na pasta, instruções do projeto, prévia, interpretador, anexos e pedido de mudança | Concluído | VS Code 1.141, modo **Agent**, permissões manuais |
| Aprovação do conteúdo dos documentos sintéticos | Confirmada | Pelo mantenedor, em 9 de outubro de 2026; registro no inventário |
| Aprovação do texto e dos resultados | Confirmada | Pelo mantenedor, em 9 de outubro de 2026; não representa novos testes |
| Outros ambientes: macOS, Linux, WSL (Windows Subsystem for Linux), Python diferente do 3.12, VS Code em português e em outras versões | Pendente | Executar os comandos do guia nesses ambientes e registrar as diferenças |
| Contas e regiões: assinaturas gratuitas ou estudantis, políticas restritivas, papéis menores que *Owner* e regiões além de `brazilsouth` e `eastus2` | Pendente | Repetir a Etapa 4 em cada cenário. Em `westeurope`, a implantação foi recusada com `RequestDisallowedByAzure` (região sem novos clientes) |
| Interações com o Copilot: prompts das Etapas 2 a 4, modo construtor e outros modelos no pedido de mudança | Pendente | Executar no VS Code e registrar as respostas |
| Custo e exclusão interativa | Pendente | Medir o custo no Cost Management após uma execução completa e executar `az group delete` sem `--yes` |

**Autoria.** Texto e código produzidos com apoio de IA (Claude Sonnet 5.5, no GitHub Copilot CLI); o Astra,
modelo preferido do mantenedor para a documentação, não estava disponível. Revisão editorial por
GPT-6.1 Sol, em 9 de outubro de 2026. Os modelos de autoria e revisão são
independentes do modelo que você escolhe no Copilot e dos modelos usados pela aplicação no Azure.

## Glossário

| Termo | Significado no exercício |
| --- | --- |
| Assinatura Azure | Escopo que organiza o uso e a cobrança dos recursos |
| Tenant | Diretório de identidades do Microsoft Entra ID associado ao acesso |
| Região | Local geográfico dos datacenters em que os recursos são criados |
| Grupo de recursos | Agrupamento de recursos Azure administrados em conjunto |
| Etiquetas (tags) | Pares nome=valor, como `laboratorio=vareleira-rag`, que identificam recursos |
| Microsoft Entra ID | Serviço de identidade usado para autenticação e autorização |
| Autenticação | Verificação de quem está acessando |
| Autorização | Decisão sobre o que a identidade autenticada pode fazer |
| ID de objeto | Identificador da sua conta, ou de um grupo ou aplicação, no Entra ID |
| RBAC | Controle de acesso baseado em papéis, do inglês *Role-Based Access Control* |
| Papel de gerenciamento e papel de dados | O primeiro permite administrar recursos, como criar a conta; o segundo permite usar o conteúdo, como ler blobs |
| Storage Blob Data Contributor | Papel de dados que permite ler, gravar e excluir blobs no escopo atribuído |
| Azure CLI | Interface de linha de comando do Azure, acessada pelo comando `az` |
| PowerShell | Ambiente de terminal e linguagem usados nos comandos deste guia |
| Código de saída | Número devolvido por um programa ao terminar; 0 indica sucesso |
| Bicep | Linguagem declarativa para descrever infraestrutura Azure |
| IaC | Infraestrutura como código: definição de recursos em arquivos versionados |
| Implantação (*deploy*) | Aplicação de uma definição para criar ou atualizar recursos |
| What-if | Previsão de alterações de infraestrutura antes da implantação |
| Reexecução previsível | Repetir um comando sem duplicar nem alterar o que já está certo; também chamada de idempotência |
| Simulação | Execução que mostra o plano sem alterar nada; é o padrão dos scripts |
| Lista de permissão | Lista do que pode ser feito; aqui, o inventário define o que pode ser enviado |
| Endereço (*endpoint*) | Endereço de acesso a um serviço; o endereço público exige autorização para entregar dados |
| HTTPS | Comunicação HTTP protegida por criptografia em trânsito |
| TLS | *Transport Layer Security*: protocolo de criptografia da comunicação; o laboratório exige a versão 1.2 |
| LRS | *Locally redundant storage*: redundância com cópias dentro de um único local físico da região |
| JSON | Formato de texto estruturado em pares nome-valor, usado nas saídas da Azure CLI |
| Blob | Objeto armazenado, como um documento de texto |
| Contêiner de blobs | Agrupamento de objetos dentro de uma conta de armazenamento |
| Metadados do blob | Pares de informação gravados junto ao blob, como identificador e versão do documento |
| ETag | Marca de versão de um blob; permite trocar o blob só se ninguém o alterou no meio |
| Exclusão reversível | Recurso que mantém blobs apagados ou sobrescritos por um prazo, para recuperação |
| Instantâneo | Cópia de um blob em determinado momento; na exclusão reversível, as versões anteriores aparecem assim |
| Inventário | Lista dos documentos e atributos usados para conferir a carga |
| Metadados | Informações sobre o documento, como produto, versão e vigência |
| Hash | Resumo calculado do conteúdo para conferir sua integridade |
| Normalização de finais de linha | Troca de CRLF (retorno de carro e avanço de linha, usado no Windows) por LF (avanço de linha, usado em outros sistemas) antes do hash, para que o mesmo texto tenha o mesmo hash em qualquer sistema |
| FAQ | Perguntas frequentes, do inglês *Frequently Asked Questions* |
| RAG | Geração de respostas apoiada em evidências recuperadas de uma base |
| Embedding | Representação numérica de conteúdo usada em busca por similaridade |
| MAF | Microsoft Agent Framework, biblioteca usada para implementar o agente do Desafio 05 |
| SDK | Conjunto de bibliotecas para usar um serviço a partir de uma linguagem de programação |
| Workspace | Pasta ou conjunto de pastas aberto no VS Code |
| Modo restrito (Restricted Mode) | Estado em que o VS Code não executa sozinho o código da pasta e limita terminal, tarefas, depuração, extensões e agentes |
| Confiança na pasta (Workspace Trust) | Decisão de confiar, ou não, nos autores de uma pasta aberta no VS Code |
| Permissões manuais | Ajuste do chat em que o Copilot pede sua aprovação antes de executar comandos e outras ações não liberadas; as edições comuns de arquivos do projeto são gravadas direto e ficam para você revisar |
| Aprovação de comando (Allow Once) | Escolha de liberar um comando de terminal só desta vez; as outras opções valem para a conversa toda ou gravam uma regra permanente |
| Interpretador e ambiente virtual | Programa que executa Python e ambiente que isola dependências do projeto |
| Prompt | Pedido e contexto fornecidos ao Copilot ou a outro modelo |
| Instruções do projeto | Arquivos que o Copilot lê sozinho para seguir as regras do repositório |
| Diff | Comparação que mostra alterações entre versões de arquivos |

## Referências

Fontes oficiais consultadas em 9 de outubro de 2026. Nomes de interface, limites e preços mudam: confira a
versão atual antes de aplicar.

1. [Assinaturas e contexto no Azure CLI](https://learn.microsoft.com/en-us/cli/azure/manage-azure-subscriptions-azure-cli).
2. [Conceitos de Azure Blob Storage](https://learn.microsoft.com/en-us/azure/storage/blobs/storage-blobs-introduction).
3. [Instalação do Bicep e da extensão para VS Code](https://learn.microsoft.com/en-us/azure/azure-resource-manager/bicep/install).
4. [Papéis para acesso a dados de blobs](https://learn.microsoft.com/en-us/azure/storage/blobs/assign-azure-role-data-access).
5. [Trabalhar com agentes no VS Code](https://code.visualstudio.com/docs/agents/overview).
6. [Gerenciar aprovações e permissões dos agentes no VS Code](https://code.visualstudio.com/docs/agents/run/approvals).
7. [Revisar e reverter alterações do agente no VS Code](https://code.visualstudio.com/docs/agents/run/review-code-edits).
8. [Instruções compartilhadas para o Copilot](https://code.visualstudio.com/docs/agent-customization/custom-instructions).
9. [Confiança no espaço de trabalho (Workspace Trust) no VS Code](https://code.visualstudio.com/docs/editing/workspaces/workspace-trust).
10. [Comando `az ad signed-in-user`](https://learn.microsoft.com/en-us/cli/azure/ad/signed-in-user).
11. [Solução de problemas do controle de acesso por papéis (RBAC) do Azure](https://learn.microsoft.com/en-us/azure/role-based-access-control/troubleshooting).
12. [Visão geral de Bicep](https://learn.microsoft.com/en-us/azure/azure-resource-manager/bicep/overview).
13. [Arquivos de parâmetros do Bicep](https://learn.microsoft.com/en-us/azure/azure-resource-manager/bicep/parameter-files).
14. [Impedir acesso de leitura anônimo a contêineres e blobs](https://learn.microsoft.com/en-us/azure/storage/blobs/anonymous-read-access-prevent).
15. [Impedir a autorização por Chave Compartilhada](https://learn.microsoft.com/en-us/azure/storage/common/shared-key-authorization-prevent).
16. [Exclusão reversível de blobs](https://learn.microsoft.com/en-us/azure/storage/blobs/soft-delete-blob-overview).
17. [Comandos `az group`](https://learn.microsoft.com/en-us/cli/azure/group).
18. [Funções de arquivos de parâmetros do Bicep, incluindo `readEnvironmentVariable`](https://learn.microsoft.com/en-us/azure/azure-resource-manager/bicep/bicep-functions-parameters-file).
19. [Previsão de alterações com Bicep what-if](https://learn.microsoft.com/en-us/azure/azure-resource-manager/bicep/deploy-what-if).
20. [Ambientes Python no VS Code](https://code.visualstudio.com/docs/python/environments).
21. [Python no VS Code](https://code.visualstudio.com/docs/languages/python).
22. [Classe `AzureCliCredential`, da biblioteca azure-identity](https://learn.microsoft.com/en-us/python/api/azure-identity/azure.identity.azureclicredential).
23. [Configurar GitHub Copilot no VS Code](https://code.visualstudio.com/docs/setup/copilot).
24. [Preços do Blob Storage](https://azure.microsoft.com/en-us/pricing/details/storage/blobs/) e [calculadora de preços do Azure](https://azure.microsoft.com/en-us/pricing/calculator/).
25. [Orçamentos e alertas no Azure Cost Management](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/tutorial-acm-create-budgets).

As atribuições do contexto fictício estão em [NOTICE.md](../../NOTICE.md). O texto deste guia está sob a
licença CC BY 4.0 (veja [LICENSE](../../LICENSE)).
