"""Ponto de entrada do gunicorn e do `flask` CLI (via FLASK_APP=wsgi)."""

from app.factory import create_app

app = create_app()
