#!/bin/sh
set -e

# Migracao no CMD, como nos outros stacks: container novo nunca sobe contra
# schema velho.
echo "==> aplicando migracoes"
flask db upgrade

echo "==> subindo gunicorn"
# limit-request-field_size: cookie nao distingue porta, entao o navegador manda
# os cookies dos cinco apps para cada um, num unico header Cookie. O padrao de
# 8190 estoura e vira 431. Os frontends Node usam 65536 pelo mesmo motivo.
exec gunicorn \
    --bind 0.0.0.0:8000 \
    --workers "${GUNICORN_WORKERS:-3}" \
    --timeout "${GUNICORN_TIMEOUT:-120}" \
    --limit-request-field_size "${GUNICORN_HEADER_SIZE:-65536}" \
    --access-logfile - \
    --error-logfile - \
    "wsgi:app"
