"""Read-only inventory and consistency checks for curriculum content.

``custom_stories`` is still the compatibility aggregate for authored content.
This module makes its implicit ownership visible without changing that schema:

* ``vocab_assessment`` is the canonical vocabulary/question bank.
* frame and story-wide vocabulary are speaking references.
* frame/conversation media are instructional content.
* ``audio_records`` and ``story_submissions`` are student evidence.

The report is intentionally plain JSON so the CLI and the future Admin Content
Library can consume the same contract. Nothing in this module writes database
rows or media files.
"""

from __future__ import annotations

import json
import mimetypes
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import unquote, urlsplit

from db import connect_db


EXPECTED_ROUNDS = ("easy", "medium", "hard")
METADATA_FIELDS = ("pinyin", "pos", "translation")
_AUDIO_EXTENSIONS = {".aac", ".flac", ".m4a", ".mp3", ".ogg", ".wav", ".webm"}
_IMAGE_EXTENSIONS = {".gif", ".jpeg", ".jpg", ".png", ".svg", ".webp"}


def _normalized(value: object) -> str:
    return " ".join(unicodedata.normalize("NFKC", str(value or "")).split()).casefold()


def _split_aligned(value: object) -> list[str]:
    if not isinstance(value, str):
        return []
    return [part.strip() for part in value.split(",")]


def _indexed(values: Sequence[str], index: int) -> str:
    return values[index] if index < len(values) else ""


def _story_level(story: Mapping[str, Any]) -> Mapping[str, Any]:
    value = story.get("story_vocabulary")
    if not isinstance(value, Mapping):
        return {}
    for key, content in value.items():
        if str(key).casefold() == "easy" and isinstance(content, Mapping):
            return content
    return {}


def _vocabulary_rows(
    value: Mapping[str, Any], *, source: str, location: str
) -> list[dict[str, Any]]:
    words = _split_aligned(value.get("vocabulary"))
    pinyin = _split_aligned(value.get("vocabularyPinyin"))
    pos = _split_aligned(value.get("vocabularyPos"))
    translations = _split_aligned(value.get("vocabularyTranslation"))
    return [
        {
            "word": word,
            "wordKey": _normalized(word),
            "pinyin": _indexed(pinyin, index),
            "pos": _indexed(pos, index),
            "translation": _indexed(translations, index),
            "source": source,
            "location": location,
            "wordIndex": index,
        }
        for index, word in enumerate(words)
        if word
    ]


def _json_string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [item.strip() for item in value if isinstance(item, str) and item.strip()]
    if not isinstance(value, str) or not value.strip():
        return []
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return []
    if not isinstance(parsed, list):
        return []
    return [item.strip() for item in parsed if isinstance(item, str) and item.strip()]


def _media_kind(url: str, role: str) -> str:
    mime = mimetypes.guess_type(urlsplit(url).path)[0] or ""
    suffix = Path(urlsplit(url).path).suffix.casefold()
    if mime.startswith("image/") or suffix in _IMAGE_EXTENSIONS or "image" in role:
        return "image"
    if mime.startswith("audio/") or suffix in _AUDIO_EXTENSIONS or "audio" in role:
        return "audio"
    return "file"


def _local_media(
    url: str, upload_root: Path
) -> tuple[str, Path | None, str | None]:
    """Return (status, path, canonical URL) without reading file content."""
    parsed = urlsplit(url)
    if not parsed.path.startswith("/uploads/"):
        if parsed.scheme in {"http", "https"}:
            return "external", None, None
        if parsed.scheme == "data":
            return "inline", None, None
        return "unsupported", None, None

    relative = PurePosixPath(unquote(parsed.path.removeprefix("/uploads/")))
    candidate = upload_root.joinpath(*relative.parts).resolve()
    try:
        safe_relative = candidate.relative_to(upload_root)
    except ValueError:
        return "invalid", None, None
    canonical_url = f"/uploads/{safe_relative.as_posix()}"
    return ("present" if candidate.is_file() else "missing"), candidate, canonical_url


