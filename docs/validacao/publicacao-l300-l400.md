# Publicação L300/L400 e integração contínua

Registro de 11 de outubro de 2026, por gpt-6-astra (Astra). O mantenedor autorizou
revisar, consolidar, publicar PRs, executar CI, publicar pré-releases e avaliar
as respostas existentes. Não houve merge, implantação, atribuição de papéis,
confiança federada, login humano ou novas chamadas Azure nesta rodada.

## Árvores e versões publicadas

| Entrega | Commit | Publicação |
| --- | --- | --- |
| L300, com 21 guias L100/L200/L300 revisados | `0093629338f189a6f11271165f428ce8275611b8` | [Pré-release v0.3.0-l300](https://github.com/EdneiMonteiro/vareleira-rag/releases/tag/v0.3.0-l300) e [PR #2](https://github.com/EdneiMonteiro/vareleira-rag/pull/2) |
| L400, com os 28 guias revisados | `429a4ba2e0893908037c7a2ddea13e951ed6b2be` | [Pré-release v0.4.0-l400](https://github.com/EdneiMonteiro/vareleira-rag/releases/tag/v0.4.0-l400) e [PR #3](https://github.com/EdneiMonteiro/vareleira-rag/pull/3) |

A árvore L300 vem da cópia preservada antes da implementação L400, sobre `5af7612`.
Ela passou pela suíte própria antes de ser commitada. O commit L400 tem L300 como
ancestral e acrescenta suas alterações, sem substituir fontes ou avaliações antigas.
Os documentos de revisão preservam a autoria inicial Sol/Sonnet e identificam Astra
separadamente.

A cadeia de revisão é #1 → #2 → #3. O #2 usa a branch do L200 como base;
o #3 usa a branch do L300. A principal não recebeu merge. Ambas as releases foram
conferidas como publicadas, não rascunhos, e marcadas como pré-release, não como
versão estável mais recente.

Este registro e os links no README são uma atualização documental posterior
às tags. Não modificam os commits publicados nem seus relatórios congelados.

## CI executada no GitHub

O workflow `Validar` foi acionado por `pull_request`, sem login Azure, ambiente
protegido ou permissão OIDC. As quatro tarefas de cada execução concluíram com
`success`; os logs de testes foram lidos para conferir as contagens, não apenas
o estado agregado.

| Execução | Linux / Python 3.12 | Windows / Python 3.12 | Bicep e JavaScript |
| --- | --- | --- | --- |
| [L300: 38146305865](https://github.com/EdneiMonteiro/vareleira-rag/actions/runs/38146305865), commit `0093629` | 859 aprovados, sem ignorados | 858 aprovados e um ignorado POSIX | Aprovados |
| [L400: 38146387934](https://github.com/EdneiMonteiro/vareleira-rag/actions/runs/38146387934), commit `429a4ba` | 1.015 aprovados, sem ignorados | 1.014 aprovados e um ignorado POSIX | Aprovados |

Comandos dos runners e resultados:

- `python -m pip install -r requirements/l300.txt`: aprovado em ambas as matrizes.
  O L400 reutiliza esses requisitos, sem pacote direto adicional.
- `python -m pip check`: aprovado.
- `python -m unittest discover -s tests`: resultados na tabela; nenhuma chamada Azure.
- `az bicep install --version "$BICEP_VERSAO"`, com `v0.48.1`: aprovado.
- `"$bicep" lint "$arquivo"` e `"$bicep" build "$arquivo" --stdout`, para todos
  os `.bicep` em `infra`: aprovados, sem avisos no lint.
- `node --check web/app.js`: aprovado.

O Windows ignora a conferência de permissões POSIX; ela passou na matriz Linux.
Essas execuções completam a lacuna de suíte integral em runners hospedados,
mas não validam o runner privado nem o workflow de implantação.
Os hashes das ações checkout/setup-python foram consultados no GitHub antes da execução.

## Revisão e avaliação

As correções e as verificações locais estão nos registros de
[L300](revisao-publicacao-l300.md) e [L400](revisao-publicacao-l400.md).
A [análise das respostas](avaliacao-semantica-2026-10-11.md) examinou os 50
registros finais e reavaliou os dois gabaritos divergentes L200 contra as fontes.

Os textos originais não constam dos relatórios nem das cópias privadas conferidas.
Por isso, a revisão semântica integral permanece bloqueada. Não se geraram
respostas substitutas nem se alteraram os 16/18 L200 ou os 16/16 por estratégia L400.

As releases e os PRs explicitam as limitações: verificador D07 inadequado para
ambiente compartilhado, sondas/limpeza privadas sem receita pública completa,
cancelamento L400 por processo e uma réplica, cobrança indisponível e ausência
de homologação de produção. Publicação e CI não removem essas restrições.
