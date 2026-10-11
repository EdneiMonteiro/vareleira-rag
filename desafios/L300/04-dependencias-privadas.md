# L300 — Desafio 04: preparar rede privada sem interromper a ingestão

[Início do laboratório](../../README.md) · [Desafio 03](03-filtrar-acesso.md) · [Desafio 05](05-automatizar-entrega.md)

| Item | Descrição |
| --- | --- |
| Situação | Topologia, DNS (sistema de nomes de domínio), ingestão privada e bloqueio público conferidos no Azure autorizado |
| Público | Operações, arquitetura e desenvolvimento, com apoio do administrador de rede e dos serviços |
| Resultado | Definição de rede, resolução de nomes e conexões privadas para consulta e ingestão |
| Custo | Endpoints, resolução de nomes, recursos gerenciados e serviços existentes têm cobranças próprias; o plano precisa de orçamento |

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
| [Testes de infraestrutura](../../tests/test_infra_l300.py) | Compilação e guardas locais |
| [Roteiro L300](../../docs/roteiro-l300.md) | Critérios, custos e fronteiras |

As definições e a integração são conferidas localmente. Um plano Azure real exige assinatura,
destinos e permissões aprovados. A rodada autorizada conferiu planos e efeitos reais,
separados das definições locais no [registro Azure](../../docs/validacao/l300-azure-validacao.md).

## Tecnologias e conceitos

**Azure Private Link** permite conectar a um serviço por um **endpoint privado**, interface com
endereço na rede do consumidor. **DNS**, sistema de nomes de domínio, traduz o nome usado pela
aplicação para esse endereço [1].
Os endereços usam o protocolo de internet (IP). **HTTPS** é o protocolo web com proteção da conexão.
**Embeddings** são vetores numéricos dos textos, calculados pelo modelo de representação.

**Azure Container Apps** usa uma rede definida na criação do ambiente. O tipo de rede não pode
ser trocado depois. No ambiente com perfis de carga (*workload profiles*), a sub-rede deve ser
dedicada, delegada a `Microsoft.App/environments` e ter tamanho compatível, no mínimo `/27` [2][3].
Um endereço de rede em notação `/27` identifica um bloco; o projeto de endereçamento também
precisa considerar intervalos reservados e redes já conectadas.

A busca é um serviço separado da rede da aplicação. O indexador precisa de **conexões privadas
compartilhadas**, chamadas *shared private links*, para sua saída ao armazenamento e ao modelo [4].
O endpoint privado de entrada do Search protege a consulta recebida, não essa saída.

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

Esta etapa foi conferida no grupo temporário autorizado. Os exemplos são referências
para o destino do aluno, não comandos já executados com suas variáveis.
**[altera o Azure]** ao implantar rede, aprovar conexões e criar a aplicação.

1. Aplique apenas a fase de rede autorizada.
2. Confira o recurso de destino, o sub-recurso e a origem de cada conexão pendente.
3. O administrador aprova somente as conexões do exercício.
4. Force o indexador L300 a usar `executionEnvironment=private`.
5. Confira resolução de nomes dentro da rede e operações reais com as identidades previstas.

A fase `rede` também cria o novo ambiente e os dois papéis de dados no contêiner L300.
Confira esses efeitos e os custos antes de autorizá-la. A identidade da busca precisa estar
habilitada na base L200; registro de imagens, identidade da aplicação e logs são dependências
existentes.
Depois das aprovações, retorne ao Desafio 02 para criar e executar o pipeline privado.
Antes da fase `aplicacao`, construa uma imagem do código L300 com seu Dockerfile, usando o
[procedimento de construção L200](../L200/05-hospedar-chat.md). Escolha uma tag nova e identificável.
A imagem publicada antes do L300 não contém o controle documental e não serve para essa migração.
A construção e publicação de imagem **[altera o Azure]**. A rodada construiu a imagem L300
e uma sonda de manutenção derivada dela, mantendo uma tag própria sem sobrescrita.
O procedimento L200 vinculado deve ser usado somente para construir a imagem, não para reaplicar
a infraestrutura anterior sobre serviços isolados.

**Limite de reprodução:** o repositório fornece o Bicep e os gerenciadores, mas a sonda de
manutenção e os helpers privados usados na rodada não compõem uma receita pública executável.
`operar_l300.py` não implanta nem coleta essas provas. A reprodução integral fica bloqueada até
o responsável preparar e revisar um executor dentro da rede, com identidade, alvos e comandos
autorizados. Não invente um comando de sonda nem trate o descritor preenchido como sua execução.

