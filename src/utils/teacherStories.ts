import type { Topic } from "../components/TopicSelector";
import { numericToToneMarked } from "./pinyin";
import { storyApprovedSnapshot } from "./quizApprovedMaterial";

const BACKEND_URL =
  import.meta.env.VITE_BACKEND_URL ||
  (import.meta.env.DEV ? "http://127.0.0.1:8000" : "");

/** Resolve a relative /uploads/... URL to an absolute backend URL. */
export function resolveImageUrl(url: string): string {
  if (!url) return url;
  if (url.startsWith("/uploads/")) return `${BACKEND_URL}${url}`;
  return url;
}

export interface VocabGroup {
  name: string;
  words: string[];
}

export interface CustomStoryFrame {
  imageUrl: string;
  prompt: string;
  vocabulary: string;
  vocabularyGroups?: VocabGroup[];
  // Handy, easy-to-learn-and-reuse phrases for this scene (replaces the old
  // single whole-story "grammar pattern" note), comma-joined per scene —
  // same convention as vocabulary/vocabularyTranslation below.
  phrases?: string;
  phrasesTranslation?: string;
  vocabularyPinyin?: string;
  vocabularyPos?: string;
  vocabularyTranslation?: string;
  // JSON-encoded array of arrays (one entry per word, aligned with the
  // comma-split `vocabulary` above) — distractors are inherently multi-valued
  // per word, unlike the other comma-joined single-value fields.
  vocabularyDistractors?: string;
  // JSON-encoded array of arrays (one entry per word, aligned with the
  // comma-split `vocabulary` above) — each word's entry is a list of
  // AI-generated {sentence, distractors} cloze candidates, grown the same
  // way vocabularyDistractors is.
  vocabularyCloze?: string;
  // JSON-encoded array of arrays (one entry per word) — each word's entry
  // is a list of AI-generated {synonym, distractors} candidates, grown the
  // same way vocabularyCloze is.
  vocabularySynonym?: string;
  suggestedAnswer?: string;
  listenAudioUrl?: string;
  listenAudioSource?: "teacher" | "tts";
  listenScript?: string;
  // Model-voice reference audio, one per word in this tier's own vocabulary
  // list (unlike vocabularyDistractors/Cloze/Synonym above, these
  // ARE tiered — see storyToTopic). JSON-encoded array of URLs (a null entry
  // means that word's clip couldn't be sliced) and, in parallel, an array of
  // 100-point [0,1] pitch-shape curves the scoring engine sends back to the
  // backend as a real-voice comparison target — see reference_voice.py.
  vocabularyAudioUrls?: string;
  vocabularyReferenceCurves?: string;
  sentenceReferenceCurves?: string;
  // Medium/Hard tiers of the same scene — progressively more complex text,
  // and optionally their own image. Absent means that tier hasn't been
  // authored yet.
  imageUrlMedium?: string;
  imageUrlHard?: string;
  promptMedium?: string;
  promptHard?: string;
  vocabularyMedium?: string;
  vocabularyHard?: string;
  vocabularyPinyinMedium?: string;
  vocabularyPinyinHard?: string;
  vocabularyPosMedium?: string;
  vocabularyPosHard?: string;
  vocabularyTranslationMedium?: string;
  vocabularyTranslationHard?: string;
  phrasesMedium?: string;
  phrasesHard?: string;
  phrasesTranslationMedium?: string;
  phrasesTranslationHard?: string;
  suggestedAnswerMedium?: string;
  suggestedAnswerHard?: string;
  listenAudioUrlMedium?: string;
  listenAudioUrlHard?: string;
  listenAudioSourceMedium?: "teacher" | "tts";
  listenAudioSourceHard?: "teacher" | "tts";
  listenScriptMedium?: string;
  listenScriptHard?: string;
  vocabularyAudioUrlsMedium?: string;
  vocabularyAudioUrlsHard?: string;
  vocabularyReferenceCurvesMedium?: string;
  vocabularyReferenceCurvesHard?: string;
  sentenceReferenceCurvesMedium?: string;
  sentenceReferenceCurvesHard?: string;
}

