"""add care_tasks table

Revision ID: b1d4f6a8c2e5
Revises: a7c3e9f1b2d4
Create Date: 2026-07-15 19:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b1d4f6a8c2e5'
down_revision: Union[str, None] = 'a7c3e9f1b2d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'care_tasks',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('tenant_id', sa.String(length=36), nullable=False),
        sa.Column('member_id', sa.String(length=36), nullable=False),
        sa.Column('care_gap_id', sa.String(length=36), nullable=True),
        sa.Column('title', sa.String(length=300), nullable=False),
        sa.Column('due_at', sa.DateTime(), nullable=True),
        sa.Column('sla_hours', sa.Integer(), nullable=True),
        sa.Column('assignee_staff_id', sa.String(length=36), nullable=True),
        sa.Column('status', sa.String(length=16), nullable=False, server_default='open'),
        sa.Column('created_by', sa.String(length=36), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.ForeignKeyConstraint(['member_id'], ['members.id']),
        sa.ForeignKeyConstraint(['care_gap_id'], ['care_gaps.id']),
        sa.ForeignKeyConstraint(['assignee_staff_id'], ['staff_users.id']),
        sa.ForeignKeyConstraint(['created_by'], ['staff_users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_care_tasks_tenant_id', 'care_tasks', ['tenant_id'])
    op.create_index('ix_care_tasks_member_id', 'care_tasks', ['member_id'])


def downgrade() -> None:
    op.drop_index('ix_care_tasks_member_id', table_name='care_tasks')
    op.drop_index('ix_care_tasks_tenant_id', table_name='care_tasks')
    op.drop_table('care_tasks')
