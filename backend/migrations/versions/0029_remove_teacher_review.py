"""Remove the retired teacher pronunciation-review data surface."""

from alembic import op


revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("teacher_pronunciation_ratings")
    # These indexes belonged to retired pilot/review queries or duplicate a
    # stronger unique lookup. Keep the underlying columns for compatibility,
    # but stop paying write/storage cost for indexes with no live consumer.
    op.drop_index("ix_audio_records_attempt_id", table_name="audio_records")
    op.drop_index("ix_audio_records_session_item", table_name="audio_records")
    op.drop_index("ix_custom_stories_frames_gin", table_name="custom_stories")
    op.drop_index("ix_learning_events_student_attempt", table_name="learning_measurement_events")
    op.drop_index("ix_students_lower_name", table_name="students")


def downgrade() -> None:
    raise RuntimeError("The retired teacher pronunciation-review table cannot be restored automatically.")
