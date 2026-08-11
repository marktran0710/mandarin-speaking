"""Add pilot attempt-identity columns to audio_records.

Closes the gap the pilot-readiness/runtime-scorer audits both found: the
research-logging plumbing (`assistive_feedback/research_log.py`) already
generates `session_id`/`attempt_id`/`attempt_number`/`attempt_type` per
request, but nothing persisted them alongside the recording a teacher
screen can actually query/play back — so a teacher rating and the
system's own research-log row for the SAME event had no shared key.

Same nullable, non-FK shape `audio_records.student_id` (0008) already
uses: legacy recordings, and any request that didn't opt into pilot
identity, carry NULL rather than a required backfill value.

`participant_id` is deliberately NOT added here -- `audio_records.
student_id` (0008) already is that field; this migration does not
duplicate it.

Revision ID: 0010
"""
from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("audio_records", sa.Column("session_id", sa.Text))
    op.add_column("audio_records", sa.Column("attempt_id", sa.Text))
    op.add_column("audio_records", sa.Column("attempt_number", sa.Integer))
    op.add_column("audio_records", sa.Column("attempt_type", sa.Text))
    op.create_index("ix_audio_records_attempt_id", "audio_records", ["attempt_id"])
    op.create_index(
        "ix_audio_records_session_item",
        "audio_records",
        ["session_id", "topic_id", "image_index"],
    )


def downgrade() -> None:
    op.drop_index("ix_audio_records_session_item", table_name="audio_records")
    op.drop_index("ix_audio_records_attempt_id", table_name="audio_records")
    op.drop_column("audio_records", "attempt_type")
    op.drop_column("audio_records", "attempt_number")
    op.drop_column("audio_records", "session_id")
