# Orientações do projeto Vareleira RAG

## Curso e público

- Escreva em pt-BR para público misto, não apenas desenvolvedores.
- Organize o curso em níveis L100, L200, L300 e L400, cada um com desafios
  incrementais. Reutilize recursos anteriores quando viável; documente migrações.
- Siga o [padrão de autoria](../docs/guia-de-autoria.md).
- Cada desafio inclui cenário, objetivos, artefatos existentes, conceitos,
  pré-requisitos, prática, resultados esperados, glossário, boas práticas e fontes.
- Ensinar GitHub Copilot no VS Code faz parte do objetivo: inclua prompts
  específicos, contexto a anexar, orientação de terminal e projeto, revisão de
  alterações e conferência dos resultados.
- Não suponha conhecimento prévio de programação. Explique siglas no primeiro
  uso, mesmo quando também aparecem no glossário.
- Use dicas, alertas, analogias e mnemônicos originais, sem copiar séries editoriais.

## Contexto e tecnologia

- Preserve o universo fictício Vareleira 0.1.0 e o piloto interno de 2025.
  Não reescreva os resultados históricos do assessment de agosto de 2026.
- Use apenas documentos sintéticos. Regras de seguro novas precisam de revisão;
  não as apresente como condições já existentes no contexto.
- A direção técnica é Python, Microsoft Agent Framework e Azure, com Bicep
  em `infra`. No L100, os deployments são o `gpt-5.4-mini` (geração) e o
  `text-embedding-3-small` (embeddings); os modelos dos demais níveis ainda precisam ser definidos.
- Diferencie o modelo que auxilia a autoria, o modelo usado pelo aluno no
  Copilot e os deployments de geração e embeddings da aplicação Azure.

## Segurança e execução

- Exija assinatura Azure ativa e permissões proporcionais à atividade.
  Login bem-sucedido não comprova autorização de dados nem de implantação.
- Receba destinos explicitamente; não fixe IDs do ambiente do instrutor em
  documentação, código ou parâmetros públicos.
- Não coloque segredos no código, prompts, saídas ou histórico Git.
- Separe gerar código de executá-lo. Não provisione, atribua permissões, envie
  dados ou exclua recursos sem autorização correspondente.
- Preserve recursos e alterações preexistentes. Documente custo, destino,
  efeitos e limpeza de cada etapa executável.

## Estado e autoria

- Não invente artefatos ou comandos de execução. Identifique pendências sem
  criar links para arquivos inexistentes.
- Registre o que foi realmente conferido, sem confundir consulta de conta,
  revisão documental, teste local e validação Azure de ponta a ponta.
- Preferência do mantenedor: Astra para documentação e Sonnet 5.5 para código
  e scripts. Confirme a disponibilidade; não substitua modelos silenciosamente.
  Essa preferência não configura nem garante a seleção de modelos no editor.
- Neste primeiro desafio (L100, Desafio 01), o mantenedor autorizou a
  implementação de Bicep, scripts, dados sintéticos e testes, feita com Sonnet 5.5.
  Documentos novos de seguro exigem revisão de conteúdo antes do uso.
- O mantenedor também pediu a implementação do L100, Desafio 02, sob a mesma
  regra, e depois a de todos os desafios do L100 (Desafios 03 a 07), em 9 de outubro de 2026.
  Como o Astra não estava disponível, o Sonnet 5.5 escreveu também a documentação deles, e cada guia
  declara isso na seção "Autoria". Os níveis L200 a L400 continuam sem implementação até nova orientação.
- Em 9 de outubro de 2026, o mantenedor pediu uma nova revisão documental do L100 com GPT-6.1 Sol,
  contra seu guia de estilo. Preserve a autoria inicial e identifique o modelo da revisão separadamente.
- Criar identidades, credenciais ou papéis (Desafio 07) exige autorização explícita de quem administra o
  tenant e a assinatura. Sem ela, não crie: escreva o roteiro, marque as etapas como não validadas e
  registre a pendência.
- Em 9 de outubro de 2026, após o relato das pendências, o mantenedor autorizou o prosseguimento.
  O D07 foi executado na assinatura de teste anteriormente indicada: identidade e credencial
  temporárias, dois papéis de dados, verificações e limpeza. Isso não autoriza novas execuções
  nem outros destinos; continue exigindo a autorização correspondente e preserve a revisão humana.
- O mantenedor confirmou a aprovação do material existente do L100 em 9 de outubro de 2026.
  O inventário registra os três documentos sintéticos como `aprovada`, sem alteração de seu texto,
  versão, tamanho ou hash. Preserve as medições e as limitações; a aprovação não transforma o
  conjunto de teste em uma amostra independente nem autoriza novas regras ou novos destinos.
- O mantenedor indicou uma assinatura de teste fora do repositório para validar
  os laboratórios. Nunca registre o ID dela, de tenants ou de pessoas em arquivos
  versionados; guarde esse tipo de evidência apenas em local privado.
- Não use Document Swarm por enquanto. Trabalhe diretamente, sem acionar esse
  fluxo salvo nova solicitação explícita do mantenedor.

## Estrutura e verificações

- `infra/` (Bicep e parâmetros por nível), `scripts/` (Python), `dados/` (documentos
  sintéticos e inventário), `desafios/` (guias), `requirements/`, `tests/` e `docs/`.
- Ambiente: Python 3.12 ou superior; `python -m pip install -r requirements/l100.txt`.
- Testes sem Azure: `python -m unittest discover -s tests`.
- Bicep: `az bicep lint --file infra/main.bicep` e `az bicep build --file infra/main.bicep --stdout`.
- Instruções por tipo de arquivo ficam em `.github/instructions/`.
