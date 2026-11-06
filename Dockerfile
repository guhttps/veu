FROM python:3.13-slim

LABEL org.opencontainers.image.title="Véu" \
      org.opencontainers.image.description="Gateway que esconde dados pessoais e segredos antes de enviar textos para modelos de IA" \
      org.opencontainers.image.source="https://github.com/guhttps/veu" \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    VEU_HOST=0.0.0.0 \
    VEU_PORTA=8787

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install ".[servidor,redis,documentos]" && useradd --create-home --uid 10001 veu

USER veu
EXPOSE 8787
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8787/veu/saude', timeout=4)"

# O Véu não inicia fora do localhost sem VEU_TOKEN (ou VEU_PERMITIR_SEM_TOKEN=1): veja docs/integracoes.md#docker
CMD ["veu", "servir"]
