import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { ConversationTurn } from "@entities/conversation";
import ConversationHistoryTurn from "./ConversationHistoryTurn";

const turn: ConversationTurn = {
  id: "system-1",
  speaker: "system",
  text: "你好嗎？",
  translation: "How are you?",
};

describe("ConversationHistoryTurn", () => {
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
});
