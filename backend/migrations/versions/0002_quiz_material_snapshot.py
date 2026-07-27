"""Add custom_stories.quiz_material_snapshot — the full per-word quiz
material tree captured at the teacher's last "Save marks" on the Quiz
Review page, so the page can diff live material against it and flag new
vs. changed vs. kept pools. Nullable: existing rows and stories that have
never been reviewed simply skip the diff.

Revision ID: 0002
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "custom_stories",
        sa.Column("quiz_material_snapshot", postgresql.JSONB),
    )


def downgrade() -> None:
    op.drop_column("custom_stories", "quiz_material_snapshot")