def _iter_word_references(value: object, path: str = "") -> Iterable[tuple[str, str]]:
    """Find additive future wordId references without treating generic ids as words."""
    if isinstance(value, Mapping):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            if key in {"wordId", "vocabularyItemId"} and isinstance(child, str):
                yield child.strip(), child_path
            else:
                yield from _iter_word_references(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _iter_word_references(child, f"{path}[{index}]")


def build_content_inventory(
    stories: Iterable[Mapping[str, Any]],
    *,
    upload_dir: str | Path,
    audio_records: Iterable[Mapping[str, Any]] = (),
    story_submissions: Iterable[Mapping[str, Any]] = (),
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build a deterministic report from already-loaded database records."""
    upload_root = Path(upload_dir).resolve()
    findings: list[dict[str, Any]] = []
    media_references: list[dict[str, Any]] = []
    referenced_local_urls: set[str] = set()
    lessons: list[dict[str, Any]] = []

    def add_finding(
        code: str,
        severity: str,
        *,
        story: Mapping[str, Any] | None = None,
        location: str = "",
        detail: object = None,
        owner_type: str | None = None,
        owner_id: str | None = None,
    ) -> dict[str, Any]:
        finding = {
            "code": code,
            "severity": severity,
            "storyId": story.get("id") if story else None,
            "location": location,
            "detail": detail,
        }
        if owner_type:
            finding["ownerType"] = owner_type
        if owner_id:
            finding["ownerId"] = owner_id
        findings.append(finding)
        return finding

    def add_media(
        url: object,
        *,
        domain: str,
        owner_type: str,
        owner_id: str,
        role: str,
        location: str,
        story: Mapping[str, Any] | None = None,
    ) -> None:
        if not isinstance(url, str) or not url.strip():
            return
        clean_url = url.strip()
        kind = _media_kind(clean_url, role)
        status, local_path, canonical_url = _local_media(clean_url, upload_root)
        if canonical_url:
            referenced_local_urls.add(canonical_url)
        item: dict[str, Any] = {
            "url": clean_url,
            "domain": domain,
            "ownerType": owner_type,
            "ownerId": owner_id,
            "role": role,
            "kind": kind,
            "location": location,
            "status": status,
        }
        if local_path is not None and local_path.is_file():
            item["bytes"] = local_path.stat().st_size
            item["mimeType"] = mimetypes.guess_type(local_path.name)[0]
        media_references.append(item)
        if status == "missing":
            add_finding(
                "broken_image" if kind == "image" else "missing_audio_file" if kind == "audio" else "missing_media_file",
                "error" if story and story.get("published") else "warning",
                story=story,
                location=location,
                detail={"url": clean_url, "role": role},
                owner_type=owner_type,
                owner_id=owner_id,
            )
        elif status in {"invalid", "unsupported"}:
            add_finding(
                "invalid_media_reference",
                "error",
                story=story,
                location=location,
                detail={"url": clean_url, "role": role},
                owner_type=owner_type,
                owner_id=owner_id,
            )

    ordered_stories = sorted(
        (dict(story) for story in stories),
        key=lambda story: (
            story.get("lesson_number") is None,
            story.get("lesson_number") or 0,
            story.get("lesson_sub_order") is None,
            story.get("lesson_sub_order") or 0,
            str(story.get("id") or ""),
        ),
    )
    for story in ordered_stories:
        story_findings_start = len(findings)
        story_id = str(story.get("id") or "")
        published = bool(story.get("published"))
        error_severity = "error" if published else "warning"
        assessment = story.get("vocab_assessment")
        questions = assessment if isinstance(assessment, list) else []
        if assessment is not None and not isinstance(assessment, list):
            add_finding(
                "invalid_canonical_bank",
                error_severity,
                story=story,
                location="vocab_assessment",
                detail="Expected a list of questions.",
            )

        questions_by_word: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for index, question in enumerate(questions):
            location = f"vocab_assessment[{index}]"
            if not isinstance(question, Mapping):
                add_finding(
                    "invalid_word_ref",
                    error_severity,
                    story=story,
                    location=location,
                    detail="Question is not an object.",
                )
                continue
            word_id = str(question.get("wordId") or "").strip()
            target_word = str(question.get("targetWord") or "").strip()
            if not word_id or not target_word:
                add_finding(
                    "invalid_word_ref",
                    error_severity,
                    story=story,
                    location=location,
                    detail={"wordId": word_id, "targetWord": target_word},
                )
                continue
            questions_by_word[word_id].append(dict(question))

        canonical_rows: list[dict[str, Any]] = []
        target_to_ids: dict[str, set[str]] = defaultdict(set)
        for word_id, word_questions in questions_by_word.items():
            target_variants = {
                _normalized(question.get("targetWord")): str(question.get("targetWord") or "").strip()
                for question in word_questions
                if _normalized(question.get("targetWord"))
            }
            if len(target_variants) > 1:
                add_finding(
                    "duplicate_word_id",
                    error_severity,
                    story=story,
                    location="vocab_assessment",
                    detail={"wordId": word_id, "targetWords": sorted(target_variants.values())},
                )
            levels = Counter(_normalized(question.get("level")) for question in word_questions)
            for level in EXPECTED_ROUNDS:
                if levels[level] == 0:
                    add_finding(
                        "missing_round_question",
                        error_severity,
                        story=story,
                        location="vocab_assessment",
                        detail={"wordId": word_id, "level": level},
                    )
                elif levels[level] > 1:
                    add_finding(
                        "duplicate_word_round",
                        error_severity,
                        story=story,
                        location="vocab_assessment",
                        detail={"wordId": word_id, "level": level, "count": levels[level]},
                    )
            first = word_questions[0]
            target = str(first.get("targetWord") or "").strip()
            target_key = _normalized(target)
            target_to_ids[target_key].add(word_id)
            canonical_rows.extend(
                {
                    "wordId": word_id,
                    "word": str(question.get("targetWord") or "").strip(),
                    "wordKey": _normalized(question.get("targetWord")),
                    "pinyin": str(question.get("pinyin") or "").strip(),
                    "pos": str(question.get("pos") or "").strip(),
                    "translation": str(question.get("simpleEnglishMeaning") or "").strip(),
                    "source": "vocab_assessment",
                    "location": f"vocab_assessment[{index}]",
                }
                for index, question in enumerate(word_questions)
            )
        for target_key, word_ids in target_to_ids.items():
            if target_key and len(word_ids) > 1:
                add_finding(
                    "duplicate_canonical_word",
                    "warning",
                    story=story,
                    location="vocab_assessment",
                    detail={"targetWord": target_key, "wordIds": sorted(word_ids)},
                )

        frames = story.get("frames") if isinstance(story.get("frames"), list) else []
        speaking_rows: list[dict[str, Any]] = []
        for frame_index, frame_value in enumerate(frames):
            if not isinstance(frame_value, Mapping):
                continue
            frame = dict(frame_value)
            speaking_rows.extend(
                _vocabulary_rows(
                    frame,
                    source="frame_vocabulary",
                    location=f"frames[{frame_index}]",
                )
            )
            for word_ref, path in _iter_word_references(frame):
                if not word_ref or word_ref not in questions_by_word:
                    add_finding(
                        "invalid_word_ref",
                        error_severity,
                        story=story,
                        location=f"frames[{frame_index}].{path}",
                        detail={"wordId": word_ref},
                    )

            add_media(
                frame.get("imageUrl"),
                domain="instructional_content",
                owner_type="story",
                owner_id=story_id,
                role="frame_image",
                location=f"frames[{frame_index}].imageUrl",
                story=story,
            )
            listen_audio = str(frame.get("listenAudioUrl") or "").strip()
            add_media(
                listen_audio,
                domain="instructional_content",
                owner_type="story",
                owner_id=story_id,
                role="scene_model_audio",
                location=f"frames[{frame_index}].listenAudioUrl",
                story=story,
            )
            vocabulary_audio = _json_string_list(frame.get("vocabularyAudioUrls"))
            for audio_index, url in enumerate(vocabulary_audio):
                add_media(
                    url,
                    domain="instructional_content",
                    owner_type="story",
                    owner_id=story_id,
                    role="vocabulary_reference_audio",
                    location=f"frames[{frame_index}].vocabularyAudioUrls[{audio_index}]",
                    story=story,
                )
            if vocabulary_audio and not listen_audio:
                add_finding(
                    "reference_audio_without_source_audio",
                    error_severity,
                    story=story,
                    location=f"frames[{frame_index}].vocabularyAudioUrls",
                    detail={"referenceCount": len(vocabulary_audio)},
                )

        story_level = _story_level(story)
        if story_level:
            speaking_rows.extend(
                _vocabulary_rows(
                    story_level,
                    source="story_vocabulary",
                    location="story_vocabulary.easy",
                )
            )

        canonical_word_keys = {row["wordKey"] for row in canonical_rows if row["wordKey"]}
        speaking_word_keys = {row["wordKey"] for row in speaking_rows if row["wordKey"]}
        speaking_by_key: dict[str, list[dict[str, Any]]] = defaultdict(list)
        canonical_by_key: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in speaking_rows:
            speaking_by_key[row["wordKey"]].append(row)
        for row in canonical_rows:
            canonical_by_key[row["wordKey"]].append(row)

        for word_key in sorted(speaking_word_keys - canonical_word_keys):
            row = speaking_by_key[word_key][0]
            add_finding(
                "speaking_word_missing_canonical_bank",
                error_severity,
                story=story,
                location=row["location"],
                detail={"word": row["word"], "source": row["source"]},
            )
        for word_key in sorted(canonical_word_keys - speaking_word_keys):
            row = canonical_by_key[word_key][0]
            add_finding(
                "quiz_word_missing_speaking",
                error_severity,
                story=story,
                location="vocab_assessment",
                detail={"word": row["word"], "wordId": row["wordId"]},
            )

        for word_key in sorted(canonical_word_keys & speaking_word_keys):
            rows = canonical_by_key[word_key] + speaking_by_key[word_key]
            for field in METADATA_FIELDS:
                variants: dict[str, list[dict[str, str]]] = defaultdict(list)
                for row in rows:
                    raw = str(row.get(field) or "").strip()
                    if raw:
                        variants[_normalized(raw)].append(
                            {"value": raw, "source": row["source"], "location": row["location"]}
                        )
                if len(variants) > 1:
                    add_finding(
                        "conflicting_vocabulary_metadata",
                        "warning",
                        story=story,
                        location="vocabulary",
                        detail={
                            "word": rows[0]["word"],
                            "field": field,
                            "variants": [items[0] for items in variants.values()],
                        },
                    )

        conversation_turns = (
            story.get("conversation_turns")
            if isinstance(story.get("conversation_turns"), list)
            else []
        )
        for turn_index, turn_value in enumerate(conversation_turns):
            if not isinstance(turn_value, Mapping):
                continue
            turn = dict(turn_value)
            location = f"conversation_turns[{turn_index}]"
            if turn.get("speaker") == "system" and not str(turn.get("audioUrl") or "").strip():
                add_finding(
                    "conversation_missing_character_audio",
                    error_severity,
                    story=story,
                    location=f"{location}.audioUrl",
                    detail={"turnId": turn.get("id")},
                )
            add_media(
                turn.get("audioUrl"),
                domain="instructional_content",
                owner_type="story",
                owner_id=story_id,
                role="conversation_character_audio",
                location=f"{location}.audioUrl",
                story=story,
            )
            add_media(
                turn.get("targetAudioUrl"),
                domain="instructional_content",
                owner_type="story",
                owner_id=story_id,
                role="conversation_target_audio",
                location=f"{location}.targetAudioUrl",
                story=story,
            )

        story_findings = findings[story_findings_start:]
        lessons.append(
            {
                "storyId": story_id,
                "title": story.get("title") or "",
                "lessonNumber": story.get("lesson_number"),
                "lessonSubOrder": story.get("lesson_sub_order"),
                "published": published,
                "sources": {
                    "canonicalVocabulary": "custom_stories.vocab_assessment",
                    "speakingVocabulary": ["custom_stories.frames", "custom_stories.story_vocabulary"],
                    "conversation": "custom_stories.conversation_turns",
                },
                "counts": {
                    "frames": len(frames),
                    "canonicalWords": len(questions_by_word),
                    "quizQuestions": len(questions),
                    "speakingWords": len(speaking_word_keys),
                    "conversationTurns": len(conversation_turns),
                    "findings": len(story_findings),
                },
                "findings": story_findings,
            }
        )

    for row in audio_records:
        owner_id = str(row.get("id") or "")
        add_media(
            row.get("audio_url"),
            domain="student_evidence",
            owner_type="audio_record",
            owner_id=owner_id,
            role="student_attempt_audio",
            location="audio_records.audio_url",
        )
        add_media(
            row.get("image_url"),
            domain="student_evidence",
            owner_type="audio_record",
            owner_id=owner_id,
            role="evidence_context_image",
            location="audio_records.image_url",
        )

    for row in story_submissions:
        owner_id = str(row.get("id") or "")
        add_media(
            row.get("concatenated_audio_url"),
            domain="student_evidence",
            owner_type="story_submission",
            owner_id=owner_id,
            role="final_submission_audio",
            location="story_submissions.concatenated_audio_url",
        )
        scenes = row.get("scenes") if isinstance(row.get("scenes"), list) else []
        for scene_index, scene in enumerate(scenes):
            if not isinstance(scene, Mapping):
                continue
            add_media(
                scene.get("audioUrl"),
                domain="student_evidence",
                owner_type="story_submission",
                owner_id=owner_id,
                role="submission_scene_audio",
                location=f"story_submissions.scenes[{scene_index}].audioUrl",
            )
            add_media(
                scene.get("imageUrl"),
                domain="student_evidence",
                owner_type="story_submission",
                owner_id=owner_id,
                role="submission_context_image",
                location=f"story_submissions.scenes[{scene_index}].imageUrl",
            )

    orphan_files: list[dict[str, Any]] = []
    if upload_root.is_dir():
        for path in sorted((item for item in upload_root.rglob("*") if item.is_file())):
            url = f"/uploads/{path.relative_to(upload_root).as_posix()}"
            if url in referenced_local_urls:
                continue
            kind = _media_kind(url, "")
            orphan = {
                "url": url,
                "kind": kind,
                "bytes": path.stat().st_size,
                "mimeType": mimetypes.guess_type(path.name)[0],
            }
            orphan_files.append(orphan)
            add_finding(
                "orphan_media_file",
                "warning",
                location=url,
                detail=orphan,
                owner_type="unowned_upload",
                owner_id=url,
            )

    by_code = dict(sorted(Counter(finding["code"] for finding in findings).items()))
    by_severity = dict(sorted(Counter(finding["severity"] for finding in findings).items()))
    media_by_domain = dict(sorted(Counter(item["domain"] for item in media_references).items()))
    media_by_status = dict(sorted(Counter(item["status"] for item in media_references).items()))
    return {
        "generatedAt": generated_at or datetime.now(timezone.utc).isoformat(),
        "readOnly": True,
        "ownership": {
            "canonicalVocabulary": "custom_stories.vocab_assessment",
            "instructionalContent": "custom_stories",
            "studentAttempts": "audio_records",
            "finalSubmissions": "story_submissions",
            "derivedAnalytics": "excluded",
            "researchData": "excluded",
        },
        "summary": {
            "stories": len(ordered_stories),
            "publishedStories": sum(bool(story.get("published")) for story in ordered_stories),
            "canonicalWords": sum(lesson["counts"]["canonicalWords"] for lesson in lessons),
            "quizQuestions": sum(lesson["counts"]["quizQuestions"] for lesson in lessons),
            "mediaReferences": len(media_references),
            "mediaByDomain": media_by_domain,
            "mediaByStatus": media_by_status,
            "orphanFiles": len(orphan_files),
            "findings": len(findings),
            "findingsBySeverity": by_severity,
            "findingsByCode": by_code,
        },
        "lessons": lessons,
        "media": {"references": media_references, "orphanFiles": orphan_files},
        "findings": findings,
    }


def build_content_inventory_from_database(*, upload_dir: str | Path) -> dict[str, Any]:
    """Load the current compatibility tables and run the read-only doctor."""
    with connect_db() as db:
        stories = db.execute(
            """
            SELECT id, title, lesson_number, lesson_sub_order, published, frames,
                   story_vocabulary, story_phrases, vocab_assessment,
                   conversation_turns
            FROM custom_stories
            ORDER BY lesson_number NULLS LAST, lesson_sub_order NULLS LAST, created_at, id
            """
        ).fetchall()
        audio_records = db.execute(
            """
            SELECT id, audio_url, image_url
            FROM audio_records
            WHERE audio_url IS NOT NULL OR image_url IS NOT NULL
            """
        ).fetchall()
        story_submissions = db.execute(
            """
            SELECT id, concatenated_audio_url, scenes
            FROM story_submissions
            WHERE concatenated_audio_url IS NOT NULL OR scenes <> '[]'::jsonb
            """
        ).fetchall()
    return build_content_inventory(
        stories,
        upload_dir=upload_dir,
        audio_records=audio_records,
        story_submissions=story_submissions,
    )
