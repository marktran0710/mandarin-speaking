import { scoreTier, scoreTierLabel } from "./scoreLabels";

describe("scoreTier", () => {
  it("buckets scores into excellent/good/ok/low at the 85/68/48 thresholds", () => {
    expect(scoreTier(100)).toBe("excellent");
    expect(scoreTier(85)).toBe("excellent");
    expect(scoreTier(84)).toBe("good");
    expect(scoreTier(68)).toBe("good");
    expect(scoreTier(67)).toBe("ok");
    expect(scoreTier(48)).toBe("ok");
    expect(scoreTier(47)).toBe("low");
    expect(scoreTier(0)).toBe("low");
  });
});

describe("scoreTierLabel", () => {
  it("returns a bilingual label for every tier", () => {
    expect(scoreTierLabel("excellent")).toEqual({ zh: "非常好", pinyin: "Fēicháng hǎo", en: "Excellent" });
    expect(scoreTierLabel("good")).toEqual({ zh: "不錯", pinyin: "Búcuò", en: "Good" });
    expect(scoreTierLabel("ok")).toEqual({ zh: "還可以", pinyin: "Hái kěyǐ", en: "Needs practice" });
    expect(scoreTierLabel("low")).toEqual({ zh: "再試試", pinyin: "Zài shìshi", en: "Keep trying" });
  });
});
