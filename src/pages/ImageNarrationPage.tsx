import { useMemo, useRef, useState } from "react";
import type { Topic } from "../TopicSelector";
import { convertBlobToWav } from "../utils/audio";
import "./ImageNarrationPage.css";

const BACKEND_URL =
  import.meta.env.VITE_BACKEND_URL ||
  (import.meta.env.DEV ? "http://127.0.0.1:8000" : "");

interface ContentAccuracy {
  score: number;
  feedback: string;
  matched_details: string[];
  missed_details: string[];
}

interface LanguageFeedback {
  provider: string;
  vocabulary_coverage?: {
    score: number;
    used: string[];
    missing: string[];
    feedback: string;
  };
  coherence?: {
    score: number;
    feedback: string;
    corrections: string[];
  };
  pronunciation_note?: {
    score: number;
    feedback: string;
  };
  content_accuracy?: ContentAccuracy;
  improved_version?: string;
  practice_prompt?: string;
}

interface AnalysisResult {
  transcription?: string;
  tone_accuracy: number;
  fluency_score: number;
  ai_feedback?: LanguageFeedback;
}

interface ImageNarrationPageProps {
  publishedTopics: Topic[];
}

// Built-in samples so this prototype works even before any teacher story is published.
const SAMPLE_SCENES: Array<{ image: string; prompt: string; vocabulary: string[] }> = [
  {
    image: "/sample-scenes/park.svg",
    prompt: "描述這張圖片發生了什麼事 (Describe what is happening in this picture)",
    vocabulary: ["公園", "下雨", "雨傘", "跑步", "孩子"],
  },
  {
    image: "/sample-scenes/market.svg",
    prompt: "說說你看到的人和物品 (Talk about the people and things you see)",
    vocabulary: ["市場", "水果", "老闆", "買", "便宜"],
  },
];

