# L300: autorização documental, automação e dependências privadas

| Item | Definição |
| --- | --- |
| Situação | Implementação e validação Azure concluídas, com limpeza e expurgos conferidos. Actions e federação não ativados |
| Público | Pessoas de Atendimento, operações, arquitetura e desenvolvimento que concluíram o L200 |
| Resultado | Recuperar somente fontes permitidas à identidade autenticada, preparar uma topologia privada e automatizar verificações e implantação com aprovação |
| Continuidade | Reutilizar documentos, modelos, política, imagem e bibliotecas; conservar os índices e a aplicação L200 durante a migração |
| Fora do escopo | Dados reais, novas regras de seguro, decisão individual de cobertura, produção e coordenação de múltiplos agentes do L400 |

## Cenário e limite de aceite

No piloto fictício de 2025, Beatriz Torres precisa que o Atendimento consulte materiais de operação
que não devem aparecer para todo participante. Teresa Moura exige que a alteração de acesso preserve
as regras gerais do produto. A equipe também quer atualizar a base e implantar versões com verificações
reproduzíveis, sem distribuir credenciais de serviços.

O L300 acrescenta classificação de acesso para o exercício. Essa classificação é metadado novo do
laboratório, não uma regra de seguro nem uma política já aprovada da seguradora fictícia.
As três fontes L100 conservam texto, versão e hash; o material operacional novo é explicitamente sintético.
O mantenedor aprovou o roteiro operacional em 10 de outubro de 2026 após sua apresentação.
Texto, versão e hash permanecem intactos. Essa primeira autorização abrangeu somente o conteúdo;
as operações Azure receberam autorização posterior e separada.

Os testes locais verificam que um trecho não autorizado fica fora do contexto enviado ao modelo.
A rodada Azure conferiu papéis emitidos a clientes de aplicação temporários, resolução privada,
ingestão, consultas e recusas fora da rede. Login humano e execução GitHub Actions não foram realizados.
O [registro Azure](validacao/l300-azure-validacao.md) distingue as operações reais dos testes locais.

O L200 teve uma rodada original de 11 de 18 casos conformes e uma rodada posterior de 16 de 18,
sem descartes e com duas divergências de classificação. Esses resultados permanecem preservados.
Acrescentar controles de acesso não transforma o classificador em um componente infalível nem
homologa a aplicação para produção.

## Sete desafios e critérios

| Desafio | Prática | Evidência necessária |
| --- | --- | --- |
| [01. Reproduzir a base](../desafios/L300/01-reproduzir-base.md) | Identificar versão, inventário e configuração; separar recursos reaproveitados de objetos L300 | Plano explícito, testes locais e preservação dos artefatos L100/L200 |
| [02. Atualizar a base classificada](../desafios/L300/02-atualizar-base.md) | Validar manifesto, carregar cópias L300 e manter execução incremental e exclusão reversível | Quatro fontes, 24 trechos e ciclo privado 24 → 21 → 24, sem divergência de classes |
| [03. Filtrar documentos por identidade](../desafios/L300/03-filtrar-acesso.md) | Interpretar papéis de aplicação e filtrar antes da recuperação/geração | Perfis distintos, identidade sem papel recusada e conteúdo restrito ausente do pedido ao modelo |
| [04. Preparar dependências privadas](../desafios/L300/04-dependencias-privadas.md) | Rede, endpoints, DNS e conexões de saída do indexador | Consulta, manutenção e ingestão privadas conferidas; acesso público bloqueado e três negativas externas |
| [05. Automatizar a entrega](../desafios/L300/05-automatizar-entrega.md) | Integração contínua e implantação manual com federação e revisão | Guardas locais; ambiente, confiança e execução Actions pendentes |
| [06. Conferir operação](../desafios/L300/06-conferir-operacao.md) | Evidências declaradas, logs sanitizados e comparação com a base anterior | Falhas explícitas e alcance de cada observação identificado |
| [07. Recuperar e limpar](../desafios/L300/07-recuperar-limpar.md) | Retorno por fase, remoção por alvo e revogação do acesso temporário | Restauração, retorno, remoção granular, recursos ausentes e expurgos conferidos |

Os guias usam os artefatos implementados e separam comandos de referência para o aluno,
operações conferidas no Azure e configuração administrativa ainda não executada.
As provas privadas usaram uma sonda manual dentro da rede, não um runner de Actions.

## Reutilização e migração

| Componente existente | Uso L300 | Mudança necessária |
| --- | --- | --- |
| [Documentos e inventário L100](../dados/l100/inventario.json) | Base comum, sem mudar regras ou bytes normalizados | Cópias em contêiner/prefixo L300 com classe de acesso |
| [Pipeline gerenciado](../scripts/lab_ingestao.py) | Divisão, embeddings, projeção e exclusão | Índice e objetos separados; campo de acesso e execução privada |
| [Chat e política](../scripts/lab_chat.py) | Referências restritas, fontes, aviso e erros | Autorização por requisição antes de enviar trechos ao modelo |
| [Infraestrutura L200](../infra/l200.bicep) | Armazenamento, busca, modelos, registro, identidade e logs | Nova rede e novo ambiente Container Apps; serviço de busca e modelos reaproveitados quando compatíveis |
| [Avaliador HTTP](../scripts/avaliar_chat.py) | Referência de contrato e relatórios sanitizados | Avaliação de papéis e rede é adicional; resultados L200 não serão repetidos para ajustar L300 |