export type NarrativeMode = "story" | "describe" | "listen_retell";

export interface CustomTeacherStory {
  id: string;
  title: string;
  learningGoal: string;
  frames: CustomStoryFrame[];
  published?: boolean;
  linear?: boolean;
  lessonNumber?: number | null;
  /** Position within its lesson (1, 2, 3...) for the in-lesson sequential
   * unlock (5-1 -> 5-2 -> 5-3). Only meaningful alongside lessonNumber; a
   * lesson with any story missing this leaves the whole lesson unordered
   * (see groupTopicsByLesson). */
  lessonSubOrder?: number | null;
  narrativeMode?: NarrativeMode;
  firstFrameIsExample?: boolean;
  rubricScores?: Record<string, unknown> | null;
  /** Teacher quiz review's diff baseline, keyed by tier — see
   * utils/quizMaterialDiff.ts. Opaque here to avoid a dependency cycle
   * (quizMaterialDiff already imports StoryDifficultyLevel from this file). */
  quizMaterialSnapshot?: Record<string, unknown>;
  /** Teacher-approved AI quiz material, keyed by tier — see
   * utils/quizApprovedMaterial.ts. What storyToTopic(story, level,
   * "approved") actually serves students. */
  quizApprovedSnapshot?: Record<string, unknown>;
  /** Quiz Review's in-progress checkbox selections, keyed by tier — see
   * utils/quizPendingApprovals.ts. Not yet published; survives a reload. */
  quizPendingApprovals?: Record<string, unknown>;
}

export const CUSTOM_STORY_STORAGE_KEY = "teacherCustomStories";

export function loadCustomStories(): CustomTeacherStory[] {
  if (typeof window === "undefined") {
    return [];
  }

  try {
    const stored = window.localStorage.getItem(CUSTOM_STORY_STORAGE_KEY);
    return stored ? JSON.parse(stored) : [];
  } catch {
    return [];
  }
}

export function saveCustomStories(stories: CustomTeacherStory[]) {
  if (typeof window !== "undefined") {
    window.localStorage.setItem(CUSTOM_STORY_STORAGE_KEY, JSON.stringify(stories));
  }
}

export function loadPublishedTeacherTopics(): Topic[] {
  return loadCustomStories()
    .filter((story) => story.published)
    .map((story) => storyToTopic(story, "easy", "approved"));
}

/** A story is authored once per scene, at the Easy tier, then optionally
 * gains Medium/Hard variants of the same plot — its own text and, if the
 * teacher uploads one, its own image; a tier left blank falls back to Easy's.
 * Picking a level just changes which tier storyToTopic reads. */
export type StoryDifficultyLevel = "easy" | "medium" | "hard";

const TIER_SUFFIX: Record<StoryDifficultyLevel, ""  | "Medium" | "Hard"> = {
  easy: "",
  medium: "Medium",
  hard: "Hard",
};

type TieredField =
  | "imageUrl"
  | "prompt"
  | "vocabulary"
  | "vocabularyPinyin"
  | "vocabularyPos"
  | "vocabularyTranslation"
  | "phrases"
  | "phrasesTranslation"
  | "suggestedAnswer"
  | "listenAudioUrl"
  | "listenScript";

/** Read a frame's text for the given tier, falling back to the base (Easy)
 * field when that tier hasn't been authored yet — so a partially-filled-in
 * Medium/Hard story still shows workable content instead of blanks. */
function tierText(
  frame: CustomStoryFrame,
  base: TieredField,
  level: StoryDifficultyLevel,
): string | undefined {
  const baseValue = frame[base];
  if (level === "easy") return baseValue;
  const suffixed = frame[`${base}${TIER_SUFFIX[level]}` as keyof CustomStoryFrame] as
    | string
    | undefined;
  return suffixed && suffixed.trim() ? suffixed : baseValue;
}

