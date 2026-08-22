/** The AI-generated quiz material a teacher has explicitly approved via the
 * Quiz Review page's "Approve & Publish" action (custom_stories
 * .quiz_approved_snapshot), keyed by difficulty tier like quiz_material_
 * snapshot. storyToTopic reads this — not the live per-word fields — when
 * building a student-facing topic, so editing a story or a student's own
 * background pool growth (StoryRecorder's growVocabularyDistractorPool and
 * friends) can never change what a student sees until a teacher re-approves.
 * Missing/empty for a tier means that tier has never been approved: the quiz
 * simply has no AI material yet, same as before this feature existed. */
import type { StoryDifficultyLevel } from "./teacherStories";
import type { QuizSourceTopic } from "./topicQuiz";
import { applyExclusionsToWord, isExcluded, type QuizExclusion } from "./quizExclusions";
import { isApproved, type QuizApprovalMark } from "./quizPendingApprovals";

export interface ApprovedMaterialEntry {
  word: string;
  translation?: string;
  distractors: string[];
  cloze: Array<{ sentence: string; distractors: string[] }>;
  synonym: Array<{ synonym: string; distractors: string[] }>;
}

export type ApprovedSnapshot = ApprovedMaterialEntry[];

export type StoredApprovedSnapshot = Partial<Record<StoryDifficultyLevel, ApprovedSnapshot>>;

// The runtime quiz shuffles and draws at most three AI distractors. Keeping
// exactly that many in a published snapshot means the set reviewed by the
// adversarial validator is the same set a student can actually be shown;
// an unreviewed fourth pool entry can never rotate into a question later.
const MAX_PUBLISHED_WRONG_OPTIONS = 3;

/** The story's approved AI material for one tier, or null when that tier
 * has never been approved — the caller should serve no AI pools in that
 * case rather than falling back to live/unreviewed material. */
export function storyApprovedSnapshot(
  story: { quizApprovedSnapshot?: unknown },
  level: StoryDifficultyLevel,
): ApprovedSnapshot | null {
  const raw = story.quizApprovedSnapshot;
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
  const entries = (raw as StoredApprovedSnapshot)[level];
  return Array.isArray(entries) ? entries : null;
}

/** Whether a published story's live quiz material has drifted from what's
 * actually approved for students — new/changed AI pools since the last
 * Approve & Publish, or a tier that's never been approved at all. A coarse,
 * story-level roll-up for a list badge; the Quiz Review page's per-word 🆕/✎
 * badges (see quizMaterialDiff.ts, a separate diff-only snapshot) are the
 * fine-grained view once a teacher opens the story to act on it. */
export function storyQuizNeedsReview(
  story: Parameters<typeof storyApprovedSnapshot>[0],
  liveEntries: ApprovedMaterialEntry[],
  level: StoryDifficultyLevel,
): boolean {
  const hasAnyAiMaterial = liveEntries.some(
    (e) => e.distractors.length || e.cloze.length || e.synonym.length,
  );
  if (!hasAnyAiMaterial) return false; // nothing AI-generated exists yet to review
  const approved = storyApprovedSnapshot(story, level);
  if (!approved) return true; // never approved
  return JSON.stringify(approved) !== JSON.stringify(liveEntries);
}

/** Builds exactly what "Approve & Publish" sends the server: one entry per
 * distinct word (first scene occurrence wins — later duplicates are inert
 * for the live quiz anyway, see collectQuizEntries), with every excluded
 * pool already stripped via applyExclusionsToWord. This becomes the whole
 * approved snapshot for the tier — nothing excluded here should ever
 * resurface for a student. */
export function buildApprovedMaterial(
  topic: QuizSourceTopic,
  exclusions: QuizExclusion[],
): ApprovedMaterialEntry[] {
  const entries: ApprovedMaterialEntry[] = [];
  const seen = new Set<string>();
  topic.images.forEach((_, si) => {
    (topic.vocabulary[si] || []).forEach((word, wi) => {
      if (seen.has(word)) return;
      seen.add(word);
      const filtered = applyExclusionsToWord(
        word,
        {
          translation: topic.vocabularyTranslation?.[si]?.[wi],
          aiDistractors: topic.vocabularyDistractors?.[si]?.[wi],
          aiCloze: topic.vocabularyCloze?.[si]?.[wi],
          aiSynonyms: topic.vocabularySynonym?.[si]?.[wi],
        },
        exclusions,
      );
      if (!filtered) return; // whole word excluded
      entries.push({
        word,
        translation: filtered.translation,
        distractors: (filtered.aiDistractors ?? []).slice(0, MAX_PUBLISHED_WRONG_OPTIONS),
        // One reviewed prompt per generated question type keeps the student
        // quiz predictable. Extra candidates remain available in the teacher
        // draft/source data, but are not published or rotated at runtime.
        cloze: (filtered.aiCloze ?? []).slice(0, 1).map((candidate) => ({
          ...candidate,
          distractors: candidate.distractors.slice(0, MAX_PUBLISHED_WRONG_OPTIONS),
        })),
        synonym: (filtered.aiSynonyms ?? []).slice(0, 1).map((candidate) => ({
          ...candidate,
          distractors: candidate.distractors.slice(0, MAX_PUBLISHED_WRONG_OPTIONS),
        })),
      });
    });
  });
  return entries;
}

/** Builds what "Approve & Publish" actually sends once Quiz Review moved to
 * opt-in checkboxes: a distractors/cloze/synonym item only makes it in if
 * the teacher explicitly checked it (allowlist, gated on having survived a
 * Validate pass first — see TeacherQuizReviewPage). */
export function buildApprovedMaterialFromApprovals(
  topic: QuizSourceTopic,
  approvals: QuizApprovalMark[],
  exclusions: QuizExclusion[],
): ApprovedMaterialEntry[] {
  const entries: ApprovedMaterialEntry[] = [];
  const seen = new Set<string>();
  topic.images.forEach((_, si) => {
    (topic.vocabulary[si] || []).forEach((word, wi) => {
      if (seen.has(word)) return;
      seen.add(word);
      if (isExcluded(exclusions, word, "word")) return;
      const cloze = topic.vocabularyCloze?.[si]?.[wi] ?? [];
      const synonym = topic.vocabularySynonym?.[si]?.[wi] ?? [];
      entries.push({
        word,
        translation: topic.vocabularyTranslation?.[si]?.[wi],
        distractors: isApproved(approvals, word, "distractors")
          ? (topic.vocabularyDistractors?.[si]?.[wi] ?? []).slice(0, MAX_PUBLISHED_WRONG_OPTIONS)
          : [],
        cloze: cloze
          .filter((_, ci) => isApproved(approvals, word, "cloze", ci))
          .slice(0, 1)
          .map((candidate) => ({
            ...candidate,
            distractors: candidate.distractors.slice(0, MAX_PUBLISHED_WRONG_OPTIONS),
          })),
        synonym: synonym
          .filter((_, syi) => isApproved(approvals, word, "synonym", syi))
          .slice(0, 1)
          .map((candidate) => ({
            ...candidate,
            distractors: candidate.distractors.slice(0, MAX_PUBLISHED_WRONG_OPTIONS),
          })),
      });
    });
  });
  return entries;
}
