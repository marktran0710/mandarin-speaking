"""Make SRS event source identity mandatory and globally unique per response."""

from alembic import op
import sqlalchemy as sa


revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 0036 originally allowed NULL source ids. Give any legacy rows a stable
    # audit-only identity before making the id mandatory; current writers never
    # emit NULL, but old rows must not prevent the schema from tightening.
    op.execute(
        """
        UPDATE student_vocab_srs_events
        SET source_response_id = 'legacy-event:' || id
        WHERE source_response_id IS NULL
        """
    )
    op.execute(
        """
        WITH ranked AS (
            SELECT id,
                   ROW_NUMBER() OVER (
                       PARTITION BY student_id, word_id, source_response_id
                       ORDER BY id
                   ) AS duplicate_rank
            FROM student_vocab_srs_events
            WHERE source_response_id IS NOT NULL
        )
        UPDATE student_vocab_srs_events AS event
        SET source_response_id = event.source_response_id || chr(58) || 'legacy-duplicate' || chr(58) || event.id
        FROM ranked
        WHERE event.id = ranked.id AND ranked.duplicate_rank > 1
        """
    )
    op.drop_constraint(
        "uq_student_vocab_srs_events_source",
        "student_vocab_srs_events",
        type_="unique",
    )
    op.alter_column(
        "student_vocab_srs_events",
        "source_response_id",
        existing_type=sa.Text(),
        nullable=False,
    )
    op.create_unique_constraint(
        "uq_student_vocab_srs_events_source",
        "student_vocab_srs_events",
        ["student_id", "word_id", "source_response_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_student_vocab_srs_events_source",
        "student_vocab_srs_events",
        type_="unique",
    )
    op.alter_column(
        "student_vocab_srs_events",
        "source_response_id",
        existing_type=sa.Text(),
        nullable=True,
    )
    op.create_unique_constraint(
        "uq_student_vocab_srs_events_source",
        "student_vocab_srs_events",
        ["student_id", "word_id", "event_type", "source_response_id"],
    )
