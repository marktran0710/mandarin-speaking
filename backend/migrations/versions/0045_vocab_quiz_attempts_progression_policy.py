"""Research Policy Layer, Epic 3, Task 3.4: stamp each vocab_quiz_attempts
row with the progression policy that actually applied when it was recorded.

Nullable and additive only - existing rows are untouched (null means
"recorded before this column existed", which the API layer treats as
production_accuracy, the only policy that has ever applied historically).
Stamped server-side at write time (see routers/vocab_quiz_attempts.py),
never trusted from the client, per the plan's "Do not infer the policy
only from frontend state."
"""

from alembic import op
import sqlalchemy as sa


revision = "0045"
down_revision = "0044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("vocab_quiz_attempts", sa.Column("progression_policy", sa.Text))
    op.add_column("vocab_quiz_attempts", sa.Column("research_study_id", sa.Text))


def downgrade() -> None:
    op.drop_column("vocab_quiz_attempts", "research_study_id")
    op.drop_column("vocab_quiz_attempts", "progression_policy")
