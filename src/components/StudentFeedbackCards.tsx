import {
  studentStrength,
  studentFix,
  studentNextStep,
  getToneFocusItems,
} from "../utils/storyRecorderFeedback";
import type { PauseAnalysis, WordProsody } from "./StoryRecorder";
import { BiLabel } from "./BiLabel";

export default function StudentFeedbackCards({
  toneAccuracy,
  fluencyScore,
  speechRate,
  wordProsody,
  pauseAnalysis,
}: {
  toneAccuracy: number;
  fluencyScore: number;
  speechRate: number;
  wordProsody: WordProsody[];
  pauseAnalysis?: PauseAnalysis;
}) {
  const focus = getToneFocusItems(wordProsody)[0];

  return (
    <section className="student-feedback-cards" aria-label="Student feedback">
      <div className="student-feedback-card good">
        <BiLabel k="good" />
        <strong>{studentStrength(toneAccuracy, fluencyScore)}</strong>
      </div>
      <div className="student-feedback-card fix">
        <BiLabel k="fix" />
        <strong>
          {studentFix(
            toneAccuracy,
            fluencyScore,
            speechRate,
            focus,
            pauseAnalysis,
          )}
        </strong>
      </div>
      <div className="student-feedback-card next">
        <BiLabel k="next_try" />
        <strong>{studentNextStep(speechRate, focus, pauseAnalysis)}</strong>
      </div>
    </section>
  );
}
