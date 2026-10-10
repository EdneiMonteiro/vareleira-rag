# L100, Desafio 05: registro de validação

Registro de trabalho da validação do [Desafio 05](../../desafios/L100/05-agente-com-maf.md): matriz de
testes, séries de medição, correções e observações de operação. O guia do aluno traz a
[situação resumida](../../desafios/L100/05-agente-com-maf.md#situação-da-validação).

## Escopo e ambiente

| Item | Descrição |
| --- | --- |
| Data de referência | 9 de outubro de 2026 |
| Destino | O mesmo grupo de recursos exclusivo da validação dos Desafios 01 a 04, excluído ao final. Os identificadores do ambiente não são publicados. |
| Execução | Sequência executada com apoio do GitHub Copilot CLI na estação do mantenedor. |
| Versões | Windows, Python 3.12.10, Azure CLI 2.89.0, `agent-framework-core` 1.21.0, `agent-framework-openai` 1.15.0, `openai` 3.23.0, `pydantic` 2.13.5, `azure-search-documents` 12.0.0 e as bibliotecas dos desafios anteriores. |
| Repetição dos comandos | Os 11 blocos de PowerShell do guia (23 linhas de comando) foram extraídos do próprio texto e executados linha a linha, com troca apenas do marcador de ID da assinatura, em PowerShell 7.6, em `brazilsouth`, duas vezes: a segunda com o código final. Nas duas, as 23 linhas terminaram com o código esperado: 2 nas duas linhas do bloco 10, que provocam a falha de propósito, e 0 nas demais. A repetição confere os códigos de saída; o conteúdo das respostas varia (veja a tabela das repetições). |
| Aprovação do mantenedor | Confirmada em 9 de outubro de 2026 para o material existente; não representa nova execução dos testes. |

## Matriz de validação

| Verificação | Resultado |
| --- | --- |
| Testes automáticos (`python -m unittest discover -s tests`) | Passaram, sem acessar o Azure, com `-X dev -W error`; 36 casos novos em `test_agente.py`. Eles executam o MAF e a biblioteca da OpenAI de verdade e trocam só o transporte HTTP por `ServicoRespostasFalso` (`tests\support.py`) |
| Dependências | `pip check` sem conflitos. O resolvedor instalou `agent-framework-core` 1.21.0 e `agent-framework-openai` 1.15.0 com o `openai` 3.23.0 e o `pydantic` 2.13.5 que o projeto já usava |
| API do MAF, verificada ao vivo antes do código | `Agent` com `OpenAIChatClient`: `credential=AzureCliCredential()` com `azure_endpoint` (sem `api_version`, com `v1` ou com `preview`) e com `base_url` terminada em `/openai/v1/` funcionaram nas quatro formas. `api_key` com um provedor de token síncrono falhou (`object str can't be used in 'await' expression`). `@tool` com `Annotated` gera o esquema da ferramenta; `response_format` aceita o esquema JSON em dicionário e `finish_reason` vale `length` quando o limite de saída corta a resposta |
| Tráfego HTTP real do MAF | `POST /openai/v1/responses` com `store: false`, `reasoning`, `max_output_tokens`, `text.format` (o esquema), `parallel_tool_calls: false`, `tools` (nome, descrição e esquema) e `include: ["reasoning.encrypted_content"]`, que o MAF acrescenta para repetir o raciocínio sem estado no servidor. A segunda requisição repete a pergunta, o item de raciocínio, a chamada da ferramenta e o resultado dela. A resposta traz `model` igual ao nome do deployment |
| Recuperação obrigatória | "Qual é a franquia da cobertura de danos elétricos?": `documentada` em todas as execuções (3 da série e 1 de cada repetição dos blocos), com 1.644 tokens de entrada e de 160 a 215 de saída |
| Agente com ferramenta, pergunta composta | Ver as séries abaixo |
| Perguntas sem busca | "Qual é a capital da França?": `fora_de_escopo` em 5 de 5 execuções (3 da série e 2 das repetições), sem chamar a ferramenta, 947 tokens de entrada. "Qual é o prazo?": `ambigua` em 5 de 5, sem chamar a ferramenta, 945 tokens de entrada |
| Caso individual | "Roubaram meu notebook na rua. O seguro paga?": `contratacao_individual` com aviso fixo e uma busca nas execuções registradas, com 2.676 a 2.930 tokens de entrada. Uma execução trouxe a frase "a situação descrita na rua não se enquadra nessa cobertura", que conclui sobre o caso e passa pela regra por palavras do Desafio 04 (falso negativo) |
| Pergunta sem evidência | "Quanto custa o seguro por mês?": uma busca e `sem_evidencia` nas execuções exploratórias |
| Agente que responde sem buscar sobre o produto | Não ocorreu no Azure em nenhuma execução; coberto por testes automáticos |
| Resposta descartada pela verificação | Três descartes (código 3) em mais de 100 execuções com a ferramenta: um nas execuções exploratórias com a pergunta composta (a citação de `VLAR-CG-1_0-006` não aparecia literalmente no trecho) e dois no ciclo de depuração com `--maximo-de-buscas 1` (a causa não foi registrada). O programa não mostrou nenhuma dessas respostas |
| Falha da busca | Deployment de embeddings inexistente (`--deployment inexistente`): `[ERRO]` com código 2 e a orientação do Desafio 02, sem resposta do agente. Com `--detalhes`, o registro do MAF mostra duas tentativas da ferramenta e a linha "returning an error result to the model" |
| Deployment de geração inexistente | `[ERRO] O deployment de geração 'inexistente' não foi encontrado` com código 2, nos dois modos de recuperação |
| Erros não provocados no Azure | 401, 403, 429, filtro de conteúdo e tempo esgotado: cobertos só por testes automáticos |
| Limpeza | Ver o registro do último desafio: o grupo é excluído uma vez, depois de todos os desafios |

### Séries de medição

Pergunta composta: "O seguro cobre alagamento e quantas vezes posso acionar a assistência 24 horas?" Esforço `low`, modo `hibrida`, deployment `geracao`.

| Configuração | Execuções | Tipo | Buscas | Tokens de entrada | Tokens de saída | Tempo |
| --- | --- | --- | --- | --- | --- | --- |
| Obrigatória, `k=5` | 5 | `documentada` em 5 | 1, do programa | 1.414 | 228 a 312 | 13,1 a 15,4 s |
| Ferramenta, `k=5`, até 2 buscas | 5 | `documentada` em 5 | 2 em 4 execuções, 1 em 1 | de 5.566 a 5.996 com 2 buscas; 2.809 com 1 | 304 a 407 | 15,9 a 22,0 s |
| Ferramenta, `k=5`, até 1 busca | 12 | `documentada` em 3, `sem_evidencia` em 7, `ambigua` em 2 | 1 | 2.732 a 3.120 | 199 a 578 | 13,3 a 17,4 s |
| Obrigatória, `k=2` | 5 | `sem_evidencia` em 5 | 1, do programa | 1.108 | 183 a 442 | 11,9 a 15,9 s |
| Ferramenta, `k=2`, até 2 buscas | 5 | `documentada` em 4, `sem_evidencia` em 1 | 2 | de 3.753 a 4.043 | 286 a 448 | 15,4 a 18,6 s |

Na primeira execução com a ferramenta, o uso foi de 5.439 tokens de entrada. Com `k=2`, a busca única do programa devolveu `VLAR-CG-1_0-006` e `VLAR-FAQ-1_0-003`, os dois sobre a assistência 24 horas, em todas as execuções em que a lista foi registrada; o trecho `VLAR-FAQ-1_0-011`, sobre alagamento, ficou de fora.

Repetições dos blocos do guia (a pergunta composta, em quatro dos comandos):

| Bloco e comando | 1ª repetição | 2ª repetição |
| --- | --- | --- |
| 5, padrão (`k=5`, até 2 buscas) | `documentada`, 2 buscas, 6.261 tokens | `sem_evidencia`, 1 busca, 2.737 tokens |
| 8, obrigatória com `--k 2` | `sem_evidencia`, 1.108 tokens | `sem_evidencia`, 1.108 tokens |
| 8, ferramenta com `--k 2` | `sem_evidencia`, 3.972 tokens | `documentada`, 2 buscas, 3.736 tokens |
| 9, `--maximo-de-buscas 1` | 0 evidências (tipo não registrado), 2.817 tokens | `sem_evidencia`, 2.737 tokens |

O guia soma a série e as duas repetições nas tabelas das Etapas 4.1 e 4.2 do modo padrão e do `k=2`.

Perguntas simples, `k=5`:

| Pergunta | Configuração | Execuções | Tipo | Buscas | Tokens de entrada | Tempo |
| --- | --- | --- | --- | --- | --- | --- |
| Franquia de danos elétricos | Obrigatória | 3 | `documentada` em 3 | 1, do programa | 1.644 | 12,0 a 13,5 s |
| Franquia de danos elétricos | Ferramenta | 3 | `documentada` em 3 | 1 | 3.087 | 13,2 a 13,7 s |
| Capital da França | Ferramenta | 3 | `fora_de_escopo` em 3 | 0 | 947 | 5,9 a 6,9 s |
| Qual é o prazo? | Ferramenta | 3 | `ambigua` em 3 | 0 | 945 | 7,2 a 10,4 s |

Ciclo de uma busca com o rastro registrado (8 execuções, `k=5`):

| Execução | Tipo | `VLAR-FAQ-1_0-011` entre os trechos |
| --- | --- | --- |
| 1 | `documentada` | Sim |
| 2, 3, 4 e 7 | `sem_evidencia` | Não |
| 5 | `ambigua` | Não |
| 6 | `documentada` | Não |
| 8 | Erro de leitura da resposta (veja abaixo) | Sem rastro |

A entrada de uma busca (de 2.732 a 3.120 tokens) soma duas idas ao modelo: a primeira, com cerca de 950 tokens de instruções, ferramenta e pergunta, e a segunda, com esses mesmos tokens mais o pedido da ferramenta e os cinco trechos.

## Correções feitas durante a validação

- **Texto antes da ferramenta.** `AgentResponse.text` junta o texto de todas as mensagens do laço, e o MAF só lê a última mensagem do assistente para preencher `value`. O programa passou a ler também apenas a última mensagem do assistente que tem texto (`texto_final`). Uma execução com `--maximo-de-buscas 1` terminou com "O modelo devolveu uma resposta fora do formato esperado". O erro não reproduziu em 50 execuções seguidas com o código anterior à correção, e a causa real daquela execução não foi confirmada. O teste `test_texto_escrito_antes_da_ferramenta_nao_entra_na_resposta_final` reproduz o mecanismo (um texto escrito pelo modelo antes de pedir a ferramenta) e falhava com o erro de formato antes da correção.
- **404 intermitente do serviço de modelos.** Ver as observações de operação.
- **Registro técnico do MAF.** Sem `--detalhes`, `lab_comum.executar_com_tratamento` oculta o registro do logger `agent_framework`, que imprimia "Function failed. Error: ..." antes da mensagem do programa.
- **Lista de trechos vazia.** O programa deixou de imprimir "Nenhum trecho recuperado." quando o agente responde sem buscar.

## Observações de operação

- **404 intermitente nos embeddings.** O endpoint `/openai/v1/embeddings` do recurso respondeu HTTP 404 ("Subdomain does not map to a resource") de forma intermitente, com o recurso, o deployment e o token corretos. Em um teste com HTTP direto, 6 de 12 pedidos falharam na rota v1 de embeddings; a rota clássica de embeddings (`/openai/deployments/<nome>/embeddings`) e a rota `responses` do mesmo recurso não falharam (12 de 12 em cada uma). Em processos novos, 14 de 26 chamadas de embeddings falharam; 16 de 20 chamadas em paralelo falharam; 20 chamadas seguidas pelo mesmo cliente não falharam. O programa passou a repetir esse erro (até 6 vezes, com espera crescente) e a abrir uma conexão nova a cada pedido. Depois da correção, 40 de 40 chamadas passaram, 3 delas com uma repetição. A causa não foi identificada; o comportamento depende do serviço, e a repetição deve ser reavaliada quando ele mudar.
- **Autenticação do MAF.** O cliente aceita `credential=AzureCliCredential(...)`. A opção `api_key` com um provedor de token síncrono falha porque o cliente espera uma função assíncrona.
- **Limites do laço.** Os limites do MAF são de melhor esforço (a documentação os descreve como conferidos depois de cada lote de chamadas). Os testes automáticos mostram o comportamento no limite: a requisição seguinte chega com `tool_choice` igual a `none`.
- **Erros da ferramenta.** O MAF devolve ao modelo um aviso genérico quando a ferramenta falha ("returning an error result to the model") e não repassa o erro ao programa; por isso a ferramenta guarda o erro e o programa o apresenta no lugar da resposta.
- **Modo de desenvolvimento do Python.** Com `-X dev`, o asyncio imprime avisos de retorno lento ("Executing <Task ...> took 0.4 seconds"). Não são erros e não aparecem sem `-X dev`.
- **Variação do modelo.** O texto das respostas, as consultas da ferramenta e o número de buscas variam entre execuções; os números das tabelas são faixas medidas, não garantias.

## Pendências

| Item | Situação | Ação para encerrar |
| --- | --- | --- |
| macOS, Linux e WSL | Pendente | Executar os comandos do guia nesses sistemas e registrar as diferenças de sintaxe |
| Python diferente do 3.12 | Pendente | Repetir as Etapas 1 a 5 com outra versão suportada |
| Windows PowerShell 5.1 | Pendente | A análise de sintaxe passou na versão 5.1.26100; falta executar os comandos nesse ambiente |
| Outros modelos de geração, outras versões do MAF e outras perguntas | Pendente | Só o `gpt-5.4-mini` e as versões fixadas foram validados; o Desafio 06 amplia a amostra |
| Agente que responde sem buscar sobre o produto, no Azure | Pendente | Coberto só por testes automáticos |
| Causa do erro de leitura da resposta e dos dois descartes do ciclo de depuração | Pendente | Registrar o texto bruto quando ocorrer de novo |
| Causa do 404 intermitente do serviço de modelos | Pendente | Reavaliar a repetição e a conexão nova quando o serviço mudar |
| 401, 403, 429, filtro de conteúdo e tempo esgotado no Azure | Pendente | Cobertos só por testes automáticos; provocar cada caso em ambiente de teste |
| Prompts para o Copilot do guia, exemplo de pedido de mudança e modo construtor | Pendente | Executar no VS Code e registrar as respostas |
| Medição de custo | Pendente | Consultar o Cost Management depois de uma execução completa |
| Aprovação do conteúdo dos documentos sintéticos | Confirmada | Mantenedor, em 9 de outubro de 2026; registro no inventário |
| Aprovação do texto, do código e dos resultados do guia | Confirmada | Mantenedor, em 9 de outubro de 2026; as revisões por IA continuam identificadas separadamente |

## Revisão editorial

### Revisão inicial — Claude Sonnet 5.5

Revisão de 9 de outubro de 2026, feita por Claude Sonnet 5.5 no GitHub Copilot CLI, com verificação automatizada do texto do guia (termos informais, siglas sem definição no primeiro uso, ordem das referências, links e âncoras) e correções pontuais. Ao contrário da [revisão do Desafio 02](l100-02-indexar-documentos.md#revisão-editorial), não houve leitura integral do guia, categoria por categoria.

| Categoria | Alteração no guia |
| --- | --- |
| Siglas | CLI (*Command-Line Interface*) e SDK (*Software Development Kit*) definidas no primeiro uso |
| Termos informais | "quebrada" e "quebrado" substituídos por "com falha" e "inválido" |
| Próximos desafios | "Planejados, ainda sem desafio escrito" deu lugar a links para os Desafios 06 e 07 |

### Revisão integral — GPT-6.1 Sol

Revisão de 9 de outubro de 2026 contra o guia de estilo do mantenedor, com leitura completa do guia e
deste registro. As correções retiram a garantia de fidelidade atribuída à conferência de citações e
identificam os limites de classificação e completude. Referências de consumo continuam limitadas às
perguntas e configurações medidas, sem uma razão universal de custo.

O guia mantém tabelas de comparação úteis ao exercício; a composição das séries e as tentativas
individuais ficam neste registro. A tabela das duas formas de recuperação ganhou um cabeçalho
descritivo, e as linhas de custo repetem o nome da pergunta para permitir leitura independente.
Comandos, código e números foram preservados; as bibliotecas reais e o transporte simulado dos testes
foram descritos separadamente.

O guia foi relido após as correções e inspecionado na prévia Markdown local.
As [verificações integradas da revisão](l100-01-preparar-ambiente.md#revisão-editorial) incluem comparação
dos comandos e conferência de referências, tabelas, links e testes locais.

## Aprovação do material

O mantenedor confirmou a aprovação do material existente em 9 de outubro de 2026.
Código, configuração e séries medidas permanecem iguais. Essa confirmação não amplia as
permissões da ferramenta do agente nem comprova a fidelidade de todas as respostas.

## Autoria

Código, testes e texto produzidos com Claude Sonnet 5.5, no GitHub Copilot CLI. O Astra, modelo preferido do
mantenedor para a documentação, não estava disponível na sessão. O modelo de autoria é independente do modelo
que o aluno escolhe no Copilot e dos deployments da aplicação (`text-embedding-3-small` e `gpt-5.4-mini`).
