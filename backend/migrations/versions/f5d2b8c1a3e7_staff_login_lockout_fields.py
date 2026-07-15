"""add staff login lockout fields

Revision ID: f5d2b8c1a3e7
Revises: e4c1a7b2f6d3
Create Date: 2026-07-07 15:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f5d2b8c1a3e7'
down_revision: Union[str, None] = 'e4c1a7b2f6d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'staff_users',
        sa.Column('failed_login_count', sa.Integer(), nullable=False, server_default='0'),
    )
    op.add_column('staff_users', sa.Column('locked_until', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('staff_users', 'locked_until')
    op.drop_column('staff_users', 'failed_login_count')
