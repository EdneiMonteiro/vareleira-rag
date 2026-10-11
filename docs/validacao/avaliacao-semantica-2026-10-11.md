# Avaliação das evidências de resposta: 11 de outubro de 2026

## Resultado e alcance

A análise confirmou a pertinência dos dois gabaritos divergentes do L200 v2,
mas **a avaliação semântica integral das respostas está bloqueada pela ausência
dos textos originais**. Nenhuma classificação histórica foi alterada.
Não houve nova geração, consulta Azure, ajuste de código ou repetição de teste final.

Esta é uma análise assistida por gpt-6-astra (Astra), não uma homologação humana
de conteúdo de seguros. Ela se limita ao universo sintético Vareleira 0.1.0.

| Material examinado | Cobertura disponível | Limite |
| --- | --- | --- |
| [Relatório L200 v2](l200-chat-avaliacao-final-v2.json) | 18 registros de tipo, situação, contagem de citações, tempo e uso; 16 conformes e dois divergentes | Sem texto da resposta, das citações ou dos trechos recuperados |
| [Comparação L400 v1](l400-comparacao-final-v1.json) | 16 registros por estratégia, 32 respostas HTTP; 16/16 conformes em cada uma | Sem texto da resposta, das citações ou dos trechos recuperados |
| Cópias privadas dos dois relatórios finais | Mesmos campos de resultado, sem textos adicionais | Não permitem reconstruir as respostas |
| Gabarito L200 v2 e fontes aprovadas | Reexame dos casos L200-V2-11 e L200-V2-14 | Examinar a expectativa não demonstra o que o modelo escreveu |

Os 50 registros foram conferidos quanto à presença de conteúdo suficiente para
revisão. **Zero deles contém a resposta completa disponível para essa finalidade.**
Isso é indisponibilidade de evidência, não 0% de fidelidade nem aprovação semântica.
Os 16/18 do L200 e 16/16 por estratégia do L400 continuam sendo resultados de contrato.

## Divergências L200

As perguntas finais permanecem somente no conjunto de avaliação, sem reprodução
neste registro ou em prompts de desenvolvimento.

| Caso | Observado no relatório | Análise da expectativa | O que continua desconhecido |
| --- | --- | --- | --- |
| L200-V2-11 | `sem_evidencia` / `recusada`, zero citações; esperado `contratacao_individual` / `respondida` | A cláusula 7.3 das Condições Gerais contém orientação geral pertinente, condicionada à apólice individual. As cláusulas 1.2 e 1.4 impedem concluir o estado de uma contratação. O caminho individual, com introdução e aviso fixos e evidência geral, é coerente com essa restrição. O gabarito não exige confirmar cancelamento ou cobertura. | Não é possível atribuir a recusa à recuperação, à classificação ou a outra etapa sem os trechos e a saída originais. A presença da regra no corpus não prova que ela foi recuperada. |
| L200-V2-14 | `documentada` / `respondida`, uma citação; esperado `ambigua` / `esclarecimento` | As cláusulas 7.3 e 9.6 tratam de fluxos distintos de pagamento. O Glossário também distingue prêmio e indenização. Pedir o referente é consistente com o contrato de esclarecimento do conjunto. | Uma citação contada não identifica qual sentido foi escolhido. Sem o texto, não se pode afirmar que houve regra inventada, escolha unilateral ou explicação correta dos dois sentidos. |

Fontes desta análise: [Condições Gerais](../../dados/l100/documentos/vareleira-lar-condicoes-gerais-v1.0.md),
especialmente cláusulas 1.2, 1.4, 7.3 e 9.6, e
[Glossário](../../dados/l100/documentos/vareleira-lar-glossario-v1.0.md), verbetes
Apólice individual, Prêmio e Indenização. As fontes não foram alteradas.
A [correção L200](l200-correcao-v2.md) conserva a explicação histórica e seus resultados.

## Critério para uma revisão semântica completa

Uma revisão por resposta precisa conferir se cada afirmação é sustentada pela
fonte citada, se condições e exceções relevantes foram preservadas, se a resposta
atende à pergunta e se evita uma conclusão individual não autorizada.
Contar citações e conferir o formato não atende a esses critérios.

Para concluir a revisão histórica, é necessário recuperar as saídas **originais**
da rodada, com correspondência comprovada entre caso, estratégia e versão.
Não se deve reexecutar os casos nem redigir respostas substitutas para preencher
a lacuna. Se essas saídas não foram preservadas, essa revisão histórica permanece
inconclusiva. Em uma avaliação futura, a retenção privada das saídas sintéticas,
dos trechos e das referências precisa ser prevista e autorizada antes da medição.

O acesso aos dois casos finais nesta análise os torna conhecidos neste contexto.
Eles não devem orientar alterações do classificador ou se tornar casos de
desenvolvimento. Eventuais mudanças exigem desenvolvimento separado, novo
congelamento e avaliação própria, sem descartar resultados desfavoráveis.

## Decisão

Conservar as duas divergências L200, os denominadores, os relatórios e os
congelamentos. Manter o fluxo convencional como padrão: a comparação L400 não
demonstrou ganho de conformidade e não permite concluir ganho semântico.
A publicação experimental deve expor essa lacuna, não anunciar fidelidade
semântica ou aprovação para produção.
