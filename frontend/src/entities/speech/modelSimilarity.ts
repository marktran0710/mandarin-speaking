import { buildModelOverlay, type ModelOverlay } from "./modelOverlay";
import { foldOctaveBlocks } from "./pitchCleaning";

export interface ModelSimilarity {
  /** Mean of the per-word Pearson correlations between the student's and
   * the model's pitch shape (semitones, same relative moments in each word). */
  r: number;
  /** What the student sees, 0-100. */
  score: number;
  wordsCompared: number;
  wordsTotal: number;
  /** v2 only: mean shape factor (0-1) and mean range factor (0-1) behind `score`. */
  shape?: number;
  range?: number;
}

/**
 * `v2` (default): shape AND size must follow the model - Pearson r says how
 * closely the rises and falls line up, the range factor says whether the
 * student moved their pitch by a comparable amount. `legacy`: the original
 * shape-only score (mean Pearson r, floored at 0), kept for comparison and as
 * an instant rollback.
 */
export type SimilarityAlgorithm = "v2" | "legacy";

export interface SimilarityParams {
  /** Word shape below this r earns no shape credit. Unrelated words already
   * correlate this well after the window-shift search (see `modelSimilarity`). */
  rFloor: number;
  /** Word shape at or above this r earns full shape credit. */
  rFull: number;
  /** Student pitch range (relative to the model's) at or below this earns no range credit. */
  rhoZero: number;
  /** ... and at or above this earns full range credit. Wider than the model is never penalised. */
  rhoFull: number;
  /** Model ranges below this count as this wide, so a nearly level model word
   * does not turn ordinary jitter into a large range ratio. */
  minReferenceSpan: number;
}

/** ENGINEERING DEFAULTS, not validated against teacher ratings. Shape: r 0.4 (about
 * what unrelated words score after the window-shift search) to 0.85 (a natural
 * re-recording). Size: using 60% of the model's pitch range earns full range
 * credit - generous on purpose, since learners speak narrower than a teacher and
 * the teacher curves themselves run wide - and under 20% earns none. Checked on
 * synthetic re-recordings/degradations of 82 real teacher sentences, see
 * docs/model-similarity-evaluation.md. Named so a later calibration can move them. */
export const DEFAULT_SIMILARITY_PARAMS: SimilarityParams = {
  rFloor: 0.4,
  rFull: 0.85,
  rhoZero: 0.2,
  rhoFull: 0.6,
  minReferenceSpan: 3,
};

/** Samples taken inside each word's span. */
const SAMPLES_PER_WORD = 20;
/** A student sample counts only when voiced pitch exists this close to it on
 * both sides; otherwise the moment is unvoiced and skipped. */
const MAX_VOICED_GAP_SECONDS = 0.05;
/** A model word whose pitch moves less than this is a flat (tone-1-like)
 * target: Pearson r has no shape to compare there, so the word is skipped. */
const FLAT_MODEL_RANGE_SEMITONES = 1;
/** Pitch trackers sometimes report half or double the real pitch for a few
 * frames. A sample this far from its *local* median (neighbouring frames) is
 * such a jump and is folded back by an octave. Local, not sentence-wide: an
 * expressive voice legitimately moves more than this across a sentence.
 * (legacy algorithm only; v2 uses `foldOctaveBlocks`.) */
const OCTAVE_FOLD_SEMITONES = 8;
const OCTAVE_WINDOW = 5;
/** Student-window shifts tried per word, as a fraction of the word's span. */
const WINDOW_SHIFTS = [-0.15, -0.1, -0.05, 0, 0.05, 0.1, 0.15];

function semitones(hz: number): number {
  return 12 * Math.log2(hz / 100);
}

function foldOctaves(values: number[]): number[] {
  return values.map((value, index) => {
    const window = values
      .slice(Math.max(0, index - OCTAVE_WINDOW), index + OCTAVE_WINDOW + 1)
      .sort((a, b) => a - b);
    const localMedian = window[Math.floor(window.length / 2)];
    let folded = value;
    while (folded - localMedian > OCTAVE_FOLD_SEMITONES) folded -= 12;
    while (localMedian - folded > OCTAVE_FOLD_SEMITONES) folded += 12;
    return folded;
  });
}

function interpolate(points: Array<[number, number]>, time: number, maxGap = Infinity): number | null {
  for (let i = 1; i < points.length; i += 1) {
    const [t0, v0] = points[i - 1];
    const [t1, v1] = points[i];
    if (time >= t0 && time <= t1) {
      if (t1 - t0 > maxGap) return null;
      return t1 === t0 ? v0 : v0 + ((time - t0) / (t1 - t0)) * (v1 - v0);
    }
  }
  return null;
}

function pearson(xs: number[], ys: number[]): number {
  const n = xs.length;
  const meanX = xs.reduce((sum, x) => sum + x, 0) / n;
  const meanY = ys.reduce((sum, y) => sum + y, 0) / n;
  let cov = 0;
  let varX = 0;
  let varY = 0;
  for (let i = 0; i < n; i += 1) {
    const dx = xs[i] - meanX;
    const dy = ys[i] - meanY;
    cov += dx * dy;
    varX += dx * dx;
    varY += dy * dy;
  }
  // A flat attempt has no shape to correlate: treat it as no similarity.
  if (varX < 1e-9 || varY < 1e-9) return 0;
  return cov / Math.sqrt(varX * varY);
}

const clamp01 = (value: number) => Math.min(1, Math.max(0, value));

/** 10th-90th percentile spread: a pitch range that one stray sample cannot inflate. */
function robustSpan(values: number[]): number {
  const sorted = [...values].sort((a, b) => a - b);
  const at = (p: number) => {
    const position = p * (sorted.length - 1);
    const low = Math.floor(position);
    const high = Math.ceil(position);
    return sorted[low] + (sorted[high] - sorted[low]) * (position - low);
  };
  return at(0.9) - at(0.1);
}

