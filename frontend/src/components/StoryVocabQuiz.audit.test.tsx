import { describe, expect, it, vi, beforeAll } from "vitest";
import {
  buildQuizQuestion,
  collectQuizEntries,
  type VocabQuizEntry,
  type VocabQuizQuestion,
} from "./StoryVocabQuiz";
import { auditQuizEntries, auditQuizQuestion, type QuizAuditIssue } from "../utils/quizAudit";
import {
  storyToTopic,
  storyHasTierContent,
  type CustomTeacherStory,
  type StoryDifficultyLevel,
} from "../utils/teacherStories";
import type { Topic } from "./TopicSelector";

// vitest runs under node, but the app tsconfig has no node types — declare
// the one process field the dump gate reads.
declare const process: { env: Record<string, string | undefined> };
import storiesFixture from "./__fixtures__/custom-stories.json";

// Snapshot of the real teacher story library (backend /api/custom-stories,
// captured 2026-07-23). Refresh with:
//   Invoke-WebRequest http://127.0.0.1:8000/api/custom-stories `
//     -OutFile src/components/__fixtures__/custom-stories.json
const stories = storiesFixture as unknown as CustomTeacherStory[];

/** Mirrors StoryRecorder's quizEntries memo: flatten every scene's glossed
 * words (aligned with their per-word AI data) and run them through
 * collectQuizEntries — the exact pool the live quiz draws from. */
function entriesForTopic(topic: Topic): VocabQuizEntry[] {
  const words: string[] = [];
  const translations: Array<string | undefined> = [];
  const suggestedAnswers: Array<string | undefined> = [];
  const aiDistractors: Array<string[] | undefined> = [];
  const pinyins: Array<string | undefined> = [];
  const aiCloze: Array<Array<{ sentence: string; distractors: string[] }> | undefined> = [];
  const partsOfSpeech: Array<string | undefined> = [];
  const aiSynonyms: Array<Array<{ synonym: string; distractors: string[] }> | undefined> = [];
  topic.images.forEach((_, si) => {
    const sceneSuggestedAnswer = topic.suggestedAnswers?.[si];
    (topic.vocabulary[si] || []).forEach((word, i) => {
      words.push(word);
      translations.push(topic.vocabularyTranslation?.[si]?.[i]);
      suggestedAnswers.push(sceneSuggestedAnswer);
      aiDistractors.push(topic.vocabularyDistractors?.[si]?.[i]);
      pinyins.push(topic.vocabularyPinyin?.[si]?.[i]);
      aiCloze.push(topic.vocabularyCloze?.[si]?.[i]);
      partsOfSpeech.push(topic.vocabularyPos?.[si]?.[i]);
      aiSynonyms.push(topic.vocabularySynonym?.[si]?.[i]);
    });
  });
  return collectQuizEntries(
    words,
    translations,
    suggestedAnswers,
    aiDistractors,
    pinyins,
    aiCloze,
    partsOfSpeech,
    aiSynonyms,
  );
}

/** Every (story, difficulty) vocab pool in the fixture with at least two
 * entries — one entry can't produce the word-option question kinds. */
function allPools(): Array<{ name: string; entries: VocabQuizEntry[] }> {
  const pools: Array<{ name: string; entries: VocabQuizEntry[] }> = [];
  for (const story of stories) {
    const levels: StoryDifficultyLevel[] = ["easy"];
    if (storyHasTierContent(story, "medium")) levels.push("medium");
    if (storyHasTierContent(story, "hard")) levels.push("hard");
    for (const level of levels) {
      const entries = entriesForTopic(storyToTopic(story, level));
      if (entries.length > 0) {
        pools.push({ name: `${story.title} (${level})`, entries });
      }
    }
  }
  return pools;
}

const ROUNDS_PER_ENTRY = 12;
const TIER_MODES = ["tier1", "tier2", "tier3"] as const;

describe("quiz audit — real story data", () => {
  beforeAll(() => {
    // jsdom has no speech synthesis; stub both globals canUseSpeechSynthesis
    // checks so listening questions participate in the audit.
    vi.stubGlobal("speechSynthesis", { speak: vi.fn(), cancel: vi.fn() });
    vi.stubGlobal("SpeechSynthesisUtterance", vi.fn());
  });

  it("has at least one story pool in the fixture", () => {
    expect(allPools().length).toBeGreaterThan(0);
  });

  it("generates only single-correct-answer questions across every story × tier", () => {
    const errors: string[] = [];
    for (const pool of allPools()) {
      for (const mode of TIER_MODES) {
        for (const entry of pool.entries) {
          for (let round = 0; round < ROUNDS_PER_ENTRY; round++) {
            const question = buildQuizQuestion(entry, pool.entries, mode);
            for (const issue of auditQuizQuestion(question, pool.entries)) {
              if (issue.severity === "error") {
                errors.push(`${pool.name} / ${mode}: [${issue.rule}] ${issue.detail}`);
              }
            }
          }
        }
      }
    }
    expect([...new Set(errors)]).toEqual([]);
  });

  it("story vocabulary data itself carries no error-level issues (warnings reported separately)", () => {
    const errors: QuizAuditIssue[] = [];
    for (const pool of allPools()) {
      for (const issue of auditQuizEntries(pool.entries)) {
        if (issue.severity === "error") errors.push(issue);
      }
    }
    expect(errors).toEqual([]);
  });
});

// ─── The audit itself must catch broken questions (not be a tautology) ───────

