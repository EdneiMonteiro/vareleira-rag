# L300 — Desafio 03: autorizar fontes antes de gerar a resposta

[Início do laboratório](../../README.md) · [Desafio 02](02-atualizar-base.md) · [Desafio 04](04-dependencias-privadas.md)

| Item | Descrição |
| --- | --- |
| Situação | Filtros e borda autenticada conferidos no Azure com clientes temporários; login humano não executado |
| Público | Atendimento, operações, arquitetura e desenvolvimento, com apoio do administrador de identidades |
| Resultado | Cada pedido recupera somente classes documentais permitidas ao principal autenticado |
| Custo | Testes com dublês não usam Azure. Uma execução real cobra busca e modelos; papéis são concedidos somente após autorização |

## Conteúdo

- [Cenário](#cenário)
- [Objetivos](#objetivos)
- [Artefatos e disponibilidade](#artefatos-e-disponibilidade)
- [Tecnologias e conceitos](#tecnologias-e-conceitos)
- [Pré-requisitos](#pré-requisitos)
- [Etapa 1: revisar a matriz de acesso](#etapa-1-revisar-a-matriz-de-acesso)
- [Etapa 2: preparar papéis de aplicação](#etapa-2-preparar-papéis-de-aplicação)
- [Etapa 3: conferir a recusa antes dos serviços](#etapa-3-conferir-a-recusa-antes-dos-serviços)
- [Como pedir uma mudança ao Copilot no VS Code](#como-pedir-uma-mudança-ao-copilot-no-vs-code)
- [Conferência do resultado](#conferência-do-resultado)
- [Solução de problemas](#solução-de-problemas)
- [Custos, pausa e limpeza](#custos-pausa-e-limpeza)
- [Situação da validação](#situação-da-validação)
- [Glossário](#glossário)
- [Referências](#referências)

## Cenário

No piloto fictício de 2025, Beatriz Torres permite que Atendimento e corretores consultem as fontes
gerais. Um roteiro interno de operação, criado especificamente para o exercício, deve ficar restrito
ao Atendimento. O assistente não pode enviar esse roteiro ao modelo para depois tentar escondê-lo
da pessoa.

A classificação de acesso é metadado do laboratório. Ela não altera o conteúdo dos seguros nem
reescreve uma política histórica da Vareleira. Teresa Moura mantém sua responsabilidade pelas regras
gerais; a administração de acesso é uma decisão separada.

## Objetivos

1. Diferenciar autenticação de autorização documental.
2. Derivar classes permitidas de papéis reconhecidos no servidor.
3. Filtrar a consulta antes de montar o contexto do modelo.
4. Conferir identidades sem papel, campos falsificados e isolamento entre requisições.

O modelo não decide permissões. A pergunta não pode escolher o índice, o filtro ou o papel.

## Artefatos e disponibilidade

| Artefato | Uso |
| --- | --- |
| [Regras de acesso](../../scripts/lab_acesso.py) | Papéis, classes e filtro L300; integrado com o chat |
| [Manifesto L300](../../dados/l300/permissoes-documentais.json) | Classificação sintética de cada fonte |
| [Chat](../../scripts/lab_chat.py) e [servidor](../../scripts/chat_web.py) | Configuração e autorização por pedido |
| [Busca](../../scripts/lab_indexacao.py) | Filtro aplicado ao serviço, antes da seleção dos trechos |
| [Política](../../scripts/lab_politica.py) | Citações, introdução individual e avisos preservados |
| [Testes de acesso](../../tests/test_acesso.py) | Dublês e verificações negativas |

O campo de acesso precisa existir no índice L300. O servidor recusa a ativação documental
com índice de nível anterior, sem autenticação ou em modo de demonstração.

## Tecnologias e conceitos

**Autenticação** confirma a identidade. **Autorização** determina quais fontes essa identidade pode ler.
O **principal** representa a identidade recebida do provedor.

Um **papel de aplicação** do Microsoft Entra ID aparece no campo `roles` do token, comprovante
digital de autenticação, após a atribuição [1].
Uma **claim** é uma informação emitida pelo provedor nesse token, como tenant (diretório de
identidades) ou papel.
Ele é diferente de um papel Azure que permite administrar um recurso. `Vareleira.Atendimento` não
concede implantação, leitura direta de blobs ou administração de índices.

O **filtro de segurança** usa um campo filtrável do índice para excluir classes não permitidas [2].
Na busca vetorial, `preFilter` aplica a restrição durante a seleção, antes de formar os resultados
que serão usados como contexto [3]. O mesmo critério precisa valer para a busca textual e híbrida.

O cabeçalho `X-MS-CLIENT-PRINCIPAL` contém dados fornecidos pela autenticação integrada de
Container Apps, conhecida como **EasyAuth** [4]. A aplicação não verifica uma assinatura desse
cabeçalho; sua confiança depende da borda interceptar e autenticar todo o tráfego.
O contrato usa **HTTP**, protocolo de transferência de hipertexto da interface web, e **JSON**,
formato JavaScript Object Notation de dados estruturados. Campos extras no pedido são recusados.

## Pré-requisitos

Abra a pasta completa no Visual Studio Code (VS Code), selecione o Python de `.venv` e use PowerShell 7.
Conclua a classificação e a definição do índice L300 antes da execução real.
Testes locais usam dublês do índice e do provedor, sem login ou modelos.

Na nuvem, confirme assinatura Azure ativa e exija tenant correto, autenticação obrigatória,
atribuição dos papéis do exercício e
caminho único pela borda. Esses passos alteram acesso real e precisam de autorização do administrador.
O tenant é o diretório de identidades; as permissões documentais são verificadas pelos papéis
da aplicação.

## Etapa 1: revisar a matriz de acesso

Confira a classificação do manifesto com o responsável:

| Papel reconhecido | Classes permitidas |
| --- | --- |
| `Vareleira.Atendimento` | `compartilhado` e `atendimento` |
| `Vareleira.Corretor` | `compartilhado` e `corretor` |
| Ambos os papéis | União das classes permitidas |
| Nenhum papel conhecido | Recusa antes de consultar busca e modelos |

1. Mantenha as três fontes originais como compartilhadas no exercício.
2. Classifique o material interno sintético como Atendimento.
3. Interrompa a carga quando faltar classificação ou quando seu valor não for reconhecido.

O campo ausente não torna o documento público. A ausência de fonte autorizada deve produzir uma
resposta sem revelar nome ou conteúdo de um documento restrito; o tipo literal de recusa ainda
depende da classificação. Na rodada registrada, o perfil Corretor recebeu `fora_de_escopo`,
não `sem_evidencia`. Essa observação não altera o gabarito nem garante classificação correta.
O manifesto não limita documentos durante a consulta: qualquer fonte com uma classe permitida
pode ser recuperada. Restrinja também quem grava metadados e quem lê diretamente o índice.

### Prompt para o Copilot: verificar a fronteira de acesso

Anexe este guia, `lab_acesso.py`, o manifesto, `lab_chat.py` e `chat_web.py`:

```text
Explique onde o L300 autentica, autoriza, filtra e gera a resposta.
Confira se alguma busca envia documentos ao modelo antes de aplicar o filtro.
Liste as situações que devem recusar antes de embeddings, índice e geração.
Preserve o L200 quando o modo documental não estiver habilitado.
Não edite arquivos, execute Azure, atribua papéis ou abra os conjuntos finais L200.
```

**Conferência:** a proposta deve usar somente papéis verificados do servidor e classes estáticas.
Texto da pergunta não entra na expressão de permissão.

## Etapa 2: preparar papéis de aplicação

Este é um roteiro administrativo de referência, não uma etapa dos testes locais.
A rodada Azure definiu papéis e usou clientes de aplicação temporários autorizados;
não atribuiu acesso a pessoas nem executou login humano.
**[altera o Azure]**, no diretório Entra ID, ao definir ou atribuir papéis e exigir atribuição.

1. No registro da aplicação L300, defina papéis com valores exatos `Vareleira.Atendimento`
   e `Vareleira.Corretor`.
2. Escolha tipos de membros conforme o público autorizado, sem acrescentar aplicações de teste
   ou pessoas por conveniência.
3. No aplicativo empresarial, confira a exigência de atribuição e os usuários ou grupos autorizados.
4. Atribua o papel correspondente e obtenha uma sessão nova para verificar as claims emitidas.

Conserve um registro de login do chat separado da identidade federada de implantação.
Cadastre seu endereço de retorno a partir de `urlRetornoLogin`, saída da fase `rede` do Bicep L300,
antes da fase `aplicacao`. O segredo desse registro é usado somente pelo provedor de login;
as consultas de dados e modelos continuam com identidade gerenciada.

O procedimento oficial explica a criação e atribuição [1][5]. Desabilitar a definição de um papel
não remove automaticamente atribuições existentes; a revogação precisa tratar as atribuições e
o ciclo de vida dos tokens.
Use identidades de teste comuns para conferir a exigência de atribuição: a documentação registra
exceção para administradores globais [5]. O filtro da aplicação continua exigindo papel reconhecido.

A configuração do chat L300 exige:

```powershell
$env:VARELEIRA_EXIGIR_ACESSO_DOCUMENTAL = "true"
$env:VARELEIRA_EXIGIR_AUTENTICACAO = "true"
$env:VARELEIRA_INDICE = "vareleira-lar-l300"
$env:VARELEIRA_TENANT_AUTORIZADO = $tenant
```

Essas variáveis devem ser definidas no ambiente da aplicação; o Bicep L300 já as inclui.
Conserve também as variáveis de busca, modelos, identidade e tenant do L200.
`VARELEIRA_TENANT_AUTORIZADO` controla quem pode entrar no chat; não é substituído por
`VARELEIRA_TENANT_ID`, usado na credencial Azure do operador. `$tenant` deve conter o diretório
explicitamente autorizado. Esses comandos configuram apenas o processo do terminal: não atualizam
uma aplicação já implantada nem criam papéis. Para hospedagem, use a fase `aplicacao` revisada.
Papéis, sessões e atribuições são preparados no Entra ID conforme o roteiro administrativo.
Evite deixar o sinalizador ativo numa sessão local usada posteriormente para `--demo`.

## Etapa 3: conferir a recusa antes dos serviços

Execute os testes locais relacionados:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_acesso.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_chat.py
```

| Caso | Resultado a conferir |
| --- | --- |
| Identidade ausente ou inválida | Recusa; nenhuma consulta de dados |
| Tenant não permitido | Recusa antes da recuperação |
| Identidade sem papel reconhecido | HTTP 403; nenhum embedding, busca ou geração |
| Corretor pergunta sobre material interno | Marcador interno ausente do pedido ao modelo e das evidências |
| Atendimento consulta material permitido | Filtro correto e fonte autorizada recuperada |
| Pedido JSON inclui papel ou filtro | Campo extra rejeitado; permissão não é aceita da pessoa |
| Duas identidades em paralelo | Permissões limitadas à requisição, sem mistura de contexto |
| Falta o campo de acesso no índice | Erro explícito, sem repetir consulta sem filtro |

Esses resultados com dublês provam o caminho da aplicação. A rodada Azure também conferiu
a borda EasyAuth e os perfis Atendimento, Corretor, ambos e sem papel reconhecido.
O [registro Azure](../../docs/validacao/l300-azure-validacao.md) distingue clientes de aplicação
de login humano, que não foi realizado.

## Como pedir uma mudança ao Copilot no VS Code

Peça uma mudança por comportamento, com teste negativo que falhe antes da correção.
Ao incluir outra classe, delimite manifesto, regras e testes; mantenha a lista fechada de classes.
Revise o diff em **Source Control**. Evite filtros montados por concatenação de valores recebidos
da pergunta ou de parâmetros de depuração.

## Conferência do resultado

Confira a expressão enviada ao índice e a ausência dos marcadores restritos no contexto
entregue ao gerador.
Guarde somente contagens e rótulos de causa, sem tokens, papéis atribuídos a pessoas reais ou
conteúdo operacional do ambiente.

## Solução de problemas

| Sintoma | Ação |
| --- | --- |
| Pessoa entra, mas recebe 403 | Confira papel da aplicação, tenant e sessão nova; não conceda papel administrativo Azure |
| Acesso por `--demo` parece funcionar | Trate como simulação; o modo não valida a borda L300 |
| Índice rejeita o filtro | Confira o campo `acesso` e sua propriedade filtrável; preserve a recusa |
| Classe ausente nos trechos | Reveja metadados, carga e projeção; não use classe compartilhada como padrão silencioso |
| Conteúdo aparece pelo acesso direto ao índice | Restrinja identidades de dados e desenho do índice; o filtro do chat não protege consultas que o contornem |

## Custos, pausa e limpeza

Os testes locais não consomem busca ou modelos. Na operação, identidades sem papel devem ser
recusadas antes desses serviços. O acesso do operador aos recursos é separado do acesso da pessoa
ao chat.

Remova atribuições temporárias ao encerrar uma validação autorizada. Preserve papéis e identidades
preexistentes. A revogação precisa ser conferida com sessão nova e os limites de expiração dos tokens.

## Situação da validação

A integração local verifica filtro e ordem de chamadas com dublês.
No Azure, Atendimento e ambos recuperaram o roteiro; Corretor não recebeu seu conteúdo;
sem papel reconhecido recebeu 403. Pedidos anônimos e principal artificial receberam 401.
Busca textual, vetorial e híbrida respeitaram os filtros e a pré-filtragem vetorial.
Não houve atribuição a pessoas nem login humano. O [registro local L300](../../docs/validacao/l300-validacao-local.md)
e o [registro Azure](../../docs/validacao/l300-azure-validacao.md) detalham os alcances separados.

## Glossário

| Termo | Significado |
| --- | --- |
| Principal | Representação da identidade autenticada |
| Claim | Informação emitida no token, como tenant ou papel |
| Papel de aplicação | Permissão de uso de uma aplicação, atribuída no Entra ID |
| Classe documental | Categoria de acesso associada à fonte no exercício |
| Filtro de segurança | Restrição que exclui fontes não permitidas da consulta |
| `preFilter` | Aplicação do filtro antes de formar resultados vetoriais |
| EasyAuth | Autenticação integrada da plataforma Container Apps |
| HTTP e JSON | Protocolo da interface web e formato dos dados do pedido |

## Referências

1. [Definir papéis e recebê-los no token](https://learn.microsoft.com/en-us/entra/identity-platform/howto-add-app-roles-in-apps).
2. [Filtros de segurança no Azure AI Search](https://learn.microsoft.com/en-us/azure/search/search-security-trimming-for-azure-search).
3. [Filtragem de consultas vetoriais](https://learn.microsoft.com/en-us/azure/search/vector-search-filters).
4. [Autenticação e claims de Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/authentication).
5. [Exigir atribuição a usuários e serviços](https://learn.microsoft.com/en-us/entra/identity-platform/howto-restrict-your-app-to-a-set-of-users).

Texto por GPT-6.1 Sol; código e testes por Claude Sonnet 5.5, com Astra indisponível.
As escolhas de autoria não configuram os modelos do aluno ou os deployments Azure.

Revisão documental: gpt-6-astra (Astra), em 11 de outubro de 2026, por leitura integral e
conferência local dos artefatos; sem nova execução Azure.
