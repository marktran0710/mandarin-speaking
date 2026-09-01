import type { ComponentType } from "react";
import type { HelpRequest } from "../../services/database";
import StoryRecorderRuntime from "./StoryRecorderRuntime";
import type { NewAudioRecord } from "./StoryRecorder/types";
import type { Topic } from "./StoryRecorder/storyContent";

export interface StoryRecorderProps {
  topic: Topic;
  selectedImage: string;
  selectedImageIndex: number;
  onImageSelect: (index: number) => void;
  onImageChange: (image: string) => void;
  onAddRecord: (record: NewAudioRecord) => Promise<string | undefined> | void;
  enableSorting?: boolean;
  enableOverview?: boolean;
  startAtQuiz?: boolean;
  studentName?: string;
  studentId?: string;
  onExit?: () => void;
  helpRequests?: HelpRequest[];
  onRaiseHand?: (message: string) => void;
}

const TypedStoryRecorder = StoryRecorderRuntime as ComponentType<StoryRecorderProps>;

export default TypedStoryRecorder;

export {
  attemptHistoryFromAudioRecords,
  practiceSceneIndicesFor,
  sceneSubmissionFromAudioRecord,
} from "./StoryRecorderRuntime";

export {
  buildClozePatchUpdates,
  buildDistractorPatchUpdates,
  buildSceneReferenceCurves,
  buildSynonymPatchUpdates,
  planClozeGrowth,
  planDistractorGrowth,
  planSynonymGrowth,
  vocabTooltip,
} from "./StoryRecorder/storyContent";

export type {
  AiProviderOption,
  ClozeGrowthCandidate,
  DistractorGrowthCandidate,
  SpeechModel,
  SynonymGrowthCandidate,
  Topic,
} from "./StoryRecorder/storyContent";

export type {
  ContentDiffSegment,
  DiagnosticStatus,
  NewAudioRecord,
  PauseAnalysis,
  PraatMetrics,
  ScoreProvenance,
  TranscriptionItem,
  VowelStatus,
  VowelZone,
  WordProsody,
  WordProsodySyllable,
} from "./StoryRecorder/types";
