"""Blind padding comparison, re-run under the binary usability criterion.

The three-level padding diagnostic is unusable: the scale it depended on
repeated itself only 36% of the time. The binary criterion repeats at 90%, so
the same question is asked again with the instrument that works.

Same 44 tokens as before and the same alignment timestamps, so nothing about
composition or alignment changes -- only how much symmetric context surrounds
the syllable, and which question is asked about it.

PRE-REGISTERED before any judgment exists:

  Primary   : 40 ms vs 0 ms, paired on the same tokens, exact McNemar.
  Secondary : 20 ms and 60 ms, descriptive only.
  40 ms is recommended only if its ACCEPT rate is at least that of 0 ms, more
  tokens move REJECT->ACCEPT than the reverse, clean auto-good segments are not
  damaged, and the direction is consistent even without significance.
  A numerically higher 20 ms or 60 ms does not override the primary comparison.

Known limitation, stated in advance: with ACCEPT running near 90%, most pairs
will agree and McNemar sees only the discordant ones. Roughly 6 discordant
pairs all pointing one way are needed for p<0.05. This experiment can show
direction and rule out harm; it is unlikely to prove significance.

    python -m pronunciation.wav2vec_tone.prepare_binary_padding
    python -m pronunciation.wav2vec_tone.serve_review --round binpad
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
SOURCE_KEY = DATA_DIR / "padding_trial_key.csv"
TRIAL_DIR = DATA_DIR / "binpad_trial_segments"
KEY_CSV = DATA_DIR / "binpad_trial_key.csv"
PAGE = DATA_DIR / "review_binpad.html"

SAMPLE_RATE = 16000
PADDING_MS = (0, 20, 40, 60)
PRIMARY = (40, 0)


def source_tokens() -> list[dict]:
    """The 44 tokens from the earlier padding diagnostic, one row each.

    Reused deliberately: holding composition fixed means any difference from
    the previous run is the criterion, not the sample.
    """
    if not SOURCE_KEY.exists():
        sys.exit(f"{SOURCE_KEY} not found — run prepare_padding_review first.")
    seen, tokens = set(), []
    for row in csv.DictReader(SOURCE_KEY.open(encoding="utf-8")):
        if row["token_id"] in seen:
            continue
        seen.add(row["token_id"])
        tokens.append(row)
    return tokens


def order_trials(tokens, seed: int):
    """Longest-waiting-first, so a token's four versions sit far apart.

    Hearing the same syllable twice in quick succession turns an absolute
    judgement into a comparison, which is exactly what blinding is meant to
    prevent.
    """
    rng = np.random.default_rng(seed)
    remaining = {}
    for token in tokens:
        paddings = list(PADDING_MS)
        rng.shuffle(paddings)
        remaining[token["token_id"]] = {"token": token, "paddings": paddings}

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
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()

    import soundfile as sf

    tokens = source_tokens()
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
        begin = max(0, int(round((float(token["orig_start"]) - pad) * SAMPLE_RATE)))
        finish = min(len(audio),
                     int(round((float(token["orig_end"]) + pad) * SAMPLE_RATE)))
        if begin == 0 or finish == len(audio):
            edge_clipped += 1
        segment = audio[begin:finish]

        trial_id = f"Q{number:03d}"
        # Named for the trial only. A condition in the filename would show up
        # in the browser's network panel and undo the blinding.
        sf.write(TRIAL_DIR / f"{trial_id}.wav", segment, SAMPLE_RATE)

        key_rows.append({
            "trial_id": trial_id,
            "token_id": token["token_id"],
            "padding_ms": trial["padding_ms"],
            "alignment_status": token["alignment_status"],
            "prior_three_level": token["original_judgment"],
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
            "segment_path": f"binpad_trial_segments/{trial_id}.wav",
            "utterance_path":
                f"../../../private-data/ompal/wav/SPEAKER{utterance_id[1:6]}/{utterance_id}.wav",
        })

    with KEY_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(key_rows[0].keys()))
        writer.writeheader()
        writer.writerows(key_rows)

    PAGE.write_text(
        render(page_items,
               storage_key="ompal_binpad_review",
               download_name="ompal_binpad_human_review.csv",
               heading="Does this segment support tone analysis?"),
        encoding="utf-8")

    positions = defaultdict(list)
    for index, trial in enumerate(trials):
        positions[trial["token"]["token_id"]].append(index)
    gaps = [min(b[i + 1] - b[i] for i in range(len(b) - 1))
            for b in (sorted(v) for v in positions.values())]

    print(f"tokens (reused)  : {len(tokens)}")
    print(f"conditions       : {', '.join(str(p) + ' ms' for p in PADDING_MS)}")
    print(f"trials           : {len(trials)}  (~{len(trials) * 6 / 60:.0f} min)")
    print(f"same-token gap   : min {min(gaps)}, median {int(np.median(gaps))}")
    print(f"edge-clipped     : {edge_clipped}")
    print(f"automatic status : "
          + ", ".join(f"{k}={v}" for k, v in
                      sorted(Counter(t['alignment_status'] for t in tokens).items())))
    print(f"prior three-level: "
          + ", ".join(f"{k}={v}" for k, v in
                      sorted(Counter(t['original_judgment'] for t in tokens).items())))
    print(f"tones            : "
          + ", ".join(f"T{k}={v}" for k, v in
                      sorted(Counter(t['expected_tone'] for t in tokens).items())))
    print(f"speakers         : {len({t['speaker_id'] for t in tokens})}")
    print(f"\nPRE-REGISTERED primary: {PRIMARY[0]} ms vs {PRIMARY[1]} ms, "
          f"paired, exact McNemar")
    print(f"key (do NOT open before reviewing): {KEY_CSV}")
    print(f"page: {PAGE}")
    print("\n  python -m pronunciation.wav2vec_tone.serve_review --round binpad")


if __name__ == "__main__":
    main()
