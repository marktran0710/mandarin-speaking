import { useMemo, useState, type FormEvent } from "react";
import Modal from "../../shared/ui/Modal";
import Icon from "../../shared/ui/Icon";
import type { StoredCustomStory } from "../../services/api/stories-submissions";
import {
  createQuizVocabularyWord,
  updateQuizVocabularyWord,
  type QuizVocabularyLevel,
  type QuizVocabularyQuestionDraft,
} from "../../services/api/vocabulary";
import type { VocabularyEntry } from "./model";

const LEVELS: QuizVocabularyLevel[] = ["Easy", "Medium", "Hard"];
// Keep Unicode letters (including Chinese) while ignoring spacing and punctuation
// for duplicate/accepted-answer checks.
const normalizePrompt = (value: string) => value.normalize("NFKC").toLocaleLowerCase().replace(/[\s\p{P}\p{S}_]+/gu, "");

interface QuestionDraft extends QuizVocabularyQuestionDraft {
  optionsText: string;
  acceptedAnswersText: string;
}

function emptyQuestion(level: QuizVocabularyLevel): QuestionDraft {
  return {
    level,
    prompt: "",
    options: [],
    optionsText: level === "Hard" ? "" : "\n\n\n",
    correctAnswer: "",
    acceptedAnswers: [],
    acceptedAnswersText: "",
    explanation: "",
  };
}

function questionDrafts(entry: VocabularyEntry): QuestionDraft[] {
  return LEVELS.map((level) => {
    const question = entry.assessmentQuestions.find((candidate) => candidate.level.toLowerCase() === level.toLowerCase());
    if (!question) return emptyQuestion(level);
    return {
      level,
      prompt: question.prompt,
      options: question.options,
      optionsText: question.options.join("\n"),
      correctAnswer: question.correctAnswer,
      acceptedAnswers: question.acceptedAnswers,
      acceptedAnswersText: question.acceptedAnswers.join("\n"),
      explanation: question.explanation,
    };
  });
}

function lines(value: string): string[] {
  return value.split(/\r?\n/).map((item) => item.trim());
}

