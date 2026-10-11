# L400: coordenação limitada, comparação e recuperação

| Item | Definição |
| --- | --- |
| Situação | Implementação, comparação Azure, isolamento e encerramento dos temporários próprios verificados |
| Público | Atendimento, operações, arquitetura e desenvolvimento após o L300 |
| Resultado | Comparar coordenação de especialistas com o RAG convencional, mantendo acesso, evidências e limites de execução |
| Continuidade | As quatro fontes aprovadas, a política L100, o chat e a topologia privada L300 continuam como referência |
| Fora do escopo | Novas regras de seguro, dados reais, decisão de cobertura individual, homologação de produção e ativação de confiança GitHub |

## Cenário e decisão

No piloto fictício de 2025, Beatriz Torres precisa consultar assuntos que podem exigir mais de
uma busca. Teresa Moura quer conferir se essa complexidade ajuda sem enfraquecer as fontes ou
a autorização documental. A equipe de operações precisa interromper consultas, observar falhas
e retornar à configuração anterior.

O L400 não presume que mais agentes tragam respostas melhores. Uma estratégia que obtém o
mesmo resultado com mais chamadas, maior duração e maior custo pode justificar conservar o
RAG convencional. O exercício mede essas diferenças; sua conclusão não autoriza produção.

As condições gerais, o glossário, as perguntas frequentes e o roteiro operacional continuam
sintéticos e aprovados. Nenhum texto novo de seguro é necessário. Perguntas e respostas
esperadas da comparação ficam fora da base recuperável e das imagens do chat.

## Sete desafios

| Desafio | Decisão ou prática |
| --- | --- |
| [01. Delimitar a coordenação](../desafios/L400/01-delimitar-coordenacao.md) | Fixar responsabilidades, fontes, identidade, limites e referência |
| [02. Coordenar especialistas](../desafios/L400/02-coordenar-especialistas.md) | Planejamento, recuperação filtrada, verificação e redação com MAF |
| [03. Operar deployments](../desafios/L400/03-operar-deployments.md) | Contingência por falha transitória, sem ampliar privilégios |
| [04. Evoluir o índice](../desafios/L400/04-evoluir-indice.md) | Reindexar em paralelo, conferir dimensões e testar promoção e retorno |
| [05. Comparar estratégias](../desafios/L400/05-comparar-estrategias.md) | Conjunto novo congelado, falhas no denominador e uso de tokens explícito |
| [06. Testar carga e interrupção](../desafios/L400/06-testar-carga-interrupcao.md) | Carga finita, progresso verificado, cancelamento e limites |
| [07. Recuperar e limpar](../desafios/L400/07-recuperar-limpar.md) | Restaurar a referência, encerrar acesso e remover somente temporários próprios |

## Arquitetura do exercício

**Microsoft Agent Framework (MAF)** organiza um fluxo explícito. Os agentes de planejamento
e redação executam responsabilidades limitadas; etapas de autorização, recuperação e
verificação continuam sob controle do programa. O framework oferece executores tipados,
eventos e mecanismos de requisição e resposta, sem obrigar uma conversa livre entre agentes [1].

```text
Identidade autenticada e pergunta
    → limites e contexto de acesso da requisição
    → planejamento de consultas
    → recuperação com filtro documental em cada consulta
    → conferência das fontes e referências
    → redação estruturada
    → política L100 e resposta verificada
```

O modelo não escolhe a assinatura, o índice, o filtro, os papéis nem o endereço de uma ferramenta.
As ferramentas do exercício consultam dados; não implantam recursos ou decidem indenização.
Uma requisição sem contexto autorizado é recusada antes das chamadas de modelos.

O modo L400 é uma opção explícita. O padrão L200/L300 permanece como referência, com o mesmo
contrato público de resposta. Não há migração silenciosa de todos os participantes.

## Modelos e compatibilidade

O exercício conserva `gpt-5.4-mini`, versão `2026-03-17`, para geração, e
`text-embedding-3-small`, versão `1`, para embeddings, vetores numéricos do texto.
O primário e a contingência são deployments, instâncias nomeadas, separados do mesmo modelo.
Criar dois deployments não cria automaticamente nova cota; a capacidade precisa ser conferida
na assinatura e região [2].

