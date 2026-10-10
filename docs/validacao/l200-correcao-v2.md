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

## Novo conjunto final

`dados\l200\avaliacao\chat-teste-v2.json` foi escrito em outro contexto, que leu somente os três
documentos sintéticos. O autor não teve acesso à implementação, aos resultados ou aos conjuntos
anteriores. O contrato foi fornecido antes da escrita.

| Item | Registro |
| --- | --- |
| Composição | 18 casos: seis documentados, seis individuais, dois ambíguos, dois sem evidência e dois fora de escopo |
| Referências de origem | 17 citações literais conferidas pelo autor; não serão injetadas como respostas do modelo |
| SHA-256 dos bytes Windows/CRLF | `41e06b32049c955d3f9f71016221a495aa77c4c4f348f86b67dcf69615d89999` |
| SHA-256 normalizado para LF | `1b30ee43f6df56797c05d02b0ffd5f09f386ff25f2d747464c3c82b0aadd0508` |
| Situação | Congelado antes da medição; configuração efetiva e resultado serão registrados separadamente |

O teste original, seus bytes e a rodada 11 de 18 foram preservados. A nova medição será feita uma
vez na aplicação hospedada, após congelar código, imagem e configuração. A aprovação de contrato
não substitui revisão semântica humana, autorização por documento ou avaliação de produção.

## Autoria

Código e testes por Claude Sonnet 5.5; novo conjunto final em contexto separado com o mesmo modelo.
Coordenação e documentação por GPT-6.1 Sol. Astra indisponível; nenhum Document Swarm foi executado.
