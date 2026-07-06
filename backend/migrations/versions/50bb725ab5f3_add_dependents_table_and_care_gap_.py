"""add dependents table and care_gap dependent_id

Revision ID: 50bb725ab5f3
Revises: c4524f2e16f1
Create Date: 2026-07-06 01:25:56.435265

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '50bb725ab5f3'
down_revision: Union[str, None] = 'c4524f2e16f1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('dependents',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('tenant_id', sa.String(length=36), nullable=False),
    sa.Column('guardian_member_id', sa.String(length=36), nullable=False),
    sa.Column('external_dependent_id', sa.String(length=128), nullable=False),
    sa.Column('first_name', sa.String(length=128), nullable=False),
    sa.Column('last_name', sa.String(length=128), nullable=False),
    sa.Column('date_of_birth', sa.String(length=10), nullable=False),
    sa.Column('sex', sa.String(length=1), nullable=False),
    sa.Column('alias', sa.String(length=32), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['guardian_member_id'], ['members.id'], ),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tenant_id', 'external_dependent_id', name='uq_tenant_external_dependent')
    )
    op.create_index(op.f('ix_dependents_external_dependent_id'), 'dependents', ['external_dependent_id'], unique=False)
    op.create_index(op.f('ix_dependents_guardian_member_id'), 'dependents', ['guardian_member_id'], unique=False)
    op.create_index(op.f('ix_dependents_tenant_id'), 'dependents', ['tenant_id'], unique=False)

    # Batch mode: SQLite can't ALTER/DROP constraints directly (only supported
    # via copy-and-move), while Postgres handles these as plain ALTER TABLE —
    # batch mode is the portable way to write both in one migration.
    with op.batch_alter_table('care_gaps', schema=None) as batch_op:
        batch_op.add_column(sa.Column('dependent_id', sa.String(length=36), nullable=True))
        batch_op.drop_constraint('uq_member_measure_period', type_='unique')
        batch_op.create_index(batch_op.f('ix_care_gaps_dependent_id'), ['dependent_id'], unique=False)
        batch_op.create_index(
            'uq_dependent_measure_period', ['dependent_id', 'measure_code', 'period'], unique=True,
            sqlite_where=sa.text('dependent_id IS NOT NULL'), postgresql_where=sa.text('dependent_id IS NOT NULL'),
        )
        batch_op.create_index(
            'uq_member_measure_period_no_dependent', ['member_id', 'measure_code', 'period'], unique=True,
            sqlite_where=sa.text('dependent_id IS NULL'), postgresql_where=sa.text('dependent_id IS NULL'),
        )
        batch_op.create_foreign_key(
            'fk_care_gaps_dependent_id_dependents', 'dependents', ['dependent_id'], ['id']
        )


def downgrade() -> None:
    with op.batch_alter_table('care_gaps', schema=None) as batch_op:
        batch_op.drop_constraint('fk_care_gaps_dependent_id_dependents', type_='foreignkey')
        batch_op.drop_index(
            'uq_member_measure_period_no_dependent',
            sqlite_where=sa.text('dependent_id IS NULL'), postgresql_where=sa.text('dependent_id IS NULL'),
        )
        batch_op.drop_index(
            'uq_dependent_measure_period',
            sqlite_where=sa.text('dependent_id IS NOT NULL'), postgresql_where=sa.text('dependent_id IS NOT NULL'),
        )
        batch_op.drop_index(batch_op.f('ix_care_gaps_dependent_id'))
        batch_op.create_unique_constraint('uq_member_measure_period', ['member_id', 'measure_code', 'period'])
        batch_op.drop_column('dependent_id')

    op.drop_index(op.f('ix_dependents_tenant_id'), table_name='dependents')
    op.drop_index(op.f('ix_dependents_guardian_member_id'), table_name='dependents')
    op.drop_index(op.f('ix_dependents_external_dependent_id'), table_name='dependents')
    op.drop_table('dependents')
