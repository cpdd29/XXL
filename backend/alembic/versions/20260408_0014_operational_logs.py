from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260408_0014"
down_revision = "20260408_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "operational_logs",
        sa.Column("id", sa.String(length=128), nullable=False),
        sa.Column("sort_index", sa.Integer(), nullable=False),
        sa.Column("timestamp", sa.String(length=128), nullable=False),
        sa.Column("type", sa.String(length=64), nullable=False),
        sa.Column("agent", sa.String(length=255), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=128), nullable=False),
        sa.Column("trace_id", sa.String(length=128), nullable=True),
        sa.Column("task_id", sa.String(length=128), nullable=True),
        sa.Column("workflow_run_id", sa.String(length=128), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_operational_logs_task_id"),
        "operational_logs",
        ["task_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_operational_logs_timestamp"),
        "operational_logs",
        ["timestamp"],
        unique=False,
    )
    op.create_index(
        op.f("ix_operational_logs_trace_id"),
        "operational_logs",
        ["trace_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_operational_logs_workflow_run_id"),
        "operational_logs",
        ["workflow_run_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_operational_logs_workflow_run_id"),
        table_name="operational_logs",
    )
    op.drop_index(
        op.f("ix_operational_logs_trace_id"),
        table_name="operational_logs",
    )
    op.drop_index(
        op.f("ix_operational_logs_timestamp"),
        table_name="operational_logs",
    )
    op.drop_index(
        op.f("ix_operational_logs_task_id"),
        table_name="operational_logs",
    )
    op.drop_table("operational_logs")
