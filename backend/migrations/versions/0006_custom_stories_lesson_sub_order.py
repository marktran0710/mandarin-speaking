"""Add custom_stories.lesson_sub_order.

Position of a story within its lesson (1, 2, 3...), for the sequential
in-lesson unlock (5-1 -> 5-2 -> 5-3). Nullable and independent of
lesson_number's own nullability: a story can have a lesson_number with no
sub_order yet (unlocking stays off for that whole lesson until every story
in it has one — see groupTopicsByLesson on the frontend).

Revision ID: 0006
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("custom_stories", sa.Column("lesson_sub_order", sa.Integer))


def downgrade() -> None:
    op.drop_column("custom_stories", "lesson_sub_order")
