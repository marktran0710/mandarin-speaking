"""Persist server-owned combined vocabulary review sessions."""

from alembic import op


revision = "0063"
down_revision = "0062"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE vocab_review_sessions (
            id TEXT PRIMARY KEY,
            student_id TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('active', 'completed', 'deferred', 'expired')),
            story_ids TEXT[] NOT NULL DEFAULT '{}',
            slots JSONB NOT NULL DEFAULT '[]'::jsonb,
            responses JSONB NOT NULL DEFAULT '{}'::jsonb,
            expires_at TIMESTAMPTZ NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CHECK (jsonb_typeof(slots) = 'array'),
            CHECK (jsonb_typeof(responses) = 'object')
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_vocab_review_sessions_active_student "
        "ON vocab_review_sessions (student_id) WHERE status = 'active'"
    )
    op.execute(
        "CREATE INDEX ix_vocab_review_sessions_student_updated "
        "ON vocab_review_sessions (student_id, updated_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_vocab_review_sessions_student_updated")
    op.execute("DROP INDEX IF EXISTS uq_vocab_review_sessions_active_student")
    op.execute("DROP TABLE IF EXISTS vocab_review_sessions")
