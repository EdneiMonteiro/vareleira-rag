# Vareleira RAG

[![ORCID](https://img.shields.io/badge/ORCID-0009--0006--0765--4201-A6CE39?logo=orcid&logoColor=white)](https://orcid.org/0009-0006-0765-4201)
[![Status: em desenvolvimento](https://img.shields.io/badge/status-em_desenvolvimento-yellow)](#estado-do-laboratório)
[![Código: MIT](https://img.shields.io/badge/C%C3%B3digo-MIT-yellow.svg)](LICENSES/MIT.txt)
[![Conteúdo: CC BY 4.0](https://img.shields.io/badge/Conte%C3%BAdo-CC%20BY%204.0-lightgrey.svg)](LICENSES/CC-BY-4.0.txt)
[![Último commit](https://img.shields.io/github/last-commit/EdneiMonteiro/vareleira-rag)](https://github.com/EdneiMonteiro/vareleira-rag/commits/main)

Laboratório educacional do **Assistente de Apólices com geração aumentada por
recuperação (RAG, do inglês Retrieval-Augmented Generation)** da
[Vareleira](https://vareleira.com/), uma seguradora inteiramente fictícia.
O objetivo é aprender a consultar condições gerais sintéticas de seguro
residencial, recuperar evidências e responder com fontes verificáveis.

**L100 e L200:** fundamentos em console e evolução para ingestão gerenciada e chat.
O L100 usa Python, Microsoft Agent Framework (MAF) e infraestrutura Azure em Bicep; seus sete desafios
foram executados no Azure e aprovados pelo mantenedor. O L200 reutiliza a base e a política, acrescenta
Text Split, comparação dos índices e chat FastAPI em Azure Container Apps com identidade gerenciada
e autenticação obrigatória. Os recursos de validação foram removidos, as identidades temporárias
foram retiradas e os recursos preexistentes foram preservados.
O novo teste do chat teve 16 de 18 casos conformes, sem descartes, após uma correção de referências.
A rodada original com 11 de 18 foi preservada. A entrega continua experimental, com duas divergências
de classificação e sem homologação do atendimento completo.

**L300:** autorização por classes de documento, ingestão separada, definições de rede privada e
automação manual. Código e sete guias foram validados localmente; a regressão posterior aos testes
Azure tem 859 casos, com 858 aprovados e um ignorado por permissões POSIX,
próprias de sistemas Unix, no Windows.
Após autorização posterior, a [validação Azure L300](docs/validacao/l300-azure-validacao.md)
foi concluída: ingestão privada, fontes por perfil, controles do protocolo de transferência de
hipertexto (HTTP), bloqueio público dos
três serviços de dados e retorno de revisão foram exercitados em um grupo temporário exclusivo.
O grupo e o grupo gerenciado foram removidos; identidades, papéis e expurgos próprios foram
conferidos, com os recursos anteriores preservados.
GitHub Actions e confiança federada não foram executados nessa rodada Azure.
A integração contínua (CI) foi executada posteriormente para publicação e na principal após os
merges, conforme o [registro de publicação](docs/validacao/publicacao-l300-l400.md).
A implantação federada por OpenID Connect (OIDC, protocolo de identidade) permanece não executada.

**L400:** coordenação limitada com Microsoft Agent Framework, contingência de geração,
índice candidato e comparação com a referência L300 foram implementados e exercitados.
A suíte final teve 1.015 casos, com 1.014 aprovados e um ignorado no Windows;
os 100 testes do runtime e 24 de sanitização operacional, incluindo permissões POSIX, passaram em Linux.
A comparação nova teve **16/16 conformes nas duas estratégias**, sem ganho observado da coordenação,
que usou mais tokens de geração e teve maior latência mediana.
O cancelamento explícito autenticado foi conferido separadamente depois dessa comparação,
sem repetir o conjunto final ou usar desconexão como prova de interrupção remota.
O [roteiro L400](docs/roteiro-l400.md) organiza sete desafios; o
[registro de validação](docs/validacao/l400-validacao.md) separa testes, comparação, falhas e
encerramento dos temporários. A limpeza foi verificada: grupo exclusivo e gerenciado ausentes,
zero recursos e papéis próprios, identidades e modelos expurgados, com oito grupos, 46 recursos
e atribuições anteriores preservados. Cobrança efetiva ainda indisponível não significa custo zero.
Nenhum resultado L400 é tratado como aprovação automática para produção.

A [revisão Astra dos 28 guias](docs/validacao/revisao-publicacao-l400.md) permanece como registro
histórico. A [rodada de operação pública](docs/validacao/operacao-publica-l300-l400-2026-10-11.md)
corrige o verificador L100 D07, que agora usa um nome de índice descartável aleatório, diferente
do índice informado. Ela acrescenta ferramentas e receitas públicas de sonda, encerramento e carga.
Na entrega inicial, o verificador corrigido e as ferramentas públicas novas tinham apenas
testes locais. As correções foram mescladas pelo pull request
(PR, proposta de alteração) [#4](https://github.com/EdneiMonteiro/vareleira-rag/pull/4) e publicadas na
[pré-release `v0.4.1-l400`](https://github.com/EdneiMonteiro/vareleira-rag/releases/tag/v0.4.1-l400),
em 11 de outubro de 2026, por ordem expressa do mantenedor.
Depois, a [rodada Azure das ferramentas públicas](docs/validacao/operacao-publica-azure-validacao-2026-10-11.md)
exercitou planejador, sonda interna, carga e migração, preservando falhas e retomadas.
As duas conferências de encerramento foram aprovadas, com 13 e 28 passos.
O [PR #5](https://github.com/EdneiMonteiro/vareleira-rag/pull/5) foi mesclado com a correção
de herdadas; o [PR #6](https://github.com/EdneiMonteiro/vareleira-rag/pull/6) foi mesclado por
delegação, com os achados e o registro, publicados em
[`v0.4.2-l400`](https://github.com/EdneiMonteiro/vareleira-rag/releases/tag/v0.4.2-l400).
**A prova é parcial:** dados ainda públicos, sem fase `isolar` ou provas pós-isolamento.
Não comprova isolamento nem homologação; login humano e implantação Actions/OIDC não foram
executados. O verificador L100 D07 corrigido e os helpers externos continuam sem nova prova Azure.
A [análise de respostas](docs/validacao/avaliacao-semantica-2026-10-11.md) preserva as duas
divergências L200 e encerra a lacuna histórica como texto irrecuperável no alcance da busca.
Não localizar as respostas não comprova sua inexistência; o conteúdo continua sem avaliação
semântica integral, e nenhum conjunto final foi reexecutado.

No L100, L200 e L300, `text-embedding-3-small` calcula os *embeddings* (vetores numéricos dos textos), e
`gpt-5.4-mini` gera as respostas. Esses modelos foram usados em `brazilsouth` entre 9 e 11 de outubro de 2026.
O modelo usado pelo aluno no Copilot e os modelos de autoria e revisão da documentação são escolhas
separadas. O L300 conservou os modelos e as versões dos deployments anteriores na validação Azure.
O L400 conservou esses modelos e versões, criou um deployment de geração de contingência
separado e executou a comparação sem repetir o conjunto após observar os resultados.

## Comece pelo primeiro desafio

Leia o [L100 — Desafio 01: preparar o ambiente e organizar a base documental](desafios/L100/01-preparar-ambiente.md).
Ele é **executável** e foi validado de ponta a ponta no Azure em 9 de outubro
de 2026, em Windows com PowerShell; a
[situação da validação](desafios/L100/01-preparar-ambiente.md#situação-da-validação)
lista o que foi e o que não foi conferido, e o
[registro de trabalho](docs/validacao/l100-01-preparar-ambiente.md) guarda a matriz
completa. Os documentos de seguro são sintéticos e novos. O mantenedor confirmou
**a aprovação do material do L100 em 9 de outubro de 2026**.

Depois, siga para o [L100 — Desafio 02: dividir, vetorizar e indexar os documentos](desafios/L100/02-indexar-documentos.md),
também executável e validado no Azure em 9 de outubro de 2026
([situação da validação](desafios/L100/02-indexar-documentos.md#situação-da-validação);
[registro de trabalho](docs/validacao/l100-02-indexar-documentos.md)). Ele continua o
primeiro: reaproveita os documentos do Blob Storage e acrescenta um serviço de busca, cobrado por hora
enquanto existir, e um deployment (instância nomeada de modelo) de embeddings, cobrado por tokens usados.

Continue pelos desafios abaixo. Os Desafios 03 a 06 são sequenciais; o 07 reutiliza a infraestrutura
e o programa do 03.

| Desafio | Tema | Situação da validação e registro |
| --- | --- | --- |
| [03: responder com fontes](desafios/L100/03-responder-com-fontes.md) | Geração e conferência dos identificadores citados | [Validação do D03](desafios/L100/03-responder-com-fontes.md#situação-da-validação); [registro do D03](docs/validacao/l100-03-responder-com-fontes.md) |
| [04: recusar sem evidência](desafios/L100/04-recusar-sem-evidencia.md) | Tipos de pergunta, citações literais e recusas | [Validação do D04](desafios/L100/04-recusar-sem-evidencia.md#situação-da-validação); [registro do D04](docs/validacao/l100-04-recusar-sem-evidencia.md) |
| [05: agente com MAF](desafios/L100/05-agente-com-maf.md) | Decisão de busca, limites e rastro | [Validação do D05](desafios/L100/05-agente-com-maf.md#situação-da-validação); [registro do D05](docs/validacao/l100-05-agente-com-maf.md) |
| [06: medir a recuperação e as respostas](desafios/L100/06-avaliar-respostas.md) | Conjuntos separados; acerto@k (cobertura dos assuntos) e MRR (média do inverso da posição) | [Validação do D06](desafios/L100/06-avaliar-respostas.md#situação-da-validação); [registro do D06](docs/validacao/l100-06-avaliar-respostas.md) |
| [07: identidade da aplicação](desafios/L100/07-identidade-da-aplicacao.md) | Key Vault e identidade de aplicação (*service principal*) com permissões delimitadas | [Validação do D07](desafios/L100/07-identidade-da-aplicacao.md#situação-da-validação); [registro do D07](docs/validacao/l100-07-identidade-da-aplicacao.md) |

Os Desafios 03 a 07 foram validados no Azure em 9 de outubro de 2026. Após autorização do mantenedor,
o D07 confirmou a consulta ao índice, o uso dos modelos e três recusas HTTP 403 com a identidade da
aplicação. A credencial, os papéis e a identidade foram removidos; o cofre e o recurso de modelos foram
expurgados, e os recursos preexistentes foram preservados.
O detector original do D04 foi substituído por texto fixo para casos classificados como individuais,
com citações e aviso. A comparação local foi seguida de uma rodada Azure com 24 perguntas novas:
22 de 23 casos comparáveis seguiram o contrato, e os 12 individuais tiveram texto fixo e aviso.
Uma pergunta esperada como ambígua foi recusada como sem evidência; a classificação ainda pode falhar.
O teste histórico do D06 teve duas falsas recusas em 12 e ficou abaixo da meta. Esses limites estão
documentados nos guias. O mantenedor confirmou a aprovação do texto, do código, dos documentos
sintéticos e dos conjuntos de perguntas em 9 de outubro de 2026.
Essa aprovação não altera as medições nem elimina as limitações registradas.

O curso atende pessoas de negócio, arquitetura, operações e desenvolvimento.
Cada desafio combina cenário da Vareleira, explicações das tecnologias,
artefatos, prática orientada, glossário, boas práticas e prompts de GitHub
Copilot no Visual Studio Code (VS Code). Use os arquivos fornecidos ou peça mudanças ao Copilot;
revise o que será executado e confira o resultado.

**Pré-requisito:** acesso a uma assinatura Azure ativa, com permissões adequadas
às atividades. O uso assistido também exige acesso ao GitHub Copilot.
Cobranças do Azure e consumo do Copilot são independentes. Executar o desafio
cria recursos reais e pode gerar custo; permissões, custos e limpeza estão
descritos no próprio guia.

## Estrutura do repositório

| Pasta | Conteúdo |
| --- | --- |
| `desafios` | Guias dos desafios, organizados por nível |
| `infra` | Bicep e parâmetros por nível |
| `scripts` | Scripts Python de carga, indexação, consulta, geração de respostas, agente, avaliação e identidade |
| `dados` | Documentos sintéticos e inventários |
| `requirements` | Dependências Python por nível |
| `tests` | Testes automáticos, sem acesso ao Azure |
| `docs` | Padrão de autoria dos desafios e registros de validação (`docs/validacao`) |
| `web` | Página do chat, interação JavaScript e estilos |
| `.github` | Instruções do Copilot, modelos de issue/PR e definições de workflows |

Para verificar o projeto localmente, sem Azure, use Python 3.12 ou superior:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements\l400.txt
python -m unittest discover -s tests
```

Para uma cópia somente do L100, use `requirements\l100.txt`; para L200, use `requirements\l200.txt`.
O arquivo L300 reutiliza os requisitos L200, e o L400 reutiliza o L300.
Instale dependências ao preparar uma cópia nova ou quando faltarem bibliotecas;
uma instalação existente pode ser conferida com `python -m pip check`.

### Níveis e continuidade

| Nível | Objetivo | Continuidade |
| --- | --- | --- |
| L100 | Entender ingestão por código e consulta RAG em console | Preparar a base compartilhada |
| L200 | Comparar ingestão gerenciada e publicar o chat em Azure Container Apps | Reutilizar documentos, busca e modelos |
| L300 | Automatizar, controlar acesso e operar com dependências privadas | Evoluir identidade, rede e observabilidade |
| L400 | Medir coordenação de agentes, resiliência e uso de múltiplos deployments | Comparar com a solução anterior e testar migrações |

L100, L200, L300 e L400 contêm sete desafios incrementais por nível, com procedimentos
de migração para mudanças de rede, índice ou identidade, verificação e recuperação.
Remova recursos temporários de comparação quando terminar a atividade.

### Continue pelo L200

O [roteiro L200](docs/roteiro-l200.md) explica decisões, reaproveitamento e limites. Comece pela
reconstrução da base: os recursos das validações anteriores foram removidos, e a continuidade depende
dos arquivos versionados, não da existência de um ambiente do instrutor.

| Desafio | Prática e registro |
| --- | --- |
| [01: reconstruir a base](desafios/L200/01-reconstruir-base.md) | Versão, destino, documentos e índice Python; [registro](docs/validacao/l200-01-reconstruir-base.md) |
| [02: ingestão gerenciada](desafios/L200/02-ingestao-gerenciada.md) | Identidade da busca e pipeline separado; [registro](docs/validacao/l200-02-ingestao-gerenciada.md) |
| [03: comparar ingestão](desafios/L200/03-comparar-ingestao.md) | 54 e 21 trechos, três modos e recuperação documental; [registro](docs/validacao/l200-03-comparar-ingestao.md) |
| [04: chat local](desafios/L200/04-chat-local.md) | Interface, fontes, isolamento e falhas; [registro](docs/validacao/l200-04-chat-local.md) |
| [05: hospedar o chat](desafios/L200/05-hospedar-chat.md) | Imagem, identidade gerenciada e autenticação na borda; [registro](docs/validacao/l200-05-hospedar-chat.md) |
| [06: avaliar o chat](desafios/L200/06-avaliar-chat.md) | Avaliador HTTP e conjunto próprio, separado das consultas de fumaça; [registro](docs/validacao/l200-06-avaliar-chat.md) |
| [07: operar, recuperar e limpar](desafios/L200/07-operar-recuperar-limpar.md) | Revisões, custos e remoções com alvo explícito; [registro](docs/validacao/l200-07-operar-recuperar-limpar.md) |

A ingestão gerenciada recuperou os assuntos das seis consultas de fumaça nos dois índices e três
modos; isso não é um benchmark independente. O chat teve respostas reais e também descartes HTTP 503.
A borda recusou pedidos anônimos e um cabeçalho artificial com 401. A identidade gerenciada recebeu
três recusas 403 fora de seus papéis. A autenticação testada usou identidade temporária, não login
interativo de uma pessoa; autorização por documento e público restrito a pessoas específicas ficam
fora desta implementação.

### Continue pelo L300

O [roteiro L300](docs/roteiro-l300.md) explica classificação, migração por fases, caminhos privados
de consulta e ingestão e fronteiras da automação. O chat conserva o fluxo fixo L200; o agente
Microsoft Agent Framework (MAF) do L100 permanece no console.

| Desafio | Prática e alcance |
| --- | --- |
| [01: reproduzir a base](desafios/L300/01-reproduzir-base.md) | Inventário e base reconstruída no Azure: 54 trechos L100 e 21 L200 |
| [02: atualizar a base](desafios/L300/02-atualizar-base.md) | Quatro fontes, hashes e classes; ciclo privado 24 → 21 → 24 |
| [03: autorizar documentos](desafios/L300/03-filtrar-acesso.md) | Papéis por requisição, filtro nos três modos e recusa antes do modelo |
| [04: dependências privadas](desafios/L300/04-dependencias-privadas.md) | Receita pública exercitada em rede privada, com falhas e retomadas; sem isolamento nesta rodada |
| [05: automatizar a entrega](desafios/L300/05-automatizar-entrega.md) | CI na principal; implantação manual com runner próprio e federação não executada |
| [06: conferir operação](desafios/L300/06-conferir-operacao.md) | Logs do Job e consulta interna observados; descritor e helpers externos sem nova medição |
| [07: recuperar e limpar](desafios/L300/07-recuperar-limpar.md) | Planejador offline orientou dois encerramentos Azure aprovados; herdadas ignoradas e contadas |

O sinalizador `VARELEIRA_EXIGIR_ACESSO_DOCUMENTAL=true` exige autenticação, tenant e índice L300.
Os papéis `Vareleira.Atendimento` e `Vareleira.Corretor` definem classes estáticas de acesso.
O padrão desligado conserva L200. A autorização ocorre antes de recuperar o contexto; a busca
vetorial usa `preFilter` e o servidor recusa trechos incompatíveis antes da geração.

O manifesto rege a carga, enquanto o indexador lê o prefixo inteiro e o chat autoriza classes.
Controle quem escreve blobs/metadados e quem consulta o índice diretamente. O novo roteiro
operacional é sintético, sem regras de seguro novas, e foi aprovado pelo mantenedor em
10 de outubro de 2026. Essa aprovação não autoriza envio de dados ou alterações no Azure.
As três fontes L100 conservam seus conteúdos e hashes.

Confira o manifesto e o plano sem Azure:

```powershell
.\.venv\Scripts\python.exe scripts\gerenciar_ingestao_l300.py --etapa validar
.\.venv\Scripts\python.exe scripts\operar_l300.py --etapa plano --fase rede --validar-bicep
```

A migração cria ambiente e aplicação Container Apps separados. As fases `rede`, `aplicacao`
e `isolar` são exclusivas e exigem implantação incremental. O fechamento público dos dados
depende de consulta, ingestão e manutenção privadas observadas e autorizadas. Os custos de
endpoints, DNS e recursos gerenciados são adicionais; o registro de imagens Basic continua
público autenticado. Reaplicar a base L100/L200 pode reabrir dados e exige revisão.
O [registro local L300](docs/validacao/l300-validacao-local.md) reúne comandos, resultados e
limites da validação. A imagem deve ser construída da revisão L300; reutilizar uma tag anterior
não acrescenta os filtros ao contêiner.

### Continue pelo L400

O [roteiro L400](docs/roteiro-l400.md) conserva a referência convencional e delimita a complexidade
adicional. A comparação teve 16/16 conformes em ambas as estratégias, sem ganho observado.
O cancelamento explícito foi validado separadamente; a simples desconexão através da borda
não comprova interrupção do workflow.

| Desafio | Prática e alcance |
| --- | --- |
| [01: delimitar a coordenação](desafios/L400/01-delimitar-coordenacao.md) | Referência, fontes, identidade, limites e plano local |
| [02: coordenar especialistas](desafios/L400/02-coordenar-especialistas.md) | Planejamento e redação MAF, recuperação filtrada e política original |
| [03: operar deployments](desafios/L400/03-operar-deployments.md) | Contingência e aplicação internas exercitadas; falha da trava e retomada registradas |
| [04: evoluir o índice](desafios/L400/04-evoluir-indice.md) | Candidato de 768 dimensões, promoção/retorno e qualificação humana dos deltas exercitados |
| [05: comparar estratégias](desafios/L400/05-comparar-estrategias.md) | Conjunto novo congelado, falhas no denominador e relatório preservado |
| [06: testar carga e interrupção](desafios/L400/06-testar-carga-interrupcao.md) | Gerador público exercitado com falha de host, seis 200 e quatro 200/oito ocupado; carga pequena |
| [07: recuperar e limpar](desafios/L400/07-recuperar-limpar.md) | Encerramento público de 28 passos aprovado, com espera assíncrona e linha de base preservada |

Consulte o [registro L400](docs/validacao/l400-validacao.md) para as provas de limpeza e os limites.
O registro de cancelamento é local ao processo e exige uma réplica; sua evolução para múltiplas
réplicas precisa de um desenho e testes próprios. O curso não homologa a aplicação para produção.

## O caso do laboratório

Na narrativa, em **2025**, Beatriz Torres, responsável pelo Atendimento,
identifica respostas divergentes para perguntas semelhantes: as equipes
consultam versões distintas de documentos. O piloto interno atende
**Atendimento e corretores** e começa pelo produto **Vareleira Lar**.
Teresa Moura, diretora técnica de Subscrição, é a autoridade sobre as regras
do produto.

O piloto é anterior ao assistente externo registrado no assessment de
agosto de 2026. As soluções em produção desse assessment pertencem à ficção,
não são entregas deste repositório.

Contexto adotado: **Vareleira 0.1.0**, na
[revisão d17a24b](https://github.com/EdneiMonteiro/vareleira/tree/d17a24bd9fdf16a5b3dba34e07764852a8477859).
Consulte a [introdução da jornada](https://vareleira.com/rag.html), o
[contexto estruturado versionado](https://github.com/EdneiMonteiro/vareleira/blob/d17a24bd9fdf16a5b3dba34e07764852a8477859/dados/contexto-v0.1.0.json)
e as [atribuições](NOTICE.md).

## Objetivos e limites

O L100 exercita:

- Preparação de documentos sintéticos com produto, versão, vigência fictícia
  e autoridade da fonte.
- Recuperação de trechos e localização da fonte, com documento e versão.
- Respostas sustentadas por referências localizáveis nos documentos.
- Tratamento de perguntas ambíguas, fora de escopo ou sem evidência suficiente.
- Medição da recuperação, dos tipos de resposta, das situações e das frases esperadas.

Comparação entre versões documentais e avaliação mais ampla da fidelidade estão previstas para a
evolução do laboratório.

Por exemplo, **“O meu seguro cobre danos elétricos?”** não pode ser respondida
como confirmação de cobertura individual apenas com condições gerais.
A análise de uma contratação depende dos documentos individuais. A política do protótipo aplica
recusas e, no caminho individual, introdução fixa, citações e aviso. Confira também erros de
classificação e a interpretação das fontes antes de usar o resultado.
As coberturas, exclusões e franquias fictícias estão nas
[Condições Gerais sintéticas](dados/l100/documentos/vareleira-lar-condicoes-gerais-v1.0.md)
do L100: conteúdo sintético novo, aprovado pelo mantenedor para o exercício.

**Fora do escopo:** dados pessoais reais; decisões de cobertura individual,
indenização ou elegibilidade; emissão ou alteração de contratos; execução de
ações em sistemas; uso em produção sem avaliação própria.
O site institucional fornece o contexto narrativo; as regras do exercício estão nos documentos
sintéticos do repositório.

## Estado do laboratório

| Entrega | Situação |
| --- | --- |
| Escopo, contexto narrativo, licenças e políticas do repositório | Disponíveis |
| Padrão de autoria e instruções do Copilot para o projeto | Disponíveis |
| L100, Desafio 01: Bicep, carga e conferência de documentos no Blob Storage | Disponível e validado no Azure, com as ressalvas do registro de validação |
| L100, Desafio 02: divisão em trechos, embeddings, índice no Azure AI Search e consulta sem resposta gerada | Disponível e validado no Azure, com as ressalvas do registro de validação |
| L100, Desafio 03: deployment de geração e respostas com fontes | Disponível e validado no Azure, com as ressalvas do registro de validação |
| L100, Desafio 04: política de resposta com citações literais e recusa sem evidência | Disponível e validado no Azure, com as ressalvas do registro de validação |
| L100, Desafio 05: agente do Microsoft Agent Framework com ferramenta de busca limitada | Disponível e validado no Azure, com as ressalvas do registro de validação |
| L100, Desafio 06: conjuntos de ajuste e de teste, métricas de recuperação e de respostas | Disponível e validado no Azure; o conjunto de teste foi medido uma vez e a meta de escolha não foi atingida nele |
| L100, Desafio 07: Key Vault, service principal e privilégio mínimo | Execução Azure histórica: identidade temporária, dois papéis, cinco operações, pergunta como aplicação e limpeza; verificador corrigido em 11 de outubro testado apenas localmente |
| Condições gerais, glossário e perguntas frequentes sintéticos (v1.0) | Disponíveis; aprovação do mantenedor confirmada |
| Perguntas dos conjuntos de ajuste e de teste (sintéticas) | Disponíveis; aprovação confirmada, com a independência parcial e os resultados registrados |
| L200: ingestão, comparação, chat e hospedagem | Implementados e exercitados; nova rodada 16 de 18, sem descartes, com duas divergências de classificação; histórico preservado |
| L300: autorização, ingestão, rede e automação | Implementado e exercitado no Azure autorizado; testes e limpeza concluídos, histórico preservado. CI Windows/Linux aprovada também na principal; implantação Actions/OIDC e login humano não executados |
| L400: coordenação, comparação, contingência e recuperação | Implementado e exercitado no Azure autorizado; testes e limpeza concluídos. Comparação 16/16 em ambas, sem ganho; CI aprovada também na principal; limites e histórico preservados |
| [Operação pública L300/L400, 11 de outubro de 2026](docs/validacao/operacao-publica-l300-l400-2026-10-11.md): encerramento, sonda, carga e correção do D07 | Entrega inicial PR #4/`v0.4.1-l400`: 1.308 casos locais, OK com três ignorados. PRs #5/#6 e `v0.4.2-l400`: correções e prova Azure parcial, encerrada e registrada; D07 L100 corrigido continua apenas local |

O L100 foi publicado na [pré-release `v0.1.0-l100`](https://github.com/EdneiMonteiro/vareleira-rag/releases/tag/v0.1.0-l100),
no commit `d4a93cc`; a [pré-release `v0.1.1-l100`](https://github.com/EdneiMonteiro/vareleira-rag/releases/tag/v0.1.1-l100)
sincroniza aprovação e avaliação posterior, sem incorporar o L200. As medições permanecem separadas no
[registro do D04](docs/validacao/l100-04-recusar-sem-evidencia.md).
O L200 está na [pré-release experimental `v0.2.0-l200`](https://github.com/EdneiMonteiro/vareleira-rag/releases/tag/v0.2.0-l200),
no commit `5b70b37`, com o teste reprovado e a limpeza concluída registrados.
A [pré-release corrigida `v0.2.1-l200`](https://github.com/EdneiMonteiro/vareleira-rag/releases/tag/v0.2.1-l200)
preserva essa história e acrescenta referências restritas, novo teste de 16 de 18 sem descartes
e o encerramento da rodada de correção. O [PR #1](https://github.com/EdneiMonteiro/vareleira-rag/pull/1)
foi mesclado na principal em 11 de outubro de 2026, por autorização expressa do mantenedor.

As pré-releases [L300 `v0.3.0-l300`](https://github.com/EdneiMonteiro/vareleira-rag/releases/tag/v0.3.0-l300)
e [L400 `v0.4.0-l400`](https://github.com/EdneiMonteiro/vareleira-rag/releases/tag/v0.4.0-l400)
continuam apontando para as árvores originais nos commits `0093629` e `429a4ba`, com CI
Windows/Linux, Bicep e JavaScript aprovada. Essas tags não incluem as correções desta rodada.
Os [PRs #2](https://github.com/EdneiMonteiro/vareleira-rag/pull/2)
e [#3](https://github.com/EdneiMonteiro/vareleira-rag/pull/3) foram mesclados em 11 de outubro de 2026,
na sequência #1 → #2 → #3; a CI passou também nos pushes da principal.
O [registro de publicação](docs/validacao/publicacao-l300-l400.md) preserva a publicação anterior.
O [registro desta rodada](docs/validacao/operacao-publica-l300-l400-2026-10-11.md) separa os merges,
os testes locais novos e o encerramento da lacuna semântica das execuções Azure históricas.
As correções foram mescladas pelo [PR #4](https://github.com/EdneiMonteiro/vareleira-rag/pull/4)
em 11 de outubro de 2026, por ordem expressa do mantenedor, com commit de merge e branch preservada.
Foi publicada a [pré-release `v0.4.1-l400`](https://github.com/EdneiMonteiro/vareleira-rag/releases/tag/v0.4.1-l400),
com tag anotada nesse commit de merge. Ela contém L100 a L400 com as correções e os registros.
Os [PRs #5](https://github.com/EdneiMonteiro/vareleira-rag/pull/5)
e [#6](https://github.com/EdneiMonteiro/vareleira-rag/pull/6) foram mesclados; foi publicada
[`v0.4.2-l400`](https://github.com/EdneiMonteiro/vareleira-rag/releases/tag/v0.4.2-l400)
por delegação final do mantenedor, com os achados e o
[registro Azure](docs/validacao/operacao-publica-azure-validacao-2026-10-11.md).
`v0.4.1-l400` e as versões anteriores permanecem intactas, sem essa evidência.
O encerramento completo preservou oito grupos, 46 recursos e a listagem de 20 atribuições;
17 foram comparadas, três herdadas ignoradas e contadas. Custo efetivo indisponível não é zero.
Não foram publicadas `v0.3.1-l300` nem `v0.1.2-l100`. Os guias L300 corrigidos e a imagem da sonda
dependem da árvore L400: o montador inclui `scripts\gerar_carga_l400.py`, e o L300 D04 aponta
para o L400 D06. Uma entrega separada exige reconstrução da árvore e novas verificações.

A versão 0.1.0 do contexto é **do universo Vareleira**, não a versão deste código. Os desafios só criam recursos no
Azure quando você executa os comandos deles; permissões, custos e limpeza estão
descritos em cada guia.

## Participação e suporte

| Necessidade | Referência |
| --- | --- |
| Tirar dúvidas e propor a evolução do laboratório | [Discussions](https://github.com/EdneiMonteiro/vareleira-rag/discussions) |
| Relatar um problema reproduzível | [Issues](https://github.com/EdneiMonteiro/vareleira-rag/issues) |
| Contribuir | [CONTRIBUTING.md](CONTRIBUTING.md) |
| Consultar suporte e seus limites | [SUPPORT.md](SUPPORT.md) |
| Entender ficção, privacidade e riscos | [DISCLAIMER.md](DISCLAIMER.md) |
| Relatar vulnerabilidades em privado | [SECURITY.md](SECURITY.md) |
| Consultar regras de convivência | [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) |
| Consultar autoria e créditos | [CONTRIBUTORS.md](CONTRIBUTORS.md) |

Projeto pessoal de **Ednei Monteiro**, sem afiliação, endosso ou suporte
oficial da Microsoft, do GitHub ou de uma seguradora. Suporte comunitário,
sem prazo de resposta garantido. Use somente dados sintéticos e nunca publique
segredos ou documentos reais de segurados.

## Licenças e citação

**Código e configurações:** [MIT](LICENSES/MIT.txt).
**Documentação, narrativa e dados sintéticos:** [CC BY 4.0](LICENSES/CC-BY-4.0.txt).
São escopos distintos, não opções de licença para o mesmo material.
Veja [LICENSE](LICENSE) e [NOTICE.md](NOTICE.md).

Referência sugerida:

> Monteiro, Ednei. *Vareleira RAG: laboratório educacional de consulta a
> condições gerais de seguro com fontes documentais*. 2026.
> https://github.com/EdneiMonteiro/vareleira-rag

Informe também a revisão utilizada. Os metadados estão em [CITATION.cff](CITATION.cff).
Este projeto não possui DOI próprio.
