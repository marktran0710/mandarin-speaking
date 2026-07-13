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
import "./ListenRetellPage.css";

interface ListenRetellPageProps {
  publishedTopics: Topic[];
}

interface ListenScene {
  image: string;
  script: string;
  audioUrl: string;
  vocabulary: string[];
}

// Built-in sample so this page works even before a teacher publishes a listening script.
const SAMPLE_SCENES: ListenScene[] = [
  {
    image: "/sample-scenes/park.svg",
    script:
      "公園裡下雨了，小朋友們撐著雨傘跑來跑去，找地方躲雨，玩得很開心。",
    audioUrl: "",
    vocabulary: ["公園", "下雨", "雨傘", "跑步", "孩子"],
  },
];

export default function ListenRetellPage({ publishedTopics }: ListenRetellPageProps) {
  const scenes = useMemo(() => buildSceneOptions(publishedTopics), [publishedTopics]);
  const [sceneIndex, setSceneIndex] = useState(0);
  const scene = scenes[sceneIndex];

  const [hasListened, setHasListened] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [recordingDuration, setRecordingDuration] = useState(0);
  const [audioUrl, setAudioUrl] = useState("");
  const [error, setError] = useState("");
  const [result, setResult] = useState<AnalysisResult | null>(null);

  const listenAudioRef = useRef<HTMLAudioElement | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const startTimeRef = useRef(0);
  const durationTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const selectScene = (index: number) => {
    setSceneIndex(index);
    setHasListened(false);
    setResult(null);
    setError("");
    setAudioUrl("");
    window.speechSynthesis?.cancel();
  };

  const playScript = () => {
    setHasListened(true);
    if (scene.audioUrl && listenAudioRef.current) {
      listenAudioRef.current.currentTime = 0;
      void listenAudioRef.current.play();
      return;
    }
    if (!("speechSynthesis" in window)) return;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(scene.script);
    utterance.lang = "zh-TW";
    utterance.rate = 0.82;
    utterance.pitch = 1;
    window.speechSynthesis.speak(utterance);
  };

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
        await submitRetell(rawBlob);
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

  const submitRetell = async (rawBlob: Blob) => {
    setIsAnalyzing(true);
    try {
      const wavBlob = await convertBlobToWav(rawBlob);
      setAudioUrl(URL.createObjectURL(wavBlob));

      const formData = new FormData();
      formData.append("file", wavBlob, "retell.wav");
      formData.append("transcription", "");
      formData.append("asr_model", "ctwhisper");
      // The script (not the picture) is the source of truth for grading a retell.
      formData.append("scene_prompt", scene.script);
      formData.append("scene_vocabulary", scene.vocabulary.join(", "));

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
    <main className="listen-retell-page">
      <section className="lr-hero">
        <p className="eyebrow">
          <BiLabel zh="原型 · 聽和說" pinyin="Yuánxíng · tīng hé shuō" en="Prototype · Listen & Retell" />
        </p>
        <h1>
          <BiLabel zh="聽和說" pinyin="Tīng hé shuō" en="Listen & Retell" />
        </h1>
        <p>
          <BiText
            zh="聽這段話（可以聽好幾次），然後用自己的話再說一次。AI 會看看你說的和你聽到的一不一樣。"
            pinyin="Tīng zhè duàn huà (kěyǐ tīng hǎo jǐ cì), ránhòu yòng zìjǐ de huà zài shuō yí cì. AI huì kànkan nǐ shuō de hé nǐ tīngdào de yì bù yíyàng."
            en="Listen to the passage (as many times as you like), then retell it in your own words. The AI compares what you said against what you heard."
          />
        </p>
      </section>

      <section className="lr-scene-picker">
        {scenes.map((option, index) => (
          <button
            key={option.image + index}
            type="button"
            className={`lr-scene-thumb ${index === sceneIndex ? "active" : ""}`}
            onClick={() => selectScene(index)}
          >
            <img src={option.image} alt={`Scene ${index + 1}`} />
            <span>
              <BiLabel zh={`場景 ${index + 1}`} pinyin={`Chǎngjǐng ${index + 1}`} en={`Scene ${index + 1}`} />
            </span>
          </button>
        ))}
      </section>

      <section className="lr-workspace">
        <div className="lr-image-panel">
          <img src={scene.image} alt="Scene for support" className="lr-image" />
          {scene.audioUrl && (
            <audio ref={listenAudioRef} src={scene.audioUrl} preload="none" />
          )}
          <button type="button" className="lr-play-btn" onClick={playScript}>
            🔊 {hasListened ? (
              <BiLabel zh="再聽一次" pinyin="Zài tīng yí cì" en="Play again" />
            ) : (
              <BiLabel zh="聽" pinyin="Tīng" en="Listen" />
            )}
          </button>
          {!scene.audioUrl && (
            <p className="lr-tts-note">
              <BiLabel
                zh="正在播放 AI 的聲音 — 這個場景還沒有老師的錄音。"
                pinyin="Zhèngzài bòfàng AI de shēngyīn — zhège chǎngjǐng hái méiyǒu lǎoshī de lùyīn."
                en="Playing AI text-to-speech — no teacher audio uploaded for this scene."
              />
            </p>
          )}
          <div className="lr-vocab-chips">
            {scene.vocabulary.map((word) => (
              <span key={word} className="lr-vocab-chip">
                {word}
              </span>
            ))}
          </div>
        </div>

        <div className="lr-record-panel">
          <button
            type="button"
            className={`btn ${isRecording ? "btn-danger" : "btn-primary"}`}
            onClick={isRecording ? stopRecording : startRecording}
            disabled={isAnalyzing || !hasListened}
          >
            {isRecording ? (
              <BiLabel zh="停止，評分" pinyin="Tíngzhǐ, píngfēn" en="Stop and evaluate" />
            ) : result ? (
              <BiLabel zh="再錄一次" pinyin="Zài lù yí cì" en="Record again" />
            ) : (
              <BiLabel zh="開始說" pinyin="Kāishǐ shuō" en="Start retelling" />
            )}
          </button>
          {!hasListened && (
            <p className="lr-status">
              <BiLabel
                zh="說之前，請先聽一次這段話。"
                pinyin="Shuō zhīqián, qǐng xiān tīng yí cì zhè duàn huà."
                en="Listen to the passage at least once before you retell it."
              />
            </p>
          )}
          <p className="lr-status">
            {isRecording ? (
              <BiLabel zh={`錄音中… ${recordingDuration}s`} pinyin={`Lùyīn zhōng… ${recordingDuration}s`} en={`Recording... ${recordingDuration}s`} />
            ) : isAnalyzing ? (
              <BiLabel zh="正在看你說的和原文一不一樣…" pinyin="Zhèngzài kàn nǐ shuō de hé yuánwén yì bù yíyàng…" en="Comparing your retelling with the passage..." />
            ) : (
              <BiLabel zh="準備好了" pinyin="Zhǔnbèi hǎo le" en="Ready" />
            )}
          </p>
          {audioUrl && <audio controls src={audioUrl} className="lr-audio-preview" />}
          {error && <p className="lr-error">{error}</p>}
        </div>
      </section>

      {result && (
        <section className="lr-result">
          <div className="lr-transcript-card">
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
            <div className="lr-content-accuracy">
              <h2><BiLabel zh="你說的跟你聽到的一樣嗎？" pinyin="Nǐ shuō de gēn nǐ tīngdào de yíyàng ma?" en="Does your retelling match what you heard?" /></h2>
              <p>{contentAccuracy.feedback}</p>
              {contentAccuracy.matched_details.length > 0 && (
                <p className="lr-matched">
                  ✓ <BiLabel zh="說對了：" pinyin="Shuō duì le:" en="Matched: " />
                  {contentAccuracy.matched_details.join(", ")}
                </p>
              )}
              {contentAccuracy.missed_details.length > 0 && (
                <p className="lr-missed">
                  ✗ <BiLabel zh="沒說到：" pinyin="Méi shuō dào:" en="Missed: " />
                  {contentAccuracy.missed_details.join(", ")}
                </p>
              )}
            </div>
          )}

          {ai?.vocabulary_coverage && (
            <div className="lr-detail-card">
              <h3><BiLabel zh="詞彙" pinyin="Cíhuì" en="Vocabulary" /></h3>
              <p>{ai.vocabulary_coverage.feedback}</p>
            </div>
          )}
          {ai?.coherence && (
            <div className="lr-detail-card">
              <h3><BiLabel zh="順暢度" pinyin="Shùnchàng dù" en="Coherence" /></h3>
              <p>{ai.coherence.feedback}</p>
            </div>
          )}
          {prosodyLines.length > 0 && (
            <div className="lr-detail-card">
              <h3><BiLabel k="character_by_character_prosody" /></h3>
              {prosodyLines.map(({ token, feedback }) => (
                <p key={token}>
                  <strong lang="zh-TW">{token}</strong> — {feedback}
                </p>
              ))}
            </div>
          )}
          {ai?.practice_prompt && (
            <div className="lr-detail-card practice">
              <h3><BiLabel zh="下一步練習" pinyin="Xià yí bù liànxí" en="Practice next" /></h3>
              <p>{ai.practice_prompt}</p>
            </div>
          )}
        </section>
      )}
    </main>
  );
}

function buildSceneOptions(publishedTopics: Topic[]): ListenScene[] {
  const fromTopics = publishedTopics.flatMap((topic) =>
    topic.images
      .map((image, index) => ({
        image,
        script: topic.listenScripts?.[index] || "",
        audioUrl: topic.listenAudioUrls?.[index] || "",
        vocabulary: topic.vocabulary[index] || [],
      }))
      .filter((scene) => scene.script || scene.audioUrl),
  );
  return fromTopics.length > 0 ? fromTopics : SAMPLE_SCENES;
}
