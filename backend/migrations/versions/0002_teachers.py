"""Add persistent teacher accounts."""
from alembic import op
import sqlalchemy as sa

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None
SQLITE_STYLE_NOW = sa.text("to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS')")

def upgrade() -> None:
    op.execute("CREATE TABLE IF NOT EXISTS teachers (id TEXT PRIMARY KEY, name TEXT NOT NULL, password TEXT NOT NULL DEFAULT '123456', status TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL DEFAULT to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS'))")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_teachers_lower_name ON teachers (lower(name))")

def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS teachers")
