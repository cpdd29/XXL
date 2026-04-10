from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260404_0005"
down_revision = "20260404_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("workflow_runs") as batch_op:
        batch_op.add_column(sa.Column("message_dispatch_context", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("workflow_runs") as batch_op:
        batch_op.drop_column("message_dispatch_context")