Azure Container Apps define a integração com uma rede virtual na criação do ambiente; o tipo de rede
não pode ser trocado posteriormente [1]. Por isso a migração cria um ambiente L300 e uma aplicação
separados. O L200 continua disponível como retorno até a conferência da nova aplicação.
Depois de isolar os dados, esse retorno precisa também restabelecer um caminho autorizado:
o ambiente L200 sem rede própria pode perder acesso às dependências.

Os recursos da validação L200 foram removidos. Reutilizar significa partir dos arquivos e parâmetros
versionados; não existe um ambiente ativo do instrutor que o aluno deva acessar.
Reutilize o registro de imagens e o processo de construção, com imagem nova da revisão L300.
A imagem anterior não implementa autorização documental. Os Desafios 02 e 03 têm preparação
local; a carga e a ingestão privadas retomam depois da fase `rede` e das aprovações do Desafio 04.

## Autorização antes do contexto do modelo

O Entra ID pode emitir papéis de aplicação no campo `roles` de um token autenticado [2].
O exercício usa os valores `Vareleira.Atendimento` e `Vareleira.Corretor`, definidos especificamente
para este laboratório. Esses papéis identificam o público do documento; não são papéis administrativos
Azure, como *Contributor*.

O servidor transforma papéis reconhecidos em classes permitidas e aplica um filtro na consulta.
O filtro atua na busca textual, vetorial e híbrida, antes de montar o contexto. A classe ausente ou
desconhecida exclui o documento. Uma pessoa sem papel conhecido recebe recusa antes da chamada
ao índice ou aos modelos.

Esse mecanismo é um filtro de segurança administrado pela aplicação, não a propagação automática
de permissões nativas do armazenamento [3]. Toda consulta deve passar por ele. Dar a uma pessoa
acesso direto ao índice pode contornar a fronteira do chat e exige desenho próprio.
O manifesto valida os arquivos da carga; o indexador lê o prefixo inteiro e a autorização do chat
considera classes, não IDs do manifesto. Restrinja a gravação dos blobs e metadados e confira
documentos inesperados antes de liberar tráfego.

O navegador não pode informar o papel, o filtro ou o tenant no JSON da pergunta. O cabeçalho
`X-MS-CLIENT-PRINCIPAL` só é confiável quando a plataforma de autenticação intercepta todo o tráfego;
ele não tem assinatura própria [4]. O sinalizador L300 recusa modo demonstrativo e execução local
sem autenticação. Os testes locais usam dublês dessa borda e são registrados como tais.

## Rede privada inclui a ingestão

O caminho proposto mantém o chat externo, com HTTPS e autenticação. Armazenamento, busca e modelos
passam a ter endpoints privados, conectados à rede da aplicação. O registro de imagens Basic conserva
endereço público autenticado; essa topologia não pretende bloquear toda saída à internet.

Um endpoint privado recebe um endereço na rede. O sistema de nomes de domínio (DNS) precisa resolver
o nome do serviço para esse endereço dentro do caminho autorizado [5]. A aplicação continua usando
os nomes oficiais dos serviços, sem escrever IPs fixos no código.

A conexão privada de entrada da busca não resolve a saída do indexador. A ingestão exige conexões
privadas compartilhadas (*shared private links*) da busca para Blob Storage e embeddings, aprovação
nos recursos de destino e `executionEnvironment=private` no indexador [6].

A camada e a disponibilidade precisam ser conferidas no destino. A documentação atual admite
Basic ou superior para vetorização integrada em regiões de alta capacidade e serviços criados após
3 de abril de 2024; outras habilidades embutidas ou personalizadas têm requisitos diferentes [6].
Não aumente a camada sem verificar a composição do skillset e o custo.

| Fase | Efeito previsto | Condição para seguir |
| --- | --- | --- |
| Rede | Preparar sub-redes, DNS, endpoints e conexões compartilhadas, mantendo o acesso público atual | Aprovar destinos e conferir conexões |
| Aplicação | Criar aplicação L300 com identidade, login e autorização documental | Conferir papéis e fontes permitidas |
| Isolamento | Desabilitar acesso público dos serviços de dados | Demonstrar consulta, ingestão e manutenção no caminho privado, com plano de retorno |

O bloqueio público é a última fase, não uma forma de descobrir se o DNS e a ingestão funcionam.
O computador do aluno e um executor hospedado do GitHub podem ficar sem acesso aos dados depois
do isolamento. Operação e carga precisam de um caminho autorizado na rede.

## Automação com acesso delimitado

A integração contínua (CI) executa testes e compilação sem identidade Azure. Código de pull requests
não deve executar num runner, computador executor, que tenha acesso à rede e aos recursos privados.

