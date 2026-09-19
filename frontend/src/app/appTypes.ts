import type { StudentWorkspaceView } from "../pages/StudentWorkspacePage";
import type { SpeechModel } from "../components/story-recorder/StoryRecorder";
import type { Page } from "../types/page";

export interface AudioRecord {
  id: string;
  audioBlob: Blob;
  timestamp: string;
  duration: number;
  transcription: string;
  model: SpeechModel;
  praatMetrics?: any;
  topicId?: string;
  studentId?: string | null;
  imageUrl?: string;
  imageIndex?: number;
  audioUrl?: string;
  audioName?: string;
  analysisVersion?: "stable_v1";
  analysisSchemaVersion?: string;
  modelVersion?: string;
  comparisonGroupId?: string;
  sessionId?: string;
  attemptId?: string;
  attemptNumber?: number;
  attemptType?: "WHOLE_SENTENCE_INITIAL" | "FOCUSED_RETRY" | "WHOLE_SENTENCE_FINAL";
  /** Set when the server already persisted this stable analysis. */
  serverVerified?: boolean;
  serverRecordId?: string;
}

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
