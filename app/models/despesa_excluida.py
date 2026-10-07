"""Registro de despesas apagadas, para o sync incremental do Controle Financeiro.

A trigger cobre qualquer DELETE (tela, limpeza em massa, SQL direto); a
auditoria não serve porque a limpeza só registra a contagem.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DDL, DateTime, Integer, event, func
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db

CRIAR_TRIGGER = """
CREATE OR REPLACE FUNCTION fn_registrar_despesa_excluida() RETURNS trigger AS $$
BEGIN
    INSERT INTO tb_despesas_excluidas (despesa_id, excluida_em)
    VALUES (OLD.id, now())
    ON CONFLICT (despesa_id) DO UPDATE SET excluida_em = EXCLUDED.excluida_em;
    RETURN OLD;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS tg_despesa_excluida ON tb_despesas;
CREATE TRIGGER tg_despesa_excluida AFTER DELETE ON tb_despesas
    FOR EACH ROW EXECUTE FUNCTION fn_registrar_despesa_excluida();
"""

APAGAR_TRIGGER = """
DROP TRIGGER IF EXISTS tg_despesa_excluida ON tb_despesas;
DROP FUNCTION IF EXISTS fn_registrar_despesa_excluida();
"""


class DespesaExcluida(db.Model):
    __tablename__ = "tb_despesas_excluidas"

    despesa_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    excluida_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )


# Para o create_all dos testes, depois de todas as tabelas (tb_despesas precisa
# existir); em produção quem cria é a migração.
event.listen(db.metadata, "after_create", DDL(CRIAR_TRIGGER))
