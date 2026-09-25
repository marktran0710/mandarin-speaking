import { useState } from "react";
import type { NewAudioRecord } from "../../components/story-recorder/StoryRecorder";
import type { Topic } from "@entities/topic";
import { buildSceneReferenceCurves, type PraatMetrics } from "../../components/story-recorder/StoryRecorder";
import { saveSpeakingProgress, type SceneSubmission } from "../../services/database";
import {
  analyzeSpeakingResult,
  type SpeakingResultAnalysis,
} from "../../components/speaking-flow-card/SpeakingResultsFlow.analysis";
import { getStudentId } from "../../utils/studentSession";
import { topicStoryId } from "../../utils/lessonGroups";
import { markPhaseSeen } from "@shared/lib/studyProgressFlags";
import { useSpeakingRecorder } from "./hooks/useSpeakingRecorder";
import PitchChart from "../../components/pitch/PitchChart";
import StudentPageHeader from "@shared/ui/student/StudentPageHeader";
import StudentSection from "@shared/ui/student/StudentSection";
import StudentButton from "@shared/ui/student/StudentButton";
import StudentAudioControl from "@shared/ui/student/StudentAudioControl";
import BilingualWord from "@shared/ui/student/BilingualWord";
import StudentInlineFeedback from "@shared/ui/student/StudentInlineFeedback";
import StudentIcon from "@shared/ui/student/StudentIcon";
import { mapWordProsodyToAlignment } from "@entities/speech/wordAlignment";
import { normalizeSpeechModel } from "@entities/speech/recordingModel";
import "@shared/ui/student/layout.css";
import "./StorySpeakingPage.css";

// Self-evaluation is shown merged into the Feedback card's Overview step
// (matching the confirmed mockup) rather than as its own stage — the
// student sees the AI verdict and reports their own impression in the same
// screen, instead of being asked to guess blind first.
type Stage = "recording" | "feedback";
type SelfEvalLevel = "good" | "ok" | "bad";
type FeedbackStep = "overview" | "fix" | "practice";

const FEEDBACK_STEP_LABEL: Record<FeedbackStep, string> = {
  overview: "Overview",
  fix: "Fix",
  practice: "Practice",
};

interface StorySpeakingPageProps {
  topic: Topic;
  selectedImageIndex: number;
  onImageIndexChange: (index: number) => void;
  onAddRecord: (record: NewAudioRecord) => Promise<string | undefined> | void;
  /** Every scene's latest submission, forwarded to StudentApp so it can
   * assemble the final story submission once the student turns work in.
   * Keyed so a re-recorded scene replaces its own entry rather than
   * duplicating it. */
  onSceneSubmission: (key: string, submission: SceneSubmission) => void;
  onDone: () => void;
}

