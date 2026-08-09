import numpy as np

from pronunciation.wav2vec_tone.nested_speaker_audit import (
    best_threshold,
    design,
    normalise_trajectory,
)


def test_design_has_only_acoustics_and_prompt_tone_interactions():
    base = np.asarray([[1.0, 2.0], [3.0, 4.0]])
    matrix = design(base, np.asarray(["1", "4"]))

    # two acoustic columns + T2/T3/T4 dummies + three interaction blocks.
    assert matrix.shape == (2, 11)
    assert np.array_equal(matrix[0, 2:5], [0.0, 0.0, 0.0])
    assert np.array_equal(matrix[1, 2:5], [0.0, 0.0, 1.0])


def test_unvoiced_trajectory_stays_missing_for_fold_local_imputation():
    output = normalise_trajectory(np.asarray([[10.0, 12.0], [np.nan, np.nan]]))
    assert np.allclose(output[0], [-1.0, 1.0])
    assert np.isnan(output[1]).all()


def test_best_threshold_uses_balanced_accuracy_not_majority_accuracy():
    y = np.asarray([0, 0, 0, 1])
    scores = np.asarray([0.1, 0.2, 0.3, 0.9])
    assert best_threshold(y, scores) <= 0.8
