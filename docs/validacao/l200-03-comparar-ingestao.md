# L200, Desafio 03: registro de validação

Registro do [guia de comparação](../../desafios/L200/03-comparar-ingestao.md), executado no Azure em
10 de outubro de 2026. Os índices coexistiram no destino autorizado; documentos reais não foram usados.

## Comparação de recuperação

Seis consultas de conferência embutidas no gerenciador, `k=3`, nos mesmos três documentos:

| Modo | L100, 54 trechos | L200, 21 trechos |
| --- | --- | --- |
| Texto | 6 de 6 assuntos esperados recuperados | 6 de 6 |
| Vetorial | 6 de 6 | 6 de 6 |
| Híbrida | 6 de 6 | 6 de 6 |

Os comandos `--etapa comparar --modo texto`, `vetorial` e `hibrida` terminaram com código 0.
O comando publicado de `scripts\buscar_trechos.py` também foi exercitado no índice L200,
sem geração de resposta.

Essa comparação é um teste de fumaça conhecido, não um benchmark independente.
Não mede superioridade da divisão, fidelidade de respostas ou ausência de vereditos.

## Exclusão reversível e recuperação

| Operação | Resultado observado |
| --- | --- |
| Conferência inicial | Três documentos, 21 trechos |
| Exclusão do blob de glossário | Somente a cópia criada nesta rodada; arquivos locais e índice L100 preservados |
| Execução de detecção | Um item processado, nenhuma falha, erro ou aviso |
| Conferência da ausência | Código 3 esperado; 16 trechos de dois documentos, glossário ausente |
| Reposição pela carga do inventário | Blob reenviado a partir do documento aprovado |
| Reindexação | Glossário voltou ao índice |
| Conferência final | Código 0; três documentos, 21 trechos e quatro definições iguais |

O teste demonstrou remoção dos trechos filhos pela projeção quando a política detectou a exclusão.
Foi uma exclusão autorizada e reversível em recursos novos, não uma alteração dos documentos originais.
O caminho de `undelete` isolado não foi exercitado; reenviar o arquivo aprovado foi a recuperação usada.

## Diferenças preservadas

Text Split não preenche seção nem cláusulas. A fonte indexada é a URL do blob, e o identificador opaco
do trecho muda quando a projeção reprocessa o documento. Os scripts de consulta reutilizam os campos
comuns; scripts estruturais L100 não são validadores do esquema L200.

Metadados de hash foram mapeados, sem nova verificação criptográfica do texto extraído.
Os bytes do blob foram conferidos pelo verificador de documentos.

## Limites

Não houve experimento de qualidade para escolher tamanho de trecho com o conjunto final.
O teste histórico D06 não foi repetido. Os prompts Copilot novos não foram enviados no VS Code.
Os resultados finais HTTP pertencem a outro conjunto e estão no Desafio 06.
