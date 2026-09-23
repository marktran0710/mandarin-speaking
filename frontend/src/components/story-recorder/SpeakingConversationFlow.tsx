import { useCallback, useEffect, useMemo, useRef, useState, type ChangeEvent } from "react";
import ConversationTurnCard from "./ConversationTurnCard";
import ConversationTurnProgress from "./ConversationTurnProgress";
import SpeakingFlowCard from "../speaking-flow-card/SpeakingFlowCard";
import { BiLabel } from "../ui/BiLabel";
import type { Topic, SpeechModel } from "./StoryRecorder/storyContent";
import type { ConversationTurn } from "./StoryRecorder/conversation";
import {
  createConversationState,
  currentConversationTurn,
  transitionConversation,
  type ConversationState,
} from "./StoryRecorder/conversationCoordinator";
import type { NewAudioRecord, PraatMetrics } from "./StoryRecorder/types";
import { canUseDatabase, listSpeakingProgress, saveSpeakingProgress, type SceneSubmission } from "../../services/database";
import { convertBlobToWav } from "../../utils/audio";
import { buildPracticeAnalysisFormData } from "../../utils/practiceAnalysis";
import {
  formatBackendError,
  getBackendUrl,
  readErrorResponse,
} from "../../utils/storyRecorderFeedback";
import { resolvePilotContext } from "../../utils/pilotSession";
import { createMeasurementEvent, recordMeasurementEvent } from "../../utils/measurement";
import { getStudentId } from "../../utils/studentSession";
import { buildSceneReferenceCurves } from "./StoryRecorder/storyContent";
import "./SpeakingConversationFlow.css";

const MAX_RECORDING_SECONDS = 30;

interface SpeechRecognitionLike {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  resultIndex: number;
  onresult: ((event: any) => void) | null;
  onerror: ((event: any) => void) | null;
  start: () => void;
  stop: () => void;
}

type SpeechRecognitionConstructor = new () => SpeechRecognitionLike;

type WindowWithSpeechRecognition = Window & {
  SpeechRecognition?: SpeechRecognitionConstructor;
  webkitSpeechRecognition?: SpeechRecognitionConstructor;
};

interface SpeakingConversationFlowProps {
  topic: Topic;
  turns: readonly ConversationTurn[];
  selectedImage: string;
  selectedImageIndex: number;
  onAddRecord: (record: NewAudioRecord) => Promise<string | undefined> | void;
  studentId?: string;
}

function makeConversationId(topicId: string): string {
  return `conversation:${topicId}`;
}

