"""Confirmatory test of +/-20 ms padding on tokens never reviewed before.

The pre-registered 40 ms hypothesis failed and stays failed. 20 ms looked best
in that experiment, but it was a secondary condition on the same 44 tokens, so
adopting it there would be selecting a winner after the fact on the data that
produced it. This is the independent test.

Only 0 ms and 20 ms are built. 40 ms and 60 ms are not re-tested, and no other
value is searched -- widening the grid after seeing which value won is the same
error in a different costume.

Every token is asserted absent from all five previous reviews, by token id and
against every key file that exists. The assertion is fatal: a single reused
token would make this confirmation partly a re-test.

    python -m pronunciation.wav2vec_tone.prepare_confirm_padding
    python -m pronunciation.wav2vec_tone.serve_review --round confirm
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pronunciation.wav2vec_tone.prepare_binary_reliability import load_audio, render

DATA_DIR = Path(__file__).resolve().parent / "data"
OMPAL_DIR = Path(__file__).resolve().parents[2] / "private-data" / "ompal"
PILOT_CSV = DATA_DIR / "ompal_alignment_pilot.csv"
TRIAL_DIR = DATA_DIR / "confirm_trial_segments"
KEY_CSV = DATA_DIR / "confirm_trial_key.csv"
PAGE = DATA_DIR / "review_confirm.html"

SAMPLE_RATE = 16000
PADDING_MS = (0, 20)

# Every earlier review, and how to read a token identity out of it.
PRIOR_REVIEWS = (
    ("round1", "ompal_alignment_review_items.csv", "pair"),
    ("round2", "ompal_alignment_review_items_round2.csv", "pair"),
    ("padding", "padding_trial_key.csv", "token_id"),
    ("binary", "binary_trial_key.csv", "token_id"),
    ("binpad", "binpad_trial_key.csv", "token_id"),
)


def previously_used() -> tuple[set, dict]:
    used, per_source = set(), {}
    for name, filename, style in PRIOR_REVIEWS:
        path = DATA_DIR / filename
        if not path.exists():
            per_source[name] = None
            continue
        ids = set()
        for row in csv.DictReader(path.open(encoding="utf-8")):
            if style == "pair":
                ids.add((row["utterance_id"], row["token_index"]))
            else:
                utterance, index = row["token_id"].rsplit("_", 1)
                ids.add((utterance, str(int(index))))
        per_source[name] = len(ids)
        used |= ids
    return used, per_source


def select(count: int, seed: int, max_per_word: int, used: set):
    """Fresh automatic-good tokens, spread over tone, duration, speaker, word.

    Automatic good by preference: these are the segments that would actually
    enter benchmark v1, so the confirmation should be run on the population the
    decision applies to.
    """
    rows = [
        r for r in csv.DictReader(PILOT_CSV.open(encoding="utf-8"))
        if r["segment_path"] and r["start_seconds"]
        and r["alignment_status"] == "good"
        and (r["utterance_id"], r["token_index"]) not in used
    ]
    rng = np.random.default_rng(seed)
    rng.shuffle(rows)

    def bucket(row):
        value = float(row["duration_seconds"])
        return ("short" if value < 0.14 else "mid" if value < 0.20
                else "long" if value < 0.28 else "xlong")

    chosen, taken = [], set()
    tones, buckets, speakers, words = Counter(), Counter(), Counter(), Counter()
    while len(chosen) < count:
        candidates = [r for r in rows
                      if id(r) not in taken and words[r["word"]] < max_per_word]
        if not candidates:
            break
        candidates.sort(key=lambda r: (
            tones[r["expected_tone"]], buckets[bucket(r)],
            speakers[r["speaker_id"]], words[r["word"]],
        ))
        pick = candidates[0]
        taken.add(id(pick))
        chosen.append(pick)
        tones[pick["expected_tone"]] += 1
        buckets[bucket(pick)] += 1
        speakers[pick["speaker_id"]] += 1
        words[pick["word"]] += 1
    return chosen


def order_trials(tokens, seed: int):
    """Longest-waiting-first so a token's two versions sit far apart."""
    rng = np.random.default_rng(seed + 1)
    remaining = {}
    for token in tokens:
        paddings = list(PADDING_MS)
        rng.shuffle(paddings)
        key = (token["utterance_id"], token["token_index"])
        remaining[key] = {"token": token, "paddings": paddings}

    order, last_seen, position = [], {k: -10**6 for k in remaining}, 0
    while any(entry["paddings"] for entry in remaining.values()):
        available = [k for k, e in remaining.items() if e["paddings"]]
        oldest = min(last_seen[k] for k in available)
        candidates = [k for k in available if last_seen[k] == oldest]
        key = candidates[int(rng.integers(len(candidates)))]
        entry = remaining[key]
        order.append({"token": entry["token"], "padding_ms": entry["paddings"].pop()})
        last_seen[key] = position
        position += 1
    return order


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tokens", type=int, default=72)
    parser.add_argument("--max-per-word", type=int, default=3)
    parser.add_argument("--seed", type=int, default=11)
    args = parser.parse_args()

    import soundfile as sf

    used, per_source = previously_used()
    print("previously reviewed token counts:")
    for name, _, _ in PRIOR_REVIEWS:
        count = per_source.get(name)
        print(f"  {name:<10}" + ("(key file absent)" if count is None else f"{count:>5}"))
    print(f"  {'total':<10}{len(used):>5} distinct tokens excluded")

    tokens = select(args.tokens, args.seed, args.max_per_word, used)
    if len(tokens) < args.tokens:
        print(f"WARNING: only {len(tokens)} fresh tokens available, "
              f"wanted {args.tokens}")

    # Fatal, not a warning. One reused token would make this a partial re-test
    # of material that already influenced the hypothesis.
    overlap = {(t["utterance_id"], t["token_index"]) for t in tokens} & used
    if overlap:
        sys.exit(f"FRESHNESS ASSERTION FAILED: {len(overlap)} token(s) already "
                 f"reviewed, e.g. {sorted(overlap)[:3]}")
    print(f"freshness assertion: PASSED — 0 of {len(tokens)} tokens seen before")

    trials = order_trials(tokens, args.seed)
    TRIAL_DIR.mkdir(parents=True, exist_ok=True)
    for old in TRIAL_DIR.glob("*.wav"):
        old.unlink()

    cache: dict[str, np.ndarray] = {}
    key_rows, page_items = [], []
    edge_clipped = 0

    for number, trial in enumerate(trials, start=1):
        token = trial["token"]
        utterance_id = token["utterance_id"]
        if utterance_id not in cache:
            cache[utterance_id] = load_audio(
                OMPAL_DIR / f"wav/SPEAKER{utterance_id[1:6]}/{utterance_id}.wav")
        audio = cache[utterance_id]

        pad = trial["padding_ms"] / 1000.0
        begin = max(0, int(round((float(token["start_seconds"]) - pad) * SAMPLE_RATE)))
        finish = min(len(audio),
                     int(round((float(token["end_seconds"]) + pad) * SAMPLE_RATE)))
        if begin == 0 or finish == len(audio):
            edge_clipped += 1
        segment = audio[begin:finish]

        trial_id = f"C{number:03d}"
        sf.write(TRIAL_DIR / f"{trial_id}.wav", segment, SAMPLE_RATE)

        key_rows.append({
            "trial_id": trial_id,
            "token_id": f"{utterance_id}_{int(token['token_index']):02d}",
            "padding_ms": trial["padding_ms"],
            "alignment_status": token["alignment_status"],
            "majority_tone_correct": token["majority_tone_correct"],
            "word": token["word"],
            "expected_pinyin": token["expected_pinyin"],
            "expected_tone": token["expected_tone"],
            "speaker_id": token["speaker_id"],
            "utterance_id": utterance_id,
            "duration_seconds": f"{len(segment) / SAMPLE_RATE:.4f}",
        })
        page_items.append({
            "trial_id": trial_id,
            "word": token["word"],
            "expected_pinyin": token["expected_pinyin"],
            "segment_path": f"confirm_trial_segments/{trial_id}.wav",
            "utterance_path":
                f"../../../private-data/ompal/wav/SPEAKER{utterance_id[1:6]}/{utterance_id}.wav",
        })

    with KEY_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(key_rows[0].keys()))
        writer.writeheader()
        writer.writerows(key_rows)
    PAGE.write_text(
        render(page_items,
               storage_key="ompal_confirm_review",
               download_name="ompal_confirm_human_review.csv",
               heading="Does this segment support tone analysis?"),
        encoding="utf-8")

    positions = defaultdict(list)
    for index, trial in enumerate(trials):
        positions[(trial["token"]["utterance_id"],
                   trial["token"]["token_index"])].append(index)
    gaps = [max(v) - min(v) for v in positions.values()]

    print(f"\nfresh tokens     : {len(tokens)}  (all automatic 'good')")
    print(f"conditions       : 0 ms and 20 ms only")
    print(f"trials           : {len(trials)}  (~{len(trials) * 6 / 60:.0f} min)")
    print(f"same-token gap   : min {min(gaps)}, median {int(np.median(gaps))}")
    print(f"edge-clipped     : {edge_clipped}")
    print(f"tones            : "
          + ", ".join(f"T{k}={v}" for k, v in
                      sorted(Counter(t['expected_tone'] for t in tokens).items())))
    print(f"speakers         : {len({t['speaker_id'] for t in tokens})}, "
          f"distinct words: {len({t['word'] for t in tokens})} "
          f"(max {max(Counter(t['word'] for t in tokens).values())} per word)")
    print(f"\nPRE-REGISTERED primary: 20 ms vs 0 ms, paired, exact McNemar")
    print(f"key (do NOT open before reviewing): {KEY_CSV}")
    print(f"page: {PAGE}")
    print("\n  python -m pronunciation.wav2vec_tone.serve_review --round confirm")


if __name__ == "__main__":
    main()
