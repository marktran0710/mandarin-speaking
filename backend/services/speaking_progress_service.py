"""Use-case orchestration for the speaking-progress upsert flow.

Holds the merge/eligibility decision tree that used to live inline in
routers/speaking_progress.py: which scene result wins on a race, whether a
save can be trusted to alter a server-verified row, and how attempts/best
scores accumulate. Raises SpeakingProgressError (not HTTPException) - the
router maps it to an HTTP status code.
"""
from datetime import datetime, timezone
from statistics import fmean
from typing import Any

from repositories import speaking_progress_repository as repo
from repositories.database import row_to_speaking_progress

_VERIFIED_SPEAKING_VERSION = "verified-speaking-stable-v1"
_SELF_EVAL_FIELDS = ("selfEvalContent", "selfEvalPronunciation")

_RESULT_CORE_FIELDS = (
    "sceneIndex",
    "transcription",
    "vocabUsed",
    "vocabMissing",
    "vocabScore",
    "toneAccuracy",
    "pronScore",
    "fluencyScore",
    "pauseCount",
    "longestPause",
    "utteranceCount",
    "choppyPauseCount",
    "articulationRate",
)


class SpeakingProgressError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _merge_cleared_words(existing: object, incoming: list[str]) -> list[str]:
    """Keep the durable union so a stale save cannot undo a drill pass."""
    values: list[str] = []
    for word in [*(existing if isinstance(existing, list) else []), *incoming]:
        if isinstance(word, str) and word not in values:
            values.append(word)
    return values


def _merge_latest_result(existing: object, incoming: dict, *, same_attempt: bool) -> dict:
    """Merge same-attempt enrichment without erasing non-empty fields."""
    if not same_attempt or not isinstance(existing, dict):
        return incoming
    existing_snapshot_id = existing.get("snapshotId")
    incoming_snapshot_id = incoming.get("snapshotId")
    if existing_snapshot_id and incoming_snapshot_id and existing_snapshot_id != incoming_snapshot_id:
        return existing
    if existing_snapshot_id and not incoming_snapshot_id:
        return existing
    # A client race can produce two different analyses with the same attempt
    # counter. Only merge a result when its scored snapshot agrees with the
    # stored one; otherwise keep the first complete snapshot instead of
    # creating a hybrid from two recordings. Audio and self-evaluation fields
    # are intentionally outside this core set and may enrich that snapshot.
    for key in _RESULT_CORE_FIELDS:
        existing_value = existing.get(key)
        incoming_value = incoming.get(key)
        if (
            existing_value not in (None, "", [], {})
            and incoming_value not in (None, "", [], {})
            and existing_value != incoming_value
        ):
            return existing
    merged = dict(existing)
    for key, value in incoming.items():
        if value in (None, "", [], {}) and merged.get(key) not in (None, "", [], {}):
            continue
        merged[key] = value
    return merged


