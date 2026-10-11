# L200 — Desafio 03: comparar divisão, vetores e recuperação

[Início do laboratório](../../README.md) · [Desafio 02](02-ingestao-gerenciada.md) · [Desafio 04](04-chat-local.md)

| Item | Descrição |
| --- | --- |
| Situação | Exercício executável. A comparação e a recuperação de um documento foram conferidas no Azure em 10 de outubro de 2026. |
| Público | Pessoas de Atendimento, operações, arquitetura e desenvolvimento. |
| Resultado | Diferenças entre os dois índices explicadas e recuperação comparada, sem exigir trechos ou identificadores iguais. |
| Custo | Embeddings das perguntas vetoriais e híbridas; serviços existentes continuam cobrados. Reprocessar documentos calcula novos embeddings. |

## Conteúdo

- [Cenário](#cenário)
- [Objetivos](#objetivos)
- [Artefatos e disponibilidade](#artefatos-e-disponibilidade)
- [Tecnologias e conceitos](#tecnologias-e-conceitos)
- [Pré-requisitos](#pré-requisitos)
- [Etapa 1: explicar as diferenças dos índices](#etapa-1-explicar-as-diferenças-dos-índices)
- [Etapa 2: comparar os três modos de busca](#etapa-2-comparar-os-três-modos-de-busca)
- [Etapa 3: conferir atualização e recuperação](#etapa-3-conferir-atualização-e-recuperação)
- [Como pedir uma mudança ao Copilot no VS Code](#como-pedir-uma-mudança-ao-copilot-no-vs-code)
- [Conferência do resultado](#conferência-do-resultado)
- [Solução de problemas](#solução-de-problemas)
- [Custos, pausa e limpeza](#custos-pausa-e-limpeza)
- [Situação da validação](#situação-da-validação)
- [Glossário](#glossário)
- [Referências](#referências)

## Cenário

No piloto fictício de 2025, Atendimento precisa encontrar a regra pertinente, independentemente de
quem preparou o índice. Beatriz Torres pede uma comparação com fontes verificáveis antes de adotar
a ingestão gerenciada. Teresa Moura exige que a equipe conserve versão e origem dos documentos.

O índice Python organiza trechos a partir da estrutura Markdown. O gerenciado usa Text Split,
habilidade que divide o texto em partes por tamanho [1]. Quantidades diferentes de trechos exigem
comparar o conteúdo recuperado, não apenas contar documentos.

## Objetivos

1. Explicar divisão, sobreposição, modelo de embeddings e campos dos dois índices.
2. Comparar seis consultas de conferência nos modos textual, vetorial e híbrido.
3. Distinguir teste de fumaça, conferência operacional curta, de avaliação independente.
4. Demonstrar que a exclusão de um blob pode retirar seus trechos e que a recuperação restaura a base.

## Artefatos e disponibilidade

| Artefato disponível | Uso |
| --- | --- |
| [Gerenciador de ingestão](../../scripts/gerenciar_ingestao.py) | Etapas `conferir`, `comparar`, `executar` e `remover` |
| [Regras de ingestão](../../scripts/lab_ingestao.py) | Divisão, embeddings, projeções e consultas de conferência |
| [Indexação Python](../../scripts/lab_indexacao.py) | Referência do L100 |
| [Carga do inventário](../../scripts/carregar_documentos.py) | Reposição de documento aprovado após exclusão de teste |
| [Consulta sem geração](../../scripts/buscar_trechos.py) | Inspeção dos trechos recuperados |
| [Registro do desafio](../../docs/validacao/l200-03-comparar-ingestao.md) | Comparação e recuperação observadas |

## Tecnologias e conceitos

**Sobreposição** repete uma parte do fim de um trecho no próximo, para reduzir perda de contexto
na fronteira. O skillset usa até 1.200 caracteres por parte, com sobreposição de 100. Essas escolhas
são parâmetros do laboratório, não valores universais para documentos de seguro.

**Vetorização integrada** calcula embeddings durante a ingestão [2]. Na consulta deste exercício,
Python continua calculando o embedding da pergunta; o pipeline não configura um vetorizador automático
da consulta. Os dois caminhos usam `text-embedding-3-small` com 1.536 dimensões.

**Busca textual** compara termos; **vetorial** compara vetores; **híbrida** combina as duas listas.
`k=3` significa recuperar os três primeiros resultados. Compare posição e evidências dentro de cada
modo; as pontuações de modos distintos têm significados diferentes.

> **Boa prática:** guarde documento e versão para localizar a fonte. A projeção pode mudar o
> identificador (ID) opaco de um trecho ao reprocessar seu documento [3].

## Pré-requisitos

Conclua os Desafios 01 e 02. Os índices `vareleira-lar-l100` e `vareleira-lar-l200` devem coexistir,
e os documentos devem estar conferidos. Use as mesmas variáveis e o ambiente Python no terminal
PowerShell 7 do VS Code.

As consultas exigem `Search Index Data Reader` na busca e uso do modelo para os modos vetorial e
híbrido. A etapa de recuperação exige permissão de carga no contêiner e execução do indexador.
Autorize separadamente uma exclusão reversível, incluindo o blob exato e o plano de reposição.

## Etapa 1: explicar as diferenças dos índices

Execute as conferências sem gravar. O verificador L100 calcula embeddings das perguntas conhecidas:

```powershell
python scripts\verificar_indice.py --busca $busca --modelos $modelos --tenant-id $tenant
python scripts\gerenciar_ingestao.py --etapa conferir --busca $busca --tenant-id $tenant
```

| Característica nesta versão | Python L100 | Gerenciado L200 |
| --- | --- | --- |
| Documentos de origem | Os mesmos três documentos | Os mesmos três documentos |
| Trechos conferidos | 54 | 21: 11 das Condições Gerais, 5 das perguntas frequentes (FAQ, *Frequently Asked Questions*) e 5 do glossário |
| Divisão | Estrutura Markdown e parâmetros do L100 | Text Split, 1.200 caracteres e sobreposição de 100 |
| Identificação de seção e cláusulas | Campos preenchidos pelo código | `secao` e `clausulas` ficam vazios |
| Identificador do trecho | Gerado pelo código | Gerado pela projeção; não é estável entre reprocessamentos |
| Documento, versão e hash declarado | Inventário e carga | Metadados do blob mapeados pela projeção |
| Execução | Script no computador | Serviço de busca com identidade própria |

A presença do metadado `sha256` não é uma nova comparação criptográfica do texto extraído.
A conferência dos bytes do blob continua sendo feita por `verificar_documentos.py`.

Os oito campos de resultado e o campo `vetor` existem nos dois índices, permitindo reutilizar a consulta.
Os scripts de **criação e conferência estrutural do L100** esperam seu esquema completo: não os use
para reindexar ou validar estruturalmente o índice L200.

### Prompt para o Copilot: comparar os mecanismos

Anexe este guia, `lab_indexacao.py` e `lab_ingestao.py`:

```text
Compare os dois caminhos de ingestão desta versão.
Explique tamanho dos trechos, sobreposição, campos ausentes e estabilidade dos IDs.
Mostre como localizar o documento original quando o ID da projeção mudar.
Não conclua que 21 trechos são melhores que 54 sem avaliar recuperação e fontes.
Não altere código, documentos, parâmetros ou recursos Azure.
```

**Conferência:** a resposta deve explicar o efeito sobre localização de fontes, operação e migração,
sem atribuir ao Text Split uma análise de cláusulas que ele não faz.

## Etapa 2: comparar os três modos de busca

As seis consultas embutidas no gerenciador são conferências de assuntos conhecidos. Os comandos
abaixo só leem índices; modos vetorial e híbrido consomem embeddings das perguntas:

```powershell
python scripts\gerenciar_ingestao.py --etapa comparar --busca $busca --modelos $modelos --tenant-id $tenant --modo texto --k 3
python scripts\gerenciar_ingestao.py --etapa comparar --busca $busca --modelos $modelos --tenant-id $tenant --modo vetorial --k 3
python scripts\gerenciar_ingestao.py --etapa comparar --busca $busca --modelos $modelos --tenant-id $tenant --modo hibrida --k 3
```

**Resultado conferido:** 6 de 6 consultas recuperaram os assuntos esperados entre os três primeiros
resultados, nos dois índices e nos três modos. O tamanho da base e o conjunto conhecido limitam essa
medição. Ela não mede fidelidade de uma resposta gerada nem demonstra superioridade de um caminho.

Para inspecionar uma pergunta sem gerar resposta:

```powershell
python scripts\buscar_trechos.py --busca $busca --modelos $modelos --tenant-id $tenant --indice vareleira-lar-l200 --pergunta "O que é a assistência 24 horas?" --modo hibrida --k 3
```

Abra os documentos no VS Code e localize os trechos mostrados. Confira versão e regra recuperada.
O [Desafio 06](06-avaliar-chat.md) trata a avaliação final com outro conjunto e configuração congelada.

## Etapa 3: conferir atualização e recuperação

Primeiro repita a execução sem mudar os arquivos, após simular seu plano:

```powershell
python scripts\gerenciar_ingestao.py --etapa executar --busca $busca --tenant-id $tenant
python scripts\gerenciar_ingestao.py --etapa executar --busca $busca --tenant-id $tenant --executar --aguardar 300
python scripts\gerenciar_ingestao.py --etapa conferir --busca $busca --tenant-id $tenant
```

**[altera o Azure]** na execução do indexador. Confira contagens e histórico; itens processados não
informam, por si, quantos tokens foram cobrados.

### Exclusão reversível e reposição autorizadas

Esta prática é opcional para o aluno e exige aprovação do alvo. Ela foi executada somente em uma
cópia Azure criada para a validação, preservando os arquivos locais e o índice L100.

1. Confira a base e combine a exclusão do blob de glossário.
2. Exclua esse blob, execute o indexador e observe a ausência intencional.
3. Reenvie a versão aprovada pelo script de carga.
4. Execute novamente o indexador e confira a recuperação.

```powershell
python scripts\verificar_documentos.py --conta $conta --tenant-id $tenant
az storage blob delete --subscription $assinatura --account-name $conta --container-name base-documental --name vareleira-lar/glossario-v1.0.md --auth-mode login --output none
python scripts\gerenciar_ingestao.py --etapa executar --busca $busca --tenant-id $tenant --executar --aguardar 300
python scripts\gerenciar_ingestao.py --etapa conferir --busca $busca --tenant-id $tenant
```

**[altera o Azure]** na exclusão e no processamento. A conferência deve reprovar a ausência esperada:
16 trechos de dois documentos, com `VLAR-GL-1.0` ausente. Essa falha intencional faz parte do exercício.
Pare se outros documentos desaparecerem.

Para repor o documento do inventário e recuperar o índice:

```powershell
python scripts\carregar_documentos.py --conta $conta --tenant-id $tenant
python scripts\carregar_documentos.py --conta $conta --tenant-id $tenant --executar
python scripts\gerenciar_ingestao.py --etapa executar --busca $busca --tenant-id $tenant --executar --aguardar 300
python scripts\gerenciar_ingestao.py --etapa conferir --busca $busca --tenant-id $tenant
python scripts\verificar_documentos.py --conta $conta --tenant-id $tenant
```

**[altera o Azure]** na reposição e no processamento. **Resultado esperado:** três documentos,
21 trechos e conferências aprovadas. Reenviar a fonte é o caminho demonstrado aqui.
Uma recuperação apenas com `undelete` pode exigir atualizar `LastModified` para que o indexador
reprocesse o blob [4]; esse caminho alternativo não foi executado nesta rodada.

## Como pedir uma mudança ao Copilot no VS Code

Para experimentar outro tamanho de trecho, peça uma proposta com índice L200 separado, custo e
critérios definidos **antes** da medição. Revise o diff e os testes; conserve o gabarito final.
Trocas de esquema podem exigir índice novo, e `--reiniciar` reprocessa todos os blobs.
O conjunto final não deve ser usado para escolher os parâmetros.

## Conferência do resultado

Registre assunto, modo, posição da evidência e diferença entre os índices, sem copiar gabaritos para
o armazenamento. Confirme três documentos e versões iguais após a recuperação.
O índice L100 deve conservar seus 54 trechos.

## Solução de problemas

| Sintoma | Ação |
| --- | --- |
| Busca vetorial incompatível | Confira deployment, modelo, versão e dimensões usados na ingestão e na consulta. |
| Citação sem seção | Localize a frase no documento; a projeção não produz o campo de seção nesta implementação. |
| Blob excluído permanece no índice | Confira política de exclusão desde a primeira execução, retenção e histórico. Projeções têm ciclo de vida próprio [3]; não generalize a outros modos de extração. |
| Reposição não reaparece | Confira carga, data da última alteração e execução; evite mudar hashes ou gabaritos para aparentar recuperação. |
| Divergência na definição | Revise a diferença antes de `--substituir`; preserve o índice de referência e o resultado anterior. |

## Custos, pausa e limpeza

A comparação usa os recursos já criados. Cada nova pergunta vetorial calcula um embedding;
reprocessar a base calcula embeddings dos trechos. Preserve os resultados para justificar a migração,
e remova índices temporários de experimentos com o plano de remoção correspondente.

Mantenha `vareleira-lar-l200` para o chat do Desafio 04. A limpeza completa está no Desafio 07.

## Situação da validação

Comparação real: seis consultas, dois índices e três modos; todos recuperaram os assuntos esperados
entre os três primeiros resultados. Exclusão e reposição: 21 → 16 → 21 trechos, mantendo os arquivos
locais e o L100. Veja o [registro](../../docs/validacao/l200-03-comparar-ingestao.md).
Esses resultados são operacionais e de fumaça, não uma avaliação independente de qualidade.

## Glossário

| Termo | Significado |
| --- | --- |
| Text Split | Habilidade de divisão de texto por tamanho |
| Sobreposição | Parte repetida entre trechos consecutivos |
| Vetorização integrada | Cálculo de embeddings incorporado à ingestão |
| `k` | Quantidade de resultados recuperados |
| Busca híbrida | Combinação da busca textual e vetorial |
| ID opaco | Identificador que não descreve semanticamente seu conteúdo |
| Teste de fumaça | Conferência curta dos mecanismos principais |
| Configuração congelada | Parâmetros preservados durante uma medição |

## Referências

1. [Text Split skill](https://learn.microsoft.com/en-us/azure/search/cognitive-search-skill-textsplit).
2. [Vetorização integrada](https://learn.microsoft.com/en-us/azure/search/vector-search-integrated-vectorization).
3. [Projeções e ciclo de vida dos documentos](https://learn.microsoft.com/en-us/azure/search/search-how-to-define-index-projections).
4. [Detecção de alterações, exclusões e reposição de blobs](https://learn.microsoft.com/en-us/azure/search/search-how-to-index-azure-blob-changed-deleted).

Texto e revisão: GPT-6.1 Sol. Código e testes: Claude Sonnet 5.5.
O Astra não estava disponível; autoria, Copilot do aluno e deployments Azure são escolhas separadas.
