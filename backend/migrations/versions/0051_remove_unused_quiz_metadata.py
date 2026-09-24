"""Remove unused workbook metadata from canonical vocabulary questions.

The quiz runtime only needs the validated question fields plus the canonical
round ``level``. Workbook provenance and teaching labels were never consumed
by the student quiz, so remove them from existing JSONB assessment rows too.
"""

from alembic import op


revision = "0051"
down_revision = "0050"
branch_labels = None
depends_on = None

_REMOVED_KEYS = (
    "tier",
    "skillLabel",
    "contextSource",
    "fullContextSentence",
    "pdfPage",
    "bookPage",
)


def upgrade() -> None:
    removed_keys_sql = " - ".join(f"'{key}'" for key in _REMOVED_KEYS)
    op.execute(
        f"""
        UPDATE custom_stories AS stories
        SET vocab_assessment = cleaned.questions
        FROM (
            SELECT source.id,
                   COALESCE(
                       jsonb_agg(question - {removed_keys_sql} ORDER BY item.ordinality),
                       '[]'::jsonb
                   ) AS questions
            FROM custom_stories AS source
            CROSS JOIN LATERAL jsonb_array_elements(
                CASE
                    WHEN jsonb_typeof(source.vocab_assessment) = 'array'
                        THEN source.vocab_assessment
                    ELSE '[]'::jsonb
                END
            ) WITH ORDINALITY AS item(question, ordinality)
            GROUP BY source.id
        ) AS cleaned
        WHERE stories.id = cleaned.id
          AND jsonb_typeof(stories.vocab_assessment) = 'array'
        """
    )


def downgrade() -> None:
    raise RuntimeError("Removed quiz metadata cannot be restored automatically.")
