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
  `text-embedding-3-small` (embeddings). O L200 reutiliza esses deployments e suas versões;
  o L300 conserva esses deployments, dimensões e política. O L400 reutiliza os modelos e
  versões, com contingência de geração separada e índice candidato de 768 dimensões;
  sua comparação e limitações ficam no registro próprio.
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
  declara isso na seção "Autoria". O L200 recebeu autorização posterior, descrita abaixo;
  o L300 recebeu o pedido de implementação posterior, descrito abaixo.
  L400 recebeu pedido posterior de implementação, descrito abaixo.
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
- Em 10 de outubro de 2026, o mantenedor autorizou executar as etapas de publicação e avaliação e,
  depois, implementar e testar o L200, incluindo validação Azure necessária no destino anterior.
  Código e testes L200 usam Sonnet 5.5; guias e coordenação usam GPT-6.1 Sol, com Astra indisponível.
  Preserve essa autorização como registro da execução, não como permissão para outros destinos.
- O L200 usa fluxo fixo de recuperação, geração e política no chat FastAPI. O agente MAF do L100
  continua no console. Não apresente o chat como uma nova validação de escolha de ferramentas.
- Ingestão gerenciada: índice separado, Text Split e embeddings; `secao` e `clausulas` vazios nesta
  implementação. O indexador lê o prefixo do contêiner; o inventário controla a carga Python.
- Hospedagem L200: identidade gerenciada para imagem, busca e modelos; segredo somente do provedor
  de login em Container Apps Secrets. Crie com ingresso interno, confira EasyAuth e só depois abra
  externo. Pessoas autenticadas do tenant são o público atual; não invente filtro por pessoa/documento.
- Avaliações locais, consultas de fumaça, geração Azure e contrato HTTP são medições diferentes.
  Preserve gabaritos e código congelados após observar o teste final; falhas contam como falhas.
- A correção L200 envia referências curtas restritas por requisição e monta citações dos trechos
  selecionados no código, preservando a política L100 e os IDs originais na apresentação.
  O teste v1 ficou em 11/18 e foi preservado; o novo v2 teve 16/18, sem descartes e com duas
  divergências. Conjuntos distintos não são uma comparação controlada; a entrega é experimental.
- Em 10 de outubro de 2026, o mantenedor pediu avançar para o L300. O escopo desta rodada é
  implementação e validação local, com GPT-6.1 Sol na documentação e Sonnet 5.5 no código,
  sem novas operações Azure, atribuições de acesso ou ativação GitHub. Astra continua indisponível.
  Publicação de workflows, implantação, federação e conexão privada precisam de decisão própria.
- Após o fechamento local, o mantenedor confirmou a assinatura de testes e `brazilsouth` e
  autorizou criar somente um grupo exclusivo para o L300. O grupo foi criado e conferido vazio,
  com os oito grupos então preexistentes preservados. Nome e IDs permanecem no registro privado.
  Essa autorização não inclui implantação de serviços, carga, identidades, papéis, conexões,
  publicação ou Actions; continue coletando as decisões uma por vez.
- Posteriormente, o mantenedor autorizou executar e testar os laboratórios e remover e expurgar
  os recursos próprios ao final, sem continuar a coleta de perguntas. Use somente o grupo
  exclusivo, a assinatura privada e `brazilsouth` confirmados, dentro do teto aprovado.
  Preserve grupos, identidades e papéis anteriores. Essa rodada não ativa Actions, federação
  ou publicação; registre cada resultado real e a limpeza em `docs/validacao/l300-azure-validacao.md`.
- A rodada Azure L300 foi encerrada em 11 de outubro de 2026: grupo exclusivo e gerenciado
  ausentes, objetos Entra e modelos próprios expurgados, papéis temporários retirados e linha
  de base preservada. Isso não autoriza repetir a execução. Actions/OIDC, login humano e matriz
  Linux permanecem não executados. Preserve as falhas, retomadas e limitações do registro.
- Em 11 de outubro de 2026, o mantenedor pediu executar o L400 até o final com autonomia,
  sem perguntas intermediárias. Preserve a base L300, use somente as quatro fontes sintéticas
  aprovadas e os destinos privados/região anteriores, com grupo exclusivo novo e limpeza própria.
  O teto anterior de US$90 não vira um novo orçamento; custo efetivo L300 continua indisponível.
  Sol escreve documentação com Astra ausente, Sonnet 5.5 implementa código e testes.
  Essa rodada não ativa publicação, Actions ou confiança federada GitHub.
