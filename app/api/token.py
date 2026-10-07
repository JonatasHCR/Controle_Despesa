"""Autenticação de serviço por token estático (Bearer), como na API da Receita."""

from __future__ import annotations

import hashlib
import hmac
from functools import wraps

from flask import current_app, jsonify, request


def requer_token(funcao):
    @wraps(funcao)
    def protegida(*args, **kwargs):
        esperado = current_app.config.get("SYNC_API_TOKEN", "")
        if not esperado:
            return jsonify(error="SYNC_API_TOKEN não configurado no servidor."), 503

        cabecalho = request.headers.get("Authorization", "")
        recebido = cabecalho[7:] if cabecalho.lower().startswith("bearer ") else ""
        # digest iguala o tamanho; compare_digest mantém tempo constante
        ok = hmac.compare_digest(
            hashlib.sha256(recebido.encode()).digest(),
            hashlib.sha256(esperado.encode()).digest(),
        )
        if not ok:
            return jsonify(error="Não autorizado."), 401
        return funcao(*args, **kwargs)

    return protegida
