"""referencia deixa de ser unica sozinha; passa a ser unica com o resto

Revision ID: c2d5f8b13e47
Revises: b1c4e7a90d32
Create Date: 2026-09-11 14:05:00.000000

"""
import sqlalchemy as sa
from alembic import op

revision = 'c2d5f8b13e47'
down_revision = 'b1c4e7a90d32'
branch_labels = None
depends_on = None

NATURAL = (
    'referencia, fornecedor_id, natureza_id, centro_custo_id, documento, md5(historico)'
)


def upgrade():
    conexao = op.get_bind()

    # Se os dados ja violam a chave nova, o CREATE UNIQUE falharia com uma
    # mensagem que nao diz quais linhas. Melhor parar antes e apontar.
    duplicadas = conexao.execute(
        sa.text(
            f'SELECT count(*) FROM (SELECT 1 FROM tb_despesas '
            f'GROUP BY {NATURAL} HAVING count(*) > 1) AS d'
        )
    ).scalar()
    if duplicadas:
        raise RuntimeError(
            f'{duplicadas} grupo(s) de despesas ja repetem a chave natural. '
            'Resolva antes de aplicar: SELECT referencia, fornecedor_id, natureza_id, '
            'centro_custo_id, documento, count(*) FROM tb_despesas GROUP BY 1,2,3,4,5, '
            'md5(historico) HAVING count(*) > 1;'
        )

    op.drop_index('ix_tb_despesas_referencia', table_name='tb_despesas')
    # Continua indexada, so nao mais unica: a busca por referencia depende dela.
    op.create_index('ix_tb_despesas_referencia', 'tb_despesas', ['referencia'], unique=False)
    op.execute(f'CREATE UNIQUE INDEX uq_despesa_natural ON tb_despesas ({NATURAL})')


def downgrade():
    op.execute('DROP INDEX uq_despesa_natural')
    op.drop_index('ix_tb_despesas_referencia', table_name='tb_despesas')
    op.create_index('ix_tb_despesas_referencia', 'tb_despesas', ['referencia'], unique=True)
