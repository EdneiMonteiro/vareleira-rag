---
description: Regras para scripts Python e testes que acessam o Azure neste laboratório.
applyTo: "scripts/**/*.py,tests/**/*.py"
---
# Python e Azure no Vareleira RAG

- Autentique com Microsoft Entra ID: `AzureCliCredential` nos scripts do L100 e identidade gerenciada ou `DefaultAzureCredential` quando o código rodar no Azure. A identidade de uma aplicação (service principal, Desafio 07) entra por uma credencial opcional nas funções que criam clientes, nunca por uma chave fixa. Nunca use chaves de conta, connection strings ou SAS assinada com chave.
- Segredos (credencial de aplicação, senha, token) entram por entrada padrão ou variável de ambiente, nunca por argumento de comando; ficam só na memória ou no serviço de segredos autorizado. O L100 usa Key Vault; o L200 guarda somente a credencial do provedor de login em Container Apps Secrets, lida pelo EasyAuth e não pelo contêiner do chat. Dados e modelos usam identidade gerenciada. Nunca imprima segredos, grave-os em arquivo ou repita-os em mensagens de erro. Teste que o valor não aparece na saída.
- Receba conta, contêiner, serviço de busca (`--busca`), recurso de modelos (`--modelos`) e tenant por argumento e valide o formato antes de montar URLs, para que o token só vá ao endereço esperado. Não fixe IDs de assinatura, tenant ou pessoas em código, testes ou mensagens.
- Ações que alteram o Azure exigem opção explícita: o padrão é simular. Nunca sobrescreva em silêncio; use condições (`overwrite=False`, ETag) e pare diante de divergências.
- Mensagens para o aluno em pt-BR, com orientação de correção. Não imprima tokens, cabeçalhos de autorização nem a mensagem bruta do serviço (ela só aparece com `--detalhes`).
- Reaproveite `scripts/lab_comum.py` (inventário, hash, argumentos, erros), `scripts/lab_indexacao.py` (trechos, índice, embeddings, busca), `scripts/lab_geracao.py` (geração), `scripts/lab_politica.py` (política de resposta), `scripts/lab_agente.py` (agente), `scripts/lab_avaliacao.py` (avaliação) e `scripts/lab_identidade.py` (segredo e identidade da aplicação) antes de criar funções novas.
- Indexação e consulta usam o mesmo deployment de embeddings e as mesmas dimensões; a impressão digital de cada trecho os inclui. Mudar um deles exige reindexar, nunca misturar vetores de modelos diferentes.
- Fixe as versões diretas em `requirements/`. Escreva testes com `unittest` e dublês, sem acessar o Azure, e execute `python -m unittest discover -s tests`.