function wordFactors(
  studentValues: number[],
  modelValues: number[],
  params: SimilarityParams,
): { r: number; shape: number; range: number; score: number } {
  const r = pearson(studentValues, modelValues);
  const shape = clamp01((r - params.rFloor) / (params.rFull - params.rFloor));
  const reference = Math.max(robustSpan(modelValues), params.minReferenceSpan);
  const ratio = robustSpan(studentValues) / reference;
  const range = clamp01((ratio - params.rhoZero) / (params.rhoFull - params.rhoZero));
  return { r, shape, range, score: shape * range };
}

/**
 * How closely the student's pitch follows the model voice, per word, averaged
 * over the words. Display-only practice feedback: an engineering choice, not
 * validated against teacher ratings, and never used for pass/unlock.
 *
 * Shape (both algorithms): Pearson r inside each word, so only each word's
 * rises and falls count - not voice pitch, and not how high one word sits
 * relative to the next. Word boundaries on the student's audio come from an
 * automatic aligner and can be off by tens of milliseconds, so small shifts of
 * the student window are tried and the best is kept. Checked 2026-09-28: the
 * model recording scored against itself gives 98-100%; matched word pairs
 * averaged r = 0.59 vs 0.36 for randomly paired words. Rejected alternatives:
 * a sentence-wide r (dominated by sentence intonation) and DTW (warps any
 * shape into a match: random pairs averaged 0.49).
 *
 * Size (v2 only): Pearson r discards how far the pitch moved, so a nearly flat
 * attempt with a tiny wobble in the right direction matched as well as a full
 * fall. v2 multiplies the shape factor by a range factor (one-sided: moving
 * more than the model is never penalised) and folds octave tracker errors out
 * of both the student and the model curve with `foldOctaveBlocks`.
 *
 * Returns null when there is no lined-up model voice or when fewer than half
 * of the words could be compared.
 */
export function modelSimilarity(
  overlay: ModelOverlay,
  pitchContour: Array<[number, number]>,
  options: { algorithm?: SimilarityAlgorithm; params?: Partial<SimilarityParams> } = {},
): ModelSimilarity | null {
  const algorithm = options.algorithm ?? "v2";
  const params = { ...DEFAULT_SIMILARITY_PARAMS, ...options.params };
  if (overlay.status !== "ok" || overlay.segments.length === 0) return null;
  const voicedPoints = pitchContour.filter(([, hz]) => hz > 0);
  if (voicedPoints.length < 2) return null;
  const fold = algorithm === "v2" ? foldOctaveBlocks : foldOctaves;
  const folded = fold(voicedPoints.map(([, hz]) => semitones(hz)));
  const voiced = voicedPoints.map(([t], i): [number, number] => [t, folded[i]]);

  const words: Array<{ r: number; shape: number; range: number; score: number }> = [];
  let flatWords = 0;
  for (const segment of overlay.segments) {
    const modelSt = fold(segment.points.map(([, hz]) => semitones(hz)));
    const model = segment.points.map(([t], i): [number, number] => [t, modelSt[i]]);
    const start = model[0][0];
    const end = model[model.length - 1][0];
    if (end <= start) continue;
    let best: { r: number; shape: number; range: number; score: number } | null = null;
    let isFlat = false;
    for (const shift of WINDOW_SHIFTS) {
      const studentValues: number[] = [];
      const modelValues: number[] = [];
      for (let i = 0; i < SAMPLES_PER_WORD; i += 1) {
        const time = start + ((i + 0.5) / SAMPLES_PER_WORD) * (end - start);
        const student = interpolate(voiced, time + shift * (end - start), MAX_VOICED_GAP_SECONDS * 2);
        // Model points are already downsampled, so their spacing is not a
        // voicing signal.
        const reference = interpolate(model, time);
        if (student !== null && reference !== null) {
          studentValues.push(student);
          modelValues.push(reference);
        }
      }
      if (studentValues.length < SAMPLES_PER_WORD / 2) continue;
      if (Math.max(...modelValues) - Math.min(...modelValues) < FLAT_MODEL_RANGE_SEMITONES) {
        isFlat = true;
        break;
      }
      const factors = wordFactors(studentValues, modelValues, params);
      const better = best === null
        || (algorithm === "v2" ? factors.score > best.score : factors.r > best.r);
      if (better) best = factors;
    }
    if (isFlat) flatWords += 1;
    else if (best !== null) words.push(best);
  }

  const wordsTotal = overlay.segments.length;
  const wordsCompared = words.length;
  // Flat model words were measured, just not scorable by shape.
  if (wordsCompared === 0 || (wordsCompared + flatWords) * 2 < wordsTotal) return null;
  const mean = (pick: (word: (typeof words)[number]) => number) =>
    words.reduce((sum, word) => sum + pick(word), 0) / wordsCompared;
  const r = mean((word) => word.r);
  if (algorithm === "legacy") {
    return { r, score: Math.round(Math.max(0, r) * 100), wordsCompared, wordsTotal };
  }
  return {
    r,
    score: Math.round(mean((word) => word.score) * 100),
    wordsCompared,
    wordsTotal,
    shape: mean((word) => word.shape),
    range: mean((word) => word.range),
  };
}

/** Line up the model voice for one attempt and score it — the same inputs
 * the result chart uses, so the saved score always matches what was drawn. */
export function attemptModelSimilarity(
  input: Parameters<typeof buildModelOverlay>[0],
): ModelSimilarity | null {
  return modelSimilarity(buildModelOverlay(input), input.pitchContour);
}