A aprovação do shared private link é uma operação no recurso de destino [4].
Confira estado `Approved` e provisionamento `Succeeded` nos dois destinos.
O grupo `openai_account` é o padrão para embeddings Azure OpenAI; a combinação com o recurso
`AIServices` reaproveitado foi aceita nesta rodada e confirmada por embeddings privados.
Essa observação não garante outras regiões ou configurações. Mudar para `foundry_account` exige
rever habilidade, suporte e camada [4], sem troca automática por tentativa.

Os nomes usados pelo código continuam sendo os endpoints oficiais; as zonas privadas fornecem
endereços no contexto da rede. Evite gravar IPs no código ou editar o arquivo de hosts como solução
de produção. Confira a resolução dentro da rede e o endereço privado esperado [1].

## Etapa 4: fechar acesso público com retorno definido

**[altera o Azure]** na fase de isolamento. Confirme previamente:

| Prova | Evidência observável |
| --- | --- |
| Consulta | Chat recupera fonte autorizada e chama modelos pela rede esperada |
| Ingestão | Indexador lê cópia sintética, calcula embeddings e conclui sem falhas |
| Manutenção | Executor autorizado confere o índice e consegue operar a fonte |
| DNS | Nomes resolvem para endpoints privados no caminho autorizado |
| Negativa externa | Procedimento e identidade definidos; após isolar, conferir recusa da leitura fora da rede |
| Retorno | Configuração anterior, alvos e responsável definidos |

Uma variável declarando conectividade validada é uma guarda de execução, não uma medição.
Registre as provas que justificam habilitá-la.
Depois do isolamento, repita consulta e ingestão e execute a negativa externa;
preserve as falhas como parte do registro.
Reaplicar as definições L100 ou L200 pode reabrir o acesso público, pois elas descrevem a
configuração anterior. Esse retorno exige revisão e autorização, mesmo quando os nomes são iguais.

## Como pedir uma mudança ao Copilot no VS Code

Delimite a fase e os módulos ao pedir mudança. Mantenha os nomes e a região reais como parâmetros,
preserve o ambiente anterior e exija teste de recusa de isolamento sem evidências.
Revise o diff em **Source Control** antes de executar Bicep.
Gerar o código não autoriza alterar a rede ou aprovar uma conexão.

## Conferência do resultado

Localmente, confira tipos, dependências, valores permitidos e fases pelo compilador e pelos testes.
Na nuvem, registre as provas da tabela anterior por identidade e origem de rede.
Verificações de saúde e prontidão do chat tratam processo e inicialização; registre a consulta
e a ingestão autenticadas como provas separadas.

## Solução de problemas

| Sintoma | Diagnóstico e recuperação |
| --- | --- |
| Chat funciona, indexador falha | Confira shared private links, aprovações e ambiente de execução |
| DNS devolve endereço público dentro da rede | Confira zonas, vínculos e endpoint correto |
| Pessoa lê dados fora da rede após isolamento | Confira configuração de acesso público e alvos reais |
| L200 perde acesso depois de fechar dados | O isolamento também afeta clientes antigos; execute o plano de retorno autorizado |
| Nome existente seria recriado ou reconfigurado | Interrompa; reveja alvo e configuração completa no inventário |

## Custos, pausa e limpeza

Endpoints privados, DNS e recursos gerenciados do ambiente têm cobranças próprias.
Container Apps pode escalar a zero sem encerrar armazenamento, busca, registro, logs e rede [2][6].
O grupo gerenciado criado pela plataforma não deve ser alterado manualmente.

Preserve a rede enquanto uma aplicação depender dela. Remova alvos próprios após retirar tráfego
e conferir consumidores. Fechar o terminal não interrompe serviços hospedados.

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
| IP e HTTPS | Endereçamento de rede e protocolo web com proteção da conexão |
| VPN | Rede privada virtual para conectividade remota |

## Referências

1. [DNS de endpoints privados](https://learn.microsoft.com/en-us/azure/private-link/private-endpoint-dns).
2. [Rede e criação do ambiente Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/networking).
3. [Sub-redes e recursos gerenciados](https://learn.microsoft.com/en-us/azure/container-apps/custom-virtual-networks).
4. [Conexões privadas de saída do indexador](https://learn.microsoft.com/en-us/azure/search/search-indexer-howto-access-private).
5. [What-if e limitações de previsão](https://learn.microsoft.com/en-us/azure/azure-resource-manager/bicep/deploy-what-if).
6. [Cobrança de Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/billing).

Texto por GPT-6.1 Sol; código e testes por Claude Sonnet 5.5, com Astra indisponível.
O modelo de autoria não configura o modelo do Copilot ou os deployments Azure.

Revisão documental: gpt-6-astra (Astra), em 11 de outubro de 2026, por leitura integral e
conferência local dos artefatos; sem nova execução Azure.
