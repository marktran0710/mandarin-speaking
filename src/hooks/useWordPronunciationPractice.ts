import { useEffect, useRef, useState } from "react";
import { convertBlobToWav } from "../utils/audio";

const BACKEND_URL =
  import.meta.env.VITE_BACKEND_URL ||
  (import.meta.env.DEV ? "http://127.0.0.1:8000" : "");

export interface WordProsodySegment {
  token: string;
  pitch_contour: Array<[number, number]>;
  reference_contour?: Array<[number, number]>;
  tone_accuracy: number;
  feedback: string;
}

export interface WordAnalyzeResult {
  tone_accuracy: number;
  feedback: string;
  word_prosody: WordProsodySegment[];
}

/**
 * Records (or accepts an uploaded file for) a single word/phrase and scores
 * it against that word's expected tone shape. Forces `transcription` to the
 * target word so the backend skips ASR and compares Praat's pitch extraction
 * directly against the word's real tone(s) via pypinyin.
 *
 * Shared by TonePracticePage (general word-bank practice) and the inline
 * per-word practice affordance on a story scene's vocabulary table.
 */
export function useWordPronunciationPractice(word: string) {
  const [isRecording, setIsRecording] = useState(false);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<WordAnalyzeResult | null>(null);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  useEffect(() => {
    return () => {
      streamRef.current?.getTracks().forEach((track) => track.stop());
    };
  }, []);

  const reset = () => {
    setResult(null);
    setError("");
  };

  const analyzeBlob = async (rawBlob: Blob): Promise<WordAnalyzeResult | null> => {
    setIsAnalyzing(true);
    try {
      const wavBlob = await convertBlobToWav(rawBlob);
      const formData = new FormData();
      formData.append("file", wavBlob, "word-practice.wav");
      formData.append("transcription", word);
      formData.append("ai_provider", "local");

      const response = await fetch(`${getBackendUrl()}/api/analyze`, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.detail || "Analysis failed.");
      }

      const data = (await response.json()) as WordAnalyzeResult;
      setResult(data);
      return data;
    } catch (err) {
      setError(formatBackendError(err));
      return null;
    } finally {
      setIsAnalyzing(false);
    }
  };

  const startRecording = async () => {
    setError("");
    setResult(null);

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      chunksRef.current = [];

      const preferredType = MediaRecorder.isTypeSupported("audio/webm") ? "audio/webm" : "";
      const recorder = new MediaRecorder(
        stream,
        preferredType ? { mimeType: preferredType } : undefined,
      );
      mediaRecorderRef.current = recorder;

      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          chunksRef.current.push(event.data);
        }
      };

      recorder.onstop = async () => {
        const rawBlob = new Blob(chunksRef.current, {
          type: recorder.mimeType || "audio/webm",
        });
        stream.getTracks().forEach((track) => track.stop());
        streamRef.current = null;
        await analyzeBlob(rawBlob);
      };

      recorder.start();
      setIsRecording(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not access the microphone.");
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current?.state === "recording") {
      mediaRecorderRef.current.stop();
    }
    setIsRecording(false);
  };

  return {
    isRecording,
    isAnalyzing,
    error,
    setError,
    result,
    startRecording,
    stopRecording,
    analyzeBlob,
    reset,
  };
}

function getBackendUrl(): string {
  if (BACKEND_URL) {
    return BACKEND_URL;
  }
  throw new Error("Word practice needs a deployed backend. Set VITE_BACKEND_URL.");
}

function formatBackendError(error: unknown): string {
  const message = error instanceof Error ? error.message : String(error);
  const networkFailures = ["Failed to fetch", "NetworkError", "Load failed"];
  if (networkFailures.some((failure) => message.includes(failure))) {
    return `Cannot reach the speech analysis backend${BACKEND_URL ? ` at ${BACKEND_URL}` : ""}. Start the backend and try again.`;
  }
  return message || "Something went wrong analyzing that recording.";
}
