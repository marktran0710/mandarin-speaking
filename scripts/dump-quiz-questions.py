"""Dump every AI-generated quiz question in the story database to JSON.

The vocabulary quiz never stores finished questions — the backend AI
endpoints (/api/vocab-quiz-distractors, -cloze, -synonym, -lookalike) store
per-word *material* on each frame, and StoryVocabQuiz assembles a question
from it at run time. This script reads that material out of the database and
renders it as the concrete questions a student can be asked, mirroring
collectQuizEntries' validity filters and applyExclusionsToWord's
teacher-marked exclusions so the dump matches what the quiz would actually
serve.

Run: python scripts/dump-quiz-questions.py [--db backend/mandarin_stories.db]
                                           [--out quiz-questions.json]
"""

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CLOZE_BLANK = "＿＿＿"
# StoryVocabQuiz.tsx: options per question (1 correct + up to 3 wrong).
OPTION_COUNT = 4


def split_list(raw):
    return [w.strip() for w in (raw or "").split(",") if w.strip()]


def load_json_field(raw):
    if not raw or not raw.strip():
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def is_excluded(exclusions, word, kind, index=None):
    return any(
        e.get("word") == word
        and e.get("kind") == kind
        and (e.get("index") is None or e.get("index") == index)
        for e in exclusions
    )


def word_questions(word, translation, material, exclusions):
    """Every question the quiz could build for one word, AI material only."""
    questions = []

    # ── translation: word -> English, AI near-miss distractors ────────────
    distractors = [d for d in material["distractors"] if d and d != translation]
    if not is_excluded(exclusions, word, "distractors"):
        if distractors:
            questions.append(
                {
                    "kind": "translation",
                    "tiers": [2, 3],  # tier 1 deliberately skips AI distractors
                    "prompt": word,
                    "promptEn": f'What does "{word}" mean?',
                    "answer": translation,
                    "aiWrongOptions": distractors[: OPTION_COUNT - 1],
                    "optionSource": "AI distractors first, then other story words, then filler",
                }
            )

    # ── cloze: blank the word in an AI-written sentence ───────────────────
    for i, candidate in enumerate(material["cloze"]):
        sentence = candidate.get("sentence", "")
        wrong = [d for d in candidate.get("distractors", []) if d and d != word]
        # collectQuizEntries drops candidates with no distractor or whose
        # sentence uses the word more than once (the blank would leak).
        if not wrong or sentence.count(word) != 1:
            continue
        if is_excluded(exclusions, word, "cloze", i):
            continue
        questions.append(
            {
                "kind": "cloze",
                "tiers": [2, 3],
                "prompt": sentence.replace(word, CLOZE_BLANK, 1),
                "promptEn": "Which word fills the blank?",
                "answer": word,
                "aiWrongOptions": wrong[: OPTION_COUNT - 1],
                "sourceSentence": sentence,
                "poolIndex": i,
                "optionSource": "AI distractors first, then other story words",
            }
        )

    # ── synonym: which word means the same? ───────────────────────────────
    for i, candidate in enumerate(material["synonym"]):
        synonym = candidate.get("synonym", "")
        wrong = [d for d in candidate.get("distractors", []) if d and d != synonym]
        if not synonym or synonym == word or not wrong:
            continue
        if is_excluded(exclusions, word, "synonym", i):
            continue
        questions.append(
            {
                "kind": "synonym",
                "tiers": [2, 3],
                "prompt": word,
                "promptEn": f'Which word means the same as "{word}"?',
                "answer": synonym,
                "aiWrongOptions": wrong[: OPTION_COUNT - 1],
                "poolIndex": i,
                "optionSource": "AI non-synonyms first, then other story words",
            }
        )

    # ── look-alike traps: fed into tier-3 reverse/listening options ───────
    lookalikes = [l for l in material["lookalike"] if l and l != word]
    if lookalikes and not is_excluded(exclusions, word, "lookalike"):
        questions.append(
            {
                "kind": "reverse-lookalike",
                "tiers": [3],
                "prompt": translation,
                "promptEn": f'Which word means "{translation}"? (also asked as a listening question)',
                "answer": word,
                "aiWrongOptions": lookalikes[: OPTION_COUNT - 1],
                "optionSource": "AI look-alike traps first, then other story words",
            }
        )

    return questions