export default function ImageNarrationPage({ publishedTopics }: ImageNarrationPageProps) {
  const scenes = useMemo(() => buildSceneOptions(publishedTopics), [publishedTopics]);
  const [sceneIndex, setSceneIndex] = useState(0);
  const scene = scenes[sceneIndex];

  const [customVocab, setCustomVocab] = useState("");
  const [isRecording, setIsRecording] = useState(false);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [recordingDuration, setRecordingDuration] = useState(0);
  const [audioUrl, setAudioUrl] = useState("");
  const [error, setError] = useState("");
  const [result, setResult] = useState<AnalysisResult | null>(null);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const startTimeRef = useRef(0);
  const durationTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const effectiveVocabulary = customVocab.trim()
    ? customVocab.split(/[,，]/).map((w) => w.trim()).filter(Boolean)
    : scene.vocabulary;

  const startRecording = async () => {
    setError("");
    setResult(null);
    setAudioUrl("");
    setRecordingDuration(0);

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      chunksRef.current = [];

      const preferredType = MediaRecorder.isTypeSupported("audio/webm") ? "audio/webm" : "";
      const recorder = new MediaRecorder(stream, preferredType ? { mimeType: preferredType } : undefined);
      mediaRecorderRef.current = recorder;

      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      };

      recorder.onstop = async () => {
        const rawBlob = new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" });
        stopTracks();
        await submitNarration(rawBlob);
      };

      startTimeRef.current = Date.now();
      durationTimerRef.current = setInterval(() => {
        setRecordingDuration(Math.floor((Date.now() - startTimeRef.current) / 1000));
      }, 250);

      recorder.start();
      setIsRecording(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not access microphone.");
      stopTracks();
      clearDurationTimer();
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current?.state === "recording") {
      mediaRecorderRef.current.stop();
    }
    setIsRecording(false);
    clearDurationTimer();
  };

  const submitNarration = async (rawBlob: Blob) => {
    setIsAnalyzing(true);
    try {
      const wavBlob = await convertBlobToWav(rawBlob);
      setAudioUrl(URL.createObjectURL(wavBlob));

      const formData = new FormData();
      formData.append("file", wavBlob, "narration.wav");
      formData.append("transcription", "");
      formData.append("asr_model", "ctwhisper");
      formData.append("scene_prompt", scene.prompt);
      formData.append("scene_vocabulary", effectiveVocabulary.join(", "));
      formData.append("scene_image_url", scene.image);

      const response = await fetch(`${getBackendUrl()}/api/analyze`, {
        method: "POST",
        body: formData,
        signal: AbortSignal.timeout(120_000),
      });

      if (!response.ok) {
        const errorData = await readErrorResponse(response);
        throw new Error(errorData.detail || "Analysis failed.");
      }

      setResult((await response.json()) as AnalysisResult);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not analyze the recording.");
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
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
  };

  const ai = result?.ai_feedback;
  const contentAccuracy = ai?.content_accuracy;

  return (
    <main className="narration-page">
      <section className="narration-hero">
        <p className="eyebrow">Prototype · Image narration</p>
        <h1>Describe the Picture</h1>
        <p>
          Look at the image, use the keywords as a guide, and describe out loud what is
          happening. The AI compares what you said against what is actually in the picture.
        </p>
      </section>

      <section className="narration-scene-picker">
        {scenes.map((option, index) => (
          <button
            key={option.image + index}
            type="button"
            className={`narration-scene-thumb ${index === sceneIndex ? "active" : ""}`}
            onClick={() => {
              setSceneIndex(index);
              setResult(null);
              setError("");
              setAudioUrl("");
            }}
          >
            <img src={option.image} alt={`Scene ${index + 1}`} />
            <span>Scene {index + 1}</span>
          </button>
        ))}
      </section>

      <section className="narration-workspace">
        <div className="narration-image-panel">
          <img src={scene.image} alt="Scene to describe" className="narration-image" />
          <p className="narration-prompt">{scene.prompt}</p>
          <div className="narration-vocab-chips">
            {effectiveVocabulary.map((word) => (
              <span key={word} className="narration-vocab-chip">
                {word}
              </span>
            ))}
          </div>
          <label className="narration-custom-vocab">
            Override keywords (comma separated)
            <input
              type="text"
              placeholder="e.g. 公園, 下雨, 雨傘"
              value={customVocab}
              onChange={(event) => setCustomVocab(event.target.value)}
            />
          </label>
        </div>

        <div className="narration-record-panel">
          <button
            type="button"
            className={`btn ${isRecording ? "btn-danger" : "btn-primary"}`}
            onClick={isRecording ? stopRecording : startRecording}
            disabled={isAnalyzing}
          >
            {isRecording ? "Stop and evaluate" : result ? "Record again" : "Start describing"}
          </button>
          <p className="narration-status">
            {isRecording
              ? `Recording... ${recordingDuration}s`
              : isAnalyzing
                ? "Comparing your description with the image..."
                : "Ready"}
          </p>
          {audioUrl && <audio controls src={audioUrl} className="narration-audio-preview" />}
          {error && <p className="narration-error">{error}</p>}
        </div>
      </section>

      {result && (
        <section className="narration-result">
          <div className="narration-transcript-card">
            <span>You said</span>
            <p lang="zh-TW">{result.transcription || "(no speech detected)"}</p>
          </div>

          <div className="narration-score-grid">
            {ai?.vocabulary_coverage && (
              <ScoreCard label="Vocabulary" score={ai.vocabulary_coverage.score} />
            )}
            {ai?.pronunciation_note && (
              <ScoreCard label="Pronunciation" score={ai.pronunciation_note.score} />
            )}
            <ScoreCard label="Tone accuracy" score={Math.round(result.tone_accuracy)} />
            {contentAccuracy && (
              <ScoreCard label="Content accuracy" score={contentAccuracy.score} highlight />
            )}
          </div>

          {contentAccuracy && (
            <div className="narration-content-accuracy">
              <h2>Does your description match the image?</h2>
              <p>{contentAccuracy.feedback}</p>
              {contentAccuracy.matched_details.length > 0 && (
                <p className="narration-matched">
                  ✓ Matched: {contentAccuracy.matched_details.join(", ")}
                </p>
              )}
              {contentAccuracy.missed_details.length > 0 && (
                <p className="narration-missed">
                  ✗ Missed: {contentAccuracy.missed_details.join(", ")}
                </p>
              )}
            </div>
          )}

          {ai?.vocabulary_coverage && (
            <div className="narration-detail-card">
              <h3>Vocabulary</h3>
              <p>{ai.vocabulary_coverage.feedback}</p>
            </div>
          )}
          {ai?.coherence && (
            <div className="narration-detail-card">
              <h3>Coherence</h3>
              <p>{ai.coherence.feedback}</p>
            </div>
          )}
          {ai?.pronunciation_note && (
            <div className="narration-detail-card">
              <h3>Pronunciation</h3>
              <p>{ai.pronunciation_note.feedback}</p>
            </div>
          )}
          {ai?.practice_prompt && (
            <div className="narration-detail-card practice">
              <h3>Practice next</h3>
              <p>{ai.practice_prompt}</p>
            </div>
          )}
        </section>
      )}
    </main>
  );
}

function buildSceneOptions(publishedTopics: Topic[]) {
  const fromTopics = publishedTopics.flatMap((topic) =>
    topic.images.map((image, index) => ({
      image,
      prompt: topic.prompts?.[index] || topic.name,
      vocabulary: topic.vocabulary[index] || [],
    })),
  );
  return fromTopics.length > 0 ? fromTopics : SAMPLE_SCENES;
}

function ScoreCard({
  label,
  score,
  highlight,
}: {
  label: string;
  score: number;
  highlight?: boolean;
}) {
  return (
    <div className={`narration-score-card ${highlight ? "highlight" : ""}`}>
      <span>{label}</span>
      <strong>{score}%</strong>
    </div>
  );
}

async function readErrorResponse(response: Response): Promise<{ detail?: string }> {
  try {
    return await response.json();
  } catch {
    return { detail: `${response.status} ${response.statusText}` };
  }
}

function getBackendUrl(): string {
  if (BACKEND_URL) return BACKEND_URL;
  throw new Error("Set VITE_BACKEND_URL to reach the FastAPI backend.");
}
