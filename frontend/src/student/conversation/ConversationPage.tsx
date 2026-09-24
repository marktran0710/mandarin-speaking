import { useEffect, useMemo, useRef, useState } from "react";
import type { NewAudioRecord } from "../../components/story-recorder/StoryRecorder";
import type { Topic } from "../../components/content/topic-selector/types";
import {
  createConversationState,
  transitionConversation,
  type ConversationState,
  type ConversationTurn,
} from "../../components/story-recorder/StoryRecorder";
import { saveSpeakingProgress, type SceneSubmission } from "../../services/database";
import {
  analyzeSpeakingResult,
  type SpeakingResultAnalysis,
} from "../../components/speaking-flow-card/SpeakingResultsFlow.analysis";
import { getStudentId } from "../../utils/studentSession";
import { useSpeakingRecorder } from "../speaking/useSpeakingRecorder";
import StudentButton from "../primitives/StudentButton";
import StudentAudioControl from "../primitives/StudentAudioControl";
import StudentInlineFeedback, { type WordChip } from "../primitives/StudentInlineFeedback";
import BilingualWord from "../primitives/BilingualWord";
import "./ConversationPage.css";

interface ConversationPageProps {
  topic: Topic;
  turns: ConversationTurn[];
  onAddRecord: (record: NewAudioRecord) => Promise<string | undefined> | void;
  onDone: () => void;
  onBack: () => void;
}

