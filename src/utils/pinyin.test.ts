import { afterAll, beforeAll, describe, expect, it, vi } from "vitest";
import { primePinyin, toPinyin } from "./pinyin";

const canonicalValues: Record<string, string> = {
  "姐姐": "jiě jiě",
  "哥哥": "gē gē",
  "弟弟": "dì dì",
  "妹妹": "mèi mèi",
  "謝謝": "xiè xiè",
  "妳": "nǐ",
  "妳這個週末要做什麼": "nǐ zhè gè zhōu mò yào zuò shén me",
  "聽音樂": "tīng yīn yuè",
  "什麼": "shén me",
};

describe("canonical Taiwan Mandarin pinyin", () => {
  beforeAll(async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_input: string, init?: RequestInit) => {
        const body = JSON.parse(String(init?.body ?? "{}")) as { texts?: string[] };
        return {
          ok: true,
          status: 200,
          json: async () => ({
            items: (body.texts ?? []).map((text) => ({
              text,
              pinyin: canonicalValues[text] ?? "",
            })),
          }),
        };
      }),
    );
    await primePinyin(Object.keys(canonicalValues));
  });

  afterAll(() => {
    vi.unstubAllGlobals();
  });

  it("uses the backend value for common Taiwan readings", () => {
    for (const [text, expected] of Object.entries(canonicalValues)) {
      expect(toPinyin(text)).toBe(expected);
    }
  });

  it("returns empty string for non-Chinese input", () => {
    expect(toPinyin("hello")).toBe("");
  });
});
