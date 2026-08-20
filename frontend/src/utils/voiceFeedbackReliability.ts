export type VoiceFeedbackReliabilityLevel =
  | "reliable"
  | "estimate"
  | "retry";

export interface VoiceFeedbackEvidence {
  feedbackQuality?: BackendFeedbackQuality | null;
  contentMatch?: boolean | null;
  contentJudged?: boolean;
  pitchContour?: Array<[number, number]>;
  wordProsody?: Array<{
    pitch_contour?: Array<[number, number]>;
    tone_accuracy?: number;
    judged?: boolean;
  }>;
  transcription?: string | null;
}

export interface BackendFeedbackQuality {
  status?: string;
  confidence?: number;
  can_score_pronunciation?: boolean;
  can_score_content?: boolean;
  reason_codes?: string[];
  /** Transitional backend name kept for compatibility during rollout. */
  reasons?: string[];
  metrics?: Record<string, number | string | boolean | null>;
}

export interface VoiceFeedbackReliability {
  level: VoiceFeedbackReliabilityLevel;
  canCountForProgress: boolean;
  reason: "content-mismatch" | "too-little-audio" | "unverified" | "checked";
}

const MIN_PITCH_POINTS = 2;

/**
 * A conservative, frontend-only interpretation of the evidence returned by
 * speech analysis. This deliberately does not manufacture a numeric
 * confidence score: the backend does not currently expose a calibrated one.
 */
export function assessVoiceFeedbackReliability(
  evidence: VoiceFeedbackEvidence,
): VoiceFeedbackReliability {
  const backendQuality = evidence.feedbackQuality;
  if (
    backendQuality?.can_score_pronunciation === false ||
    backendQuality?.status === "retry"
  ) {
    // Prefer the backend's own reason for the gate over the caller's
    // separately-computed contentMatch: a caller may score content more
    // leniently than the backend's independent verify_word check (see
    // PhrasePracticeDrill), so evidence.contentMatch can say "close enough"
    // while the backend's own gate still failed on content — showing
    // "too-little-audio" in that case names the wrong problem.
    const reasonCodes =
      backendQuality?.reason_codes ?? backendQuality?.reasons ?? [];
    const isContentMismatch =
      reasonCodes.includes("target_content_mismatch") ||
      reasonCodes.includes("target_content_unverified") ||
      evidence.contentMatch === false;
    return {
      level: "retry",
      canCountForProgress: false,
      reason: isContentMismatch ? "content-mismatch" : "too-little-audio",
    };
  }

  if (evidence.contentMatch === false) {
    return {
      level: "retry",
      canCountForProgress: false,
      reason: "content-mismatch",
    };
  }

  const words = evidence.wordProsody ?? [];
  const pitchPointCount =
    evidence.pitchContour?.length ??
    words.reduce(
      (total, word) => total + (word.pitch_contour?.length ?? 0),
      0,
    );
  const hasScoredWord = words.some(
    (word) =>
      word.judged !== false &&
      typeof word.tone_accuracy === "number" &&
      Number.isFinite(word.tone_accuracy),
  );

  if (pitchPointCount < MIN_PITCH_POINTS || !hasScoredWord) {
    return {
      level: "retry",
      canCountForProgress: false,
      reason: "too-little-audio",
    };
  }

  const independentlyChecked =
    evidence.contentMatch === true ||
    evidence.contentJudged === true ||
    backendQuality?.can_score_content === true;
  const backendNeedsReview =
    backendQuality?.status === "review" ||
    backendQuality?.status === "uncertain" ||
    backendQuality?.status === "limited";
  if (!independentlyChecked || backendNeedsReview) {
    return {
      level: "estimate",
      canCountForProgress: false,
      reason: "unverified",
    };
  }

  return {
    level: "reliable",
    canCountForProgress: true,
    reason: "checked",
  };
}
