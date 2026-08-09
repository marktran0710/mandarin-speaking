import numpy as np

from pronunciation.wav2vec_tone.voiced_nucleus_features import (
    POINTS,
    VOICED_NUCLEUS_PROXY_SCHEMA_VERSION,
    VOICED_NUCLEUS_PROXY_UNIT,
    _longest_contiguous_run,
    cache_metadata,
    load_train_cache,
    voiced_nucleus_proxy_from_segment,
)


def test_longest_contiguous_run_keeps_the_longest_frame_sequence():
    assert _longest_contiguous_run(np.asarray([1, 2, 5, 6, 7, 10])).tolist() == [5, 6, 7]


def test_proxy_is_audio_only_and_returns_semitones_for_a_voiced_sine():
    sample_rate = 16000
    time = np.arange(int(sample_rate * 0.25)) / sample_rate
    audio = 0.2 * np.sin(2 * np.pi * 200 * time)

    trajectory, status = voiced_nucleus_proxy_from_segment(audio, sample_rate)

    assert trajectory.shape == (POINTS,)
    assert np.isfinite(trajectory).all()
    assert 85 < float(np.median(trajectory)) < 100  # 200 Hz is ~91.7 semitones.
    assert status in {"energy_voiced_nucleus_proxy", "energy_proxy_insufficient_full_voiced"}


def test_train_cache_loader_rejects_non_train_or_wrong_unit_cache(tmp_path):
    path = tmp_path / "nucleus.npz"
    metadata = cache_metadata()
    metadata["unit"] = "hz"  # A unit mismatch must never be auto-converted.
    np.savez_compressed(
        path,
        token_ids=np.asarray(["a"], dtype=object),
        trajectories=np.zeros((1, POINTS)),
        statuses=np.asarray(["energy_voiced_nucleus_proxy"], dtype=object),
        metadata_json=np.asarray(__import__("json").dumps(metadata)),
    )

    try:
        load_train_cache(np.asarray(["a"]), path)
    except ValueError as error:
        assert "unit mismatch" in str(error)
    else:
        raise AssertionError("expected cache-unit validation failure")


def test_train_cache_loader_selects_an_explicit_ordered_train_subset(tmp_path):
    path = tmp_path / "nucleus.npz"
    np.savez_compressed(
        path,
        token_ids=np.asarray(["a", "b"], dtype=object),
        trajectories=np.asarray([np.full(POINTS, 80.0), np.full(POINTS, 90.0)]),
        statuses=np.asarray(["energy_voiced_nucleus_proxy", "intensity_unavailable_full_voiced"], dtype=object),
        metadata_json=np.asarray(__import__("json").dumps(cache_metadata())),
    )

    trajectories, statuses, _ = load_train_cache(np.asarray(["b", "a"]), path)

    assert np.allclose(trajectories[:, 0], [90.0, 80.0])
    assert statuses.tolist() == ["intensity_unavailable_full_voiced", "energy_voiced_nucleus_proxy"]


def test_schema_metadata_identifies_proxy_not_phone_alignment():
    metadata = cache_metadata()
    assert metadata["schema_version"] == VOICED_NUCLEUS_PROXY_SCHEMA_VERSION
    assert metadata["unit"] == VOICED_NUCLEUS_PROXY_UNIT
    assert metadata["not_phone_alignment"] is True
