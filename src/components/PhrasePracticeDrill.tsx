import { type ChangeEvent, useEffect, useRef, useState } from "react";
import { convertBlobToWav } from "../utils/audio";
import { formatBackendError, getBackendUrl } from "../utils/storyRecorderFeedback";
import { toPinyin } from "../utils/pinyin";
import type { WordProsody } from "./StoryRecorder";
import MiniContourChart from "./MiniContourChart";

const BACKEND_URL =
  import.meta.env.VITE_BACKEND_URL ||
  (import.meta.env.DEV ? "http://127.0.0.1:8000" : "");

/** A focused recorder for one meaning-chunk of the model sentence.
 *
 * The target text is deliberately sent as the analysis transcription: this
 * gives Praat the target tones for every character. `verify_word` still asks
 * the backend to run ASR independently, so a learner cannot clear a chunk by
 * making arbitrary sounds with a similar pitch contour.
 */
export default function PhrasePracticeDrill({
  phrase,
  onPass,
}: {
  phrase: string;
  onPass: (phrase: string) => void;
}) {
  const [isRecording, setIsRecording] = useState(false);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<{
    words: WordProsody[];
    contentMatch: boolean | null;
    passed: boolean;
  } | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  useEffect(
    () => () => streamRef.current?.getTracks().forEach((track) => track.stop()),
    [],
  );

  const analyze = async (audio: Blob) => {
    setIsAnalyzing(true);
    setError("");
    try {
      const wav = await convertBlobToWav(audio);
      const formData = new FormData();
      formData.append("file", wav, "phrase-practice.wav");
      formData.append("transcription", phrase);
      formData.append("verify_word", phrase);
      formData.append("scene_vocabulary", phrase);
      formData.append("ai_provider", "local");

      const response = await fetch(`${getBackendUrl()}/api/analyze`, {
        method: "POST",
        body: formData,
      });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.detail || "Phrase analysis failed.");
      }

      const data = await response.json();
      const words: WordProsody[] = data.word_prosody ?? [];
      const passed =
        data.content_match !== false &&
        words.length > 0 &&
        words.every((word) => word.passed === true);
      setResult({ words, contentMatch: data.content_match ?? null, passed });
      if (passed) onPass(phrase);
    } catch (err) {
      setError(formatBackendError(err, BACKEND_URL || "the configured backend"));
    } finally {
      setIsAnalyzing(false);
    }
  };

  const startRecording = async () => {
    setError("");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      chunksRef.current = [];
      const mimeType = MediaRecorder.isTypeSupported("audio/webm") ? "audio/webm" : "";
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      recorderRef.current = recorder;
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      };
      recorder.onstop = async () => {
        const audio = new Blob(chunksRef.current, {
          type: recorder.mimeType || "audio/webm",
        });
        stream.getTracks().forEach((track) => track.stop());
        streamRef.current = null;
        await analyze(audio);
      };
      recorder.start();
      setIsRecording(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not access the microphone.");
    }
  };

  const stopRecording = () => {
    if (recorderRef.current?.state === "recording") recorderRef.current.stop();
    setIsRecording(false);
  };

  const upload = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    if (!file.type.startsWith("audio/") && !/\.(wav|webm|mp3|m4a|ogg|aac|flac)$/i.test(file.name)) {
      setError("Choose an audio file to analyse this phrase.");
      return;
    }
    await analyze(file);
  };

  return (
    <section className="phrase-practice-drill" aria-label={`Practice phrase ${phrase}`}>
      <p className="phrase-practice-target" lang="zh-Hant">{phrase}</p>
      <p className="phrase-practice-pinyin">{toPinyin(phrase)}</p>
      <p className="phrase-practice-instruction">
        Say this part on its own. Every word must match its target pitch shape.
      </p>
      <div className="word-practice-controls">
        <button
          type="button"
          className={`btn-mini ${isRecording ? "recording" : ""}`}
          onClick={isRecording ? stopRecording : startRecording}
          disabled={isAnalyzing}
        >
          {isRecording ? "Stop" : result ? "Record again" : "Record this part"}
        </button>
        <label className={`btn-mini btn-mini-secondary word-practice-upload-label ${isRecording || isAnalyzing ? "disabled" : ""}`}>
          Upload audio
          <input
            className="word-practice-upload-input"
            type="file"
            accept="audio/*,.wav,.webm,.mp3,.m4a,.ogg,.aac,.flac"
            disabled={isRecording || isAnalyzing}
            onChange={upload}
          />
        </label>
        {isAnalyzing && <span className="word-practice-status">Analysing…</span>}
      </div>
      {error && <p className="word-practice-error">{error}</p>}
      {result && !isAnalyzing && (
        <div className={`phrase-practice-result ${result.passed ? "is-passed" : "is-failed"}`}>
          <p className="phrase-practice-verdict">
            {result.passed
              ? "This part passed. Continue to the next part."
              : "Try this part again. Match every target curve before continuing."}
          </p>
          {result.contentMatch === false && (
            <p className="word-practice-content-warning">
              The recording did not sound like the target phrase, so it cannot pass yet.
            </p>
          )}
          <div className="mini-contour-legend phrase-practice-legend" aria-hidden="true">
            <span className="mini-contour-legend-actual">Your pitch</span>
            <span className="mini-contour-legend-reference">Target pitch</span>
          </div>
          <div className="phrase-practice-word-results">
            {result.words.map((word, index) => (
              <div className={`phrase-practice-word ${word.passed ? "is-passed" : "is-failed"}`} key={`${word.token}-${index}`}>
                <div>
                  <strong>{word.token}</strong>
                  <span>{toPinyin(word.token)}</span>
                </div>
                <MiniContourChart
                  actual={word.pitch_contour}
                  reference={word.reference_contour}
                  userCurve={word.user_curve}
                  targetCurve={word.target_curve}
                />
                <small>{word.passed ? "Passed" : "Needs work"}</small>
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
