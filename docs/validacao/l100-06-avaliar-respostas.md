# L100, Desafio 06: registro de validação

Registro de trabalho da validação do [Desafio 06](../../desafios/L100/06-avaliar-respostas.md): matriz de
testes, séries de medição, o defeito que a medição encontrou, a ordem das medições e as observações de
operação. O guia do aluno traz a [situação resumida](../../desafios/L100/06-avaliar-respostas.md#situação-da-validação).

## Escopo e ambiente

| Item | Descrição |
| --- | --- |
| Data de referência | 9 de outubro de 2026 |
| Destino | O mesmo grupo de recursos exclusivo da validação dos Desafios 01 a 05, excluído ao final. Os identificadores do ambiente não são publicados. |
| Execução | Sequência executada com apoio do GitHub Copilot CLI na estação do mantenedor. |
| Versões | Windows, Python 3.12.10, Azure CLI 2.89.0, `agent-framework-core` 1.21.0, `agent-framework-openai` 1.15.0, `openai` 3.23.0, `pydantic` 2.13.5, `azure-search-documents` 12.0.0 e as bibliotecas dos desafios anteriores. |
| Modelo de geração | `gpt-5.4-mini` (versão 2026-03-17), deployment `geracao`, esforço `low`, em `brazilsouth`. |
| Repetição dos comandos | Os 9 blocos de PowerShell do guia (22 linhas de comando) foram extraídos do próprio texto e executados linha a linha, com troca apenas do marcador de ID da assinatura, em PowerShell 7.6, em `brazilsouth`, uma vez, com o guia completo. Os blocos 1 a 7 e 9 (20 linhas) terminaram com o código esperado (0) em todas as linhas. O bloco 8 (Etapa 6, conjunto de teste) não foi repetido, para não gastar o conjunto. A repetição confere os códigos de saída; o conteúdo das respostas varia (veja "Segunda amostra"). |
| Aprovação do mantenedor | Confirmada em 9 de outubro de 2026 para texto, código, resultados, conjuntos e documentos existentes; não representa nova medição. |

## Matriz de validação

| Verificação | Resultado |
| --- | --- |
| Testes automáticos (`python -m unittest discover -s tests`) | Passaram, sem acessar o Azure, com `-X dev -W error`: 292 testes no total, com 48 casos novos em `test_avaliacao.py` e 2 casos novos em `test_politica.py` |
| Etapa `validar` | Passou: os dois conjuntos têm 12 perguntas com a mesma composição (5 simples, 2 compostas, 2 individuais, 1 sem evidência, 1 fora de escopo e 1 ambígua), e toda evidência esperada aparece nos 54 trechos dos documentos locais |
| Recuperação, ajuste e teste | Ver as tabelas abaixo; uma medição de cada conjunto com o código final (a do ajuste foi repetida na revisão final com os mesmos números) |
| Respostas, ajuste | 7 configurações antes e 7 depois da correção do normalizador, e 3 repetições de 3 configurações; ver as tabelas |
| Respostas, teste | Uma única medição, com a configuração escolhida antes; ver a seção "Conjunto de teste" |
| Falsas respostas | Nenhuma em nenhuma execução do ajuste (7 + 7 + 9 execuções de 12 perguntas) nem na do teste |
| Erros de uso provocados localmente | `--conjunto` ausente, `--ids AJ-99`, `--repeticoes 9` e `--etapa recuperacao --ids AJ-10,AJ-11` terminam com a mensagem esperada e código de saída 1, sem acessar o Azure |
| Erros não provocados no Azure | Login, permissão, 429, filtro de conteúdo e tempo esgotado: cobertos só por testes automáticos (`test_erro_do_servico_de_geracao_interrompe_a_medicao_com_orientacao`) |
| 404 intermitente do serviço de modelos | Nenhum aviso nem erro 404 em cerca de 30 execuções de medição |
| Limpeza | Ver o registro do último desafio: o grupo é excluído uma vez, depois de todos os desafios |

### Recuperação

Nove perguntas de cada conjunto têm resposta nos documentos e entram na medição.

| Conjunto | Modo | acerto@1 | acerto@3 | acerto@5 | acerto@10 | MRR |
| --- | --- | --- | --- | --- | --- | --- |
| Ajuste | vetorial | 7 de 9 | 9 de 9 | 9 de 9 | 9 de 9 | 1,00 |
| Ajuste | texto | 5 de 9 | 7 de 9 | 9 de 9 | 9 de 9 | 0,78 |
| Ajuste | híbrido | 6 de 9 | 9 de 9 | 9 de 9 | 9 de 9 | 0,87 |
| Teste | vetorial | 4 de 9 | 7 de 9 | 8 de 9 | 9 de 9 | 0,79 |
| Teste | texto | 5 de 9 | 7 de 9 | 8 de 9 | 8 de 9 | 0,83 |
| Teste | híbrido | 5 de 9 | 8 de 9 | 8 de 9 | 9 de 9 | 0,85 |

No ajuste, as duas perguntas que falham no acerto@1 do modo vetorial são as compostas (o primeiro trecho cobre um dos dois assuntos). A ordem dos modos mudou entre os conjuntos: o vetorial lidera no ajuste e fica em último no teste. A posição do primeiro trecho pertinente da pergunta `AJ-08` no modo texto (5) foi conferida com `buscar_trechos.py`: os quatro primeiros trechos são perguntas frequentes de outros assuntos, e o quinto é "Como funciona a franquia?".

### Respostas no ajuste, antes da correção do normalizador

Execução única de cada configuração, 12 perguntas. "Obrigatória" é a recuperação obrigatória; "ferramenta", a recuperação por ferramenta (até 2 buscas).

| Configuração | Tipo correto | Situação correta | Descartes | Fatos presentes | Tokens de entrada | Tempo |
| --- | --- | --- | --- | --- | --- | --- |
| Obrigatória, híbrida, `k=5` | 11 de 12 | 12 de 12 | 0 | 13 de 13 | 1.596 | 3,4 s |
| Obrigatória, vetorial, `k=5` | 11 de 12 | 11 de 12 | 1 (`AJ-03`) | 12 de 12 | 1.590 | 3,1 s |
| Obrigatória, híbrida, `k=3` | 11 de 12 | 12 de 12 | 0 | 13 de 13 | 1.188 | 3,1 s |
| Obrigatória, vetorial, `k=3` | 11 de 12 | 12 de 12 | 0 | 13 de 13 | 1.182 | 3,2 s |
| Ferramenta, híbrida, `k=5` | 12 de 12 | 11 de 12 | 1 (`AJ-08`) | 12 de 12 | 2.791 | 6,5 s |
| Ferramenta, vetorial, `k=5` | 12 de 12 | 10 de 12 | 2 (`AJ-07` e `AJ-08`) | 9 de 9 | 2.769 | 6,3 s |
| Ferramenta, híbrida, `k=3` | 12 de 12 | 11 de 12 | 1 (`AJ-08`) | 12 de 12 | 2.290 | 6,1 s |

### Respostas no ajuste, depois da correção

Execução única de cada configuração, 12 perguntas, sem descartes, falsas recusas nem falsas respostas.

| Configuração | Tipo correto | Situação correta | Fatos presentes | Tokens de entrada | Tokens de saída | Buscas | Tempo |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Obrigatória, híbrida, `k=5` | 11 de 12 | 12 de 12 | 13 de 13 | 1.596 | 232 | 1,0 | 3,5 s |
| Obrigatória, vetorial, `k=5` | 11 de 12 | 12 de 12 | 12 de 13 | 1.590 | 217 | 1,0 | 3,3 s |
| Obrigatória, híbrida, `k=3` | 11 de 12 | 12 de 12 | 13 de 13 | 1.188 | 221 | 1,0 | 3,3 s |
| Obrigatória, vetorial, `k=3` | 11 de 12 | 12 de 12 | 12 de 13 | 1.182 | 217 | 1,0 | 3,1 s |
| Ferramenta, híbrida, `k=5` | 12 de 12 | 12 de 12 | 13 de 13 | 2.840 | 255 | 0,9 | 6,5 s |
| Ferramenta, vetorial, `k=5` | 12 de 12 | 12 de 12 | 12 de 13 | 2.547 | 246 | 0,8 | 6,8 s |
| Ferramenta, híbrida, `k=3` | 12 de 12 | 12 de 12 | 13 de 13 | 2.235 | 242 | 0,8 | 6,3 s |

Em 21 das 23 execuções da recuperação obrigatória (4 antes da correção, 4 depois, 6 das repetições e 9 da repetição dos blocos), o modelo classificou `AJ-10` ("Qual é o telefone do Atendimento?") como `fora_de_escopo`, e o conjunto espera `sem_evidencia`; nas outras 2, acertou. Em todas as 13 execuções do agente (3 antes, 3 depois, 3 das repetições e 4 da repetição dos blocos), a classificação foi `sem_evidencia`. A situação é a mesma nos dois casos (recusa).

### Repetições no ajuste (depois da correção)

| Configuração | Repetição | Tipo correto | Situação correta | Descartes | Falsas recusas | Falsas respostas | Fatos presentes | Tokens de entrada | Tempo |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Obrigatória, híbrida, `k=3` | 1 | 11 de 12 | 12 de 12 | 0 | 0 | 0 | 13 de 13 | 1.188 | 3,2 s |
| Obrigatória, híbrida, `k=3` | 2 | 11 de 12 | 12 de 12 | 0 | 0 | 0 | 11 de 13 | 1.188 | 2,6 s |
| Obrigatória, híbrida, `k=3` | 3 | 11 de 12 | 11 de 12 | 1 (`AJ-06`) | 0 | 0 | 10 de 11 | 1.188 | 2,5 s |
| Obrigatória, híbrida, `k=5` | 1 | 11 de 12 | 12 de 12 | 0 | 0 | 0 | 13 de 13 | 1.596 | 3,3 s |
| Obrigatória, híbrida, `k=5` | 2 | 10 de 12 | 11 de 12 | 0 | 1 (`AJ-04`, esclarecimento) | 0 | 12 de 12 | 1.596 | 2,6 s |
| Obrigatória, híbrida, `k=5` | 3 | 11 de 12 | 11 de 12 | 1 (`AJ-02`) | 0 | 0 | 11 de 11 | 1.596 | 2,7 s |
| Ferramenta, híbrida, `k=3` | 1 | 12 de 12 | 12 de 12 | 0 | 0 | 0 | 13 de 13 | 2.732 | 7,4 s |
| Ferramenta, híbrida, `k=3` | 2 | 12 de 12 | 12 de 12 | 0 | 0 | 0 | 13 de 13 | 2.397 | 6,1 s |
| Ferramenta, híbrida, `k=3` | 3 | 12 de 12 | 12 de 12 | 0 | 0 | 0 | 13 de 13 | 2.293 | 6,1 s |

Resumo das faixas: situação correta de 11 a 12 de 12 (obrigatória, `k=3` e `k=5`) e 12 de 12 nas três execuções do agente; descartes de 0 a 1 nas obrigatórias e 0 no agente. Zero falhas em 36 respostas (agente) contra 1 em 36 (obrigatória, `k=3`) e 2 em 36 (obrigatória, `k=5`) não separa as configurações: o teste exato de Fisher, para 0 de 36 contra 2 de 36, dá p ≈ 0,49. As duas execuções com fatos ausentes da obrigatória `k=3` (repetições 2 e 3) concentram a ausência nas perguntas individuais `AJ-08` e `AJ-09`.

Esse cálculo é exploratório: as rodadas repetem as mesmas 12 perguntas, portanto os 36 resultados
não constituem 36 casos independentes para generalização.

### Segunda amostra (repetição dos blocos do guia)

A repetição literal dos blocos do guia, feita depois da medição do conjunto de teste, produziu uma segunda amostra das mesmas medições do ajuste. Ela não alterou a escolha da configuração.

| Bloco e comando | Resultado |
| --- | --- |
| 5, obrigatória, híbrida, `k=5` | Tipo 11 de 12, situação 12 de 12 |
| 6, obrigatória, híbrida, `k=3` | Tipo 12 de 12 (`AJ-10` acertou o tipo), situação 12 de 12 |
| 6, obrigatória, vetorial, `k=5` | Tipo 11 de 12, situação 12 de 12 |
| 6, ferramenta, híbrida, `k=5` | Tipo 12 de 12, situação 11 de 12: um descarte (`AJ-09`, citação de `VLAR-CG-1_0-008`), 2.767 tokens de entrada, 7,1 s |
| 7, obrigatória, híbrida, `k=3`, 3 repetições | Tipo de 11 a 12 de 12; situação 12 de 12 nas 3; descartes 0; fatos de 11 a 12 de 13; 1.188 tokens; de 2,4 a 3,1 s |
| 7, obrigatória, híbrida, `k=5`, 3 repetições | Tipo 11 de 12 nas 3; situação 12 de 12 nas 3; descartes 0; fatos de 12 a 13 de 13; 1.596 tokens; de 2,5 a 3,2 s |
| 7, ferramenta, híbrida, `k=3`, 3 repetições | Tipo 12 de 12 nas 3; situação 12 de 12 nas 3; descartes 0; fatos de 12 a 13 de 13; de 2.391 a 2.556 tokens; de 6,3 a 6,7 s |

Somando as duas amostras (6 repetições de 12 perguntas por configuração), as falhas de situação foram 1 em 72 (obrigatória `k=3`), 2 em 72 (obrigatória `k=5`) e 0 em 72 (ferramenta `k=3`). Na segunda amostra, as três configurações acertaram a situação das 36 respostas: a diferença da primeira amostra não se repetiu.

### Conjunto de teste

Duas medições, cada uma uma única vez, depois da escolha. Só os números foram exibidos; `--mostrar-perguntas` não foi usada.

| Medição | Resultado |
| --- | --- |
| Recuperação (9 perguntas) | Ver a tabela da recuperação acima (linhas do conjunto de teste) |
| Respostas, obrigatória, híbrida, `k=3` | Tipo correto 10 de 12; situação correta 10 de 12; descartes 0; erros de formato 0; falsas recusas 2; falsas respostas 0; fatos presentes 8 de 8; tokens de entrada 1.150 e de saída 167; 1,0 busca; 3,3 s por pergunta |
| Por categoria | Simples 5 de 5 na situação; composta 1 de 2; individual 1 de 2; sem evidência, fora de escopo e ambígua 1 de 1 cada |

A meta de escolha pedia no máximo uma pergunta com resultado diferente do esperado em cada rodada; o teste teve duas, ambas falsas recusas. Nenhuma outra configuração foi medida no conjunto de teste.

## O defeito que a medição encontrou

**Sintoma.** Com o agente, a pergunta `AJ-08` ("Meu seguro cobre vendaval se o telhado da minha casa voar?") teve a resposta descartada nas três execuções do agente anteriores à correção ("a citação de VLAR-CG-1_0-004 não aparece literalmente no trecho"). Em quatro tentativas isoladas com o agente (híbrido, `k=5`, até 2 buscas), três foram descartadas e uma foi respondida.

**Causa.** Na cláusula 3.1, o texto do trecho termina em negrito seguido de ponto final: "...na apólice individual**." A função `normalizar` do Desafio 04 trocava cada marca de Markdown por um espaço, e o trecho virava "...na apólice individual ." (com espaço antes do ponto). O modelo copiava a frase sem as marcas, "...na apólice individual.", e a comparação literal falhava. Em uma das quatro tentativas, o modelo citou a frase com as marcas (como no texto do documento), e a citação passou.

**Correção.** `normalizar` passou a remover as marcas de ênfase (`*`, `_` e acento grave) sem deixar espaço, e a tratar `#`, `|` e `>` como separadores. Dois testes novos em `test_politica.py` cobrem a frase completa e a pontuação colada às marcas; eles falham com o código anterior. Uma verificação direta com a frase da cláusula 3.1 deu "casa: False" antes e "casa: True" depois.

**Efeito.** Depois da correção, `AJ-08` não foi descartada em nenhuma das 16 execuções de 12 perguntas (6 do agente e 10 da recuperação obrigatória). Os descartes que sobraram vieram de outras causas (ver abaixo). O guia do Desafio 04 continua correto: ele já descrevia a conferência como "ignorando marcas de Markdown (como `**`) e espaços repetidos".

**Descartes que não vieram do normalizador.**

- `AJ-07`, agente vetorial `k=5` (antes da correção): o descarte disse que a citação de `VLAR-FAQ-1_0-008` não aparecia no trecho. Uma investigação posterior reproduziu o descarte, com a mesma mensagem e o mesmo trecho, em 1 de 8 execuções: o modelo atribuiu a `VLAR-FAQ-1_0-008` uma frase que pertence a outro trecho (a da cobertura de roubo e furto qualificado). O descarte é legítimo.
- `AJ-06`, obrigatória `k=3` (repetição 3): a citação do trecho `VLAR-GL-1_0-023` não aparecia literalmente. Uma investigação com a mesma pergunta, repetida 8 vezes, reproduziu o descarte uma vez, com a causa: o modelo uniu o título ("Sublimite") e o parágrafo do trecho com dois-pontos ("Sublimite: Limite menor, aplicado a certos bens dentro de uma cobertura."), e essa frase não existe assim no texto. A regra de citação literal funcionou como projetada.
- `AJ-03` (obrigatória vetorial `k=5`, antes da correção): causa não registrada. `AJ-03` não reapareceu em 12 execuções isoladas (6 em cada modo, `k=5`).
- `AJ-02` (obrigatória híbrida `k=5`, repetição 3) e `AJ-09` (ferramenta híbrida `k=5`, repetição dos blocos): em ambos, a citação de `VLAR-CG-1_0-008` foi descartada. Esse trecho traz a tabela das franquias e os sublimites (cláusulas 6.3 e 6.4). O descarte não reproduziu em 24 execuções isoladas (12 de cada pergunta, recuperação obrigatória, híbrida, `k=5`), e o texto bruto da citação não foi registrado. A causa não foi confirmada; a hipótese, ainda sem prova, é uma citação que reescreve a frase de uma linha da tabela, que a regra de citação literal descarta.

**Fatos ausentes que não são erro de conteúdo.** `AJ-08`: em 1 de 5 execuções isoladas, a resposta explicou a cobertura e disse que depende da apólice individual, sem a palavra "contratad" que o fato exige. `AJ-09`: o fato "5.000,00" apareceu em 5 de 5 execuções isoladas; a ausência da repetição 2 não foi investigada (o texto da resposta não foi registrado).

## Ordem das medições e integridade do conjunto de teste

1. Os dois conjuntos foram escritos antes de qualquer medição, e a etapa `validar` passou.
2. Recuperação do ajuste, nos três modos.
3. Respostas do ajuste, 7 configurações. Duas execuções rotuladas como recuperação obrigatória usaram, na verdade, o agente: o programa de avaliação herdou o padrão `ferramenta` do Desafio 05. O padrão passou a ser `obrigatoria` (`adicionar_argumentos_agente(..., padrao="obrigatoria")`), as saídas erradas foram renomeadas e as configurações da recuperação obrigatória foram medidas de novo.
4. O defeito do normalizador foi encontrado, corrigido, e as 7 configurações foram medidas de novo (tabela "depois da correção").
5. Três repetições de três configurações no ajuste.
6. Meta e escolha. A meta (nenhuma falsa resposta; situação correta em pelo menos 11 de 12 em cada repetição; entre as que cumprem, o menor consumo de tokens de entrada) foi escrita depois de ver as sete configurações e as repetições do ajuste e antes de qualquer medição do conjunto de teste. Ela não é uma meta registrada antes do ajuste. A configuração escolhida foi a recuperação obrigatória, modo híbrido, `k=3`.
7. Conjunto de teste: a recuperação e as respostas, uma vez cada. Nada mais foi medido nele.
8. Repetição literal dos blocos do guia, exceto o da Etapa 6, depois da medição do teste. Ela só gerou uma segunda amostra do ajuste e não alterou a configuração escolhida.

O autor dos conjuntos, do código, do guia e das medições é o mesmo, e o texto de duas perguntas do teste aparece em um teste automático (`test_conjunto_de_teste_mostra_so_os_numeros_ate_pedir_as_perguntas`, que verifica a opção `--mostrar-perguntas`). Por isso a independência do conjunto de teste é parcial. As perguntas do teste não aparecem em guias, registros, instruções, README nem CONTRIBUTING; um teste automático confere isso.

## Observações de operação

- **Primeira chamada mais lenta.** A primeira pergunta de cada execução levou cerca de 12 segundos (12,3 s na recuperação obrigatória; de 11,1 a 11,8 s no agente), contra 2 a 4 segundos nas seguintes da recuperação obrigatória e 5 a 7 segundos nas do agente. A causa provável é a abertura das conexões; não foi investigada.
- **Execuções em sequência.** As medições do Azure foram executadas uma de cada vez. O 404 intermitente do serviço de modelos, descrito no registro do Desafio 05, não apareceu em nenhuma delas.
- **Denominador dos fatos.** Os fatos esperados contam só as respostas mostradas. Uma resposta descartada, recusada ou de esclarecimento tira os fatos dela do denominador, por isso o total varia entre repetições (por exemplo, 13, 13 e 11).
- **Tipo e situação.** A medida de tipo apontou uma única pergunta sistematicamente (`AJ-10`), sem efeito na situação. A fronteira entre `sem_evidencia` e `fora_de_escopo` é uma decisão de produto; o conjunto não foi alterado.
- **Variação do modelo.** O texto, o número de buscas do agente e os fatos presentes variam entre execuções; os números das tabelas são faixas medidas, não garantias.

## Pendências

| Item | Situação | Ação para encerrar |
| --- | --- | --- |
| Aprovação dos dois conjuntos de perguntas | Confirmada | Mantenedor, em 9 de outubro de 2026; a independência parcial continua registrada e uma nova avaliação exige conjunto independente |
| macOS, Linux e WSL | Pendente | Executar os comandos do guia nesses sistemas e registrar as diferenças de sintaxe |
| Python diferente do 3.12 | Pendente | Repetir as Etapas 1 a 7 com outra versão suportada |
| Windows PowerShell 5.1 | Pendente | A análise de sintaxe passou na versão 5.1.26100; falta executar os comandos nesse ambiente |
| Outros modelos de geração, outras versões do MAF e conjuntos maiores | Pendente | Só o `gpt-5.4-mini` e as versões fixadas foram validados; 12 perguntas e 3 repetições não permitem conclusões finas |
| Causa dos descartes de `AJ-02`, `AJ-03` e `AJ-09` (dois deles no trecho `VLAR-CG-1_0-008`) e da ausência do fato de `AJ-09` | Pendente | Registrar o texto bruto da resposta quando ocorrer de novo |
| Execução repetida dos comandos da Etapa 6 | Não feita de propósito | Repetir os blocos da Etapa 6 gastaria o conjunto de teste; eles têm os mesmos argumentos das duas medições registradas |
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
| Siglas | MRR (*mean reciprocal rank*) e CLI definidas no primeiro uso |
| Termos informais | "à mão" substituído por "manualmente", "passam a sumir" por "passam a ser removidas" e "quebrado" por "inválido" |
| Próximos desafios | "Planejado, ainda sem desafio escrito" deu lugar a um link para o Desafio 07 |

### Revisão integral — GPT-6.1 Sol

Revisão de 9 de outubro de 2026 contra o guia de estilo do mantenedor, com leitura completa do guia e
deste registro. O procedimento agora registra o critério antes de medir o ajuste, enquanto o resumo
histórico preserva a ordem real: a meta original veio depois do ajuste e antes do teste.
A configuração usada no comando da Etapa 6 foi identificada.

As tabelas e saídas passaram a ser referências registradas, em vez de promessa de acerto. Zero falsas
respostas é descrito como contagem de situações, sem afirmar que todas as frases eram fiéis às fontes.
A leitura do teste continua reservada para depois da avaliação final; a medição anterior foi
preservada com duas falsas recusas e a meta não atingida. A referência da Atividade 3 foi corrigida
para a Etapa 5 do D02. O exemplo abreviado de JSON ganhou cerca `text`, pois suas reticências não
formam JSON válido.

Código, conjuntos, números e os nove blocos PowerShell foram preservados.
O conjunto de teste não foi medido novamente.

O guia foi relido após as correções e inspecionado na prévia Markdown local.
As [verificações integradas da revisão](l100-01-preparar-ambiente.md#revisão-editorial) incluem comparação
dos comandos e conferência de referências, tabelas, links e testes locais.

## Aprovação do material

O mantenedor confirmou a aprovação do material existente e dos conjuntos em 9 de outubro de 2026.
As perguntas, a configuração escolhida e o resultado de 10 situações corretas em 12, com duas
falsas recusas, foram preservados. O teste não foi executado novamente.
A aprovação recebida não transforma a amostra em independente nem significa que a meta foi atingida.

## Efeito da nova apresentação na métrica de fatos

O resultado histórico de 10 situações corretas em 12 foi medido antes de `4eb0408` e permanece
inalterado. Não houve nova execução do conjunto de teste.

A política atual mostra texto fixo nas respostas classificadas como individuais e mantém suas
citações. A métrica de fatos continua procurando expressões somente em `decisao.texto`, não
nas citações. Nos dublês do ajuste, os fatos escritos pelo modelo para AJ-08 e AJ-09 deixam
de chegar ao texto mostrado: esses dois casos continuam com tipo e situação corretos, mas
têm zero fatos contados. A definição da métrica não foi ampliada para esconder essa diferença.

O teste de saída do avaliador foi ajustado para esse comportamento, preservando os conjuntos
e as expectativas originais. Os 48 testes de avaliação passaram localmente.
Uma nova medição de qualidade do assistente precisa de configuração e conjunto final próprios;
o teste local da política usa respostas sintéticas e não mede geração ou recuperação Azure.

## Autoria

Código, testes e texto produzidos com Claude Sonnet 5.5, no GitHub Copilot CLI. O Astra, modelo preferido do
mantenedor para a documentação, não estava disponível na sessão. O modelo de autoria é independente do modelo
que o aluno escolhe no Copilot e dos deployments da aplicação (`text-embedding-3-small` e `gpt-5.4-mini`).
