"""One-off selection script (not part of the test suite / CI).

Picks a small, representative subset of OMPAL utterances for vendoring into
this directory (backend/tests/fixtures/ompal_sample/): mixes native +
learner speakers, mixes tones 1-4, and mixes clear-consensus correct vs
incorrect rater judgments (avoids utterances where raters disagree, so the
vendored reference label is unambiguous).

Vendored here for reproducibility/audit — it is NOT run in CI and does not
need to be, since the corpus this reads from (backend/private-data/ompal/)
is gitignored and not present in a normal checkout. Re-run by hand only if
the vendored subset needs to be regenerated:

    cd backend && python tests/fixtures/ompal_sample/select_ompal_subset.py

Requires the full OMPAL corpus locally at backend/private-data/ompal/ (see
backend/benchmarking/ompal_corpus.py:download_corpus).
"""
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from benchmarking.ompal_corpus import load_utterances  # noqa: E402

CORPUS_ROOT = BACKEND / "private-data" / "ompal"


def word_consensus(word) -> str:
    """'correct' / 'incorrect' / 'mixed' — unanimous rater agreement only."""
    labels = word.rater_tone_labels
    if not labels:
        return "unlabeled"
    if all(labels):
        return "correct"
    if not any(labels):
        return "incorrect"
    return "mixed"


def utterance_summary(u):
    consensus = [word_consensus(w) for w in u.words]
    tones = sorted({t for w in u.words for t in w.expected_tones})
    return {
        "utterance_id": u.utterance_id,
        "speaker_id": u.speaker_id,
        "is_native": u.is_native,
        "text": u.text,
        "wav_path": str(u.wav_path),
        "tones": tones,
        "n_words": len(u.words),
        "n_correct_words": consensus.count("correct"),
        "n_incorrect_words": consensus.count("incorrect"),
        "n_mixed_or_unlabeled": consensus.count("mixed") + consensus.count("unlabeled"),
        "words": [
            {
                "text": w.text,
                "expected_tones": list(w.expected_tones),
                "consensus": word_consensus(w),
                "n_raters": len(w.rater_tone_labels),
            }
            for w in u.words
        ],
    }


def main():
    utterances = load_utterances(CORPUS_ROOT)
    print(f"total utterances: {len(utterances)}", file=sys.stderr)

    # Only consider short utterances (<=6 words) so vendored audio stays
    # small and the reference transcript is easy to read in a test file.
    candidates = [u for u in utterances if 2 <= len(u.words) <= 6]
    print(f"candidates (2-6 words): {len(candidates)}", file=sys.stderr)

    summaries = [utterance_summary(u) for u in candidates]

    # Bucket by (is_native, has a clean incorrect word, has a clean correct word)
    native_clean_correct = [
        s for s in summaries
        if s["is_native"] and s["n_incorrect_words"] == 0 and s["n_correct_words"] == s["n_words"]
    ]
    learner_clean_correct = [
        s for s in summaries
        if not s["is_native"] and s["n_incorrect_words"] == 0 and s["n_correct_words"] == s["n_words"]
    ]
    learner_has_incorrect = [
        s for s in summaries
        if not s["is_native"] and s["n_incorrect_words"] >= 1 and s["n_mixed_or_unlabeled"] == 0
    ]

    print(f"native, all-correct: {len(native_clean_correct)}", file=sys.stderr)
    print(f"learner, all-correct: {len(learner_clean_correct)}", file=sys.stderr)
    print(f"learner, has a clean-incorrect word: {len(learner_has_incorrect)}", file=sys.stderr)

    def tone_coverage(pool, want=4):
        """Greedily pick items until tones 1-4 all appear at least once."""
        picked = []
        seen_tones = set()
        for s in sorted(pool, key=lambda s: s["utterance_id"]):
            new_tones = set(s["tones"]) - seen_tones
            if new_tones or len(picked) < want:
                picked.append(s)
                seen_tones |= set(s["tones"])
            if len(picked) >= want and {1, 2, 3, 4} <= seen_tones:
                break
        return picked

    selected = []
    selected += tone_coverage(native_clean_correct, want=4)
    selected += tone_coverage(learner_clean_correct, want=6)
    selected += tone_coverage(learner_has_incorrect, want=6)

    out_path = Path(__file__).parent / "ompal_subset_candidates.json"
    out_path.write_text(
        json.dumps(selected, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nSelected {len(selected)} utterances -> {out_path}", file=sys.stderr)
    for s in selected:
        print(
            f"  {s['utterance_id']} native={s['is_native']} "
            f"tones={s['tones']} correct={s['n_correct_words']} "
            f"incorrect={s['n_incorrect_words']} text={s['text']}",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
