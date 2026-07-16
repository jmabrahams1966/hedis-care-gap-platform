"""add ai_interactions table (Feature E: KaveraChat AI assist)

Revision ID: b2d5f8a3c6e9
Revises: a1c4e7f2b9d3
Create Date: 2026-07-16 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2d5f8a3c6e9'
down_revision: Union[str, None] = 'a1c4e7f2b9d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'ai_interactions',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('tenant_id', sa.String(length=36), nullable=False),
        sa.Column('surface', sa.String(length=16), nullable=False),
        sa.Column('actor_staff_id', sa.String(length=36), nullable=True),
        sa.Column('member_id', sa.String(length=36), nullable=True),
        sa.Column('model', sa.String(length=128), nullable=False),
        sa.Column('prompt_tokens', sa.Integer(), nullable=True),
        sa.Column('completion_tokens', sa.Integer(), nullable=True),
        sa.Column('latency_ms', sa.Integer(), nullable=True),
        sa.Column('outcome', sa.String(length=16), nullable=False, server_default='generated'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.ForeignKeyConstraint(['actor_staff_id'], ['staff_users.id']),
        sa.ForeignKeyConstraint(['member_id'], ['members.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_ai_interactions_tenant_id', 'ai_interactions', ['tenant_id'])
    op.create_index('ix_ai_interactions_actor_staff_id', 'ai_interactions', ['actor_staff_id'])


def downgrade() -> None:
    op.drop_index('ix_ai_interactions_actor_staff_id', table_name='ai_interactions')
    op.drop_index('ix_ai_interactions_tenant_id', table_name='ai_interactions')
    op.drop_table('ai_interactions')
