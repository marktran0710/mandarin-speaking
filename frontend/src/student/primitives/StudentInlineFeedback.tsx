import { useId, useState } from "react";
import StudentIcon from "./StudentIcon";
import StudentButton from "./StudentButton";
import type { WordAlignmentItem, WordAlignmentStatus } from "../feedback/wordAlignment";
import "./StudentInlineFeedback.css";

export type { WordAlignmentItem as WordChip, WordAlignmentStatus } from "../feedback/wordAlignment";

interface StudentInlineFeedbackProps {
  meaningOk: boolean;
  pronunciationOk: boolean;
  pronunciationNote?: string;
  coachText?: string;
  wordChips?: WordAlignmentItem[];
  detailsContent?: React.ReactNode;
  onRecordAgain?: () => void;
  onContinue?: () => void;
  continueLabel?: string;
  /** Overrides the built-in Record again/Continue row — used when a caller
   * has intermediate steps (e.g. Story Speaking's Fix/Practice) between
   * this verdict and the final action. */
  footer?: React.ReactNode;
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
  footer,
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
            <span
              key={`${chip.key}-${i}`}
              className={`sa-word-chip sa-word-chip--${chip.status.toLowerCase()}`}
              aria-label={`${chip.hanzi}${chip.pinyin ? `, ${chip.pinyin}` : ""}: ${wordStatusLabel(chip.status)}${chip.note ? `. ${chip.note}` : ""}`}
              title={chip.note}
            >
              <span className="sa-word-chip__reading">
                {chip.pinyin && <span className="sa-word-chip__pinyin">{chip.pinyin}</span>}
                <span lang="zh-Hant" className="sa-word-chip__hanzi">{chip.hanzi}</span>
              </span>
              <StudentIcon name={wordStatusIcon(chip.status)} size={13} role="decorative" />
              <span className="sa-word-chip__status">{wordStatusLabel(chip.status)}</span>
              {chip.note && <span className="sa-word-chip__note">{chip.note}</span>}
            </span>
          ))}
        </div>
      )}

      {coachText && (
        <div className="sa-ai-coach">
          <StudentIcon name="school" size={16} role="meaningful" label="AI coaching note" />
          <div>
            <span className="sa-ai-coach__label">AI Coach Note</span>
            <p>{coachText}</p>
          </div>
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

      {footer !== undefined ? footer : onRecordAgain && onContinue && (
        <div className="sa-inline-feedback__actions">
          <StudentButton variant="secondary" icon="replay" onClick={onRecordAgain}>
            Record again
          </StudentButton>
          <StudentButton variant="primary" iconTrailing="arrow_forward" onClick={onContinue}>
            {continueLabel}
          </StudentButton>
        </div>
      )}
    </div>
  );
}

function wordStatusLabel(status: WordAlignmentStatus): string {
  switch (status) {
    case "CORRECT": return "Correct";
    case "UNCERTAIN": return "Uncertain";
    case "INCORRECT": return "Pronunciation needs attention";
    case "INVALID_AUDIO": return "Could not evaluate";
    case "NEUTRAL": return "Neutral tone — not separately scored";
  }
}

function wordStatusIcon(status: WordAlignmentStatus): string {
  switch (status) {
    case "CORRECT": return "check";
    case "UNCERTAIN": return "help";
    case "INCORRECT": return "priority_high";
    case "INVALID_AUDIO": return "mic_off";
    case "NEUTRAL": return "horizontal_rule";
  }
}
