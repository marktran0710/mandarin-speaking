import { isContentAccepted } from "../utils/storyRecorderFeedback";
import type { PraatMetrics, Topic } from "./StoryRecorder";
import { BiLabel, BiText } from "./BiLabel";
import RecordingPlayback from "./RecordingPlayback";
import FeedbackSummary from "./FeedbackSummary";
import WordProsodyCard from "./WordProsodyCard";
import StudentFeedbackCards from "./StudentFeedbackCards";
import PraatTimeline from "./PraatTimeline";

const getToneName = (tone: number): string => {
  const toneNames: Record<number, string> = {
    1: "一聲 - 高平 Tone 1 - High Level (ma1)",
    2: "二聲 - 上升 Tone 2 - Rising (ma2)",
    3: "三聲 - 降升 Tone 3 - Falling-Rising (ma3)",
    4: "四聲 - 下降 Tone 4 - Falling (ma4)",
  };
  return toneNames[tone] || "聲調不明確 No clear tone";
};

interface PracticeAnalysisPanelProps {
  isTranscribing: boolean;
  isAnalyzing: boolean;
  error: string | null;
  praatMetrics: PraatMetrics | null;
  attemptHistory: Array<{ tone: number; fluency: number; attempt: number }>;
  narrativeMode: Topic["narrativeMode"];
  selectedImage: string;
  selectedImageIndex: number;
  sceneAttempts?: number;
  analysisAudioBlob: Blob | null;
  transcription: string;
}

