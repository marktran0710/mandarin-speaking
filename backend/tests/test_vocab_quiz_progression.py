import pytest

from analytics.learner_model.bkt.mastery import story_scope_ids
from services import vocab_quiz_progression_service as progression


class _Rows:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows


class _Db:
    def __init__(self, response_rows, conversation_turns, frames=None):
        self.response_rows = response_rows
        self.conversation_turns = conversation_turns
        self.frames = frames

    def execute(self, query, params):
        if "FROM vocab_quiz_responses" in query:
            return _Rows(self.response_rows)
        if "FROM custom_stories" in query:
            return _Rows([{
                "id": "story-5-1", "conversation_turns": self.conversation_turns, "frames": self.frames,
                "vocab_assessment": [{"wordId": f"word-{i}", "targetWord": f"Word {i}"} for i in range(10)],
            }])
        raise AssertionError(f"Unexpected query: {query}")


def _attempt(mode, quiz_id, total=10, correct=0):
    return {
        "id": quiz_id,
        "storyId": "story-5-1",
        "studentId": "student-1",
        "mode": mode,
        "completedAt": "2026-09-01T00:00:00Z",
        "totalQuestions": total,
        # Deliberately wrong: progression must use the validated ledger below.
        "correctCount": correct,
        "progressionPolicy": "production_accuracy",
        "questionResults": [{"quizId": quiz_id} for _ in range(total)],
    }


