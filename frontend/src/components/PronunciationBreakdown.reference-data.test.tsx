import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import PronunciationBreakdown from "./PronunciationBreakdown";
import type { WordProsody } from "./StoryRecorder";

/**
 * The panel answers "did the app even listen?" — so the tests that matter are
 * about what it shows when nothing is wrong, about keeping the vowel column
 * from reading as a score it isn't, and about the collapsed row staying
 * scannable while the detail stays reachable.
 */

function word(overrides: Partial<WordProsody>): WordProsody {
  return {
    token: "你媽",
    index: 0,
    start_time: 0,
    end_time: 1,
    pitch_contour: [],
    mean_pitch: 200,
    pitch_range: 40,
    start_pitch: 200,
    end_pitch: 210,
    contour_shape: "level",
    feedback: "",
    ...overrides,
  } as WordProsody;
}

const passingWord = word({
  passed: true,
  diagnostic_status: "CORRECT",
  syllables: [
    {
      char: "你",
      tone: 3,
      score: 88,
      passed: true,
      diagnostic_status: "CORRECT",
      diagnostic_reason: "contour_matches_expected_tone",
      contour_match_score: 88,
      score_provenance: "measured",
      expected_vowel: "i",
      expected_zone: { height: "high", backness: "front" },
      final: "i",
      f1: 310,
      f2: 2280,
      measured_zone: { height: "high", backness: "front" },
      vowel_status: "measured",
    },
    {
      char: "媽",
      tone: 1,
      score: 91,
      passed: true,
      diagnostic_status: "CORRECT",
      diagnostic_reason: "contour_matches_expected_tone",
      contour_match_score: 91,
      score_provenance: "measured",
      expected_vowel: "a",
      expected_zone: { height: "low", backness: "central" },
      final: "a",
      f1: 870,
      f2: 1320,
      measured_zone: { height: "low", backness: "central" },
      vowel_status: "measured",
    },
  ],
});

/** Every character row is a button; the legend items are not. */
function characterRows() {
  return screen
    .getAllByRole("button")
    .filter((node) => node.classList.contains("pb-row"));
}

describe("PronunciationBreakdown: reference and source data", () => {
  it("uses a passing real reference curve consistently with the progression gate", () => {
    const referenceWord = word({
      reference_source: "real_voice",
      shape_accuracy: 84,
      passed: false,
      syllables: [
        {
          ...passingWord.syllables![0],
          passed: false,
          diagnostic_status: "INCORRECT",
        },
      ],
    });

    const { container } = render(<PronunciationBreakdown words={[referenceWord]} />);
    const row = container.querySelector(".pb-row")!;
    expect(row.classList.contains("pb-row-failed")).toBe(false);
    expect(row.querySelector(".is-fail")).toBeNull();
  });

  it("does not downgrade a passing phrase because one tone is neutral or unjudged", () => {
    const phrase = "\u59b3\u9019\u500b\u9031\u672b\u8981\u505a\u4ec0\u9ebc";
    const measured = word({
      token: "\u9019\u500b",
      index: 1,
      judged: true,
      passed: true,
      diagnostic_status: "CORRECT",
      syllables: [
        { char: "\u9019", tone: 4, score: 90, passed: true, diagnostic_status: "CORRECT" },
        { char: "\u500b", tone: 4, score: 90, passed: true, diagnostic_status: "CORRECT" },
      ],
    });
    const neutral = word({
      token: "\u9ebc",
      index: 2,
      judged: true,
      passed: true,
      diagnostic_status: "UNCERTAIN",
      syllables: [{
        char: "\u9ebc",
        tone: 5,
        score: 75,
        passed: true,
        diagnostic_status: "UNCERTAIN",
        score_provenance: "neutral_not_measured",
      }],
    });
    const unjudged = word({
      token: "\u59b3",
      index: 0,
      judged: false,
      passed: null,
      syllables: [{
        char: "\u59b3",
        tone: 3,
        score: 0,
        passed: null,
        diagnostic_status: "UNCERTAIN",
        score_provenance: "not_scored",
      }],
    });

    render(
      <PronunciationBreakdown
        words={[unjudged, measured, neutral]}
        targetText={phrase}
        transcription={phrase}
      />,
    );

    expect(screen.getByText("phrase ready")).toBeInTheDocument();
    expect(screen.queryByText("not enough evidence")).toBeNull();
  });

  it("loads pinyin for the exact analyzed word tokens", async () => {
    const token = "\u6e2c\u8a66\u5b57";
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ items: [{ text: token, pinyin: "ce4 shi4 zi4" }] }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const { container } = render(
      <PronunciationBreakdown
        words={[word({
          token,
          syllables: [
            { char: "\u6e2c", tone: 4, score: 90, passed: true },
            { char: "\u8a66", tone: 4, score: 90, passed: true },
            { char: "\u5b57", tone: 4, score: 90, passed: true },
          ],
        })]}
      />,
    );

    await waitFor(() => {
      expect(container.querySelector(".pb-group-pinyin")?.textContent).toBe(
        "ce4 shi4 zi4",
      );
    });
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/pinyin"),
      expect.objectContaining({ method: "POST" }),
    );
    vi.unstubAllGlobals();
  });

  it("states plainly that the vowel column is a measurement, not a score", () => {
    render(<PronunciationBreakdown words={[passingWord]} />);
    expect(screen.getByText(/母音只是量到的嘴型，沒有分數/)).toBeInTheDocument();
    expect(screen.getByText(/子音（b、p、zh…）現在還量不到/)).toBeInTheDocument();
  });

  it("renders nothing when there is no per-syllable data to show", () => {
    // Older saved recordings and the no-Praat fallback carry no syllables;
    // an empty bordered panel would just look broken.
    const { container } = render(
      <PronunciationBreakdown words={[word({ syllables: [] })]} />,
    );
    expect(container.querySelector(".pronunciation-breakdown")).toBeNull();
  });
});
