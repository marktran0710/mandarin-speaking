"""Retire the legacy per-story Quiz Review material pipeline.

The canonical quiz source is ``custom_stories.vocab_assessment``.  The old
exclusion/approval snapshots and frame-level AI pools are no longer part of
the content contract, so remove them from both the relational schema and the
embedded frame JSON.
"""

from alembic import op


revision = "0050"
down_revision = "0049"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE custom_stories AS stories
        SET frames = COALESCE(cleaned.frames, '[]'::jsonb)
        FROM (
            SELECT source.id,
                   jsonb_agg(
                       frame - 'vocabularyDistractors'
                             - 'vocabularyCloze'
                             - 'vocabularySynonym'
                       ORDER BY item.ordinality
                   ) AS frames
            FROM custom_stories AS source
            CROSS JOIN LATERAL jsonb_array_elements(
                CASE
                    WHEN jsonb_typeof(source.frames) = 'array' THEN source.frames
                    ELSE '[]'::jsonb
                END
            ) WITH ORDINALITY AS item(frame, ordinality)
            GROUP BY source.id
        ) AS cleaned
        WHERE stories.id = cleaned.id
        """
    )
    op.drop_column("custom_stories", "quiz_exclusions")
    op.drop_column("custom_stories", "quiz_material_snapshot")
    op.drop_column("custom_stories", "quiz_approved_snapshot")
    op.drop_column("custom_stories", "quiz_pending_approvals")


def downgrade() -> None:
    raise RuntimeError("Legacy quiz material cannot be restored automatically.")
