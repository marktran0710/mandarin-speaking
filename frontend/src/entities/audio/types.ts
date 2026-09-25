import type { PraatMetrics, SpeechModel } from "../speech";

export interface AudioRecord {
  id: string;
  audioBlob?: Blob;
  timestamp: string;
  duration: number;
  transcription: string;
  model: string | SpeechModel;
  praatMetrics?: PraatMetrics | any;
  topicId?: string;
  studentId?: string | null;
  imageUrl?: string;
  imageIndex?: number;
  conversationId?: string;
  turnId?: string;
  turnIndex?: number;
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
  serverVerified?: boolean;
  serverRecordId?: string;
}

export interface StudentAudioRecord extends AudioRecord {
  audioBlob: Blob;
  model: SpeechModel;
}