export default function PracticeAnalysisPanel({
  isTranscribing,
  isAnalyzing,
  error,
  praatMetrics,
  attemptHistory,
  narrativeMode,
  selectedImage,
  selectedImageIndex,
  sceneAttempts,
  analysisAudioBlob,
  transcription,
}: PracticeAnalysisPanelProps) {
  const hasWordProsody = Boolean(praatMetrics?.word_prosody?.length);

  return (
    <>
      {(isTranscribing || isAnalyzing) && (
        <div className="analysis-loading-card">
          <div className="analysis-loading-spinner" />
          <div className="analysis-loading-text">
            <p className="analysis-loading-title">
              {isTranscribing ? (
                <BiLabel k="listening_to_your_voice" />
              ) : (
                <BiLabel k="analyzing_pronunciation" />
              )}
            </p>
            <p className="analysis-loading-sub">
              {isTranscribing ? (
                <BiLabel k="converting_speech_to_text" />
              ) : (
                <BiLabel k="checking_tones_rhythm_and_vocabulary" />
              )}
            </p>
          </div>
          <div className="analysis-loading-steps">
            <span
              className={`loading-step ${isTranscribing ? "active" : "done"}`}
            >
              <BiLabel k="transcribe" />
            </span>
            <span className="loading-step-arrow">→</span>
            <span
              className={`loading-step ${isAnalyzing && !isTranscribing ? "active" : ""}`}
            >
              Praat
            </span>
            <span className="loading-step-arrow">→</span>
            <span className="loading-step">
              <BiLabel k="feedback" />
            </span>
          </div>
        </div>
      )}
      {error && <p className="error">{error}</p>}

      {praatMetrics && (
        <section className="analysis-panel">
          {/* ── Main grid: left = scores & language feedback, right = playback ── */}
          <div className="ap-grid">
            <div className="ap-feedback-col">
              {/* ── Zone 1: Summary ─────────────────────────────────────── */}
              <FeedbackSummary
                praatMetrics={praatMetrics}
                attemptHistory={attemptHistory}
                transcription={praatMetrics.transcription || ""}
              />

              {/* ── Indirect corrective feedback: hint-only for the first two
              attempts; the correct version is revealed only after that. ── */}
              {narrativeMode !== "listen_retell" &&
                (() => {
                  const cf =
                    praatMetrics.ai_feedback?.corrective_feedback;
                  const accepted = isContentAccepted(praatMetrics);
                  const missing =
                    praatMetrics.ai_feedback?.vocabulary_coverage
                      ?.missing ?? [];

                  // Already correct — nothing to correct, so stay quiet here;
                  // FeedbackSummary already shows the success state.
                  if (accepted && missing.length === 0) return null;

                  if (cf?.reveal_answer && cf.correct_version) {
                    return (
                      <div className="practice-suggested-answer">
                        <p className="block-label practice-suggested-answer-heading">
                          <BiLabel zh="正確答案" pinyin="Zhèngquè dá'àn" en="Correct version" />
                        </p>
                        {cf.errors.length > 0 && (
                          <p className="practice-suggested-answer-text">
                            <BiLabel
                              zh="可能的錯誤："
                              pinyin="Kěnéng de cuòwù:"
                              en="Possible errors: "
                            />
                            {cf.errors.join("；")}
                          </p>
                        )}
                        <p className="practice-suggested-answer-text">
                          <strong>{cf.correct_version}</strong>
                        </p>
                      </div>
                    );
                  }

                  if (cf && (cf.errors.length > 0 || cf.hint)) {
                    return (
                      <div className="practice-suggested-answer is-hint">
                        <p className="block-label practice-suggested-answer-heading">
                          <BiLabel zh="提示" pinyin="Tíshì" en="Hint" />
                        </p>
                        {cf.errors.length > 0 && (
                          <p className="practice-suggested-answer-text">
                            <BiLabel
                              zh="可能的錯誤："
                              pinyin="Kěnéng de cuòwù:"
                              en="Possible errors: "
                            />
                            {cf.errors.join("；")}
                          </p>
                        )}
                        {cf.hint && (
                          <p className="practice-suggested-answer-text">
                            {cf.hint}
                          </p>
                        )}
                        <p className="practice-suggested-answer-text">
                          <BiLabel
                            zh="請再試一次。"
                            pinyin="Qǐng zài shì yí cì."
                            en="Please try again."
                          />
                        </p>
                      </div>
                    );
                  }
                  return null;
                })()}
            </div>
            {/* /ap-feedback-col */}

            {/* ── Right column: scene thumbnail + playback + positive signals ── */}
            <div className="ap-sidebar-col">
              {/* Scene thumbnail */}
              <div className="ap-scene-card">
                <img
                  src={selectedImage}
                  alt={`Scene ${selectedImageIndex + 1}`}
                  className="ap-scene-img"
                />
                <div className="ap-scene-label">
                  <span>
                    <BiLabel
                      zh={`場景 ${selectedImageIndex + 1}`}
                      pinyin={`Chǎngjǐng ${selectedImageIndex + 1}`}
                      en={`Scene ${selectedImageIndex + 1}`}
                    />
                  </span>
                  {sceneAttempts !== undefined && (
                    <span className="ap-scene-attempts">
                      <BiLabel
                        zh={`${sceneAttempts} 次`}
                        pinyin={`${sceneAttempts} cì`}
                        en={`${sceneAttempts} attempt${sceneAttempts > 1 ? "s" : ""}`}
                      />
                    </span>
                  )}
                </div>
              </div>
              {/* Scene vocabulary with used/missed status already lives on
              the Vocabulary tab (same data) — no need to repeat the
              whole table here too. */}

              {/* ── Zone 3: Listen back ──────────────────────────────────── */}
              <div className="listen-try-zone">
                {analysisAudioBlob && (
                  <RecordingPlayback blob={analysisAudioBlob} />
                )}
              </div>

              {(praatMetrics.ai_feedback?.vocabulary_coverage?.missing
                ?.length ?? 0) === 0 && (
                <div className="try-again-complete">
                  <span className="try-again-complete-icon">✓</span>
                  <div>
                    <p className="try-again-complete-title">
                      <BiLabel k="all_vocabulary_words_used" />
                    </p>
                    <p className="try-again-complete-hint">
                      <BiText k="now_work_on_pronunciation_record_again_a" />
                    </p>
                  </div>
                </div>
              )}
            </div>
            {/* /ap-sidebar-col */}
          </div>
          {/* /ap-grid */}

          <div className="word-prosody-section">
            <div className="word-prosody-header">
              <h3>
                <BiLabel k="character_by_character_prosody" />
              </h3>
              <p>
                <BiText k="pitch_movement_estimated_for_each_mandar" />
              </p>
            </div>
            {hasWordProsody ? (
              <div className="word-prosody-grid">
                {praatMetrics.word_prosody?.map((item) => (
                  <WordProsodyCard
                    key={`${item.token}-${item.index}`}
                    item={item}
                  />
                ))}
              </div>
            ) : (
              <div className="word-prosody-empty">
                <strong>
                  <BiLabel k="no_character_feedback_yet" />
                </strong>
                <p>
                  <BiText k="needs_a_clear_pitch_contour_and_transcri" />
                </p>
              </div>
            )}
          </div>

          {/* ── Zone 4: Advanced details (collapsed) ────────────────── */}
          <details className="advanced-praat-details">
            <summary>
              <BiLabel k="advanced_analysis_details" />
            </summary>

            <div className="metrics-section">
              <div className="metric-card tone-card">
                <div className="metric-label">
                  <BiLabel k="dominant_pitch_shape" />
                </div>
                <div className="metric-value compact">
                  {getToneName(praatMetrics.detected_tone)}
                </div>
                <div className="metric-subtext">
                  <BiLabel k="tone_accuracy_score_shown_in_the_summary" />
                </div>
              </div>
              <div className="metric-card rate-card">
                <div className="metric-label">
                  <BiLabel k="speech_rate" />
                </div>
                <div className="metric-value">
                  {praatMetrics.speech_rate.toFixed(1)}
                </div>
                <div className="metric-subtext">
                  {praatMetrics.speech_rate < 2.5 ? (
                    <BiLabel k="too_slow_add_more_flow" />
                  ) : praatMetrics.speech_rate > 6.5 ? (
                    <BiLabel k="too_fast_slow_each_tone" />
                  ) : (
                    <BiLabel k="syllables_sec_good_pace" />
                  )}
                </div>
              </div>
              {praatMetrics.pause_analysis &&
              praatMetrics.pause_analysis.duration > 0 ? (
                <div className="metric-card pause-card">
                  <div className="metric-label">
                    <BiLabel k="pauses" />
                  </div>
                  <div className="metric-value">
                    {praatMetrics.pause_analysis.pause_count}
                  </div>
                  <div className="metric-subtext">
                    {praatMetrics.pause_analysis.pause_count === 0 ? (
                      <BiLabel k="no_long_pauses_smooth_delivery" />
                    ) : praatMetrics.pause_analysis.longest_pause >=
                      0.8 ? (
                      <BiLabel
                        zh={`最長間隔：${praatMetrics.pause_analysis.longest_pause.toFixed(1)}s`}
                        pinyin={`Zuì cháng jiàngé: ${praatMetrics.pause_analysis.longest_pause.toFixed(1)}s`}
                        en={`Longest gap: ${praatMetrics.pause_analysis.longest_pause.toFixed(1)}s`}
                      />
                    ) : (
                      <BiLabel
                        zh={`${praatMetrics.pause_analysis.pause_count} 次短停頓 — 快要流暢了`}
                        pinyin={`${praatMetrics.pause_analysis.pause_count} cì duǎn tíngdùn — kuàiyào liúchàng le`}
                        en={`${praatMetrics.pause_analysis.pause_count} short pause${praatMetrics.pause_analysis.pause_count > 1 ? "s" : ""} — nearly fluent`}
                      />
                    )}
                  </div>
                </div>
              ) : (
                <div className="metric-card fluency-card">
                  <div className="metric-label">
                    <BiLabel k="fluency" />
                  </div>
                  <div className="metric-value">
                    {Math.round(praatMetrics.fluency_score)}
                  </div>
                  <div className="metric-bar">
                    <div
                      className="metric-fill"
                      style={{
                        width: `${praatMetrics.fluency_score}%`,
                      }}
                    />
                  </div>
                </div>
              )}
              {praatMetrics.vowel_quality && (
                <div className="metric-card vowel-card">
                  <div className="metric-label">
                    <BiLabel k="vowel_quality" />
                  </div>
                  <div className="metric-value compact">
                    {praatMetrics.vowel_quality.split(" — ")[0]}
                  </div>
                  <div className="metric-subtext">
                    {praatMetrics.vowel_quality.split(" — ")[1] || ""}
                  </div>
                </div>
              )}
            </div>

            <StudentFeedbackCards
              toneAccuracy={praatMetrics.tone_accuracy}
              fluencyScore={praatMetrics.fluency_score}
              speechRate={praatMetrics.speech_rate}
              wordProsody={praatMetrics.word_prosody || []}
              pauseAnalysis={praatMetrics.pause_analysis}
            />

            <PraatTimeline
              audioBlob={analysisAudioBlob}
              pitchContour={praatMetrics.pitch_contour}
              wordProsody={praatMetrics.word_prosody}
              transcription={transcription}
            />

            <div className="formants-detail">
              <h3>
                <BiLabel k="formant_measurements" />
              </h3>
              <div className="formants-grid">
                {["F1", "F2", "F3"].map((f) => (
                  <div className="formant" key={f}>
                    <span>{f}</span>
                    <strong>
                      {Math.round(praatMetrics.formants[f] || 0)} Hz
                    </strong>
                  </div>
                ))}
              </div>
            </div>
          </details>
        </section>
      )}
    </>
  );
}
