"""add conversations and messages tables

Revision ID: a1c4e7f2b9d3
Revises: f6b9d3a1c8e2
Create Date: 2026-07-15 22:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1c4e7f2b9d3'
down_revision: Union[str, None] = 'f6b9d3a1c8e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'conversations',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('tenant_id', sa.String(length=36), nullable=False),
        sa.Column('member_id', sa.String(length=36), nullable=False),
        sa.Column('assigned_staff_id', sa.String(length=36), nullable=True),
        sa.Column('status', sa.String(length=16), nullable=False, server_default='open'),
        sa.Column('crisis_flag', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('last_message_at', sa.DateTime(), nullable=True),
        sa.Column('staff_unread', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('member_unread', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.ForeignKeyConstraint(['member_id'], ['members.id']),
        sa.ForeignKeyConstraint(['assigned_staff_id'], ['staff_users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('member_id'),
    )
    op.create_index('ix_conversations_tenant_id', 'conversations', ['tenant_id'])
    op.create_index('ix_conversations_member_id', 'conversations', ['member_id'])

    op.create_table(
        'messages',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('conversation_id', sa.String(length=36), nullable=False),
        sa.Column('direction', sa.String(length=16), nullable=False),
        sa.Column('channel', sa.String(length=16), nullable=False),
        sa.Column('sender_staff_id', sa.String(length=36), nullable=True),
        sa.Column('body', sa.Text(), nullable=False),  # encrypted at app layer
        sa.Column('delivery_status', sa.String(length=32), nullable=True),
        sa.Column('crisis_flag', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id']),
        sa.ForeignKeyConstraint(['sender_staff_id'], ['staff_users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_messages_conversation_id', 'messages', ['conversation_id'])


def downgrade() -> None:
    op.drop_index('ix_messages_conversation_id', table_name='messages')
    op.drop_table('messages')
    op.drop_index('ix_conversations_member_id', table_name='conversations')
    op.drop_index('ix_conversations_tenant_id', table_name='conversations')
    op.drop_table('conversations')
