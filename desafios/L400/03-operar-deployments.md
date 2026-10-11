# L400 · Desafio 03: operar deployments com contingência

[Início](../../README.md) · [Desafio 02](02-coordenar-especialistas.md) · [Desafio 04](04-evoluir-indice.md)

| Campo | Definição |
| --- | --- |
| Situação | Contingência e recusas exercitadas; modelos e limites conferidos |
| Público | Operações, arquitetura e desenvolvimento |
| Resultado | Exercitar falhas transitórias e contingência dentro dos limites |
| Custo | Testes locais não chamam modelos; tentativas e contingência reais consomem tokens |

## Conteúdo

- [Cenário](#cenário)
- [Objetivos](#objetivos)
- [Artefatos e disponibilidade](#artefatos-e-disponibilidade)
- [Tecnologias e conceitos](#tecnologias-e-conceitos)
- [Pré-requisitos](#pré-requisitos)
- [Etapa 1: distinguir modelo e deployment](#etapa-1-distinguir-modelo-e-deployment)
- [Etapa 2: classificar falhas](#etapa-2-classificar-falhas)
- [Etapa 3: conferir orçamento e retorno](#etapa-3-conferir-orçamento-e-retorno)
- [Como pedir uma mudança ao Copilot no VS Code](#como-pedir-uma-mudança-ao-copilot-no-vs-code)
- [Conferência do resultado](#conferência-do-resultado)
- [Solução de problemas](#solução-de-problemas)
- [Custos, pausa e limpeza](#custos-pausa-e-limpeza)
- [Situação da validação](#situação-da-validação)
- [Glossário e referências](#glossário-e-referências)

## Cenário

A equipe do piloto fictício precisa que uma indisponibilidade temporária seja identificada,
sem transformar um erro de permissão em uma tentativa com identidade mais poderosa.
Teresa Moura exige que a contingência conserve modelo, fontes, política e autorização.

## Objetivos

1. Conferir versão, capacidade e endereço dos deployments autorizados.
2. Separar falhas transitórias de configuração, acesso e política.
3. Limitar tentativas e contabilizar chamadas que falham.
4. Testar retorno sem alegar disponibilidade de produção.

## Artefatos e disponibilidade

| Artefato | Uso |
| --- | --- |
| [Deployment de geração L100](../../infra/modules/geracao.bicep) | Modelo, versão e capacidade explícitos |
| [Topologia L300](../../infra/l300.bicep) | Caminho privado anterior |
| [Roteiro L400](../../docs/roteiro-l400.md) | Primário, contingência e limites |
| [Tratamento do chat](../../scripts/lab_chat.py) | Códigos públicos sem texto interno |

O [Bicep L400](../../infra/l400.bicep), os [parâmetros](../../infra/levels/l400.bicepparam)
e o [helper de operação](../../scripts/operar_l400.py) estão disponíveis.
O primário e o standby foram implantados no recurso próprio com o mesmo modelo e versão.
Standby é o deployment de contingência, não um serviço de outra região.

## Tecnologias e conceitos

Um **deployment** é uma instância nomeada de modelo. O nome `geracao` não é o nome
`gpt-5.4-mini`. O exercício usa primário e contingência do mesmo modelo e versão para reduzir
variáveis; isso não garante resposta idêntica.

**Cota** limita a capacidade disponível. Dois deployments podem compartilhar a mesma cota
regional. Eles não criam automaticamente capacidade adicional nem disponibilidade independente [1].

**Retry**, nova tentativa, precisa consumir o orçamento da requisição. Um **circuit breaker**,
interrupção temporária de um destino após falhas, pode evitar repetição imediata. Ele não concede
papéis nem transforma uma resposta sem fontes em sucesso.

## Pré-requisitos

Use assinatura ativa, destinos explícitos e autorização dos recursos. Confira os modelos no
catálogo e a cota na região; não substitua uma versão ausente silenciosamente.

Os testes locais dispensam Azure. A criação de deployment **[altera o Azure]** e exige plano,
capacidade e custo aprovados. O L400 não reabre automaticamente dados públicos.

## Etapa 1: distinguir modelo e deployment

Registre em local privado nome, modelo, versão, capacidade, região e identidade.
Conserve a referência e use um nome diferente para a contingência.

| Instância | Modelo e finalidade |
| --- | --- |
| Primário de geração | Respostas estruturadas na configuração de referência |
| Contingência de geração | Mesmo contrato e autorização, quando uma falha transitória permite troca |
| Embeddings | Vetores compatíveis com o índice; não participa da troca de geração |

Não copie IDs ou endpoints reais para prompts, arquivos públicos ou logs.

O Bicep usa duas fases: `contingencia` cria somente a instância adicional no recurso existente;
`aplicacao` cria o chat L400 no ambiente privado, separado da referência. A criação de dados,
rede e identidade anterior não é repetida silenciosamente.

Confira o plano local, sem alterar serviços:

```powershell
.\.venv\Scripts\python.exe scripts\operar_l400.py --etapa planejar --passo contingencia --validar-bicep
```

Os nomes, o modelo, a versão e a capacidade entram pelos parâmetros privados do operador.
Na fase de aplicação, o segredo de login fica somente na sessão e em parâmetro seguro.
Não imprima `build-params --stdout` com valores reais.
O plano local não implanta essas fases. A receita completa dos helpers privados da rodada
não está entregue neste repositório: a reprodução exige um roteiro de implantação revisado,
com parâmetros, simulação, autorização e conferências próprios. A existência do Bicep não
torna as operações históricas reproduzíveis por um único comando deste guia.

## Etapa 2: classificar falhas

| Falha | Tratamento a conferir |
| --- | --- |
| 429, limite de capacidade | Tentativa ou contingência somente se orçamento e prazo permitirem |
| 5xx ou falha transitória de rede | Tratamento limitado e causa explícita |
| 401 ou 403 | Interromper; conferir identidade e permissão, sem contingência para contornar acesso |
| 404 | Interromper; conferir deployment e destino |
| Saída inválida ou referência inventada | Recusar; não repetir para buscar uma resposta que pareça aprovada |

Uma falha injetada no transporte de teste é diferente de uma interrupção real do serviço Azure.
Registre a origem de cada falha para não anunciar disponibilidade comprovada por um dublê.

## Etapa 3: conferir orçamento e retorno

1. Configure limites finitos antes da execução.
2. Confira se tentativas do SDK (*Software Development Kit*, biblioteca do serviço) também são contadas.
3. Simule falha antes de uma chamada e depois de um pedido já enviado.
4. Confira uso conhecido, uso incerto e tempo restante.
5. Retorne ao primário somente pelas condições definidas.

Tokens de raciocínio podem fazer parte dos tokens de saída. Não some a mesma parcela duas vezes.
Uso indisponível não representa consumo zero. Tarifas informadas produzem estimativa, não fatura.
Confira o tratamento implementado com dublês, sem provocar falhas em serviços reais:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_orquestracao.py
```

**Resultado esperado:** os testes de tentativas e contingência passam. Isso confere decisões
do código; não mede disponibilidade do deployment ou capacidade regional.

## Como pedir uma mudança ao Copilot no VS Code

```text
Anexo o roteiro L400, a configuração de limites e o tratamento de erros.
Siga uma falha 503 e uma falha 403 até a decisão de contingência.
Inclua as tentativas na contagem e preserve identidade, fontes e política.
Não amplie papéis, altere modelos ou provisione recursos.
```

Revise o diff e execute os testes que distinguem falha transitória e acesso negado.

## Conferência do resultado

Registre tentativas, destino lógico, duração, causa e uso de tokens, sem URL ou credencial.
Uma resposta final deve continuar passando pela política e pelas referências da requisição.

## Solução de problemas

| Sintoma | Ação |
| --- | --- |
| Ambos os deployments recebem 429 | Confira cota compartilhada e concorrência, sem prometer capacidade extra |
| 403 aciona contingência | Corrija a classificação; acesso negado deve interromper |
| Número de chamadas parece menor que o real | Confira retries internos e tentativas que falharam |
| Uso ausente aparece como zero | Preserve a incerteza e a reserva de orçamento |

## Custos, pausa e limpeza

Uma chamada que falha depois de ser enviada pode ter custo. Limite quantidade e duração.
Mantenha a contingência somente durante a janela necessária e retire seus recursos próprios
no encerramento autorizado. Não remova o deployment anterior de outro proprietário.

## Situação da validação

Catálogo, modelos e cotas foram conferidos; a guarda real do módulo recusou declaração
de versão incompatível. Uma falha 503 injetada no transporte da sonda acionou a contingência
e concluiu com fonte documentada; uma falha 403 parou após uma tentativa, sem troca.
Não houve interrupção regional real nem comprovação de cota adicional.
O [registro L400](../../docs/validacao/l400-validacao.md) preserva uso incerto e origem das falhas.

## Glossário e referências

| Termo | Significado |
| --- | --- |
| Deployment | Instância nomeada de um modelo |
| Cota | Limite de capacidade disponível |
| SDK | Biblioteca usada para chamar um serviço |
| Retry | Nova tentativa após falha |
| Circuit breaker | Suspensão temporária de um destino após falhas |

1. [Gestão de cotas dos modelos](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/quota).
2. [Autenticação por identidade gerenciada em Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/managed-identity).
3. [Princípios de novas tentativas](https://learn.microsoft.com/en-us/azure/architecture/patterns/retry).

Texto por GPT-6.1 Sol; código por Claude Sonnet 5.5. Autoria, Copilot e modelos Azure são distintos.

Revisão documental por gpt-6-astra (Astra), em 11 de outubro de 2026, sem nova execução Azure.
