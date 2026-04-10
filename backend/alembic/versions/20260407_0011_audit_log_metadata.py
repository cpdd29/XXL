from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260407_0011"
down_revision = "20260406_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("audit_logs") as batch_op:
        batch_op.add_column(sa.Column("metadata", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("audit_logs") as batch_op:
        batch_op.drop_column("metadata")
