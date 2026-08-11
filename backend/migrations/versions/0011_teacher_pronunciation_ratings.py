"""Add teacher_pronunciation_ratings — the minimal teacher-validation table.

Two logically distinct sections live in one row, per
`stable_experimental_teacher_validation_audit.md` PART I/F:

  A. the published pronunciation rubric (consonant/vowel/tone 0/1,
     accuracy/fluency/prosody 1-5) -- an INDEPENDENT human judgment,
     never derived from or pre-filled by F1/E2/legacy system output;
  B. a research-only "System Feedback Evaluation" section
     (retry_recommended, feedback_appropriateness) -- filled only in
     Stage 2, after Stage 1 is already saved, and never conflated with A.

`rating_stage` distinguishes the two submissions (a teacher submits Stage 1
first, then -- once unlocked -- Stage 2 as a SEPARATE row, not an update to
the same row, so both remain independently queryable).

Identity columns deliberately reuse existing identifiers rather than
duplicating them: `participant_id` = `students.id`; `item_id` =
`"{topic_id}:{scene_index}"`; `session_id`/`attempt_id` = the same values
now persisted on `audio_records` (migration 0010). `audio_record_id`
points at the exact playable recording. None of `character`/
`expected_tone`/`accepted_surface_tones`/the audio URL are duplicated here
-- all are already reachable via `audio_record_id` ->
`audio_records.praat_metrics`.

Not a foreign-key-enforced schema, matching this repo's existing
`student_id`/`topic_id` convention (`speaking_progress`, `audio_records`):
a rating for an attempt whose audio row is later removed must stay
readable, the same reasoning already applied to every other loosely-typed
identity column in this database.

The UNIQUE index treats a NULL `syllable_index` (sentence-level ratings)
as one consistent value via COALESCE, so two sentence-level submissions
from the SAME teacher for the SAME attempt+stage collide (upsert target),
while two DIFFERENT teachers' rows for the identical attempt+syllable+stage
never collide with each other -- "never overwrite one teacher's result with
another."

Revision ID: 0011
"""
from alembic import op
import sqlalchemy as sa

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

SQLITE_STYLE_NOW = sa.text("to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS')")


def upgrade() -> None:
    op.create_table(
        "teacher_pronunciation_ratings",
        sa.Column("rating_id", sa.Text, primary_key=True),
        sa.Column("teacher_id", sa.Text, nullable=False),

        sa.Column("audio_record_id", sa.Text, nullable=False),
        sa.Column("participant_id", sa.Text, nullable=False),
        sa.Column("session_id", sa.Text),
        sa.Column("item_id", sa.Text, nullable=False),
        sa.Column("attempt_id", sa.Text, nullable=False),
        sa.Column("syllable_index", sa.Integer),  # NULL = sentence-level rating

        # A. Published pronunciation rubric (Stage 1, blind, independent).
        sa.Column("consonant_score", sa.SmallInteger),  # 0/1, syllable-level
        sa.Column("vowel_score", sa.SmallInteger),      # 0/1, syllable-level
        sa.Column("tone_score", sa.SmallInteger),       # 0/1, syllable-level
        sa.Column("accuracy_score", sa.SmallInteger),   # 1-5, sentence-level
        sa.Column("fluency_score", sa.SmallInteger),    # 1-5, sentence-level
        sa.Column("prosody_score", sa.SmallInteger),    # 1-5, sentence-level

        # B. System Feedback Evaluation (Stage 2, research-only, distinct from A).
        sa.Column("retry_recommended", sa.Boolean),
        sa.Column("feedback_appropriateness", sa.Text),  # APPROPRIATE / PARTIALLY_APPROPRIATE / INAPPROPRIATE

        sa.Column("rating_stage", sa.Text, nullable=False),  # stage_1_blind / stage_2_feedback_review
        sa.Column("created_at", sa.Text, nullable=False, server_default=SQLITE_STYLE_NOW),
    )

    op.create_index(
        "ux_teacher_rating_unique",
        "teacher_pronunciation_ratings",
        ["teacher_id", "attempt_id", sa.text("COALESCE(syllable_index, -1)"), "rating_stage"],
        unique=True,
    )
    op.create_index(
        "ix_teacher_rating_attempt",
        "teacher_pronunciation_ratings",
        ["participant_id", "session_id", "item_id", "attempt_id"],
    )
    op.create_index(
        "ix_teacher_rating_audio_record",
        "teacher_pronunciation_ratings",
        ["audio_record_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_teacher_rating_audio_record", table_name="teacher_pronunciation_ratings")
    op.drop_index("ix_teacher_rating_attempt", table_name="teacher_pronunciation_ratings")
    op.drop_index("ux_teacher_rating_unique", table_name="teacher_pronunciation_ratings")
    op.drop_table("teacher_pronunciation_ratings")
