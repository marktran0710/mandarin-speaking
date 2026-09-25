import { afterAll, beforeAll, describe, expect, it, vi } from "vitest";
import { numericToToneMarked, primePinyin, toPinyin } from "./api";

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

describe("numericToToneMarked", () => {
  it("places the mark on a/e first", () => {
    expect(numericToToneMarked("guang3")).toBe("guǎng");
    expect(numericToToneMarked("xue2")).toBe("xué");
    expect(numericToToneMarked("mei4")).toBe("mèi");
  });

  it("keeps 'ou' on the o", () => {
    expect(numericToToneMarked("dou1")).toBe("dōu");
  });

  it("marks the LAST vowel for ui/iu/uo (regression: cuo4 was 'cùo')", () => {
    expect(numericToToneMarked("cuo4")).toBe("cuò");
    expect(numericToToneMarked("zuo4")).toBe("zuò");
    expect(numericToToneMarked("dui4")).toBe("duì");
    expect(numericToToneMarked("hui4")).toBe("huì");
    expect(numericToToneMarked("jiu3")).toBe("jiǔ");
  });

  it("handles ü/v spelling and neutral tone (no mark)", () => {
    expect(numericToToneMarked("lv4")).toBe("lǜ");
    expect(numericToToneMarked("nü3")).toBe("nǚ");
    expect(numericToToneMarked("wo3 men5")).toBe("wǒ men");
  });

  it("works spaced and unspaced across a whole word", () => {
    expect(numericToToneMarked("ka1 fei1 ting1")).toBe("kā fēi tīng");
    expect(numericToToneMarked("ka1fei1ting1")).toBe("kāfēitīng");
  });
});
