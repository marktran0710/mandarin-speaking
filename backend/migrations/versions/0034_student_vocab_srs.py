"""Per-word spaced-repetition schedule (SM-2), separate from BKT mastery.

Holds the SM-2 state for each (student, word): repetition count, ease factor,
interval, and the next due date. This is a SCHEDULING table only — it decides
when a word resurfaces for review. BKT mastery (``student_vocab_mastery``) is
untouched and remains the sole source of the ``p_learned`` grade.

Kept in its own table (not columns on student_vocab_mastery) so the scheduler
is cleanly separable from the mastery model.

Chains after 0033 (the quiz_level round-key relabel) — the head in this line of
work. If the spaced-repetition feature ships independently of that change,
re-point ``down_revision`` at the then-current head.
"""

from alembic import op
import sqlalchemy as sa


revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "student_vocab_srs",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("student_id", sa.Text, nullable=False),
        sa.Column("word_id", sa.Text, nullable=False),
        sa.Column("reps", sa.Integer, nullable=False, server_default="0"),
        sa.Column("ease", sa.Float, nullable=False, server_default="2.5"),
        sa.Column("interval_days", sa.Integer, nullable=False, server_default="0"),
        sa.Column("due_on", sa.Date),
        sa.Column("last_reviewed_on", sa.Date),
        sa.Column("created_at", sa.Text, nullable=False),
        sa.Column("updated_at", sa.Text, nullable=False),
        sa.UniqueConstraint("student_id", "word_id", name="uq_student_vocab_srs_student_word"),
    )
    # Query pattern: "words due for this student on/before today".
    op.create_index("ix_student_vocab_srs_due", "student_vocab_srs", ["student_id", "due_on"])


def downgrade() -> None:
    op.drop_index("ix_student_vocab_srs_due", table_name="student_vocab_srs")
    op.drop_table("student_vocab_srs")
