"""Add the admin-managed placement blueprint and immutable attempt snapshots."""

from alembic import op


revision = "0052"
down_revision = "0051"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE placement_test_blueprints (
            id TEXT PRIMARY KEY,
            revision INTEGER NOT NULL,
            questions JSONB NOT NULL DEFAULT '[]'::jsonb,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE placement_test_attempts (
            id TEXT PRIMARY KEY,
            student_id TEXT NOT NULL,
            blueprint_revision INTEGER NOT NULL,
            question_snapshot JSONB NOT NULL,
            response_snapshot JSONB NOT NULL DEFAULT '[]'::jsonb,
            status TEXT NOT NULL CHECK (status IN ('in_progress', 'completed')),
            started_at TEXT NOT NULL,
            completed_at TEXT,
            total_questions INTEGER NOT NULL,
            correct_count INTEGER,
            total_time_ms INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE INDEX placement_test_attempts_student_idx
        ON placement_test_attempts (student_id, started_at DESC)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS placement_test_attempts_student_idx")
    op.execute("DROP TABLE IF EXISTS placement_test_attempts")
    op.execute("DROP TABLE IF EXISTS placement_test_blueprints")
