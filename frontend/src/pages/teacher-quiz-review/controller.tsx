// @ts-nocheck
import { useEffect, useMemo, useRef, useState } from "react";
import { canUseDatabase, listCustomStories } from "../../services/database";
import { loadCustomStories, storyHasTierContent } from "../../utils/teacherStories";
import { storyQuizExclusions } from "../../utils/quizExclusions";
import { storyPendingApprovals } from "../../utils/quizPendingApprovals";
import { groupStoriesByLesson, lessonKeyFor, pendingKeyFor } from "./model-core";
import { QuizReviewContext } from "./context";
import { QuizReviewPageView } from "./page-view";
import type { QuizReviewJump } from "./types";

export function TeacherQuizReviewController({ jumpToLesson = null }: { jumpToLesson?: QuizReviewJump | null } = {}) {
  const [stories, setStories] = useState<CustomTeacherStory[]>([]);
  const [lessonKey, setLessonKey] = useState<string>("");
  const [storyFilterId, setStoryFilterId] = useState<string>("all");
  const [level, setLevel] = useState<StoryDifficultyLevel>("easy");
  const [exclusionsByStory, setExclusionsByStory] = useState<Record<string, QuizExclusion[]>>({});
  const [dirtyByStory, setDirtyByStory] = useState<Record<string, boolean>>({});
  const [statusByStory, setStatusByStory] = useState<Record<string, SaveStatus>>({});
  const [importNoteByStory, setImportNoteByStory] = useState<Record<string, string>>({});
  const [validationByStory, setValidationByStory] = useState<Record<string, QuizValidateResultItem[]>>({});
  const [validateStatusByStory, setValidateStatusByStory] = useState<Record<string, ValidateStatus>>({});
  const [approveStatusByStory, setApproveStatusByStory] = useState<Record<string, ApproveStatus>>({});
  // Keyed by `${storyId}:${level}` (see pendingKeyFor) — approvals are
  // tier-specific, unlike exclusions above.
  const [pendingApprovalsByKey, setPendingApprovalsByKey] = useState<Record<string, QuizApprovalMark[]>>({});
  const [editTarget, setEditTarget] = useState<EditTarget | null>(null);
  const [editDraft, setEditDraft] = useState<EditDraft | null>(null);
  const [editStatus, setEditStatus] = useState<"idle" | "saving" | "error">("idle");
  const [addQuestionTarget, setAddQuestionTarget] = useState<AddQuestionTarget | null>(null);
  const [addQuestionDraft, setAddQuestionDraft] = useState<AddQuestionDraft | null>(null);
  const [addQuestionStatus, setAddQuestionStatus] = useState<"idle" | "saving" | "error">("idle");
  const [pendingCandidatesByStory, setPendingCandidatesByStory] = useState<Record<string, PendingCandidate[]>>({});
  const [revealedCountByStory, setRevealedCountByStory] = useState<Record<string, number>>({});
  const [generationGateNoteByStory, setGenerationGateNoteByStory] = useState<Record<string, string>>({});
  const [generateStatusByStory, setGenerateStatusByStory] = useState<
    Record<string, "idle" | "generating" | "revealing" | "applying" | "error">
  >({});
  const importInputRef = useRef<HTMLInputElement>(null);
  const importTargetRef = useRef<string | null>(null);

  useEffect(() => {
    const local = loadCustomStories();
    const apply = (list: CustomTeacherStory[]) => {
      setStories(list.filter((s) => s.published));
    };
    apply(local);
    if (canUseDatabase()) {
      listCustomStories().then((db) => apply(db as CustomTeacherStory[])).catch(() => {});
    }
  }, []);

  // Seed per-story review state for any story we haven't seen yet, without
  // clobbering marks the teacher is already mid-editing in another story's
  // section on this same page.
  useEffect(() => {
    setExclusionsByStory((prev) => {
      const next = { ...prev };
      let changed = false;
      for (const story of stories) {
        if (!(story.id in next)) {
          next[story.id] = storyQuizExclusions(story);
          changed = true;
        }
      }
      return changed ? next : prev;
    });
  }, [stories]);

  // Same seed-once pattern, but keyed by story+tier since approvals are
  // tier-specific — visiting a new tier for the first time seeds it from
  // the server; a later `stories` refresh (e.g. after Approve & Publish)
  // must not clobber approvals already toggled this session.
  useEffect(() => {
    setPendingApprovalsByKey((prev) => {
      const next = { ...prev };
      let changed = false;
      for (const story of stories) {
        const key = pendingKeyFor(story.id, level);
        if (!(key in next)) {
          next[key] = storyPendingApprovals(story, level);
          changed = true;
        }
      }
      return changed ? next : prev;
    });
  }, [stories, level]);

  const lessonGroups = useMemo(() => groupStoriesByLesson(stories), [stories]);

  useEffect(() => {
    if (lessonGroups.length === 0) return;
    setLessonKey((current) =>
      current && lessonGroups.some((g) => lessonKeyFor(g.lessonNumber) === current)
        ? current
        : lessonKeyFor(lessonGroups[0].lessonNumber),
    );
  }, [lessonGroups]);

  const currentGroup = lessonGroups.find((g) => lessonKeyFor(g.lessonNumber) === lessonKey);

  // Reset back to Easy whenever the lesson changes — a level the new
  // lesson doesn't support would otherwise leave the page looking empty.
  useEffect(() => {
    setLevel("easy");
  }, [lessonKey]);

  // Deep-link from StoryBuilderSection's post-save "Go to Quiz Review"
  // banner — jumps straight to the lesson the just-saved story belongs to,
  // instead of leaving the teacher to find it in the dropdown again. Keyed
  // on the nonce so clicking the banner twice for the same lesson still works.
  useEffect(() => {
    if (!jumpToLesson) return;
    setLessonKey(lessonKeyFor(jumpToLesson.lessonNumber));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jumpToLesson?.nonce]);

  // A validate pass is tier-specific (it checks that tier's material) — a
  // leftover result from Easy would otherwise mislabel Medium's pools after
  // switching, since both share the same word/kind/poolIndex lookup keys.
  useEffect(() => {
    setValidationByStory({});
    setEditTarget(null);
    setEditDraft(null);
  }, [level]);

  useEffect(() => {
    // Start focused on one story. Batch review remains an explicit choice,
    // preventing a teacher from accidentally generating a large lesson-wide
    // draft while they are inspecting a single story.
    setStoryFilterId(currentGroup?.stories[0]?.id ?? "all");
  }, [lessonKey, currentGroup]);

  const levels: StoryDifficultyLevel[] = useMemo(() => {
    if (!currentGroup) return ["easy"];
    const out: StoryDifficultyLevel[] = ["easy"];
    if (currentGroup.stories.some((s) => storyHasTierContent(s, "medium"))) out.push("medium");
    if (currentGroup.stories.some((s) => storyHasTierContent(s, "hard"))) out.push("hard");
    return out;
  }, [currentGroup]);
  return <QuizReviewContext.Provider value={{ stories, setStories, lessonKey, setLessonKey, storyFilterId, setStoryFilterId, level, setLevel, exclusionsByStory, setExclusionsByStory, dirtyByStory, setDirtyByStory, statusByStory, setStatusByStory, importNoteByStory, setImportNoteByStory, validationByStory, setValidationByStory, validateStatusByStory, setValidateStatusByStory, approveStatusByStory, setApproveStatusByStory, pendingApprovalsByKey, setPendingApprovalsByKey, editTarget, setEditTarget, editDraft, setEditDraft, editStatus, setEditStatus, addQuestionTarget, setAddQuestionTarget, addQuestionDraft, setAddQuestionDraft, addQuestionStatus, setAddQuestionStatus, pendingCandidatesByStory, setPendingCandidatesByStory, revealedCountByStory, setRevealedCountByStory, generationGateNoteByStory, setGenerationGateNoteByStory, generateStatusByStory, setGenerateStatusByStory, importInputRef, importTargetRef, lessonGroups, currentGroup, levels }}><QuizReviewPageView /></QuizReviewContext.Provider>;
}
