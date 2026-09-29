"""Drop two tables no application code reads or writes.

- ``vocab_quiz_irt_cache``: single-row IRT projection cache. Nothing in the
  application populates or reads it any more.
- ``bkt_model_refit_requests``: refit-request queue from 0031 with no writer
  or reader in the application.

``vocab_quiz_irt_cache`` was still referenced by the 0056 trigger function
``reset_changed_vocabulary()`` through dynamic SQL, so dropping the table alone
would make every lesson-vocabulary edit fail with "relation does not exist".
The function is therefore redefined without the IRT block first.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0060"
down_revision = "0059"
branch_labels = None
depends_on = None

_ORIGINS = "evidence_origin IN ('real', 'synthetic', 'legacy_unknown')"

# The 0056 function body; __IRT_BLOCK__ marks the part that touched
# vocab_quiz_irt_cache so upgrade can omit it and downgrade can restore it.
_RESET_FUNCTION_TEMPLATE = r"""
        CREATE OR REPLACE FUNCTION reset_changed_vocabulary() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE
            lesson_scope text[];
            word_ids text[];
            snapshot jsonb := '{}'::jsonb;
            removed jsonb;
            target record;
        BEGIN
            IF vocabulary_learning_content(OLD.vocab_assessment, OLD.frames, OLD.story_vocabulary)
               = vocabulary_learning_content(NEW.vocab_assessment, NEW.frames, NEW.story_vocabulary)
               AND NEW.vocabulary_version <= OLD.vocabulary_version THEN
                NEW.vocabulary_version := OLD.vocabulary_version;
                RETURN NEW;
            END IF;
            NEW.vocabulary_version := OLD.vocabulary_version + 1;
            lesson_scope := ARRAY[OLD.id, 'teacher-' || OLD.id,
                'teacher-' || OLD.id || '-medium', 'teacher-' || OLD.id || '-hard'];
            SELECT COALESCE(array_agg(DISTINCT word_id), ARRAY[]::text[]) INTO word_ids FROM (
                SELECT q->>'wordId' word_id
                FROM jsonb_array_elements(
                    (CASE WHEN jsonb_typeof(OLD.vocab_assessment) = 'array' THEN OLD.vocab_assessment ELSE '[]'::jsonb END)
                    || (CASE WHEN jsonb_typeof(NEW.vocab_assessment) = 'array' THEN NEW.vocab_assessment ELSE '[]'::jsonb END)
                ) q WHERE q->>'wordId' IS NOT NULL
                UNION SELECT word_id FROM vocab_quiz_responses WHERE lesson_id = ANY(lesson_scope)
            ) source;
            -- Measurement events are derived from the attempts and speaking
            -- sessions below. Remove them before those source rows disappear.
            EXECUTE 'WITH removed AS (
                        DELETE FROM learning_measurement_events
                        WHERE topic_id = ANY($1)
                           OR attempt_id IN (
                               SELECT id FROM vocab_quiz_attempts
                               WHERE story_id = ANY($1)
                           )
                        RETURNING *
                    )
                    SELECT COALESCE(jsonb_agg(to_jsonb(removed)), ''[]''::jsonb)
                    FROM removed'
                INTO removed USING lesson_scope;
            snapshot := snapshot || jsonb_build_object('learning_measurement_events', removed);
            FOR target IN SELECT * FROM (VALUES
                ('student_vocab_srs_events', 'word_id', true),
                ('student_vocab_srs', 'word_id', true),
                ('student_vocab_mastery', 'word_id', true),
                ('vocab_quiz_responses', 'lesson_id', false),
                ('vocab_quiz_attempts', 'story_id', false),
                ('speaking_progress', 'topic_id', false),
                ('story_submissions', 'story_id', false)
            ) AS targets(table_name, scope_column, by_word) LOOP
                EXECUTE format(
                    'WITH removed AS (DELETE FROM %I WHERE %I = ANY($1) RETURNING *) '
                    'SELECT COALESCE(jsonb_agg(to_jsonb(removed)), ''[]''::jsonb) FROM removed',
                    target.table_name, target.scope_column
                ) INTO removed USING CASE WHEN target.by_word THEN word_ids ELSE lesson_scope END;
                snapshot := snapshot || jsonb_build_object(target.table_name, removed);
            END LOOP;
            -- These research projections are also observations of the lesson
            -- vocabulary. Keep their historical rows in the same archive so
            -- no stale state can influence a later research request.
            FOR target IN SELECT * FROM (VALUES
                ('vocab_research_bkt_state', 'word_id'),
                ('vocab_research_retention_events', 'word_id'),
                ('vocab_research_retention_state', 'word_id'),
                ('vocab_research_probe_responses', 'word_id'),
                ('vocab_research_policy_events', 'word_id'),
                ('vocab_research_probe_assignments', 'word_id')
            ) AS research_targets(table_name, scope_column) LOOP
                EXECUTE format(
                    'WITH removed AS (DELETE FROM %I WHERE %I = ANY($1) RETURNING *) '
                    'SELECT COALESCE(jsonb_agg(to_jsonb(removed)), ''[]''::jsonb) FROM removed',
                    target.table_name, target.scope_column
                ) INTO removed USING word_ids;
                snapshot := snapshot || jsonb_build_object(target.table_name, removed);
            END LOOP;
