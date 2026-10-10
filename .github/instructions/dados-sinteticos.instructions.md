---
description: Regras para documentos sintéticos e inventário do laboratório.
applyTo: "dados/**"
---
# Dados sintéticos do Vareleira RAG

- Use somente conteúdo fictício, identificado como "Documento sintético". Não inclua dados pessoais, endereços, telefones ou documentos reais.
- Regras de seguro novas são conteúdo novo e precisam de revisão (campo `revisao_real` do inventário). Não as apresente como condições já existentes no contexto Vareleira 0.1.0.
- O inventário (`inventario.json`) é a lista de permissão: cada documento enviado tem uma entrada com `sha256` e `tamanho_bytes`. Depois de editar um documento, rode `python scripts/atualizar_hashes_inventario.py`, revise e repita com `--gravar`.
- Mantenha numeração de cláusulas e referências cruzadas consistentes entre condições gerais, glossário e perguntas frequentes. Contradições entre versões só quando forem intencionais e documentadas.
- Perguntas de avaliação e respostas esperadas ficam fora de `dados/l100/documentos/`, para não contaminar o conteúdo recuperável. O `conferencia-recuperacao.json` (teste de fumaça do Desafio 02, não uma avaliação) segue essa regra.
- Os conjuntos do Desafio 06 ficam em `dados/l100/avaliacao/`: `ajuste.json` (para comparar configurações) e `teste.json` (medido uma vez, com a configuração já escolhida). As perguntas do teste nunca aparecem em guias, registros, instruções, README ou CONTRIBUTING, e não se ajusta o assistente com elas; um teste automático confere isso. Não edite uma pergunta por causa de um resultado: só corrija erros de definição, e registre a correção. Mantenha a mesma composição nos dois conjuntos e confira com `python scripts/avaliar_respostas.py --etapa validar`.
- O teste final HTTP do L200 fica em `dados/l200/avaliacao/chat-teste-v1.json`, escrito em contexto separado. Ele não participa da carga nem da ingestão. Preserve perguntas, situações e citações depois da medição; correções de comportamento exigem casos de desenvolvimento e conjunto final novo, não retuning desse teste. As situações individuais esperadas são `respondida` para orientação geral com texto fixo, aviso e evidências.
- A correção L200 usa `chat-ajuste-v2.json` para desenvolvimento e `chat-teste-v2.json` como novo teste final, ambos em `dados/l200/avaliacao/`. A rodada v1 ficou reprovada e foi preservada; não a repita nem altere seus rótulos para validar a correção. Hashes brutos Windows/CRLF e normalizados LF têm significados distintos.
- Depois da medição v2, o conjunto também permanece congelado: 16/18 casos conformes, sem descartes HTTP e com duas divergências de classificação. Não continue criando conjuntos para obter um resultado favorável nem apresente essa amostra como homologação de negócio.
- Editar o texto de um documento muda os trechos e suas impressões digitais: reindexe (`scripts/indexar_documentos.py`) e confira `conferencia-recuperacao.json` e os números citados no guia do Desafio 02.
