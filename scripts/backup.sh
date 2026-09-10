#!/bin/sh
# Backup agendado. Grava no mesmo /backups do painel admin, para que os dois
# apareçam na mesma lista.
set -eu

BACKUP_DIR="${BACKUP_DIR:-/backups}"
INTERVAL="${BACKUP_INTERVAL_HOURS:-24}"
KEEP="${BACKUP_KEEP:-7}"

mkdir -p "$BACKUP_DIR"

echo "backup: a cada ${INTERVAL}h, mantendo ${KEEP} arquivos em ${BACKUP_DIR}"

while true; do
    FILE="$BACKUP_DIR/controle_despesa_$(date +%Y%m%d_%H%M).sql"

    # --clean --if-exists nao e opcional: sem os DROPs, restaurar por cima de
    # um banco povoado aplica so os COPY que nao conflitam.
    if PGPASSWORD="$POSTGRES_PASSWORD" pg_dump \
            -h db -U "$POSTGRES_USER" \
            --clean --if-exists --no-owner --no-privileges \
            "$POSTGRES_DB" > "$FILE"; then
        echo "backup: ok -> $(basename "$FILE") ($(wc -c < "$FILE") bytes)"
    else
        # Nao deixa arquivo de zero byte passando por backup valido.
        echo "backup: FALHOU, descartando $(basename "$FILE")" >&2
        rm -f "$FILE"
    fi

    # Rotacao: mantem os $KEEP mais recentes.
    ls -t "$BACKUP_DIR"/controle_despesa_*.sql 2>/dev/null \
        | tail -n +$((KEEP + 1)) \
        | xargs -r rm -f

    sleep $((INTERVAL * 3600))
done
