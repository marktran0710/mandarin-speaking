import { useState } from "react";
import { useWordPronunciationPractice } from "../hooks/useWordPronunciationPractice";
import PitchOverlay from "./PitchOverlay";
import { BiLabel } from "./BiLabel";
import "./ScenePracticeWord.css";

/** A small mic toggle on a scene-vocabulary row that expands into an inline
 * record → score → pitch-curve panel for that single word, reusing the same
 * record/analyze flow as the Tone Practice page. Optional — doesn't block
 * moving on to recording the full scene. */
export default function ScenePracticeWord({ word }: { word: string }) {
  const [expanded, setExpanded] = useState(false);
  const {
    isRecording,
    isAnalyzing,
    error,
    result,
    startRecording,
    stopRecording,
    reset,
  } = useWordPronunciationPractice(word);

  const toggle = () => {
    if (expanded) {
      reset();
    }
    setExpanded((current) => !current);
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
          <button
            type="button"
            className={`btn-scene-practice-record ${isRecording ? "recording" : ""}`}
            onClick={isRecording ? stopRecording : startRecording}
            disabled={isAnalyzing}
            aria-label={
              isRecording ? `Stop recording ${word}` : `Record ${word} to check pronunciation`
            }
          >
            {isRecording ? (
              <BiLabel zh="停止" en="Stop" />
            ) : (
              <BiLabel zh="錄音" en="Record" />
            )}
          </button>
          {isAnalyzing && (
            <span className="scene-practice-status">
              <BiLabel zh="分析中…" en="Analyzing…" />
            </span>
          )}
          {error && <p className="scene-practice-error">{error}</p>}
          {segment && !isAnalyzing && (
            <div className="scene-practice-result">
              <strong className="scene-practice-score">{Math.round(score ?? 0)}%</strong>
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
