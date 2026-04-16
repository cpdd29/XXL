from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260415_0015"
down_revision = "20260408_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "workflow_dispatch_jobs",
        sa.Column("protocol", sa.JSON(), nullable=True),
    )
    op.add_column(
        "workflow_execution_jobs",
        sa.Column("protocol", sa.JSON(), nullable=True),
    )
    op.add_column(
        "agent_execution_jobs",
        sa.Column("protocol", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("agent_execution_jobs", "protocol")
    op.drop_column("workflow_execution_jobs", "protocol")
    op.drop_column("workflow_dispatch_jobs", "protocol")
