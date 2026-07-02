import { useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import type { Topic } from "../components/TopicSelector";
import { convertBlobToWav } from "../utils/audio";
import { BiLabel, BiText } from "../components/BiLabel";
import "../components/BiLabel.css";
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

interface WordProsody {
  token: string;
  tone_accuracy?: number;
  feedback?: string;
}

interface AnalysisResult {
  transcription?: string;
  tone_accuracy: number;
  fluency_score: number;
  word_prosody?: WordProsody[];
  ai_feedback?: LanguageFeedback;
}

/** Real, measured prosody score — averaged per-character tone_accuracy —
 * rather than the AI's generic pronunciation_note.score, which isn't
 * grounded in the actual measured pitch data. */
function averageWordProsodyAccuracy(wordProsody?: WordProsody[]): number | null {
  const accuracies = (wordProsody ?? [])
    .map((item) => item.tone_accuracy)
    .filter((value): value is number => typeof value === "number");
  if (accuracies.length === 0) return null;
  return Math.round(
    accuracies.reduce((sum, value) => sum + value, 0) / accuracies.length,
  );
}

/** Per-character feedback for the characters that most need work, grounded in
 * the actual measured pitch data (word_prosody), instead of the AI's generic
 * pronunciation_note text. */
function prosodyFeedbackLines(wordProsody?: WordProsody[]): Array<{ token: string; feedback: string }> {
  return (wordProsody ?? [])
    .filter((item) => item.feedback)
    .sort((a, b) => (a.tone_accuracy ?? 100) - (b.tone_accuracy ?? 100))
    .slice(0, 3)
    .map((item) => ({ token: item.token, feedback: item.feedback! }));
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
      setError(err instanceof Error ? err.message : "無法存取麥克風。 Could not access microphone.");
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
        throw new Error(errorData.detail || "分析失敗。 Analysis failed.");
      }

      setResult((await response.json()) as AnalysisResult);
    } catch (err) {
      setError(err instanceof Error ? err.message : "無法分析錄音。 Could not analyze the recording.");
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
  const prosodyScore = averageWordProsodyAccuracy(result?.word_prosody);
  const prosodyLines = prosodyFeedbackLines(result?.word_prosody);

  return (
    <main className="narration-page">
      <section className="narration-hero">
        <p className="eyebrow">
          <BiLabel zh="原型 · 看圖敘述" en="Prototype · Image narration" />
        </p>
        <h1>
          <BiLabel zh="看圖說話" en="Describe the Picture" />
        </h1>
        <p>
          <BiText
            zh="觀察圖片，參考關鍵詞，大聲說出發生了什麼事。AI 會比對你說的內容與圖片中的實際情況。"
            en="Look at the image, use the keywords as a guide, and describe out loud what is happening. The AI compares what you said against what is actually in the picture."
          />
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
            <span>
              <BiLabel zh={`場景 ${index + 1}`} en={`Scene ${index + 1}`} />
            </span>
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
            <BiLabel zh="覆寫關鍵詞（用逗號分隔）" en="Override keywords (comma separated)" />
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
            {isRecording ? (
              <BiLabel zh="停止並評分" en="Stop and evaluate" />
            ) : result ? (
              <BiLabel zh="再錄一次" en="Record again" />
            ) : (
              <BiLabel zh="開始描述" en="Start describing" />
            )}
          </button>
          <p className="narration-status">
            {isRecording ? (
              <BiLabel zh={`錄音中… ${recordingDuration}s`} en={`Recording... ${recordingDuration}s`} />
            ) : isAnalyzing ? (
              <BiLabel zh="正在比對你的描述與圖片…" en="Comparing your description with the image..." />
            ) : (
              <BiLabel zh="準備好了" en="Ready" />
            )}
          </p>
          {audioUrl && <audio controls src={audioUrl} className="narration-audio-preview" />}
          {error && <p className="narration-error">{error}</p>}
        </div>
      </section>

      {result && (
        <section className="narration-result">
          <div className="narration-transcript-card">
            <span><BiLabel k="you_said" /></span>
            <p lang="zh-TW">
              {result.transcription || (
                <BiLabel zh="（未偵測到語音）" en="(no speech detected)" />
              )}
            </p>
          </div>

          <div className="narration-score-grid">
            {ai?.vocabulary_coverage && (
              <ScoreCard label={<BiLabel zh="詞彙" en="Vocabulary" />} score={ai.vocabulary_coverage.score} />
            )}
            {prosodyScore !== null && (
              <ScoreCard label={<BiLabel k="character_by_character_prosody" />} score={prosodyScore} />
            )}
            <ScoreCard label={<BiLabel zh="聲調準確度" en="Tone accuracy" />} score={Math.round(result.tone_accuracy)} />
            {contentAccuracy && (
              <ScoreCard label={<BiLabel zh="內容準確度" en="Content accuracy" />} score={contentAccuracy.score} highlight />
            )}
          </div>

          {contentAccuracy && (
            <div className="narration-content-accuracy">
              <h2><BiLabel zh="你的描述符合圖片嗎？" en="Does your description match the image?" /></h2>
              <p>{contentAccuracy.feedback}</p>
              {contentAccuracy.matched_details.length > 0 && (
                <p className="narration-matched">
                  ✓ <BiLabel zh="符合：" en="Matched: " />
                  {contentAccuracy.matched_details.join(", ")}
                </p>
              )}
              {contentAccuracy.missed_details.length > 0 && (
                <p className="narration-missed">
                  ✗ <BiLabel zh="遺漏：" en="Missed: " />
                  {contentAccuracy.missed_details.join(", ")}
                </p>
              )}
            </div>
          )}

          {ai?.vocabulary_coverage && (
            <div className="narration-detail-card">
              <h3><BiLabel zh="詞彙" en="Vocabulary" /></h3>
              <p>{ai.vocabulary_coverage.feedback}</p>
            </div>
          )}
          {ai?.coherence && (
            <div className="narration-detail-card">
              <h3><BiLabel zh="連貫性" en="Coherence" /></h3>
              <p>{ai.coherence.feedback}</p>
            </div>
          )}
          {prosodyLines.length > 0 && (
            <div className="narration-detail-card">
              <h3><BiLabel k="character_by_character_prosody" /></h3>
              {prosodyLines.map(({ token, feedback }) => (
                <p key={token}>
                  <strong lang="zh-TW">{token}</strong> — {feedback}
                </p>
              ))}
            </div>
          )}
          {ai?.practice_prompt && (
            <div className="narration-detail-card practice">
              <h3><BiLabel zh="下一步練習" en="Practice next" /></h3>
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
  label: ReactNode;
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
