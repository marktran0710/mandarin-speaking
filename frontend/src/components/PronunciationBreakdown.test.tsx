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

describe("PronunciationBreakdown", () => {
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
    // Neutral tone is counted apart from uncertainty — nobody measured it, so
    // folding it into "not clear" would imply doubt about the learner.
    expect(summary).toContain("1個輕聲不計");
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
    expect(summary).toContain("1個未計入");
    expect(summary).not.toContain("1個聽不太出來");
    expect(summary).toContain("1/1個計入過關");
  });

  it("keeps the collapsed row short and puts the explanation behind a tap", async () => {
    const user = userEvent.setup();
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

    const row = characterRows()[0];
    expect(row.getAttribute("aria-expanded")).toBe("false");
    // The long bilingual status label used to sit on every row; it now lives
    // in the legend and the detail.
    expect(row.textContent).not.toContain("調型有點接近");
    expect(container.querySelector(".pb-detail")).toBeNull();

    await user.click(row);

    expect(row.getAttribute("aria-expanded")).toBe("true");
    const detail = container.querySelector(".pb-detail")!;
    expect(detail.textContent).toContain("聽不太出來");
    expect(detail.textContent).toContain("調型有點接近");

    await user.click(row);
    expect(container.querySelector(".pb-detail")).toBeNull();
  });

  it("explains the tone rule that changed the target, on demand", async () => {
    const user = userEvent.setup();
    const sandhi = word({
      token: "很好",
      diagnostic_status: "CORRECT",
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
    const { container } = render(<PronunciationBreakdown words={[sandhi]} />);

    await user.click(characterRows()[0]);
    expect(container.querySelector(".pb-detail-rule")!.textContent).toContain(
      "三聲變調",
    );
  });

  it("marks an uncertain syllable without the error field", () => {
    // The bug that started this: a contour match of 53 against the correct
    // tone was rendered as ✗ on a red field. Low match means the system could
    // not tell, not that the learner was wrong.
    const uncertain = word({
      passed: false,
      diagnostic_status: "UNCERTAIN",
      syllables: [
        { ...passingWord.syllables![0], passed: false, diagnostic_status: "UNCERTAIN" },
      ],
    });
    render(<PronunciationBreakdown words={[uncertain]} />);

    const row = characterRows()[0];
    expect(row.querySelector(".pb-tone-mark")!.textContent).toBe("△");
    expect(row.classList.contains("pb-row-failed")).toBe(false);
  });

  it("only paints the error field for a confident INCORRECT", () => {
    const incorrect = word({
      passed: false,
      diagnostic_status: "INCORRECT",
      syllables: [
        { ...passingWord.syllables![0], passed: false, diagnostic_status: "INCORRECT" },
      ],
    });
    render(<PronunciationBreakdown words={[incorrect]} />);

    const row = characterRows()[0];
    expect(row.querySelector(".pb-tone-mark")!.textContent).toBe("✗");
    expect(row.classList.contains("pb-row-failed")).toBe(true);
  });

  it("asks for a new recording rather than blaming the learner", () => {
    const invalid = word({
      diagnostic_status: "INVALID_AUDIO",
      syllables: [
        {
          ...passingWord.syllables![0],
          passed: false,
          diagnostic_status: "INVALID_AUDIO",
          contour_match_score: null,
        },
      ],
    });
    render(<PronunciationBreakdown words={[invalid]} />);

    const row = characterRows()[0];
    expect(row.querySelector(".pb-tone-mark")!.textContent).toBe("↻");
    expect(row.classList.contains("pb-row-failed")).toBe(false);
  });

  it("says neutral tone was not scored, rather than calling it uncertain", async () => {
    const user = userEvent.setup();
    const neutral = word({
      token: "什麼",
      diagnostic_status: "UNCERTAIN",
      syllables: [
        {
          char: "麼",
          tone: 5,
          score: 75,
          passed: true,
          diagnostic_status: "UNCERTAIN",
          diagnostic_reason: "neutral_tone_has_no_contour_target",
          contour_match_score: null,
          score_provenance: "neutral_not_measured",
          underlying_tone: 5,
          accepted_surface_tones: [5],
        },
      ],
    });
    const { container } = render(<PronunciationBreakdown words={[neutral]} />);

    await user.click(characterRows()[0]);
    const detail = container.querySelector(".pb-detail")!;
    expect(detail.textContent).toContain("不另外評分");
    expect(detail.textContent).toContain("Neutral tone");
    expect(detail.textContent).not.toContain("聽不太出來");
    expect(container.textContent).not.toContain("75");
  });

  it("never turns an unmeasurable vowel into a verdict", async () => {
    // 吃 holds the apical -i, which is not the vowel /i/ and has no target to
    // measure against. A blank must read as "not measured", never as "wrong".
    const user = userEvent.setup();
    const chifan = word({
      token: "吃飯",
      syllables: [
        {
          char: "吃",
          tone: 1,
          score: 80,
          passed: true,
          diagnostic_status: "CORRECT",
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
          diagnostic_status: "CORRECT",
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

    // The gliding final shows its reading compactly, with the caveat as a
    // marker rather than a sentence repeated down the column.
    const rows = characterRows();
    expect(rows[1].textContent).toContain("嘴型 大・中");
    expect(rows[1].querySelector(".pb-vowel-glide")!.getAttribute("title")).toMatch(
      /只量中間/,
    );

    await user.click(rows[1]);
    expect(container.querySelector(".pb-detail")!.textContent).toContain(
      "mouth open",
    );
  });

  it("hides the raw contour number from learners and shows it in debug", async () => {
    // 53 is a heuristic contour match, not a probability and not a score out
    // of 100. Putting it in front of a learner invites exactly that reading.
    const user = userEvent.setup();
    const item = word({
      diagnostic_status: "UNCERTAIN",
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
    await user.click(learner.container.querySelector(".pb-row") as HTMLElement);
    expect(learner.container.textContent).not.toMatch(/53/);
    expect(learner.container.textContent).not.toMatch(/confidence|probability/i);
    learner.unmount();

    const debug = render(<PronunciationBreakdown words={[item]} debug />);
    await user.click(debug.container.querySelector(".pb-row") as HTMLElement);
    expect(debug.container.textContent).toMatch(/Contour match: 53\/100/);
    expect(debug.container.textContent).toMatch(/legacy gate: FAIL/);
  });

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
