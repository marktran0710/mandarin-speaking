import { useEffect, useRef, useState } from "react";
import type { useCombinedReviewSession } from "../hooks/useCombinedReviewSession";
import StudentButton from "@shared/ui/student/StudentButton";
import StudentIcon from "@shared/ui/student/StudentIcon";
import StudentSection from "@shared/ui/student/StudentSection";
import StudentSystemText from "@shared/ui/student/StudentSystemText";
import "./CombinedReviewSession.css";

type ReviewFlow = ReturnType<typeof useCombinedReviewSession>;

const DIMENSION_COPY = {
  meaning: "knowIt",
  pinyin: "sayIt",
  context: "useIt",
} as const;

export default function CombinedReviewSession({
  review,
  onClose,
  onDiscardStale,
}: {
  review: ReviewFlow;
  onClose: () => void;
  onDiscardStale: () => void;
}) {
  const question = review.question;
  const [draft, setDraft] = useState("");
  const [selectedOption, setSelectedOption] = useState<string | null>(null);
  const questionStartedAt = useRef(Date.now());

  useEffect(() => {
    setDraft("");
    setSelectedOption(null);
    questionStartedAt.current = Date.now();
  }, [question?.slotId, review.lastResult]);

  if (review.stale) {
    return (
      <StudentSection variant="panel" className="sa-review-session__state" role="alert">
        <StudentIcon name="sync_problem" size={24} role="decorative" />
        <p><StudentSystemText k="lessonVocabularyUpdated" /></p>
        <StudentButton variant="primary" icon="refresh" onClick={onDiscardStale}>
          <StudentSystemText k="refreshReviewQueue" withinControl />
        </StudentButton>
      </StudentSection>
    );
  }

  if (review.error) {
    return (
      <StudentSection variant="panel" className="sa-review-session__state" role="alert">
        <StudentIcon name="error" size={24} role="decorative" />
        <p><StudentSystemText k="retryNetwork" /></p>
        <div className="sa-review-session__actions">
          <StudentButton variant="primary" icon="refresh" disabled={review.isSubmitting} onClick={() => void review.retrySave()}>
            <StudentSystemText k="retry" withinControl />
          </StudentButton>
          <StudentButton variant="subtle" onClick={onClose}>
            <StudentSystemText k="backToPracticeOptions" withinControl />
          </StudentButton>
        </div>
      </StudentSection>
    );
  }

  if (!review.session) return null;

  const answer = review.lastResult;

  if (!question && !answer) {
    return (
      <StudentSection variant="panel" className="sa-review-session__state">
        <StudentStatusIcon />
        <p className="sa-review-session__title"><StudentSystemText k="practiceComplete" /></p>
        <p className="sa-review-session__progress-copy">{review.session.completedCount} / {review.session.questionCount}</p>
        <StudentButton variant="primary" iconTrailing="arrow_back" onClick={onClose}>
          <StudentSystemText k="backToPracticeOptions" withinControl />
        </StudentButton>
      </StudentSection>
    );
  }

  const item = answer ?? question;
  if (!item) return null;

  const selectedAnswer = question?.answerFormat === "free_text" ? draft.trim() : selectedOption;
  const progress = review.session.questionCount > 0
    ? (review.session.completedCount / review.session.questionCount) * 100
    : 0;

  return (
    <div className="sa-review-session">
      <div className="sa-review-session__topline">
        <p className="sa-review-session__eyebrow">
          <StudentSystemText k={item.reviewReason === "due" ? "reviewToday" : "personalisedPractice"} />
          <span aria-hidden="true"> · </span>
          <StudentSystemText k={DIMENSION_COPY[item.dimension]} />
        </p>
        <span className="sa-review-session__count">
          {answer ? answer.position : question?.position} / {question?.totalQuestions ?? review.session.questionCount}
        </span>
      </div>
      <div
        className="sa-review-session__progress"
        role="progressbar"
        aria-label="Review session progress"
        aria-valuemin={0}
        aria-valuemax={review.session.questionCount}
        aria-valuenow={review.session.completedCount}
      >
        <span style={{ width: `${progress}%` }} />
      </div>

      <StudentSection variant="panel" className="sa-review-session__card">
        <h2 className="sa-review-session__word" lang="zh-Hant">{item.word}</h2>
        {!answer && question && <p className="sa-review-session__prompt">{question.prompt}</p>}

        {!answer && question?.answerFormat === "single_choice" && (
          <div className="sa-review-session__options" role="group" aria-label="Choose an answer">
            {question.options.map((option) => (
              <StudentButton
                key={option}
                variant={selectedOption === option ? "primary" : "secondary"}
                className="sa-review-session__option"
                aria-pressed={selectedOption === option}
                disabled={review.isSubmitting}
                onClick={() => setSelectedOption(option)}
              >
                <span lang="zh-Hant">{option}</span>
              </StudentButton>
            ))}
          </div>
        )}

        {!answer && question?.answerFormat === "free_text" && (
          <div className="sa-review-session__input-wrap">
            <label htmlFor="sa-review-pinyin"><StudentSystemText k="typePinyinReading" /></label>
            <input
              id="sa-review-pinyin"
              className="sa-review-session__input"
              autoComplete="off"
              maxLength={500}
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && draft.trim()) {
                  void review.submit(draft.trim(), Date.now() - questionStartedAt.current);
                }
              }}
              disabled={review.isSubmitting}
            />
          </div>
        )}

        {answer && (
          <div className={`sa-review-session__feedback ${answer.correct ? "is-correct" : "is-incorrect"}`} role="status" aria-live="polite">
            <strong><StudentSystemText k={answer.correct ? "correct" : "notQuite"} /></strong>
            <p className="sa-review-session__correct-answer">{answer.correctAnswer}</p>
            {answer.explanation && <p>{answer.explanation}</p>}
          </div>
        )}

        <div className="sa-review-session__actions">
          {!answer ? (
            <StudentButton
              variant="primary"
              iconTrailing="arrow_forward"
              disabled={!selectedAnswer || review.isSubmitting}
              onClick={() => void review.submit(selectedAnswer!, Date.now() - questionStartedAt.current)}
            >
              <StudentSystemText k="checkAnswer" withinControl />
            </StudentButton>
          ) : (
            <StudentButton variant="primary" iconTrailing="arrow_forward" onClick={review.continueAfterFeedback}>
              <StudentSystemText k={review.session.completedCount === review.session.questionCount ? "finish" : "continue"} withinControl />
            </StudentButton>
          )}
          <StudentButton variant="subtle" onClick={onClose} disabled={review.isSubmitting}>
            <StudentSystemText k="backToPracticeOptions" withinControl />
          </StudentButton>
        </div>
      </StudentSection>
    </div>
  );
}

function StudentStatusIcon() {
  return <StudentIcon name="check_circle" size={24} role="decorative" filled />;
}
