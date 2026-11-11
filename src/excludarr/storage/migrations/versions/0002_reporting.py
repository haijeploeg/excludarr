"""Add decision evidence and detailed history outcomes."""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("queue", sa.Column("evidence", sa.JSON))
    op.add_column("history", sa.Column("evidence", sa.JSON))
    op.add_column("history", sa.Column("size_bytes", sa.Integer))
    op.add_column("history", sa.Column("side_effect_errors", sa.JSON))


def downgrade() -> None:
    op.drop_column("history", "side_effect_errors")
    op.drop_column("history", "size_bytes")
    op.drop_column("history", "evidence")
    op.drop_column("queue", "evidence")
