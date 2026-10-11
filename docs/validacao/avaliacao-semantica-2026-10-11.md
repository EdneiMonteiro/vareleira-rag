# Avaliação das evidências de resposta: 11 de outubro de 2026

**Autoria:** análise original por gpt-6-astra (Astra), em 11 de outubro de 2026.
Atualização na mesma data: busca por Claude Sonnet 5.5 e texto por GPT-6.1 Sol,
com Astra indisponível, por escolha explícita do mantenedor.

## Resultado e alcance

A análise original confirmou a pertinência dos dois gabaritos divergentes do
L200 v2 e registrou a avaliação semântica integral como bloqueada pela ausência
dos textos originais. Após a busca adicional descrita abaixo, essa revisão
histórica está **ENCERRADA COMO IRRECUPERÁVEL**. O alcance são as 50 respostas
finais: 18 do L200 v2 e 32 respostas HTTP (protocolo de transferência de
hipertexto) do L400 final v1, 16 por estratégia.

Nenhuma cópia dos textos originais foi localizada nesta busca local, e não há
fonte conhecida para reconstruí-los. Isso não comprova que sejam inexistentes
em todo lugar. O encerramento registra a falta de evidência recuperável
conhecida, não uma avaliação do conteúdo.

Nenhuma classificação histórica foi alterada.
Não houve nova geração, consulta Azure, ajuste de código ou repetição de teste final.

A análise original foi assistida por gpt-6-astra (Astra). Nem ela nem esta
atualização constituem homologação humana de conteúdo de seguros. O alcance
continua limitado ao universo sintético Vareleira 0.1.0.

| Material examinado | Cobertura disponível | Limite |
| --- | --- | --- |
| [Relatório L200 v2](l200-chat-avaliacao-final-v2.json) | 18 registros de tipo, situação, contagem de citações, tempo e uso; 16 conformes e dois divergentes | Sem texto da resposta, das citações ou dos trechos recuperados |
| [Comparação L400 v1](l400-comparacao-final-v1.json) | 16 registros por estratégia, 32 respostas HTTP; 16/16 conformes em cada uma | Sem texto da resposta, das citações ou dos trechos recuperados |
| Cópias privadas dos dois relatórios finais | Mesmos campos de resultado, sem textos adicionais | Não permitem reconstruir as respostas |
| Gabarito L200 v2 e fontes aprovadas | Reexame dos casos L200-V2-11 e L200-V2-14 | Examinar a expectativa não demonstra o que o modelo escreveu |

Os 50 registros foram conferidos quanto à presença de conteúdo suficiente para
revisão. **Zero deles contém a resposta completa disponível para essa finalidade.**
Isso é indisponibilidade de evidência, não 0% de fidelidade nem aprovação semântica.
Os 16/18 do L200 e 16/16 por estratégia do L400 continuam sendo resultados de
contrato: tipo, situação, contagens e invariantes de apresentação.

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

## Busca adicional pelos textos originais

Busca conduzida em 11 de outubro de 2026 por Claude Sonnet 5.5, somente de
leitura, sem rede, sem Azure e sem reexecutar qualquer conjunto. Esta
atualização registra o método e as contagens informadas nessa busca.
Uma primeira passagem usou um nome de campo incorreto, detectado na revisão
da própria redação, e foi refeita; o método e os números abaixo são os da
passagem corrigida.

1. Conferiu-se a função `interpretar_resposta` no
   [avaliador do chat](../../scripts/avaliar_chat.py), que guarda somente
   contagens e comparações, descartando texto e citações. A descrição inicial
   do [avaliador L400](../../scripts/avaliar_l400.py) também declara que não
   grava perguntas, corpos de resposta, textos nem citações. O desenho dos
   avaliadores explica por que os textos nunca chegaram aos relatórios nem
   às suas cópias privadas.
2. Foram varridos 33 históricos de eventos de sessões locais do Copilot CLI
   (interface de linha de comando), incluindo o da sessão que executou as
   rodadas finais, com cerca de 36 mil eventos no total.
3. Procuraram-se objetos JSON (notação de objetos JavaScript), por leitura
   estruturada, inclusive nos conteúdos com aspas escapadas, exigindo o
   conjunto exato de campos do contrato público definido por
   `CAMPOS_DA_RESPOSTA`: `aviso`, `aviso_simulacao`, `evidencias`, `id`,
   `id_requisicao`, `simulada`, `situacao`, `texto`, `tipo` e `uso`.
