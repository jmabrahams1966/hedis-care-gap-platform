"""add AI triage risk columns to messages and care_gaps (Feature E)

Revision ID: c3f6a9d4b7e2
Revises: b2d5f8a3c6e9
Create Date: 2026-07-16 09:30:00.000000

Additive advisory columns for the AI triage signal. Nullable everywhere — the
deterministic crisis/safety flags (messages.crisis_flag, care_gaps.safety_flag)
are unchanged and remain the source of truth for safety routing.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3f6a9d4b7e2'
down_revision: Union[str, None] = 'b2d5f8a3c6e9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # batch_alter_table for portability: SQLite can't ALTER add columns the same
    # way Postgres does inside a plain op for tables with existing constraints.
    with op.batch_alter_table('messages') as batch:
        batch.add_column(sa.Column('ai_risk_level', sa.String(length=16), nullable=True))
        batch.add_column(sa.Column('ai_risk_rationale', sa.Text(), nullable=True))
    with op.batch_alter_table('care_gaps') as batch:
        batch.add_column(sa.Column('ai_risk_level', sa.String(length=16), nullable=True))
        batch.add_column(sa.Column('ai_risk_rationale', sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('care_gaps') as batch:
        batch.drop_column('ai_risk_rationale')
        batch.drop_column('ai_risk_level')
    with op.batch_alter_table('messages') as batch:
        batch.drop_column('ai_risk_rationale')
        batch.drop_column('ai_risk_level')
