// @ts-nocheck
import { buildApprovedMaterial } from "../../utils/quizApprovedMaterial";
import { isExcluded } from "../../utils/quizExclusions";
import { storyMaterialSnapshot } from "../../utils/quizMaterialDiff";
import { storyToTopic } from "../../utils/teacherStories";
import { builtInReviewWords, pendingKeyFor } from "./model-core";
import { useQuizReviewContext } from "./context";

export function useQuizReviewStoryState(story) {
  const ctx = useQuizReviewContext();
  const { level, storyFilterId, exclusionsByStory, dirtyByStory, statusByStory, importNoteByStory, approveStatusByStory, pendingApprovalsByKey, uploadNoteByStory } = ctx;
          const topic = storyToTopic(story, level);
          const exclusions = exclusionsByStory[story.id] ?? [];
          const dirty = dirtyByStory[story.id] ?? false;
          const status = statusByStory[story.id] ?? "idle";
          const snapshot = storyMaterialSnapshot(story, level);
          const importNote = importNoteByStory[story.id];
          const uploadNote = uploadNoteByStory[story.id];
          const approveStatus = approveStatusByStory[story.id] ?? "idle";
          const approvals = pendingApprovalsByKey[pendingKeyFor(story.id, level)] ?? [];
          const approvedCount = approvals.length;
          const hasAnyMaterial = buildApprovedMaterial(topic, []).some(
            (e) => e.distractors.length || e.cloze.length || e.synonym.length,
          );
          const isPublishing = approveStatus === "approving";
          const isSavingMarks = status === "saving";
          const canApproveAll = hasAnyMaterial;
          const showActionRail =
            approvedCount > 0 ||
            exclusions.length > 0 ||
            dirty ||
            canApproveAll ||
            isPublishing ||
            isSavingMarks ||
            approveStatus !== "idle" ||
            status !== "idle";
          const renderedWords = new Set<string>();
          const builtInWords = builtInReviewWords(topic);
          const builtInByWord = new Map(builtInWords.map((entry) => [entry.word, entry]));
  return { story, topic, exclusions, dirty, status, snapshot, importNote, uploadNote, approveStatus, approvals, approvedCount, hasAnyMaterial, isPublishing, isSavingMarks, canApproveAll, showActionRail, renderedWords, builtInWords, builtInByWord };
}
