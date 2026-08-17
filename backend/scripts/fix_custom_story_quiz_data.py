"""Curate the live custom-story vocabulary quiz material.

This migration is intentionally conservative: questionable synonym material is
removed instead of being shown as a potentially wrong answer, cloze sentences
must contain the target exactly once, and approved AI snapshots are invalidated
so teachers can review fresh material before it is served again.

Run from ``backend/`` with::

    python -m scripts.fix_custom_story_quiz_data
"""

from __future__ import annotations

import json
import os

import psycopg


DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://mandarin:mandarin@127.0.0.1:5432/mandarin"
)
CUSTOM_STORY_PREFIX = "custom-story-"
MODERN_STORY_PREFIX = "modern-chinese-"

# Labels shared by the teacher UI and the quiz generator.  Existing N/V/Adj/Adv
# labels are retained; these additions cover the actual live vocabulary.
POS_BY_WORD = {
    "我": "Pron", "你": "Pron", "妳": "Pron", "我們": "Pron", "妳們": "Pron",
    "在": "Prep", "可是": "Conj", "很多": "Quant", "好多": "Quant",
    "兩點半": "Time", "六點": "Time", "上面": "Loc", "下面": "Loc", "旁邊": "Loc",
    "中文": "N", "英文": "N", "不": "Adv", "跑步": "V", "會": "Vaux", "不會": "Vaux",
}

# The seeded Modern Chinese lessons had vocabulary words but no gloss metadata.
# These are the 39 unique words used by those nine published lessons.
MODERN_VOCAB = {
    "朋友": ("péngyǒu", "N", "friend"),
    "音樂": ("yīnyuè", "N", "music"),
    "中文": ("zhōngwén", "N", "Chinese"),
    "唱歌": ("chànggē", "V", "to sing"),
    "運動": ("yùndòng", "N", "exercise"),
    "週末": ("zhōumò", "N", "weekend"),
    "游泳": ("yóuyǒng", "V", "to swim"),
    "網球": ("wǎngqiú", "N", "tennis"),
    "衣服": ("yīfu", "N", "clothes"),
    "百貨公司": ("bǎihuò gōngsī", "N", "department store"),
    "鞋子": ("xiézi", "N", "shoes"),
    "東西": ("dōngxi", "N", "thing"),
    "年輕": ("niánqīng", "Adj", "young"),
    "漂亮": ("piàoliang", "Adj", "beautiful"),
    "流行": ("liúxíng", "Adj", "popular"),
    "有趣": ("yǒuqù", "Adj", "interesting"),
    "錢": ("qián", "N", "money"),
    "裙子": ("qúnzi", "N", "skirt"),
    "生日": ("shēngrì", "N", "birthday"),
    "褲子": ("kùzi", "N", "pants"),
    "捷運": ("jiéyùn", "N", "MRT"),
    "附近": ("fùjìn", "N", "nearby"),
    "學校": ("xuéxiào", "N", "school"),
    "電影": ("diànyǐng", "N", "movie"),
    "方便": ("fāngbiàn", "Adj", "convenient"),
    "機場": ("jīchǎng", "N", "airport"),
    "風景": ("fēngjǐng", "N", "scenery"),
    "電梯": ("diàntī", "N", "elevator"),
    "飯店": ("fàndiàn", "N", "hotel"),
    "公車": ("gōngchē", "N", "bus"),
    "走路": ("zǒulù", "V", "to walk"),
    "地圖": ("dìtú", "N", "map"),
    "天氣": ("tiānqì", "N", "weather"),
    "跑步": ("pǎobù", "V", "to jog"),
    "休息": ("xiūxi", "V", "to rest"),
    "腳踏車": ("jiǎotàchē", "N", "bicycle"),
    "郵局": ("yóujú", "N", "post office"),
    "超級市場": ("chāojí shìchǎng", "N", "supermarket"),
    "舒服": ("shūfu", "Adj", "comfortable"),
}

