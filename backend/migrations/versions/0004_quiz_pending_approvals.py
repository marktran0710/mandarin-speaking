"""Add custom_stories.quiz_pending_approvals — the currently-checked
candidate keys (word/kind/poolIndex) in the Quiz Review page's opt-in
approve-checkbox flow, keyed by difficulty tier like quiz_exclusions and
quiz_approved_snapshot. Nullable: a story with no in-progress review simply
has nothing checked yet. Distinct from quiz_approved_snapshot (0003), which
only changes when "Approve & Publish" actually runs — this column just lets
a teacher's in-progress checkbox selections survive a page reload.

Revision ID: 0004
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "custom_stories",
        sa.Column("quiz_pending_approvals", postgresql.JSONB),
    )


def downgrade() -> None:
    op.drop_column("custom_stories", "quiz_pending_approvals")
