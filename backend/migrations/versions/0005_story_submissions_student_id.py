"""Add story_submissions.student_id.

Submissions were joined to a student only by student_name (free-typed,
collision-prone), unlike vocab_quiz_attempts which already carries a
student_id alongside the name. Same nullable, non-FK shape as that table's
column (0001): legacy submissions and free-typed-name logins carry NULL.

Revision ID: 0005
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("story_submissions", sa.Column("student_id", sa.Text))
    op.create_index(
        "ix_story_submissions_story_student",
        "story_submissions",
        ["story_id", "student_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_story_submissions_story_student", table_name="story_submissions")
    op.drop_column("story_submissions", "student_id")
