"""widen member/dependent PII columns to hold encrypted values

Revision ID: b8f0a1d2c6e4
Revises: a1e9c7d43b52
Create Date: 2026-07-08 12:45:00.000000

Field-level PII encryption (app/crypto.py) stores base64 AES-SIV ciphertext,
which is longer than the plaintext, so the affected columns are widened to 512.
The existing rows are encrypted in a separate one-off step after this runs (the
EncryptedString type is transition-tolerant, so plaintext rows read fine until
then).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b8f0a1d2c6e4'
down_revision: Union[str, None] = 'a1e9c7d43b52'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_WIDE = sa.String(length=512)


def upgrade() -> None:
    with op.batch_alter_table('members', schema=None) as b:
        b.alter_column('first_name', type_=_WIDE)
        b.alter_column('last_name', type_=_WIDE)
        b.alter_column('date_of_birth', type_=_WIDE)
        b.alter_column('phone', type_=_WIDE)
        b.alter_column('email', type_=_WIDE)
    with op.batch_alter_table('dependents', schema=None) as b:
        b.alter_column('first_name', type_=_WIDE)
        b.alter_column('last_name', type_=_WIDE)
        b.alter_column('date_of_birth', type_=_WIDE)


def downgrade() -> None:
    # Intentionally not narrowing back: once values are encrypted they exceed the
    # old widths, so a narrowing downgrade would truncate/corrupt them.
    pass
