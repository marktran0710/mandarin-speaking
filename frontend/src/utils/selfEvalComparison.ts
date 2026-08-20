import type { PraatMetrics } from "../components/StoryRecorder";
import { isContentAccepted } from "./storyRecorderFeedback";

export type SelfEvalLevel = "good" | "ok" | "bad";

export const SELF_EVAL_LEVELS: SelfEvalLevel[] = ["good", "ok", "bad"];

export const SELF_EVAL_EMOJI: Record<SelfEvalLevel, string> = {
  good: "😊",
  ok: "😐",
  bad: "😟",
};

/** Maps the system's meaning verdict onto the same 3-level scale the student
 * picks from for the "意思" question, so the two sit side by side without
 * extra translation. Mirrors the "meaning"/"vocab"/accepted branches of
 * SpeakingResultsFlow's own verdict logic. */
export function systemContentLevel(
  praatMetrics: PraatMetrics,
  hasScriptMismatch: boolean,
): SelfEvalLevel {
  if (!isContentAccepted(praatMetrics) || hasScriptMismatch) return "bad";
  const missing = praatMetrics.ai_feedback?.vocabulary_coverage?.missing ?? [];
  if (missing.length > 0) return "ok";
  return "good";
}

/** Maps the system's measured tone accuracy onto the same 3-level scale for
 * the "發音" question. Self-eval only ever fires on a ready attempt, so this
 * can still land on "ok"/"bad" when the scene unlocked via the attempts
 * override (see sceneReady) rather than a clean pass. */
export function systemPronunciationLevel(
  praatMetrics: PraatMetrics,
): SelfEvalLevel {
  const score = praatMetrics.tone_accuracy ?? 0;
  if (score >= 80) return "good";
  if (score >= 55) return "ok";
  return "bad";
}

export function selfEvalLevelsMatch(
  self: SelfEvalLevel,
  system: SelfEvalLevel,
): boolean {
  return self === system;
}
