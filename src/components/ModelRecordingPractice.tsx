import { useEffect, useState } from "react";
import { modelPracticeSampleFor } from "../data/modelPracticeSamples";
import { toPinyin } from "../utils/pinyin";
import { BiLabel } from "./BiLabel";
import PhrasePracticeDrill from "./PhrasePracticeDrill";
import "./ModelRecordingPractice.css";

interface ModelRecordingPracticeProps {
  sceneIndex: number;
  modelSentence?: string;
  modelAudioUrl?: string;
}

/** Listen -> read -> repeat support for the student Speaking stage.
 * Teacher-authored model voice wins when available. Without one, the scene
 * sentence stays authoritative and can use browser speech synthesis; the
 * bundled offline sample is reserved for sessions with no scene sentence. */
export default function ModelRecordingPractice({
  sceneIndex,
  modelSentence,
  modelAudioUrl,
}: ModelRecordingPracticeProps) {
  const [practiceOpen, setPracticeOpen] = useState(false);
  const [passed, setPassed] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
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
  const canUseSpeechSynthesis =
    typeof window !== "undefined" &&
    "speechSynthesis" in window &&
    "SpeechSynthesisUtterance" in window;

  useEffect(() => {
    return () => {
      if (typeof window !== "undefined" && "speechSynthesis" in window) {
        window.speechSynthesis.cancel();
      }
    };
  }, []);

  const speakSceneSentence = () => {
    if (!canUseSpeechSynthesis) return;
    if (isSpeaking) {
      window.speechSynthesis.cancel();
      setIsSpeaking(false);
      return;
    }

    const utterance = new SpeechSynthesisUtterance(recording.sentence);
    utterance.lang = "zh-TW";
    utterance.onend = () => setIsSpeaking(false);
    utterance.onerror = () => setIsSpeaking(false);
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(utterance);
    setIsSpeaking(true);
  };

  return (
    <section className="model-recording-practice" aria-label="Listen and repeat model recording">
      {sceneSentence && !hasSceneRecording && (
        <div className="model-recording-scene-target">
          <p className="block-label">
            <BiLabel k="speaking_model_sentence" />
          </p>
          <p lang="zh-Hant">{sceneSentence}</p>
          <small>{toPinyin(sceneSentence)}</small>
        </div>
      )}

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

      {recording.audioUrl ? (
        <audio
          className="model-recording-audio"
          controls
          preload="metadata"
          src={recording.audioUrl}
          aria-label={`Model recording: ${recording.sentence}`}
        />
      ) : sceneSentence && canUseSpeechSynthesis ? (
        <button
          type="button"
          className="model-recording-speech-button"
          onClick={speakSceneSentence}
          aria-pressed={isSpeaking}
        >
          {isSpeaking ? "Stop scene sentence" : "Listen to scene sentence"}
        </button>
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

      <button
        type="button"
        className="model-recording-practice-toggle"
        aria-expanded={practiceOpen}
        onClick={() => setPracticeOpen((current) => !current)}
      >
        {practiceOpen ? (
          <BiLabel zh="收起跟讀練習" pinyin="Shōuqǐ gēndú liànxí" en="Hide repeat practice" />
        ) : (
          <BiLabel zh="跟著示範錄音練習" pinyin="Gēnzhe shìfàn lùyīn liànxí" en="Practice this model recording" />
        )}
      </button>

      {practiceOpen && (
        <div className="model-recording-drill">
          {passed && (
            <p className="model-recording-passed" role="status">
              ✓ <BiLabel zh="示範句已通過" pinyin="Shìfàn jù yǐ tōngguò" en="Model sentence passed" />
            </p>
          )}
          <PhrasePracticeDrill phrase={recording.sentence} onPass={() => setPassed(true)} />
        </div>
      )}
    </section>
  );
}
