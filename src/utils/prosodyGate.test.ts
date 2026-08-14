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

  it("uses the same hard-failure policy as progression", () => {
    // After the tone-verdict refactor, UNCERTAIN blocks progression too:
    // the diagnostic status IS the canonical gate, and CORRECT is the only
    // value that clears it. INCORRECT and UNCERTAIN both count as failures;
    // a word with diagnostic_status="CORRECT" clears it regardless of what
    // the legacy `passed` field says.
    expect(
      failedProsodyWords([
        word({ index: 1, passed: false, diagnostic_status: "UNCERTAIN" }),
        word({
          index: 2,
          passed: false,
          diagnostic_status: "CORRECT",
          reference_source: "real_voice",
          shape_accuracy: 84,
        }),
        word({ index: 3, passed: false, diagnostic_status: "INCORRECT" }),
      ]).map((item) => item.index),
    ).toEqual([1, 3]);
  });
});

describe("prosodyGatePassed", () => {
  const withSyllables = (passStates: (boolean | null)[]) =>
    word({
      passed: passStates.every(Boolean) ? true : false,
      syllables: passStates.map((state, index) => ({
        char: `s${index}`,
        tone: 1,
        score: state === true ? 80 : state === false ? 42 : 0,
        passed: state,
      })),
    });

  it("passes when no syllable failed — including empty and legacy payloads", () => {
    expect(prosodyGatePassed([withSyllables([true, true])])).toBe(true);
    expect(prosodyGatePassed([word({})])).toBe(true);
    expect(prosodyGatePassed([])).toBe(true);
    expect(prosodyGatePassed(undefined)).toBe(true);
  });

  it("clears the gate at or above the 80% syllable pass rate", () => {
    // 8/10 = 80% — exactly at the bar; passes.
    const eightyPercent = withSyllables([...Array(8).fill(true), false, false]);
    expect(prosodyGatePassed([eightyPercent])).toBe(true);
  });

  it("blocks below the 80% syllable pass rate", () => {
    // 7/10 = 70%; below the bar.
    const seventyPercent = withSyllables([
      ...Array(7).fill(true),
      false,
      false,
      false,
    ]);
    expect(prosodyGatePassed([seventyPercent])).toBe(false);
  });

  it("stays out of the way when nothing was judged", () => {
    // No judged syllables — no evidence to pass or fail on. Falls back to
    // the any-hard-failure rule; an unjudged word contributes nothing, so
    // the gate stays open.
    expect(
      prosodyGatePassed([
        word({ judged: false, passed: null, tone_accuracy: 0 }),
      ]),
    ).toBe(true);
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

describe("prosodyGatePassed reads the canonical diagnostic verdict", () => {
  // After the tone-verdict refactor, the diagnostic status IS the canonical
  // pronunciation gate. CORRECT is the only value that clears it; UNCERTAIN
  // and INCORRECT both block. This test file pins the new invariants —
  // together with the backend rule that `passed` follows `verdict==CORRECT`,
  // it closes the placeholder-auto-pass loophole end-to-end.
  it("blocks BOTH an uncertain and an incorrect verdict", () => {
    const uncertain = word({
      passed: false,
      diagnostic_status: "UNCERTAIN",
    } as Partial<WordProsody>);
    expect(prosodyGatePassed([uncertain])).toBe(false);

    const incorrect = word({
      passed: false,
      diagnostic_status: "INCORRECT",
    } as Partial<WordProsody>);
    expect(prosodyGatePassed([incorrect])).toBe(false);
  });

  it("clears a CORRECT verdict even when the legacy passed flag disagrees", () => {
    // The refactor makes the diagnostic status authoritative — a legacy
    // `passed: false` field must not veto a CORRECT diagnosis.
    const passing = word({
      passed: false,
      diagnostic_status: "CORRECT",
    } as Partial<WordProsody>);
    expect(prosodyGatePassed([passing])).toBe(true);
  });

  it("keeps unjudged words out of the gate — nothing to fail on", () => {
    // A word the analyzer did not have enough pitch to judge stays silent:
    // it is neither a fail nor a pass. Progression falls back to the
    // backend's own mastery gate, which is more strict about "not_judged".
    const unjudged = word({
      passed: null,
      judged: false,
      diagnostic_status: "UNCERTAIN",
    } as Partial<WordProsody>);
    expect(prosodyGatePassed([unjudged])).toBe(true);
  });

  it("falls back to legacy passed when no diagnostic status is present", () => {
    // Older payloads (from before the diagnostic layer existed, or from a
    // code path that still writes only the legacy fields) must still work.
    expect(prosodyGatePassed([word({ passed: true })])).toBe(true);
    expect(prosodyGatePassed([word({ passed: false })])).toBe(false);
  });
});