describe("auditQuizQuestion — synthetic violations", () => {
  const entries: VocabQuizEntry[] = [
    { word: "高興", translation: "happy", pinyin: "gāoxìng" },
    { word: "開心", translation: "happy", pinyin: "kāixīn" },
    { word: "他", translation: "he", pinyin: "tā" },
    { word: "她", translation: "she", pinyin: "tā" },
    { word: "學校", translation: "school", pinyin: "xuéxiào" },
  ];

  it("flags a missing correct answer", () => {
    const q: VocabQuizQuestion = {
      kind: "translation",
      word: "學校",
      correctTranslation: "school",
      options: ["home", "friend", "water"],
      isAiGenerated: false,
    };
    expect(auditQuizQuestion(q, entries).map((i) => i.rule)).toContain("correct-answer-missing");
  });

  it("flags case/punctuation-disguised duplicate options", () => {
    const q: VocabQuizQuestion = {
      kind: "translation",
      word: "學校",
      correctTranslation: "school",
      options: ["school", "School.", "water", "home"],
      isAiGenerated: false,
    };
    const rules = auditQuizQuestion(q, entries).map((i) => i.rule);
    expect(rules).toContain("duplicate-options");
    expect(rules).toContain("distractor-equals-correct");
  });

  it("flags a reverse question whose distractor shares the prompt translation", () => {
    const q: VocabQuizQuestion = {
      kind: "reverse",
      word: "高興",
      translation: "happy",
      correctWord: "高興",
      options: ["高興", "開心", "學校", "他"],
      isAiGenerated: false,
    };
    expect(auditQuizQuestion(q, entries).map((i) => i.rule)).toContain("reverse-second-correct");
  });

  it("flags a listening question with a homophone distractor (他/她)", () => {
    const q: VocabQuizQuestion = {
      kind: "listening",
      word: "他",
      correctWord: "他",
      options: ["他", "她", "學校", "高興"],
      isAiGenerated: false,
    };
    expect(auditQuizQuestion(q, entries).map((i) => i.rule)).toContain("listening-homophone");
  });

  it("flags a cloze sentence that still shows the answer", () => {
    const q: VocabQuizQuestion = {
      kind: "cloze",
      word: "學校",
      sentenceWithBlank: "我去____，學校很大。",
      correctWord: "學校",
      options: ["學校", "他", "高興"],
      isAiGenerated: true,
    };
    expect(auditQuizQuestion(q, entries).map((i) => i.rule)).toContain("cloze-answer-leak");
  });

  it("flags a synonym question whose distractor shares the prompt's translation", () => {
    const q: VocabQuizQuestion = {
      kind: "synonym",
      word: "高興",
      correctSynonym: "快樂",
      options: ["快樂", "開心", "學校", "他"],
      isAiGenerated: true,
    };
    expect(auditQuizQuestion(q, entries).map((i) => i.rule)).toContain("synonym-second-correct");
  });

  it("accepts a clean question", () => {
    const q: VocabQuizQuestion = {
      kind: "translation",
      word: "學校",
      correctTranslation: "school",
      options: ["school", "home", "friend", "water"],
      isAiGenerated: false,
    };
    expect(auditQuizQuestion(q, entries).filter((i) => i.severity === "error")).toEqual([]);
  });
});

// ─── One-off dump for human/AI semantic review (QUIZ_DUMP=1) ─────────────────

describe.runIf(Boolean(process.env.QUIZ_DUMP))("quiz dump for semantic review", () => {
  beforeAll(() => {
    vi.stubGlobal("speechSynthesis", { speak: vi.fn(), cancel: vi.fn() });
    vi.stubGlobal("SpeechSynthesisUtterance", vi.fn());
  });

  it("writes every distinct generated question to quiz-dump.txt", async () => {
    // Non-literal specifier keeps the app tsconfig (no node types) from
    // trying to resolve the module's types; vitest resolves it at runtime.
    const fs = (await import("node" + ":fs")) as {
      writeFileSync: (path: string, data: string, encoding: string) => void;
    };
    const lines = new Set<string>();
    const warnings = new Set<string>();
    for (const pool of allPools()) {
      for (const issue of auditQuizEntries(pool.entries)) {
        warnings.add(`${pool.name}: [${issue.rule}] ${issue.detail}`);
      }
      for (const mode of TIER_MODES) {
        for (const entry of pool.entries) {
          for (let round = 0; round < 30; round++) {
            const q = buildQuizQuestion(entry, pool.entries, mode);
            const prompt =
              q.kind === "translation" ? q.word
              : q.kind === "cloze" ? q.sentenceWithBlank
              : q.kind === "pinyin" ? q.word
              : q.kind === "pos" ? q.word
              : q.kind === "synonym" ? q.word
              : q.kind === "reverse" ? q.translation
              : `(nghe) ${q.word}`;
            const correct =
              q.kind === "translation" ? q.correctTranslation
              : q.kind === "pinyin" ? q.correctPinyin
              : q.kind === "pos" ? q.correctPos
              : q.kind === "synonym" ? q.correctSynonym
              : q.correctWord;
            lines.add(
              `${pool.name} | ${q.kind} | Q: ${prompt} | ✓ ${correct} | options: ${[...q.options].sort().join(" / ")}`,
            );
          }
        }
      }
    }
    const out = [
      "── entry warnings ──",
      ...[...warnings].sort(),
      "",
      "── distinct questions ──",
      ...[...lines].sort(),
    ].join("\n");
    fs.writeFileSync("quiz-dump.txt", out, "utf8");
    expect(lines.size).toBeGreaterThan(0);
  });
});
