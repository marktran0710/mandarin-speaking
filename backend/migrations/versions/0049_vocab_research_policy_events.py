"""Research Policy Layer, Epic 8 (research logging + admin fidelity), Task 8.1.

Adds ``vocab_research_policy_events``: an append-only log of every
protocol-relevant decision a research orchestration module makes -
assignment consultation, core-round completion, practice/retention/probe
scheduling and completion, and (reserved for future use) detected policy
violations. Nothing before this Epic wrote here; every write comes from
application/research_logging.py's record_policy_event, called from the
existing Epic 3-7 orchestration modules at the moment each event actually
happens, never reconstructed after the fact.

word_id is nullable because not every event is word-scoped (core_completed
and practice_session_created are section/session-level). payload_json
carries event-specific detail, notably a word-scoped event's assignment
condition (C/B/S/BS) computed once by the writer from the same frozen
assignment row it already has in hand - Task 8.2's fidelity metrics read
that back rather than re-joining vocab_research_assignments.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0049"
down_revision = "0048"
branch_labels = None
depends_on = None

_EVENT_TYPES = (
    "assignment_loaded",
    "core_completed",
    "practice_session_created",
    "practice_item_selected",
    "retention_enrolled",
    "review_scheduled",
    "review_yoked",
    "review_completed",
    "probe_assigned",
    "probe_completed",
    "policy_violation",
)


def upgrade() -> None:
    op.create_table(
        "vocab_research_policy_events",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("study_id", sa.Text, sa.ForeignKey("vocab_research_studies.id"), nullable=False),
        sa.Column("student_id", sa.Text, nullable=False),
        sa.Column("event_type", sa.Text, nullable=False),
        sa.Column("word_id", sa.Text),
        sa.Column("payload_json", postgresql.JSONB),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.Text, nullable=False),
        sa.CheckConstraint(
            "event_type IN (" + ", ".join(f"'{event_type}'" for event_type in _EVENT_TYPES) + ")",
            name="ck_vocab_research_policy_events_type",
        ),
    )
    # Query pattern: "how many X events has this study had" (Task 8.2 fidelity).
    op.create_index(
        "ix_vocab_research_policy_events_study_type",
        "vocab_research_policy_events",
        ["study_id", "event_type", "occurred_at"],
    )
    # Query pattern: "this one student's event timeline" (Task 8.4 drill-down).
    op.create_index(
        "ix_vocab_research_policy_events_student",
        "vocab_research_policy_events",
        ["study_id", "student_id", "occurred_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_vocab_research_policy_events_student", table_name="vocab_research_policy_events")
    op.drop_index("ix_vocab_research_policy_events_study_type", table_name="vocab_research_policy_events")
    op.drop_table("vocab_research_policy_events")
