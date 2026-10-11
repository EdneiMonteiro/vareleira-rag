# Revisão para publicação L300

Registro de 11 de outubro de 2026. Revisão documental por gpt-6-astra (Astra),
preservando autoria e revisões anteriores. O mantenedor autorizou revisão,
consolidação Git, publicação de pull requests, integração contínua e pré-releases.
Essa autorização não inclui merge, implantação, federação ou novo acesso Azure.

## Composição da versão

A árvore L300 foi recuperada da cópia de 60 arquivos preservada **antes** da
implementação L400, sobre a base Git `5af7612`. Não foi simulada removendo partes
do runtime L400. Os 21 guias L100, L200 e L300 receberam a revisão documental
atual; código, corpus e avaliações mantêm os conteúdos anteriores.

## Revisão dos guias

Foram lidos integralmente os sete guias de cada um dos três níveis, contra o
padrão de autoria e os parsers, bibliotecas, parâmetros e registros pertinentes.
As correções delimitam permissões, destinos, simulação, migrações, resultados
esperados e siglas. A aprovação histórica não foi convertida em nova validação
Azure ou em homologação de negócio.

| Nível | Correções principais |
| --- | --- |
| L100 | Preservação de parâmetros e isolamento posterior; alcance real das verificações; diferença entre modelo e deployment; testes finais históricos; limites do verificador de identidade |
| L200 | Papéis da busca e da aplicação separados; sessão com padrões L200; fluxo fixo sem seleção de ferramentas MAF; distinção entre construção e simulação; não repetição do teste v2 |
| L300 | Manifesto não é ACL automática; tenant autorizado explícito; recusa por classes; limites dos descritores, das sondas privadas e da limpeza; CI distinta de implantação federada |

## Verificações locais desta revisão

Executadas no Windows, com Python 3.12.10 do ambiente virtual existente:

| Comando ou conferência | Resultado |
| --- | --- |
| `python -m unittest discover -s tests`, usando o Python da `.venv` na árvore L300 | 859 casos: 858 aprovados e um ignorado por permissões POSIX |
| Análise sintática dos exemplos PowerShell L100/L200/L300, sem execução | 186 blocos sem erro de sintaxe |
| Links e âncoras locais da árvore L300 | 944 referências conferidas em 58 arquivos Markdown, antes deste registro; sem falhas |
| Comparação Git dos documentos e conjuntos L100/L200 recuperados | Nenhuma alteração de conteúdo; finais de linha normalizados pelo Git |

Esses números não são somados às execuções históricas como casos independentes.
As referências externas foram preservadas; não houve auditoria online integral,
validação da interface atual do VS Code ou consulta de catálogo, preço e cota.
Resultados de CI pertencem à execução GitHub vinculada ao pull request, não a
essas verificações locais.

## Limitações que acompanham a pré-release

1. `verificar_identidade.py`, no L100 D07, tenta excluir um índice de nome fixo.
   A operação não é inofensiva se existir um índice homônimo e a identidade puder
   excluí-lo. O guia agora exige ausência e exclusividade do alvo; **não usar esse
   verificador em ambiente compartilhado**. O código preexistente não foi corrigido
   por esta revisão documental. A mensagem de privilégio mínimo só cobre as
   operações tentadas, não todo o acesso da identidade.
2. As sondas privadas L300 e o script completo de encerramento não integram a
   entrega pública. Os guias identificam a dependência de executor, inventário e
   roteiro administrativo revisados. O helper público valida descritores; ele
   não coleta as evidências nem implanta ou remove todo o ambiente.
3. Login humano, implantação por Actions/OIDC e homologação de produção
   permanecem não executados. A limpeza Azure é evidência histórica, não
   autorização para recriar ou remover recursos.
4. O L200 conserva duas divergências em 18 casos. A publicação não transforma
   esse resultado em aprovação completa nem altera perguntas, gabaritos ou código
   para melhorar a contagem.

## Atualização de 11 de outubro de 2026

Os PRs #1 → #2 → #3 foram mesclados; a integração contínua (CI) passou também na principal.
O D07 usa alvo aleatório; as sondas e o planejador de encerramento agora têm ferramentas e receitas públicas.
Essas correções só foram testadas localmente, sem validação Azure; as tags originais não as incluem.
O [registro consolidado](operacao-publica-l300-l400-2026-10-11.md) preserva o alcance e as limitações desta revisão histórica.
