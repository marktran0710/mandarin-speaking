/** Public feature boundary for the shared Student Mode composition system. */
export { default as StudentWorkspaceShell } from "../../components/student-workspace/StudentWorkspaceShell";
export {
  default as StudentPageShell,
  type StudentPageShellLayout,
  type StudentPageTemplate,
  type StudentPageShellVariant,
} from "../../components/student-workspace/StudentPageShell";
export { default as StudentWorkspaceHeader } from "../../components/student-workspace/StudentWorkspaceHeader";
export { default as LearningOverview } from "../../components/student-workspace/LearningOverview";
export {
  StudentActionBar,
  StudentCluster,
  StudentGrid,
  StudentPageBody,
  StudentRow,
  StudentSection,
  StudentSectionBody,
  StudentSectionFooter,
  StudentSectionHeader,
  StudentStack,
} from "../../components/student-workspace/student-layout";
export type {
  StudentActionAlignment,
  StudentGridColumns,
  StudentLayoutDensity,
  StudentPageBodyVariant,
  StudentSectionBodyLayout,
  StudentSectionDensity,
  StudentSectionVariant,
} from "../../components/student-workspace/student-layout";
export { QuizGateStatus } from "../../components/student-workspace/LearningOverview";
export type {
  ContinuePracticeTarget,
  LearningSummary,
  QuizGateState,
  SessionIdentity,
  WorkspaceTopicSummary,
  WorkspaceView,
} from "../../types/studentWorkspace";
