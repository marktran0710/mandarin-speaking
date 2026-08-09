import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import PronunciationBreakdown from "./PronunciationBreakdown";
import type { WordProsody } from "./StoryRecorder";

/**
 * The panel exists to answer "did the app even listen?" — so the tests that
 * matter are about what it shows when nothing is wrong, and about keeping the
 * vowel column from reading as a score it isn't.
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
  syllables: [
    {
      char: "你",
      tone: 3,
      score: 88,
      passed: true,
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

describe("PronunciationBreakdown", () => {
  /** Character rows only — skips the header row and the per-word group rows. */
  function characterRows() {
    return screen
      .getAllByRole("row")
      .filter((row) => row.querySelector(".pb-char-cell"));
  }

  it("shows every character even when the whole attempt passed", () => {
    // The regression this whole panel was built for: the old flow only ever
    // rendered the breakdown for *failed* words, inside a later step, so a
    // student who read the sentence well saw no analysis at all.
    render(<PronunciationBreakdown words={[passingWord]} />);

    const rows = characterRows();
    expect(rows).toHaveLength(2);
    expect(within(rows[0]).getByText("你")).toBeInTheDocument();
    expect(within(rows[1]).getByText("媽")).toBeInTheDocument();
    // The raw contour number is deliberately absent from the learner view.
    expect(within(rows[0]).queryByText("88%")).toBeNull();
  });

  it("groups the characters under the word they belong to", () => {
    // Phrases are the unit the practice list already drills, so the readout
    // is grouped the same way rather than as a flat run of characters.
    const { container } = render(
      <PronunciationBreakdown
        words={[
          passingWord,
          word({
            token: "這個",
            index: 1,
            passed: false,
            shape_accuracy: 56,
            syllables: [
              { char: "這", tone: 4, score: 94, passed: true, vowel_status: "no_formants" },
              { char: "個", tone: 4, score: 56, passed: false, vowel_status: "no_formants" },
            ],
          }),
        ]}
      />,
    );

    const groups = container.querySelectorAll(".pb-group");
    expect(groups).toHaveLength(2);
    expect(groups[0].querySelector(".pb-group-token")!.textContent).toBe("你媽");
    expect(groups[1].querySelector(".pb-group-token")!.textContent).toBe("這個");
    // Each group carries the whole word's own verdict — the same one that
    // decides whether the word lands in the practice list.
    expect(groups[1].querySelector(".pb-group-verdict")!.textContent).toBe("✗");
    // No word-level percentage: the word score is a whole-word shape read and
    // the syllable scores are directional, so printing both invited the
    // reader to compare two numbers that legitimately disagree.
    expect(groups[1].querySelector(".pb-group-score")).toBeNull();
    expect(groups[0].querySelectorAll(".pb-char-cell")).toHaveLength(2);
  });

  it("shows △ for an uncertain syllable and never a red error", () => {
    // The bug that started this: a contour match of 53 against the correct
    // tone was rendered as ✗ on a red field. Low match means the system could
    // not tell, not that the learner was wrong.
    const uncertain = word({
      passed: false,
      diagnostic_status: "UNCERTAIN",
      syllables: [
        {
          ...passingWord.syllables![0],
          score: 53,
          passed: false,
          diagnostic_status: "UNCERTAIN",
          diagnostic_reason: "contour_match_inconclusive",
          contour_match_score: 53,
        },
      ],
    });
    const { container } = render(<PronunciationBreakdown words={[uncertain]} />);

    const toneCell = container.querySelector(".pb-tone-cell")!;
    expect(toneCell.querySelector(".pb-tone-mark")!.textContent).toBe("△");
    expect(toneCell.textContent).not.toContain("✗");
    expect(container.querySelector(".pb-tone-failed")).toBeNull();
    expect(toneCell.textContent).toContain("聽不太出來");
  });

  it("only paints the error field for a confident INCORRECT", () => {
    const incorrect = word({
      passed: false,
      diagnostic_status: "INCORRECT",
      syllables: [
        {
          ...passingWord.syllables![0],
          score: 20,
          passed: false,
          diagnostic_status: "INCORRECT",
          diagnostic_reason: "contour_contradicts_expected_tone",
          contour_match_score: 20,
        },
      ],
    });
    const { container } = render(<PronunciationBreakdown words={[incorrect]} />);
    const toneCell = container.querySelector(".pb-tone-cell")!;
    expect(toneCell.querySelector(".pb-tone-mark")!.textContent).toBe("✗");
    expect(container.querySelector(".pb-tone-failed")).not.toBeNull();
  });

  it("asks for a new recording rather than blaming the learner", () => {
    const invalid = word({
      diagnostic_status: "INVALID_AUDIO",
      syllables: [
        {
          ...passingWord.syllables![0],
          passed: false,
          diagnostic_status: "INVALID_AUDIO",
          diagnostic_reason: "recording_quality_unusable",
          contour_match_score: null,
        },
      ],
    });
    const { container } = render(<PronunciationBreakdown words={[invalid]} />);
    const toneCell = container.querySelector(".pb-tone-cell")!;
    expect(toneCell.querySelector(".pb-tone-mark")!.textContent).toBe("↻");
    expect(container.querySelector(".pb-tone-failed")).toBeNull();
  });

  it("hides the raw contour number from learners and shows it in debug", () => {
    // 53 is a heuristic contour match, not a probability and not a score out
    // of 100. Putting it in front of a learner invites exactly that reading.
    const item = word({
      syllables: [
        {
          ...passingWord.syllables![0],
          score: 53,
          passed: false,
          diagnostic_status: "UNCERTAIN",
          diagnostic_reason: "contour_match_inconclusive",
          contour_match_score: 53,
          score_provenance: "measured",
          legacy: { passed: false, score: 53, threshold: 58 },
        },
      ],
    });

    const learner = render(<PronunciationBreakdown words={[item]} />);
    expect(learner.container.textContent).not.toMatch(/53/);
    expect(learner.container.textContent).not.toMatch(/confidence|probability/i);
    learner.unmount();

    const debug = render(<PronunciationBreakdown words={[item]} debug />);
    expect(debug.container.textContent).toMatch(/Contour match: 53\/100/);
    expect(debug.container.textContent).toMatch(/legacy gate: FAIL/);
  });

  it("explains the contextual tone rule that changed the target", () => {
    const sandhi = word({
      token: "很好",
      syllables: [
        {
          char: "很",
          tone: 2,
          score: 70,
          passed: true,
          diagnostic_status: "CORRECT",
          diagnostic_reason: "contour_matches_expected_tone",
          underlying_tone: 3,
          accepted_surface_tones: [2],
          context_rule: "T3_T3",
        },
      ],
    });
    render(<PronunciationBreakdown words={[sandhi]} />);
    expect(screen.getByText(/三聲變調/)).toBeInTheDocument();
  });

  it("marks a failed syllable on the tone column only", () => {
    const failing = word({
      passed: false,
      syllables: [
        {
          ...passingWord.syllables![0],
          score: 31,
          passed: false,
        },
        passingWord.syllables![1],
      ],
    });
    const { container } = render(<PronunciationBreakdown words={[failing]} />);

    const rows = characterRows();
    expect(within(rows[0]).getByText("✗")).toBeInTheDocument();
    expect(within(rows[1]).getByText("✓")).toBeInTheDocument();

    // The failed tint stays inside the tone cell. Tinting the whole row would
    // drag the vowel column into a verdict it explicitly does not make.
    expect(rows[0].className).not.toContain("failed");
    expect(rows[0].querySelector(".pb-tone-cell.pb-tone-failed")).not.toBeNull();
    expect(rows[0].querySelector(".pb-vowel-cell.pb-tone-failed")).toBeNull();

    // And the vowel column carries no verdict marks of its own.
    expect(container.querySelectorAll(".pb-vowel .is-fail")).toHaveLength(0);
    expect(container.querySelectorAll(".pb-vowel .is-pass")).toHaveLength(0);
  });

  it("never turns an unmeasurable vowel into a verdict", () => {
    // 吃 holds the apical -i, which is not the vowel /i/ and has no target to
    // measure against. A blank here must read as "not measured", never as
    // "wrong" — a dash with the reason attached, and no tick or cross.
    const chifan = word({
      token: "吃飯",
      syllables: [
        {
          char: "吃",
          tone: 1,
          score: 80,
          passed: true,
          expected_vowel: null,
          expected_zone: null,
          measured_zone: null,
          vowel_status: "not_applicable",
        },
        {
          char: "飯",
          tone: 4,
          score: 75,
          passed: true,
          expected_vowel: "a",
          expected_zone: { height: "low", backness: "central" },
          final: "an",
          f1: 800,
          f2: 1400,
          measured_zone: { height: "low", backness: "central" },
          vowel_status: "nucleus_only",
        },
      ],
    });
    const { container } = render(<PronunciationBreakdown words={[chifan]} />);

    const dash = container.querySelector(".pb-vowel--none")!;
    expect(dash.textContent).toBe("—");
    expect(dash.getAttribute("title")).toMatch(/沒有單獨的母音/);

    // A gliding final still reports its measurement, and says so — as a
    // marker rather than a sentence, since most finals glide and repeating it
    // down the column drowns out the readings themselves.
    const glide = container.querySelector(".pb-vowel-glide")!;
    expect(glide.textContent).toBe("~");
    expect(glide.getAttribute("title")).toMatch(/只量中間/);
    expect(screen.getByText(/mouth open/)).toBeInTheDocument();
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
