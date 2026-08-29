// @ts-nocheck
import { BiLabel } from "./BiLabel";
import AppButton from "./AppButton";
import Icon from "../shared/ui/Icon";
import ContentDiffDisplay from "./ContentDiffDisplay";
import VoiceFeedbackReliabilityNotice, {
  AssistiveFeedbackNotice,
} from "./VoiceFeedbackReliabilityNotice";
import { worstState } from "../utils/assistiveFeedback";
import {
  SELF_EVAL_EMOJI,
  systemContentLevel,
  systemPronunciationLevel,
} from "../utils/selfEvalComparison";
import { ProgressSnapshot } from "./SpeakingResultsFlow.helpers";

export default function SpeakingResultsOverviewStep({
  verdict,
  verdictContent,
  feedbackReliability,
  attempts,
  hasTargetScript,
  targetScript,
  recognizedText,
  praatMetrics,
  pronunciationMastery,
  contentNeedsRetry,
  selfEvalAnswer,
  hasScriptMismatch,
  submittedAudioName,
  practicePartCount,
  assistiveFeedback,
  analysisVersion,
  comparison,
  hasFix,
  hasPractice,
  hasPhrasePractice,
  goToStep,
  onRecordAgain,
}) {
  return (
    <div className="sfc-step-panel">
      <header
        className={`sfc-verdict ${verdictContent.className}${verdictContent.text ? "" : " sfc-verdict--compact"}`}
      >
        <div className="sfc-verdict-lead">
          <span className="sfc-verdict-icon" aria-hidden="true">
            {verdictContent.icon}
          </span>
          {verdictContent.text && (
            <p className="sfc-verdict-text">{verdictContent.text}</p>
          )}
        </div>
      </header>

      <VoiceFeedbackReliabilityNotice assessment={feedbackReliability} attemptCount={attempts} />
      {hasTargetScript && (
        <ContentDiffDisplay
          target={targetScript}
          heard={recognizedText || null}
          diff={praatMetrics.content_diff}
          contentMatch={praatMetrics.content_match}
        />
      )}
      {pronunciationMastery && (
        <div
          className={`sfc-mastery-banner${pronunciationMastery.status === "passed" ? " is-cleared" : ""}`}
          role="status"
          aria-label="Pronunciation mastery status"
        >
          <p className="sfc-mastery-lead">
            {contentNeedsRetry
              ? "Content not verified — record the script again"
              : pronunciationMastery.status === "passed"
                ? "✓ Pronunciation passed"
                : pronunciationMastery.status === "not_judged"
                  ? "尚未判定 / Not judged yet"
                  : "發音需要練習 / Needs practice"}
          </p>
          {pronunciationMastery.message && <p>{pronunciationMastery.message}</p>}
          {contentNeedsRetry && <small>Tone measurements are reference-only until the script matches.</small>}
        </div>
      )}

      {selfEvalAnswer && (
        <div className="self-eval-compare">
          <div className="self-eval-compare-row">
            <span className="self-eval-compare-label"><BiLabel zh="意思" en="Meaning" /></span>
            <span className="self-eval-compare-side"><BiLabel zh="你" en="You" /> <span className="self-eval-compare-emoji">{SELF_EVAL_EMOJI[selfEvalAnswer.content]}</span></span>
            <span className="self-eval-compare-side"><BiLabel zh="系統" en="System" /> <span className="self-eval-compare-emoji">{SELF_EVAL_EMOJI[systemContentLevel(praatMetrics, hasScriptMismatch)]}</span></span>
          </div>
          <div className="self-eval-compare-row">
            <span className="self-eval-compare-label"><BiLabel zh="發音" en="Pronunciation" /></span>
            <span className="self-eval-compare-side"><BiLabel zh="你" en="You" /> <span className="self-eval-compare-emoji">{SELF_EVAL_EMOJI[selfEvalAnswer.pronunciation]}</span></span>
            <span className="self-eval-compare-side"><BiLabel zh="系統" en="System" /> <span className="self-eval-compare-emoji">{SELF_EVAL_EMOJI[systemPronunciationLevel(praatMetrics)]}</span></span>
          </div>
        </div>
      )}

      {(recognizedText || submittedAudioName) && (
        <div className="sfc-results-scene-extras">
          {recognizedText && <p className="sfc-transcript"><BiLabel k="you_said" /> <em lang="zh-TW">{recognizedText}</em></p>}
          {submittedAudioName && <p className="submitted-audio-name">✓ {submittedAudioName}</p>}
        </div>
      )}
      <ProgressSnapshot attempts={attempts} mastery={pronunciationMastery} practicePartCount={practicePartCount} />
      {assistiveFeedback && assistiveFeedback.length > 0 && (() => {
        const rolledUpState = worstState(assistiveFeedback);
        return rolledUpState ? <AssistiveFeedbackNotice state={rolledUpState} /> : null;
      })()}

      {analysisVersion === "phoneme_tone_v2" && (
        <section className="experimental-analysis-panel" aria-label="Experimental analysis">
          <div className="experimental-analysis-heading"><strong>Experimental V2</strong><span className="analysis-version-badge">Character + phoneme + T1–T5</span></div>
          <p>This result is for evaluation only and does not change progression or mastery.</p>
          {praatMetrics.character_prosody?.length ? (
            <div className="experimental-character-grid">
              {praatMetrics.character_prosody.map((item) => <div className="experimental-character-card" key={`${item.char_index}-${item.char}`}><strong>{item.char}</strong><span>{item.pinyin}</span><small>Expected T{item.expected_tone ?? "?"} · Detected {item.detected_tone ? `T${item.detected_tone}` : item.tone_status}</small></div>)}
            </div>
          ) : <p>Character alignment is not available for this attempt.</p>}
        </section>
      )}

      {comparison && (
        <section className="analysis-compare-panel" aria-label="Stable and experimental comparison">
          <h3>Comparison</h3>
          <div className="analysis-compare-grid">
            {["stable_v1", "phoneme_tone_v2"].map((version) => {
              const run = comparison.runs[version];
              return <div className="analysis-compare-card" key={version}><strong>{version === "stable_v1" ? "Stable V1 — Current" : "Experimental V2"}</strong><span>{run?.status ?? "not run"} · {run?.latencyMs ?? 0} ms</span>{run?.error ? <small>{run.error}</small> : run?.result?.character_prosody ? <small>{run.result.character_prosody.length} characters aligned</small> : <small>Current tone and prosody result</small>}</div>;
            })}
          </div>
        </section>
      )}

      {verdict === "meaning" && hasFix && <AppButton tone="primary" className="sfc-btn-next sfc-step-cta" onClick={() => goToStep("fix")}><BiLabel zh="看怎麼改" en="See how to fix it" /> →</AppButton>}
      {verdict === "vocab" && hasFix && <AppButton tone="primary" className="sfc-btn-next sfc-step-cta" onClick={() => goToStep("fix")}><BiLabel zh="看少了的生詞" en="See the missing words" /> →</AppButton>}
      {verdict === "join" && <AppButton tone="primary" className="sfc-btn-next sfc-step-cta" onClick={onRecordAgain}><Icon name="microphone" size={17} /> <BiLabel zh="再錄一次，說順一點" en="Record again, smoother this time" /></AppButton>}
      {verdict === "pronounce" && (hasPractice ? <AppButton tone="primary" className="sfc-btn-next sfc-step-cta" onClick={() => goToStep("practice")}><BiLabel zh="練習生詞" en={hasPhrasePractice ? "Practice the parts" : "Practice the words"} /> →</AppButton> : <AppButton tone="primary" className="sfc-btn-next sfc-step-cta" onClick={onRecordAgain}><Icon name="microphone" size={17} /> <BiLabel zh="再錄一次" en="Record again" /></AppButton>)}
    </div>
  );
}
