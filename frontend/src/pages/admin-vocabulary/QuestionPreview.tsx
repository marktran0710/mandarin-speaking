import { useMemo } from "react";
import Modal from "../../shared/ui/Modal";
import StudentAudioControl from "../../student/primitives/StudentAudioControl";
import type { StoredCustomStory } from "../../services/api/stories-submissions";
import type { CustomTeacherStory } from "../../utils/teacher-stories/types";
import { parseJsonArray, resolveImageUrl } from "../../utils/teacher-stories/helpers";
import { storyToTopic } from "../../utils/teacher-stories/mappers";
import { topicQuizEntries } from "../../utils/topicQuiz";
import {
  buildWordQuestionVariants,
  CLOZE_BLANK,
  type VocabAssessmentQuestion,
  type VocabQuizQuestion,
} from "../../components/story-vocab-quiz/model";
import type { VocabularyEntry } from "./model";

/** One question rendered as a uniform shape regardless of source kind. */
interface PreviewCard {
  prompt: string;
  options: string[];
  answer: string;
  /** True when the student types the answer (no options list). */
  typed: boolean;
}

const ROUND_LABEL: Record<string, { round: string; en: string }> = {
  know_it: { round: "Round 1", en: "Know it — meaning" },
  say_it: { round: "Round 2", en: "Say it — pinyin" },
  use_it: { round: "Round 3", en: "Use it — in context" },
};

const KIND_LABEL: Record<string, string> = {
  translation: "Meaning (multiple choice)",
  cloze: "Fill in the blank",
  pinyin: "Choose the pinyin",
  pos: "Part of speech",
  synonym: "Closest synonym",
  reverse: "English → Chinese",
  listening: "Listen and choose",
};

function fromAssessment(question: VocabAssessmentQuestion): PreviewCard {
  return {
    prompt: question.prompt,
    options: question.options ?? [],
    answer: question.correctAnswer,
    typed: question.answerFormat === "free_text",
  };
}

function fromPractice(question: VocabQuizQuestion): PreviewCard {
  switch (question.kind) {
    case "translation":
      return { prompt: `What does ${question.word} mean?`, options: question.options, answer: question.correctTranslation, typed: false };
    case "cloze":
      return { prompt: question.sentenceWithBlank, options: question.options, answer: question.correctWord, typed: false };
    case "pinyin":
      return { prompt: `Choose the pinyin for ${question.word}.`, options: question.options, answer: question.correctPinyin, typed: false };
    case "pos":
      return { prompt: `What part of speech is ${question.word}?`, options: question.options, answer: question.correctPos, typed: false };
    case "synonym":
      return { prompt: `Which word means the same as ${question.word}?`, options: question.options, answer: question.correctSynonym, typed: false };
    case "reverse":
      return { prompt: `Which word means “${question.translation}”?`, options: question.options, answer: question.correctWord, typed: false };
    case "listening":
      return { prompt: `Listen, then choose the word you heard (${question.word}).`, options: question.options, answer: question.correctWord, typed: false };
    default:
      return { prompt: "", options: [], answer: "", typed: false };
  }
}

