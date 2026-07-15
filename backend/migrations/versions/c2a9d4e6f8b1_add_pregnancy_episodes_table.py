"""add pregnancy_episodes table for PPC measures

Revision ID: c2a9d4e6f8b1
Revises: b1f7c3d9e2a4
Create Date: 2026-07-07 10:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c2a9d4e6f8b1'
down_revision: Union[str, None] = 'b1f7c3d9e2a4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'pregnancy_episodes',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('tenant_id', sa.String(length=36), nullable=False),
        sa.Column('member_id', sa.String(length=36), nullable=False),
        sa.Column('delivery_date', sa.String(length=10), nullable=False),
        sa.Column('estimated_due_date', sa.String(length=10), nullable=False, server_default=''),
        sa.Column('external_episode_id', sa.String(length=128), nullable=True),
        sa.Column('source', sa.String(length=32), nullable=False, server_default='claim'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['member_id'], ['members.id']),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_pregnancy_episodes_tenant_id', 'pregnancy_episodes', ['tenant_id'])
    op.create_index('ix_pregnancy_episodes_member_id', 'pregnancy_episodes', ['member_id'])
    op.create_index('ix_pregnancy_episodes_member', 'pregnancy_episodes', ['member_id'])
    op.create_index(
        'uq_pregnancy_episode_external',
        'pregnancy_episodes',
        ['tenant_id', 'external_episode_id'],
        unique=True,
        sqlite_where=sa.text('external_episode_id IS NOT NULL'),
        postgresql_where=sa.text('external_episode_id IS NOT NULL'),
    )


def downgrade() -> None:
    op.drop_index('uq_pregnancy_episode_external', table_name='pregnancy_episodes')
    op.drop_index('ix_pregnancy_episodes_member', table_name='pregnancy_episodes')
    op.drop_index('ix_pregnancy_episodes_member_id', table_name='pregnancy_episodes')
    op.drop_index('ix_pregnancy_episodes_tenant_id', table_name='pregnancy_episodes')
    op.drop_table('pregnancy_episodes')
