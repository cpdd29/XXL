from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260407_0012"
down_revision = "20260407_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workflow_execution_jobs",
        sa.Column("run_id", sa.String(length=128), nullable=False),
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
        op.f("ix_workflow_execution_jobs_available_at"),
        "workflow_execution_jobs",
        ["available_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_workflow_execution_jobs_available_at"),
        table_name="workflow_execution_jobs",
    )
    op.drop_table("workflow_execution_jobs")
