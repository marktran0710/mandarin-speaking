import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pronunciation.wav2vec_tone.produced_tone_fusion_nested import (  # noqa: E402
    TONES,
    evaluate_nested_oof,
)


def test_nested_fusion_oof_is_speaker_disjoint_and_contains_canonical_probabilities():
    rng = np.random.default_rng(12)
    # Every speaker supplies every tone twice. The only signal is acoustic;
    # IDs are merely split groups and never enter a feature matrix.
    labels = np.tile(np.repeat(np.asarray(TONES), 2), 12)
    speakers = np.repeat([f"speaker-{index}" for index in range(12)], 8)
    tone_signal = np.tile(np.repeat(np.arange(4, dtype=float), 2), 12)
    matrices = {
        "f0_praat": np.column_stack([tone_signal, rng.normal(size=len(labels))]),
        "wav2vec_mean": np.column_stack([tone_signal * 0.8, rng.normal(size=(len(labels), 3))]),
    }
    matrices["fusion"] = np.hstack([matrices["wav2vec_mean"], matrices["f0_praat"]])
    tokens = np.asarray([f"token-{index}" for index in range(len(labels))])

    report = evaluate_nested_oof(matrices, labels, speakers, tokens, outer_folds=4, inner_folds=3)

    assert report["n_tokens"] == len(labels)
    assert report["n_speakers"] == 12
    assert report["protocol"]["outer_cv"] == "GroupKFold(4) by speaker_id"
    assert "expected tone/prompt" in report["protocol"]["forbidden_features"]
    assert len(report["outer_fold_selections"]) == 4
    assert all({"decision_score_T1", "decision_score_T2", "decision_score_T3", "decision_score_T4"} <= set(row)
               for row in report["rows"])
