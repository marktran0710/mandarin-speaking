import csv
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pronunciation.wav2vec_tone.produced_tone_baseline import (  # noqa: E402
    TONES,
    contour_and_register,
    evaluate_oof,
    load_train_only,
    normalise_trajectory,
)


def test_load_train_only_uses_human_correct_rows_and_never_returns_prompt_as_feature(tmp_path):
    manifest = tmp_path / "manifest.csv"
    fields = ["token_id", "split", "expected_tone", "tone_correctness"]
    rows = [
        {"token_id": "a", "split": "train", "expected_tone": "1", "tone_correctness": "1"},
        {"token_id": "b", "split": "train", "expected_tone": "2", "tone_correctness": "0"},
        {"token_id": "c", "split": "dev", "expected_tone": "3", "tone_correctness": "1"},
    ]
    with manifest.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    cache = tmp_path / "cache.npz"
    np.savez(cache, praat=np.array([[1.0], [2.0], [3.0]]),
             token_ids=np.array(["a", "b", "c"], dtype=object),
             split=np.array(["train", "train", "dev"], dtype=object),
             speaker=np.array(["s1", "s2", "s3"], dtype=object))
    trajectories = tmp_path / "trajectory.npz"
    np.savez(trajectories, learner=np.array([[100.0, 110.0], [120.0, 130.0], [140.0, 150.0]]))

    features, labels, speakers, ids = load_train_only(manifest, cache, trajectories)

    # two centred contour values + one pitch register + one acoustic summary
    assert features.shape == (1, 4)
    assert labels.tolist() == ["1"]
    assert speakers.tolist() == ["s1"]
    assert ids.tolist() == ["a"]


def test_oof_is_speaker_disjoint_and_returns_all_tone_probabilities():
    rng = np.random.default_rng(2)
    labels = np.repeat(np.asarray(TONES), 8)
    speakers = np.repeat([f"speaker-{index}" for index in range(8)], 4)
    # Acoustic data intentionally has a recoverable class signal, without
    # smuggling labels through an identity feature.
    features = np.column_stack([
        np.tile(np.arange(4, dtype=float), 8) + rng.normal(0, 0.02, 32),
        rng.normal(0, 1, 32),
    ])
    ids = np.asarray([f"token-{index}" for index in range(32)])

    report = evaluate_oof(features, labels, speakers, ids, folds=4)

    assert report["n_tokens"] == 32
    assert report["protocol"]["forbidden_features"]
    assert all(set(fold["held_out_speakers"]).isdisjoint(
        set().union(*(set(other["held_out_speakers"]) for other in report["folds"] if other != fold))
    ) for fold in report["folds"])
    assert set(report["rows"][0]) >= {"probability_T1", "probability_T2", "probability_T3", "probability_T4"}


def test_phase_c6_semitones_are_centered_without_a_second_log_transform():
    # Phase C6 caches 12*log2(Hz), so 84/96 are already semitones.  A second
    # log would produce about +/-1 rather than the correct +/-6 contour shape.
    semitone_cache = np.asarray([[84.0, 96.0], [np.nan, np.nan]])
    centred = normalise_trajectory(semitone_cache)

    assert np.allclose(centred[0], [-6.0, 6.0])
    assert np.isnan(centred[1]).all()


def test_contour_and_register_keep_shape_and_audio_derived_register_separate():
    contour, register = contour_and_register(np.asarray([[80.0, 84.0, 88.0]]))

    assert np.allclose(contour, [[-4.0, 0.0, 4.0]])
    assert np.allclose(register, [[84.0]])
