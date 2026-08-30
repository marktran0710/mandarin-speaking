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

describe("PronunciationBreakdown: structure and summary", () => {
  it("shows every character even when the whole attempt passed", () => {
    // The regression this panel was built for: the old flow only rendered a
    // breakdown for *failed* words, inside a later step, so a student who read
    // the sentence well saw no analysis at all.
    render(<PronunciationBreakdown words={[passingWord]} />);

    const rows = characterRows();
    expect(rows).toHaveLength(2);
    expect(within(rows[0]).getByText("你")).toBeInTheDocument();
    expect(within(rows[1]).getByText("媽")).toBeInTheDocument();
  });

  it("renders the target character when ASR uses a homophone", () => {
    const { container } = render(
      <PronunciationBreakdown
        words={[word({
          token: "她",
          syllables: [{ char: "她", tone: 1, score: 88, passed: true, diagnostic_status: "CORRECT" }],
        })]}
        targetText="他"
        transcription="她"
      />,
    );

    expect(container.querySelector(".pb-group-token")?.textContent).toBe("他");
    expect(within(characterRows()[0]).getByText("他")).toBeInTheDocument();
    expect(within(characterRows()[0]).queryByText("她")).not.toBeInTheDocument();
  });

  it("groups the characters under the word they belong to", () => {
    const { container } = render(
      <PronunciationBreakdown
        words={[
          passingWord,
          word({
            token: "這個",
            index: 1,
            passed: false,
            diagnostic_status: "UNCERTAIN",
            syllables: [
              { char: "這", tone: 4, score: 94, passed: true, diagnostic_status: "CORRECT" },
              { char: "個", tone: 4, score: 56, passed: false, diagnostic_status: "UNCERTAIN" },
            ],
          }),
        ]}
      />,
    );

    const groups = container.querySelectorAll(".pb-group");
    expect(groups).toHaveLength(2);
    expect(groups[0].querySelector(".pb-group-token")!.textContent).toBe("你媽");
    expect(groups[1].querySelector(".pb-group-token")!.textContent).toBe("這個");
    expect(groups[0].querySelectorAll(".pb-row")).toHaveLength(2);
  });

  it("uses teacher phrases as the outer groups while keeping words inside", () => {
    const { container } = render(
      <PronunciationBreakdown
        words={[
          word({ token: "alpha", index: 0, syllables: passingWord.syllables }),
          word({ token: "beta", index: 1, syllables: passingWord.syllables }),
        ]}
        targetText="alpha，beta"
        transcription="alpha beta"
        teacherPhrases={["alpha", "beta"]}
      />,
    );

    const phrases = container.querySelectorAll(".pb-phrase-group");
    expect(phrases).toHaveLength(2);
    expect(phrases[0].querySelector(".pb-phrase-label")?.textContent).toBe("alpha");
    expect(phrases[1].querySelector(".pb-phrase-label")?.textContent).toBe("beta");
    expect(phrases[0].querySelectorAll(".pb-group")).toHaveLength(1);
    expect(phrases[1].querySelectorAll(".pb-group")).toHaveLength(1);
  });

  it("only marks a phrase group red when it contains a confident X", () => {
    const { container } = render(
      <PronunciationBreakdown
        words={[
          word({
            token: "alpha",
            index: 0,
            passed: false,
            diagnostic_status: "INCORRECT",
            syllables: [
              { char: "a", tone: 4, score: 20, passed: false, diagnostic_status: "INCORRECT" },
            ],
          }),
          word({
            token: "beta",
            index: 1,
            passed: false,
            diagnostic_status: "UNCERTAIN",
            syllables: [
              { char: "b", tone: 3, score: 50, passed: false, diagnostic_status: "UNCERTAIN" },
            ],
          }),
        ]}
        targetText="alpha beta"
        transcription="alpha beta"
        teacherPhrases={["alpha", "beta"]}
      />,
    );

    const phrases = container.querySelectorAll(".pb-phrase-group");
    expect(phrases).toHaveLength(2);
    expect(phrases[0].classList.contains("has-fail")).toBe(true);
    expect(phrases[0].classList.contains("is-needs-practice")).toBe(true);
    expect(phrases[1].classList.contains("has-fail")).toBe(false);
  });

  it("counts the result in one summary line", () => {
    const { container } = render(
      <PronunciationBreakdown
        words={[
          word({
            token: "什麼要",
            syllables: [
              { char: "什", tone: 2, score: 37, passed: false, diagnostic_status: "INCORRECT" },
              {
                char: "麼",
                tone: 5,
                score: 75,
                passed: true,
                diagnostic_status: "UNCERTAIN",
                score_provenance: "neutral_not_measured",
              },
              { char: "要", tone: 4, score: 51, passed: false, diagnostic_status: "UNCERTAIN" },
            ],
          }),
        ]}
      />,
    );

    const summary = container.querySelector(".pb-summary")!.textContent!;
    expect(summary).toContain("1個要練");
    expect(summary).toContain("1個聽不太出來");
    // Neutral tone remains accounting metadata, not a fifth learner-facing verdict.
    expect(summary).not.toContain("輕聲不計");
    expect(container.querySelector(".pb-head-meta")!.textContent).toContain("1輕聲不計");
    expect(summary).not.toContain("個對了");
  });

  it("separates unjudged rows and shows the backend progression count", () => {
    const { container } = render(
      <PronunciationBreakdown
        words={[word({
          syllables: [
            { char: "你", tone: 3, score: 0, passed: null, diagnostic_status: "UNCERTAIN", score_provenance: "not_scored" },
            { char: "好", tone: 3, score: 88, passed: true, diagnostic_status: "CORRECT" },
          ],
        })]}
        masteryCounts={{ passed: 1, total: 1 }}
      />,
    );

    const summary = container.querySelector(".pb-summary")!.textContent!;
    expect(summary).toContain("1個要再錄");
    expect(summary).not.toContain("1個聽不太出來");
    expect(container.querySelector(".pb-head-meta")!.textContent).toContain("1未計入");
    expect(container.querySelectorAll(".pb-tone-mark.is-retry .app-icon")).toHaveLength(1);
    expect(container.querySelector(".pb-head-score")!.textContent).toContain("1/1");
  });

  it("treats legacy T5 rows as neutral when provenance is missing", () => {
    const { container } = render(
      <PronunciationBreakdown
        words={[word({
          token: "嗎",
          syllables: [
            { char: "嗎", tone: 5, score: 75, passed: null, diagnostic_status: "UNCERTAIN" },
          ],
        })]}
      />,
    );

    expect(container.querySelector(".pb-summary")).toBeNull();
    expect(container.querySelector(".pb-head-meta")!.textContent).toContain("1輕聲不計");
    expect(container.querySelector(".pb-tone-mark.is-not-measured .app-icon")).toBeInTheDocument();
  });

});
