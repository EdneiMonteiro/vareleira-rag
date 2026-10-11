# L300 — Desafio 02: atualizar a base com classificação documental

[Início do laboratório](../../README.md) · [Desafio 01](01-reproduzir-base.md) · [Desafio 03](03-filtrar-acesso.md)

| Item | Descrição |
| --- | --- |
| Situação | Manifesto, carga e ingestão privada conferidos no Azure; ciclo de exclusão e restauração aprovado |
| Público | Atendimento, operações, arquitetura e desenvolvimento |
| Resultado | Fontes sintéticas com classe obrigatória, nomes separados e manutenção incremental conferível |
| Custo | Validação local dispensa Azure. Carga usa armazenamento; indexação usa busca e embeddings |

## Conteúdo

- [Cenário](#cenário)
- [Objetivos](#objetivos)
- [Artefatos e disponibilidade](#artefatos-e-disponibilidade)
- [Tecnologias e conceitos](#tecnologias-e-conceitos)
- [Pré-requisitos](#pré-requisitos)
- [Etapa 1: conferir fontes e classificação](#etapa-1-conferir-fontes-e-classificação)
- [Etapa 2: preparar carga e indexador separados](#etapa-2-preparar-carga-e-indexador-separados)
- [Etapa 3: conferir atualização e exclusão](#etapa-3-conferir-atualização-e-exclusão)
- [Como pedir uma mudança ao Copilot no VS Code](#como-pedir-uma-mudança-ao-copilot-no-vs-code)
- [Conferência do resultado](#conferência-do-resultado)
- [Solução de problemas](#solução-de-problemas)
- [Custos, pausa e limpeza](#custos-pausa-e-limpeza)
- [Situação da validação](#situação-da-validação)
- [Glossário](#glossário)
- [Referências](#referências)

## Cenário

No piloto fictício de 2025, Beatriz Torres inclui um roteiro operacional para o Atendimento.
As três fontes gerais permanecem disponíveis aos dois públicos. A equipe classifica cada fonte
antes da carga, para que o filtro do chat receba metadados consistentes.

O roteiro novo é exclusivamente sintético e não acrescenta cobertura, exclusão, franquia ou
condição de seguro. Teresa Moura mantém a autoridade sobre o conteúdo das regras gerais.
A classificação de acesso é uma convenção do exercício, sujeita à revisão correspondente.

## Objetivos

1. Reutilizar as fontes L100 sem alterar seus textos, versões ou hashes normalizados.
2. Exigir classificação válida para cada fonte enviada.
3. Criar índice, contêiner e objetos de ingestão L300 separados dos níveis anteriores.
4. Conferir atualização, exclusão e reposição sem duplicação ou sobrescrita silenciosa.

O programa valida somente os arquivos do manifesto. Perguntas e respostas esperadas dos conjuntos
de avaliação permanecem fora da carga.

## Artefatos e disponibilidade

| Artefato | Uso |
| --- | --- |
| [Inventário L100](../../dados/l100/inventario.json) | Fontes gerais preservadas |
| [Manifesto L300](../../dados/l300/permissoes-documentais.json) | Fontes, hashes e classes do exercício |
| [Roteiro operacional](../../dados/l300/documentos/roteiro-interno-atendimento-v1.0.md) | Conteúdo sintético de Atendimento, aprovado pelo mantenedor em 10 de outubro de 2026 |
| [Gerenciador L300](../../scripts/gerenciar_ingestao_l300.py) e [biblioteca](../../scripts/lab_ingestao_l300.py) | Validação local, carga e operações no namespace novo |
| [Biblioteca L200](../../scripts/lab_ingestao.py) | Definição de índice, divisão, embeddings e projeções reaproveitadas |
| [Roteiro L300](../../docs/roteiro-l300.md) | Migração e critérios de avanço |

Um **namespace** reserva nomes e caminhos ao nível. O material original fica nos caminhos L100;
os metadados e os objetos L300 são adicionais. O documento operacional não cria regras de seguro.
A aprovação do conteúdo não autoriza sua carga nem a criação de recursos Azure.

## Tecnologias e conceitos

Um **manifesto** lista os arquivos permitidos, suas propriedades e impressões digitais.
O **hash SHA-256**, calculado pelo algoritmo Secure Hash Algorithm de 256 bits, é uma impressão
digital dos bytes. O exercício normaliza as quebras de linha para comparar o mesmo conteúdo
em sistemas diferentes; preserve a distinção
entre hash bruto e normalizado.

Uma **classe documental** identifica o público da fonte. O índice armazena `acesso` como
campo filtrável `Edm.String`. As classes do exercício são `compartilhado`, `atendimento` e `corretor`.
Elas são valores fechados, definidos fora da pergunta.
`Edm.String` indica um campo de texto no modelo de dados do índice. O manifesto não é uma
lista de controle de acesso (ACL, *Access Control List*) aplicada automaticamente pelo serviço:
ele valida a carga; a aplicação autoriza as classes antes da recuperação.

O **indexador** lê a fonte e executa o **skillset**, conjunto de habilidades que divide textos
e calcula embeddings, vetores numéricos dos trechos. Uma **projeção** relaciona cada trecho ao
documento original e copia seus metadados para o índice [1].

O serviço acompanha alterações por data de modificação. A detecção de exclusão precisa de uma
política desde a primeira execução. Para a política nativa de blobs, a exclusão reversível deve
estar ativa e o versionamento do Blob Storage desativado [2].

## Pré-requisitos

Conclua o plano do Desafio 01. Abra o projeto no Visual Studio Code (VS Code), selecione `.venv`
em **Python: Select Interpreter** e use PowerShell 7.
A validação do manifesto e os testes dispensam login e serviços Azure.

Para carga ou ingestão reais, confirme assinatura ativa, armazenamento, busca, modelos, tenant
e permissões de cada operação. O tenant é o diretório de identidades.
A busca precisa de identidade para ler o contêiner e chamar o deployment de embeddings,
instância nomeada do modelo. A pessoa que opera precisa dos papéis proporcionais à etapa.

Depois do isolamento, execute carga e conferência num caminho autorizado dentro da rede.
A ingestão usa conexões privadas compartilhadas e ambiente de execução privado [3].
Comece pelo manifesto e pelos testes locais deste desafio. Antes de executar os comandos Azure,
conclua a fase `rede` e as aprovações do [Desafio 04](04-dependencias-privadas.md);
depois retorne aqui para a carga e a primeira execução.
Execute cada comando separadamente e confira `$LASTEXITCODE` logo depois; qualquer falha impede
a próxima alteração. Em um terminal novo, recupere os destinos privados antes de simular.

## Etapa 1: conferir fontes e classificação

1. Abra o manifesto e localize cada fonte.
2. Confira identificação sintética, caminho, hash e classe.
3. Confira as três fontes gerais contra o inventário L100.
4. Execute a conferência local e interrompa a operação se faltar classe, arquivo ou correspondência
   de conteúdo.

```powershell
.\.venv\Scripts\python.exe scripts\gerenciar_ingestao_l300.py --etapa validar
```

| Fonte | Classificação no exercício |
| --- | --- |
| Condições gerais L100 | `compartilhado` |
| Glossário L100 | `compartilhado` |
| Perguntas frequentes L100 | `compartilhado` |
| Roteiro operacional novo | `atendimento` |

**Resultado esperado:** quatro fontes listadas existem, são sintéticas e têm classe reconhecida.
Uma classe vazia ou desconhecida é erro de carga; ela não concede acesso compartilhado.
As quatro fontes existentes estão aprovadas para o exercício. Novos documentos ou alterações
de conteúdo exigem revisão correspondente; o programa mantém o aviso para material pendente.
O manifesto limita a carga da ferramenta. O indexador lê o prefixo inteiro e o chat autoriza
classes; restrinja quem grava blobs e metadados. Uma fonte inesperada com classe permitida pode
ser recuperada, mesmo sem constar na lista. A conferência do índice identifica essa divergência.

### Prompt para o Copilot: conferir o manifesto

Anexe este guia, o manifesto e o inventário L100:

```text
Confira a lista de fontes L300, seus hashes e classes, somente por leitura.
Explique o que é copiado e quais arquivos originais permanecem inalterados.
Confira se perguntas de avaliação ficaram fora do conteúdo recuperável.
Liste divergências e condições que impedem a carga.
Não mude as regras de seguro, os hashes originais ou os conjuntos finais.
Não execute carga, indexação ou comandos Azure.
```

**Conferência:** o Copilot deve distinguir classificação de acesso e regra de seguro.
Uma proposta de trocar bytes ou hash do L100 para resolver divergência exige revisão,
não atualização automática.

## Etapa 2: preparar carga e indexador separados

Esta é a sequência Azure de referência. A validação autorizada executou o mesmo gerenciador
com identidade gerenciada, de dentro da rede; veja o [registro Azure](../../docs/validacao/l300-azure-validacao.md).
Carga, criação dos objetos e execução do indexador **[altera o Azure]**.

1. Valide o manifesto antes de criar clientes de rede.
2. Defina assinatura, grupo, conta, busca, modelos e tenant em variáveis privadas da sua sessão.
3. Simule a carga no contêiner `base-documental-l300`; confira caminhos, metadados e condições
   de versão dos blobs existentes.
4. Após autorização, envie somente as fontes listadas.
5. Crie os objetos L300 e mantenha o indexador desabilitado até aprovar sua execução.
6. Confira filtro, projeção de `acesso` e política de exclusão antes da primeira execução.

Os exemplos abaixo usam o login do operador; a rodada empregou identidade gerenciada.
Eles não foram executados literalmente com as variáveis do aluno. As variáveis correspondem
ao destino escolhido pelo aluno; a ausência de valores deve interromper a operação.
Os comandos sem `--executar` leem o destino para mostrar o plano.
Para operar por identidade gerenciada dentro da rede, substitua `--tenant-id $tenant`
por `--identidade-gerenciada --client-id $clientId`; não combine essas opções.
Depois do isolamento, o terminal externo pode não alcançar os dados.

```powershell
.\.venv\Scripts\python.exe scripts\gerenciar_ingestao_l300.py --etapa carregar --conta $conta --tenant-id $tenant
.\.venv\Scripts\python.exe scripts\gerenciar_ingestao_l300.py --etapa criar --busca $busca --assinatura $assinatura --grupo $grupo --conta $conta --modelos $modelos --tenant-id $tenant
```

Após conferir e aprovar os alvos, **[altera o Azure]**:

```powershell
.\.venv\Scripts\python.exe scripts\gerenciar_ingestao_l300.py --etapa carregar --conta $conta --tenant-id $tenant --executar
.\.venv\Scripts\python.exe scripts\gerenciar_ingestao_l300.py --etapa criar --busca $busca --assinatura $assinatura --grupo $grupo --conta $conta --modelos $modelos --tenant-id $tenant --executar
.\.venv\Scripts\python.exe scripts\gerenciar_ingestao_l300.py --etapa executar --busca $busca --tenant-id $tenant --executar --aguardar
```

O indexador nasce desabilitado e sem agenda. A primeira etapa `executar` o habilita; habilitar um
indexador pode iniciar seu processamento. Confira o estado final com `--aguardar` antes de continuar.
Uma agenda futura exige decisão de custo e retenção, usando `--intervalo` na criação.

| Permissão | Identidade e escopo |
| --- | --- |
| Ler os blobs da fonte | Identidade da busca, no contêiner L300 |
| Carregar, excluir ou restaurar blobs | Operador da carga, no contêiner L300 |
| Criar e remover objetos do pipeline | Operador autorizado no serviço de busca |
| Conferir trechos e classes | Operador com leitura dos dados do índice |
| Calcular embeddings na ingestão | Identidade da busca no recurso de modelos |

O Bicep da fase `rede` acrescenta os dois papéis do contêiner. Autorizar sua implantação inclui
revisar esses efeitos; o código não concede os papéis por conta própria.

| Configuração | Valor ou condição |
| --- | --- |
| Índice | `vareleira-lar-l300` |
| Contêiner | `base-documental-l300` |
| Prefixo dos objetos de busca | `vareleira-lar-l300` |
| Marcador do exercício | `vareleira-rag:l300` |
| Campo de acesso | `acesso`, filtrável e projetado em cada trecho |
| Execução do indexador | `executionEnvironment=private` |
| Exclusão | Política nativa presente desde a primeira execução |
| Versionamento do armazenamento | Desativado para a política nativa |

Uma projeção deve mapear os metadados necessários em cada trecho. Preserve o campo de vínculo
com a fonte; seu mapeamento incorreto interrompe o acompanhamento das alterações [1].
O indexador privado depende de conexões compartilhadas aprovadas antes de conseguir executar [3].
Para esta topologia, mantenha o padrão privado. A opção de execução não privada serve a desenho
alternativo explicitamente revisado, não a contornar uma conexão recusada.

## Etapa 3: conferir atualização e exclusão

Esta prática foi conferida na rodada Azure com a cópia sintética operacional:
24 trechos antes da exclusão, 21 após a indexação e 24 após restaurar e reindexar, conforme o
[registro Azure](../../docs/validacao/l300-azure-validacao.md#ingestão-e-atualização).
Alterar metadados, excluir ou repor o blob e executar o indexador **[altera o Azure]**.

1. Registre contagem de trechos por fonte e classe antes da alteração.
2. Faça uma mudança autorizada no material operacional ou em seus metadados, preservando o L100.
3. Execute o indexador e confira a nova representação da fonte.
4. Após autorização específica, retire somente a cópia operacional L300.
5. Execute o indexador dentro da retenção e confira ausência dos trechos dessa fonte.
6. Reponha a cópia aprovada ou restaure e atualize seus metadados.
7. Execute novamente e confira presença, classes e ausência de duplicação.

As projeções acompanham mudanças e exclusões quando a fonte oferece detecção configurada [1].
A restauração nativa de um blob pode conservar `LastModified`, data da última alteração.
Regravar seus metadados faz o indexador perceber a reposição [2].

**Resultado esperado:** a fonte alterada é atualizada; a retirada elimina seus trechos; a reposição
restaura os dados previstos. As demais fontes permanecem intactas.
As contagens reais são registradas após a execução, sem fixar um número de trechos não medido.

Use somente o documento operacional `VLAR-OP-ATD-1.0`. Primeiro simule:

```powershell
.\.venv\Scripts\python.exe scripts\gerenciar_ingestao_l300.py --etapa excluir --conta $conta --tenant-id $tenant --documento VLAR-OP-ATD-1.0
```

Após autorização da exclusão reversível, **[altera o Azure]**:

```powershell
.\.venv\Scripts\python.exe scripts\gerenciar_ingestao_l300.py --etapa excluir --conta $conta --tenant-id $tenant --documento VLAR-OP-ATD-1.0 --executar
.\.venv\Scripts\python.exe scripts\gerenciar_ingestao_l300.py --etapa executar --busca $busca --tenant-id $tenant --executar --aguardar
.\.venv\Scripts\python.exe scripts\gerenciar_ingestao_l300.py --etapa conferir --busca $busca --tenant-id $tenant --ausente VLAR-OP-ATD-1.0
```

O último comando só lê e exige ausência da fonte. Para restaurar, simule e aprove o alvo antes
de executar a reposição, **[altera o Azure]** nos comandos com `--executar`:

```powershell
.\.venv\Scripts\python.exe scripts\gerenciar_ingestao_l300.py --etapa restaurar --conta $conta --tenant-id $tenant --documento VLAR-OP-ATD-1.0
.\.venv\Scripts\python.exe scripts\gerenciar_ingestao_l300.py --etapa restaurar --conta $conta --tenant-id $tenant --documento VLAR-OP-ATD-1.0 --executar
.\.venv\Scripts\python.exe scripts\gerenciar_ingestao_l300.py --etapa executar --busca $busca --tenant-id $tenant --executar --aguardar
.\.venv\Scripts\python.exe scripts\gerenciar_ingestao_l300.py --etapa conferir --busca $busca --tenant-id $tenant
```

A ferramenta recusa excluir ou restaurar fontes de origem L100. Se o objeto saiu da retenção,
a restauração nativa fica indisponível; simule a carga da cópia aprovada com `--documento`.
Se os bytes restaurados divergirem do manifesto, o programa termina com código 3 e conserva
os metadados anteriores, sem reaplicar a classificação. O blob já foi restaurado nessa situação;
interrompa a indexação, confira os efeitos e autorize uma reposição antes de continuar.

## Como pedir uma mudança ao Copilot no VS Code

Delimite manifesto, documento operacional, biblioteca e testes.
Para alterar uma classe, peça validação local e um teste negativo de acesso; trate também
o intervalo entre a mudança da fonte e a atualização do índice.
Revise o diff em **Source Control** e confirme que condições gerais e conjuntos finais
não participaram da alteração.

## Conferência do resultado

Execute os testes locais da classificação e da ingestão:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_ingestao_l300.py
```

| Conferência | Evidência |
| --- | --- |
| Manifesto | Arquivos reais, hashes normalizados e classes obrigatórias |
| Simulação | Nenhum envio ou alteração sem opção explícita |
| Repetição | Mesmo objeto reconhecido; divergência e alteração concorrente interrompem a operação |
| Índice e projeção | `acesso` filtrável e copiado para cada trecho |
| Namespace | Objetos L100/L200 preservados |
| Exclusão e reposição | Testes locais de decisão e ciclo Azure 24 → 21 → 24, sem mudar fontes L100/L200 |

## Solução de problemas

| Sintoma | Diagnóstico e ação |
| --- | --- |
| Hash diverge somente entre sistemas | Confira normalização LF (*Line Feed*)/CRLF (*Carriage Return + Line Feed*), convenções de quebra de linha, e preserve o conteúdo |
| Classe ausente | Corrija o manifesto após revisão; preserve a recusa de carga |
| Fonte no índice sem classe | Confira metadados e projeção; mantenha a fonte excluída do contexto |
| Indexador privado falha | Confira conexões compartilhadas, aprovações e identidade |
| Blob ausente, trecho ainda presente | Confira política e retenção; evite encerrar a janela antes do processamento |
| Fonte restaurada não é atualizada | Confira `LastModified`, metadados e execução do indexador |
| Restauração termina com divergência | Blob já restaurado, sem nova classificação; confira e reponha somente após autorização |

## Custos, pausa e limpeza

A validação local usa arquivos e dublês. O Azure cobra armazenamento, serviço de busca
e embeddings usados pela ingestão. Reexecuções com fontes alteradas podem recalcular vetores.
Conserve os objetos L300 para os próximos desafios e registre prazo e orçamento.

A retirada da fonte no exercício preserva sua cópia local aprovada. Encerrar a comparação exige
retirar o tráfego consumidor e remover apenas objetos próprios, em ordem de dependência.

## Situação da validação

A integração local confere manifesto, classes, hashes, definição do pipeline e decisões com dublês.
A rodada Azure conferiu quatro fontes e 24 trechos, carga idempotente, indexador privado,
exclusão e restauração, com zero falhas, erros e avisos. As fontes L100 e as medições L200
continuam preservadas. O [registro local L300](../../docs/validacao/l300-validacao-local.md)
e o [registro Azure](../../docs/validacao/l300-azure-validacao.md) distinguem testes com dublês
de operações reais. O resultado do encerramento dos temporários consta no registro Azure.

## Glossário

| Termo | Significado |
| --- | --- |
| Manifesto e hash | Lista de fontes permitidas e impressão digital do conteúdo |
| Classe documental | Categoria de acesso associada a uma fonte |
| Skillset | Conjunto de habilidades executadas pelo indexador |
| Projeção | Mapeamento de trechos e metadados para o índice |
| Namespace | Conjunto de nomes e caminhos reservado ao nível |
| `LastModified` | Data de modificação usada para detectar mudança |
| LF e CRLF | Convenções de quebra de linha em arquivos |
| ACL | Lista de controle de acesso; o manifesto não se torna uma ACL automática do índice |

## Referências

1. [Projeções e ciclo de vida dos trechos](https://learn.microsoft.com/en-us/azure/search/search-how-to-define-index-projections).
2. [Detecção de alteração, exclusão e restauração](https://learn.microsoft.com/en-us/azure/search/search-how-to-index-azure-blob-changed-deleted).
3. [Conexões privadas de saída do indexador](https://learn.microsoft.com/en-us/azure/search/search-indexer-howto-access-private).

Texto por GPT-6.1 Sol; código e testes por Claude Sonnet 5.5, com Astra indisponível.
O Copilot do aluno e os deployments Azure têm seleção e consumo separados da autoria.

Revisão documental: gpt-6-astra (Astra), em 11 de outubro de 2026, por leitura integral e
conferência local dos artefatos; sem nova execução Azure.
