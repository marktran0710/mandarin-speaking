import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ScenePracticeWord from "./ScenePracticeWord";
import { useWordPronunciationPractice } from "../hooks/useWordPronunciationPractice";
import type { WordAnalyzeResult } from "../hooks/useWordPronunciationPractice";

vi.mock("../hooks/useWordPronunciationPractice");

const mockedHook = vi.mocked(useWordPronunciationPractice);

function baseHookReturn(result: WordAnalyzeResult | null) {
  return {
    isRecording: false,
    isAnalyzing: false,
    error: "",
    setError: vi.fn(),
    result,
    startRecording: vi.fn(),
    stopRecording: vi.fn(),
    analyzeBlob: vi.fn(),
    reset: vi.fn(),
  };
}

const segment = {
  token: "水",
  pitch_contour: [[0, 180]] as Array<[number, number]>,
  reference_contour: [[0, 180]] as Array<[number, number]>,
  tone_accuracy: 82,
  feedback: "Good match for Tone 3 (dip).",
};

async function expandPanel(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("button", { name: /Practice pronouncing 水/ }));
}

describe("ScenePracticeWord content verification", () => {
  it("shows the recognized script alongside the score when it matches the target word", async () => {
    mockedHook.mockReturnValue(
      baseHookReturn({
        tone_accuracy: 82,
        feedback: "Good match.",
        word_prosody: [segment],
        recognized_text: "水",
        content_match: true,
      }),
    );
    const user = userEvent.setup();
    render(<ScenePracticeWord word="水" />);

    await expandPanel(user);

    const recognized = screen.getByText("水", { selector: "strong" });
    expect(recognized.closest(".scene-practice-recognized")).toHaveClass("match");
    expect(screen.queryByText(/doesn't match/i)).not.toBeInTheDocument();
  });

  it("flags a mismatch note when the recognized script doesn't match the target word", async () => {
    mockedHook.mockReturnValue(
      baseHookReturn({
        tone_accuracy: 82,
        feedback: "Good match.",
        word_prosody: [segment],
        recognized_text: "税",
        content_match: false,
      }),
    );
    const user = userEvent.setup();
    render(<ScenePracticeWord word="水" />);

    await expandPanel(user);

    const recognized = screen.getByText("税", { selector: "strong" });
    expect(recognized.closest(".scene-practice-recognized")).toHaveClass("mismatch");
    expect(screen.getByText(/doesn't match "水"/i)).toBeInTheDocument();
  });

  it("shows no recognized-script row when the backend didn't run verification", async () => {
    mockedHook.mockReturnValue(
      baseHookReturn({
        tone_accuracy: 82,
        feedback: "Good match.",
        word_prosody: [segment],
        recognized_text: null,
        content_match: null,
      }),
    );
    const user = userEvent.setup();
    render(<ScenePracticeWord word="水" />);

    await expandPanel(user);

    expect(await screen.findByText("Good match for Tone 3 (dip).")).toBeInTheDocument();
    expect(document.querySelector(".scene-practice-recognized")).not.toBeInTheDocument();
  });
});
