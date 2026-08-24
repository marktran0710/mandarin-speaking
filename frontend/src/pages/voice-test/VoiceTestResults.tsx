import PraatTimeline from "../../components/PraatTimeline";
import { BiLabel, BiText } from "../../components/BiLabel";
import VoiceFeedbackReliabilityNotice from "../../components/VoiceFeedbackReliabilityNotice";
import { assessVoiceFeedbackReliability } from "../../utils/voiceFeedbackReliability";
import { normalizeWordProsody } from "./helpers";
import { FeedbackBlock, formatContourShape, getToneFocusItems, ModelExampleCard, ScoreCard, ScriptWordLevel, StudentFeedbackCards } from "./VoiceFeedbackComponents";
import type { VoiceMetrics } from "./types";

export default function VoiceTestResults({ metrics, audioBlob, attemptCount }: { metrics: VoiceMetrics; audioBlob: Blob | null; attemptCount: number }) {
  const feedbackReliability = assessVoiceFeedbackReliability({ feedbackQuality: metrics.feedback_quality, pitchContour: metrics.pitch_contour, wordProsody: metrics.word_prosody, transcription: metrics.transcription });
  return <section className="voice-feedback-panel">
    <VoiceFeedbackReliabilityNotice assessment={feedbackReliability} attemptCount={attemptCount} />
    {feedbackReliability.level !== "retry" && <><div className="voice-score-grid">
      <ScoreCard label={<BiLabel zh="流暢度" pinyin="Liúchàng dù" en="Fluency" />} value={`${Math.round(metrics.fluency_score)}/100`} />
      <ScoreCard label={<BiLabel zh="聲調準確度" pinyin="Shēngdiào zhǔnquè dù" en="Tone accuracy" />} value={`${Math.round(metrics.tone_accuracy)}%`} />
      <ScoreCard label={<BiLabel zh="語速" pinyin="Yǔsù" en="Speech rate" />} value={`${metrics.speech_rate.toFixed(1)}/s`} />
    </div><StudentFeedbackCards toneAccuracy={metrics.tone_accuracy} fluencyScore={metrics.fluency_score} speechRate={metrics.speech_rate} wordProsody={metrics.word_prosody || []} /></>}
    {metrics.transcription && <ModelExampleCard text={metrics.transcription} focusWord={getToneFocusItems(metrics.word_prosody || [])[0]?.token} />}
    <div className="voice-feedback-card"><h2><BiLabel zh="音檔轉錄結果" pinyin="Yīndǎng zhuǎnlù jiéguǒ" en="Transcription from audio" /></h2>
      {metrics.description && <p className="voice-result-description">{metrics.description}</p>}
      <p className="voice-transcript-text">{metrics.transcription || <BiText zh="沒有轉錄結果，以下數據以音檔本身為準。" pinyin="Méiyǒu zhuǎnlù jiéguǒ, yǐxià shùjù yǐ yīndǎng běnshēn wéi zhǔn." en="No transcription was returned. Praat metrics are based on the audio file." />}</p>
      <ScriptWordLevel transcription={metrics.transcription || ""} wordProsody={metrics.word_prosody} />
      {metrics.transcription_model && <small className="voice-model-note"><BiLabel zh={`辨識模型：${metrics.transcription_model}`} en={`ASR model: ${metrics.transcription_model}`} /></small>}
    </div>
    {feedbackReliability.level !== "retry" && <details className="voice-advanced-details"><summary><BiLabel zh="進階 Praat 詳細資料" pinyin="Jìnjiē Praat xiángxì zīliào" en="Advanced Praat details" /></summary>
      <div className="voice-feedback-card"><h2><BiLabel zh="Praat 回饋" pinyin="Praat huíkuì" en="Praat feedback" /></h2><p>{metrics.feedback}</p></div>
      <div className="voice-feedback-card voice-praat-visual-card"><h2><BiLabel zh="Praat 視覺化圖表" pinyin="Praat shìjué huà túbiǎo" en="Praat visualization" /></h2><PraatTimeline audioBlob={audioBlob} pitchContour={metrics.pitch_contour} wordProsody={normalizeWordProsody(metrics.word_prosody)} transcription={metrics.transcription || ""} /></div>
      {metrics.word_prosody && metrics.word_prosody.length > 0 && <div className="voice-feedback-card"><h2><BiLabel zh="逐字韻律分析" pinyin="Zhúzì yùnlǜ fēnxī" en="Word-level prosody" /></h2><div className="voice-word-grid">{metrics.word_prosody.map((word) => <div className="voice-word-card" key={`${word.token}-${word.index}`}><strong lang="zh-Hant">{word.token}</strong><span><BiLabel {...formatContourShape(word.contour_shape)} /></span><small><BiLabel zh={`平均 ${Math.round(word.mean_pitch)} Hz · 範圍 ${Math.round(word.pitch_range)} Hz`} en={`${Math.round(word.mean_pitch)} Hz avg · ${Math.round(word.pitch_range)} Hz range`} /></small><p>{word.feedback}</p></div>)}</div></div>}
    </details>}
    {metrics.transcription && metrics.ai_feedback && metrics.feedback_quality?.can_score_content !== false && <div className="voice-feedback-card ai-card"><div className="ai-card-header"><h2><BiLabel zh="AI 回饋" pinyin="AI huíkuì" en="AI feedback" /></h2><span>{metrics.ai_feedback.provider}</span></div><div className="ai-feedback-columns"><FeedbackBlock title={<BiLabel zh="流暢度" pinyin="Liúchàng dù" en="Fluency" />} score={metrics.ai_feedback.fluency.score} text={metrics.ai_feedback.fluency.feedback} /><FeedbackBlock title={<BiLabel zh="文法" pinyin="Wénfǎ" en="Grammar" />} score={metrics.ai_feedback.grammar.score} text={metrics.ai_feedback.grammar.feedback} /><FeedbackBlock title={<BiLabel zh="詞彙" pinyin="Cíhuì" en="Vocabulary" />} score={metrics.ai_feedback.vocabulary.score} text={metrics.ai_feedback.vocabulary.feedback} /></div>{metrics.ai_feedback.improved_version && <p className="improved-version"><strong><BiLabel zh="改進版本：" pinyin="Gǎijìn bǎnběn:" en="Improved version:" /></strong>{" "}{metrics.ai_feedback.improved_version}</p>}<p className="practice-prompt"><strong><BiLabel zh="下一步練習：" pinyin="Xià yí bù liànxí:" en="Practice next:" /></strong>{" "}{metrics.ai_feedback.practice_prompt}</p></div>}
  </section>;
}
