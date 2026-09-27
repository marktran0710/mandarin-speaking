import { useEffect, useRef } from "react";
import type { ReactNode } from "react";
import type {
  VocabQuizEntry,
  VocabQuizQuestion,
  VocabQuizQuestionResult,
} from "@entities/vocabulary";
import BilingualWord from "@shared/ui/student/BilingualWord";
import StudentAudioControl from "@shared/ui/student/StudentAudioControl";
import StudentButton from "@shared/ui/student/StudentButton";
import StudentIcon from "@shared/ui/student/StudentIcon";
import StudentSection from "@shared/ui/student/StudentSection";
import StudentStatusPill from "@shared/ui/student/StudentStatusPill";
import StudentSystemText from "@shared/ui/student/StudentSystemText";
import ToneKeypad from "./ToneKeypad";
import {
  extractClozeSentence,
  isFreeTextQuestion,
  questionPresentation,
  sentenceSegments,
  type QuizQuestionSurface as QuizSurfaceKind,
} from "./questionModel";

interface QuizQuestionSurfaceProps {
  question: VocabQuizQuestion;
  entry?: VocabQuizEntry;
  entries: VocabQuizEntry[];
  lessonLabel: string;
  draftAnswer: string | null;
  onDraftAnswerChange: (value: string | null) => void;
  pinyinDraft: string;
  onPinyinChange: (value: string) => void;
  showingFeedback: boolean;
  lastResult?: VocabQuizQuestionResult;
  onSubmit: () => void;
  onNext: () => void;
}

function RubyText({ text }: { text: string }) {
  return <>{sentenceSegments(text).map((segment, index) => <span key={`${segment.text}-${index}`}>{segment.text}</span>)}</>;
}

function ClozePrompt({ prompt }: { prompt: string }) {
  const sentence = extractClozeSentence(prompt);
  return (
    <div className="sa-quiz__cloze-stage" aria-label="完成句子">
      <p className="sa-quiz__cloze-sentence">
        <RubyText text={sentence.before} />
        {sentence.hasBlank && <span className="sa-quiz__cloze-slot" aria-label="missing word">____</span>}
        <RubyText text={sentence.after} />
      </p>
    </div>
  );
}

function optionMeta(option: string, entries: VocabQuizEntry[]) {
  const entry = entries.find((candidate) => candidate.word.trim() === option.trim());
  if (!entry) return undefined;
  return entry.translation ? { translation: entry.translation } : undefined;
}

function OptionLabel({ option, surface, entries }: { option: string; surface: QuizSurfaceKind; entries: VocabQuizEntry[] }) {
  const meta = surface === "context" ? optionMeta(option, entries) : undefined;
  return (
    <span className={`sa-quiz__option-copy ${surface === "context" ? "is-character" : ""}`}>
      <span className="sa-quiz__option-label">{option}</span>
      {meta && (
        <span className="sa-quiz__option-meta">
          {meta.translation && <span>{meta.translation}</span>}
        </span>
      )}
    </span>
  );
}

function Feedback({ result, explanation }: { result: VocabQuizQuestionResult; explanation?: string }) {
  return (
    <div className={`sa-quiz__feedback ${result.correct ? "is-correct" : "is-incorrect"}`} role="status" aria-live="polite">
      <StudentStatusPill tone={result.correct ? "success" : "attention"} icon={result.correct ? "check_circle" : "change_history"}>
        <StudentSystemText k={result.correct ? "correct" : "notQuite"} withinControl />
      </StudentStatusPill>
      <strong><StudentSystemText k={result.correct ? "quizCorrectMessage" : "quizReviewMessage"} /></strong>
      {!result.correct && result.correctAnswer && <span>答案：{result.correctAnswer}</span>}
      {explanation && <p>{explanation}</p>}
    </div>
  );
}

function Stimulus({
  question,
  presentation,
  lessonLabel,
}: {
  question: VocabQuizQuestion;
  presentation: ReturnType<typeof questionPresentation>;
  lessonLabel: string;
}) {
  let stage: ReactNode;
  if (presentation.surface === "context") {
    stage = <ClozePrompt prompt={presentation.prompt} />;
  } else {
    stage = <BilingualWord hanzi={question.word} size="hero" />;
  }
  const heading = presentation.surface === "context"
    ? <StudentSystemText k="chooseWordCompletesSentence" />
    : presentation.promptKey && !presentation.prompt
      ? <><StudentSystemText k={presentation.promptKey} />{presentation.promptData && <> <span>{presentation.promptData}</span></>}</>
      : presentation.prompt;

  return (
    <StudentSection variant="panel" className="sa-quiz__stimulus-card">
      <div className="sa-quiz__card-heading">
        <div>
          <span className="sa-quiz__section-kicker"><i /> <StudentSystemText k={presentation.labelKey} /></span>
          <h2 id="quiz-question-title">{heading}</h2>
        </div>
        <span className="sa-quiz__source-label">{lessonLabel}</span>
      </div>
      <div className={`sa-quiz__word-stage sa-quiz__word-stage--${presentation.surface}`}>{stage}</div>
      {presentation.audioUrl && (
        <div className="sa-quiz__prompt-footer">
          <StudentAudioControl audioUrl={presentation.audioUrl} labelKey="modelAudio" showDuration />
        </div>
      )}
    </StudentSection>
  );
}

