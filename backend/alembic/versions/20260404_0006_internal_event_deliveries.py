from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260404_0006"
down_revision = "20260404_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "internal_event_deliveries",
        sa.Column("id", sa.String(length=128), nullable=False),
        sa.Column("event_name", sa.String(length=255), nullable=False),
        sa.Column("source", sa.String(length=255), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("triggered_count", sa.Integer(), nullable=False),
        sa.Column("triggered_workflow_ids", sa.JSON(), nullable=False),
        sa.Column("triggered_run_ids", sa.JSON(), nullable=False),
        sa.Column("triggered_task_ids", sa.JSON(), nullable=False),
        sa.Column("primary_workflow", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.String(length=128), nullable=False),
        sa.Column("updated_at", sa.String(length=128), nullable=False),
        sa.Column("delivered_at", sa.String(length=128), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    op.create_index(
        "ix_internal_event_deliveries_event_name",
        "internal_event_deliveries",
        ["event_name"],
        unique=False,
    )
    op.create_index(
        "ix_internal_event_deliveries_idempotency_key",
        "internal_event_deliveries",
        ["idempotency_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_internal_event_deliveries_idempotency_key", table_name="internal_event_deliveries")
    op.drop_index("ix_internal_event_deliveries_event_name", table_name="internal_event_deliveries")
    op.drop_table("internal_event_deliveries")
