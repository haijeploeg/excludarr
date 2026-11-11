"""Store the time of each successful cache fetch."""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cache", sa.Column("fetched_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    op.drop_column("cache", "fetched_at")
