# Imagem do chat do L200. Contexto de build: a raiz do projeto; o .dockerignore só deixa entrar os arquivos copiados abaixo.
# A imagem não guarda segredos nem configuração: o contêiner recebe tudo por variáveis de ambiente e usa a identidade
# gerenciada da aplicação. Sem as variáveis obrigatórias (veja scripts/lab_chat.py), ele não inicia.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependências primeiro: a camada só muda quando os manifestos mudam. O l200.txt inclui o l100.txt.
COPY requirements/l100.txt requirements/l200.txt ./requirements/
RUN python -m pip install -r requirements/l200.txt

# Só os módulos que o chat importa (lab_comum, lab_indexacao, lab_geracao e lab_politica) e a interface.
COPY scripts/lab_comum.py scripts/lab_indexacao.py scripts/lab_geracao.py scripts/lab_politica.py scripts/lab_chat.py scripts/chat_web.py ./scripts/
COPY web/index.html web/app.js web/style.css ./web/

RUN groupadd --system --gid 10001 vareleira \
    && useradd --system --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin vareleira
USER 10001:10001

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3)"]

ENTRYPOINT ["python", "scripts/chat_web.py", "--host", "0.0.0.0", "--port", "8000"]
