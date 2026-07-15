"""add staff TOTP MFA fields

Revision ID: a1e9c7d43b52
Revises: f5d2b8c1a3e7
Create Date: 2026-07-07 15:55:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1e9c7d43b52'
down_revision: Union[str, None] = 'f5d2b8c1a3e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('staff_users', sa.Column('mfa_secret', sa.String(length=64), nullable=True))
    op.add_column(
        'staff_users',
        sa.Column('mfa_enabled', sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column('staff_users', 'mfa_enabled')
    op.drop_column('staff_users', 'mfa_secret')
