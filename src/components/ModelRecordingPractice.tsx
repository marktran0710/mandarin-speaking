import { useState } from "react";
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
 * Teacher-authored model voice wins when available. Until then, a verified
 * local recording keeps the practice loop usable without network TTS. */
export default function ModelRecordingPractice({
  sceneIndex,
  modelSentence,
  modelAudioUrl,
}: ModelRecordingPracticeProps) {
  const [practiceOpen, setPracticeOpen] = useState(false);
  const [passed, setPassed] = useState(false);
  const fallback = modelPracticeSampleFor(sceneIndex);
  const hasSceneRecording = Boolean(modelSentence?.trim() && modelAudioUrl?.trim());
  const recording = hasSceneRecording
    ? {
        sentence: modelSentence!.trim(),
        pinyin: toPinyin(modelSentence!.trim()),
        meaning: "",
        audioUrl: modelAudioUrl!.trim(),
      }
    : fallback;

  return (
    <section className="model-recording-practice" aria-label="Listen and repeat model recording">
      {modelSentence?.trim() && !hasSceneRecording && (
        <div className="model-recording-scene-target">
          <p className="block-label">
            <BiLabel k="speaking_model_sentence" />
          </p>
          <p lang="zh-Hant">{modelSentence.trim()}</p>
          <small>{toPinyin(modelSentence.trim())}</small>
        </div>
      )}

      <div className="model-recording-heading">
        <span aria-hidden="true">🎧</span>
        <div>
          <p className="block-label">
            {hasSceneRecording ? (
              <BiLabel zh="本課示範錄音" pinyin="Běn kè shìfàn lùyīn" en="Scene model recording" />
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

      <audio
        className="model-recording-audio"
        controls
        preload="metadata"
        src={recording.audioUrl}
        aria-label={`Model recording: ${recording.sentence}`}
      />

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
