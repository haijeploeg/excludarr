"""Persist daemon state and compact scheduled execution outcomes."""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "daemon_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("instance", sa.String(), nullable=False),
        sa.Column("timezone", sa.String(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("stopped_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "scheduled_job",
        sa.Column("kind", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), primary_key=True),
        sa.Column("instance", sa.String(), nullable=False),
        sa.Column("schedule", sa.String(), nullable=False),
        sa.Column("state", sa.String(), nullable=False),
        sa.Column("next_due", sa.DateTime(timezone=True)),
        sa.Column("pending_due", sa.DateTime(timezone=True)),
        sa.Column("last_dispatched_due", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "job_execution",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("instance", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("outcome", sa.String()),
        sa.Column("error", sa.Text()),
        sa.Column("summary", sa.JSON()),
    )
    op.create_index("ix_job_execution_job", "job_execution", ["kind", "name", "id"])


def downgrade():
    op.drop_table("job_execution")
    op.drop_table("scheduled_job")
    op.drop_table("daemon_state")
