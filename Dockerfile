# Multi-estágio. O primeiro traduz o poetry.lock em requirements.txt; o segundo
# instala só isso. Assim o Poetry e o pip cache não viajam para a imagem final.

# --- estágio 1: resolver dependências ---------------------------------------
FROM python:3.12-slim AS dependencias

ENV PIP_NO_CACHE_DIR=1
ARG INSTALL_DEV=false

WORKDIR /app

RUN pip install --no-cache-dir "poetry==1.8.5" "poetry-plugin-export==1.8.0"

COPY pyproject.toml poetry.lock* ./
RUN if [ ! -f poetry.lock ]; then poetry lock --no-interaction --no-ansi; fi \
    && if [ "$INSTALL_DEV" = "true" ]; then \
           poetry export --with dev --without-hashes -f requirements.txt -o /tmp/req.txt; \
       else \
           poetry export --without-hashes -f requirements.txt -o /tmp/req.txt; \
       fi

# --- estágio 2: imagem de execução ------------------------------------------
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=America/Sao_Paulo

# libpango/libcairo: WeasyPrint. postgresql-client: o pg_dump/pg_restore do
# painel admin roda dentro deste container, não num sidecar com socket Docker.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpango-1.0-0 \
        libpangoft2-1.0-0 \
        libharfbuzz0b \
        libcairo2 \
        libgdk-pixbuf-2.0-0 \
        shared-mime-info \
        fonts-dejavu-core \
        postgresql-client \
    && rm -rf /var/lib/apt/lists/*

COPY --from=dependencias /tmp/req.txt /tmp/req.txt
RUN pip install --no-cache-dir -r /tmp/req.txt && rm /tmp/req.txt

# Usuário sem privilégio: se a aplicação for comprometida, o atacante não
# começa como root dentro do container. O uid é fixo para casar com o dono do
# bind mount de ./backups no host.
RUN groupadd --gid 10001 despesa \
    && useradd --uid 10001 --gid despesa --create-home --shell /usr/sbin/nologin despesa

WORKDIR /app
COPY --chown=despesa:despesa . .

# sed: um checkout no Windows grava o .sh com CRLF, o shebang vira `/bin/sh\r`
# e o Docker reporta isso como se o entrypoint nao existisse.
RUN sed -i 's/\r$//' /app/entrypoint.sh \
    && chmod +x /app/entrypoint.sh \
    && mkdir -p /backups \
    && chown despesa:despesa /backups

USER despesa

EXPOSE 8000
CMD ["/app/entrypoint.sh"]