function QuestionCard({ heading, sub, card, aiBadge }: { heading: string; sub?: string; card: PreviewCard; aiBadge?: boolean }) {
  return (
    <li className="av-qcard">
      <div className="av-qcard-head">
        <span className="av-qcard-kind">{heading}</span>
        {sub && <span className="av-qcard-sub">{sub}</span>}
        {aiBadge && <span className="av-qcard-ai">AI</span>}
      </div>
      <p className="av-qcard-prompt" lang="zh-Hant">{renderPrompt(card.prompt)}</p>
      {card.typed ? (
        <p className="av-qcard-typed">Typed answer: <strong lang="zh-Hant">{card.answer}</strong></p>
      ) : (
        <ul className="av-qcard-options">
          {card.options.map((option, index) => (
            <li key={`${option}-${index}`} className={option === card.answer ? "is-correct" : undefined} lang="zh-Hant">
              {option}
              {option === card.answer && <span className="av-qcard-tick" aria-label="correct answer"> ✓</span>}
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}

/** Cloze prompts carry a blank marker; show it as a visible gap. */
function renderPrompt(prompt: string) {
  if (!prompt.includes(CLOZE_BLANK)) return prompt;
  const [before, after] = prompt.split(CLOZE_BLANK);
  return <>{before}<span className="av-qcard-blank">____</span>{after}</>;
}

function previewAudioUrl(entry: VocabularyEntry, story: StoredCustomStory | undefined): string | undefined {
  const importedAudio = entry.assessmentQuestions
    .map(question => question.audioUrl?.trim())
    .find((url): url is string => Boolean(url));
  if (importedAudio) return resolveImageUrl(importedAudio);

  const frameAudio = parseJsonArray(story?.frames[entry.frameIndex]?.vocabularyAudioUrls)?.[entry.wordIndex];
  return typeof frameAudio === "string" && frameAudio.trim() ? resolveImageUrl(frameAudio.trim()) : undefined;
}

export default function QuestionPreview({ entry, story, onClose }: {
  entry: VocabularyEntry; story: StoredCustomStory | undefined; onClose: () => void;
}) {
  const variants = useMemo(() => {
    if (!story) return null;
    // storyToTopic reads only fields StoredCustomStory also carries; the two
    // story types are declared separately, so bridge them structurally.
    const topic = storyToTopic(story as unknown as CustomTeacherStory, "easy");
    const entries = topicQuizEntries(topic);
    const wordEntry = entry.assessmentWordId
      ? entries.find((candidate) => candidate.wordId === entry.assessmentWordId)
      : entries.find((candidate) => candidate.word === entry.word);
    if (!wordEntry) return { rounds: [], practice: [], entries: entries.length };
    return { ...buildWordQuestionVariants(wordEntry, entries), entries: entries.length };
  }, [story, entry.word, entry.assessmentWordId]);
  const audioUrl = previewAudioUrl(entry, story);

  return (
    <Modal open title={`Quiz questions: ${entry.word}`} onClose={onClose}>
      <div className="av-qpreview">
        <div className="av-qpreview-audio">
          <div className="av-qpreview-word">
            <div className="av-qpreview-word-copy">
              <span className="av-qpreview-kicker">Vocabulary audio</span>
              <strong lang="zh-Hant">{entry.word}</strong>
              <span>{entry.pinyin || "Pinyin unavailable"}</span>
            </div>
            <StudentAudioControl audioUrl={audioUrl} fallbackText={entry.word} label="Listen to word" />
          </div>
          <p className="av-qpreview-audio-status">
            {audioUrl ? "Imported model audio" : "No imported clip yet; using your browser's Chinese voice."}
          </p>
        </div>
        <p className="av-qpreview-lead">
          Every question form <strong lang="zh-Hant">{entry.word}</strong> can appear as — the three graded rounds,
          plus the extra practice types its data supports. Options are shuffled each time; the ✓ marks the correct answer.
        </p>
        {!story ? (
          <p className="av-empty" role="status">Story not found for this word.</p>
        ) : !variants || (variants.rounds.length === 0 && variants.practice.length === 0) ? (
          <p className="av-empty" role="status">
            No generated questions yet for this word. Publish/approve the quiz for this story to see its questions.
          </p>
        ) : (
          <>
            <section aria-label="Graded rounds">
              <h3 className="av-qsection">Graded rounds</h3>
              {variants.rounds.length ? (
                <ul className="av-qlist">
                  {variants.rounds.map((round) => {
                    const label = ROUND_LABEL[round.roundType];
                    return <QuestionCard key={round.mode} heading={label?.round ?? round.mode} sub={label?.en} card={fromAssessment(round.question)} />;
                  })}
                </ul>
              ) : <p className="av-empty">No round questions generated yet.</p>}
            </section>
            {variants.practice.length > 0 && (
              <section aria-label="Extra practice types">
                <h3 className="av-qsection">Extra practice types</h3>
                <ul className="av-qlist">
                  {variants.practice.map((item) => (
                    <QuestionCard
                      key={item.kind}
                      heading={KIND_LABEL[item.kind] ?? item.kind}
                      card={fromPractice(item.question)}
                      aiBadge={"isAiGenerated" in item.question && item.question.isAiGenerated}
                    />
                  ))}
                </ul>
              </section>
            )}
          </>
        )}
      </div>
    </Modal>
  );
}
