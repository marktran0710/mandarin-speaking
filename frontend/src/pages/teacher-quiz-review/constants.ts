// @ts-nocheck
import type { QuizApprovalKind } from "../../utils/quizPendingApprovals";
import type { CustomStoryFrame } from "../../utils/teacherStories";

const POOL_FIELD: Record<QuizApprovalKind, keyof CustomStoryFrame> = {
  distractors: "vocabularyDistractors",
  cloze: "vocabularyCloze",
  synonym: "vocabularySynonym",
};

export { POOL_FIELD };
