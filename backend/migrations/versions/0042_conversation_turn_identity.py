"""Persist optional conversation turn identity without changing scoring.

Legacy rows remain valid because every new column is nullable. Conversation
progress uses ``turn_id`` in its deterministic key at the application layer;
legacy scene progress keeps the existing scene-index key.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0042"
down_revision = "0041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("audio_records", sa.Column("conversation_id", sa.Text))
    op.add_column("audio_records", sa.Column("turn_id", sa.Text))
    op.add_column("audio_records", sa.Column("turn_index", sa.Integer))
    op.create_index(
        "ix_audio_records_student_conversation_turn",
        "audio_records",
        ["student_id", "conversation_id", "turn_index"],
    )

    op.add_column("speaking_progress", sa.Column("conversation_id", sa.Text))
    op.add_column("speaking_progress", sa.Column("turn_id", sa.Text))
    op.add_column("speaking_progress", sa.Column("turn_index", sa.Integer))

    op.add_column(
        "custom_stories",
        sa.Column("conversation_turns", postgresql.JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("custom_stories", "conversation_turns")
    op.drop_column("speaking_progress", "turn_index")
    op.drop_column("speaking_progress", "turn_id")
    op.drop_column("speaking_progress", "conversation_id")
    op.drop_index(
        "ix_audio_records_student_conversation_turn",
        table_name="audio_records",
    )
    op.drop_column("audio_records", "turn_index")
    op.drop_column("audio_records", "turn_id")
    op.drop_column("audio_records", "conversation_id")
