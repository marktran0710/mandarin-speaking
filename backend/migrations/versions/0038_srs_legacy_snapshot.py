"""Allow and backfill legacy SRS projection snapshots."""

from alembic import op


revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 0036 was already applied in some databases before legacy snapshots were
    # introduced. Replace the old check constraint in an additive migration so
    # those databases can accept the same baseline event as fresh installs.
    op.drop_constraint(
        "ck_student_vocab_srs_events_type",
        "student_vocab_srs_events",
        type_="check",
    )
    op.create_check_constraint(
        "ck_student_vocab_srs_events_type",
        "student_vocab_srs_events",
        "event_type IN ('enrollment', 'maintenance_success', 'maintenance_failure', 'legacy_snapshot')",
    )
    # A projection that predates the event table still needs an explicit,
    # non-answer starting point for audit/replay. The NOT EXISTS guard makes
    # this safe for fresh databases where 0036 already inserted the snapshot.
    op.execute(
        """
        INSERT INTO student_vocab_srs_events
            (student_id, word_id, source_response_id, event_type,
             correct, quality, old_reps, new_reps, old_ease, new_ease,
             old_interval_days, new_interval_days, old_due_on, new_due_on,
             algorithm_version, occurred_at)
        SELECT schedule.student_id, schedule.word_id,
               'legacy-snapshot:' || schedule.student_id || ':' || schedule.word_id,
               'legacy_snapshot', NULL, NULL,
               0, schedule.reps, 2.5, schedule.ease, 0, schedule.interval_days,
               NULL, schedule.due_on, 'legacy-snapshot-v1', CURRENT_TIMESTAMP
        FROM student_vocab_srs AS schedule
        WHERE NOT EXISTS (
            SELECT 1
            FROM student_vocab_srs_events AS event
            WHERE event.student_id = schedule.student_id
              AND event.word_id = schedule.word_id
              AND event.event_type = 'legacy_snapshot'
        )
        ON CONFLICT (student_id, word_id, source_response_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM student_vocab_srs_events
        WHERE event_type = 'legacy_snapshot'
        """
    )
    op.drop_constraint(
        "ck_student_vocab_srs_events_type",
        "student_vocab_srs_events",
        type_="check",
    )
    op.create_check_constraint(
        "ck_student_vocab_srs_events_type",
        "student_vocab_srs_events",
        "event_type IN ('enrollment', 'maintenance_success', 'maintenance_failure')",
    )
