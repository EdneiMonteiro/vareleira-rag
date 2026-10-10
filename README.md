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
O teste final do chat teve 11 de 18 casos conformes; a entrega continua experimental e não homologa
o atendimento completo.

No L100 e L200, `text-embedding-3-small` calcula os *embeddings* (vetores numéricos dos textos), e
`gpt-5.4-mini` gera as respostas. Esses modelos foram usados em `brazilsouth` em 9 e 10 de outubro de 2026.
O modelo usado pelo aluno no Copilot e os modelos de autoria e revisão da documentação são escolhas
separadas. Modelos dos próximos níveis dependem de disponibilidade, cota e avaliação.

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
| `.github` | Instruções do Copilot, modelos de issue e de pull request |

Para verificar o projeto localmente, sem Azure, use Python 3.12 ou superior:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements\l200.txt
python -m unittest discover -s tests
```

Para uma cópia somente do L100, use `requirements\l100.txt`.

### Evolução planejada

| Nível | Objetivo | Continuidade |
| --- | --- | --- |
| L100 | Entender ingestão por código e consulta RAG em console | Preparar a base compartilhada |
| L200 | Comparar ingestão gerenciada e publicar o chat em Azure Container Apps | Reutilizar documentos, busca e modelos |
| L300 | Automatizar, controlar acesso e operar com dependências privadas | Evoluir identidade, rede e observabilidade |
| L400 | Medir coordenação de agentes, resiliência e uso de múltiplos deployments | Comparar com a solução anterior e testar migrações |

O L100 contém sete desafios incrementais. Os próximos níveis também terão sequência e procedimentos
de migração para mudanças de rede, índice ou identidade, com verificação e recuperação.
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
| L100, Desafio 07: Key Vault, service principal e privilégio mínimo | Disponível e validado no Azure: identidade temporária, dois papéis, cinco operações, pergunta como aplicação e limpeza conferidos |
| Condições gerais, glossário e perguntas frequentes sintéticos (v1.0) | Disponíveis; aprovação do mantenedor confirmada |
| Perguntas dos conjuntos de ajuste e de teste (sintéticas) | Disponíveis; aprovação confirmada, com a independência parcial e os resultados registrados |
| L200: ingestão, comparação, chat e hospedagem | Implementados e exercitados; teste final 11 de 18, reprovado para o contrato completo; limpeza concluída e preexistentes preservados |
| Níveis L300 e L400 | Planejados |

O L100 foi publicado na [pré-release `v0.1.0-l100`](https://github.com/EdneiMonteiro/vareleira-rag/releases/tag/v0.1.0-l100),
no commit `d4a93cc`; a [pré-release `v0.1.1-l100`](https://github.com/EdneiMonteiro/vareleira-rag/releases/tag/v0.1.1-l100)
sincroniza aprovação e avaliação posterior, sem incorporar o L200. As medições permanecem separadas no
[registro do D04](docs/validacao/l100-04-recusar-sem-evidencia.md).
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
