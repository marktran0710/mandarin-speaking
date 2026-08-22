/** Feature entry point; implementation remains compatible with legacy pages during migration. */
export { default as StudentWorkspaceShell } from "../../components/student-workspace/StudentWorkspaceShell";
export { default as StudentWorkspaceHeader } from "../../components/student-workspace/StudentWorkspaceHeader";
export { default as WorkspaceAreaTabs } from "../../components/student-workspace/WorkspaceAreaTabs";
export { default as LearningOverview } from "../../components/student-workspace/LearningOverview";
export { QuizGateStatus } from "../../components/student-workspace/LearningOverview";
export type {
  ContinuePracticeTarget,
  LearningSummary,
  QuizGateState,
  SessionIdentity,
  WorkspaceTopicSummary,
  WorkspaceView,
} from "../../types/studentWorkspace";
