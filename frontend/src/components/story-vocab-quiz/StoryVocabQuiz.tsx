import "./StoryVocabQuiz.css";
import { useEffect } from "react";
import { BiLabel } from "../BiLabel";
import { ModeSelectScreen, ReviewScreen, SummaryScreen } from "./QuizScreens";
import { ChallengeEntry } from "./LessonVocabularyProgress";
import { QuizQuestion } from "./QuizQuestion";
import { useQuizSession } from "./useQuizSession";
import type { VocabAssessmentLevel, VocabQuizEntry, VocabQuizSummary } from "./model";

export { CLOZE_BLANK, MAX_QUESTIONS, TIMER_TICK_MS, buildQuizQuestion, buildQuizQuestions, collectQuizEntries, quizConceptId, quizItemId } from "./model";
export type { VocabQuizClozeCandidate, VocabQuizClozeQuestion, VocabQuizEntry, VocabQuizListeningQuestion, VocabQuizMode, VocabQuizPinyinQuestion, VocabQuizPosQuestion, VocabQuizQuestion, VocabQuizQuestionResult, VocabQuizReverseQuestion, VocabQuizSummary, VocabQuizSynonymCandidate, VocabQuizSynonymQuestion, VocabQuizTranslationQuestion } from "./model";

/** A tiered vocabulary check shown before story speaking practice. */
export default function StoryVocabQuiz({ entries, onDone, onBack, onComplete, storyId, baseStoryId, level = "easy", studentId, studentName }: {
  entries: VocabQuizEntry[]; onDone: () => void; onBack?: () => void;
  onComplete?: (summary: VocabQuizSummary) => void; storyId?: string; baseStoryId?: string;
  level?: "easy" | "medium" | "hard"; studentId?: string; studentName?: string;
}) {
  const assessmentQuestionCounts = entries.reduce<Partial<Record<VocabAssessmentLevel, number>>>((counts, entry) => {
    (entry.assessmentQuestions ?? []).forEach((question) => {
      counts[question.level] = (counts[question.level] ?? 0) + 1;
    });
    return counts;
  }, {});
  useEffect(() => {
    if (!onBack) return;
    const handleBack = onBack;

    // StoryRecorderRuntime owns the header and passes the activity's internal
    // phase-history callback. Keep this click inside that activity; the
    // callback falls back to the outer page only at the activity boundary.
    const returnToPreviousPage = (event: MouseEvent) => {
      if (!(event.target instanceof Element) || !event.target.closest(".btn-story-exit")) return;
      event.preventDefault();
      event.stopPropagation();
      handleBack();
    };

    document.addEventListener("click", returnToPreviousPage, true);
    return () => document.removeEventListener("click", returnToPreviousPage, true);
  }, [onBack]);

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
  if (session.screen === "mode-select") return <ModeSelectScreen stars={session.stars} weakEntries={session.weakEntries} priorityReviewWords={session.priorityReviewWords} masteredWords={session.masteredWords} level={level} assessmentQuestionCounts={assessmentQuestionCounts} progress={session.lessonProgress} startTier={session.startTier} chooseWeakWords={() => { session.setIsRetryRound(false); session.chooseMode("weak_words", session.weakEntries, session.weakEntries.length); }} onContinue={() => { if (!session.lessonProgress.knowIt.completed) session.startTier("tier1"); else if (!session.lessonProgress.sayIt.completed) session.startTier("tier2"); else if (!session.lessonProgress.useIt.completed) session.startTier("tier3"); else session.setIsRetryRound(false); }} onFinish={onDone} startChallenge={session.showChallengeEntry} showReview={() => session.setScreen("review")} />;
  if (session.screen === "review") return <ReviewScreen entries={entries} back={() => session.setScreen("mode-select")} />;
  if (session.screen === "challenge-entry") return <ChallengeEntry progress={session.lessonProgress} onStart={session.startChallenge} onBack={() => session.setScreen("mode-select")} />;
  if (session.screen === "summary") return <SummaryScreen mode={session.mode} results={session.results} missedWords={session.missedWords} missedEntries={session.missedEntries} isRetryRound={session.isRetryRound} stars={session.stars} onDone={onDone} startTier={session.startTier} practiceMissedWords={session.practiceMissedWords} backToModes={session.returnToModes} progress={session.lessonProgress} onStartChallenge={session.startChallenge} challengeBestScore={session.challengeBestScore} onStartStrengthen={session.weakEntries.length > 0 ? () => { session.setIsRetryRound(false); session.chooseMode("weak_words", session.weakEntries, session.weakEntries.length); } : undefined} />;
  if (!session.question) return null;
  return <QuizQuestion question={session.question} mode={session.mode} selected={session.selected} results={session.results} index={session.index} questionLimit={session.questionLimit} requestedQuestionCount={session.requestedQuestionCount} isRetryRound={session.isRetryRound} isLast={session.isLast} timeLeftMs={session.timeLeftMs} timeLimitMs={session.timeLimitMs} showFinishButton={session.showFinishButton} choose={session.choose} next={session.next} finish={session.finish} speakWord={session.speakWord} progress={session.lessonProgress} />;
}
