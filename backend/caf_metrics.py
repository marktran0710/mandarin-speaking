"""
caf_metrics.py — paper-grounded offline scoring for L2 Mandarin speaking.

The local (no-LLM) feedback path used to rely on ad-hoc length thresholds.
This module replaces that with deterministic measures drawn from the
Complexity-Accuracy-Fluency (CAF) tradition in second-language acquisition
and from speech-fluency research, all computable offline.

What the literature defines is the *measures*; the 0-100 mapping applied here
is a transparent, bounded calibration tuned for short beginner Mandarin
utterances. Measures and their sources:

- CAF framework
    Skehan, P. (1998). A Cognitive Approach to Language Learning. OUP.
    Housen, A., & Kuiken, F. (2009). Complexity, Accuracy and Fluency in SLA.
        Applied Linguistics, 30(4), 461-473.
- Utterance fluency
    Towell, R., Hawkins, R., & Bazergui, N. (1996). The development of fluency
        in advanced learners of French. Applied Linguistics, 17(1), 84-119.
        (mean length of run)
    De Jong, N. H., Steinel, M. P., Florijn, A. F., Schoonen, R., & Hulstijn,
        J. H. (2012). Facets of speaking proficiency. SSLA, 34(1), 5-34.
        (phonation-time ratio, articulation rate)
- Lexical diversity
    Guiraud, P. (1960). Problemes et methodes de la statistique linguistique.
        (Guiraud index = types / sqrt(tokens))
    McCarthy, P. M., & Jarvis, S. (2010). MTLD, vocd-D and HD-D: A validation
        study. Behavior Research Methods, 42(2), 381-392.
- Pronunciation (proxy)
    Witt, S. M., & Young, S. J. (2000). Phone-level pronunciation scoring and
        assessment for interactive language learning. Speech Communication,
        30(2-3), 95-108. (Goodness of Pronunciation; full GOP needs a phoneme
        acoustic model, so tone-contour correlation is used as a prosodic proxy.)
"""
from __future__ import annotations

import math
import re
from typing import Dict, List

try:
    import jieba

    jieba.setLogLevel(60)  # suppress the dictionary-loading banner
    jieba.initialize()  # load the prefix dict at import, not on first request

    # Jieba's default dictionary is Simplified Chinese. Many Traditional Chinese
    # compound words are missing or have very low frequency, causing incorrect
    # splits (e.g. 覺得 → 覺 + 得). Register the common ones explicitly so
    # they are always treated as single tokens.
    #
    # Every entry needs an explicit tag=. jieba.add_word() without one does
    # NOT preserve whatever POS tag the word already had — verified directly
    # against jieba.posseg.cut() output: even a word jieba's own dictionary
    # already tags correctly (家裡 -> 's') reverts to the unknown tag 'x' the
    # moment add_word touches it without a tag=. praat_analyzer's
    # _classify_content_word keys off this tag's first letter to decide
    # whether a word carries sentence stress, so an untagged entry here
    # silently mislabeled every one of these words a "function word".
    _TC_WORDS_BY_TAG: dict = {
        "v": [
            "覺得", "知道", "喜歡", "告訴", "幫忙", "出來", "進來", "回來", "起來",
            "下來", "出去", "進去", "回去", "看到", "聽到", "找到", "拿到", "說到",
            "做到", "想到", "學到", "走過來", "跑過去",
            "可以", "應該", "需要", "必須", "能夠", "願意",
            "沒有",
            "做飯", "吃飯", "吃飽", "喝水", "買菜", "洗碗", "看書", "看電視",
            "寫字", "唱歌", "跳舞", "打電話", "上網", "聽音樂", "做作業",
        ],
        "a": [
            "高興", "難過", "開心", "傷心", "生氣", "緊張", "害怕", "擔心", "漂亮",
            "厲害", "麻煩", "奇怪", "清楚", "重要",
        ],
        "n": [
            "時候", "地方", "東西", "事情", "問題", "機會", "方法", "意思", "道理",
            "老師", "同學", "同事", "朋友", "家人", "先生", "太太", "小姐",
            "學生", "媽媽", "爸爸", "哥哥", "姐姐", "弟弟", "妹妹", "大家",
            "校園", "大樓", "麵店",
            "中文課", "英文課", "數學課",
        ],
        "t": ["今天", "明天", "昨天", "以前", "以後", "現在", "剛才"],
        "m": ["一下"],
        "r": ["這裡", "那裡", "哪裡", "這邊", "那邊", "我們", "你們", "他們", "她們", "它們"],
        "l": ["沒關係", "不客氣", "謝謝", "對不起", "沒問題"],
        "s": ["家裡", "教室裡", "廚房裡", "房間裡", "客廳裡", "學校裡", "校園裡", "大樓裡"],
    }
    for _tag, _words in _TC_WORDS_BY_TAG.items():
        for _w in _words:
            jieba.add_word(_w, freq=50000, tag=_tag)

    # These entries need frequencies much higher than 50000 to override jieba's
    # built-in SC compounds (e.g. 在家 freq≈40000 beats 在+家裡 at 50000).
    # Boosting the TC form to 200000 makes the TC path win in Viterbi DP.
    jieba.add_word("家裡", freq=200000, tag="s")
    jieba.add_word("在家裡", freq=150000, tag="s")
    jieba.add_word("校園裡", freq=150000, tag="s")   # beats 在校 (SC compound) in 在校園裡
    jieba.add_word("在校園裡", freq=120000, tag="s")
    jieba.add_word("大樓裡", freq=100000, tag="s")
    jieba.add_word("做飯", freq=200000, tag="v")
    jieba.add_word("吃飯", freq=200000, tag="v")
    jieba.add_word("吃飽", freq=100000, tag="v")
    jieba.add_word("做作業", freq=150000, tag="v")
    jieba.add_word("教室裡", freq=100000, tag="s")
    jieba.add_word("中文課", freq=100000, tag="n")
    jieba.add_word("麵店", freq=80000, tag="n")

    _HAS_JIEBA = True
