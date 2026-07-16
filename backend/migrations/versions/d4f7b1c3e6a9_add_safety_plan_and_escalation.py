"""add safety_plans and escalation_steps tables

Revision ID: d4f7b1c3e6a9
Revises: c3e6a9b2d4f7
Create Date: 2026-07-15 20:25:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4f7b1c3e6a9'
down_revision: Union[str, None] = 'c3e6a9b2d4f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'safety_plans',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('tenant_id', sa.String(length=36), nullable=False),
        sa.Column('member_id', sa.String(length=36), nullable=False),
        sa.Column('warning_signs', sa.Text(), nullable=False, server_default=''),
        sa.Column('coping_strategies', sa.Text(), nullable=False, server_default=''),
        sa.Column('support_contacts', sa.Text(), nullable=False, server_default=''),
        sa.Column('means_restriction', sa.Text(), nullable=False, server_default=''),
        sa.Column('notes', sa.Text(), nullable=False, server_default=''),
        sa.Column('updated_by', sa.String(length=36), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.ForeignKeyConstraint(['member_id'], ['members.id']),
        sa.ForeignKeyConstraint(['updated_by'], ['staff_users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('member_id'),
    )
    op.create_index('ix_safety_plans_tenant_id', 'safety_plans', ['tenant_id'])
    op.create_index('ix_safety_plans_member_id', 'safety_plans', ['member_id'])

    op.create_table(
        'escalation_steps',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('tenant_id', sa.String(length=36), nullable=False),
        sa.Column('care_gap_id', sa.String(length=36), nullable=False),
        sa.Column('step_key', sa.String(length=64), nullable=False),
        sa.Column('completed', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('completed_by', sa.String(length=36), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.ForeignKeyConstraint(['care_gap_id'], ['care_gaps.id']),
        sa.ForeignKeyConstraint(['completed_by'], ['staff_users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('care_gap_id', 'step_key', name='uq_gap_step'),
    )
    op.create_index('ix_escalation_steps_tenant_id', 'escalation_steps', ['tenant_id'])
    op.create_index('ix_escalation_steps_care_gap_id', 'escalation_steps', ['care_gap_id'])


def downgrade() -> None:
    op.drop_index('ix_escalation_steps_care_gap_id', table_name='escalation_steps')
    op.drop_index('ix_escalation_steps_tenant_id', table_name='escalation_steps')
    op.drop_table('escalation_steps')
    op.drop_index('ix_safety_plans_member_id', table_name='safety_plans')
    op.drop_index('ix_safety_plans_tenant_id', table_name='safety_plans')
    op.drop_table('safety_plans')
