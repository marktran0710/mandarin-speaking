"""One story submission per student per lesson, with its context.

Resubmitting a lesson now overwrites the student's existing submission (the
application looks it up by story_id + student_id, which 0005 already
indexes) instead of adding another row, so these columns describe that one
living submission:

- practice_path: which practice path(s) the scenes came from
  ("speaking", "conversation" or "both").
- quiz_scores: each quiz round's latest finished score at submission time.
- submission_count: how many times the student has handed this lesson in.

Existing rows (including historical duplicates) are left as they are; every
new column is nullable or defaulted.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0059"
down_revision = "0058"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("story_submissions", sa.Column("practice_path", sa.Text, nullable=True))
    op.add_column("story_submissions", sa.Column("quiz_scores", postgresql.JSONB, nullable=True))
    op.add_column(
        "story_submissions",
        sa.Column("submission_count", sa.Integer, nullable=False, server_default="1"),
    )


def downgrade() -> None:
    op.drop_column("story_submissions", "submission_count")
    op.drop_column("story_submissions", "quiz_scores")
    op.drop_column("story_submissions", "practice_path")