except Exception:  # pragma: no cover - jieba is a declared dependency
    jieba = None
    _HAS_JIEBA = False


# Common Mandarin connectives / subordinators. Their density is a lightweight
# proxy for subordination and discourse cohesion (CAF complexity sub-construct).
CONNECTIVES: List[str] = [
    "因為", "所以", "但是", "可是", "雖然", "然後", "而且", "不過", "如果",
    "因此", "於是", "接著", "後來", "最後", "一開始", "首先", "其次", "還有",
    "卻", "並且", "以及", "或者", "由於", "為了", "只要", "除了", "不但", "而是",
]


def _is_han(ch: str) -> bool:
    return "一" <= ch <= "鿿"


def segment_words(text: str) -> List[str]:
    """Word-segment Mandarin text with jieba, keeping Han-character tokens only.

    Each contiguous run of Han characters is segmented independently so that
    punctuation (including the enumeration comma 、) acts as a word boundary
    rather than being silently stripped before segmentation.

    Falls back to character tokens if jieba is unavailable.
    """
    # 一-鿿 covers the main CJK Unified Ideographs block.
    spans = re.findall(r"[一-鿿]+", text)
    if not spans:
        return []
    result: List[str] = []
    for span in spans:
        if _HAS_JIEBA:
            tokens = jieba.cut(span)
        else:
            tokens = list(span)
        result.extend(t for t in (tok.strip() for tok in tokens) if t and any(_is_han(c) for c in t))
    return result


def _mtld(tokens: List[str], ttr_threshold: float = 0.72) -> float:
    """Measure of Textual Lexical Diversity (McCarthy & Jarvis 2010).

    Forward and reverse passes averaged. Returns the token count for very
    short inputs where MTLD is undefined.
    """
    if len(tokens) < 3:
        return float(len(tokens))

    def _one_pass(seq: List[str]) -> float:
        factors = 0.0
        types: set = set()
        count = 0
        for tok in seq:
            types.add(tok)
            count += 1
            if len(types) / count <= ttr_threshold:
                factors += 1
                types = set()
                count = 0
        if count > 0:
            ttr = len(types) / count
            factors += (1 - ttr) / (1 - ttr_threshold)
        return len(seq) / factors if factors > 0 else float(len(seq))

    return (_one_pass(tokens) + _one_pass(list(reversed(tokens)))) / 2.0


