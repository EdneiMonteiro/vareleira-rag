# L300 — Desafio 06: conferir acesso, conectividade e registros de operação

[Início do laboratório](../../README.md) · [Desafio 05](05-automatizar-entrega.md) · [Desafio 07](07-recuperar-limpar.md)

| Item | Descrição |
| --- | --- |
| Situação | Histórico preservado; logs do Job e consulta interna exercitados em 11 de outubro de 2026; sem nova medição do descritor L300 ou dos helpers externos; provas pós-isolamento não executadas |
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
- [Autoria](#autoria)

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
| [Sonda interna](../../scripts/sonda_l300.py) | Resolução de nomes, ingestão, acesso, interface interna e negativas de privilégio, uma etapa por execução manual |
| [Montador da imagem](../../scripts/montar_contexto_sonda_l300.py) e [modelos de construção](../../infra/sonda-l300) | Contexto offline; preparação do executor no [Desafio 04](04-dependencias-privadas.md#etapa-3-aprovar-conexões-e-produzir-evidências) |
| [Sonda externa do chat](../../scripts/sonda_http_externa_l300.py) | Borda sem credenciais ou uma pergunta por perfil; segredo somente em variável de ambiente |
| [Negativas externas](../../scripts/sonda_negativas_externas_l300.py) | Plano offline a partir de exportações; tentativas reais somente com `--executar` |
| [Testes HTTP](../../tests/test_sonda_http_externa_l300.py) e [de negativas externas](../../tests/test_sonda_negativas_externas_l300.py) | Dublês, classificação da causa, recusa e proteção de saída |
| [Avaliador web L200](../../scripts/avaliar_chat.py) | Contrato de avaliação preservado, separado da prova de acesso |
| [Testes](../../tests) | Dublês dos serviços e casos negativos de aplicação |

Rotas de saúde continuam com o contrato do L200 e não executam uma pergunta no modelo.
O helper `conferir` lê um descritor preenchido pelo operador; ele avalia completude e coerência,
sem obter as medições do Azure.
As ferramentas públicas derivam dos helpers privados validados no Azure na rodada histórica.
As versões públicas têm testes locais com dublês. A receita de coleta do Desafio 04 incorpora
achados da rodada de validação de 11 de outubro de 2026; continue separando uma observação real de uma declaração no descritor.

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
As faixas de **IPv4**, versão 4 do protocolo de internet, de uso privado são definidas na
**RFC 1918**, especificação da série *Request for Comments* usada na conferência da sonda.
**JSON**, formato JavaScript Object Notation, representa os dados estruturados dos resultados
e do descritor. Uma **URL**, *Uniform Resource Locator*, é o endereço de um recurso.

As sondas deste roteiro são ferramentas de conferência, distintas das probes de saúde da plataforma.
A sonda interna roda num **Container Apps Job**, tarefa finita no ambiente integrado à rede [4].
**RBAC**, controle de acesso baseado em papéis, define operações Azure por identidade e escopo [6].
Papéis RBAC de dados não substituem papéis documentais do chat.
**API**, interface de programação de aplicações, é a rota que o helper HTTP chama.
**HTTPS** protege a conexão web; as sondas HTTP aceitam somente o endereço oficial
`*.azurecontainerapps.io`, não domínio personalizado.

## Pré-requisitos

Conclua a classificação documental, o filtro, a topologia e o plano de automação.
Abra o projeto no Visual Studio Code (VS Code), selecione `.venv` e use PowerShell 7.
A parte local dispensa credenciais.

Para uma prova Azure, confirme assinatura ativa, identidades por perfil, destino e caminho de rede
autorizados. As identidades de teste devem ter os papéis necessários à operação negativa:
uma tentativa recusada por falta de papel não mede bloqueio de rede.
Use somente documentos e perguntas sintéticos.
Autorize também as leituras de configuração, as tentativas externas e seu consumo.
Criar cliente de teste, segredo ou atribuição de papel depende de autorização explícita
dos administradores do tenant e da assinatura; este guia não cria esses objetos.
Abra os guias na prévia Markdown, mantenha destinos e exportações em local privado e confira
`$LASTEXITCODE` logo após cada comando. Permissão de login, administração e acesso de dados
são conferências distintas.

Para os comandos `az containerapp`, use a CLI de 64 bits e a pasta própria de extensões,
conforme a [nota de instalação do Desafio 04](04-dependencias-privadas.md#3-criar-um-job-manual-no-ambiente-l300).
Não confunda instalar a extensão localmente com autorizar uma operação na nuvem.

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

Prepare o Job, a imagem e as identidades pelo
[roteiro público do Desafio 04](04-dependencias-privadas.md#etapa-3-aprovar-conexões-e-produzir-evidências).
A rodada histórica usou clientes de aplicação temporários e helpers privados dentro e fora
da rede; não foi login interativo de pessoas. A disponibilidade dos novos arquivos permite
preparar a reprodução, mas não demonstra execução Azure de suas versões públicas.

1. Colete positivas dentro da rede com a identidade prevista, antes de isolar.
2. Leia manualmente conexões compartilhadas e revisão ativa.
3. Confira a borda e os perfis HTTP por ferramentas próprias, sem mudar permissões para fazer
   uma tentativa passar.
4. Depois do isolamento autorizado, atualize as exportações, repita as positivas e execute
   as negativas externas.
5. Construa descritores distintos antes/depois, vinculando cada campo às observações privadas.

Reindexar e modificar a fonte **[altera o Azure]** e requer aprovação própria, como no Desafio 02.
Iniciar o Job cria uma execução Azure, mesmo quando sua etapa só lê dados.
O indexador precisa de conexões compartilhadas aprovadas e execução privada [3].
Uma resposta sem conteúdo restrito exige também conferir a seleção das fontes:
o helper HTTP observa a apresentação; a etapa `acesso` e os testes do servidor examinam
filtro e conteúdo enviado ao modelo. Evite tokens, claims de pessoas, perguntas e trechos
recuperados em registros públicos.

### 1. Mapear cada campo do descritor, versão 1

Nas tabelas, `dados` é o objeto da linha `L300_SONDA_RESULTADO=` da execução correspondente,
não a configuração declarada no Job. A sonda interna e a HTTP externa emitem **uma única linha**;
a ferramenta de negativas externas imprime orientação e deixa essa linha **por último**.
Leia veredicto e código na linha efetivamente emitida; exija versão `v=1`, etapa certa e
veredicto compatível. O código de saída do processo coincide com o da linha emitida:
`saida_bloqueada` ou `saida_invalida` resulta em saída `4`. Código zero de simulação não é prova.
Um Job `Succeeded` sem linha válida ou com causa `saida_bloqueada` não aprova a etapa.
O [passo de leitura do Desafio 04](04-dependencias-privadas.md#5-ler-conclusão-e-resultado-separadamente)
separa estado do Job e resultado da sonda.

| Campo do descritor | Ferramenta/etapa | O que ler para preencher | Coleta manual ou limite |
| --- | --- | --- | --- |
| `origem` | Operador; sem etapa de coleta | `operador` somente para observações Azure reais; `simulado` para dublês | Registre data, revisão, execução, origem de rede e identidade em proveniência privada; o rótulo não comprova esses fatos |
| `dns_privado.armazenamento` | Sonda interna, `dns` | `dados.dns.blob.todos_rfc1918` | A chave da sonda é `blob`, a do descritor é `armazenamento` |
| `dns_privado.busca` | Sonda interna, `dns` | `dados.dns.busca.todos_rfc1918` | Resolução precisa ocorrer dentro da rede autorizada |
| `dns_privado.modelos` | Sonda interna, `dns` | `dados.dns.modelos.todos_rfc1918` | RFC 1918 define faixas de endereços privados; isso não substitui uma chamada aos modelos |
| `spl_busca.armazenamento` | Leitura ARM das conexões da busca | Destino próprio, `Approved` **e** provisionamento `Succeeded` → `aprovado` | **Nenhuma etapa da sonda coleta esse campo**; use as leituras de conexões abaixo |
| `spl_busca.modelos` | Mesma leitura, para o recurso de modelos | Mesmos estados, no destino de modelos correto | Sem identificar destino ou provisionamento, mantenha `pendente` |
| `aplicacao.prontidao_http` | `http-interno` ou HTTP externa `sem-credenciais` | Número em `dados.estados.readyz`, normalmente `200` | Grave o status inteiro observado, não `true`; a prontidão isolada não mede modelos, mas `http-interno` também inclui uma pergunta com consumo |
| `aplicacao.revisao_ativa` | Leitura da aplicação, `az containerapp revision list` | Revisão da imagem conferida ativa e operacional | **Nenhuma etapa da sonda coleta esse campo**; confira também o tráfego e a associação à aplicação |
| `aplicacao.consulta_respondida` | `http-interno` Atendimento, ou HTTP externa `perfil` Atendimento/ambos | HTTP `200` e `dados.resposta.tipo=documentada`, `situacao=respondida`, `operacional=true`, com etapa aprovada | Em `http-interno`, HTTP está em `dados.estados.autenticado`; na externa, em `dados.http`. Essa consulta consome embeddings e uma geração; exige as provas separadas do caminho privado |
| `ingestao.indice` | Sonda interna, `conferir` | Conferência aprovada dos `objetos` e `definicoes` em `dados.aprovadas`, com índice disponível e trechos conferidos | Só então registre `vareleira-lar-l300`, alvo fixo da ferramenta; copiar o nome do parâmetro não demonstra existência |
| `ingestao.ambiente_de_execucao` | Sonda interna, `conferir` | `ambiente_privado` consta em `dados.aprovadas` → `private` | `executar` e `resumo` sozinhos não informam esse atributo; ele é lido da definição do indexador |
| `ingestao.ultima_execucao` | Sonda interna, `resumo` ou `executar` | `dados.indexador.resultado`, como `success` | `conferir` valida o estado, mas não emite esse resultado literal; recolha o resumo para os valores exatos |
| `ingestao.itens_processados` | Mesmas etapas | `dados.indexador.processados` | São itens da ingestão, não `dados.indice.trechos`; preserve zero quando observado |
| `ingestao.itens_com_falha` | Mesmas etapas | `dados.indexador.falhas`; confira também `erros` e `avisos` | Campo ausente continua pendente; não suponha zero a partir de um `Succeeded` do Job |
| `acesso_privado.armazenamento.positiva` | `carregar`; ciclo `excluir`/`restaurar` quando autorizado | Etapa aprovada, `cli_codigo=0`, contagens e `orfaos=0` na carga | **[altera o Azure]**: carga e ciclo operacional; seleção da identidade de manutenção e DNS precisam estar conferidos |
| `acesso_privado.busca.positiva` | `resumo`, `conferir` ou `acesso` | Índice `disponivel=true` e contagens/classes lidas; ou chamadas reais de busca e filtros conferidos em `acesso` | Em `executar`/`conferir`, o resumo complementar pode falhar sem mudar o veredicto principal; leia `dados.indice` |
| `acesso_privado.modelos.positiva` | Sonda interna, `acesso` | `dados.chamadas.embeddings` positivo; geração, se habilitada, em `dados.geracao.executada` e seus invariantes | `GERACAO=nao` não prova geração; no máximo uma geração nessa etapa, com custo de tokens |
| `acesso_privado.armazenamento.negativa` | Negativas externas, serviço `blob` | `dados.resultados`: `recusa_esperada` → `true`; `permitida` → `false`; `pendente` → `null` | Só após isolar, fora da rede, com identidade e papel de dados do operador conferidos |
| `acesso_privado.busca.negativa` | Negativas externas, serviço `busca` | Mesmo mapeamento do resultado do serviço | Recusa precisa identificar acesso público desabilitado, não falta de papel |
| `acesso_privado.modelos.negativa` | Negativas externas, serviço `modelos` | Mesmo mapeamento do resultado do serviço | Uma resposta permitida pode consumir tokens de embeddings |

`negativas-mi` fica no registro complementar, **fora do descritor versão 1**.
Ela faz três leituras que a identidade do **chat** não pode realizar: Blob original L100,
administração de índices e conta de armazenamento no ARM, serviço de administração Azure.
Os três status devem ser `403`, com identidade conferida, **de dentro de uma rede funcional**.
Falha de DNS ou conexão não demonstra falta de papel. Isso é diferente da negativa externa
de isolamento, que usa a identidade do **operador**, com papéis de dados.

**Dica:** um “aprovado” responde apenas à pergunta daquela etapa. `resumo` pode aprovar a
consistência das classes e informar `inProgress` ou zero itens; isso não completa a ingestão
exigida pelo descritor. `conferir` e `executar` também podem trazer
`dados.indice.disponivel=false` num complemento de diagnóstico. Preserve a pendência desse campo.

As conexões e a revisão ativa usam leituras, sem aprovação ou troca de tráfego:

```powershell
az search shared-private-link-resource list --subscription $assinatura --resource-group $grupo --service-name $busca --output json
az search shared-private-link-resource show --subscription $assinatura --resource-group $grupo --service-name $busca --name $nomeLink --output json
az containerapp revision list --subscription $assinatura --resource-group $grupo --name $aplicacao --output json
```

Recupere as variáveis do inventário aprovado. `$nomeLink` identifica uma conexão própria
obtida na listagem; confira cada destino. Compare os estados lidos, pois a CLI e o ARM podem
organizar os campos de modo diferente. Registro de login, página de login pública e variável
de conectividade não demonstram revisão ativa nem conectividade privada [4][5].

**Resultado esperado:** cada campo tem uma fonte identificada; coleta manual e fatos ainda
ausentes permanecem explícitos.
**Autorização, custo e limpeza:** as leituras exigem permissão no alvo; não criam concessões.
Sondas, ingestão, modelos e logs têm custos distintos. `http-interno`, assim como `acesso`,
inclui consumo de tokens: no perfil autorizado, sua pergunta usa embeddings e uma geração.
Conserve a proveniência privada pelo prazo aprovado, com seus consumidores; retire temporários
pelo Desafio 07.

### 2. Conferir HTTP de fora da rede

**Objetivo:** medir a borda do chat e uma pergunta por perfil, sem confundir esses acessos com
papéis RBAC dos serviços.

1. Confira que `$urlChat` é a URL HTTPS oficial e alcançável do computador que coordena.
   Com ingresso interno ou caminho fechado, o helper externo só funciona de uma origem que
   alcance essa URL. Não abra ingresso nem altere autenticação para contornar a falha.
   Nesse caso, use o nome completo de domínio (FQDN, *Fully Qualified Domain Name*) lido do
   ingresso no ARM, com `.internal.`, conforme o
   [passo HTTP do Desafio 04](04-dependencias-privadas.md#4-iniciar-uma-etapa-por-execução).
   Não reconstrua o host como `<app>.<domínio>`.
2. Comece pelos testes locais com dublês. **Este helper não tem simulação nem opção `--executar`:**
   uma etapa configurada faz requisições. A simulação seguida de `--executar` pertence ao helper
   de negativas dos três serviços, no próximo passo.
3. Após autorizar as leituras HTTP, execute a etapa sem credenciais:

```powershell
$env:VARELEIRA_HTTP_URL = $urlChat
Remove-Item Env:\VARELEIRA_HTTP_ETAPA -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe scripts\sonda_http_externa_l300.py --etapa sem-credenciais
$codigoHttp = $LASTEXITCODE
```

Ela exige só URL; o tenant é opcional nessa etapa. Leia a única linha de resultado, etapa
`http-externo-sem-credenciais`: `healthz=200`, `readyz=200`, `anonimo=401` e
`principal_forjado=401` em `dados.estados`, com veredicto aprovado e código `0`.
Uma rota de saúde que responde não prova consulta aos modelos.
As duas tentativas contra a API enviam uma pergunta que a borda deve recusar com `401`.
Se ela aceitar os pedidos sem identidade, o chat pode consumir embeddings e geração; o helper
reprova a etapa. “Sem credenciais” não significa consumo impossível diante de uma falha do controle.

4. Para `perfil`, o administrador fornece um cliente de aplicação de teste **já autorizado**,
   com credencial temporária e papel correspondente. Cliente de teste (`$idClienteTeste`) e
   registro de login do chat (`$idLogin`) são objetos distintos. Criar cliente, segredo ou
   atribuição de papel **[altera o Entra ID]**, exige autorização do administrador do tenant e
   não é executado por este guia. Reutilizar um objeto também exige aprovação de seu proprietário.
5. Configure os valores privados e leia o segredo sem colocá-lo no histórico:

```powershell
$env:VARELEIRA_HTTP_URL = $urlChat
$env:VARELEIRA_HTTP_TENANT_ID = $tenant
$env:VARELEIRA_HTTP_CLIENT_ID = $idClienteTeste
$env:VARELEIRA_HTTP_LOGIN_APP_ID = $idLogin
$env:VARELEIRA_HTTP_PERFIL = "atendimento"
$segredoCliente = Read-Host -AsSecureString "Segredo temporário do cliente de teste autorizado"
try {
    $env:VARELEIRA_HTTP_CLIENT_SECRET = [System.Net.NetworkCredential]::new("", $segredoCliente).Password
    .\.venv\Scripts\python.exe scripts\sonda_http_externa_l300.py --etapa perfil
    $codigoHttp = $LASTEXITCODE
}
finally {
    Remove-Item Env:\VARELEIRA_HTTP_CLIENT_SECRET -ErrorAction SilentlyContinue
    Remove-Variable segredoCliente -ErrorAction SilentlyContinue
}
```

O segredo vai **somente pela variável de ambiente**, em memória; nunca por argumento, arquivo,
prompt ou saída. Não habilite depuração nem copie o ambiente do processo.
O helper usa `ClientSecretCredential`, credencial de cliente da biblioteca Azure Identity, e
obtém token para o escopo `api://<loginAppId>/.default`, destinado ao registro de login [7].
É uma única pergunta sintética de operação por execução, não uma repetição dos conjuntos finais.

| Perfil informado e papel real do cliente | Resultado esperado da etapa `http-externo-perfil` |
| --- | --- |
| `atendimento` | HTTP 200; resposta `documentada`, `respondida` e operacional |
| `corretor` | HTTP 200; documento e marcador operacional ausentes; preservar o tipo de resposta observado |
| `ambos` | HTTP 200; resposta documentada e operacional |
| `sem-acesso` | HTTP 403; nenhuma permissão documental |

Use o cliente autorizado para cada perfil. Trocar só `VARELEIRA_HTTP_PERFIL` não muda seus
papéis; o helper compara papéis reconhecidos no token e o resultado esperado.
O perfil Corretor não deve trazer o roteiro operacional, mas o guia não força uma classificação
específica de recusa nem ajusta a pergunta para obter outra resposta.
Depois de cada prova, o administrador revoga a credencial temporária conforme o plano autorizado.
Apagar a variável local não revoga a credencial no Entra ID.

**Resultado esperado:** uma linha por execução com status e invariantes, sem segredo, token,
URL ou texto da resposta. Falha e divergência são registradas sem repetição para escolher resultado.
**Autorização, custo e limpeza:** a etapa sem credenciais faz quatro requisições e pode consumir
tokens se os pedidos com pergunta forem aceitos indevidamente; `perfil` faz uma pergunta e pode
consumir embeddings e geração. As chamadas não gravam dados.
Retire variáveis, credenciais e clientes somente conforme seu inventário e autorização;
preserve os objetos anteriores e a configuração do provedor de login.

### 3. Preparar e executar as negativas externas dos serviços

**Objetivo:** conferir a recusa do caminho público com uma identidade que **teria permissão de
dados**, evitando atribuir a isolamento uma falha de autenticação ou autorização.
A ferramenta roda no computador de quem coordena, **fora da rede privada**, com a sessão
Azure CLI do operador; não usa a identidade de manutenção nem a do chat.
Confirme a origem, inclusive se existe VPN, rede privada virtual, que levaria a tentativa pelo
caminho interno.

#### Exportar pré-condições por leitura

Depois da fase `isolar`, recupere do inventário os IDs completos `$idConta`, `$idBusca` e
`$idModelos`, e o ID de objeto `$idObjetoOperador`. Confira que pertencem ao destino aprovado.
Escolha `$arquivoConta`, `$arquivoBusca`, `$arquivoModelos`, `$arquivoPapeis` e
`$novoRelatorioNegativas` como **arquivos novos em pasta privada**, fora do repositório.
Não publique exportações: elas contêm identificadores do ambiente.

As três exportações de serviços podem ser objetos ou listas JSON, formato JavaScript Object
Notation de dados estruturados. Precisam conservar `id`, `name`, `type` e
`properties.publicNetworkAccess`. Os tipos são `Microsoft.Storage/storageAccounts`,
`Microsoft.Search/searchServices` e `Microsoft.CognitiveServices/accounts`; os três devem
ter `publicNetworkAccess=Disabled`. Não edite esse valor para fazer a simulação passar.
As leituras dos três serviços usam `az resource show` [9]. As consultas a seguir **só leem
o Azure**; a gravação é local:

```powershell
foreach ($arquivo in @($arquivoConta, $arquivoBusca, $arquivoModelos, $arquivoPapeis, $novoRelatorioNegativas)) {
    if (Test-Path -LiteralPath $arquivo) { throw "Escolha arquivos novos; preserve as exportações anteriores." }
}
$exportacao = az resource show --ids $idConta --output json
if ($LASTEXITCODE -ne 0) { throw "A conta não foi conferida." }
$exportacao | Set-Content -LiteralPath $arquivoConta -Encoding utf8 -ErrorAction Stop
$exportacao = az resource show --ids $idBusca --output json
if ($LASTEXITCODE -ne 0) { throw "A busca não foi conferida." }
$exportacao | Set-Content -LiteralPath $arquivoBusca -Encoding utf8 -ErrorAction Stop
$exportacao = az resource show --ids $idModelos --output json
if ($LASTEXITCODE -ne 0) { throw "Os modelos não foram conferidos." }
$exportacao | Set-Content -LiteralPath $arquivoModelos -Encoding utf8 -ErrorAction Stop
$exportacao = az role assignment list --subscription $assinatura --assignee-object-id $idObjetoOperador --all --fill-principal-name false --fill-role-definition-name true --output json
if ($LASTEXITCODE -ne 0) { throw "Os papéis diretos do operador não foram conferidos." }
$exportacao | Set-Content -LiteralPath $arquivoPapeis -Encoding utf8 -ErrorAction Stop
```

Use os arquivos recém-exportados da mesma configuração, não capturas antigas.
`--all` inclui atribuições abaixo da assinatura; `--assignee-object-id` seleciona diretamente
o operador, e `--fill-principal-name false` evita consulta para preencher nomes no Microsoft Graph,
interface de administração das identidades. Conserve `roleDefinitionName` [6][8].
Não use `--include-groups`: o helper precisa de atribuições **diretas** ao operador.
Cada registro conserva `principalId`, `roleDefinitionName` e `scope`.

| Alvo da tentativa | Papel de dados aceito, no alvo ou ancestral que o contenha |
| --- | --- |
| Contêiner `base-documental-l300` | `Storage Blob Data Reader`, `Storage Blob Data Contributor` ou `Storage Blob Data Owner` |
| Índice `vareleira-lar-l300` | `Search Index Data Reader` ou `Search Index Data Contributor` |
| Recurso de modelos | `Cognitive Services OpenAI User` ou `Cognitive Services OpenAI Contributor` |

O papel do contêiner não é comparado somente com a conta: o helper monta o alvo **do contêiner
L300**. Um escopo ancestral compatível pode servir à leitura, mas isso não é motivo para conceder
papéis amplos. Papéis herdados de grupo, atribuições condicionais, escopo de grupo de gerenciamento
e papéis personalizados **não contam** nessa pré-condição. Se o acesso autorizado depende deles,
essa ferramenta não comprova a pré-condição: registre a limitação e mantenha a prova pendente,
sem criar uma concessão direta por conveniência.

#### Simular antes de enviar

Primeiro, sem `--executar`:

```powershell
.\.venv\Scripts\python.exe scripts\sonda_negativas_externas_l300.py `
    --tenant-id $tenant --conta $conta --busca $busca --modelos $modelos `
    --operador-id $idObjetoOperador `
    --servicos $arquivoConta $arquivoBusca $arquivoModelos --papeis $arquivoPapeis
$codigoPlano = $LASTEXITCODE
if ($codigoPlano -ne 0) { throw "O plano não foi aprovado; nenhuma tentativa externa deve continuar." }
```

Essa chamada não usa rede nem token: confere nomes, exportações, escopos e pré-condições.
Leia o plano e a **última linha**, etapa `negativas-externas`.
Uma simulação válida termina com código `0`, `veredicto=simulado`,
`dados.modo=simulado`, `dados.rede=nao_usada` e nenhum resultado HTTP.
Serviço ainda público ou papel não comprovado gera pendência, sem tentativa.
Nada disso preenche os campos de negativa do descritor.

Após conferir o plano e autorizar as três tentativas, use os mesmos destinos e exportações:

```powershell
.\.venv\Scripts\python.exe scripts\sonda_negativas_externas_l300.py `
    --tenant-id $tenant --conta $conta --busca $busca --modelos $modelos `
    --operador-id $idObjetoOperador `
    --servicos $arquivoConta $arquivoBusca $arquivoModelos --papeis $arquivoPapeis `
    --relatorio $novoRelatorioNegativas --executar
$codigoNegativa = $LASTEXITCODE
```

O relatório é novo, não sobrescreve arquivo existente e conserva o mesmo resultado da linha
efetivamente emitida, inclusive se a barreira o trocar por `saida_bloqueada` e saída `4`.
A ferramenta usa `AzureCliCredential`,
credencial da sessão Azure CLI, e confere em memória se o token pertence ao operador informado.
Faz **uma tentativa por serviço**: listar no máximo um blob do contêiner L300, contar documentos
do índice L300 e pedir um embedding de texto sintético fixo.
Essas operações não alteram dados, mas o pedido aos modelos pode consumir tokens se a recusa falhar.
As opções `--container`, `--indice` e `--deployment` existem; nesta receita, conserve os padrões
`base-documental-l300`, `vareleira-lar-l300` e `embeddings`.

#### Qualificar origem e mecanismo

Leia `dados.modo=executado`, `dados.identidade=confere` e cada item de `dados.resultados`:
`dependencia`, `http`, `codigo_servico`, `causa`, `evidencia` e `resultado`.
Registre origem externa real, identidade usada, alvos, data e arquivos de pré-condição na
proveniência privada. O rótulo `fora_da_rede` do helper não detecta se o computador está conectado
por VPN: essa origem precisa da conferência de quem opera.

| Observação | O que demonstra | Resultado e campo de negativa |
| --- | --- | --- |
| HTTP 403, causa `acesso_publico_desabilitado`, pré-condições e identidade conferidas | Recusa do caminho público para aquela origem e operação | `recusa_esperada` → `true`; as três recusas esperadas aprovam a rodada |
| HTTP 2xx, operação aceita | A negativa daquele serviço falhou | `permitida` → `false`; rodada reprovada |
| `autorizacao_de_dados` | Identidade sem a ação de dados necessária | `pendente` → `null`; mecanismo identificado, mas não é o controle de rede procurado |
| `autenticacao` | Token ou autenticação não concluiu | `pendente` → `null`; não demonstra isolamento |
| `dns` ou `conexao` | Não houve resposta HTTP para a tentativa | `pendente` → `null`; a falha pode estar na rede do próprio operador |
| `nao_identificada` | O status não foi relacionado ao mecanismo esperado | `pendente` → `null`; um 403 sozinho não aprova |

**Atenção:** identificar uma causa é necessário, mas não suficiente: **só HTTP 403 atribuído a
`acesso_publico_desabilitado` aprova a negativa**. DNS, conexão, autenticação e autorização de dados
são causas conhecidas, porém não aprovam esse controle. Se nenhum serviço responder, o código é `2`;
recusas por outro mecanismo ou acesso permitido resultam em código `3`. Código `1` indica entradas
inválidas e `4`, defeito. Leia o veredicto e os resultados por serviço, não apenas o código.

No Blob, `AuthorizationFailure` é genérico. O helper o qualifica combinando `Disabled`, papel
de dados no alvo e identidade do token conferidos; mantenha também a prova positiva dentro da rede.
Busca e modelos reconhecem marcadores de acesso público desabilitado na mensagem do serviço,
lida somente em memória. A mensagem bruta não é publicada nem gravada.
Esta prova mostra recusa **a partir da rede de quem executa**, não bloqueio de toda origem possível,
nem indisponibilidade total do serviço.

**Para guardar na memória:** “não consegui entrar” é um sintoma; “o controle do acesso público
recusou esta operação, com esta identidade e desta origem” é a prova delimitada.

**Resultado esperado:** três resultados reais com mecanismo qualificado, e nenhuma negativa
inventada a partir de plano ou erro de conexão.
**Autorização, custo e limpeza:** autorize exportações e tentativas; o plano é offline.
As três chamadas têm consumo de serviços e o embedding pode ter tokens. Apague exportações e
relatórios privados quando seu prazo terminar; remova somente acessos temporários realmente
criados, pelo [Desafio 07](07-recuperar-limpar.md), sem revogar papéis anteriores do operador.

### 4. Construir o descritor a partir das observações

Preencha um arquivo JSON privado, indicado por `$descritor`; o operador escolhe seu caminho
e não o versiona. Mantenha uma proveniência separada com revisão, data, origem, identidade,
etapa/execução, arquivo e observação que sustentam **cada campo**. Não acrescente esses detalhes
como campos novos ao descritor: seu formato é fechado.
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
Mude `origem` para `simulado` ao exercitar o formato com dublês. O modelo declara nome de índice
e ambiente privado para mostrar o formato; esses dois valores também precisam das leituras
da tabela antes de compor uma prova de origem `operador`.
Uma linha inexistente, um estado desconhecido ou um complemento indisponível continua pendente.
Preserve zero itens processados em uma repetição sem mudanças: o validador exige pelo menos um
item processado, e não aceita transformar esse zero em uma contagem anterior.
Se for necessária nova prova de ingestão, autorize o ciclo operacional do Desafio 02 e registre
ambas as execuções. Não confunda itens processados com número de trechos.
`origem=operador`, `ambiente_de_execucao=private` e campos `true` são declarações;
as observações vinculadas são as medições.
Os comandos abaixo só leem o arquivo privado indicado por `$descritor`:

```powershell
.\.venv\Scripts\python.exe scripts\operar_l300.py --etapa conferir --descritor $descritor --momento antes-de-isolar
.\.venv\Scripts\python.exe scripts\operar_l300.py --etapa conferir --descritor $descritor --momento depois-de-isolar
```

Execute o segundo após registrar também as negativas externas. A integração local exercitou
esse caminho com descritores sintéticos. A rodada histórica L300 posteriormente conferiu dois descritores
baseados em observações reais, com proveniência privada: antes e depois do isolamento.
O [registro Azure](../../docs/validacao/l300-azure-validacao.md) discrimina as fontes e os limites.
Um descritor completo significa que seus campos são completos e coerentes, **não que o helper
mediu o Azure**. Responsável e evidências reais sustentam a decisão de habilitar a guarda.
Os resultados históricos não são preenchimentos automáticos para uma nova execução.

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
Esse resumidor reconhece **logs do chat**, não linhas `L300_SONDA_RESULTADO=`.
Mantenha as sentinelas das sondas em sua proveniência separada; misturá-las ao arquivo do chat
produz linha desconhecida e impede aprovação. Para os logs do Job, use a
[consulta de Log Analytics do Desafio 04](04-dependencias-privadas.md#5-ler-conclusão-e-resultado-separadamente),
com a janela e a execução conferidas. A consulta usa a interface HTTP, não uma extensão
de leitura de logs do Job, e deve ter intervalo e prazo limitados.

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

Para revisar o preenchimento, anexe este guia, o Desafio 04, `operar_l300.py` e as três sondas
públicas, sem anexar exportações reais:

```text
Revise por leitura o mapeamento das sondas para o descritor L300 versão 1.
Confira chaves, tipos, etapa, perfil, origem da prova e o que ainda é coleta manual.
Separe simulação, consulta real, recusa de papel e recusa de acesso público.
Explique por que DNS ou conexão sem HTTP deixam a negativa pendente.
Não preencha como medida um campo só declarado e não use resultados históricos na nova rodada.
Não execute Azure ou HTTP, edite arquivos, crie cliente, credencial ou papel.
Não peça segredo, token, ID de pessoa, pergunta final, exportação ou log bruto.
```

Revise o diff em **Source Control** antes de aceitar edição; confira contratos no código
e execute somente os testes locais relacionados. Não use o terminal do Copilot como autorização
para enviar uma pergunta ou iniciar um Job.

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

**Resultado esperado:** cada valor do descritor remete à observação do momento correto.
Negativas externas exigem execução real, identidade conferida, resposta e mecanismo esperado;
negativas da identidade do chat ficam separadas. Estado `Succeeded`, prontidão HTTP e
descritor completo têm alcances distintos.

## Solução de problemas

| Sintoma | Ação |
| --- | --- |
| Probes aprovam, perguntas falham | Confira busca e modelos por operação autenticada |
| `403` sem causa identificada | Separe autorização documental, dados e rede antes de propor alteração |
| Conteúdo restrito aparece no contexto | Interrompa uso e corrija filtro e validação da recuperação |
| Índice não acompanha a fonte | Confira estado do indexador, metadados e detecção de exclusão |
| Log contém pergunta ou claim pessoal | Suspenda sua publicação e reveja coleta, acesso e retenção |
| Teste foi repetido após observar falhas | Preserve ambas as rodadas e seus motivos; não substitua o resultado histórico |
| Plano das negativas sai com código 0 | Confira `veredicto=simulado` e `rede=nao_usada`; nenhuma negativa foi medida |
| Exportação não comprova papel de dados | Confira principal direto, nome do papel, condição e escopo do contêiner/índice; não amplie acesso por tentativa |
| Papel só vem por grupo ou é personalizado | Pré-condição fora do alcance do helper; registre a limitação sem criar concessão por conveniência |
| Negativa falha em DNS ou conexão | Origem do operador pode ser o problema; não registre isolamento aprovado e não reabra o serviço automaticamente |
| Token pertence a outra identidade | Nenhuma tentativa deve continuar; confira sessão, tenant e principal privado antes de nova autorização |
| HTTP externo não alcança ingresso interno | Use o caminho autorizado ou a sonda interna; abrir ingresso exige decisão própria |
| `token_indisponivel` no perfil HTTP | Confira tipo e código curto Entra emitidos; não exponha segredo nem mensagem bruta |
| `resumo` aprovado, mas ingestão incompleta | Leia resultado, processados, falhas, erros e avisos; aprovação de classes não substitui sucesso da ingestão |
| Linha da sonda bloqueada ou ausente | Preserve erro/pendência; confira coleta e colisão de nome, sem desligar proteção ou fabricar resultado |

## Custos, pausa e limpeza

As consultas reais usam busca e modelos. A ingestão pode recalcular embeddings dos documentos
alterados; logs têm custo de ingestão e retenção [2]. Registre período e serviços medidos, sem
supor cobrança total imediata.

Encerre servidores locais próprios depois das verificações e retire sessões ou acessos temporários
conforme a autorização. A próxima etapa trata a recuperação e a remoção dos objetos L300.
Remover a variável do segredo não revoga a credencial do cliente; essa revogação é administrativa.
Uma negativa aos modelos que falha pode consumir embeddings. Execuções do Job e coleta de logs
são cobradas separadamente; conserve apenas os temporários necessários e siga o
[Desafio 07](07-recuperar-limpar.md) para removê-los com alvo e consumidor conferidos.

## Situação da validação

A integração local registra decisões de acesso, descritores e sanitização com dublês.
A rodada histórica L300 conferiu papéis nos tokens de clientes temporários, borda EasyAuth, conexão
privada, ingestão e recusas externas. Logs reais do chat foram resumidos sem linhas desconhecidas
ou publicação de conteúdo e credenciais. Os resultados L200 ficam preservados, sem nova rodada
para ajustar esta implementação. Login humano, Actions e teste de carga não foram executados.
O [registro local L300](../../docs/validacao/l300-validacao-local.md) e o
[registro Azure](../../docs/validacao/l300-azure-validacao.md) distinguem formatos sintéticos,
operações reais e limites da medição.

**Revisão local anterior:** contratos e classificação das ferramentas públicas foram
conferidos com dublês e ajuda offline. As 21 execuções históricas continuam separadas.

**Rodada de validação de 11 de outubro de 2026:** os resultados e o console do Job foram
lidos pela API HTTP de Log Analytics. A tabela `ContainerAppConsoleLogs_CL` forneceu
`TimeGenerated`, `Log_s`, `ContainerJobName_s` e `ContainerGroupName_s`;
a ingestão levou de segundos a poucos minutos. Isso encerra a pendência do caminho de
leitura usado nesta rodada, não a validação de qualquer extensão de logs.

A etapa `http-interno` L300 observou 200 em saúde, prontidão e consulta autenticada,
com resposta documentada e marcador operacional. Anônimo e principal forjado receberam 401.
A sonda também executou o ciclo operacional: excluir um blob → reindexar para 21 trechos
e ausência da fonte operacional → conferir dez verificações → restaurar um blob →
reindexar para 24 trechos → conferir nove verificações. Esses resultados vieram do Job,
não de um descritor preenchido pelo operador.

**Sem nova medição documentada:** o conferidor do descritor L300 e o helper HTTP externo.
As negativas externas e as provas pós-isolamento não foram executadas. A fase `isolar` não foi aplicada;
os serviços de dados continuaram com acesso público habilitado. Portanto, a consulta
privada observada não comprova operação com esse acesso fechado.
Login humano, ingresso externo, implantação por GitHub Actions/OpenID Connect (OIDC, protocolo de identidade),
federação, matriz Linux local e nova avaliação semântica continuam não executados.

O custo efetivo segue indisponível; a estimativa do coordenador é de poucos dólares,
sem comprovar a fatura ou o teto estimado de US$ 30 da rodada inteira.
Os resultados e a limpeza aprovada estão no
[registro da rodada de 11 de outubro de 2026](../../docs/validacao/operacao-publica-azure-validacao-2026-10-11.md).

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
| Job e sentinela | Tarefa finita de Container Apps e linha identificável de resultado da sonda |
| RBAC e escopo | Controle por papéis Azure e limite dos recursos cobertos por uma atribuição |
| API e HTTPS | Interface entre programas e protocolo web com proteção da conexão |
| JSON | Formato JavaScript Object Notation para dados estruturados |
| ARM e Microsoft Graph | Administração dos recursos Azure e interface de administração das identidades |
| IPv4 e RFC 1918 | Versão 4 do protocolo IP e especificação das faixas destinadas a redes privadas |
| VPN | Rede privada virtual; pode mudar a origem efetiva de uma tentativa |
| Pré-condição | Fato que precisa estar comprovado antes de enviar a tentativa |
| Proveniência | Associação privada entre observação, momento, execução, identidade e campo do descritor |
| `ClientSecretCredential` e `AzureCliCredential` | Credenciais do cliente de teste e da sessão do operador, respectivamente |

## Referências

1. [Probes em Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/health-probes).
2. [Logs e Log Analytics em Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/log-monitoring).
3. [Conexões privadas de saída da busca](https://learn.microsoft.com/en-us/azure/search/search-indexer-howto-access-private).
4. [Jobs, execuções e limites de configuração](https://learn.microsoft.com/en-us/azure/container-apps/jobs).
5. [Gerenciar e conferir revisões](https://learn.microsoft.com/en-us/azure/container-apps/revisions-manage).
6. [Papéis, principais e escopos Azure](https://learn.microsoft.com/en-us/azure/role-based-access-control/role-assignments-cli).
7. [Fluxo de credenciais de cliente e escopo `.default`](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-client-creds-grant-flow).
8. [Referência CLI das atribuições de papel](https://learn.microsoft.com/en-us/cli/azure/role/assignment).
9. [Referência CLI de leitura de recursos](https://learn.microsoft.com/en-us/cli/azure/resource#az-resource-show).

## Autoria

Texto por GPT-6.1 Sol; código e testes por Claude Sonnet 5.5, com Astra indisponível.
O modelo de autoria não seleciona os modelos do Copilot do aluno ou da aplicação.

Revisão documental: gpt-6-astra (Astra), em 11 de outubro de 2026, por leitura integral e
conferência local dos artefatos; sem nova execução Azure.

Receita das sondas: GPT-6.1 Sol, com Astra indisponível, em 11 de outubro de 2026; ferramentas
públicas por Claude Sonnet 5.5; comandos verificados por ajuda offline; sem execução Azure.

Atualização pós-validação Azure de 11 de outubro de 2026: redigida por GPT-6.1 Sol com base nos fatos do coordenador; defeitos de código corrigidos com Sonnet 5.5; revisão do coordenador.
