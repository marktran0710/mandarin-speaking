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
