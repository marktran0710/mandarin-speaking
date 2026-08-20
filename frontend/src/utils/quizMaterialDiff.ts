/** Teacher quiz review: diffs a story's live quiz material against the
 * snapshot captured at the last "Save marks" (custom_stories
 * .quiz_material_snapshot), so the review page can flag which words/pools
 * are new, changed, or already reviewed and untouched (kept). Matching is
 * by content, not array index — a cloze/synonym pool that's merely been
 * reordered by regeneration should not read as "changed".
 *
 * Snapshots are stored keyed by difficulty tier (easy/medium/hard word text
 * and pools can differ per tier — see storyToTopic), so reviewing one tier
 * never clobbers another tier's baseline. */
import type { StoryDifficultyLevel } from "./teacherStories";

export interface MaterialSnapshotEntry {
  word: string;
  translation?: string;
  distractors: string[];
  cloze: Array<{ sentence: string; distractors: string[] }>;
  synonym: Array<{ synonym: string; distractors: string[] }>;
}

export type MaterialSnapshot = MaterialSnapshotEntry[];

/** The raw shape persisted in custom_stories.quiz_material_snapshot. */
export type StoredMaterialSnapshot = Partial<
  Record<StoryDifficultyLevel, MaterialSnapshot>
>;

/** Just the story/topic fields a snapshot is built from — mirrors
 * topicQuiz.ts's QuizSourceTopic, kept separate so this module doesn't
 * couple to StoryVocabQuiz. */
export interface QuizMaterialTopic {
  images: unknown[];
  vocabulary: Record<number, string[]>;
  vocabularyTranslation?: Record<number, string[]>;
  vocabularyDistractors?: Record<number, string[][]>;
  vocabularyCloze?: Record<number, Array<{ sentence: string; distractors: string[] }[]>>;
  vocabularySynonym?: Record<number, Array<{ synonym: string; distractors: string[] }[]>>;
}

/** The raw stored snapshot map off a story, or {} when the story has never
 * been saved under this feature. Typed as an accessor rather than widening
 * CustomTeacherStory, same convention as quizExclusions.ts's
 * storyQuizExclusions. */
export function storyMaterialSnapshotMap(story: {
  quizMaterialSnapshot?: unknown;
}): StoredMaterialSnapshot {
  const raw = story.quizMaterialSnapshot;
  return raw && typeof raw === "object" && !Array.isArray(raw)
    ? (raw as StoredMaterialSnapshot)
    : {};
}

/** The story's diff baseline for one tier, or null when that tier has never
 * been saved (the caller should render no badges in that case). */
export function storyMaterialSnapshot(
  story: { quizMaterialSnapshot?: unknown },
  level: StoryDifficultyLevel,
): MaterialSnapshot | null {
  return storyMaterialSnapshotMap(story)[level] ?? null;
}

/** Builds the full map to PUT after saving `level`'s marks: the story's
 * other tiers' baselines carried over untouched, this tier's replaced with
 * the material on screen right now. */
export function withUpdatedSnapshot(
  story: { quizMaterialSnapshot?: unknown },
  level: StoryDifficultyLevel,
  entries: MaterialSnapshot,
): StoredMaterialSnapshot {
  return { ...storyMaterialSnapshotMap(story), [level]: entries };
}

/** Flattens a topic's per-scene vocabulary into the snapshot shape. Words
 * are keyed by their text alone (not scene index), since scenes can be
 * added/removed/reordered between saves — a word that moves scenes should
 * still diff against its prior material. */
export function buildMaterialSnapshot(topic: QuizMaterialTopic): MaterialSnapshot {
  const entries: MaterialSnapshotEntry[] = [];
  topic.images.forEach((_, si) => {
    (topic.vocabulary[si] || []).forEach((word, wi) => {
      entries.push({
        word,
        translation: topic.vocabularyTranslation?.[si]?.[wi],
        distractors: topic.vocabularyDistractors?.[si]?.[wi] ?? [],
        cloze: topic.vocabularyCloze?.[si]?.[wi] ?? [],
        synonym: topic.vocabularySynonym?.[si]?.[wi] ?? [],
      });
    });
  });
  return entries;
}

export type MaterialDiffStatus = "new" | "changed" | "kept";

export interface WordDiff {
  status: MaterialDiffStatus;
  distractorsStatus: MaterialDiffStatus;
  /** Aligned with the current word's cloze array, in its current order. */
  clozeStatus: MaterialDiffStatus[];
  /** Aligned with the current word's synonym array, in its current order. */
  synonymStatus: MaterialDiffStatus[];
}

function sameSet(a: string[], b: string[]): boolean {
  if (a.length !== b.length) return false;
  const sortedA = [...a].sort();
  const sortedB = [...b].sort();
  return sortedA.every((v, i) => v === sortedB[i]);
}

/** Diffs one word's live material against the snapshot. Returns null when
 * there's no snapshot at all (story never saved under this feature) — the
 * caller should render no badges in that case, rather than flagging
 * everything as new. */
export function diffWord(
  word: string,
  current: {
    distractors: string[];
    cloze: Array<{ sentence: string; distractors: string[] }>;
    synonym: Array<{ synonym: string; distractors: string[] }>;
  },
  snapshot: MaterialSnapshot | null,
): WordDiff | null {
  if (!snapshot) return null;

  const prior = snapshot.find((e) => e.word === word);
  if (!prior) {
    return {
      status: "new",
      distractorsStatus: "new",
      clozeStatus: current.cloze.map(() => "new"),
      synonymStatus: current.synonym.map(() => "new"),
    };
  }

  const distractorsStatus: MaterialDiffStatus = sameSet(current.distractors, prior.distractors)
    ? "kept"
    : "changed";

  const clozeStatus = current.cloze.map((c): MaterialDiffStatus => {
    const match = prior.cloze.find((p) => p.sentence === c.sentence);
    if (!match) return "new";
    return sameSet(c.distractors, match.distractors) ? "kept" : "changed";
  });

  const synonymStatus = current.synonym.map((s): MaterialDiffStatus => {
    const match = prior.synonym.find((p) => p.synonym === s.synonym);
    if (!match) return "new";
    return sameSet(s.distractors, match.distractors) ? "kept" : "changed";
  });

  const anyChanged =
    distractorsStatus !== "kept" ||
    clozeStatus.some((s) => s !== "kept") ||
    synonymStatus.some((s) => s !== "kept");

  return {
    status: anyChanged ? "changed" : "kept",
    distractorsStatus,
    clozeStatus,
    synonymStatus,
  };
}
