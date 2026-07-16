"""add outreach cadence tables + measure sequence_id

Revision ID: e5a8c2f4b6d1
Revises: d4f7b1c3e6a9
Create Date: 2026-07-15 21:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5a8c2f4b6d1'
down_revision: Union[str, None] = 'd4f7b1c3e6a9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'outreach_sequences',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('tenant_id', sa.String(length=36), nullable=True),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('is_default', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_by', sa.String(length=36), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.ForeignKeyConstraint(['created_by'], ['staff_users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_outreach_sequences_tenant_id', 'outreach_sequences', ['tenant_id'])

    op.create_table(
        'sequence_steps',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('sequence_id', sa.String(length=36), nullable=False),
        sa.Column('step_order', sa.Integer(), nullable=False),
        sa.Column('offset_days', sa.Integer(), nullable=False),
        sa.Column('channel', sa.String(length=16), nullable=False),
        sa.Column('template_key', sa.String(length=64), nullable=False),
        sa.Column('recurring', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('repeat_interval_days', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['sequence_id'], ['outreach_sequences.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('sequence_id', 'step_order', name='uq_seq_step_order'),
    )
    op.create_index('ix_sequence_steps_sequence_id', 'sequence_steps', ['sequence_id'])

    op.create_table(
        'sequence_enrollments',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('tenant_id', sa.String(length=36), nullable=False),
        sa.Column('member_id', sa.String(length=36), nullable=False),
        sa.Column('care_gap_id', sa.String(length=36), nullable=True),
        sa.Column('sequence_id', sa.String(length=36), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False, server_default='active'),
        sa.Column('current_step_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('next_send_at', sa.DateTime(), nullable=False),
        sa.Column('ended_by', sa.String(length=36), nullable=True),
        sa.Column('ended_reason', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.ForeignKeyConstraint(['member_id'], ['members.id']),
        sa.ForeignKeyConstraint(['care_gap_id'], ['care_gaps.id']),
        sa.ForeignKeyConstraint(['sequence_id'], ['outreach_sequences.id']),
        sa.ForeignKeyConstraint(['ended_by'], ['staff_users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_sequence_enrollments_tenant_id', 'sequence_enrollments', ['tenant_id'])
    op.create_index('ix_sequence_enrollments_member_id', 'sequence_enrollments', ['member_id'])
    op.create_index('ix_enroll_due', 'sequence_enrollments', ['status', 'next_send_at'])

    op.add_column('tenant_measure_configs', sa.Column('sequence_id', sa.String(length=36), nullable=True))


def downgrade() -> None:
    op.drop_column('tenant_measure_configs', 'sequence_id')
    op.drop_index('ix_enroll_due', table_name='sequence_enrollments')
    op.drop_index('ix_sequence_enrollments_member_id', table_name='sequence_enrollments')
    op.drop_index('ix_sequence_enrollments_tenant_id', table_name='sequence_enrollments')
    op.drop_table('sequence_enrollments')
    op.drop_index('ix_sequence_steps_sequence_id', table_name='sequence_steps')
    op.drop_table('sequence_steps')
    op.drop_index('ix_outreach_sequences_tenant_id', table_name='outreach_sequences')
    op.drop_table('outreach_sequences')
