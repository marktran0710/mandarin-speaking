"""Remove the unused vocabulary 2x2 experiment without deleting pilot evidence.

Historical migrations remain for upgrades and downgrade reconstruction. Abort
if any experiment data exists; ordinary vocabulary attempts, responses, BKT,
placement and SM-2 data are preserved. Update the vocabulary-reset trigger
before dropping the tables it previously referenced.
"""
from importlib import import_module

from alembic import op

revision = "0062"
down_revision = "0061"
branch_labels = None
depends_on = None

RESEARCH_TABLES = (
    "vocab_research_probe_responses",
    "vocab_research_probe_assignments",
    "vocab_research_assessment_items",
    "vocab_research_policy_events",
    "vocab_research_retention_events",
    "vocab_research_retention_state",
    "vocab_research_bkt_state",
    "vocab_research_assignments",
    "vocab_research_participants",
    "vocab_research_studies",
)

_HISTORICAL_REVISIONS = (
    "0043_vocab_research_studies_and_participants",
    "0044_vocab_research_assignments",
    "0045_vocab_quiz_attempts_progression_policy",
    "0046_vocab_research_bkt_state",
    "0047_vocab_research_retention",
    "0048_vocab_research_probes",
    "0049_vocab_research_policy_events",
)


def _previous_reset_function() -> str:
    previous = import_module("migrations.versions.0060_drop_unused_irt_cache_and_refit_requests")
    return previous._reset_function(with_irt=False)


def _production_reset_function() -> str:
    source = _previous_reset_function()
    start = source.index("            -- These research projections")
    end = source.index("            INSERT INTO lesson_vocabulary_reset_archive", start)
    return source[:start] + source[end:]


def upgrade() -> None:
    # Lock first so an older running process cannot insert between the guard
    # and the drop. No CASCADE: an unexpected dependency must stop removal.
    op.execute("LOCK TABLE " + ", ".join((*RESEARCH_TABLES, "vocab_quiz_attempts", "vocab_quiz_responses")) + " IN ACCESS EXCLUSIVE MODE")
    table_literals = ", ".join(f"'{table}'" for table in RESEARCH_TABLES)
    op.execute(f"""
        DO $$
        DECLARE target text; has_rows boolean;
        BEGIN
            FOREACH target IN ARRAY ARRAY[{table_literals}] LOOP
                EXECUTE format('SELECT EXISTS (SELECT 1 FROM %I)', target) INTO has_rows;
                IF has_rows THEN
                    RAISE EXCEPTION 'Cannot remove 2x2: % contains experiment data', target;
                END IF;
            END LOOP;
            IF EXISTS (SELECT 1 FROM vocab_quiz_responses WHERE research_study_id IS NOT NULL)
               OR EXISTS (SELECT 1 FROM vocab_quiz_attempts
                          WHERE research_study_id IS NOT NULL
                             OR progression_policy NOT IN ('production_accuracy')) THEN
                RAISE EXCEPTION 'Cannot remove 2x2: vocabulary evidence is experiment-linked';
            END IF;
        END $$
    """)
    op.execute(_production_reset_function())
    for table in RESEARCH_TABLES:
        op.drop_table(table)
    op.drop_column("vocab_quiz_responses", "research_study_id")
    op.drop_column("vocab_quiz_attempts", "research_study_id")
    op.drop_column("vocab_quiz_attempts", "progression_policy")


def downgrade() -> None:
    # Only empty experiment structures are removed by upgrade, so there is no
    # research data to restore. Reuse their immutable original definitions.
    for module in _HISTORICAL_REVISIONS:
        import_module("migrations.versions." + module).upgrade()
    op.execute(_previous_reset_function())
