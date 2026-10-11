# L300 — Desafio 05: automatizar verificações e preparar a implantação manual

[Início do laboratório](../../README.md) · [Desafio 04](04-dependencias-privadas.md) · [Desafio 06](06-conferir-operacao.md)

| Item | Descrição |
| --- | --- |
| Situação | Workflows e operação validados localmente. Publicação e integração contínua estão autorizadas na revisão atual, sem resultado remoto anunciado aqui; implantação Actions, federação e runner privado continuam não executados |
| Público | Operações, arquitetura e desenvolvimento, com apoio dos administradores do GitHub e do Azure |
| Resultado | Verificações sem credencial em propostas de mudança e implantação manual delimitada por origem, fase e destino |
| Custo | Testes locais não chamam Azure. Execuções Actions usam cotas próprias; runner e infraestrutura Azure têm custos separados |

## Conteúdo

- [Cenário](#cenário)
- [Objetivos](#objetivos)
- [Artefatos e disponibilidade](#artefatos-e-disponibilidade)
- [Tecnologias e conceitos](#tecnologias-e-conceitos)
- [Pré-requisitos](#pré-requisitos)
- [Etapa 1: conferir a separação dos workflows](#etapa-1-conferir-a-separação-dos-workflows)
- [Etapa 2: preparar ambiente e confiança federada](#etapa-2-preparar-ambiente-e-confiança-federada)
- [Etapa 3: revisar o plano antes de aplicar](#etapa-3-revisar-o-plano-antes-de-aplicar)
- [Como pedir uma mudança ao Copilot no VS Code](#como-pedir-uma-mudança-ao-copilot-no-vs-code)
- [Conferência do resultado](#conferência-do-resultado)
- [Solução de problemas](#solução-de-problemas)
- [Custos, pausa e limpeza](#custos-pausa-e-limpeza)
- [Situação da validação](#situação-da-validação)
- [Glossário](#glossário)
- [Referências](#referências)

## Cenário

No piloto fictício de 2025, Beatriz Torres precisa saber qual versão foi conferida antes de
alterar o chat. A equipe quer executar testes em cada proposta de mudança e separar essa atividade
da implantação, que acessa a assinatura e a rede privada.

O fluxo usa arquivos versionados e aprovação administrativa. Ele conserva a política das respostas
e os resultados L200; implantar uma nova revisão não encerra a avaliação de negócio.

## Objetivos

1. Executar testes e compilação sem identidade Azure nas propostas de mudança.
2. Restringir a implantação a uma revisão confiável e a acionamento manual.
3. Usar credenciais de curta duração, com destino e permissões delimitados.
4. Preservar o plano bruto em local privado e publicar somente seu resumo sanitizado.

Este desafio prepara os arquivos. Ativar federação, configurar proteções e implantar requer
autorizações próprias; essas operações externas não fazem parte da validação local desta rodada.
Em 11 de outubro de 2026, o mantenedor autorizou publicação, propostas de mudança, integração
contínua e pré-releases, publicações preliminares versionadas. O coordenador executa essas etapas
separadamente. A autorização não comprova execução nem estende o escopo à implantação por
Actions com federação de identidade ou ao login humano. Os registros das rodadas anteriores permanecem inalterados.

## Artefatos e disponibilidade

| Artefato | Uso |
| --- | --- |
| [Workflow de validação](../../.github/workflows/validar.yml) | Verificações em runner hospedado, sem login Azure |
| [Workflow de implantação](../../.github/workflows/l300-implantar.yml) | Acionamento manual, ambiente de implantação e fase |
| [Operação L300](../../scripts/operar_l300.py) | Guardas de plano, evidências e saída pública |
| [Bicep L300](../../infra/l300.bicep) | Infraestrutura por fase |
| [Testes de operação](../../tests/test_operacao_l300.py) e [workflows](../../tests/test_workflows.py) | Decisões locais e estrutura dos arquivos |

O helper lê arquivos e variáveis, sem acessar GitHub ou Azure. A ativação administrativa
fica separada da disponibilidade dos arquivos.

## Tecnologias e conceitos

Uma **pull request (PR)** é uma proposta de mudança a ser revisada. A **integração contínua (CI)**
executa verificações sobre essa proposta. A **entrega contínua (CD)** prepara a implantação de
uma versão aprovada; neste laboratório, a aplicação da mudança é manual.

**GitHub Actions** executa um **workflow**, sequência de trabalhos definida em YAML
(*YAML Ain't Markup Language*), formato
de configuração legível. Cada trabalho roda num **runner**, computador executor.
Um runner **self-hosted** pertence ao ambiente administrado pela equipe.

**OpenID Connect (OIDC)** permite que o GitHub obtenha acesso temporário no Azure com uma relação
de confiança previamente configurada [1]. A permissão `id-token: write` permite pedir o token;
os papéis Azure determinam quais operações ele autoriza.

O token contém o **subject**, campo `sub` usado para identificar sua origem. Repositórios criados
depois de 15 de julho de 2026, ou renomeados ou transferidos depois dessa data, usam o formato
imutável com identificadores de proprietário e repositório, salvo as condições indicadas pela
plataforma [1]. Confira o formato efetivo antes de criar a credencial federada.

## Pré-requisitos

Abra a pasta completa no Visual Studio Code (VS Code), selecione `.venv` e use PowerShell 7.
Os testes locais usam Python e Bicep; login Azure e execução Actions são dispensados.

Para ativação posterior, confirme revisão autorizada, ambiente GitHub, regras de aprovação,
runner privado, assinatura Azure ativa e papéis proporcionais à fase. O administrador precisa
conferir a disponibilidade das proteções no plano e na visibilidade do repositório [2].

Mantenha a configuração dos destinos fora dos arquivos públicos. A implantação recebe assinatura,
tenant, identidade e parâmetros do ambiente aprovado. O tenant é o diretório de identidades.

## Etapa 1: conferir a separação dos workflows

1. Abra os dois arquivos de workflow.
2. Confira acionadores, runner, permissões e origem do código.
3. Confira os comandos e o plano local antes de considerar a ativação remota.

```powershell
.\.venv\Scripts\python.exe scripts\operar_l300.py --help
.\.venv\Scripts\python.exe scripts\operar_l300.py --etapa plano --fase todas
.\.venv\Scripts\python.exe scripts\operar_l300.py --etapa validar --fase rede
```

O último comando valida a intenção local padrão de simulação. Com `--exigir-azure`, o helper
confere identidade, destinos e parâmetros, mas continua sem login ou alteração externa.

| Verificação | Condição esperada |
| --- | --- |
| CI de propostas de mudança | Runner hospedado; sem `id-token: write`, login Azure ou segredo de implantação |
| Implantação | Somente `workflow_dispatch`, acionador manual |
| Origem privilegiada | Revisão confiável, sem baixar e executar código de uma PR não aprovada |
| Runner privado | Reservado à implantação e à operação autorizadas |
| Credencial | OIDC no trabalho delimitado; sem segredo de cliente para autenticar o executor |
| Ações externas | Referências fixadas em commits completos, conferidos no repositório de origem |

**Resultado esperado:** os testes aprovam as guardas de configuração.
A execução do código de uma PR em runner com credenciais ou rede privada pode expor esse ambiente;
o desenho mantém os dois caminhos separados [3].

### Prompt para o Copilot: revisar a origem e os efeitos

Anexe este guia, os workflows, `operar_l300.py` e `infra\l300.bicep`:

```text
Explique os workflows de validação e implantação do L300.
Confira origem do código, permissões do token, runner, fase, destino e saída pública.
Identifique operações que exigem autorização administrativa fora do YAML.
Preserve o acionamento manual e a ausência de identidade Azure na CI.
Não execute Actions, crie ambiente, configure federação ou implante.
Não peça segredos, tokens ou saídas brutas do ambiente.
```

**Conferência:** a análise deve identificar a configuração administrativa como pendente,
mesmo quando o YAML compila e os testes passam.

## Etapa 2: preparar ambiente e confiança federada

Esta etapa é um roteiro administrativo **não executado nesta rodada**.
Ela **altera acesso no GitHub e no Azure** ao configurar proteções, confiança e papéis.

1. No GitHub, abra **Settings > Environments** e configure `vareleira-l300`.
2. Delimite as branches ou tags autorizadas, exija revisão e confira regras de autoaprovação
   e desvio administrativo conforme a política do ambiente.
3. Configure os secrets de identificadores privados e as variáveis não secretas, em escopo do ambiente.
4. No Entra ID, estabeleça a confiança para emissor, audiência e subject efetivos.
5. Conceda somente os papéis necessários e registre alvos, proprietário e prazo do acesso.

O procedimento oficial de ambientes detalha essas proteções [2].
Quando um workflow referencia um ambiente inexistente, sua execução pode criá-lo sem regras
de proteção. Configure e confira o ambiente **antes** de ativar a implantação.

Um nome de branch delimitado no arquivo é uma guarda adicional. A revisão e a proteção da origem
permanecem responsabilidades dos administradores. Um token OIDC também não concede automaticamente
acesso a dados ou aprovação de conexões privadas.

Separe a identidade de implantação do registro de login da aplicação:

| Configuração | Função e armazenamento |
| --- | --- |
| `AZURE_CLIENT_ID`, `AZURE_TENANT_ID` e `AZURE_SUBSCRIPTION_ID` | Origem e destino da implantação OIDC; IDs privados, sem segredo de cliente |
| `VARELEIRA_GRUPO_RECURSOS`, `VARELEIRA_NOME_*` e `VARELEIRA_ID_OBJETO_CARGA` | Destinos privados e identidade da carga |
| `VARELEIRA_ID_APLICACAO_LOGIN` e `VARELEIRA_ID_TENANT_LOGIN` | Registro que autentica as pessoas no chat, distinto da identidade de implantação |
| `VARELEIRA_SEGREDO_LOGIN` | Única credencial persistente usada pelo workflow; secret do ambiente protegido, somente na fase `aplicacao` |
| Camadas, réplicas, partições, regiões e ação sem login | Configuração não secreta conferida pelos validadores, recebida de `vars` |

Os IDs e nomes de destino devem usar secrets individuais do ambiente protegido para que o
runner os mascare antes de mostrar entradas de um passo. Eles continuam sendo configuração,
não senhas. O segredo de login é efêmero nos passos que validam, simulam e aplicam; o parâmetro
Bicep é `@secure()` e o provedor EasyAuth o recebe em Container Apps Secrets.
O login OIDC do executor permanece sem segredo de cliente.
Se a API (interface de programação de aplicações) do GitHub não fornecer regras e aprovação
utilizáveis, mantenha a implantação bloqueada.
A comprovação precisa dos dois registros; uma declaração do operador não substitui nenhum deles.

O workflow pressupõe imagem **construída da revisão L300** já publicada no registro
e base L200 reconstruída.
Ele não constrói a imagem, atribui papéis de aplicação ou aprova conexões privadas automaticamente.

## Etapa 3: revisar o plano antes de aplicar

**Somente leitura do Azure**, para o plano `what-if`, exige autenticação e permissões de previsão.
**[altera o Azure]**, na aplicação, exige autorização para os efeitos da fase escolhida.
Nenhuma dessas operações foi exercitada **pelo workflow de implantação** nas rodadas registradas.
Planos e implantações Azure manuais foram executados na
[rodada Azure L300](../../docs/validacao/l300-azure-validacao.md); essa evidência não valida Actions.

1. Escolha a fase e os destinos autorizados, conservando aplicação desabilitada no primeiro plano.
2. Gere o `what-if` e guarde a saída completa em local privado.
3. Confira inclusões, alterações, remoções e itens `Unsupported`, que não puderam ser calculados.
4. Confira imagem, configuração preservada e evidências exigidas pela fase.
5. Somente após revisão e aprovação, execute a aplicação prevista.

`Unsupported`, erro de previsão, remoção não autorizada ou evidência ausente interrompem o fluxo
automático. O `what-if` tem limitações e pode deixar efeitos sem previsão completa [4].
Uma aprovação baseada numa saída incompleta precisa tratar explicitamente os itens pendentes.

O resumo público deve conter contagens e resultado das guardas. IDs de recursos, configuração
antes/depois, endpoints privados, parâmetros e mensagens brutas permanecem fora do log público.
A ocultação automática de segredos no Actions tem limites; a redução dos dados publicados
é uma proteção adicional [3].
O workflow mantém o JSON (*JavaScript Object Notation*, formato de dados estruturados) bruto do
plano apenas durante o trabalho e o apaga; ele não oferece
um arquivo bruto persistente como artefato público. A captura privada para revisão manual é
um procedimento separado. `plano_sha256` compara a forma sanitizada, sem provar igualdade dos
destinos ou de todos os valores; confira os alvos privados independentemente.

Para conferir um plano bruto autorizado já capturado, somente no seu computador:

```powershell
.\.venv\Scripts\python.exe scripts\operar_l300.py --etapa sanitizar-whatif --arquivo $arquivoWhatIf --relatorio $novoRelatorio --rotulo rede
```

Defina `$arquivoWhatIf` como arquivo privado de entrada e `$novoRelatorio` como caminho novo.
O comando não acessa a nuvem e nunca sobrescreve o relatório. Um item não suportado ou uma
propriedade removida pode exigir qualificação explícita por tipo e quantidade exata; a revisão
humana deve identificar seus efeitos. Exclusão de recurso ou mudança potencial não resolvida
continua bloqueada. O hash `plano_sha256`, impressão digital do conteúdo sanitizado, permite
comparar a nova simulação com a revisada, sem identificar os recursos por seus valores.

## Como pedir uma mudança ao Copilot no VS Code

Delimite o comportamento e os arquivos. Para incluir outra fase, peça validação de entrada,
permissões mínimas, simulação e teste de recusa correspondente.
Revise o diff em **Source Control** e confira o commit de cada ação externa [3].
Guarde os valores do ambiente nas configurações autorizadas, sem colá-los no chat.

## Conferência do resultado

Execute os testes locais dos workflows e da operação:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_workflows.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_operacao_l300.py
```

| Conferência local | Evidência |
| --- | --- |
| Parsing de YAML e testes | Estrutura esperada, acionadores e permissões delimitados |
| Plano com dublê | Erro, remoção ou efeito desconhecido impedem aplicação |
| Sanitização | Saída pública sem IDs, credenciais, pergunta ou conteúdo bruto |
| Infraestrutura | Build e lint locais por fase, com acesso público conservado na preparação |

A validação real precisa conferir obtenção do token, regras do ambiente, papel efetivo, rede
do runner e execução no destino. Esses itens ficam no registro de nuvem autorizado.
Os testes de YAML analisam os arquivos; a execução da matriz Windows/Linux em Actions
permanece pendente.

## Solução de problemas

| Sintoma | Diagnóstico e ação |
| --- | --- |
| Login federado recusado | Confira issuer, audience e subject efetivos; preserve a recusa |
| Ambiente existe sem revisor | Suspenda implantação e configure as proteções antes de ativá-la |
| Runner privado recebe tarefa de PR | Corrija o acionador e o isolamento; não execute o código não confiável |
| Plano contém `Unsupported` | Revise os efeitos não calculados; não registre aprovação automática |
| Destino não informado | Complete as variáveis autorizadas; não use o destino do instrutor |
| Log inclui configuração sensível | Interrompa a publicação, trate a exposição e reveja a sanitização |

## Custos, pausa e limpeza

Testes no computador usam recursos locais. Actions tem cotas e cobrança conforme o plano;
runner privado, rede e serviços Azure permanecem sob responsabilidade da equipe.
O modo de plano não cria os recursos previstos, mas a execução do runner tem custo próprio.

Ao encerrar uma ativação temporária, retire a confiança e os papéis criados para ela após conferir
consumidores. Preserve identidades e configurações anteriores.
Apagar um arquivo de workflow não revoga uma credencial federada já criada.

## Situação da validação

O fechamento local confere workflows, guardas, parsing (leitura da estrutura) e sanitização.
A publicação e a CI estão autorizadas para execução pelo coordenador; este guia não registra
uma execução remota nova. Ambiente protegido de implantação, confiança federada, runner privado
e implantação Actions continuam não executados e exigem suas decisões e validação próprias.
Os resultados locais e as limitações da passagem
de parâmetros são registrados separadamente.
Consulte o [registro local L300](../../docs/validacao/l300-validacao-local.md) para os comandos
conferidos e as operações externas pendentes.

## Glossário

| Termo | Significado |
| --- | --- |
| PR, CI e CD | Proposta de mudança, integração contínua e preparação da entrega |
| Workflow e YAML | Sequência de trabalhos e formato de sua configuração |
| Runner | Computador executor de um trabalho |
| OIDC | Protocolo de identidade usado para obter acesso temporário |
| Subject | Campo do token que identifica a origem para a relação de confiança |
| Credencial federada | Configuração que aceita tokens de uma origem delimitada |
| `workflow_dispatch` | Acionador manual de um workflow |
| Sanitização | Remoção ou redução de dados que não devem aparecer na saída pública |
| API e JSON | Interface entre programas e formato de dados estruturados |

## Referências

1. [OIDC do GitHub Actions com Azure](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-azure).
2. [Ambientes e proteções de implantação](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments).
3. [Uso seguro de GitHub Actions](https://docs.github.com/en/actions/reference/security/secure-use).
4. [What-if e limites de previsão](https://learn.microsoft.com/en-us/azure/azure-resource-manager/bicep/deploy-what-if).

Texto por GPT-6.1 Sol; código e testes por Claude Sonnet 5.5, com Astra indisponível.
Os modelos de autoria, do Copilot e da aplicação têm configurações e consumos separados.

Revisão documental: gpt-6-astra (Astra), em 11 de outubro de 2026, por leitura integral e
conferência local dos artefatos; sem execução Azure, GitHub Actions ou publicação nesta revisão.
