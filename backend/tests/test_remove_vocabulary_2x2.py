"""Removing the dormant experiment preserves ordinary pilot evidence."""
from importlib import import_module

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.pool import NullPool

from conftest import TEST_DATABASE_URL

migration = import_module("migrations.versions.0062_remove_vocabulary_2x2")


@pytest.fixture
def previous_schema():
    # Repository fixtures point at the isolated test DB. All DDL and data in
    # this fixture roll back, including the temporary downgrade structures.
    engine = sa.create_engine(TEST_DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1), poolclass=NullPool)
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            with Operations.context(MigrationContext.configure(connection)):
                migration.downgrade()
                yield connection
        finally:
            transaction.rollback()
    engine.dispose()


def test_upgrade_preserves_pilot_attempts_and_responses(previous_schema):
    connection = previous_schema
    connection.execute(sa.text("""
        INSERT INTO vocab_quiz_attempts
            (id, story_id, student_name, student_id, completed_at,
             total_questions, correct_count, total_time_ms, question_results)
        VALUES ('pilot-attempt', 'lesson', 'Pilot', 'pilot', '2026-10-02', 1, 1, 100, '[]'::jsonb)
    """))
    connection.execute(sa.text("""
        INSERT INTO vocab_quiz_responses
            (student_id, word_id, word, quiz_id, attempt_id, item_id,
             question_type, correct, response_time_ms, attempt_order, response_fingerprint)
        VALUES ('pilot', 'word', 'word', 'pilot-attempt', 'pilot-attempt', 'item',
                'basic_meaning_mcq', TRUE, 100, 0, 'existing-fingerprint')
    """))
    tables = ("students", "vocab_quiz_attempts", "vocab_quiz_responses", "student_vocab_mastery", "student_vocab_srs")

    def snapshot():
        return {table: connection.execute(sa.text(
            f"SELECT (to_jsonb(t) - 'research_study_id' - 'progression_policy')::text "
            f"FROM {table} t ORDER BY 1"
        )).scalars().all() for table in tables}

    before = snapshot()
    migration.upgrade()
    assert snapshot() == before
    assert connection.execute(sa.text("""
        SELECT count(*) FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name LIKE 'vocab_research_%'
    """)).scalar_one() == 0
    assert connection.execute(sa.text("""
        SELECT count(*) FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name IN ('vocab_quiz_attempts', 'vocab_quiz_responses')
          AND column_name IN ('research_study_id', 'progression_policy')
    """)).scalar_one() == 0
    trigger = connection.execute(sa.text("SELECT pg_get_functiondef('reset_changed_vocabulary()'::regprocedure)")).scalar_one()
    assert "vocab_research_" not in trigger


def test_upgrade_refuses_nonempty_experiment(previous_schema):
    connection = previous_schema
    connection.execute(sa.text("""
        INSERT INTO vocab_research_studies
            (id, name, policy_version, assignment_version, created_at)
        VALUES ('keep-study', 'Existing study', 'v1', 'v1', '2026-10-02')
    """))
    with pytest.raises(sa.exc.DBAPIError, match="contains experiment data"):
        with connection.begin_nested():
            migration.upgrade()
    assert connection.execute(sa.text("SELECT id FROM vocab_research_studies")).scalar_one() == "keep-study"


def test_upgrade_refuses_experiment_tagged_attempt_without_study(previous_schema):
    connection = previous_schema
    connection.execute(sa.text("""
        INSERT INTO vocab_quiz_attempts
            (id, story_id, student_name, completed_at, total_questions,
             correct_count, total_time_ms, progression_policy)
        VALUES ('tagged-attempt', 'lesson', 'Pilot', '2026-10-02', 1, 1, 100, 'research_coverage')
    """))
    with pytest.raises(sa.exc.DBAPIError, match="experiment-linked"):
        with connection.begin_nested():
            migration.upgrade()
    assert connection.execute(sa.text("SELECT id FROM vocab_quiz_attempts")).scalar_one() == "tagged-attempt"


def test_experiment_endpoints_are_removed(client):
    for route in client.app.routes:
        assert not getattr(route, "path", "").startswith("/api/research/vocabulary")
