#!/bin/sh
set -e

# Migracao no CMD, como nos outros stacks: container novo nunca sobe contra
# schema velho.
echo "==> aplicando migracoes"
flask db upgrade

echo "==> subindo gunicorn"
exec gunicorn \
    --bind 0.0.0.0:8000 \
    --workers "${GUNICORN_WORKERS:-3}" \
    --timeout "${GUNICORN_TIMEOUT:-120}" \
    --access-logfile - \
    --error-logfile - \
    "wsgi:app"
