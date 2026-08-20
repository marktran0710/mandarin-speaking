/** Evidence returned by the shared speech analyzer for a model recording. */
export interface ReferenceAudioEvidence {
  pitchContour?: Array<unknown>;
  wordProsody?: Array<{
    pitch_contour?: Array<unknown>;
    tone_accuracy?: number;
    judged?: boolean;
    diagnostic_status?: string;
  }>;
  feedbackQuality?: {
    status?: string;
    can_score_pronunciation?: boolean;
    reason_codes?: string[];
  };
}

export type ReferenceAudioQuality = "usable" | "limited";

export interface ReferenceAudioAssessment {
  quality: ReferenceAudioQuality;
  reason:
    | "enough_pitch_evidence"
    | "insufficient_pitch_evidence"
    | "recording_quality_gate";
  message: string;
}

// Two voiced points are the minimum needed to see a direction. Real scene
// analysis normally returns many more; this lower bound keeps short, clear
// syllables from being rejected merely because they are brief.
const MIN_PITCH_POINTS = 2;

/**
 * A model recording is useful for imitation only when the analyzer can see
 * both a sentence-level pitch contour and at least one word-level contour.
 * This is deliberately separate from a student's score: a usable reference
 * is a teaching aid, never a promise that copying it earns 100/100.
 */
export function assessReferenceAudio(
  evidence: ReferenceAudioEvidence,
): ReferenceAudioAssessment {
  const quality = evidence.feedbackQuality;
  const reasons = quality?.reason_codes ?? [];
  const hasPitch = (evidence.pitchContour?.length ?? 0) >= MIN_PITCH_POINTS;
  const hasWordEvidence = (evidence.wordProsody ?? []).some(
    (word) =>
      word.judged !== false &&
      (word.pitch_contour?.length ?? 0) >= 2 &&
      (typeof word.tone_accuracy === "number" || !word.diagnostic_status),
  );

  if (
    quality?.can_score_pronunciation === false ||
    quality?.status === "retry" ||
    reasons.includes("recording_quality_unusable")
  ) {
    return {
      quality: "limited",
      reason: "recording_quality_gate",
      message:
        "This audio is clear enough to listen to, but not reliable enough to use as a pitch model.",
    };
  }

  if (!hasPitch || !hasWordEvidence) {
    return {
      quality: "limited",
      reason: "insufficient_pitch_evidence",
      message:
        "The system could not measure enough pitch movement in this audio. Do not treat it as a pronunciation benchmark.",
    };
  }

  return {
    quality: "usable",
    reason: "enough_pitch_evidence",
    message:
      "This audio has enough pitch evidence to practise its rhythm and tone movement.",
  };
}
