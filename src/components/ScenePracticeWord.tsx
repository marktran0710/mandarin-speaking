import { useState, type ChangeEvent } from "react";
import { useWordPronunciationPractice } from "../hooks/useWordPronunciationPractice";
import PitchOverlay from "./PitchOverlay";
import { BiLabel } from "./BiLabel";
import { scoreTier, scoreTierLabel } from "../utils/scoreLabels";
import "./ScenePracticeWord.css";

/** A small mic toggle on a scene-vocabulary row that expands into an inline
 * record/upload → score → pitch-curve panel for that single word, reusing
 * the same record/analyze flow as the Tone Practice page. Optional —
 * doesn't block moving on to recording the full scene. */
export default function ScenePracticeWord({
  word,
  pinyin,
}: {
  word: string;
  pinyin?: string;
}) {
  const [expanded, setExpanded] = useState(false);
  const {
    isRecording,
    isAnalyzing,
    error,
    setError,
    result,
    startRecording,
    stopRecording,
    analyzeBlob,
    reset,
  } = useWordPronunciationPractice(word, pinyin);

  const toggle = () => {
    if (expanded) {
      reset();
    }
    setExpanded((current) => !current);
  };

  const handleUploadFile = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;

    if (!file.type.startsWith("audio/") && !/\.(wav|webm|mp3|m4a|ogg|aac|flac)$/i.test(file.name)) {
      setError(`「${file.name}」不是音訊檔。 "${file.name}" isn't an audio file.`);
      return;
    }

    setError("");
    await analyzeBlob(file);
  };

  const segment = result?.word_prosody?.[0];
  const score = segment?.tone_accuracy ?? result?.tone_accuracy;

  return (
    <>
      <button
        type="button"
        className={`scene-practice-toggle ${expanded ? "active" : ""}`}
        onClick={toggle}
        aria-expanded={expanded}
        aria-label={
          expanded
            ? `Hide pronunciation practice for ${word}`
            : `Practice pronouncing ${word}`
        }
        title={expanded ? "Hide practice" : "Practice this word"}
      >
        🎤
      </button>
      {expanded && (
        <div className="scene-practice-panel" role="cell">
          <div className="scene-practice-controls">
            <button
              type="button"
              className={`btn-mini ${isRecording ? "recording" : ""}`}
              onClick={isRecording ? stopRecording : startRecording}
              disabled={isAnalyzing}
              aria-label={
                isRecording ? `Stop recording ${word}` : `Record ${word} to check pronunciation`
              }
            >
              {isRecording ? (
                <BiLabel zh="停止" pinyin="Tíngzhǐ" en="Stop" />
              ) : (
                <BiLabel zh="錄音" pinyin="Lùyīn" en="Record" />
              )}
            </button>
            <label
              className={`btn-mini btn-mini-secondary scene-practice-upload-label ${
                isRecording || isAnalyzing ? "disabled" : ""
              }`}
              role="button"
              tabIndex={isRecording || isAnalyzing ? -1 : 0}
            >
              <BiLabel zh="上傳音檔" pinyin="Shàngchuán yīndàng" en="Upload audio" />
              <input
                type="file"
                accept="audio/*,.wav,.webm,.mp3,.m4a,.ogg,.aac,.flac"
                className="scene-practice-upload-input"
                onChange={handleUploadFile}
                disabled={isRecording || isAnalyzing}
              />
            </label>
          </div>
          {isAnalyzing && (
            <span className="scene-practice-status">
              <BiLabel zh="分析中…" pinyin="Fēnxī zhōng…" en="Analyzing…" />
            </span>
          )}
          {error && <p className="scene-practice-error">{error}</p>}
          {segment && !isAnalyzing && (
            <div className="scene-practice-result">
              {result?.recognized_text && (
                <p
                  className={`scene-practice-recognized ${
                    result.content_match === false ? "mismatch" : "match"
                  }`}
                >
                  <BiLabel zh="聽到：" pinyin="Tīngdào:" en="Heard: " />
                  <strong>{result.recognized_text}</strong>
                  {result.content_match === false && (
                    <span className="scene-practice-recognized-note">
                      <BiLabel
                        zh={`（跟「${word}」不太一樣，分數可能不準）`}
                        pinyin={`(gēn “${word}” bú tài yíyàng, fēnshù kěnéng bù zhǔn)`}
                        en={` (doesn't match "${word}" — score may not be reliable)`}
                      />
                    </span>
                  )}
                </p>
              )}
              <strong className={`scene-practice-score ${scoreTier(score ?? 0)}`}>
                {scoreTierLabel(scoreTier(score ?? 0)).zh}
              </strong>
              <PitchOverlay
                userContour={segment.pitch_contour}
                referenceContour={segment.reference_contour || []}
              />
              <p className="scene-practice-feedback">{segment.feedback}</p>
            </div>
          )}
        </div>
      )}
    </>
  );
}
