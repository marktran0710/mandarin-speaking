import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ScenePracticeWord from "./ScenePracticeWord";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ScenePracticeWord", () => {
  it("renders one listening action for a word with a model clip", () => {
    render(<ScenePracticeWord word="水" audioUrl="/audio/shui.wav" />);

    expect(
      screen.getByRole("button", {
        name: "Listen to the model pronunciation of 水",
      }),
    ).toHaveAttribute("title", "Listen to this word");
    expect(screen.queryByRole("button", { name: /Record/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Practice/i })).not.toBeInTheDocument();
  });

  it("plays and stops the model clip from the same button", async () => {
    const play = vi
      .spyOn(HTMLMediaElement.prototype, "play")
      .mockResolvedValue(undefined);
    const pause = vi
      .spyOn(HTMLMediaElement.prototype, "pause")
      .mockImplementation(() => undefined);
    const user = userEvent.setup();

    render(<ScenePracticeWord word="水" audioUrl="/audio/shui.wav" />);
    pause.mockClear();
    const listen = screen.getByRole("button", {
      name: "Listen to the model pronunciation of 水",
    });

    await user.click(listen);
    expect(play).toHaveBeenCalledTimes(1);

    const audio = document.querySelector(".scene-practice-audio") as HTMLAudioElement;
    Object.defineProperty(audio, "paused", { configurable: true, value: false });
    await user.click(listen);
    expect(pause).toHaveBeenCalledTimes(1);

    Object.defineProperty(audio, "paused", { configurable: true, value: true });
    play.mockRestore();
    pause.mockRestore();
  });

  it("falls back to browser pronunciation when a model clip is unavailable", async () => {
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

    render(<ScenePracticeWord word="水" />);

    const listen = screen.getByRole("button", {
      name: "Listen to the model pronunciation of 水",
    });
    expect(listen).not.toBeDisabled();
    expect(screen.queryByRole("button", { name: /Record/i })).not.toBeInTheDocument();

    await user.click(listen);
    expect(utterance).toHaveBeenCalledWith("水");
    expect(speak).toHaveBeenCalledTimes(1);
  });

  it("keeps the action disabled when neither audio source is available", () => {
    render(<ScenePracticeWord word="水" />);

    expect(
      screen.getByRole("button", {
        name: "Listen to the model pronunciation of 水",
      }),
    ).toBeDisabled();
  });
});
