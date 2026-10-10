# L200 — Desafio 06: avaliar o contrato do chat

[Início do laboratório](../../README.md) · [Desafio 05](05-hospedar-chat.md) · [Desafio 07](07-operar-recuperar-limpar.md)

| Item | Descrição |
| --- | --- |
| Situação | Exercício executável. A primeira rodada teve 11 de 18 casos conformes e permanece registrada; a correção usa desenvolvimento separado e um novo conjunto final. |
| Público | Pessoas de Atendimento, operações, arquitetura e desenvolvimento. |
| Resultado | Relatório de uma resposta por pergunta, com contrato esperado, erros, apresentação e consumo conhecido, sem registrar o texto da conversa. |
| Custo | Perguntas ao chat consomem modelos e requisições. Descartes também podem consumir tokens; seu consumo pode não aparecer no relatório público. |

## Conteúdo

- [Cenário](#cenário)
- [Objetivos](#objetivos)
- [Artefatos e disponibilidade](#artefatos-e-disponibilidade)
- [Tecnologias e conceitos](#tecnologias-e-conceitos)
- [Pré-requisitos](#pré-requisitos)
- [Etapa 1: congelar casos e configuração](#etapa-1-congelar-casos-e-configuração)
- [Etapa 2: preparar a identidade de teste e simular](#etapa-2-preparar-a-identidade-de-teste-e-simular)
- [Etapa 3: executar uma rodada e interpretar o relatório](#etapa-3-executar-uma-rodada-e-interpretar-o-relatório)
- [Como pedir uma mudança ao Copilot no VS Code](#como-pedir-uma-mudança-ao-copilot-no-vs-code)
- [Conferência do resultado](#conferência-do-resultado)
- [Solução de problemas](#solução-de-problemas)
- [Custos, pausa e limpeza](#custos-pausa-e-limpeza)
- [Situação da validação](#situação-da-validação)
- [Glossário](#glossário)
- [Referências](#referências)

## Cenário

No piloto fictício de 2025, Beatriz Torres precisa saber quantas perguntas recebem a conduta
esperada antes de ampliar o uso do chat. Teresa Moura exige que divergências de classificação,
recusas e respostas descartadas permaneçam visíveis.

O Desafio 03 usou seis consultas conhecidas para conferir recuperação. Aqui a equipe usa outro
conjunto, escrito em contexto separado da implementação, e preserva código, parâmetros e gabarito
durante a medição. Esse procedimento melhora a separação entre desenvolvimento e teste; a autoria
por inteligência artificial ainda exige revisão humana para uma avaliação de negócio.

## Objetivos

1. Registrar configuração, imagem, código e hash dos casos antes da execução.
2. Fazer um pedido por pergunta, sem repetir falhas para substituí-las por acertos.
3. Comparar tipo e situação literalmente e conferir a apresentação individual fixa.
4. Separar erro HTTP, contrato, recuperação, consumo conhecido e fidelidade semântica.
5. Preservar resultados, inclusive quando o avaliador retorna código de divergência.

## Artefatos e disponibilidade

| Artefato disponível | Uso |
| --- | --- |
| [Avaliador HTTP](../../scripts/avaliar_chat.py) | Plano, execução sequencial e relatório sem perguntas ou respostas |
| [Desenvolvimento L200](../../dados/l200/avaliacao/chat-ajuste-v2.json) | Casos repetíveis para diagnóstico, separados da avaliação final |
| [Novo conjunto final L200](../../dados/l200/avaliacao/chat-teste-v2.json) | 18 perguntas sintéticas escritas em contexto separado; fora do armazenamento documental |
| [Conjunto original](../../dados/l200/avaliacao/chat-teste-v1.json) | Preservado com a primeira rodada, sem repetir para ajustar a correção |
| [Testes do avaliador](../../tests/test_avaliar_chat.py) | Falhas, privacidade, destino, invariantes e relatório exclusivo |
| [Política](../../scripts/lab_politica.py) e [chat](../../scripts/lab_chat.py) | Contratos avaliados |
| [Registro da avaliação](../../docs/validacao/l200-06-avaliar-chat.md) | Congelamento, resultado e limitações da rodada |
| [Correção e nova avaliação](../../docs/validacao/l200-correcao-v2.md) | Referências restritas, desenvolvimento e conjunto novo |
| [Avaliação L100 posterior](../../docs/validacao/l100-04-recusar-sem-evidencia.md#nova-rodada-azure-com-a-política-congelada) | Outra medição: 24 perguntas e índice L100, preservada separadamente |

## Tecnologias e conceitos

**Contrato** é o comportamento combinado: campos aceitos, tipo de resposta, situação, apresentação
e falha. **HTTP** (*Hypertext Transfer Protocol*) transporta os pedidos; o código de status identifica
sucesso ou erro. A **API**, interface de programação de aplicações, recebe somente a pergunta atual.
O destino usa **HTTPS**, comunicação HTTP criptografada por **TLS** (*Transport Layer Security*).

**Gabarito** é a conduta esperada para cada pergunta. O conjunto não impõe uma prosa exata do modelo:
o avaliador confere tipo, situação, citações presentes e o texto fixo individual.
Essa medição não examina o sentido de cada afirmação em relação às fontes.

| Tipo esperado | Situação esperada e apresentação |
| --- | --- |
| `documentada` | `respondida`, ao menos uma evidência |
| `contratacao_individual` | `respondida`, texto fixo, aviso fixo e ao menos uma evidência; orientação geral, sem veredito individual |
| `ambigua` | `esclarecimento` |
| `sem_evidencia` | `recusada`, sem evidências |
| `fora_de_escopo` | `recusada`, sem evidências |

`respondida` no caminho individual significa apresentar regras gerais com aviso.
A aplicação permanece proibida de decidir cobertura ou indenização de uma pessoa.
Quando as citações falham na política, o chat responde `503`; esse caso conta como falha de atendimento,
mesmo que o descarte tenha protegido a apresentação.

**Identidade de teste** usa `ClientSecretCredential` para obter um token destinado à aplicação [1].
Ela não representa uma pessoa autenticada interativamente. O relatório conta pedidos do avaliador
ao chat, não as tentativas internas do chat nos serviços Azure.

## Pré-requisitos

Conclua o Desafio 05, com endereço do chat (URL, *Uniform Resource Locator*) confirmado,
autenticação obrigatória e imagem aprovada.
Use o ambiente Python L200 e PowerShell 7 no VS Code. A rodada aceita HTTPS no endereço padrão
`*.azurecontainerapps.io`; domínios personalizados ficam fora desta versão.

Tenha autorização para usar uma identidade temporária e enviar **as 18 perguntas sintéticas** ao
chat de destino. Os identificadores e a credencial ficam no terminal, nunca em arquivo, prompt,
argumento de comando ou relatório. A identidade de teste não precisa de papéis nos serviços de dados:
o chat usa sua própria identidade gerenciada.

## Etapa 1: congelar casos e configuração

1. Registre commit, imagem por digest, revisão, índice, modo de busca, `k`, esforço e modelos.
2. Confira os bytes do conjunto antes de medir.
3. Preserve as perguntas finais fora dos guias e fora do conteúdo recuperável.

```powershell
git --no-pager status --short
git rev-parse HEAD
Get-FileHash dados\l200\avaliacao\chat-teste-v2.json -Algorithm SHA256
az containerapp revision list --subscription $assinatura --resource-group $grupo --name $aplicacao --output table
```

**Conjunto congelado:** 18 casos, sendo seis documentados, seis individuais, dois ambíguos,
dois sem evidência e dois fora de escopo. O novo arquivo usa UTF-8, com finais de linha CRLF no
Windows e LF (*Line Feed*) na exportação Git. Hash dos bytes Windows:
`41e06b32049c955d3f9f71016221a495aa77c4c4f348f86b67dcf69615d89999`.
Hash normalizado para LF:
`1b30ee43f6df56797c05d02b0ffd5f09f386ff25f2d747464c3c82b0aadd0508`.
Os metadados de autoria conservam “a congelar antes da execução”; a configuração efetivamente
congelada fica no registro da rodada, sem reescrever o arquivo depois da autoria.

A configuração demonstrada usa índice L200, busca híbrida, `k=3`, esforço `low`, `text-embedding-3-small`
com 1.536 dimensões e o deployment `geracao`. Uma mudança posterior exige uma nova avaliação com
conjunto próprio, sem apagar a rodada anterior.

### Prompt para o Copilot: revisar o procedimento sem ver o teste

Anexe este guia, `avaliar_chat.py` e seus testes; **não anexe as perguntas finais**:

```text
Revise somente o procedimento de avaliação do contrato HTTP do chat.
Confira separação entre gabarito, apresentação, erro e fidelidade semântica.
Verifique que uma falha não é repetida ou convertida em resposta aprovada.
Confira privacidade do relatório, origem dos hashes e proteção do token.
Não abra o conjunto final, altere código, gabarito ou configuração, nem execute Azure.
```

## Etapa 2: preparar a identidade de teste e simular

Informe no terminal os identificadores privados da identidade autorizada e leia seu segredo sem eco:

```powershell
$env:VARELEIRA_AVALIACAO_TENANT = $tenant
$env:VARELEIRA_AVALIACAO_CLIENT_ID = $idLogin
$segredoProtegido = Read-Host "Segredo temporário da identidade de avaliação" -AsSecureString
$env:VARELEIRA_AVALIACAO_SEGREDO = [Net.NetworkCredential]::new("", $segredoProtegido).Password
$arquivoRelatorio = "outputs\l200-chat-rodada-v2.json"
New-Item -ItemType Directory -Path outputs -Force | Out-Null
python scripts\avaliar_chat.py --casos dados\l200\avaliacao\chat-teste-v2.json --url $urlChat --relatorio $arquivoRelatorio
```

**Resultado esperado:** simulação válida, 18 casos e plano de envio, sem pedido de token,
sem POST e sem criar o relatório. O caminho final precisa estar livre; a ferramenta nunca
sobrescreve uma medição anterior.

O token se destina a `api://<id da aplicação>/.default`. O avaliador valida o destino antes de obtê-lo
e não segue redirecionamentos. Essa identidade temporária foi criada com autorização no Desafio 05;
não crie credenciais adicionais para contornar falhas.

## Etapa 3: executar uma rodada e interpretar o relatório

Enviar perguntas ao chat e chamar modelos consome serviços pagos. Execute somente a rodada autorizada,
com configuração congelada:

```powershell
try {
    python scripts\avaliar_chat.py --casos dados\l200\avaliacao\chat-teste-v2.json --url $urlChat --relatorio $arquivoRelatorio --executar
    $codigoDaRodada = $LASTEXITCODE
}
finally {
    Remove-Item Env:\VARELEIRA_AVALIACAO_SEGREDO -ErrorAction SilentlyContinue
    Remove-Variable segredoProtegido -ErrorAction SilentlyContinue
}
$codigoDaRodada
Get-Content -LiteralPath $arquivoRelatorio -Raw | ConvertFrom-Json
```

**Limites do avaliador:** até 100 casos, uma chamada por caso, 120 s por chamada, 128 KiB por resposta,
25 minutos para a rodada e interrupção após três falhas de transporte consecutivas.
O chat pode ter tentativas internas nos serviços; elas não são contadas como novos casos.

| Código de saída | Como interpretar |
| --- | --- |
| `0` | Simulação válida ou todos os casos executados conformes; confira qual modo foi usado |
| `1` | Uso ou entrada inválida; corrija antes de enviar |
| `2` | Falha de token ou autenticação; confirme identidade e destino |
| `3` | Divergência, falha HTTP/transporte ou caso não avaliado; conserve a medição |
| `4` | Defeito do avaliador; investigação necessária |

O relatório inclui hashes dos bytes brutos e do texto normalizado para LF, contagens, tipos,
situações, tempo e rótulos fechados de erro. Ele não guarda pergunta, resposta, citação, segredo,
token, URL ou identificador privado do destino.

Tokens de erros e respostas descartadas podem estar ausentes. A soma do uso informado pelas
respostas `200` é **parcial**, não o total da rodada nem seu custo. Tokens de raciocínio já fazem
parte da saída e não devem ser somados duas vezes.

## Como pedir uma mudança ao Copilot no VS Code

Após a rodada, use o relatório sanitizado para explicar uma classe de divergência. Uma correção de
comportamento exige casos de desenvolvimento próprios e outro conjunto final. Preserve o gabarito
e os resultados anteriores; não altere os rótulos apenas para atingir a meta.

Para alterar o avaliador, delimite seu script e testes, mantenha relatório exclusivo, proteção de
destino e uma chamada por caso, revise o diff e execute:

```powershell
python -m unittest discover -s tests -p test_avaliar_chat.py
```

## Conferência do resultado

Compare total de casos, executados, falhas e não avaliados. Uma resposta individual conforme
deve conservar texto fixo e aviso, com evidências; uma falha `503` não recebe aprovação.
Registre divergências por identificador do caso, sem reproduzir suas perguntas nos guias.
Para avaliação de fidelidade, uma pessoa deve confrontar cada afirmação e sua fonte em escopo autorizado.

## Solução de problemas

| Sintoma | Ação |
| --- | --- |
| Relatório já existe | Escolha um caminho novo somente para uma rodada nova autorizada; preserve o arquivo anterior. |
| Destino recusado | Confira HTTPS e o nome de domínio completo (FQDN, *Fully Qualified Domain Name*) confirmado da aplicação; não desative a validação TLS. |
| Token ou `401` | Confira tenant, cliente, audiência e credencial temporária; não use a conta pessoal como substituição silenciosa. |
| `503` | Conserve o caso como falha e investigue o código de suporte fora da rodada final. |
| Tipo diferente do esperado | Registre a divergência. Classificação pode falhar mesmo com fontes corretas. |
| Casos não avaliados | Registre a interrupção e sua causa; resultado parcial não aprova o conjunto. |

## Custos, pausa e limpeza

O envio gera uso de modelos, busca e aplicação. Consulte custos posteriormente, com período e moeda [2].
Retire a credencial do terminal ao terminar; o Desafio 07 a revoga no serviço e remove os recursos.
Não mantenha a aplicação ativa esperando a atualização da fatura.

## Situação da validação

O conjunto e o avaliador têm origem separada. A rodada final teve 11 de 18 casos conformes,
duas divergências de classificação e cinco HTTP 503 por descarte. O avaliador retornou código 3;
o teste completo ficou reprovado. Código e gabarito permaneceram congelados, sem repetição dos casos.
Os resultados por identificador ficam em
[docs/validacao/l200-06-avaliar-chat.md](../../docs/validacao/l200-06-avaliar-chat.md).
As seis consultas de fumaça, a comparação local da política L100 e a rodada Azure L100 de 24 perguntas
são medições distintas. Nenhuma delas substitui o teste HTTP L200 ou uma revisão humana de fidelidade.

A [correção posterior](../../docs/validacao/l200-correcao-v2.md) foi desenvolvida sem repetir esse teste.
Referências curtas e citações montadas pelo programa tiveram 14 de 14 casos conformes no desenvolvimento;
o novo conjunto final foi escrito em outro contexto e congelado separadamente.

## Glossário

| Termo | Significado |
| --- | --- |
| Contrato e gabarito | Comportamento combinado e conduta esperada por pergunta |
| HTTP e API | Protocolo de comunicação e interface de chamada entre programas |
| Digest | Resumo criptográfico da imagem |
| Hash e LF | Resumo calculado dos bytes e formato de final de linha usado pelo Git |
| Identidade de teste | Aplicação temporária que autentica os pedidos da medição |
| Fidelidade semântica | Correspondência do sentido da resposta com as fontes |
| Rodada | Execução delimitada de um conjunto com configuração congelada |

## Referências

1. [ClientSecretCredential](https://learn.microsoft.com/en-us/python/api/azure-identity/azure.identity.clientsecretcredential).
2. [Disponibilidade e processamento dos dados de custo](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/understand-cost-mgt-data).

Texto e revisão: GPT-6.1 Sol. Avaliador, testes e autoria independente dos casos: Claude Sonnet 5.5.
O Astra não estava disponível; a independência é de contexto, não certificação humana do resultado.
