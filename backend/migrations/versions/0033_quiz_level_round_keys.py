"""Rename vocab_quiz_responses.quiz_level values to round keys.

The three-round diagnostic dimension used the labels ``easy``/``medium``/``hard``
in ``quiz_level``, a separate axis from ``quiz_mode`` (tier1/tier2/tier3). Those
two axes are now unified: ``quiz_level`` stores the round key ``tier1``/``tier2``/
``tier3`` (matching ``quiz_mode``), so no code path speaks in easy/medium/hard.

This is a pure value relabel — one-to-one, order-preserving — so a BKT replay
over the relabelled rows yields identical mastery: the analytics only uses
``quiz_level`` as a filter for "is this a diagnostic round", and that filter is
updated to the new keys in lockstep with this migration.

The quiz bank (``custom_stories.vocab_assessment[].level``) keeps its own
difficulty labels — it is owned by the quiz generate/approve pipeline and is
translated to a round key at read time, not renamed here.

Chained after 0032 (the story-text tier removal).
"""

from alembic import op
import sqlalchemy as sa


revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


_TO_ROUND = {"easy": "tier1", "medium": "tier2", "hard": "tier3"}
_TO_LABEL = {round_key: label for label, round_key in _TO_ROUND.items()}


def _remap(mapping: dict[str, str]) -> None:
    bind = op.get_bind()
    total = 0
    for src, dst in mapping.items():
        result = bind.execute(
            sa.text(
                "UPDATE vocab_quiz_responses SET quiz_level = :dst "
                "WHERE lower(quiz_level) = :src"
            ),
            {"src": src, "dst": dst},
        )
        total += result.rowcount or 0
    print(f"Relabelled quiz_level on {total} vocab_quiz_responses rows.")


def upgrade() -> None:
    _remap(_TO_ROUND)


def downgrade() -> None:
    _remap(_TO_LABEL)
