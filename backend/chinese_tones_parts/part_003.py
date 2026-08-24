

def generate_comprehensive_feedback(
    detected_tone: int,
    tone_accuracy: float,
    speech_rate: float,
    fluency: float,
    pitch_contour: List[Tuple[float, float]],
    word_prosody: List[Dict] | None = None,
) -> str:
    tone_feedback = (
        generate_phrase_tone_feedback(word_prosody, tone_accuracy)
        if word_prosody
        else get_tone_feedback(detected_tone, tone_accuracy, pitch_contour)
    )
    feedback_parts = [tone_feedback]

    if speech_rate > 0:
        if 3.5 <= speech_rate <= 5.5:
            feedback_parts.append(f"Speech rate is comfortable at {speech_rate:.1f} syllables/sec.")
        elif speech_rate < 3.5:
            feedback_parts.append(f"Try a little faster; current rate is {speech_rate:.1f} syllables/sec.")
        else:
            feedback_parts.append(f"Slow down slightly; current rate is {speech_rate:.1f} syllables/sec.")

    if fluency > 80:
        feedback_parts.append("Fluency is smooth.")
    elif fluency > 60:
        feedback_parts.append("Work on smoother pitch transitions.")
    else:
        feedback_parts.append("Try one shorter phrase and keep the tone movement clear.")

    return " ".join(feedback_parts)
