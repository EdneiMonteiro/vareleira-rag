# Política de segurança

## Escopo acompanhado

O acompanhamento se concentra nos arquivos disponíveis na branch `main`.
Há Bicep, scripts Python e dados sintéticos do L100, mas não há aplicação em
produção nem releases suportadas. São bem-vindos relatos de falhas de segurança
nos padrões do Bicep (acesso público, chaves, TLS), nos scripts (vazamento de
credenciais ou de segredos, validação de entrada) e nos documentos. São também bem-vindos
relatos sobre papéis ou identidades que os guias criam com privilégio demais. A inclusão de novos níveis
não implicará compromisso de suporte a versões antigas.

## Relato privado

Use [Report a vulnerability](https://github.com/EdneiMonteiro/vareleira-rag/security/advisories/new)
para comunicar vulnerabilidades em privado. Se o recurso estiver indisponível,
contate **ednei@live.com** antes de enviar detalhes sensíveis.
Não abra issues ou discussões públicas com detalhes exploráveis.

Informe arquivos e revisão afetados, impacto e reprodução mínima com dados
sintéticos. Não envie credenciais, dados pessoais ou documentos reais.
Não realize testes destrutivos nem testes contra serviços de terceiros.

Se uma credencial foi exposta, revogue-a no serviço de origem. Apagar um
arquivo, mensagem ou commit não invalida o segredo. Relate a ocorrência sem
reproduzir seu valor.

## Atendimento

O mantenedor avaliará relatos conforme sua disponibilidade, sem prazo
garantido de resposta ou correção. Problemas de conteúdo e dúvidas de uso
devem seguir [SUPPORT.md](SUPPORT.md).
