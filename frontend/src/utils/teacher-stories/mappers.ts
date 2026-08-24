import type { Topic } from "../../components/TopicSelector";
import { numericToToneMarked } from "../pinyin";
import { storyApprovedSnapshot } from "../quizApprovedMaterial";
import { resolveImageUrl, splitCsvField, parseJsonArray, tierText, TIER_SUFFIX } from "./helpers";
import type { CustomStoryFrame, CustomTeacherStory, StoryDifficultyLevel } from "./types";

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
  // Quiz identity is based on the Easy/base vocabulary even when the
  // displayed story uses a tier-specific word list. This keeps the same
  // concept connected across levels and prevents Medium/Hard arrays from
  // inheriting AI material by stale word index.
  const quizApprovedSnapshotEntries =
    source === "approved" ? storyApprovedSnapshot(story, "easy") : null;
  const quizApprovedByWord = quizApprovedSnapshotEntries
    ? quizApprovedSnapshotEntries.reduce((map, e) => {
        if (!map.has(e.word)) map.set(e.word, e);
        return map;
      }, new Map<string, (typeof quizApprovedSnapshotEntries)[number]>())
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

  const vocabularyGroups: Record<number, import("../../components/TopicSelector").VocabGroup[]> = {};
  const phrases: Record<number, string[]> = {};
  const phrasesTranslation: Record<number, string[]> = {};
  const vocabularyPinyin: Record<number, string[]> = {};
  const vocabularyPos: Record<number, string[]> = {};
  const vocabularyTranslation: Record<number, string[]> = {};
  const vocabularyDistractors: Record<number, string[][]> = {};
  const vocabularyCloze: Record<number, Array<{ sentence: string; distractors: string[] }[]>> = {};
  const vocabularySynonym: Record<number, Array<{ synonym: string; distractors: string[] }[]>> = {};
  const suggestedAnswers: Record<number, string> = {};
  const quizVocabulary: Record<number, string[]> = {};
  const quizVocabularyPinyin: Record<number, string[]> = {};
  const quizVocabularyPos: Record<number, string[]> = {};
  const quizVocabularyTranslation: Record<number, string[]> = {};
  const quizVocabularyDistractors: Record<number, string[][]> = {};
  const quizVocabularyCloze: Record<number, Array<{ sentence: string; distractors: string[] }[]>> = {};
  const quizVocabularySynonym: Record<number, Array<{ synonym: string; distractors: string[] }[]>> = {};
  const quizSuggestedAnswers: Record<number, string> = {};
  const listenAudioUrls: Record<number, string> = {};
  const listenAudioSources: Record<number, "teacher" | "tts"> = {};
  const listenScripts: Record<number, string> = {};
  const vocabularyAudioUrls: Record<number, (string | null)[]> = {};
  const vocabularyReferenceCurves: Record<number, number[][]> = {};
  const sentenceReferenceCurves: Record<number, Record<string, number[]>> = {};
  story.frames.forEach((frame, index) => {
    const baseWords = splitCsvField(frame.vocabulary);
    quizVocabulary[index] = baseWords;
    const basePinyin = splitCsvField(frame.vocabularyPinyin).map((p) => numericToToneMarked(p));
    const basePos = splitCsvField(frame.vocabularyPos);
    const baseTranslations = splitCsvField(frame.vocabularyTranslation);
    if (basePinyin.length > 0) quizVocabularyPinyin[index] = basePinyin;
    if (basePos.length > 0) quizVocabularyPos[index] = basePos;
    const approvedTranslations = baseWords.map((word, wordIndex) =>
      (source === "approved" ? quizApprovedByWord?.get(word)?.translation?.trim() : undefined) ||
      baseTranslations[wordIndex] ||
      "",
    );
    if (approvedTranslations.some(Boolean)) {
      quizVocabularyTranslation[index] = approvedTranslations;
    }
    const baseSuggestedAnswer = frame.suggestedAnswer?.trim();
    if (baseSuggestedAnswer) quizSuggestedAnswers[index] = baseSuggestedAnswer;

    if (source === "approved") {
      quizVocabularyDistractors[index] = baseWords.map(
        (word) => quizApprovedByWord?.get(word)?.distractors ?? [],
      );
      quizVocabularyCloze[index] = baseWords.map(
        (word) => quizApprovedByWord?.get(word)?.cloze ?? [],
      );
      quizVocabularySynonym[index] = baseWords.map(
        (word) => quizApprovedByWord?.get(word)?.synonym ?? [],
      );
    } else {
      const rawDistractors = parseJsonArray(frame.vocabularyDistractors);
      if (rawDistractors) {
        quizVocabularyDistractors[index] = rawDistractors.map((row) =>
          Array.isArray(row)
            ? row.filter((item): item is string => typeof item === "string")
            : [],
        );
      }
      const rawCloze = parseJsonArray(frame.vocabularyCloze);
      if (rawCloze) {
        quizVocabularyCloze[index] = rawCloze.map((row) =>
          Array.isArray(row)
            ? row.filter(
                (item): item is { sentence: string; distractors: string[] } =>
                  Boolean(item) &&
                  typeof item === "object" &&
                  typeof (item as { sentence?: unknown }).sentence === "string" &&
                  Array.isArray((item as { distractors?: unknown }).distractors),
              )
            : [],
        );
      }
      const rawSynonym = parseJsonArray(frame.vocabularySynonym);
      if (rawSynonym) {
        quizVocabularySynonym[index] = rawSynonym.map((row) =>
          Array.isArray(row)
            ? row.filter(
                (item): item is { synonym: string; distractors: string[] } =>
                  Boolean(item) &&
                  typeof item === "object" &&
                  typeof (item as { synonym?: unknown }).synonym === "string" &&
                  Array.isArray((item as { distractors?: unknown }).distractors),
              )
            : [],
        );
      }
    }

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
    quizVocabulary,
    ...(Object.keys(quizVocabularyPinyin).length > 0 ? { quizVocabularyPinyin } : {}),
    ...(Object.keys(quizVocabularyPos).length > 0 ? { quizVocabularyPos } : {}),
    ...(Object.keys(quizVocabularyTranslation).length > 0 ? { quizVocabularyTranslation } : {}),
    ...(Object.keys(quizVocabularyDistractors).length > 0 ? { quizVocabularyDistractors } : {}),
    ...(Object.keys(quizVocabularyCloze).length > 0 ? { quizVocabularyCloze } : {}),
    ...(Object.keys(quizVocabularySynonym).length > 0 ? { quizVocabularySynonym } : {}),
    ...(Object.keys(quizSuggestedAnswers).length > 0 ? { quizSuggestedAnswers } : {}),
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