def dump(db_path: Path):
    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    rows = db.execute(
        "SELECT id, title, published, lesson_number, frames, quiz_exclusions "
        "FROM custom_stories ORDER BY lesson_number, created_at"
    ).fetchall()

    stories = []
    total_questions = 0
    for row in rows:
        exclusions = load_json_field(row["quiz_exclusions"])
        frames = json.loads(row["frames"] or "[]")
        scenes = []
        seen_words = set()  # collectQuizEntries dedupes across the whole story
        story_questions = 0

        for si, frame in enumerate(frames):
            words = split_list(frame.get("vocabulary"))
            translations = split_list(frame.get("vocabularyTranslation"))
            pinyins = split_list(frame.get("vocabularyPinyin"))
            pos = split_list(frame.get("vocabularyPos"))
            distractors = load_json_field(frame.get("vocabularyDistractors"))
            cloze = load_json_field(frame.get("vocabularyCloze"))
            synonym = load_json_field(frame.get("vocabularySynonym"))
            lookalike = load_json_field(frame.get("vocabularyLookalike"))
            context = (frame.get("suggestedAnswer") or "").strip()

            entries = []
            for i, word in enumerate(words):
                translation = translations[i].strip() if i < len(translations) else ""
                # collectQuizEntries: needs a gloss, must appear in the scene's
                # sentence, first occurrence in the story wins.
                if not translation or word in seen_words:
                    continue
                if context and word not in context:
                    continue
                seen_words.add(word)
                if is_excluded(exclusions, word, "word"):
                    continue

                material = {
                    "distractors": distractors[i] if i < len(distractors) else [],
                    "cloze": cloze[i] if i < len(cloze) else [],
                    "synonym": synonym[i] if i < len(synonym) else [],
                    "lookalike": lookalike[i] if i < len(lookalike) else [],
                }
                questions = word_questions(word, translation, material, exclusions)
                if not questions:
                    continue
                story_questions += len(questions)
                entries.append(
                    {
                        "word": word,
                        "pinyin": pinyins[i] if i < len(pinyins) else None,
                        "pos": pos[i] if i < len(pos) else None,
                        "translation": translation,
                        "questions": questions,
                    }
                )

            if entries:
                scenes.append(
                    {
                        "scene": si + 1,
                        "prompt": (frame.get("prompt") or "").strip(),
                        "suggestedAnswer": context,
                        "words": entries,
                    }
                )

        total_questions += story_questions
        stories.append(
            {
                "storyId": row["id"],
                "title": row["title"],
                "lessonNumber": row["lesson_number"],
                "published": bool(row["published"]),
                "questionCount": story_questions,
                "hasAiMaterial": story_questions > 0,
                "scenes": scenes,
            }
        )

    return {
        "meta": {
            "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "source": str(db_path.relative_to(REPO)) if db_path.is_relative_to(REPO) else str(db_path),
            "storyCount": len(stories),
            "questionCount": total_questions,
            "optionCount": OPTION_COUNT,
            "clozeBlank": CLOZE_BLANK,
            "notes": [
                "Questions are assembled at run time by src/components/StoryVocabQuiz.tsx "
                "(buildQuizQuestion) from the per-word AI material dumped here; only the "
                "AI-authored parts are stored.",
                "Wrong options listed as aiWrongOptions are the AI's; the quiz shuffles them "
                "with other story words (and English filler for translation questions) up to "
                "optionCount, so a live question may show fewer AI options than are listed.",
                "Question kinds pinyin, pos, reverse and listening are derived from the "
                "teacher-authored fields with no AI call, so they are not dumped here (except "
                "reverse-lookalike, whose trap options are AI-generated).",
                "AI material is only attached to a difficulty tier that reuses the easy "
                "vocabulary list (see teacherStories.ts) — it is not generated per tier.",
                "Teacher-marked bad material (custom_stories.quiz_exclusions) is filtered out, "
                "matching src/utils/quizExclusions.ts.",
            ],
        },
        "stories": stories,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(REPO / "backend" / "mandarin_stories.db"))
    parser.add_argument("--out", default=str(REPO / "quiz-questions.json"))
    args = parser.parse_args()

    payload = dump(Path(args.db).resolve())
    out = Path(args.out).resolve()
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"Wrote {payload['meta']['questionCount']} questions "
        f"from {payload['meta']['storyCount']} stories to {out}"
    )


if __name__ == "__main__":
    main()
