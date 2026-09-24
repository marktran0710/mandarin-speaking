import type { StoredCustomStory } from "../../services/api/stories-submissions";
import type { VocabAssessmentQuestion } from "../../components/story-vocab-quiz/model";
import { buildVocabRows, type VocabRow } from "../../utils/myStoriesUtils";
import { tierText } from "../../utils/teacher-stories/helpers";

export type VocabularyTier = "easy";
export type VocabularySource = "quiz-assessment" | "story-vocabulary" | "scene-vocabulary";
export interface VocabularyEntry extends VocabRow {
  id: string;
  storyId: string;
  storyTitle: string;
  lessonNumber: number | null;
  lessonSubOrder: number | null;
  frameIndex: number;
  wordIndex: number;
  storyWide: boolean;
  source: VocabularySource;
  assessmentWordId?: string;
  assessmentRevision?: string;
  assessmentQuestions: VocabAssessmentQuestion[];
  tier: VocabularyTier;
  context: string;
  published: boolean;
  expected: { vocabulary: string; pinyin: string; translation: string; pos: string };
}

// The quiz runs one vocabulary set through three rounds. The per-word AI
// question data (distractors/cloze/synonym) belongs to that base word list, so
// the inventory is built from one canonical level and never triplicated.
// (`tier` stays "easy" because the metadata-save API is still keyed by it.)
const CANONICAL_TIER = "easy" as const;

