// @ts-nocheck
import { createPortal } from "react-dom";
import { BiLabel } from "./BiLabel";
import AppButton from "./AppButton";
import PronunciationBreakdown from "./PronunciationBreakdown";
import { AudioCompare, STEP_LABELS } from "./SpeakingResultsFlow.helpers";
import { shouldOfferRetry } from "../utils/retryPolicy";
import { worstState } from "../utils/assistiveFeedback";

export default function SpeakingResultsFlowShell({
  selectedImage,
  selectedImageIndex,
  modelAudioUrl,
  modelSentence,
  analysisAudioBlob,
  practicePartCount,
  feedbackTriggerRef,
  feedbackModalOpen,
  onOpenFeedback,
  steps,
  step,
  maxVisited,
  setStep,
  stepBody,
  onCloseFeedback,
  praatMetrics,
  targetScript,
  recognizedText,
  teacherPhraseChunks,
  assistiveFeedback,
  masteryCounts,
  hasPhrasePractice,
  allPhrasesCleared,
  remainingPracticePhrases,
  ready,
  masteryPassed,
  practiceTargets,
  remainingDrillTargets,
  attempts,
  assistiveRetriesUsed,
  onRecordAgain,
  hasNextScene,
  onNextScene,
  onViewSummary,
}) {
  return <section className="speaking-flow-card sfc-results sfc-screen" aria-label="Recording results">
    <div className="practice-workspace">
      <div className="practice-scene-col">
        <div className="practice-scene-image"><img src={selectedImage} alt={`Scene ${selectedImageIndex + 1}`} /></div>
        <AudioCompare modelAudioUrl={modelAudioUrl} modelSentence={modelSentence} analysisAudioBlob={analysisAudioBlob} />
        <div className="sfc-left-feedback">
          <button ref={feedbackTriggerRef} type="button" className="sfc-left-feedback-summary" aria-haspopup="dialog" aria-expanded={feedbackModalOpen} aria-controls="sfc-feedback-modal" onClick={onOpenFeedback}>
            <BiLabel zh="發音分析" en="Pronunciation feedback" />
            <span><BiLabel zh={practicePartCount > 0 ? `還有 ${practicePartCount} 個部分要練習` : "已通過評量音調"} en={practicePartCount > 0 ? `${practicePartCount} part${practicePartCount === 1 ? "" : "s"} to practise` : "Measured tones cleared"} /></span>
          </button>
        </div>
      </div>

      <div className="sfc-results-main">
        {steps.length > 1 && <nav className="sfc-stepper" aria-label="Feedback steps">
          {steps.map((item, index) => {
            const current = item === step;
            const visited = index <= maxVisited;
            return <button key={item} type="button" className={`sfc-step${current ? " is-current" : ""}${visited && !current ? " is-visited" : ""}`} disabled={!visited} aria-current={current ? "step" : undefined} onClick={() => setStep(item)}>
              <span className="sfc-step-num" aria-hidden="true">{visited && !current ? "✓" : index + 1}</span>
              <BiLabel zh={STEP_LABELS[item].zh} en={STEP_LABELS[item].en} />
            </button>;
          })}
        </nav>}
        {stepBody}
      </div>
    </div>

    {feedbackModalOpen && createPortal(
      <div className="sfc-feedback-modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onCloseFeedback(); }}>
        <section id="sfc-feedback-modal" className="sfc-feedback-modal" role="dialog" aria-modal="true" aria-labelledby="sfc-feedback-modal-title">
          <header className="sfc-feedback-modal-header"><div id="sfc-feedback-modal-title"><BiLabel zh="發音分析" en="Pronunciation feedback" /></div><button type="button" className="sfc-feedback-modal-close" aria-label="Close pronunciation feedback" onClick={onCloseFeedback}>×</button></header>
          <div className="sfc-feedback-modal-body"><PronunciationBreakdown words={praatMetrics.word_prosody || []} targetText={targetScript} transcription={recognizedText} teacherPhrases={teacherPhraseChunks} assistiveFeedback={assistiveFeedback} masteryCounts={masteryCounts} /></div>
        </section>
      </div>,
      document.body,
    )}

    <ResultsFooter {...{ hasPhrasePractice, allPhrasesCleared, remainingPracticePhrases, ready, masteryPassed, practiceTargets, remainingDrillTargets, attempts, assistiveFeedback, assistiveRetriesUsed, onRecordAgain, hasNextScene, onNextScene, onViewSummary }} />
  </section>;
}

