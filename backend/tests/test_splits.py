"""The speaker-disjoint split — the thing every future model comparison in
this project depends on being trustworthy. Determinism and disjointness are
not incidental properties here; they are the entire point of a `final_test`
lock, so both get tested directly rather than assumed.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from benchmarking.splits import (
    SPLIT_NAMES,
    SpeakerSplit,
    create_speaker_split,
    grouped_kfold,
    load_split,
    write_split,
)

SPEAKERS = [f"SPEAKER02{i:03d}" for i in range(1, 47)]  # the real 46


class TestCreateSpeakerSplit:
    def test_every_speaker_is_assigned_to_exactly_one_partition(self):
        split = create_speaker_split(SPEAKERS)
        assigned = split.development + split.validation + split.final_test
        assert sorted(assigned) == sorted(SPEAKERS)
        assert len(set(assigned)) == len(SPEAKERS)  # no duplicates

    def test_partitions_are_pairwise_disjoint(self):
        split = create_speaker_split(SPEAKERS)
        assert not (set(split.development) & set(split.validation))
        assert not (set(split.development) & set(split.final_test))
        assert not (set(split.validation) & set(split.final_test))

    def test_same_seed_and_input_reproduce_the_identical_split(self):
        first = create_speaker_split(SPEAKERS, seed=20260810)
        second = create_speaker_split(SPEAKERS, seed=20260810)
        assert first == second

    def test_a_different_seed_gives_a_different_split(self):
        first = create_speaker_split(SPEAKERS, seed=1)
        second = create_speaker_split(SPEAKERS, seed=2)
        assert first.development != second.development

    def test_input_order_does_not_affect_the_result(self):
        """Determinism must not secretly depend on set/list iteration order,
        which is not guaranteed stable across machines or reruns."""
        forward = create_speaker_split(SPEAKERS, seed=7)
        backward = create_speaker_split(list(reversed(SPEAKERS)), seed=7)
        assert forward == backward

    def test_sizes_follow_the_requested_ratios_within_rounding(self):
        split = create_speaker_split(SPEAKERS, ratios={"development": 0.6, "validation": 0.2, "final_test": 0.2})
        # 46 speakers: 0.6*46=27.6, 0.2*46=9.2 twice -> largest-remainder
        # rounding gives 28/9/9, summing exactly to 46.
        assert len(split.development) == 28
        assert len(split.validation) == 9
        assert len(split.final_test) == 9

    def test_every_speaker_maps_back_to_its_split_name(self):
        split = create_speaker_split(SPEAKERS)
        for name in SPLIT_NAMES:
            for speaker in getattr(split, name):
                assert split.split_of(speaker) == name
        assert split.split_of("SPEAKER02999") is None

    def test_rejects_ratios_that_do_not_sum_to_one(self):
        with pytest.raises(ValueError):
            create_speaker_split(SPEAKERS, ratios={"development": 0.5, "validation": 0.2, "final_test": 0.2})

    def test_rejects_duplicate_speaker_ids(self):
        with pytest.raises(ValueError):
            create_speaker_split(SPEAKERS + [SPEAKERS[0]])

    def test_final_test_is_marked_locked_with_an_explicit_policy(self):
        payload = create_speaker_split(SPEAKERS).to_dict()
        assert payload["final_test_locked"] is True
        assert "final_test" in payload["final_test_policy"]


class TestPersistence:
    def test_round_trips_through_json(self, tmp_path):
        split = create_speaker_split(SPEAKERS)
        path = tmp_path / "split.json"
        write_split(split, path)
        reloaded = load_split(path)
        assert reloaded == split

    def test_written_file_is_stable_readable_json(self, tmp_path):
        split = create_speaker_split(SPEAKERS)
        path = tmp_path / "split.json"
        write_split(split, path)
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert set(payload["speakers"]) == set(SPLIT_NAMES)
        assert payload["seed"] == split.seed


class TestGroupedKFold:
    def test_no_speaker_appears_in_both_sides_of_a_fold(self):
        folds = grouped_kfold(SPEAKERS, k=5)
        for train, held_out in folds:
            assert not (set(train) & set(held_out))

    def test_every_speaker_is_held_out_exactly_once_across_all_folds(self):
        folds = grouped_kfold(SPEAKERS, k=5)
        held_out_all = [speaker for _, held_out in folds for speaker in held_out]
        assert sorted(held_out_all) == sorted(SPEAKERS)
        assert len(held_out_all) == len(SPEAKERS)

    def test_train_plus_held_out_covers_everyone_in_every_fold(self):
        folds = grouped_kfold(SPEAKERS, k=5)
        for train, held_out in folds:
            assert sorted(train) + sorted(held_out) != []
            assert set(train) | set(held_out) == set(SPEAKERS)

    def test_deterministic_for_the_same_seed(self):
        assert grouped_kfold(SPEAKERS, k=5, seed=99) == grouped_kfold(SPEAKERS, k=5, seed=99)

    def test_fold_sizes_are_as_equal_as_possible(self):
        folds = grouped_kfold(SPEAKERS, k=5)  # 46 speakers -> sizes 10,9,9,9,9
        sizes = sorted(len(held_out) for _, held_out in folds)
        assert sizes == [9, 9, 9, 9, 10]

    def test_rejects_fewer_speakers_than_folds(self):
        with pytest.raises(ValueError):
            grouped_kfold(SPEAKERS[:3], k=5)

    def test_rejects_k_below_two(self):
        with pytest.raises(ValueError):
            grouped_kfold(SPEAKERS, k=1)
