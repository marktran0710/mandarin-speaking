"""Add audio_records.student_id.

Recordings currently have no student attribution, unlike vocab_quiz_attempts
and story_submissions. Same nullable, non-FK shape as those tables' student
columns: legacy recordings and free-typed-name logins carry NULL.

Revision ID: 0008
"""
from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("audio_records", sa.Column("student_id", sa.Text))
    op.create_index("ix_audio_records_student", "audio_records", ["student_id"])


def downgrade() -> None:
    op.drop_index("ix_audio_records_student", table_name="audio_records")
    op.drop_column("audio_records", "student_id")
