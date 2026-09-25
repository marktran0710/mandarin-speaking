export type {
  AssistiveFeedbackSyllable,
  BackendFeedbackQuality,
  ContentDiffSegment,
  DiagnosticStatus,
  PauseAnalysis,
  PraatMetrics,
  ScoreProvenance,
  SpeechModel,
  VowelStatus,
  VowelZone,
  WordProsody,
  WordProsodySyllable,
} from "./types";

export { ASSISTIVE_MESSAGE, matchAssistiveRecord, worstState } from "./assistiveFeedback";
export type { AssistiveState } from "./assistiveFeedback";
export { assessVoiceFeedbackReliability } from "./voiceFeedbackReliability";
export type {
  VoiceFeedbackEvidence,
  VoiceFeedbackReliability,
  VoiceFeedbackReliabilityLevel,
} from "./voiceFeedbackReliability";
export {
  scoreScriptChunks,
  scriptAlignmentText,
  scriptDisplayChars,
  scriptMatchRatio,
  scriptMismatchTokens,
  splitScriptIntoChunks,
  splitTeacherScriptIntoPhrases,
} from "./scriptAlignment";
export type { ProsodyToken, ScriptChunkScore } from "./scriptAlignment";
