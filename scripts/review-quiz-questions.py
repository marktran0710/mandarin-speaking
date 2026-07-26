"""Attach a manual semantic review to quiz-questions.json.

The mechanical rules in src/utils/quizAudit.ts already cover the structural
invariants (correct answer present, no duplicate options, cloze blank hides
the word). What they cannot see is meaning: a distractor that *also* fits the
blank, a "synonym" that isn't one, an English option that is a second valid
translation. Those were reviewed by hand; this script re-walks
quiz-questions.json in the same order the review used and pins each finding
to its question.

Run: python scripts/review-quiz-questions.py
"""

import json
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# index -> (severity, rule, note). Index is the flat 1-based question number
# in quiz-questions.json's story/scene/word/question order.
FINDINGS = {
    # ── 我們去喝下午茶 ────────────────────────────────────────────────
    3: ("error", "cloze-multi-fit", "「小美是我的好朋友，她很友善。」is fully correct — 小美 is also a name."),
    4: ("error", "synonym-degenerate", "名字 ('name') is a category, not a synonym of 友美. The question has no real answer."),
    7: ("error", "cloze-multi-fit", "「妳這個假期要做什麼？」is correct — 假期 fits the blank."),
    8: ("error", "cloze-multi-fit", "「我喜歡在假期睡懶覺。」is correct; 星期一/星期五 also fit."),
    9: ("warning", "material-inconsistent", "假期 is the correct synonym here but a distractor in questions 7 and 8."),
    12: ("error", "cloze-multi-fit", "「妳這個週末要吃/喝/玩什麼？」are all correct — any transitive verb fits 要＿什麼."),
    14: ("error", "register-inappropriate", "幹 is vulgar in Taiwanese Mandarin; unusable in an A1-A2 Traditional-Chinese course."),
    17: ("error", "cloze-multi-fit", "Every pronoun fits 「＿要在家看書、聽音樂。」"),
    18: ("error", "cloze-multi-fit", "「他/她是你的朋友。」are both correct."),
    19: ("warning", "synonym-not-synonym", "自己 = 'oneself', not a synonym of 我."),
    22: ("error", "cloze-multi-fit", "需要/必須/可以 all produce correct sentences."),
    23: ("error", "cloze-multi-fit", "想要/需要/必須 all fit; 想要 is a near-synonym of 要."),
    26: ("warning", "translation-second-correct", "在 also translates as 'on' (在桌子上) — 'on' is defensible."),
    32: ("error", "cloze-multi-fit", "「我要在學校/公司/圖書館看書、聽音樂。」are all correct."),
    33: ("error", "cloze-multi-fit", "「我愛我的學校/公司。」are correct."),
    37: ("error", "cloze-multi-fit", "「我要在家看電影、聽音樂。」is correct."),
    38: ("error", "cloze-multi-fit", "「我喜歡＿。」accepts every option; the same stem appears at question 43 with a different answer."),
    42: ("error", "cloze-multi-fit", "「我要在家看書、看電視。」is correct."),
    43: ("error", "cloze-multi-fit", "Same stem as question 38 but a different 'correct' answer — proof the stem carries no constraint."),
    44: ("warning", "synonym-not-synonym", "收聽 = 'tune in (to radio)', not a synonym of 聽音樂."),
    47: ("error", "cloze-multi-fit", "Nothing in the sentence picks a weekday — every 星期X fits."),
    48: ("error", "cloze-multi-fit", "「星期一是我的休息日。」is correct."),
    49: ("error", "synonym-wrong", "六日 means 'Sat & Sun' (and is Mainland usage), not 星期六."),
    53: ("error", "cloze-multi-fit", "「我早上/晚上/中午有課。」are all correct."),
    57: ("error", "cloze-multi-fit", "有時間 is an exact synonym of 有空 — and is the declared correct synonym at question 59."),
    58: ("warning", "cloze-multi-fit", "「我今天忙。」is acceptable colloquially."),
    65: ("error", "reverse-second-correct", "一同 also means 'together'."),
    67: ("warning", "cloze-multi-fit", "吃下午茶 is idiomatic in Taiwan — 吃 fits the blank."),
    74: ("warning", "synonym-weak", "茶會 = 'tea party', not 下午茶."),
    77: ("error", "cloze-multi-fit", "「很好！你想去哪裡？」and 「還可以！…」are both natural."),
    79: ("warning", "synonym-weak", "同意 is a verb; 好啊 is an interjection — not interchangeable."),
    80: ("error", "reverse-second-correct", "好吧 also means 'okay'."),
    82: ("error", "cloze-multi-fit", "「我/他/她想去哪裡？」are all correct."),
    83: ("error", "cloze-multi-fit", "Every pronoun fits; same stem as questions 18 and 133 with three different answers."),
    85: ("error", "reverse-second-correct", "妳 is the feminine form of the same word 'you' — identical meaning and sound."),
    87: ("error", "cloze-multi-fit", "「你可以去哪裡？」and 「你要去哪裡？」are correct."),
    88: ("error", "cloze-multi-fit", "想要 fits and is the declared synonym at question 89."),
    92: ("warning", "cloze-multi-fit", "「你想回哪裡？」is acceptable."),
    95: ("warning", "reverse-second-correct", "往 and 赴 both mean 'to go (to)'."),
    103: ("warning", "cloze-no-context", "「我＿了。」is too short to constrain the answer; 不明白了 is possible."),
    105: ("error", "reverse-second-correct", "曉得 means 'know' — and is the declared synonym at question 104."),
    107: ("error", "cloze-multi-fit", "「我知道一家很不錯的餐廳/商店。」are correct."),
    108: ("error", "cloze-multi-fit", "「我喜歡去餐廳/商店。」are correct."),
    112: ("error", "cloze-multi-fit", "雪糕 also means ice cream — declared the synonym at question 114."),
    113: ("error", "cloze-multi-fit", "「我愛吃冰棒/雪糕。」are correct."),
    115: ("warning", "reverse-second-correct", "冰糕 also denotes ice cream in some regions."),
    117: ("error", "cloze-multi-fit", "「…冰淇淋很一般。」is correct; also 很+很難吃 renders as 「很很難吃」."),
    118: ("error", "cloze-broken-option", "Option 「不 ngon」 is corrupted — Vietnamese leaked into the Chinese option."),
    122: ("error", "cloze-multi-fit", "「他們有草莓/芒果冰淇淋嗎？」are all correct."),
    123: ("error", "cloze-multi-fit", "「我愛吃餅乾/蛋糕/糖果。」are correct."),
    127: ("warning", "cloze-multi-fit", "「有哦！」is natural Taiwanese Mandarin."),
    128: ("error", "cloze-multi-fit", "「哦，我明白了。」is the more natural sentence of the two."),
    129: ("warning", "material-inconsistent", "哦 is the correct synonym here but a distractor at questions 127-128."),
    130: ("warning", "reverse-ambiguous", "哦 also renders as 'ah/oh'."),
    132: ("error", "cloze-multi-fit", "「我們/你/我有很多種冰淇淋。」are all correct."),
    133: ("error", "cloze-multi-fit", "「你們/它們是我的朋友。」are correct."),
    134: ("error", "synonym-wrong", "它們 is 'they (inanimate)' — not a synonym of 他們 for people."),
    135: ("error", "reverse-second-correct", "她們 and 它們 both translate as 'they'."),
    142: ("error", "cloze-multi-fit", "「我有一些書。」is correct."),
    144: ("warning", "reverse-second-correct", "大量 also reads as 'many/a large amount'."),
    149: ("warning", "reverse-second-correct", "類 also means 'kind/type'."),
    151: ("error", "cloze-multi-fit", "Nothing fixes the time — 三點/四點/五點 all fit."),
    152: ("error", "cloze-multi-fit", "「我們一點/三點見面。」are all correct."),
    153: ("warning", "synonym-weak", "兩點半 is ambiguous between 2:30 am and pm; '下午2:30' over-specifies."),
    # ── 捷運站在哪裡？ ───────────────────────────────────────────────
    156: ("error", "cloze-multi-fit", "Any male given name fits the blank."),
    157: ("error", "synonym-degenerate", "名字 ('name') is not a synonym of 承翰."),
    160: ("error", "cloze-multi-fit", "「承翰要去圖書館/醫院/公司。」are all correct."),
    165: ("error", "cloze-multi-fit", "巴士站 is a real station — 「請問，巴士站在哪裡？」is correct."),
    166: ("error", "cloze-multi-fit", "公車站/火車站/計程車站 all exist and fit."),
    170: ("error", "cloze-multi-fit", "「他走去公車站/火車站/港口。」are all correct."),
    173: ("warning", "material-inconsistent", "車站 is the declared synonym at question 171 but a wrong option here."),
    175: ("warning", "cloze-multi-fit", "「承翰要來學校。」is correct."),
    179: ("error", "cloze-multi-fit", "曉得 = 知道 and 記得 both give grammatical sentences; the stem shows no clue that he does NOT know."),
    181: ("warning", "reverse-second-correct", "不知 also means 'do not know'."),
    182: ("warning", "gloss-questionable", "請問 means 'excuse me / may I ask', not the imperative 'please ask' — the authored gloss drives every option here."),
    183: ("error", "cloze-multi-fit", "「對不起，捷運站在哪裡？」and 「不好意思，…」are natural."),
    184: ("warning", "synonym-weak", "詢問 is a formal verb, not interchangeable with the opener 請問."),
    186: ("warning", "material-inconsistent", "詢問 is the declared synonym at question 184 but a wrong option here."),
    187: ("error", "data-segmentation", "站在 is a mis-split of 捷運站 + 在. The word does not exist in the sentence and 'is located at' is not what 站在 means."),
    188: ("error", "data-segmentation", "Teaches the wrong parse: the sentence is 捷運站 / 在 / 哪裡, not 捷運 / 站在 / 哪裡."),
    189: ("error", "cloze-multi-fit", "位於 and 位在 both fit 「捷運＿那裡」— and inherit the 站在 segmentation error."),
    190: ("warning", "material-inconsistent", "位於 is the correct synonym here but a distractor at question 189."),
    193: ("error", "cloze-multi-fit", "Any female given name fits."),
    194: ("error", "synonym-degenerate", "名字 is not a synonym of 婉婷."),
    197: ("error", "cloze-multi-fit", "「捷運站在這裡/左邊/右邊」are all correct."),
    198: ("error", "synonym-wrong", "哪裡 is the question word 'where'; 那裡 is 'there'. They are not synonyms."),
    199: ("error", "reverse-second-correct", "那邊 and 那兒 both mean 'there'."),
    201: ("error", "cloze-multi-fit", "「近嗎？」「快嗎？」are all valid questions — the one-word stem constrains nothing."),
    203: ("error", "reverse-second-correct", "遙遠 means 'far' — and is the declared synonym at question 202."),
    205: ("warning", "cloze-multi-fit", "「遠吧？」is grammatical."),
    206: ("error", "synonym-wrong", "呢 and 嗎 are different particles; 呢 cannot replace 嗎 in a yes/no question."),
    211: ("warning", "reverse-second-correct", "不遠處 / 不遠的 are morphological variants meaning 'not far'."),
    215: ("warning", "reverse-weak", "很近的 is the same word with a particle; not a genuine alternative."),
    217: ("error", "cloze-multi-fit", "「承翰說對不起/抱歉/不好意思。」are all correct."),
    221: ("error", "cloze-multi-fit", "「他跑去捷運站。」is correct."),
    224: ("warning", "reverse-second-correct", "行 also means 'to walk'."),
    226: ("error", "cloze-multi-fit", "「他很難過/悲傷/失望。」are all grammatical; the stem gives no emotional cue."),
    228: ("warning", "fabricated-word", "高興劑 is not a word."),
    # ── 我們去士林夜市 ───────────────────────────────────────────────
    230: ("error", "cloze-multi-fit", "Every weekday fits 「我＿有課，所以不能去玩。」"),
    231: ("error", "reverse-second-correct", "週五 is Friday."),
    233: ("error", "cloze-multi-fit", "「早上/中午/下午我要去看電視。」are all correct."),
    234: ("warning", "material-inconsistent", "傍晚 = 'dusk', which is a wrong option for this same word at question 232."),
    235: ("warning", "reverse-second-correct", "夜晚 also renders as 'evening/night'."),
    237: ("error", "cloze-multi-fit", "王大/李小 are names and fit the blank."),
    238: ("error", "synonym-degenerate", "名字 is not a synonym of 志豪."),
    241: ("error", "cloze-multi-fit", "「我回學校/公司了，很高興。」are correct."),
    242: ("warning", "synonym-weak", "屋 is not used alone in Mandarin, and 家 (home) ≠ 屋 (house)."),
    249: ("error", "cloze-multi-fit", "李美/王小 are names and fit the blank."),
    250: ("error", "synonym-degenerate", "名字 is not a synonym of 佳玲."),
    255: ("error", "reverse-second-correct", "一同 and 一齊 both mean 'together'; 一起子 is not a word."),
    261: ("error", "cloze-multi-fit", "Every weekday fits 「＿我要去逛街。」"),
    263: ("error", "reverse-second-correct", "週六 is Saturday."),
    264: ("warning", "translation-second-correct", "做 also means 'create/make' — 'create' is defensible."),
    266: ("error", "register-inappropriate", "幹 is vulgar in Taiwanese Mandarin."),
    272: ("error", "synonym-degenerate", "妳 is the same word as 你 (feminine form), and is used as a wrong option at question 273."),
    273: ("error", "reverse-second-correct", "妳 means 'you'; 汝 is the classical 'you'."),
    275: ("warning", "cloze-multi-fit", "「我生病，謝謝你的關心。」is acceptable."),
    279: ("error", "cloze-multi-fit", "臺北/高雄/臺中夜市 all fit 「我們去＿吃小吃。」"),
    283: ("warning", "cloze-multi-fit", "「這個東西很不好吃，我很喜歡。」is odd but grammatical."),
    284: ("warning", "synonym-weak", "好棒 = 'great', a degree stronger than 好."),
    287: ("error", "cloze-multi-fit", "牛排/豬排/魚排 all fit 「我愛吃＿，很好吃。」"),
    288: ("warning", "synonym-weak", "炸雞 = 'fried chicken', not specifically 雞排."),
    293: ("warning", "fabricated-word", "很吃 and 吃得 are not words — the option set gives the answer away."),
    297: ("error", "reverse-second-correct", "好極了 also means 'great'."),
    299: ("error", "cloze-multi-fit", "「我愛喝紅茶/綠茶/咖啡，很好喝。」are all correct."),
    300: ("error", "synonym-wrong", "泡茶 means 'to brew tea', not bubble tea (珍奶 / 波霸奶茶)."),
    302: ("error", "translation-second-correct", "有 does mean 'exist' (有 = there is) — 'exist' is a correct answer."),
    303: ("warning", "cloze-broken-option", "Option 沒有錢 renders the sentence as 「我沒有錢錢，可以買東西。」"),
    304: ("error", "synonym-wrong", "有的 means 'some', not 'have'."),
    307: ("error", "cloze-multi-fit", "「你們/他們/她們是朋友，很好。」are all correct."),
    308: ("warning", "synonym-degenerate", "我們自己 contains the prompt word — it is 'ourselves', not a synonym."),
    311: ("error", "cloze-multi-fit", "七點/八點/九點 all fit."),
    313: ("error", "reverse-second-correct", "六時 is 'six o'clock' — and is the declared synonym at question 312."),
    315: ("error", "cloze-multi-fit", "「我們在火車站/巴士站/港口見面。」are all correct."),
    319: ("warning", "cloze-multi-fit", "「我們六點在捷運站走。」is marginally acceptable."),
    321: ("warning", "reverse-second-correct", "視 also means 'to see' (literary)."),
}