# Only retain synonyms that were manually checked for this beginner curriculum.
# An absent word intentionally gets no synonym question until a teacher adds one.
APPROVED_SYNONYMS = {
    "媽": {"母親"}, "錢包": {"錢夾"}, "哥哥": {"兄長"}, "下面": {"底下"},
    "上面": {"頂上"}, "旁邊": {"旁側"}, "忙": {"忙碌"}, "做飯": {"烹飪"},
    "啊": {"哦"}, "在這裡": {"在此"}, "書": {"書籍"}, "看書": {"閱讀"},
    "聽音樂": {"聆聽"}, "下午": {"午後"}, "有空": {"有時間"}, "一起": {"共同"},
    "喝": {"飲"}, "哪裡": {"何處"}, "去": {"前往"}, "知道": {"曉得"},
    "咖啡廳": {"咖啡店"}, "好吃": {"美味"}, "很多": {"大量"}, "好": {"很好", "良好"},
    "不錯": {"還行"}, "海邊": {"海灘"}, "風景": {"景色"}, "漂亮": {"美麗"},
    "會": {"能"}, "可是": {"但是"}, "不太好": {"不好"}, "怎麼樣": {"如何"},
    "喜歡": {"愛好"}, "很": {"非常"}, "慢": {"緩慢"}, "電視機": {"電視"},
    "看電視": {"觀看電視"}, "中文": {"漢語"}, "英文": {"英語"}, "窗戶": {"窗"},
    "大": {"巨大"}, "有": {"具有"},
}

# The old generated cloze questions used repeated targets.  These replacements
# retain the intended meaning while making the blank unambiguous.
CLOZE_REPLACEMENTS = {
    ("custom-story-1785137028726", 7, "有"): "他們有很多種冰淇淋。",
    ("custom-story-1785204635939", 2, "我"): "我不會游泳。",
    ("custom-story-1785204635939", 3, "我"): "我會游泳，但是游得不太好。",
    ("custom-story-1785204635939", 4, "去"): "我們想去海邊玩。",
    ("custom-story-1785204635939", 5, "我"): "我不喜歡跑步。",
    ("custom-story-1785204635939", 5, "不"): "我不喜歡跑步。",
    ("custom-story-1785204635939", 5, "喜歡"): "我喜歡游泳。",
    ("custom-story-1785204635939", 5, "跑"): "我跑得很慢。",
    ("custom-story-1785204635939", 7, "好"): "這項運動很好。",
}

PROMPT_REPLACEMENTS = {
    ("custom-story-1785065694751", 7): "Finish by saying where the wallet is.",
    ("custom-story-1785137028726", 7): "Add the detail about the ice-cream choices.",
    ("custom-story-1785137028726", 8): "Add the meeting time.",
    ("custom-story-1785137028726", 9): "Confirm the plan.",
    ("custom-story-1785204635939", 7): "Finish with a short agreement.",
    ("custom-story-1785235297869", 7): "Finish by saying where the wallet is.",
}


def split_csv(value: object) -> list[str]:
    if not isinstance(value, str):
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def parse_json_array(value: object) -> list:
    if not isinstance(value, str) or not value.strip():
        return []
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return []
    return parsed if isinstance(parsed, list) else []


def dump_json(value: list) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def normalize_outer_length(items: list, size: int) -> list[list]:
    normalized = [item if isinstance(item, list) else [] for item in items[:size]]
    return normalized + [[] for _ in range(size - len(normalized))]


def normalize_pos_fields(frame: dict) -> bool:
    changed = False
    for words_key, pos_key in (
        ("vocabulary", "vocabularyPos"),
        ("vocabularyMedium", "vocabularyPosMedium"),
        ("vocabularyHard", "vocabularyPosHard"),
    ):
        words = split_csv(frame.get(words_key))
        positions = split_csv(frame.get(pos_key))
        if not words or not positions:
            continue
        normalized = [POS_BY_WORD.get(word, pos) for word, pos in zip(words, positions)]
        normalized.extend(positions[len(normalized) :])
        replacement = ", ".join(normalized)
        if replacement != frame.get(pos_key):
            frame[pos_key] = replacement
            changed = True
    return changed


def clean_questions(frame: dict, story_id: str, frame_number: int) -> bool:
    words = split_csv(frame.get("vocabulary"))
    if not words:
        return False
    changed = False
    question_keys = ("vocabularyCloze", "vocabularySynonym", "vocabularyLookalike", "vocabularyDistractors")
    for key in question_keys:
        original = parse_json_array(frame.get(key))
        normalized = normalize_outer_length(original, len(words))
        if key == "vocabularyCloze":
            cleaned: list[list] = []
            for word, candidates in zip(words, normalized):
                kept = []
                for candidate in candidates:
                    if not isinstance(candidate, dict):
                        continue
                    sentence = candidate.get("sentence")
                    distractors = candidate.get("distractors")
                    if not isinstance(sentence, str) or not isinstance(distractors, list) or not distractors:
                        continue
                    sentence = CLOZE_REPLACEMENTS.get((story_id, frame_number, word), sentence)
                    if sentence.count(word) != 1:
                        continue
                    if any(not isinstance(item, str) or not item.strip() for item in distractors):
                        continue
                    kept.append({"sentence": sentence, "distractors": distractors})
                cleaned.append(kept)
            normalized = cleaned
        elif key == "vocabularySynonym":
            cleaned = []
            for word, candidates in zip(words, normalized):
                allowed = APPROVED_SYNONYMS.get(word, set())
                cleaned.append([
                    candidate
                    for candidate in candidates
                    if isinstance(candidate, dict)
                    and candidate.get("synonym") in allowed
                    and isinstance(candidate.get("distractors"), list)
                    and candidate.get("distractors")
                ])
            normalized = cleaned
        serialized = dump_json(normalized)
        if frame.get(key) != serialized:
            frame[key] = serialized
            changed = True
    return changed


