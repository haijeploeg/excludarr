"""Published list snapshots and independent refresh outcomes."""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "list_snapshot",
        sa.Column("slug", sa.String(), primary_key=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("report", sa.JSON(), nullable=True),
        sa.Column("fingerprint", sa.String(), nullable=True),
        sa.Column("successful_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
    )


def downgrade():
    op.drop_table("list_snapshot")
