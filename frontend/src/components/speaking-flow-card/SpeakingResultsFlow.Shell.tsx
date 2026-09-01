// @ts-nocheck
import { createPortal } from "react-dom";
import { BiLabel } from "../BiLabel";
import AppButton from "../AppButton";
import PronunciationBreakdown from "../PronunciationBreakdown";
import { AudioCompare, STEP_LABELS } from "./SpeakingResultsFlow.helpers";
import { shouldOfferRetry } from "../../utils/retryPolicy";
import { worstState } from "../../utils/assistiveFeedback";
import Icon from "../../shared/ui/Icon";

export default function SpeakingResultsFlowShell({
  selectedImage,
  selectedImageIndex,
  modelAudioUrl,
  modelSentence,
  analysisAudioBlob,
  practicePartCount,
  feedbackTriggerRef,
  feedbackModalRef,
  feedbackModalCloseRef,
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
  canContinue,
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
      </div>

      <div className="sfc-results-main">
        {steps.length > 1 && <nav className="sfc-stepper" aria-label="Feedback steps">
          {steps.map((item, index) => {
            const current = item === step;
            const visited = index <= maxVisited;
            return <button key={item} type="button" className={`sfc-step${current ? " is-current" : ""}${visited && !current ? " is-visited" : ""}`} disabled={!visited} aria-current={current ? "step" : undefined} onClick={() => setStep(item)}>
              <span className="sfc-step-num" aria-hidden="true">{visited && !current ? <Icon name="check" size={15} /> : index + 1}</span>
              <BiLabel zh={STEP_LABELS[item].zh} en={STEP_LABELS[item].en} />
            </button>;
          })}
        </nav>}
        <AudioCompare modelAudioUrl={modelAudioUrl} modelSentence={modelSentence} analysisAudioBlob={analysisAudioBlob} />
        {stepBody}
        <div className="sfc-results-utility">
          <button ref={feedbackTriggerRef} type="button" className="sfc-left-feedback-summary" aria-haspopup="dialog" aria-expanded={feedbackModalOpen} aria-controls="sfc-feedback-modal" onClick={onOpenFeedback}>
            <BiLabel zh="發音分析" en="Pronunciation feedback" />
            <span><BiLabel zh={practicePartCount > 0 ? `還有 ${practicePartCount} 個部分要練習` : "已通過評量音調"} en={practicePartCount > 0 ? `${practicePartCount} part${practicePartCount === 1 ? "" : "s"} to practise` : "Measured tones cleared"} /></span>
          </button>
        </div>
        <ResultsFooter {...{ hasPhrasePractice, allPhrasesCleared, remainingPracticePhrases, ready, canContinue, masteryPassed, practiceTargets, remainingDrillTargets, attempts, assistiveFeedback, assistiveRetriesUsed, onRecordAgain, hasNextScene, onNextScene, onViewSummary }} />
      </div>
    </div>

    {feedbackModalOpen && createPortal(
      <div className="sfc-feedback-modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onCloseFeedback(); }}>
        <section ref={feedbackModalRef} id="sfc-feedback-modal" className="sfc-feedback-modal" role="dialog" aria-modal="true" aria-labelledby="sfc-feedback-modal-title" tabIndex={-1}>
          <header className="sfc-feedback-modal-header"><div id="sfc-feedback-modal-title"><BiLabel zh="發音分析" en="Pronunciation feedback" /></div><button ref={feedbackModalCloseRef} type="button" className="sfc-feedback-modal-close" aria-label="Close pronunciation feedback" onClick={onCloseFeedback}><Icon name="close" size={18} /></button></header>
          <div className="sfc-feedback-modal-body"><PronunciationBreakdown words={praatMetrics.word_prosody || []} targetText={targetScript} transcription={recognizedText} teacherPhrases={teacherPhraseChunks} assistiveFeedback={assistiveFeedback} masteryCounts={masteryCounts} /></div>
        </section>
      </div>,
      document.body,
    )}

  </section>;
}

function ResultsFooter({ hasPhrasePractice, allPhrasesCleared, remainingPracticePhrases, ready, canContinue, masteryPassed, practiceTargets, remainingDrillTargets, attempts, assistiveFeedback, assistiveRetriesUsed, onRecordAgain, hasNextScene, onNextScene, onViewSummary }) {
  return <footer className="sfc-footer sfc-results-footer">
    {hasPhrasePractice && !allPhrasesCleared ? <p className="sfc-unlock-note"><Icon name="idea" size={15} /> <BiLabel zh={`還有 ${remainingPracticePhrases.length} 個部分可選擇練習；你也可以直接繼續。`} pinyin={`Hái yǒu ${remainingPracticePhrases.length} ge bùfen kě xuǎnzé liànxí; nǐ yě kěyǐ zhíjiē jìxù.`} en={`${remainingPracticePhrases.length} practice part${remainingPracticePhrases.length === 1 ? "" : "s"} remain optional; you can continue now.`} /></p>
      : hasPhrasePractice && allPhrasesCleared && !ready ? <p className="sfc-unlock-note"><Icon name="idea" size={15} /> <BiLabel zh="部分練習已完成；這次結果仍可查看，也可以直接繼續。" pinyin="Bùfèn liànxí yǐ wánchéng; zhè cì jiéguǒ réng kě chákàn, yě kěyǐ zhíjiē jìxù." en="Part practice is complete. Review this result or continue now." /></p>
        : !ready && !masteryPassed && practiceTargets.length > 0 ? <p className="sfc-unlock-note"><Icon name="idea" size={15} /> <BiLabel zh={`這些發音練習是可選的（還有 ${remainingDrillTargets.length > 0 ? `${remainingDrillTargets.length} 個部分` : "整句"}）；你可以直接繼續。`} pinyin={`Zhèxiē fāyīn liànxí shì kě xuǎn de; nǐ kěyǐ zhíjiē jìxù.`} en={`${remainingDrillTargets.length > 0 ? `${remainingDrillTargets.length} practice part${remainingDrillTargets.length > 1 ? "s" : ""}` : "The full sentence"} can be practiced optionally; you can continue now.`} /></p>
          : !ready ? <p className="sfc-unlock-note"><Icon name="idea" size={15} /> <BiLabel zh={`目前 ${attempts} 次練習；分數回饋僅供參考，你可以直接繼續。`} pinyin={`Mùqián ${attempts} cì liànxí; fēnshù huíkuì jǐn gōng cānkǎo, nǐ kěyǐ zhíjiē jìxù.`} en={`${attempts} attempt${attempts === 1 ? "" : "s"} recorded. Scores are feedback only; you can continue now.`} /></p> : null}
    {assistiveFeedback && shouldOfferRetry(worstState(assistiveFeedback), assistiveRetriesUsed) && <p className="sfc-assistive-retry-hint"><BiLabel zh="想再試一次這個音嗎？" pinyin="Xiǎng zài shì yí cì zhège yīn ma?" en="Want to try that tone once more? Totally optional." /></p>}
    <div className="sfc-footer-actions">
      <AppButton tone="subtle" className="sfc-btn-again" onClick={onRecordAgain}><Icon name="microphone" size={17} /> <BiLabel zh="再錄一次" pinyin="Zài lù yí cì" en="Record again" /></AppButton>
      {canContinue && (hasNextScene ? <AppButton tone="secondary" className="sfc-btn-next" onClick={onNextScene}><BiLabel k="next_scene" /> <Icon name="arrow-right" size={16} /></AppButton> : <AppButton tone="secondary" className="sfc-btn-next" onClick={onViewSummary}><BiLabel zh="查看總結" pinyin="Chákàn zǒngjié" en="View summary" /> <Icon name="arrow-right" size={16} /></AppButton>)}
    </div>
  </footer>;
}
