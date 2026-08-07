"""Canonical fields for tone samples, across Mandarin varieties.

The eventual target is Taiwan Mandarin (國語) written in Traditional Chinese.
The corpus in hand is AISHELL-derived Mainland Mandarin (普通話) written in
Simplified. Those are different varieties, and this module exists so the
difference is recorded per sample rather than assumed away.

Three distinctions are kept deliberately separate, because collapsing any of
them would silently corrupt the ground truth:

**Variety is not orthography.** 學 and 学 are the same word in two scripts.
Script conversion is a text mapping and says nothing about how a syllable is
pronounced, so `word_script` never implies `pinyin_variety`.

**A corpus label is not a Taiwan target.** Mainland and Taiwan standards differ
in the lexical tone assigned to many common words -- 期 qi1/qi2, 液 ye4/yi4,
危 wei1/wei2, 究 jiu1/jiu4 among others, plus systematic differences in neutral
tone, which Taiwan Mandarin uses far less. Re-labelling a Mainland corpus as
Taiwan ground truth would therefore inject real errors, so `assert_label_usable`
refuses that combination unless the pronunciation was checked against an
authoritative Taiwan source (the MoE 重編國語辭典修訂本).

**Native speech is not learner speech.** A tone a native speaker produced is a
correct example of that tone; a tone an L2 learner intended is a target, and
the recording may not match it. `speech_type` keeps the two apart so a learner
recording can never be trained on as if it were a native exemplar.
"""

from __future__ import annotations

# --- varieties -------------------------------------------------------------
MAINLAND = "mainland"    # 普通話, PRC standard
TAIWAN = "taiwan"        # 國語, ROC/Taiwan standard
VARIETIES = (MAINLAND, TAIWAN)

# --- orthography (text representation only, never an acoustic claim) --------
SIMPLIFIED = "simplified"
TRADITIONAL = "traditional"
SCRIPTS = (SIMPLIFIED, TRADITIONAL)

# --- where a pronunciation label came from ---------------------------------
SOURCE_CORPUS = "corpus"        # shipped with the corpus, unverified
SOURCE_MOE_DICT = "moe_dict"    # checked against the Taiwan MoE dictionary
SOURCE_MANUAL = "manual"        # annotated by a human for this project
LABEL_SOURCES = (SOURCE_CORPUS, SOURCE_MOE_DICT, SOURCE_MANUAL)

# Sources that may stand as Taiwan ground truth. A Mainland corpus label is
# not on this list, by design.
TAIWAN_AUTHORITATIVE_SOURCES = (SOURCE_MOE_DICT, SOURCE_MANUAL)

# --- speaker type ----------------------------------------------------------
NATIVE = "native"
L2 = "l2"
SPEECH_TYPES = (NATIVE, L2)

# --- evaluation tracks, kept separate in every future report ---------------
TRACK_A = "A_mainland_native_train"
TRACK_B = "B_taiwan_native_eval"
TRACK_C = "C_l2_vs_taiwan_target"
TRACKS = (TRACK_A, TRACK_B, TRACK_C)

# The metadata columns every tone corpus writes, whatever its variety.
SAMPLE_FIELDS = (
    "audio",              # reference to the recording, not a copy
    "dataset_index",      # row in the source dataset
    "utt_id",
    "corpus",             # which corpus this row came from
    "speaker_id",
    "speaker_variety",    # MAINLAND | TAIWAN -- the speech, not the text
    "speech_type",        # NATIVE | L2
    "word",               # as written in the source
    "word_script",        # SIMPLIFIED | TRADITIONAL -- representation only
    "pinyin",             # the tone-bearing label actually used for training
    "pinyin_variety",     # which standard `pinyin` encodes
    "pinyin_source",      # CORPUS | MOE_DICT | MANUAL
    "syllable_base",
    "tone",
)


def assert_label_usable(row: dict, target_variety: str) -> None:
    """Raise if a row's pronunciation label cannot serve as ground truth.

    The case this exists to block: reading a Mainland corpus label as a Taiwan
    target. The two standards genuinely disagree on the lexical tone of many
    common words, so that substitution would not be an approximation -- it
    would be wrong on a specific, knowable subset, and silently.

    Called before evaluation rather than during preparation, so that Mainland
    rows can be prepared and used for Mainland work without objection.
    """
    variety = row.get("pinyin_variety")
    source = row.get("pinyin_source")

    if variety not in VARIETIES:
        raise ValueError(f"pinyin_variety must be one of {VARIETIES}, got {variety!r}")
    if source not in LABEL_SOURCES:
        raise ValueError(f"pinyin_source must be one of {LABEL_SOURCES}, got {source!r}")

    if variety == target_variety:
        return

    if target_variety == TAIWAN and source not in TAIWAN_AUTHORITATIVE_SOURCES:
        raise ValueError(
            f"{row.get('utt_id', '<row>')}: pronunciation label is "
            f"{variety}/{source}, which cannot stand as Taiwan ground truth. "
            f"Mainland and Taiwan standards differ on the lexical tone of many "
            f"common words. Validate against the Taiwan MoE dictionary and set "
            f"pinyin_source={SOURCE_MOE_DICT!r}, or exclude the row."
        )
    raise ValueError(
        f"{row.get('utt_id', '<row>')}: label is {variety} but the target "
        f"variety is {target_variety}."
    )


def describe_coverage(rows) -> str:
    """Summarise which varieties, scripts and speech types are present."""
    from collections import Counter

    def tally(field):
        counts = Counter(str(row.get(field)) for row in rows)
        return ", ".join(f"{key}={value}" for key, value in sorted(counts.items()))

    return "\n".join([
        f"  corpus         : {tally('corpus')}",
        f"  speaker_variety: {tally('speaker_variety')}",
        f"  speech_type    : {tally('speech_type')}",
        f"  word_script    : {tally('word_script')}",
        f"  pinyin_variety : {tally('pinyin_variety')}",
        f"  pinyin_source  : {tally('pinyin_source')}",
    ])
