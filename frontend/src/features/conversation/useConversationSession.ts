import { useEffect, useMemo, useRef, useState } from "react";
import type { NewAudioRecord } from "../../components/story-recorder/StoryRecorder";
import type { Topic } from "@entities/topic";
import {
  createConversationState,
  currentConversationTurn,
  transitionConversation,
  type ConversationEvent,
  type ConversationState,
  type ConversationTurn,
} from "../../components/story-recorder/StoryRecorder";
import { saveSpeakingProgress, type SceneSubmission } from "../../services/database";
import {
  analyzeSpeakingResult,
  type SpeakingResultAnalysis,
} from "../../components/speaking-flow-card/SpeakingResultsFlow.analysis";
import { getStudentId } from "../../utils/studentSession";
import { topicStoryId } from "../../utils/lessonGroups";
import { markPhaseSeen } from "@shared/lib/studyProgressFlags";
import { useSpeakingRecorder, type SpeakingAnalysisResult } from "../speaking/hooks/useSpeakingRecorder";
import { normalizeSpeechModel } from "@entities/speech/recordingModel";

interface UseConversationSessionArgs {
  topic: Topic;
  turns: ConversationTurn[];
  onAddRecord: (record: NewAudioRecord) => Promise<string | undefined> | void;
  onSceneSubmission: (key: string, submission: SceneSubmission) => void;
  onDone: () => void;
}

export interface ConversationSession {
  state: ConversationState;
  currentTurn: ConversationTurn | null;
  historyTurns: ConversationTurn[];
  lastAnalysis: SpeakingResultAnalysis | null;
  lastResult: SpeakingAnalysisResult | null;
  lastRecognizedText: string;
  recorder: ReturnType<typeof useSpeakingRecorder>;
  exchange: { current: number; total: number };
  handleListen: () => void;
  handleRecord: () => Promise<void>;
  recordAgain: () => void;
  nextTurn: () => void;
}

