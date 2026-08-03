import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import ModelRecordingPractice from "./ModelRecordingPractice";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ModelRecordingPractice", () => {
  it("uses the scene target as the single source of truth when no scene audio exists", () => {
    render(<ModelRecordingPractice sceneIndex={0} modelSentence="請描述這張圖片。" />);

    expect(screen.getAllByText("請描述這張圖片。")).toHaveLength(2);
    expect(screen.getAllByText("qǐng miáo shù zhè zhāng tú piàn 。").length).toBeGreaterThan(0);
    expect(screen.getByText("The scene sentence is ready to repeat; a teacher recording is not available yet.")).toBeInTheDocument();
    expect(screen.queryByText("姐姐在家裡做飯。")).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/Model recording:/)).not.toBeInTheDocument();
  });

  it("uses a teacher scene recording when one is available", () => {
    render(
      <ModelRecordingPractice
        sceneIndex={2}
        modelSentence="我要去市場。"
        modelAudioUrl="/uploads/story_audio/market.wav"
      />,
    );

    expect(screen.getByLabelText("Model recording: 我要去市場。")).toHaveAttribute(
      "src",
      "/uploads/story_audio/market.wav",
    );
    expect(screen.queryByText("Older sister is cooking at home.")).not.toBeInTheDocument();
  });

  it("speaks the scene target instead of inventing a fallback recording", async () => {
    const speak = vi.fn();
    const cancel = vi.fn();
    class MockUtterance {
      lang = "";
      onend = () => undefined;
      onerror = () => undefined;
      constructor(public text: string) {}
    }
    const utterance = vi.fn(MockUtterance);
    vi.stubGlobal("speechSynthesis", { speak, cancel });
    vi.stubGlobal("SpeechSynthesisUtterance", utterance);
    const user = userEvent.setup();

    render(<ModelRecordingPractice sceneIndex={0} modelSentence="請描述這張圖片。" />);
    await user.click(screen.getByRole("button", { name: "Listen to scene sentence" }));

    expect(utterance).toHaveBeenCalledWith("請描述這張圖片。");
    expect(speak).toHaveBeenCalledTimes(1);
  });

  it("keeps the offline sample when there is no scene sentence at all", () => {
    render(<ModelRecordingPractice sceneIndex={0} />);

    expect(screen.getByText("姐姐在家裡做飯。")).toBeInTheDocument();
    expect(screen.getByLabelText("Model recording: 姐姐在家裡做飯。")).toHaveAttribute(
      "src",
      "/uploads/examples/pic1_example.mp3",
    );
  });

  it("opens a record-and-analyze repeat drill for the displayed recording", async () => {
    const user = userEvent.setup();
    render(<ModelRecordingPractice sceneIndex={0} />);

    await user.click(screen.getByRole("button", { name: /Practice this model recording/ }));

    expect(screen.getByLabelText("Practice phrase 姐姐在家裡做飯。")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Record this part/ })).toBeInTheDocument();
  });
});
