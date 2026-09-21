/** Feature entry point; implementation remains compatible with legacy pages during migration. */
export { default as StudentWorkspaceShell } from "../../components/student-workspace/StudentWorkspaceShell";
export {
  default as StudentPageShell,
  type StudentPageShellLayout,
  type StudentPageShellVariant,
} from "../../components/student-workspace/StudentPageShell";
export { default as StudentWorkspaceHeader } from "../../components/student-workspace/StudentWorkspaceHeader";
export { default as LearningOverview } from "../../components/student-workspace/LearningOverview";
export {
  StudentSection,
  StudentSectionBody,
  StudentSectionFooter,
  StudentSectionHeader,
} from "../../components/student-workspace/student-section";
export type {
  StudentSectionBodyLayout,
  StudentSectionDensity,
  StudentSectionVariant,
} from "../../components/student-workspace/student-section";
export { QuizGateStatus } from "../../components/student-workspace/LearningOverview";
export type {
  ContinuePracticeTarget,
  LearningSummary,
  QuizGateState,
  SessionIdentity,
  WorkspaceTopicSummary,
  WorkspaceView,
} from "../../types/studentWorkspace";
