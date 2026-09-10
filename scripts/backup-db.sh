#!/bin/sh
# Backup manual, a partir do host. Cai no mesmo ./backups do sidecar e do painel.
set -eu

cd "$(dirname "$0")/.."
. ./.env

TS=$(date +%Y%m%d_%H%M%S)
ARQUIVO="./backups/${POSTGRES_DB}_${TS}.sql"

mkdir -p ./backups

docker compose exec -T db pg_dump \
    -U "$POSTGRES_USER" \
    --clean --if-exists --no-owner --no-privileges \
    "$POSTGRES_DB" > "$ARQUIVO"

echo "backup: $ARQUIVO ($(wc -c < "$ARQUIVO") bytes)"
