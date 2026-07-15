"""add medication_fills table for PDC adherence measures

Revision ID: b1f7c3d9e2a4
Revises: 7a8ea8ca086f
Create Date: 2026-07-06 11:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b1f7c3d9e2a4'
down_revision: Union[str, None] = '7a8ea8ca086f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'medication_fills',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('tenant_id', sa.String(length=36), nullable=False),
        sa.Column('member_id', sa.String(length=36), nullable=False),
        sa.Column('drug_class', sa.String(length=32), nullable=False),
        sa.Column('ndc', sa.String(length=16), nullable=False, server_default=''),
        sa.Column('drug_label', sa.String(length=128), nullable=False, server_default=''),
        sa.Column('fill_date', sa.String(length=10), nullable=False),
        sa.Column('days_supply', sa.Integer(), nullable=False),
        sa.Column('external_claim_id', sa.String(length=128), nullable=True),
        sa.Column('source', sa.String(length=32), nullable=False, server_default='pharmacy_claim'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['member_id'], ['members.id']),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_medication_fills_tenant_id', 'medication_fills', ['tenant_id'])
    op.create_index('ix_medication_fills_member_id', 'medication_fills', ['member_id'])
    op.create_index('ix_medication_fills_member_class', 'medication_fills', ['member_id', 'drug_class'])
    # Partial unique index: dedupe re-ingested fills that carry a claim id, while
    # letting many claim-id-less rows (NULL, not "") coexist.
    op.create_index(
        'uq_medication_fill_claim',
        'medication_fills',
        ['tenant_id', 'external_claim_id'],
        unique=True,
        sqlite_where=sa.text('external_claim_id IS NOT NULL'),
        postgresql_where=sa.text('external_claim_id IS NOT NULL'),
    )


def downgrade() -> None:
    op.drop_index('uq_medication_fill_claim', table_name='medication_fills')
    op.drop_index('ix_medication_fills_member_class', table_name='medication_fills')
    op.drop_index('ix_medication_fills_member_id', table_name='medication_fills')
    op.drop_index('ix_medication_fills_tenant_id', table_name='medication_fills')
    op.drop_table('medication_fills')
