import { useEffect, useRef, useState, type ChangeEvent } from "react";
import { BiLabel, BiText } from "./BiLabel";
import RecordingPlayback from "./RecordingPlayback";
import WordProsodyCard from "./WordProsodyCard";
import { scoreTier, scoreTierLabel } from "../utils/scoreLabels";
import {
  isContentAccepted,
  sceneReady,
  weakToneGuideItems,
} from "../utils/storyRecorderFeedback";
import type {
  AiProviderOption,
  PraatMetrics,
  SpeechModel,
  Topic,
} from "./StoryRecorder";
import "./SpeakingFlowCard.css";

interface SceneProgressEntry {
  attempts: number;
  bestTone: number;
  bestFluency: number;
}

interface SpeakingFlowCardProps {
  selectedImage: string;
  selectedImageIndex: number;
  totalScenes: number;
  modelSentence?: string;
  narrativeMode: Topic["narrativeMode"];
  prog?: SceneProgressEntry;
  praatMetrics: PraatMetrics | null;
  analysisAudioBlob: Blob | null;
  error: string | null;
  isRecording: boolean;
  isBusy: boolean;
  isTranscribing: boolean;
  isAnalyzing: boolean;
  recordingDuration: number;
  silenceDuration: number;
  submittedAudioName: string;
  selectedModel: SpeechModel;
  onSelectedModelChange: (model: SpeechModel) => void;
  aiProviders: AiProviderOption[];
  aiProvider: string;
  onAiProviderChange: (value: string) => void;
  recordingButtonDisabled: boolean;
  onPrimaryRecordingAction: () => void;
  onSubmitVoiceFile: (event: ChangeEvent<HTMLInputElement>) => void;
  hasNextScene: boolean;
  onNextScene: () => void;
  onViewSummary: () => void;
}

/** The Speaking step as a two-screen app flow inside one fixed-height card:
 *
 *   record  →  (analyzing)  →  results  →  next scene / record again
 *
 * The results screen *replaces* the record controls, so a student always
 * passes through their feedback before acting — and the Next Scene button
 * lives on that screen, locked behind the same sceneReady rule the journey
 * path uses (score threshold, or enough attempts). No page scrolling: both
 * screens lay out inside the card's height. */
