"""a data de baixa entra na chave natural

Revision ID: d3e6a9c24f58
Revises: c2d5f8b13e47
Create Date: 2026-09-11 15:20:00.000000

"""
import sqlalchemy as sa
from alembic import op

revision = 'd3e6a9c24f58'
down_revision = 'c2d5f8b13e47'
branch_labels = None
depends_on = None

ANTIGA = 'referencia, fornecedor_id, natureza_id, centro_custo_id, documento, md5(historico)'
NOVA = (
    'referencia, data_baixa, fornecedor_id, natureza_id, centro_custo_id, '
    'documento, md5(historico)'
)


def upgrade():
    # A chave nova é mais permissiva que a antiga (uma coluna a mais), então
    # nada que passava antes pode passar a colidir. Recriar basta.
    op.execute('DROP INDEX uq_despesa_natural')
    op.execute(f'CREATE UNIQUE INDEX uq_despesa_natural ON tb_despesas ({NOVA})')


def downgrade():
    conexao = op.get_bind()
    duplicadas = conexao.execute(
        sa.text(
            f'SELECT count(*) FROM (SELECT 1 FROM tb_despesas '
            f'GROUP BY {ANTIGA} HAVING count(*) > 1) AS d'
        )
    ).scalar()
    if duplicadas:
        raise RuntimeError(
            f'{duplicadas} grupo(s) passariam a colidir sem a data de baixa na '
            'chave. Resolva antes de voltar esta migração.'
        )

    op.execute('DROP INDEX uq_despesa_natural')
    op.execute(f'CREATE UNIQUE INDEX uq_despesa_natural ON tb_despesas ({ANTIGA})')