def _responses(mode, quiz_id, correct_count, total=10):
    return [
        {"quiz_id": quiz_id, "quiz_mode": mode, "word_id": f"word-{index}", "quiz_level": mode, "bkt_eligible": True, "correct": index < correct_count}
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
    assert result["speakingUnlocked"] is False
    assert result["conversationUnlocked"] is False


def test_tier_three_alone_does_not_unlock_the_contiguous_ladder(monkeypatch):
    attempts = [_attempt("tier3", "q3")]
    monkeypatch.setattr(progression.quiz_attempt_repository, "list_attempts", lambda db, **kwargs: attempts)

    result = progression.get_progression(_Db(_responses("tier3", "q3", 10), None), "student-1", "story-5-1")

    assert result["quizStars"] == 0
    assert result["speakingUnlocked"] is False
    assert result["conversationUnlocked"] is False


def test_deleted_observations_revoke_stars_even_when_completed_attempts_remain(monkeypatch):
    attempts = [_attempt(tier, tier, correct=10) for tier in ("tier1", "tier2", "tier3")]
    monkeypatch.setattr(progression.quiz_attempt_repository, "list_attempts", lambda db, **kwargs: attempts)
    result = progression.get_progression(_Db([], _conversation()), "student-1", "story-5-1")
    assert result["quizStars"] == 0
    assert result["speakingUnlocked"] is False
    assert result["conversationUnlocked"] is False


@pytest.mark.parametrize("old_ids", [False, True])
def test_old_ids_or_partial_vocabulary_cannot_unlock_a_current_lesson(monkeypatch, old_ids):
    attempts = [_attempt(tier, tier, total=4, correct=4) for tier in ("tier1", "tier2", "tier3")]
    responses = [row for tier in ("tier1", "tier2", "tier3") for row in _responses(tier, tier, 4, total=4)]
    if old_ids:
        for row in responses:
            row["word_id"] = f"old-{row['word_id']}"
    monkeypatch.setattr(progression.quiz_attempt_repository, "list_attempts", lambda db, **kwargs: attempts)
    result = progression.get_progression(_Db(responses, _conversation()), "student-1", "story-5-1")
    assert result["quizStars"] == 0
    assert result["speakingUnlocked"] is False
    assert result["conversationUnlocked"] is False


def test_story_scope_ids_normalize_teacher_and_legacy_suffixes():
    expected = set(story_scope_ids("story-5-1"))
    assert expected == set(story_scope_ids("teacher-story-5-1-medium"))
    assert {"story-5-1", "teacher-story-5-1", "teacher-story-5-1-medium", "teacher-story-5-1-hard"} <= expected


def test_invalid_conversation_content_does_not_change_the_shared_practice_gate(monkeypatch):
    attempts = [_attempt("tier1", "q1"), _attempt("tier2", "q2"), _attempt("tier3", "q3")]
    responses = _responses("tier1", "q1", 7) + _responses("tier2", "q2", 9) + _responses("tier3", "q3", 9)
    monkeypatch.setattr(progression.quiz_attempt_repository, "list_attempts", lambda db, **kwargs: attempts)

    result = progression.get_progression(_Db(responses, [{"id": "only", "speaker": "system", "text": "one"}]), "student-1", "story-5-1")

    assert result["quizStars"] == 3
    assert result["speakingUnlocked"] is True
    assert result["conversationAvailable"] is False
    assert result["conversationUnlocked"] is True


@pytest.mark.parametrize("stars", [0, 1, 2, 3])
@pytest.mark.parametrize("has_content", [False, True])
def test_both_practices_share_the_same_gate_at_every_star_count(monkeypatch, stars, has_content):
    tiers = ["tier1", "tier2", "tier3"][:stars]
    attempts = [_attempt(tier, tier) for tier in tiers]
    responses = [row for tier in tiers for row in _responses(tier, tier, 10)]
    monkeypatch.setattr(progression.quiz_attempt_repository, "list_attempts", lambda db, **kwargs: attempts)

    result = progression.get_progression(_Db(responses, _conversation() if has_content else None), "student-1", "story-5-1")

    assert result["quizStars"] == stars
    assert result["conversationAvailable"] is has_content
    assert result["speakingUnlocked"] is (stars == 3)
    assert result["conversationUnlocked"] is (stars == 3)


def test_shared_story_frames_make_conversation_available_without_saved_turns(monkeypatch):
    attempts = [_attempt("tier1", "q1"), _attempt("tier2", "q2"), _attempt("tier3", "q3")]
    responses = _responses("tier1", "q1", 7) + _responses("tier2", "q2", 9) + _responses("tier3", "q3", 9)
    monkeypatch.setattr(progression.quiz_attempt_repository, "list_attempts", lambda db, **kwargs: attempts)

    frames = [
        {"suggestedAnswer": "System line"},
        {"suggestedAnswer": "Student line"},
        {"suggestedAnswer": "Closing line"},
    ]
    result = progression.get_progression(_Db(responses, None, frames), "student-1", "story-5-1")

    assert result["conversationAvailable"] is True
    assert result["conversationUnlocked"] is True


def test_finishing_a_round_earns_it_regardless_of_accuracy(monkeypatch):
    # 1/10, 0/10, 2/10 would have failed every old pass ratio (70/82/88%);
    # finishing each round is now what counts.
    attempts = [_attempt("tier1", "q1"), _attempt("tier2", "q2"), _attempt("tier3", "q3")]
    responses = _responses("tier1", "q1", 1) + _responses("tier2", "q2", 0) + _responses("tier3", "q3", 2)
    monkeypatch.setattr(progression.quiz_attempt_repository, "list_attempts", lambda db, **kwargs: attempts)

    result = progression.get_progression(_Db(responses, _conversation()), "student-1", "story-5-1")

    assert result["quizStars"] == 3
    assert result["speakingUnlocked"] is True
    assert result["tiers"]["tier1"] == {
        "earned": True, "correctCount": 1, "totalQuestions": 10, "score": 10, "completedAt": "2026-09-01T00:00:00Z",
    }
    assert result["tiers"]["tier2"]["score"] == 0


def test_each_round_reports_its_latest_finished_attempt_not_its_best(monkeypatch):
    early = {**_attempt("tier1", "q-early"), "completedAt": "2026-09-01T00:00:00Z"}
    late = {**_attempt("tier1", "q-late"), "completedAt": "2026-09-02T00:00:00Z"}
    unfinished = {**_attempt("tier1", "q-unfinished"), "completedAt": "2026-09-03T00:00:00Z"}
    responses = (
        _responses("tier1", "q-early", 9)
        + _responses("tier1", "q-late", 4)
        # Only 3 of its 10 answers reached the ledger, so it is not a finished round.
        + _responses("tier1", "q-unfinished", 3, total=3)
    )
    monkeypatch.setattr(progression.quiz_attempt_repository, "list_attempts", lambda db, **kwargs: [late, unfinished, early])

    result = progression.get_progression(_Db(responses, None), "student-1", "story-5-1")

    assert result["quizStars"] == 1
    assert result["tiers"]["tier1"]["score"] == 40
    assert result["tiers"]["tier1"]["completedAt"] == "2026-09-02T00:00:00Z"
    assert result["tiers"]["tier2"] == {
        "earned": False, "correctCount": 0, "totalQuestions": 0, "score": 0, "completedAt": None,
    }