def lexical_metrics(tokens: List[str]) -> Dict:
    """Lexical diversity: TTR, Guiraud index, MTLD, and a 0-100 score.

    Guiraud's index (types / sqrt(tokens)) is preferred over raw TTR because it
    is far less sensitive to utterance length. The score saturates so that very
    short but varied beginner sentences are not over-penalised.
    """
    n = len(tokens)
    if n == 0:
        return {"tokens": 0, "types": 0, "ttr": 0.0, "guiraud": 0.0, "mtld": 0.0, "score": 0}
    types = len(set(tokens))
    guiraud = types / math.sqrt(n)
    # G≈2 -> ~55, G≈4 -> ~80, G≈7 -> ~94 (adult L1 reference band).
    score = int(max(0, min(100, round(100 * (1 - math.exp(-guiraud / 2.5))))))
    return {
        "tokens": n,
        "types": types,
        "ttr": round(types / n, 3),
        "guiraud": round(guiraud, 2),
        "mtld": round(_mtld(tokens), 1),
        "score": score,
    }


def syntactic_complexity(tokens: List[str], text: str) -> Dict:
    """CAF Complexity: mean length of utterance + subordination via connectives.

    Length follows the mean-length-of-utterance tradition; subordination is
    approximated by connective density (Skehan 1998; Housen & Kuiken 2009).
    """
    n = len(tokens)
    connectives = [c for c in CONNECTIVES if c in text]
    sub_ratio = (len(connectives) / n) if n else 0.0
    # ~12 words is a full beginner sentence; ~1 connective per 4 words is rich.
    len_score = max(0, min(100, round((n / 12) * 100)))
    sub_score = max(0, min(100, round(sub_ratio * 400)))
    score = int(round(0.7 * len_score + 0.3 * sub_score))
    return {
        "length": n,
        "connectives": connectives,
        "subordination_ratio": round(sub_ratio, 3),
        "score": max(0, min(100, score)),
    }


def fluency_metrics(speech_rate: float, pause_analysis: Dict, syllable_count: int) -> Dict:
    """Utterance fluency from pause structure (Towell et al. 1996; De Jong 2012).

    - phonation-time ratio = speaking time / total time
    - articulation rate    = syllables / speaking time (excludes pauses)
    - mean length of run    = syllables / (pause_count + 1)
    """
    pa = pause_analysis or {}
    speaking = float(pa.get("total_speaking_duration", 0) or 0)
    duration = float(pa.get("duration", 0) or 0)
    pause_count = int(pa.get("pause_count", 0) or 0)

    ptr = (speaking / duration) if duration > 0 else float(pa.get("speech_ratio", 0) or 0)
    articulation = (syllable_count / speaking) if speaking > 0 else 0.0
    mlr = (syllable_count / (pause_count + 1)) if syllable_count else 0.0

    # Beginner reference bands: phonation >0.65, articulation 3-5 syl/s, MLR >=5.
    ptr_score = max(0, min(100, round(ptr * 140)))
    artic_score = max(0, min(100, round((min(articulation, 5.0) / 5.0) * 100)))
    mlr_score = max(0, min(100, round((min(mlr, 6.0) / 6.0) * 100)))
    score = int(round(0.4 * ptr_score + 0.35 * artic_score + 0.25 * mlr_score))

    return {
        "phonation_time_ratio": round(ptr, 3),
        "articulation_rate": round(articulation, 2),
        "mean_length_of_run": round(mlr, 2),
        "speech_rate": round(float(speech_rate or 0), 2),
        "score": max(0, min(100, score)),
    }


