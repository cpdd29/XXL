from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260403_0002"
down_revision = "20260403_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workflow_dispatch_jobs",
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("available_at", sa.String(length=128), nullable=False),
        sa.Column("step_delay_seconds", sa.Float(), nullable=True),
        sa.Column("dispatcher_id", sa.String(length=128), nullable=True),
        sa.Column("claimed_at", sa.String(length=128), nullable=True),
        sa.Column("lease_expires_at", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.String(length=128), nullable=False),
        sa.Column("updated_at", sa.String(length=128), nullable=False),
        sa.PrimaryKeyConstraint("run_id"),
    )
    op.create_index(
        op.f("ix_workflow_dispatch_jobs_available_at"),
        "workflow_dispatch_jobs",
        ["available_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_workflow_dispatch_jobs_available_at"),
        table_name="workflow_dispatch_jobs",
    )
    op.drop_table("workflow_dispatch_jobs")
