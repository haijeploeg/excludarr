"""initial

Revision ID: 0001
Revises:
"""

import sqlalchemy as sa
from alembic import op

from excludarr.storage.models import UTCDateTime

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "queue",
        sa.Column("rule", sa.String, primary_key=True),
        sa.Column("item_key", sa.String, primary_key=True),
        sa.Column("title", sa.String, nullable=False),
        sa.Column("size_bytes", sa.Integer, nullable=False),
        sa.Column("enqueued_at", UTCDateTime, nullable=False),
        sa.Column("due_at", UTCDateTime, nullable=False),
    )
    op.create_table(
        "exception",
        sa.Column("rule", sa.String, primary_key=True),
        sa.Column("item_key", sa.String, primary_key=True),
        sa.Column("title", sa.String, nullable=False),
        sa.Column("created_at", UTCDateTime, nullable=False),
    )
    op.create_table(
        "history",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("at", UTCDateTime, nullable=False),
        sa.Column("rule", sa.String, nullable=False),
        sa.Column("item_key", sa.String, nullable=False),
        sa.Column("title", sa.String, nullable=False),
        sa.Column("action", sa.String, nullable=False),
        sa.Column("size_freed", sa.Integer, nullable=False),
        sa.Column("ok", sa.Boolean, nullable=False),
        sa.Column("detail", sa.Text, nullable=False),
    )
    op.create_table(
        "cache",
        sa.Column("key", sa.String, primary_key=True),
        sa.Column("value", sa.JSON, nullable=False),
        sa.Column("expires_at", UTCDateTime, nullable=False),
    )


def downgrade() -> None:
    for t in ("cache", "history", "exception", "queue"):
        op.drop_table(t)