4. Também foram procurados os identificadores dos 34 casos finais:
   18 do L200 v2 e 16 do L400. As duas estratégias L400
   respondem aos mesmos 16 casos, totalizando 32 respostas nesse nível.

| Fonte examinada | O que continha | Conclusão |
| --- | --- | --- |
| Código dos dois avaliadores | Descarte do texto e das citações no avaliador do chat; declaração de não gravar esses conteúdos no L400 | Os relatórios e suas cópias privadas não receberam os textos originais |
| 32 dos 33 históricos locais | Nenhum objeto JSON com o conjunto exato de campos do contrato público | Nenhum corpo HTTP desse contrato foi identificado nesses históricos |
| Histórico da sessão das rodadas finais | 37 blocos com os nomes `situacao`, `texto`, `evidencias` e `id_requisicao`, em sua maioria código-fonte e diferenças de código; entre eles, três objetos JSON com o conjunto exato de campos | Os três corpos são respostas simuladas de testes locais de fumaça, não saídas dos conjuntos finais |
| Mesmos históricos: busca dos identificadores dos 34 casos finais | Identificadores somente em resumos e conferências, em mensagens do assistente, chamadas de ferramenta e suas saídas; nunca junto de um corpo HTTP | Nenhum texto original de resposta final foi localizado |

Os três objetos foram obtidos em testes locais de fumaça em 10 de outubro de
2026, contra um servidor local em modo de demonstração, com perguntas digitadas
no comando apenas para aqueles testes. O campo `simulada` é verdadeiro e não
há informação de uso de modelo. Nenhum desses objetos está no mesmo bloco de
um identificador de caso final, nem veio de uma execução do avaliador ou do
Azure. Portanto, eles não integram as 50 respostas finais nem permitem
preencher a lacuna semântica histórica.

**Limites da busca:**

- Esta atualização registra contagens e a origem dos três corpos simulados,
  sem reproduzir o conteúdo bruto dos históricos, perguntas ou respostas.
- O resultado se limita aos históricos locais, ao conjunto exato de campos
  do contrato público e aos identificadores procurados. Não prova
  inexistência dos textos em todos os formatos ou locais, nem em outras
  cópias de segurança.
- Fontes remotas não foram consultadas. Os registros de limpeza indicam que
  os recursos Azure das rodadas, inclusive os logs, foram removidos; o projeto
  do chat prevê não registrar perguntas nem respostas. Isso é uma inferência
  dos registros e do projeto, não uma nova verificação remota.
- Nada foi regenerado, reexecutado, reclassificado ou ajustado. Gabaritos,
  código, denominadores, relatórios e congelamentos permanecem como estavam.

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

## Orientação para avaliações futuras

Uma avaliação semântica futura precisa prever e autorizar, **antes da medição**,
a retenção privada e controlada das saídas sintéticas, dos trechos recuperados
e das referências. Ela exige uma versão própria e congelada do avaliador, com
correspondência entre saída, caso, estratégia e versão para permitir a revisão
descrita acima. Este registro não concede autorização de retenção.

O avaliador histórico não deve ser alterado: seu hash (resumo digital que
identifica a versão do código) consta dos relatórios. Preparar a retenção em
outra versão não autoriza repetir os conjuntos finais nem substituir as saídas
antigas. Perguntas e casos finais não são reproduzidos como exemplos nem usados
para desenvolvimento.

## Decisão

Registrar a revisão semântica integral histórica como **ENCERRADA COMO
IRRECUPERÁVEL**, porque os textos das 50 respostas finais não foram localizados
no alcance desta busca e não há fonte conhecida para reconstruí-los. A falta de
evidência não equivale a 0% de fidelidade nem a aprovação semântica; a avaliação
do conteúdo continua inconclusiva.

Conservar as duas divergências L200, sua análise de gabaritos, os gabaritos, o
código, os denominadores, os relatórios e os congelamentos.
Manter o fluxo convencional como padrão: a comparação L400 não
demonstrou ganho de conformidade e não permite concluir ganho semântico.
A publicação experimental deve expor essa lacuna, não anunciar fidelidade
semântica ou aprovação para produção.
