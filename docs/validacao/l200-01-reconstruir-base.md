# L200, Desafio 01: registro de validação

Registro do [guia de reconstrução](../../desafios/L200/01-reconstruir-base.md).
Os identificadores do destino e as saídas brutas permanecem em evidências privadas.

## Escopo e ambiente

| Item | Registro |
| --- | --- |
| Data | 10 de outubro de 2026 |
| Autorização | Mantenedor autorizou executar as etapas de publicação e avaliação e, depois, implementar e testar o L200, incluindo Azure quando necessário |
| Destino | Assinatura de teste anteriormente indicada; grupo exclusivo comprovadamente ausente antes desta rodada |
| Preservação | Inventário dos grupos e papéis preexistentes guardado antes da criação |
| Ambiente | Windows, PowerShell 7.6.6, Python 3.12.10, Azure CLI 2.89.0 e Bicep 0.48.1 |
| Modelos da base | `text-embedding-3-small`, versão `1`, 1.536 dimensões; `gpt-5.4-mini`, versão `2026-03-17`; região `brazilsouth` |
| Separação de autorizações | Aprovação humana do material L100 em 9 de outubro permanece histórica; a nova mensagem autorizou trabalho e execução L200, não uma aprovação retroativa de seus resultados |

## Reconstrução executada

| Verificação | Resultado |
| --- | --- |
| Destino, tenant e grupo | Conferidos antes da execução; nenhuma troca silenciosa da assinatura padrão |
| Infraestrutura L100 D03 | Reconstruída com `infra\levels\l100-desafio03.bicepparam`; 11 criações no plano e implantação concluída em aproximadamente 106,5 s |
| Armazenamento e proteção | Conta e contêiner autenticados com Entra ID, sem acesso anônimo nem chaves de conta |
| Documentos | Três blobs enviados e conferidos contra inventário, versão, tamanho e hash |
| Índice Python | `vareleira-lar-l100`, 54 trechos conferidos |
| Documentos locais | Textos, versões e hashes aprovados preservados; novos conjuntos de avaliação ficaram fora do conteúdo recuperável |
| Tag L100 | `v0.1.0-l100` conferida no commit `d4a93cca4c43e1587ae1b9203a06bd450412e231` |
| Resultado histórico D06 | Não repetido; a reconstrução não mudou suas métricas |

A base foi criada novamente a partir de arquivos versionados. A identidade e o cofre temporários
do fechamento L100 anterior não foram recuperados.

## Verificações locais integradas

Rodada intermediária do coordenador, após integrar ingestão, chat e infraestrutura:

| Comando exato | Resultado |
| --- | --- |
| `.\.venv\Scripts\python.exe -B -m unittest discover -s tests -q` | Passou: 547 testes, sem Azure |
| `.\.venv\Scripts\python.exe -m pip check` | Passou: nenhuma dependência quebrada |
| `az bicep lint --file infra\l200.bicep` | Passou, sem avisos |
| `az bicep build --file infra\l200.bicep --stdout` | Passou; saída gerada não foi versionada |
| `az bicep build-params --file infra\levels\l200.bicepparam --stdout` | Passou com nomes recebidos por variáveis e sem segredo real |
| `node --check web\app.js` | Passou |

Essa contagem antecede o avaliador HTTP adicional do Desafio 06. O fechamento final registra
a suíte após os últimos arquivos e correções, sem somar execuções repetidas como casos novos.

Depois do avaliador e das correções de limite de `k` e identificadores longos:
`.\.venv\Scripts\python.exe -m unittest discover -s tests` passou com **592 testes** em 60,6 s.
`pip check`, lint/build de `infra\main.bicep` e `infra\l200.bicep` e `node --check web\app.js` passaram.
As verificações mecânicas dos 14 guias conferiram 159 blocos PowerShell sem erro de sintaxe.
Os 108 blocos originais L100 foram preservados.

Na limpeza, o verificador L100 recebeu inicialmente um comando documental sem o obrigatório
`--modelos` e parou antes de consultar serviços. A família de comandos foi corrigida nos guias L200
01, 03 e 07; a execução com o parâmetro passou. Essa correção foi documental e não mudou código,
gabarito ou resultados da rodada final.

## Limites

O ambiente de implantação tinha permissões suficientes para criar recursos e atribuir papéis.
O exercício não demonstrou todos os cenários de políticas corporativas, cotas e papéis administrativos
menores. macOS, Linux, Windows PowerShell 5.1 e outros modelos não foram executados nesta rodada.

A consulta de custos do dia retornou HTTP 200 com zero linhas disponíveis naquele momento.
Esse retorno não confirma custo zero nem total L200. A limpeza e a preservação final ficam no
[registro do Desafio 07](l200-07-operar-recuperar-limpar.md).

## Autoria e revisão

Implementação por Claude Sonnet 5.5. Guias e coordenação de validação por GPT-6.1 Sol, contra o guia de
estilo do mantenedor. Astra indisponível; nenhum Document Swarm, workflow ou monitor foi executado.
As verificações locais, execução Azure e revisão humana têm registros distintos.
