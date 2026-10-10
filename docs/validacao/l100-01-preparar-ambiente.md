# L100, Desafio 01: registro de validação

Registro de trabalho da validação do [Desafio 01](../../desafios/L100/01-preparar-ambiente.md): matriz de
testes, medições e correções. O guia do aluno traz a
[situação resumida](../../desafios/L100/01-preparar-ambiente.md#situação-da-validação).

## Escopo e ambiente

| Item | Descrição |
| --- | --- |
| Data de referência | 9 de outubro de 2026 |
| Destino | Assinatura de teste, em grupos de recursos exclusivos criados para a validação e excluídos em seguida. Os identificadores do ambiente não são publicados. |
| Execução | Sequência executada com apoio do GitHub Copilot CLI na estação do mantenedor; passos do VS Code conduzidos por automação da interface. |
| Versões | Windows, Python 3.12.10, Azure CLI 2.89.0, Bicep 0.48.1, VS Code 1.141, `azure-identity` 1.26.0 e `azure-storage-blob` 12.31.0. |
| Repetição dos comandos | Comandos do guia repetidos literalmente, com troca apenas dos valores de exemplo, em PowerShell 7.6 (região `brazilsouth`) e em Windows PowerShell 5.1 (região `eastus2`, em uma pasta com espaços e acentos no caminho). Executados à parte: a concessão administrativa do papel de dados e a exclusão isolada da conta. |
| Aprovação do mantenedor | Confirmada em 9 de outubro de 2026 para o material existente; não representa nova execução dos testes. |

## Matriz de validação

| Verificação | Resultado |
| --- | --- |
| Testes automáticos (`python -m unittest discover -s tests`) | Passaram: 46 casos, no estado do repositório ao fim deste desafio, sem acesso ao Azure; repetidos em ordem aleatória, de outro diretório e com `-X dev -W error`; cobertura de linhas e ramos dos scripts em 91% |
| Bicep | `az bicep lint`, `build` e `format` sem avisos nem diferenças; o arquivo de parâmetros lê a variável de ambiente, com e sem valor |
| Documentos | Nenhum link local ou âncora inválido, 39 URLs externas respondendo, 25 referências todas citadas e 21 blocos de PowerShell sem erro de sintaxe nas duas versões do PowerShell |
| Textos sintéticos | Referências a cláusulas, valores e prazos conferidos entre Condições Gerais, glossário e perguntas frequentes |
| Políticas e papéis da assinatura de teste | Consultados somente para leitura; nenhuma política relevante para armazenamento |
| `what-if` e implantação | Quatro criações, como descrito na Etapa 4; implantação em cerca de 35 a 40 segundos |
| Configuração da conta | Acesso público e chaves de conta desativados, TLS 1.2, HTTPS, exclusão reversível por 7 dias |
| Papel de dados | `Storage Blob Data Contributor` apenas no contêiner; sem a variável, três criações e `papelDeDadosAtribuido` falso, e o papel concedido depois levou cerca de 100 segundos para valer |
| Simulação, carga e verificação | Três documentos criados e conferidos; verificação aprovada |
| Leitura anônima | Negada com HTTP 409 em quatro endereços pelo script e em três por `curl`; HTTP simples recusado. Em uma conta temporária aberta de propósito (leitura anônima de blob ligada, só com os três documentos sintéticos), o `curl` sem credenciais recebeu HTTP 200 e o verificador reprovou com código 3, apontando os três endereços; o acesso foi fechado e o grupo, excluído em seguida |
| Reexecução | Três `[igual]`; ETags dos blobs idênticos antes e depois |
| Divergência provocada | Carga parou com código 3 sem alterar nenhum blob; verificação reprovou |
| `--substituir-divergentes` | Blob restaurado; as duas versões anteriores ficaram como instantâneos apagados e voltaram com `az storage blob undelete`, com o conteúdo igual ao do inventário |
| Concorrência | Dois envios simultâneos reais: um criou os três documentos e o outro parou com código 3; um blob alterado por terceiros entre a simulação e o envio foi preservado |
| Permissões e rede | Papel só de leitura: simulação funciona e o envio é negado, sem criar nada; contêiner inexistente e regras de rede bloqueando geram orientação, ambos com código 2 |
| Erros de ambiente | Sem login, sem `az`, sem bibliotecas, tenant inexistente e console sem acentos: mensagens claras e códigos de saída previstos |
| `--tenant-id` e `--detalhes` | Funcionaram; a saída detalhada não continha token nem cabeçalho de autorização |
| Limpeza | Conta excluída sozinha, com o grupo preservado, e grupo excluído; `az group exists` respondeu `false`; grupos preexistentes intactos |
| VS Code | Confiança na pasta, instruções do projeto (quatro arquivos), prévia do Markdown, terminal com `.venv`, seletor de interpretador e anexos com `#` conferidos na interface; o primeiro prompt foi respondido conforme a Conferência |
| Pedido de mudança no chat | Claude Sonnet 5.5, modo **Agent**, permissões manuais, em duas rodadas, ambas com plano antes de editar e arquivos criados sem pedido de aprovação. Na primeira, quatro comandos liberados com **Allow Once**; a suíte falhou com o Python do sistema e passou com o do `.venv`. Na segunda, com o interpretador no pedido, três comandos com **Allow Once** e a suíte passou com o `.venv` desde o início. O botão que limpa a conversa pediu confirmação e manteve os arquivos criados |
| Acentos na saída do agente | Antes da correção do UTF-8, o terminal do agente mostrava `T�tulo`; depois, `Título`, no mesmo VS Code |

## Correções feitas durante a validação

- O erro bruto do SDK só aparece com `--detalhes`.
- A mensagem de credencial cita `az --version`.
- Um `--conta` vazio recebe orientação.
- A saída redirecionada usa UTF-8.
- O bloco do papel de dados leva o ID entre aspas.
- A cláusula 1.5 das Condições Gerais deixou de afirmar que todo termo em negrito consta do glossário.

## Pedido de mudança no chat: observações

Exemplo do guia (`scripts/listar_documentos.py`), executado no VS Code 1.141, modo **Agent**, permissões
manuais, com Claude Sonnet 5.5. Outro modelo pode agir de outro modo.

**Primeira rodada, sem o interpretador no pedido.**

1. O agente leu os arquivos, apresentou o plano, perguntou se podia seguir e criou o script e um arquivo
   com seis testes.
2. Pediu quatro comandos, cada um liberado com **Allow Once**: os dois combinados, uma consulta ao ambiente
   e a repetição dos testes.
3. O primeiro `python -m unittest` falhou com `ModuleNotFoundError: No module named 'azure'`, porque o
   terminal do agente usou o Python do sistema, e não o do ambiente virtual.
4. O agente encontrou o `.venv` e repetiu o comando com `.\.venv\Scripts\python.exe`, sem instalar nada e
   avisando que isso fugia dos dois comandos combinados. Com esse Python, a suíte passou.

**Segunda rodada, com a frase "Use o Python do ambiente virtual, `.\.venv\Scripts\python.exe`".**

1. O agente planejou os dois comandos combinados com esse Python, e o erro `No module named 'azure'` não
   ocorreu.
2. A primeira execução da suíte mostrou dois erros nos testes novos, que liam os argumentos do próprio
   `unittest`. O agente corrigiu, e a segunda execução passou.
3. O agente contou como pendente só o status `pendente`; `lab_comum.aviso_de_revisao` trata como pendente
   tudo o que não é `aprovada`. Com os dados atuais o resultado é o mesmo.

**Botão que limpa a conversa.** O botão **Clears the chat and undoes all changes** pediu confirmação,
limpou a conversa e manteve os arquivos criados pelo agente.

## Pendências

| Item | Situação | Ação para encerrar |
| --- | --- | --- |
| macOS, Linux e WSL | Pendente | Executar os comandos do guia nesses sistemas e registrar as diferenças de sintaxe |
| Python diferente do 3.12 | Pendente | Repetir a Etapa 5 com outra versão suportada |
| Instalação das dependências a partir do PyPI público | Pendente | A rede do teste bloqueou o download direto, e as versões foram conferidas pela API do PyPI; repetir `pip install -r requirements\l100.txt` em uma rede com acesso ao PyPI |
| Regiões além de `brazilsouth` e `eastus2` | Pendente | Em `westeurope`, a implantação foi recusada com `RequestDisallowedByAzure` (região sem novos clientes); validar cada região antes de recomendá-la |
| Assinaturas gratuitas ou estudantis e políticas restritivas | Pendente | Repetir a Etapa 4 nesses ambientes |
| Implantação com papéis menores que *Owner* | Pendente | A conta de teste era proprietária; repetir a Etapa 4 com *Contributor* e a concessão administrativa do papel de dados |
| Confirmação interativa dos comandos de exclusão | Pendente | O teste usou `--yes`; executar `az group delete` sem a opção |
| VS Code com interface em português e em outras versões | Pendente | Repetir a Etapa 1 e registrar os nomes da interface |
| Prompts das Etapas 2 a 4 e modo construtor | Pendente | Executar no VS Code e registrar as respostas |
| Outros modelos além do Claude Sonnet 5.5 no pedido de mudança | Pendente | Repetir o exemplo com outro modelo disponível |
| Medição de custo | Pendente | Consultar o Cost Management depois de uma execução completa |
| Aprovação das Condições Gerais, do glossário e das perguntas frequentes | Confirmada | Mantenedor, em 9 de outubro de 2026; `revisao_real.status` passou a `aprovada` |
| Aprovação do texto e dos resultados do guia | Confirmada | Mantenedor, em 9 de outubro de 2026; as revisões por IA continuam identificadas separadamente |

## Revisão editorial

### Revisão inicial — Claude Sonnet 5.5

Revisão de 9 de outubro de 2026, conforme o guia de estilo do mantenedor (documento externo ao repositório),
feita por Claude Sonnet 5.5 no GitHub Copilot CLI. Leitura integral do guia na versão revisada, correções por
categoria e nova conferência dos trechos alterados depois da leitura.

| Categoria | Alteração no guia |
| --- | --- |
| Estrutura e títulos | Títulos padronizados (Conteúdo, Cenário, Objetivos, Tecnologias e conceitos, Pré-requisitos, Conferência do resultado, Solução de problemas, Situação da validação, Glossário), sub-etapas numeradas (2.1 a 2.4, 4.1 a 4.6 e 5.1 a 5.5) e âncoras atualizadas no guia e no README |
| Voz e tempo verbal | Referências a quem escreveu o guia retiradas; as observações do teste do pedido de mudança passaram a constar como observações da validação, com a versão do VS Code |
| Construção afirmativa | Negativas dispensáveis e contrastes reescritos; negativas mantidas em proibições, riscos e condições de erro |
| Qualificadores e nomes informais | "pequeno", "menos seguros", "sem mistério", "sem medo", "rode", "sumir" e "à mão" substituídos por medida, mecanismo ou termo neutro |
| Siglas e termos | Siglas definidas no primeiro uso; "grupo de testes" unificado como "grupo de recursos do laboratório"; glossário sem variantes do mesmo termo |
| Fontes e números | A citação então numerada como [20] foi movida para a frase que sustentava; volume de 21 KB medido; custo declarado como não medido na validação |
| Separação de registros | Matriz de validação, correções e narrativa dos testes movidas para este registro; o guia mantém só a situação da validação |
| Repetição | Parágrafo duplicado sobre o endereço público da conta removido |
| Prompts | Uma linha do prompt "revisar a base sem editá-la" passou para a forma afirmativa; o prompt reescrito não foi reexecutado no Copilot |

**Verificações finais.** Os blocos de código do guia (30) ficaram idênticos aos de antes da revisão, exceto a
linha do prompt citada acima. Os 21 blocos de PowerShell passaram na análise de sintaxe do PowerShell 7.6 e do
Windows PowerShell 5.1. Links locais, âncoras, URLs externas (todas com resposta HTTP 200) e referências
numeradas foram conferidos. Os 137 testes automáticos passaram. Nenhum comando foi executado no Azure nessa revisão.

### Revisão integral — GPT-6.1 Sol

Em 9 de outubro de 2026, o mantenedor solicitou nova revisão contra seu guia de estilo, externo ao
repositório. Foram lidos o guia completo e este registro; as categorias identificadas foram examinadas
nos sete desafios do L100.

No D01, a revisão definiu siglas no ponto de uso, tornou explícito o escopo do hash e das permissões,
separou recomendações para revisar o Copilot do histórico de suas execuções e renumerou as referências
pela primeira citação. Os nomes de interface testados foram preservados com sua versão.
A autoria inicial permanece atribuída ao Sonnet 5.5; o Sol revisou a documentação.

Comandos executáveis, código, dados sintéticos e medições históricas foram preservados.
Os sete guias foram relidos após as correções, com inspeção da renderização Markdown local.
Testes locais e análise de sintaxe não representam nova execução no Azure.

**Verificações desta revisão:** a suíte existente passou com 330 testes. Os 108 blocos PowerShell
dos sete guias foram comparados com a versão anterior e permanecem idênticos.
Esses blocos passaram na análise de sintaxe do PowerShell 7.6.6 e do
Windows PowerShell 5.1.26100.9444, sem erros.
As referências foram conferidas por ordem, cobertura e preservação das fontes.
A prévia local, gerada com o conversor Markdown do PowerShell, apresentou 85 tabelas com colunas
consistentes e 153 links internos com destino existente.
O verificador examinou 32 arquivos, 559 links no texto e 81 URLs externas, sem falhas detectadas.
A aprovação do mantenedor foi confirmada posteriormente, em 9 de outubro de 2026.

### Aprovação recebida e metadados

O mantenedor confirmou sua aprovação do material existente do L100. O estado dos três documentos
no inventário passou a `aprovada`; os textos, versões, tamanhos e hashes permaneceram iguais.
Esse campo controla o aviso de revisão, mas não compõe os metadados enviados aos blobs nem o texto
dos trechos. Assim, a aprovação não modifica a base recuperável ou as medições anteriores.
A observação das simulações nos guias foi atualizada para retirar o aviso que não aparece mais.
Novos conteúdos continuam exigindo a aprovação correspondente.

O teste do aviso foi ajustado com Claude Sonnet 5.5 para usar uma cópia do inventário e conferir
os estados aprovado e pendente. Ele deixa de depender do estado atual do pacote distribuído.
A lógica de produção permanece igual; a suíte completa passou com 330 testes.

## Autoria

Texto e código produzidos com Claude Sonnet 5.5, no GitHub Copilot CLI. O Astra, modelo preferido do
mantenedor para a documentação, não estava disponível na sessão. O modelo de autoria é independente do
modelo que o aluno escolhe no Copilot e dos modelos usados pela aplicação no Azure.
