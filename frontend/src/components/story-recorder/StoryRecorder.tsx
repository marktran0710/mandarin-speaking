/**
 * Re-export hub only. The legacy React component this file used to export
 * (a wrapper around the minified StoryRecorderRuntime.js bundle) is gone —
 * the new Student Mode UI (src/student/speaking, src/student/conversation)
 * renders scenes and conversations directly. This file still exists because
 * a wide set of kept, non-student files (teacher pages, pronunciation
 * breakdown, content-diff, measurement) import types and pure helpers from
 * this exact path rather than reaching into the StoryRecorder/ subfolder
 * directly. Do not add a component export here again.
 */
export {
  practiceSceneIndicesFor,
  sceneSubmissionFromAudioRecord,
} from "./StoryRecorder/types";

export {
  buildSceneReferenceCurves,
  vocabTooltip,
} from "./StoryRecorder/storyContent";

export { normalizeConversationTurns } from "./StoryRecorder/conversation";

export type {
  ConversationSpeaker,
  ConversationTurn,
} from "./StoryRecorder/conversation";

export {
  createConversationState,
  currentConversationTurn,
  isStudentRecordingStep,
  shouldAnalyzeConversationTurn,
  transitionConversation,
} from "./StoryRecorder/conversationCoordinator";

export type {
  ConversationEvent,
  ConversationState,
  ConversationStep,
  ConversationTransition,
} from "./StoryRecorder/conversationCoordinator";

export type {
  AiProviderOption,
  SpeechModel,
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
