import { useState } from "react";
import type { NewAudioRecord } from "../../components/story-recorder/StoryRecorder";
import type { Topic } from "../../components/content/topic-selector/types";
import { buildSceneReferenceCurves } from "../../components/story-recorder/StoryRecorder";
import { saveSpeakingProgress, type SceneSubmission } from "../../services/database";
import {
  analyzeSpeakingResult,
  type SpeakingResultAnalysis,
} from "../../components/speaking-flow-card/SpeakingResultsFlow.analysis";
import { getStudentId } from "../../utils/studentSession";
import { useSpeakingRecorder } from "./useSpeakingRecorder";
import StudentPageHeader from "../primitives/StudentPageHeader";
import StudentSection from "../primitives/StudentSection";
import StudentButton from "../primitives/StudentButton";
import StudentAudioControl from "../primitives/StudentAudioControl";
import BilingualWord from "../primitives/BilingualWord";
import StudentInlineFeedback, { type WordChip } from "../primitives/StudentInlineFeedback";
import StudentIcon from "../primitives/StudentIcon";
import "../primitives/layout.css";
import "./StorySpeakingPage.css";

type Stage = "recording" | "self-eval" | "feedback";
type SelfEvalLevel = "good" | "ok" | "bad";

interface StorySpeakingPageProps {
  topic: Topic;
  selectedImageIndex: number;
  onImageIndexChange: (index: number) => void;
  onAddRecord: (record: NewAudioRecord) => Promise<string | undefined> | void;
  onDone: () => void;
}

export default function StorySpeakingPage({
  topic,
  selectedImageIndex,
  onImageIndexChange,
  onAddRecord,
  onDone,
}: StorySpeakingPageProps) {
  const [stage, setStage] = useState<Stage>("recording");
  const [selfEvalMeaning, setSelfEvalMeaning] = useState<SelfEvalLevel | null>(null);
  const [selfEvalPronunciation, setSelfEvalPronunciation] = useState<SelfEvalLevel | null>(null);
  const [lastSubmission, setLastSubmission] = useState<SceneSubmission | null>(null);
  const [lastAnalysis, setLastAnalysis] = useState<SpeakingResultAnalysis | null>(null);
  const [lastGates, setLastGates] = useState<{ masteryPassed: boolean; contentPassed: boolean } | null>(null);
  const [attempts, setAttempts] = useState(0);

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
    setLastGates({ masteryPassed: result.masteryPassed, contentPassed: result.contentPassed });
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
      model: "webspeech",
      topicId: topic.id,
      imageUrl: selectedImage,
      imageIndex: selectedImageIndex,
      praatMetrics: result.metrics,
      analysisVersion: "stable_v1",
      serverVerified: result.verified,
      serverRecordId: result.audioRecordId,
      audioUrl: result.audioUrl,
    });

    setStage("self-eval");
  };

  const submitSelfEval = async () => {
    if (!lastSubmission) return;
    const finalSubmission: SceneSubmission = {
      ...lastSubmission,
      selfEvalContent: selfEvalMeaning ?? undefined,
      selfEvalPronunciation: selfEvalPronunciation ?? undefined,
    };
    setLastSubmission(finalSubmission);
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
    setStage("feedback");
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
    setStage("recording");
    if (selectedImageIndex + 1 < topic.images.length) {
      onImageIndexChange(selectedImageIndex + 1);
    } else {
      onDone();
    }
  };

  // Word-level chips: every scored syllable, marked attention when it's
  // one of the real weak/failed words analyzeSpeakingResult already found —
  // never a re-derived threshold of our own.
  const weakTokens = lastAnalysis
    ? new Set([...lastAnalysis.weakItems.map((w) => w.token), ...lastAnalysis.failedWords.map((w) => w.token)])
    : new Set<string>();
  const wordChips: WordChip[] | undefined = lastSubmission?.transcription
    ? Array.from(new Set(lastSubmission.transcription.split(/\s+/).filter(Boolean))).map((token) => ({
        hanzi: token,
        ok: !weakTokens.has(token),
      }))
    : undefined;

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
            {(["recording", "self-eval", "feedback"] as Stage[]).map((s, i) => (
              <span key={s} className={`sa-speaking__stage ${stage === s ? "is-current" : i < (["recording", "self-eval", "feedback"] as Stage[]).indexOf(stage) ? "is-done" : ""}`}>
                {s === "recording" ? "Recording" : s === "self-eval" ? "Self Evaluation" : "Feedback"}
              </span>
            ))}
          </div>

          <StudentSection variant="tinted" className="sa-speaking__target">
            <p className="sa-speaking__target-label">Target</p>
            <BilingualWord hanzi={targetText} size="display" toneHighlight />
            <StudentAudioControl fallbackText={targetText} label="Model" />
          </StudentSection>

          {stage === "recording" && (
            <StudentSection variant="panel" className="sa-speaking__action">
              {recorder.error && <p className="sa-speaking__error">{recorder.error}</p>}
              <StudentButton
                variant="primary"
                size="lg"
                icon="mic"
                disabled={recorder.isRecording || recorder.isAnalyzing}
                onClick={handleRecord}
              >
                {recorder.isRecording ? `Recording… ${recorder.recordingDuration}s` : recorder.isAnalyzing ? "Analyzing…" : "Record"}
              </StudentButton>
            </StudentSection>
          )}

          {stage === "self-eval" && (
            <StudentSection variant="panel" className="sa-speaking__self-eval">
              <p className="sa-speaking__self-eval-title">How did you do?</p>
              <SelfEvalRow label="Meaning" value={selfEvalMeaning} onChange={setSelfEvalMeaning} />
              <SelfEvalRow label="Pronunciation" value={selfEvalPronunciation} onChange={setSelfEvalPronunciation} />
              <StudentButton
                variant="primary"
                iconTrailing="arrow_forward"
                disabled={!selfEvalMeaning || !selfEvalPronunciation}
                onClick={submitSelfEval}
              >
                See feedback
              </StudentButton>
            </StudentSection>
          )}

          {stage === "feedback" && lastAnalysis && (
            <StudentInlineFeedback
              meaningOk={lastAnalysis.accepted}
              pronunciationOk={weakTokens.size === 0}
              pronunciationNote={lastAnalysis.weakItems[0]?.token ?? lastAnalysis.failedWords[0]?.token}
              coachText={
                lastAnalysis.showCorrective
                  ? lastAnalysis.corrective?.hint || lastAnalysis.corrective?.correct_version
                  : undefined
              }
              wordChips={wordChips}
              detailsContent={
                <StudentIcon name="analytics" size={16} role="meaningful" label="Detailed pronunciation breakdown available in Progress" />
              }
              onRecordAgain={recordAgain}
              onContinue={goNextScene}
              continueLabel={selectedImageIndex + 1 < topic.images.length ? "Next scene" : "Finish"}
            />
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
