"""marcar despesa para nao sinalizar divergencia

Revision ID: b1c4e7a90d32
Revises: 75dadfe6f5d8
Create Date: 2026-09-11 09:40:00.000000

"""
import sqlalchemy as sa
from alembic import op

revision = 'b1c4e7a90d32'
down_revision = '75dadfe6f5d8'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'tb_despesas',
        sa.Column(
            'divergencia_ignorada',
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    # O filtro "somente divergentes" passa a ler esta coluna junto dos valores.
    op.create_index(
        'ix_despesas_divergentes',
        'tb_despesas',
        ['data_baixa'],
        unique=False,
        postgresql_where=sa.text(
            'divergencia_ignorada IS FALSE '
            'AND valor_original IS DISTINCT FROM valor_baixado'
        ),
    )


def downgrade():
    op.drop_index('ix_despesas_divergentes', table_name='tb_despesas')
    op.drop_column('tb_despesas', 'divergencia_ignorada')
