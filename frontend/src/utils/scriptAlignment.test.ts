import { describe, expect, it } from "vitest";
import {
  scoreScriptChunks,
  scriptMatchRatio,
  scriptMismatchTokens,
  splitScriptIntoChunks,
  splitTeacherScriptIntoPhrases,
} from "./scriptAlignment";

describe("scriptMismatchTokens", () => {
  it("returns every missing or substituted script segment, without a display limit", () => {
    expect(
      scriptMismatchTokens(
        "朋友，這個星期快結束了，你週末打算做什麼？",
        "朋友，這個星期快結束了，你週末打算去哪裡？",
      ),
    ).toEqual(["做什麼"]);
  });

  it("ignores punctuation and does not flag a script without a transcript", () => {
    expect(scriptMismatchTokens("你好，朋友！", "你好朋友")).toEqual([]);
    expect(scriptMismatchTokens("你好，朋友！", "")).toEqual([]);
  });

  it("treats 妳 and 你 as the same spoken character without changing the target text", () => {
    expect(scriptMismatchTokens("友美妳這個週末要做什麼", "友美你這個週末要做什麼")).toEqual([]);
  });

  it("keeps a different character as a real script mismatch", () => {
    expect(scriptMismatchTokens("友美妳這個週末要做什麼", "友美她這個週末要做什麼")).toEqual(["妳"]);
  });
});

describe("scriptMatchRatio", () => {
  it("returns 1 for a perfect match", () => {
    expect(scriptMatchRatio("你這個週末要做什麼", "你這個週末要做什麼")).toBe(1);
  });

  it("returns 1 when ASR uses the homophone variant 你 for target 妳", () => {
    expect(scriptMatchRatio("友美妳這個週末要做什麼", "友美你這個週末要做什麼")).toBe(1);
  });

  it("tolerates a single mismatched character in a longer phrase", () => {
    // One ASR-slipped character ("這" -> "者") out of 9 should not read as
    // a total mismatch — this is the exact case an exact-substring check
    // (the old backend content_match rule) would fail outright.
    const ratio = scriptMatchRatio("你這個週末要做什麼", "你者個週末要做什麼");
    expect(ratio).toBeGreaterThan(0.8);
    expect(ratio).toBeLessThan(1);
  });

  it("returns 0 when there is no transcript yet", () => {
    expect(scriptMatchRatio("你這個週末要做什麼", "")).toBe(0);
    expect(scriptMatchRatio("你這個週末要做什麼", undefined)).toBe(0);
  });

  it("returns 1 for an empty script (nothing to mismatch)", () => {
    expect(scriptMatchRatio("", "隨便說什麼都可以")).toBe(1);
    expect(scriptMatchRatio(undefined, "隨便說什麼都可以")).toBe(1);
  });

  it("returns a low ratio for a completely different transcript", () => {
    expect(scriptMatchRatio("你這個週末要做什麼", "今天天氣很好")).toBeLessThan(0.3);
  });
});

describe("splitScriptIntoChunks", () => {
  it("splits on Chinese clause punctuation", () => {
    expect(splitScriptIntoChunks("我先去超市買菜，然後回家做飯，最後和家人一起吃飯。")).toEqual([
      "我先去超市買菜",
      "然後回家做飯",
      "最後和家人一起吃飯",
    ]);
  });

  it("returns the whole trimmed script as one chunk when there is no internal punctuation", () => {
    expect(splitScriptIntoChunks("你好朋友")).toEqual(["你好朋友"]);
    expect(splitScriptIntoChunks("你好，朋友！")).toEqual(["你好", "朋友"]);
  });

  it("breaks a long unpunctuated script into focused practice parts", () => {
    expect(splitScriptIntoChunks("你這個週末要做什麼")).toEqual([
      "你這個週末",
      "要做什麼",
    ]);
  });

  it("returns an empty array for an empty script", () => {
    expect(splitScriptIntoChunks("")).toEqual([]);
    expect(splitScriptIntoChunks(undefined)).toEqual([]);
  });
});

describe("scoreScriptChunks", () => {
  const script = "我先去超市買菜，然後回家做飯，最後和家人一起吃飯。";

  it("attributes passing word_prosody tokens to the right chunk and marks it passed", () => {
    const wordProsody = [
      { token: "我先去超市買菜", passed: true },
      { token: "然後回家做飯", passed: true },
      { token: "最後和家人一起吃飯", passed: true },
    ];
    const result = scoreScriptChunks(script, "我先去超市買菜然後回家做飯最後和家人一起吃飯", wordProsody);
    expect(result.map((chunk) => chunk.text)).toEqual([
      "我先去超市買菜",
      "然後回家做飯",
      "最後和家人一起吃飯",
    ]);
    expect(result.every((chunk) => chunk.passed)).toBe(true);
    expect(result.every((chunk) => chunk.mismatch === "")).toBe(true);
  });

  it("marks only the chunk with the failing token as not passed", () => {
    const wordProsody = [
      { token: "我先去超市買菜", passed: true },
      { token: "然後回家做飯", passed: false },
      { token: "最後和家人一起吃飯", passed: true },
    ];
    const result = scoreScriptChunks(script, "我先去超市買菜然後回家做飯最後和家人一起吃飯", wordProsody);
    expect(result[0].passed).toBe(true);
    expect(result[1].passed).toBe(false);
    expect(result[2].passed).toBe(true);
  });

  it("marks a chunk not passed and reports its mismatch when the learner skipped it entirely", () => {
    const wordProsody = [
      { token: "我先去超市買菜", passed: true },
      { token: "最後和家人一起吃飯", passed: true },
    ];
    const result = scoreScriptChunks(script, "我先去超市買菜最後和家人一起吃飯", wordProsody);
    expect(result[0].passed).toBe(true);
    expect(result[1].passed).toBe(false);
    expect(result[1].mismatch).toBe("然後回家做飯");
    expect(result[2].passed).toBe(true);
  });

  it("returns a single chunk for an unpunctuated script, matching pre-chunking behavior", () => {
    const wordProsody = [{ token: "你好朋友", passed: true }];
    const result = scoreScriptChunks("你好朋友", "你好朋友", wordProsody);
    expect(result).toHaveLength(1);
    expect(result[0].passed).toBe(true);
  });

  it("keeps chunk and word attribution aligned when 妳 is transcribed as 你", () => {
    const result = scoreScriptChunks(
      "友美妳這個週末要做什麼",
      "友美你這個週末要做什麼",
      [{ token: "友美你這個週末", passed: true }, { token: "要做什麼", passed: true }],
      ["友美妳這個週末", "要做什麼"],
    );
    expect(result.every((chunk) => chunk.passed)).toBe(true);
    expect(result.every((chunk) => chunk.mismatch === "")).toBe(true);
  });

  it("keeps an unpunctuated teacher sentence as one phrase", () => {
    expect(splitTeacherScriptIntoPhrases("abcdefghij")).toEqual(["abcdefghij"]);
  });

  it("allows explicit teacher phrase boundaries without inventing smaller chunks", () => {
    const result = scoreScriptChunks(
      "abcdefghij",
      "abcdefghij",
      [
        { token: "abcde", passed: true },
        { token: "fghij", passed: true },
      ],
      ["abcde", "fghij"],
    );
    expect(result.map((chunk) => chunk.text)).toEqual(["abcde", "fghij"]);
    expect(result.every((chunk) => chunk.passed)).toBe(true);
  });
});
