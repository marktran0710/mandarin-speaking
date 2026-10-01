import type { Topic } from "@entities/topic";
import type { PronunciationFeatureSet, PronunciationFeedback } from "@shared/api/pronunciation";

export interface EvaluationScene {
  index: number;
  text: string;
}

/** Scenes that can be evaluated need both sides of the known-script comparison:
 * a target sentence and the teacher's recording of that sentence. */
export function evaluationScenes(topic: Topic | undefined): EvaluationScene[] {
  if (!topic) return [];
  return topic.images.flatMap((_, index) => {
    const text = topic.listenScripts?.[index]?.trim() || topic.suggestedAnswers?.[index]?.trim() || "";
    return topic.listenAudioUrls?.[index] && text ? [{ index, text }] : [];
  });
}

export interface ContourPoint {
  x: number;
  y: number;
}

function utteranceSpan(features: PronunciationFeatureSet | null | undefined): [number, number] | null {
  const syllables = features?.syllables ?? [];
  if (syllables.length === 0) return null;
  const start = syllables[0].start_ms;
  const end = syllables[syllables.length - 1].end_ms;
  return end > start ? [start, end] : null;
}

/** Pitch (semitones against the speaker's median) over the utterance, with time
 * scaled to 0..1 so a slower student lines up with a faster teacher. */
export function contourSeries(features: PronunciationFeatureSet | null | undefined): ContourPoint[] {
  const span = utteranceSpan(features);
  if (!features || !span) return [];
  const [start, end] = span;
  return features.syllables.flatMap((syllable) =>
    syllable.f0_points.map(([ms, semitones]) => ({ x: (ms - start) / (end - start), y: semitones })),
  );
}

export interface SyllableMark {
  x: number;
  label: string;
}

export function syllableBoundaries(features: PronunciationFeatureSet | null | undefined): SyllableMark[] {
  const span = utteranceSpan(features);
  if (!features || !span) return [];
  const [start, end] = span;
  return features.syllables.map((syllable) => ({
    x: (syllable.start_ms - start) / (end - start),
    label: syllable.expected.hanzi,
  }));
}

const FLAG_LABELS: Record<string, string> = {
  tone_contour_too_flat: "Pitch stayed flatter than the reference",
  tone_contour_not_level: "Pitch moved where the reference stays level",
  tone_direction_mismatch: "Pitch went a different direction",
  tone_range_too_narrow: "Right direction, not far enough",
  tone_shape_differs: "Same direction, different shape",
  syllable_too_short: "Syllable much shorter than expected",
  syllable_too_long: "Syllable much longer than expected",
};

export function flagLabel(code: string): string {
  return FLAG_LABELS[code] ?? code.replace(/_/g, " ");
}

const SHAPE_LABELS: Record<string, string> = {
  fall: "falling",
  rise: "rising",
  dip: "dipping",
  flat: "level",
  other: "uneven",
  unvoiced: "no pitch",
};

export function shapeLabel(direction: string): string {
  return SHAPE_LABELS[direction] ?? direction;
}

export function feedbackBadge(feedback: PronunciationFeedback): { label: string; tone: "llm" | "local" } {
  if (feedback.source === "llm") return { label: feedback.model ?? "model", tone: "llm" };
  return {
    label: feedback.fallback_reason ? `local feedback (${feedback.fallback_reason})` : "local feedback",
    tone: "local",
  };
}

const DIMENSION_LABELS: Record<string, string> = {
  tone: "Tone",
  segmental: "Pronunciation (sounds)",
  fluency: "Fluency",
  accuracy: "Accuracy",
  pronunciation: "Pronunciation (Wav2Vec2 + Praat tone)",
  prosody: "Prosody",
  intelligibility: "Intelligibility",
};

export function dimensionLabel(key: string): string {
  return DIMENSION_LABELS[key] ?? key;
}
