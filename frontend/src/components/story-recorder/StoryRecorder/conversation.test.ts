import { describe, expect, it } from "vitest";
import { normalizeConversationTurns } from "./conversation";

describe("normalizeConversationTurns", () => {
  it("returns a copied valid alternating conversation", () => {
    const source = [
      { id: "prompt-1", speaker: "system", text: "你好", pinyin: "nǐ hǎo" },
      { id: "reply-1", speaker: "student", text: "你好！", targetText: "你好" },
    ];

    const normalized = normalizeConversationTurns(source);

    expect(normalized).toEqual(source);
    expect(normalized).not.toBe(source);
    expect(normalized?.[0]).not.toBe(source[0]);
  });

  it.each([
    [undefined, "is missing"],
    [[], "is empty"],
    [[{ id: "one", speaker: "system", text: "雿末" }], "does not end with a student turn"],
    [[{ id: " ", speaker: "system", text: "你好" }], "has a blank id"],
    [[{ id: "one", speaker: "system", text: " " }], "has blank text"],
    [[{ id: "one", speaker: "student", text: "你好" }], "does not start with system"],
    [
      [
        { id: "one", speaker: "system", text: "你好" },
        { id: "two", speaker: "system", text: "你好" },
      ],
      "does not alternate speakers",
    ],
    [
      [
        { id: "one", speaker: "system", text: "你好" },
        { id: "one", speaker: "student", text: "你好" },
      ],
      "has duplicate ids",
    ],
    [[{ id: "one", speaker: "system", text: "你好", audioUrl: 42 }], "has a malformed optional field"],
  ])("returns null when the conversation %s", (turns: unknown, _reason: string) => {
    expect(normalizeConversationTurns(turns)).toBeNull();
  });
});
