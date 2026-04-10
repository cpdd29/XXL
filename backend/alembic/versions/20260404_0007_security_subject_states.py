from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260404_0007"
down_revision = "20260404_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "security_subject_states",
        sa.Column("user_key", sa.String(length=255), nullable=False),
        sa.Column("rate_request_timestamps", sa.JSON(), nullable=False),
        sa.Column("incident_timestamps", sa.JSON(), nullable=False),
        sa.Column("active_penalty", sa.JSON(), nullable=True),
        sa.Column("updated_at", sa.String(length=128), nullable=False),
        sa.PrimaryKeyConstraint("user_key"),
    )


def downgrade() -> None:
    op.drop_table("security_subject_states")
