import { BiLabel } from "./BiLabel";
import StudentIcon from "./StudentIcon";
import type { AnalysisResult } from "../utils/narrationAnalysis";
import "./StudentAnalysisGate.css";

interface StudentAnalysisGateProps {
  result: AnalysisResult;
}

/** A compact, student-safe explanation for an attempt that cannot be scored. */
export default function StudentAnalysisGate({ result }: StudentAnalysisGateProps) {
  const quality = result.feedback_quality;
  const reasonCodes = quality?.reason_codes ?? quality?.reasons ?? [];
  const contentMismatch =
    result.content_match === false ||
    reasonCodes.includes("target_content_mismatch");

  return (
    <aside className="student-analysis-gate" role="alert" aria-live="polite">
      <span className="student-analysis-gate-icon" aria-hidden="true">
        <StudentIcon name={contentMismatch ? "retry" : "feedback"} size={17} />
      </span>
      <div>
        <strong>
          {contentMismatch ? (
            <BiLabel
              zh="隤芸???"
              pinyin="Q?ng z?i shu? y? c穫"
              en="Try the recording again"
            />
          ) : (
            <BiLabel
              zh="隤??"
              pinyin="Q?ng q?ngq?ng z?i l羅 y穩 y? c穫"
              en="We need a clearer recording"
            />
          )}
        </strong>
        <p>
          {quality?.student_message ||
            (contentMismatch
              ? "The recording did not match the target closely enough to score safely."
              : "There was not enough clear speech or pitch evidence to score safely.")}
        </p>
        <p className="student-analysis-gate-action">
          <BiLabel
            zh="隤??閬?"
            pinyin="Q?ng z?i j靚ng y?c穫"
            en="Move a little closer to the microphone and say it once more at a natural pace."
          />
        </p>
      </div>
    </aside>
  );
}
