"""Persistence boundary for vocab_research_studies / vocab_research_participants.

Pure CRUD only - no policy decisions (those live in
domain/research/policy.py). Every function takes an already-open
connection so the caller controls the transaction boundary.
"""
from typing import Optional


def find_active_participation(db, student_id: str) -> Optional[dict]:
    """The student's participant row joined with its study, if any exists at
    all (regardless of study/participant status - the caller decides what
    "active" means from the raw fields). A student can only ever be in one
    study at a time (no such constraint is enforced yet since only one study
    is expected to run at once in this Epic; enforcing "at most one active
    study per student" is deferred until a second concurrent study is a real
    possibility)."""
    return db.execute(
        """
        SELECT
            p.student_id,
            p.active AS participant_active,
            p.class_id,
            p.sequence_id,
            s.id AS study_id,
            s.status AS study_status,
            s.policy_version,
            s.assignment_version,
            s.config_json
        FROM vocab_research_participants p
        JOIN vocab_research_studies s ON s.id = p.study_id
        WHERE p.student_id = %s
        ORDER BY p.created_at DESC
        LIMIT 1
        """,
        (student_id,),
    ).fetchone()


def insert_study(
    db,
    *,
    id: str,
    name: str,
    status: str,
    config_json: dict,
    policy_version: str,
    assignment_version: str,
    created_at: str,
) -> None:
    from psycopg.types.json import Jsonb

    db.execute(
        """
        INSERT INTO vocab_research_studies
            (id, name, status, config_json, policy_version, assignment_version, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (id, name, status, Jsonb(config_json), policy_version, assignment_version, created_at),
    )


def insert_participant(
    db,
    *,
    study_id: str,
    student_id: str,
    class_id: Optional[str],
    sequence_id: Optional[str],
    active: bool,
    created_at: str,
) -> None:
    db.execute(
        """
        INSERT INTO vocab_research_participants
            (study_id, student_id, class_id, sequence_id, active, created_at)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (study_id, student_id, class_id, sequence_id, active, created_at),
    )


def find_study(db, study_id: str) -> Optional[dict]:
    return db.execute(
        "SELECT * FROM vocab_research_studies WHERE id = %s", (study_id,)
    ).fetchone()


def count_all_participants_for_study(db, study_id: str) -> int:
    """Unlike find_participants_for_study (active-only, Epic 2's roster
    ordering need), this counts every participant row regardless of
    active - Task 8.4's admin summary reports "58 / 60 active"."""
    return db.execute(
        "SELECT COUNT(*) AS total FROM vocab_research_participants WHERE study_id = %s",
        (study_id,),
    ).fetchone()["total"]


def find_participants_for_study(db, study_id: str) -> list[dict]:
    """Active participants only, ordered by student_id for a deterministic
    roster position (round-robin sequence assignment depends on this order
    being stable across runs)."""
    return db.execute(
        """
        SELECT student_id, class_id, sequence_id
        FROM vocab_research_participants
        WHERE study_id = %s AND active = TRUE
        ORDER BY student_id
        """,
        (study_id,),
    ).fetchall()


def set_participant_sequence(db, study_id: str, student_id: str, sequence_id: str) -> None:
    db.execute(
        """
        UPDATE vocab_research_participants
        SET sequence_id = %s
        WHERE study_id = %s AND student_id = %s AND sequence_id IS NULL
        """,
        (sequence_id, study_id, student_id),
    )


def find_published_vocab_by_lesson_range(db, lesson_min: int, lesson_max: int) -> list[dict]:
    """Raw (id, lesson_number, vocab_assessment) rows for published stories
    in the given lesson range, ordered so word position within/ across
    stories is deterministic (lesson, then sub-order, then story id)."""
    return db.execute(
        """
        SELECT id, lesson_number, lesson_sub_order, vocab_assessment
        FROM custom_stories
        WHERE published = TRUE
          AND lesson_number BETWEEN %s AND %s
        ORDER BY lesson_number, lesson_sub_order NULLS LAST, id
        """,
        (lesson_min, lesson_max),
    ).fetchall()


