import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import ModelRecordingPractice from "./ModelRecordingPractice";

describe("ModelRecordingPractice", () => {
  it("provides an offline sample with transcript, pinyin, meaning and playable audio", () => {
    render(<ModelRecordingPractice sceneIndex={0} modelSentence="請描述這張圖片。" />);

    expect(screen.getByText("姐姐在家裡做飯。")).toBeInTheDocument();
    expect(screen.getByText("Jiějie zài jiālǐ zuòfàn.")).toBeInTheDocument();
    expect(screen.getByText("Older sister is cooking at home.")).toBeInTheDocument();
    expect(screen.getByLabelText("Model recording: 姐姐在家裡做飯。")).toHaveAttribute(
      "src",
      "/uploads/examples/pic1_example.mp3",
    );
    expect(screen.getByText("請描述這張圖片。")).toBeInTheDocument();
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

  it("opens a record-and-analyze repeat drill for the displayed recording", async () => {
    const user = userEvent.setup();
    render(<ModelRecordingPractice sceneIndex={0} />);

    await user.click(screen.getByRole("button", { name: /Practice this model recording/ }));

    expect(screen.getByLabelText("Practice phrase 姐姐在家裡做飯。")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Record this part/ })).toBeInTheDocument();
  });
});
