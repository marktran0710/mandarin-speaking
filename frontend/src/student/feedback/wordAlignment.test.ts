import { describe, expect, it, vi } from "vitest";
import type { WordProsody, WordProsodySyllable } from "../../components/story-recorder/StoryRecorder";
import { mapWordProsodyToAlignment } from "./wordAlignment";

vi.mock("../../utils/pinyin", () => ({
  toPinyin: (text: string) => ({
    "\u4eca\u5929": "j\u012bn ti\u0101n",
    "\u597d": "h\u01ceo",
  }[text] ?? ""),
  toPinyinSyllables: (text: string) => ({
    "\u4eca\u5929": ["j\u012bn", "ti\u0101n"],
    "\u597d": ["h\u01ceo"],
  }[text] ?? []),
}));

function word(token: string, index: number, overrides: Partial<WordProsody> = {}): WordProsody {
  return {
    token,
    index,
    start_time: 0,
    end_time: 1,
    pitch_contour: [],
    mean_pitch: 0,
    pitch_range: 0,
    start_pitch: 0,
    end_pitch: 0,
    contour_shape: "",
    feedback: "",
    ...overrides,
  };
}

describe("mapWordProsodyToAlignment", () => {
  it("preserves backend word order and maps all four diagnostic states", () => {
    const result = mapWordProsodyToAlignment([
      word("A", 0, { diagnostic_status: "CORRECT" }),
      word("B", 1, { diagnostic_status: "UNCERTAIN" }),
      word("C", 2, { diagnostic_status: "INCORRECT" }),
      word("D", 3, { diagnostic_status: "INVALID_AUDIO" }),
    ]);

    expect(result.map((item) => item.status)).toEqual([
      "CORRECT",
      "UNCERTAIN",
      "INCORRECT",
      "INVALID_AUDIO",
    ]);
    expect(result.map((item) => item.hanzi)).toEqual(["A", "B", "C", "D"]);
  });

  it("marks a neutral-only word separately from uncertain evidence", () => {
    const [item] = mapWordProsodyToAlignment([
      word("\u597d", 0, {
        diagnostic_status: "UNCERTAIN",
        syllables: [{
          char: "\u597d",
          tone: 5,
          score: 0,
          passed: null,
          score_provenance: "neutral_not_measured",
        }],
      }),
    ]);

    expect(item.status).toBe("NEUTRAL");
    expect(item.pinyin).toBe("h\u01ceo");
  });

  it("shows an all-not-scored word as unable to evaluate", () => {
    const [item] = mapWordProsodyToAlignment([
      word("A", 0, {
        diagnostic_status: "UNCERTAIN",
        syllables: [{
          char: "A",
          tone: 1,
          score: 0,
          passed: null,
          score_provenance: "not_scored",
        }],
      }),
    ]);

    expect(item.status).toBe("INVALID_AUDIO");
  });

  it("renders multi-syllable pinyin and supplied backend notes", () => {
    const [item] = mapWordProsodyToAlignment([
      word("\u4eca\u5929", 4, {
        diagnostic_status: "CORRECT",
        feedback: "Keep the two syllables connected.",
        syllables: [
          { char: "\u4eca", tone: 1, score: 80, passed: true, pinyin: "j\u012bn" } as WordProsodySyllable,
          { char: "\u5929", tone: 1, score: 80, passed: true, pinyin: "ti\u0101n" } as WordProsodySyllable,
        ],
      }),
    ]);

    expect(item.pinyin).toBe("j\u012bn ti\u0101n");
    expect(item.note).toBe("Keep the two syllables connected.");
  });

  it("does not collapse unsegmented transcription into one chip", () => {
    const result = mapWordProsodyToAlignment([
      word("\u4eca", 0, { diagnostic_status: "CORRECT" }),
      word("\u5929", 1, { diagnostic_status: "UNCERTAIN" }),
    ]);

    expect(result).toHaveLength(2);
    expect(result.map((item) => item.hanzi)).not.toContain("\u4eca\u5929");
  });
});