def count_assignments(db, study_id: str) -> int:
    return db.execute(
        "SELECT COUNT(*) AS total FROM vocab_research_assignments WHERE study_id = %s",
        (study_id,),
    ).fetchone()["total"]


def insert_assignment(
    db,
    *,
    study_id: str,
    student_id: str,
    word_id: str,
    lesson_id: Optional[str],
    section_id: Optional[str],
    bkt_policy: str,
    retention_policy: str,
    sequence_id: str,
    related_set_id: Optional[str],
    yoke_source_word_id: Optional[str],
    assignment_version: str,
    created_at: str,
) -> None:
    db.execute(
        """
        INSERT INTO vocab_research_assignments
            (study_id, student_id, word_id, lesson_id, section_id, bkt_policy,
             retention_policy, sequence_id, related_set_id, yoke_source_word_id,
             assignment_version, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            study_id, student_id, word_id, lesson_id, section_id, bkt_policy,
            retention_policy, sequence_id, related_set_id, yoke_source_word_id,
            assignment_version, created_at,
        ),
    )


def delete_assignments_for_study(db, study_id: str) -> None:
    db.execute("DELETE FROM vocab_research_assignments WHERE study_id = %s", (study_id,))


def find_assignments_for_study(db, study_id: str) -> list[dict]:
    return db.execute(
        "SELECT * FROM vocab_research_assignments WHERE study_id = %s ORDER BY student_id, id",
        (study_id,),
    ).fetchall()


def find_assignments_for_student(db, study_id: str, student_id: str) -> list[dict]:
    """One student's frozen word->condition assignment for a study. Epic 4's
    practice-session builder reads bkt_policy/retention_policy from here;
    Epic 5's retention enrollment/yoking also needs section_id and
    yoke_source_word_id - never re-derives any of these from anything else."""
    return db.execute(
        """
        SELECT word_id, lesson_id, section_id, bkt_policy, retention_policy, yoke_source_word_id
        FROM vocab_research_assignments
        WHERE study_id = %s AND student_id = %s
        ORDER BY id
        """,
        (study_id, student_id),
    ).fetchall()


def find_yoked_dependents(db, study_id: str, student_id: str, source_word_id: str) -> list[str]:
    """Which yoked words mirror this source word's schedule for this
    student (Task 5.6) - looked up from the frozen assignment, never
    recomputed. Usually zero or one word (the design pairs C<->S, B<->BS
    positionally), but this does not assume exactly one."""
    rows = db.execute(
        """
        SELECT word_id FROM vocab_research_assignments
        WHERE study_id = %s AND student_id = %s AND yoke_source_word_id = %s
        """,
        (study_id, student_id, source_word_id),
    ).fetchall()
    return [row["word_id"] for row in rows]


def count_research_practice_exposures(db, study_id: str, student_id: str, word_ids: list[str]) -> dict[str, int]:
    """How many past research-practice responses each of these words has for
    this student in this study (mastery-blind selection's only allowed
    signal - a raw exposure count, never correctness or timing)."""
    if not word_ids:
        return {}
    rows = db.execute(
        """
        SELECT word_id, COUNT(*) AS exposure_count
        FROM vocab_quiz_responses
        WHERE student_id = %s AND research_study_id = %s AND quiz_mode = 'weak_words'
          AND word_id = ANY(%s)
        GROUP BY word_id
        """,
        (student_id, study_id, word_ids),
    ).fetchall()
    return {row["word_id"]: int(row["exposure_count"]) for row in rows}


def upsert_research_bkt_state(db, *, student_id: str, study_id: str, states: list[dict], now: str) -> None:
    """Persist a treatment-BKT snapshot (Task 4.1) - one row per
    (student, study, word), replaced on every practice-session build so it
    always reflects the state that actually drove the most recent
    selection."""
    for state in states:
        db.execute(
            """
            INSERT INTO vocab_research_bkt_state
                (student_id, study_id, word_id, p_learned, observation_count,
                 correct_count, incorrect_count, last_response_at, last_item_id,
                 last_question_type, model_version, parameter_fingerprint,
                 created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (student_id, study_id, word_id) DO UPDATE SET
                p_learned = EXCLUDED.p_learned,
                observation_count = EXCLUDED.observation_count,
                correct_count = EXCLUDED.correct_count,
                incorrect_count = EXCLUDED.incorrect_count,
                last_response_at = EXCLUDED.last_response_at,
                last_item_id = EXCLUDED.last_item_id,
                last_question_type = EXCLUDED.last_question_type,
                model_version = EXCLUDED.model_version,
                parameter_fingerprint = EXCLUDED.parameter_fingerprint,
                updated_at = EXCLUDED.updated_at
            """,
            (
                student_id, study_id, state["word_id"], state["p_learned"],
                state["observation_count"], state["correct_count"], state["incorrect_count"],
                state.get("last_response_at"), state.get("last_item_id"), state.get("last_question_type"),
                state.get("model_version"), state.get("parameter_fingerprint"), now, now,
            ),
        )


def find_retention_states(db, student_id: str, study_id: str, word_ids: Optional[list[str]] = None) -> dict:
    """word_id -> raw retention_state row for this student's study (Epic 5,
    Task 5.1). Kept as raw rows here - domain/research/retention.py
    and analytics/srs.py's SrsState own the typed conversion, matching how
    repositories/srs_store.py keeps persistence and algorithm separate."""
    if word_ids is not None:
        if not word_ids:
            return {}
        rows = db.execute(
            "SELECT * FROM vocab_research_retention_state WHERE student_id = %s AND study_id = %s AND word_id = ANY(%s)",
            (student_id, study_id, word_ids),
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM vocab_research_retention_state WHERE student_id = %s AND study_id = %s",
            (student_id, study_id),
        ).fetchall()
    return {row["word_id"]: row for row in rows}


def upsert_retention_state(db, *, student_id: str, study_id: str, word_id: str, state, algorithm_version: str, now: str) -> None:
    db.execute(
        """
        INSERT INTO vocab_research_retention_state
            (student_id, study_id, word_id, reps, ease, interval_days, due_on,
             last_reviewed_on, algorithm_version, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (student_id, study_id, word_id) DO UPDATE SET
            reps = EXCLUDED.reps,
            ease = EXCLUDED.ease,
            interval_days = EXCLUDED.interval_days,
            due_on = EXCLUDED.due_on,
            last_reviewed_on = EXCLUDED.last_reviewed_on,
            algorithm_version = EXCLUDED.algorithm_version,
            updated_at = EXCLUDED.updated_at
        """,
        (
            student_id, study_id, word_id, state.reps, state.ease, state.interval_days,
            state.due_on, state.last_reviewed_on, algorithm_version, now, now,
        ),
    )


def insert_assessment_item(
    db,
    *,
    id: str,
    study_id: str,
    word_id: str,
    assessment_type: str,
    question_type: str,
    prompt: str,
    choices: Optional[list],
    correct_answer: str,
    created_at: str,
) -> None:
    from psycopg.types.json import Jsonb

    db.execute(
        """
        INSERT INTO vocab_research_assessment_items
            (id, study_id, word_id, assessment_type, question_type, prompt, choices, correct_answer, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            id, study_id, word_id, assessment_type, question_type, prompt,
            Jsonb(choices) if choices is not None else None, correct_answer, created_at,
        ),
    )


def find_assessment_item(db, item_id: str) -> Optional[dict]:
    return db.execute(
        "SELECT * FROM vocab_research_assessment_items WHERE id = %s", (item_id,)
    ).fetchone()


def find_assessment_items_for_words(db, study_id: str, word_ids: list[str], assessment_type: str) -> dict[str, dict]:
    """One item per word_id for a given assessment_type (first by id if more
    than one variant exists in the bank - deterministic, not random, so
    probe scheduling is reproducible)."""
    if not word_ids:
        return {}
    rows = db.execute(
        """
        SELECT DISTINCT ON (word_id) *
        FROM vocab_research_assessment_items
        WHERE study_id = %s AND assessment_type = %s AND word_id = ANY(%s)
        ORDER BY word_id, id
        """,
        (study_id, assessment_type, word_ids),
    ).fetchall()
    return {row["word_id"]: row for row in rows}


def find_probe_assignments_for_student(db, study_id: str, student_id: str, word_ids: Optional[list[str]] = None) -> dict[str, dict]:
    """word_id -> its probe assignment for this student, if scheduled. Used
    both to check "already enrolled" (Task 7.3 idempotency) and to look up
    an assignment by word."""
    if word_ids is not None:
        if not word_ids:
            return {}
        rows = db.execute(
            "SELECT * FROM vocab_research_probe_assignments WHERE study_id = %s AND student_id = %s AND word_id = ANY(%s)",
            (study_id, student_id, word_ids),
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM vocab_research_probe_assignments WHERE study_id = %s AND student_id = %s",
            (study_id, student_id),
        ).fetchall()
    return {row["word_id"]: row for row in rows}


def insert_probe_assignment(
    db,
    *,
    study_id: str,
    student_id: str,
    word_id: str,
    assessment_item_id: str,
    probe_type: str,
    due_at,
    assigned_at,
    created_at: str,
) -> None:
    db.execute(
        """
        INSERT INTO vocab_research_probe_assignments
            (study_id, student_id, word_id, assessment_item_id, probe_type, due_at, assigned_at, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (study_id, student_id, word_id, probe_type) DO NOTHING
        """,
        (study_id, student_id, word_id, assessment_item_id, probe_type, due_at, assigned_at, created_at),
    )


def find_due_probe_assignments(db, study_id: str, student_id: str, now) -> list[dict]:
    """Due AND unanswered (Task 7.5) - a probe that already has a response
    row must never appear here again; there is no re-grading path."""
    return db.execute(
        """
        SELECT a.*
        FROM vocab_research_probe_assignments a
        LEFT JOIN vocab_research_probe_responses r ON r.probe_assignment_id = a.id
        WHERE a.study_id = %s AND a.student_id = %s
          AND a.due_at IS NOT NULL AND a.due_at <= %s
          AND r.id IS NULL
        ORDER BY a.due_at, a.id
        """,
        (study_id, student_id, now),
    ).fetchall()


def find_probe_assignment_by_id(db, assignment_id, student_id: str) -> Optional[dict]:
    """Scoped by student_id too - a probe assignment id alone must never be
    enough to read or answer another student's probe."""
    return db.execute(
        "SELECT * FROM vocab_research_probe_assignments WHERE id = %s AND student_id = %s",
        (assignment_id, student_id),
    ).fetchone()


def find_probe_response(db, probe_assignment_id) -> Optional[dict]:
    return db.execute(
        "SELECT * FROM vocab_research_probe_responses WHERE probe_assignment_id = %s",
        (probe_assignment_id,),
    ).fetchone()


def insert_probe_response(
    db,
    *,
    probe_assignment_id,
    study_id: str,
    student_id: str,
    word_id: str,
    assessment_item_id: str,
    response_value: str,
    correct: bool,
    source_response_id: str,
    responded_at,
    created_at: str,
) -> bool:
    """Returns whether this was the first response recorded for the
    assignment (mirrors record_retention_event's idempotency contract)."""
    cursor = db.execute(
        """
        INSERT INTO vocab_research_probe_responses
            (probe_assignment_id, study_id, student_id, word_id, assessment_item_id,
             response_value, correct, source_response_id, responded_at, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (probe_assignment_id) DO NOTHING
        RETURNING id
        """,
        (
            probe_assignment_id, study_id, student_id, word_id, assessment_item_id,
            response_value, correct, source_response_id, responded_at, created_at,
        ),
    )
    return cursor.fetchone() is not None


def record_retention_event(
    db, *, student_id: str, study_id: str, word_id: str, event_type: str,
    old_state, new_state, source_response_id: str, algorithm_version: str,
    quiz_id: Optional[str] = None, attempt_id: Optional[str] = None,
    correct: Optional[bool] = None, quality: Optional[int] = None, occurred_at,
) -> bool:
    """Append one immutable transition; returns whether it was new (mirrors
    srs_store.record_srs_event's idempotency contract)."""
    cursor = db.execute(
        """
        INSERT INTO vocab_research_retention_events
            (student_id, study_id, word_id, source_response_id, quiz_id, attempt_id,
             event_type, correct, quality, old_reps, new_reps, old_ease, new_ease,
             old_interval_days, new_interval_days, old_due_on, new_due_on,
             algorithm_version, occurred_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (student_id, study_id, word_id, source_response_id) DO NOTHING
        RETURNING id
        """,
        (
            student_id, study_id, word_id, source_response_id, quiz_id, attempt_id,
            event_type, correct, quality, old_state.reps, new_state.reps,
            old_state.ease, new_state.ease, old_state.interval_days, new_state.interval_days,
            old_state.due_on, new_state.due_on, algorithm_version, occurred_at,
        ),
    )
    return cursor.fetchone() is not None


def insert_policy_event(
    db,
    *,
    study_id: str,
    student_id: str,
    event_type: str,
    word_id: Optional[str],
    payload: Optional[dict],
    occurred_at,
    created_at: str,
) -> None:
    from psycopg.types.json import Jsonb

    db.execute(
        """
        INSERT INTO vocab_research_policy_events
            (study_id, student_id, event_type, word_id, payload_json, occurred_at, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (study_id, student_id, event_type, word_id, Jsonb(payload) if payload is not None else None, occurred_at, created_at),
    )


def count_policy_events_by_type(db, study_id: str) -> dict[str, int]:
    """Task 8.2: the raw counts every fidelity ratio is built from."""
    rows = db.execute(
        "SELECT event_type, COUNT(*) AS total FROM vocab_research_policy_events WHERE study_id = %s GROUP BY event_type",
        (study_id,),
    ).fetchall()
    return {row["event_type"]: int(row["total"]) for row in rows}


def count_word_events_by_condition(db, study_id: str, event_type: str) -> dict[str, int]:
    """Task 8.2: e.g. how many practice_item_selected events landed in each
    of C/B/S/BS - read back from payload_json['condition'], which the
    writer stamped once from the frozen assignment row it already had, so
    this never needs to re-join vocab_research_assignments."""
    rows = db.execute(
        """
        SELECT payload_json ->> 'condition' AS condition, COUNT(*) AS total
        FROM vocab_research_policy_events
        WHERE study_id = %s AND event_type = %s
        GROUP BY payload_json ->> 'condition'
        """,
        (study_id, event_type),
    ).fetchall()
    return {(row["condition"] or "unknown"): int(row["total"]) for row in rows}


def average_review_delay_days(db, study_id: str) -> Optional[float]:
    """Task 8.2's "delay days": how late, on average, a word actually got
    reviewed relative to when SM-2 said it was due. Read from
    vocab_research_retention_events (Epic 5), whose old_due_on/occurred_at
    on a maintenance_success/failure row are exactly "due" vs "answered" -
    the current retention-state row only holds the NEXT due date computed
    from this review, not the one that was actually due, so it can't answer
    this question."""
    row = db.execute(
        """
        SELECT AVG(EXTRACT(EPOCH FROM (occurred_at - old_due_on)) / 86400.0) AS avg_delay_days
        FROM vocab_research_retention_events
        WHERE study_id = %s
          AND event_type IN ('maintenance_success', 'maintenance_failure')
          AND old_due_on IS NOT NULL
        """,
        (study_id,),
    ).fetchone()
    value = row["avg_delay_days"] if row else None
    return float(value) if value is not None else None
