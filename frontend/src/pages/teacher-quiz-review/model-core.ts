// @ts-nocheck
import { lessonTitle } from "../../utils/lessonGroups";
import { toPinyin } from "../../utils/pinyin";
import { POOL_FIELD } from "./constants";

function lessonKeyFor(lessonNumber: number | null): string {
  return lessonNumber === null ? "other" : String(lessonNumber);
}

function lessonOptionLabel(lessonNumber: number | null): string {
  if (lessonNumber === null) return "其他";
  return `第${lessonNumber}課 ${lessonTitle(lessonNumber).zh}`;
}

/** Groups published stories into lesson rows: numbered lessons ascending,
 * then one 其他 row for stories without a lesson (omitted when empty).
 * Mirrors lessonGroups.ts's groupTopicsByLesson, but over raw stories
 * (this page reviews every tier of a story, not one picked Topic). */
function groupStoriesByLesson(stories: CustomTeacherStory[]): LessonReviewGroup[] {
  const numbered = new Map<number, CustomTeacherStory[]>();
  const unassigned: CustomTeacherStory[] = [];
  for (const story of stories) {
    if (story.lessonNumber != null) {
      const list = numbered.get(story.lessonNumber) ?? [];
      list.push(story);
      numbered.set(story.lessonNumber, list);
    } else {
      unassigned.push(story);
    }
  }
  const groups: LessonReviewGroup[] = [...numbered.entries()]
    .sort(([a], [b]) => a - b)
    .map(([lessonNumber, groupStories]) => ({ lessonNumber, stories: groupStories }));
  if (unassigned.length > 0) {
    groups.push({ lessonNumber: null, stories: unassigned });
  }
  return groups;
}

function pendingKeyFor(storyId: string, level: StoryDifficultyLevel): string {
  return `${storyId}:${level}`;
}

type ReplaceValue =
  | string
  | string[]
  | { sentence: string; distractors: string[] }
  | { synonym: string; distractors: string[] };

/** Applies a replace-in-place edit to a frame's local copy, mirroring what
 * routers/stories.py's replace_quiz_question just wrote to the database —
 * so storyToTopic recomputes with the new content without waiting on a
 * refetch. Pure: returns a new frame, doesn't mutate the one passed in. */
type TranslationField = "vocabularyTranslation";
type PinyinField = "vocabularyPinyin";

function applyLocalEdit(
  frame: CustomStoryFrame,
  kind: QuizApprovalKind | "translation" | "pinyin",
  wordIndex: number,
  poolIndex: number | undefined,
  value: ReplaceValue,
  translationField?: TranslationField,
  pinyinField?: PinyinField,
): CustomStoryFrame {
  if (kind === "translation") {
    const field = translationField ?? "vocabularyTranslation";
    const translations = String(frame[field] ?? "").split(",").map((item) => item.trim());
    while (translations.length <= wordIndex) translations.push("");
    translations[wordIndex] = value as string;
    return { ...frame, [field]: translations.join(", ") };
  }
  if (kind === "pinyin") {
    const field = pinyinField ?? "vocabularyPinyin";
    const pinyins = String(frame[field] ?? "").split(",").map((item) => item.trim());
    while (pinyins.length <= wordIndex) pinyins.push("");
    pinyins[wordIndex] = value as string;
    return { ...frame, [field]: pinyins.join(", ") };
  }
  const field = POOL_FIELD[kind];
  const pool: unknown[] = JSON.parse((frame[field] as string | undefined) || "[]");
  while (pool.length <= wordIndex) pool.push([]);
  if (kind === "distractors") {
    pool[wordIndex] = value;
  } else {
    const candidates = Array.isArray(pool[wordIndex]) ? [...(pool[wordIndex] as unknown[])] : [];
    candidates[poolIndex ?? 0] = value;
    pool[wordIndex] = candidates;
  }
  return { ...frame, [field]: JSON.stringify(pool) };
}

function translationFieldForLevel(_frame: CustomStoryFrame, _level: StoryDifficultyLevel): TranslationField {
  return "vocabularyTranslation";
}

function invalidateApprovedWord(story: CustomTeacherStory, word: string): CustomTeacherStory {
  if (!story.quizApprovedSnapshot || typeof story.quizApprovedSnapshot !== "object") return story;
  const snapshot = Object.fromEntries(
    Object.entries(story.quizApprovedSnapshot).map(([level, entries]) => [
      level,
      Array.isArray(entries)
        ? entries.filter((entry) => !(entry && typeof entry === "object" && (entry as { word?: unknown }).word === word))
        : entries,
    ]),
  );
  return { ...story, quizApprovedSnapshot: snapshot };
}

type ReviewTopic = ReturnType<typeof storyToTopic>;

interface BuiltInReviewWord {
  word: string;
  translation: string;
  pinyin: string;
}

function pinyinFieldForLevel(_frame: CustomStoryFrame, _level: StoryDifficultyLevel): PinyinField {
  return "vocabularyPinyin";
}

/** The two non-AI question types shown in Quiz Review are built from the same
 * deterministic source as the student quiz: pinyin and reverse translation.
 * Keep one first-seen row per word so duplicate scene entries do not create
 * duplicate previews. */
function builtInReviewWords(topic: ReviewTopic): BuiltInReviewWord[] {
  const seen = new Set<string>();
  const words: BuiltInReviewWord[] = [];
  topic.images.forEach((_, si) => {
    (topic.vocabulary[si] || []).forEach((word, wi) => {
      if (seen.has(word)) return;
      const translation = topic.vocabularyTranslation?.[si]?.[wi]?.trim();
      if (!translation) return;
      seen.add(word);
      words.push({
        word,
        translation,
        pinyin: topic.vocabularyPinyin?.[si]?.[wi]?.trim() || toPinyin(word),
      });
    });
  });
  return words;
}

function reviewOptions(correct: string, alternatives: string[]): string[] {
  return Array.from(new Set([correct, ...alternatives.filter(Boolean)])).slice(0, 4);
}

/** Finds a word's current live position in the story so the CSV/JSON bulk
 * upload can attach parsed pools to the right frame/word without the
 * teacher having to specify scene/word indices themselves. */
function findLiveWordOccurrence(topic: ReviewTopic, word: string): { frameIndex: number; wordIndex: number } | null {
  for (let si = 0; si < topic.images.length; si += 1) {
    const wordIndex = (topic.vocabulary[si] || []).indexOf(word);
    if (wordIndex !== -1) return { frameIndex: si, wordIndex };
  }
  return null;
}

export { lessonKeyFor, lessonOptionLabel, groupStoriesByLesson, pendingKeyFor, applyLocalEdit, translationFieldForLevel, invalidateApprovedWord, pinyinFieldForLevel, builtInReviewWords, reviewOptions, findLiveWordOccurrence };
