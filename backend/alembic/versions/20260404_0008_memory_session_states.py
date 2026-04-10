from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260404_0008"
down_revision = "20260404_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "memory_session_states",
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("session_id", sa.String(length=128), nullable=False),
        sa.Column("last_distilled_message_created_at", sa.String(length=128), nullable=False),
        sa.Column("last_distilled_message_ids_at_created_at", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.String(length=128), nullable=False),
        sa.PrimaryKeyConstraint("user_id", "session_id"),
    )


def downgrade() -> None:
    op.drop_table("memory_session_states")
