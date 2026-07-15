"""add member_exclusions table for HEDIS exclusions

Revision ID: e4c1a7b2f6d3
Revises: d3b8e1f5a9c2
Create Date: 2026-07-07 13:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e4c1a7b2f6d3'
down_revision: Union[str, None] = 'd3b8e1f5a9c2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'member_exclusions',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('tenant_id', sa.String(length=36), nullable=False),
        sa.Column('member_id', sa.String(length=36), nullable=False),
        sa.Column('exclusion_code', sa.String(length=64), nullable=False),
        sa.Column('reference', sa.String(length=255), nullable=False, server_default=''),
        sa.Column('source', sa.String(length=32), nullable=False, server_default='claim'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['member_id'], ['members.id']),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'member_id', 'exclusion_code', name='uq_member_exclusion'),
    )
    op.create_index('ix_member_exclusions_tenant_id', 'member_exclusions', ['tenant_id'])
    op.create_index('ix_member_exclusions_member_id', 'member_exclusions', ['member_id'])
    op.create_index('ix_member_exclusions_member', 'member_exclusions', ['member_id'])


def downgrade() -> None:
    op.drop_index('ix_member_exclusions_member', table_name='member_exclusions')
    op.drop_index('ix_member_exclusions_member_id', table_name='member_exclusions')
    op.drop_index('ix_member_exclusions_tenant_id', table_name='member_exclusions')
    op.drop_table('member_exclusions')
