import { useEffect, useMemo, useState } from "react";
import type { Topic } from "../../components/content/topic-selector/types";
import { topicQuizEntries } from "../../utils/topicQuiz";
import { DIAGNOSTIC_ROUNDS, type TierMode } from "../../utils/quizTiers";
import { useQuizSession } from "../../components/story-vocab-quiz/useQuizSession";
import { getStudentId, getStudentName } from "../../utils/studentSession";
import StudentPageHeader from "../primitives/StudentPageHeader";
import StudentSection from "../primitives/StudentSection";
import StudentButton from "../primitives/StudentButton";
import StudentAudioControl from "../primitives/StudentAudioControl";
import StudentIcon from "../primitives/StudentIcon";
import "../primitives/layout.css";
import "./VocabularyQuizPage.css";

interface VocabularyQuizPageProps {
  topic: Topic;
  lessonLabel: string;
  onFinished: () => void;
}

const TIER_SEQUENCE: TierMode[] = ["tier1", "tier2", "tier3"];
const ROUND_LABEL: Record<TierMode, string> = { tier1: "Know It", tier2: "Say It", tier3: "Use It" };

export default function VocabularyQuizPage({ topic, lessonLabel, onFinished }: VocabularyQuizPageProps) {
  const entries = useMemo(() => topicQuizEntries(topic), [topic]);
  const session = useQuizSession({
    entries,
    storyId: topic.id,
    baseStoryId: topic.sourceStory?.id,
    level: "easy",
    studentId: getStudentId(),
    studentName: getStudentName(),
  });
  const [tierPos, setTierPos] = useState(0);
  const [pinyinDraft, setPinyinDraft] = useState("");

  // Auto-run the three diagnostic rounds in sequence — the approved design
  // has no separate mode-select screen, it's always Know It -> Say It ->
  // Use It for a lesson's vocabulary quiz.
  useEffect(() => {
    if (session.screen === "mode-select") {
      session.startTier(TIER_SEQUENCE[0]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session.screen]);

  useEffect(() => {
    if (session.screen !== "summary") return;
    const nextPos = tierPos + 1;
    if (nextPos < TIER_SEQUENCE.length) {
      setTierPos(nextPos);
      session.startTier(TIER_SEQUENCE[nextPos]);
    } else {
      onFinished();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session.screen]);

  useEffect(() => {
    setPinyinDraft("");
  }, [session.index, session.mode]);

  if (session.screen !== "quiz" || !session.question) {
    return null;
  }

  const question = session.question;
  const assessment = question.kind === "assessment" ? question.assessment : null;
  const isFreeText = assessment?.answerFormat === "free_text";
  const lastResult = session.results[session.results.length - 1];
  const answered = session.selected !== null;
  const showingFeedback = answered && lastResult?.word === question.word;

  return (
    <div className="sa-page-container sa-page-container--narrow">
      <StudentPageHeader
        eyebrowEn={`Study · ${lessonLabel} · Vocabulary Quiz`}
        titleZh="生詞測驗"
        titleEn={`Question ${session.index + 1} / ${session.questionLimit ?? entries.length}`}
      />

      <div className="sa-quiz__round-strip" role="tablist" aria-label="Quiz rounds">
        {TIER_SEQUENCE.map((tier, i) => (
          <span
            key={tier}
            className={`sa-quiz__round ${i < tierPos ? "is-done" : i === tierPos ? "is-current" : "is-upcoming"}`}
          >
            {i < tierPos && <StudentIcon name="check" size={14} role="decorative" />}
            {ROUND_LABEL[DIAGNOSTIC_ROUNDS[tier].mode]}
          </span>
        ))}
      </div>

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
                onClick={() => session.choose(opt)}
              >
                {opt}
              </button>
            ))}
          </div>
        )}

        {showingFeedback && (
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
          <StudentAudioControl fallbackText={question.word} label="Audio Model" />
          {showingFeedback ? (
            <StudentButton variant="primary" iconTrailing="arrow_forward" onClick={session.next}>
              Next
            </StudentButton>
          ) : isFreeText ? (
            <StudentButton
              variant="primary"
              disabled={!pinyinDraft.trim()}
              onClick={() => session.choose(pinyinDraft.trim())}
            >
              Submit
            </StudentButton>
          ) : null}
        </div>
      </StudentSection>
    </div>
  );
}
