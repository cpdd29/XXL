from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260408_0013"
down_revision = "20260407_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_execution_jobs",
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("task_id", sa.String(length=64), nullable=False),
        sa.Column("workflow_id", sa.String(length=128), nullable=False),
        sa.Column("execution_agent_id", sa.String(length=128), nullable=True),
        sa.Column("available_at", sa.String(length=128), nullable=False),
        sa.Column("step_delay_seconds", sa.Float(), nullable=True),
        sa.Column("worker_id", sa.String(length=128), nullable=True),
        sa.Column("claimed_at", sa.String(length=128), nullable=True),
        sa.Column("lease_expires_at", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.String(length=128), nullable=False),
        sa.Column("updated_at", sa.String(length=128), nullable=False),
        sa.PrimaryKeyConstraint("run_id"),
    )
    op.create_index(
        op.f("ix_agent_execution_jobs_available_at"),
        "agent_execution_jobs",
        ["available_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_execution_jobs_task_id"),
        "agent_execution_jobs",
        ["task_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_execution_jobs_workflow_id"),
        "agent_execution_jobs",
        ["workflow_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_agent_execution_jobs_workflow_id"),
        table_name="agent_execution_jobs",
    )
    op.drop_index(
        op.f("ix_agent_execution_jobs_task_id"),
        table_name="agent_execution_jobs",
    )
    op.drop_index(
        op.f("ix_agent_execution_jobs_available_at"),
        table_name="agent_execution_jobs",
    )
    op.drop_table("agent_execution_jobs")