def main():
    src = REPO / "quiz-questions.json"
    data = json.loads(src.read_text(encoding="utf-8"))

    reviewed = []
    n = 0
    for story in data["stories"]:
        for scene in story["scenes"]:
            for word in scene["words"]:
                for question in word["questions"]:
                    n += 1
                    finding = FINDINGS.get(n)
                    if not finding:
                        continue
                    severity, rule, note = finding
                    reviewed.append(
                        {
                            "questionNumber": n,
                            "severity": severity,
                            "rule": rule,
                            "note": note,
                            "storyId": story["storyId"],
                            "story": story["title"],
                            "scene": scene["scene"],
                            "word": word["word"],
                            "kind": question["kind"],
                            "prompt": question["prompt"],
                            "answer": question["answer"],
                            "aiWrongOptions": question["aiWrongOptions"],
                            **({"poolIndex": question["poolIndex"]} if "poolIndex" in question else {}),
                            # Ready to append to custom_stories.quiz_exclusions
                            # (src/utils/quizExclusions.ts) to retire this item.
                            "suggestedExclusion": exclusion_for(word["word"], question),
                        }
                    )

    by_severity = Counter(f["severity"] for f in reviewed)
    by_rule = Counter(f["rule"] for f in reviewed)
    by_kind = Counter(f["kind"] for f in reviewed)

    report = {
        "meta": {
            "reviewed": n,
            "flagged": len(reviewed),
            "clean": n - len(reviewed),
            "bySeverity": dict(by_severity),
            "byRule": dict(by_rule.most_common()),
            "byKind": dict(by_kind.most_common()),
            "severityMeaning": {
                "error": "The question has more than one defensible answer, a wrong answer, or a broken option — it must not be served as-is.",
                "warning": "Defensible but weak: a borderline second answer, an inconsistency with the same word's other questions, or a junk option.",
            },
            "notCovered": "Structural rules (answer present, duplicate options, blank hides the word) are already enforced by src/utils/quizAudit.ts and pass on all 321 questions.",
        },
        "findings": reviewed,
    }

    out = REPO / "quiz-questions-review.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(reviewed)} of {n} questions flagged "
          f"({by_severity['error']} error, {by_severity['warning']} warning) -> {out}")
    for rule, count in by_rule.most_common():
        print(f"  {rule}: {count}")


def exclusion_for(word: str, question: dict):
    kind = question["kind"]
    if kind == "cloze":
        return {"word": word, "kind": "cloze", "index": question.get("poolIndex")}
    if kind == "synonym":
        return {"word": word, "kind": "synonym", "index": question.get("poolIndex")}
    if kind == "reverse-lookalike":
        return {"word": word, "kind": "lookalike"}
    return {"word": word, "kind": "distractors"}


if __name__ == "__main__":
    main()
