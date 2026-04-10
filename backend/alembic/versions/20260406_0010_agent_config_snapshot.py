from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260406_0010"
down_revision = "20260406_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("agents") as batch_op:
        batch_op.add_column(sa.Column("config_snapshot", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("agents") as batch_op:
        batch_op.drop_column("config_snapshot")
