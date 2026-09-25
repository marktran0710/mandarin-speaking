import { describe, expect, it } from "vitest";
import { buildConversationTurnsFromScenes, normalizeConversationTurns } from "@entities/conversation";

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

  it("preserves an optional student targetAudioUrl distinct from the system's audioUrl", () => {
    const source = [
      { id: "prompt-1", speaker: "system", text: "你好", audioUrl: "/uploads/character-01.mp3" },
      { id: "reply-1", speaker: "student", text: "你好！", targetText: "你好", targetAudioUrl: "/uploads/student-model-01.mp3" },
    ];

    const normalized = normalizeConversationTurns(source);

    expect(normalized?.[0].audioUrl).toBe("/uploads/character-01.mp3");
    expect(normalized?.[1].targetAudioUrl).toBe("/uploads/student-model-01.mp3");
    expect(normalized?.[0].targetAudioUrl).toBeUndefined();
  });

  it.each([
    [undefined, "is missing"],
    [[], "is empty"],
    [[{ id: "one", speaker: "system", text: "雿末" }], "has fewer than two turns"],
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
    [
      [
        { id: "one", speaker: "system", text: "你好" },
        { id: "two", speaker: "student", text: "你好", targetAudioUrl: 42 },
      ],
      "has a malformed targetAudioUrl",
    ],
  ])("returns null when the conversation %s", (turns: unknown, _reason: string) => {
    expect(normalizeConversationTurns(turns)).toBeNull();
  });
});

describe("buildConversationTurnsFromScenes", () => {
  it("reuses scene targets, starts with system, and alternates speakers", () => {
    const turns = buildConversationTurnsFromScenes([
      { targetText: "Scene one", audioUrl: "/audio/one.mp3" },
      { targetText: "Scene two", audioUrl: "/audio/two.mp3" },
      { targetText: "Scene three" },
    ]);

    expect(turns).toEqual([
      { id: "system-scene-0", speaker: "system", text: "Scene one", sceneIndex: 0, audioUrl: "/audio/one.mp3" },
      { id: "student-scene-1", speaker: "student", text: "Scene two", sceneIndex: 1, targetText: "Scene two", targetAudioUrl: "/audio/two.mp3" },
      { id: "system-scene-2", speaker: "system", text: "Scene three", sceneIndex: 2 },
    ]);
  });

  it("falls back to the Story Speaking prompt and needs two usable scenes", () => {
    expect(buildConversationTurnsFromScenes([{ prompt: "Only scene" }])).toBeNull();
    expect(buildConversationTurnsFromScenes([
      { prompt: "First prompt" },
      { targetText: "Second target" },
    ])?.map((turn) => turn.text)).toEqual(["First prompt", "Second target"]);
  });
});
