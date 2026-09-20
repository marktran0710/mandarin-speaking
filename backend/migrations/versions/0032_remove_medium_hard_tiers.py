"""Remove the Medium/Hard story difficulty tiers.

Stories are now single-tier (the textbook-grounded Easy version). This strips
every ``*Medium``/``*Hard`` field baked into ``custom_stories.frames`` and the
``medium``/``hard`` keys of ``story_vocabulary``, and deletes any legacy rows
that were keyed under a ``-medium``/``-hard`` presentation id.

The three-round vocabulary diagnostic is unaffected: its rounds are tagged in
``quiz_level`` (easy/medium/hard = know_it/say_it/use_it) and ``quiz_mode``
(tier1/tier2/tier3), a different axis from the story text tier. This migration
therefore NEVER filters vocab responses by ``quiz_level`` — only by a
``-medium``/``-hard`` suffix on the story/lesson/quiz id — so the say_it/use_it
round evidence is preserved.

``quiz_approved_snapshot`` / ``quiz_pending_approvals`` (keyed by tier) are left
untouched: the quiz approve/publish pipeline owns those columns, and their
stale medium/hard keys are harmless dead data until that pipeline stops writing
them.

Chained after 0031 (the BKT calibration/provenance head) so it composes with
that work rather than colliding with its 0030 revision.
"""

from alembic import op
import sqlalchemy as sa


revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    # Rows recorded under a legacy -medium/-hard presentation id. Current
    # attempts/responses pool under the canonical base id, so on a normal
    # database these match nothing; the deletes only clean environments that
    # still hold suffixed ids from before the app pooled them.
    responses = bind.execute(sa.text(
        """
        DELETE FROM vocab_quiz_responses
        WHERE lesson_id LIKE '%-medium' OR lesson_id LIKE '%-hard'
           OR quiz_id LIKE '%-medium' OR quiz_id LIKE '%-hard'
        """
    ))
    attempts = bind.execute(sa.text(
        """
        DELETE FROM vocab_quiz_attempts
        WHERE story_id LIKE '%-medium' OR story_id LIKE '%-hard'
        """
    ))
    stories = bind.execute(sa.text(
        """
        DELETE FROM custom_stories
        WHERE id LIKE '%-medium' OR id LIKE '%-hard'
        """
    ))

    # Strip every *Medium/*Hard field from each frame, preserving frame order
    # and every non-tier field. A frame always keeps its Easy keys, so the
    # per-frame object is never emptied to NULL.
    bind.execute(sa.text(
        """
        UPDATE custom_stories cs
        SET frames = COALESCE(rebuilt.frames, '[]'::jsonb)
        FROM (
            SELECT s.id,
                   jsonb_agg(
                       COALESCE(
                           (SELECT jsonb_object_agg(kv.key, kv.value)
                            FROM jsonb_each(f.frame) AS kv
                            WHERE kv.key !~ '(Medium|Hard)$'),
                           '{}'::jsonb
                       )
                       ORDER BY f.ord
                   ) AS frames
            FROM custom_stories s
            CROSS JOIN LATERAL jsonb_array_elements(s.frames)
                WITH ORDINALITY AS f(frame, ord)
            WHERE jsonb_typeof(s.frames) = 'array'
            GROUP BY s.id
        ) AS rebuilt
        WHERE cs.id = rebuilt.id
        """
    ))

    # Drop the tiered vocabulary pools; the Easy pool stays under its own keys.
    vocab = bind.execute(sa.text(
        """
        UPDATE custom_stories
        SET story_vocabulary = story_vocabulary - 'medium' - 'hard'
        WHERE jsonb_typeof(story_vocabulary) = 'object'
          AND story_vocabulary ?| array['medium', 'hard']
        """
    ))

    print(
        "Removed Medium/Hard tiers: "
        f"{stories.rowcount} suffixed stories, {attempts.rowcount} suffixed attempts, "
        f"{responses.rowcount} suffixed responses deleted; "
        f"{vocab.rowcount} stories had tiered vocabulary pools stripped."
    )


def downgrade() -> None:
    # Destructive content cleanup; the removed tier fields/rows are not
    # recoverable from the remaining single-tier data.
    raise RuntimeError("Medium/Hard story tiers cannot be restored automatically.")
