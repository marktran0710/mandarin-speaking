"""One-time backfill for custom_stories.quiz_approved_snapshot.

Once storyToTopic's "approved" serving mode ships, a student's quiz is built
ONLY from quiz_approved_snapshot — never from the live per-word fields. A
story that has never been through the new "Approve & Publish" action would
suddenly lose every AI-generated question (distractors/cloze/synonym/
lookalike) it serves today, which is a real regression, not a quality
improvement.

This script closes that gap once: for every story and every tier that
actually shows content (easy always; medium/hard only when authored — same
storyHasTierContent gate the student-facing level picker uses), it copies
today's live AI material into quiz_approved_snapshot exactly as-is. Nothing
about what a student sees changes; only where it's read from does. Mirrors
storyToTopic's tier-fallback rules (see teacherStories.ts) precisely, since
this is standing in for a teacher's first "Approve & Publish" that never
happened.

A later "Quiz Review" pass by a teacher (Validate -> exclude/keep ->
Approve & Publish) is what starts actually vetting this material; this
script only prevents a silent regression on the day the gate ships.

Run: python scripts/backfill-quiz-approved-snapshot.py [--dry-run]
"""

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend"))

from database import connect_db  # noqa: E402
from psycopg.types.json import Jsonb  # noqa: E402

TIERS = ("easy", "medium", "hard")
TIER_SUFFIX = {"easy": "", "medium": "Medium", "hard": "Hard"}
TIER_FIELDS = (
    "prompt",
    "vocabulary",
    "vocabularyPinyin",
    "vocabularyPos",
    "vocabularyTranslation",
    "phrases",
    "phrasesTranslation",
    "suggestedAnswer",
    "listenAudioUrl",
    "listenScript",
)


def split_list(raw):
    return [w.strip() for w in (raw or "").split(",") if w.strip()]


def load_json_field(raw):
    if not raw or not str(raw).strip():
        return []
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    return parsed if isinstance(parsed, list) else []


def story_has_tier_content(frames, level: str) -> bool:
    """Mirrors teacherStories.ts's storyHasTierContent — whether any frame
    has its OWN text for this tier, not merely a fallback to Easy."""
    suffix = TIER_SUFFIX[level]
    for frame in frames:
        for base in TIER_FIELDS:
            value = frame.get(f"{base}{suffix}")
            if value and str(value).strip():
                return True
    return False


def tier_uses_easy_vocabulary(frame: dict, level: str) -> bool:
    """Mirrors storyToTopic's tierUsesEasyVocabulary: AI material is only
    keyed to the Easy word list, so it only carries over to a tier whose
    OWN vocabulary field is empty (that tier is showing Easy's words)."""
    if level == "easy":
        return True
    suffix = TIER_SUFFIX[level]
    return not (frame.get(f"vocabulary{suffix}") or "").strip()


def snapshot_for_tier(frames: list, level: str) -> list[dict]:
    entries = []
    for frame in frames:
        base_words = split_list(frame.get("vocabulary"))
        if level == "easy":
            words = base_words
        else:
            suffix = TIER_SUFFIX[level]
            tier_vocab = (frame.get(f"vocabulary{suffix}") or "").strip()
            words = split_list(tier_vocab) if tier_vocab else base_words

        if not words:
            continue

        translations = split_list(frame.get("vocabularyTranslation"))
        use_easy_material = tier_uses_easy_vocabulary(frame, level)
        distractors = load_json_field(frame.get("vocabularyDistractors")) if use_easy_material else []
        cloze = load_json_field(frame.get("vocabularyCloze")) if use_easy_material else []
        synonym = load_json_field(frame.get("vocabularySynonym")) if use_easy_material else []
        lookalike = load_json_field(frame.get("vocabularyLookalike")) if use_easy_material else []

        for i, word in enumerate(words):
            entries.append(
                {
                    "word": word,
                    "translation": translations[i] if i < len(translations) else None,
                    "distractors": distractors[i] if i < len(distractors) else [],
                    "cloze": cloze[i] if i < len(cloze) else [],
                    "synonym": synonym[i] if i < len(synonym) else [],
                    "lookalike": lookalike[i] if i < len(lookalike) else [],
                }
            )
    return entries


def backfill(dry_run: bool) -> None:
    with connect_db() as db:
        rows = db.execute(
            "SELECT id, title, frames, quiz_approved_snapshot FROM custom_stories"
        ).fetchall()

        updated = 0
        for row in rows:
            if row["quiz_approved_snapshot"]:
                continue  # already has an approved snapshot — a teacher has acted since; leave it alone

            frames = row["frames"] or []
            snapshot = {"easy": snapshot_for_tier(frames, "easy")}
            for level in ("medium", "hard"):
                if story_has_tier_content(frames, level):
                    snapshot[level] = snapshot_for_tier(frames, level)

            total_words = sum(len(v) for v in snapshot.values())
            print(f"{'[dry-run] ' if dry_run else ''}{row['id']} ({row['title']!r}): "
                  f"{', '.join(f'{k}={len(v)}' for k, v in snapshot.items())} words")

            if not dry_run:
                db.execute(
                    "UPDATE custom_stories SET quiz_approved_snapshot = %s WHERE id = %s",
                    (Jsonb(snapshot), row["id"]),
                )
            updated += 1

        print(f"\n{'Would update' if dry_run else 'Updated'} {updated} of {len(rows)} stories.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Print what would change without writing.")
    args = parser.parse_args()
    backfill(args.dry_run)


if __name__ == "__main__":
    main()
