# L200: correção de referências e nova avaliação

Registro de 10 de outubro de 2026. A rodada original permanece em
[l200-06-avaliar-chat.md](l200-06-avaliar-chat.md): 11 de 18 casos conformes, sem repetição das perguntas.

## Correção antes do novo teste

O contrato anterior pedia ao modelo que reproduzisse identificadores longos das projeções e
copiasse frases dos trechos. O chat agora envia referências curtas, `T1` a `Tn`, válidas somente
na requisição atual. O esquema restringe a seleção a essas referências. O programa monta as
citações com o conteúdo dos trechos selecionados e recupera seus identificadores originais depois
da validação.

O modelo continua selecionando as fontes e escrevendo o texto geral; a correção não comprova
que todas as afirmações sejam fiéis. A política L100, o mínimo de citação, a recusa de referências
desconhecidas e o texto fixo individual foram preservados. Trechos inteiros são apresentados sem
truncar condições; conteúdo acima do limite de 6.000 caracteres produz erro explícito.

As instruções L200 também distinguem a falta de tema ou referente, que exige esclarecimento,
de uma pergunta específica cuja informação não aparece nos trechos. Não foram incluídas perguntas
ou palavras dos conjuntos finais como regras do código.

## Desenvolvimento separado

Os 14 casos de `dados\l200\avaliacao\chat-ajuste-v2.json` foram escritos a partir das fontes sintéticas,
sem reutilizar as perguntas finais. Esse conjunto pode ser repetido para diagnóstico e seleção
de configuração; seus resultados não são uma avaliação independente.

| Execução de desenvolvimento | Resultado |
| --- | --- |
| Referência `e57c595`, híbrida, `k=3`, `low` | 7 de 14 conformes; sete descartes HTTP 503 |
| Primeira execução da candidata | 0 de 14; chamadas falharam por recurso não encontrado, causa HTTP 404 dos serviços |
| Candidata após reiniciar o servidor, sem alterar código ou parâmetros | 14 de 14 conformes; nenhum descarte, divergência ou erro |

Os relatórios preservam a
[referência](l200-desenvolvimento-baseline-k3.json),
[falha transitória da candidata](l200-desenvolvimento-candidata-k3.json) e
[execução após reinício](l200-desenvolvimento-candidata-k3-reinicio.json).
Não se substituiu a medição com erro pelo resultado posterior.

## Verificações locais

`.\.venv\Scripts\python.exe -m unittest discover -s tests` passou com 596 testes.
`.\.venv\Scripts\python.exe -m pip check` e `node --check web\app.js` passaram.
Os testes de regressão cobrem referências curtas restritas, remapeamento para identificadores
originais, citações integrais, campos inválidos e referências desconhecidas.
Código L100, Bicep, dependências e documentos sintéticos permaneceram inalterados.

Uma conferência adicional de navegador usou serviço explicitamente simulado, sem Azure.
A página apresentou uma citação de 2.463 caracteres e seu identificador longo completos,
como texto, sem cortar o fim da condição. O envio pelo botão funcionou; em largura de 390 pixels,
a página, a citação e a origem não transbordaram horizontalmente. Servidor e aba próprios foram
encerrados depois da conferência.

## Novo conjunto final

`dados\l200\avaliacao\chat-teste-v2.json` foi escrito em outro contexto, que leu somente os três
documentos sintéticos. O autor não teve acesso à implementação, aos resultados ou aos conjuntos
anteriores. O contrato foi fornecido antes da escrita.

| Item | Registro |
| --- | --- |
| Composição | 18 casos: seis documentados, seis individuais, dois ambíguos, dois sem evidência e dois fora de escopo |
| Referências de origem | 17 citações literais conferidas pelo autor; não foram injetadas como respostas do modelo |
| SHA-256 dos bytes Windows/CRLF | `41e06b32049c955d3f9f71016221a495aa77c4c4f348f86b67dcf69615d89999` |
| SHA-256 normalizado para LF | `1b30ee43f6df56797c05d02b0ffd5f09f386ff25f2d747464c3c82b0aadd0508` |
| Situação | Congelado antes da medição; configuração efetiva e resultado registrados em arquivos separados |

O teste original, seus bytes e a rodada 11 de 18 foram preservados. A nova medição foi feita uma
vez na aplicação hospedada, após congelar código, imagem e configuração.

