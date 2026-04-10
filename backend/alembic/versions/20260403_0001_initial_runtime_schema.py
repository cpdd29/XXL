from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260403_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agents",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("sort_index", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("tasks_completed", sa.Integer(), nullable=False),
        sa.Column("tasks_total", sa.Integer(), nullable=False),
        sa.Column("avg_response_time", sa.String(length=64), nullable=False),
        sa.Column("tokens_used", sa.Integer(), nullable=False),
        sa.Column("tokens_limit", sa.Integer(), nullable=False),
        sa.Column("success_rate", sa.Float(), nullable=False),
        sa.Column("last_active", sa.String(length=128), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.String(length=128), nullable=False),
        sa.Column("sort_index", sa.Integer(), nullable=False),
        sa.Column("timestamp", sa.String(length=128), nullable=False),
        sa.Column("action", sa.String(length=255), nullable=False),
        sa.Column("user", sa.String(length=255), nullable=False),
        sa.Column("resource", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("ip", sa.String(length=128), nullable=False),
        sa.Column("details", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "security_rules",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("sort_index", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("type", sa.String(length=64), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("hit_count", sa.Integer(), nullable=False),
        sa.Column("last_triggered", sa.String(length=128), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "tasks",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("sort_index", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("priority", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.String(length=128), nullable=False),
        sa.Column("completed_at", sa.String(length=128), nullable=True),
        sa.Column("agent", sa.String(length=255), nullable=False),
        sa.Column("tokens", sa.Integer(), nullable=False),
        sa.Column("duration", sa.String(length=128), nullable=True),
        sa.Column("workflow_id", sa.String(length=128), nullable=True),
        sa.Column("workflow_run_id", sa.String(length=128), nullable=True),
        sa.Column("trace_id", sa.String(length=128), nullable=True),
        sa.Column("channel", sa.String(length=64), nullable=True),
        sa.Column("session_id", sa.String(length=128), nullable=True),
        sa.Column("user_key", sa.String(length=255), nullable=True),
        sa.Column("preferred_language", sa.String(length=32), nullable=True),
        sa.Column("detected_lang", sa.String(length=32), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "task_steps",
        sa.Column("id", sa.String(length=128), nullable=False),
        sa.Column("task_id", sa.String(length=64), nullable=False),
        sa.Column("sort_index", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("agent", sa.String(length=255), nullable=False),
        sa.Column("started_at", sa.String(length=128), nullable=False),
        sa.Column("finished_at", sa.String(length=128), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("tokens", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_task_steps_task_id"), "task_steps", ["task_id"], unique=False)
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("sort_index", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("last_login", sa.String(length=128), nullable=False),
        sa.Column("total_interactions", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.String(length=128), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "user_profiles",
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_table(
        "workflows",
        sa.Column("id", sa.String(length=128), nullable=False),
        sa.Column("sort_index", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("updated_at", sa.String(length=128), nullable=False),
        sa.Column("node_count", sa.Integer(), nullable=False),
        sa.Column("edge_count", sa.Integer(), nullable=False),
        sa.Column("trigger", sa.JSON(), nullable=True),
        sa.Column("agent_bindings", sa.JSON(), nullable=False),
        sa.Column("nodes", sa.JSON(), nullable=False),
        sa.Column("edges", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "workflow_runs",
        sa.Column("id", sa.String(length=128), nullable=False),
        sa.Column("sort_index", sa.Integer(), nullable=False),
        sa.Column("workflow_id", sa.String(length=128), nullable=False),
        sa.Column("workflow_name", sa.String(length=255), nullable=False),
        sa.Column("task_id", sa.String(length=64), nullable=False),
        sa.Column("trigger", sa.String(length=255), nullable=False),
        sa.Column("intent", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.String(length=128), nullable=False),
        sa.Column("updated_at", sa.String(length=128), nullable=False),
        sa.Column("started_at", sa.String(length=128), nullable=False),
        sa.Column("completed_at", sa.String(length=128), nullable=True),
        sa.Column("next_dispatch_at", sa.String(length=128), nullable=True),
        sa.Column("dispatch_failure_count", sa.Integer(), nullable=False),
        sa.Column("last_dispatch_error", sa.Text(), nullable=True),
        sa.Column("dispatcher_id", sa.String(length=128), nullable=True),
        sa.Column("dispatch_claimed_at", sa.String(length=128), nullable=True),
        sa.Column("dispatch_lease_expires_at", sa.String(length=128), nullable=True),
        sa.Column("current_stage", sa.String(length=255), nullable=False),
        sa.Column("active_edges", sa.JSON(), nullable=False),
        sa.Column("nodes", sa.JSON(), nullable=False),
        sa.Column("logs", sa.JSON(), nullable=False),
        sa.Column("memory_hits", sa.Integer(), nullable=False),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_workflow_runs_task_id"), "workflow_runs", ["task_id"], unique=False)
    op.create_index(op.f("ix_workflow_runs_workflow_id"), "workflow_runs", ["workflow_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_workflow_runs_workflow_id"), table_name="workflow_runs")
    op.drop_index(op.f("ix_workflow_runs_task_id"), table_name="workflow_runs")
    op.drop_table("workflow_runs")
    op.drop_table("workflows")
    op.drop_table("user_profiles")
    op.drop_table("users")
    op.drop_index(op.f("ix_task_steps_task_id"), table_name="task_steps")
    op.drop_table("task_steps")
    op.drop_table("tasks")
    op.drop_table("security_rules")
    op.drop_table("audit_logs")
    op.drop_table("agents")
