# Suporte

O suporte é comunitário, em português do Brasil, conforme a disponibilidade
do mantenedor. Não há acordo de nível de serviço, prazo garantido de resposta,
correção ou compromisso de compatibilidade futura.

## Canais

- [Discussions](https://github.com/EdneiMonteiro/vareleira-rag/discussions):
  dúvidas, propostas de arquitetura e ideias para o laboratório.
- [Issues](https://github.com/EdneiMonteiro/vareleira-rag/issues):
  erros de documentação e problemas reproduzíveis do material disponível.
- [Comunicação privada de segurança](SECURITY.md):
  vulnerabilidades e exposição de informações sensíveis.

Antes de abrir uma conversa, procure relatos semelhantes. Informe o objetivo,
o arquivo ou revisão utilizados, o comportamento esperado e o resultado
observado. Para problemas de execução, inclua o sistema operacional, as versões
do Python e da Azure CLI, o comando executado e a mensagem de erro sem
identificadores do seu ambiente (assinatura, tenant, nome da conta) e sem
tokens. Use sempre dados sintéticos.

## Limites

Os sete desafios do L100 têm artefatos disponíveis e foram executados no Azure em Windows com
PowerShell. O Desafio 07 inclui a validação autorizada da identidade da aplicação e de sua limpeza.
Os limites e as verificações ainda pendentes constam nos registros de cada desafio. Consulte o
[estado do laboratório](README.md#estado-do-laboratório) para distinguir entregas disponíveis de
níveis planejados.

O L200 acrescenta ingestão gerenciada e chat com autenticação obrigatória. Para erros da interface,
informe o código de suporte, revisão, tipo de erro e uma descrição sintética, sem enviar a conversa.
HTTP 503 por resposta não verificada é um descarte da política; HTTP 401 indica acesso ainda não
autenticado. Login interativo humano e autorização por documento não integram a validação automatizada.

Trate permissões, políticas, cotas e cobrança com o administrador do seu ambiente ou com o suporte
do Azure. Registrar aplicações no tenant (diretório do Microsoft Entra ID), como no Desafio 07,
também exige autorização. Serviços de terceiros devem ser tratados em seus próprios canais de
suporte. Este projeto não atende segurados nem esclarece situações reais de
cobertura.

Não publique documentos reais, informações pessoais, tokens ou credenciais.
Siga o [código de conduta](CODE_OF_CONDUCT.md).
