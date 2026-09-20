"""Widen student_vocab_srs schedule columns from DATE to TIMESTAMPTZ.

The SM-2 scheduler (analytics/srs.py) moved from calendar-date scheduling to
real ``datetime`` instants so a "day" can be compressed to minutes/hours for
fast manual/demo testing via the dev-only ``SRS_DAY_SECONDS`` setting (see
routers/vocab_quiz_parts/part_001.py). A DATE column truncates to midnight
regardless of what the application sends, which would silently discard that
sub-day precision — so the columns need real timestamp precision even though
production (the default 86400s "day") keeps behaving identically.

Existing DATE values are cast to midnight UTC on upgrade, matching how the
application already treated a bare date beforehand.
"""

from alembic import op
import sqlalchemy as sa


revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "student_vocab_srs", "due_on",
        type_=sa.DateTime(timezone=True),
        postgresql_using="due_on::timestamp AT TIME ZONE 'UTC'",
    )
    op.alter_column(
        "student_vocab_srs", "last_reviewed_on",
        type_=sa.DateTime(timezone=True),
        postgresql_using="last_reviewed_on::timestamp AT TIME ZONE 'UTC'",
    )


def downgrade() -> None:
    op.alter_column(
        "student_vocab_srs", "due_on",
        type_=sa.Date,
        postgresql_using="(due_on AT TIME ZONE 'UTC')::date",
    )
    op.alter_column(
        "student_vocab_srs", "last_reviewed_on",
        type_=sa.Date,
        postgresql_using="(last_reviewed_on AT TIME ZONE 'UTC')::date",
    )
