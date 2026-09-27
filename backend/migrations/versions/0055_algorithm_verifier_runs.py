"""Persist isolated development runs for the admin Algorithm Verifier."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0055"
down_revision = "0054"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "algorithm_verifier_runs",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("student_id", sa.Text, nullable=False),
        sa.Column("fixture_story_id", sa.Text, nullable=False),
        sa.Column("fixture_revision", sa.Text, nullable=False),
        sa.Column("configuration", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("simulated_now", sa.Text, nullable=False),
        sa.Column("step_position", sa.Integer, nullable=False, server_default="0"),
        sa.Column("status", sa.Text, nullable=False, server_default="READY"),
        sa.Column("report", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.Text, nullable=False),
        sa.Column("updated_at", sa.Text, nullable=False),
    )
    op.create_index("ix_algorithm_verifier_runs_student", "algorithm_verifier_runs", ["student_id"])


def downgrade() -> None:
    op.drop_index("ix_algorithm_verifier_runs_student", table_name="algorithm_verifier_runs")
    op.drop_table("algorithm_verifier_runs")
