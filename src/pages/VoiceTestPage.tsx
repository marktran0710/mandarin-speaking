import { type ChangeEvent, useRef, useState } from "react";
import PraatTimeline from "../components/PraatTimeline";
import { convertBlobToWav } from "../utils/audio";
import "./VoiceTestPage.css";

const BACKEND_URL =
  import.meta.env.VITE_BACKEND_URL ||
  (import.meta.env.DEV ? "http://127.0.0.1:8000" : "");
const VOICE_TEST_ASR_MODEL = import.meta.env.VITE_VOICE_TEST_ASR_MODEL || "ctwhisper";

interface WordProsody {
  token: string;
  index: number;
  start_time?: number;
  end_time?: number;
  pitch_contour?: Array<[number, number]>;
  reference_contour?: Array<[number, number]>;
  mean_pitch: number;
  pitch_range: number;
  start_pitch?: number;
  end_pitch?: number;
  contour_shape: string;
  feedback: string;
}

interface VoiceMetrics {
  description?: string;
  transcription?: string;
  transcription_model?: string;
  pitch_contour: Array<[number, number]>;
  word_prosody?: WordProsody[];
  detected_tone: number;
  tone_accuracy: number;
  speech_rate: number;
  fluency_score: number;
  feedback: string;
  ai_feedback?: {
    provider: string;
    fluency: { score: number; feedback: string };
    grammar: { score: number; feedback: string; corrections: string[] };
    vocabulary: { score: number; feedback: string; suggestions: string[] };
    improved_version: string;
    practice_prompt: string;
  };
}