export default function SpeakingConversationFlow({
  topic,
  turns,
  selectedImage,
  selectedImageIndex,
  onAddRecord,
  studentId,
}: SpeakingConversationFlowProps) {
  const conversationId = useMemo(() => makeConversationId(topic.id), [topic.id]);
  const initialState = useMemo(() => createConversationState(turns), [turns]);
  const [state, setState] = useState<ConversationState>(() => initialState ?? { turnIndex: 0, step: "system" });
  const [metrics, setMetrics] = useState<PraatMetrics | null>(null);
  const [analysisAudioBlob, setAnalysisAudioBlob] = useState<Blob | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedModel, setSelectedModel] = useState<SpeechModel>("webspeech");
  const [groqAvailable, setGroqAvailable] = useState(false);
  const [openaiAvailable, setOpenaiAvailable] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [recordingDuration, setRecordingDuration] = useState(0);
  const [attempts, setAttempts] = useState(0);
  const [latestResult, setLatestResult] = useState<SceneSubmission | null>(null);
  const [progressFlags, setProgressFlags] = useState({ masteryPassed: false, contentPassed: false });
  const [verifiedRecordId, setVerifiedRecordId] = useState<string | undefined>();
  const [pendingUpload, setPendingUpload] = useState<File | null>(null);
  const [pendingUploadUrl, setPendingUploadUrl] = useState("");
  const recorderRef = useRef<MediaRecorder | null>(null);
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const transcriptRef = useRef("");
  const recordingStartedAtRef = useRef<number | null>(null);
  const durationTimerRef = useRef<number | null>(null);
  const analysisInFlightRef = useRef(false);

  const activeTurn = currentConversationTurn(state, turns);
  const studentTurn = state.step === "summary" ? null : turns[state.turnIndex];

  const applyTransition = useCallback((event: Parameters<typeof transitionConversation>[1]) => {
    setState((current) => {
      const result = transitionConversation(current, event, turns);
      return result.accepted ? result.state : current;
    });
  }, [turns]);

  useEffect(() => {
    setState(initialState ?? { turnIndex: 0, step: "system" });
    setMetrics(null);
    setAnalysisAudioBlob(null);
    setError(null);
    setAttempts(0);
    setLatestResult(null);
    setProgressFlags({ masteryPassed: false, contentPassed: false });
    setVerifiedRecordId(undefined);
  }, [initialState, topic.id]);

  // Epic 9: resume at the next incomplete exchange rather than always
  // restarting at turn 0 - a refresh or reopen must not lose progress
  // already saved via persistProgress's conversationId/turnId/turnIndex.
  useEffect(() => {
    if (!studentId || !canUseDatabase() || !initialState) return;
    let cancelled = false;
    listSpeakingProgress(studentId, topic.id)
      .then((records) => {
        if (cancelled) return;
        const completedTurnIndexes = records
          .filter((record) => record.conversationId === conversationId && typeof record.turnIndex === "number")
          .map((record) => record.turnIndex as number);
        if (completedTurnIndexes.length === 0) return;
        const nextTurnIndex = Math.max(...completedTurnIndexes) + 1;
        setState(
          nextTurnIndex >= turns.length
            ? { turnIndex: turns.length, step: "summary" }
            : { turnIndex: nextTurnIndex, step: "system" },
        );
      })
      .catch(() => undefined);
    return () => { cancelled = true; };
  }, [studentId, topic.id, conversationId, initialState, turns.length]);

  useEffect(() => {
    let active = true;
    void fetch(`${getBackendUrl()}/api/ai-providers`)
      .then((response) => response.ok ? response.json() : null)
      .then((data: { providers?: Array<{ id: string; available: boolean }>; default?: string } | null) => {
        if (!active || !Array.isArray(data?.providers)) return;
        setGroqAvailable(Boolean(data.providers.find((provider) => provider.id === "groq" && provider.available)));
        setOpenaiAvailable(Boolean(data.providers.find((provider) => provider.id === "openai" && provider.available)));
        const preferred = data.providers.find((provider) => provider.available)?.id;
        if (preferred === "groq" || preferred === "openai") setSelectedModel(preferred);
      })
      .catch(() => undefined);
    return () => { active = false; };
  }, []);

  const stopStream = useCallback(() => {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
  }, []);

  const clearTimers = useCallback(() => {
    if (durationTimerRef.current !== null) window.clearInterval(durationTimerRef.current);
    durationTimerRef.current = null;
  }, []);

  useEffect(() => () => {
    recognitionRef.current?.stop();
    recorderRef.current?.stop();
    stopStream();
    clearTimers();
    if (pendingUploadUrl) URL.revokeObjectURL(pendingUploadUrl);
  }, [clearTimers, pendingUploadUrl, stopStream]);

  const persistProgress = useCallback(async (
    result: SceneSubmission,
    flags: {
      masteryPassed: boolean;
      contentPassed: boolean;
      attempts: number;
      verifiedAudioRecordId?: string;
    },
  ) => {
    if (!studentId || !canUseDatabase()) return;
    try {
      await saveSpeakingProgress({
        studentId,
        topicId: topic.id,
        sceneIndex: result.sceneIndex,
        attempts: flags.attempts,
        bestTone: result.toneAccuracy,
        bestFluency: result.fluencyScore ?? 0,
        masteryPassed: flags.masteryPassed,
        contentPassed: flags.contentPassed,
        clearedWords: [],
        conversationId: result.conversationId,
        turnId: result.turnId,
        turnIndex: result.turnIndex,
        latestResult: result,
        baseStoryId: topic.sourceStory?.id ?? topic.id,
        difficultyLevel: topic.difficultyLevel ?? "easy",
        promptId: `${topic.sourceStory?.id ?? topic.id}:conversation:${result.turnId}`,
        verifiedAudioRecordId: flags.verifiedAudioRecordId,
      });
    } catch (cause) {
      console.warn("Failed to save conversation progress:", cause);
    }
  }, [studentId, topic]);

  const analyzeRecording = useCallback(async (audioBlob: Blob, transcript: string, model: SpeechModel) => {
    if (analysisInFlightRef.current || !studentTurn || studentTurn.speaker !== "student") return;
    analysisInFlightRef.current = true;
    setIsAnalyzing(true);
    setError(null);
    const attemptNumber = attempts + 1;
    const attemptId = `conversation-attempt-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    const pilot = resolvePilotContext();
    const targetText = studentTurn.targetText?.trim() || studentTurn.text;
    const aiProvider = selectedModel === "groq" || selectedModel === "openai"
      ? selectedModel
      : groqAvailable
        ? "groq"
        : openaiAvailable
          ? "openai"
          : undefined;
    try {
      const wav = await convertBlobToWav(audioBlob);
      const formData = buildPracticeAnalysisFormData(wav, {
        transcription: transcript,
        asrModel: model,
        aiProvider,
        sceneVocabulary: (topic.vocabulary[selectedImageIndex] || []).join(", "),
        scenePrompt: topic.prompts?.[selectedImageIndex] || topic.name,
        sceneImageUrl: selectedImage,
        scenePhrases: topic.phrases?.[selectedImageIndex]?.join("; "),
        sceneSuggestedAnswer: topic.suggestedAnswers?.[selectedImageIndex],
        sceneTargetText: targetText,
        sceneReferenceCurves: buildSceneReferenceCurves(topic, selectedImageIndex),
        participantId: getStudentId(),
        itemId: `${topic.id}:${studentTurn.id}`,
        sessionId: pilot.sessionId,
        attemptId,
        attemptNumber,
        attemptType: attemptNumber === 1 ? "WHOLE_SENTENCE_INITIAL" : "WHOLE_SENTENCE_FINAL",
        studyPhase: pilot.studyPhase,
        conversationId,
        turnId: studentTurn.id,
        turnIndex: state.turnIndex,
      });
      const verified = Boolean(studentId);
      if (verified) {
        formData.append("base_story_id", topic.sourceStory?.id ?? topic.id);
        formData.append("scene_index", String(selectedImageIndex));
        formData.append("difficulty_level", topic.difficultyLevel ?? "easy");
      }
      const response = await fetch(`${getBackendUrl()}${verified ? "/api/analyze/verified" : "/api/analyze"}`, {
        method: "POST",
        body: formData,
        signal: AbortSignal.timeout(120_000),
      });
      if (!response.ok) {
        const body = await readErrorResponse(response);
        throw new Error(body.detail || "Speech analysis failed.");
      }
      const payload = await response.json();
      const analysis = (verified ? payload.analysis : payload) as PraatMetrics & { analysis_version?: string };
      analysis.analysis_version = analysis.analysis_version ?? "stable_v1";
      analysis.progression_eligible = verified ? Boolean(payload.progressionEligible) : true;
      analysis.learning_context = {
        baseStoryId: topic.sourceStory?.id ?? topic.id,
        difficultyLevel: topic.difficultyLevel ?? "easy",
        sceneIndex: selectedImageIndex,
        promptId: `${topic.sourceStory?.id ?? topic.id}:conversation:${studentTurn.id}`,
      };
      setMetrics(analysis);
      setAnalysisAudioBlob(audioBlob);
      setAttempts(attemptNumber);
      const masteryPassed = verified
        ? Boolean(payload.verdicts?.masteryPassed)
        : analysis.pronunciation_mastery?.passed === true;
      const contentPassed = verified
        ? Boolean(payload.verdicts?.contentPassed)
        : analysis.content_match === true;
      setProgressFlags({ masteryPassed, contentPassed });
      const responseAudioUrl = verified && typeof payload.audioUrl === "string"
        ? payload.audioUrl
        : undefined;
      setVerifiedRecordId(verified ? payload.audioRecordId : undefined);
      recordMeasurementEvent(createMeasurementEvent("analysis_completed", {
        studentId: studentId ?? getStudentId(),
        sessionId: pilot.sessionId,
        attemptId,
        topicId: topic.id,
        sceneIndex: selectedImageIndex,
        properties: { conversationId, turnId: studentTurn.id, analysisVersion: "stable_v1" },
      }));
      const savedAudioUrl = await onAddRecord({
        id: `audio-${Date.now()}`,
        audioBlob,
        timestamp: new Date().toLocaleString(),
        duration: Math.max(1, Math.floor((Date.now() - (recordingStartedAtRef.current ?? Date.now())) / 1000)),
        transcription: (analysis.transcription || transcript).trim(),
        model,
        topicId: topic.id,
        imageUrl: selectedImage,
        imageIndex: selectedImageIndex,
        conversationId,
        turnId: studentTurn.id,
        turnIndex: state.turnIndex,
        praatMetrics: analysis,
        analysisVersion: "stable_v1",
        analysisSchemaVersion: analysis.analysis_schema_version,
        modelVersion: analysis.model_version,
        sessionId: pilot.sessionId,
        attemptId,
        attemptNumber,
        attemptType: attemptNumber === 1 ? "WHOLE_SENTENCE_INITIAL" : "WHOLE_SENTENCE_FINAL",
        serverVerified: verified,
        serverRecordId: verified ? payload.audioRecordId : undefined,
        audioUrl: responseAudioUrl,
      });
      const result: SceneSubmission = {
        sceneIndex: selectedImageIndex,
        imageUrl: selectedImage,
        transcription: (analysis.transcription || transcript).trim(),
        vocabUsed: analysis.ai_feedback?.vocabulary_coverage?.used ?? [],
        vocabMissing: analysis.ai_feedback?.vocabulary_coverage?.missing ?? [],
        vocabScore: analysis.ai_feedback?.vocabulary_coverage?.score ?? 0,
        toneAccuracy: Math.round(analysis.tone_accuracy ?? 0),
        pronScore: Math.round(analysis.tone_accuracy ?? 0),
        fluencyScore: Math.round(analysis.fluency_score ?? 0),
        audioUrl: responseAudioUrl ?? savedAudioUrl,
        pauseCount: analysis.pause_analysis?.pause_count ?? 0,
        longestPause: analysis.pause_analysis?.longest_pause ?? 0,
        utteranceCount: analysis.pause_analysis?.utterance_count ?? 0,
        choppyPauseCount: analysis.pause_analysis?.choppy_pause_count ?? 0,
        articulationRate: analysis.pause_analysis?.articulation_rate ?? 0,
        conversationId,
        turnId: studentTurn.id,
        turnIndex: state.turnIndex,
        baseStoryId: topic.sourceStory?.id ?? topic.id,
        difficultyLevel: topic.difficultyLevel ?? "easy",
        promptId: `${topic.sourceStory?.id ?? topic.id}:conversation:${studentTurn.id}`,
      };
      setLatestResult(result);
      await persistProgress(result, {
        masteryPassed,
        contentPassed,
        attempts: attemptNumber,
        verifiedAudioRecordId: verified ? payload.audioRecordId : undefined,
      });
      applyTransition({ type: "studentRecordingCompleted", recordingId: studentTurn.id });
    } catch (cause) {
      setError(formatBackendError(cause, getBackendUrl()));
    } finally {
      analysisInFlightRef.current = false;
      setIsAnalyzing(false);
      setIsTranscribing(false);
    }
  }, [applyTransition, attempts, conversationId, groqAvailable, onAddRecord, openaiAvailable, persistProgress, selectedImage, selectedImageIndex, selectedModel, state.turnIndex, studentId, studentTurn, topic]);

  const finishRecording = useCallback(() => {
    recognitionRef.current?.stop();
    recognitionRef.current = null;
    if (recorderRef.current?.state === "recording") recorderRef.current.stop();
    setIsRecording(false);
    clearTimers();
  }, [clearTimers]);

  const startRecording = useCallback(async () => {
    if (state.step !== "student" || isRecording || isAnalyzing) return;
    setError(null);
    chunksRef.current = [];
    transcriptRef.current = "";
    recordingStartedAtRef.current = Date.now();
    setRecordingDuration(0);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
      streamRef.current = stream;
      const mimeType = MediaRecorder.isTypeSupported("audio/webm") ? "audio/webm" : undefined;
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      recorderRef.current = recorder;
      recorder.ondataavailable = (event) => { if (event.data.size > 0) chunksRef.current.push(event.data); };
      recorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" });
        stopStream();
        void analyzeRecording(blob, transcriptRef.current, selectedModel);
      };
      recorder.start();
      setIsRecording(true);
      durationTimerRef.current = window.setInterval(() => {
        const elapsed = Math.floor((Date.now() - (recordingStartedAtRef.current ?? Date.now())) / 1000);
        setRecordingDuration(Math.min(MAX_RECORDING_SECONDS, elapsed));
        if (elapsed >= MAX_RECORDING_SECONDS) finishRecording();
      }, 250);
      const Recognition = (window as WindowWithSpeechRecognition).SpeechRecognition
        || (window as WindowWithSpeechRecognition).webkitSpeechRecognition;
      if (Recognition) {
        const recognition = new Recognition();
        recognition.continuous = true;
        recognition.interimResults = true;
        recognition.lang = "zh-TW";
        recognition.onresult = (event) => {
          let next = "";
          for (let index = event.resultIndex; index < event.results.length; index += 1) next += ` ${event.results[index][0].transcript}`;
          transcriptRef.current = `${transcriptRef.current} ${next}`.trim();
        };
        recognition.onerror = (event) => {
          if (!['network', 'no-speech', 'aborted'].includes(event.error)) setError(`Speech recognition error: ${event.error}`);
        };
        recognitionRef.current = recognition;
        recognition.start();
      }
    } catch (cause) {
      stopStream();
      clearTimers();
      setError(cause instanceof Error ? cause.message : "Failed to access microphone.");
    }
  }, [analyzeRecording, clearTimers, finishRecording, isAnalyzing, isRecording, selectedModel, state.step, stopStream]);

  const submitVoiceFile = useCallback((event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    if (!file.type.startsWith("audio/")) {
      setError("Submit an audio file.");
      return;
    }
    setPendingUpload(file);
    setPendingUploadUrl(URL.createObjectURL(file));
  }, []);

  const clearPendingUpload = useCallback(() => {
    if (pendingUploadUrl) URL.revokeObjectURL(pendingUploadUrl);
    setPendingUpload(null);
    setPendingUploadUrl("");
  }, [pendingUploadUrl]);

  const analyzePendingUpload = useCallback(() => {
    if (!pendingUpload) return;
    const file = pendingUpload;
    clearPendingUpload();
    void analyzeRecording(file, "", selectedModel);
  }, [analyzeRecording, clearPendingUpload, pendingUpload, selectedModel]);

  const handleSelfEvalSubmit = useCallback((levels: { content: "good" | "ok" | "bad"; pronunciation: "good" | "ok" | "bad" }) => {
    if (latestResult) {
      const enriched = {
        ...latestResult,
        selfEvalContent: levels.content,
        selfEvalPronunciation: levels.pronunciation,
      } satisfies SceneSubmission;
      setLatestResult(enriched);
      void persistProgress(enriched, {
        masteryPassed: progressFlags.masteryPassed,
        contentPassed: progressFlags.contentPassed,
        attempts,
        verifiedAudioRecordId: verifiedRecordId,
      });
    }
    applyTransition({ type: "selfEvaluationSubmitted" });
  }, [applyTransition, attempts, latestResult, persistProgress, progressFlags, verifiedRecordId]);

  const handleSelfEvalSkip = useCallback(() => {
    if (latestResult) {
      void persistProgress(latestResult, {
        masteryPassed: progressFlags.masteryPassed,
        contentPassed: progressFlags.contentPassed,
        attempts,
        verifiedAudioRecordId: verifiedRecordId,
      });
    }
    applyTransition({ type: "selfEvaluationSkipped" });
  }, [applyTransition, attempts, latestResult, persistProgress, progressFlags, verifiedRecordId]);
  const handleAdvance = useCallback(() => applyTransition({ type: "feedbackCompleted" }), [applyTransition]);

  if (state.step === "summary") {
    return <section className="speaking-conversation-flow conversation-summary" aria-label="Conversation summary">
      <ConversationTurnProgress turns={turns} state={state} />
      <div className="conversation-summary__body">
        <p className="conversation-summary__kicker"><BiLabel zh="對話完成" en="Conversation complete" /></p>
        <h2>Nice work. You completed every response.</h2>
        <p>Review the recordings above in your progress history whenever you want to practise again.</p>
      </div>
    </section>;
  }

  if (!activeTurn) return null;

  const isStudentTurn = activeTurn.speaker === "student";
  const currentStudentTurn = isStudentTurn ? activeTurn : studentTurn;
  const responseCard = currentStudentTurn && currentStudentTurn.speaker === "student" ? (
    <SpeakingFlowCard
      selectedImage={selectedImage}
      selectedImageIndex={selectedImageIndex}
      totalScenes={turns.length}
      modelSentence={currentStudentTurn.targetText || currentStudentTurn.text}
      // The student's own optional model-response recording - never the
      // character's line (previousSystemTurn.audioUrl), which is a
      // different speaker saying a different sentence.
      modelAudioUrl={currentStudentTurn.targetAudioUrl}
      promptMode="external"
      prog={{ attempts, bestTone: Math.round(metrics?.tone_accuracy ?? 0), bestFluency: Math.round(metrics?.fluency_score ?? 0) }}
      praatMetrics={metrics}
      analysisAudioBlob={analysisAudioBlob}
      error={error}
      isRecording={isRecording}
      isBusy={isRecording || isTranscribing || isAnalyzing}
      isTranscribing={isTranscribing}
      isAnalyzing={isAnalyzing}
      recordingDuration={recordingDuration}
      silenceDuration={0}
      selectedModel={selectedModel}
      groqAvailable={groqAvailable}
      openaiAvailable={openaiAvailable}
      onSelectedModelChange={setSelectedModel}
      recordingButtonDisabled={state.step !== "student" || isAnalyzing || isTranscribing}
      onPrimaryRecordingAction={isRecording ? finishRecording : startRecording}
      onSubmitVoiceFile={submitVoiceFile}
      pendingUploadName={pendingUpload?.name}
      pendingUploadUrl={pendingUploadUrl}
      onAnalyzePendingUpload={analyzePendingUpload}
      onClearPendingUpload={clearPendingUpload}
      masteryPassed={progressFlags.masteryPassed}
      contentPassed={progressFlags.contentPassed}
      // Non-blocking by design (feedback informs but doesn't gate the next
      // exchange) - unlike masteryPassed/contentPassed above, this one is
      // deliberately not tied to the real verdict, per the product's
      // existing continuation policy.
      sceneReadyOverride
      clearedWords={[]}
      onWordDrillPass={() => undefined}
      onSelfEvalSubmit={handleSelfEvalSubmit}
      onSelfEvalSkip={handleSelfEvalSkip}
      hasNextScene={state.turnIndex + 1 < turns.length}
      onNextScene={handleAdvance}
      onViewSummary={handleAdvance}
    />
  ) : null;

  return <section className="speaking-conversation-flow" aria-label="Conversation practice">
    <ConversationTurnProgress turns={turns} state={state} />
    {isStudentTurn ? (
      <ConversationTurnCard
        turn={activeTurn}
        responseFeedback={{ praatMetrics: metrics, revealed: state.step === "feedback" }}
      >
        {responseCard}
      </ConversationTurnCard>
    ) : (
      <ConversationTurnCard turn={activeTurn} onSystemComplete={() => applyTransition({ type: "systemAudioCompleted" })} />
    )}
  </section>;
}