A implantação usa acionamento manual e ambiente de implantação protegido. OpenID Connect (OIDC)
permite obter credenciais de curta duração sem guardar um segredo de cliente no GitHub [7].
A relação de confiança, os papéis Azure e as proteções do ambiente são configurações reais,
criadas somente após autorização.

O identificador `sub` do token precisa corresponder à origem exata. Repositórios novos podem usar
um subject imutável com identificadores de proprietário e repositório; não copie automaticamente
um exemplo antigo baseado apenas no nome [7].

Referenciar um ambiente no YAML não cria automaticamente regras de revisão. Um ambiente novo
pode nascer sem proteções; o administrador precisa configurá-las e conferi-las [8].
O arquivo de workflow é uma definição de execução, não evidência de que ela já ocorreu.
Identificadores privados usam secrets individuais do ambiente para evitar exposição no início
dos passos. Isso não os transforma em credenciais: a implantação usa OIDC sem segredo de cliente.
O registro de login do chat é outro objeto e usa somente seu segredo efêmero na fase `aplicacao`.

### Interfaces disponíveis

| Programa | Operações |
| --- | --- |
| [Gerenciador L300](../scripts/gerenciar_ingestao_l300.py) | `validar` local; `carregar`, `excluir`, `restaurar`, `criar`, `executar`, `conferir` e `remover` no destino autorizado |
| [Operação L300](../scripts/operar_l300.py) | Plano e compilação, validação de entradas, resumo de what-if, proteção do ambiente, descritor e resumo de logs; sem rede |
| [Workflow CI](../.github/workflows/validar.yml) | Testes Windows/Linux, compilação e sintaxe JavaScript sem login Azure |
| [Workflow manual](../.github/workflows/l300-implantar.yml) | Entradas, CI, ambiente protegido, OIDC, simulação e aplicação opcional |

O primeiro comando do gerenciador pode ser executado sem identidade Azure. As outras etapas
usam leitura ou alteração externa explicitamente identificada no guia.
O helper de operação não coleta medições da nuvem; ele confere registros fornecidos pelo operador.

## Custos, autorização e situação atual

Endpoints privados, DNS, recursos gerenciados do ambiente integrado, busca, modelos, registro e
logs têm custos próprios. Reutilizar o serviço de busca não elimina cobrança por sua existência.
Confira região, quantidade, duração e orçamento antes de aplicar o plano.

O fechamento começou com arquivos e testes locais. Depois de confirmar assinatura,
`brazilsouth`, grupo exclusivo e teto total de US$90, o mantenedor autorizou executar,
testar e remover e expurgar os temporários ao terminar. A rodada reconstruiu a base,
implantou a topologia privada e conferiu acesso por perfil, isolamento e recuperação.
Os dados usados são sintéticos aprovados. Nenhuma credencial federada ou execução Actions
foi ativada; a autorização desta rodada não se estende a outros destinos.
O grupo exclusivo e o gerenciado foram removidos. Aplicativos temporários e modelos foram
expurgados, os papéis próprios retirados e os oito grupos, oito papéis do operador e 46 recursos
anteriores conferidos. A cobrança ainda não retornou dados para comprovar o gasto efetivo.

Os modelos da aplicação continuam separados do modelo de autoria e do Copilot do aluno.
A aplicação preserva os deployments L200; uma troca exige avaliação própria.
O [registro local L300](validacao/l300-validacao-local.md) conserva o marco anterior:
856 casos, 855 aprovados e um ignorado por permissões POSIX no Windows.
A regressão após a correção do parser encontrada no Azure teve 859 casos,
858 aprovados e o mesmo teste POSIX ignorado.
Os 16 arquivos Bicep foram compilados e conferidos sem avisos com a versão 0.48.1.
Esses resultados são locais. O [registro Azure](validacao/l300-azure-validacao.md)
conserva 21 execuções operacionais aprovadas, resultados HTTP, descritores, falhas e limpeza.
O workflow permanece uma definição não executada no GitHub.

## Referências e autoria

Fontes oficiais conferidas em 10 de outubro de 2026:

1. [Rede em Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/networking).
2. [Papéis de aplicação e claims do Entra ID](https://learn.microsoft.com/en-us/entra/identity-platform/howto-add-app-roles-in-apps).
3. [Filtros de segurança no Azure AI Search](https://learn.microsoft.com/en-us/azure/search/search-security-trimming-for-azure-search).
4. [Autenticação integrada de Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/authentication).
5. [DNS de endpoints privados](https://learn.microsoft.com/en-us/azure/private-link/private-endpoint-dns).
6. [Conexões privadas de saída da busca](https://learn.microsoft.com/en-us/azure/search/search-indexer-howto-access-private).
7. [OIDC do GitHub Actions com Azure](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-azure).
8. [Ambientes e proteções de implantação no GitHub](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments).

Documentação por GPT-6.1 Sol; código e testes por Claude Sonnet 5.5.
Astra indisponível, sem substituição silenciosa e sem Document Swarm.
