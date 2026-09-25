import { useEffect, useState } from "react";
import type { Topic } from "../../components/content/topic-selector/types";
import { useVocabQuizFlow } from "./hooks/useVocabQuizFlow";
import { ROUND_LABEL, TIER_SEQUENCE } from "./model/tierRounds";
import StudentPageHeader from "../primitives/StudentPageHeader";
import StudentSection from "../primitives/StudentSection";
import StudentButton from "../primitives/StudentButton";
import StudentAudioControl from "../primitives/StudentAudioControl";
import StudentIcon from "../primitives/StudentIcon";
import StudentStatusPill from "../primitives/StudentStatusPill";
import "../primitives/layout.css";
import "./VocabularyQuizPage.css";

interface VocabularyQuizPageProps {
  topic: Topic;
  lessonLabel: string;
  onFinished: () => void;
}

export default function VocabularyQuizPage({ topic, lessonLabel, onFinished }: VocabularyQuizPageProps) {
  const flow = useVocabQuizFlow({ topic, onFinished });
  const [pinyinDraft, setPinyinDraft] = useState("");

  useEffect(() => {
    setPinyinDraft("");
  }, [flow.index, flow.tierPos]);

  if (flow.view === "loading") {
    return null;
  }

  const isLastTier = flow.tierPos === TIER_SEQUENCE.length - 1;
  const question = flow.question;
  const assessment = question?.kind === "assessment" ? question.assessment : null;
  const isFreeText = assessment?.answerFormat === "free_text";
  const lastResult = flow.results[flow.results.length - 1];
  const answered = flow.selected !== null;
  const showingFeedback = answered && question != null && lastResult?.word === question.word;

  return (
    <div className="sa-page-container sa-page-container--narrow">
      <StudentPageHeader
        eyebrowEn={`Study · ${lessonLabel} · Vocabulary Quiz`}
        titleZh="生詞測驗"
        titleEn={
          flow.view === "quiz"
            ? `Question ${flow.index + 1} / ${flow.questionLimit ?? flow.entries.length}`
            : "Round complete"
        }
      />

      <div className="sa-quiz__round-strip" role="tablist" aria-label="Quiz rounds">
        {TIER_SEQUENCE.map((tier, i) => (
          <span
            key={tier}
            className={`sa-quiz__round ${i < flow.tierPos ? "is-done" : i === flow.tierPos ? "is-current" : "is-upcoming"}`}
          >
            {i < flow.tierPos && <StudentIcon name="check" size={14} role="decorative" />}
            {ROUND_LABEL[tier]}
          </span>
        ))}
      </div>

      {flow.view === "round-result" && flow.roundResult ? (
        <StudentSection variant="panel" className="sa-quiz__round-result">
          <StudentStatusPill tone={flow.roundResult.passed ? "success" : "attention"}>
            {flow.roundResult.passed ? "Passed" : "Not quite"}
          </StudentStatusPill>
          <p className="sa-quiz__round-result-score">
            {flow.roundResult.correctCount} / {flow.roundResult.totalQuestions}
          </p>
          {!flow.roundResult.passed && !!flow.roundResult.starGap && (
            <p className="sa-quiz__round-result-gap">
              {flow.roundResult.starGap} more correct for {ROUND_LABEL[flow.roundResult.tier]}
            </p>
          )}
          {flow.roundResult.passed ? (
            <StudentButton variant="primary" iconTrailing="arrow_forward" onClick={flow.continueToNext}>
              {isLastTier ? "Finish" : "Continue"}
            </StudentButton>
          ) : (
            <StudentButton variant="primary" icon="replay" onClick={flow.retry}>
              Try Again
            </StudentButton>
          )}
        </StudentSection>
      ) : question ? (
        <StudentSection variant="panel" className="sa-quiz__card">
          <p className="sa-quiz__lesson-tag">{lessonLabel}</p>

          <div className="sa-quiz__stimulus">
            <span lang="zh-Hant" className="sa-quiz__hanzi">{question.word}</span>
          </div>

          {!showingFeedback && isFreeText && (
            <div className="sa-quiz__input-block">
              <label htmlFor="sa-pinyin-input" className="sa-quiz__input-label">Type the pinyin</label>
              <input
                id="sa-pinyin-input"
                type="text"
                className="sa-quiz__input"
                value={pinyinDraft}
                onChange={(e) => setPinyinDraft(e.target.value)}
                placeholder="e.g. na3 li3"
                autoComplete="off"
              />
            </div>
          )}

          {!showingFeedback && !isFreeText && (
            <div className="sa-quiz__options">
              {question.options.map((opt) => (
                <button
                  key={opt}
                  type="button"
                  className="sa-quiz__option"
                  onClick={() => flow.choose(opt)}
                >
                  {opt}
                </button>
              ))}
            </div>
          )}

          {showingFeedback && lastResult && (
            <div className={`sa-quiz__feedback ${lastResult.correct ? "is-correct" : "is-incorrect"}`}>
              <span className="sa-quiz__feedback-badge">
                <StudentIcon name={lastResult.correct ? "check_circle" : "change_history"} size={16} role="decorative" />
                {lastResult.correct ? "Correct" : "Not quite"}
              </span>
              <span lang="zh-Hant" className="sa-quiz__feedback-word">{question.word}</span>
              {!lastResult.correct && (
                <span className="sa-quiz__feedback-answer">Answer: {lastResult.correctAnswer}</span>
              )}
            </div>
          )}

          <div className="sa-quiz__actions">
            <StudentAudioControl audioUrl={assessment?.audioUrl} label="Audio Model" />
            {showingFeedback ? (
              <StudentButton variant="primary" iconTrailing="arrow_forward" onClick={flow.next}>
                Next
              </StudentButton>
            ) : isFreeText ? (
              <StudentButton
                variant="primary"
                disabled={!pinyinDraft.trim()}
                onClick={() => flow.choose(pinyinDraft.trim())}
              >
                Submit
              </StudentButton>
            ) : null}
          </div>
        </StudentSection>
      ) : null}
    </div>
  );
}
