import { useEffect, useMemo, useRef, useState, type ChangeEvent } from "react";
import type { Topic } from "../components/TopicSelector";
import { buildSceneOptions, DEFAULT_LISTEN_SCENE } from "./listen-retell/scenes";
import { convertBlobToWav } from "../utils/audio";
import { BiLabel } from "../components/BiLabel";
import StudentIcon from "../components/StudentIcon";
import StudentPageHeader from "../components/StudentPageHeader";
import ScoreCard from "../components/ScoreCard";
import StudentAnalysisGate from "../components/student/StudentAnalysisGate";
import StudentAudioActionPanel from "../components/student/StudentAudioActionPanel";
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
import "./ListenRetellPage.css";

interface ListenRetellPageProps {
  publishedTopics: Topic[];
}

const MAX_RECORDING_SECONDS = 30;

export default function ListenRetellPage({ publishedTopics }: ListenRetellPageProps) {
  const scenes = useMemo(() => buildSceneOptions(publishedTopics), [publishedTopics]);
  const [sceneIndex, setSceneIndex] = useState(0);
  const activeSceneIndex = Math.min(sceneIndex, Math.max(0, scenes.length - 1));
  const scene = scenes[activeSceneIndex] ?? DEFAULT_LISTEN_SCENE;

  const [hasListened, setHasListened] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [recordingDuration, setRecordingDuration] = useState(0);
  const [audioUrl, setAudioUrl] = useState("");
  const [pendingAudio, setPendingAudio] = useState<Blob | null>(null);
  const [pendingAudioName, setPendingAudioName] = useState("");
  const [error, setError] = useState("");
  const [result, setResult] = useState<AnalysisResult | null>(null);

  const listenAudioRef = useRef<HTMLAudioElement | null>(null);
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
    window.speechSynthesis?.cancel();
    if (durationTimerRef.current) clearInterval(durationTimerRef.current);
    if (audioUrlRef.current) URL.revokeObjectURL?.(audioUrlRef.current);
  }, []);

  const selectScene = (index: number) => {
    preparationIdRef.current += 1;
    analysisControllerRef.current?.abort();
    analysisControllerRef.current = null;
    if (mediaRecorderRef.current?.state === "recording") mediaRecorderRef.current.stop();
    setIsRecording(false);
    clearDurationTimer();
    setSceneIndex(index);
    setHasListened(false);
    setIsAnalyzing(false);
    setResult(null);
    setError("");
    clearAudioPreview();
    setPendingAudio(null);
    setPendingAudioName("");
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
        await prepareRetell(rawBlob, "retell.wav");
      };

      startTimeRef.current = Date.now();
      durationTimerRef.current = setInterval(() => {
        const elapsed = Math.min(
          MAX_RECORDING_SECONDS,
          Math.floor((Date.now() - startTimeRef.current) / 1000),
        );
        setRecordingDuration(elapsed);
        if (elapsed >= MAX_RECORDING_SECONDS) stopRecording();
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

  const prepareRetell = async (rawBlob: Blob, fileName: string) => {
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

  const submitRetell = async () => {
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
      formData.append("file", pendingAudio, pendingAudioName || "retell.wav");
      formData.append("transcription", "");
      formData.append("asr_model", "ctwhisper");
      // The script (not the picture) is the source of truth for grading a retell.
      formData.append("scene_prompt", submittedScene.script);
      formData.append("scene_target_text", submittedScene.script);
      formData.append("scene_vocabulary", submittedScene.vocabulary.join(", "));

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
    void prepareRetell(file, file.name);
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
  const visibility = getAnalysisVisibility(result);
  const rawContentAccuracy = ai?.content_accuracy;
  const contentAccuracy = visibility.showContentDetails ? rawContentAccuracy : undefined;
  const prosodyScore = averageWordProsodyAccuracy(result?.word_prosody);
  const prosodyLines = prosodyFeedbackLines(result?.word_prosody);

  return (
    <main className="listen-retell-page">
      <StudentPageHeader
        eyebrow={{ zh: "原型 · 聽和說", pinyin: "Yuánxíng · tīng hé shuō", en: "Prototype · Listen & Retell" }}
        title={{ zh: "聽和說", pinyin: "Tīng hé shuō", en: "Listen & Retell" }}
        lede={{
          zh: "聽這段話（可以聽好幾次），然後用自己的話再說一次。AI 會看看你說的和你聽到的一不一樣。",
          pinyin: "Tīng zhè duàn huà (kěyǐ tīng hǎo jǐ cì), ránhòu yòng zìjǐ de huà zài shuō yí cì. AI huì kànkan nǐ shuō de hé nǐ tīngdào de yì bù yíyàng.",
          en: "Listen to the passage (as many times as you like), then retell it in your own words. The AI compares what you said against what you heard.",
        }}
      />

      <section className="lr-scene-picker">
        {scenes.map((option, index) => (
          <button
            key={option.image + index}
            type="button"
            className={`lr-scene-thumb ${index === activeSceneIndex ? "active" : ""}`}
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
            <StudentIcon name="play" size={18} />
            {hasListened ? (
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

        <StudentAudioActionPanel
          className="lr-record-panel"
          primaryIcon={result ? "retry" : "record"}
          primaryLabel={isRecording ? "Stop and evaluate" : result ? "Record again" : "Start retelling"}
          uploadLabel="Upload audio"
          accept="audio/*,.wav,.wave,.webm,.mp3,.m4a,.ogg,.aac,.flac"
          onPrimaryAction={isRecording ? stopRecording : startRecording}
          onFileChange={handleImportAudio}
          isRecording={isRecording}
          isAnalyzing={isAnalyzing}
          hasPendingAudio={Boolean(pendingAudio && !result)}
          pendingAudioName={pendingAudioName}
          audioUrl={audioUrl}
          onAnalyze={pendingAudio && !result ? () => void submitRetell() : undefined}
          status={!hasListened ? "Listen to the passage at least once before you retell it." : isRecording ? `Recording · ${recordingDuration} / ${MAX_RECORDING_SECONDS}s` : isAnalyzing ? "Comparing your retelling with the passage..." : "Ready"}
          error={error}
          previewClassName="lr-audio-preview"
          uploadDisabled={!hasListened}
          primaryDisabled={!hasListened}
        />
        {false && <div className="lr-record-panel lr-record-panel-legacy">
          <button
            type="button"
            className={`btn student-action-record ${isRecording ? "btn-danger" : "btn-primary"}`}
            onClick={isRecording ? stopRecording : startRecording}
            disabled={isAnalyzing || !hasListened}
          >
            <StudentIcon name={isRecording ? "stop" : result ? "retry" : "record"} size={19} />
            {isRecording ? (
              <BiLabel zh="停止，評分" pinyin="Tíngzhǐ, píngfēn" en="Stop and evaluate" />
            ) : result ? (
              <BiLabel zh="再錄一次" pinyin="Zài lù yí cì" en="Record again" />
            ) : (
              <BiLabel zh="開始說" pinyin="Kāishǐ shuō" en="Start retelling" />
            )}
          </button>
          <label className="lr-upload-btn student-action-upload btn btn-secondary">
            <StudentIcon name="upload" size={18} /> <span>Upload audio</span>
            <input
              type="file"
              accept="audio/*,.wav,.wave,.webm,.mp3,.m4a,.ogg,.aac,.flac"
              onChange={handleImportAudio}
              disabled={isRecording || isAnalyzing || !hasListened}
            />
          </label>
          {pendingAudio && !result && !isAnalyzing && (
            <button type="button" className="btn student-action-analyze btn-secondary" onClick={() => void submitRetell()}>
              <StudentIcon name="analyze" size={18} /> <span>Analyze this audio</span>
            </button>
          )}
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
          {pendingAudio && !result && !isAnalyzing && (
            <p className="lr-status lr-ready-status">
              <span>Audio ready — review it, then analyze</span>
            </p>
          )}
          {pendingAudioName && <p className="lr-audio-name">{pendingAudioName}</p>}
          {audioUrl && <audio controls src={audioUrl} className="lr-audio-preview" />}
          {error && <p className="lr-error">{error}</p>}
        </div>}
      </section>

      {result && (
        <section className="lr-result">
          {visibility.needsRetry && <StudentAnalysisGate result={result} />}
          <div className="lr-transcript-card">
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
            <div className="lr-content-accuracy">
              <h2><BiLabel zh="你說的跟你聽到的一樣嗎？" pinyin="Nǐ shuō de gēn nǐ tīngdào de yíyàng ma?" en="Does your retelling match what you heard?" /></h2>
              <p>{contentAccuracy.feedback}</p>
              {contentAccuracy.matched_details.length > 0 && (
                <p className="lr-matched">
                  <StudentIcon name="check" size={15} aria-hidden="true" /> <BiLabel zh="說對了：" pinyin="Shuō duì le:" en="Matched: " />
                  {contentAccuracy.matched_details.join(", ")}
                </p>
              )}
              {contentAccuracy.missed_details.length > 0 && (
                <p className="lr-missed">
                  <StudentIcon name="x-circle" size={15} aria-hidden="true" /> <BiLabel zh="沒說到：" pinyin="Méi shuō dào:" en="Missed: " />
                  {contentAccuracy.missed_details.join(", ")}
                </p>
              )}
            </div>
          )}

          {visibility.showVocabulary && ai?.vocabulary_coverage && (
            <div className="lr-detail-card">
              <h3><BiLabel zh="詞彙" pinyin="Cíhuì" en="Vocabulary" /></h3>
              <p>{ai.vocabulary_coverage.feedback}</p>
            </div>
          )}
          {visibility.showCoherence && ai?.coherence && (
            <div className="lr-detail-card">
              <h3><BiLabel zh="順暢度" pinyin="Shùnchàng dù" en="Coherence" /></h3>
              <p>{ai.coherence.feedback}</p>
            </div>
          )}
          {visibility.showPronunciation && prosodyLines.length > 0 && (
            <div className="lr-detail-card">
              <h3><BiLabel k="character_by_character_prosody" /></h3>
              {prosodyLines.map(({ token, feedback }) => (
                <p key={token}>
                  <strong lang="zh-TW">{token}</strong> — {feedback}
                </p>
              ))}
            </div>
          )}
          {visibility.showPracticePrompt && ai?.practice_prompt && (
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
