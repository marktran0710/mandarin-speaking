import { useId, useState } from "react";
import StudentIcon from "./StudentIcon";
import StudentButton from "./StudentButton";
import "./StudentInlineFeedback.css";

export interface WordChip {
  hanzi: string;
  pinyin?: string;
  ok: boolean;
  note?: string;
}

interface StudentInlineFeedbackProps {
  meaningOk: boolean;
  pronunciationOk: boolean;
  pronunciationNote?: string;
  coachText?: string;
  wordChips?: WordChip[];
  detailsContent?: React.ReactNode;
  onRecordAgain: () => void;
  onContinue: () => void;
  continueLabel: string;
}

/**
 * Shared feedback drawer for Story Speaking and Conversation Practice. Maps
 * the real SpeakingResultAnalysis (from SpeakingResultsFlow.analysis.ts) —
 * accepted/corrective/weakItems/practiceTargets — down to this simple
 * meaning/pronunciation/word-chip vocabulary; the feature container does
 * that mapping, this component only renders it. Never color-only: every
 * verdict pairs a symbol with its color.
 */
export default function StudentInlineFeedback({
  meaningOk,
  pronunciationOk,
  pronunciationNote,
  coachText,
  wordChips,
  detailsContent,
  onRecordAgain,
  onContinue,
  continueLabel,
}: StudentInlineFeedbackProps) {
  const [detailsOpen, setDetailsOpen] = useState(false);
  const detailsId = useId();

  return (
    <div className="sa-inline-feedback">
      <div className="sa-inline-feedback__verdicts">
        <span className={`sa-verdict-row ${meaningOk ? "is-ok" : "is-attention"}`}>
          <StudentIcon name={meaningOk ? "check_circle" : "change_history"} size={16} role="decorative" />
          Meaning {meaningOk ? "accurate" : "needs another look"}
        </span>
        <span className={`sa-verdict-row ${pronunciationOk ? "is-ok" : "is-attention"}`}>
          <StudentIcon name={pronunciationOk ? "check_circle" : "change_history"} size={16} role="decorative" />
          Pronunciation{pronunciationOk ? " clear" : pronunciationNote ? `: ${pronunciationNote}` : " needs attention"}
        </span>
      </div>

      {wordChips && wordChips.length > 0 && (
        <div className="sa-word-chips" aria-label="Word-level pronunciation result">
          {wordChips.map((chip, i) => (
            <span key={`${chip.hanzi}-${i}`} className={`sa-word-chip ${chip.ok ? "is-ok" : "is-attention"}`}>
              <span lang="zh-Hant" className="sa-word-chip__hanzi">{chip.hanzi}</span>
              <StudentIcon name={chip.ok ? "check" : "change_history"} size={13} role="decorative" />
            </span>
          ))}
        </div>
      )}

      {coachText && (
        <div className="sa-ai-coach">
          <StudentIcon name="school" size={16} role="meaningful" label="AI coaching note" />
          <p>{coachText}</p>
        </div>
      )}

      {detailsContent && (
        <div className="sa-details-disclosure">
          <button
            type="button"
            className="sa-details-disclosure__trigger"
            aria-expanded={detailsOpen}
            aria-controls={detailsId}
            onClick={() => setDetailsOpen((v) => !v)}
          >
            <StudentIcon name={detailsOpen ? "expand_less" : "expand_more"} size={16} role="decorative" />
            Pronunciation details
          </button>
          {detailsOpen && (
            <div id={detailsId} className="sa-details-disclosure__panel">
              {detailsContent}
            </div>
          )}
        </div>
      )}

      <div className="sa-inline-feedback__actions">
        <StudentButton variant="secondary" icon="replay" onClick={onRecordAgain}>
          Record again
        </StudentButton>
        <StudentButton variant="primary" iconTrailing="arrow_forward" onClick={onContinue}>
          {continueLabel}
        </StudentButton>
      </div>
    </div>
  );
}