- L400 conserva modelos e versões anteriores, acrescenta geração de contingência do mesmo modelo
  e índice candidato separado de 768 dimensões. Alterar dimensão exige reindexar documentos e
  consultas compatíveis. Coordenação é opt-in; o modelo não escolhe filtro, papel ou destino.
  Compare estratégias em conjunto novo após congelar o código, contando falhas e uso desconhecido,
  sem ajustar ou repetir avaliações históricas para escolher a melhor resposta.
- O teste final L400 v1 foi executado uma vez na versão com correção de dimensão 768:
  referência e coordenação tiveram 16/16 conformes, sem ganho, com maior mediana e mais tokens
  de geração na coordenação. Preserve relatório, código e perguntas; não apresente esse resultado
  como fidelidade semântica ou homologação. A correção posterior de cancelamento HTTP não repetiu
  o conjunto final e possui provas próprias.
- Cancelamento L400: a desconexão pode não atravessar a borda Azure a tempo. O fluxo SSE usa
  cancelamento explícito autenticado pelo mesmo ator, registro de execuções ativas em memória,
  limite de admissão e remoção ao terminar. O registro é por processo com uma réplica; não aumentar
  réplicas sem redesenhar e testar o encaminhamento. Pedido remoto já enviado pode consumir tokens.
- A rodada Azure L400 foi encerrada em 11 de outubro de 2026: grupo exclusivo e gerenciado
  ausentes, zero recursos e papéis próprios, aplicativos e modelos expurgados; oito grupos,
  46 recursos e atribuições anteriores preservados. A primeira limpeza foi interrompida pela
  guarda de papéis herdados e retomada com escopo exato; preserve esse histórico.
  A consulta final de custo ficou sem linhas, não significa custo zero nem atendimento ao teto.
  Essa autorização histórica não permite novas execuções, publicação, Actions/OIDC ou produção.
- O L300 é opt-in: `VARELEIRA_EXIGIR_ACESSO_DOCUMENTAL=true` exige autenticação, tenant e índice L300.
  Os papéis de aplicação vêm do principal entregue pela borda EasyAuth obrigatória. A aplicação
  deriva classes estáticas por requisição, filtra todos os modos de busca antes da geração e usa
  `preFilter` com vetor. Papel desconhecido recusa antes de embeddings, busca e modelo.
  O padrão sem essa opção preserva o L200; demonstração e modo sem autenticação não validam L300.
- O manifesto L300 valida a carga, não é uma ACL propagada automaticamente. O indexador lê
  o prefixo inteiro e o chat autoriza classes; restrinja quem grava metadados e quem lê o índice
  diretamente. O roteiro operacional sintético foi apresentado e aprovado pelo mantenedor em
  10 de outubro de 2026, sem alterar texto, versão, tamanho ou hash. Essa aprovação é somente
  de conteúdo; Azure, publicação e Actions continuam sujeitos às autorizações próprias.
- A topologia L300 cria ambiente e aplicação Container Apps separados. Fases `rede`, `aplicacao`
  e `isolar` são exclusivas e usam implantação incremental. Isolamento depende de evidências,
  conexões compartilhadas aprovadas e configuração dos serviços preservada. Reaplicar L100/L200
  pode reabrir acesso público; isso exige revisão e autorização, não é limpeza automática.
- No encerramento completo autorizado, retire os shared private links próprios antes do serviço
  de busca e de seus destinos. O destino já ausente pode bloquear a exclusão da busca.
  Confira ausência real por listagem, não somente retorno de espera; não remova bloqueios nem
  recrie dependências automaticamente e não manipule o grupo gerenciado Container Apps.
  Listagens de atribuições podem incluir papéis fora do alvo: confira escopo e principal contra
  o inventário próprio antes de revogar e compare os papéis anteriores depois da limpeza.
- Os workflows L300 estão na principal desde os merges de 11 de outubro de 2026:
  `validar.yml` executa integração contínua (CI) em runners hospedados, só leitura e sem identidade
  Azure. `l300-implantar.yml` só aceita disparo manual (`workflow_dispatch`), exige runner
  self-hosted `vareleira-l300`, ambiente protegido e configuração em Secrets e identidade
  federada ainda inexistentes. Nunca foi executado; nenhuma federação OpenID Connect (OIDC)
  foi criada. Identidade federada de implantação e registro de login do chat são diferentes;
  somente o login do chat usa segredo efêmero na fase `aplicacao`.
  Não publique IDs ou configurações brutas nos logs.