export default function SpeakingFlowCard({
  selectedImage,
  selectedImageIndex,
  totalScenes,
  modelSentence,
  narrativeMode,
  prog,
  praatMetrics,
  analysisAudioBlob,
  error,
  isRecording,
  isBusy,
  isTranscribing,
  isAnalyzing,
  recordingDuration,
  silenceDuration,
  submittedAudioName,
  selectedModel,
  onSelectedModelChange,
  aiProviders,
  aiProvider,
  onAiProviderChange,
  recordingButtonDisabled,
  onPrimaryRecordingAction,
  onSubmitVoiceFile,
  hasNextScene,
  onNextScene,
  onViewSummary,
}: SpeakingFlowCardProps) {
  const [screen, setScreen] = useState<"record" | "results">("record");
  const [view, setView] = useState<"overview" | "words">("overview");

  // Flip to results exactly when an analysis finishes (busy → idle with
  // fresh metrics) — not merely "metrics exist", which would trap the
  // student on the results screen after choosing to record again.
  const wasBusy = useRef(false);
  useEffect(() => {
    if (wasBusy.current && !isBusy && praatMetrics) {
      setScreen("results");
      setView("overview");
    }
    wasBusy.current = isBusy;
  }, [isBusy, praatMetrics]);

  // A new scene always starts back at the record screen.
  useEffect(() => {
    setScreen("record");
    setView("overview");
  }, [selectedImageIndex]);

  const attempts = prog?.attempts ?? 0;
  const ready = prog ? sceneReady(prog) : false;

  const ai = praatMetrics?.ai_feedback;
  const accepted = praatMetrics ? isContentAccepted(praatMetrics) : true;
  const vocabCoverage = ai?.vocabulary_coverage;
  const missing = vocabCoverage?.missing ?? [];
  const usedCount = vocabCoverage?.used?.length ?? 0;
  const vocabTotal = usedCount + missing.length;
  const toneScore = Math.round(praatMetrics?.tone_accuracy ?? 0);
  const weakItems = weakToneGuideItems(praatMetrics?.word_prosody || []);
  const contentAccuracy = ai?.content_accuracy;
  const corrective = ai?.corrective_feedback;

  // The one-verdict ladder: meaning gates everything, then the unlock
  // state, then vocabulary, then pronunciation polish.
  const verdict: "meaning" | "ready" | "vocab" | "pronounce" = !accepted
    ? "meaning"
    : ready
      ? "ready"
      : missing.length > 0
        ? "vocab"
        : "pronounce";

  const sceneChip = (
    <span className="sfc-scene-chip">
      <BiLabel
        zh={`場景 ${selectedImageIndex + 1}/${totalScenes}`}
        pinyin={`Chǎngjǐng ${selectedImageIndex + 1}/${totalScenes}`}
        en={`Scene ${selectedImageIndex + 1} of ${totalScenes}`}
      />
      {attempts > 0 && (
        <span className="sfc-attempt-chip">
          <BiLabel
            zh={`第 ${attempts} 次`}
            pinyin={`Dì ${attempts} cì`}
            en={`Attempt ${attempts}`}
          />
        </span>
      )}
    </span>
  );

  // ── Analyzing overlay (either screen) ─────────────────────────────────
  if (isTranscribing || isAnalyzing) {
    return (
      <section className="speaking-flow-card sfc-analyzing" aria-label="Analyzing recording">
        <div className="analysis-loading-card sfc-loading">
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
            <span className={`loading-step ${isTranscribing ? "active" : "done"}`}>
              <BiLabel k="transcribe" />
            </span>
            <span className="loading-step-arrow">→</span>
            <span className={`loading-step ${isAnalyzing && !isTranscribing ? "active" : ""}`}>
              Praat
            </span>
            <span className="loading-step-arrow">→</span>
            <span className="loading-step">
              <BiLabel k="feedback" />
            </span>
          </div>
        </div>
      </section>
    );
  }

  // ── Screen 1: record ──────────────────────────────────────────────────
  if (screen === "record") {
    return (
      <section className="speaking-flow-card sfc-screen" aria-label="Record your story">
        <div className="sfc-record-grid">
          <div className="sfc-scene-panel">
            <img src={selectedImage} alt={`Scene ${selectedImageIndex + 1}`} />
            {modelSentence && (
              <div className="practice-model-sentence sfc-model-sentence">
                <p className="block-label practice-model-sentence-label">
                  <BiLabel k="speaking_model_sentence" />
                </p>
                <p className="practice-model-sentence-text" lang="zh-Hant">
                  {modelSentence}
                </p>
              </div>
            )}
          </div>

          <div className="sfc-record-panel">
            <div className="sfc-record-top">
              {sceneChip}
              <h3 className="sfc-record-title">
                <BiLabel k="record_your_story" />
              </h3>
            </div>

            <button
              type="button"
              onClick={onPrimaryRecordingAction}
              disabled={recordingButtonDisabled}
              className={`btn-practice-record sfc-record-btn${isRecording ? " is-recording" : ""}`}
            >
              {isRecording ? (
                <BiLabel k="stop_recording" />
              ) : (
                <BiLabel k="record" />
              )}
            </button>
            {isRecording && (
              <div className="practice-timer">
                <span>{recordingDuration}s</span>
                {selectedModel === "webspeech" && (
                  <span className="practice-silence">
                    <BiLabel
                      zh={`靜音 ${silenceDuration}s / 7s`}
                      pinyin={`Jìngyīn ${silenceDuration}s / 7s`}
                      en={`silence ${silenceDuration}s / 7s`}
                    />
                  </span>
                )}
              </div>
            )}

            {!isRecording && (
              <ol className="sfc-steps-preview" aria-label="What happens next">
                <li>
                  <span className="sfc-step-num">1</span>
                  <BiLabel zh="錄音" pinyin="Lùyīn" en="Record" />
                </li>
                <li>
                  <span className="sfc-step-num">2</span>
                  <BiLabel zh="AI 分析" pinyin="AI fēnxī" en="AI listens" />
                </li>
                <li>
                  <span className="sfc-step-num">3</span>
                  <BiLabel zh="看回饋，變更好" pinyin="Kàn huíkuì, biàn gèng hǎo" en="Read feedback, improve" />
                </li>
              </ol>
            )}

            <label
              className={`btn-practice-upload${isBusy ? " disabled" : ""}`}
              role="button"
              tabIndex={isBusy ? -1 : 0}
            >
              <BiLabel k="upload_audio" />
              <input
                className="submit-voice-input"
                type="file"
                accept="audio/*,.wav,.wave,.webm,.mp3,.m4a,.ogg"
                onChange={onSubmitVoiceFile}
                disabled={isBusy}
              />
            </label>
            {submittedAudioName && (
              <p className="submitted-audio-name">✓ {submittedAudioName}</p>
            )}
            {error && <p className="error sfc-error">{error}</p>}

            <details className="practice-model-picker sfc-options">
              <summary>
                <BiLabel k="recording_options" />
              </summary>
              {aiProviders.length > 0 && (
                <>
                  <label className="practice-model-label" htmlFor="ai-engine-select">
                    <BiLabel k="ai_engine" />
                  </label>
                  <select
                    id="ai-engine-select"
                    value={aiProvider}
                    onChange={(e) => {
                      const next = e.target.value;
                      onAiProviderChange(next);
                      if (next === "groq") onSelectedModelChange("groq");
                    }}
                    disabled={isBusy}
                  >
                    {aiProviders.map((p) => (
                      <option
                        key={p.id}
                        value={p.id}
                        disabled={!p.available || p.id === "local"}
                      >
                        {p.label}
                        {p.available && p.id !== "local" ? "" : " 🔒"}
                      </option>
                    ))}
                  </select>
                </>
              )}
              <label className="practice-model-label" htmlFor="speech-source">
                <BiLabel k="speech_source" />
              </label>
              <select
                id="speech-source"
                value={selectedModel}
                onChange={(e) => onSelectedModelChange(e.target.value as SpeechModel)}
                disabled={isBusy}
              >
                <option value="webspeech">
                  瀏覽器（繁體中文） Browser (Traditional Chinese)
                </option>
                <option value="groq">
                  Groq Whisper（免費，雲端） Groq Whisper (free, cloud)
                </option>
                <option value="ctwhisper">
                  Whisper（中文／台語，本地） Whisper (Chinese / Taiwanese, local)
                </option>
                <option value="vibevoice">
                  VibeVoice-ASR（本地檔案） VibeVoice-ASR (local file)
                </option>
              </select>
            </details>
          </div>
        </div>
      </section>
    );
  }

  // ── Screen 2: results ─────────────────────────────────────────────────
  const verdictContent = {
    meaning: {
      icon: "🧭",
      className: "sfc-verdict-meaning",
      text: (
        <BiLabel
          zh="先修正句子的意思，再管發音。"
          pinyin="Xiān xiūzhèng jùzi de yìsi, zài guǎn fāyīn."
          en="Fix what your sentence means first — pronunciation comes after."
        />
      ),
    },
    vocab: {
      icon: "📝",
      className: "sfc-verdict-vocab",
      text: (
        <BiLabel
          zh={`還缺 ${missing.length} 個詞：${missing.slice(0, 3).join("、")}`}
          pinyin={`Hái quē ${missing.length} ge cí: ${missing.slice(0, 3).join("、")}`}
          en={`${missing.length} word${missing.length > 1 ? "s" : ""} still missing: ${missing.slice(0, 3).join("、")}`}
        />
      ),
    },
    pronounce: {
      icon: "🎯",
      className: "sfc-verdict-pronounce",
      text: weakItems[0] ? (
        <BiLabel
          zh={`詞彙都用到了！現在練「${weakItems[0].token}」的聲調。`}
          pinyin={`Cíhuì dōu yòng dào le! Xiànzài liàn “${weakItems[0].token}” de shēngdiào.`}
          en={`All words used! Now practice the tone of "${weakItems[0].token}".`}
        />
      ) : (
        <BiLabel
          zh="再錄一次，讓聲調更清楚。"
          pinyin="Zài lù yí cì, ràng shēngdiào gèng qīngchu."
          en="Record again and make your tones clearer."
        />
      ),
    },
    ready: {
      icon: "🎉",
      className: "sfc-verdict-ready",
      text: (
        <BiLabel
          zh={`場景 ${selectedImageIndex + 1} 完成！可以前往下一個場景。`}
          pinyin={`Chǎngjǐng ${selectedImageIndex + 1} wánchéng! Kěyǐ qiánwǎng xià yí ge chǎngjǐng.`}
          en={`Scene ${selectedImageIndex + 1} complete! You can move on.`}
        />
      ),
    },
  }[verdict];

  const meaningJudged = Boolean(contentAccuracy?.judged);
  const hasVocabList = vocabCoverage !== undefined && vocabTotal > 0;
  const showCorrective =
    narrativeMode !== "listen_retell" &&
    !(accepted && missing.length === 0) &&
    corrective &&
    (corrective.errors.length > 0 || corrective.hint || corrective.correct_version);

  return (
    <section className="speaking-flow-card sfc-results sfc-screen" aria-label="Recording results">
      <div className="sfc-results-grid">
        {/* The scene image persists from the record screen — the anchor
            that makes record → results read as one continuous place. */}
        <aside className="sfc-results-scene">
          <img src={selectedImage} alt={`Scene ${selectedImageIndex + 1}`} />
          {analysisAudioBlob && <RecordingPlayback blob={analysisAudioBlob} />}
          {praatMetrics?.transcription && (
            <p className="sfc-transcript">
              <BiLabel k="you_said" />{" "}
              <em lang="zh-TW">{praatMetrics.transcription}</em>
            </p>
          )}
          {submittedAudioName && (
            <p className="submitted-audio-name">✓ {submittedAudioName}</p>
          )}
        </aside>

        <div className="sfc-results-main">
          <header className={`sfc-verdict ${verdictContent.className}`}>
            <span className="sfc-verdict-icon" aria-hidden="true">
              {verdictContent.icon}
            </span>
            <p className="sfc-verdict-text">{verdictContent.text}</p>
            {sceneChip}
          </header>

          <div className="sfc-step-chips" role="group" aria-label="Result checklist">
            <button
              type="button"
              className={`sfc-step-chip${view === "overview" ? " active" : ""}`}
              onClick={() => setView("overview")}
            >
              <span className={`sfc-chip-status ${meaningJudged ? (accepted ? "pass" : "fail") : ""}`}>
                {meaningJudged ? (accepted ? "✓" : "✗") : "①"}
              </span>
              <BiLabel zh="意思" pinyin="Yìsi" en="Meaning" />
            </button>
            <span className="sfc-chip-link" aria-hidden="true" />
            <button
              type="button"
              className={`sfc-step-chip${view === "overview" ? " active" : ""}`}
              onClick={() => setView("overview")}
            >
              <span className={`sfc-chip-status ${hasVocabList ? (missing.length === 0 ? "pass" : "fail") : ""}`}>
                {hasVocabList ? `${usedCount}/${vocabTotal}` : "②"}
              </span>
              <BiLabel zh="詞彙" pinyin="Cíhuì" en="Vocabulary" />
            </button>
            <span className="sfc-chip-link" aria-hidden="true" />
            <button
              type="button"
              className={`sfc-step-chip${view === "words" ? " active" : ""}`}
              onClick={() => setView("words")}
            >
              <span className={`sfc-chip-status score-tier-text ${scoreTier(toneScore)}`}>
                {scoreTierLabel(scoreTier(toneScore)).zh}
              </span>
              <BiLabel zh="發音" pinyin="Fāyīn" en="Pronunciation" />
            </button>
          </div>

          <div className="sfc-body">
            {view === "overview" && (
              <div className="sfc-overview">
                {meaningJudged && contentAccuracy?.feedback && (
                  <div
                    className={`content-accuracy-panel ${accepted ? "is-accepted" : "is-rejected"}`}
                  >
                    <p className="content-accuracy-feedback">
                      {contentAccuracy.feedback}
                    </p>
                    {contentAccuracy.missed_details.length > 0 && (
                      <p className="content-accuracy-missed">
                        ✗ {contentAccuracy.missed_details.join(", ")}
                      </p>
                    )}
                  </div>
                )}

                {showCorrective && (
                  <div
                    className={`practice-suggested-answer${corrective!.reveal_answer ? "" : " is-hint"}`}
                  >
                    <p className="block-label practice-suggested-answer-heading">
                      {corrective!.reveal_answer ? (
                        <BiLabel zh="正確答案" pinyin="Zhèngquè dá'àn" en="Correct version" />
                      ) : (
                        <BiLabel zh="提示" pinyin="Tíshì" en="Hint" />
                      )}
                    </p>
                    {corrective!.hint && (
                      <p className="practice-suggested-answer-text">{corrective!.hint}</p>
                    )}
                    {corrective!.reveal_answer && corrective!.correct_version && (
                      <p className="practice-suggested-answer-text">
                        <strong>{corrective!.correct_version}</strong>
                      </p>
                    )}
                  </div>
                )}

                {hasVocabList && missing.length > 0 && (
                  <div className="sfc-missing-words">
                    <p className="block-label">
                      <BiLabel zh="試著加入" pinyin="Shìzhe jiārù" en="Try to include" />
                    </p>
                    <div className="sfc-missing-chips">
                      {missing.map((w) => (
                        <span key={w} className="vocab-chip sfc-missing-chip">
                          {w}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {verdict === "pronounce" && weakItems.length > 0 && (
                  <button
                    type="button"
                    className="sfc-goto-words"
                    onClick={() => setView("words")}
                  >
                    <BiLabel
                      zh={`看「${weakItems[0].token}」的發音回饋 →`}
                      pinyin={`Kàn “${weakItems[0].token}” de fāyīn huíkuì →`}
                      en={`See feedback for "${weakItems[0].token}" →`}
                    />
                  </button>
                )}
              </div>
            )}

            {view === "words" && (
              <div className="sfc-words">
                <p className="block-label sfc-words-heading">
                  <BiLabel k="character_by_character_prosody" />
                </p>
                {(praatMetrics?.word_prosody?.length ?? 0) > 0 ? (
                  <div className="sfc-words-row">
                    {praatMetrics!.word_prosody!.map((item) => (
                      <WordProsodyCard key={`${item.token}-${item.index}`} item={item} />
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
            )}
          </div>
        </div>
      </div>

      <footer className="sfc-footer">
        {!ready && (
          <p className="sfc-unlock-note">
            🔒{" "}
            <BiLabel
              zh={`聲調 70 分、流暢 65 分，或練習 4 次即可解鎖（目前 ${attempts} 次）`}
              pinyin={`Shēngdiào 70 fēn, liúchàng 65 fēn, huò liànxí 4 cì jí kě jiěsuǒ (mùqián ${attempts} cì)`}
              en={`Unlock with tone 70, fluency 65, or 4 attempts (now: ${attempts})`}
            />
          </p>
        )}
        <div className="sfc-footer-actions">
          <button
            type="button"
            className="sfc-btn-again"
            onClick={() => setScreen("record")}
          >
            🎙️ <BiLabel zh="再錄一次" pinyin="Zài lù yí cì" en="Record again" />
          </button>
          {hasNextScene ? (
            <button
              type="button"
              className="sfc-btn-next"
              disabled={!ready}
              onClick={onNextScene}
            >
              <BiLabel k="next_scene" /> →
            </button>
          ) : (
            <button
              type="button"
              className="sfc-btn-next"
              disabled={!ready}
              onClick={onViewSummary}
            >
              <BiLabel zh="查看總結" pinyin="Chákàn zǒngjié" en="View summary" /> →
            </button>
          )}
        </div>
      </footer>
    </section>
  );
}
