from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260403_0003"
down_revision = "20260403_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conversation_messages",
        sa.Column("id", sa.String(length=128), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("session_id", sa.String(length=128), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("detected_lang", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.String(length=128), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_conversation_messages_created_at"),
        "conversation_messages",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_conversation_messages_session_id"),
        "conversation_messages",
        ["session_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_conversation_messages_user_id"),
        "conversation_messages",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_conversation_messages_user_id"),
        table_name="conversation_messages",
    )
    op.drop_index(
        op.f("ix_conversation_messages_session_id"),
        table_name="conversation_messages",
    )
    op.drop_index(
        op.f("ix_conversation_messages_created_at"),
        table_name="conversation_messages",
    )
    op.drop_table("conversation_messages")
