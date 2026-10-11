# L300 — Desafio 01: reproduzir a base e delimitar a migração

[Início do laboratório](../../README.md) · [Desafio 02](02-atualizar-base.md)

| Item | Descrição |
| --- | --- |
| Situação | Preparação local e reconstrução da base Azure conferidas em grupo temporário autorizado |
| Público | Pessoas de Atendimento, operações, arquitetura e desenvolvimento que concluíram o L200 |
| Resultado | Revisão identificada, inventário de dependências e plano de migração que preserva o L200 |
| Custo | As verificações locais não chamam modelos. Uma reconstrução Azure tem os custos dos recursos e precisa de orçamento |

## Conteúdo

- [Cenário](#cenário)
- [Objetivos](#objetivos)
- [Artefatos e disponibilidade](#artefatos-e-disponibilidade)
- [Tecnologias e conceitos](#tecnologias-e-conceitos)
- [Pré-requisitos](#pré-requisitos)
- [Etapa 1: abrir a versão e conferir alterações](#etapa-1-abrir-a-versão-e-conferir-alterações)
- [Etapa 2: inventariar dependências e destinos](#etapa-2-inventariar-dependências-e-destinos)
- [Etapa 3: separar as fases de migração](#etapa-3-separar-as-fases-de-migração)
- [Como pedir uma mudança ao Copilot no VS Code](#como-pedir-uma-mudança-ao-copilot-no-vs-code)
- [Conferência do resultado](#conferência-do-resultado)
- [Solução de problemas](#solução-de-problemas)
- [Custos, pausa e limpeza](#custos-pausa-e-limpeza)
- [Situação da validação](#situação-da-validação)
- [Glossário](#glossário)
- [Referências](#referências)

## Cenário

No piloto fictício de 2025, Beatriz Torres quer restringir materiais de operação ao Atendimento e
atualizar a aplicação com um procedimento repetível. A equipe parte do chat L200; Teresa Moura exige
que o acesso e a infraestrutura evoluam sem alterar as regras gerais já usadas pelo curso.

O L300 conserva os resultados anteriores. O classificador do L200 teve duas divergências no novo
conjunto final de 18 perguntas, conforme o
[registro da correção L200](../../docs/validacao/l200-correcao-v2.md). Este nível trata acesso, rede e operação; a qualidade das respostas
continua experimental, com essas limitações registradas.

## Objetivos

1. Identificar a versão de referência e preservar alterações locais.
2. Registrar os recursos que podem ser reaproveitados e os objetos novos.
3. Separar criação de rede, migração da aplicação e fechamento de acesso público.
4. Preparar verificações locais antes de decidir sobre uma execução Azure.

Novos modelos, dados reais e decisões individuais de cobertura permanecem fora deste desafio.

## Artefatos e disponibilidade

| Artefato disponível | Uso |
| --- | --- |
| [Pré-release L200 corrigida](https://github.com/EdneiMonteiro/vareleira-rag/releases/tag/v0.2.1-l200) | Referência de código e resultados preservados |
| [Roteiro L300](../../docs/roteiro-l300.md) | Fronteiras, sequência e critérios |
| [Base Bicep L100](../../infra/main.bicep) | Armazenamento, busca e modelos |
| [Infraestrutura L200](../../infra/l200.bicep) | Chat, identidades, registro e logs da configuração anterior |
| [Inventário L100](../../dados/l100/inventario.json) | Fontes sintéticas cujo conteúdo permanece inalterado |
| [Chat](../../scripts/lab_chat.py) e [política](../../scripts/lab_politica.py) | Comportamento reaproveitado |
| [Infraestrutura L300](../../infra/l300.bicep) e [parâmetros](../../infra/levels/l300.bicepparam) | Rede, aplicação e isolamento em fases independentes |
| [Manifesto L300](../../dados/l300/permissoes-documentais.json) | Classificação adicional das fontes sintéticas |
| [Plano local](../../scripts/operar_l300.py) | Revisão de fases, guardas e evidências declaradas |

Os arquivos de infraestrutura descrevem o que será implantado no destino autorizado.
Os ambientes de validação anteriores foram removidos; a equipe precisa reconstruir a base
ou identificar recursos próprios compatíveis.

## Tecnologias e conceitos

Uma **migração** muda a configuração mantendo um caminho de retorno. A versão anterior e a nova
podem coexistir durante a conferência, com custos simultâneos.

**Infraestrutura como código** registra a configuração em arquivos. **Bicep** é a linguagem usada
para descrever recursos Azure. A compilação local confere sintaxe e tipos; o Azure Resource Manager
(ARM), serviço de administração Azure, calcula mudanças previstas por `what-if` [1].

Uma **rede virtual** fornece conectividade entre recursos. Um **endpoint privado** recebe endereço
nessa rede para alcançar um serviço. A aplicação Container Apps precisa de um ambiente criado com
essa integração; o tipo de rede de um ambiente existente não pode ser trocado [2].

## Pré-requisitos

Abra a pasta completa no Visual Studio Code (VS Code), este guia na prévia Markdown e
**Terminal > New Terminal**, com PowerShell 7. Selecione o interpretador `.venv` em
**Python: Select Interpreter**. Python 3.12, Git e Azure CLI, interface de linha de comando do Azure,
são as ferramentas de referência.

A leitura e os testes locais dispensam identidade Azure. Para executar etapas externas, confirme
assinatura ativa, tenant, grupo, região, papéis, destino dos dados, efeitos e orçamento.
O tenant é o diretório de identidades; permissões de implantação, dados e atribuição de papéis
são verificações diferentes.

## Etapa 1: abrir a versão e conferir alterações

1. Abra o repositório completo.
2. Confira a revisão e as alterações locais.
3. Compare a entrega L300 com a base L200, sem descartar arquivos.

```powershell
git --no-pager status --short
git --no-pager log -1 --oneline
git --no-pager diff --name-only 5af7612
git ls-files --others --exclude-standard
```

**Resultado esperado:** revisão identificada e lista de alterações compreensível. O commit
`5af7612` referencia o fechamento L200 e sua publicação; os resultados estão nos registros
versionados. Preserve alterações de outras atividades antes de trocar branch ou aplicar patches.

Confira as bibliotecas do ambiente virtual existente:

```powershell
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -m pip check
```

Se a instalação estiver incompleta, use as dependências L300:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements\l300.txt
```

Esse comando instala bibliotecas no ambiente local e pode acessar seus servidores de pacotes.
O arquivo L300 reutiliza os requisitos L200. A rodada de integração usou as bibliotecas já
disponíveis, sem reinstalá-las. Instalar a extensão Python no VS Code não instala o interpretador.

### Prompt para o Copilot: conferir a base

Anexe este guia, o roteiro L300, `infra\l200.bicep` e o inventário:

```text
Explique a migração L200 para L300 para alguém que não programa.
Liste o que permanece, o que muda e o que precisa ser criado separadamente.
Identifique os resultados históricos que não devem ser reescritos.
Separe testes locais, leituras Azure e alterações externas.
Não edite arquivos, execute comandos, peça credenciais ou provisione recursos.
```

**Conferência:** a proposta deve conservar fontes, modelos e política, criar outro ambiente
Container Apps para a rede e colocar o fechamento público depois das provas de conectividade.
O novo contêiner precisa de uma imagem construída a partir do código L300: reutilize o registro,
o Dockerfile e o processo de construção, não a imagem publicada antes da autorização documental.

## Etapa 2: inventariar dependências e destinos

Registre, em local privado, assinatura, tenant, grupo, nomes, região, versões, proprietário e
responsável por cada autorização. Use nomes recebidos do seu ambiente, nunca os do instrutor.

| Dependência | Reaproveitamento | Cuidado |
| --- | --- | --- |
| Armazenamento e modelos | Recursos existentes podem ser mantidos | Preservar configuração; aprovar fechamento público |
| Serviço de busca | Índices L100/L200 podem coexistir com L300 | Conferir camada, região e suporte ao caminho privado |
| Documentos L100 | Mesmos textos e hashes | Classificação de acesso é metadado adicional em cópias L300 |
| Identidade gerenciada, registro e logs | Reutilizar quando compatíveis e autorizados | Conferir escopos, retenção e custo |
| Ambiente e aplicação Container Apps | Nova configuração L300 em recursos separados | Preservar L200 para retorno |
| Login e automação | Configuração explícita por identidade e origem | Papéis de aplicação e federação são autorizações reais |

Se a base estiver ausente, a reconstrução usa os procedimentos L200 antes da migração.
A rodada Azure reconstruiu a base em um grupo exclusivo: três fontes, 54 trechos L100
e 21 trechos L200, com hashes conferidos. O [registro Azure](../../docs/validacao/l300-azure-validacao.md)
identifica a execução e a limpeza, sem publicar destinos privados.
Na sequência do curso, os Desafios 02 e 03 começam por manifesto e testes locais.
Depois de preparar a rede e aprovar as conexões no Desafio 04, retorne ao Desafio 02 para
carga e ingestão Azure. A nova aplicação é publicada somente com índice e imagem L300 conferidos.

## Etapa 3: separar as fases de migração

1. Prepare rede, resolução de nomes e conexões da ingestão.
2. Implante a nova aplicação, primeiro com ingresso fechado.
3. Confira autenticação e autorização documental por perfil.
4. Demonstre consulta e ingestão no caminho privado.
5. Feche o acesso público dos serviços de dados após aprovar as evidências.

Confira o plano declarativo, sem acesso à nuvem:

```powershell
.\.venv\Scripts\python.exe scripts\operar_l300.py --etapa plano --fase todas
```

O plano lista o efeito esperado de cada fase. Na execução Azure, reveja também o `what-if`,
incluindo os itens `Unsupported`, mudanças que o ARM não conseguiu calcular [1].
Registre o efeito pendente e sua revisão antes de aplicar.

**Resultado esperado:** sequência com alvos, condições de avanço, custo e retorno. Uma falha
na resolução de nomes, nas permissões ou na ingestão interrompe o fechamento público; o procedimento não cria papéis maiores
como correção automática.
O chat conserva o fluxo fixo de recuperação, geração e política do L200. A migração ativa
explicitamente a autorização documental com `VARELEIRA_EXIGIR_ACESSO_DOCUMENTAL=true`,
autenticação na borda e índice L300; sem essa opção, o padrão L200 permanece.
Conserve também os deployments `embeddings` (`text-embedding-3-small`, versão `1`, 1.536 dimensões)
e `geracao` (`gpt-5.4-mini`, versão `2026-03-17`), instâncias nomeadas dos modelos reutilizados.

## Como pedir uma mudança ao Copilot no VS Code

Delimite o arquivo e o comportamento antes de pedir implementação. Para alterar o plano de migração,
anexe o Bicep e preserve nomes, região, camadas e proteções existentes.
Revise o diff em **Source Control** e execute os testes relacionados antes de aplicar qualquer
alteração Azure.

## Conferência do resultado

Execute a suíte local do projeto, sem Azure:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Confira também o inventário original sem gravar alterações:

```powershell
.\.venv\Scripts\python.exe scripts\atualizar_hashes_inventario.py
```

**Resultado esperado:** testes aprovados e três documentos L100 sem mudanças.
O número de casos aprovados fica no registro local, separado das medições Azure.

## Solução de problemas

| Sintoma | Ação |
| --- | --- |
| Base Azure ausente | Reproduza os arquivos L200 em destino autorizado; não suponha recursos do instrutor |
| Alterações locais inesperadas | Preserve e revise os arquivos; suspenda a migração quando houver conflito |
| Proposta de trocar rede do ambiente atual | Crie ambiente separado e mantenha a aplicação anterior como retorno |
| Permissões amplas sugeridas | Identifique operação e escopo; solicite somente a autorização necessária |
| Faltam provas do caminho privado | Complete a conferência dentro da rede antes de bloquear acesso público |

## Custos, pausa e limpeza

O inventário local não cria custo de serviços. Rede privada, recursos gerenciados Container Apps,
busca, modelos, imagens e logs têm cobranças próprias [2][3]. Registre orçamento e duração
antes de executar uma fase de migração.

Preserve os arquivos e o inventário para os desafios seguintes. A limpeza remove apenas objetos
e identidades criados para o nível, após conferir seus proprietários e as dependências preservadas.

## Situação da validação

A base versionada L200 foi conferida e o L300 foi preparado em branch local separada.
Comandos de versão, dependências, manifesto e plano foram executados localmente.
A autorização posterior permitiu reconstruir a base e testar a migração no Azure,
com grupo exclusivo, região `brazilsouth` e teto total de US$90.
Isso não autoriza novos destinos ou execuções do aluno. GitHub Actions e federação
não foram ativados.
O [registro local L300](../../docs/validacao/l300-validacao-local.md) identifica comandos,
correções e verificações anteriores; o [registro Azure](../../docs/validacao/l300-azure-validacao.md)
conserva os resultados da rodada externa e seu encerramento.

## Glossário

| Termo | Significado |
| --- | --- |
| Migração | Alteração de configuração com continuidade e retorno definidos |
| ARM e Bicep | Administração dos recursos Azure e linguagem de infraestrutura |
| Endpoint privado | Interface de acesso ao serviço com endereço na rede virtual |
| Tenant | Diretório de identidades |
| Identidade gerenciada | Identidade com credencial administrada pelo Azure |
| `what-if` | Previsão de mudanças de implantação |
| Diff | Comparação de alterações nos arquivos |

## Referências

1. [What-if e seus limites](https://learn.microsoft.com/en-us/azure/azure-resource-manager/bicep/deploy-what-if).
2. [Rede em Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/networking).
3. [Recursos gerenciados e sub-redes de Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/custom-virtual-networks).

Texto por GPT-6.1 Sol; código e testes por Claude Sonnet 5.5.
Astra indisponível; autoria, modelo do Copilot do aluno e deployments da aplicação são escolhas distintas.

Revisão documental: gpt-6-astra (Astra), em 11 de outubro de 2026, por leitura integral e
conferência local dos artefatos; sem nova execução Azure.
