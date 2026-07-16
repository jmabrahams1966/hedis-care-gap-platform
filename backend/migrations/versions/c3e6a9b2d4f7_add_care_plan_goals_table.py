"""add care_plan_goals table

Revision ID: c3e6a9b2d4f7
Revises: b1d4f6a8c2e5
Create Date: 2026-07-15 20:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3e6a9b2d4f7'
down_revision: Union[str, None] = 'b1d4f6a8c2e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'care_plan_goals',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('tenant_id', sa.String(length=36), nullable=False),
        sa.Column('member_id', sa.String(length=36), nullable=False),
        sa.Column('care_gap_id', sa.String(length=36), nullable=True),
        sa.Column('goal_text', sa.Text(), nullable=False),          # encrypted at app layer
        sa.Column('interventions_text', sa.Text(), nullable=False, server_default=''),
        sa.Column('target_date', sa.String(length=10), nullable=True),
        sa.Column('status', sa.String(length=16), nullable=False, server_default='open'),
        sa.Column('created_by', sa.String(length=36), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.ForeignKeyConstraint(['member_id'], ['members.id']),
        sa.ForeignKeyConstraint(['care_gap_id'], ['care_gaps.id']),
        sa.ForeignKeyConstraint(['created_by'], ['staff_users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_care_plan_goals_tenant_id', 'care_plan_goals', ['tenant_id'])
    op.create_index('ix_care_plan_goals_member_id', 'care_plan_goals', ['member_id'])


def downgrade() -> None:
    op.drop_index('ix_care_plan_goals_member_id', table_name='care_plan_goals')
    op.drop_index('ix_care_plan_goals_tenant_id', table_name='care_plan_goals')
    op.drop_table('care_plan_goals')