def speech_rate_verdict(articulation_rate: float) -> Dict:
    """Translate a measured articulation rate (syllables/sec, excluding
    pauses) into a plain-language too-slow/good/too-fast judgment.

    Reuses the reference bands already established elsewhere in this
    codebase rather than inventing new ones: the 2.5 / 6.5 syl/s cutoffs
    from praat_analyzer.analyze_fluency's rate_penalty, and the 3-5 syl/s
    beginner "good" band documented on fluency_metrics above.
    """
    rate = float(articulation_rate or 0)
    if rate < 2.5:
        return {
            "verdict": "slow",
            "text": (
                f"You're speaking quite slowly ({rate:.1f} syllables/sec) — "
                "most learners at this level land around 3-5/sec. Try linking "
                "syllables together more closely."
            ),
        }
    if rate > 6.5:
        return {
            "verdict": "fast",
            "text": (
                f"You're speaking quite fast ({rate:.1f} syllables/sec) — "
                "slowing down toward 3-5/sec will make each tone easier to hear."
            ),
        }
    return {
        "verdict": "good",
        "text": f"Your pace ({rate:.1f} syllables/sec) is in a good range.",
    }


def _natural_pause_offsets(reference_text: str) -> set:
    """Han-character offsets in ``reference_text`` after which a pause is
    linguistically natural: right before punctuation, or right before a
    connective word (因為/所以/但是...).

    Offsets are counted in the Han-only character stream (matching how
    ``classify_pauses`` counts characters in word_prosody tokens), so this
    is independent of exactly how either side got word-segmented.
    """
    offsets: set = set()
    pos = 0
    for ch in reference_text:
        if _is_han(ch):
            pos += 1
        else:
            offsets.add(pos)

    han_only = "".join(ch for ch in reference_text if _is_han(ch))
    for connective in CONNECTIVES:
        start = 0
        while True:
            i = han_only.find(connective, start)
            if i == -1:
                break
            offsets.add(i)
            start = i + 1

    return offsets


def _nearest_word_index_before(pause_start: float, word_prosody: List[Dict]):
    """Index of the word_prosody segment whose end_time is closest to
    ``pause_start``, restricted to segments that have a following segment
    (so the pause can be described as "between token i and i+1").
    """
    best_idx = None
    best_diff = None
    for i, word in enumerate(word_prosody[:-1]):
        end_time = word.get("end_time")
        if end_time is None:
            continue
        diff = abs(float(end_time) - float(pause_start))
        if best_diff is None or diff < best_diff:
            best_diff = diff
            best_idx = i
    return best_idx


def classify_pauses(
    reference_text: str,
    pause_analysis: Dict,
    word_prosody: List[Dict],
) -> Dict:
    """Judge each detected pause as landing at a natural boundary in the
    reference script (after punctuation, or before a connective) versus
    mid-phrase ("choppy").

    Alignment between the reference script and the student's word_prosody
    (built from their transcription) is done by cumulative Han-character
    offset rather than word/token count, since jieba may segment the two
    texts differently even when they describe the same characters in the
    same order. When the total character counts don't match (misread,
    ASR error), the alignment is too unreliable to judge pauses at all, so
    ``judged`` comes back False and no pauses are classified either way.
    """
    pauses = (pause_analysis or {}).get("pauses", []) or []
    if not pauses:
        return {"natural": [], "choppy": [], "judged": True}

    boundary_offsets = _natural_pause_offsets(reference_text)
    total_ref_chars = sum(1 for ch in reference_text if _is_han(ch))

    token_han_counts = [
        sum(1 for ch in (word.get("token") or "") if _is_han(ch))
        for word in word_prosody
    ]
    total_word_chars = sum(token_han_counts)
    if total_ref_chars == 0 or total_word_chars != total_ref_chars:
        return {"natural": [], "choppy": [], "judged": False}

    cumulative: List[int] = []
    running = 0
    for count in token_han_counts:
        running += count
        cumulative.append(running)

    natural: List[Dict] = []
    choppy: List[Dict] = []
    for pause in pauses:
        idx = _nearest_word_index_before(pause["start"], word_prosody)
        if idx is None:
            continue
        entry = {
            "before": word_prosody[idx].get("token", ""),
            "after": word_prosody[idx + 1].get("token", ""),
            "duration": float(pause.get("duration", pause["end"] - pause["start"])),
        }
        if cumulative[idx] in boundary_offsets:
            natural.append(entry)
        else:
            choppy.append(entry)

    return {"natural": natural, "choppy": choppy, "judged": True}
