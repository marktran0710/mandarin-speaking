import type {
  PraatMetrics,
  WordProsody,
} from "../components/story-recorder/StoryRecorder";
import { isAdminSession } from "./studentSession";
import { getBackendUrl as getRuntimeBackendUrl, isTestRuntime } from "../config/runtimeEnv";

function localBackendUrl(): string {
  if (isTestRuntime()) return "http://127.0.0.1:8000";
  if (typeof window === "undefined") return "http://127.0.0.1:8000";

  // Keep development requests on the page's own origin so Vite can proxy
  // /api and /uploads to the backend. This preserves the httpOnly session
  // cookie and also works when the frontend is running inside Docker.
  return window.location.origin;
}

const CONFIGURED_BACKEND_URL = isTestRuntime() ? "" : getRuntimeBackendUrl().trim();

export function getBackendUrl(): string {
  if (CONFIGURED_BACKEND_URL) {
    return CONFIGURED_BACKEND_URL;
  }

  if (typeof window !== "undefined") {
    return localBackendUrl();
  }

  throw new Error(
    "Praat analysis needs a reachable backend. Configure the Next.js backend proxy or backend URL.",
  );
}

/** Maps a Mandarin tone number to the TONE_SHAPES key for its target pitch shape. */
export const TONE_NUMBER_TO_SHAPE: Record<number, string> = {
  1: "level",
  2: "rising",
  3: "dip",
  4: "falling",
};

export const TONE_SHAPES: Record<
  string,
  { label: string; arrow: string; tip: string; drill: string }
> = {
  level: {
    label: "平直 Level →",
    arrow: "→",
    tip: "全程保持平直。 Stays flat throughout.",
    drill:
      "再說一次，試著加入更多變化 — 上升或下降。 Say it again and try to add more movement — either rise or fall.",
  },
  rising: {
    label: "上升 Rising ↗",
    arrow: "↗",
    tip: "音高從頭到尾上升。 Pitch rises start to end.",
    drill:
      "上升形狀不錯。把開頭降低一點，結尾再推高一點。 Good upward shape. Make the start lower and push the end higher.",
  },
  falling: {
    label: "下降 Falling ↘",
    arrow: "↘",
    tip: "音高從頭到尾下降。 Pitch falls start to end.",
    drill:
      "下降形狀不錯。開頭要高，然後急速下降。 Good downward shape. Start high and let it drop sharply.",
  },
  dip: {
    label: "低降 Dip ↘↗",
    arrow: "↘↗",
    tip: "先下降再上升。 Dips down, then rises.",
    drill:
      "低降形狀不錯。最低點要更深一點再回升。 Good dip shape. Make the lowest point deeper before rising back.",
  },
  variable: {
    label: "不清楚 Unclear ??",
    arrow: "??",
    tip: "未偵測到清楚的形狀。 No clear shape was detected.",
    drill:
      "把這個字單獨拿出來，慢慢說 3 次，再放回句子。 Isolate this character, say it 3 times slowly, then put it back.",
  },
};

export function sceneReady(prog: {
  attempts: number;
  bestTone: number;
  bestFluency: number;
}): boolean {
  // Admin backdoor: every scene reads as passed (see isAdminSession).
  if (isAdminSession()) return true;
  // Short-phrase threshold: tone accuracy ≥ 70%
  // Long-sentence threshold: fluency ≥ 65%
  // Override: 4+ attempts always unlocks next scene
  return prog.bestTone >= 70 || prog.bestFluency >= 65 || prog.attempts >= 4;
}

/** Real, measured prosody score — the average per-character tone_accuracy from
 * word_prosody — as opposed to the AI's generic pronunciation_note.score, which
 * isn't grounded in the actual measured pitch data. */
/** Pronunciation feedback only matters once the sentence's meaning is
 * accepted. A null/unverified content_match (the independent ASR check
 * errored, timed out, or ran without a configured model) fails open rather
 * than blocking acceptance — a verification hiccup should never cost the
 * student their pronunciation feedback. */
export function isContentAccepted(praatMetrics: PraatMetrics): boolean {
  if (praatMetrics.content_match === false) return false;
  if (praatMetrics.content_match === true) return true;
  const contentAccuracy = praatMetrics.ai_feedback?.content_accuracy;
  if (!contentAccuracy?.feedback) return true;
  return contentAccuracy.accepted !== false;
}

/** A scene can only unlock when the learner's sentence has the right meaning
 * and includes every vocabulary item the evaluator expects. Pronunciation is
 * intentionally checked separately by the prosody gate. Same fail-open rule
 * as isContentAccepted for a null content_match. */
export function sceneContentGatePassed(praatMetrics: PraatMetrics): boolean {
  // Whole-sentence practice now has an independent ASR verdict. It is more
  // authoritative than the optional language-feedback vocabulary heuristic.
  if (praatMetrics.content_match === false) return false;
  if (praatMetrics.content_match === true) return true;
  if (!isContentAccepted(praatMetrics)) return false;
  return (praatMetrics.ai_feedback?.vocabulary_coverage?.missing?.length ?? 0) === 0;
}

