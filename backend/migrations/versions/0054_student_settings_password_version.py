"""Add persisted student presentation and password-session settings."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0054"
down_revision = "0053"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "students",
        sa.Column("student_mascot", sa.Text(), nullable=False, server_default="male"),
    )
    op.add_column(
        "students",
        sa.Column("partner_mascot", sa.Text(), nullable=False, server_default="fox"),
    )
    op.add_column(
        "students",
        sa.Column("voice_hint_mode", sa.Text(), nullable=False, server_default="auto"),
    )
    op.add_column(
        "students",
        sa.Column("password_version", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_check_constraint(
        "ck_students_student_mascot",
        "students",
        "student_mascot IN ('male', 'female')",
    )
    op.create_check_constraint(
        "ck_students_partner_mascot",
        "students",
        "partner_mascot IN ('fox', 'male', 'female')",
    )
    op.create_check_constraint(
        "ck_students_voice_hint_mode",
        "students",
        "voice_hint_mode IN ('auto', 'avatar')",
    )
    op.create_check_constraint(
        "ck_students_password_version",
        "students",
        "password_version >= 0",
    )


def downgrade() -> None:
    op.drop_constraint("ck_students_password_version", "students", type_="check")
    op.drop_constraint("ck_students_voice_hint_mode", "students", type_="check")
    op.drop_constraint("ck_students_partner_mascot", "students", type_="check")
    op.drop_constraint("ck_students_student_mascot", "students", type_="check")
    op.drop_column("students", "password_version")
    op.drop_column("students", "voice_hint_mode")
    op.drop_column("students", "partner_mascot")
    op.drop_column("students", "student_mascot")
