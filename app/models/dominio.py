"""Tabelas de dominio: centro de custo, fornecedor e natureza."""

from __future__ import annotations

import re

from sqlalchemy import Boolean, Integer, String, select
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db

_ESPACOS = re.compile(r"\s+")


def normalizar(nome: str) -> str:
    return _ESPACOS.sub(" ", str(nome or "")).strip()


class _Nomeada:

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    @classmethod
    def obter_ou_criar(cls, session, nome: str, **extras):
        limpo = normalizar(nome)
        if not limpo:
            raise ValueError(f"{cls.__name__}: nome vazio")

        # Sem caixa; a primeira grafia vista e a que fica gravada.
        existente = session.scalars(
            select(cls).where(db.func.upper(cls.nome) == limpo.upper())
        ).first()
        if existente is not None:
            return existente

        novo = cls(nome=limpo, **extras)
        session.add(novo)
        session.flush()
        return novo

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} {self.nome!r}>"


class Fornecedor(_Nomeada, db.Model):
    __tablename__ = "tb_fornecedores"

    nome: Mapped[str] = mapped_column(String(200), nullable=False, unique=True, index=True)


class Natureza(_Nomeada, db.Model):
    """O "tipo" da despesa, na linguagem da planilha."""

    __tablename__ = "tb_naturezas"

    nome: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)


class CentroCusto(_Nomeada, db.Model):
    """O CR_REDUZIDO da planilha. Sem nome informado, o codigo serve de nome."""

    __tablename__ = "tb_centros_custo"

    codigo: Mapped[str] = mapped_column(String(20), nullable=False, unique=True, index=True)
    nome: Mapped[str] = mapped_column(String(200), nullable=False)

    @classmethod
    def obter_ou_criar(cls, session, codigo: str, *, nome: str | None = None):
        limpo = normalizar(codigo)
        if not limpo:
            raise ValueError("CentroCusto: codigo vazio")

        existente = session.scalars(select(cls).where(cls.codigo == limpo)).first()
        if existente is not None:
            if nome and existente.nome == existente.codigo:
                existente.nome = normalizar(nome)
            return existente

        novo = cls(codigo=limpo, nome=normalizar(nome) or limpo)
        session.add(novo)
        session.flush()
        return novo