export function useConversationSession({
  topic,
  turns,
  onAddRecord,
  onSceneSubmission,
  onDone,
}: UseConversationSessionArgs): ConversationSession {
  const [state, setState] = useState<ConversationState>(
    () => createConversationState(turns) ?? { turnIndex: 0, step: "summary" },
  );
  const [lastAnalysis, setLastAnalysis] = useState<SpeakingResultAnalysis | null>(null);
  const [lastResult, setLastResult] = useState<SpeakingAnalysisResult | null>(null);
  const [lastRecognizedText, setLastRecognizedText] = useState("");
  const conversationIdRef = useRef(`conv-${topic.id}-${Date.now()}`);
  const studentId = getStudentId();
  const currentTurn = currentConversationTurn(state, turns);

  const recorder = useSpeakingRecorder((attemptNumber) => ({
    scenePrompt: topic.name,
    sceneTargetText: currentTurn?.targetText || currentTurn?.text || "",
    conversationId: conversationIdRef.current,
    turnId: currentTurn?.id,
    turnIndex: state.turnIndex,
    attemptNumber,
  }));

  const dispatch = (event: ConversationEvent) => {
    setState((previous) => {
      const transition = transitionConversation(previous, event, turns);
      return transition.accepted ? transition.state : previous;
    });
  };

  useEffect(() => {
    if (state.step === "selfEval") dispatch({ type: "selfEvaluationSkipped" });
    // Conversation Practice has no separate learner self-evaluation step.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.step]);

  useEffect(() => {
    if (state.step === "summary") {
      markPhaseSeen(topicStoryId(topic), "conversation");
      onDone();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.step]);

  const handleListen = () => dispatch({ type: "systemAudioCompleted" });

  const handleRecord = async () => {
    if (!currentTurn) return;
    const result = await recorder.startRecording();
    if (!result) return;

    const transcription = (result.metrics.transcription || "").trim();
    const analysis = analyzeSpeakingResult({
      modelSentence: currentTurn.targetText || currentTurn.text,
      praatMetrics: result.metrics,
      ready: result.masteryPassed && result.contentPassed,
      selectedImageIndex: 0,
    });
    setLastResult(result);
    setLastRecognizedText(transcription);
    setLastAnalysis(analysis);

    const submission: SceneSubmission = {
      sceneIndex: 0,
      imageUrl: topic.images[0] ?? "",
      transcription,
      vocabUsed: result.metrics.ai_feedback?.vocabulary_coverage?.used ?? [],
      vocabMissing: result.metrics.ai_feedback?.vocabulary_coverage?.missing ?? [],
      vocabScore: result.metrics.ai_feedback?.vocabulary_coverage?.score ?? 0,
      toneAccuracy: Math.round(result.metrics.tone_accuracy ?? 0),
      pronScore: Math.round(result.metrics.tone_accuracy ?? 0),
      fluencyScore: Math.round(result.metrics.fluency_score ?? 0),
      audioUrl: result.audioUrl,
      conversationId: conversationIdRef.current,
      turnId: currentTurn.id,
      turnIndex: state.turnIndex,
      baseStoryId: topic.sourceStory?.id ?? topic.id,
      difficultyLevel: topic.difficultyLevel ?? "easy",
      promptId: `${topic.sourceStory?.id ?? topic.id}:conversation:${currentTurn.id}`,
    };

    await onAddRecord({
      id: `audio-${Date.now()}`,
      audioBlob: result.audioBlob,
      timestamp: new Date().toLocaleString(),
      duration: Math.max(1, recorder.recordingDuration),
      transcription,
      model: normalizeSpeechModel(result.metrics.transcription_model),
      topicId: topic.id,
      imageUrl: topic.images[0] ?? "",
      imageIndex: 0,
      conversationId: conversationIdRef.current,
      turnId: currentTurn.id,
      turnIndex: state.turnIndex,
      praatMetrics: result.metrics,
      analysisVersion: "stable_v1",
      serverVerified: result.verified,
      serverRecordId: result.audioRecordId,
      audioUrl: result.audioUrl,
    });

    onSceneSubmission(`conversation:${state.turnIndex}`, submission);

    if (studentId) {
      try {
        await saveSpeakingProgress({
          studentId,
          topicId: topic.id,
          sceneIndex: 0,
          attempts: 1,
          bestTone: submission.toneAccuracy,
          bestFluency: submission.fluencyScore ?? 0,
          masteryPassed: result.masteryPassed,
          contentPassed: result.contentPassed,
          clearedWords: submission.vocabUsed,
          conversationId: conversationIdRef.current,
          turnId: currentTurn.id,
          turnIndex: state.turnIndex,
          latestResult: submission,
          baseStoryId: submission.baseStoryId,
          difficultyLevel: submission.difficultyLevel,
          promptId: submission.promptId,
        });
      } catch {
        // Feedback remains usable when progress persistence is unavailable.
      }
    }

    dispatch({ type: "studentRecordingCompleted", recordingId: currentTurn.id });
  };

  const recordAgain = () => {
    setLastAnalysis(null);
    setLastResult(null);
    setLastRecognizedText("");
    setState((previous) => ({ ...previous, step: "student" }));
  };

  const nextTurn = () => {
    setLastAnalysis(null);
    setLastResult(null);
    setLastRecognizedText("");
    dispatch({ type: "feedbackCompleted" });
  };

  const historyTurns = useMemo(() => turns.slice(0, state.turnIndex), [state.turnIndex, turns]);
  const studentTurnIndexes = useMemo(
    () => turns.reduce<number[]>((indexes, turn, index) => turn.speaker === "student" ? [...indexes, index] : indexes, []),
    [turns],
  );
  const currentStudentPosition = studentTurnIndexes.findIndex((index) => index === state.turnIndex);
  const nextStudentPosition = studentTurnIndexes.findIndex((index) => index >= state.turnIndex);
  const exchange = {
    current: currentStudentPosition >= 0
      ? currentStudentPosition + 1
      : nextStudentPosition >= 0
        ? nextStudentPosition + 1
        : studentTurnIndexes.length,
    total: studentTurnIndexes.length,
  };

  return {
    state,
    currentTurn,
    historyTurns,
    lastAnalysis,
    lastResult,
    lastRecognizedText,
    recorder,
    exchange,
    handleListen,
    handleRecord,
    recordAgain,
    nextTurn,
  };
}