def _as_utc(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


def _metric_number(metrics: dict[str, Any], key: str) -> float:
    value = metrics.get(key)
    return float(value) if isinstance(value, (int, float)) else 0.0


def _verified_record_scene_result(record: dict[str, Any], progress: Any) -> tuple[dict[str, Any], bool, bool]:
    metrics = record["praat_metrics"]
    ai_feedback = metrics.get("ai_feedback")
    coverage = ai_feedback.get("vocabulary_coverage", {}) if isinstance(ai_feedback, dict) else {}
    if not isinstance(coverage, dict):
        coverage = {}
    pronunciation = metrics.get("pronunciation_mastery")
    pronunciation_passed = bool(pronunciation.get("passed")) if isinstance(pronunciation, dict) else False
    content_passed = metrics.get("content_match") is True
    word_scores = [
        float(word.get("display_score"))
        for word in (metrics.get("word_prosody") or [])
        if isinstance(word, dict) and isinstance(word.get("display_score"), (int, float))
    ]
    pron_score = fmean(word_scores) if word_scores else _metric_number(metrics, "tone_accuracy")
    pause_analysis = metrics.get("pause_analysis")
    if not isinstance(pause_analysis, dict):
        pause_analysis = {}
    result = {
        "sceneIndex": record["image_index"],
        "imageUrl": record.get("image_url") or "",
        "transcription": record.get("transcription") or metrics.get("transcription") or "",
        "vocabUsed": [word for word in (coverage.get("used") or []) if isinstance(word, str)],
        "vocabMissing": [word for word in (coverage.get("missing") or []) if isinstance(word, str)],
        "vocabScore": _metric_number(coverage, "score"),
        "toneAccuracy": _metric_number(metrics, "tone_accuracy"),
        "pronScore": pron_score,
        "fluencyScore": _metric_number(metrics, "fluency_score"),
        "audioUrl": record.get("audio_url"),
        "pauseCount": pause_analysis.get("pause_count", 0),
        "longestPause": pause_analysis.get("longest_pause", 0),
        "utteranceCount": pause_analysis.get("utterance_count", 0),
        "choppyPauseCount": pause_analysis.get("choppy_pause_count", 0),
        "articulationRate": pause_analysis.get("articulation_rate", 0),
        "baseStoryId": record["topic_id"],
        "difficultyLevel": progress.difficultyLevel or "easy",
        "snapshotId": record["id"],
    }
    if progress.conversationId:
        result["conversationId"] = progress.conversationId
    if progress.turnId:
        result["turnId"] = progress.turnId
    if progress.turnIndex is not None:
        result["turnIndex"] = progress.turnIndex
    if progress.promptId:
        result["promptId"] = progress.promptId
    incoming = progress.latestResult
    if isinstance(incoming, dict):
        for key in _SELF_EVAL_FIELDS:
            value = incoming.get(key)
            if value in {"good", "ok", "bad"}:
                result[key] = value
    return result, pronunciation_passed, content_passed


def _load_verified_record(db: Any, record_id: str, student_id: str) -> dict[str, Any]:
    record = repo.find_verified_audio_record_for_update(db, record_id)
    if record is None:
        raise SpeakingProgressError(404, "Verified audio record not found.")
    if record.get("student_id") != student_id:
        raise SpeakingProgressError(403, "Verified audio record belongs to another student.")
    if record.get("server_verified_at") is None:
        raise SpeakingProgressError(409, "Audio record is not server verified.")
    if record.get("server_verification_version") != _VERIFIED_SPEAKING_VERSION:
        raise SpeakingProgressError(409, "Audio record is not progression eligible.")
    if not isinstance(record.get("praat_metrics"), dict):
        raise SpeakingProgressError(409, "Verified audio record has no analysis metrics.")
    return record


def list_progress(db, student_id: str, topic_id: str) -> list[dict]:
    return [row_to_speaking_progress(row) for row in repo.list_progress(db, student_id, topic_id)]


def record_progress(db, progress: Any, student_id: str) -> None:
    """Persist a speaking-progress save, resolving concurrent/stale-write races.

    Mutates ``progress`` in place with the merged, persisted values (matching
    the previous router-inline behavior) so the caller can return the same
    object as the response body.
    """
    progress.studentId = student_id
    row_id = f"{progress.studentId}:{progress.topicId}:{progress.turnId or progress.sceneIndex}"
    latest_result = dict(progress.latestResult) if progress.latestResult is not None else None
    if progress.baseStoryId or progress.difficultyLevel or progress.promptId:
        if latest_result is not None:
            if progress.baseStoryId:
                latest_result["baseStoryId"] = progress.baseStoryId
            if progress.difficultyLevel:
                latest_result["difficultyLevel"] = progress.difficultyLevel
            latest_result["sceneIndex"] = progress.sceneIndex
            if progress.promptId:
                latest_result["promptId"] = progress.promptId
    progress.progressionEligible = False

    # The SELECT below cannot lock a row that does not exist yet. A
    # transaction-scoped advisory lock closes that first-insert race while
    # keeping the deterministic scene key as the lock identity.
    repo.acquire_progress_lock(db, row_id)
    existing = repo.find_progress_for_update(db, row_id)

    verified_record = None
    verified_is_stale = False
    if progress.verifiedAudioRecordId:
        verified_record = _load_verified_record(db, progress.verifiedAudioRecordId, student_id)
        expected_story_id = progress.baseStoryId or progress.topicId
        if verified_record.get("topic_id") != expected_story_id:
            raise SpeakingProgressError(409, "Verified audio record does not match this story.")
        if verified_record.get("image_index") != progress.sceneIndex:
            raise SpeakingProgressError(409, "Verified audio record does not match this scene.")

        current_id = existing.get("verified_audio_record_id") if existing else None
        if current_id and current_id != progress.verifiedAudioRecordId:
            current = repo.find_audio_record_summary(db, current_id)
            incoming_at = _as_utc(verified_record.get("server_verified_at"))
            current_at = _as_utc(current.get("server_verified_at")) if current else None
            verified_is_stale = bool(
                current
                and incoming_at
                and current_at
                and (
                    incoming_at < current_at
                    or (incoming_at == current_at and progress.verifiedAudioRecordId <= current_id)
                )
            )

        if existing and verified_is_stale:
            # A delayed save must not replace the newest server-owned
            # analysis or reintroduce its older verdict.
            merged_attempts = existing["attempts"]
            merged_best_tone = existing["best_tone"]
            merged_best_fluency = existing["best_fluency"]
            merged_mastery_passed = bool(existing["mastery_passed"])
            merged_content_passed = bool(existing["content_passed"])
            merged_cleared_words = _merge_cleared_words(existing["cleared_words"], [])
            merged_latest_result = existing["latest_result"]
            merged_verified_record_id = current_id
            progress.progressionEligible = bool(current_id)
        elif verified_record is not None:
            server_result, pronunciation_passed, content_passed = _verified_record_scene_result(
                verified_record, progress
            )
            if existing and current_id == progress.verifiedAudioRecordId:
                merged_cleared_words = _merge_cleared_words(
                    existing["cleared_words"], progress.clearedWords
                )
                merged_attempts = existing["attempts"]
                # Preserve self-evaluation enrichment already attached to
                # this same server snapshot when a retry omits it.
                if isinstance(existing["latest_result"], dict):
                    for key in _SELF_EVAL_FIELDS:
                        value = existing["latest_result"].get(key)
                        if value in {"good", "ok", "bad"} and key not in server_result:
                            server_result[key] = value
            else:
                merged_cleared_words = _merge_cleared_words([], progress.clearedWords)
                merged_attempts = 1
            stats = repo.find_verified_audio_stats(
                db, student_id, verified_record["topic_id"], verified_record["image_index"]
            )
            tone_scores = [
                _metric_number(row["praat_metrics"], "tone_accuracy")
                for row in stats
                if isinstance(row.get("praat_metrics"), dict)
            ]
            fluency_scores = [
                _metric_number(row["praat_metrics"], "fluency_score")
                for row in stats
                if isinstance(row.get("praat_metrics"), dict)
            ]
            merged_attempts = max(merged_attempts, len(stats))
            merged_best_tone = max(tone_scores, default=0.0)
            merged_best_fluency = max(fluency_scores, default=0.0)
            merged_mastery_passed = pronunciation_passed
            merged_content_passed = content_passed
            merged_latest_result = server_result
            merged_verified_record_id = progress.verifiedAudioRecordId
            progress.progressionEligible = True
        else:
            raise AssertionError("verified record validation returned no record")
    elif existing and existing.get("verified_audio_record_id"):
        # A legacy-shaped save cannot alter or clear a server-owned row.
        merged_attempts = existing["attempts"]
        merged_best_tone = existing["best_tone"]
        merged_best_fluency = existing["best_fluency"]
        merged_mastery_passed = bool(existing["mastery_passed"])
        merged_content_passed = bool(existing["content_passed"])
        merged_cleared_words = _merge_cleared_words(existing["cleared_words"], progress.clearedWords)
        merged_latest_result = existing["latest_result"]
        merged_verified_record_id = existing["verified_audio_record_id"]
        progress.progressionEligible = True
    elif existing:
        # Backward-compatible history path. These values remain explicitly
        # ineligible; they are not upgraded merely because the browser sent
        # a positive boolean or a result snapshot.
        merged_attempts = max(existing["attempts"], progress.attempts)
        merged_best_tone = max(existing["best_tone"], progress.bestTone)
        merged_best_fluency = max(existing["best_fluency"], progress.bestFluency)
        merged_mastery_passed = bool(existing["mastery_passed"] or progress.masteryPassed)
        merged_content_passed = bool(existing["content_passed"] or progress.contentPassed)
        if progress.attempts > existing["attempts"]:
            merged_cleared_words = _merge_cleared_words([], progress.clearedWords)
        elif progress.attempts == existing["attempts"]:
            merged_cleared_words = _merge_cleared_words(existing["cleared_words"], progress.clearedWords)
        else:
            merged_cleared_words = _merge_cleared_words(existing["cleared_words"], [])
        if latest_result is None:
            merged_latest_result = existing["latest_result"]
        elif progress.attempts < existing["attempts"]:
            merged_latest_result = existing["latest_result"]
        else:
            merged_latest_result = _merge_latest_result(
                existing["latest_result"], latest_result,
                same_attempt=progress.attempts == existing["attempts"],
            )
        merged_verified_record_id = None
    else:
        merged_attempts = progress.attempts
        merged_best_tone = progress.bestTone
        merged_best_fluency = progress.bestFluency
        merged_mastery_passed = progress.masteryPassed
        merged_content_passed = progress.contentPassed
        merged_cleared_words = _merge_cleared_words([], progress.clearedWords)
        merged_latest_result = latest_result
        merged_verified_record_id = None

    repo.upsert_progress(
        db,
        id=row_id,
        student_id=progress.studentId,
        topic_id=progress.topicId,
        scene_index=progress.sceneIndex,
        attempts=merged_attempts,
        best_tone=merged_best_tone,
        best_fluency=merged_best_fluency,
        mastery_passed=merged_mastery_passed,
        content_passed=merged_content_passed,
        cleared_words=merged_cleared_words,
        latest_result=merged_latest_result,
        verified_audio_record_id=merged_verified_record_id,
        conversation_id=progress.conversationId,
        turn_id=progress.turnId,
        turn_index=progress.turnIndex,
    )
    progress.attempts = merged_attempts
    progress.bestTone = merged_best_tone
    progress.bestFluency = merged_best_fluency
    progress.masteryPassed = merged_mastery_passed
    progress.contentPassed = merged_content_passed
    progress.clearedWords = merged_cleared_words
    progress.latestResult = merged_latest_result
    progress.verifiedAudioRecordId = merged_verified_record_id
