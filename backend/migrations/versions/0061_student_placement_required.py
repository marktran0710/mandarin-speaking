"""Mark new student accounts as required to take the placement test first.

Every student that exists when this runs keeps ``placement_required = FALSE``,
so nobody who already has an account is gated. The column default is then
switched to TRUE, so every account created afterwards (self-signup or by an
admin, through any code path) must take the placement test before the rest of
Student Mode unlocks.
"""

from alembic import op

revision = "0061"
down_revision = "0060"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE students ADD COLUMN placement_required BOOLEAN NOT NULL DEFAULT FALSE")
    op.execute("ALTER TABLE students ALTER COLUMN placement_required SET DEFAULT TRUE")


def downgrade() -> None:
    op.execute("ALTER TABLE students DROP COLUMN placement_required")