export default function VoiceTestPage() {
  const [isRecording, setIsRecording] = useState(false);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [error, setError] = useState("");
  const [metrics, setMetrics] = useState<VoiceMetrics | null>(null);
  const [recordingDuration, setRecordingDuration] = useState(0);
  const [audioUrl, setAudioUrl] = useState("");
  const [audioBlob, setAudioBlob] = useState<Blob | null>(null);
  const [selectedAudioName, setSelectedAudioName] = useState("");
  const [liveTranscript, setLiveTranscript] = useState("");

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const recognitionRef = useRef<any>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const transcriptRef = useRef("");
  const startTimeRef = useRef(0);
  const durationTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const startRecording = async () => {
    setError("");
    setMetrics(null);
    setAudioUrl("");
    setAudioBlob(null);
    setSelectedAudioName("");
    setLiveTranscript("");
    transcriptRef.current = "";
    setRecordingDuration(0);

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
        if (event.data.size > 0) {
          chunksRef.current.push(event.data);
        }
      };

      recorder.onstop = async () => {
        const rawBlob = new Blob(chunksRef.current, {
          type: recorder.mimeType || "audio/webm",
        });
        stopTracks();
        await analyzeAudio(
          rawBlob,
          "voice-test.wav",
          true,
          transcriptRef.current.trim(),
        );
      };

      startTimeRef.current = Date.now();
      durationTimerRef.current = setInterval(() => {
        setRecordingDuration(Math.floor((Date.now() - startTimeRef.current) / 1000));
      }, 250);

      recorder.start();
      startSpeechRecognition();
      setIsRecording(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not access microphone.");
      stopTracks();
      clearDurationTimer();
    }
  };

  const stopRecording = () => {
    recognitionRef.current?.stop();
    if (mediaRecorderRef.current?.state === "recording") {
      mediaRecorderRef.current.stop();
    }
    setIsRecording(false);
    clearDurationTimer();
  };

  const handleImportWav = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";

    if (!file) {
      return;
    }

    const isWav =
      file.type === "audio/wav" ||
      file.type === "audio/wave" ||
      file.type === "audio/x-wav" ||
      file.type === "audio/vnd.wave" ||
      file.name.toLowerCase().endsWith(".wav");

    if (!isWav) {
      setError(`Import a WAV file. "${file.name}" is not supported yet.`);
      return;
    }

    setError("");
    setMetrics(null);
    setRecordingDuration(0);
    setSelectedAudioName(file.name);
    await analyzeAudio(file, normalizeWavFileName(file.name), false);
  };

  const startSpeechRecognition = () => {
    const SpeechRecognition =
      (window as any).SpeechRecognition ||
      (window as any).webkitSpeechRecognition;

    if (!SpeechRecognition) {
      setLiveTranscript("Browser speech transcription is not available.");
      return;
    }

    const recognition = new SpeechRecognition();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = "zh-TW";

    recognition.onresult = (event: any) => {
      let finalText = transcriptRef.current;
      let interimText = "";

      for (let index = event.resultIndex; index < event.results.length; index += 1) {
        const text = event.results[index][0].transcript;
        if (event.results[index].isFinal) {
          finalText = `${finalText} ${text}`.trim();
        } else {
          interimText = `${interimText} ${text}`.trim();
        }
      }

      transcriptRef.current = finalText;
      setLiveTranscript([finalText, interimText].filter(Boolean).join(" "));
    };

    recognition.onerror = () => {
      setLiveTranscript(
        transcriptRef.current ||
          "Browser speech transcription stopped. Praat will still analyze the audio.",
      );
    };

    recognitionRef.current = recognition;
    recognition.start();
  };

  const analyzeAudio = async (
    rawBlob: Blob,
    fileName = "voice-test.wav",
    shouldConvertToWav = true,
    transcription = "",
  ) => {
    setIsAnalyzing(true);
    try {
      const wavBlob = shouldConvertToWav ? await convertBlobToWav(rawBlob) : rawBlob;
      const normalizedWavBlob = ensureWavBlob(wavBlob);
      setAudioBlob(normalizedWavBlob);
      setAudioUrl(URL.createObjectURL(normalizedWavBlob));

      const formData = new FormData();
      formData.append("file", normalizedWavBlob, fileName);
      formData.append("transcription", transcription);
      if (!transcription.trim()) {
        formData.append("asr_model", VOICE_TEST_ASR_MODEL);
      }

      const response = await fetch(`${getBackendUrl()}/api/analyze`, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        const errorData = await readErrorResponse(response);
        throw new Error(errorData.detail || "Voice analysis failed.");
      }

      setMetrics((await response.json()) as VoiceMetrics);
    } catch (err) {
      setError(formatBackendError(err, BACKEND_URL || "the configured backend"));
    } finally {
      setIsAnalyzing(false);
    }
  };

  const clearDurationTimer = () => {
    if (durationTimerRef.current) {
      clearInterval(durationTimerRef.current);
      durationTimerRef.current = null;
    }
  };

  const stopTracks = () => {
    recognitionRef.current = null;
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
  };

  const primaryLabel = isRecording
    ? "Stop and get feedback"
    : metrics
      ? "Record again"
      : "Start voice test";

  return (
    <main className="voice-test-page">
      <section className="voice-test-hero">
        <div>
          <p className="eyebrow">Voice practice</p>
          <h1>Analyze Your Voice</h1>
          <p>
            Record or upload a WAV file. The system transcribes the audio, then
            checks pronunciation and language feedback from the recording.
          </p>
        </div>
        <div className="voice-test-status">
          <span>Status</span>
          <strong>
            {isRecording ? "Recording" : isAnalyzing ? "Analyzing" : "Ready"}
          </strong>
          <p>{isRecording ? `${recordingDuration}s recorded` : "One recording is enough."}</p>
        </div>
      </section>

      <section className="voice-test-workspace">
        <div className="voice-step-row" aria-label="Voice test steps">
          <span>1. Speak or upload</span>
          <span>2. Transcribe audio</span>
          <span>3. Review</span>
        </div>

        <div className="voice-test-controls">
          <button
            type="button"
            className={`btn ${isRecording ? "btn-danger" : "btn-primary"}`}
            onClick={isRecording ? stopRecording : startRecording}
            disabled={isAnalyzing}
          >
            {primaryLabel}
          </button>
          <label
            className={`btn btn-secondary voice-file-label ${
              isRecording || isAnalyzing ? "disabled" : ""
            }`}
            role="button"
            tabIndex={isRecording || isAnalyzing ? -1 : 0}
          >
            Import WAV file
            <input
              className="voice-file-input"
              type="file"
              accept=".wav,audio/wav,audio/wave,audio/x-wav,audio/vnd.wave"
              onChange={handleImportWav}
              disabled={isRecording || isAnalyzing}
            />
          </label>
        </div>

        {audioUrl && (
          <div className="voice-audio-preview">
            <span>Recording preview</span>
            {selectedAudioName && <strong>{selectedAudioName}</strong>}
            <audio controls src={audioUrl} />
          </div>
        )}

        {liveTranscript && (
          <div className="voice-live-transcript">
            <span>Live transcript</span>
            <p>{liveTranscript}</p>
          </div>
        )}
      </section>

      {isAnalyzing && <p className="voice-test-loading">Running Praat and local feedback...</p>}
      {error && <p className="voice-test-error">{error}</p>}

      {metrics && (
        <section className="voice-feedback-panel">
          <div className="voice-score-grid">
            <ScoreCard label="Fluency" value={`${Math.round(metrics.fluency_score)}/100`} />
            <ScoreCard label="Tone accuracy" value={`${Math.round(metrics.tone_accuracy)}%`} />
            <ScoreCard label="Speech rate" value={`${metrics.speech_rate.toFixed(1)}/s`} />
          </div>

          <StudentFeedbackCards
            toneAccuracy={metrics.tone_accuracy}
            fluencyScore={metrics.fluency_score}
            speechRate={metrics.speech_rate}
            wordProsody={metrics.word_prosody || []}
          />

          <ModelExampleCard
            text={metrics.transcription || "今天下雨，所以我帶傘。"}
            focusWord={getToneFocusItems(metrics.word_prosody || [])[0]?.token}
          />

          <div className="voice-feedback-card">
            <h2>Transcription from audio</h2>
            {metrics.description && (
              <p className="voice-result-description">{metrics.description}</p>
            )}
            <p className="voice-transcript-text">
              {metrics.transcription ||
                "No transcription was returned. Praat metrics are based on the audio file."}
            </p>
            <ScriptWordLevel
              transcription={metrics.transcription || ""}
              wordProsody={metrics.word_prosody}
            />
            {metrics.transcription_model && (
              <small className="voice-model-note">
                ASR model: {metrics.transcription_model}
              </small>
            )}
          </div>

          <details className="voice-advanced-details">
            <summary>Advanced Praat details</summary>
          <div className="voice-feedback-card">
            <h2>Praat feedback</h2>
            <p>{metrics.feedback}</p>
          </div>

          <div className="voice-feedback-card voice-praat-visual-card">
            <h2>Praat visualization</h2>
            <PraatTimeline
              audioBlob={audioBlob}
              pitchContour={metrics.pitch_contour}
              wordProsody={normalizeWordProsody(metrics.word_prosody)}
              transcription={metrics.transcription || ""}
            />
          </div>

          {metrics.word_prosody && metrics.word_prosody.length > 0 && (
            <div className="voice-feedback-card">
              <h2>Word-level prosody</h2>
              <div className="voice-word-grid">
                {metrics.word_prosody.map((word) => (
                  <div className="voice-word-card" key={`${word.token}-${word.index}`}>
                    <strong>{word.token}</strong>
                    <span>{formatContourShape(word.contour_shape)}</span>
                    <small>
                      {Math.round(word.mean_pitch)} Hz avg ·{" "}
                      {Math.round(word.pitch_range)} Hz range
                    </small>
                    <p>{word.feedback}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          </details>

          {metrics.ai_feedback && (
            <div className="voice-feedback-card ai-card">
              <div className="ai-card-header">
                <h2>AI feedback</h2>
                <span>{metrics.ai_feedback.provider}</span>
              </div>
              <div className="ai-feedback-columns">
                <FeedbackBlock
                  title="Fluency"
                  score={metrics.ai_feedback.fluency.score}
                  text={metrics.ai_feedback.fluency.feedback}
                />
                <FeedbackBlock
                  title="Grammar"
                  score={metrics.ai_feedback.grammar.score}
                  text={metrics.ai_feedback.grammar.feedback}
                />
                <FeedbackBlock
                  title="Vocabulary"
                  score={metrics.ai_feedback.vocabulary.score}
                  text={metrics.ai_feedback.vocabulary.feedback}
                />
              </div>
              {metrics.ai_feedback.improved_version && (
                <p className="improved-version">
                  <strong>Improved version:</strong>{" "}
                  {metrics.ai_feedback.improved_version}
                </p>
              )}
              <p className="practice-prompt">
                <strong>Practice next:</strong> {metrics.ai_feedback.practice_prompt}
              </p>
            </div>
          )}
        </section>
      )}
    </main>
  );
}

function normalizeWavFileName(fileName: string): string {
  return fileName.toLowerCase().endsWith(".wav") ? fileName : `${fileName}.wav`;
}

function ensureWavBlob(blob: Blob): Blob {
  if (blob.type === "audio/wav" || blob.type === "audio/x-wav") {
    return blob;
  }

  return new Blob([blob], { type: "audio/wav" });
}

function normalizeWordProsody(words: WordProsody[] = []) {
  return words.map((word, index) => ({
    token: word.token,
    index: word.index ?? index,
    start_time: word.start_time ?? index,
    end_time: word.end_time ?? index + 1,
    pitch_contour: word.pitch_contour ?? [],
    reference_contour: word.reference_contour ?? [],
    mean_pitch: word.mean_pitch,
    pitch_range: word.pitch_range,
    start_pitch: word.start_pitch ?? word.mean_pitch,
    end_pitch: word.end_pitch ?? word.mean_pitch,
    contour_shape: word.contour_shape,
    feedback: word.feedback,
  }));
}

function ScriptWordLevel({
  transcription,
  wordProsody = [],
}: {
  transcription: string;
  wordProsody?: WordProsody[];
}) {
  const scriptWords =
    wordProsody.length > 0
      ? wordProsody.map((word, index) => ({
          token: word.token,
          index: word.index ?? index,
          contour: word.contour_shape,
          feedback: word.feedback,
          meanPitch: word.mean_pitch,
          pitchRange: word.pitch_range,
        }))
      : tokenizeTranscript(transcription).map((token, index) => ({
          token,
          index,
          contour: "",
          feedback: "",
          meanPitch: 0,
          pitchRange: 0,
        }));

  if (scriptWords.length === 0) {
    return (
      <div className="voice-script-empty">
        Word-level script appears after audio transcription.
      </div>
    );
  }

  return (
    <div className="voice-script-level" aria-label="Word-level script">
      {scriptWords.map((word) => (
        <span
          className="voice-script-token"
          key={`${word.token}-${word.index}`}
          title={word.feedback || undefined}
        >
          <strong>{word.token}</strong>
          {word.contour && <em>{formatContourShape(word.contour)}</em>}
          {word.meanPitch > 0 && (
            <small>
              {Math.round(word.meanPitch)} Hz / {Math.round(word.pitchRange)} Hz
            </small>
          )}
        </span>
      ))}
    </div>
  );
}

function tokenizeTranscript(transcription: string): string[] {
  return (
    transcription.match(/[\u4e00-\u9fff]|[A-Za-z0-9']+/g)?.slice(0, 80) || []
  );
}

function ScoreCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="voice-score-card">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function ModelExampleCard({
  text,
  focusWord,
}: {
  text: string;
  focusWord?: string;
}) {
  const exampleText = text.trim() || "今天下雨，所以我帶傘。";

  const playExample = () => {
    if (!("speechSynthesis" in window)) {
      return;
    }

    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(exampleText);
    utterance.lang = "zh-TW";
    utterance.rate = 0.82;
    utterance.pitch = 1;
    window.speechSynthesis.speak(utterance);
  };

  return (
    <section className="voice-model-example" aria-label="100 score example">
      <div>
        <span>100-score example</span>
        <h2>Listen, then copy with your voice</h2>
        <p>{exampleText}</p>
      </div>
      <div className="voice-model-example-actions">
        {focusWord && <em>Focus first: {focusWord}</em>}
        <button type="button" onClick={playExample}>
          Play example
        </button>
      </div>
    </section>
  );
}

function StudentFeedbackCards({
  toneAccuracy,
  fluencyScore,
  speechRate,
  wordProsody,
}: {
  toneAccuracy: number;
  fluencyScore: number;
  speechRate: number;
  wordProsody: WordProsody[];
}) {
  const focus = getToneFocusItems(wordProsody)[0];

  return (
    <section className="voice-student-feedback" aria-label="Student feedback">
      <div className="voice-student-feedback-card good">
        <span>Good</span>
        <strong>{studentStrength(toneAccuracy, fluencyScore)}</strong>
      </div>
      <div className="voice-student-feedback-card fix">
        <span>Fix</span>
        <strong>{studentFix(toneAccuracy, fluencyScore, speechRate, focus)}</strong>
      </div>
      <div className="voice-student-feedback-card next">
        <span>Next try</span>
        <strong>{studentNextStep(speechRate, focus)}</strong>
      </div>
    </section>
  );
}

function studentStrength(toneAccuracy: number, fluencyScore: number): string {
  if (toneAccuracy >= 80 && fluencyScore >= 75) {
    return "Your tones and rhythm are clear enough to build a longer sentence.";
  }
  if (toneAccuracy >= 75) {
    return "Your tone shape is recognizable.";
  }
  if (fluencyScore >= 75) {
    return "Your speaking rhythm is steady.";
  }
  return "You completed a recording. Now improve one small part.";
}

function studentFix(
  toneAccuracy: number,
  fluencyScore: number,
  speechRate: number,
  focus?: WordProsody,
): string {
  if (speechRate > 6.5) {
    return "Slow down so each Mandarin tone has time to finish.";
  }
  if (toneAccuracy < 65 && focus) {
    return `Make the tone movement clearer on "${focus.token}".`;
  }
  if (fluencyScore < 60) {
    return "Connect the words more smoothly without stopping between every character.";
  }
  if (focus) {
    return `Polish "${focus.token}" first.`;
  }
  return "Keep the sentence short and make every tone clear.";
}

function studentNextStep(speechRate: number, focus?: WordProsody): string {
  if (focus) {
    return `Say "${focus.token}" three times, then repeat the full sentence.`;
  }
  if (speechRate < 2.5) {
    return "Try the same sentence again with a little more flow.";
  }
  return "Record again and try to match the same clear rhythm.";
}

function getToneFocusItems(items: WordProsody[]): WordProsody[] {
  const scored = items.map((item) => ({
    item,
    score:
      (item.contour_shape === "variable" ? 3 : 0) +
      (item.pitch_range < 15 ? 2 : 0) +
      (item.pitch_range > 95 ? 1 : 0),
  }));

  const focus = scored
    .filter((entry) => entry.score > 0)
    .sort((a, b) => b.score - a.score)
    .map((entry) => entry.item)
    .slice(0, 4);

  return focus.length > 0 ? focus : items.slice(0, 4);
}

function FeedbackBlock({
  title,
  score,
  text,
}: {
  title: string;
  score: number;
  text: string;
}) {
  return (
    <div className="feedback-block">
      <strong>
        {title} · {Math.round(score)}/100
      </strong>
      <p>{text}</p>
    </div>
  );
}

function formatContourShape(shape: string): string {
  const labels: Record<string, string> = {
    dip: "Dipping",
    falling: "Falling",
    level: "Level",
    rising: "Rising",
    variable: "Variable",
  };
  return labels[shape] || "Variable";
}

async function readErrorResponse(response: Response): Promise<{ detail?: string }> {
  try {
    return await response.json();
  } catch {
    return { detail: `${response.status} ${response.statusText}` };
  }
}

function getBackendUrl(): string {
  if (BACKEND_URL) {
    return BACKEND_URL;
  }

  throw new Error(
    "Voice testing needs a deployed backend in production. Deploy the FastAPI backend and set VITE_BACKEND_URL.",
  );
}

function formatBackendError(error: unknown, backendUrl: string): string {
  const message = error instanceof Error ? error.message : String(error);
  const networkFailures = ["Failed to fetch", "NetworkError", "Load failed"];

  if (networkFailures.some((failure) => message.includes(failure))) {
    return `Cannot reach the speech analysis backend at ${backendUrl}. Start the FastAPI backend on port 8000, then try again.`;
  }

  return message || "Voice analysis error occurred.";
}
