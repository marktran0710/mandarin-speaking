import type { CustomTeacherStory } from "./teacherStories";

/** Teacher-marked bad quiz material (see TeacherQuizReviewPage): a whole
 * word, one candidate of a per-word AI pool (cloze/synonym with index), or
 * a word's whole lookalike/distractor pool. Stored per story on the
 * backend (custom_stories.quiz_exclusions) and applied when the quiz
 * builds its entry pool, so excluded material never becomes a question. */
export type QuizExclusionKind =
  | "word"
  | "cloze"
  | "synonym"
  | "lookalike"
  | "distractors";

export interface QuizExclusion {
  word: string;
  kind: QuizExclusionKind;
  /** Pool position for cloze/synonym; omitted = the whole pool. */
  index?: number;
}

/** The story's exclusion list. Typed as an accessor (rather than widening
 * CustomTeacherStory) so this feature stays additive while the story type
 * is in flight elsewhere. */
export function storyQuizExclusions(
  story: CustomTeacherStory,
): QuizExclusion[] {
  const raw = (story as { quizExclusions?: unknown }).quizExclusions;
  return Array.isArray(raw) ? (raw as QuizExclusion[]) : [];
}

export function isExcluded(
  exclusions: QuizExclusion[],
  word: string,
  kind: QuizExclusionKind,
  index?: number,
): boolean {
  return exclusions.some(
    (e) =>
      e.word === word &&
      e.kind === kind &&
      (e.index === undefined || e.index === index),
  );
}

export function toggleExclusion(
  exclusions: QuizExclusion[],
  next: QuizExclusion,
): QuizExclusion[] {
  const matches = (e: QuizExclusion) =>
    e.word === next.word && e.kind === next.kind && e.index === next.index;
  return exclusions.some(matches)
    ? exclusions.filter((e) => !matches(e))
    : [...exclusions, next];
}

/** Per-word quiz raw material, in the same shape StoryRecorder flattens
 * per scene before collectQuizEntries. */
export interface WordQuizMaterial {
  translation?: string;
  aiDistractors?: string[];
  pinyin?: string;
  aiCloze?: Array<{ sentence: string; distractors: string[] }>;
  pos?: string;
  aiSynonyms?: Array<{ synonym: string; distractors: string[] }>;
  aiLookalikes?: string[];
}

export interface QuizMarksExportFile {
  storyId: string;
  storyTitle: string;
  exportedAt: string;
  exclusions: QuizExclusion[];
}

/** Downloads a story's current marks as a standalone .json file — a backup
 * a teacher can restore later via readQuizMarksImportFile, mirroring
 * storyPortability.ts's exportStoryFile/readStoryImportFile pair. */
export function exportQuizMarksFile(
  story: { id: string; title: string },
  exclusions: QuizExclusion[],
): void {
  const payload: QuizMarksExportFile = {
    storyId: story.id,
    storyTitle: story.title,
    exportedAt: new Date().toISOString(),
    exclusions,
  };
  const blob = new Blob([JSON.stringify(payload, null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `quiz-marks-${story.id}.json`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

/** Parses and validates a file produced by exportQuizMarksFile. Doesn't
 * check storyId against the story being imported into — the caller decides
 * whether to warn (a teacher may deliberately copy marks between two
 * similar stories). */
export async function readQuizMarksImportFile(file: File): Promise<QuizMarksExportFile> {
  let parsed: unknown;
  try {
    parsed = JSON.parse(await file.text());
  } catch {
    throw new Error("That file is not valid JSON.");
  }

  const obj = parsed as Partial<QuizMarksExportFile> | null;
  if (!obj || typeof obj !== "object" || !Array.isArray(obj.exclusions)) {
    throw new Error("This file doesn't look like a quiz-marks export.");
  }
  const exclusions = obj.exclusions.filter(
    (e): e is QuizExclusion =>
      Boolean(e) &&
      typeof e === "object" &&
      typeof (e as QuizExclusion).word === "string" &&
      typeof (e as QuizExclusion).kind === "string",
  );

  return {
    storyId: typeof obj.storyId === "string" ? obj.storyId : "",
    storyTitle: typeof obj.storyTitle === "string" ? obj.storyTitle : "",
    exportedAt: typeof obj.exportedAt === "string" ? obj.exportedAt : "",
    exclusions,
  };
}

/** Strips excluded material from one word's quiz inputs. Returns null when
 * the whole word is excluded (the caller drops the entry entirely). */
export function applyExclusionsToWord(
  word: string,
  material: WordQuizMaterial,
  exclusions: QuizExclusion[],
): WordQuizMaterial | null {
  if (isExcluded(exclusions, word, "word")) return null;
  const next: WordQuizMaterial = { ...material };
  if (material.aiCloze) {
    next.aiCloze = material.aiCloze.filter(
      (_c, i) => !isExcluded(exclusions, word, "cloze", i),
    );
  }
  if (material.aiSynonyms) {
    next.aiSynonyms = material.aiSynonyms.filter(
      (_s, i) => !isExcluded(exclusions, word, "synonym", i),
    );
  }
  if (material.aiLookalikes && isExcluded(exclusions, word, "lookalike")) {
    next.aiLookalikes = [];
  }
  if (material.aiDistractors && isExcluded(exclusions, word, "distractors")) {
    next.aiDistractors = [];
  }
  return next;
}
