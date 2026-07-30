"""Add review fields to story_submissions.

Teachers can currently read completed submissions but have no way to mark
one as reviewed or leave a follow-up note. These nullable fields keep that
review state alongside each submission; the pending default backfills
existing rows as work that still needs review.

Revision ID: 0009
"""
from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "story_submissions",
        sa.Column(
            "review_status",
            sa.Text,
            nullable=True,
            server_default=sa.text("'pending'"),
        ),
    )
    op.add_column("story_submissions", sa.Column("teacher_note", sa.Text, nullable=True))


def downgrade() -> None:
    op.drop_column("story_submissions", "teacher_note")
    op.drop_column("story_submissions", "review_status")
