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
from typing import Dict, List

try:
    import jieba

    jieba.setLogLevel(60)  # suppress the dictionary-loading banner
    jieba.initialize()  # load the prefix dict at import, not on first request

    # Jieba's default dictionary is Simplified Chinese. Many Traditional Chinese
    # compound words are missing or have very low frequency, causing incorrect
    # splits (e.g. 覺得 → 覺 + 得). Register the common ones explicitly so
    # they are always treated as single tokens.
    _TC_WORDS = [
        # Verbs / verb-result compounds
        "覺得", "知道", "喜歡", "告訴", "幫忙", "出來", "進來", "回來", "起來",
        "下來", "出去", "進去", "回去", "看到", "聽到", "找到", "拿到", "說到",
        "做到", "想到", "學到", "走過來", "跑過去",
        # Common adjectives / stative verbs
        "高興", "難過", "開心", "傷心", "生氣", "緊張", "害怕", "擔心", "漂亮",
        "厲害", "麻煩", "奇怪", "清楚", "重要",
        # Common nouns
        "時候", "地方", "東西", "事情", "問題", "機會", "方法", "意思", "道理",
        "老師", "同學", "同事", "朋友", "家人", "先生", "太太", "小姐",
        "學生", "媽媽", "爸爸", "哥哥", "姐姐", "弟弟", "妹妹",
        # Time words
        "今天", "明天", "昨天", "以前", "以後", "現在", "剛才", "一下",
        "這裡", "那裡", "哪裡", "這邊", "那邊",
        # Modal / auxiliary
        "可以", "應該", "需要", "必須", "能夠", "願意",
        # Pronouns + particles
        "我們", "你們", "他們", "她們", "它們", "大家",
        # Common phrases
        "沒有", "沒關係", "不客氣", "謝謝", "對不起", "沒問題",
    ]
    for _w in _TC_WORDS:
        jieba.add_word(_w, freq=50000, tag="v" if _w.endswith(("得", "到", "來", "去")) else None)

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

    Falls back to character tokens if jieba is unavailable.
    """
    han = "".join(ch for ch in text if _is_han(ch))
    if not han:
        return []
    tokens = list(jieba.cut(han)) if _HAS_JIEBA else list(han)
    return [t for t in (tok.strip() for tok in tokens) if t and any(_is_han(c) for c in t)]


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
