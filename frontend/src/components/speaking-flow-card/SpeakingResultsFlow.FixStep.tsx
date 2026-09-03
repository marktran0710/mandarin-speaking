// @ts-nocheck
import { BiLabel } from "../BiLabel";
import AppButton from "../AppButton";
import StudentIcon from "../StudentIcon";
import ContentDiffDisplay from "../ContentDiffDisplay";

export default function SpeakingResultsFixStep({
  accepted,
  meaningJudged,
  showCorrective,
  contentAccuracy,
  corrective,
  hasScriptMismatch,
  isChunked,
  targetScript,
  recognizedText,
  praatMetrics,
  chunkScores,
  scriptMismatches,
  missing,
  hasPractice,
  hasPhrasePractice,
  goToStep,
  onRecordAgain,
}) {
  return (
    <div className="sfc-step-panel">
      {!accepted && (meaningJudged || showCorrective) && (
        <section className="sfc-result-card sfc-result-card--meaning is-bad">
          <header className="sfc-result-card-header"><span aria-hidden="true"><StudentIcon name="target" size={18} /></span><BiLabel zh="意思" en="Meaning" /></header>
          {meaningJudged && contentAccuracy?.feedback && (
            <div className="sfc-result-card-body">
              <p className="content-accuracy-feedback">{contentAccuracy.feedback}</p>
              {contentAccuracy.missed_details.length > 0 && <p className="content-accuracy-missed"><StudentIcon name="x-circle" size={15} /> {contentAccuracy.missed_details.join(", ")}</p>}
            </div>
          )}
          {showCorrective && <CorrectiveFeedback corrective={corrective} className="sfc-result-card-body" />}
        </section>
      )}

      {hasScriptMismatch && isChunked && (
        <section className="sfc-result-card sfc-result-card--vocab">
          <header className="sfc-result-card-header"><span aria-hidden="true"><StudentIcon name="file" size={18} /></span><BiLabel zh="跟讀對照（分段）" en="Script check (by part)" /></header>
          <div className="sfc-result-card-body">
            <p className="sfc-result-card-lead"><BiLabel zh="先練好還沒過的部分，再說一次整句" en="Practice the parts below, then say the whole sentence again." /></p>
            <ContentDiffDisplay target={targetScript} heard={recognizedText || null} diff={praatMetrics.content_diff} contentMatch={praatMetrics.content_match} />
            <div className="sfc-missing-chips">
              {chunkScores.map((chunk, index) => <span key={`${chunk.text}-${index}`} className={`vocab-chip sfc-missing-chip${chunk.passed ? " is-cleared" : ""}`}>{chunk.text} <StudentIcon name={chunk.passed ? "check" : "x-circle"} size={14} /></span>)}
            </div>
          </div>
        </section>
      )}

      {hasScriptMismatch && !isChunked && (
        <section className="sfc-result-card sfc-result-card--vocab">
          <header className="sfc-result-card-header"><span aria-hidden="true"><StudentIcon name="file" size={18} /></span><BiLabel zh="跟讀對照" en="Script check" /></header>
          <div className="sfc-result-card-body">
            <p className="sfc-result-card-lead"><BiLabel zh="這些字和範例句不同，請再說一次" en="These parts differ from the model sentence. Say them again." /></p>
            <ContentDiffDisplay target={targetScript} heard={recognizedText || null} diff={praatMetrics.content_diff} contentMatch={praatMetrics.content_match} />
            <div className="sfc-missing-chips">{scriptMismatches.map((word) => <span key={word} className="vocab-chip sfc-missing-chip">{word}</span>)}</div>
          </div>
        </section>
      )}

      {missing.length > 0 && (
        <section className="sfc-result-card sfc-result-card--vocab">
          <header className="sfc-result-card-header"><span aria-hidden="true"><StudentIcon name="book" size={18} /></span><BiLabel zh="生詞" en="Vocabulary" /></header>
          <div className="sfc-result-card-body">
            <p className="sfc-result-card-lead"><BiLabel zh="試著加入" en="Try to include" /></p>
            <div className="sfc-missing-chips">{missing.map((word) => <span key={word} className="vocab-chip sfc-missing-chip">{word}</span>)}</div>
            {accepted && showCorrective && <CorrectiveFeedback corrective={corrective} />}
          </div>
        </section>
      )}

      {hasPractice && <div className="sfc-step-cta-row"><AppButton tone="primary" className="sfc-btn-next sfc-step-cta" onClick={() => goToStep("practice")}><BiLabel zh="練習生詞" en={hasPhrasePractice ? "Practice the parts" : "Practice the words"} /> <StudentIcon name="arrow-right" size={16} /></AppButton></div>}
    </div>
  );
}

function CorrectiveFeedback({ corrective, className = "" }) {
  return (
    <div className={`${className} sfc-corrective${corrective.reveal_answer ? "" : " is-hint"}`}>
      <p className="sfc-corrective-heading">{corrective.reveal_answer ? <BiLabel zh="正確答案" en="Correct version" /> : <BiLabel zh="提示" en="Hint" />}</p>
      {corrective.hint && <p>{corrective.hint}</p>}
      {corrective.reveal_answer && corrective.correct_version && <p><strong>{corrective.correct_version}</strong></p>}
    </div>
  );
}
