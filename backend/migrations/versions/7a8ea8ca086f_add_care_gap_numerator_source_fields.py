"""add care gap numerator source fields

Revision ID: 7a8ea8ca086f
Revises: 50bb725ab5f3
Create Date: 2026-07-06 02:54:21.063395

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7a8ea8ca086f'
down_revision: Union[str, None] = '50bb725ab5f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Existing rows need a value before we can enforce NOT NULL — every gap
    # created before this migration was, by definition, evaluated from a
    # member's self-report (claims confirmation didn't exist yet), so
    # 'self_report'/'unconfirmed' backfills correctly rather than just being
    # a placeholder.
    op.add_column(
        'care_gaps',
        sa.Column('numerator_source', sa.String(length=32), nullable=False, server_default='unconfirmed'),
    )
    op.add_column(
        'care_gaps',
        sa.Column('numerator_source_reference', sa.String(length=255), nullable=False, server_default=''),
    )
    op.execute("UPDATE care_gaps SET numerator_source = 'self_report' WHERE numerator_met = true")
    with op.batch_alter_table('care_gaps', schema=None) as batch_op:
        batch_op.alter_column('numerator_source', server_default=None)
        batch_op.alter_column('numerator_source_reference', server_default=None)


def downgrade() -> None:
    op.drop_column('care_gaps', 'numerator_source_reference')
    op.drop_column('care_gaps', 'numerator_source')
