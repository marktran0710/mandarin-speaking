

class TestPhraseTargetCurveOverride:
    """calculate_phrase_tone_accuracy / calculate_phrase_shape_accuracy /
    phrase_shape_curves should compare against a real model-voice curve when
    one is supplied, instead of the synthetic idealized tone-shape pattern."""

    def test_override_curve_changes_the_shape_score(self):
        contour = _synthetic_contour([0.9, 0.75, 0.6, 0.4, 0.2])  # falling, tone 4
        # A tone-4-shaped reference should score higher than a deliberately
        # mismatched flat reference for the same recorded contour.
        matching_override = list(np.linspace(1.0, 0.0, 100))
        mismatched_override = [0.5] * 100

        matching_score = calculate_phrase_shape_accuracy(contour, [4], matching_override)
        mismatched_score = calculate_phrase_shape_accuracy(contour, [4], mismatched_override)
        assert matching_score > mismatched_score

    def test_phrase_shape_curves_returns_the_override_as_target(self):
        contour = _synthetic_contour([0.2, 0.5, 0.8])  # rising, tone 2
        override = list(np.linspace(0.1, 0.9, 100))
        _, target_curve = phrase_shape_curves(contour, [2], override)
        assert target_curve == pytest.approx(override, abs=1e-9)

    def test_tone_accuracy_blend_uses_override_for_shape_half(self):
        contour = _synthetic_contour([0.9, 0.75, 0.6, 0.4, 0.2])  # falling, tone 4
        without_override = calculate_phrase_tone_accuracy(contour, [4])
        with_matching_override = calculate_phrase_tone_accuracy(
            contour, [4], list(np.linspace(1.0, 0.0, 100))
        )
        with_mismatched_override = calculate_phrase_tone_accuracy(
            contour, [4], [0.5] * 100
        )
        assert with_matching_override > with_mismatched_override
        # Sanity: overriding with a curve that matches the synthetic tone-4
        # pattern about as well should land in the same ballpark.
        assert abs(with_matching_override - without_override) < 20
