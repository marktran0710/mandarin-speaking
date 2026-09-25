import type { StudentAudioRecord } from "@entities/audio";
import type { Page } from "../types/page";

/** Was exported by the deleted pages/StudentWorkspacePage. StudentApp owns
 * its own Study/Progress state now; this survives only as the on-disk
 * encoding appNavigation.ts still reads when restoring a saved page. */
export type StudentWorkspaceView = "practice" | "progress";

/** @deprecated Import StudentAudioRecord from @entities/audio. */
export type AudioRecord = StudentAudioRecord;

export interface PracticeTarget {
  topicId: string;
  imageIndex: number;
  startAtQuiz?: boolean;
  seq?: number;
}

export interface StudentAppBootstrapState {
  activeRole: "student" | null;
  currentPage: Page;
  studentWorkspaceView: StudentWorkspaceView;
  practiceTarget: PracticeTarget | null;
}