export default function StorySpeakingPage({
  topic,
  selectedImageIndex,
  onImageIndexChange,
  onAddRecord,
  onSceneSubmission,
  onDone,
}: StorySpeakingPageProps) {
  const [stage, setStage] = useState<Stage>("recording");
  const [selfEvalMeaning, setSelfEvalMeaning] = useState<SelfEvalLevel | null>(null);
  const [selfEvalPronunciation, setSelfEvalPronunciation] = useState<SelfEvalLevel | null>(null);
  const [lastSubmission, setLastSubmission] = useState<SceneSubmission | null>(null);
  const [lastAnalysis, setLastAnalysis] = useState<SpeakingResultAnalysis | null>(null);
  const [lastGates, setLastGates] = useState<{ masteryPassed: boolean; contentPassed: boolean } | null>(null);
  const [lastPitch, setLastPitch] = useState<{ contour: Array<[number, number]>; detectedTone: number } | null>(null);
  const [lastWordProsody, setLastWordProsody] = useState<PraatMetrics["word_prosody"]>(undefined);
  const [attempts, setAttempts] = useState(0);
  const [feedbackStep, setFeedbackStep] = useState<FeedbackStep>("overview");
  const [selfEvalSaved, setSelfEvalSaved] = useState(false);

  const targetText = topic.suggestedAnswers?.[selectedImageIndex]?.trim()
    || topic.prompts?.[selectedImageIndex]?.trim()
    || "";
  const selectedImage = topic.images[selectedImageIndex];
  const studentId = getStudentId();

  const recorder = useSpeakingRecorder((attemptNumber) => ({
    sceneVocabulary: (topic.vocabulary[selectedImageIndex] || []).join(", "),
    scenePrompt: topic.prompts?.[selectedImageIndex] || topic.name,
    sceneImageUrl: selectedImage,
    scenePhrases: topic.phrases?.[selectedImageIndex]?.join("; "),
    sceneSuggestedAnswer: topic.suggestedAnswers?.[selectedImageIndex],
    sceneTargetText: targetText,
    sceneReferenceCurves: buildSceneReferenceCurves(topic, selectedImageIndex),
    attemptNumber,
  }));

  const handleRecord = async () => {
    const result = await recorder.startRecording();
    if (!result) return;
    const nextAttempt = attempts + 1;
    setAttempts(nextAttempt);

    const coverage = result.metrics.ai_feedback?.vocabulary_coverage;
    const submission: SceneSubmission = {
      sceneIndex: selectedImageIndex,
      imageUrl: selectedImage,
      transcription: (result.metrics.transcription || "").trim(),
      vocabUsed: coverage?.used ?? [],
      vocabMissing: coverage?.missing ?? [],
      vocabScore: coverage?.score ?? 0,
      toneAccuracy: Math.round(result.metrics.tone_accuracy ?? 0),
      pronScore: Math.round(result.metrics.tone_accuracy ?? 0),
      fluencyScore: Math.round(result.metrics.fluency_score ?? 0),
      audioUrl: result.audioUrl,
      pauseCount: result.metrics.pause_analysis?.pause_count ?? 0,
      longestPause: result.metrics.pause_analysis?.longest_pause ?? 0,
      utteranceCount: result.metrics.pause_analysis?.utterance_count ?? 0,
      choppyPauseCount: result.metrics.pause_analysis?.choppy_pause_count ?? 0,
      articulationRate: result.metrics.pause_analysis?.articulation_rate ?? 0,
      baseStoryId: topic.sourceStory?.id ?? topic.id,
      difficultyLevel: topic.difficultyLevel ?? "easy",
      promptId: `${topic.sourceStory?.id ?? topic.id}:scene:${selectedImageIndex}`,
    };
    setLastSubmission(submission);
    onSceneSubmission(`speaking:${selectedImageIndex}`, submission);
    setLastGates({ masteryPassed: result.masteryPassed, contentPassed: result.contentPassed });
    setLastPitch({
      contour: result.metrics.pitch_contour ?? [],
      detectedTone: result.metrics.detected_tone ?? 0,
    });
    setLastWordProsody(result.metrics.word_prosody);
    setLastAnalysis(
      analyzeSpeakingResult({
        modelSentence: targetText,
        praatMetrics: result.metrics,
        ready: result.masteryPassed && result.contentPassed,
        selectedImageIndex,
      }),
    );

    await onAddRecord({
      id: `audio-${Date.now()}`,
      audioBlob: result.audioBlob,
      timestamp: new Date().toLocaleString(),
      duration: Math.max(1, recorder.recordingDuration),
      transcription: submission.transcription,
      model: normalizeSpeechModel(result.metrics.transcription_model),
      topicId: topic.id,
      imageUrl: selectedImage,
      imageIndex: selectedImageIndex,
      praatMetrics: result.metrics,
      analysisVersion: "stable_v1",
      serverVerified: result.verified,
      serverRecordId: result.audioRecordId,
      audioUrl: result.audioUrl,
    });

    setFeedbackStep("overview");
    setSelfEvalSaved(false);
    setStage("feedback");
  };

  // Called from the Overview step's Continue/Skip — "Continue" persists
  // whatever self-eval was picked (partial is fine), "Skip" advances
  // without recording one this attempt. Runs at most once per attempt.
  const persistSelfEvalAndAdvance = async (save: boolean) => {
    if (!selfEvalSaved && lastSubmission) {
      const finalSubmission: SceneSubmission = save
        ? {
            ...lastSubmission,
            selfEvalContent: selfEvalMeaning ?? undefined,
            selfEvalPronunciation: selfEvalPronunciation ?? undefined,
          }
        : lastSubmission;
      setLastSubmission(finalSubmission);
      setSelfEvalSaved(true);
      if (studentId) {
        try {
          await saveSpeakingProgress({
            studentId,
            topicId: topic.id,
            sceneIndex: selectedImageIndex,
            attempts,
            bestTone: finalSubmission.toneAccuracy,
            bestFluency: finalSubmission.fluencyScore ?? 0,
            masteryPassed: lastGates?.masteryPassed ?? false,
            contentPassed: lastGates?.contentPassed ?? false,
            clearedWords: finalSubmission.vocabUsed,
            baseStoryId: finalSubmission.baseStoryId,
            difficultyLevel: finalSubmission.difficultyLevel,
            promptId: finalSubmission.promptId,
            latestResult: finalSubmission,
          });
        } catch {
          // Best-effort: the student still sees their feedback even if the
          // progress write fails; it will be retried the next time they visit.
        }
      }
    }
    advanceFeedback();
  };

  const recordAgain = () => {
    setSelfEvalMeaning(null);
    setSelfEvalPronunciation(null);
    setStage("recording");
  };

  const goNextScene = () => {
    setSelfEvalMeaning(null);
    setSelfEvalPronunciation(null);
    setLastSubmission(null);
    setLastAnalysis(null);
    setLastGates(null);
    setLastPitch(null);
    setLastWordProsody(undefined);
    setStage("recording");
    if (selectedImageIndex + 1 < topic.images.length) {
      onImageIndexChange(selectedImageIndex + 1);
    } else {
      markPhaseSeen(topicStoryId(topic), "speaking");
      onDone();
    }
  };

  // Old SpeakingResultsFlow logic: after the verdict, walk Fix (script/
  // vocab correction) then Practice (per-word drill) when the attempt
  // actually needs them (analysis.steps already decided that) — never
  // both unconditionally, never invented beyond what analyzeSpeakingResult
  // found. "selfEval" is excluded here since this page already ran its own
  // self-evaluation step earlier, unconditionally, per the approved design.
  const feedbackSteps: FeedbackStep[] = lastAnalysis
    ? (lastAnalysis.steps.filter((s): s is FeedbackStep => s !== "selfEval"))
    : ["overview"];
  const feedbackStepIndex = feedbackSteps.indexOf(feedbackStep);
  const isLastFeedbackStep = feedbackStepIndex === -1 || feedbackStepIndex === feedbackSteps.length - 1;
  const nextSceneLabel = selectedImageIndex + 1 < topic.images.length ? "Next scene" : "Finish";

  const advanceFeedback = () => {
    if (isLastFeedbackStep) {
      goNextScene();
      return;
    }
    setFeedbackStep(feedbackSteps[feedbackStepIndex + 1]);
  };

  // Word-level chips: every scored syllable, marked attention when it's
  // one of the real weak/failed words analyzeSpeakingResult already found —
  // never a re-derived threshold of our own.
  const wordChips = mapWordProsodyToAlignment(lastWordProsody);

  return (
    <div className="sa-page-container">
      <StudentPageHeader
        eyebrowEn={`Story Speaking · Scene ${selectedImageIndex + 1} / ${topic.images.length}`}
        titleZh={topic.name}
        titleEn="Look, listen, and speak the target sentence"
      />

      <div className="sa-speaking__split">
        <StudentSection variant="panel" className="sa-speaking__media">
          {selectedImage && (
            <img src={selectedImage} alt="" className="sa-speaking__image" />
          )}
        </StudentSection>

        <div className="sa-speaking__workflow">
          <div className="sa-speaking__stage-tracker">
            {(["recording", "feedback"] as Stage[]).map((s) => (
              <span key={s} className={`sa-speaking__stage ${stage === s ? "is-current" : stage === "feedback" && s === "recording" ? "is-done" : ""}`}>
                {s === "recording" ? "Recording" : "Feedback"}
              </span>
            ))}
          </div>

          <StudentSection variant="tinted" className="sa-speaking__target">
            <p className="sa-speaking__target-label">Target</p>
            <BilingualWord hanzi={targetText} size="display" toneHighlight />
            <StudentAudioControl audioUrl={topic.listenAudioUrls?.[selectedImageIndex]} label="Model" />
          </StudentSection>

          {stage === "recording" && (
            <StudentSection variant="panel" className="sa-speaking__action">
              {recorder.error && <p className="sa-speaking__error">{recorder.error}</p>}
              <StudentButton
                variant={recorder.isRecording ? "danger" : "primary"}
                size="lg"
                icon={recorder.isRecording ? "stop" : "mic"}
                disabled={recorder.isAnalyzing}
                onClick={recorder.isRecording ? recorder.stopRecording : handleRecord}
              >
                {recorder.isRecording ? `Stop (${recorder.recordingDuration}s)` : recorder.isAnalyzing ? "Analyzing…" : "Record"}
              </StudentButton>
            </StudentSection>
          )}

          {stage === "feedback" && lastAnalysis && (
            <>
              {feedbackSteps.length > 1 && (
                <div className="sa-speaking__feedback-steps" role="tablist" aria-label="Feedback steps">
                  {feedbackSteps.map((step, i) => (
                    <span
                      key={step}
                      className={`sa-speaking__feedback-step ${step === feedbackStep ? "is-current" : i < feedbackStepIndex ? "is-done" : ""}`}
                    >
                      {FEEDBACK_STEP_LABEL[step]}
                    </span>
                  ))}
                </div>
              )}

              {feedbackStep === "overview" && (
                <StudentSection variant="panel" className="sa-speaking__overview">
                  <div className="sa-speaking__self-eval">
                    <p className="sa-speaking__self-eval-title">How did you do?</p>
                    <SelfEvalRow label="Meaning" value={selfEvalMeaning} onChange={setSelfEvalMeaning} />
                    <SelfEvalRow label="Pronunciation" value={selfEvalPronunciation} onChange={setSelfEvalPronunciation} />
                  </div>

                  <StudentInlineFeedback
                    meaningOk={lastAnalysis.accepted}
                    pronunciationOk={lastGates?.masteryPassed ?? false}
                    pronunciationNote={lastAnalysis.legacyPracticeWords[0]?.token ?? lastAnalysis.weakItems[0]?.token ?? lastAnalysis.failedWords[0]?.token}
                    coachText={
                      lastAnalysis.showCorrective
                        ? lastAnalysis.corrective?.hint || undefined
                        : undefined
                    }
                    wordChips={wordChips}
                    detailsContent={
                      lastPitch && lastPitch.contour.length > 0 ? (
                        <PitchChart pitchContour={lastPitch.contour} detectedTone={lastPitch.detectedTone} />
                      ) : (
                        <p className="sa-speaking__no-pitch">No pitch data captured for this attempt.</p>
                      )
                    }
                    footer={
                      <div className="sa-inline-feedback__actions">
                        <StudentButton variant="secondary" icon="replay" onClick={recordAgain}>
                          Record again
                        </StudentButton>
                        <div className="sa-speaking__overview-forward">
                          <StudentButton variant="subtle" onClick={() => persistSelfEvalAndAdvance(false)}>
                            Skip
                          </StudentButton>
                          <StudentButton variant="primary" iconTrailing="arrow_forward" onClick={() => persistSelfEvalAndAdvance(true)}>
                            {isLastFeedbackStep ? nextSceneLabel : `See ${FEEDBACK_STEP_LABEL[feedbackSteps[feedbackStepIndex + 1]]}`}
                          </StudentButton>
                        </div>
                      </div>
                    }
                  />
                </StudentSection>
              )}

              {feedbackStep === "fix" && (
                <StudentSection variant="panel" className="sa-speaking__fix">
                  <div className="sa-speaking__fix-head">
                    <StudentIcon name="edit_note" size={18} role="decorative" />
                    <h3>What to fix</h3>
                  </div>
                  {lastAnalysis.corrective?.errors.map((error, i) => (
                    <p key={i} className="sa-speaking__fix-error">{error}</p>
                  ))}
                  {lastAnalysis.corrective?.correct_version && (
                    <div className="sa-speaking__fix-correct">
                      <span className="sa-speaking__fix-correct-label">Try saying</span>
                      <BilingualWord hanzi={lastAnalysis.corrective.correct_version} size="inline" />
                    </div>
                  )}
                  <div className="sa-inline-feedback__actions">
                    <StudentButton variant="secondary" icon="replay" onClick={recordAgain}>
                      Record again
                    </StudentButton>
                    <StudentButton variant="primary" iconTrailing="arrow_forward" onClick={advanceFeedback}>
                      {isLastFeedbackStep ? nextSceneLabel : `See ${FEEDBACK_STEP_LABEL[feedbackSteps[feedbackStepIndex + 1]]}`}
                    </StudentButton>
                  </div>
                </StudentSection>
              )}

              {feedbackStep === "practice" && (
                <StudentSection variant="panel" className="sa-speaking__practice">
                  <div className="sa-speaking__fix-head">
                    <StudentIcon name="fitness_center" size={18} role="decorative" />
                    <h3>Practice these words</h3>
                  </div>
                  <div className="sa-speaking__practice-list">
                    {lastAnalysis.practiceTargets.map((target) => (
                      <div key={target.key} className="sa-speaking__practice-item">
                        <span lang="zh-Hant" className="sa-speaking__practice-word">{target.label}</span>
                        {target.word?.feedback && (
                          <span className="sa-speaking__practice-feedback">{target.word.feedback}</span>
                        )}
                      </div>
                    ))}
                  </div>
                  <div className="sa-inline-feedback__actions">
                    <StudentButton variant="secondary" icon="replay" onClick={recordAgain}>
                      Record again
                    </StudentButton>
                    <StudentButton variant="primary" iconTrailing="arrow_forward" onClick={advanceFeedback}>
                      {nextSceneLabel}
                    </StudentButton>
                  </div>
                </StudentSection>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function SelfEvalRow({
  label,
  value,
  onChange,
}: {
  label: string;
  value: SelfEvalLevel | null;
  onChange: (level: SelfEvalLevel) => void;
}) {
  const options: { level: SelfEvalLevel; text: string }[] = [
    { level: "good", text: "Good" },
    { level: "ok", text: "OK" },
    { level: "bad", text: "Needs work" },
  ];
  return (
    <div className="sa-self-eval-row">
      <span className="sa-self-eval-row__label">{label}</span>
      <div className="sa-self-eval-row__options" role="group" aria-label={label}>
        {options.map((opt) => (
          <button
            key={opt.level}
            type="button"
            className={`sa-self-eval-row__option ${value === opt.level ? "is-selected" : ""}`}
            aria-pressed={value === opt.level}
            onClick={() => onChange(opt.level)}
          >
            {opt.text}
          </button>
        ))}
      </div>
    </div>
  );
}
