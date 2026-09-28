"""Version vocabulary and archive/reset every learner when its content changes.

The trigger covers CRUD, spreadsheet imports and direct database updates in
the same transaction. Audio and generated question IDs do not change what is
being learned. Removed learning rows remain in the private reset archive.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0056"
down_revision = "0055"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("custom_stories", sa.Column("vocabulary_version", sa.Integer, nullable=False, server_default="1"))
    op.create_table(
        "lesson_vocabulary_reset_archive",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("story_id", sa.Text, nullable=False),
        sa.Column("vocabulary_version", sa.Integer, nullable=False),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("previous_content", postgresql.JSONB, nullable=False),
        sa.Column("learning_rows", postgresql.JSONB, nullable=False),
        sa.Column("reset_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_vocabulary_reset_story", "lesson_vocabulary_reset_archive", ["story_id"])
    op.execute(r"""
        CREATE FUNCTION vocabulary_learning_content(bank jsonb, scenes jsonb, story_words jsonb)
        RETURNS jsonb LANGUAGE sql IMMUTABLE AS $$
            SELECT jsonb_build_object(
                'assessment', COALESCE((
                    SELECT jsonb_agg(
                        word_content ORDER BY word_content
                    )
                    FROM (
                        SELECT DISTINCT jsonb_build_object(
                            'wordId', COALESCE(q->>'wordId', ''),
                            'targetWord', COALESCE(q->>'targetWord', q->>'word', ''),
                            'pinyin', COALESCE(q->>'pinyin', ''),
                            'meaning', COALESCE(
                                q->>'simpleEnglishMeaning', q->>'meaning',
                                q->>'translation', q->>'correctAnswer', ''
                            ),
                            'pos', COALESCE(q->>'pos', '')
                        ) AS word_content
                        FROM jsonb_array_elements(CASE WHEN jsonb_typeof(bank) = 'array' THEN bank ELSE '[]' END) q
                        WHERE COALESCE(q->>'wordId', q->>'targetWord', q->>'word', '') <> ''
                    ) normalized
                ), '[]'::jsonb),
                'sceneVocabulary', COALESCE((
                    SELECT jsonb_agg(words ORDER BY words::text) FROM (
                        SELECT jsonb_build_object(
                            'vocabulary', COALESCE(f->>'vocabulary', ''),
                            'pinyin', COALESCE(f->>'vocabularyPinyin', ''),
                            'meaning', COALESCE(f->>'vocabularyTranslation', ''),
                            'pos', COALESCE(f->>'vocabularyPos', '')
                        ) words
                        FROM jsonb_array_elements(CASE WHEN jsonb_typeof(scenes) = 'array' THEN scenes ELSE '[]' END) f
                        WHERE COALESCE(f->>'vocabulary', '') <> ''
                    ) source
                ), '[]'::jsonb),
                'storyVocabulary', COALESCE(story_words, '{}'::jsonb)
            )
        $$;

        CREATE FUNCTION reset_changed_vocabulary() RETURNS trigger LANGUAGE plpgsql AS $$
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
            -- IRT is a single global projection over quiz responses.
            EXECUTE 'WITH removed AS (DELETE FROM vocab_quiz_irt_cache RETURNING *)
                     SELECT COALESCE(jsonb_agg(to_jsonb(removed)), ''[]''::jsonb)
                     FROM removed'
                INTO removed;
            snapshot := snapshot || jsonb_build_object('vocab_quiz_irt_cache', removed);
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
        CREATE TRIGGER reset_vocabulary_learning_progress
            BEFORE UPDATE OF vocab_assessment, frames, story_vocabulary, vocabulary_version
            ON custom_stories FOR EACH ROW EXECUTE FUNCTION reset_changed_vocabulary();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER reset_vocabulary_learning_progress ON custom_stories")
    op.execute("DROP FUNCTION reset_changed_vocabulary()")
    op.execute("DROP FUNCTION vocabulary_learning_content(jsonb, jsonb, jsonb)")
    op.drop_index("ix_vocabulary_reset_story", table_name="lesson_vocabulary_reset_archive")
    op.drop_table("lesson_vocabulary_reset_archive")
    op.drop_column("custom_stories", "vocabulary_version")
