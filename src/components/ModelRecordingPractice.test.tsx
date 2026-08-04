import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import ModelRecordingPractice from "./ModelRecordingPractice";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("ModelRecordingPractice", () => {
  it("shows the scene sentence once as the single source of truth when no scene audio exists", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("backend unreachable")));

    render(<ModelRecordingPractice sceneIndex={0} modelSentence="請描述這張圖片。" />);

    expect(screen.getAllByText("請描述這張圖片。")).toHaveLength(1);
    expect(screen.getAllByText("qǐng miáo shù zhè zhāng tú piàn 。").length).toBeGreaterThan(0);
    expect(
      await screen.findByText("The scene sentence is ready to repeat; a teacher recording is not available yet."),
    ).toBeInTheDocument();
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

  it("plays a backend-synthesized model recording through an <audio> tag instead of a speak button", async () => {
    const mp3Blob = new Blob(["fake-mp3"], { type: "audio/mpeg" });
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url.includes("/api/tts")) {
          expect(init?.method).toBe("POST");
          expect(JSON.parse(String(init?.body))).toEqual({ text: "請描述這張圖片。" });
          return { ok: true, blob: async () => mp3Blob };
        }
        return { ok: true, blob: async () => new Blob() };
      }),
    );
    vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:model-tts-audio");

    render(<ModelRecordingPractice sceneIndex={0} modelSentence="請描述這張圖片。" />);

    const audio = await screen.findByLabelText("Model recording: 請描述這張圖片。");
    expect(audio.tagName).toBe("AUDIO");
    expect(audio).toHaveAttribute("src", "blob:model-tts-audio");
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("loads the Praat pitch chart for a backend-synthesized model recording too, same as a teacher recording", async () => {
    const mp3Blob = new Blob(["fake-mp3"], { type: "audio/mpeg" });
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/api/tts")) {
          return { ok: true, blob: async () => mp3Blob };
        }
        if (url.includes("/api/analyze")) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              pitch_contour: [
                [0, 200],
                [0.2, 210],
              ],
              word_prosody: [],
            }),
          };
        }
        return { ok: true, blob: async () => new Blob(["fake-audio"], { type: "audio/wav" }) };
      }),
    );
    vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:model-tts-audio");

    render(<ModelRecordingPractice sceneIndex={0} modelSentence="請描述這張圖片。" />);

    const audio = await screen.findByLabelText("Model recording: 請描述這張圖片。");
    audio.dispatchEvent(new Event("play"));

    expect(
      await screen.findByRole("img", { name: /Praat style waveform/ }),
    ).toBeInTheDocument();
  });

  it("keeps the offline sample when there is no scene sentence at all", () => {
    render(<ModelRecordingPractice sceneIndex={0} />);

    expect(screen.getByText("姐姐在家裡做飯。")).toBeInTheDocument();
    expect(screen.getByLabelText("Model recording: 姐姐在家裡做飯。")).toHaveAttribute(
      "src",
      "/uploads/examples/pic1_example.mp3",
    );
  });

  it("has no separate practice button — pressing play on the model audio loads its Praat pitch chart", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/api/analyze")) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              pitch_contour: [
                [0, 200],
                [0.2, 210],
              ],
              word_prosody: [],
            }),
          };
        }
        return {
          ok: true,
          blob: async () => new Blob(["fake-audio"], { type: "audio/wav" }),
        };
      }),
    );

    render(
      <ModelRecordingPractice
        sceneIndex={2}
        modelSentence="我要去市場。"
        modelAudioUrl="/uploads/story_audio/market.wav"
      />,
    );

    expect(
      screen.queryByRole("button", { name: /Practice this model recording/ }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /pitch chart/i }),
    ).not.toBeInTheDocument();
    expect(globalThis.fetch).not.toHaveBeenCalled();

    const audio = screen.getByLabelText("Model recording: 我要去市場。");
    audio.dispatchEvent(new Event("play"));

    expect(globalThis.fetch).toHaveBeenCalledWith("/uploads/story_audio/market.wav");
    expect(
      await screen.findByRole("img", { name: /Praat style waveform/ }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/its pitch curve is what a full-score attempt looks like/),
    ).toBeInTheDocument();
  });
});
