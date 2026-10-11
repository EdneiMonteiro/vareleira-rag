# L100 — Desafio 07: a identidade da aplicação com service principal, Key Vault e privilégio mínimo

[Início do laboratório](../../README.md) · Nível L100: fundamentos · [Desafio 06](06-avaliar-respostas.md)

| Item | Descrição |
| --- | --- |
| Situação | Exercício executável. Etapa 1 conferida localmente; Etapas 2 a 8 executadas no Azure em 9 de outubro de 2026, em Windows e PowerShell, após autorização para criar a identidade no tenant, o diretório do Microsoft Entra ID. Identidade, credencial, papéis e recursos temporários removidos. A correção do verificador de 11 de outubro de 2026 foi conferida apenas com dublês, sem nova execução Azure. Veja [Situação da validação](#situação-da-validação). |
| Público | Pessoas de negócio, arquitetura, operações e desenvolvimento. Use o Visual Studio Code (VS Code) para executar os comandos e conferir os resultados; escrever código é opcional. |
| Pré-requisito | [Desafio 03](03-responder-com-fontes.md) concluído: o serviço de busca com o índice, o deployment de geração e o `perguntar.py`. Os Desafios 04 a 06 melhoram o assistente, mas não são necessários aqui. |
| Resultado previsto | Um Azure Key Vault, um service principal (identidade da aplicação) com papéis para consultar o índice e usar os modelos, cinco operações conferidas por `verificar_identidade.py` e perguntas com `perguntar.py --identidade aplicacao`. |
| Custo | O Key Vault cobra por operação, e o serviço de busca dos desafios anteriores continua cobrando por hora. Veja [Custos, pausa e limpeza](#custos-pausa-e-limpeza). |

## Conteúdo

- [Cenário](#cenário)
- [Objetivos](#objetivos)
- [Artefatos e disponibilidade](#artefatos-e-disponibilidade)
- [Tecnologias e conceitos](#tecnologias-e-conceitos)
- [Reaproveitamento e acréscimos](#reaproveitamento-e-acréscimos)
- [Pré-requisitos](#pré-requisitos)
- [Etapa 1: instalar a biblioteca e ler o código sem Azure](#etapa-1-instalar-a-biblioteca-e-ler-o-código-sem-azure)
- [Etapa 2: criar o cofre com Bicep](#etapa-2-criar-o-cofre-com-bicep)
- [Etapa 3: guardar um segredo de teste sem expô-lo](#etapa-3-guardar-um-segredo-de-teste-sem-expô-lo)
- [Etapa 4: ver o contraste com a sua conta](#etapa-4-ver-o-contraste-com-a-sua-conta)
- [Etapa 5: criar a identidade da aplicação](#etapa-5-criar-a-identidade-da-aplicação)
- [Etapa 6: conceder papéis de consulta e uso de modelos](#etapa-6-conceder-papéis-de-consulta-e-uso-de-modelos)
- [Etapa 7: conferir o privilégio mínimo e perguntar como aplicação](#etapa-7-conferir-o-privilégio-mínimo-e-perguntar-como-aplicação)
- [Etapa 8: remover a identidade e o cofre](#etapa-8-remover-a-identidade-e-o-cofre)
- [Como pedir uma mudança ao Copilot no VS Code](#como-pedir-uma-mudança-ao-copilot-no-vs-code)
- [Conferência do resultado](#conferência-do-resultado)
- [Solução de problemas](#solução-de-problemas)
- [Custos, pausa e limpeza](#custos-pausa-e-limpeza)
- [Situação da validação](#situação-da-validação)
- [Glossário](#glossário)
- [Referências](#referências)

## Cenário

Em 2025, na história fictícia da Vareleira, o piloto do Assistente de Apólices funcionou até aqui na sessão de uma pessoa: tudo o que ele lê, o Azure atribui ao `az login` de quem o executa. Teresa Moura, diretora técnica de Subscrição, pergunta o que muda quando o assistente deixar o computador da equipe e funcionar como um serviço: com que identidade ele acessa os documentos, e o que ele poderia fazer se alguém copiasse a credencial dele? Beatriz Torres, responsável pelo Atendimento, quer o assistente funcionando sem depender da senha de ninguém.

**Missão:** separar a identidade que consulta o índice e usa os modelos da identidade do operador.
Guarde a credencial da aplicação no cofre e confira as operações permitidas e proibidas.
O programa ainda é executado no seu computador: a sessão do operador lê o segredo, e a aplicação
usa esse valor para acessar busca e modelos. Hospedar o assistente como serviço fica para outro nível.

> **Lembre-se:** o cenário é fictício. Não use apólices, nomes, endereços ou documentos de segurados reais, mesmo que tenha acesso a eles no trabalho.

## Objetivos

Ao concluir este desafio, você terá:

- distinguido três identidades: a de uma pessoa, a de uma aplicação (service principal) e a gerenciada pelo Azure;
- criado um Key Vault com autorização por papéis e guardado nele um segredo sem mostrá-lo na tela, em arquivo ou no histórico;
- visto, com a sua conta, o que "privilégio demais" parece;
- criado um service principal e concedido a ele os dois papéis para consultar o índice e usar os modelos;
- executado o assistente como aplicação, com o segredo lido do cofre, e conferido que as três operações proibidas testadas são negadas;
- removido a identidade, o segredo e o cofre.

**Próximos desafios:** este é o último desafio do nível L100. O
[L200, Desafio 01](../L200/01-reconstruir-base.md) reconstrói ou reaproveita a base conforme seu estado;
a hospedagem posterior usa identidade gerenciada, não a credencial temporária deste exercício.

> **Para guardar na memória: C-V-M.** Para dar uma identidade a uma aplicação, **C**ofre para o segredo, **V**alidade curta e **M**ínimo de papéis. Mnemônico criado para este curso.

## Artefatos e disponibilidade

| Artefato | Onde encontrar | Situação |
| --- | --- | --- |
| Desafio anterior (índice, deployment de geração e `perguntar.py`) | [03-responder-com-fontes.md](03-responder-com-fontes.md) | Disponível; pré-requisito |
| Cofre de segredos (Bicep) | [infra\modules\cofre.bicep](../../infra/modules/cofre.bicep) | Disponível; validado |
| Papéis de consulta e uso de modelos (Bicep) | [infra\modules\aplicacao.bicep](../../infra/modules/aplicacao.bicep) | Disponível; implantado e conferido |
| Ligação dos módulos | [infra\main.bicep](../../infra/main.bicep) | Disponível; cofre e papéis validados |
| Parâmetros do Desafio 07 | [infra\levels\l100-desafio07.bicepparam](../../infra/levels/l100-desafio07.bicepparam) | Disponível; validado com a aplicação |
| Guardar o segredo sem expô-lo | [scripts\guardar_segredo.py](../../scripts/guardar_segredo.py) | Disponível; validado |
| Segredo, credencial e erros da identidade | [scripts\lab_identidade.py](../../scripts/lab_identidade.py) | Disponível; credencial válida, segredo inválido e expiração no cofre conferidos; demais erros descritos na validação |
| Conferência de cinco operações | [scripts\verificar_identidade.py](../../scripts/verificar_identidade.py) | Disponível; versão anterior executada com operador e aplicação no Azure; correção conferida apenas com dublês |
| Pergunta e resposta com a opção `--identidade` | [scripts\perguntar.py](../../scripts/perguntar.py) | Disponível; executado como aplicação |
| Dependências, com a biblioteca do Key Vault | [requirements\l100.txt](../../requirements/l100.txt) | Disponível |
| Testes automáticos da identidade (sem Azure) | [tests\test_identidade.py](../../tests/test_identidade.py) | Disponíveis |

> **Atenção:** a Etapa 5 **cria uma identidade e uma credencial no seu tenant**, e as Etapas 2 e 6 criam recursos e papéis no Azure. Faça-as só com a autorização de quem administra o tenant e a assinatura, em um ambiente de teste. Se o seu usuário não puder registrar aplicações, pare: não peça credenciais emprestadas nem use a conta de outra pessoa. A decisão de executar cada comando é sua, mesmo quando você pede ao Copilot que "crie" ou "configure" algo.

## Tecnologias e conceitos

| Componente | Função neste desafio | Limite ou cuidado |
| --- | --- | --- |
| Service principal | A "conta" de uma aplicação no Microsoft Entra ID, a que os papéis do Azure são atribuídos [1] | Com o segredo dele, qualquer pessoa age como a aplicação |
| Registro de aplicação | O cadastro da aplicação no tenant, de onde vêm o ID da aplicação (`appId`) e as credenciais [1][2] | Alguns tenants só deixam administradores registrar aplicações |
| Identidade gerenciada | Identidade cuja credencial o Azure administra para recursos compatíveis, dispensando um segredo de cliente no programa [3] | O computador local deste exercício não fornece uma identidade gerenciada |
| Azure Key Vault | Cofre de segredos, chaves e certificados; usa controle de acesso por papéis (RBAC, *Role-Based Access Control*) [4][5] | A leitura exige um papel de dados. O nome do cofre excluído fica reservado durante a retenção, salvo expurgo permitido [6] |
| Papéis usados | `Key Vault Secrets Officer` (guardar e ler segredos, para o operador), `Search Index Data Reader` (só consultar documentos) e `Cognitive Services OpenAI User` (usar os deployments, sem administrá-los) [7][8] | Cada papel vale em um escopo: o cofre, o serviço de busca ou o recurso de modelos |
| `ClientSecretCredential` | Classe do SDK (*Software Development Kit*, conjunto de bibliotecas de programação) do Azure que autentica o service principal com o ID do tenant, o ID da aplicação e o segredo [9] | O segredo fica na memória do programa: nunca o imprima |
| `verificar_identidade.py` | Tenta 2 operações que a identidade precisa fazer e 3 que ela não deve poder fazer | A exclusão usa um índice de nome aleatório que não existe, diferente do índice informado em `--indice`; o resultado vale só para as cinco tentativas |

**Conceitos necessários:** três identidades, segredo e cofre, privilégio mínimo e conferência de operações.

**1. Três identidades.** O `az login` autentica a pessoa pelo fluxo permitido pela organização e mantém
a sessão do operador. A aplicação usa um service principal com uma credencial própria, como um
segredo de cliente ou certificado [1]. Uma identidade gerenciada permite a um recurso compatível
obter tokens sem que o programa guarde um segredo de cliente [3].

Para hospedar o assistente em um recurso Azure compatível, prefira a identidade gerenciada: ela
dispensa a distribuição e a renovação manual desse segredo. O exercício local usa um service
principal com segredo para ensinar seu armazenamento e sua expiração. As três identidades ainda
dependem de papéis adequados e de proteção do ambiente que as utiliza.

> **Para guardar na memória: o crachá e o armário de chaves.** O service principal é o crachá de um prestador temporário: abre só as portas da função dele. O Key Vault é o armário trancado onde o código do crachá fica guardado, e nunca num bilhete preso na parede. Analogia criada para este curso.

**2. O segredo e o cofre.** Trate o segredo da aplicação como uma senha: sua cópia permite autenticar
como a aplicação enquanto a credencial estiver válida. Neste exercício, você define uma data de
expiração, captura o valor em uma variável e o envia por *pipe* (saída de um comando ligada à entrada
de outro) ao programa que o grava no cofre. Os comandos evitam imprimir o valor ou passá-lo como
argumento, pois argumentos podem aparecer no histórico e na lista de processos [5].

A leitura do cofre exige um papel de dados [4]. A exclusão reversível (*soft-delete*) mantém cofres
e segredos excluídos pelo período configurado; o nome do cofre fica reservado nesse período,
salvo expurgo permitido [6].

**3. Privilégio mínimo.** A aplicação recebe `Search Index Data Reader` para consultar documentos do
índice e `Cognitive Services OpenAI User` para gerar embeddings e respostas [7][8].
Os escopos são o serviço de busca e o recurso de modelos. O laboratório deixa a aplicação sem papéis
de escrita no índice, de acesso ao Blob Storage ou de leitura do cofre.

Uma credencial copiada ainda permite consultar o conteúdo indexado e consumir tokens. Confira também
eventuais papéis preexistentes ou herdados: as duas atribuições do exercício não são uma auditoria
completa das permissões da identidade.

**4. Como o programa usa a identidade.** Com `--identidade aplicacao`:

1. lê o segredo do cofre **com a sessão do operador no Azure CLI** (*Command-Line Interface*, interface
   de linha de comando), que precisa de permissão de leitura de segredos;
2. cria uma `ClientSecretCredential` com tenant, identificador da aplicação e segredo [9];
3. entrega essa credencial aos clientes do índice, de embeddings e de geração.

O processo recebe o valor em memória; a cópia guardada permanece no cofre. Sem essa opção, os clientes
usam a sessão do operador, como nos desafios anteriores. A opção aplica-se a `perguntar.py` e
`verificar_identidade.py`; o agente e a avaliação dos Desafios 05 e 06 mantêm a identidade do operador.

**5. Como conferir as operações proibidas.** O verificador tenta excluir um índice de nome aleatório
que não existe, ler um segredo descartando o valor e listar um item do Blob Storage.
O nome começa com `vlr-verificacao-` e termina com 16 dígitos hexadecimais (de 0 a 9 e de a a f).
O programa usa `secrets.token_hex(8)` para gerar 8 bytes, ou 64 bits, de aleatoriedade [11].
A cada execução, sorteia um nome novo; se coincidir com o índice informado em `--indice`,
descarta o nome e sorteia de novo. Esse índice não é criado para o teste.

A exclusão continua sendo um pedido de escrita autenticado: a resposta confere a permissão,
sem remover um índice real. A recusa esperada é
HTTP 403 (*Hypertext Transfer Protocol*, protocolo da web; *Forbidden*, proibido).
Se o serviço aceitar o pedido ou responder HTTP 404 (*Not Found*, alvo não encontrado) depois da
autorização, o verificador marca "permitido": privilégio demais para a aplicação, mesmo sem excluir
conteúdo. Uma operação necessária recusada indica privilégio de menos.
O resultado cobre as cinco tentativas, não todas as ações possíveis da identidade.
Revise também os papéis, seus escopos e eventuais atribuições herdadas.

> **Para guardar na memória: a portaria e a sala que não existe.** É como pedir à portaria a remoção
> de uma sala com um número recém-sorteado, que não foi usado no prédio: testa-se a autorização sem
> mirar uma sala em uso. Cinco pedidos não mostram todos os acessos do crachá. Analogia criada para este curso.

> **Atenção — execução das Etapas 4 e 7:** a conferência manual de ausência de um nome fixo deixa de
> ser condição, pois o código sorteia um nome novo, diferente do índice consultado, para o alvo inexistente.
> Use o serviço do laboratório, de preferência exclusivo, e papéis no menor escopo possível.
> O pedido de escrita autenticado exige autorização correspondente, embora não altere recursos existentes.
> Sem essa autorização, omita o verificador e registre a pendência.

## Reaproveitamento e acréscimos

| Item | Situação | Observação |
| --- | --- | --- |
| Infraestrutura dos Desafios 01 a 03 | Reaproveitada | As criações previstas são o cofre e o papel do operador; confira também cada alteração apresentada no what-if |
| `infra\modules\cofre.bicep`, `infra\modules\aplicacao.bicep` e `l100-desafio07.bicepparam` | **Novos** | O cofre usa papéis (RBAC), exclusão reversível de 7 dias e proteção contra expurgo ligada por padrão; o arquivo de parâmetros do laboratório a desliga, de propósito, para a limpeza ser completa |
| `infra\main.bicep` | Extensão | Parâmetros de cofre e aplicação, inclusive `protecaoCofreContraExpurgo`; saídas com nomes, endereço e indicação dos papéis atribuídos |
| `lab_identidade.py`, `guardar_segredo.py` e `verificar_identidade.py` | **Novos** | Segredo, credencial, tradução de erros, gravação sem exposição e conferência de privilégios |
| `lab_indexacao.py`, `lab_geracao.py` e `lab_comum.py` | Extensão pequena | As funções que criam clientes aceitam uma credencial opcional; sem ela, usam o Azure CLI |
| `perguntar.py` | Extensão | Opções `--identidade`, `--cofre`, `--nome-do-segredo` e `--id-da-aplicacao`; sem `--identidade aplicacao`, a saída é a mesma de antes |
| `requirements\l100.txt` | Inclui `azure-keyvault-secrets` | Instale as dependências na Etapa 1 |
| Testes | `tests\test_identidade.py` novo | Executam sem Azure |
| Reverter | Remover o cofre e a aplicação (Etapa 8) | Os desafios anteriores não dependem deles |

## Pré-requisitos

Os comandos deste guia são escritos para Windows e PowerShell, no terminal integrado do Visual Studio Code (VS Code), como nos desafios anteriores.

| Pré-requisito | Como preparar | Necessário agora? |
| --- | --- | --- |
| Desafio 03 concluído | Índice, deployment de geração e `perguntar.py` funcionando, no mesmo grupo de recursos e na mesma assinatura | Sim |
| Variáveis do terminal | `$assinatura`, `$grupo`, `$busca`, `$modelos`, `$conta` e `$tenant` definidas (veja abaixo) | Sim |
| Assinatura Azure ativa | Use a assinatura autorizada nos desafios anteriores | Sim |
| Permissão de implantar recursos | Papel como `Contributor` no grupo de recursos [7] | Sim, nas Etapas 2 e 6 |
| Permissão de atribuir papéis | `User Access Administrator` ou papel equivalente no escopo, além da permissão de implantação [7] | Sim, nas Etapas 2 e 6 |
| Permissão de registrar aplicações no tenant | Papel como `Application Developer` no Microsoft Entra ID, ou a configuração do tenant que permite o registro por usuários [2] | Só na Etapa 5 |
| Ambiente virtual do Python | O mesmo do Desafio 01; a Etapa 1 instala uma biblioteca nova | Sim |
| Aceitar o custo | O Key Vault cobra por operação; o serviço de busca continua cobrando por hora | Sim |

Em um terminal novo, defina as variáveis de novo. Substitua `<ID-DA-SUA-ASSINATURA>` e use o nome do grupo criado no Desafio 01:

```powershell
$assinatura = "<ID-DA-SUA-ASSINATURA>"
$grupo = "<NOME-DO-GRUPO-EXCLUSIVO-AUTORIZADO>"
$busca = az deployment group show --subscription $assinatura --resource-group $grupo --name vareleira-rag-l100-d02 --query properties.outputs.nomeBusca.value --output tsv
$modelos = az deployment group show --subscription $assinatura --resource-group $grupo --name vareleira-rag-l100-d02 --query properties.outputs.nomeModelos.value --output tsv
$conta = az deployment group show --subscription $assinatura --resource-group $grupo --name vareleira-rag-l100 --query properties.outputs.nomeConta.value --output tsv
$tenant = az account show --subscription $assinatura --query tenantId --output tsv
$busca
$modelos
$conta
```

**Resultado esperado:** `srch-vlr-...`, `ais-vlr-...` e `stvlrag...`. O ID do tenant (`$tenant`) é um identificador do seu ambiente: não o publique.

Antes dos comandos `az ad`, compare o tenant da sessão ativa da Azure CLI
(`az account show --query tenantId --output tsv`, sem `--subscription`) com `$tenant`.
Os comandos `az ad` deste roteiro usam o tenant ativo e não aceitam `--subscription`.
Se os tenants divergirem, pare e autentique-se no tenant autorizado em uma sessão apropriada.
Consultar a assinatura de destino não muda o tenant usado por esses comandos.

## Etapa 1: instalar a biblioteca e ler o código sem Azure

**Objetivo:** instalar a biblioteca do Key Vault e executar os testes da identidade. Esta etapa não acessa o Azure.

### 1.1 Instalar a dependência

```powershell
python -m pip install -r requirements\l100.txt
python -m pip check
python -m pip show azure-keyvault-secrets
```

**Resultado esperado:** o primeiro comando instala `azure-keyvault-secrets` (ou informa `Requirement already satisfied`), o segundo informa `No broken requirements found.` e o terceiro mostra `Version: 4.11.3`.

### 1.2 Executar os testes da identidade

```powershell
python -m unittest discover -s tests -p "test_identidade.py"
```

**Resultado esperado:** uma linha de pontos, `Ran 41 tests` e `OK`.

**Atividade 1:** abra `scripts\lab_identidade.py` e procure por `print(`: o módulo que lê e guarda o segredo não imprime nada. Depois abra `scripts\guardar_segredo.py`, localize as duas linhas com `print(` e confirme que nenhuma usa a variável `valor`, que guarda o segredo.

**Conferência:** a busca em `lab_identidade.py` não encontra nenhuma ocorrência. Em `guardar_segredo.py`, os dois `print` mostram o nome do segredo, o nome do cofre, a versão e a data de validade, mas nunca o valor. Os testes `test_grava_a_entrada_padrao_sem_mostrar_o_valor` e `test_erro_do_cofre_vira_orientacao_sem_o_valor` garantem que o valor também não aparece na saída nem nas mensagens de erro.

### Prompt para o Copilot: seguir o caminho do segredo

Anexe `scripts\lab_identidade.py`, `scripts\guardar_segredo.py` e `scripts\perguntar.py`:

```text
Leia scripts/lab_identidade.py, scripts/guardar_segredo.py e scripts/perguntar.py anexados.
Explique, para quem não programa e com uma analogia, o caminho do segredo: de onde ele vem, onde fica guardado e onde ele existe quando o assistente funciona como aplicação.
Liste os lugares onde um segredo costuma vazar (arquivo, histórico do terminal, argumento de comando, mensagem de erro, saída do programa) e diga o que o código faz para cada um.
Aponte qualquer ponto em que o valor do segredo poderia ser impresso.
Não edite arquivos, não execute comandos e não acesse o Azure.
```

**Conferência:** a resposta deve localizar a entrada padrão em `ler_valor`, a validação em
`guardar_segredo` e a leitura do cofre em `resolver_credencial`. O processo recebe o segredo em memória
sem imprimi-lo. Confira também a tradução dos erros, que omite o texto bruto na saída padrão;
o modo detalhado é uma opção de diagnóstico e suas saídas exigem revisão antes de compartilhar.

## Etapa 2: criar o cofre com Bicep

**[altera o Azure]** nos comandos `az deployment group create`.

**Objetivo:** criar o Key Vault no mesmo grupo e conceder ao operador o papel de guardar e ler segredos
no cofre. O [módulo de cofre](../../infra/modules/cofre.bicep) cria o recurso.
O [arquivo principal](../../infra/main.bicep) chama esse módulo quando `implantarCofre` é verdadeiro, e
os [parâmetros do Desafio 07](../../infra/levels/l100-desafio07.bicepparam) habilitam o cofre e mantêm
as escolhas anteriores.

Repita no `what-if` e na implantação todos os nomes, regiões, camadas e capacidades personalizados
nos desafios anteriores: este arquivo não recupera essas escolhas sozinho. Se os recursos já foram
isolados pelo L300/L400, siga o roteiro daquele nível; reaplicar o L100 pode reabrir acesso público.

### Decisões de configuração do Bicep

| Decisão do Bicep | O que faz | Por que importa |
| --- | --- | --- |
| `enableRbacAuthorization: true` | O acesso aos segredos vem só dos papéis do Azure, sem as políticas de acesso antigas | Um único modelo de permissão, o mesmo dos desafios anteriores [4] |
| Exclusão reversível de 7 dias | Segredos e cofres excluídos podem ser recuperados por 7 dias, o mínimo do Azure [6] | Protege contra exclusão acidental; o nome do cofre fica reservado nesse período |
| Proteção contra expurgo: ligada no módulo, desligada no arquivo do laboratório | O módulo usa `protecaoContraExpurgo = true` por padrão, e `l100-desafio07.bicepparam` a desliga | Ligada, ela não pode ser desfeita: o cofre excluído reserva o nome durante toda a retenção e não pode ser expurgado antes do fim dela. O laboratório a desliga para limpar tudo; em produção, mantenha-a ligada [5] |
| Papel `Key Vault Secrets Officer` só para o operador, só no cofre | A sua conta guarda e lê segredos; a aplicação não recebe nenhum papel no cofre | Quem pode criar o cofre não ganha, por isso, acesso aos segredos |
| Endereço público com autenticação | O cofre responde pela internet, mas só a quem tem papel | Endpoints privados ficam para outro nível |

### 2.1 Informar quem opera o laboratório

```powershell
$env:VARELEIRA_ID_OBJETO_CARGA = az ad signed-in-user show --query id --output tsv
```

O comando não imprime nada quando conclui com sucesso. A variável `VARELEIRA_ID_OBJETO_APLICACAO` fica vazia por enquanto: ela só é usada na Etapa 6.

### 2.2 Simular a implantação (what-if)

```powershell
az deployment group what-if --subscription $assinatura --resource-group $grupo --name vareleira-rag-l100-d07 --parameters infra\levels\l100-desafio07.bicepparam
```

**Resultado esperado:** criação do cofre e da atribuição de papel do operador.
A previsão registrada terminou em `Resource changes: 2 to create, 6 to modify, 5 no change`;
os seis itens `~ Modify` vieram de propriedades preenchidas pelos serviços. Confira cada diferença
da sua previsão. Se aparecer exclusão de recurso ou criação inesperada do armazenamento ou da busca,
interrompa e confira o grupo e os parâmetros.

### 2.3 Implantar

```powershell
az deployment group create --subscription $assinatura --resource-group $grupo --name vareleira-rag-l100-d07 --parameters infra\levels\l100-desafio07.bicepparam
Remove-Item Env:\VARELEIRA_ID_OBJETO_CARGA
```

**Tempo de referência:** cerca de 80 segundos, medidos em `brazilsouth`.

### 2.4 Registrar o nome do cofre

```powershell
$cofre = az deployment group show --subscription $assinatura --resource-group $grupo --name vareleira-rag-l100-d07 --query properties.outputs.nomeCofre.value --output tsv
$cofre
```

**Resultado esperado:** `kv-vlr-...`, o nome do cofre, que forma o endereço `https://<nome-do-cofre>.vault.azure.net/`.

## Etapa 3: guardar um segredo de teste sem expô-lo

**[altera o Azure]** no comando que grava o segredo.

**Objetivo:** treinar, com um valor aleatório, o caminho que a credencial da aplicação vai percorrer na Etapa 5: do comando que a cria direto para o cofre, sem passar por arquivo, argumento de comando ou tela. O valor aleatório não é a credencial de nenhuma identidade.

```powershell
$segredo = -join ((48..57 + 65..90 + 97..122) | Get-Random -Count 40 | ForEach-Object { [char]$_ })
$segredo | python scripts\guardar_segredo.py --cofre $cofre --nome-do-segredo segredo-de-teste --validade-dias 3
Remove-Variable segredo
```

O primeiro comando cria um valor de 40 caracteres e o guarda só na variável `$segredo`. O segundo o envia ao programa pela entrada padrão (o *pipe* `|`), e o programa o grava no cofre com data de validade. O terceiro apaga a variável da sessão.

**Resultado esperado** (a versão e a data variam):

```text
Segredo 'segredo-de-teste' gravado no cofre 'kv-vlr-...' (versão <32 caracteres hexadecimais>), válido até AAAA-MM-DD.
O valor não foi mostrado nem gravado em arquivo. Apague-o da sessão do terminal quando terminar (por exemplo, Remove-Variable segredo).
```

A data de expiração é três dias após a gravação. Se ocorrer falta de permissão, confira o papel
`Key Vault Secrets Officer` no cofre. Uma atribuição recém-criada pode levar alguns minutos para valer.

Para ver o registro do segredo sem ver o valor, peça só os metadados:

```powershell
az keyvault secret show --vault-name $cofre --name segredo-de-teste --query "{Nome:name,Validade:attributes.expires,Etiquetas:tags}" --output json
```

**Resultado esperado:**

```json
{
  "Etiquetas": {
    "laboratorio": "vareleira-rag",
    "uso": "identidade-da-aplicacao"
  },
  "Nome": "segredo-de-teste",
  "Validade": "AAAA-MM-DDTHH:MM:SS+00:00"
}
```

**Atividade 2:** procure o valor do segredo nos lugares onde um segredo costuma vazar. Execute `Get-History | Select-Object -Last 6 | Format-List CommandLine` e procure o valor nos comandos. Depois confira que a saída do programa também não o mostra.

**Conferência:** o histórico deve conter `$segredo | python scripts\guardar_segredo.py ...`, com o nome
da variável. A saída mostra metadados, sem o valor. Confira ambos antes de compartilhar qualquer
evidência. A comparação de leitura e gravação feita no ambiente testado está no registro de validação.

> **Atenção:** o comando `az keyvault secret show` sem `--query` mostra o valor do segredo. Em um terminal compartilhado, gravado ou visto por outras pessoas, use sempre a consulta que escolhe só os metadados.

## Etapa 4: ver o contraste com a sua conta

**Objetivo:** comparar as permissões do operador com as operações necessárias à aplicação.
Esta etapa não cria, troca nem remove recursos existentes: a tentativa de exclusão envia um pedido
de escrita autenticado ao índice de nome aleatório que não existe, e a resposta serve para conferir
a permissão. A geração de embeddings consome tokens.

```powershell
python scripts\verificar_identidade.py --busca $busca --modelos $modelos --conta $conta --cofre $cofre --nome-do-segredo segredo-de-teste --identidade operador
```

O programa tenta cinco operações com a identidade escolhida. Duas são necessárias ao assistente
(consultar o índice e gerar embeddings), e três não devem ser permitidas a ele: apagar um índice
de nome aleatório que não existe, ler o segredo e descartar o valor, e pedir o primeiro item da lista
de documentos. O resultado descreve somente essas cinco tentativas, não todo o acesso da identidade.

**Exemplo de saída esperada da versão corrigida, com os papéis dos Desafios 01 a 03 e da Etapa 2.** As permissões da sua conta
determinam o resultado; nesta configuração, o código 3 indica operações excedentes para a aplicação:

```text
Verificação do privilégio mínimo, sem alterar recursos existentes · identidade: operador (sessão do Azure CLI)
Alvos: busca 'srch-vlr-...', modelos 'ais-vlr-...', conta 'stvlrag...', cofre 'kv-vlr-...'.
[OK   ] Consultar o índice 'vareleira-lar-l100' (leitura): permitido, como esperado (operação aceita)
[OK   ] Gerar embeddings no recurso 'ais-vlr-...': permitido, como esperado (operação aceita)
[FALHA] Alterar o serviço de busca (apagar um índice de nome aleatório que não existe): esperado negado, obtido permitido (operação aceita). PRIVILÉGIO DEMAIS: a identidade não deveria poder fazer isto. Revise os papéis dela
[FALHA] Ler o segredo 'segredo-de-teste' do cofre 'kv-vlr-...': esperado negado, obtido permitido (operação aceita). PRIVILÉGIO DEMAIS: a identidade não deveria poder fazer isto. Revise os papéis dela
[FALHA] Listar os documentos da conta 'stvlrag...': esperado negado, obtido permitido (operação aceita). PRIVILÉGIO DEMAIS: a identidade não deveria poder fazer isto. Revise os papéis dela
Esta conferência usou a sua conta, que costuma ter papéis amplos: as falhas por privilégio demais são o contraste esperado. Use --identidade aplicacao para conferir a aplicação.
Privilégio divergente do esperado. Corrija os papéis e repita. Este resultado vale só para as cinco tentativas acima. Nenhum recurso existente foi alterado por este script: a exclusão testada usa o nome aleatório de um índice que não existe.
```

**Atividade 3:** para cada `[FALHA]`, diga qual papel da sua conta concede a permissão e que dano a aplicação poderia causar se tivesse a mesma permissão.

**Conferência:** com os papéis do exercício, `Search Service Contributor` permite administrar índices;
`Key Vault Secrets Officer`, ler e alterar segredos; e `Storage Blob Data Contributor`, ler, gravar e
excluir os blobs no escopo atribuído. A aplicação só precisa consultar o índice e usar os modelos.
Se houver outras atribuições na sua conta, examine o papel e o escopo de cada operação aceita.

## Etapa 5: criar a identidade da aplicação

**[altera o Microsoft Entra ID]** nos comandos `az ad app create`, `az ad sp create` e
`az ad app credential reset`; **[altera o Azure]** ao gravar a credencial no cofre.

> **Atenção:** esta etapa foi executada em ambiente autorizado; você precisa de autorização para
> criar a identidade e a credencial no seu tenant. Se `az ad app create` for recusado, interrompa e
> consulte o administrador. Registre as saídas sem identificadores ou valores de segredo.

**Objetivo:** registrar a aplicação, criar o service principal dela e guardar a credencial no cofre, com validade de 7 dias.

Os comandos `az ad` não têm `what-if` neste roteiro. Antes de executá-los, revise com o administrador
o plano: uma aplicação nova, um service principal e uma credencial temporária, no tenant confirmado.
Registre os identificadores privadamente a cada sucesso e pare se um comando falhar. Repetir
`az ad app create` cria outra aplicação com o mesmo nome de exibição; `credential reset --append`
acrescenta outra credencial, e `guardar_segredo.py` cria outra versão no cofre. Na retomada,
reutilize somente os objetos próprios já conferidos, sem repetir cegamente a sequência.

```powershell
$aplicacao = az ad app create --display-name "sp-vlr-assistente-l100" --sign-in-audience AzureADMyOrg --query appId --output tsv
$idObjetoAplicacao = az ad sp create --id $aplicacao --query id --output tsv
```

O primeiro comando registra a aplicação, só neste tenant, e guarda em `$aplicacao` o ID dela (`appId`). O segundo cria o service principal e guarda em `$idObjetoAplicacao` o ID de objeto dele, que é o valor que o Azure pede ao conceder papéis. Os dois são identificadores do seu ambiente, e não segredos: não os publique.

```powershell
$validade = (Get-Date).AddDays(7).ToString("yyyy-MM-dd")
$segredo = az ad app credential reset --id $aplicacao --display-name "credencial-l100" --end-date $validade --append --query password --output tsv
$segredo | python scripts\guardar_segredo.py --cofre $cofre --validade-dias 7
Remove-Variable segredo
```

O primeiro comando define a data de expiração; o segundo acrescenta a credencial com `--append` e
captura seu valor em `$segredo`. O terceiro grava esse valor no cofre como `segredo-da-aplicacao`, e
o quarto remove a variável. O Azure CLI pode mostrar um aviso de que a saída contém credenciais;
o valor deve permanecer capturado na variável.

A data da credencial no Entra ID e a validade do segredo no Key Vault são definidas separadamente.
O cofre recebe sete dias a partir da gravação; `--end-date` recebe a data calculada no terminal.
Confira os metadados da credencial criada: mudar a validade no cofre não renova a credencial do Entra ID.

**Atividade 4:** confira a gravação e a ausência do valor nas saídas: repita a consulta de metadados da
Etapa 3 com `--name segredo-da-aplicacao` e revise o histórico do terminal e a saída do programa.

**Conferência:** a consulta de metadados mostra o nome, a validade de 7 dias e as etiquetas, e o histórico não traz o valor. Se o valor aparecer em algum lugar, trate a credencial como vazada: exclua-a (`az ad app credential delete`) e repita a etapa.

## Etapa 6: conceder papéis de consulta e uso de modelos

**[altera o Azure]** nos comandos `az deployment group create`.

> **Lembre-se:** o módulo cria exatamente duas atribuições para o service principal.
> Confira o papel, a identidade e o escopo no what-if e nas atribuições reais, antes de testar os acessos.

**Objetivo:** atribuir `Search Index Data Reader` no serviço de busca e `Cognitive Services OpenAI User`
no recurso de modelos. O parâmetro `principalIdAplicacao` recebe o ID de objeto do service principal;
`principalType: ServicePrincipal` informa seu tipo ao Azure. Confira a criação e a propagação das
atribuições na Etapa 7.

```powershell
$env:VARELEIRA_ID_OBJETO_CARGA = az ad signed-in-user show --query id --output tsv
$env:VARELEIRA_ID_OBJETO_APLICACAO = $idObjetoAplicacao
az deployment group what-if --subscription $assinatura --resource-group $grupo --name vareleira-rag-l100-d07 --parameters infra\levels\l100-desafio07.bicepparam
```

**Resultado esperado:** duas atribuições de papel com `+ Create` (uma no serviço de busca e outra no recurso de modelos), o cofre sem mudança e os itens `~ Modify` de ruído, como na Etapa 2. Se aparecer qualquer outro papel para a aplicação, interrompa.

```powershell
az deployment group create --subscription $assinatura --resource-group $grupo --name vareleira-rag-l100-d07 --parameters infra\levels\l100-desafio07.bicepparam
Remove-Item Env:\VARELEIRA_ID_OBJETO_CARGA, Env:\VARELEIRA_ID_OBJETO_APLICACAO
```

Um papel novo pode levar alguns minutos para valer.

## Etapa 7: conferir o privilégio mínimo e perguntar como aplicação

> **Lembre-se:** a conferência cobre as cinco operações abaixo, não todas as permissões possíveis.
> Registre os resultados da sua execução, inclusive as três recusas esperadas.

**Objetivo:** executar as cinco tentativas como aplicação e fazer uma pergunta com essa identidade.
Esta etapa não cria, troca nem remove recursos existentes: o verificador envia um pedido de escrita
autenticado ao índice de nome aleatório que não existe, para conferir a permissão. Embeddings e
geração consomem tokens.

```powershell
python scripts\verificar_identidade.py --busca $busca --modelos $modelos --conta $conta --cofre $cofre --id-da-aplicacao $aplicacao --tenant-id $tenant
```

**Exemplo de saída esperada da versão corrigida** (nomes substituídos por marcadores).
A execução histórica no Azure usou o nome fixo; o alvo aleatório e as mensagens atuais foram
conferidos apenas por testes locais com dublês:

```text
Verificação do privilégio mínimo, sem alterar recursos existentes · identidade: aplicação (service principal), com o segredo lido do cofre 'kv-vlr-...'
Alvos: busca 'srch-vlr-...', modelos 'ais-vlr-...', conta 'stvlrag...', cofre 'kv-vlr-...'.
[OK   ] Consultar o índice 'vareleira-lar-l100' (leitura): permitido, como esperado (operação aceita)
[OK   ] Gerar embeddings no recurso 'ais-vlr-...': permitido, como esperado (operação aceita)
[OK   ] Alterar o serviço de busca (apagar um índice de nome aleatório que não existe): negado, como esperado (HTTP 403)
[OK   ] Ler o segredo 'segredo-da-aplicacao' do cofre 'kv-vlr-...': negado, como esperado (HTTP 403)
[OK   ] Listar os documentos da conta 'stvlrag...': negado, como esperado (HTTP 403)
As duas operações necessárias funcionaram e as três proibidas foram recusadas. Este resultado vale só para as cinco tentativas acima. Nenhum recurso existente foi alterado por este script: a exclusão testada usa o nome aleatório de um índice que não existe. Isso não prova que a identidade não tenha outros acessos: revise também as atribuições de papel dela no Azure.
```

Cinco linhas `[OK]` e código de saída 0 indicam que as duas operações necessárias funcionaram
e as três proibidas foram recusadas. Isso não confirma privilégio mínimo em todos os acessos:
revise também as atribuições de papel da aplicação no Azure.

Se uma das duas primeiras linhas informar "PRIVILÉGIO DE MENOS", confira os papéis e os escopos.
Logo após a Etapa 6, aguarde a propagação das atribuições antes de repetir.

```powershell
python scripts\perguntar.py --busca $busca --modelos $modelos --pergunta "Qual é a franquia da cobertura de danos elétricos?" --politica completa --identidade aplicacao --cofre $cofre --id-da-aplicacao $aplicacao --tenant-id $tenant
```

**Conferência:** procure a linha de identidade abaixo e compare a resposta com as evidências da franquia.
O texto e as citações podem variar entre chamadas, como no Desafio 04:

```text
Identidade: aplicação (service principal), com o segredo lido do cofre 'kv-vlr-...'
```

**Atividade 5:** compare a Etapa 4 com a Etapa 7. Quais tentativas mudaram de "permitido" para "negado", e por quê? Se alguém copiasse a credencial da aplicação, o que essa pessoa poderia fazer, e o que não poderia?

**Conferência:** com apenas os papéis do exercício, as três tentativas proibidas devem ser recusadas.
Se alguma for aceita, confira atribuições extras ou herdadas. Uma credencial copiada ainda permite
consultar o conteúdo do índice e consumir tokens até sua expiração ou revogação; esse risco justifica
a validade limitada e o armazenamento no cofre.

**Atividade 6:** o que acontece quando a validade do segredo termina? Leia a função `ler_segredo` em `scripts\lab_identidade.py` e o teste `test_recusa_segredo_desativado_expirado_ou_vazio`.

**Conferência:** o programa recusa o segredo expirado antes de qualquer acesso ao índice ou aos modelos, com a mensagem "O segredo '...' expirou em AAAA-MM-DD" e a orientação de gerar uma nova credencial. A recusa do cofre e a do Microsoft Entra ID (códigos `AADSTS7000222` e `AADSTS7000215`) também têm mensagem própria. A recusa de um segredo expirado no cofre e a mensagem `AADSTS7000215` foram conferidas no Azure.
A expiração da credencial no Entra ID (`AADSTS7000222`) continua coberta apenas pelos testes locais.

## Etapa 8: remover a identidade e o cofre

**[altera o Azure]** nos comandos de exclusão dos papéis e do cofre e no expurgo;
**[altera o Microsoft Entra ID]** no comando que exclui o registro da aplicação.

**Objetivo:** apagar o que o desafio criou: os papéis e o registro da aplicação (que leva o service principal e as credenciais), e o cofre com o segredo.

### 8.1 Remover a aplicação

> **Atenção:** execute esta sequência somente para a identidade e os papéis criados na Etapa 5
> e na Etapa 6, após conferir seus identificadores. Preserve aplicações e atribuições preexistentes.

Na listagem de atribuições de cada recurso, confira o principal, o papel e o **escopo exato** contra
seu registro da Etapa 6. Copie somente os dois IDs de atribuição próprios para os marcadores abaixo.
Não revogue por nome de aplicação nem por uma listagem que inclua papéis herdados. A remoção por IDs
abaixo é um ajuste documental desta revisão; não foi novamente executada no Azure.

```powershell
$idBusca = az search service show --subscription $assinatura --resource-group $grupo --name $busca --query id --output tsv
$idModelos = az cognitiveservices account show --subscription $assinatura --resource-group $grupo --name $modelos --query id --output tsv
az role assignment delete --subscription $assinatura --ids "<ID-DA-ATRIBUICAO-DE-LEITURA-CRIADA-NA-ETAPA-6>"
az role assignment delete --subscription $assinatura --ids "<ID-DA-ATRIBUICAO-DE-MODELOS-CRIADA-NA-ETAPA-6>"
az ad app delete --id $aplicacao
```

Os dois primeiros comandos obtêm os escopos para a conferência, os dois seguintes removem somente
as atribuições identificadas, e o último exclui o registro da aplicação, o service principal e as
credenciais. Confira depois a ausência dos objetos ativos e das atribuições próprias, preservando
as anteriores. Sem remover os papéis antes, eles ficam no painel como "identidade não encontrada"
até a exclusão do grupo de recursos.

### 8.2 Excluir e expurgar o cofre

Consulte a região do próprio cofre, que pode diferir da região do grupo. Essa consulta ajustada
foi conferida documentalmente nesta revisão, sem nova execução Azure.

```powershell
$regiao = az keyvault show --subscription $assinatura --resource-group $grupo --name $cofre --query location --output tsv
az keyvault delete --subscription $assinatura --resource-group $grupo --name $cofre
az keyvault purge --subscription $assinatura --name $cofre --location $regiao
```

O primeiro comando obtém a região do cofre, o segundo exclui o cofre, que passa ao estado "excluído" por 7 dias, e o terceiro o expurga, o que libera o nome e apaga os segredos de vez [6]. O expurgo só é possível porque a proteção contra expurgo está desligada no arquivo de parâmetros do laboratório (Etapa 2): com ela ligada, o cofre excluído só pode ser expurgado depois do fim da retenção [6].

**Resultado esperado:** `az keyvault delete` mostra o aviso sobre a reserva do nome; `az keyvault purge`
termina sem saída. Confira com `az keyvault list-deleted --subscription $assinatura --query "[].name" --output tsv`:
o nome do seu cofre deve estar ausente. Preserve outros cofres que a lista mostrar.

## Como pedir uma mudança ao Copilot no VS Code

Use o [procedimento do Desafio 01](01-preparar-ambiente.md#como-pedir-uma-mudança-ao-copilot-no-vs-code):
contexto, plano, limites, revisão do diff (comparação entre versões dos arquivos) e verificação com
comandos autorizados. Nunca inclua segredo, credencial ou ID do tenant no pedido ou nos anexos.
Antes de descrever um erro, remova os identificadores do ambiente.

### Exemplo: resumir a conferência em uma tabela

Cole com os arquivos anexados:

```text
Leia o README, o L100 Desafio 07, scripts/verificar_identidade.py e scripts/lab_identidade.py anexados.
Quero que verificar_identidade.py mostre, no fim, uma tabela de três colunas (operação, esperado, obtido), além das linhas atuais.
Antes de editar, proponha o plano: arquivos, funções e testes.
Cuidados obrigatórios: a tabela não pode mostrar o valor do segredo, o texto bruto dos erros nem IDs de assinatura, de tenant ou de aplicação;
a tentativa de ler o segredo continua só descartando o valor; as mensagens de privilégio demais e de menos e os códigos de saída continuam iguais;
não altere os papéis do Bicep nem as tentativas.
Escreva testes com unittest e dublês, sem acessar o Azure.
Use o Python do ambiente virtual, .\.venv\Scripts\python.exe, e execute apenas:
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_identidade.py"
Não instale pacotes, não acesse o Azure, não crie identidades nem credenciais e não altere recursos.
```

**Conferência:** o diff deve acrescentar a tabela sem alterar `classificar` nem `conferir`, e trazer testes para os casos "tudo certo", "privilégio demais" e "privilégio de menos". Confira o vazamento: para mostrar o "obtido" da leitura do segredo, o Copilot pode guardar o retorno de `get_secret` e imprimi-lo; para mostrar o motivo de um erro, pode imprimir o texto bruto da exceção, que pode conter o endereço do cofre e identificadores. Confira também se ele "conserta" um resultado inesperado dando mais papéis à aplicação ou removendo a tentativa: o alarme é o objetivo da conferência.

> **Dica:** peça uma explicação do diff, com palavras simples, antes de aceitá-lo. Outros pedidos para praticar: "explique cada teste de `test_identidade.py` em uma frase" e "liste, sem editar, as diferenças entre identidade gerenciada e service principal para o assistente deste laboratório".

**Modo construtor (opcional).** Para ver como o Copilot resolveria o desafio, peça um plano em uma pasta separada e compare o resultado com os arquivos deste projeto pelo diff:

```text
Leia o L100, Desafio 07, o README e as instruções do projeto.
Proponha, sem editar, como dar a um assistente que lê documentos uma identidade própria no Azure:
que tipo de identidade usar em cada ambiente, que papéis conceder e em que escopo, onde guardar a credencial,
como conferir as cinco operações do verificador sem tratá-las como auditoria de todos os acessos, revisar os papéis e remover a identidade.
Não crie identidades nem credenciais, não atribua papéis, não envie dados e não exclua recursos.
```

Qualquer ação que crie identidades, credenciais ou papéis continua dependendo da sua decisão.

## Conferência do resultado

| Verificação | Como conferir | Evidência esperada |
| --- | --- | --- |
| Biblioteca e testes | Etapa 1 | `Version: 4.11.3`; `Ran 41 tests` e `OK` |
| Cofre | Etapa 2 | `kv-vlr-...`; what-if com dois recursos para criar |
| Segredo guardado sem exposição | Etapa 3 e a Atividade 2 | Mensagem "gravado no cofre"; valor ausente da saída e do histórico |
| Contraste com a sua conta | Etapa 4 e a Atividade 3 | Comparação de cada operação com seus papéis; com os papéis do exercício, 2 linhas `[OK]` e 3 `[FALHA]` |
| Identidade da aplicação | Etapa 5 e a Atividade 4 | Credencial no cofre; datas de validade do Entra ID e do cofre conferidas separadamente |
| Papéis da aplicação | Etapa 6 | Duas atribuições para o service principal, nos escopos da busca e dos modelos |
| Cinco operações da aplicação | Etapa 7 e as Atividades 5 e 6 | 5 linhas `[OK]`, código 0: 2 operações necessárias permitidas e 3 proibidas negadas (HTTP 403); resultado limitado às cinco tentativas, acompanhado da revisão dos papéis |
| Limpeza | Etapa 8 | Papéis, registro e service principal ausentes; cofre excluído e expurgado; recursos preexistentes preservados |

Antes de encerrar, registre em local privado o grupo de recursos, os nomes da busca, dos modelos e do cofre, o ID da aplicação e a decisão de manter, pausar ou remover os recursos. Ao compartilhar evidências, remova das saídas do terminal os identificadores do ambiente (assinatura, tenant, aplicação e nomes de recursos) e as contas de usuário.

## Solução de problemas

| Sintoma | O que conferir | O que evitar |
| --- | --- | --- |
| `[ERRO]` "Para usar a identidade da aplicação, informe também --cofre, --id-da-aplicacao, --tenant-id" (código 1) | Informe o que a mensagem lista. O ID do tenant vem de `az account show`, e o ID da aplicação é o `appId` da Etapa 5 | Colar o ID de objeto no lugar do ID da aplicação |
| `[ERRO]` "Envie o segredo pela entrada padrão..." (código 1) | Use o `|`: `$segredo \| python scripts\guardar_segredo.py ...` | Digitar o segredo no terminal |
| `[ERRO]` "A variável de ambiente ... está vazia ou não existe nesta sessão do terminal" (código 1) | A opção `--origem variavel` lê uma variável que precisa existir na sessão | Gravar o valor em um arquivo para "resolver" |
| `[ERRO]` "O segredo '...' não existe no cofre '...'" (código 2) | O nome do segredo (`--nome-do-segredo`) e se a Etapa 3 ou 5 gravou o segredo | Recriar o cofre |
| `[ERRO]` "O segredo '...' expirou em AAAA-MM-DD" (código 2) | Gere uma nova credencial e guarde-a de novo (Etapa 5) | Estender a validade sem trocar o segredo |
| `[ERRO]` "A identidade usada não tem permissão de dados no cofre" (código 2) | O papel `Key Vault Secrets Officer` (guardar) ou `Key Vault Secrets User` (ler) no cofre. Ser Owner não basta, e um papel novo pode levar alguns minutos para valer | Conceder o papel no grupo ou na assinatura inteira |
| `[ERRO]` "Não foi possível conectar ao cofre '...'" (código 2) | Nome e existência do cofre. Se foi excluído, confira a retenção e a possibilidade de expurgo | Criar outro cofre com o mesmo nome sem conferir o estado anterior |
| `[ERRO]` "O Microsoft Entra ID recusou o segredo da aplicação (AADSTS7000215...)" (código 2) | Se o cofre guarda o valor do segredo, e não o ID dele, e se a credencial não foi trocada depois de guardada | Gerar credenciais em série sem apagar as antigas |
| `[ERRO]` "O Microsoft Entra ID não encontrou a aplicação neste tenant (AADSTS700016)" (código 2) | `--id-da-aplicacao` deve ser o `appId`, e `--tenant-id`, o tenant onde a aplicação foi criada | Usar o ID de objeto do service principal |
| `[FALHA]` "PRIVILÉGIO DE MENOS" logo depois da Etapa 6 | Papéis e escopos atribuídos; aguarde alguns minutos se as atribuições forem recentes | Conceder papéis maiores para "resolver" |
| `[FALHA]` "PRIVILÉGIO DEMAIS" na conferência da aplicação | Os papéis e escopos no Azure Portal ou em `az role assignment list --assignee <ID-DE-OBJETO>`; a aplicação do exercício usa consulta ao índice e uso de modelos | Remover a tentativa do verificador |
| `az ad app create` recusado por privilégios insuficientes | O tenant não deixa o seu usuário registrar aplicações [2]. Peça a quem administra o tenant | Usar a credencial de outra pessoa |
| O valor de um segredo apareceu em arquivo, histórico, chat ou saída | Trate a credencial como vazada: exclua-a (`az ad app credential delete`), gere outra e guarde-a de novo | Apagar só o arquivo ou a linha do histórico |
| O Azure informa que o nome do cofre já está em uso depois de excluí-lo | O cofre excluído reserva o nome durante a retenção: expurgue-o (Etapa 8.2) [6]. Se a proteção contra expurgo estiver ligada, só depois do fim da retenção; nesse caso, use outro nome (`--parameters nomeCofre=<outro-nome>`) | Trocar a configuração do cofre para "contornar" |
| Erros dos desafios anteriores (login, tenant, papéis, deployment, cota) | [Solução de problemas do Desafio 03](03-responder-com-fontes.md#solução-de-problemas) | Pular a conferência |

Se precisar de ajuda, consulte os [canais e limites do suporte](../../SUPPORT.md). Não conceda papéis,
altere políticas corporativas ou desative controles como tentativa de diagnóstico.

## Custos, pausa e limpeza

O uso do Copilot segue o plano da sua conta e as regras de consumo dele, separadamente da assinatura Azure.

**O que gera custo neste desafio:** o Key Vault, que cobra por operação [10], e os tokens das perguntas feitas como aplicação (Etapa 7). O serviço de busca dos desafios anteriores continua cobrando por hora enquanto existir. O registro da aplicação e o service principal são objetos do Microsoft Entra ID, e não recursos do Azure cobrados por este desafio; confira as regras e a licença do seu tenant. Os custos em dinheiro não foram medidos, e os preços variam por região e data; consulte os [preços atuais do Key Vault](https://azure.microsoft.com/en-us/pricing/details/key-vault/) [10].

**Pausa e limpeza.** Para encerrar o exercício, remova as atribuições e o registro da aplicação pela
Etapa 8.1 e exclua e expurgue o cofre pela Etapa 8.2. A data de expiração limita a duração da credencial;
a limpeza encerra o ciclo dos objetos que você criou.

Excluir o grupo pelo [Desafio 02](02-indexar-documentos.md#custos-pausa-e-limpeza) também exclui o cofre,
mas mantém seu nome reservado durante a retenção, salvo expurgo permitido [6].
Consulte `az keyvault list-deleted` e trate apenas o cofre deste exercício, preservando os demais.

## Situação da validação

Data de referência: 9 de outubro de 2026. O registro detalhado, com a matriz de testes, o que foi e o que não foi executado e as observações de operação, está em [docs\validacao\l100-07-identidade-da-aplicacao.md](../../docs/validacao/l100-07-identidade-da-aplicacao.md).

As execuções Azure registradas usaram a versão anterior, com nome fixo. A
[correção posterior do verificador](../../docs/validacao/l100-07-identidade-da-aplicacao.md#correção-posterior-do-verificador-11-de-outubro-de-2026),
de 11 de outubro de 2026, foi conferida apenas por testes locais com dublês; o mantenedor não
autorizou novas operações Azure nesta rodada.

**Versões testadas:** Windows, Python 3.12.10, Azure CLI 2.89.0, `azure-keyvault-secrets` 4.11.3, `azure-identity` 1.26.0 e as bibliotecas dos desafios anteriores.

| Item | Situação | Detalhe |
| --- | --- | --- |
| Etapas 2 a 4 e 8.2 (cofre, segredo, conferência com a sua conta e limpeza) | Concluído | Executadas em PowerShell 7.6, em `brazilsouth`, sobre o ambiente dos Desafios 01 a 03 |
| Etapas 5 a 7 e 8.1 (service principal, papéis e execução como aplicação) | Concluído | Identidade temporária e dois papéis conferidos; 5 operações aprovadas, com 3 recusas HTTP 403; pergunta respondida com 2 citações literais; credencial, papéis e identidade removidos |
| Scripts e testes automáticos da versão inicial (sem Azure) | Concluído | Testes aprovados, com 36 casos novos em `test_identidade.py`, em 9 de outubro de 2026 |
| Correção do verificador (nome aleatório e alcance das mensagens) | Conferida localmente | 41 testes do módulo `test_identidade` aprovados com dublês, em 11 de outubro de 2026 |
| Verificador corrigido no Azure | Não executado | O alvo aleatório não foi reconferido no serviço; uma nova execução exige autorização específica |
| Links, âncoras, URLs e referências dos guias | Concluído | Nenhum link ou âncora inválido |
| Aprovação do conteúdo dos documentos sintéticos | Confirmada | Pelo mantenedor, em 9 de outubro de 2026; registro no inventário |
| Aprovação do texto, do código e dos resultados | Confirmada | Pelo mantenedor, em 9 de outubro de 2026; execução e limpeza descritas no registro |
| Outros ambientes: macOS, Linux, WSL (Windows Subsystem for Linux), Python diferente do 3.12 e Windows PowerShell 5.1 | Pendente | Executar os comandos do guia nesses ambientes e registrar as diferenças |
| Interações com o Copilot: prompts do guia, exemplo de pedido de mudança e modo construtor | Pendente | Executar no VS Code e registrar as respostas |
| Custo | Parcial | Consulta ao Cost Management executada; retorno consolidado apenas de Storage. O total dos serviços e a separação desta rodada continuam pendentes, conforme o registro |

**Autoria.** Código, testes e texto produzidos com apoio de inteligência artificial (IA), com Claude
Sonnet 5.5 no GitHub Copilot CLI; o Astra estava indisponível. Revisão editorial por GPT-6.1 Sol, em
9 de outubro de 2026. Os modelos de autoria e revisão são independentes do modelo escolhido no Copilot
e dos deployments da aplicação Azure (`text-embedding-3-small` e `gpt-5.4-mini`).

Revisão editorial e técnica por **gpt-6-astra (Astra)**, em 11 de outubro de 2026: leitura integral,
conferência de referências locais e confronto com a implementação. Não houve nova execução Azure;
autoria, revisões anteriores, aprovação histórica e limites das medições permanecem preservados.
A correção posterior do verificador substituiu o alvo fixo por um nome aleatório e delimitou as
mensagens às cinco tentativas, sem repetir a execução histórica no Azure.

Correção do verificador: Claude Sonnet 5.5, em 11 de outubro de 2026; texto desta atualização:
GPT-6.1 Sol, com Astra indisponível.

## Glossário

| Termo | Significado no exercício |
| --- | --- |
| Microsoft Entra ID | Serviço de identidades da Microsoft, onde ficam usuários, aplicações e service principals |
| Tenant | O diretório do Microsoft Entra ID de uma organização; tem um ID próprio |
| Registro de aplicação | Cadastro de uma aplicação no tenant, que dá a ela um ID e permite criar credenciais |
| Service principal | Identidade de uma aplicação em um tenant, a que os papéis do Azure são atribuídos |
| ID da aplicação (`appId`) | Identificador do registro da aplicação; não é segredo, mas é do seu ambiente |
| ID de objeto | Identificador do service principal, usado para conceder papéis; é diferente do ID da aplicação |
| Identidade gerenciada | Service principal cuja credencial o Azure cria, guarda e renova para um recurso em nuvem |
| Segredo (da aplicação) | Senha longa do service principal; quem a tem age como a aplicação até ela expirar |
| Azure Key Vault (cofre) | Serviço que guarda segredos, chaves e certificados e controla quem os lê |
| RBAC | *Role-Based Access Control*: controle de acesso por papéis atribuídos a uma identidade em um escopo |
| Papel | Conjunto de permissões, como `Search Index Data Reader` |
| Escopo | O recurso, o grupo ou a assinatura em que um papel vale |
| Privilégio mínimo | Dar a uma identidade só o que a tarefa dela exige, no menor escopo possível |
| Privilégio demais | Uma permissão que a identidade tem e não deveria ter |
| Privilégio de menos | Uma permissão de que a identidade precisa e não tem |
| Plano de dados | Operações sobre o conteúdo de um recurso (ler um segredo, consultar um índice), controladas por papéis próprios; difere do plano de gerenciamento, que cria e configura o recurso |
| Exclusão reversível | Retenção, por alguns dias, de um cofre ou segredo excluído, que pode ser recuperado |
| Expurgo | Exclusão definitiva de um cofre ou segredo que estava em exclusão reversível |
| Pipe (`|`) | Encadeamento da saída de um comando na entrada de outro, sem passar por arquivo ou argumento |
| HTTP 403 | Resposta do serviço quando a identidade existe, mas não tem permissão para a operação |
| HTTP 404 | Resposta de alvo não encontrado; na tentativa de exclusão, quando vem depois da autorização, conta como operação permitida |
| `ClientSecretCredential` | Classe do SDK do Azure que autentica um service principal com tenant, ID da aplicação e segredo |
| Tentativa de exclusão | Pedido de escrita autenticado a um índice de nome aleatório que não existe, diferente do índice informado em `--indice`; confere a permissão sem remover um índice real e é apenas uma das cinco tentativas |

## Referências

Fontes oficiais 1 a 10 consultadas em 9 de outubro de 2026; fonte 11 consultada para a atualização de 11 de outubro de 2026. Nomes de interface, limites, preços e disponibilidade mudam: confira a versão atual antes de aplicar.

1. [Aplicativos e service principals no Microsoft Entra ID](https://learn.microsoft.com/en-us/entra/identity-platform/app-objects-and-service-principals).
2. [Registrar um aplicativo do Microsoft Entra e criar um service principal](https://learn.microsoft.com/en-us/entra/identity-platform/howto-create-service-principal-portal).
3. [Identidades gerenciadas para recursos do Azure](https://learn.microsoft.com/en-us/entra/identity/managed-identities-azure-resources/overview).
4. [Conceder acesso a aplicações em um cofre de chaves com o Azure RBAC](https://learn.microsoft.com/en-us/azure/key-vault/general/rbac-guide).
5. [Proteger o Azure Key Vault](https://learn.microsoft.com/en-us/azure/key-vault/general/best-practices).
6. [Exclusão reversível do Azure Key Vault](https://learn.microsoft.com/en-us/azure/key-vault/general/soft-delete-overview).
7. [Funções internas do Azure](https://learn.microsoft.com/en-us/azure/role-based-access-control/built-in-roles).
8. [Conectar-se ao Azure AI Search com funções do Azure](https://learn.microsoft.com/en-us/azure/search/search-security-rbac).
9. [Autenticar aplicativos Python no Azure durante o desenvolvimento local com service principals](https://learn.microsoft.com/en-us/azure/developer/python/sdk/authentication/local-development-service-principal).
10. [Preços do Azure Key Vault](https://azure.microsoft.com/en-us/pricing/details/key-vault/).
11. [Geração de texto hexadecimal aleatório com `secrets.token_hex`, no Python](https://docs.python.org/3/library/secrets.html#secrets.token_hex).

O comportamento corrigido está no [verificador](../../scripts/verificar_identidade.py) e nos
[testes da identidade](../../tests/test_identidade.py). O alcance da conferência local e o histórico
Azure estão na [correção posterior registrada](../../docs/validacao/l100-07-identidade-da-aplicacao.md#correção-posterior-do-verificador-11-de-outubro-de-2026).

As atribuições do contexto fictício estão em [NOTICE.md](../../NOTICE.md). O texto deste guia está sob a licença Creative Commons Atribuição 4.0 (CC BY 4.0; veja [LICENSE](../../LICENSE)).
