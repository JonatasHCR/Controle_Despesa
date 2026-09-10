"""Escrita da trilha de auditoria.

`registrar` apenas adiciona a entrada a sessao; o commit e de quem chamou. Assim
um rollback derruba o registro junto com a operacao que falhou, em vez de
afirmar que aconteceu algo que nao aconteceu.
"""

from __future__ import annotations

from app.models import Auditoria


def registrar(
    session,
    *,
    acao: str,
    alvo_tipo: str,
    usuario=None,
    alvo_id: int | None = None,
    payload: dict | None = None,
) -> Auditoria:
    entrada = Auditoria(
        acao=acao,
        usuario_id=getattr(usuario, "id", None),
        alvo_tipo=alvo_tipo,
        alvo_id=alvo_id,
        payload=payload,
    )
    session.add(entrada)
    return entrada
