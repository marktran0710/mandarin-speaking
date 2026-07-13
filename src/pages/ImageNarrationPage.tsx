import { useMemo, useRef, useState } from "react";
import type { Topic } from "../components/TopicSelector";
import { convertBlobToWav } from "../utils/audio";
import { BiLabel, BiText } from "../components/BiLabel";
import ScoreCard from "../components/ScoreCard";
import {
  averageWordProsodyAccuracy,
  getBackendUrl,
  prosodyFeedbackLines,
  readErrorResponse,
  type AnalysisResult,
} from "../utils/narrationAnalysis";
import "../components/BiLabel.css";
import "./ImageNarrationPage.css";

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
          <BiLabel zh="原型 · 看圖說話" pinyin="Yuánxíng · kàn tú shuōhuà" en="Prototype · Image narration" />
        </p>
        <h1>
          <BiLabel zh="看圖說話" pinyin="Kàn tú shuōhuà" en="Describe the Picture" />
        </h1>
        <p>
          <BiText
            zh="看圖片，用重要的詞，大聲說出發生了什麼事。AI 會看看你說的和圖片裡的東西一不一樣。"
            pinyin="Kàn túpiàn, yòng zhòngyào de cí, dàshēng shuō chū fāshēng le shénme shì. AI huì kànkan nǐ shuō de hé túpiàn lǐ de dōngxi yì bù yíyàng."
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
              <BiLabel zh={`場景 ${index + 1}`} pinyin={`Chǎngjǐng ${index + 1}`} en={`Scene ${index + 1}`} />
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
            <BiLabel zh="改重要的詞（用逗號隔開）" pinyin="Gǎi zhòngyào de cí (yòng dòuhào gékāi)" en="Override keywords (comma separated)" />
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
              <BiLabel zh="停止，評分" pinyin="Tíngzhǐ, píngfēn" en="Stop and evaluate" />
            ) : result ? (
              <BiLabel zh="再錄一次" pinyin="Zài lù yí cì" en="Record again" />
            ) : (
              <BiLabel zh="開始描述" pinyin="Kāishǐ miáoshù" en="Start describing" />
            )}
          </button>
          <p className="narration-status">
            {isRecording ? (
              <BiLabel zh={`錄音中… ${recordingDuration}s`} pinyin={`Lùyīn zhōng… ${recordingDuration}s`} en={`Recording... ${recordingDuration}s`} />
            ) : isAnalyzing ? (
              <BiLabel zh="正在看你說的對不對…" pinyin="Zhèngzài kàn nǐ shuō de duì bú duì…" en="Comparing your description with the image..." />
            ) : (
              <BiLabel zh="準備好了" pinyin="Zhǔnbèi hǎo le" en="Ready" />
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
                <BiLabel zh="（沒聽到聲音）" pinyin="(méi tīngdào shēngyīn)" en="(no speech detected)" />
              )}
            </p>
          </div>

          <div className="mini-score-grid">
            {ai?.vocabulary_coverage && (
              <ScoreCard label={<BiLabel zh="詞彙" pinyin="Cíhuì" en="Vocabulary" />} score={ai.vocabulary_coverage.score} />
            )}
            {prosodyScore !== null && (
              <ScoreCard label={<BiLabel k="character_by_character_prosody" />} score={prosodyScore} />
            )}
            <ScoreCard label={<BiLabel zh="聲調準確度" pinyin="Shēngdiào zhǔnquè dù" en="Tone accuracy" />} score={Math.round(result.tone_accuracy)} />
            {contentAccuracy && (
              <ScoreCard label={<BiLabel zh="內容準確度" pinyin="Nèiróng zhǔnquè dù" en="Content accuracy" />} score={contentAccuracy.score} highlight />
            )}
          </div>

          {contentAccuracy && (
            <div className="narration-content-accuracy">
              <h2><BiLabel zh="你說的跟圖片一樣嗎？" pinyin="Nǐ shuō de gēn túpiàn yíyàng ma?" en="Does your description match the image?" /></h2>
              <p>{contentAccuracy.feedback}</p>
              {contentAccuracy.matched_details.length > 0 && (
                <p className="narration-matched">
                  ✓ <BiLabel zh="說對了：" pinyin="Shuō duì le:" en="Matched: " />
                  {contentAccuracy.matched_details.join(", ")}
                </p>
              )}
              {contentAccuracy.missed_details.length > 0 && (
                <p className="narration-missed">
                  ✗ <BiLabel zh="沒說到：" pinyin="Méi shuō dào:" en="Missed: " />
                  {contentAccuracy.missed_details.join(", ")}
                </p>
              )}
            </div>
          )}

          {ai?.vocabulary_coverage && (
            <div className="narration-detail-card">
              <h3><BiLabel zh="詞彙" pinyin="Cíhuì" en="Vocabulary" /></h3>
              <p>{ai.vocabulary_coverage.feedback}</p>
            </div>
          )}
          {ai?.coherence && (
            <div className="narration-detail-card">
              <h3><BiLabel zh="順暢度" pinyin="Shùnchàng dù" en="Coherence" /></h3>
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
              <h3><BiLabel zh="下一步練習" pinyin="Xià yí bù liànxí" en="Practice next" /></h3>
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
