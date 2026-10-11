# L200, Desafio 05: registro de validação

Registro do [guia de hospedagem](../../desafios/L200/05-hospedar-chat.md), executado em 10 de outubro
de 2026 no destino autorizado. IDs, nomes privados, segredo e tokens ficaram fora do repositório.

## Imagem e implantação

| Verificação | Resultado |
| --- | --- |
| Docker local | Indisponível; construção feita remotamente no ACR |
| Contexto de construção | Lista de permissão do `.dockerignore`; dados, Git, ambiente virtual e segredos excluídos |
| Primeira execução remota | `Succeeded`, imagem e digest confirmados |
| Build integrado posterior | `--no-logs` executado com tag própria; `Succeeded` e digest conferidos, sem o erro de streaming |
| Falha do terminal | Streaming de logs falhou por codificação `cp1252`; não foi interpretado como falha do build remoto |
| Registro | Administrador por senha desabilitado; download pela identidade gerenciada com `AcrPull` |
| Aplicação | Usuário de contêiner sem privilégios, 0,5 vCPU, 1 GiB, escala de zero a uma réplica |
| Ordem de abertura | Aplicação criada com ingresso interno; autenticação conferida antes de habilitar ingresso externo |
| Configuração | Índice L200, híbrida, `k=3`, `low`, embeddings de 1.536 dimensões |

O segredo de login não foi colocado na imagem ou nas variáveis do contêiner; o EasyAuth o lê
de Container Apps Secrets. Não foi criado novo Key Vault.

## Autenticação e consultas

| Verificação | Resultado |
| --- | --- |
| Registro de login | Single-tenant, callback correto, emissão de ID token habilitada |
| Atribuição a pessoas específicas | Não exigida; público autenticado do tenant, sem lista própria de pessoas |
| Provedor da plataforma | Habilitado, issuer do tenant e audiências esperadas conferidos |
| Ação anônima | `Return401`, HTTPS exigido |
| `/healthz` e `/readyz` anônimos | HTTP 200; não exercitam modelos |
| `/` e `/api/perguntar` anônimos | HTTP 401 |
| Cabeçalho artificial de principal | HTTP 401 na borda, apesar de construído para o tenant |
| Início de `/.auth/login/aad` | HTTP 302 para Entra ID; sem completar autenticação humana |
| Token real de identidade temporária | Chegou à API protegida |
| Primeira pergunta de fumaça | HTTP 503, causa `resposta_descartada`, preservada |
| Pergunta geral posterior | HTTP 200, `documentada`/`respondida`, três evidências, não simulada |
| Pergunta individual posterior | HTTP 503 por descarte, sem enfraquecer a conferência |
| Pergunta fora de escopo | HTTP 200, `fora_de_escopo`/`recusada`, nenhuma evidência |

O token veio da identidade temporária do registro de login. Essa execução não representou login
interativo de uma pessoa. A identidade de login não recebeu papéis Azure; a aplicação consultou os
serviços com sua identidade gerenciada.

## Privilégio mínimo exercitado na réplica

| Operação usando `ManagedIdentityCredential` da aplicação | Resultado |
| --- | --- |
| Consulta de índice e modelos pelo chat | Funcionou nas respostas não simuladas |
| Leitura de blob do laboratório | HTTP 403 |
| Listagem administrativa de índices | HTTP 403 |
| Leitura administrativa da conta de armazenamento pelo ARM | HTTP 403 |

Essas três recusas vieram de sondas de leitura executadas na réplica, não de tokens do operador.
Problemas locais de aspas do wrapper Windows e uma conexão de execução remota foram superados com
comandos curtos na réplica ativa, sem ampliar papéis ou alterar autenticação.

## Limites e continuidade

O Desafio 06 registra a rodada final com conjunto próprio e configuração congelada.
As perguntas de fumaça não foram usadas para retunar política ou parâmetros.
Um `503` protege a apresentação, mas também impede que a pessoa receba uma resposta;
ele é contado como falha de atendimento na avaliação de contrato.

Autorização por documento, restrição por pessoa, login humano, testes de carga de produção,
outras regiões e retenção de conversas não foram validados.
A aprovação humana do material original L100 não foi estendida automaticamente a esse desenho.

## Correções antes da avaliação final

Uma revisão de integração em contexto separado encontrou divergência entre o Bicep e o chat:
`quantidadeTrechos` aceitava até 20 na infraestrutura, mas o validador Python aceitava até 10.
Os dois módulos Bicep foram alinhados ao intervalo de 1 a 10, preservando o padrão 3.
Um teste compila a fronteira 10 e rejeita 11 com BCP327 antes de qualquer implantação.
O teste também verifica as guardas do módulo da aplicação.

O coordenador demonstrou outra divergência antes de enviar o conjunto final: IDs de projeção
com mais de 128 caracteres eram truncados pela apresentação. Dois trechos de um mesmo documento
podiam aparecer com o mesmo ID, impedindo localizar a chave inteira. A correção preserva IDs válidos
de até 1.024 caracteres, limite do Azure AI Search. A imagem final precisa incorporar essa correção
antes da medição; nenhum caso final foi usado para descobri-la ou corrigir a política.

A correção foi incorporada ao build `cq3`, cuja revisão ficou pronta em modo `Single`.
Saúde/prontidão `200` e acesso anônimo `401` foram conferidos antes da avaliação.
A resposta inicial do plano de controle antecedeu a prontidão; a conferência aguardou o recurso
existente, sem repetir a implantação.

A [rodada final](l200-06-avaliar-chat.md) teve 11 de 18 casos conformes e cinco descartes HTTP 503.
Transporte e autenticação funcionaram, mas esse resultado não homologa a qualidade completa do chat.
