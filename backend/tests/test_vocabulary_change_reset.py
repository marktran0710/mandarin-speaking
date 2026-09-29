from psycopg.types.json import Jsonb

import db


def _question(*, word: str, meaning: str = "meaning", question_id: str = "q-1", audio: str = "a-1") -> dict:
    return {
        "questionId": question_id,
        "wordId": word,
        "targetWord": word,
        "level": "easy",
        "questionType": "basic_meaning_mcq",
        "answerFormat": "single_choice",
        "pinyin": "pinyin",
        "meaning": meaning,
        "audioUrl": audio,
        "options": [meaning, "other"],
        "correctAnswer": meaning,
        "acceptedAnswers": [meaning],
        "prompt": f"What does {word} mean?",
    }


def _insert_learning_rows(story_id: str) -> None:
    with db.connect_db() as conn:
        conn.execute(
            """
            INSERT INTO students (id, name, password)
            VALUES ('reset-student-1', 'Reset Student 1', 'pw'),
                   ('reset-student-2', 'Reset Student 2', 'pw')
            """
        )
        for index, student_id in enumerate(("reset-student-1", "reset-student-2"), start=1):
            attempt_id = f"reset-attempt-{index}"
            conn.execute(
                """
                INSERT INTO vocab_quiz_attempts
                    (id, story_id, student_name, completed_at, total_questions,
                     correct_count, total_time_ms, question_results, student_id)
                VALUES (%s, %s, %s, '2026-01-01T00:00:00Z', 1, 1, 100,
                        %s, %s)
                """,
                (attempt_id, story_id, student_id, Jsonb([{"word": "word-old", "correct": True}]), student_id),
            )
            conn.execute(
                """
                INSERT INTO vocab_quiz_responses
                    (student_id, word_id, word, lesson_id, quiz_id, attempt_id,
                     item_id, question_type, correct, response_time_ms, attempt_order)
                VALUES (%s, 'word-old', 'word-old', %s, %s, %s,
                        %s, 'basic_meaning_mcq', TRUE, 100, 0)
                """,
                (student_id, story_id, f"quiz-{index}", attempt_id, f"item-{index}"),
            )
            conn.execute(
                """
                INSERT INTO student_vocab_mastery
                    (student_id, word_id, p_learned, observation_count,
                     correct_count, incorrect_count, created_at, updated_at)
                VALUES (%s, 'word-old', .9, 1, 1, 0, '2026-01-01', '2026-01-01')
                """,
                (student_id,),
            )
            conn.execute(
                """
                INSERT INTO student_vocab_srs
                    (student_id, word_id, reps, ease, interval_days,
                     created_at, updated_at)
                VALUES (%s, 'word-old', 1, 2.5, 1, '2026-01-01', '2026-01-01')
                """,
                (student_id,),
            )
            conn.execute(
                """
                INSERT INTO speaking_progress
                    (id, student_id, topic_id, scene_index, attempts,
                     best_tone, best_fluency, mastery_passed, content_passed,
                     cleared_words)
                VALUES (%s, %s, %s, 0, 1, .8, .8, TRUE, TRUE, %s)
                """,
                (f"{student_id}:{story_id}:0", student_id, story_id, Jsonb(["word-old"])),
            )
            conn.execute(
                """
                INSERT INTO story_submissions
                    (id, story_id, story_title, student_name, submitted_at, scenes, student_id)
                VALUES (%s, %s, 'Reset lesson', %s, '2026-01-01T00:00:00Z', %s, %s)
                """,
                (f"submission-{index}", story_id, student_id, Jsonb([]), student_id),
            )
            conn.execute(
                """
                INSERT INTO learning_measurement_events
                    (event_id, schema_version, name, occurred_at, student_id,
                     attempt_id, topic_id, properties)
                VALUES (%s, 'v1', 'quiz_completed', '2026-01-01T00:00:00Z',
                        %s, %s, %s, %s)
                """,
                (f"event-{index}", student_id, attempt_id, story_id, Jsonb({"source": "test"})),
            )



def test_vocabulary_change_resets_every_student_and_archives_learning_rows():
    story_id = "vocabulary-reset-lesson"
    old_question = _question(word="word-old")
    with db.connect_db() as conn:
        conn.execute(
            """
            INSERT INTO custom_stories
                (id, title, frames, published, vocab_assessment)
            VALUES (%s, 'Reset lesson', %s, TRUE, %s)
            """,
            (story_id, Jsonb([{"vocabulary": "word-old", "vocabularyPinyin": "pinyin", "vocabularyTranslation": "meaning"}]), Jsonb([old_question])),
        )
    _insert_learning_rows(story_id)

    changed_question = _question(word="word-new", meaning="new meaning", question_id="q-2", audio="a-2")
    with db.connect_db() as conn:
        conn.execute(
            "UPDATE custom_stories SET vocab_assessment = %s WHERE id = %s",
            (Jsonb([changed_question]), story_id),
        )
        story = conn.execute(
            "SELECT vocabulary_version, title FROM custom_stories WHERE id = %s",
            (story_id,),
        ).fetchone()
        counts = {
            table: conn.execute(f"SELECT count(*) AS n FROM {table}").fetchone()["n"]
            for table in (
                "vocab_quiz_responses",
                "vocab_quiz_attempts",
                "student_vocab_mastery",
                "student_vocab_srs",
                "speaking_progress",
                "story_submissions",
                "learning_measurement_events",
            )
        }
        archive = conn.execute(
            "SELECT previous_content, learning_rows FROM lesson_vocabulary_reset_archive WHERE story_id = %s",
            (story_id,),
        ).fetchone()

    assert story["vocabulary_version"] == 2
    assert story["title"] == "Reset lesson"
    assert all(value == 0 for value in counts.values())
    assert archive["previous_content"]["assessment"] == [old_question]
    assert len(archive["learning_rows"]["vocab_quiz_responses"]) == 2
    assert len(archive["learning_rows"]["learning_measurement_events"]) == 2


def test_audio_and_generated_question_id_changes_do_not_reset_progress():
    story_id = "vocabulary-audio-only"
    original = _question(word="word-stable")
    with db.connect_db() as conn:
        conn.execute(
            "INSERT INTO custom_stories (id, title, frames, published, vocab_assessment) VALUES (%s, 'Stable', %s, TRUE, %s)",
            (story_id, Jsonb([]), Jsonb([original])),
        )
    _insert_learning_rows(story_id)

    audio_only = _question(word="word-stable", question_id="generated-new-id", audio="generated-new-audio")
    with db.connect_db() as conn:
        conn.execute(
            "UPDATE custom_stories SET vocab_assessment = %s WHERE id = %s",
            (Jsonb([audio_only]), story_id),
        )
        story = conn.execute("SELECT vocabulary_version FROM custom_stories WHERE id = %s", (story_id,)).fetchone()
        response_count = conn.execute("SELECT count(*) AS n FROM vocab_quiz_responses").fetchone()["n"]

    assert story["vocabulary_version"] == 1
    assert response_count == 2
