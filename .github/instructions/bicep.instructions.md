---
description: Regras para arquivos Bicep e de parâmetros do laboratório.
applyTo: "infra/**/*.bicep,infra/**/*.bicepparam"
---
# Bicep no Vareleira RAG

- Mantenha o Bicep em `infra/`, com um arquivo de parâmetros por nível em `infra/levels/`. Reaproveite os recursos dos níveis anteriores e documente migrações.
- Use a versão de API estável mais recente que o Bicep CLI consiga tipar (sem o aviso BCP081). Se existir uma mais nova sem tipos, explique em um comentário.
- Segurança por padrão: sem acesso anônimo, sem chaves de conta (`allowSharedKeyAccess: false`), TLS 1.2, somente HTTPS, acesso a dados por Microsoft Entra ID e papéis RBAC no menor escopo. Não desative proteções como a proteção contra exclusão definitiva do Key Vault: o padrão do módulo é ligada (`protecaoContraExpurgo = true`). A única exceção é o arquivo `infra/levels/l100-desafio07.bicepparam`, que a desliga de propósito para o laboratório poder ser removido por inteiro, com o motivo em um comentário e no guia do Desafio 07. O Azure não aceita `false` nessa propriedade: omita-a (`null`).
- Busca e modelos (Desafio 02): `disableLocalAuth: true` (sem chaves de API) e `versionUpgradeOption: 'NoAutoUpgrade'` no deployment de embeddings, para que o modelo não mude sem que o índice seja refeito. Módulos de um desafio ficam desligados por padrão (`implantarIndexacao = false` em `main.bicep`), para que um desafio anterior nunca passe a cobrar sem pedido.
- Nunca fixe IDs de assinatura, tenant ou pessoas. Use parâmetros e `readEnvironmentVariable()` nos arquivos `.bicepparam`.
- Valide com `az bicep lint --file infra/main.bicep`, `az bicep build --file infra/main.bicep --stdout` e `az deployment group what-if` antes de qualquer implantação. O lint sai com código 0 mesmo com avisos (como BCP036, de valor com maiúsculas e minúsculas diferentes do tipo): leia a saída, que deve estar vazia. Gerar o Bicep não autoriza implantar, atribuir papéis nem excluir recursos.