/** Whether a story has any teacher-authored content for Medium/Hard beyond
 * the Easy fields — lets the student-facing level picker hide tiers that
 * would just silently fall back to Easy text. */
export function storyHasTierContent(
  story: CustomTeacherStory,
  level: "medium" | "hard",
): boolean {
  const suffix = TIER_SUFFIX[level];
  const fields: TieredField[] = [
    "imageUrl",
    "prompt",
    "vocabulary",
    "vocabularyPinyin",
    "vocabularyPos",
    "vocabularyTranslation",
    "phrases",
    "phrasesTranslation",
    "suggestedAnswer",
    "listenAudioUrl",
    "listenScript",
  ];
  return story.frames.some((frame) =>
    fields.some((base) => {
      const value = frame[`${base}${suffix}` as keyof CustomStoryFrame] as string | undefined;
      return Boolean(value && value.trim());
    }),
  );
}

export function storyToTopic(
  story: CustomTeacherStory,
  difficultyLevel: StoryDifficultyLevel = "easy",
  // "live" (default): the AI pools reflect whatever exists right now —
  // what TeacherQuizReviewPage needs to show a teacher for review. "approved":
  // the AI pools come only from quiz_approved_snapshot — what a student
  // must be served, so an in-progress edit or a background pool-growth call
  // (StoryRecorder's growVocabularyDistractorPool and friends) never reaches
  // a student ahead of a teacher's explicit Approve & Publish.
  source: "live" | "approved" = "live",
): Topic {
  const approvedSnapshotEntries =
    source === "approved" ? storyApprovedSnapshot(story, difficultyLevel) : null;
  // Null (not an empty Map) when nothing has ever been approved for this
  // tier — distinct from an approved-but-empty snapshot, which should still
  // serve empty AI pools rather than falling through to live material.
  // First occurrence wins on a duplicate word (built with a plain loop, not
  // `new Map(entries)`, which would let a later scene's entry silently
  // overwrite an earlier one) — matching collectQuizEntries' own dedup.
  const approvedByWord = approvedSnapshotEntries
    ? approvedSnapshotEntries.reduce((map, e) => {
        if (!map.has(e.word)) map.set(e.word, e);
        return map;
      }, new Map<string, (typeof approvedSnapshotEntries)[number]>())
    : null;
  const vocabulary = story.frames.reduce<Record<number, string[]>>(
    (allWords, frame, index) => ({
      ...allWords,
      [index]: (tierText(frame, "vocabulary", difficultyLevel) || "")
        .split(",")
        .map((word) => word.trim())
        .filter(Boolean),
    }),
    {},
  );

  const vocabularyGroups: Record<number, import("../components/TopicSelector").VocabGroup[]> = {};
  const phrases: Record<number, string[]> = {};
  const phrasesTranslation: Record<number, string[]> = {};
  const vocabularyPinyin: Record<number, string[]> = {};
  const vocabularyPos: Record<number, string[]> = {};
  const vocabularyTranslation: Record<number, string[]> = {};
  const vocabularyDistractors: Record<number, string[][]> = {};
  const vocabularyCloze: Record<number, Array<{ sentence: string; distractors: string[] }[]>> = {};
  const vocabularySynonym: Record<number, Array<{ synonym: string; distractors: string[] }[]>> = {};
  const suggestedAnswers: Record<number, string> = {};
  const listenAudioUrls: Record<number, string> = {};
  const listenAudioSources: Record<number, "teacher" | "tts"> = {};
  const listenScripts: Record<number, string> = {};
  const vocabularyAudioUrls: Record<number, (string | null)[]> = {};
  const vocabularyReferenceCurves: Record<number, number[][]> = {};
  const sentenceReferenceCurves: Record<number, Record<string, number[]>> = {};
  story.frames.forEach((frame, index) => {
    if (frame.vocabularyGroups && frame.vocabularyGroups.length > 0) {
      vocabularyGroups[index] = frame.vocabularyGroups;
    }
    const framePhrases = tierText(frame, "phrases", difficultyLevel);
    if (framePhrases && framePhrases.trim()) {
      phrases[index] = framePhrases
        .split(",")
        .map((p) => p.trim())
        .filter(Boolean);
    }
    const framePhrasesTranslation = tierText(frame, "phrasesTranslation", difficultyLevel);
    if (framePhrasesTranslation && framePhrasesTranslation.trim()) {
      phrasesTranslation[index] = framePhrasesTranslation
        .split(",")
        .map((t) => t.trim());
    }
    const frameVocabularyPinyin = tierText(frame, "vocabularyPinyin", difficultyLevel);
    if (frameVocabularyPinyin && frameVocabularyPinyin.trim()) {
      vocabularyPinyin[index] = frameVocabularyPinyin
        .split(",")
        .map((p) => numericToToneMarked(p.trim()));
    }
    const frameVocabularyPos = tierText(frame, "vocabularyPos", difficultyLevel);
    if (frameVocabularyPos && frameVocabularyPos.trim()) {
      vocabularyPos[index] = frameVocabularyPos
        .split(",")
        .map((p) => p.trim());
    }
    const frameVocabularyTranslation = tierText(frame, "vocabularyTranslation", difficultyLevel);
    if (frameVocabularyTranslation && frameVocabularyTranslation.trim()) {
      vocabularyTranslation[index] = frameVocabularyTranslation
        .split(",")
        .map((t) => t.trim());
    }
    // The per-word AI arrays below (distractors/cloze/synonym)
    // exist only for the Easy word list — they're index-aligned to
    // frame.vocabulary. When this tier authored its OWN vocabulary, that
    // alignment is meaningless: word[i] would inherit a different word's
    // distractors and, worse, its synonym "correct" answer (the quiz audit
    // caught 今天 being keyed to 名字 this way). Only attach them when this
    // tier is actually showing the Easy word list.
    const tierUsesEasyVocabulary =
      difficultyLevel === "easy" ||
      !(frame[`vocabulary${TIER_SUFFIX[difficultyLevel]}` as keyof CustomStoryFrame] as
        | string
        | undefined)?.trim();
    if (source === "live") {
      // vocabularyDistractors isn't tiered — it's regenerated per word by a
      // dedicated AI endpoint rather than authored text, and isn't currently
      // persisted by the backend at all (a separate, pre-existing gap).
      if (tierUsesEasyVocabulary && frame.vocabularyDistractors && frame.vocabularyDistractors.trim()) {
        try {
          const parsed = JSON.parse(frame.vocabularyDistractors);
          if (Array.isArray(parsed)) {
            vocabularyDistractors[index] = parsed.map((row) =>
              Array.isArray(row) ? row.filter((d): d is string => typeof d === "string") : [],
            );
          }
        } catch {
          // Malformed/stale data — treat as absent rather than breaking the quiz.
        }
      }
      // Same "not tiered, AI-grown rather than authored" story as
      // vocabularyDistractors above.
      if (tierUsesEasyVocabulary && frame.vocabularyCloze && frame.vocabularyCloze.trim()) {
        try {
          const parsed = JSON.parse(frame.vocabularyCloze);
          if (Array.isArray(parsed)) {
            vocabularyCloze[index] = parsed.map((row) =>
              Array.isArray(row)
                ? row.filter(
                    (c): c is { sentence: string; distractors: string[] } =>
                      Boolean(c) && typeof c.sentence === "string" && Array.isArray(c.distractors),
                  )
                : [],
            );
          }
        } catch {
          // Malformed/stale data — treat as absent rather than breaking the quiz.
        }
      }
      // Same "not tiered, AI-grown rather than authored" story as
      // vocabularyCloze above.
      if (tierUsesEasyVocabulary && frame.vocabularySynonym && frame.vocabularySynonym.trim()) {
        try {
          const parsed = JSON.parse(frame.vocabularySynonym);
          if (Array.isArray(parsed)) {
            vocabularySynonym[index] = parsed.map((row) =>
              Array.isArray(row)
                ? row.filter(
                    (c): c is { synonym: string; distractors: string[] } =>
                      Boolean(c) && typeof c.synonym === "string" && Array.isArray(c.distractors),
                  )
                : [],
            );
          }
        } catch {
          // Malformed/stale data — treat as absent rather than breaking the quiz.
        }
      }
    } else if (tierUsesEasyVocabulary && approvedByWord) {
      // Serving mode: every AI pool comes from the teacher-approved
      // snapshot, looked up per word — never from whatever the live fields
      // currently hold. A word with no approved entry (never reviewed, or
      // added to the story since the last approval) simply gets no AI
      // pools, same as a story that's never had any generated at all.
      const words = vocabulary[index] || [];
      vocabularyDistractors[index] = words.map((word) => approvedByWord.get(word)?.distractors ?? []);
      vocabularyCloze[index] = words.map((word) => approvedByWord.get(word)?.cloze ?? []);
      vocabularySynonym[index] = words.map((word) => approvedByWord.get(word)?.synonym ?? []);
    }
    const frameSuggestedAnswer = tierText(frame, "suggestedAnswer", difficultyLevel);
    const suffix = TIER_SUFFIX[difficultyLevel];
    if (frameSuggestedAnswer && frameSuggestedAnswer.trim()) {
      suggestedAnswers[index] = frameSuggestedAnswer.trim();
    }
    const frameListenAudioUrl = tierText(frame, "listenAudioUrl", difficultyLevel);
    if (frameListenAudioUrl && frameListenAudioUrl.trim()) {
      listenAudioUrls[index] = resolveImageUrl(frameListenAudioUrl.trim());
    }
    const frameListenAudioSource = frame[
      `listenAudioSource${suffix}` as keyof CustomStoryFrame
    ] as "teacher" | "tts" | undefined;
    if (frameListenAudioSource === "teacher" || frameListenAudioSource === "tts") {
      listenAudioSources[index] = frameListenAudioSource;
    }
    const frameListenScript = tierText(frame, "listenScript", difficultyLevel);
    if (frameListenScript && frameListenScript.trim()) {
      listenScripts[index] = frameListenScript.trim();
    }
    // No Easy fallback here (unlike tierText's fields above): a Medium/Hard
    // scene has its own word list at different indices, so Easy's audio/
    // curve pool would misalign silently rather than just being absent.
    const frameVocabularyAudioUrls = frame[`vocabularyAudioUrls${suffix}` as keyof CustomStoryFrame] as
      | string
      | undefined;
    if (frameVocabularyAudioUrls && frameVocabularyAudioUrls.trim()) {
      try {
        const parsed = JSON.parse(frameVocabularyAudioUrls);
        if (Array.isArray(parsed)) {
          vocabularyAudioUrls[index] = parsed.map((url) =>
            typeof url === "string" && url ? resolveImageUrl(url) : null,
          );
        }
      } catch {
        // Malformed/stale data — treat as absent.
      }
    }
    const frameVocabularyReferenceCurves = frame[
      `vocabularyReferenceCurves${suffix}` as keyof CustomStoryFrame
    ] as string | undefined;
    if (frameVocabularyReferenceCurves && frameVocabularyReferenceCurves.trim()) {
      try {
        const parsed = JSON.parse(frameVocabularyReferenceCurves);
        if (Array.isArray(parsed)) {
          vocabularyReferenceCurves[index] = parsed.map((curve) =>
            Array.isArray(curve) ? curve.filter((v): v is number => typeof v === "number") : [],
          );
        }
      } catch {
        // Malformed/stale data — treat as absent.
      }
    }
    const frameSentenceReferenceCurves = frame[
      `sentenceReferenceCurves${suffix}` as keyof CustomStoryFrame
    ] as string | undefined;
    if (frameSentenceReferenceCurves && frameSentenceReferenceCurves.trim()) {
      try {
        const parsed = JSON.parse(frameSentenceReferenceCurves);
        if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
          const safeCurves: Record<string, number[]> = {};
          Object.entries(parsed).forEach(([token, curve]) => {
            if (Array.isArray(curve)) {
              const numbers = curve.filter((v): v is number => typeof v === "number");
              if (numbers.length > 0) safeCurves[token] = numbers;
            }
          });
          if (Object.keys(safeCurves).length > 0) {
            sentenceReferenceCurves[index] = safeCurves;
          }
        }
      } catch {
        // Malformed/stale data — treat as absent.
      }
    }
  });

  // Easy keeps the story's original id (no behavior change for existing
  // single-tier stories); Medium/Hard get their own id so vocab-quiz
  // completion, scene recordings, and submissions track independently per
  // tier instead of colliding with Easy's.
  const topicId =
    difficultyLevel === "easy"
      ? `teacher-${story.id}`
      : `teacher-${story.id}-${difficultyLevel}`;

  return {
    id: topicId,
    name: story.title,
    description: story.learningGoal,
    skillFocus: "Teacher published activity",
    images: story.frames.map((frame) =>
      resolveImageUrl(tierText(frame, "imageUrl", difficultyLevel) || ""),
    ),
    prompts: story.frames.map((frame) => tierText(frame, "prompt", difficultyLevel) || ""),
    vocabulary,
    ...(Object.keys(vocabularyGroups).length > 0 ? { vocabularyGroups } : {}),
    ...(Object.keys(phrases).length > 0 ? { phrases } : {}),
    ...(Object.keys(phrasesTranslation).length > 0 ? { phrasesTranslation } : {}),
    ...(Object.keys(vocabularyPinyin).length > 0 ? { vocabularyPinyin } : {}),
    ...(Object.keys(vocabularyPos).length > 0 ? { vocabularyPos } : {}),
    ...(Object.keys(vocabularyTranslation).length > 0 ? { vocabularyTranslation } : {}),
    ...(Object.keys(vocabularyDistractors).length > 0 ? { vocabularyDistractors } : {}),
    ...(Object.keys(vocabularyCloze).length > 0 ? { vocabularyCloze } : {}),
    ...(Object.keys(vocabularySynonym).length > 0 ? { vocabularySynonym } : {}),
    ...(Object.keys(suggestedAnswers).length > 0 ? { suggestedAnswers } : {}),
    ...(Object.keys(listenAudioUrls).length > 0 ? { listenAudioUrls } : {}),
    ...(Object.keys(listenAudioSources).length > 0 ? { listenAudioSources } : {}),
    ...(Object.keys(listenScripts).length > 0 ? { listenScripts } : {}),
    ...(Object.keys(vocabularyAudioUrls).length > 0 ? { vocabularyAudioUrls } : {}),
    ...(Object.keys(vocabularyReferenceCurves).length > 0 ? { vocabularyReferenceCurves } : {}),
    ...(Object.keys(sentenceReferenceCurves).length > 0 ? { sentenceReferenceCurves } : {}),
    ...(story.linear ? { linear: true } : {}),
    ...(story.lessonNumber != null ? { lessonNumber: story.lessonNumber } : {}),
    ...(story.lessonSubOrder != null ? { lessonSubOrder: story.lessonSubOrder } : {}),
    narrativeMode: story.narrativeMode ?? "story",
    ...(story.firstFrameIsExample ? { firstFrameIsExample: true } : {}),
    difficultyLevel,
    sourceStory: story,
  };
}
