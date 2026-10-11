# L200, Desafio 04: registro de validação

Registro do [guia do chat local](../../desafios/L200/04-chat-local.md).
Testes executados em Windows, Python 3.12.10 e PowerShell 7, em 10 de outubro de 2026.

## Interface em demonstração

| Verificação no navegador | Resultado |
| --- | --- |
| Aviso de simulação | Visível; nenhuma consulta Azure |
| Envio por botão e Enter | Funcionou |
| Duas abas | Conversas isoladas |
| Corpo do pedido | Pergunta atual e identificador; histórico ausente |
| Nova conversa | Limpou a aba corrente sem alterar a outra |
| Texto semelhante a HTML | Tratado como texto, sem criar elemento executável |
| Largura de 390 pixels | Sem transbordamento horizontal observado |
| Console JavaScript | Nenhum erro observado |
| Encerramento | Servidor e abas de teste próprios encerrados |

Esse teste examinou apresentação e transporte. Respostas de demonstração não foram avaliadas como
conteúdo correto do produto.

## Consulta local real

O servidor foi iniciado em loopback com `--local-sem-autenticacao`, índice L200, busca híbrida,
`k=3`, esforço `low` e credencial do operador via Azure CLI.

| Pedido | Resultado |
| --- | --- |
| `/healthz` e `/readyz` | HTTP 200; modo local |
| Primeira pergunta geral de fumaça | HTTP 503, causa `resposta_descartada`; saída rejeitada não foi mostrada |
| Outro assunto geral de fumaça | HTTP 200, `documentada`/`respondida`, uma evidência e `simulada=false` |
| Campo `historico` extra | HTTP 422, causa `campos_nao_permitidos` |
| Encerramento | Servidor próprio parado e porta de teste liberada |

A segunda pergunta foi um diagnóstico operacional distinto, não substituição da primeira medição.
A falha original permaneceu registrada. Nenhum parâmetro ou regra foi ajustado por esses pedidos.
Essa identidade era a do operador, não a gerenciada da aplicação hospedada.

## Contratos e testes

Os testes locais cobrem configuração obrigatória, cabeçalho de identidade, limites de pedido,
concorrência, tempo, política, descarte, erro sanitizado e serviço demonstrativo explícito.
O servidor não guarda histórico, e uma falha real não ativa a demonstração.
Saúde e prontidão não chamam Azure.

O chat reutiliza recuperação, geração e política do L100 em fluxo fixo; o agente MAF do L100
permanece no console. Isso é uma decisão de composição, não uma nova avaliação da escolha de ferramentas.

## Limites

Interações novas com Copilot no VS Code e login interativo humano não foram executados.
Não foram medidos navegadores adicionais, tecnologias assistivas ou carga de produção.
Testes locais provocaram timeout e saturação com dublês, sem induzir indisponibilidade em serviços Azure.
