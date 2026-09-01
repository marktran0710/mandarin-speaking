import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { UserEvent } from "@testing-library/user-event";
import StoryRecorder, { practiceSceneIndicesFor } from "./StoryRecorder";
import {
  TEST_BACKEND_URL,
  activeRecognition,
  activeRecorder,
  buildAnalyzeResponse,
  cleanupStoryRecorderTestEnvironment,
  jsonResponse,
  mockBackendAnalyze,
  resetStoryRecorderTestEnvironment,
  topic,
  topicWithQuizVocab,
} from "./StoryRecorder.test.helpers";

describe("StoryRecorder student prototype", () => {
  beforeEach(resetStoryRecorderTestEnvironment);
  afterEach(cleanupStoryRecorderTestEnvironment);
  it("treats every story frame as a required student scene", () => {
    expect(
      practiceSceneIndicesFor({
        images: ["teacher-example.png", "scene-one.png", "scene-two.png"],
      }),
    ).toEqual([0, 1, 2]);

    expect(
      practiceSceneIndicesFor({
        images: ["scene-one.png", "scene-two.png"],
      }),
    ).toEqual([0, 1]);
  });

  it("defaults to the recommended Groq Whisper API when it is available", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/api/ai-providers")) {
          return jsonResponse({
            providers: [{ id: "groq", label: "Groq", available: true }],
            default: "groq",
          });
        }
        return jsonResponse({});
      }),
    );

    const user = userEvent.setup();
    render(
      <StoryRecorder
        topic={topic}
        selectedImage={topic.images[0]}
        selectedImageIndex={0}
        onImageSelect={vi.fn()}
        onImageChange={vi.fn()}
        onAddRecord={vi.fn()}
      />,
    );

    await user.click(screen.getByRole("tab", { name: /Speaking/ }));
    await user.click(screen.getByText("Recording options"));

    await waitFor(() => {
      expect(screen.getByLabelText("Speech source")).toHaveValue("groq");
    });
    expect(
      screen.getByRole("option", { name: /Groq Whisper.*recommended free API/ }),
    ).toBeEnabled();
  });

  it("offers OpenAI Whisper as a speech source, enabled only when its API key is configured", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/api/ai-providers")) {
          return jsonResponse({
            providers: [
              { id: "groq", label: "Groq", available: false },
              { id: "openai", label: "ChatGPT (OpenAI)", available: true },
            ],
            default: "local",
          });
        }
        return jsonResponse({});
      }),
    );

    const user = userEvent.setup();
    render(
      <StoryRecorder
        topic={topic}
        selectedImage={topic.images[0]}
        selectedImageIndex={0}
        onImageSelect={vi.fn()}
        onImageChange={vi.fn()}
        onAddRecord={vi.fn()}
      />,
    );

    await user.click(screen.getByRole("tab", { name: /Speaking/ }));
    await user.click(screen.getByText("Recording options"));

    await waitFor(() => {
      expect(screen.getByRole("option", { name: /OpenAI Whisper — cloud API/ })).toBeEnabled();
    });
    expect(
      screen.getByRole("option", { name: /Groq Whisper.*unavailable/ }),
    ).toBeDisabled();
  });

  it("lets a student record their own attempt and receive word-level pronunciation feedback", async () => {
    const user = userEvent.setup();
    const onAddRecord = vi.fn();

    render(
      <StoryRecorder
        topic={topic}
        selectedImage={topic.images[0]}
        selectedImageIndex={0}
        onImageSelect={vi.fn()}
        onImageChange={vi.fn()}
        onAddRecord={onAddRecord}
      />,
    );

    // Scene 0 has vocabulary, so practice lands on the Vocabulary step first
    // — jump straight to Speaking via the tab bar.
    await user.click(screen.getByRole("tab", { name: /Speaking/ }));

    await user.click(screen.getByRole("button", { name: /Record$/ }));
    expect(activeRecorder?.state).toBe("recording");
    expect(activeRecognition?.lang).toBe("zh-TW");

    await user.click(screen.getByRole("button", { name: /Stop Recording$/ }));

    // Analysis lands on the guided results screen; failed per-word feedback
    // is one step deeper in the Practice panel.
    await waitFor(() => {
      expect(screen.getByRole("region", { name: "Recording results" })).toBeInTheDocument();
    });
    await user.click(screen.getByRole("button", { name: /Practice the words/ }));
    expect(screen.getByText("Pitch rises clearly.")).toBeInTheDocument();

    expect(globalThis.fetch).toHaveBeenCalledWith(
      `${TEST_BACKEND_URL}/api/analyze`,
      expect.objectContaining({ method: "POST" }),
    );
    expect(onAddRecord).toHaveBeenCalledWith(
      expect.objectContaining({
        transcription: "Student tells the market story",
        model: "webspeech",
        praatMetrics: expect.objectContaining({
          word_prosody: expect.any(Array),
        }),
      }),
    );
  });

  it("defaults live recording to browser Traditional Chinese transcription", async () => {
    const user = userEvent.setup();
    render(
      <StoryRecorder
        topic={topic}
        selectedImage={topic.images[0]}
        selectedImageIndex={0}
        onImageSelect={vi.fn()}
        onImageChange={vi.fn()}
        onAddRecord={vi.fn()}
      />,
    );

    // Scene 0 has vocabulary, so practice lands on the Vocabulary step first
    // — jump straight to Speaking via the tab bar.
    await user.click(screen.getByRole("tab", { name: /Speaking/ }));

    await user.click(screen.getByRole("button", { name: /Record$/ }));
    expect(activeRecognition?.lang).toBe("zh-TW");
    expect(activeRecorder?.state).toBe("recording");

    await user.click(screen.getByRole("button", { name: /Stop Recording$/ }));
    await screen.findByRole("region", { name: "Recording results" });
  });

  it("uses Chinese/Taiwanese Whisper when a student submits a voice file", async () => {
    const user = userEvent.setup();
    const onAddRecord = vi.fn();

    render(
      <StoryRecorder
        topic={topic}
        selectedImage={topic.images[0]}
        selectedImageIndex={0}
        onImageSelect={vi.fn()}
        onImageChange={vi.fn()}
        onAddRecord={onAddRecord}
      />,
    );

    // Scene 0 has vocabulary, so practice lands on the Vocabulary step first
    // — jump straight to Speaking via the tab bar.
    await user.click(screen.getByRole("tab", { name: /Speaking/ }));
    // Uploading with the webspeech default falls back to Groq (webspeech
    // itself can't transcribe a file) — pick ctwhisper explicitly.
    await user.click(screen.getByText("Recording options"));
    await user.selectOptions(screen.getByLabelText(/Speech source/), "ctwhisper");

    const voiceFile = new File(["RIFF....WAVEfmt "], "story-attempt.wav", {
      type: "audio/wav",
    });
    const input = document.querySelector(
      ".submit-voice-input",
    ) as HTMLInputElement;

    await user.upload(input, voiceFile);
    await user.click(await screen.findByRole("button", { name: /Analyze audio/i }));
    await screen.findByRole("region", { name: "Recording results" });

    expect(globalThis.fetch).toHaveBeenCalledWith(
      `${TEST_BACKEND_URL}/api/analyze`,
      expect.objectContaining({ method: "POST" }),
    );
    // Mount also fires a GET to /api/ai-providers, so find the /api/analyze
    // call by URL rather than assuming it's the first fetch.
    const analyzeCall = vi
      .mocked(globalThis.fetch)
      .mock.calls.find(([url]) => String(url).includes("/api/analyze"));
    const requestBody = analyzeCall?.[1]?.body as FormData;
    expect(requestBody.get("transcription")).toBe("");
    expect(requestBody.get("asr_model")).toBe("ctwhisper");
    expect(screen.queryByText(/story-attempt\.wav/)).not.toBeInTheDocument();
    expect(onAddRecord).toHaveBeenCalledWith(
      expect.objectContaining({
        transcription: "Student tells the market story",
        model: "ctwhisper",
      }),
    );
  });

  it("transcribes and analyzes a submitted student voice file with VibeVoice", async () => {
    const user = userEvent.setup();
    const onAddRecord = vi.fn();

    render(
      <StoryRecorder
        topic={topic}
        selectedImage={topic.images[0]}
        selectedImageIndex={0}
        onImageSelect={vi.fn()}
        onImageChange={vi.fn()}
        onAddRecord={onAddRecord}
      />,
    );

    // Scene 0 has vocabulary, so practice lands on the Vocabulary step first
    // — jump straight to Speaking via the tab bar.
    await user.click(screen.getByRole("tab", { name: /Speaking/ }));

    await user.click(screen.getByText("Recording options"));
    await user.selectOptions(screen.getByLabelText(/Speech source/), "vibevoice");

    const voiceFile = new File(["RIFF....WAVEfmt "], "story-attempt.wav", {
      type: "audio/wav",
    });
    const input = document.querySelector(
      ".submit-voice-input",
    ) as HTMLInputElement;

    await user.upload(input, voiceFile);
    await user.click(await screen.findByRole("button", { name: /Analyze audio/i }));
    await screen.findByRole("region", { name: "Recording results" });

    expect(globalThis.fetch).toHaveBeenCalledWith(
      `${TEST_BACKEND_URL}/api/analyze`,
      expect.objectContaining({ method: "POST" }),
    );
    // Mount also fires a GET to /api/ai-providers, so find the /api/analyze
    // call by URL rather than assuming it's the first fetch.
    const analyzeCall = vi
      .mocked(globalThis.fetch)
      .mock.calls.find(([url]) => String(url).includes("/api/analyze"));
    const requestBody = analyzeCall?.[1]?.body as FormData;
    expect(requestBody.get("transcription")).toBe("");
    expect(requestBody.get("asr_model")).toBe("vibevoice");
    expect(screen.queryByText(/story-attempt\.wav/)).not.toBeInTheDocument();
    expect(
      (await screen.findAllByText("Student tells the market story")).length,
    ).toBeGreaterThan(0);
    expect(onAddRecord).toHaveBeenCalledWith(
      expect.objectContaining({
        transcription: "Student tells the market story",
        model: "vibevoice",
      }),
    );
  });

});
