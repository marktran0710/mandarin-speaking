import { scriptMatchRatio } from "./scriptAlignment";

/** Display-only shape of a teacher's model recording, as stored on a story
 * frame (`sentenceModelContour`). Each scored token keeps its points as
 * `[relativeTime, semitones]`: time 0..1 within that token's own span, pitch
 * in semitones relative to the model speaker's median. Never used for
 * scoring. */
export interface SentenceModelContour {
  text: string;
  tokens: Array<{ token: string; points: Array<[number, number]> }>;
}

/** One model-voice line segment per student word, already in the student's
 * own time axis and Hz. `wordIndex` is the `WordProsody.index` it sits on. */
export interface ModelOverlaySegment {
  wordIndex: number;
  points: Array<[number, number]>;
}

export type ModelOverlay =
  | { status: "ok"; segments: ModelOverlaySegment[] }
  /** No teacher recording (or one recorded for a different script). */
  | { status: "missing" }
  /** The learner said something else, so there is nothing to line up. */
  | { status: "mismatch" };

interface OverlayWord {
  token: string;
  index: number;
  start_time: number;
  end_time: number;
}

/** Below this share of the script heard in the transcript, the recording is
 * treated as a different sentence and the model line is hidden rather than
 * stretched over audio it does not describe. Display-only — it does not
 * affect any grade. */
export const MODEL_OVERLAY_MIN_SCRIPT_MATCH = 0.8;

const HANZI = /[一-鿿]/u;

function compactText(text: string): string {
  return Array.from(text.normalize("NFKC")).filter((char) => /[\p{L}\p{N}]/u.test(char)).join("");
}

function median(values: number[]): number {
  const sorted = [...values].sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
}

/** Parses the stored JSON, dropping anything malformed. */
export function parseSentenceModelContour(raw: unknown): SentenceModelContour | null {
  let value = raw;
  if (typeof value === "string") {
    if (!value.trim()) return null;
    try {
      value = JSON.parse(value);
    } catch {
      return null;
    }
  }
  if (!value || typeof value !== "object") return null;
  const { text, tokens } = value as { text?: unknown; tokens?: unknown };
  if (typeof text !== "string" || !Array.isArray(tokens)) return null;
  const safeTokens = tokens.flatMap((entry) => {
    if (!entry || typeof entry !== "object") return [];
    const { token, points } = entry as { token?: unknown; points?: unknown };
    if (typeof token !== "string" || !Array.isArray(points)) return [];
    const safePoints = points.filter(
      (point): point is [number, number] =>
        Array.isArray(point) && point.length === 2 && point.every((n) => typeof n === "number" && Number.isFinite(n)),
    );
    return [{ token, points: safePoints }];
  });
  return safeTokens.length ? { text, tokens: safeTokens } : null;
}

/**
 * Lines the teacher's model-voice shape up with the student's recording.
 *
 * Each model token is stretched onto the time span of the same token in the
 * student's attempt, so speaking faster or slower never makes the shapes
 * drift apart. Pitch keeps the model's semitone movement but is anchored at
 * the student's own median pitch: a low voice and a high voice see the same
 * rises and falls in their own range, never the teacher's absolute pitch.
 */
export function buildModelOverlay({
  contour,
  targetScript,
  transcript,
  words,
  pitchContour,
}: {
  contour: SentenceModelContour | null | undefined;
  targetScript: string;
  transcript?: string;
  words: OverlayWord[];
  pitchContour: Array<[number, number]>;
}): ModelOverlay {
  if (!contour || contour.tokens.length === 0) return { status: "missing" };
  if (compactText(contour.text) !== compactText(targetScript)) return { status: "missing" };

  if (transcript?.trim() && scriptMatchRatio(targetScript, transcript) < MODEL_OVERLAY_MIN_SCRIPT_MATCH) {
    return { status: "mismatch" };
  }

  // Both sides are tokenized from the same script by the same backend
  // tokenizer, so a different token list means the attempt was scored
  // against other text (e.g. the raw transcript) — nothing to line up.
  const studentWords = words.filter((word) => HANZI.test(word.token));
  const modelTokens = contour.tokens.filter((entry) => HANZI.test(entry.token));
  if (
    studentWords.length !== modelTokens.length
    || studentWords.some((word, index) => word.token !== modelTokens[index].token)
  ) {
    return { status: "mismatch" };
  }

  const voiced = pitchContour.map(([, hz]) => hz).filter((hz) => hz > 0);
  if (voiced.length === 0) return { status: "mismatch" };
  const anchorHz = median(voiced);

  const segments = studentWords.flatMap((word, index) => {
    const span = word.end_time - word.start_time;
    const points = modelTokens[index].points;
    if (span <= 0 || points.length < 2) return [];
    return [{
      wordIndex: word.index,
      points: points.map(([relative, semitones]): [number, number] => [
        word.start_time + relative * span,
        anchorHz * 2 ** (semitones / 12),
      ]),
    }];
  });
  return segments.length ? { status: "ok", segments } : { status: "missing" };
}
