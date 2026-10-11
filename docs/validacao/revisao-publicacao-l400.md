# Revisão para publicação L400

Registro de 11 de outubro de 2026. Revisão por gpt-6-astra (Astra), a pedido
do mantenedor. Documentação e análise foram feitas diretamente, sem execução
do fluxo Document Swarm. A autoria inicial Sol/Sonnet permanece identificada.

## Escopo e correções

Os 28 guias foram lidos integralmente. A
[revisão L300](revisao-publicacao-l300.md) cobre os 21 guias anteriores;
os sete guias L400 receberam conferência contra o runtime, as interfaces de
linha de comando, a infraestrutura e os registros históricos.

| Guia L400 | Correção ou delimitação |
| --- | --- |
| 01 | Definição de RAG e tenant no primeiro uso; preparação da `.venv` e requisitos |
| 02 | CLI e HTTP definidos; comando remoto identificado como envio com consumo; distinção entre execução do runtime e invocação exata da CLI |
| 03 | Contingência não representa outra região; limites do roteiro público de implantação; teste local de tentativas e falhas |
| 04 | Origem das variáveis privadas; descritor não executa a promoção nem coleta provas; exemplo sintético não é evidência real |
| 05 | Teste final publicado não deve ser repetido; relatório sanitizado sem texto não permite revisão semântica integral |
| 06 | Gerador de carga privado não entregue; avaliador sequencial não substitui executor concorrente |
| 07 | Limpeza completa não implementada pelo helper público; inventário e roteiro administrativo exigidos |

As métricas e o histórico de falhas, correções, retomadas e limpeza não foram
reescritos. A comparação final é a do conjunto **v1**, executado na versão
corrigida do runtime; referências históricas a “V2” e “V3” no registro dizem
respeito às revisões de implementação/prova, não a um segundo conjunto final.

## Verificações locais

| Comando ou conferência | Resultado |
| --- | --- |
| `python -m unittest discover -s tests`, inicialmente no Python do sistema | Falhou: 27 módulos não importados por dependências ausentes |
| `.\.venv\Scripts\python.exe -m unittest discover -s tests` | 1.015 casos: 1.014 aprovados e um ignorado por permissões POSIX |
| `.\.venv\Scripts\python.exe -m pip check` | Sem dependências quebradas; nenhum pacote instalado |
| `node --check web\app.js` | Aprovado |
| `.\.venv\Scripts\python.exe scripts\gerenciar_ingestao_l300.py --etapa validar` | Quatro fontes aprovadas, hashes e classes conferidos, sem rede |
| `.\.venv\Scripts\python.exe scripts\operar_l300.py --etapa plano --fase rede --validar-bicep` | Plano e compilação locais aprovados |
| `.\.venv\Scripts\python.exe scripts\operar_l400.py --etapa planejar --validar-bicep` | Plano e compilação locais aprovados |
| `az bicep lint --file <arquivo>` e `az bicep build --file <arquivo> --stdout`, para cada `.bicep` em `infra` | Todos aprovados, lint sem avisos, Bicep 0.48.1; saída de build descartada |
| Links e âncoras locais da árvore L400 | 1.143 referências em 67 arquivos Markdown antes destes registros, sem falhas |
| Análise sintática dos exemplos PowerShell dos 28 guias | 201 blocos sem erros; conteúdo não executado |

As verificações são locais. Não foram emitidas novas perguntas aos modelos
Azure, nem feitas implantações, atribuições de acesso ou consultas de cobrança.
Referências externas não receberam nova auditoria integral; preços e disponibilidade
continuam vinculados às datas e limitações dos registros anteriores.

## Avaliação de respostas e limites

A [análise semântica disponível](avaliacao-semantica-2026-10-11.md) confirma a
pertinência dos dois gabaritos divergentes L200, sem alterar os rótulos medidos.
Os relatórios L200/L400 e suas cópias privadas não contêm as respostas completas;
portanto a fidelidade semântica das 50 saídas não pôde ser avaliada integralmente.
Nenhuma saída nova foi gerada para preencher essa lacuna.

Além das limitações herdadas da revisão L300, o cancelamento L400 continua por
processo e com uma réplica. A comparação 16/16 em ambas as estratégias não
demonstrou ganho de conformidade nem fidelidade semântica. A cobrança permanece
indisponível; publicação e CI não homologam produção.
