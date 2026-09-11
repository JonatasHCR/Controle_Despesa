"""A despesa — registro central do sistema."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    false,
    func,
    text,
)
from sqlalchemy import and_ as sa_and
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db

DINHEIRO = Numeric(14, 2)


class Despesa(db.Model):
    __tablename__ = "tb_despesas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # A mesma referencia pode aparecer em lancamentos distintos; o que nao pode
    # repetir e ela junto do resto (ver CHAVE_NATURAL).
    referencia: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

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

    # Marcada quando a diferenca e esperada (baixa parcial que ainda vai crescer):
    # para de sinalizar sem mexer nos valores.
    divergencia_ignorada: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=false(), default=False
    )

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
        # `historico` entra pelo md5: e TEXT, e um valor longo estouraria o
        # limite de tamanho da linha do indice btree no meio de uma importacao.
        Index(
            "uq_despesa_natural",
            "referencia",
            "fornecedor_id",
            "natureza_id",
            "centro_custo_id",
            "documento",
            text("md5(historico)"),
            unique=True,
        ),
        CheckConstraint(
            "valor_original IS NULL OR valor_original >= 0", name="ck_despesa_original"
        ),
        CheckConstraint("valor_baixado IS NULL OR valor_baixado >= 0", name="ck_despesa_baixado"),
        Index("ix_despesas_periodo_centro", "data_baixa", "centro_custo_id"),
        Index("ix_despesas_centro_natureza_data", "centro_custo_id", "natureza_id", "data_baixa"),
    )

    @hybrid_property
    def divergente(self) -> bool:
        return not self.divergencia_ignorada and self.valor_original != self.valor_baixado

    @divergente.expression
    @classmethod
    def divergente(cls):
        # IS DISTINCT FROM, e nao `<>`: com NULL de um lado o `<>` devolve NULL
        # e a linha sumiria do filtro em silencio.
        return sa_and(
            cls.divergencia_ignorada.is_(False),
            cls.valor_original.is_distinct_from(cls.valor_baixado),
        )

    @hybrid_property
    def diverge_nos_valores(self) -> bool:
        """A diferenca crua, ignorando a marcacao. E o que a tela de edicao
        mostra para explicar por que existe a opcao de parar de sinalizar."""
        return self.valor_original != self.valor_baixado

    @diverge_nos_valores.expression
    @classmethod
    def diverge_nos_valores(cls):
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
