"""Persist versioned learning-measurement events for pilot analytics."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "learning_measurement_events",
        sa.Column("event_id", sa.Text, primary_key=True),
        sa.Column("schema_version", sa.Text, nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("occurred_at", sa.Text, nullable=False),
        sa.Column("student_id", sa.Text),
        sa.Column("class_id", sa.Text),
        sa.Column("session_id", sa.Text),
        sa.Column("attempt_id", sa.Text),
        sa.Column("topic_id", sa.Text),
        sa.Column("scene_index", sa.Integer),
        sa.Column("question_id", sa.Text),
        sa.Column("condition", sa.Text),
        sa.Column("properties", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.Text, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_learning_events_occurred_at", "learning_measurement_events", ["occurred_at"])
    op.create_index("ix_learning_events_student_attempt", "learning_measurement_events", ["student_id", "attempt_id"])


def downgrade() -> None:
    op.drop_index("ix_learning_events_student_attempt", table_name="learning_measurement_events")
    op.drop_index("ix_learning_events_occurred_at", table_name="learning_measurement_events")
    op.drop_table("learning_measurement_events")
