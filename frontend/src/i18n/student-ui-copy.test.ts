import { describe, expect, it } from "vitest";
import { studentUiCopy } from "./student-ui-copy";

describe("student UI copy catalog", () => {
  it("provides Chinese text and tone-marked pinyin for every system key", () => {
    for (const [key, copy] of Object.entries(studentUiCopy)) {
      expect(copy.zh, `${key} is missing Chinese copy`).toBeTruthy();
      expect(copy.pinyin, `${key} is missing pinyin`).toBeTruthy();
      expect(copy.en, `${key} is missing English gloss`).toBeTruthy();
      expect(copy.pinyin).toMatch(/[āáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜ]/u);
    }
  });
});
