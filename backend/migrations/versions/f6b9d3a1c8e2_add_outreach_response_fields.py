"""add outreach_attempt cadence provenance + response fields

Revision ID: f6b9d3a1c8e2
Revises: e5a8c2f4b6d1
Create Date: 2026-07-15 21:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f6b9d3a1c8e2'
down_revision: Union[str, None] = 'e5a8c2f4b6d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('outreach_attempts', sa.Column('sequence_id', sa.String(length=36), nullable=True))
    op.add_column('outreach_attempts', sa.Column('step_order', sa.Integer(), nullable=True))
    op.add_column('outreach_attempts', sa.Column('responded_at', sa.DateTime(), nullable=True))
    op.add_column('outreach_attempts', sa.Column('response_type', sa.String(length=32), nullable=True))
    op.create_index('ix_outreach_attempts_sequence_id', 'outreach_attempts', ['sequence_id'])


def downgrade() -> None:
    op.drop_index('ix_outreach_attempts_sequence_id', table_name='outreach_attempts')
    op.drop_column('outreach_attempts', 'response_type')
    op.drop_column('outreach_attempts', 'responded_at')
    op.drop_column('outreach_attempts', 'step_order')
    op.drop_column('outreach_attempts', 'sequence_id')