function ResultsFooter({ hasPhrasePractice, allPhrasesCleared, remainingPracticePhrases, ready, masteryPassed, practiceTargets, remainingDrillTargets, attempts, assistiveFeedback, assistiveRetriesUsed, onRecordAgain, hasNextScene, onNextScene, onViewSummary }) {
  return <footer className="sfc-footer">
    {hasPhrasePractice && !allPhrasesCleared ? <p className="sfc-unlock-note">🔒 <BiLabel zh={`還有 ${remainingPracticePhrases.length} 個部分要練，才能錄整句`} pinyin={`Hái yǒu ${remainingPracticePhrases.length} ge bùfen yào liàn, cáinéng lù zhěng jù`} en={`${remainingPracticePhrases.length} more part${remainingPracticePhrases.length === 1 ? "" : "s"} to practice before recording the whole sentence`} /></p>
      : hasPhrasePractice && allPhrasesCleared && !ready ? <p className="sfc-unlock-note">🔒 <BiLabel zh="每個部分都通過了，再錄一次整句就能完成這一部分。" pinyin="Měi ge bùfen dōu tōngguò le, zài lù yí cì zhěng jù jiù néng wánchéng zhè yí bùfen." en="All parts passed. Record the full sentence once more to complete this scene." /></p>
        : !ready && !masteryPassed && practiceTargets.length > 0 ? <p className="sfc-unlock-note">🔒 <BiLabel zh={`每個字都要 ✓ 才能過關 — 還有 ${remainingDrillTargets.length > 0 ? `${remainingDrillTargets.length} 個部分要練` : "整句要再錄一次"}`} pinyin={`Měi ge zì dōu yào ✓ cáinéng guòguān — hái yǒu ${remainingDrillTargets.length > 0 ? `${remainingDrillTargets.length} ge bùfèn yào liàn` : "zhěng jù yào zài lù yí cì"}`} en={`Every practice part needs a ✓ — ${remainingDrillTargets.length > 0 ? `${remainingDrillTargets.length} part${remainingDrillTargets.length > 1 ? "s" : ""} left to practice` : "re-record the whole sentence"}`} /></p>
          : !ready ? <p className="sfc-unlock-note">🔒 <BiLabel zh={`聲調 70 分、流暢 65 分，或練習 4 次即可打開（目前 ${attempts} 次）`} pinyin={`Shēngdiào 70 fēn, liúchàng 65 fēn, huò liànxí 4 cì jí kě dǎkāi (mùqián ${attempts} cì)`} en={`Unlock with tone 70, fluency 65, or 4 attempts (now: ${attempts})`} /></p> : null}
    {assistiveFeedback && shouldOfferRetry(worstState(assistiveFeedback), assistiveRetriesUsed) && <p className="sfc-assistive-retry-hint"><BiLabel zh="想再試一次這個音嗎？" pinyin="Xiǎng zài shì yí cì zhège yīn ma?" en="Want to try that tone once more? Totally optional." /></p>}
    <div className="sfc-footer-actions">
      <AppButton tone="subtle" className="sfc-btn-again" onClick={onRecordAgain}>🎙️ <BiLabel zh="再錄一次" pinyin="Zài lù yí cì" en="Record again" /></AppButton>
      {ready && (hasNextScene ? <AppButton tone="secondary" className="sfc-btn-next" onClick={onNextScene}><BiLabel k="next_scene" /> →</AppButton> : <AppButton tone="secondary" className="sfc-btn-next" onClick={onViewSummary}><BiLabel zh="查看總結" pinyin="Chákàn zǒngjié" en="View summary" /> →</AppButton>)}
    </div>
  </footer>;
}
