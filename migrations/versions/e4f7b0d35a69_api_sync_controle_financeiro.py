"""exclusões registradas por trigger e índice para o sync do Controle Financeiro

Revision ID: e4f7b0d35a69
Revises: d3e6a9c24f58
Create Date: 2026-10-06 15:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

from app.models.despesa_excluida import APAGAR_TRIGGER, CRIAR_TRIGGER

revision = 'e4f7b0d35a69'
down_revision = 'd3e6a9c24f58'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'tb_despesas_excluidas',
        sa.Column('despesa_id', sa.Integer(), autoincrement=False, nullable=False),
        sa.Column('excluida_em', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('despesa_id'),
    )
    op.create_index('ix_tb_despesas_excluidas_excluida_em', 'tb_despesas_excluidas', ['excluida_em'])
    op.create_index('ix_despesas_atualizado_em', 'tb_despesas', ['atualizado_em', 'id'])
    op.execute(CRIAR_TRIGGER)


def downgrade():
    op.execute(APAGAR_TRIGGER)
    op.drop_index('ix_despesas_atualizado_em', table_name='tb_despesas')
    op.drop_index('ix_tb_despesas_excluidas_excluida_em', table_name='tb_despesas_excluidas')
    op.drop_table('tb_despesas_excluidas')
