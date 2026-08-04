import { useEffect, useState } from "react";
import { modelPracticeSampleFor } from "../data/modelPracticeSamples";
import { toPinyin } from "../utils/pinyin";
import { convertBlobToWav } from "../utils/audio";
import { formatBackendError, getBackendUrl } from "../utils/storyRecorderFeedback";
import { BiLabel } from "./BiLabel";
import PraatTimeline from "./PraatTimeline";
import type { WordProsody } from "./StoryRecorder";
import "./ModelRecordingPractice.css";

type PraatVizState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "error"; message: string }
  | {
      status: "ready";
      audioBlob: Blob;
      pitchContour: Array<[number, number]>;
      wordProsody: WordProsody[];
    };

interface ModelRecordingPracticeProps {
  sceneIndex: number;
  modelSentence?: string;
  modelAudioUrl?: string;
}

/** Listen -> read -> repeat support for the student Speaking stage.
 * Teacher-authored model voice wins when available. Without one, the scene
 * sentence stays authoritative and is synthesized by the backend so it can
 * still play through a normal <audio> tag; the bundled offline sample is
 * reserved for sessions with no scene sentence. */
export default function ModelRecordingPractice({
  sceneIndex,
  modelSentence,
  modelAudioUrl,
}: ModelRecordingPracticeProps) {
  const [praatViz, setPraatViz] = useState<PraatVizState>({ status: "idle" });
  const [ttsAudioUrl, setTtsAudioUrl] = useState("");
  const [ttsLoading, setTtsLoading] = useState(false);
  const fallback = modelPracticeSampleFor(sceneIndex);
  const sceneSentence = modelSentence?.trim() || "";
  const hasSceneRecording = Boolean(sceneSentence && modelAudioUrl?.trim());
  // A teacher's scene sentence is the source of truth for every piece of
  // content in this card. The offline sample is only used when no scene
  // sentence was supplied; using its audio/transcript alongside a scene
  // target made the card show two different sentences.
  const recording = sceneSentence
    ? {
        sentence: sceneSentence,
        pinyin: toPinyin(sceneSentence),
        meaning: "",
        audioUrl: modelAudioUrl?.trim() || "",
      }
    : fallback;

  // A scene sentence with no teacher-recorded audio still needs something
  // playable through a real <audio> tag (no ad-hoc "speak" button, and the
  // browser's speechSynthesis voice can't be captured for the Praat compare
  // above anyway), so the backend synthesizes it once and this plays that.
  useEffect(() => {
    if (recording.audioUrl || !sceneSentence) {
      setTtsAudioUrl("");
      setTtsLoading(false);
      return;
    }

    let cancelled = false;
    let objectUrl = "";
    setTtsLoading(true);
    setTtsAudioUrl("");

    (async () => {
      try {
        const response = await fetch(`${getBackendUrl()}/api/tts`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text: sceneSentence }),
        });
        if (!response.ok) throw new Error("Could not generate audio for this sentence.");
        const blob = await response.blob();
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setTtsAudioUrl(objectUrl);
      } catch {
        if (!cancelled) setTtsAudioUrl("");
      } finally {
        if (!cancelled) setTtsLoading(false);
      }
    })();

    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [recording.audioUrl, sceneSentence]);

  // The model recording has no pre-computed Praat metrics (unlike a
  // student's own attempt, which is analyzed the moment it's recorded), so
  // this fetches whichever audio file is actually playing — teacher
  // recording, bundled offline sample, or backend-synthesized TTS, the
  // student doesn't need to know which — and runs it through the shared
  // /api/analyze pipeline the first time they press play. The audio tag
  // itself is the trigger, no separate button, and no backend call before
  // they've chosen to listen.
  const playableAudioUrl = recording.audioUrl || ttsAudioUrl;
  const recordingSentence = recording.sentence;

  useEffect(() => {
    setPraatViz({ status: "idle" });
  }, [playableAudioUrl]);

  const loadPraatVisualization = async () => {
    if (praatViz.status === "loading" || praatViz.status === "ready") return;
    setPraatViz({ status: "loading" });
    try {
      const audioResponse = await fetch(playableAudioUrl);
      if (!audioResponse.ok) throw new Error("Could not load the model recording audio.");
      const audioBlob = await audioResponse.blob();
      const wav = await convertBlobToWav(audioBlob);
      const formData = new FormData();
      formData.append("file", wav, "model-recording.wav");
      formData.append("transcription", recordingSentence);
      formData.append("ai_provider", "local");

      const response = await fetch(`${getBackendUrl()}/api/analyze`, {
        method: "POST",
        body: formData,
      });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.detail || "Model recording analysis failed.");
      }

      const data = await response.json();
      setPraatViz({
        status: "ready",
        audioBlob,
        pitchContour: data.pitch_contour ?? [],
        wordProsody: data.word_prosody ?? [],
      });
    } catch (err) {
      setPraatViz({
        status: "error",
        message: formatBackendError(err, getBackendUrl() || "the configured backend"),
      });
    }
  };

  return (
    <section className="model-recording-practice" aria-label="Listen and repeat model recording">
      <div className="model-recording-heading">
        <span aria-hidden="true">🎧</span>
        <div>
          <p className="block-label">
            {hasSceneRecording ? (
              <BiLabel zh="本課示範錄音" pinyin="Běn kè shìfàn lùyīn" en="Scene model recording" />
            ) : sceneSentence ? (
              <BiLabel zh="本課句子練習" pinyin="Běn kè jùzi liànxí" en="Scene sentence practice" />
            ) : (
              <BiLabel zh="暖身示範錄音" pinyin="Nuǎnshēn shìfàn lùyīn" en="Warm-up model recording" />
            )}
          </p>
          <small>
            <BiLabel
              zh="先聽，再跟著說，最後錄下自己的聲音。"
              pinyin="Xiān tīng, zài gēnzhe shuō, zuìhòu lùxià zìjǐ de shēngyīn."
              en="Listen first, repeat, then record yourself."
            />
          </small>
        </div>
      </div>

      <div className="model-recording-script">
        <p className="model-recording-hanzi" lang="zh-Hant">{recording.sentence}</p>
        <p className="model-recording-pinyin">{recording.pinyin}</p>
        {recording.meaning && <p className="model-recording-meaning">{recording.meaning}</p>}
      </div>

      {playableAudioUrl ? (
        <>
          <audio
            className="model-recording-audio"
            controls
            preload="metadata"
            src={playableAudioUrl}
            aria-label={`Model recording: ${recording.sentence}`}
            onPlay={loadPraatVisualization}
          />
          {praatViz.status !== "idle" && (
            <div className="model-recording-praat">
              {praatViz.status === "loading" && (
                <p className="model-recording-praat-status">
                  <BiLabel zh="分析中…" pinyin="Fēnxī zhōng…" en="Analyzing…" />
                </p>
              )}
              {praatViz.status === "error" && (
                <p className="model-recording-praat-status is-error">{praatViz.message}</p>
              )}
              {praatViz.status === "ready" && (
                <>
                  <p className="model-recording-praat-caption">
                    <BiLabel
                      zh="這是示範錄音，音高曲線就是滿分的樣子。"
                      pinyin="Zhè shì shìfàn lùyīn, yīngāo qūxiàn jiù shì mǎnfēn de yàngzi."
                      en="This is the model recording — its pitch curve is what a full-score attempt looks like."
                    />
                  </p>
                  <PraatTimeline
                    audioBlob={praatViz.audioBlob}
                    pitchContour={praatViz.pitchContour}
                    wordProsody={praatViz.wordProsody}
                    transcription={recording.sentence}
                  />
                </>
              )}
            </div>
          )}
        </>
      ) : ttsLoading ? (
        <p className="model-recording-no-audio">
          <BiLabel zh="正在產生示範發音…" pinyin="Zhèngzài chǎnshēng shìfàn fāyīn…" en="Generating model audio…" />
        </p>
      ) : (
        <p className="model-recording-no-audio">
          The scene sentence is ready to repeat; a teacher recording is not available yet.
        </p>
      )}

      <div className="model-recording-steps" aria-label="Listen and repeat steps">
        <span><b>1</b> Listen</span>
        <span><b>2</b> Repeat</span>
        <span><b>3</b> Record</span>
      </div>
    </section>
  );
}