// Restrict a story's authored vocabulary rows to just the words the published
// quiz assessment actually tests, deduped by word (the same first-occurrence
// rule the live rounds use). This keeps the admin inventory in sync with the
// rounds — which build their word list from vocabAssessment — instead of
// listing every word that appears in the story frames. Stories with no
// assessment fall through unchanged (they show their full authored list).
export function buildVocabularyInventory(stories: StoredCustomStory[]): VocabularyEntry[] {
  return [...stories].sort((a, b) => (a.lessonNumber ?? Infinity) - (b.lessonNumber ?? Infinity)
    || (a.lessonSubOrder ?? 0) - (b.lessonSubOrder ?? 0) || a.title.localeCompare(b.title))
    .flatMap(story => {
      if (Array.isArray(story.vocabAssessment)) {
        const assessmentByWordId = new Map<string, typeof story.vocabAssessment>();
        story.vocabAssessment.forEach(question => {
          const wordId = question.wordId.trim();
          if (!wordId || assessmentByWordId.has(wordId)) return;
          assessmentByWordId.set(wordId, story.vocabAssessment!.filter(item => item.wordId === wordId));
        });
        const context = story.frames.find(frame => frame.suggestedAnswer || frame.listenScript || frame.prompt);
        return Array.from(assessmentByWordId.entries()).map(([assessmentWordId, questions], wordIndex) => {
          const question = questions[0]!;
          const expected = { vocabulary: question.targetWord, pinyin: question.pinyin, translation: question.simpleEnglishMeaning, pos: question.pos };
          return {
            word: question.targetWord, pinyin: question.pinyin, translation: question.simpleEnglishMeaning, pos: question.pos,
            id: JSON.stringify([story.id, "quiz-assessment", assessmentWordId]), storyId: story.id, storyTitle: story.title,
            lessonNumber: story.lessonNumber ?? null, lessonSubOrder: story.lessonSubOrder ?? null,
            frameIndex: 0, wordIndex, storyWide: false, source: "quiz-assessment" as const, assessmentWordId,
            assessmentQuestions: questions,
            assessmentRevision: story.vocabAssessmentRevision ?? undefined,
            tier: CANONICAL_TIER, expected,
            context: context ? tierText(context, "suggestedAnswer", CANONICAL_TIER) || tierText(context, "listenScript", CANONICAL_TIER) || tierText(context, "prompt", CANONICAL_TIER) || "" : "",
            published: Boolean(story.published),
          };
        }).filter(row => Boolean(row.word));
      }
      const storyWide = story.storyVocabulary?.easy;
      let entries: VocabularyEntry[];
      if (storyWide) {
        const expected = {
          vocabulary: storyWide.vocabulary || "",
          pinyin: storyWide.vocabularyPinyin || "",
          translation: storyWide.vocabularyTranslation || "",
          pos: storyWide.vocabularyPos || "",
        };
        const context = story.frames.find(frame => frame.suggestedAnswer || frame.listenScript || frame.prompt);
        entries = buildVocabRows(expected.vocabulary, expected.pinyin, expected.pos, expected.translation)
          .map((row, wordIndex) => ({
            ...row, id: JSON.stringify([story.id, "story-wide", wordIndex]), storyId: story.id,
            storyTitle: story.title, lessonNumber: story.lessonNumber ?? null,
            lessonSubOrder: story.lessonSubOrder ?? null, frameIndex: 0, wordIndex, tier: CANONICAL_TIER,
            storyWide: true, source: "story-vocabulary" as const, expected,
            assessmentQuestions: [],
            context: context ? tierText(context, "suggestedAnswer", CANONICAL_TIER) || tierText(context, "listenScript", CANONICAL_TIER) || tierText(context, "prompt", CANONICAL_TIER) || "" : "",
            published: Boolean(story.published),
          })).filter(row => Boolean(row.word));
      } else {
        entries = story.frames.flatMap((frame, frameIndex) => {
          const expected = {
            vocabulary: tierText(frame, "vocabulary", CANONICAL_TIER) || "",
            pinyin: tierText(frame, "vocabularyPinyin", CANONICAL_TIER) || "",
            translation: tierText(frame, "vocabularyTranslation", CANONICAL_TIER) || "",
            pos: tierText(frame, "vocabularyPos", CANONICAL_TIER) || "",
          };
          return buildVocabRows(expected.vocabulary, expected.pinyin, expected.pos, expected.translation)
            .map((row, wordIndex) => ({
              ...row, id: JSON.stringify([story.id, frameIndex, wordIndex]), storyId: story.id,
              storyTitle: story.title, lessonNumber: story.lessonNumber ?? null,
              lessonSubOrder: story.lessonSubOrder ?? null, frameIndex, wordIndex, tier: CANONICAL_TIER, expected,
              storyWide: false, source: "scene-vocabulary" as const,
              assessmentQuestions: [],
              context: tierText(frame, "suggestedAnswer", CANONICAL_TIER) || tierText(frame, "listenScript", CANONICAL_TIER) || tierText(frame, "prompt", CANONICAL_TIER) || "",
              published: Boolean(story.published),
            })).filter(row => Boolean(row.word));
        });
      }
      return entries;
    });
}

const searchKey = (value: string) => value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
export function matchesVocabularySearch(entry: VocabularyEntry, query: string): boolean {
  return searchKey([entry.word, entry.pinyin, entry.translation, entry.storyTitle].join(" ")).includes(searchKey(query.trim()));
}

export function vocabularyEntriesToCsv(entries: VocabularyEntry[]): string {
  const cell = (value: string | number | null) => {
    const text = String(value ?? "");
    const safe = /^[\s]*[=+@-]/.test(text) || /^[\t\r\n]/.test(text) ? `'${text}` : text;
    return `"${safe.replace(/"/g, '""')}"`;
  };
  const rows = entries.map(e => {
    return [e.lessonNumber, e.lessonSubOrder, e.storyTitle, e.source === "quiz-assessment" ? "Quiz bank" : e.storyWide ? "Story-wide" : e.frameIndex + 1,
      e.word, e.pinyin, e.pos, e.translation, e.context];
  });
  return "\uFEFF" + [["Lesson", "Part", "Speaking story", "Scene", "Word", "Pinyin", "Part of speech", "Meaning", "Speaking context"], ...rows]
    .map(row => row.map(cell).join(",")).join("\r\n");
}