export default function QuizQuestionSurface({
  question,
  entry,
  entries,
  lessonLabel,
  draftAnswer,
  onDraftAnswerChange,
  pinyinDraft,
  onPinyinChange,
  showingFeedback,
  lastResult,
  onSubmit,
  onNext,
}: QuizQuestionSurfaceProps) {
  const presentation = questionPresentation(question, entry);
  const freeText = isFreeTextQuestion(question);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (freeText || showingFeedback) return undefined;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement) return;
      if (/^[1-4]$/.test(event.key)) {
        const option = question.options[Number(event.key) - 1];
        if (option) {
          event.preventDefault();
          onDraftAnswerChange(option);
        }
      } else if (event.key === "Enter" && draftAnswer) {
        event.preventDefault();
        onSubmit();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [draftAnswer, freeText, onDraftAnswerChange, onSubmit, question.options, showingFeedback]);

  return (
    <section
      className="sa-quiz__question-column"
      aria-labelledby="quiz-question-title"
      data-verification-word={question.word}
    >
      <Stimulus
        question={question}
        presentation={presentation}
        lessonLabel={lessonLabel}
      />

      <div className="sa-quiz__answer-section">
        <div className="sa-quiz__answer-heading">
          <div>
            <p className="sa-quiz__section-kicker"><StudentSystemText k="yourResponse" /></p>
            <h3>{freeText ? <StudentSystemText k="typeReading" /> : presentation.surface === "context" ? <StudentSystemText k="completeSentence" /> : <StudentSystemText k="chooseOption" />}</h3>
          </div>
          {!showingFeedback && !freeText && (
            <span className="sa-quiz__keyboard-hint">
              <StudentSystemText k="keyboardHint" children={`按 1–${question.options.length} 選擇 · 按 Enter 提交`} />
            </span>
          )}
        </div>

        {!showingFeedback && freeText && (
          <div className="sa-quiz__input-block">
            <label htmlFor="sa-pinyin-input"><StudentSystemText k="pinyinWithTones" /></label>
            <input
              ref={inputRef}
              id="sa-pinyin-input"
              type="text"
              className="sa-quiz__input"
              value={pinyinDraft}
              onChange={(event) => onPinyinChange(event.target.value)}
              placeholder="e.g. na3 li3"
              autoComplete="off"
              aria-describedby="sa-pinyin-help"
              onKeyDown={(event) => {
                if (event.key === "Enter" && pinyinDraft.trim()) {
                  event.preventDefault();
                  onSubmit();
                }
              }}
            />
            <span id="sa-pinyin-help" className="sa-quiz__input-help"><StudentSystemText k="useToneMarks" /></span>
            <ToneKeypad inputRef={inputRef} value={pinyinDraft} onChange={onPinyinChange} />
          </div>
        )}

        {!showingFeedback && !freeText && (
          <div className="sa-quiz__options" role="group" aria-label="答案選項">
            {question.options.map((option, index) => {
              const selected = draftAnswer === option;
              return (
                <button
                  key={`${option}-${index}`}
                  type="button"
                  className={`sa-quiz__option ${selected ? "is-selected" : ""}`}
                  onClick={() => onDraftAnswerChange(option)}
                  aria-pressed={selected}
                  aria-label={`選項 ${index + 1}：${option}`}
                >
                  <span className="sa-quiz__option-index">{index + 1}</span>
                  <OptionLabel option={option} surface={presentation.surface} entries={entries} />
                  <StudentIcon name={selected ? "check_circle" : "radio_button_unchecked"} size={20} role="decorative" />
                </button>
              );
            })}
          </div>
        )}

        {showingFeedback && lastResult && <Feedback result={lastResult} explanation={presentation.explanation} />}

        <div className="sa-quiz__actions">
          <div className="sa-quiz__action-note">
            {!showingFeedback && !freeText && <span>{draftAnswer ? <StudentSystemText k="readyToSubmit" /> : <StudentSystemText k="submitChoiceHint" />}</span>}
            {!showingFeedback && freeText && <span><StudentSystemText k="submitReadingHint" /></span>}
          </div>
          {showingFeedback ? (
            <StudentButton variant="primary" iconTrailing="arrow_forward" onClick={onNext}><StudentSystemText k="nextQuestion" withinControl /></StudentButton>
          ) : (
            <StudentButton variant="primary" disabled={freeText ? !pinyinDraft.trim() : !draftAnswer} onClick={onSubmit}>
              <StudentSystemText k={freeText ? "checkAnswer" : "submitAnswer"} withinControl />
            </StudentButton>
          )}
        </div>
      </div>
    </section>
  );
}
