"""A despesa — registro central do sistema."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db

DINHEIRO = Numeric(14, 2)


class Despesa(db.Model):
    __tablename__ = "tb_despesas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Chave natural do ERP; e o que torna a importacao idempotente.
    referencia: Mapped[int] = mapped_column(Integer, nullable=False, unique=True, index=True)

    data_baixa: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    data_emissao: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)

    centro_custo_id: Mapped[int] = mapped_column(
        ForeignKey("tb_centros_custo.id"), nullable=False, index=True
    )
    fornecedor_id: Mapped[int] = mapped_column(
        ForeignKey("tb_fornecedores.id"), nullable=False, index=True
    )
    natureza_id: Mapped[int] = mapped_column(
        ForeignKey("tb_naturezas.id"), nullable=False, index=True
    )

    historico: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    documento: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default="", index=True
    )

    valor_original: Mapped[Decimal | None] = mapped_column(DINHEIRO, nullable=True)
    valor_baixado: Mapped[Decimal | None] = mapped_column(DINHEIRO, nullable=True)

    # NULL = lancada a mao, e nao vinda de planilha.
    importacao_id: Mapped[int | None] = mapped_column(
        ForeignKey("tb_importacoes.id", ondelete="SET NULL"), nullable=True, index=True
    )
    criado_por_id: Mapped[int | None] = mapped_column(
        ForeignKey("tb_usuarios.id", ondelete="SET NULL"), nullable=True
    )

    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    centro_custo = relationship("CentroCusto", lazy="joined")
    fornecedor = relationship("Fornecedor", lazy="joined")
    natureza = relationship("Natureza", lazy="joined")
    importacao = relationship("Importacao", back_populates="despesas")

    __table_args__ = (
        CheckConstraint(
            "valor_original IS NULL OR valor_original >= 0", name="ck_despesa_original"
        ),
        CheckConstraint("valor_baixado IS NULL OR valor_baixado >= 0", name="ck_despesa_baixado"),
        Index("ix_despesas_periodo_centro", "data_baixa", "centro_custo_id"),
        Index("ix_despesas_centro_natureza_data", "centro_custo_id", "natureza_id", "data_baixa"),
    )

    @hybrid_property
    def divergente(self) -> bool:
        return self.valor_original != self.valor_baixado

    @divergente.expression
    @classmethod
    def divergente(cls):
        # IS DISTINCT FROM, e nao `<>`: com NULL de um lado o `<>` devolve NULL
        # e a linha sumiria do filtro em silencio.
        return cls.valor_original.is_distinct_from(cls.valor_baixado)

    @hybrid_property
    def diferenca(self) -> Decimal | None:
        if self.valor_baixado is None or self.valor_original is None:
            return None
        return self.valor_baixado - self.valor_original

    @diferenca.expression
    @classmethod
    def diferenca(cls):
        return cls.valor_baixado - cls.valor_original

    def __repr__(self) -> str:
        return f"<Despesa ref={self.referencia} {self.valor_baixado}>"