def populate_modern_metadata(frame: dict) -> bool:
    """Fill missing metadata and safe cloze candidates for seeded lessons."""
    words = split_csv(frame.get("vocabulary"))
    if not words or any(word not in MODERN_VOCAB for word in words):
        return False
    changed = False
    values = {
        "vocabularyPinyin": ", ".join(MODERN_VOCAB[word][0] for word in words),
        "vocabularyPos": ", ".join(MODERN_VOCAB[word][1] for word in words),
        "vocabularyTranslation": ", ".join(MODERN_VOCAB[word][2] for word in words),
    }
    for key, value in values.items():
        if frame.get(key) != value:
            frame[key] = value
            changed = True

    outer = normalize_outer_length(parse_json_array(frame.get("vocabularyCloze")), len(words))
    suggested = str(frame.get("suggestedAnswer") or "")
    fallback_by_pos = {
        "N": ["朋友", "學校", "飯店"],
        "V": ["游泳", "跑步", "休息"],
        "Adj": ["漂亮", "方便", "有趣"],
    }
    for i, word in enumerate(words):
        if outer[i] or suggested.count(word) != 1:
            continue
        pos = MODERN_VOCAB[word][1]
        distractors = [item for item in fallback_by_pos[pos] if item != word][:3]
        outer[i] = [{"sentence": suggested, "distractors": distractors}]
    serialized = dump_json(outer)
    if frame.get("vocabularyCloze") != serialized:
        frame["vocabularyCloze"] = serialized
        changed = True
    return changed


def migrate() -> tuple[list[str], list[str]]:
    changed_ids: list[str] = []
    unpublished_ids: list[str] = []
    with psycopg.connect(DATABASE_URL) as connection:
        rows = connection.execute(
            "SELECT id, frames, published FROM custom_stories "
            "WHERE id LIKE %s OR id LIKE %s ORDER BY id FOR UPDATE",
            (f"{CUSTOM_STORY_PREFIX}%", f"{MODERN_STORY_PREFIX}%"),
        ).fetchall()
        for story_id, frames, published in rows:
            story_changed = False
            next_frames = list(frames or [])
            has_content = False
            for frame_number, frame in enumerate(next_frames, start=1):
                if not isinstance(frame, dict):
                    continue
                words = split_csv(frame.get("vocabulary"))
                has_content = has_content or bool(words)
                prompt = str(frame.get("prompt") or "").strip()
                if not prompt and (story_id, frame_number) in PROMPT_REPLACEMENTS:
                    frame["prompt"] = PROMPT_REPLACEMENTS[(story_id, frame_number)]
                    story_changed = True
                if story_id.startswith(MODERN_STORY_PREFIX):
                    story_changed = populate_modern_metadata(frame) or story_changed
                story_changed = normalize_pos_fields(frame) or story_changed
                story_changed = clean_questions(frame, story_id, frame_number) or story_changed

            next_published = published
            if story_id == "custom-story-1785205277637" and not has_content and published:
                next_published = False
                unpublished_ids.append(story_id)
                story_changed = True

            if not story_changed:
                continue
            connection.execute(
                "UPDATE custom_stories SET frames = %s, published = %s, "
                "quiz_material_snapshot = NULL, quiz_approved_snapshot = NULL, "
                "quiz_pending_approvals = NULL WHERE id = %s",
                (json.dumps(next_frames, ensure_ascii=False), next_published, story_id),
            )
            changed_ids.append(story_id)
        connection.commit()
    return changed_ids, unpublished_ids


if __name__ == "__main__":
    changed, unpublished = migrate()
    print(f"Updated {len(changed)} custom stories: {', '.join(changed) or 'none'}")
    print(f"Unpublished empty placeholders: {', '.join(unpublished) or 'none'}")
