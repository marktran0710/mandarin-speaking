import { useEffect, useState } from "react";
import StudentPageHeader from "../components/StudentPageHeader";
import { BiLabel } from "../components/BiLabel";
import { canUseDatabase, listCustomStories, recordVocabQuizResponse, type VocabQuizAttempt } from "../services/database";
import { getStudentId, getStudentName } from "../utils/studentSession";
import { samplePlacementTestQuestions, type PlacementTestQuestion } from "../utils/placementTestSampling";
import "../styles/components/story-vocab-quiz/01-quiz-flow.css";
import "../styles/pages/placement-test-page/01-quiz-flow.css";

const WORDS_PER_LESSON = 4;

type Answer = { question: PlacementTestQuestion; selected: string; correct: boolean };

/** A standalone, ungated diagnostic: samples know-it (tier1) questions across
 * every published lesson so BKT has a starting read on words the student
 * hasn't reached in-app yet ("cold start"), instead of the same flat default
 * for everyone. Submits one attempt per lesson (see placementTestSampling.ts
 * for why: the server's answer resolver is scoped to a single story). Not
 * gated - a student can already be mid-course and take it, or skip it. */
export default function PlacementTestPage() {
  const [questions, setQuestions] = useState<PlacementTestQuestion[] | null>(null);
  const [index, setIndex] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);
  const [answers, setAnswers] = useState<Answer[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);

  useEffect(() => {
    if (!canUseDatabase()) {
      setQuestions([]);
      return;
    }
    listCustomStories()
      .then((stories) => setQuestions(samplePlacementTestQuestions(stories, WORDS_PER_LESSON)))
      .catch(() => setQuestions([]));
  }, []);

  if (questions === null) {
    return (
      <div className="placement-test-page">
        <div className="placement-test-loading" role="status">
          <div className="app-loading-icon" aria-hidden="true" />
          <h2><BiLabel zh="準備中…" en="Loading…" /></h2>
        </div>
      </div>
    );
  }

  if (questions.length === 0) {
    return (
      <div className="placement-test-page">
        <StudentPageHeader eyebrow={{ zh: "分班測驗", en: "Placement test" }} title={{ zh: "還沒有題目", en: "No questions available yet" }} lede={{ zh: "老師還沒發布任何生詞題庫。", en: "No published lesson has a vocabulary question bank yet." }} />
      </div>
    );
  }

  const submitAnswers = async (finalAnswers: Answer[]) => {
    setSubmitting(true);
    const byLesson = new Map<string, Answer[]>();
    for (const answer of finalAnswers) {
      const list = byLesson.get(answer.question.storyId) ?? [];
      list.push(answer);
      byLesson.set(answer.question.storyId, list);
    }
    const studentId = getStudentId();
    const studentName = getStudentName();
    const completedAt = new Date().toISOString();
    await Promise.allSettled(
      [...byLesson.entries()].map(([storyId, lessonAnswers]) => {
        const questionResults: VocabQuizAttempt["questionResults"] = lessonAnswers.map((answer, order) => ({
          word: answer.question.targetWord,
          correct: answer.correct,
          timeMs: 0,
          itemId: answer.question.itemId,
          conceptId: answer.question.wordId,
          questionKind: "basic_meaning_mcq",
          roundType: "know_it",
          knowledgeDimension: "meaning",
          activityType: "diagnostic",
          level: "easy",
          baseStoryId: storyId,
          itemVersion: "easy:v1",
          selectedAnswer: answer.selected,
          correctAnswer: answer.question.correctAnswer,
          presentedOptions: answer.question.options,
          questionPrompt: answer.question.prompt,
          answeredAt: completedAt,
          questionIndex: order,
          lessonId: storyId,
          quizId: `placement-${studentId ?? "anon"}-${storyId}-${Date.now()}`,
        }));
        const attempt: VocabQuizAttempt = {
          id: `placement-${studentId ?? "anon"}-${storyId}-${Date.now()}`,
          storyId,
          studentName,
          studentId,
          mode: "tier1",
          baseStoryId: storyId,
          level: "easy",
          completedAt,
          totalQuestions: questionResults.length,
          correctCount: questionResults.filter((result) => result.correct).length,
          totalTimeMs: 0,
          questionResults,
        };
        // Best-effort per lesson: one lesson's submission failing (e.g. a
        // dropped connection) must not lose the others or block the summary.
        return recordVocabQuizResponse(attempt).catch(() => {});
      }),
    );
    setSubmitting(false);
    setDone(true);
  };

  if (done) {
    return (
      <div className="placement-test-page">
        <StudentPageHeader
          eyebrow={{ zh: "分班測驗", en: "Placement test" }}
          title={{ zh: "測驗完成！", en: "Placement test complete!" }}
          lede={{ zh: "我們會依照你的答案安排接下來的複習。", en: "We'll personalize your review with what you shared." }}
        />
      </div>
    );
  }

  const question = questions[index];
  const isLast = index === questions.length - 1;

  const choose = (option: string) => {
    setSelected(option);
  };

  const advance = () => {
    if (!selected) return;
    const answer: Answer = { question, selected, correct: selected === question.correctAnswer };
    const nextAnswers = [...answers, answer];
    setAnswers(nextAnswers);
    setSelected(null);
    if (isLast) {
      void submitAnswers(nextAnswers);
    } else {
      setIndex((current) => current + 1);
    }
  };

  return (
    <div className="placement-test-page">
      <section className="story-vocab-quiz vocab-quiz-question-screen" aria-label="Placement test question">
        <div className="vocab-quiz-topbar placement-test-topbar">
          <p className="pt-quiz-context placement-test-title">
            <BiLabel zh="分班測驗" en="Placement test" />
          </p>
          <div className="vocab-quiz-status-progress placement-test-progress">
            <p className="vocab-quiz-progress"><BiLabel zh={`第 ${index + 1} / ${questions.length} 題`} en={`Question ${index + 1} of ${questions.length}`} /></p>
            <div className="vq-track">
              <div
                className="vq-track-rail"
                role="progressbar"
                aria-valuemin={0}
                aria-valuemax={questions.length}
                aria-valuenow={index + 1}
                aria-valuetext={`Question ${index + 1} of ${questions.length}`}
              >
                <span className="vq-track-fill" style={{ width: `${((index + 1) / questions.length) * 100}%` }} />
              </div>
            </div>
          </div>
        </div>
        <div className="vocab-quiz-content" key={question.itemId}>
          <div className="vocab-quiz-question-panel">
            <div className="vocab-quiz-header">
              <h1 className="vocab-quiz-word vocab-quiz-assessment-prompt">{question.prompt}</h1>
            </div>
          </div>
          <div className="vocab-quiz-answer-panel">
            <div className="vocab-quiz-options" role="group" aria-label="Answer choices">
              {question.options.map((option) => {
                const isChosen = option === selected;
                return (
                  <button
                    key={option}
                    type="button"
                    className={`vocab-quiz-option vocab-quiz-option-${isChosen ? "selected" : "neutral"}`}
                    onClick={() => choose(option)}
                    disabled={submitting}
                    aria-pressed={isChosen}
                  >
                    <span className="vocab-quiz-option-text">{option}</span>
                  </button>
                );
              })}
            </div>
            <div className="vocab-quiz-actions">
              <button type="button" className="btn-vocab-quiz-next" onClick={advance} disabled={!selected || submitting}>
                {submitting ? <BiLabel zh="送出中…" en="Submitting…" /> : isLast ? <BiLabel zh="完成" en="Finish" /> : <BiLabel zh="下一題" en="Next question" />}
              </button>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
