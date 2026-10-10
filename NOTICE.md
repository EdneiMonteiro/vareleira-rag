# Origem e atribuições

## Projeto e contexto

Vareleira RAG é um projeto educacional de Ednei Monteiro.
O laboratório desenvolve a jornada do Assistente de Apólices descrita na
[Vareleira](https://github.com/EdneiMonteiro/vareleira), do mesmo autor.

Referência inicial: contexto **0.1.0**, revisão
[`d17a24bd9fdf16a5b3dba34e07764852a8477859`](https://github.com/EdneiMonteiro/vareleira/tree/d17a24bd9fdf16a5b3dba34e07764852a8477859).
Fontes principais: `rag.html`, `empresa.html` e
`dados/contexto-v0.1.0.json`, sob CC BY 4.0 para conteúdo.

A documentação inicial adapta o escopo do piloto interno de 2025 e os padrões
de licenciamento, suporte e contribuição da Vareleira. Não copia as restrições
temporárias de interação nem a automação de publicação do site.

As condições gerais, o glossário e as perguntas frequentes do Vareleira Lar
(`dados/l100`) são conteúdo **novo e sintético**, criado para este laboratório
por Ednei Monteiro com apoio de ferramentas de IA, sob CC BY 4.0. Não derivam de
produtos, apólices ou documentos reais. O mantenedor confirmou sua aprovação para
uso educacional em 9 de outubro de 2026. O Bicep, os scripts Python e os testes são código sob MIT.

## Origem do assessment

O marco de agosto de 2026 vem do
[assessment do AI CoE Playbook](https://github.com/EdneiMonteiro/ai-coe-playbook/blob/f63f36f6e6e4c595577707da0ca1bb0aa6476991/assessment/exemplo-preenchido.md),
de Ednei Monteiro, sob CC BY 4.0, revisão
`f63f36f6e6e4c595577707da0ca1bb0aa6476991`.
É uma avaliação fictícia, não um resultado técnico deste laboratório.
O piloto interno foi acrescentado pela narrativa da Vareleira e antecede o
assistente externo do assessment.

## Licenças, marcas e serviços

Os textos integrais de MIT e CC BY 4.0 em `LICENSES` foram preservados a partir
do repositório Vareleira. Consulte [LICENSE](LICENSE) para os escopos.

Badges são fornecidos por Shields.io e GitHub. Nomes como Microsoft e GitHub
são usados para identificação; seus titulares mantêm os direitos de marca.
Não há afiliação, endosso ou suporte oficial dessas empresas.

Os scripts do L100 usam as bibliotecas `azure-identity`, `azure-storage-blob`,
`azure-search-documents` e `azure-keyvault-secrets`, do Azure SDK para Python, sob licença MIT; a
biblioteca `openai`, da OpenAI, sob licença Apache-2.0 (usada para chamar os
deployments de embeddings e de geração do Azure); e as bibliotecas
`agent-framework-core` e `agent-framework-openai`, do Microsoft Agent Framework, sob licença
MIT (Desafio 05), além das dependências delas. Elas
são instaladas por quem executa o laboratório (`requirements/l100.txt`) e mantêm
suas próprias licenças; seu código não é incorporado a este repositório.
O Bicep CLI, a Azure CLI e o Python são ferramentas instaladas à parte.

Novos materiais externos devem registrar origem, licença e adaptações aqui.
DOIs, versões e resultados de outros projetos não identificam este laboratório.
