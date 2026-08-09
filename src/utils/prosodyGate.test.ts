import {
  failedProsodyWords,
  prosodyGatePassed,
  shapeArrow,
  toneArrow,
} from "./storyRecorderFeedback";
import type { WordProsody } from "../components/StoryRecorder";

const word = (overrides: Partial<WordProsody>): WordProsody => ({
  token: "在家",
  index: 0,
  start_time: 0,
  end_time: 1,
  pitch_contour: [],
  mean_pitch: 220,
  pitch_range: 40,
  start_pitch: 240,
  end_pitch: 200,
  contour_shape: "falling",
  feedback: "",
  ...overrides,
});

describe("failedProsodyWords", () => {
  it("returns only words the backend marked as failed", () => {
    const words = [
      word({ token: "在家", passed: false }),
      word({ token: "看書", passed: true }),
      word({ token: "OK", passed: null }),
      word({ token: "聽" }), // legacy payload without the field
    ];
    expect(failedProsodyWords(words).map((w) => w.token)).toEqual(["在家"]);
  });

  it("handles absent word_prosody", () => {
    expect(failedProsodyWords(undefined)).toEqual([]);
  });
});

describe("prosodyGatePassed", () => {
  it("passes when no word failed — including unjudged and legacy words", () => {
    expect(prosodyGatePassed([word({ passed: true }), word({ passed: null })])).toBe(true);
    expect(prosodyGatePassed([word({})])).toBe(true);
    expect(prosodyGatePassed([])).toBe(true);
    expect(prosodyGatePassed(undefined)).toBe(true);
  });

  it("blocks when any word failed", () => {
    expect(
      prosodyGatePassed([word({ passed: true }), word({ passed: false })]),
    ).toBe(false);
  });

  it("blocks an explicitly unjudged word even when a numeric payload looks passable", () => {
    expect(
      prosodyGatePassed([
        word({ judged: false, passed: null, tone_accuracy: 0 }),
      ]),
    ).toBe(false);
  });
});

describe("tone/shape arrows", () => {
  it("maps the four tones plus neutral", () => {
    expect([1, 2, 3, 4, 5].map(toneArrow)).toEqual(["→", "↗", "˅", "↘", "·"]);
  });

  it("maps measured contour shapes, defaulting to variable", () => {
    expect(shapeArrow("rising")).toBe("↗");
    expect(shapeArrow("dip")).toBe("˅");
    expect(shapeArrow("unknown-shape")).toBe("~");
  });
});

describe("prosodyGatePassed is unaffected by the diagnostic layer", () => {
  // The four-state diagnosis exists for display and research. It must not
  // move anyone's lesson unlock, so the gate has to read exactly the same
  // fields it always did — `passed` and `judged` — and ignore the rest.
  it("ignores diagnostic_status entirely", () => {
    const failing = word({
      passed: false,
      diagnostic_status: "CORRECT",
    } as Partial<WordProsody>);
    expect(prosodyGatePassed([failing])).toBe(false);

    const passing = word({
      passed: true,
      diagnostic_status: "INCORRECT",
    } as Partial<WordProsody>);
    expect(prosodyGatePassed([passing])).toBe(true);
  });

  it("still blocks on unjudged words regardless of their diagnosis", () => {
    const unjudged = word({
      passed: null,
      judged: false,
      diagnostic_status: "CORRECT",
    } as Partial<WordProsody>);
    expect(prosodyGatePassed([unjudged])).toBe(false);
  });

  it("produces identical results with and without the new fields", () => {
    const bare = [word({ passed: true }), word({ passed: true, index: 1 })];
    const enriched = bare.map((item) => ({
      ...item,
      diagnostic_status: "UNCERTAIN" as const,
      syllables: [
        {
          char: "在",
          tone: 4,
          score: 53,
          passed: true,
          diagnostic_status: "UNCERTAIN" as const,
          contour_match_score: 53,
          legacy: { passed: true, score: 53, threshold: 58 },
        },
      ],
    }));
    expect(prosodyGatePassed(enriched)).toBe(prosodyGatePassed(bare));
    expect(failedProsodyWords(enriched).length).toBe(failedProsodyWords(bare).length);
  });
});
