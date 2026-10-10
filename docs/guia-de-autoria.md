# Padrão de autoria dos desafios

Os desafios incrementais do Vareleira RAG seguem este padrão. Os guias
[01](../desafios/L100/01-preparar-ambiente.md),
[02](../desafios/L100/02-indexar-documentos.md),
[03](../desafios/L100/03-responder-com-fontes.md),
[04](../desafios/L100/04-recusar-sem-evidencia.md),
[05](../desafios/L100/05-agente-com-maf.md),
[06](../desafios/L100/06-avaliar-respostas.md) e
[07](../desafios/L100/07-identidade-da-aplicacao.md) compõem o L100.
A situação de execução, as revisões e as pendências de cada guia ficam em seu registro de validação.
O material existente do L100 recebeu a aprovação do mantenedor em 9 de outubro de 2026.
Novos conteúdos e alterações continuam sujeitos à revisão correspondente.

## Público e linguagem

Escreva em português do Brasil para pessoas de negócio, arquitetura, operações
e desenvolvimento. Não suponha familiaridade com terminal, programação, Git,
identidade Azure ou infraestrutura como código.

Explique o necessário no ponto de uso e inclua glossário ao final de cada
desafio. Uma definição no glossário não substitui a explicação da primeira
ocorrência. Use nomes oficiais de comandos e indique o sistema operacional.

O material pode ser leve e acessível, com exemplos, analogias e mnemônicos
originais. Não reproduza texto, ilustrações, diagramação ou identidade de séries
editoriais. Não infantilize o leitor nem substitua precisão por humor.

## Estrutura de cada desafio

| Parte (título da seção) | Conteúdo obrigatório |
| --- | --- |
| Capa e Conteúdo | Nível, número, título, sumário e tabela de situação (situação, público, resultado e custo), com a distinção entre rascunho e exercício executável |
| Cenário | Situação concreta da Vareleira, responsáveis e problema a resolver |
| Objetivos | Resultado observável e o que fica fora do desafio |
| Artefatos e disponibilidade | Links para Bicep, documentos, scripts e demais arquivos realmente disponíveis, com o estado de cada um |
| Tecnologias e conceitos | Papel de cada serviço e limites, não apenas uma lista de nomes |
| Pré-requisitos | Ferramentas, contas, assinatura, permissões, dependências anteriores e custos |
| Etapas | Objetivo de cada etapa, ação em passos numerados, resultado esperado e forma de conferir |
| Prompt para o Copilot (dentro das etapas) e Como pedir uma mudança ao Copilot no VS Code | Como abrir o projeto, fornecer contexto, pedir ajuda, revisar alterações e verificar resultados |
| Conferência do resultado | Verificações que só leem, com a evidência esperada de cada uma |
| Solução de problemas | Sintomas, diagnóstico delimitado e recuperação sem contornar controles |
| Custos, pausa e limpeza | Custo, recursos reaproveitados, pausa, limpeza com alvo explícito e próxima dependência |
| Situação da validação | Resumo conciso do que foi conferido e do que está pendente, com responsável ou ação para encerrar |
| Glossário e Referências | Termos utilizados e referências oficiais que sustentem as instruções |

Artefatos pendentes são identificados como caminhos propostos, sem links
inválidos ou comandos que aparentem funcionar. Declare o escopo validado e as etapas pendentes;
uma validação parcial precisa indicar o que foi executado e a condição para concluir o restante.

## Chamadas didáticas

Use chamadas quando ajudarem a executar ou compreender uma etapa:

- **Dica:** atalho ou pergunta útil que não dispense revisão.
- **Lembre-se:** conceito essencial para interpretar a tarefa.
- **Atenção:** risco concreto, consequência e ação para evitá-lo.
- **Boa prática:** recomendação com mecanismo e limite explicados.
- **Para guardar na memória:** analogia ou mnemônico claramente identificado
  como recurso do curso, não como padrão técnico.

Não use chamadas decorativas em todos os parágrafos. O texto principal deve
continuar compreensível sem depender de cores ou ícones.

## Ensinar o uso do Copilot é parte do curso

Todo desafio deve incluir pelo menos um pedido pronto para colar no chat,
adaptado àquela tarefa. Diferencie explicação, planejamento, edição e execução.
Não presuma que anexar um arquivo autoriza acesso ao Azure ou alterações.

O prompt deve indicar objetivo, arquivos de contexto, restrições e forma de
verificação. Ao pedir implementação, delimite arquivos, dependências,
tratamento de erros e testes. Ao pedir diagnóstico, comece por leitura e
não exponha credenciais ou dados pessoais.