export default function ConversationPage({ topic, turns, onAddRecord, onDone, onBack }: ConversationPageProps) {
  const [state, setState] = useState<ConversationState>(
    () => createConversationState(turns) ?? { turnIndex: 0, step: "summary" },
  );
  const [lastAnalysis, setLastAnalysis] = useState<SpeakingResultAnalysis | null>(null);
  const [lastRecognizedText, setLastRecognizedText] = useState("");
  const conversationIdRef = useRef(`conv-${topic.id}-${Date.now()}`);
  const studentId = getStudentId();

  const currentTurn = turns[state.turnIndex] ?? null;

  const recorder = useSpeakingRecorder((attemptNumber) => ({
    scenePrompt: topic.name,
    sceneTargetText: currentTurn?.targetText || currentTurn?.text || "",
    conversationId: conversationIdRef.current,
    turnId: currentTurn?.id,
    turnIndex: state.turnIndex,
    attemptNumber,
  }));

  const dispatch = (event: Parameters<typeof transitionConversation>[1]) => {
    setState((prev) => {
      const { state: next, accepted } = transitionConversation(prev, event, turns);
      return accepted ? next : prev;
    });
  };

  // Conversation Practice has no separate self-evaluation step (Story
  // Speaking does) — fall straight through selfEval to feedback.
  useEffect(() => {
    if (state.step === "selfEval") dispatch({ type: "selfEvaluationSkipped" });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.step]);

  useEffect(() => {
    if (state.step === "summary") onDone();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.step]);

  const handleListen = () => {
    dispatch({ type: "systemAudioCompleted" });
  };

  const handleRecord = async () => {
    if (!currentTurn) return;
    const result = await recorder.startRecording();
    if (!result) return;

    setLastRecognizedText((result.metrics.transcription || "").trim());
    setLastAnalysis(
      analyzeSpeakingResult({
        modelSentence: currentTurn.targetText || currentTurn.text,
        praatMetrics: result.metrics,
        ready: result.masteryPassed && result.contentPassed,
        selectedImageIndex: 0,
      }),
    );

    await onAddRecord({
      id: `audio-${Date.now()}`,
      audioBlob: result.audioBlob,
      timestamp: new Date().toLocaleString(),
      duration: Math.max(1, recorder.recordingDuration),
      transcription: (result.metrics.transcription || "").trim(),
      model: "webspeech",
      topicId: topic.id,
      imageUrl: topic.images[0] ?? "",
      imageIndex: 0,
      conversationId: conversationIdRef.current,
      turnId: currentTurn.id,
      turnIndex: state.turnIndex,
      praatMetrics: result.metrics,
      analysisVersion: "stable_v1",
      serverVerified: result.verified,
      serverRecordId: result.audioRecordId,
      audioUrl: result.audioUrl,
    });

    if (studentId) {
      const coverage = result.metrics.ai_feedback?.vocabulary_coverage;
      const submission: SceneSubmission = {
        sceneIndex: 0,
        imageUrl: topic.images[0] ?? "",
        transcription: (result.metrics.transcription || "").trim(),
        vocabUsed: coverage?.used ?? [],
        vocabMissing: coverage?.missing ?? [],
        vocabScore: coverage?.score ?? 0,
        toneAccuracy: Math.round(result.metrics.tone_accuracy ?? 0),
        pronScore: Math.round(result.metrics.tone_accuracy ?? 0),
        fluencyScore: Math.round(result.metrics.fluency_score ?? 0),
        audioUrl: result.audioUrl,
        conversationId: conversationIdRef.current,
        turnId: currentTurn.id,
        turnIndex: state.turnIndex,
        baseStoryId: topic.sourceStory?.id ?? topic.id,
        difficultyLevel: topic.difficultyLevel ?? "easy",
        promptId: `${topic.sourceStory?.id ?? topic.id}:conversation:${currentTurn.id}`,
      };
      try {
        await saveSpeakingProgress({
          studentId,
          topicId: topic.id,
          sceneIndex: 0,
          attempts: 1,
          bestTone: submission.toneAccuracy,
          bestFluency: submission.fluencyScore ?? 0,
          masteryPassed: result.masteryPassed,
          contentPassed: result.contentPassed,
          clearedWords: submission.vocabUsed,
          conversationId: conversationIdRef.current,
          turnId: currentTurn.id,
          turnIndex: state.turnIndex,
          latestResult: submission,
          baseStoryId: submission.baseStoryId,
          difficultyLevel: submission.difficultyLevel,
          promptId: submission.promptId,
        });
      } catch {
        // Best-effort; the student still sees feedback either way.
      }
    }

    dispatch({ type: "studentRecordingCompleted", recordingId: currentTurn.id });
  };

  const recordAgain = () => {
    setLastAnalysis(null);
    setState((prev) => ({ ...prev, step: "student" }));
  };

  const nextTurn = () => {
    setLastAnalysis(null);
    dispatch({ type: "feedbackCompleted" });
  };

  const weakTokens = useMemo(
    () =>
      lastAnalysis
        ? new Set([...lastAnalysis.weakItems.map((w) => w.token), ...lastAnalysis.failedWords.map((w) => w.token)])
        : new Set<string>(),
    [lastAnalysis],
  );
  const wordChips: WordChip[] | undefined = lastRecognizedText
    ? Array.from(new Set(lastRecognizedText.split(/\s+/).filter(Boolean))).map((token) => ({
        hanzi: token,
        ok: !weakTokens.has(token),
      }))
    : undefined;

  const historyTurns = turns.slice(0, state.turnIndex);
  const exchangeCount = Math.ceil(turns.length / 2);
  const currentExchange = Math.ceil((state.turnIndex + 1) / 2);

  return (
    <div className="sa-conversation">
      <header className="sa-conversation__header">
        <button type="button" className="sa-conversation__back" onClick={onBack}>
          ← Back
        </button>
        <div className="sa-conversation__title">
          <span lang="zh-Hant">{topic.name}</span>
        </div>
        <span className="sa-conversation__exchange">Exchange {currentExchange} / {exchangeCount}</span>
      </header>

      <div className="sa-conversation__column">
        {historyTurns.map((turn) => (
          <div key={turn.id} className={`sa-bubble-row sa-bubble-row--compact ${turn.speaker === "student" ? "is-student" : "is-character"}`}>
            <span className="sa-bubble-row__who">{turn.speaker === "student" ? "You" : "Character"}</span>
            <div className="sa-bubble">
              <span lang="zh-Hant" className="sa-bubble__hanzi">{turn.text}</span>
            </div>
          </div>
        ))}

        {currentTurn && (state.step === "system") && (
          <div className="sa-bubble-row is-character">
            <span className="sa-bubble-row__who">Character</span>
            <div className="sa-bubble">
              <BilingualWord hanzi={currentTurn.text} pinyin={currentTurn.pinyin} gloss={currentTurn.translation} size="inline" />
              <StudentAudioControl audioUrl={currentTurn.audioUrl} fallbackText={currentTurn.text} label="Listen" />
              <StudentButton variant="subtle" size="sm" onClick={handleListen}>
                Continue
              </StudentButton>
            </div>
          </div>
        )}

        {currentTurn && (state.step === "student" || state.step === "feedback") && (
          <div className="sa-bubble-row is-student is-current">
            <span className="sa-bubble-row__who">Your response</span>
            <div className="sa-bubble sa-bubble--target">
              <BilingualWord
                hanzi={currentTurn.targetText || currentTurn.text}
                pinyin={currentTurn.pinyin}
                gloss={currentTurn.translation}
                size="inline"
              />
              {state.step === "student" && (
                <>
                  {recorder.error && <p className="sa-conversation__error">{recorder.error}</p>}
                  <StudentButton
                    variant="primary"
                    icon="mic"
                    disabled={recorder.isRecording || recorder.isAnalyzing}
                    onClick={handleRecord}
                  >
                    {recorder.isRecording ? `Recording… ${recorder.recordingDuration}s` : recorder.isAnalyzing ? "Analyzing…" : "Record"}
                  </StudentButton>
                </>
              )}
            </div>

            {state.step === "feedback" && lastAnalysis && (
              <div className="sa-bubble sa-bubble--feedback">
                <p className="sa-conversation__you-said">
                  You said <span lang="zh-Hant">{lastRecognizedText}</span>
                </p>
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
                  onRecordAgain={recordAgain}
                  onContinue={nextTurn}
                  continueLabel={state.turnIndex + 1 < turns.length ? "Next" : "Finish"}
                />
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
