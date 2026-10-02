import { useRef, useState } from "react";
import type { NewAudioRecord } from "../../components/story-recorder/StoryRecorder";
import type { Topic } from "@entities/topic";
import { buildSceneReferenceCurves } from "../../components/story-recorder/StoryRecorder";
import { saveSpeakingProgress, type SceneSubmission } from "../../services/database";
import {
  analyzeSpeakingResult,
  type SpeakingResultAnalysis,
} from "../../components/speaking-flow-card/model/analysis";
import { getStudentId } from "../../utils/studentSession";
import { topicStoryId } from "../../utils/lessonGroups";
import { markPhaseSeen } from "@shared/lib/studyProgressFlags";
import { useSpeakingRecorder } from "./hooks/useSpeakingRecorder";
import StudentPage, { type StudentPageActions } from "@shared/ui/student/StudentPage";
import StudentPageHeader from "@shared/ui/student/StudentPageHeader";
import StudentSection from "@shared/ui/student/StudentSection";
import StudentButton from "@shared/ui/student/StudentButton";
import StudentAudioControl from "@shared/ui/student/StudentAudioControl";
import StudentAudioUpload from "@shared/ui/student/StudentAudioUpload";
import BilingualWord from "@shared/ui/student/BilingualWord";
import StudentIcon from "@shared/ui/student/StudentIcon";
import StudentSystemText from "@shared/ui/student/StudentSystemText";
import { studentUiCopy, type StudentUiCopyKey } from "../../i18n/student-ui-copy";
import { SpeechResultReview, SpeechSelfEvaluation, type SelfEvalLevel } from "@entities/speech";
import type { SpeakingAnalysisResult } from "./hooks/useSpeakingRecorder";
import { normalizeSpeechModel } from "@entities/speech/recordingModel";
import { attemptModelSimilarity } from "@entities/speech/modelSimilarity";
import "./StorySpeakingPage.css";

// Self-evaluation is a deliberate stage between analysis and the feedback
// result, so the learner reports their impression before seeing the verdict.
type Stage = "recording" | "selfEval" | "feedback";
type FeedbackStep = "overview" | "fix";

