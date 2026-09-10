"""Trilha de auditoria: append-only, escrita por chamada explicita a registrar().

O commit fica por conta de quem chamou, para que um rollback derrube o registro
junto com a operacao que falhou.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db


class Auditoria(db.Model):
    __tablename__ = "tb_auditoria"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    acao: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    # SET NULL: o registro nao some junto com quem fez.
    usuario_id: Mapped[int | None] = mapped_column(
        ForeignKey("tb_usuarios.id", ondelete="SET NULL"), nullable=True, index=True
    )

    alvo_tipo: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    alvo_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)

    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )

    def __repr__(self) -> str:
        return f"<Auditoria {self.acao} {self.alvo_tipo}#{self.alvo_id}>"