- O mantenedor indicou uma assinatura de teste fora do repositório para validar
  os laboratórios. Nunca registre o ID dela, de tenants ou de pessoas em arquivos
  versionados; guarde esse tipo de evidência apenas em local privado.
- Não use Document Swarm por enquanto. Trabalhe diretamente, sem acionar esse
  fluxo salvo nova solicitação explícita do mantenedor.

## Estrutura e verificações

- Em 11 de outubro de 2026, o mantenedor selecionou gpt-6-astra (Astra) para revisar os
  28 guias, consolidar Git, publicar PRs/CI/pré-releases L300/L400 e avaliar as respostas
  existentes. Essa autorização não inclui merge, implantação Azure, login humano ou
  federação. Preserve a autoria anterior e registre esta revisão separadamente.
- A análise dos relatórios finais encontrou classificações e contagens, sem textos
  completos das respostas. Não reexecute conjuntos finais para reconstruí-las nem
  confunda reexame dos dois gabaritos L200 com avaliação semântica integral.
- As pré-releases `v0.3.0-l300` e `v0.4.0-l400` foram publicadas nos commits
  `0093629` e `429a4ba`, com CI Windows/Linux, Bicep e JavaScript aprovada.
  Os pull requests (PRs) #1 → #2 → #3 foram mesclados em sequência em 11 de outubro de 2026;
  a CI passou também na principal. As tags originais não incluem a rodada de operação pública.
  Essa CI não executou implantação, OIDC ou login humano. O registro histórico é
  `docs/validacao/publicacao-l300-l400.md`.
- Em 11 de outubro de 2026, o mantenedor autorizou corrigir o D07, completar as ferramentas e
  receitas públicas L300/L400, encerrar a lacuna semântica e mesclar os PRs #1 → #2 → #3.
  O D07 usa alvo aleatório diferente do índice informado; essa correção, encerramento, sondas
  e carga só foram testados localmente, nada validado no Azure.
  Os textos finais são tratados como irrecuperáveis,
  sem reexecução. Código/testes e coordenação: Claude Sonnet 5.5; documentação: GPT-6.1 Sol,
  com Astra indisponível. O PR desta rodada (aberto a partir da branch
  `fix/operacao-publica-l300-l400`, com base `main`) fica sem merge até ordem expressa.
  A autorização não inclui execução Azure, login humano, implantação Actions/OIDC/federação
  ou novas pré-releases. Registro: `docs/validacao/operacao-publica-l300-l400-2026-10-11.md`.

- `infra/` (Bicep e parâmetros por nível), `scripts/` (Python), `dados/` (documentos
  sintéticos e inventário), `desafios/` (guias), `requirements/`, `tests/` e `docs/`.
- Ambiente: Python 3.12 ou superior; requisitos L100, L200, L300 e L400 ficam em `requirements/`.
  `l300.txt` reutiliza `l200.txt`, e `l400.txt` reutiliza `l300.txt`, sem novos pacotes diretos.
- Testes sem Azure: `python -m unittest discover -s tests`.
- Bicep: `az bicep lint --file infra/main.bicep` e `az bicep build --file infra/main.bicep --stdout`.
- Bicep L200: os mesmos comandos com `infra/l200.bicep`; parâmetros sem segredos antes de
  `build-params --stdout`. Sintaxe da interface: `node --check web/app.js`.
- Bicep L300: lint/build com `infra/l300.bicep`, compilador 0.48.1 ou superior.
  Validação do manifesto, sem rede: `python scripts/gerenciar_ingestao_l300.py --etapa validar`.
  Plano local e compilação: `python scripts/operar_l300.py --etapa plano --fase rede --validar-bicep`.
  Não imprima a compilação do arquivo de parâmetros quando houver segredo real na sessão.
- Plano L400 sem rede: `python scripts/operar_l400.py --etapa planejar --validar-bicep`.
  Runtime com dublês: `python -m unittest discover -s tests -p test_orquestracao.py`.
- Ferramentas públicas, sem rede: `python scripts\planejar_encerramento.py --etapa modelo`,
  `python scripts\sonda_l300.py --etapa validar`, `python scripts\montar_contexto_sonda_l300.py --help`
  e `python scripts\gerar_carga_l400.py --help`. Planejar não executa; linha de base antes do grupo.
  Testes só com dublês; nenhuma dessas ferramentas foi validada no Azure.
- Instruções por tipo de arquivo ficam em `.github/instructions/`.
