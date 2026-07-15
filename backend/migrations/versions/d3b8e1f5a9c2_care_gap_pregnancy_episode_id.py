"""episode-scope PPC care gaps via care_gaps.pregnancy_episode_id

Revision ID: d3b8e1f5a9c2
Revises: c2a9d4e6f8b1
Create Date: 2026-07-07 12:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd3b8e1f5a9c2'
down_revision: Union[str, None] = 'c2a9d4e6f8b1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Batch mode for SQLite's copy-and-move ALTER; plain ALTER on Postgres.
    with op.batch_alter_table('care_gaps', schema=None) as batch_op:
        batch_op.add_column(sa.Column('pregnancy_episode_id', sa.String(length=36), nullable=True))
        # Narrow the plain-member index so it no longer governs episode-scoped
        # (PPC) gaps — those get their own per-episode uniqueness below, letting
        # a member hold two PPC gaps for two deliveries in one measurement year.
        batch_op.drop_index(
            'uq_member_measure_period_no_dependent',
            sqlite_where=sa.text('dependent_id IS NULL'),
            postgresql_where=sa.text('dependent_id IS NULL'),
        )
        batch_op.create_index(
            'uq_member_measure_period_no_dependent', ['member_id', 'measure_code', 'period'], unique=True,
            sqlite_where=sa.text('dependent_id IS NULL AND pregnancy_episode_id IS NULL'),
            postgresql_where=sa.text('dependent_id IS NULL AND pregnancy_episode_id IS NULL'),
        )
        batch_op.create_index(
            'uq_episode_measure', ['pregnancy_episode_id', 'measure_code'], unique=True,
            sqlite_where=sa.text('pregnancy_episode_id IS NOT NULL'),
            postgresql_where=sa.text('pregnancy_episode_id IS NOT NULL'),
        )
        batch_op.create_foreign_key(
            'fk_care_gaps_pregnancy_episode_id', 'pregnancy_episodes', ['pregnancy_episode_id'], ['id']
        )


def downgrade() -> None:
    with op.batch_alter_table('care_gaps', schema=None) as batch_op:
        batch_op.drop_constraint('fk_care_gaps_pregnancy_episode_id', type_='foreignkey')
        batch_op.drop_index(
            'uq_episode_measure',
            sqlite_where=sa.text('pregnancy_episode_id IS NOT NULL'),
            postgresql_where=sa.text('pregnancy_episode_id IS NOT NULL'),
        )
        batch_op.drop_index(
            'uq_member_measure_period_no_dependent',
            sqlite_where=sa.text('dependent_id IS NULL AND pregnancy_episode_id IS NULL'),
            postgresql_where=sa.text('dependent_id IS NULL AND pregnancy_episode_id IS NULL'),
        )
        batch_op.create_index(
            'uq_member_measure_period_no_dependent', ['member_id', 'measure_code', 'period'], unique=True,
            sqlite_where=sa.text('dependent_id IS NULL'),
            postgresql_where=sa.text('dependent_id IS NULL'),
        )
        batch_op.drop_column('pregnancy_episode_id')
