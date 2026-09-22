import type { HelpRequest } from "../services/database";
import type { NewAudioRecord } from "../components/story-recorder/StoryRecorder";
import type { Topic } from "../components/content/TopicSelector";
import type { WorkspaceView } from "../types/studentWorkspace";
import { StudentWorkspaceShell } from "../features/student-workspace";

import "./StudentWorkspacePage.css";

export type StudentWorkspaceView = WorkspaceView;

export interface StudentWorkspacePageProps {
  view: StudentWorkspaceView;
  onViewChange: (view: StudentWorkspaceView) => void;
  onAddRecord: (record: NewAudioRecord) => void;
  initialTopicId?: string;
  initialImageIndex?: number;
  initialStartAtQuiz?: boolean;
  initialTargetKey?: number;
  helpRequests: HelpRequest[];
  onRaiseHand: (message: string) => void;
  storyTopics: Topic[];
  audioRecords: import("./MyStoriesPage").AudioRecord[];
  onSessionActiveChange: (active: boolean) => void;
  isInPracticeSession: boolean;
  onStartActivity?: (topicId: string, startAtQuiz: boolean) => void;
  onLogout: () => void;
  onOpenPlacementTest?: () => void;
}

/**
 * Route-level composition boundary for Student Mode.
 *
 * The old legacy branch has been removed so every workspace entry uses the
 * same StudentModeFrame → StudentPageShell hierarchy.
 */
export default function StudentWorkspacePage(props: StudentWorkspacePageProps) {
  return <StudentWorkspaceShell {...props} />;
}
