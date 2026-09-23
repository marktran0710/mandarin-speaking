import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import ConversationTurnProgress from "./ConversationTurnProgress";
import type { ConversationTurn } from "./StoryRecorder/conversation";
import type { ConversationState } from "./StoryRecorder/conversationCoordinator";

// 4 exchanges = 8 raw system/student turns.
const turns: ConversationTurn[] = Array.from({ length: 8 }, (_, index) => ({
  id: `turn-${index}`,
  speaker: index % 2 === 0 ? "system" : "student",
  text: `text ${index}`,
}));

describe("ConversationTurnProgress", () => {
  it("labels the first exchange, not the first raw turn", () => {
    const state: ConversationState = { turnIndex: 0, step: "system" };
    render(<ConversationTurnProgress turns={turns} state={state} />);
    expect(screen.getByText("Exchange 1 of 4")).toBeInTheDocument();
  });

  it("still reports exchange 2 while on the student half of that exchange", () => {
    const state: ConversationState = { turnIndex: 3, step: "student" };
    render(<ConversationTurnProgress turns={turns} state={state} />);
    expect(screen.getByText("Exchange 2 of 4")).toBeInTheDocument();
  });

  it("reports the final exchange during its system turn", () => {
    const state: ConversationState = { turnIndex: 6, step: "system" };
    render(<ConversationTurnProgress turns={turns} state={state} />);
    expect(screen.getByText("Exchange 4 of 4")).toBeInTheDocument();
  });

  it("shows a completion label once the conversation reaches summary", () => {
    const state: ConversationState = { turnIndex: 8, step: "summary" };
    render(<ConversationTurnProgress turns={turns} state={state} />);
    expect(screen.getByText("Conversation complete")).toBeInTheDocument();
  });

  it("renders exactly one rail dot per exchange, not per raw turn", () => {
    const state: ConversationState = { turnIndex: 0, step: "system" };
    const { container } = render(<ConversationTurnProgress turns={turns} state={state} />);
    expect(container.querySelectorAll(".conversation-turn-progress__rail > li")).toHaveLength(4);
  });
});
