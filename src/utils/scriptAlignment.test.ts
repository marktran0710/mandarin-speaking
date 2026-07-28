import { describe, expect, it } from "vitest";
import { scriptMismatchTokens } from "./scriptAlignment";

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
});
