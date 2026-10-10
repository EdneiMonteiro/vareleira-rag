# L200 — Desafio 04: usar o chat local com fontes

[Início do laboratório](../../README.md) · [Desafio 03](03-comparar-ingestao.md) · [Desafio 05](05-hospedar-chat.md)

| Item | Descrição |
| --- | --- |
| Situação | Exercício executável. Interface, isolamento e erros foram conferidos localmente; o fluxo Azure é validado separadamente. |
| Público | Pessoas de Atendimento, operações, arquitetura e desenvolvimento. |
| Resultado | Chat no navegador, com tipo de pergunta, resposta, evidências, aviso e tratamento explícito de falhas. |
| Custo | Demonstração sem Azure: nenhum consumo de modelos. Modo local real: busca e tokens, usando os recursos existentes. |

## Conteúdo

- [Cenário](#cenário)
- [Objetivos](#objetivos)
- [Artefatos e disponibilidade](#artefatos-e-disponibilidade)
- [Tecnologias e conceitos](#tecnologias-e-conceitos)
- [Pré-requisitos](#pré-requisitos)
- [Etapa 1: explorar a interface sem Azure](#etapa-1-explorar-a-interface-sem-azure)
- [Etapa 2: consultar a base real pelo computador](#etapa-2-consultar-a-base-real-pelo-computador)
- [Etapa 3: conferir isolamento e erros](#etapa-3-conferir-isolamento-e-erros)
- [Como pedir uma mudança ao Copilot no VS Code](#como-pedir-uma-mudança-ao-copilot-no-vs-code)
- [Conferência do resultado](#conferência-do-resultado)
- [Solução de problemas](#solução-de-problemas)
- [Custos, pausa e limpeza](#custos-pausa-e-limpeza)
- [Situação da validação](#situação-da-validação)
- [Glossário](#glossário)
- [Referências](#referências)

## Cenário

No piloto fictício de 2025, Beatriz Torres quer que Atendimento faça perguntas sem usar os comandos
de consulta. A equipe acrescenta uma página web à recuperação e à política do L100.
O navegador mostra fontes e avisos, mantendo os mesmos limites sobre contratação individual.

Cada pergunta é independente. A lista de mensagens existe apenas na memória da página; o servidor
recebe somente a pergunta atual. O chat não acompanha referências como “e nesse caso?” usando o
histórico anterior. Essa escolha reduz retenção de conversas, mas limita o diálogo contextual.

## Objetivos

1. Explorar a interface com respostas explicitamente simuladas.
2. Consultar o índice L200 com a identidade do operador, apenas no próprio computador.
3. Conferir fontes, avisos, isolamento entre abas e falhas.
4. Separar a aplicação Python do transporte HTTP e da apresentação no navegador.

## Artefatos e disponibilidade

| Artefato disponível | Uso |
| --- | --- |
| [Servidor](../../scripts/chat_web.py) | Página, arquivos estáticos, API e controle de carga |
| [Regras do chat](../../scripts/lab_chat.py) | Configuração, consulta, política e tradução de erros |
| [Página](../../web/index.html), [interação](../../web/app.js) e [estilos](../../web/style.css) | Interface sem dependências externas de scripts |
| [Política compartilhada](../../scripts/lab_politica.py) | Tipos, citações, texto fixo e aviso |
| [Dependências](../../requirements/l200.txt) e [testes](../../tests/test_chat.py) | Instalação e validação local |
| [Registro do desafio](../../docs/validacao/l200-04-chat-local.md) | Testes de API e navegador |

## Tecnologias e conceitos

**HTTP**, protocolo de comunicação entre navegador e servidor, transporta uma pergunta em
**JSON**, formato de texto estruturado. A **API**, interface de programação de aplicações,
recebe essa pergunta em `POST /api/perguntar`.

**FastAPI** organiza as rotas Python; **Uvicorn** executa o servidor [1][2].
Os módulos do L100 recuperam trechos, chamam o deployment de geração e aplicam a política.
O chat usa esse fluxo fixo: ele não executa a escolha de ferramentas do agente
Microsoft Agent Framework (MAF) do L100 D05.

**Loopback**, endereço do próprio computador, limita o modo local a `127.0.0.1`, `localhost`
ou `::1`. Os modos `--demo` e `--local-sem-autenticacao` recusam `0.0.0.0`, endereço que aceitaria
conexões de outras máquinas.

| Rota | O que confere |
| --- | --- |
| `GET /healthz` | Processo HTTP disponível; não consulta Azure |
| `GET /readyz` | Configuração e serviço local preparados; não executa busca ou geração |
| `GET /` e `/static/*` | Interface |
| `POST /api/perguntar` | Pergunta atual, recuperação, geração e política |

O navegador insere as respostas como texto, sem interpretar HTML, linguagem de marcação da página
(*Hypertext Markup Language*). As fontes são referências textuais; a página não abre automaticamente
endereços web recebidos do modelo.

## Pré-requisitos

Use Python 3.12, dependências `requirements\l200.txt` instaladas e PowerShell 7.
Abra a pasta completa no VS Code, selecione `.venv` em **Python: Select Interpreter** e consulte este
guia na prévia Markdown. A demonstração dispensa Azure; a consulta real exige a base do Desafio 03,
sessão da Azure CLI, interface de linha de comando do Azure, no tenant autorizado e papéis de consulta e modelos.

## Etapa 1: explorar a interface sem Azure

1. No terminal do projeto, inicie a demonstração.
2. Mantenha esse terminal aberto. Em outro terminal, confira saúde e prontidão.
3. Abra `http://127.0.0.1:8000` no navegador.

```powershell
python scripts\chat_web.py --host 127.0.0.1 --port 8000 --demo
```

Em um segundo terminal:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/healthz
Invoke-RestMethod http://127.0.0.1:8000/readyz
```

**Resultado esperado:** servidor disponível, prontidão em modo `demonstracao` e aviso visível
de simulação. Faça uma pergunta para observar a apresentação. As respostas dessa modalidade
não são informações sobre o produto.

> **Atenção:** a demonstração é escolhida somente com `--demo`. Uma falha Azure nunca ativa
> esse modo como substituição silenciosa.

### Prompt para o Copilot: separar interface e consulta

Anexe este guia, `lab_chat.py`, `chat_web.py` e `web\app.js`:

```text
Explique o caminho de uma pergunta, do botão Enviar até a resposta no navegador.
Diferencie demonstração, consulta Azure local e futura identidade gerenciada.
Identifique onde a política verifica citações e suprime o texto livre individual.
Mostre quais dados ficam na página e quais são enviados ao servidor.
Não edite arquivos, execute comandos ou peça credenciais.
```

**Conferência:** o pedido HTTP deve conter somente `pergunta` e um identificador opcional;
não existe transmissão da conversa inteira.

## Etapa 2: consultar a base real pelo computador

Encerre a demonstração com **Ctrl+C** no terminal que a iniciou.
Defina os destinos reaproveitados e a configuração explícita:

```powershell
$env:VARELEIRA_BUSCA = $busca
$env:VARELEIRA_MODELOS = $modelos
$env:VARELEIRA_INDICE = "vareleira-lar-l200"
$env:VARELEIRA_TENANT_ID = $tenant
$env:VARELEIRA_DEPLOYMENT_EMBEDDINGS = "embeddings"
$env:VARELEIRA_DEPLOYMENT_GERACAO = "geracao"
$env:VARELEIRA_DIMENSOES = "1536"
$env:VARELEIRA_MODO_BUSCA = "hibrida"
$env:VARELEIRA_K = "3"
$env:VARELEIRA_ESFORCO = "low"
$env:VARELEIRA_EXIGIR_AUTENTICACAO = "false"
python scripts\chat_web.py --host 127.0.0.1 --port 8000 --local-sem-autenticacao
```

Esse modo usa `AzureCliCredential`, credencial da sua sessão Azure CLI [3]. Ele não testa a identidade
gerenciada da futura aplicação. A ausência de login no navegador só é admitida porque o servidor fica
restrito ao seu computador.

No navegador, pergunte “O que é a assistência 24 horas do Vareleira Lar?” e compare as citações
com os documentos. Uma pergunta sobre sua contratação deve receber apenas orientação geral,
texto fixo e aviso quando as evidências passam na política.

**Resultado observável:** uma resposta não simulada com tipo e evidências, ou uma falha explícita.
Se a política descartar a saída, a API responde `503` com `resposta_nao_verificada`; ela não retransmite
a resposta rejeitada.

## Etapa 3: conferir isolamento e erros

1. Abra duas abas do chat e faça perguntas distintas. Cada aba deve conservar somente sua conversa.
2. Use **Nova conversa**. A lista deve ser apagada sem alterar a outra aba.
3. Recarregue a página. As mensagens anteriores não devem reaparecer.
4. Confira uma pergunta vazia, texto longo e falha de consulta.

Para conferir a API sem expor credenciais, em outro terminal:

```powershell
$corpo = @{ pergunta = "O que é a assistência 24 horas do Vareleira Lar?" } | ConvertTo-Json
Invoke-RestMethod http://127.0.0.1:8000/api/perguntar -Method Post -ContentType "application/json" -Body ([Text.Encoding]::UTF8.GetBytes($corpo))
$invalido = '{"pergunta":"Teste sintético","historico":[]}'
(Invoke-WebRequest http://127.0.0.1:8000/api/perguntar -Method Post -ContentType "application/json" -Body $invalido -SkipHttpErrorCheck).StatusCode
```

**Resultado esperado do segundo pedido:** `422`, porque o contrato rejeita `historico`.
O limite da pergunta é de 1.000 caracteres; o servidor também limita tamanho do corpo, consultas
simultâneas e tempo de resposta.

| Falha | Resposta prevista |
| --- | --- |
| Pergunta inválida ou campo extra | `422`, sem chamar a consulta |
| Corpo grande demais | `413` |
| Todas as vagas ocupadas | `429`, com orientação de espera |
| Tempo esgotado, acesso ou serviço indisponível | `503` |
| Citação rejeitada pela política | `503`, sem texto descartado |

Os testes locais usam dublês para provocar essas falhas sem alterar permissões ou gastar tokens.
Uma tentativa manual de novo é útil para diagnóstico; na avaliação final, cada pergunta recebe
uma única tentativa.

## Como pedir uma mudança ao Copilot no VS Code

Peça uma alteração delimitada, por exemplo:

```text
Altere somente a apresentação do código de suporte no chat.
Use web\app.js, web\style.css e os testes diretamente relacionados como contexto.
Preserve textContent, o contrato de uma pergunta por requisição, o aviso de
simulação e o tratamento de 401, 429 e 503. Não adicione retenção de conversas.
Mostre o diff e as verificações locais. Não execute comandos Azure.
```

Revise **Source Control** e execute:

```powershell
python -m unittest discover -s tests -p test_chat.py
node --check web\app.js
```

O comando JavaScript exige Node.js disponível. Ele confere sintaxe, não substitui o teste no navegador.

## Conferência do resultado

Confirme envio pelo botão e por Enter, aviso de simulação quando aplicável, fontes legíveis e ausência
de mistura entre abas. No navegador, abra **Developer Tools > Network** para conferir o corpo JSON
de um pedido sintético: somente pergunta e identificador, sem histórico ou segredo.

## Solução de problemas

| Sintoma | Diagnóstico e ação |
| --- | --- |
| Porta ocupada | Escolha outra porta com `--port`; preserve o processo de outra pessoa. |
| Modo nuvem sem configuração | Preencha a configuração ou escolha explicitamente o modo local; o servidor não inicia com lacunas. |
| `503` por resposta não verificada | Confira o código de suporte e as fontes em um diagnóstico separado; preserve a política. |
| `503` por acesso Azure | Confira a identidade do operador e seus papéis, não os do navegador. |
| Referência à mensagem anterior não funciona | Reescreva a pergunta completa; o histórico não entra no pedido atual. |

## Custos, pausa e limpeza

Use **Ctrl+C** no terminal do servidor ao terminar. Isso encerra o processo local, mas a busca,
armazenamento e recursos do Desafio 02 permanecem cobrados. Retire as variáveis de configuração
quando mudar de destino. O Desafio 05 reutiliza os arquivos do chat para hospedá-lo.

## Situação da validação

API e navegador foram conferidos com demonstração explícita: botão, Enter, duas abas, Nova conversa,
corpo sem histórico, texto semelhante a HTML tratado como texto, largura móvel de 390 pixels e
ausência de erros JavaScript. Testes automatizados cobrem falhas, política e carga.
O [registro](../../docs/validacao/l200-04-chat-local.md) separa demonstração, consulta local real e
aplicação Azure; autenticação interativa de uma pessoa não foi exercitada.

## Glossário

| Termo | Significado |
| --- | --- |
| HTTP | Protocolo de comunicação entre navegador e servidor |
| API | Interface pela qual um programa chama outro |
| JSON | Formato de texto estruturado usado no pedido |
| Loopback | Endereço que aponta para o próprio computador |
| FastAPI e Uvicorn | Biblioteca de rotas e servidor HTTP do chat |
| Dublê de teste | Objeto que substitui um serviço real para testar comportamento |
| Código de suporte | Identificador de requisição usado para localizar uma falha sem publicar a pergunta |

## Referências

1. [FastAPI](https://fastapi.tiangolo.com/).
2. [Uvicorn](https://uvicorn.dev/).
3. [AzureCliCredential](https://learn.microsoft.com/en-us/python/api/azure-identity/azure.identity.azureclicredential).

Texto e revisão: GPT-6.1 Sol. Código e testes: Claude Sonnet 5.5.
O Astra não estava disponível; a preferência de autoria não configura o modelo do aluno no editor.
