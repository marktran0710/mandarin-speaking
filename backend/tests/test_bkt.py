from analytics.bkt import BKT_CONFIG, mastery_status, replay_bkt, update_bkt


def test_correct_response_increases_mastery():
    assert update_bkt(0.4, True) > 0.4


def test_incorrect_response_reduces_mastery():
    assert update_bkt(0.4, False) < 0.4


def test_probability_is_clamped_to_safe_range():
    for correct in (True, False):
        value = update_bkt(0.0, correct)
        assert 0.000001 <= value <= 0.999999
        value = update_bkt(1.0, correct)
        assert 0.000001 <= value <= 0.999999


def test_replay_is_deterministic_and_order_sensitive():
    first = replay_bkt([False, True, True])
    second = replay_bkt([False, True, True])
    reordered = replay_bkt([True, True, False])
    assert first == second
    assert first != reordered


def test_default_configuration_is_centralized_and_temporary():
    assert BKT_CONFIG.initial_mastery == 0.2
    assert BKT_CONFIG.mastery_threshold == 0.95


def test_sparse_evidence_stays_unassessed():
    assert mastery_status(0, BKT_CONFIG.initial_mastery) == "UNASSESSED"
    assert mastery_status(BKT_CONFIG.minimum_observations - 1, 0.99) == "UNASSESSED"
