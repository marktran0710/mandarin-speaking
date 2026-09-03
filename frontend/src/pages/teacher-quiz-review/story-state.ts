// @ts-nocheck
import { buildApprovedMaterial } from "../../utils/quizApprovedMaterial";
import { isExcluded } from "../../utils/quizExclusions";
import { storyMaterialSnapshot } from "../../utils/quizMaterialDiff";
import { storyToTopic } from "../../utils/teacherStories";
import { builtInReviewWords, pendingKeyFor } from "./model-core";
import { useQuizReviewContext } from "./context";

export function useQuizReviewStoryState(story) {
  const ctx = useQuizReviewContext();
  const { level, storyFilterId, exclusionsByStory, dirtyByStory, statusByStory, importNoteByStory, validateStatusByStory, approveStatusByStory, validationByStory, pendingApprovalsByKey, generateStatusByStory, pendingCandidatesByStory, revealedCountByStory } = ctx;
          if (level !== "easy" && !storyHasTierContent(story, level)) return null;
          const topic = storyToTopic(story, level);
          const exclusions = exclusionsByStory[story.id] ?? [];
          const dirty = dirtyByStory[story.id] ?? false;
          const status = statusByStory[story.id] ?? "idle";
          const snapshot = storyMaterialSnapshot(story, level);
          const importNote = importNoteByStory[story.id];
          const validateStatus = validateStatusByStory[story.id] ?? "idle";
          const approveStatus = approveStatusByStory[story.id] ?? "idle";
          const validation = validationByStory[story.id];
          const approvals = pendingApprovalsByKey[pendingKeyFor(story.id, level)] ?? [];
          const approvedCount = approvals.length;
          const generateStatus = generateStatusByStory[story.id] ?? "idle";
          const pendingCandidates = pendingCandidatesByStory[story.id] ?? [];
          const revealedCount = revealedCountByStory[story.id] ?? 0;
          const pendingByWord = new Map<string, IndexedPendingCandidate[]>();
          pendingCandidates.forEach((candidate, index) => {
            const entries = pendingByWord.get(candidate.word) ?? [];
            entries.push({ candidate, index });
            pendingByWord.set(candidate.word, entries);
          });
          const liveWords = new Set<string>();
          topic.images.forEach((_, si) => {
            (topic.vocabulary[si] || []).forEach((word) => liveWords.add(word));
          });
          const removedPendingGroups = [...pendingByWord.entries()]
            .map(([word, entries]) => ({
              word,
              entries: entries.filter(({ candidate }) => candidate.origin === "removed"),
            }))
            .filter(({ word, entries }) => entries.length > 0 && !liveWords.has(word));
          const hasAnyMaterial = buildApprovedMaterial(topic, []).some(
            (e) => e.distractors.length || e.cloze.length || e.synonym.length,
          );
          const pendingDecidedCount = pendingCandidates.filter((c) => c.decision !== "pending").length;
          const pendingAcceptedCount = pendingCandidates.filter((c) => c.decision === "accept").length;
          const isGenerating = generateStatus === "generating" || generateStatus === "revealing" || generateStatus === "applying";
          const isValidating = validateStatus === "validating";
          const isPublishing = approveStatus === "approving";
          const isSavingMarks = status === "saving";
          const canApproveAll = (validation?.length ?? 0) > 0;
          const canApplyPending = pendingCandidates.length > 0 && pendingDecidedCount === pendingCandidates.length;
          const hasSuspiciousQuestions = validation?.some((result) => result.status === "suspicious") ?? false;
          const canGenerate = pendingCandidates.length === 0 && (!hasAnyMaterial || hasSuspiciousQuestions);
          const canValidate = pendingCandidates.length === 0 && hasAnyMaterial && !hasSuspiciousQuestions;
          const showActionRail =
            approvedCount > 0 ||
            exclusions.length > 0 ||
            dirty ||
            pendingCandidates.length > 0 ||
            canApproveAll ||
            isPublishing ||
            isSavingMarks ||
            approveStatus !== "idle" ||
            status !== "idle";
          const renderedWords = new Set<string>();
          const builtInWords = builtInReviewWords(topic);
          const builtInByWord = new Map(builtInWords.map((entry) => [entry.word, entry]));
  return { story, topic, exclusions, dirty, status, snapshot, importNote, validateStatus, approveStatus, validation, approvals, approvedCount, generateStatus, pendingCandidates, revealedCount, pendingByWord, liveWords, removedPendingGroups, hasAnyMaterial, pendingDecidedCount, pendingAcceptedCount, isGenerating, isValidating, isPublishing, isSavingMarks, canApproveAll, canApplyPending, hasSuspiciousQuestions, canGenerate, canValidate, showActionRail, renderedWords, builtInWords, builtInByWord };
}
