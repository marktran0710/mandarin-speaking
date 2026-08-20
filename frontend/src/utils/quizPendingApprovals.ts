/** The Quiz Review page's opt-in checkbox selections (custom_stories
 * .quiz_pending_approvals) — which specific candidates a teacher has
 * checked so far, keyed by difficulty tier like quiz_exclusions. Not a
 * publish action by itself (see utils/quizApprovedMaterial.ts's
 * buildApprovedMaterial, sent via /quiz/approve when "Approve & Publish" is
 * clicked) — just persistence so a teacher's in-progress review survives a
 * page reload. Mirrors quizExclusions.ts's shape and helpers exactly,
 * opposite polarity: checked/allowlist instead of excluded/blacklist. */
import type { StoryDifficultyLevel } from "./teacherStories";

export type QuizApprovalKind = "distractors" | "cloze" | "synonym";

export interface QuizApprovalMark {
  word: string;
  kind: QuizApprovalKind;
  /** Pool position for cloze/synonym; omitted for distractors (the whole
   * list is one row, see routers/stories.py's replace_quiz_question). */
  index?: number;
}

export type StoredPendingApprovals = Partial<Record<StoryDifficultyLevel, QuizApprovalMark[]>>;

/** The story's checked-so-far list for one tier — [] (not undefined) when
 * the story has quizPendingApprovals but nothing for this tier yet. */
export function storyPendingApprovals(
  story: { quizPendingApprovals?: unknown },
  level: StoryDifficultyLevel,
): QuizApprovalMark[] {
  const raw = story.quizPendingApprovals;
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return [];
  const marks = (raw as StoredPendingApprovals)[level];
  return Array.isArray(marks) ? marks : [];
}

export function isApproved(
  marks: QuizApprovalMark[],
  word: string,
  kind: QuizApprovalKind,
  index?: number,
): boolean {
  return marks.some((m) => m.word === word && m.kind === kind && m.index === index);
}

export function toggleApproval(
  marks: QuizApprovalMark[],
  next: QuizApprovalMark,
): QuizApprovalMark[] {
  const matches = (m: QuizApprovalMark) =>
    m.word === next.word && m.kind === next.kind && m.index === next.index;
  return marks.some(matches) ? marks.filter((m) => !matches(m)) : [...marks, next];
}
