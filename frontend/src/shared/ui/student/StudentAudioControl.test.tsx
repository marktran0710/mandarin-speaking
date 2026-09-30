import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import StudentAudioControl from "./StudentAudioControl";

function stubAudio(play: () => Promise<void>) {
  const created: string[] = [];
  vi.stubGlobal(
    "Audio",
    class {
      constructor(url: string) {
        created.push(url);
      }
      addEventListener() {}
      play = play;
    },
  );
  return created;
}

afterEach(() => vi.unstubAllGlobals());

describe("StudentAudioControl", () => {
  it("is disabled and says so when there is no audio url", () => {
    render(<StudentAudioControl audioUrl="" />);
    expect(screen.getByRole("button", { name: "沒有音訊" })).toBeDisabled();
  });

  it("plays the clip when it loads", async () => {
    const created = stubAudio(() => Promise.resolve());
    render(<StudentAudioControl audioUrl="/uploads/audio/a.mp3" />);
    fireEvent.click(screen.getByRole("button", { name: "聆聽" }));
    await waitFor(() => expect(created).toEqual(["/uploads/audio/a.mp3"]));
    expect(screen.queryByText("不能播放")).toBeNull();
  });

  it("shows a visible error instead of failing silently, and retries with a fresh request", async () => {
    const created = stubAudio(() => Promise.reject(new Error("403")));
    render(<StudentAudioControl audioUrl="/uploads/audio/a.mp3" />);
    fireEvent.click(screen.getByRole("button", { name: "聆聽" }));

    const button = await screen.findByRole("button", { name: "不能播放" });
    expect(button).toBeEnabled();
    expect(button.className).toContain("is-error");

    fireEvent.click(button);
    await waitFor(() => expect(created).toHaveLength(2));
  });
});
