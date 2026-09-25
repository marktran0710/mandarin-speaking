import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import StoryBuilderConversationEditor from "./StoryBuilderSection.ConversationEditor";
import { blankConversationExchange, emptyCustomStoryDraft } from "./StoryBuilderSection.helpers";

function renderEditor(draft: typeof emptyCustomStoryDraft) {
  let current = draft;
  const onSetDraft = vi.fn((updater: any) => {
    current = typeof updater === "function" ? updater(current) : updater;
  });
  const view = render(
    <StoryBuilderConversationEditor draft={current} onSetDraft={onSetDraft} setValidationErrors={vi.fn()} />,
  );
  return { onSetDraft, getDraft: () => current, ...view };
}

describe("StoryBuilderConversationEditor", () => {
  it("shows only the enable toggle when conversation practice is off", () => {
    renderEditor({ ...emptyCustomStoryDraft, conversationEnabled: false, conversationExchanges: [] });
    expect(screen.getByLabelText("Enable Conversation Practice")).not.toBeChecked();
    expect(screen.queryByText("+ Add exchange")).not.toBeInTheDocument();
  });

  it("enabling the toggle seeds one blank exchange", () => {
    const { onSetDraft } = renderEditor({ ...emptyCustomStoryDraft, conversationEnabled: false, conversationExchanges: [] });
    fireEvent.click(screen.getByLabelText("Enable Conversation Practice"));
    expect(onSetDraft).toHaveBeenCalled();
  });

  it("renders each exchange's character and student fieldsets", () => {
    const exchange = { ...blankConversationExchange("ex-1"), characterText: "你好", studentText: "你好！" };
    renderEditor({ ...emptyCustomStoryDraft, conversationEnabled: true, conversationExchanges: [exchange] });
    expect(screen.getByText("Exchange 1")).toBeInTheDocument();
    expect(screen.getByDisplayValue("你好")).toBeInTheDocument();
    expect(screen.getByDisplayValue("你好！")).toBeInTheDocument();
    expect(screen.getByText("Character")).toBeInTheDocument();
    expect(screen.getByText("Student's response")).toBeInTheDocument();
  });

  it("adding an exchange appends a new blank one", () => {
    const exchange = blankConversationExchange("ex-1");
    const { onSetDraft, getDraft } = renderEditor({
      ...emptyCustomStoryDraft,
      conversationEnabled: true,
      conversationExchanges: [exchange],
    });
    fireEvent.click(screen.getByText("+ Add exchange"));
    expect(onSetDraft).toHaveBeenCalled();
    expect(getDraft().conversationExchanges).toHaveLength(2);
  });

  it("deleting an exchange removes it", () => {
    const exchange = blankConversationExchange("ex-1");
    const { getDraft } = renderEditor({
      ...emptyCustomStoryDraft,
      conversationEnabled: true,
      conversationExchanges: [exchange],
    });
    fireEvent.click(screen.getByLabelText("Delete exchange 1"));
    expect(getDraft().conversationExchanges).toHaveLength(0);
  });

  it("the up-arrow is disabled on the first exchange and the down-arrow on the last", () => {
    const exchanges = [blankConversationExchange("ex-1"), blankConversationExchange("ex-2")];
    renderEditor({ ...emptyCustomStoryDraft, conversationEnabled: true, conversationExchanges: exchanges });
    expect(screen.getByLabelText("Move exchange 1 up")).toBeDisabled();
    expect(screen.getByLabelText("Move exchange 2 down")).toBeDisabled();
    expect(screen.getByLabelText("Move exchange 1 down")).not.toBeDisabled();
    expect(screen.getByLabelText("Move exchange 2 up")).not.toBeDisabled();
  });

  it("moving an exchange down swaps it with the next one", () => {
    const exchanges = [
      { ...blankConversationExchange("ex-1"), characterText: "first" },
      { ...blankConversationExchange("ex-2"), characterText: "second" },
    ];
    const { getDraft } = renderEditor({ ...emptyCustomStoryDraft, conversationEnabled: true, conversationExchanges: exchanges });
    fireEvent.click(screen.getByLabelText("Move exchange 1 down"));
    expect(getDraft().conversationExchanges[0].characterText).toBe("second");
    expect(getDraft().conversationExchanges[1].characterText).toBe("first");
  });
});