## Resultado final da correção

| Critério | Resultado |
| --- | --- |
| Código congelado | `2c39a21e9437e6f7a4f2edf7c9ca4b1fdbb729f1` |
| Imagem | `sha256:fe6f1f959ff40d9f34eb4bf51c167e31bd69008b8a4c68f681edc08f9f3403f1` |
| Configuração | Índice L200, busca híbrida, `k=3`, esforço `low`, modo `Single` e autenticação obrigatória |
| Pedidos HTTP | 18 de 18 receberam HTTP 200, com uma tentativa por pergunta |
| Contrato esperado | 16 de 18 conformes; duas divergências de classificação |
| Erros e descartes | Nenhum erro de transporte, formato, resposta descartada ou caso não avaliado |
| Casos individuais | Cinco de seis conformes, com introdução fixa, aviso e evidências |
| Uso informado | 390 tokens de embeddings, 31.588 de entrada e 1.978 de saída; 848 de raciocínio já incluídos na saída |
| Tempo | Aproximadamente 44,9 s para a rodada |
| Código do avaliador | `3`, porque o conjunto completo ainda contém divergências |

| Tipo esperado | Casos | Conformes |
| --- | --- | --- |
| Documentada | 6 | 6 |
| Contratação individual | 6 | 5 |
| Ambígua | 2 | 1 |
| Sem evidência | 2 | 2 |
| Fora de escopo | 2 | 2 |

L200-V2-11 foi classificado como `sem_evidencia`/`recusada`, quando o gabarito esperava orientação
individual. L200-V2-14 foi classificado como `documentada`/`respondida`, quando o gabarito esperava
esclarecimento. Essas divergências foram preservadas; nenhum rótulo ou parâmetro foi alterado para
aprovar os dois casos.

O [relatório da rodada](l200-chat-avaliacao-final-v2.json) e o
[congelamento](l200-congelamento-final-v2.json) são arquivos sanitizados, sem perguntas, respostas,
credenciais ou identificadores privados do destino.
Os conjuntos v1 e v2 são diferentes: 11 de 18 e 16 de 18 não constituem uma comparação controlada
de qualidade. A comparação no mesmo conjunto foi a de desenvolvimento, registrada acima.

## Acesso e encerramento

A aplicação foi criada com ingresso interno, recebeu autenticação e só depois foi aberta externamente.
Token real de identidade temporária permitiu consultar o chat; um cabeçalho artificial de principal
foi recusado com HTTP 401. A identidade gerenciada da réplica recebeu três recusas HTTP 403:
leitura de blob, administração de índices e leitura administrativa do armazenamento.

A consulta de custos recebeu HTTP 200 sem linhas disponíveis; não confirmou o valor total da rodada.
Aplicação, pipeline, registro, principal e credencial próprios foram removidos após guardar o resultado.
A exclusão do grupo e o expurgo dos modelos concluíram. A conferência final confirmou grupo ausente,
nenhuma atribuição das identidades próprias, registro e principal de login ausentes e modelos
expurgados. Sete grupos e oito papéis do operador foram preservados, assim como outros recursos
em exclusão reversível.

O [resumo sanitizado da limpeza](l200-correcao-limpeza-sumario.json) registra o encerramento.
A exclusão do grupo levou 1.640,5 s; a espera pelo ambiente Container Apps foi acompanhada sem
enviar nova exclusão. Não restam recursos desta rodada nem servidores locais de validação em execução.

## Limites da entrega

Implementação, testes locais, exercícios de infraestrutura e resultados de avaliação são entregas
distintas de homologação de negócio. O conjunto completo de contrato ainda ficou reprovado, apesar
da ausência de descartes na nova rodada. A entrega permanece experimental, com as duas divergências
explicitamente registradas.

Uma aprovação de contrato não substituiria revisão semântica humana, autorização por documento,
teste de carga ou avaliação de produção. A classificação por modelo continua falível; gerar um novo
conjunto até obter um resultado favorável não resolveria essa limitação. As rodadas foram encerradas
sem repetir as perguntas finais nem ajustar o código com elas.

## Autoria

Código e testes por Claude Sonnet 5.5; novo conjunto final em contexto separado com o mesmo modelo.
Coordenação e documentação por GPT-6.1 Sol. Astra indisponível; nenhum Document Swarm foi executado.