export default function QuizVocabularyEditor({ entry, onClose, onSaved }: {
  entry: VocabularyEntry;
  onClose: () => void;
  onSaved: (story: StoredCustomStory) => void;
}) {
  const isCreate = !entry.assessmentWordId;
  const [targetWord, setTargetWord] = useState(entry.word);
  const [pinyin, setPinyin] = useState(entry.pinyin);
  const [meaning, setMeaning] = useState(entry.translation);
  const [pos, setPos] = useState(entry.pos);
  const [questions, setQuestions] = useState<QuestionDraft[]>(() => questionDrafts(entry));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const initial = useMemo(() => JSON.stringify({ targetWord: entry.word, pinyin: entry.pinyin, meaning: entry.translation, pos: entry.pos, questions: questionDrafts(entry) }), [entry]);
  const current = JSON.stringify({ targetWord, pinyin, meaning, pos, questions });
  const dirty = isCreate || current !== initial;

  const close = () => {
    if (!saving && (!dirty || window.confirm("Discard unsaved quiz vocabulary changes?"))) onClose();
  };

  const updateQuestion = (index: number, changes: Partial<QuestionDraft>) => {
    setQuestions((currentQuestions) => currentQuestions.map((question, questionIndex) => (
      questionIndex === index ? { ...question, ...changes } : question
    )));
  };

  const save = async (event: FormEvent) => {
    event.preventDefault();
    if (saving) return;
    const word = targetWord.trim();
    const sharedValues = [word, pinyin.trim(), meaning.trim(), pos.trim()];
    if (sharedValues.some((value) => !value || /[\r\n]/.test(value))) {
      setError("Enter the Chinese word, pinyin, meaning and part of speech.");
      return;
    }
    const drafts: QuizVocabularyQuestionDraft[] = questions.map((question) => ({
      level: question.level,
      prompt: question.prompt.trim(),
      options: question.level === "Hard" ? [] : lines(question.optionsText),
      correctAnswer: question.correctAnswer.trim(),
      acceptedAnswers: lines(question.acceptedAnswersText),
      explanation: question.explanation.trim(),
    }));
    if (drafts.some((question) => !question.prompt || !question.correctAnswer || !question.explanation || question.acceptedAnswers.some((answer) => !answer))) {
      setError("Complete the prompt, answer, accepted answers and explanation for all three rounds.");
      return;
    }
    const normalizedPrompts = drafts.map((question) => normalizePrompt(question.prompt));
    if (normalizedPrompts.some((prompt, index) => !prompt || normalizedPrompts.indexOf(prompt) !== index)) {
      setError("The three question prompts must be unique.");
      return;
    }
    if (drafts.some((question) => question.level !== "Hard" && (question.options.length !== 4 || new Set(question.options.map(normalizePrompt)).size !== 4))) {
      setError("Easy and Medium questions need four unique options each.");
      return;
    }
    if (drafts.some((question) => !question.acceptedAnswers.some((answer) => normalizePrompt(answer) === normalizePrompt(question.correctAnswer)))) {
      setError("Accepted answers must include the correct answer for every round.");
      return;
    }

    setSaving(true);
    setError("");
    try {
      const draft = {
        ...(entry.assessmentWordId ? { wordId: entry.assessmentWordId } : {}),
        ...(entry.assessmentRevision ? { expectedRevision: entry.assessmentRevision } : {}),
        targetWord: word,
        pinyin: pinyin.trim(),
        pos: pos.trim(),
        simpleEnglishMeaning: meaning.trim(),
        questions: drafts,
      };
      const story = entry.assessmentWordId
        ? await updateQuizVocabularyWord(entry.storyId, entry.assessmentWordId, draft)
        : await createQuizVocabularyWord(entry.storyId, draft);
      onSaved(story);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not save quiz vocabulary.");
      setSaving(false);
    }
  };

  return <Modal open title={isCreate ? "Add quiz vocabulary" : `Edit quiz vocabulary: ${entry.word}`} onClose={close}>
    <form className="av-editor av-quiz-editor" onSubmit={save} aria-busy={saving}>
      <p className="av-editor-help">This word is stored as one shared item with three graded questions. Materials are managed separately.</p>
      <fieldset disabled={saving}>
        <label>Chinese word<input value={targetWord} onChange={(event) => setTargetWord(event.target.value)} required maxLength={200} /></label>
        <label>Pinyin<input value={pinyin} onChange={(event) => setPinyin(event.target.value)} required maxLength={300} /></label>
        <label>Meaning (English)<input value={meaning} onChange={(event) => setMeaning(event.target.value)} required maxLength={500} /></label>
        <label>Part of speech<input value={pos} onChange={(event) => setPos(event.target.value)} required maxLength={50} /></label>
      </fieldset>
      <div className="av-question-edit-list">
        {questions.map((question, index) => <fieldset className="av-question-edit" key={question.level} disabled={saving}>
          <legend>{question.level} question</legend>
          <label>{question.level} prompt<textarea aria-label={`${question.level} prompt`} value={question.prompt} onChange={(event) => updateQuestion(index, { prompt: event.target.value })} rows={2} required /></label>
          {question.level !== "Hard" && <label>{question.level} options (one per line)<textarea aria-label={`${question.level} options`} value={question.optionsText} onChange={(event) => updateQuestion(index, { optionsText: event.target.value })} rows={4} required /></label>}
          <label>{question.level} correct answer<input aria-label={`${question.level} correct answer`} value={question.correctAnswer} onChange={(event) => updateQuestion(index, { correctAnswer: event.target.value })} required /></label>
          <label>{question.level} accepted answers (one per line)<textarea aria-label={`${question.level} accepted answers`} value={question.acceptedAnswersText} onChange={(event) => updateQuestion(index, { acceptedAnswersText: event.target.value })} rows={2} required /></label>
          <label>{question.level} explanation<textarea aria-label={`${question.level} explanation`} value={question.explanation} onChange={(event) => updateQuestion(index, { explanation: event.target.value })} rows={2} required /></label>
        </fieldset>)}
      </div>
      {error && <p className="av-error" role="alert">{error}</p>}
      <div className="av-editor-actions">
        <button type="button" className="av-button" disabled={saving} onClick={close}>Cancel</button>
        <button type="submit" className="av-button av-primary" disabled={saving}><Icon name="check" size={18} />{saving ? "Saving..." : isCreate ? "Add word" : "Save quiz word"}</button>
      </div>
    </form>
  </Modal>;
}