const FEEDBACK_STEP_KEY: Record<FeedbackStep, StudentUiCopyKey> = {
  overview: "resultStep",
  fix: "fixStep",
};
// Label of the button that moves on to that step.
const SEE_STEP_KEY: Record<FeedbackStep, StudentUiCopyKey> = {
  overview: "resultStep",
  fix: "seeFixStep",
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
  const [lastResult, setLastResult] = useState<SpeakingAnalysisResult | null>(null);
  const [lastAnalysis, setLastAnalysis] = useState<SpeakingResultAnalysis | null>(null);
  const [lastGates, setLastGates] = useState<{ masteryPassed: boolean; contentPassed: boolean } | null>(null);
  const [attempts, setAttempts] = useState(0);
  const [feedbackStep, setFeedbackStep] = useState<FeedbackStep>("overview");
  const [selfEvalSaved, setSelfEvalSaved] = useState(false);
  const selfEvalCommitRef = useRef(false);

  const targetText = topic.suggestedAnswers?.[selectedImageIndex]?.trim()
    || topic.prompts?.[selectedImageIndex]?.trim()
    || "";
  const selectedImage = topic.images[selectedImageIndex];
  const studentId = getStudentId();
  const baseStoryId = topic.sourceStory?.id ?? topic.id;

  const recorder = useSpeakingRecorder((attemptNumber) => ({
    baseStoryId,
    sceneIndex: selectedImageIndex,
    difficultyLevel: topic.difficultyLevel ?? "easy",
    sceneVocabulary: (topic.vocabulary[selectedImageIndex] || []).join(", "),
    scenePrompt: topic.prompts?.[selectedImageIndex] || topic.name,
    sceneImageUrl: selectedImage,
    scenePhrases: topic.phrases?.[selectedImageIndex]?.join("; "),
    sceneSuggestedAnswer: topic.suggestedAnswers?.[selectedImageIndex],
    sceneTargetText: targetText,
    sceneReferenceCurves: buildSceneReferenceCurves(topic, selectedImageIndex),
    attemptNumber,
  }));

  const handleAnalysisResult = async (result: Awaited<ReturnType<typeof recorder.startRecording>>) => {
    if (!result) return;
    const nextAttempt = attempts + 1;
    setAttempts(nextAttempt);

    const coverage = result.metrics.ai_feedback?.vocabulary_coverage;
    const similarity = attemptModelSimilarity({
      contour: topic.sentenceModelContours?.[selectedImageIndex],
      targetScript: targetText,
      transcript: result.metrics.transcription,
      words: result.metrics.word_prosody ?? [],
      pitchContour: result.metrics.pitch_contour ?? [],
    });
    const submission: SceneSubmission = {
      sceneIndex: selectedImageIndex,
      imageUrl: selectedImage,
      transcription: (result.metrics.transcription || "").trim(),
      vocabUsed: coverage?.used ?? [],
      vocabMissing: coverage?.missing ?? [],
      vocabScore: coverage?.score ?? 0,
      toneAccuracy: Math.round(result.metrics.tone_accuracy ?? 0),
      // Speaking uses OMPAL as the only pronunciation score. Praat remains
      // diagnostic/visual evidence and is not copied into this score field.
      pronScore: null,
      pronunciationEvaluation: result.metrics.pronunciation_evaluation,
      fluencyScore: Math.round(result.metrics.fluency_score ?? 0),
      audioUrl: result.audioUrl,
      pauseCount: result.metrics.pause_analysis?.pause_count ?? 0,
      longestPause: result.metrics.pause_analysis?.longest_pause ?? 0,
      utteranceCount: result.metrics.pause_analysis?.utterance_count ?? 0,
      choppyPauseCount: result.metrics.pause_analysis?.choppy_pause_count ?? 0,
      articulationRate: result.metrics.pause_analysis?.articulation_rate ?? 0,
      modelSimilarity: similarity?.score ?? null,
      baseStoryId,
      difficultyLevel: topic.difficultyLevel ?? "easy",
      promptId: `${topic.sourceStory?.id ?? topic.id}:scene:${selectedImageIndex}`,
    };
    setLastSubmission(submission);
    setLastResult(result);
    setLastGates({ masteryPassed: result.masteryPassed, contentPassed: result.contentPassed });
    setLastAnalysis(
      analyzeSpeakingResult({
        modelSentence: targetText,
        praatMetrics: result.metrics,
        ready: result.contentPassed,
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
    selfEvalCommitRef.current = false;
    setSelfEvalMeaning(null);
    setSelfEvalPronunciation(null);
    setStage("selfEval");
  };

  const handleRecord = async () => {
    await handleAnalysisResult(await recorder.startRecording());
  };

  const handleUpload = async (file: File) => {
    await handleAnalysisResult(await recorder.uploadRecording(file));
  };

  // Save self-evaluation before revealing the result. Skipping still keeps
  // the attempt, but leaves both self-evaluation fields empty.
  const persistSelfEvalAndAdvance = async (save: boolean) => {
    if (selfEvalCommitRef.current) return;
    selfEvalCommitRef.current = true;
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
      onSceneSubmission(`speaking:${selectedImageIndex}`, finalSubmission);
      setStage("feedback");
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
    if (!lastSubmission) setStage("feedback");
  };

  const recordAgain = () => {
    setSelfEvalMeaning(null);
    setSelfEvalPronunciation(null);
    selfEvalCommitRef.current = false;
    setLastResult(null);
    setStage("recording");
  };

  const goNextScene = () => {
    setSelfEvalMeaning(null);
    setSelfEvalPronunciation(null);
    selfEvalCommitRef.current = false;
    setLastSubmission(null);
    setLastResult(null);
    setLastAnalysis(null);
    setLastGates(null);
    setStage("recording");
    if (selectedImageIndex + 1 < topic.images.length) {
      onImageIndexChange(selectedImageIndex + 1);
    } else {
      markPhaseSeen(topicStoryId(topic), "speaking");
      onDone();
    }
  };

  // Old SpeakingResultsFlow logic: after the verdict, walk Fix (script/
  // vocab correction) when the attempt actually needs it (analysis.steps
  // already decided that) ??never invented beyond what analyzeSpeakingResult
  // found. "selfEval" is excluded here since this page already ran its own
  // self-evaluation step earlier, unconditionally, per the approved design.
  const feedbackSteps: FeedbackStep[] = lastAnalysis
    ? (lastAnalysis.steps.filter((s): s is FeedbackStep => s === "overview" || s === "fix"))
    : ["overview"];
  const feedbackStepIndex = feedbackSteps.indexOf(feedbackStep);
  const isLastFeedbackStep = feedbackStepIndex === -1 || feedbackStepIndex === feedbackSteps.length - 1;
  const nextSceneKey: StudentUiCopyKey = selectedImageIndex + 1 < topic.images.length ? "nextScene" : "finish";

  const advanceFeedback = () => {
    if (isLastFeedbackStep) {
      goNextScene();
      return;
    }
    setFeedbackStep(feedbackSteps[feedbackStepIndex + 1]);
  };

  // Word-level chips: every scored syllable, marked attention when it's
  // one of the real weak/failed words analyzeSpeakingResult already found ??
  // never a re-derived threshold of our own.
  const continueKey: StudentUiCopyKey = isLastFeedbackStep ? nextSceneKey : SEE_STEP_KEY[feedbackSteps[feedbackStepIndex + 1]];
  const continueLabel = <StudentSystemText k={continueKey} withinControl />;
  const recordAgainButton = (
    <StudentButton variant="secondary" icon="replay" onClick={recordAgain}>
      <StudentSystemText k="recordAgain" withinControl />
    </StudentButton>
  );

  let actions: StudentPageActions | undefined;
  if (stage === "selfEval" && lastResult) {
    actions = undefined;
  } else if (stage === "feedback" && lastAnalysis) {
    if (feedbackStep === "overview") {
      actions = {
        secondary: (
          <>
            {recordAgainButton}
          </>
        ),
        primary: (
          <StudentButton variant="primary" iconTrailing="arrow_forward" onClick={advanceFeedback}>
            {continueLabel}
          </StudentButton>
        ),
      };
    } else if (feedbackStep === "fix") {
      actions = {
        secondary: recordAgainButton,
        primary: (
          <StudentButton variant="primary" iconTrailing="arrow_forward" onClick={advanceFeedback}>
            {continueLabel}
          </StudentButton>
        ),
      };
    }
  }

  return (
    <StudentPage
      layout="stage"
      header={
        <StudentPageHeader
          eyebrowKey="storySpeaking"
          titleKey="storySpeakingTitle"
          context={<><span lang="zh-Hant">{topic.name}</span> · {selectedImageIndex + 1} / {topic.images.length}</>}
          subtitle={<StudentSystemText k="lookListenSpeak" />}
        />
      }
      media={
        <StudentSection variant="panel" className="sa-speaking__media">
          {selectedImage ? (
            <img src={selectedImage} alt="" className="sa-speaking__image" />
          ) : (
            <div className="sa-speaking__media-empty">
              <StudentIcon name="image" size={28} role="decorative" />
              <p><StudentSystemText k="noImageForPart" /></p>
            </div>
          )}
        </StudentSection>
      }
      actions={actions}
    >
      <div className="sa-speaking__workflow">
        <div className="sa-speaking__stage-tracker">
          {(["recording", "selfEval", "feedback"] as Stage[]).map((s) => (
            <span key={s} className={`sa-speaking__stage ${stage === s ? "is-current" : ((stage === "selfEval" || stage === "feedback") && s === "recording") || (stage === "feedback" && s === "selfEval") ? "is-done" : ""}`}>
              <StudentSystemText k={s === "recording" ? "record" : s === "selfEval" ? "selfEvaluation" : "feedback"} />
            </span>
          ))}
        </div>

        <StudentSection variant="tinted" className="sa-speaking__target">
          <p className="sa-speaking__target-label"><StudentSystemText k="target" /></p>
          <BilingualWord hanzi={targetText} size="display" toneHighlight />
          <StudentAudioControl audioUrl={topic.listenAudioUrls?.[selectedImageIndex]} labelKey="model" />
        </StudentSection>

        {stage === "recording" && (
          <StudentSection variant="panel" className="sa-speaking__action">
            {recorder.error && <p className="sa-speaking__error">{recorder.error}</p>}
            <div className="sa-speaking__record-actions">
              <StudentButton
                variant={recorder.isRecording ? "danger" : "primary"}
                size="lg"
                icon={recorder.isRecording ? "stop" : "mic"}
                disabled={recorder.isAnalyzing}
                onClick={recorder.isRecording ? recorder.stopRecording : handleRecord}
              >
                {recorder.isRecording ? <><StudentSystemText k="stop" withinControl />（{recorder.recordingDuration} 秒）</> : recorder.isAnalyzing ? <StudentSystemText k="analyzing" withinControl /> : <StudentSystemText k="record" withinControl />}
              </StudentButton>
              <StudentAudioUpload
                labelKey="upload"
                disabled={recorder.isRecording || recorder.isAnalyzing}
                onSelect={handleUpload}
              />
            </div>
          </StudentSection>
        )}

        {stage === "selfEval" && lastResult && (
          <SpeechSelfEvaluation
            targetText={targetText}
            modelAudioUrl={topic.listenAudioUrls?.[selectedImageIndex]}
            audioBlob={lastResult.audioBlob}
            meaning={selfEvalMeaning}
            pronunciation={selfEvalPronunciation}
            onMeaningChange={setSelfEvalMeaning}
            onPronunciationChange={setSelfEvalPronunciation}
            onContinue={() => persistSelfEvalAndAdvance(true)}
            onSkip={() => persistSelfEvalAndAdvance(false)}
            onRecordAgain={recordAgain}
          />
        )}

        {stage === "feedback" && lastAnalysis && lastResult && (
          <>
            {feedbackSteps.length > 1 && (
              <div className="sa-speaking__feedback-steps" role="tablist" aria-label={studentUiCopy.feedbackSteps.zh}>
                {feedbackSteps.map((step, i) => (
                  <span
                    key={step}
                    className={`sa-speaking__feedback-step ${step === feedbackStep ? "is-current" : i < feedbackStepIndex ? "is-done" : ""}`}
                  >
                    <StudentSystemText k={FEEDBACK_STEP_KEY[step]} />
                  </span>
                ))}
              </div>
            )}

            {feedbackStep === "overview" && (
              <SpeechResultReview
                targetScript={targetText}
                transcript={lastResult.metrics.transcription}
                metrics={lastResult.metrics}
                audioBlob={lastResult.audioBlob}
                audioUrl={lastResult.audioUrl}
                meaningPassed={lastAnalysis.accepted}
                modelContour={topic.sentenceModelContours?.[selectedImageIndex]}
              />
            )}

            {feedbackStep === "fix" && (
              <StudentSection variant="panel" className="sa-speaking__fix">
                <div className="sa-speaking__fix-head">
                  <StudentIcon name="edit_note" size={18} role="decorative" />
                  <h3><StudentSystemText k="whatToFix" /></h3>
                </div>
                {lastAnalysis.corrective?.errors.map((error, i) => (
                  <p key={i} className="sa-speaking__fix-error">{error}</p>
                ))}
                {lastAnalysis.corrective?.correct_version && (
                  <div className="sa-speaking__fix-correct">
                    <span className="sa-speaking__fix-correct-label"><StudentSystemText k="trySaying" /></span>
                    <BilingualWord hanzi={lastAnalysis.corrective.correct_version} size="inline" />
                  </div>
                )}
              </StudentSection>
            )}
          </>
        )}
      </div>
    </StudentPage>
  );
}
