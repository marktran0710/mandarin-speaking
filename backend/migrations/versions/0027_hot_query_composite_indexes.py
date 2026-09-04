"""Composite indexes matching the hot list queries' filters + ORDER BY.

The audio, story-submission and vocab-quiz-attempt list endpoints all filter
by student_id / story_id and then ORDER BY a timestamp DESC. Single-column
indexes let Postgres find the rows but still force a separate sort; a composite
that carries the ordering column lets the same index satisfy both the filter
and the ORDER BY (and the DISTINCT ON, for latest-by-scene). Two single-column
indexes are dropped because a new composite's leading column supersedes them.

Non-concurrent CREATE INDEX briefly locks each table against writes while the
index builds - fine at classroom data volumes. For a very large table, rebuild
these with CREATE INDEX CONCURRENTLY out-of-band instead.
"""
from alembic import op
import sqlalchemy as sa


revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # audio_records --------------------------------------------------------
    # list_audio_records: WHERE student_id = ? ORDER BY created_at DESC, id DESC
    op.create_index(
        "ix_audio_records_student_created",
        "audio_records",
        ["student_id", sa.text("created_at DESC"), sa.text("id DESC")],
    )
    # latest-by-scene: WHERE student_id = ? AND topic_id = ?
    #                  ORDER BY image_index, created_at DESC, id DESC (DISTINCT ON image_index)
    op.create_index(
        "ix_audio_records_student_topic_scene",
        "audio_records",
        ["student_id", "topic_id", "image_index", sa.text("created_at DESC"), sa.text("id DESC")],
    )
    # (student_id) alone is now a prefix of ix_audio_records_student_created.
    op.drop_index("ix_audio_records_student", table_name="audio_records")

    # story_submissions ----------------------------------------------------
    op.create_index(
        "ix_story_submissions_student_submitted",
        "story_submissions",
        ["student_id", sa.text("submitted_at DESC")],
    )
    op.create_index(
        "ix_story_submissions_story_submitted",
        "story_submissions",
        ["story_id", sa.text("submitted_at DESC")],
    )
    # (story_id) alone is now a prefix of ix_story_submissions_story_submitted.
    op.drop_index("ix_story_submissions_story_id", table_name="story_submissions")

    # vocab_quiz_attempts --------------------------------------------------
    op.create_index(
        "ix_vocab_quiz_attempts_student_completed",
        "vocab_quiz_attempts",
        ["student_id", sa.text("completed_at DESC")],
    )
    op.create_index(
        "ix_vocab_quiz_attempts_story_completed",
        "vocab_quiz_attempts",
        ["story_id", sa.text("completed_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_vocab_quiz_attempts_story_completed", table_name="vocab_quiz_attempts")
    op.drop_index("ix_vocab_quiz_attempts_student_completed", table_name="vocab_quiz_attempts")

    op.create_index("ix_story_submissions_story_id", "story_submissions", ["story_id"])
    op.drop_index("ix_story_submissions_story_submitted", table_name="story_submissions")
    op.drop_index("ix_story_submissions_student_submitted", table_name="story_submissions")

    op.create_index("ix_audio_records_student", "audio_records", ["student_id"])
    op.drop_index("ix_audio_records_student_topic_scene", table_name="audio_records")
    op.drop_index("ix_audio_records_student_created", table_name="audio_records")
