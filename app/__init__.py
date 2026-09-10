"""Pacote da aplicacao.

Nao importa Flask: `create_app` vem por __getattr__ preguicoso, para que
importar o parser puro nao arraste o framework junto.
"""

from __future__ import annotations

__all__ = ["create_app"]


def __getattr__(nome: str):
    if nome == "create_app":
        from app.factory import create_app

        return create_app
    raise AttributeError(f"module {__name__!r} has no attribute {nome!r}")
