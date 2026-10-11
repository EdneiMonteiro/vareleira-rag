# L300 — Desafio 06: conferir acesso, conectividade e registros de operação

[Início do laboratório](../../README.md) · [Desafio 05](05-automatizar-entrega.md) · [Desafio 07](07-recuperar-limpar.md)

| Item | Descrição |
| --- | --- |
| Situação | Perfis, rede, ingestão e logs reais conferidos; login humano e Actions não executados |
| Público | Atendimento, operações, arquitetura e desenvolvimento |
| Resultado | Evidências separadas de aplicação, identidade, rede e ingestão, com falhas e pendências explícitas |
| Custo | Dublês locais dispensam serviços. Consultas reais usam busca, embeddings e geração; logs têm armazenamento e retenção |

## Conteúdo

- [Cenário](#cenário)
- [Objetivos](#objetivos)
- [Artefatos e disponibilidade](#artefatos-e-disponibilidade)
- [Tecnologias e conceitos](#tecnologias-e-conceitos)
- [Pré-requisitos](#pré-requisitos)
- [Etapa 1: conferir o caminho local](#etapa-1-conferir-o-caminho-local)
- [Etapa 2: preparar as provas Azure](#etapa-2-preparar-as-provas-azure)
- [Etapa 3: revisar registros e classificação das falhas](#etapa-3-revisar-registros-e-classificação-das-falhas)
- [Etapa 4: registrar a decisão de continuidade](#etapa-4-registrar-a-decisão-de-continuidade)
- [Como pedir uma mudança ao Copilot no VS Code](#como-pedir-uma-mudança-ao-copilot-no-vs-code)
- [Conferência do resultado](#conferência-do-resultado)
- [Solução de problemas](#solução-de-problemas)
- [Custos, pausa e limpeza](#custos-pausa-e-limpeza)
- [Situação da validação](#situação-da-validação)
- [Glossário](#glossário)
- [Referências](#referências)

## Cenário

No piloto fictício de 2025, Beatriz Torres precisa distinguir uma recusa de acesso de uma falha
na ingestão ou de uma resposta descartada pela política. A equipe usa um identificador de suporte
para localizar o pedido, sem guardar seu texto nos registros.

Teresa Moura conserva as regras e a avaliação de negócio como responsabilidades separadas.
As verificações deste desafio medem controles e operação; a qualidade das respostas continua
com as limitações observadas no L200.

## Objetivos

1. Conferir que fontes restritas ficam fora do contexto do modelo.
2. Distinguir teste local de identidade, rede e dados no Azure.
3. Relacionar falhas aos seus mecanismos, sem ampliar permissões por tentativa.
4. Produzir registro público sanitizado e manter detalhes do ambiente em local privado.

Os conjuntos finais L100 e L200 permanecem congelados. Use casos sintéticos de operação próprios
para as novas verificações; eles não constituem uma nova avaliação cega de respostas.

## Artefatos e disponibilidade

| Artefato | Uso |
| --- | --- |
| [Servidor web](../../scripts/chat_web.py) | Identificador, rota, status, tempo e causa curta |
| [Chat e política](../../scripts/lab_chat.py) | Recuperação, geração, citações e descarte explícito |
| [Regras de acesso](../../scripts/lab_acesso.py) | Classes permitidas por requisição |
| [Operação L300](../../scripts/operar_l300.py) | Conferência de planos e evidências sem publicar dados do ambiente |
| [Avaliador web L200](../../scripts/avaliar_chat.py) | Contrato de avaliação preservado, separado da prova de acesso |
| [Testes](../../tests) | Dublês dos serviços e casos negativos de aplicação |

Rotas de saúde continuam com o contrato do L200 e não executam uma pergunta no modelo.
O helper `conferir` lê um descritor preenchido pelo operador; ele avalia completude e coerência,
sem obter as medições do Azure.

## Tecnologias e conceitos

**HTTP**, protocolo de transferência de hipertexto da interface web, usa códigos de status:
`401` indica autenticação necessária,
`403` indica acesso recusado e `503` indica indisponibilidade da operação. No chat, o código de
suporte e a causa curta ajudam a distinguir rede, limites de serviço e descarte da resposta.

Uma **probe** é uma verificação usada pela plataforma para decidir se o contêiner está saudável
ou pronto [1]. Neste projeto, `/healthz` confere o processo e `/readyz` a inicialização.
A prova de consulta requer uma operação autenticada que recupere fontes e use os serviços.

**Telemetria** reúne medidas e eventos da operação. O ambiente envia registros ao Log Analytics,
serviço de retenção e consulta. O desenho da consulta deve considerar custo e dados pessoais
que possam estar presentes nos logs da plataforma [2].
O **tenant** é o diretório de identidades. Uma **claim** é uma informação emitida no token.
O **deployment** é a instância nomeada de modelo usada pela aplicação.
O **DNS**, sistema de nomes de domínio, resolve o serviço para o endereço do caminho autorizado.

## Pré-requisitos

Conclua a classificação documental, o filtro, a topologia e o plano de automação.
Abra o projeto no Visual Studio Code (VS Code), selecione `.venv` e use PowerShell 7.
A parte local dispensa credenciais.

Para uma prova Azure, confirme assinatura ativa, identidades por perfil, destino e caminho de rede
autorizados. As identidades de teste devem ter os papéis necessários à operação negativa:
uma tentativa recusada por falta de papel não mede bloqueio de rede.
Use somente documentos e perguntas sintéticos.

## Etapa 1: conferir o caminho local

1. Execute os testes de autorização, chat e operação.
2. Confira a ordem das chamadas nos dublês.
3. Confira o texto e os identificadores enviados ao gerador, além da resposta apresentada.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_acesso.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_chat.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_operacao_l300.py
```

| Caso | Evidência local necessária |
| --- | --- |
| Principal sem papel reconhecido | Recusa antes de embeddings, busca e geração |
| Perfil Corretor | Filtro contém somente as classes permitidas |
| Perfil Atendimento | Fonte operacional autorizada pode entrar no contexto |
| Ambos os papéis | União das classes sem receber expressão livre da pergunta |
| Fonte com classe ausente ou desconhecida | Conteúdo excluído; nenhuma permissão implícita |
| Duas requisições com perfis distintos | Contextos e evidências não se misturam |
| Resultado de busca incompatível | Erro explícito, sem continuar a geração com fonte proibida |
| Falha de serviço ou formato | Status e código de suporte, sem saída bruta do serviço |

**Resultado esperado:** testes aprovados, com as restrições conferidas antes do gerador.
Os dublês substituem os serviços reais e registram chamadas; sua aprovação fica identificada
como evidência local.
O arquivo de teste usa marcadores sintéticos por classe. Eles são sinais didáticos de conteúdo,
não dados ou credenciais do ambiente.

### Prompt para o Copilot: explicar uma falha sem expor o ambiente

Anexe este guia e os arquivos de teste relacionados:

```text
Explique quais controles os testes L300 demonstram e quais exigem prova Azure.
Confira a ordem autenticação, autorização, busca, geração e política.
Relacione cada recusa ao mecanismo testado e identifique ausência de evidência.
Preserve os conjuntos finais L100/L200 e os resultados históricos.
Não execute Azure, altere papéis ou peça pergunta real, token, ID pessoal ou log bruto.
```

## Etapa 2: preparar as provas Azure

Esta etapa foi exercitada na rodada Azure com clientes de aplicação temporários
e uma sonda dentro da rede, não com login interativo de pessoas.
Leituras e consultas usam destinos autorizados. Reindexar e modificar a fonte
**[altera o Azure]** e requer aprovação própria.
Os helpers privados da rodada não estão disponíveis como uma ferramenta pública de coleta.
Sem executor e roteiro de sondas revisados, mantenha as provas como pendentes, conforme o
[limite de reprodução do Desafio 04](04-dependencias-privadas.md#etapa-3-aprovar-conexões-e-produzir-evidências).

1. Confira login e papel efetivo com sessões dos perfis do exercício.
2. Execute consulta autorizada dentro da rede e confira a origem das evidências.
3. Confira ausência da fonte operacional com perfil Corretor.
4. Execute ingestão incremental e confira seus erros, avisos e estado final.
5. Compare resolução de nomes e leitura de dados dentro e fora da rede.
6. Repita consulta e ingestão depois do isolamento público.

O indexador precisa de conexões compartilhadas aprovadas e execução privada [3].
Para a negativa externa, registre a origem e o mecanismo da recusa: DNS, conexão, acesso público
ou autorização de dados. Mantenha o resultado como pendente se não for possível identificar
qual controle impediu a operação.

Uma resposta exibida sem conteúdo restrito exige também conferir a seleção das fontes.
Evite registrar tokens, claims de pessoas, perguntas ou trechos recuperados em logs públicos.

Organize as evidências no formato aceito por `operar_l300.py`:

| Campo do descritor, versão 1 | Observação a registrar |
| --- | --- |
| `origem` | `operador` para registro manual de observações; `simulado` para dublês |
| `dns_privado` | Resolução dos serviços pelo caminho autorizado |
| `spl_busca` | Estados dos shared private links, conexões privadas compartilhadas da busca |
| `aplicacao` | Prontidão, revisão ativa e consulta respondida |
| `ingestao` | Índice L300, execução privada, resultado, itens e falhas |
| `acesso_privado` | Operações positivas por dependência e negativas após o isolamento |

Preencha um arquivo JSON, formato JavaScript Object Notation de dados estruturados.
Este modelo começa com campos pendentes e deve ser recusado pelo validador:

```json
{
  "versao": 1,
  "origem": "operador",
  "dns_privado": {"armazenamento": null, "busca": null, "modelos": null},
  "spl_busca": {"armazenamento": "pendente", "modelos": "pendente"},
  "aplicacao": {"prontidao_http": null, "revisao_ativa": null, "consulta_respondida": null},
  "ingestao": {
    "indice": "vareleira-lar-l300",
    "ambiente_de_execucao": "private",
    "ultima_execucao": null,
    "itens_processados": null,
    "itens_com_falha": null
  },
  "acesso_privado": {
    "armazenamento": {"positiva": null, "negativa": null},
    "busca": {"positiva": null, "negativa": null},
    "modelos": {"positiva": null, "negativa": null}
  }
}
```

Registre `true` apenas para observação atendida, `false` para falha e `null` para item pendente.
Nas conexões compartilhadas, use `aprovado`, `pendente`, `rejeitado` ou `ausente`.
Na ingestão, registre o resultado real, como `success`, e as contagens observadas.
Mude `origem` para `simulado` ao exercitar o formato com dublês; campos declarados não
substituem as observações correspondentes.
Os comandos abaixo só leem o arquivo privado indicado por `$descritor`:

```powershell
.\.venv\Scripts\python.exe scripts\operar_l300.py --etapa conferir --descritor $descritor --momento antes-de-isolar
.\.venv\Scripts\python.exe scripts\operar_l300.py --etapa conferir --descritor $descritor --momento depois-de-isolar
```

Execute o segundo após registrar também as negativas externas. A integração local exercitou
esse caminho com descritores sintéticos. A rodada Azure posteriormente conferiu dois descritores
baseados em observações reais, com proveniência privada: antes e depois do isolamento.
O [registro Azure](../../docs/validacao/l300-azure-validacao.md) discrimina as fontes e os limites.

## Etapa 3: revisar registros e classificação das falhas

1. Use o código de suporte para localizar o evento do servidor.
2. Confira rota, status, duração e causa curta.
3. Mantenha a análise de configuração em local privado.
4. Publique somente resultado, quantidade, origem da prova e pendência.

| Falha | Diagnóstico delimitado |
| --- | --- |
| Autenticação | Borda, sessão e tenant |
| Papel documental | Claim reconhecida e classificação da fonte |
| Busca | Campo filtrável, filtro, identidade de dados e caminho de rede |
| Embeddings ou geração | Deployment, cota, identidade e caminho de rede |
| Descarte pela política | Formato, referência selecionada e contrato da resposta |
| Ingestão | Fonte, metadados, projeção, conexão compartilhada e execução do indexador |

O servidor conserva o vocabulário fechado das rotas e causas. Logs HTTP adicionais da plataforma
podem incluir endereço de rede ou query string; confira seu conteúdo e retenção antes de habilitar
ou publicar esse material [2]. A query string é a parte da URL (*Uniform Resource Locator*,
endereço de um recurso) que carrega parâmetros.

O helper resume um arquivo privado exportado dos logs, sem consultar Log Analytics:

```powershell
.\.venv\Scripts\python.exe scripts\operar_l300.py --etapa resumir-logs --logs $arquivoLogs --relatorio $novoResumo
```

Escolha um relatório novo. O resumo contém contagens de status, rotas, causas e duração.
Uma linha desconhecida interrompe a aprovação do resumo com erro de divergência, sem copiar
seu conteúdo. Taxas e percentis de um exemplo sintético não são medições de desempenho Azure.
A rodada também resumiu um recorte real de logs do chat. Sondas de saúde foram separadas
das consultas; a amostra pequena não constitui teste de carga ou objetivo de nível de serviço.

## Etapa 4: registrar a decisão de continuidade

1. Identifique revisão, data e configuração conferidas.
2. Separe testes locais, leituras Azure, operações de dados e alterações de infraestrutura.
3. Registre casos aprovados, falhas, não executados e dependências para encerrá-los.
4. Autorize a fase seguinte somente com as evidências exigidas por ela.

Um campo indicando conectividade validada é uma declaração usada pela guarda de execução.
As medições de consulta, ingestão e rede devem estar disponíveis para sustentá-lo.
Se faltar uma delas, conserve o acesso público na fase de preparação e mantenha o isolamento pendente.

## Como pedir uma mudança ao Copilot no VS Code

Peça diagnóstico antes de edição. Delimite a causa e os testes que precisam falhar antes da correção.
Revise o diff em **Source Control**, confira que a mudança preserva a política L100 e execute
os testes relacionados. Uma correção de acesso não deve aceitar fontes desconhecidas,
repetir a consulta sem filtro ou usar uma identidade mais privilegiada como substituição.

## Conferência do resultado

| Tipo de evidência | Alcance |
| --- | --- |
| Build e lint Bicep | Sintaxe, tipos e definição de infraestrutura |
| Testes com dublês | Decisões, ordem das chamadas e tratamento de erros |
| Probes | Processo e prontidão conforme o contrato implementado |
| Consulta Azure autenticada | Acesso efetivo às fontes e serviços por uma identidade |
| Indexador privado | Atualização real da base pelo caminho da ingestão |
| Negativa externa | Controle identificado para uma origem e operação específicas |
| Avaliação de respostas | Qualidade sobre conjunto e configuração próprios, separada das provas de acesso |

## Solução de problemas

| Sintoma | Ação |
| --- | --- |
| Probes aprovam, perguntas falham | Confira busca e modelos por operação autenticada |
| `403` sem causa identificada | Separe autorização documental, dados e rede antes de propor alteração |
| Conteúdo restrito aparece no contexto | Interrompa uso e corrija filtro e validação da recuperação |
| Índice não acompanha a fonte | Confira estado do indexador, metadados e detecção de exclusão |
| Log contém pergunta ou claim pessoal | Suspenda sua publicação e reveja coleta, acesso e retenção |
| Teste foi repetido após observar falhas | Preserve ambas as rodadas e seus motivos; não substitua o resultado histórico |

## Custos, pausa e limpeza

As consultas reais usam busca e modelos. A ingestão pode recalcular embeddings dos documentos
alterados; logs têm custo de ingestão e retenção [2]. Registre período e serviços medidos, sem
supor cobrança total imediata.

Encerre servidores locais próprios depois das verificações e retire sessões ou acessos temporários
conforme a autorização. A próxima etapa trata a recuperação e a remoção dos objetos L300.

## Situação da validação

A integração local registra decisões de acesso, descritores e sanitização com dublês.
A rodada Azure conferiu papéis nos tokens de clientes temporários, borda EasyAuth, conexão
privada, ingestão e recusas externas. Logs reais do chat foram resumidos sem linhas desconhecidas
ou publicação de conteúdo e credenciais. Os resultados L200 ficam preservados, sem nova rodada
para ajustar esta implementação. Login humano, Actions e teste de carga não foram executados.
O [registro local L300](../../docs/validacao/l300-validacao-local.md) e o
[registro Azure](../../docs/validacao/l300-azure-validacao.md) distinguem formatos sintéticos,
operações reais e limites da medição.

## Glossário

| Termo | Significado |
| --- | --- |
| HTTP | Protocolo usado pela interface web |
| Probe | Verificação de saúde ou prontidão |
| Telemetria | Medidas e eventos da operação |
| Dublê | Substituto controlado de um serviço durante um teste |
| Código de suporte | Identificador que relaciona pedido e evento do servidor |
| Query string | Parâmetros presentes na URL |
| Evidência | Registro de uma observação, com escopo e origem definidos |
| Tenant e claim | Diretório de identidades e informação emitida no token |
| Deployment e DNS | Instância nomeada do modelo e resolução de nomes |

## Referências

1. [Probes em Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/health-probes).
2. [Logs e Log Analytics em Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/log-monitoring).
3. [Conexões privadas de saída da busca](https://learn.microsoft.com/en-us/azure/search/search-indexer-howto-access-private).

Texto por GPT-6.1 Sol; código e testes por Claude Sonnet 5.5, com Astra indisponível.
O modelo de autoria não seleciona os modelos do Copilot do aluno ou da aplicação.

Revisão documental: gpt-6-astra (Astra), em 11 de outubro de 2026, por leitura integral e
conferência local dos artefatos; sem nova execução Azure.
