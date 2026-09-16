import { beforeEach, describe, expect, it, vi } from "vitest";

const { fetchWithRetry } = vi.hoisted(() => ({ fetchWithRetry: vi.fn() }));

vi.mock("./client", () => ({
  BACKEND_URL: "http://backend.test",
  fetchWithRetry,
}));

import { createQuizVocabularyWord, type QuizVocabularyWordDraft } from "./vocabulary";

const draft: QuizVocabularyWordDraft = {
  targetWord: "bed",
  pinyin: "chuang",
  pos: "N",
  simpleEnglishMeaning: "bed",
  questions: [],
};

describe("quiz vocabulary API errors", () => {
  beforeEach(() => fetchWithRetry.mockReset());

  it("keeps structured validation issues actionable for the editor", async () => {
    fetchWithRetry.mockResolvedValue(new Response(JSON.stringify({
      detail: {
        message: "Quiz bank failed validation.",
        issues: [{ code: "CORRECT_NOT_IN_OPTIONS", question_id: "W1_EASY", message: "The correct answer must be one of the options." }],
      },
    }), { status: 422 }));

    await expect(createQuizVocabularyWord("story-1", draft)).rejects.toThrow(
      "Quiz bank failed validation. W1_EASY: [CORRECT_NOT_IN_OPTIONS] The correct answer must be one of the options.",
    );
  });
});
