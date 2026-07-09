import { toPinyin } from "./pinyin";

describe("toPinyin Taiwan Mandarin overrides", () => {
  it("keeps full tone on both syllables for common kinship reduplications", () => {
    // pinyin-pro's default (Mainland-leaning) dictionary lightens the second
    // syllable of these to a neutral tone; Taiwan Mandarin keeps it full —
    // and the backend derives a word's scored target shape directly from
    // this displayed pinyin, so a wrong override here silently mis-scores
    // pronunciation practice for these words.
    expect(toPinyin("姐姐")).toBe("jiě jiě");
    expect(toPinyin("哥哥")).toBe("gē gē");
    expect(toPinyin("弟弟")).toBe("dì dì");
    expect(toPinyin("妹妹")).toBe("mèi mèi");
  });

  it("keeps the existing 謝謝 override working", () => {
    expect(toPinyin("謝謝")).toBe("xiè xiè");
  });

  it("returns empty string for non-Chinese input", () => {
    expect(toPinyin("hello")).toBe("");
  });
});
