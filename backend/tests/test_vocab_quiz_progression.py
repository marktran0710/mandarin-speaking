from analytics.learner_model.bkt.mastery import story_scope_ids
from services import vocab_quiz_progression_service as progression


class _Rows:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows


class _Db:
    def __init__(self, response_rows, conversation_turns):
        self.response_rows = response_rows
        self.conversation_turns = conversation_turns

    def execute(self, query, params):
        if "FROM vocab_quiz_responses" in query:
            return _Rows(self.response_rows)
        if "FROM custom_stories" in query:
            return _Rows([{"conversation_turns": self.conversation_turns}])
        raise AssertionError(f"Unexpected query: {query}")


def _attempt(mode, quiz_id, total=10, correct=0):
    return {
        "id": quiz_id,
        "storyId": "story-5-1",
        "studentId": "student-1",
        "mode": mode,
        "totalQuestions": total,
        # Deliberately wrong: progression must use the validated ledger below.
        "correctCount": correct,
        "progressionPolicy": "production_accuracy",
        "questionResults": [{"quizId": quiz_id} for _ in range(total)],
    }


def _responses(mode, quiz_id, correct_count, total=10):
    return [
        {"quiz_id": quiz_id, "quiz_mode": mode, "quiz_level": mode, "bkt_eligible": True, "correct": index < correct_count}
        for index in range(total)
    ]


def _conversation():
    return [
        {"id": "system-1", "speaker": "system", "text": "Model"},
        {"id": "student-1", "speaker": "student", "text": "Reply"},
    ]


def test_three_completed_tiers_derive_three_stars_from_server_responses(monkeypatch):
    attempts = [_attempt("tier1", "q1"), _attempt("tier2", "q2"), _attempt("tier3", "q3")]
    responses = _responses("tier1", "q1", 7) + _responses("tier2", "q2", 9) + _responses("tier3", "q3", 9)
    monkeypatch.setattr(progression.quiz_attempt_repository, "list_attempts", lambda db, **kwargs: attempts)

    result = progression.get_progression(_Db(responses, _conversation()), "student-1", "teacher-story-5-1-medium")

    assert result["quizStars"] == 3
    assert result["speakingUnlocked"] is True
    assert result["conversationAvailable"] is True
    assert result["conversationUnlocked"] is True
    assert result["tiers"]["tier1"]["correctCount"] == 7


def test_partial_response_without_completed_attempt_does_not_create_a_star(monkeypatch):
    attempts = [_attempt("tier1", "q1"), _attempt("tier2", "q2")]
    responses = _responses("tier1", "q1", 7) + _responses("tier2", "q2", 9) + _responses("tier3", "partial", 10)
    monkeypatch.setattr(progression.quiz_attempt_repository, "list_attempts", lambda db, **kwargs: attempts)

    result = progression.get_progression(_Db(responses, _conversation()), "student-1", "story-5-1")

    assert result["quizStars"] == 2
    assert result["tiers"]["tier3"]["totalQuestions"] == 0


def test_tier_three_alone_does_not_unlock_the_contiguous_ladder(monkeypatch):
    attempts = [_attempt("tier3", "q3")]
    monkeypatch.setattr(progression.quiz_attempt_repository, "list_attempts", lambda db, **kwargs: attempts)

    result = progression.get_progression(_Db(_responses("tier3", "q3", 10), None), "student-1", "story-5-1")

    assert result["quizStars"] == 0
    assert result["speakingUnlocked"] is False


def test_story_scope_ids_normalize_teacher_and_legacy_suffixes():
    expected = set(story_scope_ids("story-5-1"))
    assert expected == set(story_scope_ids("teacher-story-5-1-medium"))
    assert {"story-5-1", "teacher-story-5-1", "teacher-story-5-1-medium", "teacher-story-5-1-hard"} <= expected


def test_invalid_conversation_turns_keep_conversation_locked(monkeypatch):
    attempts = [_attempt("tier1", "q1"), _attempt("tier2", "q2"), _attempt("tier3", "q3")]
    responses = _responses("tier1", "q1", 7) + _responses("tier2", "q2", 9) + _responses("tier3", "q3", 9)
    monkeypatch.setattr(progression.quiz_attempt_repository, "list_attempts", lambda db, **kwargs: attempts)

    result = progression.get_progression(_Db(responses, [{"id": "only", "speaker": "system", "text": "one"}]), "student-1", "story-5-1")

    assert result["quizStars"] == 3
    assert result["speakingUnlocked"] is True
    assert result["conversationAvailable"] is False
    assert result["conversationUnlocked"] is False
