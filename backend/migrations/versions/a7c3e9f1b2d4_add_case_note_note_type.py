"""add case_note.note_type

Revision ID: a7c3e9f1b2d4
Revises: b8f0a1d2c6e4
Create Date: 2026-07-15 19:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7c3e9f1b2d4'
down_revision: Union[str, None] = 'b8f0a1d2c6e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Free-text clinical note category (contact|assessment|safety_check|
    # care_coordination|other). Existing rows default to 'other'.
    op.add_column(
        'case_notes',
        sa.Column('note_type', sa.String(length=32), nullable=False, server_default='other'),
    )


def downgrade() -> None:
    op.drop_column('case_notes', 'note_type')
