# Sonda do L300: confere o laboratório de dentro da rede privada, como um Azure Container Apps Job de execução manual.
# Modelo do Dockerfile: o scripts/montar_contexto_sonda_l300.py o copia, com a lista de permissão (dockerignore, ao lado) e só os
# arquivos abaixo, para uma pasta própria. Faça o build dessa pasta, nunca da raiz do repositório (lá o Dockerfile é o do chat).
#
# A base é a imagem do chat, informada por --build-arg IMAGEM_CHAT=<registro>/<repositório>:<tag> (ou @sha256:<digest>) e sem valor
# padrão: sem o argumento, o build falha. Ela traz o Python, os pacotes e os módulos do chat (lab_comum, lab_acesso, lab_indexacao,
# lab_geracao, lab_politica, lab_chat e lab_orquestracao) que a sonda reutiliza: o Recuperador e o ServicoRag reais. Aqui entram só a
# sonda, o gerador de carga do L400, a ferramenta de ingestão do L300 com os módulos que o chat não tem e os documentos sintéticos
# aprovados. Nunca entram segredos, .git, sessões nem conjuntos de avaliação.
ARG IMAGEM_CHAT
FROM ${IMAGEM_CHAT}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY scripts/sonda_l300.py scripts/gerar_carga_l400.py scripts/gerenciar_ingestao_l300.py scripts/gerenciar_ingestao.py scripts/lab_ingestao.py scripts/lab_ingestao_l300.py ./scripts/
COPY dados/l100/inventario.json ./dados/l100/inventario.json
COPY dados/l100/documentos/vareleira-lar-condicoes-gerais-v1.0.md dados/l100/documentos/vareleira-lar-faq-v1.0.md dados/l100/documentos/vareleira-lar-glossario-v1.0.md ./dados/l100/documentos/
COPY dados/l300/permissoes-documentais.json ./dados/l300/permissoes-documentais.json
COPY dados/l300/documentos/roteiro-interno-atendimento-v1.0.md ./dados/l300/documentos/roteiro-interno-atendimento-v1.0.md

# Sem root (o mesmo UID do chat). A base declara HEALTHCHECK e EXPOSE para o servidor; aqui não há servidor, e o EXPOSE herdado
# é só metadado.
USER 10001:10001
HEALTHCHECK NONE

# Falha o build se a base estiver desatualizada, se faltar um módulo ou pacote, ou se um documento não conferir com o manifesto.
# É local e sem rede. A forma JSON dispensa o shell.
RUN ["python", "scripts/sonda_l300.py", "--etapa", "validar"]

# Uma etapa por execução, por --etapa ou VARELEIRA_PROBE_ETAPA; o resultado é a linha L300_SONDA_RESULTADO=<JSON>.
# O gerador de carga do L400 (scripts/gerar_carga_l400.py) também está na imagem, mas o ENTRYPOINT continua sendo a sonda: o gerador
# roda por substituição de comando no início do Job (az containerapp job start --command ... --args ...), sem mudar a imagem.
ENTRYPOINT ["python", "scripts/sonda_l300.py"]
CMD []
