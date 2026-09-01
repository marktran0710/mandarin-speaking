import { useState } from "react";
import {
  prosodyImprovementTip,
  shapeArrow,
  toneArrow,
} from "../../utils/storyRecorderFeedback";
import { scoreTier } from "../../utils/scoreLabels";
import { toPinyin, toPinyinSyllables } from "../../utils/pinyin";
import type { WordProsody } from "../story-recorder/StoryRecorder";
import MiniContourChart from "../pitch/MiniContourChart";
import WordPracticeDrill from "./WordPracticeDrill";
import { BiLabel } from "../BiLabel";
import StudentIcon from "../StudentIcon";

export default function WordProsodyCard({
  item,
  onDrillPass,
  drillDefaultOpen = false,
}: {
  item: WordProsody;
  onDrillPass?: (token: string) => void;
  /** Focus mode (one card at a time) opens the practice drill immediately —
   * practicing IS the point of that view, no extra toggle click. */
  drillDefaultOpen?: boolean;
}) {
  const improvementTip = prosodyImprovementTip(item);
  // The card's red "failed" frame reflects the sentence attempt that
  // produced `item` — but once the drill hosted below re-earns the word,
  // leaving it red contradicts the ✓ the student just saw. Track that
  // pass locally and flip the frame green.
  const [drillCleared, setDrillCleared] = useState(false);
  // Everything above the drill describes the *sentence* attempt that produced
  // `item`. The moment the student records the word on its own, that readout
  // is last-round history sitting above a fresher chart of the same word —
  // two contour charts and two verdicts for one character. Collapse it into a
  // one-line summary they can reopen, so the panel shows the attempt they
  // just made.
  const [drillAttempts, setDrillAttempts] = useState(0);
  const [showPastAttempt, setShowPastAttempt] = useState(false);
  const pastAttemptCollapsed = drillAttempts > 0 && !showPastAttempt;
  // The number shown in the topline is the shape score — the same
  // comparison the chart draws — not tone_accuracy's directional blend,
  // which can legitimately differ from what the overlay looks like.
  const shapeScore =
    typeof item.shape_accuracy === "number" ? item.shape_accuracy : null;
  const expectedTones = item.expected_tones ?? [];
  const syllables = item.syllables ?? [];
  const failed = item.passed === false && !drillCleared;
  // Pinyin is the only part of this card a beginner can actually act on —
  // "say 在 with a falling tone" is unreadable without zài. Per-syllable
  // where the characters line up (so each pass chip is labelled), whole-word
  // otherwise.
  const wordPinyin = toPinyin(item.token);
  const syllablePinyin = toPinyinSyllables(item.token);
  return (
    <div
      className={`word-prosody-card ${failed ? "word-prosody-failed" : ""}${drillCleared ? " word-prosody-cleared" : ""}`}
    >
      <div className="word-prosody-topline">
        <span className="word-prosody-token">
          <strong>{item.token}</strong>
          {wordPinyin && (
            <span className="word-prosody-token-pinyin">{wordPinyin}</span>
          )}
        </span>
        {drillCleared && (
          <span className="word-prosody-cleared-chip"><StudentIcon name="check" size={14} aria-hidden="true" /> 過關</span>
        )}
        <span className="word-prosody-topline-meta">
          {/* "You said X / target Y" — two labeled pills so the measured
              shape of the student's own pitch is never mistaken for a
              description of the target tones (the old single pill read as
              a verdict and contradicted the feedback text below). The
              "you said" half belongs to the sentence attempt, so it
              collapses with the rest of that readout; the target doesn't
              change and stays. */}
          {!pastAttemptCollapsed && (
            <span className="word-prosody-shape-pill">
              你說 {shapeArrow(item.contour_shape)}
            </span>
          )}
          {expectedTones.length > 0 && (
            <span className="word-prosody-shape-pill word-prosody-target-pill">
              要說 {expectedTones.map(toneArrow).join(" ")}
            </span>
          )}
          {shapeScore !== null && !pastAttemptCollapsed && (
            <span
              className={`word-prosody-score score-tier-text ${scoreTier(shapeScore)}`}
            >
              {Math.round(shapeScore)}%
            </span>
          )}
        </span>
      </div>
      {pastAttemptCollapsed ? (
        <button
          type="button"
          className="word-prosody-past-toggle"
          onClick={() => setShowPastAttempt(true)}
        >
          <BiLabel zh="看上次整句的結果" en="See the sentence result" /> ▾
        </button>
      ) : (
        <>
          {drillAttempts > 0 && (
            <button
              type="button"
              className="word-prosody-past-toggle is-open"
              onClick={() => setShowPastAttempt(false)}
            >
              <BiLabel zh="上次整句的結果" en="From the sentence" /> ▴
            </button>
          )}
          {syllables.length > 0 && (
            <div
              className="word-syllable-row"
              aria-label={`${item.token} per-syllable results`}
            >
              {syllables.map((syllable, index) => (
                <span
                  key={`${syllable.char}-${index}`}
                  className={`word-syllable-chip ${
                    syllable.passed ? "syllable-pass" : "syllable-fail"
                  }`}
                >
                  <span className="word-syllable-char">
                    {syllable.char} {toneArrow(syllable.tone)}{" "}
                    <StudentIcon name={syllable.passed ? "check" : "x-circle"} size={14} aria-hidden="true" />
                  </span>
                  {syllablePinyin[index] && (
                    <span className="word-syllable-pinyin">
                      {syllablePinyin[index]}
                    </span>
                  )}
                </span>
              ))}
            </div>
          )}
          <div
            className="mini-contour"
            aria-label={`${item.token} pitch contour vs target shape`}
          >
            <MiniContourChart
              actual={item.pitch_contour}
              reference={item.reference_contour}
              userCurve={item.user_curve}
              targetCurve={item.target_curve}
            />
          </div>
          <p className="word-prosody-feedback">{item.feedback}</p>
          {improvementTip && (
            <p className="word-prosody-tip"><StudentIcon name="idea" size={16} aria-hidden="true" /> {improvementTip}</p>
          )}
        </>
      )}
      <WordPracticeDrill
        word={item}
        onPass={(token) => {
          setDrillCleared(true);
          onDrillPass?.(token);
        }}
        onAttempt={() => {
          setDrillAttempts((count) => count + 1);
          setShowPastAttempt(false);
        }}
        defaultOpen={drillDefaultOpen}
      />
    </div>
  );
}
