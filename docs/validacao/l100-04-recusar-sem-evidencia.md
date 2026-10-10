# L100, Desafio 04: registro de validação

Registro de trabalho da validação do [Desafio 04](../../desafios/L100/04-recusar-sem-evidencia.md): matriz de
testes, medições, correções e observações de operação. O guia do aluno traz a
[situação resumida](../../desafios/L100/04-recusar-sem-evidencia.md#situação-da-validação).

## Escopo e ambiente

| Item | Descrição |
| --- | --- |
| Data de referência | 9 de outubro de 2026 |
| Destino | O mesmo grupo de recursos exclusivo da validação do Desafio 03, excluído ao final. Os identificadores do ambiente não são publicados. |
| Execução | Sequência executada com apoio do GitHub Copilot CLI na estação do mantenedor. |
| Versões | Windows, Python 3.12.10, Azure CLI 2.89.0, `openai` 3.23.0, `azure-search-documents` 12.0.0 e as bibliotecas dos desafios anteriores. |
| Repetição dos comandos | Os 11 blocos de PowerShell do guia foram extraídos do próprio texto e executados linha a linha, com troca apenas do marcador de ID da assinatura, em PowerShell 7.6, em `brazilsouth`. |
| Aprovação do mantenedor | Confirmada em 9 de outubro de 2026 para o material existente; não representa nova execução dos testes. |

## Matriz de validação

| Verificação | Resultado |
| --- | --- |
| Testes automáticos (`python -m unittest discover -s tests`) | Passaram, sem acesso ao Azure, com `-X dev -W error`; 30 casos novos da política |
| Política básica (Etapa 1) | "Roubaram meu notebook na rua. O seguro paga?" com `--k 10` respondeu com "Não." logo no início, em todas as execuções, e em uma delas concluiu que "um notebook roubado na rua não está coberto". As fontes citadas eram válidas (cláusulas 5.1 e 3.4), então a conferência das fontes não reprovou |
| Política completa, pergunta documentada | Tipo `documentada`; duas a três evidências literais conferidas; 1.601 a 1.644 tokens de entrada e de 161 a 338 de saída |
| Política completa, caso individual | "O meu seguro cobre danos elétricos?" repetida cinco vezes: as cinco como contratação individual, com três evidências e o aviso fixo. "Roubaram meu notebook...": `--k 10` respondeu a regra geral (cláusula 5.1, item h) sem veredito, em uma execução (a repetição posterior mostrou veredito atenuado em 6 de 9; ver "Alterações posteriores à validação"); `--k 5` respondeu só a cobertura de roubo e furto qualificado, com o aviso |
| Política completa, recusas | "Quanto custa o seguro por mês?": sem evidência; "Qual é a capital da França?": fora de escopo; os dois com o texto do programa, 1.223 a 1.245 tokens de entrada e de 46 a 68 de saída |
| Política completa, pergunta ambígua | "Qual é o prazo?", "Está coberto?", "Quanto eu pago?" e "E se isso acontecer?": tipo `ambigua`, com uma pergunta de esclarecimento |
| Regra por palavras | "Como o meu corretor avisa um sinistro?": o modelo classificou como `documentada`, e a regra do programa mudou o tipo para contratação individual (falso positivo, com aviso desnecessário). "Meu seguro tem franquia para danos elétricos?": o modelo já classificou como contratação individual |
| Citação curta | Uma execução de "O meu seguro cobre danos elétricos?" foi descartada porque o modelo citou uma frase com menos de 20 caracteres; a regra passou a ignorar as citações curtas, e a instrução passou a pedir frases de pelo menos 20 caracteres. Depois da mudança, cinco execuções seguidas passaram |
| Tempo e tokens | De 11 a 15 s por pergunta; 1.223 a 2.565 tokens de entrada e 46 a 476 de saída |
| Resposta descartada por citação inventada | Não ocorreu no Azure; coberta só pelos testes automáticos |

## Correções feitas durante a validação

- As citações com menos de 20 caracteres deixaram de descartar a resposta: o programa as ignora e exige ao menos uma citação válida.
- A instrução ao modelo passou a pedir "uma frase inteira, com pelo menos 20 caracteres".
- A detecção de veredito passou a exigir pontuação depois do "Sim" ou do "Não" no início da resposta, para não tratar "Não há carência" como veredito.

## Observações de operação

- **Variação do modelo.** O texto das respostas varia a cada execução. Em uma execução da política básica, o modelo escreveu uma palavra em outro alfabeto no meio de uma frase em português; a política básica confere as fontes, não a qualidade do texto, e a política completa também não confere. A revisão humana do texto continua necessária.
- **Classificação.** "Quanto é a franquia?" foi tratada como `documentada`, e o modelo listou todas as franquias; a fronteira entre `documentada` e `ambigua` é uma decisão de produto.
- **Recuperação.** Com `--k 5`, a exclusão da cláusula 5.1 não chegou ao modelo em nenhuma execução; a política evitou o veredito, mas não trouxe a exclusão.

## Alterações posteriores à validação

Registro de 9 de outubro de 2026, feito durante os Desafios 05 a 07.

- **Conferência das citações.** A avaliação do [Desafio 06](l100-06-avaliar-respostas.md#o-defeito-que-a-medição-encontrou) mostrou que `normalizar`, em `scripts/lab_politica.py`, trocava cada marca de ênfase do Markdown por um espaço. Uma citação correta que terminava em negrito seguido de ponto (`...individual**.`) era comparada com `...individual .` e a resposta era descartada. Agora `*`, `_` e acento grave são removidos sem deixar espaço, e `#`, `|` e `>` viram separadores. Dois testes novos em `test_politica.py` cobrem a correção. O guia não precisou mudar por causa dela: ele já descreve a conferência como "ignorando marcas de Markdown (como `**`) e espaços repetidos".
- **Mensagem do 404 intermitente.** O cliente de geração mostra uma mensagem própria para o 404 "Subdomain does not map to a resource", descrita no [registro do Desafio 02](l100-02-indexar-documentos.md#alterações-posteriores-à-validação).
- **Credencial opcional.** O cliente de geração e o `perguntar.py` aceitam uma identidade de aplicação, usada no [Desafio 07](../../desafios/L100/07-identidade-da-aplicacao.md). Sem as novas opções, o comportamento é o mesmo.
- **Veredito atenuado (limite descoberto na repetição dos blocos).** No bloco 5 (caso do notebook, `--k 10`, política completa), a resposta abriu com "Em regra, não." e concluiu que o notebook roubado na rua "se encaixa nessa exclusão geral", ao contrário da execução da validação, registrada acima como "sem veredito". Uma amostra à parte, com a mesma pergunta e os mesmos argumentos (8 execuções), deu: 4 respostas que abriram com "Em regra, não."; 1 que concluiu que "situações como furto de notebook na rua entram nessa exclusão geral"; 1 em que o detector reconheceu o veredito e trocou o texto pela frase padrão; e 2 que explicaram a regra sem concluir. Com o bloco 5, são 6 de 9 execuções com um veredito atenuado que passou pelo detector, o qual reconhece só "Sim" ou "Não" seguidos de pontuação no início e algumas frases fixas (`seu seguro cobre`, `será indenizado` e semelhantes). O código não foi alterado: o Desafio 06 mediu a política atual, inclusive no conjunto de teste, uma única vez, e mudar o detector mudaria o texto mostrado e, com ele, os fatos contados. O guia passou a descrever o limite (Tecnologias e conceitos, item 4; Etapa 2.3; Conferência do resultado).

**Conferência.** Os blocos 1 a 11 do guia foram executados de novo, linha a linha, em PowerShell 7.6.6, sobre o grupo de recursos em que os Desafios 03 a 07 foram validados (18 linhas, sem falhas, com o veredito atenuado descrito acima). Todas as execuções com geração desta repetição (as dos blocos e a amostra de 8) ocorreram nos 16 minutos seguintes à exclusão do deployment de geração pelo bloco 14 do Desafio 03: o deployment excluído continuou respondendo nesse intervalo, como medido na [observação de operação do Desafio 03](l100-03-responder-com-fontes.md#observações-de-operação), e a repetição usou, na prática, o deployment que o guia pressupõe. Os demais resultados ficaram dentro dos registrados acima: tipos `documentada`, contratação individual, sem evidência, fora de escopo e ambígua nas mesmas perguntas; com `--k 5`, a resposta trouxe só a cobertura de roubo e furto qualificado, sem a exclusão; a regra por palavras mudou de novo o tipo de "Como o meu corretor avisa um sinistro?" (o falso positivo descrito acima); de 1.231 a 2.565 tokens de entrada e de 40 a 437 de saída. Na política básica (bloco 2), uma palavra em outro alfabeto apareceu de novo no meio de uma frase em português, como na observação de variação do modelo. Os testes automáticos da política (bloco 9) passaram com 32 casos, os 30 da validação e os 2 do normalizador. Uma resposta descartada por citação inventada continua coberta só pelos testes automáticos.

## Pendências

| Item | Situação | Ação para encerrar |
| --- | --- | --- |
| macOS, Linux e WSL | Pendente | Executar os comandos do guia nesses sistemas e registrar as diferenças de sintaxe |
| Python diferente do 3.12 | Pendente | Repetir as Etapas 1 a 4 com outra versão suportada |
| Windows PowerShell 5.1 | Pendente | A análise de sintaxe passou na versão 5.1.26100; falta executar os comandos nesse ambiente |
| Outros modelos de geração e amostra maior de perguntas | Pendente | Só o `gpt-5.4-mini` foi validado, com poucas perguntas por tipo; o Desafio 06 amplia a amostra |
| Resposta descartada por citação inventada no Azure | Pendente | Coberta só por testes automáticos |
| Apresentação de casos classificados como individuais | Conferida localmente e no Azure | Texto livre suprimido nesse caminho; comparações local e Azure posteriores separadas da medição histórica |
| Nova política na geração Azure | Medida em 10 de outubro de 2026 | Rodada autorizada com 24 perguntas do conjunto novo: 22 de 23 casos comparáveis conformes; nenhuma repetição ou ajuste pelo resultado |
| Prompts para o Copilot do guia, exemplo de pedido de mudança e modo construtor | Pendente | Executar no VS Code e registrar as respostas |
| Medição de custo | Pendente | Consultar o Cost Management depois de uma execução completa |
| Aprovação do conteúdo dos documentos sintéticos | Confirmada | Mantenedor, em 9 de outubro de 2026; registro no inventário |
| Aprovação do texto, do código e dos resultados do guia | Confirmada | Mantenedor, em 9 de outubro de 2026; as revisões por IA continuam identificadas separadamente |

## Revisão editorial

### Revisão inicial — Claude Sonnet 5.5

Revisão de 9 de outubro de 2026, feita por Claude Sonnet 5.5 no GitHub Copilot CLI, com verificação automatizada do texto do guia (termos informais, siglas sem definição no primeiro uso, ordem das referências, links e âncoras) e correções pontuais. Ao contrário da [revisão do Desafio 02](l100-02-indexar-documentos.md#revisão-editorial), não houve leitura integral do guia, categoria por categoria.

| Categoria | Alteração no guia |
| --- | --- |
| Siglas | CLI definida no primeiro uso |
| Termos informais | "quebrado" substituído por "inválido" na situação da validação |
| Próximos desafios | "Planejados, ainda sem desafio escrito" deu lugar a links para os Desafios 05 a 07 |
| Limites da política | Descrição do veredito atenuado que o detector não reconhece (ver "Alterações posteriores à validação") |

### Revisão integral — GPT-6.1 Sol

Revisão de 9 de outubro de 2026 contra o guia de estilo do mantenedor, com leitura completa do guia e
deste registro. Os objetivos e a tabela de condutas agora distinguem recusas de explicação geral com
aviso. A citação literal é apresentada como conferência da frase na fonte, separada da revisão
do sentido da resposta. O limite de vereditos atenuados foi preservado.

O mnemônico C-P-R foi ajustado para incluir a revisão do texto. A subseção 4.1 passou a identificar
o problema concreto, "Recuperação incompleta". O prompt de mínimo da citação deixou de proibir a
atualização do mesmo número nas instruções do modelo, que contradizia sua conferência.
Esse prompt revisado ainda não foi executado no Copilot. Os 11 blocos PowerShell, o código e as
medições permanecem preservados.

O guia foi relido após as correções e inspecionado na prévia Markdown local.
As [verificações integradas da revisão](l100-01-preparar-ambiente.md#revisão-editorial) incluem comparação
dos comandos e conferência de referências, tabelas, links e testes locais.

## Aprovação do material

O mantenedor confirmou a aprovação do material existente em 9 de outubro de 2026.
O limite do detector, inclusive os seis vereditos atenuados em nove execuções, continua registrado.
Não houve alteração do detector nem nova medição; a aprovação não promete ausência de vereditos.

## Reforço da política após o marco aprovado

O marco `8fa5f0c` conserva a implementação aprovada e os resultados Azure anteriores.
A correção `4eb0408`, solicitada pelo mantenedor para preparar a aplicação hospedada, remove
o detector de frases e suprime o texto livre em todo caso classificado como contratação individual.
Com evidências válidas, o programa mostra a introdução fixa, as citações e o aviso.
Respostas documentadas gerais, recusas, esclarecimentos e descartes mantêm seus caminhos.

A regra é compartilhada por `perguntar.py`, pelo agente do D05 e pelo avaliador do D06.
O classificador e a regra por palavras continuam falíveis. Um caso individual não reconhecido
pode seguir outro caminho; retirar texto livre não equivale a resolver essa classificação.
As citações também precisam de contexto e revisão.

Os testes locais da política passaram com 30 casos e os do agente com 38, usando MAF instalado
sobre transporte simulado. A suíte completa permaneceu com 330 testes.
O teste antigo que exigia texto livre individual foi substituído pela conferência do texto fixo,
inclusive para conclusões atenuadas e conclusões no fim da resposta.
Essa validação não repete as nove execuções Azure antigas nem substitui seu resultado.

Nenhum documento ou pergunta do conjunto antigo foi alterado. A nova avaliação é local,
com respostas candidatas sintéticas produzidas em contexto separado do implementador.
A primeira consulta de autorização para reconstrução Azure não recebeu resposta; nenhum recurso
foi criado naquele intervalo. O mantenedor autorizou posteriormente a validação Azure necessária.

### Comparação local e correção do gabarito

Os 24 casos foram escritos em contexto separado do implementador e congelados antes da comparação.
O arquivo original manteve seu conteúdo e hash. Ele usou `recusada` nos 12 casos individuais no
sentido de recusar a decisão de cobertura, mas o contrato do programa usa `respondida` quando
mostra orientação geral, citações e aviso.

A primeira comparação aceitou essa equivalência e apontou 24 de 24 na candidata. Esse resultado
nunca representa aprovação estrita. O avaliador foi corrigido para comparar o valor literal:
com o gabarito original, ambos os commits ficam em 12 de 24 quanto aos campos esperados, enquanto
a apresentação passa de 12 de 24 no marco para 24 de 24 na candidata. Os valores crus ficaram
preservados nos relatórios.

Um revisor separado, sem acesso à implementação ou às métricas, confirmou o erro de definição.
O arquivo `politica-casos-v2-contrato.json` altera somente esses 12 rótulos de situação e registra
a revisão de gabarito; perguntas, candidatos e citações permanecem iguais. Ele não é um novo
conjunto cego. A candidata continua no commit congelado `4eb0408`.

| Comparação local | Marco `8fa5f0c` | Candidata `4eb0408` |
| --- | --- | --- |
| Gabarito original, valores literais | 12 de 24 | 12 de 24 |
| Gabarito original, apresentação | 12 de 24 | 24 de 24 |
| Contrato corrigido, valores literais | 12 de 24 | 24 de 24 |
| Contrato corrigido, apresentação | 12 de 24 | 24 de 24 |

O avaliador recebe saídas sintéticas e os trechos que contêm as citações. As contagens medem
pós-processamento local, não qualidade da busca, geração ou respostas Azure. O erro de rótulo e
sua correção permanecem explícitos; nenhuma pergunta do teste histórico foi usada para ajuste.

Os relatórios derivados preservam a
[comparação estrita do gabarito original](politica-avaliacao-local-v2-estrita.json) e a
[comparação do contrato corrigido](politica-avaliacao-v2-contrato.json).
Eles registram os commits e hashes, sem perguntas, respostas candidatas ou citações.

Para reproduzir localmente a comparação, a partir da raiz e escolhendo uma saída que ainda não existe:

```powershell
.\.venv\Scripts\python.exe scripts\avaliar_politica_local.py --casos dados\l100\avaliacao-independente\politica-casos-v2-contrato.json --baseline 8fa5f0c --candidata 4eb0408 --relatorio outputs\politica-comparacao.json
```

A pasta de saída deve existir. Esse comando foi executado com saída na pasta privada da sessão;
o caminho acima é um exemplo local. O contrato corrigido retornou código 0; o original, sem
equivalência de situações, retornou código 3 e conserva suas divergências.

## Nova rodada Azure com a política congelada

Após autorização explícita do mantenedor, a base L100 foi reconstruída no destino de teste anterior.
Em 10 de outubro de 2026, um executor em contexto separado fez uma resposta para cada uma das
24 perguntas de `politica-casos-v2-contrato.json`. Usou recuperação obrigatória híbrida, `k=3`,
esforço `low`, índice L100 com 54 trechos e código conferido contra o commit `4eb0408`.
Os candidatos sintéticos do conjunto não foram enviados ao modelo.

| Critério da rodada | Resultado |
| --- | --- |
| Decisões obtidas | 24 de 24; nenhum erro Azure ou de formato |
| Tipo, situação e origem do texto esperados | 22 de 23 casos comparáveis conformes |
| Caso não comparável | POL-18: a citação fabricada é estímulo local e não foi injetada; seu descarte artificial não é gabarito para geração real |
| Divergência | POL-19: esperado `ambigua`/`esclarecimento`, observado `sem_evidencia`/`recusada` |
| Casos individuais | 12 de 12 classificados como individuais, com texto fixo, aviso e ao menos uma citação mantida |
| Apresentação conforme a decisão tomada | 24 de 24; essa medida não julga se a decisão estava correta |
| Citações de referência presentes nos três trechos | 24 de 34; diagnóstico de recuperação, não nota de fidelidade |
| Pedidos HTTP | 73 com status 200: 24 de embeddings, 24 de geração e 25 de busca, incluindo uma contagem prévia |
| Tokens | 1.025 de embeddings, 33.268 de entrada e 5.578 de saída; 1.535 de raciocínio já incluídos na saída |
| Tempo | Média de 3,07 s, máximo de 8,77 s por pergunta; 74 s para a rodada |

O [relatório sanitizado](politica-avaliacao-azure-v1.json) preserva hashes, configuração, contagens e
resultados por identificador, sem perguntas, texto do modelo, citações ou identificadores do destino.
O executor não repetiu perguntas nem alterou código ou gabarito. O retorno de geração identificou
o deployment `geracao`, e não comprovou a versão do modelo; a configuração do recurso foi conferida
separadamente na reconstrução.

### Formato dos bytes e reprodução pela release

Os relatórios registram o hash dos bytes efetivamente lidos na árvore de trabalho Windows.
O Git normaliza os finais de linha conforme `.gitattributes`; a exportação da release usa LF.
O JSON e seus rótulos permanecem iguais, mas o checksum de bytes CRLF difere do checksum de bytes LF.

| Arquivo | SHA-256 dos bytes avaliados no Windows | SHA-256 dos bytes Git/LF da release |
| --- | --- | --- |
| `politica-casos-v1.json` | `c9e6d0110bb8aa9eaa0f66b65f6c1633ce0c0d3fbead5edef957823cef079138` | `f8ebedee3ba4ecd1a401ec2d84931a38864124da24c7cd405bcabf408ae52219` |
| `politica-casos-v2-contrato.json` | `de94f21c133efc09fada5e175bc9432a6a6efdd6362401485c0b3e4161bb9cf2` | `d02c473f7c4004e38c767affa266dea60c315e649db63621081b38e155dc5bf2` |

Essa distinção foi conferida numa exportação do commit `8bafb69`, cuja suíte exata passou com
341 testes. Não houve edição de perguntas, candidatos, citações ou situações por causa da medição.
Ao comparar hashes, use o formato de bytes indicado, em vez de alterar o conjunto para obter um valor esperado.

Essa rodada mede o fluxo fixo de busca, geração e política, não a escolha de ferramentas pelo agente
MAF, fidelidade semântica integral ou repetibilidade. A revisão de rótulos do conjunto v2 continua
explícita. O resultado não substitui as medições históricas nem o teste D06, que não foi repetido.

## Autoria

Código, testes e texto produzidos com Claude Sonnet 5.5, no GitHub Copilot CLI. O Astra, modelo preferido do
mantenedor para a documentação, não estava disponível na sessão. O modelo de autoria é independente do modelo
que o aluno escolhe no Copilot e dos deployments da aplicação (`text-embedding-3-small` e `gpt-5.4-mini`).
