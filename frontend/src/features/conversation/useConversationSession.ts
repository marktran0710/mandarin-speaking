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
} from "../../components/speaking-flow-card/model/analysis";
import { getStudentId } from "../../utils/studentSession";
import { topicStoryId } from "../../utils/lessonGroups";
import { markPhaseSeen } from "@shared/lib/studyProgressFlags";
import { useSpeakingRecorder, type SpeakingAnalysisResult } from "../speaking/hooks/useSpeakingRecorder";
import { normalizeSpeechModel } from "@entities/speech/recordingModel";
import type { SelfEvalLevel } from "@entities/speech";

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
  lastSubmission: SceneSubmission | null;
  selfEvalMeaning: SelfEvalLevel | null;
  selfEvalPronunciation: SelfEvalLevel | null;
  recorder: ReturnType<typeof useSpeakingRecorder>;
  exchange: { current: number; total: number };
  handleListen: () => void;
  handleRecord: () => Promise<void>;
  handleUpload: (file: File) => Promise<void>;
  submitSelfEvaluation: (skip: boolean) => Promise<void>;
  setSelfEvalMeaning: (value: SelfEvalLevel) => void;
  setSelfEvalPronunciation: (value: SelfEvalLevel) => void;
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
  const [lastSubmission, setLastSubmission] = useState<SceneSubmission | null>(null);
  const [selfEvalMeaning, setSelfEvalMeaning] = useState<SelfEvalLevel | null>(null);
  const [selfEvalPronunciation, setSelfEvalPronunciation] = useState<SelfEvalLevel | null>(null);
  const [selfEvalSaved, setSelfEvalSaved] = useState(false);
  const selfEvalCommitRef = useRef(false);
  const conversationIdRef = useRef(`conv-${topic.id}-${Date.now()}`);
  const studentId = getStudentId();
  const baseStoryId = topic.sourceStory?.id ?? topic.id;
  const currentTurn = currentConversationTurn(state, turns);

  const recorder = useSpeakingRecorder((attemptNumber) => ({
    baseStoryId,
    sceneIndex: currentTurn?.sceneIndex ?? 0,
    difficultyLevel: topic.difficultyLevel ?? "easy",
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
    if (state.step === "summary") {
      markPhaseSeen(topicStoryId(topic), "conversation");
      onDone();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.step]);

  const handleListen = () => dispatch({ type: "systemAudioCompleted" });

  const handleAnalysisResult = async (result: SpeakingAnalysisResult | null) => {
    if (!currentTurn) return;
    if (!result) return;

    const transcription = (result.metrics.transcription || "").trim();
    const analysis = analyzeSpeakingResult({
      modelSentence: currentTurn.targetText || currentTurn.text,
      praatMetrics: result.metrics,
      ready: result.masteryPassed && result.contentPassed,
      selectedImageIndex: currentTurn.sceneIndex ?? 0,
    });
    setLastResult(result);
    setLastRecognizedText(transcription);
    setLastAnalysis(analysis);

    const submission: SceneSubmission = {
      sceneIndex: currentTurn.sceneIndex ?? 0,
      imageUrl: topic.images[currentTurn.sceneIndex ?? 0] ?? "",
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
      baseStoryId,
      difficultyLevel: topic.difficultyLevel ?? "easy",
      promptId: `${topic.sourceStory?.id ?? topic.id}:conversation:${currentTurn.id}`,
    };
    setLastSubmission(submission);
    setSelfEvalMeaning(null);
    setSelfEvalPronunciation(null);
    setSelfEvalSaved(false);
    selfEvalCommitRef.current = false;

    await onAddRecord({
      id: `audio-${Date.now()}`,
      audioBlob: result.audioBlob,
      timestamp: new Date().toLocaleString(),
      duration: Math.max(1, recorder.recordingDuration),
      transcription,
      model: normalizeSpeechModel(result.metrics.transcription_model),
      topicId: topic.id,
      imageUrl: topic.images[currentTurn.sceneIndex ?? 0] ?? "",
      imageIndex: currentTurn.sceneIndex ?? 0,
      conversationId: conversationIdRef.current,
      turnId: currentTurn.id,
      turnIndex: state.turnIndex,
      praatMetrics: result.metrics,
      analysisVersion: "stable_v1",
      serverVerified: result.verified,
      serverRecordId: result.audioRecordId,
      audioUrl: result.audioUrl,
    });

    dispatch({ type: "studentRecordingCompleted", recordingId: currentTurn.id });
  };

  const handleRecord = async () => {
    await handleAnalysisResult(await recorder.startRecording());
  };

  const handleUpload = async (file: File) => {
    await handleAnalysisResult(await recorder.uploadRecording(file));
  };

  const submitSelfEvaluation = async (skip: boolean) => {
    if (selfEvalCommitRef.current) return;
    selfEvalCommitRef.current = true;
    if (!selfEvalSaved && lastSubmission) {
      const finalSubmission: SceneSubmission = skip
        ? lastSubmission
        : {
            ...lastSubmission,
            selfEvalContent: selfEvalMeaning ?? undefined,
            selfEvalPronunciation: selfEvalPronunciation ?? undefined,
          };
      setLastSubmission(finalSubmission);
      setSelfEvalSaved(true);
      onSceneSubmission(`conversation:${state.turnIndex}`, finalSubmission);
      dispatch(skip ? { type: "selfEvaluationSkipped" } : { type: "selfEvaluationSubmitted" });
      if (studentId) {
        try {
          await saveSpeakingProgress({
            studentId,
            topicId: topic.id,
            sceneIndex: currentTurn?.sceneIndex ?? 0,
            attempts: 1,
            bestTone: finalSubmission.toneAccuracy,
            bestFluency: finalSubmission.fluencyScore ?? 0,
            masteryPassed: lastResult?.masteryPassed ?? false,
            contentPassed: lastResult?.contentPassed ?? false,
            clearedWords: finalSubmission.vocabUsed,
            conversationId: conversationIdRef.current,
            turnId: currentTurn?.id,
            turnIndex: state.turnIndex,
            latestResult: finalSubmission,
            baseStoryId: finalSubmission.baseStoryId,
            difficultyLevel: finalSubmission.difficultyLevel,
            promptId: finalSubmission.promptId,
          });
        } catch {
          // Feedback remains usable when progress persistence is unavailable.
        }
      }
    }
    if (!lastSubmission) {
      dispatch(skip ? { type: "selfEvaluationSkipped" } : { type: "selfEvaluationSubmitted" });
    }
  };

  const recordAgain = () => {
    setLastAnalysis(null);
    setLastResult(null);
    setLastRecognizedText("");
    setLastSubmission(null);
    setSelfEvalMeaning(null);
    setSelfEvalPronunciation(null);
    setSelfEvalSaved(false);
    selfEvalCommitRef.current = false;
    setState((previous) => ({ ...previous, step: "student" }));
  };

  const nextTurn = () => {
    setLastAnalysis(null);
    setLastResult(null);
    setLastRecognizedText("");
    setLastSubmission(null);
    setSelfEvalMeaning(null);
    setSelfEvalPronunciation(null);
    setSelfEvalSaved(false);
    selfEvalCommitRef.current = false;
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
    lastSubmission,
    selfEvalMeaning,
    selfEvalPronunciation,
    recorder,
    exchange,
    handleListen,
    handleRecord,
    handleUpload,
    submitSelfEvaluation,
    setSelfEvalMeaning,
    setSelfEvalPronunciation,
    recordAgain,
    nextTurn,
  };
}
