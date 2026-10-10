# Avisos de uso

## Ficção e finalidade educacional

A Vareleira, seus personagens, produtos e acontecimentos corporativos são
fictícios. Este laboratório não representa uma seguradora autorizada, não
comercializa seguros e não recebe propostas ou documentos de segurados.
Não presta aconselhamento jurídico, regulatório ou securitário.

O repositório está em desenvolvimento. Hoje existem os sete desafios do L100: o
armazenamento, a carga e a indexação de documentos sintéticos, respostas com
fontes e recusas, um agente, a avaliação das respostas e a identidade da
aplicação com um cofre de segredos. O assistente é um exercício de console: não
há aplicação de chat. A narrativa de soluções em produção não significa que
exista uma implementação operacional neste projeto.

## Limites das respostas

A geração aumentada por recuperação (RAG, *Retrieval-Augmented Generation*) fornece documentos ao
modelo como contexto. Respostas ainda podem conter erros, omissões ou interpretações incorretas.
Confira o sentido da resposta, a fonte citada e sua vigência.

O assistente consulta condições gerais sintéticas para explicar o produto. Decisões sobre cobertura
individual, indenização ou elegibilidade, emissão de contratos e ações em sistemas estão fora do
escopo. O detector de veredito pode deixar passar conclusões individuais, e a citação literal apenas
confere se a frase existe na fonte. Revise a correspondência entre a resposta e os documentos.
As taxas do Desafio 06 descrevem os dois conjuntos de 12 perguntas usados na medição; sua generalização
exige amostras maiores e representativas. O teste teve duas falsas recusas em 12,
acima do máximo de uma admitido pelo critério de escolha.

## Dados, serviços e custos

Use apenas dados e documentos sintéticos. Não publique nem carregue
documentos reais, dados pessoais, credenciais ou segredos no laboratório.
Antes de usar serviços externos em uma adaptação, avalie quais informações
serão transmitidas, políticas de retenção, permissões e termos do serviço.

Os comandos do L100 criam recursos reais no Azure e enviam documentos sintéticos
a eles, mas somente quando você os executa. O Desafio 01 cria grupo de recursos,
conta de armazenamento, contêiner e atribuição de papel. O Desafio 02 acrescenta
um serviço de busca, um recurso de modelos com um deployment de embeddings e
atribuições de papel, e **envia o texto dos documentos ao deployment de
embeddings da sua própria assinatura** para calcular os vetores. O Desafio 03
acrescenta um deployment de geração e **envia a pergunta e os trechos recuperados
ao deployment de geração da sua própria assinatura**; os Desafios 04 a 06 repetem
esse envio, o 06 para dezenas de perguntas de avaliação. O Desafio 07 acrescenta um
Key Vault e, se você executar a Etapa 5, **cria no Microsoft Entra ID uma identidade
de aplicação (service principal) e uma credencial**, que exige permissão de
registrar aplicações no tenant, e guarda a credencial no cofre. Isso gera custo
de armazenamento, operações, busca (cobrada por hora enquanto o serviço existir),
uso de modelos (cobrado por tokens) e operações do cofre, e exige permissões na
sua assinatura e, no Desafio 07, no tenant.
Implementações futuras poderão gerar também outros custos de modelos e
infraestrutura. Quem executa é responsável por verificar preços, limites e
políticas da organização e por excluir os recursos, as identidades e as
credenciais que criou; o guia de cada desafio descreve a limpeza.

## Produção, suporte e garantias

Uma adoção em produção exige autorização e avaliação próprias. Avalie
segurança, privacidade, qualidade, acessibilidade, observabilidade, resposta a
incidentes, contingência e custos no ambiente de destino.

Projeto pessoal, sem afiliação, endosso ou suporte oficial da Microsoft, do
GitHub ou de uma seguradora. Nomes de produtos são referências descritivas.
O suporte é comunitário, conforme [SUPPORT.md](SUPPORT.md), sem prazo garantido.

Código e conteúdo são fornecidos no estado em que se encontram, sob as
exclusões de garantia e limites de responsabilidade das [licenças](LICENSE),
na extensão permitida pela legislação.
