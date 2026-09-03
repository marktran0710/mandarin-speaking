// @ts-nocheck
import type { QuizApprovalKind } from "../../utils/quizPendingApprovals";
import type { CustomStoryFrame } from "../../utils/teacherStories";

const POOL_FIELD: Record<QuizApprovalKind, keyof CustomStoryFrame> = {
  distractors: "vocabularyDistractors",
  cloze: "vocabularyCloze",
  synonym: "vocabularySynonym",
};
const GENERATED_POOL_FIELD: Record<GeneratedKind, keyof CustomStoryFrame> = {
  distractors: "vocabularyDistractors",
  cloze: "vocabularyCloze",
  synonym: "vocabularySynonym",
};
const PENDING_KIND_LABELS: Record<GeneratedKind, { zh: string; en: string }> = {
  distractors: { zh: "干擾選項", en: "Distractors" },
  cloze: { zh: "填空", en: "Cloze" },
  synonym: { zh: "同義詞", en: "Synonym" },
};

const PENDING_ORIGIN_LABELS: Record<CandidateOrigin, { zh: string; en: string }> = {
  new: { zh: "新增", en: "New" },
  changed: { zh: "已更改", en: "Changed" },
  removed: { zh: "已移除", en: "Removed" },
};

function pendingDecisionCopy(origin: CandidateOrigin, decision: "accept" | "reject") {
  if (decision === "accept") {
    if (origin === "changed") return { zh: "使用新版本", en: "Using new version" };
    if (origin === "removed") return { zh: "已刪除", en: "Removed" };
    return { zh: "已新增", en: "Added" };
  }
  if (origin === "changed") return { zh: "保留舊版本", en: "Kept old version" };
  if (origin === "removed") return { zh: "已還原", en: "Restored" };
  return { zh: "已捨棄", en: "Discarded" };
}

/** Formats one pending candidate value for a diff-style line, preserving the
 * existing prompt/options content while allowing old/new/removed rendering. */

export { POOL_FIELD, GENERATED_POOL_FIELD, PENDING_KIND_LABELS, PENDING_ORIGIN_LABELS, pendingDecisionCopy };
