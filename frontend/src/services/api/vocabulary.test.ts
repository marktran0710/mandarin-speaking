import { beforeEach, describe, expect, it, vi } from "vitest";

const { fetchWithRetry } = vi.hoisted(() => ({ fetchWithRetry: vi.fn() }));

vi.mock("./client", () => ({
  BACKEND_URL: "http://backend.test",
  fetchWithRetry,
}));

import { createQuizVocabularyWord, listVocabularyStories, type QuizVocabularyWordDraft } from "./vocabulary";

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

  it("reloads the content bank through the admin-scoped endpoint", async () => {
    fetchWithRetry.mockResolvedValue(new Response(JSON.stringify([{ id: "story-1" }]), { status: 200 }));

    await expect(listVocabularyStories()).resolves.toEqual([{ id: "story-1" }]);
    expect(fetchWithRetry).toHaveBeenCalledWith("http://backend.test/api/admin/content-bank?limit=500&skip=0");
  });

  it("surfaces the backend status when the content bank reload fails", async () => {
    fetchWithRetry.mockResolvedValue(new Response(JSON.stringify({ detail: "Administrator account required." }), { status: 403 }));

    await expect(listVocabularyStories()).rejects.toThrow("Could not load Speaking vocabulary (403). Administrator account required.");
  });
});
