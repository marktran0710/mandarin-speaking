import { useCallback, useEffect, useRef, useState } from "react";
import type { PraatMetrics } from "../../../components/story-recorder/StoryRecorder";
import { convertBlobToWav } from "../../../utils/audio";
import { buildPracticeAnalysisFormData, type PracticeAnalysisRequestContext } from "../../../utils/practiceAnalysis";
import { formatBackendError, getBackendUrl, readErrorResponse } from "../../../utils/storyRecorderFeedback";
import { getStudentId } from "../../../utils/studentSession";

/**
 * Shared recording + backend-analysis lifecycle for Story Speaking and
 * Conversation Practice. Extracted from what used to be inline in the
 * deleted SpeakingConversationFlow.tsx (git history: components/story-
 * recorder/SpeakingConversationFlow.tsx before this rewrite) so both new
 * screens call the exact same getUserMedia -> MediaRecorder -> WAV ->
 * /api/analyze pipeline instead of two divergent reimplementations. Owns
 * nothing about what happens with a result — the caller decides how to
 * persist/route it.
 */
export interface SpeakingAnalysisResult {
  metrics: PraatMetrics & { analysis_version?: string; progression_eligible?: boolean };
  audioBlob: Blob;
  audioUrl?: string;
  audioRecordId?: string;
  masteryPassed: boolean;
  contentPassed: boolean;
  verified: boolean;
}

const MAX_RECORDING_SECONDS = 30;

export function useSpeakingRecorder(buildContext: (attemptNumber: number) => PracticeAnalysisRequestContext) {
  const [isRecording, setIsRecording] = useState(false);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [recordingDuration, setRecordingDuration] = useState(0);
  const [attemptNumber, setAttemptNumber] = useState(0);

  const streamRef = useRef<MediaStream | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const recordingStartedAtRef = useRef<number | null>(null);
  const durationTimerRef = useRef<number | null>(null);
  const analysisInFlightRef = useRef(false);
  const resolveRef = useRef<((result: SpeakingAnalysisResult | null) => void) | null>(null);

  const clearTimers = useCallback(() => {
    if (durationTimerRef.current !== null) {
      window.clearInterval(durationTimerRef.current);
      durationTimerRef.current = null;
    }
  }, []);

  const stopStream = useCallback(() => {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
  }, []);

  useEffect(() => () => { clearTimers(); stopStream(); }, [clearTimers, stopStream]);

  const analyzeRecording = useCallback(async (audioBlob: Blob, nextAttemptNumber: number) => {
    if (analysisInFlightRef.current) return;
    analysisInFlightRef.current = true;
    setIsAnalyzing(true);
    setError(null);
    try {
      const wav = await convertBlobToWav(audioBlob);
      const context = buildContext(nextAttemptNumber);
      const formData = buildPracticeAnalysisFormData(wav, {
        ...context,
        participantId: getStudentId(),
        attemptNumber: nextAttemptNumber,
        attemptType: nextAttemptNumber === 1 ? "WHOLE_SENTENCE_INITIAL" : "WHOLE_SENTENCE_FINAL",
      });
      const verified = Boolean(getStudentId());
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
      const metrics = (verified ? payload.analysis : payload) as PraatMetrics & {
        analysis_version?: string;
        progression_eligible?: boolean;
      };
      metrics.analysis_version = metrics.analysis_version ?? "stable_v1";
      metrics.progression_eligible = verified ? Boolean(payload.progressionEligible) : true;
      const masteryPassed = verified
        ? Boolean(payload.verdicts?.masteryPassed)
        : metrics.pronunciation_mastery?.passed === true;
      const contentPassed = verified
        ? Boolean(payload.verdicts?.contentPassed)
        : metrics.content_match === true;
      const result: SpeakingAnalysisResult = {
        metrics,
        audioBlob,
        audioUrl: verified && typeof payload.audioUrl === "string" ? payload.audioUrl : undefined,
        audioRecordId: verified ? payload.audioRecordId : undefined,
        masteryPassed,
        contentPassed,
        verified,
      };
      setAttemptNumber(nextAttemptNumber);
      resolveRef.current?.(result);
      return result;
    } catch (cause) {
      setError(formatBackendError(cause, getBackendUrl()));
      resolveRef.current?.(null);
      return null;
    } finally {
      analysisInFlightRef.current = false;
      setIsAnalyzing(false);
      resolveRef.current = null;
    }
  }, [buildContext]);

  const finishRecording = useCallback(() => {
    if (recorderRef.current?.state === "recording") recorderRef.current.stop();
    setIsRecording(false);
    clearTimers();
  }, [clearTimers]);

  /** Starts recording; resolves with the analysis result once the backend
   * responds (or null on failure), so a caller can `await` a full attempt. */
  const startRecording = useCallback((): Promise<SpeakingAnalysisResult | null> => {
    return new Promise((resolve) => {
      if (isRecording || isAnalyzing) {
        resolve(null);
        return;
      }
      resolveRef.current = resolve;
      setError(null);
      chunksRef.current = [];
      recordingStartedAtRef.current = Date.now();
      setRecordingDuration(0);

      navigator.mediaDevices
        .getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } })
        .then((stream) => {
          streamRef.current = stream;
          const mimeType = MediaRecorder.isTypeSupported("audio/webm") ? "audio/webm" : undefined;
          const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
          recorderRef.current = recorder;
          recorder.ondataavailable = (event) => {
            if (event.data.size > 0) chunksRef.current.push(event.data);
          };
          recorder.onstop = () => {
            const blob = new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" });
            stopStream();
            void analyzeRecording(blob, attemptNumber + 1);
          };
          recorder.start();
          setIsRecording(true);
          durationTimerRef.current = window.setInterval(() => {
            const elapsed = Math.floor((Date.now() - (recordingStartedAtRef.current ?? Date.now())) / 1000);
            setRecordingDuration(Math.min(MAX_RECORDING_SECONDS, elapsed));
            if (elapsed >= MAX_RECORDING_SECONDS) finishRecording();
          }, 250);
        })
        .catch(() => {
          setError("Microphone access was denied or unavailable.");
          resolve(null);
        });
    });
  }, [analyzeRecording, attemptNumber, finishRecording, isAnalyzing, isRecording, stopStream]);

  return {
    isRecording,
    isAnalyzing,
    error,
    recordingDuration,
    attemptNumber,
    startRecording,
    stopRecording: finishRecording,
  };
}
