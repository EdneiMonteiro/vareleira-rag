# L400 · Desafio 06: testar carga e interrupção

[Início](../../README.md) · [Desafio 05](05-comparar-estrategias.md) · [Desafio 07](07-recuperar-limpar.md)

| Campo | Definição |
| --- | --- |
| Situação | Carga finita, progresso e cancelamento exercitados; limitações remotas registradas |
| Público | Operações, arquitetura, Atendimento e desenvolvimento |
| Resultado | Exercitar concorrência finita, falhas e interrupção sem ocultar consumo |
| Custo | Carga real chama serviços; quantidade, duração e orçamento devem ser definidos antes |

## Conteúdo

- [Cenário](#cenário)
- [Objetivos](#objetivos)
- [Artefatos e disponibilidade](#artefatos-e-disponibilidade)
- [Tecnologias e conceitos](#tecnologias-e-conceitos)
- [Pré-requisitos](#pré-requisitos)
- [Etapa 1: definir uma carga finita](#etapa-1-definir-uma-carga-finita)
- [Etapa 2: conferir progresso e cancelamento](#etapa-2-conferir-progresso-e-cancelamento)
- [Etapa 3: observar falhas e isolamento](#etapa-3-observar-falhas-e-isolamento)
- [Como pedir uma mudança ao Copilot no VS Code](#como-pedir-uma-mudança-ao-copilot-no-vs-code)
- [Conferência do resultado](#conferência-do-resultado)
- [Solução de problemas](#solução-de-problemas)
- [Custos, pausa e limpeza](#custos-pausa-e-limpeza)
- [Situação da validação](#situação-da-validação)
- [Glossário e referências](#glossário-e-referências)

## Cenário

Durante o piloto fictício, mais de uma pessoa pode consultar o assistente. Beatriz Torres precisa
ver o andamento sem receber texto ainda não verificado. A equipe de operações quer distinguir
sobrecarga, cancelamento e falha, conservando a autorização de cada requisição.

## Objetivos

1. Fixar número de pedidos, concorrência, prazo e condição de parada.
2. Conferir progresso sem expor resposta bruta.
3. Impedir próximas etapas de uma requisição cancelada.
4. Distinguir testes controlados de capacidade e disponibilidade de produção.

## Artefatos e disponibilidade

| Artefato | Uso |
| --- | --- |
| [Servidor do chat](../../scripts/chat_web.py) | Admissão e HTTP, protocolo de comunicação do chat |
| [Contrato e erros](../../scripts/lab_chat.py) | Limites, causas e resposta verificada |
| [Interface](../../web/app.js) | Envio e apresentação |
| [Operação L300](../../scripts/operar_l300.py) | Referência de resumo de logs sem conteúdo |

O [runtime L400](../../scripts/lab_orquestracao.py) e os
[testes](../../tests/test_orquestracao.py) implementam progresso e cancelamento.
O avaliador de comparação usa JSON sequencial; ele não mede carga concorrente nem consome
eventos de progresso.

## Tecnologias e conceitos

**Concorrência** é a quantidade de pedidos em execução ao mesmo tempo. Uma fila sem limite
não resolve falta de capacidade. **Timeout** é o prazo para interromper a espera.

**Streaming** envia partes de uma resposta durante a execução. No exercício, o progresso
contém eventos de etapa; texto do modelo só pode ser apresentado depois das verificações.
O FastAPI oferece respostas por gerador, mas isso não valida automaticamente seu conteúdo [1].
O L400 usa eventos enviados pelo servidor, **Server-Sent Events (SSE)**, no
`POST /api/perguntar/progresso`, somente quando a coordenação está ativa.
O endpoint JSON anterior permanece sem alteração de formato.

**Cancelamento** impede a continuação da requisição no programa. Um pedido remoto já enviado
pode continuar consumindo tokens até concluir ou atingir seu próprio timeout.
Não anuncie cancelamento remoto instantâneo sem prova.

## Pré-requisitos

Use perguntas sintéticas de desenvolvimento, não o conjunto final para ajustar os limites.
Prepare o destino autenticado e a quantidade exata de chamadas.
Confirme assinatura ativa e orçamento para uma prova real.

Os testes locais usam dublês e não têm consumo Azure. A execução de carga real é deliberada,
finita e autorizada; não use laço sem parada ou retries indefinidos.

## Etapa 1: definir uma carga finita

Registre pedidos, concorrência, duração, teto de chamadas e parada antes de executar.

| Condição | Resultado a conferir |
| --- | --- |
| Abaixo do limite | Pedidos admitidos, com fontes e uso observado |
| Acima da admissão | Recusa explícita de ocupado, não fila sem controle |
| Modelo limita capacidade | 429 ou tratamento transitório dentro do orçamento |
| Serviço não conclui | Timeout ou falha, sem resposta fabricada |

Uma prova pequena de carga é um teste do comportamento dos limites. Ela não estabelece
capacidade máxima, percentil de produção ou garantia de disponibilidade.
Não há um gerador público de carga concorrente neste roteiro. A sonda privada usada na
rodada não acompanha a entrega; antes de reproduzir a prova, o operador precisa de um
executor revisado com esses limites, autenticação, destinos e descarte de conteúdo dos logs.
O avaliador sequencial do Desafio 05 não substitui esse executor.

## Etapa 2: conferir progresso e cancelamento

1. Inicie uma pergunta e observe os eventos de etapa.
2. Confira que nenhum evento apresenta resposta bruta ou fonte fora do perfil.
3. Interrompa antes da próxima etapa.
4. Confira contagens de chamadas já enviadas e etapas não executadas.
5. Execute outra requisição e confirme que ela não foi cancelada por engano.

**Resultado esperado:** interrupção específica da requisição e ausência de novas chamadas.
Consumo incerto fica registrado; cancelar a interface não deve virar um resultado documentado.
Use uma sessão PowerShell dedicada, a `.venv` preparada no Desafio 01 e a pasta completa
aberta no VS Code. Os comandos locais abaixo não iniciam uma carga remota.

O fluxo SSE emite `etapa`, `tentativa` e `resumo` com metadados. Somente depois da política
há `resposta`; uma falha gera `erro`, e o fluxo termina em `fim`.
Sem a opção L400, essa rota é inexistente, com 404.
A interface usa um controlador de interrupção do navegador, `AbortController`; isso não
revoga tokens nem cancela instantaneamente o processamento remoto [4].
Na prova Azure, fechar somente a conexão não interrompeu o workflow a tempo através da borda.
Um cancelamento no programa exige sinal explícito autenticado.

No L400, a interface recebe do servidor o cabeçalho `X-Request-Id` e envia primeiro
`POST /api/perguntar/cancelar` com `{"id_requisicao":"<identificador>"}`. Somente o mesmo ator
autenticado pode pedir a interrupção; ele recebe 202, solicitação aceita. Uma identidade diferente,
execução ausente ou já encerrada recebe 404. A confirmação de interrupção vem depois,
no evento `erro` com `cancelado` e no encerramento do fluxo, não apenas no 202.

O botão aguarda a solicitação por no máximo cinco segundos e depois encerra a leitura no navegador.
Sem identificador, ou se o servidor não confirmar a solicitação, a mensagem informa que somente
a espera local foi interrompida. A pergunta, o perfil e o filtro não fazem parte do pedido de cancelamento.

O registro conserva somente execuções ativas, com validade e limite iguais aos controles do processo.
Não guarda perguntas ou respostas e usa uma assinatura interna do ator, sem expor seus identificadores.
O registro sai ao terminar ou cancelar a consulta. Nesta implementação, **o cancelamento explícito
depende de um único processo e uma réplica**. Não aumente esse número sem redesenhar o encaminhamento
e o registro; uma chamada enviada a outra réplica não encontra a execução.

Os prazos fixados são 30 segundos por chamada de modelo e 20 por busca ou embedding.
O prazo do workflow é o timeout do chat menos dois segundos, normalmente 88 segundos.
Busca e embeddings síncronos já enviados podem terminar depois do cancelamento;
não há execução da etapa seguinte nem apresentação da resposta cancelada.

Confira localmente:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_orquestracao.py
node --check web\app.js
```

## Etapa 3: observar falhas e isolamento

1. Exercite uma falha transitória controlada.
2. Exercite acesso negado sem troca de identidade.
3. Confira filtro por perfil em chamadas concorrentes.
4. Confira as dependências de dentro e de fora da rede.
5. Separe o resultado do dublê do resultado do Azure.

Depois do isolamento, o operador externo também pode receber 403 apesar de possuir papel
de dados. Origem de rede e permissão são provas distintas.

## Como pedir uma mudança ao Copilot no VS Code

```text
Anexo servidor, contrato e testes de limites L400.
Siga duas requisições simultâneas e cancele somente uma delas.
Confira a admissão, as próximas etapas e o conteúdo dos eventos.
Não envie carga real, altere permissões ou copie perguntas para logs.
```

Revise o diff, a sintaxe JavaScript e os testes relacionados antes de executar na nuvem.

## Conferência do resultado

Registre pedidos concluídos, falhas, recusas, cancelamentos, tempo e uso conhecido ou incerto.
Os logs do programa podem não incluir recusas interceptadas pela borda; os testes HTTP
precisam ser conservados separadamente.

## Solução de problemas

| Sintoma | Ação |
| --- | --- |
| Cancelar uma pergunta interrompe outra | Corrija o estado por requisição |
| Modelo continua após cancelamento | Separe chamada já enviada de nova etapa indevida |
| Progresso contém texto livre | Mantenha somente eventos fechados até a política aprovar |
| Carga fica em repetição | Confira limites de runner, SDK e contingência |

## Custos, pausa e limpeza

Defina a quantidade de chamadas antes do teste. Parar o cliente não remove serviços Azure.
Colete as evidências e encerre os temporários próprios; logs, busca e rede podem continuar cobrando.

## Situação da validação

Progresso, limites e cancelamento passaram nos testes locais, inclusive desconexão com
servidor uvicorn real. No Azure, seis pedidos com concorrência três tiveram HTTP 200 e fonte
operacional; o SSE concluiu com resposta verificada. O cancelamento direto no workflow impediu
a busca posterior e preservou uso incerto do embedding em voo. Já a desconexão HTTP não
interrompeu a execução através da borda Azure. O reparo explícito passou em 100 testes de runtime
e na suíte integrada de 1.015 casos, com 1.014 aprovados e um ignorado no Windows.
A prova Azure confirmou outro ator recusado com 404, dono aceito com 202, fluxo cancelado sem
resposta e execução encerrada ausente. O log do servidor mostrou uma chamada de modelo,
zero buscas e uso incerto da chamada já enviada. Uma nova consulta funcionou depois.
O [registro L400](../../docs/validacao/l400-validacao.md) separa origem e alcance dessas provas,
sem tratá-las como objetivos de nível de serviço de produção.

## Glossário e referências

| Termo | Significado |
| --- | --- |
| Concorrência | Pedidos executados simultaneamente |
| Admissão | Decisão de aceitar um pedido para execução |
| Timeout | Prazo máximo de espera |
| Streaming | Envio progressivo de partes de uma resposta |
| Evento de etapa | Informação de progresso sem conteúdo bruto |

1. [Respostas por geradores no FastAPI](https://fastapi.tiangolo.com/advanced/custom-response/).
2. [Eventos e requisições de workflows MAF](https://learn.microsoft.com/en-us/agent-framework/workflows/human-in-the-loop).
3. [Cotas dos modelos](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/quota).
4. [AbortController no navegador](https://developer.mozilla.org/en-US/docs/Web/API/AbortController).

Texto por GPT-6.1 Sol; código por Claude Sonnet 5.5. As ferramentas de autoria não medem o Azure.

Revisão documental por gpt-6-astra (Astra), em 11 de outubro de 2026, sem nova execução Azure.
