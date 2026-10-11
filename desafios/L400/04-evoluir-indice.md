# L400 · Desafio 04: evoluir o índice sem perder a referência

[Início](../../README.md) · [Desafio 03](03-operar-deployments.md) · [Desafio 05](05-comparar-estrategias.md)

| Campo | Definição |
| --- | --- |
| Situação | Candidato de 768 dimensões criado e conferido; promoção e retorno observados no Azure |
| Público | Operações, arquitetura e desenvolvimento |
| Resultado | Reindexar em paralelo, conferir compatibilidade e testar promoção e retorno |
| Custo | Reindexação recalcula embeddings; índices e serviços mantidos têm custos próprios |

## Conteúdo

- [Cenário](#cenário)
- [Objetivos](#objetivos)
- [Artefatos e disponibilidade](#artefatos-e-disponibilidade)
- [Tecnologias e conceitos](#tecnologias-e-conceitos)
- [Pré-requisitos](#pré-requisitos)
- [Etapa 1: identificar as duas configurações](#etapa-1-identificar-as-duas-configurações)
- [Etapa 2: reindexar em paralelo](#etapa-2-reindexar-em-paralelo)
- [Etapa 3: promover e retornar](#etapa-3-promover-e-retornar)
- [Como pedir uma mudança ao Copilot no VS Code](#como-pedir-uma-mudança-ao-copilot-no-vs-code)
- [Conferência do resultado](#conferência-do-resultado)
- [Solução de problemas](#solução-de-problemas)
- [Custos, pausa e limpeza](#custos-pausa-e-limpeza)
- [Situação da validação](#situação-da-validação)
- [Glossário e referências](#glossário-e-referências)

## Cenário

O piloto fictício quer observar uma configuração de vetores menor sem modificar o índice que já
funciona. Teresa Moura exige que fontes e classes sejam preservadas; a equipe de operações
precisa de um retorno que não dependa de reconstruir a referência durante uma falha.

## Objetivos

1. Distinguir dimensão do vetor, modelo, versão e configuração do índice.
2. Criar um candidato separado com as mesmas fontes aprovadas.
3. Conferir recuperação e classes, além da contagem de trechos.
4. Testar promoção e retorno explícitos.

## Artefatos e disponibilidade

| Artefato | Uso |
| --- | --- |
| [Gerenciador L300](../../scripts/gerenciar_ingestao_l300.py) | Criação, execução e conferência do pipeline |
| [Manifesto](../../dados/l300/permissoes-documentais.json) | Mesmos arquivos, hashes e classes |
| [Definições da ingestão](../../scripts/lab_ingestao.py) | Índice, habilidade de embeddings e projeção |
| [Acesso documental](../../scripts/lab_acesso.py) | Filtro e validação dos trechos |

O [helper L400](../../scripts/operar_l400.py) confere o descritor de promoção e retorno.
Nenhuma declaração de compatibilidade substitui as leituras reais da definição, da ingestão
e das consultas.

## Tecnologias e conceitos

**Embeddings** são vetores numéricos do texto. A **dimensão** é o número de posições de cada vetor.
O índice e a consulta precisam usar modelo, versão e dimensões compatíveis [1].

O exercício conserva `text-embedding-3-small`, versão `1`, e compara 1.536 com 768 dimensões.
O modelo permite esse intervalo [1]. Reduzir dimensões não comprova melhoria de qualidade,
latência ou custo do serviço; esses efeitos precisam de medição.

Alterar a estrutura do índice pode exigir reconstrução. Um índice separado permite experimentar
e retornar; um alias é outra estratégia possível, mas não é requisito deste exercício [2].
O caminho privado da aplicação não substitui as conexões de saída do indexador [3].

## Pré-requisitos

Use a base L300 e um caminho autorizado de manutenção dentro da rede.
Confirme assinatura ativa, identidade de carga e papéis no contêiner e na busca.

Criação de objetos e reindexação **[altera o Azure]**. Simule os alvos e preserve a referência.
Não reabra serviços públicos para permitir que um terminal externo alcance os dados.

## Etapa 1: identificar as duas configurações

| Configuração | Referência | Candidato |
| --- | --- | --- |
| Índice | `vareleira-lar-l300` | `vareleira-lar-l300-l400-768` |
| Dimensões | 1.536 | 768 |
| Modelo e versão | `text-embedding-3-small`, `1` | Os mesmos, com dimensão explícita |
| Fontes e classes | Quatro fontes aprovadas | As mesmas, com hashes conferidos |

O prefixo L300 do candidato mantém o contrato documental existente. O índice é separado
e não representa novas regras ou uma nova versão dos documentos.

## Etapa 2: reindexar em paralelo

1. Leia e registre a definição da referência.
2. Simule a criação dos quatro objetos do candidato.
3. Após autorização, crie e execute o indexador privado.
4. Confira dimensões do campo, da habilidade e das consultas.
5. Compare hashes, classes, contagens e perguntas de desenvolvimento.

O `gerenciar_ingestao_l300.py` recebe o índice e as dimensões explicitamente.
Primeiro confira o plano local:

```powershell
.\.venv\Scripts\python.exe scripts\operar_l400.py --etapa planejar --passo indice-candidato
```

Os comandos abaixo foram exercitados pelo gerenciador na rede privada.
Variáveis identificam o destino autorizado do aluno, não recursos do instrutor.
Recupere na sessão privada os nomes de `$busca`, `$grupo`, `$conta` e `$modelos`,
a assinatura em `$assinatura` e o identificador da identidade de manutenção em
`$clientIdManutencao`. Eles vêm do inventário próprio da base L300.
Um terminal comum do VS Code não passa a estar na rede privada por receber essas variáveis.
Simule a criação antes de enviar:

```powershell
.\.venv\Scripts\python.exe scripts\gerenciar_ingestao_l300.py --etapa criar --busca $busca --assinatura $assinatura --grupo $grupo --conta $conta --modelos $modelos --indice vareleira-lar-l300-l400-768 --dimensoes 768 --identidade-gerenciada --client-id $clientIdManutencao
```

Depois de autorizar os alvos, **[altera o Azure]**:

```powershell
.\.venv\Scripts\python.exe scripts\gerenciar_ingestao_l300.py --etapa criar --busca $busca --assinatura $assinatura --grupo $grupo --conta $conta --modelos $modelos --indice vareleira-lar-l300-l400-768 --dimensoes 768 --identidade-gerenciada --client-id $clientIdManutencao --executar
.\.venv\Scripts\python.exe scripts\gerenciar_ingestao_l300.py --etapa executar --busca $busca --indice vareleira-lar-l300-l400-768 --identidade-gerenciada --client-id $clientIdManutencao --executar --aguardar
```

A conferência só lê:

```powershell
.\.venv\Scripts\python.exe scripts\gerenciar_ingestao_l300.py --etapa conferir --busca $busca --indice vareleira-lar-l300-l400-768 --dimensoes 768 --identidade-gerenciada --client-id $clientIdManutencao
```

Esses comandos devem partir do caminho privado autorizado. Na sessão do Azure CLI do operador,
substitua as opções de identidade gerenciada por `--tenant-id $tenant`; não combine os dois mecanismos.
Não corte um vetor antigo para fabricar uma reindexação concluída.

## Etapa 3: promover e retornar

1. Registre configuração de origem, candidata e condição de aprovação.
2. Confira que a aplicação usa índice e dimensão da mesma configuração.
3. Aplique a troca autorizada e execute uma consulta autenticada.
4. Retorne à referência e repita a conferência.
5. Remova o candidato somente depois de retirar seus consumidores.

**Resultado esperado:** referência preservada, aplicação compatível e retorno observado.
Uma variável de configuração alterada sozinha não comprova que os vetores estão corretos.

Preencha um descritor privado com `origem=operador`, ação, manifesto dos deployments,
configurações atual/alvo e observações dos dois índices. Os índices precisam ter as mesmas
quatro fontes, hashes e classes, contagens da referência preservadas e candidato completo.
Marque `simulado` quando usar dublês.

```powershell
.\.venv\Scripts\python.exe scripts\operar_l400.py --etapa conferir-migracao --descritor $descritorPrivado --relatorio $novoRelatorio
```

O helper não aplica a troca nem coleta medições. Para promover, a aplicação usa o perfil
`candidato`; para retornar, usa `referencia`, depois de revisar o plano correspondente.
O formato do descritor está nas validações e nos exemplos sintéticos de
[`test_operacao_l400.py`](../../tests/test_operacao_l400.py). Use-os para compreender os campos,
nunca como prova observada. O roteiro que altera a aplicação e coleta essas observações
precisa ser preparado e revisado pelo operador; ele não foi entregue como comando público.

## Como pedir uma mudança ao Copilot no VS Code

```text
Anexo manifesto, ingestão e descritor da migração.
Confira modelo, versão, dimensões, filtros e consumidores dos dois índices.
Mostre quais condições impedem a promoção e como retornar à referência.
Não altere fontes, elimine o índice anterior ou execute Azure.
```

Revise o diff e os testes de configuração incompatível antes de aplicar.

## Conferência do resultado

| Prova | Resultado necessário |
| --- | --- |
| Definições | Dimensão e perfil vetorial coerentes |
| Ingestão | Conclusão sem falhas e classes do manifesto |
| Consulta | Vetor compatível e filtro enviado |
| Referência | Definição e fontes anteriores intactas |
| Retorno | Aplicação consulta novamente o índice anterior |

## Solução de problemas

| Sintoma | Ação |
| --- | --- |
| Serviço rejeita a dimensão | Confira índice, habilidade e cliente de embeddings |
| Contagem coincide, mas conteúdo diverge | Confira hashes, metadados e classes |
| Candidato substitui a referência | Interrompa e corrija nomes e condições de gravação |
| Consulta externa recebe 403 | Use o caminho privado autorizado, sem reabrir acesso |

## Custos, pausa e limpeza

Reindexação consome embeddings novamente. Defina prazo para coexistência e mantenha a referência
até conferir o retorno. A remoção do candidato não elimina a cobrança do serviço de busca.

Remova somente os objetos candidatos com propriedade conferida e consumidores retirados.
Conexões compartilhadas e recursos anteriores exigem autorização própria de encerramento.

## Situação da validação

Referência e candidato tiveram quatro fontes e 24 trechos, com 1.536 e 768 dimensões,
mesmos hashes e classes. A promoção e o retorno tiveram consulta autenticada documentada
e borda preservada. O cliente L400 recebeu uma correção para enviar `dimensions=768`;
a primeira falha foi preservada no [registro](../../docs/validacao/l400-validacao.md).
A aplicação convencional permaneceu na referência de 1.536; não foi testada no candidato.

## Glossário e referências

| Termo | Significado |
| --- | --- |
| Dimensão | Quantidade de posições do vetor |
| Reindexação | Novo processamento das fontes para preencher um índice |
| Projeção | Mapeamento dos campos das fontes para os trechos |
| Alias | Nome indireto associado a um índice |
| Promoção | Troca autorizada da configuração usada pela aplicação |

1. [Índices vetoriais e dimensões](https://learn.microsoft.com/en-us/azure/search/vector-search-how-to-create-index).
2. [Atualização e reconstrução de índices](https://learn.microsoft.com/en-us/azure/search/search-howto-reindex).
3. [Saída privada do indexador](https://learn.microsoft.com/en-us/azure/search/search-indexer-howto-access-private).

Texto por GPT-6.1 Sol; código por Claude Sonnet 5.5. Embeddings e modelo do Copilot são distintos.

Revisão documental por gpt-6-astra (Astra), em 11 de outubro de 2026, sem nova execução Azure.
