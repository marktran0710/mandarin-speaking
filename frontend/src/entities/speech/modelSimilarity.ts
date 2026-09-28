import { buildModelOverlay, type ModelOverlay } from "./modelOverlay";

export interface ModelSimilarity {
  /** Mean of the per-word Pearson correlations between the student's and
   * the model's pitch shape (semitones, same relative moments in each word). */
  r: number;
  /** `max(0, r) × 100`, rounded — what the student sees. */
  score: number;
  wordsCompared: number;
  wordsTotal: number;
}

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
 * expressive voice legitimately moves more than this across a sentence. */
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

/**
 * How closely the student's pitch follows the model voice's shape: Pearson r
 * inside each word (so only each word's rises and falls count — not voice
 * pitch, and not how high one word sits relative to the next), averaged over
 * the words. Display-only practice feedback: an engineering choice, not
 * validated against teacher ratings, and never used for pass/unlock.
 *
 * Checked 2026-09-28: the model recording scored against itself through the
 * real analysis pipeline gives 98-100%. On 148 real student words, matched
 * word pairs averaged r = 0.59 vs 0.36 for randomly paired words (without the
 * window shift: 0.04 vs -0.09), so the score does separate "followed the
 * model" from "didn't" — but unrelated shapes still land around 36%, which is
 * the practical floor. Rejected alternatives: a sentence-wide r (dominated by
 * sentence intonation, negative even when most words matched) and DTW (warps
 * any shape into a match: random pairs averaged 0.49).
 *
 * Returns null when there is no lined-up model voice or when fewer than half
 * of the words could be compared.
 */
export function modelSimilarity(
  overlay: ModelOverlay,
  pitchContour: Array<[number, number]>,
): ModelSimilarity | null {
  if (overlay.status !== "ok" || overlay.segments.length === 0) return null;
  const voicedPoints = pitchContour.filter(([, hz]) => hz > 0);
  if (voicedPoints.length < 2) return null;
  const folded = foldOctaves(voicedPoints.map(([, hz]) => semitones(hz)));
  const voiced = voicedPoints.map(([t], i): [number, number] => [t, folded[i]]);

  const correlations: number[] = [];
  let flatWords = 0;
  for (const segment of overlay.segments) {
    const model = segment.points.map(([t, hz]): [number, number] => [t, semitones(hz)]);
    const start = model[0][0];
    const end = model[model.length - 1][0];
    if (end <= start) continue;
    // Word boundaries on the student's audio come from an automatic aligner
    // and can be off by tens of milliseconds, which wrecks r for short
    // words. Try small shifts of the student window and keep the best.
    let best: number | null = null;
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
      const r = pearson(studentValues, modelValues);
      if (best === null || r > best) best = r;
    }
    if (isFlat) flatWords += 1;
    else if (best !== null) correlations.push(best);
  }

  const wordsTotal = overlay.segments.length;
  const wordsCompared = correlations.length;
  // Flat model words were measured, just not scorable by shape.
  if (wordsCompared === 0 || (wordsCompared + flatWords) * 2 < wordsTotal) return null;
  const r = correlations.reduce((sum, value) => sum + value, 0) / wordsCompared;
  return { r, score: Math.round(Math.max(0, r) * 100), wordsCompared, wordsTotal };
}

/** Line up the model voice for one attempt and score it — the same inputs
 * the result chart uses, so the saved score always matches what was drawn. */
export function attemptModelSimilarity(
  input: Parameters<typeof buildModelOverlay>[0],
): ModelSimilarity | null {
  return modelSimilarity(buildModelOverlay(input), input.pitchContour);
}