export function averageWordProsodyAccuracy(
  wordProsody?: WordProsody[],
): number | null {
  const accuracies = (wordProsody ?? [])
    .map((item) => item.tone_accuracy)
    .filter((value): value is number => typeof value === "number");
  if (accuracies.length === 0) return null;
  return Math.round(
    accuracies.reduce((sum, value) => sum + value, 0) / accuracies.length,
  );
}

/** Chinese words in this recording that failed the backend's per-syllable
 * pass gate (min syllable score below the bar). Words the backend couldn't
 * judge (passed null/undefined — non-Chinese tokens, too-short segments)
 * never count as failed. */
export function failedProsodyWords(
  wordProsody?: WordProsody[],
): WordProsody[] {
  return (wordProsody ?? []).filter(isProsodyHardFailure);
}

/** One pronunciation verdict shared by progression, practice ordering and UI.
 *
 * After the tone-verdict refactor, this is a straight reading of the
 * canonical diagnostic status: only CORRECT clears the gate; UNCERTAIN and
 * INCORRECT both fail. The refactor's UNCERTAIN != CORRECT invariant lives
 * here — a word the backend was not confident enough to call CORRECT must
 * not silently unlock progression.
 *
 * `judged: false` (or an absent verdict) is preserved as "nothing to gate
 * on" — nothing to fail either, because the backend intentionally leaves
 * those words unscored rather than guessing. */
export function isProsodyHardFailure(item: WordProsody): boolean {
  if (item.diagnostic_status === "INVALID_AUDIO") {
    return true;
  }
  if (item.judged === false) return false;
  if (item.diagnostic_status === "INCORRECT") return true;
  if (item.diagnostic_status === "UNCERTAIN") return true;
  if (item.diagnostic_status === "CORRECT") return false;
  // No diagnostic status was produced (older payload, or a code path that
  // still relies on the legacy `passed`). Fall back to the raw pass flag
  // for backwards compatibility.
  return item.passed === false;
}

/** Fraction of judged syllables that must pass for a sentence to clear
 * the pronunciation gate. Mirrors backend main.SENTENCE_SYLLABLE_PASS_RATIO
 * so the fallback path (used when the backend didn't send a
 * pronunciation_mastery block) agrees with the authoritative gate.
 * Keep the two values in step — a drift here means the frontend fallback
 * unlocks scenes the backend would still block, or vice versa. */
export const SENTENCE_SYLLABLE_PASS_RATIO = 0.80;

/** The pronunciation mastery gate: a recording clears it when at least
 * SENTENCE_SYLLABLE_PASS_RATIO of its judged syllables passed (verdict
 * == CORRECT). Individual failed words still surface for optional
 * drilling — the gate lets a student move on with occasional
 * per-syllable slips, it does not hide them.
 *
 * An empty/absent word_prosody passes — the gate only ever blocks on
 * evidence, not on missing data. */
export function prosodyGatePassed(wordProsody?: WordProsody[]): boolean {
  const words = wordProsody ?? [];
  const judgedSyllables = words
    .flatMap((word) => word.syllables ?? [])
    .filter((syllable) => syllable.passed !== null && syllable.passed !== undefined);
  if (judgedSyllables.length === 0) {
    // No per-syllable evidence to count. Fall back to the old
    // any-hard-failure rule so payloads without a syllables[] array (or
    // with only unjudged syllables) still behave predictably.
    return !words.some(isProsodyHardFailure);
  }
  const passedCount = judgedSyllables.filter((syllable) => syllable.passed === true).length;
  return passedCount / judgedSyllables.length >= SENTENCE_SYLLABLE_PASS_RATIO;
}

/** Compact arrow for a tone number (target shapes shown next to what the
 * student actually did). */
export function toneArrow(tone: number): string {
  const arrows: Record<number, string> = {
    1: "→",
    2: "↗",
    3: "˅",
    4: "↘",
    5: "·",
  };
  return arrows[tone] ?? "?";
}

/** Compact arrow for a measured contour_shape classification. */
export function shapeArrow(shape: string): string {
  const arrows: Record<string, string> = {
    level: "→",
    rising: "↗",
    falling: "↘",
    dip: "˅",
    variable: "~",
  };
  return arrows[shape] ?? "~";
}

export function formatBackendError(error: unknown, backendUrl: string): string {
  const message = error instanceof Error ? error.message : String(error);
  const networkFailures = [
    "Failed to fetch",
    "NetworkError",
    "Load failed",
    "The operation was aborted",
  ];

  if (networkFailures.some((failure) => message.includes(failure))) {
    return `無法連線到語音分析後端 ${backendUrl}。請先啟動 FastAPI 後端（連接埠 8000），再重新錄音。 Cannot reach the speech analysis backend at ${backendUrl}. Start the FastAPI backend on port 8000, then record again.`;
  }

  return message || "語音分析發生錯誤 Speech analysis error occurred";
}