A migração compara a referência de 1.536 dimensões com um índice separado de 768 dimensões.
`text-embedding-3-small` permite dimensões nesse intervalo [3]. Alterar a dimensão exige
recalcular os vetores dos documentos e das perguntas. Misturar um vetor de consulta de 768
posições com um índice de 1.536 não é uma comparação válida.

O nome proposto do candidato, `vareleira-lar-l300-l400-768`, conserva o prefixo do contrato
documental L300. Isso permite reutilizar o gerenciador e os filtros sem alterar o índice de
referência. O nome não representa uma versão nova das condições gerais.

## Limites e evidências

| Controle | Evidência necessária |
| --- | --- |
| Responsabilidade | Agentes não alteram destino, filtro ou permissões |
| Execução | Chamadas, buscas, saída e duração têm limites finitos |
| Contingência | Falhas transitórias podem trocar o deployment dentro do orçamento; erros de autorização não |
| Progresso | Eventos de etapa não incluem conteúdo bruto do modelo |
| Cancelamento | Próximas etapas deixam de executar; consumo já enviado pode continuar até o retorno remoto |
| Comparação | Mesmas perguntas e regime documentado, com falhas contadas |
| Recuperação | Índice e configuração anteriores permanecem disponíveis durante a migração |
| Limpeza | Ausência real dos alvos próprios, expurgos específicos e linha de base preservada |

Um checkpoint, registro do estado de execução, pode ajudar a retomar um workflow [4].
Ele não substitui a autorização do operador, a conferência da configuração nem o orçamento.
Persistir estado também exige tratar conteúdo, permissões do arquivo e tipos que podem ser
desserializados. Não introduza armazenamento de conversas por conveniência.

## Autorização, custos e situação

O mantenedor pediu implementar e executar o L400 até o final, sem perguntas intermediárias.
A rodada usa os destinos privados já confirmados, `brazilsouth` e um grupo exclusivo novo.
O teto anterior de US$90 não é renovado como um segundo orçamento. A cobrança efetiva do L300
e do L400 continua indisponível; reservas conservadoras de controle não representam fatura.

A rodada provisionou após as verificações locais e terminou removendo os temporários próprios.
Dados, modelos, busca, logs, imagens, rede e recursos gerenciados podem gerar cobranças.
A conferência posterior encontrou o grupo exclusivo e o gerenciado ausentes, zero recursos e
papéis próprios, aplicativos e modelos expurgados. Oito grupos, 46 recursos e atribuições anteriores
foram preservados. A consulta final de custo retornou sem linhas; isso não comprova custo zero.
Uma nova reprodução exige autorização própria, não depende dos recursos removidos desta rodada.

A implementação final passou na suíte integrada de 1.015 casos, com 1.014 aprovados e um
ignorado no Windows. Em Linux, 100 testes de runtime e 24 de sanitização operacional passaram,
incluindo o teste de permissões POSIX.
O conjunto final de 16 casos foi executado uma vez, com 16/16 conformes em ambas as estratégias,
zero descartes e maior uso de geração e latência mediana na coordenação.
Não houve ganho de conformidade que justifique trocar o padrão convencional neste regime.
O [registro L400](validacao/l400-validacao.md) conserva as correções anteriores ao teste final,
as limitações da medição, o reparo posterior de cancelamento explícito e o encerramento dos
recursos. A comparação permaneceu vinculada à versão que a respondeu,
sem repetir o conjunto para avaliar o comando de cancelamento.

## Referências e autoria

1. [Requisição e resposta em workflows MAF](https://learn.microsoft.com/en-us/agent-framework/workflows/human-in-the-loop).
2. [Cotas de modelos e deployments](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/quota).
3. [Criação de índices vetoriais e dimensões](https://learn.microsoft.com/en-us/azure/search/vector-search-how-to-create-index).
4. [Checkpoints de workflows MAF](https://learn.microsoft.com/en-us/agent-framework/workflows/checkpoints).
5. [Atualização e reconstrução de índices](https://learn.microsoft.com/en-us/azure/search/search-howto-reindex).

Texto inicial por GPT-6.1 Sol; código e testes por Claude Sonnet 5.5. Astra estava indisponível
na implementação. Revisão documental por gpt-6-astra (Astra), em 11 de outubro de 2026.
Essas escolhas não configuram o Copilot do aluno nem os deployments Azure.
