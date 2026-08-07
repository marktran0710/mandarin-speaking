"""Prepare a single-syllable Mandarin tone dataset from Hugging Face.

Source: MariyaMegre/chinese-audio-dataset (8,612 recordings, public).

Phase 1 classifies one syllable at a time, and the embedding is mean-pooled
over the whole clip, so a multi-syllable recording would average two or more
tones into a single vector labelled with only one of them. Those recordings
are therefore excluded rather than truncated -- cutting audio to its first
syllable would need alignment this phase deliberately does not have.

Audio is never decoded or copied here. The metadata keeps the dataset row index
and the original filename, so the audio can be fetched later without a second
download.

    python -m pronunciation.wav2vec_tone.prepare_dataset
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pronunciation.wav2vec_tone import schema

DATASET_ID = "MariyaMegre/chinese-audio-dataset"
CORPUS_NAME = "aishell3-derived"

# This corpus is Mainland Mandarin read speech in Simplified Chinese, and its
# pinyin ships with the corpus rather than being verified against any
# dictionary. Recorded per row rather than assumed, because the eventual
# target variety is Taiwan Mandarin and the two disagree on the lexical tone
# of many common words. See schema.assert_label_usable.
CORPUS_VARIETY = schema.MAINLAND
CORPUS_SCRIPT = schema.SIMPLIFIED
CORPUS_LABEL_SOURCE = schema.SOURCE_CORPUS
CORPUS_SPEECH_TYPE = schema.NATIVE
DEFAULT_OUT = Path(__file__).resolve().parent / "data" / "filtered_tone_metadata.csv"

# A pinyin syllable: letters (with u:/v/ü for lü, nü) followed by one tone digit.
# Anchored so "zhun1 zhong4" cannot match as a whole and slip through.
SYLLABLE_PATTERN = re.compile(r"^([a-zA-Zü:v]+)([1-5])$")
KEEP_TONES = (1, 2, 3, 4)


def normalise_base(base: str) -> str:
    """Fold the three spellings of ü onto one, ASCII-safe form.

    In pinyin `v` is a keyboard stand-in for ü, not the vowel u -- 綠 lv4 and
    路 lu4 are different syllables. Folding v onto u would merge them, which
    would understate the syllable count and, worse, let a syllable-overlap
    check believe two distinct syllables are the same one.

    ü and u: are the other two spellings of the same vowel; all three settle on
    `v` so the value stays ASCII (the Windows console here is cp950 and cannot
    print ü).
    """
    return (
        base.lower()
        .replace("u:", "v")
        .replace("ü", "v")
    )


def parse_syllable(word_pinyin: str) -> Tuple[str, int] | None:
    """Return (base, tone) for a single-syllable pinyin string, else None.

    Splitting on whitespace is what separates "ma1" from "ke1 xue2"; anything
    with more than one token is multi-syllable regardless of how it is spelled.
    """
    tokens = str(word_pinyin or "").strip().split()
    if len(tokens) != 1:
        return None
    match = SYLLABLE_PATTERN.match(tokens[0])
    if not match:
        return None
    return normalise_base(match.group(1)), int(match.group(2))


def classify(word_pinyin: str) -> Tuple[str, Tuple[str, int] | None]:
    """Bucket a record as kept, multi-syllable, neutral tone, or invalid.

    Every exclusion is attributed to a reason so the counts can be reported
    rather than a single opaque "filtered out" number.
    """
    tokens = str(word_pinyin or "").strip().split()
    if len(tokens) != 1:
        return ("multi_syllable" if len(tokens) > 1 else "invalid"), None
    parsed = parse_syllable(word_pinyin)
    if parsed is None:
        return "invalid", None
    if parsed[1] not in KEEP_TONES:
        return "neutral_tone", None
    return "keep", parsed


def prepare(dataset_id: str = DATASET_ID, limit: int | None = None) -> Tuple[List[Dict], Dict[str, int], int]:
    """Load the dataset and return (kept rows, exclusion counts, original size).

    Audio decoding is switched off. This phase needs metadata only, and
    decoding would require an extra codec dependency and a great deal of time
    for no benefit.
    """
    from datasets import Audio, load_dataset

    dataset = load_dataset(dataset_id, split="train")
    dataset = dataset.cast_column("audio", Audio(decode=False))
    original_size = len(dataset)
    if limit:
        dataset = dataset.select(range(min(limit, original_size)))

    kept: List[Dict] = []
    excluded = Counter()

    speakers = dataset["speaker_id"]
    words = dataset["word"]
    pinyins = dataset["word_pinyin"]
    utterances = dataset["utt_id"]
    audio_column = dataset["audio"]

    for index in range(len(dataset)):
        verdict, parsed = classify(pinyins[index])
        if verdict != "keep":
            excluded[verdict] += 1
            continue
        base, tone = parsed
        audio = audio_column[index]
        kept.append({
            # A reference, not a copy: enough to fetch the audio later without
            # duplicating 131 MB of WAV data during preparation.
            "audio": (audio or {}).get("path") or "",
            "dataset_index": index,
            "utt_id": utterances[index],
            "corpus": CORPUS_NAME,
            "speaker_id": speakers[index],
            "speaker_variety": CORPUS_VARIETY,
            "speech_type": CORPUS_SPEECH_TYPE,
            "word": words[index],
            "word_script": CORPUS_SCRIPT,
            "pinyin": str(pinyins[index]).strip(),
            "pinyin_variety": CORPUS_VARIETY,
            "pinyin_source": CORPUS_LABEL_SOURCE,
            "syllable_base": base,
            "tone": tone,
        })

    return kept, dict(excluded), original_size


def summarise(rows: List[Dict], excluded: Dict[str, int], original: int, path: Path) -> str:
    tones = Counter(row["tone"] for row in rows)
    speakers_by_tone = {
        tone: len({row["speaker_id"] for row in rows if row["tone"] == tone})
        for tone in KEEP_TONES
    }
    bases = Counter(row["syllable_base"] for row in rows)
    total = len(rows) or 1

    lines = [
        f"Original samples: {original}",
        f"Filtered samples: {len(rows)}",
        "",
        f"Unique speakers: {len({row['speaker_id'] for row in rows})}",
        "",
    ]
    lines += [f"Tone {tone} samples: {tones.get(tone, 0)}" for tone in KEEP_TONES]
    lines.append("")
    lines += [f"Tone {tone} speakers: {speakers_by_tone[tone]}" for tone in KEEP_TONES]
    lines += [
        "",
        f"Unique syllable bases: {len(bases)}",
        "",
        f"Excluded neutral-tone samples: {excluded.get('neutral_tone', 0)}",
        f"Excluded multi-syllable samples: {excluded.get('multi_syllable', 0)}",
        f"Excluded invalid samples: {excluded.get('invalid', 0)}",
        "",
        f"Saved metadata path: {path}",
        "",
        "--- variety / orthography coverage ---",
        schema.describe_coverage(rows),
        "",
        "--- distribution ---",
    ]
    for tone in KEEP_TONES:
        count = tones.get(tone, 0)
        lines.append(f"  Tone {tone}: {count:>6}  ({count / total * 100:5.1f}%)")

    counts = [tones.get(tone, 0) for tone in KEEP_TONES]
    ratio = (max(counts) / min(counts)) if min(counts) else float("inf")
    verdict = (
        "severely imbalanced" if ratio >= 3
        else "moderately imbalanced" if ratio >= 1.5
        else "reasonably balanced"
    )
    lines += [
        f"  max/min ratio: {ratio:.2f}  -> {verdict}",
        "",
        "--- 20 most frequent syllable bases ---",
    ]
    for base, count in bases.most_common(20):
        lines.append(f"  {base:<8} {count}")
    return "\n".join(lines)


def save(rows: List[Dict], path: Path) -> Path:
    import csv

    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(schema.SAMPLE_FIELDS)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default=DATASET_ID)
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--limit", type=int, help="inspect only the first N rows")
    args = parser.parse_args()

    rows, excluded, original = prepare(args.dataset, args.limit)
    if not rows:
        print("No single-syllable tone 1-4 records were found.")
        return
    path = save(rows, Path(args.out))
    print(summarise(rows, excluded, original, path))


if __name__ == "__main__":
    main()
