import "./StoryVocabQuiz.css";
import { BiLabel } from "../BiLabel";
import { ModeSelectScreen, ReviewScreen, SummaryScreen } from "./QuizScreens";
import { QuizQuestion } from "./QuizQuestion";
import { useQuizSession } from "./useQuizSession";
import type { VocabQuizEntry, VocabQuizSummary } from "./model";

export { CLOZE_BLANK, MAX_QUESTIONS, TIMER_TICK_MS, buildQuizQuestion, buildQuizQuestions, collectQuizEntries, quizConceptId, quizItemId } from "./model";
export type { VocabQuizClozeCandidate, VocabQuizClozeQuestion, VocabQuizEntry, VocabQuizListeningQuestion, VocabQuizMode, VocabQuizPinyinQuestion, VocabQuizPosQuestion, VocabQuizQuestion, VocabQuizQuestionResult, VocabQuizReverseQuestion, VocabQuizSummary, VocabQuizSynonymCandidate, VocabQuizSynonymQuestion, VocabQuizTranslationQuestion } from "./model";

/** A tiered vocabulary check shown before story speaking practice. */
export default function StoryVocabQuiz({ entries, onDone, onBack, onComplete, storyId, baseStoryId, level = "easy", studentId, studentName, alreadyCompleted }: {
  entries: VocabQuizEntry[]; onDone: () => void; onBack?: () => void;
  onComplete?: (summary: VocabQuizSummary) => void; storyId?: string; baseStoryId?: string;
  level?: "easy" | "medium" | "hard"; studentId?: string; studentName?: string; alreadyCompleted?: boolean;
}) {
  // Retained for runtime compatibility; navigation now belongs to the
  // activity chooser instead of the quiz surface.
  void onBack;
  const session = useQuizSession({ entries, storyId, baseStoryId, level, studentId, studentName, onComplete });
  if (!session.sessionReady) {
    return (
      <div className="app-loading">
        <div className="app-loading-card">
          <div className="app-loading-icon" aria-hidden="true" />
          <h2><BiLabel k="loading_your_progress" /></h2>
        </div>
      </div>
    );
  }
  if (session.screen === "mode-select") return <ModeSelectScreen stars={session.stars} weakEntries={session.weakEntries} priorityReviewWords={session.priorityReviewWords} level={level} alreadyCompleted={alreadyCompleted} startTier={session.startTier} chooseWeakWords={() => { session.setIsRetryRound(false); session.chooseMode("weak_words", session.weakEntries, session.weakEntries.length); }} showReview={() => session.setScreen("review")} />;
  if (session.screen === "review") return <ReviewScreen entries={entries} back={() => session.setScreen("mode-select")} />;
  if (session.screen === "summary") return <SummaryScreen mode={session.mode} results={session.results} missedWords={session.missedWords} missedEntries={session.missedEntries} isRetryRound={session.isRetryRound} stars={session.stars} onDone={onDone} startTier={session.startTier} practiceMissedWords={session.practiceMissedWords} backToModes={() => session.setScreen("mode-select")} />;
  if (!session.question) return null;
  return <QuizQuestion question={session.question} mode={session.mode} selected={session.selected} results={session.results} index={session.index} questionLimit={session.questionLimit} requestedQuestionCount={session.requestedQuestionCount} isRetryRound={session.isRetryRound} isLast={session.isLast} timeLeftMs={session.timeLeftMs} timeLimitMs={session.timeLimitMs} showFinishButton={session.showFinishButton} choose={session.choose} next={session.next} finish={session.finish} speakWord={session.speakWord} />;
}
