"""Initial schema — the six tables migrated off SQLite.

Design notes:
  * Timestamp-ish columns stay TEXT. Most are client-supplied ISO strings
    already; the DB-generated created_at defaults reproduce SQLite's exact
    'YYYY-MM-DD HH:MM:SS' format so ORDER BY created_at DESC keeps sorting
    migrated rows and new rows in one consistent sequence.
  * The JSON columns become JSONB (validated on write, indexable, and
    directly updatable with jsonb_set).
  * published/linear/first_frame_is_example become real BOOLEANs; the
    row_to_* helpers already wrap them in bool() so the API shape is
    unchanged.

Revision ID: 0001
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

# Byte-identical to SQLite's CURRENT_TIMESTAMP output.
SQLITE_STYLE_NOW = sa.text("to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS')")


def upgrade() -> None:
    op.create_table(
        "audio_records",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("timestamp", sa.Text, nullable=False),
        sa.Column("duration", sa.Integer, nullable=False),
        sa.Column("transcription", sa.Text, nullable=False, server_default=""),
        sa.Column("model", sa.Text, nullable=False),
        sa.Column("topic_id", sa.Text),
        sa.Column("image_url", sa.Text),
        sa.Column("image_index", sa.Integer),
        sa.Column("audio_url", sa.Text),
        sa.Column("praat_metrics", postgresql.JSONB),
        sa.Column("created_at", sa.Text, nullable=False, server_default=SQLITE_STYLE_NOW),
    )
    op.create_index("ix_audio_records_created_at", "audio_records", [sa.text("created_at DESC")])

    op.create_table(
        "custom_stories",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("learning_goal", sa.Text, nullable=False),
        sa.Column("frames", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("published", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.Text, nullable=False, server_default=SQLITE_STYLE_NOW),
        sa.Column("linear", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("lesson_number", sa.Integer),
        sa.Column("narrative_mode", sa.Text, nullable=False, server_default="story"),
        sa.Column("first_frame_is_example", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("quiz_exclusions", postgresql.JSONB),
    )
    # The student topic list filters on published, then groups by lesson.
    op.create_index(
        "ix_custom_stories_published_lesson",
        "custom_stories",
        ["published", "lesson_number"],
    )
    # Lets analytics reach into frames (e.g. which stories contain a word)
    # without deserialising every 34 KB blob in Python.
    op.create_index(
        "ix_custom_stories_frames_gin",
        "custom_stories",
        ["frames"],
        postgresql_using="gin",
    )

    op.create_table(
        "help_requests",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("student_name", sa.Text, nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default="open"),
        sa.Column("created_at", sa.Text, nullable=False),
        sa.Column("resolved_at", sa.Text),
    )

    op.create_table(
        "story_submissions",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("story_id", sa.Text, nullable=False),
        sa.Column("story_title", sa.Text, nullable=False),
        sa.Column("student_name", sa.Text, nullable=False),
        sa.Column("submitted_at", sa.Text, nullable=False),
        sa.Column("scenes", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("created_at", sa.Text, nullable=False, server_default=SQLITE_STYLE_NOW),
        sa.Column("concatenated_audio_url", sa.Text),
        sa.Column("story_feedback", postgresql.JSONB),
    )
    op.create_index("ix_story_submissions_story_id", "story_submissions", ["story_id"])

    op.create_table(
        "vocab_quiz_attempts",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("story_id", sa.Text, nullable=False),
        sa.Column("student_name", sa.Text, nullable=False),
        sa.Column("completed_at", sa.Text, nullable=False),
        sa.Column("total_questions", sa.Integer, nullable=False),
        sa.Column("correct_count", sa.Integer, nullable=False),
        sa.Column("total_time_ms", sa.Integer, nullable=False),
        sa.Column("question_results", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("created_at", sa.Text, nullable=False, server_default=SQLITE_STYLE_NOW),
        sa.Column("mode", sa.Text),
        # Deliberately NOT a foreign key to students.id: legacy attempts
        # recorded before the roster existed carry NULL or a stale id, and a
        # constraint would reject the historical data this app still analyses.
        sa.Column("student_id", sa.Text),
    )
    op.create_index(
        "ix_vocab_quiz_attempts_story_student",
        "vocab_quiz_attempts",
        ["story_id", "student_id"],
    )

    op.create_table(
        "students",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("name", sa.Text, nullable=False, unique=True),
        sa.Column("created_at", sa.Text, nullable=False, server_default=SQLITE_STYLE_NOW),
        # Plaintext by design — a classroom friction gate, not a security
        # boundary. Carried over verbatim from the SQLite schema.
        sa.Column("password", sa.Text, nullable=False, server_default="123456"),
    )
    # The roster lookup is case-insensitive (SQLite used COLLATE NOCASE);
    # Postgres has no such collation, so queries use lower(name) and this
    # index makes them cheap.
    op.create_index("ix_students_lower_name", "students", [sa.text("lower(name)")])


def downgrade() -> None:
    op.drop_table("students")
    op.drop_table("vocab_quiz_attempts")
    op.drop_table("story_submissions")
    op.drop_table("help_requests")
    op.drop_table("custom_stories")
    op.drop_table("audio_records")
