import { type ChangeEvent, type ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { BiLabel, BiText } from "../components/BiLabel";
import "../components/BiLabel.css";
import "./TeacherQuizReviewPage.css";
import {
  approveQuizMaterial,
  canUseDatabase,
  generateVocabCloze,
  generateVocabDistractors,
  generateVocabSynonym,
  listCustomStories,
  replaceQuizQuestion,
  saveQuizPendingApprovals,
  updateQuizExclusions,
  updateVocabularyCloze,
  updateVocabularyDistractors,
  updateVocabularySynonym,
  validateQuizMaterial,
  type VocabGrowthWord,
  type QuizValidateResultItem,
} from "../services/database";
import {
  buildClozePatchUpdates,
  buildDistractorPatchUpdates,
  buildSynonymPatchUpdates,
  planClozeGrowth,
  planDistractorGrowth,
  planSynonymGrowth,
} from "../components/StoryRecorder";
import {
  loadCustomStories,
  storyHasTierContent,
  storyToTopic,
  type CustomStoryFrame,
  type CustomTeacherStory,
  type StoryDifficultyLevel,
} from "../utils/teacherStories";
import {
  exportQuizMarksFile,
  isExcluded,
  readQuizMarksImportFile,
  storyQuizExclusions,
  toggleExclusion,
  type QuizExclusion,
  type QuizExclusionKind,
} from "../utils/quizExclusions";
import {
  buildMaterialSnapshot,
  diffWord,
  storyMaterialSnapshot,
  withUpdatedSnapshot,
  type MaterialDiffStatus,
  type MaterialSnapshotEntry,
} from "../utils/quizMaterialDiff";
import { buildApprovedMaterial, buildApprovedMaterialFromApprovals } from "../utils/quizApprovedMaterial";
import { protectGeneratedQuizMaterial } from "../utils/quizGenerationGate";
import {
  isApproved,
  storyPendingApprovals,
  toggleApproval,
  type QuizApprovalKind,
  type QuizApprovalMark,
} from "../utils/quizPendingApprovals";
import { lessonTitle } from "../utils/lessonGroups";
import { toPinyin } from "../utils/pinyin";

/** Teacher quiz review: every piece of material the vocab quiz can build
 * questions from, per lesson and difficulty tier, with a 🗑 toggle to mark
 * bad items. Marks persist per story (custom_stories.quiz_exclusions) and
 * the quiz never builds questions from marked material. Also diffs live
 * material against the snapshot from each story's last save, so a teacher
 * revisiting a lesson can see what's 🆕 new or ✎ changed since they last
 * reviewed it, and export/import a story's marks as a JSON file.
 *
 * Reached from the teacher shell: Materials → Quiz Review. */

interface LessonReviewGroup {
  lessonNumber: number | null;
  stories: CustomTeacherStory[];
}

type ReviewIconName =
  | "accept"
  | "add"
  | "chevron"
  | "edit"
  | "export"
  | "generate"
  | "import"
  | "publish"
  | "reject"
  | "restore"
  | "save"
  | "trash"
  | "validate";

function ReviewIcon({ name, size = 18 }: { name: ReviewIconName; size?: number }) {
  const common = {
    width: size,
    height: size,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.8,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
  };
  const paths: Record<ReviewIconName, ReactNode> = {
    accept: <path d="m5 12 4 4L19 6" />,
    add: <path d="M12 5v14M5 12h14" />,
    chevron: <path d="m8 10 4 4 4-4" />,
    edit: (
      <>
        <path d="M12 20h9" />
        <path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L8 18l-4 1 1-4Z" />
      </>
    ),
    export: (
      <>
        <path d="M12 3v12" />
        <path d="m7 8 5-5 5 5" />
        <path d="M5 14v5h14v-5" />
      </>
    ),
    generate: (
      <>
        <path d="M12 3v4M12 17v4M3 12h4M17 12h4" />
        <path d="m5.6 5.6 2.8 2.8m7.2 7.2 2.8 2.8m0-12.8-2.8 2.8m-7.2 7.2-2.8 2.8" />
      </>
    ),
    import: (
      <>
        <path d="M12 15V3" />
        <path d="m7 10 5 5 5-5" />
        <path d="M5 14v5h14v-5" />
      </>
    ),
    publish: (
      <>
        <path d="m22 2-7 20-4-9-9-4Z" />
        <path d="M22 2 11 13" />
      </>
    ),
    reject: <path d="m6 6 12 12M18 6 6 18" />,
    restore: (
      <>
        <path d="M3 12a9 9 0 1 0 3-6.7" />
        <path d="M3 4v6h6" />
      </>
    ),
    save: (
      <>
        <path d="M5 3h12l2 2v16H5Z" />
        <path d="M8 3v6h8V3M8 21v-7h8v7" />
      </>
    ),
    trash: (
      <>
        <path d="M4 7h16M9 7V4h6v3M7 7l1 14h8l1-14" />
        <path d="M10 11v6M14 11v6" />
      </>
    ),
    validate: (
      <>
        <path d="M9 3h6l1 2h3v16H5V5h3Z" />
        <path d="m8 13 2.5 2.5L16 10" />
      </>
    ),
  };
  return <svg {...common}>{paths[name]}</svg>;
}

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

function diffBadge(status: MaterialDiffStatus | undefined) {
  if (!status || status === "kept") return null;
  return (
    <span className={`tqr-diff-badge tqr-diff-${status}`}>
      <span className="tqr-visually-hidden">{status === "new" ? "🆕" : "✎"}</span>
      <BiLabel zh={status === "new" ? "新增" : "已更改"} en={status === "new" ? "New" : "Changed"} />
    </span>
  );
}

/** Looks up a word/kind/poolIndex in the last Validate pass — undefined
 * means "not checked yet", not "clean". Duplicate words across scenes share
 * one lookup key (matches /quiz/validate's response shape, which doesn't
 * carry scene position), the same inertness a duplicate word already has
 * for the live quiz (collectQuizEntries keeps only the first occurrence). */
function findValidation(
  results: QuizValidateResultItem[] | undefined,
  word: string,
  kind: QuizValidateResultItem["kind"],
  poolIndex?: number,
): QuizValidateResultItem | undefined {
  return results?.find(
    (r) => r.word === word && r.kind === kind && (r.poolIndex ?? undefined) === poolIndex,
  );
}

/** Three-state status badge for one question: not checked yet (no result),
 * clean, or suspicious with the judge's reason. */
function questionStatusBadge(result: QuizValidateResultItem | undefined) {
  if (!result) return null;
  if (result.status === "clean") {
    return (
      <span className="tqr-status-badge is-clean">
        <BiLabel zh="✓ 乾淨" en="✓ Clean" />
      </span>
    );
  }
  return (
    <span className="tqr-status-badge is-suspicious">
      <BiLabel zh="⚠ 可疑" en="⚠ Suspicious" />
      <span className="tqr-status-reason">{result.reason}</span>
    </span>
  );
}

type SaveStatus = "idle" | "saving" | "saved" | "error";
type ValidateStatus = "idle" | "validating" | "error";
type ApproveStatus = "idle" | "approving" | "approved" | "error";

/** Which candidate an open inline-edit form is editing. Only one at a time
 * across the whole page — keeps the state simple and matches how a teacher
 * actually works (fix one thing, then the next). */
interface EditTarget {
  storyId: string;
  frameIndex: number;
  wordIndex: number;
  word: string;
  kind: QuizApprovalKind | "translation" | "pinyin";
  poolIndex?: number;
  translationField?: TranslationField;
  pinyinField?: PinyinField;
}

type EditDraft =
  | { kind: "translation"; translation: string }
  | { kind: "distractors"; distractors: string; correctAnswer?: string }
  | { kind: "cloze"; sentence: string; distractors: string }
  | { kind: "synonym"; synonym: string; distractors: string }
  | { kind: "pinyin"; pinyin: string };

type AddQuestionKind = "distractors" | "cloze" | "synonym";
type AddQuestionDraft =
  | { kind: "distractors"; distractors: string }
  | { kind: "cloze"; sentence: string; distractors: string }
  | { kind: "synonym"; synonym: string; distractors: string };

interface AddQuestionTarget {
  storyId: string;
  frameIndex: number;
  wordIndex: number;
  word: string;
  availableKinds: AddQuestionKind[];
}

function pendingKeyFor(storyId: string, level: StoryDifficultyLevel): string {
  return `${storyId}:${level}`;
}

type ReplaceValue =
  | string
  | string[]
  | { sentence: string; distractors: string[] }
  | { synonym: string; distractors: string[] };

const POOL_FIELD: Record<QuizApprovalKind, keyof CustomStoryFrame> = {
  distractors: "vocabularyDistractors",
  cloze: "vocabularyCloze",
  synonym: "vocabularySynonym",
};

/** Applies a replace-in-place edit to a frame's local copy, mirroring what
 * routers/stories.py's replace_quiz_question just wrote to the database —
 * so storyToTopic recomputes with the new content without waiting on a
 * refetch. Pure: returns a new frame, doesn't mutate the one passed in. */
type TranslationField = "vocabularyTranslation" | "vocabularyTranslationMedium" | "vocabularyTranslationHard";
type PinyinField = "vocabularyPinyin" | "vocabularyPinyinMedium" | "vocabularyPinyinHard";

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

function translationFieldForLevel(frame: CustomStoryFrame, level: StoryDifficultyLevel): TranslationField {
  if (level === "medium" && frame.vocabularyTranslationMedium?.trim()) return "vocabularyTranslationMedium";
  if (level === "hard" && frame.vocabularyTranslationHard?.trim()) return "vocabularyTranslationHard";
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

/** Kind of a freshly-generated candidate awaiting accept/reject. */
type GeneratedKind = "distractors" | "cloze" | "synonym";
type BuiltInQuestionKind = "pinyin" | "reverse";
type CandidateOrigin = "new" | "changed" | "removed";
type PendingCandidateValue =
  | string[]
  | { sentence: string; distractors: string[] }
  | { synonym: string; distractors: string[] };

const GENERATED_POOL_FIELD: Record<GeneratedKind, keyof CustomStoryFrame> = {
  distractors: "vocabularyDistractors",
  cloze: "vocabularyCloze",
  synonym: "vocabularySynonym",
};

interface PendingCandidate {
  frameIndex: number;
  wordIndex: number;
  word: string;
  kind: GeneratedKind;
  origin: CandidateOrigin;
  // distractors: the whole new batch to append (matches how the merge
  // endpoints below already top up a pool). cloze/synonym: one new
  // candidate (the generation endpoint only ever returns one at a time).
  value: PendingCandidateValue;
  oldValue?: PendingCandidateValue;
  poolIndex?: number;
  decision: "pending" | "accept" | "reject";
}

function normalizedGeneratedText(value: string, caseInsensitive = false): string {
  const trimmed = value.trim();
  return caseInsensitive ? trimmed.toLocaleLowerCase() : trimmed;
}

function freshGeneratedStrings(values: string[], avoid: string[], caseInsensitive = false): string[] {
  const seen = new Set(avoid.map((value) => normalizedGeneratedText(value, caseInsensitive)).filter(Boolean));
  const fresh: string[] = [];
  for (const value of values) {
    const trimmed = value.trim();
    const key = normalizedGeneratedText(trimmed, caseInsensitive);
    if (!key || seen.has(key)) continue;
    seen.add(key);
    fresh.push(trimmed);
  }
  return fresh;
}

/** One quiz entry is built per vocabulary word, using its first live
 * occurrence. Keep generation aligned with that rule and omit any word that
 * is already being regenerated as a replacement in the same update pass. */
function canonicalGrowthCandidates<
  T extends { word: string; frameIndex: number; wordIndex: number },
>(candidates: T[], blockedWords: Set<string>): T[] {
  const seenWords = new Set<string>();
  return candidates.filter((candidate) => {
    if (blockedWords.has(candidate.word) || seenWords.has(candidate.word)) return false;
    seenWords.add(candidate.word);
    return true;
  });
}

interface IndexedPendingCandidate {
  candidate: PendingCandidate;
  index: number;
}

type ReviewTopic = ReturnType<typeof storyToTopic>;
type ChangedKind = Exclude<QuizValidateResultItem["kind"], "translation">;

interface BuiltInReviewWord {
  word: string;
  translation: string;
  pinyin: string;
}

function pinyinFieldForLevel(frame: CustomStoryFrame, level: StoryDifficultyLevel): PinyinField {
  if (level === "medium" && frame.vocabularyPinyinMedium?.trim()) return "vocabularyPinyinMedium";
  if (level === "hard" && frame.vocabularyPinyinHard?.trim()) return "vocabularyPinyinHard";
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

interface ChangedCandidateTarget {
  frameIndex: number;
  wordIndex: number;
  word: string;
  kind: ChangedKind;
  poolIndex?: number;
  currentValue: PendingCandidateValue;
  growthWord: VocabGrowthWord;
}

function findLiveWordOccurrence(topic: ReviewTopic, word: string): { frameIndex: number; wordIndex: number } | null {
  for (let si = 0; si < topic.images.length; si += 1) {
    const wordIndex = (topic.vocabulary[si] || []).indexOf(word);
    if (wordIndex !== -1) return { frameIndex: si, wordIndex };
  }
  return null;
}

function changedTargetForValidation(
  topic: ReviewTopic,
  result: QuizValidateResultItem,
): ChangedCandidateTarget | null {
  if (result.status !== "suspicious") return null;
  if (result.kind === "translation") return null;
  const occurrence = findLiveWordOccurrence(topic, result.word);
  if (!occurrence) return null;
  const { frameIndex, wordIndex } = occurrence;
  const translation = topic.vocabularyTranslation?.[frameIndex]?.[wordIndex];
  if (!translation) return null;
  const context = topic.suggestedAnswers?.[frameIndex];

  if (result.kind === "distractors") {
    const currentValue = topic.vocabularyDistractors?.[frameIndex]?.[wordIndex] ?? [];
    return {
      frameIndex,
      wordIndex,
      word: result.word,
      kind: result.kind,
      currentValue,
      growthWord: { word: result.word, translation, context, avoid: currentValue },
    };
  }

  if (typeof result.poolIndex !== "number") return null;

  if (result.kind === "cloze") {
    const clozePools = topic.vocabularyCloze?.[frameIndex]?.[wordIndex] ?? [];
    const currentValue = clozePools[result.poolIndex];
    if (!currentValue) return null;
    return {
      frameIndex,
      wordIndex,
      word: result.word,
      kind: result.kind,
      poolIndex: result.poolIndex,
      currentValue,
      growthWord: {
        word: result.word,
        translation,
        context,
        avoid: clozePools.map((c) => c.sentence),
      },
    };
  }

  const synonymPools = topic.vocabularySynonym?.[frameIndex]?.[wordIndex] ?? [];
  const currentValue = synonymPools[result.poolIndex];
  if (!currentValue) return null;
  return {
    frameIndex,
    wordIndex,
    word: result.word,
    kind: result.kind,
    poolIndex: result.poolIndex,
    currentValue,
    growthWord: {
      word: result.word,
      translation,
      context,
      avoid: synonymPools.map((s) => s.synonym),
    },
  };
}

function removedCandidatesFromSnapshot(snapshot: MaterialSnapshotEntry[] | null, topic: ReviewTopic): PendingCandidate[] {
  if (!snapshot) return [];
  const currentWords = new Set<string>();
  topic.images.forEach((_, si) => {
    (topic.vocabulary[si] || []).forEach((word) => currentWords.add(word));
  });

  const pending: PendingCandidate[] = [];
  for (const entry of snapshot) {
    if (currentWords.has(entry.word)) continue;
    if (entry.distractors.length > 0) {
      pending.push({
        frameIndex: -1,
        wordIndex: -1,
        word: entry.word,
        kind: "distractors",
        origin: "removed",
        value: [...entry.distractors],
        decision: "pending",
      });
    }
    entry.cloze.forEach((value, poolIndex) => {
      pending.push({
        frameIndex: -1,
        wordIndex: -1,
        word: entry.word,
        kind: "cloze",
        origin: "removed",
        value: { sentence: value.sentence, distractors: [...value.distractors] },
        poolIndex,
        decision: "pending",
      });
    });
    entry.synonym.forEach((value, poolIndex) => {
      pending.push({
        frameIndex: -1,
        wordIndex: -1,
        word: entry.word,
        kind: "synonym",
        origin: "removed",
        value: { synonym: value.synonym, distractors: [...value.distractors] },
        poolIndex,
        decision: "pending",
      });
    });
  }
  return pending;
}

/** Appends every accepted candidate into a local copy of the story's
 * frames, mirroring what the merge PATCH endpoints do server-side — so
 * storyToTopic recomputes with the new material without waiting on a
 * refetch. Pure: returns a new story, doesn't mutate the one passed in. */
function applyAcceptedCandidatesLocally(story: CustomTeacherStory, accepted: PendingCandidate[]): CustomTeacherStory {
  const caps: Record<GeneratedKind, number> = {
    distractors: 8,
    cloze: 1,
    synonym: 1,
  };
  let frames = story.frames;
  for (const candidate of accepted) {
    if (candidate.origin !== "new") continue;
    frames = frames.map((frame, fi) => {
      if (fi !== candidate.frameIndex) return frame;
      const field = GENERATED_POOL_FIELD[candidate.kind];
      const pool: unknown[] = JSON.parse((frame[field] as string | undefined) || "[]");
      while (pool.length <= candidate.wordIndex) pool.push([]);
      if (candidate.kind === "distractors") {
        const existing = Array.isArray(pool[candidate.wordIndex]) ? (pool[candidate.wordIndex] as string[]) : [];
        pool[candidate.wordIndex] = [
          ...existing,
          ...freshGeneratedStrings(
            candidate.value as string[],
            existing,
            candidate.kind === "distractors",
          ),
        ].slice(0, caps[candidate.kind]);
      } else {
        const existing = Array.isArray(pool[candidate.wordIndex])
          ? (pool[candidate.wordIndex] as Array<{ sentence?: string; synonym?: string }>)
          : [];
        const key = candidate.kind === "cloze"
          ? (candidate.value as { sentence: string }).sentence.trim()
          : (candidate.value as { synonym: string }).synonym.trim();
        const duplicate = existing.some((item) =>
          (candidate.kind === "cloze" ? item.sentence : item.synonym)?.trim() === key,
        );
        pool[candidate.wordIndex] = duplicate || !key
          ? existing
          : [...existing, candidate.value].slice(0, caps[candidate.kind]);
      }
      return { ...frame, [field]: JSON.stringify(pool) };
    });
  }
  return { ...story, frames };
}

function isChangedCandidate(
  candidate: PendingCandidate,
): candidate is PendingCandidate & { kind: QuizApprovalKind; value: ReplaceValue } {
  return candidate.origin === "changed";
}

function applyChangedCandidatesLocally(story: CustomTeacherStory, accepted: PendingCandidate[]): CustomTeacherStory {
  let frames = story.frames;
  for (const candidate of accepted) {
    if (!isChangedCandidate(candidate)) continue;
    frames = frames.map((frame, fi) =>
      fi === candidate.frameIndex
        ? applyLocalEdit(frame, candidate.kind, candidate.wordIndex, candidate.poolIndex, candidate.value)
        : frame,
    );
  }
  return { ...story, frames };
}

function appendUniqueExclusions(exclusions: QuizExclusion[], additions: QuizExclusion[]): QuizExclusion[] {
  const next = [...exclusions];
  for (const addition of additions) {
    if (
      !next.some(
        (exclusion) =>
          exclusion.word === addition.word &&
          exclusion.kind === addition.kind &&
          exclusion.index === addition.index,
      )
    ) {
      next.push(addition);
    }
  }
  return next;
}

const PENDING_KIND_LABELS: Record<GeneratedKind, { zh: string; en: string }> = {
  distractors: { zh: "干擾選項", en: "Distractors" },
  cloze: { zh: "填空", en: "Cloze" },
  synonym: { zh: "同義詞", en: "Synonym" },
};

const PENDING_ORIGIN_LABELS: Record<CandidateOrigin, { zh: string; en: string }> = {
  new: { zh: "新增", en: "New" },
  changed: { zh: "已更改", en: "Changed" },
  removed: { zh: "已移除", en: "Removed" },
};

function pendingDecisionCopy(origin: CandidateOrigin, decision: "accept" | "reject") {
  if (decision === "accept") {
    if (origin === "changed") return { zh: "使用新版本", en: "Using new version" };
    if (origin === "removed") return { zh: "已刪除", en: "Removed" };
    return { zh: "已新增", en: "Added" };
  }
  if (origin === "changed") return { zh: "保留舊版本", en: "Kept old version" };
  if (origin === "removed") return { zh: "已還原", en: "Restored" };
  return { zh: "已捨棄", en: "Discarded" };
}

/** Formats one pending candidate value for a diff-style line, preserving the
 * existing prompt/options content while allowing old/new/removed rendering. */
function renderPendingValue(candidate: PendingCandidate, value: PendingCandidateValue) {
  if (candidate.kind === "distractors") {
    const items = value as string[];
    return (
      <>
        <BiLabel zh="新增干擾選項：" en="New distractors: " />
        {items.join("、")}
      </>
    );
  }
  if (candidate.kind === "cloze") {
    const cloze = value as { sentence: string; distractors: string[] };
    return (
      <>
        <span lang="zh-Hant">{cloze.sentence.replace(candidate.word, "＿＿＿")}</span>
        <br />
        <span className="tqr-qprompt-en">Which word fills the blank?</span>
        <br />
        <span>
          Options: {[candidate.word, ...cloze.distractors].join("、")}
        </span>
      </>
    );
  }
  const synonym = value as { synonym: string; distractors: string[] };
  return (
    <>
      <span lang="zh-Hant">
        哪一個字跟「{candidate.word}」意思一樣？
      </span>
      <br />
      <span className="tqr-qprompt-en">Which word means the same as "{candidate.word}"?</span>
      <br />
      <span>
        Options: {[synonym.synonym, ...synonym.distractors].join("、")}
      </span>
    </>
  );
}

function renderDiffLine(
  candidate: PendingCandidate,
  value: PendingCandidateValue,
  diffType: "add" | "del",
  actions: ReactNode = null,
) {
  return (
    <div className={`diff-row row-${diffType}`}>
      <span className="gutter" aria-hidden="true">
        {diffType === "add" ? "+" : "-"}
      </span>
      <div className="diff-content">
        <span className="tqr-pending-meta">
          <BiLabel zh={PENDING_KIND_LABELS[candidate.kind].zh} en={PENDING_KIND_LABELS[candidate.kind].en} />
          <span className={`diff-tag is-${candidate.origin}`}>
            {candidate.origin === "new" && <span className="tqr-visually-hidden">🆕 New</span>}
            <BiLabel zh={PENDING_ORIGIN_LABELS[candidate.origin].zh} en={PENDING_ORIGIN_LABELS[candidate.origin].en} />
          </span>
        </span>
        <span className="tqr-pending-value">{renderPendingValue(candidate, value)}</span>
      </div>
      <div className="diff-actions">{actions}</div>
    </div>
  );
}

function renderPendingDiff(candidate: PendingCandidate, actions: ReactNode = null) {
  if (candidate.origin === "changed") {
    return (
      <>
        {candidate.oldValue ? renderDiffLine(candidate, candidate.oldValue, "del") : null}
        {renderDiffLine(candidate, candidate.value, "add", actions)}
      </>
    );
  }
  if (candidate.origin === "removed") {
    return (
      <>
        {renderDiffLine(candidate, candidate.value, "del", actions)}
        <p className="row-note">
          <BiLabel
            zh="這個詞已不在此場景使用，自上次檢查後已移除。"
            en="Word no longer used in this scene — dropped since the last review."
          />
        </p>
      </>
    );
  }
  return renderDiffLine(candidate, candidate.value, "add", actions);
}

export interface QuizReviewJump {
  lessonNumber: number | null;
  /** Distinguishes repeat jumps to the same lesson — the effect keys off
   * this, not lessonNumber, so a second click still re-triggers it. */
  nonce: number;
}

function ReviewFilterBar({
  lessonGroups,
  lessonKey,
  onLessonChange,
  levels,
  level,
  onLevelChange,
  stories,
  storyFilterId,
  onStoryChange,
}: {
  lessonGroups: LessonReviewGroup[];
  lessonKey: string;
  onLessonChange: (value: string) => void;
  levels: StoryDifficultyLevel[];
  level: StoryDifficultyLevel;
  onLevelChange: (value: StoryDifficultyLevel) => void;
  stories: CustomTeacherStory[];
  storyFilterId: string;
  onStoryChange: (value: string) => void;
}) {
  return (
    <header className="tqr-header" aria-label="Quiz review controls">
      <div className="tqr-header-copy">
        <h1>
          <BiLabel zh="測驗檢查" en="Quiz Review" />
        </h1>
      </div>
      <div className="tqr-controls">
        <label>
          <BiLabel zh="課" en="Lesson" />
          <select value={lessonKey} onChange={(event) => onLessonChange(event.target.value)}>
            {lessonGroups.map((group) => (
              <option key={lessonKeyFor(group.lessonNumber)} value={lessonKeyFor(group.lessonNumber)}>
                {lessonOptionLabel(group.lessonNumber)}
              </option>
            ))}
          </select>
        </label>
        {levels.length > 1 && (
          <label>
            <BiLabel zh="難度" en="Level" />
            <select
              value={level}
              onChange={(event) => onLevelChange(event.target.value as StoryDifficultyLevel)}
            >
              {levels.map((item) => (
                <option key={item} value={item}>
                  {item === "easy" ? "簡單" : item === "medium" ? "中等" : "困難"}
                </option>
              ))}
            </select>
          </label>
        )}
        {stories.length > 1 && (
          <label>
            <BiLabel zh="故事" en="Story" />
            <select value={storyFilterId} onChange={(event) => onStoryChange(event.target.value)}>
              <option value="all">全部故事（批次檢查）</option>
              {stories.map((story) => (
                <option key={story.id} value={story.id}>{story.title}</option>
              ))}
            </select>
          </label>
        )}
      </div>
    </header>
  );
}

function ReviewActionRail({
  storyTitle,
  checkedCount,
  markedCount,
  changeCount,
  children,
}: {
  storyTitle: string;
  checkedCount: number;
  markedCount: number;
  changeCount: number;
  children: ReactNode;
}) {
  return (
    <aside className="tqr-action-rail" aria-label={`${storyTitle} review actions`}>
      <p className="tqr-rail-summary" aria-live="polite">
        {checkedCount === 0 && markedCount === 0 && changeCount === 0 ? (
          <BiLabel zh="準備檢查" en="Ready to review" />
        ) : (
          <>
            {checkedCount > 0 && <span><strong>{checkedCount}</strong> <BiLabel zh="已勾選" en="checked" /></span>}
            {markedCount > 0 && <span><strong>{markedCount}</strong> <BiLabel zh="已標記" en="marked" /></span>}
            {changeCount > 0 && <span><strong>{changeCount}</strong> <BiLabel zh="待決定" en="to decide" /></span>}
          </>
        )}
      </p>
      <div className="tqr-rail-actions">{children}</div>
    </aside>
  );
}

export default function TeacherQuizReviewPage({
  jumpToLesson,
}: {
  jumpToLesson?: QuizReviewJump | null;
} = {}) {
  const [stories, setStories] = useState<CustomTeacherStory[]>([]);
  const [lessonKey, setLessonKey] = useState<string>("");
  const [storyFilterId, setStoryFilterId] = useState<string>("all");
  const [level, setLevel] = useState<StoryDifficultyLevel>("easy");
  const [exclusionsByStory, setExclusionsByStory] = useState<Record<string, QuizExclusion[]>>({});
  const [dirtyByStory, setDirtyByStory] = useState<Record<string, boolean>>({});
  const [statusByStory, setStatusByStory] = useState<Record<string, SaveStatus>>({});
  const [importNoteByStory, setImportNoteByStory] = useState<Record<string, string>>({});
  const [validationByStory, setValidationByStory] = useState<Record<string, QuizValidateResultItem[]>>({});
  const [validateStatusByStory, setValidateStatusByStory] = useState<Record<string, ValidateStatus>>({});
  const [approveStatusByStory, setApproveStatusByStory] = useState<Record<string, ApproveStatus>>({});
  // Keyed by `${storyId}:${level}` (see pendingKeyFor) — approvals are
  // tier-specific, unlike exclusions above.
  const [pendingApprovalsByKey, setPendingApprovalsByKey] = useState<Record<string, QuizApprovalMark[]>>({});
  const [editTarget, setEditTarget] = useState<EditTarget | null>(null);
  const [editDraft, setEditDraft] = useState<EditDraft | null>(null);
  const [editStatus, setEditStatus] = useState<"idle" | "saving" | "error">("idle");
  const [addQuestionTarget, setAddQuestionTarget] = useState<AddQuestionTarget | null>(null);
  const [addQuestionDraft, setAddQuestionDraft] = useState<AddQuestionDraft | null>(null);
  const [addQuestionStatus, setAddQuestionStatus] = useState<"idle" | "saving" | "error">("idle");
  const [pendingCandidatesByStory, setPendingCandidatesByStory] = useState<Record<string, PendingCandidate[]>>({});
  const [revealedCountByStory, setRevealedCountByStory] = useState<Record<string, number>>({});
  const [generationGateNoteByStory, setGenerationGateNoteByStory] = useState<Record<string, string>>({});
  const [generateStatusByStory, setGenerateStatusByStory] = useState<
    Record<string, "idle" | "generating" | "revealing" | "applying" | "error">
  >({});
  const importInputRef = useRef<HTMLInputElement>(null);
  const importTargetRef = useRef<string | null>(null);

  useEffect(() => {
    const local = loadCustomStories();
    const apply = (list: CustomTeacherStory[]) => {
      setStories(list.filter((s) => s.published));
    };
    apply(local);
    if (canUseDatabase()) {
      listCustomStories().then((db) => apply(db as CustomTeacherStory[])).catch(() => {});
    }
  }, []);

  // Seed per-story review state for any story we haven't seen yet, without
  // clobbering marks the teacher is already mid-editing in another story's
  // section on this same page.
  useEffect(() => {
    setExclusionsByStory((prev) => {
      const next = { ...prev };
      let changed = false;
      for (const story of stories) {
        if (!(story.id in next)) {
          next[story.id] = storyQuizExclusions(story);
          changed = true;
        }
      }
      return changed ? next : prev;
    });
  }, [stories]);

  // Same seed-once pattern, but keyed by story+tier since approvals are
  // tier-specific — visiting a new tier for the first time seeds it from
  // the server; a later `stories` refresh (e.g. after Approve & Publish)
  // must not clobber approvals already toggled this session.
  useEffect(() => {
    setPendingApprovalsByKey((prev) => {
      const next = { ...prev };
      let changed = false;
      for (const story of stories) {
        const key = pendingKeyFor(story.id, level);
        if (!(key in next)) {
          next[key] = storyPendingApprovals(story, level);
          changed = true;
        }
      }
      return changed ? next : prev;
    });
  }, [stories, level]);

  const lessonGroups = useMemo(() => groupStoriesByLesson(stories), [stories]);

  useEffect(() => {
    if (lessonGroups.length === 0) return;
    setLessonKey((current) =>
      current && lessonGroups.some((g) => lessonKeyFor(g.lessonNumber) === current)
        ? current
        : lessonKeyFor(lessonGroups[0].lessonNumber),
    );
  }, [lessonGroups]);

  const currentGroup = lessonGroups.find((g) => lessonKeyFor(g.lessonNumber) === lessonKey);

  // Reset back to Easy whenever the lesson changes — a level the new
  // lesson doesn't support would otherwise leave the page looking empty.
  useEffect(() => {
    setLevel("easy");
  }, [lessonKey]);

  // Deep-link from StoryBuilderSection's post-save "Go to Quiz Review"
  // banner — jumps straight to the lesson the just-saved story belongs to,
  // instead of leaving the teacher to find it in the dropdown again. Keyed
  // on the nonce so clicking the banner twice for the same lesson still works.
  useEffect(() => {
    if (!jumpToLesson) return;
    setLessonKey(lessonKeyFor(jumpToLesson.lessonNumber));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jumpToLesson?.nonce]);

  // A validate pass is tier-specific (it checks that tier's material) — a
  // leftover result from Easy would otherwise mislabel Medium's pools after
  // switching, since both share the same word/kind/poolIndex lookup keys.
  useEffect(() => {
    setValidationByStory({});
    setEditTarget(null);
    setEditDraft(null);
  }, [level]);

  useEffect(() => {
    // Start focused on one story. Batch review remains an explicit choice,
    // preventing a teacher from accidentally generating a large lesson-wide
    // draft while they are inspecting a single story.
    setStoryFilterId(currentGroup?.stories[0]?.id ?? "all");
  }, [lessonKey, currentGroup]);

  const levels: StoryDifficultyLevel[] = useMemo(() => {
    if (!currentGroup) return ["easy"];
    const out: StoryDifficultyLevel[] = ["easy"];
    if (currentGroup.stories.some((s) => storyHasTierContent(s, "medium"))) out.push("medium");
    if (currentGroup.stories.some((s) => storyHasTierContent(s, "hard"))) out.push("hard");
    return out;
  }, [currentGroup]);

  const onToggle = (storyId: string, mark: QuizExclusion) => {
    setExclusionsByStory((prev) => ({
      ...prev,
      [storyId]: toggleExclusion(prev[storyId] ?? [], mark),
    }));
    setDirtyByStory((prev) => ({ ...prev, [storyId]: true }));
    setStatusByStory((prev) => ({ ...prev, [storyId]: "idle" }));
  };

  const onSave = async (story: CustomTeacherStory, topic: ReturnType<typeof storyToTopic>) => {
    setStatusByStory((prev) => ({ ...prev, [story.id]: "saving" }));
    try {
      const snapshotMap = withUpdatedSnapshot(story, level, buildMaterialSnapshot(topic));
      await updateQuizExclusions(story.id, exclusionsByStory[story.id] ?? [], snapshotMap);
      setDirtyByStory((prev) => ({ ...prev, [story.id]: false }));
      setStatusByStory((prev) => ({ ...prev, [story.id]: "saved" }));
      setStories((prev) =>
        prev.map((s) => (s.id === story.id ? { ...s, quizMaterialSnapshot: snapshotMap } : s)),
      );
    } catch {
      setStatusByStory((prev) => ({ ...prev, [story.id]: "error" }));
    }
  };

  const onValidate = async (story: CustomTeacherStory, topic: ReturnType<typeof storyToTopic>) => {
    setValidateStatusByStory((prev) => ({ ...prev, [story.id]: "validating" }));
    try {
      // Unfiltered on purpose: buildApprovedMaterial with no exclusions just
      // dedupes by word (first scene occurrence), keeping each pool's
      // original index so a suspicious result maps back onto exactly the
      // item rendered below. Excluded items are skipped server-side via the
      // separate exclusions list, not by removing them from this payload.
      const words = buildApprovedMaterial(topic, []);
      const exclusions = exclusionsByStory[story.id] ?? [];
      const results = await validateQuizMaterial(story.id, words, exclusions);
      setValidationByStory((prev) => ({ ...prev, [story.id]: results }));
      // A later validation failure revokes the old local selection. Without
      // this, a checkbox saved from an earlier clean pass could remain in
      // the publish payload even though the question is now suspicious.
      const approvalKey = pendingKeyFor(story.id, level);
      const currentApprovals = pendingApprovalsByKey[approvalKey] ?? [];
      const cleanApprovals = currentApprovals.filter((approval) =>
        results.some(
          (result) =>
            result.status === "clean" &&
            result.word === approval.word &&
            (result.kind === approval.kind || (approval.kind === "distractors" && result.kind === "translation")) &&
            (result.poolIndex ?? undefined) === (approval.index ?? undefined),
        ),
      );
      if (cleanApprovals.length !== currentApprovals.length) {
        setPendingApprovalsByKey((prev) => ({ ...prev, [approvalKey]: cleanApprovals }));
        saveQuizPendingApprovals(story.id, level, cleanApprovals).catch(() => {});
      }
      setValidateStatusByStory((prev) => ({ ...prev, [story.id]: "idle" }));
    } catch {
      setValidateStatusByStory((prev) => ({ ...prev, [story.id]: "error" }));
    }
  };

  /** Whether this candidate has survived a Validate pass THIS session —
   * checking it on is gated on this; unchecking is always free. */
  const canCheck = (storyId: string, word: string, kind: QuizApprovalKind, poolIndex?: number): boolean =>
    findValidation(
      validationByStory[storyId],
      word,
      kind === "distractors" ? "translation" : kind,
      poolIndex,
    )?.status === "clean";

  const onToggleApproval = async (story: CustomTeacherStory, mark: QuizApprovalMark) => {
    const key = pendingKeyFor(story.id, level);
    const current = pendingApprovalsByKey[key] ?? [];
    const alreadyChecked = isApproved(current, mark.word, mark.kind, mark.index);
    if (!alreadyChecked && !canCheck(story.id, mark.word, mark.kind, mark.index)) return;
    const next = toggleApproval(current, mark);
    setPendingApprovalsByKey((prev) => ({ ...prev, [key]: next }));
    saveQuizPendingApprovals(story.id, level, next).catch(() => {});
  };

  /** Bulk-checks every candidate that came back clean this session —
   * suspicious ones stay individually decided, the whole point of flagging
   * them in the first place. */
  const onApproveAll = async (story: CustomTeacherStory) => {
    const key = pendingKeyFor(story.id, level);
    let next = pendingApprovalsByKey[key] ?? [];
    for (const r of validationByStory[story.id] ?? []) {
      if (r.status !== "clean") continue;
      const approvalKind = r.kind === "translation" ? "distractors" : r.kind;
      if (!isApproved(next, r.word, approvalKind, r.poolIndex)) {
        next = toggleApproval(next, { word: r.word, kind: approvalKind, index: r.poolIndex });
      }
    }
    setPendingApprovalsByKey((prev) => ({ ...prev, [key]: next }));
    saveQuizPendingApprovals(story.id, level, next).catch(() => {});
  };

  const onApprove = async (story: CustomTeacherStory, topic: ReturnType<typeof storyToTopic>) => {
    setApproveStatusByStory((prev) => ({ ...prev, [story.id]: "approving" }));
    try {
      const approvals = pendingApprovalsByKey[pendingKeyFor(story.id, level)] ?? [];
      const exclusions = exclusionsByStory[story.id] ?? [];
      const material = buildApprovedMaterialFromApprovals(topic, approvals, exclusions);
      await approveQuizMaterial(story.id, level, material);
      setApproveStatusByStory((prev) => ({ ...prev, [story.id]: "approved" }));
      setStories((prev) =>
        prev.map((s) =>
          s.id === story.id
            ? { ...s, quizApprovedSnapshot: { ...s.quizApprovedSnapshot, [level]: material } }
            : s,
        ),
      );
    } catch {
      setApproveStatusByStory((prev) => ({ ...prev, [story.id]: "error" }));
    }
  };

  const onStartEdit = (
    target: EditTarget,
    current: { distractors: string[]; sentence?: string; synonym?: string; correctAnswer?: string; pinyin?: string },
  ) => {
    setEditTarget(target);
    setEditStatus("idle");
    if (target.kind === "distractors") {
      setEditDraft({ kind: "distractors", distractors: current.distractors.join(", "), correctAnswer: current.correctAnswer });
    } else if (target.kind === "cloze") {
      setEditDraft({
        kind: "cloze",
        sentence: current.sentence ?? "",
        distractors: current.distractors.join(", "),
      });
    } else if (target.kind === "pinyin") {
      setEditDraft({ kind: "pinyin", pinyin: current.pinyin ?? "" });
    } else {
      setEditDraft({
        kind: "synonym",
        synonym: current.synonym ?? "",
        distractors: current.distractors.join(", "),
      });
    }
  };

  const onStartTranslationEdit = (target: EditTarget, translation: string) => {
    setEditTarget(target);
    setEditDraft({ kind: "translation", translation });
    setEditStatus("idle");
  };

  const onCancelEdit = () => {
    setEditTarget(null);
    setEditDraft(null);
    setEditStatus("idle");
  };

  const addDraftForKind = (kind: AddQuestionKind): AddQuestionDraft =>
    kind === "distractors"
      ? { kind, distractors: "" }
      : kind === "cloze"
      ? { kind, sentence: "", distractors: "" }
      : { kind, synonym: "", distractors: "" };

  const onStartAddQuestion = (target: AddQuestionTarget) => {
    const kind = target.availableKinds[0];
    if (!kind) return;
    setAddQuestionTarget(target);
    setAddQuestionDraft(addDraftForKind(kind));
    setAddQuestionStatus("idle");
  };

  const onCancelAddQuestion = () => {
    setAddQuestionTarget(null);
    setAddQuestionDraft(null);
    setAddQuestionStatus("idle");
  };

  const onSaveAddQuestion = async () => {
    if (!addQuestionTarget || !addQuestionDraft) return;
    setAddQuestionStatus("saving");
    const { storyId, frameIndex, wordIndex, word } = addQuestionTarget;
    const distractors = addQuestionDraft.distractors
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
    if (distractors.length === 0) {
      setAddQuestionStatus("error");
      return;
    }

    let value: ReplaceValue;
    try {
      if (addQuestionDraft.kind === "distractors") {
        value = distractors;
        await updateVocabularyDistractors(storyId, [{ frameIndex, wordIndex, distractors }]);
      } else if (addQuestionDraft.kind === "cloze") {
        const sentence = addQuestionDraft.sentence.trim();
        if (!sentence || sentence.split(word).length !== 2) {
          setAddQuestionStatus("error");
          return;
        }
        const candidate = { sentence, distractors };
        value = candidate;
        await updateVocabularyCloze(storyId, [{ frameIndex, wordIndex, candidates: [candidate] }]);
      } else {
        const synonym = addQuestionDraft.synonym.trim();
        if (!synonym || synonym === word) {
          setAddQuestionStatus("error");
          return;
        }
        const candidate = { synonym, distractors };
        value = candidate;
        await updateVocabularySynonym(storyId, [{ frameIndex, wordIndex, candidates: [candidate] }]);
      }

      setStories((prev) =>
        prev.map((story) =>
          story.id !== storyId
            ? story
            : {
                ...story,
                frames: story.frames.map((frame, index) =>
                  index === frameIndex
                    ? applyLocalEdit(frame, addQuestionDraft.kind, wordIndex, 0, value)
                    : frame,
                ),
              },
        ),
      );
      setValidationByStory((prev) => ({ ...prev, [storyId]: [] }));
      setAddQuestionTarget(null);
      setAddQuestionDraft(null);
      setAddQuestionStatus("idle");
    } catch {
      setAddQuestionStatus("error");
    }
  };

  const onSaveEdit = async () => {
    if (!editTarget || !editDraft) return;
    setEditStatus("saving");
    const distractors = "distractors" in editDraft
      ? editDraft.distractors.split(",").map((d) => d.trim()).filter(Boolean)
      : [];
    const value: ReplaceValue =
      editDraft.kind === "translation"
        ? editDraft.translation.trim()
        : editDraft.kind === "pinyin"
        ? editDraft.pinyin.trim()
        : editDraft.kind === "distractors"
        ? distractors
        : editDraft.kind === "cloze"
          ? { sentence: editDraft.sentence.trim(), distractors }
          : { synonym: editDraft.synonym.trim(), distractors };

    try {
      if (editTarget.kind === "distractors" && editDraft.kind === "distractors" && editDraft.correctAnswer !== undefined) {
        await replaceQuizQuestion(editTarget.storyId, editTarget.frameIndex, editTarget.wordIndex, "translation", undefined, editDraft.correctAnswer.trim(), editTarget.translationField);
      }
      if (editTarget.kind === "translation") {
        await replaceQuizQuestion(
          editTarget.storyId,
          editTarget.frameIndex,
          editTarget.wordIndex,
          editTarget.kind,
          editTarget.poolIndex,
          value,
          editTarget.translationField,
        );
      } else if (editTarget.kind === "pinyin") {
        await replaceQuizQuestion(
          editTarget.storyId,
          editTarget.frameIndex,
          editTarget.wordIndex,
          "pinyin",
          undefined,
          value,
          undefined,
          editTarget.pinyinField,
        );
      } else {
        await replaceQuizQuestion(
          editTarget.storyId,
          editTarget.frameIndex,
          editTarget.wordIndex,
          editTarget.kind,
          editTarget.poolIndex,
          value,
        );
      }
      setStories((prev) =>
        prev.map((s) =>
          s.id === editTarget.storyId
            ? (() => {
                const updated: CustomTeacherStory = {
                ...s,
                frames: s.frames.map((frame, fi) =>
                  fi === editTarget.frameIndex
                    ? (() => {
                        const edited = applyLocalEdit(
                          frame,
                          editTarget.kind,
                          editTarget.wordIndex,
                          editTarget.poolIndex,
                          value,
                          editTarget.translationField,
                          editTarget.pinyinField,
                        );
                        return editTarget.kind === "distractors" && editDraft.kind === "distractors" && editDraft.correctAnswer !== undefined
                          ? applyLocalEdit(edited, "translation", editTarget.wordIndex, undefined, editDraft.correctAnswer.trim(), editTarget.translationField)
                          : edited;
                      })()
                    : frame,
                ),
                };
                return editTarget.kind === "translation"
                  ? invalidateApprovedWord(updated, editTarget.word)
                  : updated;
              })()
            : s,
        ),
      );
      // An edited candidate needs a fresh Validate before it can be checked
      // again — drop any stale result and un-check it if it was checked.
      setValidationByStory((prev) => ({
        ...prev,
        [editTarget.storyId]: (prev[editTarget.storyId] ?? []).filter((r) =>
          editTarget.kind === "translation" || editTarget.kind === "pinyin"
            ? r.word !== editTarget.word
            : !(r.word === editTarget.word && r.kind === editTarget.kind && (r.poolIndex ?? undefined) === editTarget.poolIndex),
        ),
      }));
      const key = pendingKeyFor(editTarget.storyId, level);
      const current = pendingApprovalsByKey[key] ?? [];
      const next = editTarget.kind === "pinyin"
        ? current
        : editTarget.kind === "translation"
        ? current.filter((approval) => approval.word !== editTarget.word)
        : isApproved(current, editTarget.word, editTarget.kind, editTarget.poolIndex)
          ? toggleApproval(current, { word: editTarget.word, kind: editTarget.kind, index: editTarget.poolIndex })
          : current;
      if (next !== current) {
        setPendingApprovalsByKey((prev) => ({ ...prev, [key]: next }));
        saveQuizPendingApprovals(editTarget.storyId, level, next).catch(() => {});
      }
      setEditTarget(null);
      setEditDraft(null);
      setEditStatus("idle");
    } catch {
      setEditStatus("error");
    }
  };

  /** Runs the same growth-planning + generation calls StoryRecorder's
   * background pool growth uses (planXGrowth -> generateVocabX), but stages
   * every result as pending instead of merging it in immediately — nothing
   * is persisted until the teacher accepts it and clicks Apply. Only tops
   * up words under each pool's cap, so an already-covered word costs
   * nothing to re-run; that's what makes this safe to call both the first
   * time (every word is under cap) and after a story edit (only new/thin
   * words still qualify). */
  const onGenerate = async (story: CustomTeacherStory, topic: ReturnType<typeof storyToTopic>) => {
    const storyId = story.id;
    setGenerationGateNoteByStory((prev) => ({ ...prev, [storyId]: "" }));
    setGenerateStatusByStory((prev) => ({ ...prev, [storyId]: "generating" }));
    try {
      const plannedDistractorCandidates = planDistractorGrowth(topic);
      const plannedClozeCandidates = planClozeGrowth(topic);
      const plannedSynonymCandidates = planSynonymGrowth(topic);
      const changedTargets = (validationByStory[storyId] ?? [])
        .map((result) => changedTargetForValidation(topic, result))
        .filter((target): target is ChangedCandidateTarget => target !== null);
      const changedDistractorTargets = changedTargets.filter((target) => target.kind === "distractors");
      const changedClozeTargets = changedTargets.filter((target) => target.kind === "cloze");
      const changedSynonymTargets = changedTargets.filter((target) => target.kind === "synonym");
      const distractorCandidates = canonicalGrowthCandidates(
        plannedDistractorCandidates,
        new Set(changedDistractorTargets.map((target) => target.word)),
      );
      const clozeCandidates = canonicalGrowthCandidates(
        plannedClozeCandidates,
        new Set(changedClozeTargets.map((target) => target.word)),
      );
      const synonymCandidates = canonicalGrowthCandidates(
        plannedSynonymCandidates,
        new Set(changedSynonymTargets.map((target) => target.word)),
      );
      const toWords = (list: Array<{ word: string; translation: string; context?: string; existing: string[] }>): VocabGrowthWord[] =>
        list.map((c) => ({ word: c.word, translation: c.translation, context: c.context, avoid: c.existing }));

      const [
        rawDistractorResults,
        rawClozeResults,
        rawSynonymResults,
        changedDistractorResults,
        changedClozeResults,
        changedSynonymResults,
      ] = await Promise.all([
        distractorCandidates.length ? generateVocabDistractors(toWords(distractorCandidates)) : Promise.resolve([]),
        clozeCandidates.length ? generateVocabCloze(toWords(clozeCandidates)) : Promise.resolve([]),
        synonymCandidates.length ? generateVocabSynonym(toWords(synonymCandidates)) : Promise.resolve([]),
        Promise.all(
          changedDistractorTargets.map(async (target) => {
            const results = await generateVocabDistractors([target.growthWord]);
            const result = results.find((r) => r.word === target.word) ?? results[0];
            return result && result.distractors.length > 0 ? { target, value: result.distractors } : null;
          }),
        ),
        Promise.all(
          changedClozeTargets.map(async (target) => {
            const results = await generateVocabCloze([target.growthWord]);
            const result = results.find((r) => r.word === target.word) ?? results[0];
            return result
              ? { target, value: { sentence: result.sentence, distractors: result.distractors } }
              : null;
          }),
        ),
        Promise.all(
          changedSynonymTargets.map(async (target) => {
            const results = await generateVocabSynonym([target.growthWord]);
            const result = results.find((r) => r.word === target.word) ?? results[0];
            return result
              ? { target, value: { synonym: result.synonym, distractors: result.distractors } }
              : null;
          }),
        ),
      ]);

      const vocabulary = topic.images.flatMap((_, frameIndex) =>
        (topic.vocabulary[frameIndex] ?? []).map((word, wordIndex) => ({
          word,
          translation: topic.vocabularyTranslation?.[frameIndex]?.[wordIndex] ?? "",
        })),
      );
      const protectedMaterial = protectGeneratedQuizMaterial(vocabulary, {
        distractors: rawDistractorResults,
        cloze: rawClozeResults,
        synonym: rawSynonymResults,
      });
      const {
        distractors: distractorResults,
        cloze: clozeResults,
        synonym: synonymResults,
      } = protectedMaterial;
      if (protectedMaterial.removedCount > 0) {
        setGenerationGateNoteByStory((prev) => ({
          ...prev,
          [storyId]: `${protectedMaterial.removedCount} duplicate or answer-leaking generated value${protectedMaterial.removedCount === 1 ? " was" : "s were"} removed before review.`,
        }));
      }

      const pending: PendingCandidate[] = [];
      for (const u of buildDistractorPatchUpdates(distractorCandidates, distractorResults)) {
        const c = distractorCandidates.find((x) => x.frameIndex === u.frameIndex && x.wordIndex === u.wordIndex)!;
        const fresh = freshGeneratedStrings(u.distractors, c.existing, true);
        if (fresh.length > 0) {
          pending.push({ frameIndex: u.frameIndex, wordIndex: u.wordIndex, word: c.word, kind: "distractors", origin: "new", value: fresh, decision: "pending" });
        }
      }
      for (const u of buildClozePatchUpdates(clozeCandidates, clozeResults)) {
        const c = clozeCandidates.find((x) => x.frameIndex === u.frameIndex && x.wordIndex === u.wordIndex)!;
        const value = u.candidates[0];
        if (value && !c.existing.some((existing) => existing.trim() === value.sentence.trim())) {
          pending.push({ frameIndex: u.frameIndex, wordIndex: u.wordIndex, word: c.word, kind: "cloze", origin: "new", value, decision: "pending" });
        }
      }
      for (const u of buildSynonymPatchUpdates(synonymCandidates, synonymResults)) {
        const c = synonymCandidates.find((x) => x.frameIndex === u.frameIndex && x.wordIndex === u.wordIndex)!;
        const value = u.candidates[0];
        if (value && !c.existing.some((existing) => existing.trim() === value.synonym.trim())) {
          pending.push({ frameIndex: u.frameIndex, wordIndex: u.wordIndex, word: c.word, kind: "synonym", origin: "new", value, decision: "pending" });
        }
      }
      changedDistractorResults.forEach((item) => {
        if (!item) return;
        const fresh = freshGeneratedStrings(item.value, item.target.growthWord.avoid, true);
        if (fresh.length === 0) return;
        pending.push({
          frameIndex: item.target.frameIndex,
          wordIndex: item.target.wordIndex,
          word: item.target.word,
          kind: "distractors",
          origin: "changed",
          value: fresh,
          oldValue: item.target.currentValue,
          decision: "pending",
        });
      });
      changedClozeResults.forEach((item) => {
        if (!item) return;
        if (item.target.growthWord.avoid.some((value) => value.trim() === item.value.sentence.trim())) return;
        pending.push({
          frameIndex: item.target.frameIndex,
          wordIndex: item.target.wordIndex,
          word: item.target.word,
          kind: "cloze",
          origin: "changed",
          value: item.value,
          oldValue: item.target.currentValue,
          poolIndex: item.target.poolIndex,
          decision: "pending",
        });
      });
      changedSynonymResults.forEach((item) => {
        if (!item) return;
        if (item.target.growthWord.avoid.some((value) => value.trim() === item.value.synonym.trim())) return;
        pending.push({
          frameIndex: item.target.frameIndex,
          wordIndex: item.target.wordIndex,
          word: item.target.word,
          kind: "synonym",
          origin: "changed",
          value: item.value,
          oldValue: item.target.currentValue,
          poolIndex: item.target.poolIndex,
          decision: "pending",
        });
      });
      pending.push(...removedCandidatesFromSnapshot(storyMaterialSnapshot(story, level), topic));

      if (pending.length === 0) {
        setGenerateStatusByStory((prev) => ({ ...prev, [storyId]: "idle" }));
        return;
      }

      setPendingCandidatesByStory((prev) => ({ ...prev, [storyId]: pending }));
      setRevealedCountByStory((prev) => ({ ...prev, [storyId]: 0 }));
      setGenerateStatusByStory((prev) => ({ ...prev, [storyId]: "revealing" }));

      pending.forEach((_, i) => {
        setTimeout(() => {
          setRevealedCountByStory((prev) => ({ ...prev, [storyId]: i + 1 }));
          if (i === pending.length - 1) {
            setGenerateStatusByStory((prev) => ({ ...prev, [storyId]: "idle" }));
          }
        }, i * 260);
      });
    } catch {
      setGenerateStatusByStory((prev) => ({ ...prev, [storyId]: "error" }));
    }
  };

  const onDecideCandidate = (storyId: string, index: number, decision: "accept" | "reject") => {
    setPendingCandidatesByStory((prev) => ({
      ...prev,
      [storyId]: (prev[storyId] ?? []).map((c, i) => (i === index ? { ...c, decision } : c)),
    }));
  };

  const onUndoDecision = (storyId: string, index: number) => {
    setPendingCandidatesByStory((prev) => ({
      ...prev,
      [storyId]: (prev[storyId] ?? []).map((c, i) => (i === index ? { ...c, decision: "pending" } : c)),
    }));
  };

  const onAcceptAllPending = (storyId: string) => {
    setPendingCandidatesByStory((prev) => ({
      ...prev,
      [storyId]: (prev[storyId] ?? []).map((c) => (c.decision === "pending" ? { ...c, decision: "accept" } : c)),
    }));
  };

  const onApplyPendingCandidates = async (story: CustomTeacherStory) => {
    const storyId = story.id;
    const pending = pendingCandidatesByStory[storyId] ?? [];
    const accepted = pending.filter((c) => c.decision === "accept");
    const acceptedNew = accepted.filter((c) => c.origin === "new");
    const acceptedChanged = accepted.filter(isChangedCandidate);
    const removedExclusionAdditions: QuizExclusion[] = accepted
      .filter((c) => c.origin === "removed")
      .map((c) => ({
        word: c.word,
        kind: c.kind as QuizExclusionKind,
        index: c.poolIndex,
      }));
    const nextExclusions =
      removedExclusionAdditions.length > 0
        ? appendUniqueExclusions(exclusionsByStory[storyId] ?? [], removedExclusionAdditions)
        : exclusionsByStory[storyId] ?? [];
    setGenerateStatusByStory((prev) => ({ ...prev, [storyId]: "applying" }));
    try {
      const distractorUpdates = acceptedNew
        .filter((c) => c.kind === "distractors")
        .map((c) => ({ frameIndex: c.frameIndex, wordIndex: c.wordIndex, distractors: c.value as string[] }));
      const clozeUpdates = acceptedNew
        .filter((c) => c.kind === "cloze")
        .map((c) => ({ frameIndex: c.frameIndex, wordIndex: c.wordIndex, candidates: [c.value as { sentence: string; distractors: string[] }] }));
      const synonymUpdates = acceptedNew
        .filter((c) => c.kind === "synonym")
        .map((c) => ({ frameIndex: c.frameIndex, wordIndex: c.wordIndex, candidates: [c.value as { synonym: string; distractors: string[] }] }));

      await Promise.all([
        Promise.all([
          distractorUpdates.length ? updateVocabularyDistractors(storyId, distractorUpdates) : Promise.resolve(),
          clozeUpdates.length ? updateVocabularyCloze(storyId, clozeUpdates) : Promise.resolve(),
          synonymUpdates.length ? updateVocabularySynonym(storyId, synonymUpdates) : Promise.resolve(),
        ]),
        Promise.all(
          acceptedChanged.map((candidate) =>
            replaceQuizQuestion(
              storyId,
              candidate.frameIndex,
              candidate.wordIndex,
              candidate.kind,
              candidate.poolIndex,
              candidate.value,
            ),
          ),
        ),
        removedExclusionAdditions.length
          ? updateQuizExclusions(storyId, nextExclusions)
          : Promise.resolve(),
      ]);

      setStories((prev) =>
        prev.map((s) =>
          s.id === storyId
            ? applyChangedCandidatesLocally(applyAcceptedCandidatesLocally(s, acceptedNew), acceptedChanged)
            : s,
        ),
      );
      if (removedExclusionAdditions.length > 0) {
        setExclusionsByStory((prev) => ({ ...prev, [storyId]: nextExclusions }));
        setDirtyByStory((prev) => ({ ...prev, [storyId]: false }));
        setStatusByStory((prev) => ({ ...prev, [storyId]: "saved" }));
      }
      setPendingCandidatesByStory((prev) => ({ ...prev, [storyId]: [] }));
      setGenerateStatusByStory((prev) => ({ ...prev, [storyId]: "idle" }));
    } catch {
      setGenerateStatusByStory((prev) => ({ ...prev, [storyId]: "error" }));
    }
  };

  const triggerImport = (storyId: string) => {
    importTargetRef.current = storyId;
    importInputRef.current?.click();
  };

  const onImportChange = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    const storyId = importTargetRef.current;
    e.target.value = "";
    if (!file || !storyId) return;
    try {
      const parsed = await readQuizMarksImportFile(file);
      setExclusionsByStory((prev) => ({ ...prev, [storyId]: parsed.exclusions }));
      setDirtyByStory((prev) => ({ ...prev, [storyId]: true }));
      setStatusByStory((prev) => ({ ...prev, [storyId]: "idle" }));
      setImportNoteByStory((prev) => ({
        ...prev,
        [storyId]:
          parsed.storyId && parsed.storyId !== storyId
            ? `⚠ File exported from a different story (${parsed.storyId})`
            : `✓ Imported ${parsed.exclusions.length} marks — Save to apply`,
      }));
    } catch (err) {
      setImportNoteByStory((prev) => ({
        ...prev,
        [storyId]: `⚠ ${err instanceof Error ? err.message : "Invalid marks file"}`,
      }));
    }
  };

  const onExport = (story: CustomTeacherStory) => {
    exportQuizMarksFile(story, exclusionsByStory[story.id] ?? []);
  };

  const trashButton = (
    storyId: string,
    word: string,
    kind: QuizExclusionKind,
    index?: number,
  ) => {
    const exclusions = exclusionsByStory[storyId] ?? [];
    const marked = isExcluded(exclusions, word, kind, index);
    return (
      <button
        type="button"
        className={`tqr-trash${marked ? " is-marked" : ""}`}
        aria-pressed={marked}
        aria-label={`${marked ? "Restore" : "Exclude"} ${kind} for ${word}`}
        onClick={() => onToggle(storyId, index === undefined ? { word, kind } : { word, kind, index })}
      >
        <ReviewIcon name={marked ? "restore" : "trash"} size={16} />
      </button>
    );
  };

  const approvalCheckbox = (storyId: string, word: string, kind: QuizApprovalKind, poolIndex?: number) => {
    const approvals = pendingApprovalsByKey[pendingKeyFor(storyId, level)] ?? [];
    const checked = isApproved(approvals, word, kind, poolIndex);
    // A prior selection must not bypass a later failed validation. This can
    // happen when a teacher re-checks an item after its AI pool changed.
    const checkable = canCheck(storyId, word, kind, poolIndex);
    // The disabled reason must match reality: a question can be blocked
    // either because Validate hasn't run yet, or because it ran and flagged
    // the question suspicious — those need different guidance, not the same
    // generic "Validate first" for both.
    const result = findValidation(
      validationByStory[storyId],
      word,
      kind === "distractors" ? "translation" : kind,
      poolIndex,
    );
    if (!result) return null;
    const disabledTitle = checkable
      ? undefined
      : result
        ? "Suspicious — fix this question before approving it"
        : "Validate this question first";
    return (
      <input
        type="checkbox"
        className="tqr-approve-checkbox"
        checked={checked}
        disabled={!checkable}
        title={disabledTitle}
        aria-label={`Approve ${kind} for ${word}`}
        onChange={() => {
          const story = stories.find((s) => s.id === storyId);
          if (story) onToggleApproval(story, { word, kind, index: poolIndex });
        }}
      />
    );
  };

  const editButton = (target: EditTarget, current: { distractors: string[]; sentence?: string; synonym?: string }) => (
    <button type="button" className="tqr-edit" onClick={() => onStartEdit(target, current)}>
      <ReviewIcon name="edit" size={15} />
      <BiLabel zh="編輯" en="Edit" />
    </button>
  );

  const editForm = () => {
    if (!editDraft) return null;
    return (
      <div className="tqr-edit-form">
        {editDraft.kind === "translation" && (
          <label>
            <BiLabel zh="正確答案" en="Correct answer" />
            <input
              type="text"
              value={editDraft.translation}
              onChange={(e) => setEditDraft({ kind: "translation", translation: e.target.value })}
            />
          </label>
        )}
        {editDraft.kind === "distractors" && editDraft.correctAnswer !== undefined && (
          <label>
            <BiLabel zh="正確答案" en="Correct answer" />
            <input type="text" value={editDraft.correctAnswer} onChange={(e) => setEditDraft({ ...editDraft, correctAnswer: e.target.value })} />
          </label>
        )}
        {editDraft.kind === "cloze" && (
          <label>
            <BiLabel zh="句子" en="Sentence" />
            <input
              type="text"
              lang="zh-Hant"
              value={editDraft.sentence}
              onChange={(e) => setEditDraft({ ...editDraft, sentence: e.target.value })}
            />
          </label>
        )}
        {editDraft.kind === "synonym" && (
          <label>
            <BiLabel zh="同義詞" en="Synonym" />
            <input
              type="text"
              lang="zh-Hant"
              value={editDraft.synonym}
              onChange={(e) => setEditDraft({ ...editDraft, synonym: e.target.value })}
            />
          </label>
        )}
        {editDraft.kind === "pinyin" && (
          <label>
            <BiLabel zh="拼音" en="Pinyin" />
            <input
              type="text"
              value={editDraft.pinyin}
              onChange={(e) => setEditDraft({ kind: "pinyin", pinyin: e.target.value })}
            />
          </label>
        )}
        {editDraft.kind !== "translation" && editDraft.kind !== "pinyin" && <label>
          <BiLabel zh="錯誤選項（逗號分隔）" en="Wrong options (comma-separated)" />
          <input
            type="text"
            value={editDraft.distractors}
            onChange={(e) => setEditDraft({ ...editDraft, distractors: e.target.value })}
          />
        </label>}
        <div className="tqr-edit-actions">
          <button type="button" className="tqr-io" onClick={onCancelEdit}>
            <BiLabel zh="取消" en="Cancel" />
          </button>
          {editStatus !== "saving" ? (
            <button type="button" className="tqr-save" onClick={onSaveEdit}>
              <BiLabel zh="儲存並重新驗證" en="Save (needs re-validation)" />
            </button>
          ) : (
            <span className="tqr-status-progress"><BiLabel zh="儲存中…" en="Saving…" /></span>
          )}
        </div>
        {editStatus === "error" && (
          <span className="tqr-status-error" role="alert">
            <BiLabel zh="儲存失敗" en="Save failed" />
          </span>
        )}
      </div>
    );
  };

  const isEditing = (target: Omit<EditTarget, "storyId" | "frameIndex" | "wordIndex">, storyId: string) =>
    editTarget?.storyId === storyId &&
    editTarget.word === target.word &&
    editTarget.kind === target.kind &&
    (editTarget.poolIndex ?? undefined) === (target.poolIndex ?? undefined);

  /** Renders one assembled question — prompt, options with the correct
   * answer highlighted, status badge, checkbox, and Edit — instead of the
   * raw pool text a teacher would otherwise have to parse themselves. The
   * first entry in `options` is always the correct answer. */
  const questionRow = (spec: {
    storyId: string;
    frameIndex: number;
    wordIndex: number;
    word: string;
    kind: QuizApprovalKind;
    poolIndex?: number;
    kindLabel: { zh: string; en: string };
    promptZh: string;
    promptEn: string;
    options: string[];
    translationField?: TranslationField;
    editValue: { distractors: string[]; sentence?: string; synonym?: string; correctAnswer?: string };
    diffStatus: MaterialDiffStatus | undefined;
  }) => {
    const result = findValidation(
      validationByStory[spec.storyId],
      spec.word,
      spec.kind === "distractors" ? "translation" : spec.kind,
      spec.poolIndex,
    );
    return (
      <div className="tqr-qrow diff-row row-ctx" key={`${spec.kind}-${spec.poolIndex ?? 0}`}>
        <span className="gutter tqr-q-select">
          {approvalCheckbox(spec.storyId, spec.word, spec.kind, spec.poolIndex)}
        </span>
        <span className="tqr-qkind">
          {diffBadge(spec.diffStatus)}
          <BiLabel zh={spec.kindLabel.zh} en={spec.kindLabel.en} />
          {spec.poolIndex !== undefined && ` #${spec.poolIndex + 1}`}
        </span>
        <div className="diff-content tqr-qbody">
          <p className="tqr-qprompt" lang="zh-Hant">
            {spec.promptZh}
            <br />
            <span className="tqr-qprompt-en">{spec.promptEn}</span>
          </p>
          <div className="tqr-qoptions">
            {spec.options.map((opt, i) => (
              <span key={i} className={`tqr-opt${i === 0 ? " is-correct" : ""}`}>
                {opt}
              </span>
            ))}
          </div>
        </div>
        <div className="tqr-q-status">
          {questionStatusBadge(result)}
        </div>
        <div className="diff-actions tqr-q-actions">
          {questionDeleteButton(spec.storyId, spec.word, spec.kind, spec.poolIndex)}
          {editButton(
            {
              storyId: spec.storyId,
              frameIndex: spec.frameIndex,
              wordIndex: spec.wordIndex,
              word: spec.word,
              kind: spec.kind,
              poolIndex: spec.poolIndex,
              translationField: spec.translationField,
            },
            spec.editValue,
          )}
        </div>
        {isEditing({ word: spec.word, kind: spec.kind, poolIndex: spec.poolIndex }, spec.storyId) && editForm()}
      </div>
    );
  };

  const addQuestionForm = () => {
    if (!addQuestionTarget || !addQuestionDraft) return null;
    return (
      <div className="tqr-add-form" aria-label="Add quiz question">
        <div className="tqr-add-form-heading">
          <ReviewIcon name="add" size={16} />
          <BiLabel zh="新增題目" en="Add question" />
        </div>
        <label>
          <BiLabel zh="題型" en="Question type" />
          <select
            value={addQuestionDraft.kind}
            onChange={(event) => setAddQuestionDraft(addDraftForKind(event.target.value as AddQuestionKind))}
          >
            {addQuestionTarget.availableKinds.map((kind) => (
              <option key={kind} value={kind}>
                {kind === "distractors" ? "翻譯 Translation" : kind === "cloze" ? "填空 Cloze" : "同義詞 Synonym"}
              </option>
            ))}
          </select>
        </label>
        {addQuestionDraft.kind === "cloze" && (
          <label>
            <BiLabel zh="句子（必須包含目標詞）" en="Sentence (must include the word)" />
            <input
              type="text"
              lang="zh-Hant"
              value={addQuestionDraft.sentence}
              onChange={(event) => setAddQuestionDraft({ ...addQuestionDraft, sentence: event.target.value })}
            />
          </label>
        )}
        {addQuestionDraft.kind === "synonym" && (
          <label>
            <BiLabel zh="同義詞" en="Synonym" />
            <input
              type="text"
              lang="zh-Hant"
              value={addQuestionDraft.synonym}
              onChange={(event) => setAddQuestionDraft({ ...addQuestionDraft, synonym: event.target.value })}
            />
          </label>
        )}
        <label>
          <BiLabel zh="錯誤選項（逗號分隔）" en="Wrong options (comma-separated)" />
          <input
            type="text"
            value={addQuestionDraft.distractors}
            onChange={(event) => setAddQuestionDraft({ ...addQuestionDraft, distractors: event.target.value })}
          />
        </label>
        <div className="tqr-edit-actions">
          <button type="button" className="tqr-io" onClick={onCancelAddQuestion}>
            <BiLabel zh="取消" en="Cancel" />
          </button>
          {addQuestionStatus !== "saving" ? (
            <button type="button" className="tqr-save" onClick={onSaveAddQuestion}>
              <ReviewIcon name="add" size={15} />
              <BiLabel zh="新增題目" en="Add question" />
            </button>
          ) : (
            <span className="tqr-status-progress"><BiLabel zh="新增中…" en="Adding…" /></span>
          )}
        </div>
        {addQuestionStatus === "error" && (
          <span className="tqr-status-error" role="alert">
            <BiLabel zh="請填寫完整題目內容與錯誤選項" en="Complete the question and add at least one wrong option" />
          </span>
        )}
      </div>
    );
  };

  const onStartPinyinEdit = (target: EditTarget, pinyin: string) => {
    setEditTarget(target);
    setEditDraft({ kind: "pinyin", pinyin });
    setEditStatus("idle");
  };

  const questionDeleteButton = (
    storyId: string,
    word: string,
    kind: QuizApprovalKind | BuiltInQuestionKind,
    index?: number,
  ) => {
    const exclusions = exclusionsByStory[storyId] ?? [];
    const exclusionKind: QuizExclusionKind = kind === "distractors" ? "distractors" : kind;
    const marked = isExcluded(exclusions, word, exclusionKind, index);
    const questionName = kind === "distractors" ? "translation" : kind;
    const exclusion = index === undefined
      ? { word, kind: exclusionKind }
      : { word, kind: exclusionKind, index };

    return (
      <button
        type="button"
        className={`tqr-trash tqr-question-delete${marked ? " is-marked" : ""}`}
        aria-pressed={marked}
        aria-label={`${marked ? "Restore" : "Delete"} ${questionName} question for ${word}`}
        title={`${marked ? "Restore" : "Delete"} this ${questionName} question`}
        onClick={() => {
          if (!marked && typeof window !== "undefined") {
            const confirmed = window.confirm(
              `Delete this ${questionName} question for ${word}? You can restore it before saving.`,
            );
            if (!confirmed) return;
          }
          onToggle(storyId, exclusion);
        }}
      >
        <ReviewIcon name={marked ? "restore" : "trash"} size={16} />
      </button>
    );
  };

  /** Renders a deterministic question preview. Built-in questions use the
   * same row actions as generated questions: teachers can edit their source
   * value or exclude/restore the question before saving. */
  const builtInQuestionRow = (spec: {
    key: string;
    storyId: string;
    frameIndex: number;
    wordIndex: number;
    word: string;
    kind: BuiltInQuestionKind;
    kindLabel: { zh: string; en: string };
    promptZh: string;
    promptEn: string;
    options: string[];
    pinyin?: string;
    pinyinField?: PinyinField;
    translation?: string;
    translationField?: TranslationField;
  }) => (
    <div className="tqr-qrow diff-row row-ctx" key={spec.key}>
      <span className="gutter tqr-q-select" aria-hidden="true" />
      <span className="tqr-qkind">
        <BiLabel zh={spec.kindLabel.zh} en={spec.kindLabel.en} />
      </span>
      <div className="diff-content tqr-qbody">
        <p className="tqr-qprompt" lang="zh-Hant">
          {spec.promptZh}
          <br />
          <span className="tqr-qprompt-en">{spec.promptEn}</span>
        </p>
        <div className="tqr-qoptions">
          {spec.options.map((opt, i) => (
            <span key={i} className={`tqr-opt${i === 0 ? " is-correct" : ""}`}>
              {i === 0 ? "✓ " : "· "}{opt}
            </span>
          ))}
        </div>
      </div>
      <div className="tqr-q-status" aria-hidden="true" />
      <div className="diff-actions tqr-q-actions">
        {questionDeleteButton(spec.storyId, spec.word, spec.kind)}
        <button
          type="button"
          className="tqr-edit"
          onClick={() => {
            if (spec.kind === "pinyin") {
              onStartPinyinEdit(
                {
                  storyId: spec.storyId,
                  frameIndex: spec.frameIndex,
                  wordIndex: spec.wordIndex,
                  word: spec.word,
                  kind: "pinyin",
                  pinyinField: spec.pinyinField,
                },
                spec.pinyin ?? "",
              );
            } else {
              onStartTranslationEdit(
                {
                  storyId: spec.storyId,
                  frameIndex: spec.frameIndex,
                  wordIndex: spec.wordIndex,
                  word: spec.word,
                  kind: "translation",
                  translationField: spec.translationField,
                },
                spec.translation ?? "",
              );
            }
          }}
        >
          <ReviewIcon name="edit" size={15} />
          <BiLabel zh="編輯" en="Edit" />
        </button>
      </div>
      {spec.kind === "pinyin" && isEditing({ word: spec.word, kind: "pinyin" }, spec.storyId) && editForm()}
    </div>
  );

  const pendingDecisionActions = (storyId: string, candidate: PendingCandidate, index: number) => {
    if (candidate.decision === "pending") {
      return (
        <div className="tqr-pending-decide">
          <button
            type="button"
            className="tqr-icon-btn accept"
            aria-label="Accept"
            title="Accept"
            onClick={() => onDecideCandidate(storyId, index, "accept")}
          >
            <ReviewIcon name="accept" size={16} />
          </button>
          <button
            type="button"
            className="tqr-icon-btn reject"
            aria-label="Reject"
            title="Reject"
            onClick={() => onDecideCandidate(storyId, index, "reject")}
          >
            <ReviewIcon name="reject" size={16} />
          </button>
        </div>
      );
    }
    return (
      <div className="tqr-pending-decided">
        <span className={`tqr-decision-tag ${candidate.decision === "accept" ? "is-accept" : "is-reject"}`}>
          {candidate.decision === "accept" ? "✓ " : "× "}
          <BiLabel
            zh={pendingDecisionCopy(candidate.origin, candidate.decision).zh}
            en={pendingDecisionCopy(candidate.origin, candidate.decision).en}
          />
        </span>
        <button type="button" className="undo-link" onClick={() => onUndoDecision(storyId, index)}>
          <BiLabel zh="復原" en="Undo" />
        </button>
      </div>
    );
  };

  const pendingCandidateRows = (storyId: string, entries: IndexedPendingCandidate[]) =>
    entries.map(({ candidate, index }) => (
      <div
        className={`tqr-pending-change is-${candidate.origin}${candidate.decision === "reject" ? " is-rejected" : ""}`}
        key={`${candidate.word}-${candidate.kind}-${index}`}
      >
        {renderPendingDiff(candidate, pendingDecisionActions(storyId, candidate, index))}
      </div>
    ));

  const changeChip = (count: number, hasRemoved = false) => (
    count > 0 ? (
      <span className={`tqr-change-chip ${hasRemoved ? "is-mix" : "is-add"}`}>
        <BiLabel zh={`${count} 項變更`} en={`${count} ${count === 1 ? "change" : "changes"}`} />
      </span>
    ) : null
  );

  return (
    <main className="teacher-quiz-review">
      <input
        type="file"
        accept="application/json"
        ref={importInputRef}
        onChange={onImportChange}
        className="tqr-file-input"
        data-testid="tqr-import-input"
      />
      <ReviewFilterBar
        lessonGroups={lessonGroups}
        lessonKey={lessonKey}
        onLessonChange={setLessonKey}
        levels={levels}
        level={level}
        onLevelChange={setLevel}
        stories={currentGroup?.stories ?? []}
        storyFilterId={storyFilterId}
        onStoryChange={setStoryFilterId}
      />

      {!currentGroup && (
        <p className="tqr-empty">
          <BiText
            zh="還沒有已發佈的故事。"
            pinyin="Hái méiyǒu yǐ fābù de gùshì."
            en="No published stories yet."
          />
        </p>
      )}

      {currentGroup &&
        currentGroup.stories.filter((story) => storyFilterId === "all" || story.id === storyFilterId).map((story) => {
          if (level !== "easy" && !storyHasTierContent(story, level)) return null;
          const topic = storyToTopic(story, level);
          const exclusions = exclusionsByStory[story.id] ?? [];
          const dirty = dirtyByStory[story.id] ?? false;
          const status = statusByStory[story.id] ?? "idle";
          const snapshot = storyMaterialSnapshot(story, level);
          const importNote = importNoteByStory[story.id];
          const validateStatus = validateStatusByStory[story.id] ?? "idle";
          const approveStatus = approveStatusByStory[story.id] ?? "idle";
          const validation = validationByStory[story.id];
          const approvals = pendingApprovalsByKey[pendingKeyFor(story.id, level)] ?? [];
          const approvedCount = approvals.length;
          const generateStatus = generateStatusByStory[story.id] ?? "idle";
          const pendingCandidates = pendingCandidatesByStory[story.id] ?? [];
          const revealedCount = revealedCountByStory[story.id] ?? 0;
          const pendingByWord = new Map<string, IndexedPendingCandidate[]>();
          pendingCandidates.forEach((candidate, index) => {
            const entries = pendingByWord.get(candidate.word) ?? [];
            entries.push({ candidate, index });
            pendingByWord.set(candidate.word, entries);
          });
          const liveWords = new Set<string>();
          topic.images.forEach((_, si) => {
            (topic.vocabulary[si] || []).forEach((word) => liveWords.add(word));
          });
          const removedPendingGroups = [...pendingByWord.entries()]
            .map(([word, entries]) => ({
              word,
              entries: entries.filter(({ candidate }) => candidate.origin === "removed"),
            }))
            .filter(({ word, entries }) => entries.length > 0 && !liveWords.has(word));
          const hasAnyMaterial = buildApprovedMaterial(topic, []).some(
            (e) => e.distractors.length || e.cloze.length || e.synonym.length,
          );
          const pendingDecidedCount = pendingCandidates.filter((c) => c.decision !== "pending").length;
          const pendingAcceptedCount = pendingCandidates.filter((c) => c.decision === "accept").length;
          const isGenerating = generateStatus === "generating" || generateStatus === "revealing" || generateStatus === "applying";
          const isValidating = validateStatus === "validating";
          const isPublishing = approveStatus === "approving";
          const isSavingMarks = status === "saving";
          const canApproveAll = (validation?.length ?? 0) > 0;
          const canApplyPending = pendingCandidates.length > 0 && pendingDecidedCount === pendingCandidates.length;
          const hasSuspiciousQuestions = validation?.some((result) => result.status === "suspicious") ?? false;
          const canGenerate = pendingCandidates.length === 0 && (!hasAnyMaterial || hasSuspiciousQuestions);
          const canValidate = pendingCandidates.length === 0 && hasAnyMaterial && !hasSuspiciousQuestions;
          const showActionRail =
            approvedCount > 0 ||
            exclusions.length > 0 ||
            dirty ||
            pendingCandidates.length > 0 ||
            canApproveAll ||
            isPublishing ||
            isSavingMarks ||
            approveStatus !== "idle" ||
            status !== "idle";
          const renderedWords = new Set<string>();
          const builtInWords = builtInReviewWords(topic);
          const builtInByWord = new Map(builtInWords.map((entry) => [entry.word, entry]));

          return (
            <section className="tqr-story" key={story.id}>
              <div className={`tqr-workspace${showActionRail ? "" : " is-single"}`}>
                <div className="tqr-review-panel">
                  <header className="tqr-story-actions">
                    <div className="tqr-toolbar-primary">
                      <h2 className="tqr-panel-story-title">{story.title}</h2>
                      {canGenerate && !isGenerating ? (
                        <button
                          type="button"
                          className="tqr-generate"
                          title="Create a new draft, or refresh only questions affected by story changes. Students cannot see a draft."
                          onClick={() => onGenerate(story, topic)}
                        >
                          <ReviewIcon name="generate" />
                          {hasAnyMaterial ? (
                            <BiLabel zh="更新題目" en="Update Questions" />
                          ) : (
                            <BiLabel zh="生成題目" en="Generate Questions" />
                          )}
                        </button>
                      ) : isGenerating ? (
                        <span className="tqr-status-progress" role="status">
                          {generateStatus === "applying" ? <BiLabel zh="套用中…" en="Applying…" /> : <BiLabel zh="生成中…" en="Generating…" />}
                        </span>
                      ) : null}
                      <div className="tqr-toolbar-status" aria-live="polite">
                        {generateStatus === "error" && (
                          <span className="tqr-status-error" role="alert">
                            <BiLabel zh="生成失敗，請稍後再試" en="Generate failed. Try again in a moment" />
                          </span>
                        )}
                        {validateStatus === "error" && (
                          <span className="tqr-status-error" role="alert">
                            <BiLabel zh="檢查失敗" en="Validate failed" />
                          </span>
                        )}
                      </div>
                      <details className="tqr-more-tools tqr-toolbar-more">
                        <summary><BiLabel zh="更多" en="More" /></summary>
                        <div className="tqr-rail-utilities">
                          {canValidate && !isValidating && (
                            <button
                              type="button"
                              className="tqr-io"
                              title="Validate the current draft for duplicate or unsafe answers before selecting questions to publish."
                              onClick={() => onValidate(story, topic)}
                            >
                              <ReviewIcon name="validate" />
                              <BiLabel zh="驗證題目" en="Validate Questions" />
                            </button>
                          )}
                          {isValidating && (
                            <span className="tqr-status-progress" role="status">
                              <BiLabel zh="驗證中…" en="Validating…" />
                            </span>
                          )}
                          <button type="button" className="tqr-io" onClick={() => onExport(story)}>
                            <ReviewIcon name="export" />
                            <BiLabel zh="匯出" en="Export" />
                          </button>
                          <button type="button" className="tqr-io" onClick={() => triggerImport(story.id)}>
                            <ReviewIcon name="import" />
                            <BiLabel zh="匯入" en="Import" />
                          </button>
                        </div>
                      </details>
                    </div>
                  </header>
                  {importNote && <p className="tqr-import-note" role="status">{importNote}</p>}
                  {generationGateNoteByStory[story.id] && (
                    <p className="tqr-import-note" role="status">
                      {generationGateNoteByStory[story.id]}
                    </p>
                  )}

                  {generateStatus === "generating" && (
                    <div className="tqr-generate-spinner" role="status">
                      <span className="tqr-spinner" aria-hidden="true" />
                      <BiLabel zh="正在生成題目…" en="Generating questions…" />
                    </div>
                  )}

                  <div className="tqr-table-head" aria-hidden="true">
                    <span />
                    <span><BiLabel zh="題型" en="Type" /></span>
                    <span><BiLabel zh="題目內容／答案" en="Question / answer" /></span>
                    <span><BiLabel zh="驗證狀態" en="Validation" /></span>
                    <span><BiLabel zh="操作" en="Actions" /></span>
                  </div>

              {topic.images.map((_, si) => {
                const words = (topic.vocabulary[si] || [])
                  .map((word, wordIndex) => ({ word, wordIndex }))
                  .filter(({ word }) => {
                    if (renderedWords.has(word)) return false;
                    renderedWords.add(word);
                    return true;
                  });
                if (words.length === 0) return null;
                return (
                  <section className="tqr-scene" key={si}>
                    <h3 className="tqr-scene-title">
                      <BiLabel zh={`部分 ${si + 1}`} en={`Scene ${si + 1}`} />
                    </h3>
                    {words.map(({ word, wordIndex: wi }) => {
                      const wordGone = isExcluded(exclusions, word, "word");
                      const pinyin = topic.vocabularyPinyin?.[si]?.[wi];
                      const pos = topic.vocabularyPos?.[si]?.[wi];
                      const translation = topic.vocabularyTranslation?.[si]?.[wi];
                      const translationField = translationFieldForLevel(story.frames[si], level);
                      const translationCheck = findValidation(validationByStory[story.id], word, "translation");
                      const distractors = topic.vocabularyDistractors?.[si]?.[wi] ?? [];
                      const cloze = (topic.vocabularyCloze?.[si]?.[wi] ?? []).slice(0, 1);
                      const synonyms = (topic.vocabularySynonym?.[si]?.[wi] ?? []).slice(0, 1);
                      const availableAddKinds: AddQuestionKind[] = [
                        ...(distractors.length === 0 ? ["distractors" as const] : []),
                        ...(cloze.length === 0 ? ["cloze" as const] : []),
                        ...(synonyms.length === 0 ? ["synonym" as const] : []),
                      ];
                      const builtIn = builtInByWord.get(word);
                      const pinyinOptions = builtIn
                        ? reviewOptions(
                            builtIn.pinyin,
                            builtInWords
                              .filter((entry) => entry.word !== word && entry.pinyin !== builtIn.pinyin)
                              .map((entry) => entry.pinyin),
                          )
                        : [];
                      const reverseOptions = builtIn
                        ? reviewOptions(
                            builtIn.word,
                            builtInWords
                              .filter(
                                (entry) =>
                                  entry.word !== word &&
                                  entry.translation.toLowerCase() !== builtIn.translation.toLowerCase(),
                              )
                              .map((entry) => entry.word),
                          )
                        : [];
                      const diff = diffWord(word, { distractors, cloze, synonym: synonyms }, snapshot);
                      const wordPending = (pendingByWord.get(word) ?? []).filter(
                        ({ candidate, index }) => candidate.origin !== "removed" && index < revealedCount,
                      );
                      return (
                        <article
                          className={`tqr-word-file${wordGone ? " is-word-gone" : ""}`}
                          key={`${word}-${wi}`}
                        >
                          <header className="tqr-word-head">
                            <span className="tqr-word-chev"><ReviewIcon name="chevron" size={15} /></span>
                            <strong lang="zh-Hant">{word}</strong>
                            {pinyin && <span className="tqr-pinyin">{pinyin}</span>}
                            {pos && <span className="tqr-pos">{pos}</span>}
                            {translation ? (
                              <span className="tqr-translation">→ {translation}</span>
                            ) : (
                              <span className="tqr-no-quiz">
                                <BiLabel zh="沒有翻譯，不會出題" en="No translation — never quizzed" />
                              </span>
                            )}
                            {translation && distractors.length === 0 && (
                              <button
                                type="button"
                                className="tqr-edit tqr-edit-answer"
                                onClick={() =>
                                  onStartTranslationEdit(
                                    {
                                      storyId: story.id,
                                      frameIndex: si,
                                      wordIndex: wi,
                                      word,
                                      kind: "translation",
                                      translationField,
                                    },
                                    translation,
                                  )
                                }
                              >
                                <BiLabel zh="編輯答案" en="Edit answer" />
                              </button>
                            )}
                            {translation && distractors.length === 0 && translationCheck && (
                              <span className="tqr-answer-check">
                                <BiLabel zh="答案檢查" en="Answer check" />
                                {questionStatusBadge(translationCheck)}
                              </span>
                            )}
                            {translation && !wordGone && availableAddKinds.length > 0 && (
                              <button
                                type="button"
                                className="tqr-add-question"
                                aria-label={`Add question for ${word}`}
                                onClick={() =>
                                  onStartAddQuestion({
                                    storyId: story.id,
                                    frameIndex: si,
                                    wordIndex: wi,
                                    word,
                                    availableKinds: availableAddKinds,
                                  })
                                }
                              >
                                <ReviewIcon name="add" size={15} />
                                <BiLabel zh="新增題目" en="Add question" />
                              </button>
                            )}
                            {translation && trashButton(story.id, word, "word")}
                            <span className="tqr-word-head-spacer" />
                            {diffBadge(diff?.status)}
                            {changeChip(wordPending.length)}
                          </header>
                          {isEditing({ word, kind: "translation" }, story.id) && editForm()}
                          {addQuestionTarget?.storyId === story.id &&
                            addQuestionTarget.frameIndex === si &&
                            addQuestionTarget.wordIndex === wi &&
                            addQuestionForm()}
                          {!wordGone && translation && (
                            <div className="tqr-pools">
                              {distractors.length > 0 &&
                                questionRow({
                                  storyId: story.id,
                                  frameIndex: si,
                                  wordIndex: wi,
                                  word,
                                  kind: "distractors",
                                  kindLabel: { zh: "翻譯", en: "Translation" },
                                  promptZh: `「${word}」是什麼意思？`,
                                  promptEn: `What does "${word}" mean?`,
                                  options: [translation, ...distractors],
                                  translationField,
                                  editValue: { distractors, correctAnswer: translation },
                                  diffStatus: diff?.distractorsStatus,
                                })}
                              {cloze.map((c, ci) =>
                                questionRow({
                                  storyId: story.id,
                                  frameIndex: si,
                                  wordIndex: wi,
                                  word,
                                  kind: "cloze",
                                  poolIndex: ci,
                                  kindLabel: { zh: "填空", en: "Cloze" },
                                  promptZh: c.sentence.replace(word, "＿＿＿"),
                                  promptEn: "Which word fills the blank?",
                                  options: [word, ...c.distractors],
                                  editValue: { sentence: c.sentence, distractors: c.distractors },
                                  diffStatus: diff?.clozeStatus[ci],
                                }),
                              )}
                              {synonyms.map((s, syi) =>
                                questionRow({
                                  storyId: story.id,
                                  frameIndex: si,
                                  wordIndex: wi,
                                  word,
                                  kind: "synonym",
                                  poolIndex: syi,
                                  kindLabel: { zh: "同義詞", en: "Synonym" },
                                  promptZh: `哪一個字跟「${word}」意思一樣？`,
                                  promptEn: `Which word means the same as "${word}"?`,
                                  options: [s.synonym, ...s.distractors],
                                  editValue: { synonym: s.synonym, distractors: s.distractors },
                                  diffStatus: diff?.synonymStatus[syi],
                                }),
                              )}
                              {pinyinOptions.length > 1 &&
                                builtInQuestionRow({
                                  key: "pinyin",
                                  storyId: story.id,
                                  frameIndex: si,
                                  wordIndex: wi,
                                  word,
                                  kind: "pinyin",
                                  kindLabel: { zh: "拼音", en: "Pinyin" },
                                  promptZh: `「${word}」的拼音是什麼？`,
                                  promptEn: `What is the pinyin for "${word}"?`,
                                  options: pinyinOptions,
                                  pinyin: builtIn?.pinyin,
                                  pinyinField: pinyinFieldForLevel(story.frames[si], level),
                                })}
                              {reverseOptions.length > 1 &&
                                builtInQuestionRow({
                                  key: "reverse",
                                  storyId: story.id,
                                  frameIndex: si,
                                  wordIndex: wi,
                                  word,
                                  kind: "reverse",
                                  kindLabel: { zh: "反向翻譯", en: "Reverse translation" },
                                  promptZh: `哪一個詞是「${builtIn?.translation ?? translation}」？`,
                                  promptEn: `Which word means "${builtIn?.translation ?? translation}"?`,
                                  options: reverseOptions,
                                  translation: builtIn?.translation ?? translation,
                                  translationField,
                                })}
                              {pendingCandidateRows(story.id, wordPending)}
                            </div>
                          )}
                        </article>
                      );
                    })}
                  </section>
                );
              })}
              {removedPendingGroups.some(({ entries }) => entries.some(({ index }) => index < revealedCount)) && (
                <section className="tqr-removed-section">
                  <h3 className="tqr-scene-title">
                    <BiLabel zh="已從場景移除" en="Removed from scene" />
                  </h3>
                  {removedPendingGroups.map(({ word, entries }) => {
                    const visibleEntries = entries.filter(({ index }) => index < revealedCount);
                    if (visibleEntries.length === 0) return null;
                    return (
                      <article className="tqr-word-file is-removed-word" key={`removed-${word}`}>
                        <header className="tqr-word-head">
                          <span className="tqr-word-chev"><ReviewIcon name="chevron" size={15} /></span>
                          <strong lang="zh-Hant">{word}</strong>
                          <span className="tqr-no-quiz">
                            <BiLabel zh="已從場景移除" en="removed from scene" />
                          </span>
                          <span className="tqr-word-head-spacer" />
                          {changeChip(visibleEntries.length, true)}
                        </header>
                        <div className="tqr-pools">{pendingCandidateRows(story.id, visibleEntries)}</div>
                      </article>
                    );
                  })}
                </section>
              )}
                </div>

                {showActionRail && <ReviewActionRail
                  storyTitle={story.title}
                  checkedCount={approvedCount}
                  markedCount={exclusions.length}
                  changeCount={pendingCandidates.length}
                >
                  <div className="tqr-rail-primary" aria-live="polite">
                    {approvedCount > 0 && !isPublishing && (
                      <button
                        type="button"
                        className="tqr-approve"
                        title="Publish the checked questions as the version students receive."
                        onClick={() => onApprove(story, topic)}
                      >
                        <ReviewIcon name="publish" size={20} />
                        <BiLabel zh="核准並發佈" en="Approve & Publish" />
                      </button>
                    )}
                    {isPublishing && (
                      <span className="tqr-status-progress" role="status">
                        <BiLabel zh="發佈中…" en="Publishing…" />
                      </span>
                    )}
                    {approveStatus === "approved" && (
                      <span className="tqr-status-ok">
                        <ReviewIcon name="accept" size={16} />
                        <BiLabel zh="已發佈" en="Published" />
                      </span>
                    )}
                    {approveStatus === "error" && (
                      <span className="tqr-status-error" role="alert">
                        <BiLabel zh="發佈失敗" en="Publish failed" />
                      </span>
                    )}
                  </div>

                  {canApproveAll && (
                    <button type="button" className="tqr-rail-button" onClick={() => onApproveAll(story)}>
                      <ReviewIcon name="accept" />
                      <BiLabel zh="核准全部乾淨題目" en="Approve all clean" />
                    </button>
                  )}

                  {dirty && !isSavingMarks && (
                    <button
                      type="button"
                      className="tqr-save tqr-rail-button"
                      onClick={() => onSave(story, topic)}
                    >
                      <ReviewIcon name="save" />
                      <BiLabel zh="儲存標記" en="Save marks" />
                    </button>
                  )}
                  {isSavingMarks && (
                    <span className="tqr-status-progress" role="status">
                      <BiLabel zh="儲存中…" en="Saving…" />
                    </span>
                  )}
                  {status === "saved" && !dirty && (
                    <span className="tqr-status-ok">
                      <ReviewIcon name="accept" size={16} />
                      <BiLabel zh="已儲存" en="Saved" />
                    </span>
                  )}
                  {status === "error" && (
                    <span className="tqr-status-error" role="alert">
                      <BiLabel zh="儲存失敗" en="Save failed" />
                    </span>
                  )}

                  {pendingCandidates.length > 0 && (
                    <div className="tqr-decision-bar">
                      <span>
                        {pendingDecidedCount === pendingCandidates.length ? (
                          <BiLabel
                            zh={`已決定全部 ${pendingCandidates.length} 項`}
                            en={`All ${pendingCandidates.length} changes decided`}
                          />
                        ) : (
                          <BiLabel
                            zh={`已決定 ${pendingDecidedCount} / ${pendingCandidates.length} 項`}
                            en={`${pendingDecidedCount} of ${pendingCandidates.length} changes decided`}
                          />
                        )}
                      </span>
                      <span className="tqr-decision-actions">
                        {pendingDecidedCount < pendingCandidates.length && (
                          <button type="button" className="tqr-io" onClick={() => onAcceptAllPending(story.id)}>
                            <BiLabel zh="全部接受" en="Accept All" />
                          </button>
                        )}
                        {canApplyPending && generateStatus !== "applying" && (
                          <button
                            type="button"
                            className="tqr-approve"
                            onClick={() => onApplyPendingCandidates(story)}
                          >
                            <BiLabel zh={`套用變更（${pendingAcceptedCount}）`} en={`Apply Changes (${pendingAcceptedCount})`} />
                          </button>
                        )}
                        {generateStatus === "applying" && (
                          <span className="tqr-status-progress" role="status">
                            <BiLabel zh="套用中…" en="Applying…" />
                          </span>
                        )}
                      </span>
                    </div>
                  )}

                </ReviewActionRail>}
              </div>
            </section>
          );
        })}
    </main>
  );
}
