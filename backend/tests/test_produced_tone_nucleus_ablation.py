import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pronunciation.wav2vec_tone.produced_tone_nucleus_ablation import (  # noqa: E402
    TONES, centre, score_oof,
)


def test_nucleus_centres_only_its_own_acoustic_contour_and_oof_is_complete():
    contour = np.asarray([[70.0, 71.0, 72.0], [100.0, 100.0, 100.0]])
    assert np.allclose(centre(contour), [[-1.0, 0.0, 1.0], [0.0, 0.0, 0.0]])
    labels = np.tile(np.asarray(TONES), 6)
    groups = np.repeat([f"s{i}" for i in range(6)], 4)
    features = np.column_stack([np.tile(np.arange(4), 6), np.ones(len(labels))])
    scores = score_oof(features, labels, groups, folds=3)
    assert scores.shape == (24, 4)
    assert np.isfinite(scores).all()
