"""Scope BKT response idempotency and record replay provenance."""

from alembic import op
import sqlalchemy as sa


revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("uq_vocab_quiz_response_order", "vocab_quiz_responses", type_="unique")
    op.create_unique_constraint(
        "uq_vocab_quiz_response_student_quiz_order",
        "vocab_quiz_responses",
        ["student_id", "quiz_id", "attempt_order"],
    )
    op.add_column("vocab_quiz_responses", sa.Column("response_fingerprint", sa.Text, nullable=True))
    op.add_column("student_vocab_mastery", sa.Column("model_version", sa.Text, nullable=True))
    op.add_column("student_vocab_mastery", sa.Column("parameter_fingerprint", sa.Text, nullable=True))


def downgrade() -> None:
    # 0030 deliberately permits two students to use the same generated quiz
    # id/order. Recreating the old global constraint would fail (or force an
    # unsafe data choice) once such valid rows exist.
    duplicate_slots = op.get_bind().execute(sa.text(
        """
        SELECT 1
        FROM vocab_quiz_responses
        GROUP BY quiz_id, attempt_order
        HAVING COUNT(DISTINCT student_id) > 1
        LIMIT 1
        """
    )).first()
    if duplicate_slots is not None:
        raise RuntimeError(
            "Cannot restore the global vocab response uniqueness constraint: "
            "cross-student quiz slots now exist."
        )
    op.drop_column("student_vocab_mastery", "parameter_fingerprint")
    op.drop_column("student_vocab_mastery", "model_version")
    op.drop_column("vocab_quiz_responses", "response_fingerprint")
    op.drop_constraint("uq_vocab_quiz_response_student_quiz_order", "vocab_quiz_responses", type_="unique")
    op.create_unique_constraint("uq_vocab_quiz_response_order", "vocab_quiz_responses", ["quiz_id", "attempt_order"])
