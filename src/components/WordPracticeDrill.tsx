import { type ChangeEvent, useEffect, useRef, useState } from "react";
import { convertBlobToWav } from "../utils/audio";
import { scoreTier, scoreTierLabel } from "../utils/scoreLabels";
import {
  formatBackendError,
  getBackendUrl,
} from "../utils/storyRecorderFeedback";
import type { WordProsody } from "./StoryRecorder";
import { BiLabel } from "./BiLabel";
import MiniContourChart from "./MiniContourChart";

const BACKEND_URL =
  import.meta.env.VITE_BACKEND_URL ||
  (import.meta.env.DEV ? "http://127.0.0.1:8000" : "");

/** Lets a student drill just this one character/word in place, right where its
 * sentence feedback appeared — record it alone as many times as they like and
 * see the chart update, instead of having to re-record the whole sentence to
 * fix one weak syllable. Sends the known token as `transcription`, which makes
 * the backend skip ASR entirely and score the recording directly against this
 * word's real expected tone(s) — so a re-record here is never limited by
 * speech-recognition accuracy. */
export default function WordPracticeDrill({ word }: { word: WordProsody }) {
  const [open, setOpen] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [error, setError] = useState("");
  const [attempts, setAttempts] = useState<WordProsody[]>([]);
  const [latestContentMatch, setLatestContentMatch] = useState<boolean | null>(
    null,
  );

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  useEffect(() => {
    return () => {
      streamRef.current?.getTracks().forEach((track) => track.stop());
    };
  }, []);

  const latest = attempts[attempts.length - 1];
  const previous = attempts[attempts.length - 2];
  const trend =
    latest && previous
      ? Math.round((latest.tone_accuracy ?? 0) - (previous.tone_accuracy ?? 0))
      : undefined;

  const startRecording = async () => {
    setError("");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      chunksRef.current = [];

      const preferredType = MediaRecorder.isTypeSupported("audio/webm")
        ? "audio/webm"
        : "";
      const recorder = new MediaRecorder(
        stream,
        preferredType ? { mimeType: preferredType } : undefined,
      );
      mediaRecorderRef.current = recorder;

      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      };

      recorder.onstop = async () => {
        const rawBlob = new Blob(chunksRef.current, {
          type: recorder.mimeType || "audio/webm",
        });
        stream.getTracks().forEach((track) => track.stop());
        streamRef.current = null;
        await analyzeAttempt(rawBlob);
      };

      recorder.start();
      setIsRecording(true);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "無法使用麥克風 Could not access the microphone.",
      );
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current?.state === "recording") {
      mediaRecorderRef.current.stop();
    }
    setIsRecording(false);
  };

  const analyzeAttempt = async (rawBlob: Blob) => {
    setIsAnalyzing(true);
    try {
      const wavBlob = await convertBlobToWav(rawBlob);
      const formData = new FormData();
      formData.append("file", wavBlob, "word-practice.wav");
      formData.append("transcription", word.token);
      formData.append("verify_word", word.token);
      formData.append("ai_provider", "local");

      const response = await fetch(`${getBackendUrl()}/api/analyze`, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.detail || "Analysis failed.");
      }

      const data = await response.json();
      const segment: WordProsody | undefined = data.word_prosody?.[0];
      if (!segment) {
        setError(
          "沒聽清楚，靠近麥克風、把音拉長一點再試一次。 Didn't catch enough of that — move closer to the mic and hold the sound a little longer.",
        );
        return;
      }
      setLatestContentMatch(data.content_match ?? null);
      setAttempts((prev) => [...prev, segment]);
    } catch (err) {
      setError(
        formatBackendError(err, BACKEND_URL || "the configured backend"),
      );
    } finally {
      setIsAnalyzing(false);
    }
  };

  const handleImportFile = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;

    if (
      !file.type.startsWith("audio/") &&
      !/\.(wav|webm|mp3|m4a|ogg|aac|flac)$/i.test(file.name)
    ) {
      setError(
        `「${file.name}」不是音訊檔。 "${file.name}" isn't an audio file.`,
      );
      return;
    }

    setError("");
    await analyzeAttempt(file);
  };

  return (
    <div className="word-practice-drill">
      <button
        type="button"
        className="word-practice-toggle"
        onClick={() => setOpen((prev) => !prev)}
        aria-expanded={open}
      >
        {open ? (
          <BiLabel zh="關掉單字練習" pinyin="Guāndiào dānzì liànxí" en="Hide word practice" />
        ) : (
          <BiLabel
            zh={`🎙 自己練習「${word.token}」`}
            en={`🎙 Practice "${word.token}" alone`}
          />
        )}
      </button>

      {open && (
        <div className="word-practice-panel">
          <div className="word-practice-controls">
            <button
              type="button"
              className={`btn-mini ${isRecording ? "recording" : ""}`}
              onClick={isRecording ? stopRecording : startRecording}
              disabled={isAnalyzing}
            >
              {isRecording ? (
                <BiLabel zh="停止" pinyin="Tíngzhǐ" en="Stop" />
              ) : attempts.length > 0 ? (
                <BiLabel zh="再錄一次" pinyin="Zài lù yí cì" en="Record again" />
              ) : (
                <BiLabel zh="錄音" pinyin="Lùyīn" en="Record" />
              )}
            </button>
            <label
              className={`btn-mini btn-mini-secondary word-practice-upload-label ${
                isRecording || isAnalyzing ? "disabled" : ""
              }`}
              role="button"
              tabIndex={isRecording || isAnalyzing ? -1 : 0}
            >
              <BiLabel zh="上傳音檔" pinyin="Shàngchuán yīndàng" en="Upload audio" />
              <input
                type="file"
                accept="audio/*,.wav,.webm,.mp3,.m4a,.ogg,.aac,.flac"
                className="word-practice-upload-input"
                onChange={handleImportFile}
                disabled={isRecording || isAnalyzing}
              />
            </label>
            {isAnalyzing && (
              <span className="word-practice-status">
                <BiLabel zh="分析中…" pinyin="Fēnxī zhōng…" en="Analyzing…" />
              </span>
            )}
            {attempts.length > 0 && (
              <span className="word-practice-attempt-count">
                <BiLabel zh="第" pinyin="Dì" en="Try" /> {attempts.length}
              </span>
            )}
          </div>

          {error && <p className="word-practice-error">{error}</p>}

          {latest && !isAnalyzing && (
            <div
              className={`word-practice-result ${scoreTier(latest.tone_accuracy ?? 0)}`}
            >
              {latestContentMatch === false && (
                <p className="word-practice-content-warning">
                  <BiLabel
                    zh={`聽起來不太像「${word.token}」，分數可能不準。`}
                    en={`Didn't sound like "${word.token}" — the score may not be reliable.`}
                  />
                </p>
              )}
              <div
                className="mini-contour"
                aria-label={`Practice attempt pitch for ${word.token}`}
              >
                <MiniContourChart
                  actual={latest.pitch_contour}
                  reference={latest.reference_contour}
                />
              </div>
              <div className="word-practice-result-meta">
                <strong className={`score-tier-text ${scoreTier(latest.tone_accuracy ?? 0)}`}>
                  {scoreTierLabel(scoreTier(latest.tone_accuracy ?? 0)).zh}
                </strong>
                {typeof trend === "number" && trend !== 0 && (
                  <em className={trend > 0 ? "trend-up" : "trend-down"}>
                    {trend > 0 ? "↑" : "↓"} {Math.abs(trend)}%
                  </em>
                )}
              </div>
              <p>{latest.feedback}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
