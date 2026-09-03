"""Preserve mappable legacy quiz responses in the BKT response ledger."""
from alembic import op
import sqlalchemy as sa


revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inserted = bind.execute(sa.text(
        """
        INSERT INTO vocab_quiz_responses
            (student_id, word_id, word, lesson_id, quiz_id, attempt_id,
             item_id, question_type, selected_answer, correct_answer,
             presented_options, question_prompt, answered_at, bkt_eligible,
             bkt_eligibility_errors, correct, response_time_ms, occurred_at,
             attempt_order, quiz_level, quiz_mode)
        SELECT
            attempt.student_id,
            btrim(response->>'word'),
            btrim(response->>'word'),
            attempt.story_id,
            attempt.id,
            attempt.id,
            COALESCE(NULLIF(btrim(response->>'itemId'), ''),
                     attempt.id || ':' || (ordinality - 1)::text),
            COALESCE(NULLIF(response->>'questionKind', ''), 'legacy'),
            response->>'selectedAnswer',
            response->>'correctAnswer',
            COALESCE(response->'presentedOptions', '[]'::jsonb),
            response->>'questionPrompt',
            response->>'answeredAt',
            FALSE,
            '["HISTORICAL_RESPONSE_NOT_VALIDATED"]'::jsonb,
            (response->>'correct')::boolean,
            CASE WHEN COALESCE(response->>'timeMs', '') ~ '^[0-9]+$'
                 THEN (response->>'timeMs')::integer ELSE 0 END,
            attempt.completed_at,
            (ordinality - 1)::integer,
            response->>'level',
            attempt.mode
        FROM vocab_quiz_attempts AS attempt
        CROSS JOIN LATERAL jsonb_array_elements(
            CASE WHEN jsonb_typeof(attempt.question_results) = 'array'
                 THEN attempt.question_results ELSE '[]'::jsonb END
        ) WITH ORDINALITY AS expanded(response, ordinality)
        WHERE attempt.student_id IS NOT NULL
          AND jsonb_typeof(response) = 'object'
          AND btrim(COALESCE(response->>'word', '')) <> ''
          AND response ? 'correct'
          AND jsonb_typeof(response->'correct') = 'boolean'
        ON CONFLICT (quiz_id, attempt_order) DO NOTHING
        """
    ))
    skipped = bind.execute(sa.text(
        """
        SELECT COUNT(*) AS count
        FROM vocab_quiz_attempts
        WHERE student_id IS NULL
           OR jsonb_typeof(question_results) <> 'array'
        """
    )).scalar_one()
    print(f"BKT legacy response backfill inserted {inserted.rowcount} audit-only rows.")
    if skipped:
        print(f"BKT legacy response backfill skipped {skipped} attempts with no student or response array; review before import.")


def downgrade() -> None:
    # The ledger is append-only and may contain new responses after upgrade.
    # Removing rows by migration provenance would require an origin column, so
    # downgrade intentionally leaves preserved audit history intact.
    pass