Ensine a abrir a pasta completa, usar a prévia Markdown e o terminal, selecionar
o interpretador quando aplicável e revisar o diff. Explique que instalar a
extensão Python não instala o interpretador. Não gere configurações do VS Code
que não sejam necessárias ao desafio.

O aluno pode escolher modelos disponíveis em sua conta. Não torne os modelos
usados pelos autores um pré-requisito para acompanhar o curso. Uso do Copilot
e consumo dos modelos Azure são serviços e cobranças diferentes.

## Continuidade técnica e narrativa

Preserve o contexto Vareleira 0.1.0, o piloto interno de 2025 e o assessment
histórico de agosto de 2026. Novas regras de seguro são conteúdo sintético novo,
não fatos já aprovados pelo projeto original.

Reutilize recursos entre desafios sempre que tecnicamente viável. Declare
adições, mudanças, migrações, custo e recuperação. Uma configuração de nível
anterior não é um procedimento automático de downgrade ou limpeza.

Mantenha dados de teste e respostas esperadas fora do conteúdo recuperável.
Não introduza contradições documentais involuntárias, acesso anônimo ou
credenciais fixas para simplificar exercícios.

## Desafios que alteram o Azure

Marque cada etapa que cria, troca ou remove recursos com **[altera o Azure]** e
separe-as das etapas que só leem. Todo desafio executável deve:

- receber assinatura, grupo de recursos e nomes por parâmetro ou variável, sem
  fixar identificadores do ambiente de quem escreve;
- oferecer simulação ou `what-if` antes de alterar e mostrar o plano ao aluno;
- tornar a repetição previsível: não duplicar, não sobrescrever em silêncio e
  parar diante de divergências;
- usar identidade do Microsoft Entra ID, sem chaves de conta, e papéis no menor
  escopo possível;
- incluir uma verificação que só lê, com evidência objetiva do resultado,
  inclusive do que deve ser negado;
- descrever custo, permissões necessárias, limpeza com alvo explícito e como
  continuar nos próximos desafios;
- ter testes automáticos, sem Azure, para a lógica de decisão: inventário,
  hashes, plano e tradução de erros;
- terminar com a situação da validação: data, ambiente, versões, o que passou e
  o que está pendente, com responsável ou ação para encerrar. A matriz completa
  e as correções feitas durante a validação ficam em `docs/validacao`, fora do
  guia do aluno.

Os comandos publicados devem ter sido executados em ambiente autorizado.
Comandos não exercitados precisam ser declarados como tais.

## Revisão antes da publicação

Confira links e artefatos, coerência entre comando e saída esperada, explicação
de termos, adequação ao público e limites de cada verificação.
Teste a sequência executável no ambiente autorizado e registre o que passou,
falhou ou não foi executado. Separe consulta de assinatura, análise local, teste automático e
execução dos recursos no Azure.

Separe evidências privadas do ambiente de conteúdo público. Não publique IDs
do ambiente de teste, credenciais, saídas brutas ou preços sem contexto.
Logs e matrizes de validação ficam em `docs/validacao`, separados do guia do
aluno, e seguem a mesma regra sobre IDs e credenciais.
Quando faltar implementação, publique apenas o rascunho identificado como tal.

## Revisão editorial

Leia o guia inteiro antes de publicar ou alterar. Ao encontrar um problema,
procure a mesma categoria em todo o texto, e não só no trecho apontado.

- **Voz e tempo:** escreva no presente para procedimentos e comportamento geral
  e reserve o futuro para ações previstas e comportamentos posteriores à ação
  descrita. Evite referências a quem escreveu o guia ("no teste do autor").
- **Construção afirmativa:** diga o que fazer e o que acontece. Reserve a
  negação para limites e riscos concretos.
- **Sem metatexto, lemas ou qualificadores sem prova:** cada "seguro", "simples"
  ou "rápido" precisa de fonte, medida ou consequência.
- **Siglas e termos:** defina a sigla na primeira ocorrência e use um único termo
  por conceito, no texto e no glossário.
- **Procedimentos:** numere os passos e indique o resultado observável de cada
  um.
- **Números e afirmações:** cada número, limite ou comportamento tem fonte
  oficial ou medição registrada, e a citação fica na frase que ela sustenta.
- **Ambiente de quem escreve:** retire assinatura, nomes, caminhos, horários e
  tentativas que servem só ao laboratório do autor.
- **Registros internos:** mantenha logs, matrizes e histórico de correções em
  `docs/validacao`; o guia traz só a situação da validação.
- **Títulos e âncoras:** ao renomear um título, atualize sumário, links internos
  e links de outros arquivos, e confira a navegação.
