import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ConversationTurn } from "@entities/conversation";
import { studentUiCopy } from "../../i18n/student-ui-copy";
import ConversationHistoryTurn from "./ConversationHistoryTurn";

const turn: ConversationTurn = {
  id: "system-1",
  speaker: "system",
  text: "你好嗎？",
  translation: "How are you?",
};

describe("ConversationHistoryTurn", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("keeps the role marker in the shared header and omits it for grouped middle turns", () => {
    const { container, rerender } = render(
      <ConversationHistoryTurn turn={turn} showRoleHeader />,
    );

    expect(container.querySelectorAll("[data-role-header]")).toHaveLength(1);
    expect(container.querySelector("[data-role-header] .sa-conversation__mascot")).toBeInTheDocument();
    expect(container.querySelector(".sa-bubble .sa-conversation__mascot")).toBeNull();
    expect(container.querySelector("[data-role-header] .sa-bubble-row__dot")).toBeInTheDocument();

    rerender(<ConversationHistoryTurn turn={turn} showRoleHeader={false} />);

    expect(container.querySelector("[data-role-header]")).toBeNull();
    expect(container.querySelector(".sa-bubble")).toBeInTheDocument();
  });

  it("replays the submitted student recording instead of the authored model audio", () => {
    const play = vi.fn().mockResolvedValue(undefined);
    const constructedUrls: string[] = [];
    class AudioMock {
      duration = Number.NaN;
      play = play;

      constructor(url: string) {
        constructedUrls.push(url);
      }

      addEventListener() {}
    }
    vi.stubGlobal("Audio", AudioMock);

    render(
      <ConversationHistoryTurn
        turn={{
          id: "student-1",
          speaker: "student",
          text: "我要在家看書、聽音樂。",
          targetAudioUrl: "/uploads/audio/model-sample.mp3",
        }}
        studentAudioUrl="/uploads/audio/submitted-answer.wav"
        showRoleHeader
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: studentUiCopy.replayAnswer.zh }));

    expect(constructedUrls).toEqual(["/uploads/audio/submitted-answer.wav"]);
    expect(constructedUrls).not.toContain("/uploads/audio/model-sample.mp3");
  });

  it("does not present model audio as a replay when no student recording is available", () => {
    render(
      <ConversationHistoryTurn
        turn={{
          id: "student-1",
          speaker: "student",
          text: "我要在家看書、聽音樂。",
          targetAudioUrl: "/uploads/audio/model-sample.mp3",
        }}
        showRoleHeader
      />,
    );

    expect(screen.queryByRole("button", { name: studentUiCopy.replayAnswer.zh })).not.toBeInTheDocument();
  });
});
