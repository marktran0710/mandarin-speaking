"""Remove unused custom-story metadata fields.

The application now derives story behavior from the frames and lesson order;
these four columns are no longer part of the custom-story contract.
"""
from __future__ import annotations

from alembic import op


revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for column in ("learning_goal", "narrative_mode", "linear", "first_frame_is_example"):
        op.drop_column("custom_stories", column)


def downgrade() -> None:
    raise RuntimeError("Downgrade is not supported after removing custom-story metadata")
