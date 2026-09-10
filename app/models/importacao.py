"""Registro de cada importacao de planilha.

O sha256 permite reconhecer que aquele arquivo exato ja entrou.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db


class Importacao(db.Model):
    __tablename__ = "tb_importacoes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    arquivo: Mapped[str] = mapped_column(String(255), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    usuario_id: Mapped[int | None] = mapped_column(
        ForeignKey("tb_usuarios.id", ondelete="SET NULL"), nullable=True
    )

    linhas_lidas: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    linhas_ignoradas: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    criados: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    atualizados: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )

    despesas = relationship("Despesa", back_populates="importacao")

    def __repr__(self) -> str:
        return f"<Importacao {self.arquivo} +{self.criados}/~{self.atualizados}>"