__IRT_BLOCK__
            INSERT INTO lesson_vocabulary_reset_archive
                (story_id, vocabulary_version, reason, previous_content, learning_rows)
            VALUES (OLD.id, OLD.vocabulary_version,
                CASE WHEN NEW.vocab_assessment IS DISTINCT FROM OLD.vocab_assessment
                     OR NEW.frames IS DISTINCT FROM OLD.frames
                     OR NEW.story_vocabulary IS DISTINCT FROM OLD.story_vocabulary
                     THEN 'vocabulary_changed' ELSE 'vocabulary_history_reset' END,
                jsonb_build_object('assessment', OLD.vocab_assessment, 'frames', OLD.frames,
                    'storyVocabulary', OLD.story_vocabulary), snapshot);
            RETURN NEW;
        END
        $$;
"""

_IRT_BLOCK = r"""
            -- IRT is a single global projection over quiz responses.
            EXECUTE 'WITH removed AS (DELETE FROM vocab_quiz_irt_cache RETURNING *)
                     SELECT COALESCE(jsonb_agg(to_jsonb(removed)), ''[]''::jsonb)
                     FROM removed'
                INTO removed;
            snapshot := snapshot || jsonb_build_object('vocab_quiz_irt_cache', removed);
"""


def _reset_function(with_irt: bool) -> str:
    return _RESET_FUNCTION_TEMPLATE.replace("__IRT_BLOCK__", _IRT_BLOCK if with_irt else "")


def upgrade() -> None:
    op.execute(_reset_function(with_irt=False))
    op.drop_table("vocab_quiz_irt_cache")
    op.drop_table("bkt_model_refit_requests")


def downgrade() -> None:
    op.create_table(
        "bkt_model_refit_requests",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("evidence_origin", sa.Text, nullable=False),
        sa.Column("requested_by", sa.Text, nullable=True),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default="requested"),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("fit_run_id", sa.Text, nullable=True),
        sa.ForeignKeyConstraint(["fit_run_id"], ["bkt_model_fit_runs.id"], ondelete="RESTRICT"),
        sa.CheckConstraint(_ORIGINS, name="ck_bkt_model_refit_requests_evidence_origin"),
        sa.CheckConstraint("status IN ('requested', 'running', 'completed', 'rejected')", name="ck_bkt_model_refit_requests_status"),
    )
    op.create_table(
        "vocab_quiz_irt_cache",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("student_ability", postgresql.JSONB, nullable=False),
        sa.Column("item_difficulty", postgresql.JSONB, nullable=False),
        sa.Column("student_speed", postgresql.JSONB, nullable=False),
        sa.Column("item_time_intensity", postgresql.JSONB, nullable=False),
        sa.Column("n_responses", sa.Integer, nullable=False),
        sa.Column("fitted_at", sa.Text, nullable=False),
    )
    op.execute(_reset_function(with_irt=True))
