import { useEffect, useMemo, useRef, useState, type ChangeEvent } from "react";
import type { Topic } from "../components/TopicSelector";
import { convertBlobToWav } from "../utils/audio";
import { BiLabel } from "../components/BiLabel";
import StudentIcon from "../components/StudentIcon";
import StudentPageHeader from "../components/StudentPageHeader";
import ScoreCard from "../components/ScoreCard";
import StudentAnalysisGate from "../components/StudentAnalysisGate";
import {
  averageWordProsodyAccuracy,
  getBackendUrl,
  prosodyFeedbackLines,
  readErrorResponse,
  getAnalysisVisibility,
  isUsableScore,
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
  const activeSceneIndex = Math.min(sceneIndex, Math.max(0, scenes.length - 1));
  const scene = scenes[activeSceneIndex] ?? SAMPLE_SCENES[0];

  const [customVocab, setCustomVocab] = useState("");
  const [isRecording, setIsRecording] = useState(false);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [recordingDuration, setRecordingDuration] = useState(0);
  const [audioUrl, setAudioUrl] = useState("");
  const [pendingAudio, setPendingAudio] = useState<Blob | null>(null);
  const [pendingAudioName, setPendingAudioName] = useState("");
  const [error, setError] = useState("");
  const [result, setResult] = useState<AnalysisResult | null>(null);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const startTimeRef = useRef(0);
  const durationTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const mountedRef = useRef(true);
  const preparationIdRef = useRef(0);
  const audioUrlRef = useRef("");
  const analysisControllerRef = useRef<AbortController | null>(null);

  const clearAudioPreview = () => {
    if (audioUrlRef.current) {
      URL.revokeObjectURL?.(audioUrlRef.current);
      audioUrlRef.current = "";
    }
    setAudioUrl("");
  };

  useEffect(() => () => {
    mountedRef.current = false;
    preparationIdRef.current += 1;
    analysisControllerRef.current?.abort();
    if (mediaRecorderRef.current?.state === "recording") {
      mediaRecorderRef.current.stop();
    }
    streamRef.current?.getTracks().forEach((track) => track.stop());
    if (durationTimerRef.current) clearInterval(durationTimerRef.current);
    if (audioUrlRef.current) URL.revokeObjectURL?.(audioUrlRef.current);
  }, []);

  const effectiveVocabulary = customVocab.trim()
    ? customVocab.split(/[,，]/).map((w) => w.trim()).filter(Boolean)
    : scene.vocabulary;

  const startRecording = async () => {
    const recordingId = ++preparationIdRef.current;
    analysisControllerRef.current?.abort();
    analysisControllerRef.current = null;
    setError("");
    setResult(null);
    clearAudioPreview();
    setPendingAudio(null);
    setPendingAudioName("");
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
        if (recordingId !== preparationIdRef.current) return;
        await prepareNarration(rawBlob, "narration.wav");
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

  const prepareNarration = async (rawBlob: Blob, fileName: string) => {
    const preparationId = ++preparationIdRef.current;
    try {
      const wavBlob = await convertBlobToWav(rawBlob);
      if (!mountedRef.current || preparationId !== preparationIdRef.current) return;
      clearAudioPreview();
      const nextAudioUrl = URL.createObjectURL(wavBlob);
      audioUrlRef.current = nextAudioUrl;
      setPendingAudio(wavBlob);
      setPendingAudioName(fileName);
      setAudioUrl(nextAudioUrl);
      setResult(null);
      setError("");
    } catch (err) {
      if (mountedRef.current && preparationId === preparationIdRef.current) {
        setError(err instanceof Error ? err.message : "Could not prepare the audio.");
      }
    }
  };

  const submitNarration = async () => {
    if (!pendingAudio) return;
    const submittedScene = scene;
    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), 120_000);
    analysisControllerRef.current?.abort();
    analysisControllerRef.current = controller;
    setIsAnalyzing(true);
    setResult(null);
    try {
      const formData = new FormData();
      formData.append("file", pendingAudio, pendingAudioName || "narration.wav");
      formData.append("transcription", "");
      formData.append("asr_model", "ctwhisper");
      formData.append("scene_prompt", submittedScene.prompt);
      formData.append("scene_vocabulary", effectiveVocabulary.join(", "));
      formData.append("scene_image_url", submittedScene.image);

      const response = await fetch(`${getBackendUrl()}/api/analyze`, {
        method: "POST",
        body: formData,
        signal: controller.signal,
      });

      if (!response.ok) {
        const errorData = await readErrorResponse(response);
        throw new Error(errorData.detail || "分析失敗。 Analysis failed.");
      }

      const nextResult = (await response.json()) as AnalysisResult;
      if (mountedRef.current && analysisControllerRef.current === controller) {
        setResult(nextResult);
      }
    } catch (err) {
      if (controller.signal.aborted && analysisControllerRef.current !== controller) return;
      if (controller.signal.aborted) {
        setError("Analysis took too long. Please try the recording again.");
        return;
      }
      setError(err instanceof Error ? err.message : "無法分析錄音。 Could not analyze the recording.");
    } finally {
      window.clearTimeout(timeoutId);
      if (analysisControllerRef.current === controller) {
        analysisControllerRef.current = null;
        if (mountedRef.current) setIsAnalyzing(false);
      }
    }
  };

  const handleImportAudio = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    if (!file.type.startsWith("audio/") && !/\.(wav|wave|webm|mp3|m4a|ogg|aac|flac)$/i.test(file.name)) {
      setError("Please choose an audio file.");
      return;
    }
    setResult(null);
    setError("");
    preparationIdRef.current += 1;
    clearAudioPreview();
    setPendingAudio(null);
    setPendingAudioName("");
    void prepareNarration(file, file.name);
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
  const rawContentAccuracy = ai?.content_accuracy;
  const visibility = getAnalysisVisibility(result);
  const contentAccuracy = visibility.showContentDetails ? rawContentAccuracy : undefined;
  const prosodyScore = averageWordProsodyAccuracy(result?.word_prosody);
  const prosodyLines = prosodyFeedbackLines(result?.word_prosody);

  return (
    <main className="narration-page">
      <StudentPageHeader
        eyebrow={{ zh: "原型 · 看圖說話", pinyin: "Yuánxíng · kàn tú shuōhuà", en: "Prototype · Image narration" }}
        title={{ zh: "看圖說話", pinyin: "Kàn tú shuōhuà", en: "Describe the Picture" }}
        lede={{
          zh: "看圖片，用重要的詞，大聲說出發生了什麼事。AI 會看看你說的和圖片裡的東西一不一樣。",
          pinyin: "Kàn túpiàn, yòng zhòngyào de cí, dàshēng shuō chū fāshēng le shénme shì. AI huì kànkan nǐ shuō de hé túpiàn lǐ de dōngxi yì bù yíyàng.",
          en: "Look at the image, use the keywords as a guide, and describe out loud what is happening. The AI compares what you said against what is actually in the picture.",
        }}
      />

      <section className="narration-scene-picker">
        {scenes.map((option, index) => (
          <button
            key={option.image + index}
            type="button"
            className={`narration-scene-thumb ${index === activeSceneIndex ? "active" : ""}`}
            onClick={() => {
              preparationIdRef.current += 1;
              analysisControllerRef.current?.abort();
              analysisControllerRef.current = null;
              if (mediaRecorderRef.current?.state === "recording") mediaRecorderRef.current.stop();
              setIsRecording(false);
              clearDurationTimer();
              setSceneIndex(index);
              setIsAnalyzing(false);
              setResult(null);
              setError("");
              clearAudioPreview();
              setPendingAudio(null);
              setPendingAudioName("");
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
          <p className="narration-prompt" lang="zh-Hant">{scene.prompt}</p>
          <div className="narration-vocab-chips">
            {effectiveVocabulary.map((word) => (
              <span key={word} className="narration-vocab-chip" lang="zh-Hant">
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
            className={`btn student-action-record ${isRecording ? "btn-danger" : "btn-primary"}`}
            onClick={isRecording ? stopRecording : startRecording}
            disabled={isAnalyzing}
          >
            <StudentIcon name={isRecording ? "stop" : result ? "retry" : "record"} size={19} />
            {isRecording ? (
              <BiLabel zh="停止，評分" pinyin="Tíngzhǐ, píngfēn" en="Stop and evaluate" />
            ) : result ? (
              <BiLabel zh="再錄一次" pinyin="Zài lù yí cì" en="Record again" />
            ) : (
              <BiLabel zh="開始描述" pinyin="Kāishǐ miáoshù" en="Start describing" />
            )}
          </button>
          <label className="narration-upload-btn student-action-upload btn btn-secondary">
            <StudentIcon name="upload" size={18} /> <span>Upload audio</span>
            <input
              type="file"
              accept="audio/*,.wav,.wave,.webm,.mp3,.m4a,.ogg,.aac,.flac"
              onChange={handleImportAudio}
              disabled={isRecording || isAnalyzing}
            />
          </label>
          {pendingAudio && !result && !isAnalyzing && (
            <button type="button" className="btn student-action-analyze btn-secondary" onClick={() => void submitNarration()}>
              <StudentIcon name="analyze" size={18} /> <span>Analyze this audio</span>
            </button>
          )}
          <p className="narration-status">
            {isRecording ? (
              <BiLabel zh={`錄音中… ${recordingDuration}s`} pinyin={`Lùyīn zhōng… ${recordingDuration}s`} en={`Recording... ${recordingDuration}s`} />
            ) : isAnalyzing ? (
              <BiLabel zh="正在看你說的對不對…" pinyin="Zhèngzài kàn nǐ shuō de duì bú duì…" en="Comparing your description with the image..." />
            ) : (
              <BiLabel zh="準備好了" pinyin="Zhǔnbèi hǎo le" en="Ready" />
            )}
          </p>
          {pendingAudio && !result && !isAnalyzing && (
            <p className="narration-status narration-ready-status">
              <span>Audio ready — review it, then analyze</span>
            </p>
          )}
          {pendingAudioName && <p className="narration-audio-name">{pendingAudioName}</p>}
          {audioUrl && <audio controls src={audioUrl} className="narration-audio-preview" />}
          {error && <p className="narration-error">{error}</p>}
        </div>
      </section>

      {result && (
        <section className="narration-result">
          {visibility.needsRetry && <StudentAnalysisGate result={result} />}
          <div className="narration-transcript-card">
            <span><BiLabel k="you_said" /></span>
            <p lang="zh-TW">
              {result.transcription || (
                <BiLabel zh="（沒聽到聲音）" pinyin="(méi tīngdào shēngyīn)" en="(no speech detected)" />
              )}
            </p>
          </div>

          {!visibility.needsRetry && <div className="mini-score-grid">
            {visibility.showVocabulary && ai?.vocabulary_coverage && (
              <ScoreCard label={<BiLabel zh="詞彙" pinyin="Cíhuì" en="Vocabulary" />} score={ai.vocabulary_coverage.score} />
            )}
            {visibility.showPronunciation && prosodyScore !== null && (
              <ScoreCard label={<BiLabel k="character_by_character_prosody" />} score={prosodyScore} />
            )}
            {visibility.showPronunciation && isUsableScore(result.tone_accuracy) && (
              <ScoreCard label={<BiLabel zh="聲調準確度" pinyin="Shēngdiào zhǔnquè dù" en="Tone accuracy" />} score={Math.round(result.tone_accuracy)} />
            )}
            {contentAccuracy && (
              <ScoreCard label={<BiLabel zh="內容準確度" pinyin="Nèiróng zhǔnquè dù" en="Content accuracy" />} score={contentAccuracy.score} highlight />
            )}
          </div>}

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

          {visibility.showVocabulary && ai?.vocabulary_coverage && (
            <div className="narration-detail-card">
              <h3><BiLabel zh="詞彙" pinyin="Cíhuì" en="Vocabulary" /></h3>
              <p>{ai.vocabulary_coverage.feedback}</p>
            </div>
          )}
          {visibility.showCoherence && ai?.coherence && (
            <div className="narration-detail-card">
              <h3><BiLabel zh="順暢度" pinyin="Shùnchàng dù" en="Coherence" /></h3>
              <p>{ai.coherence.feedback}</p>
            </div>
          )}
          {visibility.showPronunciation && prosodyLines.length > 0 && (
            <div className="narration-detail-card">
              <h3><BiLabel k="character_by_character_prosody" /></h3>
              {prosodyLines.map(({ token, feedback }) => (
                <p key={token}>
                  <strong lang="zh-TW">{token}</strong> — {feedback}
                </p>
              ))}
            </div>
          )}
          {visibility.showPracticePrompt && ai?.practice_prompt && (
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
