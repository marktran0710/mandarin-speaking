"""Fresh blinded sample to confirm rms_relative_db as a QC signal.

Sampling is deliberately blind to every QC feature under test. Balancing runs
over speaker, tone, lexical item, duration and broad initial class only, so
the confirmation set is a fair slice of the material rather than one enriched
at either end of the measure being validated.

Ten hidden duplicates ride along to measure how repeatable the human judgement
is on this material. They are chosen to span the range of rms_relative_db --
not to influence sampling, since they are drawn from tokens already selected,
and they are excluded from the QC analysis as independent observations.

    python -m pronunciation.wav2vec_tone.prepare_qc_confirmation
    python -m pronunciation.wav2vec_tone.serve_review --round qc
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pronunciation.wav2vec_tone import frozen_qc
from pronunciation.wav2vec_tone.prepare_binary_reliability import load_audio, render

DATA_DIR = Path(__file__).resolve().parent / "data"
OMPAL_DIR = Path(__file__).resolve().parents[2] / "private-data" / "ompal"
PILOT_CSV = DATA_DIR / "ompal_alignment_pilot.csv"
TRIAL_DIR = DATA_DIR / "qc_trial_segments"
KEY_CSV = DATA_DIR / "qc_trial_key.csv"
PAGE = DATA_DIR / "review_qc.html"
SAMPLE_RATE = 16000
MIN_DUPLICATE_SEPARATION = 20

PRIOR_REVIEWS = (
    ("ompal_alignment_review_items.csv", "pair"),
    ("ompal_alignment_review_items_round2.csv", "pair"),
    ("padding_trial_key.csv", "token_id"),
    ("binary_trial_key.csv", "token_id"),
    ("binpad_trial_key.csv", "token_id"),
    ("confirm_trial_key.csv", "token_id"),
    ("audit_trial_key.csv", "token_id"),
)

# Broad initial classes. Grouped by manner and aspiration because those are
# what plausibly drive token loudness: aspirated stops release a burst of
# noise, sonorants are fully voiced throughout, fricatives sustain turbulence.
# Documented here and used only descriptively -- never as a QC predictor.
INITIAL_CLASSES = {
    "sonorant_or_zero": ("m", "n", "l", "r", "y", "w"),
    "unaspirated_obstruent": ("b", "d", "g", "j", "zh", "z"),
    "aspirated_obstruent": ("p", "t", "k", "q", "ch", "c"),
    "fricative": ("f", "s", "sh", "x", "h"),
}


def romanize(pinyin: str) -> str:
    decomposed = unicodedata.normalize("NFD", pinyin)
    return "".join(c for c in decomposed
                   if unicodedata.category(c) != "Mn").lower().strip()


def initial_class(pinyin: str) -> str:
    """Broad onset class from the expected pinyin; 'zero' counts as sonorant."""
    base = re.sub(r"[^a-z]", "", romanize(pinyin))
    if not base:
        return "unknown"
    for length in (2, 1):
        prefix = base[:length]
        for name, members in INITIAL_CLASSES.items():
            if prefix in members:
                return name
    return "sonorant_or_zero"      # vowel-initial syllables


def previously_used() -> set:
    used = set()
    for filename, style in PRIOR_REVIEWS:
        path = DATA_DIR / filename
        if not path.exists():
            continue
        for row in csv.DictReader(path.open(encoding="utf-8")):
            if style == "pair":
                used.add((row["utterance_id"], str(int(row["token_index"]))))
            else:
                utterance, index = row["token_id"].rsplit("_", 1)
                used.add((utterance, str(int(index))))
    return used


def duration_bin(row) -> str:
    value = float(row["duration_seconds"])
    return ("short" if value < 0.12 else "mid" if value < 0.18
            else "long" if value < 0.26 else "xlong")


def select(count: int, seed: int, max_per_word: int, used: set, lengths: dict):
    """Balance on speaker, tone, word, duration and onset class only.

    None of the QC features under test enters this decision. Enriching either
    end of rms_relative_db would guarantee a strong-looking AUC that says
    nothing about the corpus.
    """
    rows = []
    for row in csv.DictReader(PILOT_CSV.open(encoding="utf-8")):
        if not row["start_seconds"] or row["alignment_status"] != "good":
            continue
        if (row["utterance_id"], str(int(row["token_index"]))) in used:
            continue
        length = lengths[row["utterance_id"]]
        if float(row["start_seconds"]) <= 0 or float(row["end_seconds"]) >= length:
            continue        # extraction hit the utterance edge
        row["initial_class"] = initial_class(row["expected_pinyin"])
        rows.append(row)

    rng = np.random.default_rng(seed)
    rng.shuffle(rows)

    chosen, taken = [], set()
    tones, onsets, bins, speakers, words = (
        Counter(), Counter(), Counter(), Counter(), Counter())
    while len(chosen) < count:
        candidates = [r for r in rows
                      if id(r) not in taken and words[r["word"]] < max_per_word]
        if not candidates:
            break
        candidates.sort(key=lambda r: (
            tones[r["expected_tone"]], onsets[r["initial_class"]],
            bins[duration_bin(r)], speakers[r["speaker_id"]], words[r["word"]]))
        pick = candidates[0]
        taken.add(id(pick))
        chosen.append(pick)
        tones[pick["expected_tone"]] += 1
        onsets[pick["initial_class"]] += 1
        bins[duration_bin(pick)] += 1
        speakers[pick["speaker_id"]] += 1
        words[pick["word"]] += 1
    return chosen


def order_trials(unique_rows, duplicate_rows, seed: int):
    rng = np.random.default_rng(seed + 3)
    entries = ([{"row": r, "repeat": 0} for r in unique_rows]
               + [{"row": r, "repeat": 1} for r in duplicate_rows])
    for _ in range(4000):
        rng.shuffle(entries)
        seen, ok = {}, True
        for position, entry in enumerate(entries):
            token = (entry["row"]["utterance_id"], entry["row"]["token_index"])
            if token in seen and position - seen[token] < MIN_DUPLICATE_SEPARATION:
                ok = False
                break
            seen[token] = position
        if ok:
            return entries
    raise RuntimeError("could not separate duplicates")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tokens", type=int, default=100)
    parser.add_argument("--duplicates", type=int, default=10)
    parser.add_argument("--max-per-word", type=int, default=5)
    parser.add_argument("--seed", type=int, default=31)
    args = parser.parse_args()

    import soundfile as sf

    used = previously_used()
    lengths = {}
    for row in csv.DictReader(PILOT_CSV.open(encoding="utf-8")):
        utterance_id = row["utterance_id"]
        if utterance_id not in lengths:
            info = sf.info(str(OMPAL_DIR
                               / f"wav/SPEAKER{utterance_id[1:6]}/{utterance_id}.wav"))
            lengths[utterance_id] = info.frames / info.samplerate

    chosen = select(args.tokens, args.seed, args.max_per_word, used, lengths)
    overlap = {(r["utterance_id"], str(int(r["token_index"]))) for r in chosen} & used
    if overlap:
        sys.exit(f"FRESHNESS ASSERTION FAILED: {len(overlap)} reused token(s)")
    print(f"freshness assertion: PASSED — 0 of {len(chosen)} tokens seen before "
          f"({len(used)} excluded)")

    # Features are computed now, after selection, so they cannot have shaped it.
    cache: dict[str, np.ndarray] = {}
    for row in chosen:
        utterance_id = row["utterance_id"]
        if utterance_id not in cache:
            cache[utterance_id] = load_audio(
                OMPAL_DIR / f"wav/SPEAKER{utterance_id[1:6]}/{utterance_id}.wav")
        audio = cache[utterance_id]
        begin = max(0, int(round(float(row["start_seconds"]) * SAMPLE_RATE)))
        finish = min(len(audio), int(round(float(row["end_seconds"]) * SAMPLE_RATE)))
        segment = audio[begin:finish]
        row["_segment"] = (begin, finish)
        row["rms_relative_db"] = frozen_qc.rms_relative_db(segment, audio)
        row["local_snr_db"] = frozen_qc.local_snr_db(segment, audio, (begin, finish))

    # Duplicates span the measured range so reliability is not estimated only
    # on comfortable cases.
    ordered = sorted(chosen, key=lambda r: r["rms_relative_db"])
    positions = np.linspace(0, len(ordered) - 1, args.duplicates).round().astype(int)
    duplicates = [ordered[int(p)] for p in dict.fromkeys(positions)]

    entries = order_trials(chosen, duplicates, args.seed)
    TRIAL_DIR.mkdir(parents=True, exist_ok=True)
    for old in TRIAL_DIR.glob("*.wav"):
        old.unlink()

    key_rows, page_items = [], []
    for number, entry in enumerate(entries, start=1):
        row = entry["row"]
        utterance_id = row["utterance_id"]
        begin, finish = row["_segment"]
        segment = cache[utterance_id][begin:finish]
        trial_id = f"Q{number:03d}"
        sf.write(TRIAL_DIR / f"{trial_id}.wav", segment, SAMPLE_RATE)

        key_rows.append({
            "trial_id": trial_id,
            "token_id": f"{utterance_id}_{int(row['token_index']):02d}",
            "is_repeat": entry["repeat"],
            "rms_relative_db": f"{row['rms_relative_db']:.4f}",
            "local_snr_db": ("" if not np.isfinite(row["local_snr_db"])
                             else f"{row['local_snr_db']:.4f}"),
            "alignment_score": row["alignment_score"],
            "duration_seconds": row["duration_seconds"],
            "voiced_proportion": row["voiced_proportion"],
            "alignment_status": row["alignment_status"],
            "word": row["word"], "expected_pinyin": row["expected_pinyin"],
            "expected_tone": row["expected_tone"],
            "initial_class": row["initial_class"],
            "speaker_id": row["speaker_id"], "utterance_id": utterance_id,
            "majority_tone_correct": row["majority_tone_correct"],
        })
        page_items.append({
            "trial_id": trial_id, "word": row["word"],
            "expected_pinyin": row["expected_pinyin"],
            "segment_path": f"qc_trial_segments/{trial_id}.wav",
            "utterance_path":
                f"../../../private-data/ompal/wav/SPEAKER{utterance_id[1:6]}/{utterance_id}.wav",
        })

    with KEY_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(key_rows[0].keys()))
        writer.writeheader()
        writer.writerows(key_rows)
    PAGE.write_text(
        render(page_items, storage_key="ompal_qc_review",
               download_name="ompal_qc_human_review.csv",
               heading="Does this segment support tone analysis?"),
        encoding="utf-8")

    seen = defaultdict(list)
    for index, entry in enumerate(entries):
        seen[(entry["row"]["utterance_id"], entry["row"]["token_index"])].append(index)
    gaps = [max(v) - min(v) for v in seen.values() if len(v) > 1]
    values = np.asarray([r["rms_relative_db"] for r in chosen])
    predicted = [frozen_qc.qc_keep(v) for v in values]

    print(f"\nunique tokens     : {len(chosen)}")
    print(f"hidden duplicates : {len(duplicates)}  (separation min {min(gaps)})")
    print(f"total trials      : {len(entries)}")
    print(f"speakers          : {len({r['speaker_id'] for r in chosen})}, "
          f"words: {len({r['word'] for r in chosen})} "
          f"(max {max(Counter(r['word'] for r in chosen).values())})")
    print(f"tones             : "
          + ", ".join(f"T{k}={v}" for k, v in
                      sorted(Counter(r['expected_tone'] for r in chosen).items())))
    print(f"initial classes   : "
          + ", ".join(f"{k}={v}" for k, v in
                      sorted(Counter(r['initial_class'] for r in chosen).items())))
    print(f"duration bins     : "
          + ", ".join(f"{k}={v}" for k, v in
                      sorted(Counter(duration_bin(r) for r in chosen).items())))
    print(f"\nrms_relative_db in sample: min {values.min():.2f}  median "
          f"{np.median(values):.2f}  max {values.max():.2f} dB")
    print(f"local_snr_db available   : "
          f"{sum(1 for r in chosen if np.isfinite(r['local_snr_db']))}/{len(chosen)}")
    print(f"frozen rule would keep   : {sum(1 for p in predicted if p)}/{len(chosen)} "
          f"({sum(1 for p in predicted if p) / len(chosen) * 100:.0f}%)  "
          f"[prediction recorded now, hidden from the reviewer]")
    print(f"\nkey (do NOT open before reviewing): {KEY_CSV}")
    print(f"page: {PAGE}")
    print("\n  python -m pronunciation.wav2vec_tone.serve_review --round qc")


if __name__ == "__main__":
    main()
